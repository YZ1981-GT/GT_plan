"""底稿功能行为动作 API — wp-functional-actions spec

端点：
  GET  /api/projects/{project_id}/workpapers/{wp_id}/actions
       → 根据底稿 functional_type 返回可用动作列表
  POST /api/projects/{project_id}/workpapers/{wp_id}/actions/execute
       → 执行指定动作（调后端取数 → 填回 parsed_data）
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_action_registry import (
    ACTION_REGISTRY,
    get_actions,
    get_action_config,
    ActionConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["wp-functional-actions"])


# ─── Schemas ───────────────────────────────────────────────

class ActionInfo(BaseModel):
    label: str
    description: str
    endpoint: str
    method: str
    params_schema: dict[str, Any]
    fill_strategy: str
    requires_llm: bool
    icon: str


class ActionsResponse(BaseModel):
    functional_type: str | None
    actions: list[ActionInfo]


class ExecuteActionRequest(BaseModel):
    action_label: str
    params: dict[str, Any]


class ExecuteActionResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] | None = None
    rows_affected: int = 0


# ─── 获取可用动作 ─────────────────────────────────────────

@router.get("/{project_id}/workpapers/{wp_id}/actions", response_model=ActionsResponse)
async def get_workpaper_actions(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿可用的功能行为动作列表"""
    # 查询底稿的 functional_type
    functional_type = await _get_functional_type(db, project_id, wp_id)

    if not functional_type:
        return ActionsResponse(functional_type=None, actions=[])

    actions = get_actions(functional_type)
    return ActionsResponse(
        functional_type=functional_type,
        actions=[
            ActionInfo(
                label=a.label,
                description=a.description,
                endpoint=a.endpoint,
                method=a.method,
                params_schema=a.params_schema,
                fill_strategy=a.fill_strategy,
                requires_llm=a.requires_llm,
                icon=a.icon,
            )
            for a in actions
        ],
    )


# ─── 执行动作 ─────────────────────────────────────────────

