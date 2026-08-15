#!/usr/bin/env python
"""修正 I 类公式预设的科目码与 sheet 引用（幂等）。

Wave 2 修订：I 类 18 个块中存在系统性贴错标签问题，
由上一步诊断确认（tmp_i_out2.txt）。

主要错误：
- I2 审定表：wp_name='商誉审定表' + account_codes=['1711'] → 开发支出审定表 + ['1704']
- I3 审定表：wp_name='长期待摊费用审定表' + ['1801'] → 商誉审定表 + ['1711']
- I4 审定表：wp_name='开发支出审定表' + ['1703'] → 长期待摊费用审定表 + ['1801']
- I5 审定表：account_codes=['1811']（递延所得税资产属 N1）→ []
- I6 审定表：account_codes=['6602'] → ['6604']
- I1 审定表：account_codes 缺 '1703'
- I3 明细块：引用 1712（account_chart 无此码）
- I2 明细块：account_codes=['1801','6602'] → ['1704','5301']
- I4 明细块：account_codes=['1801','1811'] → ['1801']（删 1811）
- I6 月度明细块：account_codes=['6602'] → ['6604']
- I1 分析程序块：引用不存在的 sheet 分析程序I1-3 → 整块删除
- I2 资本化判断块：account_codes=['1801'] → ['1704']
- I1 审定表：PREV sheet 引用 '审定表I1-1' → '审定表I1'

Usage::

    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --apply
    python backend/scripts/fix/fix_i_cycle_prefill_presets.py --check

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

#: I1 审定表 sheet 名（源模板实证：**无 `-1`**，六循环唯一例外）
#: 依据 = openpyxl 直读 `backend/wp_templates/I/I1 无形资产.xlsx` 的 tab 名集合。
I1_SHEET_WRONG = "审定表I1-1"
I1_SHEET_RIGHT = "审定表I1"

#: 12 张 I 类披露 sheet 的「显式无预设」登记（R4.1 的第二条路径）。
#:
#: 🔴 **实证裁决（2026-08-09，openpyxl 逐格直读 6 份源 workbook）**：
#: 这 12 张披露表共 **663 格跨 sheet 引用，全部指向本 workbook 内的 `明细表IX-2`**，
#: 「从试算表取数」的格 **= 0**（另有 87 格引用 `底稿目录` 取表头身份信息、
#: 417 格是 `SUM`/算术派生）。逐张实证见 `_wip_i_t8p3.txt`。
#:
#: ⇒ 给这些格配 ``TB()`` 预设会造成**双真源**：预设从 `trial_balance` 取数、
#: 底稿披露 Tab 又从 `明细表IX-2` 推送同一格，两条链算出的数必然在
#: 「明细表尚未编制」与「试算表已有余额」之间打架，而审计师看不出哪个在生效。
#: 平台既有范式是**披露表由底稿推送**（`iXNoteSectionMap.ts` + `useDisclosureAutoSync`），
#: 预设层不介入。
#:
#: ⚠️ 本登记表是「已裁决不做」而非「待办」—— 新增条目必须写明源模板取数来源，
#: 禁把「暂时没想清楚」塞进来当逃逸阀。
DISCLOSURE_NO_PRESET_REGISTRY: dict[tuple[str, str], str] = {
    ("I1", "附注披露信息（上市公司）"): (
        "110 格全部引用 `明细表I1-2`（账面原值/累计摊销/减值准备三层的期初、"
        "增减明细、期末），另 158 格为 SUM/算术派生。三层期末均为 "
        "`=期初+本期增加-本期减少` 的表内派生，非试算表取数。"
    ),
    ("I1", "附注披露信息（国有企业）"): (
        "108 格全部引用 `明细表I1-2`（四层 × 12 类别 × 期初/增/减/期末）。"
        "四层合计行为 `SUM(本层各类别)`，账面价值层为 `原价-累计摊销-减值` 派生。"
    ),
    ("I2", "附注披露（上市公司）"): (
        "54 格全部引用 `明细表I2-2`（逐研发项目的期初/内部开发支出/其他增加/"
        "确认为无形资产/计入当期损益/期末）。「研发支出按费用性质」表（人工费/材料费/"
        "水电燃气费/折旧费/无形资产摊销/外购在研项目）在源模板中**无公式**，"
        "是审计师按研发费用辅助账手工填列，非科目码可推导。"
    ),
    ("I2", "附注披露（国有企业）"): "54 格全部引用 `明细表I2-2`，结构同上市版（少「资本化依据」续表）。",
    ("I3", "附注披露（上市公司）"): (
        "72 格全部引用 `明细表I3-2`（逐被投资单位的商誉原值与减值准备两表）。"
        "商誉按资产组披露，而 `tb_balance` 的 `1711` 子科目不保证与资产组一一对应 ⇒ "
        "只能由底稿逐项录入后推送。"
    ),
    ("I3", "附注披露（国有企业）"): (
        "63 格全部引用 `明细表I3-2`，结构同上市版（少「减值测试过程与参数」文字段）。"
        "商誉按资产组披露，源模板无任何试算表取数格。"
    ),
    ("I4", "附注披露（上市公司）"): (
        "30 格全部引用 `明细表I4-2`（逐项目的期初/本期增加/本期摊销/其他减少/期末）。"
        "长期待摊费用按摊销项目披露，非科目余额直取。"
    ),
    ("I4", "附注披露（国有企业）"): (
        "30 格全部引用 `明细表I4-2`，结构同上市版。长期待摊费用按摊销项目披露，"
        "源模板无任何从试算表取数的格。"
    ),
    ("I5", "附注披露（上市公司）"): (
        "55 格全部引用 `明细表I5-2`。另：`BS-037 = TB('1911')` 而 `1911` 在 "
        "`account_chart` 两张表全库都不存在（R2.1）⇒ 即便想配 TB() 预设也无码可用。"
    ),
    ("I5", "附注披露（国有企业）"): "33 格全部引用 `明细表I5-2`；无标准科目映射，同上。",
    ("I6", "附注披露（上市公司）"): (
        "27 格全部引用 `明细表I6-2`（研发费用按费用性质分月度/项目明细）。"
        "研发费用是损益类，披露按费用性质拆分，而 `6604` 的子科目不保证按性质设置 ⇒ "
        "由底稿 I6-2 逐项录入后推送。"
    ),
    ("I6", "附注披露（国有企业）"): (
        "27 格全部引用 `明细表I6-2`，结构同上市版。研发费用按费用性质拆分披露，"
        "源模板无任何从试算表取数的格。"
    ),
}

#: 研发费用标准科目码（`report_config` 实证 `IS-006 研发费用 = TB('6604','本期发生额')`）。
#: `6602` 是**管理费用**（归 K9，全库借方 6.24 亿），不得用于 I 类任何研发费用格。
RD_EXPENSE_WRONG = "6602"
RD_EXPENSE_RIGHT = "6604"


#: 12 张 I 类披露 sheet 的 `(wp_code, sheet 名)` —— **源模板事实**（openpyxl 直读
#: `backend/wp_templates/I/*.xlsx` 的 tab 名，2026-08-09 实证）。
#:
#: 🔴 两种命名并存且**都是源模板事实，不得统一**：
#:    I1 = `附注披露信息（上市公司）`/`（国有企业）`（带「信息」二字）
#:    I2~I6 = `附注披露（上市公司）`/`（国有企业）`（无「信息」二字）
#: 六份全部**全角括号** + 「**国有企业**」（无一处「国企」）。
#:
#: ⚠️ 本常量与 :data:`DISCLOSURE_NO_PRESET_REGISTRY` **必须独立声明** ——
#: 若「覆盖完备」判据从登记表自身派生，该判据就成了自证（恒真）。
DISCLOSURE_SHEETS: tuple[tuple[str, str], ...] = (
    ("I1", "附注披露信息（上市公司）"),
    ("I1", "附注披露信息（国有企业）"),
    ("I2", "附注披露（上市公司）"),
    ("I2", "附注披露（国有企业）"),
    ("I3", "附注披露（上市公司）"),
    ("I3", "附注披露（国有企业）"),
    ("I4", "附注披露（上市公司）"),
    ("I4", "附注披露（国有企业）"),
    ("I5", "附注披露（上市公司）"),
    ("I5", "附注披露（国有企业）"),
    ("I6", "附注披露（上市公司）"),
    ("I6", "附注披露（国有企业）"),
)

#: 披露 sheet 总数锚点（源模板事实：6 循环 × 2 变体）。
#:
#: 🔴 独立写死的数字，让「同时从 :data:`DISCLOSURE_SHEETS` 与
#: :data:`DISCLOSURE_NO_PRESET_REGISTRY` 两处都删掉某张 sheet」打红 ——
#: 只靠「两集合相等」互校时，同步删两边不会红（集合仍相等，只是都少了一项，
#: 循环自然扫不到它 ⇒ R4.1 判据静默失去覆盖）。
_DISCLOSURE_SHEET_COUNT = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["mappings"]


def _find_block(doc: dict[str, Any], wp_code: str, sheet: str) -> dict[str, Any] | None:
    for b in _blocks(doc):
        if b.get("wp_code") == wp_code and b.get("sheet") == sheet:
            return b
    return None


def _find_block_any(
    doc: dict[str, Any], wp_code: str, *sheets: str
) -> dict[str, Any] | None:
    """按多个候选 sheet 名找块（**改名场景必需**）。

    🔴 为什么不能只用 :func:`_find_block`：I1 块要把 ``sheet`` 从错名
    ``审定表I1-1`` 改成源模板真实 tab 名 ``审定表I1``。改完之后键就变了，
    若查找键写死错名，二次 ``--apply`` 会找不到块 → 幂等断裂；若写死新名，
    首次 ``--apply`` 又找不到块 → 改名永远不执行。故按「新名优先、错名兜底」查。
    """
    for sheet in sheets:
        b = _find_block(doc, wp_code, sheet)
        if b is not None:
            return b
    return None


def _replace_code_in_formula(formula: str, old: str, new: str) -> str:
    """Replace account code in formula expressions like TB('old',...) → TB('new',...)."""
    return formula.replace(f"'{old}'", f"'{new}'")


def _remove_cells_with_code(block: dict[str, Any], code: str) -> int:
    """Remove cells whose formula references the given code. Returns count removed."""
    cells = block.get("cells", [])
    before = len(cells)
    block["cells"] = [c for c in cells if f"'{code}'" not in c.get("formula", "")]
    return before - len(block["cells"])


# ---------------------------------------------------------------------------
# apply_fixes: the idempotent correction logic
# ---------------------------------------------------------------------------

def apply_fixes(doc: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply all I-cycle corrections. Returns (modified_doc, list_of_changes)."""
    changes: list[str] = []

    # --- 1. I1 审定表：sheet 改名 + account_codes 补 '1703' + PREV 实参同步 ---
    # 🔴 源模板实证：I1 审定表真实 tab 名是 `审定表I1`（**无 `-1`**），是六循环唯一例外
    #    （I2~I6 均为 `审定表IX-1`）。改造前本块 `sheet` 字段写 `审定表I1-1`，
    #    在源 workbook 里根本不存在 → 该块整体贴错标签（R3.1）。
    # 🔴 改名必须同时改**块的 `sheet` 字段**与**公式实参里的旧 sheet 名**（R3.2）；
    #    只改后者是改造前的缺陷 —— 那样块自己仍指向不存在的 tab。
    b = _find_block(doc, "I1", I1_SHEET_WRONG) or _find_block(doc, "I1", I1_SHEET_RIGHT)
    if b:
        if b.get("sheet") != I1_SHEET_RIGHT:
            b["sheet"] = I1_SHEET_RIGHT
            changes.append(
                f"I1 审定表: sheet '{I1_SHEET_WRONG}' → '{I1_SHEET_RIGHT}'（源模板真实 tab 名）"
            )
        codes = b.get("account_codes", [])
        if "1703" not in codes:
            codes.append("1703")
            b["account_codes"] = codes
            changes.append("I1 审定表: account_codes 补 '1703'")
        # 公式实参里的旧 sheet 名（PREV / WP 等任意函数）一并同步
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if f"'{I1_SHEET_WRONG}'" in f:
                c["formula"] = f.replace(f"'{I1_SHEET_WRONG}'", f"'{I1_SHEET_RIGHT}'")
                changes.append(
                    f"I1 审定表: 公式实参 '{I1_SHEET_WRONG}' → '{I1_SHEET_RIGHT}'"
                    f" in {c.get('cell_ref')}"
                )

    # --- 2. I2 审定表：wp_name→开发支出审定表; account_codes→['1704']; TB('1711')→TB('1704') ---
    b = _find_block(doc, "I2", "审定表I2-1")
    if b:
        if b.get("wp_name") != "开发支出审定表":
            b["wp_name"] = "开发支出审定表"
            changes.append("I2 审定表: wp_name → '开发支出审定表'")
        if b.get("account_codes") != ["1704"]:
            b["account_codes"] = ["1704"]
            changes.append("I2 审定表: account_codes → ['1704']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1711'" in f:
                c["formula"] = _replace_code_in_formula(f, "1711", "1704")
                changes.append(f"I2 审定表: TB('1711') → TB('1704') in {c['cell_ref']}")


    # --- 3. I3 审定表：wp_name→商誉审定表; account_codes→['1711']; TB('1801')→TB('1711') ---
    b = _find_block(doc, "I3", "审定表I3-1")
    if b:
        if b.get("wp_name") != "商誉审定表":
            b["wp_name"] = "商誉审定表"
            changes.append("I3 审定表: wp_name → '商誉审定表'")
        if b.get("account_codes") != ["1711"]:
            b["account_codes"] = ["1711"]
            changes.append("I3 审定表: account_codes → ['1711']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1801'" in f:
                c["formula"] = _replace_code_in_formula(f, "1801", "1711")
                changes.append(f"I3 审定表: TB('1801') → TB('1711') in {c['cell_ref']}")

    # --- 4. I4 审定表：wp_name→长期待摊费用审定表; account_codes→['1801']; TB('1703')→TB('1801') ---
    b = _find_block(doc, "I4", "审定表I4-1")
    if b:
        if b.get("wp_name") != "长期待摊费用审定表":
            b["wp_name"] = "长期待摊费用审定表"
            changes.append("I4 审定表: wp_name → '长期待摊费用审定表'")
        if b.get("account_codes") != ["1801"]:
            b["account_codes"] = ["1801"]
            changes.append("I4 审定表: account_codes → ['1801']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1703'" in f:
                c["formula"] = _replace_code_in_formula(f, "1703", "1801")
                changes.append(f"I4 审定表: TB('1703') → TB('1801') in {c['cell_ref']}")

    # --- 5. I5 审定表：wp_name→其他非流动资产审定表; account_codes→[]; 删 TB('1811') cells ---
    b = _find_block(doc, "I5", "审定表I5-1")
    if b:
        if b.get("wp_name") != "其他非流动资产审定表":
            b["wp_name"] = "其他非流动资产审定表"
            changes.append("I5 审定表: wp_name → '其他非流动资产审定表'")
        if b.get("account_codes") != []:
            b["account_codes"] = []
            changes.append("I5 审定表: account_codes → [] (1811 属 N1 循环)")
        removed = _remove_cells_with_code(b, "1811")
        if removed:
            changes.append(f"I5 审定表: 删除 {removed} 条引用 1811 的 cells")


    # --- 6. I6 审定表：wp_name→研发费用审定表; account_codes→['6604']; TB('6602')→TB('6604') ---
    b = _find_block(doc, "I6", "审定表I6-1")
    if b:
        if b.get("wp_name") != "研发费用审定表":
            b["wp_name"] = "研发费用审定表"
            changes.append("I6 审定表: wp_name → '研发费用审定表'")
        if b.get("account_codes") != ["6604"]:
            b["account_codes"] = ["6604"]
            changes.append("I6 审定表: account_codes → ['6604']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'6602'" in f:
                c["formula"] = _replace_code_in_formula(f, "6602", "6604")
                changes.append(f"I6 审定表: TB('6602') → TB('6604') in {c['cell_ref']}")

    # --- 7. I2 明细块：account_codes→['1704','6604']; TB('1801')→TB('1704'); TB('6602')→TB('6604') ---
    #
    # 🔴 `account_codes` 只允许**这一处**写者（2026-08-09 修）。
    #    改造前这里写 `['1704','5301']`、下方 `6602→6604` 那段又改成 `['1704','6604']`
    #    = 同一字段两个写者（memory 已记的 `row_type` 多写者事故同型）。
    #    虽然执行顺序让最终值恰好正确，但二次 `--apply` 会输出两条相反的变更记录，
    #    且任何人调整两段顺序就会让 `--check` 与 `--apply` 结论打架。
    #    `5301` 是旧制码（研发支出旧科目），本块公式实际引用 6604 ⇒ 按公式自洽取 6604。
    b = _find_block(doc, "I2", "明细表I2-2")
    if b:
        if b.get("account_codes") != ["1704", RD_EXPENSE_RIGHT]:
            b["account_codes"] = ["1704", RD_EXPENSE_RIGHT]
            changes.append(
                f"I2 明细表: account_codes → ['1704','{RD_EXPENSE_RIGHT}']（与公式自洽）"
            )
        # wp_name fix: should be 开发支出明细表
        if b.get("wp_name") != "开发支出明细表":
            b["wp_name"] = "开发支出明细表"
            changes.append("I2 明细表: wp_name → '开发支出明细表'")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'1801'" in f:
                c["formula"] = _replace_code_in_formula(f, "1801", "1704")
                changes.append(f"I2 明细表: TB('1801') → TB('1704') in {c['cell_ref']}")
        # 🔴 `研发费用_期末` 原写 TB('6602')，而 6602 是**管理费用**（归 K9）。
        # 该格 description 自称「与 I6 勾稽」而 I6 研发费用真源是 6604
        # （本脚本第 6/10 步已把 I6 两块的 6602 全改成 6604）→ 此处不改就是
        # 「同一勾稽两端取不同科目」，且拿管理费用当研发费用是数字级错误。
        # 旧注释「TB('6602') 保留（用于与 I6 勾稽），不改」是错的，已撤回。
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if f"'{RD_EXPENSE_WRONG}'" in f:
                c["formula"] = _replace_code_in_formula(
                    f, RD_EXPENSE_WRONG, RD_EXPENSE_RIGHT
                )
                changes.append(
                    f"I2 明细表: TB('{RD_EXPENSE_WRONG}') → "
                    f"TB('{RD_EXPENSE_RIGHT}') in {c['cell_ref']}（研发费用非管理费用）"
                )
        # ⚠️ 此处**不得**再写 `account_codes` —— 该字段的唯一写者在本节开头。
        #    （改造前这里有第二个写者，与节首那个取值不同，二次 --apply 会输出
        #     两条相反的变更记录 = 多写者事故的典型征兆。）

    # --- 8. I3 明细块：删除引用 1712 的 cells（account_chart 无此码） ---
    b = _find_block(doc, "I3", "明细表I3-2")
    if b:
        removed = _remove_cells_with_code(b, "1712")
        if removed:
            changes.append(f"I3 明细表: 删除 {removed} 条引用 1712 的 cells")
        # Also fix account_codes: remove '1712'
        codes = b.get("account_codes", [])
        if "1712" in codes:
            codes.remove("1712")
            b["account_codes"] = codes
            changes.append("I3 明细表: account_codes 删除 '1712'")


    # --- 9. I4 明细块：account_codes→['1801']（删 1811）; 删 TB('1811') cells ---
    b = _find_block(doc, "I4", "明细表I4-2")
    if b:
        if b.get("account_codes") != ["1801"]:
            b["account_codes"] = ["1801"]
            changes.append("I4 明细表: account_codes → ['1801'] (删 1811)")
        removed = _remove_cells_with_code(b, "1811")
        if removed:
            changes.append(f"I4 明细表: 删除 {removed} 条引用 1811 的 cells")

    # --- 10. I6 月度明细块：account_codes→['6604']; TB/LEDGER('6602')→('6604') ---
    b = _find_block(doc, "I6", "明细表I6-2")
    if b:
        if b.get("account_codes") != ["6604"]:
            b["account_codes"] = ["6604"]
            changes.append("I6 月度明细: account_codes → ['6604']")
        for c in b.get("cells", []):
            f = c.get("formula", "")
            if "'6602'" in f:
                c["formula"] = _replace_code_in_formula(f, "6602", "6604")
                changes.append(f"I6 月度明细: ('6602') → ('6604') in {c['cell_ref']}")

    # --- 11. I1 分析程序块：整块删除（引用不存在的 sheet + 病态 TB_SUM） ---
    idx_to_remove = None
    for i, blk in enumerate(_blocks(doc)):
        if blk.get("wp_code") == "I1" and blk.get("sheet") == "分析程序I1-3":
            idx_to_remove = i
            break
    if idx_to_remove is not None:
        _blocks(doc).pop(idx_to_remove)
        changes.append("I1 分析程序块: 整块删除（sheet '分析程序I1-3' 不存在 + 病态 TB_SUM）")

    # --- 12. I2 资本化判断块：account_codes→['1704'] ---
    b = _find_block(doc, "I2", "研发项目资本化时点判断I2-6")
    if b:
        if b.get("account_codes") != ["1704"]:
            b["account_codes"] = ["1704"]
            changes.append("I2 资本化判断块: account_codes → ['1704']")

    return doc, changes


# ---------------------------------------------------------------------------
# check: verify no remaining errors
# ---------------------------------------------------------------------------

def check(doc: dict[str, Any]) -> list[str]:
    """Check for remaining I-cycle preset errors. Returns list of issues."""
    issues: list[str] = []

    # I1 审定表
    # 🔴 必须按新旧两个 sheet 名查找 —— 改名后旧键找不到块，
    #    否则「块不存在」会被当成合规（`if b:` 静默跳过全部判据）。
    b = _find_block(doc, "I1", I1_SHEET_RIGHT) or _find_block(
        doc, "I1", I1_SHEET_WRONG
    )
    if b:
        codes = b.get("account_codes", [])
        if "1703" not in codes:
            issues.append("I1 审定表: account_codes 缺 '1703'")
        # 🔴 块自己的 `sheet` 字段（此前漏判 —— 旧版只查公式实参，
        #    于是 `--check` rc=0 而数据侧 sheet 名仍是源模板不存在的 `审定表I1-1`）
        if b.get("sheet") != I1_SHEET_RIGHT:
            issues.append(
                f"I1 审定表: sheet='{b.get('sheet')}'（源模板真实 tab 名是 "
                f"'{I1_SHEET_RIGHT}'，无 '-1'；I1 是六循环唯一例外）"
            )
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if f"{I1_SHEET_WRONG}'" in formulas:
            issues.append(
                f"I1 审定表: PREV 仍引用 '{I1_SHEET_WRONG}'（应为 '{I1_SHEET_RIGHT}'）"
            )
    else:
        issues.append("I1 审定表块不存在")

    # I2 审定表
    b = _find_block(doc, "I2", "审定表I2-1")
    if b:
        if b.get("wp_name") != "开发支出审定表":
            issues.append(f"I2 审定表: wp_name='{b.get('wp_name')}' (应为 '开发支出审定表')")
        if b.get("account_codes") != ["1704"]:
            issues.append(f"I2 审定表: account_codes={b.get('account_codes')} (应为 ['1704'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1711'" in formulas:
            issues.append("I2 审定表: 仍引用 '1711'")
    else:
        issues.append("I2 审定表块不存在")

    # I3 审定表
    b = _find_block(doc, "I3", "审定表I3-1")
    if b:
        if b.get("wp_name") != "商誉审定表":
            issues.append(f"I3 审定表: wp_name='{b.get('wp_name')}' (应为 '商誉审定表')")
        if b.get("account_codes") != ["1711"]:
            issues.append(f"I3 审定表: account_codes={b.get('account_codes')} (应为 ['1711'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1801'" in formulas:
            issues.append("I3 审定表: 仍引用 '1801'")
    else:
        issues.append("I3 审定表块不存在")

    # I4 审定表
    b = _find_block(doc, "I4", "审定表I4-1")
    if b:
        if b.get("wp_name") != "长期待摊费用审定表":
            issues.append(f"I4 审定表: wp_name='{b.get('wp_name')}' (应为 '长期待摊费用审定表')")
        if b.get("account_codes") != ["1801"]:
            issues.append(f"I4 审定表: account_codes={b.get('account_codes')} (应为 ['1801'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1703'" in formulas:
            issues.append("I4 审定表: 仍引用 '1703'")
    else:
        issues.append("I4 审定表块不存在")


    # I5 审定表
    b = _find_block(doc, "I5", "审定表I5-1")
    if b:
        if b.get("account_codes") != []:
            issues.append(f"I5 审定表: account_codes={b.get('account_codes')} (应为 [])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1811'" in formulas:
            issues.append("I5 审定表: 仍引用 '1811'")
    else:
        issues.append("I5 审定表块不存在")

    # I6 审定表
    b = _find_block(doc, "I6", "审定表I6-1")
    if b:
        if b.get("account_codes") != ["6604"]:
            issues.append(f"I6 审定表: account_codes={b.get('account_codes')} (应为 ['6604'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'6602'" in formulas:
            issues.append("I6 审定表: 仍引用 '6602'")
    else:
        issues.append("I6 审定表块不存在")

    # I2 明细块
    b = _find_block(doc, "I2", "明细表I2-2")
    if b:
        # 🔴 期望值由 ['1704','5301'] 改为 ['1704','6604']：
        #    `5301` 是旧《企业会计制度》成本类码（`account_chart` 的 standard 侧
        #    5xxx 段全是零余额骨架行）；本块「研发费用_期末」格取的是研发费用，
        #    真源 = `6604`（与 I6 同一科目，见 `report_config` 的 IS-006）。
        if b.get("account_codes") != ["1704", "6604"]:
            issues.append(
                f"I2 明细表: account_codes={b.get('account_codes')} "
                "(应为 ['1704','6604'])"
            )
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1801'" in formulas:
            issues.append("I2 明细表: 仍引用 '1801'（应改 '1704'）")
        # 🔴 此前漏判：旧版把这处 `TB('6602')` 注释成「保留（用于与 I6 勾稽），不改」，
        #    而 `6602` 是**管理费用**（归 K9），与该格 description 自称的
        #    「研发费用本期累计费用化金额（与 I6 勾稽）」矛盾。
        if "'6602'" in formulas:
            issues.append(
                "I2 明细表: 仍引用 '6602'（管理费用，归 K9）—— "
                "「研发费用_期末」格应取 '6604'"
            )

    # I3 明细块
    b = _find_block(doc, "I3", "明细表I3-2")
    if b:
        codes = b.get("account_codes", [])
        if "1712" in codes:
            issues.append("I3 明细表: account_codes 仍含 '1712'")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1712'" in formulas:
            issues.append("I3 明细表: 仍引用 '1712'（account_chart 无此码）")

    # I4 明细块
    b = _find_block(doc, "I4", "明细表I4-2")
    if b:
        if b.get("account_codes") != ["1801"]:
            issues.append(f"I4 明细表: account_codes={b.get('account_codes')} (应为 ['1801'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'1811'" in formulas:
            issues.append("I4 明细表: 仍引用 '1811'")

    # I6 月度明细
    b = _find_block(doc, "I6", "明细表I6-2")
    if b:
        if b.get("account_codes") != ["6604"]:
            issues.append(f"I6 月度明细: account_codes={b.get('account_codes')} (应为 ['6604'])")
        formulas = " ".join(c.get("formula", "") for c in b.get("cells", []))
        if "'6602'" in formulas:
            issues.append("I6 月度明细: 仍引用 '6602'")

    # I1 分析程序块应已删除
    b = _find_block(doc, "I1", "分析程序I1-3")
    if b is not None:
        issues.append("I1 分析程序块: 仍存在（应已删除，sheet 不存在 + 病态 TB_SUM）")

    # I2 资本化判断块
    b = _find_block(doc, "I2", "研发项目资本化时点判断I2-6")
    if b:
        if b.get("account_codes") != ["1704"]:
            issues.append(f"I2 资本化判断块: account_codes={b.get('account_codes')} (应为 ['1704'])")

    # --- R4.1：12 张披露 sheet 必须「有预设块」或「已显式登记为无预设」 ---
    #
    # 这条判据的价值不是逼人补预设，而是**杜绝沉默** —— 改造前 12 张披露 sheet
    # 既无预设也无登记，读者无法区分「有意不给」与「忘了给」。
    declared = {
        (b.get("wp_code"), b.get("sheet"))
        for b in _blocks(doc)
        if b.get("sheet") in {s for _, s in DISCLOSURE_SHEETS}
    }
    for wp, sheet in DISCLOSURE_SHEETS:
        if (wp, sheet) in declared:
            continue  # 有预设块 = 合规
        if (wp, sheet) not in DISCLOSURE_NO_PRESET_REGISTRY:
            issues.append(
                f"{wp} 披露 sheet '{sheet}'：既无预设块、也未登记进 "
                "DISCLOSURE_NO_PRESET_REGISTRY（R4.1 要求二者之一，禁沉默）"
            )

    return issues


def check_registry_consistency() -> list[str]:
    """登记表自身的一致性（不依赖 JSON，供守卫与 CLI 共用）。

    三条（缺一即让登记表退化成逃逸阀）：

    1. **覆盖完备** —— `DISCLOSURE_SHEETS` 的每一项都要有归属（预设块或登记）。
    2. **无冗余** —— 登记表不得出现 `DISCLOSURE_SHEETS` 之外的键（防拿它豁免别的 sheet）。
    3. **理由实质** —— 每条理由必须够长且含实证标记（禁「暂不需要」这类空话）。
    """
    out: list[str] = []
    known = set(DISCLOSURE_SHEETS)

    for key in DISCLOSURE_NO_PRESET_REGISTRY:
        if key not in known:
            out.append(f"登记表出现未知 sheet {key}（不在 DISCLOSURE_SHEETS 内）")

    markers = ("引用", "格", "明细表", "定性", "源模板", "#REF!", "推送")
    for key, reason in DISCLOSURE_NO_PRESET_REGISTRY.items():
        if len(reason) < 30:
            out.append(f"{key} 的登记理由过短（{len(reason)} 字），须写明实证依据")
        elif not any(m in reason for m in markers):
            out.append(
                f"{key} 的登记理由缺实证标记（须含 {'/'.join(markers)} 之一）"
            )

    if len(DISCLOSURE_NO_PRESET_REGISTRY) > len(DISCLOSURE_SHEETS):
        out.append(
            f"登记条目数 {len(DISCLOSURE_NO_PRESET_REGISTRY)} 超过披露 sheet 总数 "
            f"{len(DISCLOSURE_SHEETS)}（上限只许下调）"
        )

    # 4. 交叉锁死：披露 sheet 总数必须与源模板事实（6 循环 × 2 变体）一致。
    #    🔴 这条防的是「把某张 sheet 从 DISCLOSURE_SHEETS 悄悄删掉」—— 该集合是
    #    R4.1 判据的遍历面，集合小了就静默失去对该 sheet 的覆盖（循环自然扫不到）。
    if len(DISCLOSURE_SHEETS) != _DISCLOSURE_SHEET_COUNT:
        out.append(
            f"披露 sheet 全集 {len(DISCLOSURE_SHEETS)} != 源模板事实 "
            f"{_DISCLOSURE_SHEET_COUNT}（6 循环 × 2 变体）。"
            "若某张已改为配预设，须把它移出登记表**并**下调本锚点，两处同改。"
        )

    # 5. 六循环各恰好两张（防某循环整体漏登记）
    per_cycle: dict[str, int] = {}
    for wp, _sheet in DISCLOSURE_SHEETS:
        per_cycle[wp] = per_cycle.get(wp, 0) + 1
    for wp in ("I1", "I2", "I3", "I4", "I5", "I6"):
        if per_cycle.get(wp, 0) != 2:
            out.append(
                f"{wp} 的披露 sheet 数为 {per_cycle.get(wp, 0)}（应为 2：上市 + 国企）"
            )
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="修正 I 类公式预设（幂等）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="写回修订到 JSON 文件")
    mode.add_argument("--check", action="store_true", help="检查是否有未修正的错误（CI 用）")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)

    if args.check:
        issues = check_registry_consistency() + check(doc)
        if issues:
            print(f"[FAIL] {len(issues)} 个未修正的 I 类预设错误：")
            for iss in issues:
                print(f"  - {iss}")
            return 1
        print("[OK] I 类公式预设校验通过（0 个错误）")
        return 0

    # Default: dry-run (print changes without writing)
    doc, changes = apply_fixes(doc)

    if not changes:
        print("无需修改（已对齐）")
    else:
        print(f"修订方案（{len(changes)} 处变更）：")
        for ch in changes:
            print(f"  - {ch}")

    # Post-apply validation
    issues = check(doc)
    if issues:
        print(f"\n[ERROR] 修订后仍有 {len(issues)} 个未修正错误：")
        for iss in issues:
            print(f"  - {iss}")
        return 1

    if not args.apply:
        print("\n[dry-run] 未写文件。使用 --apply 写入。")
        return 0

    # Write back
    if changes:
        trailing = "\n" if raw.endswith("\n") else ""
        MAPPING_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
            encoding="utf-8",
        )
        print(f"\n已写入 {MAPPING_PATH}")

    print("[OK] I 类公式预设修正完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
