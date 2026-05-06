"""
Pydantic v2 schemas for seed JSON files validation.

Each seed file in backend/data/ has a corresponding BaseModel here.
Used by scripts/validate_seed_files.py to ensure seed data integrity.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─── audit_report_templates_seed.json ───────────────────────────────────────


class AuditReportSection(BaseModel):
    section_name: str
    section_order: int
    is_required: bool
    template_text: str


class AuditReportTemplate(BaseModel):
    opinion_type: str
    company_type: str
    sections: list[AuditReportSection]


class AuditReportTemplatesSeed(BaseModel):
    description: str
    placeholders_doc: dict[str, str]
    templates: list[AuditReportTemplate]


# ─── report_config_seed.json ────────────────────────────────────────────────


class ReportConfigRow(BaseModel):
    row_code: str
    row_number: int
    row_name: str
    indent_level: int
    is_total_row: bool
    formula: str | None = None
    formula_category: str | None = None
    formula_description: str | None = None
    formula_source: str | None = None
    parent_row_code: str | None = None


class ReportConfig(BaseModel):
    report_type: str
    applicable_standard: str
    template_variant: str
    scope: str
    description: str
    rows: list[ReportConfigRow]


# report_config_seed.json is a list of ReportConfig
ReportConfigSeed = list[ReportConfig]


# ─── note_templates_seed.json ───────────────────────────────────────────────


class NoteTableRow(BaseModel):
    label: str
    account_codes: list[str]
    is_total: bool


class NoteTableTemplate(BaseModel):
    headers: list[str]
    rows: list[NoteTableRow]


class NoteAccountMapping(BaseModel):
    account_name: str
    report_row_code: str
    note_section: str
    section_title: str
    content_type: str
    sort_order: int
    check_roles: list[str]
    table_template: NoteTableTemplate


class NoteTemplatesSeed(BaseModel):
    description: str
    account_mapping_template: list[NoteAccountMapping]
    check_presets: dict[str, list[str]]
    wide_table_presets: dict[str, Any] = Field(default_factory=dict)


# ─── wp_account_mapping.json ────────────────────────────────────────────────


class WpAccountMappingEntry(BaseModel):
    wp_code: str
    cycle: str
    wp_name: str
    account_codes: list[str]
    account_name: str
    report_row: str | None = None
    note_section: str | None = None
    is_primary: bool | None = None
    template_file: str | None = None


class WpAccountMappingSeed(BaseModel):
    description: str
    version: str
    mappings: list[WpAccountMappingEntry]


# ─── independence_questions_annual.json ─────────────────────────────────────


class IndependenceQuestion(BaseModel):
    id: int
    category: str
    question: str


# independence_questions_annual.json is a list of IndependenceQuestion
IndependenceQuestionsSeed = list[IndependenceQuestion]


# ─── qc_rule_definitions_seed.json ──────────────────────────────────────────


class QcRuleDefinitionEntry(BaseModel):
    rule_code: str
    severity: str
    scope: str
    category: str
    title: str
    description: str | None = None
    standard_ref: list[str] | None = None
    expression_type: str = "python"
    expression: str | None = None
    parameters_schema: dict[str, Any] | None = None
    enabled: bool = True
    version: int = 1


# qc_rule_definitions_seed.json is a list of QcRuleDefinitionEntry
QcRuleDefinitionsSeed = list[QcRuleDefinitionEntry]


# ─── audit_log_rules_seed.json ──────────────────────────────────────────────


class AuditLogRuleEntry(BaseModel):
    """审计日志规则条目（结构与 QcRuleDefinitionEntry 一致）"""

    rule_code: str
    severity: str
    scope: str
    category: str
    title: str
    description: str | None = None
    standard_ref: list[str] | None = None
    expression_type: str = "python"
    expression: str | None = None
    parameters_schema: dict[str, Any] | None = None
    enabled: bool = True
    version: int = 1


# audit_log_rules_seed.json is a list of AuditLogRuleEntry
AuditLogRulesSeed = list[AuditLogRuleEntry]
