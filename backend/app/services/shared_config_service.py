"""共享配置模板服务

三层共享体系：
1. system（事务所默认）→ 所有项目可见
2. group（集团级）→ 同集团下的子企业项目可见
3. personal（个人级）→ 该用户参与的项目可见

5类配置：report_mapping / account_mapping / formula_config / report_template / workpaper_template
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared_config_models import SharedConfigTemplate, ConfigReference
from app.models.core import Project

logger = logging.getLogger(__name__)


class SharedConfigService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 保存为模板 ──

    async def save_as_template(
        self,
        name: str,
        config_type: str,
        config_data: dict,
        owner_type: str = "personal",
        owner_user_id: UUID | None = None,
        owner_project_id: UUID | None = None,
        description: str = "",
        applicable_standard: str | None = None,
        is_public: bool = False,
        allowed_project_ids: list[UUID] | None = None,
    ) -> SharedConfigTemplate:
        """保存当前配置为共享模板"""
        # 查找同名模板是否已存在（同类型+同所有者）
        q = sa.select(SharedConfigTemplate).where(
            SharedConfigTemplate.config_type == config_type,
            SharedConfigTemplate.owner_type == owner_type,
            SharedConfigTemplate.name == name,
            SharedConfigTemplate.is_deleted == False,
        )
        if owner_user_id:
            q = q.where(SharedConfigTemplate.owner_user_id == owner_user_id)
        if owner_project_id:
            q = q.where(SharedConfigTemplate.owner_project_id == owner_project_id)

        result = await self.db.execute(q)
        existing = result.scalar_one_or_none()

        if existing:
            # 更新已有模板
            existing.config_data = config_data
            existing.config_version = (existing.config_version or 1) + 1
            existing.description = description or existing.description
            existing.applicable_standard = applicable_standard or existing.applicable_standard
            existing.is_public = is_public
            if allowed_project_ids is not None:
                existing.allowed_project_ids = [str(pid) for pid in allowed_project_ids]
            await self.db.flush()
            return existing

        # 获取项目名称（冗余字段）
        project_name = None
        if owner_project_id:
            proj = await self.db.get(Project, owner_project_id)
            if proj:
                project_name = getattr(proj, 'client_name', None) or str(owner_project_id)

        tpl = SharedConfigTemplate(
            name=name,
            description=description,
            config_type=config_type,
            owner_type=owner_type,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            owner_project_name=project_name,
            config_data=config_data,
            applicable_standard=applicable_standard,
            is_public=is_public,
            allowed_project_ids=[str(pid) for pid in (allowed_project_ids or [])],
        )
        self.db.add(tpl)
        await self.db.flush()
        return tpl

    # ── 查询可用模板 ──

    async def list_available_templates(
        self,
        config_type: str,
        user_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> list[SharedConfigTemplate]:
        """查询当前用户/项目可用的模板列表

        可见性规则：
        - system 模板：所有人可见
        - group 模板：同集团项目可见（通过 parent_project_id 判断）
        - personal 模板：本人创建的可见
        - is_public=True 的模板：所有人可见
        """
        q = sa.select(SharedConfigTemplate).where(
            SharedConfigTemplate.config_type == config_type,
            SharedConfigTemplate.is_deleted == False,
        )
        result = await self.db.execute(q)
        all_templates = list(result.scalars().all())

        # 获取当前项目的集团 parent_project_id
        group_project_id = None
        if project_id:
            proj = await self.db.get(Project, project_id)
            if proj:
                group_project_id = getattr(proj, 'parent_project_id', None) or project_id

        visible = []
        for tpl in all_templates:
            # system 和 public 始终可见
            if tpl.owner_type == 'system' or tpl.is_public:
                visible.append(tpl)
                continue
            # personal 模板：本人可见
            if tpl.owner_type == 'personal' and user_id and tpl.owner_user_id == user_id:
                visible.append(tpl)
                continue
            # group 模板：同集团可见
            if tpl.owner_type == 'group' and group_project_id:
                if tpl.owner_project_id == group_project_id or tpl.owner_project_id == project_id:
                    visible.append(tpl)
                    continue
            # allowed_project_ids 白名单
            if project_id and tpl.allowed_project_ids:
                if str(project_id) in tpl.allowed_project_ids:
                    visible.append(tpl)

        return visible

    # ── 引用模板到项目 ──

    async def apply_template(
        self,
        template_id: UUID,
        project_id: UUID,
        user_id: UUID,
    ) -> dict:
        """将模板配置应用到指定项目，返回配置数据"""
        tpl = await self.db.get(SharedConfigTemplate, template_id)
        if not tpl or tpl.is_deleted:
            raise ValueError("模板不存在")

        # 记录引用
        ref = ConfigReference(
            project_id=project_id,
            template_id=template_id,
            config_type=tpl.config_type,
            applied_by=user_id,
        )
        self.db.add(ref)

        # 更新引用统计
        tpl.reference_count = (tpl.reference_count or 0) + 1
        tpl.last_referenced_at = datetime.utcnow()
        await self.db.flush()

        return {
            "config_type": tpl.config_type,
            "config_data": tpl.config_data,
            "template_name": tpl.name,
            "template_version": tpl.config_version,
        }

    # ── 获取模板详情 ──

    async def get_template(self, template_id: UUID) -> SharedConfigTemplate | None:
        tpl = await self.db.get(SharedConfigTemplate, template_id)
        if tpl and not tpl.is_deleted:
            return tpl
        return None

    # ── 删除模板 ──

    async def delete_template(self, template_id: UUID, user_id: UUID) -> bool:
        tpl = await self.db.get(SharedConfigTemplate, template_id)
        if not tpl or tpl.is_deleted:
            return False
        # 只有所有者或 system 类型可删
        if tpl.owner_type == 'personal' and tpl.owner_user_id != user_id:
            raise ValueError("无权删除他人的模板")
        tpl.is_deleted = True
        tpl.deleted_at = datetime.utcnow()
        await self.db.flush()
        return True

    # ── 查询项目的引用历史 ──

    async def list_references(self, project_id: UUID) -> list[dict]:
        q = (
            sa.select(ConfigReference, SharedConfigTemplate.name, SharedConfigTemplate.config_type)
            .join(SharedConfigTemplate, ConfigReference.template_id == SharedConfigTemplate.id)
            .where(ConfigReference.project_id == project_id)
            .order_by(ConfigReference.applied_at.desc())
        )
        result = await self.db.execute(q)
        return [
            {
                "id": str(ref.id),
                "template_name": name,
                "config_type": ct,
                "applied_at": ref.applied_at.isoformat() if ref.applied_at else None,
                "is_customized": ref.is_customized,
            }
            for ref, name, ct in result.all()
        ]
