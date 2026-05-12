"""Balance 主表去重逻辑专项测试（Layer 1 修复验证）。

修复背景：真实 Excel 余额表常见"汇总行(无aux) + N 明细行(有aux)"结构，
如 1002 银行存款 = 工行 198,431.65 + 邮储 108,640.62 = 汇总 307,072.27。
旧逻辑把带 aux 的行既写 aux_balance 又重写主表，导致 tb_balance 里
同 account_code 重复 N+1 次，所有下游 SUM(closing_balance) 翻倍。

修复后主表去重规则：
- 有汇总行 → 主表仅保留汇总行，丢弃带 aux 行的重复
- 仅明细 → 聚合成虚拟汇总行，raw_extra._aggregated_from_aux=true
"""
from __future__ import annotations

from decimal import Decimal

from app.services.ledger_import.converter import convert_balance_rows


def test_summary_plus_details_dedup_to_single_main_row():
    """场景 A：汇总行 + 2 明细行 → 主表 1 条 + 辅助表 2 条。"""
    rows = [
        # 汇总行：1002 银行存款 期末 307072.27（无 aux）
        {
            "account_code": "1002", "account_name": "银行存款",
            "opening_debit": "500000", "closing_debit": "307072.27",
        },
        # 明细行 1：工行 198431.65
        {
            "account_code": "1002", "account_name": "银行存款",
            "opening_debit": "300000", "closing_debit": "198431.65",
            "aux_dimensions": "金融机构:A001,工商银行",
        },
        # 明细行 2：邮储 108640.62
        {
            "account_code": "1002", "account_name": "银行存款",
            "opening_debit": "200000", "closing_debit": "108640.62",
            "aux_dimensions": "金融机构:A002,中国邮政储蓄银行",
        },
    ]

    balance, aux_balance = convert_balance_rows(rows)

    # 主表仅 1 条，用汇总行的值（307072.27）
    assert len(balance) == 1
    assert balance[0]["account_code"] == "1002"
    assert balance[0]["closing_balance"] == Decimal("307072.27")
    assert balance[0]["opening_balance"] == Decimal("500000")
    # 汇总行没有聚合标记
    assert not (balance[0].get("raw_extra") or {}).get("_aggregated_from_aux")

    # 辅助表 2 条
    assert len(aux_balance) == 2
    assert {r["aux_name"] for r in aux_balance} == {"工商银行", "中国邮政储蓄银行"}
    # 辅助表和 = 汇总行
    aux_sum = sum((r["closing_balance"] for r in aux_balance), Decimal(0))
    assert aux_sum == Decimal("307072.27")


def test_only_details_aggregate_to_virtual_summary():
    """场景 B：仅有明细行（无汇总）→ 聚合虚拟主表行，标记 _aggregated_from_aux。"""
    rows = [
        {
            "account_code": "1122", "account_name": "应收账款",
            "closing_debit": "5000",
            "aux_dimensions": "客户:C001 甲公司",
        },
        {
            "account_code": "1122", "account_name": "应收账款",
            "closing_debit": "3000",
            "aux_dimensions": "客户:C002 乙公司",
        },
    ]

    balance, aux_balance = convert_balance_rows(rows)

    assert len(balance) == 1
    assert balance[0]["account_code"] == "1122"
    # 聚合值 = 5000 + 3000 = 8000
    assert balance[0]["closing_balance"] == Decimal("8000")
    # 聚合标记
    re = balance[0].get("raw_extra") or {}
    assert re.get("_aggregated_from_aux") is True
    assert re.get("_aux_row_count") == 2

    assert len(aux_balance) == 2


def test_plain_rows_without_aux_unchanged():
    """场景 C：纯汇总行无任何 aux → 主表原样 1 条，辅助表空。"""
    rows = [
        {"account_code": "1001", "account_name": "库存现金",
         "closing_debit": "120"},
        {"account_code": "4103", "account_name": "本年利润",
         "closing_debit": "10000"},
    ]

    balance, aux_balance = convert_balance_rows(rows)

    assert len(balance) == 2
    assert len(aux_balance) == 0
    codes = {r["account_code"] for r in balance}
    assert codes == {"1001", "4103"}


def test_multiple_accounts_mixed_scenarios():
    """混合场景：A 有汇总+明细 / B 仅明细 / C 纯汇总，主表按组去重。"""
    rows = [
        # A: 汇总 + 2 明细
        {"account_code": "1002", "closing_debit": "307072.27"},
        {"account_code": "1002", "closing_debit": "198431.65",
         "aux_dimensions": "金融机构:A001,工行"},
        {"account_code": "1002", "closing_debit": "108640.62",
         "aux_dimensions": "金融机构:A002,邮储"},
        # B: 仅 2 明细
        {"account_code": "1122", "closing_debit": "5000",
         "aux_dimensions": "客户:C001 甲"},
        {"account_code": "1122", "closing_debit": "3000",
         "aux_dimensions": "客户:C002 乙"},
        # C: 纯汇总
        {"account_code": "1001", "closing_debit": "120"},
    ]

    balance, aux_balance = convert_balance_rows(rows)

    # 主表 3 条（每个 account_code 各 1 条，无重复）
    assert len(balance) == 3
    codes = {r["account_code"] for r in balance}
    assert codes == {"1001", "1002", "1122"}

    # 1002 用汇总行值
    b1002 = next(r for r in balance if r["account_code"] == "1002")
    assert b1002["closing_balance"] == Decimal("307072.27")
    assert not (b1002.get("raw_extra") or {}).get("_aggregated_from_aux")

    # 1122 是聚合行
    b1122 = next(r for r in balance if r["account_code"] == "1122")
    assert b1122["closing_balance"] == Decimal("8000")
    assert (b1122.get("raw_extra") or {}).get("_aggregated_from_aux") is True

    # 1001 纯汇总
    b1001 = next(r for r in balance if r["account_code"] == "1001")
    assert b1001["closing_balance"] == Decimal("120")

    # 辅助表 4 条
    assert len(aux_balance) == 4


