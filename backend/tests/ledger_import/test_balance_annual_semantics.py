"""余额表「年度优先 + 月度兜底」语义 — spec balance-import-annual-column-semantics。

见 .kiro/specs/balance-import-annual-column-semantics/{requirements,design,tasks}.md。

本文件贯穿 Wave0(安全网基线) → Wave1(识别层) → Wave2(分类层) → Wave3(转换层)
→ Wave4(SubmitGate) 的单测与属性测试。

三个映射真源（design §A/B/C 冻结清单，Task 1.2）：
  - A  identifier._MERGED_HEADER_MAPPING（点号合并表头，_match_header 最先命中）
  - B  data/ledger_recognition_rules.json::column_aliases（单行别名，_rebuild_aliases 读取）
  - C  smart_import_engine._MERGED_HEADER_MAP（legacy 参照，已正确区分 year_*）

分层期望终态（design §C）：
  KEY_COLUMNS["balance"]       = {account_code, year_opening_debit, year_opening_credit,
                                  year_debit, year_credit, closing_balance}
  RECOMMENDED 含               = {opening_balance, opening_debit, opening_credit,
                                  debit_amount, credit_amount, closing_debit, closing_credit, ...}

SubmitGate CRITICAL_COLUMNS["balance"] 期望终态（design §F）——任一满足即过：
  {account_code, opening_balance} / {account_code, closing_balance}
  / {account_code, debit_amount, credit_amount}
  / {account_code, year_opening_debit, year_opening_credit}
  / {account_code, closing_debit, closing_credit}
  / {account_code, year_debit, year_credit}
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ledger_import.converter import convert_balance_rows

# ---------------------------------------------------------------------------
# Task 1.2 — 冻结分类/校验真源期望集合（供后续波次断言引用）
# ---------------------------------------------------------------------------

EXPECTED_KEY_COLUMNS_BALANCE = {
    "account_code",
    "year_opening_debit",
    "year_opening_credit",
    "year_debit",
    "year_credit",
    "closing_balance",
}

EXPECTED_RECOMMENDED_SUBSET_BALANCE = {
    "opening_balance",
    "opening_debit",
    "opening_credit",
    "debit_amount",
    "credit_amount",
    "closing_debit",
    "closing_credit",
}

EXPECTED_SUBMITGATE_CRITICAL_BALANCE = [
    {"account_code", "opening_balance"},
    {"account_code", "closing_balance"},
    {"account_code", "debit_amount", "credit_amount"},
    {"account_code", "year_opening_debit", "year_opening_credit"},
    {"account_code", "closing_debit", "closing_credit"},
    {"account_code", "year_debit", "year_credit"},
]


# ---------------------------------------------------------------------------
# Task 1.1 — converter 月度-only 行为基线锚点（不变量，贯穿全波次绿）
#
# 月度-only 输入（无 year_*）在「年度优先 + 月度兜底」下必须逐值等价于变更前，
# 因 _first_decimal(None, month_value) == month_value。此锚点是 Property 4 的基石。
# ---------------------------------------------------------------------------

_MONTH_ONLY_ROW = {
    "account_code": "1001",
    "account_name": "库存现金",
    "opening_debit": "100",
    "opening_credit": "0",
    "debit_amount": "50",
    "credit_amount": "30",
    "closing_debit": "120",
    "closing_credit": "0",
}


def test_month_only_conversion_baseline_anchor():
    """月度-only 余额行的落库结果（不变量基线）。

    资产类 1001 库存现金（借方正常）：期初 100 借、本期借 50/贷 30、期末 120 借。
    """
    balance_rows, aux_rows = convert_balance_rows([dict(_MONTH_ONLY_ROW)])
    assert aux_rows == []
    assert len(balance_rows) == 1
    r = balance_rows[0]
    assert r["account_code"] == "1001"
    assert r["opening_balance"] == Decimal("100")
    assert r["debit_amount"] == Decimal("50")
    assert r["credit_amount"] == Decimal("30")
    assert r["closing_balance"] == Decimal("120")
    assert r["opening_direction"] == "debit"
    assert r["closing_direction"] == "debit"


def test_month_only_net_opening_direction_preserved():
    """净额+方向模式（无分列）月度-only：负债类贷方余额归一为正数（不变量）。"""
    row = {
        "account_code": "2202",
        "account_name": "应付账款",
        "opening_balance": "200",
        "direction": "贷",
        "debit_amount": "0",
        "credit_amount": "80",
        "closing_balance": "280",
    }
    balance_rows, _ = convert_balance_rows([row])
    r = balance_rows[0]
    # 负债贷方：opening_balance 净额 200 贷 → 归一为类别自然正数 200
    assert r["opening_balance"] == Decimal("200")
    assert r["opening_direction"] == "credit"
    assert r["credit_amount"] == Decimal("80")


# ---------------------------------------------------------------------------
# Wave1 — 识别层映射（Task 2.3）
# ---------------------------------------------------------------------------

from app.services.ledger_import.identifier import (  # noqa: E402
    _match_header,
    _match_merged_header,
    reload_rules,
    _rebuild_aliases,
)


@pytest.fixture(autouse=True)
def _reload_identifier_rules():
    """确保每个测试用最新 JSON 规则（模块导入已 bootstrap，此处显式重载防污染）。"""
    reload_rules()
    _rebuild_aliases()
    yield


# ---- Property 8: 点号合并表头区分年度 ----

@pytest.mark.parametrize(
    "header,expected",
    [
        ("年初余额.借方金额", "year_opening_debit"),
        ("年初余额.贷方金额", "year_opening_credit"),
        ("本年累计.借方金额", "year_debit"),
        ("本年累计.贷方金额", "year_credit"),
        ("累计发生额.借方", "year_debit"),
        ("累计发生额.贷方", "year_credit"),
        ("期初余额.借方金额", "opening_debit"),
        ("期初余额.贷方金额", "opening_credit"),
        ("本期发生额.借方金额", "debit_amount"),
        ("本期发生额.贷方金额", "credit_amount"),
        ("期末余额.借方金额", "closing_debit"),
        ("期末余额.贷方金额", "closing_credit"),
    ],
)
def test_merged_header_distinguishes_year(header, expected):
    field, conf, source = _match_merged_header(header)
    assert field == expected, f"{header} → {field}, expected {expected}"
    assert conf > 0


# ---- Property 13: 年初净额单列边界（_default → opening_balance）----

def test_merged_header_year_opening_net_default():
    # 点号形式 + group=年初余额 + sub 非借贷子列 → _default → opening_balance
    field, _c, _s = _match_merged_header("年初余额.金额")
    assert field == "opening_balance"
    # 期初余额 _default 亦为 opening_balance
    field2, _c2, _s2 = _match_merged_header("期初余额.余额")
    assert field2 == "opening_balance"


def test_merged_header_requires_dot():
    # 裸 group（无点号）不走合并表头映射
    assert _match_merged_header("年初余额") == (None, 0, "")


# ---- Property 9: 单行别名区分年度 ----

@pytest.mark.parametrize(
    "header,expected",
    [
        ("年初借方", "year_opening_debit"),
        ("年初贷方", "year_opening_credit"),
        ("期初借方", "opening_debit"),
        ("期初贷方", "opening_credit"),
        ("本年累计借方", "year_debit"),
        ("本年累计贷方", "year_credit"),
        ("累计借方", "year_debit"),
        ("累计贷方", "year_credit"),
        ("本期借方", "debit_amount"),
        ("本期贷方", "credit_amount"),
        ("借方发生额", "debit_amount"),
        ("贷方发生额", "credit_amount"),
        ("期初余额", "opening_balance"),
        ("期末余额", "closing_balance"),
        ("科目编码", "account_code"),
    ],
)
def test_single_row_alias_distinguishes_year(header, expected):
    field, conf, _source = _match_header(header)
    assert field == expected, f"{header} → {field}, expected {expected}"
    assert conf > 0


# ---------------------------------------------------------------------------
# Wave2 — 分类层 + 替代守卫（Task 3.3）
# ---------------------------------------------------------------------------

from app.services.ledger_import.detection_types import (  # noqa: E402
    KEY_COLUMNS,
    RECOMMENDED_COLUMNS,
    SheetDetection,
    classify_column_tier,
)
from app.services.ledger_import.identifier import identify  # noqa: E402


def _tier_map(headers: list[str]) -> tuple[str, dict[str, str]]:
    """构建 SheetDetection → identify → 返回 (table_type, {standard_field: tier})。"""
    sheet = SheetDetection(
        file_name="余额表.xlsx",
        sheet_name="科目余额表",
        row_count_estimate=2,
        header_row_index=0,
        data_start_row=1,
        table_type="unknown",
        table_type_confidence=0,
        confidence_level="manual_required",
        preview_rows=[headers],
        detection_evidence={"header_cells": headers},
    )
    result = identify(sheet)
    tiers: dict[str, str] = {}
    for cm in result.column_mappings:
        if cm.standard_field:
            tiers[cm.standard_field] = cm.column_tier
    return result.table_type, tiers


def test_frozen_key_recommended_sets_match_expected():
    """Task 1.2 冻结集合与实际 KEY/RECOMMENDED 一致（分类真源守卫）。"""
    assert KEY_COLUMNS["balance"] == EXPECTED_KEY_COLUMNS_BALANCE
    assert EXPECTED_RECOMMENDED_SUBSET_BALANCE <= RECOMMENDED_COLUMNS["balance"]


# ---- Property 5: 同时含年度+月度列 → 年度=key、月度=recommended ----

def test_mixed_year_month_tiers():
    headers = [
        "科目编码", "年初借方", "年初贷方", "期初借方", "期初贷方",
        "本年累计借方", "本年累计贷方", "本期借方", "本期贷方", "期末余额",
    ]
    table_type, tiers = _tier_map(headers)
    assert table_type == "balance"
    # 年度列 = key
    assert tiers["year_opening_debit"] == "key"
    assert tiers["year_opening_credit"] == "key"
    assert tiers["year_debit"] == "key"
    assert tiers["year_credit"] == "key"
    assert tiers["closing_balance"] == "key"
    # 月度列 = recommended（单字段替代不提升）
    assert tiers["opening_debit"] == "recommended"
    assert tiers["opening_credit"] == "recommended"
    assert tiers["debit_amount"] == "recommended"
    assert tiers["credit_amount"] == "recommended"


# ---- Property 6: 仅月度列仍识别为 balance + 不误阻断 ----

def test_month_only_still_recognized_as_balance():
    headers = [
        "科目编码", "期初借方", "期初贷方", "本期借方", "本期贷方",
        "期末借方", "期末贷方",
    ]
    table_type, tiers = _tier_map(headers)
    assert table_type == "balance", "仅月度列的余额表应仍识别为 balance（替代组兜底）"
    # 期末分列经组合替代提升为 key（Property 7 组合型）
    assert tiers["closing_debit"] == "key"
    assert tiers["closing_credit"] == "key"


# ---- Property 7: 提升守卫 ----

def test_single_field_alt_not_promoted_combo_promoted():
    # 同时含年初列与期初列：opening_debit 是 year_opening_debit 的单字段替代 → 不提升
    _tt, tiers = _tier_map([
        "科目编码", "年初借方", "年初贷方", "期初借方", "期初贷方",
        "本年累计借方", "本年累计贷方", "期末借方", "期末贷方",
    ])
    assert tiers["opening_debit"] == "recommended"
    assert tiers["opening_credit"] == "recommended"
    # 期末分列组合替代 → 提升为 key
    assert tiers["closing_debit"] == "key"
    assert tiers["closing_credit"] == "key"


def test_classify_column_tier_direct():
    # 直接分层（不经替代提升）
    assert classify_column_tier("year_opening_debit", "balance") == "key"
    assert classify_column_tier("year_debit", "balance") == "key"
    assert classify_column_tier("closing_balance", "balance") == "key"
    assert classify_column_tier("opening_debit", "balance") == "recommended"
    assert classify_column_tier("debit_amount", "balance") == "recommended"
    assert classify_column_tier("closing_debit", "balance") == "recommended"


# ---------------------------------------------------------------------------
# Wave3 — 转换层年度优先（Task 4.2 PBT，Property 1-4、11）
# ---------------------------------------------------------------------------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from app.services.ledger_import.converter import _first_decimal  # noqa: E402
from app.services.smart_import_engine import (  # noqa: E402
    convert_balance_rows as legacy_convert_balance_rows,
)

# 金额策略：非负整数字符串（避免符号/精度噪声，聚焦取数优先级）
_amt = st.integers(min_value=0, max_value=10_000_000).map(str)


def _base_row(**over):
    row = {"account_code": "1122", "account_name": "应收账款"}
    row.update(over)
    return row


# ---- Property 1: 整年导出等价性（年初=期初、本年累计=本期）----

@settings(max_examples=5, deadline=None)
@given(od=_amt, oc=_amt, dbt=_amt, cdt=_amt, cct=_amt)
def test_full_year_equivalence(od, oc, dbt, cdt, cct):
    """年初==期初 且 本年累计==本期 时，与"仅月度列"转换逐值等价。"""
    with_year = _base_row(
        year_opening_debit=od, year_opening_credit=oc,
        opening_debit=od, opening_credit=oc,
        year_debit=dbt, year_credit="0",
        debit_amount=dbt, credit_amount="0",
        closing_debit=cdt, closing_credit=cct,
    )
    month_only = _base_row(
        opening_debit=od, opening_credit=oc,
        debit_amount=dbt, credit_amount="0",
        closing_debit=cdt, closing_credit=cct,
    )
    (rw,), _ = convert_balance_rows([with_year])
    (rm,), _ = convert_balance_rows([month_only])
    for f in ("opening_balance", "debit_amount", "credit_amount", "closing_balance"):
        assert rw[f] == rm[f], f"{f}: year-path {rw[f]} != month-only {rm[f]}"


# ---- Property 2: 期初年度优先（年初≠期初）----

@settings(max_examples=5, deadline=None)
@given(year=st.integers(min_value=1, max_value=9_000_000),
       month=st.integers(min_value=1, max_value=9_000_000))
def test_opening_year_priority(year, month):
    """年初借 ≠ 期初借 时，opening_balance 由年初派生。"""
    row = _base_row(
        year_opening_debit=str(year), year_opening_credit="0",
        opening_debit=str(month), opening_credit="0",
        closing_debit="0", closing_credit="0",
    )
    (r,), _ = convert_balance_rows([row])
    # 资产借方：opening_balance 归一为借方正数 = 年初借值（非月度）
    assert r["opening_balance"] == Decimal(str(year))


# ---- Property 3: 发生额本年累计优先 ----

@settings(max_examples=5, deadline=None)
@given(ycum=st.integers(min_value=1, max_value=9_000_000),
       month=st.integers(min_value=1, max_value=9_000_000))
def test_occurrence_year_cumulative_priority(ycum, month):
    row = _base_row(
        opening_debit="0", opening_credit="0",
        year_debit=str(ycum), year_credit="0",
        debit_amount=str(month), credit_amount="0",
        closing_debit="0", closing_credit="0",
    )
    (r,), _ = convert_balance_rows([row])
    assert r["debit_amount"] == Decimal(str(ycum))


# ---- Property 4: 月度兜底（无 year_*）----

def test_month_only_fallback_matches_anchor():
    (r,), _ = convert_balance_rows([dict(_MONTH_ONLY_ROW)])
    assert r["opening_balance"] == Decimal("100")
    assert r["debit_amount"] == Decimal("50")
    assert r["credit_amount"] == Decimal("30")
    assert r["closing_balance"] == Decimal("120")


# ---- Property 11: 期末逻辑不变 ----

def test_closing_logic_unchanged():
    row = _base_row(
        opening_debit="0", opening_credit="0",
        debit_amount="0", credit_amount="0",
        closing_debit="500", closing_credit="0",
    )
    (r,), _ = convert_balance_rows([row])
    assert r["closing_balance"] == Decimal("500")


# ---- _first_decimal: Decimal(0) 不被当缺失 ----

def test_first_decimal_zero_is_present():
    assert _first_decimal("0", "999") == Decimal("0")  # 年度列=0 优先，不跳月度
    assert _first_decimal("", "999") == Decimal("999")  # 年度空 → 兜底月度
    assert _first_decimal(None, None) is None


# ---- Property 12 (partial): legacy 与 v2 口径一致 ----

@settings(max_examples=5, deadline=None)
@given(od=_amt, dbt=_amt, cdt=_amt)
def test_legacy_v2_year_first_parity(od, dbt, cdt):
    """legacy smart_import_engine 与 v2 converter 的年度优先取数逐值一致。"""
    row = _base_row(
        year_opening_debit=od, opening_debit="1",
        year_debit=dbt, debit_amount="1", credit_amount="0",
        closing_debit=cdt, closing_credit="0",
    )
    (v2,), _ = convert_balance_rows([dict(row)])
    (lg,), _ = legacy_convert_balance_rows([dict(row)])
    assert v2["opening_balance"] == lg["opening_balance"]
    assert v2["debit_amount"] == lg["debit_amount"]
    assert v2["closing_balance"] == lg["closing_balance"]


# ---------------------------------------------------------------------------
# Wave4 — SubmitGate 变体（Task 5.2，Property 10）
# ---------------------------------------------------------------------------

from app.services.ledger_import.submit_gate import (  # noqa: E402
    CRITICAL_COLUMNS,
    SubmitGate,
)


def test_submitgate_critical_combos_frozen():
    """CRITICAL_COLUMNS["balance"] 与冻结期望集合一致。"""
    actual = [set(c) for c in CRITICAL_COLUMNS["balance"]]
    for expected in EXPECTED_SUBMITGATE_CRITICAL_BALANCE:
        assert expected in actual, f"缺关键列组合 {expected}"


@pytest.mark.parametrize(
    "mapped,should_pass",
    [
        # 原三组合仍通过
        ({"account_code", "opening_balance"}, True),
        ({"account_code", "closing_balance"}, True),
        ({"account_code", "debit_amount", "credit_amount"}, True),
        # 年度/分列变体通过（R2.5）
        ({"account_code", "year_opening_debit", "year_opening_credit"}, True),
        ({"account_code", "closing_debit", "closing_credit"}, True),
        ({"account_code", "year_debit", "year_credit"}, True),
        # 年度分列文件（全年初+本年累计+期末分列）通过
        ({"account_code", "year_opening_debit", "year_opening_credit",
          "year_debit", "year_credit", "closing_debit", "closing_credit"}, True),
        # 缺失：仅 account_code 不过
        ({"account_code"}, False),
        # 缺失：只有半边期末分列不过
        ({"account_code", "closing_debit"}, False),
    ],
)
def test_submitgate_balance_critical_columns(mapped, should_pass):
    assert SubmitGate._has_critical_columns("balance", mapped) is should_pass


# ---------------------------------------------------------------------------
# Wave5 — 契约守卫（Task 6.2）：三个映射真源年度/月度一致
# ---------------------------------------------------------------------------

from app.services.ledger_import.identifier import _MERGED_HEADER_MAPPING  # noqa: E402
from app.services.smart_import_engine import _MERGED_HEADER_MAP as _LEGACY_MERGED  # noqa: E402


def test_three_mapping_sources_year_month_consistent():
    """A(identifier 点号) / B(JSON 单行别名) / C(legacy 参照) 三源对年初/本年累计口径一致。"""
    # A: identifier 点号合并表头
    assert _MERGED_HEADER_MAPPING["年初余额"]["借方金额"] == "year_opening_debit"
    assert _MERGED_HEADER_MAPPING["年初余额"]["贷方金额"] == "year_opening_credit"
    assert _MERGED_HEADER_MAPPING["本年累计"]["借方金额"] == "year_debit"
    assert _MERGED_HEADER_MAPPING["本年累计"]["贷方金额"] == "year_credit"
    assert _MERGED_HEADER_MAPPING["期初余额"]["借方金额"] == "opening_debit"
    assert _MERGED_HEADER_MAPPING["本期发生额"]["借方金额"] == "debit_amount"

    # B: JSON 单行别名（经 _match_header）
    assert _match_header("年初借方")[0] == "year_opening_debit"
    assert _match_header("本年累计借方")[0] == "year_debit"
    assert _match_header("期初借方")[0] == "opening_debit"
    assert _match_header("本期借方")[0] == "debit_amount"

    # C: legacy 参照（smart_import_engine._MERGED_HEADER_MAP）
    assert _LEGACY_MERGED["年初借方"] == "year_opening_debit"
    assert _LEGACY_MERGED["本年累计借方"] == "year_debit"
    assert _LEGACY_MERGED["期初余额_借方金额"] == "opening_debit"

    # 三源一致：年初→year_opening_debit（不再退化为 opening_debit）
    assert (
        _MERGED_HEADER_MAPPING["年初余额"]["借方金额"]
        == _match_header("年初借方")[0]
        == _LEGACY_MERGED["年初借方"]
        == "year_opening_debit"
    )


# ---------------------------------------------------------------------------
# 复盘补强 — aux 消歧（Property 14）+ 年初余额净额显式映射（Property 15）
# ---------------------------------------------------------------------------


def _identify_type(sheet_name: str, headers: list[str]) -> tuple[str, int]:
    sheet = SheetDetection(
        file_name="x.xlsx", sheet_name=sheet_name, row_count_estimate=2,
        header_row_index=0, data_start_row=1, table_type="unknown",
        table_type_confidence=0, confidence_level="manual_required",
        preview_rows=[headers], detection_evidence={"header_cells": headers},
    )
    r = identify(sheet)
    return r.table_type, r.table_type_confidence


@pytest.mark.parametrize(
    "sheet_name,headers",
    [
        # 含 aux_type/aux_code + 净额/发生额，泛型 sheet 名（只靠表头，最难 case）
        ("Sheet1", ["科目编码", "辅助类型", "辅助编码", "辅助名称",
                    "期初余额", "借方发生额", "贷方发生额", "期末余额"]),
        # 含 aux_type/aux_code、无 aux_name、且 sheet 名为「辅助余额表」——曾被误判 balance
        ("辅助余额表", ["科目编码", "辅助类型", "辅助编码",
                    "期初余额", "借方发生额", "贷方发生额", "期末余额"]),
    ],
)
def test_aux_balance_not_misclassified_as_balance(sheet_name, headers):
    """Property 14：含 aux 维度列的余额表识别为 aux_balance（不被年度语义改造误判为 balance）。"""
    tt, _conf = _identify_type(sheet_name, headers)
    assert tt == "aux_balance", f"{sheet_name}/{headers} → {tt}, 期望 aux_balance"


def test_classic_and_year_balance_still_balance():
    """对照：无 aux 列的经典净额表与年度分列表仍识别为 balance（不被负向信号误伤）。"""
    assert _identify_type("Sheet1", ["科目编码", "科目名称", "期初余额", "借方发生额", "贷方发生额", "期末余额"])[0] == "balance"
    assert _identify_type("科目余额表", ["科目编码", "科目名称", "年初借方", "年初贷方", "本年累计借方", "本年累计贷方", "期末余额"])[0] == "balance"


def test_year_opening_net_single_column_explicit_alias():
    """Property 15：「年初余额」净额单列经精确别名映射到 opening_balance（exact，非 Levenshtein 兜底）。"""
    field, conf, source = _match_header("年初余额")
    assert field == "opening_balance"
    assert source == "header_exact"
    assert conf >= 90
