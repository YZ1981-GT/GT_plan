"""存量项目附注表格结构 vs 现行种子（只读；spec disclosure-note-template-word-realignment Task 11，design §4.2）。

仓库根执行::

    .venv\\Scripts\\python.exe backend/scripts/check/check_note_project_tables.py --all-targets
    .venv\\Scripts\\python.exe backend/scripts/check/check_note_project_tables.py --project <id> --report out.json

每个项目打印两行五类计数：库内原样、读时增强后（用户在编辑器里看到的）。只比对编号在种子里的活动行；
种子取生成链同口径（``DisclosureEngine._load_templates``：项目口径过滤、编号归一）。不写库（事务回滚）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts" / "fix"))


async def _one(project_id: uuid.UUID, year: int) -> dict:
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.report_models import DisclosureNote
    from app.services.disclosure_engine import DisclosureEngine
    from app.services.note_project_table_diff import compare_section, enriched, summarize

    from app.models.core import Project

    async with async_session() as db:
        deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar()
        if deleted is None or deleted:
            return {"project_id": str(project_id), "year": year, "skipped": "项目不存在或已删除"}
        engine = DisclosureEngine(db)
        tt = await engine._get_active_template_type(project_id)
        templates = {t["note_section"]: t for t in await engine._load_templates(project_id, tt)}
        rows = (await db.execute(sa.select(DisclosureNote.note_section, DisclosureNote.table_data).where(
            DisclosureNote.project_id == project_id, DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false()))).all()
        await db.rollback()
    raw, enr, details = [], [], []
    for code, td in rows:
        tmpl = templates.get(code)
        if tmpl is None or not (tmpl.get("tables") or td):
            continue
        a = compare_section(td, tmpl.get("tables") or [])
        b = compare_section(enriched(td, tt, code), tmpl.get("tables") or [])
        raw.append(a)
        enr.append(b)
        if a["count_mismatch"] or any(c != "一致" for c, _ in a["tables"]):
            details.append({"note_section": code, "raw": a, "enriched": b})
    return {"project_id": str(project_id), "year": year, "template_type": tt,
            "raw": summarize(raw), "enriched": summarize(enr), "sections": details}


async def main() -> int:
    from realign_project_notes import TARGETS  # noqa: E402 - 同一份目标清单

    parser = argparse.ArgumentParser(description="存量项目附注表格结构 vs 现行种子（只读）")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--project", action="append")
    who.add_argument("--all-targets", action="store_true")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    reports = []
    for pid_text in (list(TARGETS) if args.all_targets else args.project):
        report = await _one(uuid.UUID(pid_text), args.year)
        reports.append(report)
        name = TARGETS.get(pid_text, pid_text)
        if "skipped" in report:
            print(f"{name}  跳过：{report['skipped']}")
            continue
        print(f"{name}  原样：{report['raw']}")
        print(f"{' ' * len(name)}  增强后：{report['enriched']}")
    if args.report:
        args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
