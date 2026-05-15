"""OCR 结果→抽凭表自动填充逻辑

Sprint 7 Task 7.2: 将 OCR 识别结果自动填入底稿抽凭表。
Sprint 7 Task 7.4: 凭证照片↔抽凭表行双向关联。
Sprint 7 Task 7.7: 合同/对账单 OCR 提取→台账自动填充。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_ocr_voucher_service import VoucherOCRResult

logger = logging.getLogger(__name__)


async def fill_voucher_table_from_ocr(
    db: AsyncSession,
    wp_id: UUID,
    ocr_results: list[VoucherOCRResult],
    attachment_ids: list[UUID],
    user_id: UUID,
) -> dict:
    """将 OCR 结果填入抽凭表底稿的 parsed_data

    Args:
        db: 数据库会话
        wp_id: 底稿 ID
        ocr_results: OCR 结构化结果列表
        attachment_ids: 对应的附件 ID 列表（与 ocr_results 一一对应）
        user_id: 操作人

    Returns:
        填充结果摘要
    """
    from app.models.workpaper_models import WorkingPaper

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()

    if not wp:
        return {"error": "底稿不存在", "filled_count": 0}

    parsed_data = wp.parsed_data or {}
    voucher_rows = parsed_data.get("voucher_rows", [])

    filled_count = 0
    for i, ocr_result in enumerate(ocr_results):
        if ocr_result.confidence < 0.3:
            continue

        attachment_id = attachment_ids[i] if i < len(attachment_ids) else None

        # 构建抽凭表行
        row = {
            "id": str(uuid4()),
            "voucher_no": ocr_result.voucher_no,
            "voucher_date": ocr_result.voucher_date.isoformat() if ocr_result.voucher_date else None,
            "summary": ocr_result.summary,
            "debit_entries": [
                {"account_code": e.account_code, "account_name": e.account_name, "amount": str(e.amount)}
                for e in ocr_result.debit_entries
            ],
            "credit_entries": [
                {"account_code": e.account_code, "account_name": e.account_name, "amount": str(e.amount)}
                for e in ocr_result.credit_entries
            ],
            "preparer": ocr_result.preparer,
            "reviewer": ocr_result.reviewer,
            "confidence": ocr_result.confidence,
            "attachment_id": str(attachment_id) if attachment_id else None,
            "source": "ocr",
            "filled_at": datetime.now(timezone.utc).isoformat(),
            "filled_by": str(user_id),
        }
        voucher_rows.append(row)
        filled_count += 1

    # 更新 parsed_data
    parsed_data["voucher_rows"] = voucher_rows
    parsed_data["last_ocr_fill"] = datetime.now(timezone.utc).isoformat()

    await db.execute(
        sa.text("UPDATE working_paper SET parsed_data = :pd WHERE id = :wid"),
        {"pd": sa.type_coerce(parsed_data, sa.JSON), "wid": str(wp_id)},
    )
    await db.flush()

    logger.info("OCR fill: wp_id=%s filled=%d rows", wp_id, filled_count)
    return {"filled_count": filled_count, "total_rows": len(voucher_rows)}


async def link_photo_to_voucher_row(
    db: AsyncSession,
    wp_id: UUID,
    row_id: str,
    attachment_id: UUID,
) -> bool:
    """凭证照片↔抽凭表行双向关联（Task 7.4）

    Args:
        db: 数据库会话
        wp_id: 底稿 ID
        row_id: 抽凭表行 ID
        attachment_id: 附件 ID

    Returns:
        是否关联成功
    """
    from app.models.workpaper_models import WorkingPaper

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()

    if not wp or not wp.parsed_data:
        return False

    parsed_data = wp.parsed_data
    voucher_rows = parsed_data.get("voucher_rows", [])

    for row in voucher_rows:
        if row.get("id") == row_id:
            row["attachment_id"] = str(attachment_id)
            break
    else:
        return False

    parsed_data["voucher_rows"] = voucher_rows
    await db.execute(
        sa.text("UPDATE working_paper SET parsed_data = :pd WHERE id = :wid"),
        {"pd": sa.type_coerce(parsed_data, sa.JSON), "wid": str(wp_id)},
    )
    await db.flush()
    return True


async def fill_ledger_from_contract_ocr(
    db: AsyncSession,
    wp_id: UUID,
    ocr_text: str,
    doc_type: str,
    user_id: UUID,
) -> dict:
    """合同/对账单 OCR 提取→台账自动填充（Task 7.7）

    Args:
        db: 数据库会话
        wp_id: 台账底稿 ID
        ocr_text: OCR 识别的原始文本
        doc_type: 文档类型 (contract / statement)
        user_id: 操作人

    Returns:
        填充结果
    """
    import re
    from app.models.workpaper_models import WorkingPaper

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()

    if not wp:
        return {"error": "底稿不存在", "filled_count": 0}

    parsed_data = wp.parsed_data or {}
    ledger_rows = parsed_data.get("ledger_rows", [])

    extracted = _extract_contract_fields(ocr_text, doc_type)
    if extracted:
        extracted["id"] = str(uuid4())
        extracted["source"] = f"ocr_{doc_type}"
        extracted["filled_at"] = datetime.now(timezone.utc).isoformat()
        extracted["filled_by"] = str(user_id)
        ledger_rows.append(extracted)

    parsed_data["ledger_rows"] = ledger_rows
    await db.execute(
        sa.text("UPDATE working_paper SET parsed_data = :pd WHERE id = :wid"),
        {"pd": sa.type_coerce(parsed_data, sa.JSON), "wid": str(wp_id)},
    )
    await db.flush()

    return {"filled_count": 1 if extracted else 0, "extracted": extracted}


def _extract_contract_fields(text: str, doc_type: str) -> Optional[dict]:
    """从合同/对账单文本提取关键字段"""
    import re

    result: dict = {}

    # 合同号
    m = re.search(r"(?:合同号|合同编号|编号)[：:\s]*([A-Za-z0-9\-]+)", text)
    if m:
        result["contract_no"] = m.group(1)

    # 金额
    amounts = re.findall(r"(?:金额|总价|合计)[：:\s]*([\d,]+\.?\d*)", text)
    if amounts:
        result["amount"] = amounts[0].replace(",", "")

    # 对方单位
    m = re.search(r"(?:甲方|乙方|供应商|客户)[：:\s]*(.+?)(?:\n|$)", text)
    if m:
        result["counterparty"] = m.group(1).strip()[:50]

    # 日期
    m = re.search(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})", text)
    if m:
        result["date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # 对账单特有字段
    if doc_type == "statement":
        m = re.search(r"(?:余额|期末余额)[：:\s]*([\d,]+\.?\d*)", text)
        if m:
            result["balance"] = m.group(1).replace(",", "")

    return result if result else None
