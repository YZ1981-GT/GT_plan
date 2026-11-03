"""Draft Refresh 真 PG 用例的共用世界（spec formula-hub-integrity-closure 任务 20 第一段 B；ADR-FHIC-08）。

``test_draft_refresh_truthful.py``（B-1a / B-1b）、``test_report_generate_callers_regression.py``（B-1b-2）与
``test_draft_refresh_router_status.py``（B-2）共用：

- :func:`draft_refresh_world`：按生产注册只挂 ``draft_refresh.router`` 的应用（``tests.authz_world.build_app``）+ TestClient；
  ``pg_tx_session``（独立连接 + 外层事务 + 保存点会话）建在 TestClient 的事件循环线程里（asyncpg 连接绑定事件循环），夹具写入、
  请求、前后对账共用同一外层事务；路由里的 commit / rollback 只作用于保存点，退出时一律回滚，快照库不留数据。只替换
  ``get_current_user`` / ``get_db``：身份是夹具里的合伙人 + 本项目 edit 成员行，门禁与业务链真实运行。
- 世界 = 【测试】项目（准则同医疗器械）+ 合伙人 + 本项目 edit 成员 + 医疗器械 2025 的试算表全部行与其余额表 / 科目映射 / 标准
  科目表（``INSERT … SELECT``，除 id / project_id 外原样）。precheck 只要求本项目年度的余额表、试算表有行（经
  ``get_active_filter``），复制来的余额表即满足；余额表与映射一并复制，是因为报表范围先跑 ``full_recalc``（company_code
  ``001``）：只有试算表时，复制来的 61 行（都是 001）没有余额表 / 映射支撑，未审 / 审定 / 期初被清零，报表全为 0。
- :class:`Recorder`：包装 ``event_bus.publish`` / ``publish_immediate``（记事件类型、项目、年度、``extra`` 与在时间线上的位置后
  照常调用原实现）、``TrialBalanceService.full_recalc`` / ``ReportEngine.generate_all_reports`` /
  ``DraftRefreshService.trigger_recalc``（记一笔后调用原实现）、``DraftRefreshOrchestrator.generate``（原实现返回后记下结果对象的
  outcome / status / failures 深拷贝 —— 路由把 failures 压成字符串，``stage`` 等字段只在这里看得到）、会话的 ``commit`` /
  ``rollback``（原实现返回后记一笔）；只记录、不替换，退出时逐个还原（实例上原先没有的属性删掉，不留下遮住类方法的实例属性）。
- 读数：本项目 ``financial_report`` / ``trial_balance`` / ``draft_refresh_audit`` / ``draft_marker`` 全行（``row_to_json``，逐字节
  比较用）、未删报表行状态、试算表行、审计行、Draft 标记、``prefill_stale`` 为真的底稿数。
- 夹具件（B-1b）：:func:`add_workpaper`（wp_index 一行 + prefill_stale=False 的底稿一张）、:func:`override_report_formula`（生产
  项目层适配 ``save_overrides`` 只改本项目的一行报表公式）。身份每次请求按 id 重新取（路由回滚会让会话里的对象全部过期，过期
  对象在异步上下文里读属性会报错）。
- B-1b-2（需求 3.5 两个调用方回归）：:func:`draft_refresh_world` 的 ``routers`` 可换挂别的生产路由（默认只挂 ``draft_refresh.router``），
  :meth:`World.post` 可指定端点；``call:`` 标记的 ``extra`` 记位置参数与关键字参数的摘要（标量原样、UUID 转字符串、其余记类型名），
  另记报表路由的三道门禁 —— ``require_operation`` 依赖里的 ``_resolve_project_role``、``check_consol_lock``、
  ``PrerequisiteChecker.check``（都只记录、调用原实现）；记录包装带 ``__wrapped__``（``inspect.unwrap`` 取回原实现）。
"""
from __future__ import annotations

import copy
import functools
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.deps as deps_module
import app.routers.draft_refresh as draft_refresh_router
import app.routers.reports as reports_router
import app.services.formula_management.draft_refresh_orchestrator as orchestrator_module
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectStatus, ProjectType, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.services.draft_refresh_service import DraftRefreshService
from app.services.event_bus import event_bus
from app.services.formula_management import refresh_report_scope
from app.services.formula_management.draft_refresh_orchestrator import DraftRefreshOrchestrator
from app.services.formula_settings.project_ops import save_overrides
from app.services.prerequisite_checker import PrerequisiteChecker
from app.services.report_engine import ReportEngine
from app.services.trial_balance_service import TrialBalanceService
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

