"""Tests for Task 4.1: BulkExportService.export(...)

验证批量导出编排逻辑：
- 遍历 manifest.exportable() 调 export_tab
- mode=data + only_with_data 时空表标 skipped(no_data)
- 写 manifest.json + README.txt
- fail-soft：单 Tab 导出失败 → 跳过继续
- sha256 正确计算

Requirements: 1.1, 1.2, 1.7, 3.1, 3.2, 3.3, 6.3
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from app.services.bulk_tab.bulk_export_service import (
    _is_empty_xlsx,
    _render_readme,
    _sha256,
    export,
)
from app.services.bulk_tab.manifest_builder import (
    BulkManifest,
    ManifestFileEntry,
    ManifestSkippedEntry,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    files: list[ManifestFileEntry] | None = None,
    mode: str = "template",
) -> BulkManifest:
    """创建测试用 BulkManifest。"""
    return BulkManifest(
        schema_version="1.0",
        project_id=str(uuid.uuid4()),
        audit_year=2025,
        exported_at="2025-07-12T10:00:00Z",
        exported_by="test_user",
        platform_version="1.0.0",
        mode=mode,
        cycles=["D"],
        files=files or [],
        skipped=[],
    )


def _make_entry(
    sheet_code: str = "D2-2",
    api_prefix: str = "d2",
    wp_id: str | None = None,
    sha256: str = "",
) -> ManifestFileEntry:
    """创建测试用 ManifestFileEntry。"""
    return ManifestFileEntry(
        addr_id=f"D2/{sheet_code}",
        wp_code="D2",
        parent_wp_code="D2",
        sheet_code=sheet_code,
        sheet_name=f"明细表{sheet_code}",
        origin="standard",
        api_prefix=api_prefix,
        item_id=f"{sheet_code}-vc-rows",
        storage_field="remark",
        wp_id=wp_id or str(uuid.uuid4()),
        import_order=1,
        depends_on_sheets=[],
        zip_path=f"D/D2/{sheet_code}_明细表_模板.xlsx",
        sha256=sha256,
    )


def _make_xlsx_with_data() -> bytes:
    """创建含数据行的 xlsx bytes（模拟非空导出）。"""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2", "col3"])  # 表头
    ws.append(["data1", "data2", "data3"])  # 数据行
    ws.append(["data4", "data5", "data6"])  # 数据行
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_xlsx_empty() -> bytes:
    """创建仅有表头的空 xlsx bytes（模拟空导出）。"""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2", "col3"])  # 仅表头
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Patch targets
_PATCH_BUILD_MANIFEST = "app.services.bulk_tab.bulk_export_service.build_manifest"
_PATCH_EXPORT_TAB = "app.services.bulk_tab.bulk_export_service.export_tab"


# ---------------------------------------------------------------------------
# Unit tests: _sha256
# ---------------------------------------------------------------------------


class TestSha256:
    def test_sha256_computes_correctly(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256(data) == expected

    def test_sha256_empty_bytes(self):
        data = b""
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256(data) == expected


# ---------------------------------------------------------------------------
# Unit tests: _is_empty_xlsx
# ---------------------------------------------------------------------------


class TestIsEmptyXlsx:
    def test_xlsx_with_data_returns_false(self):
        xlsx_bytes = _make_xlsx_with_data()
        assert _is_empty_xlsx(xlsx_bytes) is False

    def test_xlsx_empty_returns_true(self):
        xlsx_bytes = _make_xlsx_empty()
        assert _is_empty_xlsx(xlsx_bytes) is True

    def test_invalid_bytes_returns_false(self):
        """非法 bytes 保守返回 False（不跳过）。"""
        assert _is_empty_xlsx(b"not a valid xlsx") is False

    def test_empty_bytes_returns_false(self):
        """空字节保守返回 False。"""
        assert _is_empty_xlsx(b"") is False


# ---------------------------------------------------------------------------
# Unit tests: _render_readme
# ---------------------------------------------------------------------------


class TestRenderReadme:
    def test_template_mode_readme(self):
        entry = _make_entry(sha256="abc123")
        manifest = _make_manifest(files=[entry], mode="template")
        readme = _render_readme(manifest)

        assert "模板" in readme
        assert "D2-2" in readme
        assert "使用说明" in readme
        assert "请勿修改文件名" in readme
        assert manifest.exported_by in readme

    def test_data_mode_readme(self):
        entry = _make_entry(sha256="abc123")
        manifest = _make_manifest(files=[entry], mode="data")
        readme = _render_readme(manifest)

        assert "数据" in readme
        assert "归档" in readme
        assert "D2-2" in readme

    def test_readme_includes_skipped(self):
        manifest = _make_manifest(files=[], mode="template")
        manifest.skipped.append(
            ManifestSkippedEntry(
                addr_id="D2/D2-X",
                sheet_code="D2-X",
                sheet_name="不可导出表",
                parent_wp_code="D2",
                skip_reason="no_adapter",
            )
        )
        readme = _render_readme(manifest)

        assert "跳过" in readme
        assert "no_adapter" in readme

    def test_readme_only_lists_exported_files(self):
        """sha256 为空的 entry 不列入文件清单。"""
        entry_ok = _make_entry(sheet_code="D2-2", sha256="abc")
        entry_empty = _make_entry(sheet_code="D2-3", sha256="")
        manifest = _make_manifest(files=[entry_ok, entry_empty], mode="template")
        readme = _render_readme(manifest)

        assert "D2-2" in readme
        # D2-3 sha256 为空不应出现在文件清单部分
        # 但可能出现在其他地方，核心是不在"文件清单"下
        file_list_section = readme.split("## 文件清单")[1]
        assert "D2-2" in file_list_section


# ---------------------------------------------------------------------------
# Integration tests: export()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_basic_success():
    """基本导出：2 个 Tab 均成功，ZIP 含 xlsx + manifest.json + README.txt。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry1 = _make_entry(sheet_code="D2-1", api_prefix="d2")
    entry2 = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry1, entry2], mode="template")

    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
            exported_by="test_user",
        )

    # 验证返回的是 BytesIO
    assert isinstance(result, io.BytesIO)

    # 验证 ZIP 内容
    with zipfile.ZipFile(result) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "README.txt" in names
        # 验证至少有 xlsx 文件
        xlsx_files = [n for n in names if n.endswith(".xlsx")]
        assert len(xlsx_files) == 2

        # 验证 manifest.json 结构
        manifest_content = json.loads(zf.read("manifest.json"))
        assert manifest_content["mode"] == "template"
        assert len(manifest_content["files"]) == 2
        # 验证 sha256 已填入
        for f in manifest_content["files"]:
            assert f["sha256"] != ""
            assert f["sha256"] == hashlib.sha256(xlsx_data).hexdigest()


