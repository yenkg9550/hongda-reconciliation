"""MongoDB 連線層（motor / async）。

支援 in-memory fallback：當 USE_INMEMORY_FALLBACK=true 或匯入 motor 失敗時，
會改用 mongomock-motor，方便沒有真實 Atlas 也能驗證程式邏輯。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


_client: Any = None
_db: Any = None


def _build_client() -> tuple[Any, Any]:
    """建立 motor client；連不上時依設定 fallback 到 mongomock。"""
    if settings.use_inmemory_fallback:
        try:
            from mongomock_motor import AsyncMongoMockClient

            client = AsyncMongoMockClient()
            logger.warning("using mongomock-motor (in-memory) — for dev/test only")
            return client, client[settings.mongodb_db]
        except ImportError:
            logger.error("USE_INMEMORY_FALLBACK=true 但 mongomock-motor 未安裝")

    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(settings.mongodb_uri, uuidRepresentation="standard")
        return client, client[settings.mongodb_db]
    except Exception as exc:
        logger.exception("connect to MongoDB failed: %s", exc)
        # 最後一道防線：改用 mongomock
        try:
            from mongomock_motor import AsyncMongoMockClient

            client = AsyncMongoMockClient()
            logger.warning("falling back to mongomock-motor")
            return client, client[settings.mongodb_db]
        except ImportError:
            raise


def get_client() -> Any:
    global _client, _db
    if _client is None:
        _client, _db = _build_client()
    return _client


def get_db() -> Any:
    global _client, _db
    if _db is None:
        _client, _db = _build_client()
    return _db


async def close() -> None:
    global _client, _db
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _db = None


async def ping() -> dict:
    """Health check — 回傳 server info 或錯誤。"""
    db = get_db()
    try:
        info = await db.command("ping")
        return {"ok": True, "result": info}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
