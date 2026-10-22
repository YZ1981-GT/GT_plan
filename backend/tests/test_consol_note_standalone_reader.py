"""单体附注读取层测试（consol_note_standalone_reader）。

样本取真库形态（2026-10-22 只读探针）：安徽「八、1」_tables 行带 _cell_meta / _cell_modes；
宜宾「八、1」workpaper 来源 sub_table_data + _sub_table_columns（行名「现金」）；应收账款坏账
准备分类表单体拆成期末表 +「（续：期初数）」续表、列分组用「账面金额」。合并模板一律用真模板
（find_table），不手写合并表头。
"""
from __future__ import annotations

import pytest

from app.services.consol_note_formula_service import find_table
from app.services.consol_note_section_mapping import resolve_mapping_entry
from app.services.consol_note_standalone_reader import (
    pick_standalone_table,
    read_source_table,
)

# 表头路径 / 列语义键 / 续表认定的用例在 tests/test_note_table_header_library.py（读取层已收口到标题行库）


def _meta(section: str, label: str) -> dict:
    return {
        "0": {"semantic": "closing_balance", "binding_id": f"{section}.{label}.closing_balance", "manual_value": None},
        "1": {"semantic": "opening_balance", "binding_id": f"{section}.{label}.opening_balance", "manual_value": None},
    }


def _row(label: str, values: list, *, total: bool = False) -> dict:
    return {
        "label": label, "values": values, "is_total": total,
        "row_type": "total" if total else "data",
        "_cell_meta": _meta("八、1", label), "_cell_modes": {"0": "auto", "1": "auto"},
    }


ANHUI_CASH = {
    "name": "货币资金",
    "headers": ["项目", "期末余额", "期初余额"],
    "rows": [
        _row("库存现金", [376.73, 286.73]),
        _row("银行存款", [1000000.0, 800000.0]),
        _row("其他货币资金", [None, None]),
        _row("合计", [1000376.73, 800286.73], total=True),
    ],
}
ANHUI_RESTRICTED = {"name": "受限制的货币资金明细", "headers": ["项目", "期末余额", "期初余额"], "rows": [
    _row("银行承兑汇票保证金", [5000.0, None]),
]}


def _read(td: dict, section_id: str, template_type: str = "soe"):
    entry = resolve_mapping_entry(template_type, section_id) or {}
    return read_source_table(
        td,
        consol_table=find_table(template_type, section_id),
        table_name=entry.get("standalone_table_name"),
        title=entry.get("consol_title"),
    )


class TestPickTable:
    def test_by_mapped_name(self):
        assert pick_standalone_table([ANHUI_CASH, ANHUI_RESTRICTED], table_name="受限制的货币资金明细") == (1, None)

    def test_enumerator_prefix_ignored(self):
        tables = [{"name": "（1）按账龄披露应收账款"}, {"name": "（2）按坏账准备计提方法分类披露应收账款"}]
        assert pick_standalone_table(tables, table_name="按账龄披露应收账款") == (0, None)

    def test_no_name_single_table(self):
        assert pick_standalone_table([ANHUI_CASH], table_name=None, title="不相干") == (0, None)

    def test_named_but_absent_is_not_guessed(self):
        """映射给了表名、单体只有另一张表：不拿错表凑数。"""
        idx, why = pick_standalone_table([ANHUI_CASH], table_name="受限制的货币资金明细")
        assert idx is None and "受限制的货币资金明细" in why

    def test_many_tables_without_evidence(self):
        idx, why = pick_standalone_table([ANHUI_CASH, ANHUI_RESTRICTED], table_name=None, title="合同资产情况")
        assert idx is None and "2 张表" in why


