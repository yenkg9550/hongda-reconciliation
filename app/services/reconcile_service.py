"""對帳骨架（MongoDB 版）。

Stage 1：
- 觸發 reconcile 會在 upload_jobs 建立一筆 job_type=reconcile_m1/m2/m3，立即標 done
- GET 結果回傳 stub 資料
- M3 第一次呼叫時會把示範例外塞進 m3_exceptions collection
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db.collections import M3_EXCEPTIONS, UPLOAD_JOBS


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
        "message": f"{module.upper()} 對帳完成（骨架版本，未實作 engine）",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "retry_count": 0,
        "created_at": now,
        "last_attempt_at": now,
        "finished_at": now,
    }
    await db[UPLOAD_JOBS].insert_one(doc)
    return doc


# ── stub 場站 ───────────────────────────────────────────
_VENUES = [
    ("001", "北城停車場", "遠通"),
    ("002", "南港車站", "遠通"),
    ("003", "台北 101", "微程式"),
    ("005", "信義威秀", "碩譽"),
    ("007", "台大", "遠通"),
    ("009", "松山車站", "微程式"),
    ("011", "西門紅樓", "碩譽"),
    ("014", "士林夜市", "遠通"),
]


def stub_m1_results() -> list[dict]:
    out = []
    for idx, (code, name, vendor) in enumerate(_VENUES):
        st = "diff" if idx % 3 == 0 else "matched"
        diff = -((idx + 1) * 41) if st == "diff" else 0
        out.append(
            {
                "venue_code": code,
                "venue_name": name,
                "vendor_code": vendor,
                "payment_type": None,
                "vendor_amount": str((idx + 1) * 12500),
                "expected_remit": str((idx + 1) * 12500),
                "actual_remit": str((idx + 1) * 12500 + diff),
                "diff_amount": str(diff),
                "status": st,
            }
        )
    return out


def stub_m2_results() -> list[dict]:
    out = []
    for idx, (code, name, _) in enumerate(_VENUES):
        st = "diff" if idx % 5 == 0 else "matched"
        diff = -((idx + 1) * 23) if st == "diff" else 0
        out.append(
            {
                "venue_code": code,
                "venue_name": name,
                "collector_name": "陳收費員" if idx % 2 == 0 else "李收費員",
                "cash_amount": str((idx + 1) * 8400),
                "bank_amount": str((idx + 1) * 8400 + diff),
                "diff_amount": str(diff),
                "status": st,
            }
        )
    return out


REASON_LABELS = {
    "rate_diff": "費率差（疑似 iPass 0% 混入）",
    "timing": "時間差（跨月撥款）",
    "note_unmatched": "銀行備註無法識別場站",
    "missing": "缺帳",
    "amount": "金額差異",
    "other": "其他",
}


async def ensure_stub_m3(db: Any) -> None:
    coll = db[M3_EXCEPTIONS]
    if await coll.find_one({}):
        return
    samples = [
        {
            "venue_code": "001", "venue_name": "北城停車場", "payment_type": "linepay",
            "diff_type": "rate_diff", "diff_amount": "-820", "note": None, "resolved": False,
        },
        {
            "venue_code": "003", "venue_name": "台北 101", "payment_type": "easycard",
            "diff_type": "timing", "diff_amount": "-136", "note": None, "resolved": False,
        },
        {
            "venue_code": "009", "venue_name": "松山車站", "payment_type": "cash",
            "diff_type": "note_unmatched", "diff_amount": "0", "note": None, "resolved": False,
        },
        {
            "venue_code": "014", "venue_name": "士林夜市", "payment_type": "linepay",
            "diff_type": "rate_diff", "diff_amount": "-720", "note": None, "resolved": False,
        },
    ]
    await coll.insert_many(samples)


def serialize_m3(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "venue_code": doc.get("venue_code"),
        "venue_name": doc.get("venue_name"),
        "payment_type": doc.get("payment_type"),
        "diff_type": doc.get("diff_type"),
        "diff_amount": doc.get("diff_amount"),
        "reason_label": REASON_LABELS.get(doc.get("diff_type") or "", doc.get("diff_type")),
        "note": doc.get("note"),
        "resolved": bool(doc.get("resolved")),
    }
