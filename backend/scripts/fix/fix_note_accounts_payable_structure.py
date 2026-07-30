#!/usr/bin/env python
"""附注应付账款章节结构对齐源模版（幂等修订）。

**目标**：把附注模板中应付账款章节的表名 / 行集合 / 列结构 / TAB 编制提示
对齐两个权威源，消除 md 重建产物留下的假表名与占位行。

历史问题：

1. 上市 §五、37 第二张表 ``name`` 被写成 ``"项  目"``——那是 md 表格的**首个表头
   单元格**，不是表名；真名是 md 的 ``### 其中，账龄超过1年的重要应付账款``。
   TAB 页签因此显示「项  目」，且底稿同步的子表名无法逐字对上（→ 孤儿子表）。
2. 上市 §五、37 第一张表保留了 md 的占位行 ``可无限量添加行``——它是模版给编制者
   的提示语，落到 ``rows`` 里就成了**假数据行**；真实分类应为源底稿 F4-1 审定表
   「按性质分类」的 5 类（货款 / 工程款 / 设备款 / 服务费 / 其他）。
3. 两个 variant 的全部表都缺 ``columns``（ColumnDef）→ 底稿同步无列头元数据，
   附注渲染只能退回英文字段键或空表头。
4. 两个 variant 的全部表都缺 ``guidance``（TAB 页签编制提示）。
5. ``text_sections`` 里混入了纯表标题行（``### 其中，账龄超过1年的重要应付账款`` /
   ``### 账龄超过1 年的重要应付账款``），既不是正文也不是提示。

**权威源**（两者口径不同，各管一段，不得混用）：

- 附注**行集合 / 表名 / 表头文案** → ``基础数据/附注模版/上市报表附注.md`` §应付账款
  与 ``基础数据/附注模版/国企报表附注.md`` §应付账款。
  ⚠️ 国企附注模版账龄行是「1年以内（含1年）/ 1至2年 / 2至3年 / 3年以上」，
  **不带**底稿 xlsx 的「（含2年）/（含3年）」——此处以附注模版为准，不要"修正"。
  同理国企第二张表名 md 原文即 ``账龄超过1 年的重要应付账款``（「1」后有空格），
  保持逐字，改名会破坏底稿子表名契约。
- 上市第一张表的**分类行** → ``基础数据/……/F 存货循环/F4 应付账款.xlsx``
  ``审定表F4-1`` 「一、按照性质分类」（货款/工程款/设备款/服务费/其他）。
- **guidance 文案** → 仅取 F4 源 xlsx ``明细表F4-2`` 提示区红字、F4A 程序表条款、
  附注模版「供应商融资安排」章节（解释第17号），以及「勾稽：」前缀的工具提示。

Usage::

    python backend/scripts/fix/fix_note_accounts_payable_structure.py --dry-run
    python backend/scripts/fix/fix_note_accounts_payable_structure.py
    python backend/scripts/fix/fix_note_accounts_payable_structure.py --check
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

ALIGNED_BY = "f4-accounts-payable-disclosure-template-alignment"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、37"
SOE_SECTION = "八、37"

# 表名（与 note_template tables[].name 逐字一致，前端 F4_*_SUBTABLE 契约锚点）
LISTED_MAIN_TABLE = "应付账款"
LISTED_OVER1Y_TABLE = "其中，账龄超过1年的重要应付账款"
SOE_MAIN_TABLE = "应付账款"
# md 原文「账龄超过1 年」在「1」后带一个空格，保持逐字
SOE_OVER1Y_TABLE = "账龄超过1 年的重要应付账款"


# ─────────────────────────── 行构造 ───────────────────────────

def _data_row(label: str = "") -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _strip_header_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删除 ``header_label`` 行：其语义已由 ``_column_groups`` 承载。"""
    return [r for r in rows if str(r.get("row_type", "")) != "header_label"]


# ─────────────────────────── 列结构 ───────────────────────────
# label 逐字取自附注模版 md 表头 / 底稿披露组件既有 el-table-column。
# 均为 3 列单级表头 → 显式 flat 抑制后端 _infer_groups_from_headers 前缀推断。

LISTED_NATURE_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]

