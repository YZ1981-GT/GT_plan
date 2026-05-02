"""底稿精细化规则 API

GET  /api/wp-fine-rules                              — 列出所有精细化规则（支持 cycle/quality 过滤）
GET  /api/wp-fine-rules/summary                      — 精细化规则汇总统计
GET  /api/wp-fine-rules/system-map                   — 底稿体系全景图（四阶段递进+11个业务循环）
GET  /api/wp-fine-rules/{wp_code}                    — 获取指定底稿的精细化规则
POST /api/projects/{id}/workpapers/{wp_id}/fine-extract — 使用精细化规则提取数据
"""
import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_fine_rule_engine import load_fine_rule, list_fine_rules, extract_with_fine_rule

router = APIRouter(tags=["底稿精细化"])

_SYSTEM_MAP_PATH = Path(__file__).parent.parent.parent / "data" / "wp_system_map.json"


@router.get("/api/wp-fine-rules")
async def list_rules(
    cycle: str | None = None,
    quality: str | None = None,
    _user=Depends(get_current_user),
):
    """列出所有精细化规则

    可选过滤：
    - cycle: 循环前缀（A/B/C/D/E/F/G/H/I/J/K/L/M/N/S/T）
    - quality: 质量等级（A=精修/B=有layout/C=有checks/D=基础）
    """
    rules = list_fine_rules()
    if cycle:
        rules = [r for r in rules if r.get("cycle_prefix") == cycle.upper()]
    if quality:
        rules = [r for r in rules if r.get("quality") == quality.upper()]
    return {"rules": rules, "total": len(rules)}


@router.get("/api/wp-fine-rules/summary")
async def rules_summary(_user=Depends(get_current_user)):
    """精细化规则汇总统计（按循环分组）"""
    rules = list_fine_rules()
    by_cycle = {}
    for r in rules:
        cycle = r.get("cycle", "其他")
        entry = by_cycle.setdefault(cycle, {"total": 0, "refined": 0, "checks_total": 0})
        entry["total"] += 1
        if r.get("quality") == "A":
            entry["refined"] += 1
        entry["checks_total"] += r.get("checks", 0)
    return {
        "total": len(rules),
        "refined": sum(1 for r in rules if r.get("quality") == "A"),
        "by_cycle": by_cycle,
    }


@router.get("/api/wp-fine-rules/system-map")
async def get_system_map(_user=Depends(get_current_user)):
    """底稿体系全景图

    返回四阶段递进关系（准备→控制测试→实质性→完成）和 11 个业务循环的
    B→C→实质性底稿关联，供前端可视化展示。
    """
    if not _SYSTEM_MAP_PATH.exists():
        raise HTTPException(status_code=404, detail="wp_system_map.json not found")
    with open(_SYSTEM_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/api/wp-fine-rules/{wp_code}")
async def get_rule(wp_code: str, _user=Depends(get_current_user)):
    """获取指定底稿的精细化规则"""
    rule = load_fine_rule(wp_code)
    if not rule:
        raise HTTPException(status_code=404, detail=f"No fine rule for {wp_code}")
    return rule


@router.post("/api/projects/{project_id}/workpapers/{wp_id}/fine-extract")
async def fine_extract(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """使用精细化规则从底稿提取结构化数据"""
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp, idx = row
    if not wp.file_path:
        raise HTTPException(status_code=400, detail="底稿文件路径为空")

    data = extract_with_fine_rule(
        wp.file_path, idx.wp_code, str(project_id)
    )
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])

    # 持久化检查结果到 parsed_data.fine_checks
    try:
        pd = wp.parsed_data or {}
        pd["fine_checks"] = data.get("checks", [])
        pd["fine_summary"] = data.get("summary", {})
        pd["fine_extracted_at"] = __import__("datetime").datetime.utcnow().isoformat()
        wp.parsed_data = pd
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wp, "parsed_data")
        await db.flush()
        await db.commit()
    except Exception:
        pass  # 持久化失败不阻断返回

    return data
