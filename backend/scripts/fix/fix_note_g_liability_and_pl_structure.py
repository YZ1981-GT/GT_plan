#!/usr/bin/env python
"""补齐 G10/G11/G13/G14 附注披露表 columns 与 guidance（幂等）。

**目标**：附注模板 G10 交易性金融负债 / G11 投资收益 / G13 公允价值变动收益 /
G14 信用减值损失共 8 个章节 12 张表此前**全部缺 `columns`**（`columns: []`）→
seed 路径走 `note_sub_table_projector._infer_groups_from_headers` 前缀推断，
可能凭空造父表头；金额列无 `format=amount`。

所有 12 张表在源模板中均为**单行表头**（无两级分组）→ 一律显式标 `flat`。

权威源（三者互证）：

- `backend/wp_templates/G/` 下对应源 xlsx 的两张披露 sheet（openpyxl 实测列头）；
- `note_template_{listed,soe}.json` 既有 headers（交付物权威）；
- `g{10,11,13,14}NoteSectionMap.ts` / `g11NoteSectionMap.ts` 等的列定义（推送路径已验证）。

章节与表结构：

- **G10 交易性金融负债**
  - Listed §五、34：3 tables，主表 5 列（项目/期初余额/本期增加/本期减少/期末余额）
  - Soe §八、34：2 tables，主表 3 列（项目/期末公允价值/期初公允价值）

- **G11 投资收益**
  - Listed §五、69：2 tables，主表 3 列（项目/本期发生额/上期发生额）
  - Soe §八、70：1 table，3 列（项目/本期发生额/上期发生额）

- **G13 公允价值变动收益**
  - Listed §三、公允价值变动收益：2 tables，主表 3 列（产生公允价值变动收益的来源/本期发生额/上期发生额）
  - Soe §八、72：1 table，3 列（产生公允价值变动收益的来源/本期发生额/上期发生额）

- **G14 信用减值损失**
  - Listed §三、信用减值损失：1 table，3 列（项目/本期发生额/上期发生额）
  - Soe §八、73：1 table，3 列（项目/本期发生额/上期发生额）

Usage::

    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py --dry-run
    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py
    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py --check
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    flat_columns,
    rule,
    run_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "g-cycle-extraction-mapping-and-disclosure-alignment"

# ═══════════════════════════ Guidance 文本 ═══════════════════════════

GUIDANCE_G10 = (
    "对于指定为以公允价值计量且其变动计入当期损益的金融负债，"
    "需区分企业自身信用风险变动引起的公允价值变动金额计入其他综合收益"
    "和全部利得或损失计入当期损益两种情况（CAS 37 第41-43条）。"
)
GUIDANCE_G11 = (
    "以下不存在的项目可以删除。对于业务处置的收益（含子公司和分公司），"
    "无论直接出售还是先持有待售再出售，均整体计入投资收益。"
)
GUIDANCE_G13 = (
    "以下不存在的项目可以删除。"
    "公允价值变动收益按产生来源分类列示本期发生额与上期发生额。"
)
GUIDANCE_G14 = (
    "损失以「—」号填列，以下不存在的项目可以删除。"
    "信用减值损失按 CAS 22 预期信用损失模型分来源列示。"
)

# ═══════════════════════════ G10 交易性金融负债 ═══════════════════════════

G10_LISTED_SECTION = "五、34"
G10_SOE_SECTION = "八、34"

# Listed: 5 列主表（同结构用于3张表）
_G10_LISTED_COLS = flat_columns([
    ("label", "项目", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("current_increase", "本期增加", AMOUNT),
    ("current_decrease", "本期减少", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
])

# Soe: 3 列主表（同结构用于2张表）
_G10_SOE_COLS = flat_columns([
    ("label", "项目", None),
    ("end_fv", "期末公允价值", AMOUNT),
    ("begin_fv", "期初公允价值", AMOUNT),
])

# ═══════════════════════════ G11 投资收益 ═══════════════════════════

G11_LISTED_SECTION = "五、69"
G11_SOE_SECTION = "八、70"

_G11_COLS = flat_columns([
    ("label", "项目", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])

# ═══════════════════════════ G13 公允价值变动收益 ═══════════════════════════

G13_LISTED_SECTION = "三、公允价值变动收益"
G13_SOE_SECTION = "八、72"

_G13_COLS = flat_columns([
    ("label", "产生公允价值变动收益的来源", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])

# ═══════════════════════════ G14 信用减值损失 ═══════════════════════════

G14_LISTED_SECTION = "三、信用减值损失"
G14_SOE_SECTION = "八、73"

_G14_COLS = flat_columns([
    ("label", "项目", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])


# ═══════════════════════════ 章节计划 ═══════════════════════════

def _g10_listed_plan(tables: list[str]) -> list[dict]:
    """G10 Listed 五、34：3 tables，全部使用相同 5 列结构。"""
    return [rule(name, _G10_LISTED_COLS, None, GUIDANCE_G10) for name in tables]


def _g10_soe_plan(tables: list[str]) -> list[dict]:
    """G10 Soe 八、34：2 tables，全部使用相同 3 列结构。"""
    return [rule(name, _G10_SOE_COLS, None, GUIDANCE_G10) for name in tables]


def _g11_listed_plan(tables: list[str]) -> list[dict]:
    """G11 Listed 五、69：2 tables，全部使用相同 3 列结构。"""
    return [rule(name, _G11_COLS, None, GUIDANCE_G11) for name in tables]


def _g11_soe_plan(tables: list[str]) -> list[dict]:
    """G11 Soe 八、70：1 table。"""
    return [rule(name, _G11_COLS, None, GUIDANCE_G11) for name in tables]


def _g13_listed_plan(tables: list[str]) -> list[dict]:
    """G13 Listed 三、公允价值变动收益：2 tables（主表+套保明细），同结构。"""
    return [rule(name, _G13_COLS, None, GUIDANCE_G13) for name in tables]


def _g13_soe_plan(tables: list[str]) -> list[dict]:
    """G13 Soe 八、72：1 table。"""
    return [rule(name, _G13_COLS, None, GUIDANCE_G13) for name in tables]


def _g14_listed_plan(tables: list[str]) -> list[dict]:
    """G14 Listed 三、信用减值损失：1 table。"""
    return [rule(name, _G14_COLS, None, GUIDANCE_G14) for name in tables]


def _g14_soe_plan(tables: list[str]) -> list[dict]:
    """G14 Soe 八、73：1 table。"""
    return [rule(name, _G14_COLS, None, GUIDANCE_G14) for name in tables]


# ═══════════════════════════ 表名发现（运行时从模板读取） ═══════════════════════════

import json  # noqa: E402


def _get_table_names(path: Path, section_number: str) -> list[str]:
    """从模板 JSON 中读取指定章节的所有表名。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            tables = sec.get("tables") or []
            return [str(t.get("name", "")) for t in tables]
    return []


