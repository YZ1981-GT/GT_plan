"""direction_resolver 单元测试（ledger-sign-convention-unify 需求 2、3）。

覆盖：6 大类正常方向 + 备抵反向 + 名称编码冲突 + 名称缺失兜底 + 多关键词优先级。
纯函数，无需 DB。
"""
from __future__ import annotations

import pytest

from app.services.ledger_import.direction_resolver import resolve_account_direction


class TestNormalCategories:
    """6 大类正常方向：资产/成本/费用→debit；负债/权益/收入→credit。"""

    def test_asset_debit(self):
        d, s = resolve_account_direction("1002", "银行存款")
        assert d == "debit"
        assert s == "account_category_inferred"

    def test_liability_credit(self):
        d, s = resolve_account_direction("2221", "应交税费")
        assert d == "credit"

    def test_equity_credit(self):
        d, _ = resolve_account_direction("4001", "实收资本")
        assert d == "credit"

    def test_revenue_credit(self):
        d, _ = resolve_account_direction("6001", "主营业务收入")
        assert d == "credit"

    def test_expense_debit(self):
        d, _ = resolve_account_direction("6601", "销售费用")
        assert d == "debit"

    def test_cost_debit(self):
        d, _ = resolve_account_direction("6401", "主营业务成本")
        assert d == "debit"


class TestContraAccounts:
    """备抵/反向科目：方向与编码大类相反，靠名称识别。"""

    @pytest.mark.parametrize("code,name", [
        ("1602", "累计折旧"),
        ("1702", "累计摊销"),
        ("1231", "坏账准备"),
        ("1601", "固定资产减值准备"),
        ("1471", "存货跌价准备"),
        ("1801", "长期待摊费用减值准备"),
    ])
    def test_asset_contra_credit(self, code, name):
        """资产备抵 → credit（与 1xxx 资产借方相反）。"""
        d, s = resolve_account_direction(code, name)
        assert d == "credit"
        assert s == "contra_account"

    def test_treasury_stock_debit(self):
        """库存股（权益备抵）→ debit。"""
        d, s = resolve_account_direction("4201", "库存股")
        assert d == "debit"
        assert s == "contra_account"


class TestNameCodeConflict:
    """名称与编码冲突：名称优先（_infer_category 已名称优先）。"""

    def test_name_overrides_code_prefix(self):
        # 编码 1xxx 通常是资产(debit)，但名称"累计折旧"是备抵→credit
        d, s = resolve_account_direction("1602", "累计折旧")
        assert d == "credit"
        assert s == "contra_account"


class TestNameMissing:
    """名称缺失：仅编码兜底，标低置信度。"""

    def test_empty_name_liability_low_confidence(self):
        d, s = resolve_account_direction("2202", "")
        assert d == "credit"
        assert s == "account_category_inferred_low_confidence"

    def test_empty_name_asset_low_confidence(self):
        d, s = resolve_account_direction("1122", "")
        assert d == "debit"
        assert s == "account_category_inferred_low_confidence"


class TestPriority:
    """多关键词/优先级：备抵正则 > 名称类别 > 编码。"""

    def test_contra_beats_category(self):
        # "固定资产减值准备" 既含"固定资产"(资产类名)又含"减值准备"(备抵)→备抵优先 credit
        d, s = resolve_account_direction("1601", "固定资产减值准备")
        assert d == "credit"
        assert s == "contra_account"

    def test_direction_always_valid(self):
        for code, name in [("1002", "银行存款"), ("2221", "应交税费"), ("1602", "累计折旧"), ("", "")]:
            d, s = resolve_account_direction(code, name)
            assert d in ("debit", "credit")
            assert isinstance(s, str) and s


# ---------------------------------------------------------------------------
# PBT（hypothesis，max_examples=5 — 项目硬性约束）
# ---------------------------------------------------------------------------
from hypothesis import given, settings, strategies as st


# 编码片段（覆盖 6 大类前缀）+ 任意中文/空名称
_code_strategy = st.from_regex(r"[1-6][0-9]{3}", fullmatch=True)
_name_strategy = st.one_of(
    st.just(""),
    st.sampled_from([
        "银行存款", "应交税费", "实收资本", "主营业务收入", "销售费用",
        "累计折旧", "坏账准备", "库存股", "固定资产减值准备", "其他",
    ]),
    st.text(min_size=0, max_size=8),
)


class TestPBT:
    @settings(max_examples=5)
    @given(code=_code_strategy, name=_name_strategy)
    def test_direction_always_binary(self, code, name):
        """属性：方向恒为 debit/credit 之一，source 非空。"""
        d, s = resolve_account_direction(code, name)
        assert d in ("debit", "credit")
        assert isinstance(s, str) and s

    @settings(max_examples=5)
    @given(code=_code_strategy)
    def test_contra_priority_stable(self, code):
        """属性：含备抵关键词时恒判 contra_account 且方向稳定，不受编码影响。"""
        d, s = resolve_account_direction(code, "累计折旧")
        assert s == "contra_account"
        assert d == "credit"

    @settings(max_examples=5)
    @given(code=_code_strategy, name=_name_strategy)
    def test_idempotent(self, code, name):
        """属性：同输入多次调用结果一致（纯函数幂等）。"""
        r1 = resolve_account_direction(code, name)
        r2 = resolve_account_direction(code, name)
        assert r1 == r2
