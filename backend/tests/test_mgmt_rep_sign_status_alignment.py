"""Task 22: QC wizard_state 管理层声明 与主版本 sign_status 对齐

验证 MgmtRepresentationRule 读取 field_overrides A16 主版本 sign_status：
1. signed → 通过（无 hit）
2. sent → warning（进行中）
3. pending → blocking（未开始）
4. 无 selected_version 时 fallback 到 wizard_state 布尔标记
5. wizard_state.mgmt_representation_obtained=True 向后兼容
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

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
from app.models.workpaper_field_override_models import WorkpaperFieldOverride  # noqa: E402
from app.services.gate_rules_round6 import MgmtRepresentationRule  # noqa: E402
from app.services.field_override_service import FieldOverrideService  # noqa: E402


FAKE_USER_ID = uuid.uuid4()
YEAR = 2025


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
        id=FAKE_USER_ID,
        username="test_user",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _create_project(
    db: AsyncSession,
    user_id: uuid.UUID,
    wizard_state: dict | None = None,
    audit_period_end: date | None = None,
) -> Project:
    proj = Project(
        id=uuid.uuid4(),
        name="Test Project A16",
        client_name="Test Client",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
        wizard_state=wizard_state,
        audit_period_end=audit_period_end or date(YEAR, 12, 31),
    )
    db.add(proj)
    await db.flush()
    return proj


async def _set_field_override(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    scope: str,
    item_key: str,
    field: str,
    value,
):
    svc = FieldOverrideService(db)
    await svc.set(project_id, year, scope, item_key, field, value, FAKE_USER_ID)
    await db.flush()


# ---------------------------------------------------------------------------
# 场景 1：主版本 sign_status = signed → 通过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_main_version_passes(db_session: AsyncSession, user):
    """A16 主版本 sign_status=signed → MgmtRepresentationRule 通过"""
    proj = await _create_project(db_session, user.id)

    # 设置 selected_version = A16-1
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-1"
    )
    # 设置 A16-1 sign_status = signed
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-1", "sign_status", "value", "signed"
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is None


# ---------------------------------------------------------------------------
# 场景 2：主版本 sign_status = sent → warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sent_main_version_returns_warning(db_session: AsyncSession, user):
    """A16 主版本 sign_status=sent → MgmtRepresentationRule 返回 warning"""
    proj = await _create_project(db_session, user.id)

    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-3"
    )
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-3", "sign_status", "value", "sent"
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is not None
    assert hit.rule_code == "R7-MGMT-REP"
    assert hit.error_code == "MGMT_REP_SENT_NOT_SIGNED"
    assert hit.severity == "warning"
    assert "已发出" in hit.message


# ---------------------------------------------------------------------------
# 场景 3：主版本 sign_status = pending → blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_main_version_blocks(db_session: AsyncSession, user):
    """A16 主版本 sign_status=pending → MgmtRepresentationRule 阻断"""
    proj = await _create_project(db_session, user.id)

    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-2"
    )
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-2", "sign_status", "value", "pending"
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is not None
    assert hit.rule_code == "R7-MGMT-REP"
    assert hit.error_code == "MGMT_REP_NOT_OBTAINED"
    assert hit.severity == "blocking"


# ---------------------------------------------------------------------------
# 场景 4：有 selected_version 但无 sign_status → blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sign_status_for_version_blocks(db_session: AsyncSession, user):
    """有 selected_version 但该版本无 sign_status 记录 → 阻断"""
    proj = await _create_project(db_session, user.id)

    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-5"
    )
    # 不设置 sign_status

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    # sign_status is None → field_overrides 无数据分支 → fallback 到 wizard_state
    # wizard_state 也无 → blocking
    assert hit is not None
    assert hit.severity == "blocking"


# ---------------------------------------------------------------------------
# 场景 5：无 selected_version，wizard_state=True → 通过（向后兼容）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_field_overrides_wizard_state_true_passes(db_session: AsyncSession, user):
    """无 field_overrides A16 数据，wizard_state.mgmt_representation_obtained=True → 通过"""
    proj = await _create_project(
        db_session, user.id,
        wizard_state={"mgmt_representation_obtained": True},
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is None


# ---------------------------------------------------------------------------
# 场景 6：无 selected_version，wizard_state=False → blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_field_overrides_wizard_state_false_blocks(db_session: AsyncSession, user):
    """无 field_overrides A16 数据，wizard_state.mgmt_representation_obtained=False → 阻断"""
    proj = await _create_project(
        db_session, user.id,
        wizard_state={"mgmt_representation_obtained": False},
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is not None
    assert hit.severity == "blocking"


# ---------------------------------------------------------------------------
# 场景 7：主版本 signed 覆盖 wizard_state=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_field_overrides_signed_overrides_wizard_state_false(db_session: AsyncSession, user):
    """field_overrides sign_status=signed 优先于 wizard_state=False"""
    proj = await _create_project(
        db_session, user.id,
        wizard_state={"mgmt_representation_obtained": False},
    )

    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-1"
    )
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-1", "sign_status", "value", "signed"
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    assert hit is None


# ---------------------------------------------------------------------------
# 场景 8：不同主版本独立
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_version_status_independent(db_session: AsyncSession, user):
    """selected_version=A16-2 signed 通过；即使 A16-1=pending 无影响"""
    proj = await _create_project(db_session, user.id)

    # selected = A16-2, signed
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16", "selected_version", "value", "A16-2"
    )
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-2", "sign_status", "value", "signed"
    )
    # A16-1 仍为 pending
    await _set_field_override(
        db_session, proj.id, YEAR,
        "word_template:A16:A16-1", "sign_status", "value", "pending"
    )

    rule = MgmtRepresentationRule()
    hit = await rule.check(db_session, {"project_id": proj.id})
    # 只看 selected_version (A16-2) → signed → 通过
    assert hit is None
