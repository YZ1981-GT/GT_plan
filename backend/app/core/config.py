"""配置管理模块 — 使用 pydantic-settings 从环境变量/.env 文件加载配置"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform"
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    # JWT
    JWT_SECRET_KEY: str  # 必填，无默认值
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    # 登录安全
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 30
    # ONLYOFFICE
    ONLYOFFICE_URL: str = "http://onlyoffice:80"
    WOPI_BASE_URL: str = "http://backend:8000/wopi"
    # 文件存储
    STORAGE_ROOT: str = "./storage"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
