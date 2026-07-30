#!/usr/bin/env python
"""附注「其他流动资产」章节结构对齐源模版（幂等修订）。

**目标**：把附注模板 ``其他流动资产`` 章节（上市 §五、13 / 国企 §八、14）由
md 重建产物修正为可用结构 —— 消除「段落文本当表名」「表头首格当表名」「表头行
残留成假数据行」，并补齐 ``columns`` / ``guidance``。

历史问题（2026-07-30 实测）：

1. 上市第 2 张表名是段落文本泄漏：``[披露与合同取得成本有关的资产相关的信息，……例如：``
   → TAB 页签显示一整段说明文字；且该表 ``headers[0]`` 是 ``[佣金支出]``（类别列），
   md 重建把空的标签列首格丢掉了 → 标签列无列头。
2. 上市第 3 张表名是表头首格 ``项  目``；其 ``rows[0]`` 又是 ``row_type: header_label``
   的**假数据行**（压扁的第二行表头残留）。
3. 两版共 4 张表**全部** ``columns=0``（未表态）+ **全部无** ``guidance``
   → seed 路径会走 ``_infer_groups_from_headers`` 前缀推断。

**权威源**（三者互证，裁决见 spec design §概览）：

- ``backend/wp_templates/K/K2 其他流动资产.xlsx`` 的
  ``附注披露信息（上市公司）`` / ``附注披露信息（国企）``（**全角括号**）：
  两版都只有一张三列明细表（项目 / 期末 / 期初），数据引 ``'明细表K2-2'!A11~A14,A17``；
  上市蓝字「（金额较大的其他流动资产，应说明其内容、性质）」，
  国企蓝字「（根据性质选择披露方式）」。
- ``note_template_{listed,soe}.json``（交付物权威）：列名与固定行名以此为准
  —— 上市 ``期末余额 / 上年年末余额``、国企 ``期末余额 / 期初余额``。
- ``backend/data/note_check_preset_formulas.json`` F13-1 / F13-1a / F13-2：
  只对①明细表设勾稽 → 表②③是**条件性披露表**（源 xlsx 无，附注模版有）。

裁决要点：

- 源 xlsx 三列都是**单行表头** → 4 张表一律显式 ``flat``，并删除 ``_column_groups``。
- 上市表②是**转置结构**：行 = 变动项目（期初余额 / 本年增加 / 本年摊销 /
  本年计提减值损失 / 期末余额），列 = 资产主要类别 + 合计；``［佣金支出］``是源模版
  示例类别（可改名可增删），seed 保留一列。
- 表名迁移后旧键由同步载荷的 ``_removed_table_keys`` 清理（见 ``k2NoteSectionMap.ts``）。

Usage::

    python backend/scripts/fix/fix_note_k2_structure.py --dry-run
    python backend/scripts/fix/fix_note_k2_structure.py
    python backend/scripts/fix/fix_note_k2_structure.py --check

spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ R4
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "k2-other-current-assets-disclosure-alignment"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、13"
SOE_SECTION = "八、14"

# ── 表名（与 k2NoteSectionMap.ts 的 sub_table_data 键逐字一致）──────────────
T_MAIN = "其他流动资产"
T_CONTRACT_COST = "合同取得成本"
T_CARBON = "碳排放配额变动情况"

# md 重建产物的历史表名（同步载荷同样上报为 `_removed_table_keys`）
T_CONTRACT_COST_OBSOLETE = (
    "[披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、"
    "该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及"
    "减值损失金额等。例如："
)
T_CARBON_OBSOLETE = "项  目"

# 源模版示例类别（可改名；底稿同步时按实际主要类别整表覆盖）
SEED_CONTRACT_COST_CATEGORY = "佣金支出"


# ─────────────────────────── 行构造 ───────────────────────────

def _data_row(label: str) -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _strip_header_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删除 ``header_label`` 假数据行（压扁的第二行表头残留）。"""
    return [r for r in rows if str(r.get("row_type", "")) != "header_label"]


CONTRACT_COST_ROWS = [
    "期初余额",
    "本年增加",
    "本年摊销",
    "本年计提减值损失",
    "期末余额",
]


# ─────────────────────────── 列结构 ───────────────────────────

def _flat3(label_head: str, c1_key: str, c1_head: str, c2_key: str, c2_head: str) -> dict[str, Any]:
    """三列单行表头：标签列 + 两个金额列。``flat`` 标在标签列即对整表生效。"""
    return {
        "headers": [label_head, c1_head, c2_head],
        "columns": [
            {"key": "label", "label": label_head, "is_label": True, "flat": True},
            {"key": c1_key, "label": c1_head, "format": "amount"},
            {"key": c2_key, "label": c2_head, "format": "amount"},
        ],
        "_column_groups": [],
    }


