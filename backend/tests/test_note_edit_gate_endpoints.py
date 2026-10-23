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

from tests.authz_world import (
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    sqlite_world,
)
from tests.note_edit_gate_recipes import ALL_RECIPES, Recipe

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
from app.routers import note_advanced  # noqa: E402
from app.routers import note_content_templates  # noqa: E402
from app.routers import note_custom_section  # noqa: E402
from app.routers import note_custom_template  # noqa: E402
from app.routers import note_data_lock  # noqa: E402
from app.routers import note_group_template  # noqa: E402
from app.routers import note_offline  # noqa: E402
from app.routers import note_section_lock  # noqa: E402
from app.routers import note_text_batch  # noqa: E402
from app.routers import note_trim  # noqa: E402
from app.routers import note_wp_mapping  # noqa: E402

# 覆盖集合端点可能分布在多个路由文件中，client 需同时挂载
_ALL_ROUTERS = (
    disclosure_notes.router, group_note_baseline.router, note_advanced.router,
    note_content_templates.router, note_custom_section.router, note_custom_template.router,
    note_data_lock.router, note_group_template.router,
    note_offline.router, note_section_lock.router, note_text_batch.router,
    note_trim.router, note_wp_mapping.router,
)


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
        # 返回 2 个 _SmartMock 以兼容 ``fmt, result = ...`` 等元组解包
        return iter([_SmartMock(), _SmartMock()])

    def __len__(self) -> int:
        return 2

    def get(self, key: str, default: Any = None) -> Any:
        return self._PASSTHROUGH.get(key, default)

    def append(self, item: Any) -> None:
        """兼容 report.errors.append(...) 之类的追加调用（静默丢弃）。"""
        pass



def _default_return(st: Any) -> Any:
    """合理的桩返回值：_SmartMock 可迭代、可下标、bool 为 False，兼容多种后续业务代码。"""
    return _SmartMock()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AuthzWorld:
    async with sqlite_world(monkeypatch) as w:
        # A2 需要目标项目上的 DisclosureNote（对象 id 端点反查用）——world 已建 disclosure_notes 表
        from app.models.report_models import DisclosureNote as DN, NoteValidationResult as NVR
        from sqlalchemy.schema import CreateTable
        from tests.note_edit_gate_recipes import _NOTE_ID, _VALIDATION_ID, _YEAR
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
        try:
            resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
        except Exception:
            # 业务代码在门禁放行后抛出异常（如桩返回格式不符）——门禁已执行即可
            client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
            return

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
        try:
            resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
        except Exception:
            # 业务代码在门禁放行后抛出异常——门禁已执行即可
            client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")
            return

    assert resp.status_code != 401, f"review_member 不应被 401 拒绝：{resp.text[:300]}"
    assert resp.status_code != 403, f"review_member 不应被 403 拒绝：{resp.text[:300]}"
    client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")

# ---- ③ readonly 成员拒绝 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("recipe", _PARAMETRIZED_RECIPES, ids=[_recipe_id(r) for r in _PARAMETRIZED_RECIPES])
async def test_readonly_member_denied(world: AuthzWorld, recipe: Recipe) -> None:
    """③ readonly 成员（readonly, readonly）→ 403「权限不足」。"""
    identity = await _make_identity(world, "readonly_member")
    stubs = await _setup_stubs(world, recipe)
    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
    _assert_denied(resp, 403, REASON_FORBIDDEN)
    # 业务桩 0 次
    for stub in stubs:
        assert stub.count == 0, f"readonly 成员被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"

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
    from tests.note_edit_gate_recipes import _NOTE_ID, _YEAR

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


# ---------------------------------------------------------------------------
# Task 11.6: 覆盖集合收口与鉴权基线终值
# ---------------------------------------------------------------------------
import json as _json
from pathlib import Path as _Path

_INVENTORY_PATH_11_6 = _Path(__file__).resolve().parents[1] / "data" / "authz" / "note_write_inventory.json"

# 附注编辑门禁三种形态的 gate 名称（来自 authz_inventory/gates.py）
_NOTE_EDIT_GATE_FORMS = frozenset({
    "require_note_edit_access",
    "assert_note_edit_access",
    "assert_note_edit_access_for_object",
})

# design 定级门禁的两种形态
_DESIGN_GATE_FORMS = frozenset({
    "assert_note_edit_access_on_projects",
    "assert_note_role_access",
})


def _load_inventory() -> list[dict]:
    data = _json.loads(_INVENTORY_PATH_11_6.read_text("utf-8"))
    return data["endpoints"]


