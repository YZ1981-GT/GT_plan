"""清点「规则已不存在、格里还留着推送值」的附注单元格（只读，不改任何数据）。

缘由（spec note-table-structure-formula-pull-closure R8）：公式推送按规则写格并在 ``formula_push_state`` 记一行
（``rule_id`` + ``last_pushed_value``）。规则清单（``backend/data/formula_push_rules.json``）改过之后，旧规则写下的格
没有任何人再维护：推送不碰它（规则没了）、附注预设公式也不碰它（推送拥有格保护按 state 判定），于是格里永远停在
当年推送的那个数。真库实测 D2 的 ``D2.note.subtable_0 / _1 / _2 / _7 / _10`` 就是这类（规则现在只有 ``D2.note.main``）。

本脚本只报告，不修。输出按项目 / 章节 / 规则列出：留在格里的值、当时推的值、是否仍然相等（相等 ⇒ 这一格的数就是
那条已删规则留下的）。要清理请人工确认后另走修复脚本。

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


def _known_rule_ids() -> set[str]:
    from app.services.formula_push.rules import load_rules

    return {r.rule_id for r in load_rules()}


async def collect(project_id: str | None) -> dict:
    from app.core.database import async_session
    from app.models.core import Project

    known = _known_rule_ids()
    async with async_session() as db:
        where = [sa.text("domain = 'note'")]
        params: dict = {}
        if project_id:
            where.append(sa.text("project_id = :pid"))
            params["pid"] = project_id
        rows = (await db.execute(sa.text(
            "SELECT s.project_id, s.year, s.note_section, s.rule_id, s.addr_id, s.state, "
            "       s.last_pushed_value, s.current_value, s.updated_at "
            "FROM formula_push_state s "
            f"WHERE {' AND '.join('(' + str(w) + ')' for w in where)} "
            "ORDER BY s.project_id, s.note_section, s.rule_id, s.addr_id"
        ), params)).mappings().all()
        names = {
            str(pid): name for pid, name in (await db.execute(
                sa.select(Project.id, Project.name))).all()
        }

    out: list[dict] = []
    for r in rows:
        if r["rule_id"] in known:
            continue
        pushed, current = r["last_pushed_value"], r["current_value"]
        out.append({
            "project_id": str(r["project_id"]),
            "project_name": names.get(str(r["project_id"]), ""),
            "year": r["year"],
            "note_section": r["note_section"],
            "rule_id": r["rule_id"],
            "addr_id": r["addr_id"],
            "state": r["state"],
            "last_pushed_value": pushed,
            "current_value": current,
            # 相等 ⇒ 格里的数就是这条已删规则当年推的（没有人改过，也没有人再维护）
            "still_pushed_value": pushed is not None and pushed == current,
            "updated_at": str(r["updated_at"]),
        })
    return {"known_rule_count": len(known), "note_state_rows": len(rows), "orphans": out}


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
