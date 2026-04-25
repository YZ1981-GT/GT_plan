"""附注章节裁剪服务

Phase 9 Task 9.27
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.note_trim_models import NoteSectionInstance, NoteTrimScheme
from app.services.note_template_service import NoteTemplateService

logger = logging.getLogger(__name__)


def _extract_basic_info(wizard_state: dict | None) -> dict:
    state = wizard_state or {}
    return (
        state.get("steps", {}).get("basic_info", {}).get("data")
        or state.get("basic_info", {}).get("data")
        or {}
    )


class NoteTrimService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_project_basic_info(self, project_id: UUID) -> dict:
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {}

        template_service = NoteTemplateService()
        wizard_state, _, changed = template_service.backfill_locked_template_snapshot(project.wizard_state)
        if changed:
            project.wizard_state = wizard_state
            await self.db.flush()
        return _extract_basic_info(project.wizard_state)

    async def resolve_template_type(self, project_id: UUID, template_type: str | None) -> str:
        if template_type:
            resolved = template_type
        else:
            basic_info = await self._get_project_basic_info(project_id)
            resolved = basic_info.get("template_type")
            resolved = resolved if isinstance(resolved, str) and resolved else "soe"

        if resolved == "custom":
            await self._load_custom_template(project_id)
        return resolved

    async def get_sections(self, project_id: UUID, template_type: str = "soe") -> list[dict]:
        """获取章节列表（含裁剪状态）"""
        q = (
            sa.select(NoteSectionInstance)
            .where(
                NoteSectionInstance.project_id == project_id,
                NoteSectionInstance.template_type == template_type,
                NoteSectionInstance.is_deleted == False,  # noqa
            )
            .order_by(NoteSectionInstance.sort_order)
        )
        rows = (await self.db.execute(q)).scalars().all()
        sections = await self._load_template_sections(project_id, template_type)

        if template_type == "custom" and rows and self._should_reinitialize(rows, sections):
            for row in rows:
                row.is_deleted = True
            await self.db.flush()
            rows = []

        if not rows and sections:
            rows = await self._init_from_sections(project_id, template_type, sections)

        return [
            {
                "id": str(r.id),
                "section_number": r.section_number,
                "section_title": r.section_title,
                "status": r.status,
                "skip_reason": r.skip_reason,
                "sort_order": r.sort_order,
            }
            for r in rows
        ]

    async def _load_custom_template(self, project_id: UUID) -> dict:
        basic_info = await self._get_project_basic_info(project_id)
        template_service = NoteTemplateService()
        locked_snapshot = template_service.get_locked_template_snapshot(basic_info)
        if locked_snapshot is not None:
            return locked_snapshot

        template_id = basic_info.get("custom_template_id")
        if not template_id:
            logger.warning("project %s has no custom_template_id in wizard_state", project_id)
            raise HTTPException(status_code=400, detail="当前项目未绑定有效的自定义附注模板，请先在项目基本信息中选择")

        template = template_service.get_template(template_id)
        if template is None:
            logger.warning("custom note template %s not found for project %s", template_id, project_id)
            raise HTTPException(status_code=400, detail="当前项目绑定的自定义附注模板不存在或已失效，请重新选择")
        return template

    async def _load_template_sections(self, project_id: UUID, template_type: str) -> list[dict]:
        if template_type == "custom":
            template = await self._load_custom_template(project_id)
            return template.get("sections", [])

        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tmpl_file = data_dir / f"note_template_{template_type}.json"
        if not tmpl_file.exists():
            return []

        tmpl = json.loads(tmpl_file.read_text(encoding="utf-8-sig"))
        return tmpl.get("sections", [])

    def _should_reinitialize(self, rows: list[NoteSectionInstance], sections: list[dict]) -> bool:
        existing = [(row.section_number, row.section_title) for row in rows]
        desired = [
            (section.get("section_number", f"五、{idx + 1}"), section.get("section_title", ""))
            for idx, section in enumerate(sections)
        ]
        return existing != desired

    async def _init_from_template(self, project_id: UUID, template_type: str) -> list[NoteSectionInstance]:
        """从模版初始化章节实例"""
        sections = await self._load_template_sections(project_id, template_type)
        return await self._init_from_sections(project_id, template_type, sections)

    async def _init_from_sections(
        self,
        project_id: UUID,
        template_type: str,
        sections: list[dict],
    ) -> list[NoteSectionInstance]:
        instances = []
        for i, s in enumerate(sections):
            inst = NoteSectionInstance(
                project_id=project_id,
                template_type=template_type,
                section_number=s.get("section_number", f"五、{i+1}"),
                section_title=s.get("section_title", ""),
                sort_order=i * 10,
            )
            self.db.add(inst)
            instances.append(inst)

        await self.db.flush()
        return instances

    async def save_trim(self, project_id: UUID, template_type: str, items: list[dict]) -> int:
        """保存裁剪结果"""
        updated = 0
        for item in items:
            sid = item.get("id")
            if not sid:
                continue
            await self.db.execute(
                sa.update(NoteSectionInstance)
                .where(NoteSectionInstance.id == sid)
                .values(status=item.get("status", "retain"), skip_reason=item.get("skip_reason"))
            )
            updated += 1

        # 保存裁剪方案
        scheme = NoteTrimScheme(
            project_id=project_id,
            template_type=template_type,
            scheme_name=f"附注裁剪-{template_type}-{datetime.now().strftime('%Y%m%d')}",
            trim_data={item["id"]: {"status": item.get("status"), "skip_reason": item.get("skip_reason")} for item in items if item.get("id")},
        )
        self.db.add(scheme)
        await self.db.flush()
        return updated

    async def get_trim_scheme(self, project_id: UUID, template_type: str) -> dict | None:
        q = (
            sa.select(NoteTrimScheme)
            .where(
                NoteTrimScheme.project_id == project_id,
                NoteTrimScheme.template_type == template_type,
                NoteTrimScheme.is_deleted == False,  # noqa
            )
            .order_by(NoteTrimScheme.created_at.desc())
            .limit(1)
        )
        scheme = (await self.db.execute(q)).scalar_one_or_none()
        if not scheme:
            return None
        return {"id": str(scheme.id), "scheme_name": scheme.scheme_name, "trim_data": scheme.trim_data}
