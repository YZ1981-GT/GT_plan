#!/usr/bin/env python
"""ADJ() 预设第二参归一修正（幂等，spec adj-formula-repair-and-approval-gate-wiring Task 1.5）。

扫描 ``backend/data/prefill_formula_mapping.json`` 中所有 ``=ADJ('科目','类型')`` 公式，
检查第二参是否在 ``normalize_adj_type`` 的合法白名单内。

三种模式：
  --check    只检查，有非法字面量 exit 1（CI 守卫用）
  --dry-run  展示会做的修改但不写文件
  --apply    修正非法字面量并写回文件（带 round-trip 自检）

替换策略：
  同一 wp_code + block 内若存在合法的 ADJ() 预设，按 cell_ref 语义推断
  （含 'AJE' -> aje_net, 含 'RJE' -> rje_net）。无法推断时报错不修。

Usage::

    python backend/scripts/fix/fix_adj_preset_type_literals.py --check
    python backend/scripts/fix/fix_adj_preset_type_literals.py --dry-run
    python backend/scripts/fix/fix_adj_preset_type_literals.py --apply

spec: .kiro/specs/adj-formula-repair-and-approval-gate-wiring/ Requirements 2.5, Property P3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

# ---------------------------------------------------------------------------
# ADJ() regex: captures (account_code, type_literal) from =ADJ('xxx','yyy')
# Also matches without leading = (some presets omit it; prefill engine strips = anyway)
# ---------------------------------------------------------------------------
_ADJ_RE = re.compile(r"=?ADJ\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")

# ---------------------------------------------------------------------------
# White list (self-contained, mirrors adjustment_amount_source._ADJ_TYPE_NORMALIZE)
# Kept self-contained so this script can run without importing app modules.
# CI task 1.6 separately validates that this set == VALID_ADJ_TYPE_LITERALS.
# ---------------------------------------------------------------------------
_VALID_LITERALS: frozenset[str] = frozenset({
    "aje_net", "aje", "rje_net", "rje",
    "\u5ba1\u8ba1\u8c03\u6574",   # 审计调整
    "\u91cd\u5206\u7c7b",         # 重分类
})


def _infer_replacement(cell: dict[str, Any], block: dict[str, Any]) -> str | None:
    """Infer the correct ADJ type literal from cell_ref / description context.

    Returns 'aje_net' or 'rje_net' if inference succeeds, None otherwise.
    """
    cell_ref = (cell.get("cell_ref") or "").upper()
    desc = (cell.get("description") or "").upper()

    # cell_ref-based inference (strongest signal)
    if "AJE" in cell_ref or "审计调整" in cell_ref.upper():
        return "aje_net"
    if "RJE" in cell_ref or "重分类" in cell_ref.upper():
        return "rje_net"

    # description-based inference
    if "审计调整" in desc or "AJE" in desc:
        return "aje_net"
    if "重分类" in desc or "RJE" in desc:
        return "rje_net"

    # Look at neighboring cells in the same block for pattern
    for sibling in block.get("cells", []):
        if sibling is cell:
            continue
        sib_formula = sibling.get("formula") or ""
        m = _ADJ_RE.search(sib_formula)
        if m and m.group(2).strip().lower() in {v.lower() for v in _VALID_LITERALS}:
            sib_ref = (sibling.get("cell_ref") or "").upper()
            # If sibling is AJE-like, this cell is likely RJE (they come in pairs)
            if "AJE" in sib_ref:
                return "rje_net"
            if "RJE" in sib_ref:
                return "aje_net"

    return None


def scan(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan all ADJ() presets, return list of violations.

    Each violation is a dict with keys:
      wp_code, block_idx, sheet, coordinate, cell_ref, formula, bad_param, replacement
    """
    violations: list[dict[str, Any]] = []

    for wp_code, blocks in doc.items():
        if not isinstance(blocks, list):
            continue
        for bi, block in enumerate(blocks):
            for cell in block.get("cells", []):
                formula = cell.get("formula") or ""
                for m in _ADJ_RE.finditer(formula):
                    param2 = m.group(2)
                    if param2.strip().lower() not in {v.lower() for v in _VALID_LITERALS}:
                        replacement = _infer_replacement(cell, block)
                        violations.append({
                            "wp_code": wp_code,
                            "block_idx": bi,
                            "sheet": block.get("sheet") or block.get("sheet_name") or "?",
                            "coordinate": cell.get("coordinate") or "?",
                            "cell_ref": cell.get("cell_ref") or "?",
                            "formula": formula,
                            "bad_param": param2,
                            "replacement": replacement,
                        })
    return violations


