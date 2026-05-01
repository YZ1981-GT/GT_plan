"""账龄分析 API

GET  /api/aging/presets                              — 获取账龄预设方案（三年段/五年段）
GET  /api/projects/{id}/aging/config                 — 获取项目账龄配置
PUT  /api/projects/{id}/aging/config                 — 保存项目账龄配置（预设选择+自定义分段+计提比例）
POST /api/projects/{id}/aging/calculate              — 计算账龄坏账计提
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User, Project
from app.services.aging_analysis_service import (
    get_aging_presets, get_project_aging_config,
    get_effective_segments, calculate_aging_provision,
)

router = APIRouter(prefix="/api", tags=["账龄分析"])


@router.get("/aging/presets")
async def list_presets(_user=Depends(get_current_user)):
    """获取账龄预设方案"""
    presets = get_aging_presets()
    return {
        "presets": {
            k: {"name": v.get("name"), "description": v.get("description", ""), "segment_count": len(v.get("segments", []))}
            for k, v in presets.items() if k != "custom"
        },
        "details": presets,
    }


@router.get("/projects/{project_id}/aging/config")
async def get_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取项目账龄配置"""
    config = await get_project_aging_config(db, project_id)
    segments = get_effective_segments(
        config["preset"], config.get("custom_segments"), config.get("custom_rates")
    )
    return {
        "project_id": str(project_id),
        "preset": config["preset"],
        "custom_segments": config.get("custom_segments", []),
        "custom_rates": config.get("custom_rates", {}),
        "effective_segments": segments,
    }


@router.put("/projects/{project_id}/aging/config")
async def save_config(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """保存项目账龄配置"""
    result = await db.execute(sa.select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = project.wizard_state or {}
    ws["aging_config"] = {
        "preset": body.get("preset", "three_year"),
        "custom_segments": body.get("custom_segments", []),
        "custom_rates": body.get("custom_rates", {}),
    }
    project.wizard_state = ws
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "wizard_state")
    await db.flush()
    await db.commit()

    return {"message": "账龄配置已保存", "preset": ws["aging_config"]["preset"]}


@router.post("/projects/{project_id}/aging/calculate")
async def calculate(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """计算账龄坏账计提"""
    year = body.get("year", 2025)
    account_code = body.get("account_code", "1122")
    preset = body.get("preset")
    custom_segments = body.get("custom_segments")
    custom_rates = body.get("custom_rates")

    # 如果未指定预设，从项目配置读取
    if not preset:
        config = await get_project_aging_config(db, project_id)
        preset = config["preset"]
        if not custom_segments:
            custom_segments = config.get("custom_segments")
        if not custom_rates:
            custom_rates = config.get("custom_rates")

    # 存货科目走库龄分析
    if account_code.startswith("140") or account_code.startswith("146"):
        from app.services.aging_analysis_service import calculate_inventory_aging
        return await calculate_inventory_aging(db, project_id, year, preset, custom_rates)

    result = await calculate_aging_provision(
        db, project_id, year, account_code, preset, custom_segments, custom_rates
    )
    return result


@router.get("/aging/inventory-presets")
async def list_inventory_presets(_user=Depends(get_current_user)):
    """获取存货库龄预设方案"""
    from app.services.aging_analysis_service import get_inventory_aging_presets
    presets = get_inventory_aging_presets()
    return {
        "presets": {
            k: {"name": v["name"], "segment_count": len(v["segments"])}
            for k, v in presets.items()
        },
        "details": presets,
    }
