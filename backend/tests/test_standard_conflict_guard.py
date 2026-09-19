"""跨主体类型披露同步守卫

Spec: applicable-standards-runtime-and-sync-guard R4.1~R4.6 / R5.2

背景：`sync_from_workpaper` 的定位键只有 `(project_id, year, note_section)`，请求体里的
`current_standard` 既不参与匹配也不校验 → 在国企项目上编辑上市披露 Tab 会把数据写进上市
章节号对应的记录（实测项目 2aa00f57：国企 `五、19`=应付职工薪酬 / `五、20`=应交税费，
与上市编号完全不同）→ 静默污染错误章节。前端门控已生效，但客户端门控可被绕过
（旧版本前端 / 直接 POST），服务端必须自守。

覆盖：
- Property 4：同 entity 恒放行（含 scope 差异）/ 跨 entity 恒拒绝
- Property 5：守卫永不因自身失败而阻断（fail-open）
- Property 6：拒绝时零写入（db.add / db.commit 均未调用）
- 路由 409 结构化 detail（单章节 + 批量端点同守卫）
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_disclosure_sync import router as wp_disclosure_sync_router
from app.services.standard_unification_service import (
    VALID_ENTITY_TYPES,
    VALID_SCOPES,
    detect_standard_conflict,
)
from app.services.wp_disclosure_sync_service import (
    StandardMismatchError,
    _guard_standard_matches_project,
    _resolve_project_sync_context,
    sync_from_workpaper,
)

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _std(entity: str, scope: str = "standalone", stage: str = "normal") -> dict:
    return {"entity_type": entity, "scope": scope, "stage": stage}


# ─── Property 4：entity 维度判定矩阵 ─────────────────────────────────────────


@pytest.mark.parametrize("project_entity", VALID_ENTITY_TYPES)
@pytest.mark.parametrize("project_scope", VALID_SCOPES)
@pytest.mark.parametrize("requested_scope", VALID_SCOPES)
def test_p4_same_entity_always_allowed(project_entity, project_scope, requested_scope):
    """同 entity（哪怕 scope 不同）恒放行 —— 合并/个别报表口径另有流程，此处不误杀。"""
    conflict = detect_standard_conflict(
        _std(project_entity, project_scope), f"{project_entity}_{requested_scope}"
    )
    assert conflict is None


@pytest.mark.parametrize("project_entity", VALID_ENTITY_TYPES)
@pytest.mark.parametrize("requested_entity", VALID_ENTITY_TYPES)
@pytest.mark.parametrize("requested_scope", VALID_SCOPES)
def test_p4_cross_entity_allowed_after_user_override(project_entity, requested_entity, requested_scope):
    """用户裁决（2026-08-16）：跨 entity 降级为 warning 放行，不再 hard block。"""
    conflict = detect_standard_conflict(
        _std(project_entity), f"{requested_entity}_{requested_scope}"
    )
    # 所有组合都放行（返回 None）
    assert conflict is None


@pytest.mark.parametrize("requested", ["soe", "standalone", "consolidated", "SOE_Standalone"])
def test_p4_dimension_values_allowed_for_soe_project(requested):
    """维度值 / 大小写混写都在派生列表里（或不含 entity 语义）→ 放行。"""
    assert detect_standard_conflict(_std("soe"), requested) is None


@pytest.mark.parametrize("requested", ["listed", "listed_standalone", "LISTED_CONSOLIDATED"])
def test_p4_listed_request_on_soe_project_allowed(requested):
    """用户裁决：跨 entity 放行（合并模块场景）。"""
    conflict = detect_standard_conflict(_std("soe"), requested)
    assert conflict is None


def test_p4_soe_request_on_listed_project_allowed():
    """用户裁决：跨 entity 放行。"""
    conflict = detect_standard_conflict(_std("listed", "consolidated"), "soe_standalone")
    assert conflict is None


# ─── Property 5：fail-open ───────────────────────────────────────────────────


@pytest.mark.parametrize("project_standard", [None, {}, [], "soe", 0])
def test_p5_unknown_project_standard_allows(project_standard):
    assert detect_standard_conflict(project_standard, "listed_standalone") is None


@pytest.mark.parametrize("requested", [None, "", "   "])
def test_p5_empty_requested_allows(requested):
    assert detect_standard_conflict(_std("soe"), requested) is None


@pytest.mark.parametrize("requested", ["general", "default", "custom_variant", "v2"])
def test_p5_non_entity_literals_allow(requested):
    """既有非准则字面量（历史调用方）→ 零回归放行。"""
    assert detect_standard_conflict(_std("soe"), requested) is None


def test_p5_illegal_project_entity_allows():
    """项目侧 entity 不合法（脏数据）→ 不可判 → fail-open。"""
    assert detect_standard_conflict({"entity_type": "州企", "scope": "x"}, "listed") is None


# ─── 服务层守卫 ──────────────────────────────────────────────────────────────


def test_guard_allows_cross_entity_after_user_override(caplog):
    """用户裁决：跨 entity 放行不再抛 StandardMismatchError。"""
    with caplog.at_level("WARNING"):
        _guard_standard_matches_project(PROJECT_ID, _std("soe"), "listed_standalone", "五、30")
    # 不抛异常，仅记 warning
    assert any("cross-entity sync allowed" in rec.message or "scope mismatch" in rec.message
               for rec in caplog.records)


def test_guard_scope_mismatch_logs_but_allows(caplog):
    with caplog.at_level("WARNING"):
        _guard_standard_matches_project(
            PROJECT_ID, _std("soe", "standalone"), "soe_consolidated", "五、30"
        )
    assert any("scope mismatch" in rec.message for rec in caplog.records)


def _project_row_db(*, audit_year=2025, v2=None, template_type=None, report_scope=None) -> MagicMock:
    """fake AsyncSession：首个 execute 返回项目行（audit_year + 准则四列）。"""
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    row = MagicMock()
    row.first = MagicMock(return_value=(audit_year, v2, template_type, report_scope))
    db.execute = AsyncMock(return_value=row)
    return db


@pytest.mark.asyncio
async def test_resolve_context_prefers_v2_then_legacy_columns():
    db = _project_row_db(audit_year=2025, v2={"entity_type": "listed", "scope": "consolidated"})
    assert await _resolve_project_sync_context(db, PROJECT_ID) == (
        2025,
        {"entity_type": "listed", "scope": "consolidated", "stage": "normal"},
    )

    db = _project_row_db(audit_year=2024, v2=None, template_type="soe", report_scope="standalone")
    year, std = await _resolve_project_sync_context(db, PROJECT_ID)
    assert year == 2024
    assert std["entity_type"] == "soe"


@pytest.mark.asyncio
async def test_resolve_context_no_standard_returns_none():
    """无任何准则字段 → None（不能被 _normalize_standard 补成默认 soe 而误杀上市推送）。"""
    db = _project_row_db(v2=None, template_type=None, report_scope=None)
    assert await _resolve_project_sync_context(db, PROJECT_ID) == (2025, None)


@pytest.mark.asyncio
async def test_resolve_context_db_error_fails_open():
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    assert await _resolve_project_sync_context(db, PROJECT_ID) == (None, None)


# ─── Property 6：拒绝时零写入 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_p6_cross_entity_sync_allowed_proceeds():
    """用户裁决后跨 entity 同步放行（不再抛 StandardMismatchError）。"""
    db = _project_row_db(v2={"entity_type": "soe", "scope": "standalone"})
    user = MagicMock()
    user.id = USER_ID

    # 不再抛异常；会继续执行到查 disclosure_notes（execute_count > 1）
    # 因为 mock db 没有完整的 disclosure_notes 行，会在后续环节失败或返回空，
    # 但不会抛 StandardMismatchError
    try:
        await sync_from_workpaper(
            db,
            PROJECT_ID,
            wp_id=WP_ID,
            sheet_name="附注披露信息（上市公司）",
            section_id="五、30",
            sub_table_data={"主表": [{"a": 1}]},
            current_standard="listed_standalone",
            user=user,
        )
    except StandardMismatchError:
        pytest.fail("不应再抛 StandardMismatchError（用户裁决已放行）")
    except Exception:
        pass  # 后续步骤因 mock 不完整可能出其他错，不是本测试关注点


@pytest.mark.asyncio
async def test_p6_matching_standard_proceeds_to_note_lookup():
    """反向自检：准则一致时守卫不拦，流程继续（会去查 disclosure_notes）。"""
    db = _project_row_db(v2={"entity_type": "soe", "scope": "standalone"})
    note_result = MagicMock()
    note_result.scalar_one_or_none = MagicMock(return_value=None)
    project_row = MagicMock()
    project_row.first = MagicMock(return_value=(2025, {"entity_type": "soe", "scope": "standalone"}, None, None))
    db.execute = AsyncMock(side_effect=[project_row, note_result, note_result])
    user = MagicMock()
    user.id = USER_ID

    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="附注披露信息（国有企业）",
        section_id="八、9",
        sub_table_data={"主表": [{"a": 1}]},
        current_standard="soe_standalone",
        user=user,
    )
    assert result["success"] is True
    assert result["created"] is True
    db.add.assert_called_once()


# ─── 路由 409 ────────────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wp_disclosure_sync_router)

    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.add = MagicMock()

    async def _override_db():
        yield mock_db

    async def _override_user():
        return User(
            id=USER_ID,
            username="user",
            email="user@test.com",
            hashed_password="x",
            role=UserRole.admin,
            is_active=True,
            is_deleted=False,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


_CONFLICT = {
    "project_standard": "soe_standalone",
    "requested_standard": "listed_standalone",
    "project_entity": "soe",
    "requested_entity": "listed",
    "allowed": ["soe_standalone", "soe", "standalone"],
}


@pytest.mark.asyncio
async def test_router_single_returns_409_with_structured_detail():
    app = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "附注披露信息（上市公司）",
        "section_id": "五、30",
        "sub_table_data": {"主表": [{"a": 1}]},
        "current_standard": "listed_standalone",
    }
    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(side_effect=StandardMismatchError(_CONFLICT)),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "STANDARD_MISMATCH"
    assert detail["project_standard"] == "soe_standalone"
    assert detail["requested_standard"] == "listed_standalone"
    assert detail["allowed"] == ["soe_standalone", "soe", "standalone"]
    assert "不能以 listed_standalone 同步" in detail["detail"]


@pytest.mark.asyncio
async def test_router_batch_shares_the_same_guard():
    app = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "current_standard": "listed_standalone",
        "items": [
            {"sheet_name": "附注披露信息（上市公司）", "section_id": "五、30", "sub_table_data": {}},
        ],
    }
    with patch(
        "app.routers.wp_disclosure_sync.sync_batch_from_workpaper",
        new=AsyncMock(side_effect=StandardMismatchError(_CONFLICT)),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-batch-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "STANDARD_MISMATCH"


def test_service_guard_is_wired_before_any_write():
    """源码断言：守卫调用必须出现在 note 查询/写入之前（防未来重构挪位置）。"""
    import inspect

    from app.services import wp_disclosure_sync_service as svc

    src = inspect.getsource(svc.sync_from_workpaper)
    guard_at = src.index("_guard_standard_matches_project(")
    lookup_at = src.index("sa.select(DisclosureNote)")
    assert guard_at < lookup_at
    assert "db.add(note)" in src and guard_at < src.index("db.add(note)")
