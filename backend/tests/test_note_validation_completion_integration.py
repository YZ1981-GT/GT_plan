"""NoteValidationEngine.validate_all 端到端集成测试 + 契约 + 回归.

Spec:   .kiro/specs/disclosure-note-validation-completion/ Wave 4 Task 9
Reqs:   8.3, 9.1, 9.2, 9.3, 9.4, 9.5   Property: 1-12

覆盖：
- 集成：validate_all 端到端（mock report/tb 查询 + monkeypatch _invoke_llm_review）
        构造有 note_data 的场景 → 断言产出 findings（不平章节出 finding）
- 缺数据源全 skip 不误报：report_data/tb_data 全空 → 不产 false finding
- 异常源 fail-open：tb 底层查询抛异常 → _load_tb_data 内部 fail-open，
        validate_all 不抛、其余校验照常（P2）
- P12 回归：report_data 装配后 balance 用真实报表行金额比对（非恒 0）
- LLM warning：有正文 + monkeypatch _invoke_llm_review 返回问题 → warning finding（P9）
- 契约：EXECUTORS 覆盖全部 11 个 ValidationType 成员；枚举成员不变
- P11：execute_rule 对 executor 内部异常兜底（passed=True，不阻断）
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationContext,
    ValidationRule,
    ValidationType,
)
from app.services import note_validation_executors as nve
from app.services.note_validation_executors import (
    EXECUTORS,
    _execute_completeness,
)

PROJECT_ID = uuid4()
YEAR = 2025


# ---------------------------------------------------------------------------
# mock helpers（对齐 test_note_validation_context_loading）
# ---------------------------------------------------------------------------


def _make_db_mock():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _result_all(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


def _result_scalars(objs):
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = objs
    res.scalars.return_value = scalars
    return res


def _note(section, table_data):
    n = MagicMock()
    n.note_section = section
    n.table_data = table_data
    return n


# ---------------------------------------------------------------------------
# 集成：validate_all 端到端产 findings（不平章节）+ P12 端到端
# ---------------------------------------------------------------------------


class TestValidateAllProducesFindings:
    @pytest.mark.asyncio
    async def test_unbalanced_section_produces_finding(self):
        """有 note_data + report_data 不平 → validate_all 产 finding。

        兼作 P12 端到端：balance 用真实报表行金额比对（expected=100 非恒 0）。
        """
        db = _make_db_mock()
        # note query（inline 触发 "余额" 校验，note total=80）→ 后续 persist
        note = _note(
            "五、1",
            {"total": 80, "_validation_rules": ["余额"]},
        )
        db.execute.side_effect = [_result_scalars([note]), MagicMock()]

        engine = NoteValidationEngine(db)
        # patch 数据装配：report 与 note 不平（100 vs 80）
        engine._load_report_data = AsyncMock(return_value={"五、1": Decimal("100")})
        engine._load_tb_data = AsyncMock(return_value={})
        engine._load_prior_notes = AsyncMock(return_value={})
        # 隔离 preset.md 路径，聚焦 inline 校验
        engine.load_preset = AsyncMock(return_value=[])

        result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")

        assert result["failed"] >= 1
        findings = result["findings"]
        bal = [f for f in findings if f["note_section"] == "五、1"]
        assert bal, f"expected finding for 五、1, got {findings}"
        f0 = bal[0]
        assert f0["check_type"] == "余额"
        # P12：真实报表行金额 100（非恒 0）
        assert f0["expected_value"] == 100.0
        assert f0["actual_value"] == 80.0
        assert f0["severity"] == "error"

    @pytest.mark.asyncio
    async def test_balanced_section_no_finding(self):
        """report 与 note 平衡 → 不产 finding。"""
        db = _make_db_mock()
        note = _note("五、1", {"total": 100, "_validation_rules": ["余额"]})
        db.execute.side_effect = [_result_scalars([note]), MagicMock()]

        engine = NoteValidationEngine(db)
        engine._load_report_data = AsyncMock(return_value={"五、1": Decimal("100")})
        engine._load_tb_data = AsyncMock(return_value={})
        engine._load_prior_notes = AsyncMock(return_value={})
        engine.load_preset = AsyncMock(return_value=[])

        result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")
        assert result["failed"] == 0
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# LLM warning 路径（P9）：有正文 + monkeypatch _invoke_llm_review 产 warning
# ---------------------------------------------------------------------------


class TestValidateAllLlmReview:
    @pytest.mark.asyncio
    async def test_llm_review_warning_finding(self, monkeypatch):
        """有正文且 LLM 返回问题 → warning 级 AI 提示 finding。

        LLM_REVIEW 走 engine 的 async 特例路径 _execute_llm_review_async
        → await chat_completion，故 mock 模块级 chat_completion。
        """
        monkeypatch.setattr(
            nve, "chat_completion",
            AsyncMock(return_value="占位符残留 XX 未填写，与表格数据矛盾"),
        )
        db = _make_db_mock()
        note = _note(
            "五、20",
            {"text_content": "本年XX大幅增加", "_validation_rules": ["LLM审核"]},
        )
        db.execute.side_effect = [_result_scalars([note]), MagicMock()]

        engine = NoteValidationEngine(db)
        engine._load_report_data = AsyncMock(return_value={})
        engine._load_tb_data = AsyncMock(return_value={})
        engine._load_prior_notes = AsyncMock(return_value={})
        engine.load_preset = AsyncMock(return_value=[])

        result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")
        llm = [f for f in result["findings"] if f["note_section"] == "五、20"]
        assert llm, f"expected LLM warning finding, got {result['findings']}"
        assert llm[0]["check_type"] == "LLM审核"
        # 无 diff_amount → severity warning（AI 提示，非阻断）
        assert llm[0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_llm_review_fail_open_no_false_finding(self, monkeypatch):
        """P9 fail-open：chat_completion 抛异常 → 不误报不抛（async 路径）。"""
        monkeypatch.setattr(
            nve, "chat_completion", AsyncMock(side_effect=RuntimeError("llm down"))
        )
        db = _make_db_mock()
        note = _note(
            "五、20",
            {"text_content": "本年正文", "_validation_rules": ["LLM审核"]},
        )
        db.execute.side_effect = [_result_scalars([note]), MagicMock()]

        engine = NoteValidationEngine(db)
        engine._load_report_data = AsyncMock(return_value={})
        engine._load_tb_data = AsyncMock(return_value={})
        engine._load_prior_notes = AsyncMock(return_value={})
        engine.load_preset = AsyncMock(return_value=[])

        result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")
        # fail-open → 该章节不产 finding
        assert [f for f in result["findings"] if f["note_section"] == "五、20"] == []


# ---------------------------------------------------------------------------
# 缺数据源全 skip 不误报
# ---------------------------------------------------------------------------


class TestValidateAllNoFalsePositive:
    @pytest.mark.asyncio
    async def test_all_sources_empty_no_false_finding(self):
        """report_data/tb_data 全空 + note_data 空 → validate_all 不产 false finding。"""
        db = _make_db_mock()
        db.execute.side_effect = [_result_scalars([])]  # 空 note，无 persist

        engine = NoteValidationEngine(db)
        engine._load_report_data = AsyncMock(return_value={})
        engine._load_tb_data = AsyncMock(return_value={})
        engine._load_prior_notes = AsyncMock(return_value={})
        engine.load_preset = AsyncMock(return_value=[])

        result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")
        assert result["failed"] == 0
        assert result["findings"] == []

    def test_completeness_skips_when_tb_empty(self):
        """P4：完整性校验在 tb_data 全空时 Skip_On_Missing（不误报）。"""
        ctx = ValidationContext(note_data={}, tb_data={})
        rule = ValidationRule(
            section_code="",
            rule_type=ValidationType.COMPLETENESS,
            expression="全局完整性",
        )
        res = _execute_completeness(rule, ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True


# ---------------------------------------------------------------------------
# 异常源 fail-open（P2）：tb 底层查询抛 → validate_all 不抛、其余照常
# ---------------------------------------------------------------------------


class TestValidateAllFailOpen:
    @pytest.mark.asyncio
    async def test_tb_source_raises_validate_all_resilient(self):
        """P2：_load_tb_data 底层查询抛异常 → 内部 fail-open，其余校验照常。"""
        db = _make_db_mock()
        note = _note("五、1", {"total": 50})  # 无 inline 规则
        # 调用序列：note query / report select / tb select(raise) / prior select
        db.execute.side_effect = [
            _result_scalars([note]),
            _result_all([("五、1", Decimal("50"))]),
            RuntimeError("tb down"),
            _result_scalars([]),
        ]

        engine = NoteValidationEngine(db)
        engine.load_preset = AsyncMock(return_value=[])

        with patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")

        # 不抛、返回结构化，report/prior 装配照常（tb fail-open 不阻断）
        assert isinstance(result, dict)
        assert result["project_id"] == str(PROJECT_ID)
        assert result["year"] == YEAR
        assert "findings" in result


# ---------------------------------------------------------------------------
# 契约：EXECUTORS 覆盖全部 11 个 ValidationType + 枚举成员不变
# ---------------------------------------------------------------------------


class TestExecutorContract:
    def test_executors_cover_all_validation_types(self):
        """EXECUTORS 字典覆盖全部 11 个 ValidationType 枚举成员，无遗漏。"""
        assert set(EXECUTORS.keys()) == set(ValidationType)
        assert len(EXECUTORS) == 11
        # 每个 type 都有 callable executor
        for vt in ValidationType:
            assert callable(EXECUTORS[vt])

    def test_validation_type_members_unchanged(self):
        """ValidationType 恰好 11 个成员，值不变。"""
        expected = {
            "BALANCE": "余额",
            "WIDE_TABLE": "宽表",
            "VERTICAL": "纵向",
            "CROSS": "交叉",
            "CROSS_ACCOUNT": "跨科目",
            "SUB_ITEM": "其中项",
            "SECONDARY_DETAIL": "二级明细",
            "COMPLETENESS": "完整性",
            "AGING_PROGRESSION": "账龄衔接",
            "LLM_REVIEW": "LLM审核",
            "DESCRIPTION": "描述",
        }
        actual = {m.name: m.value for m in ValidationType}
        assert actual == expected
        assert len(ValidationType) == 11


# ---------------------------------------------------------------------------
# P11：execute_rule 对 executor 内部异常兜底（不阻断）
# ---------------------------------------------------------------------------


class TestExecuteRuleErrorGuard:
    def test_executor_exception_does_not_block(self, monkeypatch):
        """P11：executor 抛异常 → execute_rule 兜底返回 passed=True + details.error。"""

        def _boom(rule, ctx):
            raise ValueError("executor blew up")

        # EXECUTORS 与 engine._EXECUTORS 是同一 dict 对象引用
        monkeypatch.setitem(EXECUTORS, ValidationType.BALANCE, _boom)

        engine = NoteValidationEngine(None)
        rule = ValidationRule(
            section_code="五、1",
            rule_type=ValidationType.BALANCE,
            expression="preset:余额",
        )
        res = engine.execute_rule(rule, ValidationContext())
        assert res.passed is True  # 不阻断
        assert "error" in res.details
        assert "executor blew up" in res.details["error"]

    def test_missing_executor_does_not_block(self, monkeypatch):
        """无对应 executor 时也不阻断（passed=True + details.error）。"""
        monkeypatch.delitem(EXECUTORS, ValidationType.DESCRIPTION, raising=False)
        engine = NoteValidationEngine(None)
        rule = ValidationRule(
            section_code="五、9",
            rule_type=ValidationType.DESCRIPTION,
            expression="desc",
        )
        res = engine.execute_rule(rule, ValidationContext())
        assert res.passed is True
        assert "No executor" in res.details.get("error", "")
