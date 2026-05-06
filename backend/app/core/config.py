"""配置管理模块 — 使用 pydantic-settings 从环境变量/.env 文件加载配置"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 查找 .env 文件：优先 backend/.env，其次项目根目录 .env
_env_file = ".env"
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if not Path(_env_file).exists() and _root_env.exists():
    _env_file = str(_root_env)


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"
    DB_POOL_SIZE: int = 10       # 连接池常驻连接数
    DB_MAX_OVERFLOW: int = 20    # 连接池最大溢出连接数
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3030"
    # 登录安全
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 30
    # ONLYOFFICE（向后兼容，底稿编辑已迁移至 Univer）
    ONLYOFFICE_URL: str = "http://onlyoffice:80"
    WOPI_BASE_URL: str = "http://backend:8000/wopi"
    # 文件存储
    STORAGE_ROOT: str = "./storage"
    ATTACHMENT_PRIMARY_STORAGE: str = "paperless"
    ATTACHMENT_FALLBACK_TO_LOCAL: bool = True
    ATTACHMENT_LOCAL_STORAGE_ROOT: str = "./storage/attachments"
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
    LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB: int = 200
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
    DEFAULT_EMBEDDING_MODEL: str = "Kbenkhaled/Qwen3.5-27B-NVFP4"
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

    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")

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

# 启动时警告弱 JWT 密钥
import logging as _logging
_logger = _logging.getLogger("audit_platform.config")
if not settings.is_jwt_key_secure:
    _logger.warning(
        "⚠️  JWT_SECRET_KEY 使用了默认弱密钥，生产环境请设置强随机密钥（至少16字符）"
    )
