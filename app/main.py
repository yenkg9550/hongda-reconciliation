"""FastAPI 應用入口（MongoDB Atlas + GridFS 版本）。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.db.collections import ensure_indexes
from app.db.mongo import close as close_mongo
from app.db.mongo import get_db, ping
from app.routers import jobs, master, reconcile, reports, uploads
from app.schemas.common import error_envelope

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    try:
        await ensure_indexes(db)
    except Exception as exc:
        logger.warning("ensure_indexes failed: %s", exc)
    yield
    await close_mongo()


def create_app() -> FastAPI:
    app = FastAPI(
        title="宏達停車場對帳系統 API",
        version="0.4.0",
        description="MongoDB Atlas + GridFS，對應 docs/API文件.md v0.3.1",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(uploads.router, prefix=settings.api_v1_prefix, tags=["uploads"])
    app.include_router(jobs.router, prefix=settings.api_v1_prefix, tags=["jobs"])
    app.include_router(reconcile.router, prefix=settings.api_v1_prefix, tags=["reconcile"])
    app.include_router(master.router, prefix=settings.api_v1_prefix, tags=["master"])
    app.include_router(reports.router, prefix=settings.api_v1_prefix, tags=["reports"])

    @app.get("/", tags=["meta"], summary="Health check (lightweight, for Render port detection)")
    async def root():
        # 注意：這個 endpoint 不 await Mongo，避免 Render 健康檢查超時。
        # 要看 Mongo 連線狀態請打 /healthz。
        return {
            "name": "宏達停車場對帳系統",
            "version": "0.4.0",
            "docs": f"{settings.api_v1_prefix}/docs",
            "storage": "MongoDB GridFS",
        }

    @app.get("/healthz", tags=["meta"], summary="Deep health check (含 Mongo ping)")
    async def healthz():
        mongo_health = await ping()
        return {
            "name": "宏達停車場對帳系統",
            "version": "0.4.0",
            "mongodb": mongo_health,
            "storage": "MongoDB GridFS",
        }

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=error_envelope(
                    detail.get("code", "ERROR"),
                    detail.get("message", "錯誤"),
                    detail.get("detail"),
                ),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope("HTTP_ERROR", str(detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_envelope("VALIDATION_ERROR", "請求參數驗證失敗", exc.errors()),
        )

    return app


app = create_app()
