"""底稿证据采集单一入口（spec attachment-evidence-intake，ADR-AEI-01/03/05/06）。

底稿里产生的证据文件只经这里进附件表：
- :func:`create_evidence`：上传策略 → 建附件（不进旧的同名自动建版本）→ 整稿关联或行级证据链接，只 flush；
- :func:`intake_ocr_upload`：26 个底稿 OCR 端点的前半段——带 ``attachment_id`` 时校验它确属本底稿，
  不带时先建附件并提交，再给出识别用的本地文件。

改造前：OCR 端点把文件写到 ``storage/workpapers/{wp}/…`` 旁路目录，附件表没有记录，行里存的是临时 id；
带 ``attachment_id`` 时不校项目与关联，能读走任意项目附件的识别全文；建附件失败也返回临时 id 继续识别。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.attachment_upload_policy import UploadRejected

logger = logging.getLogger(__name__)

#: 证据类型登记表（``ATTACHMENT_TYPES`` 的子集：去掉 ``general`` / ``workpaper_item``）；前端选项与之逐项一致。
EVIDENCE_TYPES: frozenset[str] = frozenset({
    "evidence", "support", "voucher", "contract", "bank_statement", "stocktake", "note", "confirmation", "signed",
})
DEFAULT_EVIDENCE_TYPE = "evidence"

#: 整稿上传 / 行级上传各自的 ``reference_type``（行级与附件管理页的无引用上传隔开旧版本链键，ADR-AEI-03）
WP_REFERENCE_TYPE = "working_paper"
ROW_REFERENCE_TYPE = "workpaper_item"

_POSITION_LIMITS = {"sheet_name": 100, "cell_ref": 100, "page_ref": 50}


def parse_workpaper_id(wp_id: str | UUID) -> UUID:
    """路径参数解析成 UUID；非法 ⇒ 400（不读文件、不建行、不调用识别）。"""
    if isinstance(wp_id, UUID):
        return wp_id
    try:
        return UUID(str(wp_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="无效的底稿 ID")


# ─── 证据类型 ────────────────────────────────────────────────────────────────


def validate_evidence_type(value: str | None) -> str | None:
    """空 ⇒ None（交给缺省规则）；不在登记表 ⇒ 422。"""
    text = (value or "").strip()
    if not text:
        return None
    if text not in EVIDENCE_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "EVIDENCE_TYPE_NOT_ALLOWED", "message": "不支持的证据类型"},
        )
    return text


def default_evidence_type(
    wp_code: str | None, *, native_type: str | None = None, native_prefix: str | None = None,
) -> str:
    """缺省证据类型：底稿属于端点本循环 ⇒ 端点类型；证据声明恰好一类 ⇒ 该类；否则 ``evidence``。"""
    from app.services.workpaper_evidence_requirements import (
        matches_wp_code_prefix,
        resolve_requirements_for_wp_code,
    )

    if native_type and native_prefix and wp_code and matches_wp_code_prefix(wp_code, native_prefix):
        return native_type
    declared = {req["type"] for req in resolve_requirements_for_wp_code(wp_code)}
    if len(declared) == 1:
        only = next(iter(declared))
        if only in EVIDENCE_TYPES:
            return only
    return DEFAULT_EVIDENCE_TYPE


def resolve_evidence_type(
    requested: str | None, wp_code: str | None, *,
    native_type: str | None = None, native_prefix: str | None = None, voucher_keyed: bool = False,
) -> str:
    """显式类型优先；带凭证键 ⇒ 凭证 / 原始单据（不按底稿声明取：F1 声明函证，凭证附件曾被记成函证，
    spec attachment-voucher-evidence-binding ADR-AVE-05）；否则按缺省规则。"""
    explicit = validate_evidence_type(requested)
    if explicit:
        return explicit
    if voucher_keyed:
        from app.services.voucher_evidence import VOUCHER_EVIDENCE_TYPE

        return VOUCHER_EVIDENCE_TYPE
    return default_evidence_type(wp_code, native_type=native_type, native_prefix=native_prefix)


# ─── 位置、体量、底稿 ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidencePosition:
    """行级位置：``sheet_name`` = 表页键；``cell_ref`` = A1 单元格 / ``item:{序号}`` / ``row:{行 id}``；
    ``voucher_key`` = 凭证键规范串（凭证检查行的原件按凭证身份挂，可只有它，spec attachment-voucher-evidence-binding）。"""

    sheet_name: str | None = None
    cell_ref: str | None = None
    page_ref: str | None = None
    voucher_key: str | None = None

    @property
    def is_row_level(self) -> bool:
        return bool(self.sheet_name or self.cell_ref or self.voucher_key)


def build_position(
    sheet_name: str | None, cell_ref: str | None, page_ref: str | None = None, voucher_key: str | None = None,
) -> EvidencePosition:
    """位置字段去空白、超长 400；凭证键格式错 400（规范化后存）。"""
    from app.services.voucher_evidence import normalize_voucher_key

    values = {"sheet_name": sheet_name, "cell_ref": cell_ref, "page_ref": page_ref}
    cleaned: dict[str, str | None] = {}
    for key, raw in values.items():
        text = (raw or "").strip() or None
        if text is not None and len(text) > _POSITION_LIMITS[key]:
            raise HTTPException(status_code=400, detail=f"位置字段过长：{key}")
        cleaned[key] = text
    return EvidencePosition(**cleaned, voucher_key=normalize_voucher_key(voucher_key))


def max_upload_bytes() -> int:
    """附件上传上限（与附件上传端点同一配置项，未配置时 50MB）。"""
    from app.core.config import settings

    return int(getattr(settings, "ATTACHMENT_MAX_UPLOAD_BYTES", 50 * 1024 * 1024))


async def read_upload_limited(file: UploadFile) -> bytes:
    """读上传内容；超过附件上传上限 ⇒ 413。"""
    max_size = max_upload_bytes()
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content) / 1024 / 1024:.1f}MB），最大允许 {max_size / 1024 / 1024:.0f}MB",
        )
    return content


@dataclass(frozen=True)
class IntakeWorkpaper:
    id: UUID
    project_id: UUID
    wp_code: str | None


async def load_workpaper(db: AsyncSession, wp_id: UUID, *, project_id: UUID | None = None) -> IntakeWorkpaper:
    """底稿不存在 / 已删除 / 不属于 ``project_id`` ⇒ 404。"""
    row = (await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.project_id, WpIndex.wp_code)
        .outerjoin(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )).first()
    if row is None or (project_id is not None and row.project_id != project_id):
        raise HTTPException(status_code=404, detail="底稿不存在")
    return IntakeWorkpaper(id=row.id, project_id=row.project_id, wp_code=row.wp_code)


# ─── 建证据 ──────────────────────────────────────────────────────────────────


async def create_evidence(
    db: AsyncSession, *, wp: IntakeWorkpaper, file_name: str, content: bytes, evidence_type: str, user: Any,
    position: EvidencePosition | None = None, ocr_status: str | None = None,
) -> dict[str, Any]:
    """建附件并关联到底稿（只 flush，调用方提交）。返回 ``{"attachment": …, "evidence_link": … | None}``。

    行级（``position`` 带表页或单元格）只写证据链接，整稿只写 ``attachment_working_paper``（ADR-AEI-02）。
    归档 ⇒ 423、上传策略不过 ⇒ 422，都在落盘与建行之前。
    """
    from app.services.attachment_destructive_guard import assert_project_writable
    from app.services.attachment_service import AttachmentService
    from app.services.wp_evidence_service import WpEvidenceService

    await assert_project_writable(db, wp.project_id, user)
    row_level = position is not None and position.is_row_level
    metadata: dict[str, Any] = {
        "attachment_type": evidence_type,
        "reference_id": wp.id,
        "reference_type": ROW_REFERENCE_TYPE if row_level else WP_REFERENCE_TYPE,
    }
    if ocr_status:
        metadata["ocr_status"] = ocr_status
    svc = AttachmentService(db)
    try:
        attachment = await svc.upload_attachment_file(
            project_id=wp.project_id, file_name=file_name, content=content,
            metadata=metadata, created_by=user.id, version_chain=False,
        )
    except UploadRejected as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail())
    att_id = UUID(attachment["id"])
    link = None
    if row_level:
        link = await WpEvidenceService(db).create_link(
            wp_id=wp.id, attachment_id=att_id, created_by=user.id,
            sheet_name=position.sheet_name, cell_ref=position.cell_ref, page_ref=position.page_ref,
            evidence_type=evidence_type, voucher_key=position.voucher_key,
        )
    else:
        await svc.ensure_wp_link(att_id, wp.id, association_type=evidence_type, created_by=user.id)
    return {"attachment": attachment, "evidence_link": link}


# ─── OCR 端点前半段 ──────────────────────────────────────────────────────────


@dataclass
class OcrIntakeOptions:
    """OCR 端点的可选表单字段（需求 2.1、2.4；凭证键见 spec attachment-voucher-evidence-binding 需求 4.1）
    + 本次请求产生的识别临时副本（请求结束时删除）。"""

    evidence_type: str | None = None
    evidence_sheet: str | None = None
    evidence_cell: str | None = None
    evidence_voucher_key: str | None = None
    temp_paths: list[Path] = field(default_factory=list)

    def cleanup(self) -> None:
        for path in self.temp_paths:
            path.unlink(missing_ok=True)
        self.temp_paths.clear()


async def ocr_intake_options(
    evidence_type: str | None = Form(None),
    evidence_sheet: str | None = Form(None),
    evidence_cell: str | None = Form(None),
    evidence_voucher_key: str | None = Form(None),
) -> AsyncIterator[OcrIntakeOptions]:
    """OCR 路由的依赖：收四个可选表单字段；带 yield，异常返回时也删临时副本。"""
    options = OcrIntakeOptions(
        evidence_type=evidence_type, evidence_sheet=evidence_sheet, evidence_cell=evidence_cell,
        evidence_voucher_key=evidence_voucher_key,
    )
    try:
        yield options
    finally:
        options.cleanup()


@dataclass
class OcrSource:
    """识别输入：附件 id + 本地文件路径；``reused`` 非空时直接返回已有结果、不识别。"""

    attachment_id: UUID
    path: str = ""
    reused: dict[str, Any] | None = None
    created: bool = False
    temp_path: Path | None = None

    def cleanup(self) -> None:
        """只删识别用的临时副本，不碰附件原件。"""
        if self.temp_path is not None:
            self.temp_path.unlink(missing_ok=True)


async def linked_attachment_or_404(db: AsyncSession, attachment_id: UUID, wp: IntakeWorkpaper) -> Attachment:
    """附件须未删除、与底稿同项目且已关联到本底稿（整稿关联 / reference / 本底稿证据链接），否则 404。"""
    from app.services.attachment_ocr_writeback import is_attachment_linked_to_wp

    att = (await db.execute(
        sa.select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted == sa.false())
    )).scalar_one_or_none()
    if att is None or att.project_id != wp.project_id or not await is_attachment_linked_to_wp(db, attachment_id, wp.id):
        raise HTTPException(status_code=404, detail="附件不存在或未关联到本底稿")
    return att


def _local_file(storage_type: str | None, file_path: str | None) -> str | None:
    if storage_type == "local" and file_path and Path(file_path).is_file():
        return str(file_path)
    return None


async def intake_ocr_upload(
    db: AsyncSession, *, wp_id: str | UUID, file: UploadFile, attachment_id: str | None, force_reocr: bool,
    user: Any, native_type: str, native_prefix: str, options: OcrIntakeOptions | None = None,
) -> OcrSource:
    """底稿 OCR 端点前半段（需求 2.1、2.2、2.5，ADR-AEI-05）。新建附件时在识别前提交。

    带 ``attachment_id``：须属本底稿（否则 404，不返回识别文本）；不强制重识别且已有文本 ⇒ 复用；
    重识别读附件已存原件（Paperless 存储时才用请求里的文件）。不带：经 :func:`create_evidence` 建附件。
    """
    from app.services.attachment_destructive_guard import assert_project_writable
    from app.services.attachment_ocr_writeback import load_reusable_ocr, parse_optional_uuid
    from app.services.attachment_service import AttachmentService

    if not isinstance(options, OcrIntakeOptions):  # 直接调用路由函数（未经依赖注入）时是 Depends 占位
        options = OcrIntakeOptions()
    wp = await load_workpaper(db, parse_workpaper_id(wp_id))
    file_name = file.filename or "upload.pdf"
    svc = AttachmentService(db)
    linked = parse_optional_uuid(attachment_id)
    if linked is not None:
        att = await linked_attachment_or_404(db, linked, wp)
        if not force_reocr:
            reused = await load_reusable_ocr(db, linked)
            if reused is not None:
                return OcrSource(attachment_id=linked, reused=reused)
        await assert_project_writable(db, wp.project_id, user)
        local = _local_file(att.storage_type, att.file_path)
        if local is not None:
            return OcrSource(attachment_id=linked, path=local)
        return _with_temp(options, svc, linked, att.file_name or file_name, await read_upload_limited(file))

    position = build_position(
        options.evidence_sheet, options.evidence_cell, voucher_key=options.evidence_voucher_key,
    )
    content = await read_upload_limited(file)
    etype = resolve_evidence_type(
        options.evidence_type, wp.wp_code, native_type=native_type, native_prefix=native_prefix,
        voucher_keyed=position.voucher_key is not None,
    )
    created = await create_evidence(
        db, wp=wp, file_name=file_name, content=content, evidence_type=etype, user=user,
        position=position, ocr_status="processing",
    )
    await db.commit()
    att_id = UUID(created["attachment"]["id"])
    raw = await svc.get_raw_storage(att_id) or {}
    local = _local_file(raw.get("storage_type"), raw.get("file_path"))
    if local is not None:
        return OcrSource(attachment_id=att_id, path=local, created=True)
    source = _with_temp(options, svc, att_id, file_name, content)
    source.created = True
    return source


def _with_temp(options: OcrIntakeOptions, svc: Any, attachment_id: UUID, file_name: str, content: bytes) -> OcrSource:
    temp = svc._write_temp_file(file_name, content)
    options.temp_paths.append(temp)
    return OcrSource(attachment_id=attachment_id, path=str(temp), temp_path=temp)


async def record_ocr_response(db: AsyncSession, wp_id: UUID, src: OcrSource, response: Any) -> Any:
    """原来不写回识别结果的 OCR 路由用（需求 2.6）：把响应里的识别文本 / 字段写回附件后原样返回。"""
    from app.services.attachment_ocr_writeback import finalize_linked_ocr_writeback

    fields = getattr(response, "extracted_fields", None)
    await finalize_linked_ocr_writeback(
        db, wp_id=wp_id, linked_att_id=src.attachment_id, temp_id=str(src.attachment_id),
        ocr_text=getattr(response, "ocr_text", "") or "",
        extracted_fields=dict(fields) if isinstance(fields, dict) else {},
        confidence=float(getattr(response, "confidence", 0) or 0),
    )
    return response
