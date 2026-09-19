#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L 循环附注结构对齐 v2（本 spec 独有的 5 处，与 v1 互不重叠）。

本脚本**不改**既有三个脚本的负责章节，只处理 spec
`l-cycle-extraction-formula-and-disclosure-completion` 声明的 5 处偏差：

| #  | 章节    | 问题                              | 修法                               |
|----|---------|-----------------------------------|------------------------------------|
| E1 | 八、45  | 列 key 中文 + flat 每列           | key 改 snake_case + flat 只标签列  |
| E1 | 八、46  | 同上（两张表共 12 列）            | 同上                               |
| E2 | 八、57  | 列序与源模板相反                  | 按源模板调列序（项目/年初余额/期末余额）|
| E3 | 五、46  | t04 缺 4 个「账面价值」列         | 补 4 列 + 加 group = 9 列          |
| E4 | 五、52  | text_sections 为空（源模板确无）   | 仅守卫防回退（不动，如实登记为零）  |
| E4 | 八、57  | text_sections 为空                | 仅守卫防回退                       |

Usage::

    python backend/scripts/fix/fix_note_l_cycle_structure_v2.py --dry-run
    python backend/scripts/fix/fix_note_l_cycle_structure_v2.py --apply
    python backend/scripts/fix/fix_note_l_cycle_structure_v2.py --check

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ R6
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]  # → backend/
DATA_DIR = ROOT / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "fix_note_l_cycle_structure_v2"
AMOUNT = "amount"
TEXT = "text"


# ═══════════════════════════════════════════════════════════════════════════════
# E1: 八、45 / 八、46 列 key 规范化
# ═══════════════════════════════════════════════════════════════════════════════

