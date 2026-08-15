"""I5 其他非流动资产「本项目无此科目」三态守卫（Property 6 / 7）。

背景（`report_config` + `account_chart` 双向实证，2026-08-09）：

- ``BS-037 其他非流动资产 = TB('1911','期末余额')`` —— 四准则同码同公式；
- 而 ``1911`` 在 `account_chart` 的 **两张表（client / standard）全库都不存在**，
  科目名「其他非流动资产」亦零命中 ⇒ 8 个真实项目 I5 全部 ``std=[] orig=[]``。

⇒ 段兜底码保持**空 tuple** 是**正确行为**（宁缺勿造），不是待补的缺口。
本守卫钉死这一点，并要求「本项目无此科目」与「余额为 0」两态可分 ——
前者 ``found=False``、码集为空；后者 ``found=True`` 且金额为 0。
把两者都渲染成 ``0.00`` 会让审计师把「平台取不到数」误当「客户确实没余额」而漏做程序。

反向自检（Property 7）：构造一个**含** ``1911`` 或名为「其他非流动资产」的科目表替身，
解析必须命中 —— 证明「返空」是数据事实而非判据被写死成空。

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/
      Requirements 2.1~2.4，Property 6 / 7
"""
from __future__ import annotations

import pytest

from app.services.four_table.i_cycle_accounts import (
    SEGMENT_COST,
    I_CYCLE_SEGMENTS,
    ISegmentAccounts,
    claim_segments,
)

_I5_SEGMENTS = I_CYCLE_SEGMENTS["I5"]


# ─────────────────────────────────────────────────────────────────────────────
# Property 6 —— 兜底空 + 三态可分
# ─────────────────────────────────────────────────────────────────────────────


