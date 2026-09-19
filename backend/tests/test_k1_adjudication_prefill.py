"""K1 render: 科目定位 / 叶子取数 / adjudication_prefill 契约.

修的两条历史错误（DB 只读实证，项目 `0ec33ac9`/2025）都在本文件钉死：

1. 备抵取整个 `1231` → 含应收账款坏账 26,401,719.77，合计 28,464,225.16；
   正确口径 `1231.03` = 900,217.36。
2. 只取最深层级 → 丢一级叶子 `1221.11`(3,597,359.45) / `1221.12`(55,035,942.52)，
   原值 211,252,631.06；正确叶子口径 269,885,933.03（= 父科目 `1221` 期末）。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 1.3, 2.1~2.4, 3.1~3.3, 3.5 / Property 1, 2, 3, 4, 10
"""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_other_receivables import (
    K1_ACCOUNT_SPEC,
    K1_DISCLOSURE_SHEET_LISTED,
    K1_DISCLOSURE_SHEET_SOE,
    K1_REPORT_ROW_CODE,
    K1_SHEETS,
    _build_adjudication_prefill,
    _build_fs_reconciliation,
    _build_tb_values,
    _classify_nature,
    _has_persisted_adjudication,
)
from app.services.four_table.leaf_aggregation import LeafRow, select_leaves
from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_REPORT,
    ReportLineAccounts,
)

# ── 实测 fixture ─────────────────────────────────────────────────────────────

REC_CLOSING = 269885933.03
REC_OPENING = 150302795.09
DEEPEST_ONLY_CLOSING = 211252631.06     # 旧「最深层级」口径（错）
PROV_CLOSING = 900217.36                # 1231.03（对）
PROV_OPENING = 639230.01
WHOLE_1231_CLOSING = 28464225.16        # 整个 1231（错，含应收账款）
DIVIDEND_CLOSING = 21000000.00          # 1131 应收股利
MARGIN_DEPOSIT_CLOSING = 55035942.52    # 1221.12 保证金及押金


def _row(code, name, opening, closing, direction="debit", debit=0.0, credit=0.0):
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=opening,
        closing=closing,
        debit=debit,
        credit=credit,
        direction=direction,
        dataset_id="ds",
    )


def _leaves() -> list[LeafRow]:
    """项目 0ec33ac9 / 2025 的真实科目树（1221 / 1231 / 1131 / 1132）→ 叶子。"""
    rows = [
        _row("1221", "其他应收款", REC_OPENING, REC_CLOSING,
             debit=1601611866.71, credit=1482028728.77),
        _row("1221.11", "其他应收款_个人往来", 1022267.86, 3597359.45),
        _row("1221.12", "其他应收款_保证金及押金", 52568902.81, MARGIN_DEPOSIT_CLOSING),
        _row("1221.13", "其他应收款_代收代付款项", 93264.30, 93264.30),
        _row("1221.13.01", "其他应收款_代收代付款项_代垫职工款项", 93264.30, 93264.30),
        _row("1221.15", "其他应收款_资金往来", 87626505.29, 207815404.88),
        _row("1221.15.02", "其他应收款_资金往来_短期借款", 48200000.00, 84800000.00),
        _row("1221.15.04", "其他应收款_资金往来_应收利息", 30444.33, 37808.48),
        _row("1221.15.06", "其他应收款_资金往来_应收上存", 1317639.94, 86373080.62),
        _row("1221.15.08", "其他应收款_资金往来_应收利润", 38078421.02, 36604515.78),
        _row("1221.98", "其他应收款_其他", 8991854.83, 3343961.88),
        _row("1221.98.03", "其他应收款_其他_经营类往来款", 218269.57, 379612.31),
        _row("1221.98.08", "其他应收款_其他_仓储配送费", 58240.00, -10500.00, "credit"),
        _row("1221.98.91", "其他应收款_其他_保理追加收购款", 7027572.00, 2802009.32),
        _row("1221.98.99", "其他应收款_其他_其他", 1687773.26, 172840.25),
        _row("1231", "坏账准备", 15728468.72, WHOLE_1231_CLOSING, "credit"),
        _row("1231.01", "坏账准备_应收票据", 3037132.25, 1162288.03, "credit"),
        _row("1231.02", "坏账准备_应收账款", 12052106.46, 26401719.77, "credit"),
        _row("1231.03", "坏账准备_其他应收款", PROV_OPENING, PROV_CLOSING, "credit"),
        _row("1231.05", "坏账准备_长期应收款", 0.0, 0.0, "credit"),
        _row("1131", "应收股利", 0.0, DIVIDEND_CLOSING, debit=DIVIDEND_CLOSING),
        _row("1132", "应收利息", 0.0, 0.0),
    ]
    return select_leaves(rows)


