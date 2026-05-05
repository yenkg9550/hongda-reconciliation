"""對帳每月必要上傳項目。

目前先收斂 Phase 1 範圍，只開銀行對帳單上傳。
"""

from __future__ import annotations

from typing import TypedDict


class SlotDef(TypedDict):
    slot_key: str
    source_type: str
    source_name: str
    label: str
    category: str
    expected_file_count: int
    is_required: bool


REQUIRED_SLOTS: list[SlotDef] = [
    {"slot_key": "bank_taishin_personal", "source_type": "bank", "source_name": "台新(個人)", "label": "台新（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_personal", "source_type": "bank", "source_name": "永豐(個人)", "label": "永豐（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_hongda", "source_type": "bank", "source_name": "永豐(宏達)", "label": "永豐（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_jincheng", "source_type": "bank", "source_name": "永豐(晉呈)", "label": "永豐（晉呈）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_personal", "source_type": "bank", "source_name": "合作(個人)", "label": "合作金庫（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_hongda", "source_type": "bank", "source_name": "合作(宏達)", "label": "合作金庫（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_jincheng", "source_type": "bank", "source_name": "合作(晉呈)", "label": "合作金庫（晉呈）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_cathay_hongda", "source_type": "bank", "source_name": "國泰(宏達)", "label": "國泰世華（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_post", "source_type": "bank", "source_name": "郵局", "label": "郵局", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
]


def slot_key_for(source_type: str, source_name: str) -> str:
    """把 (source_type, source_name) 轉成 slot_key。"""
    if source_type == "bank":
        # 用 source_name 對應現有 slot
        for slot in REQUIRED_SLOTS:
            if slot["source_type"] == "bank" and slot["source_name"] == source_name:
                return slot["slot_key"]
    return f"{source_type}_{source_name}"
