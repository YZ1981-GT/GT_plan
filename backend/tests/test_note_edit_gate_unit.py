"""附注编辑门禁的函数级单元测试（partner-manager-edit-permission 任务 6.2、6.3；需求 6.2~6.8、6.11、6.12、7.6、8.3）。

被测 ``app.services.note_edit_gate`` 的三种挂载形态与角色限定形态，全部在权限世界（``tests/authz_world.py`` 的 SQLite 版）里运行：
- 函数体 ``assert_note_edit_access``：直接调用。
- 对象反查 ``assert_note_edit_access_for_object``：直接调用，对象为世界里的附注章节（``DisclosureNote``）。
- 路径依赖 ``require_note_edit_access``：挂在本文件的最小测试路由上（``consol_lock`` 取 True / False 各一条路由），
  经 ``world.client_for_app`` 用 httpx 真发请求；路由的业务处理换成计数桩（放行恰 1 次、拒绝 0 次）。
- 角色限定 ``assert_note_role_access``（design 定级形态，任务 6.3）：直接调用。另一个 design 定级形态（多项目）的函数级用例
  在 ``test_note_edit_gate_multi_project_unit.py``。

替换范围（需求 12.1）：只替换 RLS 设置（记录项目 id）与测试路由的业务处理。归档、成员级别、EQCR、操作矩阵、合并锁的输入
全部由库里的项目、成员行、人员库记录与委派给出，门禁与判定一个都不替换。故障只注在 EQCR 判定的下一层：
``eqcr_resolver._count_project_eqcr_assignments`` 本身，或驱动层的委派条数语句（需求 7.6）。

判定步骤的可观测证据：各步取数的语句形态互不相同。``StepRecorder`` 在世界引擎上以 ``before_cursor_execute`` 记下语句，
按形态归为 projection（对象反查的一列投影）/ archive（归档守卫取项目行）/ member（成员级别）/ eqcr（EQCR 别名委派条数）/
matrix（成员行项目角色）/ consol_lock（合并锁标记），认不出的记为 other。期望序列按 design §4.6 的判定顺序写死：前一步拒绝
即序列在该步截止；admin 跳过成员与矩阵即序列里没有 member / matrix；``consol_lock=False`` 即没有 consol_lock。全局角色为
eqcr 时 EQCR 判定不发语句，该步另由 ``GateTrace``（PEP 669，只观测不替换）计 ``is_project_eqcr`` 的执行次数。正向对照
``test_step_recorder_positive_control`` 逐一执行各步的取数（对象投影按门禁同一写法，其余直接调用生产取数函数），证明
记录器认得出每一种语句。

归档守卫用 ``db.get`` 取项目：项目对象已在会话身份映射里时不发语句。每次判定前把会话里的项目对象移出（``_forget_projects``），
归档判定读的就是库里的现值（与生产里每个请求一个新会话相同），只改变取数是否经过语句，不改变结论。

期望的状态码、detail 与原因按需求 6.4~6.8、6.12 与 design §4.6 原文写死，不读生产常量（改文案即红）。
"""
from __future__ import annotations

import inspect
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy.exc
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from sqlalchemy import event, select

import app.core.database as core_database
import app.deps as deps
import app.services.eqcr_resolver as eqcr_resolver
import app.services.note_edit_gate as note_edit_gate
from app.models.base import PermissionLevel, ProjectStatus
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.note_edit_gate import note_edit_rejection_reason, require_note_edit_access
from tests.authz_world import (
    OTHER_PROJECT_ID,
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    GateTrace,
    ServiceStub,
    assert_gates_are_production,
    sqlite_world,
)

# ─── 期望（按需求与 design §4.6 原文写死） ──────────────────────────────────


@dataclass(frozen=True)
class Rejection:
    status: int
    detail: Any  # HTTPException.detail 原样
    reason: str  # note_edit_rejection_reason 应取回的中文原因（D13）


ALLOW = "放行"
# ① 归档（需求 6.7，沿用 _check_project_not_archived 的现有提示）
ARCHIVED = Rejection(423, {
    "error_code": "PROJECT_ARCHIVED", "message": "项目已归档，无法编辑", "message_en": "Project archived (read-only)",
}, "项目已归档，无法编辑")
# ② 非成员 / readonly 成员（需求 6.4，沿用项目级鉴权的固定文案）
FORBIDDEN = Rejection(403, "权限不足", "权限不足")
# ③ 本项目 EQCR（需求 6.5；design §4.6 REASON_EQCR_READONLY）
EQCR_READONLY = Rejection(403, {
    "error_code": "NOTE_EDIT_EQCR_READONLY", "message": "独立复核合伙人（EQCR）在本项目只读，不能编辑附注",
}, "独立复核合伙人（EQCR）在本项目只读，不能编辑附注")
# ④ 操作矩阵不放行 note:edit（需求 6.12；design §4.6 REASON_OPERATION_DENIED）
OPERATION_DENIED = Rejection(403, {
    "error_code": "NOTE_EDIT_OPERATION_DENIED", "message": "您在本项目的角色没有编辑附注的操作权限",
}, "您在本项目的角色没有编辑附注的操作权限")
# ⑤ 合并锁（需求 6.6，沿用 check_consol_lock 的现有提示）
CONSOL_LOCKED = Rejection(423, "项目已被合并锁定，无法修改", "项目已被合并锁定，无法修改")
NOTE_NOT_FOUND = "附注章节不存在"  # 对象不存在（需求 6.8，沿用现有文案）

