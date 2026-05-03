"""現金業績。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CashRecord(Base):
    __tablename__ = "cash_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("upload_jobs.job_id"), nullable=False, index=True
    )
    venue_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("venues.venue_code"), index=True
    )
    collector_name: Mapped[str | None] = mapped_column(String(50), index=True)
    item_type: Mapped[str | None] = mapped_column(String(20))  # 臨停/月租/其他
    charge_date: Mapped[date | None] = mapped_column(Date)
    deposit_date: Mapped[date | None] = mapped_column(Date)
    deposit_channel: Mapped[str | None] = mapped_column(String(30))  # ATM / convenience_store
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
