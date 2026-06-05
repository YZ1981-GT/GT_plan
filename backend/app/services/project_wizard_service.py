"""项目初始化向导服务 — 创建项目、管理向导步骤、校验、确认

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8
"""

import logging
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
from app.services.note_template_service import NoteTemplateService
from app.services.uscc_validator import validate_uscc
from app.services.uniqueness_checker import check_uniqueness

# 默认报表类型（与 batch_project_service.DEFAULT_REPORT_SCOPE 保持一致）
DEFAULT_REPORT_SCOPE = "standalone"

logger = logging.getLogger(__name__)

# 步骤依赖链：每个步骤的前置步骤必须已完成
STEP_ORDER: list[WizardStep] = [
    WizardStep.basic_info,
    WizardStep.account_import,
    WizardStep.account_mapping,
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
    # 确认无前置依赖——基本信息在 create_project 时已自动保存，直接可确认
    WizardStep.confirmation: [],
}

# basic_info 步骤的必填字段
BASIC_INFO_REQUIRED_FIELDS = ["client_name", "audit_year", "project_type", "accounting_standard"]


def _normalize_basic_info(
    data: BasicInfoSchema,
    existing_basic_info: dict | None = None,
) -> tuple[BasicInfoSchema, dict | None]:
    template_service = NoteTemplateService()
    if data.template_type != "custom":
        data.custom_template_id = None
        data.custom_template_name = None
        data.custom_template_version = None
        return data, None

    if not data.custom_template_id:
        raise HTTPException(status_code=400, detail="选择自定义附注模板时必须提供模板标识")

    existing_snapshot = template_service.get_locked_template_snapshot(existing_basic_info)
    if existing_snapshot is not None and existing_snapshot.get("id") == data.custom_template_id:
        locked_snapshot = existing_snapshot
    else:
        template = template_service.get_template(data.custom_template_id)
        if template is None:
            raise HTTPException(status_code=400, detail="所选自定义附注模板不存在或已失效，请重新选择")
        locked_snapshot = template_service.build_locked_template_snapshot(template)

    data.custom_template_name = locked_snapshot.get("name") or data.custom_template_name
    data.custom_template_version = locked_snapshot.get("version") or data.custom_template_version
    return data, locked_snapshot


def _sync_basic_info_to_project(project: Project, data: BasicInfoSchema) -> None:
    project.name = f"{data.client_name}_{data.audit_year}"
    project.client_name = data.client_name
    project.project_type = data.project_type
    project.manager_id = data.manager_id
    project.partner_id = data.signing_partner_id
    project.company_code = data.company_code
    project.short_name = data.short_name
    project.audit_year = data.audit_year
    project.template_type = data.template_type
    project.report_scope = data.report_scope
    # 合并类型仅在合并报表项目下有意义；单户报表清空避免误导
    project.consolidation_type = (
        data.consolidation_type if data.report_scope == "consolidated" else None
    )
    project.parent_company_name = data.parent_company_name
    project.parent_company_code = data.parent_company_code
    project.ultimate_company_name = data.ultimate_company_name
    project.ultimate_company_code = data.ultimate_company_code


def _validate_custom_template_messages(step_data: dict | None) -> list[ValidationMessage]:
    data = step_data or {}
    if data.get("template_type") != "custom":
        return []

    template_service = NoteTemplateService()
    if template_service.get_locked_template_snapshot(data) is not None:
        return []

    template_id = data.get("custom_template_id")
    if not template_id:
        return [
            ValidationMessage(
                field="custom_template_id",
                message="选择自定义附注模板时必须提供模板标识",
                severity="error",
            )
        ]

    template = template_service.get_template(str(template_id))
    if template is None:
        return [
            ValidationMessage(
                field="custom_template_id",
                message="所选自定义附注模板不存在或已失效，请重新选择",
                severity="error",
            )
        ]
    return []


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


async def _backfill_locked_custom_template_snapshot(project: Project, db: AsyncSession) -> bool:
    template_service = NoteTemplateService()
    wizard_state, _, changed = template_service.backfill_locked_template_snapshot(project.wizard_state)
    if not changed:
        return False

    project.wizard_state = wizard_state
    await db.commit()
    await db.refresh(project)
    return True


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


