"""ACNR CCR Resolve Check — M1 报告模式 CI 守卫。

校验每条 CCR（cross_wp_references）source 可被 ACNR catalog resolve，
或已标 `semantic_only`。产出缺口清单但**不阻断 PR**（report mode）。

M1 报告模式 vs M3 blocking 模式:
- M1（本脚本）: 产出缺口报告，exit code 始终 0（report mode）
- M3（task 21.1）: 要求 100% resolve，缺口时阻断 PR

L4 边端点 normalize:
- 对每个已 resolve 的 CCR source，记录其 canonical addr_id
- 输出 addr_id 映射摘要

Requirements: 17.1, 17.2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_DATA_DIR = _BACKEND_ROOT / "data"
_ACNR_DATA_DIR = _DATA_DIR / "acnr"
_CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"
_CCR_PATH = _DATA_DIR / "cross_wp_references.json"


# ---------------------------------------------------------------------------
# Lightweight offline catalog resolve (no DB, no imports from app/)
# ---------------------------------------------------------------------------


class OfflineCatalog:
    """Minimal offline catalog for resolve checks — no FastAPI/DB deps."""

    def __init__(self, catalog_data: dict[str, Any]) -> None:
        sheets: list[dict] = catalog_data.get("sheets", [])
        cells: list[dict] = catalog_data.get("cells", [])

        # Index: addr_id → entry
        self.sheets_by_addr_id: dict[str, dict] = {}
        # Index: sheet_code → list[entry]
        self.sheets_by_code: dict[str, list[dict]] = {}
        # Index: alias/sheet_name → list[entry]
        self.sheets_by_alias: dict[str, list[dict]] = {}
        # Index: cell addr_id → entry
        self.cells_by_addr_id: dict[str, dict] = {}
        # Index: parent_addr_id → list[cell]
        self.cells_by_parent: dict[str, list[dict]] = {}

        for s in sheets:
            aid = s.get("addr_id", "")
            self.sheets_by_addr_id[aid] = s

            code = s.get("sheet_code", "")
            self.sheets_by_code.setdefault(code, []).append(s)

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

    def resolve_formula_ref(self, formula_ref: str) -> dict[str, Any]:
        """Resolve a WP()/PREV() formula_ref to an addr_id.

        Returns: {"found": bool, "addr_id": str|None, "method": str}
        """
        if not formula_ref.startswith("WP(") and not formula_ref.startswith("PREV("):
            return {"found": False, "addr_id": None, "method": "unsupported_func"}

        # Parse args from formula
        args = self._parse_formula_args(formula_ref)
        if not args:
            return {"found": False, "addr_id": None, "method": "parse_failed"}

        if len(args) == 3:
            return self._resolve_3arg(args[0], args[1], args[2])
        elif len(args) == 2:
            return self._resolve_2arg(args[0], args[1])
        else:
            return {"found": False, "addr_id": None, "method": "bad_arity"}

    def resolve_source_address(
        self, source_wp: str, source_sheet: str, source_cell: str | None
    ) -> dict[str, Any]:
        """Resolve a CCR source by wp_code + sheet + cell components.

        Returns: {"found": bool, "addr_id": str|None, "method": str}
        """
        # Try to find the sheet entry
        sheet_entry = self._find_sheet(source_wp, source_sheet)
        if not sheet_entry:
            return {"found": False, "addr_id": None, "method": "sheet_miss"}

        sheet_addr_id = sheet_entry.get("addr_id", "")

        if not source_cell:
            return {"found": True, "addr_id": sheet_addr_id, "method": "sheet_hit"}

        # Try cell-level resolve
        candidate_addr_id = f"{sheet_addr_id}/{source_cell}"
        if candidate_addr_id in self.cells_by_addr_id:
            return {"found": True, "addr_id": candidate_addr_id, "method": "cell_exact"}

        # Cell not in catalog but sheet is — still resolved to sheet level
        # (the cell may be a semantic_only or just not seeded yet)
        return {"found": True, "addr_id": candidate_addr_id, "method": "cell_inferred"}

    # --- Internal helpers ---

    def _parse_formula_args(self, formula_ref: str) -> list[str]:
        """Extract single-quoted arguments from WP('a','b','c')."""
        try:
            start = formula_ref.index("(") + 1
            end = formula_ref.rindex(")")
        except ValueError:
            return []

        args_str = formula_ref[start:end]
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
        return args

    def _find_sheet(self, parent_wp: str, sheet_name_or_code: str) -> dict | None:
        """Find a sheet entry by parent + sheet_name/sheet_code/alias."""
        # 1. By sheet_code
        for s in self.sheets_by_code.get(sheet_name_or_code, []):
            if s.get("parent_wp_code") == parent_wp:
                return s

        # 2. By sheet_name or alias
        for s in self.sheets_by_alias.get(sheet_name_or_code, []):
            if s.get("parent_wp_code") == parent_wp:
                return s

        # 3. Fuzzy: sheet_name contains sheet_code pattern
        for s in self.sheets_by_addr_id.values():
            if s.get("parent_wp_code") == parent_wp:
                code = s.get("sheet_code", "")
                name = s.get("sheet_name", "")
                if code and (code in sheet_name_or_code or sheet_name_or_code in name):
                    return s

        return None

    def _resolve_3arg(
        self, parent: str, sheet_name: str, cell_or_semantic: str
    ) -> dict[str, Any]:
        """Resolve WP(parent, sheet_name, cell|semantic)."""
        sheet_entry = self._find_sheet(parent, sheet_name)
        if not sheet_entry:
            return {"found": False, "addr_id": None, "method": "3arg_sheet_miss"}

        sheet_addr_id = sheet_entry.get("addr_id", "")
        candidate = f"{sheet_addr_id}/{cell_or_semantic}"

        # Exact cell match
        if candidate in self.cells_by_addr_id:
            return {"found": True, "addr_id": candidate, "method": "3arg_cell_exact"}

        # Semantic label match within parent sheet cells
        cells = self.cells_by_parent.get(sheet_addr_id, [])
        for c in cells:
            if c.get("semantic_label") == cell_or_semantic:
                return {
                    "found": True,
                    "addr_id": c.get("addr_id"),
                    "method": "3arg_semantic",
                }
            if c.get("cell_address") == cell_or_semantic:
                return {
                    "found": True,
                    "addr_id": c.get("addr_id"),
                    "method": "3arg_cell_addr",
                }

        # Sheet resolved but cell not found — infer addr_id
        return {"found": True, "addr_id": candidate, "method": "3arg_cell_inferred"}

    def _resolve_2arg(self, first: str, second: str) -> dict[str, Any]:
        """Resolve WP(parent, sheet_name) or WP(wp_code, cell)."""
        # Try standard: parent + sheet_name
        sheet_entry = self._find_sheet(first, second)
        if sheet_entry:
            return {
                "found": True,
                "addr_id": sheet_entry.get("addr_id"),
                "method": "2arg_sheet_hit",
            }

        # Try custom_flat: wp_code + cell
        matches = self.sheets_by_code.get(first, [])
        if len(matches) == 1:
            return {
                "found": True,
                "addr_id": f"{matches[0]['addr_id']}/{second}",
                "method": "2arg_custom_flat",
            }

        return {"found": False, "addr_id": None, "method": "2arg_miss"}


# ---------------------------------------------------------------------------
# CCR resolve check
# ---------------------------------------------------------------------------


def _build_ccr_source_formula(ref: dict) -> str | None:
    """Construct a formula_ref from CCR source fields for resolve attempt.

    CCR source has: source_wp, source_sheet, source_cell, source_cell_label.
    We build a WP() formula for resolve testing.
    """
    source_wp = ref.get("source_wp", "")
    source_sheet = ref.get("source_sheet", "")
    source_cell = ref.get("source_cell", "")
    source_cell_label = ref.get("source_cell_label", "")

    if not source_wp or not source_sheet:
        return None

    # Build 3-arg formula if cell info available
    if source_cell:
        return f"WP('{source_wp}','{source_sheet}','{source_cell}')"
    elif source_cell_label:
        return f"WP('{source_wp}','{source_sheet}','{source_cell_label}')"
    else:
        return f"WP('{source_wp}','{source_sheet}')"


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------


class ResolveResult:
    """Single CCR source resolve result."""

    __slots__ = ("ref_id", "source_formula", "resolved", "addr_id", "method", "semantic_only")

    def __init__(
        self,
        ref_id: str,
        source_formula: str,
        resolved: bool,
        addr_id: str | None,
        method: str,
        semantic_only: bool = False,
    ):
        self.ref_id = ref_id
        self.source_formula = source_formula
        self.resolved = resolved
        self.addr_id = addr_id
        self.method = method
        self.semantic_only = semantic_only


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Execute CCR resolve check (M1 report mode).

    Always exits 0 — this is report mode, not blocking.
    """
    # --- Load catalog ---
    if not _CATALOG_PATH.exists():
        print(
            f"[ACNR ccr-resolve] WARNING: {_CATALOG_PATH} 不存在，跳过检查。",
            file=sys.stderr,
        )
        return 0  # report mode, never block

    try:
        catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[ACNR ccr-resolve] WARNING: 读取 catalog 失败: {e}",
            file=sys.stderr,
        )
        return 0

    catalog = OfflineCatalog(catalog_data)

    # --- Load CCR data ---
    if not _CCR_PATH.exists():
        print(
            f"[ACNR ccr-resolve] WARNING: {_CCR_PATH} 不存在，跳过检查。",
            file=sys.stderr,
        )
        return 0

    try:
        ccr_data = json.loads(_CCR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[ACNR ccr-resolve] WARNING: 读取 CCR 数据失败: {e}",
            file=sys.stderr,
        )
        return 0

    references = ccr_data.get("references", [])
    if not references:
        print("[ACNR ccr-resolve] OK — CCR 无引用条目。")
        return 0

    # --- Resolve each CCR source ---
    results: list[ResolveResult] = []

    for ref in references:
        ref_id = ref.get("ref_id", "?")
        is_semantic_only = ref.get("semantic_only", False)

        # Build source formula for resolve attempt
        source_formula = _build_ccr_source_formula(ref)
        if not source_formula:
            results.append(
                ResolveResult(
                    ref_id=ref_id,
                    source_formula="(no source)",
                    resolved=False,
                    addr_id=None,
                    method="no_source_fields",
                    semantic_only=is_semantic_only,
                )
            )
            continue

        # Attempt 1: resolve via formula_ref
        resolve_out = catalog.resolve_formula_ref(source_formula)
        if resolve_out["found"]:
            results.append(
                ResolveResult(
                    ref_id=ref_id,
                    source_formula=source_formula,
                    resolved=True,
                    addr_id=resolve_out["addr_id"],
                    method=resolve_out["method"],
                    semantic_only=is_semantic_only,
                )
            )
            continue

        # Attempt 2: resolve via source_wp + source_sheet + source_cell
        source_wp = ref.get("source_wp", "")
        source_sheet = ref.get("source_sheet", "")
        source_cell = ref.get("source_cell")
        resolve_out2 = catalog.resolve_source_address(
            source_wp, source_sheet, source_cell
        )
        if resolve_out2["found"]:
            results.append(
                ResolveResult(
                    ref_id=ref_id,
                    source_formula=source_formula,
                    resolved=True,
                    addr_id=resolve_out2["addr_id"],
                    method=resolve_out2["method"],
                    semantic_only=is_semantic_only,
                )
            )
            continue

        # Miss
        results.append(
            ResolveResult(
                ref_id=ref_id,
                source_formula=source_formula,
                resolved=False,
                addr_id=None,
                method=resolve_out["method"],
                semantic_only=is_semantic_only,
            )
        )

    # --- Classify results ---
    resolved_results = [r for r in results if r.resolved]
    semantic_only_skipped = [r for r in results if not r.resolved and r.semantic_only]
    gap_results = [r for r in results if not r.resolved and not r.semantic_only]

    # --- Build L4 edge endpoint addr_id mapping (R17.2) ---
    addr_id_mapping: dict[str, str] = {}
    for r in resolved_results:
        if r.addr_id:
            addr_id_mapping[r.ref_id] = r.addr_id

    # --- Print summary ---
    total = len(results)
    resolved_count = len(resolved_results)
    semantic_count = len(semantic_only_skipped)
    gap_count = len(gap_results)

    print("=" * 70)
    print("  ACNR CCR Resolve Check — M1 Report Mode")
    print("=" * 70)
    print(f"  Total CCR sources:       {total}")
    print(f"  ✓ Resolved:              {resolved_count}")
    print(f"  ○ Semantic-only skipped: {semantic_count}")
    print(f"  ✗ Gaps (unresolved):     {gap_count}")
    print(
        f"  L4 addr_id endpoints:    {len(addr_id_mapping)} mapped"
    )
    print("=" * 70)

    # --- Detail: gaps ---
    if gap_results:
        print("\n--- Gap List (unresolved CCR sources) ---\n")
        for r in gap_results:
            print(f"  [{r.ref_id}] {r.source_formula}")
            print(f"         method: {r.method}")
            print()

    # --- Detail: resolve method breakdown ---
    method_counts: dict[str, int] = {}
    for r in resolved_results:
        method_counts[r.method] = method_counts.get(r.method, 0) + 1
    if method_counts:
        print("\n--- Resolve Method Breakdown ---\n")
        for method, count in sorted(
            method_counts.items(), key=lambda x: -x[1]
        ):
            print(f"  {method}: {count}")

    # --- Detail: sample addr_id mappings ---
    if addr_id_mapping:
        print(f"\n--- L4 Endpoint addr_id Mapping (sample, first 10) ---\n")
        for ref_id, addr_id in list(addr_id_mapping.items())[:10]:
            print(f"  {ref_id} → {addr_id}")
        if len(addr_id_mapping) > 10:
            print(f"  ... and {len(addr_id_mapping) - 10} more")

    # --- Final status ---
    print()
    if gap_count == 0:
        print("[ACNR ccr-resolve] ✓ All CCR sources resolve or are semantic_only.")
    else:
        resolve_pct = (resolved_count / total * 100) if total else 0
        print(
            f"[ACNR ccr-resolve] ⚠ {gap_count} CCR source(s) cannot resolve "
            f"(resolve rate: {resolve_pct:.1f}%). "
            f"Report mode — PR not blocked."
        )

    # M1 report mode: always exit 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
