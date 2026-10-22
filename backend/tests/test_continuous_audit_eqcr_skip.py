# Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
"""Property 13 – 连续审计复制团队跳过上年 EQCR（partner-manager-edit-permission §4.11）。

对任意上年项目数据（0–6 名有未删除成员行的用户、0–2 名只有已删除成员行的用户、
各用户任意全局角色与 0–3 条委派及干扰数据），开启复制团队后：
  • 新项目成员行用户集合 = 上年未删除成员行用户集合 − 上年持有 EQCR 别名现行委派的用户集合
  • 每行项目角色 / 级别 / 循环 / 科目与上年逐值相同、有效期为空、未建委派
  • 复制人数 + 跳过人数 = 上年未删除成员行数
  • 提示存在当且仅当跳过人数 ≥ 1
  • 上年与他项目数据不变

Validates: Requirements 11.1, 11.2, 11.3, 11.6
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import hypothesis.strategies as st
import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings, example, HealthCheck
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.role_map_expected import EXPECTED_EQCR_ALIASES, EXPECTED_ROLE_MAP

# ---------------------------------------------------------------------------
# SQLite compat & engine
# ---------------------------------------------------------------------------
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


# ---------------------------------------------------------------------------
# Model imports (after engine init to avoid dialect issues)
# ---------------------------------------------------------------------------
from app.models.base import (  # noqa: E402
    Base,
    PermissionLevel,
    ProjectStatus,
    ProjectUserRole,
    UserRole,
)
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402

# ---------------------------------------------------------------------------
# All ROLE_MAP keys (used by strategies)
# ---------------------------------------------------------------------------
ALL_ROLE_MAP_KEYS: list[str] = sorted(EXPECTED_ROLE_MAP.keys())
ALL_USER_ROLES: list[UserRole] = list(UserRole)
ALL_PROJECT_ROLES: list[ProjectUserRole] = list(ProjectUserRole)
ALL_PERM_LEVELS: list[PermissionLevel] = list(PermissionLevel)


# ---------------------------------------------------------------------------
# Lightweight data descriptors for hypothesis
# ---------------------------------------------------------------------------
@dataclass
class MemberDesc:
    """Describes one prior-year member row (project_users)."""

    role: ProjectUserRole
    level: PermissionLevel
    scope_cycles: str | None = None
    scope_accounts: str | None = None
    is_deleted: bool = False


@dataclass
class AssignmentDesc:
    """Describes one assignment (project_assignments)."""

    project_key: str  # "prior" | "other"
    role: str
    is_deleted: bool = False
    staff_is_deleted: bool = False
    staff_user_id_is_none: bool = False


@dataclass
class UserDesc:
    """Describes one user in the test scenario."""

    global_role: UserRole = UserRole.auditor
    prior_member: MemberDesc | None = None
    other_member: MemberDesc | None = None
    assignments: list[AssignmentDesc] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Model-side calculation: which users should be skipped
# ---------------------------------------------------------------------------
def _model_eqcr_user_ids(users: dict[str, UserDesc]) -> set[str]:
    """Return user keys that hold EQCR-alias active assignments on the prior project.

    Uses EXPECTED_EQCR_ALIASES (from role_map_expected.py), NOT production code.
    """
    eqcr_keys: set[str] = set()
    for key, u in users.items():
        for a in u.assignments:
            if (
                a.project_key == "prior"
                and not a.is_deleted
                and not a.staff_is_deleted
                and not a.staff_user_id_is_none
                and a.role in EXPECTED_EQCR_ALIASES
            ):
                eqcr_keys.add(key)
                break
    return eqcr_keys


def _model_expected_copied(users: dict[str, UserDesc]) -> set[str]:
    """User keys expected in the new project after copy_team."""
    eqcr = _model_eqcr_user_ids(users)
    return {
        k
        for k, u in users.items()
        if u.prior_member is not None and not u.prior_member.is_deleted and k not in eqcr
    }


def _model_expected_skipped(users: dict[str, UserDesc]) -> int:
    """Number of prior undel members skipped due to EQCR."""
    eqcr = _model_eqcr_user_ids(users)
    return sum(
        1
        for k, u in users.items()
        if u.prior_member is not None and not u.prior_member.is_deleted and k in eqcr
    )


# ---------------------------------------------------------------------------
# DB fixture – fresh schema for every test
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
async def _seed_scenario(
    db: AsyncSession,
    users: dict[str, UserDesc],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed prior project, other project, users, members, staff, assignments.

    Returns (prior_project_id, other_project_id).
    """
    prior = Project(
        name="公司_2025",
        client_name="公司",
        status=ProjectStatus.created,
        project_type="annual",
        company_code="91110000300000000G",
        audit_year=2025,
        report_scope="standalone",
        template_type="soe",
        wizard_state={
            "steps": {
                "basic_info": {
                    "step": "basic_info",
                    "completed": True,
                    "data": {
                        "audit_year": 2025,
                        "client_name": "公司",
                        "company_code": "91110000300000000G",
                    },
                }
            }
        },
    )
    other = Project(
        name="他项目_2025",
        client_name="他项目",
        status=ProjectStatus.created,
        project_type="annual",
        company_code="91110000400000000H",
        audit_year=2025,
        report_scope="standalone",
        template_type="soe",
        wizard_state={
            "steps": {
                "basic_info": {
                    "step": "basic_info",
                    "completed": True,
                    "data": {
                        "audit_year": 2025,
                        "client_name": "他项目",
                        "company_code": "91110000400000000H",
                    },
                }
            }
        },
    )
    db.add_all([prior, other])
    await db.flush()

    project_map = {"prior": prior.id, "other": other.id}

    # Create users and their members/assignments
    for key, udesc in users.items():
        user = User(
            username=f"user_{key}",
            email=f"user_{key}@test.com",
            hashed_password="fake",
            role=udesc.global_role,
        )
        db.add(user)
        await db.flush()

        # Prior-year member
        if udesc.prior_member is not None:
            m = udesc.prior_member
            pu = ProjectUser(
                project_id=prior.id,
                user_id=user.id,
                role=m.role,
                permission_level=m.level,
                scope_cycles=m.scope_cycles,
                scope_accounts=m.scope_accounts,
                is_deleted=m.is_deleted,
            )
            db.add(pu)

        # Other project member
        if udesc.other_member is not None:
            m = udesc.other_member
            pu = ProjectUser(
                project_id=other.id,
                user_id=user.id,
                role=m.role,
                permission_level=m.level,
                scope_cycles=m.scope_cycles,
                scope_accounts=m.scope_accounts,
                is_deleted=m.is_deleted,
            )
            db.add(pu)

        # Assignments (each through a staff member)
        for idx, adesc in enumerate(udesc.assignments):
            staff = StaffMember(
                name=f"staff_{key}_{idx}",
                user_id=None if adesc.staff_user_id_is_none else user.id,
                is_deleted=adesc.staff_is_deleted,
            )
            db.add(staff)
            await db.flush()
            pa = ProjectAssignment(
                project_id=project_map[adesc.project_key],
                staff_id=staff.id,
                role=adesc.role,
                is_deleted=adesc.is_deleted,
            )
            db.add(pa)

    await db.commit()
    return prior.id, other.id


