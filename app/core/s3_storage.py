# Deprecated — 本專案已改用 MongoDB GridFS（見 app/db/gridfs.py）。
# 保留此檔僅為避免歷史 import 失敗。
raise ImportError(
    "app.core.s3_storage 已棄用，請改用 app.db.gridfs"
)
