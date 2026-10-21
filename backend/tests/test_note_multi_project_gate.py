"""附注编辑门禁多项目形态的性质测试（partner-manager-edit-permission 任务 6.4；Property 8；需求 8.5；design §4.6、§8.3）。

被测 ``app.services.note_edit_gate.assert_note_edit_access_on_projects``。每个样例在独立的权限世界（``tests/authz_world.py`` 的
SQLite 版）里造数，经一个最小测试端点真发一次请求：端点在函数体顶层先调多项目形态，通过后才执行业务（design §4.8 表 B 的
写法）。只替换当前用户与数据库会话（``client_for_app``）、RLS 设置（只记录项目 id）；门禁与各步判定一个都不替换，各项目上的
结论全部由库里的项目状态、成员行与委派给出。

生成器（design §8.3）：1~4 个项目；调用者全局角色取全部 7 个取值；每个项目上各自随机取是否归档、是否合并锁定、成员行（无 /
已删除 / 未删除，级别 readonly / review / edit × 项目角色 partner / manager / qc / auditor / readonly）、本项目现行委派（无 /
``eqcr`` / ``独立复核合伙人`` / 不是 EQCR 别名的 ``manager``）；端点是否判合并锁随机；请求里的项目顺序随机，可重复出现。

模型（不调用任何被测判定函数）：各项目单独判定的结论按需求 6.13 的先后取第一个成立的拒绝 —— 归档 423（6.7，含 admin）→ 非
admin 且没有未删除成员行或级别为 readonly 403「权限不足」（6.4）→ 全局 eqcr 或持本项目 EQCR 别名委派 403（6.5、7.1，admin
不豁免）→ 非 admin 且「全局角色 ∪ 项目角色」的操作权限不含 ``note:edit`` 403（6.12）→ 端点判合并锁且项目合并锁定 423（6.6）。
整单结论按需求 8.5：放行当且仅当每个项目都放行；否则有 403 即 403，否则 423；``project_ids`` 恰为未通过的项目（去重后按判定
先后），message 按任务 6.3 钉住的写法（前缀 + 逐个「项目 id（单独判定的原因）」，以「、」连接）。拒绝原因与状态码取
``test_note_edit_gate_unit.py`` 按需求原文写死的期望，EQCR 别名取需求 2.5 期望表，操作矩阵按需求 6.12 与 Q1（矩阵不改）写死。

「任何项目都没有数据写入」的观测：请求前后各取一次权限世界六张表的全部行（逐列取值），拒绝时逐值相同、业务调用 0 次。正向
对照：放行时业务恰 1 次，同一观测看得到它的写入（每个涉及的项目各多一条附注，其余行逐值不变），所以拒绝时的「不变」不是
观测不到。另核每个项目都单独判定了一次：多项目形态执行 1 次，判定实现的执行次数等于去重后的项目数，归档一步按去重后的先后
逐项目各发一次语句（``StepRecorder``；判定前把项目对象移出会话，归档守卫的 ``db.get`` 因此真发语句）。
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
import hypothesis
from hypothesis import example, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.database as core_database
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import ProjectStatus
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.note_edit_gate import assert_note_edit_access_on_projects
from tests.authz_world import (
    OTHER_PROJECT_ID, TARGET_NOTE_ID, TARGET_PROJECT_ID, WORLD_TABLES, AuthzWorld, sqlite_world,
)
from tests.role_map_expected import EXPECTED_EQCR_ALIASES
from tests.test_note_edit_gate_multi_project_unit import ERROR_CODE, MULTI, PREFIX, THIRD_PROJECT_ID, _judged
from tests.test_note_edit_gate_unit import (
    ARCHIVED, CONSOL_LOCKED, EQCR_READONLY, FORBIDDEN, IMPL, OPERATION_DENIED, Rejection, StepRecorder,
    _forget_projects,
)

FOURTH_PROJECT_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e12")  # 第 4 个项目：按 6.3 第三个项目的取法另建
PROJECT_IDS = (TARGET_PROJECT_ID, OTHER_PROJECT_ID, THIRD_PROJECT_ID, FOURTH_PROJECT_ID)
NOTE_IDS = (  # 各项目上一条既有附注
    TARGET_NOTE_ID,
    uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e13"),
    uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e14"),
    uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e15"),
)
GLOBAL_ROLES = ("admin", "partner", "manager", "auditor", "qc", "eqcr", "readonly")  # 全局角色的全部取值（需求 6.13）
LEVELS = ("readonly", "review", "edit")
PROJECT_ROLES = ("partner", "manager", "qc", "auditor", "readonly")  # 角色映射可写出的项目角色（需求 6.13）
ALIASES = (None, "eqcr", "独立复核合伙人", "manager")  # 本项目现行委派；manager 不是 EQCR 别名，作干扰项
_PASSING_LEVELS = frozenset({"review", "edit"})  # 需求 6.4：review 及以上
# 需求 6.12 与 Q1（操作矩阵内容不改）：操作权限含 note:edit 的全局角色（admin 另按恒放行处理）与项目角色
_NOTE_EDIT_GLOBAL_ROLES = frozenset({"partner", "manager", "auditor"})
_NOTE_EDIT_PROJECT_ROLES = frozenset({"partner", "manager"})

# 最小测试端点与它的业务写入（放行时给每个涉及的项目各加一条附注）
_LOCK_PATH = "/api/note-multi-project-gate-probe/with-consol-lock"
_NO_LOCK_PATH = "/api/note-multi-project-gate-probe/without-consol-lock"
WRITTEN_SECTION = "九、9"
WRITTEN_TITLE = "【测试】多项目判定写入"
WRITTEN_TEXT = "【测试】放行后业务写入的正文"
_NOTES = DisclosureNote.__tablename__
Calls = list[tuple[tuple[uuid.UUID, ...], uuid.UUID]]  # 业务调用：（请求原样的项目清单，操作人）


# ─── 场景与模型 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Situation:
    """调用者在一个项目上的情形。``member`` 为成员行的（级别，项目角色），``deleted`` 为真即该行已删除；
    ``alias`` 为调用者在本项目一条现行委派的角色。"""

    archived: bool = False
    locked: bool = False
    member: tuple[str, str] | None = None
    deleted: bool = False
    alias: str | None = None


@dataclass(frozen=True)
class Scenario:
    global_role: str
    consol_lock: bool  # 端点是否判合并锁
    situations: tuple[Situation, ...]  # 第 i 个项目（PROJECT_IDS[i]）上的情形，1~4 个
    request: tuple[int, ...]  # 请求里的项目下标，按请求先后，可重复
    name: str = "generated"


@dataclass(frozen=True)
class Expected:
    ordered: tuple[int, ...]  # 去重保序后的项目下标
    status: int  # 200 为放行
    denied: tuple[int, ...]  # 未通过的项目下标，按判定先后
    detail: dict[str, Any] | None  # 拒绝时的 detail；放行为 None


def _single(scenario: Scenario, situation: Situation) -> Rejection | None:
    """一个项目单独判定的结论：按需求 6.13 的先后取第一个成立的拒绝，都不成立为放行（None）。"""
    admin = scenario.global_role == "admin"
    if situation.archived:
        return ARCHIVED  # 6.7：对任何调用者（含 admin），先于其余各步
    level = None if situation.member is None or situation.deleted else situation.member[0]
    if not admin and level not in _PASSING_LEVELS:
        return FORBIDDEN  # 6.4：没有未删除成员行，或级别为 readonly
    if scenario.global_role == "eqcr" or situation.alias in EXPECTED_EQCR_ALIASES:
        return EQCR_READONLY  # 6.5、7.1：admin 不豁免
    if (
        not admin
        and scenario.global_role not in _NOTE_EDIT_GLOBAL_ROLES
        and situation.member[1] not in _NOTE_EDIT_PROJECT_ROLES
    ):
        return OPERATION_DENIED  # 6.12：admin 恒放行；走到这里的非 admin 必有未删除成员行
    if scenario.consol_lock and situation.locked:
        return CONSOL_LOCKED  # 6.6：只对判合并锁的端点
    return None


def _model(scenario: Scenario) -> Expected:
    """整单结论（需求 8.5）：去重保序后逐项目单独判定；有未通过的项目即整单拒绝，其中有 403 即 403，否则 423。"""
    ordered: list[int] = []
    for index in scenario.request:  # 去重保序：按首次出现的先后
        if index not in ordered:
            ordered.append(index)
    verdicts = [(index, _single(scenario, scenario.situations[index])) for index in ordered]
    denied = [(index, rejection) for index, rejection in verdicts if rejection is not None]
    if not denied:
        return Expected(tuple(ordered), 200, (), None)
    status = 403 if any(rejection.status == 403 for _index, rejection in denied) else 423
    message = PREFIX + "、".join(f"{PROJECT_IDS[index]}（{rejection.reason}）" for index, rejection in denied)
    project_ids = [str(PROJECT_IDS[index]) for index, _rejection in denied]
    detail = {"error_code": ERROR_CODE, "message": message, "project_ids": project_ids}
    return Expected(tuple(ordered), status, tuple(index for index, _rejection in denied), detail)


# ─── 造数、最小测试端点与观测 ────────────────────────────────────────────────


async def _project(world: AuthzWorld, index: int) -> Project:
    if index == 0:
        return world.target
    if index == 1:
        return await world.other_project()
    return await world.project(project_id=PROJECT_IDS[index], name=f"【测试】多项目判定第 {index + 1} 个项目")


async def _arrange(world: AuthzWorld, scenario: Scenario) -> User:
    """建调用者，并按情形在第 i 个项目上建成员行、现行委派，设项目状态与合并锁定标记，另建一条既有附注。"""
    user = await world.user(scenario.global_role)
    for index, situation in enumerate(scenario.situations):
        project = await _project(world, index)
        if situation.member is not None:
            level, role = situation.member
            (await world.member(level, role, project=project, user=user)).member.is_deleted = situation.deleted
        if situation.alias is not None:
            await world.eqcr_assignment(situation.alias, user=user, project=project)
        project.status = ProjectStatus.archived if situation.archived else ProjectStatus.execution
        project.consol_lock = situation.locked
        await world.add_note(note_id=NOTE_IDS[index], project=project)
    await world.db.flush()
    return user


class _ProbeBody(BaseModel):
    project_ids: list[uuid.UUID]


def _probe_app(calls: Calls) -> FastAPI:
    """最小测试端点：多项目形态在函数体顶层、先于业务（design §4.8 表 B 的写法），``consol_lock`` 在调用处写字面量，
    两条路由各一种。业务真写库：给请求涉及的每个项目各加一条附注，并把调用记入 ``calls``。"""

    async def _save(db: AsyncSession, project_ids: list[uuid.UUID], operator: User) -> dict[str, bool]:
        calls.append((tuple(project_ids), operator.id))
        for project_id in dict.fromkeys(project_ids):
            db.add(DisclosureNote(
                project_id=project_id, year=2025, note_section=WRITTEN_SECTION, section_title=WRITTEN_TITLE,
                text_content=WRITTEN_TEXT,
            ))
        await db.flush()
        return {"saved": True}

    router = APIRouter()

    @router.post(_LOCK_PATH)
    async def _with_consol_lock(
        body: _ProbeBody, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    ):
        await assert_note_edit_access_on_projects(db, current_user, body.project_ids, consol_lock=True)
        return await _save(db, body.project_ids, current_user)

    @router.post(_NO_LOCK_PATH)
    async def _without_consol_lock(
        body: _ProbeBody, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    ):
        await assert_note_edit_access_on_projects(db, current_user, body.project_ids, consol_lock=False)
        return await _save(db, body.project_ids, current_user)

    api = FastAPI()
    api.include_router(router)
    return api


async def _snapshot(db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """权限世界六张表的全部行（按主键排序、逐列取值）。"""
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in WORLD_TABLES:
        result = await db.execute(select(table).order_by(*table.primary_key.columns))
        tables[table.name] = [dict(row._mapping) for row in result]
    return tables


@dataclass(frozen=True)
class Observed:
    status: int
    body: Any
    gate_runs: dict[str, int]  # 本次请求里各生产门禁代码开始执行的次数
    judged: list[uuid.UUID]  # 归档一步的语句绑定的项目，按发生先后
    calls: Calls
    before: dict[str, list[dict[str, Any]]]
    after: dict[str, list[dict[str, Any]]]
    caller_id: uuid.UUID


async def _observe(scenario: Scenario) -> Observed:
    """在新的权限世界里造数 → 取快照 → 经最小测试端点发一次请求 → 再取快照。"""
    calls: Calls = []
    with pytest.MonkeyPatch.context() as monkeypatch:
        async with sqlite_world(monkeypatch) as world:
            user = await _arrange(world, scenario)
            async with world.client_for_app(_probe_app(calls), user=user) as client:
                before = await _snapshot(world.db)
                _forget_projects(world)
                with StepRecorder(world) as recorder:
                    response = await client.post(
                        _LOCK_PATH if scenario.consol_lock else _NO_LOCK_PATH,
                        json={"project_ids": [str(PROJECT_IDS[index]) for index in scenario.request]},
                    )
                after = await _snapshot(world.db)
            return Observed(
                response.status_code, response.json(), client.gate_runs, _judged(recorder.records, "archive"),
                calls, before, after, user.id,
            )


def _check_property(scenario: Scenario) -> None:
    """Property 8 的全部断言：结论与错误体等于模型；拒绝时任何项目都没有数据写入，放行时同一观测看得到业务写入。"""
    expected = _model(scenario)
    observed = asyncio.run(_observe(scenario))
    ordered_ids = [PROJECT_IDS[index] for index in expected.ordered]
    # 每个涉及的项目都单独判定了一次：去重后按先后，遇到拒绝也判完全部项目（需求 8.5「对请求涉及的每个项目逐一判定」）
    assert (observed.gate_runs[MULTI], observed.gate_runs[IMPL]) == (1, len(ordered_ids))
    assert observed.judged == ordered_ids
    if expected.detail is not None:
        # 拒绝：任何项目都没有数据写入（先核数据与业务调用，再核响应）
        assert observed.after == observed.before, "拒绝后权限世界的数据变了"
        assert observed.calls == []
        assert (observed.status, observed.body) == (expected.status, {"detail": expected.detail})
        return
    # 放行（正向对照）：业务恰 1 次、操作人为调用者本人；同一观测看得到它的写入，其余行逐值不变
    assert observed.calls == [(tuple(PROJECT_IDS[index] for index in scenario.request), observed.caller_id)]
    assert (observed.status, observed.body) == (200, {"saved": True})
    before, after = observed.before, observed.after
    assert {name: rows for name, rows in after.items() if name != _NOTES} == {
        name: rows for name, rows in before.items() if name != _NOTES
    }
    kept = {row["id"] for row in before[_NOTES]}
    assert [row for row in after[_NOTES] if row["id"] in kept] == before[_NOTES]
    written = sorted(
        (row["project_id"], row["note_section"], row["section_title"], row["text_content"])
        for row in after[_NOTES] if row["id"] not in kept
    )
    assert written == sorted((project_id, WRITTEN_SECTION, WRITTEN_TITLE, WRITTEN_TEXT) for project_id in ordered_ids)


# ─── 生成器（design §8.3：1~4 个项目，每个项目上的身份情形随机，含归档、EQCR、非成员） ────────

_members = st.none() | st.tuples(st.sampled_from(LEVELS), st.sampled_from(PROJECT_ROLES))


@st.composite
def _situations(draw: st.DrawFn) -> Situation:
    member = draw(_members)
    return Situation(
        archived=draw(st.booleans()), locked=draw(st.booleans()), member=member,
        deleted=member is not None and draw(st.booleans()), alias=draw(st.sampled_from(ALIASES)),
    )


@st.composite
def _scenarios(draw: st.DrawFn) -> Scenario:
    count = draw(st.integers(min_value=1, max_value=4))
    request = list(draw(st.permutations(list(range(count)))))
    for _ in range(draw(st.integers(min_value=0, max_value=2))):  # 再插入 0~2 个重复出现的项目（去重保序）
        request.insert(draw(st.integers(min_value=0, max_value=len(request))), draw(st.integers(0, count - 1)))
    return Scenario(
        global_role=draw(st.sampled_from(GLOBAL_ROLES)), consol_lock=draw(st.booleans()),
        situations=tuple(draw(_situations()) for _ in range(count)), request=tuple(request),
    )


# ─── 显式样例（@example：补固定样例没有覆盖的维度，结论按模型核对） ──────────────────

_EDIT = ("edit", "manager")
_E1 = Scenario(  # 4 个项目、请求里重复出现；三种 403 各一，不判合并锁时合并锁定的项目照样通过 ⇒ 403，列 P4、P1、P2
    global_role="qc", consol_lock=False,
    situations=(
        Situation(member=("review", "partner"), alias="独立复核合伙人"),  # EQCR 只读（中文别名）
        Situation(member=("review", "qc")),  # 全局 qc ∪ 项目角色 qc 不含 note:edit：操作矩阵
        Situation(member=_EDIT, locked=True),  # 通过
        Situation(member=_EDIT, deleted=True),  # 只有已删除成员行：权限不足
    ),
    request=(2, 3, 0, 2, 1),
    name="E1-four-projects-three-kinds-of-403",
)
_E2 = Scenario(  # admin：不要求成员行、不判矩阵，不豁免归档与合并锁；非 EQCR 委派不影响结论 ⇒ 423，列 P2、P3
    global_role="admin", consol_lock=True,
    situations=(
        Situation(alias="manager"),  # 非成员：通过
        Situation(member=("readonly", "readonly"), locked=True),  # 合并锁定
        Situation(archived=True, alias="eqcr"),  # 归档先于 EQCR
    ),
    request=(1, 0, 2),
    name="E2-admin-only-423",
)


# ─── 固定样例（design §8.3 性质 8：全部通过；一个 403 + 一个 423 ⇒ 403；只有 423 ⇒ 423）──────────


@dataclass(frozen=True)
class FixedCase:
    scenario: Scenario
    status: int  # 按任务原文写死的整单结论，200 为放行
    denied: tuple[int, ...]  # 未通过的项目下标，按判定先后


FIXED: tuple[FixedCase, ...] = (
    FixedCase(Scenario(  # 4 个项目都通过、请求里重复出现：也是零写入观测的正向对照（业务恰 1 次，看得到写入）
        "auditor", True,
        (Situation(member=_EDIT), Situation(member=("review", "qc")),
         Situation(member=("review", "partner"), alias="manager"), Situation(member=("edit", "auditor"))),
        request=(3, 1, 0, 3, 2, 1), name="all-pass",
    ), 200, ()),
    FixedCase(Scenario(  # 归档 423 在前、中间一个通过、非成员 403 在后 ⇒ 403，两个都列出
        "auditor", True, (Situation(member=_EDIT, archived=True), Situation(member=_EDIT), Situation()),
        request=(0, 1, 2), name="one-403-one-423-is-403",
    ), 403, (0, 2)),
    FixedCase(Scenario(  # 一个通过，归档与合并锁定各一个 423 ⇒ 423
        "auditor", True,
        (Situation(member=_EDIT), Situation(member=_EDIT, archived=True), Situation(member=_EDIT, locked=True)),
        request=(0, 1, 2), name="only-423-is-423",
    ), 423, (1, 2)),
)


@pytest.fixture(autouse=True)
def _dev_database_untouched() -> Iterator[None]:
    """不得经 ``app.core.database`` 的正式引擎（连本地开发库）发语句：记录并拦下（同 6.2、6.3 的两个单元测试文件）。"""
    hits: list[str] = []
    target = core_database.engine.sync_engine

    def _deny(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        hits.append(" ".join(statement.split()[:3]))
        raise RuntimeError("测试期间禁止经 app.core.database.engine 访问本地开发库")

    event.listen(target, "before_cursor_execute", _deny)
    yield
    event.remove(target, "before_cursor_execute", _deny)
    assert hits == [], f"经正式引擎（本地开发库）发出了语句：{hits}"


# ─── Property 8 ──────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(scenario=_scenarios())
@example(scenario=_E1)
@example(scenario=_E2)
def test_property_8_multi_project_gate_rejects_whole_request(scenario: Scenario) -> None:
    # Feature: partner-manager-edit-permission, Property 8: 多项目判定整单拒绝
    expected = _model(scenario)
    hypothesis.event(f"整单结论 {expected.status}")  # 只进 --hypothesis-show-statistics 的统计，不参与判定
    hypothesis.event(f"涉及项目数 {len(expected.ordered)}")
    _check_property(scenario)


@pytest.mark.parametrize("case", FIXED, ids=[case.scenario.name for case in FIXED])
def test_property_8_fixed_examples(case: FixedCase) -> None:
    """性质 8 的三个固定样例：整单结论与未通过的项目按任务原文写死，先核对模型，再跑 Property 8 的全部断言。"""
    expected = _model(case.scenario)
    assert (expected.status, expected.denied) == (case.status, case.denied), "模型与固定样例不一致"
    _check_property(case.scenario)
