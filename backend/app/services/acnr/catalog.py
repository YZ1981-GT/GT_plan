"""ACNR L1 GlobalCatalog — 只读 catalog 服务层

读取 `global_catalog.json`（懒加载 + 缓存），构建索引，
提供 list_sheets / list_cells / lookup / resolve（首期 L1 only）。

Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.3, 5.6
"""
from __future__ import annotations

import json
import logging
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Catalog 数据路径 ───────────────────────────────────────────────────────
_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "acnr" / "global_catalog.json"


class CatalogIndex:
    """内存索引，按需构建一次。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self.version: str = data.get("version", "1")
        self.registry_version: str = data.get("registry_version", "unknown")

        sheets: list[dict] = data.get("sheets", [])
        cells: list[dict] = data.get("cells", [])

        # 主索引: addr_id → entry
        self.sheets_by_addr_id: dict[str, dict] = {}
        # sheet_code → list[entry]（可能多个 → ambiguous）
        self.sheets_by_code: dict[str, list[dict]] = {}
        # alias → list[sheet entry]
        self.sheets_by_alias: dict[str, list[dict]] = {}
        # parent_addr_id → list[cell entry]
        self.cells_by_parent: dict[str, list[dict]] = {}
        # cell addr_id → entry
        self.cells_by_addr_id: dict[str, dict] = {}

        for s in sheets:
            aid = s.get("addr_id", "")
            self.sheets_by_addr_id[aid] = s

            code = s.get("sheet_code", "")
            self.sheets_by_code.setdefault(code, []).append(s)

            # 别名索引（含 sheet_name 本身作为 alias key）
            name = s.get("sheet_name", "")
            if name:
                self.sheets_by_alias.setdefault(name, []).append(s)
            for alias in s.get("sheet_name_aliases", []):
                self.sheets_by_alias.setdefault(alias, []).append(s)

        for c in cells:
            aid = c.get("addr_id", "")
            self.cells_by_addr_id[aid] = c
            parent = c.get("parent_addr_id", "")
            self.cells_by_parent.setdefault(parent, []).append(c)

        # 合并全部条目（sheet + cell）用于 fuzzy 搜索
        self._all_entries: list[dict] = sheets + cells


# ─── 全局 catalog 单例（懒加载） ─────────────────────────────────────────────
_catalog: CatalogIndex | None = None


def _load_catalog() -> CatalogIndex:
    """懒加载 catalog JSON 并构建索引。"""
    global _catalog
    if _catalog is not None:
        return _catalog

    catalog_path = Path(os.environ.get("ACNR_CATALOG_PATH", str(_CATALOG_PATH)))
    if not catalog_path.exists():
        logger.warning("ACNR catalog 文件不存在: %s，使用空 catalog", catalog_path)
        _catalog = CatalogIndex({"version": "1", "registry_version": "unknown", "sheets": [], "cells": []})
        return _catalog

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _catalog = CatalogIndex(data)
    logger.info(
        "ACNR catalog 加载完成: version=%s, sheets=%d, cells=%d",
        _catalog.registry_version,
        len(_catalog.sheets_by_addr_id),
        len(_catalog.cells_by_addr_id),
    )
    return _catalog


def get_catalog() -> CatalogIndex:
    """获取 catalog 索引（已缓存）。"""
    return _load_catalog()


def reload_catalog() -> CatalogIndex:
    """强制重新加载 catalog（用于测试或热重载）。"""
    global _catalog
    _catalog = None
    return _load_catalog()


# ─── 公共服务方法 ─────────────────────────────────────────────────────────────


def list_sheets(
    cycle: str | None = None,
    import_export_only: bool = False,
) -> list[dict]:
    """列出 sheet 目录条目，可按 cycle 和 import_export 过滤。

    Requirements: R14.1, R15.3
    """
    cat = get_catalog()
    result = list(cat.sheets_by_addr_id.values())

    if cycle:
        result = [s for s in result if s.get("cycle", "").upper() == cycle.upper()]
    if import_export_only:
        result = [s for s in result if s.get("import_export", {}).get("enabled")]

    return result


def list_cells(sheet_addr_id: str) -> list[dict]:
    """列出某 sheet 下的所有 cell 条目。

    Requirements: R14.1, R15.3
    """
    cat = get_catalog()
    return cat.cells_by_parent.get(sheet_addr_id, [])


def lookup(
    wp_code: str | None = None,
    sheet: str | None = None,
    cell_desc: str | None = None,
) -> dict:
    """正向查找：按 wp_code / sheet_code / cell_desc 组合查询。

    返回统一响应契约 data 部分：
      - hit: {found:true, addr_id, entry_type, ...}
      - miss: {found:false, candidates:[...]}
      - ambiguous: {found:false, error:"ambiguous", candidates:[...]}

    Requirements: R2.1, R2.2, R2.3, R2.4
    """
    cat = get_catalog()

    # 1. 尝试按 sheet_code 精确查找
    if sheet:
        matches = cat.sheets_by_code.get(sheet, [])

        # 如果有 wp_code 约束，进一步过滤
        if wp_code and matches:
            matches = [m for m in matches if m.get("parent_wp_code") == wp_code]

        if len(matches) == 1:
            entry = matches[0]
            # 如果指定了 cell_desc，在该 sheet 下搜索 cell
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")

        if len(matches) > 1:
            return _ambiguous_response(matches)

    # 2. 仅提供 wp_code 时：查找对应 parent_wp_code 的 sheets
    if wp_code and not sheet:
        matches = [
            s for s in cat.sheets_by_addr_id.values()
            if s.get("parent_wp_code") == wp_code
        ]
        if len(matches) == 1:
            entry = matches[0]
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")
        if len(matches) > 1:
            # wp_code 下多个 sheet 是正常的（bundle），返回 ambiguous
            return _ambiguous_response(matches)

    # 3. 别名反查
    if sheet:
        alias_matches = cat.sheets_by_alias.get(sheet, [])
        if wp_code and alias_matches:
            alias_matches = [m for m in alias_matches if m.get("parent_wp_code") == wp_code]
        if len(alias_matches) == 1:
            entry = alias_matches[0]
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")
        if len(alias_matches) > 1:
            return _ambiguous_response(alias_matches)

    # 4. Miss — 返回相近候选（≤5）
    query = " ".join(filter(None, [wp_code, sheet, cell_desc]))
    candidates = _find_candidates(query, max_results=5)
    return {"found": False, "candidates": candidates}


def resolve(
    uri: str | None = None,
    formula_ref: str | None = None,
    addr_id: str | None = None,
    index_ref: str | None = None,
) -> dict:
    """统一解析入口（首期 M0 只读 L1）。

    输入接受四种语法之一，输出统一响应契约。
    决策树（M0 精简版）：
      1. 规范化输入 → 推导 addr_id
      2. L1 Cell 精确 match
      3. L1 Sheet + aliases match
      4. miss → candidates ≤ 5

    Requirements: R5.1, R5.3, R5.5, R5.6
    """
    cat = get_catalog()
    resolved_addr_id: str | None = None

    # 1. 规范化输入 → 推导 addr_id
    if addr_id:
        resolved_addr_id = addr_id
    elif uri:
        resolved_addr_id = _uri_to_addr_id(uri)
    elif formula_ref:
        resolved_addr_id = _formula_ref_to_addr_id(formula_ref)
    elif index_ref:
        resolved_addr_id = _index_ref_to_addr_id(index_ref)

    if not resolved_addr_id:
        # 无法解析输入
        query = uri or formula_ref or addr_id or index_ref or ""
        candidates = _find_candidates(query, max_results=5)
        return {"found": False, "candidates": candidates}

    # 2. L1 Cell 精确 match
    cell = cat.cells_by_addr_id.get(resolved_addr_id)
    if cell:
        return _hit_cell_response(cell)

    # 3. L1 Sheet 精确 match
    sheet_entry = cat.sheets_by_addr_id.get(resolved_addr_id)
    if sheet_entry:
        return _hit_response(sheet_entry, "sheet")

    # 4. 尝试按 sheet_code 部分匹配（addr_id 可能只有 sheet 部分）
    # 例如 addr_id="D2-2" 实际应该查 "D2/D2-2"
    parts = resolved_addr_id.split("/")
    if len(parts) == 1:
        # 可能是裸 sheet_code
        code_matches = cat.sheets_by_code.get(parts[0], [])
        if len(code_matches) == 1:
            return _hit_response(code_matches[0], "sheet")
        if len(code_matches) > 1:
            return _ambiguous_response(code_matches)

    # 5. miss
    candidates = _find_candidates(resolved_addr_id, max_results=5)
    return {"found": False, "candidates": candidates}


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────


def _lookup_cell_in_sheet(sheet_entry: dict, cell_desc: str) -> dict:
    """在某个 sheet 下按 cell_desc 搜索 cell。"""
    cat = get_catalog()
    parent_id = sheet_entry.get("addr_id", "")
    cells = cat.cells_by_parent.get(parent_id, [])

    # 精确匹配 cell_address
    exact = [c for c in cells if c.get("cell_address") == cell_desc]
    if len(exact) == 1:
        return _hit_cell_response(exact[0])

    # semantic_label 包含匹配
    semantic = [c for c in cells if cell_desc in (c.get("semantic_label") or "")]
    if len(semantic) == 1:
        return _hit_cell_response(semantic[0])
    if len(semantic) > 1:
        return _ambiguous_response(semantic)

    # miss
    candidates = _find_candidates(
        f"{parent_id}/{cell_desc}",
        max_results=5,
        scope_entries=cells,
    )
    return {"found": False, "candidates": candidates}


def _hit_response(entry: dict, entry_type: str) -> dict:
    """构造命中响应（sheet 级）。"""
    result: dict[str, Any] = {
        "found": True,
        "addr_id": entry.get("addr_id"),
        "entry_type": entry_type,
        "sheet_name": entry.get("sheet_name"),
        "parent_wp_code": entry.get("parent_wp_code"),
        "sheet_code": entry.get("sheet_code"),
    }
    # 附带 import_export 信息（如有）
    ie = entry.get("import_export")
    if ie:
        result["import_export"] = ie
    return result


def _hit_cell_response(cell: dict) -> dict:
    """构造命中响应（cell 级）。"""
    return {
        "found": True,
        "addr_id": cell.get("addr_id"),
        "entry_type": "cell",
        "cell_address": cell.get("cell_address"),
        "semantic_label": cell.get("semantic_label"),
        "formula_ref": cell.get("formula_ref"),
        "uri": cell.get("uri"),
        "jump_route": _build_jump_route(cell),
    }


def _ambiguous_response(entries: list[dict]) -> dict:
    """构造 ambiguous 响应。"""
    candidates = [
        {
            "addr_id": e.get("addr_id"),
            "display_label": e.get("display_label") or e.get("sheet_name") or e.get("semantic_label") or e.get("addr_id"),
            "score": 1.0,
        }
        for e in entries
    ]
    return {"found": False, "error": "ambiguous", "candidates": candidates}


def _find_candidates(
    query: str,
    max_results: int = 5,
    scope_entries: list[dict] | None = None,
) -> list[dict]:
    """模糊搜索候选项（≤ max_results）。"""
    if not query:
        return []

    cat = get_catalog()
    entries = scope_entries if scope_entries is not None else cat._all_entries
    query_lower = query.lower()

    scored: list[tuple[float, dict]] = []
    for e in entries:
        # 取多个字段做比较
        targets = [
            e.get("addr_id", ""),
            e.get("sheet_code", ""),
            e.get("sheet_name", ""),
            e.get("semantic_label", ""),
            e.get("cell_address", ""),
        ]
        # 别名也参与
        for alias in e.get("sheet_name_aliases", []):
            targets.append(alias)

        best_score = 0.0
        for t in targets:
            if not t:
                continue
            t_lower = t.lower()
            # 前缀匹配加分
            if t_lower.startswith(query_lower) or query_lower.startswith(t_lower):
                score = 0.8
            else:
                score = SequenceMatcher(None, query_lower, t_lower).ratio()
            best_score = max(best_score, score)

        if best_score > 0.3:
            scored.append((best_score, e))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "addr_id": e.get("addr_id"),
            "display_label": e.get("display_label") or e.get("sheet_name") or e.get("semantic_label") or e.get("addr_id"),
            "score": round(score, 3),
        }
        for score, e in scored[:max_results]
    ]


def _build_jump_route(cell: dict) -> str | None:
    """从 cell 条目构建 jump_route。"""
    cat = get_catalog()
    parent_id = cell.get("parent_addr_id", "")
    parent = cat.sheets_by_addr_id.get(parent_id)
    if parent:
        template = parent.get("jump_route_template", "")
        # M0 不填 wp_id（无 ProjectBinding），保留模板
        return template
    return None


def _uri_to_addr_id(uri: str) -> str | None:
    """从 URI 推导 addr_id。

    standard: wp://{parent}/{sheet_name}#{cell} → {parent}/{sheet_code}/{cell}
    custom_flat: wp://{wp_code}/{cell} → 需要查索引
    """
    if not uri.startswith("wp://"):
        return None

    body = uri[5:]  # 去掉 "wp://"
    cat = get_catalog()

    # 带 # 分隔符 → cell 级
    if "#" in body:
        path_part, cell_part = body.rsplit("#", 1)
        parts = path_part.split("/")
        if len(parts) == 2:
            parent, sheet_name = parts
            # 通过 parent + sheet_name 找到 sheet 的 addr_id
            for s in cat.sheets_by_addr_id.values():
                if s.get("parent_wp_code") == parent and s.get("sheet_name") == sheet_name:
                    return f"{s['addr_id']}/{cell_part}"
            # fallback: 尝试 sheet_code 匹配
            for s in cat.sheets_by_addr_id.values():
                if s.get("parent_wp_code") == parent and s.get("sheet_code") == sheet_name:
                    return f"{s['addr_id']}/{cell_part}"
            # fallback: 尝试别名匹配
            alias_hits = cat.sheets_by_alias.get(sheet_name, [])
            parent_filtered = [s for s in alias_hits if s.get("parent_wp_code") == parent]
            if len(parent_filtered) == 1:
                return f"{parent_filtered[0]['addr_id']}/{cell_part}"
            # fallback: 尝试 sheet_name 包含 sheet_code 的模式匹配
            # 例如 "明细表D2-2" 对应 sheet_code="D2-2"
            for s in cat.sheets_by_addr_id.values():
                if s.get("parent_wp_code") == parent:
                    code = s.get("sheet_code", "")
                    if code and code in sheet_name:
                        return f"{s['addr_id']}/{cell_part}"
        elif len(parts) == 1:
            # custom_flat: wp://{wp_code}#{cell}
            wp_code = parts[0]
            matches = cat.sheets_by_code.get(wp_code, [])
            if len(matches) == 1:
                return f"{matches[0]['addr_id']}/{cell_part}"
    else:
        # 无 # → sheet 级
        parts = body.split("/")
        if len(parts) == 2:
            parent, sheet_name = parts
            for s in cat.sheets_by_addr_id.values():
                if s.get("parent_wp_code") == parent and s.get("sheet_name") == sheet_name:
                    return s["addr_id"]
                if s.get("parent_wp_code") == parent and s.get("sheet_code") == sheet_name:
                    return s["addr_id"]
            # 别名
            alias_hits = cat.sheets_by_alias.get(sheet_name, [])
            parent_filtered = [s for s in alias_hits if s.get("parent_wp_code") == parent]
            if len(parent_filtered) == 1:
                return parent_filtered[0]["addr_id"]
            # sheet_name 包含 sheet_code
            for s in cat.sheets_by_addr_id.values():
                if s.get("parent_wp_code") == parent:
                    code = s.get("sheet_code", "")
                    if code and code in sheet_name:
                        return s["addr_id"]
        elif len(parts) == 1:
            # 可能是裸 wp_code
            return parts[0]

    return None


def _formula_ref_to_addr_id(formula_ref: str) -> str | None:
    """从 formula_ref 推导 addr_id。

    WP('D2','明细表D2-2','E100') → D2/D2-2/E100
    WP('D2','明细表D2-2') → D2/D2-2
    WP('CUST-01','B7') → CUST-01（custom_flat，需查索引）
    """
    if not formula_ref.startswith("WP(") and not formula_ref.startswith("PREV("):
        return None

    # 提取参数
    start = formula_ref.index("(") + 1
    end = formula_ref.rindex(")")
    args_str = formula_ref[start:end]

    # 简单解析单引号分隔的参数
    args: list[str] = []
    in_quote = False
    current = ""
    for ch in args_str:
        if ch == "'" and not in_quote:
            in_quote = True
        elif ch == "'" and in_quote:
            in_quote = False
            args.append(current)
            current = ""
        elif in_quote:
            current += ch

    cat = get_catalog()

    if len(args) == 3:
        # 三参: WP(parent, sheet_name, cell|semantic)
        parent, sheet_name, cell_or_semantic = args
        # 找 sheet
        for s in cat.sheets_by_addr_id.values():
            if s.get("parent_wp_code") == parent and s.get("sheet_name") == sheet_name:
                return f"{s['addr_id']}/{cell_or_semantic}"
            if s.get("parent_wp_code") == parent and s.get("sheet_code") == sheet_name:
                return f"{s['addr_id']}/{cell_or_semantic}"
        # 别名匹配
        alias_hits = cat.sheets_by_alias.get(sheet_name, [])
        parent_filtered = [s for s in alias_hits if s.get("parent_wp_code") == parent]
        if len(parent_filtered) == 1:
            return f"{parent_filtered[0]['addr_id']}/{cell_or_semantic}"
        # sheet_name 包含 sheet_code 的模式匹配
        for s in cat.sheets_by_addr_id.values():
            if s.get("parent_wp_code") == parent:
                code = s.get("sheet_code", "")
                if code and code in sheet_name:
                    return f"{s['addr_id']}/{cell_or_semantic}"
        # fallback: 直接拼
        return f"{parent}/{sheet_name}/{cell_or_semantic}"

    elif len(args) == 2:
        # 二参: WP(parent, sheet_name) or WP(wp_code, cell)
        first, second = args
        # 优先尝试 standard: parent + sheet_name
        for s in cat.sheets_by_addr_id.values():
            if s.get("parent_wp_code") == first and s.get("sheet_name") == second:
                return s["addr_id"]
            if s.get("parent_wp_code") == first and s.get("sheet_code") == second:
                return s["addr_id"]
        # 别名匹配
        alias_hits = cat.sheets_by_alias.get(second, [])
        parent_filtered = [s for s in alias_hits if s.get("parent_wp_code") == first]
        if len(parent_filtered) == 1:
            return parent_filtered[0]["addr_id"]
        # sheet_name 包含 sheet_code
        for s in cat.sheets_by_addr_id.values():
            if s.get("parent_wp_code") == first:
                code = s.get("sheet_code", "")
                if code and code in second:
                    return s["addr_id"]
        # 尝试 custom_flat: wp_code + cell
        matches = cat.sheets_by_code.get(first, [])
        if len(matches) == 1:
            return f"{matches[0]['addr_id']}/{second}"
        # fallback
        return f"{first}/{second}"

    return None


def _index_ref_to_addr_id(index_ref: str) -> str | None:
    """从索引命名空间语法推导 addr_id。

    cell:D2-2!E100 → D2/D2-2/E100
    wp:D2-2 → D2/D2-2
    sheet:D2-2 → D2/D2-2
    TB:1001 → 非 wp 域，首期返回 None（委托 V1）
    """
    if ":" not in index_ref:
        return None

    ns, target = index_ref.split(":", 1)
    ns_lower = ns.lower()
    cat = get_catalog()

    if ns_lower == "cell":
        # cell:D2-2!E100 → sheet_code=D2-2, cell=E100
        if "!" in target:
            sheet_code, cell = target.split("!", 1)
            matches = cat.sheets_by_code.get(sheet_code, [])
            if len(matches) == 1:
                return f"{matches[0]['addr_id']}/{cell}"
        return None

    elif ns_lower in ("wp", "sheet"):
        # wp:D2-2 / sheet:D2-2 → sheet_code=D2-2
        matches = cat.sheets_by_code.get(target, [])
        if len(matches) == 1:
            return matches[0]["addr_id"]
        return None

    # TB/Note/Adj/Att/EQCR/Calc/Sample/Confirm → 非 wp 域，M0 不解析
    return None
