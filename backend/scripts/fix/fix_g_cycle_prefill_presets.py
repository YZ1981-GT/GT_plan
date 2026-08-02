#!/usr/bin/env python
"""G 循环公式预设纠偏（幂等）。

修订 ``backend/data/prefill_formula_mapping.json`` 里 G1~G14 的 6 类缺陷
（全部为 2026-08-01 DB + 源 xlsx 只读实证）：

1. **取错科目族**
   - G6 用 ``1505``（= 债权投资减值准备），其他债权投资真值 **``1506``**
   - G8 用 ``1506``（= 其他债权投资），其他权益工具投资真值 **``1507``**
   - G9 用 ``1507``（= 其他权益工具投资），其他非流动金融资产真值 **``1519``**
   - G12 用 ``6115``（= 资产处置损益，H10 的科目），净敞口套期收益真值 **``6103``**
   - G14 用 ``6701``（= 资产减值损失，K11 的科目），信用减值损失真值 **``6702``**
   根因：`report_config` 的 ``BS-022/BS-025/BS-026`` 连续偏移一位、
   ``IS-016`` 与 ``IS-017`` 整整互换（详见 `four_table/g_cycle_specs` docstring）。

2. **区间口径把四个科目全加进一个循环**
   G4 审定表 ``TB_SUM('1504~1507')`` → 把 G4 原值 + 其备抵 + G6 + G8 全加进债权投资。
   改 ``TB('1504')``，`account_codes` 收敛为 ``['1504', '1505']``（原值 + 备抵）。

3. **残留不存在 / 别循环的子科目**
   - G4-2 的 ``TB('1501.03')`` —— ``1501`` 是旧准则「持有至到期投资」，取数恒空
   - G8-2 的 ``TB('1525')`` / ``TB('1526')`` / ``TB('1527')`` —— 投资性房地产
     累计折旧 / 累计摊销 / 减值准备（H3 的科目族）
   两者均**删除**（宁缺勿造：客户子科目结构不可预设）。

4. **损益类口径错**
   G11/G12/G13/G14 用 ``期初余额`` / ``期末余额``，而损益类科目在含年末结转损益的
   全年账上余额恒为 0（实测 `tb_balance.closing_balance` 在 6101/6111/6115/6701/6702
   全项目全为 0）。平台权威口径见 `report_config` 的 ``IS-011``/``IS-015`` —— 均为
   ``本期发生额``。
   - ``未审数`` 改 ``本期发生额``
   - ``期初余额`` **删除**（损益类无期初余额；`formula_engine.COLUMN_ALIASES` 也没有
     ``上期发生额`` 别名，写了会被静默回退成 ``期末余额``；上年数已由 ``上年审定数``
     的 ``PREV()`` 覆盖）

5. **幽灵 sheet**
   G1 有一个 ``分析程序G1-3`` 块，而源 xlsx 的 G1-3 实为 ``调整分录汇总G1-3``
   → 该 sheet 名不存在，整块预设永不命中，**删除**。

6. **描述贴错标签**：随科目码一并纠正 ``description`` 里的科目名与码。

Usage::

    python backend/scripts/fix/fix_g_cycle_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_g_cycle_prefill_presets.py --check
    python backend/scripts/fix/fix_g_cycle_prefill_presets.py

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/ Requirements 4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
PRESETS = _BACKEND / "data" / "prefill_formula_mapping.json"

#: 损益类循环（口径必须是本期发生额）
PL_CYCLES = {"G11", "G12", "G13", "G14"}

#: 损益类循环里应删除的 cell_ref（损益无期初余额）
PL_DROP_CELL_REFS = {"期初余额"}

#: 科目码整体替换：wp_code → {旧码: 新码}
CODE_REMAP: dict[str, dict[str, str]] = {
    "G6": {"1505": "1506"},
    "G8": {"1506": "1507"},
    "G9": {"1507": "1519"},
    "G12": {"6115": "6103"},
    "G14": {"6701": "6702"},
}

#: 科目名纠正（description 里贴错的标签）：wp_code → [(旧文案, 新文案)]
DESC_FIXES: dict[str, list[tuple[str, str]]] = {
    "G4": [
        ("1501 债权投资", "1504 债权投资"),
        ("债权投资审定表期初余额合计", "债权投资期初余额"),
        ("债权投资审定表期末余额合计（未审）", "债权投资期末余额（未审）"),
    ],
    "G8": [("1521 其他权益工具投资", "1507 其他权益工具投资")],
}

#: 整块删除：(wp_code, sheet) —— 源 xlsx 无此 sheet
DROP_BLOCKS: set[tuple[str, str]] = {("G1", "分析程序G1-3")}

#: 单元格删除：(wp_code, sheet, cell_ref) —— 引用不存在 / 别循环科目
DROP_CELLS: set[tuple[str, str, str]] = {
    ("G4", "明细表G4-2", "应计利息_期末"),
    ("G8", "明细表G8-2", "FVOCI_1525_期末"),
    ("G8", "明细表G8-2", "FVOCI_1526_期末"),
    ("G8", "明细表G8-2", "FVOCI_1527_期末"),
}

#: G4 审定表：区间口径 → 单科目
G4_ADJ_SHEET = "审定表G4-1"
G4_ADJ_FORMULA_FIXES = {
    "=TB_SUM('1504~1507','期初余额')": "=TB('1504','期初余额')",
    "=TB_SUM('1504~1507','期末余额')": "=TB('1504','期末余额')",
}
G4_ADJ_ACCOUNTS = ["1504", "1505"]


def _blocks_of(data: dict, wp_code: str) -> list[dict]:
    return [b for b in data.get("mappings", []) if b.get("wp_code") == wp_code]


def _remap_codes_in_text(text: str, remap: dict[str, str]) -> str:
    """把 ``'1505'`` / ``'1505.01'`` 形态的科目码整体替换（严格边界）。"""
    out = text
    for old, new in remap.items():
        # 引号内的整码或带点号子科目：'1505' / '1505.01'
        out = re.sub(rf"'{old}((?:\.\d+)*)'", rf"'{new}\1'", out)
        # 描述文字里的裸码（前后不是数字）
        out = re.sub(rf"(?<!\d){old}(?!\d)", new, out)
    return out


def apply_fixes(data: dict) -> list[str]:
    """就地修订，返回变更说明列表（空 = 已无欠账）。纯函数（除就地改 data）。"""
    changes: list[str] = []
    mappings: list[dict] = data.get("mappings", [])

    # ── 1. 整块删除（幽灵 sheet）────────────────────────────────────────────
    keep: list[dict] = []
    for blk in mappings:
        key = (blk.get("wp_code"), blk.get("sheet"))
        if key in DROP_BLOCKS:
            changes.append(f"删除幽灵块 {key[0]} / sheet={key[1]}（源 xlsx 无此 sheet）")
            continue
        keep.append(blk)
    if len(keep) != len(mappings):
        data["mappings"] = keep
        mappings = keep

    # ── 2. 单元格删除 ──────────────────────────────────────────────────────
    for blk in mappings:
        wp = blk.get("wp_code")
        sheet = blk.get("sheet")
        cells = blk.get("cells") or []
        kept_cells = []
        for cell in cells:
            if (wp, sheet, cell.get("cell_ref")) in DROP_CELLS:
                changes.append(
                    f"删除 {wp}/{sheet}/{cell.get('cell_ref')}"
                    f"（引用不存在或别循环科目：{cell.get('formula')}）"
                )
                continue
            kept_cells.append(cell)
        if len(kept_cells) != len(cells):
            blk["cells"] = kept_cells

    # ── 3. G4 区间口径 → 单科目 ─────────────────────────────────────────────
    for blk in _blocks_of(data, "G4"):
        if blk.get("sheet") != G4_ADJ_SHEET:
            continue
        if blk.get("account_codes") != G4_ADJ_ACCOUNTS:
            changes.append(
                f"G4/{G4_ADJ_SHEET} account_codes {blk.get('account_codes')}"
                f" → {G4_ADJ_ACCOUNTS}（原把 G6/G8 科目也算进债权投资）"
            )
            blk["account_codes"] = list(G4_ADJ_ACCOUNTS)
        for cell in blk.get("cells") or []:
            f = cell.get("formula") or ""
            if f in G4_ADJ_FORMULA_FIXES:
                changes.append(
                    f"G4/{G4_ADJ_SHEET}/{cell.get('cell_ref')}: {f}"
                    f" → {G4_ADJ_FORMULA_FIXES[f]}"
                )
                cell["formula"] = G4_ADJ_FORMULA_FIXES[f]
                cell["formula_type"] = "TB"

    # ── 4. 科目码整体替换 ───────────────────────────────────────────────────
    for wp, remap in CODE_REMAP.items():
        for blk in _blocks_of(data, wp):
            before_acc = list(blk.get("account_codes") or [])
            after_acc = [_remap_codes_in_text(c, remap) for c in before_acc]
            if after_acc != before_acc:
                changes.append(f"{wp}/{blk.get('sheet')} account_codes {before_acc} → {after_acc}")
                blk["account_codes"] = after_acc
            for cell in blk.get("cells") or []:
                for field in ("formula", "description"):
                    old = cell.get(field) or ""
                    new = _remap_codes_in_text(old, remap)
                    if new != old:
                        changes.append(
                            f"{wp}/{blk.get('sheet')}/{cell.get('cell_ref')}.{field}: {old} → {new}"
                        )
                        cell[field] = new

    # ── 5. 损益类口径 → 本期发生额 ──────────────────────────────────────────
    for wp in sorted(PL_CYCLES):
        for blk in _blocks_of(data, wp):
            cells = blk.get("cells") or []
            kept = []
            for cell in cells:
                ref = cell.get("cell_ref")
                if ref in PL_DROP_CELL_REFS:
                    changes.append(
                        f"{wp}/{blk.get('sheet')}/{ref}: 删除（损益类无期初余额，"
                        f"上年数由「上年审定数」的 PREV() 覆盖）"
                    )
                    continue
                f = cell.get("formula") or ""
                new_f = f.replace("','期末余额')", "','本期发生额')").replace(
                    "','期初余额')", "','本期发生额')"
                )
                if new_f != f:
                    changes.append(
                        f"{wp}/{blk.get('sheet')}/{ref}: {f} → {new_f}（损益类口径）"
                    )
                    cell["formula"] = new_f
                kept.append(cell)
            if len(kept) != len(cells):
                blk["cells"] = kept

    # ── 6. 描述贴错标签 ─────────────────────────────────────────────────────
    for wp, fixes in DESC_FIXES.items():
        for blk in _blocks_of(data, wp):
            for cell in blk.get("cells") or []:
                desc = cell.get("description") or ""
                new = desc
                for old_txt, new_txt in fixes:
                    new = new.replace(old_txt, new_txt)
                if new != desc:
                    changes.append(
                        f"{wp}/{blk.get('sheet')}/{cell.get('cell_ref')}.description 纠正贴错标签"
                    )
                    cell["description"] = new

    return changes


def load() -> dict[str, Any]:
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="G 循环公式预设纠偏（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写盘")
    ap.add_argument("--check", action="store_true", help="有欠账则 exit 1（CI 用）")
    args = ap.parse_args()

    original_text = PRESETS.read_text(encoding="utf-8")
    data = json.loads(original_text)

    # 🔴 round-trip 自检：先确认 dump 能逐字复现原文，否则本脚本会引入巨大无关 diff
    if dump(data) != original_text:
        print(
            "[FATAL] json.dumps 无法逐字复现原文（缩进 / 尾换行 / 转义不一致）。\n"
            "        继续写盘会产生覆盖全文件的无关 diff 并与并发会话冲突。",
            file=sys.stderr,
        )
        return 2

    changes = apply_fixes(data)

    if not changes:
        print("[OK] G 循环公式预设无欠账")
        return 0

    for c in changes:
        print(f"  - {c}")
    print(f"\n共 {len(changes)} 项变更")

    if args.check:
        print("[FAIL] 存在未修订的欠账（--check）", file=sys.stderr)
        return 1
    if args.dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    PRESETS.write_text(dump(data), encoding="utf-8")
    print(f"[WRITTEN] {PRESETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
