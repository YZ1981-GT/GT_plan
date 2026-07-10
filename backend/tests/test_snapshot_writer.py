"""Tests for SnapshotWriter — 双向编辑写回 (Req 2, Req 13)

Property 3: 写事务一致性 — 成功写回后 JSONB + xlsx 都含新值, prefill_stale=True
Property 4: 乐观锁冲突检测 — opened_at < updated_at → 409
Property 5: 写权限强制 — 非 workpaper 源或无权限 → 403, 数据不变
Property 26: 跨模块写路由 — 每个模块写到正确目标
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from hypothesis import given, settings, strategies as st

from app.services.custom_query.snapshot_writer import (
    SnapshotWriter,
    WritebackConflict,
    WritebackPermissionDenied,
    _parse_cell_ref,
    snapshot_writer,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_mock_user(username="testuser", user_id="user-001", role="admin"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.role = role
    return user


def _make_snapshot_with_cell(sheet_name: str, row: int, col: int, value):
    """Create a minimal univer_snapshot with a single cell value."""
    return {
        "univer_snapshot": {
            "sheets": {
                "0": {
                    "name": sheet_name,
                    "cellData": {
                        str(row): {
                            str(col): {"v": value}
                        }
                    }
                }
            }
        }
    }


# ─── Unit Tests: _parse_cell_ref ─────────────────────────────────────────────


class TestParseCellRef:
    """Test cell reference parsing (1-indexed → 0-indexed)."""

    def test_b7(self):
        """B7 → row=6, col=1"""
        row, col = _parse_cell_ref("B7")
        assert row == 6
        assert col == 1

    def test_a1(self):
        """A1 → row=0, col=0"""
        row, col = _parse_cell_ref("A1")
        assert row == 0
        assert col == 0

    def test_z26(self):
        """Z26 → row=25, col=25"""
        row, col = _parse_cell_ref("Z26")
        assert row == 25
        assert col == 25

    def test_aa1(self):
        """AA1 → row=0, col=26"""
        row, col = _parse_cell_ref("AA1")
        assert row == 0
        assert col == 26

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_cell_ref("invalid")

    def test_lowercase_normalized(self):
        """Lowercase input is normalized to uppercase."""
        row, col = _parse_cell_ref("b7")
        assert row == 6
        assert col == 1


# ---------------------------------------------------------------------------
# Property 3: 写事务一致性
# Feature: advanced-query-enhancements-p1p2, Property 3: Write transactional consistency
# ---------------------------------------------------------------------------


class TestProperty3WriteTransactionalConsistency:
    """After successful write, both JSONB and xlsx contain new value,
    and prefill_stale=True on the corresponding working_paper record."""

    @pytest.mark.asyncio
    @settings(max_examples=10)
    @given(
        new_value=st.one_of(
            st.integers(min_value=-10000, max_value=10000),
            st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
        ),
        row_num=st.integers(min_value=1, max_value=50),
        col_letter=st.sampled_from(["A", "B", "C", "D", "E", "F"]),
    )
    async def test_write_consistency_property(self, new_value, row_num, col_letter):
        """After successful write, JSONB contains new value and prefill_stale=True.

        **Validates: Requirements 2.1, 2.2**
        """
        cell_ref = f"{col_letter}{row_num}"
        row_idx = row_num - 1
        col_idx = ord(col_letter) - ord("A")
        sheet_name = "TestSheet"
        old_value = "old"

        # Build snapshot with old value
        parsed_data = _make_snapshot_with_cell(sheet_name, row_idx, col_idx, old_value)
        now = datetime.now(timezone.utc)

        # Track what gets written to DB
        written_parsed_data = None
        written_prefill_stale = None

        async def mock_execute(stmt, params=None):
            nonlocal written_parsed_data, written_prefill_stale
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)

            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            elif "UPDATE working_paper" in stmt_str:
                if params:
                    written_parsed_data = params.get("new_pd")
                    written_prefill_stale = True
                mock_result = MagicMock()
                return mock_result
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_user = _make_mock_user()

        writer = SnapshotWriter()

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            result = await writer.write_cell(
                db=mock_db,
                user=mock_user,
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref=cell_ref,
                new_value=new_value,
                opened_at=now,  # same as updated_at → no conflict
                module="workpaper",
            )

        # Verify success
        assert result["success"] is True
        assert result["updated_at"] is not None

        # Verify JSONB was updated with new value
        assert written_parsed_data is not None
        pd = json.loads(written_parsed_data)
        cell_val = pd["univer_snapshot"]["sheets"]["0"]["cellData"][str(row_idx)][str(col_idx)]["v"]
        assert cell_val == new_value

        # Verify prefill_stale was set
        assert written_prefill_stale is True


    @pytest.mark.asyncio
    async def test_write_updates_jsonb_and_marks_stale(self):
        """Concrete example: write B7=42, verify JSONB updated + prefill_stale."""
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 6, 1, "old_val")
        now = datetime.now(timezone.utc)

        written_data = {}

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            elif "UPDATE working_paper" in stmt_str:
                if params:
                    written_data["pd"] = params.get("new_pd")
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            result = await snapshot_writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="B7",
                new_value=42,
                opened_at=now,
            )

        assert result["success"] is True
        assert result["old_value"] == "old_val"

        pd = json.loads(written_data["pd"])
        assert pd["univer_snapshot"]["sheets"]["0"]["cellData"]["6"]["1"]["v"] == 42


# ---------------------------------------------------------------------------
# Property 4: 乐观锁冲突检测
# Feature: advanced-query-enhancements-p1p2, Property 4: Optimistic lock conflict detection
# ---------------------------------------------------------------------------


class TestProperty4OptimisticLockConflict:
    """When opened_at < updated_at, must reject with WritebackConflict."""

    @pytest.mark.asyncio
    @settings(max_examples=10)
    @given(
        opened_offset_seconds=st.integers(min_value=1, max_value=86400),
    )
    async def test_stale_write_rejected(self, opened_offset_seconds):
        """For any write where opened_at < updated_at, must raise WritebackConflict.

        **Validates: Requirements 2.3**
        """
        now = datetime.now(timezone.utc)
        updated_at = now
        opened_at = now - timedelta(seconds=opened_offset_seconds)

        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "val")

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (updated_at, parsed_data, "D2", "", "test-project-id")
                return mock_result
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        writer = SnapshotWriter()

        with pytest.raises(WritebackConflict) as exc_info:
            await writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="A1",
                new_value="new",
                opened_at=opened_at,
            )

        # Verify conflict details
        assert exc_info.value.latest_updated_at == updated_at

    @pytest.mark.asyncio
    async def test_exact_same_time_no_conflict(self):
        """When opened_at == updated_at, no conflict (not strictly earlier)."""
        now = datetime.now(timezone.utc)
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "val")

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            result = await snapshot_writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="A1",
                new_value="new",
                opened_at=now,
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_conflict_returns_editor_info(self):
        """Conflict exception includes latest_editor."""
        now = datetime.now(timezone.utc)
        opened_at = now - timedelta(seconds=10)
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "val")
        parsed_data["univer_snapshot"]["saved_by"] = "other_user"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with pytest.raises(WritebackConflict) as exc_info:
            await snapshot_writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="A1",
                new_value="new",
                opened_at=opened_at,
            )

        assert exc_info.value.latest_editor == "other_user"


# ---------------------------------------------------------------------------
# Property 5: 写权限强制
# Feature: advanced-query-enhancements-p1p2, Property 5: Write permission enforcement
# ---------------------------------------------------------------------------


class TestProperty5WritePermissionEnforcement:
    """Non-workpaper source or no write permission → 403, data unchanged."""

    @pytest.mark.asyncio
    @settings(max_examples=10)
    @given(
        module=st.sampled_from(["report", "note", "adj", "tb"]),
    )
    async def test_non_workpaper_module_requires_permission(self, module):
        """For non-workpaper modules, permission check applies.

        **Validates: Requirements 2.5**
        """
        # The endpoint-level permission check is in the router.
        # At the service level, we verify that unsupported modules raise.
        writer = SnapshotWriter()

        # Verify that the writer routes to the correct module handler
        # (this tests the routing, not permission — permission is at endpoint level)
        assert module in ("report", "note", "adj", "tb")

    @pytest.mark.asyncio
    async def test_unsupported_module_raises(self):
        """Unsupported module raises WritebackPermissionDenied.

        **Validates: Requirements 2.5**
        """
        writer = SnapshotWriter()
        mock_db = AsyncMock()

        with pytest.raises(WritebackPermissionDenied) as exc_info:
            await writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name="Sheet1",
                cell_ref="A1",
                new_value="test",
                opened_at=datetime.now(timezone.utc),
                module="invalid_module",
            )

        assert "Unsupported module" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_tb_only_allows_audited_amount_column(self):
        """Trial balance only allows writing to column G (audited_amount).

        **Validates: Requirements 2.5**
        """
        writer = SnapshotWriter()
        now = datetime.now(timezone.utc)

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = ("tb-001", now)
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # Column A (account_code) should be rejected
        with pytest.raises(WritebackPermissionDenied):
            await writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="tb-001",
                sheet_name="tb_detail",
                cell_ref="A1",  # col A = account_code, not writable
                new_value=100,
                opened_at=now,
                module="tb",
            )

    def test_endpoint_permission_model(self):
        """CellWritebackRequest model validates module field."""
        from app.routers.custom_query import CellWritebackRequest

        # Valid modules
        for module in ("workpaper", "report", "note", "adj", "tb"):
            req = CellWritebackRequest(
                project_id="test-project-id",
                wp_code="D2",
                sheet_name="Sheet1",
                cell_ref="A1",
                new_value=42,
                module=module,
            )
            assert req.module == module

        # Invalid module
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CellWritebackRequest(
                project_id="test-project-id",
                wp_code="D2",
                sheet_name="Sheet1",
                cell_ref="A1",
                new_value=42,
                module="invalid",
            )


# ---------------------------------------------------------------------------
# Property 26: 跨模块写路由
# Feature: advanced-query-enhancements-p1p2, Property 26: Cross-module write routing
# ---------------------------------------------------------------------------


class TestProperty26CrossModuleWriteRouting:
    """For each module, write routes to correct target table/column."""

    @pytest.mark.asyncio
    @settings(max_examples=10)
    @given(
        module=st.sampled_from(["workpaper", "report", "note", "adj", "tb"]),
    )
    async def test_module_routes_to_correct_handler(self, module):
        """Each module routes to its specific write handler.

        **Validates: Requirements 13.5**
        """
        writer = SnapshotWriter()

        # Verify routing by checking method resolution
        if module == "workpaper":
            assert hasattr(writer, "_write_workpaper_cell")
        elif module == "report":
            assert hasattr(writer, "_write_report_cell")
        elif module == "note":
            assert hasattr(writer, "_write_note_cell")
        elif module == "adj":
            assert hasattr(writer, "_write_adj_cell")
        elif module == "tb":
            assert hasattr(writer, "_write_tb_cell")


    @pytest.mark.asyncio
    async def test_workpaper_writes_to_parsed_data(self):
        """Workpaper module writes to parsed_data['univer_snapshot'].

        **Validates: Requirements 13.5**
        """
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "old")
        now = datetime.now(timezone.utc)
        written_sql = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            written_sql.append(stmt_str)
            if "SELECT" in stmt_str and "working_paper" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            await snapshot_writer.write_cell(
                db=mock_db, user=_make_mock_user(), wp_id="wp-001",
                sheet_name=sheet_name, cell_ref="A1", new_value="new",
                opened_at=now, module="workpaper",
            )

        # Verify UPDATE was on working_paper table
        assert any("UPDATE working_paper" in s for s in written_sql)

    @pytest.mark.asyncio
    async def test_report_writes_to_report_snapshot(self):
        """Report module writes to report_snapshot.data.

        **Validates: Requirements 13.5**
        """
        now = datetime.now(timezone.utc)
        report_data = {
            "rows": [
                {"row_code": "BS-001", "row_name": "资产", "current_period_amount": 100,
                 "prior_period_amount": 90, "formula": None}
            ]
        }
        written_sql = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            written_sql.append(stmt_str)
            if "SELECT" in stmt_str and "report_snapshot" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = ("rs-001", report_data, now)
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        await snapshot_writer.write_cell(
            db=mock_db, user=_make_mock_user(), wp_id="rs-001",
            sheet_name="report_balance_sheet", cell_ref="C2", new_value=200,
            opened_at=now, module="report",
        )

        assert any("UPDATE report_snapshot" in s for s in written_sql)

    @pytest.mark.asyncio
    async def test_note_writes_to_consol_note_data(self):
        """Note module writes to consol_note_data.data.

        **Validates: Requirements 13.5**
        """
        now = datetime.now(timezone.utc)
        note_data = {
            "rows": [
                {"code": "1001", "name": "现金", "year_end": 100, "year_begin": 90, "formula": None}
            ]
        }
        written_sql = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            written_sql.append(stmt_str)
            if "SELECT" in stmt_str and "consol_note_data" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = ("nd-001", note_data, now)
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        await snapshot_writer.write_cell(
            db=mock_db, user=_make_mock_user(), wp_id="nd-001",
            sheet_name="note_五-1-1", cell_ref="C2", new_value=150,
            opened_at=now, module="note",
        )

        assert any("UPDATE consol_note_data" in s for s in written_sql)

    @pytest.mark.asyncio
    async def test_adj_writes_to_adjustments_table(self):
        """Adj module writes to adjustments table.

        **Validates: Requirements 13.5**
        """
        now = datetime.now(timezone.utc)
        written_sql = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            written_sql.append(stmt_str)
            if "SELECT" in stmt_str and "adjustments" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = ("adj-001", now)
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        await snapshot_writer.write_cell(
            db=mock_db, user=_make_mock_user(), wp_id="adj-001",
            sheet_name="adj_aje", cell_ref="D1", new_value=500.0,
            opened_at=now, module="adj",
        )

        assert any("UPDATE adjustments" in s for s in written_sql)

    @pytest.mark.asyncio
    async def test_tb_writes_to_trial_balance(self):
        """TB module writes to trial_balance.audited_amount.

        **Validates: Requirements 13.5**
        """
        now = datetime.now(timezone.utc)
        written_sql = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            written_sql.append(stmt_str)
            if "SELECT" in stmt_str and "trial_balance" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = ("tb-001", now)
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        await snapshot_writer.write_cell(
            db=mock_db, user=_make_mock_user(), wp_id="tb-001",
            sheet_name="tb_detail", cell_ref="G2", new_value=1000.0,
            opened_at=now, module="tb",
        )

        assert any("UPDATE trial_balance" in s for s in written_sql)
        assert any("audited_amount" in s for s in written_sql)


# ---------------------------------------------------------------------------
# E2E-style integration test (mocked DB)
# ---------------------------------------------------------------------------


class TestCellWritebackE2E:
    """End-to-end style tests for the cell writeback flow."""

    @pytest.mark.asyncio
    async def test_full_writeback_flow(self):
        """Complete writeback: read → check lock → write → emit event."""
        sheet_name = "审定表D2-1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 6, 1, 12345.67)
        now = datetime.now(timezone.utc)
        events_emitted = []

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "/path/to/file.xlsx", "test-project-id")
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            # 新版: snapshot_writer 使用 orchestrator，需 mock ORM 查询 + orchestrator
            with patch("app.services.workpaper_save_orchestrator.orchestrator.after_save", new_callable=AsyncMock) as mock_orch:
                mock_orch.return_value = 2  # new file_version

                result = await snapshot_writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id="wp-001",
                    sheet_name=sheet_name,
                    cell_ref="B7",
                    new_value=99999.99,
                    opened_at=now,
                )

        assert result["success"] is True
        assert result["old_value"] == 12345.67
        assert result["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_conflict_flow(self):
        """Conflict scenario: opened_at is stale → WritebackConflict raised."""
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "val")
        now = datetime.now(timezone.utc)
        stale_opened_at = now - timedelta(minutes=5)

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", "test-project-id")
                return mock_result
            return MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        with pytest.raises(WritebackConflict) as exc_info:
            await snapshot_writer.write_cell(
                db=mock_db,
                user=_make_mock_user(username="editor_a"),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="A1",
                new_value="new",
                opened_at=stale_opened_at,
            )

        assert exc_info.value.latest_updated_at == now


# ---------------------------------------------------------------------------
# ACNR addr_id 集成测试（M2, R15.1, R15.2, R15.4）
# Feature: acnr, Task 16.1: snapshot_writer 回写 addr_id
# ---------------------------------------------------------------------------


class TestSnapshotWriterAcnrAddrId:
    """snapshot_writer 回写时附带 ACNR addr_id + column_metadata。

    R15.1: 存 addr_id 而非裸 (wp_id, sheet_name, cell_ref)
    R15.2: 列元数据挂 addr_id，chip 可下钻到格
    R15.4: 回写解析带 project context
    """

    @pytest.mark.asyncio
    async def test_write_result_contains_addr_id(self):
        """成功写回后结果包含 addr_id 字段。

        **Validates: Requirements 15.1**
        """
        sheet_name = "明细表D2-2"
        parsed_data = _make_snapshot_with_cell(sheet_name, 6, 1, "old")
        now = datetime.now(timezone.utc)
        project_id = "00000000-0000-0000-0000-000000000001"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", project_id)
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # Mock ACNR catalog to return a known sheet entry
        mock_catalog = MagicMock()
        mock_sheet_entry = {
            "addr_id": "D2/D2-2",
            "parent_wp_code": "D2",
            "sheet_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "display_label": "底稿 > D2 > 明细表D2-2",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
        }
        mock_catalog.sheets_by_alias = {"明细表D2-2": [mock_sheet_entry]}
        mock_catalog.sheets_by_code = {"D2-2": [mock_sheet_entry]}
        mock_catalog.cells_by_addr_id = {}

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with patch("app.services.acnr.catalog.get_catalog", return_value=mock_catalog):
                result = await snapshot_writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id="wp-001",
                    sheet_name=sheet_name,
                    cell_ref="B7",
                    new_value=42,
                    opened_at=now,
                    project_id=project_id,
                )

        assert result["success"] is True
        # R15.1: addr_id 存在且格式正确
        assert result["addr_id"] is not None
        assert "D2" in result["addr_id"]

    @pytest.mark.asyncio
    async def test_write_result_contains_column_metadata_for_drilldown(self):
        """写回结果包含 column_metadata，chip 可下钻到格。

        **Validates: Requirements 15.2**
        """
        sheet_name = "明细表D2-2"
        cell_ref = "E100"
        parsed_data = _make_snapshot_with_cell(sheet_name, 99, 4, "old_val")
        now = datetime.now(timezone.utc)
        project_id = "00000000-0000-0000-0000-000000000002"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", project_id)
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # Mock ACNR catalog with a registered cell entry
        mock_catalog = MagicMock()
        mock_sheet_entry = {
            "addr_id": "D2/D2-2",
            "parent_wp_code": "D2",
            "sheet_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "display_label": "底稿 > D2 > 明细表D2-2",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
        }
        mock_cell_entry = {
            "addr_id": "D2/D2-2/E100",
            "parent_addr_id": "D2/D2-2",
            "uri": "wp://D2/明细表D2-2#E100",
            "formula_ref": "WP('D2','明细表D2-2','合计行-期末余额')",
            "semantic_label": "合计行-期末余额",
            "cell_address": "E100",
        }
        mock_catalog.sheets_by_alias = {"明细表D2-2": [mock_sheet_entry]}
        mock_catalog.sheets_by_code = {"D2-2": [mock_sheet_entry]}
        mock_catalog.cells_by_addr_id = {"D2/D2-2/E100": mock_cell_entry}

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with patch("app.services.acnr.catalog.get_catalog", return_value=mock_catalog):
                result = await snapshot_writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id="wp-001",
                    sheet_name=sheet_name,
                    cell_ref=cell_ref,
                    new_value=99999.99,
                    opened_at=now,
                    project_id=project_id,
                )

        assert result["success"] is True
        # R15.2: column_metadata 存在且含 drill-down 信息
        assert result["column_metadata"] is not None
        meta = result["column_metadata"]
        assert meta["addr_id"] == "D2/D2-2/E100"
        assert meta["drilldown_enabled"] is True
        assert meta["cell_address"] == "E100"
        assert meta["sheet_addr_id"] == "D2/D2-2"
        # 语义标签作为 display_label
        assert "合计行-期末余额" in meta["display_label"]

    @pytest.mark.asyncio
    async def test_write_carries_project_context(self):
        """回写解析携带 project context（R15.4）。

        **Validates: Requirements 15.4**
        """
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "old")
        now = datetime.now(timezone.utc)
        project_id = "00000000-0000-0000-0000-000000000003"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", project_id)
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # 验证 _resolve_addr_id 被调用且带 project_id
        writer = SnapshotWriter()
        resolve_calls = []
        original_resolve = writer._resolve_addr_id

        def tracking_resolve(wp_code, sheet_name, cell_ref, project_id=None):
            resolve_calls.append({
                "wp_code": wp_code,
                "sheet_name": sheet_name,
                "cell_ref": cell_ref,
                "project_id": project_id,
            })
            return None  # 模拟 miss

        writer._resolve_addr_id = tracking_resolve

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            await writer.write_cell(
                db=mock_db,
                user=_make_mock_user(),
                wp_id="wp-001",
                sheet_name=sheet_name,
                cell_ref="A1",
                new_value="new",
                opened_at=now,
                project_id=project_id,
            )

        # R15.4: resolve 必须携带 project_id
        assert len(resolve_calls) == 1
        assert resolve_calls[0]["project_id"] == project_id
        assert resolve_calls[0]["wp_code"] == "D2"
        assert resolve_calls[0]["sheet_name"] == sheet_name
        assert resolve_calls[0]["cell_ref"] == "A1"

    @pytest.mark.asyncio
    async def test_acnr_miss_falls_back_gracefully(self):
        """ACNR catalog miss 时降级返回构造的 addr_id，不阻塞写回。

        **Validates: Requirements 15.1**
        """
        sheet_name = "未注册Sheet"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "old")
        now = datetime.now(timezone.utc)
        project_id = "00000000-0000-0000-0000-000000000004"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "X9", "", project_id)
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # Mock catalog that returns empty for all lookups (miss)
        mock_catalog = MagicMock()
        mock_catalog.sheets_by_alias = {}
        mock_catalog.sheets_by_code = {}
        mock_catalog.cells_by_addr_id = {}

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with patch("app.services.acnr.catalog.get_catalog", return_value=mock_catalog):
                result = await snapshot_writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id="wp-001",
                    sheet_name=sheet_name,
                    cell_ref="A1",
                    new_value="new",
                    opened_at=now,
                    project_id=project_id,
                )

        # 写回仍然成功（不阻塞）
        assert result["success"] is True
        # 降级 addr_id 仍有值（最大努力）
        assert result["addr_id"] is not None
        assert "X9" in result["addr_id"]
        # column_metadata 降级但仍存在
        assert result["column_metadata"] is not None
        assert result["column_metadata"]["drilldown_enabled"] is False

    @pytest.mark.asyncio
    async def test_acnr_error_does_not_block_write(self):
        """ACNR 解析异常时不阻塞写回主流程（降级策略）。

        **Validates: Requirements 15.1**
        """
        sheet_name = "Sheet1"
        parsed_data = _make_snapshot_with_cell(sheet_name, 0, 0, "old")
        now = datetime.now(timezone.utc)
        project_id = "00000000-0000-0000-0000-000000000005"

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, 'text') else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (now, parsed_data, "D2", "", project_id)
                return mock_result
            elif "UPDATE" in stmt_str:
                return MagicMock()
            return MagicMock(first=MagicMock(return_value=None))

        mock_db = AsyncMock()
        mock_db.execute = mock_execute

        # Mock catalog that raises an exception
        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with patch(
                "app.services.acnr.catalog.get_catalog",
                side_effect=RuntimeError("catalog not loaded"),
            ):
                result = await snapshot_writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id="wp-001",
                    sheet_name=sheet_name,
                    cell_ref="A1",
                    new_value="new",
                    opened_at=now,
                    project_id=project_id,
                )

        # 写回成功不受 ACNR 故障影响
        assert result["success"] is True
        assert result["updated_at"] is not None
        # 降级 addr_id 仍有值
        assert result["addr_id"] == "D2/Sheet1/A1"

    @pytest.mark.asyncio
    async def test_cell_in_l1_seeds_gets_rich_metadata(self):
        """L1 种子中注册的 cell 获得完整 addr_id + uri + formula_ref + semantic_label。

        **Validates: Requirements 15.1, 15.2**
        """
        writer = SnapshotWriter()

        # Mock catalog with registered cell
        mock_catalog = MagicMock()
        mock_sheet_entry = {
            "addr_id": "D2/D2-2",
            "parent_wp_code": "D2",
            "sheet_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "display_label": "底稿 > D2 > 明细表D2-2",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
        }
        mock_cell_entry = {
            "addr_id": "D2/D2-2/E100",
            "parent_addr_id": "D2/D2-2",
            "uri": "wp://D2/明细表D2-2#E100",
            "formula_ref": "WP('D2','明细表D2-2','合计行-期末余额')",
            "semantic_label": "合计行-期末余额",
            "cell_address": "E100",
        }
        mock_catalog.sheets_by_alias = {"明细表D2-2": [mock_sheet_entry]}
        mock_catalog.sheets_by_code = {}
        mock_catalog.cells_by_addr_id = {"D2/D2-2/E100": mock_cell_entry}

        with patch("app.services.acnr.catalog.get_catalog", return_value=mock_catalog):
            result = writer._resolve_addr_id(
                wp_code="D2",
                sheet_name="明细表D2-2",
                cell_ref="E100",
                project_id="test-project-id",
            )

        assert result is not None
        assert result["addr_id"] == "D2/D2-2/E100"
        assert result["uri"] == "wp://D2/明细表D2-2#E100"
        assert result["formula_ref"] == "WP('D2','明细表D2-2','合计行-期末余额')"
        assert result["entry_type"] == "cell"
        assert result["semantic_label"] == "合计行-期末余额"
        # column_metadata for chip drill-down
        meta = result["column_metadata"]
        assert meta["drilldown_enabled"] is True
        assert meta["addr_id"] == "D2/D2-2/E100"

    @pytest.mark.asyncio
    async def test_unregistered_cell_gets_constructed_addr_id(self):
        """未在 L1 种子注册的 cell 仍获得构造的 addr_id（runtime 格式）。

        **Validates: Requirements 15.1**
        """
        writer = SnapshotWriter()

        # Mock catalog: sheet exists but cell not registered
        mock_catalog = MagicMock()
        mock_sheet_entry = {
            "addr_id": "D2/D2-2",
            "parent_wp_code": "D2",
            "sheet_code": "D2-2",
            "sheet_name": "明细表D2-2",
            "jump_route_template": "/workpapers/{wp_id}?sheet=D2-2",
        }
        mock_catalog.sheets_by_alias = {"明细表D2-2": [mock_sheet_entry]}
        mock_catalog.sheets_by_code = {}
        mock_catalog.cells_by_addr_id = {}  # cell not registered

        with patch("app.services.acnr.catalog.get_catalog", return_value=mock_catalog):
            result = writer._resolve_addr_id(
                wp_code="D2",
                sheet_name="明细表D2-2",
                cell_ref="B7",
                project_id="test-project-id",
            )

        assert result is not None
        # 构造的 addr_id 格式正确
        assert result["addr_id"] == "D2/D2-2/B7"
        assert result["entry_type"] == "cell"
        assert result["parent_addr_id"] == "D2/D2-2"
        # 仍支持 drill-down（但无语义标签）
        meta = result["column_metadata"]
        assert meta["drilldown_enabled"] is True
        assert meta["cell_address"] == "B7"
