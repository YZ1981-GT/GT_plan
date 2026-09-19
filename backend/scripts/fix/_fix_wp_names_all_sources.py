"""修复存量项目底稿占位名称（"底稿B22A" → 真实名称）。

从多源合并名称：wp_account_mapping.json → prefill_formula_mapping.json →
acnr/sheet_display_names.json → gt_template_library.json（按优先级 setdefault）。
仅更新 wp_name 匹配 ^底稿[A-Z] 占位模式且能解析出真实名的行。

用法（cwd=backend）：
  python scripts/fix/_fix_wp_names_all_sources.py --dry-run
  python scripts/fix/_fix_wp_names_all_sources.py            # 实际执行
  python scripts/fix/_fix_wp_names_all_sources.py --project <uuid>  # 限定项目
"""
import asyncio
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data"
DRY_RUN = "--dry-run" in sys.argv
PROJECT_ID = None
if "--project" in sys.argv:
    PROJECT_ID = sys.argv[sys.argv.index("--project") + 1]

_PLACEHOLDER = re.compile(r"^底稿[A-Z]")


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def build_name_map() -> dict[str, str]:
    nm: dict[str, str] = {}
    for fname, key in [
        ("wp_account_mapping.json", None),
        ("prefill_formula_mapping.json", None),
    ]:
        d = _load(DATA / fname)
        if d:
            entries = d.get("mappings", d) if isinstance(d, dict) else d
            for e in entries:
                if isinstance(e, dict) and e.get("wp_code") and e.get("wp_name"):
                    nm.setdefault(e["wp_code"], e["wp_name"])
    d = _load(DATA / "acnr" / "sheet_display_names.json")
    if d:
        inner = d.get("names", d) if isinstance(d, dict) else d
        if isinstance(inner, dict):
            for code, name in inner.items():
                if isinstance(name, str) and name:
                    nm.setdefault(code, name)
    d = _load(DATA / "gt_template_library.json")
    if d:
        entries = d.get("templates", d) if isinstance(d, dict) else d
        if isinstance(entries, dict):
            for code, e in entries.items():
                if isinstance(e, dict) and (e.get("name") or e.get("wp_name")):
                    nm.setdefault(code, e.get("name") or e.get("wp_name"))
        elif isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and e.get("wp_code") and (e.get("name") or e.get("wp_name")):
                    nm.setdefault(e["wp_code"], e.get("name") or e.get("wp_name"))
    return nm


async def main():
    from app.core.database import async_session
    from app.models.workpaper_models import WpIndex
    import sqlalchemy as sa

    name_map = build_name_map()
    print(f"名称源合并 {len(name_map)} 条")

    async with async_session() as db:
        conds = [WpIndex.is_deleted == sa.false()]
        if PROJECT_ID:
            conds.append(WpIndex.project_id == PROJECT_ID)
        rows = (await db.execute(
            sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name).where(*conds)
        )).all()

        updates, unresolved = [], []
        for rid, code, name in rows:
            if name and _PLACEHOLDER.match(name):
                correct = name_map.get(code)
                if correct and correct != name:
                    updates.append((rid, code, name, correct))
                elif not correct:
                    unresolved.append(code)

        print(f"扫描 {len(rows)} 行，占位待修 {len(updates)} 行，无名称源 {len(set(unresolved))} 个")
        for rid, code, old, new in updates:
            print(f"  {code}: '{old}' → '{new}'")
        if unresolved:
            print("  [无名称源，跳过]:", " ".join(sorted(set(unresolved))))

        if DRY_RUN:
            print("\n[DRY RUN] 未修改。")
            return
        if not updates:
            print("无需修复。")
            return
        for rid, code, old, new in updates:
            await db.execute(sa.update(WpIndex).where(WpIndex.id == rid).values(wp_name=new))
        await db.commit()
        print(f"\n[OK] 已修正 {len(updates)} 行底稿名称。")


if __name__ == "__main__":
    asyncio.run(main())
