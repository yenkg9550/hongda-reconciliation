# Deprecated — 本專案已改用 S3（見 app/core/s3_storage.py）。
raise ImportError(
    "app.core.storage 已棄用，請改用 app.core.s3_storage（AWS S3 + boto3）"
)
