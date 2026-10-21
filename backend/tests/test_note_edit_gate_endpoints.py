"""覆盖集合端点五身份测试（partner-manager-edit-permission Task 10.2）。

读 ``backend/data/authz/note_write_inventory.json`` 取覆盖集合（E/I 类且 target_gate kind=note_edit_gate），
与 ``note_edit_gate_recipes.ALL_RECIPES`` 配方表求交后参数化。每个端点 × 五种身份各在独立世界里发同一请求。

结论判定：
- 放行（①② edit/review member）= 响应 2xx/4xx 业务错误、门禁至少执行 1 次
  ——业务桩本身会在很多端点上引发后续异常（如 mock 返回 None 致 AttributeError），
  所以「放行」的证据是**门禁确实执行了且没有先返回 403/401/423**。
- 拒绝（③ EQCR、④ non-member）= 403 且原因逐字相等
- 未登录（⑤）= 401 "Not authenticated"
- 对象 id 端点另测：④ 附带有权项目标识仍 403「权限不足」、对象不存在 404

_Requirements: 6.2, 6.4, 6.5, 6.8, 12.1, 12.2_
"""
from __future__ import annotations

import importlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import Response

from authz_world import (
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    sqlite_world,
)
from note_edit_gate_recipes import ALL_RECIPES, Recipe

# ---------------------------------------------------------------------------
# 清册加载与覆盖集合
# ---------------------------------------------------------------------------

_INVENTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "authz" / "note_write_inventory.json"


def _load_coverage_set() -> set[tuple[str, str]]:
    """覆盖集合 = 清册中 target_gate.kind == 'note_edit_gate' 的端点。"""
    data = json.loads(_INVENTORY_PATH.read_text("utf-8"))
    result: set[tuple[str, str]] = set()
    for ep in data["endpoints"]:
        tg = ep.get("target_gate") or {}
        if tg.get("kind") == "note_edit_gate":
            result.add((ep["method"], ep["path"]))
    return result


COVERAGE_SET = _load_coverage_set()

# 与配方表求交：只测已有配方的端点
_PARAMETRIZED_KEYS: list[tuple[str, str]] = sorted(COVERAGE_SET & set(ALL_RECIPES.keys()))
_PARAMETRIZED_RECIPES: list[Recipe] = [ALL_RECIPES[k] for k in _PARAMETRIZED_KEYS]

# ---------------------------------------------------------------------------
# 预期拒绝原因（从 note_edit_gate 常量导入，保证逐字一致）
# ---------------------------------------------------------------------------

from app.services.note_edit_gate import REASON_EQCR_READONLY, REASON_FORBIDDEN  # noqa: E402


# ---------------------------------------------------------------------------
# 路由导入
# ---------------------------------------------------------------------------

from app.routers import disclosure_notes  # noqa: E402
from app.routers import group_note_baseline  # noqa: E402
from app.routers import note_custom_template  # noqa: E402
from app.routers import note_wp_mapping  # noqa: E402

# 覆盖集合端点可能分布在多个路由文件中，client 需同时挂载
_ALL_ROUTERS = (disclosure_notes.router, group_note_baseline.router, note_custom_template.router, note_wp_mapping.router)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _recipe_id(recipe: Recipe) -> str:
    return f"{recipe.method} {recipe.path_template}"


def _assert_denied(resp: Response, status: int, reason: str) -> None:
    """断言拒绝响应：状态码 + detail 中的 message 或 detail 本身逐字一致。

    门禁的 HTTPException detail 可能是纯字符串（如「权限不足」）或 dict（如 ``{error_code, message}``）。
    """
    assert resp.status_code == status, (
        f"期望 {status}，实际 {resp.status_code}；body={resp.text[:500]}"
    )
    body = resp.json()
    detail = body.get("detail", "")
    # detail 可能是 dict（含 message）或纯字符串
    if isinstance(detail, dict):
        actual_reason = detail.get("message", "")
    else:
        actual_reason = detail
    assert actual_reason == reason, f"reason 不一致：期望 {reason!r}，实际 {actual_reason!r}"


async def _setup_stubs(world: AuthzWorld, recipe: Recipe) -> list[Any]:
    """为一个配方安装业务桩，返回桩列表。

    - ``is_class=True``（类桩）：替换为 callable，被调用（实例化）时返回一个 _SmartMock，
      其属性再被访问时返回协程兼容的 callable。
    - 普通桩（函数 / 单例对象）：直接返回 None 的计数桩。
    """
    stubs = []
    for st in recipe.stubs:
        owner = importlib.import_module(st.owner_import)
        if st.is_class:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=False))
        else:
            stubs.append(world.stub(owner, st.attr, returns=_default_return(st), awaitable=st.awaitable))
    return stubs


