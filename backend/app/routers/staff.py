"""人员库 API 路由

Phase 9 Task 1.2
"""

from __future__ import annotations

import uuid
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.staff_schemas import (
    StaffCreate,
    StaffListResponse,
    StaffResponse,
    StaffResumeResponse,
    StaffUpdate,
)
from app.services.staff_service import StaffService

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("", response_model=StaffListResponse)
async def list_staff(
    search: str | None = Query(None),
    department: str | None = Query(None),
    partner_name: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    items, total = await svc.list_staff(search, department, partner_name, offset, limit)
    return StaffListResponse(
        items=[StaffResponse.model_validate(s) for s in items],
        total=total,
    )


@router.post("", response_model=StaffResponse)
async def create_staff(
    data: StaffCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.create_staff(data.model_dump(exclude_none=True))
    await db.commit()
    return StaffResponse.model_validate(staff)


@router.put("/{staff_id}", response_model=StaffResponse)
async def update_staff(
    staff_id: UUID,
    data: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.update_staff(staff_id, data.model_dump(exclude_none=True))
    if not staff:
        raise HTTPException(404, "人员不存在")
    await db.commit()
    return StaffResponse.model_validate(staff)


@router.get("/{staff_id}/resume")
async def get_resume(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    staff = await svc.get_staff(staff_id)
    if not staff:
        raise HTTPException(404, "人员不存在")
    resume = await svc.get_resume(staff_id)
    return {
        "staff_id": str(staff_id),
        "name": staff.name,
        "title": staff.title,
        "department": staff.department,
        **resume,
    }


@router.get("/{staff_id}/projects")
async def get_projects(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = StaffService(db)
    return await svc.get_projects(staff_id)


@router.delete("/{staff_id}")
async def delete_staff(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除人员（仅允许删除 source=custom 的自定义人员）"""
    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(StaffMember).where(StaffMember.id == staff_id, StaffMember.is_deleted == False)
    )
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="人员不存在")

    source = getattr(staff, "source", "custom")
    if source == "seed":
        raise HTTPException(status_code=400, detail="初始导入的人员不允许删除")

    staff.is_deleted = True
    await db.commit()
    return {"message": "已删除", "id": str(staff_id)}


@router.get("/me/staff-id")
async def get_my_staff_id(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取当前登录用户关联的 staff_member ID"""
    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    result = await db.execute(
        sa.select(StaffMember).where(
            StaffMember.user_id == user.id,
            StaffMember.is_deleted == False,
        )
    )
    staff = result.scalar_one_or_none()
    if staff:
        return {"staff_id": str(staff.id), "name": staff.name}

    # 如果没有关联，尝试按用户名匹配
    result = await db.execute(
        sa.select(StaffMember).where(
            StaffMember.name == user.username,
            StaffMember.is_deleted == False,
        )
    )
    staff = result.scalar_one_or_none()
    if staff:
        # 自动关联
        staff.user_id = user.id
        await db.commit()
        return {"staff_id": str(staff.id), "name": staff.name}

    # 都没找到，自动创建一条 custom 记录
    from app.models.staff_models import StaffMember as SM
    import uuid
    new_staff = SM(
        id=uuid.uuid4(),
        user_id=user.id,
        name=user.username,
        source="custom",
    )
    db.add(new_staff)
    await db.commit()
    return {"staff_id": str(new_staff.id), "name": new_staff.name, "auto_created": True}


@router.post("/import-excel")
async def import_staff_from_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从Excel批量导入人员

    Excel格式：姓名/部门/职级/所属合伙人（第一行为表头）
    """
    import openpyxl
    import io

    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx/.xls 文件")

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"文件解析失败: {e}")

    ws = wb.active
    imported = 0
    skipped = 0

    # 跳过表头行
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    from app.models.staff_models import StaffMember
    import sqlalchemy as sa

    for row in rows:
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if not name:
            continue

        # 检查是否已存在
        existing = await db.execute(
            sa.select(StaffMember).where(StaffMember.name == name, StaffMember.is_deleted == sa.false())
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        department = str(row[1]).strip() if len(row) > 1 and row[1] else None
        title = str(row[2]).strip() if len(row) > 2 and row[2] else None
        partner_name = str(row[3]).strip() if len(row) > 3 and row[3] else None

        staff = StaffMember(
            id=uuid.uuid4(),
            name=name,
            department=department,
            title=title,
            partner_name=partner_name,
            source="custom",
        )
        db.add(staff)
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "total_rows": len(rows)}


# ═══ 人员交接（Round 2 需求 10） ═══


class HandoverRequest(BaseModel):
    """交接请求体"""
    scope: str = Field(..., pattern="^(all|by_project)$", description="交接范围")
    project_ids: list[UUID] | None = Field(None, description="scope=by_project 时指定项目")
    target_staff_id: UUID = Field(..., description="接收人 ID")
    reason_code: str = Field(
        ...,
        pattern="^(resignation|long_leave|rotation|other)$",
        description="原因码",
    )
    reason_detail: str | None = Field(None, description="原因详情")
    effective_date: date = Field(..., description="生效日期")


class HandoverPreviewResponse(BaseModel):
    """交接预览响应"""
    workpapers: int
    issues: int
    assignments: int


class HandoverResponse(BaseModel):
    """交接执行响应"""
    handover_record_id: str
    workpapers_moved: int
    issues_moved: int
    assignments_moved: int
    independence_superseded: int


@router.post("/{staff_id}/handover", response_model=HandoverResponse)
async def execute_handover(
    staff_id: UUID,
    body: HandoverRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "partner", "manager"])),
):
    """执行人员交接 — 批量转移底稿/工单/项目委派。

    - scope='all': 转移该人员名下所有项目的工作
    - scope='by_project': 仅转移指定项目的工作
    - reason_code='resignation' 时自动标记独立性声明为 superseded_by_handover

    权限（Batch 1 P0.2）：
    - admin / partner：可交接任意人员
    - manager：只能交接自己项目（manager/signing_partner）内的人员
    - 其他角色：403
    """
    from app.services.handover_service import HandoverService
    from app.services.manager_dashboard_service import ManagerDashboardService

    if staff_id == body.target_staff_id:
        raise HTTPException(
            status_code=400,
            detail="交接人和接收人不能是同一人",
        )

    # Batch 1 Fix 2.4: effective_date 合理范围校验
    from datetime import timedelta
    today = date.today()
    if body.effective_date < today - timedelta(days=30):
        raise HTTPException(status_code=400, detail="生效日期不能早于 30 天前")
    if body.effective_date > today + timedelta(days=30):
        raise HTTPException(status_code=400, detail="生效日期不能晚于 30 天后")

    # manager 级权限：限制 by_project 范围在自己的项目里
    if user.role.value == "manager":
        if body.scope != "by_project" or not body.project_ids:
            raise HTTPException(
                status_code=403,
                detail="项目经理只能进行 by_project 范围的交接，且必须指定 project_ids",
            )
        # 查询当前 manager 可见项目
        mgr_svc = ManagerDashboardService(db)
        allowed_project_ids = set(await mgr_svc._get_manager_project_ids(user))
        requested_ids = set(body.project_ids)
        if not requested_ids.issubset(allowed_project_ids):
            raise HTTPException(
                status_code=403,
                detail="项目经理只能交接自己管理的项目",
            )

    service = HandoverService(db)

    try:
        result = await service.execute(
            from_staff_id=staff_id,
            to_staff_id=body.target_staff_id,
            scope=body.scope,
            project_ids=body.project_ids,
            reason_code=body.reason_code,
            reason_detail=body.reason_detail,
            effective_date=body.effective_date,
            executed_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return HandoverResponse(**result)


@router.get("/{staff_id}/handover/preview", response_model=HandoverPreviewResponse)
async def preview_handover(
    staff_id: UUID,
    scope: str = Query(..., pattern="^(all|by_project)$"),
    project_ids: str | None = Query(None, description="逗号分隔的项目 ID"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "partner", "manager"])),
):
    """预览交接将影响的数据量（不执行实际变更）。

    权限（Batch 1 P0.2）：同 execute_handover，仅 admin/partner/manager 可访问。
    manager 对 scope='all' 的预览返回 403（避免泄露跨项目信息）。
    """
    from app.services.handover_service import HandoverService
    from app.services.manager_dashboard_service import ManagerDashboardService

    parsed_project_ids: list[UUID] | None = None
    if project_ids:
        try:
            parsed_project_ids = [UUID(pid.strip()) for pid in project_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="project_ids 格式错误")

    # manager 不能查看全局预览（避免信息泄露）
    if user.role.value == "manager":
        if scope != "by_project" or not parsed_project_ids:
            raise HTTPException(
                status_code=403,
                detail="项目经理只能预览 by_project 范围，且必须指定 project_ids",
            )
        mgr_svc = ManagerDashboardService(db)
        allowed_project_ids = set(await mgr_svc._get_manager_project_ids(user))
        if not set(parsed_project_ids).issubset(allowed_project_ids):
            raise HTTPException(
                status_code=403,
                detail="项目经理只能预览自己管理的项目",
            )

    service = HandoverService(db)
    preview = await service.get_handover_preview(
        from_staff_id=staff_id,
        scope=scope,
        project_ids=parsed_project_ids,
    )
    return HandoverPreviewResponse(**preview)
