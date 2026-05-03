# Deprecated — 本專案已改用 MongoDB（見 app/db/mongo.py）。
# 此檔保留是因為掛載卷無法刪除。
raise ImportError(
    "app.core.database 已棄用，請改用 app.db.mongo（MongoDB Atlas + motor）"
)
