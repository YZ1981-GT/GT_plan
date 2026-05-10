"""OCR 识别服务 v2 — 单据识别 + AI分类 + 字段提取 + 批量处理 + 账目匹配

基于 PaddleOCR 的通用文档 OCR 识别，支持：
- 单张OCR识别（≤5秒）
- AI自动分类单据类型（12类）
- AI语义理解提取结构化字段
- 批量异步处理（Celery任务）
- 单据与账面数据自动匹配
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIService, AIServiceUnavailableError

try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None  # type: ignore

from app.models import (
    AIModelType,
    DocumentExtracted,
    DocumentMatch,
    DocumentScan,
    DocumentType,
    TbLedger,
    MatchResult,
    RecognitionStatus,
)
from app.models.dataset_models import LedgerDataset, DatasetStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局 PaddleOCR 实例（延迟初始化）
_paddle_ocr: "PaddleOCR | None" = None
# 线程池用于同步OCR调用
_ocr_executor = ThreadPoolExecutor(max_workers=4)

# 异步任务状态存储（内存，生产环境建议用Redis）
_task_status: dict[str, dict[str, Any]] = {}


def _get_ocr_engine() -> "PaddleOCR":
    """获取或创建 PaddleOCR 引擎实例"""
    global _paddle_ocr
    if _paddle_ocr is None:
        _paddle_ocr = PaddleOCR(
            lang="ch",
            use_angle_cls=True,
            use_gpu=False,
            show_log=False,
        )
    return _paddle_ocr


def _extract_text_from_result(result: Any) -> list[dict[str, Any]]:
    """从 PaddleOCR 结果中提取文本和置信度"""
    items = []
    if not result:
        return items

    for page_result in result:
        if not page_result:
            continue
        for line in page_result:
            if not line or len(line) < 2:
                continue
            coords = line[0] if line[0] else []
            text_info = line[1]
            if isinstance(text_info, tuple) and len(text_info) >= 2:
                text = text_info[0]
                confidence = text_info[1]
            else:
                text = str(text_info)
                confidence = 0.0

            items.append({
                "text": text,
                "bbox": coords,
                "confidence": float(confidence),
            })
    return items


# ======================================================================
# OCRService — 核心业务类
# ======================================================================

class OCRService:
    """OCR识别服务 — 单据处理完整流水线"""

    # 12类单据的字段提取规则
    DOCUMENT_FIELD_RULES: dict[str, list[str]] = {
        "sales_invoice": ["buyer_name", "amount", "tax_amount", "invoice_date", "invoice_no", "goods_name"],
        "purchase_invoice": ["seller_name", "amount", "tax_amount", "invoice_date", "invoice_no", "goods_name"],
        "bank_receipt": ["transaction_date", "counterparty_name", "amount", "summary", "transaction_type"],
        "bank_statement": ["transaction_date", "counterparty_name", "amount", "summary", "transaction_type"],
        "outbound_order": ["outbound_date", "product_name", "quantity", "unit_price", "amount", "customer"],
        "inbound_order": ["inbound_date", "product_name", "quantity", "unit_price", "amount", "supplier"],
        "logistics_order": ["ship_date", "receiver", "sender", "tracking_no", "sign_date"],
        "voucher": ["voucher_no", "date", "summary", "account_code", "account_name", "amount", "debit", "credit"],
        "tax_return": ["tax_type", "period", "amount", "filing_date"],
        "contract": ["party_a", "party_b", "contract_amount", "sign_date", "expire_date", "payment_terms"],
        "bank_reconciliation": ["bank_name", "account_no", "statement_date", "opening_balance", "closing_balance"],
        "other": [],
    }

    DOCUMENT_TYPE_LABELS: dict[str, str] = {
        "sales_invoice": "销售发票",
        "purchase_invoice": "采购发票",
        "bank_receipt": "银行收付款回单",
        "bank_statement": "银行对账单",
        "outbound_order": "出库单",
        "inbound_order": "入库单",
        "logistics_order": "物流单据",
        "voucher": "记账凭证",
        "tax_return": "纳税申报表",
        "contract": "合同协议",
        "bank_reconciliation": "银行余额调节表",
        "other": "其他单据",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AIService(db)

    # ------------------------------------------------------------------
    # 6.1 — recognize_single / classify_document / extract_fields
    # ------------------------------------------------------------------

    async def recognize_single(self, file_path: str) -> dict[str, Any]:
        """单张单据OCR识别，≤5秒，调PaddleOCR"""
        start = time.time()
        try:
            ocr = _get_ocr_engine()
            loop = asyncio.get_event_loop()

            # PaddleOCR是同步的，放线程池避免阻塞
            result = await loop.run_in_executor(
                _ocr_executor,
                lambda: ocr.ocr(file_path, cls=True)
            )

            items = _extract_text_from_result(result)
            full_text = "\n".join(item["text"] for item in items)
            elapsed = time.time() - start

            if elapsed > 5.0:
                logger.warning(f"OCR exceed 5s: {elapsed:.2f}s for {file_path}")

            return {
                "success": True,
                "items": items,
                "full_text": full_text,
                "stats": {
                    "total_lines": len(items),
                    "avg_confidence": round(
                        sum(i["confidence"] for i in items) / len(items), 4
                    ) if items else 0.0,
                    "processing_time": round(elapsed, 2),
                },
            }
        except Exception as e:
            logger.exception(f"OCR failed: {file_path}")
            return {"success": False, "error": str(e), "items": [], "full_text": ""}

    async def classify_document(self, ocr_text: str) -> str:
        """AI自动分类单据类型（12类），调LLM"""
        if not ocr_text or len(ocr_text.strip()) < 10:
            return "other"

        system_prompt = (
            "你是一个专业的审计单据分类助手。请根据OCR识别的单据文本，判断其类型。\n"
            "只能返回以下12种类型之一（只输出类型名称，不要其他内容）：\n"
            "sales_invoice, purchase_invoice, bank_receipt, bank_statement, "
            "outbound_order, inbound_order, logistics_order, voucher, "
            '"tax_return, contract, bank_reconciliation, other\\n\\n"'
            '"分类规则：\\n"'
            '"- 销售发票：包含"销项税"、"购买方"、"销售方"等\\n"'
            '"- 采购发票：包含"进项税"、"销售方"、"供应商"等\\n"'
            '"- 银行收付款回单：包含"收款人"、"付款人"、"交易金额"等\\n"'
            '"- 银行对账单：包含"对手户名"、"交易类型"、"余额"等\\n"'
            '"- 出库单：包含"出库"、"商品名称"、"数量"等\\n"'
            '"- 入库单：包含"入库"、"供应商"、"商品名称"等\\n"'
            '"- 物流单据：包含"收件人"、"寄件人"、"运单号"等\\n"'
            '"- 记账凭证：包含"借方"、"贷方"、"凭证号"等\\n"'
            '"- 纳税申报表：包含"税款"、"申报"、"税额"等\\n"'
            '"- 合同协议：包含"甲方"、"乙方"、"合同金额"等\\n"'
            '"- 银行余额调节表：包含"银行余额"、"企业余额"、"调节"等\\n"'
            '"- 其他：无法归类时用other"'
        )

        try:
            model = await self.ai.get_active_model(AIModelType.chat)
            model_name = model.model_name if model else settings.DEFAULT_CHAT_MODEL

            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请分类以下单据文本（前500字符）：\n{ocr_text[:500]}"},
                ],
                model=model_name,
                temperature=0.1,
            )

            result = response.strip().lower().replace(" ", "_")
            if result not in self.DOCUMENT_FIELD_RULES:
                result = "other"
            return result
        except Exception as e:
            logger.warning(f"LLM classify failed, defaulting to other: {e}")
            return "other"

    async def extract_fields(
        self, ocr_text: str, document_type: str
    ) -> list[dict[str, Any]]:
        """按DOCUMENT_FIELD_RULES提取结构化字段，调LLM语义理解"""
        fields = self.DOCUMENT_FIELD_RULES.get(document_type, [])
        if not fields or not ocr_text:
            return []

        field_list = ", ".join(fields)
        system_prompt = (
            '你是一个专业的审计字段提取助手。请从以下OCR文本中提取指定字段，'
            '返回JSON数组格式（只输出JSON，不要其他内容）。\n'
            f'字段列表：{field_list}\n'
            "提取规则：\n"
            "- 只提取存在的字段，找不到则值为null\n"
            '- 金额字段返回数字（去掉逗号和元字）\n'
            "- 日期字段返回 YYYY-MM-DD 格式\n"
            "- confidence表示该字段提取的可信度（0-1）\n"
            "返回格式示例：\n"
            '[{"field_name":"amount","field_value":"15000.00","confidence":0.95}]'
        )

        try:
            model = await self.ai.get_active_model(AIModelType.chat)
            model_name = model.model_name if model else settings.DEFAULT_CHAT_MODEL

            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请提取以下文本的字段：\n{ocr_text[:2000]}"},
                ],
                model=model_name,
                temperature=0.1,
            )

            # 尝试解析JSON
            text = response.strip()
            # 去掉 markdown 代码块
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            extracted = json.loads(text)
            if isinstance(extracted, list):
                return [
                    {
                        "field_name": item.get("field_name", ""),
                        "field_value": str(item.get("field_value", "")) if item.get("field_value") else None,
                        "confidence_score": round(float(item.get("confidence", 0.5)), 4),
                    }
                    for item in extracted
                    if item.get("field_name")
                ]
            return []
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM extract_fields failed: {e}")
            return []

    # ------------------------------------------------------------------
    # 6.2 — batch_recognize / get_task_status
    # ------------------------------------------------------------------

    async def batch_recognize(
        self, project_id: UUID, file_paths: list[str], user_id: UUID | None = None
    ) -> str:
        """批量OCR识别，提交后台异步任务，返回task_id"""
        task_id = str(uuid4())
        _task_status[task_id] = {
            "status": "pending",
            "total": len(file_paths),
            "processed": 0,
            "failed": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "errors": [],
            "results": [],
        }

        # 在后台线程运行（避免阻塞）
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            None,
            _batch_recognize_sync,
            task_id,
            str(project_id),
            file_paths,
            str(user_id) if user_id else None,
        )
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询批量任务进度"""
        return _task_status.get(task_id, {"status": "not_found"})


