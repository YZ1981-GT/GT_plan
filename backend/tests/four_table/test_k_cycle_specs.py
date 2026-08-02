"""K 循环科目声明单一真源的守卫。

把立项时的 DB 只读实证钉进测试 —— 尤其是 K5「取错整个科目族」这条：
`2701` 在全部项目的 `account_chart` 中一律是**长期应付款**（L5 科目），
`2801` 才是预计负债。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Property 2, 3, 4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.k_cycle_specs import (
    EMPTY_REASON_NO_ACCOUNT,
    K6_LIABILITY_ROW_CODE_LISTED,
    K6_LIABILITY_ROW_CODE_SOE,
    K_CYCLE_SPECS,
    MISUSED_ACCOUNT_CODES,
    NONEXISTENT_ACCOUNT_CODES,
    balance_cycle_codes,
    get_k_cycle_spec,
    no_account_cycle_codes,
    pl_cycle_codes,
)
from app.services.four_table.pl_occurrence import AccountNature

_STRATEGY_DIR = Path("backend/app/routers/wp_render_strategies")

#: 立项实证：report_config 的 K 循环报表行（listed, soe, formula 引用的科目码或 None）
_EXPECTED_ROWS: dict[str, tuple[str, str, str | None]] = {
    "K3": ("BS-053", "BS-075", "2241"),
    "K4": ("BS-058", "BS-081", "2301"),
    "K5": ("BS-068", "BS-094", "2801"),
    "K6": ("BS-015", "BS-024", None),
    "K7": ("BS-069", "BS-095", "2401"),
    "K8": ("IS-004", "IS-022", "6601"),
    "K9": ("IS-005", "IS-023", "6602"),
    "K10": ("IS-010", "IS-030", "6117"),
    "K11": ("IS-017", "IS-038", None),
    "K12": ("IS-020", "IS-041", "6301"),
    "K13": ("IS-021", "IS-043", "6711"),
}


def test_all_k_cycles_declared():
    """K3~K13 十一个循环全部登记，无遗漏无多余。"""
    assert set(K_CYCLE_SPECS) == set(_EXPECTED_ROWS)
    assert len(K_CYCLE_SPECS) == 11


@pytest.mark.parametrize("wp_code", sorted(_EXPECTED_ROWS))
def test_row_codes_match_report_config_evidence(wp_code):
    """报表行编码与 `report_config` 实证一致。"""
    listed, soe, _acct = _EXPECTED_ROWS[wp_code]
    spec = K_CYCLE_SPECS[wp_code]
    assert spec.row_code_listed == listed
    assert spec.row_code_soe == soe
    # 两套准则的行号必须不同 —— 相同说明抄漏了一侧
    assert spec.row_code_listed != spec.row_code_soe


def test_row_codes_are_globally_unique():
    """同一 row_code 不得被两个循环声明（会互相抢公式）。"""
    seen: dict[str, str] = {}
    for code, spec in K_CYCLE_SPECS.items():
        for row in (spec.row_code_listed, spec.row_code_soe):
            assert row not in seen, f"{row} 被 {seen.get(row)} 与 {code} 同时声明"
            seen[row] = code
    # K6 负债侧两行也不得与任何已声明行冲突
    for row in (K6_LIABILITY_ROW_CODE_LISTED, K6_LIABILITY_ROW_CODE_SOE):
        assert row not in seen


# ─────────────────────────────────────────────────────────────────────────────
# Property 3：K5 不取长期应付款
# ─────────────────────────────────────────────────────────────────────────────


def test_k5_fallback_is_provisions_not_long_term_payables():
    """🔴 K5 兜底码必须是 2801 预计负债，绝不是 2701 长期应付款。"""
    spec = K_CYCLE_SPECS["K5"]
    assert spec.fallback_standard == "2801"
    assert spec.fallback_standard != "2701"
    assert spec.account_name == "预计负债"


def test_misused_code_registry_documents_why():
    """反向自检：误用码登记表必须说明 2701 的真实科目名。

    若有人把 K5 改回 2701，本断言配合上一条会立刻打红并给出原因。
    """
    assert MISUSED_ACCOUNT_CODES["2701"] == "长期应付款"


@pytest.mark.parametrize("wp_code", sorted(_EXPECTED_ROWS))
def test_no_spec_uses_misused_or_nonexistent_codes(wp_code):
    """任何循环的兜底码都不得是误用码或不存在的码。"""
    fb = K_CYCLE_SPECS[wp_code].fallback_standard
    if not fb:
        return
    assert fb not in MISUSED_ACCOUNT_CODES
    assert fb not in NONEXISTENT_ACCOUNT_CODES


# ─────────────────────────────────────────────────────────────────────────────
# Property 4：宁缺勿造
# ─────────────────────────────────────────────────────────────────────────────


def test_no_account_cycles_are_k4_and_k6():
    """三表零命中的循环恰好是 K4（其他流动负债）与 K6（持有待售）。"""
    assert sorted(no_account_cycle_codes()) == ["K4", "K6"]


@pytest.mark.parametrize("wp_code", ["K4", "K6"])
def test_no_account_cycles_declare_empty_fallback(wp_code):
    """宁缺勿造的循环不得有兜底码 —— 有兜底码就会去取不存在的科目。"""
    spec = K_CYCLE_SPECS[wp_code]
    assert spec.has_account is False
    assert spec.fallback_standard == ""
    assert "零命中" in spec.note


def test_empty_reason_is_actionable():
    """空结果说明文案必须告诉用户「怎么办」，而不是只说「没数据」。"""
    assert "手工录入" in EMPTY_REASON_NO_ACCOUNT
    assert "宁缺勿造" in EMPTY_REASON_NO_ACCOUNT


def test_nonexistent_codes_registry_covers_all_historical_hardcodes():
    """K4/K6 历史硬编码过的码全部登记（供源码守卫使用）。"""
    for code in ("2245", "2301", "1481", "2605", "2331"):
        assert code in NONEXISTENT_ACCOUNT_CODES


# ─────────────────────────────────────────────────────────────────────────────
# 损益 / 余额分流
# ─────────────────────────────────────────────────────────────────────────────


def test_pl_cycles_are_k8_to_k13():
    assert sorted(pl_cycle_codes(), key=lambda c: int(c[1:])) == [
        "K8",
        "K9",
        "K10",
        "K11",
        "K12",
        "K13",
    ]


def test_balance_cycles_are_k3_to_k7():
    assert sorted(balance_cycle_codes(), key=lambda c: int(c[1:])) == [
        "K3",
        "K4",
        "K5",
        "K6",
        "K7",
    ]


@pytest.mark.parametrize(
    ("wp_code", "nature"),
    [
        ("K8", AccountNature.EXPENSE),
        ("K9", AccountNature.EXPENSE),
        ("K10", AccountNature.INCOME),
        ("K11", AccountNature.EXPENSE),
        ("K12", AccountNature.INCOME),
        ("K13", AccountNature.EXPENSE),
    ],
)
def test_pl_nature_matches_account_direction(wp_code, nature):
    """费用/减值/营业外支出走借方；其他收益/营业外收入走贷方。"""
    assert K_CYCLE_SPECS[wp_code].nature is nature


@pytest.mark.parametrize("wp_code", ["K3", "K4", "K5", "K6", "K7"])
def test_balance_cycles_have_no_nature(wp_code):
    """资产负债类不经损益模块，nature 必须为 None。"""
    assert K_CYCLE_SPECS[wp_code].nature is None
    assert K_CYCLE_SPECS[wp_code].is_pl is False


# ─────────────────────────────────────────────────────────────────────────────
# spec_for（按准则选行号）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("standards", "expected_row"),
    [
        (["listed_standalone", "listed", "standalone"], "BS-068"),
        (["soe_standalone", "soe", "standalone"], "BS-094"),
        (["listed_consolidated"], "BS-068"),
        (["soe_consolidated"], "BS-094"),
        ([], "BS-094"),  # 准则未知 → 用国企行号（在册项目绝大多数是 soe）
        (None, "BS-094"),
    ],
)
def test_spec_for_selects_row_code_by_standard(standards, expected_row):
    """🔴 两套准则的 row_code 本身就不同，必须在声明层先选对行号。"""
    assert K_CYCLE_SPECS["K5"].spec_for(standards).row_code == expected_row


def test_spec_for_carries_fallback():
    spec = K_CYCLE_SPECS["K5"].spec_for(["soe_standalone"])
    assert spec.fallback_gross == ("2801",)
    assert spec.fallback_provision == ()


@pytest.mark.parametrize("wp_code", ["K4", "K6"])
def test_spec_for_no_account_cycles_has_empty_fallback(wp_code):
    """宁缺勿造循环的 ReportLineAccountSpec 不带兜底码。"""
    spec = K_CYCLE_SPECS[wp_code].spec_for(["soe_standalone"])
    assert spec.fallback_gross == ()


def test_get_k_cycle_spec_is_case_insensitive():
    assert get_k_cycle_spec("k5") is K_CYCLE_SPECS["K5"]
    assert get_k_cycle_spec(" K13 ") is K_CYCLE_SPECS["K13"]
    assert get_k_cycle_spec("K99") is None
    assert get_k_cycle_spec("") is None


# ─────────────────────────────────────────────────────────────────────────────
# 源码守卫（Property 5 后端侧 + Property 4 源码侧）
# ─────────────────────────────────────────────────────────────────────────────


def _strip_comments(src: str) -> str:
    """去掉 Python 注释与三引号 docstring（踩坑说明里会写反例字样）。"""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


_STRATEGY_FILES: dict[str, str] = {
    "K3": "_k3_other_payables.py",
    "K4": "_k4_other_current_liabilities.py",
    "K5": "_k5_provisions.py",
    "K6": "_k6_held_for_sale.py",
    "K7": "_k7_deferred_income.py",
    "K8": "_k8_selling_expenses.py",
    "K9": "_k9_admin_expenses.py",
    "K10": "_k10_other_income.py",
    "K11": "_k11_asset_impairment_loss.py",
    "K12": "_k12_non_operating_income.py",
    "K13": "_k13_non_operating_expense.py",
}


def test_strategy_files_exist():
    """反向自检：文件名映射有效，否则下面的源码断言全是空转。"""
    for wp_code, fn in _STRATEGY_FILES.items():
        assert (_STRATEGY_DIR / fn).exists(), f"{wp_code} 策略文件不存在: {fn}"


def test_strip_comments_actually_strips():
    """反向自检：`_strip_comments` 确实生效（否则源码断言恒不触发）。"""
    sample = '"""docstring 里提到 debit - credit 反例"""\nx = 1  # 注释里也提 2701\n'
    stripped = _strip_comments(sample)
    assert "debit - credit" not in stripped
    assert "2701" not in stripped
    assert "x = 1" in stripped


@pytest.mark.parametrize("wp_code", sorted(_STRATEGY_FILES, key=lambda c: int(c[1:])))
def test_no_pl_net_difference_in_strategy_source(wp_code):
    """Property 5：取数源码不得出现 `debit - credit` 形态（恒零）。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES[wp_code]).read_text("utf-8"))
    patterns = [
        # 费用类写法
        r"debit\s*-\s*credit",
        r"debit_amount\s*-\s*credit_amount",
        r'\["debit"\]\s*-\s*\w+\["credit"\]',
        # 🔴 收益类是反向写法（K10 6117 / K12 6301），同样恒零
        r"credit\s*-\s*debit",
        r"credit_amount\s*-\s*debit_amount",
        r'\["credit"\]\s*-\s*\w+\["debit"\]',
    ]
    for pat in patterns:
        assert not re.search(pat, src), f"{wp_code} 源码含损益净额表达式: {pat}"


@pytest.mark.parametrize("wp_code", ["K4", "K6"])
def test_no_nonexistent_codes_in_strategy_source(wp_code):
    """Property 4 源码侧：宁缺勿造循环不得再出现不存在的科目码字面量。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES[wp_code]).read_text("utf-8"))
    for code in NONEXISTENT_ACCOUNT_CODES:
        assert f'"{code}"' not in src, f"{wp_code} 源码含不存在的科目码 {code}"
        assert f"'{code}'" not in src, f"{wp_code} 源码含不存在的科目码 {code}"


def test_k5_source_has_no_long_term_payable_code():
    """Property 3 源码侧：K5 源码不得出现 2701（长期应付款）。"""
    src = _strip_comments((_STRATEGY_DIR / _STRATEGY_FILES["K5"]).read_text("utf-8"))
    assert '"2701"' not in src
    assert "'2701'" not in src
