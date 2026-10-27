"""端点级测试夹具「权限世界」（partner-manager-edit-permission design §8.2、D11；需求 12.1、12.2、12.4）。

夹具模块，不是测试文件（文件名不匹配 ``test_*.py``，不被收集）。测试文件里这样用：

    @pytest_asyncio.fixture
    async def world(monkeypatch):
        async with sqlite_world(monkeypatch) as w:
            yield w

一、数据
- SQLite 内存库（``StaticPool``，同一条连接）只建六张表：users / projects / project_users / staff_members /
  project_assignments / disclosure_notes。外键只保留指向这六张表的。模型里用 ``postgresql_where`` 声明的部分索引，
  在 SQLite 上按同样的列与条件重建为部分索引（``create_all`` 在 SQLite 上建出的唯一索引不带删除条件，会误拒 PG 上合法的
  「一条已删除行 + 一条现行行」）。
- 端点要读的业务表经可选参数 ``extra_tables`` 补建（``sqlite_world(monkeypatch, extra_tables=(...))``，PG 版同名参数）：
  建在六张表之后、按外键依赖排序，外键只保留指向本次所建表的，PG 上所需枚举类型同样在临时 schema 内新建。缺省不补建
  （仍只有六张表）。缺表即该用例失败，不降级跳过。
- PG 同构版 ``pg_world``（供 ``pg_only`` 用例）：同一事务内建临时 schema，``SET LOCAL search_path`` 只含该 schema，用同一份
  建表函数建同样的六张表（枚举类型按 ORM 声明的取值在临时 schema 内新建）。会话以 SAVEPOINT 方式加入该事务，端点里的
  ``commit`` 只释放保存点；结束时整体回滚，不留任何对象。连接串只取进程环境变量 ``DATABASE_URL``。
- 目标项目（固定 id ``TARGET_PROJECT_ID``）在建世界时建好：未归档、未合并锁定、未删除。id 固定，五种身份各在独立的世界里
  也能对同一路径发同一请求（需求 12.2）。

二、身份（需求 12.2 ①~⑤、12.4 ⑥~⑧）
- 工厂：``member(level, role)``、``eqcr_assignment(alias, user=...)``、``non_member_with_other_project()``。
- 八种身份各一个方法，方法名即 ``IDENTITY_LABELS`` 的键，``identity(key)`` 按键分派。⑦⑧ 之外全局角色都是 auditor；
  只有 ⑤ 持有 EQCR 别名委派；Redis 替身里不预置任何键。

三、可替换点（且只有这些，需求 12.1）
- 当前用户：``client(..., user=...)`` override ``get_current_user``，返回世界里的真实 ``User`` 行；``user=None`` 为未登录。
  数据库会话 ``get_db`` 同时 override 为世界的会话（只提供数据，不是判定）。
- Redis 客户端（不是判定）：建世界时把 ``app.core.redis`` 的两个客户端名（``redis_client`` 与 ``get_redis`` 所用的 ``_redis_client``）
  换成独立 FakeServer 的 fakeredis，``decode_responses=True`` 与生产客户端的取值形态相同；初始为空。权限缓存已由任务 3.4 移除
  （design D3），级别判定点不读写 Redis，这里只让测试进程不连真实 Redis。现状：测试进程里 ``redis_client`` 是导入时按 ``settings.REDIS_URL`` 建的
  ``redis.asyncio.Redis``（连真实本机 Redis），``_redis_client`` 在首次 ``get_redis()`` 时同样建出；``tests/conftest.py`` 没有替换。
- RLS 上下文：``replace_rls()``（``client`` 默认调用）把 ``app.deps.set_rls_context`` 与 ``app.core.database.set_rls_context``
  换成只记录项目 id 的空操作（门禁经 ``app.deps`` 的模块全局名调用；生产函数在 SQLite 上本来就按方言跳过）。
- 归档守卫 ``replace_archive_guard()``、委派查询 ``replace_eqcr_query(count)``：只用于不观测归档 / EQCR 的用例。每次替换都记入
  ``replaced``，观测该判定的用例用 ``assert_not_replaced`` 自证没有替换。
- 端点的业务 service：``stub(owner, attr, returns)`` 打桩并计数；对门禁、门禁所在模块与上面几个可替换点一律拒绝打桩。
- 不提供、也不允许以 ``dependency_overrides`` 或 monkeypatch 替换 ``PRODUCTION_GATES`` 所列门禁；新增门禁形态（如附注编辑门禁）
  时在 ``PRODUCTION_GATES`` 与 ``_GUARDED_MODULES`` 登记。

四、「请求经过的门禁 is 生产对象」自检的口径
1. 导入本模块时给 ``PRODUCTION_GATES`` 取快照，并核对每个快照是定义在该模块源文件里的同名函数、源文件在被测 ``app`` 包内
   （导入前就被换掉的情形在这里暴露）。
2. ``assert_gates_are_production()``：各模块属性仍 ``is`` 快照（导入后被 monkeypatch 换掉即失败）。
3. ``assert_world_overrides(app)``：``dependency_overrides`` 只含 ``get_current_user`` 与 ``get_db``。
4. 每个请求都在 ``GateTrace`` 内发出：用 ``sys.monitoring``（PEP 669）观测快照函数与工厂内 ``dependency`` 闭包的代码对象开始执行
   的次数，不替换、不包装任何对象；``GateClient.assert_passed`` 断言生产门禁的代码确实执行过（及次数）。
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from types import CodeType, FunctionType, ModuleType
from typing import Any

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.schema import (
    AddConstraint, CreateIndex, CreateTable, ForeignKeyConstraint, Index, Table, sort_tables,
)

import app
import app.core.database as core_database
import app.core.redis as core_redis
import app.deps as deps
import app.services.eqcr_resolver as eqcr_resolver
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.models.staff_models import ProjectAssignment, StaffMember

# ─── 常量 ────────────────────────────────────────────────────────────────────

TARGET_PROJECT_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e01")  # 目标项目（请求发往的项目）
OTHER_PROJECT_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e02")  # 身份④有权的另一项目
TARGET_NOTE_ID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e03")  # 目标项目上的附注（对象 id 端点用）

# 按外键依赖先后排列：建表时依次建，被引用的表在前
WORLD_TABLES: tuple[Table, ...] = (
    User.__table__, Project.__table__, ProjectUser.__table__,
    StaffMember.__table__, ProjectAssignment.__table__, DisclosureNote.__table__,
)
WORLD_TABLE_NAMES: frozenset[str] = frozenset(table.name for table in WORLD_TABLES)

# 需求 12.2 五种标准身份与 12.4 三种补充情形；键即 AuthzWorld 上的方法名
IDENTITY_LABELS: dict[str, str] = {
    "edit_member": "① edit 级成员（manager, edit）",
    "review_member": "② review 级非 EQCR 成员（qc, review）",
    "readonly_member": "③ readonly 成员（readonly, readonly）",
    "non_member": "④ 非成员（另一项目上 manager, edit）",
    "project_eqcr": "⑤ 本项目 EQCR（partner, review + eqcr 现行委派）",
    "archived_edit_member": "⑥ 已归档项目上的 edit 级成员（manager, edit）",
    "qc_review_member": "⑦ 全局角色与项目角色均为 qc 的 review 级成员",
    "admin_non_member": "⑧ 全局 admin、不是本项目成员",
}
STANDARD_IDENTITIES: tuple[str, ...] = (
    "edit_member", "review_member", "readonly_member", "non_member", "project_eqcr",
)
SUPPLEMENTARY_IDENTITIES: tuple[str, ...] = ("archived_edit_member", "qc_review_member", "admin_non_member")

# 不可替换的生产门禁（需求 12.1 第三项）。新增门禁形态时在此登记，并把它所在的模块加进 _GUARDED_MODULES。
PRODUCTION_GATES: tuple[str, ...] = (
    "app.deps.require_project_access",
    "app.deps.assert_project_permission",
    "app.services.eqcr_resolver.is_project_eqcr",
    "app.routers.deliverable._guard_action",
    # 附注编辑门禁（任务 6.1）：判定实现与路径依赖 / 对象反查两种挂载形态
    "app.services.note_edit_gate.assert_note_edit_access",
    "app.services.note_edit_gate.require_note_edit_access",
    "app.services.note_edit_gate.assert_note_edit_access_for_object",
    # 附注编辑门禁的 design 定级形态（任务 6.3）：多项目与角色限定
    "app.services.note_edit_gate.assert_note_edit_access_on_projects",
    "app.services.note_edit_gate.assert_note_role_access",
    # 高级构建器准入（advanced-query-linkage-closure 任务 12）：路由门禁与 access 接口共用的判定
    "app.routers.query_builder.require_query_builder_access",
    "app.services.custom_query.builder_access.builder_admission",
    "app.services.custom_query.builder_access.resolve_builder_access",
)
# 门禁、判定（成员级别 / 归档 / 操作矩阵 / 合并锁 / EQCR）与基础设施所在的模块：其中的对象一律不能当业务 service 打桩
_GUARDED_MODULES: frozenset[str] = frozenset({
    "app.deps", "app.services.eqcr_resolver", "app.services.note_edit_gate", "app.core.database", "app.core.redis",
    "app.services.custom_query.builder_access",
})
REPLACEABLE_POINTS: frozenset[str] = frozenset({"rls", "archive_guard", "eqcr_query"})
_REPLACEABLE_NAMES: frozenset[str] = frozenset(
    {"set_rls_context", "_check_project_not_archived", "_count_project_eqcr_assignments", "get_current_user", "get_db"}
)
_APP_DIR = Path(app.__file__).resolve().parent


# ─── 建表（SQLite 与 PG 同一份逻辑） ─────────────────────────────────────────


def _referred_table(fk: ForeignKeyConstraint) -> str:
    """外键指向的表名（只读声明串，不要求被指向的表已注册）。"""
    (target,) = {element.target_fullname.rsplit(".", 1)[0].rsplit(".", 1)[-1] for element in fk.elements}
    return target


def _enum_types(tables: Iterable[Table] = WORLD_TABLES) -> dict[str, tuple[str, ...]]:
    """所建表用到的原生枚举类型：类型名 → ORM 声明的取值（PG 上在临时 schema 内新建）。

    非原生枚举（``native_enum=False``）在 PG 上建成 VARCHAR，不需要类型；六张表的枚举都是原生且有名字的。
    """
    found: dict[str, tuple[str, ...]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, SAEnum) and column.type.native_enum and column.type.name:
                labels = tuple(column.type.enums)
                if found.setdefault(column.type.name, labels) != labels:
                    raise RuntimeError(f"枚举类型 {column.type.name} 在不同列上声明的取值不同")
    return found


def world_tables(extra_tables: Iterable[Table] = ()) -> tuple[Table, ...]:
    """本次要建的表：六张表在前（原顺序），``extra_tables`` 去掉重复与六张表后按外键依赖排序追加。"""
    extras = {table.name: table for table in extra_tables if table.name not in WORLD_TABLE_NAMES}
    return (*WORLD_TABLES, *sort_tables(extras.values()))


def _index_statement(index: Index, dialect: str) -> CreateIndex | str:
    """PG 原样建；SQLite 上把 ``postgresql_where`` 部分索引按同样的列与条件重建为部分索引。"""
    where = index.dialect_options["postgresql"]["where"]
    if dialect != "sqlite" or where is None:
        return CreateIndex(index)
    if len(index.expressions) != len(index.columns):
        raise RuntimeError(f"{index.name} 含表达式列，SQLite 部分索引重建只支持普通列")
    columns = ", ".join(column.name for column in index.columns)
    unique = "UNIQUE " if index.unique else ""
    return f"CREATE {unique}INDEX {index.name} ON {index.table.name} ({columns}) WHERE {where}"


def create_world_schema(conn: Connection, extra_tables: Iterable[Table] = ()) -> None:
    """在 ``conn`` 上建权限世界的六张表及 ``extra_tables``（供 ``AsyncConnection.run_sync`` 调用）。

    PG 建表时就校验外键目标：六张表里指向补建表的外键（如 disclosure_notes → working_paper）在全部表建完后再
    ``ALTER TABLE … ADD`` 补上；SQLite 建表时不校验外键目标，照旧内联。缺省（不补建）时 DDL 与原先逐句相同。
    """
    tables = world_tables(extra_tables)
    names = frozenset(table.name for table in tables)
    dialect = conn.dialect.name
    if dialect == "postgresql":
        for name, labels in sorted(_enum_types(tables).items()):
            postgresql.ENUM(*labels, name=name).create(conn, checkfirst=False)
    created: set[str] = set()
    deferred: list[ForeignKeyConstraint] = []
    for table in tables:
        in_world = [fk for fk in table.foreign_key_constraints if _referred_table(fk) in names]
        inline = in_world
        if dialect == "postgresql":
            ready = created | {table.name}
            inline = [fk for fk in in_world if _referred_table(fk) in ready]
            deferred.extend(fk for fk in in_world if _referred_table(fk) not in ready)
        conn.execute(CreateTable(table, include_foreign_key_constraints=inline))
        created.add(table.name)
        for index in sorted(table.indexes, key=lambda item: item.name):
            statement = _index_statement(index, dialect)
            if isinstance(statement, str):
                conn.exec_driver_sql(statement)
            else:
                conn.execute(statement)
    for fk in deferred:
        conn.execute(AddConstraint(fk))


# ─── 「请求经过的门禁 is 生产对象」 ──────────────────────────────────────────


def _split(dotted: str) -> tuple[ModuleType, str]:
    module_name, _, attr = dotted.rpartition(".")
    return importlib.import_module(module_name), attr


def _production_problem(dotted: str, module: ModuleType, attr: str, fn: Any) -> str | None:
    """快照不是「定义在该模块源文件里、被测 app 包内的同名函数」时给出原因。"""
    if not isinstance(fn, FunctionType):
        return f"{dotted} 不是函数（{type(fn).__name__}）"
    if (fn.__module__, fn.__qualname__) != (module.__name__, attr):
        return f"{dotted} 实为 {fn.__module__}.{fn.__qualname__}"
    source = Path(fn.__code__.co_filename).resolve()
    if source != Path(module.__file__).resolve() or not source.is_relative_to(_APP_DIR):
        return f"{dotted} 的源文件 {source} 不是被测 app 包（{_APP_DIR}）内的 {module.__name__}"
    return None


def _snapshot_gates() -> dict[str, FunctionType]:
    snapshot: dict[str, FunctionType] = {}
    problems: list[str] = []
    for dotted in PRODUCTION_GATES:
        module, attr = _split(dotted)
        fn = getattr(module, attr)
        problem = _production_problem(dotted, module, attr, fn)
        if problem is None:
            snapshot[dotted] = fn
        else:
            problems.append(problem)
    if problems:
        raise RuntimeError("导入权限世界时门禁已不是生产对象：" + "；".join(problems))
    return snapshot


PRODUCTION_GATE_OBJECTS: dict[str, FunctionType] = _snapshot_gates()


def _gate_codes() -> dict[CodeType, str]:
    """要观测的代码对象 → 名称：门禁函数本体，及依赖工厂内的 ``dependency`` 闭包（每次请求真正执行的是它）。"""
    codes: dict[CodeType, str] = {}
    for dotted, fn in PRODUCTION_GATE_OBJECTS.items():
        codes[fn.__code__] = dotted
        for const in fn.__code__.co_consts:
            if isinstance(const, CodeType) and const.co_name == "dependency":
                codes[const] = f"{dotted}.<locals>.dependency"
    return codes


GATE_CODES: dict[CodeType, str] = _gate_codes()
TRACED_GATES: tuple[str, ...] = tuple(sorted(GATE_CODES.values()))


def assert_gates_are_production(lookup: Callable[[ModuleType, str], Any] = getattr) -> None:
    """各门禁的模块属性仍是导入时快照的生产函数（``lookup`` 只供自测注入，默认按模块属性取）。"""
    problems = []
    for dotted, original in PRODUCTION_GATE_OBJECTS.items():
        module, attr = _split(dotted)
        current = lookup(module, attr)
        if current is not original:
            problems.append(f"{dotted} 已被替换为 {current!r}")
    if problems:
        raise AssertionError("请求经过的门禁不是生产对象（需求 12.1）：" + "；".join(problems))


def _is_gate_callable(obj: Any) -> bool:
    """门禁函数本身，或由门禁工厂产出的闭包（按身份与代码对象比，不要求可哈希）。"""
    return any(obj is fn for fn in PRODUCTION_GATE_OBJECTS.values()) or getattr(obj, "__code__", None) in GATE_CODES


def assert_world_overrides(api: FastAPI) -> None:
    """``dependency_overrides`` 只允许当前用户与数据库会话；替换门禁的 override 会静默失效，替换判定则测不到判定。"""
    extra = [key for key in api.dependency_overrides if key is not get_current_user and key is not get_db]
    if extra:
        labels = sorted(
            f"{getattr(key, '__module__', '?')}.{getattr(key, '__qualname__', key)!s}"
            + ("（门禁）" if _is_gate_callable(key) else "")
            for key in extra
        )
        raise AssertionError("dependency_overrides 只允许 get_current_user 与 get_db（需求 12.1），多出：" + "、".join(labels))


_PREFERRED_TOOL_IDS = (4, 3, 2)  # sys.monitoring 工具号：0 / 1 / 5 留给调试器、覆盖率、优化器


class GateTrace:
    """观测一段代码执行期间各生产门禁代码对象开始执行的次数（PEP 669，只观测、不替换）。"""

    def __init__(self) -> None:
        self.counts: dict[str, int] = dict.fromkeys(TRACED_GATES, 0)
        self._tool: int | None = None

    def _on_start(self, code: CodeType, _offset: int) -> None:
        name = GATE_CODES.get(code)
        if name is not None:
            self.counts[name] += 1

    def __enter__(self) -> GateTrace:
        mon = sys.monitoring
        free = [tool for tool in _PREFERRED_TOOL_IDS if mon.get_tool(tool) is None]
        if not free:
            raise RuntimeError(f"sys.monitoring 工具号 {_PREFERRED_TOOL_IDS} 都被占用，无法观测请求经过的门禁")
        self._tool = free[0]
        mon.use_tool_id(self._tool, "authz_world.gate_trace")
        try:
            mon.register_callback(self._tool, mon.events.PY_START, self._on_start)
            for code in GATE_CODES:
                mon.set_local_events(self._tool, code, mon.events.PY_START)
        except BaseException:
            self._release()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        self._release()

    def _release(self) -> None:
        mon = sys.monitoring
        if self._tool is None:
            return
        for code in GATE_CODES:
            mon.set_local_events(self._tool, code, 0)
        mon.register_callback(self._tool, mon.events.PY_START, None)
        mon.free_tool_id(self._tool)
        self._tool = None


class GateClient:
    """``httpx.AsyncClient`` 的薄包装：每个请求前做自检，请求在 ``GateTrace`` 内发出。"""

    def __init__(self, http: AsyncClient, api: FastAPI) -> None:
        self.http = http
        self.app = api
        self.gate_runs: dict[str, int] = {}  # 上一个请求里各生产门禁代码开始执行的次数

    async def request(self, method: str, url: str, **kwargs: Any) -> Response:
        assert_gates_are_production()
        assert_world_overrides(self.app)
        with GateTrace() as trace:
            try:
                response = await self.http.request(method, url, **kwargs)
            finally:
                self.gate_runs = dict(trace.counts)
        return response

    async def get(self, url: str, **kwargs: Any) -> Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Response:
        return await self.request("DELETE", url, **kwargs)

    def assert_passed(self, gate: str, times: int | None = None) -> None:
        """上一个请求执行过生产门禁 ``gate`` 的代码（``times`` 给出时次数须相等）。"""
        if gate not in TRACED_GATES:
            raise KeyError(f"{gate!r} 不在观测范围内；可选：{list(TRACED_GATES)}")
        runs = self.gate_runs.get(gate, 0)  # 还没发过请求时为 0
        if times is None and runs == 0:
            raise AssertionError(f"上一个请求没有执行生产门禁 {gate}")
        if times is not None and runs != times:
            raise AssertionError(f"上一个请求执行生产门禁 {gate} {runs} 次，期望 {times} 次")


# ─── 按生产注册挂 router ─────────────────────────────────────────────────────


class _RegistrationRecorder:
    """代替 FastAPI 应用接收 ``router_registry`` 的 ``include_router`` 调用，只记录（router，参数）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[APIRouter, dict[str, Any]]] = []

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        self.calls.append((router, kwargs))

    @property
    def routes(self) -> list[Any]:  # 供注册完整性校验读取，与生产应用的路由同源
        return [route for router, _ in self.calls for route in router.routes]


