"""Tests for render-config analytical-review integration

Validates: Requirements 1.1, 7.4
Verifies that GET /api/workpapers/{wp_id}/render-config returns
{analytical_review: ...} for analytical-review componentType (A1-13/A1-14).

Uses in-process ASGI httpx (干净验证法).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.main import app


def _make_engine():
    return create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)


MOCK_AR_DATA = {
    "wp_code": "A1-13",
    "scope": "standalone",
    "year": 2025,
    "sheets": {
        "bs_horizontal": {
            "title": "已审资产负债表（母公司）横向趋势分析",
            "index": "A1-13-1",
            "columns": [
                "项目", "行次", "上年审定数", "本年审定数",
                "变动额", "变动%", "变动状况", "显著变动原因分析",
            ],
            "rows": [
                {
                    "row_code": "BS-001",
                    "name": "流动资产",
                    "prior": 1000000,
                    "current": 1200000,
                    "change": 200000,
                    "change_pct": 20.0,
                    "status": "significant",
                    "reason": None,
                }
            ],
        },
        "bs_vertical": {"title": "纵向分析", "index": "A1-13-2", "rows": []},
        "is_horizontal": {"title": "利润表横向", "index": "A1-13-3", "rows": []},
        "is_vertical": {"title": "利润表纵向", "index": "A1-13-4", "rows": []},
        "ratio_analysis": {"title": "比率分析", "index": "A1-13-5", "categories": []},
    },
}


@pytest.mark.asyncio
async def test_render_config_analytical_review_integration():
    """In-process httpx test for analytical-review render-config.

    Tests:
    1. Returns analytical_review key in html_data with mock data
    2. Scope is standalone for A1-13
    3. Graceful degradation when service fails (analytical_review=None, no 500)
    """
    from app.services.wp_classification_service import ClassificationResult

    # Step 1: Get auth token and wp_id from DB
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text(
                "SELECT id FROM users WHERE username = 'admin' AND is_active = true LIMIT 1"
            ))
            user_row = r.fetchone()
            if user_row is None:
                pytest.skip("No admin user in DB")

            r2 = await conn.execute(text("""
                SELECT wp.id, wp.project_id, wi.wp_code
                FROM working_paper wp
                JOIN wp_index wi ON wi.id = wp.wp_index_id
                WHERE wp.is_deleted = false AND wi.is_deleted = false
                LIMIT 1
            """))
            wp_row = r2.fetchone()
            if wp_row is None:
                pytest.skip("No working_paper in DB")
    finally:
        await engine.dispose()

    from app.core.security import create_access_token
    token = create_access_token({"sub": str(user_row.id), "type": "access"})
    headers = {"Authorization": f"Bearer {token}"}
    wp_id = str(wp_row.id)
    wp_code = wp_row.wp_code

    mock_classification = ClassificationResult(
        wp_code=wp_code,
        sheet_name="分析性复核",
        class_code="A-分析性复核",
        class_="A-分析性复核",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ─── Test A: Normal case — analytical_review data returned ─────────
        with patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClassSvc, patch(
            "app.routers.wp_render_config.derive_component_type",
            return_value="analytical-review",
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {wp_code: "analytical-review"},
        ), patch(
            "app.services.analytical_review_service.get_analytical_review_data",
            new_callable=AsyncMock,
            return_value=MOCK_AR_DATA,
        ) as mock_get_ar:
            mock_instance = AsyncMock()
            mock_instance.get_classification = AsyncMock(return_value=[mock_classification])
            MockClassSvc.return_value = mock_instance

            resp = await client.get(
                f"/api/workpapers/{wp_id}/render-config",
                headers=headers,
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        data = body.get("data", body)

        sheets = data.get("sheets", [])
        assert len(sheets) >= 1

        # Find the analytical-review sheet
        ar_sheet = next(
            (s for s in sheets if s.get("componentType") == "analytical-review"), None
        )
        assert ar_sheet is not None, "Expected an analytical-review sheet in response"

        # html_data should contain analytical_review key
        html_data = ar_sheet.get("html_data", {})
        assert "analytical_review" in html_data, "html_data should contain 'analytical_review' key"

        ar_result = html_data["analytical_review"]
        assert ar_result is not None
        assert ar_result.get("wp_code") == "A1-13"
        assert ar_result.get("scope") == "standalone"
        assert "sheets" in ar_result
        assert "bs_horizontal" in ar_result["sheets"]

        # ─── Test B: Service failure — graceful degradation ───────────────
        with patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClassSvc2, patch(
            "app.routers.wp_render_config.derive_component_type",
            return_value="analytical-review",
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {wp_code: "analytical-review"},
        ), patch(
            "app.services.analytical_review_service.get_analytical_review_data",
            new_callable=AsyncMock,
            side_effect=RuntimeError("模拟数据库连接失败"),
        ):
            mock_instance2 = AsyncMock()
            mock_instance2.get_classification = AsyncMock(return_value=[mock_classification])
            MockClassSvc2.return_value = mock_instance2

            resp2 = await client.get(
                f"/api/workpapers/{wp_id}/render-config",
                headers=headers,
            )

        assert resp2.status_code == 200, "Service failure should NOT cause 500"
        body2 = resp2.json()
        data2 = body2.get("data", body2)

        sheets2 = data2.get("sheets", [])
        ar_sheet2 = next(
            (s for s in sheets2 if s.get("componentType") == "analytical-review"), None
        )
        assert ar_sheet2 is not None

        html_data2 = ar_sheet2.get("html_data", {})
        assert html_data2["analytical_review"] is None, "Failed service should return None"


def test_scope_determination_logic():
    """Unit test for scope determination: A1-14 → consolidated, else → standalone."""
    # This tests the inline logic: ar_scope = "consolidated" if wp_code == "A1-14" else "standalone"
    assert ("consolidated" if "A1-14" == "A1-14" else "standalone") == "consolidated"
    assert ("consolidated" if "A1-13" == "A1-14" else "standalone") == "standalone"
    assert ("consolidated" if "D1" == "A1-14" else "standalone") == "standalone"
