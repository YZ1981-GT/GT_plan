#!/usr/bin/env python
"""附注预付款项章节结构对齐源模版（幂等修订）。

**目标**：把附注模板 ``预付款项`` 章节（上市 §五、7 / 国企 §八、7）被压平的
两级表头恢复为源模版结构，消除重名表与「表名即列名」，补齐 ``columns`` /
``guidance`` / 空白明细行骨架。

历史问题：

1. 两版「按账龄」表源模版是两行表头（``期末余额`` / ``上年年末余额`` 各跨
   ``金额`` + ``比例%`` 两列），seed 只留了第一行 ``headers``（3 项），第二行被
   降级成 ``row_type: header_label`` 的**假数据行**；
2. 上市第 3 张表名叫「单位名称」——那是标签列列头，不是表名 → TAB 页签显示列名；
3. 国企第 3 张表**与第 2 张同名**（都叫「账龄超过1年的大额预付款项」）→ 与同步
   载荷键 ``按欠款方归集的期末余额前五名的预付款项`` 错位，形成孤儿子表
   （附注 TAB 永空 + 底稿数据丢失）；
4. 6 张表均无 ``columns``（列元数据）与 ``guidance``（TAB 页签编制提示）；
5. 第 2/3 张表只有 ``合计`` 行，缺源模版的空白明细行骨架。

**权威源**（三者互相印证，冲突裁决见 spec design §二）：

- ``基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/
  4.风险应对-实质性程序（D-N）/F 存货循环/F1 预付账款.xlsx``
  的 ``附注披露信息(上市公司)`` / ``附注披露信息(国企)``
- ``基础数据/附注模版/上市报表附注.md`` / ``国企报表附注.md`` §预付款项
- ``backend/data/note_check_preset_formulas.json`` F7-1~F7-14（listed / soe 双份）

裁决要点：

- 按账龄表 = **5 列**（账龄 + 期末{金额,比例} + 期初{金额,比例}）+ **7 行**
  （各账龄段 + 小计 + 减：减值准备 + 合计）——附注模版与 F7-6/F7-7/F7-8 一致；
  国企源 xlsx 的逐段「坏账准备」列留在**底稿侧**作审计明细，同步时聚合为
  ``减：减值准备`` 行（信息不丢，两侧各守其源）。
- 上市第 2 张表**无**「账龄」「未结算的原因」列（F7-9/F7-10 listed 明确）。
- 上市第 3 张表**无**「减值准备」列（F7-13 listed 明确）。
- 国企第 3 张表第 4 列名为「减值准备」（附注模版 + F7-13 soe），非「坏账准备」。

**行不动原则**：账龄段行集合以源模版默认 3 年段四档为骨架；项目切 5 年段/自定义时
由底稿同步整表覆盖行（``sub_table_data``），seed 只是初始骨架。

Usage::

    python backend/scripts/fix/fix_note_prepayment_structure.py --dry-run
    python backend/scripts/fix/fix_note_prepayment_structure.py
    python backend/scripts/fix/fix_note_prepayment_structure.py --check

spec: .kiro/specs/f1-prepayment-disclosure-template-alignment/ R1
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "f1-prepayment-disclosure-template-alignment"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、7"
SOE_SECTION = "八、7"

# 表名（与 f1DisclosureSyncPayload.ts 的 sub_table_data 键逐字一致）
T_LISTED_AGING = "预付款项按账龄披露"
T_LISTED_OVER1 = "账龄超过1年的重要预付款项"
T_LISTED_TOP5 = "按预付对象归集的预付款项期末余额前五名单位情况"
T_LISTED_TOP5_OBSOLETE = "单位名称"

T_SOE_AGING = "预付款项按账龄列示"
T_SOE_OVER1 = "账龄超过1年的大额预付款项"
T_SOE_TOP5 = "按欠款方归集的期末余额前五名的预付款项"


# ─────────────────────────── 行构造 ───────────────────────────

def _data_row(label: str = "") -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _subtotal_row(label: str = "小计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def _total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _strip_header_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删除 ``header_label`` 行：其语义已由 ``_column_groups`` 承载。"""
    return [r for r in rows if str(r.get("row_type", "")) != "header_label"]


