"""附注正文 markdown 残留 诊断/清理脚本（spec disclosure-note-quality-completion R1 / Task 1.4）。

历史「生成附注」LLM 把 markdown 草稿（###/**/列表）写入 text_content，富文本框按 HTML
渲染 → 显示字面 ###/**。本脚本：
- 默认（只读）：按项目统计含 markdown 残留的活跃附注章节数，不改库。
- --apply：把 text_content 经 sanitize_note_narrative 归一（去 markdown 标记保文字），
  改动前把原值备份到一次性表 _note_text_markdown_backup（幂等、可回滚）。

用法（cwd=backend）：
    python scripts/diagnose_note_text_markdown.py                 # 只读诊断
    python scripts/diagnose_note_text_markdown.py --project <id>  # 限定项目
    python scripts/diagnose_note_text_markdown.py --apply         # 清理（带备份）
    python scripts/diagnose_note_text_markdown.py --rollback      # 从备份回滚

幂等：sanitize 后不含 markdown → 再次 --apply rowcount=0。
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, ".")

from app.core.config import settings  # noqa: E402
from app.services.note_content_utils import sanitize_note_narrative  # noqa: E402

_MD = re.compile(r"###|\*\*|需补充|待补充")

_BACKUP_DDL = """
CREATE TABLE IF NOT EXISTS _note_text_markdown_backup (
    note_id UUID PRIMARY KEY,
    project_id UUID,
    note_section TEXT,
    original_text_content TEXT,
    backed_up_at TIMESTAMPTZ DEFAULT now()
)
"""


async def _rows(conn, project_id: str | None):
    where = "is_deleted = false AND text_content IS NOT NULL AND text_content <> ''"
    params: dict = {}
    if project_id:
        where += " AND project_id = :pid"
        params["pid"] = project_id
    res = await conn.execute(
        text(f"SELECT id, project_id, note_section, text_content FROM disclosure_notes WHERE {where}"),
        params,
    )
    return res.fetchall()


async def diagnose(engine, project_id: str | None) -> None:
    async with engine.connect() as conn:
        rows = await _rows(conn, project_id)
    by_project: dict[str, int] = {}
    total = 0
    for _id, pid, _sec, tc in rows:
        if tc and _MD.search(tc):
            by_project[str(pid)] = by_project.get(str(pid), 0) + 1
            total += 1
    print(f"[诊断] 活跃附注 text_content 含 markdown 残留：{total} 条，跨 {len(by_project)} 项目")
    for pid, n in sorted(by_project.items(), key=lambda kv: -kv[1]):
        print(f"  - project {pid}: {n} 条")
    if total == 0:
        print("  （无残留，无需清理）")


async def apply_clean(engine, project_id: str | None) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(_BACKUP_DDL))
        rows = await _rows(conn, project_id)
        changed = 0
        for _id, pid, sec, tc in rows:
            if not tc or not _MD.search(tc):
                continue
            cleaned = sanitize_note_narrative(tc)
            if cleaned == tc:
                continue
            # 备份原值（幂等：主键冲突不覆盖已有备份）
            await conn.execute(
                text(
                    "INSERT INTO _note_text_markdown_backup (note_id, project_id, note_section, original_text_content) "
                    "VALUES (:id, :pid, :sec, :tc) ON CONFLICT (note_id) DO NOTHING"
                ),
                {"id": _id, "pid": pid, "sec": sec, "tc": tc},
            )
            await conn.execute(
                text("UPDATE disclosure_notes SET text_content = :tc WHERE id = :id"),
                {"tc": cleaned, "id": _id},
            )
            changed += 1
    print(f"[清理] 归一 {changed} 条 text_content（原值已备份到 _note_text_markdown_backup，可 --rollback）")


async def rollback(engine) -> None:
    async with engine.begin() as conn:
        res = await conn.execute(
            text(
                "UPDATE disclosure_notes d SET text_content = b.original_text_content "
                "FROM _note_text_markdown_backup b WHERE d.id = b.note_id"
            )
        )
        print(f"[回滚] 恢复 {res.rowcount} 条 text_content")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        if args.rollback:
            await rollback(engine)
        elif args.apply:
            await apply_clean(engine, args.project)
            await diagnose(engine, args.project)
        else:
            await diagnose(engine, args.project)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
