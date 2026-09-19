"""G0A 函证程序表 —— 补齐源模板「程序分类」（D 列）

spec: g0-confirmation-source-alignment，Task 17（Requirement 8.1/8.2/8.5/8.6）

背景（逐格实证）
-----------------
源模板 `backend/wp_templates/G/G0 投资循环函证.xlsx` 的 `函证程序表G0A` D 列是
**程序分类**（`常规★` / `备选` / `IPO/上市/新三板/重组/舞弊应对`），是项目组裁剪
程序的核心依据。平台 `procedure_table_templates.json` 的 `/tables/G0A` 12 条 item
**完全没有这个字段** → 前端「类别」列（`hasCategory` 全空即隐藏）不显示、类别筛选
radio-group 无选项、按类别批量裁剪无从下手。

前端与 render 侧本就支持，只缺数据：
- `_a_program.py`：`"program_category": it.get("category") or it.get("program_category") or ""`
- `GtAProgramConsole.vue`：`prop="program_category"` 的「类别」列 + `activeCategory`
  筛选 + `categoryTagType`（已识别 `常规★`/`备选`/含 `IPO`/含 `舞弊`）

🔴 两条不做的事
---------------
1. **不动 `applicable_default`**：`_a_program.py` 只把 `applicable == "na"` 映射成
   `status='not_applicable'`，写 `"no"` 与 `"yes"` 渲染结果相同 = 死配置。
   「按项目属性自动裁剪 IPO 专项程序」属平台级改造。
2. **不删根级 `/G0A`**：顶层共 66 条同族条目（57 条与 `tables` 重复且内容分叉，
   9 条根级独有在运行时不可用），只删 G0 一条会造成不一致 → 平台级 spec。

用法
----
    python backend/scripts/fix/fix_g0a_program_category.py --check
    python backend/scripts/fix/fix_g0a_program_category.py --dry-run
    python backend/scripts/fix/fix_g0a_program_category.py --apply

退出码：0 = 无欠账 / 1 = 有欠账（--check）/ 2 = round-trip 自检失败（不写盘）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_JSON_PATH = _REPO_ROOT / "backend" / "data" / "procedure_table_templates.json"
_XLSX_PATH = _REPO_ROOT / "backend" / "wp_templates" / "G" / "G0 投资循环函证.xlsx"

TABLE_CODE = "G0A"
SHEET_NAME = "函证程序表G0A"

# 源模板 D7:D18 逐字（seq → 程序分类）。守卫会用 openpyxl 直读交叉比对。
PROGRAM_CATEGORY: dict[int, str] = {
    1: "常规★",
    2: "IPO/上市/新三板/重组/舞弊应对",
    3: "常规★",
    4: "常规★",
    5: "常规★",
    6: "常规★",
    7: "备选",
    8: "备选",
    9: "常规★",
    10: "常规★",
    11: "舞弊应对/IPO/上市/新三板/重组",
    12: "常规★",
}


def read_source_categories() -> dict[int, str]:
    """openpyxl 直读源模板 D7:D18 —— 脚本自身也以源 xlsx 为裁决者。"""
    import openpyxl

    wb = openpyxl.load_workbook(_XLSX_PATH, data_only=True)
    ws = wb[SHEET_NAME]
    out: dict[int, str] = {}
    for row in range(7, 19):
        seq_raw = ws.cell(row, 1).value
        category = ws.cell(row, 4).value
        if seq_raw is None:
            continue
        out[int(str(seq_raw).strip())] = str(category).strip() if category else ""
    return out


def plan(data: dict) -> list[tuple[int, str]]:
    """返回待写入的 (seq, program_category)；已正确的不列入。"""
    table = data.get("tables", {}).get(TABLE_CODE)
    if not table:
        raise SystemExit(f"`tables.{TABLE_CODE}` 不存在，源数据结构已变，请复核 spec")
    items = table.get("items") or []
    if len(items) != 12:
        raise SystemExit(f"`tables.{TABLE_CODE}.items` 应为 12 条，实为 {len(items)}")

    changes: list[tuple[int, str]] = []
    for item in items:
        seq = item.get("seq")
        expected = PROGRAM_CATEGORY.get(seq)
        if expected is None:
            raise SystemExit(f"seq={seq!r} 不在源模板分类表内")
        if item.get("program_category") != expected:
            changes.append((seq, expected))
    return changes


def apply_plan(data: dict, changes: list[tuple[int, str]]) -> None:
    by_seq = {c[0]: c[1] for c in changes}
    for item in data["tables"][TABLE_CODE]["items"]:
        if item["seq"] in by_seq:
            item["program_category"] = by_seq[item["seq"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印变更计划，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = _JSON_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    # round-trip 自检：dumps 必须能逐字复现原文，否则整文件写回会造成全文件重排
    reproduced = json.dumps(data, indent=2, ensure_ascii=False)
    if reproduced.strip() != raw.strip():
        print(
            "[FATAL] round-trip 自检失败：json.dumps(indent=2, ensure_ascii=False) "
            f"无法逐字复现原文（{len(reproduced)} vs {len(raw)}），拒绝写盘",
            file=sys.stderr,
        )
        return 2

    # 源模板交叉比对：常量表必须与源 xlsx 一致
    if _XLSX_PATH.exists():
        src = read_source_categories()
        if src != PROGRAM_CATEGORY:
            diff = {k: (PROGRAM_CATEGORY.get(k), v) for k, v in src.items() if PROGRAM_CATEGORY.get(k) != v}
            print(f"[FATAL] 常量表与源模板 D7:D18 不一致（常量, 源）: {diff}", file=sys.stderr)
            return 2
    else:
        print(f"[WARN] 源模板缺失，跳过交叉比对: {_XLSX_PATH}", file=sys.stderr)

    changes = plan(data)

    if not changes:
        print(f"[OK] {TABLE_CODE} program_category 已齐备（12/12），0 项欠账")
        return 0

    print(f"[PLAN] {len(changes)} 项变更：")
    for seq, category in changes:
        print(f"  seq={seq:<3} program_category → {category}")

    if args.check:
        print(f"[FAIL] {len(changes)} 项欠账", file=sys.stderr)
        return 1
    if args.dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    apply_plan(data, changes)
    out = json.dumps(data, indent=2, ensure_ascii=False)
    _JSON_PATH.write_text(out + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    print(f"[APPLIED] 已写入 {_JSON_PATH}")

    # 幂等自检
    again = plan(json.loads(_JSON_PATH.read_text(encoding="utf-8")))
    if again:
        print(f"[FATAL] 幂等自检失败：写盘后仍有 {len(again)} 项欠账", file=sys.stderr)
        return 2
    print("[OK] 幂等自检通过（再次计划 0 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
