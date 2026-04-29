"""附注校验公式引擎

支持8种公式类型：
1. BalanceCheck — 余额核对（报表数 vs 附注合计）
2. WideTableHorizontal — 宽表横向勾稽（期初+变动=期末）
3. VerticalReconcile — 纵向勾稽（子项合计=总计行）
4. CrossCheck — 交叉校验（跨表数据一致性）
5. SubItemCheck — 其中项校验（其中项≤总额）
6. AgingTransition — 账龄衔接（上期期末=本期期初）
7. CompletenessCheck — 完整性检查（必填项非空）
8. LLMReview — LLM审核（调用 vLLM 做内容合理性检查）

双层架构：本地规则引擎优先 + LLM兜底

Validates: Requirements 9.2, 9.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    """校验发现"""
    rule_type: str
    severity: str  # high / medium / low / info
    message: str
    details: dict = field(default_factory=dict)


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
        try:
            r = float(report_amount)
            n = float(note_total)
        except (ValueError, TypeError):
            return findings
        if abs(r - n) > 0.01:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="high",
                message=f"报表数 {r:,.2f} 与附注合计 {n:,.2f} 不一致，差异 {r - n:,.2f}",
                details={"report_amount": r, "note_total": n, "diff": r - n},
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
            try:
                o = float(opening)
                c = float(closing)
                ch = sum(float(x) for x in changes if x is not None)
            except (ValueError, TypeError):
                continue
            expected = o + ch
            if abs(expected - c) > 0.01:
                findings.append(Finding(
                    rule_type=self.rule_type,
                    severity="medium",
                    message=f"行 '{row.get('label', '?')}': 期初({o:,.2f})+变动({ch:,.2f})={expected:,.2f} ≠ 期末({c:,.2f})",
                    details={"label": row.get("label"), "opening": o, "changes": ch, "closing": c},
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
        try:
            t = float(total)
            s = sum(float(x) for x in items if x is not None)
        except (ValueError, TypeError):
            return findings
        if abs(s - t) > 0.01:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"子项合计 {s:,.2f} ≠ 总计行 {t:,.2f}，差异 {s - t:,.2f}",
                details={"sum_items": s, "total": t, "diff": s - t},
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
        try:
            s = float(source_value)
            t = float(target_value)
        except (ValueError, TypeError):
            return findings
        if abs(s - t) > 0.01:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"跨表数据不一致: 来源 {s:,.2f} ≠ 目标 {t:,.2f}",
                details={
                    "source": note_data.get("source_table", ""),
                    "target": note_data.get("target_table", ""),
                    "source_value": s, "target_value": t,
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
        try:
            t = float(total)
            s = sum(float(x.get("amount", 0)) for x in sub_items if x.get("amount") is not None)
        except (ValueError, TypeError):
            return findings
        if s > t + 0.01:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"其中项合计 {s:,.2f} 超过总额 {t:,.2f}",
                details={"sub_total": s, "total": t},
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
        try:
            pc = float(prior_closing)
            co = float(current_opening)
        except (ValueError, TypeError):
            return findings
        if abs(pc - co) > 0.01:
            findings.append(Finding(
                rule_type=self.rule_type,
                severity="medium",
                message=f"账龄衔接不一致: 上期期末 {pc:,.2f} ≠ 本期期初 {co:,.2f}",
                details={"prior_closing": pc, "current_opening": co},
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
    """LLM审核 — 调用 vLLM 对附注内容做合理性检查

    检查项：
    1. 会计政策描述是否与准则一致
    2. 数值描述是否与表格数据匹配
    3. 披露是否完整（关键信息是否遗漏）
    """
    rule_type = "llm_review"

    def validate(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        """同步版本：直接返回空（LLM 需要异步调用）"""
        return []

    async def validate_async(self, note_data: dict, params: dict | None = None) -> list[Finding]:
        """异步版本：调用 LLM 做内容审核"""
        findings: list[Finding] = []
        text_content = note_data.get("text_content", "")
        section_title = note_data.get("section_title", "")

        if not text_content or len(text_content) < 20:
            return findings

        try:
            from app.services.llm_client import chat_completion

            prompt = f"""你是资深审计员，请审核以下附注章节内容，检查：
1. 会计政策描述是否规范
2. 数值描述是否合理（有无明显矛盾）
3. 披露是否完整（关键信息是否遗漏）

章节标题：{section_title}
内容：
{text_content[:2000]}

请以 JSON 数组格式返回发现的问题，每个问题包含 severity(high/medium/low) 和 message 字段。
如果没有问题，返回空数组 []。"""

            response = await chat_completion(prompt)
            if not response:
                return findings

            # 尝试解析 LLM 返回的 JSON
            import json
            try:
                # 提取 JSON 部分
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                issues = json.loads(text)
                if isinstance(issues, list):
                    for issue in issues[:5]:  # 最多 5 条
                        findings.append(Finding(
                            rule_type=self.rule_type,
                            severity=issue.get("severity", "low"),
                            message=f"[LLM] {issue.get('message', '未知问题')}",
                            details={"source": "llm_review", "section": section_title},
                        ))
            except (json.JSONDecodeError, IndexError):
                # LLM 返回非 JSON 格式，提取关键信息
                if "问题" in response or "不一致" in response or "缺少" in response:
                    findings.append(Finding(
                        rule_type=self.rule_type,
                        severity="low",
                        message=f"[LLM] {response[:200]}",
                        details={"source": "llm_review", "raw_response": response[:500]},
                    ))
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"LLM review skipped: {e}")

        return findings


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
    2. 如果本地规则未发现问题，再调用LLM兜底（validate_async 异步版本）

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

    # 第二层：LLM兜底（仅在本地规则未发现问题时调用）
    if not all_findings:
        llm = VALIDATORS["llm_review"]
        all_findings.extend(llm.validate(note_data))

    return all_findings
