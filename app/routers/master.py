"""主檔 CRUD：venues / rates / mappings (MongoDB)"""

from __future__ import annotations

from typing import Annotated

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Body, HTTPException, Path, Query

from app.db.collections import FEE_RATES, VENUES
from app.db.mongo import get_db
from app.schemas.common import paged_envelope, success_envelope
from app.schemas.master import FeeRateUpdateRequest, VenueCreateRequest, VenueUpdateRequest

router = APIRouter()


def _serialize_venue(doc: dict) -> dict:
    payments = doc.get("payments") or []
    return {
        "venue_code": doc.get("venue_code"),
        "venue_name": doc.get("venue_name"),
        "vendor_code": doc.get("vendor_code"),
        "manager": doc.get("manager"),
        "tax_id": doc.get("tax_id"),
        "is_active": doc.get("is_active", True),
        "payments": [
            {
                "id": str(p.get("_id") or p.get("id") or i),
                "payment_type": p.get("payment_type"),
                "merchant_id": p.get("merchant_id"),
            }
            for i, p in enumerate(payments)
        ],
    }


def _serialize_rate(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "payment_type": doc.get("payment_type"),
        "rate": str(doc.get("rate")),
        "effective_from": doc.get("effective_from"),
        "effective_to": doc.get("effective_to"),
    }


# ── /venues ────────────────────────────────────────────
@router.get("/venues", summary="取得場站清單")
async def list_venues(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: bool | None = Query(None),
):
    db = get_db()
    query: dict = {}
    if is_active is not None:
        query["is_active"] = is_active
    coll = db[VENUES]
    total = await coll.count_documents(query)
    cursor = coll.find(query).sort("venue_code", 1).skip((page - 1) * page_size).limit(page_size)
    rows = await cursor.to_list(length=page_size)
    return paged_envelope(
        [_serialize_venue(v) for v in rows], total=total, page=page, page_size=page_size
    )


@router.post("/venues", summary="新增場站")
async def create_venue(req: VenueCreateRequest):
    db = get_db()
    if await db[VENUES].find_one({"_id": req.venue_code}):
        raise HTTPException(
            409, detail={"code": "VENUE_DUPLICATE", "message": f"場站 {req.venue_code} 已存在"}
        )
    doc = req.model_dump()
    doc["_id"] = req.venue_code
    doc.setdefault("payments", [])
    await db[VENUES].insert_one(doc)
    return success_envelope(_serialize_venue(doc))


@router.put("/venues/{venue_code}", summary="更新場站")
async def update_venue(venue_code: Annotated[str, Path(...)], req: VenueUpdateRequest):
    db = get_db()
    update_dict = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    if not update_dict:
        raise HTTPException(
            400, detail={"code": "EMPTY_UPDATE", "message": "沒有要更新的欄位"}
        )
    result = await db[VENUES].update_one({"_id": venue_code}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(
            404, detail={"code": "VENUE_NOT_FOUND", "message": f"找不到場站 {venue_code}"}
        )
    refreshed = await db[VENUES].find_one({"_id": venue_code})
    return success_envelope(_serialize_venue(refreshed))


# ── /rates ────────────────────────────────────────────
@router.get("/rates", summary="取得費率清單")
async def list_rates():
    db = get_db()
    cursor = db[FEE_RATES].find({}).sort("payment_type", 1)
    rows = await cursor.to_list(length=1000)
    return success_envelope([_serialize_rate(r) for r in rows])


@router.put("/rates/{rate_id}", summary="更新費率")
async def update_rate(rate_id: Annotated[str, Path(...)], body: FeeRateUpdateRequest = Body(...)):
    db = get_db()
    try:
        oid = ObjectId(rate_id)
    except InvalidId:
        raise HTTPException(
            400, detail={"code": "INVALID_ID", "message": "rate_id 必須是 ObjectId"}
        )
    update_dict = {k: (str(v) if k == "rate" and v is not None else (v.isoformat() if hasattr(v, "isoformat") else v))
                   for k, v in body.model_dump(exclude_unset=True).items()}
    if not update_dict:
        raise HTTPException(400, detail={"code": "EMPTY_UPDATE", "message": "沒有要更新的欄位"})
    result = await db[FEE_RATES].update_one({"_id": oid}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(404, detail={"code": "RATE_NOT_FOUND", "message": "找不到費率"})
    refreshed = await db[FEE_RATES].find_one({"_id": oid})
    return success_envelope(_serialize_rate(refreshed))


# ── /mappings (venues.payments 子陣列) ──────────────────
@router.get("/mappings", summary="取得場站對照表（venue.payments 平鋪）")
async def list_mappings():
    db = get_db()
    cursor = db[VENUES].find({}).sort("venue_code", 1)
    rows = await cursor.to_list(length=10_000)
    items = []
    for v in rows:
        for i, p in enumerate(v.get("payments") or []):
            items.append(
                {
                    "id": f"{v['_id']}::{i}",
                    "venue_code": v.get("venue_code"),
                    "payment_type": p.get("payment_type"),
                    "merchant_id": p.get("merchant_id"),
                }
            )
    return success_envelope(items)


@router.put("/mappings/{mapping_id}", summary="更新對照表（id 格式 venue_code::index）")
async def update_mapping(mapping_id: Annotated[str, Path(...)], body: dict = Body(...)):
    db = get_db()
    try:
        venue_code, idx_str = mapping_id.split("::", 1)
        idx = int(idx_str)
    except (ValueError, AttributeError):
        raise HTTPException(400, detail={"code": "INVALID_ID", "message": "mapping_id 格式應為 venue_code::index"})

    venue = await db[VENUES].find_one({"_id": venue_code})
    if not venue or idx >= len(venue.get("payments") or []):
        raise HTTPException(404, detail={"code": "MAPPING_NOT_FOUND", "message": "找不到對照"})

    update: dict = {}
    if "merchant_id" in body:
        update[f"payments.{idx}.merchant_id"] = body["merchant_id"]
    if "payment_type" in body:
        update[f"payments.{idx}.payment_type"] = body["payment_type"]
    if not update:
        raise HTTPException(400, detail={"code": "EMPTY_UPDATE", "message": "沒有要更新的欄位"})

    await db[VENUES].update_one({"_id": venue_code}, {"$set": update})
    refreshed = await db[VENUES].find_one({"_id": venue_code})
    p = refreshed["payments"][idx]
    return success_envelope(
        {
            "id": mapping_id,
            "venue_code": venue_code,
            "payment_type": p.get("payment_type"),
            "merchant_id": p.get("merchant_id"),
        }
    )
