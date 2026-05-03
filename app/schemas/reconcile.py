"""對帳相關 schema."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ReconcileTriggerRequest(BaseModel):
    period_start: date
    period_end: date


class ReconcileTriggerResponse(BaseModel):
    job_id: str
    job_type: str  # reconcile_m1 / m2 / m3
    status: str = "queued"
    message: str = "已建立對帳作業"


class M1ResultItem(BaseModel):
    venue_code: str
    venue_name: str | None = None
    vendor_code: str | None = None
    payment_type: str | None = None
    vendor_amount: Decimal = Decimal(0)
    expected_remit: Decimal = Decimal(0)
    actual_remit: Decimal = Decimal(0)
    diff_amount: Decimal = Decimal(0)
    status: str  # matched / diff / pending


class M2ResultItem(BaseModel):
    venue_code: str
    venue_name: str | None = None
    collector_name: str | None = None
    cash_amount: Decimal = Decimal(0)
    bank_amount: Decimal = Decimal(0)
    diff_amount: Decimal = Decimal(0)
    status: str


class M3ExceptionItem(BaseModel):
    id: int
    venue_code: str | None = None
    venue_name: str | None = None
    payment_type: str | None = None
    vendor_amount: Decimal = Decimal(0)
    actual_remit: Decimal = Decimal(0)
    diff_amount: Decimal = Decimal(0)
    diff_type: str | None = None
    reason_label: str | None = None
    note: str | None = None
    resolved: bool = False


class M3ResolveRequest(BaseModel):
    resolved: bool = True
    note: str | None = None
