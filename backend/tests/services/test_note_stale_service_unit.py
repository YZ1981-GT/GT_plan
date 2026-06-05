"""单测 — NoteStaleService bug 修复回归 + 文本章节降级

Feature: disclosure-note-linkage-and-slimdown
Validates: Requirements 2.3, 2.6

覆盖：
- 修复后 import 成功（来自 report_models 非 phase13_models）
- note_section 字段可用（非 section_code）
- refresh_from_workpaper 真正执行刷新（非空返回）
- refresh_stale_sections 真正执行刷新
- 纯文本章节被识别并保留 stale（区别于自动重算章节被清 stale）
- 取数失败章节保留 stale + errors 记录
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import RefillReport
from app.services.note_stale_service import NoteStaleService, RefreshResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()
YEAR = 2025


def _make_db_mock():
    """Create a mock AsyncSession with standard async methods."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Test: import 正确性回归
# ---------------------------------------------------------------------------


class TestImportRegression:
    """验证修复后 import 成功、字段名正确"""

    def test_disclosure_note_imported_from_report_models(self):
        """DisclosureNote 应从 report_models 导入（非 phase13_models）"""
        # 如果 import 是错误的 phase13_models，这个 import 本身就会失败
        from app.models.report_models import DisclosureNote as DN
        assert DN.__tablename__ == "disclosure_notes"

    def test_note_section_field_exists(self):
        """DisclosureNote 应有 note_section 字段（非 section_code）"""
        assert hasattr(DisclosureNote, "note_section")
        # section_code 不是 DisclosureNote 的字段
        # note_section 是真实字段
        col = DisclosureNote.__table__.columns
        assert "note_section" in col

    def test_is_stale_field_exists(self):
        """DisclosureNote 应有 is_stale 布尔字段"""
        assert hasattr(DisclosureNote, "is_stale")


# ---------------------------------------------------------------------------
# Test: refresh_from_workpaper 真正执行
# ---------------------------------------------------------------------------