@cache
def production_registrations() -> tuple[tuple[APIRouter, dict[str, Any]], ...]:
    """跑一遍生产的 ``register_all_routers``，得到每次 ``include_router`` 的（router，前缀 / 依赖 / 标签等参数）。"""
    from app.router_registry import register_all_routers

    recorder = _RegistrationRecorder()
    register_all_routers(recorder)  # type: ignore[arg-type]
    return tuple(recorder.calls)


def _router_label(router: APIRouter) -> str:
    modules = sorted({route.endpoint.__module__ for route in router.routes if hasattr(route, "endpoint")})
    return f"router（前缀 {router.prefix!r}，端点模块 {modules}）"


def build_app(*routers: APIRouter) -> FastAPI:
    """只挂指定 router 的应用；前缀、注册时附加的依赖等参数与生产注册逐次相同（同一 router 注册多次则挂多次）。"""
    if not routers:
        raise ValueError("build_app 至少需要一个 router")
    registrations = production_registrations()
    api = FastAPI()
    for router in routers:
        matched = [kwargs for registered, kwargs in registrations if registered is router]
        if not matched:
            raise LookupError(f"{_router_label(router)} 没有经 router_registry 注册：端点级测试只测生产注册的路径")
        for kwargs in matched:
            api.include_router(router, **kwargs)
    return api


