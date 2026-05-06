"""EQCR 年度独立性声明端点"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from .schemas import AnnualDeclarationSubmitRequest

router = APIRouter()


@router.get("/independence/annual/check")
async def check_annual_declaration(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查当前用户是否已提交本年度独立性声明（需求 12）。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    has_declaration = await svc.check_annual_declaration(current_user.id)
    return {
        "has_declaration": has_declaration,
        "year": datetime.now(timezone.utc).year,
    }


@router.get("/independence/annual/questions")
async def get_annual_questions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取年度独立性声明问题集（需求 12）。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    questions = svc.get_annual_questions()
    return {"questions": questions, "total": len(questions)}


@router.post("/independence/annual/submit")
async def submit_annual_declaration(
    payload: AnnualDeclarationSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交年度独立性声明（需求 12）。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    try:
        result = await svc.submit_annual_declaration(
            current_user.id,
            payload.year,
            payload.answers,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
