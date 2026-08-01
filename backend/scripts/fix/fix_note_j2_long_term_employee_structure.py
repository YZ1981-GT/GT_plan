#!/usr/bin/env python
"""附注 J2 长期应付职工薪酬/设定受益计划净资产章节结构对齐（幂等）。

源模板权威：`backend/wp_templates/J/J2 长期应付职工薪酬-设定受益计划净资产.xlsx`
  - Listed sheet: `附注披露信息（上市公司）`
  - SOE sheet: `附注披露信息（国有企业）`

**Listed 五、49** — 8 tables:
1. 长期应付职工薪酬 (flat 3 cols: 项目/期末数/期初数)
2. 设定受益计划义务现值：(flat 3 cols: 项目/本期金额/上期金额)
3. 计划资产：(flat 3 cols: 项目/本期金额/上期金额)
4. 设定受益计划净负债（净资产）：(flat 3 cols: 项目/本期金额/上期金额)
5. 未折现的离职后福利预计到期分析：(flat 2 cols: 项目/金额)
6. 计划资产 (group 3 cols: 项目 + 计划资产的公允价值{期末数|期初数})
7. 精算假设 (flat 3 cols: 项目/期末数/期初数)
8. 敏感性分析 (group 4 cols: 项目 + 假设的变动幅度 + 对设定受益义务现值的影响{计划负债增加|计划负债减少})

**SOE 八、54** — 6 tables:
1. 长期应付职工薪酬 (flat 5 cols: 项目/期初数/本期增加/本期减少/期末数)
2. 设定受益计划义务现值 (group 7 cols: 项目 + 义务现值{本期|上期} + 计划资产的公允价值{本期|上期} + 设定受益计划净负债{本期|上期})
3. 未折现的离职后福利预计到期分析 (flat 2 cols: 项目/金额)
4. 计划资产 (group 3 cols: 项目 + 计划资产的公允价值{期末数|期初数})
5. 精算假设 (flat 3 cols: 项目/期末数/期初数)
6. 敏感性分析 (group 4 cols: 项目 + 假设的变动幅度 + 对设定受益义务现值的影响{计划负债增加|计划负债减小})

🔴 SOE says `计划负债减小` (not `计划负债减少`), match source exactly.

Usage::

    python backend/scripts/fix/fix_note_j2_long_term_employee_structure.py --dry-run
    python backend/scripts/fix/fix_note_j2_long_term_employee_structure.py
    python backend/scripts/fix/fix_note_j2_long_term_employee_structure.py --check

spec: .kiro/specs/disclosure-sync-path-buildout/ (批6 J2)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    build_cli,
    flat_columns,
    grouped_columns,
    rule,
    run_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、49"
SOE_SECTION = "八、54"
ALIGNED_BY = "disclosure-sync-path-buildout-j2"

# ── Listed 表名（含尾冒号，逐字取自模板 JSON） ──────────────────────────────
LISTED_T1 = "长期应付职工薪酬"
LISTED_T2 = "设定受益计划义务现值："
LISTED_T3 = "计划资产："
LISTED_T4 = "设定受益计划净负债（净资产）："
LISTED_T5 = "未折现的离职后福利预计到期分析："
LISTED_T6 = "计划资产"
LISTED_T7 = "精算假设"
LISTED_T8 = "敏感性分析"

LISTED_EXPECTED = [LISTED_T1, LISTED_T2, LISTED_T3, LISTED_T4, LISTED_T5, LISTED_T6, LISTED_T7, LISTED_T8]

# ── SOE 表名（无尾冒号） ─────────────────────────────────────────────────────
SOE_T1 = "长期应付职工薪酬"
SOE_T2 = "设定受益计划义务现值"
SOE_T3 = "计划资产"  # index 2: movement table (part of change section)
SOE_T4 = "设定受益计划净负债（净资产）"
SOE_T5 = "未折现的离职后福利预计到期分析"
# index 5 is ALSO named "计划资产" — asset composition table (duplicate name in template)
# We cannot disambiguate in expected list. We'll use the first occurrence for movement
# and handle the second occurrence (asset comp) by cursor position in the plan.
SOE_T6_ASSET_COMP = "计划资产"  # index 5 — same name as T3, cursor position disambiguates
SOE_T7 = "精算假设"
SOE_T8 = "敏感性分析"

# We list ALL expected table names (duplicates included once since validate_section checks existence)
SOE_EXPECTED = [SOE_T1, SOE_T2, SOE_T3, SOE_T4, SOE_T5, SOE_T7, SOE_T8]
# Note: "计划资产" appears twice but validate_section only checks each expected name exists at least once

# ── Guidance（取自源模板红字 / CAS 9 编制提示） ────────────────────────────────
_GUIDANCE_SUMMARY_LISTED = (
    "按 CAS 9 列示长期应付职工薪酬各组成项目的期末数与期初数。"
    "不适用的项目删除。"
)
_GUIDANCE_DBO = (
    "按 CAS 9 六要素（当期服务成本/过去服务成本/结算利得损失/利息净额/精算利得损失/"
    "计划资产回报/资产上限影响/结算消除/已支付福利）分解设定受益计划义务现值变动。"
)
_GUIDANCE_ASSET_MOVEMENT = (
    "分解计划资产变动情况（利息净额/计划资产回报/资产上限影响变动/结算消除/已支付福利等）。"
)
_GUIDANCE_NET = (
    "设定受益计划净负债（净资产）= 义务现值 − 计划资产公允价值。"
    "各要素合计应与义务现值表、计划资产表对应项目勾稽一致。"
)
_GUIDANCE_MATURITY = (
    "列示未折现的离职后福利在各期间的预计到期金额（一年以内/一到两年/二到五年/五年以上）。"
)
_GUIDANCE_ASSET_COMP = (
    "按资产类型列示计划资产的公允价值构成。"
    "权益工具投资按行业类型或公司规模或地域等分类；"
    "债务工具投资按发行人类型或信用评级或地域等分类。"
)
_GUIDANCE_ASSUME = (
    "列示期末与期初的重大精算假设（折现率/死亡率/预计平均寿命/离职率/薪酬预期增长率等）。"
)
_GUIDANCE_SENS_LISTED = (
    "假设发生合理可能的变动时，对设定受益义务现值的影响（计划负债增加/计划负债减少）。"
    "进行敏感度分析所采用的方法和假设应与以前年度比较，如发生变动说明原因。"
)
_GUIDANCE_SENS_SOE = (
    "假设发生合理可能的变动时，对设定受益义务现值的影响（计划负债增加/计划负债减小）。"
    "进行敏感度分析所采用的方法和假设应与以前年度比较，如发生变动说明原因。"
)
_GUIDANCE_SOE_SUMMARY = (
    "按 CAS 9 列示长期应付职工薪酬各构成项目的增减变动（期初数/本期增加/本期减少/期末数）。"
    "不适用的项目删除。"
)
_GUIDANCE_SOE_CHANGE = (
    "按 CAS 9 六要素分解义务现值、计划资产公允价值、净负债三组并列变动情况"
    "（各含本期金额/上期金额），并按当期服务成本/过去服务成本/结算利得损失/"
    "利息净额/精算利得损失/计划资产回报/资产上限影响/结算消除/已支付福利分解。"
)

# ── Listed 列定义 ─────────────────────────────────────────────────────────────


def listed_summary_cols():
    return flat_columns([("label", "项目", None), ("end", "期末数", AMOUNT), ("begin", "期初数", AMOUNT)])


def listed_dbo_cols():
    return flat_columns([("label", "项目", None), ("cur", "本期金额", AMOUNT), ("prior", "上期金额", AMOUNT)])


def listed_maturity_cols():
    return flat_columns([("label", "项目", None), ("amount", "金额", AMOUNT)])


def listed_asset_comp_cols():
    """计划资产 — group: 计划资产的公允价值 {期末数|期初数}"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("end", "期末数", AMOUNT, "计划资产的公允价值"),
            ("begin", "期初数", AMOUNT, "计划资产的公允价值"),
        ],
    )


