"""Property 10: 判定查询与写端点结论一致（partner-manager-edit-permission Task 13.3）。

需求 12.4 的八种身份情形 × 覆盖集合全部端点（参数化穷举）：
- 不能编辑时查询原因与写请求拒绝原因逐字相同
- 查询前后业务数据不变
- EQCR 判定出错时查询返回失败响应，不返回「能编辑」

_Requirements: 10.1, 12.4_
"""
from __future__ import annotations

import importlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.schema import CreateTable

from authz_world import (
    IDENTITY_LABELS,
    STANDARD_IDENTITIES,
    SUPPLEMENTARY_IDENTITIES,
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    sqlite_world,
)
from note_edit_gate_recipes import ALL_RECIPES, Recipe, _NOTE_ID, _VALIDATION_ID, _YEAR

from app.services.note_edit_gate import (
    REASON_EQCR_READONLY,
    REASON_FORBIDDEN,
    REASON_OPERATION_DENIED,
)

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
_PARAMETRIZED_KEYS: list[tuple[str, str]] = sorted(COVERAGE_SET & set(ALL_RECIPES.keys()))
_PARAMETRIZED_RECIPES: list[Recipe] = [ALL_RECIPES[k] for k in _PARAMETRIZED_KEYS]

# ---------------------------------------------------------------------------
# 路由导入（查询端点 + 全部覆盖集合路由）
# ---------------------------------------------------------------------------

from app.routers import disclosure_notes  # noqa: E402
from app.routers import group_note_baseline  # noqa: E402
from app.routers import note_advanced  # noqa: E402
from app.routers import note_content_templates  # noqa: E402
from app.routers import note_custom_section  # noqa: E402
from app.routers import note_custom_template  # noqa: E402
from app.routers import note_data_lock  # noqa: E402
from app.routers import note_edit_permission  # noqa: E402
from app.routers import note_group_template  # noqa: E402
from app.routers import note_offline  # noqa: E402
from app.routers import note_section_lock  # noqa: E402
from app.routers import note_text_batch  # noqa: E402
from app.routers import note_trim  # noqa: E402
from app.routers import note_wp_mapping  # noqa: E402

# 覆盖集合写端点 + 查询端点
_ALL_ROUTERS = (
    note_edit_permission.router,
    disclosure_notes.router, group_note_baseline.router, note_advanced.router,
    note_content_templates.router, note_custom_section.router, note_custom_template.router,
    note_data_lock.router, note_group_template.router,
    note_offline.router, note_section_lock.router, note_text_batch.router,
    note_trim.router, note_wp_mapping.router,
)

_QUERY_URL = f"/api/projects/{TARGET_PROJECT_ID}/disclosure-notes/edit-permission"

# ---------------------------------------------------------------------------
# 八种身份 = 五种标准 + 三种补充
# ---------------------------------------------------------------------------

ALL_IDENTITY_KEYS: tuple[str, ...] = (*STANDARD_IDENTITIES, *SUPPLEMENTARY_IDENTITIES)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


class _SmartMock:
    """同 test_note_edit_gate_endpoints.py 的业务桩代理对象。"""

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
        return iter([_SmartMock(), _SmartMock()])

    def __len__(self) -> int:
        return 2

    def get(self, key: str, default: Any = None) -> Any:
        return self._PASSTHROUGH.get(key, default)


def _default_return(st: Any) -> Any:
    return None


async def _setup_stubs(world: AuthzWorld, recipe: Recipe) -> list[Any]:
    """为一个配方安装业务桩。"""
    from note_edit_gate_recipes import StubTarget

    stubs = []
    for st in recipe.stubs:
        owner = importlib.import_module(st.owner_import)
        if st.is_class:
            stubs.append(world.stub(owner, st.attr, returns=_SmartMock(), awaitable=False))
        else:
            stubs.append(world.stub(owner, st.attr, returns=_default_return(st), awaitable=st.awaitable))
    return stubs


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        # A2 需要目标项目上的 DisclosureNote（对象 id 端点反查用）
        from app.models.report_models import DisclosureNote as DN, NoteValidationResult as NVR

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


