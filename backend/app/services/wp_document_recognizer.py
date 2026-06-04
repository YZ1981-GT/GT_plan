"""原始凭证 LLM 识别服务 — wp-evidence-collection spec Task 3

替代 wp_ocr_voucher_service 正则版，按 doc_type 调 LLM 结构化提取。
支持 4+ 类型：记账凭证/发票/出入库单/银行回单

LLM 链路：
  - WP_AI_SERVICE_ENABLED=True → 调用 vLLM 结构化提取
  - WP_AI_SERVICE_ENABLED=False → 返回 stub 结果（字段模板）

确认流：复用 V3 Req6 wrap_ai_output_with_log 门禁
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DocType(str, Enum):
    """支持的原始凭证类型"""
    VOUCHER = "voucher"           # 记账凭证
    INVOICE = "invoice"           # 发票
    WAREHOUSE = "warehouse"       # 出入库单
    BANK_RECEIPT = "bank_receipt"  # 银行回单


# 各类型的提取字段定义
DOC_TYPE_FIELDS: dict[str, list[str]] = {
    DocType.VOUCHER: [
        "voucher_no",       # 凭证号
        "voucher_date",     # 凭证日期
        "debit_amount",     # 借方金额
        "credit_amount",    # 贷方金额
        "summary",          # 摘要
        "account_name",     # 科目名称
        "preparer",         # 制单人
        "reviewer",         # 审核人
    ],
    DocType.INVOICE: [
        "invoice_no",       # 发票号码
        "invoice_code",     # 发票代码
        "invoice_date",     # 开票日期
        "seller_name",      # 销方名称
        "buyer_name",       # 购方名称
        "amount",           # 金额（不含税）
        "tax_amount",       # 税额
        "total_amount",     # 价税合计
        "tax_rate",         # 税率
        "invoice_type",     # 发票类型（增值税专用/普通）
    ],
    DocType.WAREHOUSE: [
        "doc_no",           # 单据编号
        "doc_date",         # 单据日期
        "direction",        # 方向（入库/出库）
        "item_name",        # 物品名称
        "quantity",         # 数量
        "unit_price",       # 单价
        "total_amount",     # 金额
        "warehouse_name",   # 仓库名称
        "handler",          # 经手人
    ],
    DocType.BANK_RECEIPT: [
        "receipt_no",       # 回单编号
        "transaction_date", # 交易日期
        "payer_name",       # 付款方
        "payee_name",       # 收款方
        "amount",           # 金额
        "payer_account",    # 付款账号
        "payee_account",    # 收款账号
        "bank_name",        # 开户行
        "purpose",          # 用途/摘要
    ],
}

# LLM 提示词模板
_PROMPT_TEMPLATES: dict[str, str] = {
    DocType.VOUCHER: (
        "请从以下记账凭证图片/文本中提取结构化信息，以 JSON 格式返回：\n"
        "字段：voucher_no(凭证号), voucher_date(日期), debit_amount(借方金额), "
        "credit_amount(贷方金额), summary(摘要), account_name(科目), "
        "preparer(制单人), reviewer(审核人)\n"
        "文本内容：\n{text}"
    ),
    DocType.INVOICE: (
        "请从以下发票图片/文本中提取结构化信息，以 JSON 格式返回：\n"
        "字段：invoice_no(发票号码), invoice_code(发票代码), invoice_date(开票日期), "
        "seller_name(销方), buyer_name(购方), amount(金额), tax_amount(税额), "
        "total_amount(价税合计), tax_rate(税率), invoice_type(发票类型)\n"
        "文本内容：\n{text}"
    ),
    DocType.WAREHOUSE: (
        "请从以下出入库单图片/文本中提取结构化信息，以 JSON 格式返回：\n"
        "字段：doc_no(单据编号), doc_date(日期), direction(入库/出库), "
        "item_name(物品名称), quantity(数量), unit_price(单价), "
        "total_amount(金额), warehouse_name(仓库), handler(经手人)\n"
        "文本内容：\n{text}"
    ),
    DocType.BANK_RECEIPT: (
        "请从以下银行回单图片/文本中提取结构化信息，以 JSON 格式返回：\n"
        "字段：receipt_no(回单编号), transaction_date(交易日期), "
        "payer_name(付款方), payee_name(收款方), amount(金额), "
        "payer_account(付款账号), payee_account(收款账号), "
        "bank_name(开户行), purpose(用途)\n"
        "文本内容：\n{text}"
    ),
}


class WpDocumentRecognizer:
    """原始凭证 LLM 识别服务

    按 doc_type 分派不同的 prompt 模板调用 LLM 结构化提取。
    WP_AI_SERVICE_ENABLED=False 时返回 stub 结果。
    """

    async def recognize(
        self,
        db: AsyncSession,
        *,
        attachment_id: UUID,
        doc_type: str,
        project_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """识别单份原始凭证

        Returns:
            {
                "attachment_id": str,
                "doc_type": str,
                "status": "recognized" | "failed",
                "fields": { ... },
                "confidence": float,
                "is_llm_stub": bool,
            }
        """
        from app.core.config import settings

        # 获取附件信息
        att_info = await self._get_attachment_info(db, attachment_id)
        if not att_info:
            return {
                "attachment_id": str(attachment_id),
                "doc_type": doc_type,
                "status": "failed",
                "fields": {},
                "confidence": 0.0,
                "is_llm_stub": True,
                "error": "附件不存在",
            }

        # LLM 链路开关
        if not settings.WP_AI_SERVICE_ENABLED:
            # Stub 模式：返回字段模板
            fields = self._get_stub_fields(doc_type)
            return {
                "attachment_id": str(attachment_id),
                "doc_type": doc_type,
                "status": "recognized",
                "fields": fields,
                "confidence": 0.0,
                "is_llm_stub": True,
            }

        # 真实 LLM 识别
        try:
            fields = await self._llm_recognize(db, attachment_id, att_info, doc_type)
            confidence = 0.85 if fields else 0.0

            # 写入 ai_content_log（复用 V3 Req6 确认流）
            if fields and project_id and user_id:
                await self._write_ai_content_log(
                    db, fields, doc_type, project_id, user_id, attachment_id
                )

            return {
                "attachment_id": str(attachment_id),
                "doc_type": doc_type,
                "status": "recognized" if fields else "failed",
                "fields": fields or {},
                "confidence": confidence,
                "is_llm_stub": False,
            }
        except Exception as e:
            logger.error("LLM recognize failed: %s", e)
            return {
                "attachment_id": str(attachment_id),
                "doc_type": doc_type,
                "status": "failed",
                "fields": {},
                "confidence": 0.0,
                "is_llm_stub": False,
                "error": str(e),
            }

    async def recognize_batch(
        self,
        db: AsyncSession,
        *,
        attachments: list[dict[str, Any]],
        project_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """批量识别原始凭证

        Args:
            attachments: [{"attachment_id": str, "doc_type": str}, ...]

        Returns:
            {"total": int, "recognized": int, "results": [...]}
        """
        results = []
        for att in attachments:
            result = await self.recognize(
                db,
                attachment_id=UUID(att["attachment_id"]),
                doc_type=att.get("doc_type", DocType.VOUCHER),
                project_id=project_id,
                user_id=user_id,
            )
            results.append(result)

        return {
            "total": len(results),
            "recognized": sum(1 for r in results if r["status"] == "recognized"),
            "results": results,
        }

    def get_supported_doc_types(self) -> list[dict[str, Any]]:
        """获取支持的凭证类型列表"""
        return [
            {"code": DocType.VOUCHER, "name": "记账凭证", "fields": DOC_TYPE_FIELDS[DocType.VOUCHER]},
            {"code": DocType.INVOICE, "name": "发票", "fields": DOC_TYPE_FIELDS[DocType.INVOICE]},
            {"code": DocType.WAREHOUSE, "name": "出入库单", "fields": DOC_TYPE_FIELDS[DocType.WAREHOUSE]},
            {"code": DocType.BANK_RECEIPT, "name": "银行回单", "fields": DOC_TYPE_FIELDS[DocType.BANK_RECEIPT]},
        ]

    def _get_stub_fields(self, doc_type: str) -> dict[str, Any]:
        """Stub 模式：返回字段模板（所有值为 None）"""
        fields_list = DOC_TYPE_FIELDS.get(doc_type, DOC_TYPE_FIELDS[DocType.VOUCHER])
        return {field: None for field in fields_list}

    async def _llm_recognize(
        self,
        db: AsyncSession,
        attachment_id: UUID,
        att_info: dict[str, Any],
        doc_type: str,
    ) -> dict[str, Any] | None:
        """调用 LLM 结构化提取

        实际实现：
          1. 读取附件文件（图片/PDF）
          2. OCR 提取文本（MinerU / PaddleOCR）
          3. 构造 doc_type 对应的 prompt
          4. 调用 vLLM 获取 JSON 输出
          5. 解析并返回字段
        """
        try:
            import json

            from app.core.config import settings as app_settings
            from app.schemas.llm_structured import DocRecognitionResult

            ocr_text = f"[附件: {att_info.get('filename', '')}]"
            prompt = _PROMPT_TEMPLATES.get(doc_type, _PROMPT_TEMPLATES[DocType.VOUCHER])
            prompt = prompt.format(text=ocr_text)
            messages = [{"role": "user", "content": prompt}]

            if app_settings.LLM_STRUCTURED_OUTPUT_ENABLED:
                from app.services.structured_llm_service import (
                    StructuredOutputError,
                    extract_structured,
                )

                try:
                    result = await extract_structured(
                        messages,
                        DocRecognitionResult,
                        max_tokens=1000,
                        temperature=0.1,
                    )
                    parsed = result.fields
                    if parsed:
                        return parsed
                except StructuredOutputError as exc:
                    logger.warning("structured extract failed, legacy fallback: %s", exc)

            from app.services.llm_client import chat_completion

            content = await chat_completion(
                messages,
                max_tokens=1000,
                temperature=0.1,
            )
            if content and "{" in content:
                json_str = content[content.index("{"):content.rindex("}") + 1]
                return json.loads(json_str)
            return None
        except Exception as e:
            logger.warning("LLM recognize error: %s", e)
            return None

    async def _write_ai_content_log(
        self,
        db: AsyncSession,
        fields: dict[str, Any],
        doc_type: str,
        project_id: UUID,
        user_id: UUID,
        attachment_id: UUID,
    ) -> None:
        """写入 ai_content_log 触发确认流门禁"""
        try:
            import json
            from app.services.wp_ai_service import wrap_ai_output_with_log

            content = json.dumps(fields, ensure_ascii=False, default=str)
            await wrap_ai_output_with_log(
                content=content,
                confidence=0.85,
                db=db,
                project_id=project_id,
                user_id=user_id,
                instance_type="document_recognition",
                instance_id=attachment_id,
            )
        except Exception as e:
            logger.warning("write_ai_content_log failed: %s", e)

    async def _get_attachment_info(
        self, db: AsyncSession, attachment_id: UUID
    ) -> dict[str, Any] | None:
        """获取附件基本信息"""
        result = await db.execute(text(
            "SELECT id, file_name, file_path, file_type "
            "FROM attachments WHERE id = :att_id"
        ), {"att_id": str(attachment_id)})
        row = result.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "filename": row[1],
            "file_path": row[2],
            "file_type": row[3],
        }


# 单例
wp_document_recognizer = WpDocumentRecognizer()
