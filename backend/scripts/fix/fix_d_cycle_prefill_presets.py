"""D 循环公式预设 sheet 名与口径纠偏 + 明细块补齐（幂等）—— spec Task 18 + 19。

用法::

    python backend/scripts/fix/fix_d_cycle_prefill_presets.py            # dry-run
    python backend/scripts/fix/fix_d_cycle_prefill_presets.py --check    # 欠账即非零退出
    python backend/scripts/fix/fix_d_cycle_prefill_presets.py --apply

🔴 **本脚本 2026-08-06 重建** —— Task 18/19 曾被标 `[x]` 但实证为假绿：脚本文件在磁盘上
不存在，4 处旧 sheet 名与 6 个缺失明细块在 **HEAD 与工作树都仍是旧状态**（HEAD 的 D 类
块 = 23 个）。属平台已登记的「并发会话互相回退同一文件」范式。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task 18：sheet 名与口径纠偏
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**(a) 4 处 sheet 名贴错标签**（源 xlsx `wb.sheetnames` 直读实证，旧名根本不存在）::

    审定表D0-1   → 函证结果汇总表D0-1
    函证汇总表D0-2 → 核实被函证单位信息D0-2
    分析程序D0-3  → 跟函函证过程控制D0-3
    分析程序D4-3  → 其他业务收入明细表D4-3

`sheet` 是运行时匹配键 ⇒ 贴错 = 该块永不命中、公式管理页空白，且**任何语法校验都不报错**。

**(b) D4 审定表「期初余额」与「未审数」公式逐字相同**（都是
`TB_SUM('6001~6099','本期发生额')`）—— 损益类**无期初余额**概念，上年数只能走
`PREV()`。改为 `PREV('D4','营业收入审定表D4-1','审定数')`。

**(c) D5 引用 `1124` 的公式改 `PLACEHOLDER`** —— 该码在活体 `account_chart` 两个 source
零命中、`account_mapping` 零反解、`tb_balance` 零数据行。原块 `_note` 已如实写明「求值
结果预期恒为 0」，但**留着 `TB('1124',…)` 会让公式管理页显示一个恒空的公式**，比
PLACEHOLDER + 实证说明更差（后者能告诉审计师「为什么空」）。

**(d) D2-3 坏账准备明细表两处口径错（本轮新发现，spec 未列）**::

    LEDGER('6602','credit'/'debit','全年')  description 写「信用减值损失」
      → 🔴 6602 是**管理费用**（account_chart 20 项目 x 2 source 零分歧实证）；
        应收款项减值走**信用减值损失 6702**（6701 = 资产减值损失）。改 6702。

    LEDGER('1231','credit','全年')  「本期核销」
      → 🔴 双重问题：① `_resolve_ledger_formula` 是 `account_code == args[0]`
        **精确等于**、非前缀匹配，而 `tb_ledger.account_code` 是**原始码（点号体系）**
        ⇒ 客户在 `1231.02` 记账时该式恒 0；② 若真在 `1231` 父级记账，则把 D1/D6/K1
        等全部循环的坏账准备核销一并算进 D2。标准码 `1231-02`（横杠）在点号体系的
        `tb_ledger` 同样命中不了 ⇒ 无法用单条公式表达，改 `PLACEHOLDER`。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task 19：明细块补齐 + 审定表 `WP()` 联动
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

新增 6 个明细块（sheet 名逐字取源 xlsx）：D3-2 / D5-2 / D5-4 / D6-2 / D6-3 / D7-2。

审定表补 `WP()` 引用本循环明细表（D1 已有作范式）；**明细表块禁反向引用审定表**
（防成环，守卫 `test_wp_references_are_acyclic` 钉死）。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 5.1~5.6, 5.8, 5.9 / Task 18, 19
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
MAPPING_PATH = BACKEND / "data" / "prefill_formula_mapping.json"

# ── Task 18(a) sheet 名纠偏（旧名 → 源 xlsx 真实 tab 名）────────────────────────
SHEET_RENAMES: dict[tuple[str, str], str] = {
    ("D0", "审定表D0-1"): "函证结果汇总表D0-1",
    ("D0", "函证汇总表D0-2"): "核实被函证单位信息D0-2",
    ("D0", "分析程序D0-3"): "跟函函证过程控制D0-3",
    ("D4", "分析程序D4-3"): "其他业务收入明细表D4-3",
}

# ── Task 19 明细表 sheet 名（源 xlsx 逐字）──────────────────────────────────────
SHEET_D3_DETAIL = "预收账款明细表D3-2"
SHEET_D5_DETAIL = "应收款项融资明细表D5-2"
SHEET_D5_FV = "应收款项融资公允价值测算表D5-4"
SHEET_D6_DETAIL = "明细表D6-2"
SHEET_D6_IMPAIR = "合同资产减值准备明细表D6-3"
SHEET_D7_DETAIL = "明细表D7-2"
SHEET_D2_DETAIL = "明细表D2-2"
SHEET_D2_IMPAIR = "坏账准备明细表D2-3"

D5_PLACEHOLDER_REASON = (
    "应收款项融资（1124）在活体 account_chart 两个 source 零命中、account_mapping 零反解、"
    "tb_balance 零数据行 —— 本平台在册项目无此业务，属业务事实而非错码。"
    "审计师可在公式管理面板按本项目实际科目改写（Tier A 可编辑覆盖优先于预设）。"
)

D2_WRITEOFF_REASON = (
    "本期核销无法用单条 LEDGER() 表达：_resolve_ledger_formula 是 account_code 精确等于、"
    "非前缀匹配，而 tb_ledger.account_code 是客户原始码（点号体系），标准码 1231-02（横杠）"
    "命中不了；若退回父码 1231 则把 D1/D6/K1 等循环的坏账核销一并算进 D2。"
    "取数真源 = D2-3 明细表逐行录入或四表叶子聚合。"
)


def _cell(ref: str, formula: str, ftype: str, desc: str) -> dict[str, Any]:
    return {
        "cell_ref": ref,
        "formula": formula,
        "formula_type": ftype,
        "description": desc,
    }


# ── Task 19：应新增的明细块 ─────────────────────────────────────────────────────
def build_detail_blocks() -> list[dict[str, Any]]:
    """六个明细块。明细块**禁**反向引用审定表（防成环）。"""
    return [
        {
            "wp_code": "D3",
            "wp_name": "预收账款明细表",
            "sheet": SHEET_D3_DETAIL,
            "sheet_name": SHEET_D3_DETAIL,
            "account_codes": ["2203"],
            "cells": [
                _cell(
                    "期初合计",
                    "=TB('2203','期初余额')",
                    "TB",
                    "预收款项期初余额（负债贷方口径）。按往来单位/性质的分行由四表叶子子科目"
                    "归集（实证客户有 2203.01 预收货款 / 2203.02 预收项目款），非单条公式可表达",
                ),
                _cell(
                    "期末合计",
                    "=TB('2203','期末余额')",
                    "TB",
                    "预收款项期末余额（未审）。勾稽：本表期末合计 = 审定表D3-1 未审数",
                ),
                _cell(
                    "上年期末合计",
                    f"=PREV('D3','{SHEET_D3_DETAIL}','期末合计')",
                    "PREV",
                    "上年同底稿期末合计",
                ),
            ],
        },
        {
            "wp_code": "D5",
            "wp_name": "应收款项融资明细表",
            "sheet": SHEET_D5_DETAIL,
            "sheet_name": SHEET_D5_DETAIL,
            "account_codes": ["1124"],
            "cells": [
                _cell(
                    "期末合计",
                    "=PLACEHOLDER()",
                    "PLACEHOLDER",
                    f"应收款项融资明细表期末合计。{D5_PLACEHOLDER_REASON}",
                ),
                _cell(
                    "上年期末合计",
                    f"=PREV('D5','{SHEET_D5_DETAIL}','期末合计')",
                    "PREV",
                    "上年同底稿期末合计",
                ),
            ],
        },
        {
            "wp_code": "D5",
            "wp_name": "应收款项融资公允价值测算表",
            "sheet": SHEET_D5_FV,
            "sheet_name": SHEET_D5_FV,
            "account_codes": ["1124"],
            "cells": [
                _cell(
                    "公允价值合计",
                    "=PLACEHOLDER()",
                    "PLACEHOLDER",
                    "应收款项融资公允价值合计（FVOCI 计量）。"
                    f"{D5_PLACEHOLDER_REASON} 公允价值本身属估值判断，四表无对应字段。",
                ),
                _cell(
                    "上年公允价值合计",
                    f"=PREV('D5','{SHEET_D5_FV}','公允价值合计')",
                    "PREV",
                    "上年同底稿公允价值合计",
                ),
            ],
        },
        {
            "wp_code": "D6",
            "wp_name": "合同资产明细表",
            "sheet": SHEET_D6_DETAIL,
            "sheet_name": SHEET_D6_DETAIL,
            "account_codes": ["1141"],
            "cells": [
                _cell(
                    "期初合计",
                    "=TB('1141','期初余额')",
                    "TB",
                    "合同资产原值期初余额（BS-011）",
                ),
                _cell(
                    "期末合计",
                    "=TB('1141','期末余额')",
                    "TB",
                    "合同资产原值期末余额（未审）。勾稽：本表期末合计 = 审定表D6-1 区块一原值小计",
                ),
                _cell(
                    "上年期末合计",
                    f"=PREV('D6','{SHEET_D6_DETAIL}','期末合计')",
                    "PREV",
                    "上年同底稿期末合计",
                ),
            ],
        },
        {
            "wp_code": "D6",
            "wp_name": "合同资产减值准备明细表",
            "sheet": SHEET_D6_IMPAIR,
            "sheet_name": SHEET_D6_IMPAIR,
            "account_codes": ["1142"],
            "cells": [
                _cell(
                    "期初合计",
                    "=TB('1142','期初余额')",
                    "TB",
                    "合同资产减值准备期初余额。🔴 IMP-004 的 formula 四准则**全 NULL** ⇒ "
                    "报表行解析必失败、只能走兜底码；后端另声明第二候选 1231-05（standard 表 "
                    "10 项目有定义但零数据），故本式可能恒空 —— 属业务事实",
                ),
                _cell(
                    "期末合计",
                    "=TB('1142','期末余额')",
                    "TB",
                    "合同资产减值准备期末余额（未审）。勾稽：= 审定表D6-1 区块二坏账小计",
                ),
                _cell(
                    "上年期末合计",
                    f"=PREV('D6','{SHEET_D6_IMPAIR}','期末合计')",
                    "PREV",
                    "上年同底稿期末合计",
                ),
            ],
        },
        {
            "wp_code": "D7",
            "wp_name": "合同负债明细表",
            "sheet": SHEET_D7_DETAIL,
            "sheet_name": SHEET_D7_DETAIL,
            "account_codes": ["2205"],
            "cells": [
                _cell(
                    "期初合计",
                    "=TB('2205','期初余额')",
                    "TB",
                    "合同负债期初余额（BS-047，负债贷方口径）",
                ),
                _cell(
                    "期末合计",
                    "=TB('2205','期末余额')",
                    "TB",
                    "合同负债期末余额（未审）。🔴 唯一有活体数据的项目用 client 码 2204，"
                    "account_mapping 的 2205←2204 auto_exact 反解使其能命中",
                ),
                _cell(
                    "上年期末合计",
                    f"=PREV('D7','{SHEET_D7_DETAIL}','期末合计')",
                    "PREV",
                    "上年同底稿期末合计",
                ),
            ],
        },
    ]


# ── Task 19：审定表应补的 WP() cells（key = (wp_code, 审定表 sheet)）───────────
ADJUDICATION_WP_CELLS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("D2", "审定表D2-1"): [
        _cell(
            "明细表D2-2期末合计",
            f"=WP('D2','{SHEET_D2_DETAIL}','期末合计')",
            "WP",
            "审定表原值行 ← D2-2 明细表期末合计（按信用风险组合方式 SUMIF 聚合）",
        ),
        _cell(
            "坏账准备期末合计",
            f"=WP('D2','{SHEET_D2_IMPAIR}','坏账准备期末余额')",
            "WP",
            "审定表坏账准备行 ← D2-3 坏账准备明细表期末余额",
        ),
    ],
    ("D3", "审定表D3-1"): [
        _cell(
            "明细表D3-2期末合计",
            f"=WP('D3','{SHEET_D3_DETAIL}','期末合计')",
            "WP",
            "审定表 ← D3-2 预收账款明细表期末合计",
        ),
    ],
    ("D6", "审定表D6-1"): [
        _cell(
            "明细表D6-2期末合计",
            f"=WP('D6','{SHEET_D6_DETAIL}','期末合计')",
            "WP",
            "审定表区块一原值小计 ← D6-2 明细表期末合计",
        ),
        _cell(
            "减值准备明细表D6-3期末合计",
            f"=WP('D6','{SHEET_D6_IMPAIR}','期末合计')",
            "WP",
            "审定表区块二坏账小计 ← D6-3 减值准备明细表期末合计",
        ),
    ],
    ("D7", "审定表D7-1"): [
        _cell(
            "明细表D7-2期末合计",
            f"=WP('D7','{SHEET_D7_DETAIL}','期末合计')",
            "WP",
            "审定表 ← D7-2 明细表期末合计（按性质/账龄聚合）",
        ),
    ],
}


# ── Task 18(b)(c)(d) 单元格级改写：(wp, sheet, cell_ref) → 新字段 ───────────────
def cell_patches() -> dict[tuple[str, str, str], dict[str, str]]:
    """注意 key 里的 sheet 用**纠偏后**的名字（rename 先执行）。"""
    return {
        # (b) D4 损益类无期初余额
        ("D4", "营业收入审定表D4-1", "期初余额"): {
            "formula": "=PREV('D4','营业收入审定表D4-1','审定数')",
            "formula_type": "PREV",
            "description": (
                "上年营业收入审定数（损益类**无期初余额**概念，上年数只能走 PREV）。"
                "🔴 改造前本格与「未审数」公式逐字相同（都是 TB_SUM('6001~6099','本期发生额')）"
            ),
        },
        # (c) D5 审定表四格改 PLACEHOLDER
        ("D5", "审定表D5", "期初余额"): {
            "formula": "=PLACEHOLDER()",
            "formula_type": "PLACEHOLDER",
            "description": f"应收款项融资审定表期初余额。{D5_PLACEHOLDER_REASON}",
        },
        ("D5", "审定表D5", "未审数"): {
            "formula": "=PLACEHOLDER()",
            "formula_type": "PLACEHOLDER",
            "description": f"应收款项融资审定表期末余额（未审）。{D5_PLACEHOLDER_REASON}",
        },
        ("D5", "审定表D5", "AJE调整"): {
            "formula": "=PLACEHOLDER()",
            "formula_type": "PLACEHOLDER",
            "description": f"应收款项融资审计调整分录净额。{D5_PLACEHOLDER_REASON}",
        },
        ("D5", "审定表D5", "RJE调整"): {
            "formula": "=PLACEHOLDER()",
            "formula_type": "PLACEHOLDER",
            "description": f"应收款项融资重分类调整分录净额。{D5_PLACEHOLDER_REASON}",
        },
        # (d) D2-3 两处口径错
        ("D2", SHEET_D2_IMPAIR, "本期计提"): {
            "formula": "=LEDGER('6702','credit','全年')",
            "formula_type": "LEDGER",
            "description": (
                "从序时账取**信用减值损失（6702）**贷方发生额（本期计提坏账准备）。"
                "🔴 改造前写 6602 —— 那是**管理费用**（account_chart 20 项目 x 2 source "
                "零分歧实证）；应收款项减值按金融工具准则走信用减值损失 6702"
            ),
        },
        ("D2", SHEET_D2_IMPAIR, "本期转回"): {
            "formula": "=LEDGER('6702','debit','全年')",
            "formula_type": "LEDGER",
            "description": (
                "从序时账取**信用减值损失（6702）**借方发生额（本期转回坏账准备）。"
                "🔴 改造前写 6602（管理费用），同「本期计提」"
            ),
        },
        ("D2", SHEET_D2_IMPAIR, "本期核销"): {
            "formula": "=PLACEHOLDER()",
            "formula_type": "PLACEHOLDER",
            "description": f"本期核销坏账准备。{D2_WRITEOFF_REASON}",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════


def _key(b: dict[str, Any]) -> tuple[str, str]:
    return str(b.get("wp_code") or ""), str(b.get("sheet") or "")


def plan(mappings: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """返回四类欠账。纯函数，不改入参。"""
    keys = {_key(b) for b in mappings}
    by_key = {_key(b): b for b in mappings}

    renames = [(k, new) for k, new in SHEET_RENAMES.items() if k in keys]

    add_blocks = [b for b in build_detail_blocks() if _key(b) not in keys]

    add_cells: list[tuple[tuple[str, str], list[dict]]] = []
    for k, cells in ADJUDICATION_WP_CELLS.items():
        cur = by_key.get(k)
        if cur is None:
            continue
        have = {str(c.get("cell_ref")) for c in (cur.get("cells") or [])}
        missing = [c for c in cells if str(c["cell_ref"]) not in have]
        if missing:
            add_cells.append((k, missing))

    patches: list[tuple[tuple[str, str, str], dict[str, str]]] = []
    for (wp, sheet, ref), new in cell_patches().items():
        cur = by_key.get((wp, sheet))
        if cur is None:
            continue
        for c in cur.get("cells") or []:
            if str(c.get("cell_ref")) != ref:
                continue
            if str(c.get("formula")) != new["formula"]:
                patches.append(((wp, sheet, ref), new))
            break

    # 公式实参里残留的旧 sheet 名（与「改块名」是同一笔错误的两处出现；
    # 只算块名会让 --check 假绿）
    stale_args: list[str] = []
    for b in mappings:
        for c in b.get("cells") or []:
            f = str(c.get("formula") or "")
            for (rn_wp, rn_old) in SHEET_RENAMES:
                if f"'{rn_wp}','{rn_old}'" in f or f"'{rn_wp}', '{rn_old}'" in f:
                    stale_args.append(
                        f"{b.get('wp_code')} {b.get('sheet')!r} [{c.get('cell_ref')}]: {f}"
                    )

    return {
        "renames": renames,
        "stale_args": stale_args,
        "add_blocks": add_blocks,
        "add_cells": add_cells,
        "patches": patches,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    mappings: list[dict[str, Any]] = data["mappings"]

    round_trip = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    rt_ok = round_trip == raw
    if not rt_ok and args.apply:
        print("[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文，拒绝写回")
        print(f"      原文 {len(raw)} / 复现 {len(round_trip)} 字节")
        return 2

    p = plan(mappings)
    debt = (
        len(p["renames"])
        + len(p["stale_args"])
        + len(p["add_blocks"])
        + sum(len(c) for _, c in p["add_cells"])
        + len(p["patches"])
    )

    print(f"[INFO] mappings 总块数 = {len(mappings)}")
    print(f"[INFO] Task 18(a) sheet 名待纠偏 = {len(p['renames'])}")
    for (wp, old), new in p["renames"]:
        print(f"       ~ {wp}  {old!r} -> {new!r}")
    print(f"[INFO] Task 18(a) 公式实参残留旧 sheet 名 = {len(p['stale_args'])}")
    for s in p["stale_args"]:
        print(f"       ~ {s}")
    print(f"[INFO] Task 18(b)(c)(d) 单元格待改写 = {len(p['patches'])}")
    for (wp, sheet, ref), new in p["patches"]:
        print(f"       ~ {wp}  {sheet!r} [{ref}] -> {new['formula']}")
    print(f"[INFO] Task 19 明细块待新增 = {len(p['add_blocks'])}")
    for b in p["add_blocks"]:
        print(f"       + {b['wp_code']}  {b['sheet']!r}  cells={len(b['cells'])}")
    print(f"[INFO] Task 19 审定表 WP() 待补 = {sum(len(c) for _, c in p['add_cells'])}")
    for (wp, sheet), cells in p["add_cells"]:
        print(f"       + {wp}  {sheet!r}  {[str(c['cell_ref']) for c in cells]}")
    print(f"[INFO] round-trip 自检 = {'OK' if rt_ok else 'DIFF（只影响 --apply）'}")

    if args.check:
        print(f"[CHECK] 欠账 {debt} 项")
        return 1 if debt else 0

    if not args.apply:
        print("[DRY-RUN] 未写回（加 --apply 生效）")
        return 0
    if debt == 0:
        print("[OK] 无欠账，文件未改动")
        return 0

    # 1) rename（先做 —— 后续 patch 的 key 用新名）
    for b in mappings:
        k = _key(b)
        new = SHEET_RENAMES.get(k)
        if new:
            b["sheet"] = new
            if "sheet_name" in b:
                b["sheet_name"] = new
            b["_sheet_rename_note"] = (
                f"sheet 名于 2026-08-06 由 {k[1]!r} 纠正为源 xlsx 真实 tab 名 "
                f"{new!r}（旧名在源模板中不存在 ⇒ 该块此前永不命中）"
            )

    # 1b) 🔴 公式**实参**里的旧 sheet 名也要改 —— 与「改块名」是同一笔错误的两处出现。
    #     只改块的 `sheet` 会留下 PREV('D0','审定表D0-1',…) 指向不存在的 tab
    #     （守卫 test_prev_targets_are_real_sheets 正是这么抓出来的）。
    for b in mappings:
        for c in b.get("cells") or []:
            f = str(c.get("formula") or "")
            if not f:
                continue
            new_f = f
            for (rn_wp, rn_old), rn_new in SHEET_RENAMES.items():
                # 只替换 PREV/WP 第二实参位置上的该 sheet 名（带引号，避免误伤描述）
                new_f = new_f.replace(f"'{rn_wp}','{rn_old}'", f"'{rn_wp}','{rn_new}'")
                new_f = new_f.replace(f"'{rn_wp}', '{rn_old}'", f"'{rn_wp}', '{rn_new}'")
            if new_f != f:
                c["formula"] = new_f

    by_key = {_key(b): b for b in mappings}

    # 2) cell patches
    for (wp, sheet, ref), new in cell_patches().items():
        blk = by_key.get((wp, sheet))
        if not blk:
            continue
        for c in blk.get("cells") or []:
            if str(c.get("cell_ref")) == ref:
                c.update(new)
                break

    # 3) 审定表补 WP()
    for k, cells in ADJUDICATION_WP_CELLS.items():
        blk = by_key.get(k)
        if not blk:
            continue
        have = {str(c.get("cell_ref")) for c in (blk.get("cells") or [])}
        blk["cells"].extend([c for c in cells if str(c["cell_ref"]) not in have])

    # 4) 新增明细块
    existing = {_key(b) for b in mappings}
    mappings.extend([b for b in build_detail_blocks() if _key(b) not in existing])

    MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] 已写回，共处理 {debt} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
