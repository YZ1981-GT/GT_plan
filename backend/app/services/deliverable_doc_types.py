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
    ProjectType.capital_verification.value: [
        WordExportDocType.audit_report.value,
        "special_report",
    ],
    ProjectType.tax_audit.value: [
        WordExportDocType.audit_report.value,
        "special_report",
    ],
}

PRIOR_PERIOD_SCENARIOS = frozenset({
    "continuing_audit",
    "predecessor_auditor",
    "prior_unaudited",
})

# 专项报告子类型注册表 — 新增专项无需改核心逻辑（需求 20.2）
SPECIAL_REPORT_SUBTYPES: dict[str, str] = {
    "special_audit_report": "专项审计报告",
    "internal_control_assurance": "内控鉴证报告",
    "agreed_upon_procedures": "约定程序报告",
    "capital_verification_report": "验资报告",
    "tax_audit_report": "税审报告",
}


def register_doc_type(doc_type: str, label: str) -> None:
    """运行时注册新 doc_type（需求 20.1: 无需改核心逻辑即可扩展）"""
    DOC_TYPE_LABELS[doc_type] = label


def register_special_subtype(subtype: str, label: str) -> None:
    """注册新专项报告子类型"""
    SPECIAL_REPORT_SUBTYPES[subtype] = label


def doc_type_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(doc_type, doc_type)


def required_doc_types(project_type: str) -> list[str]:
    return list(
        REQUIRED_BY_PROJECT_TYPE.get(project_type, REQUIRED_BY_PROJECT_TYPE[ProjectType.annual.value])
    )


def is_extensible_doc_type(doc_type: str) -> bool:
    """任意非空字符串均可作为交付物类型管理"""
    return bool(doc_type and doc_type.strip())
