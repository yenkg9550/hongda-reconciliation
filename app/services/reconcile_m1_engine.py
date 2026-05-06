"""M1a 對帳引擎（async/Mongo 版）。

跟 backend_20260506/app/services/reconcile_m1.py 同邏輯：
- vendor 某 venue 某天合計 × (1 - rate) ≈ bank 某天某筆撥款
- lag D-1 ~ D-7 + 累計 1~31 天
- tolerance ±1 元
- abs_diff/bank_amount < 5% 算 partial、其餘 unmatched

寫入 m1_results collection 並回傳統計。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from app.db.collections import (
    BANK_ENTRIES,
    FEE_RATES,
    M1_DETAILS,
    UPLOAD_JOBS,
    VENDOR_TX,
    VENUES,
)
from app.services.reference_classifier import ClassifierCache, classify_reference


LAG_DAYS = list(range(1, 8))
TOLERANCE = 1.0
ACCUM_MAX_DAYS = 31

# vendor 端 payment_type 標準化
_PAY_NORM = {
    "linepay": "linepay",
    "LinePay": "linepay",
    "LINE Pay": "linepay",
    "Line支付": "linepay",
    "easycard": "easycard",
    "悠遊卡": "easycard",
    "票卡": "easycard",
    "creditcard": "creditcard",
    "ApplePay": "creditcard",
    "apple Pay": "creditcard",
    "GooglePay": "creditcard",
    "街口支付": "jkopay",
    "jkopay": "jkopay",
    "悠遊付": "easywallet",
    "easywallet": "easywallet",
    "ipass": "ipass",
    "iPASS MONEY": "ipass",
    "一卡通": "ipass",
    "一卡通Money": "ipass",
    "EasyPay": "easycard",
    "icash": "icash",
    "iCash": "icash",
    "icash pay": "icash",
    "cash": "cash",
}


def _norm_pay(pt):
    if pt is None:
        return None
    return _PAY_NORM.get(pt, pt)


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


class M1Cache:
    """記憶體快取：venues / rates / vendor_sums，加速 lookup。"""

    def __init__(self) -> None:
        self.venue_to_vendor: dict[str, Optional[str]] = {}
        # rates: (vendor_code, payment_type) -> [(effective_date, rate), ...] 倒序
        self.rates: dict[tuple, list[tuple[date, float]]] = defaultdict(list)
        # vendor_sums: (venue_code, date, payment_type) -> sum
        self.vendor_sums: dict[tuple, float] = defaultdict(float)
        self.vendor_sums_any_pay: dict[tuple, float] = defaultdict(float)
        self.vendor_total_by_day: dict[tuple, float] = defaultdict(float)

    @classmethod
    async def build(cls, db: Any) -> "M1Cache":
        self = cls()

        # venues
        async for v in db[VENUES].find({}, {"venue_code": 1, "vendor_code": 1, "_id": 1}):
            vc = v.get("venue_code") or v.get("_id")
            self.venue_to_vendor[vc] = v.get("vendor_code")

        # rates
        async for r in db[FEE_RATES].find({}):
            try:
                rate = float(r.get("rate", 0))
            except (TypeError, ValueError):
                continue
            eff = _to_date(r.get("effective_date")) or date(1900, 1, 1)
            self.rates[(r.get("vendor_code"), r.get("payment_type"))].append((eff, rate))
        for k in self.rates:
            self.rates[k].sort(key=lambda x: x[0], reverse=True)

        # vendor_transactions
        cursor = db[VENDOR_TX].find(
            {},
            {"venue_code": 1, "transaction_date": 1, "payment_type": 1, "amount": 1, "_id": 0},
        )
        async for row in cursor:
            vc = row.get("venue_code")
            d = _to_date(row.get("transaction_date"))
            try:
                amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            if not vc or not d:
                continue
            pt = _norm_pay(row.get("payment_type"))
            self.vendor_sums[(vc, d, pt)] += amt
            self.vendor_sums_any_pay[(vc, d)] += amt

        for (vc, d), s in self.vendor_sums_any_pay.items():
            vendor_code = self.venue_to_vendor.get(vc)
            if vendor_code:
                self.vendor_total_by_day[(vendor_code, d)] += s

        return self

    def get_rate(self, vendor_code: Optional[str], payment_type: str, on_date: date) -> float:
        if not payment_type:
            return 0.0
        for key in [(vendor_code, payment_type), (None, payment_type)]:
            for eff, rate in self.rates.get(key, []):
                if eff <= on_date:
                    return rate
        return 0.0

    def vendor_sum(
        self, venue_code: str, target_date: date, payment_type: Optional[str]
    ) -> float:
        pt = _norm_pay(payment_type) if payment_type else None
        if pt:
            return self.vendor_sums.get((venue_code, target_date, pt), 0.0)
        return self.vendor_sums_any_pay.get((venue_code, target_date), 0.0)

    def vendor_total_range(self, vendor_code: str, start: date, end: date) -> float:
        total = 0.0
        d = start
        while d <= end:
            total += self.vendor_total_by_day.get((vendor_code, d), 0.0)
            d += timedelta(days=1)
        return total


def _try_match_venue(
    cache: M1Cache,
    bank_date: date,
    bank_amount: float,
    venue_code: str,
    payment_type: Optional[str],
) -> Optional[dict]:
    """從 D-1 往前累計，看哪個區間的 vendor 合計 ≈ bank 撥款。"""
    vendor_code = cache.venue_to_vendor.get(venue_code)
    rate = cache.get_rate(vendor_code, payment_type or "", bank_date)

    # (a) 單日 D-1~D-7
    for offset in LAG_DAYS:
        target = bank_date - timedelta(days=offset)
        v_sum = cache.vendor_sum(venue_code, target, payment_type)
        if v_sum <= 0:
            continue
        expected = v_sum * (1 - rate)
        if abs(expected - bank_amount) <= TOLERANCE:
            return {
                "transaction_date": target,
                "vendor_amount": v_sum,
                "expected_remit": expected,
                "diff": expected - bank_amount,
                "rate": rate,
                "lag_days": offset,
                "accum_days": 1,
            }

    # (b) 累計：對每個 end_offset，往前累積 1~31 天
    for end_offset in LAG_DAYS:
        end_date = bank_date - timedelta(days=end_offset)
        running = 0.0
        for span in range(1, ACCUM_MAX_DAYS + 1):
            day = end_date - timedelta(days=span - 1)
            running += cache.vendor_sum(venue_code, day, payment_type)
            if running <= 0:
                continue
            expected = running * (1 - rate)
            if abs(expected - bank_amount) <= TOLERANCE:
                return {
                    "transaction_date": end_date,
                    "vendor_amount": running,
                    "expected_remit": expected,
                    "diff": expected - bank_amount,
                    "rate": rate,
                    "lag_days": end_offset,
                    "accum_days": span,
                }
    return None


def _find_closest_window(
    cache: M1Cache,
    bank_date: date,
    bank_amount: float,
    venue_code: str,
    payment_type: Optional[str],
) -> Optional[dict]:
    """找 |expected - bank_amount| 最小的累計 window（不限 tolerance）。"""
    vendor_code = cache.venue_to_vendor.get(venue_code)
    rate = cache.get_rate(vendor_code, payment_type or "", bank_date)

    best: Optional[dict] = None
    for end_offset in LAG_DAYS:
        end_date = bank_date - timedelta(days=end_offset)
        running = 0.0
        for span in range(1, ACCUM_MAX_DAYS + 1):
            day = end_date - timedelta(days=span - 1)
            running += cache.vendor_sum(venue_code, day, payment_type)
            if running <= 0:
                continue
            expected = running * (1 - rate)
            abs_diff = abs(expected - bank_amount)
            if best is None or abs_diff < best["abs_diff"]:
                best = {
                    "transaction_date": end_date,
                    "vendor_amount": running,
                    "expected_remit": expected,
                    "diff": expected - bank_amount,
                    "abs_diff": abs_diff,
                    "rate": rate,
                    "lag_days": end_offset,
                    "accum_days": span,
                }
    return best


async def _company_bank_entries(
    db: Any, period_start: date, period_end: date
) -> list[dict]:
    """撈期間內公司戶（宏達 / 晉呈）的銀行入帳。"""
    job_cursor = db[UPLOAD_JOBS].find(
        {
            "source_type": "bank",
            "$or": [
                {"filename": {"$regex": "宏達"}},
                {"filename": {"$regex": "晉呈"}},
            ],
        },
        {"job_id": 1, "filename": 1, "_id": 0},
    )
    jobs = await job_cursor.to_list(length=200)
    if not jobs:
        return []
    job_ids = [j["job_id"] for j in jobs]
    job_filename = {j["job_id"]: j.get("filename", "") for j in jobs}

    cursor = db[BANK_ENTRIES].find(
        {
            "job_id": {"$in": job_ids},
            "value_date": {
                "$gte": period_start.isoformat(),
                "$lte": period_end.isoformat(),
            },
        }
    ).sort("value_date", 1)
    rows = await cursor.to_list(length=100_000)
    out = []
    for i, r in enumerate(rows, 1):
        out.append(
            {
                "bank_id": i,
                "transaction_date": _to_date(r.get("value_date")),
                "amount": float(r.get("amount") or 0),
                # 用 memo_raw 當 reference（跟 sample 對齊）；description 太短沒場名
                "reference": r.get("memo_raw") or r.get("description") or "",
                "filename": job_filename.get(r.get("job_id"), ""),
                "_orig_id": r.get("_id"),
            }
        )
    return out


async def reconcile_period(db: Any, period_start: date, period_end: date) -> dict:
    """跑 M1a 對帳，把結果寫進 m1_results、回傳統計。"""
    import logging, time
    log = logging.getLogger(__name__)
    t0 = time.time()
    batch_id = str(uuid4())
    bank_txns = await _company_bank_entries(db, period_start, period_end)
    log.info("m1: loaded %d bank txns in %.1fs", len(bank_txns), time.time() - t0)
    cache = await M1Cache.build(db)
    log.info("m1: built M1Cache in %.1fs", time.time() - t0)
    classifier_cache = await ClassifierCache.build(db)
    log.info("m1: built ClassifierCache in %.1fs (mappings=%d, venues=%d)",
             time.time() - t0,
             sum(len(v) for v in classifier_cache.mapping_by_source.values()),
             len(classifier_cache.venues_active))

    # 清掉同期間舊資料再寫新的（per-bank-entry 明細放 m1_details，跟 ScreenE 用的 m1_results 分開）
    await db[M1_DETAILS].delete_many(
        {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()}
    )

    stats = {
        "batch_id": batch_id,
        "bank_txn_count": len(bank_txns),
        "matched": 0,
        "partial": 0,
        "unmatched": 0,
        "by_strategy": defaultdict(int),
    }

    docs: list[dict] = []
    for bt in bank_txns:
        if bt["transaction_date"] is None:
            continue
        cm = await classify_reference(bt["reference"], db, cache=classifier_cache)
        match_info: Optional[dict] = None
        matched_venue_code: Optional[str] = None

        if cm.confidence == "exact" and cm.venue_code:
            match_info = _try_match_venue(
                cache, bt["transaction_date"], bt["amount"], cm.venue_code, cm.payment_type
            )
            if match_info:
                matched_venue_code = cm.venue_code
                stats["by_strategy"]["exact"] += 1

        elif cm.confidence == "fuzzy" and cm.venue_candidates:
            for cand in cm.venue_candidates:
                m = _try_match_venue(
                    cache, bt["transaction_date"], bt["amount"], cand, cm.payment_type
                )
                if m:
                    match_info = m
                    matched_venue_code = cand
                    stats["by_strategy"]["fuzzy"] += 1
                    break

        elif cm.confidence == "vendor_total" and cm.vendor_code:
            vendors_try = (
                ["fuer_car", "fuer_ticket"] if cm.vendor_code == "fuer" else [cm.vendor_code]
            )
            for vc in vendors_try:
                v_sum = cache.vendor_total_range(
                    vc,
                    bt["transaction_date"] - timedelta(days=31),
                    bt["transaction_date"] - timedelta(days=1),
                )
                if v_sum <= 0:
                    continue
                rate = cache.get_rate(vc, cm.payment_type or "", bt["transaction_date"])
                expected = v_sum * (1 - rate)
                if abs(expected - bt["amount"]) <= TOLERANCE:
                    match_info = {
                        "transaction_date": bt["transaction_date"],
                        "vendor_amount": v_sum,
                        "expected_remit": expected,
                        "diff": expected - bt["amount"],
                        "rate": rate,
                        "lag_days": -1,
                    }
                    matched_venue_code = None
                    stats["by_strategy"]["vendor_total"] += 1
                    break

        meta: dict = {
            "bank_id": bt["bank_id"],
            "classifier_confidence": cm.confidence,
            "classifier_pattern": cm.raw_pattern,
            "classifier_candidates": cm.venue_candidates,
        }

        doc: dict[str, Any] = {
            "reconcile_batch_id": batch_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "bank_id": bt["bank_id"],
            "bank_transaction_date": bt["transaction_date"].isoformat(),
            "bank_amount": bt["amount"],
            "bank_filename": bt["filename"],
            "reference": bt["reference"],
            "venue_code": matched_venue_code,
            "vendor_code": cm.vendor_code,
            "payment_type": cm.payment_type,
            "actual_remit": bt["amount"],
            "meta": meta,
        }

        if match_info:
            doc["vendor_amount"] = match_info["vendor_amount"]
            doc["expected_remit"] = match_info["expected_remit"]
            doc["diff"] = match_info["diff"]
            doc["status"] = "matched"
            meta.update({
                "match_strategy": "exact_or_fuzzy",
                "lag_days": match_info.get("lag_days"),
                "accum_days": match_info.get("accum_days"),
                "rate": match_info.get("rate"),
            })
            stats["matched"] += 1
        else:
            # closest fallback
            fuzzy_best: Optional[dict] = None
            fuzzy_venue: Optional[str] = None
            try_venues: list[str] = []
            if cm.confidence == "exact" and cm.venue_code:
                try_venues = [cm.venue_code]
            elif cm.confidence == "fuzzy" and cm.venue_candidates:
                try_venues = cm.venue_candidates
            for cand in try_venues:
                fb = _find_closest_window(
                    cache, bt["transaction_date"], bt["amount"], cand, cm.payment_type
                )
                if fb and (fuzzy_best is None or fb["abs_diff"] < fuzzy_best["abs_diff"]):
                    fuzzy_best = fb
                    fuzzy_venue = cand

            if fuzzy_best:
                doc["vendor_amount"] = fuzzy_best["vendor_amount"]
                doc["expected_remit"] = fuzzy_best["expected_remit"]
                doc["diff"] = fuzzy_best["diff"]
                doc["venue_code"] = fuzzy_venue
                meta.update({
                    "match_strategy": "closest_partial",
                    "lag_days": fuzzy_best.get("lag_days"),
                    "accum_days": fuzzy_best.get("accum_days"),
                    "rate": fuzzy_best.get("rate"),
                })
                pct = fuzzy_best["abs_diff"] / max(bt["amount"], 1) * 100
                if pct < 5:
                    doc["status"] = "partial"
                    stats["partial"] += 1
                else:
                    doc["status"] = "unmatched"
                    stats["unmatched"] += 1
            else:
                doc["status"] = "unmatched"
                stats["unmatched"] += 1

        docs.append(doc)

    if docs:
        # 分批 insert，避免一次太大
        BATCH = 500
        for i in range(0, len(docs), BATCH):
            await db[M1_DETAILS].insert_many(docs[i : i + BATCH])

    stats["by_strategy"] = dict(stats["by_strategy"])
    log.info(
        "m1: reconcile_period done in %.1fs. matched=%d partial=%d unmatched=%d",
        time.time() - t0, stats["matched"], stats["partial"], stats["unmatched"],
    )
    return stats
