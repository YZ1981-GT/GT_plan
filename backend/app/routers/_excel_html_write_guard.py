"""legacy Excel-HTML 文件写入口的底稿绑定门（platform-release-blocker-closure Task 9）。

从 excel_html.py 抽出的伴生模块：五个 legacy 文件写端点（save_edits / confirm_as_template /
sync_from_onlyoffice / rollback_file_version / execute_formulas）在产生副作用前，都先经本函数解析
file_stem → 底稿，若对应底稿则过项目 / 底稿门并锁定终态状态行（复核通过 / 归档 → 423）。
抽成独立模块是为把 excel_html.py 控制在行数门内（优先抽伴生模块、不抬 whitelist）。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User


async def guard_bound_workpaper_write(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    file_stem: str,
    *,
    route_name: str,
) -> UUID | None:
    """legacy 文件入口若对应底稿，先过项目/底稿门并锁定终态状态行。"""
    import sqlalchemy as sa

    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.routers._wp_gate import enforce_wp_gate, raise_if_workpaper_frozen

    wp_id = (
        await db.execute(
            sa.select(WorkingPaper.id)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WpIndex.wp_code == file_stem,
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.is_deleted == sa.false(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if wp_id is None:
        return None
    await enforce_wp_gate(
        db,
        current_user,
        entrypoint="workpaper.parsed_data_write",
        action="save_parsed_data",
        method="POST",
        wp_id=wp_id,
        project_id=project_id,
        entry_family="file",
        route_name=route_name,
    )
    await raise_if_workpaper_frozen(db, wp_id)
    return wp_id


__all__ = ["guard_bound_workpaper_write"]