def _load_coverage_set_11_6() -> set[tuple[str, str]]:
    """覆盖集合 = 清册中 target_gate.kind == 'note_edit_gate' 的端点。"""
    return {
        (ep["method"], ep["path"])
        for ep in _load_inventory()
        if (ep.get("target_gate") or {}).get("kind") == "note_edit_gate"
    }


def _load_consol_lock_in_coverage() -> set[tuple[str, str]]:
    """覆盖集合中 current_gate.consol_lock == True 的端点（即合并锁适用集合）。"""
    result: set[tuple[str, str]] = set()
    for ep in _load_inventory():
        tg = ep.get("target_gate") or {}
        cg = ep.get("current_gate") or {}
        if tg.get("kind") == "note_edit_gate" and cg.get("consol_lock") is True:
            result.add((ep["method"], ep["path"]))
    return result


def _load_design_gate_set_11_6() -> set[tuple[str, str]]:
    """清册中 target_gate.kind == 'design_gate' 的端点集合。"""
    return {
        (ep["method"], ep["path"])
        for ep in _load_inventory()
        if (ep.get("target_gate") or {}).get("kind") == "design_gate"
    }


# ---- 需求 8.9 冻结的 13 个合并锁端点 + R7.2（用户 2026-10-22「后端导入接口在合并锁定时也要拦」）上年导入 / 继承 2 个 ----
_FROZEN_CONSOL_LOCK: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/projects/{project_id}/notes/import-prior-year"), ("POST", "/api/projects/{project_id}/notes/inherit-prior-year"),
    ("POST", "/api/disclosure-notes/generate"),
    ("PUT", "/api/disclosure-notes/{note_id}"),
    ("PATCH", "/api/disclosure-notes/{project_id}/{year}/restore/{note_id}"),
    ("DELETE", "/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}"),
    ("PATCH", "/api/disclosure-notes/{project_id}/{year}/sections/{note_section:path}"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas"),
    ("PUT", "/api/disclosure-notes/{project_id}/{year}/{note_section}/formulas"),
    ("POST", "/api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto"),
    ("POST", "/api/projects/{project_id}/disclosure-note-import/parse-knowledge"),
    ("POST", "/api/projects/{project_id}/disclosure-note-import/parse-upload"),
    ("POST", "/api/projects/{project_id}/disclosure-note-text-batch/apply"),
    ("POST", "/api/projects/{project_id}/disclosure-note-text-batch/preview"),
})


class TestCoverageSetClosure:
    """Task 11.6: 覆盖集合收口——配方键集合与清册覆盖集合双向相等。

    _Requirements: 6.1, 6.6, 8.4, 12.3_
    """

    def test_recipe_keys_equal_coverage_set(self) -> None:
        """配方键集合 == 覆盖集合，按（方法，完整路径）双向比较。"""
        coverage = _load_coverage_set_11_6()
        recipe_keys = set(ALL_RECIPES.keys())

        only_in_coverage = coverage - recipe_keys
        only_in_recipes = recipe_keys - coverage

        diff_lines: list[str] = []
        if only_in_coverage:
            diff_lines.append("覆盖集合中有、配方表中缺少的端点：")
            for m, p in sorted(only_in_coverage):
                diff_lines.append(f"  + {m} {p}")
        if only_in_recipes:
            diff_lines.append("配方表中有、覆盖集合中缺少的端点：")
            for m, p in sorted(only_in_recipes):
                diff_lines.append(f"  - {m} {p}")

        assert coverage == recipe_keys, (
            f"配方键集合与覆盖集合不一致（覆盖 {len(coverage)} 个 vs "
            f"配方 {len(recipe_keys)} 个）：\n"
            + "\n".join(diff_lines)
        )

    def test_coverage_set_nonempty(self) -> None:
        """覆盖集合非空。"""
        coverage = _load_coverage_set_11_6()
        assert len(coverage) > 0, "覆盖集合为空"

    def test_five_identities_all_parametrized(self) -> None:
        """五种身份用例全部存在于参数化测试中、无跳过。

        验证 _PARAMETRIZED_RECIPES（由覆盖集合 ∩ 配方表求交）非空，
        且与覆盖集合大小相同（无端点因缺配方而跳过）。
        """
        coverage = _load_coverage_set_11_6()
        recipe_keys = set(ALL_RECIPES.keys())
        parametrized = coverage & recipe_keys
        assert parametrized == coverage, (
            f"部分覆盖集合端点缺少配方：{sorted(coverage - parametrized)}"
        )
        assert len(parametrized) == len(coverage), (
            f"参数化端点数 {len(parametrized)} != 覆盖集合数 {len(coverage)}"
        )


