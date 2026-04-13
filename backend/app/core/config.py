"""配置管理模块 — 使用 pydantic-settings 从环境变量/.env 文件加载配置"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 查找 .env 文件：优先 backend/.env，其次项目根目录 .env
_env_file = ".env"
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if not Path(_env_file).exists() and _root_env.exists():
    _env_file = str(_root_env)


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"
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
    # ONLYOFFICE
    ONLYOFFICE_URL: str = "http://onlyoffice:80"
    WOPI_BASE_URL: str = "http://backend:8000/wopi"
    # 文件存储
    STORAGE_ROOT: str = "./storage"

    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")


settings = Settings()
