"""独立性声明 API — Refinement Round 1 需求 10

端点：
  GET  /api/projects/{project_id}/independence-declarations
  POST /api/projects/{project_id}/independence-declarations
  PATCH /api/projects/{project_id}/independence-declarations/{declaration_id}
  POST /api/projects/{project_id}/independence-declarations/{declaration_id}/submit
  GET  /api/independence/questions
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
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
