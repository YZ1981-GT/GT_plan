"""S2 ADR-CCN-06: 门禁逐项确认留痕 — router 层

端点:
- GET  /api/projects/{project_id}/consistency-gate/acknowledgements  列表
- POST /api/projects/{project_id}/consistency-gate/acknowledgements  确认
- POST /api/projects/{project_id}/consistency-gate/acknowledgements/{ack_id}/revoke  撤销

权限 D1:
- comparison-fail 类确认仅签字合伙人可操作（由后端根据 check_name + status 派生，不信任客户端）
- data-missing / check-exception 类需 edit 级
- 列表需 review 级
- observe 模式下 POST 确认返回 409
"""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.phase14_enums import GateSeverity
from app.services import gate_acknowledgement_service as ack_svc
from app.services.gate_acknowledgement_service import compute_result_fingerprint

router = APIRouter()

# ── 比较不通过类规则（需签字合伙人确认） ──────────────────────
_COMPARISON_FAIL_RULES: frozenset[str] = frozenset({"R4-CROSS-CHECK"})


def _classify_check(check_name: str, status: str) -> str:
    """根据规则编码和检查状态派生确认类别（不信任客户端）。

    - comparison-fail: 数值比较未通过，需签字合伙人
    - data-missing: 数据不足 / 规则未执行
    - check-exception: 其他异常
    """
    if check_name in _COMPARISON_FAIL_RULES and status == "failed":
        return "comparison-fail"
    if status in ("not_executed", "not_applicable"):
        return "data-missing"
    return "check-exception"


class AcknowledgementCreateBody(BaseModel):
    """确认请求体"""
    year: int
    check_name: str
    branch_id: str = ""
    status: str
    key_numbers: dict[str, float | None] = {}
    reason: str = Field(..., min_length=10, description="确认原因，至少 10 字符")
    # 以下字段保留用于向后兼容，后端忽略客户端传值
    result_fingerprint: str = ""  # 由后端根据 key_numbers 计算
    check_class: str = "data-missing"  # 由后端根据 check_name + status 派生


@router.get("/api/projects/{project_id}/consistency-gate/acknowledgements")
async def list_acknowledgements(
    project_id: uuid.UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("review")),
) -> list[dict]:
    """列出项目 + 年度的全部确认记录"""
    return await ack_svc.list_acknowledgements(db, project_id, year)


@router.post("/api/projects/{project_id}/consistency-gate/acknowledgements")
async def create_acknowledgement(
    project_id: uuid.UUID,
    body: AcknowledgementCreateBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
) -> dict:
    """新建确认

    observe 模式下返回 409；comparison-fail 类仅 partner 可操作。
    """
    # observe 模式 → 409
    enforcement = os.environ.get("CONSISTENCY_GATE_ENFORCEMENT", "observe")
    if enforcement != "enforce":
        raise HTTPException(409, "当前为只提示模式，无需确认")

    # 后端计算指纹（不信任客户端传值）——与 gate_engine._compute_fingerprint_for_hit 同口径
    result_fingerprint = compute_result_fingerprint(
        check_name=body.check_name,
        branch_id=body.branch_id,
        status=GateSeverity.blocking,  # 确认仅在 enforce 模式下创建，severity 恒为 blocking
        key_numbers=body.key_numbers,
    )

    # D1 权限分级：由后端根据 (check_name, status) 派生类别，不信任客户端 check_class
    check_class = _classify_check(body.check_name, body.status)
    if check_class == "comparison-fail":
        user_role = getattr(user, "role", None) or getattr(user, "system_role", None) or ""
        if str(user_role) != "partner":
            raise HTTPException(403, "比较不通过类确认仅签字合伙人可操作")

    user_role_str = str(getattr(user, "role", None) or getattr(user, "system_role", None) or "")
    try:
        result = await ack_svc.acknowledge(
            db=db,
            project_id=project_id,
            year=body.year,
            check_name=body.check_name,
            branch_id=body.branch_id,
            status=body.status,
            result_fingerprint=result_fingerprint,
            reason=body.reason,
            user_id=user.id,
            user_role=user_role_str,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    await db.commit()
    return result


@router.post(
    "/api/projects/{project_id}/consistency-gate/acknowledgements/{ack_id}/revoke"
)
async def revoke_acknowledgement(
    project_id: uuid.UUID,
    ack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
) -> dict:
    """撤销确认"""
    try:
        result = await ack_svc.revoke(db, ack_id, user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))

    await db.commit()
    return result
