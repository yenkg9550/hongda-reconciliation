"""支付業者交易（正規化後）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("upload_jobs.job_id"), nullable=False, index=True
    )
    venue_code: Mapped[str | None] = mapped_column(String(10), index=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, index=True)
    payment_type: Mapped[str | None] = mapped_column(String(30), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    fee_tax: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    fee_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)

    expected_remit_date: Mapped[date | None] = mapped_column(Date)
    raw_ref_no: Mapped[str | None] = mapped_column(String(100))
