"""调整分录明细行校验与编号规则的唯一实现。

大厅新建 / 修改（``AdjustmentService.create_entry`` / ``update_entry``）与 Excel 导入预检
（``adjustment_import_service``）共用这里的规则，前端 ``adjustmentLineRules.ts`` 按同一口径
做即时提示（spec adjustment-hall-entry-review-closure 需求 1.2 / 1.3）。

规则：
- 每行必须有科目；
- 金额不能为负（冲减录入到相反方向）；
- 同一行借贷不能同时有数；借贷都为 0 的行不允许；
- 整组借贷合计相等且大于 0；
- 金额一律按分舍入后再比较（Numeric(20, 2) 落库同口径）。
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable

CENT = Decimal("0.01")

#: 自定义编号的最大长度（adjustment_no 列为 String，界面与导入按此截断校验）
MAX_ADJUSTMENT_NO_LENGTH = 30


def to_cents(value: Any) -> Decimal:
    """把金额转成按分舍入的 Decimal；None / 空串视为 0，无法识别抛 ValueError。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal("0.00")
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"金额无法识别：{value}") from exc
    if not d.is_finite():
        raise ValueError(f"金额无法识别：{value}")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def entry_rule_errors(lines: Iterable[Any], *, row_labels: list[str] | None = None) -> list[str]:
    """返回一笔分录违反的全部规则（中文、带行号）；为空表示通过。

    ``lines`` 的元素只需有 ``standard_account_code`` / ``debit_amount`` / ``credit_amount``
    三个属性（AdjustmentLineItem、导入解析行均可）；``row_labels`` 给出每行的展示名
    （导入用「第 5 行」这类文件行号），缺省按「第 N 行」从 1 编号。
    """
    items = list(lines)
    if not items:
        return ["至少需要一行明细"]
    errors: list[str] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for idx, li in enumerate(items):
        label = row_labels[idx] if row_labels and idx < len(row_labels) else f"第 {idx + 1} 行"
        code = str(getattr(li, "standard_account_code", None) or "").strip()
        try:
            debit = to_cents(getattr(li, "debit_amount", None))
            credit = to_cents(getattr(li, "credit_amount", None))
        except ValueError as exc:
            errors.append(f"{label}{exc}")
            continue
        if not code:
            errors.append(f"{label}未选择科目")
        if debit < 0 or credit < 0:
            errors.append(f"{label}金额不能为负数（冲减请录入到相反方向）")
        if debit != 0 and credit != 0:
            errors.append(f"{label}借方和贷方不能同时填写")
        if debit == 0 and credit == 0:
            errors.append(f"{label}借贷金额均为 0")
        total_debit += debit
        total_credit += credit
    if total_debit != total_credit:
        errors.append(
            f"借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}，"
            f"差额 {total_debit - total_credit}"
        )
    elif total_debit == 0:
        errors.append("借贷合计为 0，没有需要调整的金额")
    return errors


def normalize_adjustment_no(value: str | None) -> str | None:
    """规整用户填写的编号：去首尾空白，空串视为未填；超长抛 ValueError。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_ADJUSTMENT_NO_LENGTH:
        raise ValueError(f"编号「{text}」超过 {MAX_ADJUSTMENT_NO_LENGTH} 个字符")
    return text


def next_free_number(prefix: str, start: int, used: set[str]) -> str:
    """从 ``start`` 起找第一个未被占用的「前缀-三位序号」。"""
    n = max(int(start), 1)
    while f"{prefix}-{n:03d}" in used:
        n += 1
    return f"{prefix}-{n:03d}"