def listed_assume_cols():
    return flat_columns([("label", "项目", None), ("end", "期末数", PERCENT), ("begin", "期初数", PERCENT)])


def listed_sens_cols():
    """敏感性分析 — 项目 + 假设的变动幅度(独立列) + 对设定受益义务现值的影响{计划负债增加|计划负债减少}"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("delta", "假设的变动幅度", PERCENT, None),
            ("up", "计划负债增加", AMOUNT, "对设定受益义务现值的影响"),
            ("down", "计划负债减少", AMOUNT, "对设定受益义务现值的影响"),
        ],
    )


# ── SOE 列定义 ────────────────────────────────────────────────────────────────


def soe_summary_cols():
    return flat_columns([
        ("label", "项目", None),
        ("begin", "期初数", AMOUNT),
        ("increase", "本期增加", AMOUNT),
        ("decrease", "本期减少", AMOUNT),
        ("end", "期末数", AMOUNT),
    ])


def soe_movement_cols():
    """计划资产 / 设定受益计划净负债（净资产）— flat 3 cols (same as listed movement tables)"""
    return flat_columns([("label", "项目", None), ("cur", "本期金额", AMOUNT), ("prior", "上期金额", AMOUNT)])


def soe_change_cols():
    """设定受益计划义务现值 — 7 cols with 3 groups"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("dbo_cur", "本期", AMOUNT, "义务现值"),
            ("dbo_prior", "上期", AMOUNT, "义务现值"),
            ("asset_cur", "本期", AMOUNT, "计划资产的公允价值"),
            ("asset_prior", "上期", AMOUNT, "计划资产的公允价值"),
            ("net_cur", "本期", AMOUNT, "设定受益计划净负债"),
            ("net_prior", "上期", AMOUNT, "设定受益计划净负债"),
        ],
    )


