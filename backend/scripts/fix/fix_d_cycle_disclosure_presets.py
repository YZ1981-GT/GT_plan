"""D 循环披露 sheet 公式预设补齐（幂等）—— spec Task 20。

改造前 **只有 D4** 的两张披露 sheet 有预设块（各 8 cells），D1/D2/D3/D5/D6/D7
共 **12 张披露 sheet 零预设** ⇒ 公式管理页面在这些 sheet 上完全空白，审计师
看不到「这张披露表的数应该从哪来」。

用法::

    python backend/scripts/fix/fix_d_cycle_disclosure_presets.py            # dry-run
    python backend/scripts/fix/fix_d_cycle_disclosure_presets.py --check    # 欠账数即退出码
    python backend/scripts/fix/fix_d_cycle_disclosure_presets.py --apply

🔴 **sheet 名逐字取源 xlsx tab 名，六种括号写法并存，禁「统一」**（2026-08-06
openpyxl 直读 `wb.sheetnames` 实证）::

    D1  '附注披露信息（上市公司）'   '附注披露信息（国企）'      全角 / 全角
    D2  '附注披露信息(上市公司)'    '附注披露信息(国企)'        半角 / 半角
    D3  '附注披露信息(上市公司)'    '附注披露信息(国企)'        半角 / 半角
    D5  '附注披露信息（上市公司）'   '附注披露信息（国企）'      全角 / 全角
    D6  '附注披露信息(上市公司）'    '附注披露信息（国企）'      **前半后全** / 全角
    D7  '附注披露信息(上市公司)'    '附注披露信息(国企)'        半角 / 半角

`sheet` 是运行时匹配键（`page_key` 由 `wp_code` + sheet 派生），写错即预设永不命中。

🔴 **`cell_ref` 用业务语义名不是单元格地址** —— 与 D4 既有块及平台 prefill 引擎
一致（`cell_ref` 同时是手工覆盖键）。

🔴 **公式口径与各循环 render 的报表行解析结果对齐**（不硬编码猜）::

    D1  BS-005 应收票据    原值 1121 − 备抵 1231-01
    D2  BS-006 应收账款    原值 1122 − 备抵 1231-02
    D3  BS-046 预收款项    2203（负债，无备抵）
    D5  BS-007 应收款项融资 1124 → **PLACEHOLDER**（见下）
    D6  BS-011 合同资产    原值 1141 − 备抵 1142
    D7  BS-047 合同负债    2205（负债，无备抵）

🔴 **D5 一律 PLACEHOLDER**：`1124` 在活体 `account_chart` 两个 source 零命中、
`account_mapping` 零反解、`tb_balance` 零数据行 —— 是**业务事实**（这批项目没有
应收款项融资业务），不是错码。写 `TB('1124',…)` 会让公式管理页显示一个恒空的
公式，比 PLACEHOLDER + 实证说明更差。

🔴 **D2 的 4 张 hidden 披露表不建预设**（`附注披露信息(上市公司）D2-1` /
`附注披露信息（国企）D2-1`，分布在 3 个 D2 workbook 里）—— 它们是旧版残留且
`sheet_state=hidden`，给它们建预设会在公式管理页凭空多出四张不该编制的表。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 5.1, 5.2, 5.7, 5.9 / Task 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
MAPPING_PATH = BACKEND / "data" / "prefill_formula_mapping.json"

# ── 源 xlsx 真实 tab 名（openpyxl 直读，逐字，禁改写）────────────────────────
DISCLOSURE_SHEETS: dict[str, tuple[str, str]] = {
    "D1": ("附注披露信息（上市公司）", "附注披露信息（国企）"),
    "D2": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
    "D3": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
    "D5": ("附注披露信息（上市公司）", "附注披露信息（国企）"),
    "D6": ("附注披露信息(上市公司）", "附注披露信息（国企）"),
    "D7": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
}

# D2 的 hidden 旧版披露表 —— 显式登记为「不建预设」，防后续会话「补齐」
HIDDEN_LEGACY_SHEETS: tuple[str, ...] = (
    "附注披露信息(上市公司）D2-1",
    "附注披露信息（国企）D2-1",
)

# ── 各循环科目与报表行（与 render 的 report_line_accounts 解析结果对齐）───────
# (中文科目名, 报表行, 原值标准码, 备抵标准码或 None, 是否负债)
CYCLE_SPEC: dict[str, tuple[str, str, str, str | None, bool]] = {
    "D1": ("应收票据", "BS-005", "1121", "1231-01", False),
    "D2": ("应收账款", "BS-006", "1122", "1231-02", False),
    "D3": ("预收款项", "BS-046", "2203", None, True),
    "D5": ("应收款项融资", "BS-007", "1124", None, False),
    "D6": ("合同资产", "BS-011", "1141", "1142", False),
    "D7": ("合同负债", "BS-047", "2205", None, True),
}

# D5 的 PLACEHOLDER 理由（逐条登记，防它变成逃逸阀）
D5_PLACEHOLDER_REASON = (
    "应收款项融资（1124）在活体 account_chart 两个 source 均零命中、"
    "account_mapping 零反解、tb_balance 零数据行 —— 本平台在册项目无此业务，"
    "属业务事实而非错码。取数口径待客户实际启用该科目后按 BS-007 报表行解析补入。"
)


def _cells_for(wp: str, sheet: str) -> list[dict[str, Any]]:
    """构造某循环某披露 sheet 的 cells。纯函数。"""
    name, row_code, gross, provision, is_liability = CYCLE_SPEC[wp]

    if wp == "D5":
        return [
            {
                "cell_ref": "期末账面价值",
                "formula": "=PLACEHOLDER()",
                "formula_type": "PLACEHOLDER",
                "description": f"{name}披露表期末账面价值（{row_code}）。{D5_PLACEHOLDER_REASON}",
            },
            {
                "cell_ref": "上年账面价值",
                "formula": f"=PREV('{wp}','{sheet}','期末账面价值')",
                "formula_type": "PREV",
                "description": f"上年{name}账面价值（取上年同页）",
            },
        ]

    period = "期末余额"
    cells: list[dict[str, Any]] = [
        {
            "cell_ref": "期末账面余额",
            "formula": f"=TB('{gross}','{period}')",
            "formula_type": "TB",
            "description": f"{name}披露表期末账面余额（{row_code} 原值口径，科目 {gross}）",
        }
    ]

    if provision:
        cells.append(
            {
                "cell_ref": "期末坏账准备",
                "formula": f"=TB('{provision}','{period}')",
                "formula_type": "TB",
                "description": (
                    f"{name}披露表期末减值准备（标准码 {provision}）。"
                    "🔴 取数侧对该码无条件叠加主体名称过滤 —— account_mapping 存在把"
                    "其他科目的坏账准备错映射到本码的 auto_fuzzy 行。"
                ),
            }
        )
        cells.append(
            {
                "cell_ref": "期末账面价值",
                "formula": f"=TB('{gross}','{period}')-TB('{provision}','{period}')",
                "formula_type": "TB",
                "description": f"{name}披露表期末账面价值 = 账面余额 − 减值准备（{row_code}）",
            }
        )
    else:
        cells.append(
            {
                "cell_ref": "期末账面价值",
                "formula": f"=TB('{gross}','{period}')",
                "formula_type": "TB",
                "description": (
                    f"{name}披露表期末账面价值（{row_code}"
                    f"{'，负债类贷方口径' if is_liability else ''}）。本循环无备抵科目。"
                ),
            }
        )

    cells.append(
        {
            "cell_ref": "期初账面余额",
            "formula": f"=TB('{gross}','期初余额')",
            "formula_type": "TB",
            "description": f"{name}披露表期初账面余额（科目 {gross}）",
        }
    )
    cells.append(
        {
            "cell_ref": "上年账面价值",
            "formula": f"=PREV('{wp}','{sheet}','期末账面价值')",
            "formula_type": "PREV",
            "description": f"上年{name}账面价值（取上年同页）",
        }
    )
    # 🔴 明细表联动：审定表↔明细表已由 Task 19 建好，披露表引用**明细表**而非审定表，
    #    避免「披露→审定→明细」三级链在审定表未编制时整条断掉。
    detail = DETAIL_SHEET.get(wp)
    if detail:
        cells.append(
            {
                "cell_ref": "明细表合计核对",
                "formula": f"=WP('{wp}','{detail}','期末合计')",
                "formula_type": "WP",
                "description": f"与{detail}期末合计核对（勾稽用，不参与披露取数）",
            }
        )
    return cells


# 各循环明细表 tab 名（源 xlsx 实证；D5 明细表存在但取数走 PLACEHOLDER 故不接）
DETAIL_SHEET: dict[str, str] = {
    "D1": "原值明细表（按类别）D1-2",
    "D2": "明细表D2-2",
    "D3": "预收账款明细表D3-2",
    "D6": "明细表D6-2",
    "D7": "明细表D7-2",
}


def build_expected_blocks() -> list[dict[str, Any]]:
    """构造应存在的 12 个披露块。纯函数、稳定排序。"""
    out: list[dict[str, Any]] = []
    for wp in sorted(DISCLOSURE_SHEETS):
        listed, soe = DISCLOSURE_SHEETS[wp]
        name = CYCLE_SPEC[wp][0]
        for sheet in (listed, soe):
            _, _, gross, provision, _ = CYCLE_SPEC[wp]
            accounts = [gross] + ([provision] if provision else [])
            out.append(
                {
                    "wp_code": wp,
                    "wp_name": f"{wp} {sheet}",
                    "sheet": sheet,
                    "sheet_name": sheet,
                    "account_codes": accounts,
                    "cells": _cells_for(wp, sheet),
                }
            )
    return out


def _key(block: dict[str, Any]) -> tuple[str, str]:
    return str(block.get("wp_code") or ""), str(block.get("sheet") or "")


def plan(mappings: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """返回 (待新增块, 待补 cells 的块)。语义比对，**不**看 description。"""
    existing = {_key(b): b for b in mappings}
    to_add: list[dict] = []
    to_patch: list[dict] = []
    for exp in build_expected_blocks():
        cur = existing.get(_key(exp))
        if cur is None:
            to_add.append(exp)
            continue
        have = {str(c.get("cell_ref")) for c in (cur.get("cells") or [])}
        missing = [c for c in exp["cells"] if str(c["cell_ref"]) not in have]
        if missing:
            to_patch.append({"key": _key(exp), "missing": missing})
    return to_add, to_patch


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="写回 JSON")
    ap.add_argument("--check", action="store_true", help="仅报欠账数（欠账即非零退出）")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    mappings: list[dict[str, Any]] = data["mappings"]

    # round-trip 自检：不能逐字复现原文即拒绝写回（防全文件重排与并发冲突）
    round_trip = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    rt_ok = round_trip == raw
    if not rt_ok and args.apply:
        print("[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文，拒绝写回")
        print(f"      原文 {len(raw)} 字节 / 复现 {len(round_trip)} 字节")
        return 2

    to_add, to_patch = plan(mappings)
    debt = len(to_add) + sum(len(p["missing"]) for p in to_patch)

    print(f"[INFO] mappings 总块数 = {len(mappings)}")
    print(f"[INFO] 应有披露块 = {len(build_expected_blocks())}（6 循环 x 2 变体）")
    print(f"[INFO] 待新增块 = {len(to_add)} / 待补 cells = {sum(len(p['missing']) for p in to_patch)}")
    for b in to_add:
        print(f"       + {b['wp_code']}  {b['sheet']!r}  cells={len(b['cells'])}")
    for p in to_patch:
        refs = [str(c["cell_ref"]) for c in p["missing"]]
        print(f"       ~ {p['key'][0]}  {p['key'][1]!r}  missing={refs}")

    print(f"[INFO] hidden 旧版披露表（有意不建预设）= {list(HIDDEN_LEGACY_SHEETS)}")
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

    by_key = {_key(b): b for b in mappings}
    for p in to_patch:
        by_key[p["key"]]["cells"].extend(p["missing"])
    mappings.extend(to_add)

    MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] 已写回：新增 {len(to_add)} 块 / 补 {sum(len(p['missing']) for p in to_patch)} cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
