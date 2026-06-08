"""converter v2 符号约定单元测试（ledger-sign-convention-unify 需求 8.1）。

覆盖 Task 2.1/2.2 对 converter.py 的改造（design「测试策略-单元测试-converter」）：
- 各类科目存储符号正确（资产/成本/费用借方正；负债/权益/收入贷方余额存正数；
  备抵科目：累计折旧/坏账准备→credit、库存股→debit 方向正确）
- 方向字段写入：opening_direction/closing_direction/*_direction_source/sign_convention_version=v2
- 显式方向列优先（需求 5.3）
- 借贷分列计算（需求 5.4）
- 方向与类别冲突（负债借方余额）保留带符号负值 + sign_anomaly_flags（需求 1.5/4.5）
- 分录行 entry_direction + source 标记，金额口径不变
- 幂等（需求 5.6）
- 不破坏辅助维度拆分 / 主表去重

纯函数测试，无需真实 PG，使用构造的 row dict 输入。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.ledger_import.converter import (
    convert_balance_rows,
    convert_balance_rows_v2,
    convert_ledger_rows,
    convert_ledger_rows_v2,
)
from app.services.ledger_import.sign_convention_types import CURRENT_SIGN_CONVENTION


def _one(rows: list[dict]) -> dict:
    """转换并断言主表恰好 1 条，返回该行。"""
    balance, _ = convert_balance_rows(rows)
    assert len(balance) == 1
    return balance[0]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 各类科目存储符号正确（需求 1.2/1.3、8.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestStorageSignByCategory:
    """借方类（资产/成本/费用）借方余额存正数；
    贷方类（负债/权益/收入）贷方余额存正数。"""

    def test_asset_debit_positive(self):
        """资产：1001 库存现金 借方余额 → 正数，方向 debit。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "closing_debit": "120", "opening_debit": "100"}])
        assert b["closing_balance"] == Decimal("120")
        assert b["opening_balance"] == Decimal("100")
        assert b["closing_direction"] == "debit"
        assert b["opening_direction"] == "debit"

    def test_cost_debit_positive(self):
        """成本：6401 主营业务成本 借方余额 → 正数，方向 debit。"""
        b = _one([{"account_code": "6401", "account_name": "主营业务成本",
                   "closing_debit": "30000"}])
        assert b["closing_balance"] == Decimal("30000")
        assert b["closing_direction"] == "debit"

    def test_expense_debit_positive(self):
        """费用：6601 销售费用 借方余额 → 正数，方向 debit。"""
        b = _one([{"account_code": "6601", "account_name": "销售费用",
                   "closing_debit": "5000"}])
        assert b["closing_balance"] == Decimal("5000")
        assert b["closing_direction"] == "debit"

    def test_liability_credit_stored_positive(self):
        """负债：2202 应付账款 贷方余额 → 存正数（不再是负数），方向 credit。"""
        b = _one([{"account_code": "2202", "account_name": "应付账款",
                   "closing_credit": "8000", "opening_credit": "6000"}])
        assert b["closing_balance"] == Decimal("8000")
        assert b["opening_balance"] == Decimal("6000")
        assert b["closing_direction"] == "credit"
        assert b["opening_direction"] == "credit"

    def test_equity_credit_stored_positive(self):
        """权益：4001 实收资本 贷方余额 → 存正数，方向 credit。"""
        b = _one([{"account_code": "4001", "account_name": "实收资本",
                   "closing_credit": "1000000"}])
        assert b["closing_balance"] == Decimal("1000000")
        assert b["closing_direction"] == "credit"

    def test_revenue_credit_stored_positive(self):
        """收入：6001 主营业务收入 贷方余额 → 存正数，方向 credit。"""
        b = _one([{"account_code": "6001", "account_name": "主营业务收入",
                   "closing_credit": "500000"}])
        assert b["closing_balance"] == Decimal("500000")
        assert b["closing_direction"] == "credit"


