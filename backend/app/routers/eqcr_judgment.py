"""EQCR 结构化判断 API — Phase 7 F1

提供 5 维度结构化判断的提交和查询功能。
- POST: 提交判断（需 eqcr 角色）
- GET: 获取当前判断（只读）

双写策略：snapshot_data.judgments + 独立 judgments 列。
任一维度 conclusion='fail' → can_sign=False 阻断签字。

Validates: Requirements F1.1, F1.2, F1.3, F1.4, F1.5, F1.6
"""

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/projects/{project_id}/eqcr-judgment",
    tags=["eqcr-judgment"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

DIMENSION_KEYS = [
    "material_misstatement",
    "going_concern",
    "key_audit_matters",
    "other_information",
    "audit_report",
]

CONCLUSION_VALUES = ["pass", "qualified", "fail"]
RISK_LEVELS = ["high", "medium", "low"]


class JudgmentDimension(BaseModel):
    key: Literal[
        "material_misstatement",
        "going_concern",
        "key_audit_matters",
        "other_information",
        "audit_report",
    ]
    conclusion: Literal["pass", "qualified", "fail"]
    rationale: str = ""
    referenced_wps: list[str] = []
    risk_level: Literal["high", "medium", "low"] = "medium"


class EqcrJudgmentSubmit(BaseModel):
    dimensions: list[JudgmentDimension]

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, v: list[JudgmentDimension]) -> list[JudgmentDimension]:
        if len(v) != 5:
            raise ValueError("必须提交 5 个维度的判断")
        keys = [d.key for d in v]
        for k in DIMENSION_KEYS:
            if k not in keys:
                raise ValueError(f"缺少维度: {k}")
        if len(set(keys)) != 5:
            raise ValueError("维度 key 不能重复")
        return v


class EqcrJudgmentResponse(BaseModel):
    id: str
    project_id: str
    dimensions: list[dict]
    submitted_at: str
    submitted_by: str
    can_sign: bool


# ---------------------------------------------------------------------------
# Helper: check EQCR role
# ---------------------------------------------------------------------------


async def _check_eqcr_role(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> None:
    """验证用户在该项目具有 eqcr 角色。"""
    # admin 跳过
    if user.role.value == "admin":
        return

    from app.models.staff_models import ProjectAssignment, StaffMember

    from sqlalchemy import select

    result = await db.execute(
        select(ProjectAssignment.role)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == project_id,
            StaffMember.user_id == user.id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
    )
    role = result.scalar_one_or_none()
    if role != "eqcr":
        raise HTTPException(status_code=403, detail="仅 EQCR 角色可提交判断")


# ---------------------------------------------------------------------------
# POST /api/projects/{project_id}/eqcr-judgment
# ---------------------------------------------------------------------------


@router.post("", response_model=EqcrJudgmentResponse)
async def submit_judgment(
    project_id: uuid.UUID,
    body: EqcrJudgmentSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EqcrJudgmentResponse:
    """提交 EQCR 5 维度结构化判断。"""
    await _check_eqcr_role(project_id, current_user, db)

    # Validate all dimensions have conclusion filled
    for dim in body.dimensions:
        if not dim.conclusion:
            raise HTTPException(
                status_code=422,
                detail=f"维度 {dim.key} 缺少结论",
            )

    # Determine can_sign
    can_sign = all(d.conclusion != "fail" for d in body.dimensions)

    now = datetime.utcnow()
    judgments_data = {
        "dimensions": [d.model_dump() for d in body.dimensions],
        "submitted_at": now.isoformat(),
        "submitted_by": str(current_user.id),
        "can_sign": can_sign,
    }

    # Get current snapshot for this project
    result = await db.execute(
        sql_text(
            "SELECT id, snapshot_data FROM eqcr_snapshots "
            "WHERE project_id = :pid AND is_current = TRUE "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="当前项目暂无 EQCR 快照，请先创建快照",
        )

    snapshot_id = row[0]
    snapshot_data = row[1] if row[1] else {}

    # Dual write: update snapshot_data.judgments + independent judgments column
    if isinstance(snapshot_data, str):
        snapshot_data = json.loads(snapshot_data)

    snapshot_data["judgments"] = judgments_data

    await db.execute(
        sql_text(
            "UPDATE eqcr_snapshots "
            "SET snapshot_data = :data::jsonb, judgments = :judgments::jsonb "
            "WHERE id = :sid"
        ),
        {
            "sid": str(snapshot_id),
            "data": json.dumps(snapshot_data, ensure_ascii=False),
            "judgments": json.dumps(judgments_data, ensure_ascii=False),
        },
    )

    # Write to app_audit_log
    try:
        await db.execute(
            sql_text(
                "INSERT INTO app_audit_log (id, user_id, action, resource_type, resource_id, details, created_at) "
                "VALUES (:id, :uid, :action, :rtype, :rid, :details::jsonb, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": str(current_user.id),
                "action": "eqcr_judgment_submit",
                "rtype": "eqcr_snapshot",
                "rid": str(snapshot_id),
                "details": json.dumps(
                    {"project_id": str(project_id), "can_sign": can_sign},
                    ensure_ascii=False,
                ),
                "now": now,
            },
        )
    except Exception:
        pass  # audit_log write failure should not block main operation

    await db.commit()

    return EqcrJudgmentResponse(
        id=str(snapshot_id),
        project_id=str(project_id),
        dimensions=[d.model_dump() for d in body.dimensions],
        submitted_at=now.isoformat(),
        submitted_by=str(current_user.id),
        can_sign=can_sign,
    )


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/eqcr-judgment
# ---------------------------------------------------------------------------


@router.get("")
async def get_judgment(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """获取当前 EQCR 判断（只读）。"""
    result = await db.execute(
        sql_text(
            "SELECT id, judgments FROM eqcr_snapshots "
            "WHERE project_id = :pid AND is_current = TRUE "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    row = result.first()

    if row is None:
        return {"judgment": None}

    judgments = row[1]
    if judgments is None:
        return {"judgment": None}

    if isinstance(judgments, str):
        judgments = json.loads(judgments)

    return {
        "judgment": {
            "id": str(row[0]),
            "project_id": str(project_id),
            "dimensions": judgments.get("dimensions", []),
            "submitted_at": judgments.get("submitted_at"),
            "submitted_by": judgments.get("submitted_by"),
            "can_sign": judgments.get("can_sign", True),
        }
    }