# ======================================================================
# 同步批量处理（在线程池中运行，避免阻塞事件循环）
# ======================================================================

def _batch_recognize_sync(task_id: str, project_id: str, file_paths: list[str], user_id: str | None):
    """同步批量处理 — 在线程池中运行"""
    import asyncio
    from app.core.database import async_session_maker

    async def _run():
        status = _task_status[task_id]
        status["status"] = "running"

        async with async_session_maker() as db:
            ai = AIService(db)

            for i, file_path in enumerate(file_paths):
                try:
                    # OCR识别
                    ocr = _get_ocr_engine()
                    result = ocr.ocr(file_path, cls=True)
                    items = _extract_text_from_result(result)
                    full_text = "\n".join(item["text"] for item in items)

                    # AI分类
                    doc_type = await _llm_classify(ai, full_text)

                    # 写入 document_scan
                    doc_scan = DocumentScan(
                        id=uuid4(),
                        project_id=UUID(project_id),
                        file_path=file_path,
                        file_name=os.path.basename(file_path),
                        file_size=os.path.getsize(file_path) if os.path.exists(file_path) else None,
                        document_type=DocumentType(doc_type),
                        recognition_status=RecognitionStatus.completed,
                        uploaded_by=UUID(user_id) if user_id else None,
                    )
                    db.add(doc_scan)
                    await db.flush()  # 获取 doc_scan.id

                    # AI字段提取
                    fields = await _llm_extract_fields(ai, full_text, doc_type)
                    for f in fields:
                        extracted = DocumentExtracted(
                            id=uuid4(),
                            document_scan_id=doc_scan.id,
                            field_name=f["field_name"],
                            field_value=f["field_value"],
                            confidence_score=Decimal(str(f["confidence_score"])),
                            human_confirmed=False,
                        )
                        db.add(extracted)

                    status["processed"] += 1
                    status["results"].append({
                        "file_path": file_path,
                        "document_id": str(doc_scan.id),
                        "document_type": doc_type,
                    })
                    await db.commit()

                except Exception as e:
                    logger.exception(f"batch item failed: {file_path}")
                    status["failed"] += 1
                    status["errors"].append({"file": file_path, "error": str(e)})
                    try:
                        await db.rollback()
                    except Exception:
                        pass

                # 更新进度
                _task_status[task_id] = status

            status["status"] = "completed"
            status["completed_at"] = datetime.now(timezone.utc).isoformat()
            _task_status[task_id] = status

    asyncio.run(_run())