class TestContraAccounts:
    """备抵/反向科目方向正确（需求 3）。

    备抵识别体现在 direction 值上（与编码大类相反）；direction_source 反映金额列
    来源（借贷分列→split_columns）。用净额输入（无方向列）可验证来源退化为
    contra_account（资产备抵的 v1 贷方净额为负，归一后存正数）。
    """

    def test_accumulated_depreciation_credit_via_split(self):
        """累计折旧（1602，挂资产编码）借贷分列 → 方向 credit，贷方余额存正数。"""
        b = _one([{"account_code": "1602", "account_name": "累计折旧",
                   "closing_credit": "20000"}])
        assert b["closing_direction"] == "credit"
        # 借贷分列输入 → 来源为 split_columns；备抵性体现在 direction=credit
        assert b["closing_direction_source"] == "split_columns"
        assert b["closing_balance"] == Decimal("20000")

    def test_accumulated_depreciation_source_contra_via_net(self):
        """净额输入（无方向列）→ 来源退化为类别推断结果 contra_account。
        资产备抵 v1 贷方净额为负，归一后存正数。"""
        b = _one([{"account_code": "1602", "account_name": "累计折旧",
                   "closing_balance": "-20000"}])
        assert b["closing_direction"] == "credit"
        assert b["closing_direction_source"] == "contra_account"
        assert b["closing_balance"] == Decimal("20000")

    def test_bad_debt_provision_credit(self):
        """坏账准备（1231，挂资产编码）→ 方向 credit。"""
        b = _one([{"account_code": "1231", "account_name": "坏账准备",
                   "closing_credit": "3000"}])
        assert b["closing_direction"] == "credit"
        assert b["closing_balance"] == Decimal("3000")

    def test_treasury_stock_debit(self):
        """库存股（4201，挂权益编码）→ 方向 debit，借方余额存正数。"""
        b = _one([{"account_code": "4201", "account_name": "库存股",
                   "closing_debit": "50000"}])
        assert b["closing_direction"] == "debit"
        assert b["closing_balance"] == Decimal("50000")

    def test_treasury_stock_source_contra_via_net(self):
        """库存股净额输入 → 来源 contra_account；权益备抵 v1 借方净额为正，归一后存正数。"""
        b = _one([{"account_code": "4201", "account_name": "库存股",
                   "closing_balance": "50000"}])
        assert b["closing_direction"] == "debit"
        assert b["closing_direction_source"] == "contra_account"
        assert b["closing_balance"] == Decimal("50000")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 方向字段写入（需求 4.1/4.3、1.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectionFieldsWritten:
    def test_all_direction_fields_present(self):
        b = _one([{"account_code": "2202", "account_name": "应付账款",
                   "opening_credit": "6000", "closing_credit": "8000"}])
        # 方向字段
        assert b["opening_direction"] == "credit"
        assert b["closing_direction"] == "credit"
        # 来源字段（借贷分列 → split_columns）
        assert b["opening_direction_source"] == "split_columns"
        assert b["closing_direction_source"] == "split_columns"
        # 约定版本标记 v2
        assert b["sign_convention_version"] == CURRENT_SIGN_CONVENTION
        assert b["sign_convention_version"] == "v2_category_natural_positive"

    def test_category_inferred_source_when_no_columns(self):
        """无显式列/分列，仅净额（无方向 token）→ 来源退化为类别推断。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "closing_balance": "120"}])
        assert b["closing_direction"] == "debit"
        assert b["closing_direction_source"] == "account_category_inferred"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 显式方向列优先（需求 5.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestExplicitDirectionPriority:
    def test_explicit_credit_direction_column(self):
        """显式方向列 '贷' + 净额余额 → 来源 explicit_direction，存正数。"""
        b = _one([{"account_code": "2221", "account_name": "应交税费",
                   "closing_balance": "14203492", "direction": "贷"}])
        # 应交税费贷方余额，显式列标贷 → 归一后存正数
        assert b["closing_balance"] == Decimal("14203492")
        assert b["closing_direction"] == "credit"
        assert b["closing_direction_source"] == "explicit_direction"

    def test_explicit_debit_direction_column(self):
        """显式方向列 '借' → 来源 explicit_direction。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "closing_balance": "500", "direction": "借"}])
        assert b["closing_balance"] == Decimal("500")
        assert b["closing_direction"] == "debit"
        assert b["closing_direction_source"] == "explicit_direction"

    def test_explicit_direction_beats_net_only(self):
        """显式方向来源应覆盖类别推断来源（优先级验证）。"""
        b = _one([{"account_code": "4001", "account_name": "实收资本",
                   "closing_balance": "1000000", "closing_direction": "贷"}])
        assert b["closing_direction_source"] == "explicit_direction"
        assert b["closing_balance"] == Decimal("1000000")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 借贷分列计算（需求 5.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestSplitColumns:
    def test_split_columns_source_marked(self):
        """opening_debit/opening_credit 分列 → 来源 split_columns。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "opening_debit": "100", "closing_debit": "120"}])
        assert b["opening_direction_source"] == "split_columns"
        assert b["closing_direction_source"] == "split_columns"

    def test_split_columns_net_then_normalized(self):
        """分列同时有借贷 → 先算净额再按方向归一。
        资产类借 1000 贷 200 → 净 800 借方 → 存 800 正数。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "closing_debit": "1000", "closing_credit": "200"}])
        assert b["closing_balance"] == Decimal("800")
        assert b["closing_direction"] == "debit"

    def test_split_columns_liability_net_normalized(self):
        """负债类分列：贷 5000 借 1000 → 净 -4000（v1）→ 归一存 +4000。"""
        b = _one([{"account_code": "2202", "account_name": "应付账款",
                   "closing_debit": "1000", "closing_credit": "5000"}])
        assert b["closing_balance"] == Decimal("4000")
        assert b["closing_direction"] == "credit"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 方向与类别冲突 → 保留带符号负值 + sign_anomaly_flags（需求 1.5/4.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectionCategoryConflict:
    def test_liability_with_debit_balance_keeps_negative(self):
        """负债出现借方余额（应交税费借方留抵）→ 归一后为负值，保留不翻正。"""
        b = _one([{"account_code": "2221", "account_name": "应交税费",
                   "closing_debit": "14203492"}])
        # 类别正常方向 credit，但实际借方余额 → 归一后 stored = -net = 负数
        assert b["closing_balance"] == Decimal("-14203492")
        assert b["closing_direction"] == "credit"
        # 异常标记
        flags = b.get("sign_anomaly_flags")
        assert flags is not None
        assert flags["normal_direction"] == "credit"
        conflicts = flags["conflicts"]
        assert any(c["period"] == "closing" and c["actual_direction"] == "debit"
                   for c in conflicts)

    def test_normal_balance_no_anomaly_flag(self):
        """方向与类别一致 → 不产生 sign_anomaly_flags。"""
        b = _one([{"account_code": "2202", "account_name": "应付账款",
                   "closing_credit": "8000"}])
        assert b.get("sign_anomaly_flags") is None

    def test_asset_with_credit_balance_keeps_negative(self):
        """资产出现贷方余额（贷方红字）→ 归一后为负值，保留。"""
        b = _one([{"account_code": "1001", "account_name": "库存现金",
                   "closing_credit": "500"}])
        assert b["closing_balance"] == Decimal("-500")
        assert b["closing_direction"] == "debit"
        flags = b.get("sign_anomaly_flags")
        assert flags is not None
        assert flags["normal_direction"] == "debit"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 分录行 entry_direction + source（需求 4.2/5.2），金额口径不变
