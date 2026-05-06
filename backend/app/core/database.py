"""数据库连接模块 — SQLAlchemy 2.0 异步引擎 + 会话工厂"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# 任务 14.1：根据数据库类型配置不同的连接池参数
# - PostgreSQL 生产：pool_size=20 / max_overflow=80（总计 100 连接），recycle 30 分钟
# - SQLite 开发：轻量配置，recycle 1 小时
_is_postgres = settings.DATABASE_URL.startswith("postgresql")

if _is_postgres:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=max(settings.DB_POOL_SIZE, 20),
        max_overflow=max(settings.DB_MAX_OVERFLOW, 80),
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800,  # 30 分钟，与 PG idle_in_transaction_session_timeout 协调
        echo=False,
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 同步引擎和会话工厂（供同步 service 函数使用）
_sync_engine = engine.sync_engine
SyncSession = sessionmaker(bind=_sync_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：提供异步数据库会话，请求结束后自动关闭。"""
    async with async_session() as session:
        yield session


async def dispose_engine() -> None:
    """优雅关闭连接池，在应用关闭时调用。"""
    await engine.dispose()


def get_sync_db():
    """生成同步数据库会话的依赖注入函数（供同步 service 使用）。

    用法:
        db: Session = Depends(get_sync_db)
    """
    db = SyncSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

