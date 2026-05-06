"""剛鈺報表（.xls）。

兩種 schema 並存：
- 18 欄「停車交易」：項目/車牌號/發票號/汽機車/進場時間/繳費時間/出場時間/停車時長/
                繳費機號/折扣項目/繳費金額/折抵金額/總金額/付款方式/卡號/電支交易序號/...
- 12 欄「發票記錄」：狀態/發票號/做廢/銷貨時間/繳費機號/車牌號/銷售額/稅額/總金額/
                隨機碼/買方統編/付款方式

依據 user 指示，只處理 18 欄停車交易（12 欄是上傳發票記錄，對帳不需要）。
時間是 Excel 序列數字（如 46022.80259）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import xlrd

from app.parsers.base import BaseParser
from app.utils.vendor_dates import excel_serial_to_date, parse_datetime_loose


# 付款方式中文 → 標準 code
_PAY_TYPE_MAP = {
    "現金": "cash",
    "悠遊卡": "easycard",
    "LinePay": "linepay",
    "linepay": "linepay",
    "LINE Pay": "linepay",
    "一卡通Money": "ipass",
    "一卡通": "ipass",
    "icash": "icash",
}


def _to_amount(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            return None


def _normalize_payment(s: Any) -> str | None:
    if s is None:
        return None
    text = str(s).strip()
    return _PAY_TYPE_MAP.get(text, text or None)


class GangyuParser(BaseParser):

    def parse(self, file_path: str, job_id: str, period: str) -> list[dict]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"找不到檔案：{file_path}")

        wb = xlrd.open_workbook(str(path), ragged_rows=True)
        sheet = wb.sheet_by_index(0)
        if sheet.nrows < 2:
            return []

        header = sheet.row_values(0)
        # 偵測 schema
        if "項目" in header and "繳費金額" in header and "付款方式" in header:
            return self._parse_parking(sheet, job_id, period)
        if "狀態" in header and "銷貨時間" in header:
            # 12 欄發票記錄：依 user 指示忽略
            return []
        raise ValueError(f"剛鈺：無法識別 schema：header={header[:5]}")

    def _parse_parking(self, sheet: Any, job_id: str, period: str) -> list[dict]:
        """18 欄停車交易。"""
        out: list[dict] = []
        for r in range(1, sheet.nrows):
            row = sheet.row_values(r)
            if not row or all(v in (None, "") for v in row):
                continue
            item = str(row[0]).strip() if len(row) > 0 else ""
            if item != "臨停":
                continue
            amount = _to_amount(row[10] if len(row) > 10 else None)  # 繳費金額
            if amount is None or amount <= 0:
                continue
            # 繳費時間是 Excel 序列數字
            tdate = excel_serial_to_date(row[5] if len(row) > 5 else None)
            if tdate is None:
                # fallback：寬鬆解析
                tdate = parse_datetime_loose(row[5] if len(row) > 5 else None)
            if tdate is None:
                continue
            payment_type = _normalize_payment(row[13] if len(row) > 13 else None)
            transaction_id = (
                str(row[2]).strip() if len(row) > 2 and row[2] not in (None, "") else None
            )
            # 電支交易序號（有的話更精準）
            ele_id = str(row[15]).strip() if len(row) > 15 and row[15] not in (None, "") else None
            txn = ele_id or transaction_id
            raw = {
                "車牌號": str(row[1]) if len(row) > 1 and row[1] not in (None, "") else None,
                "發票號": transaction_id,
                "進場時間": str(row[4]) if len(row) > 4 else None,
                "繳費時間": str(row[5]) if len(row) > 5 else None,
                "繳費金額": amount,
                "折抵金額": _to_amount(row[11]) if len(row) > 11 else None,
                "總金額": _to_amount(row[12]) if len(row) > 12 else None,
                "付款方式": str(row[13]) if len(row) > 13 and row[13] not in (None, "") else None,
                "電支交易序號": ele_id,
            }
            out.append({
                "job_id": job_id,
                "venue_code": None,
                "payment_type": payment_type,
                "transaction_date": tdate,
                "amount": amount,
                "transaction_id": (txn or "")[:100] or None,
                "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            })
        return out
