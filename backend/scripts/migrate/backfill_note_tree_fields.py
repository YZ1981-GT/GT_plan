"""附注树形字段回填（Task 10，AC-3.1）：给旧行补 section_id / level / parent_section_id / sort_index。

与生成链 ``DisclosureEngine.generate_notes`` 同一口径（``_load_templates`` + ``_fill_tree_fields``）：
- 按**项目自己的** template_type / report_scope 取模板（含项目级自定义合并）；按 note_section 精确对应；
- **只补空不覆盖**：已有 section_id 的行（转换服务 / 用户 / 早年回填写过的）一律不动；
- 同项目年度已被占用的 section_id 不重复写（记为冲突）；模板里没有的章节（自定义章）保持为空，不编造 ID；
- section_id 只在同一模板内稳定，跨模板匹配仍走 variant matrix 与显式别名（不据此做跨模板映射）。

默认 **dry-run**（只读，打印每个项目的可补 / 已有 / 无模板 / 冲突计数）；``--apply`` 才写库，
``UPDATE … WHERE id = :id AND section_id IS NULL``，可重复执行。真实回填须先经用户拍板。

取代 ``migrate_section_number_to_section_id.py``（A.0.5 旧脚本把国企、上市模板合成一个按编号的索引且国企优先，
上市项目同编号章节会拿到国企的 section_id；也不区分合并 / 单体口径）。

用法::

    python backend/scripts/migrate/backfill_note_tree_fields.py [--project <uuid> ...] [--apply]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa  # noqa: E402

from app.models.core import Project  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402


async def plan_backfill(db, project_id: UUID) -> dict[str, Any]:
    """只读：本项目各年度可补的行（与生成链同口径），不写库。"""
    from app.services.disclosure_engine import DisclosureEngine, _fill_tree_fields
    from app.services.note_section_catalog import normalize_report_scope, normalize_template_type

    project = await db.get(Project, project_id)
    raw_tt = getattr(project, "template_type", None)
    tt = "custom" if raw_tt == "custom" else normalize_template_type(raw_tt)  # 未设置按国企（与生成链默认一致）
    plan: dict[str, Any] = {"project_id": str(project_id), "name": getattr(project, "name", None),
                            "template_type": tt, "rows": 0, "already": 0, "fill": [], "no_template": 0,
                            "conflict": 0}
    if tt not in ("soe", "listed"):
        plan["skipped"] = "自定义 / 未知模板类型：模板没有树形字段，不回填"
        return plan
    templates = await DisclosureEngine(db)._load_templates(
        project_id, tt, normalize_report_scope(getattr(project, "report_scope", None)))
    by_code = {t["note_section"]: t for t in templates}
    notes = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id, DisclosureNote.is_deleted == sa.false()
    ).order_by(DisclosureNote.year, DisclosureNote.sort_order.asc().nulls_last()))).scalars().all()
    taken: dict[int, set[str]] = {}
    for n in notes:
        if n.section_id:
            taken.setdefault(n.year, set()).add(n.section_id)
    for n in notes:
        plan["rows"] += 1
        if n.section_id:
            plan["already"] += 1
            continue
        tmpl = by_code.get(n.note_section)
        if tmpl is None or not tmpl.get("section_id"):
            plan["no_template"] += 1
            continue
        probe = DisclosureNote(note_section=n.note_section)  # 在替身上演练同一补齐函数，不改真行
        _fill_tree_fields(probe, tmpl, taken.setdefault(n.year, set()))
        if probe.section_id is None:
            plan["conflict"] += 1
            continue
        plan["fill"].append({"id": str(n.id), "year": n.year, "note_section": n.note_section,
                             "section_id": probe.section_id, "level": probe.level,
                             "parent_section_id": probe.parent_section_id, "sort_index": probe.sort_index})
    return plan


async def apply_backfill(db, plan: dict[str, Any]) -> int:
    """写库（调用方负责 commit）：只补 section_id 仍为空的行 ⇒ 重复执行、与生成链并发都不会覆盖已写的值。"""
    written = 0
    for row in plan["fill"]:
        values = {k: row[k] for k in ("section_id", "level", "parent_section_id")}
        if isinstance(row.get("sort_index"), int):
            values["sort_index"] = row["sort_index"]
        result = await db.execute(  # 用 ORM 列绑定：UUID 主键在各方言下按真实类型比较
            sa.update(DisclosureNote)
            .where(DisclosureNote.id == UUID(row["id"]), DisclosureNote.section_id.is_(None))
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        written += result.rowcount or 0
    return written


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="附注树形字段回填（默认 dry-run）")
    parser.add_argument("--project", action="append", default=[], help="只处理指定项目（可多次）")
    parser.add_argument("--apply", action="store_true", help="真正写库（须先经用户拍板）")
    args = parser.parse_args(argv)

    from app.core.database import async_session

    async with async_session() as db:
        ids = [UUID(p) for p in args.project] or list((await db.execute(
            sa.select(DisclosureNote.project_id).where(DisclosureNote.is_deleted == sa.false()).distinct()
        )).scalars().all())
        total = 0
        for pid in sorted(ids, key=str):
            plan = await plan_backfill(db, pid)
            print(f"{plan['name']} [{plan['template_type']}] 行 {plan['rows']}：已有 {plan['already']} · "
                  f"可补 {len(plan['fill'])} · 模板无此章 {plan['no_template']} · 冲突 {plan['conflict']}"
                  + (f" · 跳过：{plan['skipped']}" if plan.get("skipped") else ""))
            if args.apply and plan["fill"]:
                total += await apply_backfill(db, plan)
                await db.commit()
        if not args.apply:
            await db.rollback()
            print("[DRY RUN] 未写库。确认后加 --apply 执行。")
        else:
            print(f"已写入 {total} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
