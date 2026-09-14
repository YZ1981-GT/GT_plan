"""一次性脚本：修复存量项目底稿名称（"底稿A18"→正确中文名）

根因：generate_project_workpapers 的 name fallback 链缺少 wp_account_mapping.json，
导致 gt_template_library.json 中没有的编码（A18~A27 等）用了 "底稿{code}" fallback。

本脚本从 wp_account_mapping.json 读取正确名称，批量 UPDATE DB 中名称为"底稿X"模式的行。

用法：
  cd backend
  ..\.venv\Scripts\python.exe scripts/fix/_fix_wp_names_from_mapping.py [--dry-run]
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from uuid import UUID

# 添加 backend 到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

DRY_RUN = "--dry-run" in sys.argv


async def main():
    from app.core.database import async_session
    from app.models.workpaper_models import WpIndex
    import sqlalchemy as sa

    # 加载 wp_account_mapping.json 的正确名称
    mapping_path = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    mapping_raw = json.loads(mapping_path.read_text(encoding="utf-8"))
    mappings = mapping_raw.get("mappings", []) if isinstance(mapping_raw, dict) else mapping_raw
    name_map = {e["wp_code"]: e["wp_name"] for e in mappings if e.get("wp_code") and e.get("wp_name")}

    # 查找 DB 中名称为"底稿X"模式的 wp_index 行
    pattern = re.compile(r"^底稿[A-Z]\d")

    async with async_session() as db:
        result = await db.execute(
            sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name).where(
                WpIndex.is_deleted == sa.false(),
            )
        )
        rows = result.all()

        updates = []
        for row_id, wp_code, wp_name in rows:
            if wp_name and pattern.match(wp_name) and wp_code in name_map:
                correct_name = name_map[wp_code]
                if wp_name != correct_name:
                    updates.append((row_id, wp_code, wp_name, correct_name))

        print(f"扫描 {len(rows)} 条 wp_index，发现 {len(updates)} 条需修正名称：")
        for rid, code, old, new in updates[:20]:
            print(f"  {code}: '{old}' → '{new}'")
        if len(updates) > 20:
            print(f"  ... 及另外 {len(updates) - 20} 条")

        if DRY_RUN:
            print("\n[DRY RUN] 未执行任何修改。去掉 --dry-run 参数实际执行。")
            return

        if not updates:
            print("无需修复。")
            return

        # 批量 UPDATE
        for rid, code, old, new in updates:
            await db.execute(
                sa.update(WpIndex).where(WpIndex.id == rid).values(wp_name=new)
            )
        await db.commit()
        print(f"\n✅ 已修正 {len(updates)} 条底稿名称。")


if __name__ == "__main__":
    asyncio.run(main())
