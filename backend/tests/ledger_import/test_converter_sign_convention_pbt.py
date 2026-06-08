"""converter v2 符号约定属性测试（PBT，ledger-sign-convention-unify Task 2.4）。

对应 design「测试策略-PBT」：
- 属性：converter 转换后，同类科目存储符号一致；幂等（二次转换结果相同）。

本文件实现两条命名属性：
1. 同类符号一致：对任意生成的同类（同正常方向）科目余额行（如全部负债类贷方
   余额），`convert_balance_rows` 转换后存储符号一致——同为正数，方向同为该类
   正常方向（credit/debit）。
2. 转换幂等：对任意生成的余额行列表，`convert_balance_rows` 二次转换结果完全相同。

硬约束（需求 8.5，项目铁律）：hypothesis `@settings(max_examples<=5)`，禁用默认 100。
此处用 max_examples=3 进一步加速。

纯函数测试，无需真实 PG，使用构造的 row dict 输入。
"""
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from app.services.ledger_import.converter import convert_balance_rows
from app.services.ledger_import.sign_convention_types import CURRENT_SIGN_CONVENTION


# ---------------------------------------------------------------------------
# 科目样本（非备抵，正常方向明确，便于"同类符号一致"断言）
# ---------------------------------------------------------------------------
# 贷方正常类（负债/权益/收入）：贷方余额归一后应存正数，方向 credit。
_CREDIT_NORMAL = [
    ("2202", "应付账款"),
    ("2241", "其他应付款"),
    ("2211", "应付职工薪酬"),
    ("4001", "实收资本"),
    ("4002", "资本公积"),
    ("6001", "主营业务收入"),
    ("6051", "其他业务收入"),
]
# 借方正常类（资产/成本/费用）：借方余额归一后应存正数，方向 debit。
_DEBIT_NORMAL = [
    ("1001", "库存现金"),
    ("1002", "银行存款"),
    ("1122", "应收账款"),
    ("6401", "主营业务成本"),
    ("6601", "销售费用"),
    ("6602", "管理费用"),
]

# 幂等属性用全集（含备抵科目，覆盖更广输入空间）。
_ALL_CODE_NAME = _CREDIT_NORMAL + _DEBIT_NORMAL + [
    ("1602", "累计折旧"),
    ("1231", "坏账准备"),
    ("4201", "库存股"),
]

_amount_strategy = st.integers(min_value=1, max_value=10_000_000)


@st.composite
def _same_category_rows(draw, *, samples, balance_side):
    """生成同类科目余额行列表（同正常方向，正常侧余额，无方向冲突）。

    samples: 该类的 (code, name) 候选；balance_side: 'closing_credit' 或 'closing_debit'。
    每行金额为正整数字符串，余额落在科目正常方向一侧，因此归一后必为正数、无异常。
    """
    n = draw(st.integers(min_value=1, max_value=6))
    rows: list[dict] = []
    for _ in range(n):
        code, name = draw(st.sampled_from(samples))
        amt = draw(_amount_strategy)
        rows.append({
            "account_code": code,
            "account_name": name,
            balance_side: str(amt),
        })
    return rows


@st.composite
def _arbitrary_balance_rows(draw):
    """生成任意余额行列表（混合类别/借贷侧/可选辅助维度），用于幂等属性。"""
    n = draw(st.integers(min_value=0, max_value=8))
    rows: list[dict] = []
    for _ in range(n):
        code, name = draw(st.sampled_from(_ALL_CODE_NAME))
        amt = draw(st.integers(min_value=0, max_value=10_000_000))
        use_credit = draw(st.booleans())
        row: dict = {"account_code": code, "account_name": name}
        row["closing_credit" if use_credit else "closing_debit"] = str(amt)
        # 可选期初余额
        if draw(st.booleans()):
            row["opening_credit" if use_credit else "opening_debit"] = str(
                draw(st.integers(min_value=0, max_value=10_000_000))
            )
        # 可选辅助维度
        if draw(st.booleans()):
            row["aux_dimensions"] = "客户:C001 甲公司"
        rows.append(row)
    return rows


class TestSameCategorySignConsistency:
    """属性 1：同类科目转换后存储符号一致（同为正数 + 方向同为该类正常方向）。

    **Validates: Requirements 8.5**
    """

    @settings(max_examples=3)
    @given(rows=_same_category_rows(samples=_CREDIT_NORMAL, balance_side="closing_credit"))
    def test_credit_normal_rows_consistent_positive_credit(self, rows):
        """全部贷方正常类（如负债贷方余额）→ 存储符号一致：正数 + 方向 credit。"""
        balance, _ = convert_balance_rows(rows)
        assert balance, "至少应产出一条主表行"
        for r in balance:
            assert r["closing_direction"] == "credit"
            assert r["closing_balance"] > 0
            assert r["sign_convention_version"] == CURRENT_SIGN_CONVENTION
            # 正常方向余额不应触发符号异常
            assert r.get("sign_anomaly_flags") is None

    @settings(max_examples=3)
    @given(rows=_same_category_rows(samples=_DEBIT_NORMAL, balance_side="closing_debit"))
    def test_debit_normal_rows_consistent_positive_debit(self, rows):
        """全部借方正常类（如资产借方余额）→ 存储符号一致：正数 + 方向 debit。"""
        balance, _ = convert_balance_rows(rows)
        assert balance, "至少应产出一条主表行"
        for r in balance:
            assert r["closing_direction"] == "debit"
            assert r["closing_balance"] > 0
            assert r["sign_convention_version"] == CURRENT_SIGN_CONVENTION
            assert r.get("sign_anomaly_flags") is None


class TestConversionIdempotent:
    """属性 2：convert_balance_rows 二次转换结果完全相同（幂等）。

    **Validates: Requirements 8.5**
    """

    @settings(max_examples=3)
    @given(rows=_arbitrary_balance_rows())
    def test_balance_conversion_idempotent(self, rows):
        b1, a1 = convert_balance_rows(rows)
        b2, a2 = convert_balance_rows(rows)
        assert b1 == b2
        assert a1 == a2