def _recipe_id(recipe: Recipe) -> str:
    return f"{recipe.method} {recipe.path_template}"


def _extract_reason(resp_json: dict) -> str | None:
    """从 403/423 响应体提取拒绝原因（与查询端点的 reason 字段对拍）。"""
    detail = resp_json.get("detail", "")
    if isinstance(detail, dict):
        return detail.get("message", "")
    return detail


# ═══════════════════════════════════════════════════════════════════════════════
# Property 10: 判定查询与写端点结论一致
# ═══════════════════════════════════════════════════════════════════════════════


# 能通过查询端点自身 readonly 鉴权（会得到 200 + can_edit 判定结果的身份）
_QUERY_OK_DENIED: dict[str, str] = {
    "readonly_member": REASON_FORBIDDEN,
    "project_eqcr": REASON_EQCR_READONLY,
    "qc_review_member": REASON_OPERATION_DENIED,
}

# 查询端点自身 readonly 鉴权就拒绝的身份（非成员得 403；前端视同不能编辑）
_QUERY_SELF_DENIED_KEYS: tuple[str, ...] = ("non_member",)

_ALLOWED_IDENTITY_KEYS: tuple[str, ...] = ("edit_member", "review_member", "admin_non_member")

_QUERY_OK_DENIED_PAIRS = [(k, r) for k in _QUERY_OK_DENIED for r in _PARAMETRIZED_RECIPES]
_QUERY_SELF_DENIED_PAIRS = [(k, r) for k in _QUERY_SELF_DENIED_KEYS for r in _PARAMETRIZED_RECIPES]
_ALLOWED_PAIRS = [(k, r) for k in _ALLOWED_IDENTITY_KEYS for r in _PARAMETRIZED_RECIPES]


# ---------------------------------------------------------------------------
# 10a: 能通过查询自身鉴权但不能编辑时，查询原因与写请求拒绝原因逐字相同
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_key, recipe",
    _QUERY_OK_DENIED_PAIRS,
    ids=[f"{k}-{_recipe_id(r)}" for k, r in _QUERY_OK_DENIED_PAIRS],
)
async def test_query_reason_matches_write_denial(
    world: AuthzWorld, identity_key: str, recipe: Recipe,
) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """不能编辑时（成员），查询端点返回的 reason 与写请求的 403 detail 逐字相同。"""
    identity = await world.identity(identity_key)
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        # 1. 查询端点（readonly 鉴权通过，判定返回 can_edit=False）
        query_resp = await client.request("GET", _QUERY_URL)
        assert query_resp.status_code == 200, (
            f"查询端点应返回 200，实际 {query_resp.status_code}：{query_resp.text[:300]}"
        )
        query_data = query_resp.json().get("data", query_resp.json())
        assert query_data["can_edit"] is False, (
            f"身份 {identity_key} 不应能编辑，查询结果={query_data}"
        )
        query_reason = query_data["reason"]

        # 2. 写端点
        write_resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

        # 3. 写请求必须被拒绝（403）
        assert write_resp.status_code == 403, (
            f"身份 {identity_key} 写端点应被 403 拒绝，实际 {write_resp.status_code}：{write_resp.text[:300]}"
        )
        write_reason = _extract_reason(write_resp.json())

        # 4. 原因逐字相同
        assert query_reason == write_reason, (
            f"原因不一致（身份 {identity_key}）：查询 {query_reason!r} ≠ 写 {write_reason!r}"
        )

    # 5. 业务桩 0 次（拒绝时不执行业务）
    for stub in stubs:
        assert stub.count == 0, (
            f"被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"
        )