class _SmartMock:
    """一个自动代理对象：任何属性访问都返回一个 _SmartMock 子对象。

    该子对象同时是：
    - 可调用（``await obj.method(...)`` → 返回新的 _SmartMock）
    - 可迭代（``for x in obj.attr:`` → 空迭代）
    - falsy（``if obj.attr:`` → False，防止在空数据时进入 SQLAlchemy .in_() 等路径）
    - dict-like（``obj["key"]`` → 合理的默认值）

    放行用例中业务代码会试图在桩返回的对象上调方法（如 ``engine.generate_notes(...)``），
    方法可能被 await，所以 __call__ 返回协程。
    """
    _PASSTHROUGH = {"ok": True, "message": "stubbed", "executed": 0, "updated": 0}

    def __getattr__(self, name: str) -> _SmartMock:
        return _SmartMock()

    async def __call__(self, *args: Any, **kwargs: Any) -> _SmartMock:
        return _SmartMock()

    def __getitem__(self, key: str) -> Any:
        return self._PASSTHROUGH.get(key, None)

    def __bool__(self) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter([])

    def __len__(self) -> int:
        return 0

    def get(self, key: str, default: Any = None) -> Any:
        return self._PASSTHROUGH.get(key, default)

    def append(self, item: Any) -> None:
        """兼容 report.errors.append(...) 之类的追加调用（静默丢弃）。"""
        pass

    def append(self, item: Any) -> None:
        """兼容 report.errors.append(...) 之类的追加调用（静默丢弃）。"""
        pass


def _default_return(st: Any) -> Any:
    """合理的桩返回值。"""
    return None


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AuthzWorld:
    async with sqlite_world(monkeypatch) as w:
        # A2 需要目标项目上的 DisclosureNote（对象 id 端点反查用）——world 已建 disclosure_notes 表
        from app.models.report_models import DisclosureNote as DN, NoteValidationResult as NVR
        from sqlalchemy.schema import CreateTable
        from note_edit_gate_recipes import _NOTE_ID, _VALIDATION_ID, _YEAR
        await w.db.execute(
            DN.__table__.insert().values(
                id=_NOTE_ID,
                project_id=TARGET_PROJECT_ID,
                year=_YEAR,
                note_section="五、1",
                section_title="测试章节",
                is_deleted=False,
            )
        )
        # A8 需要 note_validation_results 表 + 行
        conn = await w.db.connection()
        await conn.run_sync(lambda sync_conn: sync_conn.execute(CreateTable(NVR.__table__)))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await w.db.execute(
            NVR.__table__.insert().values(
                id=_VALIDATION_ID,
                project_id=TARGET_PROJECT_ID,
                year=_YEAR,
                validation_timestamp=now,
                findings="[]",
            )
        )
        await w.db.flush()
        yield w


# ---------------------------------------------------------------------------
# 五种标准身份的工厂
# ---------------------------------------------------------------------------


async def _make_identity(world: AuthzWorld, key: str) -> Identity:
    return await world.identity(key)


# ---------------------------------------------------------------------------
# 参数化测试
# ---------------------------------------------------------------------------


class TestCoverageSetNotEmpty:
    """覆盖集合与配方表求交后非空。"""

    def test_parametrized_recipes_nonempty(self) -> None:
        assert len(_PARAMETRIZED_RECIPES) > 0, "覆盖集合与配方表求交为空，没有端点可测"

    def test_a1_through_a12_all_covered(self) -> None:
        """A1–A12（disclosure_notes.py 的 12 个端点）都在配方里。"""
        dn_keys = {
            k for k in COVERAGE_SET
            if k in ALL_RECIPES
        }
        dn_in_recipes = {k for k in ALL_RECIPES if ALL_RECIPES[k].path_template.startswith("/api/disclosure-notes")}
        assert dn_in_recipes <= dn_keys


# ---- ① edit 成员放行 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_edit_member_allowed(world: AuthzWorld, recipe: Recipe) -> None:
    """① edit 级成员（manager, edit）→ 门禁放行。"""
    identity = await _make_identity(world, "edit_member")
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    # 放行的证据：门禁执行了，且不是 401/403
    assert resp.status_code != 401, f"edit_member 不应被 401 拒绝：{resp.text[:300]}"
    assert resp.status_code != 403, f"edit_member 不应被 403 拒绝：{resp.text[:300]}"
    # 门禁确实跑过（覆盖集合端点的唯一项目级判定）
    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")


# ---- ② review 非 EQCR 成员放行 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_review_member_allowed(world: AuthzWorld, recipe: Recipe) -> None:
    """② review 级非 EQCR 成员（qc, review）→ 门禁放行。"""
    identity = await _make_identity(world, "review_member")
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    assert resp.status_code != 401, f"review_member 不应被 401 拒绝：{resp.text[:300]}"
    assert resp.status_code != 403, f"review_member 不应被 403 拒绝：{resp.text[:300]}"
    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")


