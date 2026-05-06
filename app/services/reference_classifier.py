"""Bank reference 解析器（async/Mongo 版）。

支援兩種模式：
- 直接吃 motor db（每筆 reference 都會打 Mongo，慢但簡單）
- 給 ClassifierCache 預載 master，整個分類過程在記憶體做（快很多）

reconcile_m1_engine 走 cache 路徑；單次測試 / 其他呼叫者吃 db 即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.db.collections import VENUE_MAPPINGS, VENUES


@dataclass
class ReferenceMatch:
    payment_type: Optional[str] = None
    venue_code: Optional[str] = None
    venue_candidates: list[str] = field(default_factory=list)
    is_vendor_total: bool = False
    vendor_code: Optional[str] = None
    confidence: str = "unknown"  # exact / fuzzy / vendor_total / unknown
    raw_pattern: str = "unmatched"


class ClassifierCache:
    """預載 master 進記憶體，給 reconcile 大量分類用。"""

    def __init__(self) -> None:
        # (source, source_name) -> [venue_code,...]（同一 source_name 可能多筆 mapping）
        self.mapping_exact: dict[tuple[str, str], list[str]] = {}
        # source -> list of (source_name, venue_code)（給 prefix match 用）
        self.mapping_by_source: dict[str, list[tuple[str, str]]] = {}
        # venue_name -> [venue_code,...]
        self.venue_by_first: dict[str, list[str]] = {}  # 給 prefix match 用，按 first_char 分桶
        self.venues_active: list[tuple[str, str]] = []  # (venue_name, venue_code)

    @classmethod
    async def build(cls, db: Any) -> "ClassifierCache":
        self = cls()

        # venue_mappings
        async for m in db[VENUE_MAPPINGS].find({"is_active": {"$ne": False}}):
            src = m.get("source"); name = m.get("source_name"); vc = m.get("venue_code")
            if not (src and name and vc):
                continue
            self.mapping_exact.setdefault((src, name), []).append(vc)
            self.mapping_by_source.setdefault(src, []).append((name, vc))

        # venues：按 venue_name 第一個字分桶
        async for v in db[VENUES].find({"is_active": {"$ne": False}}):
            name = v.get("venue_name"); vc = v.get("venue_code") or v.get("_id")
            if not (name and vc):
                continue
            self.venues_active.append((name, vc))
            first = name[0] if name else ""
            if first:
                self.venue_by_first.setdefault(first, []).append(vc)

        return self

    def find_venues_by_prefix(self, prefix: str) -> list[str]:
        if not prefix:
            return []
        # 第一個字當 bucket，再對 bucket 內全比 prefix
        bucket = self.venue_by_first.get(prefix[0], [])
        if len(prefix) == 1:
            return list(bucket)
        # 對 venue_name 再做 prefix 比對（從 venues_active 撈）
        return [vc for name, vc in self.venues_active if name.startswith(prefix)]


# 全形 → 半形
_FULL_TO_HALF = str.maketrans(
    "０１２３４５６７８９"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "＿．／－",
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "_./-",
)


def _normalize_full_to_half(text: str) -> str:
    return text.translate(_FULL_TO_HALF)


def _strip_bank_prefix(text: str) -> str:
    """剝掉 reference 前綴的長串銀行代碼數字（如永豐戶 387xxxxxxxxxxxxxxx）。"""
    return re.sub(r"^\d{18,}", "", text).strip()


async def _find_venues_by_prefix(db: Any, prefix: str) -> list[str]:
    """venue_name 以 prefix 開頭的 venue_code 清單（DB 版）。"""
    if not prefix:
        return []
    safe = re.escape(prefix)
    cursor = db[VENUES].find(
        {"venue_name": {"$regex": f"^{safe}"}, "is_active": {"$ne": False}},
        {"venue_code": 1, "_id": 0},
    )
    rows = await cursor.to_list(length=200)
    return [r["venue_code"] for r in rows if r.get("venue_code")]


async def classify_reference(
    ref: Optional[str], db: Any, *, cache: Optional[ClassifierCache] = None
) -> ReferenceMatch:
    """根據 bank reference 推斷 payment_type 與 venue_code。

    cache 給的話走純記憶體（快很多）；沒給的話 fallback 打 Mongo。
    """
    if not ref:
        return ReferenceMatch(raw_pattern="empty")

    raw_text = ref.strip()
    text = _strip_bank_prefix(raw_text)
    if not text:
        return ReferenceMatch(
            payment_type="easycard",
            confidence="unknown",
            raw_pattern="numeric_easycard_no_venue",
        )

    # 1. LINE PAY 精準
    if "連加－" in text or "連支－" in text:
        store = re.split(r"連[加支]－", text, maxsplit=1)[-1].strip()
        store = _normalize_full_to_half(store)
        if store:
            if cache:
                exact = cache.mapping_exact.get(("linepay", store), [])
                if exact:
                    return ReferenceMatch(
                        payment_type="linepay", venue_code=exact[0],
                        confidence="exact", raw_pattern="linepay_store",
                    )
                cands = [
                    vc for name, vc in cache.mapping_by_source.get("linepay", [])
                    if name.startswith(store)
                ]
            else:
                vm = await db[VENUE_MAPPINGS].find_one(
                    {"source": "linepay", "source_name": store}
                )
                if vm:
                    return ReferenceMatch(
                        payment_type="linepay", venue_code=vm.get("venue_code"),
                        confidence="exact", raw_pattern="linepay_store",
                    )
                cursor = db[VENUE_MAPPINGS].find(
                    {"source": "linepay", "source_name": {"$regex": f"^{re.escape(store)}"}}
                )
                cands_vm = await cursor.to_list(length=50)
                cands = [vm.get("venue_code") for vm in cands_vm if vm.get("venue_code")]
            if cands:
                if len(cands) == 1:
                    return ReferenceMatch(
                        payment_type="linepay", venue_code=cands[0],
                        venue_candidates=cands, confidence="exact",
                        raw_pattern="linepay_store_prefix_unique",
                    )
                return ReferenceMatch(
                    payment_type="linepay", venue_candidates=cands,
                    confidence="fuzzy", raw_pattern="linepay_store_prefix_fuzzy",
                )
        return ReferenceMatch(
            payment_type="linepay", confidence="unknown",
            raw_pattern="linepay_unknown_store",
        )

    async def _venues_by_prefix(prefix: str) -> list[str]:
        return cache.find_venues_by_prefix(prefix) if cache else await _find_venues_by_prefix(db, prefix)

    # 2. 悠遊卡撥款<owner><first>
    m = re.match(r"悠遊卡撥款(宏達|晉呈)(.)", text)
    if m:
        venue_first = m.group(2)
        candidates = await _venues_by_prefix(venue_first)
        if len(candidates) == 1:
            return ReferenceMatch(
                payment_type="easycard",
                venue_code=candidates[0],
                venue_candidates=candidates,
                confidence="exact",
                raw_pattern="easycard_remit_unique",
            )
        return ReferenceMatch(
            payment_type="easycard",
            venue_candidates=candidates,
            confidence="fuzzy" if candidates else "unknown",
            raw_pattern="easycard_remit",
        )

    # 3. 悠遊付提領
    m = re.match(r"悠遊付提領[＿_]?(宏達|晉呈)?(.)", text)
    if m:
        venue_first = m.group(2)
        candidates = await _venues_by_prefix(venue_first)
        return ReferenceMatch(
            payment_type="easywallet",
            venue_code=candidates[0] if len(candidates) == 1 else None,
            venue_candidates=candidates,
            confidence=(
                "exact" if len(candidates) == 1 else "fuzzy" if candidates else "unknown"
            ),
            raw_pattern="easywallet_remit",
        )

    # 4. 遠創智慧 (FETC)
    if "遠創" in text:
        return ReferenceMatch(
            payment_type="fetc",
            is_vendor_total=True,
            vendor_code="fetc",
            confidence="vendor_total",
            raw_pattern="fetc_total",
        )

    # 5. 阜爾運通
    if "阜爾運通" in text:
        return ReferenceMatch(
            is_vendor_total=True,
            vendor_code="fuer",  # ambiguous，由 reconcile algorithm 進一步分
            confidence="vendor_total",
            raw_pattern="fuer_total",
        )

    # 7. 國泰世華受託信託
    if "國泰世華" in text and ("受託信託" in text or "信託財產" in text):
        return ReferenceMatch(
            confidence="unknown",
            raw_pattern="cathay_trust",
        )

    # 6. 場名直接 reference
    text_norm = _normalize_full_to_half(text)
    candidates_text = [
        text_norm,
        re.sub(r"^\d{3,8}", "", text_norm).strip(),
        re.sub(r"^\d+月\d+日", "", text_norm).strip(),
        re.sub(r"^[一二三四五六七八九十]+月[一二三四五六七八九十零0-9]+日", "", text_norm).strip(),
    ]
    for t in candidates_text:
        if not t:
            continue
        for prefix_len in [4, 3, 2]:
            prefix = t[:prefix_len]
            if not prefix or prefix.isdigit():
                continue
            cands = await _venues_by_prefix(prefix)
            if cands:
                if len(cands) == 1:
                    return ReferenceMatch(
                        venue_code=cands[0],
                        venue_candidates=cands,
                        confidence="exact",
                        raw_pattern=f"venue_direct_{prefix_len}",
                    )
                return ReferenceMatch(
                    venue_candidates=cands,
                    confidence="fuzzy",
                    raw_pattern=f"venue_partial_{prefix_len}",
                )

    # 8. 純數字 16+ 位
    if re.fullmatch(r"\d{16,20}", text):
        return ReferenceMatch(
            payment_type="easycard",
            confidence="unknown",
            raw_pattern="numeric_easycard_no_venue",
        )

    # 9. 商家月結
    if any(kw in text for kw in ["股份有限", "財團法人", "有限公司"]):
        return ReferenceMatch(
            confidence="unknown",
            raw_pattern="merchant_payment",
        )

    return ReferenceMatch(raw_pattern="unmatched")
