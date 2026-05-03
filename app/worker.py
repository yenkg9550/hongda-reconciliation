"""背景 Worker（MongoDB + GridFS 骨架版）：

- 輪詢 upload_jobs WHERE status='queued' AND job_type='upload'
- 模擬 parsing：標 status=done、row_count 隨意填、把 GridFS metadata.bucket 設為 'done'
- 真正的 Parser 會在 Stage 2 接進來

執行方式：
    cd backend
    python -m app.worker
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime

from app.core.config import settings
from app.db.collections import UPLOAD_JOBS
from app.db.gridfs import update_bucket_label
from app.db.mongo import get_db

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def _process_one(job_id: str) -> None:
    db = get_db()
    doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    if not doc or doc.get("status") != "queued":
        return

    # 進入 processing
    await db[UPLOAD_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": "processing", "last_attempt_at": datetime.utcnow()}},
    )
    if doc.get("gridfs_id"):
        await update_bucket_label(doc["gridfs_id"], "processing")

    # 模擬處理時間
    await asyncio.sleep(random.uniform(0.4, 1.2))

    # 微程式 demo：第一次必失敗、之後成功
    force_fail = (doc.get("source_name") == "微程式") and (doc.get("retry_count") or 0) == 0
    if force_fail:
        err = "格式錯誤：欄位數不符（預期 9 欄，實際 6 欄）"
        await db[UPLOAD_JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "error_msg": err,
                "message": err,
                "finished_at": datetime.utcnow(),
            }},
        )
        if doc.get("gridfs_id"):
            await update_bucket_label(doc["gridfs_id"], "failed")
        logger.info("job %s → failed", job_id)
        return

    rows = random.randint(120, 5000)
    await db[UPLOAD_JOBS].update_one(
        {"_id": job_id},
        {"$set": {
            "status": "done",
            "progress": 100,
            "row_count": rows,
            "message": f"解析成功，共 {rows} 筆",
            "finished_at": datetime.utcnow(),
        }},
    )
    if doc.get("gridfs_id"):
        await update_bucket_label(doc["gridfs_id"], "done")
    logger.info("job %s → done (rows=%d)", job_id, rows)


async def main() -> None:
    logger.info("worker started, interval=%ds", settings.worker_interval_seconds)
    while True:
        try:
            db = get_db()
            cursor = db[UPLOAD_JOBS].find(
                {"status": "queued", "job_type": "upload"}, {"_id": 1}
            ).limit(20)
            ids = [d["_id"] async for d in cursor]
            for jid in ids:
                await _process_one(jid)
        except Exception:
            logger.exception("worker tick failed")
        await asyncio.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
