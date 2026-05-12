"""Tests for workpaper HTML preview endpoint (Round 4 需求 8)

GET /api/projects/{project_id}/workpapers/{wp_id}/html
- Returns HTML preview of workpaper
- Supports ?mask=true for desensitization
- Reuses excel_html_converter
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers.workpaper_html_preview import (
    _mask_structure,
    get_workpaper_html_preview,
)


class TestMaskStructure:
    """Test _mask_structure helper function."""

    def test_masks_sensitive_amounts(self):
        """大额数值应被脱敏为 [amount]"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": "项目"},
                        "0:1": {"value": 500000.0},  # >= 100000, sensitive
                        "0:2": {"value": 99.0},  # < 100000, not sensitive
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        assert masked["sheets"][0]["cells"]["0:1"]["value"] == "[amount]"
        assert masked["sheets"][0]["cells"]["0:2"]["value"] == 99.0

    def test_masks_company_names(self):
        """公司名应被脱敏"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": "北京华为科技有限公司"},
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        # Company name should be replaced with [client_N] placeholder
        assert "[client_" in masked["sheets"][0]["cells"]["0:0"]["value"]

    def test_preserves_none_values(self):
        """None 值不应被处理"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": None},
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        assert masked["sheets"][0]["cells"]["0:0"]["value"] is None

    def test_preserves_small_numbers(self):
        """小额数值不应被脱敏"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": 1234.56},
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        assert masked["sheets"][0]["cells"]["0:0"]["value"] == 1234.56

    def test_does_not_mutate_original(self):
        """脱敏不应修改原始 structure"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": 999999.0},
                    }
                }
            ]
        }
        _mask_structure(structure)
        assert structure["sheets"][0]["cells"]["0:0"]["value"] == 999999.0

    def test_handles_empty_structure(self):
        """空 structure 应正常处理"""
        structure = {"sheets": []}
        masked = _mask_structure(structure)
        assert masked == {"sheets": []}

    def test_handles_empty_string_values(self):
        """空字符串不应被处理"""
        structure = {
            "sheets": [
                {
                    "cells": {
                        "0:0": {"value": ""},
                        "0:1": {"value": "   "},
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        assert masked["sheets"][0]["cells"]["0:0"]["value"] == ""
        assert masked["sheets"][0]["cells"]["0:1"]["value"] == "   "


class TestGetWorkpaperHtmlPreview:
    """Test the endpoint handler logic."""

    @pytest.mark.asyncio
    async def test_returns_404_when_workpaper_not_found(self):
        """底稿不存在时返回 404"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_workpaper_html_preview(
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                mask=False,
                db=mock_db,
                _user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "底稿不存在" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_html_from_parsed_data_structure(self):
        """从 parsed_data 中的 sheets 数据生成 HTML"""
        mock_db = AsyncMock()
        mock_wp = MagicMock()
        mock_wp.parsed_data = {
            "sheets": [
                {
                    "name": "Sheet1",
                    "cells": {
                        "0:0": {"value": "项目"},
                        "0:1": {"value": "金额"},
                        "1:0": {"value": "收入"},
                        "1:1": {"value": 1000},
                    },
                    "merges": [],
                    "cols": [],
                    "rows": [],
                }
            ]
        }
        mock_wp.file_path = None
        mock_wp.is_deleted = False
        mock_wp.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        response = await get_workpaper_html_preview(
            project_id=mock_wp.project_id,
            wp_id=uuid.uuid4(),
            mask=False,
            db=mock_db,
            _user=mock_user,
        )

        # Should return HTMLResponse
        assert "<!DOCTYPE html>" in response.body.decode()
        assert "gt-excel-table" in response.body.decode()
        assert "项目" in response.body.decode()

    @pytest.mark.asyncio
    async def test_returns_html_with_mask(self):
        """mask=true 时应脱敏大额金额"""
        mock_db = AsyncMock()
        mock_wp = MagicMock()
        mock_wp.parsed_data = {
            "sheets": [
                {
                    "name": "Sheet1",
                    "cells": {
                        "0:0": {"value": "项目"},
                        "0:1": {"value": 500000.0},
                    },
                    "merges": [],
                    "cols": [],
                    "rows": [],
                }
            ]
        }
        mock_wp.file_path = None
        mock_wp.is_deleted = False
        mock_wp.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        response = await get_workpaper_html_preview(
            project_id=mock_wp.project_id,
            wp_id=uuid.uuid4(),
            mask=True,
            db=mock_db,
            _user=mock_user,
        )

        body = response.body.decode()
        assert "500000" not in body
        assert "[amount]" in body

    @pytest.mark.asyncio
    async def test_returns_404_when_no_data_available(self):
        """无 parsed_data 且无文件时返回 404"""
        mock_db = AsyncMock()
        mock_wp = MagicMock()
        mock_wp.parsed_data = None
        mock_wp.file_path = None
        mock_wp.is_deleted = False
        mock_wp.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_workpaper_html_preview(
                project_id=mock_wp.project_id,
                wp_id=uuid.uuid4(),
                mask=False,
                db=mock_db,
                _user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "无可预览的数据" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_uses_structure_subkey_from_parsed_data(self):
        """parsed_data 中有 structure 子键时使用它"""
        mock_db = AsyncMock()
        mock_wp = MagicMock()
        mock_wp.parsed_data = {
            "structure": {
                "sheets": [
                    {
                        "name": "Sheet1",
                        "cells": {"0:0": {"value": "测试"}},
                        "merges": [],
                        "cols": [],
                        "rows": [],
                    }
                ]
            },
            "other_data": "ignored",
        }
        mock_wp.file_path = None
        mock_wp.is_deleted = False
        mock_wp.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        response = await get_workpaper_html_preview(
            project_id=mock_wp.project_id,
            wp_id=uuid.uuid4(),
            mask=False,
            db=mock_db,
            _user=mock_user,
        )

        body = response.body.decode()
        assert "测试" in body

    @pytest.mark.asyncio
    async def test_mobile_friendly_html_structure(self):
        """返回的 HTML 应包含移动端友好的 viewport meta"""
        mock_db = AsyncMock()
        mock_wp = MagicMock()
        mock_wp.parsed_data = {
            "sheets": [
                {
                    "name": "Sheet1",
                    "cells": {"0:0": {"value": "数据"}},
                    "merges": [],
                    "cols": [],
                    "rows": [],
                }
            ]
        }
        mock_wp.file_path = None
        mock_wp.is_deleted = False
        mock_wp.project_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        mock_db.execute.return_value = mock_result

        mock_user = MagicMock()

        response = await get_workpaper_html_preview(
            project_id=mock_wp.project_id,
            wp_id=uuid.uuid4(),
            mask=False,
            db=mock_db,
            _user=mock_user,
        )

        body = response.body.decode()
        assert 'name="viewport"' in body
        assert "width=device-width" in body
        assert "lang=\"zh-CN\"" in body
