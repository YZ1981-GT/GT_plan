"""Round 6 GateRule 测试：KAM 确认 + 独立性确认

4 场景：
1. KAM 未确认 → 阻断
2. 独立性未确认 → 阻断
3. 两者都确认 → 通过（无 hit）
4. extra_findings 不再包含冗余的 KAM/independence 项
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
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
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.services.gate_rules_round6 import (  # noqa: E402
    KamConfirmedRule,
    IndependenceConfirmedRule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def user(db_session: AsyncSession):
    u = User(
        id=uuid.uuid4(),
        username="test_user",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _create_project(
    db: AsyncSession, user_id: uuid.UUID, wizard_state: dict
) -> Project:
    """创建测试项目并设置 wizard_state"""
    proj = Project(
        id=uuid.uuid4(),
        name="Test Project",
        client_name="Test Client",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
        wizard_state=wizard_state,
    )
    db.add(proj)
    await db.flush()
    return proj


# ---------------------------------------------------------------------------
# 场景 1：KAM 未确认 → 阻断
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kam_not_confirmed_blocks(db_session: AsyncSession, user):
    """KAM 未确认时，KamConfirmedRule 应返回 blocking hit"""
    proj = await _create_project(
        db_session, user.id, {"kam_confirmed": False, "independence_confirmed": True}
    )

    rule = KamConfirmedRule()
    context = {"project_id": proj.id}
    hit = await rule.check(db_session, context)

    assert hit is not None
    assert hit.rule_code == "R6-KAM"
    assert hit.error_code == "KAM_NOT_CONFIRMED"
    assert hit.severity == "blocking"
    assert "关键审计事项" in hit.message


# ---------------------------------------------------------------------------
# 场景 2：独立性未确认 → 阻断
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_independence_not_confirmed_blocks(db_session: AsyncSession, user):
    """独立性未确认时，IndependenceConfirmedRule 应返回 blocking hit"""
    proj = await _create_project(
        db_session, user.id, {"kam_confirmed": True, "independence_confirmed": False}
    )

    rule = IndependenceConfirmedRule()
    context = {"project_id": proj.id}
    hit = await rule.check(db_session, context)

    assert hit is not None
    assert hit.rule_code == "R6-INDEPENDENCE"
    assert hit.error_code == "INDEPENDENCE_NOT_CONFIRMED"
    assert hit.severity == "blocking"
    assert "独立性" in hit.message


# ---------------------------------------------------------------------------
# 场景 3：两者都确认 → 通过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_confirmed_passes(db_session: AsyncSession, user):
    """KAM + 独立性都确认时，两条规则均返回 None（通过）"""
    proj = await _create_project(
        db_session, user.id, {"kam_confirmed": True, "independence_confirmed": True}
    )

    context = {"project_id": proj.id}

    kam_rule = KamConfirmedRule()
    indep_rule = IndependenceConfirmedRule()

    assert await kam_rule.check(db_session, context) is None
    assert await indep_rule.check(db_session, context) is None


# ---------------------------------------------------------------------------
# 场景 4：extra_findings 不再包含冗余的 KAM/independence 项
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extra_findings_no_redundant_kam_independence(db_session: AsyncSession, user):
    """partner_service._compute_sign_extra_findings 不再产出 KAM/independence 项，
    验证 gate 规则覆盖后 extra_findings 无冗余。
    """
    proj = await _create_project(
        db_session, user.id, {"kam_confirmed": False, "independence_confirmed": False}
    )

    # 模拟调用 _compute_sign_extra_findings 的逻辑：
    # 由于已移除 KAM/independence 检查，extra_findings 中不应出现这两个 category
    from app.services.partner_service import SignReadinessService

    svc = SignReadinessService(db_session)
    extra = await svc._compute_sign_extra_findings(proj.id, proj)

    # 验证 extra_findings 中不包含 kam_confirmed 和 independence 类目
    assert "kam_confirmed" not in extra, (
        "extra_findings 不应再包含 kam_confirmed（已由 R6-KAM GateRule 覆盖）"
    )
    assert "independence" not in extra, (
        "extra_findings 不应再包含 independence（已由 R6-INDEPENDENCE GateRule 覆盖）"
    )