def test_multi_dimension_single_row_still_one_main():
    """单行多维度（如"客户:C001;部门:D01"）→ 主表仍仅产出 1 条，辅助表 N 条。"""
    rows = [
        {"account_code": "6601", "account_name": "管理费用",
         "closing_debit": "1000",
         "aux_dimensions": "客户:C001 甲,部门:D01 财务"},
    ]

    balance, aux_balance = convert_balance_rows(rows)

    assert len(balance) == 1
    assert len(aux_balance) == 2
    # 主表是聚合行（因为无汇总行），值等于该单行
    assert balance[0]["closing_balance"] == Decimal("1000")


def test_different_company_codes_not_merged():
    """不同 company_code 下相同 account_code 不应合并。"""
    rows = [
        {"account_code": "1001", "company_code": "COMP01", "closing_debit": "100"},
        {"account_code": "1001", "company_code": "COMP02", "closing_debit": "200"},
    ]

    balance, _ = convert_balance_rows(rows)

    assert len(balance) == 2
    vals = {(r["company_code"], r["closing_balance"]) for r in balance}
    assert vals == {("COMP01", Decimal("100")), ("COMP02", Decimal("200"))}



# ═══════════════════════════════════════════════════════════════════════════
# 多维度冗余存储（YG36 真实场景）
# ═══════════════════════════════════════════════════════════════════════════


def test_multi_dimension_redundant_storage():
    """一行多维度（金融机构 + 银行账户）入 aux_balance 冗余存 N 条。

    YG36 真实数据：
      行 A: 金融机构:YG0001,工商银行;银行账户:3100...  closing=3948.93
      行 B: 金融机构:YG0018,邮储;银行账户:951...       closing=100.00

    预期：
    - 主表 1 条（account_code=1002 去重后）
    - aux_balance 4 条（2 行 × 2 维度，每条记原行金额）
    - 按 aux_type 分组求和 = 主表（这是"冗余存储"的关键性质）
    """
    rows = [
        {
            "account_code": "1002", "account_name": "银行存款",
            "closing_debit": "3948.93",
            "aux_dimensions": "金融机构:YG0001,工商银行;银行账户:3100035219100042014",
        },
        {
            "account_code": "1002", "account_name": "银行存款",
            "closing_debit": "100.00",
            "aux_dimensions": "金融机构:YG0018,中国邮政储蓄银行;银行账户:951004010002007700",
        },
    ]
    balance, aux_balance = convert_balance_rows(rows)

    # 主表：聚合 1 条（因为没有无 aux 的汇总行，走 _aggregate_aux_to_summary 路径）
    assert len(balance) == 1
    assert balance[0]["account_code"] == "1002"
    assert balance[0]["closing_balance"] == Decimal("4048.93")  # 3948.93 + 100
    assert balance[0].get("raw_extra", {}).get("_aggregated_from_aux") is True

    # 辅助表：4 条（每行 2 维度 × 2 行 = 4 条冗余）
    assert len(aux_balance) == 4
    types = [r["aux_type"] for r in aux_balance]
    assert types.count("金融机构") == 2
    assert types.count("银行账户") == 2

    # 按单一维度类型求和 = 主表 closing_balance（冗余存储的关键性质）
    from collections import defaultdict
    sums_by_type: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for r in aux_balance:
        sums_by_type[r["aux_type"]] += r["closing_balance"]

    assert sums_by_type["金融机构"] == Decimal("4048.93")
    assert sums_by_type["银行账户"] == Decimal("4048.93")

    # 反例：所有 aux 行求和 = 父 × 2（N 维度），这证明禁止平铺求和
    flat_sum = sum((r["closing_balance"] for r in aux_balance), Decimal(0))
    assert flat_sum == Decimal("8097.86")  # 父 × 2


def test_multi_dimension_with_summary_row_dedup():
    """有汇总行 + 多维度明细：主表用汇总行，aux_balance 冗余存。"""
    rows = [
        # 汇总行（无 aux）
        {"account_code": "1002", "account_name": "银行存款",
         "closing_debit": "4048.93"},
        # 两行多维度明细
        {
            "account_code": "1002", "account_name": "银行存款",
            "closing_debit": "3948.93",
            "aux_dimensions": "金融机构:YG0001,工商银行;银行账户:3100...",
        },
        {
            "account_code": "1002", "account_name": "银行存款",
            "closing_debit": "100.00",
            "aux_dimensions": "金融机构:YG0018,邮储;银行账户:951...",
        },
    ]
    balance, aux_balance = convert_balance_rows(rows)

    # 主表 1 条（用汇总行，不聚合）
    assert len(balance) == 1
    assert balance[0]["closing_balance"] == Decimal("4048.93")
    assert not (balance[0].get("raw_extra") or {}).get("_aggregated_from_aux")

    # aux_balance 4 条（2 行 × 2 维度）
    assert len(aux_balance) == 4
