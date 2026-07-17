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

import logging
import os

logger = logging.getLogger(__name__)
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.services.attachment_locator import project_attachment_locator


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
        """创建附件记录（AT-3：同名自动建版本链）

        同 (project_id, reference_id, reference_type, file_name) 第二次调用时
        新行 version=N+1，previous_version_id 指向当前最新版本。
        """
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

        # AT-3：解析版本链
        ref_id_raw = data.get("reference_id")
        ref_id = ref_id_raw if isinstance(ref_id_raw, UUID) else (UUID(ref_id_raw) if ref_id_raw else None)
        version, prev_id = await self._resolve_version_chain(
            project_id=project_id,
            file_name=data["file_name"],
            reference_id=ref_id,
            reference_type=data.get("reference_type"),
        )

        attachment = Attachment(
            project_id=project_id,
            file_name=data["file_name"],
            file_path=file_path,
            file_type=data.get("file_type") or self._guess_file_type(data["file_name"]),
            file_size=data.get("file_size", 0),
            attachment_type=data.get("attachment_type", "general"),
            reference_id=ref_id,
            reference_type=data.get("reference_type"),
            storage_type=storage_type,
            paperless_document_id=paperless_document_id,
            ocr_status=data.get("ocr_status") or self._default_ocr_status(storage_type, paperless_document_id),
            ocr_text=data.get("ocr_text"),
            created_by=created_by,
            version=version,
            previous_version_id=prev_id,
        )
        self.db.add(attachment)
        await self.db.flush()
        # 替换（version>1，即产生了新版本）→ 发出治理失效信号，令下游可标记 stale。
        # 首版上传（version==1）不发（无被替换的旧版本/无下游依赖）。
        if version > 1:
            await self._emit_version_replaced_signal(
                new_att=attachment,
                previous_version_id=prev_id,
                actor=created_by,
                project_id=project_id,
                anchor_id=prev_id,
            )
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
                # 自动重试：Paperless 上传失败时重试 1 次
                paperless_document_id = await self.upload_to_paperless(temp_path.as_posix(), metadata)
                if paperless_document_id is None:
                    import asyncio
                    logger.warning("Paperless upload failed, retrying in 2s...")
                    update_task(task_id, TaskStatus.retrying)
                    await asyncio.sleep(2)
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
            normalized_file_type = file_type.lower()
            file_type_aliases = {
                "word": ["word", "doc", "docx"],
                "excel": ["excel", "xls", "xlsx", "csv"],
                "image": ["image", "jpg", "jpeg", "png", "gif", "bmp", "webp"],
            }
            if normalized_file_type in file_type_aliases:
                stmt = stmt.where(Attachment.file_type.in_(file_type_aliases[normalized_file_type]))
            else:
                stmt = stmt.where(Attachment.file_type == normalized_file_type)
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
        """附件详情（对外序列化：file_path 已投影为 opaque locator，见 _to_dict）"""
        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id, Attachment.is_deleted == sa.false())
        )
        a = result.scalar_one_or_none()
        return self._to_dict(a) if a else None

    async def get_raw_storage(self, attachment_id: UUID) -> dict | None:
        """内部真实存储位置解析（C3 例外通道）。

        ``_to_dict`` 的 ``file_path`` 对外已脱敏为 opaque locator，故受控下载/预览等
        **内部字节读取** 不能再依赖序列化 dict，必须经本方法拿真实 ``storage_type`` +
        ``file_path``（真实本地路径或 ``paperless://`` key）。本方法结果 **仅供服务端内部
        读取**，绝不进入对外响应。
        """
        result = await self.db.execute(
            sa.select(Attachment).where(
                Attachment.id == attachment_id, Attachment.is_deleted == sa.false()
            )
        )
        a = result.scalar_one_or_none()
        if a is None:
            return None
        return {
            "id": str(a.id),
            "project_id": str(a.project_id),
            "file_name": a.file_name,
            "file_size": a.file_size,
            "file_type": a.file_type,
            "storage_type": a.storage_type,
            "paperless_document_id": a.paperless_document_id,
            # 真实存储位置 —— 内部读取专用，禁止对外序列化。
            "file_path": a.file_path,
        }

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
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT, mounts={}, trust_env=False) as client:
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
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT, mounts={}, trust_env=False) as client:
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
            async with httpx.AsyncClient(timeout=settings.PAPERLESS_TIMEOUT, mounts={}, trust_env=False) as client:
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

    #: 未治理启发式抽取的响应标记（P2-⑤）：正则抽取的金额/日期/主体是 **辅助线索**，
    #: 未经 AI-gate / citation 治理，**必须经人工确认后** 才能进入任何正式底稿/结论。
    _HEURISTIC_GOVERNANCE_MARKER: dict = {
        "governed": False,
        "requires_human_confirmation": True,
        "note": (
            "启发式正则抽取，仅供参考线索；未经 AI-gate/citation 治理。"
            "在进入任何正式底稿或函证结论前必须由具备权限的人工核对确认。"
        ),
    }

    async def extract_confirmation_reply(self, attachment_id: UUID) -> dict:
        """从函证回函中提取关键信息（启发式辅助，非治理结论）。

        返回值恒含 ``governed=False`` / ``requires_human_confirmation=True`` 标记：本方法用正则
        从 OCR 文本抽取金额/日期/主体，是 **辅助线索** 而非正式结论；其输出未经 AI-gate 治理，
        若要进入正式底稿/函证结论必须先由人工核对确认（P2-⑤）。抽取算法本身不变。
        """
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
                **self._HEURISTIC_GOVERNANCE_MARKER,
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
            **self._HEURISTIC_GOVERNANCE_MARKER,
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
            # C3 opaque-locator（R1/R14 §6.1）：对外只投影为受控下载 URL 或 paperless://
            # scheme，绝不泄露绝对路径/原始 local storage key。真实路径的内部读取须走
            # get_raw_storage()，不得依赖此序列化值。兼容窗口内保留 file_path 键。
            "file_path": project_attachment_locator(
                a.id, storage_type=a.storage_type, storage_key=a.file_path
            ),
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
            # AT-3 版本字段
            "version": getattr(a, "version", 1),
            "previous_version_id": (
                str(a.previous_version_id) if getattr(a, "previous_version_id", None) else None
            ),
        }

    # ──────────────────────────────────────────────────────────────────────
    # AT-3 版本管理（spec proposal-remaining-18 task 5.3）
    # ──────────────────────────────────────────────────────────────────────

    def _dialect_name(self) -> str:
        """探测底层方言名（``postgresql`` / ``sqlite`` / ...）；失败返回空串。"""
        bind = None
        try:
            bind = self.db.get_bind()
        except Exception:
            bind = getattr(self.db, "bind", None)
        try:
            return bind.dialect.name if bind is not None else ""
        except Exception:
            return ""

    def _is_postgres(self) -> bool:
        return self._dialect_name() == "postgresql"

    async def _lock_version_chain(
        self,
        project_id: UUID,
        file_name: str,
        reference_id: UUID | None,
        reference_type: str | None,
    ) -> None:
        """在读取 ``max(version)`` 之前对逻辑版本链取父作用域锁（治理契约 R2/§5.1）。

        治理路径（``AttachmentVersionManager.replace_version``）对稳定的 ``attachments``
        父行取 ``SELECT ... FOR UPDATE`` 作为序列化点，读取 ``MAX(version_no)`` 再 +1。

        legacy 是**行式版本模型**（``attachments`` 表一行一个版本），没有稳定的父行；且
        对"当前最新行"取 ``FOR UPDATE`` **无法**阻止重复版本号 —— 两个并发事务各自锁住同
        一个旧的最新行、都算出 ``max+1``，各自插入的新最大行对对方是幻读，锁不到。因此这里
        采用 **chain 级 ``pg_advisory_xact_lock``** 作为逻辑父锁：它以链身份
        ``(project_id, file_name, reference_id, reference_type)`` 为键把同一条链上的所有并发
        replace 串行化（也覆盖首版创建竞态），事务结束自动释放，等价于治理层对父行的
        ``FOR UPDATE`` 序列化点。此外再对现有链行取一次 ``FOR UPDATE`` 行锁，显式"锁定现有
        版本链行"，与 R2/§5.1 措辞对齐。

        仅在 PostgreSQL 生效；SQLite 等单元测试方言为 no-op（并发正确性由真实 PG16 集成
        测试验证）。
        """
        if not self._is_postgres():
            return
        # (1) 逻辑父锁：以链身份为键的 advisory 事务锁（串行化点）。
        chain_key = "attachment_version_chain|{}|{}|{}|{}".format(
            project_id, file_name, reference_id, reference_type
        )
        await self.db.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": chain_key},
        )
        # (2) 显式对现有链行取 FOR UPDATE 行锁（对齐 §5.1 "锁定现有版本链行"）。
        lock_stmt = sa.select(Attachment.id).where(
            Attachment.project_id == project_id,
            Attachment.file_name == file_name,
            Attachment.is_deleted == sa.false(),
        )
        if reference_id is not None:
            lock_stmt = lock_stmt.where(Attachment.reference_id == reference_id)
        else:
            lock_stmt = lock_stmt.where(Attachment.reference_id.is_(None))
        if reference_type is not None:
            lock_stmt = lock_stmt.where(Attachment.reference_type == reference_type)
        else:
            lock_stmt = lock_stmt.where(Attachment.reference_type.is_(None))
        await self.db.execute(lock_stmt.with_for_update())

    async def _has_governance_version_chain(self, anchor_id: UUID | None) -> bool:
        """该附件是否已存在治理 ``AttachmentVersion`` 链（守卫用）。"""
        if anchor_id is None or not self._is_postgres():
            return False
        try:
            row = await self.db.execute(
                sa.text(
                    "SELECT 1 FROM attachment_versions WHERE attachment_id = :aid LIMIT 1"
                ),
                {"aid": str(anchor_id)},
            )
            return row.scalar() is not None
        except Exception:
            # 治理表在部分环境尚未建立 —— 视为无治理链。
            return False

    async def _emit_version_replaced_signal(
        self,
        *,
        new_att: Attachment,
        previous_version_id: UUID | None,
        actor: UUID | None,
        project_id: UUID,
        anchor_id: UUID | None,
    ) -> None:
        """发出与治理 replace 相同的失效信号（``attachment.version_replaced`` outbox 事件）。

        令下游可被标记 stale（R9.1）。**复用治理既有 outbox 事件，不新造事件类型**。

        守卫（§4.3/双版本模型收敛）：legacy 路径**绝不**写 ``attachment_versions``
        （治理不可变表）——即使该附件已存在治理链，也只镜像失效信号（使两条链经同一信号
        保持一致），不创建分叉的治理版本行。完整委派（改由治理 version manager 生成版本）
        因需要 content_hash / ActorContext / idempotency / capability 等 legacy 调用方不提供
        的输入、会破坏向后兼容，故本次延后。

        仅在 PostgreSQL + 有明确 actor 时发出；只 ``flush`` 不 ``commit``（与业务变更同事务，
        对齐治理 outbox 语义）。best-effort：治理表缺失时记 warning 不阻断 legacy 回滚/替换。
        """
        if actor is None or not self._is_postgres():
            return
        try:
            from app.services.evidence_governance.frozen_contracts import ActorContext
            from app.services.evidence_governance.outbox import (
                OutboxService,
                derive_event_id,
            )
        except Exception:  # pragma: no cover - 治理模块不可用时降级
            return
        try:
            actor_ctx = ActorContext.for_user(actor)
        except Exception:
            return
        governed = await self._has_governance_version_chain(anchor_id)
        event_type = "attachment.version_replaced"
        event_id = derive_event_id(
            command_root_id=new_att.id, event_type=event_type, seq=0
        )
        payload = {
            "attachment_id": str(new_att.id),
            # legacy 行式版本：版本即行本身，new_version_id 用新行 id。
            "new_version_id": str(new_att.id),
            "new_version_no": new_att.version,
            "previous_version_id": (
                str(previous_version_id) if previous_version_id else None
            ),
            "content_hash": None,
            "origin": "legacy_attachment_service",
            "governed_chain_present": governed,
        }
        try:
            await OutboxService(self.db).enqueue(
                project_id=project_id,
                audit_year=getattr(new_att, "audit_year", None),
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                actor=actor_ctx,
            )
        except Exception:  # pragma: no cover - 信号 best-effort，不阻断主流程
            logger.warning(
                "legacy attachment stale signal enqueue failed", exc_info=True
            )

    async def _resolve_version_chain(
        self,
        project_id: UUID,
        file_name: str,
        reference_id: UUID | None,
        reference_type: str | None,
    ) -> tuple[int, UUID | None]:
        """计算新版本号 + previous_version_id

        同 (project_id, reference_id, reference_type, file_name) 已有记录时，
        新 version = max(version) + 1，previous_version_id 指向当前最新版本。
        否则 version=1, previous_version_id=None。

        并发安全：读取 ``max(version)`` **之前**先对逻辑版本链取父作用域锁
        （``_lock_version_chain``），使并发 legacy replace 无法算出重复版本号。
        """
        # 父作用域锁 —— 必须先于 max(version) 读取（治理契约 R2/§5.1）。
        await self._lock_version_chain(project_id, file_name, reference_id, reference_type)

        stmt = (
            sa.select(Attachment)
            .where(
                Attachment.project_id == project_id,
                Attachment.file_name == file_name,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(Attachment.version.desc())
            .limit(1)
        )
        if reference_id is not None:
            stmt = stmt.where(Attachment.reference_id == reference_id)
        else:
            stmt = stmt.where(Attachment.reference_id.is_(None))
        if reference_type is not None:
            stmt = stmt.where(Attachment.reference_type == reference_type)
        else:
            stmt = stmt.where(Attachment.reference_type.is_(None))

        latest = (await self.db.execute(stmt)).scalar_one_or_none()
        if latest is None:
            return 1, None
        return (latest.version or 1) + 1, latest.id

    async def list_versions(
        self,
        attachment_id_or_project_id: UUID,
        file_name: str | None = None,
        reference_id: UUID | None = None,
        reference_type: str | None = None,
    ) -> list[dict]:
        """列出同名附件的版本链（按 version 升序）

        两种调用契约：
        - list_versions(attachment_id)：从 attachment_id 反查所属链（同 project_id + 同 file_name + 同 reference）
        - list_versions(project_id, file_name=..., reference_id=..., reference_type=...)：直接定位链

        attachment_id 不存在时返回 []
        """
        # 契约 1：仅传 attachment_id
        if file_name is None:
            entry = (
                await self.db.execute(
                    sa.select(Attachment).where(Attachment.id == attachment_id_or_project_id)
                )
            ).scalar_one_or_none()
            if entry is None:
                return []
            project_id = entry.project_id
            file_name = entry.file_name
            reference_id = entry.reference_id
            reference_type = entry.reference_type
        else:
            project_id = attachment_id_or_project_id

        stmt = (
            sa.select(Attachment)
            .where(
                Attachment.project_id == project_id,
                Attachment.file_name == file_name,
                Attachment.is_deleted == sa.false(),
            )
            .order_by(Attachment.version.asc())
        )
        if reference_id is not None:
            stmt = stmt.where(Attachment.reference_id == reference_id)
        else:
            stmt = stmt.where(Attachment.reference_id.is_(None))
        if reference_type is not None:
            stmt = stmt.where(Attachment.reference_type == reference_type)
        else:
            stmt = stmt.where(Attachment.reference_type.is_(None))

        result = await self.db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    async def rollback_to_version(
        self,
        attachment_id: UUID | None = None,
        version_id: UUID | None = None,
        project_id: UUID | None = None,
        file_name: str | None = None,
        target_version: int | None = None,
        reference_id: UUID | None = None,
        reference_type: str | None = None,
        created_by: UUID | None = None,
        rolled_back_by: UUID | None = None,
    ) -> dict:
        """回滚到指定历史版本：复制旧版本元数据创建 version=N+1 新行

        两种调用契约（任一即可）：
        - rollback_to_version(attachment_id, version_id, created_by=...) — 通过 attachment_id 锁定链 + version_id 定位目标
        - rollback_to_version(project_id, file_name, target_version, reference_id, reference_type, rolled_back_by=...) — 显式定位

        跨链回滚（version_id 不属于 attachment_id 所在链）→ raise ValueError
        旧版本不真删（is_deleted=false 保留），新行 previous_version_id 指向当前最新版本。
        """
        actor = created_by or rolled_back_by

        # 契约 1：attachment_id + version_id
        if attachment_id is not None and version_id is not None:
            entry = (
                await self.db.execute(
                    sa.select(Attachment).where(Attachment.id == attachment_id)
                )
            ).scalar_one_or_none()
            if entry is None:
                raise ValueError(f"attachment_id 不存在: {attachment_id}")
            target = (
                await self.db.execute(
                    sa.select(Attachment).where(Attachment.id == version_id)
                )
            ).scalar_one_or_none()
            if target is None:
                raise ValueError(f"version_id 不存在: {version_id}")
            # 跨链校验
            if (
                target.project_id != entry.project_id
                or target.file_name != entry.file_name
                or target.reference_id != entry.reference_id
                or target.reference_type != entry.reference_type
            ):
                raise ValueError(
                    f"跨链回滚被拒绝：version_id={version_id} 不属于 attachment_id={attachment_id} 所在链"
                )
            project_id = entry.project_id
            file_name = entry.file_name
            reference_id = entry.reference_id
            reference_type = entry.reference_type
        # 契约 2：(project_id, file_name, target_version)
        elif project_id is not None and file_name is not None and target_version is not None:
            target_stmt = (
                sa.select(Attachment)
                .where(
                    Attachment.project_id == project_id,
                    Attachment.file_name == file_name,
                    Attachment.version == target_version,
                    Attachment.is_deleted == sa.false(),
                )
            )
            if reference_id is not None:
                target_stmt = target_stmt.where(Attachment.reference_id == reference_id)
            else:
                target_stmt = target_stmt.where(Attachment.reference_id.is_(None))
            if reference_type is not None:
                target_stmt = target_stmt.where(Attachment.reference_type == reference_type)
            else:
                target_stmt = target_stmt.where(Attachment.reference_type.is_(None))
            target = (await self.db.execute(target_stmt)).scalar_one_or_none()
            if target is None:
                raise ValueError(
                    f"目标版本不存在: file_name={file_name}, version={target_version}"
                )
        else:
            raise ValueError(
                "必须提供 (attachment_id, version_id) 或 (project_id, file_name, target_version)"
            )

        # 锁定链的锚点（用于治理链存在性检查）：契约 1 用 entry，契约 2 用 target。
        anchor_id = target.id

        new_version, prev_id = await self._resolve_version_chain(
            project_id, file_name, reference_id, reference_type
        )
        # 回滚 = 追加一条 version=N+1 的**新行**，复制 target 的元数据。
        # 不可变性守卫：**只 INSERT 新行，绝不 UPDATE 任何历史行的 file_path/字节/
        # created_by**；target 及所有旧版本回滚后保持逐字节不变（治理 §4.3 / P4）。
        # actor 必须落库（治理要求：新记录须有明确责任主体）。
        new_att = Attachment(
            project_id=project_id,
            file_name=target.file_name,
            file_path=target.file_path,
            file_type=target.file_type,
            file_size=target.file_size,
            attachment_type=target.attachment_type,
            reference_id=target.reference_id,
            reference_type=target.reference_type,
            storage_type=target.storage_type,
            paperless_document_id=target.paperless_document_id,
            ocr_status=target.ocr_status,
            ocr_text=target.ocr_text,
            created_by=actor,
            version=new_version,
            previous_version_id=prev_id,
        )
        self.db.add(new_att)
        await self.db.flush()
        # 治理一致性：回滚创建了新版本 → 发出与治理 replace 相同的失效信号
        # （attachment.version_replaced），令下游可标记 stale；若该附件已有治理
        # AttachmentVersion 链则镜像信号 + 守卫（不创建分叉的治理版本行）。
        await self._emit_version_replaced_signal(
            new_att=new_att,
            previous_version_id=prev_id,
            actor=actor,
            project_id=project_id,
            anchor_id=anchor_id,
        )
        return self._to_dict(new_att)
