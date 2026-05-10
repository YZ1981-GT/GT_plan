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
    *,
    force_dataset_id: UUID | None = None,
) -> sa.ColumnElement:
    """获取四表查询的统一过滤条件

    过渡期逻辑：
    - 始终包含 project_id + year + is_deleted=false
    - 未来有 dataset_id 列时，优先用 dataset_id 过滤

    F50 / Sprint 8.20: 新增 ``force_dataset_id`` 参数。
    下游对象（Workpaper/AuditReport/DisclosureNote/Misstatement）已绑定
    ``bound_dataset_id`` 时，调用方应把该 id 传入 ``force_dataset_id``，
    查询会强制锁定在该数据集版本（忽略 status='active'），保证"签字时看到
    什么数据，之后就永远是什么数据"的合规语义。

    Args:
        db: 数据库会话
        table: SQLAlchemy Table 对象（如 TbBalance.__table__）
        project_id: 项目 ID
        year: 年度
        force_dataset_id: 可选，强制使用的 dataset_id（绑定模式）

    Returns:
        SQLAlchemy WHERE 条件表达式
    """
    # F50: force_dataset_id 模式 —— 下游对象已绑定版本快照
    if force_dataset_id is not None and hasattr(table.c, "dataset_id"):
        return sa.and_(
            table.c.project_id == project_id,
            table.c.year == year,
            table.c.dataset_id == force_dataset_id,
            table.c.is_deleted == sa.false(),
        )

    base_filter = sa.and_(
        table.c.project_id == project_id,
        table.c.year == year,
        table.c.is_deleted == sa.false(),
    )

    # 四表已有 dataset_id 列，优先用 active dataset 过滤
    try:
        active_id = await DatasetService.get_active_dataset_id(db, project_id, year)
        if active_id and hasattr(table.c, 'dataset_id'):
            return sa.and_(
                table.c.project_id == project_id,
                table.c.year == year,
                table.c.dataset_id == active_id,
                table.c.is_deleted == sa.false(),
            )
    except Exception:
        pass  # ledger_datasets 表可能不存在，降级到 is_deleted 过滤

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


def get_filter_with_dataset_id(
    table: sa.Table,
    project_id: UUID,
    year: int,
    dataset_id: UUID,
) -> sa.ColumnElement:
    """同步版本：使用预先获取的 dataset_id 构建过滤条件（B' 架构优化）

    适用场景：service 入口先查一次 active dataset_id，后续批量查询复用，
    避免每次 get_active_filter 都查 ledger_datasets 表。

    Args:
        table: SQLAlchemy Table 对象（如 TbBalance.__table__）
        project_id: 项目 ID
        year: 年度
        dataset_id: 预先获取的 active dataset_id

    Returns:
        SQLAlchemy WHERE 条件表达式（project_id + year + dataset_id + is_deleted=false）
    """
    return sa.and_(
        table.c.project_id == project_id,
        table.c.year == year,
        table.c.dataset_id == dataset_id,
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


async def bind_to_active_dataset(
    db: AsyncSession,
    obj,
    project_id: UUID,
    year: int,
) -> UUID | None:
    """F50 / Sprint 8.17-8.19: 通用下游对象绑定工具。

    把 ``obj.bound_dataset_id`` 和 ``obj.dataset_bound_at`` 设为当前 active
    dataset。如果没有 active dataset（项目尚未导入账套），两个字段保持 None
    不抛异常（允许先建底稿后导账套的工作流）。

    调用方：
    - Workpaper 首次生成时（template_engine.generate_project_workpapers / wp_template.py）
    - DisclosureNote 创建时（disclosure_engine / consol_disclosure_service）
    - UnadjustedMisstatement 创建时（misstatement_service）
    - AuditReport 转 final 时（audit_report_service.update_status / sign_service.order=5）

    Args:
        db: 数据库会话
        obj: 任意带有 bound_dataset_id / dataset_bound_at 字段的 ORM 对象
        project_id: 绑定查询依据的项目
        year: 绑定查询依据的年度

    Returns:
        绑定上的 dataset_id（None 表示无 active dataset）
    """
    from datetime import datetime, timezone

    active_id = await DatasetService.get_active_dataset_id(db, project_id, year)
    if active_id is not None:
        obj.bound_dataset_id = active_id
        obj.dataset_bound_at = datetime.now(timezone.utc)
    return active_id


def bind_to_active_dataset_sync(
    db,
    obj,
    project_id: UUID,
    year: int,
) -> UUID | None:
    """F50 / Sprint 8.19: 同步版本的下游对象绑定工具。

    用于仍使用 sync ``sqlalchemy.orm.Session`` 的老 service（如
    ``consol_disclosure_service``）。行为与 async 版一致：无 active dataset
    时两字段保持 None 不抛异常。
    """
    from datetime import datetime, timezone

    from app.models.dataset_models import DatasetStatus, LedgerDataset

    try:
        result = db.execute(
            sa.select(LedgerDataset.id)
            .where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.year == year,
                LedgerDataset.status == DatasetStatus.active,
            )
            .order_by(
                LedgerDataset.activated_at.desc().nullslast(),
                LedgerDataset.created_at.desc(),
            )
        )
        active_id = result.scalars().first()
    except Exception:
        active_id = None

    if active_id is not None:
        obj.bound_dataset_id = active_id
        obj.dataset_bound_at = datetime.now(timezone.utc)
    return active_id