MISSING_NOTE_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e09")  # 库里没有的附注
OTHER_NOTE_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e0a")  # 另一项目上的附注
INJECTED = "注入：委派查询失败"

FORMS = ("body", "object", "path")
_STEP = {"P": "projection", "A": "archive", "M": "member", "E": "eqcr", "X": "matrix", "L": "consol_lock"}

# 生产门禁代码的观测名（GateTrace.counts / GateClient.gate_runs 的键）
IMPL = "app.services.note_edit_gate.assert_note_edit_access"
FOR_OBJECT = "app.services.note_edit_gate.assert_note_edit_access_for_object"
CLOSURE = "app.services.note_edit_gate.require_note_edit_access.<locals>.dependency"
PROJECT_PERMISSION = "app.deps.assert_project_permission"
EQCR_JUDGE = "app.services.eqcr_resolver.is_project_eqcr"


# ─── 语句记录器 ──────────────────────────────────────────────────────────────

# 各步取数语句的形态（空白归一后整句匹配），与 design §4.6 的判定步骤一一对应
_STEP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("projection", re.compile(
        r"SELECT disclosure_notes\.project_id FROM disclosure_notes WHERE disclosure_notes\.id = \?")),
    ("archive", re.compile(
        r"SELECT projects\.id AS projects_id, .*\bprojects\.status AS projects_status\b.* FROM projects"
        r" WHERE projects\.id = \?")),
    ("member", re.compile(r"SELECT project_users\.permission_level FROM project_users WHERE .+")),
    ("eqcr", re.compile(
        r"SELECT count\(project_assignments\.id\) AS count_1 FROM project_assignments JOIN staff_members .+")),
    ("matrix", re.compile(r"SELECT project_users\.role FROM project_users WHERE .+")),
    ("consol_lock", re.compile(r"SELECT projects\.consol_lock FROM projects WHERE projects\.id = \?")),
)
_HEX32 = re.compile(r"[0-9a-f]{32}")  # SQLite 上 UUID 列按 32 位十六进制绑定


def _classify(statement: str) -> str:
    text = " ".join(statement.split())
    for step, pattern in _STEP_PATTERNS:
        if pattern.fullmatch(text):
            return step
    return f"other: {text[:80]}"


class StepRecorder:
    """在权限世界引擎上记下发出的每条语句：（步骤名，绑定参数里的 UUID）。只记录，不改变语句。"""

    def __init__(self, world: AuthzWorld) -> None:
        self._engine = world.db.bind.sync_engine
        self.records: list[tuple[str, tuple[uuid.UUID, ...]]] = []

    def __enter__(self) -> StepRecorder:
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc: object) -> None:
        event.remove(self._engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, _conn: Any, _cursor: Any, statement: str, parameters: Any, *_rest: Any) -> None:
        uuids = tuple(uuid.UUID(p) for p in parameters or () if isinstance(p, str) and _HEX32.fullmatch(p))
        self.records.append((_classify(statement), uuids))

    @property
    def steps(self) -> list[str]:
        return [step for step, _uuids in self.records]


def _forget_projects(world: AuthzWorld) -> None:
    """把会话身份映射里的项目对象移出：归档守卫的 ``db.get`` 随之真发语句，读库里的现值。"""
    for obj in list(world.db.identity_map.values()):
        if isinstance(obj, Project):
            world.db.expunge(obj)


# ─── 路径依赖形态的最小测试路由 ──────────────────────────────────────────────

STUB_RESULT = {"saved": True}
_LOCK_PATH = "/api/projects/{project_id}/note-edit-gate-unit/with-consol-lock"
_NO_LOCK_PATH = "/api/projects/{project_id}/note-edit-gate-unit/without-consol-lock"
_PROBE = APIRouter()


class _NoteWrite:
    """测试路由的业务处理挂点；用例里经 ``world.stub`` 换成计数桩。"""

    @staticmethod
    async def save(project_id: uuid.UUID, operator_id: uuid.UUID) -> dict[str, bool]:
        raise AssertionError("测试路由的业务处理未打桩")


@_PROBE.put(_LOCK_PATH)
async def _write_with_consol_lock(
    project_id: uuid.UUID, current_user: User = Depends(require_note_edit_access(consol_lock=True)),
):
    return await _NoteWrite.save(project_id, current_user.id)