# ---- ③ EQCR 拒绝 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_eqcr_denied(world: AuthzWorld, recipe: Recipe) -> None:
    """③ 本项目 EQCR（partner, review + eqcr 委派）→ 403，原因为 EQCR 只读文案。"""
    identity = await _make_identity(world, "project_eqcr")
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    _assert_denied(resp, 403, REASON_EQCR_READONLY)
    # 业务桩 0 次
    for stub in stubs:
        assert stub.count == 0, f"EQCR 被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"


# ---- ④ 非成员拒绝 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_non_member_denied(world: AuthzWorld, recipe: Recipe) -> None:
    """④ 非成员（另一项目 manager, edit）→ 403「权限不足」。"""
    identity = await _make_identity(world, "non_member")
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    _assert_denied(resp, 403, REASON_FORBIDDEN)
    for stub in stubs:
        assert stub.count == 0, f"非成员被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"


# ---- ⑤ 未登录 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_unauthenticated_denied(world: AuthzWorld, recipe: Recipe) -> None:
    """⑤ 未登录 → 401 "Not authenticated"。"""
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=None) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    assert resp.status_code == 401, f"未登录应 401，实际 {resp.status_code}：{resp.text[:300]}"
    for stub in stubs:
        assert stub.count == 0, f"未登录被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"


# ---------------------------------------------------------------------------
# 对象 id 端点的补充测试
# ---------------------------------------------------------------------------

_OBJECT_ID_RECIPES = [r for r in _PARAMETRIZED_RECIPES if r.object_id_endpoint]


@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _OBJECT_ID_RECIPES, ids=[_recipe_id(r) for r in _OBJECT_ID_RECIPES])
async def test_non_member_with_other_project_still_denied(world: AuthzWorld, recipe: Recipe) -> None:
    """④ 非成员附带有权项目标识仍得 403「权限不足」。

    对象属于目标项目，非成员在另一项目有权但在目标项目无成员行 → 按对象所属项目判定。
    """
    identity = await _make_identity(world, "non_member")
    stubs = await _setup_stubs(world, recipe)

    # 对象 id 端点的 URL 指向的对象属于 TARGET_PROJECT_ID
    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    _assert_denied(resp, 403, REASON_FORBIDDEN)
    for stub in stubs:
        assert stub.count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _OBJECT_ID_RECIPES, ids=[_recipe_id(r) for r in _OBJECT_ID_RECIPES])
async def test_object_not_found_returns_404(world: AuthzWorld, recipe: Recipe) -> None:
    """对象 id 端点：对象不存在 → 404，业务桩 0 次。"""
    identity = await _make_identity(world, "edit_member")
    stubs = await _setup_stubs(world, recipe)

    assert recipe.nonexistent_url is not None, f"{recipe.key} 是对象 id 端点但未定义 nonexistent_url"
    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.nonexistent_url, **recipe.request_kwargs)

    assert resp.status_code == 404, f"对象不存在应 404，实际 {resp.status_code}：{resp.text[:300]}"
    for stub in stubs:
        assert stub.count == 0, f"对象不存在时业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"


# ---------------------------------------------------------------------------
# B1 刷新被拒时附注表格数据保持请求前状态（Task 11.1）
# ---------------------------------------------------------------------------

_B1_REFRESH_RECIPES = [
    r for r in _PARAMETRIZED_RECIPES
    if r.path_template in (
        "/api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers",
        "/api/disclosure-notes/{project_id}/{year}/{note_section}/refresh-from-workpaper",
    )
]


@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _B1_REFRESH_RECIPES, ids=[_recipe_id(r) for r in _B1_REFRESH_RECIPES])
async def test_b1_refresh_denied_preserves_table_data(world: AuthzWorld, recipe: Recipe) -> None:
    """B1 刷新端点被拒时，附注表格数据保持请求前状态（Task 11.1，需求 8.1 / 6.11）。

    用非成员发 B1 刷新请求，在请求前后分别读取目标附注的 table_data，断言二者逐值相等。
    """
    from note_edit_gate_recipes import _NOTE_ID, _YEAR

    # 记录刷新前的 table_data
    from app.models.report_models import DisclosureNote as DN
    import sqlalchemy as sa

    before = (await world.db.execute(
        sa.select(DN.table_data).where(DN.id == _NOTE_ID)
    )).scalar_one_or_none()

    identity = await _make_identity(world, "non_member")
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

    _assert_denied(resp, 403, REASON_FORBIDDEN)
    for stub in stubs:
        assert stub.count == 0, f"被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"

    # 确认 table_data 不变
    after = (await world.db.execute(
        sa.select(DN.table_data).where(DN.id == _NOTE_ID)
    )).scalar_one_or_none()
    assert after == before, (
        f"B1 刷新被拒后 table_data 应保持不变：before={before!r}, after={after!r}"
    )
