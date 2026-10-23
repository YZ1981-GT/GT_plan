"""Task 1.4 / ADR-FMC-02：底稿公式端点 save_formula 对非 wp kind 的纵深防御。

验收判据（tasks.md Task 1.4）：后端 `save_formula` 拒收非 wp kind（含只读投影伪标记）。

两层覆盖：
  1) 单元：`_reject_non_wp_kind` 纯函数对各 kind / 伪标记的放行 / 拒收。
  2) 端点：AsyncClient 对非 wp kind / 伪标记请求返 403，且对 wp / 省略 kind 放行到后续
     求值（反向断言：未注入违规时不误拒）。

变异反证（单元级）：若把 `_reject_non_wp_kind` 改成「恒放行」（删掉守卫），
`test_mutant_pass_through_would_accept_non_wp` 坐实非 wp kind 会被接受（即守卫失效即打红）；
生产函数对同一输入抛 403（反向断言）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.deps import get_current_user
from app.models.workpaper_models import WpFormula
from app.routers.wp_formula import (
    FormulaSaveRequest,
    _reject_non_wp_kind,
    router as wp_formula_router,
)
from app.services.wp_formula_service import WpFormulaService


# ─────────────────────────── 单元：_reject_non_wp_kind ───────────────────────────

def _req(**kw) -> FormulaSaveRequest:
    base = dict(
        sheet_name="审定表E1-1",
        target_cell="B5",
        expression="WP('D1','B5')",
        year=2025,
    )
    base.update(kw)
    return FormulaSaveRequest(**base)


def test_reject_passes_when_kind_omitted():
    # 省略 kind（前端 wp 行默认不带）→ 放行（不抛）。
    _reject_non_wp_kind(_req())


def test_reject_passes_when_kind_wp():
    _reject_non_wp_kind(_req(kind="wp"))
    _reject_non_wp_kind(_req(kind="WP"))  # 大小写不敏感


@pytest.mark.parametrize("bad_kind", ["surfaced", "extraction", "report", "note", "tb_detail"])
def test_reject_403_for_non_wp_kind(bad_kind):
    with pytest.raises(HTTPException) as ei:
        _reject_non_wp_kind(_req(kind=bad_kind))
    assert ei.value.status_code == 403
    assert ei.value.detail["error_code"] == "FORMULA_NON_WP_KIND_REJECTED"


@pytest.mark.parametrize(
    "marker_field,value",
    [
        ("target_cell", "E1-surfaced-tb-check"),
        ("target_cell", "tierB-D6-1-tb-amount"),
        ("sheet_name", "F2-surfaced-F2-3-0"),
        ("sheet_name", "tierB-x"),
    ],
)
def test_reject_403_for_readonly_projection_marker(marker_field, value):
    # 即便没带 kind，只读投影伪标记（-surfaced- / tierB-）出现在 target_cell/sheet_name 即拒。
    with pytest.raises(HTTPException) as ei:
        _reject_non_wp_kind(_req(**{marker_field: value}))
    assert ei.value.status_code == 403
    assert ei.value.detail["error_code"] == "FORMULA_READONLY_PROJECTION_REJECTED"


def test_reject_allows_normal_wp_target():
    # 正常 wp 目标（真实 A1 单元 + 中文 sheet 名）不被误拒（反向断言）。
    _reject_non_wp_kind(_req(sheet_name="货币资金审定表E1-1", target_cell="B7"))
    _reject_non_wp_kind(_req(sheet_name="审定表", target_cell="AB12", kind="wp"))


def test_mutant_pass_through_would_accept_non_wp():
    """变异反证：恒放行的变异体会接受非 wp kind（守卫删掉即打红）；生产函数拒收（反向断言）。"""

    def mutant_always_pass(_body: FormulaSaveRequest) -> None:
        return None  # 删掉守卫 = 恒放行

    bad = _req(kind="surfaced")
    # 变异体：不抛（错误地接受非 wp kind）。
    assert mutant_always_pass(bad) is None
    # 生产：拒收（反向断言）。
    with pytest.raises(HTTPException):
        _reject_non_wp_kind(bad)


# ─────────────────────────── 端点：save_formula 403 ───────────────────────────

class _FakeUser:
    id = uuid.uuid4()
    is_active = True


@pytest.fixture(autouse=True)
def _stub_wp_ownership():
    with patch.object(
        WpFormulaService, "_verify_wp_ownership", new=AsyncMock(return_value=True)
    ):
        yield


@pytest.fixture(autouse=True)
def _stub_project_authz():
    """隔离项目级鉴权（formula-manager-closure Task 5.2 / ADR-FMC-06）：本测试聚焦
    **非 wp kind 纵深防御**，用 `_FakeUser` 桩（无 `.role`）+ mock `_load_wp` + 只建
    `wp_formula` 表。Task 5.2 的 `_authorize_wp_project` 会查 `projects`/`project_users`
    且读 `user.role`，对本桩环境必崩。项目级越权由 `test_fm_p0_05_cross_project_idor`
    专测覆盖，此处桩成放行以保持对 kind 防御的聚焦。"""
    with patch(
        "app.routers.wp_formula._authorize_wp_project", new=AsyncMock(return_value=None)
    ):
        yield


@pytest.fixture(autouse=True)
def _stub_ref_template_type():
    """隔离引用校验口径（spec formula-fetch-and-wp-generation-defect-closure R6）：请求不带 template_type 时
    端点按底稿所属项目查 `projects.template_type`，本测试只建 `wp_formula` 表 ⇒ 桩成原缺省 soe。
    口径解析本身由 `test_wp_formula_ref_template_type` 用真 projects 行覆盖。"""
    with patch(
        "app.routers.wp_formula._resolve_ref_template_type", new=AsyncMock(return_value="soe")
    ):
        yield


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_app(session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(wp_formula_router)

    async def _db():
        yield session

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return app


async def _save(client: AsyncClient, wp_id, payload):
    return await client.put(f"/api/workpapers/{wp_id}/formulas", json=payload)


@pytest.mark.anyio
async def test_save_formula_endpoint_rejects_non_wp_kind_and_accepts_wp():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: WpFormula.__table__.create(sync_conn, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()

    async with factory() as session:
        app = _make_app(session)
        transport = ASGITransport(app=app)

        with patch(
            "app.routers.wp_formula._load_wp", new_callable=AsyncMock
        ) as mock_load:
            mock_wp = MagicMock()
            mock_wp.project_id = project_id
            mock_wp.parsed_data = {"html_data": {"审定表": {"cells": {}}}}
            mock_wp.wp_index_id = None
            mock_load.return_value = mock_wp

            with patch(
                "app.services.wp_formula_service.validate_refs_via_acnr",
                new_callable=AsyncMock,
                return_value=[],
            ), patch(
                "app.routers.wp_formula.evaluate_wp_formula_expression",
                new_callable=AsyncMock,
                return_value=(Decimal("100"), []),
            ), patch(
                "app.services.wp_parsed_data_service.touch_wp_registry",
                new_callable=AsyncMock,
            ):
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    # 非 wp kind → 403（纵深防御）
                    r = await _save(client, wp_id, {
                        "sheet_name": "审定表", "target_cell": "B5",
                        "expression": "WP('D1','B5')", "year": 2025, "kind": "surfaced",
                    })
                    assert r.status_code == 403
                    assert r.json()["detail"]["error_code"] == "FORMULA_NON_WP_KIND_REJECTED"

                    # report kind → 403
                    r = await _save(client, wp_id, {
                        "sheet_name": "审定表", "target_cell": "B5",
                        "expression": "WP('D1','B5')", "year": 2025, "kind": "report",
                    })
                    assert r.status_code == 403

                    # 只读投影伪标记（无 kind）→ 403
                    r = await _save(client, wp_id, {
                        "sheet_name": "审定表", "target_cell": "E1-surfaced-tb-check",
                        "expression": "WP('D1','B5')", "year": 2025,
                    })
                    assert r.status_code == 403
                    assert r.json()["detail"]["error_code"] == "FORMULA_READONLY_PROJECTION_REJECTED"

                    # 反向断言：wp kind 放行到后续求值（200，不被误拒）
                    r = await _save(client, wp_id, {
                        "sheet_name": "审定表", "target_cell": "B5",
                        "expression": "WP('D1','B5')", "year": 2025, "kind": "wp",
                    })
                    assert r.status_code == 200, r.text

                    # 反向断言：省略 kind（前端 wp 行默认）同样放行
                    r = await _save(client, wp_id, {
                        "sheet_name": "审定表", "target_cell": "B6",
                        "expression": "WP('D1','B6')", "year": 2025,
                    })
                    assert r.status_code == 200, r.text

    await engine.dispose()
