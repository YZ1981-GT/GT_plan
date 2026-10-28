"""附注公式逐表目标 / 按表结构生成的预设 / 严格求值（spec note-pull-header-formula-closure R3）。纯函数，不连库。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import note_formula_tables as nft


def _row(label, values=None, **kw):
    return {"label": label, "values": values if values is not None else [None, None], **kw}


def _total(label="合计", values=None, row_type="total", **kw):
    return _row(label, values, is_total=True, row_type=row_type, **kw)


# 国企 八、5「（2）按坏账准备计提方法分类披露应收账款」同形：两级表头、比例 / 损失率列、「其中：」标记行
BAD_DEBT = {
    "name": "（2）按坏账准备计提方法分类披露应收账款",
    "headers": ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"],
    "_column_groups": [{"group": "账面余额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 2}],
    "rows": [
        _row("按单项计提坏账准备", [100.0, 10.0, 20.0, 20.0, None]),
        _row("按组合计提坏账准备", [900.0, 90.0, 45.0, 5.0, None]),
        _row("其中：", [None] * 5),
        _row("应收中央企业客户", [600.0, 60.0, 30.0, 5.0, None]),
        _row("应收海外企业客户", [300.0, 30.0, 15.0, 5.0, None]),
        _total("合 计", [None] * 5),
    ],
}


class TestKeys:
    def test_first_table_keeps_legacy_form(self):
        assert nft.formula_key(0, 3, 1) == "3:1" and nft.formula_key(2, 3, 1) == "t2:3:1"
        assert nft.parse_formula_key("3:1") == (0, 3, 1)
        assert nft.parse_formula_key("t2:3:1") == (2, 3, 1)
        assert nft.parse_formula_key(" t0 : 3 : 1 ") == (0, 3, 1)

    @pytest.mark.parametrize("bad", ["", "R1", "3", "a:b", "t:1:2", "1:2:3", None])
    def test_non_cell_target(self, bad):
        assert nft.parse_formula_key(bad) is None

    def test_iter_tables_prefers_tables_list(self):
        td = {"rows": [_row("x")], "_tables": [{"rows": []}, "坏", {"rows": [_row("y")]}]}
        assert [i for i, _t in nft.iter_note_tables(td)] == [0, 2]
        assert nft.iter_note_tables({"rows": []}) == [(0, {"rows": []})]
        assert nft.iter_note_tables(None) == []


class TestTotalTerms:
    def test_simple_table_sums_every_detail_row(self):
        rows = [_row("库存现金"), _row("银行存款"), {"label": "……", "row_type": "expandable"}, _total(),
                _row("其中：存放在境外的款项总额")]
        plans, reasons = nft.total_terms(rows)
        assert plans == {3: [(0, 1), (1, 1)]} and reasons == {}

    def test_marker_rows_list_details_of_the_row_above(self):
        plans, reasons = nft.total_terms(BAD_DEBT["rows"])
        assert plans == {5: [(0, 1), (1, 1)]}, "「其中：」下面是按组合计提的明细，不重复加"
        assert reasons == {}

    def test_each_marker_belongs_to_its_previous_row(self):
        # 上市「按坏账计提方法分类披露」：两个分类各带一个「其中：」和空白明细行
        rows = [_row("按单项计提坏账准备"), _row("其中："), _row(""), _row(""), _row("按组合计提坏账准备"),
                _row("其中："), _row("应收中央企业客户"), _row("应收海外企业客户"), _total()]
        assert nft.total_terms(rows) == ({8: [(0, 1), (4, 1)]}, {})

    def test_subtotal_less_deduction(self):
        rows = [_row("1年以内"), _row("1至2年"), _total("小计", row_type="subtotal"), _row("减：坏账准备"), _total()]
        plans, _ = nft.total_terms(rows)
        assert plans == {2: [(0, 1), (1, 1)], 4: [(2, 1), (3, -1)]}

    def test_segments_each_subtotal_then_total_of_subtotals(self):
        # 国企 八、18「对合营企业或联营企业发生超额亏损的分担额」：每段小计加本段，合计 = 各小计
        sub = {"row_type": "subtotal"}
        rows = [_row("合营企业"), _row(""), _total("小计", **sub), _row("联营企业"), _row(""), _total("小计", **sub),
                _total("合  计")]
        assert nft.total_terms(rows) == ({2: [(0, 1), (1, 1)], 5: [(3, 1), (4, 1)], 6: [(2, 1), (5, 1)]}, {})

    def test_segment_titles_open_each_segment(self):
        # 递延所得税资产 / 负债：分段标题是每段第一行，两段各自小计、没有合计
        sub = {"row_type": "subtotal"}
        rows = [_row("一、递延所得税资产"), _row("资产减值准备"), _total("小计", **sub),
                _row("二、递延所得税负债"), _row("使用权资产"), _total("小计", **sub)]
        assert nft.total_terms(rows) == ({2: [(0, 1), (1, 1)], 5: [(3, 1), (4, 1)]}, {})

    def test_title_style_subtotals_sum_rows_below(self):
        # 国企 八、4「按组合计提坏账准备的应收票据」：小计在本组之上
        sub = {"row_type": "subtotal"}
        rows = [_total("商业承兑汇票小计：", **sub), _row(""), _total("银行承兑汇票小计：", **sub), _row(""), _total()]
        assert nft.total_terms(rows) == ({0: [(1, 1)], 2: [(3, 1)], 4: [(0, 1), (2, 1)]}, {})

    def test_total_of_subtotals_even_when_a_subtotal_is_ambiguous(self):
        # 持有待售资产：（一）组内有「其中：X」⇒ 小计判不准，合计 = （一）+（二）仍判得准
        sub = {"row_type": "subtotal"}
        rows = [_total("（一）持有待售非流动资产", **sub), _row("其中：固定资产"), _row("无形资产"),
                _total("（二）持有待售处置组中的资产", **sub), _row(""), _total()]
        plans, reasons = nft.total_terms(rows)
        assert plans == {3: [(4, 1)], 5: [(0, 1), (3, 1)]} and set(reasons) == {0}

    def test_continued_table_total_is_subtotal_less_deduction(self):
        # 应付债券（续）：明细在主表，本表只有「小计 / 减：一年内到期 / 合计」
        rows = [_total("小计", row_type="subtotal"), _row("减：一年内到期的应付债券"), _total()]
        plans, reasons = nft.total_terms(rows)
        assert plans == {2: [(0, 1), (1, -1)]} and set(reasons) == {0}

    def test_items_after_last_subtotal_join_the_total(self):
        rows = [_row("甲"), _row("乙"), _total("小计", row_type="subtotal"), _row("丙"), _total()]
        assert nft.total_terms(rows) == ({2: [(0, 1), (1, 1)], 4: [(2, 1), (3, 1)]}, {})

    @pytest.mark.parametrize("rows, why", [
        ([_row("分类为以公允价值计量的金融资产"), _row("其中：债务工具投资"), _row("权益工具投资"),
          _row("指定为以公允价值计量的金融资产"), _total()], "其中"),
        # 上市「按账龄披露」：「1年以内小计」嵌在「小计」里
        ([_row("1年以内"), _row("其中：0-X个月"), _total("1年以内小计：", row_type="subtotal"), _row("1至2年"),
          _total("小  计", row_type="subtotal"), _row("减：坏账准备"), _total()], "嵌套"),
        ([_row("a"), _total(), _row("b"), _total()], "多个合计"),
        # 第一行就是合计、上方没有明细（分段标题式的「（一）…」段首合计按本段明细算，见 test_note_total_terms 段首合计）
        ([_total("合计"), _row("固定资产")], "没有可合计"),
        ([_row("减：坏账准备"), _total()], "减项"),
        # 国企 八、87 融资租赁出租人：「…收款额小计」在「三、」下，上方还有「一、」「二、」两段
        ([_row("一、收入情况"), _row("销售损益"), _row("二、未折现租赁收款额"), _row("第1年"), _row("三、调节"),
          _total("剩余年度将收到的未折现租赁收款额小计", row_type="subtotal"), _row("减：未实现融资收益")],
         "分段标题"),
        ([_row("一、甲类"), _row("a"), _row("二、乙类"), _row("b"), _total("小计", row_type="subtotal"),
          _row("c"), _total("小计", row_type="subtotal"), _total()], "分段标题"),
    ])
    def test_ambiguous_tables_get_a_reason_not_a_formula(self, rows, why):
        plans, reasons = nft.total_terms(rows)
        assert plans == {} and reasons and all(why in r for r in reasons.values()), (plans, reasons)

    def test_sub_row_between_last_subtotal_and_total(self):
        rows = [_row("甲"), _total("小计", row_type="subtotal"), _row("其中：乙"), _total()]
        plans, reasons = nft.total_terms(rows)
        assert plans == {1: [(0, 1)]} and list(reasons) == [3] and "其中" in reasons[3]


class TestColumns:
    def test_ratio_columns_are_not_summed(self):
        assert nft.amount_columns(BAD_DEBT) == [0, 2, 4]

    def test_book_value_from_column_groups(self):
        assert nft.book_value_columns(BAD_DEBT) == [(4, 0, (2,))]

    def test_book_value_per_period(self):
        table = {"headers": ["项目", "账面余额", "减值准备", "账面价值", "账面余额", "减值准备", "账面价值"],
                 "_column_groups": [{"group": "期末余额", "start": 1, "span": 3},
                                    {"group": "期初余额", "start": 4, "span": 3}], "rows": []}
        assert sorted(nft.book_value_columns(table)) == [(2, 0, (1,)), (5, 3, (4,))]

    def test_book_value_needs_one_gross_column(self):
        table = {"headers": ["项目", "账面价值", "公允价值"], "rows": []}
        assert nft.book_value_columns(table) == []


class TestPresets:
    def test_bad_debt_table_presets(self):
        formulas, notes = nft.table_preset_formulas(BAD_DEBT, 1)
        assert notes == []
        # 合计行：只合计金额列，按分类两行（其中明细不重复加）
        assert formulas["t1:5:0"]["expression"] == "SUM(0:1, 0)"
        assert formulas["t1:5:2"]["expression"] == "SUM(0:1, 2)"
        assert formulas["t1:5:4"]["type"] == "vertical_sum", "合计行的账面价值按明细之和，不另算"
        assert "t1:5:1" not in formulas and "t1:5:3" not in formulas, "比例 / 损失率不加总"
        # 账面价值 = 账面余额 − 坏账准备（明细行、其中明细行都算；「其中：」标记行不算）
        assert formulas["t1:0:4"]["expression"] == "cell(0,0) - cell(0,2)"
        assert formulas["t1:3:4"]["expression"] == "cell(3,0) - cell(3,2)"
        assert "t1:2:4" not in formulas
        assert all(f["table_index"] == 1 and f["category"] == "auto_calc" for f in formulas.values())

    def test_section_presets_cover_every_table(self):
        td = {"rows": [], "_tables": [
            {"name": "按账龄", "headers": ["账龄", "期末数", "期初数"], "rows": [_row("1年以内"), _row("1至2年"), _total()]},
            BAD_DEBT,
        ]}
        formulas, notes = nft.section_preset_formulas(td)
        assert {"2:0", "2:1", "t1:5:0", "t1:0:4"} <= set(formulas)
        assert formulas["2:0"]["table_index"] == 0 and notes == []

    def test_reasons_reported_for_ambiguous_tables(self):
        td = {"_tables": [{"name": "交易性金融资产", "headers": ["项目", "期末", "期初"], "rows": [
            _row("分类为以公允价值计量的金融资产"), _row("其中：债务工具投资"), _row("其他"), _total()]}]}
        formulas, notes = nft.section_preset_formulas(td)
        assert formulas == {} and notes[0]["row"] == 3 and "其中" in notes[0]["reason"]


class TestEvaluate:
    ROWS = [_row("a", [100.0, None]), _row("b", ["1,234.50", None]), _row("c", [None, None]), _total()]

    def test_sum_and_cells(self):
        assert nft.evaluate("SUM(0:2, 0)", self.ROWS) == (Decimal("1334.50"), None)
        assert nft.evaluate("cell(0,0) - cell(1,0) * 2", self.ROWS)[0] == Decimal("-2369.00")
        assert nft.evaluate("=(cell(0,0) + 50) / 3", self.ROWS)[0] == Decimal("50")

    def test_all_referenced_cells_empty_is_not_zero(self):
        value, reason = nft.evaluate("SUM(0:2, 1)", self.ROWS)
        assert value is None and reason == "引用的单元格都没有数"

    @pytest.mark.parametrize("expr, why", [
        ("cell(0,0) / cell(2,1)", "除数为 0"),
        ("ROUND(cell(0,0), 2)", "写法无法识别"),
        ("cell(0,0) %", "写法无法识别"),
        ("", "公式为空"),
    ])
    def test_strict_failures(self, expr, why):
        value, reason = nft.evaluate(expr, self.ROWS)
        assert value is None and why in reason

    def test_cross_refs_via_resolver(self):
        refs = {"TB('1001','期末')": 30.0}
        assert nft.evaluate("TB('1001','期末') + cell(0,0)", self.ROWS, refs.get) == (Decimal("130.0"), None)
        value, reason = nft.evaluate("TB('9999','期末')", self.ROWS, refs.get)
        assert value is None and reason == "取不到 TB('9999','期末')"
        # 跨表取到数、表内格为空：照算（空格按 0）
        assert nft.evaluate("TB('1001','期末') + cell(2,0)", self.ROWS, refs.get)[0] == Decimal("30.0")

    def test_order_and_cycles(self):
        order, cyclic = nft.table_order({(3, 0): "SUM(0:2, 0)", (2, 0): "cell(0,0) + cell(1,0)", (5, 0): "cell(6,0)",
                                          (6, 0): "cell(5,0)"})
        assert order.index((2, 0)) < order.index((3, 0))
        assert cyclic == [(5, 0), (6, 0)]


class TestTargets:
    TD = {"_tables": [{"name": "按账龄", "headers": ["账龄", "期末数", "期初数"],
                       "rows": [_row("1年以内"), _row("1至2年"), _total()]}, BAD_DEBT]}

    def test_catalog_and_readable_target(self):
        catalog = nft.formula_targets(self.TD)
        assert [t["name"] for t in catalog] == ["按账龄", BAD_DEBT["name"]]
        assert catalog[1]["columns"][0] == "账面余额/金额" and catalog[1]["rows"][5] == "合 计"
        assert nft.describe_target(self.TD, "t1:5:4") == f"{BAD_DEBT['name']} · 合 计 · 账面价值"
        assert nft.describe_target(self.TD, "2:1") == "按账龄 · 合计 · 期初数"
        assert nft.describe_target(self.TD, "t9:0:0") == "t9:0:0"

    def test_target_issues(self):
        issues = nft.target_issues(self.TD, [
            {"target": "", "formula": "SUM(0:1, 0)"},
            {"target": "R1", "formula": "1"},
            {"target": "t3:0:0", "formula": "1"},
            {"target": "t1:9:0", "formula": "1"},
            {"target": "2:0", "formula": "SUM(0:1, 0)"},
            {"target": "", "formula": "  "},
        ])
        assert [i["target"] for i in issues] == ["第 1 条", "R1", "t3:0:0", "t1:9:0"]
        assert "没有选择目标" in issues[0]["message"] and "不是单元格" in issues[1]["message"]
        assert "第 4 张表" in issues[2]["message"] and "6 行 × 5 列" in issues[3]["message"]
