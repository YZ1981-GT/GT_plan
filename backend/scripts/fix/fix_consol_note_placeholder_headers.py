"""合并附注已存数据里的「列N」标签列表头修正（spec note-pull-followup-closure R6）。

旧版合并模板种子（md 解析）把整列留白的标签列表头写成「列1」，上市 12 张「组合计提项目：…」表带着它；拉数 / 汇总写合并附注时
已存表头优先（``data.get("headers") or 模板表头``），种子修好后已存数据仍显示「列1」。本工具把已存数据里标签列表头为「列N」的
改成现行合并模板的表头（种子已取单体同名表的首列表头；模板也还是占位时留空）：

- 只看标签列（第 0 列），只改「列N」占位，不动别的表头；
- 默认只出报告；``--apply`` 只对项目名带「【测试】」的项目实写（真实项目只出报告），写前把原 ``data`` 备份到 ``backend/backups/``，
  逐条只更新 ``data`` 一列。

用法::

    python backend/scripts/fix/fix_consol_note_placeholder_headers.py --all                       # 全部合并附注只出报告
    python backend/scripts/fix/fix_consol_note_placeholder_headers.py --project <uuid> --apply    # 只限【测试】项目
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

TEST_PROJECT_MARK = "【测试】"
BACKUP_DIR = _BACKEND / "backups"
PLACEHOLDER_RE = re.compile(r"列\d+")


def fixed_headers(data: Any, template_headers: list[Any]) -> list[Any] | None:
    """已存表头的标签列是「列N」⇒ 换成模板表头（模板也是占位 / 空 ⇒ 留空）后的整行表头；不用改返回 None。"""
    heads = data.get("headers") if isinstance(data, dict) else None
    if not isinstance(heads, list) or not heads or not PLACEHOLDER_RE.fullmatch(str(heads[0] or "").strip()):
        return None
    tpl = str(template_headers[0] or "").strip() if template_headers else ""
    label = "" if not tpl or PLACEHOLDER_RE.fullmatch(tpl) else str(template_headers[0])
    return [label, *heads[1:]]


async def run(project_ids: list[UUID] | None, apply: bool) -> int:
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.core import Project
    from app.services.consol_note_detail_source_service import resolve_section_template_type
    from app.services.consol_note_formula_service import find_table

    async with async_session() as db:
        q = sa.select(ConsolNoteData, Project.name).join(Project, Project.id == ConsolNoteData.project_id).where(
            ConsolNoteData.data["headers"][0].astext.op("~")(r"^列[0-9]+$"))
        if project_ids:
            q = q.where(ConsolNoteData.project_id.in_(project_ids))
        rows = (await db.execute(q.order_by(Project.name, ConsolNoteData.section_id))).all()
        by_project: dict[UUID, list[tuple[Any, list[Any]]]] = {}
        names: dict[UUID, str] = {}
        types: dict[UUID, str] = {}
        for record, name in rows:
            pid = record.project_id
            names[pid] = name or ""
            if pid not in types:
                types[pid] = await resolve_section_template_type(db, pid)
            table = find_table(types[pid], record.section_id) or {}
            new = fixed_headers(record.data, list(table.get("headers") or []))
            if new is not None:
                by_project.setdefault(pid, []).append((record, new))
        total = applied = 0
        for pid, items in by_project.items():
            total += len(items)
            detail = "、".join(f"{r.section_id}@{r.node_key or '项目级'}→「{new[0]}」" for r, new in items[:6])
            print(f"{names[pid]}（{pid}）：{len(items)} 条表头带「列N」：{detail}{' 等' if len(items) > 6 else ''}")
            if not apply:
                continue
            if TEST_PROJECT_MARK not in names[pid]:
                print("  ↳ 不是【测试】项目：只出报告，不写入")
                continue
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"consol_note_placeholder_headers_{str(pid)[:8]}_{datetime.now():%Y%m%d_%H%M%S}.json"
            backup.write_text(json.dumps([{"id": str(r.id), "section_id": r.section_id, "node_key": r.node_key,
                                           "data": r.data} for r, _n in items], ensure_ascii=False, indent=1,
                                         default=str), encoding="utf-8")
            for record, new in items:
                data = copy.deepcopy(record.data)
                data["headers"] = new
                await db.execute(sa.update(ConsolNoteData).where(ConsolNoteData.id == record.id).values(data=data))
            await db.commit()
            applied += len(items)
            print(f"  ↳ 已写入 {len(items)} 条；原数据备份 {backup}")
        print(f"合计：表头带「列N」{total} 条，已写入 {applied} 条")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", action="append", type=UUID, help="合并项目 id（可重复）")
    target.add_argument("--all", action="store_true", help="全部项目（只出报告）")
    parser.add_argument("--apply", action="store_true", help="实写（只限【测试】项目）")
    args = parser.parse_args(argv)
    if args.all and args.apply:
        parser.error("--all 只出报告；实写请逐个 --project 指定【测试】项目")
    return asyncio.run(run(args.project, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
