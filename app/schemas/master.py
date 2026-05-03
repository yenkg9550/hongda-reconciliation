"""主檔 schema."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class VenuePaymentItem(BaseModel):
    id: int
    payment_type: str
    merchant_id: str | None = None


class VenueItem(BaseModel):
    venue_code: str
    venue_name: str
    vendor_code: str | None = None
    manager: str | None = None
    tax_id: str | None = None
    is_active: bool = True
    payments: list[VenuePaymentItem] = []


class VenueCreateRequest(BaseModel):
    venue_code: str
    venue_name: str
    vendor_code: str | None = None
    manager: str | None = None
    tax_id: str | None = None
    is_active: bool = True


class VenueUpdateRequest(BaseModel):
    venue_name: str | None = None
    vendor_code: str | None = None
    manager: str | None = None
    tax_id: str | None = None
    is_active: bool | None = None


class FeeRateItem(BaseModel):
    id: int
    payment_type: str
    rate: Decimal
    effective_from: date | None = None
    effective_to: date | None = None


class FeeRateUpdateRequest(BaseModel):
    rate: Decimal | None = None
    effective_from: date | None = None
    effective_to: date | None = None
