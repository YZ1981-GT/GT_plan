"""存量迁移：把 disclosure_notes.text_content 残留的 ### 标题行清理 + per-table guidance 归位。

Feature: note-per-table-guidance (Phase 3 / R4)

针对 174 条 `text_content LIKE '%###%'` 的旧存量附注：
  - 复用生产 `classify_template_content`（保证迁移规则 == 生成规则，杜绝漂移）
  - 标题行（###/（N）/匹配表名）→ 移除 + 推进游标
  - 紧跟的提示段 → 移入对应 `_tables[idx].guidance`
  - 实质正文 → 保留在 text_content
  - 无法归属（单表/无表）的提示 → 章节级 guidance_text
  - 原 text_content 备份到 `_tables[0]._orig_text_content`（rollback 用）

用法（dry-run 默认，不写库）：
  python -m backend.scripts.fix.fix_note_per_table_guidance
  python -m backend.scripts.fix.fix_note_per_table_guidance --project-id <uuid>
  python -m backend.scripts.fix.fix_note_per_table_guidance --project-id <uuid> --execute

铁律：
  - 一律先 dry-run 核对，再 --execute。
  - 实际写库走 savepoint 事务（begin_nested）+ 验证后 commit。
  - 幂等：已迁移的行（_tables[0] 已含 _orig_text_content）跳过，按行自带备份天然
    支持多项目独立迁移（无整表 backup 检查阻塞第二个项目）。
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

# Ensure backend app importable when run as a script
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402
from app.services.disclosure_engine import (  # noqa: E402
    _flatten_paragraphs,
    _is_table_title_paragraph,
    classify_template_content,
    is_guidance_paragraph,
)

logger = logging.getLogger(__name__)

# 行内备份字段名（存于 _tables[0]，rollback 时还原 text_content）
ORIG_BACKUP_KEY = "_orig_text_content"


@dataclass
class SectionPlan:
    """单章节迁移计划（纯逻辑产物，dry-run 打印 + execute 应用共用）。"""

    note_section: str = ""
    orig_text_content: str = ""
    new_text_content: str | None = None
    section_guidance: str | None = None
    # idx -> (table_name, guidance_str)
    per_table_guidance: dict[int, tuple[str, str]] = field(default_factory=dict)
    title_rows_removed: list[str] = field(default_factory=list)
    table_names: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return (
            self.new_text_content != self.orig_text_content
            or bool(self.per_table_guidance)
            or bool(self.section_guidance)
            or bool(self.title_rows_removed)
        )


def plan_section_changes(row: dict[str, Any]) -> SectionPlan:
    """纯函数：基于一行 disclosure_note 计算迁移计划。

    入参 row 至少含 `text_content`(str|None) 与 `table_data`(dict|None)。
    复用生产 `classify_template_content` 产出权威结果（substantive / section_guidance /
    per_table_guidance），另用同套谓词函数 `_is_table_title_paragraph` 仅为 dry-run
    诊断列出"将被移除的标题行"。两者均复用生产代码，不重写规则。
    """
    text_content = row.get("text_content") or ""
    table_data = row.get("table_data") or {}
    tables = table_data.get("_tables") or []
    table_names = [(t.get("name") or "").strip() for t in tables]

    # 权威分类（与附注生成同一套规则）
    substantive, section_guidance, per_table = classify_template_content(
        [text_content], None, tables
    )

    # 诊断：将被移除的标题行（复用生产谓词，不重写规则）
    paragraphs = _flatten_paragraphs([text_content], None)
    title_rows = [
        p
        for p in paragraphs
        if not is_guidance_paragraph(p) and _is_table_title_paragraph(p)
    ]

    per_table_named: dict[int, tuple[str, str]] = {}
    for idx, g in per_table.items():
        name = table_names[idx] if 0 <= idx < len(table_names) else f"#{idx}"
        per_table_named[idx] = (name, g)

    return SectionPlan(
        note_section=str(row.get("note_section") or ""),
        orig_text_content=text_content,
        new_text_content=substantive,
        section_guidance=section_guidance,
        per_table_guidance=per_table_named,
        title_rows_removed=title_rows,
        table_names=table_names,
    )


def apply_plan_to_table_data(
    table_data: dict[str, Any], plan: SectionPlan
) -> dict[str, Any]:
    """把迁移计划写进 table_data（_tables[idx].guidance + _tables[0] 备份）。

    纯函数，返回修改后的 table_data（原地修改并返回，便于 SQLAlchemy JSONB 重新赋值）。
    """
    tables = table_data.get("_tables")
    if not isinstance(tables, list) or not tables:
        # 无 _tables 结构则无处写 per-table guidance，至少保留备份
        return table_data

    # 行内备份原 text_content（幂等：已备份则不覆盖）
    if ORIG_BACKUP_KEY not in tables[0]:
        tables[0][ORIG_BACKUP_KEY] = plan.orig_text_content

    for idx, (_name, guidance) in plan.per_table_guidance.items():
        if 0 <= idx < len(tables) and guidance:
            tables[idx]["guidance"] = guidance

    return table_data


def _already_migrated(table_data: dict[str, Any] | None) -> bool:
    tables = (table_data or {}).get("_tables")
    return bool(
        isinstance(tables, list) and tables and ORIG_BACKUP_KEY in tables[0]
    )


def _print_plan(plan: SectionPlan) -> None:
    print(f"\n[{plan.note_section}]  表格: {plan.table_names or '（无 _tables）'}")
    if plan.title_rows_removed:
        print("  将移除的标题行:")
        for t in plan.title_rows_removed:
            print(f"    - {t!r}")
    else:
        print("  将移除的标题行: （无）")
    if plan.per_table_guidance:
        print("  per-table guidance 分配:")
        for idx, (name, g) in sorted(plan.per_table_guidance.items()):
            print(f"    _tables[{idx}] ({name}).guidance = {g!r}")
    else:
        print("  per-table guidance 分配: （无）")
    if plan.section_guidance:
        print(f"  章节级 guidance_text(降级) = {plan.section_guidance!r}")
    print(f"  保留 text_content = {plan.new_text_content!r}")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL") or str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _connect_args() -> dict[str, Any]:
    # 与 database.py 一致：无 TLS 部署显式禁 asyncpg SSL 协商（Windows 握手稳定性）
    if "asyncpg" in _database_url() and getattr(settings, "DB_DISABLE_SSL", False):
        return {"ssl": False}
    return {}


def _project_filter(project_id: str | None):
    if not project_id or project_id == "all":
        return None
    return UUID(project_id)


async def _load_target_notes(
    session: AsyncSession, project_id: str | None
) -> list[DisclosureNote]:
    """加载 text_content 含 '###' 的存量章节（按 project 限定）。"""
    pid = _project_filter(project_id)
    stmt = select(DisclosureNote).where(
        DisclosureNote.is_deleted == False,  # noqa: E712
        DisclosureNote.text_content.isnot(None),
        DisclosureNote.text_content.like("%###%"),
    )
    if pid is not None:
        stmt = stmt.where(DisclosureNote.project_id == pid)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def run_dry_run(session: AsyncSession, project_id: str | None) -> None:
    notes = await _load_target_notes(session, project_id)
    print(
        f"DRY-RUN 范围: project={project_id or 'all'}, "
        f"text_content 含 '###' 的章节数={len(notes)}"
    )
    changed = 0
    skipped_migrated = 0
    for note in notes:
        if _already_migrated(note.table_data):
            skipped_migrated += 1
            continue
        plan = plan_section_changes(
            {
                "note_section": note.note_section,
                "text_content": note.text_content,
                "table_data": note.table_data,
            }
        )
        if plan.has_changes:
            changed += 1
            _print_plan(plan)

    print("\n" + "=" * 56)
    print("DRY-RUN 汇总:")
    print(f"  扫描章节: {len(notes)}")
    print(f"  将变更: {changed}")
    print(f"  已迁移(跳过): {skipped_migrated}")
    print("  未写库（dry-run）。确认后加 --execute 实际迁移。")
    print("=" * 56)


async def run_execute(session: AsyncSession, project_id: str | None) -> None:
    notes = await _load_target_notes(session, project_id)
    print(
        f"EXECUTE 范围: project={project_id or 'all'}, 候选章节数={len(notes)}"
    )
    migrated = 0
    skipped = 0
    # savepoint 事务：内层 nested 应用，验证后外层 commit
    async with session.begin_nested():
        for note in notes:
            if _already_migrated(note.table_data):
                skipped += 1
                continue
            plan = plan_section_changes(
                {
                    "note_section": note.note_section,
                    "text_content": note.text_content,
                    "table_data": note.table_data,
                }
            )
            if not plan.has_changes:
                skipped += 1
                continue

            table_data = copy.deepcopy(note.table_data or {})
            apply_plan_to_table_data(table_data, plan)
            note.table_data = table_data
            # JSONB 脏跟踪：深拷贝后重新赋值仍可能因嵌套等值被 ORM 判为未变更，
            # 显式 flag_modified 强制发出 UPDATE（行内 _orig_text_content 备份依赖此）。
            flag_modified(note, "table_data")
            note.text_content = plan.new_text_content
            if plan.section_guidance:
                # 多表 per-table 之外的通用提示降级到章节级（不覆盖已有非空值）
                note.guidance_text = note.guidance_text or plan.section_guidance
            migrated += 1
        await session.flush()
    await session.commit()
    print(f"EXECUTE 完成：迁移 {migrated} 章，跳过 {skipped} 章")


async def run_rollback(session: AsyncSession, project_id: str | None) -> None:
    """用行内备份 `_tables[0]._orig_text_content` 还原 text_content + 清 per-table guidance。"""
    pid = _project_filter(project_id)
    stmt = select(DisclosureNote).where(
        DisclosureNote.is_deleted == False,  # noqa: E712
    )
    if pid is not None:
        stmt = stmt.where(DisclosureNote.project_id == pid)
    result = await session.execute(stmt)
    notes = list(result.scalars().all())

    restored = 0
    async with session.begin_nested():
        for note in notes:
            td = note.table_data
            if not _already_migrated(td):
                continue
            new_td = copy.deepcopy(td)
            tables = new_td["_tables"]
            orig = tables[0].pop(ORIG_BACKUP_KEY, None)
            for t in tables:
                t.pop("guidance", None)
            note.table_data = new_td
            flag_modified(note, "table_data")
            note.text_content = orig
            restored += 1
        await session.flush()
    await session.commit()
    print(f"ROLLBACK 完成：还原 {restored} 章")


async def main_async(args: argparse.Namespace) -> None:
    engine = create_async_engine(
        _database_url(), echo=False, connect_args=_connect_args()
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        if args.rollback:
            await run_rollback(session, args.project_id)
        elif args.execute:
            await run_execute(session, args.project_id)
        else:
            await run_dry_run(session, args.project_id)
    await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="迁移 disclosure_notes.text_content 残留 ### → per-table guidance"
    )
    parser.add_argument(
        "--project-id",
        dest="project_id",
        default=None,
        help="限定 project UUID；不传则全库（dry-run 建议先全库扫描）",
    )
    parser.add_argument(
        "--execute",
        "--apply",
        dest="execute",
        action="store_true",
        help="实际写库（默认 dry-run 不写库）",
    )
    parser.add_argument(
        "--rollback",
        dest="rollback",
        action="store_true",
        help="用行内备份还原（撤销迁移）",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
