"""集团模板继承与下发服务

支持将当前项目附注结构保存为集团模板，并下发到子企业项目。
下发策略：A层覆盖 / B/C层保留数据更新结构 / D层合并

Requirements: 52.1-52.7
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


class DistributeStrategy:
    """下发策略枚举"""
    A_OVERWRITE = "a_overwrite"          # A层覆盖
    BC_KEEP_DATA = "bc_keep_data"        # B/C层保留数据更新结构
    D_MERGE = "d_merge"                  # D层合并
    REFERENCE = "reference"              # 参照模式（不强制覆盖）


class NoteGroupTemplateService:
    """集团附注模板服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_as_group_template(
        self,
        project_id: UUID,
        year: int,
        template_name: str,
        created_by: UUID | None = None,
    ) -> dict[str, Any]:
        """将当前项目附注结构保存为集团模板。

        保存内容：章节结构 + 文字模板 + 表格结构 + 校验规则
        """
        template_id = uuid4()
        now = datetime.now(timezone.utc)

        # 获取当前项目附注结构
        result = await self._db.execute(
            text("""
                -- disclosure_notes 的真实列名：section_id / section_title /
                -- text_content / level（原写 section_code / title / content / layer
                -- 全部不存在 ⇒ 本查询从未成功执行过）。用别名保持模板里的键名不变。
                -- validation_status 该表无此维度（校验结果在独立表
                -- note_validation_results），故不再选取；模板消费方按缺键处理。
                SELECT section_id   AS section_code,
                       section_title AS title,
                       level        AS layer,
                       sort_order,
                       text_content AS content,
                       table_data
                FROM disclosure_notes
                WHERE project_id = :pid AND year = :year
                ORDER BY sort_order
            """),
            {"pid": str(project_id), "year": year},
        )
        sections = [dict(r._mapping) for r in result.fetchall()]

        # 序列化模板数据
        template_data = {
            "sections": sections,
            "source_project_id": str(project_id),
            "source_year": year,
        }

        # 存储模板（使用 project wizard_state 作为存储）
        await self._db.execute(
            text("""
                INSERT INTO group_note_templates
                    (id, name, template_data, created_by, created_at)
                VALUES
                    (:id, :name, :data, :created_by, :created_at)
            """),
            {
                "id": str(template_id),
                "name": template_name,
                "data": json.dumps(template_data, default=str, ensure_ascii=False),
                "created_by": str(created_by) if created_by else None,
                "created_at": now,
            },
        )

        logger.info(
            "[GroupTemplate] Saved template '%s' from project %s year %d (%d sections)",
            template_name, project_id, year, len(sections),
        )

        return {
            "template_id": str(template_id),
            "name": template_name,
            "section_count": len(sections),
            "created_at": now.isoformat(),
        }

    async def distribute_template(
        self,
        template_id: UUID,
        target_project_ids: list[UUID],
        strategy: str = DistributeStrategy.BC_KEEP_DATA,
    ) -> dict[str, Any]:
        """将集团模板下发到子企业项目。

        Parameters
        ----------
        template_id : UUID
            集团模板 ID
        target_project_ids : list[UUID]
            目标项目 ID 列表
        strategy : str
            下发策略

        Returns
        -------
        dict
            下发结果摘要
        """
        # 加载模板
        result = await self._db.execute(
            text("SELECT template_data, name FROM group_note_templates WHERE id = :id"),
            {"id": str(template_id)},
        )
        row = result.first()
        if not row:
            return {"error": "Template not found", "distributed": 0}

        template_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        template_name = row[1]

        success_count = 0
        failed_ids: list[str] = []

        for pid in target_project_ids:
            try:
                await self._apply_template_to_project(
                    pid, template_data, strategy
                )
                success_count += 1
            except Exception as e:
                logger.warning("[GroupTemplate] Failed to distribute to %s: %s", pid, e)
                failed_ids.append(str(pid))

        logger.info(
            "[GroupTemplate] Distributed '%s' to %d/%d projects (strategy=%s)",
            template_name, success_count, len(target_project_ids), strategy,
        )

        return {
            "template_id": str(template_id),
            "template_name": template_name,
            "strategy": strategy,
            "total": len(target_project_ids),
            "success": success_count,
            "failed": failed_ids,
        }

    async def _apply_template_to_project(
        self,
        project_id: UUID,
        template_data: dict,
        strategy: str,
    ) -> None:
        """将模板应用到单个项目（按策略处理）。"""
        sections = template_data.get("sections", [])

        for section in sections:
            layer = section.get("layer", "B")

            if strategy == DistributeStrategy.A_OVERWRITE and layer == "A":
                # A层直接覆盖
                await self._upsert_section(project_id, section, overwrite=True)
            elif strategy == DistributeStrategy.BC_KEEP_DATA and layer in ("B", "C"):
                # B/C层保留数据，更新结构
                await self._upsert_section(project_id, section, overwrite=False)
            elif strategy == DistributeStrategy.D_MERGE and layer == "D":
                # D层合并
                await self._upsert_section(project_id, section, overwrite=False)
            elif strategy == DistributeStrategy.REFERENCE:
                # 参照模式：不强制覆盖，仅标记关联
                pass
            else:
                # 默认：更新结构保留数据
                await self._upsert_section(project_id, section, overwrite=False)

    async def _upsert_section(
        self,
        project_id: UUID,
        section: dict,
        overwrite: bool = False,
    ) -> None:
        """插入或更新附注章节。"""
        section_code = section.get("section_code")
        if not section_code:
            return

        # 检查是否已存在
        result = await self._db.execute(
            text("""
                -- 列真名 section_id（无 section_code），绑定参数名保持 :code
                SELECT id FROM disclosure_notes
                WHERE project_id = :pid AND section_id = :code
                LIMIT 1
            """),
            {"pid": str(project_id), "code": section_code},
        )
        existing = result.first()

        if existing and not overwrite:
            # 保留数据，仅更新结构字段
            await self._db.execute(
                text("""
                    -- 列真名：section_id / level（原 section_code / layer 不存在）
                    UPDATE disclosure_notes
                    SET sort_order = :sort_order, level = :layer
                    WHERE project_id = :pid AND section_id = :code
                """),
                {
                    "pid": str(project_id),
                    "code": section_code,
                    "sort_order": section.get("sort_order", 0),
                    "layer": section.get("layer"),
                },
            )
        elif existing and overwrite:
            # 完全覆盖
            await self._db.execute(
                text("""
                    -- 列真名：section_title / text_content / level / section_id
                    UPDATE disclosure_notes
                    SET section_title = :title, text_content = :content,
                        table_data = :table_data, sort_order = :sort_order,
                        level = :layer
                    WHERE project_id = :pid AND section_id = :code
                """),
                {
                    "pid": str(project_id),
                    "code": section_code,
                    "title": section.get("title"),
                    "content": section.get("content"),
                    "table_data": json.dumps(section.get("table_data"), default=str)
                    if section.get("table_data") else None,
                    "sort_order": section.get("sort_order", 0),
                    "layer": section.get("layer"),
                },
            )

    async def detach_from_group_template(
        self,
        project_id: UUID,
    ) -> dict[str, Any]:
        """将项目从集团模板脱离。

        脱离后项目附注结构独立维护，不再接收集团模板更新。
        """
        # 清除项目的集团模板关联标记
        await self._db.execute(
            text("""
                UPDATE projects
                SET wizard_state = jsonb_set(
                    COALESCE(wizard_state, '{}'),
                    '{group_template_id}',
                    'null'
                )
                WHERE id = :pid
            """),
            {"pid": str(project_id)},
        )

        logger.info("[GroupTemplate] Project %s detached from group template", project_id)

        return {
            "project_id": str(project_id),
            "detached": True,
            "detached_at": datetime.now(timezone.utc).isoformat(),
        }

    async def list_templates(self) -> list[dict[str, Any]]:
        """列出所有集团模板。"""
        result = await self._db.execute(
            text("SELECT id, name, created_at FROM group_note_templates ORDER BY created_at DESC")
        )
        return [
            {"id": str(r[0]), "name": r[1], "created_at": str(r[2])}
            for r in result.fetchall()
        ]
