"""附注语义结构 sidecar schema 测试

验证：
- 有效模型构建
- row_type 枚举值
- 可选字段处理 None
- 序列化往返

Validates: Requirements 3.1, 3.2, 3.3, 3.5
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.schemas.note_semantic_schema import (
    NoteCellMeta,
    NotePolicyClause,
    NoteRowType,
    NoteSemanticColumn,
    NoteSemanticMeta,
    NoteSemanticRow,
    NoteSemanticSidecar,
    NoteSemanticTable,
)


# ===========================================================================
# Unit Tests
# ===========================================================================


class TestNoteRowType:
    """row_type 枚举测试"""

    def test_all_enum_values_exist(self):
        """Requirements 3.2: 至少包括 9 种行类型"""
        expected = {
            "table_title",
            "group_header",
            "data",
            "subtotal",
            "total",
            "note_tip",
            "footnote",
            "blank",
            "custom",
        }
        actual = {e.value for e in NoteRowType}
        assert expected == actual

    def test_enum_is_str_enum(self):
        """行类型可以直接作为字符串比较"""
        assert NoteRowType.data == "data"
        assert NoteRowType.total == "total"

    def test_enum_from_value(self):
        """从字符串值构建枚举"""
        assert NoteRowType("table_title") is NoteRowType.table_title
        assert NoteRowType("custom") is NoteRowType.custom

    def test_invalid_row_type_raises(self):
        """无效行类型抛出 ValueError"""
        with pytest.raises(ValueError):
            NoteRowType("invalid_type")


class TestNoteSemanticColumn:
    """列语义定义测试"""

    def test_minimal_construction(self):
        """Requirements 3.3: col_id 为必填"""
        col = NoteSemanticColumn(col_id="closing_balance")
        assert col.col_id == "closing_balance"
        assert col.label == ""
        assert col.source is None
        assert col.amount_role is None

    def test_full_construction(self):
        """完整列定义"""
        col = NoteSemanticColumn(
            col_id="closing_balance",
            label="期末余额",
            source="workpaper",
            amount_role="closing",
        )
        assert col.col_id == "closing_balance"
        assert col.label == "期末余额"
        assert col.source == "workpaper"
        assert col.amount_role == "closing"


class TestNoteSemanticRow:
    """行语义定义测试"""

    def test_minimal_construction(self):
        """row_id 为必填，row_type 默认 data"""
        row = NoteSemanticRow(row_id="within_1_year")
        assert row.row_id == "within_1_year"
        assert row.row_type == NoteRowType.data
        assert row.label == ""
        assert row.values == []
        assert row.cell_modes is None
        assert row.cell_meta is None

    def test_full_construction_with_alias(self):
        """使用 JSON alias 构建（模拟反序列化）"""
        row = NoteSemanticRow(
            row_id="within_1_year",
            row_type=NoteRowType.data,
            label="1年以内",
            values=[100, 200],
            _cell_modes={"0": "auto"},
            _cell_meta={"0": NoteCellMeta(binding_id="ar_aging_within_1y_closing")},
        )
        assert row.row_id == "within_1_year"
        assert row.row_type == NoteRowType.data
        assert row.values == [100, 200]
        assert row.cell_modes == {"0": "auto"}
        assert row.cell_meta["0"].binding_id == "ar_aging_within_1y_closing"

    def test_row_type_enum_validation(self):
        """row_type 接受枚举值字符串"""
        row = NoteSemanticRow(row_id="total_row", row_type="total")
        assert row.row_type == NoteRowType.total


class TestNoteSemanticTable:
    """表语义定义测试"""

    def test_minimal_construction(self):
        """Requirements 3.1: table_id 为必填"""
        table = NoteSemanticTable(table_id="aging_analysis")
        assert table.table_id == "aging_analysis"
        assert table.name == ""
        assert table.columns == []
        assert table.rows == []

    def test_full_construction(self):
        """完整表定义"""
        table = NoteSemanticTable(
            table_id="aging_analysis",
            name="账龄分析",
            columns=[
                NoteSemanticColumn(
                    col_id="closing_balance",
                    label="期末余额",
                    source="workpaper",
                    amount_role="closing",
                )
            ],
            rows=[
                NoteSemanticRow(
                    row_id="within_1_year",
                    row_type=NoteRowType.data,
                    label="1年以内",
                    values=[100],
                )
            ],
        )
        assert table.table_id == "aging_analysis"
        assert table.name == "账龄分析"
        assert len(table.columns) == 1
        assert table.columns[0].col_id == "closing_balance"
        assert len(table.rows) == 1
        assert table.rows[0].row_id == "within_1_year"


class TestNoteSemanticMeta:
    """章节语义元数据测试"""

    def test_minimal_construction(self):
        """section_id 和 semantic_section_id 为必填"""
        meta = NoteSemanticMeta(
            section_id="accounts_receivable",
            semantic_section_id="accounts_receivable",
        )
        assert meta.section_id == "accounts_receivable"
        assert meta.semantic_section_id == "accounts_receivable"
        assert meta.variant is None
        assert meta.scope is None

    def test_full_construction(self):
        """完整元数据"""
        meta = NoteSemanticMeta(
            section_id="accounts_receivable",
            semantic_section_id="accounts_receivable",
            variant="soe_consolidated",
            scope="consolidated",
        )
        assert meta.variant == "soe_consolidated"
        assert meta.scope == "consolidated"


class TestNotePolicyClause:
    """会计政策条款测试"""

    def test_minimal_construction(self):
        """clause_id 为必填"""
        clause = NotePolicyClause(clause_id="policy_revenue")
        assert clause.clause_id == "policy_revenue"
        assert clause.title == ""
        assert clause.level == 1
        assert clause.current_text is None
        assert clause.template_text is None
        assert clause.prior_year_text is None
        assert clause.variables == []
        assert clause.diff_status == "unknown"
        assert clause.confirm_status == "pending"

    def test_full_construction(self):
        """完整条款"""
        clause = NotePolicyClause(
            clause_id="policy_revenue",
            title="收入确认",
            level=2,
            current_text="本年收入确认政策...",
            template_text="模板收入确认政策...",
            prior_year_text="上年收入确认政策...",
            variables=["company_name", "year"],
            diff_status="changed",
            confirm_status="pending",
        )
        assert clause.title == "收入确认"
        assert clause.level == 2
        assert clause.current_text == "本年收入确认政策..."
        assert clause.variables == ["company_name", "year"]
        assert clause.diff_status == "changed"

    def test_optional_text_fields_accept_none(self):
        """文本字段可以为 None"""
        clause = NotePolicyClause(
            clause_id="policy_cash",
            current_text=None,
            template_text=None,
            prior_year_text=None,
        )
        assert clause.current_text is None
        assert clause.template_text is None
        assert clause.prior_year_text is None


class TestNoteSemanticSidecar:
    """顶层容器测试"""

    def test_empty_sidecar(self):
        """空 sidecar 所有字段为默认值"""
        sidecar = NoteSemanticSidecar()
        assert sidecar.semantic is None
        assert sidecar.tables == []
        assert sidecar.policy_clauses == []

    def test_full_sidecar(self):
        """完整 sidecar 构建"""
        sidecar = NoteSemanticSidecar(
            _semantic=NoteSemanticMeta(
                section_id="accounts_receivable",
                semantic_section_id="accounts_receivable",
                variant="soe_consolidated",
                scope="consolidated",
            ),
            _tables=[
                NoteSemanticTable(
                    table_id="aging_analysis",
                    name="账龄分析",
                    columns=[
                        NoteSemanticColumn(
                            col_id="closing_balance",
                            label="期末余额",
                            source="workpaper",
                            amount_role="closing",
                        )
                    ],
                    rows=[
                        NoteSemanticRow(
                            row_id="within_1_year",
                            row_type=NoteRowType.data,
                            label="1年以内",
                            values=[100],
                            _cell_modes={"0": "auto"},
                            _cell_meta={
                                "0": NoteCellMeta(
                                    binding_id="ar_aging_within_1y_closing"
                                )
                            },
                        )
                    ],
                )
            ],
            _policy_clauses=[
                NotePolicyClause(
                    clause_id="policy_revenue",
                    title="收入确认",
                    level=2,
                    current_text="...",
                    diff_status="changed",
                    confirm_status="pending",
                )
            ],
        )
        assert sidecar.semantic is not None
        assert sidecar.semantic.section_id == "accounts_receivable"
        assert len(sidecar.tables) == 1
        assert sidecar.tables[0].table_id == "aging_analysis"
        assert len(sidecar.policy_clauses) == 1
        assert sidecar.policy_clauses[0].clause_id == "policy_revenue"


class TestSerializationRoundTrip:
    """序列化往返测试"""

    def test_sidecar_json_roundtrip(self):
        """sidecar → JSON → sidecar 往返一致"""
        original = NoteSemanticSidecar(
            _semantic=NoteSemanticMeta(
                section_id="accounts_receivable",
                semantic_section_id="accounts_receivable",
                variant="soe_consolidated",
                scope="consolidated",
            ),
            _tables=[
                NoteSemanticTable(
                    table_id="aging_analysis",
                    name="账龄分析",
                    columns=[
                        NoteSemanticColumn(
                            col_id="closing_balance",
                            label="期末余额",
                        )
                    ],
                    rows=[
                        NoteSemanticRow(
                            row_id="within_1_year",
                            row_type=NoteRowType.data,
                            label="1年以内",
                            values=[100],
                        )
                    ],
                )
            ],
            _policy_clauses=[
                NotePolicyClause(
                    clause_id="policy_revenue",
                    title="收入确认",
                    level=2,
                    diff_status="changed",
                    confirm_status="pending",
                )
            ],
        )
        # 序列化为 JSON（使用 alias）
        json_str = original.model_dump_json(by_alias=True)
        data = json.loads(json_str)

        # 验证 JSON 使用了 alias 键
        assert "_semantic" in data
        assert "_tables" in data
        assert "_policy_clauses" in data

        # 从 JSON 反序列化
        restored = NoteSemanticSidecar.model_validate(data)

        # 往返一致性
        assert restored.semantic.section_id == original.semantic.section_id
        assert restored.semantic.semantic_section_id == original.semantic.semantic_section_id
        assert restored.tables[0].table_id == original.tables[0].table_id
        assert restored.tables[0].rows[0].row_id == original.tables[0].rows[0].row_id
        assert restored.tables[0].rows[0].row_type == original.tables[0].rows[0].row_type
        assert restored.policy_clauses[0].clause_id == original.policy_clauses[0].clause_id

    def test_row_json_roundtrip_with_cell_meta(self):
        """行 → JSON → 行 往返（含 _cell_modes 和 _cell_meta alias）"""
        original = NoteSemanticRow(
            row_id="total_row",
            row_type=NoteRowType.total,
            label="合计",
            values=[1000, 2000],
            _cell_modes={"0": "formula", "1": "auto"},
            _cell_meta={
                "0": NoteCellMeta(binding_id="total_binding"),
                "1": NoteCellMeta(formula_id="f_001"),
            },
        )
        json_str = original.model_dump_json(by_alias=True)
        data = json.loads(json_str)

        # 验证 alias
        assert "_cell_modes" in data
        assert "_cell_meta" in data

        # 反序列化
        restored = NoteSemanticRow.model_validate(data)
        assert restored.row_id == "total_row"
        assert restored.row_type == NoteRowType.total
        assert restored.cell_modes == {"0": "formula", "1": "auto"}
        assert restored.cell_meta["0"].binding_id == "total_binding"
        assert restored.cell_meta["1"].formula_id == "f_001"

    def test_design_doc_example_parses(self):
        """设计文档示例 JSON 能被正确解析"""
        example_json = {
            "_semantic": {
                "section_id": "accounts_receivable",
                "semantic_section_id": "accounts_receivable",
                "variant": "soe_consolidated",
                "scope": "consolidated",
            },
            "_tables": [
                {
                    "table_id": "aging_analysis",
                    "name": "账龄分析",
                    "columns": [
                        {
                            "col_id": "closing_balance",
                            "label": "期末余额",
                            "source": "workpaper",
                            "amount_role": "closing",
                        }
                    ],
                    "rows": [
                        {
                            "row_id": "within_1_year",
                            "row_type": "data",
                            "label": "1年以内",
                            "values": [100],
                            "_cell_modes": {"0": "auto"},
                            "_cell_meta": {
                                "0": {"binding_id": "ar_aging_within_1y_closing"}
                            },
                        }
                    ],
                }
            ],
        }
        sidecar = NoteSemanticSidecar.model_validate(example_json)
        assert sidecar.semantic.section_id == "accounts_receivable"
        assert sidecar.tables[0].table_id == "aging_analysis"
        assert sidecar.tables[0].columns[0].col_id == "closing_balance"
        row = sidecar.tables[0].rows[0]
        assert row.row_id == "within_1_year"
        assert row.row_type == NoteRowType.data
        assert row.cell_modes == {"0": "auto"}
        assert row.cell_meta["0"].binding_id == "ar_aging_within_1y_closing"


# ===========================================================================
# Property-Based Tests
# ===========================================================================


# --- Strategies ---

note_row_type_st = st.sampled_from(list(NoteRowType))

col_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=30,
)

row_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=30,
)

table_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=30,
)

section_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=50,
)

clause_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=30,
)


@st.composite
def semantic_column_st(draw):
    return NoteSemanticColumn(
        col_id=draw(col_id_st),
        label=draw(st.text(max_size=20)),
        source=draw(st.one_of(st.none(), st.sampled_from(["workpaper", "formula", "manual", "prior_note"]))),
        amount_role=draw(st.one_of(st.none(), st.sampled_from(["opening", "closing", "current", "prior"]))),
    )


@st.composite
def semantic_row_st(draw):
    return NoteSemanticRow(
        row_id=draw(row_id_st),
        row_type=draw(note_row_type_st),
        label=draw(st.text(max_size=20)),
        values=draw(st.lists(st.one_of(st.integers(-10000, 10000), st.none()), max_size=5)),
    )


@st.composite
def semantic_table_st(draw):
    return NoteSemanticTable(
        table_id=draw(table_id_st),
        name=draw(st.text(max_size=20)),
        columns=draw(st.lists(semantic_column_st(), max_size=3)),
        rows=draw(st.lists(semantic_row_st(), max_size=3)),
    )


@st.composite
def semantic_meta_st(draw):
    return NoteSemanticMeta(
        section_id=draw(section_id_st),
        semantic_section_id=draw(section_id_st),
        variant=draw(st.one_of(
            st.none(),
            st.sampled_from(["soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"]),
        )),
        scope=draw(st.one_of(st.none(), st.sampled_from(["standalone", "consolidated", "both"]))),
    )


@st.composite
def policy_clause_st(draw):
    return NotePolicyClause(
        clause_id=draw(clause_id_st),
        title=draw(st.text(max_size=20)),
        level=draw(st.integers(1, 5)),
        current_text=draw(st.one_of(st.none(), st.text(max_size=50))),
        template_text=draw(st.one_of(st.none(), st.text(max_size=50))),
        prior_year_text=draw(st.one_of(st.none(), st.text(max_size=50))),
        variables=draw(st.lists(st.text(min_size=1, max_size=10), max_size=3)),
        diff_status=draw(st.sampled_from(["unchanged", "changed", "added", "removed", "unknown"])),
        confirm_status=draw(st.sampled_from(["pending", "confirmed", "rejected"])),
    )


@st.composite
def sidecar_st(draw):
    return NoteSemanticSidecar(
        _semantic=draw(st.one_of(st.none(), semantic_meta_st())),
        _tables=draw(st.lists(semantic_table_st(), max_size=2)),
        _policy_clauses=draw(st.lists(policy_clause_st(), max_size=2)),
    )


class TestPropertyBasedSerialization:
    """PBT: 序列化往返属性

    **Validates: Requirements 3.5** — 保持兼容性，序列化/反序列化不丢失数据。
    """

    @settings(max_examples=5)
    @given(sidecar=sidecar_st())
    def test_sidecar_roundtrip_property(self, sidecar: NoteSemanticSidecar):
        """任意 sidecar 序列化→反序列化后等价"""
        json_str = sidecar.model_dump_json(by_alias=True)
        restored = NoteSemanticSidecar.model_validate_json(json_str)

        # semantic
        if sidecar.semantic is None:
            assert restored.semantic is None
        else:
            assert restored.semantic.section_id == sidecar.semantic.section_id
            assert restored.semantic.semantic_section_id == sidecar.semantic.semantic_section_id
            assert restored.semantic.variant == sidecar.semantic.variant
            assert restored.semantic.scope == sidecar.semantic.scope

        # tables
        assert len(restored.tables) == len(sidecar.tables)
        for orig_t, rest_t in zip(sidecar.tables, restored.tables):
            assert rest_t.table_id == orig_t.table_id
            assert len(rest_t.columns) == len(orig_t.columns)
            assert len(rest_t.rows) == len(orig_t.rows)

        # policy_clauses
        assert len(restored.policy_clauses) == len(sidecar.policy_clauses)
        for orig_c, rest_c in zip(sidecar.policy_clauses, restored.policy_clauses):
            assert rest_c.clause_id == orig_c.clause_id
            assert rest_c.diff_status == orig_c.diff_status
            assert rest_c.confirm_status == orig_c.confirm_status

    @settings(max_examples=5)
    @given(row_type=note_row_type_st)
    def test_row_type_roundtrip_property(self, row_type: NoteRowType):
        """任意 row_type 序列化后仍为合法枚举值"""
        row = NoteSemanticRow(row_id="test", row_type=row_type)
        data = row.model_dump(by_alias=True)
        restored = NoteSemanticRow.model_validate(data)
        assert restored.row_type == row_type
        assert restored.row_type.value == row_type.value
