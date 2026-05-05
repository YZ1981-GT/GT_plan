"""R5 任务 2：EQCR 独立性 SOD 规则单元测试

覆盖 design.md "SOD 规则细节" 约定的 4 个场景：

1. 先委派 signing_partner，再委派同人为 eqcr 同项目 → 拒绝
2. 先委派 eqcr，再委派同人为 auditor 同项目 → 拒绝
3. A 项目 eqcr、B 项目 manager（不同项目，同一人）→ 通过
4. 首次委派 eqcr 到新项目 → 通过

另补充批量模式（``proposed_roles``）与非冲突角色（如 qc）共存的小回归。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

# 独立测试 engine，避免与其他测试共享表
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型（顺序对齐 conftest.py）
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

from app.models.core import Project  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.services.sod_guard_service import (  # noqa: E402
    EqcrIndependenceRule,
    SodViolation,
)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_setup(db_session):
    """建两个项目 + 一个人员，返回 (project_a, project_b, staff)。"""
    p_a = Project(name="项目 A", client_name="客户甲")
    p_b = Project(name="项目 B", client_name="客户乙")
    staff = StaffMember(name="张三", employee_no="E-100")
    db_session.add_all([p_a, p_b, staff])
    await db_session.flush()
    return p_a, p_b, staff


# ---------------------------------------------------------------------------
# 场景 1：signing_partner → eqcr（同项目同人）→ 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario1_signing_partner_then_eqcr_rejected(db_session, sample_setup):
    project_a, _project_b, staff = sample_setup

    pa = ProjectAssignment(
        project_id=project_a.id,
        staff_id=staff.id,
        role="signing_partner",
    )
    db_session.add(pa)
    await db_session.flush()

    rule = EqcrIndependenceRule()
    with pytest.raises(SodViolation) as excinfo:
        await rule.check(
            db_session,
            project_id=project_a.id,
            staff_id=staff.id,
            new_role="eqcr",
        )
    assert excinfo.value.policy_code == "SOD_EQCR_INDEPENDENCE_CONFLICT"
    assert "signing_partner" in str(excinfo.value) or "EQCR" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 场景 2：eqcr → auditor（同项目同人）→ 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario2_eqcr_then_auditor_rejected(db_session, sample_setup):
    project_a, _project_b, staff = sample_setup

    pa = ProjectAssignment(
        project_id=project_a.id,
        staff_id=staff.id,
        role="eqcr",
    )
    db_session.add(pa)
    await db_session.flush()

    rule = EqcrIndependenceRule()
    with pytest.raises(SodViolation) as excinfo:
        await rule.check(
            db_session,
            project_id=project_a.id,
            staff_id=staff.id,
            new_role="auditor",
        )
    assert excinfo.value.policy_code == "SOD_EQCR_INDEPENDENCE_CONFLICT"


# ---------------------------------------------------------------------------
# 场景 3：A 项目 eqcr、B 项目 manager（不同项目）→ 通过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario3_different_projects_pass(db_session, sample_setup):
    project_a, project_b, staff = sample_setup

    # A 项目：张三 = EQCR
    db_session.add(
        ProjectAssignment(
            project_id=project_a.id,
            staff_id=staff.id,
            role="eqcr",
        )
    )
    await db_session.flush()

    # B 项目：张三 = manager 应放行
    rule = EqcrIndependenceRule()
    await rule.check(
        db_session,
        project_id=project_b.id,
        staff_id=staff.id,
        new_role="manager",
    )  # 不抛异常即通过


# ---------------------------------------------------------------------------
# 场景 4：首次委派 eqcr（新项目无任何委派）→ 通过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario4_first_eqcr_assignment_pass(db_session, sample_setup):
    project_a, _project_b, staff = sample_setup
    rule = EqcrIndependenceRule()
    await rule.check(
        db_session,
        project_id=project_a.id,
        staff_id=staff.id,
        new_role="eqcr",
    )  # 无任何现存委派，直接放行


# ---------------------------------------------------------------------------
# 补充：eqcr 与 qc 不冲突（qc 不在 CONFLICT_ROLES）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qc_does_not_conflict_with_eqcr(db_session, sample_setup):
    project_a, _project_b, staff = sample_setup

    # 先 qc
    db_session.add(
        ProjectAssignment(
            project_id=project_a.id,
            staff_id=staff.id,
            role="qc",
        )
    )
    await db_session.flush()

    rule = EqcrIndependenceRule()
    # qc 在现有列表中，但 qc 不属于 CONFLICT_ROLES，所以新增 eqcr 放行
    await rule.check(
        db_session,
        project_id=project_a.id,
        staff_id=staff.id,
        new_role="eqcr",
    )


# ---------------------------------------------------------------------------
# 补充：批量模式 proposed_roles 同时含 eqcr 与 signing_partner → 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_proposed_roles_eqcr_vs_signing_partner_raises(db_session, sample_setup):
    """同一批 save_assignments 请求中若同一个人同时被委派 EQCR + 冲突角色，
    规则应在批次内检出冲突，无需依赖 DB 状态。"""
    project_a, _project_b, staff = sample_setup

    proposed = [
        (staff.id, "eqcr"),
        (staff.id, "signing_partner"),
    ]
    rule = EqcrIndependenceRule()
    with pytest.raises(SodViolation):
        await rule.check(
            db_session,
            project_id=project_a.id,
            staff_id=staff.id,
            new_role="eqcr",
            proposed_roles=proposed,
        )


# ---------------------------------------------------------------------------
# 补充：非 eqcr/非 conflict 的角色（如 readonly）不走校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_irrelevant_role_pass(db_session, sample_setup):
    project_a, _project_b, staff = sample_setup
    rule = EqcrIndependenceRule()
    # readonly 不在 conflict 集合，也不是 eqcr，直接短路
    await rule.check(
        db_session,
        project_id=project_a.id,
        staff_id=staff.id,
        new_role="readonly",
    )
