"""幂等脚本：纠正 H 类公式预设中的错误科目码。

用法：
    python -m scripts.fix.fix_h_cycle_prefill_presets --dry-run   # 只打印变更
    python -m scripts.fix.fix_h_cycle_prefill_presets --check     # 返回欠账数，CI 用
    python -m scripts.fix.fix_h_cycle_prefill_presets --apply     # 写盘

真源 = `four_table/h{n}_account_scope.py` 的兜底码声明。
脚本只改 `account_codes`（块的科目声明）和明显错误的 `wp_name`，
不改 `items`（公式条目本身全为空数组，暂无需改动）。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ─── 从单一真源动态提取各循环的正确科目码 ──────────────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.four_table.h_cycle_specs import H_CYCLE_SPECS  # noqa: E402


def _fallback_codes(cycle: str) -> list[str]:
    """从 H_CYCLE_SPECS 提取某循环全部槽的兜底码（排序去重）。"""
    spec = H_CYCLE_SPECS.get(cycle)
    if not spec:
        return []
    codes: list[str] = []
    for slot in spec.slots:
        codes.extend(slot.fallback_standard_codes or ())
    return sorted(set(codes))


# ─── 纠正规则（块定位 → 期望值） ────────────────────────────────────────────────

# (wp_code, sheet 子串) → 期望的 account_codes + 期望的 wp_name（None=不改名）
_CORRECTIONS: list[dict] = [
    # H3 审定表：整块是 H8 内容贴过来的
    {
        "wp_code": "H3", "sheet_match": "审定表",
        "expected_codes_source": "H3",
        "expected_wp_name": "投资性房地产审定表（成本模式）",
    },
    # H3 明细表(成本模式)：1522/1523 不存在
    {
        "wp_code": "H3", "sheet_match": "明细表（成本模式）",
        "expected_codes_source": "H3",
        "expected_wp_name": None,  # 名字已对
    },
    # H5 审定表：1611→1631/1632
    {
        "wp_code": "H5", "sheet_match": "审定表",
        "expected_codes_source": "H5",
        "expected_wp_name": None,
    },
    # H8 审定表：1631（油气）→1641/1642/1643
    {
        "wp_code": "H8", "sheet_match": "审定表",
        "expected_codes_source": "H8",
        "expected_wp_name": None,
    },
    # H8 明细表：1621/1622（生物资产）→1641/1642/1643
    {
        "wp_code": "H8", "sheet_match": "明细表",
        "expected_codes_source": "H8",
        "expected_wp_name": None,
    },
    # H9 审定表：2802（不存在）→2601
    {
        "wp_code": "H9", "sheet_match": "审定表",
        "expected_codes_source": "H9",
        "expected_wp_name": None,
    },
    # H9 明细表：2802→2601
    {
        "wp_code": "H9", "sheet_match": "租赁负债明细表",
        "expected_codes_source": "H9",
        "expected_wp_name": None,
    },
    # H9 未确认融资费用：2803→2602
    {
        "wp_code": "H9", "sheet_match": "未确认融资费用",
        "expected_codes": ["2602"],
        "expected_wp_name": None,
    },
    # H1 分析程序：1604（在建工程）不属 H1
    {
        "wp_code": "H1", "sheet_match": "分析程序",
        "expected_codes": ["1601", "1602", "1603"],
        "expected_wp_name": None,
    },
]


def _get_expected_codes(rule: dict) -> list[str]:
    """从规则获取期望码列表。"""
    if "expected_codes" in rule:
        return rule["expected_codes"]
    return _fallback_codes(rule["expected_codes_source"])


# ─── 公式表达式里的科目码纠正（`cells[].formula`） ─────────────────────────────
#
# 🔴 2026-08-03 浏览器实测发现：上一版只改了块级 `account_codes`，
# 而**公式表达式** `=TB('2802','期末余额')` 里的旧错误码没改 ——
# 底稿「四表取数（公式管理）」面板照旧显示 `TB('2205')` / `TB('2802')`，
# 取数当然还是错的。字段名是 `cells` 不是 `items`（上一版扫描报 `formulas=0` 即因此）。
#
# 形态：{wp_code: {旧码: 新码}}
_FORMULA_CODE_FIXES: dict[str, dict[str, str]] = {
    # H5 油气资产：1611 融资租赁资产 → 1631 油气资产
    "H5": {"1611": "1631"},
    # H8 使用权资产：1631 油气资产 → 1641 使用权资产
    "H8": {"1631": "1641", "1621": "1641", "1622": "1642"},
    # H9 租赁负债：2802/2803（不存在）→ 2601/2602；2205 是合同负债（D7 域）
    "H9": {"2802": "2601", "2803": "2602", "2205": "2601", "220501": "2602"},
    # H3 投资性房地产：1503 可供出售金融资产 / 1504 债权投资 → 1521 / 1525
    "H3": {"1503": "1521", "1504": "1525", "1522": "1525", "1523": "1526"},
    # H2 在建工程：不得引用 1601 固定资产（H1 域）
    # H10 资产处置损益：损益类不得用期初/期末余额口径（另由 _PL_COLUMN_FIXES 处理）
}

#: H10 损益类口径纠正：期初/期末余额 → 本期发生额
_PL_COLUMN_FIXES: dict[str, dict[str, str]] = {
    "H10": {"期初余额": "本期发生额", "期末余额": "本期发生额"},
}

#: 损益类科目（只有引用这些科目的公式才允许改成发生额口径）
#: `1606 固定资产清理` 是资产类过渡科目，**不在此列** —— 它有真实期初/期末余额。
_PL_ACCOUNTS: tuple[str, ...] = ("6115",)


def _fix_formula_codes(block: dict, mapping: dict[str, str]) -> list[str]:
    """替换块内全部 `cells[].formula` 的科目码。返回变更说明。"""
    changes: list[str] = []
    for cell in block.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        f = cell.get("formula")
        if not isinstance(f, str) or not f:
            continue
        new_f = f
        for old, new in mapping.items():
            # 只替换**引号内的科目码实参**，避免误伤描述文字或列名
            new_f = new_f.replace(f"'{old}'", f"'{new}'")
        if new_f != f:
            changes.append(
                f"    {cell.get('cell_ref', '?')}: {f} → {new_f}"
            )
            cell["formula"] = new_f
    return changes


def _fix_pl_columns(block: dict, mapping: dict[str, str]) -> list[str]:
    """损益类：把公式里的余额口径列名换成发生额。

    🔴 **只对损益科目生效**（`_PL_ACCOUNTS`）。H10 明细表同时引用
    `1606 固定资产清理` —— 那是**资产类过渡科目**，有真实期初/期末余额，
    套发生额口径会改错（首版误改，dry-run 时发现）。
    """
    changes: list[str] = []
    for cell in block.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        f = cell.get("formula")
        if not isinstance(f, str) or not f:
            continue
        # 该公式必须引用损益科目才允许改口径
        if not any(f"'{code}'" in f for code in _PL_ACCOUNTS):
            continue
        new_f = f
        for old, new in mapping.items():
            new_f = new_f.replace(f"'{old}'", f"'{new}'")
        if new_f != f:
            changes.append(f"    {cell.get('cell_ref', '?')}: {f} → {new_f}")
            cell["formula"] = new_f
    return changes


# ─── 主逻辑 ────────────────────────────────────────────────────────────────────

_MAPPING_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "prefill_formula_mapping.json"


def _find_block(mappings: list, wp_code: str, sheet_match: str) -> dict | None:
    """按 wp_code + sheet 子串定位块。"""
    for block in mappings:
        if not isinstance(block, dict):
            continue
        if block.get("wp_code") != wp_code:
            continue
        sheet = block.get("sheet", "") or ""
        if sheet_match in sheet:
            return block
    return None


def run(mode: str) -> int:
    """执行纠正。返回欠账数（0=全绿）。"""
    with open(_MAPPING_FILE, encoding="utf-8") as f:
        data = json.load(f)

    mappings = data.get("mappings", [])
    changes: list[str] = []

    for rule in _CORRECTIONS:
        block = _find_block(mappings, rule["wp_code"], rule["sheet_match"])
        if block is None:
            changes.append(f"[MISS] {rule['wp_code']} sheet含'{rule['sheet_match']}' 未找到")
            continue

        expected_codes = _get_expected_codes(rule)
        current_codes = block.get("account_codes", [])
        expected_name = rule.get("expected_wp_name")

        # 检查 codes
        if sorted(current_codes) != sorted(expected_codes):
            changes.append(
                f"[CODE] {rule['wp_code']} {block.get('sheet','')}: "
                f"{current_codes} → {expected_codes}"
            )
            if mode == "apply":
                block["account_codes"] = expected_codes

        # 检查 wp_name
        if expected_name and block.get("wp_name") != expected_name:
            changes.append(
                f"[NAME] {rule['wp_code']} {block.get('sheet','')}: "
                f"'{block.get('wp_name','')}' → '{expected_name}'"
            )
            if mode == "apply":
                block["wp_name"] = expected_name

    # ─── 公式表达式里的科目码 + 损益口径（遍历全部 H 块，不只 _CORRECTIONS 命中的） ───
    for block in mappings:
        if not isinstance(block, dict):
            continue
        wp = (block.get("wp_code") or "").upper()
        sheet = block.get("sheet", "") or ""

        code_map = _FORMULA_CODE_FIXES.get(wp)
        if code_map:
            # dry-run/check 不能改原对象 → 先深拷贝探测
            probe = block if mode == "apply" else json.loads(json.dumps(block))
            for line in _fix_formula_codes(probe, code_map):
                changes.append(f"[FORMULA] {wp} {sheet}:\n{line}")

        pl_map = _PL_COLUMN_FIXES.get(wp)
        if pl_map:
            probe = block if mode == "apply" else json.loads(json.dumps(block))
            for line in _fix_pl_columns(probe, pl_map):
                changes.append(f"[PL-COL] {wp} {sheet}:\n{line}")

    if mode == "check":
        if changes:
            print(f"[FAIL] {len(changes)} items need fixing:")
            for c in changes:
                print(f"  {c}")
            return len(changes)
        print("[OK] 0 items need fixing")
        return 0

    if mode == "dry-run":
        if changes:
            print(f"Would make {len(changes)} changes:")
            for c in changes:
                print(f"  {c}")
        else:
            print("No changes needed (already up to date)")
        return 0

    if mode == "apply":
        if not changes:
            print("[OK] No changes needed (already up to date)")
            return 0
        with open(_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[DONE] Written {len(changes)} changes:")
        for c in changes:
            print(f"  {c}")
        return 0

    return 1


def main():
    parser = argparse.ArgumentParser(description="纠正 H 类公式预设中的错误科目码")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        sys.exit(run("dry-run"))
    elif args.check:
        sys.exit(run("check"))
    elif args.apply:
        sys.exit(run("apply"))


if __name__ == "__main__":
    main()
