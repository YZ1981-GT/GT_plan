"""数据库连接模块 — SQLAlchemy 2.0 异步引擎 + 会话工厂"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 自动检测断开的连接
    pool_recycle=3600,    # 1小时回收连接（防止数据库端超时断开）
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

