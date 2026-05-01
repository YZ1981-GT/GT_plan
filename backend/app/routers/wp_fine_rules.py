"""底稿精细化规则 API

GET  /api/wp-fine-rules                              — 列出所有精细化规则
GET  /api/wp-fine-rules/{wp_code}                    — 获取指定底稿的精细化规则
POST /api/projects/{id}/workpapers/{wp_id}/fine-extract — 使用精细化规则提取数据
"""
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


@router.get("/api/wp-fine-rules")
async def list_rules(_user=Depends(get_current_user)):
    """列出所有精细化规则"""
    return {"rules": list_fine_rules()}


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
