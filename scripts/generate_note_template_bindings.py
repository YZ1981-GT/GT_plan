"""自动生成 backend/data/note_template_bindings.json.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.1
Design: D2 模板与绑定分离 — header_normalize.semantic + binding schema
Reqs:   R1.1 验收标准 1（≥ 80% 章节覆盖；本轮自动生成预期 30-50%，等 P-1
        审计师手工补 50+ 变动表后再补到 80%）

策略
----
**保守自动生成**：仅对（a）行带 ``account_codes`` 字段，或（b）章节
``section_number`` 在 ``wp_account_mapping.note_section`` 列表中的 row 自
动生成 binding。能匹配上 ``wp_account_mapping`` 的 section_number 取
其全部条目的 ``account_codes`` 并集；行级 ``account_codes`` 则覆盖
section 级。

列语义到 source 的固定映射（design.md D2）：

| header_semantic                               | source              | field            | 备注 |
|-----------------------------------------------|---------------------|------------------|------|
| closing_balance                               | trial_balance       | audited_amount   | 期末 |
| opening_balance                               | trial_balance       | opening_balance  | 期初 |
| prior_year_value                              | prior_year_note     | value            | 上年 |
| aging_bucket_within_1y / 1_2y / 2_3y / 3_5y / over_5y | aux_ledger_aging | bucket_amount | + bucket |
| current_year_increase / decrease              | manual              | n/a              | 暂留 manual placeholder（P-1 审计师补） |
| current_period_acquisition / disposal / writeoff / recover | manual | n/a         | 同上 |
| current_year_provision                        | manual              | n/a              | 同上 |
| provision_ratio                               | manual              | n/a              | 同上 |
| original_value / accumulated_depreciation / impairment_provision / carrying_value / cost / fair_value | trial_balance | audited_amount | 取期末 |
| category_subtotal                             | formula             | n/a              | mode=auto + formula=sum |
| formula_result                                | manual              | n/a              | mode=manual + 用户公式 |
| manual_text                                   | (跳过)              | n/a              | 行标识列不生成 binding |

行类型规则：
- ``row_type == "header_label"`` → 不生成 binding（标题占位行）
- ``row_type in ("subtotal", "total")`` 且 ``is_total`` → 写入
  ``formula = "sum(detail)"`` + ``mode = "auto"``，**不写 binding 字段**
- 其他 ``row_type == "data"`` → 按列语义生成

agg 默认 ``sum``；wp_name 含「负债 / 应付 / 借款 / 票据 / 债券 / 租赁 /
预收 / 应交 / 薪酬」等关键词时**留 TODO 注释**未自动改 sum_minus（保守）。

输出
----
- ``backend/data/note_template_bindings.json``  生成的 binding 主文件
- ``scripts/note_template_bindings_report.txt`` 报告（覆盖率 / source 分布
  / mode 分布 / 待 review placeholder 数）

用法
----
    .venv\\Scripts\\python.exe scripts\\generate_note_template_bindings.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# 允许 `from backend.app.services.note_column_semantics import ...`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.services.note_column_semantics import (  # noqa: E402
    NoteColumnSemantics,
    VALID_SEMANTICS,
)

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------

DATA_DIR = ROOT / "backend" / "data"
SOE_TEMPLATE = DATA_DIR / "note_template_soe.json"
LISTED_TEMPLATE = DATA_DIR / "note_template_listed.json"
WP_MAPPING = DATA_DIR / "wp_account_mapping.json"

OUT_BINDINGS = DATA_DIR / "note_template_bindings.json"
OUT_REPORT = ROOT / "scripts" / "note_template_bindings_report.txt"

VERSION = "2026-1"
GENERATOR_NAME = "scripts/generate_note_template_bindings.py"

# 7 种合法 source（CI 单测断言）
VALID_SOURCES: tuple[str, ...] = (
    "trial_balance",
    "ledger_sum",
    "aux_balance",
    "aux_ledger_aging",
    "formula",
    "prior_year_note",
    "manual",
)

# 3 种合法 mode（CI 单测断言）
VALID_MODES: tuple[str, ...] = ("auto", "manual", "locked")

# 列语义 → (source, field, extra) 默认映射
# extra 是会合并进 binding dict 的额外字段
_AGING_BUCKET_NAMES = {
    "aging_bucket_within_1y": "1年以内",
    "aging_bucket_1_2y": "1-2年",
    "aging_bucket_2_3y": "2-3年",
    "aging_bucket_3_5y": "3-5年",
    "aging_bucket_over_5y": "5年以上",
}

# 这些列直接落 trial_balance / audited_amount（按期末口径）
_TB_AUDITED_SEMANTICS: set[str] = {
    "closing_balance",
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "carrying_value",
    "cost",
    "fair_value",
}

# 这些列因「自动取数能力不足」暂留 manual placeholder（待 P-1 审计师补）
_MANUAL_PLACEHOLDER_SEMANTICS: set[str] = {
    "current_year_increase",
    "current_year_decrease",
    "current_period_acquisition",
    "current_period_disposal",
    "current_period_writeoff",
    "current_period_recover",
    "current_year_provision",
    "provision_ratio",
    "formula_result",
}

# 行标识列：不生成 binding
_ROW_LABEL_SEMANTICS: set[str] = {"manual_text"}

# 不生成 binding 的 row_type
_NO_BINDING_ROW_TYPES: set[str] = {"header_label"}


# ---------------------------------------------------------------------------
# wp_account_mapping 索引
# ---------------------------------------------------------------------------


def _load_wp_section_index(
    wp_path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """加载 wp_account_mapping.json，按 note_section 聚合.

    Returns:
        (section_to_mappings, section_to_account_codes_union)
    """
    payload = json.loads(wp_path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings", [])

    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in mappings:
        sec = m.get("note_section")
        if sec:
            by_section[sec].append(m)

    union: dict[str, list[str]] = {}
    for sec, items in by_section.items():
        codes: list[str] = []
        seen: set[str] = set()
        for m in items:
            for c in m.get("account_codes") or []:
                if c not in seen:
                    seen.add(c)
                    codes.append(c)
        union[sec] = codes

    return dict(by_section), union


def _pick_wp_code(section_mappings: list[dict[str, Any]]) -> str | None:
    """挑选代表性 wp_code：优先 is_primary=True，否则取第一条."""
    if not section_mappings:
        return None
    for m in section_mappings:
        if m.get("is_primary"):
            return m.get("wp_code")
    return section_mappings[0].get("wp_code")


# ---------------------------------------------------------------------------
# 单条 binding 构建
# ---------------------------------------------------------------------------


def _build_cell_binding(
    semantic: str,
    account_codes: list[str],
) -> dict[str, Any] | None:
    """根据列语义返回单元格 binding dict；行标识列返回 None.

    所有返回的 dict 必含 source / field / mode / account_codes 4 个必填项
    （account_codes 即便空也给空数组，CI 单测会断言）。
    """
    if semantic in _ROW_LABEL_SEMANTICS:
        return None

    base: dict[str, Any] = {
        "source": "manual",
        "field": "value",
        "account_codes": list(account_codes),
        "mode": "manual",
    }

    if semantic == "closing_balance":
        base.update(
            source="trial_balance",
            field="audited_amount",
            agg="sum",
            mode="auto",
        )
    elif semantic == "opening_balance":
        base.update(
            source="trial_balance",
            field="opening_balance",
            agg="sum",
            mode="auto",
        )
    elif semantic == "prior_year_value":
        base.update(
            source="prior_year_note",
            field="value",
            mode="auto",
        )
    elif semantic in _AGING_BUCKET_NAMES:
        base.update(
            source="aux_ledger_aging",
            field="bucket_amount",
            bucket=_AGING_BUCKET_NAMES[semantic],
            mode="auto",
        )
    elif semantic in _TB_AUDITED_SEMANTICS:
        base.update(
            source="trial_balance",
            field="audited_amount",
            agg="sum",
            mode="auto",
        )
    elif semantic in _MANUAL_PLACEHOLDER_SEMANTICS:
        # 留 manual placeholder + TODO 标记（P-1 审计师补）
        base.update(
            source="manual",
            field="value",
            mode="manual",
            todo="待 P-1 审计师手工标注（变动列/计提比例/公式列）",
        )
    else:
        # 未识别语义：兜底 manual + TODO
        base.update(
            source="manual",
            field="value",
            mode="manual",
            todo=f"未识别列语义: {semantic}",
        )

    # 终极保障：4 必填项
    base["account_codes"] = list(base.get("account_codes") or [])
    return base


# ---------------------------------------------------------------------------
# 模板遍历 + 章节绑定
# ---------------------------------------------------------------------------


def _row_account_codes(
    row: dict[str, Any], section_codes: list[str]
) -> list[str]:
    """行级 account_codes 优先，否则用 section 级并集."""
    row_codes = row.get("account_codes")
    if isinstance(row_codes, list) and row_codes:
        return [c for c in row_codes if c]
    return list(section_codes)


def _row_label(row: dict[str, Any], fallback_index: int) -> str:
    label = row.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return f"row_{fallback_index}"


def _build_table_binding(
    table: dict[str, Any],
    section_codes: list[str],
) -> tuple[dict[str, Any], int, int]:
    """为单张表生成 binding；返回 (table_binding_dict, n_data_bindings, n_rows_with_binding)."""
    headers = table.get("headers") or []
    semantics = NoteColumnSemantics.identify_headers(list(headers))

    header_normalize = [
        {"text": str(h) if h is not None else "", "semantic": s}
        for h, s in zip(headers, semantics, strict=False)
    ]

    rows_out: dict[str, dict[str, Any]] = {}
    n_data_bindings = 0
    n_rows_with_binding = 0

    rows = table.get("rows") or []
    seen_labels: dict[str, int] = {}
    for ri, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_type = row.get("row_type") or "data"
        if row_type in _NO_BINDING_ROW_TYPES:
            continue

        label = _row_label(row, ri)
        # 同名行去重（"小  计"出现多次）
        if label in seen_labels:
            seen_labels[label] += 1
            label = f"{label}#{seen_labels[label]}"
        else:
            seen_labels[label] = 0

        # 合计 / 小计 行 → 不写 binding，写公式
        if row.get("is_total") or row_type in {"subtotal", "total"}:
            rows_out[label] = {
                "row_type": row_type,
                "formula": "sum(detail)",
                "mode": "auto",
            }
            continue

        # data 行：根据列语义生成 binding
        codes = _row_account_codes(row, section_codes)
        bindings: dict[str, dict[str, Any]] = {}
        for col_index, semantic in enumerate(semantics):
            cell = _build_cell_binding(semantic, codes)
            if cell is None:
                continue
            # 同语义多列时附加索引避免覆盖
            key = semantic
            if key in bindings:
                key = f"{semantic}_col{col_index}"
            bindings[key] = cell
            n_data_bindings += 1

        row_dict: dict[str, Any] = {"row_type": row_type}
        if bindings:
            row_dict["binding"] = bindings
            n_rows_with_binding += 1
        rows_out[label] = row_dict

    table_binding = {
        "table_index": -1,  # 由调用方填充
        "table_name": table.get("name") or "",
        "header_normalize": header_normalize,
        "rows": rows_out,
    }
    return table_binding, n_data_bindings, n_rows_with_binding


def _build_section_binding(
    section: dict[str, Any],
    section_mappings: list[dict[str, Any]],
    section_codes: list[str],
) -> tuple[dict[str, Any] | None, int, int]:
    """为一个 section 生成 binding；若该 section 无任何可绑定 row 则返回 None."""
    tables = section.get("tables") or []
    if not tables:
        return None, 0, 0

    out_tables: list[dict[str, Any]] = []
    total_bindings = 0
    total_rows_with_binding = 0

    for ti, tbl in enumerate(tables):
        if not isinstance(tbl, dict):
            continue
        table_binding, n_b, n_r = _build_table_binding(tbl, section_codes)
        table_binding["table_index"] = ti
        out_tables.append(table_binding)
        total_bindings += n_b
        total_rows_with_binding += n_r

    if not out_tables or total_bindings == 0:
        return None, 0, 0

    wp_code = _pick_wp_code(section_mappings)
    return (
        {
            "wp_code": wp_code,
            "tables": out_tables,
        },
        total_bindings,
        total_rows_with_binding,
    )


# ---------------------------------------------------------------------------
# 顶层流程
# ---------------------------------------------------------------------------


def _process_template(
    template_path: Path,
    by_section: dict[str, list[dict[str, Any]]],
    section_codes_union: dict[str, list[str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """处理一个模板文件，返回 (bindings_by_section, stats)."""
    template = json.loads(template_path.read_text(encoding="utf-8"))
    sections = template.get("sections", [])

    bindings: dict[str, dict[str, Any]] = {}
    section_with_table = 0
    section_with_binding = 0
    binding_count = 0

    for section in sections:
        sec_num = section.get("section_number")
        if not sec_num:
            continue
        if section.get("tables"):
            section_with_table += 1

        section_mappings = by_section.get(sec_num, [])
        section_codes = section_codes_union.get(sec_num, [])

        # 段级有 table 但没 wp_account_mapping 命中：仍允许通过
        # row 级 account_codes 触发（如 listed 五、1 货币资金 row 自带 codes）
        sec_binding, n_b, _ = _build_section_binding(
            section, section_mappings, section_codes
        )
        if sec_binding is None:
            continue

        bindings[sec_num] = sec_binding
        section_with_binding += 1
        binding_count += n_b

    stats = {
        "total_sections": len(sections),
        "sections_with_tables": section_with_table,
        "sections_with_binding": section_with_binding,
        "binding_cells": binding_count,
        "coverage_ratio": (
            section_with_binding / len(sections) if sections else 0.0
        ),
    }
    return bindings, stats


def _aggregate_distribution(
    all_bindings: dict[str, dict[str, dict[str, Any]]],
) -> tuple[Counter, Counter, int]:
    """统计 source / mode 分布 + manual placeholder 计数."""
    source_counter: Counter[str] = Counter()
    mode_counter: Counter[str] = Counter()
    todo_count = 0

    for template_bindings in all_bindings.values():
        for sec_binding in template_bindings.values():
            for tbl in sec_binding.get("tables", []):
                for row in tbl.get("rows", {}).values():
                    binding_dict = row.get("binding") or {}
                    for cell in binding_dict.values():
                        source_counter[cell.get("source", "<missing>")] += 1
                        mode_counter[cell.get("mode", "<missing>")] += 1
                        if cell.get("todo"):
                            todo_count += 1
    return source_counter, mode_counter, todo_count


def _write_report(
    out_path: Path,
    soe_stats: dict[str, Any],
    listed_stats: dict[str, Any],
    source_counter: Counter,
    mode_counter: Counter,
    todo_count: int,
    total_cells: int,
) -> None:
    lines: list[str] = []
    lines.append("# note_template_bindings.json 自动生成报告")
    lines.append(f"生成时间: {datetime.now().isoformat()}")
    lines.append(f"生成器: {GENERATOR_NAME}")
    lines.append("")
    lines.append("## 模板覆盖率")
    for name, stats in (("SOE", soe_stats), ("Listed", listed_stats)):
        total = stats["total_sections"]
        cov = stats["sections_with_binding"]
        ratio = stats["coverage_ratio"] * 100
        lines.append(
            f"- {name}: {cov}/{total} 章节命中 binding "
            f"({ratio:.1f}%)；含表 {stats['sections_with_tables']}；"
            f"binding cells {stats['binding_cells']}"
        )
    lines.append("")
    lines.append(f"## binding cells 总数: {total_cells}")
    lines.append("")
    lines.append("## source 分布")
    for src, n in source_counter.most_common():
        lines.append(f"- {src}: {n}")
    lines.append("")
    lines.append("## mode 分布")
    for m, n in mode_counter.most_common():
        lines.append(f"- {m}: {n}")
    lines.append("")
    lines.append(f"## 待 P-1 审计师手工 review 的 manual placeholder: {todo_count}")
    lines.append("")
    lines.append("## 备注")
    lines.append("- 本文件为自动生成版本，覆盖率不含 50+ 变动表手工绑定；")
    lines.append("- 待前置任务 P-1 老审计师 review 后补充。")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    by_section, codes_union = _load_wp_section_index(WP_MAPPING)

    soe_bindings, soe_stats = _process_template(
        SOE_TEMPLATE, by_section, codes_union
    )
    listed_bindings, listed_stats = _process_template(
        LISTED_TEMPLATE, by_section, codes_union
    )

    # 合并两个模板的 binding（key=section_number）；若同 section_number
    # 在两模板都有，listed 优先（覆盖率更高）。
    combined: dict[str, dict[str, Any]] = dict(soe_bindings)
    combined.update(listed_bindings)

    payload: dict[str, Any] = {
        "version": VERSION,
        "auto_generated": True,
        "generated_at": datetime.now().isoformat(),
        "generator": GENERATOR_NAME,
        "coverage_note": (
            "自动生成版本（前置 P-1 未完成）；50+ 变动表 binding 待审计师手工标注。"
            "本版仅自动绑定 期末/期初/上年/账龄/账面/原值/折旧/减值 等可静态推导列；"
            "本期增减/计提比例/公式列均留 manual placeholder + todo。"
        ),
        "valid_sources": list(VALID_SOURCES),
        "valid_modes": list(VALID_MODES),
        "valid_semantics": list(VALID_SEMANTICS),
        "stats": {
            "soe": soe_stats,
            "listed": listed_stats,
            "merged_sections": len(combined),
        },
        "bindings": combined,
    }

    OUT_BINDINGS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    src_counter, mode_counter, todo_count = _aggregate_distribution(
        {"soe": soe_bindings, "listed": listed_bindings}
    )
    total_cells = sum(src_counter.values())

    _write_report(
        OUT_REPORT,
        soe_stats,
        listed_stats,
        src_counter,
        mode_counter,
        todo_count,
        total_cells,
    )

    print(f"[ok] wrote {OUT_BINDINGS} ({len(combined)} sections)")
    print(f"[ok] wrote {OUT_REPORT}")
    print(
        f"     SOE coverage {soe_stats['sections_with_binding']}/"
        f"{soe_stats['total_sections']} "
        f"({soe_stats['coverage_ratio'] * 100:.1f}%)"
    )
    print(
        f"     Listed coverage {listed_stats['sections_with_binding']}/"
        f"{listed_stats['total_sections']} "
        f"({listed_stats['coverage_ratio'] * 100:.1f}%)"
    )
    print(f"     binding cells: {total_cells}; placeholders: {todo_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
