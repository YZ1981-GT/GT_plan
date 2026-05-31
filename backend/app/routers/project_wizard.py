"""项目初始化向导 API 路由

Validates: Requirements 1.1-1.8
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
    return ProjectCreateResponse(
        id=project.id,
        name=project.name,
        client_name=project.client_name,
        audit_year=_extract_project_audit_year(project),
        project_type=project.project_type.value if project.project_type else None,
        status=project.status.value,
        template_type=project.template_type,
        report_scope=project.report_scope,
        parent_project_id=project.parent_project_id,
        consol_level=project.consol_level or 1,
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
      - partner_name / manager_name = JOIN users.display_name

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

    # 3. 一次性取 partner/manager display_name
    user_ids = {p.partner_id for p in projects if p.partner_id} | {p.manager_id for p in projects if p.manager_id}
    name_map: dict = {}
    if user_ids:
        from app.models.core import User as UserModel
        user_rows = (await db.execute(
            select(UserModel.id, UserModel.display_name, UserModel.username).where(UserModel.id.in_(list(user_ids)))
        )).all()
        for uid, dname, uname in user_rows:
            name_map[uid] = dname or uname

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


@router.get("/{project_id}/wizard", response_model=WizardState)
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
    _token: None = Depends(require_confirmation_token),
):
    """软删除单个项目（需二次密码确认）"""
    from sqlalchemy import select
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")
    project.is_deleted = True
    await db.commit()
    return {"id": str(project_id), "deleted": True}


@router.post("/batch-delete")
async def batch_delete_projects(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _token: None = Depends(require_confirmation_token),
):
    """批量软删除项目（需二次密码确认）"""
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
