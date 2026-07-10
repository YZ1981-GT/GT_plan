"""ACNR Catalog Generator — 唯一生成入口。

合并 6 类输入为 SheetCatalogEntry/CellCatalogEntry，确定性输出（同输入 → 字节一致）。

Usage:
    python backend/scripts/acnr/generate_catalog.py [--offline] [--cycle D]

Requirements: 1.3, 1.4, 3.3, 3.4, 3.5, 18.1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_DATA_DIR = _BACKEND_ROOT / "data"
_ACNR_DATA_DIR = _DATA_DIR / "acnr"
_SOURCES_DIR = _ACNR_DATA_DIR / "sources"
_SHARDS_DIR = _ACNR_DATA_DIR / "shards"

# 确保 backend 在 sys.path 以便 import loaders
sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Imports (after path setup)
# ---------------------------------------------------------------------------

from app.services.acnr.loaders.from_classification import (  # noqa: E402
    SheetCatalogEntry,
    load_sheet_skeletons_from_classification,
)
from app.services.acnr.loaders.from_ie_manifest import load_ie_manifest  # noqa: E402
from app.services.acnr.loaders.from_address_seeds import (  # noqa: E402
    CellCatalogEntry,
    load_cell_entries_from_seeds,
)
from app.services.acnr.loaders.from_frontend_labels import (  # noqa: E402
    load_sheet_name_aliases,
)
from app.services.acnr.loaders.from_render_registry import (  # noqa: E402
    load_render_registry_edges,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CATALOG_VERSION = "1"


# ---------------------------------------------------------------------------
# Overrides 加载
# ---------------------------------------------------------------------------

_OVERRIDES_PATH = _ACNR_DATA_DIR / "global_catalog.overrides.json"


def _load_overrides() -> dict[str, dict[str, Any]]:
    """加载 global_catalog.overrides.json，返回 {addr_id → override_fields}。

    overrides 文件格式：
    {
      "overrides": [
        { "addr_id": "D2/D2-2", "fields": {...}, "reason": "...", "owner": "..." }
      ]
    }
    """
    if not _OVERRIDES_PATH.exists():
        return {}

    with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    result: dict[str, dict[str, Any]] = {}
    for entry in data.get("overrides", []):
        addr_id = entry.get("addr_id", "")
        if addr_id and "fields" in entry:
            result[addr_id] = entry["fields"]

    return result


# ---------------------------------------------------------------------------
# Classification 离线缓存（CI/offline 模式）
# ---------------------------------------------------------------------------

_CLASSIFICATION_CACHE_PATH = _ACNR_DATA_DIR / "sources" / "classification_cache.json"


def _load_classification_records_offline() -> list[dict[str, Any]]:
    """从离线缓存 JSON 读取 classification 记录。"""
    if not _CLASSIFICATION_CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Classification cache not found: {_CLASSIFICATION_CACHE_PATH}\n"
            f"Run with DB access first to generate cache, or provide records."
        )
    with open(_CLASSIFICATION_CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 别名冲突检测（R3.3, R3.4, R3.5）
# ---------------------------------------------------------------------------


def _detect_alias_conflicts(
    aliases: dict[str, list[str]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """检测一对多别名冲突。

    Returns
    -------
    (clean_aliases, conflicts)
        clean_aliases: 去除冲突后的干净别名映射 {sheet_code → safe_aliases}
        conflicts: 冲突报告列表 [{alias, sheet_codes, action}]
    """
    # 反转映射：alias → list[sheet_codes]
    alias_to_sheets: dict[str, list[str]] = {}
    for sheet_code, alias_list in aliases.items():
        for alias in alias_list:
            if alias not in alias_to_sheets:
                alias_to_sheets[alias] = []
            if sheet_code not in alias_to_sheets[alias]:
                alias_to_sheets[alias].append(sheet_code)

    # 找出一对多冲突（一个别名映射多个 sheet_code）
    conflicting_aliases: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    for alias, sheet_codes in alias_to_sheets.items():
        if len(sheet_codes) > 1:
            conflicting_aliases.add(alias)
            conflicts.append({
                "alias": alias,
                "sheet_codes": sorted(sheet_codes),
                "action": "blocked",
                "reason": "one-to-many conflict: alias maps to multiple sheet_codes",
            })

    # 构建干净别名：移除冲突别名（R3.5 阻断优先于缺口标记）
    clean_aliases: dict[str, list[str]] = {}
    for sheet_code, alias_list in aliases.items():
        safe = [a for a in alias_list if a not in conflicting_aliases]
        if safe:
            clean_aliases[sheet_code] = safe

    return clean_aliases, conflicts


# ---------------------------------------------------------------------------
# 合并管线
# ---------------------------------------------------------------------------


def generate_catalog(
    *,
    classification_records: list[Any] | None = None,
    cycle: str = "d",
    offline: bool = False,
    registry_version: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """执行 catalog 生成管线。

    Parameters
    ----------
    classification_records
        classification 记录（ORM/dict），None 时走离线缓存。
    cycle
        循环码（小写），默认 'd'。
    offline
        是否使用离线缓存。
    registry_version
        catalog 版本号。None 时自动生成。

    Returns
    -------
    (catalog_data, report_data, manifest_blocked)
        catalog_data: global_catalog.json 内容
        report_data: catalog_report.json 内容
        manifest_blocked: skip_reason 是否阻止 bulk manifest
    """
    # --- 版本号 ---
    if registry_version is None:
        registry_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    # --- Step 1: 加载 classification 骨架 ---
    if classification_records is None:
        if offline:
            classification_records = _load_classification_records_offline()
        else:
            # 从 DB 加载 — 非离线模式需要 classification_cache 或 DB
            # 首期用离线缓存兜底
            classification_records = _load_classification_records_offline()

    # Step 1 也获取 render_registry 的 render_type_map 用于 editor_engine 推断
    render_data = load_render_registry_edges()
    render_type_map = render_data.render_types

    sheets = load_sheet_skeletons_from_classification(
        classification_records,
        registry_version=registry_version,
        render_type_map=render_type_map,
    )

    # 建立 addr_id → SheetCatalogEntry 索引
    sheet_index: dict[str, SheetCatalogEntry] = {s.addr_id: s for s in sheets}
    sheet_by_code: dict[str, SheetCatalogEntry] = {s.sheet_code: s for s in sheets}

    # --- Step 2: 合并 import_export（IE manifest） ---
    try:
        ie_data = load_ie_manifest(cycle)
    except FileNotFoundError:
        ie_data = {}

    for sheet_code, ie_segment in ie_data.items():
        if sheet_code in sheet_by_code:
            sheet_by_code[sheet_code].import_export = ie_segment

    # --- Step 3: 合并 component_type（render_registry） ---
    for wp_code, comp_type in render_data.component_types.items():
        if wp_code in sheet_by_code:
            sheet_by_code[wp_code].component_type = comp_type

    # --- Step 4: 合并 sheet_name_aliases（frontend labels） ---
    raw_aliases = load_sheet_name_aliases()
    clean_aliases, alias_conflicts = _detect_alias_conflicts(raw_aliases)

    for sheet_code, alias_list in clean_aliases.items():
        if sheet_code in sheet_by_code:
            # 合并，去重
            existing = set(sheet_by_code[sheet_code].sheet_name_aliases)
            for alias in alias_list:
                if alias not in existing:
                    sheet_by_code[sheet_code].sheet_name_aliases.append(alias)
                    existing.add(alias)

    # --- Step 5: 加载 CellCatalogEntry（坐标种子） ---
    cells = load_cell_entries_from_seeds(
        data_dir=_DATA_DIR,
        registry_version=registry_version,
    )

    # --- Step 6: 应用 overrides（最高优先级） ---
    overrides = _load_overrides()
    for addr_id, fields in overrides.items():
        if addr_id in sheet_index:
            entry = sheet_index[addr_id]
            for key, value in fields.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
        # 也尝试 cell 级 override（按 addr_id 匹配）
        for cell in cells:
            if cell.addr_id == addr_id:
                for key, value in fields.items():
                    if hasattr(cell, key):
                        setattr(cell, key, value)

    # --- skip_reason 全局阻断检测（R1.4） ---
    manifest_blocked = False
    for entry in sheets:
        if entry.skip_reason:
            manifest_blocked = True
            break

    # --- 生成报告 ---
    # 缺口检测：semantic_only 无 A1 的 cell
    gaps: list[dict[str, Any]] = []
    for cell in cells:
        if cell.semantic_only:
            gaps.append({
                "addr_id": cell.addr_id,
                "parent_addr_id": cell.parent_addr_id,
                "type": "semantic_only_missing_a1",
                "description": f"CellCatalogEntry {cell.addr_id} 无可靠 A1 坐标",
            })

    # 未登记别名（在 labels 中出现但对应 sheet_code 不在 catalog 的）
    unregistered_aliases: list[dict[str, Any]] = []
    for sheet_code, alias_list in raw_aliases.items():
        if sheet_code not in sheet_by_code:
            unregistered_aliases.append({
                "sheet_code": sheet_code,
                "aliases": alias_list,
                "reason": "sheet_code not found in classification catalog",
            })

    report_data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": registry_version,
        "manifest_blocked": manifest_blocked,
        "alias_conflicts": alias_conflicts,
        "gaps": gaps,
        "unregistered_aliases": unregistered_aliases,
        "summary": {
            "total_sheets": len(sheets),
            "total_cells": len(cells),
            "alias_conflict_count": len(alias_conflicts),
            "gap_count": len(gaps),
            "unregistered_alias_count": len(unregistered_aliases),
            "sheets_with_skip_reason": sum(
                1 for s in sheets if s.skip_reason
            ),
        },
    }

    # --- 构建 catalog 输出 ---
    catalog_data = _build_catalog_output(sheets, cells, registry_version)

    return catalog_data, report_data, manifest_blocked


# ---------------------------------------------------------------------------
# 确定性输出构建
# ---------------------------------------------------------------------------


def _sheet_to_dict(entry: SheetCatalogEntry) -> dict[str, Any]:
    """将 SheetCatalogEntry 转为 dict（排除 None/空值保持简洁）。"""
    d = asdict(entry)
    # 清理空列表和 None 值使输出简洁
    result: dict[str, Any] = {}
    for key, value in sorted(d.items()):
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, str) and not value and key not in (
            "addr_id", "domain", "sheet_code", "sheet_name"
        ):
            continue
        result[key] = value
    return result


def _cell_to_dict(entry: CellCatalogEntry) -> dict[str, Any]:
    """将 CellCatalogEntry 转为 dict。"""
    d = entry.to_dict()
    result: dict[str, Any] = {}
    for key, value in sorted(d.items()):
        if value is None and key not in ("cell_address", "semantic_label"):
            continue
        if isinstance(value, str) and not value and key not in (
            "addr_id", "parent_addr_id", "domain"
        ):
            continue
        result[key] = value
    return result


def _build_catalog_output(
    sheets: list[SheetCatalogEntry],
    cells: list[CellCatalogEntry],
    registry_version: str,
) -> dict[str, Any]:
    """构建确定性 catalog JSON 结构。

    确定性保证：
    - sheets 按 addr_id 排序
    - cells 按 addr_id 排序
    - 每个 dict 的 key 按 sort_keys 排序（json.dumps 时）
    """
    # 排序保证确定性
    sorted_sheets = sorted(sheets, key=lambda s: s.addr_id)
    sorted_cells = sorted(cells, key=lambda c: c.addr_id)

    return {
        "version": CATALOG_VERSION,
        "registry_version": registry_version,
        "sheets": [_sheet_to_dict(s) for s in sorted_sheets],
        "cells": [_cell_to_dict(c) for c in sorted_cells],
    }


# ---------------------------------------------------------------------------
# 确定性 JSON 序列化
# ---------------------------------------------------------------------------


def _deterministic_json(data: Any) -> str:
    """确定性 JSON 输出（同输入 → 字节一致）。

    - sort_keys=True 保证 key 排序
    - indent=2 保证可读
    - ensure_ascii=False 保留中文
    - 尾部换行
    """
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


# ---------------------------------------------------------------------------
# 文件写入
# ---------------------------------------------------------------------------


def write_catalog(
    catalog_data: dict[str, Any],
    report_data: dict[str, Any],
    *,
    output_dir: Path | None = None,
    write_shards: bool = True,
    cycle: str = "d",
) -> tuple[Path, Path]:
    """写入 catalog 与 report 文件。

    Returns
    -------
    (catalog_path, report_path)
    """
    out = output_dir or _ACNR_DATA_DIR

    # 主 catalog
    catalog_path = out / "global_catalog.json"
    catalog_json = _deterministic_json(catalog_data)
    catalog_path.write_text(catalog_json, encoding="utf-8")

    # catalog report
    report_path = out / "catalog_report.json"
    report_json = _deterministic_json(report_data)
    report_path.write_text(report_json, encoding="utf-8")

    # 可选分片
    if write_shards:
        _SHARDS_DIR.mkdir(parents=True, exist_ok=True)
        shard_path = _SHARDS_DIR / f"catalog_{cycle.upper()}.json"
        # 分片只包含对应循环的 sheets 和 cells
        cycle_upper = cycle.upper()
        shard_sheets = [
            s for s in catalog_data["sheets"]
            if s.get("cycle", "").upper() == cycle_upper
        ]
        shard_cells = [
            c for c in catalog_data["cells"]
            if _cell_belongs_to_cycle(c, cycle_upper, catalog_data["sheets"])
        ]
        shard_data = {
            "version": CATALOG_VERSION,
            "registry_version": catalog_data["registry_version"],
            "cycle": cycle_upper,
            "sheets": shard_sheets,
            "cells": shard_cells,
        }
        shard_json = _deterministic_json(shard_data)
        shard_path.write_text(shard_json, encoding="utf-8")

    return catalog_path, report_path


def _cell_belongs_to_cycle(
    cell: dict[str, Any],
    cycle: str,
    sheets: list[dict[str, Any]],
) -> bool:
    """判断 cell 是否属于指定循环。

    策略：
    1. 若 parent_addr_id 精确匹配某 sheet 的 addr_id 且该 sheet 的 cycle == target → True
    2. 若 parent_addr_id 的前缀字母（如 D1/D1-2 → 'D'）匹配 cycle → True
       （覆盖 tab 级坐标种子，其 parent 不在 catalog 但循环可由首字母推断）
    """
    parent = cell.get("parent_addr_id", "")

    # 精确匹配已有 sheet
    for sheet in sheets:
        if sheet.get("addr_id") == parent and sheet.get("cycle", "").upper() == cycle:
            return True

    # 前缀字母推断循环（如 D1/D1-2 → 首字母 'D'）
    if parent:
        first_char = parent[0].upper()
        if first_char == cycle:
            return True

    return False


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="ACNR Catalog Generator — 生成 global_catalog.json"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="使用离线缓存（不连接 DB）",
    )
    parser.add_argument(
        "--cycle",
        default="d",
        help="循环码（默认 d）",
    )
    parser.add_argument(
        "--registry-version",
        default=None,
        help="指定 registry_version（默认自动生成时间戳）",
    )
    parser.add_argument(
        "--no-shards",
        action="store_true",
        help="不生成分片文件",
    )
    args = parser.parse_args()

    print(f"[ACNR] Generating catalog (cycle={args.cycle}, offline={args.offline})")

    try:
        catalog_data, report_data, manifest_blocked = generate_catalog(
            cycle=args.cycle,
            offline=args.offline,
            registry_version=args.registry_version,
        )
    except FileNotFoundError as e:
        print(f"[ACNR] ERROR: {e}", file=sys.stderr)
        return 1

    # 写入文件
    catalog_path, report_path = write_catalog(
        catalog_data,
        report_data,
        write_shards=not args.no_shards,
        cycle=args.cycle,
    )

    # 输出摘要
    summary = report_data.get("summary", {})
    print(f"[ACNR] Done.")
    print(f"  Catalog: {catalog_path}")
    print(f"  Report:  {report_path}")
    print(f"  Sheets:  {summary.get('total_sheets', 0)}")
    print(f"  Cells:   {summary.get('total_cells', 0)}")
    print(f"  Alias conflicts: {summary.get('alias_conflict_count', 0)}")
    print(f"  Gaps:    {summary.get('gap_count', 0)}")
    print(f"  Unregistered aliases: {summary.get('unregistered_alias_count', 0)}")
    print(f"  Manifest blocked: {manifest_blocked}")

    if manifest_blocked:
        print(
            "[ACNR] WARNING: manifest_blocked=true — "
            "bulk manifest generation is completely blocked due to skip_reason entries."
        )

    # 确定性校验：计算 hash 供 CI 比对
    catalog_json = _deterministic_json(catalog_data)
    digest = hashlib.sha256(catalog_json.encode("utf-8")).hexdigest()[:16]
    print(f"  SHA256 prefix: {digest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