# ─── 业务 service 桩 ─────────────────────────────────────────────────────────


@dataclass(eq=False)
class ServiceStub:
    """端点业务 service 的桩：记录每次调用的参数，返回 ``returns``（``awaitable`` 时包成协程）。"""

    target: str
    returns: Any = None
    awaitable: bool = True
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if not self.awaitable:
            return self.returns

        async def _result() -> Any:
            return self.returns

        return _result()

    @property
    def count(self) -> int:
        return len(self.calls)


def _owner_module(owner: Any) -> str:
    return owner.__name__ if isinstance(owner, ModuleType) else str(getattr(owner, "__module__", ""))


def _owner_label(owner: Any) -> str:
    if isinstance(owner, ModuleType):
        return owner.__name__
    return f"{_owner_module(owner)}.{getattr(owner, '__qualname__', type(owner).__qualname__)}"


def _assert_stubbable(owner: Any, attr: str) -> None:
    """门禁、门禁所在模块里的对象、可替换点不能当业务 service 打桩（需求 12.1）。"""
    current = getattr(owner, attr)
    owner_module = _owner_module(owner)
    if (
        _is_gate_callable(current)
        or attr in _REPLACEABLE_NAMES
        or owner_module in _GUARDED_MODULES
        or str(getattr(current, "__module__", "")) in _GUARDED_MODULES
    ):
        raise ValueError(
            f"{owner_module}.{attr} 是门禁、判定或可替换点，不能当业务 service 打桩；"
            "可替换点请用 AuthzWorld 上对应的 replace_* 方法（需求 12.1）"
        )


