"""组成部分审计师服务"""

from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.consolidation_models import (
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
    InstructionStatus,
    EvaluationStatusEnum,
)
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    ComponentAuditorResponse,
    InstructionCreate,
    InstructionUpdate,
    InstructionResponse,
    ResultCreate,
    ResultUpdate,
    ResultResponse,
    ComponentDashboard,
)


# ========== 组成部分审计师 ==========


def get_auditors(db: Session, project_id: UUID) -> list[ComponentAuditor]:
    return (
        db.query(ComponentAuditor)
        .filter(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted.is_(False),
        )
        .all()
    )


def get_auditor(db: Session, auditor_id: UUID, project_id: UUID) -> ComponentAuditor | None:
    return (
        db.query(ComponentAuditor)
        .filter(
            ComponentAuditor.id == auditor_id,
            ComponentAuditor.project_id == project_id,
        )
        .first()
    )


def create_auditor(db: Session, project_id: UUID, data: ComponentAuditorCreate) -> ComponentAuditor:
    auditor = ComponentAuditor(project_id=project_id, **data.model_dump())
    db.add(auditor)
    db.commit()
    db.refresh(auditor)
    return auditor


def update_auditor(
    db: Session, auditor_id: UUID, project_id: UUID, data: ComponentAuditorUpdate
) -> ComponentAuditor | None:
    auditor = get_auditor(db, auditor_id, project_id)
    if not auditor:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(auditor, key, value)
    db.commit()
    db.refresh(auditor)
    return auditor


def delete_auditor(db: Session, auditor_id: UUID, project_id: UUID) -> bool:
    auditor = get_auditor(db, auditor_id, project_id)
    if not auditor:
        return False
    auditor.is_deleted = True
    db.commit()
    return True


# ========== 组成部分指令 ==========


def get_instructions(db: Session, project_id: UUID, auditor_id: UUID | None = None) -> list[ComponentInstruction]:
    q = db.query(ComponentInstruction).filter(
        ComponentInstruction.project_id == project_id,
        ComponentInstruction.is_deleted.is_(False),
    )
    if auditor_id:
        q = q.filter(ComponentInstruction.component_auditor_id == auditor_id)
    return q.all()


def get_instruction(db: Session, instruction_id: UUID, project_id: UUID) -> ComponentInstruction | None:
    return (
        db.query(ComponentInstruction)
        .filter(
            ComponentInstruction.id == instruction_id,
            ComponentInstruction.project_id == project_id,
        )
        .first()
    )


def create_instruction(db: Session, project_id: UUID, data: InstructionCreate) -> ComponentInstruction:
    instruction = ComponentInstruction(
        project_id=project_id,
        status=InstructionStatus.PENDING,
        **data.model_dump(),
    )
    db.add(instruction)
    db.commit()
    db.refresh(instruction)
    return instruction


def update_instruction(
    db: Session, instruction_id: UUID, project_id: UUID, data: InstructionUpdate
) -> ComponentInstruction | None:
    instruction = get_instruction(db, instruction_id, project_id)
    if not instruction:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(instruction, key, value)
    db.commit()
    db.refresh(instruction)
    return instruction


def delete_instruction(db: Session, instruction_id: UUID, project_id: UUID) -> bool:
    instruction = get_instruction(db, instruction_id, project_id)
    if not instruction:
        return False
    instruction.is_deleted = True
    db.commit()
    return True


# ========== 组成部分结果 ==========


def get_results(db: Session, project_id: UUID, auditor_id: UUID | None = None) -> list[ComponentResult]:
    q = db.query(ComponentResult).filter(
        ComponentResult.project_id == project_id,
        ComponentResult.is_deleted.is_(False),
    )
    if auditor_id:
        q = q.filter(ComponentResult.component_auditor_id == auditor_id)
    return q.all()


def get_result(db: Session, result_id: UUID, project_id: UUID) -> ComponentResult | None:
    return (
        db.query(ComponentResult)
        .filter(
            ComponentResult.id == result_id,
            ComponentResult.project_id == project_id,
        )
        .first()
    )


def create_result(db: Session, project_id: UUID, data: ResultCreate) -> ComponentResult:
    result = ComponentResult(
        project_id=project_id,
        evaluation_status=EvaluationStatusEnum.PENDING,
        **data.model_dump(),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def update_result(
    db: Session, result_id: UUID, project_id: UUID, data: ResultUpdate
) -> ComponentResult | None:
    result = get_result(db, result_id, project_id)
    if not result:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(result, key, value)
    db.commit()
    db.refresh(result)
    return result


def delete_result(db: Session, result_id: UUID, project_id: UUID) -> bool:
    result = get_result(db, result_id, project_id)
    if not result:
        return False
    result.is_deleted = True
    db.commit()
    return True


# ========== 看板 ==========


def get_dashboard(db: Session, project_id: UUID) -> ComponentDashboard:
    total = db.query(func.count(ComponentAuditor.id)).filter(
        ComponentAuditor.project_id == project_id,
        ComponentAuditor.is_deleted.is_(False),
    ).scalar() or 0

    pending_instructions = db.query(func.count(ComponentInstruction.id)).filter(
        ComponentInstruction.project_id == project_id,
        ComponentInstruction.is_deleted.is_(False),
        ComponentInstruction.status == InstructionStatus.PENDING,
    ).scalar() or 0

    pending_results = db.query(func.count(ComponentResult.id)).filter(
        ComponentResult.project_id == project_id,
        ComponentResult.is_deleted.is_(False),
        ComponentResult.evaluation_status == EvaluationStatusEnum.PENDING,
    ).scalar() or 0

    received_results = db.query(func.count(ComponentResult.id)).filter(
        ComponentResult.project_id == project_id,
        ComponentResult.is_deleted.is_(False),
    ).scalar() or 0

    non_standard = db.query(func.count(ComponentResult.id)).filter(
        ComponentResult.project_id == project_id,
        ComponentResult.is_deleted.is_(False),
        ComponentResult.opinion_type != None,  # noqa: E711
    ).scalar() or 0

    return ComponentDashboard(
        total_auditors=total,
        pending_instructions=pending_instructions,
        pending_results=pending_results,
        received_results=received_results,
        non_standard_opinions=non_standard,
    )