# ---------------------------------------------------------------------------
# 10a-2: 非成员 — 查询自身 readonly 鉴权拒绝（403），写请求同样 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_key, recipe",
    _QUERY_SELF_DENIED_PAIRS,
    ids=[f"{k}-{_recipe_id(r)}" for k, r in _QUERY_SELF_DENIED_PAIRS],
)
async def test_non_member_query_denied_write_also_denied(
    world: AuthzWorld, identity_key: str, recipe: Recipe,
) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """非成员：查询端点自身 readonly 鉴权返回 403，写请求同样 403，原因都是「权限不足」。"""
    identity = await world.identity(identity_key)
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        # 1. 查询端点（readonly 鉴权拒绝非成员）
        query_resp = await client.request("GET", _QUERY_URL)
        assert query_resp.status_code == 403, (
            f"非成员查询应被 403 拒绝，实际 {query_resp.status_code}：{query_resp.text[:300]}"
        )
        query_reason = _extract_reason(query_resp.json())

        # 2. 写端点
        write_resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)

        # 3. 写请求也 403
        assert write_resp.status_code == 403, (
            f"非成员写端点应被 403 拒绝，实际 {write_resp.status_code}：{write_resp.text[:300]}"
        )
        write_reason = _extract_reason(write_resp.json())

        # 4. 两边原因都是「权限不足」
        assert query_reason == REASON_FORBIDDEN, (
            f"非成员查询原因应为「{REASON_FORBIDDEN}」，实际 {query_reason!r}"
        )
        assert write_reason == REASON_FORBIDDEN, (
            f"非成员写原因应为「{REASON_FORBIDDEN}」，实际 {write_reason!r}"
        )

    # 5. 业务桩 0 次
    for stub in stubs:
        assert stub.count == 0, (
            f"非成员被拒后业务桩 {stub.target} 不应被调用，实际 {stub.count} 次"
        )


# ---------------------------------------------------------------------------
# 10b: 能编辑时，查询返回 can_edit=True 且写请求不被 403/401 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_key, recipe",
    _ALLOWED_PAIRS,
    ids=[f"{k}-{_recipe_id(r)}" for k, r in _ALLOWED_PAIRS],
)
async def test_query_allows_when_write_allowed(
    world: AuthzWorld, identity_key: str, recipe: Recipe,
) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """能编辑时，查询返回 can_edit=True，写端点不返回 403/401。"""
    identity = await world.identity(identity_key)
    stubs = await _setup_stubs(world, recipe)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        # 1. 查询端点
        query_resp = await client.request("GET", _QUERY_URL)
        assert query_resp.status_code == 200, (
            f"查询端点应返回 200，实际 {query_resp.status_code}：{query_resp.text[:300]}"
        )
        query_data = query_resp.json().get("data", query_resp.json())
        assert query_data["can_edit"] is True, (
            f"身份 {identity_key} 应能编辑，查询结果={query_data}"
        )

        # 2. 写端点
        try:
            write_resp = await client.request(recipe.method, recipe.url, **recipe.request_kwargs)
        except Exception:
            # 业务代码在门禁放行后抛出异常——门禁已执行即可
            return

    # 3. 写端点不应返回 401/403
    assert write_resp.status_code != 401, (
        f"身份 {identity_key} 写端点不应被 401 拒绝：{write_resp.text[:300]}"
    )
    assert write_resp.status_code != 403, (
        f"身份 {identity_key} 写端点不应被 403 拒绝：{write_resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# 10c: 查询前后业务数据不变
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_key",
    [k for k in ALL_IDENTITY_KEYS if k != "archived_edit_member"],
    ids=[k for k in ALL_IDENTITY_KEYS if k != "archived_edit_member"],
)
async def test_query_does_not_modify_data(world: AuthzWorld, identity_key: str) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """判定查询前后附注数据不变。"""
    from sqlalchemy import select, func
    from app.models.report_models import DisclosureNote

    identity = await world.identity(identity_key)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        # 查询前计数
        count_before = (await world.db.execute(select(func.count(DisclosureNote.id)))).scalar() or 0

        # 发送查询请求
        await client.request("GET", _QUERY_URL)

        # 查询后计数
        await world.db.flush()
        count_after = (await world.db.execute(select(func.count(DisclosureNote.id)))).scalar() or 0

    assert count_before == count_after, (
        f"查询前后附注行数不一致：{count_before} → {count_after}"
    )