def _blank_rows_then_total(n: int) -> list[dict[str, Any]]:
    return [_data_row() for _ in range(n)] + [_total_row()]


# ─────────────────────────── 列结构 ───────────────────────────

def _aging_patch(end_group: str, prior_group: str, pct_label: str) -> dict[str, Any]:
    """按账龄表：账龄 + {金额, 比例} × 期末/期初两组（5 列两级表头）。"""
    return {
        "headers": ["账龄", "金额", pct_label, "金额", pct_label],
        "columns": [
            {"key": "label", "label": "账龄", "is_label": True},
            {"key": "end_amount", "label": "金额", "group": end_group, "format": "amount"},
            {"key": "end_pct", "label": pct_label, "group": end_group, "format": "percent"},
            {"key": "prior_amount", "label": "金额", "group": prior_group, "format": "amount"},
            {"key": "prior_pct", "label": pct_label, "group": prior_group, "format": "percent"},
        ],
        "_column_groups": [
            {"group": end_group, "start": 1, "span": 2},
            {"group": prior_group, "start": 3, "span": 2},
        ],
    }


LISTED_OVER1_PATCH = {
    "headers": ["债务人名称", "账面余额", "占预付款项合计的比例（%）", "减值准备"],
    "columns": [
        {"key": "label", "label": "债务人名称", "is_label": True, "flat": True},
        {"key": "balance", "label": "账面余额", "format": "amount"},
        {"key": "proportion_pct", "label": "占预付款项合计的比例（%）", "format": "percent"},
        {"key": "impairment", "label": "减值准备", "format": "amount"},
    ],
    "_column_groups": [],
}

LISTED_TOP5_PATCH = {
    "headers": ["单位名称", "预付款项<br/>期末余额", "占预付款项期末余额<br/>合计数的比例%"],
    "columns": [
        {"key": "label", "label": "单位名称", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "预付款项期末余额", "format": "amount"},
        {"key": "proportion_pct", "label": "占预付款项期末余额合计数的比例%", "format": "percent"},
    ],
    "_column_groups": [],
}

SOE_OVER1_PATCH = {
    "headers": ["债权单位", "债务单位", "期末余额", "账龄", "未结算的原因"],
    "columns": [
        {"key": "creditor_unit", "label": "债权单位", "is_label": True, "flat": True},
        {"key": "debtor_unit", "label": "债务单位"},
        {"key": "end_balance", "label": "期末余额", "format": "amount"},
        {"key": "aging", "label": "账龄"},
        {"key": "reason", "label": "未结算的原因"},
    ],
    "_column_groups": [],
}

SOE_TOP5_PATCH = {
    "headers": ["债务人名称", "账面余额", "占预付款项合计的比例（%）", "减值准备"],
    "columns": [
        {"key": "label", "label": "债务人名称", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "账面余额", "format": "amount"},
        {"key": "proportion_pct", "label": "占预付款项合计的比例（%）", "format": "percent"},
        {"key": "impairment", "label": "减值准备", "format": "amount"},
    ],
    "_column_groups": [],
}


# ─────────────────────────── guidance（TAB 页签编制提示） ───────────────────────────
# 只取源模版括注 / 附注模版说明 / 以「勾稽：」前缀标注的 F7-* 校验口径。

