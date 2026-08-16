#!/usr/bin/env python
"""K 循环公式预设修正幂等脚本。

修正 `prefill_formula_mapping.json` 中 K3~K13 的 9 个错位块 + 移除 K14~K18 的
5 个孤儿块 + 清 K6 的病态区间 + 纠正 K5 明细块的科目码。

**根因**：`prefill_formula_mapping.json` 的 K 块全部按「遗留审定表族」编号写入，
与平台真实的致同 2025 模板族（`backend/wp_templates/K/*.xlsx` + `RENDERER_DISPATCH`
+ `componentType` 三方一致）全面错位。

**实证**（`report_config` + `account_chart` + `tb_balance` + `trial_balance` 四表交叉）::

    wp_code | 预设 wp_name       | 预设 accounts | 真实循环  | 真值科目
    K3      | 财务费用审定表      | ['6603']      | 其他应付款 | 2241
    K4      | 研发费用审定表      | ['6604']      | 其他流动负债| 无（宁缺勿造）
    K5      | 税金及附加审定表    | ['6403']      | 预计负债   | 2801
    K5(明细)| 预计负债明细        | ['2241']+2701 | 预计负债   | 2801
    K6      | 持有待售...审定表   | ['1481','2331']| 持有待售  | 无
    K7      | 预付款项审定表      | ['1123']      | 递延收益   | 2401
    K10     | 营业外收入审定表    | ['6301']      | 其他收益   | 6117
    K11     | 营业外支出审定表    | ['6711']      | 资产减值损失| 6701
    K12     | 信用减值损失审定表  | ['6701']      | 营业外收入 | 6301
    K13     | 资产减值损失审定表  | ['6702']      | 营业外支出 | 6711
    K14~K18 | (5 个)              | 各异          | 平台无循环 | 孤儿

**操作**：
- `--dry-run`（默认）：只报告变更，不写盘
- `--check`：报告后以 exit code 指示（0=无需变更，1=有欠账）
- `--apply`：执行变更并写盘

**幂等性**：多次 `--apply` 的结果与一次相同（已修正的块不再触发变更）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Task 15 / Requirements 7.1~7.5 / Property 12, 13, 14, 15
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prefill_formula_mapping.json"

# ─────────────────────────────────────────────────────────────────────────────
# 正确科目映射（report_config 实证，k_cycle_specs.py 单一真源）
# ─────────────────────────────────────────────────────────────────────────────

CORRECT_ACCOUNTS: dict[str, str | None] = {
    "K3": "2241",   # 其他应付款 BS-050
    "K4": None,     # 其他流动负债 BS-053 四变体 formula 全 NULL + account_chart 两侧零命中
    "K5": "2801",   # 预计负债 BS-065
    # 🔴 2026-08-14 由 None 改 '1481'：原值依据「四行 formula 全 None」，而那四个
    #    row_code（BS-015/BS-024/BS-056/BS-079）本身就是错的 —— 按 row_name 反查后
    #    正确落点是 BS-012（资产 TB('1481')）/ BS-051（负债 TB('2245')）/
    #    IMP-007（备抵 TB('1482')），公式都在，且 1481/1482/2245 在 account_chart
    #    client 侧确实存在。声明真源 `k_cycle_specs.K_CYCLE_SPECS['K6']` 已
    #    `has_account=True` / `fallback_standard='1481'`，此处与它对齐。
    "K6": "1481",   # 持有待售资产 BS-012
    "K7": "2401",   # 递延收益 BS-066
    "K8": "6601",   # 销售费用 IS-004/IS-022
    "K9": "6602",   # 管理费用 IS-005/IS-023
    "K10": "6117",  # 其他收益 IS-010/IS-030
    "K11": "6701",  # 资产减值损失 IS-017/IS-038 (None→兜底)
    "K12": "6301",  # 营业外收入 IS-020/IS-041
    "K13": "6711",  # 营业外支出 IS-021/IS-043
}

CORRECT_WP_NAMES: dict[str, str] = {
    "K3": "其他应付款审定表",
    "K4": "其他流动负债审定表",
    "K5": "预计负债审定表",
    "K6": "持有待售资产和负债审定表",
    "K7": "递延收益审定表",
    "K8": "销售费用审定表",
    "K9": "管理费用审定表",
    "K10": "其他收益审定表",
    "K11": "资产减值损失审定表",
    "K12": "营业外收入审定表",
    "K13": "营业外支出审定表",
}

ORPHAN_WP_CODES = {"K14", "K15", "K16", "K17", "K18"}

# K5 明细块的错误科目：原写 2241（其他应付款）和公式里写 2701（长期应付款）
K5_DETAIL_WRONG_CODES = {"2241", "2701"}


def _build_correct_cells(wp_code: str, acct: str | None) -> list[dict]:
    """为主审定表块生成正确的 cells（只含基础公式：TB + ADJ + PREV）。"""
    if acct is None:
        return []  # 宁缺勿造：不含 TB() 公式
    is_pl = acct.startswith("6")
    period = "本期发生额" if is_pl else "期末余额"
    period_begin = "本期发生额" if is_pl else "期初余额"
    # 损益类只有本期发生额口径
    cells = [
        {"cell_ref": "期初余额", "formula": f"=TB('{acct}','{period_begin}')",
         "label": f"从试算表取{CORRECT_WP_NAMES[wp_code][:4]}{period_begin}",
         "description": f"科目由报表行映射解析（k_cycle_specs 声明真源），兜底 {acct}"},
        {"cell_ref": "未审数", "formula": f"=TB('{acct}','{period}')",
         "label": f"从试算表取{CORRECT_WP_NAMES[wp_code][:4]}{period}（未审）",
         "description": f"四表取数权威口径 = trial_balance"},
        {"cell_ref": "AJE调整", "formula": f"=ADJ('{acct}','aje_net')",
         "label": f"{CORRECT_WP_NAMES[wp_code][:4]}审计调整分录净额",
         "description": ""},
        {"cell_ref": "RJE调整", "formula": f"=ADJ('{acct}','rje_net')",
         "label": f"{CORRECT_WP_NAMES[wp_code][:4]}重分类调整分录净额",
         "description": ""},
        {"cell_ref": "上年审定数", "formula": f"=PREV('{wp_code}','审定表{wp_code}-1','审定数')",
         "label": "上年同底稿审定数",
         "description": ""},
    ]
    return cells


def _build_k5_detail_cells() -> list[dict]:
    """K5 预计负债明细块的正确 cells（科目 2801 不是 2701/2241）。"""
    return [
        {"cell_ref": "预计负债_期末未审数", "formula": "=TB('2801','期末余额')",
         "label": "从试算表取预计负债（2801）期末余额",
         "description": "🔴 历史写 2701（长期应付款）是错误科目族"},
        {"cell_ref": "预计负债_期初余额", "formula": "=TB('2801','期初余额')",
         "label": "从试算表取预计负债（2801）期初余额",
         "description": ""},
        {"cell_ref": "本期借方发生额", "formula": "=TB('2801','借方发生额')",
         "label": "从试算表取预计负债本期借方发生额（冲销/支付）",
         "description": ""},
        {"cell_ref": "本期贷方发生额", "formula": "=TB('2801','贷方发生额')",
         "label": "从试算表取预计负债本期贷方发生额（计提）",
         "description": ""},
    ]


def apply_fixes(data: dict) -> list[str]:
    """对 mappings 列表就地修正，返回变更日志。"""
    mappings = data["mappings"]
    changes: list[str] = []

    # Pass 1: Remove orphans K14~K18
    orphans = [i for i, x in enumerate(mappings)
               if x.get("wp_code") in ORPHAN_WP_CODES]
    for i in reversed(orphans):
        block = mappings[i]
        changes.append(f"REMOVE orphan: {block['wp_code']} | {block.get('wp_name','')}")
        del mappings[i]

    # Pass 2: Fix main adjudication blocks for K3~K13
    for x in mappings:
        wc = x.get("wp_code", "")
        if wc not in CORRECT_ACCOUNTS:
            continue
        expected_acct = CORRECT_ACCOUNTS[wc]
        current_accts = x.get("account_codes", [])
        current_name = x.get("wp_name", "")
        cells = x.get("cells") or x.get("entries") or []

        # 主审定表块的判据 = **sheet 名含「审定表」**（结构事实，不依赖公式）。
        #
        # 🔴 两次踩坑记录，别再改回公式判据：
        # ① 原判据 `any("ADJ(" in f)`：K6 曾走「宁缺勿造」分支被剥成**只剩 PREV**，
        #    本脚本认不出它是主块而跳过，而守卫
        #    `test_main_block_account_codes_correct` 的判据是 `ADJ( or PREV(`
        #    认得出 ⇒ 守卫红、脚本报「无需变更」，欠账永远修不掉。
        # ② 于是放宽成 `ADJ( or PREV(`，结果「实质性分析K8-4」块（含
        #    `PREV('K8','审定表K8-1','审定数')`）被当成审定表块，`wp_name` 差点被改成
        #    「销售费用审定表」—— 它是实质性分析表。
        # sheet 名是唯一不会两头摇的判据。
        is_main = "审定表" in str(x.get("sheet", ""))
        # K5 detail block: has "预计负债" in wp_name and no ADJ
        is_k5_detail = (wc == "K5" and not is_main and
                        any(c for c in current_accts if c in K5_DETAIL_WRONG_CODES))
        # K3 detail (其他应付款明细): correct account 2241, has AUX formulas — leave as-is
        is_k3_detail = (wc == "K3" and not is_main and "2241" in current_accts)

        if is_k3_detail:
            continue  # K3 明细块科目码本就正确

        if is_k5_detail:
            # Fix K5 detail block
            if current_accts != ["2801"]:
                changes.append(f"FIX K5 detail: account_codes {current_accts} → ['2801']")
                x["account_codes"] = ["2801"]
            # Fix cells
            new_cells = _build_k5_detail_cells()
            if cells != new_cells:
                changes.append(f"FIX K5 detail: rewrite {len(cells)} cells → {len(new_cells)} cells")
                x["cells"] = new_cells
            continue

        if not is_main:
            continue  # Skip non-adjudication blocks (K8 月度明细 / K8 分析程序 etc.)

        # Fix wp_name
        correct_name = CORRECT_WP_NAMES.get(wc, "")
        if correct_name and current_name != correct_name:
            changes.append(f"FIX {wc}: wp_name '{current_name}' → '{correct_name}'")
            x["wp_name"] = correct_name

        # Fix account_codes
        if expected_acct is None:
            # Should not have TB() — but keep block with empty cells for PREV()
            new_accts: list[str] = []
            if current_accts != new_accts:
                changes.append(f"FIX {wc}: account_codes {current_accts} → [] (宁缺勿造)")
                x["account_codes"] = new_accts
            # Remove TB/ADJ cells, keep only PREV
            new_cells = [c for c in cells if "PREV(" in (c.get("formula") or "")]
            if not new_cells:
                new_cells = [{"cell_ref": "上年审定数",
                              "formula": f"=PREV('{wc}','审定表{wc}-1','审定数')",
                              "label": "上年同底稿审定数", "description": ""}]
            if cells != new_cells:
                changes.append(f"FIX {wc}: strip TB/ADJ cells → keep {len(new_cells)} PREV-only")
                x["cells"] = new_cells
        else:
            # Fix account_codes
            if expected_acct not in str(current_accts):
                new_accts_list = [expected_acct]
                changes.append(f"FIX {wc}: account_codes {current_accts} → {new_accts_list}")
                x["account_codes"] = new_accts_list

            # Rebuild cells with correct account
            new_cells = _build_correct_cells(wc, expected_acct)
            # Check if current cells reference wrong codes
            has_wrong = any(
                expected_acct not in (c.get("formula") or "")
                for c in cells
                if "TB(" in (c.get("formula") or "") or "ADJ(" in (c.get("formula") or "")
            )
            if has_wrong:
                changes.append(f"FIX {wc}: rewrite {len(cells)} cells (wrong code → {expected_acct})")
                x["cells"] = new_cells

    # Pass 3: Clean pathological ranges in K6
    for x in mappings:
        if x.get("wp_code") != "K6":
            continue
        cells = x.get("cells") or x.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if "TB_SUM('1481~2331')" in f:
                changes.append(f"FIX K6: remove pathological TB_SUM('1481~2331') in {c.get('cell_ref','')}")
                c["formula"] = ""
                c["description"] = (c.get("description") or "") + " [removed: TB_SUM('1481~2331') 跨科目大类病态区间]"

    # Pass 4: Fix K8 附加块的病态区间 TB_SUM('6601~6603')
    for x in mappings:
        if x.get("wp_code") != "K8":
            continue
        cells = x.get("cells") or x.get("entries") or []
        for c in cells:
            f = c.get("formula") or ""
            if "TB_SUM('6601~6603')" in f:
                # Replace with single-code: 这个块是 K8 分析程序，应只取 6601
                new_f = f.replace("TB_SUM('6601~6603','期末余额')", "=TB('6601','期末余额')")
                new_f = new_f.replace("TB_SUM('6601~6603'", "TB('6601'")
                if new_f != f:
                    changes.append(f"FIX K8 analysis: TB_SUM('6601~6603') → TB('6601') in {c.get('cell_ref','')}")
                    c["formula"] = new_f

    # Pass 5: Add WP() linkage (审定表 ← 明细表/检查表勾稽)
    # 铁律：明细表块禁含 WP() 防成环；审定表块可引明细表
    WP_LINKAGE: dict[str, list[dict]] = {
        "K3": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K3','明细表K3-2','期末余额合计')",
             "label": "审定表与 K3-2 明细表期末合计勾稽", "description": "🔴 反向不可：K3-2 禁引 WP() 防循环"},
        ],
        "K5": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K5','明细表K5-2','期末余额合计')",
             "label": "审定表与 K5-2 明细表期末合计勾稽", "description": ""},
        ],
        "K7": [
            {"cell_ref": "明细表期末合计", "formula": "=WP('K7','明细表K7-2','期末余额合计')",
             "label": "审定表与 K7-2 明细表期末合计勾稽", "description": ""},
        ],
        "K8": [
            {"cell_ref": "明细表本期合计", "formula": "=WP('K8','明细表K8-2','本期发生额合计')",
             "label": "审定表与 K8-2 明细表本期发生额合计勾稽", "description": ""},
        ],
        "K9": [
            {"cell_ref": "明细表本期合计", "formula": "=WP('K9','明细表K9-2','本期发生额合计')",
             "label": "审定表与 K9-2 明细表本期发生额合计勾稽", "description": ""},
        ],
    }
    for x in mappings:
        wc = x.get("wp_code", "")
        if wc not in WP_LINKAGE:
            continue
        cells = x.get("cells") or x.get("entries") or []
        # 🔴 判据必须是 **sheet 名含「审定表」**，与 Pass 2 保持一致。
        #
        # 原判据 `any("ADJ(" or "PREV(" in formula)` 在 Task 12 建了披露块后立刻出事：
        # 披露块含 `PREV()`（上年账面价值 / 上期发生额）⇒ 被误认成审定表块 ⇒
        # 本 Pass 往**披露块**里塞明细表引用，破坏了「披露块只单向引用审定表」的
        # 防环设计（否则成 审定表→明细表→披露→审定表 三角环）。
        # Task 11 修 Pass 2 时漏了这里，是同一个判据缺陷的第二处。
        if "审定表" not in str(x.get("sheet", "")):
            continue
        for wp_entry in WP_LINKAGE[wc]:
            # Check if already present
            existing_refs = {c.get("cell_ref") for c in cells}
            if wp_entry["cell_ref"] in existing_refs:
                continue
            cells.append(wp_entry)
            changes.append(f"ADD WP: {wc} | {wp_entry['cell_ref']} → {wp_entry['formula']}")
        x["cells"] = cells

    changes += _apply_closure_fixes(mappings)
    return changes


# ─────────────────────────────────────────────────────────────────────────────
# 以下为 spec `k-cycle-extraction-formula-and-disclosure-closure` Task 11 追加
# ─────────────────────────────────────────────────────────────────────────────

#: 公式函数名 → `formula_type`（Property 19：K 前缀全部 cell 必须有 formula_type）
_FORMULA_TYPE_BY_FN: tuple[tuple[str, str], ...] = (
    ("TB_SUM(", "TB_SUM"),
    ("LEDGER_DETAIL(", "LEDGER_DETAIL"),
    ("TB(", "TB"),
    ("ADJ(", "ADJ"),
    ("PREV(", "PREV"),
    ("WP(", "WP"),
    ("AUX(", "AUX"),
)

#: 源 xlsx 真实 tab 名（openpyxl 直读 `backend/wp_templates/K/*.xlsx`，2026-08-14 实测）。
#:
#: 🔴 **空格是源模板事实，必须逐字保留** —— K4/K5/K6 的部分 tab 名带空格
#: （`审定表 K5-1` / `明细表 K5-2`），而预设的 `PREV()`/`WP()` 实参把空格丢了，
#: 指向源 xlsx 不存在的 tab ⇒ 该引用永不命中。**不要把空格当笔误清掉**。
_SHEET_ARG_CORRECTIONS: dict[str, str] = {
    "审定表K5-1": "审定表 K5-1",
    "明细表K5-2": "明细表 K5-2",
}

#: 损益类（`6xxx`）期间口径改正。
#:
#: 判据两条：
#: ① `COLUMN_ALIASES`（`app/services/formula_engine.py`）已注册 `本期发生额`；
#: ② 平台损益类循环的既有范式就是它 —— 实测 `本期发生额` 在 6xxx 科目上用了 49 次
#:    （D4 / G11 / G12 全部如此），而 K8/K9 用 `期初余额`/`期末余额` 是异常。
#:
#: 损益类**没有期初余额概念**（费用是发生额、不结转余额）。故：
#: - 「未审数」类格 → `本期发生额`
#: - 「期初」类格 → 改走 `PREV()` 取**上年同格**（对应源模板列头「上期未审数」）
#:
#: 🔴 只改 `formula`，**不改 `cell_ref`** —— 后者是绑定键：
#: `prefill_anchor_map` 以 `(wp_code, sheet, cell_ref)` 三元组做锚点、
#: `wp_template_init_service` 以 `sheet!cell_ref` 判用户自定义公式是否覆盖、
#: 前端 `k0MatrixSpec.spec.ts` 已把 cell_ref 与预设逐字锁死。改名会让用户已录入的
#: 公式覆盖与地址坐标同时失联。
_PL_PERIOD = "本期发生额"


def _infer_formula_type(formula: str) -> str | None:
    """从公式推断 `formula_type`（取最先匹配的函数名，长名优先）。"""
    f = str(formula or "")
    if not f:
        return None
    for token, ftype in _FORMULA_TYPE_BY_FN:
        if token in f:
            return ftype
    return None


def _apply_closure_fixes(mappings: list[dict]) -> list[str]:
    """Task 11 的六类改正（幂等）。

    🔴 删块必须**最先**做：否则后续几个 Pass 会先给它补 `formula_type`、改期间口径，
    再把整块删掉 —— 白做一趟且变更日志里留下误导性的记录。
    """
    changes: list[str] = []
    changes += _remove_dead_k8_analysis_block(mappings)
    k_blocks = [
        b for b in mappings if str(b.get("wp_code", "")).upper().startswith("K")
    ]

    # ── ① Property 19：补 formula_type ────────────────────────────────
    for b in k_blocks:
        wc = b.get("wp_code")
        for c in b.get("cells") or []:
            if c.get("formula_type"):
                continue
            ftype = _infer_formula_type(c.get("formula") or "")
            if ftype is None:
                continue
            c["formula_type"] = ftype
            changes.append(
                f"ADD formula_type: {wc} | {b.get('sheet')} | "
                f"{c.get('cell_ref')} → {ftype}"
            )

    # ── ② Property 23：公式实参 sheet 名补空格 ─────────────────────────
    for b in k_blocks:
        wc = b.get("wp_code")
        for c in b.get("cells") or []:
            f = str(c.get("formula") or "")
            if not f:
                continue
            new_f = f
            for wrong, right in _SHEET_ARG_CORRECTIONS.items():
                new_f = new_f.replace(f"'{wrong}'", f"'{right}'")
            if new_f != f:
                c["formula"] = new_f
                changes.append(
                    f"FIX sheet arg: {wc} | {b.get('sheet')} | "
                    f"{c.get('cell_ref')} | {f} → {new_f}"
                )

    # ── ③ Property 20：损益类期间口径 ─────────────────────────────────
    for b in k_blocks:
        wc = str(b.get("wp_code", ""))
        sheet = str(b.get("sheet", ""))
        accts = [str(a) for a in (b.get("account_codes") or [])]
        if not accts or not all(a.startswith("6") for a in accts):
            continue
        cells = b.get("cells") or []
        # 🔴 `PREV()` 的第三参必须是**本块内真实存在**的 cell_ref。
        #    初版硬编码 `'未审数'`：对审定表成立，但「实质性分析K8-4」块的格是
        #    「本年发生额 / 上年发生额 / 本年期初 / 本年期末」—— 没有「未审数」⇒
        #    PREV 指向不存在的锚点、永不命中，而 JSON 里是字符串、静态检查查不出。
        #    故按「本块现有 cell_ref」择一：优先含「未审」，否则取第一个非期初的 TB 格。
        own_refs = [str(c.get("cell_ref") or "") for c in cells]
        prev_target = next((r for r in own_refs if "未审" in r), "")
        if not prev_target:
            prev_target = next(
                (
                    r
                    for r, c in zip(own_refs, cells)
                    if "期初" not in r and "TB(" in str(c.get("formula") or "")
                ),
                "",
            )
        for c in cells:
            ref = str(c.get("cell_ref") or "")
            f = str(c.get("formula") or "")
            if not f or "TB(" not in f and "TB_SUM(" not in f:
                continue
            # 「期初」类格：损益类无期初余额 ⇒ 走 PREV 取上年同格
            if "期初" in ref:
                if not prev_target:
                    changes.append(
                        f"SKIP PL period (无可指向的本块 cell_ref): {wc} | {sheet} | {ref}"
                    )
                    continue
                new_f = f"=PREV('{wc}','{sheet}','{prev_target}')"
                if f != new_f:
                    c["formula"] = new_f
                    c["formula_type"] = "PREV"
                    c["description"] = (
                        f"上年同底稿「{prev_target}」格（损益类无期初余额概念，"
                        "对应源模板列头「上期未审数」）"
                    )
                    changes.append(
                        f"FIX PL period: {wc} | {sheet} | {ref} | {f} → {new_f}"
                    )
                continue
            # 其余格：余额口径 → 本期发生额
            new_f = f
            for wrong in ("期末余额", "期初余额", "贷方发生额", "借方发生额"):
                new_f = new_f.replace(f"'{wrong}'", f"'{_PL_PERIOD}'")
            if new_f != f:
                c["formula"] = new_f
                changes.append(
                    f"FIX PL period: {wc} | {sheet} | {ref} | {f} → {new_f}"
                )

    # ── ④ Property 22：删项目专属辅助项编码 ────────────────────────────
    #    `AUX('2241','代收代付类别','A001','期末余额')` 里的 `A001` 是**某个项目**的
    #    辅助项编码，换个项目就不存在 ⇒ 预设对其余项目全体失效。
    #    宁缺勿造：整块删除（保留空 cells），由审计师在底稿内按本项目实际辅助项建行。
    _AUX_CODE_RE = re.compile(r"\b(?:YG\d+|SKT\d+|A\d{3})\b")
    for b in k_blocks:
        wc = b.get("wp_code")
        cells = b.get("cells") or []
        polluted = [
            c
            for c in cells
            if _AUX_CODE_RE.search(str(c.get("formula") or ""))
            or _AUX_CODE_RE.search(str(c.get("cell_ref") or ""))
        ]
        if not polluted:
            continue
        kept = [c for c in cells if c not in polluted]
        codes = sorted(
            {
                m
                for c in polluted
                for m in _AUX_CODE_RE.findall(
                    str(c.get("formula") or "") + str(c.get("cell_ref") or "")
                )
            }
        )
        b["cells"] = kept
        b["_aux_removal_note"] = (
            f"2026-08-14 移除 {len(polluted)} 个含项目专属辅助项编码（{', '.join(codes)}）"
            "的 cell —— 辅助项编码按项目而异，写死会让预设对其余项目全体失效"
            "（spec k-cycle-…-closure Task 11 / Property 22）"
        )
        changes.append(
            f"REMOVE aux-polluted cells: {wc} | {b.get('sheet')} | "
            f"{len(polluted)} cells | codes={codes}"
        )

    # ── ⑤ Property 24：K8/K9 月度明细补到 12 月 ────────────────────────
    _MONTH_RE = re.compile(r"^(?P<name>.+?)_(?P<m>\d{1,2})月_合计$")
    for b in k_blocks:
        wc = str(b.get("wp_code", ""))
        cells = b.get("cells") or []
        months: dict[int, dict] = {}
        stem = ""
        for c in cells:
            m = _MONTH_RE.match(str(c.get("cell_ref") or ""))
            if m:
                months[int(m.group("m"))] = c
                stem = m.group("name")
        if not months or not stem:
            continue
        missing = [n for n in range(1, 13) if n not in months]
        if not missing:
            continue
        template = months[max(months)]
        tf = str(template.get("formula") or "")
        for n in missing:
            new_cell = {
                "cell_ref": f"{stem}_{n}月_合计",
                "formula": re.sub(r"'\d{1,2}月'", f"'{n}月'", tf),
                "formula_type": template.get("formula_type") or "LEDGER_DETAIL",
                "description": f"{stem} {n} 月发生额（按月度从序时账抽取）",
            }
            cells.append(new_cell)
            changes.append(
                f"ADD month cell: {wc} | {b.get('sheet')} | {new_cell['cell_ref']}"
            )
        b["cells"] = cells

    return changes


#: K8 预设里贴错标签的死块 sheet 名（源 xlsx 无此 tab）
DEAD_K8_ANALYSIS_SHEET = "分析程序K8-3"


def _remove_dead_k8_analysis_block(mappings: list[dict]) -> list[str]:
    """Property 18/23：删除 K8「分析程序K8-3」死块。

    实测（openpyxl 直读 `backend/wp_templates/K/K8 销售费用.xlsx`）：源 xlsx **没有**
    「分析程序K8-3」这个 tab（真名是「调整分录汇总K8-3」与「实质性分析K8-4」）⇒
    该块运行时**永不命中**，已经是死块。它同时还有三处错：

    - ``wp_name='管理费用分析程序'`` —— K8 是**销售费用**（K9 才是管理费用）
    - ``account_codes=['6601','6602','6603']`` —— 跨销售/管理/财务三费，K8 只应 `6601`
    - ``PREV('K8','分析程序K8-3',…)`` —— 自引不存在的 tab

    **为什么删而不是改**：把 sheet 指向源 xlsx 真名「实质性分析K8-4」会与既有同名块
    **撞键**（同 ``(wp_code, sheet)`` 两块，lookup 只取其一 ⇒ 另一块仍是死块）。而它的
    三个 cell 语义已被「实质性分析K8-4」块**完全覆盖**（上年审定数 ≈ 上年发生额、
    本年未审数 ≈ 本年发生额、明细表本期合计逐字相同）⇒ 删除不丢任何取数能力。

    这条推翻了 tasks.md 设计阶段写的「改回销售费用口径」——那时未察觉该 sheet 在源
    xlsx 不存在、且内容已被另一块覆盖。
    """
    changes: list[str] = []
    for i in range(len(mappings) - 1, -1, -1):
        b = mappings[i]
        if str(b.get("wp_code", "")) != "K8":
            continue
        if str(b.get("sheet", "")) != DEAD_K8_ANALYSIS_SHEET:
            continue
        changes.append(
            f"REMOVE dead block: K8 | {DEAD_K8_ANALYSIS_SHEET} | "
            f"wp_name={b.get('wp_name')!r} accounts={b.get('account_codes')} "
            "（源 xlsx 无该 tab ⇒ 永不命中；三个 cell 已被「实质性分析K8-4」覆盖）"
        )
        del mappings[i]
    return changes


def _round_trip_guard(raw: str, data: dict) -> None:
    """Property 25：`json.dumps` 不能逐字复现原文即 exit 2（拒绝写盘）。

    这个文件 429KB / 282 块、被 5 个 spec 共享。若序列化形态与原文不一致，
    一次写盘就会重排整个文件 —— 把并发会话的成果全部卷进 diff，
    后续任何人做 `git diff` 都无法分辨谁改了什么。
    """
    if json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n" == raw:
        return
    print(
        "❌ round-trip 自检失败：json.dumps(indent=2)+换行 无法逐字复现原文。\n"
        "   直接写盘会重排整个文件并卷入并发会话的改动 —— 已拒绝写盘。\n"
        "   请先确认该文件的序列化形态（缩进 / 尾换行 / ensure_ascii）后再改本脚本。",
        file=sys.stderr,
    )
    sys.exit(2)


def _force_utf8_stdout() -> None:
    """把 stdout/stderr 强制成 UTF-8。

    🔴 Windows 控制台默认 GBK，`•` / `✅` / `❌` 这些装饰字符会抛
    ``UnicodeEncodeError`` —— 而它发生在**打印变更清单时、写盘之前**，
    表现为「脚本报错但文件没改」，容易被误读成「改动失败需重试」。
    本脚本会进 CI，故在脚本内自愈而不依赖 `PYTHONIOENCODING` 环境变量。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — 自愈失败也不该阻断主流程
                pass


def main():
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="K 循环公式预设修正幂等脚本")
    parser.add_argument("--apply", action="store_true", help="执行修正并写盘")
    parser.add_argument("--check", action="store_true", help="检查后以 exit code 报告")
    args = parser.parse_args()

    raw = _DATA_PATH.read_text(encoding="utf-8")
    _round_trip_guard(raw, json.loads(raw))
    data = json.loads(raw)
    changes = apply_fixes(data)

    if not changes:
        print("✅ 无需变更（已是最新）")
        sys.exit(0)

    print(f"{'[DRY-RUN] ' if not args.apply else ''}变更清单 ({len(changes)} 项):")
    for c in changes:
        print(f"  • {c}")

    if args.apply:
        _DATA_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n✅ 已写盘: {_DATA_PATH}")
    elif args.check:
        print(f"\n❌ 有 {len(changes)} 项欠账")
        sys.exit(1)
    else:
        print(f"\n⚠️  DRY-RUN 模式，使用 --apply 执行修正")


if __name__ == "__main__":
    main()
