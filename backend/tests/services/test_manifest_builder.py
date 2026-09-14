"""Tests for Task 1.1: ManifestBuilder — build_manifest

验证 ManifestBuilder 从 ACNR 读取路由元数据、生成 BulkManifest 结构、
正确处理 skip_reason/wp_id=None → skipped[]、zip_path 模板化。

Requirements: 1.4, 1.5, 1.6, 1.8, 7.1, 7.2, 7.3
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from app.services.bulk_tab.manifest_builder import (
    BulkManifest,
    ManifestFileEntry,
    ManifestSkippedEntry,
    build_manifest,
    _make_short_label,
    _build_zip_path,
)

# Patch targets (lazy imports inside build_manifest)
_PATCH_EXPORT = "app.services.wp_bulk_tab_export.list_export_sheets"
_PATCH_LIST_IE = "app.services.acnr.manifest.list_import_export"
_PATCH_LIST_SHEETS = "app.services.acnr.catalog.list_sheets"


# ---------------------------------------------------------------------------
# _make_short_label
# ---------------------------------------------------------------------------


class TestMakeShortLabel:
    """zip_path 中 short_label 的生成逻辑。"""

    def test_removes_sheet_code_suffix(self):
        """sheet_name 末尾精确匹配 sheet_code 时去除。"""
        assert _make_short_label("明细表D2-2", "D2-2") == "明细表"

    def test_removes_alphanumeric_suffix(self):
        """sheet_name 末尾类似编码后缀时去除。"""
        assert _make_short_label("应收账款实质性程序表D2A", "D2A") == "应收账款实质性程序表"

    def test_fallback_to_original_when_empty(self):
        """去除后为空时回退到 sheet_code。"""
        result = _make_short_label("D2-2", "D2-2")
        assert result == "D2-2"

    def test_chinese_characters_preserved(self):
        """中文字符应保留。"""
        result = _make_short_label("坏账准备计算表D2-10", "D2-10")
        assert "坏账准备计算表" in result

    def test_special_chars_slugified(self):
        """特殊字符（括号等）被替换为下划线。"""
        result = _make_short_label("分析程序（一）E1-14", "E1-14")
        assert "（" not in result
        assert "）" not in result


# ---------------------------------------------------------------------------
# _build_zip_path
# ---------------------------------------------------------------------------


class TestBuildZipPath:
    """zip_path 模板 {cycle}/{parent_wp_code}/{sheet_code}_{short_label}_{模板|数据}.xlsx"""

    def test_template_mode(self):
        path = _build_zip_path("D", "D2", "D2-2", "明细表D2-2", "template")
        assert path == "D/D2/D2-2_明细表_模板.xlsx"

    def test_data_mode(self):
        path = _build_zip_path("D", "D2", "D2-2", "明细表D2-2", "data")
        assert path == "D/D2/D2-2_明细表_数据.xlsx"

    def test_complex_sheet_name(self):
        path = _build_zip_path("D", "D4", "D4-13", "检查D4-13", "template")
        assert path == "D/D4/D4-13_检查_模板.xlsx"

    def test_path_structure(self):
        """确认路径结构为 cycle/parent/file.xlsx"""
        path = _build_zip_path("K", "K1", "K1-2", "明细K1-2", "data")
        parts = path.split("/")
        assert parts[0] == "K"
        assert parts[1] == "K1"
        assert parts[2].endswith(".xlsx")


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


class TestBuildManifest:
    """build_manifest 集成行为。"""

    @pytest.mark.asyncio
    async def test_returns_bulk_manifest(self):
        """应返回 BulkManifest 实例。"""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = str(uuid.uuid4())

        export_entries = [
            {
                "sheet_code": "D2-1",
                "api_prefix": "d2",
                "item_id": "D2-adjudication-rows",
                "import_order": 10,
                "depends_on_sheets": [],
                "wp_id": wp_id,
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-1",
                "storage_field": "remark",
            },
        ]

        async def _mock_export(*args, **kwargs):
            return export_entries

        async def _mock_ie(*args, **kwargs):
            return export_entries

        def _mock_catalog(*args, **kwargs):
            return [
                {
                    "addr_id": "D2/D2-1",
                    "sheet_code": "D2-1",
                    "sheet_name": "审定表D2-1",
                    "origin": "standard",
                    "cycle": "D",
                    "parent_wp_code": "D2",
                }
            ]

        with patch(_PATCH_EXPORT, side_effect=_mock_export), \
             patch(_PATCH_LIST_IE, side_effect=_mock_ie), \
             patch(_PATCH_LIST_SHEETS, side_effect=_mock_catalog):
            result = await build_manifest(
                mock_db, project_id, ["D"], "template",
                exported_by="test_user",
                platform_version="1.0.0",
                audit_year=2025,
            )

        assert isinstance(result, BulkManifest)
        assert result.schema_version == "1.0"
        assert result.project_id == str(project_id)
        assert result.mode == "template"
        assert result.cycles == ["D"]
        assert result.exported_by == "test_user"
        assert result.platform_version == "1.0.0"
        assert result.audit_year == 2025
        assert result.exported_at  # non-empty

    @pytest.mark.asyncio
    async def test_files_populated_from_export_entries(self):
        """files[] 应从 list_export_sheets 结果填充。"""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = str(uuid.uuid4())

        export_entries = [
            {
                "sheet_code": "D2-2",
                "api_prefix": "d2",
                "item_id": "D2-detail-rows",
                "import_order": 20,
                "depends_on_sheets": ["D2-1"],
                "wp_id": wp_id,
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-2",
                "storage_field": "remark",
            },
        ]

        async def _mock_export(*args, **kwargs):
            return export_entries

        async def _mock_ie(*args, **kwargs):
            return export_entries

        def _mock_catalog(*args, **kwargs):
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

        with patch(_PATCH_EXPORT, side_effect=_mock_export), \
             patch(_PATCH_LIST_IE, side_effect=_mock_ie), \
             patch(_PATCH_LIST_SHEETS, side_effect=_mock_catalog):
            result = await build_manifest(mock_db, project_id, ["D"], "data")

        assert len(result.files) == 1
        f = result.files[0]
        assert isinstance(f, ManifestFileEntry)
        assert f.addr_id == "D2/D2-2"
        assert f.wp_code == "D2"
        assert f.parent_wp_code == "D2"
        assert f.sheet_code == "D2-2"
        assert f.sheet_name == "明细表D2-2"
        assert f.origin == "standard"
        assert f.api_prefix == "d2"
        assert f.item_id == "D2-detail-rows"
        assert f.wp_id == wp_id
        assert f.import_order == 20
        assert f.depends_on_sheets == ["D2-1"]
        assert f.zip_path == "D/D2/D2-2_明细表_数据.xlsx"
        assert f.sha256 == ""  # 导出时填入

    @pytest.mark.asyncio
    async def test_skipped_entries_for_wp_id_none(self):
        """wp_id=None 的条目应写入 skipped[]（Req 1.6, 1.8）。"""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = str(uuid.uuid4())

        # list_export_sheets 已过滤 wp_id=None，只返回有效的
        export_entries = [
            {
                "sheet_code": "D2-1",
                "api_prefix": "d2",
                "item_id": "D2-adj",
                "import_order": 10,
                "depends_on_sheets": [],
                "wp_id": wp_id,
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-1",
                "storage_field": "remark",
            }
        ]

        # list_import_export 返回全量（含 wp_id=None 的）
        all_entries = [
            *export_entries,
            {
                "sheet_code": "D2-3",
                "api_prefix": "d2",
                "item_id": "D2-bd-rows",
                "import_order": 30,
                "depends_on_sheets": ["D2-1"],
                "wp_id": None,  # resolve_instance miss
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-3",
                "storage_field": "remark",
            },
        ]

        async def _mock_export(*args, **kwargs):
            return export_entries

        async def _mock_ie(*args, **kwargs):
            return all_entries

        def _mock_catalog(*args, **kwargs):
            return [
                {
                    "addr_id": "D2/D2-1",
                    "sheet_code": "D2-1",
                    "sheet_name": "审定表D2-1",
                    "origin": "standard",
                    "cycle": "D",
                    "parent_wp_code": "D2",
                },
                {
                    "addr_id": "D2/D2-3",
                    "sheet_code": "D2-3",
                    "sheet_name": "坏账D2-3",
                    "origin": "standard",
                    "cycle": "D",
                    "parent_wp_code": "D2",
                },
            ]

        with patch(_PATCH_EXPORT, side_effect=_mock_export), \
             patch(_PATCH_LIST_IE, side_effect=_mock_ie), \
             patch(_PATCH_LIST_SHEETS, side_effect=_mock_catalog):
            result = await build_manifest(mock_db, project_id, ["D"], "template")

        assert len(result.files) == 1
        assert len(result.skipped) == 1
        s = result.skipped[0]
        assert isinstance(s, ManifestSkippedEntry)
        assert s.sheet_code == "D2-3"
        assert s.skip_reason == "resolve_instance_miss"
        assert s.sheet_name == "坏账D2-3"

    @pytest.mark.asyncio
    async def test_to_dict_serialization(self):
        """to_dict() 应生成可 JSON 序列化的 dict。"""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = str(uuid.uuid4())

        export_entries = [
            {
                "sheet_code": "D2-2",
                "api_prefix": "d2",
                "item_id": "D2-detail-rows",
                "import_order": 20,
                "depends_on_sheets": [],
                "wp_id": wp_id,
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-2",
                "storage_field": "remark",
            }
        ]

        async def _mock_export(*args, **kwargs):
            return export_entries

        async def _mock_ie(*args, **kwargs):
            return export_entries

        def _mock_catalog(*args, **kwargs):
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

        with patch(_PATCH_EXPORT, side_effect=_mock_export), \
             patch(_PATCH_LIST_IE, side_effect=_mock_ie), \
             patch(_PATCH_LIST_SHEETS, side_effect=_mock_catalog):
            result = await build_manifest(mock_db, project_id, ["D"], "template")

        d = result.to_dict()
        assert d["schema_version"] == "1.0"
        assert d["mode"] == "template"
        assert len(d["files"]) == 1
        assert d["files"][0]["zip_path"] == "D/D2/D2-2_明细表_模板.xlsx"
        assert d["files"][0]["addr_id"] == "D2/D2-2"

    @pytest.mark.asyncio
    async def test_exportable_filters_wp_id_none(self):
        """exportable() 应只返回 wp_id 非空的条目。"""
        manifest = BulkManifest(
            files=[
                ManifestFileEntry(
                    addr_id="D2/D2-1", wp_code="D2", parent_wp_code="D2",
                    sheet_code="D2-1", sheet_name="审定表", origin="standard",
                    api_prefix="d2", item_id="D2-adj", storage_field="remark",
                    wp_id="some-id", import_order=10, depends_on_sheets=[],
                    zip_path="D/D2/D2-1_审定表_模板.xlsx", sha256="",
                ),
                ManifestFileEntry(
                    addr_id="D2/D2-3", wp_code="D2", parent_wp_code="D2",
                    sheet_code="D2-3", sheet_name="坏账", origin="standard",
                    api_prefix="d2", item_id="D2-bd", storage_field="remark",
                    wp_id=None, import_order=30, depends_on_sheets=[],
                    zip_path="D/D2/D2-3_坏账_模板.xlsx", sha256="",
                ),
            ]
        )
        exportable = manifest.exportable()
        assert len(exportable) == 1
        assert exportable[0].sheet_code == "D2-1"

    @pytest.mark.asyncio
    async def test_multi_cycle(self):
        """多循环应合并到同一 manifest。"""
        mock_db = AsyncMock()
        project_id = uuid.uuid4()

        d_entries = [
            {
                "sheet_code": "D2-1",
                "api_prefix": "d2",
                "item_id": "D2-adj",
                "import_order": 10,
                "depends_on_sheets": [],
                "wp_id": str(uuid.uuid4()),
                "parent_wp_code": "D2",
                "addr_id": "D2/D2-1",
                "storage_field": "remark",
            }
        ]
        k_entries = [
            {
                "sheet_code": "K1-2",
                "api_prefix": "k1",
                "item_id": "K1-detail",
                "import_order": 10,
                "depends_on_sheets": [],
                "wp_id": str(uuid.uuid4()),
                "parent_wp_code": "K1",
                "addr_id": "K1/K1-2",
                "storage_field": "remark",
            }
        ]

        call_count = {"export": 0, "ie": 0}

        async def _mock_export(*args, **kwargs):
            call_count["export"] += 1
            cycle = args[2] if len(args) > 2 else kwargs.get("cycle", "D")
            return d_entries if cycle == "D" else k_entries

        async def _mock_ie(*args, **kwargs):
            call_count["ie"] += 1
            cycle = args[2] if len(args) > 2 else kwargs.get("cycle", "D")
            return d_entries if cycle == "D" else k_entries

        def _mock_catalog(*args, **kwargs):
            cycle = kwargs.get("cycle", args[0] if args else "D")
            if cycle == "D":
                return [{"addr_id": "D2/D2-1", "sheet_code": "D2-1",
                         "sheet_name": "审定表D2-1", "origin": "standard",
                         "cycle": "D", "parent_wp_code": "D2"}]
            return [{"addr_id": "K1/K1-2", "sheet_code": "K1-2",
                     "sheet_name": "明细K1-2", "origin": "standard",
                     "cycle": "K", "parent_wp_code": "K1"}]

        with patch(_PATCH_EXPORT, side_effect=_mock_export), \
             patch(_PATCH_LIST_IE, side_effect=_mock_ie), \
             patch(_PATCH_LIST_SHEETS, side_effect=_mock_catalog):
            result = await build_manifest(mock_db, project_id, ["D", "K"], "template")

        assert result.cycles == ["D", "K"]
        assert len(result.files) == 2
        assert result.files[0].sheet_code == "D2-1"
        assert result.files[1].sheet_code == "K1-2"
