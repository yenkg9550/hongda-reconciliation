"""對帳服務（MongoDB 版）。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db.collections import M1_RESULTS, M2_RESULTS, M3_EXCEPTIONS, UPLOAD_JOBS, VENUES


async def trigger_reconcile(
    db: Any, *, module: str, period_start: date, period_end: date
) -> dict:
    if module not in ("m1", "m2", "m3"):
        raise ValueError(f"unknown module: {module}")
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


def _money(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _period_query(period_start: date, period_end: date) -> dict[str, str]:
    return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()}


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
    }
