"""Wave5 集成测试 — 附注校验 findings 端到端集成（Task 6.1）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave5 (Task 6.1)
Reqs:   6.1 / 6.2 / 6.4

验证 generate_notes / sync 之后 ``NoteValidationEngine.validate_all`` 能产出**真实
findings**，覆盖四类核心勾稽（Req6.2）：

- 合计 = 分项之和           → ``纵向`` (VERTICAL) / ``其中项`` (SUB_ITEM)
- 附注合计 ↔ 报表行         → ``余额`` (BALANCE，section 键) / ``交叉`` (CROSS，report_row)
- 附注内部变动表期初+增-减=期末 → ``宽表`` (WIDE_TABLE)

并断言：
- 金额不平 → finding.passed=False（validate_all 收集进 findings）；
- 金额平 → 无 finding（passed=True 不进 findings）。
- findings dict 字段与前端 ``NoteValidationFinding`` 契约一致
  （note_section / table_name / check_type / severity / message /
  expected_value / actual_value）—— 见 DisclosureEditor.vue 校验面板消费。

两条验证路径（对齐 Task 6.1「validate_all 或 execute_all + ValidationContext」）：
1. ``TestFindingsViaValidateAll`` — mock DB，validate_all 端到端产出 findings dict。
2. ``TestExecutorCorrectnessDirect`` — db=None + ValidationContext 直调 execute_rule，
   逐类校验 balanced pass / unbalanced fail（不依赖 DB / preset.md）。
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

PROJECT_ID = uuid4()
YEAR = 2025

# 前端 NoteValidationFinding 消费字段（auditPlatformApi.ts + DisclosureEditor.vue 校验面板）
_FRONTEND_FINDING_KEYS = {
    "note_section",
    "table_name",
    "check_type",
    "severity",
    "message",
    "expected_value",
    "actual_value",
}


# ---------------------------------------------------------------------------
# mock 辅助
# ---------------------------------------------------------------------------


def _make_db_mock():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _result_scalars(objs):
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = objs
    res.scalars.return_value = scalars
    return res


def _result_all(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


def _note(section, table_data):
    n = MagicMock()
    n.note_section = section
    n.table_data = table_data
    n.is_stale = True
    return n


def _seq_execute(results_by_call):
    """按调用序返回结果；超出范围（如 _persist_results 的 insert）返回 MagicMock，
    避免 side_effect 列表耗尽抛 StopIteration 与调用次数强耦合。"""
    state = {"i": 0}

    async def _exec(*_a, **_k):
        i = state["i"]
        state["i"] += 1
        if i < len(results_by_call):
            return results_by_call[i]
        return MagicMock()

    return _exec


# ---------------------------------------------------------------------------
# table_data 构造器（inline _validation_rules 驱动）
# ---------------------------------------------------------------------------


def _vertical_td(detail_amounts, total, *, rule="纵向"):
    """纵向 / 其中项：明细行 + 合计行（is_total）。sum(明细)==total 时平衡。"""
    rows = [{"label": f"项{i}", "amount": a} for i, a in enumerate(detail_amounts)]
    rows.append({"label": "合计", "amount": total, "is_total": True})
    return {"_validation_rules": [rule], "rows": rows}


def _wide_table_td(opening, increase, decrease, closing):
    """宽表：期初+增-减 == 期末 时平衡。"""
    return {
        "_validation_rules": ["宽表"],
        "rows": [
            {
                "label": "甲",
                "opening": opening,
                "increase": increase,
                "decrease": decrease,
                "closing": closing,
            }
        ],
    }


def _balance_td(total):
    """余额：note.total 与 report_data[section] 比对（section 作报表键）。"""
    return {"_validation_rules": ["余额"], "total": total, "rows": []}


# ===========================================================================
# 路径 1 — validate_all 端到端产出真实 findings（mock DB）
# ===========================================================================


class TestFindingsViaValidateAll:
    """generate_notes/sync 后 validate_all 从 DB 装配数据 → 产出真实 findings。"""

    async def _run(self, notes, report_rows, tb_rows):
        db = _make_db_mock()
        db.execute = _seq_execute(
            [
                _result_scalars(notes),        # 1. note_data
                _result_all(report_rows),      # 2. _load_report_data
                _result_all(tb_rows),          # 3. _load_tb_data
                _result_scalars([]),           # 4. _load_prior_notes
            ]
        )
        engine = NoteValidationEngine(db)
        with patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            return await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")

    def _findings_for(self, result, section):
        return [f for f in result["findings"] if f["note_section"] == section]

    @pytest.mark.asyncio
    async def test_unbalanced_sections_produce_findings(self):
        """三类不平（纵向 / 余额 / 宽表）均产出 finding；平衡章节不产 finding。"""
        notes = [
            # 纵向：明细 100+200=300 ≠ 合计 500 → 不平
            _note("五、TEST-V", _vertical_td([100, 200], 500)),
            # 余额：note.total 900 ≠ 报表 1000 → 不平
            _note("五、TEST-B", _balance_td(900)),
            # 宽表：100+50-30=120 ≠ 期末 200 → 不平
            _note("五、TEST-W", _wide_table_td(100, 50, 30, 200)),
            # 平衡：明细 100+200=300 == 合计 300 → 不产 finding
            _note("五、TEST-OK", _vertical_td([100, 200], 300)),
        ]
        report_rows = [("五、TEST-B", Decimal("1000"))]
        result = await self._run(notes, report_rows, [])

        # 三个不平章节各产 finding
        assert len(self._findings_for(result, "五、TEST-V")) == 1
        assert len(self._findings_for(result, "五、TEST-B")) == 1
        assert len(self._findings_for(result, "五、TEST-W")) == 1
        # 平衡章节不产 finding
        assert self._findings_for(result, "五、TEST-OK") == []

    @pytest.mark.asyncio
    async def test_vertical_finding_expected_actual(self):
        """合计=分项：finding 携正确 expected(合计) / actual(分项和)。"""
        notes = [_note("五、TEST-V", _vertical_td([100, 200], 500))]
        result = await self._run(notes, [], [])
        f = self._findings_for(result, "五、TEST-V")[0]
        assert f["check_type"] == ValidationType.VERTICAL.value
        assert f["expected_value"] == 500.0   # 合计行
        assert f["actual_value"] == 300.0     # 分项之和
        assert f["severity"] == "error"       # diff=200 > 0.01

    @pytest.mark.asyncio
    async def test_balance_finding_note_vs_report(self):
        """附注↔报表行（余额）：expected=报表金额，actual=附注合计。"""
        notes = [_note("五、TEST-B", _balance_td(900))]
        report_rows = [("五、TEST-B", Decimal("1000"))]
        result = await self._run(notes, report_rows, [])
        f = self._findings_for(result, "五、TEST-B")[0]
        assert f["check_type"] == ValidationType.BALANCE.value
        assert f["expected_value"] == 1000.0
        assert f["actual_value"] == 900.0

    @pytest.mark.asyncio
    async def test_balanced_all_no_findings(self):
        """全部平衡时不产出任何本测试章节的 finding。"""
        notes = [
            _note("五、TEST-V", _vertical_td([100, 200], 300)),
            _note("五、TEST-B", _balance_td(1000)),
            _note("五、TEST-W", _wide_table_td(100, 50, 30, 120)),
        ]
        report_rows = [("五、TEST-B", Decimal("1000"))]
        result = await self._run(notes, report_rows, [])
        for sec in ("五、TEST-V", "五、TEST-B", "五、TEST-W"):
            assert self._findings_for(result, sec) == [], sec

    @pytest.mark.asyncio
    async def test_findings_dict_matches_frontend_contract(self):
        """finding dict 字段 ⊇ 前端 NoteValidationFinding 消费字段（DisclosureEditor 面板）。"""
        notes = [_note("五、TEST-V", _vertical_td([100, 200], 500))]
        result = await self._run(notes, [], [])
        assert result["findings"], "预期至少一条 finding"
        for f in result["findings"]:
            assert _FRONTEND_FINDING_KEYS.issubset(set(f.keys())), set(f.keys())

    @pytest.mark.asyncio
    async def test_result_summary_counts(self):
        """validate_all 返回结构含 total_rules/passed/failed，failed==findings 数。"""
        notes = [
            _note("五、TEST-V", _vertical_td([100, 200], 500)),   # 不平
            _note("五、TEST-OK", _vertical_td([100, 200], 300)),  # 平
        ]
        result = await self._run(notes, [], [])
        assert result["failed"] == len(result["findings"])
        assert result["total_rules"] >= result["passed"] + result["failed"]
        assert result["failed"] >= 1


# ===========================================================================
# 路径 2 — execute_rule + ValidationContext 直调（db=None，不依赖 preset.md）
# ===========================================================================


class TestExecutorCorrectnessDirect:
    """逐类校验 balanced→passed=True / unbalanced→passed=False（Task 6.1 金额平/不平）。"""

    def setup_method(self):
        self.engine = NoteValidationEngine(db=None)

    def _rule(self, section, rtype, **meta):
        return ValidationRule(
            section_code=section,
            rule_type=rtype,
            expression=f"preset:{rtype.value}",
            metadata=meta,
        )

    # ── 合计=分项（vertical）──
    @pytest.mark.asyncio
    async def test_vertical_balanced_passes(self):
        ctx = ValidationContext(note_data={"S": _vertical_td([100, 200], 300)})
        r = self.engine.execute_rule(self._rule("S", ValidationType.VERTICAL), ctx)
        assert r.passed is True

    @pytest.mark.asyncio
    async def test_vertical_unbalanced_fails(self):
        ctx = ValidationContext(note_data={"S": _vertical_td([100, 200], 500)})
        r = self.engine.execute_rule(self._rule("S", ValidationType.VERTICAL), ctx)
        assert r.passed is False
        assert r.expected_value == Decimal("500")
        assert r.actual_value == Decimal("300")

    # ── 合计=分项（sub_item）──
    @pytest.mark.asyncio
    async def test_sub_item_balanced_passes(self):
        ctx = ValidationContext(note_data={"S": _vertical_td([50, 50], 100, rule="其中项")})
        r = self.engine.execute_rule(self._rule("S", ValidationType.SUB_ITEM), ctx)
        assert r.passed is True

    @pytest.mark.asyncio
    async def test_sub_item_unbalanced_fails(self):
        ctx = ValidationContext(note_data={"S": _vertical_td([50, 50], 120, rule="其中项")})
        r = self.engine.execute_rule(self._rule("S", ValidationType.SUB_ITEM), ctx)
        assert r.passed is False
        assert r.diff_amount == Decimal("20")

    # ── 附注↔报表行（cross，report_row 显式目标）──
    @pytest.mark.asyncio
    async def test_cross_report_row_balanced_passes(self):
        ctx = ValidationContext(
            note_data={"S": {"total": 500}},
            report_data={"BS-015": Decimal("500")},
        )
        r = self.engine.execute_rule(
            self._rule("S", ValidationType.CROSS, report_row="BS-015"), ctx
        )
        assert r.passed is True
        assert r.details.get("target_kind") == "report"

    @pytest.mark.asyncio
    async def test_cross_report_row_unbalanced_fails(self):
        ctx = ValidationContext(
            note_data={"S": {"total": 500}},
            report_data={"BS-015": Decimal("400")},
        )
        r = self.engine.execute_rule(
            self._rule("S", ValidationType.CROSS, report_row="BS-015"), ctx
        )
        assert r.passed is False
        assert r.expected_value == Decimal("400")
        assert r.actual_value == Decimal("500")

    @pytest.mark.asyncio
    async def test_cross_missing_report_row_skips_not_false(self):
        """Skip_On_Missing：report_row 目标缺失 → passed=True + skipped（不误报）。"""
        ctx = ValidationContext(note_data={"S": {"total": 500}}, report_data={})
        r = self.engine.execute_rule(
            self._rule("S", ValidationType.CROSS, report_row="BS-999"), ctx
        )
        assert r.passed is True
        assert r.details.get("skipped") is True

    # ── 变动表期初+增-减=期末（wide_table）──
    @pytest.mark.asyncio
    async def test_wide_table_balanced_passes(self):
        ctx = ValidationContext(note_data={"S": _wide_table_td(100, 50, 30, 120)})
        r = self.engine.execute_rule(self._rule("S", ValidationType.WIDE_TABLE), ctx)
        assert r.passed is True
        assert r.details["unbalanced_rows"] == []

    @pytest.mark.asyncio
    async def test_wide_table_unbalanced_fails(self):
        ctx = ValidationContext(note_data={"S": _wide_table_td(100, 50, 30, 200)})
        r = self.engine.execute_rule(self._rule("S", ValidationType.WIDE_TABLE), ctx)
        assert r.passed is False
        assert r.details["unbalanced_rows"]
        assert r.details["unbalanced_rows"][0]["expected"] == 120.0
        assert r.details["unbalanced_rows"][0]["actual"] == 200.0
