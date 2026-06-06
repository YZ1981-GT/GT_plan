"""交付物 doc_type 可扩展配置 — 不硬编码核心逻辑"""

from __future__ import annotations

from app.models.base import ProjectType
from app.models.phase13_models import WordExportDocType

DOC_TYPE_LABELS: dict[str, str] = {
    WordExportDocType.audit_report.value: "审计报告正文",
    WordExportDocType.financial_report.value: "财务报表",
    WordExportDocType.disclosure_notes.value: "附注",
    WordExportDocType.full_package.value: "全套包",
    "special_report": "专项报告",
}

STANDARD_TRIO = [
    WordExportDocType.audit_report.value,
    WordExportDocType.financial_report.value,
    WordExportDocType.disclosure_notes.value,
]

REQUIRED_BY_PROJECT_TYPE: dict[str, list[str]] = {
    ProjectType.annual.value: list(STANDARD_TRIO),
    ProjectType.ipo.value: list(STANDARD_TRIO),
    ProjectType.special.value: [
        WordExportDocType.audit_report.value,
        "special_report",
    ],
    ProjectType.internal_control.value: [
        WordExportDocType.audit_report.value,
    ],
}

PRIOR_PERIOD_SCENARIOS = frozenset({
    "continuing_audit",
    "predecessor_auditor",
    "prior_unaudited",
})


def doc_type_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(doc_type, doc_type)


def required_doc_types(project_type: str) -> list[str]:
    return list(
        REQUIRED_BY_PROJECT_TYPE.get(project_type, REQUIRED_BY_PROJECT_TYPE[ProjectType.annual.value])
    )


def is_extensible_doc_type(doc_type: str) -> bool:
    """任意非空字符串均可作为交付物类型管理"""
    return bool(doc_type and doc_type.strip())
