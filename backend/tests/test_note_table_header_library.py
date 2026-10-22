"""标题行库识别口径测试（note_table_header_library / note_table_header_match）。

样本：合并表一律用真模板（find_table）；单体表取真种子 note_template_soe.json 的「八、4 应收票据」
（真库同一章节并存三种表组合：无期间主表 + 续期初 + 续 / 期末数 + 续期初 / 两种都有）。
"""
from __future__ import annotations

import copy
import json

import pytest

from app.services import note_table_header_library as L
from app.services import note_table_header_match as M
from app.services.consol_note_formula_service import find_table
from app.services.note_section_catalog import section_applies_to_scope, template_json_path


def _keys(table, **kw):
    return [k.key for k in L.column_keys(table, **kw)]


def _soe_section(code: str) -> list[dict]:
    seed = json.loads(template_json_path("soe").read_text(encoding="utf-8"))
    sec = next(s for s in seed["sections"] if s["section_number"] == code and section_applies_to_scope(s, "standalone"))
    return copy.deepcopy(sec["tables"])


class TestContinuationName:
    @pytest.mark.parametrize("name", [
        "续：", "续（1）：", "续表", "（续）", "按坏账准备计提方法分类披露应收票据（续：期初数）",
        "重要在建工程项目变动情况（续）：", "附表（续表）", "续：重要合营企业本期及上期经营成果",
    ])
    def test_markers(self, name):
        assert L.is_continuation_name(name)

    @pytest.mark.parametrize("name", [
        "期末发行在外的优先股、永续债等金融工具情况", "其他应收款项转移继续涉入形成的资产、负债的金额",
        "手续费及佣金收入", "整个存续期预期信用损失", "计入递延收益的政府补助，后续采用总额法计量",
        "②资产负债表日后连续五个会计年度每年将收到的未折现租赁收款额", "持续经营", "",
    ])
    def test_words_containing_xu_are_not_continuations(self, name):
        assert not L.is_continuation_name(name)


class TestNamePeriodAndSegments:
    @pytest.mark.parametrize("name,period", [
        ("按坏账准备计提方法分类披露应收票据（期末数）", "end"),
        ("按坏账准备计提方法分类披露应收票据（续：期初数）", "prior"),
        ("按坏账计提方法分类（续：上年年末余额）", "prior"),
        ("所有权或使用权受到限制的资产（续：上年年末）", "prior"),
        ("开发支出（续：资本化情况）", None),
        ("其他应收款（表2）", None),
        ("按坏账准备计提方法分类披露应收票据（续）", None),
        ("期末重要的债权投资", None),
    ])
    def test_name_period(self, name, period):
        assert L.name_period(name) == period

    @pytest.mark.parametrize("seg,expected", [
        ("期末余额", ("end", None)), ("期 末 数", ("end", None)), ("本期发生额", ("cur", None)),
        ("上年年末余额", ("prior", None)), ("期初余额(1)", ("prior", None)), ("上期金额", ("prev", None)),
        ("期末公允价值", ("end", "公允价值")), ("期末账面价值", ("end", "账面价值")),
        ("减值准备期末余额", ("end", "减值准备")), ("期末余额（账面价值）", ("end", "账面价值")),
        ("本期增加", ("cur", "增加")), ("期末余额/本期发生额", ("end", None)),
        ("上年年末余额/上期发生额", ("prior", None)), ("利得/损失", (None, "利得/损失")),
        ("账面余额", (None, "账面余额")),
    ])
    def test_parse_segment(self, seg, expected):
        assert L.parse_segment(seg) == expected


