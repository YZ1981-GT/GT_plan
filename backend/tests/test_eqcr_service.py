"""EQCR 工作台服务单元测试

Refinement Round 5 任务 3 验证目标：

1. ``test_list_my_projects_empty`` — 没有 EQCR 委派时返回空
2. ``test_list_my_projects_basic`` — 委派一个 EQCR 项目并录 2 条 opinion，
   验证进度 / 判断事项 counts / 签字日排序
3. ``test_get_project_overview_basic`` — overview 返回结构字段齐全
4. ``test_list_my_projects_sort_by_signing_date`` — 多个项目按签字日升序
5. ``test_list_my_projects_disagree_progress`` — 含 disagree 的 opinion 切
   进度到 ``disagree``
6. ``test_list_my_projects_only_eqcr_role`` — 同人兼任其他角色的项目不混入

按 ``refinement-round5-independent-review/design.md`` "EQCR 工作台复用
ProjectAssignment.role='eqcr'" 决策，测试直接操作底层 ORM 建数据，
不触碰 SOD 规则层（SOD 已在 ``test_eqcr_independence_sod.py`` 覆盖）。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

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

# 独立 engine，避免与其他测试共享表
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型（与 conftest.py / test_eqcr_independence_sod.py 保持一致）
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

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrOpinion  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.services.eqcr_service import (  # noqa: E402
    EQCR_CORE_DOMAINS,
    PROGRESS_DISAGREE,
    PROGRESS_IN_PROGRESS,
    PROGRESS_NOT_STARTED,
    EqcrService,
)


# ---------------------------------------------------------------------------
# 基础 fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


async def _make_user(db: AsyncSession, *, role: UserRole = UserRole.partner) -> User:
    user = User(
        id=uuid.uuid4(),
        username=f"u-{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.com",
        hashed_password="x",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_staff(
    db: AsyncSession, user_id: uuid.UUID | None = None, name: str = "张三"
) -> StaffMember:
    staff = StaffMember(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        employee_no=f"E-{uuid.uuid4().hex[:6]}",
    )
    db.add(staff)
    await db.flush()
    return staff


async def _make_project(
    db: AsyncSession,
    *,
    name: str = "项目 A",
    client_name: str = "客户 A",
    audit_period_end: date | None = None,
) -> Project:
    proj = Project(
        id=uuid.uuid4(),
        name=name,
        client_name=client_name,
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=audit_period_end,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _assign_eqcr(db: AsyncSession, project_id: uuid.UUID, staff_id: uuid.UUID) -> None:
    db.add(
        ProjectAssignment(
            project_id=project_id,
            staff_id=staff_id,
            role="eqcr",
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# 测试 1：没有 EQCR 委派返回空
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_empty(db_session):
    """用户不存在 StaffMember，或 StaffMember 无 eqcr 委派 → 空列表。"""
    user = await _make_user(db_session)

    svc = EqcrService(db_session)

    # 1a. 用户完全没有 staff 记录
    assert await svc.list_my_projects(user.id) == []

    # 1b. 有 staff 记录但无任何委派
    await _make_staff(db_session, user.id)
    assert await svc.list_my_projects(user.id) == []

    # 1c. 有非 eqcr 委派（manager）不应返回
    proj = await _make_project(db_session)
    db_session.add(
        ProjectAssignment(
            project_id=proj.id,
            staff_id=(await _resolve_single_staff_id(db_session, user.id)),
            role="manager",
        )
    )
    await db_session.flush()
    assert await svc.list_my_projects(user.id) == []


async def _resolve_single_staff_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    from sqlalchemy import select

    sid = (
        await db.execute(select(StaffMember.id).where(StaffMember.user_id == user_id))
    ).scalar_one()
    return sid


# ---------------------------------------------------------------------------
# 测试 2：基础项目卡片（进度 + counts）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_basic(db_session):
    """委派一个 EQCR 项目 + 2 条 opinion → 验证进度 in_progress，
    counts 为 {unreviewed: 3, reviewed: 2}。"""
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)

    # 签字日 10 天后
    signing = date.today() + timedelta(days=10)
    proj = await _make_project(
        db_session,
        name="项目 A",
        audit_period_end=signing,
    )
    await _assign_eqcr(db_session, proj.id, staff.id)

    # 录 2 条 opinion（agree / agree），剩余 3 个 domain 未录
    db_session.add_all(
        [
            EqcrOpinion(
                project_id=proj.id,
                domain="materiality",
                verdict="agree",
                comment="认可整体重要性",
                created_by=user.id,
            ),
            EqcrOpinion(
                project_id=proj.id,
                domain="estimate",
                verdict="agree",
                created_by=user.id,
            ),
        ]
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)

    assert len(cards) == 1
    card = cards[0]
    assert card["project_id"] == str(proj.id)
    assert card["project_name"] == "项目 A"
    assert card["client_name"] == "客户 A"
    assert card["signing_date"] == signing.isoformat()
    assert card["days_to_signing"] == 10

    # 2 个 domain reviewed，3 个未 reviewed
    assert card["judgment_counts"] == {"unreviewed": 3, "reviewed": 2}

    # 没全部 agree 也没 disagree → in_progress
    assert card["my_progress"] == PROGRESS_IN_PROGRESS


# ---------------------------------------------------------------------------
# 测试 3：项目 overview 返回结构
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_overview_basic(db_session):
    """overview 返回结构包含 project / my_role_confirmed / opinion_summary 等字段。"""
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)

    signing = date.today() + timedelta(days=5)
    proj = await _make_project(
        db_session,
        name="项目 B",
        client_name="客户 B",
        audit_period_end=signing,
    )
    await _assign_eqcr(db_session, proj.id, staff.id)

    # 录一条 disagree 意见 + 一条 agree
    db_session.add_all(
        [
            EqcrOpinion(
                project_id=proj.id,
                domain="materiality",
                verdict="agree",
                created_by=user.id,
            ),
            EqcrOpinion(
                project_id=proj.id,
                domain="opinion_type",
                verdict="disagree",
                comment="保留意见应该升级为否定意见",
                created_by=user.id,
            ),
        ]
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    overview = await svc.get_project_overview(user.id, proj.id)

    assert overview is not None
    # project 子对象字段齐全
    assert overview["project"]["id"] == str(proj.id)
    assert overview["project"]["name"] == "项目 B"
    assert overview["project"]["client_name"] == "客户 B"
    assert overview["project"]["signing_date"] == signing.isoformat()

    # my_role_confirmed 因为做了 eqcr 委派 = True
    assert overview["my_role_confirmed"] is True

    # opinion_summary: 5 个 domain key 都在，已录的返回 verdict，未录的返回 None
    by_domain = overview["opinion_summary"]["by_domain"]
    assert set(by_domain.keys()) == set(EQCR_CORE_DOMAINS)
    assert by_domain["materiality"] == "agree"
    assert by_domain["opinion_type"] == "disagree"
    assert by_domain["estimate"] is None
    assert overview["opinion_summary"]["total"] == 2

    # 未建异议合议记录 → disagreement_count 应为 1（未解决）
    assert overview["disagreement_count"] == 1

    # 其他计数
    assert overview["note_count"] == 0
    assert overview["shadow_comp_count"] == 0

    # 不存在的项目返回 None
    assert await svc.get_project_overview(user.id, uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# 测试 4：签字日排序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_sort_by_signing_date(db_session):
    """多个项目按签字日升序排列，无签字日的排在最后。"""
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)

    p_late = await _make_project(
        db_session,
        name="P-late",
        audit_period_end=date.today() + timedelta(days=30),
    )
    p_early = await _make_project(
        db_session,
        name="P-early",
        audit_period_end=date.today() + timedelta(days=3),
    )
    p_none = await _make_project(db_session, name="P-none", audit_period_end=None)

    for p in (p_late, p_early, p_none):
        await _assign_eqcr(db_session, p.id, staff.id)

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)

    names = [c["project_name"] for c in cards]
    assert names == ["P-early", "P-late", "P-none"]


# ---------------------------------------------------------------------------
# 测试 5：含 disagree → 进度切到 disagree
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_disagree_progress(db_session):
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)
    proj = await _make_project(db_session, name="项目 C")
    await _assign_eqcr(db_session, proj.id, staff.id)

    db_session.add(
        EqcrOpinion(
            project_id=proj.id,
            domain="materiality",
            verdict="disagree",
            created_by=user.id,
        )
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)

    assert len(cards) == 1
    assert cards[0]["my_progress"] == PROGRESS_DISAGREE


# ---------------------------------------------------------------------------
# 测试 6：非 eqcr 委派的项目不出现
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_only_eqcr_role(db_session):
    """同一个 user 在 A 项目是 eqcr，在 B 项目是 qc，只返回 A。"""
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)

    p_a = await _make_project(db_session, name="A 项目", client_name="客户 A")
    p_b = await _make_project(db_session, name="B 项目", client_name="客户 B")

    await _assign_eqcr(db_session, p_a.id, staff.id)
    db_session.add(
        ProjectAssignment(project_id=p_b.id, staff_id=staff.id, role="qc")
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)
    assert len(cards) == 1
    assert cards[0]["project_name"] == "A 项目"


# ---------------------------------------------------------------------------
# 测试 7：没有任何 opinion 时进度 = not_started
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_projects_not_started(db_session):
    user = await _make_user(db_session)
    staff = await _make_staff(db_session, user.id)
    proj = await _make_project(db_session)
    await _assign_eqcr(db_session, proj.id, staff.id)

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)
    assert len(cards) == 1
    assert cards[0]["my_progress"] == PROGRESS_NOT_STARTED
    assert cards[0]["judgment_counts"] == {"unreviewed": 5, "reviewed": 0}


# ---------------------------------------------------------------------------
# 测试 8：overview 对非 EQCR 用户返回 my_role_confirmed=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_overview_not_eqcr_user(db_session):
    """非项目 EQCR 的用户调用 overview，my_role_confirmed=False。"""
    eqcr_user = await _make_user(db_session)
    eqcr_staff = await _make_staff(db_session, eqcr_user.id, name="EQCR")
    other_user = await _make_user(db_session)

    proj = await _make_project(db_session)
    await _assign_eqcr(db_session, proj.id, eqcr_staff.id)

    svc = EqcrService(db_session)
    overview = await svc.get_project_overview(other_user.id, proj.id)
    assert overview is not None
    assert overview["my_role_confirmed"] is False
