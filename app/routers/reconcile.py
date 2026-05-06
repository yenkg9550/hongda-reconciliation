"""POST/GET /reconcile/m1|m2|m3, PATCH /reconcile/m3/{id}  (Mongo)"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Body, HTTPException, Path, Query

from app.db.collections import M3_EXCEPTIONS
from app.db.mongo import get_db
from app.schemas.common import success_envelope
from app.schemas.reconcile import M3ResolveRequest, ReconcileTriggerRequest
from app.services.reconcile_service import (
    get_m1_results,
    get_m2_results,
    serialize_m3,
    trigger_reconcile,
)

router = APIRouter()


def _to_objectid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except InvalidId:
        raise HTTPException(
            400, detail={"code": "INVALID_ID", "message": f"無效的 ObjectId: {s}"}
        )


# ── M1 ──────────────────────────────────────────────
@router.post("/reconcile/m1", summary="觸發 M1 電子支付對帳")
async def trigger_m1(req: ReconcileTriggerRequest):
    db = get_db()
    job = await trigger_reconcile(db, module="m1", period_start=req.period_start, period_end=req.period_end)
    return success_envelope(
        {"job_id": job["job_id"], "job_type": "reconcile_m1", "status": job["status"], "message": job["message"]}
    )


@router.get("/reconcile/m1", summary="查詢 M1 對帳結果")
async def get_m1(
    period_start: date = Query(...),
    period_end: date = Query(...),
    venue_code: str | None = Query(None),
):
    db = get_db()
    items = await get_m1_results(
        db, period_start=period_start, period_end=period_end, venue_code=venue_code
    )
    return success_envelope(items)


# ── M2 ──────────────────────────────────────────────
@router.post("/reconcile/m2", summary="觸發 M2 現金對帳")
async def trigger_m2(req: ReconcileTriggerRequest):
    db = get_db()
    job = await trigger_reconcile(db, module="m2", period_start=req.period_start, period_end=req.period_end)
    return success_envelope(
        {"job_id": job["job_id"], "job_type": "reconcile_m2", "status": job["status"], "message": job["message"]}
    )


@router.get("/reconcile/m2", summary="查詢 M2 對帳結果")
async def get_m2(
    period_start: date = Query(...),
    period_end: date = Query(...),
    venue_code: str | None = Query(None),
):
    db = get_db()
    items = await get_m2_results(
        db, period_start=period_start, period_end=period_end, venue_code=venue_code
    )
    return success_envelope(items)


# ── M3 ──────────────────────────────────────────────
@router.post("/reconcile/m3", summary="觸發 M3 例外調查")
async def trigger_m3(req: ReconcileTriggerRequest):
    db = get_db()
    job = await trigger_reconcile(db, module="m3", period_start=req.period_start, period_end=req.period_end)
    return success_envelope(
        {"job_id": job["job_id"], "job_type": "reconcile_m3", "status": job["status"], "message": job["message"]}
    )


@router.get("/reconcile/m3", summary="查詢 M3 例外清單")
async def get_m3(
    period_start: date | None = Query(None),
    period_end: date | None = Query(None),
    venue_code: str | None = Query(None),
    resolved: bool | None = Query(None),
):
    db = get_db()
    query: dict = {}
    if period_start and period_end:
        query["period_start"] = period_start.isoformat()
        query["period_end"] = period_end.isoformat()
    if venue_code:
        query["venue_code"] = venue_code
    if resolved is not None:
        query["resolved"] = resolved
    cursor = db[M3_EXCEPTIONS].find(query).sort("_id", 1)
    rows = await cursor.to_list(length=10_000)
    return success_envelope([serialize_m3(r) for r in rows])


@router.get("/reconcile/m3/{exception_id}", summary="查詢單筆例外明細")
async def get_m3_detail(exception_id: Annotated[str, Path(...)]):
    db = get_db()
    oid = _to_objectid(exception_id)
    r = await db[M3_EXCEPTIONS].find_one({"_id": oid})
    if not r:
        raise HTTPException(404, detail={"code": "EXCEPTION_NOT_FOUND", "message": "找不到例外項目"})
    return success_envelope(serialize_m3(r))


@router.patch("/reconcile/m3/{exception_id}", summary="標記例外為已處理")
async def resolve_m3(
    exception_id: Annotated[str, Path(...)],
    body: M3ResolveRequest = Body(...),
):
    db = get_db()
    oid = _to_objectid(exception_id)
    update: dict = {"$set": {"resolved": body.resolved}}
    if body.note is not None:
        update["$set"]["note"] = body.note
    result = await db[M3_EXCEPTIONS].update_one({"_id": oid}, update)
    if result.matched_count == 0:
        raise HTTPException(404, detail={"code": "EXCEPTION_NOT_FOUND", "message": "找不到例外項目"})
    refreshed = await db[M3_EXCEPTIONS].find_one({"_id": oid})
    return success_envelope(serialize_m3(refreshed))
