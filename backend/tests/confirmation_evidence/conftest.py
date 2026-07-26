"""confirmation-attachment-ocr-linkage — 共享 fixture（Task 1.3）

为本 spec 全部测试波次提供公共基础设施：
- SQLite 兼容 shim
- 内存异步数据库会话
- 常用 ID / 工厂函数
- hypothesis profile 注册

_Requirements: 10.1, 10.5_
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

# ─── SQLite 兼容 shim ─────────────────────────────────────────────────────────
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.models.confirmation_models import Confirmation  # noqa: E402

# ─── hypothesis profile ───────────────────────────────────────────────────────
from hypothesis import settings as hyp_settings, HealthCheck

hyp_settings.register_profile(
    "confirmation_evidence",
    max_examples=5,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.function_scoped_fixture,
    ],
)
hyp_settings.load_profile("confirmation_evidence")

# ─── 常量 ─────────────────────────────────────────────────────────────────────
FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# 所有合法状态
ALL_STATUSES = ("pending", "sent", "returned", "matched", "discrepancy")

# 默认容差
DEFAULT_TOLERANCE = Decimal("0.01")


# ─── 引擎 & 会话 fixture ──────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    return engine


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    """每个测试函数独立的内存会话，仅建 Confirmation 表。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(
                sync_conn, tables=[Confirmation.__table__]
            )
        )
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[Confirmation.__table__]
            )
        )
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────
def make_confirmation_data(
    *,
    confirm_type: str = "receivable",
    counterparty: str = "测试公司",
    book_amount: float | None = None,
    status: str = "pending",
) -> dict:
    """构造创建函证所需的最小数据 dict。"""
    data: dict = {
        "confirm_type": confirm_type,
        "counterparty": counterparty,
    }
    if book_amount is not None:
        data["book_amount"] = book_amount
    return data