async def _llm_classify(ai: AIService, ocr_text: str) -> str:
    """LLM分类（在线程中调用时需新建事件循环）"""
    if not ocr_text or len(ocr_text.strip()) < 10:
        return "other"

    system_prompt = (
        "你是单据分类助手，只返回以下类型之一：\n"
        "sales_invoice, purchase_invoice, bank_receipt, bank_statement, "
        "outbound_order, inbound_order, logistics_order, voucher, "
        "tax_return, contract, bank_reconciliation, other"
    )

    try:
        response = await ai.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"分类（仅输出类型）：\n{ocr_text[:500]}"},
            ],
            temperature=0.1,
        )
        result = response.strip().lower().replace(" ", "_")
        valid = [
            "sales_invoice", "purchase_invoice", "bank_receipt", "bank_statement",
            "outbound_order", "inbound_order", "logistics_order", "voucher",
            "tax_return", "contract", "bank_reconciliation", "other",
        ]
        return result if result in valid else "other"
    except Exception:
        return "other"


async def _llm_extract_fields(ai: AIService, ocr_text: str, doc_type: str) -> list[dict]:
    """LLM字段提取"""
    rules = {
        "sales_invoice": ["buyer_name", "amount", "tax_amount", "invoice_date", "invoice_no"],
        "purchase_invoice": ["seller_name", "amount", "tax_amount", "invoice_date", "invoice_no"],
        "bank_receipt": ["transaction_date", "counterparty_name", "amount", "summary"],
        "bank_statement": ["transaction_date", "counterparty_name", "amount", "summary"],
        "voucher": ["voucher_no", "date", "summary", "amount", "debit", "credit"],
        "other": [],
    }
    fields = rules.get(doc_type, [])
    if not fields or not ocr_text:
        return []

    system_prompt = (
        f"从文本提取以下字段，返回JSON数组：{', '.join(fields)}\n"
        "格式：[{\"field_name\":\"xxx\",\"field_value\":\"xxx\",\"confidence\":0.9}]"
    )

    try:
        response = await ai.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"提取字段：\n{ocr_text[:2000]}"},
            ],
            temperature=0.1,
        )
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        extracted = json.loads(text)
        return [
            {
                "field_name": item.get("field_name", ""),
                "field_value": str(item.get("field_value", "")) if item.get("field_value") else None,
                "confidence_score": round(float(item.get("confidence", 0.5)), 4),
            }
            for item in (extracted if isinstance(extracted, list) else [])
            if item.get("field_name")
        ]
    except Exception:
        return []


