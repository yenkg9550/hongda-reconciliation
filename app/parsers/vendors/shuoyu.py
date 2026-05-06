"""碩譽報表（3 種格式：繳費紀錄／悠遊卡／LINE PAY）。

- 繳費紀錄：18 欄 .xls；col 0=序號, col 2=事件類型, col 9=繳費時間, col 10=收費
    → 事件類型='票卡繳費' skip（跟悠遊卡紀錄重複，會雙重計算）
- 悠遊卡支付紀錄：10 欄 .xls；col 3=繳費時間, col 7=訂單金額, col 9=交易狀態
    → 交易狀態!='成功' skip
- LINE PAY 支付紀錄：15 欄 .xls；col 3=繳費時間, col 5=實收金額, col 14=狀態
    → 狀態!='已扣費' skip
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import xlrd

from app.parsers.base import BaseParser
from app.utils.vendor_dates import parse_datetime_loose


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


def _detect_format(filename: str) -> str:
    """根據檔名識別 3 種格式之一：'fee' / 'easycard' / 'linepay'。"""
    if "LINE PAY" in filename or "LINEPAY" in filename.upper():
        return "linepay"
    if "悠遊卡" in filename:
        return "easycard"
    if "繳費紀錄" in filename or "繳費記錄" in filename:
        return "fee"
    raise ValueError(f"碩譽：無法從檔名識別格式：{filename}")


class ShuoyuParser(BaseParser):

    def parse(self, file_path: str, job_id: str, period: str) -> list[dict]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"找不到檔案：{file_path}")

        fmt = _detect_format(path.name)
        wb = xlrd.open_workbook(str(path))
        sheet = wb.sheet_by_index(0)
        if sheet.nrows < 3:
            return []

        # 共用：r1=標題、r2=欄名、r3+=資料
        if fmt == "fee":
            return self._parse_fee(sheet, job_id, period)
        if fmt == "easycard":
            return self._parse_easycard(sheet, job_id, period)
        if fmt == "linepay":
            return self._parse_linepay(sheet, job_id, period)
        return []

    def _parse_fee(self, sheet: Any, job_id: str, period: str) -> list[dict]:
        """繳費紀錄：18 欄。事件類型=票卡繳費 skip。"""
        out: list[dict] = []
        for r in range(2, sheet.nrows):
            row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            if not row or all(v in (None, "") for v in row):
                continue
            event_type = str(row[2]).strip() if len(row) > 2 else ""
            if event_type == "票卡繳費":
                # 跟悠遊卡紀錄會重複，skip
                continue
            amount = _to_amount(row[10] if len(row) > 10 else None)
            if amount is None or amount <= 0:
                continue
            tdate = parse_datetime_loose(row[9] if len(row) > 9 else None)
            if tdate is None:
                continue
            transaction_id = str(row[0]).strip() if row[0] not in (None, "") else None
            raw = {
                "記錄序號": str(row[0]) if row[0] not in (None, "") else None,
                "事件類型": event_type or None,
                "車牌": str(row[5]) if len(row) > 5 and row[5] not in (None, "") else None,
                "繳費時間": str(row[9]) if len(row) > 9 else None,
                "收費": amount,
                "付費": _to_amount(row[11]) if len(row) > 11 else None,
                "折抵": _to_amount(row[13]) if len(row) > 13 else None,
                "發票": str(row[16]) if len(row) > 16 and row[16] not in (None, "") else None,
            }
            out.append({
                "job_id": job_id,
                "venue_code": None,
                "payment_type": "cash",
                "transaction_date": tdate,
                "amount": amount,
                "transaction_id": transaction_id[:100] if transaction_id else None,
                "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            })
        return out

    def _parse_easycard(self, sheet: Any, job_id: str, period: str) -> list[dict]:
        """悠遊卡支付紀錄：10 欄。交易狀態!='成功' skip。"""
        out: list[dict] = []
        for r in range(2, sheet.nrows):
            row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            if not row or all(v in (None, "") for v in row):
                continue
            state = str(row[9]).strip() if len(row) > 9 else ""
            if state != "成功":
                continue
            amount = _to_amount(row[7] if len(row) > 7 else None)
            if amount is None or amount <= 0:
                continue
            tdate = parse_datetime_loose(row[3] if len(row) > 3 else None)
            if tdate is None:
                continue
            transaction_id = str(row[4]).strip() if len(row) > 4 and row[4] not in (None, "") else None
            raw = {
                "車牌": str(row[1]) if len(row) > 1 and row[1] not in (None, "") else None,
                "繳費時間": str(row[3]) if len(row) > 3 else None,
                "訂單編號": str(row[4]) if len(row) > 4 and row[4] not in (None, "") else None,
                "票卡編號": str(row[5]) if len(row) > 5 and row[5] not in (None, "") else None,
                "訂單金額": amount,
                "交易狀態": state,
            }
            out.append({
                "job_id": job_id,
                "venue_code": None,
                "payment_type": "easycard",
                "transaction_date": tdate,
                "amount": amount,
                "transaction_id": transaction_id[:100] if transaction_id else None,
                "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            })
        return out

    def _parse_linepay(self, sheet: Any, job_id: str, period: str) -> list[dict]:
        """LINE PAY：15 欄。狀態!='已扣費' skip。"""
        out: list[dict] = []
        for r in range(2, sheet.nrows):
            row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            if not row or all(v in (None, "") for v in row):
                continue
            state = str(row[14]).strip() if len(row) > 14 else ""
            if state != "已扣費":
                continue
            amount = _to_amount(row[5] if len(row) > 5 else None)  # 實收金額
            if amount is None or amount <= 0:
                continue
            tdate = parse_datetime_loose(row[3] if len(row) > 3 else None)  # 繳費時間
            if tdate is None:
                continue
            transaction_id = str(row[8]).strip() if len(row) > 8 and row[8] not in (None, "") else None
            raw = {
                "車牌": str(row[1]) if len(row) > 1 and row[1] not in (None, "") else None,
                "繳費時間": str(row[3]) if len(row) > 3 else None,
                "訂單金額": _to_amount(row[4]) if len(row) > 4 else None,
                "實收金額": amount,
                "折抵金額": _to_amount(row[6]) if len(row) > 6 else None,
                "訂單編號": str(row[8]) if len(row) > 8 and row[8] not in (None, "") else None,
                "支付時間": str(row[10]) if len(row) > 10 else None,
                "狀態": state,
            }
            out.append({
                "job_id": job_id,
                "venue_code": None,
                "payment_type": "linepay",
                "transaction_date": tdate,
                "amount": amount,
                "transaction_id": transaction_id[:100] if transaction_id else None,
                "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            })
        return out
