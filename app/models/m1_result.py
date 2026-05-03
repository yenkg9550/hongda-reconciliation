"""M1 對帳結果與其與 bank_entries 的關聯。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class M1Result(Base):
    __tablename__ = "m1_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    venue_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    payment_type: Mapped[str | None] = mapped_column(String(30), index=True)

    vendor_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    expected_remit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    actual_remit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    diff: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    status: Mapped[str] = mapped_column(
        Enum("matched", "diff", "pending", name="m1_status_enum"),
        nullable=False,
        default="pending",
        index=True,
    )

    bank_entries: Mapped[list["M1ResultBankEntry"]] = relationship(
        back_populates="m1_result", cascade="all, delete-orphan"
    )


class M1ResultBankEntry(Base):
    """M1 結果 ↔ 銀行入帳（一對多，假日合批）。"""

    __tablename__ = "m1_result_bank_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    m1_result_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("m1_results.id", ondelete="CASCADE"), nullable=False
    )
    bank_entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bank_entries.id", ondelete="CASCADE"), nullable=False
    )

    m1_result: Mapped[M1Result] = relationship(back_populates="bank_entries")
