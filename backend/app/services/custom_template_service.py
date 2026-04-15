"""用户自定义底稿模板服务

功能：
- 创建/更新/删除自定义模板
- 模板发布（共享给其他用户）
- 模板市场（查看已发布模板）
- 模板版本管理
- 模板分类（行业专用/客户专用/个人收藏）
- 模板验证（公式语法+区域定义）

Validates: Requirements 4.1-4.6
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import WpTemplateCustom


# 取数公式正则（用于验证）
FORMULA_PATTERN = re.compile(
    r"=(TB|WP|AUX|PREV|SUM_TB)\s*\(", re.IGNORECASE
)


class CustomTemplateService:

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_template(
        self, db: AsyncSession, user_id: UUID, data: dict[str, Any],
    ) -> dict:
        """创建自定义模板"""
        tpl = WpTemplateCustom(
            user_id=user_id,
            template_name=data["template_name"],
            category=data.get("category", "personal"),
            template_file_path=data["template_file_path"],
            version=data.get("version", "1.0"),
            description=data.get("description"),
        )
        db.add(tpl)
        await db.flush()
        return self._to_dict(tpl)

    async def update_template(
        self, db: AsyncSession, template_id: UUID, user_id: UUID, data: dict[str, Any],
    ) -> dict:
        """更新模板（仅所有者可更新）"""
        tpl = await self._get_owned(db, template_id, user_id)
        if not tpl:
            raise ValueError("模板不存在或无权限")

        for key in ("template_name", "category", "template_file_path", "description"):
            if key in data:
                setattr(tpl, key, data[key])
        await db.flush()
        return self._to_dict(tpl)

    async def delete_template(
        self, db: AsyncSession, template_id: UUID, user_id: UUID,
    ) -> bool:
        """软删除模板"""
        tpl = await self._get_owned(db, template_id, user_id)
        if not tpl:
            raise ValueError("模板不存在或无权限")
        tpl.soft_delete()
        await db.flush()
        return True

    async def get_template(self, db: AsyncSession, template_id: UUID) -> dict | None:
        """获取模板详情"""
        result = await db.execute(
            sa.select(WpTemplateCustom).where(
                WpTemplateCustom.id == template_id,
                WpTemplateCustom.is_deleted == sa.false(),
            )
        )
        tpl = result.scalar_one_or_none()
        return self._to_dict(tpl) if tpl else None

    # ------------------------------------------------------------------
    # 列表与搜索
    # ------------------------------------------------------------------

    async def list_my_templates(
        self, db: AsyncSession, user_id: UUID,
        category: str | None = None,
    ) -> list[dict]:
        """我的模板列表"""
        stmt = (
            sa.select(WpTemplateCustom)
            .where(
                WpTemplateCustom.user_id == user_id,
                WpTemplateCustom.is_deleted == sa.false(),
            )
            .order_by(WpTemplateCustom.updated_at.desc())
        )
        if category:
            stmt = stmt.where(WpTemplateCustom.category == category)
        result = await db.execute(stmt)
        return [self._to_dict(t) for t in result.scalars().all()]

    async def list_market(
        self, db: AsyncSession, category: str | None = None,
    ) -> list[dict]:
        """模板市场（已发布的模板）"""
        stmt = (
            sa.select(WpTemplateCustom)
            .where(
                WpTemplateCustom.is_published == sa.true(),
                WpTemplateCustom.is_deleted == sa.false(),
            )
            .order_by(WpTemplateCustom.updated_at.desc())
        )
        if category:
            stmt = stmt.where(WpTemplateCustom.category == category)
        result = await db.execute(stmt)
        return [self._to_dict(t) for t in result.scalars().all()]

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------

    async def publish_template(
        self, db: AsyncSession, template_id: UUID, user_id: UUID,
    ) -> dict:
        """发布模板到市场"""
        tpl = await self._get_owned(db, template_id, user_id)
        if not tpl:
            raise ValueError("模板不存在或无权限")
        tpl.is_published = True
        await db.flush()
        return self._to_dict(tpl)

    async def unpublish_template(
        self, db: AsyncSession, template_id: UUID, user_id: UUID,
    ) -> dict:
        """取消发布"""
        tpl = await self._get_owned(db, template_id, user_id)
        if not tpl:
            raise ValueError("模板不存在或无权限")
        tpl.is_published = False
        await db.flush()
        return self._to_dict(tpl)

    # ------------------------------------------------------------------
    # 版本管理
    # ------------------------------------------------------------------

    async def create_version(
        self, db: AsyncSession, template_id: UUID, user_id: UUID,
        new_version: str, file_path: str,
    ) -> dict:
        """创建新版本（复制为新记录，版本号递增）"""
        tpl = await self._get_owned(db, template_id, user_id)
        if not tpl:
            raise ValueError("模板不存在或无权限")

        new_tpl = WpTemplateCustom(
            user_id=user_id,
            template_name=tpl.template_name,
            category=tpl.category,
            template_file_path=file_path,
            version=new_version,
            description=tpl.description,
            is_published=False,
        )
        db.add(new_tpl)
        await db.flush()
        return self._to_dict(new_tpl)

    # ------------------------------------------------------------------
    # 验证
    # ------------------------------------------------------------------

    async def validate_template(self, file_content: str | None = None) -> dict:
        """验证模板（公式语法检查）

        实际场景中会用 openpyxl 解析 .xlsx 文件检查 Named Ranges 和公式语法。
        这里做简化版：检查公式文本中的取数公式语法是否合法。
        """
        issues: list[dict] = []

        if not file_content:
            return {"valid": True, "issues": [], "message": "无内容需要验证"}

        # 检查公式语法
        formulas = FORMULA_PATTERN.findall(file_content)
        if not formulas:
            issues.append({
                "type": "warning",
                "message": "未检测到取数公式（TB/WP/AUX/PREV/SUM_TB）",
            })

        # 检查括号匹配
        open_count = file_content.count("(")
        close_count = file_content.count(")")
        if open_count != close_count:
            issues.append({
                "type": "error",
                "message": f"括号不匹配：左括号 {open_count} 个，右括号 {close_count} 个",
            })

        valid = not any(i["type"] == "error" for i in issues)
        return {
            "valid": valid,
            "issues": issues,
            "formula_count": len(formulas),
            "message": "验证通过" if valid else "存在错误，请修正",
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    async def _get_owned(
        self, db: AsyncSession, template_id: UUID, user_id: UUID,
    ) -> WpTemplateCustom | None:
        result = await db.execute(
            sa.select(WpTemplateCustom).where(
                WpTemplateCustom.id == template_id,
                WpTemplateCustom.user_id == user_id,
                WpTemplateCustom.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    def _to_dict(self, tpl: WpTemplateCustom) -> dict:
        return {
            "id": str(tpl.id),
            "user_id": str(tpl.user_id),
            "template_name": tpl.template_name,
            "category": tpl.category,
            "template_file_path": tpl.template_file_path,
            "is_published": tpl.is_published,
            "version": tpl.version,
            "description": tpl.description,
            "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
            "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
        }
