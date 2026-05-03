"""上傳/作業相關 schema."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class UploadJobItem(BaseModel):
    job_id: str
    filename: str
    status: str


class UploadRejectedItem(BaseModel):
    filename: str
    reason: str
    message: str
    existing_job_id: str | None = None


class UploadResponse(BaseModel):
    accepted: list[UploadJobItem]
    rejected: list[UploadRejectedItem]


class JobValidation(BaseModel):
    has_issues: bool = False
    error_count: int = 0
    warning_count: int = 0
    missing_file_count: int = 0


class JobResponse(BaseModel):
    job_id: str
    job_type: str
    source_type: str | None = None
    source_name: str | None = None
    filename: str | None = None
    status: str
    progress: int
    message: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    row_count: int | None = None
    retry_count: int = 0
    created_at: datetime
    finished_at: datetime | None = None
    validation: JobValidation | None = None


class JobIssue(BaseModel):
    row: int | None = None
    severity: str  # error / warning
    message: str
    detail: dict[str, Any] | None = None


class UploadStatusJob(BaseModel):
    job_id: str
    filename: str
    status: str
    uploaded_at: datetime
    message: str | None = None


class UploadStatusItem(BaseModel):
    slot_key: str
    source_type: str
    source_name: str
    is_required: bool = True
    status: str  # done / warning / error / missing
    message: str | None = None
    expected_file_count: int = 1
    uploaded_file_count: int = 0
    missing_subfiles: list[str] = []
    uploaded_jobs: list[UploadStatusJob] = []


class UploadStatusResponse(BaseModel):
    period: str
    total_required: int
    completed_count: int
    warning_count: int
    error_count: int = 0
    missing_count: int = 0
    can_submit_reconcile: bool
    items: list[UploadStatusItem]
