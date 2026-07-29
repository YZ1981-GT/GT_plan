"""
诊断脚本：检测附注 refill 的 binding label 匹配率。

逐章节加载 binding（从 note_template_bindings.json）+ 真实 table_data rows，
统计每章节有多少 binding 行能匹配到实际 row label → 定位"刷新不生效"的具体章节。

同时对指定项目开启公式灰度（wizard_state.disclosure_note_formula_enabled=true）。

用法：
  cd backend
  set PYTHONPATH=.
  python scripts/diagnose_note_refill_coverage.py

环境变量：
  TARGET_PROJECT_ID  目标项目 UUID（默认 0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49）
  ENABLE_FORMULA     设为 "true" 时对目标项目开启公式灰度
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

# 确保能 import app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


TARGET_PROJECT_ID = UUID(os.environ.get(
    "TARGET_PROJECT_ID", "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
))
ENABLE_FORMULA = os.environ.get("ENABLE_FORMULA", "").lower() == "true"
YEAR = 2025


async def main():
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 加载 binding JSON
    bindings_path = Path(__file__).resolve().parent.parent / "data" / "note_template_bindings.json"
    if not bindings_path.exists():
        print(f"[ERROR] Binding file not found: {bindings_path}")
        return

    with open(bindings_path, "r", encoding="utf-8-sig") as f:
        bindings_data = json.load(f)

    # 构建 section -> binding tables
    sections_binding = {}
    bindings_raw = bindings_data.get("bindings", {})
    if isinstance(bindings_raw, dict):
        for sec_num, sec_data in bindings_raw.items():
            tables = sec_data.get("tables", []) if isinstance(sec_data, dict) else []
            if sec_num and tables:
                sections_binding[sec_num] = tables
    elif isinstance(bindings_raw, list):
        for section in bindings_raw:
            sec_num = section.get("section_number", "")
            tables = section.get("tables", [])
            if sec_num and tables:
                sections_binding[sec_num] = tables

    print(f"[INFO] Loaded {len(sections_binding)} sections from binding JSON")
    print(f"[INFO] Target project: {TARGET_PROJECT_ID}, year: {YEAR}")
    print()

    async with async_session() as db:
        # 查所有活跃附注
        result = await db.execute(text("""
            SELECT note_section, section_title, content_type,
                   table_data::text AS td_text,
                   table_data
            FROM disclosure_notes
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND content_type IN ('table', 'mixed')
              AND table_data IS NOT NULL AND table_data::text != '{}'
            ORDER BY note_section
        """), {"pid": str(TARGET_PROJECT_ID), "year": YEAR})
        notes = result.fetchall()

        print(f"[INFO] Found {len(notes)} table/mixed notes")
        print()

        # 统计
        total_matched = 0
        total_unmatched = 0
        matched_sections = []
        unmatched_sections = []

        for note in notes:
            sec = note.note_section
            td = note.table_data
            if not isinstance(td, dict):
                continue

            # 跳过 workpaper source（与引擎一致）
            if td.get("_source") in ("workpaper", "workpaper_html"):
                continue

            # 获取 binding
            sec_binding_tables = sections_binding.get(sec, [])
            if not sec_binding_tables:
                unmatched_sections.append((sec, note.section_title, "无 binding"))
                total_unmatched += 1
                continue

            # 检查第一张表的 binding rows 能否匹配实际 rows
            first_table_binding = sec_binding_tables[0] if sec_binding_tables else {}
            binding_rows = first_table_binding.get("rows", {})

            # 实际 rows
            actual_rows = []
            nested = td.get("_tables")
            if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                actual_rows = nested[0].get("rows", [])
            else:
                actual_rows = td.get("rows", [])

            if not actual_rows:
                unmatched_sections.append((sec, note.section_title, "实际无 rows"))
                total_unmatched += 1
                continue

            # 统计 label 匹配
            actual_labels = set()
            for r in actual_rows:
                if isinstance(r, dict):
                    lbl = r.get("label", "")
                    if lbl:
                        actual_labels.add(lbl)

            binding_labels = set(binding_rows.keys()) if isinstance(binding_rows, dict) else set()

            matched_labels = actual_labels & binding_labels
            if matched_labels:
                matched_sections.append((sec, note.section_title, len(matched_labels), len(actual_labels)))
                total_matched += 1
            else:
                unmatched_sections.append((sec, note.section_title, f"0/{len(actual_labels)} label 匹配"))
                total_unmatched += 1

        print("=" * 70)
        print(f"匹配统计：{total_matched} 章节可 refill / {total_unmatched} 章节无法匹配")
        print("=" * 70)
        print()

        if matched_sections:
            print(f"--- 可 refill 的章节 ({len(matched_sections)}) ---")
            for sec, title, matched, total in matched_sections[:20]:
                print(f"  [OK] {sec:12s} {title[:30]:30s}  匹配 {matched}/{total} 行")
            if len(matched_sections) > 20:
                print(f"  ... 还有 {len(matched_sections) - 20} 个")
            print()

        if unmatched_sections:
            print(f"--- 无法 refill 的章节 ({len(unmatched_sections)}) ---")
            for sec, title, reason in unmatched_sections[:30]:
                print(f"  [--] {sec:12s} {title[:30]:30s}  原因: {reason}")
            if len(unmatched_sections) > 30:
                print(f"  ... 还有 {len(unmatched_sections) - 30} 个")
            print()

        # 开灰度
        if ENABLE_FORMULA:
            print()
            print("=" * 70)
            print(f"[ACTION] 为项目 {TARGET_PROJECT_ID} 开启公式灰度...")
            result = await db.execute(text("""
                UPDATE projects
                SET wizard_state = jsonb_set(
                    COALESCE(wizard_state, '{}'::jsonb),
                    '{disclosure_note_formula_enabled}',
                    'true'::jsonb
                )
                WHERE id = :pid
                RETURNING id
            """), {"pid": str(TARGET_PROJECT_ID)})
            row = result.fetchone()
            if row:
                await db.commit()
                print(f"[OK] 公式灰度已开启（wizard_state.disclosure_note_formula_enabled = true）")
                print(f"     下次 refill 时 119 条 formula binding（sum/report/aging）将生效")
            else:
                print(f"[WARN] 项目未找到，未修改")
        else:
            print()
            print("[INFO] 若要开启公式灰度，设置环境变量 ENABLE_FORMULA=true 重跑")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
