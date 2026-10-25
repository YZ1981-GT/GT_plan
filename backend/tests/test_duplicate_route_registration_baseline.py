"""重复路由注册棘轮守卫

spec: knowledge-upload-robustness-and-consumer-wiring（Requirement 7.1）

═══ 缘起 ═══

``POST /api/disclosure-notes/{project_id}/ai/complete`` 在 ``note_ai.py`` 里注册了两次：
FastAPI 按注册顺序匹配，先注册的 query 参数版遮蔽了 body 版 ⇒ 前端按 JSON 调用恒 422，
附注「AI 续写」从上线起就不可用，而源码里「看得见」两个实现、任何 grep 判据都会绿。

触类旁通现算全应用（2026-09-30，2414 条 method+path）：重复注册 **11** 组，横跨 6 个业务域。
本 spec 修掉附注那一组；其余 10 组逐个需判断哪份是活实现（被遮蔽的那份可能才是新版），
超出本 spec 范围 ⇒ **冻结为基线，只许减少**。

判据一律以运行期 ``app.routes`` 为准（不 grep 源码：同名函数、条件注册、router 重复
include 都只在运行期可见 —— ``b60`` 那组就是同一个函数被注册了两次）。
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import pytest

#: 2026-09-30 冻结的「已知重复」（method, path）。🔴 只许删除条目，不许新增：
#: 修掉一组后必须同步删掉它（``test_baseline_has_no_stale_entries`` 会逼你删）。
_KNOWN_DUPLICATES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/aging/presets"),
    ("GET", "/api/b60/chapter-definitions"),
    ("GET", "/api/projects/{project_id}/a16/recommended-version"),
    ("GET", "/api/projects/{project_id}/aging/config"),
    ("GET", "/api/projects/{project_id}/issue-hints"),
    ("GET", "/api/projects/{project_id}/working-papers/{wp_id}/export-word"),
    ("GET", "/api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete"),
    ("GET", "/api/projects/{project_id}/workpaper-summaries/{key}"),
    ("POST", "/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry"),
    ("PUT", "/api/projects/{project_id}/aging/config"),
})

#: 本 spec 修复的那一组：不得回归
_FIXED = ("POST", "/api/disclosure-notes/{project_id}/ai/complete")

#: FastAPI 不自动为 GET 追加 HEAD，但 Starlette 原生 Route 会；OPTIONS 由 CORS 中间件处理
_IGNORED_METHODS = frozenset({"HEAD", "OPTIONS"})


def duplicated_routes(routes: Iterable[object]) -> dict[tuple[str, str], list[str]]:
    """``(method, path) → [endpoint 全名, …]``，只返回注册次数 ≥ 2 的组（按注册顺序，首个生效）。"""
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in routes:
        methods = getattr(route, "methods", None) or ()
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or endpoint is None:
            continue
        where = f"{endpoint.__module__}.{endpoint.__qualname__}"
        for method in methods:
            if method not in _IGNORED_METHODS:
                seen[(method, path)].append(where)
    return {k: v for k, v in seen.items() if len(v) > 1}


@pytest.fixture(scope="module")
def app_routes() -> list[object]:
    from app.main import app  # 延迟 import：构建 app 较重

    return list(app.routes)


def test_route_table_is_not_empty(app_routes):
    """防空转：app 没装配好时路由表会异常小，下面的断言会全体假绿。"""
    assert len(app_routes) >= 2000, len(app_routes)


def test_no_new_duplicate_route(app_routes):
    dups = duplicated_routes(app_routes)
    new = {k: v for k, v in dups.items() if k not in _KNOWN_DUPLICATES}
    assert not new, (
        "新增了重复注册的路由（先注册者遮蔽后注册者，后者永远不可达）：\n"
        + "\n".join(f"  {m} {p}\n    生效：{w[0]}\n    被遮蔽：{', '.join(w[1:])}" for (m, p), w in sorted(new.items()))
    )


def test_note_ai_complete_is_registered_exactly_once(app_routes):
    hits = [
        r for r in app_routes
        if getattr(r, "path", None) == _FIXED[1] and _FIXED[0] in (getattr(r, "methods", None) or ())
    ]
    assert len(hits) == 1, [f"{r.endpoint.__module__}.{r.endpoint.__qualname__}" for r in hits]


def test_baseline_has_no_stale_entries(app_routes):
    """棘轮只许向下：已修好的组必须从 ``_KNOWN_DUPLICATES`` 删除，锁住成果。"""
    dups = duplicated_routes(app_routes)
    stale = sorted(k for k in _KNOWN_DUPLICATES if k not in dups)
    assert not stale, f"以下已不再重复注册，请从 _KNOWN_DUPLICATES 删除：{stale}"


def test_detector_catches_an_injected_duplicate():
    """双向变异：检测器对注入的重复路由必须命中、对同路径不同方法不得误报。"""
    from fastapi import APIRouter

    router = APIRouter(prefix="/probe")

    @router.post("/x")
    async def first():  # pragma: no cover - 只注册不调用
        return 1

    @router.post("/x")
    async def second():  # pragma: no cover
        return 2

    @router.get("/x")
    async def third():  # pragma: no cover
        return 3

    dups = duplicated_routes(router.routes)
    assert set(dups) == {("POST", "/probe/x")}
    # 按注册顺序：首个生效、其余被遮蔽
    assert [w.rsplit(".", 1)[-1] for w in dups[("POST", "/probe/x")]] == ["first", "second"]