def _accounts(*, provision_exact=True, signed=True) -> ReportLineAccounts:
    """soe_standalone 解析结果（`BS-009 = TB('1221') - TB('1231-03') + TB('1131')`）。"""
    return ReportLineAccounts(
        gross=["1221"],
        provision=["1231.03"] if provision_exact else ["1231"],
        gross_standard=["1221"],
        provision_standard=["1231-03"],
        extra={"1131": ["1131"], "1132": ["1132"]},
        signed_codes=[("1221", 1), ("1231-03", -1), ("1131", 1)] if signed else [],
        formula="TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')",
        row_code="BS-009",
        resolved_from=RESOLVED_FROM_REPORT,
        provision_resolved_from=RESOLVED_FROM_REPORT,
        provision_exact=provision_exact,
    )


# ── 既有契约（保留） ─────────────────────────────────────────────────────────


def test_classify_nature_keywords():
    assert _classify_nature("履约保证金") == "margin"
    assert _classify_nature("房屋押金") == "deposit"
    assert _classify_nature("员工备用金") == "petty"
    assert _classify_nature("关联方往来款") == "intercompany"
    assert _classify_nature("其他应收") == "other-nature"


def test_has_persisted_adjudication_detects_nonzero_unadj():
    assert not _has_persisted_adjudication({})
    assert not _has_persisted_adjudication({"K1-1-receivable-r0-unadj": {"remark": "0"}})
    assert _has_persisted_adjudication({"K1-1-receivable-r0-unadj": {"remark": "100.5"}})
    assert not _has_persisted_adjudication({"K1-1-audit-note": {"remark": "说明"}})


def test_module_declares_bs009_row_code():
    """报表行次常量必须是 DB 实证值 BS-009（改错会让整条链路解析落空）。"""
    assert K1_REPORT_ROW_CODE == "BS-009"
    assert K1_ACCOUNT_SPEC.row_code == "BS-009"
    assert K1_ACCOUNT_SPEC.extra_standard_codes == ("1131", "1132")


# ── Property 1 / 2：叶子口径 + 备抵范围 ─────────────────────────────────────


def test_prefill_gross_equals_parent_total_not_deepest_only():
    prefill = _build_adjudication_prefill(_leaves(), _accounts())
    rec = prefill["receivable_total"]
    assert round(rec["closing"], 2) == REC_CLOSING
    assert round(rec["opening"], 2) == REC_OPENING
    # 反向钉子：旧「最深层级」口径必须不再出现
    assert round(rec["closing"], 2) != DEEPEST_ONLY_CLOSING


def test_prefill_provision_is_other_receivable_subaccount_only():
    prefill = _build_adjudication_prefill(_leaves(), _accounts())
    bd = prefill["bad_debt_total"]
    assert round(bd["closing"], 2) == PROV_CLOSING
    assert round(bd["opening"], 2) == PROV_OPENING
    # 反向钉子：不得等于整个 1231（含应收账款 26,401,719.77）
    assert round(bd["closing"], 2) != WHOLE_1231_CLOSING


def test_prefill_nature_includes_margin_deposit_bucket():
    """一级叶子 1221.12 必须进 margin 桶（旧实现整段丢掉 → 该桶恒 0）。"""
    prefill = _build_adjudication_prefill(_leaves(), _accounts())
    nature = prefill["nature"]
    assert "margin" in nature
    assert round(nature["margin"]["closing"], 2) == MARGIN_DEPOSIT_CLOSING
    # 性质各桶期末之和 == 原值合计（叶子无遗漏）
    total = sum(v["closing"] for v in nature.values())
    assert round(total, 2) == REC_CLOSING