# ─── 权限世界 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Identity:
    """一种身份：真实的 ``User`` 行，请求发往的目标项目，及其在库里的成员行 / 委派。"""

    key: str
    label: str
    user: User
    project: Project
    member: ProjectUser | None = None  # 在目标项目的成员行
    assignment: ProjectAssignment | None = None  # 在目标项目的 EQCR 别名委派（仅 ⑤）
    other_project: Project | None = None  # 有权的另一项目（仅 ④）
    other_member: ProjectUser | None = None  # 在另一项目的成员行（仅 ④）


class AuthzWorld:
    """一个权限世界：会话、目标项目、身份工厂、可替换点与端点客户端。用 ``sqlite_world`` / ``pg_world`` 创建。"""

    def __init__(self, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, schema: str | None = None) -> None:
        self.db = db
        self.monkeypatch = monkeypatch
        self.schema = schema  # PG 版的临时 schema 名；SQLite 版为 None
        self.dialect: str = db.get_bind().dialect.name
        self.redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
        self.replaced: set[str] = set()
        self.rls_calls: list[str] = []  # replace_rls 之后，门禁设置 RLS 上下文时传入的项目 id
        self.target: Project
        self._other: Project | None = None

    @classmethod
    async def create(cls, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, schema: str | None = None) -> AuthzWorld:
        world = cls(db, monkeypatch, schema=schema)
        # Redis 客户端：两个客户端名都指向本世界独占的 fakeredis（初始为空 ⇒ 不预置任何键）
        monkeypatch.setattr(core_redis, "redis_client", world.redis)
        monkeypatch.setattr(core_redis, "_redis_client", world.redis)
        world.target = await world.project(project_id=TARGET_PROJECT_ID, name="【测试】权限世界目标项目")
        return world

    async def _add(self, row: Any) -> Any:
        self.db.add(row)
        await self.db.flush()
        return row

    # ── 基本工厂 ──

    async def user(self, global_role: UserRole | str = UserRole.auditor) -> User:
        tag = uuid.uuid4().hex[:12]
        return await self._add(User(
            username=f"aw-{tag}", email=f"{tag}@authz-world.test", hashed_password="x",
            role=UserRole(global_role), is_active=True,
        ))

    async def project(
        self, *, project_id: uuid.UUID | None = None, name: str = "【测试】权限世界项目",
        status: ProjectStatus = ProjectStatus.execution, consol_lock: bool = False, is_deleted: bool = False,
    ) -> Project:
        return await self._add(Project(
            id=project_id or uuid.uuid4(), name=name, client_name="权限世界", status=status,
            consol_lock=consol_lock, is_deleted=is_deleted,
        ))

    async def other_project(self) -> Project:
        """身份④有权的另一项目（固定 id，一个世界只建一次）。"""
        if self._other is None:
            self._other = await self.project(project_id=OTHER_PROJECT_ID, name="【测试】权限世界另一项目")
        return self._other

    async def member(
        self, level: PermissionLevel | str, role: ProjectUserRole | str, *, project: Project | None = None,
        user: User | None = None, global_role: UserRole | str = UserRole.auditor,
    ) -> Identity:
        """在 ``project``（默认目标项目）建一条未删除成员行（role, level）；``user`` 省略时新建全局角色为 ``global_role`` 的用户。"""
        project = project or self.target
        user = user or await self.user(global_role)
        project_role, permission_level = ProjectUserRole(role), PermissionLevel(level)
        row = await self._add(ProjectUser(
            project_id=project.id, user_id=user.id, role=project_role, permission_level=permission_level,
        ))
        return Identity("member", f"成员（{project_role.value}, {permission_level.value}）", user, project, member=row)

    async def eqcr_assignment(
        self, alias: str = "eqcr", *, user: User, project: Project | None = None,
    ) -> ProjectAssignment:
        """给 ``user`` 建一条人员库记录，并在 ``project``（默认目标项目）建一条角色为 ``alias`` 的现行委派。"""
        project = project or self.target
        staff = await self._add(StaffMember(user_id=user.id, name="权限世界人员"))
        return await self._add(ProjectAssignment(
            project_id=project.id, staff_id=staff.id, role=alias, assigned_at=datetime.now(timezone.utc),
        ))

    async def non_member_with_other_project(self, *, global_role: UserRole | str = UserRole.auditor) -> Identity:
        """身份④：在目标项目没有成员行，在另一项目有一条（manager, edit）成员行。"""
        user = await self.user(global_role)
        other = await self.other_project()
        row = await self._add(ProjectUser(
            project_id=other.id, user_id=user.id, role=ProjectUserRole.manager, permission_level=PermissionLevel.edit,
        ))
        return Identity("non_member", IDENTITY_LABELS["non_member"], user, self.target, other_project=other, other_member=row)

    async def add_note(
        self, *, note_id: uuid.UUID = TARGET_NOTE_ID, project: Project | None = None, year: int = 2025,
        note_section: str = "五、1", section_title: str = "货币资金",
    ) -> DisclosureNote:
        """目标项目上的一条附注（对象 id 端点用）。"""
        project = project or self.target
        return await self._add(DisclosureNote(
            id=note_id, project_id=project.id, year=year, note_section=note_section, section_title=section_title,
        ))

    # ── 需求 12.2 五种标准身份、12.4 三种补充情形 ──

    def _named(self, identity: Identity, key: str) -> Identity:
        return replace(identity, key=key, label=IDENTITY_LABELS[key])

    async def edit_member(self) -> Identity:
        """① 成员行（manager, edit）。"""
        return self._named(await self.member("edit", "manager"), "edit_member")

    async def review_member(self) -> Identity:
        """② 成员行（qc, review），没有 EQCR 别名委派。"""
        return self._named(await self.member("review", "qc"), "review_member")

    async def readonly_member(self) -> Identity:
        """③ 成员行（readonly, readonly）。"""
        return self._named(await self.member("readonly", "readonly"), "readonly_member")

    async def non_member(self) -> Identity:
        """④ 目标项目没有成员行，另一项目一条（manager, edit）成员行。"""
        return await self.non_member_with_other_project()

    async def project_eqcr(self) -> Identity:
        """⑤ 成员行（partner, review），并在目标项目持有一条 ``eqcr`` 现行委派。"""
        identity = await self.member("review", "partner")
        assignment = await self.eqcr_assignment("eqcr", user=identity.user)
        return replace(self._named(identity, "project_eqcr"), assignment=assignment)

    async def archived_edit_member(self) -> Identity:
        """⑥ 身份①的成员，目标项目置为已归档（同一世界里的其他身份随之落在已归档项目上，要对照就各用一个世界）。"""
        identity = self._named(await self.member("edit", "manager"), "archived_edit_member")
        self.target.status = ProjectStatus.archived
        await self.db.flush()
        return identity

    async def qc_review_member(self) -> Identity:
        """⑦ 全局角色 qc，成员行（qc, review）。"""
        return self._named(await self.member("review", "qc", global_role=UserRole.qc), "qc_review_member")

    async def admin_non_member(self) -> Identity:
        """⑧ 全局角色 admin，不是本项目成员。"""
        user = await self.user(UserRole.admin)
        return Identity("admin_non_member", IDENTITY_LABELS["admin_non_member"], user, self.target)

    async def identity(self, key: str) -> Identity:
        """按 ``IDENTITY_LABELS`` 的键建身份（参数化用）。"""
        if key not in IDENTITY_LABELS:
            raise KeyError(f"未登记的身份 {key!r}；可选：{list(IDENTITY_LABELS)}")
        return await getattr(self, key)()

    # ── 可替换点（需求 12.1；只有这些） ──

    def replace_rls(self) -> None:
        """RLS 上下文设置置空：只记录项目 id。"""
        if "rls" in self.replaced:
            return

        async def _record(_session: AsyncSession, project_id: uuid.UUID | str) -> None:
            self.rls_calls.append(str(project_id))

        self.monkeypatch.setattr(deps, "set_rls_context", _record)
        self.monkeypatch.setattr(core_database, "set_rls_context", _record)
        self.replaced.add("rls")

    def replace_archive_guard(self) -> None:
        """归档守卫置空：只用于不观测归档结论的用例。"""

        async def _skip(_db: AsyncSession, _project_id: uuid.UUID, _user: User, _min_permission: str) -> None:
            return None

        self.monkeypatch.setattr(deps, "_check_project_not_archived", _skip)
        self.replaced.add("archive_guard")

    def replace_eqcr_query(self, count: int = 0) -> None:
        """委派查询（``is_project_eqcr`` 的下一层）固定返回 ``count``：只用于不观测 EQCR 结论的用例。"""

        async def _count(_db: AsyncSession, _user_id: uuid.UUID, _project_id: uuid.UUID) -> int:
            return count

        self.monkeypatch.setattr(eqcr_resolver, "_count_project_eqcr_assignments", _count)
        self.replaced.add("eqcr_query")

    def assert_not_replaced(self, *points: str) -> None:
        """观测某判定的用例自证该判定的下层没有被替换。"""
        unknown = sorted(set(points) - REPLACEABLE_POINTS)
        if unknown:
            raise ValueError(f"未登记的可替换点 {unknown}；可选：{sorted(REPLACEABLE_POINTS)}")
        hit = sorted(set(points) & self.replaced)
        if hit:
            raise AssertionError(f"本用例观测的判定已被替换：{hit}")

    def stub(self, owner: Any, attr: str, returns: Any = None, *, awaitable: bool = True) -> ServiceStub:
        """把端点的业务 service ``owner.attr`` 换成计数桩。"""
        _assert_stubbable(owner, attr)
        stub = ServiceStub(target=f"{_owner_label(owner)}.{attr}", returns=returns, awaitable=awaitable)
        self.monkeypatch.setattr(owner, attr, stub)
        return stub

    # ── 端点客户端 ──

    @asynccontextmanager
    async def client(
        self, *routers: APIRouter, user: User | None, replace_rls: bool = True,
    ) -> AsyncIterator[GateClient]:
        """按生产注册只挂 ``routers`` 的应用 + httpx 真发请求（ASGI，同一事件循环，能用本世界的异步会话）。

        ``user`` 为世界里的真实 ``User`` 行；``None`` 表示未登录（不 override 当前用户，真实 ``get_current_user`` 判定）。
        """
        async with self.client_for_app(build_app(*routers), user=user, replace_rls=replace_rls) as client:
            yield client

    @asynccontextmanager
    async def client_for_app(
        self, api: FastAPI, *, user: User | None, replace_rls: bool = True,
    ) -> AsyncIterator[GateClient]:
        """在给定应用上装好当前用户与会话 override 后发请求（生产端点请用 ``client``）。"""
        session = self.db

        async def _db():  # override 不能带 *args / **kwargs：FastAPI 会当成必填查询参数（422）
            yield session

        api.dependency_overrides[get_db] = _db
        if user is not None:

            async def _user() -> User:
                return user

            api.dependency_overrides[get_current_user] = _user
        if replace_rls:
            self.replace_rls()
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://authz-world") as http:
            yield GateClient(http, api)


