"""三元组唯一性检查器。

检查 (company_code, audit_year, report_scope) 组合在非删除项目中是否唯一。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from uuid import UUID


async def check_uniqueness(
    company_code: str,
    audit_year: int,
    report_scope: str,
    db: AsyncSession,
    *,
    exclude_project_id: UUID | None = None,
) -> tuple[bool, str | None]:
    """检查三元组唯一性，返回 (is_unique, error_message)。排除 is_deleted=True 的项目。

    ``exclude_project_id``：向导保存基本信息时排除本项目自身（R2.3），
    既有调用方（create_project / continuous_audit）不传、行为不变。
    """
    stmt = select(Project.id).where(
        Project.company_code == company_code,
        Project.audit_year == audit_year,
        Project.report_scope == report_scope,
        Project.is_deleted == False,  # noqa: E712
    )
    if exclude_project_id is not None:
        stmt = stmt.where(Project.id != exclude_project_id)
    stmt = stmt.limit(1)

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        if report_scope == "standalone":
            return False, "已存在该单位该年度的单户项目"
        else:
            return False, "已存在该单位该年度的合并项目"

    return True, None