@_PROBE.put(_NO_LOCK_PATH)
async def _write_without_consol_lock(
    project_id: uuid.UUID, current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    return await _NoteWrite.save(project_id, current_user.id)


def _probe_app() -> FastAPI:
    api = FastAPI()
    api.include_router(_PROBE)
    return api


# ─── 用例表 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Who:
    """调用者：全局角色；目标项目上的成员行（项目角色，级别）及是否已删除；另一项目上的（manager, edit）成员行；
    本项目现行委派的角色。"""

    global_role: str = "auditor"
    member: tuple[str, str] | None = None
    member_deleted: bool = False
    other_member: bool = False
    eqcr_alias: str | None = None


@dataclass(frozen=True)
class Case:
    name: str
    who: Who
    verdict: Any  # ALLOW 或 Rejection
    steps: str  # 期望执行的判定步骤，_STEP 的代码按发生先后
    consol_lock: bool = True
    archived: bool = False
    locked: bool = False

    @property
    def eqcr_judged(self) -> bool:
        """走到了第 ③ 步：归档 423 与「权限不足」以外的结论都先经过 EQCR 判定。"""
        return self.verdict is not ARCHIVED and self.verdict is not FORBIDDEN


EDIT = Who(member=("manager", "edit"))  # 需求 12.2 身份①
REVIEW = Who(member=("qc", "review"))  # 身份②
READONLY = Who(member=("readonly", "readonly"))  # 身份③
NON_MEMBER = Who(other_member=True)  # 身份④
PROJECT_EQCR = Who(member=("partner", "review"), eqcr_alias="eqcr")  # 身份⑤
QC_REVIEW = Who("qc", member=("qc", "review"))  # 需求 12.4 ⑦
ADMIN = Who("admin")  # ⑧

CASES: tuple[Case, ...] = (
    # ① 归档 423：对任何调用者（含 admin、非成员、readonly 成员与 EQCR）先于其余各步（需求 6.7）
    Case("archived-admin", ADMIN, ARCHIVED, "A", archived=True),
    Case("archived-non-member", NON_MEMBER, ARCHIVED, "A", archived=True),
    Case("archived-readonly-member", READONLY, ARCHIVED, "A", archived=True),
    Case("archived-project-eqcr", PROJECT_EQCR, ARCHIVED, "A", archived=True),
    Case("archived-and-locked-edit-member", EDIT, ARCHIVED, "A", archived=True, locked=True),
    # ② 非 admin、无未删除成员行或级别 readonly → 403「权限不足」，不再判 EQCR、矩阵与合并锁（需求 6.4、6.5 末句）
    Case("non-member", NON_MEMBER, FORBIDDEN, "AM"),
    Case("non-member-locked", NON_MEMBER, FORBIDDEN, "AM", locked=True),
    Case("readonly-member", READONLY, FORBIDDEN, "AM"),
    Case("deleted-member-row-only", Who(member=("manager", "edit"), member_deleted=True), FORBIDDEN, "AM"),
    Case("readonly-member-with-eqcr-assignment", Who(member=("readonly", "readonly"), eqcr_alias="eqcr"),
         FORBIDDEN, "AM"),
    Case("global-eqcr-non-member", Who("eqcr"), FORBIDDEN, "AM"),
    # ③ 本项目 EQCR → 403 只读，admin 不豁免；不再判矩阵与合并锁（需求 6.5、7.1）
    Case("project-eqcr", PROJECT_EQCR, EQCR_READONLY, "AME"),
    Case("project-eqcr-locked", PROJECT_EQCR, EQCR_READONLY, "AME", locked=True),
    Case("project-eqcr-cn-alias", Who(member=("partner", "review"), eqcr_alias="独立复核合伙人"), EQCR_READONLY, "AME"),
    Case("qc-review-member-with-eqcr-assignment", Who("qc", member=("qc", "review"), eqcr_alias="eqcr"),
         EQCR_READONLY, "AME"),
    Case("global-eqcr-review-member", Who("eqcr", member=("partner", "review")), EQCR_READONLY, "AM"),  # 全局分支不查委派
    Case("admin-with-eqcr-assignment", Who("admin", eqcr_alias="eqcr"), EQCR_READONLY, "AE"),
    # ④ 非 admin，全局角色 ∪ 项目角色的操作权限不含 note:edit → 403，不再判合并锁（需求 6.12）
    Case("qc-global-qc-role", QC_REVIEW, OPERATION_DENIED, "AMEX"),
    Case("qc-global-qc-role-locked", QC_REVIEW, OPERATION_DENIED, "AMEX", locked=True),
    Case("readonly-global-auditor-role", Who("readonly", member=("auditor", "edit")), OPERATION_DENIED, "AMEX"),
    # ⑤ consol_lock=True 且项目合并锁定 → 423（需求 6.6）
    Case("edit-member-locked", EDIT, CONSOL_LOCKED, "AMEXL", locked=True),
    Case("admin-locked", ADMIN, CONSOL_LOCKED, "AEL", locked=True),
    # 放行：review 及以上、非 EQCR、矩阵放行（需求 6.2）；admin 不要求成员行、不看级别、不判矩阵（需求 6.3）
    Case("edit-member", EDIT, ALLOW, "AMEXL"),
    Case("review-member", REVIEW, ALLOW, "AMEXL"),
    Case("qc-global-manager-role", Who("qc", member=("manager", "edit")), ALLOW, "AMEXL"),
    Case("admin-non-member", ADMIN, ALLOW, "AEL"),
    Case("admin-with-readonly-member-row", Who("admin", member=("readonly", "readonly")), ALLOW, "AEL"),
    # consol_lock=False：不判合并锁，项目合并锁定照样放行（需求 6.6）
    Case("edit-member-locked-without-lock-check", EDIT, ALLOW, "AMEX", consol_lock=False, locked=True),
    Case("review-member-locked-without-lock-check", REVIEW, ALLOW, "AMEX", consol_lock=False, locked=True),
    Case("admin-locked-without-lock-check", ADMIN, ALLOW, "AE", consol_lock=False, locked=True),
)


# ─── 造数与调用 ──────────────────────────────────────────────────────────────


async def _arrange(world: AuthzWorld, who: Who, *, archived: bool = False, locked: bool = False) -> User:
    """按 ``who`` 在库里建调用者、成员行与委派，设目标项目状态，并在目标项目上建一条附注（对象反查用）。"""
    user = await world.user(who.global_role)
    if who.member is not None:
        role, level = who.member
        (await world.member(level, role, user=user)).member.is_deleted = who.member_deleted
    if who.other_member:
        await world.member("edit", "manager", project=await world.other_project(), user=user)
    if who.eqcr_alias is not None:
        await world.eqcr_assignment(who.eqcr_alias, user=user)
    if archived:
        world.target.status = ProjectStatus.archived
    world.target.consol_lock = locked
    await world.add_note()
    await world.db.flush()
    world.replace_rls()
    return user


async def _call_direct(
    world: AuthzWorld, form: str, user: User, *, consol_lock: bool,
    note_id: uuid.UUID = TARGET_NOTE_ID, project_id: uuid.UUID = TARGET_PROJECT_ID,
) -> Any:
    """直接调用函数体 / 对象反查形态：放行返回门禁的返回值，拒绝返回 ``HTTPException``，其他异常照常抛出。"""
    assert_gates_are_production()
    try:
        if form == "body":
            return await note_edit_gate.assert_note_edit_access(world.db, user, project_id, consol_lock=consol_lock)
        return await note_edit_gate.assert_note_edit_access_for_object(
            world.db, user, id_column=DisclosureNote.id, project_column=DisclosureNote.project_id,
            object_id=note_id, not_found_detail=NOTE_NOT_FOUND, consol_lock=consol_lock,
        )
    except HTTPException as exc:
        return exc


def _url(consol_lock: bool, project_id: uuid.UUID = TARGET_PROJECT_ID) -> str:
    return (_LOCK_PATH if consol_lock else _NO_LOCK_PATH).format(project_id=project_id)


@dataclass
class Run:
    outcome: Any  # 直接调用：门禁返回值或 HTTPException；路径依赖：httpx Response
    records: list[tuple[str, tuple[uuid.UUID, ...]]]
    gate_runs: dict[str, int]
    stub: ServiceStub | None = None

    @property
    def steps(self) -> list[str]:
        return [step for step, _uuids in self.records]


async def _run(
    world: AuthzWorld, form: str, user: User, *, consol_lock: bool,
    note_id: uuid.UUID = TARGET_NOTE_ID, project_id: uuid.UUID = TARGET_PROJECT_ID,
) -> Run:
    """以一种形态做一次判定，记下执行过的步骤与生产门禁代码的执行次数。"""
    _forget_projects(world)
    if form == "path":
        stub = world.stub(_NoteWrite, "save", returns=STUB_RESULT)
        async with world.client_for_app(_probe_app(), user=user) as client:
            with StepRecorder(world) as recorder:
                response = await client.put(_url(consol_lock, project_id))
        return Run(response, recorder.records, client.gate_runs, stub)
    with StepRecorder(world) as recorder, GateTrace() as trace:
        outcome = await _call_direct(world, form, user, consol_lock=consol_lock, note_id=note_id, project_id=project_id)
    return Run(outcome, recorder.records, trace.counts)


def _assert_outcome(run: Run, form: str, verdict: Any, user: User, project_id: uuid.UUID = TARGET_PROJECT_ID) -> None:
    """结论逐值比较：放行 / 拒绝的状态码、detail 与原因；路径依赖形态另核业务桩（放行恰 1 次、拒绝 0 次）。"""
    outcome = run.outcome
    if form == "path":
        if verdict is ALLOW:
            assert (outcome.status_code, outcome.json()) == (200, STUB_RESULT), outcome.text
            assert run.stub.calls == [((project_id, user.id), {})]  # 业务恰 1 次，操作人为调用者本人（需求 6.2）
        else:
            assert (outcome.status_code, outcome.json()) == (verdict.status, {"detail": verdict.detail})
            assert run.stub.count == 0  # 拒绝：业务一次也不执行（需求 6.11）
        return
    if verdict is ALLOW:
        if form == "body":
            assert outcome is user  # 放行返回当前用户本人：业务以调用者本人为操作人（需求 6.2、6.3）
        else:
            assert outcome == project_id  # 对象反查形态放行返回对象所属项目
        return
    assert isinstance(outcome, HTTPException), outcome
    assert (outcome.status_code, outcome.detail) == (verdict.status, verdict.detail)
    assert note_edit_rejection_reason(outcome) == verdict.reason


def _inject_eqcr_failure(world: AuthzWorld, monkeypatch: pytest.MonkeyPatch, kind: str) -> list[BaseException]:
    """EQCR 判定的下一层出错（需求 7.6），本用例内一直生效：``query-function`` 让委派条数函数本身抛错；``driver`` 让委派
    条数语句在驱动执行时按 DBAPI 错误失败（委派查询报错 / 连接中断；SQLAlchemy 照真实库报错包成 ``OperationalError``，
    ``orig`` 为原错误），只动本世界引擎的方言实例。返回注入的异常列表，供核对冒泡出来的就是它。"""
    raised: list[BaseException] = []
    if kind == "query-function":

        async def _failing(_db: Any, _user_id: uuid.UUID, _project_id: uuid.UUID) -> int:
            raised.append(RuntimeError(INJECTED))
            raise raised[-1]

        monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _failing)
    else:
        dialect = world.db.bind.sync_engine.dialect
        do_execute, dbapi_error = dialect.do_execute, dialect.loaded_dbapi.OperationalError

        def _failing_execute(cursor: Any, statement: str, parameters: Any, context: Any = None) -> None:
            if _classify(statement) == "eqcr":
                raised.append(dbapi_error(INJECTED))
                raise raised[-1]
            do_execute(cursor, statement, parameters, context)

        monkeypatch.setattr(dialect, "do_execute", _failing_execute)
    return raised


