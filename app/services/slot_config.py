"""對帳每月必要上傳項目（17 個 slot）。

對應 docs/API文件.md 1.8 的 GET /upload-status：
- vendor: 7 家系統商
- bank: 5 家銀行
- payment: 4 家支付業者
- cash: 1 個收費員業績
"""

from __future__ import annotations

from typing import TypedDict


class SlotDef(TypedDict):
    slot_key: str
    source_type: str
    source_name: str
    expected_file_count: int
    is_required: bool


REQUIRED_SLOTS: list[SlotDef] = [
    # 系統商
    {"slot_key": "vendor_剛鈺", "source_type": "vendor", "source_name": "剛鈺", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_微程式", "source_type": "vendor", "source_name": "微程式", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_永璽", "source_type": "vendor", "source_name": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_碩譽", "source_type": "vendor", "source_name": "碩譽", "expected_file_count": 3, "is_required": True},
    {"slot_key": "vendor_詮營", "source_type": "vendor", "source_name": "詮營", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_遠通", "source_type": "vendor", "source_name": "遠通", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_阜爾", "source_type": "vendor", "source_name": "阜爾", "expected_file_count": 2, "is_required": True},
    # 銀行
    {"slot_key": "bank_taishin", "source_type": "bank", "source_name": "台新", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank", "source_type": "bank", "source_name": "合作金庫", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_cathay", "source_type": "bank", "source_name": "國泰世華", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_personal", "source_type": "bank", "source_name": "永豐銀行（個人）", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_post", "source_type": "bank", "source_name": "郵局", "expected_file_count": 1, "is_required": True},
    # 支付業者
    {"slot_key": "payment_linepay", "source_type": "payment", "source_name": "LINE Pay", "expected_file_count": 1, "is_required": True},
    {"slot_key": "payment_easycard", "source_type": "payment", "source_name": "悠遊卡", "expected_file_count": 1, "is_required": True},
    {"slot_key": "payment_easywallet", "source_type": "payment", "source_name": "悠遊付", "expected_file_count": 1, "is_required": True},
    {"slot_key": "payment_ipass", "source_type": "payment", "source_name": "iPass Money", "expected_file_count": 1, "is_required": False},
    # 現金業績
    {"slot_key": "cash_record", "source_type": "cash", "source_name": "現金業績", "expected_file_count": 1, "is_required": True},
]


def slot_key_for(source_type: str, source_name: str) -> str:
    """把 (source_type, source_name) 轉成 slot_key。"""
    if source_type == "bank":
        # 用 source_name 對應現有 slot
        for slot in REQUIRED_SLOTS:
            if slot["source_type"] == "bank" and slot["source_name"] == source_name:
                return slot["slot_key"]
    return f"{source_type}_{source_name}"
