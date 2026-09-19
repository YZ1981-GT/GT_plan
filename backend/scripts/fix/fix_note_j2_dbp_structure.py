#!/usr/bin/env python
"""幂等修正 J2 设定受益计划附注模板结构（八、54 soe / 五、49 listed / 五、17 listed）。

修正问题（按优先级）：
  八、54（soe）—— 6 处
  五、49（listed）—— 2 处
  五、17（listed）—— 补 columns + guidance

用法：
  python scripts/fix/fix_note_j2_dbp_structure.py --dry-run   # 打印变更不写文件
  python scripts/fix/fix_note_j2_dbp_structure.py --check     # 只校验现状
  python scripts/fix/fix_note_j2_dbp_structure.py             # 执行修正
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    apply_plan,
    build_cli,
    data_row,
    drop_tables,
    ensure_text_sections,
    find_section,
    flat_columns,
    grouped_columns,
    headers_of,
    rule,
    run_section,
    stamp,
    titleize_text_sections,
    total_row,
    validate_section,
)

import json

# ─────────────────────────── 常量 ───────────────────────────

ALIGNED_BY = "j-cycle-four-table-extraction-and-disclosure-alignment"

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SOE_PATH = _DATA_DIR / "note_template_soe.json"
_LISTED_PATH = _DATA_DIR / "note_template_listed.json"

# ─────────────────── 八、54 soe：表/列/行定义 ───────────────────

# tables[0] 长期应付职工薪酬 —— 主表行名修正（源 R7~R9）
SOE_54_TABLE0_ROWS = [
    data_row("设定受益计划净负债"),
    data_row("辞退福利"),
    data_row("一年后支付的辞退福利"),
    total_row("合计"),
]

# tables[1]（删掉两张变动表后的 tables[1]）= 设定受益计划情况（源 R12）
# 7 列：项目 | 设定受益计划义务现值(本期金额/上期金额) | 计划资产的公允价值(本期金额/上期金额) | 设定受益计划净负债（净资产）(本期金额/上期金额)
SOE_54_TABLE1_COLUMNS = grouped_columns(
    ("label", "项目"),
    [
        ("dbo_cur", "本期金额", "amount", "设定受益计划义务现值"),
        ("dbo_prior", "上期金额", "amount", "设定受益计划义务现值"),
        ("asset_cur", "本期金额", "amount", "计划资产的公允价值"),
        ("asset_prior", "上期金额", "amount", "计划资产的公允价值"),
        ("net_cur", "本期金额", "amount", "设定受益计划净负债（净资产）"),
        ("net_prior", "上期金额", "amount", "设定受益计划净负债（净资产）"),
    ],
)

# tables[1] 行集（源 R13~R26 + 补 3 行）
SOE_54_TABLE1_ROWS = [
    data_row("一、期初余额"),
    data_row("二、计入当期损益的设定受益成本"),
    data_row("1．当期服务成本"),
    data_row("2．过去服务成本"),
    data_row("3．结算利得（损失以\"-\"表示）"),
    data_row("4．利息净额"),
    data_row("三、计入其他综合收益的设定受益成本"),
    data_row("设定受益计划净负债（净资产）的重新计量"),  # 源 R23 补入
    data_row("1．精算利得（损失以\"-\"表示）"),
    data_row("2．计划资产的回报（计入利息净额的除外）"),  # 源 R25 补入
    data_row("3．资产上限影响的变动（计入利息净额的除外）"),  # 源 R26 补入
    data_row("四、其他变动"),
    data_row("1．结算时消除的负债"),
    data_row("2．已支付的福利"),
    data_row("……"),
    data_row("五、期末余额"),
]

# 八、54 text_sections[0] 交叉引用修正
SOE_54_TEXT_SECTIONS_CROSS_REF_OLD_PATTERNS = ["八、39", "八、35"]
SOE_54_TEXT_SECTIONS_CROSS_REF_NEW = "八、40"

# 八、54 期望表名清单（删 2 张后的 6 表）
SOE_54_EXPECTED_TABLES = [
    "长期应付职工薪酬",
    "设定受益计划情况",
    "未折现的离职后福利预计到期分析",
    "计划资产",     # 构成表
    "精算假设",
    "敏感性分析",
]

# ─────────────────── 五、49 listed：行集补 2 行 ───────────────────

LISTED_49_TABLE1_ROWS = [
    data_row("一、期初余额"),
    data_row("二、计入当期损益的设定受益成本"),
    data_row("1．当期服务成本"),
    data_row("2．过去服务成本"),
    data_row("3．结算利得（损失以\"-\"表示）"),
    data_row("4．利息净额"),
    data_row("三、计入其他综合收益的设定受益成本"),
    data_row("1．精算利得（损失以\"-\"表示）"),
    data_row("2．计划资产的回报（计入利息净额的除外）"),       # 源 R27 补入
    data_row("3．资产上限影响的变动（计入利息净额的除外）\xa0"),  # 源 R28 含尾 nbsp
    data_row("四、其他变动"),
    data_row("1．结算时消除的负债"),
    data_row("2．已支付的福利"),
    data_row("……"),
    data_row("五、期末余额"),
]

LISTED_49_EXPECTED_TABLES = [
    "长期应付职工薪酬",
    "设定受益计划义务现值：",
    "计划资产：",
    "设定受益计划净负债（净资产）：",
    "未折现的离职后福利预计到期分析：",
    "计划资产",
    "精算假设",
    "敏感性分析",
]

# ─────────────────── 五、17 listed：补 columns + guidance ───────────────────

LISTED_17_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("begin", "期初余额", "amount"),
    ("increase", "本期增加", "amount"),
    ("decrease", "本期减少", "amount"),
    ("end", "期末余额", "amount"),
])

LISTED_17_GUIDANCE = (
    "设定受益计划存在净资产时，按 CAS 9 列示该净资产的期初余额、"
    "本期增减与期末余额（变动口径同「长期应付职工薪酬」章节的变动表）。"
    "不适用的项目删除。"
)

LISTED_17_EXPECTED_TABLES = ["设定受益计划净资产"]


# ═══════════════════════════ 处理函数 ═══════════════════════════


def _fix_soe_54_cross_ref(section: dict) -> list[str]:
    """修正 text_sections[0] 中「八、39」或「八、35」→「八、40」。"""
    ts = section.get("text_sections")
    if not isinstance(ts, list) or not ts:
        return []
    changes: list[str] = []
    first = str(ts[0])
    new_first = first
    for old in SOE_54_TEXT_SECTIONS_CROSS_REF_OLD_PATTERNS:
        if old in new_first:
            new_first = new_first.replace(old, SOE_54_TEXT_SECTIONS_CROSS_REF_NEW)
    if new_first != first:
        ts[0] = new_first
        changes.append(f"text_sections[0]：交叉引用改指「{SOE_54_TEXT_SECTIONS_CROSS_REF_NEW}」")
    return changes


def _run_soe_54(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """处理 八、54 soe 的 6 处修正。"""
    doc = json.loads(_SOE_PATH.read_text(encoding="utf-8"))
    section = find_section(doc, "八、54")
    if section is None:
        return [], ["未找到章节 八、54（note_template_soe.json）"], []

    if check:
        errs: list[str] = []
        tables = section.get("tables") or []
        # 检查是否仍存在应删除的变动表
        for i, t in enumerate(tables):
            name = str(t.get("name", ""))
            rows = t.get("rows") or []
            if name == "计划资产" and len(t.get("columns") or []) == 3 and len(rows) == 9:
                errs.append(f"[{i}] 变动表「计划资产」（rows=9）未删除")
            if name == "设定受益计划净负债（净资产）" and len(rows) == 5 and len(t.get("columns") or []) == 3:
                errs.append(f"[{i}] 变动表「设定受益计划净负债（净资产）」（rows=5）未删除")
        # 检查 tables[1] 改名
        if len(tables) > 1:
            t1_name = str(tables[1].get("name", ""))
            if t1_name == "设定受益计划义务现值":
                errs.append("[1] 表名未改为「设定受益计划情况」")
        # 检查 columns group 正名
        if len(tables) > 1:
            cols = tables[1].get("columns") or []
            if len(cols) >= 7:
                if cols[1].get("group") == "义务现值":
                    errs.append("[1] columns[1].group 未改为「设定受益计划义务现值」")
                if cols[5].get("group") == "设定受益计划净负债":
                    errs.append("[1] columns[5].group 未改为「设定受益计划净负债（净资产）」")
                if cols[1].get("label") == "本期":
                    errs.append("[1] columns[1].label 未改为「本期金额」")
        # 检查行集是否补了 3 行
        if len(tables) > 1:
            rows = tables[1].get("rows") or []
            labels = [str(r.get("label", "")) for r in rows]
            if "设定受益计划净负债（净资产）的重新计量" not in labels:
                errs.append("[1] 缺行「设定受益计划净负债（净资产）的重新计量」")
            if "2．计划资产的回报（计入利息净额的除外）" not in labels:
                errs.append("[1] 缺行「2．计划资产的回报（计入利息净额的除外）」")
            if "3．资产上限影响的变动（计入利息净额的除外）" not in labels:
                errs.append("[1] 缺行「3．资产上限影响的变动（计入利息净额的除外）」")
        # 检查 tables[0] 行名
        if tables:
            t0_rows = tables[0].get("rows") or []
            if t0_rows:
                if str(t0_rows[0].get("label", "")) != "设定受益计划净负债":
                    errs.append(f"[0] rows[0].label 不是「设定受益计划净负债」，现为「{t0_rows[0].get('label')}」")
                if len(t0_rows) > 2 and str(t0_rows[2].get("label", "")) != "一年后支付的辞退福利":
                    errs.append(f"[0] rows[2].label 不是「一年后支付的辞退福利」，现为「{t0_rows[2].get('label')}」")
        # 检查交叉引用
        ts = section.get("text_sections")
        if isinstance(ts, list) and ts:
            first = str(ts[0])
            for old in SOE_54_TEXT_SECTIONS_CROSS_REF_OLD_PATTERNS:
                if old in first:
                    errs.append(f"text_sections[0] 含过时交叉引用「{old}」")
        return [], [], errs

    # ─── 执行修正 ───
    changes: list[str] = []
    warnings: list[str] = []
    tables = section.get("tables") or []

    # 1. 删 tables[2]（变动表「计划资产」rows=9）和 tables[3]（「设定受益计划净负债（净资产）」rows=5）
    #    判据：按位置 + rows 数
    to_remove_indices: list[int] = []
    for i, t in enumerate(tables):
        name = str(t.get("name", ""))
        rows = t.get("rows") or []
        cols_count = len(t.get("columns") or [])
        if name == "计划资产" and cols_count == 3 and len(rows) == 9:
            to_remove_indices.append(i)
            changes.append(f"[{i}] 删除变动表「计划资产」（cols=3, rows=9）")
        elif name == "设定受益计划净负债（净资产）" and len(rows) == 5 and cols_count == 3:
            to_remove_indices.append(i)
            changes.append(f"[{i}] 删除变动表「设定受益计划净负债（净资产）」（cols=3, rows=5）")
    for idx in sorted(to_remove_indices, reverse=True):
        tables.pop(idx)
    section["tables"] = tables

    # 2. tables[1] 改名 → 「设定受益计划情况」
    if len(tables) > 1:
        t1 = tables[1]
        old_name = str(t1.get("name", ""))
        if old_name != "设定受益计划情况":
            t1["name"] = "设定受益计划情况"
            changes.append(f"[1] 表名：「{old_name}」→「设定受益计划情况」")

    # 3. tables[1] columns group 与 leaf label 正名
    if len(tables) > 1:
        t1 = tables[1]
        want_cols = json.loads(json.dumps(SOE_54_TABLE1_COLUMNS, ensure_ascii=False))
        want_headers = headers_of(SOE_54_TABLE1_COLUMNS)
        if t1.get("columns") != want_cols or t1.get("headers") != want_headers:
            t1["columns"] = want_cols
            t1["headers"] = want_headers
            changes.append("[1] columns：group 正名 + 叶子 label 改「本期金额/上期金额」")
        # 派生 _column_groups
        from _note_structure_kit import derive_column_groups
        want_groups = derive_column_groups(SOE_54_TABLE1_COLUMNS)
        if t1.get("_column_groups") != want_groups:
            t1["_column_groups"] = json.loads(json.dumps(want_groups, ensure_ascii=False))
            changes.append("[1] _column_groups 更新（三组两级表头）")

    # 4. tables[1] 行集补 3 行（幂等）
    if len(tables) > 1:
        t1 = tables[1]
        rows = t1.get("rows") or []
        labels = [str(r.get("label", "")) for r in rows]
        need_update = False
        if "设定受益计划净负债（净资产）的重新计量" not in labels:
            need_update = True
        if "2．计划资产的回报（计入利息净额的除外）" not in labels:
            need_update = True
        if "3．资产上限影响的变动（计入利息净额的除外）" not in labels:
            need_update = True
        if need_update:
            t1["rows"] = json.loads(json.dumps(SOE_54_TABLE1_ROWS, ensure_ascii=False))
            changes.append(f"[1] rows：{len(labels)} → {len(SOE_54_TABLE1_ROWS)} 行（补 3 行）")

    # 5. tables[0] 主表行名修正
    if tables:
        t0 = tables[0]
        t0_rows = t0.get("rows") or []
        need_t0_update = False
        if t0_rows:
            if str(t0_rows[0].get("label", "")) != "设定受益计划净负债":
                need_t0_update = True
            if len(t0_rows) > 2 and str(t0_rows[2].get("label", "")) != "一年后支付的辞退福利":
                need_t0_update = True
        if need_t0_update:
            t0["rows"] = json.loads(json.dumps(SOE_54_TABLE0_ROWS, ensure_ascii=False))
            changes.append(f"[0] rows：主表行名修正为源模板 R7~R9 口径")

    # 6. text_sections 交叉引用修正
    changes += _fix_soe_54_cross_ref(section)

    # 写文件
    errs: list[str] = []
    if changes and not dry_run:
        stamp(section, ALIGNED_BY)
        _SOE_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes, warnings, errs


def _run_listed_49(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """处理 五、49 listed 的 2 处修正（tables[1] 补 2 行）。"""
    doc = json.loads(_LISTED_PATH.read_text(encoding="utf-8"))
    section = find_section(doc, "五、49")
    if section is None:
        return [], ["未找到章节 五、49（note_template_listed.json）"], []

    if check:
        errs: list[str] = []
        tables = section.get("tables") or []
        if len(tables) > 1:
            rows = tables[1].get("rows") or []
            labels = [str(r.get("label", "")) for r in rows]
            if "2．计划资产的回报（计入利息净额的除外）" not in labels:
                errs.append("[1] 缺行「2．计划资产的回报（计入利息净额的除外）」")
            if not any("3．资产上限影响的变动" in lbl for lbl in labels):
                errs.append("[1] 缺行「3．资产上限影响的变动（计入利息净额的除外）」")
        return [], [], errs

    # ─── 执行修正 ───
    changes: list[str] = []
    warnings: list[str] = []
    tables = section.get("tables") or []

    # tables[1]（设定受益计划义务现值：）补 2 行
    if len(tables) > 1:
        t1 = tables[1]
        rows = t1.get("rows") or []
        labels = [str(r.get("label", "")) for r in rows]
        need_update = False
        if "2．计划资产的回报（计入利息净额的除外）" not in labels:
            need_update = True
        if not any("3．资产上限影响的变动" in lbl for lbl in labels):
            need_update = True
        if need_update:
            t1["rows"] = json.loads(json.dumps(LISTED_49_TABLE1_ROWS, ensure_ascii=False))
            changes.append(f"[1] rows：{len(labels)} → {len(LISTED_49_TABLE1_ROWS)} 行（补 2 行）")

    # 写文件
    if changes and not dry_run:
        stamp(section, ALIGNED_BY)
        _LISTED_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes, warnings, []


def _run_listed_17(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """处理 五、17 listed：补 columns + guidance。"""
    doc = json.loads(_LISTED_PATH.read_text(encoding="utf-8"))
    section = find_section(doc, "五、17")
    if section is None:
        return [], ["未找到章节 五、17（note_template_listed.json）"], []

    if check:
        errs: list[str] = []
        tables = section.get("tables") or []
        if tables:
            t0 = tables[0]
            cols = t0.get("columns") or []
            if not cols:
                errs.append("[0] 设定受益计划净资产 缺 columns")
            if not str(t0.get("guidance") or "").strip():
                errs.append("[0] 设定受益计划净资产 缺 guidance")
        else:
            errs.append("缺表：设定受益计划净资产")
        aligned = section.get("_aligned_by")
        if aligned != ALIGNED_BY:
            errs.append(f"_aligned_by 未标记（现为 {aligned!r}）")
        return [], [], errs

    # ─── 执行修正 ───
    changes: list[str] = []
    tables = section.get("tables") or []
    if tables:
        t0 = tables[0]
        want_cols = json.loads(json.dumps(LISTED_17_COLUMNS, ensure_ascii=False))
        if t0.get("columns") != want_cols:
            t0["columns"] = want_cols
            t0["headers"] = headers_of(LISTED_17_COLUMNS)
            changes.append("[0] 设定受益计划净资产 补 5 列 flat columns")
        if t0.get("guidance") != LISTED_17_GUIDANCE:
            t0["guidance"] = LISTED_17_GUIDANCE
            changes.append(f"[0] 设定受益计划净资产 补 guidance（{len(LISTED_17_GUIDANCE)} 字）")

    if changes and not dry_run:
        stamp(section, ALIGNED_BY)
        _LISTED_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes, [], []


# ═══════════════════════════ CLI 调度 ═══════════════════════════

_LABELS = {
    "soe_54": "八、54 设定受益计划（国企）",
    "listed_49": "五、49 设定受益计划（上市）",
    "listed_17": "五、17 设定受益计划净资产（上市）",
}


def _runner(key: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    if key == "soe_54":
        return _run_soe_54(dry_run, check)
    elif key == "listed_49":
        return _run_listed_49(dry_run, check)
    elif key == "listed_17":
        return _run_listed_17(dry_run, check)
    return [], [f"未知 key: {key}"], []


main = build_cli(
    description="J2 设定受益计划附注模板结构修正（八、54 / 五、49 / 五、17）",
    runner=_runner,
    labels=_LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
