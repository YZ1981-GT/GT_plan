"""附注表格合计构成（单体 / 合并 / 前端共用的唯一判定，spec note-pull-header-formula-closure R5）。"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import note_total_terms as ntt

BACKEND = Path(__file__).resolve().parents[1]


def _row(label, **kw):
    return {"label": label, **kw}


def _sub(label="小计"):
    return {"label": label, "row_type": "subtotal", "is_total": True}


def _tot(label="合计"):
    return {"label": label, "row_type": "total", "is_total": True}


class TestLabelRowType:
    @pytest.mark.parametrize("label, kind", [
        ("小计", "subtotal"), ("小  计", "subtotal"), ("小计：", "subtotal"), ("商业承兑汇票小计", "subtotal"),
        ("合计", "total"), ("合 计", "total"), ("合\u3000计", "total"), ("合计:", "total"), ("总计", "total"),
        ("三、其他综合收益合计", "data"), ("其他", "data"), ("", "data"), (None, "data"),
    ])
    def test_subtotal_checked_before_total(self, label, kind):
        assert ntt.label_row_type(label) == kind


class TestHelpers:
    ROWS = [_row("1年以内"), _row("1至2年"), _sub(), _row("减：坏账准备"), _tot()]

    def test_order_subtotals_first(self):
        plans, _ = ntt.total_terms(self.ROWS)
        assert ntt.total_order(self.ROWS, {4: plans[4], 2: plans[2]}) == [2, 4]

    def test_flatten_expands_subtotals_and_refuses_ambiguous(self):
        plans, _ = ntt.total_terms(self.ROWS)
        assert ntt.flatten_terms(self.ROWS, plans, 4) == [(0, 1), (1, 1), (3, -1)]
        rows = [_row("其中：甲"), _sub(), _row("减：乙"), _tot()]
        plans, reasons = ntt.total_terms(rows)
        assert 1 in reasons and ntt.flatten_terms(rows, plans, 3) is None

    def test_sum_terms_strict(self):
        values = {0: Decimal("100"), 1: None, 3: Decimal("15")}
        assert ntt.sum_terms([(0, 1), (1, 1), (3, -1)], values.get) == Decimal("85")
        assert ntt.sum_terms([(1, 1)], values.get) is None, "构成里的格全空不写 0"

    def test_title_style_table_with_an_emptied_group(self):
        """标题式小计表删空了一组：那组小计判不准，不把上一组的明细算给它；续表「小计 / 减 / 合计」不是标题式。"""
        rows = [_sub("商业承兑汇票小计"), _row("甲"), _sub("银行承兑汇票小计"), _tot()]
        plans, reasons = ntt.total_terms(rows)
        assert plans == {0: [(1, 1)], 3: [(0, 1), (2, 1)]} and list(reasons) == [2]
        plans, reasons = ntt.total_terms([_sub(), _row("减：一年内到期"), _tot()])
        assert plans == {2: [(0, 1), (1, -1)]} and list(reasons) == [0]

    def test_plan_description(self):
        plans, _ = ntt.total_terms(self.ROWS)
        assert ntt.plan_description(self.ROWS, plans[2]) == "明细之和"
        assert ntt.plan_description(self.ROWS, plans[4]) == "小计 − 减：坏账准备"


class TestSegmentHeadTotals:
    """段首合计（spec note-pull-followup-closure R7）：「一、…合计」在本段第一行、下面是本段明细。"""

    def test_each_head_total_sums_its_own_segment(self):
        rows = [_tot("一、账面原值合计"), _row("其中：土地资产"), _row("房屋、建筑物"), _row("……"),
                _tot("二、累计折旧合计"), _row("1、房屋、建筑物"), _row("2、土地使用权")]
        plans, reasons = ntt.total_terms(rows)
        assert plans == {0: [(1, 1), (2, 1)], 4: [(5, 1), (6, 1)]} and reasons == {}, "「其中：X」在段内第一行算构成，占位行不算"
        assert ntt.plan_description(rows, plans[0]) == "明细之和"

    @pytest.mark.parametrize("bad, reason", [
        ([_row("房屋"), _row("其中：境外")], "其中"),
        ([_row("其中："), _row("房屋")], "其中"),
        ([_row("房屋"), _row("减：减值准备")], "减项"),
        ([_row("房屋"), _row("（一）境外")], "分段标题"),
        ([], "没有可合计的明细行"),
    ])
    def test_ambiguous_segment_is_refused_alone(self, bad, reason):
        rows = [_tot("一、原价合计"), *bad, _tot("二、累计摊销合计"), _row("专利权"), _row("软件")]
        plans, reasons = ntt.total_terms(rows)
        second = len(bad) + 1
        assert list(reasons) == [0] and reason in reasons[0], reasons
        assert plans == {second: [(second + 1, 1), (second + 2, 1)]}, "别的段照常判"

    @pytest.mark.parametrize("rows", [
        [_row("流动资产"), _tot("一、资产合计"), _row("流动负债"), _tot("二、负债合计")],  # 第一行不是合计
        [_tot("一、成本合计"), _row("房屋"), _tot("合计"), _row("土地")],  # 有合计不是分段标题式
        [_tot("一、成本合计"), _row("房屋"), _sub("（一）小计"), _row("土地")],  # 有小计
    ])
    def test_other_shapes_keep_the_old_verdict(self, rows):
        kinds = [ntt.row_kind(r) for r in rows]
        totals = [i for i, k in enumerate(kinds) if k in ("total", "subtotal")]
        assert ntt._segment_head_terms(rows, kinds, totals) is None
        plans, reasons = ntt.total_terms(rows)
        assert reasons and not plans and "多个合计" in next(iter(reasons.values())), (plans, reasons)

    def test_single_head_total(self):
        plans, reasons = ntt.total_terms([_tot("一、成本合计"), _row("房屋"), _row("土地")])
        assert plans == {0: [(1, 1), (2, 1)]} and reasons == {}
        plans, reasons = ntt.total_terms([_tot("合计"), _row("房屋"), _row("土地")])
        assert plans == {} and list(reasons) == [0], "不是分段标题式的合计在第一行：照旧判不准"

    def test_real_templates(self):
        doc = {tt: json.loads((BACKEND / "data" / f"note_template_{tt}.json").read_text(encoding="utf-8"))
               for tt in ("soe", "listed")}

        def table(tt, section, name):
            sec = next(s for s in doc[tt]["sections"] if s["section_number"] == section)
            return next(t for t in sec["tables"] if t.get("name") == name)["rows"]

        judged = [("八、21", "以成本计量", 5), ("八、21", "以公允价值计量", 3), ("八、22", "固定资产情况", 5),
                  ("八、25", "油气资产", 4), ("八、26", "使用权资产", 5), ("八、27", "无形资产情况", 4)]
        for section, name, count in judged:
            rows = table("soe", section, name)
            plans, reasons = ntt.total_terms(rows)
            assert len(plans) == count and reasons == {}, (section, name, reasons)
            for target, terms in plans.items():
                assert all(ntt.row_kind(rows[r]) in ("data", "sub") for r, _s in terms), (section, target)
        for section, name in [("七、8", "在合营安排或联营企业中的权益（表2）"), ("七、8", "在合营安排或联营企业中的权益（表6）"),
                              ("九、2", "风险管理目标和政策（表8）")]:
            plans, reasons = ntt.total_terms(table("listed", section, name))
            assert plans == {} and reasons, (section, name)


class TestRealTemplates:
    """按真模板逐表：构成只引用本表的行、小计的构成里没有合计行；国企 八、87 融资租赁的跨段小计判不准。"""

    @pytest.mark.parametrize("tt", ["soe", "listed"])
    def test_plans_reference_rows_of_the_same_table(self, tt):
        doc = json.loads((BACKEND / "data" / f"note_template_{tt}.json").read_text(encoding="utf-8"))
        checked = 0
        for sec in doc["sections"]:
            for table in sec.get("tables") or []:
                rows = table.get("rows") or []
                kinds = [ntt.row_kind(r) for r in rows]
                plans, reasons = ntt.total_terms(rows)
                assert not set(plans) & set(reasons)
                for target, terms in plans.items():
                    assert kinds[target] in ("total", "subtotal")
                    assert all(0 <= r < len(rows) and r != target for r, _s in terms)
                    if kinds[target] == "subtotal":
                        assert all(kinds[r] == "data" for r, _s in terms), (sec["section_number"], target)
                    checked += 1
        assert checked > 200

    def test_finance_lease_cross_segment_subtotal_is_ambiguous(self):
        doc = json.loads((BACKEND / "data" / "note_template_soe.json").read_text(encoding="utf-8"))
        sec = next(s for s in doc["sections"] if s["section_number"] == "八、87")
        table = next(t for t in sec["tables"] if any("未折现租赁收款额小计" in str(r.get("label")) for r in t["rows"]))
        plans, reasons = ntt.total_terms(table["rows"])
        row = next(i for i, r in enumerate(table["rows"]) if "未折现租赁收款额小计" in str(r.get("label")))
        assert row not in plans and "分段标题" in reasons[row]


def test_golden_is_current():
    """前后端交叉锁：golden 与现算一致（前端 noteTotalTerms.spec.ts 逐表对照同一份）。"""
    import importlib.util

    path = BACKEND / "scripts" / "gen" / "gen_note_total_terms_golden.py"
    spec = importlib.util.spec_from_file_location("_gen_note_total_terms_golden", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    current = (BACKEND / "data" / "note_total_terms_golden.json").read_text(encoding="utf-8")
    assert module.render() == current, "重跑 python scripts/gen/gen_note_total_terms_golden.py --write"
