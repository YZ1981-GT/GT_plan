"""Unit tests for bulk_import_service — dry_run + run 核心逻辑。

测试覆盖：
  - align() 函数对齐逻辑（missing / unlisted / 正常）
  - ImportReport 数据结构与序列化
  - dry_run 快乐路径 + ZIP 解析失败 + 完整性校验失败
  - run 快乐路径 + 门禁 blocked + missing 跳过 + 回滚逻辑
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bulk_tab.bulk_import_service import (
    AlignedItem,
    FatalImportError,
    ImportPlan,
    ImportReport,
    SheetReport,
    align,
    dry_run,
    run,
)
from app.services.bulk_tab.single_tab_adapter import TabImportResult
from app.services.bulk_tab.snapshot_guard import AtomicityMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(files: dict[str, bytes], manifest: dict) -> bytes:
    """构建内存 ZIP 字节流。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files.items():
            zf.writestr(path, data)
        manifest_json = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        zf.writestr("manifest.json", manifest_json)
    return buf.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Tests: align()
# ---------------------------------------------------------------------------


class TestAlign:
    """align() 对齐逻辑测试。"""

    def test_normal_alignment(self):
        """正常对齐 — manifest 和 ZIP 都有的文件。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_审定表_数据.xlsx",
             "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
            {"sheet_code": "D2-2", "zip_path": "D/D2/D2-2_明细表_数据.xlsx",
             "wp_id": "bbb", "api_prefix": "d2", "import_order": 2},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
            {"sheet_code": "D2-2", "wp_id": "bbb", "api_prefix": "d2", "import_order": 2},
        ]
        zip_file_list = [
            "manifest.json",
            "D/D2/D2-1_审定表_数据.xlsx",
            "D/D2/D2-2_明细表_数据.xlsx",
        ]

        plan = align(manifest_files, topo_sheets, zip_file_list)

        assert len(plan.items) == 2
        assert plan.items[0].sheet_code == "D2-1"
        assert plan.items[1].sheet_code == "D2-2"
        assert not plan.items[0].missing
        assert not plan.items[1].missing
        assert plan.unlisted_paths == []

    def test_missing_file(self):
        """manifest 中有但 ZIP 中无 → missing。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_审定表_数据.xlsx",
             "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
        ]
        zip_file_list = ["manifest.json"]  # 没有 xlsx

        plan = align(manifest_files, topo_sheets, zip_file_list)

        assert len(plan.items) == 1
        assert plan.items[0].missing is True

    def test_unlisted_file(self):
        """ZIP 中有 xlsx 但 manifest 未登记 → unlisted。"""
        manifest_files = [
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1_审定表_数据.xlsx",
             "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
        ]
        topo_sheets = [
            {"sheet_code": "D2-1", "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
        ]
        zip_file_list = [
            "manifest.json",
            "D/D2/D2-1_审定表_数据.xlsx",
            "D/D2/EXTRA_未登记.xlsx",
        ]

        plan = align(manifest_files, topo_sheets, zip_file_list)

        assert len(plan.items) == 1
        assert not plan.items[0].missing
        assert "D/D2/EXTRA_未登记.xlsx" in plan.unlisted_paths

    def test_topo_order_preserved(self):
        """items 按 topo_sheets 顺序排列。"""
        manifest_files = [
            {"sheet_code": "D2-2", "zip_path": "D/D2/D2-2.xlsx",
             "wp_id": "bbb", "api_prefix": "d2", "import_order": 2},
            {"sheet_code": "D2-1", "zip_path": "D/D2/D2-1.xlsx",
             "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
        ]
        # topo 顺序：D2-1 在前
        topo_sheets = [
            {"sheet_code": "D2-1", "wp_id": "aaa", "api_prefix": "d2", "import_order": 1},
            {"sheet_code": "D2-2", "wp_id": "bbb", "api_prefix": "d2", "import_order": 2},
        ]
        zip_file_list = ["manifest.json", "D/D2/D2-1.xlsx", "D/D2/D2-2.xlsx"]

        plan = align(manifest_files, topo_sheets, zip_file_list)

        assert plan.items[0].sheet_code == "D2-1"
        assert plan.items[1].sheet_code == "D2-2"


# ---------------------------------------------------------------------------
# Tests: ImportReport
# ---------------------------------------------------------------------------


class TestImportReport:
    """ImportReport 数据结构测试。"""

    def test_summary(self):
        """summary 正确统计各状态。"""
        report = ImportReport(strategy="overwrite", dry_run=False)
        report.mark("D2-1", "success")
        report.mark("D2-2", "partial")
        report.mark("D2-3", "blocked_by_status", reason="review_passed")
        report.mark("D2-4", "missing")

        summary = report.summary
        assert summary["success"] == 1
        assert summary["partial"] == 1
        assert summary["blocked"] == 1
        assert summary["missing"] == 1

    def test_to_dict(self):
        """to_dict 序列化。"""
        report = ImportReport(strategy="fill-empty", dry_run=True)
        report.mark("D2-1", "success")

        d = report.to_dict()
        assert d["strategy"] == "fill-empty"
        assert d["dry_run"] is True
        assert len(d["sheets"]) == 1
        assert d["sheets"][0]["sheet_code"] == "D2-1"

    def test_merge_tab_result(self):
        """merge 正确合并 TabImportResult。"""
        report = ImportReport()
        result = TabImportResult(status="partial", rows_imported=42, warnings=["row_limit_exceeded"])
        report.merge("D2-1", result)

        assert report.sheets[0].status == "partial"
        assert report.sheets[0].rows == 42
        assert "row_limit_exceeded" in report.sheets[0].warnings


# ---------------------------------------------------------------------------
# Tests: ImportPlan
# ---------------------------------------------------------------------------


class TestImportPlan:
    """ImportPlan 辅助测试。"""

    def test_writable_wp_ids(self):
        """writable_wp_ids 去重且排除 blocked/missing。"""
        wp1 = str(uuid.uuid4())
        wp2 = str(uuid.uuid4())
        plan = ImportPlan(items=[
            AlignedItem(sheet_code="A", wp_id=wp1, api_prefix="d2", zip_path="a.xlsx", status=""),
            AlignedItem(sheet_code="B", wp_id=wp1, api_prefix="d2", zip_path="b.xlsx", status=""),
            AlignedItem(sheet_code="C", wp_id=wp2, api_prefix="d2", zip_path="c.xlsx",
                        status="", blocked=True),
            AlignedItem(sheet_code="D", wp_id=wp2, api_prefix="d2", zip_path="d.xlsx",
                        status="", missing=True),
        ])

        ids = plan.writable_wp_ids
        assert len(ids) == 1
        assert ids[0] == uuid.UUID(wp1)


# ---------------------------------------------------------------------------
# Tests: dry_run
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry_run 集成测试（mock DB 和外部依赖）。"""

    @pytest.mark.asyncio
    async def test_invalid_zip(self):
        """非法 ZIP → 立即返回失败报告。"""
        db = AsyncMock()
        report = await dry_run(db, str(uuid.uuid4()), b"not a zip", "overwrite")

        assert report.dry_run is True
        assert any(s.status == "failed" for s in report.sheets)

    @pytest.mark.asyncio
    async def test_missing_manifest(self):
        """ZIP 中无 manifest.json → 失败报告。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.xlsx", b"data")
        zip_bytes = buf.getvalue()

        db = AsyncMock()
        report = await dry_run(db, str(uuid.uuid4()), zip_bytes, "overwrite")

        assert any(s.status == "failed" for s in report.sheets)

    @pytest.mark.asyncio
    async def test_happy_path(self):
        """正常 dry_run — 所有 sheet 通过。"""
        xlsx_data = b"fake xlsx content"
        manifest = {
            "cycles": ["D"],
            "files": [
                {
                    "sheet_code": "D2-1",
                    "zip_path": "D/D2/D2-1.xlsx",
                    "wp_id": "11111111-1111-1111-1111-111111111111",
                    "api_prefix": "d2",
                    "import_order": 1,
                    "sha256": _sha256(xlsx_data),
                },
            ],
        }
        zip_bytes = _make_zip({"D/D2/D2-1.xlsx": xlsx_data}, manifest)

        topo_sheets = [
            {
                "sheet_code": "D2-1",
                "wp_id": "11111111-1111-1111-1111-111111111111",
                "api_prefix": "d2",
                "import_order": 1,
                "depends_on_sheets": [],
            }
        ]

        db = AsyncMock()

        with patch(
            "app.services.wp_bulk_tab_export.list_import_sheets",
            new_callable=AsyncMock,
            return_value=topo_sheets,
        ), patch(
            "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
            new_callable=AsyncMock,
            return_value={"11111111-1111-1111-1111-111111111111": "draft"},
        ):
            report = await dry_run(db, str(uuid.uuid4()), zip_bytes, "overwrite")

        assert report.dry_run is True
        success_sheets = [s for s in report.sheets if s.status == "success"]
        assert len(success_sheets) == 1
        assert success_sheets[0].sheet_code == "D2-1"


# ---------------------------------------------------------------------------
# Tests: run
# ---------------------------------------------------------------------------


class TestRun:
    """run 集成测试（mock DB 和外部依赖）。"""

    @pytest.mark.asyncio
    async def test_invalid_zip(self):
        """非法 ZIP → 立即返回失败报告。"""
        db = AsyncMock()
        report = await run(db, str(uuid.uuid4()), b"not a zip", "overwrite")

        assert report.dry_run is False
        assert any(s.status == "failed" for s in report.sheets)

    @pytest.mark.asyncio
    async def test_happy_path_import(self):
        """正常导入 — 单 sheet 成功。"""
        xlsx_data = b"fake xlsx content"
        wp_id = "22222222-2222-2222-2222-222222222222"
        manifest = {
            "cycles": ["D"],
            "files": [
                {
                    "sheet_code": "D2-2",
                    "zip_path": "D/D2/D2-2.xlsx",
                    "wp_id": wp_id,
                    "api_prefix": "d2",
                    "import_order": 1,
                    "sha256": _sha256(xlsx_data),
                },
            ],
        }
        zip_bytes = _make_zip({"D/D2/D2-2.xlsx": xlsx_data}, manifest)

        topo_sheets = [
            {
                "sheet_code": "D2-2",
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": 1,
                "depends_on_sheets": [],
            }
        ]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"

        db = AsyncMock()

        mock_result = TabImportResult(status="success", rows_imported=10)

        with patch(
            "app.services.wp_bulk_tab_export.list_import_sheets",
            new_callable=AsyncMock,
            return_value=topo_sheets,
        ), patch(
            "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
            new_callable=AsyncMock,
            return_value={wp_id: "draft"},
        ), patch(
            "app.services.bulk_tab.bulk_import_service.import_tab",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.services.bulk_tab.bulk_import_service.SnapshotGuard.snapshot",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.bulk_tab.bulk_import_service._write_import_audit_log",
            new_callable=AsyncMock,
        ):
            report = await run(db, str(uuid.uuid4()), zip_bytes, "overwrite", user=mock_user)

        assert report.dry_run is False
        assert not report.rolled_back
        success_sheets = [s for s in report.sheets if s.status == "success"]
        assert len(success_sheets) == 1
        assert success_sheets[0].rows == 10

    @pytest.mark.asyncio
    async def test_blocked_by_status(self):
        """review_passed 底稿 → blocked_by_status。"""
        xlsx_data = b"fake xlsx"
        wp_id = "33333333-3333-3333-3333-333333333333"
        manifest = {
            "cycles": ["D"],
            "files": [
                {
                    "sheet_code": "D2-7",
                    "zip_path": "D/D2/D2-7.xlsx",
                    "wp_id": wp_id,
                    "api_prefix": "d2",
                    "import_order": 1,
                    "sha256": _sha256(xlsx_data),
                },
            ],
        }
        zip_bytes = _make_zip({"D/D2/D2-7.xlsx": xlsx_data}, manifest)

        topo_sheets = [
            {
                "sheet_code": "D2-7",
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": 1,
                "depends_on_sheets": [],
            }
        ]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"

        db = AsyncMock()

        with patch(
            "app.services.wp_bulk_tab_export.list_import_sheets",
            new_callable=AsyncMock,
            return_value=topo_sheets,
        ), patch(
            "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
            new_callable=AsyncMock,
            return_value={wp_id: "review_passed"},
        ), patch(
            "app.services.bulk_tab.bulk_import_service.SnapshotGuard.snapshot",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.bulk_tab.bulk_import_service._write_import_audit_log",
            new_callable=AsyncMock,
        ):
            report = await run(db, str(uuid.uuid4()), zip_bytes, "overwrite", user=mock_user)

        blocked = [s for s in report.sheets if s.status == "blocked_by_status"]
        assert len(blocked) == 1
        assert blocked[0].sheet_code == "D2-7"

    @pytest.mark.asyncio
    async def test_missing_file_skipped(self):
        """manifest 中有但 ZIP 中无文件 → missing 继续。"""
        wp_id = "44444444-4444-4444-4444-444444444444"
        manifest = {
            "cycles": ["D"],
            "files": [
                {
                    "sheet_code": "D2-3",
                    "zip_path": "D/D2/D2-3.xlsx",
                    "wp_id": wp_id,
                    "api_prefix": "d2",
                    "import_order": 1,
                    # No sha256 → ZipReader.verify_integrity skips this
                },
            ],
        }
        zip_bytes = _make_zip({}, manifest)

        topo_sheets = [
            {
                "sheet_code": "D2-3",
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": 1,
                "depends_on_sheets": [],
            }
        ]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"

        db = AsyncMock()

        with patch(
            "app.services.wp_bulk_tab_export.list_import_sheets",
            new_callable=AsyncMock,
            return_value=topo_sheets,
        ), patch(
            "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
            new_callable=AsyncMock,
            return_value={wp_id: "draft"},
        ), patch(
            "app.services.bulk_tab.bulk_import_service.SnapshotGuard.snapshot",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.bulk_tab.bulk_import_service._write_import_audit_log",
            new_callable=AsyncMock,
        ):
            report = await run(db, str(uuid.uuid4()), zip_bytes, "overwrite", user=mock_user)

        missing = [s for s in report.sheets if s.status == "missing"]
        assert len(missing) == 1
        assert not report.rolled_back

    @pytest.mark.asyncio
    async def test_all_or_nothing_rollback(self):
        """all-or-nothing 模式下单 sheet 失败 → 回滚。"""
        xlsx_data = b"fake xlsx"
        wp_id = "55555555-5555-5555-5555-555555555555"
        manifest = {
            "cycles": ["D"],
            "files": [
                {
                    "sheet_code": "D2-1",
                    "zip_path": "D/D2/D2-1.xlsx",
                    "wp_id": wp_id,
                    "api_prefix": "d2",
                    "import_order": 1,
                    "sha256": _sha256(xlsx_data),
                },
            ],
        }
        zip_bytes = _make_zip({"D/D2/D2-1.xlsx": xlsx_data}, manifest)

        topo_sheets = [
            {
                "sheet_code": "D2-1",
                "wp_id": wp_id,
                "api_prefix": "d2",
                "import_order": 1,
                "depends_on_sheets": [],
            }
        ]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.role = MagicMock()
        mock_user.role.value = "admin"

        db = AsyncMock()

        mock_result = TabImportResult(status="failed", rows_imported=0, errors=["parse error"])

        from app.services.bulk_tab.snapshot_guard import SnapshotRecord

        fake_snap = SnapshotRecord(wp_id=uuid.UUID(wp_id), snapshot_id=uuid.uuid4())

        with patch(
            "app.services.wp_bulk_tab_export.list_import_sheets",
            new_callable=AsyncMock,
            return_value=topo_sheets,
        ), patch(
            "app.services.bulk_tab.bulk_import_service._get_wp_statuses",
            new_callable=AsyncMock,
            return_value={wp_id: "draft"},
        ), patch(
            "app.services.bulk_tab.bulk_import_service.import_tab",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.services.bulk_tab.bulk_import_service.SnapshotGuard.snapshot",
            new_callable=AsyncMock,
            return_value=[fake_snap],
        ), patch(
            "app.services.bulk_tab.bulk_import_service.SnapshotGuard.rollback",
            new_callable=AsyncMock,
        ) as mock_rollback, patch(
            "app.services.bulk_tab.bulk_import_service._write_import_audit_log",
            new_callable=AsyncMock,
        ):
            report = await run(
                db, str(uuid.uuid4()), zip_bytes, "overwrite",
                user=mock_user, atomicity=AtomicityMode.ALL_OR_NOTHING,
            )

        assert report.rolled_back is True
        mock_rollback.assert_called_once()
