"""权限缓存移除守卫与 Redis 不可用用例（partner-manager-edit-permission 任务 3.5；design D3、D12、§2.2；需求 5.3、5.7）。

接替关系：任务 3.4 随权限缓存删除了 ``test_phase8.py::TestPermissionCache`` 三例（``test_cache_miss_returns_none``、
``test_set_and_get_cache``、``test_invalidate_cache``），本文件是它们的接替测试。缓存移除后，需求 5.7「经缓存读写函数跑用例、
先跑命中对照」不再适用（design D12、§2.2），由第一部分的语法树守卫替代；第二部分按需求 5.3 实测 Redis 不可用时判定照常。

一、语法树守卫（``ast.parse``；docstring 不计，注释不进语法树）
- 扫描对象：``app.deps`` 与 ``app.services.custom_query.ownership_guard`` 的模块文件（本树 ``app`` 包内，且就是被导入运行的文件）。
- 计入的标识符：名字、属性名、函数 / 类定义名、形参名、关键字实参名、``global`` / ``nonlocal`` 声明、``except … as`` 绑定名、
  导入（模块路径、导入的名字、别名），以及 docstring 以外、整串为点分标识符的字符串常量（``getattr`` / ``importlib`` 式的
  动态引用）。点分的逐段判定。
- 判据 ①：两个模块的任何位置都不出现 ``CACHE_NAMES`` 中的名字（不定义、不引用）。
- 判据 ②：``app.deps`` 中 ``JUDGMENT_FUNCTIONS`` 四个模块顶层函数的整个定义（签名、装饰器、函数体，含嵌套函数、lambda 与类）
  不引用 Redis 客户端：没有一段含 ``redis``（不分大小写，覆盖 ``app.core.redis``、``redis_client``、``_redis_client``、
  ``get_redis``、``redis.asyncio`` 等），也没有本模块顶层从 redis 相关模块导入时绑定的名字（如把 ``redis_client`` 以
  ``as _rc`` 导入后的 ``_rc``）。模块顶层的导入语句本身不属判据 ② 的范围。
- 不空转：解析了两个模块文件且各扫到标识符；四个判定函数在模块顶层各恰定义一次；合成源码（``tmp_path``）上两条判据报出
  写回的缓存函数定义、字符串式引用、函数体内的 Redis 导入与经顶层别名的访问，docstring 与注释里的同名字样不报。

二、Redis 不可用（需求 5.3）
- 权限世界（``tests/authz_world.py``）建世界时把 ``app.core.redis`` 的两个客户端名（``redis_client``、``_redis_client``）换成
  本世界的 fakeredis（即「Redis 正常」）。本部分在同一处再换成替身：每个命令都抛 ``redis.exceptions.ConnectionError``，或每个
  命令都阻塞 5 秒。只替换 Redis 客户端这个基础设施对象，不替换任何判定函数（门禁、归档守卫、成员级别读取都是生产代码）；
  替身记下对它的每一次属性访问。
- ``assert_project_permission``：八种身份 × review / edit 级，结论与 Redis 正常时逐值相同，且等于按需求写死的期望（放行 /
  403「权限不足」/ 423）；单次判定耗时低于 1 秒；替身访问次数为 0。
- 经 HTTP：生产注册的 ``POST /api/projects/{project_id}/cross-check/rules/custom``（路由级 readonly、端点级 edit 两道
  ``require_project_access``，业务 service 打桩计数）：状态码、响应体、桩调用次数、生产门禁执行次数与 Redis 正常时逐值相同，
  不返回 5xx，单个请求耗时低于 1 秒，替身访问次数为 0。请求路径：当前用户经 override 给出，真实 ``get_current_user``（其令牌
  黑名单与 SoD 撤销检查读 ``redis_client``，不可用时自行降级跳过）不在路径上；测试应用是裸 FastAPI，没有中间件；该路由的生产
  注册不附加 ``dedicated_wp_gate``。路径上可能访问 Redis 的只有两道门禁，替身访问次数为 0 即说明它们不访问。
- 1 秒阈值：需求 5.3 的上限是「单次判定因等待缓存而增加的耗时合计不超过 1 秒」。判定点不再访问 Redis，正常时一次判定在
  SQLite 内存库上是毫秒级；阻塞替身每个命令 5 秒，判定路径上只要访问一次 Redis 就会越过阈值。
- 替身先自测（不空转）：连接错误替身的任何命令都抛错，生产取用入口 ``get_redis`` 按自身降级逻辑返回 None；阻塞替身的命令
  0.3 秒内不返回。各用例的耗时写进 ``user_properties``（junit 结果里的 properties），供验收记录取用。
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import re
import time
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

import app
import app.core.redis as core_redis
import app.deps as deps
from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import get_current_user
from app.models.core import User
from app.routers import wp_cross_check
from app.services.wp_cross_check_service import CrossCheckService
from tests.authz_world import TARGET_PROJECT_ID, AuthzWorld, GateClient, assert_gates_are_production, sqlite_world

# ═══ 一、语法树守卫 ═══════════════════════════════════════════════════════════

_APP = Path(app.__file__).resolve().parent
SCANNED_MODULES: dict[str, Path] = {
    "app.deps": _APP / "deps.py",
    "app.services.custom_query.ownership_guard": _APP / "services" / "custom_query" / "ownership_guard.py",
}
CACHE_NAMES: frozenset[str] = frozenset(
    {"_get_cached_permission", "_set_cached_permission", "invalidate_permission_cache", "PERM_CACHE_TTL"}
)
JUDGMENT_FUNCTIONS: tuple[str, ...] = (
    "_load_member_level", "assert_project_permission", "authorize_wp_edit", "authorize_wp_read",
)
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


@dataclass(frozen=True)
class Hit:
    line: int
    form: str  # 名字 / 属性 / 定义 / 形参 / 关键字实参 / 声明 / 异常绑定 / 导入 / 导入别名 / 字符串
    identifier: str

    def __str__(self) -> str:
        return f"第 {self.line} 行{self.form} {self.identifier}"


@dataclass
class ModuleScan:
    path: Path
    identifiers: int = 0  # 扫到的标识符个数（不空转）
    functions: dict[str, int] = field(default_factory=dict)  # 模块顶层函数名 → 定义次数
    redis_bound: frozenset[str] = frozenset()  # 模块顶层从 redis 相关模块导入时绑定的名字
    cache_hits: list[Hit] = field(default_factory=list)  # 判据 ①
    redis_hits: dict[str, list[Hit]] = field(default_factory=dict)  # 判据 ②：找到的判定函数 → 命中


def _mentions_redis(dotted: str) -> bool:
    return any("redis" in part.lower() for part in dotted.split("."))


def _docstrings(tree: ast.Module) -> set[ast.AST]:
    """模块、类、函数的 docstring 常量节点（节点按对象身份比较，树存活期间不会被回收）。"""
    found: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                found.add(first.value)
    return found


def _import_identifiers(node: ast.Import | ast.ImportFrom) -> list[tuple[str, str]]:
    """导入语句的模块路径、导入的名字（``from`` 形式拼上模块路径）与别名。"""
    base = (node.module or "") if isinstance(node, ast.ImportFrom) else ""
    found = [("导入", base)] if base else []
    for alias in node.names:
        found.append(("导入", f"{base}.{alias.name}" if base else alias.name))
        if alias.asname:
            found.append(("导入别名", alias.asname))
    return found


def _identifiers(node: ast.AST, docstrings: set[ast.AST]) -> list[tuple[str, str]]:
    """节点直接携带的（形态，标识符）；导入与字符串给出点分路径，由调用方逐段判定。"""
    if isinstance(node, ast.Name):
        return [("名字", node.id)]
    if isinstance(node, ast.Attribute):
        return [("属性", node.attr)]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [("定义", node.name)]
    if isinstance(node, ast.arg):
        return [("形参", node.arg)]
    if isinstance(node, ast.keyword):
        return [("关键字实参", node.arg)] if node.arg else []
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return [("声明", name) for name in node.names]
    if isinstance(node, ast.ExceptHandler):
        return [("异常绑定", node.name)] if node.name else []
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _import_identifiers(node)
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings:
        return [("字符串", node.value)] if _DOTTED.fullmatch(node.value) else []
    return []


def _module_level(tree: ast.Module) -> Iterator[ast.AST]:
    """模块顶层的节点：进入 if / try 等复合语句，不进函数、类与 lambda。"""
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _redis_bound(tree: ast.Module) -> frozenset[str]:
    """模块顶层从 redis 相关模块导入时绑定的名字。

    ``import a.b.redis`` 不带别名时绑定的是顶层包名 ``a``，不计入（否则包名的每次使用都成了命中）；这种写法经属性链
    ``a.b.redis`` 访问，属性名 ``redis`` 本身会被判据 ② 认出。
    """
    bound: set[str] = set()
    for node in _module_level(tree):
        if isinstance(node, ast.ImportFrom):
            bound.update(a.asname or a.name for a in node.names if _mentions_redis(f"{node.module or ''}.{a.name}"))
        elif isinstance(node, ast.Import):
            bound.update(a.asname for a in node.names if a.asname and _mentions_redis(a.name))
    return frozenset(bound)


def scan_module(path: Path, judgment_functions: Collection[str] = ()) -> ModuleScan:
    """扫描一个模块文件：判据 ① 扫全模块；判据 ② 只扫 ``judgment_functions`` 中定义在模块顶层的函数。"""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    docstrings = _docstrings(tree)
    scan = ModuleScan(path=path, redis_bound=_redis_bound(tree))
    for node in ast.walk(tree):
        for form, identifier in _identifiers(node, docstrings):
            scan.identifiers += 1
            if not CACHE_NAMES.isdisjoint(identifier.split(".")):
                scan.cache_hits.append(Hit(getattr(node, "lineno", 0), form, identifier))
    for top in tree.body:
        if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        scan.functions[top.name] = scan.functions.get(top.name, 0) + 1
        if top.name not in judgment_functions:
            continue
        hits = scan.redis_hits.setdefault(top.name, [])
        for node in ast.walk(top):
            for form, identifier in _identifiers(node, docstrings):
                if _mentions_redis(identifier) or not scan.redis_bound.isdisjoint(identifier.split(".")):
                    hits.append(Hit(getattr(node, "lineno", 0), form, identifier))
    return scan


@pytest.fixture(scope="module")
def scans() -> dict[str, ModuleScan]:
    return {
        name: scan_module(path, JUDGMENT_FUNCTIONS if name == "app.deps" else ())
        for name, path in SCANNED_MODULES.items()
    }


def _listing(hits: list[Hit]) -> str:
    return "；".join(str(hit) for hit in hits)


def test_scanner_reads_both_modules_and_all_four_judgment_points(scans: dict[str, ModuleScan]) -> None:
    """扫描器不空转：两个模块文件就是本树被导入运行的文件，都扫到了标识符；四个判定函数在模块顶层各恰定义一次。"""
    assert _APP == Path(__file__).resolve().parents[1] / "app"
    for name, path in SCANNED_MODULES.items():
        assert Path(importlib.import_module(name).__file__).resolve() == path, name
    assert sorted(scans) == sorted(SCANNED_MODULES)
    assert {name: scan.identifiers > 0 for name, scan in scans.items()} == dict.fromkeys(SCANNED_MODULES, True)
    deps_scan = scans["app.deps"]
    assert {fn: deps_scan.functions.get(fn, 0) for fn in JUDGMENT_FUNCTIONS} == dict.fromkeys(JUDGMENT_FUNCTIONS, 1)
    assert sorted(deps_scan.redis_hits) == sorted(JUDGMENT_FUNCTIONS)


@pytest.mark.parametrize("module", list(SCANNED_MODULES))
def test_cache_names_are_neither_defined_nor_referenced(scans: dict[str, ModuleScan], module: str) -> None:
    """判据 ①（接替 TestPermissionCache 三例）：缓存读、写、失效三个函数与 PERM_CACHE_TTL 不再定义，也不再被引用。"""
    hits = scans[module].cache_hits
    assert hits == [], f"{module} 仍定义或引用已移除的权限缓存名 {sorted(CACHE_NAMES)}：{_listing(hits)}"


@pytest.mark.parametrize("function", JUDGMENT_FUNCTIONS)
def test_judgment_point_does_not_reference_redis(scans: dict[str, ModuleScan], function: str) -> None:
    """判据 ②：成员级别读取与三个级别判定点每次直接查库，函数定义里没有对 Redis 客户端的引用。"""
    hits = scans["app.deps"].redis_hits.get(function)
    assert hits == [], f"app.deps.{function} 引用了 Redis 客户端：{_listing(hits or [])}"


# 合成源码：四个判定函数齐全；docstring（含整串恰为被禁名字的）与注释里的同名字样不该报，其余四处该报
_SYNTHETIC = '''\
"""合成模块：_get_cached_permission、PERM_CACHE_TTL、redis_client 只在 docstring 与注释里出现时不计。"""
from app.core.redis import redis_client as _rc


async def _get_cached_permission(user_id, project_id):  # 写回的缓存函数定义
    return None


async def _load_member_level(db, user_id, project_id):
    """redis_client"""
    # from app.core.redis import redis_client
    # PERM_CACHE_TTL = 300
    return None


async def assert_project_permission(db, current_user, project_id, min_permission="readonly"):
    """PERM_CACHE_TTL"""
    from app.core.redis import redis_client
    return current_user


async def authorize_wp_edit(db, current_user, wp_id):
    return getattr(db, "invalidate_permission_cache")


async def authorize_wp_read(db, current_user, wp_id):
    async def _probe():
        return await _rc.get("perm:x")
    return await _probe()
'''


def _pairs(hits: list[Hit]) -> list[tuple[str, str]]:
    return sorted((hit.form, hit.identifier) for hit in hits)


def test_scanner_reports_violations_but_not_docstrings_or_comments(tmp_path: Path) -> None:
    """扫描器不空转（合成源码，写在仓库外的临时目录）：判据 ① 报出写回的定义与字符串式引用，判据 ② 报出函数体内的 Redis
    导入与嵌套函数里经顶层别名的访问；docstring 与注释不报。"""
    path = tmp_path / "synthetic_deps.py"
    path.write_text(_SYNTHETIC, encoding="utf-8")
    scan = scan_module(path, JUDGMENT_FUNCTIONS)
    assert _pairs(scan.cache_hits) == [("字符串", "invalidate_permission_cache"), ("定义", "_get_cached_permission")]
    assert scan.redis_bound == frozenset({"_rc"})
    assert {fn: _pairs(hits) for fn, hits in scan.redis_hits.items()} == {
        "_load_member_level": [],
        "assert_project_permission": [("导入", "app.core.redis"), ("导入", "app.core.redis.redis_client")],
        "authorize_wp_edit": [],
        "authorize_wp_read": [("名字", "_rc")],
    }


# ═══ 二、Redis 不可用（需求 5.3） ═══════════════════════════════════════════════

ALLOW = "放行"
DENIED = (403, "权限不足")  # assert_project_permission 的拒绝文案
ARCHIVED_DETAIL = {
    "error_code": "PROJECT_ARCHIVED", "message": "项目已归档，无法编辑", "message_en": "Project archived (read-only)",
}
ARCHIVED = (423, ARCHIVED_DETAIL)
LEVELS = ("review", "edit")
VERDICT_BUDGET_SECONDS = 1.0  # 需求 5.3：单次判定因等待缓存而增加的耗时合计不超过 1 秒
BLOCK_SECONDS = 5.0
CONNECTION_ERROR = "Error 10061 connecting to 127.0.0.1:6379. 由于目标计算机积极拒绝，无法连接。（替身 Redis）"
OUTAGES = ("connection_error", "blocking_5s")

# 身份 → review / edit 级的结论，按需求 12.2、12.4 的身份定义与 assert_project_permission 的现行口径写死（不由被测函数推出）：
# 非 readonly 级先判归档（423）；admin 跳过成员判定；其余成员级别不低于所测级别才放行，非成员 403。
EXPECTED_VERDICTS: dict[str, dict[str, object]] = {
    "edit_member": {"review": ALLOW, "edit": ALLOW},
    "review_member": {"review": ALLOW, "edit": DENIED},
    "readonly_member": {"review": DENIED, "edit": DENIED},
    "non_member": {"review": DENIED, "edit": DENIED},
    "project_eqcr": {"review": ALLOW, "edit": DENIED},
    "archived_edit_member": {"review": ARCHIVED, "edit": ARCHIVED},
    "qc_review_member": {"review": ALLOW, "edit": DENIED},
    "admin_non_member": {"review": ALLOW, "edit": ALLOW},
}


class RedisOutage:
    """替身 Redis 客户端：每一次属性访问都记入 ``touched``；取到的命令被调用时抛连接错误，或阻塞 5 秒后返回 None。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        self.touched.append(name)
        return self._command

    async def _command(self, *_args: Any, **_kwargs: Any) -> None:
        if self.mode == "connection_error":
            raise RedisConnectionError(CONNECTION_ERROR)
        await asyncio.sleep(BLOCK_SECONDS)


