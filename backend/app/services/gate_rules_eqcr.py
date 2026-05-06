"""EQCR 门禁规则

Refinement Round 5 任务 12 — 需求 5, 6

GateType.eqcr_approval 基础规则：
- 已有 opinion 覆盖 5 个 domain（materiality / estimate / related_party /
  going_concern / opinion_type）
- 无 unresolved disagreement（即所有 verdict='disagree' 的 opinion 都有
  对应的 EqcrDisagreementResolution 且 resolved_at 不为空）
"""

import logging
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eqcr_models import EqcrDisagreementResolution, EqcrOpinion
from app.models.phase14_enums import GateType
from app.services.gate_engine import GateRule, GateRuleHit, rule_registry

logger = logging.getLogger(__name__)

# EQCR 基础 5 个判断域（与 eqcr_service.py EQCR_CORE_DOMAINS 一致）
_REQUIRED_DOMAINS: frozenset[str] = frozenset([
    "materiality",
    "estimate",
    "related_party",
    "going_concern",
    "opinion_type",
])


class EqcrDomainCoverageRule(GateRule):
    """EQCR 门禁规则：5 个判断域必须全部有 opinion 记录。"""

    rule_code = "EQCR-01"
    error_code = "EQCR_DOMAIN_INCOMPLETE"
    severity = "blocking"

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            # 查询该项目所有 active 的 EQCR opinion 的 domain 集合
            q = (
                select(EqcrOpinion.domain)
                .where(
                    EqcrOpinion.project_id == project_id,
                    EqcrOpinion.is_deleted == False,  # noqa: E712
                    EqcrOpinion.domain.in_(list(_REQUIRED_DOMAINS)),
                )
                .distinct()
            )
            result = await db.execute(q)
            covered_domains = set(result.scalars().all())

            missing = _REQUIRED_DOMAINS - covered_domains
            if missing:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message=f"EQCR 尚未对以下判断域录入意见：{', '.join(sorted(missing))}",
                    location={"missing_domains": sorted(missing)},
                    suggested_action="请在 EQCR 工作台对所有 5 个判断域录入复核意见后再审批",
                )
            return None
        except Exception as e:
            logger.error(f"[EQCR-GATE] domain coverage check error: {e}")
            return None


class EqcrNoUnresolvedDisagreementRule(GateRule):
    """EQCR 门禁规则：不能有未解决的 disagreement。"""

    rule_code = "EQCR-02"
    error_code = "EQCR_UNRESOLVED_DISAGREEMENT"
    severity = "blocking"

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            # 查找所有 verdict='disagree' 的 opinion
            disagree_q = (
                select(EqcrOpinion.id)
                .where(
                    EqcrOpinion.project_id == project_id,
                    EqcrOpinion.verdict == "disagree",
                    EqcrOpinion.is_deleted == False,  # noqa: E712
                )
            )
            disagree_ids = list((await db.execute(disagree_q)).scalars().all())

            if not disagree_ids:
                return None

            # 查找已解决的 disagreement resolution
            resolved_q = (
                select(EqcrDisagreementResolution.eqcr_opinion_id)
                .where(
                    EqcrDisagreementResolution.eqcr_opinion_id.in_(disagree_ids),
                    EqcrDisagreementResolution.resolved_at.isnot(None),
                )
            )
            resolved_ids = set((await db.execute(resolved_q)).scalars().all())

            unresolved_count = sum(
                1 for op_id in disagree_ids if op_id not in resolved_ids
            )
            if unresolved_count > 0:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message=f"存在 {unresolved_count} 条未解决的 EQCR 异议，需先完成合议",
                    location={"unresolved_count": unresolved_count},
                    suggested_action="请完成所有 EQCR 异议的合议流程后再审批",
                )
            return None
        except Exception as e:
            logger.error(f"[EQCR-GATE] unresolved disagreement check error: {e}")
            return None


def register_eqcr_gate_rules():
    """注册 EQCR 门禁规则到 rule_registry。"""
    rule_registry.register(GateType.eqcr_approval, EqcrDomainCoverageRule())
    rule_registry.register(GateType.eqcr_approval, EqcrNoUnresolvedDisagreementRule())
    logger.info("[GATE] EQCR gate rules EQCR-01/02 registered")
