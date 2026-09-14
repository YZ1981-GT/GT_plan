#!/usr/bin/env python
"""幂等脚本：G7 长期股权投资附注模板结构对齐。

**本轮只实现上市 `五、18` 这一个作用域**（后续追加 4.2~4.4 的其它作用域）。

**现状**（postgres 实证 + JSON 文件）：
- 上市 `五、18 长期股权投资` 只有 1 张表 `长期股权投资`，`headers` 5 列（源模板 13 列），
  `columns=0`，`guidance=None`，1 个 `row_type: header_label` 假行，
  `①合营企业`/`…`/小计/`②联营企业`/`…`/小计/合计 共 7 个数据行。
- `text_sections` 只有 2 段裸标题。

**目标**：
1. 主表 `长期股权投资` 的 `headers` 由 5 列扩为 13 列（逐字取自源模板 A8:M11 的合并区）
2. 补 `columns`（13 列，含 `group: '本期增减变动'` 覆盖第 3~10 列；其余列不给 group = 混合分组）
3. 补 `guidance`（取源模板 R24 的 15 号文第十九条（十九）括注内容的头 200 字作提示）
4. 删 `row_type: header_label` 假行
5. `…` 占位行保留（它们在源模板是真实可扩动态行 —— 合营企业/联营企业各一个 `…`）
6. 用 `ensure_text_sections` 补缺的 text_sections（现只有 2 段裸标题，补到 4 段：
   现有 2 + 「减值测试说明」+ 「重要合营联营投资披露」）
7. 写 `_aligned_by: 'fix_note_g7_long_term_equity_structure'` 标记

用法：
  python backend/scripts/fix/fix_note_g7_long_term_equity_structure.py --dry-run
  python backend/scripts/fix/fix_note_g7_long_term_equity_structure.py --check
  python backend/scripts/fix/fix_note_g7_long_term_equity_structure.py

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    ensure_text_sections,
    grouped_columns,
    missing_text_sections,
    rule,
    run_section,
    validate_section,
)

# `row_type` 判据单一真源（kit 已把 backend/ 加进 sys.path）。
from app.services.note_expandable_markers import (  # noqa: E402
    row_type_for_label as _row_type_for_label,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"

LISTED_SECTION = "五、18"
ALIGNED_BY = "fix_note_g7_long_term_equity_structure"

T_MAIN = "长期股权投资"

# ─────────────────────────── 列定义（13 列）───────────────────────────
# 逐字取自源模板 A8:M11 的合并区；第 3~10 列属 `本期增减变动` 分组

_GROUP = "本期增减变动"

# 🔴 标签列 key 统一为平台惯例 `'label'`（g7-column-alignment spec Task 5）：
# 平台 211 个标签列定义里 148 个用 `'label'`；`'项目'` 这类**中文字面量当 key**
# 违反「禁硬编码」且全平台仅 G 循环在用。`is_label`/`label` 显示文字不动 ——
# 投影器 `note_sub_table_projector._project_row` 对标签列有**双向兜底**
# （L67-68 任意标签 key → `label` 回填 / L204-205 反向回退），故改 key 零数据风险。
LISTED_MAIN_COLUMNS = grouped_columns(
    ("label", "被投资单位"),
    [
        ("openingBook", "期初余额（账面价值）", AMOUNT, None),
        ("openingImpairment", "减值准备期初余额", AMOUNT, None),
        ("addition", "追加/新增投资", AMOUNT, _GROUP),
        ("reduction", "减少投资", AMOUNT, _GROUP),
        ("equityProfit", "权益法下确认的投资损益", AMOUNT, _GROUP),
        ("oci", "其他综合收益调整", AMOUNT, _GROUP),
        ("otherEquity", "其他权益变动", AMOUNT, _GROUP),
        ("dividend", "宣告发放现金股利或利润", AMOUNT, _GROUP),
        ("impairment", "计提减值准备", AMOUNT, _GROUP),
        ("other", "其他", AMOUNT, _GROUP),
        ("closingBook", "期末余额（账面价值）", AMOUNT, None),
        ("closingImpairment", "减值准备期末余额", AMOUNT, None),
    ],
)

LISTED_MAIN_HEADERS = [
    "被投资单位", "期初余额（账面价值）", "减值准备期初余额",
    "追加/新增投资", "减少投资", "权益法下确认的投资损益",
    "其他综合收益调整", "其他权益变动", "宣告发放现金股利或利润",
    "计提减值准备", "其他", "期末余额（账面价值）", "减值准备期末余额",
]

# ─────────────────────────── 行定义 ───────────────────────────
# 删 `row_type: header_label` 假行，保留 `…` 动态行
# 行集：①合营企业 + … + 小计 + ②联营企业 + … + 小计 + 合计

# 🔴 `…` 是源模板留的**可扩位**（零可见内容），禁硬编码 `row_type: "data"` ——
# 否则与 `fix_note_expandable_rows.py` 互相翻转。判据单一真源 =
# app/services/note_expandable_markers.row_type_for_label。
LISTED_MAIN_ROWS: list[dict[str, Any]] = [
    {"label": "①合营企业", "row_type": _row_type_for_label("①合营企业")},
    {"label": "…", "row_type": _row_type_for_label("…")},
    {"label": "小计", "is_total": True, "row_type": "subtotal"},
    {"label": "②联营企业", "row_type": _row_type_for_label("②联营企业")},
    {"label": "…", "row_type": _row_type_for_label("…")},
    {"label": "小计", "is_total": True, "row_type": "subtotal"},
    {"label": "合计", "is_total": True, "row_type": "total"},
]

# ─────────────────────────── guidance ───────────────────────────
# 取源模板 R24 的 15 号文第十九条（十九）括注内容

_GUIDANCE = (
    "长期股权投资变动表（源模板 A8:M11 两级表头）：列 = 被投资单位（标签列）+ "
    "期初余额（账面价值）+ 减值准备期初余额 + 本期增减变动（追加/新增投资、减少投资、"
    "权益法下确认的投资损益、其他综合收益调整、其他权益变动、宣告发放现金股利或利润、"
    "计提减值准备、其他）+ 期末余额（账面价值）+ 减值准备期末余额。"
    "行 = ①合营企业（含动态明细行 `…`）/ 小计 / ②联营企业（含动态明细行 `…`）/ 小计 / 合计。"
    "勾稽：期末余额（账面价值）= 期初余额（账面价值）+ 本期增减变动各列代数和 − 计提减值准备 中影响账面价值部分。"
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去"
    "处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。"
    "可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数"
    "及其确定依据。（15号文第十九条（十九））】"
    "数据来源：审定表 G7-1 / 明细表 G7-2。"
)

# ─────────────────────────── text_sections 补缺段 ───────────────────────────
# 现只有 2 段：「### 对子公司投资」「### 对联营、合营企业投资」
# 补 2 段（追加到末尾）

_REQUIRED_TEXT_SECTIONS = [
    "减值测试说明",
    "重要合营联营投资披露",
]


# ─────────────────────────── plan 构建 ───────────────────────────

def _listed_plan() -> list[dict[str, Any]]:
    return [rule(T_MAIN, LISTED_MAIN_COLUMNS, LISTED_MAIN_ROWS, _GUIDANCE)]


EXPECTED = {"listed": [T_MAIN]}
_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan),
}
_LABELS = {
    "listed": "note_template_listed.json §五、18 长期股权投资（上市）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        require_text_sections=_REQUIRED_TEXT_SECTIONS,
    )


main = build_cli(
    "附注 G7 长期股权投资章节结构对齐（幂等）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
