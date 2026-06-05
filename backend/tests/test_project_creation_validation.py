"""项目创建校验链 Property-Based Tests。

Feature: project-creation-enhancement
Properties 4-8
"""

import uuid

import pytest
import pytest_asyncio
import hypothesis.strategies as st
from hypothesis import given, settings, HealthCheck
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS


# ---------------------------------------------------------------------------
# 辅助：构造合法 USCC
# ---------------------------------------------------------------------------

def _compute_check_digit(prefix: str) -> str:
    """根据 17 位前缀计算第 18 位校验码字符。"""
    total = 0
    for i in range(17):
        total += _CHAR_TO_VALUE[prefix[i]] * _WEIGHTS[i]
    remainder = total % 31
    check_digit = 31 - remainder
    if check_digit == 31:
        check_digit = 0
    return USCC_CHARSET[check_digit]


def make_valid_uscc(prefix_17: str) -> str:
    """从 17 位前缀构造合法 18 位 USCC。"""
    return prefix_17 + _compute_check_digit(prefix_17)


# 一个固定的合法 USCC 用于测试
FIXED_USCC_PREFIX = "91110000710931130"
FIXED_USCC = make_valid_uscc(FIXED_USCC_PREFIX)


# ---------------------------------------------------------------------------
# DB Fixtures（in-memory SQLite）
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def engine():
    """创建测试用 in-memory SQLite 引擎。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
        SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


# ---------------------------------------------------------------------------
# 辅助：直接调用 service 层创建项目（绕过 Pydantic 使用 dict 构造）
# ---------------------------------------------------------------------------

async def _create_project_direct(
    db: AsyncSession,
    *,
    client_name: str = "测试客户",
    audit_year: int = 2025,
    project_type: str = "annual",
    accounting_standard: str = "enterprise",
    company_code: str | None = None,
    short_name: str | None = None,
    report_scope: str = "standalone",
):
    """直接调用 create_project，构造 BasicInfoSchema 时绕过空值（传有效占位给 Pydantic，
    然后替换 data 属性来模拟空值到达 service 层）。"""
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    # 构造合法 schema 对象
    actual_company_code = company_code if company_code and len(company_code) >= 18 else FIXED_USCC
    actual_short_name = short_name if short_name and len(short_name) >= 1 else "占位"

    data = BasicInfoSchema(
        client_name=client_name,
        audit_year=audit_year,
        project_type=project_type,
        accounting_standard=accounting_standard,
        company_code=actual_company_code,
        short_name=actual_short_name,
        report_scope=report_scope,
    )

    # 覆盖为真实测试值（模拟绕过 Pydantic 到达 service 的场景）
    if company_code is not None:
        object.__setattr__(data, "company_code", company_code)
    if short_name is not None:
        object.__setattr__(data, "short_name", short_name)

    return await create_project(data, db)


async def _create_project_valid(
    db: AsyncSession,
    *,
    client_name: str = "测试客户",
    audit_year: int = 2025,
    project_type: str = "annual",
    accounting_standard: str = "enterprise",
    company_code: str = FIXED_USCC,
    short_name: str = "测试简称",
    report_scope: str = "standalone",
):
    """正常创建项目（所有参数合法）。"""
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    data = BasicInfoSchema(
        client_name=client_name,
        audit_year=audit_year,
        project_type=project_type,
        accounting_standard=accounting_standard,
        company_code=company_code,
        short_name=short_name,
        report_scope=report_scope,
    )
    return await create_project(data, db)


# ---------------------------------------------------------------------------
# Property 4: 必填字段为空时拒绝创建
# **Validates: Requirements 1.1, 2.2**
# ---------------------------------------------------------------------------

# Strategy: whitespace-only or empty values (simulates bypassed Pydantic)
_empty_or_whitespace = st.one_of(
    st.just(""),
    st.just("   "),
    st.just("\t"),
    st.just("\n"),
    st.just("  \t\n  "),
)


@given(empty_val=_empty_or_whitespace)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_empty_company_code_rejected(empty_val: str, engine):
    """Empty/whitespace company_code → rejection with '企业代码为必填项'。"""
    from fastapi import HTTPException
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            await _create_project_direct(db, company_code=empty_val)
        assert exc_info.value.status_code == 422
        assert "企业代码为必填项" in exc_info.value.detail


@given(empty_val=_empty_or_whitespace)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_empty_short_name_rejected(empty_val: str, engine):
    """Empty/whitespace short_name → rejection with '项目简称为必填项'。"""
    from fastapi import HTTPException
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            await _create_project_direct(db, short_name=empty_val)
        assert exc_info.value.status_code == 422
        assert "项目简称为必填项" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Property 5: Short_Name 持久化往返
# **Validates: Requirements 2.4, 2.5**
# ---------------------------------------------------------------------------

# Strategy: non-whitespace short names (valid for Pydantic min_length=1)
_valid_short_names = st.text(
    alphabet=st.characters(categories=("L", "N", "P")),
    min_size=1, max_size=50,
).filter(lambda s: s.strip())

# Strategy: 17-char USCC prefixes (for generating unique USCCs)
_uscc_prefix = st.text(alphabet=USCC_CHARSET, min_size=17, max_size=17)


@given(short_name=_valid_short_names, prefix=_uscc_prefix)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_short_name_round_trip(short_name: str, prefix: str, engine):
    """Valid short_name round-trip: create → read back → same value."""
    from sqlalchemy import select

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        uscc = make_valid_uscc(prefix)

        project = await _create_project_valid(
            db, short_name=short_name, company_code=uscc, audit_year=2099,
        )

        # Read back
        result = await db.execute(select(Project).where(Project.id == project.id))
        loaded = result.scalar_one()
        assert loaded.short_name == short_name


# ---------------------------------------------------------------------------
# Property 6: 唯一性三元组重复拒绝
# **Validates: Requirements 3.1, 3.2, 3.3**
# ---------------------------------------------------------------------------

_report_scopes = st.sampled_from(["standalone", "consolidated"])


@given(report_scope=_report_scopes, prefix=_uscc_prefix)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_duplicate_triple_rejected(report_scope: str, prefix: str, engine):
    """Duplicate (company_code, audit_year, report_scope) → rejection with Chinese label."""
    from fastapi import HTTPException

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        uscc = make_valid_uscc(prefix)

        # First creation succeeds
        await _create_project_valid(
            db, company_code=uscc, audit_year=2030, report_scope=report_scope,
        )

        # Second creation with same triple fails
        with pytest.raises(HTTPException) as exc_info:
            await _create_project_valid(
                db, company_code=uscc, audit_year=2030, report_scope=report_scope,
                short_name="另一个简称",
            )
        assert exc_info.value.status_code == 409
        if report_scope == "standalone":
            assert "单户" in exc_info.value.detail
        else:
            assert "合并" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Property 7: 不同 Report_Scope 可共存
# **Validates: Requirements 3.5**
# ---------------------------------------------------------------------------

@given(prefix=_uscc_prefix)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_different_scope_coexist(prefix: str, engine):
    """Same (company_code, audit_year) with different report_scope → both succeed."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        uscc = make_valid_uscc(prefix)

        # standalone succeeds
        p1 = await _create_project_valid(
            db, company_code=uscc, audit_year=2031, report_scope="standalone",
            short_name="单户项目",
        )
        assert p1.id is not None

        # consolidated with same code+year also succeeds
        p2 = await _create_project_valid(
            db, company_code=uscc, audit_year=2031, report_scope="consolidated",
            short_name="合并项目",
        )
        assert p2.id is not None
        assert p1.id != p2.id


