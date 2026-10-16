"""附注校验公式引擎

支持8种公式类型：
1. BalanceCheck — 余额核对（报表数 vs 附注合计）
2. WideTableHorizontal — 宽表横向勾稽（期初+变动=期末）
3. VerticalReconcile — 纵向勾稽（子项合计=总计行）
4. CrossCheck — 交叉校验（跨表数据一致性）
5. SubItemCheck — 其中项校验（其中项≤总额）
6. AgingTransition — 账龄衔接（上期期末=本期期初）
7. CompletenessCheck — 完整性检查（必填项非空）
8. LLMReview — LLM审核占位（本引擎不调大模型）

双层架构：本地规则引擎优先 + LLMReview 兜底。🔴 2026-10-16 起大模型只在用户手动单击时调用（spec
disclosure-note-template-word-realignment Task 22）：兜底层是同步占位、恒返回空；原会调大模型的
``LLMReview.validate_async`` 全仓零调用方，已删除。附注大模型审核只走 ``NoteValidationEngine(allow_llm=True)``。

Validates: Requirements 9.2, 9.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services._decimal_helpers import (
    AmountConversionError,
    amount_tolerance,
    to_decimal,
)


@dataclass
class Finding:
    """校验发现"""
    rule_type: str
    severity: str  # high / medium / low / info
    message: str
    details: dict = field(default_factory=dict)


def _to_decimal_safe(value: Any) -> Decimal | None:
    """容忍式转换：失败返回 None（保持各 validator 的 except 原语义）。"""
    if value is None:
        return None
    try:
        return to_decimal(value, allow_none=False)
    except (AmountConversionError, ValueError, TypeError):
        return None


def _max_abs(*amounts: Decimal | None) -> Decimal | None:
    """选取参考金额中绝对值最大者，作为 amount_tolerance 输入。"""
    candidate: Decimal | None = None
    for amt in amounts:
        if amt is None:
            continue
        if candidate is None or abs(amt) > abs(candidate):
            candidate = amt
    return candidate


# ---------------------------------------------------------------------------
# 8种校验器基类
# ---------------------------------------------------------------------------

class BaseValidator:
    """校验器基类"""
    rule_type: str = "base"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        raise NotImplementedError


class BalanceCheck(BaseValidator):
    """余额核对：报表数 vs 附注合计"""
    rule_type = "balance_check"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        report_amount = note_data.get("report_amount")
        note_total = note_data.get("note_total")
        if report_amount is None or note_total is None:
            return findings
        r = _to_decimal_safe(report_amount)
        n = _to_decimal_safe(note_total)
        if r is None or n is None:
            return findings
        diff = r - n
        # 动态容差：以参考金额规模为基准，小金额仍为 0.01，大金额按比例放宽
        tolerance = amount_tolerance(_max_abs(r, n))
        if abs(diff) > tolerance:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="high",
                message=f"报表数 {r:,.2f} 与附注合计 {n:,.2f} 不一致，差异 {diff:,.2f}",
                details={
                    "report_amount": float(r),
                    "note_total": float(n),
                    "diff": float(diff),
                    "tolerance": float(tolerance),
                },
            ))
        return findings


class WideTableHorizontal(BaseValidator):
    """宽表横向勾稽：期初 + 变动 = 期末"""
    rule_type = "wide_table_horizontal"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        rows = note_data.get("rows", [])
        for row in rows:
            opening = row.get("opening")
            changes = row.get("changes", [])
            closing = row.get("closing")
            if opening is None or closing is None:
                continue
            o = _to_decimal_safe(opening)
            c = _to_decimal_safe(closing)
            if o is None or c is None:
                continue
            ch = Decimal("0")
            change_failed = False
            for x in changes:
                if x is None:
                    continue
                xd = _to_decimal_safe(x)
                if xd is None:
                    change_failed = True
                    break
                ch += xd
            if change_failed:
                continue
            expected = o + ch
            diff = expected - c
            tolerance = amount_tolerance(_max_abs(o, c, ch, expected))
            if abs(diff) > tolerance:
                findings.append(Finding(
                    rule_type=self.rule_type,
                    severity="medium",
                    message=f"行 '{row.get('label', '?')}': 期初({o:,.2f})+变动({ch:,.2f})={expected:,.2f} ≠ 期末({c:,.2f})",
                    details={
                        "label": row.get("label"),
                        "opening": float(o),
                        "changes": float(ch),
                        "closing": float(c),
                        "tolerance": float(tolerance),
                    },
                ))
        return findings


class VerticalReconcile(BaseValidator):
    """纵向勾稽：子项合计 = 总计行"""
    rule_type = "vertical_reconcile"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        items = note_data.get("items", [])
        total = note_data.get("total")
        if total is None or not items:
            return findings
        t = _to_decimal_safe(total)
        if t is None:
            return findings
        s = Decimal("0")
        item_failed = False
        for x in items:
            if x is None:
                continue
            xd = _to_decimal_safe(x)
            if xd is None:
                item_failed = True
                break
            s += xd
        if item_failed:
            return findings
        diff = s - t
        tolerance = amount_tolerance(_max_abs(s, t))
        if abs(diff) > tolerance:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"子项合计 {s:,.2f} ≠ 总计行 {t:,.2f}，差异 {diff:,.2f}",
                details={
                    "sum_items": float(s),
                    "total": float(t),
                    "diff": float(diff),
                    "tolerance": float(tolerance),
                },
            ))
        return findings


class CrossCheck(BaseValidator):
    """交叉校验：跨表数据一致性"""
    rule_type = "cross_check"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        source_value = note_data.get("source_value")
        target_value = note_data.get("target_value")
        if source_value is None or target_value is None:
            return findings
        s = _to_decimal_safe(source_value)
        t = _to_decimal_safe(target_value)
        if s is None or t is None:
            return findings
        diff = s - t
        tolerance = amount_tolerance(_max_abs(s, t))
        if abs(diff) > tolerance:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"跨表数据不一致: 来源 {s:,.2f} ≠ 目标 {t:,.2f}",
                details={
                    "source": note_data.get("source_table", ""),
                    "target": note_data.get("target_table", ""),
                    "source_value": float(s),
                    "target_value": float(t),
                    "tolerance": float(tolerance),
                },
            ))
        return findings


class SubItemCheck(BaseValidator):
    """其中项校验：其中项 ≤ 总额"""
    rule_type = "sub_item_check"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        total = note_data.get("total")
        sub_items = note_data.get("sub_items", [])
        if total is None or not sub_items:
            return findings
        t = _to_decimal_safe(total)
        if t is None:
            return findings
        s = Decimal("0")
        item_failed = False
        for x in sub_items:
            amt = x.get("amount") if isinstance(x, dict) else None
            if amt is None:
                continue
            d = _to_decimal_safe(amt)
            if d is None:
                item_failed = True
                break
            s += d
        if item_failed:
            return findings
        # 其中项不得 > 总额，但保留容差避免微小舍入误判
        tolerance = amount_tolerance(_max_abs(s, t))
        if s > t + tolerance:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"其中项合计 {s:,.2f} 超过总额 {t:,.2f}",
                details={
                    "sub_total": float(s),
                    "total": float(t),
                    "tolerance": float(tolerance),
                },
            ))
        return findings


class AgingTransition(BaseValidator):
    """账龄衔接：上期期末 = 本期期初"""
    rule_type = "aging_transition"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        prior_closing = note_data.get("prior_closing")
        current_opening = note_data.get("current_opening")
        if prior_closing is None or current_opening is None:
            return findings
        pc = _to_decimal_safe(prior_closing)
        co = _to_decimal_safe(current_opening)
        if pc is None or co is None:
            return findings
        diff = pc - co
        tolerance = amount_tolerance(_max_abs(pc, co))
        if abs(diff) > tolerance:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"账龄衔接不一致: 上期期末 {pc:,.2f} ≠ 本期期初 {co:,.2f}",
                details={
                    "prior_closing": float(pc),
                    "current_opening": float(co),
                    "tolerance": float(tolerance),
                },
            ))
        return findings


class CompletenessCheck(BaseValidator):
    """完整性检查：必填项非空"""
    rule_type = "completeness_check"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        findings: list[Finding] = []
        required_fields = (params or {}).get("required_fields", [])
        for field_name in required_fields:
            value = note_data.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                findings.append(Finding(
                    rule_type=self.rule_type,
                    severity="low",
                    message=f"必填项 '{field_name}' 为空",
                    details={"field": field_name},
                ))
        return findings


class LLMReview(BaseValidator):
    """LLM审核占位 — 自动路径不调大模型（手动审核见 ``NoteValidationEngine(allow_llm=True)``）

    检查项：
    1. 会计政策描述是否与准则一致
    2. 数值描述是否与表格数据匹配
    3. 披露是否完整（关键信息是否遗漏）
    """
    rule_type = "llm_review"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        """恒返回空：公式引擎是自动路径，不调大模型。"""
        return []


# ---------------------------------------------------------------------------
# 校验器注册表
# ---------------------------------------------------------------------------

VALIDATORS: dict[str, BaseValidator] = {
    "balance_check": BalanceCheck(),
    "wide_table_horizontal": WideTableHorizontal(),
    "vertical_reconcile": VerticalReconcile(),
    "cross_check": CrossCheck(),
    "sub_item_check": SubItemCheck(),
    "aging_transition": AgingTransition(),
    "completeness_check": CompletenessCheck(),
    "llm_review": LLMReview(),
}

LOCAL_VALIDATORS = [k for k in VALIDATORS if k != "llm_review"]


# ---------------------------------------------------------------------------
# 双层架构入口
# ---------------------------------------------------------------------------

def validate_note(note_data: dict, rule_types: list[str] | None = None) -> list[Finding]:
    """校验附注数据

    双层架构：
    1. 先运行本地规则引擎（7种非LLM校验器）
    2. 如果本地规则未发现问题，再走 LLMReview 兜底（同步占位、不调大模型）

    Args:
        note_data: 附注数据字典
        rule_types: 指定要运行的规则类型列表，None=全部

    Returns:
        校验发现列表
    """
    all_findings: list[Finding] = []

    # 第一层：本地规则
    types_to_run = rule_types or LOCAL_VALIDATORS
    for rule_type in types_to_run:
        if rule_type == "llm_review":
            continue
        validator = VALIDATORS.get(rule_type)
        if validator:
            params = note_data.get("params", {}).get(rule_type)
            all_findings.extend(validator.validate(note_data, params))

    # 第二层：LLMReview 兜底（占位；仅在本地规则未发现问题时走到，不调大模型）
    if not all_findings:
        llm = VALIDATORS["llm_review"]
        all_findings.extend(llm.validate(note_data))

    return all_findings
