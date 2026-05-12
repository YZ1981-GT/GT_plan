"""模板库三层体系服务

核心能力：
1. 事务所默认模板管理（初始化/列表/详情）
2. 集团定制模板（从事务所模板派生/修订/列表）
3. 项目模板选择（选择模板源/拉取到项目/联动状态）
4. 模板与数据联动（四表/调整/附件的溯源关系）
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template_library_models import (
    ProjectTemplateSelection,
    TemplateLevel,
    TemplateLibraryItem,
    TemplateType,
)

logger = logging.getLogger(__name__)


class TemplateLibraryService:
    """模板库管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ═══ 第一层：事务所默认模板 ═══

    async def list_firm_templates(
        self, template_type: TemplateType | None = None
    ) -> list[TemplateLibraryItem]:
        """列出事务所默认模板"""
        query = sa.select(TemplateLibraryItem).where(
            TemplateLibraryItem.level == TemplateLevel.firm_default,
            TemplateLibraryItem.is_deleted == sa.false(),
        )
        if template_type:
            query = query.where(TemplateLibraryItem.template_type == template_type)
        result = await self.db.execute(query.order_by(TemplateLibraryItem.name))
        return list(result.scalars().all())

    async def register_firm_template(
        self,
        name: str,
        template_type: TemplateType,
        file_path: str | None = None,
        wp_code: str | None = None,
        audit_cycle: str | None = None,
        account_codes: list[str] | None = None,
        report_scope: str | None = None,
        description: str | None = None,
    ) -> TemplateLibraryItem:
        """注册事务所默认模板"""
        item = TemplateLibraryItem(
            id=uuid.uuid4(),
            name=name,
            template_type=template_type,
            level=TemplateLevel.firm_default,
            file_path=file_path,
            wp_code=wp_code,
            audit_cycle=audit_cycle,
            account_codes=account_codes,
            report_scope=report_scope,
            description=description,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    # ═══ 第二层：集团定制模板 ═══

    async def create_group_template(
        self,
        source_template_id: UUID,
        group_id: UUID,
        group_name: str,
        customizations: dict | None = None,
        created_by: UUID | None = None,
    ) -> TemplateLibraryItem:
        """从事务所模板派生集团定制模板"""
        # 加载源模板
        source = await self.db.execute(
            sa.select(TemplateLibraryItem).where(TemplateLibraryItem.id == source_template_id)
        )
        src = source.scalar_one_or_none()
        if not src:
            raise ValueError("源模板不存在")

        # 复制为集团定制版
        item = TemplateLibraryItem(
            id=uuid.uuid4(),
            name=f"{src.name}（{group_name}定制版）",
            template_type=src.template_type,
            level=TemplateLevel.group_custom,
            group_id=group_id,
            group_name=group_name,
            source_template_id=source_template_id,
            version="1.0",
            file_path=src.file_path,  # 初始指向同一文件，修订后指向新文件
            wp_code=src.wp_code,
            audit_cycle=src.audit_cycle,
            account_codes=src.account_codes,
            report_scope=src.report_scope,
            description=src.description,
            created_by=created_by,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_group_templates(
        self, group_id: UUID, template_type: TemplateType | None = None
    ) -> list[TemplateLibraryItem]:
        """列出集团定制模板"""
        query = sa.select(TemplateLibraryItem).where(
            TemplateLibraryItem.level == TemplateLevel.group_custom,
            TemplateLibraryItem.group_id == group_id,
            TemplateLibraryItem.is_deleted == sa.false(),
        )
        if template_type:
            query = query.where(TemplateLibraryItem.template_type == template_type)
        result = await self.db.execute(query.order_by(TemplateLibraryItem.name))
        return list(result.scalars().all())

    # ═══ 第三层：项目模板选择与拉取 ═══

    async def select_template_for_project(
        self,
        project_id: UUID,
        template_id: UUID,
        selected_by: UUID | None = None,
    ) -> ProjectTemplateSelection:
        """为项目选择模板（从事务所默认或集团定制中选）"""
        from datetime import datetime, timezone

        # 加载模板信息
        tmpl = await self.db.execute(
            sa.select(TemplateLibraryItem).where(TemplateLibraryItem.id == template_id)
        )
        template = tmpl.scalar_one_or_none()
        if not template:
            raise ValueError("模板不存在")

        # 检查是否已选择同类型模板
        existing = await self.db.execute(
            sa.select(ProjectTemplateSelection).where(
                ProjectTemplateSelection.project_id == project_id,
                ProjectTemplateSelection.template_type == template.template_type,
                ProjectTemplateSelection.is_active == sa.true(),
            )
        )
        old = existing.scalar_one_or_none()
        if old:
            old.is_active = False  # 取消旧选择

        # 创建新选择
        selection = ProjectTemplateSelection(
            id=uuid.uuid4(),
            project_id=project_id,
            template_id=template_id,
            template_type=template.template_type,
            pulled_at=datetime.now(timezone.utc),
            selected_by=selected_by,
        )
        self.db.add(selection)
        await self.db.flush()
        return selection

    async def get_project_templates(self, project_id: UUID) -> list[dict]:
        """获取项目已选择的模板列表"""
        result = await self.db.execute(
            sa.select(ProjectTemplateSelection, TemplateLibraryItem)
            .join(TemplateLibraryItem, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
            .where(
                ProjectTemplateSelection.project_id == project_id,
                ProjectTemplateSelection.is_active == sa.true(),
            )
        )
        rows = result.all()
        return [
            {
                "selection_id": str(sel.id),
                "template_id": str(tmpl.id),
                "template_name": tmpl.name,
                "template_type": tmpl.template_type.value,
                "level": tmpl.level.value,
                "group_name": tmpl.group_name,
                "wp_code": tmpl.wp_code,
                "report_scope": tmpl.report_scope,
                "pulled_at": sel.pulled_at.isoformat() if sel.pulled_at else None,
                "linked_trial_balance": sel.linked_trial_balance,
                "linked_adjustments": sel.linked_adjustments,
                "linked_attachments": sel.linked_attachments,
            }
            for sel, tmpl in rows
        ]

    async def pull_template_to_project(
        self,
        project_id: UUID,
        template_id: UUID,
        storage_root: str = "./storage",
    ) -> dict:
        """将模板文件拉取到项目目录

        复制模板文件到 storage/projects/{project_id}/templates/
        """
        tmpl = await self.db.execute(
            sa.select(TemplateLibraryItem).where(TemplateLibraryItem.id == template_id)
        )
        template = tmpl.scalar_one_or_none()
        if not template or not template.file_path:
            return {"error": "模板文件不存在"}

        source_path = Path(template.file_path)
        if not source_path.exists():
            return {"error": f"模板文件不存在: {template.file_path}"}

        # 复制到项目目录
        target_dir = Path(storage_root) / "projects" / str(project_id) / "templates"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
        shutil.copy2(source_path, target_path)

        return {
            "template_name": template.name,
            "target_path": str(target_path),
            "file_size": target_path.stat().st_size,
        }

    # ═══ 可用模板列表（供前端选择器使用） ═══

    async def get_available_templates(
        self,
        project_id: UUID | None = None,
        group_id: UUID | None = None,
        template_type: TemplateType | None = None,
    ) -> list[dict]:
        """获取可用模板列表（事务所默认 + 集团定制）

        供前端模板选择器使用，用户从中选择要应用到项目的模板。
        """
        templates = []

        # 事务所默认模板
        firm = await self.list_firm_templates(template_type)
        for t in firm:
            templates.append({
                "id": str(t.id),
                "name": t.name,
                "type": t.template_type.value,
                "level": "firm_default",
                "level_label": "事务所默认",
                "wp_code": t.wp_code,
                "audit_cycle": t.audit_cycle,
                "report_scope": t.report_scope,
                "description": t.description,
            })

        # 集团定制模板
        if group_id:
            group = await self.list_group_templates(group_id, template_type)
            for t in group:
                templates.append({
                    "id": str(t.id),
                    "name": t.name,
                    "type": t.template_type.value,
                    "level": "group_custom",
                    "level_label": f"{t.group_name}定制",
                    "wp_code": t.wp_code,
                    "audit_cycle": t.audit_cycle,
                    "report_scope": t.report_scope,
                    "description": t.description,
                })

        return templates
