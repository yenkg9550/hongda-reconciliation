"""M3 例外差異。"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class M3Exception(Base):
    __tablename__ = "m3_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    m1_result_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("m1_results.id", ondelete="SET NULL"), index=True
    )
    vendor_tx_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vendor_transactions.id", ondelete="SET NULL")
    )
    payment_tx_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("payment_transactions.id", ondelete="SET NULL")
    )
    venue_code: Mapped[str | None] = mapped_column(String(10), index=True)
    venue_name: Mapped[str | None] = mapped_column(String(100))
    payment_type: Mapped[str | None] = mapped_column(String(30))

    diff_type: Mapped[str | None] = mapped_column(
        Enum("timing", "amount", "missing", "rate_diff", "note_unmatched", "other", name="m3_diff_type_enum"),
    )
    diff_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
