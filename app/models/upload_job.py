"""上傳作業（兼用於 reconcile 背景作業）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    job_type: Mapped[str] = mapped_column(
        Enum("upload", "reconcile_m1", "reconcile_m2", "reconcile_m3", name="job_type_enum"),
        nullable=False,
        default="upload",
    )

    # upload-only 欄位
    source_type: Mapped[str | None] = mapped_column(String(30))  # vendor/payment/bank/cash
    source_name: Mapped[str | None] = mapped_column(String(50))
    file_path: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    row_count: Mapped[int | None] = mapped_column(Integer)

    # 共用欄位
    status: Mapped[str] = mapped_column(
        Enum("queued", "processing", "done", "failed", name="job_status_enum"),
        nullable=False,
        default="queued",
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)

    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_of_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("upload_jobs.job_id", ondelete="SET NULL")
    )

    error_msg: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
