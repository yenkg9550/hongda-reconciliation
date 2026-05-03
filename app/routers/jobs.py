"""GET /jobs, GET /jobs/{id}, POST /jobs/{id}/retry, GET /jobs/{id}/issues (Mongo)"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app.db.collections import UPLOAD_JOBS
from app.db.mongo import get_db
from app.schemas.common import paged_envelope, success_envelope

router = APIRouter()


def _serialize_job(doc: dict) -> dict:
    return {
        "job_id": doc.get("job_id"),
        "job_type": doc.get("job_type"),
        "source_type": doc.get("source_type"),
        "source_name": doc.get("source_name"),
        "filename": doc.get("filename"),
        "status": doc.get("status"),
        "progress": doc.get("progress", 0),
        "message": doc.get("message"),
        "period_start": doc.get("period_start"),
        "period_end": doc.get("period_end"),
        "row_count": doc.get("row_count"),
        "retry_count": doc.get("retry_count", 0),
        "created_at": doc["created_at"].isoformat() if hasattr(doc.get("created_at"), "isoformat") else doc.get("created_at"),
        "finished_at": doc["finished_at"].isoformat() if hasattr(doc.get("finished_at"), "isoformat") else doc.get("finished_at"),
        "gridfs_id": doc.get("gridfs_id"),
        "validation": {
            "has_issues": doc.get("status") == "failed",
            "error_count": 1 if doc.get("status") == "failed" else 0,
            "warning_count": 0,
            "missing_file_count": 0,
        },
    }


@router.get("/jobs", summary="列出近期作業記錄")
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(None),
    job_type: str | None = Query(None),
    source_type: str | None = Query(None),
):
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    if job_type:
        query["job_type"] = job_type
    if source_type:
        query["source_type"] = source_type

    coll = db[UPLOAD_JOBS]
    total = await coll.count_documents(query)
    cursor = coll.find(query).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    rows = await cursor.to_list(length=page_size)
    return paged_envelope(
        [_serialize_job(j) for j in rows], total=total, page=page, page_size=page_size
    )


@router.get("/jobs/{job_id}", summary="查詢單一作業狀態")
async def get_job(job_id: Annotated[str, Path(...)]):
    db = get_db()
    doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    if not doc:
        raise HTTPException(
            404, detail={"code": "JOB_NOT_FOUND", "message": f"找不到 job {job_id}"}
        )
    return success_envelope(_serialize_job(doc))


@router.post("/jobs/{job_id}/retry", summary="重新執行作業")
async def retry_job(job_id: Annotated[str, Path(...)]):
    db = get_db()
    doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    if not doc:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "找不到 job"})
    if doc.get("status") != "failed":
        raise HTTPException(
            409,
            detail={
                "code": "JOB_NOT_RETRIABLE",
                "message": f"目前狀態 {doc.get('status')} 不可重試（僅 failed 可重試）",
            },
        )

    update = {
        "$set": {
            "status": "queued",
            "message": "已排入重試",
            "error_msg": None,
        },
        "$inc": {"retry_count": 1},
    }
    await db[UPLOAD_JOBS].update_one({"_id": job_id}, update)
    refreshed = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    return success_envelope(_serialize_job(refreshed))


@router.get("/jobs/{job_id}/issues", summary="查詢作業問題明細")
async def get_job_issues(job_id: Annotated[str, Path(...)]):
    db = get_db()
    doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    if not doc:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "找不到 job"})
    issues = []
    if doc.get("status") == "failed" and doc.get("error_msg"):
        issues.append(
            {
                "row": None,
                "severity": "error",
                "message": doc["error_msg"],
                "detail": None,
            }
        )
    return success_envelope(issues)
