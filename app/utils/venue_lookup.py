"""從檔名解析 venue_name；查 venue_code（async/Mongo 版）。

跟 backend_20260506 同名同義；差別是 lookup_venue_code 改成 motor async。
"""
from __future__ import annotations

import re
from typing import Any

from app.db.collections import VENUES, VENUE_MAPPINGS


# 廠商中文 → vendor_code（與 master_data.json 一致）
VENDOR_KEYWORD_MAP: list[tuple[str, str]] = [
    # 「阜爾票卡」要在「阜爾」之前
    ("阜爾票卡", "fuer_ticket"),
    ("阜爾", "fuer_car"),
    ("剛鈺", "gangyu"),
    ("微程式", "microprogram"),
    ("永璽", "yongxi"),
    ("碩譽", "shuoyu"),
    ("詮營", "quanying"),
    ("遠通", "fetc"),
]


def detect_vendor_code(filename: str) -> str | None:
    """從檔名識別 vendor_code，例如 '昌吉(剛鈺).xls' → 'gangyu'。"""
    for kw, code in VENDOR_KEYWORD_MAP:
        if kw in filename:
            return code
    return None


def extract_venue_name(filename: str, vendor_code: str | None = None) -> str | None:
    """從檔名抽出場名（與 backend_20260506 同邏輯）。"""
    if not filename:
        return None
    name = re.sub(r"\.(xlsx?|csv)$", "", filename, flags=re.IGNORECASE)
    head = re.split(r"[(（]", name, maxsplit=1)[0].strip()
    head = re.sub(r"\.\d+月$", "", head).strip()
    head = re.sub(r"\d+月$", "", head).strip()
    head = re.sub(r"_\d+(\.\d+)?$", "", head).strip()
    return head or None


async def lookup_venue_code(
    db: Any,
    vendor_code: str | None,
    venue_name: str | None,
) -> str | None:
    """查 venue_code：先查 venue_mappings，fallback 到 venues 主檔。"""
    if not venue_name:
        return None

    if vendor_code:
        vm = await db[VENUE_MAPPINGS].find_one(
            {"source": vendor_code, "source_name": venue_name, "is_active": {"$ne": False}}
        )
        if vm and vm.get("venue_code"):
            return vm["venue_code"]

    v = await db[VENUES].find_one({"venue_name": venue_name})
    if v:
        return v.get("venue_code") or v.get("_id")
    return None
