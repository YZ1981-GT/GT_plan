"""E1 货币资金四表取数守卫（科目定位 / 叶子聚合 / 零余额账户 / 受限口径）。

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 11.1, 11.5**

Properties: 1（叶子和 == 父额）、2（点号边界）、3（零余额账户保留）、
4（无字面量兜底泄漏）、16（受限候选集不重不漏）

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ (Task 2/3/3.5/4)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies import _e1_monetary_fund as e1
from app.services.four_table import LeafRow, aggregate_leaves, parent_totals, select_leaves
from app.services.four_table.e_cycle_specs import (
    E1_MONETARY_FUND_SPEC,
    E1_REPORT_ROW_CODE,
    E1_SLOT_BANK,
    E1_SLOT_CASH,
    E1_SLOT_DIGITAL,
    E1_SLOT_FINANCE_CO,
    E1_SLOT_OTHER,
    E1_TOTAL_SLOT_KEYS,
)
from app.services.four_table.semantic_account_resolver import (
    RESOLVED_FROM_CLIENT_CHART,
    RESOLVED_FROM_NONE,
    ResolvedSlot,
    SemanticAccountResult,
)

E1_RENDER_PATH = Path(e1.__file__)
SPEC_PATH = Path(E1_MONETARY_FUND_SPEC.__module__.replace(".", "/") + ".py")


# ─── 测试替身 ────────────────────────────────────────────────────────────────


def _slot(key: str, codes: list[str], *, found: bool = True) -> ResolvedSlot:
    return ResolvedSlot(
        key=key,
        label=key,
        codes=list(codes),
        standard_codes=list(codes),
        matched=[(c, key) for c in codes],
        resolved_from=RESOLVED_FROM_CLIENT_CHART if found else RESOLVED_FROM_NONE,
        exact=True,
    )


def _accounts(**slot_codes: list[str]) -> SemanticAccountResult:
    slots = {k: _slot(k, v) for k, v in slot_codes.items()}
    return SemanticAccountResult(
        slots=slots, row_code=E1_REPORT_ROW_CODE, chart_available=True
    )


def _row(code: str, name: str, opening: float, closing: float,
         debit: float = 0.0, credit: float = 0.0) -> LeafRow:
    return LeafRow(
        account_code=code, account_name=name,
        opening=opening, closing=closing, debit=debit, credit=credit,
        direction="debit", opening_direction="debit",
    )


# ─── 活体形态子树（项目 df5b8403 实证，含三层科目）──────────────────────────
#
# 1002 父 20,751,212.11 = 1002.011 746,150.53 + 1002.012 5,061.58 + 1002.013 20,000,000
# 1012 父    461,130.20 = 1012.012 101,085.58 + 1012.013 12,025.18
#                        + 1012.014.01 232,580.53 + 1012.014.02 115,438.91
LIVE_SUBTREE: list[LeafRow] = [
    _row("1001", "库存现金", 0.0, 0.0),
    _row("1002", "银行存款", 22052208.87, 20751212.11, 106036611.38, 107337608.14),
    _row("1002.001", "北京基本户202", 0.0, 0.0),
    _row("1002.011", "金华招行基本户801", 2047150.90, 746150.53, 106036607.77, 107337608.14),
    _row("1002.012", "金华招行资本金户403", 5057.97, 5061.58, 3.61, 0.0),
    _row("1002.013", "金华结构性存款账户", 20000000.0, 20000000.0),
    _row("1012", "其他货币资金", 1149617.68, 461130.20),
    _row("1012.012", "金华 AFO", 379790.36, 101085.58),
    _row("1012.013", "金华微信小程序", 21870.00, 12025.18),
    _row("1012.014", "金华小桔有车", 747957.32, 348019.44),
    _row("1012.014.01", "金华小桔有车", 490611.21, 232580.53),
    _row("1012.014.02", "金华小桔有车（收银台16554）", 257346.11, 115438.91),
]

LIVE_ACCOUNTS = _accounts(cash=["1001"], bank=["1002"], other=["1012"])


class TestProperty1LeafSumEqualsParent:
    """Property 1：叶子和 == 父科目额（活体实证数值）。"""

    @pytest.mark.parametrize(
        "prefix,expected_closing,expected_opening",
        [
            ("1002", 20751212.11, 22052208.87),
            ("1012", 461130.20, 1149617.68),
        ],
    )
    def test_leaf_sum_matches_parent(self, prefix, expected_closing, expected_opening):
        leaves = select_leaves(LIVE_SUBTREE)
        leaf = aggregate_leaves(leaves, [prefix])
        parent = parent_totals(LIVE_SUBTREE, prefix)
        assert parent["closing"] == pytest.approx(expected_closing, abs=0.005)
        assert leaf["closing"] == pytest.approx(expected_closing, abs=0.005)
        assert leaf["opening"] == pytest.approx(expected_opening, abs=0.005)

    def test_three_level_middle_node_excluded(self):
        """`1012.014` 是中间层，不得与其 .01/.02 同时计入（否则双算）。"""
        codes = {r.account_code for r in select_leaves(LIVE_SUBTREE)}
        assert "1012.014" not in codes
        assert {"1012.014.01", "1012.014.02"} <= codes

    def test_parent_check_diff_is_zero(self):
        check = e1.build_e1_parent_check(LIVE_SUBTREE, LIVE_ACCOUNTS)
        for code, info in check.items():
            assert info["diff"] == pytest.approx(0.0, abs=0.005), f"{code} 勾稽不平: {info}"


class TestProperty2DotBoundary:
    """Property 2：点号边界安全 —— 旧 `startswith` 实现会丢掉 `1002.1`。"""

    SIBLINGS = [
        _row("1002", "银行存款", 0.0, 300.0),
        _row("1002.1", "一号户", 0.0, 100.0),
        _row("1002.11", "十一号户", 0.0, 200.0),
    ]

    def test_both_siblings_are_leaves(self):
        codes = {r.account_code for r in select_leaves(self.SIBLINGS)}
        assert codes == {"1002.1", "1002.11"}, (
            "1002.1 被误判为非叶子 —— 这正是旧 `c.startswith(code)` 实现的缺陷"
        )

    def test_leaf_sum_still_equals_parent(self):
        leaves = select_leaves(self.SIBLINGS)
        assert aggregate_leaves(leaves, ["1002"])["closing"] == pytest.approx(300.0)

    def test_legacy_startswith_implementation_would_fail(self):
        """反向自检：复现旧实现，证明上面的断言不是恒真。"""
        all_codes = [r.account_code for r in self.SIBLINGS]

        def legacy_is_leaf(code: str) -> bool:
            return not any(c != code and c.startswith(code) for c in all_codes)

        legacy = {c for c in all_codes if legacy_is_leaf(c)}
        assert legacy == {"1002.11"}, "旧实现应只剩 1002.11（丢掉 1002.1）"
        assert legacy != {"1002.1", "1002.11"}


class TestProperty3ZeroBalanceAccountsKept:
    """Property 3：银行账户清单保留零余额账户（E1-10 完整性核对需要）。"""

    def test_account_list_keeps_zero_balance(self):
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        bank_leaves = slot_leaves[E1_SLOT_BANK]
        account_list = e1.build_e1_account_list(slot_leaves, {})
        assert len(account_list) == len(bank_leaves)
        codes = {a["code"] for a in account_list}
        assert "1002.001" in codes, "本年零余额账户被抹掉 → E1-10 完整性核对失效"
        zero = [a for a in account_list if a["isZeroBalance"]]
        assert zero and zero[0]["code"] == "1002.001"

    def test_detail_rows_do_filter_zero(self):
        """金额明细仍过滤全零行（与账户清单口径故意不同）。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        detail = e1.build_e1_detail_rows(slot_leaves, {})
        bank_codes = {r["code"] for r in detail[E1_SLOT_BANK]}
        assert "1002.001" not in bank_codes
        assert {"1002.011", "1002.012", "1002.013"} <= bank_codes

    def test_cash_slot_all_zero_yields_empty_detail_but_tb_zero(self):
        """1001 全零：明细为空，但 tb_values 仍给 0（不是缺键）。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        detail = e1.build_e1_detail_rows(slot_leaves, {})
        assert detail[E1_SLOT_CASH] == []
        tb = e1.build_e1_tb_values(slot_leaves)
        assert tb[f"{E1_SLOT_CASH}_closing"] == pytest.approx(0.0)


class TestTbValuesAndAdjudicationPrefill:
    def test_total_only_sums_three_base_slots(self):
        """合计只含三个基础槽 —— finance_co/digital 是其中项，加进去会双算。"""
        assert E1_TOTAL_SLOT_KEYS == (E1_SLOT_CASH, E1_SLOT_BANK, E1_SLOT_OTHER)
        accounts = _accounts(
            cash=["1001"], bank=["1002"], other=["1012"], finance_co=["1002"]
        )
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, accounts)
        tb = e1.build_e1_tb_values(slot_leaves)
        expected = 0.0 + 20751212.11 + 461130.20
        assert tb["total_closing"] == pytest.approx(expected, abs=0.005)

    def test_adjudication_prefill_shape_and_found_flag(self):
        accounts = _accounts(cash=["1001"], bank=["1002"], other=["1012"])
        # 本项目无数字货币科目 → found=False
        accounts.slots[E1_SLOT_DIGITAL] = _slot(E1_SLOT_DIGITAL, [], found=False)
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, accounts)
        pf = e1.build_e1_adjudication_prefill(slot_leaves, accounts)
        assert pf[E1_SLOT_BANK]["closing"] == pytest.approx(20751212.11, abs=0.005)
        assert pf[E1_SLOT_BANK]["accountCode"] == "1002"
        assert pf[E1_SLOT_DIGITAL]["found"] is False
        assert pf[E1_SLOT_DIGITAL]["closing"] == pytest.approx(0.0)


class TestProperty16RestrictedCandidateSet:
    """Property 16：受限候选集不跨族、不重不漏（扁平叶子清单口径）。"""

    def test_leaves_sum_equals_three_slot_total(self):
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        leaf_sum = sum(x["closing"] for x in rp["leaves"])
        tb = e1.build_e1_tb_values(slot_leaves)
        assert leaf_sum == pytest.approx(tb["total_closing"], abs=0.005)

    def test_flat_leaf_list_not_preaggregated_buckets(self):
        """🔴 必须下发**逐叶子**明细：预聚合是有损表示，叶子被人工改归属后
        前端无法重算被改动桶的余额。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        assert "leaves" in rp
        assert "buckets" not in rp, "预聚合的 buckets 会让人工改归属无法重算"
        for x in rp["leaves"]:
            assert set(x) == {"code", "name", "opening", "closing", "slot", "autoBucket"}

    def test_live_project_all_leaves_unclassified(self):
        """活体项目叶子名全是户名/渠道名 → `autoBucket` 全 None（宁缺勿造）。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        assert all(x["autoBucket"] is None for x in rp["leaves"]), (
            "活体叶子名不含受限关键字，不得被归类"
        )
        # 全零叶子（1001 / 1002.001）不下发，故只剩 7 个有金额的叶子
        assert {x["code"] for x in rp["leaves"]} == {
            "1002.011", "1002.012", "1002.013",
            "1012.012", "1012.013", "1012.014.01", "1012.014.02",
        }

    def test_zero_balance_leaves_not_shipped(self):
        """全零叶子不下发（活体 50+ 空账户会淹没「待归类」面板）。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        codes = {x["code"] for x in rp["leaves"]}
        assert "1001" not in codes and "1002.001" not in codes
        # 求和恒等式仍成立（跳过的都是 0）
        leaf_sum = sum(x["closing"] for x in rp["leaves"])
        tb = e1.build_e1_tb_values(slot_leaves)
        assert leaf_sum == pytest.approx(tb["total_closing"], abs=0.005)

    def test_restricted_leaf_carries_auto_bucket(self):
        subtree = [
            _row("1012", "其他货币资金", 0.0, 300.0),
            _row("1012.01", "银行承兑汇票保证金", 0.0, 100.0),
            _row("1012.02", "信用证保证金", 0.0, 200.0),
        ]
        accounts = _accounts(other=["1012"])
        slot_leaves = e1.build_e1_slot_leaves(subtree, accounts)
        rp = e1.build_e1_restricted_prefill(slot_leaves, accounts)
        by_code = {x["code"]: x for x in rp["leaves"]}
        assert by_code["1012.01"]["autoBucket"] == "bank_acceptance"
        assert by_code["1012.01"]["closing"] == pytest.approx(100.0)
        assert by_code["1012.02"]["autoBucket"] == "letter_of_credit"
        assert by_code["1012.02"]["closing"] == pytest.approx(200.0)

    def test_leaf_slot_is_reported(self):
        """每个叶子标注所属语义槽（cash/bank/other），供 UI 分组与溯源。"""
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        by_code = {x["code"]: x for x in rp["leaves"]}
        assert by_code["1002.011"]["slot"] == E1_SLOT_BANK
        assert by_code["1012.012"]["slot"] == E1_SLOT_OTHER

    def test_bucket_defs_are_shipped_for_frontend(self):
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, LIVE_ACCOUNTS)
        rp = e1.build_e1_restricted_prefill(slot_leaves, LIVE_ACCOUNTS)
        assert rp["bucketDefs"], "未下发桶定义 → 前端会自己抄一份中文标签"
        assert rp["source"]["report_row_code"] == E1_REPORT_ROW_CODE


