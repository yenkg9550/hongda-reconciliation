"""系統商報表解析器工廠。

每個 parser 模組未實作前以 _NotImplementedParser placeholder 佔位，
被叫到時 raise NotImplementedError。
"""
from __future__ import annotations

from app.parsers.base import BaseParser
from app.utils.venue_lookup import detect_vendor_code


class _NotImplementedParser(BaseParser):
    def __init__(self, vendor_code: str):
        self.vendor_code = vendor_code

    def parse(self, file_path: str, job_id: str, period: str) -> list[dict]:
        raise NotImplementedError(f"vendor parser 尚未實作：{self.vendor_code}")


def detect_vendor_parser(filename: str) -> tuple[BaseParser, str]:
    """根據檔名識別 vendor parser。

    Returns:
        (parser, vendor_code)
    """
    vendor_code = detect_vendor_code(filename)
    if vendor_code is None:
        raise ValueError(f"無法從檔名識別系統商：{filename}")

    # 各 parser 已實作則 import 真的 class，否則 fallback to placeholder
    try:
        if vendor_code == "fuer_ticket":
            from app.parsers.vendors.fuer_ticket import FuerTicketParser
            return FuerTicketParser(), vendor_code
        if vendor_code == "fuer_car":
            from app.parsers.vendors.fuer_car import FuerCarParser
            return FuerCarParser(), vendor_code
        if vendor_code == "shuoyu":
            from app.parsers.vendors.shuoyu import ShuoyuParser
            return ShuoyuParser(), vendor_code
        if vendor_code == "gangyu":
            from app.parsers.vendors.gangyu import GangyuParser
            return GangyuParser(), vendor_code
        if vendor_code == "microprogram":
            from app.parsers.vendors.microprogram import MicroprogramParser
            return MicroprogramParser(), vendor_code
        if vendor_code == "quanying":
            from app.parsers.vendors.quanying import QuanyingParser
            return QuanyingParser(), vendor_code
        if vendor_code == "yongxi":
            from app.parsers.vendors.yongxi import YongxiParser
            return YongxiParser(), vendor_code
        if vendor_code == "fetc":
            from app.parsers.vendors.fetc import FetcParser
            return FetcParser(), vendor_code
    except ImportError:
        pass

    return _NotImplementedParser(vendor_code), vendor_code
