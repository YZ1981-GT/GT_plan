#!/usr/bin/env python
"""fix_h0_prefill_presets.py — H0 函证公式预设纠偏（幂等）.

spec: h0-confirmation-source-fidelity-and-linkage · Task 21 / Requirements 11

修正两处：

1. **sheet 名贴错标签** —— 原写 `审定表H0-1`，而源模板
   `backend/wp_templates/H/H0 固定资产循环函证.xlsx` **没有这个 tab**（9 张 sheet 全部
   实证：底稿目录 / 函证程序表H0A / 函证结果汇总表H0-1 / 核实被函证单位信息H0-2 /
   跟函函证过程控制H0-3 / 差异核对表H0-4 / 替代程序H0-5 / 邮件传真回函可靠性验证H0-6 /
   函证程序舞弊风险评价表H0-7）。函证枢纽压根没有审定表 → 该 sheet 名永远匹配不上，
   `page_key='workpaper:H0'` 下的两条预设是死配置。→ 改 `函证结果汇总表H0-1`。

2. **单科目硬编码 `TB('1601')`** —— H0-1 是**九品种**函证汇总（固定资产/在建工程/
   投资性房地产/工程物资/油气资产/固定资产清理/生产性生物资产/使用权资产/租赁负债），
   `1601` 只是固定资产原值。且账面金额已由
   `app/services/four_table/h0_book_amounts.resolve_h0_book_amounts` 在 render 期按
   **本项目科目表**逐品种语义定位后下发（`project_context.h0_book_amounts`），
   实证客户可能用 `1651/1652`(H8) / `2651`(H9) 等非标准码 → 写死任何一个码都会取错。
   → 两条改 `PLACEHOLDER`（沿用 E1 数字货币的既有范式），description 写明取数真源。

用法::

    python backend/scripts/fix/fix_h0_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_h0_prefill_presets.py --check    # exit 1 = 有欠账
    python backend/scripts/fix/fix_h0_prefill_presets.py --apply

🔴 round-trip 自检：脚本先确认 `json.dumps(json.loads(raw))` 能**逐字复现**原文，
   不能复现即 exit 2 拒绝写入（防把并发会话的格式/顺序整体重排）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
H0_XLSX = REPO_ROOT / "backend" / "wp_templates" / "H" / "H0 固定资产循环函证.xlsx"

WP_CODE = "H0"

#: 源模板真实的函证结果汇总表 tab 名。
TARGET_SHEET = "函证结果汇总表H0-1"
OBSOLETE_SHEET = "审定表H0-1"

#: 九品种兜底科目码（仅作展示/参考；运行时取数一律走语义定位，不据此写死）。
#: 与 `four_table/h0_book_amounts.H0_MATRIX_CATEGORY_SPECS` 的品种集合一一对应。
H0_REFERENCE_ACCOUNT_CODES = [
    "1601",  # 固定资产（原值）
    "1604",  # 在建工程
    "1521",  # 投资性房地产
    "1605",  # 工程物资
    "1701",  # 油气资产
    "1606",  # 固定资产清理
    "1621",  # 生产性生物资产
    "1641",  # 使用权资产
    "2601",  # 租赁负债
]

#: 纠偏后的两条 cell 定义。
TARGET_CELLS = [
    {
        "cell_ref": "期初余额",
        "formula": "=PLACEHOLDER('函证品种账面金额（期初）')",
        "formula_type": "PLACEHOLDER",
        "description": (
            "H0-1 函证结果汇总表下区「一、函证情况」的账面金额是**九品种**"
            "（固定资产/在建工程/投资性房地产/工程物资/油气资产/固定资产清理/"
            "生产性生物资产/使用权资产/租赁负债）逐品种口径，不存在单一科目码。"
            "取数真源 = `app/services/four_table/h0_book_amounts.resolve_h0_book_amounts`"
            "（走 semantic_account_resolver 按科目名在**本项目**科目表定位 + 叶子聚合，"
            "原值减各备抵槽），render 期注入 `project_context.h0_book_amounts`。"
            "原写 =TB('1601','期初余额') 只取固定资产原值，且实证客户可能用 1651/1652(H8)、"
            "2651(H9) 等非标准码 → 写死任何一个码都会取错。本项目无某品种科目时前端显示"
            "「本项目无此科目」而非 0。"
        ),
    },
    {
        "cell_ref": "未审数",
        "formula": "=PLACEHOLDER('函证品种账面金额（期末未审）')",
        "formula_type": "PLACEHOLDER",
        "description": "九品种期末账面金额（同上，由 h0_book_amounts 语义定位后 render 下发）",
    },
]


def _load_raw() -> str:
    return MAPPING_PATH.read_text(encoding="utf-8")


def _roundtrip_ok(raw: str) -> bool:
    """json.dumps 能否逐字复现原文（否则写盘会整体重排，拒绝执行）."""
    data = json.loads(raw)
    return json.dumps(data, ensure_ascii=False, indent=2) == raw.rstrip("\n")


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _plan(data: dict) -> tuple[list[str], dict | None]:
    """返回 (变更清单, H0 块引用)。清单为空 = 已达目标状态（幂等）."""
    blocks = [m for m in data["mappings"] if str(m.get("wp_code", "")) == WP_CODE]
    if not blocks:
        return ["[ERROR] prefill_formula_mapping.json 无 H0 块"], None
    if len(blocks) > 1:
        return [f"[ERROR] H0 块重复 {len(blocks)} 个，需人工核对"], None
    blk = blocks[0]

    changes: list[str] = []
    if blk.get("sheet") != TARGET_SHEET:
        changes.append(f"sheet: 「{blk.get('sheet')}」→「{TARGET_SHEET}」")
    if blk.get("account_codes") != H0_REFERENCE_ACCOUNT_CODES:
        changes.append(
            f"account_codes: {blk.get('account_codes')} → 九品种兜底码"
            f"（{len(H0_REFERENCE_ACCOUNT_CODES)} 项，仅作参考）"
        )
    if blk.get("cells") != TARGET_CELLS:
        old = [
            f"{c.get('cell_ref')}={c.get('formula')}" for c in blk.get("cells") or []
        ]
        changes.append(f"cells: {old} → 2 条 PLACEHOLDER（取数改由语义定位下发）")
    return changes, blk


def _verify_target_sheet_exists() -> str | None:
    """校验目标 sheet 名确实在源模板中（防把一个错名换成另一个错名）."""
    try:
        import openpyxl
    except ImportError:
        return None  # 无 openpyxl 时跳过（--check 在 CI 有 openpyxl）
    if not H0_XLSX.exists():
        return f"源模板不存在: {H0_XLSX}"
    names = set(openpyxl.load_workbook(H0_XLSX).sheetnames)
    if TARGET_SHEET not in names:
        return f"目标 sheet「{TARGET_SHEET}」不在源模板中：{sorted(names)}"
    if OBSOLETE_SHEET in names:
        return f"源模板竟存在「{OBSOLETE_SHEET}」→ 本脚本前提失效，请重新核对"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="H0 函证公式预设纠偏（幂等）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="仅打印变更计划（默认）")
    g.add_argument("--check", action="store_true", help="有欠账则 exit 1")
    g.add_argument("--apply", action="store_true", help="写入")
    args = ap.parse_args()

    raw = _load_raw()
    if not _roundtrip_ok(raw):
        print(
            "[FATAL] prefill_formula_mapping.json 无法 round-trip 复现"
            "（缩进/键序与 json.dumps(indent=2) 不一致）→ 拒绝写入以免整体重排。",
            file=sys.stderr,
        )
        return 2

    err = _verify_target_sheet_exists()
    if err:
        print(f"[FATAL] {err}", file=sys.stderr)
        return 2

    data = json.loads(raw)
    total_before = len(data["mappings"])
    changes, blk = _plan(data)

    if blk is None:
        for c in changes:
            print(c, file=sys.stderr)
        return 2

    if not changes:
        print("[OK] H0 预设已达目标状态，0 项欠账")
        return 0

    print(f"[PLAN] H0 预设待修 {len(changes)} 项：")
    for c in changes:
        print(f"  - {c}")

    if args.check:
        return 1
    if not args.apply:
        print("（--dry-run，未写入；加 --apply 执行）")
        return 0

    blk["sheet"] = TARGET_SHEET
    blk["account_codes"] = list(H0_REFERENCE_ACCOUNT_CODES)
    blk["cells"] = json.loads(json.dumps(TARGET_CELLS, ensure_ascii=False))

    # 只触碰 H0 块：块数不变，其余块逐字节不变
    assert len(data["mappings"]) == total_before, "块数变了"
    new_raw = _dump(data)
    old_data = json.loads(raw)
    for i, (old_blk, new_blk) in enumerate(zip(old_data["mappings"], data["mappings"])):
        if str(new_blk.get("wp_code")) == WP_CODE:
            continue
        assert json.dumps(old_blk, ensure_ascii=False, sort_keys=True) == json.dumps(
            new_blk, ensure_ascii=False, sort_keys=True
        ), f"非 H0 块 #{i}({new_blk.get('wp_code')}) 被改动"

    MAPPING_PATH.write_text(new_raw, encoding="utf-8")
    print(f"[APPLIED] 已写入 {MAPPING_PATH}（{len(changes)} 项）")

    # 写后自检：重新读一遍应为 0 欠账（幂等）
    changes2, _ = _plan(json.loads(_load_raw()))
    if changes2:
        print(f"[FATAL] 写后仍有欠账: {changes2}", file=sys.stderr)
        return 2
    print("[OK] 写后复检 0 项欠账（幂等）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