class TestColumnPaths:
    def test_consol_paths_use_display_header_rows(self):
        """五-4-2 三层表头：「账面价值」最底层纵向合并，不继承左侧「预期信用损失率」（展示同口径）。"""
        paths = L.column_paths(find_table("soe", "五-4-2"))
        assert paths[1] == ("期末数", "账面余额", "金额")
        assert paths[4] == ("期末数", "坏账准备", "预期信用损失率(%)")
        assert paths[5] == ("期末数", "账面价值")

    def test_flat_header_slash_is_not_split(self):
        assert L.column_paths({"headers": ["项目", "利得/损失"]})[1] == ("利得/损失",)

    def test_projector_tree_groups(self):
        table = {
            "headers": ["项目", "金额", "比例", "金额", "账面价值"],
            "_column_groups": [{"group": "期末余额", "children": [
                {"group": "账面余额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 1},
                {"headerIdx": 4},
            ]}],
        }
        assert L.column_paths(table)[1:] == [
            ("期末余额", "账面余额", "金额"), ("期末余额", "账面余额", "比例"),
            ("期末余额", "坏账准备", "金额"), ("期末余额", "账面价值"),
        ]

    def test_columns_group_slash_levels_and_explicit_flat(self):
        cols = [{"label": "项目", "is_label": True}, {"label": "金额", "group": "期末余额/账面余额"}]
        assert L.column_paths({"headers": ["项目", "金额"], "columns": cols})[1] == ("期末余额", "账面余额", "金额")
        assert L.column_paths({"headers": ["项目", "金额"], "columns": cols, "_column_groups": []})[1] == ("金额",)


class TestColumnKeys:
    def test_multi_header_beats_misaligned_headers(self):
        """五-4-1 的 headers 与 multi_header 错位，键以多级表头为准。"""
        keys = _keys(find_table("soe", "五-4-1"))
        assert keys[1] == "end|账面余额" and keys[3] == "end|账面价值" and keys[4] == "prior|账面余额"

    def test_ratio_and_label_kinds(self):
        keys = L.column_keys(find_table("soe", "五-4-2"))
        assert keys[0].kind == "label"
        assert [k.kind for k in keys[1:]] == ["amount", "ratio", "amount", "ratio", "amount"]

    def test_period_words_split_balance_and_flow(self):
        assert _keys({"headers": ["项目", "期末数", "上年年末余额", "本期发生额", "上期金额"]})[1:] == [
            "end|", "prior|", "cur|", "prev|",
        ]

    def test_period_prefix_does_not_collide(self):
        """旧词表把「期末账面价值 / 期末公允价值」都只认成期末，同表两列撞键。"""
        assert _keys({"headers": ["项目", "期末账面价值", "期末公允价值"]})[1:] == ["end|账面价值", "end|公允价值"]

    def test_name_period_fills_missing_period(self):
        table = {"name": "按坏账准备计提方法分类披露应收票据（续：期初数）", "headers": ["类别", "金额", "账面价值"],
                 "_column_groups": [{"group": "账面余额", "start": 1, "span": 1}]}
        assert _keys(table)[1:] == ["prior|账面余额", "prior|账面价值"]

    def test_measure_alias_and_filler_words(self):
        """「账面金额」与「账面余额」同义；「金额 / 余额」只是计量的填充词（账面余额/金额 ≡ 账面余额）。"""
        table = {"headers": ["类别", "金额"], "_column_groups": [{"group": "账面金额", "start": 1, "span": 1}]}
        assert _keys(table)[1] == "-|账面余额"
        assert _keys({"headers": ["项目", "期末余额", "余额"]})[1:] == ["end|", "-|"]

    def test_text_columns_are_not_amounts(self):
        keys = L.column_keys({"headers": ["债务人名称", "核销金额", "核销原因", "是否因关联交易产生", "债券期限", "到期日"]})
        assert [k.kind for k in keys[1:]] == ["amount", "text", "text", "text", "text"]

    def test_seed_hyphen_levels(self):
        """单体种子把三级表头压成「中级-叶」：按连字符拆层；带数字 / 公式的不拆。"""
        table = {"headers": ["类别", "账面余额-金额", "坏账准备-金额", "期末余额(4)=(1)+(2)-(3)"],
                 "_column_groups": [{"group": "期末余额", "start": 1, "span": 2}]}
        assert _keys(table)[1:] == ["end|账面余额", "end|坏账准备", "end|"]


class TestContinuationLinks:
    def test_period_split_is_column_continuation(self):
        tables = _soe_section("八、4")
        links = L.continuation_links([tables[0], tables[1], tables[3]])
        assert set(links) == {2}
        assert (links[2].of, links[2].kind, links[2].via) == (1, "columns", "base")

    def test_bare_markers_chain_to_previous_non_continuation(self):
        tables = [
            {"name": "重要非全资子公司主要财务信息—期末数", "headers": ["项目", "A公司"], "rows": [["流动资产"]]},
            {"name": "续（1）", "headers": ["项目", "A公司"], "rows": [["流动资产"]]},
            {"name": "续（2）", "headers": ["项目", "A公司"], "rows": [["流动资产"]]},
        ]
        links = L.continuation_links(tables)
        assert [(i, lk.of, lk.via) for i, lk in sorted(links.items())] == [(1, 0, "previous"), (2, 0, "previous")]

    def test_disjoint_rows_are_row_continuation(self):
        tables = [
            {"name": "重要合营企业主要财务信息", "headers": ["项目", "A公司"], "rows": [["流动资产"], ["非流动资产"]]},
            {"name": "续：重要合营企业本期及上期经营成果", "headers": ["项目", "A公司"], "rows": [["营业收入"], ["净利润"]]},
        ]
        assert L.continuation_links(tables)[1].kind == "rows"

    def test_continuation_follows_adjacent_table(self):
        """「续」接紧挨着的上一张表：上市「应付债券（续）」续的是增减变动表，不是同基名的汇总表。"""
        tables = [
            {"name": "应付债券", "headers": ["项目", "期末余额", "上年年末余额"], "rows": [["合计"]]},
            {"name": "应付债券的增减变动", "headers": ["债券名称", "面值", "发行金额"], "rows": [["小计"]]},
            {"name": "应付债券（续）", "headers": ["债券名称", "期初余额", "期末余额"], "rows": [["小计"]]},
        ]
        assert L.continuation_links(tables)[2].of == 1

    def test_same_base_wins_when_rows_agree(self):
        tables = [
            {"name": "按单项计提（期末余额）", "headers": ["名称", "账面余额"], "rows": [["甲公司"], ["乙公司"]]},
            {"name": "按组合计提", "headers": ["组合", "账面余额"], "rows": [["组合1"]]},
            {"name": "按单项计提（续：上年年末余额）", "headers": ["名称", "账面余额"], "rows": [["甲公司"], ["乙公司"]]},
        ]
        link = L.continuation_links(tables)[2]
        assert (link.of, link.via) == (0, "base")

    def test_continuing_involvement_is_not_linked(self):
        tables = _soe_section("八、9")
        names = [t.get("name") for t in tables]
        links = L.continuation_links(tables)
        idx = names.index("其他应收款项转移继续涉入形成的资产、负债的金额")
        assert idx not in links


class TestMatchColumns:
    def _k(self, idx, period, *measure, kind="amount"):
        return L.ColumnKey(idx, tuple(measure), period, tuple(measure), kind)

    def test_rules_in_order_and_ambiguity(self):
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, "end", "账面余额", "金额"), self._k(2, "cur"), self._k(3, "end", "比例", kind="ratio")]
        source = [label, self._k(1, "end", "金额"), self._k(2, "end"), self._k(3, "prior")]
        m = M.match_columns(target, [source])
        assert m.col_map == {1: (0, 1), 2: (0, 2)}
        assert m.rules == {1: "suffix", 2: "period_family"} and m.ratio == [3]

    def test_reverse_and_period_only_rules(self):
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, None, "第一阶段"), self._k(2, "end"), self._k(3, "prior", "公允价值")]
        source = [label, self._k(1, None, "第一阶段", "未来12个月预期信用损失"),
                  self._k(2, "end", "公允价值"), self._k(3, "prior")]
        m = M.match_columns(target, [source])
        assert m.col_map == {1: (0, 1), 2: (0, 2), 3: (0, 3)}
        assert m.rules == {1: "reverse_prefix", 2: "period_only", 3: "period_only"}

    def test_period_only_needs_a_single_candidate(self):
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, "end")]
        source = [label, self._k(1, "end", "账面价值"), self._k(2, "end", "公允价值")]
        assert M.match_columns(target, [source]).col_map == {}

    def test_ambiguous_hits_and_double_claims_are_dropped(self):
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, "end"), self._k(2, "prior", "账面余额", "金额"), self._k(3, "prior", "坏账准备", "金额")]
        source = [label, self._k(1, "end"), self._k(2, "end"), self._k(3, "prior", "金额")]
        m = M.match_columns(target, [source])
        assert m.col_map == {} and m.unmatched == [1, 2, 3]

    def test_pure_period_column_is_the_unique_balance_column(self):
        """单体「期末数」（纯期间 = 余额）↔ 合并「期末数/账面余额 | 期末数/坏账准备」：对唯一的余额列（两个方向）。"""
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, "end", "账面余额"), self._k(2, "end", "坏账准备"),
                  self._k(3, "prior", "账面余额"), self._k(4, "prior", "坏账准备")]
        source = [label, self._k(1, "end"), self._k(2, "prior")]
        m = M.match_columns(target, [source])
        assert m.col_map == {1: (0, 1), 3: (0, 2)} and m.rules == {1: "period_balance", 3: "period_balance"}
        assert m.unmatched == [2, 4]
        back = M.match_columns(source, [target])
        assert back.col_map == {1: (0, 1), 2: (0, 3)} and set(back.rules.values()) == {"period_balance"}

    def test_pure_period_column_next_to_a_net_column_is_ambiguous(self):
        """同期间既有账面余额又有账面价值：纯期间列对余额还是净额分不出，不对应（宁缺不错）。"""
        label = L.ColumnKey(0, (), None, (), "label")
        target = [label, self._k(1, "end", "账面余额"), self._k(2, "end", "坏账准备"), self._k(3, "end", "账面价值")]
        source = [label, self._k(1, "end")]
        assert M.match_columns(target, [source]).col_map == {}
        assert M.match_columns(source, [target]).col_map == {}