LISTED_OVER1Y_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "unsettled_reason", "label": "未偿还或未结转的原因"},
]

SOE_AGING_COLUMNS = [
    {"key": "label", "label": "账龄", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "opening_amount", "label": "期初余额", "format": "amount"},
]

SOE_OVER1Y_COLUMNS = [
    {"key": "label", "label": "债权单位名称", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "unsettled_reason", "label": "未偿还原因"},
]


# ─────────────────────────── TAB 编制提示 ───────────────────────────

_OVER1Y_HINT_BODY = (
    "账龄超过1年的大额应付账款，应说明未偿还或未结转的原因，"
    "并在资产负债表日后事项中说明是否偿还；账龄超过3年以上的应付账款应说明未偿还的原因。"
)
_OVER1Y_HINT = f"源模板提示：{_OVER1Y_HINT_BODY}"

LISTED_NATURE_GUIDANCE = (
    "按款项性质分类列示（源模板 F4-1 审定表「一、按照性质分类」：货款、工程款、设备款、"
    "服务费、其他，可无限量添加行）。"
    "勾稽：期末余额＝F4-1 按性质「期末审定数」，上年年末余额＝按性质「期初审定数」；"
    "合计应与试算平衡表应付账款（2202）审定数一致。"
)

LISTED_OVER1Y_GUIDANCE = (
    f"{_OVER1Y_HINT}"
    "勾稽：取自 F4-5 账龄1年以上的应付账款检查表（债权人名称／审定金额／未偿还或未结转的原因），"
    "本表合计不应超过 F4-1 按账龄「1年以上」各档期末审定数之和。"
)

SOE_AGING_GUIDANCE = (
    "按账龄分类列示（附注模版：1年以内（含1年）／1至2年／2至3年／3年以上）。"
    "账龄档位跟随项目账龄配置：3年段即上述 4 档；5年段按同一「X至Y年」口径展开为"
    "1年以内（含1年）／1至2年／2至3年／3至4年／4至5年／5年以上；自定义段用配置段名。"
    "勾稽：期末余额＝F4-1 按账龄「期末审定数」，期初余额＝按账龄「期初审定数」；"
    "合计应与 F4-1 按性质分类合计一致。"
)

SOE_OVER1Y_GUIDANCE = (
    f"{_OVER1Y_HINT}"
    "勾稽：取自 F4-5 账龄1年以上的应付账款检查表（债权人名称／审定金额／未偿还或未结转的原因），"
    "本表合计不应超过上表「1年以上」各档期末余额之和。"
)


# ─────────────────────────── text_sections 修订 ───────────────────────────

# 纯表标题行：语义已由 tables[].name 承载，留在 text_sections 里会污染正文/提示分流
LISTED_TEXT_REMOVE = [
    "### 其中，账龄超过1年的重要应付账款",
    "其中，账龄超过1年的重要应付账款",
]
SOE_TEXT_REMOVE = [
    "### 账龄超过1 年的重要应付账款",
    "账龄超过1 年的重要应付账款",
    "### 账龄超过1年的重要应付账款",
]

# 【】块 → 后端 classify_template_content 归入 section_guidance（编制提示），不进正文
_SUPPLIER_FINANCE_HINT = (
    "【提示：存在供应商融资安排（如反向保理、供应链融资平台）的，按《企业会计准则解释第17号》"
    "在「现金流量表补充资料—供应商融资安排」中披露该安排的条款和条件、资产负债表中的列报项目"
    "及其中「供应商已收到款项」的金额、付款到期日的区间、不涉及现金收支的当期变动；"
    "底稿见 F4-9 供应商融资检查表。】"
)

LISTED_TEXT_ADDITIONS = [
    f"【提示：{_OVER1Y_HINT_BODY}】",
    _SUPPLIER_FINANCE_HINT,
]
SOE_TEXT_ADDITIONS = list(LISTED_TEXT_ADDITIONS)


# ─────────────────────────── 修订计划 ───────────────────────────

