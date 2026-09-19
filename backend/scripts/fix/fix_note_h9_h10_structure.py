#!/usr/bin/env python
"""附注 H9 租赁负债 + H10 资产处置损益章节结构对齐（幂等）。

源模板权威：`backend/wp_templates/H/H9 租赁负债.xlsx` / `H10 资产处置损益.xlsx`。

**H10 是重灾区（两个 P0，皆为潜伏态 —— 全库四章节 `last_sync_at` 全 NULL，无存量污染）**：

1. 🔴 **上市两张表同名 `项  目`**（皆为表头首格泄漏）→ `sub_table_data` 以表名为键，
   同名互相覆盖**丢整张表**。载荷现用 `项  目__trial` + `_trial_detail` 双写绕过，
   但投影器只渲染模板里存在的表名 → 那两个键是**孤儿**，试运行销售明细永远进不了附注。
   → 本脚本分别正名为 `资产处置收益（损失以“-”填列）` / `试运行销售损益`。
2. **两版主表各缺源模板 3 行**（债务重组 / 使用权资产 / 油气资产）—— 载荷
   `H10_NOTE_TEMPLATE_LABEL` 早已备好这三条映射，只是模板无落点；上市另有
   `可无限量添加行` 纯占位行与 `header_label` 假行须删。
3. **上市试运行表两级表头被压扁**：源模板 R27/R28 是
   `本期发生额{收入,成本}` / `上期发生额{收入,成本}` 共 5 列，模板压成 3 列。
   载荷已带 `current_income`/`current_cost`/`prior_income`/`prior_cost` 四字段，
   只是列定义未声明 → 四列数据无落点。
4. 三表 `columns=0` + 无 `guidance`；国企 `text_sections` 两段残留 `**` markdown 残迹
   且漏掉源模板 R25 第 3 条；上市漏掉 `【提示：` 开头与源模板 R24 第 4 条。

**H9 结构本就与源模板一致**（上市 3 行 —— R8~R10 是空白可扩明细区故不 seed；
国企 5 行含 `……` 可扩行），只补 `columns`/`guidance`。

🔴 **改名走 `rule(aliases=[...])`，绝不进 `drop_tables`** —— `drop_tables` 在 `apply_plan`
之前执行，会把该表连行一起删掉（H2 已踩）。

🔴 **上市三行标签统一为全角 `“-”`**：源模板 `债务重组` / `使用权资产` / `油气资产` 三行用的是
半角 `"-"`（同一 sheet 内混用），此处统一全角以对齐载荷 `H10_NOTE_TEMPLATE_LABEL`
与已有 7 行的字面 —— 否则同一张表内引号宽度不一致，行标签匹配会随机失败。

Usage::

    python backend/scripts/fix/fix_note_h9_h10_structure.py --dry-run
    python backend/scripts/fix/fix_note_h9_h10_structure.py
    python backend/scripts/fix/fix_note_h9_h10_structure.py --check

spec: .kiro/specs/h9-h10-remaining-disclosure-alignment/ (Task 2)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    data_row,
    flat_columns,
    rule,
    run_section,
    total_row,
    two_period_columns,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

# 🔴 listed `三、` 章 section_number 被 md 重建截断为 10 字符 —— 这是**既有真源形态**
# （全库 70+ 条同款），修法是改前端常量对齐它，不是改模板编号（会波及整章 + 并发 spec）。
H10_LISTED_SECTION = "三、资产处置收益（损"
H10_SOE_SECTION = "八、75"
H9_LISTED_SECTION = "五、47"
H9_SOE_SECTION = "八、52"
ALIGNED_BY = "h9-h10-remaining-disclosure-alignment"

# ── 表名 ────────────────────────────────────────────────────────────────
H10_LISTED_MAIN = "资产处置收益（损失以“-”填列）"
H10_LISTED_TRIAL = "试运行销售损益"
H10_SOE_MAIN = "资产处置收益（损失以“-”号填列）"
H9_MAIN = "租赁负债"
LEAKED = "项  目"  # 表头首格泄漏名（两张表共用 → 同名覆盖）

# ── 行集（源 xlsx listed R9~R19 / soe R9~R18，两版仅括注用语不同）─────────
_H10_ITEMS = [
    "持有待售的非流动资产（处置组）处置利得",
    "固定资产处置利得",
    "在建工程处置利得",
    "生产性生物资产处置利得",
    "无形资产处置利得",
    "债务重组中因处置非流动资产产生的利得",
    "非货币性资产交换产生的利得",
    "使用权资产处置利得",
    "油气资产处置利得",
]

H10_LISTED_ROW_LABELS = [f"{x}（损失以“-”填列）" for x in _H10_ITEMS] + ["试运行销售损益"]
H10_SOE_ROW_LABELS = list(_H10_ITEMS) + ["试运行销售损益"]
H10_TRIAL_ROW_LABELS = ["固定资产试运行销售", "研发样品销售"]


def _rows(labels: list[str]) -> list[dict[str, Any]]:
    return [data_row(x) for x in labels] + [total_row("合计")]


# ── 列 ──────────────────────────────────────────────────────────────────
_H10_MAIN_BASE = [
    ("label", "项目", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
]
H10_LISTED_MAIN_COLUMNS = flat_columns(_H10_MAIN_BASE)
H10_SOE_MAIN_COLUMNS = flat_columns(
    _H10_MAIN_BASE + [("non_recurring_amount", "计入当期非经常性损益的金额", AMOUNT)]
)

# 源模板 R27/R28 两级表头：本期发生额{收入,成本} / 上期发生额{收入,成本}
# key 前缀 current/prior 与载荷 buildH10TrialSubTableRows 的字段名逐字一致
H10_TRIAL_COLUMNS = two_period_columns(
    ("label", "项目"),
    ("本期发生额", "上期发生额"),
    [("income", "收入", AMOUNT), ("cost", "成本", AMOUNT)],
    prefixes=("current", "prior"),
)

H9_LISTED_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("end_balance", "期末余额", AMOUNT),
    ("prior_balance", "上年年末余额", AMOUNT),
])
H9_SOE_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("end_balance", "期末余额", AMOUNT),
    ("begin_balance", "期初余额", AMOUNT),
])

# ── guidance（只取源模板红字 / 15 号文 / 以「勾稽：」标注的工具提示）────────
_G_H10_MAIN_COMMON = (
    "反映企业出售划分为持有待售的非流动资产（金融工具、长期股权投资和投资性房地产除外）"
    "或处置组时确认的处置利得或损失，以及处置未划分为持有待售的固定资产、在建工程、"
    "生产性生物资产及无形资产而产生的处置利得或损失；债务重组中因处置非流动资产产生的"
    "利得或损失、非货币性资产交换产生的利得或损失也包括在本项目内。"
    "本项目应根据损益类科目「资产处置损益」的发生额分析填列；如为处置损失，以「-」号填列。"
    "【源模板提示：①不构成业务的资产组处置（含先持有待售再出售）整体计入资产处置收益，"
    "与资产组相关的其他综合收益转入资产处置收益；②构成业务（含子公司、分公司）的处置"
    "整体计入投资收益，相关其他综合收益同时转入投资收益；③单项投资性房地产的处置损益"
    "计入「其他业务收入/成本」，不计入本项目；④使用权资产、油气资产处置损益计入"
    "资产处置收益，不适用的项目可删除对应行。】"
    "勾稽：合计 = 各项目行之和，且应与审定表 H10-1 审定数一致；"
    "试运行销售损益行应等于「试运行销售损益」明细表合计（收入−成本）。"
    "数据来源：明细表 H10-2 / 审定表 H10-1 / 检查表 H10-4。"
)

_G_H10_LISTED_MAIN = _G_H10_MAIN_COMMON
_G_H10_SOE_MAIN = (
    _G_H10_MAIN_COMMON
    + "「计入当期非经常性损益的金额」按国资监管口径单独列示，未计入非经常性损益的部分填 0 或留空。"
)

_G_H10_TRIAL = (
    "试运行销售损益明细（源模板 R27–R31）：两级表头 —— 本期发生额{收入, 成本} / "
    "上期发生额{收入, 成本}。行为 固定资产试运行销售 / 研发样品销售 / 合计。"
    "勾稽：合计行 = 各行逐列之和；本表净额（收入−成本）应等于主表「试运行销售损益」行金额。"
    "源模板要求说明成本的具体核算方法（在本节说明文字中披露）。"
    "数据来源：明细表 H10-2 试运行销售区块。"
)

_G_H9_LISTED = (
    "租赁负债列示表（源模板 R7–R13）：按租赁资产类别列示期末余额与上年年末余额，"
    "R8–R10 为可扩明细行区（按被审计单位实际租赁类别增删行）。"
    "勾稽：小计 = 各类别行之和；合计 = 小计 − 一年内到期的租赁负债；"
    "合计应与审定表 H9-1 审定数一致，一年内到期部分与「一年内到期的非流动负债」附注勾稽。"
    "本期计提的租赁负债利息费用及其在财务费用—利息支出与资本化之间的分配，在本节说明文字中披露。"
    "【源模板提示：①租赁负债利息费用适用借款费用准则；使用权资产于租赁期开始日即达到预定可使用"
    "状态，租赁负债相关利息费用不应资本化计入使用权资产，租赁期开始日后租赁负债可视同一般借款。"
    "②承租人支付的租金中包含的增值税不属于租赁付款额，不纳入租赁负债与使用权资产的计量。"
    "③租赁保证金不属于租赁付款额，应单独作为资产/负债处理。】"
    "数据来源：审定表 H9-1 / 明细表 H9-2 / 未确认融资费用明细表 H9-3。"
)

_G_H9_SOE = (
    "租赁负债列示表（源模板 R7–R12）：租赁付款额 / 减：未确认的融资费用 / "
    "重分类至一年内到期的非流动负债 / `……`（可扩扣减行）/ 租赁负债净额。"
    "勾稽：租赁负债净额 = 租赁付款额 − 未确认的融资费用 − 重分类至一年内到期的非流动负债 "
    "− 其他扣减项；净额应与审定表 H9-1 审定数一致。"
    "【源模板提示：①租赁负债利息费用适用借款费用准则，租赁期开始日后租赁负债可视同一般借款，"
    "不应资本化计入使用权资产。②租金中包含的增值税不纳入租赁负债与使用权资产的计量。"
    "③租赁保证金应单独作为资产/负债处理。】"
    "数据来源：审定表 H9-1 / 明细表 H9-2 / 未确认融资费用明细表 H9-3。"
)

# ── text_sections（整表替换；`#### ` 前缀仅用于表标题，正文段禁带 `#`）──────
H10_LISTED_TEXT_SECTIONS = [
    "【提示：",
    "1.对于不构成业务的资产组的处置收益，无论直接出售还是先持有待售再出售，均整体计入资产处置收益，"
    "与资产组相关的其他综合收益转入资产处置收益。",
    "2.对于业务（包括子公司和分公司）处置的收益，无论直接出售还是先持有待售再出售，均整体计入投资收益，"
    "与业务相关的其他综合收益同时转入投资收益。",
    "3.单项的投资性房地产的处置，无论是直接出售还是先划分为持有待售资产再出售，"
    "处置损益均计入“其他业务收入/成本”，不计入“资产处置收益”。",
    "4.使用权资产、油气资产处置损益计入资产处置收益；不适用项目可删除对应行。】",
    # 裸表名会被当披露正文渲染 → 必须带 `#### ` 作表标题
    f"#### {H10_LISTED_TRIAL}",
    "（说明成本的具体核算方法。）",
]

H10_SOE_TEXT_SECTIONS = [
    "【提示：反映企业出售划分为持有待售的非流动资产（金融工具、长期股权投资和投资性房地产除外）"
    "或处置组时确认的处置利得或损失，以及处置未划分为持有待售的固定资产、在建工程、生产性生物资产"
    "及无形资产而产生的处置利得或损失。债务重组中因处置非流动资产产生的利得或损失和非货币性资产交换"
    "产生的利得或损失也包括在本项目内。该项目应根据在损益类科目新设置的“资产处置损益”科目的发生额"
    "分析填列；如为处置损失，以“-”号填列。】",
    # 原为 `**…**`（md 重建残迹）→ 剥离
    "【提示：1、针对业务（包括子公司和分公司）处置，不论直接出售还是先持有待售再出售，"
    "相关处置损益均计入“投资收益”，相关OCI在处置完成时转入“投资收益”。",
    "2、不构成业务的资产组处置（资产包涵盖42号准则规范及不在42号准则规范的相关资产），"
    "除非该资产组仅包括金融工具和长投（其处置损益计入“投资收益”），无论直接出售还是先持有待售再出售，"
    "相关处置损益打包确认，均计入“资产处置收益”。与处置组相关的OCI也转入“资产处置收益”。",
    # 源模板 R25 第 3 条，模板 JSON 原本整段缺失
    "3、单项的投资性房地产的处置，无论是直接出售还是先划分为持有待售资产再出售，"
    "处置损益均计入“其他业务收入/成本”】",
]


def _h10_listed_plan() -> list[dict[str, Any]]:
    return [
        rule(
            H10_LISTED_MAIN,
            H10_LISTED_MAIN_COLUMNS,
            _rows(H10_LISTED_ROW_LABELS),
            _G_H10_LISTED_MAIN,
            aliases=[LEAKED],
        ),
        rule(
            H10_LISTED_TRIAL,
            H10_TRIAL_COLUMNS,
            _rows(H10_TRIAL_ROW_LABELS),
            _G_H10_TRIAL,
            aliases=[LEAKED],
        ),
    ]


def _h10_soe_plan() -> list[dict[str, Any]]:
    return [
        rule(
            H10_SOE_MAIN,
            H10_SOE_MAIN_COLUMNS,
            _rows(H10_SOE_ROW_LABELS),
            _G_H10_SOE_MAIN,
        )
    ]


def _h9_listed_plan() -> list[dict[str, Any]]:
    # rows=None：结构本就与源模板一致（R8~R10 空白可扩区不 seed 占位行）
    return [rule(H9_MAIN, H9_LISTED_COLUMNS, None, _G_H9_LISTED)]


def _h9_soe_plan() -> list[dict[str, Any]]:
    # rows=None：5 行含 `……` 可扩扣减行，须保留
    return [rule(H9_MAIN, H9_SOE_COLUMNS, None, _G_H9_SOE)]


EXPECTED = {
    "h10_listed": [H10_LISTED_MAIN, H10_LISTED_TRIAL],
    "h10_soe": [H10_SOE_MAIN],
    "h9_listed": [H9_MAIN],
    "h9_soe": [H9_MAIN],
}

_TARGETS: dict[str, tuple[Path, str, Any, list[str] | None]] = {
    "h10_listed": (LISTED_PATH, H10_LISTED_SECTION, _h10_listed_plan, H10_LISTED_TEXT_SECTIONS),
    "h10_soe": (SOE_PATH, H10_SOE_SECTION, _h10_soe_plan, H10_SOE_TEXT_SECTIONS),
    "h9_listed": (LISTED_PATH, H9_LISTED_SECTION, _h9_listed_plan, None),
    "h9_soe": (SOE_PATH, H9_SOE_SECTION, _h9_soe_plan, None),
}

_LABELS = {
    "h10_listed": "note_template_listed.json §三、资产处置收益（损（上市）",
    "h10_soe": "note_template_soe.json §八、75 资产处置收益（国企）",
    "h9_listed": "note_template_listed.json §五、47 租赁负债（上市）",
    "h9_soe": "note_template_soe.json §八、52 租赁负债（国企）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn, text_sections = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        # 🔴 不传 drops —— `项  目` 只能靠 rule(aliases=[...]) 改名。
        # drop_tables 在 apply_plan **之前**执行，进 drops 会把该表连行一起删掉（H2 已踩）。
        text_sections=text_sections,
    )


main = build_cli("附注 H9 租赁负债 + H10 资产处置损益章节结构对齐（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
