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
    # 銀行對帳單
    {"slot_key": "bank_taishin_personal", "source_type": "bank", "source_name": "台新(個人)", "label": "台新（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_personal", "source_type": "bank", "source_name": "永豐(個人)", "label": "永豐（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_hongda", "source_type": "bank", "source_name": "永豐(宏達)", "label": "永豐（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_sinopac_jincheng", "source_type": "bank", "source_name": "永豐(晉呈)", "label": "永豐（晉呈）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_personal", "source_type": "bank", "source_name": "合作(個人)", "label": "合作金庫（個人）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_hongda", "source_type": "bank", "source_name": "合作(宏達)", "label": "合作金庫（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_landbank_jincheng", "source_type": "bank", "source_name": "合作(晉呈)", "label": "合作金庫（晉呈）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_cathay_hongda", "source_type": "bank", "source_name": "國泰(宏達)", "label": "國泰世華（宏達）", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    {"slot_key": "bank_post", "source_type": "bank", "source_name": "郵局", "label": "郵局", "category": "銀行對帳單", "expected_file_count": 1, "is_required": True},
    # 永璽（系統商交易明細，依場域分檔）
    {"slot_key": "vendor_yongxi_wujie", "source_type": "vendor_yongxi", "source_name": "五結", "label": "五結", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_mingde", "source_type": "vendor_yongxi", "source_name": "明德", "label": "明德", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_songren", "source_type": "vendor_yongxi", "source_name": "松仁", "label": "松仁", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_yongli_1", "source_type": "vendor_yongxi", "source_name": "永利機台1", "label": "永利機台 1", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_yongli_2", "source_type": "vendor_yongxi", "source_name": "永利機台2", "label": "永利機台 2", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_jiaoxi", "source_type": "vendor_yongxi", "source_name": "礁溪", "label": "礁溪", "category": "永璽", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_yongxi_shennong4", "source_type": "vendor_yongxi", "source_name": "神農四", "label": "神農四", "category": "永璽", "expected_file_count": 1, "is_required": True},
    # 阜爾（系統商交易明細，依場域分檔）
    {"slot_key": "vendor_fuer_daai_1", "source_type": "vendor_fuer", "source_name": "大愛一", "label": "大愛一", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_daai_2", "source_type": "vendor_fuer", "source_name": "大愛二", "label": "大愛二", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_qiaozhong_1", "source_type": "vendor_fuer", "source_name": "僑中一", "label": "僑中一", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_zhongyang", "source_type": "vendor_fuer", "source_name": "中央", "label": "中央", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_daweidao", "source_type": "vendor_fuer", "source_name": "大衛道", "label": "大衛道", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_zhongping", "source_type": "vendor_fuer", "source_name": "中平", "label": "中平", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_yingge", "source_type": "vendor_fuer", "source_name": "鶯歌", "label": "鶯歌", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_leli", "source_type": "vendor_fuer", "source_name": "樂利", "label": "樂利", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_renyi_2", "source_type": "vendor_fuer", "source_name": "仁義二", "label": "仁義二", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_xinmin", "source_type": "vendor_fuer", "source_name": "新民", "label": "新民", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_chenghong", "source_type": "vendor_fuer", "source_name": "承鋐", "label": "承鋐", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_jianfu_2", "source_type": "vendor_fuer", "source_name": "尖福二", "label": "尖福二", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_dunfu", "source_type": "vendor_fuer", "source_name": "敦富", "label": "敦富", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_huanzhong", "source_type": "vendor_fuer", "source_name": "環中", "label": "環中", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_caijin", "source_type": "vendor_fuer", "source_name": "才金", "label": "才金", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_longfeng", "source_type": "vendor_fuer", "source_name": "龍鳳", "label": "龍鳳", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_shuangshi", "source_type": "vendor_fuer", "source_name": "雙十", "label": "雙十", "category": "阜爾", "expected_file_count": 1, "is_required": True},
    {"slot_key": "vendor_fuer_wenhua", "source_type": "vendor_fuer", "source_name": "文化", "label": "文化", "category": "阜爾", "expected_file_count": 1, "is_required": True},
]


def slot_key_for(source_type: str, source_name: str) -> str:
    """把 (source_type, source_name) 轉成 slot_key。"""
    if source_type == "bank":
        for slot in REQUIRED_SLOTS:
            if slot["source_type"] == "bank" and slot["source_name"] == source_name:
                return slot["slot_key"]
    if source_type == "vendor_yongxi":
        for slot in REQUIRED_SLOTS:
            if slot["source_type"] == "vendor_yongxi" and slot["source_name"] == source_name:
                return slot["slot_key"]
    if source_type == "vendor_fuer":
        for slot in REQUIRED_SLOTS:
            if slot["source_type"] == "vendor_fuer" and slot["source_name"] == source_name:
                return slot["slot_key"]
    return f"{source_type}_{source_name}"
