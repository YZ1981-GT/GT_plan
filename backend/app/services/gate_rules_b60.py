# -*- coding: utf-8 -*-
"""B60 适用性矩阵缺附件门禁规则"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_enums import GateSeverity, GateType
from app.services.gate_engine import GateRule, GateRuleHit, rule_registry

logger = logging.getLogger(__name__)


class B60AttachmentMatrixRule(GateRule):
    """矩阵勾选为是但缺少对应底稿 → warning（不阻断签发，提示补齐）"""

    rule_code = "B60-ATTACH-MATRIX"
    error_code = "B60_ATTACHMENT_MISSING"
    severity = GateSeverity.warning

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.services.b60_plan_service import evaluate_qc

            qc = await evaluate_qc(project_id, db)
            missing = [f for f in qc.findings if f.code in ("B60-ATTACH-MISSING", "B60-CORE-MISSING")]
            if not missing:
                return None
            codes = sorted({f.location.get("wp_code") for f in missing if f.location.get("wp_code")})
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"B60 适用性矩阵要求的底稿缺失：{', '.join(codes) if codes else '见质控明细'}",
                location={"project_id": str(project_id), "missing_wp_codes": codes},
                suggested_action="打开 B60 适用性矩阵面板核对勾选，或生成缺失底稿",
            )
        except Exception as e:
            logger.error("[B60-ATTACH-MATRIX] check error: %s", e)
            return None


class B60MaterialityRefRule(GateRule):
    """重要性索引未填 → warning"""

    rule_code = "B60-MATERIALITY-REF"
    error_code = "B60_MATERIALITY_REF_MISSING"
    severity = GateSeverity.warning

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.services.b60_plan_service import evaluate_qc

            qc = await evaluate_qc(project_id, db)
            hits = [f for f in qc.findings if f.code == "B60-MATERIALITY-REF-MISSING"]
            if not hits:
                return None
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=hits[0].message,
                location={"project_id": str(project_id)},
                suggested_action=hits[0].suggested_action,
            )
        except Exception as e:
            logger.error("[B60-MATERIALITY-REF] check error: %s", e)
            return None


class B60dVersionConsistencyRule(GateRule):
    """报送存档版本 ≠ AuditPlan.plan_version → warning（CW-422）"""

    rule_code = "B60D-VERSION-CONSISTENCY"
    error_code = "B60D_VERSION_MISMATCH"
    severity = GateSeverity.warning

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.services.b60_plan_service import evaluate_qc

            qc = await evaluate_qc(project_id, db)
            hits = [
                f
                for f in qc.findings
                if f.code in ("B60D-VERSION-MISMATCH", "B60D-VERSION-UNDECLARED")
            ]
            if not hits:
                return None
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=hits[0].message,
                location={"project_id": str(project_id), **(hits[0].location or {})},
                suggested_action=hits[0].suggested_action,
            )
        except Exception as e:
            logger.error("[B60D-VERSION-CONSISTENCY] check error: %s", e)
            return None


def register_b60_rules():
    gates = [GateType.submit_review, GateType.sign_off, GateType.export_package]
    rule_registry.register_all(gates, B60AttachmentMatrixRule())
    rule_registry.register_all(gates, B60MaterialityRefRule())
    rule_registry.register_all(gates, B60dVersionConsistencyRule())
    logger.info(
        "[GATE] B60 rules registered: B60-ATTACH-MATRIX, B60-MATERIALITY-REF, B60D-VERSION-CONSISTENCY"
    )


register_b60_rules()
