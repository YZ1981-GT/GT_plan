#!/usr/bin/env python
"""fix_l0_prefill_presets.py — L0 函证公式预设纠偏（幂等）.

spec: l0-confirmation-source-alignment
  Requirements 2.1 ~ 2.9 / Property 5 / 6 / 7

改造前 L0 块**整块贴错标签**，四处都不可用：

1. **sheet 名不存在** —— 原写 ``审定表L0-1``，而源模板
   ``backend/wp_templates/L/L0 债务循环函证.xlsx`` 的 9 张可见 sheet 里**没有这个 tab**
   （底稿目录 / 函证程序表F0A / 函证结果汇总表L0-1 / 核实被函证单位信息L0-2 /
   跟函函证过程控制L0-3 / 函证差异调节表L0-4 / 长期应付款替代程序L0-5 /
   邮件传真回函可靠性验证L0-6 / 函证程序舞弊风险评价表L0-7）。
   函证枢纽压根没有审定表 → 该块永远匹配不上，是死配置。→ 改 ``函证结果汇总表L0-1``。

2. **科目码取的正是源模板明确排除的银行借款** —— 原 ``account_codes=['2001','2501']``：
   ``2001`` 是**短期借款**、``2501`` 是**长期借款**（``account_chart`` 双向对账实证），
   而源模板 ``函证程序表F0A!G7`` 的程序 1 批注**逐字写着**「本函证不包含银行长期借款、
   银行短期借款函证，与银行借款相关函证详见货币资金循环」。
   L0 的真实品种是 ``E29 长期应付款`` / ``F29 应付债券``。

3. **病态区间** —— 原 ``TB_SUM('2001~2501', ...)`` 会把 2001~2501 之间**全部负债科目**
   （应付票据/应付账款/预收/应付职工薪酬/应交税费/其他应付款/长期借款…）扫进来。

4. **cell_ref 是审定表口径** —— 原写「期初余额」/「未审数」，而 L0-1 需要取数的位置是
   下区「一、函证情况」矩阵的**「本期（期末）账面金额」两格**（源 ``E30``/``F30``，
   源模板该行**无公式**=手填）。cell_ref 同时是**手工覆盖键** → 写审定表口径的键
   等于让预设永远落不到矩阵上。→ 改为 G0/K0 已确立的矩阵键
   ``L0-1-matrix-{品种}-book_amount``。

取数口径（``report_config`` 只读实证，四准则一致）::

    长期应付款  BS-064 = TB('2701','期末余额')
    应付债券    BS-062 = TB('2502','期末余额')

🔴 **必须按 row_code 精确匹配，不能按 row_name** —— ``BS-092`` 在 soe 侧 row_name
也叫「长期应付款」但 ``formula`` 为 NULL，按 row_name 匹配会拿到空公式
（同 K2 的 BS-014/BS-017、K0 的 BS-050/BS-075 同名坑）。

🔴 公式一律 ``PLACEHOLDER``（沿用 G0/H0/K0 已落地的范式），**不写 TB()**：
``cell_ref`` 是手工覆盖键，写 ``TB()`` 会让「按码取到的 0」伪装成审计师手填值，
压住语义定位拿到的 ``undefined`` → 「本项目无此科目」与「余额为 0」不可区分。
运行态取数一律走 ``four_table`` 语义定位（``l_cycle_specs.L5_SPEC`` / ``L4_SPEC``，
按科目名在**本项目**科目表定位 + 叶子聚合），``account_codes`` 只作展示与筛选。

用法::

    python backend/scripts/fix/fix_l0_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_l0_prefill_presets.py --check    # exit 1 = 有欠账
    python backend/scripts/fix/fix_l0_prefill_presets.py --apply

🔴 round-trip 自检：先确认 ``json.dumps(json.loads(raw))`` 能**逐字复现**原文，
   不能复现即 exit 2 拒绝写入（防把并发会话的格式/顺序整体重排）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
L0_XLSX = REPO_ROOT / "backend" / "wp_templates" / "L" / "L0 债务循环函证.xlsx"

WP_CODE = "L0"
WP_NAME = "债务循环函证"

#: 源模板真实的函证结果汇总表 tab 名
TARGET_SHEET = "函证结果汇总表L0-1"
OBSOLETE_SHEET = "审定表L0-1"

#: 源模板 L0A!G7 明确排除的银行借款科目 —— 改造前的 account_codes 正是这两个
BANK_LOAN_CODES_EXCLUDED = ("2001", "2501")

#: 两品种参考科目码（**仅作展示与筛选**；运行态一律走语义定位，不据此写死取数）。
#: 与 `four_table/l_cycle_specs.py` 的 L5_SPEC / L4_SPEC 兜底码一致。
L0_REFERENCE_ACCOUNT_CODES = [
    "2701",  # 长期应付款（BS-064）
    "2702",  # 未确认融资费用（2701 的抵减子族；父族叶子聚合已按方向净掉，不二次减）
    "2502",  # 应付债券（BS-062）
]

_SEMANTIC_NOTE = (
    "参考科目码仅作展示与筛选，运行态不据此取数 —— 一律走 four_table 语义定位"
    "（l_cycle_specs 的 L5_SPEC/L4_SPEC + semantic_account_resolver，"
    "按科目名在**本项目**科目表定位 + 叶子聚合，期末余额口径）。"
)

_PLACEHOLDER_NOTE = (
    "🔴 formula_type 用 PLACEHOLDER 不写 TB()：cell_ref 同时是手工覆盖键，"
    "写 TB() 会让「按码取到的 0」伪装成审计师手填值，压住语义定位拿到的 undefined，"
    "使「本项目无此科目」与「余额为 0」不可区分（R2.8 / R3.4）。"
)

_FIX_NOTE = (
    "纠偏：原块 sheet='审定表L0-1'（源 xlsx 无此 tab，函证枢纽无审定表）、"
    "account_codes=['2001','2501']（分别是短期借款/长期借款，"
    "正是源模板 函证程序表F0A!G7 程序 1 批注明确排除的银行借款）、"
    "公式 TB_SUM('2001~2501',…)（病态区间，会把两码之间全部负债科目扫入）、"
    "cell_ref 是审定表口径的「期初余额」/「未审数」（永远落不到矩阵上）。"
)

#: 矩阵账面金额两格（源 E30/F30）。cell_ref 沿用 G0/K0 已落地的矩阵手工覆盖键形态
#: `X0-1-matrix-{品种}-{指标key}` —— 品种段是源模板中文字面（同时是上区 E 列
#: SUMIF 的 criteria，非可改文案），指标段是稳定 key。
TARGET_CELLS = [
    {
        "cell_ref": "L0-1-matrix-长期应付款-book_amount",
        "formula": "=PLACEHOLDER('长期应付款本期（期末）账面金额')",
        "formula_type": "PLACEHOLDER",
        "description": (
            "品种「长期应付款」本期（期末）账面金额（源模板 函证结果汇总表L0-1!E30，"
            "该行无公式=手填，是矩阵 8 指标里唯一的录入位）。"
            "报表行 **BS-064** = TB('2701','期末余额')，四准则一致；"
            "🔴 必须按 row_code 精确匹配 —— BS-092 在 soe 侧 row_name 也叫「长期应付款」"
            "但 formula 为 NULL，按 row_name 匹配会拿到空公式。"
            "2702 未确认融资费用是 2701 的抵减子族，**已在父族叶子聚合内按方向净掉，"
            "不作二次扣减**（否则双算）。"
            + _SEMANTIC_NOTE + _PLACEHOLDER_NOTE + _FIX_NOTE
        ),
    },
    {
        "cell_ref": "L0-1-matrix-应付债券-book_amount",
        "formula": "=PLACEHOLDER('应付债券本期（期末）账面金额')",
        "formula_type": "PLACEHOLDER",
        "description": (
            "品种「应付债券」本期（期末）账面金额（源模板 函证结果汇总表L0-1!F30，"
            "该行无公式=手填）。"
            "报表行 **BS-062** = TB('2502','期末余额')，四准则一致。"
            + _SEMANTIC_NOTE + _PLACEHOLDER_NOTE
        ),
    },
]

#: 只扫这些**语义字段**做校验；`description`/`notes` 会如实写出被纠正的反例
#: （如「原写 TB_SUM('2001~2501',…)」），把它们纳入比对会让「说明文字被数成真实引用」，
#: 也会让手工补充说明被判成欠账（R2.7）。
SEMANTIC_CELL_FIELDS = ("cell_ref", "formula", "formula_type", "applies_when")

#: 语义字段里禁止出现的字样
FORBIDDEN_IN_SEMANTIC = ("TB_SUM", "SUM_TB", "TB(", *BANK_LOAN_CODES_EXCLUDED)


# ─── round-trip 格式（实证：indent=2 / ensure_ascii=False / 有末尾换行） ──────

_DUMP_KW = {"ensure_ascii": False, "indent": 2}
_TRAILING_NEWLINE = "\n"


def _dump(data) -> str:
    return json.dumps(data, **_DUMP_KW) + _TRAILING_NEWLINE


def _safe(text: str) -> str:
    """Windows GBK 控制台安全输出：剥掉本地 codepage 编不出的字符（如 🔴）。

    否则 `print` 会抛 UnicodeEncodeError 让脚本整体崩掉（与写盘无关的输出层问题）。
    """
    enc = (sys.stdout.encoding or "utf-8")
    return str(text).encode(enc, errors="replace").decode(enc, errors="replace")


def _round_trip_ok(raw: str, data) -> bool:
    return _dump(data) == raw


# ─── 期望块 / 欠账诊断 ───────────────────────────────────────────────────────


def build_l0_block() -> dict:
    return {
        "wp_code": WP_CODE,
        "wp_name": WP_NAME,
        "sheet": TARGET_SHEET,
        "account_codes": list(L0_REFERENCE_ACCOUNT_CODES),
        "cells": [dict(c) for c in TARGET_CELLS],
    }


def _semantic_view(cell: dict) -> dict:
    return {k: cell.get(k) for k in SEMANTIC_CELL_FIELDS if k in cell or k != "applies_when"}


def diff_block(existing: dict | None) -> list[str]:
    """返回欠账清单（空 = 已对齐）。只扫语义字段（R2.7）。"""
    gaps: list[str] = []
    expected = build_l0_block()

    if existing is None:
        gaps.append(f"{WP_CODE} 预设块缺失")
        return gaps

    if existing.get("sheet") != TARGET_SHEET:
        gaps.append(
            f"sheet = {existing.get('sheet')!r}，应为 {TARGET_SHEET!r}"
            + ("（源 xlsx 无此 tab，函证枢纽无审定表）"
               if existing.get("sheet") == OBSOLETE_SHEET else "")
        )

    codes = list(existing.get("account_codes") or [])
    for bad in BANK_LOAN_CODES_EXCLUDED:
        if bad in codes:
            gaps.append(
                f"account_codes 含 {bad}（"
                + ("短期借款" if bad == "2001" else "长期借款")
                + "）—— 源模板 L0A 程序 1 明确排除银行借款"
            )
    for need in ("2701", "2502"):
        if need not in codes:
            gaps.append(f"account_codes 缺 {need}（"
                        + ("长期应付款 BS-064" if need == "2701" else "应付债券 BS-062")
                        + "）")

    got_cells = existing.get("cells") or []
    exp_cells = expected["cells"]

    for cell in got_cells:
        for field in SEMANTIC_CELL_FIELDS:
            val = str(cell.get(field) or "")
            for bad in FORBIDDEN_IN_SEMANTIC:
                if bad in val:
                    gaps.append(
                        f"cells[{cell.get('cell_ref')!r}].{field} 含禁用字样 {bad!r}: {val[:60]!r}"
                    )

    got_refs = [c.get("cell_ref") for c in got_cells]
    exp_refs = [c["cell_ref"] for c in exp_cells]
    if got_refs != exp_refs:
        gaps.append(f"cell_ref 序列 {got_refs} 应为 {exp_refs}")
        return gaps

    for g, e in zip(got_cells, exp_cells):
        for field in SEMANTIC_CELL_FIELDS:
            if field == "applies_when" and field not in e and field not in g:
                continue
            if g.get(field) != e.get(field):
                gaps.append(
                    f"cells[{e['cell_ref']!r}].{field} 不符："
                    f"{str(g.get(field))[:50]!r} → {str(e.get(field))[:50]!r}"
                )
    return gaps


def _find_block(mappings: list, wp_code: str) -> tuple[int, dict] | tuple[None, None]:
    for i, b in enumerate(mappings):
        if str(b.get("wp_code") or "") == wp_code:
            return i, b
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账则非零退出")
    g.add_argument("--dry-run", action="store_true", help="打印将写入的内容，不落盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        print("[ERR] prefill_formula_mapping.json 缺少 mappings 列表", file=sys.stderr)
        return 2

    idx, block = _find_block(mappings, WP_CODE)
    gaps = diff_block(block)

    if args.check:
        if gaps:
            print(f"欠账 {len(gaps)} 项：")
            for gap in gaps:
                print("  -", _safe(gap))
            return 1
        print(f"[OK] {WP_CODE} 预设块已对齐源模板（0 项欠账）")
        return 0

    if not gaps:
        print(f"[OK] 已对齐，无需改动（{WP_CODE} 块 {len(TARGET_CELLS)} cells）")
        return 0

    if not _round_trip_ok(raw, data):
        print(
            "[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文。\n"
            "   直接写盘会重排整个文件（并发会话冲突风险），已中止。",
            file=sys.stderr,
        )
        return 2

    others_before = [
        json.dumps(b, ensure_ascii=False, sort_keys=True)
        for i, b in enumerate(mappings) if i != idx
    ]

    expected = build_l0_block()
    if idx is None:
        mappings.append(expected)
    else:
        mappings[idx] = expected

    others_after = [
        json.dumps(b, ensure_ascii=False, sort_keys=True)
        for i, b in enumerate(mappings) if i != (idx if idx is not None else len(mappings) - 1)
    ]
    if others_before != others_after:
        print("[ERR] 加法式约束被破坏：其他 wp_code 的块发生变化，已中止", file=sys.stderr)
        return 2

    out = _dump(data)

    if args.dry_run:
        # 🔴 只打印**语义字段**摘要，不打 description 全文 —— 后者含 🔴 等
        # 非 GBK 字符，在 Windows GBK 控制台会 UnicodeEncodeError 直接崩掉。
        print(f"[dry-run] 将写入 {WP_CODE} 块：")
        print(f"  sheet          = {expected['sheet']}")
        print(f"  account_codes  = {expected['account_codes']}")
        for c in expected["cells"]:
            print(f"  cell_ref       = {c['cell_ref']}")
            print(f"    formula      = {c['formula']}")
            print(f"    formula_type = {c['formula_type']}")
            print(f"    description  = {len(c['description'])} 字（含纠偏说明，此处省略）")
        print(f"\n[dry-run] 欠账 {len(gaps)} 项将被修复：")
        for gap in gaps:
            print("  -", _safe(gap))
        return 0

    if args.apply:
        MAPPING_PATH.write_text(out, encoding="utf-8")
        print(f"[OK] 已写入 {WP_CODE} 块（{len(expected['cells'])} cells），修复 {len(gaps)} 项欠账")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
