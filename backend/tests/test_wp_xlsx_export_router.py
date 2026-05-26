"""Tests for wp_xlsx_export router — POST /api/workpapers/{wp_id}/export-xlsx

验证端点行为：
  - 404: 底稿不存在
  - 500: 模板缺失（TemplateNotFoundError）
  - 422: 必填字段缺失（ExportValidationError）
  - 200: 正常导出 xlsx attachment

Requirements: 2.1（一键导出 Excel）
"""

from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_xlsx_export_service import (
    ExportValidationError,
    TemplateNotFoundError,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_user():
    """Create a mock user for auth."""
    from app.models.core import User
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "test_admin"
    user.role = "admin"
    return user


@pytest.fixture
def mock_working_paper():
    """Create a mock working paper."""
    wp = MagicMock()
    wp.id = uuid.uuid4()
    wp.project_id = uuid.uuid4()
    wp.wp_index_id = uuid.uuid4()
    wp.is_deleted = False
    wp.parsed_data = {
        "html_data": {
            "TestSheet": {"rows": [{"name": "Row 1"}]},
        },
    }
    return wp


@pytest.fixture
def mock_wp_index():
    """Create a mock wp_index."""
    idx = MagicMock()
    idx.id = uuid.uuid4()
    idx.wp_code = "D2A"
    idx.is_deleted = False
    return idx


@pytest.fixture
def mock_project():
    """Create a mock project."""
    from datetime import date

    proj = MagicMock()
    proj.id = uuid.uuid4()
    proj.client_name = "测试审计公司"
    proj.audit_period_end = date(2025, 12, 31)
    return proj


# ─── Direct function tests (bypass middleware) ───────────────────────────────


class TestExportXlsxEndpoint:
    """Test POST /api/workpapers/{wp_id}/export-xlsx logic."""

    @pytest.mark.asyncio
    async def test_404_when_workpaper_not_found(self, mock_user):
        """Returns 404 when wp_id does not exist."""
        from fastapi import HTTPException
        from app.routers.wp_xlsx_export import export_xlsx

        # Mock DB session that returns no working paper
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await export_xlsx(
                wp_id=uuid.uuid4(),
                db=mock_db,
                current_user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "底稿不存在" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_404_when_wp_index_not_found(
        self, mock_user, mock_working_paper
    ):
        """Returns 404 when wp_index does not exist."""
        from fastapi import HTTPException
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        with pytest.raises(HTTPException) as exc_info:
            await export_xlsx(
                wp_id=mock_working_paper.id,
                db=mock_db,
                current_user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "索引" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_500_when_schema_not_found(
        self, mock_user, mock_working_paper, mock_wp_index
    ):
        """Returns 500 when render schema is missing."""
        from fastapi import HTTPException
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            elif call_count[0] == 2:
                scalars.first.return_value = mock_wp_index
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        with patch(
            "app.routers.wp_xlsx_export._schema_service.load_schema",
            side_effect=FileNotFoundError("Schema not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await export_xlsx(
                    wp_id=mock_working_paper.id,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 500
            assert "schema" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_500_when_template_not_found(
        self, mock_user, mock_working_paper, mock_wp_index, mock_project
    ):
        """Returns 500 when template xlsx file is missing."""
        from fastapi import HTTPException
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            elif call_count[0] == 2:
                scalars.first.return_value = mock_wp_index
            elif call_count[0] == 3:
                scalars.first.return_value = mock_project
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        mock_schema = {
            "wp_code": "D2A",
            "template_path": "nonexistent.xlsx",
            "sheets": {"TestSheet": {}},
        }

        with patch(
            "app.routers.wp_xlsx_export._schema_service.load_schema",
            return_value=mock_schema,
        ), patch(
            "app.routers.wp_xlsx_export.export_workpaper_xlsx",
            side_effect=TemplateNotFoundError("Template not found: nonexistent.xlsx"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await export_xlsx(
                    wp_id=mock_working_paper.id,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 500
            assert "模板" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_422_when_required_fields_missing(
        self, mock_user, mock_working_paper, mock_wp_index, mock_project
    ):
        """Returns 422 when required project metadata fields are empty."""
        from fastapi import HTTPException
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            elif call_count[0] == 2:
                scalars.first.return_value = mock_wp_index
            elif call_count[0] == 3:
                scalars.first.return_value = mock_project
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        mock_schema = {
            "wp_code": "D2A",
            "template_path": "backend/wp_templates/D/D2.xlsx",
            "sheets": {"TestSheet": {}},
        }

        with patch(
            "app.routers.wp_xlsx_export._schema_service.load_schema",
            return_value=mock_schema,
        ), patch(
            "app.routers.wp_xlsx_export.export_workpaper_xlsx",
            side_effect=ExportValidationError(["entity_name", "period_end"]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await export_xlsx(
                    wp_id=mock_working_paper.id,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 422
            detail = exc_info.value.detail
            assert "entity_name" in detail["missing_fields"]
            assert "period_end" in detail["missing_fields"]

    @pytest.mark.asyncio
    async def test_200_successful_export(
        self, mock_user, mock_working_paper, mock_wp_index, mock_project
    ):
        """Returns StreamingResponse with xlsx on successful export."""
        from fastapi.responses import StreamingResponse
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            elif call_count[0] == 2:
                scalars.first.return_value = mock_wp_index
            elif call_count[0] == 3:
                scalars.first.return_value = mock_project
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        mock_schema = {
            "wp_code": "D2A",
            "template_path": "backend/wp_templates/D/D2.xlsx",
            "sheets": {"TestSheet": {}},
        }

        fake_xlsx = BytesIO(b"PK\x03\x04fake xlsx content")

        with patch(
            "app.routers.wp_xlsx_export._schema_service.load_schema",
            return_value=mock_schema,
        ), patch(
            "app.routers.wp_xlsx_export.export_workpaper_xlsx",
            return_value=fake_xlsx,
        ):
            response = await export_xlsx(
                wp_id=mock_working_paper.id,
                db=mock_db,
                current_user=mock_user,
            )

            assert isinstance(response, StreamingResponse)
            assert response.media_type == (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            # Check Content-Disposition header
            headers_dict = dict(response.headers)
            content_disp = headers_dict.get("content-disposition", "")
            assert "attachment" in content_disp
            assert "D2A.xlsx" in content_disp

    @pytest.mark.asyncio
    async def test_filename_uses_wp_code_and_sheet_name(
        self, mock_user, mock_working_paper, mock_wp_index, mock_project
    ):
        """Filename includes wp_code and first sheet name (URL-encoded)."""
        from fastapi.responses import StreamingResponse
        from app.routers.wp_xlsx_export import export_xlsx

        mock_db = AsyncMock()
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count[0] == 1:
                scalars.first.return_value = mock_working_paper
            elif call_count[0] == 2:
                scalars.first.return_value = mock_wp_index
            elif call_count[0] == 3:
                scalars.first.return_value = mock_project
            else:
                scalars.first.return_value = None
            result.scalars.return_value = scalars
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        mock_schema = {
            "wp_code": "D2A",
            "template_path": "backend/wp_templates/D/D2.xlsx",
            "sheets": {"应收账款实质性程序表D2A": {}},
        }

        fake_xlsx = BytesIO(b"PK\x03\x04fake xlsx content")

        with patch(
            "app.routers.wp_xlsx_export._schema_service.load_schema",
            return_value=mock_schema,
        ), patch(
            "app.routers.wp_xlsx_export.export_workpaper_xlsx",
            return_value=fake_xlsx,
        ):
            response = await export_xlsx(
                wp_id=mock_working_paper.id,
                db=mock_db,
                current_user=mock_user,
            )

            headers_dict = dict(response.headers)
            content_disp = headers_dict.get("content-disposition", "")
            # ASCII fallback filename
            assert 'filename="D2A.xlsx"' in content_disp
            # UTF-8 encoded filename with Chinese characters
            assert "filename*=UTF-8''" in content_disp
            assert "D2A_" in content_disp