def install_outage(monkeypatch: pytest.MonkeyPatch, mode: str) -> RedisOutage:
    """把 ``app.core.redis`` 的两个客户端名换成替身（权限世界换 fakeredis 也是这一处）：只换基础设施对象，不换判定函数。"""
    outage = RedisOutage(mode)
    monkeypatch.setattr(core_redis, "redis_client", outage)
    monkeypatch.setattr(core_redis, "_redis_client", outage)
    return outage


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def test_connection_error_stand_in_fails_every_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """替身不空转：任何命令都抛连接错误；生产取用入口 ``get_redis`` 按自身降级逻辑判它不可用（返回 None）；访问都被记下。"""
    outage = install_outage(monkeypatch, "connection_error")
    assert core_redis.redis_client is outage
    assert core_redis._redis_client is outage
    with pytest.raises(RedisConnectionError) as exc_info:
        await core_redis.redis_client.get("perm:probe")
    assert str(exc_info.value) == CONNECTION_ERROR
    assert await get_redis() is None
    assert outage.touched == ["get", "ping"]


async def test_blocking_stand_in_blocks_every_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """替身不空转：命令 0.3 秒内不返回（每个命令阻塞 5 秒）；访问被记下。"""
    outage = install_outage(monkeypatch, "blocking_5s")
    command = asyncio.ensure_future(core_redis.redis_client.get("perm:probe"))
    done, _pending = await asyncio.wait({command}, timeout=0.3)
    command.cancel()
    (outcome,) = await asyncio.gather(command, return_exceptions=True)
    assert done == set()
    assert type(outcome) is asyncio.CancelledError
    assert outage.touched == ["get"]


