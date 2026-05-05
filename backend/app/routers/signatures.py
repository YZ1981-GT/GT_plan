"""电子签名 API 路由

- POST /api/signatures/sign                       — 签署文档
- GET  /api/signatures/workflow/{project_id}       — 签字工作流状态
- GET  /api/signatures/{object_type}/{object_id}   — 签名记录
- POST /api/signatures/{signature_id}/verify       — 验证签名
- POST /api/signatures/{signature_id}/revoke       — 撤销签名

Validates: Requirements 7.1-7.4, R1 需求 4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.sign_service import (
    PrerequisiteNotMetError,
    SignService,
    StatusTransitionError,
)

router = APIRouter(tags=["signatures"])


class SignRequest(BaseModel):
    object_type: str
    object_id: UUID
    signer_id: UUID
    signature_level: str
    signature_data: dict | None = None
    ip_address: str | None = None
    # R1 Task 7 需求 3.5：合伙人签字/归档签字提交 readiness 弹窗发放的
    # gate_eval_id，后端校验"5 分钟内未过期且对应 ready=True"，否则拒签。
    # 为向后兼容保留为可选；``project_id`` 同样可选，仅用于校验令牌绑定，
    # 不传则跳过令牌校验（老入口不破坏）。
    gate_eval_id: UUID | None = None
    project_id: UUID | None = None
    gate_type: str | None = None  # 'sign_off' | 'export_package'
    # R1 Task 11: 签字前置依赖
    required_order: int | None = None
    required_role: str | None = None
    prerequisite_signature_ids: list[str] | None = None


@router.post("/api/signatures/sign")
async def sign_document(
    body: SignRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """签署文档。

    R1 Task 7：若请求携带 ``gate_eval_id`` 与 ``project_id``/``gate_type``，
    则在签字前调用 ``gate_eval_store.validate_gate_eval`` 校验；失败返回
    ``403 GATE_STALE``。

    R1 Task 11：校验 prerequisite_signature_ids 全部已签，否则 403
    PREREQUISITE_NOT_MET。最高级签完后同事务切 AuditReport.status。
    """
    # --- gate_eval_id 校验（Task 7） ---
    if body.gate_eval_id is not None:
        if body.project_id is None or body.gate_type is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "GATE_EVAL_REQUEST_INCOMPLETE",
                    "message": "gate_eval_id 必须与 project_id 和 gate_type 同时提交",
                },
            )
        from app.services.gate_eval_store import validate_gate_eval

        ok, reason = await validate_gate_eval(
            str(body.gate_eval_id),
            project_id=body.project_id,
            gate_type=body.gate_type,
            require_ready=True,
        )
        if not ok:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "GATE_STALE",
                    "message": (
                        "gate_eval_id 无效、已过期或对应评估结果不为 PASS，"
                        "请刷新 readiness 检查后重试"
                    ),
                    "reason": reason,
                },
            )

    # --- 签字 + 前置校验 + 状态机联动（同事务） ---
    svc = SignService()
    user_agent = request.headers.get("user-agent")
    try:
        result = await svc.sign_document(
            db,
            object_type=body.object_type,
            object_id=body.object_id,
            signer_id=body.signer_id,
            level=body.signature_level,
            signature_data=body.signature_data,
            ip_address=body.ip_address,
            required_order=body.required_order,
            required_role=body.required_role,
            prerequisite_signature_ids=body.prerequisite_signature_ids,
            user_agent=user_agent,
            gate_eval_id=str(body.gate_eval_id) if body.gate_eval_id else None,
        )
        await db.commit()
        return result
    except PrerequisiteNotMetError as e:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "PREREQUISITE_NOT_MET",
                "message": "前置签字未完成，无法签署",
                "missing_ids": e.missing_ids,
            },
        )
    except StatusTransitionError as e:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "STATUS_TRANSITION_FAILED",
                "message": (
                    f"报告状态切换失败: 当前 {e.current_status}，"
                    f"预期 {e.expected_status}"
                ),
            },
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/signatures/workflow/{project_id}")
async def get_signature_workflow(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取项目签字工作流状态。

    返回 [{order, role, required_user_id, status, signed_at, signed_by}]
    status: 'waiting' | 'ready' | 'signed'
    """
    svc = SignService()
    return await svc.get_workflow(db, project_id)


@router.get("/api/signatures/{object_type}/{object_id}")
async def get_signatures(
    object_type: str, object_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取签名记录"""
    svc = SignService()
    return await svc.get_signatures(db, object_type, object_id)


@router.post("/api/signatures/{signature_id}/verify")
async def verify_signature(
    signature_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验证签名"""
    svc = SignService()
    try:
        return await svc.verify_signature(db, signature_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/signatures/{signature_id}/revoke")
async def revoke_signature(
    signature_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销签名"""
    svc = SignService()
    try:
        result = await svc.revoke_signature(db, signature_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