LISTED_GUIDANCE = {
    T_LISTED_AGING: (
        "账龄段随项目账龄枚举自动适配（3年段 / 5年段 / 自定义），由 F1-2 明细表审定账龄聚合。"
        "勾稽：各账龄段之和 = 小计行（期末 / 上年年末各独立校验）；合计行 = 小计行 − 减：减值准备行；"
        "比例% = 该行金额 ÷ 小计行金额 × 100（小计行应为 100，减值准备行与合计行不参与比例校验）；"
        "合计行期末金额 = 资产负债表「预付款项」期末数。"
    ),
    T_LISTED_OVER1: (
        "（账龄超过1年的金额重要预付账款，应说明未及时结算的原因。）"
        "勾稽：明细行之和 = 合计行（账面余额列）；合计行账面余额 ≤ 按账龄表 1 年以上各段期末金额之和；"
        "占比 = 该行账面余额 ÷ 按账龄表小计行期末金额 × 100。"
    ),
    T_LISTED_TOP5: (
        "（按预付对象集中度，汇总或分别披露期末余额前五名的预付款项的期末余额及占预付款项期末余额合计数的比例。）"
        "勾稽：明细行之和 = 合计行；合计行余额 ≤ 按账龄表小计行期末金额；"
        "占比 = 该行余额 ÷ 按账龄表小计行期末金额 × 100。"
    ),
}

SOE_GUIDANCE = {
    T_SOE_AGING: (
        "账龄段随项目账龄枚举自动适配（3年段 / 5年段 / 自定义），由 F1-2 明细表审定账龄聚合；"
        "「减：减值准备」行取底稿逐账龄段减值准备之列合计。"
        "勾稽：各账龄段之和 = 小计行（期末 / 期初各独立校验）；合计行 = 小计行 − 减：减值准备行；"
        "比例（%）= 该行金额 ÷ 小计行金额 × 100；合计行期末金额 = 资产负债表「预付款项」期末数。"
    ),
    T_SOE_OVER1: (
        "债务单位 / 期末余额 / 账龄自 F1-5「账龄1年以上的大额预付账款检查表」带入，需补「未结算的原因」。"
        "勾稽：明细行之和 = 合计行（期末余额列）；合计行期末余额 ≤ 按账龄表 1 年以上各段期末金额之和；"
        "完整性：期末余额 ≠ 0 的行，债权单位 / 债务单位 / 账龄 / 未结算的原因均不得为空。"
    ),
    T_SOE_TOP5: (
        "按期末账面余额降序取前五名，自 F1-2 明细表归集。"
        "勾稽：明细行之和 = 合计行（每个数值列独立校验）；合计行账面余额 ≤ 按账龄表小计行期末金额；"
        "合计行减值准备 ≤ 按账龄表减：减值准备行期末金额；占比 = 该行账面余额 ÷ 按账龄表小计行期末金额 × 100。"
    ),
}


# ─────────────────────────── 修订计划 ───────────────────────────
# 按 section.tables 顺序逐条匹配（游标只前进），重名表由位置区分。

def _listed_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": [T_LISTED_AGING],
            "patch": _aging_patch("期末余额", "上年年末余额", "比例%"),
            "rows": "strip",
        },
        {
            "aliases": [T_LISTED_OVER1],
            "patch": LISTED_OVER1_PATCH,
            "rows": "blank3",
        },
        {
            "aliases": [T_LISTED_TOP5_OBSOLETE, T_LISTED_TOP5],
            "new_name": T_LISTED_TOP5,
            "patch": LISTED_TOP5_PATCH,
            "rows": "blank5",
        },
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": [T_SOE_AGING],
            "patch": _aging_patch("期末数", "期初数", "比例（%）"),
            "rows": "strip",
        },
        {
            "aliases": [T_SOE_OVER1],
            "patch": SOE_OVER1_PATCH,
            "rows": "blank5",
        },
        {
            # 第 3 张表与第 2 张同名（seed 缺陷）→ 游标已过第 2 张，按位置命中后改名
            "aliases": [T_SOE_OVER1, T_SOE_TOP5],
            "new_name": T_SOE_TOP5,
            "patch": SOE_TOP5_PATCH,
            "rows": "blank5",
        },
    ]