@pytest.fixture(autouse=True)
def _dev_database_untouched() -> Iterator[None]:
    """不得经 ``app.core.database`` 的正式引擎（连本地开发库）发语句：记录并拦下（门禁全程只用权限世界的会话）。"""
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


# ═══ 一、记录器的正向对照 ═══════════════════════════════════════════════════


async def test_step_recorder_positive_control(world: AuthzWorld) -> None:
    """逐一执行各步的取数：对象投影按门禁的同一写法，其余直接调用门禁所用的生产取数函数。每次恰记到一条，归类与绑定的
    项目 / 用户正确；无关语句归为 other。下面各用例里「序列中没有某步」因此是「该步没有执行」，不是记录器看不见
    （路径依赖形态的放行用例另证明记录器也记得到经 HTTP 发出的语句）。"""
    user = await _arrange(world, EDIT)
    _forget_projects(world)
    db = world.db
    with StepRecorder(world) as recorder:
        await db.execute(select(DisclosureNote.project_id).where(DisclosureNote.id == TARGET_NOTE_ID))
        await deps._check_project_not_archived(db, TARGET_PROJECT_ID, user, "review")
        await deps._load_member_level(db, user.id, TARGET_PROJECT_ID)
        await eqcr_resolver._count_project_eqcr_assignments(db, user.id, TARGET_PROJECT_ID)
        await deps._resolve_project_role(db, user.id, TARGET_PROJECT_ID)
        await deps.check_consol_lock(project_id=TARGET_PROJECT_ID, db=db)
        await db.execute(select(User.id).where(User.id == user.id))
    assert recorder.records == [
        ("projection", (TARGET_NOTE_ID,)),
        ("archive", (TARGET_PROJECT_ID,)),
        ("member", (TARGET_PROJECT_ID, user.id)),
        ("eqcr", (TARGET_PROJECT_ID, user.id)),
        ("matrix", (TARGET_PROJECT_ID, user.id)),
        ("consol_lock", (TARGET_PROJECT_ID,)),
        ("other: SELECT users.id FROM users WHERE users.id = ?", (user.id,)),
    ]


