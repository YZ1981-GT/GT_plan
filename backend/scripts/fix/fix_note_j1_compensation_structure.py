"""幂等脚本：修正 J1 应付职工薪酬附注模板结构（五、40 上市 / 八、40 国企）。

修正 4 处问题：
1. 五、40 三张表列头改上市口径：headers[1]→`上年年末数`，headers[4]→`期末数`；
   同时改 columns 的 label（key 不变）
2. 五、40 表[1]「短期薪酬」补源 R24 的 `……` 可扩行：
   在「3．生育保险费」之后、「住房公积金」之前插入一行
3. 八、40 表[1]「短期薪酬列示」行集修正：
   `医疗保险费及生育保险费` → `医疗保险费`（不含「及生育保险费」），
   并在「工伤保险费」之后新增「生育保险费」行（源模板 4 项而非 3 项）
4. 五、40 表[2]「设定提存计划」的「其中：」层补序号：
   `其中：基本养老保险费` → `其中：1．基本养老保险费`
   `失业保险费` → `2．失业保险费`
   `企业年金缴费` → `3．企业年金缴费`
   `其他` → `4．其他`（仅「设定提存计划」下的第一个「其他」）

用法：
    python scripts/fix/fix_note_j1_compensation_structure.py --dry-run
    python scripts/fix/fix_note_j1_compensation_structure.py --check
    python scripts/fix/fix_note_j1_compensation_structure.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALIGNED_BY = "j-cycle-four-table-extraction-and-disclosure-alignment"

BASE = Path(__file__).resolve().parent.parent.parent  # backend/
LISTED_PATH = BASE / "data" / "note_template_listed.json"
SOE_PATH = BASE / "data" / "note_template_soe.json"

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# `row_type` 判据单一真源：`……` 是源模板可扩位（零可见内容），禁硬编码 "data"，
# 否则与 `fix_note_expandable_rows.py` 互相翻转。
from app.services.note_expandable_markers import (  # noqa: E402
    row_type_for_label as _row_type_for_label,
)

# ─────────────────── 列头目标态 ───────────────────

# 五、40 三张表列头（R6 口径）
LISTED_HEADERS_OLD = ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]
LISTED_HEADERS_NEW = ["项目", "上年年末数", "本期增加", "本期减少", "期末数"]

# columns label 对应修改：key 不变！
LISTED_COL_LABEL_MAP = {
    "期初余额": "上年年末数",
    "期末余额": "期末数",
}

# ─────── 五、40 表[1]「短期薪酬」插入行 ─────────

LISTED_SHORT_INSERT_AFTER = "3．生育保险费"
LISTED_SHORT_INSERT_BEFORE = "住房公积金"
LISTED_SHORT_INSERT_ROW = {"label": "……", "row_type": _row_type_for_label("……")}

# ─────── 八、40 表[1]「短期薪酬列示」行集修正 ─────

SOE_SHORT_OLD_LABEL = "其中：医疗保险费及生育保险费"
SOE_SHORT_NEW_LABEL = "其中：医疗保险费"
SOE_SHORT_INSERT_AFTER = "工伤保险费"
SOE_SHORT_INSERT_ROW = {"label": "生育保险费", "row_type": "data"}

# ─────── 五、40 表[2]「设定提存计划」序号补齐 ────

DC_PLAN_RENAMES = [
    ("其中：基本养老保险费", "其中：1．基本养老保险费"),
    ("失业保险费", "2．失业保险费"),
    ("企业年金缴费", "3．企业年金缴费"),
    # 第一个「其他」（紧跟企业年金缴费）→「4．其他」
]
DC_PLAN_OTHER_OLD = "其他"
DC_PLAN_OTHER_NEW = "4．其他"


# ─────────────────── 工具函数 ───────────────────

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_section(doc: dict, section_number: str) -> dict | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


# ─────────────────── 修正函数 ───────────────────

def fix_listed_headers(section: dict, dry_run: bool) -> list[str]:
    """修正 1：五、40 三张表的列头 headers + columns.label。"""
    changes: list[str] = []
    tables = section.get("tables", [])
    for i, tbl in enumerate(tables):
        name = tbl.get("name", "")
        # headers 修正
        headers = tbl.get("headers", [])
        if headers == LISTED_HEADERS_OLD:
            if not dry_run:
                tbl["headers"] = list(LISTED_HEADERS_NEW)
            changes.append(f"[{i}] {name} headers: 期初余额→上年年末数, 期末余额→期末数")
        elif headers == LISTED_HEADERS_NEW:
            pass  # 已改过
        else:
            # 逐个检查
            modified = False
            new_headers = list(headers)
            if len(headers) >= 5:
                if headers[1] == "期初余额":
                    new_headers[1] = "上年年末数"
                    modified = True
                if headers[4] == "期末余额":
                    new_headers[4] = "期末数"
                    modified = True
            if modified:
                if not dry_run:
                    tbl["headers"] = new_headers
                changes.append(f"[{i}] {name} headers 部分修正")

        # columns label 修正（key 不变！）
        cols = tbl.get("columns", [])
        for ci, col in enumerate(cols):
            old_label = col.get("label", "")
            new_label = LISTED_COL_LABEL_MAP.get(old_label)
            if new_label:
                if not dry_run:
                    col["label"] = new_label
                changes.append(f"[{i}] {name} columns[{ci}].label: {old_label!r}→{new_label!r}")
    return changes


def fix_listed_short_term_insert(section: dict, dry_run: bool) -> list[str]:
    """修正 2：五、40 表[1]「短期薪酬」补 `……` 可扩行。"""
    changes: list[str] = []
    tables = section.get("tables", [])
    if len(tables) < 2:
        return changes
    tbl = tables[1]
    if tbl.get("name") != "短期薪酬":
        return changes
    rows = tbl.get("rows", [])

    # 检查是否已有 `……` 行在正确位置
    after_idx = next((i for i, r in enumerate(rows) if r.get("label") == LISTED_SHORT_INSERT_AFTER), None)
    before_idx = next((i for i, r in enumerate(rows) if r.get("label") == LISTED_SHORT_INSERT_BEFORE), None)

    if after_idx is None or before_idx is None:
        return changes

    # 检查中间是否已存在 `……` 行
    if before_idx == after_idx + 2:
        mid = rows[after_idx + 1]
        if mid.get("label") == "……":
            return changes  # 已存在

    if before_idx == after_idx + 1:
        # 紧邻 → 需要插入
        if not dry_run:
            rows.insert(after_idx + 1, dict(LISTED_SHORT_INSERT_ROW))
        changes.append(f"[1] 短期薪酬：在「{LISTED_SHORT_INSERT_AFTER}」后插入「……」可扩行")

    return changes


def fix_soe_short_term_rows(section: dict, dry_run: bool) -> list[str]:
    """修正 3：八、40 表[1]「短期薪酬列示」行集修正。"""
    changes: list[str] = []
    tables = section.get("tables", [])
    if len(tables) < 2:
        return changes
    tbl = tables[1]
    if tbl.get("name") != "短期薪酬列示":
        return changes
    rows = tbl.get("rows", [])

    # 3a: 改名 `医疗保险费及生育保险费` → `医疗保险费`
    for r in rows:
        if r.get("label") == SOE_SHORT_OLD_LABEL:
            if not dry_run:
                r["label"] = SOE_SHORT_NEW_LABEL
            changes.append(f"[1] 短期薪酬列示：「{SOE_SHORT_OLD_LABEL}」→「{SOE_SHORT_NEW_LABEL}」")
            break

    # 3b: 在「工伤保险费」后插入「生育保险费」（如果还没有）
    # 先检查是否已有「生育保险费」行
    has_shengyu = any(r.get("label") == "生育保险费" for r in rows)
    if not has_shengyu:
        insert_idx = next(
            (i for i, r in enumerate(rows) if r.get("label") == SOE_SHORT_INSERT_AFTER),
            None,
        )
        if insert_idx is not None:
            if not dry_run:
                rows.insert(insert_idx + 1, dict(SOE_SHORT_INSERT_ROW))
            changes.append(f"[1] 短期薪酬列示：在「{SOE_SHORT_INSERT_AFTER}」后插入「生育保险费」")

    return changes


def fix_listed_dc_plan_numbering(section: dict, dry_run: bool) -> list[str]:
    """修正 4：五、40 表[2]「设定提存计划」其中层补序号。"""
    changes: list[str] = []
    tables = section.get("tables", [])
    if len(tables) < 3:
        return changes
    tbl = tables[2]
    if tbl.get("name") != "设定提存计划":
        return changes
    rows = tbl.get("rows", [])

    # 按旧 label 改名
    for old, new in DC_PLAN_RENAMES:
        for r in rows:
            if r.get("label") == old:
                if not dry_run:
                    r["label"] = new
                changes.append(f"[2] 设定提存计划：「{old}」→「{new}」")
                break

    # 特殊处理第一个「其他」（紧跟在「企业年金缴费」/「3．企业年金缴费」之后的）
    # 找到「企业年金缴费」或「3．企业年金缴费」的位置
    qynj_idx = next(
        (i for i, r in enumerate(rows)
         if r.get("label") in ("企业年金缴费", "3．企业年金缴费")),
        None,
    )
    if qynj_idx is not None and qynj_idx + 1 < len(rows):
        next_row = rows[qynj_idx + 1]
        if next_row.get("label") == DC_PLAN_OTHER_OLD:
            if not dry_run:
                next_row["label"] = DC_PLAN_OTHER_NEW
            changes.append(f"[2] 设定提存计划：「{DC_PLAN_OTHER_OLD}」（首个）→「{DC_PLAN_OTHER_NEW}」")

    return changes


# ─────────────────── 校验函数 ───────────────────

def check_listed(section: dict) -> list[str]:
    """校验五、40 修正是否已到位。"""
    errs: list[str] = []
    tables = section.get("tables", [])

    # 检查 1: 三张表列头
    for i, tbl in enumerate(tables):
        name = tbl.get("name", "")
        headers = tbl.get("headers", [])
        if len(headers) >= 5:
            if headers[1] != "上年年末数":
                errs.append(f"[{i}] {name} headers[1]={headers[1]!r}, 期望「上年年末数」")
            if headers[4] != "期末数":
                errs.append(f"[{i}] {name} headers[4]={headers[4]!r}, 期望「期末数」")
        # columns label
        cols = tbl.get("columns", [])
        for ci, col in enumerate(cols):
            label = col.get("label", "")
            if label == "期初余额":
                errs.append(f"[{i}] {name} columns[{ci}].label=「期初余额」, 期望「上年年末数」")
            if label == "期末余额":
                errs.append(f"[{i}] {name} columns[{ci}].label=「期末余额」, 期望「期末数」")

    # 检查 2: 短期薪酬 `……` 行
    if len(tables) >= 2 and tables[1].get("name") == "短期薪酬":
        rows = tables[1].get("rows", [])
        after_idx = next((i for i, r in enumerate(rows) if r.get("label") == LISTED_SHORT_INSERT_AFTER), None)
        before_idx = next((i for i, r in enumerate(rows) if r.get("label") == LISTED_SHORT_INSERT_BEFORE), None)
        if after_idx is not None and before_idx is not None:
            if before_idx == after_idx + 1:
                errs.append("[1] 短期薪酬：「3．生育保险费」与「住房公积金」之间缺「……」可扩行")
            elif before_idx == after_idx + 2:
                mid = rows[after_idx + 1]
                if mid.get("label") != "……":
                    errs.append(f"[1] 短期薪酬：中间行 label={mid.get('label')!r}, 期望「……」")

    # 检查 4: 设定提存计划序号
    if len(tables) >= 3 and tables[2].get("name") == "设定提存计划":
        rows = tables[2].get("rows", [])
        expected_labels = {
            "其中：1．基本养老保险费",
            "2．失业保险费",
            "3．企业年金缴费",
            "4．其他",
        }
        actual_labels = {r.get("label") for r in rows}
        for exp in expected_labels:
            if exp not in actual_labels:
                errs.append(f"[2] 设定提存计划：缺行「{exp}」")
        # 旧名不应存在
        old_labels = {"其中：基本养老保险费", "失业保险费", "企业年金缴费"}
        for old in old_labels:
            if old in actual_labels:
                errs.append(f"[2] 设定提存计划：旧名仍在「{old}」")

    return errs


def check_soe(section: dict) -> list[str]:
    """校验八、40 修正是否已到位。"""
    errs: list[str] = []
    tables = section.get("tables", [])

    # 检查 3: 短期薪酬列示行集
    if len(tables) >= 2 and tables[1].get("name") == "短期薪酬列示":
        rows = tables[1].get("rows", [])
        labels = [r.get("label") for r in rows]

        if SOE_SHORT_OLD_LABEL in labels:
            errs.append(f"[1] 短期薪酬列示：旧名仍在「{SOE_SHORT_OLD_LABEL}」")
        if SOE_SHORT_NEW_LABEL not in labels:
            errs.append(f"[1] 短期薪酬列示：缺行「{SOE_SHORT_NEW_LABEL}」")
        if "生育保险费" not in labels:
            errs.append("[1] 短期薪酬列示：缺行「生育保险费」")
        if "工伤保险费" not in labels:
            errs.append("[1] 短期薪酬列示：缺行「工伤保险费」")

        # 验证顺序：医疗 < 工伤 < 生育 < 其他
        expected_order = ["其中：医疗保险费", "工伤保险费", "生育保险费", "其他"]
        positions = []
        for exp in expected_order:
            pos = next((i for i, l in enumerate(labels) if l == exp), None)
            if pos is not None:
                positions.append(pos)
        if positions and positions != sorted(positions):
            errs.append("[1] 短期薪酬列示：「其中：」四项顺序不正确")

    return errs


# ─────────────────── 主流程 ───────────────────

def run_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str]]:
    doc = load_json(LISTED_PATH)
    section = find_section(doc, "五、40")
    if section is None:
        return [], ["未找到章节 五、40"]

    if check:
        errs = check_listed(section)
        return [], errs

    changes: list[str] = []
    changes += fix_listed_headers(section, dry_run)
    changes += fix_listed_short_term_insert(section, dry_run)
    changes += fix_listed_dc_plan_numbering(section, dry_run)

    if changes and not dry_run:
        # stamp
        import datetime
        section["_aligned_by"] = ALIGNED_BY
        section["_aligned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_json(LISTED_PATH, doc)

    return changes, []


def run_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str]]:
    doc = load_json(SOE_PATH)
    section = find_section(doc, "八、40")
    if section is None:
        return [], ["未找到章节 八、40"]

    if check:
        errs = check_soe(section)
        return [], errs

    changes: list[str] = []
    changes += fix_soe_short_term_rows(section, dry_run)

    if changes and not dry_run:
        import datetime
        section["_aligned_by"] = ALIGNED_BY
        section["_aligned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_json(SOE_PATH, doc)

    return changes, []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="修正 J1 应付职工薪酬附注模板结构（五、40 / 八、40）"
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写文件")
    ap.add_argument("--check", action="store_true", help="只校验现状，有欠账 exit 1")
    args = ap.parse_args()

    total_changes = 0
    total_errs = 0

    # 五、40 上市
    print("\n=== 五、40（上市）===")
    changes, errs = run_listed(args.dry_run, args.check)
    for c in changes:
        print(f"  ~ {c}")
    for e in errs:
        print(f"  x {e}")
    if not changes and not errs:
        print("  = 已对齐（幂等空操作）")
    total_changes += len(changes)
    total_errs += len(errs)

    # 八、40 国企
    print("\n=== 八、40（国企）===")
    changes, errs = run_soe(args.dry_run, args.check)
    for c in changes:
        print(f"  ~ {c}")
    for e in errs:
        print(f"  x {e}")
    if not changes and not errs:
        print("  = 已对齐（幂等空操作）")
    total_changes += len(changes)
    total_errs += len(errs)

    if args.check:
        print(f"\n--check：{total_errs} 项欠账")
        return 1 if total_errs else 0
    print(
        f"\n{'[dry-run] ' if args.dry_run else ''}共 {total_changes} 处变更，"
        f"{total_errs} 项问题"
    )
    return 1 if total_errs else 0


if __name__ == "__main__":
    sys.exit(main())
