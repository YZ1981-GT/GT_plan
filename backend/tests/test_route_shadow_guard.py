"""全应用路由遮蔽守卫（spec platform-performance-residual-findings-closure R1）

═══ 缘起 ═══

Starlette 按注册顺序取第一条命中的路由。同方法下，**先注册的参数路由**能匹配**后注册路由**的路径时，
后者永远不可达 —— 源码里看得见两个实现，任何 grep 判据都会绿：

* ``GET /api/report-config/row-note-mapping`` 被同文件先声明的 ``GET /{config_id}`` 截走 ⇒ 恒 422，
  报表页附注列从上线起一直走前端静态映射；
* ``GET /api/projects/{project_id}/workhours/budget-vs-actual`` 被 ``/workhours/{entry_id}`` 截走 ⇒ 工时页预算对比恒 422；
* ``GET /api/projects/{pid}/workpapers/{wp_id}/versions``（版本链快照）与导入导出的归档历史同路径，
  版本历史抽屉拿到的是另一份数据（恒空）。

2026-10-31 现算 2576 条 API 路由：遮蔽 13 条（含两组「两功能同路径、参数名不同」）。重复注册（同方法同 path
字符串）由 ``test_duplicate_route_registration_baseline.py`` 守；本守卫看 path 字符串不同、但匹配上会撞的那一类。

═══ 判据 ═══

以运行期 ``app.routes`` 为准（懒路由只推迟重属性、路由索引按原下标取第一条，二者不改变匹配顺序）：
对每条 HTTP 路由按参数转换器生成样本路径（``{x}`` → ``x0``、``{x:int}`` → ``1``、``{x:uuid}`` → 合法 UUID、
``{x:path}`` → ``x0``），看它**之前**注册的路由里有没有同方法、``path_regex`` 已能匹配该样本的（``Mount``
不分方法）。允许集为空，只许保持为空。

已知局限：后注册路由的单段参数取 ``x0``，先注册路由若用了 ``{x:uuid}`` / ``{x:int}`` 这类收窄转换器，
「真实 UUID 被前者截走」这种部分遮蔽看不到（2026-10-31 全仓只用了 ``:path``，无单段收窄转换器）。
"""
from __future__ import annotations

import re
from collections.abc import Iterable

import pytest

#: 已知遮蔽（later_method, later_path）。🔴 只许保持为空：修好的必须真修，不许登记豁免。
_KNOWN_SHADOWS: frozenset[tuple[str, str]] = frozenset()

#: 与 Starlette 路由正则同口径的参数段：``{name}`` / ``{name:convertor}``
_PARAM = re.compile(r"\{([^}:]+)(?::([^}]+))?\}")
_SAMPLES = {
    None: "x0",
    "str": "x0",
    "path": "x0",
    "int": "1",
    "float": "1.5",
    "uuid": "00000000-0000-4000-8000-000000000000",
}
#: FastAPI 不为 GET 追加 HEAD，Starlette 原生 Route 会；OPTIONS 由 CORS 中间件处理
_IGNORED_METHODS = frozenset({"HEAD", "OPTIONS"})


def sample_path(path: str) -> str:
    """按参数转换器把路由模板换成一条能被它自己匹配的具体路径。"""
    return _PARAM.sub(lambda m: _SAMPLES.get(m.group(2), "x0"), path)


def _methods(route: object) -> frozenset[str]:
    return frozenset(getattr(route, "methods", None) or ()) - _IGNORED_METHODS


def _label(route: object) -> str:
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        return f"{type(route).__name__}({getattr(route, 'path', '?')})"
    return f"{endpoint.__module__}.{endpoint.__qualname__}"


