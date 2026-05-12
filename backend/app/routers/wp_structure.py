"""底稿三式联动 API

GET  /api/projects/{id}/workpapers/{wp_id}/structure     — 获取底稿 structure.json
POST /api/projects/{id}/workpapers/{wp_id}/structure      — 保存编辑后的 structure
POST /api/projects/{id}/workpapers/{wp_id}/structure/rebuild — 强制重建 structure
GET  /api/projects/{id}/workpapers/{wp_id}/structure/html  — 获取 HTML 预览
POST /api/projects/{id}/workpapers/batch-structure         — 批量生成 structure
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["底稿三式联动"],
)


@router.get("/{wp_id}/structure")
async def get_structure(
    project_id: UUID,
    wp_id: UUID,
    force_rebuild: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿的 structure.json（缓存优先，支持强制重建）"""
    wp, idx = await _get_wp_with_index(db, project_id, wp_id)

    from app.services.wp_structure_bridge import get_workpaper_structure
    structure = get_workpaper_structure(
        wp.file_path, idx.wp_code, str(project_id), 0, force_rebuild
    )
    if not structure:
        raise HTTPException(status_code=404, detail="无法生成 structure.json")

    return {
        "wp_id": str(wp_id),
        "wp_code": idx.wp_code,
        "structure": structure,
        "row_count": len(structure.get("rows", [])),
        "sheet_count": len(structure.get("sheets", [])),
        "sheet_names": [s.get("name", f"Sheet{i+1}") for i, s in enumerate(structure.get("sheets", []))],
        "has_formulas": any(
            c.get("formula")
            for r in structure.get("rows", [])
            for c in r.get("cells", [])
        ),
    }


@router.post("/{wp_id}/structure")
async def save_structure(
    project_id: UUID,
    wp_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """保存编辑后的 structure.json 并回写 Excel"""
    wp, idx = await _get_wp_with_index(db, project_id, wp_id)

    structure = body.get("structure")
    if not structure:
        raise HTTPException(status_code=400, detail="缺少 structure 数据")

    # 保存 structure.json
    import json
    from pathlib import Path
    structure_path = Path(wp.file_path).with_suffix(".structure.json")
    try:
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存 structure.json 失败: {e}")

    # 回写 Excel
    sync_excel = body.get("sync_excel", True)
    excel_synced = False
    if sync_excel and wp.file_path:
        from app.services.wp_structure_bridge import save_structure_to_excel
        excel_synced = save_structure_to_excel(wp.file_path, structure)

    # 版本递增
    wp.file_version = (wp.file_version or 0) + 1
    from datetime import datetime, timezone
    wp.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    # 失效地址缓存
    try:
        from app.services.address_registry import address_registry
        address_registry.invalidate(str(project_id), domain="wp")
    except Exception:
        pass

    return {
        "wp_id": str(wp_id),
        "version": wp.file_version,
        "excel_synced": excel_synced,
        "message": "保存成功",
    }


@router.post("/{wp_id}/structure/rebuild")
async def rebuild_structure(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """强制从 Excel 重建 structure.json（丢弃缓存）"""
    wp, idx = await _get_wp_with_index(db, project_id, wp_id)

    from app.services.wp_structure_bridge import generate_structure_for_workpaper
    structure = generate_structure_for_workpaper(
        wp.file_path, idx.wp_code, str(project_id), 0
    )
    if not structure:
        raise HTTPException(status_code=500, detail="重建失败")

    return {
        "wp_id": str(wp_id),
        "wp_code": idx.wp_code,
        "row_count": len(structure.get("rows", [])),
        "message": "structure.json 已重建",
    }


@router.get("/{wp_id}/structure/html")
async def get_structure_html(
    project_id: UUID,
    wp_id: UUID,
    page: int = Query(1),
    page_size: int = Query(200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿的 HTML 预览（支持分页）"""
    wp, idx = await _get_wp_with_index(db, project_id, wp_id)

    from app.services.wp_structure_bridge import get_workpaper_structure
    structure = get_workpaper_structure(wp.file_path, idx.wp_code, str(project_id))
    if not structure:
        raise HTTPException(status_code=404, detail="无法获取 structure")

    from app.services.excel_html_converter import structure_to_html
    html = structure_to_html(structure, page=page, page_size=page_size)

    total_rows = len(structure.get("rows", []))
    return {
        "wp_id": str(wp_id),
        "html": html,
        "total_rows": total_rows,
        "page": page,
        "page_size": page_size,
        "is_large": total_rows > page_size,
    }


@router.post("/batch-structure")
async def batch_generate(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量为项目所有底稿生成 structure.json"""
    from app.services.wp_structure_bridge import batch_generate_structures
    result = await batch_generate_structures(db, str(project_id))
    return result


@router.get("/{wp_id}/structure/addresses")
async def get_addresses(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿中可引用的地址坐标列表"""
    wp, idx = await _get_wp_with_index(db, project_id, wp_id)

    from app.services.wp_structure_bridge import get_workpaper_addresses
    addresses = get_workpaper_addresses(
        wp.file_path, idx.wp_code, str(project_id)
    )
    return {"wp_code": idx.wp_code, "addresses": addresses, "count": len(addresses)}


# ── Helper ──

async def _get_wp_with_index(db: AsyncSession, project_id: UUID, wp_id: UUID):
    """获取底稿+索引，不存在则404"""
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
    return row[0], row[1]
