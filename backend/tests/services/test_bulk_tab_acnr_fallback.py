"""Tests for Task 1.2: ACNR 加载失败降级

验证 ManifestBuilder 在 ACNR catalog 不可用时抛出明确异常
(AcnrCatalogUnavailableError)，绝不静默退回分散 JSON。

Requirements: 7.4
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from app.services.acnr.catalog import CatalogLoadError
from app.services.bulk_tab.exceptions import AcnrCatalogUnavailableError
from app.services.bulk_tab.manifest_builder import build_manifest, BulkManifest

# patch target: lazy import inside build_manifest
_PATCH_TARGET = "app.services.wp_bulk_tab_export.list_export_sheets"
_PATCH_LIST_IE = "app.services.acnr.manifest.list_import_export"
_PATCH_LIST_SHEETS = "app.services.acnr.catalog.list_sheets"


async def _raise_catalog_error(*args, **kwargs):
    """Async mock that raises CatalogLoadError."""
    raise CatalogLoadError("Catalog 加载失败且不存在可用的上一版缓存")


async def _raise_file_not_found(*args, **kwargs):
    raise CatalogLoadError("文件不存在")


async def _raise_json_error(*args, **kwargs):
    raise CatalogLoadError("JSON 解析失败")


@pytest.mark.asyncio
async def test_acnr_catalog_unavailable_raises_explicit_error():
    """CatalogLoadError 应被包装为 AcnrCatalogUnavailableError，不静默降级。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    with patch(_PATCH_TARGET, side_effect=_raise_catalog_error):
        with pytest.raises(AcnrCatalogUnavailableError) as exc_info:
            await build_manifest(mock_db, project_id, ["D"], "template")

        assert "ACNR catalog 不可用" in str(exc_info.value)
        assert exc_info.value.cause is not None
        assert isinstance(exc_info.value.cause, CatalogLoadError)


@pytest.mark.asyncio
async def test_acnr_catalog_unavailable_preserves_cycle_context():
    """异常消息中应包含 cycle 信息，方便定位问题。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    with patch(_PATCH_TARGET, side_effect=_raise_file_not_found):
        with pytest.raises(AcnrCatalogUnavailableError) as exc_info:
            await build_manifest(mock_db, project_id, ["K"], "data")

        assert "cycle=K" in str(exc_info.value)


@pytest.mark.asyncio
async def test_acnr_catalog_unavailable_no_silent_fallback():
    """确认不会返回空列表或 None 作为静默降级——必须抛异常。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    with patch(_PATCH_TARGET, side_effect=_raise_json_error):
        # 必须抛异常，不能返回任何值
        with pytest.raises(AcnrCatalogUnavailableError):
            await build_manifest(mock_db, project_id, None, "template")


@pytest.mark.asyncio
async def test_normal_operation_returns_bulk_manifest():
    """catalog 正常时不应抛异常，应返回 BulkManifest。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()
    wp_id = str(uuid.uuid4())

    mock_entries = [
        {
            "sheet_code": "D2-2",
            "api_prefix": "d2",
            "item_id": "D2-vc-rows",
            "import_order": 1,
            "depends_on_sheets": [],
            "wp_id": wp_id,
            "parent_wp_code": "D2",
            "addr_id": "D2/D2-2",
            "storage_field": "remark",
        }
    ]

    async def _mock_list_export_sheets(*args, **kwargs):
        return mock_entries

    async def _mock_list_import_export(*args, **kwargs):
        return mock_entries

    def _mock_list_sheets(*args, **kwargs):
        return [
            {
                "addr_id": "D2/D2-2",
                "sheet_code": "D2-2",
                "sheet_name": "明细表D2-2",
                "origin": "standard",
                "cycle": "D",
                "parent_wp_code": "D2",
            }
        ]

    with patch(_PATCH_TARGET, side_effect=_mock_list_export_sheets), \
         patch(_PATCH_LIST_IE, side_effect=_mock_list_import_export), \
         patch(_PATCH_LIST_SHEETS, side_effect=_mock_list_sheets):
        result = await build_manifest(mock_db, project_id, ["D"], "template")

    assert isinstance(result, BulkManifest)
    assert len(result.files) == 1
    assert result.files[0].sheet_code == "D2-2"
    assert result.files[0].wp_id == wp_id
    assert result.files[0].zip_path == "D/D2/D2-2_明细表_模板.xlsx"
    assert len(result.skipped) == 0


@pytest.mark.asyncio
async def test_exception_chain_preserved():
    """验证异常链（__cause__）被正确保留，方便调试。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()
    original = CatalogLoadError("磁盘 IO 错误")

    async def _raise_original(*args, **kwargs):
        raise original

    with patch(_PATCH_TARGET, side_effect=_raise_original):
        with pytest.raises(AcnrCatalogUnavailableError) as exc_info:
            await build_manifest(mock_db, project_id, ["D"], "data")

        # __cause__ 是标准 Python 异常链
        assert exc_info.value.__cause__ is original
