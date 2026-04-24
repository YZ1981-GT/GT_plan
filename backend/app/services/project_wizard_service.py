"""项目初始化向导服务 — 创建项目、管理向导步骤、校验、确认

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    ValidationMessage,
    ValidationResult,
    WizardState,
    WizardStep,
    WizardStepData,
)

# 步骤依赖链：每个步骤的前置步骤必须已完成
STEP_ORDER: list[WizardStep] = [
    WizardStep.basic_info,
    WizardStep.materiality,
    WizardStep.team_assignment,
    WizardStep.template_set,
    WizardStep.confirmation,
]

STEP_DEPENDENCIES: dict[WizardStep, list[WizardStep]] = {
    WizardStep.basic_info: [],
    WizardStep.account_import: [WizardStep.basic_info],
    WizardStep.account_mapping: [WizardStep.basic_info, WizardStep.account_import],
    WizardStep.materiality: [WizardStep.basic_info],
    WizardStep.team_assignment: [WizardStep.basic_info],
    WizardStep.template_set: [WizardStep.basic_info, WizardStep.materiality],
    WizardStep.confirmation: [WizardStep.basic_info],
}

# basic_info 步骤的必填字段
BASIC_INFO_REQUIRED_FIELDS = ["client_name", "audit_year", "project_type", "accounting_standard"]


def _build_initial_wizard_state(project_id: UUID) -> dict:
    """构建初始向导状态 JSONB 数据。"""
    state = WizardState(
        project_id=project_id,
        current_step=WizardStep.basic_info,
        steps={},
        completed=False,
    )
    return state.model_dump(mode="json")


def _parse_wizard_state(project: Project) -> WizardState:
    """从 Project.wizard_state JSONB 解析为 WizardState 对象。"""
    if project.wizard_state is None:
        return WizardState(
            project_id=project.id,
            current_step=WizardStep.basic_info,
            steps={},
            completed=False,
        )
    return WizardState.model_validate(project.wizard_state)


async def _get_project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    """获取项目，不存在则抛 404。"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


async def create_project(data: BasicInfoSchema, db: AsyncSession) -> Project:
    """创建项目记录，状态=created，初始化 wizard_state JSONB。

    Validates: Requirements 1.2, 1.3
    """
    project = Project(
        name=f"{data.client_name}_{data.audit_year}",
        client_name=data.client_name,
        project_type=data.project_type,
        status=ProjectStatus.created,
        manager_id=data.manager_id,
        partner_id=data.signing_partner_id,
        company_code=data.company_code,
        template_type=data.template_type,
        report_scope=data.report_scope,
        parent_company_name=data.parent_company_name,
        parent_company_code=data.parent_company_code,
        ultimate_company_name=data.ultimate_company_name,
        ultimate_company_code=data.ultimate_company_code,
    )
    db.add(project)
    await db.flush()  # 获取 project.id

    # 初始化 wizard_state，并将 basic_info 步骤数据写入
    basic_info_data = data.model_dump(mode="json")
    state = WizardState(
        project_id=project.id,
        current_step=WizardStep.basic_info,
        steps={
            WizardStep.basic_info.value: WizardStepData(
                step=WizardStep.basic_info,
                data=basic_info_data,
                completed=True,
            )
        },
        completed=False,
    )
    project.wizard_state = state.model_dump(mode="json")
    await db.commit()
    await db.refresh(project)
    return project


# ---------------------------------------------------------------------------
# get_wizard_state
# ---------------------------------------------------------------------------


async def get_wizard_state(project_id: UUID, db: AsyncSession) -> WizardState:
    """获取向导当前状态（已完成步骤、当前步骤、各步骤数据）。

    支持断点续做：退出后重新进入恢复已保存步骤数据。
    Validates: Requirements 1.4, 1.5
    """
    project = await _get_project_or_404(db, project_id)
    return _parse_wizard_state(project)


# ---------------------------------------------------------------------------
# update_step
# ---------------------------------------------------------------------------


