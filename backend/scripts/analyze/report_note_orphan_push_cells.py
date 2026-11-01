"""清点「规则已不存在、格里还留着推送值」的附注单元格（只读，不改任何数据）。

缘由（spec note-table-structure-formula-pull-closure R8）：公式推送按规则写格并在 ``formula_push_state`` 记一行
（``rule_id`` + ``last_pushed_value``）。规则清单（``backend/data/formula_push_rules.json``）改过之后，旧规则写下的格
没有任何人再维护：推送不碰它（规则没了）、附注预设公式也不碰它（推送拥有格保护按 state 判定），于是格里永远停在
当年推送的那个数。真库实测 D2 的 ``D2.note.subtable_0 / _1 / _2 / _7 / _10`` 就是这类（规则现在只有 ``D2.note.main``）。

判定与修复脚本（``backend/scripts/fix/purge_orphan_push_states.py``）、推送回执共用
``app.services.formula_push.orphan_states``（设计 ADR-7：只有一份）。本脚本只报告，清理请走修复脚本。

用法：
  python backend/scripts/analyze/report_note_orphan_push_cells.py              # 全部项目
  python backend/scripts/analyze/report_note_orphan_push_cells.py --project <uuid>
  python backend/scripts/analyze/report_note_orphan_push_cells.py --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402


async def collect(project_id: str | None) -> dict:
    from app.core.database import async_session
    from app.models.core import Project
    from app.services.formula_push.orphan_states import known_rule_ids, list_orphans

    async with async_session() as db:
        known = known_rule_ids()
        orphans = await list_orphans(db, project_id=project_id)
        scope = " AND project_id = CAST(:pid AS uuid)" if project_id else ""
        total_note_rows = (await db.execute(
            sa.text(f"SELECT count(*) FROM formula_push_state WHERE domain = 'note'{scope}"),
            {"pid": project_id} if project_id else {},
        )).scalar_one()
        names = {str(pid): name for pid, name in (await db.execute(sa.select(Project.id, Project.name))).all()}

    return {
        "known_rule_count": len(known),
        "note_state_rows": int(total_note_rows),
        "orphans": [{**o.to_dict(), "project_name": names.get(o.project_id, "")} for o in orphans],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="清点规则已删除、格里仍留推送值的附注单元格（只读）")
    ap.add_argument("--project", help="只看某个项目（uuid）")
    ap.add_argument("--json", dest="json_path", help="同时把明细写到这个文件")
    args = ap.parse_args()

    report = asyncio.run(collect(args.project))
    orphans = report["orphans"]
    print(f"规则清单 {report['known_rule_count']} 条；附注域推送状态 {report['note_state_rows']} 行；"
          f"规则已不存在的 {len(orphans)} 行")
    by_rule: dict[tuple[str, str, str], list[dict]] = {}
    for o in orphans:
        by_rule.setdefault((o["project_name"], o["note_section"] or "-", o["rule_id"]), []).append(o)
    for (project, section, rule), items in sorted(by_rule.items()):
        kept = sum(1 for i in items if i["still_pushed_value"])
        print(f"  {project} · {section} · {rule}：{len(items)} 格（其中 {kept} 格的数仍是当年推送值）")
        for i in items:
            print(f"      {i['addr_id']}  state={i['state']}  推送值={i['last_pushed_value']}"
                  f"  现值={i['current_value']}  更新于 {i['updated_at'][:19]}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"明细已写入 {args.json_path}")
    if not orphans:
        print("没有这类单元格。")
    else:
        print("\n清理（会改真库）：python backend/scripts/fix/purge_orphan_push_states.py --apply --confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
