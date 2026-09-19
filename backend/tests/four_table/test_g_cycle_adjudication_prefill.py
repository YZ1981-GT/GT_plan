"""G 循环审定表「从四表库带入未审数」统一预填载荷守卫。

钉死 Task 3.3 的四条设计约束（每条都对应一个已实证的缺陷形态）：

1. **宁缺勿造** —— 无槽 / 无叶子 / 全零余额一律返 ``{}``，前端据此显示
   「四表库暂无该科目数据」而不是把 0 当「已核实为零」。
2. **损益类单侧取数** —— ``debit - credit`` 在含年末结转损益的全年账上结构性恒为 0
   （N4/N5 实证 9 个项目全中），本文件用「借贷相等」的真实形态做**反向自检**。
3. **不做桶预聚合** —— 载荷必须含逐叶子明细（``leaves``），否则审计师在前端改归属后
   无法重算（E1 受限资金实证）。
4. **备抵正数口径** —— `tb_balance` 对备抵科目有两种符号约定（G7 的 `1512` 存负值），
   审定表减值段是正数，必须 ``abs()`` 归一。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 3.3, 3.4, 3.5 / Task 3.3
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.four_table.g_cycle_adjudication_prefill import (
    PERIOD_BALANCE,
    PERIOD_CURRENT,
    SlotView,
    balance_amounts,
    build_g_adjudication_prefill,
    normalize_slots,
    pl_occurrence,
    slot_of_code,
)
from app.services.four_table.g_cycle_specs import G_PL_CYCLES, G_PL_POSITIVE_SIDE
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.report_line_accounts import ReportLineAccounts
from app.services.four_table.semantic_account_resolver import (
    ResolvedSlot,
    SemanticAccountResult,
)


# ─── 构造助手 ────────────────────────────────────────────────────────────────


def _leaf(code, name, opening=0.0, closing=0.0, debit=0.0, credit=0.0) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=opening,
        closing=closing,
        debit=debit,
        credit=credit,
    )


def _semantic(**slots) -> SemanticAccountResult:
    """``_semantic(gross=['1504'], provision=['1505'])`` → SemanticAccountResult。"""
    out = {}
    for key, codes in slots.items():
        out[key] = ResolvedSlot(
            key=key,
            label=key,
            is_provision=(key == "provision"),
            codes=list(codes),
            standard_codes=list(codes),
        )
    return SemanticAccountResult(slots=out, chart_available=True)


# ─── Property 1：宁缺勿造 ────────────────────────────────────────────────────


class TestEmptyIsEmpty:
    def test_unregistered_wp_code(self):
        assert build_g_adjudication_prefill("X9", _semantic(gross=["1504"]),
                                            [_leaf("1504.01", "a", closing=1)]) == {}

    def test_no_slot_codes(self):
        """本项目无该科目族 → {}（不能退化成宽前缀取别循环的钱）。"""
        assert build_g_adjudication_prefill("G4", _semantic(), [_leaf("1504", "债权投资", closing=1)]) == {}
        assert build_g_adjudication_prefill("G4", None, [_leaf("1504", "债权投资", closing=1)]) == {}

    def test_no_rows(self):
        assert build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), []) == {}

    def test_all_zero_leaves_dropped(self):
        """🔴 全零叶子不下发 —— 否则「不适用」被伪装成「已核实为零」。"""
        rows = [_leaf("1504.01", "债权投资_A", 0.0, 0.0)]
        assert build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows) == {}

    def test_pl_zero_occurrence_dropped(self):
        rows = [_leaf("6111.01", "投资收益_A", debit=0.0, credit=0.0)]
        assert build_g_adjudication_prefill("G11", _semantic(gross=["6111"]), rows) == {}


# ─── Property 2：资产 / 负债类口径 ───────────────────────────────────────────


class TestBalanceCycles:
    ROWS = [
        _leaf("1504", "债权投资", 1000.0, 1200.0),          # 父行
        _leaf("1504.01", "债权投资_甲公司债券", 600.0, 700.0),
        _leaf("1504.02", "债权投资_乙公司债券", 400.0, 500.0),
        _leaf("1505", "债权投资减值准备", -50.0, -80.0),      # 🔴 负值存储
    ]

    def _out(self):
        return build_g_adjudication_prefill(
            "G4", _semantic(gross=["1504"], provision=["1505"]), self.ROWS
        )

    def test_period_is_balance(self):
        out = self._out()
        assert out["period"] == PERIOD_BALANCE
        assert out["positive_side"] == ""

    def test_parent_row_excluded_leaves_only(self):
        """父行 `1504` 不进 leaves（否则父子双算）。"""
        codes = [x["code"] for x in self._out()["leaves"]]
        assert "1504" not in codes
        assert set(codes) == {"1504.01", "1504.02", "1505"}

    def test_provision_absolute_value(self):
        """🔴 备抵负值 → 正数口径（审定表减值段与原值段方向一致）。"""
        prov = next(x for x in self._out()["leaves"] if x["code"] == "1505")
        assert prov["opening"] == 50.0
        assert prov["closing"] == 80.0

    def test_slot_totals(self):
        slots = self._out()["slots"]
        assert slots["gross"]["closing"] == 1200.0
        assert slots["provision"]["closing"] == 80.0
        assert slots["provision"]["is_provision"] is True

    def test_parent_check_leaf_sum_equals_parent(self):
        """叶子和 == 父额自检（本例故意含备抵 → 单前缀条件不成立，应为 None）。"""
        assert self._out()["parent_check"] is None

    def test_parent_check_single_prefix(self):
        rows = [
            _leaf("1504", "债权投资", 1000.0, 1200.0),
            _leaf("1504.01", "债权投资_甲", 600.0, 700.0),
            _leaf("1504.02", "债权投资_乙", 400.0, 500.0),
        ]
        pc = build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows)["parent_check"]
        assert pc == {"leaf_sum": 1200.0, "parent": 1200.0, "diff": 0.0}

    def test_dot_boundary(self):
        """`1101` 不得吸入 `11010`（不同科目）。"""
        rows = [
            _leaf("1101.01", "交易性金融资产_股票", 10.0, 20.0),
            _leaf("11010", "别的科目", 999.0, 999.0),
        ]
        out = build_g_adjudication_prefill("G1", _semantic(gross=["1101"]), rows)
        assert [x["code"] for x in out["leaves"]] == ["1101.01"]


# ─── Property 3：损益类单侧取数 + 反向自检 ───────────────────────────────────


class TestPlCycles:
    #: 真实形态：必有「结转本年利润」分录 → 借贷两侧金额**恒相等**
    CARRY_FORWARD_ROWS = [
        _leaf("6111.01", "投资收益_权益法", debit=732_847.56, credit=732_847.56),
        _leaf("6111.02", "投资收益_处置", debit=100_000.00, credit=100_000.00),
    ]

    def test_credit_side_for_income(self):
        out = build_g_adjudication_prefill("G11", _semantic(gross=["6111"]), self.CARRY_FORWARD_ROWS)
        assert out["period"] == PERIOD_CURRENT
        assert out["positive_side"] == "credit"
        assert out["total"]["current"] == pytest.approx(832_847.56)
        # 余额列不参与（损益类期末余额结转后归零）
        assert out["total"]["closing"] == 0.0

    def test_debit_side_for_loss(self):
        rows = [_leaf("6702.01", "信用减值损失_应收账款", debit=126_151_230.15, credit=126_151_230.15)]
        out = build_g_adjudication_prefill("G14", _semantic(gross=["6702"]), rows)
        assert out["positive_side"] == "debit"
        assert out["total"]["current"] == pytest.approx(126_151_230.15)

    def test_reverse_selfcheck_debit_minus_credit_would_be_zero(self):
        """🔴 反向自检：若改用 `debit - credit`，本 fixture 的发生额会全归 0。

        这正是 N4/N5 实测踩到的形态 —— 该断言失败说明有人把口径改回了差额法。
        """
        for leaf in self.CARRY_FORWARD_ROWS:
            assert leaf.debit - leaf.credit == 0
        out = build_g_adjudication_prefill("G11", _semantic(gross=["6111"]), self.CARRY_FORWARD_ROWS)
        assert out["total"]["current"] > 0

    def test_pl_sign_table_covers_exactly_pl_cycles(self):
        assert set(G_PL_POSITIVE_SIDE) == set(G_PL_CYCLES)
        assert set(G_PL_POSITIVE_SIDE.values()) <= {"debit", "credit"}

    def test_pl_occurrence_pure(self):
        leaf = _leaf("6111.01", "x", debit=3.0, credit=7.0)
        assert pl_occurrence(leaf, "credit") == 7.0
        assert pl_occurrence(leaf, "debit") == 3.0


# ─── Property 4：逐叶子明细必须下发（禁桶预聚合） ────────────────────────────


class TestLeafDetailIsMandatory:
    def test_leaves_present_and_sums_to_total(self):
        rows = [
            _leaf("1504.01", "债权投资_甲", 600.0, 700.0),
            _leaf("1504.02", "债权投资_乙", 400.0, 500.0),
        ]
        out = build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows)
        assert len(out["leaves"]) == 2
        assert out["total"]["closing"] == pytest.approx(
            sum(x["closing"] for x in out["leaves"])
        )

    def test_no_bucket_key_in_payload(self):
        """载荷里不得出现预聚合的桶结构（`buckets` / `by_category`）。"""
        rows = [_leaf("1504.01", "债权投资_甲", 600.0, 700.0)]
        out = build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows)
        assert "buckets" not in out
        assert "by_category" not in out

    def test_every_leaf_carries_code_name_slot(self):
        rows = [_leaf("1504.01", "债权投资_甲", 600.0, 700.0)]
        leaf = build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows)["leaves"][0]
        assert leaf["code"] == "1504.01"
        assert leaf["name"] == "债权投资_甲"
        assert leaf["slot"] == "gross"


# ─── Property 5：槽归属与结果形态归一 ────────────────────────────────────────


class TestSlotResolution:
    def test_longest_prefix_wins(self):
        slots = {
            "gross": SlotView("gross", "原值", codes=["1101"]),
            "derivative": SlotView("derivative", "衍生", codes=["1101.04"]),
        }
        assert slot_of_code(slots, "1101.04.01") == "derivative"
        assert slot_of_code(slots, "1101.01") == "gross"
        assert slot_of_code(slots, "9999") is None

    def test_normalize_semantic_result(self):
        slots = normalize_slots(_semantic(gross=["1504"], provision=["1505"]))
        assert set(slots) == {"gross", "provision"}
        assert slots["provision"].is_provision is True

    def test_normalize_report_line_accounts(self):
        """🔴 兼容 `ReportLineAccounts`（G1/G2/G3/G4/G10~G13 主 render 仍在用）。"""
        acc = ReportLineAccounts(gross=["1101"], provision=[])
        slots = normalize_slots(acc)
        assert set(slots) == {"gross"}
        assert slots["gross"].codes == ["1101"]

    def test_normalize_report_line_accounts_with_provision(self):
        acc = ReportLineAccounts(gross=["1504"], provision=["1505"])
        slots = normalize_slots(acc)
        assert set(slots) == {"gross", "provision"}
        assert slots["provision"].is_provision is True

    def test_normalize_none_and_unknown(self):
        assert normalize_slots(None) == {}
        assert normalize_slots(object()) == {}

    def test_report_line_path_produces_prefill(self):
        """报表行结果也能产出预填（不必等 Wave 2 迁移完成）。"""
        rows = [_leaf("2101.01", "交易性金融负债_甲", 100.0, 200.0)]
        out = build_g_adjudication_prefill("G10", ReportLineAccounts(gross=["2101"]), rows)
        assert out["total"]["closing"] == 200.0
        assert out["period"] == PERIOD_BALANCE


# ─── Property 6：balance_amounts 纯函数 ──────────────────────────────────────


class TestBalanceAmounts:
    @pytest.mark.parametrize("stored", [(-80.0), (80.0)])
    def test_provision_两种符号约定同解(self, stored):
        leaf = _leaf("1505", "债权投资减值准备", stored, stored)
        assert balance_amounts(leaf, is_provision=True) == (80.0, 80.0)

    def test_gross_keeps_sign(self):
        """原值保留符号 —— 借方叶子出现负余额是合法的（K1 实证），翻正会破坏勾稽。"""
        leaf = _leaf("1504.98", "债权投资_调整", -86_483.10, -86_483.10)
        assert balance_amounts(leaf, is_provision=False) == (-86_483.10, -86_483.10)


# ─── PBT：合计恒等 ──────────────────────────────────────────────────────────


_amount = st.floats(
    min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False, width=32
)


@settings(max_examples=5, deadline=None)
@given(st.lists(_amount, min_size=1, max_size=6))
def test_pbt_total_equals_leaf_sum(closings):
    rows = [
        _leaf(f"1504.{i:02d}", f"债权投资_{i}", 0.0, round(c, 2))
        for i, c in enumerate(closings, 1)
    ]
    out = build_g_adjudication_prefill("G4", _semantic(gross=["1504"]), rows)
    if not out:
        # 全零 → 空载荷（宁缺勿造），无需比对
        assert all(round(c, 2) == 0 for c in closings)
        return
    assert out["total"]["closing"] == pytest.approx(
        round(sum(x["closing"] for x in out["leaves"]), 2), abs=0.01
    )


@settings(max_examples=5, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=1e9, allow_nan=False, width=32),
                min_size=1, max_size=6))
def test_pbt_pl_total_equals_positive_side_sum(credits):
    """损益类：合计 == 正方向单侧之和（借方同额也不得抵减）。"""
    rows = [
        _leaf(f"6111.{i:02d}", f"投资收益_{i}", debit=round(c, 2), credit=round(c, 2))
        for i, c in enumerate(credits, 1)
    ]
    out = build_g_adjudication_prefill("G11", _semantic(gross=["6111"]), rows)
    expected = round(sum(round(c, 2) for c in credits), 2)
    if not out:
        assert expected == 0
        return
    assert out["total"]["current"] == pytest.approx(expected, abs=0.01)
