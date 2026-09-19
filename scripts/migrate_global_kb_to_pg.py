"""
Migration Script: 全局知识库文件系统 → PostgreSQL

扫描 ~/.gt_audit_helper/knowledge/{category}/ 每个文件，
幂等创建文档到对应 preset folder，触发索引流水线。

用法:
  python scripts/migrate_global_kb_to_pg.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 9 个全局知识库分类
CATEGORIES = [
    "workpaper_templates",
    "regulations",
    "accounting_standards",
    "quality_control",
    "audit_procedures",
    "industry_guides",
    "prompts",
    "report_templates",
    "notes",
]

GLOBAL_ROOT = Path.home() / ".gt_audit_helper" / "knowledge"


async def migrate(dry_run: bool = False) -> dict:
    """执行迁移。返回统计结果。"""
    from app.core.database import async_session
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
    from app.services.knowledge_folder_service import KnowledgeDocumentService
    from app.services.indexing_pipeline import run_indexing_pipeline
    from app.routers.knowledge_base import _get_or_create_preset_folder
    import sqlalchemy as sa

    stats = {"scanned": 0, "created": 0, "skipped": 0, "errors": 0, "indexed": 0}

    async with async_session() as db:
        for category in CATEGORIES:
            category_dir = GLOBAL_ROOT / category
            if not category_dir.exists():
                logger.info(f"[{category}] directory not found, skip")
                continue

            # 获取或创建 preset folder
            folder = await _get_or_create_preset_folder(db, category)
            logger.info(f"[{category}] folder_id={folder.id}")

            for file_path in sorted(category_dir.iterdir()):
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue

                stats["scanned"] += 1
                filename = file_path.name

                # 幂等检查: (folder_id, filename) 已存在?
                existing = await db.execute(
                    sa.select(KnowledgeDocument.id, KnowledgeDocument.version).where(
                        KnowledgeDocument.folder_id == folder.id,
                        KnowledgeDocument.name == filename,
                        KnowledgeDocument.is_deleted == sa.false(),
                    )
                )
                row = existing.one_or_none()

                if row:
                    # 已存在 → version increment (幂等: 重复运行只增版本不重复)
                    doc_id, current_version = row
                    if dry_run:
                        logger.info(f"  [DRY-RUN] would increment version: {filename} (v{current_version}→v{current_version + 1})")
                        stats["skipped"] += 1
                        continue

                    await db.execute(
                        sa.update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == doc_id)
                        .values(version=current_version + 1)
                    )
                    stats["skipped"] += 1
                    logger.info(f"  [SKIP] already exists: {filename} (v{current_version})")
                    continue

                if dry_run:
                    logger.info(f"  [DRY-RUN] would create: {filename}")
                    stats["created"] += 1
                    continue

                # 创建文档记录
                try:
                    file_size = file_path.stat().st_size
                    svc = KnowledgeDocumentService(db)
                    doc = await svc.create_document(
                        folder_id=folder.id,
                        name=filename,
                        storage_path=str(file_path),
                        file_size=file_size,
                        file_type=filename.rsplit(".", 1)[-1] if "." in filename else None,
                        created_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # system user
                    )
                    stats["created"] += 1
                    logger.info(f"  [CREATE] {filename} → doc_id={doc.id}")

                    # 触发索引
                    try:
                        await run_indexing_pipeline(doc.id)
                        stats["indexed"] += 1
                    except Exception as e:
                        logger.warning(f"  [INDEX-FAIL] {filename}: {e}")

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(f"  [ERROR] {filename}: {e}")

        await db.commit()

    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("=== DRY RUN MODE (no changes) ===")

    logger.info(f"Scanning: {GLOBAL_ROOT}")
    stats = asyncio.run(migrate(dry_run=dry_run))

    logger.info("=== Migration Complete ===")
    logger.info(f"  Scanned: {stats['scanned']}")
    logger.info(f"  Created: {stats['created']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info(f"  Indexed: {stats['indexed']}")
    logger.info(f"  Errors:  {stats['errors']}")


if __name__ == "__main__":
    main()
