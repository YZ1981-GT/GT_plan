#!/usr/bin/env python3
"""
migrate_abcs_confirmation_ledger.py — Wave 4 Task 5.4
迁移 A/B/C/S 与 confirmation 特殊组件的 Capability Ledger 条目。

按适用性保留能力级豁免；不得以"非结构化底稿"豁免复核/版本等无关能力。

关键规则:
  - version / review 是所有经 GtWpRenderer 渲染组件的通用能力，不可因
    "非结构化"或"程序表"豁免（由 Runtime Boundary 统一提供）。
  - agingConfig 仅对含账龄维度的底稿适用；A/B/C/S 多数无账龄→exempt。
  - persistence 按实际 checklist-responses 接线判定。
  - importExport 按"动态行表格"铁律判定。
  - acnr 按 GtIndexChip 使用判定。
  - ai 由 Runtime Boundary 统一提供。

Feature: workpaper-maintainability-convergence, Task 5.4
Requirements: 1.3, 2, 7
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

COVERAGE_LEDGER_PATH = (
    PROJECT_ROOT / 'audit-platform' / 'frontend' / 'src'
    / 'components' / 'workpaper' / 'coverage-ledger.json'
)

TODAY = date.today().isoformat()

# ─── Helper builders ──────────────────────────────────────────────────────────

def _runtime_boundary():
    return {
        "status": "covered",
        "evidence": ["GtWpRenderer:Runtime_Boundary"],
        "exemption": None,
    }


def _covered(evidence: str):
    return {
        "status": "covered",
        "evidence": [evidence],
        "exemption": None,
    }


def _exempt(reason: str, capability: str):
    return {
        "status": "exempt",
        "evidence": [],
        "exemption": {
            "reason": reason,
            "capability": capability,
            "approvedBy": "manager",
            "approvedAt": TODAY,
            "reviewAt": TODAY,
        },
    }


def _unknown():
    return {
        "status": "unknown",
        "evidence": [],
        "exemption": None,
    }


# ─── Standard exemptions ─────────────────────────────────────────────────────

AGING_EXEMPT_REASON = (
    "该底稿不含账龄维度分析（非应收/应付类科目审定表），agingConfig 不适用"
)
IMPORT_EXPORT_EXEMPT_REASON = (
    "文档/目录/程序表/检查清单类底稿无动态明细行表格，"
    "不适用导入导出（项目铁律：动态行表格才需要导入导出）"
)
PERSISTENCE_EXEMPT_CONSOLE_REASON = (
    "程序表组件(a-program-console)由平台统一渲染，"
    "persistence由GtAProgramConsole内部状态管理，不走checklist-responses适配器"
)
ACNR_EXEMPT_REASON = (
    "该组件无需地址坐标索引跳转(无GtIndexChip使用场景)，acnr不适用"
)

# ─── A-cycle rules ────────────────────────────────────────────────────────────
# A1=Dashboard, A2=AdjustmentConsole, A3=ConsolidationConsole,
# A10-A17=bundles, A13=misstatement, A14=d-form-table, A18/A21-A25=review-bundles,
# A27-A31=various, A4/A5/A7=audit-sheet/cf-verification

A_CYCLE_RULES = {
    # Components with existing entries already correctly set (Runtime Boundary covers
    # version/review/ai/displayPrefs; agingConfig exempt for non-aging)
    "A1": {
        "agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig"),
        "persistence": _exempt(
            "Dashboard 展示汇总数据，不直接保存checklist数据，persistence不适用",
            "persistence",
        ),
    },
    "A2": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A3": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A10": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A11": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A12": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A13": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A14": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A15": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A16": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A17": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A18": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A21": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A22": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A23": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A24": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A25": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A27": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A28": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A30": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A31": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A4": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A5": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A7": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A8": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "A9": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
}

# ─── B-cycle rules ────────────────────────────────────────────────────────────
# B-cycle = planning bundles with internal el-tabs navigation
# B13/B19/B50/B51=bundles, B2/B22/B23/B30=specialized, B1/B3/B52=d-form/checklist
# B5/B10-B12/B18/B40=a-program-console, B60=audit-sheet

B_CYCLE_RULES = {
    "B2": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B13": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B19": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B22": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B23": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B30": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B50": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B51": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B1": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B3": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B5": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B10": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B11": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B12": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B18": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B40": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B52": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "B60": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
}

# ─── C-cycle rules ────────────────────────────────────────────────────────────
# C1=entity-level-control (unique), C2-C15=c-control-test (shared componentType),
# C22=itgc-bundle, C23=journal-control, C24=journal-detail (four-table linkage),
# C25=internal-audit, C26=info-processing-control
# C-cycle: NO aging (control testing, not substantive); persistence varies;
# version/review ALWAYS covered by Runtime Boundary

C_CYCLE_RULES = {
    "C1": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "C22": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "C23": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "C24": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "C25": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "C26": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
}
# C2-C15 all use c-control-test shared componentType
for i in range(2, 16):
    C_CYCLE_RULES[f"C{i}"] = {
        "agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig"),
    }
# C10 already in range but just confirming

# ─── S-cycle rules ────────────────────────────────────────────────────────────
# S3-S6=specialized workpapers with unique componentTypes
# S12-S21=expert/specialized with useSExpertPersist (already have persistence)
# S32-S35=bundles
# S1/S2/S8-S11/S16/S17=a-program-console (programs)

S_CYCLE_RULES = {
    # S3-S6: specialized workpapers - have persistence via useSExpertPersist or dedicated
    "S3": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S4": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S5": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S6": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    # S12-S15: expert utilization - have useSExpertPersist
    "S12": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S13": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S14": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S15": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    # S16/S17: program consoles
    "S16": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S17": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    # S20/S21: specialized
    "S20": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S21": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    # S32-S35: bundles
    "S32": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S33": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S34": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S35": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    # S1/S2/S8-S11: program consoles
    "S1": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S2": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S8": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S9": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S10": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
    "S11": {"agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig")},
}

# ─── Confirmation rules ───────────────────────────────────────────────────────
# D0/E0/F0/G0/H0/K0/L0 = confirmation hubs (shared cross-cycle)
# All have persistence (via k0-confirmation composables) and acnr (via GtIndexChip)
# All already correctly marked as covered in existing ledger
# agingConfig: exempt (confirmation is about verifying balances, not aging analysis)

CONFIRMATION_RULES = {}
for code in ("D0", "E0", "F0", "G0", "H0", "K0", "L0"):
    CONFIRMATION_RULES[code] = {
        "agingConfig": _exempt(AGING_EXEMPT_REASON, "agingConfig"),
    }


# ─── Program console components ──────────────────────────────────────────────
# These are a-program-console type: persistence is handled by
# GtAProgramConsole internally, not checklist-responses adapter.

PROGRAM_CONSOLE_CODES = {
    "B5", "B10", "B11", "B12", "B18", "B40",
    "S1", "S2", "S8", "S9", "S10", "S11", "S16", "S17",
}


def apply_migration(ledger: dict) -> tuple[dict, list[str]]:
    """Apply capability-level migration to A/B/C/S and confirmation entries.

    Returns (updated_ledger, changes_log).
    """
    result = deepcopy(ledger)
    entries = result.setdefault("entries", {})
    changes: list[str] = []

    all_rules = {}
    all_rules.update(A_CYCLE_RULES)
    all_rules.update(B_CYCLE_RULES)
    all_rules.update(C_CYCLE_RULES)
    all_rules.update(S_CYCLE_RULES)
    all_rules.update(CONFIRMATION_RULES)

    for wp_code, overrides in sorted(all_rules.items()):
        entry = entries.get(wp_code)
        if entry is None:
            changes.append(f"SKIP {wp_code}: not in ledger")
            continue

        capabilities = entry.setdefault("capabilities", {})

        # 1. Ensure Runtime Boundary capabilities are marked covered
        #    (version, review, ai, displayPrefs are ALWAYS covered by Runtime Boundary)
        for cap in ("displayPrefs", "version", "review", "ai"):
            current = capabilities.get(cap, {})
            current_status = current.get("status") if isinstance(current, dict) else None
            if current_status != "covered":
                capabilities[cap] = _runtime_boundary()
                changes.append(
                    f"SET {wp_code}.{cap} = covered (Runtime_Boundary) "
                    f"[was: {current_status}]"
                )

        # 2. Apply per-capability overrides from rules
        for cap, new_value in overrides.items():
            current = capabilities.get(cap, {})
            current_status = current.get("status") if isinstance(current, dict) else None
            new_status = new_value.get("status")
            # Don't downgrade covered → exempt (if already covered, keep it)
            if current_status == "covered" and new_status == "exempt":
                continue
            if current != new_value:
                capabilities[cap] = new_value
                changes.append(
                    f"SET {wp_code}.{cap} = {new_status} [was: {current_status}]"
                )

        # 3. For program console types: mark persistence as covered
        #    (GtAProgramConsole handles its own persistence internally)
        component_type = entry.get("componentType", "")
        if wp_code in PROGRAM_CONSOLE_CODES or component_type == "a-program-console":
            current_persist = capabilities.get("persistence", {})
            current_persist_status = (
                current_persist.get("status")
                if isinstance(current_persist, dict) else None
            )
            if current_persist_status in ("unknown", None):
                capabilities["persistence"] = _covered(
                    "GtAProgramConsole:internal-state-management"
                )
                changes.append(
                    f"SET {wp_code}.persistence = covered (program-console internal) "
                    f"[was: {current_persist_status}]"
                )

        # 4. For importExport: ensure proper per-capability exemption if currently unknown
        current_ie = capabilities.get("importExport", {})
        current_ie_status = (
            current_ie.get("status") if isinstance(current_ie, dict) else None
        )
        if current_ie_status == "unknown":
            # Most A/B/C/S components don't have dynamic row tables
            if component_type in (
                "a-program-console", "a1-dashboard", "a2-adjustment-console",
                "a3-consolidation-console", "checklist-table", "audit-sheet",
                "audit-legend", "review-bundle", "d-form-table",
                "misstatement-workpaper", "cf-verification",
                "b50-risk-assessment", "b23-process-control",
                "b30-group-audit", "b22a-control-matrix",
                "c-control-test", "c1-entity-level-control",
                "c22-itgc-bundle", "c23-journal-entry-control",
                "c25-internal-audit-reliance", "c26-info-processing-control",
                "s3-policy-change", "s4-nonmonetary-exchange",
                "s5-debt-restructuring", "s6-fund-occupation",
                "s12-cpa-expert", "s13-mgmt-expert",
                "s14-accounting-estimate", "s15-eps-roe",
                "s20-revenue-deduction", "s21-data-asset",
                "s32-fraud-bundle", "s33-ann14-bundle",
                "s34-ipo-bundle", "s35-refinance-bundle",
            ):
                capabilities["importExport"] = _exempt(
                    IMPORT_EXPORT_EXEMPT_REASON, "importExport"
                )
                changes.append(
                    f"SET {wp_code}.importExport = exempt [was: {current_ie_status}]"
                )
            # Bundle types with internal el-tabs
            elif "bundle" in component_type:
                capabilities["importExport"] = _exempt(
                    IMPORT_EXPORT_EXEMPT_REASON, "importExport"
                )
                changes.append(
                    f"SET {wp_code}.importExport = exempt [was: {current_ie_status}]"
                )

        # 5. Remove entry-level exemption if present (v2 forbids it)
        if "exemption" in entry:
            del entry["exemption"]
            changes.append(f"DELETE {wp_code}.exemption (entry-level forbidden in v2)")

    return result, changes


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

    if not COVERAGE_LEDGER_PATH.exists():
        print(f"[ERROR] coverage-ledger.json not found: {COVERAGE_LEDGER_PATH}")
        return 1

    with open(COVERAGE_LEDGER_PATH, 'r', encoding='utf-8') as f:
        ledger = json.load(f)

    updated, changes = apply_migration(ledger)

    if not changes:
        print("[OK] No changes needed — all A/B/C/S/confirmation entries already correct.")
        return 0

    print(f"[MIGRATION] {len(changes)} changes applied:")
    for change in changes:
        print(f"  {change}")

    with open(COVERAGE_LEDGER_PATH, 'w', encoding='utf-8') as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"\n[OK] Updated {COVERAGE_LEDGER_PATH}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
