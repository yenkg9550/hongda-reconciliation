"""組裝 GET /upload-status 回應（MongoDB 版）。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.db.collections import UPLOAD_JOBS
from app.services.slot_config import REQUIRED_SLOTS, SlotDef


def _month_range(period: str) -> tuple[date, date]:
    year, month = period.split("-")
    y, m = int(year), int(month)
    start = date(y, m, 1)
    if m == 12:
        end_first = date(y + 1, 1, 1)
    else:
        end_first = date(y, m + 1, 1)
    end = end_first - timedelta(days=1)
    return start, end


def _slot_status(slot: SlotDef, jobs: list[dict]) -> dict[str, Any]:
    completed = [j for j in jobs if j["status"] == "done"]
    failed = [j for j in jobs if j["status"] == "failed"]
    processing = [j for j in jobs if j["status"] in ("queued", "processing")]

    expected = slot["expected_file_count"]

    if failed and not completed:
        status = "error"
        message = failed[-1].get("error_msg") or failed[-1].get("message") or "解析失敗"
    elif len(completed) == 0 and not processing and not failed:
        status = "missing"
        message = "尚未上傳"
    elif len(completed) < expected:
        status = "warning"
        message = f"已上傳 {len(completed)} 份，尚缺 {expected - len(completed)} 份"
    else:
        status = "done"
        message = completed[-1].get("message") or "解析成功"

    uploaded_jobs = [
        {
            "job_id": j["job_id"],
            "filename": j.get("filename", ""),
            "status": j["status"],
            "uploaded_at": j["created_at"].isoformat() if hasattr(j["created_at"], "isoformat") else j["created_at"],
            "message": j.get("message"),
        }
        for j in jobs
    ]
    missing_subfiles: list[str] = []
    if status == "warning" and slot["expected_file_count"] > 1:
        missing_subfiles = [f"預期共 {expected} 份，目前 {len(completed)} 份"]

    return {
        "slot_key": slot["slot_key"],
        "source_type": slot["source_type"],
        "source_name": slot["source_name"],
        "is_required": slot["is_required"],
        "status": status,
        "message": message,
        "expected_file_count": expected,
        "uploaded_file_count": len(completed),
        "missing_subfiles": missing_subfiles,
        "uploaded_jobs": uploaded_jobs,
    }


async def build_upload_status(db: Any, period: str) -> dict[str, Any]:
    start, end = _month_range(period)

    cursor = db[UPLOAD_JOBS].find(
        {
            "job_type": "upload",
            "period_start": {"$gte": start.isoformat()},
            "period_end": {"$lte": end.isoformat()},
        }
    ).sort("created_at", 1)
    jobs = await cursor.to_list(length=10_000)

    items: list[dict[str, Any]] = []
    completed_count = 0
    warning_count = 0
    error_count = 0
    missing_count = 0
    required_total = 0

    for slot in REQUIRED_SLOTS:
        slot_jobs = [
            j
            for j in jobs
            if j.get("source_type") == slot["source_type"]
            and j.get("source_name") == slot["source_name"]
        ]
        item = _slot_status(slot, slot_jobs)
        items.append(item)
        if slot["is_required"]:
            required_total += 1
            if item["status"] == "done":
                completed_count += 1
            elif item["status"] == "warning":
                warning_count += 1
                completed_count += 1
            elif item["status"] == "error":
                error_count += 1
            elif item["status"] == "missing":
                missing_count += 1

    can_submit = error_count == 0 and missing_count == 0

    return {
        "period": period,
        "total_required": required_total,
        "completed_count": completed_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "missing_count": missing_count,
        "can_submit_reconcile": can_submit,
        "items": items,
    }