def test_prefill_portfolio_falls_back_to_aging_bucket():
    prefill = _build_adjudication_prefill(_leaves(), _accounts())
    assert round(prefill["portfolio"]["aging"]["closing"], 2) == REC_CLOSING
    assert round(prefill["portfolio_provision"]["aging"]["closing"], 2) == PROV_CLOSING


def test_provision_name_filter_applied_only_on_wide_prefix():
    """反解退化为宽前缀 `1231` 时叠名称过滤 → 只剩「坏账准备_其他应收款」。"""
    wide = _build_adjudication_prefill(_leaves(), _accounts(provision_exact=False))
    assert round(wide["bad_debt_total"]["closing"], 2) == PROV_CLOSING
    # 反向自检：不过滤时会把整个 1231 的子科目都算进来
    leaves = _leaves()
    from app.services.four_table.leaf_aggregation import aggregate_leaves

    unfiltered = aggregate_leaves(leaves, ["1231"], absolute=True)["closing"]
    assert round(unfiltered, 2) == WHOLE_1231_CLOSING


# ── Property 10：报表口径合计按公式符号加权 ─────────────────────────────────


def test_fs_reconciliation_uses_formula_signs():
    fs = _build_fs_reconciliation(_leaves(), _accounts())
    assert round(fs["dividend"], 2) == DIVIDEND_CLOSING
    assert round(fs["interest"], 2) == 0.0
    expected = REC_CLOSING - PROV_CLOSING + DIVIDEND_CLOSING
    assert round(fs["report_total"], 2) == round(expected, 2)


def test_fs_reconciliation_default_caliber_without_formula():
    """公式缺失（fallback 口径）时退化为「原值 − 备抵 + 附加」。"""
    fs = _build_fs_reconciliation(_leaves(), _accounts(signed=False))
    expected = REC_CLOSING - PROV_CLOSING + DIVIDEND_CLOSING + 0.0
    assert round(fs["report_total"], 2) == round(expected, 2)


def test_prefill_carries_fs_reconciliation():
    prefill = _build_adjudication_prefill(_leaves(), _accounts())
    assert set(prefill["fs_reconciliation"]) == {"interest", "dividend", "report_total"}


# ── Property 3 / 4：空输入与手工优先 ────────────────────────────────────────


def test_prefill_empty_when_no_leaves():
    assert _build_adjudication_prefill([], _accounts()) == {}


def test_prefill_empty_when_all_zero():
    zeros = select_leaves([_row("1221", "其他应收款", 0.0, 0.0)])
    assert _build_adjudication_prefill(zeros, _accounts()) == {}


def test_tb_values_keys_match_frontend_contract():
    """键名与 `GtK1OtherReceivables._loadTbData` 读取的字段逐字对齐。"""
    tb = _build_tb_values(
        _leaves(),
        _accounts(),
        {
            "1221": {"unadjusted": 1356207261.45, "audited": 1356207261.45},
            "1231-03": {"unadjusted": -9544930.32, "audited": -9544930.32},
        },
    )
    for key in (
        "receivable_unadjusted",
        "receivable_audited",
        "bad_debt_unadjusted",
        "bad_debt_audited",
        "receivable_unadjusted_opening",
        "receivable_unadjusted_closing",
        "bad_debt_unadjusted_opening",
        "bad_debt_unadjusted_closing",
    ):
        assert key in tb, key
    assert round(tb["receivable_unadjusted_closing"], 2) == REC_CLOSING
    assert round(tb["bad_debt_unadjusted_closing"], 2) == PROV_CLOSING
    # trial_balance 侧备抵取绝对值（备抵在 TB 里可能是负数）
    assert round(tb["bad_debt_unadjusted"], 2) == 9544930.32


def test_tb_values_trial_balance_longest_prefix_wins():
    """`1231` 与 `1231-03` 并存时按最长前缀归属，防双计。"""
    tb = _build_tb_values(
        _leaves(),
        _accounts(),
        {
            "1231-03": {"unadjusted": 100.0, "audited": 100.0},
            "1221": {"unadjusted": 5.0, "audited": 5.0},
        },
    )
    assert tb["bad_debt_unadjusted"] == 100.0
    assert tb["receivable_unadjusted"] == 5.0


