"""关联方披露专项适配器

将关联方模块数据适配为附注披露所需结构：
- 关联方主体清单
- 关系类型
- 交易类型
- 本期发生额
- 期末余额
- 是否已函证/是否有附件
- 与报表项目的 tie-out

不直接查 DB，接收结构化输入数据，输出标准化披露结构和质量问题。

Validates: Requirements 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from app.services.note_quality_checklist_service import QualityChecklistItem


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class RelatedParty(BaseModel):
    """关联方主体"""

    party_id: str = Field(..., description="关联方唯一标识")
    party_name: str = Field(..., description="关联方名称")
    relationship_type: str = Field(default="", description="关系类型：母公司/子公司/联营/合营/关键管理人等")
    relationship_description: str = Field(default="", description="关系说明")


class RelatedPartyTransaction(BaseModel):
    """关联方交易"""

    party_id: str = Field(..., description="关联方 ID")
    transaction_type: str = Field(..., description="交易类型：销售/采购/资金拆借/担保等")
    current_amount: Decimal = Field(default=Decimal("0"), description="本期发生额")
    prior_amount: Decimal = Field(default=Decimal("0"), description="上期发生额")


class RelatedPartyBalance(BaseModel):
    """关联方余额"""

    party_id: str = Field(..., description="关联方 ID")
    balance_type: str = Field(default="receivable", description="余额类型：receivable/payable")
    closing_balance: Decimal = Field(default=Decimal("0"), description="期末余额")
    opening_balance: Decimal = Field(default=Decimal("0"), description="期初余额")


class RelatedPartyEvidence(BaseModel):
    """关联方证据标识"""

    party_id: str = Field(..., description="关联方 ID")
    has_confirmation: bool = Field(default=False, description="是否已函证")
    has_attachment: bool = Field(default=False, description="是否有附件")
    confirmation_status: str = Field(default="not_sent", description="函证状态：not_sent/sent/received/confirmed")


class TieoutResult(BaseModel):
    """tie-out 结果"""

    rule_description: str = Field(..., description="规则说明")
    note_total: Decimal = Field(default=Decimal("0"), description="附注合计")
    report_amount: Decimal = Field(default=Decimal("0"), description="报表金额")
    difference: Decimal = Field(default=Decimal("0"), description="差异")
    is_balanced: bool = Field(default=True, description="是否平衡")


class RelatedPartyDisclosureResult(BaseModel):
    """关联方披露适配结果"""

    parties: list[RelatedParty] = Field(default_factory=list)
    transactions: list[RelatedPartyTransaction] = Field(default_factory=list)
    balances: list[RelatedPartyBalance] = Field(default_factory=list)
    evidences: list[RelatedPartyEvidence] = Field(default_factory=list)
    tieout_results: list[TieoutResult] = Field(default_factory=list)
    quality_items: list[QualityChecklistItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class RelatedPartyDisclosureAdapter:
    """关联方披露专项适配器

    接收关联方原始数据和报表数据，输出标准化披露结构和质量问题。
    """

    def __init__(self, tolerance: Decimal = Decimal("0.01")) -> None:
        self._tolerance = tolerance

    def adapt(
        self,
        parties: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
        balances: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        report_data: dict[str, Any] | None = None,
    ) -> RelatedPartyDisclosureResult:
        """执行关联方披露适配

        Args:
            parties: 关联方主体列表
            transactions: 关联方交易列表
            balances: 关联方余额列表
            evidences: 证据标识列表
            report_data: 报表数据（用于 tie-out）

        Returns:
            标准化披露结果
        """
        adapted_parties = self._adapt_parties(parties)
        adapted_transactions = self._adapt_transactions(transactions)
        adapted_balances = self._adapt_balances(balances)
        adapted_evidences = self._adapt_evidences(evidences)

        tieout_results = self._compute_tieout(adapted_balances, report_data or {})
        quality_items = self._generate_quality_items(
            adapted_parties, adapted_transactions, adapted_balances,
            adapted_evidences, tieout_results
        )

        return RelatedPartyDisclosureResult(
            parties=adapted_parties,
            transactions=adapted_transactions,
            balances=adapted_balances,
            evidences=adapted_evidences,
            tieout_results=tieout_results,
            quality_items=quality_items,
        )

    # ------------------------------------------------------------------
    # 适配方法
    # ------------------------------------------------------------------

    def _adapt_parties(self, raw: list[dict[str, Any]]) -> list[RelatedParty]:
        """适配关联方主体清单"""
        result: list[RelatedParty] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            result.append(RelatedParty(
                party_id=str(item.get("party_id", "")),
                party_name=str(item.get("party_name", "")),
                relationship_type=str(item.get("relationship_type", "")),
                relationship_description=str(item.get("relationship_description", "")),
            ))
        return result

    def _adapt_transactions(self, raw: list[dict[str, Any]]) -> list[RelatedPartyTransaction]:
        """适配关联方交易"""
        result: list[RelatedPartyTransaction] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            result.append(RelatedPartyTransaction(
                party_id=str(item.get("party_id", "")),
                transaction_type=str(item.get("transaction_type", "")),
                current_amount=self._to_decimal(item.get("current_amount", 0)),
                prior_amount=self._to_decimal(item.get("prior_amount", 0)),
            ))
        return result

    def _adapt_balances(self, raw: list[dict[str, Any]]) -> list[RelatedPartyBalance]:
        """适配关联方余额"""
        result: list[RelatedPartyBalance] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            result.append(RelatedPartyBalance(
                party_id=str(item.get("party_id", "")),
                balance_type=str(item.get("balance_type", "receivable")),
                closing_balance=self._to_decimal(item.get("closing_balance", 0)),
                opening_balance=self._to_decimal(item.get("opening_balance", 0)),
            ))
        return result

    def _adapt_evidences(self, raw: list[dict[str, Any]]) -> list[RelatedPartyEvidence]:
        """适配证据标识"""
        result: list[RelatedPartyEvidence] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            result.append(RelatedPartyEvidence(
                party_id=str(item.get("party_id", "")),
                has_confirmation=bool(item.get("has_confirmation", False)),
                has_attachment=bool(item.get("has_attachment", False)),
                confirmation_status=str(item.get("confirmation_status", "not_sent")),
            ))
        return result

    # ------------------------------------------------------------------
    # Tie-out
    # ------------------------------------------------------------------

    def _compute_tieout(
        self,
        balances: list[RelatedPartyBalance],
        report_data: dict[str, Any],
    ) -> list[TieoutResult]:
        """关联方余额与报表项目 tie-out"""
        results: list[TieoutResult] = []

        # 应收类 tie-out
        receivable_total = sum(
            (b.closing_balance for b in balances if b.balance_type == "receivable"),
            Decimal("0"),
        )
        report_receivable = self._get_report_amount(
            report_data, "other_receivables_related", "closing_balance"
        )
        if report_receivable is not None:
            diff = abs(receivable_total - report_receivable)
            results.append(TieoutResult(
                rule_description="关联方应收余额合计 vs 报表关联方往来应收",
                note_total=receivable_total,
                report_amount=report_receivable,
                difference=diff,
                is_balanced=diff <= self._tolerance,
            ))

        # 应付类 tie-out
        payable_total = sum(
            (b.closing_balance for b in balances if b.balance_type == "payable"),
            Decimal("0"),
        )
        report_payable = self._get_report_amount(
            report_data, "other_payables_related", "closing_balance"
        )
        if report_payable is not None:
            diff = abs(payable_total - report_payable)
            results.append(TieoutResult(
                rule_description="关联方应付余额合计 vs 报表关联方往来应付",
                note_total=payable_total,
                report_amount=report_payable,
                difference=diff,
                is_balanced=diff <= self._tolerance,
            ))

        return results

    # ------------------------------------------------------------------
    # 质量清单
    # ------------------------------------------------------------------

    def _generate_quality_items(
        self,
        parties: list[RelatedParty],
        transactions: list[RelatedPartyTransaction],
        balances: list[RelatedPartyBalance],
        evidences: list[RelatedPartyEvidence],
        tieout_results: list[TieoutResult],
    ) -> list[QualityChecklistItem]:
        """生成质量清单条目"""
        items: list[QualityChecklistItem] = []

        # Requirement 9.3: 差异进入质量清单
        for tr in tieout_results:
            if not tr.is_balanced:
                items.append(QualityChecklistItem(
                    level="warning",
                    category="tieout",
                    section_id="related_party",
                    message=f"{tr.rule_description}：差异 {tr.difference:.2f}",
                    route="/projects/{pid}/disclosure-notes?section=related_party",
                    evidence={
                        "note_total": str(tr.note_total),
                        "report_amount": str(tr.report_amount),
                        "difference": str(tr.difference),
                    },
                ))

        # Requirement 9.4: 缺少关系说明
        for party in parties:
            if not party.relationship_type:
                items.append(QualityChecklistItem(
                    level="warning",
                    category="completeness",
                    section_id="related_party",
                    message=f"关联方「{party.party_name}」缺少关系类型",
                    route="/projects/{pid}/disclosure-notes?section=related_party",
                ))

        # Requirement 9.4: 有余额但无交易说明
        party_ids_with_transactions = {t.party_id for t in transactions}
        for balance in balances:
            if balance.closing_balance != Decimal("0") and balance.party_id not in party_ids_with_transactions:
                items.append(QualityChecklistItem(
                    level="warning",
                    category="completeness",
                    section_id="related_party",
                    message=f"关联方 {balance.party_id} 有余额但无交易记录",
                    route="/projects/{pid}/disclosure-notes?section=related_party",
                ))

        # 证据缺失提示
        evidence_map = {e.party_id: e for e in evidences}
        for balance in balances:
            if balance.closing_balance != Decimal("0"):
                ev = evidence_map.get(balance.party_id)
                if ev is None or (not ev.has_confirmation and not ev.has_attachment):
                    items.append(QualityChecklistItem(
                        level="info",
                        category="completeness",
                        section_id="related_party",
                        message=f"关联方 {balance.party_id} 有余额但缺少函证或附件证据",
                        route="/projects/{pid}/disclosure-notes?section=related_party",
                    ))

        return items

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_report_amount(
        self,
        report_data: dict[str, Any],
        item: str,
        amount_role: str,
    ) -> Decimal | None:
        """从报表数据取值"""
        item_data = report_data.get(item)
        if not item_data or not isinstance(item_data, dict):
            return None
        val = item_data.get(amount_role)
        if val is None:
            return None
        return self._to_decimal(val)

    @staticmethod
    def _to_decimal(val: Any) -> Decimal:
        """安全转 Decimal"""
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError):
            return Decimal("0")