LISTED_MAIN_PATCH = _flat3("项目", "end_amount", "期末余额", "prior_amount", "上年年末余额")
SOE_MAIN_PATCH = _flat3("项目", "end_amount", "期末余额", "prior_amount", "期初余额")
LISTED_CARBON_PATCH = _flat3("项目", "current_amount", "本期发生额", "prior_amount", "上期发生额")

LISTED_CONTRACT_COST_PATCH = {
    # 转置结构：列 = 资产主要类别（seed 一列示例）+ 合计
    "headers": ["项目", SEED_CONTRACT_COST_CATEGORY, "合计"],
    "columns": [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "cat_1", "label": SEED_CONTRACT_COST_CATEGORY, "format": "amount"},
        {"key": "total", "label": "合计", "format": "amount"},
    ],
    "_column_groups": [],
}


# ─────────────────────────── guidance ───────────────────────────

_LISTED_MAIN_GUIDANCE = (
    "【提示：进项税额，根据“应交税费-应交增值税”科目借方余额分析填列；"
    "多交或预缴的增值税额，根据“应交税费-未交增值税”科目以及“应交税费-预交增值税”"
    "科目借方余额分析填列。上述重分类事项，如属于其他非流动资产的，应在"
    "“其他非流动资产”科目列示。】"
    "源模板要求根据实际情况列示，不存在的项目请删除；金额较大的其他流动资产，"
    "应在下方文本区说明其内容、性质。"
    "勾稽：合计行期末余额 = 报表「其他流动资产」期末数（F13-1）；"
    "合计行上年年末余额 = 报表期初数（F13-1a）；"
    "各明细行之和 = 合计行（每个数值列独立校验，F13-2）。"
    "数据来源：审定表 K2-1 / 明细表 K2-2。"
)

_LISTED_CONTRACT_COST_GUIDANCE = (
    "披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、"
    "该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及"
    "减值损失金额等。"
    "源模板以［佣金支出］为示例类别，实际按该资产主要类别列示（类别列可增删改名）；"
    "摊销期限未超过一年的合同取得成本于其发生时计入当期损益。"
    "勾稽：合计列 = 各类别列之和；"
    "期末余额行 = 期初余额 + 本年增加 − 本年摊销 − 本年计提减值损失。"
    "数据来源：合同取得成本明细表 K2-4 / 摊销测算表 K2-5。"
)

_LISTED_CARBON_GUIDANCE = (
    "披露与碳排放权相关的信息，包括："
    "①与碳排放权交易相关的信息（参与减排机制的特征、碳排放战略、节能减排措施等）；"
    "②碳排放配额的具体来源（配额取得方式、取得年度、用途、结转原因等）；"
    "③节能减排或超额排放情况（免费分配取得的碳排放配额与同期实际排放量有关数据的"
    "对比情况、节能减排或超额排放的原因等）；"
    "④碳排放配额变动情况按本表格式披露。"
    "勾稽：本期期末碳排放配额 = 本期期初碳排放配额 + 本期增加 − 本期减少；"
    "各（1）（2）（3）分项之和 = 对应的本期增加 / 本期减少汇总行。"
)

_SOE_MAIN_GUIDANCE = (
    "【提示：待抵扣进项税额，根据“应交税费-应交增值税”科目借方余额分析填列；"
    "预缴税金中的增值税额，根据“应交税费-未交增值税”科目以及“应交税费-预交增值税”"
    "科目借方余额分析填列；上述重分类事项，如属于其他非流动资产的，应在"
    "“其他非流动资产”科目列示。】"
    "源模板要求根据性质选择披露方式。"
    "勾稽：合计行期末余额 = 报表「其他流动资产」期末数（F13-1）；"
    "合计行期初余额 = 报表期初数（F13-1a）；"
    "各明细行之和 = 合计行（每个数值列独立校验，F13-2）。"
    "数据来源：审定表 K2-1 / 明细表 K2-2。"
)

LISTED_GUIDANCE = {
    T_MAIN: _LISTED_MAIN_GUIDANCE,
    T_CONTRACT_COST: _LISTED_CONTRACT_COST_GUIDANCE,
    T_CARBON: _LISTED_CARBON_GUIDANCE,
}
SOE_GUIDANCE = {T_MAIN: _SOE_MAIN_GUIDANCE}


# ─────────────────────────── 修订计划 ───────────────────────────

