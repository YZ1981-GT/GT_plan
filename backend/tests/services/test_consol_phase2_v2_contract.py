"""合并模块 Phase 2 S4 V2 灰度结构契约测试（hypothesis + 集成）

V2 附注（generate_full_consol_notes）返回 plain dict 章节，老版（generate_consol_notes_sync）
返回 Pydantic ConsolDisclosureSection。路由 response_model=list[ConsolDisclosureSection]，
因此 `_adapt_v2_sections_to_schema` 必须把任意 V2 dict 归一化为合法 ConsolDisclosureSection
——这就是 S4 结构等价不变量：无论 V2 数据形态如何（dict 行 / list 行 / 缺键 / None 行 /
非 dict 章节），适配器永不抛错，且总返回合法 ConsolDisclosureSection 列表。

属性 S4（需求 3.3）：CONSOL_NOTES_V2_ENABLED 切换不破坏返回结构契约（章节列表 schema 一致）。

Validates: Requirements 3.1, 3.2, 3.3 (Property S4)
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.models.consolidation_schemas import ConsolDisclosureRow, ConsolDisclosureSection
from app.services.consol_disclosure_service import (
    _adapt_v2_row_to_schema,
    _adapt_v2_sections_to_schema,
)

# ---------------------------------------------------------------------------
# strategies：刻意生成"乱"的 V2 数据形态（契约不变量必须对所有形态成立）
# ---------------------------------------------------------------------------

# 单元格值：字符串 / 数字 / None / bool
_cell_value = st.one_of(
    st.text(max_size=20),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.none(),
    st.booleans(),
)

# V2 行：dict（col_1..col_6 / col1..col6 混用 + 可能缺键）/ list / None / 非法标量
_v2_row_dict = st.dictionaries(
    keys=st.sampled_from(
        ["col_1", "col_2", "col_3", "col_4", "col_5", "col_6",
         "col1", "col2", "col3", "row_index", "extra_key"]
    ),
    values=_cell_value,
    max_size=6,
)
_v2_row_list = st.lists(_cell_value, max_size=8)
_v2_row = st.one_of(_v2_row_dict, _v2_row_list, st.none(), st.integers())

# V2 章节：dict（含/缺 table_data、rows、section_id/section_title）/ 非 dict（应被跳过）
_v2_section = st.one_of(
    st.fixed_dictionaries(
        {
            "section_id": st.one_of(st.text(max_size=15), st.none()),
            "section_title": st.one_of(st.text(max_size=20), st.none()),
            "table_data": st.one_of(
                st.fixed_dictionaries(
                    {
                        "rows": st.lists(_v2_row, max_size=5),
                        "summary": st.one_of(st.text(max_size=20), st.none()),
                    }
                ),
                st.none(),
                st.integers(),  # table_data 非 dict（防御）
            ),
            "section_type": st.sampled_from(["group_header", "data", "text", None]),
            "is_editable": st.booleans(),
        }
    ),
    st.none(),  # 非 dict 章节 → 应被跳过
    st.integers(),
    st.text(max_size=10),
)


# ===========================================================================
# 行级适配器契约
# ===========================================================================


class TestAdaptRowContract:
    """_adapt_v2_row_to_schema 对任意输入返回合法 ConsolDisclosureRow。"""

    @given(row=_v2_row)
    @settings(max_examples=15)
    def test_always_returns_valid_row(self, row):
        """任意 V2 行形态 → 返回 ConsolDisclosureRow，永不抛错。"""
        result = _adapt_v2_row_to_schema(row)
        assert isinstance(result, ConsolDisclosureRow)
        # 所有单元格值均被 stringify（None 保持 None）
        for i in range(1, 7):
            val = getattr(result, f"col{i}")
            assert val is None or isinstance(val, str)

    def test_dict_col_naming_variants(self):
        """col_1 与 col1 命名都接受。"""
        r1 = _adapt_v2_row_to_schema({"col_1": "A", "col_2": "B"})
        assert r1.col1 == "A" and r1.col2 == "B"
        r2 = _adapt_v2_row_to_schema({"col1": "X"})
        assert r2.col1 == "X"

    def test_list_row_positional_mapping(self):
        """list 行按位置映射到 col_1..col_6，多余截断。"""
        r = _adapt_v2_row_to_schema(["a", "b", "c", "d", "e", "f", "g", "h"])
        assert r.col1 == "a" and r.col6 == "f"

    def test_none_row_returns_empty(self):
        """None 行 → 空行。"""
        r = _adapt_v2_row_to_schema(None)
        assert isinstance(r, ConsolDisclosureRow)
        assert all(getattr(r, f"col{i}") is None for i in range(1, 7))


# ===========================================================================
# S4 章节级契约不变量
# ===========================================================================


class TestS4SectionContractInvariant:
    """S4：_adapt_v2_sections_to_schema 对任意 V2 形态返回合法 ConsolDisclosureSection 列表。

    这是结构等价属性——适配器把 V2 归一化为老版契约（路由 response_model 成立）。

    **Validates: Requirements 3.3**
    """

    @given(v2_sections=st.lists(_v2_section, max_size=8))
    @settings(max_examples=15)
    def test_always_returns_valid_section_list(self, v2_sections):
        """任意 V2 章节列表（含 dict/None/标量混杂）→ 永不抛错，每项均合法 schema。"""
        result = _adapt_v2_sections_to_schema(v2_sections)

        assert isinstance(result, list)
        for sec in result:
            # 契约核心：每项都是合法 ConsolDisclosureSection
            assert isinstance(sec, ConsolDisclosureSection)
            # 必填字段 schema 一致（与老版 response_model 相同）
            assert isinstance(sec.section_code, str)
            assert isinstance(sec.section_title, str)
            assert isinstance(sec.rows, list)
            assert isinstance(sec.is_editable, bool)
            assert isinstance(sec.is_group_header, bool)
            for row in sec.rows:
                assert isinstance(row, ConsolDisclosureRow)

    @given(v2_sections=st.lists(_v2_section, max_size=8))
    @settings(max_examples=10)
    def test_non_dict_sections_skipped(self, v2_sections):
        """非 dict 章节被跳过 → 结果章节数 == 输入中 dict 章节数。"""
        result = _adapt_v2_sections_to_schema(v2_sections)
        dict_count = sum(1 for s in v2_sections if isinstance(s, dict))
        assert len(result) == dict_count

    def test_empty_and_none_input(self):
        """空列表 / None 输入 → 返回空列表（不抛错）。"""
        assert _adapt_v2_sections_to_schema([]) == []
        assert _adapt_v2_sections_to_schema(None) == []


# ===========================================================================
# S4 集成：V2 dict 章节 vs 老版 ConsolDisclosureSection 的 schema 等价
# ===========================================================================


class TestS4SchemaEquivalence:
    """V2 适配结果与老版 ConsolDisclosureSection 字段集完全一致（结构契约）。

    **Validates: Requirements 3.3**
    """

    def test_v2_adapted_field_set_matches_legacy(self):
        """适配后的章节 model_dump 字段集 == 老版直接构造的字段集。"""
        # 老版章节（直接构造 Pydantic）
        legacy = ConsolDisclosureSection(
            section_code="note_cash",
            section_title="货币资金",
            content="合计 100",
            rows=[ConsolDisclosureRow(col_1="银行存款", col_2="100")],
        )

        # V2 dict 章节经适配器
        v2_dict = {
            "section_id": "note_cash",
            "section_title": "货币资金",
            "table_data": {
                "rows": [{"col_1": "银行存款", "col_2": "100"}],
                "summary": "合计 100",
            },
        }
        adapted = _adapt_v2_sections_to_schema([v2_dict])
        assert len(adapted) == 1

        # 字段集（schema）必须完全一致
        assert set(legacy.model_dump().keys()) == set(adapted[0].model_dump().keys())
        # 关键字段映射正确
        assert adapted[0].section_code == "note_cash"
        assert adapted[0].section_title == "货币资金"
        assert adapted[0].content == "合计 100"
        assert adapted[0].rows[0].col1 == "银行存款"

    def test_group_header_inferred_from_section_type(self):
        """section_type == 'group_header' → is_group_header=True。"""
        adapted = _adapt_v2_sections_to_schema(
            [{"section_id": "h", "section_title": "标题", "section_type": "group_header"}]
        )
        assert adapted[0].is_group_header is True

    def test_missing_keys_default_to_empty_strings(self):
        """V2 章节缺 section_id/section_title → 默认空字符串（仍合法 schema）。"""
        adapted = _adapt_v2_sections_to_schema([{}])
        assert len(adapted) == 1
        assert adapted[0].section_code == ""
        assert adapted[0].section_title == ""
        assert adapted[0].rows == []