@router.post(
    "/{project_id}/workpapers/{wp_id}/actions/execute",
    response_model=ExecuteActionResponse,
)
async def execute_workpaper_action(
    project_id: UUID,
    wp_id: UUID,
    req: ExecuteActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行底稿功能行为动作（取数→填回 parsed_data）"""
    functional_type = await _get_functional_type(db, project_id, wp_id)
    if not functional_type:
        raise HTTPException(status_code=422, detail={"message": "该底稿未配置功能行为类型"})

    action = get_action_config(functional_type, req.action_label)
    if not action:
        raise HTTPException(
            status_code=422,
            detail={"message": f"未找到动作: {req.action_label}"},
        )

    if action.requires_llm:
        # LLM 链路待接入 — 返回提示
        return ExecuteActionResponse(
            success=False,
            message="LLM 链路待接入，该动作暂不可用",
            data=None,
            rows_affected=0,
        )

    # 调用对应后端取数服务
    try:
        result = await _dispatch_action(db, project_id, wp_id, action, req.params)
    except Exception as e:
        logger.exception(f"动作执行失败: {action.label}")
        raise HTTPException(
            status_code=500,
            detail={"message": f"动作执行失败: {str(e)}"},
        )

    # 填回 parsed_data
    rows_affected = await _fill_parsed_data(
        db, wp_id, result, action.fill_strategy
    )

    return ExecuteActionResponse(
        success=True,
        message=f"{action.label} 执行成功",
        data=result,
        rows_affected=rows_affected,
    )


# ─── 获取全局注册表（前端初始化用） ─────────────────────────

@router.get("/actions/registry")
async def get_action_registry(
    current_user: User = Depends(get_current_user),
):
    """获取完整动作注册表（前端缓存用）"""
    registry = {}
    for ft, actions in ACTION_REGISTRY.items():
        registry[ft] = [
            ActionInfo(
                label=a.label,
                description=a.description,
                endpoint=a.endpoint,
                method=a.method,
                params_schema=a.params_schema,
                fill_strategy=a.fill_strategy,
                requires_llm=a.requires_llm,
                icon=a.icon,
            ).model_dump()
            for a in actions
        ]
    return registry


# ─── 内部辅助 ─────────────────────────────────────────────

async def _get_functional_type(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> str | None:
    """查询底稿的 functional_type（通过 wp_code 关联 classification 表）"""
    # 先获取底稿的 wp_code
    result = await db.execute(text(
        "SELECT wp_code FROM working_paper WHERE id = :wp_id AND project_id = :pid"
    ), {"wp_id": str(wp_id), "pid": str(project_id)})
    row = result.fetchone()
    if not row:
        return None

    wp_code = row[0]

    # 查 classification 表的 functional_type（取第一个非空值）
    result2 = await db.execute(text(
        "SELECT DISTINCT functional_type FROM workpaper_sheet_classification "
        "WHERE wp_code = :wp_code AND functional_type IS NOT NULL "
        "LIMIT 1"
    ), {"wp_code": wp_code})
    ft_row = result2.fetchone()
    return ft_row[0] if ft_row else None


async def _dispatch_action(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    action: ActionConfig,
    params: dict[str, Any],
) -> dict[str, Any]:
    """根据 action.endpoint 分派到对应 service"""
    from app.services.sampling_enhanced_service import (
        CutoffTestService,
        AgingAnalysisService,
        MonthlyDetailService,
    )

    endpoint = action.endpoint

    if endpoint == "sampling/cutoff-test":
        svc = CutoffTestService()
        return await svc.run_cutoff_test(
            db,
            project_id,
            params.get("year", 2025),
            params.get("account_codes", []),
            params.get("days_before", 5),
            params.get("days_after", 5),
            params.get("amount_threshold", 10000),
        )

    elif endpoint == "sampling/aging-analysis":
        svc = AgingAnalysisService()
        brackets = params.get("aging_brackets", [
            {"label": "1年以内", "min_days": 0, "max_days": 365},
            {"label": "1-2年", "min_days": 366, "max_days": 730},
            {"label": "2-3年", "min_days": 731, "max_days": 1095},
            {"label": "3年以上", "min_days": 1096},
        ])
        return await svc.analyze_aging(
            db,
            project_id,
            params.get("account_code", ""),
            brackets,
            params.get("base_date", ""),
            params.get("year"),
        )

    elif endpoint == "sampling/monthly-detail":
        svc = MonthlyDetailService()
        return await svc.generate_monthly_detail(
            db,
            project_id,
            params.get("account_code", ""),
            params.get("year", 2025),
        )

    elif endpoint == "sampling/execute":
        # 抽凭 — 使用 WpSamplingEngine
        from app.services.wp_sampling_engine import WpSamplingEngine
        engine = WpSamplingEngine()
        return await engine.execute_sampling(
            db=db,
            project_id=project_id,
            year=params.get("year", 2025),
            account_codes=params.get("account_codes", []),
            method=params.get("method", "random"),
            sample_size=params.get("sample_size", 25),
            amount_threshold=params.get("amount_threshold"),
            sampling_interval=params.get("sampling_interval"),
        )

    else:
        raise ValueError(f"未实现的端点: {endpoint}")


async def _fill_parsed_data(
    db: AsyncSession,
    wp_id: UUID,
    data: dict[str, Any],
    strategy: str,
) -> int:
    """将取数结果填回底稿 parsed_data

    策略：
      - replace_rows: 替换 action_data 区域
      - append_rows: 追加到 action_data
      - merge_cells: 按 cell 合并
    """
    import json

    # 读取当前 parsed_data
    result = await db.execute(text(
        "SELECT parsed_data FROM working_paper WHERE id = :wp_id"
    ), {"wp_id": str(wp_id)})
    row = result.fetchone()
    if not row:
        return 0

    parsed_data = row[0] or {}
    if isinstance(parsed_data, str):
        parsed_data = json.loads(parsed_data)

    # 写入 action_data 区域
    if strategy == "replace_rows":
        parsed_data["action_data"] = data
    elif strategy == "append_rows":
        existing = parsed_data.get("action_data", {})
        if isinstance(existing, dict) and "entries" in existing and "entries" in data:
            existing["entries"] = existing.get("entries", []) + data["entries"]
            parsed_data["action_data"] = existing
        else:
            parsed_data["action_data"] = data
    elif strategy == "merge_cells":
        parsed_data["action_data"] = {**parsed_data.get("action_data", {}), **data}

    # 写回
    await db.execute(text(
        "UPDATE working_paper SET parsed_data = :pd::jsonb WHERE id = :wp_id"
    ), {"pd": json.dumps(parsed_data, ensure_ascii=False, default=str), "wp_id": str(wp_id)})
    await db.flush()

    rows_affected = len(data.get("entries", [])) if "entries" in data else 1
    return rows_affected
