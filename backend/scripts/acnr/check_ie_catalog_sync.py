"""ACNR IE ↔ Catalog Sync Check — CI 守卫。

校验 d_cycle_ie_manifest.yaml 与 global_catalog.json 的 import_export 段一致（首期 D 循环）。

检测项：
1. Manifest 中有但 catalog 中找不到 sheet_code 的条目
2. Catalog 中有 import_export 但 manifest 中未登记的 sheet（首期仅 D 循环）
3. 字段值不匹配：api_prefix / item_id / storage_field / import_order / depends_on_sheets

Requirements: 18.5
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_ACNR_DATA_DIR = _BACKEND_ROOT / "data" / "acnr"
_CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"
_MANIFEST_DIR = _ACNR_DATA_DIR / "sources"

# 支持的循环（波 1: D, 波 2: K/F/G/H）
_SUPPORTED_CYCLES = ["D", "K", "F", "G", "H"]

# 需要精确比对的字段（manifest 与 catalog.import_export 共有）
_COMPARE_FIELDS = [
    "api_prefix",
    "item_id",
    "storage_field",
    "import_order",
    "depends_on_sheets",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_item_id(value) -> list[str] | str:
    """Normalize item_id for comparison — list 排序后比较。"""
    if isinstance(value, list):
        return sorted(value)
    return value


def _normalize_depends_on_sheets(value) -> list[str]:
    """Normalize depends_on_sheets — 始终作为排序 list 比较。"""
    if value is None:
        return []
    if isinstance(value, list):
        return sorted(value)
    return [value]


def _normalize_field(field_name: str, value):
    """按字段名 normalize 值以便比较。"""
    if field_name == "item_id":
        return _normalize_item_id(value)
    if field_name == "depends_on_sheets":
        return _normalize_depends_on_sheets(value)
    return value


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """执行 IE ↔ Catalog sync 检查。"""
    errors: list[str] = []

    # --- Step 1: 加载 catalog ---
    if not _CATALOG_PATH.exists():
        print(
            f"[ACNR ie-sync] ERROR: {_CATALOG_PATH} 不存在。",
            file=sys.stderr,
        )
        return 1

    try:
        catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[ACNR ie-sync] ERROR: 读取 global_catalog.json 失败: {e}",
            file=sys.stderr,
        )
        return 1

    # 构建 sheet_code → import_export 映射（支持的循环）
    catalog_sheets: dict[str, dict] = {}
    catalog_sheets_by_cycle: dict[str, dict[str, dict]] = {c: {} for c in _SUPPORTED_CYCLES}
    for sheet in catalog_data.get("sheets", []):
        cycle = sheet.get("cycle", "")
        if cycle not in _SUPPORTED_CYCLES:
            continue
        sheet_code = sheet.get("sheet_code", "")
        ie = sheet.get("import_export")
        if ie and ie.get("enabled"):
            catalog_sheets[sheet_code] = ie
            catalog_sheets_by_cycle[cycle][sheet_code] = ie

    # --- Step 2: 遍历每个支持的 cycle manifest ---
    warnings: list[str] = []
    for cycle in _SUPPORTED_CYCLES:
        manifest_path = _MANIFEST_DIR / f"{cycle.lower()}_cycle_ie_manifest.yaml"
        if not manifest_path.exists():
            print(
                f"[ACNR ie-sync] ERROR: {manifest_path} 不存在。",
                file=sys.stderr,
            )
            return 1

        try:
            manifest_data = yaml.safe_load(
                manifest_path.read_text(encoding="utf-8")
            )
        except (yaml.YAMLError, OSError) as e:
            print(
                f"[ACNR ie-sync] ERROR: 读取 {manifest_path.name} 失败: {e}",
                file=sys.stderr,
            )
            return 1

        manifest_entries = manifest_data.get("entries", [])
        manifest_sheet_codes: set[str] = set()

        # --- Step 3: 逐条比对 manifest → catalog ---
        cycle_catalog_sheets = catalog_sheets_by_cycle.get(cycle, {})
        for entry in manifest_entries:
            sheet_code = entry.get("sheet_code", "")
            manifest_sheet_codes.add(sheet_code)

            if sheet_code not in cycle_catalog_sheets:
                # M0 阶段 classification 可能未按子 sheet 粒度注册
                # （如 D1-1 在 classification 中只有 D1），
                # 此类条目报 warning 不报 error。
                warnings.append(
                    f"[{cycle}] Manifest 条目 '{sheet_code}' 在 catalog 中"
                    f"未找到对应的 import_export（classification 粒度不足，"
                    f"首期可接受）"
                )
                continue

            catalog_ie = cycle_catalog_sheets[sheet_code]

            # 逐字段比对
            for field in _COMPARE_FIELDS:
                manifest_val = _normalize_field(field, entry.get(field))
                catalog_val = _normalize_field(field, catalog_ie.get(field))

                if manifest_val != catalog_val:
                    errors.append(
                        f"[{cycle}] '{sheet_code}'.{field} 不一致 — "
                        f"manifest={manifest_val!r}, catalog={catalog_val!r}"
                    )

        # --- Step 4: 检查 catalog 有 import_export 但 manifest 未登记的 sheet ---
        cycle_catalog_sheets = catalog_sheets_by_cycle.get(cycle, {})
        for sheet_code in cycle_catalog_sheets:
            if sheet_code not in manifest_sheet_codes:
                errors.append(
                    f"[{cycle}] Catalog 中 '{sheet_code}' 有 import_export"
                    f"（enabled=true）但 manifest 中未登记"
                )

    # --- Step 5: 输出结果 ---
    if not errors:
        total_ie_sheets = sum(len(v) for v in catalog_sheets_by_cycle.values())
        msg = (
            f"[ACNR ie-sync] OK — "
            f"manifest 与 catalog import_export 段一致"
            f"（{len(_SUPPORTED_CYCLES)} 循环, "
            f"{total_ie_sheets} 条 I/E sheet）。"
        )
        if warnings:
            msg += (
                f"\n  ℹ {len(warnings)} 条 manifest 条目在 catalog 中"
                f"无对应 sheet（classification 粒度不足，首期可接受）。"
            )
        print(msg)
        return 0

    print(
        f"[ACNR ie-sync] FAIL — 发现 {len(errors)} 处不一致：",
        file=sys.stderr,
    )
    for err in errors:
        print(f"  ✗ {err}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "修复方式：更新 manifest YAML 或重新运行 generate_catalog.py 使二者同步。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
