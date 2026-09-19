"""Evidence Governance 路由包（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R4, R5, R8, R12
Design: §3.2 统一 Facade 与服务职责, §6.1 通用约定, §7.2 稳定失败类别

本包提供治理层的 FastAPI 装配：

- ``get_evidence_facade``：把 ``EvidenceGovernanceFacade`` 绑定到请求 DB 会话的依赖，
  后续 wave（上传/OCR/引用/门禁端点）统一经此获取 facade。
- ``resolve_user_actor``：从当前登录用户构造 ``(ActorContext, system_role)``。
- ``evidence_governance_error_handler`` / ``raise_http``：把稳定 ``EvidenceErrorCode``
  映射为 HTTP 状态与脱敏错误体（design §7.2）。
- ``router``：``/api/projects/{project_id}/years/{year}/evidence`` 根。当前提供只读
  command 审计状态端点（router 不提交业务事务；写端点在后续 wave 加入并委托 facade）。

注册到 router_registry/system.py §134。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.evidence_governance_models import (
    EvidenceAuditCommandRoot,
    EvidenceAuditTransition,
)
from app.services.evidence_governance.facade import EvidenceGovernanceFacade
from app.services.evidence_governance.frozen_contracts import (
    API_ROOT_TEMPLATE,
    ActorContext,
    EvidenceGovernanceError,
)

router = APIRouter(prefix="/api/projects/{project_id}/years/{year}/evidence", tags=["证据治理"])


# ---------------------------------------------------------------------------
# 依赖
# ---------------------------------------------------------------------------

def get_evidence_facade(db: AsyncSession = Depends(get_db)) -> EvidenceGovernanceFacade:
    """请求级 ``EvidenceGovernanceFacade``（绑定当前会话；facade 管理短事务）。"""
    return EvidenceGovernanceFacade(db)


def resolve_user_actor(
    current_user: User = Depends(get_current_user),
) -> tuple[ActorContext, str]:
    """从登录用户构造 ``(ActorContext(user), system_role)``。角色以 DB 为权威真源。"""
    return ActorContext.for_user(current_user.id), current_user.role.value


def raise_http(err: EvidenceGovernanceError) -> "HTTPException":
    """把治理错误映射为脱敏 HTTP 响应（error_code/message/retryable，无目标细节）。"""
    return HTTPException(
        status_code=err.http_status,
        detail={
            "error_code": err.error_code.value,
            "message": str(err),
            "retryable": err.retryable,
        },
    )


# ---------------------------------------------------------------------------
# 只读：command 审计状态（R12 可观测性；router 不提交业务事务）
# ---------------------------------------------------------------------------

@router.get("/commands/{command_root_id}")
async def get_command_status(
    project_id: uuid.UUID,
    year: int,
    command_root_id: uuid.UUID,
    facade: EvidenceGovernanceFacade = Depends(get_evidence_facade),
    actor_role: tuple[ActorContext, str] = Depends(resolve_user_actor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回某 command-root 的脱敏状态 + transition 时间线。

    scope 授权先于读取：``authorize_object`` 从 DB 重新解析该 command-root 的权威归属，
    并与 path scope 比对；不存在与越权返回同一脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``。
    """
    actor, role = actor_role
    try:
        await facade.scope_guard.authorize_object(
            actor_role=role,
            actor=actor,
            object_type="command_root",
            object_id=command_root_id,
            requested_project_id=project_id,
            requested_year=year,
        )
    except EvidenceGovernanceError as err:
        raise raise_http(err)

    root = await db.get(EvidenceAuditCommandRoot, command_root_id)
    if root is None:  # 已通过 scope 授权，理论上必存在；防御性脱敏
        from app.services.evidence_governance.frozen_contracts import EvidenceErrorCode

        raise raise_http(
            EvidenceGovernanceError(EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN)
        )

    transitions = (
        (
            await db.execute(
                select(EvidenceAuditTransition)
                .where(EvidenceAuditTransition.command_root_id == command_root_id)
                .order_by(EvidenceAuditTransition.at.asc())
            )
        )
        .scalars()
        .all()
    )

    return {
        "command_root_id": str(root.id),
        "command_type": root.command_type,
        "result": root.result,
        "reason_code": root.reason_code,
        "trace_id": root.trace_id,
        "transitions": [
            {
                "transition_type": t.transition_type,
                "from_state": t.from_state,
                "to_state": t.to_state,
                "metadata": t.metadata_redacted or {},
                "at": t.at.isoformat() if t.at else None,
            }
            for t in transitions
        ],
    }


# ---------------------------------------------------------------------------
# 全局可观测性（Task 7.4, Wave 6；design §9.3）
#   进程级低基数指标聚合 + 近期告警；admin/manager 只读。指标为进程内聚合，
#   非项目 scope，故独立于项目 scope 根，走全局 /api/evidence-governance 前缀。
# ---------------------------------------------------------------------------

observability_router = APIRouter(prefix="/api/evidence-governance", tags=["证据治理可观测性"])


@observability_router.get("/metrics")
async def get_evidence_governance_metrics(
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回治理低基数指标 + 近期告警聚合（design §9.3）。

    覆盖 upload/boundary/ref/OCR queue+failure/AI coverage/citation/stale
    age+closure/review reopen/formal gate/archive hash/hold/outbox lag/PG pool
    wait/backpressure。告警关联 command-root/transition/trace，metadata 已脱敏。
    """
    from app.services.evidence_governance.observability import get_evidence_metrics

    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role not in ("admin", "manager", "partner"):
        from app.services.evidence_governance.frozen_contracts import EvidenceErrorCode

        raise raise_http(
            EvidenceGovernanceError(EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN)
        )
    return get_evidence_metrics().get_aggregated_metrics()


# 安全上传 + 安全读取端点（Task 3.2/3.3/3.4 的 HTTP 接线）。放在包末尾导入，避免与
# 本模块的依赖/异常辅助形成循环导入；由 router_registry/system.py §135 挂载。
from app.routers.evidence_governance.attachments_router import (  # noqa: E402
    router as attachments_router,
)

__all__ = [
    "router",
    "observability_router",
    "attachments_router",
    "get_evidence_facade",
    "resolve_user_actor",
    "raise_http",
    "API_ROOT_TEMPLATE",
]
