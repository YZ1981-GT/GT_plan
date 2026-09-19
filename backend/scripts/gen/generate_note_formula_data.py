#!/usr/bin/env python3
"""附注公式数据生成器（Wave 3 / Task 4.1 + 4.2）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 2（合计只登记预设 + 追溯标注，不写公式 binding）
        决策 3（``source='formula'`` + ``formula_kind='sum'``，不新增 source 枚举）
        决策 4（人工/试算表优先，不覆盖）
        §「Wave 0 核实结论」V2 / V3 / V4 / V7 / V8 / V10 / V12
Reqs:   1.1 / 1.4 / 2.1 / 2.2 / 2.4 / 5.1 / 5.2 / 5.3 / 5.4 / 7.1 / 9.5

做什么
------
1. 读 ``note_template_{soe,listed}.json``（行序 + headers）与
   ``note_template_bindings.json``（列语义 + 既有 cell binding），按
   ``section_number`` 配对（listed 优先，镜像 bindings 生成器的合并口径 §V3）。
2. 调 ``note_formula_derivation`` 纯函数派生：
   - **变动表恒等式**（期末 = 期初 + 增 − 减）→ 写 binding（仅覆盖当前
     ``manual`` + ``todo`` 的候选格）+ 登记预设
   - **合计/小计求和** → **只**加追溯标注 + 登记预设（决策 2 硬约束：生成路径
     第二遍求值不跳过合计行，写公式 binding 会与 ``_backfill_totals`` 双写）
3. 幂等写回两个数据文件 + 产出覆盖率报告。

用法
----
    python scripts/gen/generate_note_formula_data.py            # dry-run
    python scripts/gen/generate_note_formula_data.py --apply    # 备份 + 写回

**写回后必须**跑 ``python scripts/normalize_note_bindings.py --write``
（补国企 legacy_aliases，否则变体矩阵测试会失败）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.note_formula_derivation import (  # noqa: E402
    DerivationResult,
    FormulaSpec,
    derive_note_formulas,
    is_total_row,
)

DATA = _BACKEND / "data"
BINDINGS_PATH = DATA / "note_template_bindings.json"
BACKUP_DIR = DATA / "note_template_bindings_backup"
REPORT_PATH = DATA / "note_formula_coverage_report.md"
TEMPLATES = {
    "soe": DATA / "note_template_soe.json",
    "listed": DATA / "note_template_listed.json",
}

#: 与 bindings 生成器一致：同 section_number 时 listed 优先（覆盖率更高）
VARIANT_PRIORITY = ("listed", "soe")

DERIVED_BY_MOVEMENT = "movement_identity"
DERIVED_BY_SUM = "sum_total"


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_preserving_newline(path: Path, payload: Any) -> str:
    """序列化，保留原文件的结尾换行约定（幂等前提）。"""
    raw = path.read_text(encoding="utf-8")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text + "\n" if raw.endswith("\n") else text


# ---------------------------------------------------------------------------
# 配对：section_number → (variant, template_section)
# ---------------------------------------------------------------------------


def build_section_pairs(
    templates: dict[str, Any], bindings: dict[str, Any]
) -> tuple[dict[str, tuple[str, dict]], list[str]]:
    """为每个 binding 章节找出其结构来源模板（listed 优先，§V3）。

    Returns:
        ``(pairs, unpaired)``；``pairs[section_number] = (variant, template_section)``
    """
    by_variant: dict[str, dict[str, dict]] = {}
    for variant, tpl in templates.items():
        idx: dict[str, dict] = {}
        for sec in tpl.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            num = sec.get("section_number")
            if isinstance(num, str) and num:
                idx.setdefault(num, sec)
        by_variant[variant] = idx

    pairs: dict[str, tuple[str, dict]] = {}
    unpaired: list[str] = []
    for section in (bindings.get("bindings") or {}):
        for variant in VARIANT_PRIORITY:
            sec = by_variant.get(variant, {}).get(section)
            if sec is not None:
                pairs[section] = (variant, sec)
                break
        else:
            unpaired.append(section)
    return pairs, unpaired


def _structure_aligned(template_section: dict, binding_section: dict) -> str | None:
    """结构对齐校验；对齐返回 None，否则返回 reason。"""
    t_tables = template_section.get("tables")
    b_tables = binding_section.get("tables")
    if not isinstance(t_tables, list) or not isinstance(b_tables, list):
        return "tables_missing"
    if len(t_tables) != len(b_tables):
        return "table_count_mismatch"
    for tt, bt in zip(t_tables, b_tables):
        if not isinstance(tt, dict) or not isinstance(bt, dict):
            return "table_not_dict"
        headers = tt.get("headers")
        hn = bt.get("header_normalize")
        if not isinstance(headers, list) or not isinstance(hn, list):
            return "headers_missing"
        if len(headers) != len(hn):
            return "header_length_mismatch"
    return None


# ---------------------------------------------------------------------------
# 写入 bindings
# ---------------------------------------------------------------------------


def _binding_cell_slot(
    binding_section: dict, table_index: int, row_label: str
) -> dict[str, Any] | None:
    tables = binding_section.get("tables") or []
    if not (0 <= table_index < len(tables)):
        return None
    tbl = tables[table_index]
    if not isinstance(tbl, dict):
        return None
    rows = tbl.get("rows")
    if not isinstance(rows, dict):
        return None
    row = rows.get(row_label)
    return row if isinstance(row, dict) else None


def apply_movement_bindings(
    binding_section: dict, specs: list[FormulaSpec]
) -> tuple[int, list[str]]:
    """把 movement 恒等式写进 binding（仅替换 manual+todo 候选格）。"""
    written = 0
    problems: list[str] = []
    for spec in specs:
        row = _binding_cell_slot(binding_section, spec.table_index, spec.row_label)
        if row is None:
            problems.append(f"row_slot_missing:{spec.section_number}:{spec.row_label}")
            continue
        cells = row.get("binding")
        if not isinstance(cells, dict):
            problems.append(f"binding_missing:{spec.section_number}:{spec.row_label}")
            continue
        sem = spec.semantic
        if not sem or sem not in cells:
            problems.append(
                f"semantic_missing:{spec.section_number}:{spec.row_label}:{sem}"
            )
            continue
        existing = cells[sem]
        # 决策 4：只覆盖 manual+todo placeholder
        if not (
            isinstance(existing, dict)
            and existing.get("source") == "manual"
            and existing.get("todo")
        ):
            problems.append(
                f"not_manual_todo:{spec.section_number}:{spec.row_label}:{sem}"
            )
            continue
        # 必填字段（`tests/services/test_note_template_bindings.py` 契约）：
        # source / field / mode / account_codes 缺一不可。
        cells[sem] = {
            "source": "formula",
            "formula_kind": "sum",
            "field": "value",
            "account_codes": [],
            "cells": spec.cells_payload(),
            "table_index": spec.table_index,
            "mode": "auto",
            "derived_by": spec.derived_by,
            "derived_note": spec.derived_note,
        }
        written += 1
    return written, problems


def apply_sum_annotations(
    binding_section: dict, specs: list[FormulaSpec]
) -> int:
    """合计行只加**追溯标注**（不写 source/formula_kind → Property 3）。

    同一合计行各列求和范围相同（`_backfill_totals` 逐列同范围），故按行标注一次。
    """
    annotated = 0
    by_row: dict[tuple[int, str], FormulaSpec] = {}
    for spec in specs:
        by_row.setdefault((spec.table_index, spec.row_label), spec)
    for (table_index, row_label), spec in by_row.items():
        row = _binding_cell_slot(binding_section, table_index, row_label)
        if row is None:
            continue
        member_rows = sorted(
            {int(cell[1:].split("C")[0]) for cell, _sign in spec.signed_cells}
        )
        row["derived_sum"] = {
            "derived_by": spec.derived_by,
            "member_row_numbers": member_rows,
            "derived_note": spec.derived_note,
        }
        annotated += 1
    return annotated


# ---------------------------------------------------------------------------
# 预设
# ---------------------------------------------------------------------------


def _preset_target_cell(spec: FormulaSpec, kind: str) -> str:
    return (
        f"note-formula:{kind}:{spec.variant}:{spec.section_number}:"
        f"T{spec.table_index}:{spec.target_cell}"
    )


def build_preset_entries(results: list[DerivationResult]) -> list[Any]:
    """派生结果 → PresetEntry 列表（机器可读表达式，登记进显式 seed）。"""
    from app.services.formula_management.preset_library import PresetEntry

    entries: list[Any] = []
    for res in results:
        for spec in res.movement_specs:
            entries.append(
                PresetEntry(
                    page_key=f"note:{spec.section_number}",
                    target_cell=_preset_target_cell(spec, "movement"),
                    expression=spec.expression(),
                    formula_type="auto_calc",
                    refs=[
                        {"formula_ref": f"ROW('{cell}')"}
                        for cell, _sign in spec.signed_cells
                    ],
                    source="note_formula_derivation",
                    description=(
                        f"{spec.table_name or '表'}·{spec.row_label}："
                        f"{spec.derived_note}"
                    ),
                    variant=spec.variant or None,
                )
            )
        for spec in res.sum_specs:
            entries.append(
                PresetEntry(
                    page_key=f"note:{spec.section_number}",
                    target_cell=_preset_target_cell(spec, "sum"),
                    expression=spec.expression(),
                    formula_type="auto_calc",
                    refs=[
                        {"formula_ref": f"ROW('{cell}')"}
                        for cell, _sign in spec.signed_cells
                    ],
                    source="note_formula_derivation",
                    description=(
                        f"{spec.table_name or '表'}·{spec.row_label}："
                        f"{spec.derived_note}（仅登记可见，计算真源为 _backfill_totals）"
                    ),
                    variant=spec.variant or None,
                )
            )
    return entries


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def render_report(
    results: list[DerivationResult],
    *,
    pairs_count: int,
    unpaired: list[str],
    unaligned: list[tuple[str, str]],
    written_bindings: int,
    annotated_totals: int,
    preset_count: int,
    binding_problems: list[str],
) -> str:
    movement = sum(len(r.movement_specs) for r in results)
    sums = sum(len(r.sum_specs) for r in results)
    candidates = sum(r.candidate_cells for r in results)
    skipped_cand = sum(r.skipped_candidate_count for r in results)
    remaining = sum(r.remaining_manual_todo for r in results)
    reasons = Counter(s.reason for r in results for s in r.skipped)
    per_variant = Counter(r.variant for r in results)
    sections_with_movement = sum(1 for r in results if r.movement_specs)

    lines: list[str] = []
    lines.append("# 附注公式数据覆盖率报告")
    lines.append("")
    lines.append(
        "> 由 `scripts/gen/generate_note_formula_data.py` 自动生成"
        f"（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）。"
    )
    lines.append(
        "> spec: `.kiro/specs/disclosure-note-formula-data-population/`"
    )
    lines.append("")
    lines.append("## 章节配对")
    lines.append("")
    lines.append(f"- 已配对章节（listed 优先）：**{pairs_count}**")
    lines.append(f"  - listed：{per_variant.get('listed', 0)}；soe：{per_variant.get('soe', 0)}")
    lines.append(f"- 未在任何模板找到 section_number：{len(unpaired)} {unpaired[:5]}")
    lines.append(f"- 结构未对齐跳过：{len(unaligned)}")
    for section, reason in unaligned[:10]:
        lines.append(f"  - {section}: {reason}")
    lines.append("")
    lines.append("## 变动表恒等式（期末 = 期初 + 增 − 减）")
    lines.append("")
    lines.append(f"- 产出公式：**{movement}** 条，覆盖 **{sections_with_movement}** 个章节")
    lines.append(f"- 写入 binding：**{written_bindings}** 格（仅覆盖 manual+todo 候选）")
    lines.append("")
    lines.append("## 合计 / 小计")
    lines.append("")
    lines.append(f"- 登记预设：**{sums}** 条（逐列）")
    lines.append(f"- binding 追溯标注：**{annotated_totals}** 行")
    lines.append(
        "- **不写公式 binding**（决策 2）：计算真源仍是 `_backfill_totals`，"
        "避免与生成路径第二遍求值双写"
    )
    lines.append("")
    lines.append("## 候选格三分类（Property 16）")
    lines.append("")
    lines.append(f"- 候选单元格总数（data 行 × 有语义列 × 当前 manual+todo）：**{candidates}**")
    lines.append(f"- 已公式化：**{movement}**")
    lines.append(f"- 被跳过的候选：**{skipped_cand}**")
    lines.append(f"- 仍 manual+todo：**{remaining}**")
    lines.append(
        f"- 校验：{movement} + {skipped_cand} + {remaining} = "
        f"{movement + skipped_cand + remaining}"
        f"（应等于 {candidates}）"
    )
    lines.append("")
    lines.append("## 跳过原因分布")
    lines.append("")
    lines.append("| reason | 次数 |")
    lines.append("| --- | --- |")
    for reason, n in reasons.most_common():
        lines.append(f"| {reason} | {n} |")
    lines.append("")
    lines.append("## 预设登记")
    lines.append("")
    lines.append(f"- 写入 `formula_presets_seed.json` 条目：**{preset_count}**")
    lines.append("")
    lines.append("## 未产出的公式类型（诚实说明）")
    lines.append("")
    lines.append(
        "- `aging`：`refill_sections` / 生成第二遍的 ctx **未注入 `aging_data`**"
        "（Wave 0 §V1）→ 本轮不产出账龄公式，避免写入永不可求值的 binding。"
    )
    lines.append(
        "- `report`（报表→附注写值）：按用户拍板的决策 1，报表↔附注**只做校验不做写值**，"
        "故不产出 report 取数 binding；勾稽关系由 `logic_check` 预设承载。"
    )
    if binding_problems:
        lines.append("")
        lines.append("## binding 写入异常（前 20 条）")
        lines.append("")
        for p in binding_problems[:20]:
            lines.append(f"- {p}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def run(apply: bool) -> int:
    templates = {k: _load(p) for k, p in TEMPLATES.items()}
    bindings = _load(BINDINGS_PATH)

    pairs, unpaired = build_section_pairs(templates, bindings)
    results: list[DerivationResult] = []
    unaligned: list[tuple[str, str]] = []
    written_bindings = 0
    annotated_totals = 0
    binding_problems: list[str] = []

    for section, (variant, tpl_section) in pairs.items():
        binding_section = bindings["bindings"][section]
        reason = _structure_aligned(tpl_section, binding_section)
        if reason:
            unaligned.append((section, reason))
            continue

        res = derive_note_formulas(section, tpl_section, binding_section, variant)
        results.append(res)

        w, probs = apply_movement_bindings(binding_section, res.movement_specs)
        written_bindings += w
        binding_problems.extend(probs)
        annotated_totals += apply_sum_annotations(binding_section, res.sum_specs)

    presets = build_preset_entries(results)

    report = render_report(
        results,
        pairs_count=len(pairs),
        unpaired=unpaired,
        unaligned=unaligned,
        written_bindings=written_bindings,
        annotated_totals=annotated_totals,
        preset_count=len(presets),
        binding_problems=binding_problems,
    )

    print(report)

    if not apply:
        print("\n(dry-run；加 --apply 才写回数据文件)")
        return 0

    # 备份 + 写回 bindings
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"note_template_bindings_{stamp}.json"
    shutil.copy2(BINDINGS_PATH, backup)
    BINDINGS_PATH.write_text(
        _dump_preserving_newline(BINDINGS_PATH, bindings), encoding="utf-8"
    )
    print(f"[ok] backed up {backup.name}")
    print(f"[ok] wrote {BINDINGS_PATH.name}")

    # 预设 upsert（幂等，按 (page_key, target_cell) 去重）
    from app.services.formula_management.preset_library import upsert_seed_presets

    stats = upsert_seed_presets(presets)
    print(f"[ok] presets upserted: {stats}")

    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"[ok] wrote {REPORT_PATH.name}")
    print(
        "\n[next] 必须执行：python scripts/normalize_note_bindings.py --write"
        "（补国企 legacy_aliases）"
    )
    return 0


def main() -> int:
    # Windows GBK 控制台无法打印 U+2212（−）等字符 → 强制 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass
    parser = argparse.ArgumentParser(
        description="生成附注表内公式 binding + 公式管理预设（幂等）"
    )
    parser.add_argument(
        "--apply", action="store_true", help="备份并写回数据文件（默认 dry-run）"
    )
    args = parser.parse_args()
    return run(args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
