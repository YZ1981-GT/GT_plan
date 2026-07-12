"""Tests for Task 4.3: bulk_import_service.dry_run(...)

验证 dry_run 校验 manifest/完整性/表头/工作流状态门禁，不写库，返回逐文件预检报告。

Requirements: 2.3
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from app.services.bulk_tab.bulk_import_service import (
    ImportReport,
    SheetReport,
    dry_run,
    align,
    AlignedItem,
    ImportPlan,
)
from app.services.bulk_tab.zip_handler import (
    ZipManifestMissing,
    ZipSizeLimitExceeded,
)


# ---------------------------------------------------------------------------
# Helpers: 构建测试用 ZIP bytes
# ---------------------------------------------------------------------------


def _make_xlsx_bytes(content: str = "test") -> bytes:
    """生成一个假 xlsx 内容（纯 bytes 占位）。"""
    return content.encode("utf-8")


def _make_zip(
    files: dict[str, bytes] | None = None,
    manifest: dict | None = None,
    *,
    include_manifest: bool = True,
    compute_sha256: bool = True,
) -> bytes:
    """构建测试用 ZIP bytes。"""
    if files is None:
        files = {}

    if manifest is None and include_manifest:
        manifest = {
            "schema_version": "1.0",
            "project_id": str(uuid.uuid4()),
            "cycles": ["D"],
            "files": [],
            "skipped": [],
        }
        for zip_path, content in files.items():
            sha = hashlib.sha256(content).hexdigest() if compute_sha256 else ""
            filename = zip_path.rsplit("/", 1)[-1] if "/" in zip_path else zip_path
            sheet_code = filename.split("_")[0]
            manifest["files"].append({
                "sheet_code": sheet_code,
                "zip_path": zip_path,
                "sha256": sha,
                "wp_id": str(uuid.uuid4()),
                "api_prefix": "d2",
                "item_id": f"{sheet_code}-rows",
                "import_order": 1,
                "depends_on_sheets": [],
            })

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
        if include_manifest and manifest is not None:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))

    return buf.getvalue()


def _make_standard_zip(
    sheet_codes: list[str] | None = None,
    *,
    wp_ids: dict[str, str] | None = None,
    extra_zip_files: dict[str, bytes] | None = None,
    missing_files: list[str] | None = None,
) -> tuple[bytes, dict]:
    """构建标准测试 ZIP（含 manifest + files）。

    Returns:
        (zip_bytes, manifest_dict)
    """
    if sheet_codes is None:
        sheet_codes = ["D2-1", "D2-2", "D2-7"]
    if wp_ids is None:
        wp_ids = {code: str(uuid.uuid4()) for code in sheet_codes}
    if missing_files is None:
        missing_files = []

    files: dict[str, bytes] = {}
    manifest_files: list[dict] = []

    for code in sheet_codes:
        zip_path = f"D/D2/{code}_明细表_数据.xlsx"
        content = _make_xlsx_bytes(f"data-for-{code}")
        sha = hashlib.sha256(content).hexdigest()

        manifest_files.append({
            "sheet_code": code,
            "zip_path": zip_path,
            "sha256": sha,
            "wp_id": wp_ids.get(code, str(uuid.uuid4())),
            "api_prefix": "d2",
            "item_id": f"{code}-rows",
            "import_order": sheet_codes.index(code) + 1,
            "depends_on_sheets": [],
        })

        if code not in missing_files:
            files[zip_path] = content

    manifest = {
        "schema_version": "1.0",
        "project_id": str(uuid.uuid4()),
        "cycles": ["D"],
        "files": manifest_files,
        "skipped": [],
    }

    if extra_zip_files:
        files.update(extra_zip_files)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))

    return buf.getvalue(), manifest


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

_PATCH_LIST_IMPORT = "app.services.wp_bulk_tab_export.list_import_sheets"
_PATCH_GET_STATUSES = "app.services.bulk_tab.bulk_import_service._get_wp_statuses"


async def _mock_list_import_sheets_returns(entries):
    """工厂函数: 返回一个 mock，给出指定 entries。"""
    async def _mock(*args, **kwargs):
        return entries
    return _mock


# ---------------------------------------------------------------------------
# Tests: dry_run 核心逻辑
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry_run 预检核心逻辑测试。"""

    @pytest.mark.asyncio
    async def test_dry_run_returns_import_report(self):
        """dry_run 应返回 ImportReport 实例且 dry_run=True。"""
        zip_bytes, _ = _make_standard_zip(sheet_codes=["D2-1"])
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [{"sheet_code": "D2-1", "api_prefix": "d2", "item_id": "D2-1-rows",
                     "import_order": 1, "depends_on_sheets": [], "wp_id": "wp-1"}]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={}):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        assert isinstance(report, ImportReport)
        assert report.dry_run is True
        assert report.strategy == "overwrite"
        assert report.import_id  # 非空

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write_db(self):
        """dry_run 不应调用 db.flush/commit（Req 2.3）。"""
        zip_bytes, _ = _make_standard_zip(sheet_codes=["D2-1"])
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return []

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={}):
            await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        mock_db.commit.assert_not_called()
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_invalid_zip_returns_failed(self):
        """传入非法 ZIP 应在报告中标 failed。"""
        mock_db = AsyncMock()
        report = await dry_run(mock_db, str(uuid.uuid4()), b"not a zip", "overwrite")

        # dry_run 内部 catch 异常并标注报告
        assert isinstance(report, ImportReport)
        assert any(s.status == "failed" for s in report.sheets)

    @pytest.mark.asyncio
    async def test_dry_run_no_manifest_returns_failed(self):
        """ZIP 中无 manifest.json 应在报告中标 failed。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("some_file.xlsx", b"data")
        mock_db = AsyncMock()
        report = await dry_run(mock_db, str(uuid.uuid4()), buf.getvalue(), "overwrite")

        assert isinstance(report, ImportReport)
        assert any(s.status == "failed" for s in report.sheets)

    @pytest.mark.asyncio
    async def test_dry_run_marks_missing_files(self):
        """manifest 中声明但 ZIP 中缺失的文件应标 missing（或 integrity 校验失败）。

        当 manifest 中 sha256 非空且对应文件不在 ZIP 中时，verify_integrity 会
        先捕获并报 failed（__integrity__）。若 sha256 为空，则跳过完整性检查，
        align 步骤标注 missing。两种路径都正确反映"文件缺失"。
        """
        wp_ids = {"D2-1": str(uuid.uuid4()), "D2-2": str(uuid.uuid4()), "D2-7": str(uuid.uuid4())}

        # 构建 ZIP: D2-7 不放入 ZIP，但 manifest sha256 留空（跳过完整性）
        files: dict[str, bytes] = {}
        manifest_files: list[dict] = []
        for code in ["D2-1", "D2-2", "D2-7"]:
            zip_path = f"D/D2/{code}_明细表_数据.xlsx"
            content = _make_xlsx_bytes(f"data-for-{code}")
            sha = hashlib.sha256(content).hexdigest() if code != "D2-7" else ""
            manifest_files.append({
                "sheet_code": code, "zip_path": zip_path, "sha256": sha,
                "wp_id": wp_ids[code], "api_prefix": "d2",
                "item_id": f"{code}-rows", "import_order": ["D2-1", "D2-2", "D2-7"].index(code) + 1,
                "depends_on_sheets": [],
            })
            if code != "D2-7":
                files[zip_path] = content

        manifest = {"schema_version": "1.0", "project_id": str(uuid.uuid4()),
                    "cycles": ["D"], "files": manifest_files, "skipped": []}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p, c in files.items():
                zf.writestr(p, c)
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zip_bytes = buf.getvalue()
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [
                {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": wp_ids["D2-1"],
                 "import_order": 1, "depends_on_sheets": []},
                {"sheet_code": "D2-2", "api_prefix": "d2", "wp_id": wp_ids["D2-2"],
                 "import_order": 2, "depends_on_sheets": []},
                {"sheet_code": "D2-7", "api_prefix": "d2", "wp_id": wp_ids["D2-7"],
                 "import_order": 3, "depends_on_sheets": []},
            ]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={
                 wp_ids["D2-1"]: "draft",
                 wp_ids["D2-2"]: "draft",
                 wp_ids["D2-7"]: "draft",
             }):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        missing_sheets = [s for s in report.sheets if s.status == "missing"]
        assert len(missing_sheets) == 1
        assert missing_sheets[0].sheet_code == "D2-7"

    @pytest.mark.asyncio
    async def test_dry_run_marks_unlisted_files(self):
        """ZIP 中存在但 manifest 未登记的 xlsx 应标 unlisted。"""
        extra_files = {"D/D2/EXTRA_unknown_data.xlsx": b"extra content"}
        wp_ids = {"D2-1": str(uuid.uuid4())}
        zip_bytes, _ = _make_standard_zip(
            sheet_codes=["D2-1"],
            wp_ids=wp_ids,
            extra_zip_files=extra_files,
        )
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [{"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": wp_ids["D2-1"],
                     "import_order": 1, "depends_on_sheets": []}]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={wp_ids["D2-1"]: "draft"}):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        unlisted_sheets = [s for s in report.sheets if s.status == "unlisted"]
        assert len(unlisted_sheets) >= 1

    @pytest.mark.asyncio
    async def test_dry_run_blocks_review_passed_wp(self):
        """review_passed 状态的底稿应标 blocked_by_status（Req 9.1）。"""
        wp_id_blocked = str(uuid.uuid4())
        wp_id_ok = str(uuid.uuid4())
        zip_bytes, _ = _make_standard_zip(
            sheet_codes=["D2-1", "D2-2"],
            wp_ids={"D2-1": wp_id_blocked, "D2-2": wp_id_ok},
        )
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [
                {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": wp_id_blocked,
                 "import_order": 1, "depends_on_sheets": []},
                {"sheet_code": "D2-2", "api_prefix": "d2", "wp_id": wp_id_ok,
                 "import_order": 2, "depends_on_sheets": []},
            ]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={
                 wp_id_blocked: "review_passed",
                 wp_id_ok: "draft",
             }):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        blocked = [s for s in report.sheets if s.status == "blocked_by_status"]
        assert len(blocked) == 1
        assert blocked[0].sheet_code == "D2-1"
        assert blocked[0].reason == "review_passed"

        success = [s for s in report.sheets if s.status == "success"]
        assert len(success) == 1
        assert success[0].sheet_code == "D2-2"

    @pytest.mark.asyncio
    async def test_dry_run_blocks_archived_wp(self):
        """archived 状态的底稿应标 blocked_by_status（Req 9.1）。"""
        wp_id = str(uuid.uuid4())
        zip_bytes, _ = _make_standard_zip(
            sheet_codes=["D2-1"],
            wp_ids={"D2-1": wp_id},
        )
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [{"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": wp_id,
                     "import_order": 1, "depends_on_sheets": []}]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={wp_id: "archived"}):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        blocked = [s for s in report.sheets if s.status == "blocked_by_status"]
        assert len(blocked) == 1
        assert blocked[0].reason == "archived"

    @pytest.mark.asyncio
    async def test_dry_run_writable_marks_success(self):
        """writable 状态的底稿预检应标 success。"""
        wp_id = str(uuid.uuid4())
        zip_bytes, _ = _make_standard_zip(
            sheet_codes=["D2-1"],
            wp_ids={"D2-1": wp_id},
        )
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return [{"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": wp_id,
                     "import_order": 1, "depends_on_sheets": []}]

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={wp_id: "draft"}):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        success = [s for s in report.sheets if s.status == "success"]
        assert len(success) == 1
        assert success[0].sheet_code == "D2-1"

    @pytest.mark.asyncio
    async def test_dry_run_strategy_echoed_in_report(self):
        """ImportReport 应回显所用 strategy（Req 8.4）。"""
        zip_bytes, _ = _make_standard_zip(sheet_codes=["D2-1"])
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return []

        for strat in ("overwrite", "fill-empty", "reject"):
            with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
                 patch(_PATCH_GET_STATUSES, return_value={}):
                report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, strat)
            assert report.strategy == strat

    @pytest.mark.asyncio
    async def test_dry_run_to_dict_serializable(self):
        """ImportReport.to_dict() 应返回可 JSON 序列化的 dict。"""
        zip_bytes, _ = _make_standard_zip(sheet_codes=["D2-1"])
        mock_db = AsyncMock()

        async def mock_lis(*a, **kw):
            return []

        with patch(_PATCH_LIST_IMPORT, side_effect=mock_lis), \
             patch(_PATCH_GET_STATUSES, return_value={}):
            report = await dry_run(mock_db, str(uuid.uuid4()), zip_bytes, "overwrite")

        d = report.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)
        assert "import_id" in serialized
        assert "dry_run" in serialized
        assert d["dry_run"] is True


# ---------------------------------------------------------------------------
# Tests: align() function
# ---------------------------------------------------------------------------


class TestAlign:
    """align() 对齐逻辑测试。"""

    def test_align_basic_match(self):
        """manifest 与 topo 完全匹配时无 missing/unlisted。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_data.xlsx",
             "wp_id": "wp1", "api_prefix": "d2", "import_order": 1, "depends_on_sheets": []},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": "wp1",
             "import_order": 1, "depends_on_sheets": []},
        ]
        zip_file_list = ["D/D2/D2-1_data.xlsx", "manifest.json"]

        plan = align(manifest_files, topo_sheets, zip_file_list)
        assert len(plan.items) == 1
        assert plan.items[0].missing is False
        assert len(plan.unlisted_paths) == 0

    def test_align_marks_missing(self):
        """manifest 中有但 ZIP 中无文件应标 missing。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_data.xlsx",
             "wp_id": "wp1", "api_prefix": "d2", "import_order": 1},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": "wp1",
             "import_order": 1, "depends_on_sheets": []},
        ]
        zip_file_list = ["manifest.json"]  # 缺少 D2-1_data.xlsx

        plan = align(manifest_files, topo_sheets, zip_file_list)
        assert len(plan.items) == 1
        assert plan.items[0].missing is True

    def test_align_marks_unlisted(self):
        """ZIP 中有但 manifest 中无的 xlsx 应标 unlisted。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_data.xlsx",
             "wp_id": "wp1", "api_prefix": "d2", "import_order": 1},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": "wp1",
             "import_order": 1, "depends_on_sheets": []},
        ]
        zip_file_list = [
            "D/D2/D2-1_data.xlsx",
            "D/D2/EXTRA_unlisted.xlsx",  # unlisted
            "manifest.json",
        ]

        plan = align(manifest_files, topo_sheets, zip_file_list)
        assert len(plan.items) == 1
        assert plan.items[0].missing is False
        assert "D/D2/EXTRA_unlisted.xlsx" in plan.unlisted_paths

    def test_align_preserves_topo_order(self):
        """对齐结果应保持 topo_sheets 的拓扑顺序。"""
        manifest_files = [
            {"sheet_code": "D2-2", "zip_path": "D/D2/D2-2_data.xlsx",
             "wp_id": "wp2", "api_prefix": "d2", "import_order": 2},
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_data.xlsx",
             "wp_id": "wp1", "api_prefix": "d2", "import_order": 1},
        ]
        # topo 顺序: D2-1 先于 D2-2
        topo_sheets = [
            {"sheet_code": "D2-1", "api_prefix": "d2", "wp_id": "wp1",
             "import_order": 1, "depends_on_sheets": []},
            {"sheet_code": "D2-2", "api_prefix": "d2", "wp_id": "wp2",
             "import_order": 2, "depends_on_sheets": ["D2-1"]},
        ]
        zip_file_list = [
            "D/D2/D2-1_data.xlsx", "D/D2/D2-2_data.xlsx", "manifest.json",
        ]

        plan = align(manifest_files, topo_sheets, zip_file_list)
        assert len(plan.items) == 2
        assert plan.items[0].sheet_code == "D2-1"
        assert plan.items[1].sheet_code == "D2-2"


