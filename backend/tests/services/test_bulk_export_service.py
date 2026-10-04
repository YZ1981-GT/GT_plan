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
    SKIP_REASON_LABELS,
    _is_empty_xlsx,
    _render_readme,
    _sha256,
    export,
)
from app.services.bulk_tab.exceptions import BulkExportNothingToExportError
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
        """数据模式 README。

        🔴 **过期断言更正（spec `environment-hygiene…` Task 8.3）**：原断言
        ``"归档" in readme`` 在 HEAD 上就是红的 —— 数据模式的使用说明三句里从来没有
        「归档」二字（那是 `scenario_registry` 里 archive_export 场景的文案，不在 README）。
        改为断言真实存在的内容。
        """
        entry = _make_entry(sha256="abc123")
        manifest = _make_manifest(files=[entry], mode="data")
        readme = _render_readme(manifest)

        assert "数据" in readme
        assert "批量导入" in readme  # 数据模式使用说明第 2 句
        assert "D2-2" in readme

    def test_readme_includes_skipped(self):
        """未导出条目的原因用**中文**写进 README（Req 8.2）。

        契约变更：原先直接输出英文 `skip_reason` 代码（`no_adapter`），用户看不懂。
        现在 README / `_底稿目录.xlsx` / 零 Tab 拦截提示三处共用
        `SKIP_REASON_LABELS` 的中文标签；`manifest.json` 仍保留原始代码供程序读取。
        """
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

        assert "未导出原因" in readme
        assert SKIP_REASON_LABELS["no_adapter"] in readme
        assert "D2-X" in readme
        # 英文代码不再出现在用户可见文案里
        assert "no_adapter" not in readme

    def test_readme_lists_every_selected_cycle_even_with_zero_exports(self):
        """「各循环状态」逐个列出**所选**循环，含 0 张的（Req 8.1）。

        原实现的键取自已导出文件的 `zip_path` 首段 ⇒ 勾了但一张都没导出的循环
        在 README 里整个消失，恰是用户最需要解释的那些。
        """
        entry = _make_entry(sheet_code="D2-2", sha256="abc")
        manifest = _make_manifest(files=[entry], mode="data")
        manifest.cycles = ["D", "E", "F"]
        readme = _render_readme(manifest)

        status_section = readme.split("各循环状态:")[1]
        assert "D: 导出 1 张" in status_section
        # E / F 一张都没有，但必须出现
        assert "E: 导出 0 张" in status_section
        assert "F: 导出 0 张" in status_section

    def test_readme_explains_unsupported_cycles(self):
        """整个循环未接入导入导出时，README 给出循环名与原因（Req 8.5）。"""
        from app.services.bulk_tab.scenario_registry import UNSUPPORTED_CYCLE_REASON

        entry = _make_entry(sheet_code="D2-2", sha256="abc")
        manifest = _make_manifest(files=[entry], mode="data")
        manifest.cycles = ["D", "E"]
        manifest.unsupported_cycles = ["E"]
        readme = _render_readme(manifest)

        assert "未纳入的循环" in readme
        assert UNSUPPORTED_CYCLE_REASON in readme
        assert "货币资金" in readme  # CYCLE_NAMES["E"]
        # 不支持的循环不再被算成「导出 0 张」，而是明确写「未纳入」
        status_section = readme.split("各循环状态:")[1]
        assert "E: 未纳入" in status_section

    def test_readme_extra_files_reflect_what_was_written(self):
        """「附加文件」段按**实际写入**逐行生成（Req 8.2）。

        原实现固定列 5 个文件、再用「缺失即该项暂无数据」一句带过，模板包里也照列 ——
        用户无法区分「这项没数据」与「这个包压根不该有这项」。
        """
        entry = _make_entry(sheet_code="D2-2", sha256="abc")

        # 数据模式且真写了两个附加文件 ⇒ 逐个列出，不列没写的
        data_manifest = _make_manifest(files=[entry], mode="data")
        data_readme = _render_readme(
            data_manifest,
            ["_报表/财务报表.xlsx", "_试算表/试算平衡表.xlsx"],
        )
        assert "_报表/财务报表.xlsx" in data_readme
        assert "_试算表/试算平衡表.xlsx" in data_readme
        assert "_附注/财务报表附注.docx" not in data_readme
        assert "_报表/财务报表_未审数.xlsx" not in data_readme

        # 模板模式恒无附加文件 ⇒ 给出「属于项目数据」的说明，而不是「暂无数据」
        tpl_readme = _render_readme(_make_manifest(files=[entry], mode="template"), [])
        assert "_报表/财务报表.xlsx" not in tpl_readme
        assert "模板包不附带报表、附注、试算表" in tpl_readme
        # 两种模式都保留底稿目录与 manifest
        for text in (data_readme, tpl_readme):
            assert "_底稿目录.xlsx" in text
            assert "manifest.json" in text

    def test_readme_only_lists_exported_files(self):
        """sha256 为空的 entry 不列入文件清单。

        🔴 **过期断言更正**：原代码 `readme.split("## 文件清单")[1]` 在 HEAD 上就抛
        IndexError —— README 的小节标题是 `文件清单`，从来没有 `## ` 前缀（那是
        Markdown 习惯，而 README 是纯文本 + 横线分隔）。同时补上原先缺失的负向断言。
        """
        entry_ok = _make_entry(sheet_code="D2-2", sha256="abc")
        entry_empty = _make_entry(sheet_code="D2-3", sha256="")
        manifest = _make_manifest(files=[entry_ok, entry_empty], mode="template")
        readme = _render_readme(manifest)

        file_list_section = readme.split("文件清单")[-1]
        assert "D2-2" in file_list_section
        # 原测试只断言 D2-2 在，删掉 `if f.sha256` 也照样绿 ⇒ 补负向断言
        assert "D2-3" not in file_list_section


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
        # 🔴 **过期断言更正**：原断言 `len(xlsx_files) == 2` 在 HEAD 上就是红的 ——
        # `_底稿目录.xlsx` 从 Step 3c 起就无条件写入，实际是 3 个。按口径分开数：
        # 底稿 xlsx 恰 2 张，附加文件只有底稿目录（模板模式不含报表 / 附注 / 试算表）。
        sheet_xlsx = [n for n in names if n.endswith(".xlsx") and not n.startswith("_")]
        assert sheet_xlsx == ["D/D2/D2-1_明细表_模板.xlsx", "D/D2/D2-2_明细表_模板.xlsx"]
        assert "_底稿目录.xlsx" in names
        # Req 8.2：模板模式不附带项目数据
        assert not [n for n in names if n.startswith(("_报表/", "_附注/", "_试算表/"))]

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
async def test_export_all_tabs_fail_is_rejected_not_an_empty_zip():
    """🔴 **契约反转**：一张 Tab 都没导出成功 ⇒ 422 拒绝，不再产出空 ZIP（Req 8.1）。

    原测试名 `test_export_all_tabs_fail_still_produces_zip` 钉的是「全部失败仍产出
    ZIP」。**2026-09-30 用户裁决改掉它**：真栈实测中导出 0 张底稿时界面照样提示
    「模板 ZIP 已导出」，用户下载到一个只有 README 的包，完全不知道发生了什么。

    单张失败仍 fail-soft（见 `test_export_fail_soft_no_adapter` 与下面的
    `test_export_one_success_keeps_fail_soft`）—— 归档 spec
    `workpaper-bulk-tab-import-export` 的 Req 1.6 / 1.8 只规定「单 Tab 跳过不使整包
    失败」，没有规定零 Tab 也要出包。
    """
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
        with pytest.raises(BulkExportNothingToExportError) as exc_info:
            await export(
                db=mock_db,
                project_id=project_id,
                cycles=["D"],
                mode="template",
            )

    exc = exc_info.value
    assert exc.status_code == 422
    # 用户看到的是中文原因，且点明这一类问题（导出失败）
    assert "没有可导出的底稿" in str(exc)
    assert "导出时出错" in str(exc)
    # counts 按类别计数，供日志 / 测试区分
    assert exc.counts.get("export_failed") == 1


