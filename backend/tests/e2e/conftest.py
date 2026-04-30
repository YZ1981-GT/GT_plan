"""E2E 测试配置 — 支持 PostgreSQL（docker-compose.test.yml）或 SQLite 降级

运行方式:
    # 方式1：使用 PostgreSQL + Redis（推荐）
    docker compose -f docker-compose.test.yml up -d
    E2E_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/audit_test \
        python -m pytest backend/tests/e2e/ -v

    # 方式2：使用 SQLite 内存数据库（无需 Docker）
    python -m pytest backend/tests/e2e/ -v
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# 环境变量覆盖（必须在 import app 之前设置）
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "e2e-test-secret-key")

# 数据库 URL：优先使用 E2E_DATABASE_URL 环境变量（PostgreSQL），否则降级 SQLite
_E2E_DB_URL = os.environ.get("E2E_DATABASE_URL", "")
_USE_PG = bool(_E2E_DB_URL and "postgresql" in _E2E_DB_URL)

if _USE_PG:
    TEST_DB_URL = _E2E_DB_URL
    os.environ["DATABASE_URL"] = _E2E_DB_URL
    os.environ.setdefault("REDIS_URL", "redis://localhost:6381/0")
else:
    # SQLite 降级模式 — 与单元测试相同的基础设施
    TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
    os.environ.setdefault("DATABASE_URL", TEST_DB_URL)

# SQLite JSONB 兼容 — 必须在 import ORM 模型之前
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.base import Base  # noqa: E402

# 确保所有 ORM 模型已导入，create_all 才能建全表
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401

# Stub for 'workpapers' table referenced by AI models FK
import sqlalchemy as _sa


class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)


# ---------------------------------------------------------------------------
# pytest marker 注册
# ---------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end integration tests")


# ---------------------------------------------------------------------------
# event loop（session scope，所有 E2E 测试共享）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 数据库引擎 + 建表 / 销毁
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    if _USE_PG:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


# ---------------------------------------------------------------------------
# 每个测试函数独立的数据库会话（自动回滚隔离）
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# fakeredis（SQLite 模式下替代真实 Redis）
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def fake_redis():
    """提供 fakeredis 实例，用于 SQLite 降级模式。"""
    r = fakeredis.aioredis.FakeRedis()
    yield r
    await r.aclose()


# ---------------------------------------------------------------------------
# 测试用管理员用户
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """在测试数据库中创建一个 admin 用户并返回。"""
    from app.models.core import User, UserRole

    user = User(
        id=uuid4(),
        username=f"e2e_admin_{uuid4().hex[:8]}",
        email=f"e2e_{uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# 认证 token
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_token(admin_user):
    """为测试用户生成 JWT access token。"""
    return create_access_token({"sub": str(admin_user.id)})


# ---------------------------------------------------------------------------
# httpx AsyncClient（通过 ASGITransport 直连 FastAPI app）
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(
    engine, db_session, auth_token, fake_redis
) -> AsyncGenerator[AsyncClient, None]:
    """带认证的 httpx AsyncClient，依赖注入覆盖 get_db 和 get_redis。"""

    async def _override_get_db():
        yield db_session

    async def _override_get_redis():
        return fake_redis

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {auth_token}"},
    ) as c:
        yield c

    fastapi_app.dependency_overrides.clear()
