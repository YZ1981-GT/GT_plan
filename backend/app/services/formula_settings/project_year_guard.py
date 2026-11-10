"""项目级底稿没有年度列；实际写事务须锁定并重读项目年度。"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa


async def matches_project_year(db, project_id: UUID | str, year: int | None,
                               *, lock: bool = False) -> bool:
    """锁保持到调用方提交或回滚；非锁预检不能替代写入事务内的核验。

    populate_existing 避免 identity map 返回加锁前缓存的年度。SQLite 不实现
    FOR UPDATE；内存用例只能验证读写语义，不能证明 PostgreSQL 的锁竞争。
    """
    from app.models.base import ProjectStatus
    from app.models.core import Project
    from app.services.project_audit_year import resolve_project_audit_year

    if year is None:
        return False
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    if lock:
        statement = (sa.select(Project).where(Project.id == pid)
                     .with_for_update().execution_options(populate_existing=True))
        project = (await db.execute(statement)).scalar_one_or_none()
    else:
        project = await db.get(Project, pid)
    return (project is not None and not project.is_deleted
            and project.status != ProjectStatus.archived
            and resolve_project_audit_year(project) == year)