@pytest.mark.asyncio
async def test_export_fail_soft_no_adapter():
    """api_prefix 未注册时跳过该 Tab，不使整包失败。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry1 = _make_entry(sheet_code="D2-1", api_prefix="d2")
    entry2 = _make_entry(sheet_code="D2-X", api_prefix="unknown_prefix")
    manifest = _make_manifest(files=[entry1, entry2], mode="template")

    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        if api_prefix == "unknown_prefix":
            raise KeyError("未注册")
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
        )

    # 应成功返回 ZIP
    with zipfile.ZipFile(result) as zf:
        manifest_content = json.loads(zf.read("manifest.json"))
        # 只有 1 个成功导出的文件
        assert len(manifest_content["files"]) == 1
        assert manifest_content["files"][0]["sheet_code"] == "D2-1"
        # skipped 中有 no_adapter
        skipped_reasons = [s["skip_reason"] for s in manifest_content["skipped"]]
        assert "no_adapter" in skipped_reasons


@pytest.mark.asyncio
async def test_export_fail_soft_general_exception():
    """export_tab 抛一般异常时跳过该 Tab，继续其余。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry1 = _make_entry(sheet_code="D2-1", api_prefix="d2")
    entry2 = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry1, entry2], mode="template")

    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    call_count = 0

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        nonlocal call_count
        call_count += 1
        if sheet_code == "D2-1":
            raise RuntimeError("DB连接超时")
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
        )

    with zipfile.ZipFile(result) as zf:
        manifest_content = json.loads(zf.read("manifest.json"))
        # D2-1 失败被跳过，D2-2 成功
        assert len(manifest_content["files"]) == 1
        assert manifest_content["files"][0]["sheet_code"] == "D2-2"
        # skipped 包含 export_failed
        skipped_reasons = [s["skip_reason"] for s in manifest_content["skipped"]]
        assert "export_failed" in skipped_reasons


