"""签发与导出包的实时证据就绪门。"""
from __future__ import annotations

from app.models.phase14_enums import GateSeverity, GateType
from app.services.gate_engine import GateRule, GateRuleHit, rule_registry


class EvidenceReadinessRule(GateRule):
    rule_code = "EVIDENCE-READINESS"
    error_code = "EVIDENCE_NOT_READY"
    severity = GateSeverity.blocking

    async def check(self, db, context: dict):
        from app.services.evidence_readiness import EvidenceReadinessService

        project_id = context.get("project_id")
        if project_id is None:
            return self.not_executed("缺少项目，无法判断审计证据是否就绪")
        result = await EvidenceReadinessService(db).evaluate_project(project_id)
        if result.status in {"ready", "not_declared"}:
            return None
        blockers = result.blockers
        unknown = result.status == "unknown"
        codes = [row.wp_code or "未知底稿" for row in blockers[:10]]
        return GateRuleHit(
            rule_code=self.rule_code,
            error_code="EVIDENCE_READINESS_UNKNOWN" if unknown else self.error_code,
            severity=GateSeverity.blocking,
            message=(
                "证据状态无法判断，禁止继续正式签发或归档"
                if unknown
                else f"{len(blockers)} 张底稿证据未就绪：{'、'.join(codes)}"
            ),
            location={
                "project_id": str(project_id),
                "workpaper_ids": [str(row.wp_id) for row in blockers[:20]],
                "status": result.status,
            },
            suggested_action="请在底稿附件中补齐并确认要求的证据后重试",
        )


def register_evidence_readiness_rule() -> None:
    rule_registry.register_all(
        [GateType.sign_off, GateType.export_package], EvidenceReadinessRule(),
    )


register_evidence_readiness_rule()