# ═══ 二、判定顺序与结论（三种形态） ═════════════════════════════════════════


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
async def test_order_and_verdict(world: AuthzWorld, case: Case, form: str) -> None:
    """结论逐值等于期望（需求 6.2~6.7、6.12）；执行过的判定步骤按先后等于期望序列：归档 → 成员 → EQCR → 矩阵 → 合并锁，
    前一步拒绝即不再往下判，admin 跳过成员与矩阵但不豁免 EQCR，``consol_lock=False`` 不判合并锁；对象反查形态在最前恰多
    一条一列投影（门禁之前只有这一次读，需求 6.1、6.8）。"""
    user = await _arrange(world, case.who, archived=case.archived, locked=case.locked)
    run = await _run(world, form, user, consol_lock=case.consol_lock)
    expected_steps = [_STEP[code] for code in ("P" if form == "object" else "") + case.steps]
    assert run.steps == expected_steps
    # 生产门禁代码确实执行了（PEP 669 观测）；全局 eqcr 的 EQCR 判定不发语句，靠这里计它
    expected_runs = {IMPL: 1, PROJECT_PERMISSION: 1, EQCR_JUDGE: int(case.eqcr_judged)}
    expected_runs |= {"body": {}, "object": {FOR_OBJECT: 1}, "path": {CLOSURE: 1}}[form]
    assert {name: run.gate_runs[name] for name in expected_runs} == expected_runs
    _assert_outcome(run, form, case.verdict, user)


# ═══ 三、对象反查：404 与目标项目 ═══════════════════════════════════════════


@pytest.mark.parametrize("archived", [False, True], ids=["active", "archived"])
@pytest.mark.parametrize("who", [EDIT, NON_MEMBER, PROJECT_EQCR, ADMIN],
                         ids=["edit-member", "non-member", "project-eqcr", "admin"])
async def test_object_missing_is_404_after_the_only_projection(world: AuthzWorld, who: Who, archived: bool) -> None:
    """对象不存在 → 404「附注章节不存在」：只发出那一条一列投影，不进入判定实现；项目已归档也先 404（需求 6.7 末句、6.8）。"""
    user = await _arrange(world, who, archived=archived)
    run = await _run(world, "object", user, consol_lock=True, note_id=MISSING_NOTE_ID)
    assert run.records == [("projection", (MISSING_NOTE_ID,))]
    assert (run.gate_runs[FOR_OBJECT], run.gate_runs[IMPL]) == (1, 0)
    outcome = run.outcome
    assert isinstance(outcome, HTTPException), outcome
    assert (outcome.status_code, outcome.detail, note_edit_rejection_reason(outcome)) == (404, NOTE_NOT_FOUND, NOTE_NOT_FOUND)


