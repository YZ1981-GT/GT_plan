"""Tests for Sprint C.1 — 附注 AI 辅助服务 (D10).

Covers:
- C.1.1: suggest_dynamic_rows
- C.1.2: generate_paragraph_from_workpaper
- C.1.3: check_wp_tb_consistency
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_ai_assistant_service import NoteAIAssistantService


# ---------------------------------------------------------------------------
# C.1.1: suggest_dynamic_rows
# ---------------------------------------------------------------------------


class TestSuggestDynamicRows:
    """C.1.1 — AI 建议动态行."""

    @pytest.mark.asyncio
    async def test_no_accounts_returns_empty(self):
        service = NoteAIAssistantService(db=None)
        result = await service.suggest_dynamic_rows("section_cash", uuid4(), 2025)
        assert result == []

    @pytest.mark.asyncio
    async def test_suggests_when_aux_count_gt_3(self):
        service = NoteAIAssistantService(db=None)
        # Mock internal methods
        service._get_section_accounts = AsyncMock(return_value=["1122", "1123"])
        service._query_aux_balance = AsyncMock(return_value=[
            {"aux_type": "客户", "aux_code": "C001", "aux_name": "客户A"},
            {"aux_type": "客户", "aux_code": "C002", "aux_name": "客户B"},
            {"aux_type": "客户", "aux_code": "C003", "aux_name": "客户C"},
            {"aux_type": "客户", "aux_code": "C004", "aux_name": "客户D"},
            {"aux_type": "客户", "aux_code": "C005", "aux_name": "客户E"},
        ])

        result = await service.suggest_dynamic_rows("section_ar", uuid4(), 2025)
        assert len(result) == 1
        assert result[0]["region_name"] == "aux_客户"
        assert result[0]["aux_count"] == 5
        assert result[0]["suggested_source"] == "aux_balance"
        assert result[0]["confidence"] > 0.5

    @pytest.mark.asyncio
    async def test_no_suggestion_when_aux_count_le_3(self):
        service = NoteAIAssistantService(db=None)
        service._get_section_accounts = AsyncMock(return_value=["1001"])
        service._query_aux_balance = AsyncMock(return_value=[
            {"aux_type": "银行", "aux_code": "B001", "aux_name": "工行"},
            {"aux_type": "银行", "aux_code": "B002", "aux_name": "建行"},
        ])

        result = await service.suggest_dynamic_rows("section_cash", uuid4(), 2025)
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_aux_types(self):
        service = NoteAIAssistantService(db=None)
        service._get_section_accounts = AsyncMock(return_value=["1122"])
        service._query_aux_balance = AsyncMock(return_value=[
            {"aux_type": "客户", "aux_code": "C001"},
            {"aux_type": "客户", "aux_code": "C002"},
            {"aux_type": "客户", "aux_code": "C003"},
            {"aux_type": "客户", "aux_code": "C004"},
            {"aux_type": "项目", "aux_code": "P001"},
            {"aux_type": "项目", "aux_code": "P002"},
        ])

        result = await service.suggest_dynamic_rows("section_ar", uuid4(), 2025)
        # Only 客户 has > 3
        assert len(result) == 1
        assert result[0]["aux_type"] == "客户"


# ---------------------------------------------------------------------------
# C.1.2: generate_paragraph_from_workpaper
# ---------------------------------------------------------------------------


class TestGenerateParagraph:
    """C.1.2 — 从底稿生成段落."""

    @pytest.mark.asyncio
    async def test_no_wp_data_returns_empty(self):
        service = NoteAIAssistantService(db=None)
        service._load_workpaper_data = AsyncMock(return_value=None)
        result = await service.generate_paragraph_from_workpaper("h08", "section_fa", uuid4(), 2025)
        assert result == ""

    @pytest.mark.asyncio
    async def test_with_wp_data_returns_stub(self):
        service = NoteAIAssistantService(db=None)
        service._load_workpaper_data = AsyncMock(return_value={"summary": "固定资产减值测试通过"})
        result = await service.generate_paragraph_from_workpaper("h08", "section_fa", uuid4(), 2025)
        # LLM stub returns fallback text
        assert "h08" in result

    @pytest.mark.asyncio
    async def test_extract_summary_from_conclusion(self):
        service = NoteAIAssistantService(db=None)
        wp_data = {"结论": "经测试，商誉未发生减值"}
        summary = service._extract_wp_summary(wp_data, "h08")
        assert "商誉" in summary

    @pytest.mark.asyncio
    async def test_extract_summary_from_sheet_text(self):
        service = NoteAIAssistantService(db=None)
        wp_data = {"Sheet1": {"text": "本期固定资产增加 500 万元"}}
        summary = service._extract_wp_summary(wp_data, "h01")
        assert "固定资产" in summary


# ---------------------------------------------------------------------------
# C.1.3: check_wp_tb_consistency
# ---------------------------------------------------------------------------


class TestCheckConsistency:
    """C.1.3 — wp_data 与 TB 一致性校核."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self):
        service = NoteAIAssistantService(db=None)
        result = await service.check_wp_tb_consistency(uuid4(), 2025)
        assert result == []

    @pytest.mark.asyncio
    async def test_consistency_check_structure(self):
        service = NoteAIAssistantService(db=None)
        service._load_wp_bindings = AsyncMock(return_value=[
            {"section_id": "s1", "wp_code": "h08", "account_codes": ["1601"], "field": "amount"},
        ])
        service._get_wp_value = AsyncMock(return_value=100000.0)
        service._get_tb_value = AsyncMock(return_value=99000.0)

        result = await service.check_wp_tb_consistency(uuid4(), 2025)
        assert len(result) == 1
        assert result[0]["section_id"] == "s1"
        assert result[0]["diff"] == 1000.0
        assert result[0]["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_high_severity_diff(self):
        service = NoteAIAssistantService(db=None)
        service._load_wp_bindings = AsyncMock(return_value=[
            {"section_id": "s1", "wp_code": "h08", "account_codes": ["1601"], "field": "amount"},
        ])
        service._get_wp_value = AsyncMock(return_value=500000.0)
        service._get_tb_value = AsyncMock(return_value=480000.0)

        result = await service.check_wp_tb_consistency(uuid4(), 2025)
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_no_diff_no_issue(self):
        service = NoteAIAssistantService(db=None)
        service._load_wp_bindings = AsyncMock(return_value=[
            {"section_id": "s1", "wp_code": "h08", "account_codes": ["1601"], "field": "amount"},
        ])
        service._get_wp_value = AsyncMock(return_value=100.0)
        service._get_tb_value = AsyncMock(return_value=100.0)

        result = await service.check_wp_tb_consistency(uuid4(), 2025)
        assert result == []

    @pytest.mark.asyncio
    async def test_none_values_skipped(self):
        service = NoteAIAssistantService(db=None)
        service._load_wp_bindings = AsyncMock(return_value=[
            {"section_id": "s1", "wp_code": "h08", "account_codes": ["1601"], "field": "amount"},
        ])
        service._get_wp_value = AsyncMock(return_value=None)
        service._get_tb_value = AsyncMock(return_value=100.0)

        result = await service.check_wp_tb_consistency(uuid4(), 2025)
        assert result == []
