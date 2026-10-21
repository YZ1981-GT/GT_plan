"""附注编辑门禁多项目形态的函数级单元测试（partner-manager-edit-permission 任务 6.3；需求 8.5；design §4.6）。

被测 ``app.services.note_edit_gate.assert_note_edit_access_on_projects``，在权限世界（``tests/authz_world.py`` 的 SQLite 版）里
直接调用。做法与 ``test_note_edit_gate_unit.py`` 相同，并从该文件导入语句记录器与观测名：只替换 RLS 设置（记录项目 id），门禁与
判定一个都不替换；故障只注在 EQCR 判定的下一层 ``eqcr_resolver._count_project_eqcr_assignments``。各项目上的结论全部由库里的
项目状态、成员行与委派给出。本文件只放固定样例；Property 8（多项目判定整单拒绝）的性质测试在任务 6.4。

期望的状态码、错误码与 detail 字段按需求 8.5 与 design §4.6 写死，不读生产常量。design 只规定「中文 message 列出未通过的项目 id」、
没有给出原文：message 的写法（前缀 + 逐个「项目 id（该项目单独判定的原因）」，以「、」连接）由本文件钉住。
"""
from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event

import app.core.database as core_database
import app.services.eqcr_resolver as eqcr_resolver
import app.services.note_edit_gate as note_edit_gate
from app.models.base import ProjectStatus
from app.models.core import Project, User
from app.services.note_edit_gate import note_edit_rejection_reason
from tests.authz_world import (
    OTHER_PROJECT_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    GateTrace,
    assert_gates_are_production,
    sqlite_world,
)
from tests.test_note_edit_gate_unit import EQCR_JUDGE, IMPL, INJECTED, StepRecorder, _forget_projects

MULTI = "app.services.note_edit_gate.assert_note_edit_access_on_projects"
THIRD_PROJECT_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e11")
PREFIX = "以下项目未通过附注编辑权限判定："
ERROR_CODE = "NOTE_EDIT_MULTI_PROJECT_DENIED"
# 调用者在单个项目上的情形 → 该项目单独判定的拒绝原因（需求 6.4~6.7 与 design §4.6 原文）
REASON = {
    "none": "权限不足",
    "readonly": "权限不足",
    "eqcr": "独立复核合伙人（EQCR）在本项目只读，不能编辑附注",
    "archived": "项目已归档，无法编辑",
    "locked": "项目已被合并锁定，无法修改",
}
# 逐项目判定里过了归档与成员两步（assert_project_permission 此时为该项目设置 RLS）的情形；admin 不看成员行
PAST_MEMBER_STEP = {"auditor": {"edit", "eqcr", "locked"}, "admin": {"none", "edit", "readonly", "eqcr", "locked"}}