# 上市源模版「（3）」小节的括注与两种披露格式已在 seed text_sections 中，
# 但缺「说明：」前缀段与国企侧全部说明段 → 仅补缺失项（精确串查重，幂等）。
LISTED_TEXT_ADDITIONS: list[str] = []
LISTED_TEXT_ANCHOR: str | None = None

SOE_TEXT_ADDITIONS = [
    "（账龄超过1年的大额预付款项，应说明未结算的原因。）",
]
SOE_TEXT_ANCHOR = "### 账龄超过1年的大额预付款项"


# ─────────────────────────── 应用 ───────────────────────────

def _rows_for(mode: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if mode == "strip":
        return _strip_header_labels(existing)
    if mode == "blank3":
        return _blank_rows_then_total(3)
    if mode == "blank5":
        return _blank_rows_then_total(5)
    return existing


def _matches(table_name: str, rule: dict[str, Any]) -> bool:
    return table_name in rule["aliases"]


def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def apply_plan(
    section: dict[str, Any],
    plan: list[dict[str, Any]],
    guidance: dict[str, str],
) -> tuple[list[str], list[str]]:
    """按计划就地修订 ``section.tables``。

    Returns:
        (changes, warnings)
    """
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for rule in plan:
        idx = next(
            (i for i in range(cursor, len(tables)) if _matches(str(tables[i].get("name", "")), rule)),
            None,
        )
        if idx is None:
            warnings.append(f"未找到表：{rule['aliases'][-1]}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        new_name = rule.get("new_name")

        if new_name and old_name != new_name:
            dup = next(
                (j for j, t in enumerate(tables) if j != idx and str(t.get("name", "")) == new_name),
                None,
            )
            if dup is not None:
                warnings.append(
                    f"表名迁移跳过：「{old_name}」→「{new_name}」，索引 {dup} 已占用该名（请人工确认）"
                )
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{new_name}」")

        patch = rule["patch"]
        for key in ("headers", "columns", "_column_groups"):
            if key not in patch:
                continue
            want = patch[key]
            if not want and key == "_column_groups":
                # 单级表头：显式清空（seed 若误留分组则删键）
                if tbl.pop(key, None) is not None:
                    changes.append(f"[{idx}] {tbl.get('name')}.{key}：删除（单级表头）")
                continue
            if tbl.get(key) != want:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(want, ensure_ascii=False))
                changes.append(
                    f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(want)} 项"
                )

        rows_mode = rule.get("rows", "keep")
        if rows_mode != "keep":
            old_rows = tbl.get("rows") or []
            new_rows = _rows_for(rows_mode, old_rows)
            if new_rows != old_rows:
                tbl["rows"] = new_rows
                changes.append(
                    f"[{idx}] {tbl.get('name')}.rows：{len(old_rows)} → {len(new_rows)} 行（{rows_mode}）"
                )

        cursor = idx + 1

    for name, text in guidance.items():
        tbl = next((t for t in tables if str(t.get("name", "")) == name), None)
        if tbl is None:
            warnings.append(f"guidance 未落地：找不到表「{name}」")
            continue
        if tbl.get("guidance") != text:
            tbl["guidance"] = text
            changes.append(f"{name}.guidance → {len(text)} 字")

    return changes, warnings


def append_text_sections(
    section: dict[str, Any],
    additions: list[str],
    anchor: str | None,
) -> list[str]:
    """在 anchor 之后插入缺失文本段（精确串查重 → 幂等）。"""
    if not additions:
        return []
    texts: list[str] = section.setdefault("text_sections", [])
    missing = [t for t in additions if t not in texts]
    if not missing:
        return []

    pos = len(texts)
    if anchor and anchor in texts:
        pos = texts.index(anchor) + 1
    texts[pos:pos] = missing
    return [f"text_sections 追加 {len(missing)} 段（位置 {pos}）"]


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

EXPECTED_TABLES = {
    LISTED_SECTION: [T_LISTED_AGING, T_LISTED_OVER1, T_LISTED_TOP5],
    SOE_SECTION: [T_SOE_AGING, T_SOE_OVER1, T_SOE_TOP5],
}


