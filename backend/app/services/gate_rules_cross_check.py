"""跨科目校验门禁规则

Sprint 4 Task 4.8: 集成到签字前门禁 gate_engine（CROSS_CHECK_PASSED 规则）
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_enums import GateType
from app.services.gate_engine import GateRule, GateRuleHit, rule_registry

logger = logging.getLogger(__name__)


class CrossCheckPassedRule(GateRule):
    """跨科目校验通过规则

    签字前门禁：检查所有 blocking 级别的跨科目校验规则是否通过。
    """

    rule_code = "R4-CROSS-CHECK"
    error_code = "CROSS_CHECK_FAILED"
    severity = "blocking"

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        """检查跨科目校验是否全部通过"""
        from app.services.wp_cross_check_service import CrossCheckService

        project_id = context.get("project_id")
        if not project_id:
            return None

        # 从 context 获取年度，默认当前年
        year = context.get("year")
        if not year:
            # 尝试从项目获取
            import sqlalchemy as sa
            try:
                q = sa.text("SELECT year FROM working_paper WHERE project_id = :pid LIMIT 1")
                result = await db.execute(q, {"pid": str(project_id)})
                row = result.first()
                year = row[0] if row else None
            except Exception:
                pass

        if not year:
            # 无法确定年度，跳过检查
            return None

        svc = CrossCheckService(db)
        passed = await svc.check_for_sign_off(project_id, year)

        if not passed:
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="跨科目校验存在 blocking 级别失败项，请先修正差异",
                location={"project_id": str(project_id), "year": year},
                suggested_action="执行跨科目校验并修正所有 blocking 差异",
            )

        return None


def register_cross_check_rules():
    """注册跨科目校验规则到 sign_off 门禁"""
    rule_registry.register_all([GateType.sign_off], CrossCheckPassedRule())
    logger.info("[GATE] Cross-check rule R4-CROSS-CHECK registered to sign_off")