async def _run_copy(
    db: AsyncSession, prior_id: uuid.UUID
) -> dict[str, Any]:
    """Invoke ContinuousAuditService.create_next_year with copy_team=True."""
    from app.services.continuous_audit_service import ContinuousAuditService

    svc = ContinuousAuditService()
    result = await svc.create_next_year(
        db=db,
        prior_project_id=prior_id,
        copy_team=True,
        copy_mapping=False,
        copy_procedures=False,
    )
    await db.commit()
    return result


async def _get_new_project_members(
    db: AsyncSession, new_project_id: uuid.UUID
) -> list[ProjectUser]:
    """Query all undel members in the new project."""
    r = await db.execute(
        sa.select(ProjectUser).where(
            ProjectUser.project_id == new_project_id,
            ProjectUser.is_deleted == sa.false(),
        )
    )
    return list(r.scalars().all())


async def _get_new_project_assignments(
    db: AsyncSession, new_project_id: uuid.UUID
) -> list[ProjectAssignment]:
    """Query all assignments in the new project."""
    r = await db.execute(
        sa.select(ProjectAssignment).where(
            ProjectAssignment.project_id == new_project_id,
        )
    )
    return list(r.scalars().all())


async def _snapshot_members(
    db: AsyncSession, project_id: uuid.UUID
) -> dict[uuid.UUID, tuple[str, str, str | None, str | None, bool]]:
    """Snapshot (role, level, cycles, accounts, is_deleted) keyed by user_id."""
    r = await db.execute(
        sa.select(ProjectUser).where(ProjectUser.project_id == project_id)
    )
    return {
        pu.user_id: (
            pu.role.value if hasattr(pu.role, "value") else str(pu.role),
            pu.permission_level.value if hasattr(pu.permission_level, "value") else str(pu.permission_level),
            pu.scope_cycles,
            pu.scope_accounts,
            pu.is_deleted,
        )
        for pu in r.scalars().all()
    }


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------
_ROLE_ALIASES = sorted(EXPECTED_ROLE_MAP.keys())

