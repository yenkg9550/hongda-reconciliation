"""Demo 用：一次把指定月份的 17 個 slot 全部填成 'done'。

執行方式：
    cd backend
    python -m app.demo_fill              # 預設 2026-03
    python -m app.demo_fill 2026-04      # 指定月份

效果：
    - 在 MongoDB 的 upload_jobs collection 寫入 16~17 筆 done 紀錄（永豐個人保留 warning）
    - 不會塞真實檔案到 GridFS（純粹 metadata，給前端 demo）
    - 已存在的不會重覆塞

注意：這只是 demo 用，正式流程還是要真實上傳檔案。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta

from app.db.collections import UPLOAD_JOBS
from app.db.mongo import get_db
from app.services.slot_config import REQUIRED_SLOTS


def _month_range(period: str) -> tuple[date, date]:
    y, m = map(int, period.split("-"))
    start = date(y, m, 1)
    end_first = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end_first - timedelta(days=1)


async def fill(period: str = "2026-03") -> None:
    db = get_db()
    start, end = _month_range(period)
    print(f"→ 對 {period} 一鍵補齊（{start} ~ {end}）")

    inserted = 0
    skipped = 0
    now = datetime.utcnow()

    for slot in REQUIRED_SLOTS:
        # 檢查是否已存在該月份該 slot 的 job
        existing = await db[UPLOAD_JOBS].find_one(
            {
                "job_type": "upload",
                "source_type": slot["source_type"],
                "source_name": slot["source_name"],
                "period_start": start.isoformat(),
            }
        )
        if existing:
            skipped += 1
            continue

        job_id = str(uuid.uuid4())
        # 永豐個人留個 warning 訊息給前端展示
        message = "解析成功（demo）"
        if slot["source_name"] == "永豐銀行（個人）":
            message = "解析成功，但 3 筆交易備註無法自動識別場站"

        doc = {
            "_id": job_id,
            "job_id": job_id,
            "job_type": "upload",
            "source_type": slot["source_type"],
            "source_name": slot["source_name"],
            "filename": f"{slot['slot_key']}_{period.replace('-', '')}.xlsx",
            "checksum": f"demo-{job_id[:16]}",
            "status": "done",
            "progress": 100,
            "row_count": 100,
            "message": message,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "retry_count": 0,
            "error_msg": None,
            "created_at": now,
            "last_attempt_at": now,
            "finished_at": now,
        }

        # 碩譽需要 3 份才完整、阜爾需要 2 份 → 多塞幾筆
        await db[UPLOAD_JOBS].insert_one(doc)
        inserted += 1
        print(f"  ✓ {slot['slot_key']:30s} done")

        if slot["expected_file_count"] > 1:
            for sub in range(1, slot["expected_file_count"]):
                sub_id = str(uuid.uuid4())
                sub_doc = {
                    **doc,
                    "_id": sub_id,
                    "job_id": sub_id,
                    "filename": f"{slot['slot_key']}_part{sub + 1}_{period.replace('-', '')}.xlsx",
                    "checksum": f"demo-{sub_id[:16]}",
                }
                await db[UPLOAD_JOBS].insert_one(sub_doc)
                inserted += 1
                print(f"    + {slot['slot_key']} 子檔 {sub + 1}/{slot['expected_file_count']}")

    print(f"\n✓ 完成：新增 {inserted} 筆，跳過 {skipped} 筆（已存在）")


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "2026-03"
    asyncio.run(fill(period))
