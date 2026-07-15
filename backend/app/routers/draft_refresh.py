"""全局一键刷新统一入口（合伙人专属，Global_Refresh）.

公式管理库（formula-management-library）Task 5.5 / 设计 Components §1 与 §13。
formula-runtime-convergence Task 15: 收敛路由权限与 API 契约 [Req 10,12,13｜P13,P15]。

分层门禁（Req 1 / Req 20）：
- **全局一键刷新**（本模块 ``POST /api/workpapers/draft-refresh``）走**合伙人门禁**
  （``require_role(["partner", "signing_partner"])``），一次从四表库未审数生成
  未审报表 + 底稿 + 附注初稿。
- **模块/循环级局部刷新**（``wp_render_config.py`` 的 ``audit-sheet-refresh``）走
  **编辑权门禁**（``require_wp_edit_permission``），不锁死为合伙人。

门禁复用 ``deps.py`` 的 ``require_role``（不新增并行角色判断，Req 1.3）。
编排：``DraftRefreshService.precheck``（precheck 阻断 422，先于编排）+
``DraftRefreshOrchestrator.generate``（按勾选 scopes 分派生成器产 RefreshUnit + page_keys，
经 ``refresh_with_presets`` 治理：套预设 + 幂等 + Draft 标记 + 覆盖排除 + 审计留痕，Req 21）；
service 只 flush，router 层 commit（工程铁律）。

API 契约（design §11）：
- 空 scopes → 422（不再隐式全量刷新）。
- transaction_mode: all_or_nothing | partial_success（默认 all_or_nothing）。
- idempotency_key: 可选幂等键。
- rollback endpoint: POST /api/workpapers/draft-refresh/{run_id}/rollback。
- 响应严格按 DraftRefreshResponse / RollbackResponse Pydantic model。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import User
from app.schemas.formula_runtime import (
    DraftRefreshRequest,
    DraftRefreshResponse,
    PresetApplication,
    RollbackResponse,
)
from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_management.draft_refresh_orchestrator import (
    DraftRefreshOrchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["draft-refresh"],
)

# 合伙人角色（全局一键刷新专属门禁，Req 1.1）。复用 deps.require_role，不新增并行角色判断。
PARTNER_ROLES = ["partner", "signing_partner"]


@router.post("/draft-refresh", response_model=DraftRefreshResponse)
async def one_click_draft_refresh(
    body: DraftRefreshRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(PARTNER_ROLES)),
) -> DraftRefreshResponse:
    """全局一键刷新统一入口（合伙人专属，Global_Refresh，公式管理库 Req 1）。

    一次从四表库未审数生成未审报表 + 底稿 + 附注初稿。门禁复用 ``deps.py`` 的
    ``require_role(["partner", "signing_partner"])``（不新增并行角色判断，Req 1.3）——
    非合伙人一律 403 且不执行任何数据写入（Req 1.2）。

    空 scopes → 422（Req 12 / design Error Handling：不再隐式全量刷新）。
    transaction_mode 显式传入（默认 all_or_nothing）。
    idempotency_key 可选用于幂等校验。
    project ownership 显式传 project_id 到 service 层（Req 10）。
    all-or-nothing 失败时由 router rollback（Req 9）。

    编排（Req 1.4 / Req 21）：``DraftRefreshService.precheck``（四表库完整度前置校验）→
    ``DraftRefreshOrchestrator.generate``（按勾选 ``scopes`` 分派各上游生成器产出
    ``RefreshUnit`` + ``page_keys``，交治理层 ``refresh_with_presets`` 统一编排：套预设 +
    幂等 + Draft 标记 + 覆盖排除 + 快照 + 审计留痕，``affected_count = len(refreshed_units)``
    不再恒为 0）。
    """
    # 注意：空 scopes 已由 Pydantic min_length=1 校验，FastAPI 自动返回 422。

    service = DraftRefreshService()

    # 前置校验：四表库完整度不足则阻断，不执行任何写入（Req 2.2）——阻断不进 orchestrator
    precheck = await service.precheck(db, project_id=body.project_id, year=body.year)
    if not precheck.can_refresh:
        raise HTTPException(
            status_code=422,
            detail={"message": "四表库数据不完整，无法一键刷新", **precheck.to_dict()},
        )

    # 生成编排层（Req 21）：按勾选 scopes 分派生成器产 RefreshUnit + page_keys，
    # 交治理层 refresh_with_presets 统一编排（幂等 / Draft / 覆盖 / 快照 / 审计）
    # 显式传 project_id 到 service 层（Req 10 ownership context）
    orchestrator = DraftRefreshOrchestrator(db)
    try:
        result, preset_application = await orchestrator.generate(
            project_id=body.project_id,
            year=body.year,
            operator=_user,
            scopes=body.scopes,
            confirm_overwrite=body.confirm_overwrite,
        )
    except Exception as exc:
        # all-or-nothing 失败由 router rollback（Req 9）
        if body.transaction_mode == "all_or_nothing":
            await db.rollback()
        logger.exception("Draft refresh failed for project %s", body.project_id)
        raise HTTPException(
            status_code=500,
            detail={"message": f"刷新执行失败: {exc}"},
        ) from exc

    # service 只 flush，router 层 commit（工程铁律）
    await db.commit()

    # 构造标准响应（design §11）
    result_dict = result.to_dict() if hasattr(result, "to_dict") else {}
    preset_dict = (
        preset_application.to_dict()
        if hasattr(preset_application, "to_dict")
        else {}
    )

    return DraftRefreshResponse(
        status=result_dict.get("status", "success"),
        run_id=result_dict.get("run_id", body.project_id),
        transaction_mode=body.transaction_mode,
        affected_count=result_dict.get("affected_count", 0),
        applied_count=result_dict.get("applied_count", 0),
        failed_count=result_dict.get("failed_count", 0),
        skipped_count=result_dict.get("skipped_count", 0),
        scopes=body.scopes,
        idempotent=result_dict.get("idempotent", False),
        rollback_available=result_dict.get("rollback_available", True),
        warnings=result_dict.get("warnings", []),
        failures=result_dict.get("failures", []),
        preset_application=PresetApplication(
            preset_count=preset_dict.get("preset_count", 0),
            presetted_pages=preset_dict.get("presetted_pages", []),
            pending_pages=preset_dict.get("pending_pages", []),
        ),
    )


@router.post(
    "/draft-refresh/{run_id}/rollback",
    response_model=RollbackResponse,
)
async def rollback_draft_refresh(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(PARTNER_ROLES)),
) -> RollbackResponse:
    """回滚指定 Execution_Run（合伙人专属）。

    加载快照按写入逆序恢复业务值、Draft marker、生命周期状态等治理元数据（Req 2）。
    CAS 保护：若目标当前版本不等于快照 applied_version，返回 conflict（Req 2.4）。
    成功后写入 rolled_back 审计记录与 Outbox 失效事件。
    """
    service = DraftRefreshService()

    try:
        rollback_result = await service.rollback(db, run_id=run_id)
    except Exception as exc:
        await db.rollback()
        logger.exception("Rollback failed for run_id %s", run_id)
        return RollbackResponse(
            status="failed",
            run_id=run_id,
            restored_count=0,
            conflicts=[],
            error=str(exc),
        )

    await db.commit()

    # 构造 rollback 响应
    if hasattr(rollback_result, "to_dict"):
        rd = rollback_result.to_dict()
        return RollbackResponse(
            status="rolled_back",
            run_id=run_id,
            restored_count=rd.get("restored_count", 0),
            conflicts=rd.get("conflicts", []),
            error=None,
        )

    return RollbackResponse(
        status="rolled_back",
        run_id=run_id,
        restored_count=getattr(rollback_result, "restored_count", 0),
        conflicts=getattr(rollback_result, "conflicts", []),
        error=None,
    )
