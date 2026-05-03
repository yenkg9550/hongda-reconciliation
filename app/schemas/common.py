"""通用 envelope schema — { success, data } / { success, error }."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorObj(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorObj | None = None


class Pagination(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20


class PagedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    pagination: Pagination


# 工具函式：直接產生 dict（給 exception handler）
def success_envelope(data: Any = None) -> dict:
    return {"success": True, "data": data}


def error_envelope(code: str, message: str, detail: Any | None = None) -> dict:
    return {"success": False, "error": {"code": code, "message": message, "detail": detail}}


def paged_envelope(items: list[Any], total: int, page: int = 1, page_size: int = 20) -> dict:
    return {
        "success": True,
        "data": items,
        "pagination": {"total": total, "page": page, "page_size": page_size},
    }
