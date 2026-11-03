"""知识文档版本显式晋升为项目证据。

源知识 ACL 与目标项目权限由路由先行校验；本服务只在同一事务中钉住源版本/字节，
创建项目附件聚合根、不可变 v1 与 append-only provenance。service 只 flush，不 commit。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_blob_models import AssetBlob, KnowledgeEvidencePromotion
from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion
from app.models.knowledge_models import KnowledgeDocument
from app.services.asset_blob_service import (
    AssetBlobReadRejected,
    AssetBlobService,
    VerifiedAssetBlob,
    resolve_within_root,
)
from app.services.attachment_upload_policy import scan_content
from app.services.knowledge_upload_service import knowledge_storage_root
from app.services.safe_file_ingress import sniff_media_type


class KnowledgeEvidencePromotionError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def as_detail(self) -> dict[str, str]:
        return {"error_code": self.code, "message": self.message}


@dataclass(frozen=True)
class KnowledgeEvidencePromotionResult:
    promotion_id: UUID
    source_document_id: UUID
    source_document_version: int
    attachment_id: UUID
    attachment_version_id: UUID
    project_id: UUID
    audit_year: int
    content_hash: str
    replayed: bool
    created_blob_path: Path | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "promotion_id": str(self.promotion_id),
            "source_document_id": str(self.source_document_id),
            "source_document_version": self.source_document_version,
            "attachment_id": str(self.attachment_id),
            "attachment_version_id": str(self.attachment_version_id),
            "project_id": str(self.project_id),
            "audit_year": self.audit_year,
            "content_hash": self.content_hash,
            "replayed": self.replayed,
        }


@dataclass(frozen=True)
class _SourceSnapshot:
    blob: AssetBlob
    verified: VerifiedAssetBlob
    created_path: Path | None


def _file_type(document: KnowledgeDocument) -> str:
    value = (document.file_type or Path(document.name).suffix).strip().lower().lstrip(".")
    return value or "txt"


def _media_type(document: KnowledgeDocument, detected: str | None) -> str | None:
    if _file_type(document) in {"md", "markdown"}:
        return "text/markdown"
    return detected


def _materialized_text_path(document: KnowledgeDocument, digest: str) -> Path:
    suffix = ".md" if _file_type(document) in {"md", "markdown"} else ".txt"
    return knowledge_storage_root() / "_evidence_snapshots" / str(document.id) / f"v{document.version}-{digest}{suffix}"


def _write_content_addressed(path: Path, content: bytes) -> bool:
    """原子写内容寻址文件；返回本次是否新建。"""
    root = knowledge_storage_root()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise KnowledgeEvidencePromotionError(
            "SOURCE_STORAGE_REJECTED", "知识文档存储位置不安全"
        ) from exc
    if path.exists():
        existing = path.read_bytes()
        if existing != content:
            raise KnowledgeEvidencePromotionError(
                "SOURCE_BYTES_CHANGED", "知识文档版本字节已变化，不能晋升"
            )
        return False
    temp = path.with_name(f".{path.name}.{uuid4().hex}.part")
    try:
        with open(temp, "xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return True


class KnowledgeEvidencePromotionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.blobs = AssetBlobService(db)

    async def _load_source_for_update(self, document_id: UUID) -> KnowledgeDocument:
        document = (
            await self.db.execute(
                sa.select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.is_deleted == sa.false(),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if document is None:
            raise KnowledgeEvidencePromotionError(
                "SOURCE_NOT_FOUND", "知识文档不存在或已删除", status_code=404
            )
        return document

    async def _existing(
        self,
        *,
        project_id: UUID,
        actor_user_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeEvidencePromotion | None:
        return (
            await self.db.execute(
                sa.select(KnowledgeEvidencePromotion).where(
                    KnowledgeEvidencePromotion.project_id == project_id,
                    KnowledgeEvidencePromotion.actor_user_id == actor_user_id,
                    KnowledgeEvidencePromotion.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _assert_same_intent(
        row: KnowledgeEvidencePromotion,
        document: KnowledgeDocument,
    ) -> None:
        if row.source_document_id != document.id or row.source_document_version != document.version:
            raise KnowledgeEvidencePromotionError(
                "IDEMPOTENCY_KEY_REUSED",
                "该幂等键已用于另一份知识文档，请重新发起操作",
            )

    @staticmethod
    def _result(
        row: KnowledgeEvidencePromotion,
        *,
        replayed: bool,
        created_blob_path: Path | None = None,
    ) -> KnowledgeEvidencePromotionResult:
        if row.target_attachment_version_id is None:
            raise KnowledgeEvidencePromotionError(
                "PROMOTION_INCOMPLETE", "既有晋升记录缺少附件版本，不能重放"
            )
        return KnowledgeEvidencePromotionResult(
            promotion_id=row.id,
            source_document_id=row.source_document_id,
            source_document_version=row.source_document_version,
            attachment_id=row.target_attachment_id,
            attachment_version_id=row.target_attachment_version_id,
            project_id=row.project_id,
            audit_year=row.audit_year,
            content_hash=row.source_hash,
            replayed=replayed,
            created_blob_path=created_blob_path,
        )

    async def _source_snapshot(
        self,
        document: KnowledgeDocument,
        actor_user_id: UUID,
    ) -> _SourceSnapshot:
        root = knowledge_storage_root()
        if document.blob_id is not None:
            try:
                verified = await self.blobs.read_verified(
                    document.blob_id,
                    allowed_roots=(root,),
                )
            except AssetBlobReadRejected as exc:
                raise KnowledgeEvidencePromotionError(
                    "SOURCE_BYTES_UNAVAILABLE",
                    "知识文档原始字节不存在或完整性校验失败",
                ) from exc
            blob = await self.db.get(AssetBlob, document.blob_id)
            assert blob is not None
            return _SourceSnapshot(blob=blob, verified=verified, created_path=None)

        created_path: Path | None = None
        source_path = resolve_within_root(document.storage_path, root)
        if source_path is not None:
            try:
                content = await asyncio.to_thread(source_path.read_bytes)
            except OSError as exc:
                raise KnowledgeEvidencePromotionError(
                    "SOURCE_BYTES_UNAVAILABLE", "知识文档原始文件无法读取"
                ) from exc
            storage_key = str(source_path)
        elif document.storage_path:
            raise KnowledgeEvidencePromotionError(
                "SOURCE_STORAGE_REJECTED", "知识文档原始文件不在受信存储范围内"
            )
        elif document.content_text is not None:
            content = document.content_text.encode("utf-8")
            if not content:
                raise KnowledgeEvidencePromotionError(
                    "SOURCE_BYTES_UNAVAILABLE", "空知识文档不能晋升为项目证据"
                )
            digest = hashlib.sha256(content).hexdigest()
            source_path = _materialized_text_path(document, digest)
            if await asyncio.to_thread(_write_content_addressed, source_path, content):
                created_path = source_path
            storage_key = str(source_path)
        else:
            raise KnowledgeEvidencePromotionError(
                "SOURCE_BYTES_UNAVAILABLE", "知识文档没有可用的原始文件或正文"
            )

        if not content:
            raise KnowledgeEvidencePromotionError(
                "SOURCE_BYTES_UNAVAILABLE", "空知识文档不能晋升为项目证据"
            )
        try:
            await scan_content(content)
        except Exception as exc:
            from app.services.attachment_upload_policy import UploadRejected

            if isinstance(exc, UploadRejected):
                raise KnowledgeEvidencePromotionError(
                    "SOURCE_CONTENT_UNSAFE",
                    "知识文档原始内容未通过证据安全检查",
                    status_code=422,
                ) from exc
            raise
        detected = sniff_media_type(content[:4096])
        blob = await self.blobs.register_bytes(
            storage_type="local",
            storage_key=storage_key,
            content=content,
            media_type=detected,
            actor_user_id=actor_user_id,
        )
        document.blob_id = blob.id
        verified = VerifiedAssetBlob(
            blob_id=blob.id,
            content=content,
            canonical_path=source_path,
            content_hash=blob.content_hash,
            byte_size=blob.byte_size,
            media_type=blob.detected_media_type,
        )
        return _SourceSnapshot(blob=blob, verified=verified, created_path=created_path)

    async def promote(
        self,
        *,
        source_document_id: UUID,
        project_id: UUID,
        audit_year: int,
        actor_user_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeEvidencePromotionResult:
        """创建或重放知识版本→项目证据快照。"""
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise KnowledgeEvidencePromotionError(
                "INVALID_IDEMPOTENCY_KEY", "幂等键不能为空且不能超过 128 个字符", status_code=422
            )
        if not await self.blobs.available():
            raise KnowledgeEvidencePromotionError(
                "ASSET_BLOB_NOT_READY", "不可变字节迁移尚未就绪，请联系管理员", status_code=503
            )

        document = await self._load_source_for_update(source_document_id)
        existing = await self._existing(
            project_id=project_id,
            actor_user_id=actor_user_id,
            idempotency_key=key,
        )
        if existing is not None:
            self._assert_same_intent(existing, document)
            return self._result(existing, replayed=True)

        snapshot: _SourceSnapshot | None = None
        try:
            snapshot = await self._source_snapshot(document, actor_user_id)
            attachment_id = uuid4()
            version_id = uuid4()
            locator = f"blob://{snapshot.blob.id}"
            media_type = _media_type(document, snapshot.verified.media_type)
            attachment = Attachment(
                id=attachment_id,
                project_id=project_id,
                audit_year=audit_year,
                file_name=document.name,
                original_file_name=document.name,
                file_path=locator,
                file_type=_file_type(document),
                file_size=snapshot.verified.byte_size,
                attachment_type="evidence",
                reference_type="knowledge_document",
                reference_id=document.id,
                storage_type="asset_blob",
                ocr_status="completed" if document.content_text else "pending",
                ocr_text=document.content_text,
                is_key_evidence=False,
                metadata_status="complete",
                metadata_missing={},
                state="available",
                current_version_id=version_id,
                version=1,
                source_type="knowledge_document",
                provider="knowledge_library",
                created_by=actor_user_id,
                actor_type="user",
                actor_user_id=actor_user_id,
            )
            version = AttachmentVersion(
                id=version_id,
                attachment_id=attachment_id,
                project_id=project_id,
                audit_year=audit_year,
                version_no=1,
                storage_type="asset_blob",
                storage_key=locator,
                media_type=media_type,
                byte_size=snapshot.verified.byte_size,
                content_hash=snapshot.verified.content_hash,
                blob_id=snapshot.blob.id,
                config_snapshot={
                    "source": {
                        "kind": "knowledge_document",
                        "document_id": str(document.id),
                        "document_version": document.version,
                    }
                },
                availability="available",
                actor_type="user",
                actor_user_id=actor_user_id,
            )
            promotion = KnowledgeEvidencePromotion(
                source_document_id=document.id,
                source_document_version=document.version,
                source_blob_id=snapshot.blob.id,
                source_hash=snapshot.verified.content_hash,
                target_attachment_id=attachment_id,
                target_attachment_version_id=version_id,
                project_id=project_id,
                audit_year=audit_year,
                idempotency_key=key,
                actor_user_id=actor_user_id,
            )
            try:
                async with self.db.begin_nested():
                    self.db.add_all((attachment, version, promotion))
                    await self.db.flush()
            except IntegrityError:
                # 同一请求并发到达：唯一键只允许一个 promotion，失败 SAVEPOINT
                # 会连同本次 target root/version 一起回滚。随后重读胜者。
                existing = await self._existing(
                    project_id=project_id,
                    actor_user_id=actor_user_id,
                    idempotency_key=key,
                )
                if existing is None:
                    raise
                self._assert_same_intent(existing, document)
                return self._result(existing, replayed=True)
            return self._result(
                promotion,
                replayed=False,
                created_blob_path=snapshot.created_path,
            )
        except Exception:
            # 仅清理由本事务在锁住源版本后新建的内容寻址文件。既有知识文件和 blob 不删。
            if snapshot is not None and snapshot.created_path is not None:
                snapshot.created_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def cleanup_after_rollback(result: KnowledgeEvidencePromotionResult | None) -> None:
        """router commit 失败后的文件补偿；已有源文件/复用 blob 不受影响。"""
        if result is not None and result.created_blob_path is not None:
            result.created_blob_path.unlink(missing_ok=True)