# ─── 建世界 ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def sqlite_world(
    monkeypatch: pytest.MonkeyPatch, *, extra_tables: Iterable[Table] = (),
) -> AsyncIterator[AuthzWorld]:
    """SQLite 内存库版权限世界（``extra_tables``：六张表之外要补建的表）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(create_world_schema, tuple(extra_tables))
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            world = await AuthzWorld.create(session, monkeypatch)
            try:
                yield world
            finally:
                await world.redis.aclose()
    finally:
        await engine.dispose()


def pg_engine() -> AsyncEngine:
    """连真 PG 的引擎：连接串只取进程环境变量 ``DATABASE_URL``（不读 .env、不回显）；SSL 参数与 ``app.core.database`` 同口径。"""
    from app.core.config import settings

    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        raise RuntimeError("PG 版权限世界只取进程环境变量 DATABASE_URL，且须指向 PostgreSQL（仅供 pg_only 用例）")
    connect_args = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)


@asynccontextmanager
async def pg_world(
    monkeypatch: pytest.MonkeyPatch, *, extra_tables: Iterable[Table] = (),
) -> AsyncIterator[AuthzWorld]:
    """真 PG 版权限世界：同一事务内建临时 schema，``search_path`` 只含它，结束整体回滚（``extra_tables`` 同 SQLite 版）。"""
    engine = pg_engine()
    schema = f"authz_world_{uuid.uuid4().hex[:12]}"
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                # 只含临时 schema：不带 schema 的表名、类型名不可能解析到 public 的正式对象
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                await conn.run_sync(create_world_schema, tuple(extra_tables))
                async with AsyncSession(
                    bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint",
                ) as session:
                    world = await AuthzWorld.create(session, monkeypatch, schema=schema)
                    try:
                        yield world
                    finally:
                        await world.redis.aclose()
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