def apply(doc: dict[str, Any]) -> list[str]:
    """Fix non-standard ADJ() second params in-place. Returns list of change descriptions."""
    violations = scan(doc)
    changes: list[str] = []

    for v in violations:
        if v["replacement"] is None:
            changes.append(
                f"[ERROR] {v['wp_code']} {v['coordinate']}: "
                f"cannot infer replacement for '{v['bad_param']}'"
            )
            continue

        wp_code = v["wp_code"]
        bi = v["block_idx"]
        block = doc[wp_code][bi]

        for cell in block.get("cells", []):
            formula = cell.get("formula") or ""
            if formula == v["formula"]:
                old = v["bad_param"]
                new = v["replacement"]
                cell["formula"] = formula.replace(f"'{old}'", f"'{new}'")
                changes.append(
                    f"[FIX] {wp_code} {v['coordinate']}: "
                    f"'{old}' -> '{new}' in {cell['formula']}"
                )
                break

    return changes


def validate(doc: dict[str, Any]) -> list[str]:
    """Check all ADJ() second params are valid. Returns list of error messages."""
    violations = scan(doc)
    errors: list[str] = []
    for v in violations:
        errors.append(
            f"{v['wp_code']} {v['coordinate']}: "
            f"ADJ() second param '{v['bad_param']}' not in whitelist"
        )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ADJ() preset second-param normalization (idempotent)"
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                       help="Validate only, exit 1 if violations found")
    mode.add_argument("--dry-run", action="store_true",
                       help="Show changes without writing file")
    mode.add_argument("--apply", action="store_true",
                       help="Fix violations and write file")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc: dict[str, Any] = json.loads(raw)

    # --- check mode ---
    if args.check:
        errs = validate(doc)
        if errs:
            print(f"[FAIL] {len(errs)} non-standard ADJ() second param(s):")
            for e in errs:
                print(f"  {e}")
            return 1
        # Also report current distribution as confirmation
        total_aje, total_rje, total_other = _count_distribution(doc)
        print(
            f"[OK] ADJ() preset validation passed (0 violations). "
            f"Distribution: aje_net={total_aje}, rje_net={total_rje}, other_valid={total_other}"
        )
        return 0

    # --- apply / dry-run mode ---
    changes = apply(doc)
    if changes:
        print(f"{len(changes)} change(s):")
        for c in changes:
            print(f"  {c}")
    else:
        print("No changes needed (all ADJ() second params already valid)")

    # Abort on inference failures
    if any(c.startswith("[ERROR]") for c in changes):
        print("[FAIL] Some violations could not be auto-fixed (see [ERROR] above)")
        return 1

    # Round-trip self-check: re-validate after apply
    errs = validate(doc)
    if errs:
        print("[FAIL] Round-trip self-check failed after apply:")
        for e in errs:
            print(f"  {e}")
        return 1

    if args.dry_run:
        print("[dry-run] File not written")
        return 0

    # Write back (preserve trailing newline)
    if changes:
        trailing = "\n" if raw.endswith("\n") else ""
        MAPPING_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
            encoding="utf-8",
        )
        print(f"Written to {MAPPING_PATH}")

    total_aje, total_rje, total_other = _count_distribution(doc)
    print(
        f"[OK] All passed. "
        f"Distribution: aje_net={total_aje}, rje_net={total_rje}, other_valid={total_other}"
    )
    return 0


def _count_distribution(doc: dict[str, Any]) -> tuple[int, int, int]:
    """Count ADJ() second-param distribution (aje_net, rje_net, other_valid)."""
    aje = rje = other = 0
    for wp_code, blocks in doc.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            for cell in block.get("cells", []):
                formula = cell.get("formula") or ""
                for m in _ADJ_RE.finditer(formula):
                    p2 = m.group(2).strip().lower()
                    if p2 == "aje_net":
                        aje += 1
                    elif p2 == "rje_net":
                        rje += 1
                    elif p2 in {v.lower() for v in _VALID_LITERALS}:
                        other += 1
    return aje, rje, other


if __name__ == "__main__":
    sys.exit(main())
