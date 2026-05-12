"""F48 / Sprint 8.7: 校验规则说明文档（单一真源）。

对齐 design §D12.2 + requirements F48。

本模块把 ``validator.py`` 中每条 finding code 对应的规则（公式 / 容差 / 范围 /
示例 / 是否可 force）写成 Pydantic model + 模块级列表，给前端独立页面
``/ledger-import/validation-rules`` 展示，并由
``GET /api/ledger-import/validation-rules`` 端点返回。

与 validator.py 的关系：

- validator.py 每条 ``code=...`` 的 finding 在此处都必须有 ``ValidationRuleDoc``
  条目（双向一致性由 ``test_validation_rules_catalog.py`` 强制保证）
- 文档字段（``formula_cn`` / ``tolerance_cn`` / ``why_cn`` / ``example``）
  面向审计助理的中文展示，不做字符串插值

涵盖范围（v1，对齐 validator.py 实际 emit 的 10 个 code）：

- L1：``AMOUNT_NOT_NUMERIC_KEY`` / ``AMOUNT_NOT_NUMERIC_RECOMMENDED``
       / ``DATE_INVALID_KEY`` / ``DATE_INVALID_RECOMMENDED``
       / ``ROW_SKIPPED_KEY_EMPTY``
- L2：``BALANCE_UNBALANCED`` / ``L2_LEDGER_YEAR_OUT_OF_RANGE``
       / ``ACCOUNT_NOT_IN_CHART``
- L3：``BALANCE_LEDGER_MISMATCH`` / ``AUX_ACCOUNT_MISMATCH``

不覆盖：

- 上传/检测阶段的 fatal 码（``FILE_TOO_LARGE`` / ``UNSUPPORTED_FILE_TYPE`` 等）
  —— 已由 ``error_hints.py`` 的 ``ERROR_HINTS`` 提供用户友好文案，规则说明页
  只聚焦"业务校验逻辑"
- F42 规模警告（``EMPTY_LEDGER_WARNING`` / ``SUSPICIOUS_DATASET_SIZE``）
  —— 属 detect 阶段告警，同样走 ``error_hints.py``

使用方式::

    from app.services.ledger_import.validation_rules_catalog import (
        VALIDATION_RULES_CATALOG,
        get_rule_by_code,
    )

    for rule in VALIDATION_RULES_CATALOG:
        print(rule.code, rule.title_cn)

    rule = get_rule_by_code("BALANCE_LEDGER_MISMATCH")
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RuleLevel = Literal["L1", "L2", "L3"]
RuleSeverity = Literal["blocking", "warning"]


class ValidationRuleDoc(BaseModel):
    """单条校验规则说明文档（F48 / design D12.2）。

    字段语义：

    - ``code``              ：与 ``ValidationFinding.code`` 完全对齐
    - ``level`` / ``severity`` ：与 validator.py 里的 level / severity 对齐
    - ``title_cn``          ：规则短标题（中文，前端列表展示）
    - ``formula``           ：英文公式字符串（方便开发/运维对照）
    - ``formula_cn``        ：中文公式（面向审计助理展示）
    - ``tolerance_formula`` ：容差计算公式（无容差的规则传 None）
    - ``tolerance_cn``      ：容差中文说明
    - ``scope_cn``          ：作用范围（按 account_code / 全表 / 按行）
    - ``why_cn``            ：该规则存在的业务意义 / 发现什么问题
    - ``example``           ：对照样例 ``{"inputs": ..., "expected": ...,
      "pass": "...", "fail": "..."}``，None 表示不提供样例
    - ``can_force``         ：是否允许 ``force_activate`` 跳过（L1 全 False，
      L2 除 ``L2_LEDGER_YEAR_OUT_OF_RANGE`` 外皆 True，L3 视具体规则）
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    level: RuleLevel
    severity: RuleSeverity
    title_cn: str
    formula: str
    formula_cn: str
    tolerance_formula: Optional[str] = None
    tolerance_cn: Optional[str] = None
    scope_cn: str
    why_cn: str
    example: Optional[dict[str, Any]] = Field(default=None)
    can_force: bool


# ---------------------------------------------------------------------------
# 规则目录（与 validator.py 的 code 一一对齐）
# ---------------------------------------------------------------------------