ENDPOINT = "/api/workpapers/draft-refresh"
YEAR = 2025
MED_NAME = "重庆医药集团医疗器械有限公司_2025"
#: 复制的表：（表名, 是否按年度, 额外条件）；都按 project_id 取来源行
COPIED_TABLES: tuple[tuple[str, bool, str], ...] = (
    ("trial_balance", True, ""), ("tb_balance", True, ""),
    ("account_mapping", False, ""), ("account_chart", False, " AND source = 'standard'"))
EVENT_KINDS = ("publish", "publish_immediate")
#: 时间线上记编排器结果对象的那一笔（``extra`` = outcome / status / failures）
RESULT_KIND = "result:generate"
#: :func:`rows_json` 只认这几张表（表名不拼外部输入）
JSON_TABLES = ("financial_report", "trial_balance", "draft_refresh_audit", "draft_marker")
#: 调用前记一笔（``extra`` = 参数摘要）再调用原实现的（属主, 属性名, 时间线标记）：类上的方法、模块里的函数
CALL_SPIES: tuple[tuple[Any, str, str], ...] = (
    (TrialBalanceService, "full_recalc", "call:full_recalc"),
    (ReportEngine, "generate_all_reports", "call:generate_all_reports"),
    (DraftRefreshService, "trigger_recalc", "call:trigger_recalc"),
    (deps_module, "_resolve_project_role", "call:_resolve_project_role"),  # require_operation 依赖每次都调
    (reports_router, "check_consol_lock", "call:check_consol_lock"),  # 报表路由按模块全局名调用
    (PrerequisiteChecker, "check", "call:PrerequisiteChecker.check"),
)

Key = tuple[str, str]
Prepare = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]


@dataclass(frozen=True)
class Seeded:
    project_id: uuid.UUID
    user: User
    source_id: uuid.UUID
    copied: dict[str, int]


@dataclass(frozen=True)
class Mark:
    """时间线上的一笔：``request:start`` / ``request:end`` / ``commit`` / ``rollback`` / ``call:<函数名>``（``extra`` =
    ``{"args": [...], "kwargs": {...}}`` 参数摘要，见 :data:`CALL_SPIES`）/ ``publish`` / ``publish_immediate``（事件另带类型、
    项目、年度、``extra``）/ :data:`RESULT_KIND`（``extra`` = 编排器结果对象的 outcome / status / failures）；``at`` =
    ``time.perf_counter()``。"""

    kind: str
    event_type: str | None = None
    project_id: str | None = None
    year: int | None = None
    extra: dict[str, Any] | None = None
    at: float = field(default_factory=time.perf_counter)


@dataclass(frozen=True)
class ReportRow:
    amount: Decimal | None
    prior: Decimal | None
    formula_used: str | None
    is_stale: bool
    calc_version: int | None
    calc_error: str | None


@dataclass(frozen=True)
class AuditRow:
    id: uuid.UUID
    result_status: str
    idempotency_key: str | None
    affected_count: int
    detail: dict[str, Any]
    raw: str  # row_to_json 全文


@contextmanager
def _wrapped(owner: Any, name: str, make: Callable[[Any], Any]) -> Iterator[None]:
    """把 ``owner.name`` 换成 ``make(当前生效的实现)``；退出时原样还原（``owner`` 自身原先没有该属性则删掉）。"""
    own = vars(owner)
    had, previous = name in own, own.get(name)
    setattr(owner, name, make(getattr(owner, name)))
    try:
        yield
    finally:
        if had:
            setattr(owner, name, previous)
        else:
            delattr(owner, name)


