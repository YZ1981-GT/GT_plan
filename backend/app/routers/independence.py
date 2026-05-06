"""独立性声明 API — Refinement Round 1 需求 10

端点：
  GET  /api/projects/{project_id}/independence-declarations
  POST /api/projects/{project_id}/independence-declarations
  PATCH /api/projects/{project_id}/independence-declarations/{declaration_id}
  POST /api/projects/{project_id}/independence-declarations/{declaration_id}/submit
  GET  /api/independence/questions
  GET  /api/my/pending-independence  (R1 Bug Fix 7: 批量查询待声明项目)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, Project
from app.models.staff_models import ProjectAssignment
from app.models.independence_models import IndependenceDeclaration
from app.services.independence_service import IndependenceService

router = APIRouter(tags=["独立性声明"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class CreateDeclarationRequest(BaseModel):
    """创建独立性声明请求"""
    declarant_id: UUID
    declaration_year: int = Field(..., ge=2000, le=2100)


class UpdateDeclarationRequest(BaseModel):
    """更新独立性声明请求"""
    answers: dict | None = None
    attachments: list[dict] | None = None


# ------------------------------------------------------------------
# 问题模板端点
# ------------------------------------------------------------------


@router.get("/api/independence/questions")
async def get_independence_questions(
    current_user: User = Depends(get_current_user),
):
    """返回独立性问题模板（20 条）。"""
    questions = IndependenceService.get_questions()
    return {"questions": questions, "total": len(questions)}


# ------------------------------------------------------------------
# 项目级声明端点
# ------------------------------------------------------------------


@router.get("/api/projects/{project_id}/independence-declarations")
async def list_declarations(
    project_id: UUID,
    year: int | None = Query(default=None, description="按年份筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出项目的独立性声明。"""
    declarations = await IndependenceService.list_declarations(db, project_id, year)
    return {
        "declarations": [
            IndependenceService.declaration_to_dict(d) for d in declarations
        ],
        "total": len(declarations),
    }


@router.post("/api/projects/{project_id}/independence-declarations", status_code=201)
async def create_declaration(
    project_id: UUID,
    body: CreateDeclarationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一份 draft 状态的独立性声明。"""
    decl = await IndependenceService.create_declaration(
        db=db,
        project_id=project_id,
        declarant_id=body.declarant_id,
        year=body.declaration_year,
    )
    await db.commit()
    return IndependenceService.declaration_to_dict(decl)


@router.patch("/api/projects/{project_id}/independence-declarations/{declaration_id}")
async def update_declaration(
    project_id: UUID,
    declaration_id: UUID,
    body: UpdateDeclarationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 draft 状态的声明（answers / attachments）。"""
    try:
        decl = await IndependenceService.update_declaration(
            db=db,
            declaration_id=declaration_id,
            answers=body.answers,
            attachments=body.attachments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if decl is None:
        raise HTTPException(status_code=404, detail="声明不存在")
    await db.commit()
    return IndependenceService.declaration_to_dict(decl)


@router.post("/api/projects/{project_id}/independence-declarations/{declaration_id}/submit")
async def submit_declaration(
    project_id: UUID,
    declaration_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交声明：draft → submitted，触发 SignatureRecord + 审计日志。"""
    try:
        decl = await IndependenceService.submit_declaration(
            db=db,
            declaration_id=declaration_id,
            signer_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return IndependenceService.declaration_to_dict(decl)



# ------------------------------------------------------------------
# R1 Bug Fix 7: 批量查询当前用户待声明项目（避免 N+1 HTTP）
# ------------------------------------------------------------------


@router.get("/api/my/pending-independence")
async def get_my_pending_independence(
    limit: int = Query(50, ge=1, le=500, description="返回条数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前用户尚未提交独立性声明的项目列表。

    查询逻辑：
    1. 找到当前用户被分配为核心角色（signing_partner/manager/qc/eqcr）的活跃项目
    2. 排除已归档项目（archived_at IS NOT NULL）
    3. 排除当前年度已有 submitted/approved 声明的项目

    R1 Bug Fix 7: 替代前端 N+1 循环调用。
    Batch 2-10: 新增 limit 参数（默认 50，上限 500）+ has_more 字段。
    """
    year = datetime.now(timezone.utc).year
    user_id = current_user.id

    # 核心角色
    core_roles = ["signing_partner", "manager", "qc", "eqcr"]

    # 1) 查询用户被分配为核心角色的活跃项目
    assigned_stmt = (
        select(Project)
        .join(ProjectAssignment, ProjectAssignment.project_id == Project.id)
        .where(
            and_(
                ProjectAssignment.staff_id == user_id,
                ProjectAssignment.role.in_(core_roles),
                ProjectAssignment.is_deleted == False,  # noqa: E712
                Project.is_deleted == False,  # noqa: E712
                Project.archived_at.is_(None),
            )
        )
        .distinct()
    )
    result = await db.execute(assigned_stmt)
    projects = result.scalars().all()

    if not projects:
        return {"projects": [], "total": 0, "has_more": False}

    project_ids = [p.id for p in projects]

    # 2) 查询当前年度已完成声明的项目 ID
    completed_stmt = (
        select(IndependenceDeclaration.project_id)
        .where(
            and_(
                IndependenceDeclaration.declarant_id == user_id,
                IndependenceDeclaration.project_id.in_(project_ids),
                IndependenceDeclaration.declaration_year == year,
                IndependenceDeclaration.status.in_(["submitted", "approved"]),
            )
        )
        .distinct()
    )
    completed_result = await db.execute(completed_stmt)
    completed_project_ids = {row[0] for row in completed_result.all()}

    # 3) 过滤出未完成的项目
    pending_all = [
        {
            "id": str(p.id),
            "name": p.name,
            "client_name": getattr(p, "client_name", None),
            "status": p.status.value if hasattr(p.status, "value") else str(p.status) if p.status else None,
        }
        for p in projects
        if p.id not in completed_project_ids
    ]

    total = len(pending_all)
    pending = pending_all[:limit]

    return {
        "projects": pending,
        "total": total,
        "has_more": total > limit,
    }
