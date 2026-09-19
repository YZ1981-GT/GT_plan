"""构建/刷新公式预设库并物化 Preset Inventory（Task 14.1 / Req 22.1, 22.3）。

幂等：预设库 = ``formula_presets_seed.json``（显式新增预设）∪ 三处收敛源
（``prefill_formula_mapping`` / ``check_presets`` / ``wide_table_presets``，由
``preset_library`` 适配层读时收敛），按 ``(page_key, target_cell)`` 去重
（遵循 ``seed_note_account_mappings.py`` 的幂等去重模式）。

本脚本把去重后的**逐页登记**物化到 ``backend/data/formula_presets/inventory.json``
（Preset Inventory，承载公式页面 → page_key + preset_status + formula_count），
输出稳定 → 重复运行结果一致（幂等）。

用法：
    python backend/scripts/seed/seed_formula_presets.py           # 构建并写 inventory.json
    python backend/scripts/seed/seed_formula_presets.py --check   # 只校验去重/统计，不写文件
    python backend/scripts/seed/seed_formula_presets.py --seed-only  # 不收敛既有源，仅用显式 seed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → backend/
sys.path.insert(0, str(ROOT))

from app.services.formula_management.preset_library import (  # noqa: E402
    INVENTORY_PATH,
    build_inventory,
    build_preset_library,
)


def build_inventory_doc(*, include_sources: bool = True) -> tuple[dict, dict[str, int]]:
    """构建 inventory.json 文档 + 去重统计。"""
    entries, stats = build_preset_library(include_sources=include_sources)
    pages = build_inventory(entries)

    # 按 scope 汇总，便于覆盖度一览
    by_scope: dict[str, dict[str, int]] = {}
    for p in pages:
        agg = by_scope.setdefault(p.scope, {"pages": 0, "formula_count": 0})
        agg["pages"] += 1
        agg["formula_count"] += p.formula_count

    doc = {
        "description": (
            "公式预设库 Preset Inventory：逐页登记承载公式的页面/sheet"
            "（page_key + preset_status + formula_count）。由 seed_formula_presets.py "
            "从 formula_presets_seed.json + 收敛源（prefill/check/wide_table）去重物化。"
        ),
        "version": "2025-R1",
        "generated_by": "backend/scripts/seed/seed_formula_presets.py",
        "summary": {
            "total_pages": len(pages),
            "total_formulas": len(entries),
            "by_scope": by_scope,
        },
        "pages": [p.to_dict() for p in pages],
    }
    return doc, stats


def seed(*, include_sources: bool = True, write: bool = True) -> dict:
    doc, stats = build_inventory_doc(include_sources=include_sources)

    if write:
        INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        INVENTORY_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return {
        "inserted": stats.get("inserted", 0),
        "skipped": stats.get("skipped", 0),
        "total_pages": doc["summary"]["total_pages"],
        "total_formulas": doc["summary"]["total_formulas"],
        "by_source": {
            k.split(":", 1)[1]: v for k, v in stats.items() if k.startswith("source:")
        },
        "by_scope": doc["summary"]["by_scope"],
        "written": write,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="构建/刷新公式预设库 Preset Inventory")
    parser.add_argument(
        "--check", action="store_true", help="只校验/统计，不写 inventory.json"
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="不收敛既有源，仅用 formula_presets_seed.json",
    )
    args = parser.parse_args()

    result = seed(include_sources=not args.seed_only, write=not args.check)

    print("\n[OK] Formula Preset Library")
    print(f"  Inserted (deduped): {result['inserted']}")
    print(f"  Skipped (duplicate page_key+target_cell): {result['skipped']}")
    print(f"  Total pages: {result['total_pages']}")
    print(f"  Total formulas: {result['total_formulas']}")
    print(f"  By source: {result['by_source']}")
    print(f"  By scope: {result['by_scope']}")
    print(f"  inventory.json written: {result['written']}")


if __name__ == "__main__":
    main()