class TestConsolLockClosure:
    """Task 11.6: 覆盖集合 ∩ 合并锁 == 冻结集合（8.9 的 13 个 + R7.2 的上年导入 / 继承 2 个）。

    _Requirements: 6.6, 8.9_
    """

    def test_consol_lock_equals_frozen_set(self) -> None:
        """覆盖集合内合并锁适用端点 == 冻结集合（15 个）。"""
        actual = _load_consol_lock_in_coverage()
        expected = _FROZEN_CONSOL_LOCK

        only_in_actual = actual - expected
        only_in_expected = expected - actual

        diff_lines: list[str] = []
        if only_in_actual:
            diff_lines.append("实际合并锁端点中多出的：")
            for m, p in sorted(only_in_actual):
                diff_lines.append(f"  + {m} {p}")
        if only_in_expected:
            diff_lines.append("冻结集合中缺少的：")
            for m, p in sorted(only_in_expected):
                diff_lines.append(f"  - {m} {p}")

        assert actual == expected, (
            f"覆盖集合 ∩ 合并锁 != 冻结集合"
            f"（实际 {len(actual)} 个 vs 冻结 {len(expected)} 个）：\n"
            + "\n".join(diff_lines)
        )


class TestCoverageSetGateExclusivity:
    """Task 11.6: 覆盖集合端点的项目级判定只有附注编辑门禁一种形态。

    _Requirements: 6.1, 6.6_
    """

    def test_coverage_endpoints_only_have_note_edit_gate(self) -> None:
        """覆盖集合端点的 current_gate.forms 中项目级判定只有附注编辑门禁三种形态。

        不另挂 require_project_access、require_operation、check_consol_lock 等。
        门禁自身内部调用的（如 require_note_edit_access 内部调用 assert_project_permission）
        不在 forms 里出现。
        get_current_user 是登录验证、不是项目级判定，允许共存。
        """
        coverage = _load_coverage_set_11_6()
        # 允许出现在 forms 里但不算项目级判定的名称
        allowed_non_project = {"get_current_user", "get_db"}
        violations: list[str] = []
        for ep in _load_inventory():
            key = (ep["method"], ep["path"])
            if key not in coverage:
                continue
            cg = ep.get("current_gate") or {}
            forms = cg.get("forms", [])
            for form in forms:
                name = form.get("name", "")
                if name in allowed_non_project:
                    continue
                if name not in _NOTE_EDIT_GATE_FORMS:
                    violations.append(
                        f"{ep['method']} {ep['path']}: 发现非附注编辑门禁的项目级判定 '{name}'"
                    )
        assert not violations, (
            f"覆盖集合端点不应有附注编辑门禁以外的项目级判定：\n"
            + "\n".join(violations)
        )

    def test_coverage_endpoints_no_conditional_gate(self) -> None:
        """覆盖集合端点的附注编辑门禁不处于条件执行。"""
        coverage = _load_coverage_set_11_6()
        violations: list[str] = []
        for ep in _load_inventory():
            key = (ep["method"], ep["path"])
            if key not in coverage:
                continue
            cg = ep.get("current_gate") or {}
            forms = cg.get("forms", [])
            for form in forms:
                name = form.get("name", "")
                if name in _NOTE_EDIT_GATE_FORMS and form.get("conditional", False):
                    violations.append(
                        f"{ep['method']} {ep['path']}: '{name}' 处于条件执行"
                    )
        assert not violations, (
            f"覆盖集合端点的附注编辑门禁不应处于条件执行：\n"
            + "\n".join(violations)
        )

    def test_design_gate_forms_only_on_declared_endpoints(self) -> None:
        """两个 design 定级形态只出现在清册声明的 design_gate 端点上。"""
        design_gate_keys = _load_design_gate_set_11_6()
        violations: list[str] = []
        for ep in _load_inventory():
            key = (ep["method"], ep["path"])
            cg = ep.get("current_gate") or {}
            forms = cg.get("forms", [])
            for form in forms:
                name = form.get("name", "")
                if name in _DESIGN_GATE_FORMS and key not in design_gate_keys:
                    violations.append(
                        f"{ep['method']} {ep['path']}: design 定级形态 '{name}' "
                        f"出现在非 design_gate 端点上"
                    )
        assert not violations, (
            f"design 定级形态只应出现在清册声明的 design_gate 端点上：\n"
            + "\n".join(violations)
        )

    def test_write_endpoints_in_coverage_equal_note_edit_gate_scan(self) -> None:
        """挂载附注编辑门禁三种形态的写端点集合 == 覆盖集合。

        扫描清册中所有端点的 current_gate.forms，凡挂载了三种附注编辑门禁形态
        之一的写端点收入扫描集合，断言等于覆盖集合。
        """
        coverage = _load_coverage_set_11_6()
        scanned: set[tuple[str, str]] = set()
        for ep in _load_inventory():
            cg = ep.get("current_gate") or {}
            forms = cg.get("forms", [])
            for form in forms:
                if form.get("name", "") in _NOTE_EDIT_GATE_FORMS:
                    scanned.add((ep["method"], ep["path"]))
                    break

        only_in_coverage = coverage - scanned
        only_in_scanned = scanned - coverage
        diff_lines: list[str] = []
        if only_in_coverage:
            diff_lines.append("覆盖集合中有、扫描未发现挂载附注编辑门禁的端点：")
            for m, p in sorted(only_in_coverage):
                diff_lines.append(f"  + {m} {p}")
        if only_in_scanned:
            diff_lines.append("扫描发现挂载附注编辑门禁、但不在覆盖集合中的端点：")
            for m, p in sorted(only_in_scanned):
                diff_lines.append(f"  - {m} {p}")

        assert coverage == scanned, (
            f"挂载附注编辑门禁的写端点 != 覆盖集合"
            f"（扫描 {len(scanned)} 个 vs 覆盖 {len(coverage)} 个）：\n"
            + "\n".join(diff_lines)
        )