# ---------------------------------------------------------------------------
# 10d: EQCR 判定出错时查询返回失败响应，不返回「能编辑」
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_eqcr_error_returns_failure(world: AuthzWorld) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """EQCR 判定出错时查询不返回 can_edit=True：要么 5xx 要么异常冒泡。"""
    import app.services.eqcr_resolver as eqcr_mod

    identity = await world.edit_member()

    # 注入 EQCR 判定异常（在下一层 _count_project_eqcr_assignments）
    async def _boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("EQCR judgment simulated failure")

    world.monkeypatch.setattr(eqcr_mod, "_count_project_eqcr_assignments", _boom)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        try:
            resp = await client.request("GET", _QUERY_URL)
        except Exception:
            # 异常冒泡到客户端（ASGI 传输不经中间件的 500 包装）= 非成功 = 不按能编辑处理
            return

    # 如果返回了响应（中间件包装成 500）：不能是 can_edit=True
    assert resp.status_code >= 400, (
        f"EQCR 出错应返回失败响应，实际 {resp.status_code}：{resp.text[:300]}"
    )
    body = resp.json()
    data = body.get("data", body)
    assert data.get("can_edit") is not True, "EQCR 判定出错时不应返回 can_edit=True"


# ---------------------------------------------------------------------------
# 10e: 已归档项目 — 查询返回不能编辑 + 归档原因
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_archived_project_returns_not_editable(world: AuthzWorld) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """已归档项目上的成员，查询返回 can_edit=False 且 reason 包含归档信息。"""
    identity = await world.archived_edit_member()

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request("GET", _QUERY_URL)

    assert resp.status_code == 200, (
        f"查询端点应返回 200，实际 {resp.status_code}：{resp.text[:300]}"
    )
    data = resp.json().get("data", resp.json())
    assert data["can_edit"] is False, f"已归档项目应不能编辑，查询结果={data}"
    assert data["reason"] is not None, "已归档项目的拒绝原因不应为空"


# ---------------------------------------------------------------------------
# 10f: 未登录 — 查询返回 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_unauthenticated_returns_401(world: AuthzWorld) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """未登录用户查询返回 401。"""
    async with world.client(*_ALL_ROUTERS, user=None) as client:
        resp = await client.request("GET", _QUERY_URL)

    assert resp.status_code == 401, (
        f"未登录应返回 401，实际 {resp.status_code}：{resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# 10g: is_eqcr 一律给出
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_key",
    [k for k in ALL_IDENTITY_KEYS if k != "archived_edit_member"],
)
async def test_query_always_includes_is_eqcr(world: AuthzWorld, identity_key: str) -> None:
    # Feature: partner-manager-edit-permission, Property 10: 判定查询与写端点结论一致
    """查询响应一律包含 is_eqcr 字段（布尔值）。"""
    identity = await world.identity(identity_key)

    async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
        resp = await client.request("GET", _QUERY_URL)

    if resp.status_code == 200:
        data = resp.json().get("data", resp.json())
        assert "is_eqcr" in data, f"响应缺少 is_eqcr 字段：{data}"
        assert isinstance(data["is_eqcr"], bool), (
            f"is_eqcr 应为布尔值，实际 {type(data['is_eqcr']).__name__}"
        )

        # EQCR 身份的 is_eqcr 应为 True
        if identity_key == "project_eqcr":
            assert data["is_eqcr"] is True, "project_eqcr 身份的 is_eqcr 应为 True"
        # 非 EQCR 成员的 is_eqcr 应为 False
        elif identity_key in ("edit_member", "review_member", "readonly_member", "qc_review_member"):
            assert data["is_eqcr"] is False, (
                f"身份 {identity_key} 的 is_eqcr 应为 False"
            )