# ---------------------------------------------------------------------------
# Tests: ImportReport / SheetReport data models
# ---------------------------------------------------------------------------


class TestDataModels:
    """数据模型单元测试。"""

    def test_sheet_report_to_dict_minimal(self):
        """SheetReport 最小 dict 输出。"""
        sr = SheetReport(sheet_code="D2-1", status="success", rows=10)
        d = sr.to_dict()
        assert d["sheet_code"] == "D2-1"
        assert d["status"] == "success"
        assert d["rows"] == 10

    def test_sheet_report_to_dict_with_reason(self):
        """SheetReport 含 reason 时输出 reason。"""
        sr = SheetReport(
            sheet_code="D2-7",
            status="blocked_by_status",
            reason="review_passed",
        )
        d = sr.to_dict()
        assert d["reason"] == "review_passed"

    def test_import_report_summary_property(self):
        """summary 应正确统计各状态数量。"""
        report = ImportReport()
        report.sheets = [
            SheetReport(sheet_code="A", status="success"),
            SheetReport(sheet_code="B", status="success"),
            SheetReport(sheet_code="C", status="blocked_by_status"),
            SheetReport(sheet_code="D", status="missing"),
            SheetReport(sheet_code="E", status="failed"),
            SheetReport(sheet_code="F", status="unlisted"),
            SheetReport(sheet_code="G", status="conflict_rejected"),
        ]
        summary = report.summary
        assert summary["success"] == 2
        assert summary["blocked"] == 1
        assert summary["missing"] == 1
        assert summary["failed"] == 1
        assert summary["unlisted"] == 1
        assert summary["conflict_rejected"] == 1

    def test_import_report_to_dict(self):
        """to_dict 序列化完整。"""
        report = ImportReport(strategy="fill-empty", dry_run=True)
        report.mark("D2-1", "success")
        d = report.to_dict()
        assert d["strategy"] == "fill-empty"
        assert d["dry_run"] is True
        assert len(d["sheets"]) == 1

    def test_import_plan_writable_wp_ids(self):
        """writable_wp_ids 排除 blocked 和 missing。"""
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        id3 = str(uuid.uuid4())
        plan = ImportPlan(items=[
            AlignedItem(sheet_code="A", wp_id=id1, api_prefix="d2",
                        zip_path="a.xlsx", status=""),
            AlignedItem(sheet_code="B", wp_id=id2, api_prefix="d2",
                        zip_path="b.xlsx", status="", blocked=True),
            AlignedItem(sheet_code="C", wp_id=id3, api_prefix="d2",
                        zip_path="c.xlsx", status="", missing=True),
        ])
        writable = plan.writable_wp_ids
        assert len(writable) == 1
        assert str(writable[0]) == id1
