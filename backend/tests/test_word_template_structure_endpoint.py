"""Unit tests for GET /api/workpapers/{wp_id}/template-structure endpoint.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers.wp_onlyoffice_router import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakePlaceholder:
    field_id: str
    label: str
    data_type: str
    default_value: str
    position: dict
    pattern: str


@dataclass
class FakeParagraph:
    index: int
    text: str
    style: str
    heading_level: int
    placeholder_ids: list


@dataclass
class FakeTable:
    index: int
    rows: list
    placeholder_ids: list


@dataclass
class FakeStructure:
    paragraphs: list
    tables: list
    placeholders: list
    metadata: dict


def _make_structure() -> FakeStructure:
    return FakeStructure(
        paragraphs=[
            FakeParagraph(
                index=0,
                text="关于对${entity_name}的审计",
                style="Heading 1",
                heading_level=1,
                placeholder_ids=["entity_name"],
            )
        ],
        tables=[
            FakeTable(
                index=0,
                rows=[["项目", "内容"], ["被审计单位", "${entity_name}"]],
                placeholder_ids=["entity_name"],
            )
        ],
        placeholders=[
            FakePlaceholder(
                field_id="entity_name",
                label="被审计单位",
                data_type="text",
                default_value="××公司",
                position={"paragraph_index": 0},
                pattern="${entity_name}",
            )
        ],
        metadata={
            "template_name": "A8-1 审计业务约定书",
            "wp_code": "A8-1",
            "last_parsed_at": "2026-06-26T10:00:00Z",
        },
    )


def _make_app(
    wp_code: str = "A8-1",
    component_type: str = "word-template",
    template_exists: bool = True,
    structure: FakeStructure | None = None,
    checklist_rows: list | None = None,
) -> FastAPI:
    """Build test app with mocked dependencies."""
    from pathlib import Path

    app = FastAPI()
    app.include_router(router)

    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()

    # Mock WorkingPaper
    mock_wp = MagicMock()
    mock_wp.id = wp_id
    mock_wp.project_id = project_id
    mock_wp.is_deleted = False

    # Mock _load_wp_or_404
    async def mock_load_wp(db, _wp_id):
        if str(_wp_id) == str(wp_id):
            return mock_wp, wp_code
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="底稿不存在")

    # Mock template path
    mock_path = MagicMock(spec=Path) if template_exists else None
    if mock_path:
        mock_path.exists.return_value = True
        mock_path.__str__ = lambda self: "/fake/template.docx"

    # Mock checklist responses
    rows = checklist_rows or []

    async def mock_db_execute(stmt, params=None):
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_db_execute

    # Mock dependencies
    async def mock_get_db():
        yield mock_db

    async def mock_get_current_user():
        user = MagicMock()
        user.id = uuid.uuid4()
        user.username = "test_user"
        user.role = MagicMock(value="admin")
        return user

    from app.core.database import get_db
    from app.deps import get_current_user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user

    return app, wp_id, mock_load_wp, mock_path, structure or _make_structure()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTemplateStructureEndpoint:
    """Test GET /api/workpapers/{wp_id}/template-structure."""

    @pytest.mark.asyncio
    async def test_returns_structure_for_word_template(self):
        """Requirement 3.1: Returns cached TemplateStructure for word-template wp_code."""
        app, wp_id, mock_load, mock_path, structure = _make_app()

        with patch(
            "app.routers.wp_onlyoffice_router._load_wp_or_404", mock_load
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {"A8-1": "word-template"},
        ), patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=mock_path,
        ), patch(
            "app.services.wp_docx_template_parser.get_cached_structure",
            return_value=structure,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/template-structure")

            assert resp.status_code == 200
            data = resp.json()
            # ResponseWrapperMiddleware wraps in {code, message, data}
            body = data.get("data", data)
            assert "template_structure" in body
            assert "filled_responses" in body
            ts = body["template_structure"]
            assert len(ts["placeholders"]) == 1
            assert ts["placeholders"][0]["field_id"] == "entity_name"
            assert ts["metadata"]["wp_code"] == "A8-1"

    @pytest.mark.asyncio
    async def test_400_for_non_word_template(self):
        """Requirement 3.3: Returns 400 for non-word-template wp_code."""
        app, wp_id, mock_load, _, _ = _make_app(
            wp_code="D1", component_type="audit-sheet"
        )

        with patch(
            "app.routers.wp_onlyoffice_router._load_wp_or_404", mock_load
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {"D1": "audit-sheet"},
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/template-structure")

            assert resp.status_code == 400
            detail = resp.json().get("detail", "")
            assert "word-template" in detail

    @pytest.mark.asyncio
    async def test_404_for_missing_template_file(self):
        """Requirement 3.5: Returns 404 when template file doesn't exist."""
        app, wp_id, mock_load, _, _ = _make_app(template_exists=False)

        with patch(
            "app.routers.wp_onlyoffice_router._load_wp_or_404", mock_load
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {"A8-1": "word-template"},
        ), patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/template-structure")

            assert resp.status_code == 404
            detail = resp.json().get("detail", "")
            assert "模板文件不存在" in detail

    @pytest.mark.asyncio
    async def test_merges_checklist_responses(self):
        """Requirement 3.4: Merges checklist_responses current values into placeholders."""
        # Create a mock row with item_id and conclusion
        mock_row = MagicMock()
        mock_row.item_id = "wt-A8-1-entity_name"
        mock_row.conclusion = "示例公司"
        mock_row.remark = ""

        app, wp_id, mock_load, mock_path, structure = _make_app(
            checklist_rows=[mock_row]
        )

        with patch(
            "app.routers.wp_onlyoffice_router._load_wp_or_404", mock_load
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {"A8-1": "word-template"},
        ), patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=mock_path,
        ), patch(
            "app.services.wp_docx_template_parser.get_cached_structure",
            return_value=structure,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/template-structure")

            assert resp.status_code == 200
            data = resp.json()
            body = data.get("data", data)
            assert body["filled_responses"]["entity_name"] == "示例公司"
            assert body["template_structure"]["placeholders"][0]["current_value"] == "示例公司"

    @pytest.mark.asyncio
    async def test_422_for_parse_failure(self):
        """Returns 422 when template parsing fails."""
        from pathlib import Path

        app, wp_id, mock_load, mock_path, _ = _make_app()

        with patch(
            "app.routers.wp_onlyoffice_router._load_wp_or_404", mock_load
        ), patch(
            "app.services.wp_classification_service._WP_CODE_OVERRIDE",
            {"A8-1": "word-template"},
        ), patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=mock_path,
        ), patch(
            "app.services.wp_docx_template_parser.get_cached_structure",
            side_effect=ValueError("Invalid docx file"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/template-structure")

            assert resp.status_code == 422
            detail = resp.json().get("detail", "")
            assert "模板解析失败" in detail
