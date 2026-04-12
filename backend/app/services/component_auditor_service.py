"""组成部分审计师服务

提供组成部分审计师、审计指令和审计结果的业务逻辑处理。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.consolidation_models import (
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
    CompetenceRating,
    EvaluationStatus,
    InstructionStatus,
    OpinionTypeEnum,
)
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    ComponentAuditorResponse,
    ComponentDashboard,
    ComponentInstructionResponse,
    ComponentResultCreate,
    ComponentResultResponse,
    InstructionCreate,
    InstructionSend,
    InstructionUpdate,
)


# =============================================================================
# ComponentAuditorService
# =============================================================================


class ComponentAuditorService:
    """组成部分审计师服务类"""

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # 5.1 组成部分审计师 CRUD
    # -------------------------------------------------------------------------

    def create_auditor(
        self, project_id: UUID, data: ComponentAuditorCreate
    ) -> ComponentAuditor:
        """创建组成部分审计师记录

        Args:
            project_id: 项目ID
            data: 创建数据，包含 competence_rating 和 rating_basis

        Returns:
            创建的 ComponentAuditor 记录

        Raises:
            ValueError: 如果 competence_rating 或 rating_basis 缺失
        """
        # 验证 competence_rating 和 rating_basis 必须提供
        if data.competence_rating is None:
            raise ValueError("competence_rating (胜任能力评价) 必须提供")
        if data.rating_basis is None:
            raise ValueError("rating_basis (评价依据) 必须提供")

        auditor = ComponentAuditor(
            project_id=project_id,
            company_code=data.company_code,
            firm_name=data.firm_name,
            contact_person=data.contact_person,
            contact_info=data.contact_info,
            competence_rating=data.competence_rating,
            rating_basis=data.rating_basis,
            independence_confirmed=data.independence_confirmed,
            independence_date=data.independence_date,
            is_deleted=False,
        )
        self.db.add(auditor)
        self.db.commit()
        self.db.refresh(auditor)
        return auditor

    def update_auditor(
        self,
        auditor_id: UUID,
        data: ComponentAuditorUpdate,
    ) -> ComponentAuditor | None:
        """更新组成部分审计师记录

        Args:
            auditor_id: 审计师ID
            data: 更新数据

        Returns:
            更新后的 ComponentAuditor 记录，如果不存在返回 None
        """
        auditor = self.get_auditor(auditor_id)
        if not auditor:
            return None

        # 获取旧值用于日志记录
        old_competence_rating = auditor.competence_rating
        old_rating_basis = auditor.rating_basis

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(auditor, key, value)

        # 如果评分发生变化，记录变化
        if (
            "competence_rating" in update_data
            and update_data["competence_rating"] != old_competence_rating
        ):
            # 评分变更日志（实际项目中可记录到审计日志表）
            audit_log = {
                "auditor_id": str(auditor_id),
                "field": "competence_rating",
                "old_value": old_competence_rating.value
                if old_competence_rating
                else None,
                "new_value": update_data["competence_rating"].value
                if update_data["competence_rating"]
                else None,
                "timestamp": datetime.utcnow().isoformat(),
            }
            # 审计日志记录可以扩展为独立的审计日志表

        if (
            "rating_basis" in update_data
            and update_data["rating_basis"] != old_rating_basis
        ):
            audit_log = {
                "auditor_id": str(auditor_id),
                "field": "rating_basis",
                "old_value": old_rating_basis,
                "new_value": update_data["rating_basis"],
                "timestamp": datetime.utcnow().isoformat(),
            }

        self.db.commit()
        self.db.refresh(auditor)
        return auditor

    def get_auditor(self, auditor_id: UUID) -> ComponentAuditor | None:
        """获取单个组成部分审计师

        Args:
            auditor_id: 审计师ID

        Returns:
            ComponentAuditor 记录或 None
        """
        return (
            self.db.query(ComponentAuditor)
            .filter(
                ComponentAuditor.id == auditor_id,
                ComponentAuditor.is_deleted.is_(False),
            )
            .first()
        )

    def get_auditors_by_project(self, project_id: UUID) -> list[ComponentAuditor]:
        """获取项目下所有组成部分审计师

        Args:
            project_id: 项目ID

        Returns:
            ComponentAuditor 记录列表
        """
        return (
            self.db.query(ComponentAuditor)
            .filter(
                ComponentAuditor.project_id == project_id,
                ComponentAuditor.is_deleted.is_(False),
            )
            .order_by(ComponentAuditor.firm_name)
            .all()
        )

    def get_dashboard(self, project_id: UUID) -> dict[str, Any]:
        """获取仪表盘统计信息

        Args:
            project_id: 项目ID

        Returns:
            包含以下统计信息的字典:
            - total_auditors: 审计师总数
            - instructions_by_status: 各状态的指令数量
            - results_by_status: 各状态的结果数量
            - pending_review: 待复核的指令/结果数量
        """
        # 审计师总数
        total_auditors = (
            self.db.query(func.count(ComponentAuditor.id))
            .filter(
                ComponentAuditor.project_id == project_id,
                ComponentAuditor.is_deleted.is_(False),
            )
            .scalar()
            or 0
        )

        # 指令按状态统计
        instructions_status_raw = (
            self.db.query(
                ComponentInstruction.status,
                func.count(ComponentInstruction.id).label("count"),
            )
            .filter(
                ComponentInstruction.project_id == project_id,
                ComponentInstruction.is_deleted.is_(False),
            )
            .group_by(ComponentInstruction.status)
            .all()
        )
        instructions_by_status = {
            status.value: count for status, count in instructions_status_raw
        }

        # 结果按状态统计
        results_status_raw = (
            self.db.query(
                ComponentResult.evaluation_status,
                func.count(ComponentResult.id).label("count"),
            )
            .filter(
                ComponentResult.project_id == project_id,
                ComponentResult.is_deleted.is_(False),
            )
            .group_by(ComponentResult.evaluation_status)
            .all()
        )
        results_by_status = {
            status.value: count for status, count in results_status_raw
        }

        # 待复核数量（指令中 pending_review 或 acknowledged 状态的，以及结果中 pending 状态的）
        pending_review_instructions = (
            self.db.query(func.count(ComponentInstruction.id))
            .filter(
                ComponentInstruction.project_id == project_id,
                ComponentInstruction.is_deleted.is_(False),
                ComponentInstruction.status.in_(
                    [InstructionStatus.draft, InstructionStatus.sent]
                ),
            )
            .scalar()
            or 0
        )

        pending_review_results = (
            self.db.query(func.count(ComponentResult.id))
            .filter(
                ComponentResult.project_id == project_id,
                ComponentResult.is_deleted.is_(False),
                ComponentResult.evaluation_status == EvaluationStatus.pending,
            )
            .scalar()
            or 0
        )

        pending_review = pending_review_instructions + pending_review_results

        return {
            "total_auditors": total_auditors,
            "instructions_by_status": instructions_by_status,
            "results_by_status": results_by_status,
            "pending_review": pending_review,
        }

    # -------------------------------------------------------------------------
    # 5.2 审计指令管理
    # -------------------------------------------------------------------------

    def create_instruction(
        self, project_id: UUID, data: InstructionCreate
    ) -> ComponentInstruction:
        """创建审计指令

        Args:
            project_id: 项目ID
            data: 创建数据

        Returns:
            创建的 ComponentInstruction 记录

        Raises:
            ValueError: 如果审计师不属于该项目
        """
        # 验证审计师属于该项目
        auditor = (
            self.db.query(ComponentAuditor)
            .filter(
                ComponentAuditor.id == data.component_auditor_id,
                ComponentAuditor.project_id == project_id,
                ComponentAuditor.is_deleted.is_(False),
            )
            .first()
        )
        if not auditor:
            raise ValueError(
                f"审计师 ID '{data.component_auditor_id}' 不属于该项目"
            )

        instruction = ComponentInstruction(
            project_id=project_id,
            component_auditor_id=data.component_auditor_id,
            instruction_date=data.instruction_date,
            due_date=data.due_date,
            materiality_level=data.materiality_level,
            audit_scope_description=data.audit_scope_description,
            reporting_format=data.reporting_format,
            special_attention_items=data.special_attention_items,
            instruction_file_path=data.instruction_file_path,
            status=InstructionStatus.draft,
            is_deleted=False,
        )
        self.db.add(instruction)
        self.db.commit()
        self.db.refresh(instruction)
        return instruction

    def send_instruction(
        self, instruction_id: UUID
    ) -> ComponentInstruction:
        """发送审计指令

        锁定指令内容，更新状态为 sent，并记录发送时间。

        Args:
            instruction_id: 指令ID

        Returns:
            更新后的 ComponentInstruction 记录

        Raises:
            ValueError: 如果指令已发送或不存在
        """
        instruction = self.get_instruction(instruction_id)
        if not instruction:
            raise ValueError("指令不存在")

        if instruction.status == InstructionStatus.sent:
            raise ValueError("指令已发送，无法重复发送")

        if instruction.status == InstructionStatus.acknowledged:
            raise ValueError("指令已被确认，无法重新发送")

        # 锁定指令内容并更新状态
        instruction.status = InstructionStatus.sent
        instruction.sent_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(instruction)
        return instruction

    def get_instructions(
        self,
        project_id: UUID,
        filters: dict[str, Any] | None = None,
    ) -> list[ComponentInstruction]:
        """获取审计指令列表

        支持按审计师ID、状态、年份过滤。

        Args:
            project_id: 项目ID
            filters: 过滤条件，包含:
                - auditor_id: 审计师ID
                - status: 指令状态
                - year: 年份（通过 due_date 或 instruction_date 过滤）

        Returns:
            ComponentInstruction 记录列表
        """
        query = (
            self.db.query(ComponentInstruction)
            .filter(
                ComponentInstruction.project_id == project_id,
                ComponentInstruction.is_deleted.is_(False),
            )
        )

        if filters:
            if "auditor_id" in filters and filters["auditor_id"]:
                query = query.filter(
                    ComponentInstruction.component_auditor_id
                    == filters["auditor_id"]
                )
            if "status" in filters and filters["status"]:
                query = query.filter(
                    ComponentInstruction.status == filters["status"]
                )
            if "year" in filters and filters["year"]:
                year = filters["year"]
                query = query.filter(
                    (ComponentInstruction.instruction_date >= f"{year}-01-01")
                    & (
                        ComponentInstruction.instruction_date
                        <= f"{year}-12-31"
                    )
                    | (ComponentInstruction.due_date >= f"{year}-01-01")
                    & (ComponentInstruction.due_date <= f"{year}-12-31")
                )

        return query.order_by(ComponentInstruction.created_at.desc()).all()

    def get_instruction(
        self, instruction_id: UUID
    ) -> ComponentInstruction | None:
        """获取单个审计指令

        Args:
            instruction_id: 指令ID

        Returns:
            ComponentInstruction 记录或 None
        """
        return (
            self.db.query(ComponentInstruction)
            .filter(
                ComponentInstruction.id == instruction_id,
                ComponentInstruction.is_deleted.is_(False),
            )
            .first()
        )

    def update_instruction(
        self,
        instruction_id: UUID,
        data: InstructionUpdate,
    ) -> ComponentInstruction | None:
        """更新审计指令

        仅允许在指令状态为 draft 时更新。

        Args:
            instruction_id: 指令ID
            data: 更新数据

        Returns:
            更新后的 ComponentInstruction 记录

        Raises:
            ValueError: 如果指令已发送
        """
        instruction = self.get_instruction(instruction_id)
        if not instruction:
            return None

        # 仅允许在草稿状态更新
        if instruction.status != InstructionStatus.draft:
            raise ValueError(
                f"指令状态为 '{instruction.status.value}'，仅草稿状态可更新"
            )

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(instruction, key, value)

        self.db.commit()
        self.db.refresh(instruction)
        return instruction

    # -------------------------------------------------------------------------
    # 5.3 审计结果管理
    # -------------------------------------------------------------------------

    def receive_result(
        self, project_id: UUID, data: ComponentResultCreate
    ) -> ComponentResult:
        """接收审计结果

        Args:
            project_id: 项目ID
            data: 创建数据

        Returns:
            创建的 ComponentResult 记录

        Raises:
            ValueError: 如果指令或审计师不属于该项目，或非标准意见缺少说明
        """
        # 验证指令存在
        instruction = (
            self.db.query(ComponentInstruction)
            .filter(
                ComponentInstruction.id == data.component_auditor_id,
                ComponentInstruction.project_id == project_id,
                ComponentInstruction.is_deleted.is_(False),
            )
            .first()
        )
        if not instruction:
            raise ValueError(f"指令 ID '{data.component_auditor_id}' 不存在")

        # 验证审计师属于该项目
        auditor = (
            self.db.query(ComponentAuditor)
            .filter(
                ComponentAuditor.id == instruction.component_auditor_id,
                ComponentAuditor.project_id == project_id,
                ComponentAuditor.is_deleted.is_(False),
            )
            .first()
        )
        if not auditor:
            raise ValueError(
                f"指令关联的审计师不属于该项目"
            )

        # 非标准意见需要提供说明
        is_non_standard = data.opinion_type not in [
            OpinionTypeEnum.unqualified,
            None,
        ]
        if is_non_standard and not data.group_team_evaluation:
            raise ValueError(
                "非标准意见(opinion_type 非 unqualified)必须提供评价说明 (group_team_evaluation)"
            )

        result = ComponentResult(
            project_id=project_id,
            component_auditor_id=instruction.component_auditor_id,
            received_date=data.received_date,
            opinion_type=data.opinion_type,
            identified_misstatements=data.identified_misstatements,
            significant_findings=data.significant_findings,
            result_file_path=data.result_file_path,
            group_team_evaluation=data.group_team_evaluation,
            needs_additional_procedures=data.needs_additional_procedures,
            evaluation_status=EvaluationStatus.pending,
            is_deleted=False,
        )

        # 标记非标准意见
        if is_non_standard:
            result.needs_additional_procedures = True

        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def accept_result(self, result_id: UUID) -> ComponentResult:
        """接受审计结果

        接受后，组成部分的调整金额可用于合并。

        Args:
            result_id: 结果ID

        Returns:
            更新后的 ComponentResult 记录

        Raises:
            ValueError: 如果结果不存在或状态不是 received
        """
        result = self.get_result(result_id)
        if not result:
            raise ValueError("结果不存在")

        if result.evaluation_status != EvaluationStatus.pending:
            raise ValueError(
                f"结果状态为 '{result.evaluation_status.value}'，仅待处理状态可接受"
            )

        result.evaluation_status = EvaluationStatus.accepted
        # 接受后，该结果中的调整金额可用于合并工作

        self.db.commit()
        self.db.refresh(result)
        return result

    def reject_result(
        self, result_id: UUID, reason: str
    ) -> ComponentResult:
        """拒绝审计结果

        Args:
            result_id: 结果ID
            reason: 拒绝原因

        Returns:
            更新后的 ComponentResult 记录
        """
        result = self.get_result(result_id)
        if not result:
            raise ValueError("结果不存在")

        result.evaluation_status = EvaluationStatus.requires_followup
        result.significant_findings = (
            f"{result.significant_findings or ''}\n拒绝原因: {reason}".strip()
        )

        self.db.commit()
        self.db.refresh(result)
        return result

    def get_results(
        self,
        project_id: UUID,
        filters: dict[str, Any] | None = None,
    ) -> list[ComponentResult]:
        """获取审计结果列表

        支持按审计师ID、指令ID、状态、年份过滤。

        Args:
            project_id: 项目ID
            filters: 过滤条件，包含:
                - auditor_id: 审计师ID
                - instruction_id: 指令ID
                - status: 结果状态
                - year: 年份（通过 received_date 过滤）

        Returns:
            ComponentResult 记录列表
        """
        query = (
            self.db.query(ComponentResult)
            .filter(
                ComponentResult.project_id == project_id,
                ComponentResult.is_deleted.is_(False),
            )
        )

        if filters:
            if "auditor_id" in filters and filters["auditor_id"]:
                query = query.filter(
                    ComponentResult.component_auditor_id == filters["auditor_id"]
                )
            if "instruction_id" in filters and filters["instruction_id"]:
                # 需要通过指令关联查询
                instruction_ids = (
                    self.db.query(ComponentInstruction.id)
                    .filter(
                        ComponentInstruction.id == filters["instruction_id"],
                        ComponentInstruction.project_id == project_id,
                    )
                    .subquery()
                )
                query = query.filter(
                    ComponentResult.component_auditor_id.in_(instruction_ids)
                )
            if "status" in filters and filters["status"]:
                query = query.filter(
                    ComponentResult.evaluation_status == filters["status"]
                )
            if "year" in filters and filters["year"]:
                year = filters["year"]
                query = query.filter(
                    (ComponentResult.received_date >= f"{year}-01-01")
                    & (ComponentResult.received_date <= f"{year}-12-31")
                )

        return query.order_by(ComponentResult.created_at.desc()).all()

    def get_result(self, result_id: UUID) -> ComponentResult | None:
        """获取单个审计结果

        Args:
            result_id: 结果ID

        Returns:
            ComponentResult 记录或 None
        """
        return (
            self.db.query(ComponentResult)
            .filter(
                ComponentResult.id == result_id,
                ComponentResult.is_deleted.is_(False),
            )
            .first()
        )
