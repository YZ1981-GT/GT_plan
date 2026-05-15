"""跨科目校验路由

Sprint 4 Task 4.2:
  POST /execute          执行校验（全量或指定规则）
  GET  /results          获取最近校验结果
  GET  /rules            获取规则库
  POST /rules/custom     新增项目级自定义规则
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_cross_check_service import CrossCheckService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/cross-check",
    tags=["cross-check"],
)


# ─── Request / Response Models ────────────────────────────────────────────────


class ExecuteRequest(BaseModel):
    year: int
    rule_ids: list[str] | None = None
    trigger: str = Field(default="manual", pattern="^(manual|save|sign_off)$")


class CustomRuleRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    formula: str = Field(..., min_length=1, max_length=2000)
    tolerance: float = Field(default=0.01, ge=0)
    severity: str = Field(default="warning", pattern="^(blocking|warning|info)$")
    applicable_stages: list[str] = Field(default_factory=lambda: ["completion"])
    applicable_cycles: list[str] = Field(default_factory=list)


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_cross_check(
    project_id: str,
    body: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """执行校验（全量或指定规则）"""
    svc = CrossCheckService(db)
    results = await svc.execute(
        UUID(project_id),
        body.year,
        rule_ids=body.rule_ids,
        trigger=body.trigger,
    )
    await db.commit()

    # 统计
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")

    return {
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": total - passed - failed - skipped,
        },
    }


@router.get("/results")
async def get_results(
    project_id: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """获取最近校验结果"""
    svc = CrossCheckService(db)
    results = await svc.get_latest_results(UUID(project_id), year)
    return {"items": results, "total": len(results)}


@router.get("/rules")
async def get_rules(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取规则库（内置 + 项目自定义）"""
    svc = CrossCheckService(db)
    rules = await svc.get_rules()
    return {"items": rules, "total": len(rules)}


@router.post("/rules/custom")
async def add_custom_rule(
    project_id: str,
    body: CustomRuleRequest,
    db: AsyncSession = Depends(get_db),
):
    """新增项目级自定义规则"""
    svc = CrossCheckService(db)
    rule_def = {
        "description": body.description,
        "formula": body.formula,
        "tolerance": body.tolerance,
        "severity": body.severity,
        "applicable_stages": body.applicable_stages,
        "applicable_cycles": body.applicable_cycles,
        "enabled": True,
    }
    result = await svc.add_custom_rule(UUID(project_id), rule_def)
    await db.commit()
    return result