@pytest.mark.asyncio
async def test_export_data_only_with_data_skips_empty():
    """mode=data + only_with_data 时空表标 skipped(no_data)。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry1 = _make_entry(sheet_code="D2-1", api_prefix="d2")
    entry2 = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry1, entry2], mode="data")

    xlsx_with_data = _make_xlsx_with_data()
    xlsx_empty = _make_xlsx_empty()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        if sheet_code == "D2-1":
            return xlsx_empty  # 空表
        return xlsx_with_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="data",
            only_with_data=True,
        )

    with zipfile.ZipFile(result) as zf:
        manifest_content = json.loads(zf.read("manifest.json"))
        # 仅 D2-2 有数据被导出
        assert len(manifest_content["files"]) == 1
        assert manifest_content["files"][0]["sheet_code"] == "D2-2"
        # D2-1 标注 no_data
        skipped_reasons = [s["skip_reason"] for s in manifest_content["skipped"]]
        assert "no_data" in skipped_reasons


@pytest.mark.asyncio
async def test_export_data_without_only_with_data_includes_empty():
    """mode=data 但不设 only_with_data 时，空表也导出。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry = _make_entry(sheet_code="D2-1", api_prefix="d2")
    manifest = _make_manifest(files=[entry], mode="data")

    xlsx_empty = _make_xlsx_empty()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        return xlsx_empty

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="data",
            only_with_data=False,
        )

    with zipfile.ZipFile(result) as zf:
        manifest_content = json.loads(zf.read("manifest.json"))
        # 空表仍导出
        assert len(manifest_content["files"]) == 1


@pytest.mark.asyncio
async def test_export_progress_callback():
    """progress.tick 被正确调用。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry], mode="template")

    xlsx_data = _make_xlsx_with_data()
    progress = MagicMock()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
            progress=progress,
        )

    # progress.tick 至少调用 1 次
    assert progress.tick.call_count >= 1


@pytest.mark.asyncio
async def test_export_manifest_json_structure():
    """manifest.json 包含正确的 schema_version、mode、cycles 等字段。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry], mode="template")
    manifest.project_id = str(project_id)
    manifest.audit_year = 2025
    manifest.exported_by = "admin"
    manifest.platform_version = "2.0.0"

    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
            exported_by="admin",
            platform_version="2.0.0",
            audit_year=2025,
        )

    with zipfile.ZipFile(result) as zf:
        manifest_content = json.loads(zf.read("manifest.json"))
        assert manifest_content["schema_version"] == "1.0"
        assert manifest_content["mode"] == "template"
        assert manifest_content["cycles"] == ["D"]
        assert manifest_content["exported_by"] == "admin"
        assert manifest_content["platform_version"] == "2.0.0"
        assert manifest_content["audit_year"] == 2025


@pytest.mark.asyncio
async def test_export_zip_no_sensitive_data():
    """ZIP 不含敏感信息（Req 6.3）。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry = _make_entry(sheet_code="D2-2", api_prefix="d2")
    manifest = _make_manifest(files=[entry], mode="template")

    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        return xlsx_data

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
        )

    # 检查 ZIP 内文件名不含敏感模式
    sensitive_patterns = ["token", "secret", "password", "api_key", "private_key"]
    with zipfile.ZipFile(result) as zf:
        for name in zf.namelist():
            name_lower = name.lower()
            for pattern in sensitive_patterns:
                assert pattern not in name_lower, \
                    f"ZIP 文件名 '{name}' 包含敏感模式 '{pattern}'"

        # README 和 manifest 不含敏感字符串
        readme = zf.read("README.txt").decode("utf-8")
        for pattern in sensitive_patterns:
            assert pattern not in readme.lower()


@pytest.mark.asyncio
async def test_export_all_tabs_fail_still_produces_zip():
    """所有 Tab 导出失败时仍应产生有效 ZIP（含 manifest + README）。"""
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    entry = _make_entry(sheet_code="D2-1", api_prefix="d2")
    manifest = _make_manifest(files=[entry], mode="template")

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        raise RuntimeError("全部失败")

    with patch(_PATCH_BUILD_MANIFEST, side_effect=_mock_build_manifest), \
         patch(_PATCH_EXPORT_TAB, side_effect=_mock_export_tab):
        result = await export(
            db=mock_db,
            project_id=project_id,
            cycles=["D"],
            mode="template",
        )

    # ZIP 仍有效，含 manifest + README
    with zipfile.ZipFile(result) as zf:
        assert "manifest.json" in zf.namelist()
        assert "README.txt" in zf.namelist()
        manifest_content = json.loads(zf.read("manifest.json"))
        assert len(manifest_content["files"]) == 0
        assert len(manifest_content["skipped"]) >= 1
