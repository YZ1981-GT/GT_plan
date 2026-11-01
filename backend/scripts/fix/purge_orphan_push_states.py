"""回收「规则已不存在」的附注推送状态行，并让这些格回到现行机制维护（spec note-table-structure-formula-pull-closure R9）。

为什么要回收：公式推送写格时在 ``formula_push_state`` 记一行。规则清单改名 / 删条目后，这些行既不再被推送维护
（规则没了），也挡着附注预设公式（执行器按 state 判「推送拥有格」就跳过）⇒ 格里永远停在当年推的那个数。
真库实证：和平药房 八、5（1）按账龄披露应收账款 / （3）坏账准备情况的「合  计」四格，停在已退役的
``D2.note.subtable_0 / _7`` 推的 156,682,427.22 与 96,298,458.45。

做什么：①删掉这些状态行（不动格里的值）②对受影响的章节重跑附注公式，让合计 / 比例按现行口径重算。
不直接清值：0 是一个有含义的金额，不能用它表示「没人维护」（设计 ADR-6）。

用法：
  python backend/scripts/fix/purge_orphan_push_states.py                       # 只预演（默认）
  python backend/scripts/fix/purge_orphan_push_states.py --project <uuid>
  python backend/scripts/fix/purge_orphan_push_states.py --apply --confirm     # 真的删 + 重算
  python backend/scripts/fix/purge_orphan_push_states.py --apply --confirm --no-recalc
备份：``--apply`` 前把要删的行整行写到 ``backend/backups/orphan_push_states_<时间戳>.json``。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402

BACKUP_DIR = ROOT / "backups"


async def _run(project: str | None, year: int | None, apply: bool, recalc: bool) -> int:
    from app.core.database import async_session
    from app.models.core import Project
    from app.services.formula_push.orphan_states import list_orphans

    async with async_session() as db:
        orphans = await list_orphans(db, project_id=project, year=year)
        names = {str(pid): name for pid, name in (await db.execute(sa.select(Project.id, Project.name))).all()}

        print(f"附注域孤儿推送状态行 {len(orphans)} 条"
              f"（其中 {sum(1 for o in orphans if o.still_pushed_value)} 条的数仍是当年推送值）")
        by_section: dict[tuple[str, int, str], list] = {}
        for o in orphans:
            by_section.setdefault((o.project_id, o.year, o.note_section or ""), []).append(o)
        for (pid, yr, section), items in sorted(by_section.items(), key=lambda kv: str(kv[0])):
            print(f"  {names.get(pid, pid)} · {yr} · {section or '(无章节)'}：{len(items)} 格")
            for o in items:
                print(f"      {o.rule_id}  {o.addr_id}  推送值={o.last_pushed_value}  现值={o.current_value}")
        if not orphans:
            print("没有这类状态行，无需处理。")
            return 0
        if not apply:
            print("\n[DRY RUN] 没有改任何数据。确认后加 --apply --confirm 执行。")
            return 0

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"orphan_push_states_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_text(json.dumps([o.to_dict() for o in orphans], ensure_ascii=False, indent=2, default=str),
                          encoding="utf-8")
        print(f"\n已备份 {len(orphans)} 行到 {backup}")

        deleted = 0
        for o in orphans:
            deleted += (await db.execute(
                sa.text("DELETE FROM formula_push_state WHERE project_id = CAST(:pid AS uuid) "
                        "  AND year = :yr AND addr_id = :addr"),
                {"pid": o.project_id, "yr": o.year, "addr": o.addr_id},
            )).rowcount or 0
        await db.commit()
        print(f"已删除状态行 {deleted} 条")

        if not recalc:
            print("按 --no-recalc 跳过重算；这些格要等下一次「刷新 / 按公式填入」才会按现行口径重算。")
            return 0
        from app.services.note_formula_generator import execute_note_formulas

        updated = 0
        for (pid, yr, section), _items in sorted(by_section.items(), key=lambda kv: str(kv[0])):
            if not section:
                continue
            try:
                result = await execute_note_formulas(db, pid, yr, section)
                await db.commit()
            except Exception as exc:  # noqa: BLE001 —— 一个章节失败不拖垮其余
                await db.rollback()
                print(f"  重算 {names.get(pid, pid)} · {section} 失败：{exc}")
                continue
            n = int((result or {}).get("updated") or 0)
            updated += n
            print(f"  重算 {names.get(pid, pid)} · {yr} · {section}：改了 {n} 格")
        print(f"重算合计改了 {updated} 格")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="回收规则已不存在的附注推送状态行（默认只预演）")
    ap.add_argument("--project", help="只处理某个项目（uuid）")
    ap.add_argument("--year", type=int, help="只处理某个年度")
    ap.add_argument("--apply", action="store_true", help="真的删除（需同时给 --confirm）")
    ap.add_argument("--confirm", action="store_true", help="与 --apply 配对使用，防手滑")
    ap.add_argument("--no-recalc", action="store_true", help="删完不重跑附注公式")
    args = ap.parse_args()
    if args.apply and not args.confirm:
        print("--apply 必须同时给 --confirm（会改真库数据）")
        return 2
    return asyncio.run(_run(args.project, args.year, args.apply, not args.no_recalc))


if __name__ == "__main__":
    raise SystemExit(main())
