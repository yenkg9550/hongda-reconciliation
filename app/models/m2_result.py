"""M2 對帳結果（現金）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class M2Result(Base):
    __tablename__ = "m2_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    venue_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    collector_name: Mapped[str | None] = mapped_column(String(50), index=True)

    cash_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    bank_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    diff: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    status: Mapped[str] = mapped_column(
        Enum("matched", "diff", "pending", name="m2_status_enum"),
        nullable=False,
        default="pending",
        index=True,
    )
