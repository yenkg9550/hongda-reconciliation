"""上傳服務（MongoDB + GridFS）。

接收檔案 → 計算 SHA-256 → 查重 → 寫入 GridFS → 在 upload_jobs 建立紀錄。
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from app.db.collections import BANK_ENTRIES, UPLOAD_JOBS, VENDOR_TX
from app.db.gridfs import compute_sha256, put_pending
from app.db.gridfs import update_bucket_label
from app.parsers.vendors import detect_vendor_parser
from app.services.bank_parser import BankParseError, parse_bank_entries
from app.utils.venue_lookup import (
    detect_vendor_code,
    extract_venue_name,
    lookup_venue_code,
)

logger = logging.getLogger(__name__)


async def receive_upload(
    db: Any,
    *,
    source_type: str,
    source_name: str,
    period_start: date,
    period_end: date,
    filename: str,
    file_bytes: bytes,
) -> tuple[dict | None, dict | None]:
    """接收一份檔案。

    回傳 (accepted_doc, rejected_dict)，恰好一個為 None。
    accepted_doc 是寫入 MongoDB 的 upload_jobs document。
    """
    checksum = compute_sha256(file_bytes)

    # 查重：相同 checksum 已 done → 拒絕
    existing = await db[UPLOAD_JOBS].find_one(
        {"checksum": checksum, "status": "done"}
    )
    if existing:
        return None, {
            "filename": filename,
            "reason": "DUPLICATE_FILE",
            "message": "已成功匯入過，若要重跑請先至作業記錄確認",
            "existing_job_id": existing.get("job_id"),
        }

    job_id = str(uuid.uuid4())
    gridfs_id = await put_pending(file_bytes, job_id, filename)

    now = datetime.utcnow()
    doc = {
        "_id": job_id,         # 用 UUID 字串作 _id，方便 by-id 查
        "job_id": job_id,
        "job_type": "upload",
        "source_type": source_type,
        "source_name": source_name,
        "filename": filename,
        "gridfs_id": str(gridfs_id),
        "checksum": checksum,
        "status": "queued",
        "progress": 0,
        "message": "已接收，待背景 worker 處理",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "row_count": None,
        "retry_count": 0,
        "retry_of_job_id": None,
        "error_msg": None,
        "created_at": now,
        "last_attempt_at": None,
        "finished_at": None,
    }
    await db[UPLOAD_JOBS].insert_one(doc)

    if source_type == "bank":
        await _parse_bank_upload(
            db,
            job_id=job_id,
            gridfs_id=str(gridfs_id),
            file_bytes=file_bytes,
            filename=filename,
            source_name=source_name,
        )
        doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})
    elif source_type.startswith("vendor"):
        await _parse_vendor_upload(
            db,
            job_id=job_id,
            gridfs_id=str(gridfs_id),
            file_bytes=file_bytes,
            filename=filename,
            source_name=source_name,
            source_type=source_type,
            period_start=period_start,
        )
        doc = await db[UPLOAD_JOBS].find_one({"_id": job_id})

    return doc, None


async def _parse_bank_upload(
    db: Any,
    *,
    job_id: str,
    gridfs_id: str,
    file_bytes: bytes,
    filename: str,
    source_name: str,
) -> None:
    await db[UPLOAD_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": "processing", "progress": 50, "last_attempt_at": datetime.utcnow()}},
    )
    await update_bucket_label(gridfs_id, "processing")

    try:
        entries = parse_bank_entries(
            file_bytes=file_bytes,
            filename=filename,
            source_name=source_name,
            job_id=job_id,
        )
    except BankParseError as exc:
        await db[UPLOAD_JOBS].update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "progress": 100,
                    "message": str(exc),
                    "error_msg": str(exc),
                    "finished_at": datetime.utcnow(),
                }
            },
        )
        await update_bucket_label(gridfs_id, "failed")
        return

    await db[BANK_ENTRIES].delete_many({"job_id": job_id})
    if entries:
        await db[BANK_ENTRIES].insert_many(entries)
    await db[UPLOAD_JOBS].update_one(
        {"_id": job_id},
        {
            "$set": {
                "status": "done",
                "progress": 100,
                "row_count": len(entries),
                "message": f"解析成功，共 {len(entries)} 筆銀行入帳",
                "error_msg": None,
                "finished_at": datetime.utcnow(),
            }
        },
    )
    await update_bucket_label(gridfs_id, "done")


async def _parse_vendor_upload(
    db: Any,
    *,
    job_id: str,
    gridfs_id: str,
    file_bytes: bytes,
    filename: str,
    source_name: str,
    source_type: str,
    period_start: date,
) -> None:
    """系統商報表解析：依檔名 / source_name 派 parser，寫進 vendor_transactions。"""
    await db[UPLOAD_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": "processing", "progress": 50, "last_attempt_at": datetime.utcnow()}},
    )
    await update_bucket_label(gridfs_id, "processing")

    # vendor_code 解析優先序：source_type 後綴 → filename → source_name
    vendor_code: str | None = None
    if "_" in source_type:
        vendor_code = source_type.split("_", 1)[1]
    if not vendor_code:
        vendor_code = detect_vendor_code(filename) or detect_vendor_code(source_name)

    if not vendor_code:
        msg = f"無法識別系統商：filename={filename!r} source_name={source_name!r}"
        await db[UPLOAD_JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed", "progress": 100, "message": msg, "error_msg": msg,
                "finished_at": datetime.utcnow(),
            }},
        )
        await update_bucket_label(gridfs_id, "failed")
        return

    # parser 需要實體檔案，先寫到 tempfile
    suffix = Path(filename).suffix or ".xlsx"
    period_str = period_start.strftime("%Y-%m")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(file_bytes)
            tmp_path = Path(tf.name)

        # 從 filename → vendor parser 派工。先確認 parser 抓到的 code 跟我們的 vendor_code 一致
        try:
            parser, parser_vc = detect_vendor_parser(filename)
        except ValueError:
            # filename 沒帶系統商字樣（例如阜爾票卡 0101.xls），fallback 用 source_name
            parser, parser_vc = detect_vendor_parser(f"{source_name}({_kw_for_vendor(vendor_code)}).xlsx")

        records = parser.parse(str(tmp_path), job_id, period_str)

        # venue_code lookup：parser 可能回 venue_code=None，要從檔名抽場名再查
        venue_name = extract_venue_name(filename, vendor_code)
        if not venue_name or venue_name == Path(filename).stem:
            venue_name = extract_venue_name(source_name, vendor_code)
        shared_venue_code = await lookup_venue_code(db, vendor_code, venue_name)

        cleaned: list[dict] = []
        for rec in records:
            if rec.get("venue_code") is None and shared_venue_code:
                rec["venue_code"] = shared_venue_code
            rec.pop("venue_name", None)
            # date → datetime（BSON 不收 datetime.date）
            td = rec.get("transaction_date")
            if isinstance(td, date) and not isinstance(td, datetime):
                rec["transaction_date"] = datetime.combine(td, time.min)
            # 補 source 資訊以便對帳追蹤
            rec.setdefault("vendor_code", vendor_code)
            rec.setdefault("source_name", source_name)
            rec.setdefault("filename", filename)
            cleaned.append(rec)

        await db[VENDOR_TX].delete_many({"job_id": job_id})
        if cleaned:
            await db[VENDOR_TX].insert_many(cleaned)

        await db[UPLOAD_JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": "done",
                "progress": 100,
                "row_count": len(cleaned),
                "message": f"解析成功，共 {len(cleaned)} 筆系統商交易",
                "error_msg": None,
                "finished_at": datetime.utcnow(),
            }},
        )
        await update_bucket_label(gridfs_id, "done")
    except Exception as exc:  # noqa: BLE001 — 任意 parser 例外都當失敗
        logger.exception("vendor parse failed: job=%s", job_id)
        msg = f"解析失敗：{exc}"
        await db[UPLOAD_JOBS].update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed", "progress": 100, "message": msg, "error_msg": msg,
                "finished_at": datetime.utcnow(),
            }},
        )
        await update_bucket_label(gridfs_id, "failed")
    finally:
        if tmp_path and tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _kw_for_vendor(vendor_code: str) -> str:
    """vendor_code → 中文關鍵字（給 detect_vendor_parser 用的反查）。"""
    mapping = {
        "fuer_ticket": "阜爾票卡",
        "fuer_car": "阜爾",
        "gangyu": "剛鈺",
        "microprogram": "微程式",
        "yongxi": "永璽",
        "shuoyu": "碩譽",
        "quanying": "詮營",
        "fetc": "遠通",
    }
    return mapping.get(vendor_code, vendor_code)
