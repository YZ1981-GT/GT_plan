# -*- coding: utf-8 -*-
"""B60 P3: mapping triggers + cross_wp_references CW-417~422 + CW-96 fix."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"D:/GT_plan")


def patch_mapping() -> list[str]:
    mapping_path = ROOT / "backend/data/wp_account_mapping.json"
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    updates = {
        "B60-1": {
            "trigger": "must_have",
            "must_have": True,
            "audit_stage": "risk_assessment",
            "platform_note": "B60 chapter3 hours; index B60-1",
        },
        "B60-2-1": {
            "trigger": "conditional",
            "applies_when": "needs_it_audit",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60-2-2": {
            "trigger": "conditional",
            "applies_when": "it_team_executes",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60-2-3": {
            "trigger": "conditional",
            "applies_when": "it_team_executes",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60-3": {
            "trigger": "conditional",
            "applies_when": "uses_expert",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60A": {
            "trigger": "conditional",
            "applies_when": "integrated_audit",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60B": {
            "trigger": "conditional",
            "applies_when": "listed_or_ipo",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60C": {
            "trigger": "conditional",
            "applies_when": "soe_annual",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
        "B60D": {
            "trigger": "conditional",
            "applies_when": "needs_regulatory_filing",
            "must_have": False,
            "audit_stage": "risk_assessment",
        },
    }
    changed: list[str] = []
    for m in data["mappings"]:
        code = m.get("wp_code")
        if code == "B60":
            m["platform_fields"] = "wp_platform_fields/B60.json"
            m["attachment_matrix"] = [
                "integrated_audit->B60A",
                "listed_or_ipo->B60B",
                "soe_annual->B60C",
                "needs_regulatory_filing->B60D",
                "needs_it_audit->B60-2-1",
                "it_team_executes->B60-2-2/B60-2-3",
                "uses_expert->B60-3",
                "B60-1 always",
            ]
            changed.append("B60")
        if code in updates:
            m.update(updates[code])
            changed.append(code)
    mapping_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def patch_xref() -> list[str]:
    xref_path = ROOT / "backend/data/cross_wp_references.json"
    xref = json.loads(xref_path.read_text(encoding="utf-8"))
    refs = xref["references"]
    for r in refs:
        if r.get("ref_id") == "CW-96":
            r["description"] = "H1 depreciation policy -> B60 overall strategy"
            r["targets"] = [
                {
                    "wp_code": "B60",
                    "sheet": "总体审计策略",
                    "cell": "重大会计实务_固定资产折旧政策",
                    "formula": None,
                    "cell_label": "固定资产折旧政策",
                    "address": "B60:总体审计策略:重大会计实务_固定资产折旧政策",
                }
            ]
            r["category"] = "cross_module"

    new_refs = [
        {
            "ref_id": "CW-417",
            "description": "B60 ch5 materiality conclusion -> B19-1",
            "source_wp": "B60",
            "source_sheet": "总体审计策略",
            "source_cell": "重要性水平结论",
            "targets": [
                {
                    "wp_code": "B19-1",
                    "sheet": "重要性水平确定表",
                    "cell": "PM_TE_AMPT",
                    "formula": None,
                    "cell_label": "PM/TE/AMPT",
                    "address": "B19-1:重要性水平确定表:PM_TE_AMPT",
                }
            ],
            "category": "materiality_linkage",
            "severity": "warning",
            "source_address": "B60:总体审计策略:重要性水平结论",
        },
        {
            "ref_id": "CW-418",
            "description": "B60 ch5 materiality calc -> B15",
            "source_wp": "B60",
            "source_sheet": "总体审计策略",
            "source_cell": "重要性水平计算过程",
            "targets": [
                {
                    "wp_code": "B15",
                    "sheet": "重要性计算表",
                    "cell": "计算过程",
                    "formula": None,
                    "cell_label": "重要性计算过程",
                    "address": "B15:重要性计算表:计算过程",
                }
            ],
            "category": "materiality_linkage",
            "severity": "recommended",
            "source_address": "B60:总体审计策略:重要性水平计算过程",
        },
        {
            "ref_id": "CW-419",
            "description": "B60 ch6 risk summary <-> B50 risk_id",
            "source_wp": "B60",
            "source_sheet": "总体审计策略",
            "source_cell": "风险ID/B50行号",
            "targets": [
                {
                    "wp_code": "B50",
                    "sheet": "风险汇总",
                    "cell": "risk_id",
                    "formula": None,
                    "cell_label": "risk_id",
                    "address": "B50:风险汇总:risk_id",
                }
            ],
            "category": "cross_module",
            "severity": "warning",
            "source_address": "B60:总体审计策略:风险ID/B50行号",
            "note": "Row fields risk_id/scot_id on SCOT+ link to B50",
        },
        {
            "ref_id": "CW-420",
            "description": "B60 ch7 SCOT+ -> cycle procedures (scot_id)",
            "source_wp": "B60",
            "source_sheet": "总体审计策略",
            "source_cell": "SCOT+_循环代码_程序索引",
            "targets": [
                {
                    "target_module": "cycle_procedures",
                    "target_field": "scot_id",
                    "link_type": "plan_to_procedure",
                }
            ],
            "category": "cross_module",
            "severity": "recommended",
            "source_address": "B60:总体审计策略:SCOT+_循环代码_程序索引",
        },
        {
            "ref_id": "CW-421",
            "description": "B60 -> AuditPlan plan_version/materiality_reference/attachment_flags",
            "source_wp": "B60",
            "source_sheet": "总体审计策略",
            "source_cell": "计划版本与适用性矩阵",
            "targets": [
                {"target_module": "audit_plan", "target_field": "plan_version", "link_type": "data_source"},
                {
                    "target_module": "audit_plan",
                    "target_field": "materiality_reference",
                    "link_type": "data_source",
                },
                {
                    "target_module": "audit_plan",
                    "target_field": "key_focus_areas.b60_attachment_flags",
                    "link_type": "data_source",
                },
            ],
            "category": "cross_module",
            "severity": "recommended",
            "source_address": "B60:总体审计策略:计划版本与适用性矩阵",
            "note": "Store matrix on AuditPlan.key_focus_areas.b60_attachment_flags; bump plan_version on ch15",
        },
        {
            "ref_id": "CW-422",
            "description": "B60D filing archive <-> AuditPlan.plan_version",
            "source_wp": "B60D",
            "source_sheet": "报送函",
            "source_cell": "对应B60版本日期",
            "targets": [
                {
                    "target_module": "audit_plan",
                    "target_field": "plan_version",
                    "link_type": "consistency_check",
                },
                {
                    "target_module": "audit_plan",
                    "target_field": "updated_at",
                    "link_type": "consistency_check",
                },
            ],
            "category": "cross_module",
            "severity": "warning",
            "source_address": "B60D:报送函:对应B60版本日期",
        },
    ]
    existing = {r["ref_id"] for r in refs}
    added: list[str] = []
    for nr in new_refs:
        if nr["ref_id"] not in existing:
            refs.append(nr)
            added.append(nr["ref_id"])
        else:
            for i, r in enumerate(refs):
                if r["ref_id"] == nr["ref_id"]:
                    refs[i] = nr
                    added.append(nr["ref_id"] + "(replaced)")
                    break
    xref["stats"]["total"] = len(refs)
    note = xref["stats"].get("coverage_note") or ""
    if "CW-417" not in note:
        xref["stats"]["coverage_note"] = note + " + B60 P3 (CW-417~CW-422)"
    xref_path.write_text(json.dumps(xref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def main():
    print("mapping:", patch_mapping())
    print("xref:", patch_xref())


if __name__ == "__main__":
    main()
