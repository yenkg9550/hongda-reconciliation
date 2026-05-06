"""報表匯出（MongoDB 版）。"""

from __future__ import annotations

import io
import logging
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.db.collections import M3_EXCEPTIONS
from app.db.mongo import get_db
from app.services.m1_excel_export import m1_workbook_bytes
from app.services.reconcile_service import REASON_LABELS, get_m2_results

logger = logging.getLogger(__name__)

router = APIRouter()


def _content_disposition(filename: str, ascii_fallback: str | None = None) -> str:
    """產出符合 RFC 5987 的 Content-Disposition 值，支援中文檔名。

    HTTP header 只能 latin-1，中文要用 filename*=UTF-8'' 加 percent-encode。
    舊瀏覽器看 ASCII fallback 那條 filename。
    """
    fb = ascii_fallback or "report.xlsx"
    return (
        f'attachment; filename="{fb}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _wb_to_response(wb: Workbook, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(filename, "report.xlsx")},
    )


@router.get("/reports/m1/export", summary="匯出 M1 對帳報表（23 欄完整版）")
async def export_m1(period_start: date = Query(...), period_end: date = Query(...)):
    db = get_db()
    try:
        data = await m1_workbook_bytes(db, period_start=period_start, period_end=period_end)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "export_m1 failed: period=%s~%s err=%s", period_start, period_end, exc
        )
        raise HTTPException(
            500,
            detail={
                "code": "M1_EXPORT_FAILED",
                "message": f"M1 報表匯出失敗：{type(exc).__name__}: {exc}",
            },
        )
    period_label = period_start.strftime("%Y-%m")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": _content_disposition(
                f"M1a_對帳結果_{period_label}.xlsx",
                ascii_fallback=f"M1a_recon_{period_label}.xlsx",
            ),
        },
    )


@router.get("/reports/m2/export", summary="匯出 M2 對帳報表")
async def export_m2(period_start: date = Query(...), period_end: date = Query(...)):
    db = get_db()
    wb = Workbook()
    ws = wb.active
    ws.title = "M2 現金對帳"
    ws.append(["場站代碼", "場站名稱", "收費員", "現金業績", "銀行入帳", "差異", "狀態"])
    for r in await get_m2_results(db, period_start=period_start, period_end=period_end):
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
