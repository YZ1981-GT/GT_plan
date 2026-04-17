"""附注章节裁剪服务

Phase 9 Task 9.27
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_trim_models import NoteSectionInstance, NoteTrimScheme

logger = logging.getLogger(__name__)


class NoteTrimService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

        if not rows:
            # 从模版初始化
            rows = await self._init_from_template(project_id, template_type)

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

    async def _init_from_template(self, project_id: UUID, template_type: str) -> list[NoteSectionInstance]:
        """从模版初始化章节实例"""
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tmpl_file = data_dir / f"note_template_{template_type}.json"
        if not tmpl_file.exists():
            return []

        tmpl = json.loads(tmpl_file.read_text(encoding="utf-8-sig"))
        sections = tmpl.get("sections", [])

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