class Recorder:
    """一条时间线：事件投递、执行函数与过时刷新的调用、编排器结果、会话 commit / rollback（只记录，原实现照常执行）。"""

    def __init__(self) -> None:
        self.timeline: list[Mark] = []

    def since(self, start: int) -> list[Mark]:
        return self.timeline[start:]

    @contextmanager
    def installed(self, session: AsyncSession) -> Iterator[Recorder]:
        """事件两个方法包在单例实例上（别处留下的实例属性也照样被包住、退出时原样放回），:data:`CALL_SPIES` 包在类 / 模块上，
        编排器包在类上。"""
        with ExitStack() as stack:
            for name in EVENT_KINDS:
                stack.enter_context(_wrapped(event_bus, name, self._event_spy(name)))
            for owner, name, kind in CALL_SPIES:
                stack.enter_context(_wrapped(owner, name, self._marked(kind, before=True)))
            stack.enter_context(_wrapped(DraftRefreshOrchestrator, "generate", self._result_spy))
            for name in ("commit", "rollback"):
                stack.enter_context(_wrapped(session, name, self._marked(name, before=False)))
            yield self

    def _result_spy(self, original):
        """编排器 ``generate`` 返回后记下结果对象的 outcome / status / failures（深拷贝），原样返回。"""
        async def generate(*args, **kwargs):
            result, application = await original(*args, **kwargs)
            self.timeline.append(Mark(RESULT_KIND, extra={
                "outcome": getattr(result, "outcome", None), "status": getattr(result, "status", None),
                "failures": copy.deepcopy(list(getattr(result, "failures", None) or []))}))
            return result, application
        return generate

    def _event_spy(self, kind: str) -> Callable[[Any], Any]:
        def make(original):
            async def spy(payload):
                self.timeline.append(Mark(kind, payload.event_type.value, str(payload.project_id), payload.year,
                                          copy.deepcopy(dict(payload.extra or {}))))
                return await original(payload)
            return spy
        return make

    def _marked(self, kind: str, *, before: bool) -> Callable[[Any], Any]:
        """``before`` 为真在调用原实现之前记一笔（执行函数，``extra`` = 参数摘要），否则在原实现返回之后记（commit / rollback）。"""
        def make(original):
            @functools.wraps(original)
            async def marked(*args, **kwargs):
                if before:
                    self.timeline.append(Mark(kind, extra={"args": [_brief(value) for value in args],
                                                           "kwargs": {k: _brief(v) for k, v in kwargs.items()}}))
                result = await original(*args, **kwargs)
                if not before:
                    self.timeline.append(Mark(kind))
                return result
            return marked
        return make


