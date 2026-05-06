"""種子資料：正式 master（venues / venue_mappings / fee_rates）。

資料來源是 backend_20260506 的 SQLite，匯出後存在 app/master_data.json。
這支腳本把 JSON load 進原本 backend 的 MongoDB（依 _id upsert）。

執行方式：
    cd backend
    python -m app.seed
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.db.collections import FEE_RATES, VENUE_MAPPINGS, VENUES, ensure_indexes
from app.db.mongo import get_db

logger = logging.getLogger("seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


MASTER_DATA_PATH = Path(__file__).resolve().parent / "master_data.json"


def _load_master() -> dict:
    if not MASTER_DATA_PATH.is_file():
        raise FileNotFoundError(
            f"找不到 master_data.json：{MASTER_DATA_PATH}。"
            "請先從 backend_20260506/hongda_parking.db 匯出 master 資料。"
        )
    with MASTER_DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


async def seed_venues(db, venues: list[dict]) -> int:
    """venues：以 venue_code 作 _id；保留真實的 venue_name / vendor_code / manager。"""
    n = 0
    for v in venues:
        venue_code = v["venue_code"]
        doc = {
            "_id": venue_code,
            "venue_code": venue_code,
            "venue_name": v.get("venue_name"),
            "vendor_code": v.get("vendor_code"),
            "manager": v.get("manager"),
            "is_active": bool(v.get("is_active", 1)),
        }
        await db[VENUES].update_one({"_id": venue_code}, {"$set": doc}, upsert=True)
        n += 1
    return n


async def seed_venue_mappings(db, mappings: list[dict]) -> int:
    """venue_mappings：用 (source, source_name) 當唯一 key，clear-and-insert 比較單純。"""
    await db[VENUE_MAPPINGS].delete_many({})
    if not mappings:
        return 0
    docs = [
        {
            "source": m["source"],
            "source_name": m["source_name"],
            "venue_code": m["venue_code"],
            "venue_name": m.get("venue_name"),
            "is_active": bool(m.get("is_active", 1)),
        }
        for m in mappings
    ]
    await db[VENUE_MAPPINGS].insert_many(docs)
    return len(docs)


async def seed_rates(db, rates: list[dict]) -> int:
    """fee_rates：用 (vendor_code, payment_type, effective_date) 當複合 key。"""
    await db[FEE_RATES].delete_many({})
    if not rates:
        return 0
    docs = [
        {
            "vendor_code": r.get("vendor_code"),
            "payment_type": r["payment_type"],
            "rate": float(r["rate"]),
            "effective_date": r.get("effective_date"),
        }
        for r in rates
    ]
    await db[FEE_RATES].insert_many(docs)
    return len(docs)


async def seed() -> None:
    db = get_db()
    await ensure_indexes(db)

    data = _load_master()
    n_v = await seed_venues(db, data.get("venues", []))
    n_m = await seed_venue_mappings(db, data.get("venue_mappings", []))
    n_r = await seed_rates(db, data.get("rates", []))
    logger.info("seed done: venues=%d venue_mappings=%d fee_rates=%d", n_v, n_m, n_r)


if __name__ == "__main__":
    asyncio.run(seed())