VALIDATION_RULES_CATALOG: list[ValidationRuleDoc] = [
    # =============================================================
    # L1 解析期校验
    # =============================================================
    ValidationRuleDoc(
        code="AMOUNT_NOT_NUMERIC_KEY",
        level="L1",
        severity="blocking",
        title_cn="关键金额列非数值（阻断）",
        formula="parse_numeric(value) -> float",
        formula_cn="将关键金额列的字符串解析为数值（允许千分位逗号）",
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按行逐单元格检查关键列（如 debit_amount / credit_amount / opening_balance / closing_balance）",
        why_cn=(
            "关键金额列出现无法解析的值会直接导致入库金额错误，"
            "必须在激活前修复，因此此码不可 force 跳过"
        ),
        example={
            "inputs": {"debit_amount": "abc", "credit_amount": "0"},
            "expected": "数值（如 100.00）",
            "fail": "‘abc’ 非数值，blocking",
            "pass": "‘1,234.56’ 可正常解析为 1234.56",
        },
        can_force=False,
    ),
    ValidationRuleDoc(
        code="AMOUNT_NOT_NUMERIC_RECOMMENDED",
        level="L1",
        severity="warning",
        title_cn="次关键金额列非数值（警告）",
        formula="parse_numeric(value) -> float; on failure set NULL",
        formula_cn="次关键金额列解析失败时置 NULL 并记 warning",
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按行逐单元格检查次关键金额列（如 opening_debit / closing_credit）",
        why_cn=(
            "次关键列允许缺失，解析失败时不阻断但保留告警提醒审计助理核查"
        ),
        example={
            "inputs": {"opening_debit": "xx"},
            "expected": "数值或空",
            "fail": "‘xx’ 非数值，warning + 置 NULL",
            "pass": "‘100.00’ 正常解析",
        },
        can_force=False,  # warning 不需要 force，始终放行
    ),
    ValidationRuleDoc(
        code="DATE_INVALID_KEY",
        level="L1",
        severity="blocking",
        title_cn="关键日期列无法解析（阻断）",
        formula="parse_date(value) -> datetime",
        formula_cn=(
            "将关键日期列解析为日期"
            "（支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD / Excel 序列号）"
        ),
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按行逐单元格检查 voucher_date（序时账关键列）",
        why_cn="凭证日期错误会导致年度过滤、月度分析、L2 年度校验错位",
        example={
            "inputs": {"voucher_date": "not-a-date"},
            "expected": "合法日期（推荐 YYYY-MM-DD）",
            "fail": "‘not-a-date’ 无法解析，blocking",
            "pass": "‘2025-03-15’ 或 Excel 序列号 45731",
        },
        can_force=False,
    ),
    ValidationRuleDoc(
        code="DATE_INVALID_RECOMMENDED",
        level="L1",
        severity="warning",
        title_cn="次关键日期列无法解析（警告）",
        formula="parse_date(value) -> datetime; on failure set NULL",
        formula_cn="次关键日期列解析失败时置 NULL 并记 warning",
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按行逐单元格检查次关键日期列",
        why_cn="次关键日期列缺失不影响核心校验，但保留告警提醒补录",
        example=None,
        can_force=False,
    ),
    ValidationRuleDoc(
        code="ROW_SKIPPED_KEY_EMPTY",
        level="L1",
        severity="warning",
        title_cn="整行关键列空值被跳过（脏行容忍）",
        formula="any(key_col is empty for key_col in non_exclusive_key_cols)",
        formula_cn=(
            "企业级宽容策略：整行有值但非借贷互斥对的关键列为空时跳过该行，"
            "不阻断整批激活"
        ),
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按行整体判断（预检阶段）",
        why_cn=(
            "真实业务数据无法 100% 干净，脏行（如缺科目代码）应被静默过滤而非"
            "阻断整批激活；被跳过行数记 warning 供审计助理核查"
        ),
        example={
            "inputs": {"account_code": "", "opening_balance": 1000},
            "expected": "整行写入",
            "fail": "account_code 空但其他字段有值 → 跳过 + warning",
            "pass": "所有字段都空 → 静默跳过（空白尾行）",
        },
        can_force=False,
    ),
    # =============================================================
    # L2 全量后校验
    # =============================================================
    ValidationRuleDoc(
        code="BALANCE_UNBALANCED",
        level="L2",
        severity="blocking",
        title_cn="序时账借贷合计不平衡",
        formula="sum(debit_amount) == sum(credit_amount)",
        formula_cn="借方发生额合计 应 等于 贷方发生额合计",
        tolerance_formula="abs(sum_debit - sum_credit) <= 0.01",
        tolerance_cn="固定容差 0.01 元（仅防浮点精度误差）",
        scope_cn="按 dataset 全量聚合 tb_ledger",
        why_cn=(
            "借贷合计不平衡说明序时账不完整或存在金额录入错误；"
            "explanation.sample_voucher_ids 按单凭证借贷差额降序给出前 10 条候选"
        ),
        example={
            "inputs": {"sum_debit": 300.0, "sum_credit": 250.0},
            "expected": "差额 ≤ 0.01 元",
            "fail": "差额 50 元 → blocking",
            "pass": "差额 0.005 元 → 通过（浮点容差内）",
        },
        can_force=True,
    ),
    ValidationRuleDoc(
        code="L2_LEDGER_YEAR_OUT_OF_RANGE",
        level="L2",
        severity="blocking",
        title_cn="序时账凭证日期超出年度范围（强制不可跳过）",
        formula="year_start <= voucher_date <= year_end",
        formula_cn=(
            "凭证日期 应 在年度区间 [year-01-01, year-12-31] 内"
        ),
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按 dataset 扫描 tb_ledger 所有 voucher_date",
        why_cn=(
            "越界凭证会导致年度分析错位、合并报表失衡；"
            "此码明确不可被 force 跳过，必须修复源数据"
        ),
        example={
            "inputs": {
                "year": 2025,
                "bounds": ["2025-01-01", "2025-12-31"],
                "violating_voucher_dates": ["2024-12-31", "2026-01-01"],
            },
            "expected": "所有 voucher_date ∈ [2025-01-01, 2025-12-31]",
            "fail": "存在 2024-12-31 凭证 → blocking 且不可 force",
            "pass": "所有日期在年度范围内",
        },
        can_force=False,
    ),
    ValidationRuleDoc(
        code="ACCOUNT_NOT_IN_CHART",
        level="L2",
        severity="blocking",
        title_cn="序时账科目不在科目表中",
        formula="ledger.account_code IN (SELECT account_code FROM account_chart)",
        formula_cn="序时账中出现的每个科目代码都应在已导入的科目表中存在",
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn=(
            "仅当该 dataset 导入了 tb_account_chart 时触发；"
            "按 account_code 做 LEFT JOIN 找缺失"
        ),
        why_cn=(
            "科目表是科目代码的真源，序时账出现未登记科目说明"
            "源数据异常或科目表未同步更新"
        ),
        example={
            "inputs": {"ledger_account_codes": ["1001", "1002", "9999"]},
            "expected": "所有 account_code 都能在 account_chart 查到",
            "fail": "‘9999’ 不在科目表 → blocking",
            "pass": "全部命中",
        },
        can_force=True,
    ),
    # =============================================================
    # L3 跨表校验
    # =============================================================
    ValidationRuleDoc(
        code="BALANCE_LEDGER_MISMATCH",
        level="L3",
        severity="blocking",
        title_cn="余额表 vs 序时账累计一致性校对",
        formula=(
            "closing_balance = opening_balance + sum(debit_amount) "
            "- sum(credit_amount)"
        ),
        formula_cn="期末余额 = 期初余额 + 借方累计 - 贷方累计",
        tolerance_formula="min(1.0 + magnitude * 0.00001, 100.0)",
        tolerance_cn=(
            "动态容差：基础 1.0 元 + 最大金额量级 × 0.001%，上限 100 元；"
            "magnitude = max(|opening|, |closing|, |sum_debit|, |sum_credit|, 1)"
        ),
        scope_cn="按 account_code 逐科目 LEFT JOIN tb_balance × tb_ledger",
        why_cn=(
            "余额表与序时账必须一致，差异说明存在漏过账、期初错录、跨期调整未入账"
            "等问题；explanation.diff_breakdown 给出 4 项贡献拆解定位差异来源"
        ),
        example={
            "inputs": {
                "account_code": "1001",
                "opening_balance": 100,
                "sum_debit": 50,
                "sum_credit": 30,
                "actual_closing": 130,
            },
            "expected": 120,
            "fail": "实际 130 vs 期望 120 → diff=10 > tol=1.0013 → blocking",
            "pass": "actual_closing=120.5 → diff=0.5 < tol=1.0013 → 通过",
        },
        can_force=True,
    ),
    ValidationRuleDoc(
        code="AUX_ACCOUNT_MISMATCH",
        level="L3",
        severity="warning",
        title_cn="辅助表科目不在主表中",
        formula=(
            "aux_balance.account_code IN (SELECT account_code FROM balance) "
            "AND aux_ledger.account_code IN (SELECT account_code FROM ledger)"
        ),
        formula_cn=(
            "辅助余额表 / 辅助序时账中的 account_code 应同时存在于"
            "主余额表 / 主序时账中"
        ),
        tolerance_formula=None,
        tolerance_cn=None,
        scope_cn="按 dataset 对 tb_aux_balance × tb_balance、tb_aux_ledger × tb_ledger 分别做 LEFT JOIN",
        why_cn=(
            "辅助科目应是主科目的明细补充，出现主表无匹配说明科目代码错录"
            "或辅助表导出了未启用科目；warning 级别不阻断"
        ),
        example={
            "inputs": {
                "aux_balance_codes": ["1001", "1002.01"],
                "main_balance_codes": ["1001", "1002"],
            },
            "expected": "aux_balance 所有 code 都能在 main_balance 查到",
            "fail": "‘1002.01’ 在辅助表但主表只有 ‘1002’ → warning",
            "pass": "所有辅助 code 都能在主表命中",
        },
        can_force=True,
    ),
]


# ---------------------------------------------------------------------------
# 查询辅助
# ---------------------------------------------------------------------------


def get_rule_by_code(code: str) -> Optional[ValidationRuleDoc]:
    """按 ``code`` 精确查找规则文档；未命中返回 ``None``。

    time complexity: O(n)，n ≈ 10（小常量，足够）。对于极高并发场景
    可在模块级缓存 dict，但目前 API 端点 QPS 很低，简单线性查足够。
    """
    for rule in VALIDATION_RULES_CATALOG:
        if rule.code == code:
            return rule
    return None


__all__ = [
    "ValidationRuleDoc",
    "VALIDATION_RULES_CATALOG",
    "get_rule_by_code",
]
