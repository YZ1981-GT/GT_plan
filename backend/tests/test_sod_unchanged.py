"""职责分离判定与 EQCR 兼任校验的不变量（partner-manager-edit-permission 任务 2.9；需求 9.5；design Property 11、§8.3）。

被测都在 ``app/services/sod_guard_service.py``（本 spec 不改它），在真实 SQLite 库上调用，本文件不替换任何函数：

- ``SoDGuardService.check(db, project_id, wp_id, actor_id, target_role)``：读 ``working_paper`` 一行，按属性
  ``preparer_id`` / ``reviewer_id`` / ``partner_reviewed_by`` 收集操作人在底稿上的已有角色，与目标角色查互斥矩阵
  ``CONFLICT_MATRIX``（策略码查 ``POLICY_CODES``），并写一条 ``trace_events``。不读成员行，也不读委派。
- ``EqcrIndependenceRule.check(db, project_id, staff_id, new_role, *, proposed_roles=None)``：单条模式读
  ``project_assignments``（同项目、同人员库记录、未删除、角色不等于本次角色）；批量模式只看 ``proposed_roles``，不读库。
  冲突抛 ``SodViolation``，委派保存端点取它的 ``message`` 与 ``policy_code`` 作 409 响应。
- ``validate_eqcr_sod_in_batch(assignments)``：批内预检，纯函数（没有 db 参数）；冲突角色是函数内局部的
  ``CONFLICT_ROLES | {"qc"}``，没有模块常量可读，由 ``test_conflict_role_sets_unchanged`` 按行为逐个角色测出。

结论 = （是否允许，冲突描述 / 消息，策略码）。期望值来源：本 spec 改动前的树（基线 B = ``a02a21419``）上用仓库外一次性
探针逐条实测，字面写入下表，不按代码阅读推断；探针输出摘要见 acceptance.md 任务 2.9。实测要点：

- ``WorkingPaper`` 没有 ``preparer_id``、``reviewer_id`` 属性（编制人、复核人分别存在 ``assigned_to``、``reviewer`` 列），
  ``hasattr`` 为假 ⇒ 职责分离判定只经 ``partner_reviewed_by`` 取到已有角色：互斥矩阵 6 个键里只有
  (partner_approver, preparer) 会命中，另外 5 个键对真实底稿数据恒放行。按需求 9.5 保持现行为，只登记、不修。
- 无成员行、6 种项目角色 × 3 种级别、一条已删除成员行，共 20 种成员行状态下，104 条样例的结论逐条相同。

样例里「底稿职位」用真实列表达：编制人 = ``working_paper.assigned_to``（同时写 ``wp_index.assigned_to``）、
复核人 = ``working_paper.reviewer``（同时写 ``wp_index.reviewer``）、合伙人审批人 = ``working_paper.partner_reviewed_by``；
操作人不担任的职位由另外三个用户担任。成员行（``project_users``，项目 P）落在被判定的人身上：职责分离判定是操作人，
兼任校验是人员库记录 S 关联到的用户（S 之外的人员库记录 T 不关联用户）。

测试：
- ``test_fixed_table_without_member_row``：样例表 104 条逐条断言（无成员行）。
- ``test_property_11_sod_conclusion_independent_of_member_row``（Property 11）：任意成员行（或无成员行）下结论等于样例表。
  显式样例为样例表全部 104 条，各配一条成员行；随机抽样只从收 db 参数的 82 条里取。
- ``test_conflict_matrix_and_policy_codes_unchanged``、``test_eqcr_conflict_roles_unchanged``：常量逐值比对。
- ``test_conflict_role_sets_unchanged``：逐个角色测出批内预检与兼任校验两种模式的冲突角色集合。
- ``test_fixed_table_covers_mandated_samples``：样例表含需求 9.5 点名的全部样例。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.phase14_models import TraceEvent
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.services.sod_guard_service import (
    CONFLICT_MATRIX,
    POLICY_CODES,
    EqcrIndependenceRule,
    SoDGuardService,
    SodViolation,
    validate_eqcr_sod_in_batch,
)

# ─── 样例的输入描述 ──────────────────────────────────────────────────────────

BZ, FH, HH = "编制人", "复核人", "合伙人审批人"  # 底稿的三个职位
ALL3 = frozenset({BZ, FH, HH})
S_ID = "11111111-1111-4111-8111-111111111111"  # 批内预检里的人员库记录 S、T（预检收的是字符串）
T_ID = "22222222-2222-4222-8222-222222222222"
_PRE_STAFF = {"S": S_ID, "T": T_ID, "": ""}

Verdict = tuple[bool, str | None, str | None]  # （是否允许，冲突描述 / 消息，策略码）


@dataclass(frozen=True)
class Sod:
    """职责分离判定：操作人担任的底稿职位（三个职位的子集）、目标角色、底稿是否存在。"""

    holds: frozenset[str]
    target: str
    wp_exists: bool = True


@dataclass(frozen=True)
class Single:
    """兼任校验单条模式（读库）：人员库记录 S 已有的委派（项目 P / Q，角色，是否已删除）与本次委派角色。"""

    existing: tuple[tuple[str, str, bool], ...]
    new_role: str


@dataclass(frozen=True)
class Batch:
    """兼任校验批量模式：本批终态（人员库记录 S / T，角色）、S 的本次角色、S 在 P 上已落库的委派（批量模式不读）。"""

    proposed: tuple[tuple[str, str], ...]
    new_role: str
    db_existing: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pre:
    """批内预检：本批委派（人员库记录 S / T / 空串，角色）。"""

    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Case:
    case_id: str
    inputs: Sod | Single | Batch | Pre
    expected: Verdict


@dataclass(frozen=True)
class Member:
    """被判定的人在项目 P 的成员行。"""

    role: ProjectUserRole
    level: PermissionLevel
    deleted: bool = False


# ─── 固定样例表（期望 = 基线树实测值，逐条字面写入） ────────────────────────────

ALLOW: Verdict = (True, None, None)
_APPROVER: Verdict = (False, "同人编制+终审同一底稿", "SOD_PREPARER_APPROVER_CONFLICT")
_EQ = "SOD_EQCR_INDEPENDENCE_CONFLICT"
# 需求 9.5 列出的「直接放行」委派角色（既不是 eqcr、也不在冲突角色集合里），及样例编号里用的 ASCII 标签
_DIRECT_PASS = (
    ("独立复核合伙人", "cn_eqcr"), ("partner", "partner"), ("合伙人", "cn_partner"), ("项目经理", "cn_manager"),
    ("审计员", "cn_auditor"), ("assistant", "assistant"), ("助理", "cn_assistant"), ("质控", "cn_qc"),
)

_SOD_CASES = (
    # 互斥矩阵的 6 个键：操作人担任「已有角色」对应的底稿职位，判定「目标角色」
    Case("sod-key-preparer-partner_approver", Sod(frozenset({BZ}), "partner_approver"), ALLOW),
    Case("sod-key-partner_approver-preparer", Sod(frozenset({HH}), "preparer"), _APPROVER),
    Case("sod-key-preparer-reviewer", Sod(frozenset({BZ}), "reviewer"), ALLOW),
    Case("sod-key-reviewer-preparer", Sod(frozenset({FH}), "preparer"), ALLOW),
    Case("sod-key-qc_reviewer-preparer", Sod(frozenset(), "preparer"), ALLOW),  # 底稿没有质控职位，操作人与三职位无关
    Case("sod-key-preparer-qc_reviewer", Sod(frozenset({BZ}), "qc_reviewer"), ALLOW),
    # 三个职位全担任 × 四个目标角色
    Case("sod-all3-partner_approver", Sod(ALL3, "partner_approver"), ALLOW),
    Case("sod-all3-preparer", Sod(ALL3, "preparer"), _APPROVER),
    Case("sod-all3-reviewer", Sod(ALL3, "reviewer"), ALLOW),
    Case("sod-all3-qc_reviewer", Sod(ALL3, "qc_reviewer"), ALLOW),
    # 其余组合与边界
    Case("sod-preparer+reviewer-partner_approver", Sod(frozenset({BZ, FH}), "partner_approver"), ALLOW),
    Case("sod-partner_approver-reviewer", Sod(frozenset({HH}), "reviewer"), ALLOW),
    Case("sod-partner_approver-partner_approver", Sod(frozenset({HH}), "partner_approver"), ALLOW),
    Case("sod-partner_approver-qc_reviewer", Sod(frozenset({HH}), "qc_reviewer"), ALLOW),
    Case("sod-reviewer-partner_approver", Sod(frozenset({FH}), "partner_approver"), ALLOW),
    Case("sod-reviewer-reviewer", Sod(frozenset({FH}), "reviewer"), ALLOW),
    Case("sod-preparer-preparer", Sod(frozenset({BZ}), "preparer"), ALLOW),
    Case("sod-unrelated-reviewer", Sod(frozenset(), "reviewer"), ALLOW),
    Case("sod-partner_approver-unknown-eqcr", Sod(frozenset({HH}), "eqcr"), ALLOW),
    Case("sod-partner_approver-case-Preparer", Sod(frozenset({HH}), "Preparer"), ALLOW),
    Case("sod-wp-missing-preparer", Sod(frozenset(), "preparer", wp_exists=False), ALLOW),
)

_SINGLE_CASES = (
    # eqcr 与每个冲突角色双向：先有冲突角色再委派 eqcr / 先有 eqcr 再委派冲突角色
    Case("single-eqcr-after-signing_partner", Single((("P", "signing_partner", False),), "eqcr"),
         (False, "同项目内该人员已是 signing_partner 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("single-signing_partner-after-eqcr", Single((("P", "eqcr", False),), "signing_partner"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 signing_partner", _EQ)),
    Case("single-eqcr-after-manager", Single((("P", "manager", False),), "eqcr"),
         (False, "同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("single-manager-after-eqcr", Single((("P", "eqcr", False),), "manager"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 manager", _EQ)),
    Case("single-eqcr-after-auditor", Single((("P", "auditor", False),), "eqcr"),
         (False, "同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("single-auditor-after-eqcr", Single((("P", "eqcr", False),), "auditor"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 auditor", _EQ)),
    # eqcr 与 qc：单条模式放行；独立复核合伙人 与 manager：放行
    Case("single-eqcr-after-qc", Single((("P", "qc", False),), "eqcr"), ALLOW),
    Case("single-qc-after-eqcr", Single((("P", "eqcr", False),), "qc"), ALLOW),
    Case("single-cn_eqcr-after-manager", Single((("P", "manager", False),), "独立复核合伙人"), ALLOW),
    Case("single-manager-after-cn_eqcr", Single((("P", "独立复核合伙人", False),), "manager"), ALLOW),
    # 直接放行角色 × eqcr（双向）
    *(Case(f"single-{tag}-after-eqcr", Single((("P", "eqcr", False),), role), ALLOW)
      for role, tag in _DIRECT_PASS),
    *(Case(f"single-eqcr-after-{tag}", Single((("P", role, False),), "eqcr"), ALLOW)
      for role, tag in _DIRECT_PASS),
    # 边界：无委派、已删除委派、他项目委派、同角色
    Case("single-eqcr-no-assignment", Single((), "eqcr"), ALLOW),
    Case("single-eqcr-after-deleted-manager", Single((("P", "manager", True),), "eqcr"), ALLOW),
    Case("single-eqcr-after-manager-on-other-project", Single((("Q", "manager", False),), "eqcr"), ALLOW),
    Case("single-manager-after-deleted-eqcr", Single((("P", "eqcr", True),), "manager"), ALLOW),
    Case("single-eqcr-after-eqcr", Single((("P", "eqcr", False),), "eqcr"), ALLOW),
)

_BATCH_CASES = (
    # eqcr 与每个冲突角色同批，双向：S 的本次角色为 eqcr / 为冲突角色
    Case("batch-eqcr-with-signing_partner", Batch((("S", "eqcr"), ("S", "signing_partner")), "eqcr"),
         (False, "同项目内该人员已是 signing_partner 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("batch-signing_partner-with-eqcr", Batch((("S", "signing_partner"), ("S", "eqcr")), "signing_partner"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 signing_partner", _EQ)),
    Case("batch-eqcr-with-manager", Batch((("S", "eqcr"), ("S", "manager")), "eqcr"),
         (False, "同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("batch-manager-with-eqcr", Batch((("S", "manager"), ("S", "eqcr")), "manager"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 manager", _EQ)),
    Case("batch-eqcr-with-auditor", Batch((("S", "eqcr"), ("S", "auditor")), "eqcr"),
         (False, "同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("batch-auditor-with-eqcr", Batch((("S", "auditor"), ("S", "eqcr")), "auditor"),
         (False, "同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 auditor", _EQ)),
    # eqcr 与 qc 同批：批量模式放行（批内预检拒绝，见 pre-eqcr-qc）；独立复核合伙人 与 manager 同批：放行
    Case("batch-eqcr-with-qc", Batch((("S", "eqcr"), ("S", "qc")), "eqcr"), ALLOW),
    Case("batch-qc-with-eqcr", Batch((("S", "qc"), ("S", "eqcr")), "qc"), ALLOW),
    Case("batch-cn_eqcr-with-manager", Batch((("S", "独立复核合伙人"), ("S", "manager")), "独立复核合伙人"), ALLOW),
    Case("batch-manager-with-cn_eqcr", Batch((("S", "manager"), ("S", "独立复核合伙人")), "manager"), ALLOW),
    # 多个冲突角色时报批内先出现的那个；他人的角色、已落库的委派都不计
    Case("batch-eqcr-first-conflict-wins", Batch((("S", "eqcr"), ("S", "auditor"), ("S", "manager")), "eqcr"),
         (False, "同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）", _EQ)),
    Case("batch-eqcr-other-staff-manager", Batch((("S", "eqcr"), ("T", "manager")), "eqcr"), ALLOW),
    Case("batch-eqcr-ignores-db-manager", Batch((("S", "eqcr"),), "eqcr", db_existing=("manager",)), ALLOW),
    Case("batch-manager-ignores-db-eqcr", Batch((("S", "manager"),), "manager", db_existing=("eqcr",)), ALLOW),
    # 直接放行角色 × eqcr 同批（双向）
    *(Case(f"batch-{tag}-with-eqcr", Batch((("S", role), ("S", "eqcr")), role), ALLOW)
      for role, tag in _DIRECT_PASS),
    *(Case(f"batch-eqcr-with-{tag}", Batch((("S", "eqcr"), ("S", role)), "eqcr"), ALLOW)
      for role, tag in _DIRECT_PASS),
)

_PRE_CASES = (
    Case("pre-empty", Pre(()), ALLOW),
    # eqcr 与每个冲突角色（含 qc）同批，两种先后
    Case("pre-eqcr-signing_partner", Pre((("S", "eqcr"), ("S", "signing_partner"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['signing_partner'] 角色，违反独立性", _EQ)),
    Case("pre-signing_partner-eqcr", Pre((("S", "signing_partner"), ("S", "eqcr"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['signing_partner'] 角色，违反独立性", _EQ)),
    Case("pre-eqcr-manager", Pre((("S", "eqcr"), ("S", "manager"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['manager'] 角色，违反独立性", _EQ)),
    Case("pre-manager-eqcr", Pre((("S", "manager"), ("S", "eqcr"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['manager'] 角色，违反独立性", _EQ)),
    Case("pre-eqcr-auditor", Pre((("S", "eqcr"), ("S", "auditor"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性", _EQ)),
    Case("pre-auditor-eqcr", Pre((("S", "auditor"), ("S", "eqcr"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性", _EQ)),
    Case("pre-eqcr-qc", Pre((("S", "eqcr"), ("S", "qc"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['qc'] 角色，违反独立性", _EQ)),
    Case("pre-qc-eqcr", Pre((("S", "qc"), ("S", "eqcr"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['qc'] 角色，违反独立性", _EQ)),
    # 独立复核合伙人 与 manager 同批：放行
    Case("pre-cn_eqcr-manager", Pre((("S", "独立复核合伙人"), ("S", "manager"))), ALLOW),
    # 多个冲突角色排序列出；他人的角色不计；缺人员或角色的条目跳过；按人员首次出现的先后报第一个违规者
    Case("pre-eqcr-manager-auditor", Pre((("S", "eqcr"), ("S", "manager"), ("S", "auditor"))),
         (False, f"人员 {S_ID} 在同批次中同时持有 eqcr 与 ['auditor', 'manager'] 角色，违反独立性", _EQ)),
    Case("pre-eqcr-other-staff-manager", Pre((("S", "eqcr"), ("T", "manager"))), ALLOW),
    Case("pre-skip-missing-fields", Pre((("S", "eqcr"), ("S", ""), ("", "manager"))), ALLOW),
    Case("pre-first-staff-wins", Pre((("T", "eqcr"), ("T", "auditor"), ("S", "eqcr"), ("S", "manager"))),
         (False, f"人员 {T_ID} 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性", _EQ)),
    # 直接放行角色 × eqcr 同批
    *(Case(f"pre-eqcr-{tag}", Pre((("S", "eqcr"), ("S", role))), ALLOW) for role, tag in _DIRECT_PASS),
)

_CASES: tuple[Case, ...] = (*_SOD_CASES, *_SINGLE_CASES, *_BATCH_CASES, *_PRE_CASES)


# ─── 测试库与观测：每个样例一个独立的 SQLite 内存库 ─────────────────────────────

_TABLES = [
    User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__, TraceEvent.__table__,
    StaffMember.__table__, ProjectAssignment.__table__, ProjectUser.__table__,
]


def _verdict_of(exc: SodViolation | None) -> Verdict:
    """兼任校验的结论：不抛即放行；抛 SodViolation 取委派保存端点用的 message 与 policy_code。"""
    if exc is None:
        return ALLOW
    assert str(exc) == exc.message, "SodViolation 的字符串形式与 message 不一致"
    return (False, exc.message, exc.policy_code)


async def _judge_sod(db, project: Project, subject: User, sod: Sod) -> Verdict:
    holder: dict[str, uuid.UUID] = {}
    for n, position in enumerate((BZ, FH, HH)):
        if position in sod.holds:
            holder[position] = subject.id
            continue
        other = User(username=f"u-other-{n}", email=f"other{n}@test.local", hashed_password="x", role=UserRole.auditor)
        db.add(other)
        await db.flush()
        holder[position] = other.id
    index = WpIndex(project_id=project.id, wp_code="D2", wp_name="应收账款", assigned_to=holder[BZ], reviewer=holder[FH])
    db.add(index)
    await db.flush()
    wp = WorkingPaper(
        project_id=project.id, wp_index_id=index.id, file_path="D2.xlsx", source_type=WpSourceType.template,
        assigned_to=holder[BZ], reviewer=holder[FH], partner_reviewed_by=holder[HH],
    )
    db.add(wp)
    await db.flush()
    result = await SoDGuardService().check(
        db, project_id=project.id, wp_id=wp.id if sod.wp_exists else uuid.uuid4(), actor_id=subject.id,
        target_role=sod.target,
    )
    return (result.allowed, result.conflict_type, result.policy_code)


async def _judge_eqcr(db, pid: dict[str, uuid.UUID], subject: User, inputs: Single | Batch) -> Verdict:
    staff = {"S": StaffMember(user_id=subject.id, name="测试人员甲"), "T": StaffMember(user_id=None, name="测试人员乙")}
    db.add_all(list(staff.values()))
    await db.flush()
    s_id = staff["S"].id
    if isinstance(inputs, Single):
        rows = [(project, role, deleted) for project, role, deleted in inputs.existing]
        proposed = None
    else:
        rows = [("P", role, False) for role in inputs.db_existing]
        proposed = [(staff[key].id, role) for key, role in inputs.proposed]
    for project, role, deleted in rows:
        db.add(ProjectAssignment(project_id=pid[project], staff_id=s_id, role=role, is_deleted=deleted))
    await db.flush()
    try:
        await EqcrIndependenceRule().check(
            db, project_id=pid["P"], staff_id=s_id, new_role=inputs.new_role, proposed_roles=proposed
        )
    except SodViolation as exc:
        return _verdict_of(exc)
    return _verdict_of(None)


async def _seed_and_judge(inputs: Sod | Single | Batch, member: Member | None) -> Verdict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            projects = {"P": Project(name="【测试】P", client_name="甲"), "Q": Project(name="【测试】Q", client_name="乙")}
            db.add_all(list(projects.values()))
            subject = User(username="u-subject", email="subject@test.local", hashed_password="x", role=UserRole.auditor)
            db.add(subject)
            await db.flush()
            if member is not None:
                db.add(ProjectUser(
                    project_id=projects["P"].id, user_id=subject.id, role=member.role,
                    permission_level=member.level, is_deleted=member.deleted,
                ))
                await db.flush()
            if isinstance(inputs, Sod):
                return await _judge_sod(db, projects["P"], subject, inputs)
            return await _judge_eqcr(db, {key: p.id for key, p in projects.items()}, subject, inputs)
    finally:
        await engine.dispose()


def _observe(inputs: Sod | Single | Batch | Pre, member: Member | None) -> Verdict:
    """被判定的人在 P 上持有 ``member`` 这条成员行（None 为没有成员行）时的结论。批内预检是纯函数，不建库。"""
    if isinstance(inputs, Pre):
        try:
            validate_eqcr_sod_in_batch([{"staff_id": _PRE_STAFF[key], "role": role} for key, role in inputs.items])
        except SodViolation as exc:
            return _verdict_of(exc)
        return _verdict_of(None)
    return asyncio.run(_seed_and_judge(inputs, member))


# ─── 互斥矩阵与冲突角色集合的内容（基线实测值） ────────────────────────────────

_EXPECTED_MATRIX: dict[tuple[str, str], tuple[str, str]] = {  # （已有角色，目标角色）→（冲突描述，策略码）
    ("preparer", "partner_approver"): ("同人编制+终审同一底稿", "SOD_PREPARER_APPROVER_CONFLICT"),
    ("partner_approver", "preparer"): ("同人编制+终审同一底稿", "SOD_PREPARER_APPROVER_CONFLICT"),
    ("preparer", "reviewer"): ("经理复核本人编制底稿", "SOD_PREPARER_REVIEWER_CONFLICT"),
    ("reviewer", "preparer"): ("经理复核本人编制底稿", "SOD_PREPARER_REVIEWER_CONFLICT"),
    ("qc_reviewer", "preparer"): ("质控人员参与被抽查底稿修改", "SOD_QC_PREPARER_CONFLICT"),
    ("preparer", "qc_reviewer"): ("质控人员参与被抽查底稿修改", "SOD_QC_PREPARER_CONFLICT"),
}
_EXPECTED_CONFLICT_ROLES = frozenset({"signing_partner", "manager", "auditor"})
_EXPECTED_PRECHECK_CONFLICT_ROLES = frozenset({"signing_partner", "manager", "auditor", "qc"})
# 逐个角色测冲突集合用的委派角色全集：需求 2.5 期望表的全部键 + 大小写 / 首尾空白变体、未登记角色、职责分离角色名
_ROLE_UNIVERSE = (
    "signing_partner", "partner", "合伙人", "manager", "项目经理", "qc", "质控", "eqcr", "独立复核合伙人",
    "auditor", "审计员", "assistant", "助理",
    "EQCR", "Eqcr", " eqcr", "Manager", " manager", "QC", "观察员", "readonly", "preparer",
)


def _plain(key: tuple) -> tuple[str, ...]:
    """矩阵键里是 SoDRole（str 混入的枚举）；取枚举值比较。"""
    return tuple(getattr(part, "value", part) for part in key)


def test_conflict_matrix_and_policy_codes_unchanged() -> None:
    matrix = {_plain(key): text for key, text in CONFLICT_MATRIX.items()}
    codes = {_plain(key): code for key, code in POLICY_CODES.items()}
    assert len(matrix) == len(CONFLICT_MATRIX) and len(codes) == len(POLICY_CODES), "矩阵键取枚举值后出现重复"
    assert matrix == {key: text for key, (text, _code) in _EXPECTED_MATRIX.items()}, "互斥矩阵的内容变了"
    assert codes == {key: code for key, (_text, code) in _EXPECTED_MATRIX.items()}, "互斥矩阵的策略码变了"


def test_eqcr_conflict_roles_unchanged() -> None:
    assert type(EqcrIndependenceRule.CONFLICT_ROLES) is frozenset
    assert EqcrIndependenceRule.CONFLICT_ROLES == _EXPECTED_CONFLICT_ROLES, "EqcrIndependenceRule.CONFLICT_ROLES 变了"
    assert EqcrIndependenceRule.POLICY_CODE == _EQ


def _rejected(make) -> set[str]:
    return {role for role in _ROLE_UNIVERSE if _observe(make(role), None)[0] is False}


def test_conflict_role_sets_unchanged() -> None:
    """按行为逐个角色测出冲突角色集合：批内预检 = CONFLICT_ROLES 加 qc；兼任校验两种模式、两个方向 = CONFLICT_ROLES。"""
    assert _rejected(lambda r: Pre((("S", "eqcr"), ("S", r)))) == _EXPECTED_PRECHECK_CONFLICT_ROLES, "批内预检"
    assert _rejected(lambda r: Batch((("S", r), ("S", "eqcr")), r)) == _EXPECTED_CONFLICT_ROLES, "批量：本次为该角色"
    assert _rejected(lambda r: Batch((("S", "eqcr"), ("S", r)), "eqcr")) == _EXPECTED_CONFLICT_ROLES, "批量：本次为 eqcr"
    assert _rejected(lambda r: Single((("P", "eqcr", False),), r)) == _EXPECTED_CONFLICT_ROLES, "单条：已有 eqcr"
    assert _rejected(lambda r: Single((("P", r, False),), "eqcr")) == _EXPECTED_CONFLICT_ROLES, "单条：本次为 eqcr"


# ─── 固定样例表逐项断言（无成员行） ───────────────────────────────────────────

_MANDATED = {  # 需求 9.5 点名必须覆盖的样例
    # 互斥矩阵每个键
    *(f"sod-key-{existing}-{target}" for existing, target in _EXPECTED_MATRIX),
    # eqcr 与每个冲突角色双向（单条、批量、批内预检）
    *(f"single-eqcr-after-{role}" for role in _EXPECTED_CONFLICT_ROLES),
    *(f"single-{role}-after-eqcr" for role in _EXPECTED_CONFLICT_ROLES),
    *(f"batch-eqcr-with-{role}" for role in _EXPECTED_CONFLICT_ROLES),
    *(f"batch-{role}-with-eqcr" for role in _EXPECTED_CONFLICT_ROLES),
    *(f"pre-eqcr-{role}" for role in _EXPECTED_CONFLICT_ROLES),
    *(f"pre-{role}-eqcr" for role in _EXPECTED_CONFLICT_ROLES),
    # 独立复核合伙人 与 manager 同批：兼任校验放行
    "batch-cn_eqcr-with-manager", "batch-manager-with-cn_eqcr", "pre-cn_eqcr-manager",
    # eqcr 与 qc 同批：批内预检拒绝，单条与批量模式放行
    "pre-eqcr-qc", "pre-qc-eqcr", "batch-eqcr-with-qc", "batch-qc-with-eqcr", "single-eqcr-after-qc",
    "single-qc-after-eqcr",
    # 需求 9.5 列出的直接放行角色
    *(f"single-{tag}-after-eqcr" for _role, tag in _DIRECT_PASS),
}


def test_fixed_table_covers_mandated_samples() -> None:
    ids = [case.case_id for case in _CASES]
    assert len(ids) == len(set(ids)) == 104, "样例编号重复，或样例数与基线实测的 104 条不一致"
    assert len(_DB_CASES) == 82, "收 db 参数的样例（职责分离判定 21 + 单条 31 + 批量 30）应为 82 条"
    assert not (_MANDATED - set(ids)), f"缺少需求 9.5 点名的样例：{sorted(_MANDATED - set(ids))}"


@pytest.mark.parametrize("case", [pytest.param(case, id=case.case_id) for case in _CASES])
def test_fixed_table_without_member_row(case: Case) -> None:
    actual = _observe(case.inputs, None)
    assert actual == case.expected, f"{case.case_id}：结论为 {actual}，基线实测为 {case.expected}"


# ─── Property 11：职责分离判定与成员行无关 ─────────────────────────────────────

_members = st.none() | st.builds(
    Member, st.sampled_from(list(ProjectUserRole)), st.sampled_from(list(PermissionLevel)), st.booleans()
)
# 随机生成只从收 db 参数的样例里抽：批内预检是纯函数，成员行无从影响它
_DB_CASES = tuple(case for case in _CASES if not isinstance(case.inputs, Pre))
# 显式样例：样例表全部 104 条各配一条成员行，项目角色 × 级别 18 种轮换，外加一条已删除的成员行
_EXAMPLE_MEMBERS = (
    *(Member(role, level) for role in ProjectUserRole for level in PermissionLevel),
    Member(ProjectUserRole.partner, PermissionLevel.edit, deleted=True),
)


def _with_table_examples(test):
    for n, case in enumerate(_CASES):
        test = example(case=case, member=_EXAMPLE_MEMBERS[n % len(_EXAMPLE_MEMBERS)])(test)
    return test


@settings(max_examples=5, deadline=None)
@given(case=st.sampled_from(_DB_CASES), member=_members)
@_with_table_examples
def test_property_11_sod_conclusion_independent_of_member_row(case: Case, member: Member | None) -> None:
    # Feature: partner-manager-edit-permission, Property 11: 职责分离判定与成员行无关
    actual = _observe(case.inputs, member)
    assert actual == case.expected, f"{case.case_id}：成员行 {member} 下结论为 {actual}，样例表为 {case.expected}"
