"""修复存量 standalone 项目中不应存在的 consolidated_only 附注行（按项目自身模板类型判定）。

用法:
    python backend/scripts/fix/fix_standalone_consolidated_only.py --dry-run
    python backend/scripts/fix/fix_standalone_consolidated_only.py --execute

原因：早期 DisclosureEngine 未过滤 consolidated_only 节，且附注模板里 4 个一级章曾被
错标为 both（见 ``fix_note_chapter_scope.py``）⇒ standalone 项目 DB 中残留合并专属章节
（如 七、本期纳入合并报表 / 十二 母公司财务报表的主要项目附注）。

═══ 🔴 2026-09-30 修两处缺陷（旧版本不得再用） ═══

1. **跨变体误删**：旧版把 soe 与 listed 两份模板的 consolidated_only 章节号**合并成
   一个集合**，再对**所有** standalone 项目按 note_section 匹配。但两版的章号含义不同 ——
   soe「七」= 合并范围的变化（合并专属），listed「七」= 在其他主体中的权益（单体也有）；
   soe「十二」= 母公司章，listed「十二」= 股份支付。实测若按旧版执行，会从 standalone
   **listed** 项目里软删 14 行合法附注，其中「在其他主体中的权益」（正文 1582 字）与
   「股份支付」（1074 字）是用户已有内容。⇒ 改为**按每个项目自己的 template_type**
   取对应模板的集合判定；template_type 为空的项目不猜，直接跳过并计数。
2. **路径失效**：旧版 ``DATA_DIR = parent.parent / "data"`` 解析为 ``backend/scripts/data``
   （不存在）⇒ 两份模板都读不到 ⇒ 集合恒空 ⇒ 脚本对任何库都报「未加载到任何章节」后退出。
   也就是说它**从未真正执行过**（这也是上面那个误删一直没发生的唯一原因）。

修复策略:
1. 按变体读取 ``note_template_{soe|listed}.json`` 中 scope=consolidated_only 的 section_number
   （含 legacy 编号归一后的形式）
2. 查 report_scope 为 standalone 或空（默认视为 standalone）的项目
3. 对每个项目，只用它**自己** template_type 的集合匹配未删除的附注行
4. --dry-run 打印将被软删的行（含正文长度，便于人工确认没有误伤有内容的行）
5. --execute 设置 is_deleted=True（软删，可恢复）
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.note_section_catalog import normalize_section_code

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

#: backend/data（本文件在 backend/scripts/fix/ 下 ⇒ parents[2] = backend）
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
VARIANTS = ("soe", "listed")


def load_consolidated_only_sections() -> dict[str, frozenset[str]]:
    """按变体返回 consolidated_only 的 section_number 集合 ``{"soe": {...}, "listed": {...}}``。

    🔴 必须按变体分开：两版章号含义不同（见模块 docstring 缺陷 1）。
    模板缺失即抛错 —— 读不到判据真源时静默返回空集会让脚本「什么都不做但报成功」。
    """
    out: dict[str, frozenset[str]] = {}
    for template_type in VARIANTS:
        json_path = DATA_DIR / f"note_template_{template_type}.json"
        if not json_path.is_file():
            raise FileNotFoundError(f"附注模板缺失：{json_path}")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        codes: set[str] = set()
        for section in data.get("sections", []):
            if section.get("scope") != "consolidated_only":
                continue
            sn = (section.get("section_number") or "").strip()
            if not sn:
                continue
            codes.add(sn)
            canonical = normalize_section_code(sn, template_type=template_type)
            if canonical != sn:
                codes.add(canonical)
        if not codes:
            raise RuntimeError(f"{json_path.name} 里一个 consolidated_only 章节都没有 —— 判据失效")
        out[template_type] = frozenset(codes)
    return out


def select_rows_to_delete(
    rows: list[tuple], sections_by_variant: dict[str, frozenset[str]]
) -> tuple[list[tuple], int]:
    """纯函数：``rows`` = ``(id, template_type, note_section, ...)``。

    返回 (待删行, 因 template_type 未知而跳过的行数)。只按行所属项目**自己**的变体判定。
    """
    picked: list[tuple] = []
    unknown = 0
    for row in rows:
        template_type = (row[1] or "").strip().lower()
        if template_type not in sections_by_variant:
            unknown += 1
            continue
        if (row[2] or "").strip() in sections_by_variant[template_type]:
            picked.append(row)
    return picked, unknown


async def run(dry_run: bool = True) -> dict:
    """执行修复。返回统计摘要。"""
    sections_by_variant = load_consolidated_only_sections()
    for v, codes in sections_by_variant.items():
        logger.info(f"[{v}] consolidated_only 章节编码 {len(codes)} 个")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    summary = {
        "standalone_projects": 0,
        "affected_rows": 0,
        "deleted_rows": 0,
        "skipped_unknown_template_type": 0,
        "dry_run": dry_run,
        "sections_found": {},
    }

    try:
        async with async_session() as db:
            stmt = (
                select(
                    DisclosureNote.id,
                    Project.template_type,
                    DisclosureNote.note_section,
                    DisclosureNote.section_title,
                    DisclosureNote.project_id,
                    DisclosureNote.year,
                    func.length(func.coalesce(DisclosureNote.text_content, "")),
                )
                .join(Project, Project.id == DisclosureNote.project_id)
                .where(
                    and_(
                        or_(
                            Project.report_scope == "standalone",
                            Project.report_scope.is_(None),
                            Project.report_scope == "",
                        ),
                        DisclosureNote.is_deleted == False,  # noqa: E712
                    )
                )
            )
            rows = (await db.execute(stmt)).all()
            summary["standalone_projects"] = len({r[4] for r in rows})

            picked, unknown = select_rows_to_delete(rows, sections_by_variant)
            summary["affected_rows"] = len(picked)
            summary["skipped_unknown_template_type"] = unknown
            if unknown:
                logger.warning(f"{unknown} 行所属项目 template_type 为空，无法判定口径 → 跳过（不猜）")
            if not picked:
                logger.info("✅ 无需修复：standalone 项目中无 consolidated_only 残留行")
                return summary

            for r in picked:
                key = f"{r[1]}|{r[2]}"
                summary["sections_found"][key] = summary["sections_found"].get(key, 0) + 1
            logger.info(f"发现 {len(picked)} 行需要修复:")
            for key, count in sorted(summary["sections_found"].items()):
                logger.info(f"  {key}: {count} 行")

            if dry_run:
                logger.info("[DRY-RUN] 以下行将被软删除（text_len>0 的行请人工确认）:")
                for r in picked:
                    logger.info(
                        f"  id={r[0]} project={r[4]} {r[1]} section={r[2]} "
                        f"title={r[3]} year={r[5]} text_len={r[6]}"
                    )
                logger.info("使用 --execute 参数实际执行修复")
                return summary

            ids = [r[0] for r in picked]
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.execute(
                update(DisclosureNote)
                .where(DisclosureNote.id.in_(ids))
                .values(is_deleted=True, updated_at=now)
            )
            await db.commit()
            summary["deleted_rows"] = len(ids)
            logger.info(f"✅ 已软删除 {len(ids)} 行 consolidated_only 残留")
            return summary
    finally:
        await engine.dispose()


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
    print(f"  template_type 为空而跳过: {result.get('skipped_unknown_template_type', 0)}")
    if not result.get("dry_run"):
        print(f"  已软删除行数: {result.get('deleted_rows', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
