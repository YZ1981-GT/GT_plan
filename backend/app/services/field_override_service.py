"""统一字段覆盖存储服务

多个底稿模块共享的"系统自动值+用户可覆盖"模式。
scope 区分底稿域（'procedure_table:A1'、'review:A23' 等）。
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_field_override_models import WorkpaperFieldOverride


class FieldOverrideService:
    """统一字段覆盖存储"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(
        self,
        project_id: uuid.UUID,
        year: int,
        scope: str,
        item_key: str,
        field: str,
    ) -> Any | None:
        """获取单个覆盖值，不存在返回 None"""
        stmt = select(WorkpaperFieldOverride.value).where(
            WorkpaperFieldOverride.project_id == project_id,
            WorkpaperFieldOverride.year == year,
            WorkpaperFieldOverride.scope == scope,
            WorkpaperFieldOverride.item_key == item_key,
            WorkpaperFieldOverride.field == field,
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def get_batch(
        self,
        project_id: uuid.UUID,
        year: int,
        scope: str,
    ) -> dict[str, dict[str, Any]]:
        """返回该 scope 下所有覆盖值 {item_key: {field: value}}"""
        stmt = select(WorkpaperFieldOverride).where(
            WorkpaperFieldOverride.project_id == project_id,
            WorkpaperFieldOverride.year == year,
            WorkpaperFieldOverride.scope == scope,
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        batch: dict[str, dict[str, Any]] = {}
        for row in rows:
            batch.setdefault(row.item_key, {})[row.field] = row.value
        return batch

    async def set(
        self,
        project_id: uuid.UUID,
        year: int,
        scope: str,
        item_key: str,
        field: str,
        value: Any,
        user_id: uuid.UUID | None = None,
    ) -> WorkpaperFieldOverride:
        """Upsert 覆盖值"""
        stmt = select(WorkpaperFieldOverride).where(
            WorkpaperFieldOverride.project_id == project_id,
            WorkpaperFieldOverride.year == year,
            WorkpaperFieldOverride.scope == scope,
            WorkpaperFieldOverride.item_key == item_key,
            WorkpaperFieldOverride.field == field,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            existing.updated_by = user_id
            await self.db.flush()
            return existing

        override = WorkpaperFieldOverride(
            project_id=project_id,
            year=year,
            scope=scope,
            item_key=item_key,
            field=field,
            value=value,
            updated_by=user_id,
        )
        self.db.add(override)
        await self.db.flush()
        return override

    @staticmethod
    def merge(auto_values: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        """自动值 + 覆盖值合并（覆盖优先）

        auto_values: {field: auto_value}
        overrides: {field: override_value}
        返回合并后的字典，覆盖值不为 None 时替换自动值。
        """
        merged = dict(auto_values)
        for k, v in overrides.items():
            if v is not None:
                merged[k] = v
        return merged