class TestReadSourceTable:
    def test_anhui_tables_shape(self):
        st = _read({"_tables": [ANHUI_CASH, ANHUI_RESTRICTED]}, "五-1-1")
        assert st.table_name == "货币资金"
        assert st.unmatched_columns == [] and st.ratio_columns == []
        assert st.rows[0] == {"label": "库存现金", "row_type": "data", "values": [376.73, 286.73]}
        assert st.rows[2]["values"] == [None, None]
        assert st.rows[3]["row_type"] == "total"

    def test_second_table_of_same_section(self):
        """五-1-2 与 五-1-1 同属单体「八、1」，按子表名取第二张表。"""
        st = _read({"_tables": [ANHUI_CASH, ANHUI_RESTRICTED]}, "五-1-2")
        assert st.table_name == "受限制的货币资金明细"
        assert st.rows == [{"label": "银行承兑汇票保证金", "row_type": "data", "values": [5000.0, None]}]

    def test_workpaper_source_is_read_through_projection(self):
        """宜宾形态：workpaper 来源读 sub_table_data 投影（编辑器显示的就是它），不读模板 _tables。"""
        td = {
            "_source": "workpaper",
            "_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                         "rows": [{"label": "库存现金", "values": [999.0, 999.0]}]}],
            "_sub_table_columns": {"货币资金": [
                {"key": "label", "flat": True, "label": "项目", "is_label": True},
                {"key": "end_amount", "label": "期末余额", "format": "amount"},
                {"key": "prior_amount", "label": "期初余额", "format": "amount"},
            ]},
            "sub_table_data": {"货币资金": [
                {"label": "现金", "end_amount": 0, "prior_amount": 0},
                {"label": "银行存款", "end_amount": 110.3, "prior_amount": 148151.74},
                {"label": "合计", "is_total": True, "end_amount": 110.3, "prior_amount": 148151.74},
            ]},
        }
        st = _read(td, "五-1-1")
        assert [r["label"] for r in st.rows] == ["现金", "银行存款", "合计"]
        assert st.rows[1]["values"] == [110.3, 148151.74]

    def test_receivable_end_table_plus_continuation_and_ratio_skipped(self):
        """五-5-2 合并一张 11 列表 ↔ 单体期末表 +「（续：期初数）」续表；比例 / 损失率列不加总。"""
        headers = ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"]
        groups = [{"group": "账面金额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 2}]
        end = {"name": "（2）按坏账准备计提方法分类披露应收账款", "headers": headers, "_column_groups": groups, "rows": [
            {"label": "按单项计提坏账准备", "values": [100, 10, 5, 5, 95], "row_type": "data"},
            {"label": "按组合计提坏账准备", "values": [900, 90, 45, 5, 855], "row_type": "data"},
            {"label": "合  计", "values": [1000, 100, 50, 5, 950], "is_total": True, "row_type": "total"},
        ]}
        prior = {"name": "（2）按坏账准备计提方法分类披露应收账款（续：期初数）", "headers": headers,
                 "_column_groups": groups, "rows": [
            {"label": "按组合计提坏账准备", "values": [720, 90, 36, 5, 684], "row_type": "data"},
            {"label": "按单项计提坏账准备", "values": [80, 10, 4, 5, 76], "row_type": "data"},
        ]}
        st = _read({"_tables": [{"name": "（1）按账龄披露应收账款", "headers": ["账龄", "期末数", "期初数"], "rows": []},
                                end, prior]}, "五-5-2")
        assert st.table_name == end["name"]
        assert st.unmatched_columns == []
        assert len(st.ratio_columns) == 4
        # 期末：金额 / 坏账准备 / 账面价值；期初来自续表（按行名对行，不按位置）
        assert st.rows[0]["values"] == [100, None, 5, None, 95, 80, None, 4, None, 76]
        assert st.rows[1]["values"] == [900, None, 45, None, 855, 720, None, 36, None, 684]
        assert st.rows[2]["row_type"] == "total"

    def test_duplicate_standalone_headers_without_groups_stay_blank(self):
        """单体表两列都叫「账面余额」又没有分组：分不清期末 / 期初就不填，并回报列名。"""
        td = {"_tables": [{"name": "应收票据分类", "headers": ["票据种类", "账面余额", "坏账准备", "账面价值",
                                                            "账面余额", "坏账准备", "账面价值"],
                           "rows": [{"label": "银行承兑票据", "values": [1, 2, 3, 4, 5, 6]}]}]}
        st = _read(td, "五-4-1")
        assert st.rows[0]["values"] == [None] * 6
        assert "期末数/账面余额" in st.unmatched_columns

    def test_placeholder_rows_and_text_values(self):
        td = {"_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": [
            {"label": "库存现金", "values": ["1,234.50", "X.XX"]},
            {"label": "……", "values": [None, None], "row_type": "expandable"},
            {"label": "", "values": [1, 2]},
        ]}]}
        st = _read(td, "五-1-1")
        assert st.rows == [{"label": "库存现金", "row_type": "data", "values": [1234.5, None]}]

    def test_prior_continuation_chosen_by_headers(self):
        """国企 五-4-3（期初数续表）：映射子表名精确命中的「（续）」是单项计提表，按表头读「（续：期初数）」。"""
        groups = [{"group": "账面余额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 2}]
        headers = ["类别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"]
        tables = [
            {"name": "按坏账准备计提方法分类披露应收票据（期末数）", "headers": headers, "_column_groups": groups,
             "rows": [{"label": "按组合计提坏账准备", "values": [900, 90, 45, 5, 855]}]},
            {"name": "按坏账准备计提方法分类披露应收票据（续：期初数）", "headers": headers, "_column_groups": groups,
             "rows": [{"label": "按组合计提坏账准备", "values": [700, 70, 35, 5, 665]}]},
            {"name": "按坏账准备计提方法分类披露应收票据（续）", "headers": ["名称", "账面余额", "坏账准备", "预期信用损失率(%)", "计提理由"],
             "rows": [{"label": "甲公司", "values": [10, 1, 10, "无法收回"]}]},
        ]
        st = read_source_table(
            {"_tables": tables}, consol_table=find_table("soe", "五-4-3"),
            table_name="按坏账准备计提方法分类披露应收票据（续）",
        )
        assert st.table_name == "按坏账准备计提方法分类披露应收票据（续：期初数）"
        assert st.table_choice == "structure"
        assert st.rows == [{"label": "按组合计提坏账准备", "row_type": "data", "values": [700, None, 35, None, 665]}]
        assert st.to_status()["table_choice"] == "structure"

    def test_row_continuation_rows_are_appended(self):
        """行续表（同样的列补行）：行追加在主表后，列按续表自己的表头对应。"""
        tables = [
            {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [{"label": "库存现金", "values": [1, 2]}, {"label": "银行存款", "values": [3, 4]}]},
            {"name": "货币资金（续）", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [{"label": "其他货币资金", "values": [5, 6]}]},
        ]
        st = _read({"_tables": tables}, "五-1-1")
        assert [r["label"] for r in st.rows] == ["库存现金", "银行存款", "其他货币资金"]
        assert st.rows[2]["values"] == [5, 6]

    def test_legacy_headerless_table_uses_cell_semantics(self):
        """真库旧单表格式（宜宾临港店）：headers 为空，按行 _cell_meta 语义补表头后认列（与附注编辑器同口径）。"""
        def row(label, end, prior):
            return {"label": label, "values": [end, prior], "_cell_meta": {
                "0": {"semantic": "closing_balance"}, "1": {"semantic": "opening_balance"}}}
        td = {"headers": [], "rows": [row("库存现金", 10, 8), row("银行存款", 100, 90)]}
        st = read_source_table(td, consol_table=find_table("soe", "五-1-1"), table_name="货币资金",
                               section_title="货币资金")
        assert st.rows[0]["values"] == [10, 8] and st.rows[1]["values"] == [100, 90]

    def test_continuing_involvement_table_is_not_joined(self):
        """「继续涉入」表名含「续」但不是续表，不能被当成主表的续表并进来。"""
        tables = [
            {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": [{"label": "库存现金", "values": [1, 2]}]},
            {"name": "货币资金转移继续涉入形成的资产", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [{"label": "其他", "values": [9, 9]}]},
        ]
        st = _read({"_tables": tables}, "五-1-1")
        assert [r["label"] for r in st.rows] == ["库存现金"]

    @pytest.mark.parametrize("td", [None, {}, {"_tables": []}])
    def test_empty_inputs_have_reason(self, td):
        st = read_source_table(td, consol_table=find_table("soe", "五-1-1"), table_name="货币资金")
        assert st.rows == [] and st.reason
