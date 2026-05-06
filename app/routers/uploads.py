"""POST /uploads, DELETE /uploads/{job_id}, GET /upload-status (MongoDB + GridFS)"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Path as FPath, UploadFile

from app.db.collections import UPLOAD_JOBS
from app.db.gridfs import delete_object
from app.db.mongo import get_db
from app.schemas.common import success_envelope
from app.services.upload_service import receive_upload
from app.services.upload_status_service import build_upload_status

router = APIRouter()


@router.post("/uploads", summary="上傳報表檔案（多檔，存到 GridFS）")
async def upload_files(
    source_type: Annotated[
        Literal[
            "vendor",
            "payment",
            "bank",
            "cash",
            "vendor_yongxi",
            "vendor_fuer",
        ],
        Form(),
    ],
    source_name: Annotated[str, Form()],
    period_start: Annotated[date, Form()],
    period_end: Annotated[date, Form()],
    files: Annotated[list[UploadFile], File(description="一或多個檔案")],
):
    db = get_db()
    accepted = []
    rejected = []
    for f in files:
        content = await f.read()
        accepted_doc, reject = await receive_upload(
            db,
            source_type=source_type,
            source_name=source_name,
            period_start=period_start,
            period_end=period_end,
            filename=f.filename or "unnamed",
            file_bytes=content,
        )
        if reject:
            rejected.append(reject)
        elif accepted_doc:
            accepted.append(
                {
                    "job_id": accepted_doc["job_id"],
                    "filename": accepted_doc["filename"],
                    "status": accepted_doc["status"],
                    "message": accepted_doc.get("message"),
                    "row_count": accepted_doc.get("row_count"),
                    "gridfs_id": accepted_doc["gridfs_id"],
                }
            )
    return success_envelope({"accepted": accepted, "rejected": rejected})


@router.delete("/uploads/{job_id}", summary="移除單一已上傳檔案")
async def delete_upload(job_id: Annotated[str, FPath(...)]):
    db = get_db()
    doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    if not doc:
        raise HTTPException(
            404, detail={"code": "JOB_NOT_FOUND", "message": f"找不到 job {job_id}"}
        )
    if doc.get("status") == "processing":
        raise HTTPException(
            409, detail={"code": "JOB_PROCESSING", "message": "處理中的 job 不可刪除"}
        )

    if doc.get("gridfs_id"):
        await delete_object(doc["gridfs_id"])

    await db[UPLOAD_JOBS].delete_one({"_id": job_id})
    return success_envelope({"job_id": job_id, "deleted": True})


@router.get("/upload-status", summary="查詢月份上傳總覽")
async def get_upload_status(period: str):
    if len(period) != 7 or period[4] != "-":
        raise HTTPException(
            400, detail={"code": "INVALID_PERIOD", "message": "period 格式須為 YYYY-MM"}
        )
    db = get_db()
    data = await build_upload_status(db, period)
    return success_envelope(data)
