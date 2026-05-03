"""銀行入帳。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BankEntry(Base):
    __tablename__ = "bank_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("upload_jobs.job_id"), nullable=False, index=True
    )
    account_id: Mapped[str | None] = mapped_column(String(30), index=True)
    value_date: Mapped[date | None] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    description: Mapped[str | None] = mapped_column(String(100))
    memo_raw: Mapped[str | None] = mapped_column(String(200))
    venue_code: Mapped[str | None] = mapped_column(String(10), index=True)
    payment_source: Mapped[str | None] = mapped_column(String(30))
