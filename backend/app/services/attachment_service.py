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
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment, AttachmentWorkingPaper


class AttachmentService:
    """附件管理服务"""

    def __init__(
        self,
        db: AsyncSession,
        paperless_url: str | None = None,
        paperless_token: str | None = None,
    ):
        self.db = db
        self.paperless_url = paperless_url
        self.paperless_token = paperless_token

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_attachment(
        self, project_id: UUID, data: dict[str, Any],
        created_by: UUID | None = None,
    ) -> dict:
        """创建附件记录"""
        attachment = Attachment(
            project_id=project_id,
            file_name=data["file_name"],
            file_path=data["file_path"],
            file_type=data.get("file_type", "unknown"),
            file_size=data.get("file_size", 0),
            paperless_document_id=data.get("paperless_document_id"),
            ocr_status=data.get("ocr_status", "pending"),
            created_by=created_by,
        )
        self.db.add(attachment)
        await self.db.flush()
        return self._to_dict(attachment)

    async def list_attachments(
        self, project_id: UUID,
        file_type: str | None = None,
        ocr_status: str | None = None,
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

    # ------------------------------------------------------------------
    # 全文搜索
    # ------------------------------------------------------------------

    async def search(self, project_id: UUID, query: str) -> list[dict]:
        """全文搜索附件（搜索文件名和 OCR 文本）"""
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

    # ------------------------------------------------------------------
    # Paperless-ngx 集成（需要 httpx）
    # ------------------------------------------------------------------

    async def upload_to_paperless(self, file_path: str, metadata: dict) -> int | None:
        """上传文档到 Paperless-ngx，返回 document_id"""
        if not self.paperless_url or not self.paperless_token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
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
            async with httpx.AsyncClient(timeout=15) as client:
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
            async with httpx.AsyncClient(timeout=15) as client:
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
    # 15.5 自动文档分类
    # ------------------------------------------------------------------

    # 文件名关键词 → 文档类型映射
    _TYPE_KEYWORDS: dict[str, list[str]] = {
        "contract": ["合同", "协议", "contract", "agreement"],
        "invoice": ["发票", "invoice", "税票"],
        "bank_statement": ["银行", "对账单", "流水", "bank"],
        "confirmation": ["函证", "回函", "询证", "confirmation"],
        "license": ["证照", "营业执照", "许可证", "license"],
        "voucher": ["凭证", "记账", "voucher"],
        "report": ["报告", "报表", "report"],
    }

    # 文件名中的期间模式
    _PERIOD_PATTERNS: list[str] = [
        r"20\d{2}",           # 2024, 2025
        r"20\d{2}[-/]\d{1,2}",  # 2024-01, 2025/12
        r"\d{1,2}月",         # 1月, 12月
    ]

    async def classify_document(self, attachment_id: UUID) -> dict:
        """自动分类文档（基于文件名 + OCR 文本分析）

        返回：document_type, customer_hint, period_hint
        """
        import re

        result = await self.db.execute(
            sa.select(Attachment).where(Attachment.id == attachment_id)
        )
        att = result.scalar_one_or_none()
        if not att:
            raise ValueError("附件不存在")

        file_name = (att.file_name or "").lower()
        ocr_text = (att.ocr_text or "")[:500].lower()  # 只分析前500字
        combined = file_name + " " + ocr_text

        # 1. 文档类型识别
        doc_type = "unknown"
        for dtype, keywords in self._TYPE_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                doc_type = dtype
                break

        # 2. 文件扩展名辅助判断
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

        # 3. 期间提取
        period_hint = None
        for pattern in self._PERIOD_PATTERNS:
            match = re.search(pattern, att.file_name or "")
            if match:
                period_hint = match.group()
                break

        # 4. 客户名称提示（从文件名中提取非关键词部分）
        customer_hint = None
        name_parts = re.split(r"[-_\s.]+", (att.file_name or "").rsplit(".", 1)[0])
        for part in name_parts:
            if len(part) >= 2 and not any(kw in part.lower() for kws in self._TYPE_KEYWORDS.values() for kw in kws):
                if not re.match(r"^\d+$", part):  # 排除纯数字
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
    # 15.6 函证回函 OCR 识别
    # ------------------------------------------------------------------

    # 回函关键字段的正则模式
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
        """从函证回函中提取关键信息

        提取：回函金额、回函日期、回函单位名称
        依赖 OCR 文本（ocr_text 字段）
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
            }

        # 1. 提取金额
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

        # 2. 提取日期
        reply_date = None
        for pattern in self._DATE_PATTERNS:
            match = re.search(pattern, ocr_text)
            if match:
                reply_date = match.group(1)
                break

        # 3. 提取回函单位
        reply_entity = None
        for pattern in self._ENTITY_PATTERNS:
            match = re.search(pattern, ocr_text)
            if match:
                reply_entity = match.group(1).strip()
                break

        # 4. 置信度评估
        found_count = sum(1 for v in [reply_amount, reply_date, reply_entity] if v is not None)
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

    def _to_dict(self, a: Attachment) -> dict:
        return {
            "id": str(a.id),
            "project_id": str(a.project_id),
            "file_name": a.file_name,
            "file_path": a.file_path,
            "file_type": a.file_type,
            "file_size": a.file_size,
            "paperless_document_id": a.paperless_document_id,
            "ocr_status": a.ocr_status,
            "ocr_text": a.ocr_text[:200] if a.ocr_text else None,  # 截断预览
            "is_deleted": a.is_deleted,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