# ═══════════════════════════════════════════════════════════════════════════


def _ledger_row(**extra) -> dict:
    base = {
        "account_code": "1001",
        "account_name": "库存现金",
        "voucher_date": date(2025, 1, 15),
        "voucher_no": "记-1",
        "debit_amount": "100.00",
        "credit_amount": "0",
    }
    base.update(extra)
    return base


class TestLedgerEntryDirection:
    def test_debit_only_entry_split_columns(self):
        """借方单边非零 → entry_direction=debit，source=split_columns，金额不变。"""
        ledger, _, _ = convert_ledger_rows([_ledger_row(
            debit_amount="100.00", credit_amount="0")])
        r = ledger[0]
        assert r["entry_direction"] == "debit"
        assert r["entry_direction_source"] == "split_columns"
        # 金额口径不变（不归一化分录金额）
        assert r["debit_amount"] == Decimal("100.00")
        assert r["credit_amount"] == Decimal("0")

    def test_credit_only_entry_split_columns(self):
        """贷方单边非零 → entry_direction=credit。"""
        ledger, _, _ = convert_ledger_rows([_ledger_row(
            debit_amount="0", credit_amount="250.00")])
        r = ledger[0]
        assert r["entry_direction"] == "credit"
        assert r["entry_direction_source"] == "split_columns"
        assert r["credit_amount"] == Decimal("250.00")

    def test_explicit_direction_token_priority(self):
        """显式方向列优先于借贷分列推断。"""
        ledger, _, _ = convert_ledger_rows([_ledger_row(
            debit_amount="100", credit_amount="0", direction="贷")])
        r = ledger[0]
        assert r["entry_direction"] == "credit"
        assert r["entry_direction_source"] == "explicit_direction"

    def test_both_nonzero_falls_back_to_category(self):
        """两侧皆非零（合成小计行）→ 退化按科目类别推断。
        资产类 1001 → debit。"""
        ledger, _, _ = convert_ledger_rows([_ledger_row(
            debit_amount="100", credit_amount="100")])
        r = ledger[0]
        assert r["entry_direction"] == "debit"
        # 来源为类别推断（非 split_columns/explicit）
        assert r["entry_direction_source"] in (
            "account_category_inferred",
            "account_category_inferred_low_confidence",
        )

    def test_amount_unchanged_for_liability_entry(self):
        """负债类分录金额口径不变（不像余额行那样归一）。"""
        ledger, _, _ = convert_ledger_rows([_ledger_row(
            account_code="2202", account_name="应付账款",
            debit_amount="0", credit_amount="8000")])
        r = ledger[0]
        assert r["entry_direction"] == "credit"
        assert r["credit_amount"] == Decimal("8000")
        assert r["debit_amount"] == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# 7. 幂等（需求 5.6）
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotency:
    def test_balance_conversion_idempotent(self):
        """同输入二次转换余额结果完全相同。"""
        rows = [
            {"account_code": "1001", "account_name": "库存现金", "closing_debit": "120"},
            {"account_code": "2202", "account_name": "应付账款", "closing_credit": "8000"},
            {"account_code": "1602", "account_name": "累计折旧", "closing_credit": "20000"},
            {"account_code": "2221", "account_name": "应交税费", "closing_debit": "14203492"},
        ]
        b1, a1 = convert_balance_rows(rows)
        b2, a2 = convert_balance_rows(rows)
        assert b1 == b2
        assert a1 == a2

    def test_ledger_conversion_idempotent(self):
        rows = [
            _ledger_row(debit_amount="100", credit_amount="0"),
            _ledger_row(account_code="2202", account_name="应付账款",
                        debit_amount="0", credit_amount="8000"),
        ]
        l1, al1, s1 = convert_ledger_rows(rows)
        l2, al2, s2 = convert_ledger_rows(rows)
        assert l1 == l2
        assert al1 == al2
        assert s1 == s2