async def _verdict(world: AuthzWorld, user: User, level: str) -> tuple[object, float]:
    """真实 ``assert_project_permission`` 对（用户，目标项目，级别）的结论与耗时；结论为「放行」或（状态码，detail）。"""
    assert_gates_are_production()
    started = time.perf_counter()
    try:
        returned = await deps.assert_project_permission(world.db, user, TARGET_PROJECT_ID, level)
    except HTTPException as exc:
        return (exc.status_code, exc.detail), time.perf_counter() - started
    elapsed = time.perf_counter() - started
    assert returned is user, "放行时应原样返回当前用户"
    return ALLOW, elapsed


def _record_seconds(request: pytest.FixtureRequest, *, healthy: float, outage: float) -> None:
    """耗时写进本用例的 ``user_properties``（junit 结果里的 properties；与 ``record_property`` 同一处，不触发 xunit2 告警）。"""
    request.node.user_properties.extend([("healthy_seconds", round(healthy, 4)), ("outage_seconds", round(outage, 4))])


@pytest.mark.parametrize("outage_mode", OUTAGES)
@pytest.mark.parametrize("key", list(EXPECTED_VERDICTS))
async def test_assert_project_permission_unaffected_by_redis_outage(
    world: AuthzWorld, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, key: str, outage_mode: str,
) -> None:
    """同一世界里先在 Redis 正常时判定，再换上替身判定：结论逐值相同，耗时低于阈值，替身未被访问。"""
    identity = await world.identity(key)
    world.assert_not_replaced("archive_guard", "eqcr_query", "rls")
    healthy = {level: await _verdict(world, identity.user, level) for level in LEVELS}
    healthy_verdicts = {level: verdict for level, (verdict, _) in healthy.items()}
    assert healthy_verdicts == EXPECTED_VERDICTS[key]
    assert await world.redis.keys("*") == []  # Redis 正常时判定也不写任何键
    outage = install_outage(monkeypatch, outage_mode)
    observed = {level: await _verdict(world, identity.user, level) for level in LEVELS}
    seconds = {level: elapsed for level, (_, elapsed) in observed.items()}
    _record_seconds(request, healthy=max(elapsed for _, elapsed in healthy.values()), outage=max(seconds.values()))
    assert {level: verdict for level, (verdict, _) in observed.items()} == healthy_verdicts
    assert outage.touched == []
    assert max(seconds.values()) < VERDICT_BUDGET_SECONDS, seconds


