"""项目底稿自动生成

Phase 9 Task 9.2: 项目创建时按模板集复制文件到项目目录
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex, WpTemplate, WpTemplateSet

logger = logging.getLogger(__name__)

# 项目底稿存储根目录
STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage" / "projects"


class WorkpaperGeneratorService:
    """项目底稿自动生成服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_from_templates(
        self,
        project_id: UUID,
        template_set_id: UUID | None = None,
        audit_cycles: list[str] | None = None,
        created_by: UUID | None = None,
    ) -> dict:
        """从模板生成项目底稿

        Args:
            project_id: 项目ID
            template_set_id: 模板集ID（可选，不指定则用全量模板）
            audit_cycles: 限定审计循环（可选，如 ["D","E","F"]）
            created_by: 创建人

        Returns: {"generated": N, "skipped": M, "errors": [...]}
        """
        # 确定要使用的模板编号列表
        template_codes: list[str] | None = None
        if template_set_id:
            ts_result = await self.db.execute(
                sa.select(WpTemplateSet).where(WpTemplateSet.id == template_set_id)
            )
            ts = ts_result.scalar_one_or_none()
            if ts and ts.template_codes:
                template_codes = ts.template_codes

        # 查询模板
        q = sa.select(WpTemplate).where(
            WpTemplate.is_deleted == False,  # noqa
            WpTemplate.status == "published",
        )
        if template_codes:
            q = q.where(WpTemplate.template_code.in_(template_codes))
        if audit_cycles:
            q = q.where(WpTemplate.audit_cycle.in_(audit_cycles))

        templates = (await self.db.execute(q.order_by(WpTemplate.template_code))).scalars().all()

        if not templates:
            return {"generated": 0, "skipped": 0, "errors": ["未找到匹配的模板"]}

        # 检查已有底稿（避免重复生成）
        existing_q = sa.select(WpIndex.wp_code).where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa
        )
        existing_codes = set((await self.db.execute(existing_q)).scalars().all())

        # 项目底稿目录
        project_dir = STORAGE_ROOT / str(project_id) / "workpapers"
        project_dir.mkdir(parents=True, exist_ok=True)

        generated = 0
        skipped = 0
        errors: list[str] = []

        for tmpl in templates:
            if tmpl.template_code in existing_codes:
                skipped += 1
                continue

            try:
                src = Path(tmpl.file_path)
                if not src.exists():
                    errors.append(f"{tmpl.template_code}: 源文件不存在 {tmpl.file_path}")
                    continue

                # 复制文件
                dest = project_dir / f"{tmpl.template_code}{src.suffix}"
                shutil.copy2(str(src), str(dest))

                # 创建 wp_index 记录
                wp_idx = WpIndex(
                    project_id=project_id,
                    wp_code=tmpl.template_code,
                    wp_name=tmpl.template_name,
                    audit_cycle=tmpl.audit_cycle,
                )
                self.db.add(wp_idx)
                await self.db.flush()

                # 创建 working_paper 记录
                wp = WorkingPaper(
                    project_id=project_id,
                    wp_index_id=wp_idx.id,
                    file_path=str(dest),
                    source_type="template",
                    status="draft",
                    created_by=created_by,
                )
                self.db.add(wp)
                generated += 1

            except Exception as e:
                errors.append(f"{tmpl.template_code}: {e}")

        if generated > 0:
            await self.db.flush()

        logger.info(f"项目底稿生成: project={project_id}, generated={generated}, skipped={skipped}")
        return {"generated": generated, "skipped": skipped, "errors": errors[:20]}
