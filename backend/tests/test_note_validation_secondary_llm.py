"""Wave 3 — 二级明细汇总(_execute_secondary_detail) + LLM 文本合理性审核(async) 三态测试.

Spec:   .kiro/specs/disclosure-note-validation-completion/ Wave 3 Task 7 + Task 8
Reqs:   6.1-6.3 / 7.1-7.4 / 8.1, 8.2
属性:   Task7 → P8(二级汇总不平出 finding / 无结构 skip) / P10(只读)
        Task8 → P9(LLM fail-open：占位串/异常/无正文 不误报不抛) / P10(只读)

审计铁律：executor 只读不写；Skip 优于误报（缺数据/无结构 passed=True + details.skipped）；
LLM fail-open（占位串 `[.../⚠️...` / 异常 → skip）；context 值转字符串；容差走 _resolve_tolerance。

LLM executor 是 **async**（唯一需 await chat_completion），由引擎 execute_all 的 async 特例
路径（NoteValidationEngine._run_rule）分发到 _execute_llm_review_async；其余 10 个同步执行器
经 execute_rule 不变。测试用 asyncio.run 驱动 async，mock 打在 executor 实际 import 处
（app.services.note_validation_executors.chat_completion）。
"""

from __future__ import annotations

import asyncio
import copy
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationContext,
    ValidationRule,
    ValidationType,
)
from app.services.note_validation_executors import (
    _execute_llm_review_async,
    _execute_secondary_detail,
)

_LLM_PATCH_TARGET = "app.services.note_validation_executors.chat_completion"


def _rule(rtype: ValidationType, section: str = "五、7", **md) -> ValidationRule:
    return ValidationRule(
        section_code=section,
        rule_type=rtype,
        expression=f"test:{rtype.value}",
        metadata=md,
    )


# ===========================================================================
# Task 7 — _execute_secondary_detail（Req6 / P8 / P10）
# ===========================================================================


def _level_section(parent_amt, *child_amts):
    """层级结构：level=1 父 + level=2 子（顺序分组）。"""
    rows = [{"label": "应收账款", "level": 1, "amount": parent_amt}]
    for i, ca in enumerate(child_amts):
        rows.append({"label": f"客户{i}", "level": 2, "amount": ca})
    return {"rows": rows}


class TestSecondaryDetailSkipOnMissing:
    """无二级明细结构 / 章节缺失 / 空 → Skip_On_Missing（P8）。"""

    def test_missing_section_skips(self):
        ctx = ValidationContext(note_data={})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_flat_rows_no_structure_skips(self):
        """单层明细（无 level/parent/children）→ 不臆造层次 → skip。"""
        ctx = ValidationContext(
            note_data={"五、7": {"rows": [
                {"label": "甲", "amount": 100},
                {"label": "乙", "amount": 50},
            ]}}
        )
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_empty_section_skips(self):
        ctx = ValidationContext(note_data={"五、7": {"rows": [], "total": 0}})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is True
        assert res.details.get("skipped") is True


class TestSecondaryDetailBalance:
    """P8：Σ二级明细 = 一级项目金额 → pass；不平 → finding。"""

    def test_balanced_level_group_passes(self):
        ctx = ValidationContext(note_data={"五、7": _level_section(100, 60, 40)})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is True
        assert not res.details.get("imbalances")

    def test_unbalanced_level_group_finding(self):
        ctx = ValidationContext(note_data={"五、7": _level_section(100, 60, 30)})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is False
        assert len(res.details.get("imbalances", [])) == 1
        assert res.diff_amount is not None and res.diff_amount > 0

    def test_balanced_parent_ref_group_passes(self):
        """显式 parent 引用分组：Σ子 = 父。"""
        td = {"rows": [
            {"id": "p1", "label": "长期股权投资", "amount": 300},
            {"parent": "p1", "label": "子公司A", "amount": 200},
            {"parent": "p1", "label": "子公司B", "amount": 100},
        ]}
        ctx = ValidationContext(note_data={"五、7": td})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is True

    def test_unbalanced_parent_ref_group_finding(self):
        td = {"rows": [
            {"id": "p1", "label": "长期股权投资", "amount": 300},
            {"parent": "p1", "label": "子公司A", "amount": 200},
            {"parent": "p1", "label": "子公司B", "amount": 50},  # 250 ≠ 300
        ]}
        ctx = ValidationContext(note_data={"五、7": td})
        res = _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert res.passed is False
        assert res.diff_amount == Decimal("50")


class TestSecondaryDetailReadOnly:
    """P10：执行前后 ctx 深比不变（只读）。"""

    def test_finding_path_read_only(self):
        ctx = ValidationContext(note_data={"五、7": _level_section(100, 60, 30)})
        before = copy.deepcopy(ctx)
        _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert ctx == before

    def test_skip_path_read_only(self):
        ctx = ValidationContext(note_data={})
        before = copy.deepcopy(ctx)
        _execute_secondary_detail(_rule(ValidationType.SECONDARY_DETAIL), ctx)
        assert ctx == before


