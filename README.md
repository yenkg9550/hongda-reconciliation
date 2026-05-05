# 宏達停車場對帳系統 — 後端

FastAPI + **MongoDB Atlas** + **GridFS**（檔案存 Mongo，不依賴 S3）。
所有 endpoint 已可呼叫，檔案上傳會落地到 GridFS，M1/M2/M3 查詢與報表匯出會讀取 MongoDB collections。

---

## 0. TL;DR

```bash
# 本機開發
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填 MONGODB_URI（Atlas 字串）
python -m app.seed    # 種入示範資料
uvicorn app.main:app --reload
# → http://localhost:8000/api/v1/docs

# 部署到 Render
git push           # render.yaml 會自動拉，依下方教學設好 env vars
```

> 沒裝 Mongo？把 `.env` 加 `USE_INMEMORY_FALLBACK=true` 就會用 mongomock。
> 注意：mongomock 不支援 GridFS（檔案上傳會失敗），其他端點都能跑。

---

## 1. 環境變數一覽

| 變數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| `MONGODB_URI` | ✅ | `mongodb://localhost:27017` | Atlas 連線字串 |
| `MONGODB_DB` | ✅ | `reconciliation` | DB 名稱 |
| `CORS_ORIGINS` | ✅ | `http://localhost:5173` | 用逗號分隔多個 origin |
| `API_V1_PREFIX` | | `/api/v1` | 路由前綴 |
| `APP_ENV` | | `development` | |
| `WORKER_INTERVAL_SECONDS` | | `5` | Worker 輪詢間隔 |
| `USE_INMEMORY_FALLBACK` | | `false` | 開發/CI 用 mongomock |

`.env.example` 是範本，本機開發時 `cp .env.example .env` 後填值即可。

---

## 2. 端點清單

對應 `docs/API文件.md` v0.3.1：

| Method | Endpoint | 說明 |
| ------ | -------- | ---- |
| `POST` | `/api/v1/uploads` | 接收檔案、SHA-256 查重、寫入 GridFS、建立 upload_jobs |
| `DELETE` | `/api/v1/uploads/{job_id}` | 刪除（含 GridFS 檔案） |
| `GET` | `/api/v1/upload-status?period=YYYY-MM` | 動態彙總 17 個 slot |
| `GET` | `/api/v1/jobs` | 分頁列出所有 job |
| `GET` | `/api/v1/jobs/{job_id}` | 單筆狀態（FE polling 用） |
| `POST` | `/api/v1/jobs/{job_id}/retry` | 失敗的 job 排入重試 |
| `GET` | `/api/v1/jobs/{job_id}/issues` | 解析錯誤明細 |
| `POST` | `/api/v1/reconcile/m1\|m2\|m3` | 觸發對帳作業（骨架：直接 done） |
| `GET` | `/api/v1/reconcile/m1\|m2\|m3` | 對帳結果 |
| `GET` | `/api/v1/reconcile/m3/{id}` | 例外明細 |
| `PATCH` | `/api/v1/reconcile/m3/{id}` | 標記例外為已處理 |
| `GET\|POST\|PUT` | `/api/v1/venues` | 場站 CRUD |
| `GET\|PUT` | `/api/v1/rates`, `/api/v1/mappings` | 費率、對照表 |
| `GET` | `/api/v1/reports/{m1\|m2\|m3}/export` | xlsx 匯出 |

