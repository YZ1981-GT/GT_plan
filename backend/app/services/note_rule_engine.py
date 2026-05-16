"""附注通用规则引擎 — 5 条规则决定"生成什么"

Requirements: 35.1, 35.2, 35.3, 35.4, 35.5

规则 A（余额驱动）：报表行次金额 ≠ 0 → 生成对应附注章节
规则 B（变动驱动）：本期与上期差异 > 重要性水平 × 5% → 生成变动分析
规则 C（底稿驱动）：对应底稿已编制且有审定数 → 从底稿取数
规则 D（政策驱动）：会计政策章节始终生成
规则 E（关联方驱动）：关联方交易/余额 > 0 → 生成关联方披露
未触发任何规则的章节标记为"本期无此项业务"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class RuleType(str, Enum):
    """规则类型"""
    BALANCE = "balance"           # 规则 A：余额驱动
    CHANGE = "change"             # 规则 B：变动驱动
    WORKPAPER = "workpaper"       # 规则 C：底稿驱动
    POLICY = "policy"             # 规则 D：政策驱动
    RELATED_PARTY = "related_party"  # 规则 E：关联方驱动


class SectionDecision(str, Enum):
    """章节生成决策"""
    GENERATE = "generate"         # 生成（有数据）
    SKIP = "skip"                 # 跳过（本期无此项业务）
    ALWAYS = "always"             # 始终生成（政策类）
    VARIATION = "variation"       # 生成变动分析


@dataclass
class RuleResult:
    """单条规则判断结果"""
    rule_type: RuleType
    triggered: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionJudgment:
    """章节生成判断结果"""
    section_code: str
    decision: SectionDecision
    triggered_rules: list[RuleResult] = field(default_factory=list)
    skip_reason: str = ""  # 当 decision=SKIP 时的原因


@dataclass
class RuleEngineContext:
    """规则引擎上下文"""
    # 报表数据: {row_code: {current_period_amount, prior_period_amount}}
    report_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 底稿状态: {wp_code: {has_data: bool, audited: bool}}
    workpaper_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 重要性水平
    materiality: Decimal = Decimal("0")
    # 关联方数据: {party_name: {transaction_amount, balance_amount}}
    related_party_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 政策章节列表
    policy_sections: list[str] = field(default_factory=list)
    # 必披露章节列表
    mandatory_sections: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 默认政策章节（始终生成）
# ---------------------------------------------------------------------------

DEFAULT_POLICY_SECTIONS = [
    "note_accounting_policies",
    "note_significant_judgments",
    "note_tax_policy",
    "note_revenue_recognition",
    "note_consolidation_scope",
]

# 关联方相关章节
RELATED_PARTY_SECTIONS = [
    "note_related_parties",
    "note_related_party_transactions",
    "note_related_party_balances",
]


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------

class NoteRuleEngine:
    """附注通用规则引擎

    通过 5 条通用规则自动判断附注章节是否需要生成。
    """

    def __init__(self, context: RuleEngineContext | None = None):
        self.context = context or RuleEngineContext()

    # ------------------------------------------------------------------
    # 规则 A：余额驱动
    # ------------------------------------------------------------------

    def check_balance_rule(
        self,
        section_code: str,
        report_row_code: str | None = None,
    ) -> RuleResult:
        """规则 A：报表行次金额 ≠ 0 → 生成对应附注章节"""
        if not report_row_code:
            return RuleResult(rule_type=RuleType.BALANCE, triggered=False, reason="无对应报表行次")

        row_data = self.context.report_data.get(report_row_code, {})
        current_amount = row_data.get("current_period_amount", 0) or 0
        prior_amount = row_data.get("prior_period_amount", 0) or 0

        # 本期或上期有余额即触发
        triggered = (Decimal(str(current_amount)) != 0) or (Decimal(str(prior_amount)) != 0)

        return RuleResult(
            rule_type=RuleType.BALANCE,
            triggered=triggered,
            reason=f"报表行次 {report_row_code} 金额={'非零' if triggered else '为零'}",
            details={"current": current_amount, "prior": prior_amount},
        )

    # ------------------------------------------------------------------
    # 规则 B：变动驱动
    # ------------------------------------------------------------------

    def check_change_rule(
        self,
        section_code: str,
        report_row_code: str | None = None,
    ) -> RuleResult:
        """规则 B：本期与上期差异 > 重要性水平 × 5% → 生成变动分析"""
        if not report_row_code:
            return RuleResult(rule_type=RuleType.CHANGE, triggered=False, reason="无对应报表行次")

        row_data = self.context.report_data.get(report_row_code, {})
        current = Decimal(str(row_data.get("current_period_amount", 0) or 0))
        prior = Decimal(str(row_data.get("prior_period_amount", 0) or 0))
        diff = abs(current - prior)
        threshold = self.context.materiality * Decimal("0.05")

        triggered = diff > threshold and threshold > 0

        return RuleResult(
            rule_type=RuleType.CHANGE,
            triggered=triggered,
            reason=f"变动 {diff} {'>' if triggered else '≤'} 重要性×5% ({threshold})",
            details={"diff": float(diff), "threshold": float(threshold)},
        )

    # ------------------------------------------------------------------
    # 规则 C：底稿驱动
    # ------------------------------------------------------------------

    def check_workpaper_rule(
        self,
        section_code: str,
        wp_code: str | None = None,
    ) -> RuleResult:
        """规则 C：对应底稿已编制且有审定数 → 从底稿取数"""
        if not wp_code:
            return RuleResult(rule_type=RuleType.WORKPAPER, triggered=False, reason="无对应底稿编码")

        wp_status = self.context.workpaper_status.get(wp_code, {})
        has_data = wp_status.get("has_data", False)
        audited = wp_status.get("audited", False)

        triggered = has_data and audited

        return RuleResult(
            rule_type=RuleType.WORKPAPER,
            triggered=triggered,
            reason=f"底稿 {wp_code} {'已编制且有审定数' if triggered else '未就绪'}",
            details={"has_data": has_data, "audited": audited},
        )

    # ------------------------------------------------------------------
    # 规则 D：政策驱动
    # ------------------------------------------------------------------

    def check_policy_rule(self, section_code: str) -> RuleResult:
        """规则 D：会计政策章节始终生成"""
        policy_sections = self.context.policy_sections or DEFAULT_POLICY_SECTIONS
        triggered = section_code in policy_sections

        return RuleResult(
            rule_type=RuleType.POLICY,
            triggered=triggered,
            reason=f"{'会计政策章节，始终生成' if triggered else '非政策章节'}",
        )

    # ------------------------------------------------------------------
    # 规则 E：关联方驱动
    # ------------------------------------------------------------------

    def check_related_party_rule(self, section_code: str) -> RuleResult:
        """规则 E：关联方交易/余额 > 0 → 生成关联方披露"""
        if section_code not in RELATED_PARTY_SECTIONS:
            return RuleResult(rule_type=RuleType.RELATED_PARTY, triggered=False, reason="非关联方章节")

        # 检查是否有关联方数据
        has_rp_data = False
        for party_data in self.context.related_party_data.values():
            tx_amount = Decimal(str(party_data.get("transaction_amount", 0) or 0))
            bal_amount = Decimal(str(party_data.get("balance_amount", 0) or 0))
            if tx_amount > 0 or bal_amount > 0:
                has_rp_data = True
                break

        return RuleResult(
            rule_type=RuleType.RELATED_PARTY,
            triggered=has_rp_data,
            reason=f"关联方交易/余额{'> 0' if has_rp_data else '= 0'}",
        )

    # ------------------------------------------------------------------
    # 综合判断
    # ------------------------------------------------------------------

    def judge_section(
        self,
        section_code: str,
        report_row_code: str | None = None,
        wp_code: str | None = None,
    ) -> SectionJudgment:
        """综合 5 条规则判断章节是否需要生成"""
        rules: list[RuleResult] = []

        # 规则 D 优先：政策章节始终生成
        policy_result = self.check_policy_rule(section_code)
        rules.append(policy_result)
        if policy_result.triggered:
            return SectionJudgment(
                section_code=section_code,
                decision=SectionDecision.ALWAYS,
                triggered_rules=rules,
            )

        # 必披露章节始终生成
        if section_code in self.context.mandatory_sections:
            return SectionJudgment(
                section_code=section_code,
                decision=SectionDecision.ALWAYS,
                triggered_rules=rules,
            )

        # 规则 E：关联方驱动
        rp_result = self.check_related_party_rule(section_code)
        rules.append(rp_result)
        if rp_result.triggered:
            return SectionJudgment(
                section_code=section_code,
                decision=SectionDecision.GENERATE,
                triggered_rules=rules,
            )

        # 规则 A：余额驱动
        balance_result = self.check_balance_rule(section_code, report_row_code)
        rules.append(balance_result)

        # 规则 C：底稿驱动
        wp_result = self.check_workpaper_rule(section_code, wp_code)
        rules.append(wp_result)

        # 规则 B：变动驱动
        change_result = self.check_change_rule(section_code, report_row_code)
        rules.append(change_result)

        # 判断决策
        if balance_result.triggered or wp_result.triggered:
            decision = SectionDecision.GENERATE
        elif change_result.triggered:
            decision = SectionDecision.VARIATION
        else:
            decision = SectionDecision.SKIP

        skip_reason = ""
        if decision == SectionDecision.SKIP:
            skip_reason = "本期无此项业务"

        return SectionJudgment(
            section_code=section_code,
            decision=decision,
            triggered_rules=rules,
            skip_reason=skip_reason,
        )

    # ------------------------------------------------------------------
    # 批量判断
    # ------------------------------------------------------------------

    def judge_all_sections(
        self,
        sections: list[dict[str, Any]],
    ) -> list[SectionJudgment]:
        """批量判断所有章节

        Args:
            sections: [{section_code, report_row_code, wp_code}]
        """
        results = []
        for sec in sections:
            judgment = self.judge_section(
                section_code=sec.get("section_code", ""),
                report_row_code=sec.get("report_row_code"),
                wp_code=sec.get("wp_code"),
            )
            results.append(judgment)
        return results

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    @staticmethod
    def summarize(judgments: list[SectionJudgment]) -> dict[str, int]:
        """统计判断结果"""
        summary = {"generate": 0, "skip": 0, "always": 0, "variation": 0}
        for j in judgments:
            summary[j.decision.value] = summary.get(j.decision.value, 0) + 1
        return summary