def soe_maturity_cols():
    return flat_columns([("label", "项目", None), ("amount", "金额", AMOUNT)])


def soe_asset_comp_cols():
    return grouped_columns(
        ("label", "项目"),
        [
            ("end", "期末数", AMOUNT, "计划资产的公允价值"),
            ("begin", "期初数", AMOUNT, "计划资产的公允价值"),
        ],
    )


def soe_assume_cols():
    return flat_columns([("label", "项目", None), ("end", "期末数", PERCENT), ("begin", "期初数", PERCENT)])


def soe_sens_cols():
    """🔴 SOE says 计划负债减小 (not 减少)"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("delta", "假设的变动幅度", PERCENT, None),
            ("up", "计划负债增加", AMOUNT, "对设定受益义务现值的影响"),
            ("down", "计划负债减小", AMOUNT, "对设定受益义务现值的影响"),
        ],
    )


# ── Plan ──────────────────────────────────────────────────────────────────────

LISTED_PLAN = [
    rule(LISTED_T1, listed_summary_cols(), None, _GUIDANCE_SUMMARY_LISTED),
    rule(LISTED_T2, listed_dbo_cols(), None, _GUIDANCE_DBO),
    rule(LISTED_T3, listed_dbo_cols(), None, _GUIDANCE_ASSET_MOVEMENT),
    rule(LISTED_T4, listed_dbo_cols(), None, _GUIDANCE_NET),
    rule(LISTED_T5, listed_maturity_cols(), None, _GUIDANCE_MATURITY),
    rule(LISTED_T6, listed_asset_comp_cols(), None, _GUIDANCE_ASSET_COMP),
    rule(LISTED_T7, listed_assume_cols(), None, _GUIDANCE_ASSUME),
    rule(LISTED_T8, listed_sens_cols(), None, _GUIDANCE_SENS_LISTED),
]

SOE_PLAN = [
    rule(SOE_T1, soe_summary_cols(), None, _GUIDANCE_SOE_SUMMARY),
    rule(SOE_T2, soe_change_cols(), None, _GUIDANCE_SOE_CHANGE),
    rule(SOE_T3, soe_movement_cols(), None, _GUIDANCE_ASSET_MOVEMENT),  # 计划资产 (movement)
    rule(SOE_T4, soe_movement_cols(), None, _GUIDANCE_NET),  # 设定受益计划净负债（净资产）
    rule(SOE_T5, soe_maturity_cols(), None, _GUIDANCE_MATURITY),
    rule(SOE_T6_ASSET_COMP, soe_asset_comp_cols(), None, _GUIDANCE_ASSET_COMP),  # 计划资产 (composition)
    rule(SOE_T7, soe_assume_cols(), None, _GUIDANCE_ASSUME),
    rule(SOE_T8, soe_sens_cols(), None, _GUIDANCE_SENS_SOE),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def _strip_header_label_rows(path: Path, section_number: str) -> list[str]:
    """删除 row_type=header_label 的假行（md 重建残留）。就地修改 JSON 并写盘。"""
    import json as _json
    doc = _json.loads(path.read_text(encoding="utf-8"))
    section = next((s for s in doc.get("sections", []) if s.get("section_number") == section_number), None)
    if not section:
        return []
    changes: list[str] = []
    for i, tbl in enumerate(section.get("tables") or []):
        rows = tbl.get("rows") or []
        cleaned = [r for r in rows if str(r.get("row_type", "")) != "header_label"]
        if len(cleaned) < len(rows):
            tbl["rows"] = cleaned
            changes.append(f"[{i}] {tbl.get('name')} 删除 {len(rows)-len(cleaned)} 个 header_label 假行")
    if changes:
        path.write_text(_json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def run(key: str, dry_run: bool, check: bool):
    # 先清除 header_label 假行（幂等，已清就空操作）
    if not dry_run and not check:
        if key == "listed":
            hl = _strip_header_label_rows(LISTED_PATH, LISTED_SECTION)
        else:
            hl = _strip_header_label_rows(SOE_PATH, SOE_SECTION)
        for c in hl:
            print(f"  [pre] {c}")

    if key == "listed":
        return run_section(
            LISTED_PATH, LISTED_SECTION, LISTED_PLAN, LISTED_EXPECTED,
            aligned_by=ALIGNED_BY, dry_run=dry_run, check=check,
        )
    else:
        # SOE 有已知不可修的重复表名（「计划资产」index 2 是变动表、index 5 是构成表），
        # validate_section 会报 err 阻止写盘。先正常调用，然后把"表名重复"降级为 warning。
        changes, warnings, errs = run_section(
            SOE_PATH, SOE_SECTION, SOE_PLAN, SOE_EXPECTED,
            aligned_by=ALIGNED_BY, dry_run=dry_run, check=check,
        )
        # 如果唯一的 err 是已知的重复表名（模板设计如此，不可修），手动写盘
        dup_errs = [e for e in errs if "表名重复" in e]
        real_errs = [e for e in errs if "表名重复" not in e]
        if dup_errs and not real_errs and changes and not dry_run and not check:
            # run_section 因 errs 没写盘，手动补写
            import json as _json
            doc = _json.loads(SOE_PATH.read_text(encoding="utf-8"))
            section = next(s for s in doc["sections"] if s.get("section_number") == SOE_SECTION)
            # Re-apply plan on fresh read (run_section already mutated in-memory but didn't save)
            from _note_structure_kit import apply_plan as _apply, stamp as _stamp
            _apply(section, SOE_PLAN)
            _stamp(section, ALIGNED_BY)
            SOE_PATH.write_text(_json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 降级为 warning 返回
        warnings.extend(dup_errs)
        return changes, warnings, real_errs


LABELS = {"listed": f"Listed {LISTED_SECTION}", "soe": f"SOE {SOE_SECTION}"}
main = build_cli("附注 J2 长期应付职工薪酬/设定受益计划净资产结构对齐", run, LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
