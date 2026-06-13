"""Split guidance text from disclosure_notes.text_content (preview / execute / rollback).

Feature: note-guidance-text-separation
Usage:
  python -m backend.scripts.migrate._split_guidance_text preview --project <uuid|all>
  python -m backend.scripts.migrate._split_guidance_text execute --project <uuid|all> --confirm
  python -m backend.scripts.migrate._split_guidance_text rollback --project <uuid|all>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text as sa_text, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend app importable
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.models.report_models import DisclosureNote  # noqa: E402
from app.services.deliverable_section_state_service import (  # noqa: E402
    DeliverableSectionStateService,
)
from app.services.disclosure_engine import identify_guidance  # noqa: E402

logger = logging.getLogger(__name__)

BACKUP_TABLE = "_note_guidance_split_backup"


@dataclass
class ChangedSection:
    project_id: UUID
    year: int
    section_code: str
    note_id: UUID


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def _ensure_backup_table(session: AsyncSession) -> None:
    await session.execute(sa_text(f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
            note_id UUID PRIMARY KEY,
            project_id UUID NOT NULL,
            year INT NOT NULL,
            note_section TEXT NOT NULL,
            source_text_content TEXT NOT NULL,
            backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))


async def _backup_nonempty(session: AsyncSession, project: str) -> int:
    """检查备份表是否已有该范围数据（按 project 限定，支持多项目独立迁移）。"""
    pid = _project_filter(project)
    if pid is None:
        result = await session.execute(sa_text(f"SELECT COUNT(*) FROM {BACKUP_TABLE}"))
    else:
        result = await session.execute(
            sa_text(f"SELECT COUNT(*) FROM {BACKUP_TABLE} WHERE project_id = :pid"),
            {"pid": pid},
        )
    return int(result.scalar_one())


def _project_filter(project: str):
    if project == "all":
        return None
    return UUID(project)


async def _load_notes(session: AsyncSession, project: str) -> list[DisclosureNote]:
    pid = _project_filter(project)
    stmt = select(DisclosureNote).where(DisclosureNote.is_deleted == False)  # noqa: E712
    if pid is not None:
        stmt = stmt.where(DisclosureNote.project_id == pid)
    stmt = stmt.where(
        DisclosureNote.text_content.isnot(None),
        DisclosureNote.text_content != "",
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def cmd_preview(session: AsyncSession, project: str) -> None:
    notes = await _load_notes(session, project)
    total = len(notes)
    print(f"预览范围: project={project}, 非空 text_content 章节数={total}")
    hit = 0
    skipped = 0
    for note in notes:
        split = identify_guidance(note.text_content or "")
        if split is None:
            skipped += 1
            print(f"\n[{note.note_section}] 跳过（无法可靠识别）")
            continue
        hit += 1
        guidance, remaining = split
        print(f"\n[{note.note_section}]")
        print("  将抽取为 guidance_text:")
        print(f"    {guidance!r}")
        print("  将保留为 text_content:")
        print(f"    {remaining!r}")

    # 汇总统计：命中率供运维判断规则覆盖是否足够（避免逐条肉眼核对数百行）
    rate = (hit / total * 100) if total else 0.0
    print("\n" + "=" * 50)
    print("拆分汇总:")
    print(f"  扫描章节: {total}")
    print(f"  命中拆分: {hit} ({rate:.1f}%)")
    print(f"  低置信度跳过（保留不动）: {skipped}")
    print("=" * 50)



async def _task_ids_for_section(
    session: AsyncSession,
    project_id: UUID,
    year: int,
    section_code: str,
) -> list[UUID]:
    from app.models.audit_platform_models import DeliverableSectionState

    stmt = select(DeliverableSectionState.word_export_task_id).where(
        DeliverableSectionState.project_id == project_id,
        DeliverableSectionState.year == year,
        DeliverableSectionState.section_code == section_code,
    ).distinct()
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def _recalc_baselines(
    session: AsyncSession,
    changed: list[ChangedSection],
) -> None:
    svc = DeliverableSectionStateService(session)
    for item in changed:
        new_hash = await svc.compute_source_snapshot_hash(
            item.project_id, item.year, item.section_code,
        )
        task_ids = await _task_ids_for_section(
            session, item.project_id, item.year, item.section_code,
        )
        for task_id in task_ids:
            await svc.clear_section_stale(task_id, item.section_code, new_hash)


async def cmd_execute(session: AsyncSession, project: str, confirm: bool) -> None:
    if not confirm:
        print("拒绝执行：须显式传入 --confirm")
        return

    await _ensure_backup_table(session)
    if await _backup_nonempty(session, project) > 0:
        print(f"备份表 {BACKUP_TABLE} 已有该范围(project={project})数据，请先 rollback")
        return

    notes = await _load_notes(session, project)
    changed: list[ChangedSection] = []

    for note in notes:
        split = identify_guidance(note.text_content or "")
        if split is None:
            continue
        guidance, remaining = split
        await session.execute(
            sa_text(f"""
                INSERT INTO {BACKUP_TABLE}
                    (note_id, project_id, year, note_section, source_text_content)
                VALUES (:note_id, :project_id, :year, :note_section, :source_text_content)
            """),
            {
                "note_id": note.id,
                "project_id": note.project_id,
                "year": note.year,
                "note_section": note.note_section,
                "source_text_content": note.text_content,
            },
        )
        note.guidance_text = guidance or None
        note.text_content = remaining or None
        changed.append(ChangedSection(
            project_id=note.project_id,
            year=note.year,
            section_code=note.note_section,
            note_id=note.id,
        ))

    await session.flush()
    await _recalc_baselines(session, changed)
    await session.commit()
    print(f"execute 完成：拆分 {len(changed)} 章，跳过 {len(notes) - len(changed)} 章")


async def cmd_rollback(session: AsyncSession, project: str) -> None:
    pid = _project_filter(project)
    where = "d.id = b.note_id"
    params: dict[str, Any] = {}
    if pid is not None:
        where += " AND d.project_id = :project_id"
        params["project_id"] = pid

    await session.execute(
        sa_text(f"""
            UPDATE disclosure_notes d
            SET text_content = b.source_text_content,
                guidance_text = NULL
            FROM {BACKUP_TABLE} b
            WHERE {where}
        """),
        params,
    )
    if pid is not None:
        await session.execute(
            sa_text(f"DELETE FROM {BACKUP_TABLE} WHERE project_id = :project_id"),
            {"project_id": pid},
        )
    else:
        await session.execute(sa_text(f"DELETE FROM {BACKUP_TABLE}"))
    await session.commit()
    print("rollback 完成")


async def main_async(args: argparse.Namespace) -> None:
    engine = create_async_engine(_database_url(), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        if args.command == "preview":
            await cmd_preview(session, args.project)
        elif args.command == "execute":
            await cmd_execute(session, args.project, args.confirm)
        elif args.command == "rollback":
            await cmd_rollback(session, args.project)
    await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Split guidance_text from text_content")
    sub = parser.add_subparsers(dest="command", required=True)

    p_preview = sub.add_parser("preview")
    p_preview.add_argument("--project", required=True, help="project UUID or 'all'")

    p_exec = sub.add_parser("execute")
    p_exec.add_argument("--project", required=True)
    p_exec.add_argument("--confirm", action="store_true")

    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("--project", required=True)

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