RULES_PATH = f"/api/projects/{TARGET_PROJECT_ID}/cross-check/rules/custom"
RULE_BODY = {"description": "Redis 不可用用例规则", "formula": "1 = 1"}
STUB_RESULT = {"id": "stub-rule"}
GATE = "app.deps.assert_project_permission"
# 身份 →（状态码，响应体，业务桩调用次数，assert_project_permission 执行次数）。路由级 readonly 门禁先于端点级 edit 门禁：
# 非成员在 readonly 门禁即被拒（执行 1 次）；已归档项目在 readonly 级不判归档，到 edit 级得 423。
HTTP_EXPECTED: dict[str, tuple[int, object, int, int]] = {
    "edit_member": (200, STUB_RESULT, 1, 2),
    "review_member": (403, {"detail": "权限不足"}, 0, 2),
    "non_member": (403, {"detail": "权限不足"}, 0, 1),
    "archived_edit_member": (423, {"detail": ARCHIVED_DETAIL}, 0, 2),
    "admin_non_member": (200, STUB_RESULT, 1, 2),
}


async def _post_rule(world: AuthzWorld, client: GateClient) -> tuple[tuple[int, object, int, int], float]:
    """发一次「新增自定义校验规则」请求（业务 service 换成新的计数桩）：（状态码，响应体，桩调用次数，门禁执行次数）与耗时。"""
    stub = world.stub(CrossCheckService, "add_custom_rule", returns=STUB_RESULT)
    started = time.perf_counter()
    response = await client.post(RULES_PATH, json=RULE_BODY)
    elapsed = time.perf_counter() - started
    return (response.status_code, response.json(), stub.count, client.gate_runs[GATE]), elapsed


@pytest.mark.parametrize("outage_mode", OUTAGES)
@pytest.mark.parametrize("key", list(HTTP_EXPECTED))
async def test_http_gate_unaffected_by_redis_outage(
    world: AuthzWorld, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, key: str, outage_mode: str,
) -> None:
    """同一应用先在 Redis 正常时发一次请求，再换上替身发一次：结论与业务效果逐值相同，不返回 5xx，耗时低于阈值，替身未被访问。"""
    identity = await world.identity(key)
    async with world.client(wp_cross_check.router, user=identity.user) as client:
        healthy, healthy_seconds = await _post_rule(world, client)
        outage = install_outage(monkeypatch, outage_mode)
        observed, seconds = await _post_rule(world, client)
    _record_seconds(request, healthy=healthy_seconds, outage=seconds)
    world.assert_not_replaced("archive_guard", "eqcr_query")
    assert set(client.app.dependency_overrides) == {get_current_user, get_db}  # 真实 get_current_user 不在请求路径上
    assert healthy == HTTP_EXPECTED[key]
    assert observed == healthy
    assert observed[0] < 500
    assert outage.touched == []
    assert seconds < VERDICT_BUDGET_SECONDS