@pytest.fixture(autouse=True)
def _dev_database_untouched() -> Iterator[None]:
    """不得经 ``app.core.database`` 的正式引擎（连本地开发库）发语句：记录并拦下（同 ``test_note_edit_gate_unit.py``）。"""
    hits: list[str] = []
    target = core_database.engine.sync_engine

    def _deny(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        hits.append(" ".join(statement.split()[:3]))
        raise RuntimeError("测试期间禁止经 app.core.database.engine 访问本地开发库")

    event.listen(target, "before_cursor_execute", _deny)
    yield
    event.remove(target, "before_cursor_execute", _deny)
    assert hits == [], f"经正式引擎（本地开发库）发出了语句：{hits}"


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def _project(world: AuthzWorld, index: int) -> Project:
    if index == 0:
        return world.target
    if index == 1:
        return await world.other_project()
    return await world.project(project_id=THIRD_PROJECT_ID, name="【测试】多项目判定第三个项目")


async def _arrange(world: AuthzWorld, global_role: str, situations: tuple[str, ...]) -> tuple[User, list[uuid.UUID]]:
    """调用者在第 i 个项目（依次为目标项目、另一项目、第三个项目）上的情形取 ``situations[i]``：none 无成员行；
    edit (manager, edit)；readonly (readonly, readonly)；eqcr (partner, review) 且持 ``eqcr`` 现行委派；archived / locked
    为 (manager, edit) 且项目已归档 / 合并锁定。返回调用者与各项目 id。"""
    user = await world.user(global_role)
    projects = [await _project(world, index) for index in range(len(situations))]
    for project, situation in zip(projects, situations, strict=True):
        if situation in ("edit", "archived", "locked"):
            await world.member("edit", "manager", project=project, user=user)
        elif situation == "readonly":
            await world.member("readonly", "readonly", project=project, user=user)
        elif situation == "eqcr":
            await world.member("review", "partner", project=project, user=user)
            await world.eqcr_assignment("eqcr", user=user, project=project)
        if situation == "archived":
            project.status = ProjectStatus.archived
        project.consol_lock = situation == "locked"
    await world.db.flush()
    world.replace_rls()
    _forget_projects(world)  # 归档守卫的 db.get 每个项目都真发语句，读库里的现值
    return user, [project.id for project in projects]


async def _call(world: AuthzWorld, user: User, project_ids: Iterable[uuid.UUID], *, consol_lock: bool) -> Any:
    """直接调用多项目形态：放行返回门禁的返回值，拒绝返回 ``HTTPException``，其他异常照常抛出。"""
    assert_gates_are_production()
    try:
        return await note_edit_gate.assert_note_edit_access_on_projects(world.db, user, project_ids, consol_lock=consol_lock)
    except HTTPException as exc:
        return exc


def _judged(records: list[tuple[str, tuple[uuid.UUID, ...]]], step: str) -> list[uuid.UUID]:
    """记录里某一步绑定的项目 id，按发生先后（各步语句的首个绑定参数都是项目 id）。"""
    return [uuids[0] for name, uuids in records if name == step]


# ═══ 一、结论与错误体 ═══════════════════════════════════════════════════════


@dataclass(frozen=True)
class MultiCase:
    name: str
    situations: tuple[str, ...]
    status: int | None  # 期望状态码；None 为放行
    denied: tuple[int, ...] = ()  # 未通过的项目（situations 的下标，按判定先后）
    global_role: str = "auditor"
    consol_lock: bool = True


MULTI_CASES: tuple[MultiCase, ...] = (
    # design §8.3 性质 8 的三个固定样例：全部通过；一个 403 + 一个 423 ⇒ 403；只有 423 ⇒ 423
    MultiCase("all-pass", ("edit", "edit", "edit"), None),
    MultiCase("one-423-one-403-is-403", ("archived", "none"), 403, (0, 1)),
    MultiCase("only-423-is-423", ("archived", "locked"), 423, (0, 1)),
    # 403 不论先后；EQCR 只读、readonly 都按 403；通过的项目不列出
    MultiCase("one-403-one-423-is-403", ("none", "archived"), 403, (0, 1)),
    MultiCase("eqcr-is-403", ("edit", "eqcr"), 403, (1,)),
    MultiCase("readonly-and-archived-around-a-pass", ("readonly", "edit", "archived"), 403, (0, 2)),
    MultiCase("single-423-among-passes", ("edit", "locked", "edit"), 423, (1,)),
    MultiCase("single-project-403", ("none",), 403, (0,)),
    # consol_lock 原样传给每个项目的判定
    MultiCase("locked-without-lock-check", ("edit", "locked"), None, consol_lock=False),
    # admin：不要求成员行，不豁免归档与 EQCR
    MultiCase("admin-all-pass", ("none", "edit"), None, global_role="admin"),
    MultiCase("admin-eqcr-and-archived-is-403", ("eqcr", "archived"), 403, (0, 1), global_role="admin"),
    MultiCase("admin-archived-is-423", ("none", "archived"), 423, (1,), global_role="admin"),
)


@pytest.mark.parametrize("case", MULTI_CASES, ids=[case.name for case in MULTI_CASES])
async def test_multi_project_verdict_and_error_body(world: AuthzWorld, case: MultiCase) -> None:
    """每个项目都调一次判定实现（遇到拒绝也判完全部项目，再下结论）。放行当且仅当每个项目都放行，并在最后把 RLS 重设为首个
    项目；拒绝时有 403 即 403、否则 423，detail 逐值等于期望（错误码、列出未通过项目及原因的中文 message、``project_ids``），
    且不重设 RLS（需求 8.5；design §4.6）。"""
    user, project_ids = await _arrange(world, case.global_role, case.situations)
    with StepRecorder(world) as recorder, GateTrace() as trace:
        outcome = await _call(world, user, project_ids, consol_lock=case.consol_lock)
    assert (trace.counts[MULTI], trace.counts[IMPL]) == (1, len(project_ids))
    assert _judged(recorder.records, "archive") == project_ids  # 每个项目按先后各判一次
    rls_during_judgment = [
        str(project_id) for project_id, situation in zip(project_ids, case.situations, strict=True)
        if situation in PAST_MEMBER_STEP[case.global_role]
    ]
    if case.status is None:
        assert outcome is user
        assert world.rls_calls == [*rls_during_judgment, str(project_ids[0])]  # 最后一次重设为首个项目
        return
    denied = [project_ids[index] for index in case.denied]
    message = PREFIX + "、".join(f"{project_ids[index]}（{REASON[case.situations[index]]}）" for index in case.denied)
    assert isinstance(outcome, HTTPException), outcome
    assert (outcome.status_code, outcome.detail) == (
        case.status, {"error_code": ERROR_CODE, "message": message, "project_ids": [str(pid) for pid in denied]},
    )
    assert note_edit_rejection_reason(outcome) == message
    assert world.rls_calls == rls_during_judgment  # 拒绝：不重设


# ═══ 二、去重保序 ═══════════════════════════════════════════════════════════


async def test_multi_project_dedups_keeping_first_occurrence_order(world: AuthzWorld) -> None:
    """重复出现的项目只判一次，按首次出现的先后判；放行后 RLS 重设为去重后的首个项目。入参可以是任意可迭代对象（这里是生成器）。"""
    user, (target, other, third) = await _arrange(world, "auditor", ("edit", "edit", "edit"))
    requested = [other, target, other, third, target]
    with StepRecorder(world) as recorder, GateTrace() as trace:
        outcome = await _call(world, user, (project_id for project_id in requested), consol_lock=False)
    assert outcome is user
    assert (trace.counts[MULTI], trace.counts[IMPL]) == (1, 3)
    assert _judged(recorder.records, "member") == [other, target, third]
    assert world.rls_calls == [str(other), str(target), str(third), str(other)]


async def test_multi_project_lists_a_repeated_denied_project_once(world: AuthzWorld) -> None:
    """未通过的项目在请求里重复出现，也只判一次、只列一次。"""
    user, (target, other) = await _arrange(world, "auditor", ("none", "edit"))
    with GateTrace() as trace:
        outcome = await _call(world, user, [target, other, target, target], consol_lock=True)
    assert trace.counts[IMPL] == 2
    assert isinstance(outcome, HTTPException), outcome
    assert (outcome.status_code, outcome.detail) == (
        403, {"error_code": ERROR_CODE, "message": f"{PREFIX}{target}（权限不足）", "project_ids": [str(target)]},
    )


# ═══ 三、其他异常原样冒泡 ═══════════════════════════════════════════════════

_UNCOLLECTED: list[Any] = [
    pytest.param(RuntimeError, lambda: RuntimeError(INJECTED), id="query-error"),
    pytest.param(HTTPException, lambda: HTTPException(status_code=503, detail=INJECTED), id="http-503"),
]


@pytest.mark.parametrize(("error_type", "make_error"), _UNCOLLECTED)
async def test_multi_project_other_exceptions_propagate_as_is(
    world: AuthzWorld, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception],
    make_error: Callable[[], Exception],
) -> None:
    """第一个项目已判为 403（记下），第二个项目的 EQCR 委派查询出错：异常原样冒泡 —— 不当成拒绝收集、不并入整单拒绝
    （403 / 423 以外状态码的 ``HTTPException`` 同样如此），第三个项目不再判，RLS 不重设（design §4.6；需求 7.6 的出错语义）。"""
    user, project_ids = await _arrange(world, "auditor", ("none", "edit", "edit"))
    raised: list[Exception] = []

    async def _failing(_db: Any, _user_id: uuid.UUID, _project_id: uuid.UUID) -> int:
        raised.append(make_error())
        raise raised[-1]

    monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _failing)
    with StepRecorder(world) as recorder, GateTrace() as trace:
        with pytest.raises(error_type) as exc_info:
            await note_edit_gate.assert_note_edit_access_on_projects(world.db, user, project_ids, consol_lock=True)
    assert raised == [exc_info.value]  # 冒泡出来的就是注入的那个异常对象
    assert getattr(exc_info.value, "detail", str(exc_info.value)) == INJECTED
    assert (trace.counts[IMPL], trace.counts[EQCR_JUDGE]) == (2, 1)
    assert _judged(recorder.records, "archive") == project_ids[:2]
    assert world.rls_calls == [str(project_ids[1])]


