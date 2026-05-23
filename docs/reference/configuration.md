# 配置中心参考文档（CONFIGURATION_REFERENCE）

> [proposal-remaining-18 / MT-9 / 任务 5.8] — 列出全平台所有可配置项，覆盖：①后端 `backend/app/core/config.py`（pydantic-settings）②项目根 `.env` / `backend/.env`（环境变量覆盖）③前端 `audit-platform/frontend/.env`（Vite `VITE_*`）④少量未走 `Settings` 的 `os.environ.get(...)` 直读项。
>
> **最后更新**：2026-05-22  · **维护**：每次新增配置项时同步更新本文档（建议加 pre-commit 校验，见末尾"防漂移脚本"）。
>
> **修改方式说明**：
> - **重启生效**：`Settings()` 一次加载（FastAPI 启动时实例化 `settings`），改完需重启后端进程。占绝大多数项。
> - **运行时生效**：少数 `os.environ.get(...)` 在每次调用时读取（如 `LEDGER_IMPORT_MAX_CONCURRENT` / `LOG_FILE_PATH` 在 router 内显式读取），改完无需重启。
> - **前端**：`VITE_*` 在 `vite build` / `vite dev` 启动时注入，改完需重启 dev server 或重新打包。

---

## 目录

1. [后端核心（数据库 / Redis / JWT / CORS）](#1-后端核心)
2. [LLM 与 AI 服务](#2-llm-与-ai-服务)
3. [文件存储 / 附件 / 云端归档](#3-文件存储--附件--云端归档)
4. [OCR 与 MinerU](#4-ocr-与-mineru)
5. [外部服务（ONLYOFFICE / Paperless / ChromaDB）](#5-外部服务)
6. [性能 / 并发 / 上传限制](#6-性能--并发--上传限制)
7. [安全（密钥校验 / RLS / 病毒扫描 / 独立性宽容期）](#7-安全)
8. [前端 Vite 环境变量](#8-前端-vite-环境变量)
9. [日志（结构化 JSON / 文件轮转 / admin 查看面板）](#9-日志)
10. [备份 / 迁移 / 归档 / 数据清理](#10-备份--迁移--归档--数据清理)
11. [账表导入（Ledger Import）专项](#11-账表导入专项)
12. [Docker Compose 部署变量](#12-docker-compose-部署变量)
13. [防漂移校验脚本](#13-防漂移校验脚本)

---

## 1. 后端核心

### 1.1 数据库（PostgreSQL）

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform` | str | 后端全局 ORM 连接；启动时按前缀（`postgresql+asyncpg` / `sqlite+aiosqlite`）选择驱动；`backend/scripts/*.py` 多数也读取此值 | 生产环境强密码；6000 并发必用 PostgreSQL，**禁用 SQLite** | 重启 |
| `DB_POOL_SIZE` | `50` | int | SQLAlchemy 连接池常驻连接数（6000 并发优化基线） | 生产 ≥ 50；开发 20 即可 | 重启 |
| `DB_MAX_OVERFLOW` | `100` | int | 连接池峰值溢出连接数；`pool_size + max_overflow = 总上限` | 生产 ≥ 100；开发 80 即可 | 重启 |

### 1.2 Redis（缓存 / Worker 心跳 / 限流 / Sentinel HA）

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `REDIS_URL` | `redis://localhost:6379/0` | str | 缓存（TB 60s TTL / prefill 5min TTL）/ 限流 / SLA worker 幂等去重 / Outbox 事件重放 | 生产指向独立 Redis 实例 | 重启 |
| `REDIS_MODE` | `single`（兼容值 `standalone`） | str | `single` 直连 `REDIS_URL`；`sentinel` 走哨兵故障转移 | 单机 `single`；HA 部署 `sentinel` | 重启 |
| `REDIS_SENTINEL_HOSTS` | `localhost:26379,localhost:26380,localhost:26381` | str（逗号分隔） | Sentinel 哨兵节点列表（仅 `REDIS_MODE=sentinel` 生效） | 至少 3 节点保证仲裁 | 重启 |
| `REDIS_SENTINEL_SERVICE` | `mymaster` | str | Sentinel 监控的主节点 service name | 与 `sentinel.conf` 一致 | 重启 |

### 1.3 JWT 认证

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `JWT_SECRET_KEY` | `dev-secret-key-change-in-production` | str | 所有 access / refresh token 签名；改后旧 token 全部失效 | **生产必填**；`openssl rand -hex 32`（≥ 16 字符且非弱密钥列表，否则 `APP_ENV=production` 启动报错） | 重启 |
| `JWT_ALGORITHM` | `HS256` | str | 签名算法 | `HS256` 即可；如换为 `RS256` 需配套公私钥 | 重启 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | int | Access token 有效期（Phase 5 SC-4 由 120 缩短到 30 分钟） | 生产 30；开发可放宽 120 | 重启 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | int | Refresh token 有效期 | 7 天 | 重启 |
| `LOGIN_MAX_ATTEMPTS` | `5` | int | 登录连续失败上限（超过锁定） | 5 | 重启 |
| `LOGIN_LOCK_MINUTES` | `30` | int | 登录失败锁定时长（分钟） | 30 | 重启 |
| `BCRYPT_ROUNDS` | `12` | int | bcrypt 哈希 cost factor（OWASP 推荐 12） | 12（高安全 14） | 重启 |

### 1.4 CORS 与运行环境

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3030` | str（逗号分隔） | FastAPI CORSMiddleware 白名单 | 生产改为正式域名，禁用 `*` | 重启 |
| `APP_ENV` | `dev` | str | `dev` / `staging` / `production`；`production` 模式下 `JWT_SECRET_KEY` 弱密钥校验失败将启动报错（Q5 安全门禁） | 生产环境必设 `production` | 重启 |

---

## 2. LLM 与 AI 服务

### 2.1 vLLM（本地大模型，OpenAI 兼容 API）

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `LLM_BASE_URL` | `http://localhost:8100/v1` | str | OpenAI 兼容 API 入口；前缀 `v1` 必带 | 容器内用 `http://vllm:8000/v1` | 重启 |
| `LLM_API_KEY` | `not-needed` | str | vLLM 本地不校验，可留默认；接入 OpenAI / 商业 API 时填真实 key | 视服务而定 | 重启 |
| `DEFAULT_CHAT_MODEL` | `Kbenkhaled/Qwen3.5-27B-NVFP4` | str | LLMService 默认 chat 模型 ID（必须为 vLLM 已加载） | 与 `VLLM_MODEL` 保持一致 | 重启 |
| `DEFAULT_EMBEDDING_MODEL` | `Kbenkhaled/Qwen3.5-27B-NVFP4` | str | 嵌入模型 ID（当前与 chat 共用） | 实际部署独立 embedding 模型 | 重启 |
| `LLM_TEMPERATURE` | `0.3` | float | 默认采样温度 | 审计场景 0.1~0.3（确定性优先） | 重启 |
| `LLM_MAX_TOKENS` | `4096` | int | 单次响应最大 token | 4096~8192；Qwen3.5-27B 支持 32K 上下文 | 重启 |
| `LLM_ENABLE_THINKING` | `False` | bool | Qwen3.5 thinking 模式（COT 显式输出）；审计场景默认关闭 | 默认 `False` | 重启 |
| `LLM_RATE_LIMIT_PER_MINUTE` | `10` | int | 每用户每分钟 LLM 调用上限 | 10（防止单用户耗尽） | 重启 |
| `WP_AI_SERVICE_ENABLED` | `False` | bool | 6 个 LLM stub 引擎（H 减值 / I 商誉 / G 公允价值 / K 费用异常 / J 股份支付 / N 递延所得税）的 `is_llm_stub` 标志开关；`False` 时 API 返回 stub 提示 | vLLM 上线 + prompt 调优后改 `True` | 重启 |

### 2.2 备用 / 周边

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | str | vLLM 不可用时降级备用（当前未自动切换，预留） | 视部署 | 重启 |
| `CHROMADB_URL` | `http://localhost:8000` | str | ChromaDB 向量库（RAG 知识库使用） | 容器内 `http://chromadb:8000` | 重启 |

---

## 3. 文件存储 / 附件 / 云端归档

### 3.1 本地存储

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `STORAGE_ROOT` | `./storage` | str | 全局文件存储根；多个 service 直接 `os.environ.get` 读取（如 `private_storage_service` / `word_template_filler` / `cloud_storage_service`） | 绝对路径优先；磁盘空间充足挂载 | **混合**：`Settings` 重启生效 / 部分 service 读 `os.environ` 也是启动一次性 |

### 3.2 附件（Paperless / 本地回退）

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `ATTACHMENT_PRIMARY_STORAGE` | `paperless` | str | 主存储后端：`paperless` / `local` | `paperless`（生产）/ `local`（轻量） | 重启 |
| `ATTACHMENT_FALLBACK_TO_LOCAL` | `True` | bool | Paperless 不可达时回退本地 | `True` 提升可用性 | 重启 |
| `ATTACHMENT_LOCAL_STORAGE_ROOT` | `./storage/attachments` | str | 本地附件根目录 | 同 `STORAGE_ROOT` 同盘 | 重启 |
| `PAPERLESS_URL` | `""` | str | Paperless-ngx API 入口 | 部署后填实际地址 | 重启 |
| `PAPERLESS_TOKEN` | `""` | str | Paperless API token | 不入 git；用 secret manager | 重启 |
| `PAPERLESS_TIMEOUT` | `30` | int | 请求超时秒数 | 30 | 重启 |

### 3.3 云端归档（事务所内部服务器）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `CLOUD_STORAGE_TYPE` | `local` | str | `sftp` / `s3` / `smb` / `local`（测试模式） | 重启 |
| `CLOUD_SFTP_HOST` / `CLOUD_SFTP_PORT` / `CLOUD_SFTP_USER` / `CLOUD_SFTP_PASSWORD` / `CLOUD_SFTP_KEY_PATH` / `CLOUD_SFTP_BASE_PATH` | `192.168.1.100` / `22` / `audit_archive` / `""` / `""` / `/archive/audit` | str/int | SFTP 模式（事务所内部文件服务器） | 重启 |
| `CLOUD_S3_ENDPOINT` / `CLOUD_S3_ACCESS_KEY` / `CLOUD_S3_SECRET_KEY` / `CLOUD_S3_BUCKET` / `CLOUD_S3_REGION` | `http://192.168.1.100:9000` / `""` / `""` / `audit-archive` / `""` | str | S3 兼容（MinIO / OSS / 内部对象存储） | 重启 |
| `CLOUD_SMB_SERVER` / `CLOUD_SMB_USER` / `CLOUD_SMB_PASSWORD` | `\\\\192.168.1.100\\archive` / `""` / `""` | str | Windows 共享 | 重启 |
| `CLOUD_LOCAL_PATH` | `archive_cloud` | str | 本地归档目录（测试用） | 重启 |
| `CLOUD_SYNC_ON_UPLOAD` | `true` | bool | 上传时是否双写云端 | 重启 |

> 📌 **实现说明**：以上 `CLOUD_*` 全部走 `cloud_storage_service.py` 模块级 `os.environ.get`，模块导入时一次性读取，与 `Settings` 重启生效语义等价。

---

## 4. OCR 与 MinerU

### 4.1 OCR 引擎选择

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `OCR_DEFAULT_ENGINE` | `auto` | str | `auto` / `paddle` / `tesseract` | 重启 |
| `OCR_PADDLE_ENABLED` | `True` | bool | PaddleOCR 启用开关 | 重启 |
| `OCR_TESSERACT_ENABLED` | `True` | bool | Tesseract 启用开关 | 重启 |
| `OCR_TESSERACT_LANG` | `chi_sim+eng` | str | Tesseract 语言包（简中+英文） | 重启 |
| `OCR_CONFIDENCE_THRESHOLD` | `0.8` | float | 识别置信度阈值（低于此值标"低置信"） | 重启 |

### 4.2 MinerU（GPU 文档解析）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `MINERU_ENABLED` | `False` | bool | 主开关；需 GPU 支持 | 重启 |
| `MINERU_API_URL` | `http://localhost:8000` | str | HTTP 模式 API 入口 | 重启 |
| `MINERU_USE_CLI` | `True` | bool | `True` 调用本地 `mineru` 命令；`False` 走 HTTP | 重启 |

---

## 5. 外部服务

### 5.1 ONLYOFFICE（向后兼容，底稿编辑已迁移至 Univer）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `ONLYOFFICE_URL` | `http://onlyoffice:80` | str | ONLYOFFICE Document Server 地址 | 重启 |
| `WOPI_BASE_URL` | `http://backend:8000/wopi` | str | WOPI Host 基础地址 | 重启 |

### 5.2 Office 在线预览（LibreOffice 转 PDF）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `OFFICE_PREVIEW_CACHE_DIR` | `<repo>/storage/office_preview_cache` | str | Office 文件转 PDF 后的缓存目录（`office_preview.py` 显式 `os.environ.get`） | **运行时**（每次请求都读） |

---

## 6. 性能 / 并发 / 上传限制

### 6.1 上传 / 请求体大小

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `MAX_UPLOAD_SIZE_MB` | `800` | int | 单个上传文件大小上限（MB） | 重启 |
| `MAX_REQUEST_BODY_MB` | `850` | int | 全局请求体上限（略大于 `MAX_UPLOAD_SIZE_MB` 容纳 multipart 开销） | 重启 |

### 6.2 事件总线 / 公式引擎（Phase 8）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `EVENT_DEBOUNCE_MS` | `500` | int | 事件总线去重窗口（毫秒） | 重启 |
| `FORMULA_EXECUTE_TIMEOUT` | `10` | int | 单次公式执行超时（秒） | 重启 |

### 6.3 并发治理（运行时读）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `LEDGER_IMPORT_MAX_CONCURRENT` | `3` | int | 账表导入全局并发上限（`global_concurrency.py` 每次调用都重读，便于测试 monkeypatch） | **运行时** |

---

## 7. 安全

### 7.1 加密 / 密钥

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `ENCRYPTION_KEY` | `""` | str | Phase 8 数据加密密钥（敏感字段加密存储） | `openssl rand -hex 32`；不入 git | 重启 |

### 7.2 ClamAV 病毒扫描（SC-3）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `CLAMAV_ENABLED` | `False` | bool | 附件上传病毒扫描开关 | 重启 |
| `CLAMAV_HOST` | `localhost` | str | clamd 主机 | 重启 |
| `CLAMAV_PORT` | `3310` | int | clamd 端口 | 重启 |

### 7.3 独立性声明 legacy 宽容期（R6+）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `INDEPENDENCE_LEGACY_CUTOFF_DATE` | `2026-05-05` | str（YYYY-MM-DD） | 早于此日期创建的项目进入 legacy 宽容期；空字符串 = 无宽容期 | 重启 |
| `INDEPENDENCE_LEGACY_GRACE_ENABLED` | `True` | bool | 全局宽容期总开关；老项目升级完毕后置 `False` 彻底下线 | 重启 |

> 📌 **PG RLS / RBAC** 由数据库迁移 `V005__enable_rls.sql` 与 `deps.py` 的 `set_rls_context()` 实现，不通过环境变量配置（`security_definer` 函数 + project_isolation policy）。

---

## 8. 前端 Vite 环境变量

文件：`audit-platform/frontend/.env`（生产构建时使用 `.env.production`）

| 变量名 | 默认值 | 类型 | 影响范围 | 推荐值 | 修改方式 |
|--------|--------|------|----------|--------|----------|
| `VITE_API_BASE_URL` | `http://localhost:9980` | str | `vite.config.ts` proxy `/api` + `/wopi` 转发目标 | 容器内 `http://backend:8000`；生产域名 `https://api.audit.example.com` | 重启 dev / 重新打包 |
| `VITE_DEV_PORT` | `3030` | str（解析为 int） | Vite dev server 监听端口；`strictPort: false`（占用时自动+1） | 与 `start-dev.bat` 一致 | 重启 dev |

> 📌 **实现说明**：当前 `src/**` 中无 `import.meta.env.VITE_*` 直接引用，仅 `vite.config.ts` 读取这两个变量构造 dev proxy（前端调用走同源 `/api`，由 proxy 转发到后端）。如需运行时切换 API 地址，可将 `VITE_API_BASE_URL` 通过 `import.meta.env` 注入到 `apiProxy.ts`。

---

## 9. 日志

### 9.1 结构化 JSON + 文件轮转

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `LOG_FILE_PATH` | `logs/app.jsonl`（`DEFAULT_LOG_FILE_PATH`） | str | JSON 日志文件路径；空字符串 `""` = 禁用文件 handler；`unset` = 默认路径 | **运行时**（`logs_viewer` 每次请求都重读） |

**日志格式**：JSONL，每行一条 `{"timestamp", "level", "logger", "message", "request_id", "exception"?}`。
**轮转策略**：`TimedRotatingFileHandler(when="midnight", backupCount=14)`（按日轮转，保留 14 天）。
**`enable_file_handler` 参数**：`setup_logging(enable_file_handler=False)` 可在测试中关闭文件 handler；不通过 env 控制。

### 9.2 日志查看面板（admin）

`SystemSettings → 日志查看 Tab`（admin / partner only）→ 路由 `GET /api/system/logs/view`，从 `LOG_FILE_PATH` 读取最近 N 行。

---

## 10. 备份 / 迁移 / 归档 / 数据清理

### 10.1 备份脚本（`backend/scripts/backup.py`）

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `BACKUP_DIR` | `backups` | str | 备份输出目录 | 运行时（脚本启动时读） |
| `BACKUP_RETENTION_DAYS` | `30` | int | 旧备份保留天数 | 运行时 |

### 10.2 迁移 Runner（`backend/app/core/migration_runner.py`）

无独立 env 变量；`migration_runner.py --rollback / --confirm` CLI 模式调用，读取 `DATABASE_URL`。
迁移文件位于 `migrations/V*.sql`（V001~V012 全部已上线，对应回滚 R001~R012）。

### 10.3 数据清理 / Worker

| 变量名 | 默认值 | 类型 | 影响范围 | 修改方式 |
|--------|--------|------|----------|----------|
| `LEDGER_PURGE_KEEP_COUNT` | `10` | int | `dataset_purge_worker` 保留最近 N 个数据集 | 运行时（worker 每轮重读） |
| `LEDGER_IMPORT_EXPECTED_WORKERS` | `1` | int | 健康检查期望的 worker 数（少于此值告警） | 运行时 |
| `LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_ENABLED` | `True` | bool | 事件消费记录清理总开关 | 重启 |
| `LEDGER_IMPORT_EVENT_CONSUMPTION_RETENTION_DAYS` | `180` | int | 事件消费记录保留天数 | 重启 |
| `LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_INTERVAL_SECONDS` | `3600` | int | 清理任务执行间隔（秒） | 重启 |
| `LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_BATCH_SIZE` | `5000` | int | 单次清理批次大小 | 重启 |

---

## 11. 账表导入专项

> 配置项较多（22 个），单独成节。完整文档见 `docs/architecture/ledger-import-v2.md`。

| 变量名 | 默认值 | 类型 | 说明 |
|--------|--------|------|------|
| `LEDGER_UPLOAD_STORAGE_ROOT` | `./storage/ledger_uploads` | str | 上传暂存目录 |
| `LEDGER_UPLOAD_TTL_HOURS` | `24` | int | 上传文件保留时长（小时） |
| `LEDGER_UPLOAD_MAX_FILE_COUNT` | `20` | int | 单次上传最大文件数 |
| `LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB` | `1024` | int | 单次上传总大小上限（MB），支持 432MB+ 大 CSV 场景 |
| `LEDGER_ARTIFACT_STORAGE_BACKEND` | `local` | str | `local` / `s3` |
| `LEDGER_ARTIFACT_S3_ENDPOINT_URL` | `""` | str | S3 兼容端点 URL |
| `LEDGER_ARTIFACT_S3_REGION` | `us-east-1` | str | S3 region |
| `LEDGER_ARTIFACT_S3_BUCKET` | `""` | str | S3 bucket 名 |
| `LEDGER_ARTIFACT_S3_PREFIX` | `ledger-import` | str | S3 对象 key 前缀 |
| `LEDGER_ARTIFACT_S3_ACCESS_KEY_ID` | `""` | str | S3 access key |
| `LEDGER_ARTIFACT_S3_SECRET_ACCESS_KEY` | `""` | str | S3 secret key |
| `LEDGER_ARTIFACT_S3_USE_SSL` | `True` | bool | S3 强制 HTTPS |
| `LEDGER_ARTIFACT_DOWNLOAD_ROOT` | `./storage/ledger_artifact_cache` | str | S3 下载缓存目录 |
| `LEDGER_ARTIFACT_STORAGE_FAILURE_MODE` | `""` | str | 故障注入：`timeout` / `readonly` / `unavailable`（仅测试用） |
| `LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD` | `0.85` | float | 列识别置信度 ≥ 此值自动应用 |
| `LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED` | `True` | bool | 进程内 runner 开关（vs 独立 worker） |
| `LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS` | `30` | int | Worker 轮询间隔 |
| `LEDGER_IMPORT_WORKER_BATCH_SIZE` | `3` | int | Worker 单批处理任务数 |
| `LEDGER_IMPORT_FULL_MODE_MAX_FILE_MB` | `30` | int（≥1） | 完整模式（vs 流式）的单文件大小阈值 |
| `LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED` | `True` | bool | 事件 outbox 重放总开关 |
| `LEDGER_IMPORT_OUTBOX_REPLAY_INTERVAL_SECONDS` | `30` | int | 重放轮询间隔 |
| `LEDGER_IMPORT_OUTBOX_REPLAY_MAX_BACKOFF_SECONDS` | `300` | int | 重试退避上限（秒） |
| `LEDGER_IMPORT_OUTBOX_REPLAY_JITTER_RATIO` | `0.2` | float | 退避抖动比例 |
| `LEDGER_IMPORT_OUTBOX_REPLAY_LIMIT` | `100` | int | 单轮重放上限 |
| `LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS` | `20` | int | 单事件最大重试次数 |
| `LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD` | `0.05`（≥0.0,≤1.0）| float | 失败率告警阈值 |
| `LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD` | `0.02`（≥0.0,≤1.0）| float | 超时率严重告警阈值 |
| `LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD` | `1800`（≥1）| int | P95 处理时长告警阈值（秒） |
| `LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD` | `300`（≥1）| int | 队列延迟 P95 告警阈值（秒） |
| `LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD` | `20`（≥1）| int | Outbox 积压告警阈值 |
| `LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD` | `10`（≥1）| int | 活跃任务数告警阈值 |

---

## 12. Docker Compose 部署变量

文件：项目根 `.env`（被 `docker-compose.yml` 通过 `${VAR:-default}` 引用）。

### 12.1 PostgreSQL / Redis / 后端 / ONLYOFFICE 端口

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `PG_USER` / `PG_PASSWORD` / `PG_DB` / `PG_PORT` | `postgres` / `postgres` / `audit_platform` / `5432` | PG 容器初始化 |
| `REDIS_PORT` | `6379` | Redis 对外端口 |
| `API_PORT` | `8000`（生产）/ `9980`（本地开发） | 后端对外端口 |
| `OFFICE_PORT` | `8080` | ONLYOFFICE 对外端口 |

### 12.2 vLLM 容器

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `VLLM_PORT` | `8100` | vLLM 对外端口 |
| `VLLM_HF_CACHE` | `D:/vllm/hf-cache` | HuggingFace 缓存目录（host 挂载） |
| `VLLM_MODEL` | `Kbenkhaled/Qwen3.5-27B-NVFP4` | 模型 ID（HF） |
| `VLLM_MODEL_NAME` | `qwen3.5-27b` | API 调用时使用的模型名 |
| `VLLM_MAX_MODEL_LEN` | `32768` | 最大上下文长度 |
| `VLLM_GPU_MEM` | `0.89` | GPU 显存利用率 |
| `NVFP4_BACKEND` | `marlin` | NVFP4 GEMM 后端：`marlin`（解码快）或 `flashinfer-cutlass`（预填充快） |
| `HF_TOKEN` | `""` | HuggingFace Token（模型已离线缓存通常不需要） |

### 12.3 路径覆盖（业务）

| 变量名 | 默认值 | 影响范围 |
|--------|--------|----------|
| `TSJ_PROMPT_DIR` | unset → 自动查找 `<repo>/TSJ` | `workpaper_fill_service` 加载审计复核提示词 |
| `TSJ_KNOWLEDGE_DIR` | unset → 自动查找 `<repo>/TSJ` | `knowledge_tsj` router 提供"准则"侧栏 |
| `CROSS_WP_REF_PATH` | unset → `backend/data/cross_wp_references.json` | `cross_cycle_breakage_service` 加载跨底稿引用 |
| `LINKAGE_PANORAMA_CWR_PATH` | unset → 同上 | `linkage_panorama` router |
| `VR_RULES_DATA_DIR` | unset → `backend/data/` | `vr_coverage` router |

> 以上路径覆盖项均为 `os.environ.get`，模块导入时一次读取，重启生效。

---

## 13. 防漂移校验脚本

为防止本文档与 `config.py` 实际声明项漂移，提供一个简单的 grep 校验脚本（一次性使用，不入仓库；用完即删）：

```python
# scripts/_check_config_doc_drift.py（一次性，用完即删）
import re
from pathlib import Path

DOC = Path("docs/reference/configuration.md").read_text(encoding="utf-8")
CFG = Path("backend/app/core/config.py").read_text(encoding="utf-8")

# 提取 config.py 中所有大写变量声明（pydantic Settings 字段）
cfg_vars = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]+)\s*[:=]", CFG, re.MULTILINE))

# 提取 doc 中反引号包裹的全大写变量
doc_vars = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", DOC))

missing_in_doc = sorted(cfg_vars - doc_vars)
extra_in_doc = sorted(doc_vars - cfg_vars - {
    # 白名单：来自其他来源（os.environ / .env / docker-compose / Vite）
    "VITE_API_BASE_URL", "VITE_DEV_PORT",
    "PG_USER", "PG_PASSWORD", "PG_DB", "PG_PORT",
    "REDIS_PORT", "API_PORT", "OFFICE_PORT",
    "VLLM_PORT", "VLLM_HF_CACHE", "VLLM_MODEL", "VLLM_MODEL_NAME",
    "VLLM_MAX_MODEL_LEN", "VLLM_GPU_MEM", "NVFP4_BACKEND", "HF_TOKEN",
    "CLOUD_STORAGE_TYPE", "CLOUD_SFTP_HOST", "CLOUD_SFTP_PORT",
    "CLOUD_SFTP_USER", "CLOUD_SFTP_PASSWORD", "CLOUD_SFTP_KEY_PATH",
    "CLOUD_SFTP_BASE_PATH", "CLOUD_S3_ENDPOINT", "CLOUD_S3_ACCESS_KEY",
    "CLOUD_S3_SECRET_KEY", "CLOUD_S3_BUCKET", "CLOUD_S3_REGION",
    "CLOUD_SMB_SERVER", "CLOUD_SMB_USER", "CLOUD_SMB_PASSWORD",
    "CLOUD_LOCAL_PATH", "CLOUD_SYNC_ON_UPLOAD",
    "OFFICE_PREVIEW_CACHE_DIR", "TSJ_PROMPT_DIR", "TSJ_KNOWLEDGE_DIR",
    "CROSS_WP_REF_PATH", "LINKAGE_PANORAMA_CWR_PATH", "VR_RULES_DATA_DIR",
    "LOG_FILE_PATH", "BACKUP_DIR", "BACKUP_RETENTION_DAYS",
    "LEDGER_PURGE_KEEP_COUNT", "LEDGER_IMPORT_EXPECTED_WORKERS",
    "LEDGER_IMPORT_MAX_CONCURRENT",
})

if missing_in_doc:
    print("❌ config.py 中存在但文档未列出：")
    for v in missing_in_doc:
        print(f"  - {v}")
if extra_in_doc:
    print("⚠️  文档列出但 config.py 中找不到（可能来自 .env 或 os.environ）：")
    for v in extra_in_doc:
        print(f"  - {v}")
if not missing_in_doc and not extra_in_doc:
    print("✅ 配置文档与 config.py 完全对齐")
```

**预期输出**：跑一次后输出 `✅ 配置文档与 config.py 完全对齐`（或列出新增/未覆盖项，作为本文档维护清单）。

---

## 维护备忘

- **新增 `Settings` 字段**：必须同步追加到本文档对应章节（建议 PR 模板加 checkbox）。
- **删除 `Settings` 字段**：必须同步删除本文档条目，并在变更日志注明 deprecation 周期。
- **`os.environ.get` 直读项**：少用，必要时归类到对应章节并标注"运行时读"。
- **回归核验**：每次 spec 完成后跑上述 grep 脚本一次（用完即删）。

> **关联文档**：
> - 部署：`docker-compose.yml` / `start-dev.bat` / `docs/deployment/phase8/deployment.md`
> - 安全：`docs/adr/` 下 RLS / JWT / RBAC 决策
> - 性能：`docs/deployment/phase8/guide.md`（连接池 / 缓存 TTL 调优）
> - 日志：`backend/app/core/logging_config.py` 实现细节
