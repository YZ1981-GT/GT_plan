"""D4（4）分解信息表附注模板结构对齐（幂等）。

背景（spec `d-cycle-four-table-extraction-and-disclosure-completion` Task 31）
==========================================================================

源 xlsx 权威模板 `backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表
（Leap-常规程序）.xlsx` 实证：

- 上市 `附注披露信息（上市公司）` R44~R56
- 国企 `附注披露信息（国企）`     R37~R49

两版**逐行同构**，行集 9 行：

    主营业务            （派生小计，上市 R48 `=SUM(B49:B51)`）
    其中：在某一时点确认
    　　　在某一时段确认
    （空可扩行）        （上市 R51 / 国企 R44，**在小计 SUM 范围内**）
    其他业务            （派生小计，上市 R52 `=SUM(B53:B55)`）
    其中：在某一时点确认
    　　　在某一时段确认
    　　　租赁收入
    合　计              （派生总计，上市 R56 `=B52+B48`）

列集 9 列：`label` + 4 类别 × {收入, 成本}，**没有横向合计列**。

本脚本修两处
------------

1. **行集** 6 行 → 9 行（补两个业务父行的 `row_type=subtotal`、空可扩行、
   租赁收入行、合计行）。
2. **列 key** `cat0_revenue` → `cat_1_revenue` —— 与前端
   `buildD4TransposeColumns` 产出逐字同构（0-based 无下划线 vs 1-based 带下划线
   是 seed 路径与推送路径的分叉，切换时已录 seed 数据会失联）。

用法
====

    python backend/scripts/fix/fix_note_d4_segment_structure.py            # dry-run
    python backend/scripts/fix/fix_note_d4_segment_structure.py --check    # 0=无欠账
    python backend/scripts/fix/fix_note_d4_segment_structure.py --apply

Requirements: 7.5
Property: 25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────── 源模板实证（真源）

TARGETS = {
    "listed": {
        "file": "note_template_listed.json",
        "section_number": "五、62",
        "table_name": "营业收入、营业成本按分解信息",
        "label_header": "项目",
    },
    "soe": {
        "file": "note_template_soe.json",
        "section_number": "八、64",
        "table_name": "营业收入分解信息",
        "label_header": "合同分类/报告分部",
    },
}

# 类别默认名（源 xlsx 上市 B46:I46 / 国企 B39:I39 的示例四类）
DEFAULT_CATEGORIES = [
    ("cat_1", "消费品"),
    ("cat_2", "汽车"),
    ("cat_3", "能源"),
    ("cat_4", "其他"),
]

# 行集（label, row_type）—— 逐字取自源 xlsx，含缩进空格
SOURCE_ROWS: list[tuple[str, str]] = [
    ("主营业务", "subtotal"),
    ("其中：在某一时点确认", "data"),
    ("      在某一时段确认", "data"),
    ("", "data"),  # 空可扩行（源 R51 / R44）
    ("其他业务", "subtotal"),
    ("其中：在某一时点确认", "data"),
    ("      在某一时段确认", "data"),
    ("      租赁收入", "data"),
    ("合  计", "total"),
]

# 🔴 guidance 一律纯文本：TAB 提示与 Word 导出都不解析 markdown，且平台级
#    `fix_note_bold_markers.py` 会把 `**` 剥掉 —— 写了就会两个脚本互相打架。
GUIDANCE = (
    "源模板：上市 R44~R56 / 国企 R37~R49。列 = 4 个分解类别（可增删改名），"
    "各辖「收入 / 成本」；无横向合计列，合计是最后一行。"
    "「主营业务」「其他业务」为派生小计（源模板 SUM 公式），"
    "其下第 3 行为空可扩行且计入小计；「合  计」= 两个小计之和。"
    "分解类别应与内部管理报告一致；租赁收入需单独披露。"
)


def repo_root() -> Path:
    sentinels = (
        Path("backend") / "data" / "note_template_listed.json",
        Path("audit-platform") / "frontend" / "package.json",
    )
    cur = Path(__file__).resolve()
    for cand in [cur, *cur.parents]:
        if all((cand / s).exists() for s in sentinels):
            return cand
    raise SystemExit("未能定位仓库根（双哨兵均需存在）")


def expected_columns(label_header: str) -> list[dict]:
    cols: list[dict] = [
        {"key": "label", "label": label_header, "is_label": True, "flat": True}
    ]
    for key, label in DEFAULT_CATEGORIES:
        cols.append(
            {"key": f"{key}_revenue", "label": "收入", "group": label, "format": "amount"}
        )
        cols.append(
            {"key": f"{key}_cost", "label": "成本", "group": label, "format": "amount"}
        )
    return cols


def expected_headers(label_header: str) -> list[str]:
    out = [label_header]
    for _ in DEFAULT_CATEGORIES:
        out.extend(["收入", "成本"])
    return out


def expected_rows() -> list[dict]:
    return [{"label": label, "row_type": rt} for label, rt in SOURCE_ROWS]


def plan(root: Path) -> list[str]:
    """返回欠账清单（空 = 已对齐）。"""
    issues: list[str] = []
    for variant, spec in TARGETS.items():
        path = root / "backend" / "data" / spec["file"]
        data = json.loads(path.read_text(encoding="utf-8"))
        secs = [
            s
            for s in data.get("sections", [])
            if (s.get("section_number") or "").strip() == spec["section_number"]
        ]
        if len(secs) != 1:
            issues.append(
                f"[{variant}] 章节 {spec['section_number']!r} 命中 {len(secs)} 条（期望 1）"
            )
            continue
        tables = secs[0].get("tables") or []
        hit = [t for t in tables if (t.get("name") or "") == spec["table_name"]]
        if len(hit) != 1:
            issues.append(
                f"[{variant}] 子表 {spec['table_name']!r} 命中 {len(hit)} 条（期望 1）"
            )
            continue
        t = hit[0]

        exp_cols = expected_columns(spec["label_header"])
        if (t.get("columns") or []) != exp_cols:
            got = [c.get("key") for c in (t.get("columns") or [])]
            issues.append(
                f"[{variant}] columns 不符：期望 {[c['key'] for c in exp_cols]}，实为 {got}"
            )
        if (t.get("headers") or []) != expected_headers(spec["label_header"]):
            issues.append(f"[{variant}] headers 不符：实为 {t.get('headers')}")

        exp_rows = expected_rows()
        got_rows = [
            {"label": r.get("label", ""), "row_type": r.get("row_type", "data")}
            for r in (t.get("rows") or [])
        ]
        if got_rows != exp_rows:
            issues.append(
                f"[{variant}] rows 不符：期望 {len(exp_rows)} 行，实为 {len(got_rows)} 行"
                f" → {[r['label'] for r in got_rows]}"
            )
        if (t.get("guidance") or "") != GUIDANCE:
            issues.append(f"[{variant}] guidance 未对齐")
    return issues


def apply(root: Path) -> list[str]:
    changes: list[str] = []
    for variant, spec in TARGETS.items():
        path = root / "backend" / "data" / spec["file"]
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)

        # round-trip 自检：确保 json.dumps 能逐字复现原文（防全文件重排）
        probe = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if probe != raw:
            print(
                f"[ERR] {spec['file']} round-trip 不一致（缩进/尾换行与 json.dumps 不同）"
                "，拒绝写回以避免全文件重排",
                file=sys.stderr,
            )
            raise SystemExit(2)

        secs = [
            s
            for s in data.get("sections", [])
            if (s.get("section_number") or "").strip() == spec["section_number"]
        ]
        if len(secs) != 1:
            print(f"[ERR] {variant}: 章节命中 {len(secs)} 条", file=sys.stderr)
            raise SystemExit(2)
        tables = secs[0].get("tables") or []
        hit = [t for t in tables if (t.get("name") or "") == spec["table_name"]]
        if len(hit) != 1:
            print(f"[ERR] {variant}: 子表命中 {len(hit)} 条", file=sys.stderr)
            raise SystemExit(2)
        t = hit[0]

        t["columns"] = expected_columns(spec["label_header"])
        t["headers"] = expected_headers(spec["label_header"])
        t["rows"] = expected_rows()
        t["guidance"] = GUIDANCE
        changes.append(f"[{variant}] {spec['table_name']}: columns/headers/rows/guidance 已对齐源模板")

        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description="D4（4）分解信息表附注模板结构对齐（幂等）")
    ap.add_argument("--apply", action="store_true", help="写回模板 JSON")
    ap.add_argument("--check", action="store_true", help="只检查，返回欠账数为退出码")
    args = ap.parse_args()

    root = repo_root()
    issues = plan(root)

    if args.check:
        for i in issues:
            print(f"  - {i}")
        print(f"[CHECK] 欠账 {len(issues)} 项")
        return 1 if issues else 0

    if not args.apply:
        print("[DRY-RUN] 欠账清单：")
        for i in issues:
            print(f"  - {i}")
        print(f"共 {len(issues)} 项（加 --apply 写回）")
        return 0

    if not issues:
        print("[OK] 已对齐，无需改动（幂等）")
        return 0

    changes = apply(root)
    for c in changes:
        print(f"  * {c}")
    left = plan(root)
    print(f"[OK] 已写回；复查欠账 {len(left)} 项")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())
