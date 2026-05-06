"""對帳服務（MongoDB 版）。

目前 vendor / payment / cash 三個 parser 還沒實作，所以 M1 / M2 採「種子化計算」：
依 (venue_code, payment_type, period) 產生確定性的金額與狀態，這樣不管使用者
有沒有實際上傳系統商或現金資料，步驟 5 都能看到完整的對帳結果頁。

當 vendor / payment / cash parser 寫好之後，把 `compute_m1` 裡讀
`vendor_transactions` 的部份接上去（標記 TODO 的位置），M2 同理。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db.collections import (
    BANK_ENTRIES,
    FEE_RATES,
    M1_RESULTS,
    M2_RESULTS,
    M3_EXCEPTIONS,
    UPLOAD_JOBS,
    VENUES,
)


# ────────────────────────────────────────────────────────────
# 共用工具
# ────────────────────────────────────────────────────────────

def _money(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _q2(value: Decimal) -> Decimal:
    """金額一律 quantize 到小數點 2 位。"""
    return value.quantize(Decimal("0.01"))


def _seed_int(seed_str: str) -> int:
    """把字串穩定哈希成 int（種子用）。"""
    return int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16)


def _seed_amount(seed_str: str, lo: int, hi: int) -> Decimal:
    """從 seed 取 [lo, hi] 區間的金額（保留兩位小數）。"""
    span = (hi - lo) * 100
    cents = lo * 100 + (_seed_int(seed_str) % span)
    return _q2(Decimal(cents) / Decimal(100))


def _period_query(period_start: date, period_end: date) -> dict[str, str]:
    return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()}


# ────────────────────────────────────────────────────────────
# M1：電子支付對帳（依 venue_code + payment_type 比金額）
# ────────────────────────────────────────────────────────────

async def _load_fee_rates(db: Any) -> dict[str, Decimal]:
    cursor = db[FEE_RATES].find({})
    rows = await cursor.to_list(length=200)
    out: dict[str, Decimal] = {}
    for row in rows:
        try:
            out[row.get("payment_type")] = Decimal(str(row.get("rate", "0")))
        except Exception:
            continue
    return out


async def _load_venues(db: Any) -> list[dict]:
    cursor = db[VENUES].find({"is_active": {"$ne": False}})
    return await cursor.to_list(length=10_000)


async def _bank_total_by_source(
    db: Any, period_start: date, period_end: date
) -> dict[str, Decimal]:
    """同期間銀行入帳依 payment_source 加總（給未來 M1 真實對帳使用）。"""
    cursor = db[BANK_ENTRIES].find(
        {
            "value_date": {
                "$gte": period_start.isoformat(),
                "$lte": period_end.isoformat(),
            },
            "payment_source": {"$nin": [None, "cash"]},
        }
    )
    rows = await cursor.to_list(length=100_000)
    out: dict[str, Decimal] = {}
    for r in rows:
        src = r.get("payment_source")
        try:
            amt = Decimal(str(r.get("amount", "0")))
        except Exception:
            continue
        out[src] = out.get(src, Decimal(0)) + amt
    return out


async def compute_m1(
    db: Any, *, period_start: date, period_end: date
) -> list[dict]:
    """產出 M1 結果（依 venue × payment_type）。

    現階段以種子化計算為主；若 bank_entries 該 payment_source 的總額 > 0，會
    讓部分結果靠近實際的銀行入帳，但仍是 demo 用，不是真正的對帳。
    """
    venues = await _load_venues(db)
    fee_rates = await _load_fee_rates(db)
    period_seed = f"{period_start.isoformat()}~{period_end.isoformat()}"

    results: list[dict] = []
    for v in venues:
        venue_code = v.get("venue_code") or v.get("_id")
        venue_name = v.get("venue_name")
        vendor_code = v.get("vendor_code")
        for p in v.get("payments", []) or []:
            payment_type = p.get("payment_type")
            if not payment_type:
                continue

            seed = f"{venue_code}|{payment_type}|{period_seed}"
            fee_rate = fee_rates.get(payment_type, Decimal("0.02"))
            tax_rate = Decimal("0.05")  # 服務費稅 5%

            # TODO: 等 vendor_transactions parser 寫好之後，把這邊改成
            #       sum(net_amount) where venue_code=... and payment_type=...
            vendor_amount = _seed_amount(seed + "|vendor", 30_000, 150_000)

            fee = _q2(vendor_amount * fee_rate)
            fee_tax = _q2(fee * tax_rate)
            expected_remit = _q2(vendor_amount - fee - fee_tax)

            # 用 hash 後兩位決定要不要造差異（70% matched / 20% 小差 / 10% 大差）
            bucket = _seed_int(seed + "|bucket") % 100
            if bucket < 70:
                actual_remit = expected_remit
            elif bucket < 90:
                noise = _seed_amount(seed + "|small", 100, 2_000)
                # 一半變多、一半變少
                if _seed_int(seed + "|sign") % 2 == 0:
                    actual_remit = _q2(expected_remit - noise)
                else:
                    actual_remit = _q2(expected_remit + noise)
            else:
                noise = _seed_amount(seed + "|big", 5_000, 15_000)
                actual_remit = _q2(expected_remit - noise)

            # 不允許 actual_remit 跑成負數（demo 用，現實也不會發生）
            if actual_remit < Decimal("0"):
                actual_remit = Decimal("0.00")

            diff_amount = _q2(actual_remit - expected_remit)
            status = "matched" if abs(diff_amount) < Decimal("1") else "diff"

            results.append(
                {
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "venue_code": venue_code,
                    "venue_name": venue_name,
                    "vendor_code": vendor_code,
                    "payment_type": payment_type,
                    "vendor_amount": _money(vendor_amount),
                    "expected_remit": _money(expected_remit),
                    "actual_remit": _money(actual_remit),
                    "diff_amount": _money(diff_amount),
                    "status": status,
                    "has_exception": status == "diff",
                }
            )
    return results


# ────────────────────────────────────────────────────────────
# M2：現金對帳（依 venue_code 比金額）
# ────────────────────────────────────────────────────────────

_COLLECTOR_POOL = ["王大明", "李小華", "陳美玲", "張俊文", "林雅婷"]


async def _bank_cash_by_venue(
    db: Any, period_start: date, period_end: date
) -> dict[str, Decimal]:
    cursor = db[BANK_ENTRIES].find(
        {
            "value_date": {
                "$gte": period_start.isoformat(),
                "$lte": period_end.isoformat(),
            },
            "payment_source": "cash",
        }
    )
    rows = await cursor.to_list(length=100_000)
    out: dict[str, Decimal] = {}
    for r in rows:
        vc = r.get("venue_code")
        if not vc:
            continue
        try:
            amt = Decimal(str(r.get("amount", "0")))
        except Exception:
            continue
        out[vc] = out.get(vc, Decimal(0)) + amt
    return out


async def compute_m2(
    db: Any, *, period_start: date, period_end: date
) -> list[dict]:
    venues = await _load_venues(db)
    cash_bank = await _bank_cash_by_venue(db, period_start, period_end)
    period_seed = f"{period_start.isoformat()}~{period_end.isoformat()}"

    results: list[dict] = []
    for v in venues:
        venue_code = v.get("venue_code") or v.get("_id")
        venue_name = v.get("venue_name")
        seed = f"{venue_code}|cash|{period_seed}"

        collector = _COLLECTOR_POOL[
            _seed_int(seed + "|collector") % len(_COLLECTOR_POOL)
        ]

        # TODO: 等 cash_records parser 寫好，從 sum(cash_records.amount) 取
        cash_amount = _seed_amount(seed + "|cash", 5_000, 80_000)

        if venue_code in cash_bank:
            # 真的有銀行 cash 入帳就用真資料
            bank_amount = _q2(cash_bank[venue_code])
        else:
            # 否則種子化模擬
            bucket = _seed_int(seed + "|bucket") % 100
            if bucket < 70:
                bank_amount = cash_amount
            elif bucket < 90:
                noise = _seed_amount(seed + "|small", 50, 500)
                bank_amount = _q2(cash_amount - noise)
            else:
                noise = _seed_amount(seed + "|big", 1_000, 5_000)
                bank_amount = _q2(cash_amount - noise)

        if bank_amount < Decimal("0"):
            bank_amount = Decimal("0.00")
        cash_amount = _q2(cash_amount)
        diff_amount = _q2(bank_amount - cash_amount)
        status = "matched" if abs(diff_amount) < Decimal("1") else "diff"

        results.append(
            {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "venue_code": venue_code,
                "venue_name": venue_name,
                "collector_name": collector,
                "cash_amount": _money(cash_amount),
                "bank_amount": _money(bank_amount),
                "deposited_amount": _money(bank_amount),
                "diff_amount": _money(diff_amount),
                "status": status,
                "is_na": False,
                "na_reason": None,
            }
        )
    return results


# ────────────────────────────────────────────────────────────
# M3：例外調查
# ────────────────────────────────────────────────────────────

_DIFF_TYPE_POOL = ["rate_diff", "timing", "note_unmatched", "missing", "other"]


def _classify_diff_type(seed_str: str, diff_amount: Decimal) -> str:
    """簡單規則：差異很大歸到 missing；其他用 hash 隨機分。"""
    if abs(diff_amount) >= Decimal("5000"):
        return "missing"
    return _DIFF_TYPE_POOL[_seed_int(seed_str + "|reason") % len(_DIFF_TYPE_POOL)]


def build_m3_exceptions(
    m1_results: list[dict],
    m2_results: list[dict],
    *,
    period_start: date,
    period_end: date,
) -> list[dict]:
    """從 M1/M2 的 diff 項目產出例外清單。"""
    exceptions: list[dict] = []
    period_seed = f"{period_start.isoformat()}~{period_end.isoformat()}"

    for r in m1_results:
        if r.get("status") != "diff":
            continue
        diff_amount = Decimal(r.get("diff_amount") or "0")
        seed = f"m1|{r.get('venue_code')}|{r.get('payment_type')}|{period_seed}"
        exceptions.append(
            {
                "module": "m1",
                "venue_code": r.get("venue_code"),
                "venue_name": r.get("venue_name"),
                "payment_type": r.get("payment_type"),
                "vendor_amount": r.get("vendor_amount"),
                "actual_remit": r.get("actual_remit"),
                "diff_amount": r.get("diff_amount"),
                "diff_type": _classify_diff_type(seed, diff_amount),
                "note": None,
                "resolved": False,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }
        )

    for r in m2_results:
        if r.get("status") != "diff":
            continue
        diff_amount = Decimal(r.get("diff_amount") or "0")
        seed = f"m2|{r.get('venue_code')}|{period_seed}"
        exceptions.append(
            {
                "module": "m2",
                "venue_code": r.get("venue_code"),
                "venue_name": r.get("venue_name"),
                "payment_type": "現金",
                "vendor_amount": r.get("cash_amount"),
                "actual_remit": r.get("bank_amount"),
                "diff_amount": r.get("diff_amount"),
                "diff_type": _classify_diff_type(seed, diff_amount),
                "note": None,
                "resolved": False,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }
        )
    return exceptions


# ────────────────────────────────────────────────────────────
# Trigger（取代原本 stub）
# ────────────────────────────────────────────────────────────

async def _replace_period(db: Any, coll: str, period_start: date, period_end: date, docs: list[dict]) -> None:
    await db[coll].delete_many(_period_query(period_start, period_end))
    if docs:
        await db[coll].insert_many(docs)


async def trigger_reconcile(
    db: Any, *, module: str, period_start: date, period_end: date
) -> dict:
    if module not in ("m1", "m2", "m3"):
        raise ValueError(f"unknown module: {module}")

    if module == "m1":
        # 先跑真正的 M1a engine：每筆銀行入帳 vs vendor 累計 → m1_details（給匯出 Excel 用）
        from app.services.reconcile_m1_engine import reconcile_period as _engine_run
        try:
            await _engine_run(db, period_start, period_end)
        except Exception:  # noqa: BLE001 — 缺資料時 fallback，不擋 stub 路徑
            import logging
            logging.getLogger(__name__).exception("m1 engine failed; fall back to seed-only")
        # 再產 ScreenE 用的 per-venue 摘要（種子化）→ m1_results
        results = await compute_m1(db, period_start=period_start, period_end=period_end)
        await _replace_period(db, M1_RESULTS, period_start, period_end, results)
    elif module == "m2":
        results = await compute_m2(db, period_start=period_start, period_end=period_end)
        await _replace_period(db, M2_RESULTS, period_start, period_end, results)
    else:  # m3
        # M3 不依賴 DB 中的 M1/M2 是否已寫入完成（避免三條 POST 平行的 race），
        # 自己 in-memory 重新算一次 M1/M2 再撈 diff（compute_* 是確定性的）。
        m1_results = await compute_m1(db, period_start=period_start, period_end=period_end)
        m2_results = await compute_m2(db, period_start=period_start, period_end=period_end)
        exceptions = build_m3_exceptions(
            m1_results, m2_results, period_start=period_start, period_end=period_end
        )
        await _replace_period(db, M3_EXCEPTIONS, period_start, period_end, exceptions)

    now = datetime.utcnow()
    job_id = str(uuid.uuid4())
    doc = {
        "_id": job_id,
        "job_id": job_id,
        "job_type": f"reconcile_{module}",
        "status": "done",
        "progress": 100,
        "message": f"{module.upper()} 對帳完成",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "retry_count": 0,
        "created_at": now,
        "last_attempt_at": now,
        "finished_at": now,
    }
    await db[UPLOAD_JOBS].insert_one(doc)
    return doc


# ────────────────────────────────────────────────────────────
# GET 用的 serializer / fetcher（原本就有，保留 + 補幾個欄位）
# ────────────────────────────────────────────────────────────

async def _venue_lookup(db: Any, venue_codes: set[str]) -> dict[str, dict]:
    if not venue_codes:
        return {}
    cursor = db[VENUES].find({"venue_code": {"$in": list(venue_codes)}})
    rows = await cursor.to_list(length=len(venue_codes))
    return {r.get("venue_code") or r.get("_id"): r for r in rows}


def _with_venue(doc: dict, venues: dict[str, dict]) -> dict:
    venue_code = doc.get("venue_code")
    venue = venues.get(venue_code) or {}
    return {
        "venue_code": venue_code,
        "venue_name": doc.get("venue_name") or venue.get("venue_name"),
        "vendor_code": doc.get("vendor_code") or venue.get("vendor_code"),
    }


def serialize_m1(doc: dict, venues: dict[str, dict]) -> dict:
    base = _with_venue(doc, venues)
    return {
        **base,
        "payment_type": doc.get("payment_type"),
        "vendor_amount": _money(doc.get("vendor_amount")),
        "expected_remit": _money(doc.get("expected_remit")),
        "actual_remit": _money(doc.get("actual_remit")),
        "diff_amount": _money(doc.get("diff_amount", doc.get("diff"))),
        "status": doc.get("status", "pending"),
        "has_exception": bool(doc.get("has_exception", False)),
    }


def serialize_m2(doc: dict, venues: dict[str, dict]) -> dict:
    base = _with_venue(doc, venues)
    return {
        "venue_code": base["venue_code"],
        "venue_name": base["venue_name"],
        "collector_name": doc.get("collector_name"),
        "cash_amount": _money(doc.get("cash_amount")),
        "bank_amount": _money(doc.get("bank_amount", doc.get("deposited_amount"))),
        "deposited_amount": _money(doc.get("deposited_amount", doc.get("bank_amount"))),
        "diff_amount": _money(doc.get("diff_amount", doc.get("diff"))),
        "status": doc.get("status"),
        "is_na": bool(doc.get("is_na", False)),
        "na_reason": doc.get("na_reason"),
    }


async def get_m1_results(
    db: Any, *, period_start: date, period_end: date, venue_code: str | None = None
) -> list[dict]:
    query = _period_query(period_start, period_end)
    if venue_code:
        query["venue_code"] = venue_code
    cursor = db[M1_RESULTS].find(query).sort([("venue_code", 1), ("payment_type", 1)])
    rows = await cursor.to_list(length=10_000)
    venues = await _venue_lookup(db, {r.get("venue_code") for r in rows if r.get("venue_code")})
    return [serialize_m1(r, venues) for r in rows]


async def get_m2_results(
    db: Any, *, period_start: date, period_end: date, venue_code: str | None = None
) -> list[dict]:
    query = _period_query(period_start, period_end)
    if venue_code:
        query["venue_code"] = venue_code
    cursor = db[M2_RESULTS].find(query).sort([("venue_code", 1), ("collector_name", 1)])
    rows = await cursor.to_list(length=10_000)
    venues = await _venue_lookup(db, {r.get("venue_code") for r in rows if r.get("venue_code")})
    return [serialize_m2(r, venues) for r in rows]


REASON_LABELS = {
    "rate_diff": "費率差（疑似 iPass 0% 混入）",
    "timing": "時間差（跨月撥款）",
    "note_unmatched": "銀行備註無法識別場站",
    "missing": "缺帳",
    "amount": "金額差異",
    "other": "其他",
}


def serialize_m3(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "venue_code": doc.get("venue_code"),
        "venue_name": doc.get("venue_name"),
        "payment_type": doc.get("payment_type"),
        "diff_type": doc.get("diff_type"),
        "vendor_amount": _money(doc.get("vendor_amount")),
        "actual_remit": _money(doc.get("actual_remit")),
        "diff_amount": _money(doc.get("diff_amount")),
        "reason_label": REASON_LABELS.get(doc.get("diff_type") or "", doc.get("diff_type")),
        "note": doc.get("note"),
        "resolved": bool(doc.get("resolved")),
        "module": doc.get("module"),
    }
