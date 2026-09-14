#!/usr/bin/env python3
"""附注公式数据契约守卫（Wave 5 / Task 6.1）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Props:  Property 3（合计不写公式 binding）/ Property 4（合计口径 ≡ `_backfill_totals`）
        Property 12（不新增披露内容 + 不改 valid_sources）/ Property 13（linkage 不批量填）
        Property 14（预设↔binding 章节集合一致）/ Property 15（cross_check 同源）

以**数据文件遍历**为源，不硬编码逐条清单。失败信息指名章节 + 字段。

用法
----
    python scripts/check/check_note_formula_contract.py            # 报告
    python scripts/check/check_note_formula_contract.py --strict   # 有违规即 exit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DATA = _BACKEND / "data"
BINDINGS_PATH = DATA / "note_template_bindings.json"
SEED_PATH = DATA / "formula_presets" / "formula_presets_seed.json"
LINKAGE_PATH = DATA / "disclosure" / "report_note_linkage.json"
TEMPLATES = {
    "soe": DATA / "note_template_soe.json",
    "listed": DATA / "note_template_listed.json",
}

#: 生成器/resolvers 声明的合法 source（本 spec 不得改动 —— 决策 6）
EXPECTED_BINDING_VALID_SOURCES = {
    "trial_balance",
    "ledger_sum",
    "aux_balance",
    "aux_ledger_aging",
    "wp_data",
    "formula",
    "prior_year_note",
    "manual",
}

TOTAL_ROW_TYPES = {"total", "subtotal"}
DERIVED_SOURCE_MOVEMENT = "note_formula_derivation"
DERIVED_SOURCE_CROSS_CHECK = "note_report_cross_check"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _template_index() -> dict[str, tuple[str, dict]]:
    """section_number → (variant, section)（listed 优先，镜像 bindings 合并口径）."""
    out: dict[str, tuple[str, dict]] = {}
    for variant in ("soe", "listed"):  # listed 后写 → 覆盖 soe
        tpl = _load(TEMPLATES[variant])
        for sec in tpl.get("sections") or []:
            num = sec.get("section_number") if isinstance(sec, dict) else None
            if isinstance(num, str) and num:
                out[num] = (variant, sec)
    return out


def _is_total(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    return bool(row.get("is_total")) or row.get("row_type") in TOTAL_ROW_TYPES


def _backfill_member_rows(template_rows: list[dict]) -> dict[int, list[int]]:
    """复刻 `_backfill_totals` 求和范围：合计行 1-based → 成员行 1-based 列表."""
    out: dict[int, list[int]] = {}
    for i, row in enumerate(template_rows):
        if not _is_total(row) or i == 0:
            continue
        start = 0
        for j in range(i - 1, -1, -1):
            if _is_total(template_rows[j]):
                start = j + 1
                break
        members = [j + 1 for j in range(start, i) if not _is_total(template_rows[j])]
        if members:
            out[i + 1] = members
    return out


def _section_from_target_cell(target_cell: str, kind: str) -> str | None:
    """``note-formula:{kind}:{variant}:{section}:T{ti}:R.C.`` → section."""
    prefix = f"note-formula:{kind}:"
    if not target_cell.startswith(prefix):
        return None
    rest = target_cell[len(prefix) :]
    parts = rest.split(":")
    if len(parts) < 4:
        return None
    return parts[1]


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def check_all() -> list[str]:
    problems: list[str] = []
    bindings_doc = _load(BINDINGS_PATH)
    bindings = bindings_doc.get("bindings") or {}
    seed = _load(SEED_PATH)
    presets = list(seed.get("presets") or [])
    templates = _template_index()

    # --- Property 12a：valid_sources 未被本 spec 改动 -------------------------
    declared = set(bindings_doc.get("valid_sources") or [])
    if declared != EXPECTED_BINDING_VALID_SOURCES:
        problems.append(
            "[P12] note_template_bindings.valid_sources 被改动："
            f"多出 {sorted(declared - EXPECTED_BINDING_VALID_SOURCES)}，"
            f"缺少 {sorted(EXPECTED_BINDING_VALID_SOURCES - declared)}"
        )

    binding_movement_sections: set[str] = set()
    binding_sum_sections: set[str] = set()

    for section, sec in bindings.items():
        tpl_pair = templates.get(section)
        tables = sec.get("tables") or []
        for ti, tbl in enumerate(tables):
            if not isinstance(tbl, dict):
                continue
            rows = tbl.get("rows") or {}
            if not isinstance(rows, dict):
                continue
            for label, row in rows.items():
                if not isinstance(row, dict):
                    continue
                is_total = row.get("row_type") in TOTAL_ROW_TYPES

                # --- Property 3：合计行不得有公式 binding -------------------
                if is_total:
                    if isinstance(row.get("binding"), dict):
                        for sem, cell in row["binding"].items():
                            if not isinstance(cell, dict):
                                continue
                            if cell.get("source") == "formula" or cell.get(
                                "formula_kind"
                            ):
                                problems.append(
                                    f"[P3] {section} T{ti} 合计行「{label}」"
                                    f"语义 {sem} 写了公式 binding"
                                )
                    ann = row.get("derived_sum")
                    if isinstance(ann, dict):
                        binding_sum_sections.add(section)
                        if ann.get("source") or ann.get("formula_kind"):
                            problems.append(
                                f"[P3] {section} T{ti} 合计行「{label}」的"
                                " derived_sum 标注不得带 source/formula_kind"
                            )
                        # --- Property 4：合计口径 ≡ _backfill_totals ---------
                        if tpl_pair is not None:
                            _variant, tpl_sec = tpl_pair
                            t_tables = tpl_sec.get("tables") or []
                            if ti < len(t_tables):
                                t_rows = [
                                    r
                                    for r in (t_tables[ti].get("rows") or [])
                                    if isinstance(r, dict)
                                ]
                                expected_map = _backfill_member_rows(t_rows)
                                # 找该 label 在模板中的行号（1-based，首个匹配）
                                row_no = next(
                                    (
                                        idx + 1
                                        for idx, r in enumerate(t_rows)
                                        if (r.get("label") or "") == label
                                    ),
                                    None,
                                )
                                if row_no is not None:
                                    expected = expected_map.get(row_no)
                                    got = ann.get("member_row_numbers")
                                    if expected is not None and got != expected:
                                        problems.append(
                                            f"[P4] {section} T{ti}「{label}」"
                                            f"求和范围不符 _backfill_totals："
                                            f"got={got} expected={expected}"
                                        )
                    continue

                # --- data 行：公式 binding 合规性 ---------------------------
                cells = row.get("binding")
                if not isinstance(cells, dict):
                    continue
                for sem, cell in cells.items():
                    if not isinstance(cell, dict):
                        continue
                    if cell.get("source") != "formula":
                        continue
                    binding_movement_sections.add(section)
                    if cell.get("formula_kind") != "sum":
                        problems.append(
                            f"[P14] {section} T{ti}「{label}」{sem}："
                            f"formula_kind={cell.get('formula_kind')!r}（应为 'sum'）"
                        )
                    if not isinstance(cell.get("cells"), list) or not cell["cells"]:
                        problems.append(
                            f"[P14] {section} T{ti}「{label}」{sem}：cells 为空"
                        )
                    for field in ("field", "account_codes", "mode"):
                        if field not in cell:
                            problems.append(
                                f"[P14] {section} T{ti}「{label}」{sem}："
                                f"缺必填字段 {field}"
                            )
                    # --- Property 12b：行标签必须来自模板（不新增披露内容）---
                    if tpl_pair is not None:
                        _variant, tpl_sec = tpl_pair
                        t_tables = tpl_sec.get("tables") or []
                        if ti < len(t_tables):
                            labels = {
                                (r.get("label") or "")
                                for r in (t_tables[ti].get("rows") or [])
                                if isinstance(r, dict)
                            }
                            if label not in labels:
                                problems.append(
                                    f"[P12] {section} T{ti}「{label}」"
                                    "行标签不存在于模板（疑似新增披露内容）"
                                )

    # --- Property 14：预设 ↔ binding 章节集合一致 ---------------------------
    preset_movement_sections: set[str] = set()
    preset_sum_sections: set[str] = set()
    cross_check_by_origin: dict[str, dict[str, Any]] = {}
    derived_cross: list[dict[str, Any]] = []
    for p in presets:
        page_key = p.get("page_key") or ""
        target = p.get("target_cell") or ""
        source = p.get("source") or ""
        if page_key == "report:cross_check":
            cross_check_by_origin[target] = p
        if source == DERIVED_SOURCE_MOVEMENT:
            sec = _section_from_target_cell(target, "movement")
            if sec:
                preset_movement_sections.add(sec)
            else:
                sec = _section_from_target_cell(target, "sum")
                if sec:
                    preset_sum_sections.add(sec)
                else:
                    problems.append(f"[P14] 预设 target_cell 无法解析章节：{target}")
        elif source == DERIVED_SOURCE_CROSS_CHECK:
            derived_cross.append(p)

    if preset_movement_sections != binding_movement_sections:
        problems.append(
            "[P14] movement 章节集合不一致："
            f"仅预设 {sorted(preset_movement_sections - binding_movement_sections)[:5]}，"
            f"仅 binding {sorted(binding_movement_sections - preset_movement_sections)[:5]}"
        )
    if preset_sum_sections != binding_sum_sections:
        problems.append(
            "[P14] 合计登记章节集合不一致："
            f"仅预设 {sorted(preset_sum_sections - binding_sum_sections)[:5]}，"
            f"仅 binding {sorted(binding_sum_sections - preset_sum_sections)[:5]}"
        )

    # --- Property 15：cross_check 同源 --------------------------------------
    for p in derived_cross:
        target = p.get("target_cell") or ""
        # note-crosscheck:{section}:{origin_target_cell}
        parts = target.split(":", 2)
        if len(parts) != 3 or parts[0] != "note-crosscheck":
            problems.append(f"[P15] 附注侧勾稽 target_cell 非法：{target}")
            continue
        origin = parts[2]
        src = cross_check_by_origin.get(origin)
        if src is None:
            problems.append(f"[P15] 找不到同源 report:cross_check 条目：{origin}")
            continue
        if (p.get("expression") or "") != (src.get("expression") or ""):
            problems.append(f"[P15] 表达式与报表侧不一致：{target}")
        if (p.get("formula_type") or "") != (src.get("formula_type") or ""):
            problems.append(f"[P15] formula_type 与报表侧不一致：{target}")

    # --- Property 13：linkage 未被批量填 ------------------------------------
    linkage = _load(LINKAGE_PATH)
    business_keys = [k for k in linkage if isinstance(k, str) and not k.startswith("_")]
    if business_keys:
        problems.append(
            f"[P13] report_note_linkage.json 出现业务条目（应为 0）：{business_keys[:5]}"
        )

    print("# 附注公式数据契约守卫")
    print()
    print(f"- binding movement 章节：{len(binding_movement_sections)}")
    print(f"- binding 合计标注章节：{len(binding_sum_sections)}")
    print(f"- 预设 movement 章节：{len(preset_movement_sections)}")
    print(f"- 预设 合计 章节：{len(preset_sum_sections)}")
    print(f"- 附注侧勾稽预设：{len(derived_cross)}（源 report:cross_check {len(cross_check_by_origin)}）")
    print(f"- linkage 业务条目：{len(business_keys)}（应为 0）")
    print()
    if problems:
        print(f"## 违规 {len(problems)} 项")
        print()
        for p in problems[:50]:
            print(f"- {p}")
        if len(problems) > 50:
            print(f"- …… 其余 {len(problems) - 50} 项省略")
    else:
        print("## [OK] 全部契约通过")
    return problems


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass
    parser = argparse.ArgumentParser(description="附注公式数据契约守卫")
    parser.add_argument("--strict", action="store_true", help="有违规即 exit 1")
    args = parser.parse_args()
    problems = check_all()
    return 1 if (problems and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