class TestProperty4NoHardcodedAccountLeak:
    """Property 4：科目码字面量只允许出现在语义规格的兜底位。"""

    def _strip_comments(self, src: str) -> str:
        return re.sub(r"#[^\n]*", "", re.sub(r'"""[\s\S]*?"""', "", src))

    def test_render_module_has_no_account_code_literals(self):
        src = self._strip_comments(E1_RENDER_PATH.read_text(encoding="utf-8"))
        # 反向自检：确实读到了代码
        assert "build_e1_slot_leaves" in src
        hits = re.findall(r"['\"](100[12]|1012|1502)['\"]", src)
        assert hits == [], f"render 里出现硬编码科目码 {hits} —— 应由语义规格定位"

    def test_old_symbols_are_gone(self):
        for sym in ("_fetch_leaf_accounts", "_is_leaf", "_CASH_PREFIX",
                    "_BANK_PREFIX", "_OTHER_PREFIX"):
            assert not hasattr(e1, sym), f"{sym} 未删除（自造叶子逻辑应委托共享件）"

    def test_spec_declares_fallback_only_for_three_base_slots(self):
        """按需增设的两槽故意无兜底码（无一级标准科目，写死必取错）。"""
        by_key = {s.key: s for s in E1_MONETARY_FUND_SPEC.slots}
        assert by_key[E1_SLOT_CASH].fallback_standard_codes == ("1001",)
        assert by_key[E1_SLOT_BANK].fallback_standard_codes == ("1002",)
        assert by_key[E1_SLOT_OTHER].fallback_standard_codes == ("1012",)
        assert by_key[E1_SLOT_FINANCE_CO].fallback_standard_codes == ()
        assert by_key[E1_SLOT_DIGITAL].fallback_standard_codes == ()

    def test_spec_row_code_is_bs002(self):
        assert E1_MONETARY_FUND_SPEC.row_code == "BS-002" == E1_REPORT_ROW_CODE


