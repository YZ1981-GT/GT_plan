"""一次性核查：辽宁卫生/和平药房 多表附注的 per-table guidance 现状。用完即删。"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from sqlalchemy import text
from app.core.database import async_session

PROJECTS = {
    "辽宁卫生": "37814426-a29e-4fc2-9313-a59d229bf7b0",
    "和平药房": "5942c12e-65fb-4187-ace3-79d45a90cb53",
}


async def main():
    async with async_session() as s:
        for label, pid in PROJECTS.items():
            print(f"\n========== {label} ({pid}) ==========")
            rows = (
                await s.execute(
                    text(
                        """
                        SELECT note_section, content_type, sort_order,
                               guidance_text, table_data
                        FROM disclosure_notes
                        WHERE project_id = :pid
                          AND content_type IN ('table','mixed')
                        ORDER BY sort_order ASC NULLS LAST, note_section
                        """
                    ),
                    {"pid": pid},
                )
            ).fetchall()
            print(f"  mixed/table 章节数: {len(rows)}")
            for r in rows:
                td = r.table_data
                if isinstance(td, str):
                    try:
                        td = json.loads(td)
                    except Exception:
                        td = {}
                td = td or {}
                tables = td.get("_tables") or []
                multi = len(tables) > 1
                has_section_g = bool((r.guidance_text or "").strip())
                per_table_g = {
                    i: (t.get("guidance") or "").strip()
                    for i, t in enumerate(tables)
                    if (t.get("guidance") or "").strip()
                }
                still_has_hash = "###" in (
                    json.dumps(td, ensure_ascii=False)
                )
                if multi or per_table_g or has_section_g:
                    names = [t.get("name") for t in tables]
                    print(
                        f"  [{r.note_section}] tables={len(tables)} "
                        f"names={names} section_guidance={has_section_g} "
                        f"per_table_guidance_idx={list(per_table_g.keys())} "
                        f"hash_in_td={still_has_hash}"
                    )
                    for i, g in per_table_g.items():
                        print(f"        _tables[{i}].guidance = {g[:80]!r}")


asyncio.run(main())