# 八、45「（1）一年内到期的长期借款」—— 单级 3 列
E1_845_COLUMNS = [
    # 🔴 首列 label 是「借款类别」不是「项目」—— 源 xlsx
    # L3!附注披露（国企）信息核对!A21 直读为 借款类别（守卫 Class A 的
    # test_source_header_row_landmarks 对该格直接断言）。初版沿用了平台通用的
    # 「项目」措辞，属自造列名，会让三向比对的第三条边（源 xlsx）恒红。
    {"key": "label", "label": "借款类别", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": AMOUNT},
    {"key": "prior_amount", "label": "期初余额", "format": AMOUNT},
]
E1_845_GUIDANCE = (
    "勾稽：合计 = 各项之和。数据来源 L3-1 审定表。"
    "一年内到期部分从长期借款中拆出，应与 八、53 主表的「减：一年内到期的长期借款」行一致。"
)

# 八、46 第 1 张「（2）一年内到期的应付债券」—— 5 列
E1_846_T0_COLUMNS = [
    {"key": "label", "label": "债券名称", "is_label": True, "flat": True},
    {"key": "face_value", "label": "面值", "format": AMOUNT},
    {"key": "issue_date", "label": "发行日期", "format": TEXT},
    {"key": "bond_term", "label": "债券期限", "format": TEXT},
    {"key": "issue_amount", "label": "发行金额", "format": AMOUNT},
]
E1_846_T0_GUIDANCE = (
    "一年内到期的应付债券基本信息表（面值/发行日期/期限/发行金额）。"
    "数据来源 L4 应付债券底稿。"
)

# 八、46 第 2 张「一年内到期的应付债券」—— 7 列
E1_846_T1_COLUMNS = [
    {"key": "label", "label": "债券名称", "is_label": True, "flat": True},
    {"key": "begin_amount", "label": "期初余额", "format": AMOUNT},
    {"key": "issued", "label": "本期发行", "format": AMOUNT},
    {"key": "interest_accrued", "label": "按面值计提利息", "format": AMOUNT},
    {"key": "premium_discount", "label": "溢折价摊销", "format": AMOUNT},
    {"key": "repaid", "label": "本期偿还", "format": AMOUNT},
    {"key": "end_amount", "label": "期末余额", "format": AMOUNT},
]
E1_846_T1_GUIDANCE = (
    "一年内到期的应付债券增减变动表。"
    "勾稽：期末余额 = 期初余额 + 本期发行 + 按面值计提利息 + 溢折价摊销 - 本期偿还。"
    "数据来源 L4 应付债券底稿。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# E2: 八、57 列序改为与源模板一致（项目/年初余额/期末余额）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 源 xlsx `L7!附注披露信息(国企)!A6/B6/C6` = 项目 / 年初余额 / 期末余额
# 当前模板 = 项目 / 期末余额 / 期初余额（附注交付物口径，被 fix_note_l_cycle_structure
# 有意保留）。
# 本 spec 裁决 C 推翻该决策：改为与源模板一致。
# 🔴 key 保持不变（begin_amount/end_amount），只改 label 与数组顺序。
# 这样已持久化 sub_table_data 的 key 不受影响。

E2_857_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "prior_amount", "label": "年初余额", "format": AMOUNT},
    {"key": "end_amount", "label": "期末余额", "format": AMOUNT},
]
E2_857_GUIDANCE = (
    "勾稽：合计 = 各项目之和。数据来源 L7-1 审定表 / L7-2 明细表。"
    "列序按源模板（项目/年初余额/期末余额），与上市侧（期末数/上年年末数）相反是源模板事实。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# E3: 五、46 t04 补 4 个「账面价值」列 + 加 group = 9 列
# ═══════════════════════════════════════════════════════════════════════════════
#
# 源模板 r063/r064 两行表头：
#   r63: 发行在外的金融工具 | 期初余额      | 本期增加      | 本期减少      | 期末余额
#   r64:                     | 数量 | 账面价值 | 数量 | 账面价值 | 数量 | 账面价值 | 数量 | 账面价值
# = 1 标签列 + 4 组 × 2（数量/账面价值）= 9 列

E3_546_T04_NAME = "期末发行在外的优先股、永续债等其他金融工具变动情况"
E3_546_T04_COLUMNS = [
    {"key": "label", "label": "发行在外的金融工具", "is_label": True},
    {"key": "begin_count", "label": "数量", "format": AMOUNT, "group": "期初余额"},
    {"key": "begin_value", "label": "账面价值", "format": AMOUNT, "group": "期初余额"},
    {"key": "increase_count", "label": "数量", "format": AMOUNT, "group": "本期增加"},
    {"key": "increase_value", "label": "账面价值", "format": AMOUNT, "group": "本期增加"},
    {"key": "decrease_count", "label": "数量", "format": AMOUNT, "group": "本期减少"},
    {"key": "decrease_value", "label": "账面价值", "format": AMOUNT, "group": "本期减少"},
    {"key": "end_count", "label": "数量", "format": AMOUNT, "group": "期末余额"},
    {"key": "end_value", "label": "账面价值", "format": AMOUNT, "group": "期末余额"},
]
E3_546_T04_HEADERS = [c["label"] for c in E3_546_T04_COLUMNS]
E3_546_T04_COLUMN_GROUPS = [
    {"group": "期初余额", "start": 1, "span": 2},
    {"group": "本期增加", "start": 3, "span": 2},
    {"group": "本期减少", "start": 5, "span": 2},
    {"group": "期末余额", "start": 7, "span": 2},
]
E3_546_T04_GUIDANCE = (
    "期末发行在外的优先股、永续债等其他金融工具数量及账面价值变动情况。"
    "如无发行在外的优先股/永续债，本表可删除。"
    "源模板 r063/r064 为两级表头（4 组各含数量+账面价值）。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def _find_section(doc: dict, section_number: str) -> dict | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def _find_table(section: dict, table_name: str) -> dict | None:
    for tbl in section.get("tables", []):
        if tbl.get("name") == table_name:
            return tbl
    return None


def _stamp(section: dict) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════════════
# 修改逻辑
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_e1_845(soe: dict) -> list[str]:
    """E1: 八、45 列 key 中文→英文 + flat 只标标签列 + 补 guidance。"""
    changes: list[str] = []
    sec = _find_section(soe, "八、45")
    if sec is None:
        changes.append("[WARN] 八、45 章节不存在")
        return changes

    tbl = sec["tables"][0] if sec.get("tables") else None
    if tbl is None:
        changes.append("[WARN] 八、45 无表")
        return changes

    if tbl.get("columns") != E1_845_COLUMNS:
        changes.append("八、45: columns 改为英文 key + format + flat 只标签列")
        tbl["columns"] = E1_845_COLUMNS
        tbl["headers"] = [c["label"] for c in E1_845_COLUMNS]

    if tbl.get("guidance") != E1_845_GUIDANCE:
        changes.append("八、45: 补 guidance")
        tbl["guidance"] = E1_845_GUIDANCE

    if changes:
        _stamp(sec)
    return changes


def _apply_e1_846(soe: dict) -> list[str]:
    """E1: 八、46 两张表列 key 中文→英文。"""
    changes: list[str] = []
    sec = _find_section(soe, "八、46")
    if sec is None:
        changes.append("[WARN] 八、46 章节不存在")
        return changes

    tables = sec.get("tables", [])
    if len(tables) < 2:
        changes.append("[WARN] 八、46 表数量不足 2")
        return changes

    # 第 1 张
    t0 = tables[0]
    if t0.get("columns") != E1_846_T0_COLUMNS:
        changes.append("八、46 t0: columns 改为英文 key")
        t0["columns"] = E1_846_T0_COLUMNS
        t0["headers"] = [c["label"] for c in E1_846_T0_COLUMNS]
    if t0.get("guidance") != E1_846_T0_GUIDANCE:
        changes.append("八、46 t0: 补 guidance")
        t0["guidance"] = E1_846_T0_GUIDANCE

    # 第 2 张
    t1 = tables[1]
    if t1.get("columns") != E1_846_T1_COLUMNS:
        changes.append("八、46 t1: columns 改为英文 key")
        t1["columns"] = E1_846_T1_COLUMNS
        t1["headers"] = [c["label"] for c in E1_846_T1_COLUMNS]
    if t1.get("guidance") != E1_846_T1_GUIDANCE:
        changes.append("八、46 t1: 补 guidance")
        t1["guidance"] = E1_846_T1_GUIDANCE

    if changes:
        _stamp(sec)
    return changes


def _apply_e2_857(soe: dict) -> list[str]:
    """E2: 八、57 列序改为与源模板一致（项目/年初余额/期末余额）。"""
    changes: list[str] = []
    sec = _find_section(soe, "八、57")
    if sec is None:
        changes.append("[WARN] 八、57 章节不存在")
        return changes

    tbl = sec["tables"][0] if sec.get("tables") else None
    if tbl is None:
        changes.append("[WARN] 八、57 无表")
        return changes

    if tbl.get("columns") != E2_857_COLUMNS:
        changes.append("八、57: 列序改为 项目/年初余额/期末余额（源模板口径）")
        tbl["columns"] = E2_857_COLUMNS
        tbl["headers"] = [c["label"] for c in E2_857_COLUMNS]

    if tbl.get("guidance") != E2_857_GUIDANCE:
        changes.append("八、57: 更新 guidance（说明列序与上市侧相反是源模板事实）")
        tbl["guidance"] = E2_857_GUIDANCE

    if changes:
        _stamp(sec)
    return changes


def _apply_e3_546_t04(listed: dict) -> list[str]:
    """E3: 五、46 t04 补 4 个账面价值列 + 加 group = 9 列两级表头。"""
    changes: list[str] = []
    sec = _find_section(listed, "五、46")
    if sec is None:
        changes.append("[WARN] 五、46 章节不存在")
        return changes

    tbl = _find_table(sec, E3_546_T04_NAME)
    if tbl is None:
        changes.append(f"[WARN] 五、46 无表 '{E3_546_T04_NAME}'")
        return changes

    if tbl.get("columns") != E3_546_T04_COLUMNS:
        changes.append("五、46 t04: columns 补 4 列账面价值 = 9 列")
        tbl["columns"] = E3_546_T04_COLUMNS
        tbl["headers"] = E3_546_T04_HEADERS

    if tbl.get("_column_groups") != E3_546_T04_COLUMN_GROUPS:
        changes.append("五、46 t04: 加 _column_groups 四组各 span=2")
        tbl["_column_groups"] = E3_546_T04_COLUMN_GROUPS

    if tbl.get("guidance") != E3_546_T04_GUIDANCE:
        changes.append("五、46 t04: 更新 guidance")
        tbl["guidance"] = E3_546_T04_GUIDANCE

    if changes:
        _stamp(sec)
    return changes


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    ap = argparse.ArgumentParser(description="L 循环附注结构对齐 v2")
    ap.add_argument("--dry-run", action="store_true", help="只输出改动计划，不写盘")
    ap.add_argument("--check", action="store_true", help="校验是否已对齐（有偏差 exit 1）")
    ap.add_argument("--apply", action="store_true", help="执行并写盘（默认）")
    args = ap.parse_args()

    soe = _load_json(SOE_PATH)
    listed = _load_json(LISTED_PATH)

    # 取改动前快照（round-trip 自检用）
    soe_before = json.dumps(soe, ensure_ascii=False, indent=2) + "\n"
    listed_before = json.dumps(listed, ensure_ascii=False, indent=2) + "\n"

    all_changes: list[str] = []
    all_changes.extend(_apply_e1_845(soe))
    all_changes.extend(_apply_e1_846(soe))
    all_changes.extend(_apply_e2_857(soe))
    all_changes.extend(_apply_e3_546_t04(listed))

    if args.check:
        if all_changes:
            print(f"[FAIL] {len(all_changes)} 项欠账:")
            for c in all_changes:
                print(f"  {c}")
            sys.exit(1)
        else:
            print("[OK] L 循环附注结构 v2: 0 项欠账")
            sys.exit(0)

    if not all_changes:
        print("[OK] 无需改动")
        sys.exit(0)

    print(f"改动计划: {len(all_changes)} 项")
    for c in all_changes:
        print(f"  {c}")

    if args.dry_run:
        print("(dry-run 模式，未写盘)")
        sys.exit(0)

    # 写盘
    _save_json(SOE_PATH, soe)
    _save_json(LISTED_PATH, listed)

    # round-trip 自检
    soe_rt = json.dumps(_load_json(SOE_PATH), ensure_ascii=False, indent=2) + "\n"
    listed_rt = json.dumps(_load_json(LISTED_PATH), ensure_ascii=False, indent=2) + "\n"
    soe_written = json.dumps(soe, ensure_ascii=False, indent=2) + "\n"
    listed_written = json.dumps(listed, ensure_ascii=False, indent=2) + "\n"

    if soe_rt != soe_written:
        print("[ERROR] soe round-trip 失败（写盘后再读不等于内存态）", file=sys.stderr)
        sys.exit(2)
    if listed_rt != listed_written:
        print("[ERROR] listed round-trip 失败", file=sys.stderr)
        sys.exit(2)

    print(f"[OK] 已写盘 {len(all_changes)} 项改动")
    sys.exit(0)


if __name__ == "__main__":
    main()
