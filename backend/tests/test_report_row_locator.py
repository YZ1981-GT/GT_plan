"""报表关键行按行名定位（spec citar-report-analysis 任务 1）。

用 ``report_config_seed.json`` 四套模板的真实行名验证：每个语义键在每套模板里都定位到
「行名就是这一项」的那一行，而不是编码相同的别的行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.report_row_locator import SEMANTIC_LABELS, locate, normalize_row_name

_SEED = Path(__file__).resolve().parents[1] / "data" / "report_config_seed.json"
_STANDARDS = ("soe_standalone", "listed_standalone", "soe_consolidated", "listed_consolidated")
_BS_KEYS = ("cash", "accounts_receivable", "inventory", "current_assets", "total_assets",
            "current_liabilities", "total_liabilities", "total_equity")
_IS_KEYS = ("revenue", "cost_of_sales", "profit_before_tax", "income_tax", "net_profit")


def _rows(standard: str, report_type: str) -> list[dict]:
    for block in json.loads(_SEED.read_text(encoding="utf-8")):
        if block["applicable_standard"] == standard and block["report_type"] == report_type:
            return block["rows"]
    raise AssertionError(f"种子里没有 {standard} / {report_type}")


#: 期望的规范化行名（定位结果的行名规范化后必须等于其中之一）
_EXPECTED = {
    "cash": {"货币资金"},
    "accounts_receivable": {"应收账款"},
    "inventory": {"存货"},
    "current_assets": {"流动资产合计"},
    "total_assets": {"资产总计"},
    "current_liabilities": {"流动负债合计"},
    "total_liabilities": {"负债合计"},
    "total_equity": {"所有者权益合计", "股东权益合计"},
    "revenue": {"营业收入"},
    "cost_of_sales": {"营业成本"},
    "profit_before_tax": {"利润总额"},
    "income_tax": {"所得税费用"},
    "net_profit": {"净利润"},
    "equity_ending": {"本年年末余额"},
}


@pytest.mark.parametrize("standard", _STANDARDS)
@pytest.mark.parametrize("key", _BS_KEYS)
def test_balance_sheet_keys(standard, key):
    row = locate(_rows(standard, "balance_sheet"), key)
    assert row is not None, f"{standard} 资产负债表找不到 {SEMANTIC_LABELS[key]}"
    assert normalize_row_name(row["row_name"]) in _EXPECTED[key], row


@pytest.mark.parametrize("standard", _STANDARDS)
@pytest.mark.parametrize("key", _IS_KEYS)
def test_income_statement_keys(standard, key):
    row = locate(_rows(standard, "income_statement"), key)
    assert row is not None, f"{standard} 利润表找不到 {SEMANTIC_LABELS[key]}"
    assert normalize_row_name(row["row_name"]) in _EXPECTED[key], row


@pytest.mark.parametrize("standard", _STANDARDS)
def test_equity_ending(standard):
    row = locate(_rows(standard, "equity_statement"), "equity_ending")
    assert row is not None
    assert normalize_row_name(row["row_name"]) == "本年年末余额"


@pytest.mark.parametrize("standard", ("soe_standalone", "listed_standalone"))
def test_hardcoded_codes_would_hit_wrong_rows(standard):
    """反证：旧代码写死的编码在现行模板里是别的行（定位器存在的理由）。"""
    bs = {r["row_code"]: r for r in _rows(standard, "balance_sheet")}
    is_ = {r["row_code"]: r for r in _rows(standard, "income_statement")}
    assert normalize_row_name(bs["BS-019"]["row_name"]) != "流动资产合计"
    assert normalize_row_name(bs["BS-001"]["row_name"]) != "货币资金"
    assert "净利润" not in normalize_row_name(is_["IS-019"]["row_name"])
    assert "PL-001" not in is_


def test_net_profit_skips_sub_items():
    """「1.归属于母公司所有者的净利润」「其中：持续经营净利润」不能当净利润。"""
    rows = [
        {"row_name": "1.归属于母公司所有者的净利润", "indent_level": 1},
        {"row_name": "五、净利润（净亏损以“－”号填列）", "indent_level": 0},
    ]
    assert locate(rows, "net_profit") is rows[1]


def test_net_profit_sub_item_alone_is_not_net_profit():
    """没有顶层净利润行时，名字以「净利润」开头的子项也不能顶替（单独钉住顶层判据）。"""
    rows = [{"row_name": "其中：净利润（归属于母公司）", "indent_level": 1}]
    assert locate(rows, "net_profit") is None


def test_equity_total_ignores_parent_attributable():
    rows = [
        {"row_name": "归属于母公司所有者权益合计", "indent_level": 0},
        {"row_name": "所有者权益合计", "indent_level": 0},
    ]
    assert locate(rows, "total_equity") is rows[1]


def test_not_found_returns_none():
    assert locate([{"row_name": "流动资产：", "indent_level": 0}], "current_assets") is None


@pytest.mark.parametrize("raw, norm", [
    ("四、利润总额（亏损总额以“－”号填列）", "利润总额"),
    ("减： 所得税费用", "所得税费用"),
    ("  其中：营业收入", "营业收入"),
    ("股东（或所有者）权益合计", "股东权益合计"),
    ("△ 2.提取一般风险准备", "提取一般风险准备"),
])
def test_normalize(raw, norm):
    assert normalize_row_name(raw) == norm


# ─── 跨表核对取数（logic_check.build_report_row_cache）─────────────────────────

def _with_amounts(rows: list[dict], amounts: dict[str, str]) -> list[dict]:
    """给种子行按规范化行名填金额，其余行填一个干扰值（编码相同的错行一旦被取到就会露馅）。"""
    out = []
    for r in rows:
        norm = normalize_row_name(r["row_name"])
        out.append({**r, "current_period_amount": amounts.get(norm, "7777")})
    return out


@pytest.mark.parametrize("standard", ("soe_standalone", "listed_standalone"))
def test_cross_check_cache_uses_real_rows(standard):
    from decimal import Decimal

    from app.services.formula_management.logic_check import build_report_row_cache

    bs = _with_amounts(_rows(standard, "balance_sheet"), {
        "资产总计": "1000", "负债合计": "600", "所有者权益合计": "400", "股东权益合计": "400",
        "货币资金": "50",
    })
    is_ = _with_amounts(_rows(standard, "income_statement"), {
        "营业收入": "2000", "营业成本": "1500", "利润总额": "100", "所得税费用": "25", "净利润": "75",
    })
    eq = _with_amounts(_rows(standard, "equity_statement"), {"本年年末余额": "400"})
    cache = build_report_row_cache(bs, is_, eq)
    assert cache["assets_total"] == Decimal("1000")
    assert cache["equity_total"] == Decimal("400")
    assert cache["BS-001"] == Decimal("50")       # 货币资金，不是「流动资产：」
    assert cache["IS-001"] == Decimal("2000")     # 营业收入
    assert cache["IS-002"] == Decimal("1500")     # 营业成本
    assert cache["IS-017"] == Decimal("100")      # 利润总额，不是「▲赔付支出净额」
    assert cache["IS-018"] == Decimal("25")
    assert cache["IS-019"] == Decimal("75")       # 净利润，不是「营业利润」「保单红利支出」
    assert cache["EQ-ENDING"] == Decimal("400")   # 权益变动表年末（原先恒 0）
    assert cache["IS-003"] == Decimal("0")        # 无独立毛利行，不取编码 IS-003 的别的行
