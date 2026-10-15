"""附注正文导入、内容模板与原子批量应用 API schema。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class OwnerScope(str, Enum):
    personal = "personal"
    group = "group"


class BatchSourceKind(str, Enum):
    upload = "upload"
    knowledge = "knowledge"
    content_template = "content_template"


class BatchApplyMode(str, Enum):
    replace = "replace"
    append = "append"


class NoteSectionKind(str, Enum):
    narrative = "narrative"
    account_explanation = "account_explanation"
    container = "container"


class MatchConfidence(str, Enum):
    confirmed = "confirmed"
    candidate = "candidate"
    manual_required = "manual_required"


class PreviewCategory(str, Enum):
    recommended = "recommended"
    review = "review"
    unavailable = "unavailable"


class ParsedSourceSection(StrictSchema):
    source_id: str = Field(min_length=1, max_length=160)
    section_code: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    level: int = Field(default=1, ge=1, le=10)
    parent_source_id: str | None = Field(default=None, max_length=160)
    html: str = Field(default="", max_length=524_288)
    confidence: MatchConfidence = MatchConfidence.candidate
    warnings: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedSource(StrictSchema):
    source_kind: BatchSourceKind
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    #: 与 ``note_document_parser.MAX_SECTIONS`` 同值（解析结果原样回传预览 / 写入；不跟着改就「解析成功、预览 422」）
    sections: list[ParsedSourceSection] = Field(default_factory=list, max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    needs_ocr: bool = False


class ParseKnowledgeRequest(StrictSchema):
    year: int = Field(ge=2000, le=2200)
    doc_ids: list[UUID] = Field(min_length=1, max_length=5)


class NoteTextSectionItem(StrictSchema):
    id: UUID
    section_id: str | None = None
    note_section: str
    section_title: str
    section_kind: NoteSectionKind
    parent_section_id: str | None = None
    level: int | None = None
    sort_index: int
    content_type: str | None = None
    text_content: str | None = None
    content_hash: str
    updated_at: datetime | None = None
    status: str
    is_stale: bool


class SnapshotPreviewRequest(StrictSchema):
    year: int = Field(ge=2000, le=2200)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    owner_scope: OwnerScope


class SaveContentTemplateRequest(SnapshotPreviewRequest):
    snapshot_digest: str = Field(min_length=64, max_length=64)


class QualitySummary(StrictSchema):
    total: int = 0
    with_content: int = 0
    empty: int = 0
    placeholder: int = 0
    draft: int = 0
    stale: int = 0
    entity_specific: int = 0
    account_explanation: int = 0
    high_risk: int = 0


class SnapshotPreviewResponse(StrictSchema):
    snapshot_digest: str
    content_hash: str
    byte_size: int
    source_project_name: str
    source_year: int
    template_type: str
    report_scope: str
    quality_summary: QualitySummary


class ContentTemplateVersionMeta(StrictSchema):
    id: UUID
    version_no: int
    schema_version: int
    source_project_id: UUID
    source_project_name: str
    source_year: int
    template_type: str
    report_scope: str
    quality_summary: dict[str, Any]
    content_hash: str
    byte_size: int
    created_by: UUID | None = None
    created_at: datetime


class ContentTemplateListItem(StrictSchema):
    id: UUID
    name: str
    description: str | None = None
    owner_scope: OwnerScope
    current_version: ContentTemplateVersionMeta | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class BatchSource(StrictSchema):
    source_kind: BatchSourceKind
    parsed_source: ParsedSource | None = None
    template_version_id: UUID | None = None
    template_content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    knowledge_doc_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_shape(self) -> "BatchSource":
        if self.source_kind == BatchSourceKind.content_template:
            if self.template_version_id is None or self.template_content_hash is None:
                raise ValueError("内容模板来源必须固定 template_version_id 与 content_hash")
            if self.parsed_source is not None or self.knowledge_doc_ids:
                raise ValueError("内容模板来源不能携带客户端正文或知识库 ID")
        else:
            if self.parsed_source is None:
                raise ValueError("上传或知识库来源必须携带解析结果")
            if self.template_version_id is not None or self.template_content_hash is not None:
                raise ValueError("非模板来源不能携带模板版本")
            if self.source_kind == BatchSourceKind.knowledge and not self.knowledge_doc_ids:
                raise ValueError("知识库来源必须携带文档 ID 供服务端重新判权")
        return self


class ManualMapping(StrictSchema):
    source_id: str = Field(min_length=1, max_length=160)
    target_note_id: UUID


class VariableReplacement(StrictSchema):
    replacement_id: str
    variable: str
    old_value: str
    new_value: str
    reversible: bool = True


class BatchPreviewRequest(StrictSchema):
    year: int = Field(ge=2000, le=2200)
    source: BatchSource
    #: 每个来源章节至多一条，上限与解析章节上限同值
    manual_mappings: list[ManualMapping] = Field(default_factory=list, max_length=1000)
    #: 用户撤销的变量替换（ID 按来源章节确定性生成）；apply 必须原样回传，否则重算的拟写入内容对不上
    revoked_replacement_ids: list[str] = Field(default_factory=list, max_length=500)


class BatchPreviewItem(StrictSchema):
    source_id: str
    target_note_id: UUID | None = None
    target_note_section: str | None = None
    match_kind: str
    evidence: str
    confidence: MatchConfidence
    category: PreviewCategory
    unavailable_reason: str | None = None
    before_html: str = ""
    proposed_html: str = ""
    before_hash: str
    proposed_hash: str
    expected_updated_at: datetime | None = None
    default_mode: BatchApplyMode = BatchApplyMode.replace
    quality_flags: list[str] = Field(default_factory=list)
    replacements: list[VariableReplacement] = Field(default_factory=list)


class BatchPreviewResponse(StrictSchema):
    preview_digest: str
    source: BatchSource
    items: list[BatchPreviewItem]
    summary: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class BatchApplySelection(StrictSchema):
    source_id: str = Field(min_length=1, max_length=160)
    target_note_id: UUID
    mode: BatchApplyMode
    expected_updated_at: datetime | None = None
    before_hash: str = Field(min_length=64, max_length=64)
    proposed_hash: str = Field(min_length=64, max_length=64)
    #: 兼容旧客户端；服务端**不使用**（R-09：只写服务端重算的预览结果）
    proposed_html: str | None = Field(default=None, max_length=524_288)


class BatchApplyRequest(StrictSchema):
    """apply 须携带与 preview 相同的来源 / 手工映射 / 撤销项：服务端据此重算并校验 digest。"""

    year: int = Field(ge=2000, le=2200)
    source: BatchSource
    preview_digest: str = Field(min_length=64, max_length=64)
    #: 每个目标章节至多一条（见下方校验），上限按项目章节数（design §11.2「单次 batch apply 章节数」）
    selections: list[BatchApplySelection] = Field(min_length=1, max_length=500)
    manual_mappings: list[ManualMapping] = Field(default_factory=list, max_length=1000)
    revoked_replacement_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_targets(self) -> "BatchApplyRequest":
        ids = [item.target_note_id for item in self.selections]
        if len(ids) != len(set(ids)):
            raise ValueError("同一目标章节不能在一个批次中重复")
        source_ids = [item.source_id for item in self.selections]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("同一来源章节不能在一个批次中重复")
        return self


class BatchApplyResponse(StrictSchema):
    application_id: UUID
    mutation_id: str
    applied_count: int
    summary: dict[str, int]
    changed_note_ids: list[UUID]
    warnings: list[str] = Field(default_factory=list)
    replayed: bool = False


class TemplateDeleteResponse(StrictSchema):
    id: UUID
    deleted: bool