# ── 披露 sheet 名（源 xlsx 逐字） ───────────────────────────────────────────


def test_disclosure_sheet_names_match_source_xlsx_literals():
    """上市侧前半角后全角；国企侧是「国企」不是「国有企业」。"""
    assert K1_DISCLOSURE_SHEET_LISTED == "附注披露信息(上市公司）"
    assert K1_DISCLOSURE_SHEET_SOE == "附注披露信息（国企）"
    names = [s["sheet_name"] for s in K1_SHEETS]
    assert K1_DISCLOSURE_SHEET_LISTED in names
    assert K1_DISCLOSURE_SHEET_SOE in names
    # 反向自检：旧的错误写法不得残留
    assert "附注披露信息（上市公司）" not in names
    assert "附注披露信息（国有企业）" not in names


# ─────────────────── K1-3 坏账准备 render seed（k1-extraction-chain-and-note-alignment） ───────────────────
#
# spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
# Requirements 2.1, 2.4 / Property 3
#
# 复用本文件顶部的 `_leaves()` fixture（真实项目 0ec33ac9/2025 科目树）：
# 备抵叶子仅 `1231.03`（期初 639230.01 / 期末 900217.36），期末 - 期初 = 260987.35
# 为净增（贷方计提），故应归入 `currentProvision`。


def test_k1_bad_debt_seed_from_real_fixture_isolates_other_receivable():
    from app.services.four_table.k1_detail_seed import build_k1_bad_debt_seed_from_tb

    accounts = _accounts()
    p = build_k1_bad_debt_seed_from_tb(_leaves(), accounts.provision)
    assert p is not None
    portfolio = next(r for r in p["mainRows"] if r["category"] == "portfolio")
    assert portfolio["priorBook"] == PROV_OPENING
    assert portfolio["currentBook"] == PROV_CLOSING
    # 不得混入 1231.02（应收账款坏账）
    assert portfolio["currentBook"] != WHOLE_1231_CLOSING


def test_k1_bad_debt_seed_fail_open_on_empty_provision():
    from app.services.four_table.k1_detail_seed import build_k1_bad_debt_seed_from_tb

    assert build_k1_bad_debt_seed_from_tb([], []) is None
    assert build_k1_bad_debt_seed_from_tb(_leaves(), []) is None


def test_render_seeds_k1_3_when_no_manual_data():
    """characterization：render 在无手工 K1-3 数据时写入 seed，
    且不影响既有 `adjudication_prefill` / `tb_values` / `tb_source_codes` 输出键。"""
    from app.services.four_table.k1_detail_seed import (
        K1_BAD_DEBT_ITEM_ID,
        build_k1_bad_debt_seed_from_tb,
        seed_k1_bad_debt,
    )

    accounts = _accounts()
    responses_snapshot: dict = {}
    p = build_k1_bad_debt_seed_from_tb(_leaves(), accounts.provision)
    assert seed_k1_bad_debt(responses_snapshot, p) is True
    assert K1_BAD_DEBT_ITEM_ID in responses_snapshot


def test_render_seed_skipped_when_manual_k1_3_present():
    import json as _json

    from app.services.four_table.k1_detail_seed import (
        K1_BAD_DEBT_ITEM_ID,
        build_k1_bad_debt_seed_from_tb,
        seed_k1_bad_debt,
    )

    manual = {"version": 2, "mainRows": [
        {"category": "portfolio", "isSubRow": False, "priorBook": 42.0},
    ]}
    responses_snapshot = {
        K1_BAD_DEBT_ITEM_ID: {"conclusion": "", "remark": _json.dumps(manual)}
    }
    accounts = _accounts()
    p = build_k1_bad_debt_seed_from_tb(_leaves(), accounts.provision)
    assert seed_k1_bad_debt(responses_snapshot, p) is False
    assert _json.loads(responses_snapshot[K1_BAD_DEBT_ITEM_ID]["remark"]) == manual
