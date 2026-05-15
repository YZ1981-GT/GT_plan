"""EQCR 充分性评价端点 — POST /eqcr-evaluation

Sprint 11 Task 11.3
评价结果：充分/需补充/重大疑虑
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/projects/{project_id}/eqcr-evaluation", tags=["eqcr-evaluation"])


class EqcrVerdict(str, Enum):
    sufficient = "sufficient"
    needs_supplement = "needs_supplement"
    major_concern = "major_concern"


class EqcrEvaluationCreate(BaseModel):
    wp_id: uuid.UUID
    verdict: EqcrVerdict
    comment: Optional[str] = None


class EqcrEvaluationOut(BaseModel):
    id: str
    wp_id: str
    verdict: str
    comment: Optional[str] = None
    evaluator_id: str
    evaluated_at: str


@router.post("", response_model=EqcrEvaluationOut, status_code=201)
async def create_eqcr_evaluation(
    project_id: uuid.UUID,
    body: EqcrEvaluationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建 EQCR 充分性评价"""
    evaluation_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Store as audit log entry for traceability
    from app.services.audit_logger_enhanced import audit_logger
    await audit_logger.log_action(
        user_id=current_user.id,
        action="eqcr_evaluation_created",
        object_type="workpaper",
        object_id=body.wp_id,
        project_id=project_id,
        details={
            "verdict": body.verdict.value,
            "comment": body.comment,
        },
    )

    return EqcrEvaluationOut(
        id=str(evaluation_id),
        wp_id=str(body.wp_id),
        verdict=body.verdict.value,
        comment=body.comment,
        evaluator_id=str(current_user.id),
        evaluated_at=now.isoformat(),
    )


@router.get("")
async def list_eqcr_evaluations(
    project_id: uuid.UUID,
    wp_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询 EQCR 评价列表"""
    # Stub: 实际实现从 audit_log_entries 或专用表查询
    return {"evaluations": []}
