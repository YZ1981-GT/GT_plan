"""附件管理服务 — Paperless-ngx 集成

功能：
- 上传附件（本地存储 + 可选推送到 Paperless-ngx）
- 附件列表/详情/搜索
- OCR 状态跟踪
- 关联附件到底稿
- 全文搜索（通过 Paperless-ngx API）

Validates: Requirements 14.1-14.8
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.attachment_models import Attachment, AttachmentWorkingPaper


class AttachmentService:
    """附件管理服务"""

    def __init__(
        self,
        db: AsyncSession,
        paperless_url: str | None = None,
        paperless_token: str | None = None,
        primary_storage: str | None = None,
        fallback_to_local: bool | None = None,
        local_storage_root: str | None = None,
    ):
        self.db = db
        self.paperless_url = paperless_url if paperless_url is not None else settings.PAPERLESS_URL
        self.paperless_token = paperless_token if paperless_token is not None else settings.PAPERLESS_TOKEN
        self.primary_storage = (primary_storage or settings.ATTACHMENT_PRIMARY_STORAGE or "paperless").lower()
        self.fallback_to_local = (
            settings.ATTACHMENT_FALLBACK_TO_LOCAL if fallback_to_local is None else fallback_to_local
        )
        self.local_storage_root = Path(local_storage_root or settings.ATTACHMENT_LOCAL_STORAGE_ROOT)

    def paperless_enabled(self) -> bool:
        """Paperless-ngx 是否可用"""
        return bool(self.paperless_url and self.paperless_token)

    async def create_attachment(
        self,
        project_id: UUID,
        data: dict[str, Any],
        created_by: UUID | None = None,
    ) -> dict:
        """创建附件记录"""
        paperless_document_id = data.get("paperless_document_id")
        storage_type = data.get("storage_type")
        if not storage_type:
            if paperless_document_id or str(data.get("file_path", "")).startswith("paperless://"):
                storage_type = "paperless"
            else:
                storage_type = "local"

        file_path = data["file_path"]
        if storage_type == "paperless" and paperless_document_id and not str(file_path).startswith("paperless://"):
            file_path = self._paperless_uri(paperless_document_id)

        attachment = Attachment(
            project_id=project_id,
            file_name=data["file_name"],
            file_path=file_path,
            file_type=data.get("file_type") or self._guess_file_type(data["file_name"]),
            file_size=data.get("file_size", 0),
            attachment_type=data.get("attachment_type", "general"),
            reference_id=data.get("reference_id"),
            reference_type=data.get("reference_type"),
            storage_type=storage_type,
            paperless_document_id=paperless_document_id,
            ocr_status=data.get("ocr_status") or self._default_ocr_status(storage_type, paperless_document_id),
            ocr_text=data.get("ocr_text"),
            created_by=created_by,
        )
        self.db.add(attachment)
        await self.db.flush()
        return self._to_dict(attachment)

    async def upload_attachment_file(
        self,
        project_id: UUID,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
        created_by: UUID | None = None,
    ) -> dict:
        """上传附件，优先存储到 Paperless-ngx，失败时回退到本地存储"""
        metadata = metadata or {}
        temp_path = self._write_temp_file(file_name, content)

        # 创建异步任务跟踪
        from app.services.task_center import create_task, update_task, TaskType, TaskStatus
        task_id = create_task(
            TaskType.ocr,
            project_id=str(project_id),
            object_id=file_name,
            params={"file_size": len(content), "storage": self.primary_storage},
        )

        try:
            use_paperless = self.primary_storage == "paperless" and self.paperless_enabled()
            if use_paperless:
                update_task(task_id, TaskStatus.processing)
                paperless_document_id = await self.upload_to_paperless(temp_path.as_posix(), metadata)
                if paperless_document_id is not None:
                    update_task(task_id, TaskStatus.success, result={"paperless_id": paperless_document_id})
                    return await self.create_attachment(
                        project_id,
                        {
                            "file_name": file_name,
                            "file_path": self._paperless_uri(paperless_document_id),
                            "file_type": metadata.get("file_type") or self._guess_file_type(file_name),
                            "file_size": len(content),
                            "attachment_type": metadata.get("attachment_type", "general"),
                            "reference_id": metadata.get("reference_id"),
                            "reference_type": metadata.get("reference_type"),
                            "storage_type": "paperless",
                            "paperless_document_id": paperless_document_id,
                            "ocr_status": metadata.get("ocr_status", "processing"),
                        },
                        created_by=created_by,
                    )
                if not self.fallback_to_local:
                    raise RuntimeError("Paperless-ngx 上传失败，且未启用本地回退存储")

            local_path = self._write_local_file(
                project_id=project_id,
                file_name=file_name,
                content=content,
                attachment_type=metadata.get("attachment_type", "general"),
            )
            update_task(task_id, TaskStatus.success, result={"storage": "local", "path": local_path})
            return await self.create_attachment(
                project_id,
                {
                    "file_name": file_name,
                    "file_path": local_path,
                    "file_type": metadata.get("file_type") or self._guess_file_type(file_name),
                    "file_size": len(content),
                    "attachment_type": metadata.get("attachment_type", "general"),
                    "reference_id": metadata.get("reference_id"),
                    "reference_type": metadata.get("reference_type"),
                    "storage_type": "local",
                    "ocr_status": metadata.get("ocr_status", "pending"),
                },
                created_by=created_by,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    async def list_attachments(
        self,
        project_id: UUID,
        file_type: str | None = None,
        ocr_status: str | None = None,
        attachment_type: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> list[dict]:
        """附件列表"""
        stmt = (
            sa.select(Attachment)
            .where(Attachment.project_id == project_id, Attachment.is_deleted == sa.false())
            .order_by(Attachment.created_at.desc())
        )
        if file_type:
            stmt = stmt.where(Attachment.file_type == file_type)
        if ocr_status:
            stmt = stmt.where(Attachment.ocr_status == ocr_status)
        if attachment_type:
            stmt = stmt.where(Attachment.attachment_type == attachment_type)
        if reference_type:
            stmt = stmt.where(Attachment.reference_type == reference_type)
        if reference_id:
            stmt = stmt.where(Attachment.reference_id == reference_id)

        result = await self.db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    async def get_attachment(self, attachment_id: UUID) -> dict | None:
        """附件详情"""
        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted == sa.false())
        )
        a = result.scalar_one_or_none()
        return self._to_dict(a) if a else None

    async def update_ocr_status(
        self, attachment_id: UUID, status: str, ocr_text: str | None = None,
    ) -> dict | None:
        """更新 OCR 状态"""
        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id)
        )
        a = result.scalar_one_or_none()
        if not a:
            return None
        a.ocr_status = status
        if ocr_text is not None:
            a.ocr_text = ocr_text
        await self.db.flush()
        return self._to_dict(a)

    # ------------------------------------------------------------------
    # 关联底稿
    # ------------------------------------------------------------------

    async def associate_with_wp(
        self, attachment_id: UUID, wp_id: UUID,
        association_type: str = "evidence",
        notes: str | None = None,
        created_by: UUID | None = None,
    ) -> dict:
        """关联附件到底稿"""
        link = AttachmentWorkingPaper(
            attachment_id=attachment_id,
            wp_id=wp_id,
            association_type=association_type,
            notes=notes,
            created_by=created_by,
        )
        self.db.add(link)
        await self.db.flush()
        return {
            "id": str(link.id),
            "attachment_id": str(link.attachment_id),
            "wp_id": str(link.wp_id),
            "association_type": link.association_type,
            "notes": link.notes,
        }

    async def get_wp_attachments(self, wp_id: UUID) -> list[dict]:
        """获取底稿关联的附件"""
        stmt = (
            sa.select(Attachment)
            .join(AttachmentWorkingPaper, AttachmentWorkingPaper.attachment_id == Attachment.id)
            .where(AttachmentWorkingPaper.wp_id == wp_id, Attachment.is_deleted == sa.false())
        )
        result = await self.db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    async def get_latest_reference_attachment(
        self,
        reference_id: UUID,
        reference_type: str,
        attachment_type: str | None = None,
    ) -> Attachment | None:
        """获取某业务对象最新的统一附件记录"""
        stmt = (
            sa.select(Attachment)
            .where(
                Attachment.reference_id == reference_id,
                Attachment.reference_type == reference_type,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(Attachment.created_at.desc())
        )
        if attachment_type:
            stmt = stmt.where(Attachment.attachment_type == attachment_type)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # ------------------------------------------------------------------
    # 全文搜索
    # ------------------------------------------------------------------

    async def search(self, project_id: UUID, query: str) -> list[dict]:
        """全文搜索附件（优先合并 Paperless-ngx 全文搜索结果）"""
        db_results = await self._search_db(project_id, query)
        if not self.paperless_enabled():
            return db_results

        paperless_results = await self.search_paperless(query)
        if not paperless_results:
            return db_results

        merged: dict[str, dict] = {item["id"]: item for item in db_results}
        for item in await self._merge_paperless_results(project_id, paperless_results):
            merged[item["id"]] = item
        return list(merged.values())

    # ------------------------------------------------------------------
    # Paperless-ngx 集成（需要 httpx）
    # ------------------------------------------------------------------

    async def upload_to_paperless(self, file_path: str, metadata: dict) -> int | None:
        """上传文档到 Paperless-ngx，返回 document_id"""
        if not self.paperless_url or not self.paperless_token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT) as client:
                with open(file_path, "rb") as f:
                    files = {"document": (os.path.basename(file_path), f)}
                    data = {
                        "title": metadata.get("title", os.path.basename(file_path)),
                    }
                    if metadata.get("correspondent"):
                        data["correspondent"] = metadata["correspondent"]
                    if metadata.get("document_type"):
                        data["document_type"] = metadata["document_type"]

                    resp = await client.post(
                        f"{self.paperless_url}/api/documents/post_document/",
                        files=files,
                        data=data,
                        headers={"Authorization": f"Token {self.paperless_token}"},
                    )
                    if resp.status_code in (200, 201):
                        return resp.json().get("id")
        except Exception:
            pass
        return None

    async def get_paperless_ocr(self, document_id: int) -> str | None:
        """从 Paperless-ngx 获取 OCR 结果"""
        if not self.paperless_url or not self.paperless_token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.paperless_url}/api/documents/{document_id}/",
                    headers={"Authorization": f"Token {self.paperless_token}"},
                )
                if resp.status_code == 200:
                    return resp.json().get("content", "")
        except Exception:
            pass
        return None

    async def search_paperless(self, query: str) -> list[dict]:
        """通过 Paperless-ngx 全文搜索"""
        if not self.paperless_url or not self.paperless_token:
            return []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.paperless_url}/api/documents/",
                    params={"query": query},
                    headers={"Authorization": f"Token {self.paperless_token}"},
                )
                if resp.status_code == 200:
                    return resp.json().get("results", [])
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # 自动文档分类
    # ------------------------------------------------------------------

    _TYPE_KEYWORDS: dict[str, list[str]] = {
        "contract": ["合同", "协议", "contract", "agreement"],
        "invoice": ["发票", "invoice", "税票"],
        "bank_statement": ["银行", "对账单", "流水", "bank"],
        "confirmation": ["函证", "回函", "询证", "confirmation"],
        "license": ["证照", "营业执照", "许可证", "license"],
        "voucher": ["凭证", "记账", "voucher"],
        "report": ["报告", "报表", "report"],
    }

    _PERIOD_PATTERNS: list[str] = [
        r"20\d{2}",
        r"20\d{2}[-/]\d{1,2}",
        r"\d{1,2}月",
    ]

    async def classify_document(self, attachment_id: UUID) -> dict:
        """自动分类文档（基于文件名 + OCR 文本分析）"""
        import re

        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id)
        )
        att = result.scalar_one_or_none()
        if not att:
            raise ValueError("附件不存在")

        file_name = (att.file_name or "").lower()
        ocr_text = (att.ocr_text or "")[:500].lower()
        combined = file_name + " " + ocr_text

        doc_type = "unknown"
        for dtype, keywords in self._TYPE_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                doc_type = dtype
                break

        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
        if ext in ("jpg", "jpeg", "png", "gif", "bmp"):
            file_category = "image"
        elif ext == "pdf":
            file_category = "pdf"
        elif ext in ("doc", "docx"):
            file_category = "word"
        elif ext in ("xls", "xlsx", "csv"):
            file_category = "excel"
        else:
            file_category = ext or "unknown"

        period_hint = None
        for pattern in self._PERIOD_PATTERNS:
            match = re.search(pattern, att.file_name or "")
            if match:
                period_hint = match.group()
                break

        customer_hint = None
        name_parts = re.split(r"[-_\s.]+", (att.file_name or "").rsplit(".", 1)[0])
        for part in name_parts:
            if len(part) >= 2 and not any(kw in part.lower() for kws in self._TYPE_KEYWORDS.values() for kw in kws):
                if not re.match(r"^\d+$", part):
                    customer_hint = part
                    break

        return {
            "attachment_id": str(att.id),
            "document_type": doc_type,
            "file_category": file_category,
            "period_hint": period_hint,
            "customer_hint": customer_hint,
        }

    # ------------------------------------------------------------------
    # 函证回函 OCR 识别
    # ------------------------------------------------------------------

    _AMOUNT_PATTERNS: list[str] = [
        r"(?:余额|金额|合计|总计|balance|amount)[：:\s]*([¥￥]?\s*[\d,]+\.?\d*)",
        r"([¥￥]\s*[\d,]+\.?\d*)",
        r"(\d{1,3}(?:,\d{3})*\.?\d{0,2})\s*(?:元|万元)",
    ]

    _DATE_PATTERNS: list[str] = [
        r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
    ]

    _ENTITY_PATTERNS: list[str] = [
        r"(?:单位|公司|银行|entity|company)[：:\s]*(.{2,30}?)(?:\n|$|，|,)",
        r"(?:致|to)[：:\s]*(.{2,30}?)(?:\n|$)",
    ]

    async def extract_confirmation_reply(self, attachment_id: UUID) -> dict:
        """从函证回函中提取关键信息"""
        import re

        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id)
        )
        att = result.scalar_one_or_none()
        if not att:
            raise ValueError("附件不存在")

        ocr_text = att.ocr_text or ""
        if not ocr_text.strip():
            return {
                "attachment_id": str(att.id),
                "reply_amount": None,
                "reply_date": None,
                "reply_entity": None,
                "confidence": "low",
                "message": "OCR 文本为空，请先完成 OCR 识别",
            }

        reply_amount = None
        for pattern in self._AMOUNT_PATTERNS:
            match = re.search(pattern, ocr_text)
            if match:
                raw = match.group(1).replace(",", "").replace("¥", "").replace("￥", "").strip()
                try:
                    reply_amount = float(raw)
                except ValueError:
                    pass
                if reply_amount is not None:
                    break

        reply_date = None
        for pattern in self._DATE_PATTERNS:
            match = re.search(pattern, ocr_text)
            if match:
                reply_date = match.group(1)
                break

        reply_entity = None
        for pattern in self._ENTITY_PATTERNS:
            match = re.search(pattern, ocr_text)
            if match:
                reply_entity = match.group(1).strip()
                break

        found_count = sum(1 for value in [reply_amount, reply_date, reply_entity] if value is not None)
        confidence = "high" if found_count == 3 else "medium" if found_count >= 1 else "low"

        return {
            "attachment_id": str(att.id),
            "reply_amount": reply_amount,
            "reply_date": reply_date,
            "reply_entity": reply_entity,
            "confidence": confidence,
            "message": f"提取到 {found_count}/3 个字段",
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _paperless_uri(self, document_id: int) -> str:
        return f"paperless://documents/{document_id}"

    def _guess_file_type(self, file_name: str) -> str:
        ext = Path(file_name).suffix.lower().lstrip(".")
        if ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp"}:
            return "image"
        if ext in {"xls", "xlsx", "csv"}:
            return "excel"
        if ext in {"doc", "docx"}:
            return "word"
        return ext or "unknown"

    def _default_ocr_status(self, storage_type: str, paperless_document_id: int | None) -> str:
        if storage_type == "paperless" and paperless_document_id is not None:
            return "processing"
        return "pending"

    def _write_temp_file(self, file_name: str, content: bytes) -> Path:
        suffix = Path(file_name).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            return Path(tmp.name)

    def _write_local_file(
        self,
        project_id: UUID,
        file_name: str,
        content: bytes,
        attachment_type: str,
    ) -> str:
        safe_name = Path(file_name).name or "attachment.bin"
        target_dir = self.local_storage_root / str(project_id) / attachment_type
        target_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        target_path = target_dir / safe_name
        counter = 1
        while target_path.exists():
            target_path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        target_path.write_bytes(content)
        return target_path.as_posix()

    async def _search_db(self, project_id: UUID, query: str) -> list[dict]:
        kw = f"%{query}%"
        stmt = (
            sa.select(Attachment)
            .where(
                Attachment.project_id == project_id,
                Attachment.is_deleted == sa.false(),
                sa.or_(
                    Attachment.file_name.ilike(kw),
                    Attachment.ocr_text.ilike(kw),
                ),
            )
            .order_by(Attachment.created_at.desc())
            .limit(50)
        )
        result = await self.db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    async def _merge_paperless_results(self, project_id: UUID, paperless_results: list[dict]) -> list[dict]:
        document_ids = [item.get("id") for item in paperless_results if item.get("id") is not None]
        if not document_ids:
            return []

        stmt = sa.select(Attachment).where(
            Attachment.project_id == project_id,
            Attachment.is_deleted == sa.false(),
            Attachment.paperless_document_id.in_(document_ids),
        )
        result = await self.db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    def _to_dict(self, a: Attachment) -> dict:
        return {
            "id": str(a.id),
            "project_id": str(a.project_id),
            "file_name": a.file_name,
            "file_path": a.file_path,
            "file_type": a.file_type,
            "file_size": a.file_size,
            "attachment_type": a.attachment_type,
            "reference_id": str(a.reference_id) if a.reference_id else None,
            "reference_type": a.reference_type,
            "storage_type": a.storage_type,
            "paperless_document_id": a.paperless_document_id,
            "ocr_status": a.ocr_status,
            "ocr_text": a.ocr_text[:200] if a.ocr_text else None,  # 截断预览
            "is_deleted": a.is_deleted,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
