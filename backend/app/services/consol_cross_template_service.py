"""Sprint B.2 — 集团内多模板共存联动.

当合并项目模板 = SOE，但子公司 A 是 Listed 时：
- 共有章节 → 直接汇总（section_title 匹配）
- 子公司有 / 合并版无 → 数据归档不丢（标 _archived_from_child）
- 合并版有 / 子公司无 → 标 not_applicable + provenance 标识

API: translate_child_section / aggregate_cross_template / build_cross_template_provenance
"""
from __future__ import annotations

import logging
from copy import deepcopy
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.services.note_template_diff import (
    adapt_table_data,
    classify_section_mapping,
    load_diff_data,
)

logger = logging.getLogger(__name__)

__all__ = [
    "translate_child_section",
    "aggregate_cross_template",
    "build_cross_template_provenance",
]


# ---------------------------------------------------------------------------
# B.2.1 translate_child_section
# ---------------------------------------------------------------------------

def translate_child_section(
    child_section: dict[str, Any],
    from_type: str,
    to_type: str,
    diff_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将子公司章节数据翻译到合并版模板格式."""
    if not isinstance(child_section, dict):
        return {"_not_applicable": True, "reason": "invalid_input"}

    if from_type == to_type:
        return deepcopy(child_section)

    if diff_data is None:
        diff_data = load_diff_data()

    section_id = child_section.get("section_id", "")
    classification, metadata = classify_section_mapping(
        section_id, diff_data, source_type=from_type,
    )

    if classification == "common":
        result = deepcopy(child_section)
        result["_translated"] = True
        result["_translation_type"] = "common"
        if metadata:
            result["_target_section_id"] = metadata.get("target_section_id", "")
        return result

    if classification == "format_diff":
        result = deepcopy(child_section)
        table_data = result.get("table_data", {})
        if table_data and metadata:
            target_format = metadata.get(
                f"{to_type}_format", metadata.get("listed_format", {}),
            )
            field_mapping = metadata.get("field_mapping")
            result["table_data"] = adapt_table_data(table_data, target_format, field_mapping)
        result["_translated"] = True
        result["_translation_type"] = "format_diff"
        if metadata:
            result["_target_section_id"] = metadata.get("target_section_id", "")
        return result

    if classification == "source_only":
        result = deepcopy(child_section)
        result["_archived_from_child"] = True
        result["_translation_type"] = "source_only"
        result["_archive_reason"] = (
            f"Section '{section_id}' exists in {from_type} but not in {to_type}"
        )
        return result

    if classification == "target_only":
        return {
            "section_id": section_id,
            "_not_applicable": True,
            "_translation_type": "target_only",
            "reason": f"Section exists in {to_type} only, child has no data",
        }

    # unknown — 保守归档
    result = deepcopy(child_section)
    result["_archived_from_child"] = True
    result["_translation_type"] = "unknown"
    return result


# ---------------------------------------------------------------------------
# B.2.2 aggregate_cross_template
# ---------------------------------------------------------------------------

async def aggregate_cross_template(
    consol_project_id: UUID,
    section_id: str,
    year: int,
    children: list[dict[str, Any]],
    consol_type: str = "soe",
    db: Any = None,
) -> dict[str, Any]:
    """跨模板汇总：对齐不同模板子公司的章节数据后汇总."""
    diff_data = load_diff_data()

    translated_sections: list[dict[str, Any]] = []
    archived_sections: list[dict[str, Any]] = []
    not_applicable_children: list[dict[str, Any]] = []
    child_contributions: list[dict[str, Any]] = []

    for child in children:
        child_template = child.get("template_type", consol_type)
        section_data = child.get("section_data", {})
        project_id = child.get("project_id", "")
        company_name = child.get("company_name", "")

        translated = translate_child_section(
            section_data, from_type=child_template, to_type=consol_type,
            diff_data=diff_data,
        )

        if translated.get("_archived_from_child"):
            archived_sections.append({
                "project_id": str(project_id),
                "company_name": company_name,
                "template_type": child_template,
                "section_data": translated,
            })
            continue

        if translated.get("_not_applicable"):
            not_applicable_children.append({
                "project_id": str(project_id),
                "company_name": company_name,
                "template_type": child_template,
                "reason": translated.get("reason", ""),
            })
            continue

        translated_sections.append(translated)
        amount = _extract_total_amount(translated.get("table_data", {}))
        child_contributions.append({
            "project_id": str(project_id),
            "company_name": company_name,
            "template_type": child_template,
            "amount": amount,
        })

    aggregated_rows = _merge_translated_rows(translated_sections)
    provenance = build_cross_template_provenance(child_contributions)

    return {
        "section_id": section_id,
        "year": year,
        "consol_project_id": str(consol_project_id),
        "aggregated_rows": aggregated_rows,
        "provenance": provenance,
        "archived_sections": archived_sections,
        "not_applicable_children": not_applicable_children,
        "child_count": len(children),
        "translated_count": len(translated_sections),
    }


# ---------------------------------------------------------------------------
# B.2.3 build_cross_template_provenance
# ---------------------------------------------------------------------------

def build_cross_template_provenance(
    child_contributions: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建跨模板 provenance.

    Returns: {"contributions": [...], "has_cross_template": bool,
              "template_types_involved": list[str]}
    """
    if not child_contributions:
        return {"contributions": [], "has_cross_template": False, "template_types_involved": []}

    template_types: set[str] = set()
    contributions: list[dict[str, Any]] = []

    for contrib in child_contributions:
        t_type = contrib.get("template_type", "unknown")
        template_types.add(t_type)
        contributions.append({
            "project_id": contrib.get("project_id", ""),
            "company_name": contrib.get("company_name", ""),
            "template_type": t_type,
            "amount": contrib.get("amount"),
        })

    sorted_types = sorted(template_types)
    return {
        "contributions": contributions,
        "has_cross_template": len(sorted_types) > 1,
        "template_types_involved": sorted_types,
    }


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _extract_total_amount(table_data: dict[str, Any]) -> Decimal | None:
    """从 table_data 提取合计行金额."""
    if not isinstance(table_data, dict):
        return None
    rows = table_data.get("rows", [])
    if not isinstance(rows, list):
        return None
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        if row.get("row_type") == "total" or row.get("is_total"):
            values = row.get("values", {})
            if isinstance(values, dict):
                for val in values.values():
                    if val is not None:
                        try:
                            return Decimal(str(val))
                        except Exception:
                            continue
    return None


def _merge_translated_rows(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并多个翻译后章节的行数据."""
    all_rows: list[dict[str, Any]] = []
    for section in sections:
        table_data = section.get("table_data", {})
        if isinstance(table_data, dict):
            rows = table_data.get("rows", [])
            if isinstance(rows, list):
                all_rows.extend(rows)
    return all_rows
