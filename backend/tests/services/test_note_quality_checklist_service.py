"""附注质量清单服务测试

测试 NoteQualityChecklistService 的各类检查逻辑。

Validates: Requirements 9.1, 9.2, 9.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.note_quality_checklist_service import (
    VALID_CATEGORIES,
    VALID_LEVELS,
    NoteQualityChecklistService,
    QualityChecklistItem,
)


@pytest.fixture
def service() -> NoteQualityChecklistService:
    return NoteQualityChecklistService()


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestFormulaErrorDetection:
    """测试公式错误检测"""

    def test_detects_formula_with_last_error(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "accounts_receivable"},
            "_formulas": {
                "accounts_receivable.aging_analysis.total.closing_balance": {
                    "formula_id": "f_001",
                    "expr": "SUM(A1:A5)",
                    "last_error": "除零错误",
                    "last_result": None,
                }
            },
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "blocking"
        assert item.category == "formula"
        assert item.section_id == "accounts_receivable"
        assert item.table_id == "aging_analysis"
        assert item.row_id == "total"
        assert item.col_id == "closing_balance"
        assert "除零错误" in item.message

    def test_no_error_when_formula_succeeds(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "cash"},
            "_formulas": {
                "cash.main.row1.col1": {
                    "formula_id": "f_002",
                    "expr": "WP('E1','现金','余额')",
                    "last_error": None,
                    "last_result": "1000.00",
                }
            },
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 0

    def test_multiple_formula_errors(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "fixed_assets"},
            "_formulas": {
                "fixed_assets.main.row1.col1": {
                    "formula_id": "f_003",
                    "last_error": "来源缺失",
                },
                "fixed_assets.main.row2.col2": {
                    "formula_id": "f_004",
                    "last_error": "公式语法错误",
                },
            },
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 2
        assert all(i.category == "formula" for i in items)


class TestStaleDataDetection:
    """测试数据陈旧检测"""

    def test_detects_stale_bool(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "accounts_receivable"},
            "_stale": True,
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "warning"
        assert item.category == "stale"
        assert item.section_id == "accounts_receivable"

    def test_detects_stale_dict(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "cash"},
            "_stale": {"reason": "底稿 E1 已更新", "source_wp": "E1"},
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "warning"
        assert item.category == "stale"
        assert "E1" in item.message
        assert item.evidence is not None
        assert item.evidence["source_wp"] == "E1"

    def test_no_stale_when_absent(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "cash"},
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 0


class TestManualOverrideDetection:
    """测试手工覆盖检测"""

    def test_detects_unconfirmed_manual_override(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "accounts_receivable"},
            "_tables": [
                {
                    "table_id": "aging_analysis",
                    "columns": [
                        {"col_id": "closing_balance", "label": "期末余额"},
                    ],
                    "rows": [
                        {
                            "row_id": "within_1_year",
                            "row_type": "data",
                            "_cell_modes": {"0": "manual"},
                            "_cell_meta": {"0": {}},
                        },
                    ],
                }
            ],
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "warning"
        assert item.category == "manual_override"
        assert item.table_id == "aging_analysis"
        assert item.row_id == "within_1_year"
        assert item.col_id == "closing_balance"

    def test_no_issue_when_manual_confirmed(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "cash"},
            "_tables": [
                {
                    "table_id": "main",
                    "columns": [{"col_id": "amount"}],
                    "rows": [
                        {
                            "row_id": "r1",
                            "row_type": "data",
                            "_cell_modes": {"0": "manual"},
                            "_cell_meta": {"0": {"confirmed": True}},
                        },
                    ],
                }
            ],
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 0

    def test_no_issue_when_mode_is_auto(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "cash"},
            "_tables": [
                {
                    "table_id": "main",
                    "columns": [{"col_id": "amount"}],
                    "rows": [
                        {
                            "row_id": "r1",
                            "row_type": "data",
                            "_cell_modes": {"0": "auto"},
                            "_cell_meta": {},
                        },
                    ],
                }
            ],
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 0


class TestAiUnconfirmedDetection:
    """测试 AI 未确认检测"""

    def test_detects_ai_draft_bool(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "related_party"},
            "_ai_draft": True,
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "blocking"
        assert item.category == "ai"

    def test_detects_ai_draft_dict_unconfirmed(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "related_party"},
            "_ai_draft": {"status": "pending"},
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        item = items[0]
        assert item.level == "blocking"
        assert item.category == "ai"

    def test_no_issue_when_ai_confirmed(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "related_party"},
            "_ai_draft": {"status": "confirmed"},
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 0


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_input_returns_empty_list(self, service: NoteQualityChecklistService):
        items = service.generate_checklist([])
        assert items == []

    def test_empty_table_data_returns_empty(self, service: NoteQualityChecklistService):
        items = service.generate_checklist([{}])
        assert items == []

    def test_section_id_defaults_to_unknown(self, service: NoteQualityChecklistService):
        table_data = {
            "_stale": True,
        }
        items = service.generate_checklist([table_data])
        assert len(items) == 1
        assert items[0].section_id == "unknown"

    def test_multiple_sections_aggregated(self, service: NoteQualityChecklistService):
        data1 = {
            "_semantic": {"section_id": "sec_a"},
            "_stale": True,
        }
        data2 = {
            "_semantic": {"section_id": "sec_b"},
            "_ai_draft": True,
        }
        items = service.generate_checklist([data1, data2])
        assert len(items) == 2
        section_ids = {i.section_id for i in items}
        assert section_ids == {"sec_a", "sec_b"}


class TestLevelClassification:
    """测试 blocking vs warning 级别"""

    def test_formula_errors_are_blocking(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "test"},
            "_formulas": {"test.t.r.c": {"last_error": "err"}},
        }
        items = service.generate_checklist([table_data])
        assert items[0].level == "blocking"

    def test_stale_data_is_warning(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "test"},
            "_stale": True,
        }
        items = service.generate_checklist([table_data])
        assert items[0].level == "warning"

    def test_manual_override_is_warning(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "test"},
            "_tables": [
                {
                    "table_id": "t1",
                    "columns": [{"col_id": "c1"}],
                    "rows": [
                        {
                            "row_id": "r1",
                            "_cell_modes": {"0": "manual"},
                            "_cell_meta": {"0": {}},
                        }
                    ],
                }
            ],
        }
        items = service.generate_checklist([table_data])
        assert items[0].level == "warning"

    def test_ai_unconfirmed_is_blocking(self, service: NoteQualityChecklistService):
        table_data = {
            "_semantic": {"section_id": "test"},
            "_ai_draft": True,
        }
        items = service.generate_checklist([table_data])
        assert items[0].level == "blocking"


# ---------------------------------------------------------------------------
# Property-Based Test
# ---------------------------------------------------------------------------


# Strategies for generating table_data
st_section_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)

st_formula_error = st.fixed_dictionaries(
    {"last_error": st.text(min_size=1, max_size=30)},
    optional={"formula_id": st.text(min_size=1, max_size=10), "expr": st.text(max_size=30)},
)

st_formulas = st.dictionaries(
    keys=st.from_regex(r"[a-z_]{1,10}\.[a-z_]{1,10}\.[a-z_]{1,10}\.[a-z_]{1,10}", fullmatch=True),
    values=st_formula_error,
    min_size=0,
    max_size=3,
)

st_stale = st.one_of(
    st.just(None),
    st.just(True),
    st.just(False),
    st.fixed_dictionaries({"reason": st.text(min_size=1, max_size=20)}),
)

st_ai_draft = st.one_of(
    st.just(None),
    st.just(True),
    st.just(False),
    st.fixed_dictionaries({"status": st.sampled_from(["pending", "confirmed", "rejected"])}),
)

st_table_data = st.fixed_dictionaries(
    {"_semantic": st.fixed_dictionaries({"section_id": st_section_id})},
    optional={
        "_formulas": st_formulas,
        "_stale": st_stale,
        "_ai_draft": st_ai_draft,
    },
)


@settings(max_examples=5)
@given(table_data_list=st.lists(st_table_data, min_size=0, max_size=3))
def test_all_items_have_valid_level_and_category(
    table_data_list: list[dict],
):
    """**Validates: Requirements 9.2**

    Property: All generated checklist items must have valid level and category values.
    """
    service = NoteQualityChecklistService()
    items = service.generate_checklist(table_data_list)
    for item in items:
        assert item.level in VALID_LEVELS, f"Invalid level: {item.level}"
        assert item.category in VALID_CATEGORIES, f"Invalid category: {item.category}"
        assert isinstance(item.message, str) and len(item.message) > 0
