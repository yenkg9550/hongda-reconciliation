# 備用：若你想用 Docker 部署（Fly.io / Railway / 自架 EC2），可用這支 Dockerfile。
# Render 用 Python runtime 直接跑，不需要這支。
FROM python:3.11-slim

WORKDIR /app

# 系統相依（pymongo SRV 需 dnspython 已在 requirements，無需 apt 套件）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