[OpenAPI 文件](http://localhost:8000/api/v1/docs) 可直接互動測試。

---

## 3. 目錄結構

```
backend/
├── app/
│   ├── main.py                      # FastAPI 入口（含 lifespan / CORS / 例外處理）
│   ├── core/
│   │   └── config.py                # pydantic-settings 環境設定
│   ├── db/
│   │   ├── mongo.py                 # motor client + ping + 自動 fallback
│   │   ├── collections.py           # collection 名稱 + 索引規格
│   │   └── gridfs.py                # GridFS 上傳/刪除/讀取
│   ├── schemas/                     # Pydantic envelope + 請求/回應模型
│   ├── routers/                     # uploads/jobs/reconcile/master/reports
│   ├── services/
│   │   ├── slot_config.py           # 17 個 slot 定義
│   │   ├── upload_service.py        # 接檔案 + 查重 + 落 GridFS
│   │   ├── upload_status_service.py # 組裝 GET /upload-status
│   │   └── reconcile_service.py     # 對帳 job + MongoDB 結果查詢
│   ├── worker.py                    # 背景 worker（輪詢 queued → 模擬解析）
│   └── seed.py                      # 12 場站 + 5 種費率示範資料
├── render.yaml                      # Render Blueprint
├── Dockerfile                       # 備用（Fly.io / Railway）
├── Procfile                         # 備用（Railway / Heroku）
├── runtime.txt                      # Render 指定 Python 版本
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

# 4. 部署到 Render（從零開始的步驟）

整個流程約 30 分鐘，**完全免費**。

## Step 1 — 準備 MongoDB Atlas（5 分鐘，免費）

1. 到 [https://www.mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register) 註冊
2. 建立一個 **M0 (Free)** cluster，地區選 `AWS / Tokyo (ap-northeast-1)` 或 `Singapore`
3. 進入 cluster 後依序：
   - 左側 **Database Access** → Add New Database User
     - Username/password 自己取，**密碼勿用 `@` `:` `/`**（要塞進 URI）
     - Privileges 選 `Read and write to any database`
   - 左側 **Network Access** → Add IP Address
     - 選 `Allow Access from Anywhere`（`0.0.0.0/0`）
     - Production 建議改成 Render 的 outbound IP，但 demo 階段先全開
4. 回到 cluster 主畫面，點 **Connect** → **Drivers** → 複製連線字串：

   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

   記得把 `<password>` 換成你剛剛設的密碼。

## Step 2 — 把專案推到 GitHub

```bash
cd /path/to/twi_hongda_reconciliation
git add backend/
git commit -m "feat: backend skeleton (MongoDB + GridFS)"
git push origin main
```

## Step 3 — 部署到 Render（10 分鐘，免費）

1. 到 [https://render.com](https://render.com) 用 GitHub 帳號登入
2. 右上角 **New +** → **Blueprint**
3. 選你的 repo → Render 會自動讀 `backend/render.yaml`
4. 服務出來後，**Environment** 分頁設定 secrets：

   | Key | Value |
   | --- | --- |
   | `MONGODB_URI` | Step 1 複製的字串 |
   | `CORS_ORIGINS` | 你的前端網址，例如 `https://my-frontend.netlify.app`。本機調試先填 `http://localhost:5173,http://localhost:4173` |

5. 第一次建好後會自動 build。等到狀態顯示綠色 **Live**，url 大概長：

   ```
   https://hongda-reconciliation-api.onrender.com
   ```

6. 開 `https://hongda-reconciliation-api.onrender.com/api/v1/docs` 看 OpenAPI 文件。
   開 `https://hongda-reconciliation-api.onrender.com/` 看 mongo 連線是否 OK。

## Step 4 — Seed 一次（一次性）

Render free tier 沒有 SSH，但可以用 Render Shell（Pro 才有），或臨時加一個 endpoint。
最簡單：本機 `cp .env.example .env`，把 `MONGODB_URI` 填上 Step 1 的 Atlas URI，然後跑：

```bash
cd backend
python -m app.seed   # 連到 Atlas、寫入 12 場站 + 5 費率
```

之後 Render 上的 API 立即看得到（同一個 DB）。

> Render free 方案會在 15 分鐘無流量後 sleep，下次請求要 30~60 秒喚醒。Demo 夠用，正式上線記得升 paid。

---

# 5. 前端串接教學

## Step 5.1 — 前端 API 設定

前端已內建 `frontend/src/api/http.js`，開發環境預設 `VITE_USE_MOCK=false` 並會串 `VITE_API_BASE`。本機後端請設定：

```bash
VITE_USE_MOCK=false
VITE_API_BASE=http://localhost:8000/api/v1
```

> 小細節：Render free 第一次喚醒會慢，可以加一個 axios interceptor 在 401/503 時 retry。

## Step 5.2 — 設定 baseURL

在 `frontend/.env.development`：

```
VITE_API_BASE=http://localhost:8000/api/v1
```

`frontend/.env.production`：

```
VITE_API_BASE=https://hongda-reconciliation-api.onrender.com/api/v1
```

跑 `npm run dev` 會吃 development，`npm run build` 會吃 production。

## Step 5.3 — 後端 CORS 要放行

到 Render 的環境變數把 `CORS_ORIGINS` 改成包含你的前端網址（多個用逗號）：

```
CORS_ORIGINS=http://localhost:5173,https://my-frontend.netlify.app
```

設完後 Render 會自動重新部署。

## Step 5.4 — 前端跑起來測試

```bash
cd frontend
npm install
npm run dev
```

開 `http://localhost:5173`，應該能看到：

- Screen A 月份 = 2026/03，缺件 16 項（因為 Atlas 上沒 upload 紀錄）
- 點「進入補齊檔案中心」，每個 slot 都可以上傳真檔（會落到 Atlas GridFS）
- 上傳完到 `https://...onrender.com/api/v1/upload-status?period=2026-03` 可以看到狀態變化

---

# 6. 常見坑

| 症狀 | 原因 | 解法 |
| --- | --- | --- |
| Render build 失敗：`module 'lib' has no attribute 'X509_V_FLAG_NOTIFY_POLICY'` | `pyOpenSSL` 太舊 | 在 `requirements.txt` 加 `pyopenssl>=23.2` |
| 前端 console 報 CORS error | `CORS_ORIGINS` 沒包含你的網址 | 到 Render env 改 `CORS_ORIGINS` |
| Atlas 連不上 | IP whitelist 或密碼有特殊字元 | Network Access 改 `0.0.0.0/0`；密碼改純英數 |
| `pymongo.errors.ServerSelectionTimeoutError` | 連線字串拼錯，或 cluster paused | Atlas dashboard 看 cluster 狀態 |
| Render free 第一次請求慢 | 15 分鐘無流量會 sleep | 加 cron 每 10 分鐘 ping `/`，或升 paid |
| 上傳大檔案失敗 | GridFS 16MB chunk 沒問題，但 Render free 有 100MB body limit | 大檔請改 chunk upload，或升 paid |

---

# 7. Stage 2/3 接入點

| 要做的事 | 檔案 | 現況 |
| -------- | ---- | ---- |
| 各家 Parser | 新增 `app/parsers/vendors/*.py` 等 | 未實作 |
| Parser 接 worker | `app/worker.py` 的 `_process_one` | 目前直接標 done/failed |
| M1 引擎 | 新增 `app/engine/m1_electronic.py` | `reconcile_service.trigger_reconcile` 留接口 |
| M2 引擎 | 新增 `app/engine/m2_cash.py` | 同上 |
| M3 引擎 | 新增 `app/engine/m3_exception.py` | 同上 |
| 真實 issues | 新 collection `job_issues`，補進 `/jobs/{id}/issues` | 目前以 error_msg 偽裝 |

---

# 8. 棄用檔案

下列檔案是早期 SQLAlchemy + S3 版本的殘留，已改 raise ImportError。
不會被任何模組 import，只是因為掛載卷無法直接刪除而保留：

- `app/core/database.py`、`app/core/storage.py`、`app/core/s3_storage.py`
- `app/models/*.py`（SQLAlchemy ORM）
- `alembic/`、`alembic.ini`

可以放心刪掉。
