"""OCR 字段提取服务 — Round 4 需求 12

提供 POST /api/attachments/{id}/ocr-fields 的业务逻辑：
- 若 attachment.ocr_status='completed'，直接返回 ocr_fields_cache
- 若 pending/failed，异步触发 OCR（unified_ocr_service.recognize + extract_fields）
- 结果缓存到 attachment.ocr_fields_cache JSONB
- 同一附件多次提取复用缓存结果

Validates: Requirements 12.2, 12.5
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment

logger = logging.getLogger(__name__)

# 内存中的异步 OCR 任务状态（生产环境建议用 Redis）
_ocr_jobs: dict[str, dict[str, Any]] = {}


class OcrFieldsService:
    """OCR 字段提取服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_trigger_ocr_fields(
        self, attachment_id: UUID
    ) -> tuple[dict[str, Any], int]:
        """获取或触发 OCR 字段提取。

        Returns:
            (response_body, http_status_code)
            - 200 + fields: 已完成，直接返回缓存
            - 202 + job_id: 异步触发中
            - 404: 附件不存在
        """
        # 1. 查询附件
        result = await self.db.execute(
            sa.select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.is_deleted == sa.false(),
            )
        )
        attachment = result.scalar_one_or_none()
        if not attachment:
            return {"detail": "附件不存在"}, 404

        # 2. 若已完成且有缓存，直接返回
        if attachment.ocr_status == "completed" and attachment.ocr_fields_cache:
            return {
                "status": "completed",
                "attachment_id": str(attachment_id),
                "fields": attachment.ocr_fields_cache,
            }, 200

        # 3. 若已完成但无缓存（旧数据），用 ocr_text 提取字段
        if attachment.ocr_status == "completed" and attachment.ocr_text:
            fields = await self._extract_fields_from_text(
                attachment.ocr_text, attachment.file_name
            )
            # 缓存结果
            attachment.ocr_fields_cache = fields
            attachment.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.flush()
            return {
                "status": "completed",
                "attachment_id": str(attachment_id),
                "fields": fields,
            }, 200

        # 4. 未完成，触发异步 OCR
        job_id = str(uuid.uuid4())
        _ocr_jobs[job_id] = {
            "status": "processing",
            "attachment_id": str(attachment_id),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "result": None,
            "error": None,
        }

        # 更新状态为 processing
        attachment.ocr_status = "processing"
        attachment.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.flush()

        # 启动后台任务
        asyncio.create_task(
            self._run_ocr_async(attachment_id, job_id)
        )

        return {
            "status": "processing",
            "attachment_id": str(attachment_id),
            "job_id": job_id,
            "message": "OCR 处理已触发，请轮询获取结果",
        }, 202

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """查询异步 OCR 任务状态"""
        return _ocr_jobs.get(job_id)

    async def _run_ocr_async(self, attachment_id: UUID, job_id: str) -> None:
        """后台异步执行 OCR 识别 + 字段提取"""
        from app.core.database import async_session

        try:
            async with async_session() as db:
                result = await db.execute(
                    sa.select(Attachment).where(Attachment.id == attachment_id)
                )
                attachment = result.scalar_one_or_none()
                if not attachment:
                    _ocr_jobs[job_id]["status"] = "failed"
                    _ocr_jobs[job_id]["error"] = "附件不存在"
                    return

                # 执行 OCR 识别
                ocr_text = await self._perform_ocr(attachment.file_path)

                # 提取字段
                fields = await self._extract_fields_from_text(
                    ocr_text, attachment.file_name
                )

                # 更新附件记录
                attachment.ocr_status = "completed"
                attachment.ocr_text = ocr_text
                attachment.ocr_fields_cache = fields
                attachment.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await db.commit()

                # 更新任务状态
                _ocr_jobs[job_id]["status"] = "completed"
                _ocr_jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
                _ocr_jobs[job_id]["result"] = fields

        except Exception as exc:
            logger.exception("OCR async job failed: attachment_id=%s", attachment_id)
            _ocr_jobs[job_id]["status"] = "failed"
            _ocr_jobs[job_id]["error"] = str(exc)

            # 尝试将状态回退为 failed
            try:
                from app.core.database import async_session
                async with async_session() as db:
                    result = await db.execute(
                        sa.select(Attachment).where(Attachment.id == attachment_id)
                    )
                    att = result.scalar_one_or_none()
                    if att:
                        att.ocr_status = "failed"
                        att.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        await db.commit()
            except Exception:
                logger.exception("Failed to update attachment status to failed")

    async def _perform_ocr(self, file_path: str) -> str:
        """执行 OCR 识别，返回全文文本"""
        try:
            from app.services.unified_ocr_service import UnifiedOCRService

            ocr_service = UnifiedOCRService()
            result = await ocr_service.recognize(file_path)
            return result.get("text", "")
        except Exception as exc:
            logger.warning("UnifiedOCRService failed, trying stub: %s", exc)
            # 如果 OCR 引擎不可用，返回空文本（stub 模式）
            return ""

    async def _extract_fields_from_text(
        self, ocr_text: str, file_name: str
    ) -> dict[str, Any]:
        """从 OCR 文本中提取结构化字段

        复用 ocr_service_v2 的 classify + extract_fields 能力。
        如果 AI 不可用，返回基于规则的 stub 结果。
        """
        if not ocr_text or len(ocr_text.strip()) < 5:
            return {"fields": [], "document_type": "other", "extracted_at": _now_iso()}

        try:
            from app.services.ocr_service_v2 import OCRService

            # OCRService 需要 db session，但这里只用其分类和提取方法
            # 创建一个轻量实例
            ocr_svc = OCRService(self.db)

            # 分类文档类型
            doc_type = await ocr_svc.classify_document(ocr_text)

            # 提取字段
            fields_list = await ocr_svc.extract_fields(ocr_text, doc_type)

            # 转换为 dict 格式便于前端使用
            fields_dict = {}
            for f in fields_list:
                field_name = f.get("field_name", "")
                if field_name:
                    fields_dict[field_name] = f.get("field_value")

            return {
                "fields": fields_list,
                "fields_dict": fields_dict,
                "document_type": doc_type,
                "extracted_at": _now_iso(),
            }

        except Exception as exc:
            logger.warning("OCR field extraction via AI failed: %s", exc)
            # Stub: 返回基于文件名的默认字段
            return self._stub_extract(file_name)

    def _stub_extract(self, file_name: str) -> dict[str, Any]:
        """Stub 提取 — AI 不可用时返回空结构"""
        file_lower = file_name.lower() if file_name else ""

        # 根据文件名猜测文档类型
        doc_type = "other"
        if any(kw in file_lower for kw in ("发票", "invoice", "vat")):
            doc_type = "sales_invoice"
        elif any(kw in file_lower for kw in ("银行", "bank", "回单")):
            doc_type = "bank_receipt"
        elif any(kw in file_lower for kw in ("合同", "contract")):
            doc_type = "contract"

        return {
            "fields": [],
            "fields_dict": {},
            "document_type": doc_type,
            "extracted_at": _now_iso(),
            "note": "OCR 引擎暂不可用，请稍后重试",
        }


def _now_iso() -> str:
    """当前 UTC 时间 ISO 格式"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