def _listed_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": [LISTED_MAIN_TABLE],
            "patch": {
                "headers": ["项目", "期末余额", "上年年末余额"],
                "columns": LISTED_NATURE_COLUMNS,
                "guidance": LISTED_NATURE_GUIDANCE,
            },
            "rows": "listed_nature",
        },
        {
            # md 重建把首个表头单元格当成了表名
            "aliases": [LISTED_OVER1Y_TABLE, "项  目", "项目"],
            "new_name": LISTED_OVER1Y_TABLE,
            "patch": {
                "headers": ["项目", "期末余额", "未偿还或未结转的原因"],
                "columns": LISTED_OVER1Y_COLUMNS,
                "guidance": LISTED_OVER1Y_GUIDANCE,
            },
            "rows": "over1y",
        },
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": [SOE_MAIN_TABLE],
            "patch": {
                "headers": ["账龄", "期末余额", "期初余额"],
                "columns": SOE_AGING_COLUMNS,
                "guidance": SOE_AGING_GUIDANCE,
            },
            # 行集合以附注模版为准（4 档，不加「（含2年）」）
            "rows": "soe_aging",
        },
        {
            "aliases": [SOE_OVER1Y_TABLE, "账龄超过1年的重要应付账款", "债权单位名称"],
            "new_name": SOE_OVER1Y_TABLE,
            "patch": {
                "headers": ["债权单位名称", "期末余额", "未偿还原因"],
                "columns": SOE_OVER1Y_COLUMNS,
                "guidance": SOE_OVER1Y_GUIDANCE,
            },
            "rows": "over1y",
        },
    ]


# 上市按性质分类行 = F4-1 审定表「一、按照性质分类」5 类（删除 md 占位行「可无限量添加行」）
LISTED_NATURE_ROWS = ["货款", "工程款", "设备款", "服务费", "其他"]
# 国企按账龄行 = 国企附注模版 §应付账款 4 档（逐字，不带「（含2年）」）
SOE_AGING_ROWS = ["1年以内（含1年）", "1至2年", "2至3年", "3年以上"]