def validate_section(section: dict[str, Any], section_number: str) -> list[str]:
    """结构自洽校验：表名唯一且齐备 / 无 header_label / 列数一致 / 分组不越界不重叠 / guidance 齐备。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i

        headers = tbl.get("headers") or []
        if any(not str(h).strip() for h in headers):
            errs.append(f"[{i}] {name} headers 含空串：{headers}")
        n_val = max(len(headers) - 1, 0)

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != n_val:
                errs.append(f"[{i}] {name} 第 {j} 行 values={len(vals)} ≠ headers-1={n_val}")

        cols = tbl.get("columns")
        if not cols:
            errs.append(f"[{i}] {name} 缺 columns")
        elif len(cols) != len(headers):
            errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
        elif str(cols[0].get("label", "")) != str(headers[0]):
            errs.append(
                f"[{i}] {name} columns[0].label={cols[0].get('label')!r} ≠ headers[0]={headers[0]!r}"
            )

        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"[{i}] {name} 缺 guidance")

        groups = tbl.get("_column_groups")
        if groups:
            occupied: set[int] = set()
            for g in groups:
                start, span = int(g.get("start", 0)), int(g.get("span", 0))
                if start < 1:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」start={start} < 1")
                if start + span > len(headers):
                    errs.append(
                        f"[{i}] {name} 分组「{g.get('group')}」越界：{start}+{span} > {len(headers)}"
                    )
                rng = set(range(start, start + span))
                if rng & occupied:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」区间重叠")
                occupied |= rng

    for want in EXPECTED_TABLES.get(section_number, []):
        if want not in seen:
            errs.append(f"缺表：「{want}」")

    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(
    path: Path,
    section_number: str,
    plan: list[dict[str, Any]],
    guidance: dict[str, str],
    text_additions: list[str],
    text_anchor: str | None,
    *,
    dry_run: bool,
    check_only: bool,
) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    section = _find_section(doc, section_number)
    if section is None:
        return False, [f"[FATAL] {path.name} 未找到 section_number={section_number}"]

    log: list[str] = [f"=== {path.name} §{section_number} {section.get('section_title')} ==="]

    if check_only:
        errs = validate_section(section, section_number)
        log.append(f"_aligned_by={section.get('_aligned_by')!r}")
        if section.get("_aligned_by") != ALIGNED_BY:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_plan(section, plan, guidance)
    changes += append_text_sections(section, text_additions, text_anchor)

    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section, section_number)
    if errs:
        log.append("[FATAL] 修订后结构校验失败，未写入：")
        log.extend(f"  {e}" for e in errs)
        return False, log

    log.append(f"结构校验通过（{len(section.get('tables') or [])} 张表）")

    if dry_run:
        log.append("[dry-run] 未写文件")
        return True, log

    if not changes and section.get("_aligned_by") == ALIGNED_BY:
        log.append("已对齐且无变更，跳过写入")
        return True, log

    _stamp(section)
    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
        encoding="utf-8",
    )
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注预付款项章节结构对齐源模版（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    targets = [
        (LISTED_PATH, LISTED_SECTION, _listed_plan(), LISTED_GUIDANCE,
         LISTED_TEXT_ADDITIONS, LISTED_TEXT_ANCHOR),
        (SOE_PATH, SOE_SECTION, _soe_plan(), SOE_GUIDANCE,
         SOE_TEXT_ADDITIONS, SOE_TEXT_ANCHOR),
    ]

    ok_all = True
    for path, section_number, plan, guidance, texts, anchor in targets:
        ok, log = _process(
            path, section_number, plan, guidance, texts, anchor,
            dry_run=args.dry_run, check_only=args.check,
        )
        print("\n".join(log))
        print()
        ok_all = ok_all and ok

    if not ok_all:
        print("[FAIL] 存在未通过项")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