def shadowed_routes(routes: Iterable[object]) -> dict[tuple[str, str], tuple[str, str, str]]:
    """``(method, 后注册 path) → (先命中的 path, 先命中者全名, 被遮蔽者全名)``。

    只看 HTTP 路由（有 ``methods``）；同 path 字符串的重复注册留给重复注册守卫。
    """
    from starlette.routing import Mount

    ordered = list(routes)
    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    for j, later in enumerate(ordered):
        later_path = getattr(later, "path", None)
        later_methods = _methods(later)
        if not later_path or not later_methods or getattr(later, "path_regex", None) is None:
            continue
        probe = sample_path(later_path)
        pending = set(later_methods)
        for earlier in ordered[:j]:
            regex = getattr(earlier, "path_regex", None)
            if regex is None:
                continue
            if isinstance(earlier, Mount):
                hit = set(pending)
            else:
                if getattr(earlier, "path", None) == later_path:
                    continue
                hit = pending & _methods(earlier)
            if not hit or not regex.match(probe):
                continue
            for method in hit:
                found[(method, later_path)] = (getattr(earlier, "path", "?"), _label(earlier), _label(later))
            pending -= hit
            if not pending:
                break
    return found


@pytest.fixture(scope="module")
def app_routes() -> list[object]:
    from app.main import app  # 延迟 import：构建 app 较重

    return list(app.routes)


def test_route_table_is_not_empty(app_routes):
    """防空转：app 没装配好时路由表会异常小，下面的断言会全体假绿。"""
    assert len(app_routes) >= 2000, len(app_routes)


def test_no_shadowed_route(app_routes):
    found = shadowed_routes(app_routes)
    new = {k: v for k, v in found.items() if k not in _KNOWN_SHADOWS}
    assert not new, (
        "后注册的路由被先注册的同方法路由截走（永远不可达）。静态路径请注册在参数路径之前"
        "（同模块调声明顺序、跨模块调 include 顺序）；两个功能共用一条路径的改名其中一条：\n"
        + "\n".join(
            f"  {m} {p}\n    先命中：{e_path}  ({e_ep})\n    被遮蔽：{l_ep}"
            for (m, p), (e_path, e_ep, l_ep) in sorted(new.items())
        )
    )


def test_allowlist_has_no_stale_entries(app_routes):
    stale = sorted(k for k in _KNOWN_SHADOWS if k not in shadowed_routes(app_routes))
    assert not stale, f"以下已不再被遮蔽，请从 _KNOWN_SHADOWS 删除：{stale}"


#: 2026-10-31 修复的 13 条（其中两条是两功能同路径：批量复核删了死路由、版本归档改了路径）。
#: 逐条按运行期 ``route.matches`` 解析样本请求，钉住「现在由谁服务」。
_FIXED_CASES: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/attachments/paperless-health", "app.routers.attachments.check_paperless_health"),
    ("GET", "/api/report-config/row-note-mapping", "app.routers.report_row_note_mapping.get_row_note_mapping"),
    ("GET", "/api/report-config/candidates", "app.routers.report_config_baseline.list_candidates"),
    ("GET", "/api/disclosure-notes/{p}/2025/deleted", "app.routers.disclosure_notes.list_deleted_sections"),
    ("GET", "/api/disclosure-notes/{p}/2025/formula-health", "app.routers.disclosure_notes.formula_health"),
    ("GET", "/api/disclosure-notes/{p}/wp-mapping", "app.routers.note_wp_mapping.get_mapping"),
    ("GET", "/api/disclosure-notes/{p}/sections", "app.routers.note_trim.get_sections"),
    ("GET", "/api/disclosure-notes/{p}/sections/trim-scheme", "app.routers.note_trim.get_trim_scheme"),
    ("GET", "/api/projects/{p}/workhours/summary", "app.routers.workhour_entries.get_summary"),
    ("GET", "/api/projects/{p}/workhours/budget-vs-actual", "app.routers.workhour_budget.get_budget_compare"),
    ("GET", "/api/projects/{p}/workhours/approval", "app.routers.workhour_approval.list_pending_approvals"),
    ("GET", "/api/projects/{p}/workpapers/{w}/versions", "app.routers.version_trail.list_versions"),
    ("GET", "/api/projects/{p}/workpapers/{w}/version-archives",
     "app.routers.wp_export_import_router.get_version_history"),
    ("POST", "/api/projects/{p}/ai-batch-review", "app.routers.review_prompt.batch_review"),
)
_SAMPLE_PID = "11111111-1111-4111-8111-111111111111"
_SAMPLE_WID = "22222222-2222-4222-8222-222222222222"