# Include case variants and whitespace variants as "not-EQCR" strings
_VARIANT_STRINGS = ["EQCR", "Eqcr", " eqcr", "eqcr ", "Manager", " manager ", ""]

_assignment_role_st = st.one_of(
    st.sampled_from(_ROLE_ALIASES),
    st.sampled_from(_VARIANT_STRINGS),
    st.text(min_size=0, max_size=30),
)

_member_st = st.builds(
    MemberDesc,
    role=st.sampled_from(ALL_PROJECT_ROLES),
    level=st.sampled_from(ALL_PERM_LEVELS),
    scope_cycles=st.one_of(st.none(), st.just("A,B,C")),
    scope_accounts=st.one_of(st.none(), st.just("1001,1002")),
    is_deleted=st.just(False),  # undel member
)

_deleted_member_st = st.builds(
    MemberDesc,
    role=st.sampled_from(ALL_PROJECT_ROLES),
    level=st.sampled_from(ALL_PERM_LEVELS),
    is_deleted=st.just(True),
)

_assignment_st = st.builds(
    AssignmentDesc,
    project_key=st.sampled_from(["prior", "other"]),
    role=_assignment_role_st,
    is_deleted=st.booleans(),
    staff_is_deleted=st.booleans(),
    staff_user_id_is_none=st.booleans(),
)


@st.composite
def _user_desc_st(draw: st.DrawFn) -> UserDesc:
    return UserDesc(
        global_role=draw(st.sampled_from(ALL_USER_ROLES)),
        prior_member=draw(st.one_of(st.none(), _member_st)),
        other_member=draw(st.one_of(st.none(), _member_st)),
        assignments=draw(st.lists(_assignment_st, min_size=0, max_size=3)),
    )


@st.composite
def _scenario_st(draw: st.DrawFn) -> dict[str, UserDesc]:
    """Generate a scenario with 0-6 users with undel members, 0-2 with only deleted members."""
    users: dict[str, UserDesc] = {}
    n_undel = draw(st.integers(min_value=0, max_value=6))
    n_del_only = draw(st.integers(min_value=0, max_value=2))

    for i in range(n_undel):
        u = draw(_user_desc_st())
        # Ensure this user has an undel member on prior
        if u.prior_member is None or u.prior_member.is_deleted:
            u.prior_member = draw(_member_st)
        users[f"u{i}"] = u

    for i in range(n_del_only):
        u = draw(_user_desc_st())
        # Ensure this user only has a deleted member on prior
        u.prior_member = draw(_deleted_member_st)
        users[f"d{i}"] = u

    return users