async def create_project(
    data: BasicInfoSchema, db: AsyncSession, *, auto_commit: bool = True
) -> Project:
    """创建项目记录，状态=created，初始化 wizard_state JSONB。

    Validates: Requirements 1.2, 1.3
    校验链：short_name 非空 → company_code 非空 → USCC 格式 → 唯一性

    Args:
        data: 基本信息 Schema
        db: 数据库会话
        auto_commit: 是否自动 commit。批量导入传 False 由调用方统一 commit。
    """
    # --- 校验链 ---
    # 1. short_name 非空
    short_name = (data.short_name or "").strip() if data.short_name else ""
    if not short_name:
        raise HTTPException(status_code=422, detail="项目简称为必填项")

    # 2. company_code 非空
    company_code = (data.company_code or "").strip() if data.company_code else ""
    if not company_code:
        raise HTTPException(status_code=422, detail="企业代码为必填项")

    # 3. USCC 格式校验
    uscc_valid, uscc_error = validate_uscc(company_code)
    if not uscc_valid:
        raise HTTPException(status_code=422, detail=uscc_error)

    # 4. 唯一性校验
    audit_year = data.audit_year
    report_scope = data.report_scope or DEFAULT_REPORT_SCOPE
    is_unique, uniqueness_error = await check_uniqueness(
        company_code, audit_year, report_scope, db
    )
    if not is_unique:
        raise HTTPException(status_code=409, detail=uniqueness_error)

    # --- 创建项目 ---
    data, custom_template_snapshot = _normalize_basic_info(data)
    project = Project(status=ProjectStatus.created)
    _sync_basic_info_to_project(project, data)
    db.add(project)
    await db.flush()  # 获取 project.id

    # 初始化 wizard_state，并将 basic_info 步骤数据写入
    basic_info_data = data.model_dump(mode="json")
    if custom_template_snapshot is not None:
        basic_info_data["custom_template_snapshot"] = custom_template_snapshot
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

    if auto_commit:
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
    await _backfill_locked_custom_template_snapshot(project, db)
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

    # basic_info 允许在 created / planning 状态下编辑（从项目详情页"编辑"进入）
    allowed_statuses = (
        {ProjectStatus.created, ProjectStatus.planning}
        if step == WizardStep.basic_info
        else {ProjectStatus.created}
    )
    if project.status not in allowed_statuses:
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
    step_data = data
    if step == WizardStep.basic_info:
        existing_basic_info = state.steps.get(WizardStep.basic_info.value)
        basic_info, custom_template_snapshot = _normalize_basic_info(
            BasicInfoSchema.model_validate(data),
            existing_basic_info.data if existing_basic_info is not None else None,
        )
        step_data = basic_info.model_dump(mode="json")
        if custom_template_snapshot is not None:
            step_data["custom_template_snapshot"] = custom_template_snapshot
        _sync_basic_info_to_project(project, basic_info)

    state.steps[step.value] = WizardStepData(
        step=step,
        data=step_data,
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
            messages.extend(_validate_custom_template_messages(step_data.data))

    elif step == WizardStep.confirmation:
        basic_info_step = state.steps.get(WizardStep.basic_info.value)
        if basic_info_step is not None:
            messages.extend(_validate_custom_template_messages(basic_info_step.data))

    return ValidationResult(valid=len(messages) == 0, messages=messages)


# ---------------------------------------------------------------------------
# confirm_project
# ---------------------------------------------------------------------------


async def confirm_project(
    project_id: UUID,
    db: AsyncSession,
    changed_by: UUID | None = None,
) -> Project:
    """确认创建，状态 created → planning。

    确认后从向导状态派生结构化"适用准则"并写入统一准则源
    （applicable_standard_v2），同时发出 STANDARD_CHANGED 事件。
    准则派生失败不影响向导确认本身（次要关注点，须保持向导确认稳健）。

    Validates: Requirements 1.7, 1.2
    """
    project = await _get_project_or_404(db, project_id)

    if project.status != ProjectStatus.created:
        raise HTTPException(
            status_code=400,
            detail=f"项目状态为 {project.status.value}，无法确认（仅 created 状态可确认；planning 项目已确认无需重复）",
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

    # 向导确认后派生并写入统一准则源（需求 1.2）。
    # 局部导入避免模块加载期的循环依赖（StandardUnificationService
    # 依赖 event_bus / models）。准则派生失败不阻断向导确认。
    try:
        from app.services.standard_unification_service import (
            StandardUnificationService,
        )

        svc = StandardUnificationService(db)
        derived = svc.derive_from_wizard(project.wizard_state)
        await svc.set_standard(
            project.id,
            derived,
            changed_by=changed_by or project.manager_id or project.id,
        )
        # set_standard 只 flush 不 commit，由调用方统一提交事务
        await db.commit()
        await db.refresh(project)
    except Exception:  # noqa: BLE001 — 派生为次要关注点，不应使向导确认失败
        logger.warning(
            "确认项目 %s 后派生统一准则源失败（向导确认本身已成功）",
            project_id,
            exc_info=True,
        )

    return project
