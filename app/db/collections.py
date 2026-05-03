"""MongoDB collection 名稱與索引規格。

對應原 SQL schema（系統架構文件第六章）：
  venues / venue_payments / fee_rates / upload_jobs
  vendor_transactions / payment_transactions / bank_entries / cash_records
  m1_results / m1_result_bank_entries / m2_results / m3_exceptions

文件結構保留 SQL 時的欄位命名，便於前後端對齊。
唯一比較大的差異：
  - venue_payments 改放進 venues.payments 子陣列
  - upload_jobs 的 job_id 用 UUID 字串作 _id
  - 其他 collection 用 ObjectId 作 _id，原 SQL 的 id 欄位不出現
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


# Collection 名稱
VENUES = "venues"
FEE_RATES = "fee_rates"
UPLOAD_JOBS = "upload_jobs"
VENDOR_TX = "vendor_transactions"
PAYMENT_TX = "payment_transactions"
BANK_ENTRIES = "bank_entries"
CASH_RECORDS = "cash_records"
M1_RESULTS = "m1_results"
M2_RESULTS = "m2_results"
M3_EXCEPTIONS = "m3_exceptions"

# GridFS bucket prefix（會用到 {prefix}.files / {prefix}.chunks 兩個系統 collection）
GRIDFS_PREFIX = "uploads"


# 索引規格：(collection, [(keys, options)])
INDEX_SPECS: dict[str, list[tuple[Any, dict]]] = {
    UPLOAD_JOBS: [
        ([("checksum", ASCENDING)], {"name": "ix_checksum"}),
        ([("status", ASCENDING)], {"name": "ix_status"}),
        ([("job_type", ASCENDING)], {"name": "ix_job_type"}),
        (
            [("source_type", ASCENDING), ("source_name", ASCENDING), ("period_start", ASCENDING)],
            {"name": "ix_slot_period"},
        ),
        ([("created_at", DESCENDING)], {"name": "ix_created_at"}),
    ],
    VENDOR_TX: [
        ([("job_id", ASCENDING)], {"name": "ix_job_id"}),
        ([("venue_code", ASCENDING), ("transaction_date", ASCENDING)], {"name": "ix_venue_date"}),
    ],
    PAYMENT_TX: [
        ([("job_id", ASCENDING)], {"name": "ix_job_id"}),
        ([("payment_type", ASCENDING), ("transaction_date", ASCENDING)], {"name": "ix_pay_date"}),
    ],
    BANK_ENTRIES: [
        ([("job_id", ASCENDING)], {"name": "ix_job_id"}),
        ([("account_id", ASCENDING), ("value_date", ASCENDING)], {"name": "ix_account_date"}),
        ([("venue_code", ASCENDING)], {"name": "ix_venue"}),
    ],
    CASH_RECORDS: [
        ([("job_id", ASCENDING)], {"name": "ix_job_id"}),
        ([("venue_code", ASCENDING), ("collector_name", ASCENDING)], {"name": "ix_venue_collector"}),
    ],
    M1_RESULTS: [
        (
            [("period_start", ASCENDING), ("period_end", ASCENDING), ("venue_code", ASCENDING)],
            {"name": "ix_period_venue"},
        ),
    ],
    M2_RESULTS: [
        (
            [("period_start", ASCENDING), ("period_end", ASCENDING), ("venue_code", ASCENDING)],
            {"name": "ix_period_venue"},
        ),
    ],
    M3_EXCEPTIONS: [
        ([("resolved", ASCENDING)], {"name": "ix_resolved"}),
        ([("venue_code", ASCENDING)], {"name": "ix_venue"}),
    ],
    FEE_RATES: [
        ([("payment_type", ASCENDING)], {"name": "ix_payment_type"}),
    ],
}


async def ensure_indexes(db: Any) -> None:
    """在啟動時呼叫一次，確保索引就緒（已存在則 no-op）。"""
    for coll_name, specs in INDEX_SPECS.items():
        coll = db[coll_name]
        for keys, opts in specs:
            try:
                await coll.create_index(keys, **opts)
            except Exception as exc:
                logger.warning("create_index(%s, %s) failed: %s", coll_name, keys, exc)
