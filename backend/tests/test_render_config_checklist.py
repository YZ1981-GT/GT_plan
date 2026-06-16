"""Tests for render-config checklist-table integration

Validates: Requirements 2.1, 2.2
Verifies that GET /api/workpapers/{wp_id}/render-config returns
{template: ..., responses: ...} for checklist-table componentType.

Uses in-process ASGI httpx (干净验证法).

Note: Uses a single test function to avoid Windows asyncpg event loop
corruption between tests (shared app engine + fixture engine dispose issue).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.main import app


def _make_engine():
    return create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)


MOCK_TEMPLATE = {
    "wp_code": "A1-15",
    "title": "企业会计准则有关财务报表列报及披露核对表",
    "sections": [
        {
            "id": "S01",
            "title": "1.1 财务报表的列报",
            "items": [
                {
                    "id": "S01-001",
                    "type": "actionable",
                    "standard_ref": "CAS 30.5",
                    "content": "1 财务报表编制应当以持续经营假设为基础。",
                    "children": [],
                }
            ],
        }
    ],
    "toc": [{"id": "S01", "title": "1.1 财务报表的列报", "applicable": None}],
    "stats": {"total_actionable": 1, "total_guidance": 0, "total_sections": 1},
    "parsed_at": "2026-01-01T00:00:00+00:00",
}


@pytest.mark.asyncio
async def test_render_config_checklist_table_integration():
    """Comprehensive in-process httpx test for checklist-table render-config.

    Tests:
    1. Returns template + responses dict structure
    2. Template data has expected keys (wp_code, sections, toc, stats)
    3. Responses is always a dict
    4. Graceful degradation when template file not found (template=None, no 500)
    5. Response dict values have correct shape {conclusion, remark, wp_ref}
    """
    from app.services.wp_classification_service import ClassificationResult

    # Step 1: Get auth token and wp_id from DB
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            # Auth
            r = await conn.execute(text(
                "SELECT id FROM users WHERE username = 'admin' AND is_active = true LIMIT 1"
            ))
            user_row = r.fetchone()
            if user_row is None:
                pytest.skip("No admin user in DB")

            # Working paper
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
        sheet_name="核对表",
        class_code="A-程序表",
        class_="A-程序表",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ─── Test A: Normal case — template + responses structure ──────────
        with patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClassSvc, patch(
            "app.routers.wp_render_config.derive_component_type",
            return_value="checklist-table",
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {wp_code: "checklist-table"},
        ), patch(
            "app.services.checklist_docx_parser.get_checklist_template",
            new_callable=AsyncMock,
            return_value=MOCK_TEMPLATE,
        ):
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

        # Should have sheets
        sheets = data.get("sheets", [])
        assert len(sheets) >= 1

        # Find the checklist-table sheet
        checklist_sheet = next(
            (s for s in sheets if s.get("componentType") == "checklist-table"), None
        )
        assert checklist_sheet is not None, "Expected a checklist-table sheet in response"

        # html_data should contain template and responses
        html_data = checklist_sheet.get("html_data", {})
        assert "template" in html_data, "html_data should contain 'template' key"
        assert "responses" in html_data, "html_data should contain 'responses' key"

        # Template should have expected structure
        template = html_data["template"]
        assert template is not None
        assert template.get("wp_code") == "A1-15"
        assert "sections" in template
        assert "toc" in template
        assert "stats" in template
        assert template["stats"]["total_actionable"] == 1

        # Responses should be dict
        responses = html_data["responses"]
        assert isinstance(responses, dict)

        # Validate response values have correct shape
        for item_id, resp_data in responses.items():
            assert isinstance(item_id, str)
            assert "conclusion" in resp_data
            assert "remark" in resp_data
            assert "wp_ref" in resp_data

        # ─── Test B: Template not found — graceful degradation ────────────
        with patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClassSvc2, patch(
            "app.routers.wp_render_config.derive_component_type",
            return_value="checklist-table",
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {wp_code: "checklist-table"},
        ), patch(
            "app.services.checklist_docx_parser.get_checklist_template",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError("未找到核对表模板文件"),
        ):
            mock_instance2 = AsyncMock()
            mock_instance2.get_classification = AsyncMock(return_value=[mock_classification])
            MockClassSvc2.return_value = mock_instance2

            resp2 = await client.get(
                f"/api/workpapers/{wp_id}/render-config",
                headers=headers,
            )

        assert resp2.status_code == 200, "Template not found should NOT cause 500"
        body2 = resp2.json()
        data2 = body2.get("data", body2)

        sheets2 = data2.get("sheets", [])
        checklist_sheet2 = next(
            (s for s in sheets2 if s.get("componentType") == "checklist-table"), None
        )
        assert checklist_sheet2 is not None

        html_data2 = checklist_sheet2["html_data"]
        assert html_data2["template"] is None, "Missing template should return None"
        assert isinstance(html_data2["responses"], dict), "Responses should still be dict"