# ═══ 四、签名与参数 fail-closed ═════════════════════════════════════════════


def test_multi_project_signature_matches_design() -> None:
    """design §4.6 的签名：``consol_lock`` 是无默认值的仅关键字参数（调用处必须写明是否判合并锁）。"""
    parameters = inspect.signature(note_edit_gate.assert_note_edit_access_on_projects).parameters
    assert [(name, p.kind.name, p.default is inspect.Parameter.empty) for name, p in parameters.items()] == [
        ("db", "POSITIONAL_OR_KEYWORD", True), ("current_user", "POSITIONAL_OR_KEYWORD", True),
        ("project_ids", "POSITIONAL_OR_KEYWORD", True), ("consol_lock", "KEYWORD_ONLY", True),
    ]


_BAD_ARGUMENTS = [
    pytest.param([], True, ValueError, "至少需要一个项目", id="no-project"),
    pytest.param(str(TARGET_PROJECT_ID), True, TypeError, "项目须为 UUID，收到 ['str']", id="id-string-as-sequence"),
    pytest.param([TARGET_PROJECT_ID, str(OTHER_PROJECT_ID)], True, TypeError, "项目须为 UUID，收到 ['UUID', 'str']",
                 id="string-element"),
    pytest.param([TARGET_PROJECT_ID], None, TypeError, "on_projects 的 consol_lock 须为 True 或 False，收到 None",
                 id="consol-lock-none"),
]


@pytest.mark.parametrize(("project_ids", "consol_lock", "error", "fragment"), _BAD_ARGUMENTS)
async def test_multi_project_rejects_bad_arguments_before_any_query(
    world: AuthzWorld, project_ids: Any, consol_lock: Any, error: type[Exception], fragment: str,
) -> None:
    """参数 fail-closed（任务 6.3 新增；design 只规定 ``consol_lock`` 必填）：没有项目、项目不是 UUID（含把单个 id 字符串当
    序列传入）、``consol_lock`` 不是 bool，都在任何读库与判定之前报错，也不设置 RLS。调用者是参数正确时会放行的 admin。"""
    user = await world.user("admin")
    world.replace_rls()
    _forget_projects(world)
    with StepRecorder(world) as recorder, GateTrace() as trace:
        with pytest.raises(error) as exc_info:
            await note_edit_gate.assert_note_edit_access_on_projects(world.db, user, project_ids, consol_lock=consol_lock)
    assert fragment in str(exc_info.value)
    assert (recorder.records, trace.counts[MULTI], trace.counts[IMPL], world.rls_calls) == ([], 1, 0, [])
