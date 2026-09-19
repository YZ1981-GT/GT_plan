"""
check_addr_id_unique.py — 校验 global_catalog.json 中 addr_id 全局唯一性

CI 脚本，加载 global_catalog.json（及 overrides 文件新增条目），验证：
1. sheets 数组内 addr_id 无重复
2. cells 数组内 addr_id 无重复
3. 跨 sheets/cells 两数组，addr_id 无碰撞（全局唯一）

用法：
    python backend/scripts/acnr/check_addr_id_unique.py

退出码：
    0 = 全部唯一
    1 = 存在重复

Validates: Requirements 18.4, 24.4
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根目录
REPO_ROOT = Path(__file__).resolve().parents[3]

# 数据文件路径
CATALOG_PATH = REPO_ROOT / "backend" / "data" / "acnr" / "global_catalog.json"
OVERRIDES_PATH = REPO_ROOT / "backend" / "data" / "acnr" / "global_catalog.overrides.json"


def load_json(path: Path) -> dict | None:
    """加载 JSON 文件，失败返回 None。"""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def collect_addr_ids(catalog: dict, overrides: dict | None) -> tuple[list[str], list[str]]:
    """从 catalog 和 overrides 中收集所有 addr_id。

    返回 (sheet_addr_ids, cell_addr_ids) 两个列表（含重复以便检测）。
    """
    sheet_ids: list[str] = []
    cell_ids: list[str] = []

    # 从 catalog 主文件收集
    for entry in catalog.get("sheets", []):
        addr_id = entry.get("addr_id")
        if addr_id:
            sheet_ids.append(addr_id)

    for entry in catalog.get("cells", []):
        addr_id = entry.get("addr_id")
        if addr_id:
            cell_ids.append(addr_id)

    # 从 overrides 收集新增条目（如果 overrides 添加了新 sheet/cell）
    if overrides:
        for override in overrides.get("overrides", []):
            addr_id = override.get("addr_id")
            if not addr_id:
                continue
            # overrides 通常是补丁不是新增，但如果有 entry_type 标记则按类型归类
            entry_type = override.get("entry_type", "")
            if entry_type == "cell":
                cell_ids.append(addr_id)
            elif entry_type == "sheet":
                sheet_ids.append(addr_id)
            # 没有 entry_type 的 override 按 addr_id 段数判断：
            # 2 段 = sheet（如 D2/D2-2），3 段 = cell（如 D2/D2-2/E100）
            elif "/" in addr_id:
                segments = addr_id.split("/")
                if len(segments) >= 3:
                    cell_ids.append(addr_id)
                else:
                    sheet_ids.append(addr_id)

    return sheet_ids, cell_ids


def find_duplicates(ids: list[str]) -> dict[str, int]:
    """返回出现次数 > 1 的 addr_id 及其出现次数。"""
    counts: dict[str, int] = {}
    for aid in ids:
        counts[aid] = counts.get(aid, 0) + 1
    return {k: v for k, v in counts.items() if v > 1}


def main() -> int:
    """主入口。"""
    print("=" * 60)
    print("ACNR addr_id 全局唯一性校验")
    print("=" * 60)

    # 加载 catalog
    catalog = load_json(CATALOG_PATH)
    if catalog is None:
        print(f"❌ 无法加载 catalog: {CATALOG_PATH}")
        return 1
    print(f"✅ 已加载 catalog ({CATALOG_PATH.name})")

    # 加载 overrides（可选）
    overrides = load_json(OVERRIDES_PATH)
    if overrides is not None:
        print(f"✅ 已加载 overrides ({OVERRIDES_PATH.name})")
    else:
        print("⏭️  overrides 文件不存在或为空，跳过")

    # 收集所有 addr_id
    sheet_ids, cell_ids = collect_addr_ids(catalog, overrides)
    print(f"\n   sheets addr_id 数量: {len(sheet_ids)}")
    print(f"   cells  addr_id 数量: {len(cell_ids)}")
    print(f"   总计: {len(sheet_ids) + len(cell_ids)}")

    has_error = False

    # 1. sheets 内部重复检查
    print("\n--- 1. sheets 数组内 addr_id 重复检查 ---")
    sheet_dups = find_duplicates(sheet_ids)
    if sheet_dups:
        has_error = True
        for aid, count in sorted(sheet_dups.items()):
            print(f"   ❌ 重复 (sheets): {aid} (出现 {count} 次)")
    else:
        print("   ✅ sheets 内无重复")

    # 2. cells 内部重复检查
    print("\n--- 2. cells 数组内 addr_id 重复检查 ---")
    cell_dups = find_duplicates(cell_ids)
    if cell_dups:
        has_error = True
        for aid, count in sorted(cell_dups.items()):
            print(f"   ❌ 重复 (cells): {aid} (出现 {count} 次)")
    else:
        print("   ✅ cells 内无重复")

    # 3. 跨数组碰撞检查（sheet addr_id 不应与 cell addr_id 相同）
    print("\n--- 3. 跨 sheets/cells 碰撞检查 ---")
    sheet_set = set(sheet_ids)
    cell_set = set(cell_ids)
    collisions = sheet_set & cell_set
    if collisions:
        has_error = True
        for aid in sorted(collisions):
            print(f"   ❌ 碰撞: {aid} 同时出现在 sheets 和 cells 中")
    else:
        print("   ✅ 跨数组无碰撞")

    # 汇总
    print("\n" + "=" * 60)
    total = len(sheet_ids) + len(cell_ids)
    unique_total = len(sheet_set | cell_set)

    if has_error:
        dup_count = sum(sheet_dups.values()) + sum(cell_dups.values()) + len(collisions)
        print(f"❌ 校验失败：发现 {dup_count} 处重复/碰撞问题")
        return 1

    print(f"✅ 校验通过：{unique_total} 个 addr_id 全局唯一")
    return 0


if __name__ == "__main__":
    sys.exit(main())
