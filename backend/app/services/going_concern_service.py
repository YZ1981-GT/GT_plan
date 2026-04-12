from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.collaboration_models import (
    GoingConcern, GoingConcernIndicator, GcRiskLevel, IndicatorSeverity,
)
from datetime import datetime, timezone
import uuid


class GoingConcernService:
    @staticmethod
    def init_indicators(db: Session, project_id: str, created_by: str) -> List[GoingConcernIndicator]:
        """项目创建时预填充标准风险指标"""
        gc = GoingConcern(
            id=uuid.uuid4(),
            project_id=project_id,
            assessment_date=datetime.now(timezone.utc).date(),
            has_gc_indicator=False,
            risk_level=GcRiskLevel.low,
            assessment_basis="",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=created_by,
        )
        db.add(gc)
        db.commit()
        db.refresh(gc)

        # Standard financial indicators
        items = [
            ("FIN-001", "连续亏损超过2年", IndicatorSeverity.high),
            ("FIN-002", "营运资金为负", IndicatorSeverity.high),
            ("FIN-003", "债务逾期或违约", IndicatorSeverity.high),
            ("FIN-004", "经营现金净流量持续为负", IndicatorSeverity.medium),
            ("FIN-005", "主要财务指标恶化", IndicatorSeverity.medium),
            ("OPS-001", "重要业务板块终止或重大业务流失", IndicatorSeverity.high),
            ("OPS-002", "主要供应商或客户流失", IndicatorSeverity.medium),
            ("OPS-003", "关键管理人员或核心技术流失", IndicatorSeverity.medium),
            ("LAW-001", "重大诉讼或仲裁", IndicatorSeverity.high),
            ("LAW-002", "监管处罚或重大合规问题", IndicatorSeverity.high),
            ("LAW-003", "主要资产被查封或冻结", IndicatorSeverity.high),
            ("EXT-001", "行业整体衰退且无好转迹象", IndicatorSeverity.medium),
            ("EXT-002", "重大宏观经济变化（汇率/利率/政策）", IndicatorSeverity.medium),
            ("EXT-003", "不可抗力事件影响持续经营", IndicatorSeverity.high),
        ]
        indicators = []
        for code, desc, severity in items:
            ind = GoingConcernIndicator(
                id=uuid.uuid4(),
                going_concern_id=gc.id,
                indicator_type=code,
                description=desc,
                severity=severity,
                is_identified=False,
                is_deleted=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(ind)
            indicators.append(ind)
        db.commit()
        return indicators

    @staticmethod
    def create_evaluation(
        db: Session,
        project_id: str,
        assessment_date=None,
        created_by: str = None,
    ) -> GoingConcern:
        gc = GoingConcern(
            id=uuid.uuid4(),
            project_id=project_id,
            assessment_date=assessment_date or datetime.now(timezone.utc).date(),
            has_gc_indicator=False,
            risk_level=GcRiskLevel.low,
            assessment_basis="",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=created_by,
        )
        db.add(gc)
        db.commit()
        db.refresh(gc)
        return gc

    @staticmethod
    def update_evaluation(
        db: Session,
        gc_id: str,
        has_gc_indicator: bool,
        risk_level: str,
        assessment_basis: Optional[str] = None,
        management_plans: Optional[str] = None,
        auditor_conclusion: Optional[str] = None,
    ) -> Optional[GoingConcern]:
        gc = db.query(GoingConcern).filter(GoingConcern.id == gc_id).first()
        if not gc:
            return None
        gc.has_gc_indicator = has_gc_indicator
        gc.risk_level = GcRiskLevel[risk_level.upper()]
        if assessment_basis is not None:
            gc.assessment_basis = assessment_basis
        if management_plans is not None:
            gc.management_plans = management_plans
        if auditor_conclusion is not None:
            gc.auditor_conclusion = auditor_conclusion
        gc.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(gc)
        return gc

    @staticmethod
    def get_evaluation(db: Session, project_id: str) -> Optional[GoingConcern]:
        return db.query(GoingConcern).filter(
            GoingConcern.project_id == project_id,
            GoingConcern.is_deleted == False,  # noqa: E712
        ).order_by(GoingConcern.created_at.desc()).first()

    @staticmethod
    def update_indicator(
        db: Session,
        indicator_id: str,
        is_identified: bool,
        evidence: Optional[str] = None,
    ) -> Optional[GoingConcernIndicator]:
        ind = db.query(GoingConcernIndicator).filter(
            GoingConcernIndicator.id == indicator_id
        ).first()
        if ind:
            ind.is_identified = is_identified
            if evidence:
                ind.evidence = evidence
            ind.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(ind)
        return ind

    @staticmethod
    def get_indicators(db: Session, gc_id: str) -> List[GoingConcernIndicator]:
        return db.query(GoingConcernIndicator).filter(
            GoingConcernIndicator.going_concern_id == gc_id,
            GoingConcernIndicator.is_deleted == False,  # noqa: E712
        ).all()



    @staticmethod
    def get_conclusion_gates(db: Session, project_id: str) -> dict:
        """获取持续经营结论门控条件"""
        gc = GoingConcernService.get_evaluation(db, project_id)
        indicators = []
        if gc:
            indicators = GoingConcernService.get_indicators(db, str(gc.id))

        high_indicators = [
            ind for ind in indicators
            if ind.is_identified and ind.severity == IndicatorSeverity.high
        ]
        medium_indicators = [
            ind for ind in indicators
            if ind.is_identified and ind.severity == IndicatorSeverity.medium
        ]

        # 门控逻辑
        if gc and gc.has_gc_indicator and gc.risk_level == GcRiskLevel.high:
            conclusion_type = "going_concern_inappropriate"
            gates = [
                {"gate": "high_indicator", "passed": len(high_indicators) == 0, "message": "无高风险指标"},
                {"gate": "management_plan", "passed": bool(gc.management_plans), "message": "管理层应对计划"},
                {"gate": "auditor_conclusion", "passed": bool(gc.auditor_conclusion), "message": "审计师结论"},
            ]
        elif gc and gc.has_gc_indicator and gc.risk_level == GcRiskLevel.medium:
            conclusion_type = "material_uncertainty"
            gates = [
                {"gate": "medium_indicator", "passed": len(medium_indicators) == 0, "message": "无中等风险指标"},
                {"gate": "disclosure", "passed": bool(gc.assessment_basis), "message": "披露充分性"},
            ]
        else:
            conclusion_type = "no_significant_doubt"
            gates = []

        return {
            "project_id": str(project_id),
            "conclusion_type": conclusion_type,
            "gates": gates,
            "high_risk_count": len(high_indicators),
            "medium_risk_count": len(medium_indicators),
            "all_gates_passed": all(g["passed"] for g in gates),
        }
