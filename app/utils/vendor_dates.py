"""系統商報表共用：Excel 序列數字、字串日期 → datetime.date。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


_EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_serial_to_datetime(v: Any) -> datetime | None:
    """Excel 序列數字（如 46022.80259）→ datetime。

    Excel 用 1900-01-01 為 day 1，但有 1900 年 leap year bug，所以實際 epoch 是 1899-12-30。
    """
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < 0 or f > 200_000:  # 防呆：合理範圍
        return None
    try:
        return _EXCEL_EPOCH + timedelta(days=f)
    except (OverflowError, ValueError):
        return None


def excel_serial_to_date(v: Any) -> date | None:
    dt = excel_serial_to_datetime(v)
    return dt.date() if dt else None


def parse_datetime_loose(s: Any) -> date | None:
    """彈性解析常見日期/datetime 格式 → date。

    支援：
    - datetime / date 物件直通
    - Excel 序列數字 (float/int)
    - '2026-01-31 21:48:55' / '2026/01/31' / '2026-01-31'
    - 帶 \\t、空白前綴的字串
    """
    if s is None or s == "":
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    # Excel 序列號（純數字）
    if isinstance(s, (int, float)):
        return excel_serial_to_date(s)
    text = str(s).strip().replace("\t", "").strip()
    if not text:
        return None
    # 純數字字串（Excel 序列）
    try:
        f = float(text)
        if "/" not in text and "-" not in text:
            return excel_serial_to_date(f)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # 截掉時間部分再試
    head = text.split()[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    return None
