"""阜爾票卡場（BIFF2 古早 Excel 格式）。

特性：
- BIFF2 格式：xlrd 在 fixed_BIFF2_xfindex 會 assert 失敗，需 monkey-patch
- 每天一檔（檔名如 '0101.xls'），場名在父資料夾或必須由上傳 metadata 帶入
- Layout：
    r3: 場地名稱: <場名> | 資料日期: YYYY/MM/DD
    r5: 欄名（合併儲存格，實際資料分散在 16 欄）
    r7+: 多個收費站段，每段有 'NNN' 收費站 marker、資料列、'筆數:' 小計
- 資料列 col index（依實測）：
    col 0:  序號 7-8 位
    col 1:  票號
    col 4:  統一編號
    col 6:  進場車道（'A' / '02' 等）
    col 7:  進場日期 YYYYMMDD
    col 8:  進場時間 HHMM
    col 9:  出場車道
    col 10: 出場日期 YYYYMMDD
    col 11: 出場時間 HHMM
    col 13: 金額
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import xlrd

from app.parsers.base import BaseParser


# ---------- BIFF2 monkey-patch（process-wide，only once）----------

_BIFF2_PATCHED = False


def _patch_xlrd_for_biff2() -> None:
    global _BIFF2_PATCHED
    if _BIFF2_PATCHED:
        return
    from xlrd import biffh
    from xlrd import sheet as _xlrd_sheet
    from xlrd.sheet import Sheet

    # Fix 1: BIFF2 xfindex assert 在某些檔案會失敗
    original = Sheet.fixed_BIFF2_xfindex

    def patched_xf(self, cell_attr, rowx, colx, true_xfx=None):
        try:
            return original(self, cell_attr, rowx, colx, true_xfx)
        except AssertionError:
            return 0

    Sheet.fixed_BIFF2_xfindex = patched_xf

    # Fix 2: BIFF2 string length 偶爾會多算 1，導致 cp950/big5 解到 incomplete sequence
    # 改用寬鬆解碼（壞 byte 用 ? 取代）
    def _lenient_decode(b, enc):
        return b.decode(enc, errors="replace")

    biffh.unicode = _lenient_decode
    _xlrd_sheet.unicode = _lenient_decode

    _BIFF2_PATCHED = True


# ---------- helper ----------


def _yyyymmdd_to_date(s: Any) -> date | None:
    if s is None or s == "":
        return None
    text = str(s).strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


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


def _is_data_row_serial(v: Any) -> bool:
    """col 0 是不是「資料列序號」(7-8 位純數字)。"""
    if v is None:
        return False
    s = str(v).strip()
    return bool(re.fullmatch(r"\d{7,8}", s))


def _venue_name_from_path(file_path: str) -> str | None:
    """從父資料夾名抽 venue_name。

    例如：'/.../富貴(阜爾票卡)/0101.xls' → '富貴'
    """
    parent = Path(file_path).parent.name
    if not parent:
        return None
    # 剝掉 '(阜爾票卡)' 之類的後綴
    head = re.split(r"[(（]", parent, maxsplit=1)[0].strip()
    return head or None


# ---------- parser ----------


class FuerTicketParser(BaseParser):
    """阜爾票卡 BIFF2 .xls，每日一檔。"""

    def parse(self, file_path: str, job_id: str, period: str) -> list[dict]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"找不到檔案：{file_path}")

        _patch_xlrd_for_biff2()

        try:
            wb = xlrd.open_workbook(str(path), encoding_override="cp950")
        except Exception as e:
            raise ValueError(f"無法讀取阜爾票卡 BIFF2 檔案：{e}") from e

        sheet = wb.sheet_by_index(0)
        if sheet.nrows < 7:
            return []

        venue_name = _venue_name_from_path(file_path)

        out: list[dict] = []
        for r in range(sheet.nrows):
            row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            if not row:
                continue
            if not _is_data_row_serial(row[0] if len(row) > 0 else None):
                continue
            # col 13 = 金額；col 10 = 出場日期；col 1 = 票號
            amount = _to_amount(row[13] if len(row) > 13 else None)
            if amount is None or amount <= 0:
                continue
            tdate = _yyyymmdd_to_date(row[10] if len(row) > 10 else None)
            if tdate is None:
                # 廢卡可能沒出場日期；fallback 進場日期
                tdate = _yyyymmdd_to_date(row[7] if len(row) > 7 else None)
            if tdate is None:
                continue
            transaction_id = str(row[1]).strip() if len(row) > 1 and row[1] not in (None, "") else None

            raw = {
                "序號": str(row[0]) if row[0] not in (None, "") else None,
                "票號": str(row[1]) if len(row) > 1 and row[1] not in (None, "") else None,
                "統一編號": str(row[4]) if len(row) > 4 and row[4] not in (None, "") else None,
                "進場": f"{row[6]}-{row[7]}-{row[8]}" if len(row) > 8 else None,
                "出場": f"{row[9]}-{row[10]}-{row[11]}" if len(row) > 11 else None,
                "金額": amount,
            }

            out.append({
                "job_id": job_id,
                "venue_name": venue_name,  # 暫存，dispatcher 會 lookup→venue_code 後丟掉
                "venue_code": None,
                "payment_type": "票卡",
                "transaction_date": tdate,
                "amount": amount,
                "transaction_id": transaction_id[:100] if transaction_id else None,
                "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            })
        return out