async def test_object_form_target_is_the_objects_project(world: AuthzWorld) -> None:
    """需求 6.8：目标项目只取自对象。形态签名里没有项目参数，调用方另附的项目标识传不进门禁；身份④（目标项目无成员行、
    另一项目 (manager, edit)）对目标项目上的对象被拒，对其有权项目上的对象放行，各步查询绑定的都是对象所属项目。"""
    parameters = inspect.signature(note_edit_gate.assert_note_edit_access_for_object).parameters
    assert [(name, parameter.kind.name) for name, parameter in parameters.items()] == [
        ("db", "POSITIONAL_OR_KEYWORD"), ("current_user", "POSITIONAL_OR_KEYWORD"), ("id_column", "KEYWORD_ONLY"),
        ("project_column", "KEYWORD_ONLY"), ("object_id", "KEYWORD_ONLY"), ("not_found_detail", "KEYWORD_ONLY"),
        ("consol_lock", "KEYWORD_ONLY"),
    ]
    user = await _arrange(world, NON_MEMBER)
    await world.add_note(note_id=OTHER_NOTE_ID, project=await world.other_project())
    denied = await _run(world, "object", user, consol_lock=True)
    _assert_outcome(denied, "object", FORBIDDEN, user)
    assert denied.records == [
        ("projection", (TARGET_NOTE_ID,)), ("archive", (TARGET_PROJECT_ID,)), ("member", (TARGET_PROJECT_ID, user.id)),
    ]
    allowed = await _run(world, "object", user, consol_lock=True, note_id=OTHER_NOTE_ID)
    _assert_outcome(allowed, "object", ALLOW, user, project_id=OTHER_PROJECT_ID)
    assert allowed.records == [
        ("projection", (OTHER_NOTE_ID,)), ("archive", (OTHER_PROJECT_ID,)), ("member", (OTHER_PROJECT_ID, user.id)),
        ("eqcr", (OTHER_PROJECT_ID, user.id)), ("matrix", (OTHER_PROJECT_ID, user.id)), ("consol_lock", (OTHER_PROJECT_ID,)),
    ]
    assert world.rls_calls == [str(OTHER_PROJECT_ID)]  # 只在放行的那次、对对象所属项目设置


async def test_path_form_target_is_the_path_project(world: AuthzWorld) -> None:
    """路径依赖形态的目标项目是路径参数：身份④对目标项目得 403「权限不足」，对其有权的另一项目放行。"""
    user = await _arrange(world, NON_MEMBER)
    denied = await _run(world, "path", user, consol_lock=True)
    _assert_outcome(denied, "path", FORBIDDEN, user)
    assert denied.records == [("archive", (TARGET_PROJECT_ID,)), ("member", (TARGET_PROJECT_ID, user.id))]
    allowed = await _run(world, "path", user, consol_lock=True, project_id=OTHER_PROJECT_ID)
    _assert_outcome(allowed, "path", ALLOW, user, project_id=OTHER_PROJECT_ID)
    assert allowed.records == [
        ("archive", (OTHER_PROJECT_ID,)), ("member", (OTHER_PROJECT_ID, user.id)), ("eqcr", (OTHER_PROJECT_ID, user.id)),
        ("matrix", (OTHER_PROJECT_ID, user.id)), ("consol_lock", (OTHER_PROJECT_ID,)),
    ]
    assert world.rls_calls == [str(OTHER_PROJECT_ID)]


# ═══ 四、review 与 edit 同等处理；consol_lock 必须写明 ═════════════════════


async def test_review_and_edit_level_get_the_same_processing(world: AuthzWorld) -> None:
    """需求 6.2：同一用户其余条件相同时，成员行级别为 review 与为 edit 得到相同的业务处理与响应，操作人为调用者本人。"""
    identity = await world.member("review", "manager")
    world.replace_rls()
    user, row = identity.user, identity.member
    runs = []
    for level in ("review", "edit"):
        row.permission_level = PermissionLevel(level)
        await world.db.flush()
        assert await deps._load_member_level(world.db, user.id, TARGET_PROJECT_ID) == level
        runs.append(await _run(world, "path", user, consol_lock=True))
    for run in runs:
        _assert_outcome(run, "path", ALLOW, user)
        assert run.steps == ["archive", "member", "eqcr", "matrix", "consol_lock"]


@pytest.mark.parametrize("name", ["assert_note_edit_access", "require_note_edit_access", "assert_note_edit_access_for_object"])
def test_consol_lock_is_a_required_keyword(name: str) -> None:
    """三种形态的 ``consol_lock`` 都是无默认值的仅关键字参数：调用处必须写明是否判合并锁（需求 6.6；design D1）。"""
    parameter = inspect.signature(getattr(note_edit_gate, name)).parameters["consol_lock"]
    assert (parameter.kind, parameter.default) == (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.empty)


# ═══ 五、EQCR 判定出错：冒泡、不放行（需求 7.6、6.11） ═════════════════════


_FAULTS = [
    pytest.param("query-function", RuntimeError, id="query-function"),
    pytest.param("driver", sqlalchemy.exc.OperationalError, id="driver"),
]


@pytest.mark.parametrize(("kind", "expected_type"), _FAULTS)
@pytest.mark.parametrize("form", FORMS)
async def test_eqcr_query_failure_propagates(
    world: AuthzWorld, monkeypatch: pytest.MonkeyPatch, form: str, kind: str, expected_type: type[BaseException],
) -> None:
    """调用者是不出错时会放行的 edit 级成员：EQCR 判定的下层查询出错时，异常原样冒泡（不被当成「非 EQCR」放行），
    矩阵与合并锁两步不再执行；路径依赖形态的业务处理一次也不执行。"""
    user = await _arrange(world, EDIT)
    _forget_projects(world)
    raised = _inject_eqcr_failure(world, monkeypatch, kind)
    prefix = ["projection"] if form == "object" else []
    if form == "path":
        stub = world.stub(_NoteWrite, "save", returns=STUB_RESULT)
        async with world.client_for_app(_probe_app(), user=user) as client:
            with StepRecorder(world) as recorder:
                with pytest.raises(expected_type) as exc_info:
                    await client.put(_url(True))
        assert stub.count == 0
    else:
        with StepRecorder(world) as recorder, GateTrace() as trace:
            with pytest.raises(expected_type) as exc_info:
                await _call_direct(world, form, user, consol_lock=True)
        assert (trace.counts[IMPL], trace.counts[EQCR_JUDGE]) == (1, 1)
    origin = exc_info.value.orig if kind == "driver" else exc_info.value
    assert raised == [origin]  # 冒泡出来的就是注入的那个异常
    assert str(origin) == INJECTED
    # 驱动层故障时委派条数语句已发出（被记到后才失败）；函数层故障时该函数本身就是失败点，不发语句
    assert recorder.steps == [*prefix, "archive", "member", *(["eqcr"] if kind == "driver" else [])]