def resolve_endpoint(routes: Iterable[object], method: str, path: str) -> str | None:
    """与 Starlette ``Router.app`` 同口径：按注册顺序取第一条 ``Match.FULL`` 的路由。"""
    from starlette.routing import Match

    scope = {"type": "http", "method": method, "path": path, "root_path": "", "headers": []}
    for route in routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return _label(route)
    return None


@pytest.mark.parametrize("method,template,expected", _FIXED_CASES)
def test_fixed_routes_resolve_to_their_own_endpoint(app_routes, method, template, expected):
    path = template.replace("{p}", _SAMPLE_PID).replace("{w}", _SAMPLE_WID)
    assert resolve_endpoint(app_routes, method, path) == expected


def test_pm_dashboard_dead_batch_review_is_gone(app_routes):
    """``pm_dashboard.batch_review`` 从未可达且绕过复核状态机：删除，不得复活到别的路径上。"""
    assert not [r for r in app_routes if _label(r) == "app.routers.pm_dashboard.batch_review"]


def test_detector_catches_injected_shadow_and_spares_legal_orders():
    """双向变异：参数在前必报；静态在前、不同方法、收窄转换器、段数不同都不得误报。"""
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/p/{item_id}")
    async def p_param():  # pragma: no cover - 只注册不调用
        return 1

    @router.get("/p/static")
    async def p_static():  # pragma: no cover
        return 2

    @router.post("/p/static")
    async def p_static_post():  # pragma: no cover - 不同方法：不算
        return 3

    @router.get("/q/static")
    async def q_static():  # pragma: no cover - 静态在前：合法
        return 4

    @router.get("/q/{item_id}")
    async def q_param():  # pragma: no cover
        return 5

    @router.get("/r/{n:int}")
    async def r_int():  # pragma: no cover - 收窄转换器：不截字面量段
        return 6

    @router.get("/r/static")
    async def r_static():  # pragma: no cover
        return 7

    @router.get("/s/{a}/{b}")
    async def s_two():  # pragma: no cover - 段数不同：不截
        return 8

    @router.get("/s/{a}")
    async def s_one():  # pragma: no cover
        return 9

    @router.get("/t/{pid}/x")
    async def t_pid():  # pragma: no cover - 两功能同路径、参数名不同：必报
        return 10

    @router.get("/t/{project_id}/x")
    async def t_project_id():  # pragma: no cover
        return 11

    found = shadowed_routes(router.routes)
    assert set(found) == {("GET", "/p/static"), ("GET", "/t/{project_id}/x")}, found
    assert found[("GET", "/p/static")][0] == "/p/{item_id}"
    assert found[("GET", "/p/static")][1].endswith(".p_param")
    assert found[("GET", "/p/static")][2].endswith(".p_static")


def test_detector_sees_mounts_regardless_of_method():
    """先挂的 Mount 不分方法截走前缀下的一切：也要报。"""
    from fastapi import APIRouter
    from starlette.applications import Starlette
    from starlette.routing import Mount

    router = APIRouter()

    @router.post("/static/upload")
    async def upload():  # pragma: no cover
        return 1

    routes = [Mount("/static", app=Starlette()), *router.routes]
    found = shadowed_routes(routes)
    assert set(found) == {("POST", "/static/upload")}, found


def test_sample_path_honours_convertors():
    assert sample_path("/a/{x}/b/{y:int}/c/{z:uuid}") == "/a/x0/b/1/c/00000000-0000-4000-8000-000000000000"
    assert sample_path("/f/{k:path}") == "/f/x0"