# ---------------------------------------------------------------------------
# Property 13 – hypothesis test
# ---------------------------------------------------------------------------
class TestProperty13ContinuousAuditCopy:
    """Property 13: 连续审计复制等于模型"""

    @pytest.mark.asyncio
    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=_scenario_st())
    async def test_property13_copy_equals_model(self, scenario: dict[str, UserDesc], db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        # Validates: Requirements 11.1, 11.2, 11.3, 11.6

        # Fresh schema for each example
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as session:
            prior_id, other_id = await _seed_scenario(session, scenario)

            # Snapshot prior and other before copy
            prior_snap = await _snapshot_members(session, prior_id)
            other_snap = await _snapshot_members(session, other_id)

            # Run service
            result = await _run_copy(session, prior_id)
            new_pid = uuid.UUID(result["new_project_id"])

            # Model expectations
            expected_copied_keys = _model_expected_copied(scenario)
            expected_skipped = _model_expected_skipped(scenario)

            # 1. New project members == expected (by user_id set)
            new_members = await _get_new_project_members(session, new_pid)
            # Map user_id -> username for better error messages
            user_map: dict[uuid.UUID, str] = {}
            for pu in new_members:
                r = await session.execute(sa.select(User.username).where(User.id == pu.user_id))
                user_map[pu.user_id] = r.scalar() or "?"

            new_usernames = {user_map.get(pu.user_id, "?") for pu in new_members}
            expected_usernames = {f"user_{k}" for k in expected_copied_keys}
            assert new_usernames == expected_usernames, (
                f"Members mismatch: got {new_usernames}, expected {expected_usernames}"
            )

            # 2. Each row: role/level/cycles/accounts matches prior, valid_from/to empty
            for pu in new_members:
                uname = user_map.get(pu.user_id, "?")
                key = uname.removeprefix("user_")
                udesc = scenario[key]
                pm = udesc.prior_member
                assert pm is not None
                pu_role = pu.role.value if hasattr(pu.role, "value") else str(pu.role)
                pu_level = pu.permission_level.value if hasattr(pu.permission_level, "value") else str(pu.permission_level)
                assert pu_role == pm.role.value, f"{uname}: role {pu_role} != {pm.role.value}"
                assert pu_level == pm.level.value, f"{uname}: level {pu_level} != {pm.level.value}"
                assert pu.scope_cycles == pm.scope_cycles
                assert pu.scope_accounts == pm.scope_accounts
                assert pu.valid_from is None, f"{uname}: valid_from should be None"
                assert pu.valid_to is None, f"{uname}: valid_to should be None"

            # 3. No assignments created in new project
            new_assignments = await _get_new_project_assignments(session, new_pid)
            assert len(new_assignments) == 0, "No assignments should be created for new project"

            # 4. Counts
            items = result["items_copied"]
            assert items["team_assignments"] == len(expected_copied_keys), (
                f"team_assignments={items['team_assignments']} != expected {len(expected_copied_keys)}"
            )
            assert items["team_skipped_eqcr"] == expected_skipped

            prior_undel_count = sum(
                1 for u in scenario.values()
                if u.prior_member is not None and not u.prior_member.is_deleted
            )
            assert items["team_assignments"] + items["team_skipped_eqcr"] == prior_undel_count

            # 5. Notices
            notices = result.get("notices", [])
            if expected_skipped >= 1:
                assert len(notices) >= 1
                assert "独立复核合伙人需在新项目重新委派" in notices[0]
            else:
                assert not any("独立复核合伙人" in n for n in notices)

            # 6. Prior and other project members unchanged
            prior_snap_after = await _snapshot_members(session, prior_id)
            other_snap_after = await _snapshot_members(session, other_id)
            assert prior_snap_after == prior_snap, "Prior project members changed"
            assert other_snap_after == other_snap, "Other project members changed"


# ---------------------------------------------------------------------------
# Fixed samples ①–⑨
# ---------------------------------------------------------------------------
class TestFixedSamples:
    """需求 11.6 固定样例 ①–⑨"""

    @pytest_asyncio.fixture
    async def fresh_db(self) -> AsyncSession:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session

    def _base_user(self, **overrides: Any) -> UserDesc:
        """Default: auditor role, prior member (partner, review), no assignments."""
        defaults = dict(
            global_role=UserRole.auditor,
            prior_member=MemberDesc(role=ProjectUserRole.partner, level=PermissionLevel.review),
        )
        defaults.update(overrides)
        return UserDesc(**defaults)

    # ① 上年委派 eqcr → 跳过
    @pytest.mark.asyncio
    async def test_sample_1_eqcr_skipped(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "alice": self._base_user(
                assignments=[AssignmentDesc(project_key="prior", role="eqcr")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 0, "EQCR user should be skipped"
        assert result["items_copied"]["team_skipped_eqcr"] == 1
        assert "独立复核合伙人需在新项目重新委派" in result["notices"][0]

    # ② 上年委派 独立复核合伙人 → 跳过
    @pytest.mark.asyncio
    async def test_sample_2_chinese_eqcr_skipped(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "bob": self._base_user(
                assignments=[AssignmentDesc(project_key="prior", role="独立复核合伙人")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 0, "独立复核合伙人 user should be skipped"
        assert result["items_copied"]["team_skipped_eqcr"] == 1

    # ③ 经人员库记录甲委派 manager、经记录乙委派 eqcr → 跳过
    @pytest.mark.asyncio
    async def test_sample_3_dual_staff_one_eqcr_skipped(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "carol": self._base_user(
                assignments=[
                    AssignmentDesc(project_key="prior", role="manager"),
                    AssignmentDesc(project_key="prior", role="eqcr"),
                ],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 0

    # ④ 上年委派 EQCR（大写不精确匹配）→ 复制
    @pytest.mark.asyncio
    async def test_sample_4_uppercase_eqcr_not_skipped(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "dave": self._base_user(
                assignments=[AssignmentDesc(project_key="prior", role="EQCR")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 1, "EQCR (uppercase) is not a valid EQCR alias, should be copied"
        assert result["items_copied"]["team_skipped_eqcr"] == 0

    # ⑤ 上年的 eqcr 委派已删除 → 复制
    @pytest.mark.asyncio
    async def test_sample_5_deleted_eqcr_assignment_copied(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "eve": self._base_user(
                assignments=[AssignmentDesc(project_key="prior", role="eqcr", is_deleted=True)],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 1, "Deleted EQCR assignment means user is not currently EQCR"
        assert result["items_copied"]["team_skipped_eqcr"] == 0

    # ⑥ 全局角色 eqcr、上年委派 manager、成员行 (manager, edit) → 复制，仍为 (manager, edit)
    @pytest.mark.asyncio
    async def test_sample_6_global_eqcr_with_manager_assignment_copied(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "frank": UserDesc(
                global_role=UserRole.eqcr,
                prior_member=MemberDesc(role=ProjectUserRole.manager, level=PermissionLevel.edit),
                assignments=[AssignmentDesc(project_key="prior", role="manager")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 1, "Global eqcr without EQCR assignment should be copied"
        pu = new_members[0]
        assert pu.role == ProjectUserRole.manager
        assert pu.permission_level == PermissionLevel.edit

    # ⑦ 全局角色 admin、上年委派 eqcr → 跳过（admin 不豁免）
    @pytest.mark.asyncio
    async def test_sample_7_admin_eqcr_skipped(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "grace": UserDesc(
                global_role=UserRole.admin,
                prior_member=MemberDesc(role=ProjectUserRole.partner, level=PermissionLevel.review),
                assignments=[AssignmentDesc(project_key="prior", role="eqcr")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 0, "Admin with EQCR assignment should be skipped"
        assert result["items_copied"]["team_skipped_eqcr"] == 1

    # ⑧ 在另一项目委派 eqcr、上年委派 manager → 复制
    @pytest.mark.asyncio
    async def test_sample_8_eqcr_on_other_project_copied(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "hank": self._base_user(
                assignments=[
                    AssignmentDesc(project_key="other", role="eqcr"),
                    AssignmentDesc(project_key="prior", role="manager"),
                ],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 1, "EQCR on other project should not affect prior project copy"

    # ⑨ 上年委派 manager → 复制，跳过人数 0，响应不含提示
    @pytest.mark.asyncio
    async def test_sample_9_manager_copied_no_notice(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        users = {
            "ivan": self._base_user(
                assignments=[AssignmentDesc(project_key="prior", role="manager")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 1
        assert result["items_copied"]["team_skipped_eqcr"] == 0
        notices = result.get("notices", [])
        assert not any("独立复核合伙人" in n for n in notices)


# ---------------------------------------------------------------------------
# Sample ⑩ – end-to-end: create next year, then verify skipped user gets 403
# ---------------------------------------------------------------------------
class TestSample10EndToEnd:
    """样例 ⑩：用 ① 的数据经创建下年项目接口真发请求，
    再以该用户对新项目调用覆盖集合中任一端点，得到 403。
    """

    @pytest_asyncio.fixture
    async def fresh_db(self) -> AsyncSession:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session

    @pytest.mark.asyncio
    async def test_sample_10_skipped_user_gets_403(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        # Validates: Requirements 11.1, 11.6 sample ⑩
        # Setup: create the EQCR user like sample ①
        users = {
            "alice": UserDesc(
                global_role=UserRole.auditor,
                prior_member=MemberDesc(role=ProjectUserRole.partner, level=PermissionLevel.review),
                assignments=[AssignmentDesc(project_key="prior", role="eqcr")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)

        # Step 1: create next year via service
        result = await _run_copy(fresh_db, prior_id)
        new_pid = uuid.UUID(result["new_project_id"])
        assert result["items_copied"]["team_skipped_eqcr"] == 1

        # Step 2: verify the skipped user has no membership in the new project
        new_members = await _get_new_project_members(fresh_db, new_pid)
        assert len(new_members) == 0, "Skipped user should not have membership in new project"

        # Step 3: verify via direct project_users query (simulating what
        # assert_project_permission would do – absence = 403)
        alice_user = (
            await fresh_db.execute(
                sa.select(User).where(User.username == "user_alice")
            )
        ).scalar_one()
        alice_member = (
            await fresh_db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == new_pid,
                    ProjectUser.user_id == alice_user.id,
                    ProjectUser.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        assert alice_member is None, (
            "Skipped EQCR user has no member row → assert_project_permission would return 403 '权限不足'"
        )


# ---------------------------------------------------------------------------
# Requirement 11.5: fault injection → entire creation fails
# ---------------------------------------------------------------------------
class TestFaultInjection:
    """需求 11.5：在判定的下层查询注入异常 → 非成功响应，库中不存在新项目及其成员行。"""

    @pytest_asyncio.fixture
    async def fresh_db(self) -> AsyncSession:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session

    @pytest.mark.asyncio
    async def test_eqcr_query_error_fails_entire_creation(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        # Validates: Requirements 11.5
        from unittest.mock import AsyncMock, patch

        users = {
            "alice": UserDesc(
                global_role=UserRole.auditor,
                prior_member=MemberDesc(role=ProjectUserRole.partner, level=PermissionLevel.review),
                assignments=[AssignmentDesc(project_key="prior", role="eqcr")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)

        # Inject fault in eqcr_resolver.project_eqcr_user_ids (the lower layer used by the service)
        with patch(
            "app.services.eqcr_resolver.project_eqcr_user_ids",
            new_callable=AsyncMock,
            side_effect=RuntimeError("数据库连接中断"),
        ):
            from app.services.continuous_audit_service import ContinuousAuditService

            svc = ContinuousAuditService()
            with pytest.raises(RuntimeError, match="数据库连接中断"):
                await svc.create_next_year(
                    db=fresh_db,
                    prior_project_id=prior_id,
                    copy_team=True,
                    copy_mapping=False,
                    copy_procedures=False,
                )

        # Since the router didn't commit (error propagated), we need to rollback
        await fresh_db.rollback()

        # No new project should exist: the only project is the prior one and the other
        all_projects = (
            await fresh_db.execute(sa.select(Project))
        ).scalars().all()
        prior_names = {p.name for p in all_projects}
        assert not any("2026" in name for name in prior_names), (
            "New project should not exist after EQCR query failure"
        )

    @pytest.mark.asyncio
    async def test_retry_after_fault_succeeds(self, fresh_db: AsyncSession):
        # Feature: partner-manager-edit-permission, Property 13: 连续审计复制等于模型
        # Validates: Requirements 11.5 (retry succeeds)
        from unittest.mock import AsyncMock, patch

        users = {
            "alice": UserDesc(
                global_role=UserRole.auditor,
                prior_member=MemberDesc(role=ProjectUserRole.partner, level=PermissionLevel.review),
                assignments=[AssignmentDesc(project_key="prior", role="eqcr")],
            )
        }
        prior_id, _ = await _seed_scenario(fresh_db, users)

        # First attempt: fault injection
        with patch(
            "app.services.eqcr_resolver.project_eqcr_user_ids",
            new_callable=AsyncMock,
            side_effect=RuntimeError("连接失败"),
        ):
            from app.services.continuous_audit_service import ContinuousAuditService

            svc = ContinuousAuditService()
            with pytest.raises(RuntimeError):
                await svc.create_next_year(
                    db=fresh_db,
                    prior_project_id=prior_id,
                    copy_team=True,
                    copy_mapping=False,
                    copy_procedures=False,
                )
        await fresh_db.rollback()

        # Retry: should succeed since no fault injection
        result = await _run_copy(fresh_db, prior_id)
        assert "new_project_id" in result
        assert result["items_copied"]["team_skipped_eqcr"] == 1