# ═══ 六、角色限定形态（任务 6.3；需求 8.3；design §4.6、§4.8 表 B） ═══════════

ROLE_GATE = "app.services.note_edit_gate.assert_note_role_access"
# design §4.8 表 B 的角色集合与声明文案（逐字）
PARTNER_MANAGER = frozenset({"partner", "manager"})
ADMIN_ONLY: frozenset[str] = frozenset()
SWITCH_TEMPLATE = "仅本项目经理或合伙人可切换附注模板类型"
FORCE_RELEASE = "仅本项目经理或合伙人可强制释放章节锁"
LOCK_DATA = "仅本项目经理或合伙人可锁定报表附注数据"
UNLOCK_DATA = "仅管理员可解除报表附注数据锁定"
ROLE = "角色不在集合内"  # 期望占位：403 NOTE_ROLE_REQUIRED，message 为该例声明的文案
_ROLE_STEP = {**_STEP, "R": "matrix"}  # R：角色判定自己的项目角色查询（与矩阵一步同一语句形态，排在判定实现之后）


@dataclass(frozen=True)
class RoleCase:
    name: str
    who: Who
    roles: frozenset[str]
    message: str  # 声明的拒绝文案（denied_message）
    verdict: Any  # ALLOW、Rejection 或 ROLE
    steps: str  # _ROLE_STEP 的代码按发生先后
    archived: bool = False
    locked: bool = False

    @property
    def expected(self) -> Any:
        if self.verdict is not ROLE:
            return self.verdict
        return Rejection(403, {"error_code": "NOTE_ROLE_REQUIRED", "message": self.message}, self.message)

    @property
    def eqcr_judged(self) -> bool:
        return self.verdict is not ARCHIVED and self.verdict is not FORBIDDEN


def _pm(name: str, who: Who, verdict: Any, steps: str, message: str = SWITCH_TEMPLATE, **flags: bool) -> RoleCase:
    return RoleCase(name, who, PARTNER_MANAGER, message, verdict, steps, **flags)


def _admin_only(name: str, who: Who, verdict: Any, steps: str, **flags: bool) -> RoleCase:
    return RoleCase(f"admin-only-{name}", who, ADMIN_ONLY, UNLOCK_DATA, verdict, steps, **flags)


ROLE_CASES: tuple[RoleCase, ...] = (
    # 经理 / 合伙人集合：判定实现放行后，成员行项目角色属于集合才放行；不判合并锁（合并锁定项目照样往下判）
    _pm("manager-edit-member", EDIT, ALLOW, "AMEXR"),
    _pm("partner-edit-member", Who(member=("partner", "edit")), ALLOW, "AMEXR", FORCE_RELEASE),
    _pm("partner-review-member-without-eqcr", Who(member=("partner", "review")), ALLOW, "AMEXR", LOCK_DATA),
    _pm("qc-global-manager-member", Who("qc", member=("manager", "edit")), ALLOW, "AMEXR"),
    _pm("manager-edit-member-locked-project", EDIT, ALLOW, "AMEXR", locked=True),
    _pm("qc-review-member", REVIEW, ROLE, "AMEXR"),
    _pm("auditor-edit-member", Who(member=("auditor", "edit")), ROLE, "AMEXR", FORCE_RELEASE),
    # EQCR 先被排除：项目角色 partner 属于集合，照样 403 EQCR 只读（③ 先于角色判定），admin 不豁免
    _pm("project-eqcr", PROJECT_EQCR, EQCR_READONLY, "AME"),
    _pm("project-eqcr-cn-alias", Who(member=("partner", "review"), eqcr_alias="独立复核合伙人"), EQCR_READONLY, "AME",
        LOCK_DATA),
    _pm("global-eqcr-partner-member", Who("eqcr", member=("partner", "review")), EQCR_READONLY, "AM"),
    _pm("admin-with-eqcr-assignment", Who("admin", eqcr_alias="eqcr"), EQCR_READONLY, "AE"),
    # readonly 成员先得「权限不足」：项目角色 manager 属于集合也一样（② 先于角色判定）
    _pm("readonly-level-manager-role", Who(member=("manager", "readonly")), FORBIDDEN, "AM"),
    _pm("readonly-member", READONLY, FORBIDDEN, "AM"),
    _pm("non-member", NON_MEMBER, FORBIDDEN, "AM", FORCE_RELEASE),
    _pm("deleted-manager-row-only", Who(member=("manager", "edit"), member_deleted=True), FORBIDDEN, "AM"),
    # 操作矩阵与归档同样先于角色判定
    _pm("qc-global-qc-role", QC_REVIEW, OPERATION_DENIED, "AMEX"),
    _pm("archived-manager-member", EDIT, ARCHIVED, "A", archived=True),
    _pm("archived-admin", ADMIN, ARCHIVED, "A", archived=True),
    # admin：不要求成员行，不判矩阵与项目角色
    _pm("admin-non-member", ADMIN, ALLOW, "AE"),
    _pm("admin-with-readonly-member-row", Who("admin", member=("readonly", "readonly")), ALLOW, "AE", LOCK_DATA),
    # 空集 = 仅 admin
    _admin_only("admin-non-member", ADMIN, ALLOW, "AE"),
    _admin_only("admin-locked-project", ADMIN, ALLOW, "AE", locked=True),
    _admin_only("manager-edit-member", EDIT, ROLE, "AMEXR"),
    _admin_only("global-partner-partner-member", Who("partner", member=("partner", "edit")), ROLE, "AMEXR"),
    _admin_only("project-eqcr", PROJECT_EQCR, EQCR_READONLY, "AME"),
    _admin_only("admin-with-eqcr-assignment", Who("admin", eqcr_alias="eqcr"), EQCR_READONLY, "AE"),
    _admin_only("readonly-member", READONLY, FORBIDDEN, "AM"),
    _admin_only("archived-admin", ADMIN, ARCHIVED, "A", archived=True),
)