def _brief(value: Any) -> Any:
    """参数摘要：``None`` 与标量原样、UUID 转字符串，其余记类型名（不持有引用）。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value) if isinstance(value, uuid.UUID) else type(value).__name__


@dataclass
class World:
    client: TestClient
    session: AsyncSession
    api: FastAPI
    seeded: Seeded
    recorder: Recorder = field(default_factory=Recorder)

    @property
    def project_id(self) -> uuid.UUID:
        return self.seeded.project_id

    def run(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """在 TestClient 的事件循环线程里跑 ``fn(session, *args)``（与请求同一连接、同一外层事务）。"""
        return self.client.portal.call(fn, self.session, *args)

    def body(self, scopes: list[str], **extra: Any) -> dict[str, Any]:
        return {"project_id": str(self.project_id), "year": YEAR, "scopes": list(scopes), **extra}

    def post(self, body: dict[str, Any], endpoint: str = ENDPOINT) -> tuple[Any, list[Mark]]:
        """真发一次请求（默认 Draft Refresh 端点），返回（响应, 本次请求的时间线：首尾是 ``request:start`` / ``request:end``）。"""
        start = len(self.recorder.timeline)
        self.recorder.timeline.append(Mark("request:start"))
        response = self.client.post(endpoint, json=body)
        self.recorder.timeline.append(Mark("request:end"))
        return response, self.recorder.since(start)


async def copy_rows(session: AsyncSession, table: str, source_id: uuid.UUID, target_id: uuid.UUID, *,
                    by_year: bool, extra: str = "") -> int:
    """按 information_schema 列清单 ``INSERT … SELECT`` 复制来源项目的行（id 新生成、project_id 换成目标，其余原样）。"""
    columns = (await session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table "
        "AND column_name NOT IN ('id', 'project_id') ORDER BY ordinal_position"), {"table": table})).scalars().all()
    quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
    where = "project_id = :src" + (" AND year = :year" if by_year else "") + extra
    params: dict[str, Any] = {"dst": target_id, "src": source_id, **({"year": YEAR} if by_year else {})}
    result = await session.execute(text(
        f"INSERT INTO {table} (id, project_id, {quoted}) SELECT gen_random_uuid(), :dst, {quoted} "
        f"FROM {table} WHERE {where}"), params)
    return int(result.rowcount)


async def seed_world(session: AsyncSession, purpose: str, prepare: Prepare | None = None) -> Seeded:
    """【测试】项目（名称 ``【测试】fh_t20_<用途>_<10 位十六进制>``）+ 合伙人 + edit 成员 + 复制的四张表；``prepare`` 在提交前改夹具。"""
    located = (await session.execute(text(
        "SELECT id, template_type, report_scope FROM projects "
        "WHERE name = :name AND is_deleted = false AND audit_year = :year"), {"name": MED_NAME, "year": YEAR})).all()
    if len(located) != 1:
        raise AssertionError(f"快照库里按名称定位 {MED_NAME}（未删、{YEAR} 年度）应恰 1 个，实际 {located}")
    source_id, template_type, report_scope = located[0]
    tag = uuid.uuid4().hex[:10]
    user = User(username=f"fh_t20_{purpose}_{tag}", email=f"fh_t20_{purpose}_{tag}@example.test",
                hashed_password="x", role=UserRole.partner)
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_t20_{purpose}_{tag}",
                      client_name=f"{TEST_PROJECT_PREFIX}Draft Refresh 如实报告", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, template_type=template_type, report_scope=report_scope,
                      audit_year=YEAR)
    session.add_all([user, project])
    await session.flush()
    session.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.partner,
                            permission_level=PermissionLevel.edit))
    copied = {table: await copy_rows(session, table, source_id, project.id, by_year=by_year, extra=extra)
              for table, by_year, extra in COPIED_TABLES}
    if not all(copied.values()):
        raise AssertionError(f"夹具空转：来源项目有表没有行可复制 {copied}")
    if prepare is not None:
        await prepare(session, project.id)
    await session.commit()  # pg_tx：只释放保存点，夹具留在外层事务里，请求里的回滚碰不到它
    return Seeded(project.id, user, source_id, copied)


def authenticate(api: FastAPI, session: AsyncSession, user: User) -> None:
    """只替换 ``get_db`` / ``get_current_user``。身份按 id 现取：未过期时 ``session.get`` 直接返回同一对象（不发 SQL）；路由
    回滚后会话里的对象全部过期，在这里重新载入，否则下一次请求读 ``role`` 会在异步上下文里触发隐式 IO。"""
    user_id = user.id

    async def _db():
        yield session

    async def _user():
        return await session.get(User, user_id)

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)


@contextmanager
def draft_refresh_world(purpose: str, prepare: Prepare | None = None,
                        routers: Sequence[APIRouter] = ()) -> Iterator[World]:
    """``routers`` 为空 ⇒ 只挂 ``draft_refresh.router``；需求 3.5 的报表路由回归传 ``(reports.router,)``（同样按生产注册挂）。"""
    api = build_app(*(routers or (draft_refresh_router.router,)))
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            seeded = client.portal.call(seed_world, session, purpose, prepare)
            authenticate(api, session, seeded.user)
            world = World(client, session, api, seeded)
            with world.recorder.installed(session):
                yield world


def assert_production_path() -> None:
    """路由走生产编排器、生产报表范围执行与生产事件总线单例（包装的是真对象，不是替身）。"""
    assert draft_refresh_router.DraftRefreshOrchestrator is DraftRefreshOrchestrator
    assert draft_refresh_router.event_bus is event_bus
    assert orchestrator_module.execute_report_scope is refresh_report_scope.execute_report_scope


async def rows_json(session: AsyncSession, project_id: uuid.UUID, table: str) -> list[tuple[str, str]]:
    """本项目 ``table``（:data:`JSON_TABLES` 之一）全行（不分年度 / 删除标记）的（id, ``row_to_json``），按 id 排序。"""
    if table not in JSON_TABLES:
        raise ValueError(f"rows_json 不认表 {table!r}（只认 {JSON_TABLES}）")
    rows = (await session.execute(text(
        f"SELECT t.id::text, row_to_json(t)::text FROM {table} t WHERE t.project_id = :pid ORDER BY t.id"),
        {"pid": project_id})).all()
    return [(str(row[0]), str(row[1])) for row in rows]


async def report_rows_json(session: AsyncSession, project_id: uuid.UUID) -> list[tuple[str, str]]:
    """本项目 ``financial_report`` 全行（不分年度 / 删除标记）的（id, ``row_to_json``），按 id 排序。"""
    return await rows_json(session, project_id, "financial_report")


async def report_states(session: AsyncSession, project_id: uuid.UUID, year: int = YEAR) -> dict[Key, ReportRow]:
    """本项目年度未删报表行：（报表类型, 行次）→ 金额 / 上期 / 生成时公式 / 过期 / 计算版本 / 错误。"""
    rows = (await session.execute(text(
        "SELECT report_type::text, row_code, current_period_amount, prior_period_amount, formula_used, is_stale, "
        "calc_version, calc_error FROM financial_report WHERE project_id = :pid AND year = :year AND is_deleted = false"),
        {"pid": project_id, "year": year})).all()
    return {(str(row[0]), str(row[1])): ReportRow(*row[2:]) for row in rows}


async def trial_balance_rows(session: AsyncSession, project_id: uuid.UUID, year: int = YEAR) -> list[tuple[str, ...]]:
    """本项目年度试算表全部行（含已删）的（科目码, 公司, 未审, 调整三列, 审定, 期初, 删除标记）文本，排序后返回。"""
    rows = (await session.execute(text(
        "SELECT standard_account_code, company_code, unadjusted_amount, rje_adjustment, aje_adjustment, wp_adjustment, "
        "audited_amount, opening_balance, is_deleted FROM trial_balance WHERE project_id = :pid AND year = :year"),
        {"pid": project_id, "year": year})).all()
    return sorted(tuple(str(value) for value in row) for row in rows)


async def audit_rows(session: AsyncSession, project_id: uuid.UUID) -> list[AuditRow]:
    """本项目全部 ``draft_refresh_audit`` 行（按 id 排序；同一外层事务里 ``operated_at`` 可能相同，不拿它判先后）。"""
    rows = (await session.execute(text(
        "SELECT t.id, t.result_status, t.idempotency_key, t.affected_count, t.detail::text, row_to_json(t)::text "
        "FROM draft_refresh_audit t WHERE t.project_id = :pid ORDER BY t.id"), {"pid": project_id})).all()
    return [AuditRow(row[0], row[1], row[2], int(row[3]), json.loads(row[4]), str(row[5])) for row in rows]


async def draft_markers(session: AsyncSession, project_id: uuid.UUID) -> list[tuple[str, str, str | None]]:
    """本项目全部 Draft 标记的（单元, 状态, 所属刷新 id），按单元排序。"""
    rows = (await session.execute(text(
        "SELECT unit_scope, state, refresh_id::text FROM draft_marker WHERE project_id = :pid ORDER BY unit_scope, id"),
        {"pid": project_id})).all()
    return [(str(row[0]), str(row[1]), row[2]) for row in rows]


async def prefill_stale_count(session: AsyncSession, project_id: uuid.UUID) -> int:
    """本项目 ``working_paper.prefill_stale`` 为真的行数（不分删除标记）。"""
    return int((await session.execute(text(
        "SELECT count(*) FROM working_paper WHERE project_id = :pid AND prefill_stale"), {"pid": project_id})).scalar_one())


async def add_workpaper(session: AsyncSession, project_id: uuid.UUID, wp_code: str) -> uuid.UUID:
    """wp_index 一行（``wp_code``）+ 底稿一张：``prefill_stale=False``、带 ``prefill_tb_snapshot`` ⇒ 属于 ``prefill_engine.mark_stale``
    会标过时的「持有已落库派生值」底稿（没有快照 / 派生值的底稿 mark_stale 不碰，判据会空转）。返回底稿 id。"""
    wp_index_id = (await session.execute(text(
        "INSERT INTO wp_index (id, project_id, wp_code, wp_name) VALUES (gen_random_uuid(), :pid, :code, :name) "
        "RETURNING id"), {"pid": project_id, "code": wp_code, "name": f"{TEST_PROJECT_PREFIX}fh_t20 底稿 {wp_code}"}
    )).scalar_one()
    return (await session.execute(text(
        "INSERT INTO working_paper (id, project_id, wp_index_id, file_path, source_type, prefill_stale, "
        "prefill_tb_snapshot) VALUES (gen_random_uuid(), :pid, :wid, :path, 'template', false, CAST(:snap AS jsonb)) "
        "RETURNING id"), {"pid": project_id, "wid": wp_index_id, "path": f"fh_t20/{wp_code}.xlsx",
                          "snap": json.dumps({"1002": "1.00"})})).scalar_one()


async def override_report_formula(session: AsyncSession, project_id: uuid.UUID, report_type: str, row_code: str,
                                  formula: str, label: str) -> dict[str, Any]:
    """经生产项目层适配 ``save_overrides``（domain=report）把本项目的一行报表公式换成 ``formula``：只写 ``project:<项目>``
    行、不动准则行；保存期不校验公式（悬空引用在报表计算时才失败）。返回 ``save_overrides`` 的结果。"""
    return await save_overrides(session, domain="report", project_id=project_id, user_id=None, items=[
        {"slot_key": f"{report_type}:{row_code}", "label": label, "definition": {"formula": formula}}])