class TestSemanticSlotExcludes:
    """否决词：防「存放财务公司款项」被 bank 的包含匹配吸走。"""

    def test_bank_excludes_finance_company(self):
        by_key = {s.key: s for s in E1_MONETARY_FUND_SPEC.slots}
        assert "财务公司" in by_key[E1_SLOT_BANK].exclude_names
        assert "中央银行" in by_key[E1_SLOT_BANK].exclude_names

    def test_cash_excludes_equivalents(self):
        by_key = {s.key: s for s in E1_MONETARY_FUND_SPEC.slots}
        assert "等价物" in by_key[E1_SLOT_CASH].exclude_names


class TestMultiSlotReportConfigFallback:
    """🔴 多槽规格下报表公式兜底层（层③）必须收窄 —— 真实 DB 实测的两个 P0。

    `BS-002 货币资金 = TB('1001')+TB('1002')+TB('1012')` 是**整条报表行**的科目集。
    改造前 `semantic_account_resolver` 把它整份分配给「按名称没命中的槽」，实测后果：

    ① `finance_co` / `digital`（准则解释15号「可增设」，`fallback=()`）各自拿到
       `['1001','1002','1012']` → `tb_values.finance_co_closing == digital_closing
       == total_closing`（两行都等于**货币资金全额**），一点「从四表库带入未审数」
       就把全额填进这两行，E1-1 合计还会把 digital 再加一遍；
    ② 项目 `2aa00f57` 无「库存现金」→ `cash` 拿到 `['1002','1012']`
       → `total = cash + bank + other` 把 1002/1012 算两遍：
       **8,935,072.24 vs 真值 4,467,536.12（虚增一倍）**。

    平台级修法 = 层③只对**单槽**规格生效（见
    `semantic_account_resolver.resolve_semantic_accounts` 的 `allow_report_config_tier`
    与 `test_semantic_account_resolver.py::TestChartTiers` 的 4 条守卫）。
    本类从 E1 侧钉死后果面：合计不得双算、未命中槽必须返空。

    **Validates: Requirements 2.1, 2.2, 2.4**
    """

    def test_total_not_double_counted_when_cash_missing(self):
        """项目无库存现金：cash 槽返空 → 合计 = bank + other，不得把 1002/1012 算两遍。"""
        subtree = [
            _row("1002", "银行存款", 848871.86, 327095.20),
            _row("1012", "其他货币资金", 52475713.77, 4140440.92),
        ]
        # 修好后的真实形态：cash 槽 found=False、codes 为空
        accounts = _accounts(bank=["1002"], other=["1012"])
        accounts.slots[E1_SLOT_CASH] = _slot(E1_SLOT_CASH, [], found=False)
        slot_leaves = e1.build_e1_slot_leaves(subtree, accounts)
        tb = e1.build_e1_tb_values(slot_leaves)
        assert tb[f"{E1_SLOT_CASH}_closing"] == pytest.approx(0.0)
        assert tb["total_closing"] == pytest.approx(4467536.12, abs=0.005)
        assert tb["total_opening"] == pytest.approx(53324585.63, abs=0.005)

    def test_legacy_broad_fallback_would_double_count(self):
        """反向自检：复现旧行为（cash 拿到 1002+1012）→ 合计必然虚增一倍。"""
        subtree = [
            _row("1002", "银行存款", 848871.86, 327095.20),
            _row("1012", "其他货币资金", 52475713.77, 4140440.92),
        ]
        legacy = _accounts(
            cash=["1002", "1012"],  # 旧层③把整条报表行的存在码全给了 cash
            bank=["1002"],
            other=["1012"],
        )
        slot_leaves = e1.build_e1_slot_leaves(subtree, legacy)
        tb = e1.build_e1_tb_values(slot_leaves)
        assert tb["total_closing"] == pytest.approx(8935072.24, abs=0.005), (
            "旧行为应复现虚增一倍的 8,935,072.24 —— 证明上一条断言不是恒真"
        )
        assert tb["total_closing"] != pytest.approx(4467536.12, abs=0.005)

    def test_finance_co_and_digital_stay_empty_without_own_account(self):
        """两个「可增设」槽在本项目无同名科目时必须返空，不得等于货币资金全额。"""
        accounts = _accounts(cash=["1001"], bank=["1002"], other=["1012"])
        for key in (E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL):
            accounts.slots[key] = _slot(key, [], found=False)
        slot_leaves = e1.build_e1_slot_leaves(LIVE_SUBTREE, accounts)
        tb = e1.build_e1_tb_values(slot_leaves)
        total = tb["total_closing"]
        assert total == pytest.approx(21212342.31, abs=0.005)
        for key in (E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL):
            assert tb[f"{key}_closing"] == pytest.approx(0.0)
            assert tb[f"{key}_closing"] != pytest.approx(total, abs=0.005)
        pf = e1.build_e1_adjudication_prefill(slot_leaves, accounts)
        for key in (E1_SLOT_FINANCE_CO, E1_SLOT_DIGITAL):
            assert pf[key]["found"] is False
            assert pf[key]["accountCodes"] == []
            assert pf[key]["closing"] == pytest.approx(0.0)

    def test_parent_check_slot_label_keeps_first_claimer(self):
        """`parent_check` 的 `slot` 标签取**首个**声明该码的槽（曾被最后一个槽覆盖）。"""
        accounts = _accounts(cash=["1001"], bank=["1002"], other=["1012"])
        # 构造一个也声明 1002 的后续槽（客户把数字货币挂在银行存款下的情形）
        accounts.slots[E1_SLOT_DIGITAL] = _slot(E1_SLOT_DIGITAL, ["1002"])
        check = e1.build_e1_parent_check(LIVE_SUBTREE, accounts)
        assert check["1001"]["slot"] == E1_SLOT_CASH
        assert check["1002"]["slot"] == E1_SLOT_BANK, (
            "后续槽不得覆盖 slot 标签（实测曾把 1001/1002/1012 都标成 digital）"
        )
        assert check["1012"]["slot"] == E1_SLOT_OTHER
