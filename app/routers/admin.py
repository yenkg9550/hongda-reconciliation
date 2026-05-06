"""管理用 API：重置資料庫等流程操作。

- POST /admin/reset：清空交易、上傳、對帳結果與 GridFS 檔案，
  但保留 master 資料（venues、fee_rates）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.db.collections import (
    BANK_ENTRIES,
    CASH_RECORDS,
    GRIDFS_PREFIX,
    M1_DETAILS,
    M1_RESULTS,
    M2_RESULTS,
    M3_EXCEPTIONS,
    PAYMENT_TX,
    UPLOAD_JOBS,
    VENDOR_TX,
)
from app.db.mongo import get_db
from app.schemas.common import success_envelope

logger = logging.getLogger(__name__)

router = APIRouter()


# 會被清空的 collection（保留 venues、fee_rates 兩個 master 表）
RESETTABLE_COLLECTIONS = [
    UPLOAD_JOBS,
    VENDOR_TX,
    PAYMENT_TX,
    BANK_ENTRIES,
    CASH_RECORDS,
    M1_RESULTS,
    M1_DETAILS,
    M2_RESULTS,
    M3_EXCEPTIONS,
]

# GridFS 用的兩個系統 collection
GRIDFS_COLLECTIONS = [f"{GRIDFS_PREFIX}.files", f"{GRIDFS_PREFIX}.chunks"]


@router.post("/admin/reset", summary="重置流程資料（保留 venues / fee_rates master 資料）")
async def reset_data():
    db = get_db()
    cleared: dict[str, int] = {}

    for coll_name in RESETTABLE_COLLECTIONS:
        result = await db[coll_name].delete_many({})
        cleared[coll_name] = result.deleted_count

    # GridFS：直接清掉兩個 collection 比一個個 delete bucket file 快
    for coll_name in GRIDFS_COLLECTIONS:
        try:
            result = await db[coll_name].delete_many({})
            cleared[coll_name] = result.deleted_count
        except Exception as exc:
            # collection 可能根本不存在，忽略
            logger.info("skip clear %s: %s", coll_name, exc)
            cleared[coll_name] = 0

    return success_envelope({"cleared": cleared, "preserved": ["venues", "fee_rates"]})
