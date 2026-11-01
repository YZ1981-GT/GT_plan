"""三个高级查询写端点在**最终运行栈**里一律 410（advanced-query-linkage-closure 阶段 0；ADR-AQL-02）。

与 `test_aql_writeback_isolation_pg.py` 的区别，也正是本文件存在的理由：那边用
`tests.authz_world.build_app` 自建应用，证明的是「路由实现返回 410」；这里用生产的
`app.main.app`，证明的是「用户真实访问到的那一套栈」也返回 410 —— 自建应用不装平台的
响应信封中间件、也不含生产的 router 注册顺序，两者任一环节出问题都可能让自建那侧全绿而
生产侧仍是 404 / 401 / 422。

判据分三层，缺一层都可能假绿：

1. **路由表层**：按 Starlette「首条命中」语义解析 `app.routes`，命中的必须是退役桩本身。
   只数「路径存在」会被同路径的旧实现遮蔽或被重复注册的另一份接走（平台有过 13 条路由遮蔽
   的先例），所以这里断言命中的端点函数名与同路径候选数。
2. **响应层**：不带登录态、请求体故意畸形，仍必须得 410 且带同一错误码 ——
   退役要早于鉴权与请求体校验，否则旧客户端拿到 401 / 422，看不出「已下线」。
3. **实现层**：桩不得依赖数据库会话（无 `get_db`），即不占连接池、不可能写库。

另配阳性对照：一条仍在服务的路径不得也是 410，否则说明判据在对所有路径空转。
"""
from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Match

RETIRED_PATHS = {
    "/api/custom-query/cell-writeback": "cell_writeback_gone",
    "/api/custom-query/writeback-preview": "writeback_preview_gone",
    "/api/custom-query/writeback-confirm": "writeback_confirm_gone",
}
RETIRED_ERROR_CODE = "ADVANCED_QUERY_WRITEBACK_RETIRED"


@pytest.fixture(scope="module")
def runtime_app():
    """生产应用对象（不是测试自建的那一个）。"""
    from app.main import app

    return app


@pytest.fixture(scope="module")
def runtime_client(runtime_app):
    """不进入 lifespan：退役桩不需要任何应用状态，而 startup 会连库跑迁移与启动任务。

    刻意不用 ``with TestClient(...)``——那会触发 lifespan，在没有可用库的环境里整组报错，
    把「路由与响应」的判据变成「环境是否就绪」的判据。
    """
    return TestClient(runtime_app, raise_server_exceptions=False)


def _resolve(app, path: str, method: str = "POST"):
    """按 Starlette 首条命中语义解析 (命中的 route, 同路径候选数)。"""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "headers": [],
        "query_string": b"",
    }
    same_path = [r for r in app.routes if getattr(r, "path", None) == path]
    for route in app.routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return route, len(same_path)
    return None, len(same_path)


def _find_error_code(node: object) -> str | None:
    """错误信封形状由平台中间件决定，这里不假设层级（生产是 ``{code, message{...}}``）。"""
    if isinstance(node, dict):
        value = node.get("error_code")
        if isinstance(value, str):
            return value
        for child in node.values():
            found = _find_error_code(child)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_error_code(child)
            if found:
                return found
    return None


@pytest.mark.parametrize("path", sorted(RETIRED_PATHS))
def test_retired_path_resolves_to_the_retirement_stub(runtime_app, path: str) -> None:
    route, same_path = _resolve(runtime_app, path)
    assert route is not None, f"{path}: POST 在生产路由表里无命中 —— 旧客户端会拿到 404 而非可诊断的 410"
    assert getattr(route.endpoint, "__name__", None) == RETIRED_PATHS[path], (
        f"{path}: 命中的端点是 {getattr(route.endpoint, '__name__', None)!r}，"
        f"不是退役桩 {RETIRED_PATHS[path]!r} —— 该路径被别的实现接走了"
    )
    assert same_path == 1, f"{path}: 同路径注册了 {same_path} 条路由，首条命中可能随注册顺序漂移"
    assert getattr(route, "status_code", None) == 410, f"{path}: 声明的状态码不是 410"


@pytest.mark.parametrize("path", sorted(RETIRED_PATHS))
def test_retired_path_returns_410_before_auth_and_body_validation(runtime_client, path: str) -> None:
    response = runtime_client.post(path, json={"malformed": True})
    assert response.status_code == 410, (
        f"{path}: 无登录态 + 畸形请求体得 {response.status_code}，不是 410 —— "
        "退役必须早于鉴权与请求体校验"
    )
    assert _find_error_code(response.json()) == RETIRED_ERROR_CODE, response.text[:400]


@pytest.mark.parametrize("path", sorted(RETIRED_PATHS))
def test_retirement_stub_does_not_touch_the_database(runtime_app, path: str) -> None:
    route, _ = _resolve(runtime_app, path)
    assert route is not None
    deps = [
        getattr(getattr(p.default, "dependency", None), "__name__", None)
        for p in inspect.signature(route.endpoint).parameters.values()
        if getattr(p.default, "dependency", None) is not None
    ]
    assert not [d for d in deps if d and "get_db" in d], (
        f"{path}: 退役桩仍依赖数据库会话 {deps} —— 未实现的能力不应占用连接池"
    )


def test_a_live_path_is_not_410(runtime_client) -> None:
    """阳性对照：判据不是对所有路径都报 410（否则上面三条恒绿）。"""
    response = runtime_client.get("/api/health")
    assert response.status_code != 410, "阳性对照失败：仍在服务的路径也返回 410，判据在空转"
