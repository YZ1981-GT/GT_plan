"""test_regulatory_letter_service — A18-2 监管沟通函 service 单元测试

覆盖:
- check_completeness：空/部分/全填/不适用
- export_word：模板调用（mock filler）
- get_a8_step_suggestion：映射逻辑
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.regulatory_letter_service import (
    RegulatoryLetterService,
    a18_check_incomplete,
    a18_export_word,
    get_a8_step_suggestion,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_db(responses: list[dict] | None = None, header: str | None = None):
    """创建 mock AsyncSession"""
    db = AsyncMock()

    async def _execute(stmt, params=None):
        result = MagicMock()
        sql_text = str(stmt.text) if hasattr(stmt, "text") else str(stmt)

        if "item_id LIKE 'A18-2-%'" in sql_text:
            rows = responses or []
            result.mappings.return_value.all.return_value = rows
        elif "item_id = :item_id" in sql_text:
            result.scalar_one_or_none.return_value = header
        elif "FROM projects" in sql_text:
            row = {"client_name": "测试公司", "audit_period_end": MagicMock(year=2025)}
            result.mappings.return_value.first.return_value = row
        else:
            result.mappings.return_value.all.return_value = []
        return result

    db.execute = _execute
    return db


# ─── check_completeness ──────────────────────────────────────────────────────


class TestCheckCompleteness:
    """完整性检查测试"""

    @pytest.mark.asyncio
    async def test_all_empty_returns_4_incomplete(self):
        """全部未填写 → 4 项 incomplete"""
        db = _make_db(responses=[])
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is True
        assert result["count"] == 4
        assert len(result["incomplete_topics"]) == 4

    @pytest.mark.asyncio
    async def test_all_na_returns_complete(self):
        """全部不适用 → complete"""
        responses = [
            {"item_id": f"A18-2-00{i}", "conclusion": "N", "remark": ""}
            for i in range(1, 5)
        ]
        db = _make_db(responses=responses)
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is False
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_applicable_with_content_is_complete(self):
        """适用且有内容 → complete"""
        responses = [
            {"item_id": "A18-2-001", "conclusion": "Y", "remark": json.dumps({"content": "发现舞弊线索"})},
            {"item_id": "A18-2-002", "conclusion": "N", "remark": ""},
            {"item_id": "A18-2-003", "conclusion": "N", "remark": ""},
            {"item_id": "A18-2-004", "conclusion": "N", "remark": ""},
        ]
        db = _make_db(responses=responses)
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is False

    @pytest.mark.asyncio
    async def test_applicable_without_content_is_incomplete(self):
        """适用但无内容 → incomplete"""
        responses = [
            {"item_id": "A18-2-001", "conclusion": "Y", "remark": json.dumps({"content": ""})},
            {"item_id": "A18-2-002", "conclusion": "N", "remark": ""},
            {"item_id": "A18-2-003", "conclusion": "N", "remark": ""},
            {"item_id": "A18-2-004", "conclusion": "N", "remark": ""},
        ]
        db = _make_db(responses=responses)
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is True
        assert result["count"] == 1
        assert "舞弊" in result["incomplete_topics"]


# ─── export_word ─────────────────────────────────────────────────────────────


class TestExportWord:
    """导出 Word 测试（mock filler）"""

    @pytest.mark.asyncio
    async def test_export_calls_fill_and_export(self):
        """验证 export_word 调用 fill_and_export + export_to_bytes"""
        responses = [
            {"item_id": "A18-2-001", "conclusion": "Y", "remark": json.dumps({"content": "舞弊描述"})},
            {"item_id": "A18-2-002", "conclusion": "N", "remark": ""},
            {"item_id": "A18-2-003", "conclusion": "Y", "remark": json.dumps({"content": "一致", "radioChoice": "no_inconsistency"})},
            {"item_id": "A18-2-004", "conclusion": "N", "remark": ""},
        ]
        header_json = json.dumps({"companyName": "ABC公司", "auditYear": "2025", "regulator": "证监会", "partnerName": "张三"})
        db = _make_db(responses=responses, header=header_json)

        mock_doc = MagicMock()
        mock_doc.add_paragraph = MagicMock(return_value=MagicMock())
        mock_doc.paragraphs = []

        with patch("app.services.regulatory_letter_service._TEMPLATE_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("app.services.regulatory_letter_service.fill_and_export") as mock_fill:
                from app.services.docx_template_filler import FillResult
                mock_fill.return_value = (mock_doc, FillResult())
                with patch("app.services.regulatory_letter_service.export_to_bytes", return_value=b"PK\x03\x04fake") as mock_export:
                    with patch("docx.Document", return_value=mock_doc):
                        svc = RegulatoryLetterService()
                        result = await svc.export_word(db, uuid4(), uuid4())

        assert result == b"PK\x03\x04fake"
        mock_fill.assert_called_once()
        # context should have client_name and audit_year
        call_args = mock_fill.call_args
        context_arg = call_args[0][1]
        assert context_arg["client_name"] == "ABC公司"
        assert context_arg["audit_year"] == "2025"
        mock_export.assert_called_once_with(mock_doc)


# ─── get_a8_step_suggestion ──────────────────────────────────────────────────


class TestA8Suggestion:
    """A8 步骤建议映射"""

    @pytest.mark.asyncio
    async def test_all_completed_suggests_no_inconsistency(self):
        """A8 seq 3/4/5 全 completed → no_inconsistency"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = [
            {"item_id": "A8-seq-3", "conclusion": "completed"},
            {"item_id": "A8-seq-4", "conclusion": "completed"},
            {"item_id": "A8-seq-5", "conclusion": "completed"},
        ]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] == "no_inconsistency"

    @pytest.mark.asyncio
    async def test_in_progress_suggests_minor(self):
        """有 in_progress → minor_uncorrected"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = [
            {"item_id": "A8-seq-3", "conclusion": "completed"},
            {"item_id": "A8-seq-4", "conclusion": "in_progress"},
            {"item_id": "A8-seq-5", "conclusion": "completed"},
        ]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] == "minor_uncorrected"

    @pytest.mark.asyncio
    async def test_no_rows_returns_none(self):
        """无数据 → None"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] is None


# ─── convenience functions ───────────────────────────────────────────────────


class TestConvenience:
    """模块级快捷函数"""

    @pytest.mark.asyncio
    async def test_a18_check_incomplete_delegates(self):
        db = _make_db(responses=[])
        result = await a18_check_incomplete(db, uuid4(), uuid4())
        assert "has_incomplete" in result
        assert result["wp_code"] == "A18-2"
