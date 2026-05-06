"""Parser 抽象基底。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str, job_id: str, period: str) -> list[dict]:
        """回傳 list of dicts，每個 dict 對應一筆 bank_transactions 欄位資料。"""
        ...
