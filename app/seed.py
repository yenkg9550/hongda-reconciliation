"""種子資料：基本場站、費率（MongoDB 版）。

執行方式：
    cd backend
    python -m app.seed
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from app.db.collections import FEE_RATES, VENUES
from app.db.mongo import get_db

logger = logging.getLogger("seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


VENUES_DATA = [
    ("001", "北城停車場", "遠通"),
    ("002", "南港車站", "遠通"),
    ("003", "台北 101", "微程式"),
    ("005", "信義威秀", "碩譽"),
    ("007", "台大", "遠通"),
    ("009", "松山車站", "微程式"),
    ("011", "西門紅樓", "碩譽"),
    ("014", "士林夜市", "遠通"),
    ("018", "南港展覽館", "微程式"),
    ("022", "內湖科學園區", "碩譽"),
    ("025", "汐止 IFG", "遠通"),
    ("030", "新店秀朗橋", "微程式"),
]

PAYMENTS = ["linepay", "easycard", "easywallet", "credit_card"]

RATES = [
    ("linepay", "0.0200"),
    ("easycard", "0.0150"),
    ("easywallet", "0.0150"),
    ("ipass_money", "0.0000"),
    ("credit_card", "0.0250"),
]


async def seed() -> None:
    db = get_db()

    # 場站
    for code, name, vendor in VENUES_DATA:
        existing = await db[VENUES].find_one({"_id": code})
        if existing:
            continue
        payments = [{"payment_type": pt, "merchant_id": f"{code}-{pt}"} for pt in PAYMENTS]
        await db[VENUES].insert_one(
            {
                "_id": code,
                "venue_code": code,
                "venue_name": name,
                "vendor_code": vendor,
                "is_active": True,
                "payments": payments,
            }
        )

    # 費率
    for pt, rate in RATES:
        existing = await db[FEE_RATES].find_one({"payment_type": pt})
        if existing:
            continue
        await db[FEE_RATES].insert_one({"payment_type": pt, "rate": rate})

    logger.info("seed completed")


if __name__ == "__main__":
    asyncio.run(seed())
