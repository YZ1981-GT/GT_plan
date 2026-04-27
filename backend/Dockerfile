# ============================================================
# 审计作业平台 — FastAPI 后端
# 基础镜像: python:3.12-slim-bookworm (稳定版本)
# ============================================================

FROM python:3.12-slim

# 禁用代理
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV http_proxy=
ENV https_proxy=
ENV HTTP_PROXY=
ENV HTTPS_PROXY=

# 系统依赖（curl 用于健康检查，fonts-wqy-zenhei 中文字体）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 复制仿宋_GB2312字体（如果可用）
COPY fonts/FangSong_GB2312.ttf /usr/share/fonts/truetype/fangsong/ 2>/dev/null || true
RUN fc-cache -fv 2>/dev/null || true

WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --default-timeout=300

# 复制应用代码
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
