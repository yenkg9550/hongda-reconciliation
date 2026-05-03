"""Demo 用：清空已上傳的資料（保留 venues / fee_rates 主檔）。

執行方式：
    cd backend
    source .venv/bin/activate

    python -m app.demo_clear                  # 清 2026-03 的 upload + 對應 GridFS 檔案
    python -m app.demo_clear 2026-04          # 清指定月份
    python -m app.demo_clear --all            # 清所有月份的所有 upload/reconcile job + GridFS + M3 例外
    python -m app.demo_clear --all --yes      # 不要確認，直接刪

保留：
    - venues、fee_rates（主檔）
    - GridFS 內容（除非 --all）
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

from bson import ObjectId

from app.db.collections import GRIDFS_PREFIX, M3_EXCEPTIONS, UPLOAD_JOBS
from app.db.mongo import get_db


def _month_range(period: str) -> tuple[date, date]:
    y, m = map(int, period.split("-"))
    start = date(y, m, 1)
    end_first = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end_first - timedelta(days=1)


async def _delete_gridfs(db, file_ids: list[str]) -> int:
    """刪除 GridFS 上的檔案（含 chunks）。回傳實際刪除筆數。"""
    if not file_ids:
        return 0
    files_coll = db[f"{GRIDFS_PREFIX}.files"]
    chunks_coll = db[f"{GRIDFS_PREFIX}.chunks"]
    deleted = 0
    for fid in file_ids:
        try:
            oid = ObjectId(fid) if isinstance(fid, str) else fid
        except Exception:
            continue
        await chunks_coll.delete_many({"files_id": oid})
        r = await files_coll.delete_one({"_id": oid})
        if r.deleted_count:
            deleted += 1
    return deleted


async def clear_period(period: str) -> None:
    db = get_db()
    start, end = _month_range(period)
    print(f"→ 清除 {period}（{start} ~ {end}）的上傳紀錄與檔案")

    # 找出該月份的所有 upload job
    cursor = db[UPLOAD_JOBS].find(
        {
            "job_type": "upload",
            "period_start": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }
    )
    jobs = await cursor.to_list(length=10_000)
    print(f"  找到 {len(jobs)} 筆 upload_jobs")

    # 收集 gridfs_id 然後刪 GridFS
    gridfs_ids = [j["gridfs_id"] for j in jobs if j.get("gridfs_id")]
    deleted_files = await _delete_gridfs(db, gridfs_ids)
    print(f"  從 GridFS 刪除 {deleted_files} 個檔案")

    # 刪 upload_jobs
    job_ids = [j["_id"] for j in jobs]
    if job_ids:
        r = await db[UPLOAD_JOBS].delete_many({"_id": {"$in": job_ids}})
        print(f"  從 upload_jobs 刪除 {r.deleted_count} 筆")

    print("✓ 完成")


async def clear_all() -> None:
    db = get_db()
    print("→ 清除所有 upload + reconcile job、GridFS 全部檔案、M3 例外")

    # 1. 列出所有 GridFS 檔案，全部刪
    files_coll = db[f"{GRIDFS_PREFIX}.files"]
    chunks_coll = db[f"{GRIDFS_PREFIX}.chunks"]
    files_count = await files_coll.count_documents({})
    chunks_count = await chunks_coll.count_documents({})
    await chunks_coll.delete_many({})
    await files_coll.delete_many({})
    print(f"  GridFS：刪除 {files_count} 個 files、{chunks_count} 個 chunks")

    # 2. 清 upload_jobs（含 reconcile_m1/m2/m3）
    r = await db[UPLOAD_JOBS].delete_many({})
    print(f"  upload_jobs：刪除 {r.deleted_count} 筆")

    # 3. 清 M3 例外
    r = await db[M3_EXCEPTIONS].delete_many({})
    print(f"  m3_exceptions：刪除 {r.deleted_count} 筆")

    print("✓ 完成（venues 與 fee_rates 保留）")


async def main():
    args = sys.argv[1:]
    is_all = "--all" in args
    auto_yes = "--yes" in args
    period_args = [a for a in args if not a.startswith("--")]

    if is_all:
        if not auto_yes:
            ans = input("⚠️  確定要清空所有 upload/reconcile/GridFS/M3 例外嗎？(輸入 yes 確認): ").strip()
            if ans.lower() != "yes":
                print("取消")
                return
        await clear_all()
    else:
        period = period_args[0] if period_args else "2026-03"
        await clear_period(period)


if __name__ == "__main__":
    asyncio.run(main())
