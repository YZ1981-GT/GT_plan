"""配置管理模块 — 使用 pydantic-settings 从环境变量/.env 文件加载配置"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 查找 .env 文件：优先 backend/.env，其次项目根目录 .env
_env_file = ".env"
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if not Path(_env_file).exists() and _root_env.exists():
    _env_file = str(_root_env)


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"
    DB_POOL_SIZE: int = 50       # 连接池常驻连接数（6000 并发优化）
    DB_MAX_OVERFLOW: int = 100   # 连接池最大溢出连接数（6000 并发优化）
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MODE: str = "single"  # "single"（默认） | "sentinel"（HA）
    REDIS_SENTINEL_HOSTS: str = "localhost:26379,localhost:26380,localhost:26381"
    REDIS_SENTINEL_SERVICE: str = "mymaster"
    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 小时（开发环境）
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3030"
    # 登录安全
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 30
    # ONLYOFFICE（向后兼容，底稿编辑已迁移至 Univer）
    ONLYOFFICE_URL: str = "http://onlyoffice:80"
    # JWT secret 默认空=禁用 JWT 签名（适用于容器 JWT_ENABLED=false 的开发环境）。
    # 生产环境须与 OnlyOffice 容器 JWT_SECRET 保持一致。
    ONLYOFFICE_JWT_SECRET: str = ""
    ONLYOFFICE_CALLBACK_BASE: str = ""
    ONLYOFFICE_MAX_SESSIONS: int = 10  # 最大并发编辑人数
    # procedure-delegation-visibility-isolation Task 11（组件 C11 EditorSecurity）：
    # 冻结的有限 JWT 时效（秒）。此值在验收开始前冻结并写入 Evidence_Manifest（Req 10.10/10.11）。
    # config 标识符 = "ONLYOFFICE_JWT_LIFETIME_SECONDS"。有限正值，绝不为 0 / 负 / 无限。
    ONLYOFFICE_JWT_LIFETIME_SECONDS: int = Field(default=900, ge=1)
    # 编辑器签名令牌强制校验开关。True = 对 config/file-read/callback/PutFile 等安全关键入口
    # 强制全量签名令牌校验（secret 缺失 / JWT disabled / 签名 / 过期 / 空值 / 不一致 fail-closed，
    # 即使 dev JWT_ENABLED=false 也拒绝写/回调路径，Req 10.9）。False（dev 默认）= 记录告警但放行，
    # 供 JWT disabled 的开发环境编辑；上线前置 True。校验机制本身恒 fail-closed（editor_security）。
    #
    # visibility-isolation-go-live-hardening Task 2 / R1（组件 H1 EnforcementEnabler）：
    # 此开关改为「环境求值」（见下方 _derive_onlyoffice_jwt_enforce 校验器）——
    # 未显式设置时按 APP_ENV 求值：prod/production/staging → True；dev（JWT disabled）保持 False。
    # 默认值本身不硬翻转为 True，避免破坏本地开发编辑。显式设置（env / .env 给出
    # ONLYOFFICE_JWT_ENFORCE=true|false）则完全尊重原值 —— 这就是不需代码回滚的 Rollback_Path：
    # 生产置 ONLYOFFICE_JWT_ENFORCE=false 即恢复启用前行为。
    ONLYOFFICE_JWT_ENFORCE: bool = False
    WOPI_BASE_URL: str = "http://backend:8000/wopi"
    # 文件存储
    STORAGE_ROOT: str = "./storage"
    ATTACHMENT_PRIMARY_STORAGE: str = "paperless"
    ATTACHMENT_FALLBACK_TO_LOCAL: bool = True
    ATTACHMENT_LOCAL_STORAGE_ROOT: str = "./storage/attachments"
    # 证据治理 —— 上传隔离/暂存区（durable quarantine，evidence-governance-hardening R1.2/§4.0/§5.1）
    # 必须位于任何 Storage_Boundary root（STORAGE_ROOT / ATTACHMENT_LOCAL_STORAGE_ROOT）之外，
    # 隔离内容绝不可经下载/预览/EvidenceRef/OCR/AI/FormalOutput/archive 任何边界路径读取。
    ATTACHMENT_QUARANTINE_ROOT: str = "./quarantine_store"
    # 是否使用持久（磁盘）隔离区。生产默认 True，保证 202 异步 finalize / 进程重启后 staged 内容仍在。
    ATTACHMENT_QUARANTINE_DURABLE: bool = True
    # 未 finalize 的 staged/quarantined 内容存活上限（秒）；超过由 reaper 加密擦除 + 标记 purged。
    ATTACHMENT_QUARANTINE_TTL_SECONDS: int = 86400  # 24h
    PAPERLESS_URL: str = ""
    PAPERLESS_TOKEN: str = ""
    PAPERLESS_TIMEOUT: int = 30
    # OCR 配置
    OCR_DEFAULT_ENGINE: str = "auto"  # auto, paddle, tesseract
    OCR_PADDLE_ENABLED: bool = True
    OCR_TESSERACT_ENABLED: bool = True
    OCR_TESSERACT_LANG: str = "chi_sim+eng"
    OCR_CONFIDENCE_THRESHOLD: float = 0.8
    # MinerU 配置
    MINERU_ENABLED: bool = False
    MINERU_API_URL: str = "http://localhost:8000"
    MINERU_USE_CLI: bool = True  # 使用 CLI 模式（直接调用本地 mineru 命令）
    # 文件上传限制
    MAX_UPLOAD_SIZE_MB: int = 800  # 最大上传文件大小（MB）
    MAX_REQUEST_BODY_MB: int = 850  # 全局请求体大小上限（MB），略大于上传限制以容纳 multipart 开销
    LEDGER_UPLOAD_STORAGE_ROOT: str = "./storage/ledger_uploads"
    LEDGER_UPLOAD_TTL_HOURS: int = 24
    LEDGER_UPLOAD_MAX_FILE_COUNT: int = 20
    LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB: int = 1024  # 账表导入总大小上限（MB），支持大 CSV 场景（如和平药房 432MB）
    LEDGER_ARTIFACT_STORAGE_BACKEND: str = "local"  # local, s3
    LEDGER_ARTIFACT_S3_ENDPOINT_URL: str = ""
    LEDGER_ARTIFACT_S3_REGION: str = "us-east-1"
    LEDGER_ARTIFACT_S3_BUCKET: str = ""
    LEDGER_ARTIFACT_S3_PREFIX: str = "ledger-import"
    LEDGER_ARTIFACT_S3_ACCESS_KEY_ID: str = ""
    LEDGER_ARTIFACT_S3_SECRET_ACCESS_KEY: str = ""
    LEDGER_ARTIFACT_S3_USE_SSL: bool = True
    LEDGER_ARTIFACT_DOWNLOAD_ROOT: str = "./storage/ledger_artifact_cache"
    LEDGER_ARTIFACT_STORAGE_FAILURE_MODE: str = ""  # timeout, readonly, unavailable
    LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD: float = 0.85
    LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED: bool = True
    LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS: int = 30
    LEDGER_IMPORT_WORKER_BATCH_SIZE: int = 3
    LEDGER_IMPORT_FULL_MODE_MAX_FILE_MB: int = Field(default=30, ge=1)
    LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED: bool = True
    LEDGER_IMPORT_OUTBOX_REPLAY_INTERVAL_SECONDS: int = 30
    LEDGER_IMPORT_OUTBOX_REPLAY_MAX_BACKOFF_SECONDS: int = 300
    LEDGER_IMPORT_OUTBOX_REPLAY_JITTER_RATIO: float = 0.2
    LEDGER_IMPORT_OUTBOX_REPLAY_LIMIT: int = 100
    LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS: int = 20
    LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD: float = Field(default=0.05, ge=0.0, le=1.0)
    LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD: float = Field(default=0.02, ge=0.0, le=1.0)
    LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD: int = Field(default=1800, ge=1)
    LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD: int = Field(default=300, ge=1)
    LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD: int = Field(default=20, ge=1)
    LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD: int = Field(default=10, ge=1)
    LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_ENABLED: bool = True
    LEDGER_IMPORT_EVENT_CONSUMPTION_RETENTION_DAYS: int = Field(default=180, ge=1)
    LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_INTERVAL_SECONDS: int = Field(default=3600, ge=60)
    LEDGER_IMPORT_EVENT_CONSUMPTION_CLEANUP_BATCH_SIZE: int = Field(default=5000, ge=1)
    # LLM 服务配置（默认使用本地 vLLM）
    LLM_BASE_URL: str = "http://localhost:8100/v1"  # vLLM OpenAI 兼容 API
    LLM_API_KEY: str = "not-needed"  # vLLM 本地不需要 API Key
    DEFAULT_CHAT_MODEL: str = "Kbenkhaled/Qwen3.5-27B-NVFP4"
    DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    LLM_EMBEDDING_BASE_URL: str = "http://localhost:8101/v1"  # 独立 embedding 服务（bge-m3）
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096
    LLM_ENABLE_THINKING: bool = False  # Qwen3.5 thinking 模式，审计场景默认关闭
    # Ollama 配置（备用，当 vLLM 不可用时降级）
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # ChromaDB 向量数据库
    CHROMADB_URL: str = "http://localhost:8000"
    # Phase 8: 事件总线去重窗口（毫秒）
    EVENT_DEBOUNCE_MS: int = 500
    # Phase 8: 公式引擎超时（秒）
    FORMULA_EXECUTE_TIMEOUT: int = 10
    # Phase 8: 数据加密密钥
    ENCRYPTION_KEY: str = ""
    # LLM 限流配置
    LLM_RATE_LIMIT_PER_MINUTE: int = 10  # 每用户每分钟最大 LLM 调用次数
    # bcrypt cost factor（OWASP 推荐 12，可通过环境变量调整）
    BCRYPT_ROUNDS: int = 12

    # R1 上线日期：早于此日期创建的项目进入独立性声明 legacy 宽容期
    # 空字符串表示"无 legacy 宽容期"，所有项目都严格检查
    INDEPENDENCE_LEGACY_CUTOFF_DATE: str = "2026-05-05"
    # Batch 3-7: 全局宽容期总开关；R6+ 老项目升级完毕后可关闭此开关彻底下线宽容期
    # False = 关闭，即使项目早于 CUTOFF_DATE 也严格检查（不走 legacy 路径）
    INDEPENDENCE_LEGACY_GRACE_ENABLED: bool = True

    # Q5: 运行环境标识（dev / staging / production）
    # production 模式下强制校验关键安全配置（JWT_SECRET_KEY 等），校验失败启动报错
    APP_ENV: str = "dev"

    # ClamAV 病毒扫描（SC-3）
    CLAMAV_ENABLED: bool = False
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310

    # --- 证据治理附件安全门（attachment-ocr-ai-evidence-governance-hardening R1.2/R1.3/R2/R15）---
    # SecureAttachmentGateway 的三道内容门：声明媒体类型允许清单 / 恶意内容扫描 / 可读性检查。
    # 生产接线必须真实注入（不能保持 None 默认——None 会令门以 default=True 放行）。
    #
    # 声明媒体类型正向允许清单（逗号分隔）。上传声明的媒体类型不在此集合则拒绝
    # （MEDIA_TYPE_MISMATCH / declared_type_not_allowed）。默认覆盖审计底稿常见证据类型
    # （pdf/png/jpeg/gif/bmp/tiff/xlsx/docx/pptx/xls/doc/csv/txt/zip）。留空字符串=禁用允许清单
    # （不推荐；等同无正向白名单）。
    ATTACHMENT_ALLOWED_MEDIA_TYPES: str = (
        "application/pdf,"
        "image/png,image/jpeg,image/gif,image/bmp,image/tiff,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "application/vnd.ms-excel,application/msword,application/vnd.ms-powerpoint,"
        "text/csv,text/plain,application/zip"
    )
    # 最小签名式恶意内容检查（拒绝可执行/脚本 magic：PE MZ / ELF / Mach-O / shebang / EICAR）。
    # 这是真实的最小实现（非 lambda:True 桩）；与 CLAMAV_ENABLED 组合成完整恶意内容门。
    ATTACHMENT_SIGNATURE_SCAN_ENABLED: bool = True
    # 可读性检查（非空 + 按识别类型的廉价可解析性校验）。
    ATTACHMENT_READABILITY_CHECK_ENABLED: bool = True
    # fail-closed 启动守卫：为 True 时若三道门未真实接线则启动直接报错；
    # 为 False（默认）时仅在 production 环境下打 loud WARNING 并在治理指标中暴露。
    ATTACHMENT_SECURITY_GATES_REQUIRED: bool = False

    # I-F4 商誉减值 / 后续 LLM 接入开关（默认 False = stub 实现）
    # 当 wp_ai_service 升级真实接入 LLM 后改为 True，前端 is_llm_stub 字段自动反映
    WP_AI_SERVICE_ENABLED: bool = False

    # 交付物章节内容控件化（deliverable-lineage-content-control spec）
    # True = 生成审计报告正文/附注 docx 时为每节注入 Block Content Control（Tag=sec_xxx，
    # 与 bookmark 并存），供前端 OnlyOffice 连接器实现真·光标跟随溯源。
    # 默认 False = 不注入内容控件，生成的 docx 与引入前逐字节等价（零回归）。
    DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED: bool = False

    # 向量存储后端切换（pgtext=现状降级 | pgvector=原生向量列+ivfflat）
    # 默认 pgtext（安全，现有行为不变）；pgvector 需 V043 迁移 + CREATE EXTENSION vector
    VECTOR_STORE_BACKEND: str = "pgtext"

    # 合并模块开发中标记（Phase 0 防误用 P3）
    # True = 合并模块处于开发中，前端展示警告 banner；端到端验证通过后人工置 False
    CONSOL_MODULE_DEV_MODE: bool = True

    # 合并附注 V2 灰度开关（Phase 2 接线 / ADR-CONSOL-202）
    # False = 老版兼容（generate_consol_notes_sync，7 骨架章节，默认）
    # True  = V2（generate_full_consol_notes，消费子公司单体附注汇总）
    # 默认 False：V2 真实数据验证通过后（Phase 4）再默认开启；V2 异常自动回退老版
    CONSOL_NOTES_V2_ENABLED: bool = False

    # 国企↔上市跨模板章节翻译接线开关（Phase 2 / ADR-CONSOL-204）
    # consol_cross_template_service（translate_child_section 等 3 API）原为孤儿
    # （0 router 引用），Phase 2 随 V2 附注汇总路径接线。
    # 双开关防御：仅当 CONSOL_NOTES_V2_ENABLED AND CONSOL_CROSS_TEMPLATE_ENABLED
    # 同时为 True 时才对 template_type 不同的子公司章节做跨模板翻译；
    # False（默认）= 即使 V2 开启也跳过跨模板翻译，原样汇总（老版兼容、灰度防御）。
    CONSOL_CROSS_TEMPLATE_ENABLED: bool = False

    # --- llm-structured-output ---
    LLM_STRUCTURED_OUTPUT_ENABLED: bool = True
    LLM_GUIDED_DECODING_ENABLED: bool = True
    LLM_STRUCTURED_MAX_RETRIES: int = 2

    # --- endpoint-fuzz-and-tracing ---
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER: str = "console"  # console | otlp
    OTEL_OTLP_ENDPOINT: str = "http://localhost:4317"
    RETRIEVAL_BM25_FALLBACK_ENABLED: bool = True
    SCHEMATHESIS_MAX_EXAMPLES: int = 5

    # --- pg-pooling-and-load-test ---
    DB_USE_PGBOUNCER: bool = False
    DB_PGBOUNCER_HOST: str = "localhost"
    DB_PGBOUNCER_PORT: int = 6432
    # 本地/Docker 开发：PG 未配 SSL，asyncpg 默认 sslmode=prefer 仍会先发 SSLRequest
    # 探测握手，Windows ProactorEventLoop 下该握手易被中止（WinError 10053 /
    # connection_lost）。无 SSL 部署显式禁用协商，消除该失败面。生产启 TLS 时置 False。
    DB_DISABLE_SSL: bool = True

    # --- xlsx-read-acceleration ---
    XLSX_READ_USE_CALAMINE: bool = True

    # --- dev-tooling-modernization ---
    DOCLING_ENABLED: bool = False

    # --- audit-report-template-integration (Phase 1) ---
    # 灰度开关：False=保留 ReportBodyService 旧路径；True=TemplateFillService 主路径
    USE_TEMPLATE_FILL_SERVICE: bool = True
    # 模板 manifest 根目录；留空则使用 backend/data/audit_report_templates
    TEMPLATE_MANIFEST_DIR: str = ""
    # 报告正文 preview 会话 TTL（小时）
    FILL_PREVIEW_TTL_HOURS: int = 24

    # --- procedure-delegation-notification ---
    # expand → dual-read → backfill → cutover → contract 分阶段部署开关（完整行为矩阵见 Task 15）。
    # expand 阶段默认全部 off/legacy：render-config 只读 overlay 且 task overlay 不改既有读语义。
    # PROCEDURE_ROW_TASKS_ENABLED=True 才在 render-config 上叠加 task overlay（纯读，缺 task 标 materialization_required）。
    PROCEDURE_ROW_TASKS_ENABLED: bool = False
    # procedure-mainline-convergence Task 7.2: 值域统一为下划线 + 新增 paused
    # legacy = 所有写走旧 ProcedureInstance 路径（默认，向后兼容）
    # dual = 新旧双写（过渡期数据验证用）
    # task_source = 只走 ProcedureRowTask 新路径（生产目标态）
    # paused = 紧急回退态，新路径暂停接受写入（drain + audit），读仍走 task overlay
    PROCEDURE_ROW_TASK_WRITE_MODE: str = "legacy"  # legacy | dual | task_source | paused
    PROCEDURE_TASK_DISPATCHER_ENABLED: bool = False

    # --- visibility-isolation-go-live-hardening Task 3 / R2（组件 H2 DispatcherLifecycle）---
    # epoch 失效 Redis dispatcher（publisher fan-out + subscriber psubscribe）挂载开关。
    # 默认 True：应用启动即挂载失效派发器 → 撤权走 Redis 快路径 ≤1s 收敛。
    # 置 False 即回退（不挂载 dispatcher），撤权仍由 PersistentEpochCache 的 ≤1s DB epoch
    # 安全网兜底 fail-closed（绝不 stale-allow），是纯配置、不需代码回滚的 Rollback_Path。
    VISIBILITY_INVALIDATION_DISPATCHER_ENABLED: bool = True

    # --- disclosure-note-knowledge-ai-enrichment ---
    # 附注 AI 正文生成的知识库 RAG 检索接入开关（加法式、可开关、fail-open）。
    # 默认 False = 零回归：行为与接入前逐字一致，_generate_text_with_llm / generate_notes
    # 不调用 NoteKnowledgeEnricher，退回现有三级填充（上年 DB → 通用 LLM → 模板）。
    # 生产/试点可经 env 置 True 启用 RAG（检索知识库文档作参照上下文 + Citation 溯源）。
    # 任一环失败（知识库为空 / semantic_search 抛异常 / LLM 不可用）一律 fail-open 降级，
    # 故开关仅控制"是否尝试 RAG"，不影响可用性。
    DISCLOSURE_NOTE_RAG_ENABLED: bool = False
    # 单章节 RAG 检索返回的知识库片段上限（semantic_search top_k），避免 token 溢出。
    DISCLOSURE_NOTE_RAG_TOP_K: int = 5
    # 拼入 LLM user prompt 的参照上下文字符预算上限，超出则截断超长片段。
    DISCLOSURE_NOTE_RAG_CHAR_BUDGET: int = 3000

    # --- disclosure-note-formula-and-report-sync ---
    # 附注表内公式求值（resolve_formula sum/aging/report）+ 报表→附注金额真同步的灰度开关。
    # 默认 False = 零回归：resolve_formula 保持返 None（stub 行为）、sync_report_to_notes
    # 保持仅清 is_stale（当前可观察行为），不产生新副作用、逐字节等价当前链路。
    # 置 True 才启用 NoteFormulaEvaluator 表内求值 + ReportNoteLinkage 报表→附注真同步。
    # 任一环求值/同步异常一律 fail-open（返 None / 跳过计 skipped），不阻塞附注生成或报表流程。
    # 注：附注校验 preset 加载/解析修复（Wave4）是纯 bug 修复，不受本开关约束。
    DISCLOSURE_NOTE_FORMULA_ENABLED: bool = False
    # 附注校验 findings 严格度开关（Wave4 修 preset 路径后，soe 760 / listed 187 条规则从
    # "恒 0 findings" 变为全量运行 → 有数据章节会瞬间涌现大量 warning，冲击审计师）。
    # 默认 False = 宽松缓冲：validate_all 只逐条返回 error 级 findings（合计不平等硬性），
    # warning 级折叠进 warning_summary（按 note_section×check_type 聚合计数，不逐条弹）。
    # True = 严格：全部 findings（含 warning）逐条返回。上线平稳后可置 True。
    # 不影响 findings 的产生与持久化，仅影响 validate_all 响应的 findings 明细呈现粒度。
    DISCLOSURE_NOTE_VALIDATION_STRICT: bool = False

    # --- d-cycle-four-table-extraction-formulas ---
    # D1–D7 四表库（trial_balance/tb_balance/tb_ledger/tb_aux_balance）→ 审定表自动提取
    # 填充（Tier B `_build_adjudication_prefill` 预填）+ Tier A 可编辑提取公式的灰度开关。
    # 默认 False = 零回归：D1–D7 render 不调 prefill、不返 adjudication_prefill、公式管理面板
    # 不列 Tier A 预设 → render 逐字节等价当前链路（保留既有 tb_amount 核对行/手工一键取数/
    # 明细导入导出/审定 TB 核对/附注联动不变）。置 True 才启用 Tier B 预填 + Tier A 公式。
    # 任一环取数异常一律 fail-open（该循环返空 prefill / tb_amount=0 等不变），不阻断 render。
    # D6/D2 试点验证后再铺 D1/D3/D4/D5/D7，单循环可回退。
    D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED: bool = False

    # --- f2-four-table-extraction-refresh ---
    # F2 存货审定表四表取数灰度开关。置 True 才启用 F2-1 Tier A 可编辑取数公式 +
    # Tier B render 预填 + 🔄刷新取数入口。默认 False = 零回归：F2 render/公式管理/
    # 前端行为与改动前逐字节等价。
    F2_FOUR_TABLE_EXTRACTION_ENABLED: bool = False

    # --- d-cycle-tier-a-writeback-detail-seed（前置 spec 的增量，P0-2 子开关）---
    # 门控「明细表维度归集 render 自动 seed」（P0-2 / Requirement 4）——打开 D-cycle 明细表
    # 且明细行完全空时，调既有后端归集（tb_aux_balance 客户/合同维度、序时账期后归集）
    # transient seed 明细行进 render 返回（detail_prefill，不落库、手工优先、fail-open）。
    # 默认 False = 零回归：明细表不自动 seed，仍由前端手工「一键取数」按钮驱动。
    # **生效条件 = 主开关 D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED ∧ 本子开关**（被主开关 AND）——
    # 故可"发 P0-1、压 P0-2"实现真正独立灰度与回退（主开关关则本子开关无效）。
    # P0-1（Tier A 真生效）与 P0-2（本子开关）代码路径独立，其一失败不牵连其二。
    D_CYCLE_DETAIL_SEED_ENABLED: bool = False

    # --- h1-four-table-extraction ---
    # H1 固定资产四表取数扩展的灰度开关：H1-2 明细**分类级**取数（tb_balance 叶子）、
    # 明细增减 ↔ 序时账（tb_ledger 1601 借/贷合计）核对、折旧账面数取数与对方科目可用性探测。
    # 默认 False = 零回归：H1 render 不输出 `h1_four_table_prefill`，前端无取数入口，
    # 既有 H1-1 分类预填（adjudication_category_prefill）/ tb_values / 各 H1-x 内部带入不变。
    # 任一取数环节异常一律 fail-open（该段返空 / available=False），不阻断 render。
    # 宁缺勿造边界（已实证）：tb_aux_balance 无资产卡片维度 → 不做卡片级明细；
    # tb_ledger 1602 对方科目填充率约 9% 且凭证为合并记账 → 折旧费用归属不自动归集。
    H1_FOUR_TABLE_EXTRACTION_ENABLED: bool = True

    # --- g7-linkage-extraction-completion（G7 长期股权投资取数灰度）---
    # 门控 G7-2 逐户四表取数（tb_aux_balance aux_type='客户' 1511 归集）+ G7-1 叶子分类合计
    # 核对（tb_balance 1511/1512 叶子聚合 → tb_leaf_categories）。默认 False = 零回归：
    # render 不输出 tb_leaf_categories、取数端点返回 imported_count=0 不写入，G7 各 sheet
    # 逐字节不变。取数异常一律 fail-open（返空/None）不阻断 render。
    # 联动入口/抽凭/stale 提示/合并范围反向补录（R1/R5/R6/R7）为纯 UI 接线，不受本开关约束。
    G7_FOUR_TABLE_EXTRACTION_ENABLED: bool = False

    # --- h4-four-table-extraction ---
    # H4 工程物资四表取数灰度开关：H4-2 明细从 tb_balance 1605 叶子自动种子、
    # H4-1 审定表 TB 核对走 report_account_mapping 规则映射、H4-6 盘点覆盖率分母自动带入、
    # H4-5 减少检查↔H2 在建工程跨底稿勾稽。
    # 默认 False = 零回归：render 不输出 detail_prefill/tb_source_codes/h4_extraction_enabled，
    # 既有功能逐字节不变。任一取数环节异常一律 fail-open 不阻断 render。
    H4_FOUR_TABLE_EXTRACTION_ENABLED: bool = True

    # --- h2-four-table-extraction ---
    # H2 在建工程四表取数灰度开关：H2-2 明细从 tb_balance 1604 叶子自动种子。
    # 默认 True = render 输出 detail_prefill 供前端 Persist_First 种子。
    H2_FOUR_TABLE_EXTRACTION_ENABLED: bool = True

    # --- hi-cycle-four-table-extraction ---
    # H5-H10 / I1-I6 共 12 张审定表四表库取数公式预设 + render 分段 prefill + 刷新入口。
    # 复用 d_cycle_extraction 模块（presets/anchor_registry/tier_a_seed/prefill）。
    # 默认 False = 零回归：render 不输出 adjudication_segment_prefill 等取数字段，
    # 既有功能逐字节不变。各底稿取数环节异常一律 fail-open 不阻断 render。
    HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED: bool = True

    # --- lmn-four-table-extraction ---
    # L/M/N 循环审定表四表库取数灰度开关：L1-L8 + M1/M2 从 tb_balance 取期初/期末余额
    # 或借贷发生额供审定表 TB 核对行消费。默认 False = 零回归：helper 返回全 0 结果，
    # 前端 `hasTb` 守卫不渲染核对行（逐字节等价当前无 TB 数据时审定表无核对行）。
    # 任一取数异常一律 fail-open（result 各字段置 0，log warning），不阻断 render。
    LMN_FOUR_TABLE_EXTRACTION_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")

    @model_validator(mode="after")
    def _derive_onlyoffice_jwt_enforce(self) -> "Settings":
        """R1 组件 H1 EnforcementEnabler：环境求值 ONLYOFFICE_JWT_ENFORCE。

        仅当该开关**未被显式设置**（env / .env / 构造入参均未给出 ``ONLYOFFICE_JWT_ENFORCE``）时，
        按运行环境标识 ``APP_ENV`` 派生：prod/production/staging → True；其余（dev，JWT disabled）
        保持 False，本地开发编辑不受影响。

        若显式设置（如 ``ONLYOFFICE_JWT_ENFORCE=false``），``model_fields_set`` 会包含该字段名，
        此处跳过派生并完全尊重显式值 —— 这就是**纯配置、不需代码回滚**的 Rollback_Path：
        生产环境置 ``ONLYOFFICE_JWT_ENFORCE=false`` 即恢复启用前行为。
        """
        if "ONLYOFFICE_JWT_ENFORCE" not in self.model_fields_set:
            env = (self.APP_ENV or "").strip().lower()
            if env in ("prod", "production", "staging"):
                self.ONLYOFFICE_JWT_ENFORCE = True
        return self

    @property
    def is_jwt_key_secure(self) -> bool:
        """检查 JWT 密钥是否为安全值（非默认弱密钥）"""
        _WEAK_KEYS = {
            "dev-secret-key-change-in-production",
            "change-me-to-a-random-secret",
            "secret",
            "test",
        }
        return self.JWT_SECRET_KEY not in _WEAK_KEYS and len(self.JWT_SECRET_KEY) >= 16


settings = Settings()

# 启动时校验关键安全配置
import logging as _logging
_logger = _logging.getLogger("audit_platform.config")
if not settings.is_jwt_key_secure:
    # Q5: production 模式下强制失败，防止弱密钥上线
    if settings.APP_ENV.lower() in ("prod", "production"):
        raise RuntimeError(
            "APP_ENV=production 但 JWT_SECRET_KEY 使用弱密钥/<16 字符。"
            "生产环境必须设置强随机密钥（建议 `openssl rand -hex 32`）。"
            "如需跳过此检查（仅用于应急），可临时设置 APP_ENV=staging。"
        )
    _logger.warning(
        "⚠️  JWT_SECRET_KEY 使用了默认弱密钥，生产环境请设置强随机密钥（至少16字符）"
    )


