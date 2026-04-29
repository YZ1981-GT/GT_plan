"""数据集查询过滤器 — 统一读路径

过渡策略：
- 第一步（当前）：提供 active_data_filter() 工具函数
  - 有 active dataset 时用 dataset_id 过滤
  - 无 dataset 时降级为 is_deleted=false（兼容旧数据）
- 第二步：四表新增 dataset_id 列（ALTER TABLE）
- 第三步：新导入写入时填充 dataset_id
- 第四步：查询逐步迁移到 dataset_id 过滤

当前阶段（第一步）：所有读路径应通过此模块获取过滤条件，
而非直接散落 is_deleted=false。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dataset_service import DatasetService


async def get_active_filter(
    db: AsyncSession,
    table: sa.Table,
    project_id: UUID,
    year: int,
) -> sa.ColumnElement:
    """获取四表查询的统一过滤条件

    过渡期逻辑：
    - 始终包含 project_id + year + is_deleted=false
    - 未来有 dataset_id 列时，优先用 dataset_id 过滤

    Args:
        db: 数据库会话
        table: SQLAlchemy Table 对象（如 TbBalance.__table__）
        project_id: 项目 ID
        year: 年度

    Returns:
        SQLAlchemy WHERE 条件表达式
    """
    base_filter = sa.and_(
        table.c.project_id == project_id,
        table.c.year == year,
        table.c.is_deleted == sa.false(),
    )

    # 四表已有 dataset_id 列，优先用 active dataset 过滤
    active_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if active_id and hasattr(table.c, 'dataset_id'):
        return sa.and_(
            table.c.project_id == project_id,
            table.c.year == year,
            table.c.dataset_id == active_id,
            table.c.is_deleted == sa.false(),
        )

    return base_filter


def sync_active_filter(
    table: sa.Table,
    project_id: UUID,
    year: int,
) -> sa.ColumnElement:
    """同步版本的过滤条件（不查 dataset，纯 is_deleted 过滤）

    供不方便 await 的场景使用。
    """
    return sa.and_(
        table.c.project_id == project_id,
        table.c.year == year,
        table.c.is_deleted == sa.false(),
    )


async def get_active_dataset_id_or_none(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> UUID | None:
    """获取当前 active 数据集 ID（便捷入口）

    供需要 dataset_id 的场景使用（如导入历史页面标注当前版本）。
    """
    return await DatasetService.get_active_dataset_id(db, project_id, year)