@pytest.mark.asyncio
async def test_export_one_success_keeps_fail_soft():
    """只要有 1 张成功，其余跳过仍按原 fail-soft 规则只记进 manifest（Req 8.1 末句）。

    这条是上一个测试的正向对照：证明零 Tab 拦截**没有**把 fail-soft 一并改成 fail-hard。
    """
    mock_db = AsyncMock()
    project_id = uuid.uuid4()

    ok_entry = _make_entry(sheet_code="D2-1", api_prefix="d2")
    bad_entry = _make_entry(sheet_code="D2-9", api_prefix="d2")
    manifest = _make_manifest(files=[ok_entry, bad_entry], mode="template")
    xlsx_data = _make_xlsx_with_data()

    async def _mock_build_manifest(*args, **kwargs):
        return manifest

    async def _mock_export_tab(db, wp_id, api_prefix, sheet_code, mode):
        if sheet_code == "D2-9":
            raise RuntimeError("这一张失败")
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
        names = zf.namelist()
        assert "manifest.json" in names
        content = json.loads(zf.read("manifest.json"))
        assert [f["sheet_code"] for f in content["files"]] == ["D2-1"]
        assert [s["sheet_code"] for s in content["skipped"]] == ["D2-9"]
        # manifest.json 里仍是原始英文代码（供程序读取），只有用户可见文案改中文
        assert content["skipped"][0]["skip_reason"] == "export_failed"