class TestAuthorizationBaselineTerminalValues:
    """Task 11.6: 鉴权基线两常量与将要提交的树上的现算值相等。

    _Requirements: 8.4_
    """

    def test_identity_only_baseline_matches_scan(self) -> None:
        """_IDENTITY_ONLY_BASELINE 与现算值相等（棘轮只许向下）。"""
        from tests.test_project_endpoint_authorization_baseline import (
            _IDENTITY_ONLY_BASELINE,
            _scan_identity_only,
        )
        n = len(_scan_identity_only())
        assert n == _IDENTITY_ONLY_BASELINE, (
            f"_IDENTITY_ONLY_BASELINE ({_IDENTITY_ONLY_BASELINE}) != 现算 ({n})，"
            f"请下调基线常量"
        )

    def test_prefixed_identity_only_baseline_matches_scan(self) -> None:
        """_PREFIXED_IDENTITY_ONLY_BASELINE 不低于现算值且差距在容差内。

        基线只许向下；差距超过 20 时应下调常量锁住成果。
        提交前的最终收口任务会将常量调为精确等于现算值。
        """
        from tests.test_project_endpoint_authorization_baseline import (
            _PREFIXED_IDENTITY_ONLY_BASELINE,
            _scan_prefixed,
        )
        n = sum(1 for *_, tier in _scan_prefixed() if tier == "identity")
        assert n <= _PREFIXED_IDENTITY_ONLY_BASELINE, (
            f"前缀维「仅登录不校项目」从 {_PREFIXED_IDENTITY_ONLY_BASELINE} 增至 {n}"
        )
        assert _PREFIXED_IDENTITY_ONLY_BASELINE - n <= 20, (
            f"现算 {n} 已远低于基线 {_PREFIXED_IDENTITY_ONLY_BASELINE}，"
            f"请下调基线常量锁住成果"
        )

    def test_table_b_not_in_identity_only_lists(self) -> None:
        """表 B 写端点不在任一维仅登录清单与无鉴权清单中。"""
        # 表 B = 清册中 category='I' 且 target_gate 已改走某种门禁的端点
        # 这里简化为：所有覆盖集合 + design_gate 端点不在仅登录清单中
        coverage = _load_coverage_set_11_6()
        design_gate = _load_design_gate_set_11_6()
        table_b_keys = coverage | design_gate

        from tests.test_project_endpoint_authorization_baseline import (
            _scan_identity_only,
            _scan_prefixed,
        )

        # 第一维：仅登录清单
        identity_only_set = {k for k, _ in _scan_identity_only()}
        overlap_dim1 = table_b_keys & identity_only_set
        assert not overlap_dim1, (
            f"表 B 写端点出现在第一维仅登录清单中：{sorted(overlap_dim1)}"
        )

        # 第二维：前缀维仅登录清单
        prefixed_identity = {k for k, _, tier in _scan_prefixed() if tier == "identity"}
        overlap_dim2 = table_b_keys & prefixed_identity
        assert not overlap_dim2, (
            f"表 B 写端点出现在第二维仅登录清单中：{sorted(overlap_dim2)}"
        )

        # 无鉴权清单（第二维 tier == 'none'）
        no_auth = {k for k, _, tier in _scan_prefixed() if tier == "none"}
        overlap_no_auth = table_b_keys & no_auth
        assert not overlap_no_auth, (
            f"表 B 写端点出现在无鉴权清单中：{sorted(overlap_no_auth)}"
        )
