#!/usr/bin/env python3
"""报表↔附注勾稽 → **附注侧** logic_check 预设（Wave 3 / Task 4.3）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 1（报表↔附注只做校验，不做写值 —— 用户已拍板）
        §「Wave 0 核实结论」V12 / V13
Reqs:   3.2 / 3.3 / 7.3

做什么
------
从 ``formula_presets_seed.json`` 的 ``page_key='report:cross_check'`` 条目中提取
``NOTE('{章节}', …)`` 引用，为**该附注章节**登记同源的 ``logic_check`` 预设：

- **表达式与容差逐字沿用原条目**（同源，绝不另写一套口径 → Property 15）
- ``target_cell`` 用稳定派生 id，不与既有 1549 条中文 ``check_presets`` 撞
  ``(page_key, target_cell)``
- 无法解析出章节的条目（纯报表内恒等式）**跳过并记录**（实测 93 条中 32 条如此）
- 幂等：重复运行结果一致（``upsert_seed_presets`` 按去重键覆盖）

用法
----
    python scripts/gen/generate_note_cross_check_presets.py            # dry-run
    python scripts/gen/generate_note_cross_check_presets.py --apply    # 写回

写回后建议重跑 ``python scripts/seed/seed_formula_presets.py`` 刷新
``inventory.json``（物化 Preset Inventory）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

SEED_PATH = _BACKEND / "data" / "formula_presets" / "formula_presets_seed.json"
CROSS_CHECK_PAGE_KEY = "report:cross_check"

#: ``NOTE('五、1', '合计')`` / ``NOTE("八、22")`` 均可解析
_NOTE_RE = re.compile(r"NOTE\(\s*['\"]([^'\"]+)['\"]")


def extract_note_sections(expression: str) -> list[str]:
    """从表达式提取被引用的附注章节号（保序去重）。"""
    if not isinstance(expression, str):
        return []
    seen: list[str] = []
    for sec in _NOTE_RE.findall(expression):
        sec = sec.strip()
        if sec and sec not in seen:
            seen.append(sec)
    return seen


def derived_target_cell(section: str, origin_target_cell: str) -> str:
    """稳定派生 id（避免与中文 check_presets 撞去重键）。"""
    return f"note-crosscheck:{section}:{origin_target_cell}"


def build_entries(presets: list[dict[str, Any]]) -> tuple[list[Any], list[str]]:
    """→ ``(entries, skipped_target_cells)``（表达式/refs/容差同源）。"""
    from app.services.formula_management.preset_library import PresetEntry

    entries: list[Any] = []
    skipped: list[str] = []
    for p in presets:
        if (p.get("page_key") or "") != CROSS_CHECK_PAGE_KEY:
            continue
        expr = p.get("expression") or ""
        origin = (p.get("target_cell") or "").strip()
        sections = extract_note_sections(expr)
        if not sections:
            skipped.append(origin or "<no-target-cell>")
            continue
        for section in sections:
            entries.append(
                PresetEntry(
                    page_key=f"note:{section}",
                    target_cell=derived_target_cell(section, origin),
                    # Property 15：表达式与容差逐字同源，不另写口径
                    expression=expr,
                    formula_type=p.get("formula_type") or "logic_check",
                    refs=list(p.get("refs") or []),
                    source="note_report_cross_check",
                    description=(
                        "报表↔附注勾稽（与报表侧 "
                        f"`{CROSS_CHECK_PAGE_KEY}` 同源）："
                        f"{p.get('description') or ''}"
                    ).strip(),
                    variant=p.get("variant") or None,
                )
            )
    return entries, skipped


def run(apply: bool) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    doc = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    presets = list(doc.get("presets") or [])
    cross = [p for p in presets if (p.get("page_key") or "") == CROSS_CHECK_PAGE_KEY]

    entries, skipped = build_entries(presets)
    sections = Counter(e.page_key for e in entries)

    print("# 报表↔附注勾稽 → 附注侧 logic_check 预设")
    print()
    print(f"- `{CROSS_CHECK_PAGE_KEY}` 源条目：**{len(cross)}**")
    print(f"- 含 `NOTE('章节')` 可派生：**{len(cross) - len(skipped)}**")
    print(f"- 纯报表内恒等式（无 NOTE，跳过）：**{len(skipped)}** {skipped[:5]}")
    print(f"- 派生附注侧预设：**{len(entries)}** 条，覆盖 **{len(sections)}** 个附注章节")
    print()
    if not apply:
        print("(dry-run；加 --apply 才写回 formula_presets_seed.json)")
        return 0

    from app.services.formula_management.preset_library import upsert_seed_presets

    stats = upsert_seed_presets(entries)
    print(f"[ok] presets upserted: {stats}")
    print(
        "\n[next] 建议执行：python scripts/seed/seed_formula_presets.py"
        "（刷新 inventory.json）"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 report:cross_check 派生附注侧 logic_check 预设（幂等）"
    )
    parser.add_argument("--apply", action="store_true", help="写回 seed 文件")
    args = parser.parse_args()
    return run(args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
