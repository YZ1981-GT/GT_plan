"""3 级校验 — L1 解析期 / L2 全量后 / L3 跨表。

职责（见 design.md §19 / Sprint 2 Task 35-38）：

- L1 (按列分层) :
  - 关键列     → 金额非数 / 日期非法 / 值为空 触发 `blocking`。
  - 次关键列   → 同类问题触发 `warning` 并把该值置 NULL。
  - 非关键列   → 不校验，原样进 `raw_extra`。
- L2           : 借贷平衡、年度范围、科目存在性。
- L3           : 余额期末 = 序时累计（容差 1 元）、辅助与主表科目一致性。
- `force_activate` : 跳过 L2/L3 的 blocking（需审批链）。

返回 `ValidationFinding` 列表 + `ActivationGate` 判定。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny

from .detection_types import (
    KEY_COLUMNS,
    RECOMMENDED_COLUMNS,
    TableType,
)

# ---------------------------------------------------------------------------
# Finding explanation 子结构（F47）
# ---------------------------------------------------------------------------


class ExplanationBase(BaseModel):
    """校验发现的可解释元数据基类（F47 / design §D12.1）。

    所有字段都是人类/机器混合语义：

    - ``formula``     ：英文公式字符串（如 ``"closing = opening + sum(debit) - sum(credit)"``）
    - ``formula_cn``  ：中文公式（展示给审计助理看）
    - ``inputs``      ：代入值字典，键是公式中各个变量名
    - ``computed``    ：公式求出的中间值（expected / actual / diff / tolerance 等）
    - ``hint``        ：中文建议（如 "检查是否有凭证漏过账"）
    """

    model_config = ConfigDict(extra="forbid")

    formula: str
    formula_cn: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    computed: dict[str, Any] = Field(default_factory=dict)
    hint: str = ""


class BalanceMismatchExplanation(ExplanationBase):
    """L3 ``BALANCE_LEDGER_MISMATCH`` 专属解释。

    额外字段：

    - ``diff_breakdown`` ：差异来源分解（opening / sum_debit / sum_credit
      / closing 四条权重），每条 ``{source, value, weight}``
    - ``tolerance_formula`` ：容差计算公式字符串
    """

    diff_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    tolerance_formula: str = "min(1.0 + magnitude * 0.00001, 100.0)"


class UnbalancedExplanation(ExplanationBase):
    """L2 ``BALANCE_UNBALANCED`` 专属解释。

    额外字段 ``sample_voucher_ids`` 保留导致借贷差异最大的前 10 条凭证号。
    """

    sample_voucher_ids: list[str] = Field(default_factory=list)


class YearOutOfRangeExplanation(ExplanationBase):
    """L2 ``L2_LEDGER_YEAR_OUT_OF_RANGE`` 专属解释。

    额外字段：

    - ``year_bounds`` ：(year_start, year_end) 日期串元组
    - ``out_of_range_samples`` ：越界凭证样本（前 10 条，``{voucher_no, voucher_date}``）
    """

    year_bounds: tuple[str, str]
    out_of_range_samples: list[dict[str, Any]] = Field(default_factory=list)


class L1TypeErrorExplanation(ExplanationBase):
    """L1 类型错误（AMOUNT / DATE）专属解释。

    额外字段：

    - ``field_name``    ：出错的标准字段名
    - ``actual_value``  ：原始字符串（可能被截断到 128 char）
    - ``expected_type`` ：期望类型（``numeric`` / ``date``）
    """

    field_name: str
    actual_value: str
    expected_type: Literal["numeric", "date"]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class ValidationFinding(BaseModel):
    """单条校验发现（F47：附可选 explanation；F49：location.drill_down）。

    ``location`` 为 dict（保持向后兼容），常见 key：

    - ``file`` / ``sheet`` / ``row`` / ``column`` ：定位信息
    - ``drill_down`` ：F49 差异下钻 payload（可选），结构如::

        {
            "target": "tb_ledger" | "tb_aux_ledger" | "tb_aux_balance",
            "filter": {"dataset_id": "<uuid>", "account_code": "1001", ...},
            "sample_ids": ["<uuid1>", "<uuid2>", "<uuid3>"],
            "expected_count": 458,
        }

      前端 ``DiagnosticPanel.vue`` 用 ``target`` + ``filter`` 打开
      ``LedgerPenetration.vue`` 穿透抽屉，``sample_ids`` 用于高亮首屏行。
      仅 L3 findings 当前填充此字段，L1/L2 可按需扩展。
    """

    level: Literal["L1", "L2", "L3"]
    severity: Literal["fatal", "blocking", "warning"]
    code: str
    message: str
    location: dict  # { file, sheet, row, column, drill_down? }
    blocking: bool  # True when this finding blocks activation (unless force)
    # SerializeAsAny 确保子类特有字段（diff_breakdown / sample_voucher_ids 等）
    # 在 model_dump() / API JSON 输出中保留而不被基类截断
    explanation: Optional[SerializeAsAny[ExplanationBase]] = None


class ActivationGate(BaseModel):
    """激活门判定结果。"""

    allowed: bool
    blocking_findings: list[ValidationFinding]
    warning_findings: list[ValidationFinding]


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------

# 金额类字段名集合（用于判断是否需要做数值校验）
_AMOUNT_FIELDS: set[str] = {
    "debit_amount",
    "credit_amount",
    "opening_balance",
    "closing_balance",
    "opening_debit",
    "opening_credit",
    "closing_debit",
    "closing_credit",
}

# 日期类字段名集合
_DATE_FIELDS: set[str] = {
    "voucher_date",
}

# L2_LEDGER_YEAR_OUT_OF_RANGE 不可被 force 跳过
_NON_FORCEABLE_CODES: frozenset[str] = frozenset({
    "L2_LEDGER_YEAR_OUT_OF_RANGE",
})

# 日期解析格式列表
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _try_parse_numeric(value: object) -> Optional[float]:
    """尝试将值解析为数值，失败返回 None。"""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _try_parse_date(value: object) -> Optional[datetime]:
    """尝试将值解析为日期，支持多种格式和 Excel 序列号。"""
    if value is None:
        return None
    # 如果已经是 datetime 对象
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if s == "":
        return None
    # 尝试标准格式
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 尝试 Excel 序列号（纯数字，范围 1-100000 大致覆盖 1900-2173）
    try:
        serial = float(s)
        if 1 <= serial <= 100000:
            # Excel 序列号：1 = 1900-01-01（Excel 有 1900 闰年 bug，这里简化处理）
            from datetime import timedelta

            base = datetime(1899, 12, 30)
            return base + timedelta(days=int(serial))
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _is_empty(value: object) -> bool:
    """判断值是否为空。"""
    if value is None:
        return True
    s = str(value).strip()
    return s == ""


# ---------------------------------------------------------------------------
# Level 1 — Parse-time validation
# ---------------------------------------------------------------------------


def validate_l1(
    rows: list[dict],
    table_type: TableType,
    column_mapping: dict[str, str],  # {original_header: standard_field}
    *,
    file_name: str = "",
    sheet_name: str = "",
) -> tuple[list[ValidationFinding], list[dict]]:
    """L1 validation: per-row, per-column checks (企业级宽容策略).

    Returns (findings, cleaned_rows) — cleaned_rows 只包含"可入库"的行。

    ## 整行级别（新增，企业级通用规则）
    - 整行所有 key col（除 exclusive_pair 外）都空 → 静默跳过（空白行/尾部行）
    - 部分 key col 空、其他有值 → 记 `ROW_SKIPPED_KEY_EMPTY` warning，跳过该行
      （脏数据容忍：不阻止整批激活，仅记录被跳过行数）
    - exclusive_pair（借贷互斥 / 余额零值）内字段允许全空（原有语义）

    ## 字段级别
    - AMOUNT 字段（debit_amount / opening_balance / 等）：值非空但不可解析为数值
        - key tier：blocking `AMOUNT_NOT_NUMERIC_KEY`
        - recommended tier：warning + 值置 None
    - DATE 字段（voucher_date）：值非空但不可解析为日期
        - key tier：blocking `DATE_INVALID_KEY`
        - recommended tier：warning + 值置 None
    - extra 字段：不做任何校验（原样进 raw_extra）
    """
    key_cols = KEY_COLUMNS.get(table_type, set())
    rec_cols = RECOMMENDED_COLUMNS.get(table_type, set())

    # Build reverse mapping: standard_field → original_header (for reference)
    # But rows are already keyed by standard_field names
    # The column_mapping tells us which original headers map to which standard fields
    # Rows dict keys are standard_field names

    # S7 修复：某些"关键列组"属于合法可全空场景，EMPTY 检查不做 blocking
    # 序时账：debit_amount / credit_amount（借贷只出现一个，另一个必空）
    # 余额表：8 个金额字段（分列 opening_debit/opening_credit/closing_debit/closing_credit
    #                     + 合计 opening_balance/closing_balance/debit_amount/credit_amount）
    #         允许全部为空（零余额行，期初期末均为 0 的科目是合法数据）
    # 语义：exclusive_group 内的字段不强制 EMPTY blocking，
    #       但值非空时仍校验能否解析为数值（AMOUNT 类型检查保留）
    _EXCLUSIVE_KEY_PAIRS: dict[str, set[str]] = {
        "ledger": {"debit_amount", "credit_amount"},
        "aux_ledger": {"debit_amount", "credit_amount"},
        "balance": {
            "opening_balance", "closing_balance",
            "debit_amount", "credit_amount",
            "opening_debit", "opening_credit",
            "closing_debit", "closing_credit",
        },
        "aux_balance": {
            "opening_balance", "closing_balance",
            "debit_amount", "credit_amount",
            "opening_debit", "opening_credit",
            "closing_debit", "closing_credit",
        },
    }
    exclusive_pair = _EXCLUSIVE_KEY_PAIRS.get(table_type, set())

    findings: list[ValidationFinding] = []
    cleaned_rows: list[dict] = []

    # S7 企业级规则：key column 空值处理策略
    # 1. 整行所有字段（key + recommended + extra）都空 → 纯空白行，静默跳过
    # 2. 整行有值但非 exclusive_pair 的 key col 有空 → 脏数据行 warning + 跳过
    # 3. AMOUNT / DATE 类型错误 → warning + 该字段置 None（原有逻辑）
    non_exclusive_key_cols = key_cols - exclusive_pair

    for row_idx, row in enumerate(rows):
        # ── 预检 1：整行是否所有字段都空（纯空白行/尾部行）──
        row_all_empty = all(_is_empty(v) for v in row.values())
        if row_all_empty:
            continue  # 静默跳过

        # ── 预检 2：非 exclusive 的 key col 是否有空（脏数据行）──
        row_empty_key_names = [
            fn for fn in non_exclusive_key_cols if _is_empty(row.get(fn))
        ]
        if row_empty_key_names:
            findings.append(
                ValidationFinding(
                    level="L1",
                    severity="warning",
                    code="ROW_SKIPPED_KEY_EMPTY",
                    message=(
                        f"第 {row_idx} 行因关键列空值被跳过："
                        f"{', '.join(row_empty_key_names)}"
                    ),
                    location={
                        "file": file_name,
                        "sheet": sheet_name,
                        "row": row_idx,
                        "column": ",".join(row_empty_key_names),
                    },
                    blocking=False,
                )
            )
            continue  # 整行跳过，不写入

        cleaned_row = dict(row)  # shallow copy

        for field_name, value in row.items():
            # Determine tier
            if field_name in key_cols:
                tier = "key"
            elif field_name in rec_cols:
                tier = "recommended"
            else:
                # Extra column — no validation
                continue

            location = {
                "file": file_name,
                "sheet": sheet_name,
                "row": row_idx,
                "column": field_name,
            }

            # --- EMPTY check (已由预检 1/2 处理，此处 defensive) ---
            if tier == "key" and _is_empty(value):
                # 预检已处理：空白行跳过、脏数据行跳过+warning
                # 走到这里只可能是 exclusive_pair 成员（允许全空），直接放行
                continue

            # --- AMOUNT check ---
            if field_name in _AMOUNT_FIELDS:
                if not _is_empty(value) and _try_parse_numeric(value) is None:
                    actual_value_str = str(value)[:128]
                    amount_explanation = L1TypeErrorExplanation(
                        formula=f"parse_numeric({field_name}) -> float",
                        formula_cn=f"将关键列 {field_name} 的字符串解析为数值（允许千分位逗号）",
                        inputs={"raw_value": actual_value_str},
                        computed={"parse_result": None},
                        hint="检查该值是否为合法数字（如 1234.56 或 1,234.56）；若为空建议填 0",
                        field_name=field_name,
                        actual_value=actual_value_str,
                        expected_type="numeric",
                    )
                    if tier == "key":
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="blocking",
                                code="AMOUNT_NOT_NUMERIC_KEY",
                                message=(
                                    f"关键列 '{field_name}' 值 '{value}' "
                                    f"非数值（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=True,
                                explanation=amount_explanation,
                            )
                        )
                    else:
                        # recommended → warning + NULL
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="warning",
                                code="AMOUNT_NOT_NUMERIC_RECOMMENDED",
                                message=(
                                    f"次关键列 '{field_name}' 值 '{value}' "
                                    f"非数值，已置 NULL（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=False,
                                explanation=amount_explanation,
                            )
                        )
                        cleaned_row[field_name] = None

            # --- DATE check ---
            elif field_name in _DATE_FIELDS:
                if not _is_empty(value) and _try_parse_date(value) is None:
                    actual_value_str = str(value)[:128]
                    date_explanation = L1TypeErrorExplanation(
                        formula=f"parse_date({field_name}) -> datetime",
                        formula_cn=(
                            f"将关键列 {field_name} 的字符串解析为日期"
                            f"（支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD / Excel 序列号）"
                        ),
                        inputs={"raw_value": actual_value_str},
                        computed={"parse_result": None},
                        hint="检查该值是否为合法日期（推荐 YYYY-MM-DD 格式）；Excel 序列号会自动换算",
                        field_name=field_name,
                        actual_value=actual_value_str,
                        expected_type="date",
                    )
                    if tier == "key":
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="blocking",
                                code="DATE_INVALID_KEY",
                                message=(
                                    f"关键列 '{field_name}' 值 '{value}' "
                                    f"无法解析为日期（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=True,
                                explanation=date_explanation,
                            )
                        )
                    else:
                        # recommended → warning + NULL
                        findings.append(
                            ValidationFinding(
                                level="L1",
                                severity="warning",
                                code="DATE_INVALID_RECOMMENDED",
                                message=(
                                    f"次关键列 '{field_name}' 值 '{value}' "
                                    f"无法解析为日期，已置 NULL（第 {row_idx} 行）"
                                ),
                                location=location,
                                blocking=False,
                                explanation=date_explanation,
                            )
                        )
                        cleaned_row[field_name] = None

        cleaned_rows.append(cleaned_row)

    return findings, cleaned_rows


# ---------------------------------------------------------------------------
# Level 2 — Post-write validation
# ---------------------------------------------------------------------------


async def validate_l2(
    db,
    *,
    dataset_id: UUID,
    year: int,
    project_id: UUID,
) -> list[ValidationFinding]:
    """L2 validation: aggregate checks after all data is written.

    Checks:
    1. BALANCE_UNBALANCED: sum(debit_amount) != sum(credit_amount) in tb_ledger
    2. L2_LEDGER_YEAR_OUT_OF_RANGE: any voucher_date outside [year-01-01, year-12-31]
    3. ACCOUNT_NOT_IN_CHART: account_code in tb_ledger not found in account_chart
       (only if account_chart was imported)

    All findings are blocking=True by default (can be force-skipped).
    """
    from sqlalchemy import text

    findings: list[ValidationFinding] = []

    # --- Check 1: Debit/Credit balance in tb_ledger ---
    result = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(debit_amount), 0) AS total_debit,
                COALESCE(SUM(credit_amount), 0) AS total_credit
            FROM tb_ledger
            WHERE dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    row = result.fetchone()
    if row is not None:
        total_debit = float(row.total_debit)
        total_credit = float(row.total_credit)
        if abs(total_debit - total_credit) > 0.01:
            # 取借贷差异贡献最大的前 10 条凭证号（按 |debit - credit| 降序）
            sample_result = await db.execute(
                text("""
                    SELECT voucher_no,
                           COALESCE(SUM(debit_amount), 0) AS vd,
                           COALESCE(SUM(credit_amount), 0) AS vc
                    FROM tb_ledger
                    WHERE dataset_id = :dataset_id
                      AND voucher_no IS NOT NULL
                    GROUP BY voucher_no
                    ORDER BY ABS(COALESCE(SUM(debit_amount), 0)
                                 - COALESCE(SUM(credit_amount), 0)) DESC
                    LIMIT 10
                """),
                {"dataset_id": str(dataset_id)},
            )
            sample_voucher_ids = [r.voucher_no for r in sample_result.fetchall()]

            diff_value = round(total_debit - total_credit, 4)
            explanation = UnbalancedExplanation(
                formula="sum(debit_amount) == sum(credit_amount)",
                formula_cn="借方发生额合计 应 等于 贷方发生额合计",
                inputs={
                    "sum_debit": round(total_debit, 2),
                    "sum_credit": round(total_credit, 2),
                },
                computed={
                    "diff": diff_value,
                    "abs_diff": abs(diff_value),
                    "tolerance": 0.01,
                },
                hint=(
                    "检查是否有凭证只录入了一侧（漏过账）或金额错录；"
                    "`sample_voucher_ids` 是按单凭证借贷差额降序的前 10 条候选，可优先排查"
                ),
                sample_voucher_ids=sample_voucher_ids,
            )
            findings.append(
                ValidationFinding(
                    level="L2",
                    severity="blocking",
                    code="BALANCE_UNBALANCED",
                    message=(
                        f"序时账借贷不平衡：借方合计 {total_debit:.2f}，"
                        f"贷方合计 {total_credit:.2f}，"
                        f"差额 {abs(total_debit - total_credit):.2f}"
                    ),
                    location={"file": "", "sheet": "", "row": -1, "column": ""},
                    blocking=True,
                    explanation=explanation,
                )
            )

    # --- Check 2: Voucher date out of year range ---
    result = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM tb_ledger
            WHERE dataset_id = :dataset_id
              AND (
                  voucher_date < :year_start
                  OR voucher_date > :year_end
              )
        """),
        {
            "dataset_id": str(dataset_id),
            "year_start": f"{year}-01-01",
            "year_end": f"{year}-12-31",
        },
    )
    row = result.fetchone()
    if row is not None and row.cnt > 0:
        # 抽取越界样本（前 10 条，含 voucher_no + voucher_date）
        sample_result = await db.execute(
            text("""
                SELECT voucher_no, voucher_date
                FROM tb_ledger
                WHERE dataset_id = :dataset_id
                  AND (
                      voucher_date < :year_start
                      OR voucher_date > :year_end
                  )
                ORDER BY voucher_date
                LIMIT 10
            """),
            {
                "dataset_id": str(dataset_id),
                "year_start": f"{year}-01-01",
                "year_end": f"{year}-12-31",
            },
        )
        out_of_range_samples: list[dict[str, Any]] = []
        for r in sample_result.fetchall():
            vd = r.voucher_date
            out_of_range_samples.append(
                {
                    "voucher_no": r.voucher_no,
                    "voucher_date": vd.isoformat() if hasattr(vd, "isoformat") else str(vd),
                }
            )

        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"
        explanation = YearOutOfRangeExplanation(
            formula="year_start <= voucher_date <= year_end",
            formula_cn="凭证日期 应 在年度区间 [year_start, year_end] 内",
            inputs={
                "year": year,
                "year_start": year_start,
                "year_end": year_end,
            },
            computed={
                "out_of_range_count": int(row.cnt),
            },
            hint=(
                "检查越界凭证是否应归属其他年度（如跨年调整）；"
                "L2_LEDGER_YEAR_OUT_OF_RANGE 不可被 force 跳过，必须修复源数据"
            ),
            year_bounds=(year_start, year_end),
            out_of_range_samples=out_of_range_samples,
        )
        findings.append(
            ValidationFinding(
                level="L2",
                severity="blocking",
                code="L2_LEDGER_YEAR_OUT_OF_RANGE",
                message=(
                    f"序时账中有 {row.cnt} 条记录的凭证日期"
                    f"不在 {year} 年度范围内（{year}-01-01 ~ {year}-12-31）"
                ),
                location={"file": "", "sheet": "", "row": -1, "column": "voucher_date"},
                blocking=True,
                explanation=explanation,
            )
        )

    # --- Check 3: Account code not in chart (only if chart exists) ---
    result = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM tb_account_chart
            WHERE dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    chart_row = result.fetchone()
    has_chart = chart_row is not None and chart_row.cnt > 0

    if has_chart:
        result = await db.execute(
            text("""
                SELECT DISTINCT l.account_code
                FROM tb_ledger l
                LEFT JOIN tb_account_chart c
                    ON c.dataset_id = l.dataset_id
                    AND c.account_code = l.account_code
                WHERE l.dataset_id = :dataset_id
                  AND c.account_code IS NULL
            """),
            {"dataset_id": str(dataset_id)},
        )
        missing_codes = [r.account_code for r in result.fetchall()]
        if missing_codes:
            sample = missing_codes[:10]
            findings.append(
                ValidationFinding(
                    level="L2",
                    severity="blocking",
                    code="ACCOUNT_NOT_IN_CHART",
                    message=(
                        f"序时账中有 {len(missing_codes)} 个科目代码"
                        f"不在科目表中：{', '.join(sample)}"
                        + ("..." if len(missing_codes) > 10 else "")
                    ),
                    location={
                        "file": "",
                        "sheet": "",
                        "row": -1,
                        "column": "account_code",
                    },
                    blocking=True,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Level 3 — Cross-table validation
# ---------------------------------------------------------------------------


async def validate_l3(
    db,
    *,
    dataset_id: UUID,
    project_id: UUID,
) -> list[ValidationFinding]:
    """L3 validation: cross-table consistency checks.

    Checks:
    1. BALANCE_LEDGER_MISMATCH: For each account_code,
       tb_balance.closing_balance != tb_balance.opening_balance
           + sum(tb_ledger.debit) - sum(tb_ledger.credit)
       Tolerance: dynamic — base 1.0 + magnitude × 0.001%, cap 100 → blocking
    2. AUX_ACCOUNT_MISMATCH: account_codes in tb_aux_balance/tb_aux_ledger
       that don't exist in tb_balance/tb_ledger → warning (not blocking)
    """
    from sqlalchemy import text

    findings: list[ValidationFinding] = []

    # --- Check 1: Balance vs Ledger mismatch ---
    result = await db.execute(
        text("""
            SELECT
                b.account_code,
                b.opening_balance,
                b.closing_balance,
                COALESCE(l.sum_debit, 0) AS sum_debit,
                COALESCE(l.sum_credit, 0) AS sum_credit
            FROM tb_balance b
            LEFT JOIN (
                SELECT
                    account_code,
                    SUM(debit_amount) AS sum_debit,
                    SUM(credit_amount) AS sum_credit
                FROM tb_ledger
                WHERE dataset_id = :dataset_id
                GROUP BY account_code
            ) l ON l.account_code = b.account_code
            WHERE b.dataset_id = :dataset_id
        """),
        {"dataset_id": str(dataset_id)},
    )
    rows = result.fetchall()
    mismatch_accounts: list[str] = []
    # 保留第一条差异最大的科目用于 explanation
    sample_mismatch: Optional[dict[str, Any]] = None
    for row in rows:
        opening = float(row.opening_balance) if row.opening_balance is not None else 0.0
        closing = float(row.closing_balance) if row.closing_balance is not None else 0.0
        sum_debit = float(row.sum_debit)
        sum_credit = float(row.sum_credit)
        expected_closing = opening + sum_debit - sum_credit
        diff = abs(closing - expected_closing)
        # S7: 动态容差——按金额量级调整（小金额 1 元，大金额按比例）
        # 基础容差 1 元 + 金额量级的 0.001%（万分之一），上限 100 元
        magnitude = max(abs(opening), abs(closing), abs(sum_debit), abs(sum_credit), 1.0)
        tolerance = min(1.0 + magnitude * 0.00001, 100.0)
        if diff > tolerance:
            mismatch_accounts.append(row.account_code)
            if sample_mismatch is None or diff > sample_mismatch["diff"]:
                sample_mismatch = {
                    "account_code": row.account_code,
                    "opening_balance": round(opening, 2),
                    "sum_debit": round(sum_debit, 2),
                    "sum_credit": round(sum_credit, 2),
                    "expected_closing": round(expected_closing, 2),
                    "actual_closing": round(closing, 2),
                    "diff": round(diff, 4),
                    "tolerance": round(tolerance, 4),
                    "magnitude": round(magnitude, 2),
                }

    if mismatch_accounts:
        sample = mismatch_accounts[:10]
        explanation: Optional[BalanceMismatchExplanation] = None
        # F49 / Sprint 8.13: 构造 drill_down 让前端直达穿透抽屉
        drill_down: Optional[dict[str, Any]] = None
        if sample_mismatch is not None:
            mismatch_code = sample_mismatch["account_code"]
            # 取差异最大科目的前 3 条 tb_ledger.id 作为 sample_ids
            sid_result = await db.execute(
                text("""
                    SELECT id FROM tb_ledger
                    WHERE dataset_id = :dataset_id
                      AND account_code = :account_code
                    ORDER BY voucher_date, voucher_no
                    LIMIT 3
                """),
                {
                    "dataset_id": str(dataset_id),
                    "account_code": mismatch_code,
                },
            )
            sample_ids = [str(r.id) for r in sid_result.fetchall()]
            # 取该科目总行数作为 expected_count
            cnt_result = await db.execute(
                text("""
                    SELECT COUNT(*) AS cnt FROM tb_ledger
                    WHERE dataset_id = :dataset_id
                      AND account_code = :account_code
                """),
                {
                    "dataset_id": str(dataset_id),
                    "account_code": mismatch_code,
                },
            )
            cnt_row = cnt_result.fetchone()
            expected_count = int(cnt_row.cnt) if cnt_row is not None else 0
            drill_down = {
                "target": "tb_ledger",
                "filter": {
                    "dataset_id": str(dataset_id),
                    "account_code": mismatch_code,
                },
                "sample_ids": sample_ids,
                "expected_count": expected_count,
            }
            # diff_breakdown：把期末余额拆成 4 个来源（符号表示权重）
            diff_breakdown = [
                {
                    "source": "opening_balance",
                    "value": sample_mismatch["opening_balance"],
                    "weight": "+",
                },
                {
                    "source": "sum_debit",
                    "value": sample_mismatch["sum_debit"],
                    "weight": "+",
                },
                {
                    "source": "sum_credit",
                    "value": sample_mismatch["sum_credit"],
                    "weight": "-",
                },
                {
                    "source": "actual_closing_balance",
                    "value": sample_mismatch["actual_closing"],
                    "weight": "=",
                },
            ]
            explanation = BalanceMismatchExplanation(
                formula=(
                    "closing_balance = opening_balance + sum(debit_amount)"
                    " - sum(credit_amount)"
                ),
                formula_cn=(
                    "期末余额 = 期初余额 + 借方累计 - 贷方累计"
                    "（按科目逐行核对，容差动态）"
                ),
                inputs={
                    "account_code": sample_mismatch["account_code"],
                    "opening_balance": sample_mismatch["opening_balance"],
                    "sum_debit": sample_mismatch["sum_debit"],
                    "sum_credit": sample_mismatch["sum_credit"],
                    "actual_closing_balance": sample_mismatch["actual_closing"],
                },
                computed={
                    "expected_closing": sample_mismatch["expected_closing"],
                    "diff": sample_mismatch["diff"],
                    "tolerance": sample_mismatch["tolerance"],
                    "magnitude": sample_mismatch["magnitude"],
                },
                hint=(
                    "检查该科目是否有凭证漏过账、期初余额导入错误、或存在跨期调整未入账；"
                    "样本科目为差额最大的 1 个，完整科目列表见 message"
                ),
                diff_breakdown=diff_breakdown,
                tolerance_formula="min(1.0 + magnitude * 0.00001, 100.0)",
            )
        findings.append(
            ValidationFinding(
                level="L3",
                severity="blocking",
                code="BALANCE_LEDGER_MISMATCH",
                message=(
                    f"余额表期末余额与序时账累计不一致（动态容差），"
                    f"涉及 {len(mismatch_accounts)} 个科目：{', '.join(sample)}"
                    + ("..." if len(mismatch_accounts) > 10 else "")
                ),
                location={
                    "file": "",
                    "sheet": "",
                    "row": -1,
                    "column": "closing_balance",
                    # F49 / Sprint 8.12+8.13: 直达穿透抽屉所需 payload
                    "drill_down": drill_down,
                },
                blocking=True,
                explanation=explanation,
            )
        )

    # --- Check 2: Aux account codes not in main tables ---
    # Check aux_balance codes not in balance
    result = await db.execute(
        text("""
            SELECT DISTINCT ab.account_code
            FROM tb_aux_balance ab
            LEFT JOIN tb_balance b
                ON b.dataset_id = ab.dataset_id
                AND b.account_code = ab.account_code
            WHERE ab.dataset_id = :dataset_id
              AND b.account_code IS NULL
        """),
        {"dataset_id": str(dataset_id)},
    )
    aux_balance_missing = [r.account_code for r in result.fetchall()]

    # Check aux_ledger codes not in ledger
    result = await db.execute(
        text("""
            SELECT DISTINCT al.account_code
            FROM tb_aux_ledger al
            LEFT JOIN tb_ledger l
                ON l.dataset_id = al.dataset_id
                AND l.account_code = al.account_code
            WHERE al.dataset_id = :dataset_id
              AND l.account_code IS NULL
        """),
        {"dataset_id": str(dataset_id)},
    )
    aux_ledger_missing = [r.account_code for r in result.fetchall()]

    all_aux_missing = set(aux_balance_missing + aux_ledger_missing)
    if all_aux_missing:
        sample = sorted(all_aux_missing)[:10]
        # F49 / Sprint 8.13: 为辅助科目不一致也填 drill_down
        # 优先选 aux_ledger 作 target（凭证级数据更有穿透价值），
        # 若该 missing 仅在 aux_balance，则退回 aux_balance
        missing_code = sample[0]
        target_table = (
            "tb_aux_ledger"
            if missing_code in aux_ledger_missing
            else "tb_aux_balance"
        )
        aux_sid_result = await db.execute(
            text(f"""
                SELECT id FROM {target_table}
                WHERE dataset_id = :dataset_id
                  AND account_code = :account_code
                LIMIT 3
            """),
            {
                "dataset_id": str(dataset_id),
                "account_code": missing_code,
            },
        )
        aux_sample_ids = [str(r.id) for r in aux_sid_result.fetchall()]
        aux_cnt_result = await db.execute(
            text(f"""
                SELECT COUNT(*) AS cnt FROM {target_table}
                WHERE dataset_id = :dataset_id
                  AND account_code = :account_code
            """),
            {
                "dataset_id": str(dataset_id),
                "account_code": missing_code,
            },
        )
        aux_cnt_row = aux_cnt_result.fetchone()
        aux_expected_count = (
            int(aux_cnt_row.cnt) if aux_cnt_row is not None else 0
        )
        aux_drill_down = {
            "target": target_table,
            "filter": {
                "dataset_id": str(dataset_id),
                "account_code": missing_code,
            },
            "sample_ids": aux_sample_ids,
            "expected_count": aux_expected_count,
        }
        findings.append(
            ValidationFinding(
                level="L3",
                severity="warning",
                code="AUX_ACCOUNT_MISMATCH",
                message=(
                    f"辅助表中有 {len(all_aux_missing)} 个科目代码"
                    f"不在主表中：{', '.join(sample)}"
                    + ("..." if len(all_aux_missing) > 10 else "")
                ),
                location={
                    "file": "",
                    "sheet": "",
                    "row": -1,
                    "column": "account_code",
                    "drill_down": aux_drill_down,
                },
                blocking=False,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Activation Gate
# ---------------------------------------------------------------------------


def evaluate_activation(
    findings: list[ValidationFinding],
    *,
    force: bool = False,
) -> ActivationGate:
    """Evaluate whether activation is allowed.

    Rules:
    - L1 blocking findings → ALWAYS block (cannot force-skip)
    - L2/L3 blocking findings → block UNLESS force=True
    - Exception: L2_LEDGER_YEAR_OUT_OF_RANGE cannot be force-skipped
    - Warnings never block
    """
    blocking_findings: list[ValidationFinding] = []
    warning_findings: list[ValidationFinding] = []

    for f in findings:
        if f.blocking:
            blocking_findings.append(f)
        else:
            warning_findings.append(f)

    if not blocking_findings:
        return ActivationGate(
            allowed=True,
            blocking_findings=[],
            warning_findings=warning_findings,
        )

    # Determine if activation is allowed despite blocking findings
    if not force:
        # Without force, any blocking finding blocks
        return ActivationGate(
            allowed=False,
            blocking_findings=blocking_findings,
            warning_findings=warning_findings,
        )

    # With force=True, check which findings can be skipped
    non_skippable: list[ValidationFinding] = []
    for f in blocking_findings:
        # L1 blocking findings can NEVER be force-skipped
        if f.level == "L1":
            non_skippable.append(f)
        # Specific codes that cannot be force-skipped
        elif f.code in _NON_FORCEABLE_CODES:
            non_skippable.append(f)
        # L2/L3 blocking findings CAN be force-skipped (not added to non_skippable)

    if non_skippable:
        return ActivationGate(
            allowed=False,
            blocking_findings=non_skippable,
            warning_findings=warning_findings,
        )

    # All blocking findings are force-skippable
    return ActivationGate(
        allowed=True,
        blocking_findings=blocking_findings,
        warning_findings=warning_findings,
    )


__all__ = [
    "ValidationFinding",
    "ActivationGate",
    "ExplanationBase",
    "BalanceMismatchExplanation",
    "UnbalancedExplanation",
    "YearOutOfRangeExplanation",
    "L1TypeErrorExplanation",
    "validate_l1",
    "validate_l2",
    "validate_l3",
    "evaluate_activation",
]
