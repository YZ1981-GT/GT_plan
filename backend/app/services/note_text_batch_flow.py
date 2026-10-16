"""附注正文批量导入：来源解析与服务端预览编排（端点只做鉴权与错误映射）。

spec: disclosure-note-doc-upload-and-batch-fill Task 20 / 25 / 33（第二轮复盘 R-01）

来源可信度在这里统一裁定：
- 上传：正文由客户端回传（用户可在双栏里二次编辑），服务端重新消毒、限额并由 preview_digest 绑定；
  文件元数据（名称 / hash / 字节数 / 格式）由 parse-upload 用服务端密钥签名，回传时验签，
  审计记录不吃客户端自报值；
- 知识库：每次 preview / apply 都经 ``KnowledgeIndexService.load_documents`` 重新逐篇判权，版本以服务端为准；
- 内容模板：正文只从不可变版本读取，客户端不能携带正文；复核可见性与固定 content_hash。
客户端回传的章节 metadata 一律丢弃（只留 ``doc_id``）：它会影响章类型门控与按编号匹配。
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.core import Project
from app.models.note_content_template_models import NoteContentTemplate, NoteContentTemplateVersion
from app.services.note_content_template_service import can_view_template
from app.services.note_document_parser import (
    MAX_SECTION_HTML_BYTES,
    MAX_SECTIONS,
    MAX_UPLOAD_BYTES,
    ParsedSection,
    ParseError,
    ParseResult,
    parse_docx,
    parse_pdf,
    parse_text_source,
)
from app.services.note_section_tree_locator import source_parent_ids
from app.services.note_text_batch_service import (
    ManualMappingError,
    SourceContext,
    build_preview,
    load_target_sections,
    locate_sources,
    resolve_target_context,
    tree_warnings,
    validate_mappings,
)

__all__ = [
    "MAX_BATCH_SOURCE_BYTES",
    "ResolvedSource",
    "SourceError",
    "build_target_vars",
    "compute_preview",
    "knowledge_source_payload",
    "parse_upload_bytes",
    "resolve_source",
    "upload_source_payload",
]

#: design §11.2「整套 text_content」硬上限：一次来源的全部章节正文字节和
MAX_BATCH_SOURCE_BYTES = 5 * 1024 * 1024

_DOCX_MIMES = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip", "application/x-zip-compressed", "application/octet-stream",
})
_PDF_MIMES = frozenset({"application/pdf", "application/x-pdf", "application/octet-stream"})
_SIGNED_KEYS = ("file_name", "file_hash", "byte_size", "file_format")


class SourceError(Exception):
    """来源不可用 / 非法（端点按 ``status`` 返回，``code`` 进 ``detail.error_code``）。"""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ResolvedSource:
    kind: str
    sections: list[ParsedSection]
    context: SourceContext
    identity: dict[str, Any]          # 进 preview_digest
    audit_metadata: dict[str, Any]    # 进 note_text_batch_applications.source_metadata
    entity_name: str | None = None
    template_version_id: UUID | None = None
    template_content_hash: str | None = None
    warnings: list[str] = field(default_factory=list)


# ── 上传 ─────────────────────────────────────────────────────────────────────


def _basename(filename: str | None) -> str:
    return (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:255]


def parse_upload_bytes(filename: str | None, content_type: str | None, data: bytes) -> tuple[str, ParseResult]:
    """扩展名 + MIME + 文件签名三重校验后解析（CPU 密集，端点放线程池调用）。"""
    name = _basename(filename).lower()
    fmt = "docx" if name.endswith(".docx") else "pdf" if name.endswith(".pdf") else None
    if fmt is None:
        raise ParseError("UNSUPPORTED_FILE", "仅支持 .docx 或 .pdf 文件")
    mime = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if mime not in (_DOCX_MIMES if fmt == "docx" else _PDF_MIMES):
        raise ParseError("UNSUPPORTED_FILE", "文件类型与扩展名不符")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ParseError("FILE_TOO_LARGE", f"文件超过上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
    signed = data.startswith(b"PK\x03\x04") if fmt == "docx" else b"%PDF-" in data[:1024]
    if not signed:
        raise ParseError("UNSUPPORTED_FILE", "文件内容与扩展名不符（文件签名校验失败）")
    result = parse_docx(data) if fmt == "docx" else parse_pdf(data)
    if result.needs_ocr and not result.sections:
        raise ParseError("PDF_NEEDS_OCR", "PDF 不含可提取文本，可能是扫描件；请上传文字版，或先上传知识库完成 OCR")
    if not result.sections:
        raise ParseError("NO_PARSEABLE_TEXT", "未能从文件中解析出任何章节")
    return fmt, result


def _signing_key() -> bytes:
    """由服务端密钥派生的专用签名键（域分离：不与 JWT 签名共用同一把键）。"""
    return hashlib.sha256(b"note-text-batch/upload-source/v1\x00" + settings.JWT_SECRET_KEY.encode("utf-8")).digest()


def _signature(meta: dict[str, Any], *, project_id: UUID, user_id: UUID) -> str:
    """绑定项目 + 解析人 + 文件元数据：防止跨项目 / 跨用户复用，也防止伪造审计记录里的文件信息。"""
    payload = json.dumps({"project_id": str(project_id), "user_id": str(user_id),
                          **{k: meta.get(k) for k in _SIGNED_KEYS}}, sort_keys=True, ensure_ascii=False)
    return hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _section_payload(section: ParsedSection, parent_id: str | None = None) -> dict[str, Any]:
    return {
        "source_id": section.source_id[:160],
        "title": (section.title or "").strip()[:500] or "（无标题）",
        "level": min(max(int(section.level or 1), 1), 10),
        # 章节树上级（AC-1.6，左栏按树显示）；定位时服务端按顺序与层级重算，不信回传值
        "parent_source_id": parent_id[:160] if parent_id else None,
        "html": section.html or "",
        "confidence": section.confidence,
        "warnings": list(section.warnings)[:50],
        "metadata": {},
    }


def upload_source_payload(fmt: str, filename: str | None, data: bytes, result: ParseResult, *,
                          project_id: UUID, user_id: UUID) -> dict[str, Any]:
    """parse-upload 响应（``ParsedSource`` 形态）；元数据带服务端签名，preview / apply 原样回传。"""
    meta: dict[str, Any] = {
        "file_name": _basename(filename), "file_hash": result.file_hash or hashlib.sha256(data).hexdigest(),
        "byte_size": len(data), "file_format": fmt,
    }
    meta["signature"] = _signature(meta, project_id=project_id, user_id=user_id)
    parents = source_parent_ids(result.sections)
    return {"source_kind": "upload", "source_metadata": meta,
            "sections": [_section_payload(s, parents.get(s.source_id)) for s in result.sections],
            "warnings": list(result.warnings), "needs_ocr": False}


# ── 知识库 ───────────────────────────────────────────────────────────────────


async def _visible_documents(db: AsyncSession, doc_ids: list[UUID], *, user: Any, project_id: UUID) -> list[dict]:
    from app.services.knowledge_index_service import KnowledgeIndexService

    return await KnowledgeIndexService(db).load_documents(doc_ids, user=user, project_id=project_id)


async def knowledge_source_payload(db: AsyncSession, *, project_id: UUID, user: Any,
                                   doc_ids: list[UUID]) -> dict[str, Any]:
    """逐篇判权后解析；不可见文档只给不区分原因的提示（不泄露存在性，AC-5.3）。"""
    docs = await _visible_documents(db, doc_ids, user=user, project_id=project_id)
    warnings: list[str] = []
    missing = len({str(d) for d in doc_ids}) - len(docs)
    if missing:
        warnings.append(f"{missing} 篇文档不可用（无权限、已删除或不存在），已跳过")
    sections: list[dict[str, Any]] = []
    for doc in docs:
        name = doc.get("document_name") or "未命名文档"
        result = parse_text_source(doc.get("content") or "", source_kind="knowledge",
                                   doc_id=doc["source_id"], doc_name=name)
        if not result.sections:
            warnings.append(f"《{name}》正文为空（扫描件需先在知识库完成 OCR）")
            continue
        warnings.extend(f"《{name}》：{w}" for w in result.warnings)
        parents = source_parent_ids(result.sections)  # 每篇各自成树
        for section in result.sections:
            item = _section_payload(section)
            # 多篇文档的解析 ID 会撞（每篇都从 s1 起编）⇒ 按文档命名空间
            item["source_id"] = f"{doc['source_id']}:{section.source_id}"[:160]
            parent = parents.get(section.source_id)
            item["parent_source_id"] = f"{doc['source_id']}:{parent}"[:160] if parent else None
            item["metadata"] = {"doc_id": doc["source_id"]}
            sections.append(item)
    if not sections:
        raise SourceError("NO_PARSEABLE_TEXT", "所选文档均不可用或正文为空：" + "；".join(warnings))
    if len(sections) > MAX_SECTIONS:
        warnings.append(f"解析章节数 {len(sections)} 超过上限 {MAX_SECTIONS}，已截断")
        sections = sections[:MAX_SECTIONS]
    documents = [{"doc_id": d["source_id"], "document_name": d.get("document_name"),
                  "doc_version": d.get("doc_version")} for d in docs]
    return {"source_kind": "knowledge", "source_metadata": {"documents": documents},
            "sections": sections, "warnings": warnings, "needs_ocr": False}


# ── preview / apply 共用：服务端重建来源 ─────────────────────────────────────


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _client_sections(parsed: Any, kind: str) -> list[ParsedSection]:
    """客户端回传章节：查重、限额，metadata 只留 ``doc_id``。"""
    if _enum_value(parsed.source_kind) != kind:
        raise SourceError("SOURCE_KIND_MISMATCH", "来源类型与解析结果不一致，请重新解析")
    if not parsed.sections:
        raise SourceError("EMPTY_SOURCE", "来源没有任何章节")
    seen: set[str] = set()
    total = 0
    out: list[ParsedSection] = []
    for s in parsed.sections:
        if s.source_id in seen:
            raise SourceError("DUPLICATE_SOURCE_ID", f"来源章节 ID 重复：{s.source_id}")
        seen.add(s.source_id)
        size = len(s.html.encode("utf-8"))
        if size > MAX_SECTION_HTML_BYTES:
            raise SourceError("PAYLOAD_TOO_LARGE", f"章节「{s.title}」正文超过单章上限 512KB", 413)
        total += size
        doc_id = (s.metadata or {}).get("doc_id")
        out.append(ParsedSection(source_id=s.source_id, title=s.title, level=s.level, html=s.html,
                                 confidence=_enum_value(s.confidence),
                                 metadata={"doc_id": str(doc_id)} if doc_id else {}))
    if total > MAX_BATCH_SOURCE_BYTES:
        raise SourceError("PAYLOAD_TOO_LARGE", "来源正文总量超过 5MB 上限，请拆分文档", 413)
    return out


def _verify_upload_metadata(meta: dict[str, Any], *, project_id: UUID, user_id: UUID) -> dict[str, Any]:
    expected = _signature(meta, project_id=project_id, user_id=user_id)
    if not isinstance(meta.get("signature"), str) or not hmac.compare_digest(meta["signature"], expected):
        raise SourceError("SOURCE_METADATA_INVALID", "上传来源信息校验失败，请重新上传文件")
    return {k: meta.get(k) for k in _SIGNED_KEYS}


async def _resolve_template(db: AsyncSession, *, project_id: UUID, user: Any, source: Any) -> ResolvedSource:
    version = await db.get(NoteContentTemplateVersion, source.template_version_id)
    template = await db.get(NoteContentTemplate, version.template_id) if version else None
    if template is None or not await can_view_template(db, user, template, viewer_project_id=project_id):
        raise SourceError("TEMPLATE_NOT_VISIBLE", "内容模板不存在或无权访问", 404)
    if version.content_hash != source.template_content_hash:
        raise SourceError("TEMPLATE_HASH_MISMATCH", "模板版本内容与所选版本不一致，请重新选择版本", 409)
    sections = [
        ParsedSection(
            source_id=str(s.get("source_note_id") or s.get("note_section")),
            title=s.get("section_title") or s.get("note_section") or "（无标题）",
            html=s.get("text_content") or "",
            metadata={k: s.get(k) for k in ("note_section", "section_kind", "section_id", "status", "is_stale")},
        )
        for s in version.sections_data or [] if isinstance(s, dict)
    ]
    source_project = await db.get(Project, version.source_project_id)
    meta = {"template_id": str(template.id), "template_name": template.name,
            "template_version_id": str(version.id), "version_no": version.version_no,
            "content_hash": version.content_hash, "source_project_id": str(version.source_project_id),
            "source_year": version.source_year}
    return ResolvedSource(
        kind="content_template", sections=sections,
        context=SourceContext(kind="content_template", template_type=version.template_type,
                              report_scope=version.report_scope),
        identity={"kind": "content_template", "template_version_id": str(version.id),
                  "content_hash": version.content_hash},
        audit_metadata=meta,
        entity_name=(source_project.client_name if source_project else None) or version.source_project_name,
        template_version_id=version.id, template_content_hash=version.content_hash,
    )


async def resolve_source(db: AsyncSession, *, project_id: UUID, user: Any, source: Any) -> ResolvedSource:
    """按 ``BatchSource`` 在服务端重建来源（preview 与 apply 各调一次，结果须一致才能过 digest）。"""
    kind = _enum_value(source.source_kind)
    if kind == "content_template":
        return await _resolve_template(db, project_id=project_id, user=user, source=source)
    sections = _client_sections(source.parsed_source, kind)
    if kind == "upload":
        meta = _verify_upload_metadata(source.parsed_source.source_metadata, project_id=project_id, user_id=user.id)
        return ResolvedSource(kind="upload", sections=sections, context=SourceContext(kind="upload"),
                              identity={"kind": "upload", "file_hash": meta["file_hash"]}, audit_metadata=meta)
    docs = await _visible_documents(db, list(source.knowledge_doc_ids), user=user, project_id=project_id)
    visible = {d["source_id"] for d in docs}
    if {str(d) for d in source.knowledge_doc_ids} - visible:
        raise SourceError("KNOWLEDGE_DOC_NOT_VISIBLE", "所选知识库文档不可用（无权限、已删除或不存在），请重新选择", 404)
    if any(s.metadata.get("doc_id") not in visible for s in sections):
        raise SourceError("SOURCE_SECTION_INVALID", "来源章节不属于所选知识库文档，请重新解析")
    documents = [{"doc_id": d["source_id"], "document_name": d.get("document_name"),
                  "doc_version": d.get("doc_version")} for d in docs]
    return ResolvedSource(
        kind="knowledge", sections=sections, context=SourceContext(kind="knowledge"),
        identity={"kind": "knowledge", "documents": sorted([d["doc_id"], d["doc_version"]] for d in documents)},
        audit_metadata={"documents": documents},
    )


def build_target_vars(project: Project | None, year: int) -> dict[str, str]:
    """目标确定性变量（AC-10.1）：只取服务端权威值，缺失则不替换（不猜币种 / 金额单位）。"""
    out = {"year": str(year)}
    if project is not None and project.client_name:
        out["company_name"] = project.client_name
    start, end = getattr(project, "audit_period_start", None), getattr(project, "audit_period_end", None)
    if start and end:
        out["report_period"] = f"{start.year}年{start.month}月{start.day}日至{end.year}年{end.month}月{end.day}日"
    return out


async def compute_preview(db: AsyncSession, *, project_id: UUID, year: int, resolved: ResolvedSource,
                          manual_mappings: list[Any], revoked_replacement_ids: list[str]) -> dict[str, Any]:
    """服务端预览：上传 / 知识库只填叙述章节，模板全套（design §7.1）；不写库。"""
    template_type, report_scope = await resolve_target_context(db, project_id)
    # 定位要走章节树的容器节点 ⇒ 一律取全部章节；可写范围由 writable_for 按来源类型另判（上传 / 知识库只填叙述）
    targets = await load_target_sections(db, project_id, year, include_content=True, scope="all")
    mapping = {m.source_id: m.target_note_id for m in manual_mappings}
    if len(mapping) != len(manual_mappings):
        raise ManualMappingError("同一来源章节只能映射一个目标章节")
    validate_mappings(resolved.sections, targets, mapping, source_context=resolved.context)
    sources, matches, structural = locate_sources(resolved.sections, targets, manual_mappings=mapping,
                                                  source_context=resolved.context, target_template_type=template_type)
    preview = build_preview(
        sources, targets, matches,
        target_vars=build_target_vars(await db.get(Project, project_id), year),
        source_entity_name=resolved.entity_name, revoked_replacement_ids=set(revoked_replacement_ids),
        source_context=resolved.context, target_template_type=template_type, target_report_scope=report_scope,
        source_identity=resolved.identity, structural_ids=structural,
    )
    tree_notes = tree_warnings(targets) if resolved.kind != "content_template" else []
    preview["warnings"] = [*resolved.warnings, *tree_notes, *preview.get("warnings", [])]
    return preview
