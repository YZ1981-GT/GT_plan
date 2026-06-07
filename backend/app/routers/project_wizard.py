"""项目初始化向导 API 路由

Validates: Requirements 1.1-1.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.routers.password_confirm import require_confirmation_token
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    ProjectCreateResponse,
    ValidationResult,
    WizardState,
    WizardStep,
)
from app.models.core import Project, User
from app.services import project_wizard_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _extract_project_audit_year(project: Project) -> int | None:
    """提取项目审计年度，兜底优先级（防止 wizard_state 未填齐导致 null）：

    1. wizard_state.steps.basic_info.data.audit_year (主要来源，向导走完时填)
    2. project.audit_period_start.year（创建时填的审计期间起）
    3. project.name 末尾的 _YYYY 后缀（命名约定 `{客户}_{年度}`）
    返回值始终 > 2000。
    """
    wizard_state = project.wizard_state or {}
    basic_info = (
        wizard_state.get("steps", {}).get("basic_info", {}).get("data")
        or wizard_state.get("basic_info", {}).get("data")
        or {}
    )
    raw_year = basic_info.get("audit_year") or basic_info.get("year")
    if raw_year:
        try:
            audit_year = int(raw_year)
            if audit_year > 2000:
                return audit_year
        except (TypeError, ValueError):
            pass

    # 兜底 1：审计期间起始年
    if project.audit_period_start:
        try:
            y = project.audit_period_start.year
            if y > 2000:
                return y
        except (AttributeError, TypeError):
            pass

    # 兜底 2：项目名末尾 _YYYY 后缀
    if project.name:
        import re
        m = re.search(r'_(\d{4})$', project.name)
        if m:
            try:
                y = int(m.group(1))
                if y > 2000:
                    return y
            except ValueError:
                pass

    return None


def _to_project_response(project: Project) -> ProjectCreateResponse:
    # 优先使用物化列 audit_year（Task 4.3），缺失时回退提取逻辑
    audit_year = project.audit_year or _extract_project_audit_year(project)
    return ProjectCreateResponse(
        id=project.id,
        name=project.name,
        client_name=project.client_name,
        short_name=project.short_name,
        company_code=project.company_code,
        audit_year=audit_year,
        project_type=project.project_type.value if project.project_type else None,
        status=project.status.value,
        template_type=project.template_type,
        report_scope=project.report_scope,
        parent_project_id=project.parent_project_id,
        consol_level=project.consol_level or 1,
        consol_lock=bool(project.consol_lock),
        created_at=project.created_at,
    )


@router.get("", response_model=list[ProjectCreateResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """获取项目列表（按用户可见性过滤）

    admin/partner 可见所有项目，其他角色只能看到自己参与的项目。
    """
    from sqlalchemy import select
    from app.models.core import ProjectUser

    if current_user.role.value in ("admin", "partner"):
        # 管理员和合伙人可见所有项目
        result = await db.execute(
            select(Project).where(Project.is_deleted == False)  # noqa: E712
        )
    else:
        # 其他角色只能看到自己参与的项目
        my_project_ids = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        pids = [r[0] for r in my_project_ids.all()]
        if not pids:
            return []
        result = await db.execute(
            select(Project).where(
                Project.id.in_(pids),
                Project.is_deleted == False,  # noqa: E712
            )
        )

    projects = result.scalars().all()
    return [_to_project_response(p) for p in projects]


@router.get("/list-with-progress")
async def list_projects_with_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """仪表盘甘特视图专用：项目列表 + 进度 + 派生时间窗 + 负责人姓名。

    派生规则（避免改 Project 模型）：
      - start_date = audit_year-12-01（典型审计期开始：年报年末）
      - due_date   = (audit_year+1)-04-30（典型审计报告截止）
      - overall_progress = sum(已完成 wp count) / sum(wp count) * 100
        已完成 = WorkingPaper.status in (locked, archived)；空集时为 0
      - partner_name / manager_name = JOIN users.username

    单次 SQL 聚合（项目数 N）+ 单次 SQL 取 wp 进度（GROUP BY project_id）+ 单次 users JOIN，
    总计 3 次 IO，不会随 N 退化。
    """
    from datetime import date
    from sqlalchemy import select, func
    from app.models.core import ProjectUser
    from app.models.workpaper_models import WorkingPaper

    # 1. 项目可见性过滤
    if current_user.role.value in ("admin", "partner"):
        proj_result = await db.execute(
            select(Project).where(Project.is_deleted == False)  # noqa: E712
        )
    else:
        my_pids = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        pids = [r[0] for r in my_pids.all()]
        if not pids:
            return []
        proj_result = await db.execute(
            select(Project).where(
                Project.id.in_(pids),
                Project.is_deleted == False,  # noqa: E712
            )
        )
    projects = proj_result.scalars().all()
    if not projects:
        return []
    proj_ids = [p.id for p in projects]

    # 2. 一次性聚合 wp 进度（review_passed/archived 占比 = 完成度）
    from sqlalchemy import case
    progress_q = (
        select(
            WorkingPaper.project_id,
            func.count(WorkingPaper.id).label("total"),
            func.sum(
                case((WorkingPaper.status.in_(("review_passed", "archived")), 1), else_=0)
            ).label("done"),
        )
        .where(
            WorkingPaper.project_id.in_(proj_ids),
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .group_by(WorkingPaper.project_id)
    )
    progress_rows = (await db.execute(progress_q)).all()
    progress_map = {
        row[0]: round((int(row[2] or 0) / int(row[1])) * 100, 1) if int(row[1]) > 0 else 0.0
        for row in progress_rows
    }

    # 3. 一次性取 partner/manager 名称（users 表无 display_name 列，用 username）
    user_ids = {p.partner_id for p in projects if p.partner_id} | {p.manager_id for p in projects if p.manager_id}
    name_map: dict = {}
    if user_ids:
        from app.models.core import User as UserModel
        user_rows = (await db.execute(
            select(UserModel.id, UserModel.username).where(UserModel.id.in_(list(user_ids)))
        )).all()
        for uid, uname in user_rows:
            name_map[uid] = uname

    # 4. 组装
    out: list[dict] = []
    for p in projects:
        ay = _extract_project_audit_year(p)
        start_date_iso: str | None = None
        due_date_iso: str | None = None
        if ay:
            try:
                start_date_iso = date(ay, 12, 1).isoformat()
                due_date_iso = date(ay + 1, 4, 30).isoformat()
            except ValueError:
                pass
        out.append({
            "id": str(p.id),
            "name": p.name,
            "client_name": p.client_name,
            "audit_year": ay,
            "project_type": p.project_type.value if p.project_type else None,
            "status": p.status.value,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "start_date": start_date_iso,
            "due_date": due_date_iso,
            "overall_progress": progress_map.get(p.id, 0.0),
            "partner_name": name_map.get(p.partner_id) if p.partner_id else None,
            "manager_name": name_map.get(p.manager_id) if p.manager_id else None,
        })
    return out


@router.get("/{project_id}", response_model=ProjectCreateResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    from sqlalchemy import select
    from app.models.core import ProjectUser

    query = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    if current_user.role.value not in ("admin", "partner"):
        query = query.join(ProjectUser, ProjectUser.project_id == Project.id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _to_project_response(project)


@router.post("", response_model=ProjectCreateResponse)
async def create_project(
    data: BasicInfoSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """创建审计项目（向导步骤1-基本信息）。

    Validates: Requirements 1.2, 1.3
    """
    project = await project_wizard_service.create_project(data, db)
    return _to_project_response(project)


# ---------------------------------------------------------------------------
# Phase 3 需求 5.1: 配置合并范围 — 把已有单体项目挂为子公司（attach subsidiaries）
# ---------------------------------------------------------------------------


class AttachSubsidiariesRequest(BaseModel):
    """配置合并范围请求：把若干已有单体项目挂到本合并项目下作子公司。"""
    child_project_ids: list[UUID]


@router.get("/{project_id}/available-subsidiaries", response_model=list[ProjectCreateResponse])
async def list_available_subsidiaries(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """列出可挂为子公司的候选单体项目（需求 5.1）。

    候选 = 用户可见 + 非本项目 + report_scope != consolidated +
    （未挂到其他集团 或 已挂到本项目）。仅 consolidated 项目可调（R3：不影响非合并流程）。
    """
    from sqlalchemy import select, or_
    from app.models.core import ProjectUser

    parent = await db.get(Project, project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    query = select(Project).where(
        Project.is_deleted == False,  # noqa: E712
        Project.id != project_id,
        or_(Project.report_scope != "consolidated", Project.report_scope.is_(None)),
        or_(
            Project.parent_project_id.is_(None),
            Project.parent_project_id == project_id,
        ),
    )
    if current_user.role.value not in ("admin", "partner"):
        query = query.join(ProjectUser, ProjectUser.project_id == Project.id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    result = await db.execute(query)
    return [_to_project_response(p) for p in result.scalars().all()]


@router.post("/{project_id}/attach-subsidiaries", response_model=list[ProjectCreateResponse])
async def attach_subsidiaries(
    project_id: UUID,
    body: AttachSubsidiariesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectCreateResponse]:
    """把选中的已有单体项目挂为本合并项目的子公司（需求 5.1）。

    - 仅 consolidated 项目可调（R3：非合并项目流程不变）。
    - 设置子项目 parent_project_id = 本项目；consol_level = 母 + 1。
    - 成功后广播 CONSOL_SCOPE_CHANGED（需求 5.2）→ 前端树自动刷新。
    - 仅 admin/partner 或有写权限者可操作（沿用项目可见性，权限不足的子项目跳过）。
    """
    from sqlalchemy import select
    from app.models.core import ProjectUser

    parent = await db.get(Project, project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    # 可写项目集合（admin/partner 全可写，其他角色仅自己参与的项目）
    allowed_ids: set[UUID] | None = None
    if current_user.role.value not in ("admin", "partner"):
        mine = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        allowed_ids = {r[0] for r in mine.all()}

    attached: list[Project] = []
    for child_id in body.child_project_ids:
        if child_id == project_id:
            continue
        if allowed_ids is not None and child_id not in allowed_ids:
            continue
        child = await db.get(Project, child_id)
        if child is None or child.is_deleted:
            continue
        if child.report_scope == "consolidated":
            continue  # 不允许把合并项目挂为子公司
        child.parent_project_id = project_id
        child.consol_level = (parent.consol_level or 1) + 1
        attached.append(child)

    await db.commit()
    for c in attached:
        await db.refresh(c)

    # 需求 5.2：合并范围变更广播，前端树自动刷新（ADR-CONSOL-303）
    if attached:
        from app.services.consol_scope_service import _emit_scope_changed
        _emit_scope_changed(project_id, _extract_project_audit_year(parent))

    return [_to_project_response(c) for c in attached]
async def get_wizard_state(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
    """获取向导当前状态（支持断点续做）。

    Validates: Requirements 1.4, 1.5
    """
    return await project_wizard_service.get_wizard_state(project_id, db)


@router.put("/{project_id}/wizard/{step}", response_model=WizardState)
async def update_step(
    project_id: UUID,
    step: WizardStep,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WizardState:
    """更新指定步骤数据并持久化。

    Validates: Requirements 1.3, 1.4, 1.5
    """
    return await project_wizard_service.update_step(project_id, step, data, db)


@router.post(
    "/{project_id}/wizard/validate/{step}",
    response_model=ValidationResult,
)
async def validate_step(
    project_id: UUID,
    step: WizardStep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidationResult:
    """校验指定步骤是否满足前进条件。

    Validates: Requirements 1.8
    """
    return await project_wizard_service.validate_step(project_id, step, db)


@router.post("/{project_id}/wizard/confirm", response_model=ProjectCreateResponse)
async def confirm_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    """确认创建项目，状态 created → planning。

    Validates: Requirements 1.7
    """
    project = await project_wizard_service.confirm_project(
        project_id, db, changed_by=current_user.id
    )
    return _to_project_response(project)


# ── 删除项目 ──


from pydantic import BaseModel as _BaseModel


class BatchDeleteRequest(_BaseModel):
    project_ids: list[UUID]


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除单个项目（前端已有二次确认弹窗，仅 admin/partner/manager 可操作）"""
    from fastapi import HTTPException
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="权限不足，仅管理员/合伙人/项目经理可删除项目")
    from sqlalchemy import select
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    project.is_deleted = True
    await db.commit()
    return {"id": str(project_id), "deleted": True}


@router.post("/batch-delete")
async def batch_delete_projects(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量软删除项目（前端已有二次确认弹窗，仅 admin/partner/manager 可操作）"""
    from fastapi import HTTPException
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="权限不足，仅管理员/合伙人/项目经理可删除项目")
    from sqlalchemy import select, update
    count = 0
    for pid in body.project_ids:
        result = await db.execute(
            select(Project).where(Project.id == pid, Project.is_deleted == False)  # noqa: E712
        )
        p = result.scalar_one_or_none()
        if p:
            p.is_deleted = True
            count += 1
    await db.commit()
    return {"deleted_count": count, "requested": len(body.project_ids)}
