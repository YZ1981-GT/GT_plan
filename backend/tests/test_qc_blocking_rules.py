"""QC 阻断级规则真实测试 — 验证 4 类阻断场景"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def mock_wp():
    """创建模拟底稿"""
    wp = MagicMock()
    wp.id = uuid4()
    wp.project_id = uuid4()
    wp.reviewer = None
    wp.parsed_data = {}
    wp.file_path = "storage/test.xlsx"
    wp.file_version = 1
    wp.wp_index_id = uuid4()
    return wp


@pytest.fixture
def mock_context(mock_wp):
    from app.services.qc_engine import QCContext
    db = AsyncMock()
    ctx = QCContext(db=db, working_paper=mock_wp, project_id=mock_wp.project_id)
    return ctx


class TestConclusionNotEmpty:
    """QC-01: 结论区为空时阻断"""

    @pytest.mark.asyncio
    async def test_empty_conclusion_blocks(self, mock_context):
        from app.services.qc_engine import ConclusionNotEmptyRule
        rule = ConclusionNotEmptyRule()
        mock_context.working_paper.parsed_data = {}
        findings = await rule.check(mock_context)
        assert len(findings) == 1
        assert findings[0].severity == "blocking"
        assert "结论" in findings[0].message

    @pytest.mark.asyncio
    async def test_filled_conclusion_passes(self, mock_context):
        from app.services.qc_engine import ConclusionNotEmptyRule
        rule = ConclusionNotEmptyRule()
        mock_context.working_paper.parsed_data = {"conclusion": "经审计，该科目金额正确"}
        findings = await rule.check(mock_context)
        assert len(findings) == 0


class TestAIFillConfirmed:
    """QC-02: AI 未确认内容阻断"""

    @pytest.mark.asyncio
    async def test_unconfirmed_ai_blocks(self, mock_context):
        from app.services.qc_engine import AIFillConfirmedRule
        rule = AIFillConfirmedRule()
        mock_context.working_paper.parsed_data = {
            "ai_content": [
                {"cell_ref": "B5", "status": "pending"},
                {"cell_ref": "B6", "status": "accepted"},
            ]
        }
        findings = await rule.check(mock_context)
        assert len(findings) == 1
        assert "未确认" in findings[0].message

    @pytest.mark.asyncio
    async def test_all_confirmed_passes(self, mock_context):
        from app.services.qc_engine import AIFillConfirmedRule
        rule = AIFillConfirmedRule()
        mock_context.working_paper.parsed_data = {
            "ai_content": [
                {"cell_ref": "B5", "status": "accepted"},
                {"cell_ref": "B6", "status": "modified"},
            ]
        }
        findings = await rule.check(mock_context)
        assert len(findings) == 0


class TestFormulaConsistency:
    """QC-03: 审定数公式不平衡阻断"""

    @pytest.mark.asyncio
    async def test_formula_mismatch_blocks(self, mock_context):
        from app.services.qc_engine import FormulaConsistencyRule
        rule = FormulaConsistencyRule()
        mock_context.working_paper.parsed_data = {
            "unadjusted_amount": 100000,
            "aje_adjustment": 5000,
            "rje_adjustment": -2000,
            "audited_amount": 999999,  # 应该是 103000
        }
        findings = await rule.check(mock_context)
        assert len(findings) == 1
        assert "审定数" in findings[0].message

    @pytest.mark.asyncio
    async def test_formula_balanced_passes(self, mock_context):
        from app.services.qc_engine import FormulaConsistencyRule
        rule = FormulaConsistencyRule()
        mock_context.working_paper.parsed_data = {
            "unadjusted_amount": 100000,
            "aje_adjustment": 5000,
            "rje_adjustment": -2000,
            "audited_amount": 103000,
        }
        findings = await rule.check(mock_context)
        assert len(findings) == 0


class TestReviewerAssigned:
    """QC-04: 复核人未分配阻断"""

    @pytest.mark.asyncio
    async def test_no_reviewer_blocks(self, mock_context):
        from app.services.qc_engine import ReviewerAssignedRule
        rule = ReviewerAssignedRule()
        mock_context.working_paper.reviewer = None
        findings = await rule.check(mock_context)
        assert len(findings) == 1
        assert "复核人" in findings[0].message

    @pytest.mark.asyncio
    async def test_reviewer_assigned_passes(self, mock_context):
        from app.services.qc_engine import ReviewerAssignedRule
        rule = ReviewerAssignedRule()
        mock_context.working_paper.reviewer = uuid4()
        findings = await rule.check(mock_context)
        assert len(findings) == 0


class TestQCEngineIntegration:
    """QC 引擎集成测试"""

    def test_engine_has_5_blocking_rules(self):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        blocking = [r for r in engine.rules if r.severity == "blocking"]
        assert len(blocking) == 5

    def test_rule_ids_unique(self):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        ids = [r.rule_id for r in engine.rules]
        assert len(ids) == len(set(ids)), f"重复 rule_id: {[x for x in ids if ids.count(x) > 1]}"

    def test_rule_ids_sequential(self):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        ids = [int(r.rule_id.split("-")[1]) for r in engine.rules]
        assert ids == sorted(ids), "rule_id 不连续"
