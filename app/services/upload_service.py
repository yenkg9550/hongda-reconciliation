"""上傳服務（MongoDB + GridFS）。

接收檔案 → 計算 SHA-256 → 查重 → 寫入 GridFS → 在 upload_jobs 建立紀錄。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from app.db.collections import UPLOAD_JOBS
from app.db.gridfs import compute_sha256, put_pending


async def receive_upload(
    db: Any,
    *,
    source_type: str,
    source_name: str,
    period_start: date,
    period_end: date,
    filename: str,
    file_bytes: bytes,
) -> tuple[dict | None, dict | None]:
    """接收一份檔案。

    回傳 (accepted_doc, rejected_dict)，恰好一個為 None。
    accepted_doc 是寫入 MongoDB 的 upload_jobs document。
    """
    checksum = compute_sha256(file_bytes)

    # 查重：相同 checksum 已 done → 拒絕
    existing = await db[UPLOAD_JOBS].find_one(
        {"checksum": checksum, "status": "done"}
    )
    if existing:
        return None, {
            "filename": filename,
            "reason": "DUPLICATE_FILE",
            "message": "已成功匯入過，若要重跑請先至作業記錄確認",
            "existing_job_id": existing.get("job_id"),
        }

    job_id = str(uuid.uuid4())
    gridfs_id = await put_pending(file_bytes, job_id, filename)

    now = datetime.utcnow()
    doc = {
        "_id": job_id,         # 用 UUID 字串作 _id，方便 by-id 查
        "job_id": job_id,
        "job_type": "upload",
        "source_type": source_type,
        "source_name": source_name,
        "filename": filename,
        "gridfs_id": str(gridfs_id),
        "checksum": checksum,
        "status": "queued",
        "progress": 0,
        "message": "已接收，待背景 worker 處理",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "row_count": None,
        "retry_count": 0,
        "retry_of_job_id": None,
        "error_msg": None,
        "created_at": now,
        "last_attempt_at": None,
        "finished_at": None,
    }
    await db[UPLOAD_JOBS].insert_one(doc)
    return doc, None
