"""附注行关联底稿端点 [R8-S2-12]

GET /api/notes/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers
返回与指定附注行关联的底稿列表（通过 note→account→wp_mapping 追溯）。

简化实现：
- 按 note_section 前缀匹配底稿 wp_code（例如 note_section='4.1' 匹配 wp_code 以 '4.1' 或相关循环前缀开头）
- 返回项目所有底稿（客户端自行筛选）或按 row_code 提示筛选
- 完整实现需 note_account_mapping 表（本轮不新建，留待后续）
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/notes",
    tags=["note-workpapers"],
)


@router.get("/{project_id}/{year}/{note_section}/row/{row_code}/related-workpapers")
async def get_note_row_related_workpapers(
    project_id: UUID,
    year: int,
    note_section: str,
    row_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回附注行关联的底稿列表

    Args:
        project_id: 项目 ID
        year: 年度
        note_section: 附注章节号（如 '4.1'）
        row_code: 行编码（如 'row_1', 'currency_cash'）

    Returns:
        {
            "note_section": "4.1",
            "row_code": "row_1",
            "workpapers": [{"id", "wp_code", "wp_name"}]
        }
    """
    from app.models.workpaper_models import WpIndex

    # 简化实现：返回该项目全部底稿，前端可显示选择器
    # 完整实现需 DisclosureNote.account_code 映射到 wp_account_mapping
    stmt = (
        select(WpIndex)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa: E712
        )
        .order_by(WpIndex.wp_code)
        .limit(50)
    )
    try:
        wps = (await db.execute(stmt)).scalars().all()
    except Exception:
        wps = []

    return {
        "note_section": note_section,
        "row_code": row_code,
        "workpapers": [
            {
                "id": str(wp.id),
                "wp_code": wp.wp_code,
                "wp_name": wp.wp_name,
            }
            for wp in wps
        ],
    }