def _listed_plan() -> list[dict[str, Any]]:
    return [
        {"aliases": [T_MAIN], "patch": LISTED_MAIN_PATCH, "rows": "strip"},
        {
            "aliases": [T_CONTRACT_COST_OBSOLETE, T_CONTRACT_COST],
            "new_name": T_CONTRACT_COST,
            "patch": LISTED_CONTRACT_COST_PATCH,
            "rows": "contract_cost",
        },
        {
            "aliases": [T_CARBON_OBSOLETE, T_CARBON],
            "new_name": T_CARBON,
            "patch": LISTED_CARBON_PATCH,
            "rows": "strip",
        },
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [{"aliases": [T_MAIN], "patch": SOE_MAIN_PATCH, "rows": "strip"}]


EXPECTED_TABLES = {
    LISTED_SECTION: [T_MAIN, T_CONTRACT_COST, T_CARBON],
    SOE_SECTION: [T_MAIN],
}


# ─────────────────────────── 应用 ───────────────────────────

def _rows_for(mode: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if mode == "strip":
        return _strip_header_labels(existing)
    if mode == "contract_cost":
        return [_data_row(label) for label in CONTRACT_COST_ROWS]
    return existing


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
    """按计划就地修订 ``section.tables``。返回 ``(changes, warnings)``。"""
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for rule in plan:
        idx = next(
            (
                i
                for i in range(cursor, len(tables))
                if str(tables[i].get("name", "")) in rule["aliases"]
            ),
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
                    f"表名迁移跳过：「{old_name[:30]}…」→「{new_name}」，"
                    f"索引 {dup} 已占用该名（请人工确认）"
                )
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name[:40]}」→「{new_name}」")

        patch = rule["patch"]
        for key in ("headers", "columns", "_column_groups"):
            if key not in patch:
                continue
            want = patch[key]
            if not want and key == "_column_groups":
                if tbl.pop(key, None) is not None:
                    changes.append(f"[{idx}] {tbl.get('name')}.{key}：删除（单级表头，靠 flat 表态）")
                continue
            if tbl.get(key) != want:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(want, ensure_ascii=False))
                changes.append(f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(want)} 项")

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


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any], section_number: str) -> list[str]:
    """结构自洽校验：表名唯一齐备 / 无假数据行 / 列数一致 / 显式 flat / guidance 齐备。"""
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
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label 假数据行")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != n_val:
                errs.append(f"[{i}] {name} 第 {j} 行 values={len(vals)} ≠ headers-1={n_val}")

        cols = tbl.get("columns") or []
        if not cols:
            errs.append(f"[{i}] {name} 缺 columns")
        else:
            if len(cols) != len(headers):
                errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
            if str(cols[0].get("label", "")) != str(headers[0] if headers else ""):
                errs.append(
                    f"[{i}] {name} columns[0].label={cols[0].get('label')!r} "
                    f"≠ headers[0]={(headers[0] if headers else None)!r}"
                )
            if not cols[0].get("is_label"):
                errs.append(f"[{i}] {name} columns[0] 未标 is_label")
            has_flat = any(c.get("flat") for c in cols)
            has_group = any(c.get("group") for c in cols)
            if has_flat and has_group:
                errs.append(f"[{i}] {name} 同表既有 flat 又有 group")
            if not has_flat and not has_group:
                errs.append(f"[{i}] {name} 未表态（既无 flat 也无 group）")
            if has_flat and tbl.get("_column_groups"):
                errs.append(f"[{i}] {name} 标了 flat 却仍留 _column_groups")

        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"[{i}] {name} 缺 guidance")

    for want in EXPECTED_TABLES.get(section_number, []):
        if want not in seen:
            errs.append(f"缺表：「{want}」")

    for obsolete in (T_CONTRACT_COST_OBSOLETE, T_CARBON_OBSOLETE):
        if obsolete in seen and section_number == LISTED_SECTION:
            errs.append(f"历史表名残留：「{obsolete[:40]}」")

    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(
    path: Path,
    section_number: str,
    plan: list[dict[str, Any]],
    guidance: dict[str, str],
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
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注其他流动资产章节结构对齐源模版（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    targets = [
        (LISTED_PATH, LISTED_SECTION, _listed_plan(), LISTED_GUIDANCE),
        (SOE_PATH, SOE_SECTION, _soe_plan(), SOE_GUIDANCE),
    ]

    ok_all = True
    lines: list[str] = []
    for path, section_number, plan, guidance in targets:
        ok, log = _process(
            path,
            section_number,
            plan,
            guidance,
            dry_run=args.dry_run,
            check_only=args.check,
        )
        ok_all = ok_all and ok
        lines.extend(log)
        lines.append("")

    print("\n".join(lines))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