async def update_step(
    project_id: UUID,
    step: WizardStep,
    data: dict,
    db: AsyncSession,
) -> WizardState:
    """更新指定步骤数据，持久化到 projects.wizard_state JSONB。

    Validates: Requirements 1.3, 1.4, 1.5
    """
    project = await _get_project_or_404(db, project_id)

    if project.status != ProjectStatus.created:
        raise HTTPException(
            status_code=400,
            detail="项目已确认，无法修改向导步骤",
        )

    state = _parse_wizard_state(project)

    # 检查步骤依赖：前置步骤必须已完成
    deps = STEP_DEPENDENCIES.get(step, [])
    for dep in deps:
        dep_step = state.steps.get(dep.value)
        if dep_step is None or not dep_step.completed:
            raise HTTPException(
                status_code=400,
                detail=f"前置步骤 {dep.value} 尚未完成",
            )

    # 更新步骤数据
    state.steps[step.value] = WizardStepData(
        step=step,
        data=data,
        completed=True,
    )
    state.current_step = step

    # 持久化
    project.wizard_state = state.model_dump(mode="json")
    await db.commit()
    await db.refresh(project)
    return _parse_wizard_state(project)


# ---------------------------------------------------------------------------
# validate_step
# ---------------------------------------------------------------------------


async def validate_step(
    project_id: UUID,
    step: WizardStep,
    db: AsyncSession,
) -> ValidationResult:
    """校验指定步骤是否满足前进条件（必填字段 + 步骤依赖）。

    Validates: Requirements 1.8
    """
    project = await _get_project_or_404(db, project_id)
    state = _parse_wizard_state(project)
    messages: list[ValidationMessage] = []

    # 1. 检查步骤依赖
    deps = STEP_DEPENDENCIES.get(step, [])
    for dep in deps:
        dep_step = state.steps.get(dep.value)
        if dep_step is None or not dep_step.completed:
            messages.append(
                ValidationMessage(
                    field=dep.value,
                    message=f"前置步骤「{dep.value}」尚未完成",
                    severity="error",
                )
            )

    # 2. 检查步骤特定的必填字段
    if step == WizardStep.basic_info:
        step_data = state.steps.get(WizardStep.basic_info.value)
        if step_data is None:
            messages.append(
                ValidationMessage(
                    field="basic_info",
                    message="基本信息尚未填写",
                    severity="error",
                )
            )
        else:
            for field in BASIC_INFO_REQUIRED_FIELDS:
                val = step_data.data.get(field)
                if val is None or (isinstance(val, str) and not val.strip()):
                    messages.append(
                        ValidationMessage(
                            field=field,
                            message=f"必填字段「{field}」缺失",
                            severity="error",
                        )
                    )

    elif step == WizardStep.confirmation:
        # 确认步骤的依赖已在上面通用逻辑中检查，这里不重复
        pass

    return ValidationResult(valid=len(messages) == 0, messages=messages)


# ---------------------------------------------------------------------------
# confirm_project
# ---------------------------------------------------------------------------


async def confirm_project(project_id: UUID, db: AsyncSession) -> Project:
    """确认创建，状态 created → planning。

    Validates: Requirements 1.7
    """
    project = await _get_project_or_404(db, project_id)

    if project.status != ProjectStatus.created:
        raise HTTPException(
            status_code=400,
            detail=f"项目状态为 {project.status.value}，无法确认（仅 created 状态可确认）",
        )

    # 校验确认步骤
    validation = await validate_step(project_id, WizardStep.confirmation, db)
    if not validation.valid:
        field_list = ", ".join(m.field for m in validation.messages)
        raise HTTPException(
            status_code=400,
            detail=f"向导校验未通过，缺失步骤: {field_list}",
        )

    # 更新状态
    state = _parse_wizard_state(project)
    state.completed = True
    project.wizard_state = state.model_dump(mode="json")
    project.status = ProjectStatus.planning

    await db.commit()
    await db.refresh(project)
    return project
