"""費率設定。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeeRate(Base):
    __tablename__ = "fee_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