# ======================================================================
# 6.3 — match_with_ledger
# ======================================================================

async def match_with_ledger(
    db: AsyncSession,
    document_scan_id: UUID,
    project_id: UUID,
) -> DocumentMatch | None:
    """单据数据与账面数据自动匹配：按金额+日期+对方单位关键词"""
    # 1. 获取单据提取字段
    result = await db.execute(
        select(DocumentExtracted).where(
            DocumentExtracted.document_scan_id == document_scan_id
        )
    )
    fields = result.scalars().all()

    # 提取关键字段
    amount = None
    transaction_date = None
    counterparty = None

    for f in fields:
        fn = f.field_name.lower()
        if fn in ("amount", "金额", "amount_debit", "借方金额"):
            try:
                raw = f.field_value or ""
                amount = abs(float(raw.replace(",", "").replace("元", "")))
            except (ValueError, AttributeError):
                pass
        elif fn in ("transaction_date", "交易日期", "日期", "invoice_date"):
            transaction_date = f.field_value
        elif fn in ("counterparty_name", "对方单位", "supplier", "customer", "buyer_name", "seller_name"):
            counterparty = f.field_value

    if amount is None:
        return None

    # 2. 查询匹配账目（金额近似+日期相近+对方单位关键词）
    # B' 架构：用 dataset_id 过滤 active 数据（无 year 参数时查所有年度）
    active_ds_subq = (
        select(LedgerDataset.id)
        .where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.status == DatasetStatus.active,
        )
    )
    query = select(TbLedger).where(
        TbLedger.project_id == project_id,
        TbLedger.dataset_id.in_(active_ds_subq),
        TbLedger.is_deleted == False,  # noqa: E712
    )

    # 金额匹配（±1元容差）
    amount_condition = and_(
        TbLedger.debit_amount.isnot(None),
        func.abs(TbLedger.debit_amount - amount) <= 1.0,
    )
    credit_condition = and_(
        TbLedger.credit_amount.isnot(None),
        func.abs(TbLedger.credit_amount - amount) <= 1.0,
    )

    result = await db.execute(
        select(TbLedger).where(
            and_(
                query.whereclause,
                or_(amount_condition, credit_condition),
            )
        ).limit(10)
    )
    candidates = result.scalars().all()

    # 3. 筛选最佳匹配（对方单位关键词命中）
    best_match: TbLedger | None = None
    best_score = 0.0

    for entry in candidates:
        score = 0.0
        entry_text = f"{entry.summary or ''} {entry.counterparty or ''}".lower()

        if counterparty and counterparty.lower() in entry_text:
            score += 0.5
        if amount is not None:
            da = float(entry.debit_amount or 0)
            ca = float(entry.credit_amount or 0)
            matched_amt = max(da, ca)
            if matched_amt and abs(matched_amt - amount) <= 0.01:
                score += 0.5

        if score > best_score:
            best_score = score
            best_match = entry

    # 4. 写入匹配结果
    if best_match:
        matched_amt = float(best_match.debit_amount or best_match.credit_amount or 0)
        diff = round(matched_amt - amount, 2) if amount else None

        doc_match = DocumentMatch(
            id=uuid4(),
            document_scan_id=document_scan_id,
            matched_voucher_no=best_match.voucher_no,
            matched_account_code=best_match.account_code,
            matched_amount=Decimal(str(matched_amt)),
            match_result=MatchResult.exact if best_score >= 0.9 else MatchResult.fuzzy,
            difference_amount=Decimal(str(diff)) if diff else None,
            difference_description=f"金额差异：{diff}" if diff else None,
        )
        db.add(doc_match)
        await db.commit()
        await db.refresh(doc_match)
        return doc_match

    # 无匹配
    doc_match = DocumentMatch(
        id=uuid4(),
        document_scan_id=document_scan_id,
        match_result=MatchResult.no_match,
    )
    db.add(doc_match)
    await db.commit()
    await db.refresh(doc_match)
    return doc_match


