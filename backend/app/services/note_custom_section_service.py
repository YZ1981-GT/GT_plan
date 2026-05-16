"""附注章节模板可扩展性服务

支持自定义章节创建、保存为模板、从模板库应用到项目。

Requirements: 49.1-49.8
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NoteCustomSectionService:
    """附注自定义章节服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_custom_section(
        self,
        project_id: UUID,
        year: int,
        section_type: str,
        title: str,
        content: str | None = None,
        table_structure: dict | None = None,
    ) -> dict[str, Any]:
        """创建自定义附注章节。

        Parameters
        ----------
        section_type : str
            章节类型：text / table / mixed
        title : str
            章节标题
        content : str, optional
            文字内容
        table_structure : dict, optional
            表格结构定义
        """
        section_id = uuid4()
        now = datetime.now(timezone.utc)

        # 获取当前最大 sort_order
        result = await self._db.execute(
            text("""
                SELECT COALESCE(MAX(sort_order), 0) + 1
                FROM disclosure_notes
                WHERE project_id = :pid AND year = :year
            """),
            {"pid": str(project_id), "year": year},
        )
        next_order = result.scalar() or 1

        # 生成 section_code
        section_code = f"CUSTOM-{str(section_id)[:8].upper()}"

        await self._db.execute(
            text("""
                INSERT INTO disclosure_notes
                    (id, project_id, year, section_code, title, content,
                     table_data, sort_order, is_custom, layer, created_at)
                VALUES
                    (:id, :pid, :year, :code, :title, :content,
                     :table_data, :sort_order, :is_custom, :layer, :now)
            """),
            {
                "id": str(section_id),
                "pid": str(project_id),
                "year": year,
                "code": section_code,
                "title": title,
                "content": content,
                "table_data": json.dumps(table_structure, ensure_ascii=False)
                if table_structure else None,
                "sort_order": next_order,
                "is_custom": True,
                "layer": "D",  # 自定义章节默认 D 层
                "now": now,
            },
        )

        logger.info(
            "[CustomSection] Created: %s (%s) in project %s",
            title, section_type, project_id,
        )

        return {
            "section_id": str(section_id),
            "section_code": section_code,
            "title": title,
            "section_type": section_type,
            "sort_order": next_order,
            "created_at": now.isoformat(),
        }

    async def save_as_template(
        self,
        section_id: UUID,
        template_name: str | None = None,
    ) -> dict[str, Any]:
        """将自定义章节保存到模板库供其他项目复用。"""
        # 获取章节数据
        result = await self._db.execute(
            text("""
                SELECT section_code, title, content, table_data, layer
                FROM disclosure_notes
                WHERE id = :id
            """),
            {"id": str(section_id)},
        )
        section = result.mappings().first()
        if not section:
            return {"error": "Section not found"}

        template_id = uuid4()
        now = datetime.now(timezone.utc)
        name = template_name or section["title"]

        template_data = {
            "title": section["title"],
            "content": section["content"],
            "table_data": section["table_data"],
            "layer": section["layer"],
            "source_section_code": section["section_code"],
        }

        await self._db.execute(
            text("""
                INSERT INTO note_section_templates
                    (id, name, template_data, created_at)
                VALUES
                    (:id, :name, :data, :now)
            """),
            {
                "id": str(template_id),
                "name": name,
                "data": json.dumps(template_data, default=str, ensure_ascii=False),
                "now": now,
            },
        )

        logger.info("[CustomSection] Saved as template: %s (%s)", name, template_id)

        return {
            "template_id": str(template_id),
            "name": name,
            "created_at": now.isoformat(),
        }

    async def apply_template(
        self,
        project_id: UUID,
        year: int,
        template_id: UUID,
    ) -> dict[str, Any]:
        """从模板库应用模板到项目。"""
        # 加载模板
        result = await self._db.execute(
            text("SELECT name, template_data FROM note_section_templates WHERE id = :id"),
            {"id": str(template_id)},
        )
        row = result.first()
        if not row:
            return {"error": "Template not found"}

        template_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]

        # 创建章节
        section_result = await self.create_custom_section(
            project_id=project_id,
            year=year,
            section_type="mixed",
            title=template_data.get("title", row[0]),
            content=template_data.get("content"),
            table_structure=template_data.get("table_data"),
        )

        logger.info(
            "[CustomSection] Applied template %s to project %s",
            template_id, project_id,
        )

        return {
            "applied": True,
            "template_id": str(template_id),
            "section": section_result,
        }

    async def list_templates(self) -> list[dict[str, Any]]:
        """列出所有章节模板。"""
        result = await self._db.execute(
            text("SELECT id, name, created_at FROM note_section_templates ORDER BY created_at DESC")
        )
        return [
            {"template_id": str(r[0]), "name": r[1], "created_at": str(r[2])}
            for r in result.fetchall()
        ]
