"""附注「manual 占位」存量修复（spec note-pull-followup-closure R5 / ADR-5「没有绑定 ≠ 人工」）。

旧版生成把「没有 binding / binding 为 manual 且没有预填值」的格标 ``_cell_modes=manual`` ⇒ 推送 keep_manual、附注公式与
合计回填只写自动格，这些格永远进不来数。现行生成不再标（``_cell_meta.unbound``）；本工具把存量里同样的格改回自动：

- 只改：存储为 manual、值为空、``_cell_meta.manual_value`` 为空、且现行 binding 对这一格没有自动取数来源（与生成同一判定
  ``binding_cell_unbound``）。用户「一键清除公式」改成 manual 的格（binding 有自动来源）、有值或有预填 / 备份值的格不动；
- 改法：去掉该格的 ``_cell_modes`` 键，``_cell_meta`` 记 ``unbound``；``_tables`` 各表与顶层 ``rows``（首表镜像）各自按格判定；
- 默认只出报告；``--apply`` 只对项目名带「【测试】」的项目实写（真实项目只出报告），写前把原 ``table_data`` 备份到
  ``backend/backups/``，逐条只更新 ``table_data`` 一列（不盖「最近一次编辑」：这是数据修复，不是人工编辑）。

用法::

    python backend/scripts/fix/fix_note_manual_placeholders.py --project <uuid> [--year 2025]          # 报告
    python backend/scripts/fix/fix_note_manual_placeholders.py --project <uuid> --apply               # 只限【测试】项目
    python backend/scripts/fix/fix_note_manual_placeholders.py --all                                  # 全部项目只出报告
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

TEST_PROJECT_MARK = "【测试】"
BACKUP_DIR = _BACKEND / "backups"


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_total(row: dict) -> bool:
    return bool(row.get("is_total")) or row.get("row_type") in ("total", "subtotal")


def plan_rows(rows: Any, binding_table: dict | None) -> tuple[list[dict], Counter]:
    """一张表里要改回自动的格 → ``[{row, col, label, kind}]`` 与跳过原因计数。"""
    from app.services.disclosure_engine import DisclosureEngine, binding_cell_unbound

    binding_table = binding_table if isinstance(binding_table, dict) else {}
    binding_rows = binding_table.get("rows") if isinstance(binding_table.get("rows"), dict) else {}
    header_normalize = binding_table.get("header_normalize") if isinstance(binding_table.get("header_normalize"), list) else []
    changes: list[dict] = []
    skipped: Counter = Counter()
    for r, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict) or _is_total(row):
            continue
        modes = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
        meta = row.get("_cell_meta") if isinstance(row.get("_cell_meta"), dict) else {}
        values = row.get("values") if isinstance(row.get("values"), list) else []
        label = str(row.get("label") or "")
        for key, mode in modes.items():
            if mode != "manual" or not str(key).isdigit():
                continue
            c = int(key)
            slot = meta.get(key) if isinstance(meta.get(key), dict) else {}
            if not _blank(values[c] if c < len(values) else None):
                skipped["有值（人工填过）"] += 1
                continue
            if not _blank(slot.get("manual_value")):
                skipped["有预填 / 备份值"] += 1
                continue
            cell = DisclosureEngine._resolve_cell_binding(label, c, binding_rows, header_normalize, meta)
            if not binding_cell_unbound(cell):
                skipped["binding 有取数来源 / 预填值（人工标的）"] += 1
                continue
            kind = "无 binding" if cell is None else "manual 无预填"
            changes.append({"row": r, "col": c, "label": label, "kind": kind})
    return changes, skipped


def plan_note(table_data: Any, section: str) -> tuple[list[dict], Counter]:
    """一条附注要改回自动的格（``table`` = ``_tables`` 下标；顶层 rows 记 ``"rows"``）。"""
    from app.services.note_template_bindings_loader import get_binding_for_section

    if not isinstance(table_data, dict):
        return [], Counter()
    sec_binding = get_binding_for_section(section) or {}
    binding_tables = sec_binding.get("tables") if isinstance(sec_binding.get("tables"), list) else []

    def binding(t: int) -> dict | None:
        return binding_tables[t] if 0 <= t < len(binding_tables) else None

    changes: list[dict] = []
    skipped: Counter = Counter()
    nested = table_data.get("_tables")
    for t, table in enumerate(nested if isinstance(nested, list) else []):
        if isinstance(table, dict):
            found, skip = plan_rows(table.get("rows"), binding(t))
            changes += [{**ch, "table": t} for ch in found]
            skipped += skip
    if isinstance(table_data.get("rows"), list):  # 顶层 rows（旧单表 / 首表镜像）同样按格判定
        mirror = isinstance(nested, list) and bool(nested)
        found, skip = plan_rows(table_data["rows"], binding(0))
        changes += [{**ch, "table": "rows", "mirror": mirror} for ch in found]
        if not mirror:
            skipped += skip
    return changes, skipped


def apply_plan(table_data: dict, changes: list[dict]) -> dict:
    """按计划改（返回新对象，入参不动）：去掉该格的人工标记，``_cell_meta`` 记 unbound。"""
    out = copy.deepcopy(table_data)
    for ch in changes:
        rows = out["rows"] if ch["table"] == "rows" else out["_tables"][ch["table"]]["rows"]
        row = rows[ch["row"]]
        key = str(ch["col"])
        row["_cell_modes"].pop(key, None)
        meta = row.get("_cell_meta") if isinstance(row.get("_cell_meta"), dict) else {}
        slot = meta.get(key) if isinstance(meta.get(key), dict) else {"manual_value": None, "semantic": None,
                                                                       "binding_id": None}
        slot["unbound"] = True
        meta[key] = slot
        row["_cell_meta"] = meta
    return out


async def run(project_ids: list[UUID] | None, year: int | None, apply: bool) -> int:
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.core import Project
    from app.models.report_models import DisclosureNote

    async with async_session() as db:
        q = sa.select(Project.id, Project.name).where(Project.is_deleted == sa.false())
        if project_ids:
            q = q.where(Project.id.in_(project_ids))
        projects = (await db.execute(q.order_by(Project.name))).all()
        total = Counter()
        for pid, name in projects:
            nq = sa.select(DisclosureNote).where(DisclosureNote.project_id == pid,
                                                 DisclosureNote.is_deleted == sa.false())
            if year is not None:
                nq = nq.where(DisclosureNote.year == year)
            notes = (await db.execute(nq)).scalars().all()
            plans = []
            kinds: Counter = Counter()
            skipped: Counter = Counter()
            for note in notes:
                changes, skip = plan_note(note.table_data, note.note_section or "")
                skipped += skip
                if changes:
                    plans.append((note, changes))
                    kinds.update(ch["kind"] for ch in changes if not ch.get("mirror"))
            cells = sum(1 for _n, chs in plans for ch in chs if not ch.get("mirror"))
            mirrored = sum(1 for _n, chs in plans for ch in chs if ch.get("mirror"))
            total["cells"] += cells
            print(f"{name}（{pid}）：附注 {len(notes)} 条，要改回自动 {cells} 格 / {len(plans)} 条"
                  + (f"（{dict(kinds)}）" if kinds else "") + (f"，另顶层首表镜像 {mirrored} 格" if mirrored else "")
                  + (f"；不动：{dict(skipped)}" if skipped else ""))
            if not apply or not plans:
                continue
            if TEST_PROJECT_MARK not in (name or ""):
                print(f"  ↳ 不是【测试】项目：只出报告，不写入")
                continue
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"note_manual_placeholders_{str(pid)[:8]}_{datetime.now():%Y%m%d_%H%M%S}.json"
            backup.write_text(json.dumps([{"note_id": str(n.id), "note_section": n.note_section, "year": n.year,
                                           "table_data": n.table_data} for n, _c in plans],
                                         ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            for note, changes in plans:
                await db.execute(sa.update(DisclosureNote).where(DisclosureNote.id == note.id)
                                 .values(table_data=apply_plan(note.table_data, changes)))
            await db.commit()
            total["applied"] += cells
            print(f"  ↳ 已写入 {cells} 格；原数据备份 {backup}")
        print(f"合计：要改回自动 {total['cells']} 格，已写入 {total['applied']} 格")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", action="append", type=UUID, help="项目 id（可重复）")
    target.add_argument("--all", action="store_true", help="全部项目（只出报告）")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="实写（只限【测试】项目）")
    args = parser.parse_args(argv)
    if args.all and args.apply:
        parser.error("--all 只出报告；实写请逐个 --project 指定【测试】项目")
    return asyncio.run(run(args.project, args.year, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
