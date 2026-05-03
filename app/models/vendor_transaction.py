"""系統商交易（正規化後）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VendorTransaction(Base):
    __tablename__ = "vendor_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("upload_jobs.job_id"), nullable=False, index=True
    )
    venue_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("venues.venue_code"), index=True
    )
    transaction_date: Mapped[date | None] = mapped_column(Date, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    invoice_no: Mapped[str | None] = mapped_column(String(20))
    plate_no: Mapped[str | None] = mapped_column(String(10))
    source_vendor: Mapped[str | None] = mapped_column(String(20))
