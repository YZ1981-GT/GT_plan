# Feature: custom-workpaper-formula-binding — wp_formula 端点 in-process ASGI（任务 2.2）
"""保存→列出→删除往返 + 悬空引用 422。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.deps import get_current_user
from app.models.workpaper_models import WpFormula
from app.routers.wp_formula import router as wp_formula_router
from app.services.wp_formula_service import WpFormulaService


@pytest.fixture(autouse=True)
def _stub_wp_ownership():
    """隔离归属校验（Req 10）：这些端点测试只建 wp_formula 表不建 working_paper，
    save()/list_by_wp() 的 _verify_wp_ownership 会查 working_paper → sqlite no such table。
    归属另有 ownership_guard 专测覆盖，此处 class 级 stub 返回 True 隔离。"""
    with patch.object(
        WpFormulaService, "_verify_wp_ownership", new=AsyncMock(return_value=True)
    ):
        yield


class _FakeUser:
    id = uuid.uuid4()
    is_active = True


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


@pytest.mark.anyio
async def test_wp_formula_crud_roundtrip():
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
            "app.routers.wp_formula._load_wp",
            new_callable=AsyncMock,
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
            ):
                with patch(
                    "app.routers.wp_formula.evaluate_wp_formula_expression",
                    new_callable=AsyncMock,
                    return_value=(Decimal("100"), []),
                ):
                    with patch(
                        "app.services.wp_parsed_data_service.touch_wp_registry",
                        new_callable=AsyncMock,
                    ):
                        async with AsyncClient(
                            transport=transport, base_url="http://test"
                        ) as client:
                            put_resp = await client.put(
                                f"/api/workpapers/{wp_id}/formulas",
                                json={
                                    "sheet_name": "审定表",
                                    "target_cell": "B5",
                                    "expression": "WP('D1','B5')",
                                    "year": 2025,
                                },
                            )
                            assert put_resp.status_code == 200
                            body = put_resp.json()
                            assert body.get("evaluated_value") == "100"
                            saved_id = body["saved"]["id"]
                            assert (
                                mock_wp.parsed_data["html_data"]["审定表"]["cells"]["B5"]
                                == 100
                            )

                            get_resp = await client.get(
                                f"/api/workpapers/{wp_id}/formulas"
                            )
                            assert get_resp.status_code == 200
                            items = get_resp.json()["items"]
                            assert len(items) == 1
                            assert items[0]["target_cell"] == "B5"

                            del_resp = await client.delete(
                                f"/api/workpapers/{wp_id}/formulas/{saved_id}"
                            )
                            assert del_resp.status_code == 200

                            # 🔴 2026-09-22 补判据：**必须回读确认真的删掉了**。
                            # 此前这里只断言 `status_code == 200` 就收工，而真实缺陷恰恰是
                            # 「返回 200 但一行未删」—— router 调
                            # `wp_formula_service.delete(db, formula_id)` 时漏传
                            # `project_id`，服务层 ownership 门（Req 10.6：project_id 为
                            # None 即 return False）直接拒绝，router 又忽略返回值、无条件
                            # 回 `{"deleted": ...}`。真栈实测：DELETE 200 之后
                            # GET /formulas 仍返回该条。只看状态码的守卫对此恒绿。
                            #
                            # 变异反证：把 delete 调用改回不传 project_id（或去掉
                            # `if not deleted: 404`），下面两条立刻打红。
                            after_resp = await client.get(
                                f"/api/workpapers/{wp_id}/formulas"
                            )
                            assert after_resp.status_code == 200
                            after_items = after_resp.json()["items"]
                            assert after_items == [], (
                                f"DELETE 返回 200 但公式仍在列表里（假成功）：{after_items}"
                            )
                            assert not any(
                                i.get("id") == saved_id for i in after_items
                            ), "被删 id 仍可读回"

    await engine.dispose()


@pytest.mark.anyio
async def test_wp_formula_save_rejects_dangling_ref():
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

        with patch("app.routers.wp_formula._load_wp", new_callable=AsyncMock) as mock_load:
            mock_wp = AsyncMock()
            mock_wp.project_id = project_id
            mock_load.return_value = mock_wp

            with patch(
                "app.services.wp_formula_service.validate_refs_via_acnr",
                new_callable=AsyncMock,
                return_value=[{"status": "not_found", "ref": "WP('X','Z99')"}],
            ):
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    resp = await client.put(
                        f"/api/workpapers/{wp_id}/formulas",
                        json={
                            "sheet_name": "审定表",
                            "target_cell": "B5",
                            "expression": "WP('X','Z99')",
                            "year": 2025,
                        },
                    )
                    assert resp.status_code == 422
                    assert "issues" in resp.json()["detail"]

    await engine.dispose()
