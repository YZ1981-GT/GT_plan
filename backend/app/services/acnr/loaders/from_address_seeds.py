"""Loader: 13 种子文件 → CellCatalogEntry。

读取 `backend/data/*_address_registry_seed.json` 文件，
将每个坐标种子转换为 CellCatalogEntry。

Requirements: 4.1, 4.3
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data"

_SEED_FILE_PATTERN = re.compile(r"^[a-z]\d*_address_registry_seed\.json$")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class CellCatalogEntry:
    """L1 CellCatalogEntry（design.md §Data Models）。"""

    addr_id: str
    parent_addr_id: str
    uri: str
    domain: str = "wp"
    cell_address: str | None = None
    semantic_label: str | None = None
    semantic_only: bool = False
    purpose: str = ""
    formula_ref: str = ""
    registry_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "addr_id": self.addr_id,
            "parent_addr_id": self.parent_addr_id,
            "uri": self.uri,
            "domain": self.domain,
            "cell_address": self.cell_address,
            "semantic_label": self.semantic_label,
            "semantic_only": self.semantic_only,
            "purpose": self.purpose,
            "formula_ref": self.formula_ref,
            "registry_version": self.registry_version,
        }


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _slugify(label: str) -> str:
    """将中文语义名转为 slug（小写，空格→'-'，去除特殊字符）。"""
    # 保留中文、字母、数字、连字符
    s = label.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\u4e00-\u9fff-]", "", s)
    return s


def _extract_parent_wp_code(wp_code: str) -> str:
    """从 sheet 级 wp_code 提取 parent（如 D2-2 → D2）。"""
    m = re.match(r"^([A-S]\d+)", wp_code)
    if m:
        return m.group(1)
    return wp_code


def _build_uri(parent: str, sheet_name: str, cell_address: str | None) -> str:
    """构建 standard profile URI。"""
    if cell_address:
        return f"wp://{parent}/{sheet_name}#{cell_address}"
    return f"wp://{parent}/{sheet_name}"


def _build_formula_ref(
    parent: str, sheet_name: str, cell_or_semantic: str | None
) -> str:
    """构建 formula_ref。"""
    if cell_or_semantic:
        return f"WP('{parent}','{sheet_name}','{cell_or_semantic}')"
    return f"WP('{parent}','{sheet_name}')"


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_cell_entries_from_seeds(
    *,
    data_dir: Path | None = None,
    registry_version: str = "",
) -> list[CellCatalogEntry]:
    """从 13 个种子文件加载 CellCatalogEntry 列表。

    Parameters
    ----------
    data_dir
        数据目录（默认 backend/data/）。
    registry_version
        catalog 版本号。

    Returns
    -------
    list[CellCatalogEntry]
        所有坐标种子转换的 Cell 条目。
    """
    base = data_dir or _DATA_DIR
    results: list[CellCatalogEntry] = []

    # 收集所有 *_address_registry_seed.json 文件
    seed_files = sorted(
        f
        for f in base.iterdir()
        if f.is_file() and _SEED_FILE_PATTERN.match(f.name)
    )

    for seed_path in seed_files:
        with open(seed_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        for sheet_entry in entries:
            wp_code = sheet_entry.get("wp_code", "")
            sheet_name = sheet_entry.get("sheet_name", "")
            coordinates = sheet_entry.get("coordinates", [])

            parent = _extract_parent_wp_code(wp_code)
            sheet_code = wp_code
            parent_addr_id = f"{parent}/{sheet_code}"

            for coord in coordinates:
                cell_address: str | None = coord.get("cell_address") or coord.get("cell_ref")
                description: str = coord.get("description", "") or coord.get("label", "")
                purpose: str = coord.get("purpose", "")
                semantic_only: bool = coord.get("semantic_only", False)

                # addr_id 构造规则（design.md §8.2–8.4）
                if semantic_only or not cell_address:
                    # 无可靠 A1 → slug(semantic_label)
                    coord_key = _slugify(description) if description else "unknown"
                    semantic_only = True
                else:
                    coord_key = cell_address

                addr_id = f"{parent}/{sheet_code}/{coord_key}"

                # URI 与 formula_ref
                uri = _build_uri(parent, sheet_name, cell_address)
                formula_ref_target = description if semantic_only else cell_address
                formula_ref = _build_formula_ref(parent, sheet_name, formula_ref_target)

                cell_entry = CellCatalogEntry(
                    addr_id=addr_id,
                    parent_addr_id=parent_addr_id,
                    uri=uri,
                    cell_address=cell_address,
                    semantic_label=description or None,
                    semantic_only=semantic_only,
                    purpose=purpose,
                    formula_ref=formula_ref,
                    registry_version=registry_version,
                )
                results.append(cell_entry)

    return results
