"""Sprint A.0.5 — 一次性 DB backfill：disclosure_notes.section_id / level / parent_section_id / sort_index.

**目的**：把 V019 新增的 7 列从 NULL 填充为有效值，数据来源 = 模板 JSON
（已由 A.0.2 脚本注入 section_id / level / parent_section_id / sort_index）。

**匹配逻辑**：
  DB 行的 `note_section` 字段（如 "四、记账本位币"）与模板 JSON 中
  section 的 `section_number` 字段做精确匹配。匹配命中后把模板的
  section_id / level / parent_section_id / sort_index 写入 DB 行。

  未命中的行（如用户自定义章节）→ 生成 fallback section_id（基于
  note_section 拼音 slug），level=2，parent_section_id=None，sort_index
  按 sort_order 推算。

**幂等性**：
  已有 section_id 的行跳过（不覆盖）。多次执行安全。

**用法**::

    python backend/scripts/migrate_section_number_to_section_id.py [--dry-run]

**回滚**：
    UPDATE disclosure_notes SET section_id=NULL, level=NULL,
      parent_section_id=NULL, sort_index=0, auto_numbering=true,
      lock_number=false, locked_number=NULL;
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from uuid import UUID

# 确保 backend 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import engine as async_engine


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# 模板加载 + 索引构建
# ---------------------------------------------------------------------------

_KEBAB_RE = re.compile(r"[^a-z0-9]+")


def _kebab_fallback(text: str) -> str:
    """简易 ASCII slug（不依赖 pypinyin，仅用于 fallback ID）."""
    slug = _KEBAB_RE.sub("-", text.lower()).strip("-")
    return slug[:80] or "section"


def _load_template_index() -> dict[str, dict]:
    """加载 SOE + Listed 模板 JSON，构建 {section_number: section_meta} 索引.

    如果两个模板有同 section_number 的 section，SOE 优先（因为现有项目
    大部分是 SOE）。
    """
    index: dict[str, dict] = {}
    for fname in ("note_template_soe.json", "note_template_listed.json"):
        fpath = DATA_DIR / fname
        if not fpath.exists():
            continue
        raw = json.loads(fpath.read_text(encoding="utf-8-sig"))
        for sec in raw.get("sections", []):
            sn = sec.get("section_number", "")
            if not sn:
                continue
            # 只取第一次出现（SOE 优先）
            if sn not in index:
                index[sn] = {
                    "section_id": sec.get("section_id"),
                    "level": sec.get("level"),
                    "parent_section_id": sec.get("parent_section_id"),
                    "sort_index": sec.get("sort_index", 0),
                }
    return index


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------


async def backfill(dry_run: bool = False) -> None:
    from sqlalchemy import text as sa_text
    engine = async_engine
    template_index = _load_template_index()
    print(f"Template index loaded: {len(template_index)} entries")

    async with engine.begin() as conn:
        # 1. 查所有 section_id IS NULL 的行
        rows = (await conn.execute(sa_text(
            "SELECT id, note_section, sort_order FROM disclosure_notes "
            "WHERE section_id IS NULL"
        ))).fetchall()
        print(f"Rows to backfill: {len(rows)}")

        if not rows:
            print("Nothing to do.")
            return

        matched = 0
        fallback_count = 0
        used_ids: set[str] = set()

        # 先收集已有 section_id 避免冲突
        existing = (await conn.execute(sa_text(
            "SELECT section_id FROM disclosure_notes WHERE section_id IS NOT NULL"
        ))).fetchall()
        for r in existing:
            if r[0]:
                used_ids.add(r[0])

        updates: list[dict] = []
        for row in rows:
            row_id, note_section, sort_order = row[0], row[1], row[2]
            meta = template_index.get(note_section)
            if meta and meta.get("section_id"):
                sid = meta["section_id"]
                level = meta.get("level", 2)
                parent = meta.get("parent_section_id")
                sort_idx = meta.get("sort_index", 0)
                matched += 1
            else:
                # Fallback：生成 ID
                slug = _kebab_fallback(note_section or "unknown")
                sid = f"fallback-{slug}"
                # 确保唯一
                n = 2
                base = sid
                while sid in used_ids:
                    sid = f"{base}-{n}"
                    n += 1
                level = 2
                parent = None
                sort_idx = sort_order // 10 if sort_order else 0
                fallback_count += 1

            used_ids.add(sid)
            updates.append({
                "id": str(row_id),
                "section_id": sid,
                "level": level,
                "parent_section_id": parent,
                "sort_index": sort_idx,
            })

        print(f"  Matched from template: {matched}")
        print(f"  Fallback generated:    {fallback_count}")

        if dry_run:
            print("\n[DRY RUN] No changes written.")
            for u in updates[:10]:
                print(f"  {u['id'][:8]}... → {u['section_id']} (level={u['level']})")
            if len(updates) > 10:
                print(f"  ... and {len(updates) - 10} more")
            return

        # 2. 批量 UPDATE
        for u in updates:
            await conn.execute(sa_text(
                "UPDATE disclosure_notes SET "
                "  section_id = :section_id, "
                "  level = :level, "
                "  parent_section_id = :parent_section_id, "
                "  sort_index = :sort_index "
                "WHERE id = :id"
            ), u)

        print(f"\nBackfill complete: {len(updates)} rows updated.")


def main():
    dry_run = "--dry-run" in sys.argv
    asyncio.run(backfill(dry_run=dry_run))


if __name__ == "__main__":
    main()
