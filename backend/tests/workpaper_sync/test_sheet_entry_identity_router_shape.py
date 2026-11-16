"""兄弟 scope 前缀端点（`/sync/entry-identity`）的路由形态守卫。

spec: `onlyoffice-sheet-open-via-published-artifact` task 2.1

═══ 为什么单独一个文件 ═══

`test_task28_sync_router.py` 是 umbrella spec
（`workpaper-html-onlyoffice-bidirectional-writeback-closure`）的路由守卫，它建立时的
前提是「每条用户路由都挂在 `USER_SYNC_PREFIX` 下」。本 spec 引入了**第二条**显式 scope
前缀：`/sync/entry-identity` 必须先算出 entry_id，因此挂不进自带 `{entry_id:path}` 的
那条。把它塞回 task28 会让两套 spec 的判据混在一起，改任一方基线都要动另一方。

═══ 这里钉什么 ═══

1. 两条前缀都带 `project/wp` 段（否则「显式 scope」只是修辞）；
2. 兄弟前缀端点集可枚举且与登记集逐值相等（防分母静默变小）；
3. `entry-identity` 的等价鉴权是 `authorize_wp_read` 项目级只读门（不是只校验登录）；
4. `entry-identity` 不需要 entry_id 就能命中（挂回去即红）。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

from app.routers import wp_sync_router as SR

_BACKEND = Path(__file__).resolve().parents[2]
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"


def _tree() -> ast.Module:
    return ast.parse(_ROUTER_PY.read_text(encoding="utf-8"))


def _func(name: str) -> ast.AST:
    for node in ast.walk(_tree()):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _explicit_scope_prefixes() -> tuple[str, ...]:
    """合法**显式 scope** 前缀全集（真源是 router 的两个常量，不是测试里的字面量）。"""
    return (SR.USER_SYNC_PREFIX, SR.ENTRY_IDENTITY_PREFIX)


def _sibling_prefix_routes() -> list[object]:
    """兄弟前缀路由。

    🔴 `ENTRY_IDENTITY_PREFIX` 是 `USER_SYNC_PREFIX` 的**字符串前缀**
    （`…/sync` ⊂ `…/sync/entries/{entry_id:path}`）。裸 `startswith` 判兄弟前缀会把
    全部用户路由算成兄弟（实测 22 条）⇒ 必须「排除 primary」再判。
    """
    return [
        r for r in SR.router.routes
        if not r.path.startswith(SR.USER_SYNC_PREFIX)
        and r.path.startswith(SR.ENTRY_IDENTITY_PREFIX)
    ]


#: 兄弟前缀端点登记集。新增这类端点必须同时给出等价鉴权判据。
_SIBLING_PREFIX_ENDPOINTS = frozenset({"resolve_entry_identity"})


def test_explicit_scope_prefixes_all_carry_project_and_wp_segments() -> None:
    """前缀本身必须带 project/wp 段 —— 否则「显式 scope」只是修辞。

    把一条前缀改成 `/api/workpaper-sync`（真实存在的 DocServer 服务凭证面）之后，
    「每条用户路由都在显式 scope 前缀下」那条判据仍会全绿而 AC 10.5 已被破坏。
    """
    for prefix in _explicit_scope_prefixes():
        for segment in ("{project_id}", "{wp_id}"):
            assert segment in prefix, (
                f"显式 scope 前缀 {prefix!r} 缺 {segment} 段 —— 它就不再是带 scope 的用户路由"
            )


def test_sibling_prefix_endpoints_are_exactly_the_registered_ones() -> None:
    """分母守卫：兄弟前缀端点必须与 `_SIBLING_PREFIX_ENDPOINTS` 逐值相等。

    新增一个兄弟前缀端点却不更新本集合 ⇒ task28 那个「每个 handler 的第一个 await 是
    `_guard`」判据的分母静默变小（该端点被 continue 跳过），而它可能真的缺鉴权。
    """
    actual = {r.endpoint.__name__ for r in _sibling_prefix_routes()}
    assert actual == set(_SIBLING_PREFIX_ENDPOINTS), (
        f"兄弟前缀端点 {sorted(actual)} ≠ 登记集 {sorted(_SIBLING_PREFIX_ENDPOINTS)} —— "
        "新增这类端点时必须同时给出等价鉴权判据"
    )


def test_entry_identity_uses_project_level_read_gate() -> None:
    """等价鉴权：必须是 `authorize_wp_read`，不是只校验登录。

    `resolve_entry_identity` 在算出 entry_id 之前无从调用 `_guard`（后者要 entry scope），
    所以它的 authorization-before-resource 由 `authorize_wp_read(db, user, wp_id)` 承担。

    🔴 若改成只 `Depends(get_current_user)`，任意登录用户就能用任意 wp_id 探测
    「该底稿有哪些 entry / 是否可在线编辑」—— 横向信息泄露。
    """
    fn = _func("resolve_entry_identity")
    names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
    }
    assert "authorize_wp_read" in names, (
        "resolve_entry_identity 没有调用 authorize_wp_read —— 兄弟前缀端点必须用项目级"
        "只读门，否则任意登录用户可枚举他人底稿的 entry"
    )


def test_entry_identity_is_reachable_without_an_entry_id() -> None:
    """兄弟前缀端点必须**不需要** entry_id 就能命中 —— 这正是它单独挂前缀的原因。

    反向自检：把本端点挂回 `USER_SYNC_PREFIX` 后（路径变成
    `…/entries/{entry_id:path}/entry-identity`），本判据会打红。
    """
    project, wp = uuid.uuid4(), uuid.uuid4()
    scope = {
        "type": "http",
        "method": "GET",
        # 注意：路径里**没有** `entries/{...}` 段。
        "path": f"/api/projects/{project}/workpapers/{wp}/sync/entry-identity",
        "headers": [],
    }
    hits = [
        route.endpoint.__name__
        for route in SR.router.routes
        if route.matches(scope)[0].name == "FULL"
    ]
    assert hits == ["resolve_entry_identity"], (
        f"不带 entry 段的 entry-identity 路径命中 {hits} —— "
        "该端点若挂回带 `{entry_id:path}` 的前缀，前端仍得先知道 entry_id"
    )
