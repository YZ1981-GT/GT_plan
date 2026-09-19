"""测试：附注公式依赖图服务

测试公式依赖解析、语义锚点解析、旧公式兼容、冲突检测和依赖图构建。

Validates: Requirements 4.1, 4.3, 4.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_formula_dependency_service import (
    VALID_DEPENDENCY_TYPES,
    build_dependency_graph,
    detect_anchor_conflicts,
    parse_formula_dependencies,
    resolve_formula_anchor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TABLE_DATA = {
    "_semantic": {
        "section_id": "accounts_receivable",
        "semantic_section_id": "accounts_receivable",
    },
    "_tables": [
        {
            "table_id": "aging_analysis",
            "name": "账龄分析",
            "columns": [
                {"col_id": "closing_balance", "label": "期末余额"},
                {"col_id": "opening_balance", "label": "期初余额"},
                {"col_id": "provision", "label": "坏账准备"},
            ],
            "rows": [
                {"row_id": "within_1_year", "row_type": "data", "label": "1年以内", "values": [100, 90, 5]},
                {"row_id": "1_to_2_years", "row_type": "data", "label": "1-2年", "values": [50, 40, 10]},
                {"row_id": "total", "row_type": "total", "label": "合计", "values": [150, 130, 15]},
            ],
        },
        {
            "table_id": "bad_debt",
            "name": "坏账准备",
            "columns": [
                {"col_id": "opening", "label": "期初"},
                {"col_id": "provision_current", "label": "本期计提"},
                {"col_id": "closing", "label": "期末"},
            ],
            "rows": [
                {"row_id": "individual", "row_type": "data", "label": "单项", "values": [10, 5, 15]},
                {"row_id": "portfolio", "row_type": "data", "label": "组合", "values": [20, 3, 23]},
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Unit Tests: parse_formula_dependencies
# ---------------------------------------------------------------------------


class TestParseFormulaDependencies:
    """测试从公式表达式解析 TB/WP/REPORT/NOTE/PRIOR 依赖。"""

    def test_parse_wp_dependency(self) -> None:
        expr = "WP('D2','附注披露表','within_1_year_closing')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "workpaper"
        assert deps[0]["wp_code"] == "D2"
        assert deps[0]["sheet"] == "附注披露表"
        assert deps[0]["field"] == "within_1_year_closing"

    def test_parse_tb_dependency(self) -> None:
        expr = "TB('1122','期末')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "trial_balance"
        assert deps[0]["account_code"] == "1122"
        assert deps[0]["column"] == "期末"

    def test_parse_report_dependency(self) -> None:
        expr = "REPORT('BS-002','current')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "report"
        assert deps[0]["row_code"] == "BS-002"
        assert deps[0]["period"] == "current"

    def test_parse_note_dependency(self) -> None:
        expr = "NOTE('五、3','合计','期末')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "note"
        assert deps[0]["section"] == "五、3"
        assert deps[0]["aggregate"] == "合计"
        assert deps[0]["period"] == "期末"

    def test_parse_prior_dependency(self) -> None:
        expr = "PRIOR('应收账款','期末')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "prior"
        assert deps[0]["account_name"] == "应收账款"
        assert deps[0]["period"] == "期末"

    def test_parse_multiple_dependencies(self) -> None:
        expr = "TB('1001','期末') + WP('E1','审定表','B5') - REPORT('BS-001','current')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 3
        types = {d["type"] for d in deps}
        assert types == {"trial_balance", "workpaper", "report"}

    def test_parse_empty_expression(self) -> None:
        assert parse_formula_dependencies("") == []
        assert parse_formula_dependencies(None) == []  # type: ignore[arg-type]

    def test_parse_no_external_dependencies(self) -> None:
        """表内引用公式（cell/SUM）无外部依赖。"""
        expr = "SUM(0:3, 1)"
        deps = parse_formula_dependencies(expr)
        assert deps == []

    def test_parse_mixed_internal_external(self) -> None:
        """混合表内引用和外部依赖。"""
        expr = "cell(0,1) + TB('1001','期末')"
        deps = parse_formula_dependencies(expr)
        assert len(deps) == 1
        assert deps[0]["type"] == "trial_balance"


# ---------------------------------------------------------------------------
# Unit Tests: resolve_formula_anchor
# ---------------------------------------------------------------------------


class TestResolveFormulaAnchor:
    """测试语义锚点和位置锚点解析。"""

    def test_resolve_positional_anchor(self) -> None:
        """旧位置锚点 row:col 继续可用。"""
        result = resolve_formula_anchor("0:1", SAMPLE_TABLE_DATA)
        assert result == (0, 1)

    def test_resolve_positional_large_index(self) -> None:
        result = resolve_formula_anchor("10:5", SAMPLE_TABLE_DATA)
        assert result == (10, 5)

    def test_resolve_semantic_anchor(self) -> None:
        """新语义锚点 section.table.row.col 解析。"""
        result = resolve_formula_anchor(
            "accounts_receivable.aging_analysis.within_1_year.closing_balance",
            SAMPLE_TABLE_DATA,
        )
        assert result == (0, 0)

    def test_resolve_semantic_anchor_second_row(self) -> None:
        result = resolve_formula_anchor(
            "accounts_receivable.aging_analysis.1_to_2_years.opening_balance",
            SAMPLE_TABLE_DATA,
        )
        assert result == (1, 1)

    def test_resolve_semantic_anchor_total_row(self) -> None:
        result = resolve_formula_anchor(
            "accounts_receivable.aging_analysis.total.provision",
            SAMPLE_TABLE_DATA,
        )
        assert result == (2, 2)

    def test_resolve_semantic_second_table(self) -> None:
        """跨表解析：第二张表的语义锚点。"""
        result = resolve_formula_anchor(
            "accounts_receivable.bad_debt.individual.opening",
            SAMPLE_TABLE_DATA,
        )
        assert result == (0, 0)

    def test_resolve_nonexistent_table(self) -> None:
        result = resolve_formula_anchor(
            "accounts_receivable.nonexistent.row1.col1",
            SAMPLE_TABLE_DATA,
        )
        assert result is None

    def test_resolve_nonexistent_row(self) -> None:
        result = resolve_formula_anchor(
            "accounts_receivable.aging_analysis.nonexistent_row.closing_balance",
            SAMPLE_TABLE_DATA,
        )
        assert result is None

    def test_resolve_nonexistent_col(self) -> None:
        result = resolve_formula_anchor(
            "accounts_receivable.aging_analysis.within_1_year.nonexistent_col",
            SAMPLE_TABLE_DATA,
        )
        assert result is None

    def test_resolve_empty_anchor(self) -> None:
        assert resolve_formula_anchor("", SAMPLE_TABLE_DATA) is None
        assert resolve_formula_anchor(None, SAMPLE_TABLE_DATA) is None  # type: ignore[arg-type]

    def test_resolve_insufficient_parts(self) -> None:
        """不足 4 段的语义锚点返回 None。"""
        assert resolve_formula_anchor("section.table.row", SAMPLE_TABLE_DATA) is None
        assert resolve_formula_anchor("section.table", SAMPLE_TABLE_DATA) is None

    def test_resolve_with_empty_table_data(self) -> None:
        assert resolve_formula_anchor("0:1", {}) == (0, 1)  # positional still works
        assert resolve_formula_anchor("a.b.c.d", {}) is None  # semantic fails


# ---------------------------------------------------------------------------
# Unit Tests: detect_anchor_conflicts
# ---------------------------------------------------------------------------


class TestDetectAnchorConflicts:
    """测试旧下标锚点与新语义锚点冲突检测。"""

    def test_no_conflict_when_same_expression(self) -> None:
        """同一 cell 两种锚点但表达式相同 → 无冲突。"""
        formulas = {
            "0:0": {"expression": "TB('1122','期末')", "type": "cross_table"},
            "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                "expr": "TB('1122','期末')",
                "formula_id": "f_001",
            },
        }
        conflicts = detect_anchor_conflicts(formulas, SAMPLE_TABLE_DATA)
        assert conflicts == []

    def test_conflict_detected_different_expression(self) -> None:
        """同一 cell 两种锚点且表达式不同 → 冲突。"""
        formulas = {
            "0:0": {"expression": "TB('1122','期末')", "type": "cross_table"},
            "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                "expr": "WP('D2','附注披露表','ar_closing')",
                "formula_id": "f_001",
            },
        }
        conflicts = detect_anchor_conflicts(formulas, SAMPLE_TABLE_DATA)
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict["cell"] == (0, 0)
        assert "0:0" in conflict["positional_anchor"]
        assert "aging_analysis" in conflict["semantic_anchor"]
        assert "保留旧位置锚点结果" in conflict["message"]

    def test_no_conflict_different_cells(self) -> None:
        """不同 cell 的公式不算冲突。"""
        formulas = {
            "0:0": {"expression": "TB('1001','期末')", "type": "cross_table"},
            "accounts_receivable.aging_analysis.1_to_2_years.opening_balance": {
                "expr": "TB('1122','期初')",
                "formula_id": "f_002",
            },
        }
        conflicts = detect_anchor_conflicts(formulas, SAMPLE_TABLE_DATA)
        assert conflicts == []

    def test_empty_formulas(self) -> None:
        assert detect_anchor_conflicts({}, SAMPLE_TABLE_DATA) == []
        assert detect_anchor_conflicts(None, SAMPLE_TABLE_DATA) == []  # type: ignore[arg-type]

    def test_only_positional_no_conflict(self) -> None:
        """只有位置锚点，无语义锚点 → 无冲突。"""
        formulas = {
            "0:0": {"expression": "TB('1001','期末')"},
            "1:1": {"expression": "TB('1002','期初')"},
        }
        conflicts = detect_anchor_conflicts(formulas, SAMPLE_TABLE_DATA)
        assert conflicts == []

    def test_only_semantic_no_conflict(self) -> None:
        """只有语义锚点，无位置锚点 → 无冲突。"""
        formulas = {
            "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                "expr": "WP('D2','附注披露表','ar_closing')",
            },
        }
        conflicts = detect_anchor_conflicts(formulas, SAMPLE_TABLE_DATA)
        assert conflicts == []


# ---------------------------------------------------------------------------
# Unit Tests: build_dependency_graph
# ---------------------------------------------------------------------------


class TestBuildDependencyGraph:
    """测试依赖图构建。"""

    def test_build_single_formula_graph(self) -> None:
        formulas = {
            "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                "formula_id": "f_ar_001",
                "expr": "WP('D2','附注披露表','within_1_year_closing')",
            }
        }
        graph = build_dependency_graph(formulas)
        assert graph["summary"]["total_formulas"] == 1
        assert graph["summary"]["total_dependencies"] == 1
        assert graph["summary"]["by_type"]["workpaper"] == 1
        assert len(graph["nodes"]) == 1
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["type"] == "workpaper"
        assert "D2" in graph["edges"][0]["to"]

    def test_build_multi_dependency_graph(self) -> None:
        formulas = {
            "f1": {
                "formula_id": "f_001",
                "expr": "TB('1001','期末') + WP('E1','审定表','B5')",
            },
            "f2": {
                "formula_id": "f_002",
                "expr": "REPORT('BS-002','current') - PRIOR('应收账款','期末')",
            },
        }
        graph = build_dependency_graph(formulas)
        assert graph["summary"]["total_formulas"] == 2
        assert graph["summary"]["total_dependencies"] == 4
        assert graph["summary"]["by_type"]["trial_balance"] == 1
        assert graph["summary"]["by_type"]["workpaper"] == 1
        assert graph["summary"]["by_type"]["report"] == 1
        assert graph["summary"]["by_type"]["prior"] == 1

    def test_build_empty_graph(self) -> None:
        graph = build_dependency_graph({})
        assert graph["summary"]["total_formulas"] == 0
        assert graph["summary"]["total_dependencies"] == 0
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_build_graph_with_internal_only(self) -> None:
        """只有表内引用，无外部依赖。"""
        formulas = {
            "2:0": {
                "formula_id": None,
                "expression": "SUM(0:1, 0)",
                "type": "vertical_sum",
            }
        }
        graph = build_dependency_graph(formulas)
        assert graph["summary"]["total_formulas"] == 1
        assert graph["summary"]["total_dependencies"] == 0
        assert graph["nodes"][0]["dependencies"] == []

    def test_build_graph_note_dependency(self) -> None:
        formulas = {
            "x": {
                "expr": "NOTE('五、3','合计','期末')",
            }
        }
        graph = build_dependency_graph(formulas)
        assert graph["summary"]["by_type"]["note"] == 1
        assert "五、3" in graph["edges"][0]["to"]

    def test_build_graph_none_input(self) -> None:
        graph = build_dependency_graph(None)  # type: ignore[arg-type]
        assert graph["summary"]["total_formulas"] == 0


# ---------------------------------------------------------------------------
# Integration: formula error → quality checklist
# ---------------------------------------------------------------------------


class TestFormulaErrorInQualityChecklist:
    """测试公式执行失败进入质量清单的集成。"""

    def test_formula_with_last_error_generates_checklist_item(self) -> None:
        """含 last_error 的公式应被质量清单服务识别为 blocking。"""
        from app.services.note_quality_checklist_service import (
            NoteQualityChecklistService,
        )

        table_data = {
            "_semantic": {"section_id": "accounts_receivable"},
            "_formulas": {
                "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                    "formula_id": "f_001",
                    "expr": "WP('D2','附注披露表','missing_field')",
                    "last_error": "字段 missing_field 不存在",
                    "last_result": None,
                }
            },
        }

        svc = NoteQualityChecklistService()
        items = svc.generate_checklist([table_data])
        formula_items = [i for i in items if i.category == "formula"]
        assert len(formula_items) == 1
        assert formula_items[0].level == "blocking"
        assert "missing_field" in formula_items[0].message

    def test_formula_without_error_not_in_checklist(self) -> None:
        """无 last_error 的公式不进入质量清单。"""
        from app.services.note_quality_checklist_service import (
            NoteQualityChecklistService,
        )

        table_data = {
            "_semantic": {"section_id": "accounts_receivable"},
            "_formulas": {
                "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
                    "formula_id": "f_001",
                    "expr": "WP('D2','附注披露表','ar_closing')",
                    "last_error": None,
                    "last_result": "100.00",
                }
            },
        }

        svc = NoteQualityChecklistService()
        items = svc.generate_checklist([table_data])
        formula_items = [i for i in items if i.category == "formula"]
        assert formula_items == []


# ---------------------------------------------------------------------------
# Property-Based Test: parse_formula_dependencies 始终返回合法 type
# ---------------------------------------------------------------------------


class TestParseDependenciesPBT:
    """PBT: parse_formula_dependencies 对任意表达式始终返回合法 dependency types。

    **Validates: Requirements 4.5**
    """

    @settings(max_examples=5)
    @given(
        func_type=st.sampled_from(["TB", "WP", "REPORT", "NOTE", "PRIOR"]),
        arg1=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_-",
            ),
            min_size=1,
            max_size=20,
        ),
        arg2=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_-",
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_parse_always_returns_valid_types(
        self, func_type: str, arg1: str, arg2: str
    ) -> None:
        """对任意构造的公式表达式，parse_formula_dependencies 返回的 type 必在合法集合内。

        **Validates: Requirements 4.5**
        """
        # 构造各类型公式表达式
        if func_type == "TB":
            expr = f"TB('{arg1}','{arg2}')"
        elif func_type == "WP":
            expr = f"WP('{arg1}','{arg2}','field_x')"
        elif func_type == "REPORT":
            expr = f"REPORT('{arg1}','{arg2}')"
        elif func_type == "NOTE":
            expr = f"NOTE('{arg1}','{arg2}','期末')"
        else:  # PRIOR
            expr = f"PRIOR('{arg1}','{arg2}')"

        deps = parse_formula_dependencies(expr)
        assert len(deps) >= 1, f"Expected at least 1 dep for {expr}, got {deps}"
        for dep in deps:
            assert dep["type"] in VALID_DEPENDENCY_TYPES, (
                f"Invalid type '{dep['type']}' not in {VALID_DEPENDENCY_TYPES}"
            )