# ===========================================================================
# Task 8 — _execute_llm_review_async（Req7 / P9 fail-open / P10 只读）
# ===========================================================================


def _text_ctx(text: str, section: str = "五、7") -> ValidationContext:
    return ValidationContext(
        note_data={section: {"text_content": text, "rows": [
            {"label": "银行存款", "amount": 500},
        ], "total": 500}}
    )


class TestLlmReviewFindingAndPass:
    def test_llm_flags_problem_produces_warning_finding(self):
        """LLM 指出问题 → warning 级 AI 提示 finding（P9 反例：正常返回）。"""
        ctx = _text_ctx("货币资金主要为银行存款 XX 万元（占位符未替换）。")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="1. 存在占位符 XX 未填写")):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is False
        assert res.details.get("ai_hint") is True
        assert res.details.get("severity") == "warning"
        assert res.details.get("skipped") is not True
        assert "XX" in res.details.get("llm_review", "")

    def test_llm_no_issue_passes(self):
        """LLM 返回"无异常" → pass。"""
        ctx = _text_ctx("货币资金主要为银行存款，期末余额 500 元，与表格一致。")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="无异常")):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("ai_hint") is True
        assert res.details.get("skipped") is not True


class TestLlmReviewFailOpen:
    """P9：LLM 不可用/超时/占位串/异常/无正文 → skip（passed=True），不误报、不抛。"""

    def test_placeholder_reply_skips(self):
        ctx = _text_ctx("正文内容")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="[LLM 服务暂不可用，请检查 vLLM 是否启动]")):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_warning_placeholder_reply_skips(self):
        ctx = _text_ctx("正文内容")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="⚠️ LLM 未返回有效内容，请重试。")):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_empty_reply_skips(self):
        ctx = _text_ctx("正文内容")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="")):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_exception_does_not_raise_and_skips(self):
        """chat_completion 抛异常 → executor 捕获 → skip（不抛、不误报）。"""
        ctx = _text_ctx("正文内容")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(side_effect=RuntimeError("boom"))):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("skipped") is True

    def test_no_text_content_skips_without_llm_call(self):
        """无正文 → skip，且根本不调用 LLM。"""
        ctx = ValidationContext(note_data={"五、7": {"rows": [], "total": 0}})
        rule = _rule(ValidationType.LLM_REVIEW)
        mock = AsyncMock(return_value="不应被调用")
        with patch(_LLM_PATCH_TARGET, new=mock):
            res = asyncio.run(_execute_llm_review_async(rule, ctx))
        assert res.passed is True
        assert res.details.get("skipped") is True
        mock.assert_not_awaited()


class TestLlmReviewReadOnly:
    """P10：LLM 审核只读，执行前后 ctx 深比不变。"""

    def test_warning_path_read_only(self):
        ctx = _text_ctx("含占位符 XX")
        before = copy.deepcopy(ctx)
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="1. 占位符残留")):
            asyncio.run(_execute_llm_review_async(rule, ctx))
        assert ctx == before

    def test_skip_path_read_only(self):
        ctx = _text_ctx("正文")
        before = copy.deepcopy(ctx)
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(side_effect=RuntimeError("boom"))):
            asyncio.run(_execute_llm_review_async(rule, ctx))
        assert ctx == before


# ===========================================================================
# 引擎 async 特例路径：NoteValidationEngine._run_rule（LLM→async / 其余→同步）
# ===========================================================================


class TestEngineAsyncDispatch:
    def test_run_rule_routes_llm_to_async_warning(self):
        """LLM_REVIEW 经 _run_rule 走 async 特例，真实（mock）调用 chat_completion。"""
        engine = NoteValidationEngine(db=None)
        ctx = _text_ctx("含占位符 XX")
        rule = _rule(ValidationType.LLM_REVIEW)
        with patch(_LLM_PATCH_TARGET, new=AsyncMock(return_value="1. 占位符残留")):
            res = asyncio.run(engine._run_rule(rule, ctx))
        assert res.passed is False
        assert res.details.get("ai_hint") is True

    def test_run_rule_non_llm_uses_sync_executor(self):
        """非 LLM 规则经 _run_rule 走同步 execute_rule（行为不变）。"""
        engine = NoteValidationEngine(db=None)
        # VERTICAL：明细和 ≠ 合计 → finding（同步执行器）
        ctx = ValidationContext(note_data={"五、7": {"rows": [
            {"label": "甲", "amount": 60},
            {"label": "乙", "amount": 30},
            {"is_total": True, "amount": 100},
        ]}})
        rule = _rule(ValidationType.VERTICAL)
        sync_res = engine.execute_rule(rule, ctx)
        async_res = asyncio.run(engine._run_rule(rule, ctx))
        assert async_res.passed == sync_res.passed
        assert async_res.passed is False  # 90 ≠ 100