# ======================================================================
# 6.1 复用 — 通用图片/PDF OCR（支持 router 直接调用）
# ======================================================================

async def process_image_bytes(
    image_data: bytes,
    ocr_type: str = "通用",
) -> dict[str, Any]:
    """处理图片字节，返回OCR结果"""
    start = time.time()
    try:
        ocr = _get_ocr_engine()
        loop = asyncio.get_event_loop()

        # base64编码后传给PaddleOCR
        b64_data = base64.b64encode(image_data).decode("utf-8")
        result = await loop.run_in_executor(
            _ocr_executor,
            lambda: ocr.ocr(b64_data, use_card_cls=False)
        )

        items = _extract_text_from_result(result)
        full_text = "\n".join(item["text"] for item in items)

        elapsed = time.time() - start

        return {
            "success": True,
            "items": items,
            "full_text": full_text,
            "stats": {
                "page_count": 1,
                "total_lines": len(items),
                "avg_confidence": round(
                    sum(i["confidence"] for i in items) / len(items), 4
                ) if items else 0.0,
                "processing_time": round(elapsed, 2),
                "ocr_type": ocr_type,
            },
        }
    except Exception as e:
        logger.exception("Image OCR processing failed")
        return {"success": False, "error": str(e), "items": [], "full_text": ""}


async def process_pdf_bytes(
    pdf_data: bytes,
    ocr_type: str = "通用",
) -> dict[str, Any]:
    """处理PDF字节（每页转图片后OCR）"""
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        return {"success": False, "error": "pdf2image not installed", "pages": []}

    start = time.time()
    try:
        images = convert_from_bytes(pdf_data, dpi=150)
        pages = []
        all_items = []
        all_texts = []
        total_lines = 0
        total_conf = 0.0

        ocr = _get_ocr_engine()
        loop = asyncio.get_event_loop()

        for page_idx, img in enumerate(images):
            page_start = time.time()
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            b64_data = base64.b64encode(img_bytes.read()).decode("utf-8")
            result = await loop.run_in_executor(
                _ocr_executor,
                lambda: ocr.ocr(b64_data, use_card_cls=False)
            )

            items = _extract_text_from_result(result)
            full_text = "\n".join(item["text"] for item in items)
            page_time = time.time() - page_start

            pages.append({
                "page": page_idx + 1,
                "items": items,
                "full_text": full_text,
                "stats": {
                    "total_lines": len(items),
                    "avg_confidence": round(
                        sum(i["confidence"] for i in items) / len(items), 4
                    ) if items else 0.0,
                    "processing_time": round(page_time, 2),
                },
            })
            all_items.extend(items)
            all_texts.append(full_text)
            total_lines += len(items)
            if items:
                total_conf += sum(i["confidence"] for i in items)

        return {
            "success": True,
            "pages": pages,
            "full_text": "\n\n--- Page Break ---\n\n".join(all_texts),
            "items": all_items,
            "stats": {
                "page_count": len(pages),
                "total_lines": total_lines,
                "avg_confidence": round(total_conf / total_lines, 4) if total_lines else 0.0,
                "processing_time": round(time.time() - start, 2),
                "ocr_type": ocr_type,
            },
        }
    except Exception as e:
        logger.exception("PDF OCR processing failed")
        return {"success": False, "error": str(e), "pages": []}