class TestProperty6EmptyFallbackAndThreeStates:
    """I5 cost 段兜底必须为空；三态必须可区分。"""

    def test_i5_has_exactly_one_segment(self):
        assert len(_I5_SEGMENTS) == 1, (
            f"I5 应为单段（cost），实为 {len(_I5_SEGMENTS)} 段："
            f"{[s.segment for s in _I5_SEGMENTS]}"
        )
        assert _I5_SEGMENTS[0].segment == SEGMENT_COST

    def test_i5_fallback_is_empty_tuple(self):
        """🔴 宁缺勿造：`1911` 全库不存在，禁按 CAS 猜一个码填进去。"""
        spec = _I5_SEGMENTS[0]
        assert spec.fallback == (), (
            f"I5 cost 段兜底码必须为空 tuple，实为 {spec.fallback!r}。\n"
            "依据：`BS-037 = TB('1911')` 而 `1911` 在 account_chart 两张表全库都不存在，"
            "「其他非流动资产」科目名亦零命中 ⇒ 无标准科目可映射。\n"
            "给它填任何码都是臆造（会让审计师看到一个不属于本科目的金额）。"
        )

    def test_i5_is_not_a_provision_or_occurrence_segment(self):
        """I5 是资产原值段：不取绝对值、不走本期发生额。"""
        spec = _I5_SEGMENTS[0]
        assert spec.absolute is False
        assert spec.credit_is_increase is False
        assert spec.occurrence is False

    def test_state_absent_no_account(self):
        """态①「本项目无此科目」：``standard`` 与 ``original`` 双空。

        .. note::
           🔴 判据是**码集空/非空**，不是某个 ``found`` 布尔字段 ——
           `ISegmentAccounts` 有意不设该字段（实证其字段为
           ``segment/label/standard/original/exact/resolved_from/absolute/...``）。
           前端共享件 `cycleAccountScope.isAccountAbsent()` 同样按码集判定，
           两侧同源。守卫不得为了「好断言」而给生产 dataclass 新增字段。
        """
        seg = ISegmentAccounts(
            segment=SEGMENT_COST,
            label="其他非流动资产",
            standard=[],
            original=[],
            resolved_from="none",
        )
        assert not seg.standard and not seg.original, "态①：码集必须双空"

    def test_state_zero_balance_is_distinguishable(self):
        """态②「余额为 0」：有科目映射（码集非空），金额为 0 与态①必须可分。"""
        seg = ISegmentAccounts(
            segment=SEGMENT_COST,
            label="其他非流动资产",
            standard=["1911"],
            original=["1911"],
            resolved_from="report_config",
        )
        assert seg.standard and seg.original, (
            "有科目映射时码集必须非空 —— 否则「余额为 0」与「无此科目」不可区分"
        )

    def test_two_states_differ(self):
        """两态的码集空性必须不同（这是前端能分开渲染的唯一依据）。"""
        absent = ISegmentAccounts(
            segment=SEGMENT_COST, label="x", standard=[], original=[]
        )
        zero = ISegmentAccounts(
            segment=SEGMENT_COST, label="x", standard=["1911"], original=["1911"]
        )
        assert bool(absent.standard) != bool(zero.standard), (
            "两态在码集空性上必须可分"
        )

    def test_no_found_field_by_design(self):
        """反向锁死：`ISegmentAccounts` **有意**不设 ``found`` 字段。

        若将来有人加了它，本条打红提醒：要么两侧（后端 dataclass + 前端
        `isAccountAbsent`）同时改并收敛判据，要么别加 —— 禁出现「一个语义两处
        各判一次」的双真源。
        """
        seg = ISegmentAccounts(segment=SEGMENT_COST, label="x")
        assert not hasattr(seg, "found"), (
            "`ISegmentAccounts` 新增了 found 字段 —— 三态判据出现第二个真源。\n"
            "现有判据 = 码集空/非空（前后端同源）；加字段前须先收敛判据。"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Property 7 —— 反向自检：判据不是写死为空
# ─────────────────────────────────────────────────────────────────────────────


class TestProperty7ReverseSelfCheck:
    """构造替身证明「若科目真的存在则会命中」。"""

    def test_claim_hits_when_1911_named_correctly(self):
        """替身：`1911` 存在且名为「其他非流动资产」⇒ cost 段必须认领它。"""
        name_lookup = {"1911": "其他非流动资产"}
        claimed, unclaimed = claim_segments(["1911"], name_lookup, _I5_SEGMENTS)
        assert "1911" in claimed[SEGMENT_COST], (
            "替身里 1911 名为「其他非流动资产」却未被 cost 段认领 —— "
            "说明认领判据被写死成空（Property 7 不成立）"
        )
        assert unclaimed == []

    def test_claim_hits_when_client_uses_other_code(self):
        """替身：客户把「其他非流动资产」挂在非标准码 `1901` 上 ⇒ 同样应认领。

        这是「按科目名定位」优于「按码硬查」的关键场景。
        """
        name_lookup = {"1901": "其他非流动资产"}
        claimed, _ = claim_segments(["1901"], name_lookup, _I5_SEGMENTS)
        assert "1901" in claimed[SEGMENT_COST]

    def test_claim_misses_unrelated_account(self):
        """反面：不相关科目不得被 I5 认领（否则会把别的循环的钱算进来）。"""
        name_lookup = {"2241": "其他应付款"}
        claimed, unclaimed = claim_segments(["2241"], name_lookup, _I5_SEGMENTS)
        assert claimed.get(SEGMENT_COST, ()) == () or "2241" not in claimed[SEGMENT_COST]
        assert "2241" in unclaimed

    @pytest.mark.parametrize(
        "name",
        ["其他非流动资产", "其他非流动资产_长期预付款", "长期其他非流动资产"],
    )
    def test_name_variants_hit(self, name: str):
        """名称变体（带前后缀的客户子科目名）应命中。"""
        claimed, _ = claim_segments(["9999"], {"9999": name}, _I5_SEGMENTS)
        assert "9999" in claimed[SEGMENT_COST], f"{name!r} 未命中 I5 语义"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3（补强）：叶子聚合纯函数的符号与空段语义
#
# 🔴 **2026-08-12 变异检验 P3 判 GREEN 抓出的真缺口**：把
# `i_cycle_prefill.build_leaf_project_rows` 里的 `sign = abs if seg.absolute else ...`
# 改成恒等（备抵段不再取绝对值 ⇒ 累计摊销/减值准备全变负数），**全库无一条测试打红**。
# 实测全库确实**没有任何守卫测** `build_leaf_project_rows` / `segment_amounts` /
# `build_i1_category_rows` —— 其余循环（D6/F2/K1/K2/N1~N5）都测了自己的
# `build_adjudication_prefill`，只有 I 循环的纯函数层裸奔。
#
# Property 3 原本靠「连库 A/B 对照」验证，但那是**一次性**的落地前比对，
# 不进 CI、也拦不住后续回退。本组补上纯函数级的常驻判据。
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty3LeafAggregationPurity:
    """叶子聚合的符号约定与「宁缺勿造」语义。"""

    @staticmethod
    def _leaf(code: str, name: str, opening: float, closing: float,
              debit: float = 0.0, credit: float = 0.0):
        from app.services.four_table.leaf_aggregation import LeafRow

        return LeafRow(
            account_code=code,
            account_name=name,
            opening=opening,
            closing=closing,
            debit=debit,
            credit=credit,
        )

    @staticmethod
    def _seg(segment: str, prefixes: tuple[str, ...], *, absolute: bool = False,
             credit_is_increase: bool = False):
        from app.services.four_table.i_cycle_accounts import ISegmentAccounts

        return ISegmentAccounts(
            segment=segment,
            label=segment,
            standard=list(prefixes),
            original=list(prefixes),
            exact=True,
            resolved_from="test",
            absolute=absolute,
            credit_is_increase=credit_is_increase,
            occurrence=False,
        )

    def test_provision_segment_takes_absolute_value(self):
        """🔴 备抵段（`absolute=True`）的四个金额必须**全部**取绝对值。

        `tb_balance` 的备抵科目是贷方余额（v1 口径存负数或带方向），
        不取绝对值会让审定表的「累计摊销」「减值准备」列显示负数，
        且与源模板的「正数列示、末行相减」形态冲突。
        """
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1702.01", "累计摊销_土地使用权", -100.0, -180.0, 0.0, 80.0)]
        rows = build_leaf_project_rows(leaves, self._seg("amortization", ("1702",), absolute=True))
        assert len(rows) == 1, f"应产出 1 行，实为 {rows}"
        row = rows[0]
        for field in ("opening", "closing", "increase", "decrease"):
            assert row[field] >= 0, (
                f"备抵段 {field}={row[field]} 为负 ⇒ `absolute=True` 未生效。"
                f"整行 = {row}"
            )
        assert row["opening"] == 100.0 and row["closing"] == 180.0

    def test_non_provision_segment_keeps_sign(self):
        """反向边界：非备抵段（`absolute=False`）**不得**取绝对值。

        没有这条，把 `sign` 写成恒 `abs` 也会绿 —— 那会把资产段的负数余额
        （如红冲后的开发支出）伪装成正数。
        """
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1704.01", "开发支出_项目甲", -50.0, -70.0, 0.0, 20.0)]
        rows = build_leaf_project_rows(leaves, self._seg("cost", ("1704",), absolute=False))
        assert rows[0]["opening"] == -50.0, f"非备抵段被取了绝对值：{rows[0]}"
        assert rows[0]["closing"] == -70.0

    def test_credit_is_increase_swaps_increase_decrease(self):
        """`credit_is_increase=True` 时增减方向互换（备抵科目贷方是增加）。"""
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1702.01", "累计摊销_软件", 0.0, 0.0, debit=30.0, credit=70.0)]
        swapped = build_leaf_project_rows(
            leaves, self._seg("amortization", ("1702",), absolute=True, credit_is_increase=True)
        )[0]
        normal = build_leaf_project_rows(
            leaves, self._seg("cost", ("1702",), absolute=True, credit_is_increase=False)
        )[0]
        assert swapped["increase"] == 70.0 and swapped["decrease"] == 30.0, swapped
        assert normal["increase"] == 30.0 and normal["decrease"] == 70.0, normal

    def test_empty_prefix_segment_returns_no_rows(self):
        """段无科目码（I5 / I3.impairment 实证形态）→ 返空列表，**不造零行**。

        造一行 0 会把「本项目无此科目」伪装成「已核实为零」（E1 已实测过该缺陷）。
        """
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1911.01", "其他非流动资产_预付设备款", 10.0, 20.0)]
        assert build_leaf_project_rows(leaves, self._seg("cost", ())) == []

    def test_unmatched_leaves_produce_no_rows(self):
        """前缀不命中任何叶子 → 空列表（不兜底、不塞「其他」行）。"""
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1601.01", "固定资产_房屋", 10.0, 20.0)]
        assert build_leaf_project_rows(leaves, self._seg("cost", ("1704",))) == []

    def test_same_label_leaves_are_merged_with_all_codes_kept(self):
        """同名叶子合并成一行，但 `codes` 必须保留全部来源码（溯源不能丢）。"""
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [
            self._leaf("1704.01", "开发支出_项目甲", 10.0, 20.0),
            self._leaf("1704.02", "开发支出_项目甲", 5.0, 7.0),
        ]
        rows = build_leaf_project_rows(leaves, self._seg("cost", ("1704",)))
        assert len(rows) == 1, f"同名叶子未合并：{rows}"
        assert rows[0]["opening"] == 15.0 and rows[0]["closing"] == 27.0
        assert sorted(rows[0]["codes"]) == ["1704.01", "1704.02"], rows[0]["codes"]

    def test_segment_amounts_matches_row_totals(self):
        """`segment_amounts()` 的合计必须等于逐行求和（两条取数路径不得漂移）。"""
        from app.services.four_table.i_cycle_prefill import (
            build_leaf_project_rows,
            segment_amounts,
        )

        leaves = [
            self._leaf("1704.01", "开发支出_甲", 10.0, 20.0, debit=12.0, credit=2.0),
            self._leaf("1704.02", "开发支出_乙", 5.0, 8.0, debit=4.0, credit=1.0),
        ]
        seg = self._seg("cost", ("1704",))
        rows = build_leaf_project_rows(leaves, seg)
        totals = segment_amounts(leaves, seg)
        assert round(sum(r["opening"] for r in rows), 2) == round(totals["opening"], 2)
        assert round(sum(r["closing"] for r in rows), 2) == round(totals["closing"], 2)

    def test_reverse_self_check_absolute_flag_actually_matters(self):
        """反向自检：同一批叶子在 `absolute` 开/关下结果**必须不同**。

        若两者相同说明取数根本没读 `absolute`（判据在空转）。
        """
        from app.services.four_table.i_cycle_prefill import build_leaf_project_rows

        leaves = [self._leaf("1702.01", "累计摊销_专利", -100.0, -200.0)]
        on = build_leaf_project_rows(leaves, self._seg("amortization", ("1702",), absolute=True))
        off = build_leaf_project_rows(leaves, self._seg("amortization", ("1702",), absolute=False))
        assert on[0]["closing"] != off[0]["closing"], (
            f"absolute 开/关结果相同（{on[0]['closing']}）⇒ 该标志未被消费，判据空转"
        )