@pytest.mark.parametrize("case", ROLE_CASES, ids=[case.name for case in ROLE_CASES])
async def test_role_access_order_and_verdict(world: AuthzWorld, case: RoleCase) -> None:
    """先过判定实现：归档、「权限不足」、EQCR 只读（admin 不豁免）、操作矩阵的拒绝都先于角色判定，且不判合并锁；admin 放行；
    否则成员行项目角色须属于集合，不属于 → 403 ``NOTE_ROLE_REQUIRED`` + 该例声明的文案（逐字）；空集仅 admin（需求 8.3）。"""
    user = await _arrange(world, case.who, archived=case.archived, locked=case.locked)
    _forget_projects(world)
    assert_gates_are_production()
    with StepRecorder(world) as recorder, GateTrace() as trace:
        try:
            outcome: Any = await note_edit_gate.assert_note_role_access(
                world.db, user, TARGET_PROJECT_ID, project_roles=case.roles, denied_message=case.message,
            )
        except HTTPException as exc:
            outcome = exc
    assert recorder.steps == [_ROLE_STEP[code] for code in case.steps]
    expected_runs = {ROLE_GATE: 1, IMPL: 1, PROJECT_PERMISSION: 1, EQCR_JUDGE: int(case.eqcr_judged)}
    assert {name: trace.counts[name] for name in expected_runs} == expected_runs
    expected = case.expected
    if expected is ALLOW:
        assert outcome is user  # 放行返回当前用户本人
        return
    assert isinstance(outcome, HTTPException), outcome
    assert (outcome.status_code, outcome.detail) == (expected.status, expected.detail)
    assert note_edit_rejection_reason(outcome) == expected.reason


def test_role_access_signature_matches_design() -> None:
    """design §4.6 的签名：角色集合与拒绝文案都是无默认值的仅关键字参数，调用处必须写明。"""
    parameters = inspect.signature(note_edit_gate.assert_note_role_access).parameters
    assert [(name, p.kind.name, p.default is inspect.Parameter.empty) for name, p in parameters.items()] == [
        ("db", "POSITIONAL_OR_KEYWORD", True), ("current_user", "POSITIONAL_OR_KEYWORD", True),
        ("project_id", "POSITIONAL_OR_KEYWORD", True), ("project_roles", "KEYWORD_ONLY", True),
        ("denied_message", "KEYWORD_ONLY", True),
    ]


_BAD_ROLE_DECLARATIONS = [
    pytest.param({"partner", "manager"}, SWITCH_TEMPLATE, TypeError, "project_roles 须为 frozenset，收到 set", id="set"),
    pytest.param("eqcr", SWITCH_TEMPLATE, TypeError, "project_roles 须为 frozenset，收到 str", id="str"),
    pytest.param(frozenset({"manger", "partner"}), SWITCH_TEMPLATE, ValueError, "未登记的项目角色 'manger'；", id="misspelt"),
    pytest.param(frozenset({"preparer"}), SWITCH_TEMPLATE, ValueError, "未登记的项目角色 'preparer'；", id="matrix-only-role"),
    pytest.param(PARTNER_MANAGER, "", ValueError, "denied_message 须为非空的中文拒绝原因，收到 ''", id="empty-message"),
    pytest.param(PARTNER_MANAGER, "  ", ValueError, "denied_message 须为非空的中文拒绝原因，收到 '  '", id="blank-message"),
]


@pytest.mark.parametrize(("roles", "message", "error", "fragment"), _BAD_ROLE_DECLARATIONS)
async def test_role_access_rejects_bad_declarations_before_any_query(
    world: AuthzWorld, roles: Any, message: Any, error: type[Exception], fragment: str,
) -> None:
    """声明 fail-closed（任务 6.3 新增，design 未写）：角色集合不是 frozenset、含成员行项目角色以外的取值，或拒绝文案为空，
    在任何读库与判定之前报错。调用者是声明正确时会放行的 (manager, edit) 成员。"""
    user = await _arrange(world, EDIT)
    _forget_projects(world)
    with StepRecorder(world) as recorder, GateTrace() as trace:
        with pytest.raises(error) as exc_info:
            await note_edit_gate.assert_note_role_access(
                world.db, user, TARGET_PROJECT_ID, project_roles=roles, denied_message=message,
            )
    assert fragment in str(exc_info.value)
    assert (recorder.records, trace.counts[ROLE_GATE], trace.counts[IMPL]) == ([], 1, 0)