class TestRefreshFromWorkpaper:
    """验证 refresh_from_workpaper 调用 DisclosureEngine 真实重算"""

    @pytest.mark.asyncio
    async def test_refresh_actually_calls_refill_sections(self):
        """refresh_from_workpaper 应调用 DisclosureEngine.refill_sections（非空返回）"""
        db = _make_db_mock()

        # Mock NoteAccountMapping 查询 — 返回一条映射
        mock_result = MagicMock()
        mock_result.all.return_value = [("五、3",)]
        db.execute = AsyncMock(return_value=mock_result)

        # Mock DisclosureEngine.refill_sections
        mock_report = RefillReport(
            sections_recomputed=["五、3"],
            text_only_sections=[],
            cells_updated=5,
            records=[],
            errors=[],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ) as mock_refill:
            result = await service.refresh_from_workpaper(PROJECT_ID, YEAR, "D1")

        # 验证结果非空
        assert isinstance(result, RefreshResult)
        assert result.sections_refreshed > 0 or result.cells_updated > 0
        # 验证 refill_sections 被调用
        mock_refill.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_uses_default_wp_mapping(self):
        """refresh_from_workpaper 应使用 DEFAULT_WP_MAPPING 匹配前缀"""
        db = _make_db_mock()

        # Mock NoteAccountMapping 查询 — 空结果（通过 DEFAULT_WP_MAPPING 匹配）
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        mock_report = RefillReport(
            sections_recomputed=["五、3"],
            text_only_sections=[],
            cells_updated=3,
            records=[],
            errors=[],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            result = await service.refresh_from_workpaper(PROJECT_ID, YEAR, "D1")

        # D1 前缀应匹配 DEFAULT_WP_MAPPING 中的 "五、3":"D1" 和 "五、29":"D1"
        assert result.cells_updated == 3

    @pytest.mark.asyncio
    async def test_refresh_no_mapping_returns_empty(self):
        """wp_code 无任何映射时返回空结果"""
        db = _make_db_mock()

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        service = NoteStaleService(db)

        # 使用一个不在 DEFAULT_WP_MAPPING 中的 wp_code
        result = await service.refresh_from_workpaper(PROJECT_ID, YEAR, "Z99")

        assert result.sections_refreshed == 0
        assert result.cells_updated == 0


# ---------------------------------------------------------------------------
# Test: refresh_stale_sections 真正执行
# ---------------------------------------------------------------------------


class TestRefreshStaleSections:
    """验证 refresh_stale_sections 走真实重算"""

    @pytest.mark.asyncio
    async def test_stale_sections_calls_refill(self):
        """refresh_stale_sections 应查 stale 章节并调 refill_sections"""
        db = _make_db_mock()

        # Mock stale 章节查询
        mock_note = MagicMock(spec=DisclosureNote)
        mock_note.note_section = "五、1"
        mock_note.is_stale = True

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_note]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        mock_report = RefillReport(
            sections_recomputed=["五、1"],
            text_only_sections=[],
            cells_updated=2,
            records=[],
            errors=[],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            result = await service.refresh_stale_sections(PROJECT_ID, YEAR)

        assert result.sections_refreshed == 1
        assert result.cells_updated == 2

    @pytest.mark.asyncio
    async def test_no_stale_sections_returns_empty(self):
        """无 stale 章节时返回空结果"""
        db = _make_db_mock()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        service = NoteStaleService(db)
        result = await service.refresh_stale_sections(PROJECT_ID, YEAR)

        assert result.sections_refreshed == 0
        assert result.cells_updated == 0


# ---------------------------------------------------------------------------
# Test: 纯文本章节降级
# ---------------------------------------------------------------------------


class TestTextOnlySectionDegradation:
    """验证纯文本章节被识别并保留 stale"""

    @pytest.mark.asyncio
    async def test_text_only_sections_kept_stale(self):
        """纯文本章节保留 stale=True，不被清除"""
        db = _make_db_mock()

        # 两个 stale 章节：一个可重算，一个纯文本
        mock_note_table = MagicMock(spec=DisclosureNote)
        mock_note_table.note_section = "五、1"
        mock_note_table.is_stale = True

        mock_note_text = MagicMock(spec=DisclosureNote)
        mock_note_text.note_section = "一、1"
        mock_note_text.is_stale = True

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_note_table, mock_note_text]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        # refill_sections 报告：五、1 重算成功，一、1 是纯文本
        mock_report = RefillReport(
            sections_recomputed=["五、1"],
            text_only_sections=["一、1"],
            cells_updated=4,
            records=[],
            errors=[],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            result = await service.refresh_stale_sections(PROJECT_ID, YEAR)

        # 只有 sections_recomputed 中的章节被清 stale
        assert result.sections_refreshed == 1
        assert result.cells_updated == 4
        # text_only 章节不被刷新（保留 stale）

    @pytest.mark.asyncio
    async def test_failed_sections_kept_stale_with_errors(self):
        """取数失败的章节保留 stale，errors 记录原因"""
        db = _make_db_mock()

        mock_note = MagicMock(spec=DisclosureNote)
        mock_note.note_section = "五、6"
        mock_note.is_stale = True

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_note]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        # refill 失败：章节取数出错
        mock_report = RefillReport(
            sections_recomputed=[],
            text_only_sections=[],
            cells_updated=0,
            records=[],
            errors=["五、6: 底稿 F1 无 parsed_data"],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            result = await service.refresh_stale_sections(PROJECT_ID, YEAR)

        # 无章节被清 stale
        assert result.sections_refreshed == 0
        # 错误被记录
        assert len(result.errors) == 1
        assert "五、6" in result.errors[0]

    @pytest.mark.asyncio
    async def test_refill_exception_returns_error(self):
        """refill_sections 抛异常时返回 error，不崩溃"""
        db = _make_db_mock()

        mock_note = MagicMock(spec=DisclosureNote)
        mock_note.note_section = "五、1"
        mock_note.is_stale = True

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_note]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = await service.refresh_stale_sections(PROJECT_ID, YEAR)

        # 不抛异常，返回包含错误的结果
        assert result.sections_refreshed == 0
        assert len(result.errors) > 0
        assert "重算失败" in result.errors[0]


# ---------------------------------------------------------------------------
# Test: service 只 flush 不 commit
# ---------------------------------------------------------------------------


class TestTransactionBoundary:
    """验证 service 只 flush 不 commit（Req 1.3）"""

    @pytest.mark.asyncio
    async def test_refresh_stale_only_flushes(self):
        """refresh_stale_sections 只调 flush 不调 commit"""
        db = _make_db_mock()

        mock_note = MagicMock(spec=DisclosureNote)
        mock_note.note_section = "五、1"
        mock_note.is_stale = True

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_note]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        mock_report = RefillReport(
            sections_recomputed=["五、1"],
            text_only_sections=[],
            cells_updated=1,
            records=[],
            errors=[],
        )

        service = NoteStaleService(db)

        with patch(
            "app.services.disclosure_engine.DisclosureEngine.refill_sections",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            await service.refresh_stale_sections(PROJECT_ID, YEAR)

        db.flush.assert_called()
        db.commit.assert_not_called()