# ═══════════════════════════ 统一调度 ═══════════════════════════

_TARGETS: dict[str, tuple[Path, str, type]] = {}
_LABELS: dict[str, str] = {}

# 按章节键注册：{cycle}_{variant}
_CHAPTER_DEFS: list[tuple[str, str, Path, str, object]] = [
    ("g10_listed", "G10 交易性金融负债（上市 §五、34）", LISTED_PATH, G10_LISTED_SECTION, _g10_listed_plan),
    ("g10_soe", "G10 交易性金融负债（国企 §八、34）", SOE_PATH, G10_SOE_SECTION, _g10_soe_plan),
    ("g11_listed", "G11 投资收益（上市 §五、69）", LISTED_PATH, G11_LISTED_SECTION, _g11_listed_plan),
    ("g11_soe", "G11 投资收益（国企 §八、70）", SOE_PATH, G11_SOE_SECTION, _g11_soe_plan),
    ("g13_listed", "G13 公允价值变动收益（上市 §三、公允价值变动收益）", LISTED_PATH, G13_LISTED_SECTION, _g13_listed_plan),
    ("g13_soe", "G13 公允价值变动收益（国企 §八、72）", SOE_PATH, G13_SOE_SECTION, _g13_soe_plan),
    ("g14_listed", "G14 信用减值损失（上市 §三、信用减值损失）", LISTED_PATH, G14_LISTED_SECTION, _g14_listed_plan),
    ("g14_soe", "G14 信用减值损失（国企 §八、73）", SOE_PATH, G14_SOE_SECTION, _g14_soe_plan),
]


def _runner(key: str, dry_run: bool, check: bool):
    for chap_key, label, path, section_number, plan_fn in _CHAPTER_DEFS:
        if chap_key == key:
            table_names = _get_table_names(path, section_number)
            if not table_names:
                return [], [f"章节 {section_number} 无表或不存在（{path.name}）"], []
            plan = plan_fn(table_names)
            return run_section(
                path,
                section_number,
                plan,
                table_names,
                aligned_by=ALIGNED_BY,
                dry_run=dry_run,
                check=check,
            )
    return [], [f"未知键：{key}"], []


_LABELS = {chap_key: label for chap_key, label, *_ in _CHAPTER_DEFS}

main = build_cli(
    "补齐 G10/G11/G13/G14 附注披露表 columns 与 guidance（幂等）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
