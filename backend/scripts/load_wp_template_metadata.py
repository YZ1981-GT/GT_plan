"""加载 wp_template_metadata 种子数据到数据库

合并三个 seed 文件（D-N / B / C-A-S）的 179 条记录，写入 wp_template_metadata 表。
支持幂等执行（按 wp_code 去重，已存在则更新）。

用法:
    python backend/scripts/load_wp_template_metadata.py

也可作为 API 端点调用:
    POST /api/wp-template-metadata/seed
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# 确保可以从 backend/ 或 repo root 运行
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
SEED_FILES = [
    DATA_DIR / "wp_template_metadata_dn_seed.json",
    DATA_DIR / "wp_template_metadata_b_seed.json",
    DATA_DIR / "wp_template_metadata_cas_seed.json",
]


def load_all_entries() -> list[dict]:
    """从三个 seed 文件加载所有条目，按 wp_code 去重（后者覆盖前者）"""
    merged: dict[str, dict] = {}
    for seed_file in SEED_FILES:
        if not seed_file.exists():
            print(f"  跳过（不存在）: {seed_file.name}")
            continue
        with open(seed_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        for entry in entries:
            wp_code = entry.get("wp_code")
            if wp_code:
                merged[wp_code] = entry
        print(f"  加载 {len(entries)} 条 from {seed_file.name}")
    return list(merged.values())


async def load_to_database(entries: list[dict]) -> dict:
    """将条目写入 wp_template_metadata 表（幂等：存在则更新）"""
    from app.core.database import engine as async_engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    inserted = 0
    updated = 0
    errors = []

    async with session_factory() as db:
        for entry in entries:
            wp_code = entry["wp_code"]
            try:
                # 检查是否已存在
                existing = (await db.execute(
                    text("SELECT id FROM wp_template_metadata WHERE wp_code = :code"),
                    {"code": wp_code},
                )).first()

                row_data = {
                    "wp_code": wp_code,
                    "component_type": entry.get("component_type", "univer"),
                    "audit_stage": entry.get("audit_stage", "substantive"),
                    "cycle": entry.get("cycle"),
                    "file_format": entry.get("file_format", "xlsx"),
                    "procedure_steps": json.dumps(entry.get("procedure_steps") or [], ensure_ascii=False),
                    "guidance_text": None,
                    "formula_cells": json.dumps(entry.get("formula_cells") or [], ensure_ascii=False),
                    "required_regions": json.dumps([], ensure_ascii=False),
                    "linked_accounts": json.dumps(entry.get("linked_accounts") or [], ensure_ascii=False),
                    "note_section": entry.get("note_section"),
                    "conclusion_cell": json.dumps(entry.get("conclusion_cell"), ensure_ascii=False) if entry.get("conclusion_cell") else None,
                    "audit_objective": entry.get("audit_objective"),
                    "related_assertions": json.dumps(entry.get("related_assertions") or [], ensure_ascii=False),
                    "procedure_flow_config": None,
                }

                if existing:
                    # UPDATE
                    set_clause = ", ".join(f"{k} = :{k}" for k in row_data if k != "wp_code")
                    await db.execute(
                        text(f"UPDATE wp_template_metadata SET {set_clause} WHERE wp_code = :wp_code"),
                        row_data,
                    )
                    updated += 1
                else:
                    # INSERT
                    row_data["id"] = str(uuid4())
                    cols = ", ".join(row_data.keys())
                    vals = ", ".join(f":{k}" for k in row_data.keys())
                    await db.execute(
                        text(f"INSERT INTO wp_template_metadata ({cols}) VALUES ({vals})"),
                        row_data,
                    )
                    inserted += 1
            except Exception as e:
                errors.append({"wp_code": wp_code, "error": str(e)})

        await db.commit()

    return {"inserted": inserted, "updated": updated, "errors": errors, "total": len(entries)}


async def main_async():
    print("=" * 60)
    print("加载 wp_template_metadata 种子数据")
    print("=" * 60)

    entries = load_all_entries()
    print(f"\n  合并后总条目: {len(entries)}")

    # 统计
    by_stage = {}
    by_type = {}
    for e in entries:
        stage = e.get("audit_stage", "unknown")
        ctype = e.get("component_type", "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_type[ctype] = by_type.get(ctype, 0) + 1

    print(f"  按阶段: {by_stage}")
    print(f"  按组件: {by_type}")

    print("\n  写入数据库...")
    result = await load_to_database(entries)
    print(f"\n  结果: inserted={result['inserted']}, updated={result['updated']}, errors={len(result['errors'])}")
    if result["errors"]:
        print(f"  错误详情（前5条）:")
        for err in result["errors"][:5]:
            print(f"    {err['wp_code']}: {err['error']}")

    print("\n✅ 完成")
    return result


def main():
    """同步入口"""
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