def _rows_for(mode: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if mode == "listed_nature":
        return [_data_row(label) for label in LISTED_NATURE_ROWS] + [_total_row()]
    if mode == "soe_aging":
        return [_data_row(label) for label in SOE_AGING_ROWS] + [_total_row()]
    if mode == "over1y":
        # 逐项披露，无固定行：保留 2 个空白骨架行 + 合计（同步时整表覆盖）
        return [_data_row(), _data_row(), _total_row()]
    if mode == "strip":
        return _strip_header_labels(existing)
    return existing


# ─────────────────────────── 应用 ───────────────────────────

def _matches(table_name: str, rule: dict[str, Any]) -> bool:
    if table_name in rule["aliases"]:
        return True
    for pre in rule.get("alias_prefixes", []):
        if table_name.startswith(pre):
            return True
    return False


def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def apply_plan(
    section: dict[str, Any],
    plan: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """按计划就地修订 section.tables（游标只前进，重名表由位置区分）。"""
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for rule in plan:
        idx = next(
            (i for i in range(cursor, len(tables))
             if _matches(str(tables[i].get("name", "")).strip(), rule)),
            None,
        )
        if idx is None:
            warnings.append(f"未找到表：{rule['aliases'][0]}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        new_name = rule.get("new_name")

        if new_name and old_name != new_name:
            dup = next(
                (j for j, t in enumerate(tables)
                 if j != idx and str(t.get("name", "")) == new_name),
                None,
            )
            if dup is not None:
                warnings.append(
                    f"表名迁移跳过：「{old_name}」→「{new_name}」，"
                    f"索引 {dup} 已占用该名（请人工确认）"
                )
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{new_name}」")

        patch = rule["patch"]
        for key in ("headers", "columns", "_column_groups"):
            if key not in patch:
                continue
            if tbl.get(key) != patch[key]:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(patch[key], ensure_ascii=False))
                changes.append(
                    f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(patch[key])} 项"
                )
        if "guidance" in patch and tbl.get("guidance") != patch["guidance"]:
            had = bool(tbl.get("guidance"))
            tbl["guidance"] = patch["guidance"]
            changes.append(
                f"[{idx}] {tbl.get('name')}.guidance：{'更新' if had else '新增'}"
                f"（{len(patch['guidance'])} 字）"
            )

        rows_mode = rule.get("rows", "keep")
        if rows_mode != "keep":
            old_rows = tbl.get("rows") or []
            new_rows = _rows_for(rows_mode, old_rows)
            if new_rows != old_rows:
                tbl["rows"] = new_rows
                changes.append(
                    f"[{idx}] {tbl.get('name')}.rows：{len(old_rows)} → {len(new_rows)} 行"
                    f"（{rows_mode}）"
                )

        cursor = idx + 1

    return changes, warnings


def revise_text_sections(
    section: dict[str, Any],
    remove: list[str],
    additions: list[str],
) -> list[str]:
    """删除纯表标题行 + 追加缺失【提示】段（精确串查重 → 幂等）。"""
    texts: list[str] = section.setdefault("text_sections", [])
    changes: list[str] = []

    kept = [t for t in texts if str(t).strip() not in remove]
    if len(kept) != len(texts):
        changes.append(f"text_sections 删除 {len(texts) - len(kept)} 段纯表标题行")
        texts[:] = kept

    missing = [t for t in additions if t not in texts]
    if missing:
        texts.extend(missing)
        changes.append(f"text_sections 追加 {len(missing)} 段编制提示")
    return changes


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any], expected_names: list[str]) -> list[str]:
    """结构自洽校验：表名唯一且齐备、columns/headers 对齐、guidance 齐备、无假数据行。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i

        headers = [str(h) for h in (tbl.get("headers") or [])]
        if not headers:
            errs.append(f"[{i}] {name} 缺 headers")
        if any(h.strip() == "" for h in headers):
            errs.append(f"[{i}] {name} headers 含空串：{headers}")
        n_val = max(len(headers) - 1, 0)

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label（假数据行）")
            if str(row.get("label", "")).strip() in {"可无限量添加行", "项  目", "项目"}:
                errs.append(f"[{i}] {name} 第 {j} 行为占位/表头文案：{row.get('label')!r}")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != n_val:
                errs.append(f"[{i}] {name} 第 {j} 行 values={len(vals)} ≠ headers-1={n_val}")

        cols = tbl.get("columns")
        if not cols:
            errs.append(f"[{i}] {name} 缺 columns（同步无列头元数据）")
        else:
            if len(cols) != len(headers):
                errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
            label_cols = [c for c in cols if c.get("is_label")]
            if len(label_cols) != 1:
                errs.append(f"[{i}] {name} is_label 列数={len(label_cols)}（应为 1）")
            elif headers and str(label_cols[0].get("label")) != headers[0]:
                errs.append(
                    f"[{i}] {name} 标签列 label={label_cols[0].get('label')!r} "
                    f"≠ headers[0]={headers[0]!r}"
                )
            for c in cols:
                if not str(c.get("key", "")):
                    errs.append(f"[{i}] {name} columns 存在空 key")

        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"[{i}] {name} 缺 guidance（TAB 页签编制提示）")

    for expected in expected_names:
        if expected not in seen:
            errs.append(f"缺表：「{expected}」（当前表名：{list(seen)}）")

    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(
    path: Path,
    section_number: str,
    plan: list[dict[str, Any]],
    text_remove: list[str],
    text_additions: list[str],
    expected_names: list[str],
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
        errs = validate_section(section, expected_names)
        log.append(f"_aligned_by={section.get('_aligned_by')!r}")
        if section.get("_aligned_by") != ALIGNED_BY:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_plan(section, plan)
    changes += revise_text_sections(section, text_remove, text_additions)

    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section, expected_names)
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


TARGETS = [
    (
        LISTED_PATH, LISTED_SECTION, _listed_plan, LISTED_TEXT_REMOVE,
        LISTED_TEXT_ADDITIONS, [LISTED_MAIN_TABLE, LISTED_OVER1Y_TABLE],
    ),
    (
        SOE_PATH, SOE_SECTION, _soe_plan, SOE_TEXT_REMOVE,
        SOE_TEXT_ADDITIONS, [SOE_MAIN_TABLE, SOE_OVER1Y_TABLE],
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="附注应付账款章节结构对齐源模版（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    ok_all = True
    for path, section_number, plan_fn, remove, texts, expected in TARGETS:
        ok, log = _process(
            path, section_number, plan_fn(), remove, texts, expected,
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
