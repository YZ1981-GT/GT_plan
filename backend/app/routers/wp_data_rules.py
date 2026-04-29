"""底稿通用数据提取规则 API

提供：
- 按底稿编号提取关联数据（试算表/调整分录/附注）
- 按附注章节提取关联数据
- 底稿与附注一致性校验
- 映射关系查询
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_data_rules import (
    extract_wp_data,
    extract_note_data,
    check_wp_note_consistency,
    get_mapping_for_wp,
    get_mapping_for_account,
    get_mapping_for_note,
    _load_mapping,
)

router = APIRouter(prefix="/api/wp-data-rules", tags=["底稿数据规则"])


@router.get("/mapping")
async def get_all_mappings(
    current_user: User = Depends(get_current_user),
):
    """获取完整的底稿-科目-报表-附注映射表"""
    return _load_mapping()


@router.get("/mapping/by-wp/{wp_code}")
async def get_mapping_by_wp(
    wp_code: str,
    current_user: User = Depends(get_current_user),
):
    """根据底稿编号查询映射关系"""
    m = get_mapping_for_wp(wp_code)
    if not m:
        return {"error": f"未找到底稿 {wp_code} 的映射"}
    return m


@router.get("/mapping/by-account/{account_code}")
async def get_mapping_by_account(
    account_code: str,
    current_user: User = Depends(get_current_user),
):
    """根据科目编码查询映射关系"""
    m = get_mapping_for_account(account_code)
    if not m:
        return {"error": f"未找到科目 {account_code} 的映射"}
    return m


@router.get("/mapping/by-note/{note_section}")
async def get_mapping_by_note(
    note_section: str,
    current_user: User = Depends(get_current_user),
):
    """根据附注章节号查询映射关系"""
    m = get_mapping_for_note(note_section)
    if not m:
        return {"error": f"未找到附注 {note_section} 的映射"}
    return m


@router.get("/projects/{project_id}/extract/{wp_code}")
async def extract_data_for_wp(
    project_id: UUID,
    wp_code: str,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提取底稿关联的全部数据（试算表+调整分录+附注映射）

    通用规则自动计算：
    - 期末未审数/AJE/RJE/审定数 从 trial_balance
    - 期初审定数 从上年 trial_balance
    - 变动额 = 审定 - 期初
    - 调整分录明细
    """
    return await extract_wp_data(db, project_id, year, wp_code)


@router.get("/projects/{project_id}/note-data/{note_section}")
async def extract_data_for_note(
    project_id: UUID,
    note_section: str,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提取附注章节关联的数据（从底稿/试算表）"""
    return await extract_note_data(db, project_id, year, note_section)


@router.get("/projects/{project_id}/consistency/{wp_code}")
async def check_consistency(
    project_id: UUID,
    wp_code: str,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验底稿审定数与附注合计的一致性"""
    return await check_wp_note_consistency(db, project_id, year, wp_code)


@router.get("/projects/{project_id}/batch-extract")
async def batch_extract(
    project_id: UUID,
    year: int = Query(default=2025),
    cycle: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量提取一个循环下所有底稿的数据

    用于底稿工作台一次性加载所有关联数据。
    """
    mappings = _load_mapping()
    if cycle:
        mappings = [m for m in mappings if m.get("cycle") == cycle]

    results = []
    for m in mappings:
        wp_code = m.get("wp_code")
        if wp_code:
            data = await extract_wp_data(db, project_id, year, wp_code)
            results.append(data)

    return {"cycle": cycle, "count": len(results), "items": results}


# ═══ 附注表格取数（三种样式 + 三种模式） ═══

@router.get("/projects/{project_id}/note-table/{note_section}/style")
async def get_note_table_style(
    project_id: UUID,
    note_section: str,
    current_user: User = Depends(get_current_user),
):
    """获取附注章节的表格样式（fixed_rows/dynamic_rows/mixed）"""
    from app.services.note_data_extractor import identify_table_style
    style = identify_table_style(note_section)
    return {"note_section": note_section, "table_style": style.value}


@router.get("/projects/{project_id}/note-table/{note_section}/cell")
async def note_cell(
    project_id: UUID,
    note_section: str,
    row_label: str = Query(...),
    col_header: str = Query(...),
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """固定单元格取数：NOTE_CELL(section, row_label, col_header)"""
    from app.services.note_data_extractor import note_cell_fetch
    val = await note_cell_fetch(db, project_id, year, note_section, row_label, col_header)
    return {"note_section": note_section, "row": row_label, "col": col_header, "value": str(val) if val is not None else None}


@router.get("/projects/{project_id}/note-table/{note_section}/column")
async def note_column(
    project_id: UUID,
    note_section: str,
    col_header: str = Query(...),
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """整列取数：NOTE_COL(section, col_header) → 支持浮动行填充"""
    from app.services.note_data_extractor import note_column_fetch
    rows = await note_column_fetch(db, project_id, year, note_section, col_header)
    return {"note_section": note_section, "col": col_header, "rows": rows}


@router.get("/projects/{project_id}/note-table/{note_section}/row")
async def note_row(
    project_id: UUID,
    note_section: str,
    row_label: str = Query(...),
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """整行取数：NOTE_ROW(section, row_label) → 支持变动表多列"""
    from app.services.note_data_extractor import note_row_fetch
    data = await note_row_fetch(db, project_id, year, note_section, row_label)
    return {"note_section": note_section, **data}


@router.get("/projects/{project_id}/note-table/{note_section}/dynamic-rows")
async def note_dynamic_rows(
    project_id: UUID,
    note_section: str,
    year: int = Query(default=2025),
    top_n: int = Query(default=20, ge=5, le=100),
    min_amount: float = Query(default=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成浮动行数据（从辅助余额表/底稿明细动态生成）

    参数：
    - top_n: 最多显示行数（默认20，超出合并为"其他"）
    - min_amount: 最小金额阈值（默认0，低于此值合并为"其他"）
    """
    from app.services.note_data_extractor import generate_dynamic_rows
    rows = await generate_dynamic_rows(db, project_id, year, note_section, top_n, min_amount)
    return {"note_section": note_section, "rows": rows, "count": len(rows)}
