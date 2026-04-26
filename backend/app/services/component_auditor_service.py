"""组成部分审计师服务 — 异步 ORM"""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

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

async def get_auditors(db: AsyncSession, project_id: UUID) -> list[ComponentAuditor]:
    result = await db.execute(
        sa.select(ComponentAuditor).where(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def get_auditor(db: AsyncSession, auditor_id: UUID, project_id: UUID) -> ComponentAuditor | None:
    result = await db.execute(
        sa.select(ComponentAuditor).where(
            ComponentAuditor.id == auditor_id,
            ComponentAuditor.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_auditor(db: AsyncSession, project_id: UUID, data: ComponentAuditorCreate) -> ComponentAuditor:
    auditor = ComponentAuditor(project_id=project_id, **data.model_dump())
    db.add(auditor)
    await db.commit()
    await db.refresh(auditor)
    return auditor


async def update_auditor(db: AsyncSession, auditor_id: UUID, project_id: UUID, data: ComponentAuditorUpdate) -> ComponentAuditor | None:
    auditor = await get_auditor(db, auditor_id, project_id)
    if not auditor:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(auditor, key, value)
    await db.commit()
    await db.refresh(auditor)
    return auditor


async def delete_auditor(db: AsyncSession, auditor_id: UUID, project_id: UUID) -> bool:
    auditor = await get_auditor(db, auditor_id, project_id)
    if not auditor:
        return False
    auditor.soft_delete()
    await db.commit()
    return True


# ========== 组成部分指令 ==========

async def get_instructions(db: AsyncSession, project_id: UUID, auditor_id: UUID | None = None) -> list[ComponentInstruction]:
    stmt = sa.select(ComponentInstruction).where(
        ComponentInstruction.project_id == project_id,
        ComponentInstruction.is_deleted.is_(False),
    )
    if auditor_id:
        stmt = stmt.where(ComponentInstruction.component_auditor_id == auditor_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_instruction(db: AsyncSession, instruction_id: UUID, project_id: UUID) -> ComponentInstruction | None:
    result = await db.execute(
        sa.select(ComponentInstruction).where(
            ComponentInstruction.id == instruction_id,
            ComponentInstruction.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_instruction(db: AsyncSession, project_id: UUID, data: InstructionCreate) -> ComponentInstruction:
    instruction = ComponentInstruction(
        project_id=project_id, status=InstructionStatus.PENDING, **data.model_dump(),
    )
    db.add(instruction)
    await db.commit()
    await db.refresh(instruction)
    return instruction


async def update_instruction(db: AsyncSession, instruction_id: UUID, project_id: UUID, data: InstructionUpdate) -> ComponentInstruction | None:
    instruction = await get_instruction(db, instruction_id, project_id)
    if not instruction:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(instruction, key, value)
    await db.commit()
    await db.refresh(instruction)
    return instruction


async def delete_instruction(db: AsyncSession, instruction_id: UUID, project_id: UUID) -> bool:
    instruction = await get_instruction(db, instruction_id, project_id)
    if not instruction:
        return False
    instruction.soft_delete()
    await db.commit()
    return True


# ========== 组成部分结果 ==========

async def get_results(db: AsyncSession, project_id: UUID, auditor_id: UUID | None = None) -> list[ComponentResult]:
    stmt = sa.select(ComponentResult).where(
        ComponentResult.project_id == project_id,
        ComponentResult.is_deleted.is_(False),
    )
    if auditor_id:
        stmt = stmt.where(ComponentResult.component_auditor_id == auditor_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_result(db: AsyncSession, result_id: UUID, project_id: UUID) -> ComponentResult | None:
    result = await db.execute(
        sa.select(ComponentResult).where(
            ComponentResult.id == result_id,
            ComponentResult.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_result(db: AsyncSession, project_id: UUID, data: ResultCreate) -> ComponentResult:
    r = ComponentResult(
        project_id=project_id, evaluation_status=EvaluationStatusEnum.PENDING, **data.model_dump(),
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def update_result(db: AsyncSession, result_id: UUID, project_id: UUID, data: ResultUpdate) -> ComponentResult | None:
    r = await get_result(db, result_id, project_id)
    if not r:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(r, key, value)
    await db.commit()
    await db.refresh(r)
    return r


async def delete_result(db: AsyncSession, result_id: UUID, project_id: UUID) -> bool:
    r = await get_result(db, result_id, project_id)
    if not r:
        return False
    r.soft_delete()
    await db.commit()
    return True


# ========== 看板 ==========

async def get_dashboard(db: AsyncSession, project_id: UUID) -> ComponentDashboard:
    total = (await db.execute(
        sa.select(func.count(ComponentAuditor.id)).where(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted.is_(False),
        )
    )).scalar() or 0

    pending_instructions = (await db.execute(
        sa.select(func.count(ComponentInstruction.id)).where(
            ComponentInstruction.project_id == project_id,
            ComponentInstruction.is_deleted.is_(False),
            ComponentInstruction.status == InstructionStatus.PENDING,
        )
    )).scalar() or 0

    pending_results = (await db.execute(
        sa.select(func.count(ComponentResult.id)).where(
            ComponentResult.project_id == project_id,
            ComponentResult.is_deleted.is_(False),
            ComponentResult.evaluation_status == EvaluationStatusEnum.PENDING,
        )
    )).scalar() or 0

    received_results = (await db.execute(
        sa.select(func.count(ComponentResult.id)).where(
            ComponentResult.project_id == project_id,
            ComponentResult.is_deleted.is_(False),
        )
    )).scalar() or 0

    non_standard = (await db.execute(
        sa.select(func.count(ComponentResult.id)).where(
            ComponentResult.project_id == project_id,
            ComponentResult.is_deleted.is_(False),
            ComponentResult.opinion_type != None,  # noqa: E711
        )
    )).scalar() or 0

    return ComponentDashboard(
        total_auditors=total,
        pending_instructions=pending_instructions,
        pending_results=pending_results,
        received_results=received_results,
        non_standard_opinions=non_standard,
    )
