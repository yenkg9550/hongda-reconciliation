"""GridFS 檔案儲存 — 全部存在 MongoDB，不依賴 AWS S3。

提供與舊 s3_storage 相容的 API：
- compute_sha256(data): 計算檔案 hash（synchronous，給 worker / service 共用）
- put_pending(file_bytes, job_id, filename) -> ObjectId: 上傳到 GridFS
- delete_object(file_id) -> bool: 刪除
- get_bytes(file_id) -> bytes: 讀回（給 parser 用）
- exists(file_id) -> bool
"""

from __future__ import annotations

import hashlib
from typing import BinaryIO

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.db.collections import GRIDFS_PREFIX
from app.db.mongo import get_db


def compute_sha256(data: bytes | BinaryIO) -> str:
    """計算 SHA-256（同步），bytes 或 file-like 都吃。"""
    h = hashlib.sha256()
    if isinstance(data, bytes):
        h.update(data)
        return h.hexdigest()
    pos = data.tell()
    data.seek(0)
    while True:
        chunk = data.read(65536)
        if not chunk:
            break
        h.update(chunk)
    data.seek(pos)
    return h.hexdigest()


def _bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(get_db(), bucket_name=GRIDFS_PREFIX)


async def put_pending(file_bytes: bytes, job_id: str, filename: str) -> ObjectId:
    """把檔案存進 GridFS，回傳 ObjectId。

    metadata 會帶 job_id 與 bucket label（方便日後 query / cleanup）。
    """
    bucket = _bucket()
    file_id = await bucket.upload_from_stream(
        filename,
        file_bytes,
        metadata={"job_id": job_id, "bucket": "pending"},
    )
    return file_id


async def update_bucket_label(file_id: ObjectId | str, new_bucket: str) -> None:
    """模擬「移動 bucket」：只改 metadata 的 label，不真的搬資料。

    GridFS 沒有資料夾概念；舊架構 import/{pending,processing,done,failed}
    用的就是「狀態標籤」，現在用 metadata.bucket 對等表達。
    """
    fid = ObjectId(file_id) if isinstance(file_id, str) else file_id
    db = get_db()
    await db[f"{GRIDFS_PREFIX}.files"].update_one(
        {"_id": fid}, {"$set": {"metadata.bucket": new_bucket}}
    )


async def delete_object(file_id: ObjectId | str) -> bool:
    """刪除一個 GridFS 檔案。找不到回 False，不噴錯。"""
    fid = ObjectId(file_id) if isinstance(file_id, str) else file_id
    bucket = _bucket()
    try:
        await bucket.delete(fid)
        return True
    except Exception:
        return False


async def get_bytes(file_id: ObjectId | str) -> bytes:
    """把整份檔案讀進記憶體。給 parser 解析用。"""
    fid = ObjectId(file_id) if isinstance(file_id, str) else file_id
    bucket = _bucket()
    grid_out = await bucket.open_download_stream(fid)
    return await grid_out.read()


async def exists(file_id: ObjectId | str) -> bool:
    fid = ObjectId(file_id) if isinstance(file_id, str) else file_id
    db = get_db()
    return (await db[f"{GRIDFS_PREFIX}.files"].find_one({"_id": fid})) is not None
