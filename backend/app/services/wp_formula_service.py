"""自定义底稿公式绑定持久化服务（custom-workpaper-formula-binding 组①第三层）。

三层一致第三层：DB 迁移 V052__wp_formula.sql + ORM WpFormula(Mapped[]) + 本 service。

职责：
- save：按 (wp_id, sheet_name, target_cell) 维度 upsert（已存在覆盖更新
  expression/category/description，不存在则新建）。save 前先调用
  ``address_registry.validate_formula_refs`` 校验悬空引用，含 ``not_found``
  项则不写库，返回 issues 列表供 router 转 422（Req 6.4）。
- list_by_wp：列出某 wp_id 的全部公式。
- delete：按 formula_id 删除单条。

工程铁律（遵循 memory）：
- service 只 ``flush`` 不 ``commit``（跨 service 编排由 router 统一 commit 保原子）。
- 全 async（AsyncSession + select/execute async 风格）。
- ``address_registry`` 为模块级单例，直接 import 使用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.address_registry import address_registry

logger = logging.getLogger(__name__)


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    """将 str / UUID 统一为 UUID（容忍已是 UUID 的入参）。"""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class WpFormulaService:
    """自定义底稿公式 CRUD（save / list / delete）。"""

    async def save(
        self,
        db: AsyncSession,
        *,
        project_id: uuid.UUID | str,
        wp_id: uuid.UUID | str,
        sheet_name: str,
        target_cell: str,
        expression: str,
        year: int,
        template_type: str = "soe",
        category: str | None = None,
        description: str | None = None,
        created_by: uuid.UUID | str | None = None,
    ) -> tuple[WpFormula | None, list[dict]]:
        """保存（upsert）一条底稿公式。

        以 (wp_id, sheet_name, target_cell) 为唯一维度：已存在则覆盖更新
        expression/category/description，不存在则新建。

        保存前调用 ``address_registry.validate_formula_refs`` 校验 expression
        中引用的地址是否有效；若含悬空引用（``not_found``），**不写库**，返回
        ``(None, issues)`` 供 router 转 422。校验通过返回 ``(WpFormula, [])``。

        只 flush 不 commit（router 统一 commit）。

        Args:
            db: AsyncSession。
            project_id: 所属项目 id。
            wp_id: 所属底稿 working_paper.id。
            sheet_name: sheet 名称。
            target_cell: 写入目标单元格（如 B5）。
            expression: 公式表达式。
            year: 校验悬空引用所需年度（传给 validate_formula_refs）。
            template_type: 模板类型，默认 'soe'（传给 validate_formula_refs）。
            category: 公式分类（可选）。
            description: 描述（可选）。
            created_by: 创建人 user id（可选，仅新建时写入）。

        Returns:
            (WpFormula, []) 保存成功；(None, issues) 含悬空引用未写库。
        """
        project_uuid = _as_uuid(project_id)
        wp_uuid = _as_uuid(wp_id)
        created_by_uuid = _as_uuid(created_by) if created_by is not None else None

        # ── 悬空引用校验（Req 6.4 / P6）：含 not_found 则不写库 ──
        issues = await address_registry.validate_formula_refs(
            db, str(project_uuid), year, expression, template_type
        )
        if issues:
            logger.info(
                "wp_formula save 拒绝：公式含悬空引用 wp_id=%s cell=%s issues=%d",
                wp_uuid, target_cell, len(issues),
            )
            return None, issues

        # ── upsert：按 (wp_id, sheet_name, target_cell) 维度 ──
        existing = (
            await db.execute(
                sa.select(WpFormula).where(
                    WpFormula.wp_id == wp_uuid,
                    WpFormula.sheet_name == sheet_name,
                    WpFormula.target_cell == target_cell,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.expression = expression
            existing.category = category
            existing.description = description
            existing.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return existing, []

        formula = WpFormula(
            project_id=project_uuid,
            wp_id=wp_uuid,
            sheet_name=sheet_name,
            target_cell=target_cell,
            expression=expression,
            category=category,
            description=description,
            created_by=created_by_uuid,
        )
        db.add(formula)
        await db.flush()
        return formula, []

    async def list_by_wp(
        self, db: AsyncSession, wp_id: uuid.UUID | str
    ) -> list[WpFormula]:
        """列出某底稿的全部公式（按 sheet_name, target_cell 排序）。"""
        wp_uuid = _as_uuid(wp_id)
        result = await db.execute(
            sa.select(WpFormula)
            .where(WpFormula.wp_id == wp_uuid)
            .order_by(WpFormula.sheet_name, WpFormula.target_cell)
        )
        return list(result.scalars().all())

    async def delete(self, db: AsyncSession, formula_id: uuid.UUID | str) -> bool:
        """按 formula_id 删除单条公式。

        只 flush 不 commit（router 统一 commit）。

        Returns:
            True 已删除；False 记录不存在（无操作）。
        """
        formula_uuid = _as_uuid(formula_id)
        obj = (
            await db.execute(
                sa.select(WpFormula).where(WpFormula.id == formula_uuid)
            )
        ).scalar_one_or_none()
        if obj is None:
            return False
        await db.delete(obj)
        await db.flush()
        return True


# 模块级单例（与 address_registry 等保持一致的使用风格）
wp_formula_service = WpFormulaService()
