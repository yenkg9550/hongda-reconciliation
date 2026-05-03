"""場站主檔與場站支付方式對照。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Venue(Base):
    __tablename__ = "venues"

    venue_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    venue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor_code: Mapped[str | None] = mapped_column(String(20))
    manager: Mapped[str | None] = mapped_column(String(50))
    tax_id: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    payments: Mapped[list["VenuePayment"]] = relationship(
        back_populates="venue", cascade="all, delete-orphan"
    )


class VenuePayment(Base):
    __tablename__ = "venue_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("venues.venue_code", ondelete="CASCADE"), nullable=False
    )
    payment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(String(100))

    venue: Mapped[Venue] = relationship(back_populates="payments")