class TestChooseUnit:
    @pytest.mark.parametrize("combo", ["both", "no_period_primary", "end_primary"])
    def test_real_receivable_note_combos(self, combo):
        t = _soe_section("八、4")
        tables = {
            "both": t,
            "no_period_primary": [t[0], t[2], t[3], t[4], *t[5:]],
            "end_primary": [t[0], t[1], t[3], *t[5:]],
        }[combo]
        names = [x.get("name") for x in tables]
        end = M.choose_unit(tables, target_keys=L.column_keys(find_table("soe", "五-4-2")),
                            table_name="按坏账准备计提方法分类披露应收票据")
        prior = M.choose_unit(tables, target_keys=L.column_keys(find_table("soe", "五-4-3")),
                              table_name="按坏账准备计提方法分类披露应收票据（续）")
        assert names[end.primary] in ("按坏账准备计提方法分类披露应收票据（期末数）", "按坏账准备计提方法分类披露应收票据")
        assert end.match.exact_count == 3
        # 期初数续表：名字精确命中的是单项计提表（列完全不同），按表头选中「（续：期初数）」；
        # 没有「（续）」表的组合靠同类基名直接认到
        assert names[prior.primary] == "按坏账准备计提方法分类披露应收票据（续：期初数）"
        has_plain_cont = "按坏账准备计提方法分类披露应收票据（续）" in names
        assert prior.method == ("structure" if has_plain_cont else "name")
        assert prior.match.exact_count == 3

    def test_generic_columns_never_chosen_by_structure(self):
        tables = [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": []}]
        target = L.column_keys({"headers": ["项目", "期末余额", "期初余额"]})
        ch = M.choose_unit(tables, target_keys=target, table_name="受限制的货币资金明细")
        assert ch.primary is None and "受限制的货币资金明细" in ch.reason

    def test_structure_fallback_when_names_absent(self):
        """首汽式旧数据：表名是表头首格，名字对不上，按具体列选中唯一表。"""
        tables = [
            {"name": "票据种类", "headers": ["票据种类", "账面余额"], "rows": []},
            {"name": "类  别", "headers": ["类别", "金额", "金额", "账面价值"],
             "_column_groups": [{"group": "账面余额", "start": 1, "span": 1}, {"group": "坏账准备", "start": 2, "span": 1}],
             "rows": []},
        ]
        ch = M.choose_unit(tables, target_keys=L.column_keys(find_table("soe", "五-4-2")),
                           table_name="按坏账准备计提方法分类披露应收票据")
        assert (ch.primary, ch.method) == (1, "structure")

    def test_data_breaks_tie_between_old_and_new_template_tables(self):
        """同一章节新旧模板表并存（同基名、同构）：表头分不出时取有数的那张。"""
        tables = [
            {"name": "按坏账计提方法分类", "headers": ["类别", "期末账面余额"], "rows": [["A", None]]},
            {"name": "按坏账计提方法分类（期末余额）", "headers": ["类别", "账面余额"], "rows": [["A", 5]]},
        ]
        target = L.column_keys({"headers": ["类别", "期末账面余额"]})
        ch = M.choose_unit(tables, target_keys=target, table_name="按坏账计提方法分类")
        assert ch.primary == 1

    def test_structure_fallback_refuses_identical_tables(self):
        """没有名字证据、两张表同构：只靠次要特征分不出就不猜（上市 五-9-4 按组合 / 按库龄组合）。"""
        def table(name):
            return {"name": name, "headers": ["组合", "账面余额", "跌价准备"], "rows": []}
        tables = [table("按组合计提存货跌价准备"), table("按库龄组合计提存货跌价准备")]
        target = L.column_keys({"headers": ["组合", "期末账面余额", "期末跌价准备"]})
        assert M.choose_unit(tables, target_keys=target, title="（15号文第十九条（六））").primary is None

    def test_bare_continuation_title_only_considers_continuations(self):
        """合并表标题就是「续：」：不拿列结构碰巧相同的汇总表凑数。"""
        prior = ["类别", "上年年末账面余额", "上年年末坏账准备"]
        tables = [
            {"name": "应收票据", "headers": ["票据种类", "上年年末账面余额", "上年年末坏账准备"], "rows": []},
            {"name": "按坏账计提方法分类（期末余额）", "headers": ["类别", "期末账面余额", "期末坏账准备"], "rows": []},
            {"name": "按坏账计提方法分类（续：上年年末余额）", "headers": prior, "rows": []},
        ]
        ch = M.choose_unit(tables, target_keys=L.column_keys({"headers": prior}), title="续：")
        assert ch.primary == 2

    def test_title_named_table_competes_with_mapping_name(self):
        """映射子表名来自种子（种子把敏感性分析表错叫「计划资产」）：项目附注里名字对的那张也参加比较。"""
        sensitivity = ["项目", "假设的变动幅度", "对设定受益义务现值的影响"]
        tables = [
            {"name": "计划资产", "headers": ["项目", "期末公允价值", "期初公允价值"], "rows": []},
            {"name": "敏感性分析", "headers": sensitivity, "rows": []},
        ]
        ch = M.choose_unit(tables, target_keys=L.column_keys({"headers": sensitivity}),
                           table_name="计划资产", title="敏感性分析")
        assert ch.primary == 1

    def test_bare_continuation_title_does_not_dilute_specific_name(self):
        """旧格式里一堆「续：」表：映射给了具体续表名时，裸「续：」标题不再把它们都拉成候选。"""
        cols = ["项目", "A公司"]
        tables = [
            {"name": "续：重要合营企业本期及上期经营成果", "headers": cols, "rows": []},
            {"name": "续：", "headers": cols, "rows": []},
            {"name": "续：", "headers": cols, "rows": []},
        ]
        ch = M.choose_unit(tables, target_keys=L.column_keys({"headers": ["项目", "(A公司)本期发生额"]}),
                           table_name="续：重要合营企业本期及上期经营成果", title="续：")
        assert ch.primary == 0

    def test_name_only_selection_keeps_old_rules(self):
        cash = {"name": "货币资金", "headers": ["项目", "期末余额"]}
        assert M.choose_unit([cash], table_name=None, title="不相干").primary == 0
        two = M.choose_unit([cash, dict(cash)], table_name="货币资金")
        assert two.primary is None and "多张同名表" in two.reason


class TestOverrides:
    def _vocab(self, **overrides):
        raw = json.loads(L.VOCABULARY_PATH.read_text(encoding="utf-8"))
        raw["overrides"] = {"columns": [], "continuations": [], **overrides}
        return L._build_vocabulary(raw)

    def test_column_override_by_identity(self):
        vocab = self._vocab(columns=[{
            "variant": "soe_consolidated", "table": "五-5-1", "col": 2, "period": "end",
            "measure": ["坏账准备"], "reason": "测试",
        }])
        table = find_table("soe", "五-5-1")
        plain = L.column_keys(table, vocab=vocab)
        over = L.column_keys(table, identity=("soe_consolidated", "五-5-1"), vocab=vocab)
        assert over[2].key == "end|坏账准备" and over[2].source == "override"
        assert plain[2].source == "rule"

    def test_override_without_reason_is_rejected(self):
        with pytest.raises(ValueError, match="reason"):
            self._vocab(columns=[{"variant": "soe_consolidated", "table": "五-5-1", "col": 2, "period": "end"}])

    def test_continuation_overrides(self):
        tables = [
            {"name": "主表", "headers": ["项目", "期末余额"], "rows": [["A"]]},
            {"name": "续：", "headers": ["项目", "期初余额"], "rows": [["A"]]},
            {"name": "补充表", "headers": ["项目", "期初余额"], "rows": [["A"]]},
        ]
        vocab = self._vocab(continuations=[
            {"variant": "soe_standalone", "table": "八、1#续：", "not_continuation": True, "reason": "测试"},
            {"variant": "soe_standalone", "table": "八、1#补充表", "of": "主表", "kind": "columns", "reason": "测试"},
        ])
        links = L.continuation_links(tables, variant="soe_standalone", section="八、1", vocab=vocab)
        assert set(links) == {2} and (links[2].of, links[2].via) == (0, "override")


# ─── 逐列角色 / 变动表勾稽列（spec consol-note-header-library-and-node-reaggregate R5） ───


def _col(*path: str) -> dict:
    """单列表：最后一段是叶表头，前面几段是分组（``columns[].group`` 用「/」分层）。"""
    group = "/".join(path[:-1])
    cols = [{"label": "项目", "is_label": True}, {"label": path[-1], **({"group": group} if group else {})}]
    return {"headers": ["项目", path[-1]], "columns": cols}


def _vocab_with(**fields):
    raw = json.loads(L.VOCABULARY_PATH.read_text(encoding="utf-8"))
    raw.update(fields)
    return L._build_vocabulary(raw)


class TestColumnRoles:
    @pytest.mark.parametrize("period,side", [
        ("end", "current"), ("cur", "current"), ("prior", "previous"), ("prev", "previous"), (None, None),
    ])
    def test_period_side(self, period, side):
        assert L.period_side(period) == side

    def test_flat_change_table(self):
        roles = L.column_roles({"headers": [
            "项目", "期初余额", "本期增加", "本期减少", "本期核销", "期末余额", "比例(%)", "备注", "本期<br/>增加",
        ]})
        # 「核销」= 减少（2026-10-22 用户确认）
        assert roles == ["label", "opening", "increase", "decrease", "decrease", "closing", None, None, "increase"]

    @pytest.mark.parametrize("path,role", [
        (("期末余额",), "closing"), (("本期发生额",), "closing"), (("期末公允价值",), "closing"),
        (("期末数", "账面余额", "金额"), "closing"), (("上年年末余额",), "opening"), (("上期金额",), "opening"),
        (("期初数", "账面余额"), "opening"),
        (("期末数", "坏账准备", "金额"), None), (("期末数", "账面价值"), None), (("期末余额", "已质押金额"), None),
        (("期末数", "账面余额", "比例(%)"), None), (("期末余额", "核销原因"), None),
    ])
    def test_balance_columns_are_pure_period_or_balance_measures(self, path, role):
        """余额列 = 纯期间 / 账面余额 / 公允价值；坏账准备 / 账面价值 / 比例 / 说明 不和试算表审定数比。"""
        assert L.column_roles(_col(*path))[1] == role

    @pytest.mark.parametrize("path,kind", [
        (("本期计提",), "increase"), (("本期应交",), "increase"), (("按面值计提利息",), "increase"),
        (("本期变动金额", "转销或核销"), "decrease"), (("本期增减变动", "减少投资"), "decrease"),
        (("本期核销",), "decrease"), (("核销金额",), "decrease"), (("本期增减变动", "计提减值准备"), "movement"),
        (("本期增加", "自用房地产或存货转入"), "increase"),
    ])
    def test_movement_kind_longest_word_wins(self, path, kind):
        """命中多个变动词取最长的（「计提减值准备」方向不定，不按「计提」认作增加）；同长按 增加 → 减少 → 不定。"""
        key = L.column_keys(_col(*path))[1]
        assert L.movement_kind(key) == kind and L.column_role(key) == kind

    def test_balance_side_columns_are_never_movements(self):
        """种子多级表头错位把「计提的利息」挂到期末余额下：期末一侧的列不当变动列。"""
        key = L.column_keys(_col("期末余额", "计提的利息"))[1]
        assert key.period == "end" and L.movement_kind(key) is None and L.column_role(key) is None

    def test_template_header_rows_beat_flat_headers(self):
        """角色按展示表头（多级表头）算，平表头不参与（五-24-1：期末余额 / 期初余额 各含 账面余额 / 减值准备 / 账面价值）。

        种子平表头已改成逐列全路径（R6.3），与展示表头逐列同路径；旧种子平表头只在分组起始列写期间
        （「期初余额」落在期末余额/减值准备上），换回这种错位平表头，角色也照展示表头。"""
        table = find_table("soe", "五-24-1")
        roles = ["label", "closing", None, None, "opening", None, None]
        assert L.column_roles(table) == roles
        assert [tuple(L.norm(p) for p in h.split("/")) for h in table["headers"][1:]] == L.column_paths(table)[1:]
        stale = dict(table, headers=["项  目", "期末余额", "期初余额", "", "", "", ""])
        assert L.column_roles(stale) == roles
        assert L.column_roles({"headers": stale["headers"]})[2] == "opening"  # 错位平表头单读会把减值准备列当期初

    def test_words_come_from_vocabulary(self):
        vocab = _vocab_with(movement_words={"increase": ["核销"]}, balance_measures=["账面价值"])
        assert L.column_roles(_col("本期核销"), vocab=vocab)[1] == "increase"   # 默认词表是减少：词表驱动
        assert L.column_roles(_col("本期增加"), vocab=vocab)[1] is None
        assert L.column_roles(_col("期末数", "账面价值"), vocab=vocab)[1] == "closing"
        assert L.column_roles(_col("期末数", "账面余额"), vocab=vocab)[1] is None


class TestRollForward:
    def test_simple_change_table(self):
        flow = L.rollforward_columns({"headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]})
        assert flow == L.RollForward(1, 4, (2,), (3,), ())

    def test_write_off_is_a_decrease(self):
        """坏账准备变动表：「本期核销」按减少参与勾稽（期末 = 期初 + 计提 − 转回 − 核销），不再按方向不定跳过整行。"""
        flow = L.rollforward_columns({"headers": ["项目", "期初余额", "本期计提", "本期收回或转回", "本期核销", "期末余额"]})
        assert flow == L.RollForward(1, 5, (2,), (3, 4), ())

    def test_every_leaf_of_movement_groups(self):
        """五-10-2 存货跌价准备：「本期增加 / 本期减少」分组下每个叶子列都参与（旧逻辑只认分组起始列）。"""
        assert L.rollforward_columns(find_table("soe", "五-10-2")) == L.RollForward(1, 7, (2, 3), (4, 5, 6), ())

    def test_unknown_flows_between_opening_and_closing(self):
        """五-81-9 筹资活动负债变动：现金流量净额 / 公允价值变动 / 其他 方向不定。"""
        assert L.rollforward_columns(find_table("soe", "五-81-9")) == L.RollForward(1, 6, (3,), (), (2, 4, 5))

    def test_columns_outside_opening_and_closing_are_notes(self):
        """十二-长期股权投资-2：期末之后的「本期计提减值准备 / 减值准备期末余额」是说明列，不参与勾稽。"""
        flow = L.rollforward_columns(find_table("soe", "十二-长期股权投资-2"))
        assert flow == L.RollForward(1, 4, (2,), (3,), ())

    def test_equity_investment_detail(self):
        """五-18-2 长期股权投资明细：投资成本在期初之前不参与；增减变动里「计提减值准备」方向不定。"""
        flow = L.rollforward_columns(find_table("soe", "五-18-2"))
        assert (flow.opening, flow.closing, flow.increase, flow.decrease) == (2, 11, (), (4,))
        assert flow.unknown == (3, 5, 6, 7, 8, 9, 10)

    def test_same_measure_pair_without_balance_columns(self):
        """五-25-1 期初 / 期末账面价值；五-58-1 期初 / 期末投资金额（所占比例是比例列）。"""
        assert L.rollforward_columns(find_table("soe", "五-25-1")) == L.RollForward(1, 4, (2,), (3,), ())
        assert L.rollforward_columns(find_table("soe", "五-58-1")) == L.RollForward(1, 5, (3,), (4,), ())

    def test_repaired_seed_movement_columns(self):
        """种子多级表头按 Word 修复后（R6.3）：「处置 / 转为自用房地产」回到「本期减少」下，变动列都有方向。"""
        assert L.rollforward_columns(find_table("soe", "五-22-1")) == L.RollForward(1, 6, (2, 3), (4, 5), ())
        assert L.rollforward_columns(find_table("soe", "五-13-2")) == L.RollForward(1, 5, (2,), (3, 4), ())
        assert L.rollforward_columns(find_table("soe", "五-29-1")) == L.RollForward(1, 7, (2, 3), (4, 5, 6), ())

    def test_not_a_single_rollforward(self):
        """五-51-2 数量 / 账面价值各有一对期初、期末：不唯一不校验；期末列重复、余额表、空表都不校验。"""
        assert L.rollforward_columns(find_table("soe", "五-51-2")) is None
        assert L.rollforward_columns({"headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额", "期末数"]}) is None
        assert L.rollforward_columns(find_table("soe", "五-1-1")) is None
        assert L.rollforward_columns({"headers": []}) is None
