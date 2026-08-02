#!/usr/bin/env python
"""纠正并补齐 E1 货币资金的公式管理预设（幂等）。

**改造前的 5 处缺陷（全部 DB / openpyxl 实证）**

1. 🔴 **取错整个科目族**：`数字货币明细表E1-4` 块 ``account_codes=['1502']`` +
   ``TB('1502',…)``，而 `account_chart` 实证 **`1502` = 持有至到期投资减值准备**。
   数字货币按《企业会计准则解释第 15 号》（财会〔2021〕35 号）是在「货币资金」项下
   **增设二级科目**核算，**没有独立的一级标准科目** —— 写死任何码都是错的
   （活体 `1502` 全库仅 1 行 / 1 个项目，即该项目的持有至到期投资减值准备）。
   → 改 `PLACEHOLDER`，由 render 的语义槽 `digital`（按科目名 `数字货币`/`数字人民币`
   在本项目科目表里定位）动态取数。

2. 🔴 **`applies_when` 是死字段**：该块写 ``applies_when="tb_account_exists:1502"``，
   `notes` 声称「chain_orchestrator 加载 sheet 前检查 tb_balance…无则隐藏整 sheet」。
   全仓 grep 实证：``tb_account_exists`` **只出现在本 JSON 与归档 spec 文档里，无任何
   Python 消费方**；`chain_orchestrator` 的同名字段读的是 ``project_flags`` 里的
   **flag 名**（B60 平台字段机制），与本文件不是一回事。→ 该功能从未实现，字段删除
   并把 `notes` 改成实情（避免下一个人再被误导）。

3. **`sheet` 名与源 xlsx 不一致**（→ prefill 定位不到该 sheet，预设静默失效）：

   ==================  ==========================  ==============================
   块                  改造前 `sheet`              源 xlsx 真实 tab 名
   ==================  ==========================  ==============================
   货币资金审定表      ``审定表E1-1``              ``货币资金审定表E1-1``
   货币资金分析程序    ``分析程序E1-3``            ``货币资金分析表E1-14``
   ==================  ==========================  ==============================

   ``分析程序E1-3`` 是**双重错误**：源 xlsx 里 ``E1-3`` 是「银行存款及其他货币资金
   明细表」，分析表实为 ``货币资金分析表E1-14`` / ``利息收入月度分析E1-15``。
   `PREV('E1','分析程序E1-3','审定数')` 同址改正。

4. **`TB_SUM('1001~1012',…)` 是脆弱写法**：`account_chart` 实证 ``^10(0|1)[0-9]$``
   范围内只有 `1001`/`1002`/`1012`，故当前**等价**于 `BS-002`（不虚增）；但客户若有
   `1003 存放中央银行款项` / `1011 存出保证金`（金融企业科目）就会虚增。
   → 改显式三项相加，与 ``report_config`` 的 ``BS-002`` 公式逐字同构。

5. **两张披露 sheet 零公式预设**（公式管理页对披露表完全空白）→ 新增两块，
   公式依据源 xlsx 逐格可查（上市 ``B8=='货币资金审定表E1-1'!G7`` 等）。

**另补** E1-1 审定表的底稿间 `WP()` 联动（← E1-2 / E1-3 / E1-4）。

**两条硬约束**

- `preset_library.convert_prefill_presets()` 的 ``page_key = f"workpaper:{wp_code}"``
  **忽略 sheet** → 同一 wp_code 内 ``cell_ref`` 必须**全局唯一**，同名互相遮蔽。
  改造前 `审定表E1-1` 与 `分析程序E1-3` 都有 ``上年审定数`` = 已在撞键 → 本脚本给
  分析表块的条目加前缀区分。
- **明细表块禁引 `WP()`** —— E1 取数级联是 E1-2/E1-3/E1-4 → E1-1，明细反引审定表即成环。

**范围外（本脚本不动，见 spec Notes）**

`E0 银行询证函` 块的 ``sheet="审定表E0-1"`` 同样不存在（源 xlsx 真实 tab 是
``函证结果汇总表E0-1``）。E0 函证模块跨 9 个循环共享，改名会让一个长期失效的 prefill
**突然开始写入**共享 sheet，需独立验证 → 留作后续，并由守卫显式锁定现值防静默漂移。

Usage::

    python backend/scripts/fix/fix_e1_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_e1_prefill_presets.py
    python backend/scripts/fix/fix_e1_prefill_presets.py --check

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ R3 (Task 5)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

# ── 源 xlsx 真实 tab 名（openpyxl 实证）────────────────────────────────────
SHEET_ADJ = "货币资金审定表E1-1"
SHEET_CASH_DETAIL = "现金明细表E1-2"
SHEET_BANK_DETAIL = "银行存款及其他货币资金明细表(人民币及外币)E1-3"
SHEET_DIGITAL = "数字货币明细表E1-4"
SHEET_ANALYSIS = "货币资金分析表E1-14"
SHEET_DISC_LISTED = "附注披露信息(上市公司)"
SHEET_DISC_SOE = "附注披露信息(国企)"

#: 旧值 → 新值（sheet 名纠正）
SHEET_RENAMES: dict[str, str] = {
    "审定表E1-1": SHEET_ADJ,
    "分析程序E1-3": SHEET_ANALYSIS,
}

#: `BS-002` 货币资金三项显式相加（替代脆弱区间 `TB_SUM('1001~1012',…)`）
def _bs002(period: str) -> str:
    return (
        f"=TB('1001','{period}') + TB('1002','{period}') + TB('1012','{period}')"
    )


#: 审定表块内被替换的公式（cell_ref → 新公式）
ADJ_FORMULA_FIXES: dict[str, dict[str, str]] = {
    "期初余额": {
        "formula": _bs002("期初余额"),
        "formula_type": "TB",
        "description": (
            "货币资金期初余额合计 = 库存现金 + 银行存款 + 其他货币资金"
            "（与 report_config 的 BS-002 公式逐字同构；原 TB_SUM('1001~1012') "
            "在客户存在 1003/1011 时会虚增）"
        ),
    },
    "未审数": {
        "formula": _bs002("期末余额"),
        "formula_type": "TB",
        "description": (
            "货币资金期末余额合计（未审）= 库存现金 + 银行存款 + 其他货币资金"
            "（对齐 report_config BS-002）"
        ),
    },
}

#: E1-1 审定表新增的底稿间联动（cell_ref 在 workpaper:E1 内全局唯一）
ADJ_NEW_CELLS: list[dict[str, Any]] = [
    {
        "cell_ref": "现金明细表期末合计",
        "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期末余额合计')",
        "formula_type": "WP",
        "description": "库存现金审定未审数来源 = E1-2 现金明细表期末余额合计",
    },
    {
        "cell_ref": "银行及其他货币资金明细表期末合计",
        "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','期末余额合计')",
        "formula_type": "WP",
        "description": (
            "银行存款 + 其他货币资金审定未审数来源 = E1-3 明细表期末余额合计"
            "（E1-3 按银行账户逐户列示，合计应与 TB(1002)+TB(1012) 勾稽）"
        ),
    },
    {
        "cell_ref": "数字货币明细表期末合计",
        "formula": f"=WP('E1','{SHEET_DIGITAL}','期末余额合计')",
        "formula_type": "WP",
        "description": (
            "数字货币审定未审数来源 = E1-4 数字货币明细表期末余额合计"
            "（数字货币无一级标准科目，按科目名在本项目科目表定位，见 e_cycle_specs）"
        ),
    },
    {
        "cell_ref": "本期借方发生额",
        "formula": _bs002("本期借方"),
        "formula_type": "TB",
        "description": "货币资金本期借方发生额合计（收款；供 E1-14 分析与 E1-23 收支检查）",
    },
    {
        "cell_ref": "本期贷方发生额",
        "formula": _bs002("本期贷方"),
        "formula_type": "TB",
        "description": "货币资金本期贷方发生额合计（付款；供 E1-14 分析与 E1-23 收支检查）",
    },
]

#: 数字货币块的整块替换（`1502` 是持有至到期投资减值准备 → 不得引用）
DIGITAL_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "数字货币明细表",
    "sheet": SHEET_DIGITAL,
    # 🔴 故意留空：数字货币按准则解释 15 号是货币资金项下**增设二级科目**，
    # 无独立一级标准科目。科目由 render 的语义槽 `digital` 按科目名逐项目定位。
    "account_codes": [],
    "cells": [
        {
            "cell_ref": "数字货币期末合计",
            "formula": "=PLACEHOLDER('数字货币期末余额合计')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "数字货币期末余额合计 —— 无独立一级标准科目（准则解释15号：在「货币资金」"
                "项下增设二级科目核算），故不写死科目码；由 render 语义槽 `digital` "
                "按科目名（数字货币/数字人民币）在**本项目**科目表里定位后下发。"
                "本项目无该科目时前端显示「本项目无此科目」而非 0。"
            ),
        },
        {
            "cell_ref": "数字货币期初合计",
            "formula": "=PLACEHOLDER('数字货币期初余额合计')",
            "formula_type": "PLACEHOLDER",
            "description": "数字货币期初余额合计（同上，语义槽动态定位）",
        },
    ],
    "notes": (
        "改造前本块引用 TB('1502')，而 1502 实为「持有至到期投资减值准备」= 取错整个"
        "科目族（活体全库仅 1 行 / 1 项目）。原 applies_when='tb_account_exists:1502' "
        "已删除 —— 全仓 grep 实证该形态无任何 Python 消费方（chain_orchestrator 的同名"
        "字段读的是 project_flags 里的 flag 名，属 B60 平台字段机制），所谓「无 1502 则"
        "隐藏整 sheet」从未实现。明细行 R10-R16 由用户逐项录入；R17 合计行是 SUM 公式，"
        "由 _is_formula_cell 守护跳过。"
    ),
}

#: 上市披露表块 —— 公式依据源 xlsx「附注披露信息(上市公司)」逐格
DISC_LISTED_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "附注披露信息(上市公司)",
    "sheet": SHEET_DISC_LISTED,
    "account_codes": ["1001", "1002", "1012"],
    "cells": [
        {
            "cell_ref": "披露上市_库存现金_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','库存现金_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B8 = '货币资金审定表E1-1'!G7（库存现金审定数）",
        },
        {
            "cell_ref": "披露上市_库存现金_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','库存现金_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C8 = '货币资金审定表E1-1'!D7",
        },
        {
            "cell_ref": "披露上市_银行存款_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','银行存款_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B9 = '货币资金审定表E1-1'!G10",
        },
        {
            "cell_ref": "披露上市_银行存款_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','银行存款_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C9 = '货币资金审定表E1-1'!D10",
        },
        {
            "cell_ref": "披露上市_存放财务公司款项_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','存放财务公司款项_审定数')",
            "formula_type": "WP",
            "description": (
                "源 xlsx B10 = '货币资金审定表E1-1'!G9。按准则解释15号「可在货币资金"
                "项目之下增设『其中：存放财务公司款项』单独列示」→ 无独立一级标准科目，"
                "由 render 语义槽 `finance_co` 按科目名定位"
            ),
        },
        {
            "cell_ref": "披露上市_其他货币资金_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','其他货币资金_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B11 = '货币资金审定表E1-1'!G11",
        },
        {
            "cell_ref": "披露上市_其他货币资金_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','其他货币资金_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C11 = '货币资金审定表E1-1'!D11",
        },
        {
            "cell_ref": "披露上市_存款应计利息_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','存款应计利息_审定数')",
            "formula_type": "WP",
            "description": (
                "源 xlsx B12 = G14+G15+G16（审定表应计利息三行之和）。"
                "按源模板提示：应计利息指按实际利率法计提、尚未到付息期的部分，"
                "不含逾期未收利息（列示于「应收利息」），且不属现金及现金等价物"
            ),
        },
        {
            "cell_ref": "披露上市_合计_期末",
            "formula": "=PLACEHOLDER('货币资金披露合计（表内 SUM，勿覆盖）')",
            "formula_type": "PLACEHOLDER",
            "description": "源 xlsx B14 = SUM(B8:B13) —— 表内合计公式，不由 prefill 写入",
        },
        {
            "cell_ref": "披露上市_原币表勾稽差异",
            "formula": "=PLACEHOLDER('主表合计 − 原币表人民币合计（应为 0）')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "源 xlsx B16 = B14 − D62 —— 这是**勾稽校验行**不是披露行，"
                "由披露表勾稽面板计算，不推送到附注"
            ),
        },
    ],
    "notes": (
        "改造前两张披露 sheet 零预设（公式管理页空白）。主表各行取自 E1-1 审定数，"
        "与源 xlsx 的跨 sheet 引用逐格对应。外币两表（R25 外币性货币项目 / R35 原币表）"
        "取自 E1-2 / E1-3 的币种维度，其 SUMIF 形态无法用 prefill 词汇表达 → 由前端"
        "披露表按币种枚举聚合，不在此处预设。"
    ),
}

#: 国企披露表块 —— 公式依据源 xlsx「附注披露信息(国企)」逐格
DISC_SOE_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "附注披露信息(国企)",
    "sheet": SHEET_DISC_SOE,
    "account_codes": ["1001", "1002", "1012"],
    "cells": [
        {
            "cell_ref": "披露国企_现金_期末",
            "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期末余额合计')",
            "formula_type": "WP",
            "description": "源 xlsx B8 = '现金明细表E1-2'!G22（国企版首行字面是「现金」）",
        },
        {
            "cell_ref": "披露国企_现金_期初",
            "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期初余额合计')",
            "formula_type": "WP",
            "description": "源 xlsx C8 = '现金明细表E1-2'!B22",
        },
        {
            "cell_ref": "披露国企_银行存款_期末",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','银行存款期末合计')",
            "formula_type": "WP",
            "description": "源 xlsx B9 = E1-3!AB42 + AB43",
        },
        {
            "cell_ref": "披露国企_银行存款_期初",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','银行存款期初合计')",
            "formula_type": "WP",
            "description": "源 xlsx C9 = E1-3!G43 + G42",
        },
        {
            "cell_ref": "披露国企_其他货币资金_期末",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','其他货币资金期末合计')",
            "formula_type": "WP",
            "description": "源 xlsx B10 = E1-3!AB44",
        },
        {
            "cell_ref": "披露国企_其他货币资金_期初",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','其他货币资金期初合计')",
            "formula_type": "WP",
            "description": "源 xlsx C10 = E1-3!G44",
        },
        {
            "cell_ref": "披露国企_受限资金_期末合计",
            "formula": "=PLACEHOLDER('受限制货币资金期末合计（按受限类别动态归集）')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "源 xlsx「受限制的货币资金明细」B23 合计。各类别行由 render 的 "
                "restricted_prefill 按**叶子科目名**动态分类归集（客户命名千差万别，"
                "无法写死科目码）；未命中的叶子进「待归类」面板交审计师点选。"
                "校验预设 F1-5：②表合计.期末 = 报表货币资金期末 − 补充资料③表"
                "「期末现金及现金等价物余额」"
            ),
        },
    ],
    "notes": (
        "国企版主表首行字面是「现金」（非「库存现金」），列头是「期末余额 / 年初余额」"
        "（非「期末数 / 期初数」）—— 与上市版不同，见源 xlsx R7/R8。"
        "受限制货币资金明细表的类别行走动态分类，见 four_table/e1_restricted_buckets.py。"
    ),
}

#: 分析表块的 cell_ref 前缀纠正（原 `上年审定数` 与审定表块撞 page_key）
ANALYSIS_CELL_RENAMES: dict[str, str] = {
    "上年审定数": "分析表上年审定数",
    "本年未审数": "分析表本年未审数",
}


# ─────────────────────────── 计划构建 ───────────────────────────


def _blocks(data: dict) -> list[dict]:
    return data["mappings"]


def _find(blocks: list[dict], wp_code: str, sheet: str) -> dict | None:
    for b in blocks:
        if b.get("wp_code") == wp_code and b.get("sheet") == sheet:
            return b
    return None


def build_plan(data: dict) -> list[str]:
    """就地修改 ``data``，返回变更描述列表（空 = 已对齐）。"""
    changes: list[str] = []
    blocks = _blocks(data)

    # ① sheet 名纠正（block.sheet 与公式内的 sheet 实参**都要改**）
    for old, new in SHEET_RENAMES.items():
        blk = _find(blocks, "E1", old)
        if blk is not None:
            blk["sheet"] = new
            changes.append(f"sheet 纠正: {old!r} → {new!r}")
    # 公式实参里的旧 sheet 名（`PREV('E1','审定表E1-1',…)` / `WP('E1','分析程序E1-3',…)`）
    for b in blocks:
        if b.get("wp_code") != "E1":
            continue
        for c in b.get("cells", []):
            f = c.get("formula") or ""
            for old, new in SHEET_RENAMES.items():
                if f"'{old}'" in f:
                    c["formula"] = f.replace(f"'{old}'", f"'{new}'")
                    f = c["formula"]
                    changes.append(
                        f"{b.get('sheet')}: {c.get('cell_ref')!r} 公式内 sheet 实参 "
                        f"{old!r} → {new!r}（源 xlsx 无该 tab，原公式定位落空）"
                    )

    # ② 审定表块：公式替换 + 新增联动
    adj = _find(blocks, "E1", SHEET_ADJ)
    if adj is not None:
        cells = adj.setdefault("cells", [])
        by_ref = {c.get("cell_ref"): c for c in cells}
        for ref, patch in ADJ_FORMULA_FIXES.items():
            cur = by_ref.get(ref)
            if cur is not None and cur.get("formula") != patch["formula"]:
                cur.update(patch)
                changes.append(f"{SHEET_ADJ}: {ref} 公式改为显式 BS-002 三项相加")
        for cell in ADJ_NEW_CELLS:
            if cell["cell_ref"] not in by_ref:
                cells.append(json.loads(json.dumps(cell, ensure_ascii=False)))
                changes.append(f"{SHEET_ADJ}: 新增 {cell['cell_ref']}")

    # ③ 分析表块：cell_ref 去撞键 + 公式口径
    ana = _find(blocks, "E1", SHEET_ANALYSIS)
    if ana is not None:
        for cell in ana.get("cells", []):
            ref = cell.get("cell_ref")
            if ref in ANALYSIS_CELL_RENAMES:
                cell["cell_ref"] = ANALYSIS_CELL_RENAMES[ref]
                changes.append(
                    f"{SHEET_ANALYSIS}: cell_ref {ref!r} → "
                    f"{ANALYSIS_CELL_RENAMES[ref]!r}（page_key 忽略 sheet，需全局唯一）"
                )
            f = cell.get("formula") or ""
            if "TB_SUM('1001~1012'" in f:
                period = "期末余额" if "期末余额" in f else "期初余额"
                cell["formula"] = _bs002(period)
                cell["formula_type"] = "TB"
                changes.append(f"{SHEET_ANALYSIS}: TB_SUM 区间改显式 BS-002 三项相加")

    # ④ 数字货币块整块替换（1502 → PLACEHOLDER + 删死字段）
    dig = _find(blocks, "E1", SHEET_DIGITAL)
    if dig is not None:
        target = json.loads(json.dumps(DIGITAL_BLOCK, ensure_ascii=False))
        if dig != target:
            idx = blocks.index(dig)
            blocks[idx] = target
            changes.append(
                f"{SHEET_DIGITAL}: 整块替换 —— 1502（持有至到期投资减值准备）→ "
                "PLACEHOLDER + 删除死字段 applies_when"
            )

    # ⑤ 两张披露 sheet 新增块
    for blk in (DISC_LISTED_BLOCK, DISC_SOE_BLOCK):
        existing = _find(blocks, "E1", blk["sheet"])
        target = json.loads(json.dumps(blk, ensure_ascii=False))
        if existing is None:
            blocks.append(target)
            changes.append(f"新增披露块: {blk['sheet']}")
        elif existing != target:
            blocks[blocks.index(existing)] = target
            changes.append(f"更新披露块: {blk['sheet']}")

    return changes


def _semantic_blob(block: dict) -> str:
    """只取**语义字段**（公式 + 科目码 + 结构字段）拼串供断言。

    🔴 不能对整块 ``json.dumps`` 做「不得出现 xxx」类断言 —— ``description`` / ``notes``
    里会**如实写出被纠正的反例**（如「原 TB_SUM('1001~1012') 在…会虚增」、
    「改造前本块引用 TB('1502')」），整块扫描会把说明文字数成真实引用而误报。
    同 `stripComments()` 一类的坑，平台已多次踩中。
    """
    parts: list[str] = [json.dumps(block.get("account_codes") or [], ensure_ascii=False)]
    for k in ("applies_when",):
        if k in block:
            parts.append(f"{k}={block[k]!r}")
    for c in block.get("cells", []):
        parts.append(str(c.get("formula") or ""))
        parts.append(str(c.get("formula_type") or ""))
    return "\n".join(parts)


def validate(data: dict) -> list[str]:
    """返回欠账列表（空 = 已对齐）。"""
    problems: list[str] = []
    blocks = _blocks(data)
    e1 = [b for b in blocks if b.get("wp_code") == "E1"]

    # 反向自检：确实取到了 E1 块，且语义串非空（否则下面全是空转）
    if not e1:
        problems.append("未找到任何 wp_code=E1 的块（定位失效，断言会空转）")
    elif not any(_semantic_blob(b).strip() for b in e1):
        problems.append("E1 块的语义字段全空（_semantic_blob 抽取失效）")

    # 不得残留错误 sheet 名 —— block.sheet 与**公式实参**两处都查
    for bad in SHEET_RENAMES:
        if any(b.get("sheet") == bad for b in e1):
            problems.append(f"残留错误 sheet 名 {bad!r}（block.sheet）")
        for b in e1:
            for c in b.get("cells", []):
                if f"'{bad}'" in (c.get("formula") or ""):
                    problems.append(
                        f"块 {b.get('sheet')!r} 的 {c.get('cell_ref')!r} 公式仍引用"
                        f"不存在的 sheet {bad!r}"
                    )

    for b in e1:
        blob = _semantic_blob(b)
        if "1502" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍引用 1502（持有至到期投资减值准备）")
        if "tb_account_exists" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍带死字段 applies_when/tb_account_exists")
        if "TB_SUM('1001~1012'" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍用脆弱区间 TB_SUM('1001~1012')")

    # cell_ref 在 workpaper:E1 内全局唯一（page_key 忽略 sheet）
    seen: dict[str, str] = {}
    for b in e1:
        for c in b.get("cells", []):
            ref = c.get("cell_ref")
            if ref in seen:
                problems.append(
                    f"cell_ref 撞键 {ref!r}（{seen[ref]!r} 与 {b.get('sheet')!r}）"
                    " —— page_key 忽略 sheet，同名会互相遮蔽"
                )
            else:
                seen[ref] = b.get("sheet") or ""

    # 披露块存在
    for sheet in (SHEET_DISC_LISTED, SHEET_DISC_SOE):
        if not any(b.get("sheet") == sheet for b in e1):
            problems.append(f"缺披露块 {sheet!r}")

    # 明细块禁 WP()（防成环）
    detail_sheets = {SHEET_CASH_DETAIL, SHEET_BANK_DETAIL, SHEET_DIGITAL}
    for b in e1:
        if b.get("sheet") in detail_sheets:
            for c in b.get("cells", []):
                if "WP(" in (c.get("formula") or ""):
                    problems.append(
                        f"明细块 {b.get('sheet')!r} 的 {c.get('cell_ref')!r} 引用了 WP() "
                        "—— 会与 E1-1 审定表成环"
                    )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写盘")
    ap.add_argument("--check", action="store_true", help="只校验，返回欠账数")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    if args.check:
        problems = validate(data)
        for p in problems:
            print(f"  [欠账] {p}")
        print(f"--check: {len(problems)} 项欠账")
        return 1 if problems else 0

    changes = build_plan(data)
    if not changes:
        print("已对齐，无需变更（0 项）")
        return 0
    for c in changes:
        print(f"  [变更] {c}")
    print(f"共 {len(changes)} 项变更")

    if args.dry_run:
        print("--dry-run：未写盘")
        return 0

    problems = validate(data)
    if problems:
        for p in problems:
            print(f"  [校验失败] {p}")
        print("校验未通过，拒绝写盘")
        return 1

    MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {MAPPING_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
