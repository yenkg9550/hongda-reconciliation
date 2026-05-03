"""報表匯出（MongoDB 版）。"""

from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.db.collections import M3_EXCEPTIONS
from app.db.mongo import get_db
from app.services.reconcile_service import REASON_LABELS, stub_m1_results, stub_m2_results

router = APIRouter()


def _wb_to_response(wb: Workbook, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/m1/export", summary="匯出 M1 對帳報表")
async def export_m1(period_start: date = Query(...), period_end: date = Query(...)):
    wb = Workbook()
    ws = wb.active
    ws.title = "M1 電子支付對帳"
    ws.append(["場站代碼", "場站名稱", "系統商", "系統商金額", "預期撥款", "實際撥款", "差異", "狀態"])
    for r in stub_m1_results():
        ws.append([
            r["venue_code"], r["venue_name"], r["vendor_code"],
            r["vendor_amount"], r["expected_remit"], r["actual_remit"],
            r["diff_amount"], r["status"],
        ])
    return _wb_to_response(wb, f"m1_{period_start}_{period_end}.xlsx")


@router.get("/reports/m2/export", summary="匯出 M2 對帳報表")
async def export_m2(period_start: date = Query(...), period_end: date = Query(...)):
    wb = Workbook()
    ws = wb.active
    ws.title = "M2 現金對帳"
    ws.append(["場站代碼", "場站名稱", "收費員", "現金業績", "銀行入帳", "差異", "狀態"])
    for r in stub_m2_results():
        ws.append([
            r["venue_code"], r["venue_name"], r["collector_name"],
            r["cash_amount"], r["bank_amount"], r["diff_amount"], r["status"],
        ])
    return _wb_to_response(wb, f"m2_{period_start}_{period_end}.xlsx")


@router.get("/reports/m3/export", summary="匯出 M3 例外清單")
async def export_m3():
    db = get_db()
    cursor = db[M3_EXCEPTIONS].find({}).sort("_id", 1)
    rows = await cursor.to_list(length=10_000)
    wb = Workbook()
    ws = wb.active
    ws.title = "M3 例外清單"
    ws.append(["ID", "場站", "支付類型", "差異金額", "原因", "備註", "已處理"])
    for r in rows:
        ws.append([
            str(r.get("_id")),
            f"{r.get('venue_code', '')} {r.get('venue_name', '')}",
            r.get("payment_type"),
            r.get("diff_amount"),
            REASON_LABELS.get(r.get("diff_type") or "", r.get("diff_type")),
            r.get("note") or "",
            "是" if r.get("resolved") else "否",
        ])
    return _wb_to_response(wb, "m3_exceptions.xlsx")
