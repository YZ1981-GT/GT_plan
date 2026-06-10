"""修复存量 standalone 项目中不应存在的 consolidated_only 附注行。

用法:
    python backend/scripts/fix/fix_standalone_consolidated_only.py --dry-run
    python backend/scripts/fix/fix_standalone_consolidated_only.py --execute

原因：早期 DisclosureEngine 未过滤 consolidated_only 节导致
standalone 项目 DB 中残留合并专属章节（如 七、本期纳入合并报表）。

修复策略:
1. 从 note_template_{soe|listed}.json 读取所有 scope=consolidated_only 的 section_number
2. 查 DB 中 report_scope='standalone' (或 NULL/空，默认视为 standalone) 的项目
3. 找这些项目 disclosure_notes 中 note_section 匹配 consolidated_only 清单的行
4. --dry-run: 打印将被软删的行
5. --execute: 设置 is_deleted=True + deleted_at=now()
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update, func, and_, or_, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.note_section_catalog import (
    normalize_section_code,
    load_section_scope_map,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_consolidated_only_sections() -> set[str]:
    """从 JSON 种子文件加载所有 consolidated_only 的 section_number."""
    consolidated_sections: set[str] = set()

    for template_type in ("soe", "listed"):
        json_path = DATA_DIR / f"note_template_{template_type}.json"
        if not json_path.exists():
            logger.warning(f"种子文件不存在: {json_path}")
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        for section in data.get("sections", []):
            if section.get("scope") == "consolidated_only":
                sn = section.get("section_number", "").strip()
                if sn:
                    consolidated_sections.add(sn)
                    # 也加入 legacy 归一后的形式
                    canonical = normalize_section_code(sn, template_type=template_type)
                    if canonical != sn:
                        consolidated_sections.add(canonical)

    return consolidated_sections


async def run(dry_run: bool = True) -> dict:
    """执行修复。返回统计摘要。"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    consolidated_sections = _load_consolidated_only_sections()
    if not consolidated_sections:
        logger.error("未加载到任何 consolidated_only 章节，中止")
        return {"error": "no_sections_loaded"}

    logger.info(f"已加载 {len(consolidated_sections)} 个 consolidated_only 章节编码")

    summary = {
        "standalone_projects": 0,
        "affected_rows": 0,
        "deleted_rows": 0,
        "dry_run": dry_run,
        "sections_found": {},
    }

    async with async_session() as db:
        # 1. 查所有 standalone 项目（report_scope='standalone' 或 NULL/空）
        stmt = select(Project.id, Project.name, Project.report_scope).where(
            or_(
                Project.report_scope == "standalone",
                Project.report_scope.is_(None),
                Project.report_scope == "",
            )
        )
        result = await db.execute(stmt)
        standalone_projects = result.all()
        summary["standalone_projects"] = len(standalone_projects)
        logger.info(f"找到 {len(standalone_projects)} 个 standalone 项目")

        if not standalone_projects:
            logger.info("无 standalone 项目，无需修复")
            await engine.dispose()
            return summary

        project_ids = [p.id for p in standalone_projects]

        # 2. 查这些项目中属于 consolidated_only 的未删除附注行
        stmt = select(
            DisclosureNote.id,
            DisclosureNote.project_id,
            DisclosureNote.note_section,
            DisclosureNote.section_title,
            DisclosureNote.year,
        ).where(
            and_(
                DisclosureNote.project_id.in_(project_ids),
                DisclosureNote.note_section.in_(consolidated_sections),
                DisclosureNote.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        affected_rows = result.all()
        summary["affected_rows"] = len(affected_rows)

        if not affected_rows:
            logger.info("✅ 无需修复：standalone 项目中无 consolidated_only 残留行")
            await engine.dispose()
            return summary

        # 统计各 section 的出现次数
        for row in affected_rows:
            key = row.note_section
            summary["sections_found"][key] = summary["sections_found"].get(key, 0) + 1

        logger.info(f"发现 {len(affected_rows)} 行需要修复:")
        for section, count in sorted(summary["sections_found"].items()):
            logger.info(f"  {section}: {count} 行")

        if dry_run:
            logger.info("\n[DRY-RUN] 以下行将被软删除:")
            for row in affected_rows[:20]:
                logger.info(
                    f"  id={row.id} project={row.project_id} "
                    f"section={row.note_section} title={row.section_title} year={row.year}"
                )
            if len(affected_rows) > 20:
                logger.info(f"  ... 及另外 {len(affected_rows) - 20} 行")
            logger.info("\n使用 --execute 参数实际执行修复")
        else:
            # 3. 软删除
            affected_ids = [row.id for row in affected_rows]
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            stmt = (
                update(DisclosureNote)
                .where(DisclosureNote.id.in_(affected_ids))
                .values(is_deleted=True, updated_at=now)
            )
            await db.execute(stmt)
            await db.commit()
            summary["deleted_rows"] = len(affected_ids)
            logger.info(f"✅ 已软删除 {len(affected_ids)} 行 consolidated_only 残留")

    await engine.dispose()
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="修复 standalone 项目中不应存在的 consolidated_only 附注行"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="仅预览，不执行修改")
    group.add_argument("--execute", action="store_true", help="实际执行软删除")
    args = parser.parse_args()

    result = asyncio.run(run(dry_run=args.dry_run))

    print("\n" + "=" * 60)
    print("修复摘要:")
    print(f"  模式: {'DRY-RUN（预览）' if result.get('dry_run') else '已执行'}")
    print(f"  Standalone 项目数: {result.get('standalone_projects', 0)}")
    print(f"  受影响行数: {result.get('affected_rows', 0)}")
    if not result.get("dry_run"):
        print(f"  已软删除行数: {result.get('deleted_rows', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