# ---------------------------------------------------------------------------
# Property 8: 软删除项目不阻塞新建
# **Validates: Requirements 3.7**
# ---------------------------------------------------------------------------

@given(prefix=_uscc_prefix)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_soft_deleted_does_not_block(prefix: str, engine):
    """Soft-deleted project with same triple → new creation succeeds."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        uscc = make_valid_uscc(prefix)

        # Create first project
        p1 = await _create_project_valid(
            db, company_code=uscc, audit_year=2032, report_scope="standalone",
            short_name="将被删除",
        )

        # Soft-delete it
        p1.is_deleted = True
        await db.commit()

        # New creation with same triple succeeds
        p2 = await _create_project_valid(
            db, company_code=uscc, audit_year=2032, report_scope="standalone",
            short_name="新项目",
        )
        assert p2.id is not None
        assert p2.id != p1.id


# ---------------------------------------------------------------------------
# Property 12: 并发创建同三元组至多一个成功（pg_only）
# **Validates: Requirements 3.1 并发安全**
# ---------------------------------------------------------------------------

@pytest.mark.pg_only
@given(prefix=_uscc_prefix)
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_concurrent_create_at_most_one_succeeds(prefix: str, engine):
    """Property 12: 并发创建同三元组时，DB 唯一索引保证至多一个成功。

    注意：此测试依赖真实 PG 的 partial unique index，SQLite 无等价约束，
    标记 pg_only 在 SQLite 环境下自动 skip。
    """
    import asyncio
    from fastapi import HTTPException
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    uscc = make_valid_uscc(prefix)

    async def _try_create(session_idx: int):
        async with factory() as db:
            data = BasicInfoSchema(
                client_name=f"并发客户{session_idx}",
                audit_year=2099,
                project_type="annual",
                accounting_standard="enterprise",
                company_code=uscc,
                short_name=f"并发简称{session_idx}",
                report_scope="standalone",
            )
            return await create_project(data, db)

    results = await asyncio.gather(
        _try_create(1),
        _try_create(2),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, (Exception, BaseException))]
    # DB 唯一约束保证至多一个成功
    assert len(successes) <= 1, f"Expected at most 1 success, got {len(successes)}"