# ═══════════════════════════════════════════════════════════════════════════
# 8. 不破坏辅助维度拆分 / 主表去重（需求 5.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestPreservesAuxAndDedup:
    def test_aux_split_still_works_with_sign(self):
        """带辅助维度的余额行：主表去重 + 辅助拆分仍生效，且 aux 行也带方向字段。"""
        rows = [
            {"account_code": "1002", "account_name": "银行存款",
             "closing_debit": "307072.27"},
            {"account_code": "1002", "account_name": "银行存款",
             "closing_debit": "198431.65",
             "aux_dimensions": "金融机构:A001,工商银行"},
            {"account_code": "1002", "account_name": "银行存款",
             "closing_debit": "108640.62",
             "aux_dimensions": "金融机构:A002,中国邮政储蓄银行"},
        ]
        balance, aux_balance = convert_balance_rows(rows)
        # 主表去重为 1 条
        assert len(balance) == 1
        assert balance[0]["closing_balance"] == Decimal("307072.27")
        assert balance[0]["closing_direction"] == "debit"
        # 辅助表 2 条，均带方向字段与 v2 版本
        assert len(aux_balance) == 2
        for r in aux_balance:
            assert r["closing_direction"] == "debit"
            assert r["sign_convention_version"] == CURRENT_SIGN_CONVENTION

    def test_ledger_aux_split_with_direction(self):
        """序时账辅助拆分不受方向标记影响，主表+辅助表均带 entry_direction。"""
        rows = [_ledger_row(aux_dimensions="客户:C001 甲公司")]
        ledger, aux_ledger, stats = convert_ledger_rows(rows)
        assert len(ledger) == 1
        assert len(aux_ledger) == 1
        assert ledger[0]["entry_direction"] == "debit"
        assert aux_ledger[0]["entry_direction"] == "debit"
        assert stats == {"客户": 1}


# ═══════════════════════════════════════════════════════════════════════════
# 9. v2 结构化接口透传 sign_convention_version
# ═══════════════════════════════════════════════════════════════════════════


class TestV2StructuredResult:
    def test_balance_v2_stats_version(self):
        result = convert_balance_rows_v2([
            {"account_code": "2202", "account_name": "应付账款", "closing_credit": "8000"},
        ])
        assert result.stats["sign_convention_version"] == CURRENT_SIGN_CONVENTION
        assert len(result.rows) == 1
        assert result.rows[0]["closing_balance"] == Decimal("8000")

    def test_ledger_v2_rows_with_direction_count(self):
        result = convert_ledger_rows_v2([
            _ledger_row(debit_amount="100", credit_amount="0"),
        ])
        assert result.stats["sign_convention_version"] == CURRENT_SIGN_CONVENTION
        assert result.stats["rows_with_direction"] == 1
