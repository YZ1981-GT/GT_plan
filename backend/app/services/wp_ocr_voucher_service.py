"""凭证 OCR 结构化提取服务

Sprint 7 Task 7.1: 扩展 unified_ocr_service，新增凭证结构化提取模板。
提取字段：凭证号/日期/摘要/借方科目+金额/贷方科目+金额/制单人/审核人
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class VoucherEntry:
    """凭证分录行"""
    account_code: str = ""
    account_name: str = ""
    amount: Decimal = Decimal("0")
    direction: str = ""  # debit / credit


@dataclass
class VoucherOCRResult:
    """凭证 OCR 结构化结果"""
    voucher_no: str = ""
    voucher_date: Optional[date] = None
    summary: str = ""
    debit_entries: list[VoucherEntry] = field(default_factory=list)
    credit_entries: list[VoucherEntry] = field(default_factory=list)
    preparer: str = ""
    reviewer: str = ""
    confidence: float = 0.0
    raw_text: str = ""


# 凭证字段提取正则模板
_PATTERNS = {
    "voucher_no": [
        re.compile(r"(?:凭证号|记账凭证|凭证编号|No)[.：:\s]*([A-Za-z]*[\-]?\d+)"),
        re.compile(r"(?:转|收|付|记)-?(\d{3,6})"),
    ],
    "date": [
        re.compile(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})"),
        re.compile(r"日期[：:\s]*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})"),
    ],
    "preparer": [
        re.compile(r"(?:制单|编制|制表|记账)[人员]?[：:\s]*([^\s,，]{2,4})"),
    ],
    "reviewer": [
        re.compile(r"(?:审核|复核|审批)[人员]?[：:\s]*([^\s,，]{2,4})"),
    ],
    "summary": [
        re.compile(r"(?:摘要|说明)[：:\s]*(.+?)(?:\n|$)"),
    ],
    "amount": [
        re.compile(r"([\d,]+\.\d{2})"),
    ],
    "account": [
        re.compile(r"(\d{4}(?:\.\d{2,4})?)\s+(.+?)(?:\s|$)"),
    ],
}


def parse_voucher_from_text(raw_text: str) -> VoucherOCRResult:
    """从 OCR 原始文本解析凭证结构化数据

    Args:
        raw_text: OCR 识别的原始文本

    Returns:
        VoucherOCRResult 结构化结果
    """
    result = VoucherOCRResult(raw_text=raw_text)
    lines = raw_text.strip().split("\n")
    confidence_scores: list[float] = []

    # 提取凭证号
    for pat in _PATTERNS["voucher_no"]:
        m = pat.search(raw_text)
        if m:
            result.voucher_no = m.group(1).strip()
            confidence_scores.append(0.9)
            break

    # 提取日期
    for pat in _PATTERNS["date"]:
        m = pat.search(raw_text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                result.voucher_date = date(y, mo, d)
                confidence_scores.append(0.95)
            except (ValueError, IndexError):
                pass
            break

    # 提取摘要
    for pat in _PATTERNS["summary"]:
        m = pat.search(raw_text)
        if m:
            result.summary = m.group(1).strip()[:200]
            confidence_scores.append(0.8)
            break

    # 提取制单人/审核人
    for pat in _PATTERNS["preparer"]:
        m = pat.search(raw_text)
        if m:
            result.preparer = m.group(1).strip()
            confidence_scores.append(0.85)
            break

    for pat in _PATTERNS["reviewer"]:
        m = pat.search(raw_text)
        if m:
            result.reviewer = m.group(1).strip()
            confidence_scores.append(0.85)
            break

    # 提取借贷分录（简化：按行扫描含金额的行）
    _extract_entries(lines, result)

    # 综合置信度
    if confidence_scores:
        result.confidence = round(sum(confidence_scores) / len(confidence_scores), 2)
    else:
        result.confidence = 0.3

    return result


def _extract_entries(lines: list[str], result: VoucherOCRResult) -> None:
    """从文本行中提取借贷分录"""
    current_direction = ""
    for line in lines:
        line_lower = line.strip()
        if not line_lower:
            continue

        # 判断借贷方向
        if "借" in line_lower and "贷" not in line_lower:
            current_direction = "debit"
        elif "贷" in line_lower and "借" not in line_lower:
            current_direction = "credit"

        # 提取金额
        amounts = _PATTERNS["amount"][0].findall(line_lower)
        if not amounts:
            continue

        # 提取科目
        account_code = ""
        account_name = ""
        acct_match = _PATTERNS["account"][0].search(line_lower)
        if acct_match:
            account_code = acct_match.group(1)
            account_name = acct_match.group(2).strip()
        else:
            # 尝试提取纯文本科目名
            cleaned = re.sub(r"[\d,]+\.\d{2}", "", line_lower)
            cleaned = re.sub(r"[借贷]", "", cleaned).strip()
            if len(cleaned) >= 2:
                account_name = cleaned[:20]

        amount_val = Decimal(amounts[0].replace(",", ""))
        entry = VoucherEntry(
            account_code=account_code,
            account_name=account_name,
            amount=amount_val,
            direction=current_direction or "debit",
        )

        if current_direction == "credit":
            result.credit_entries.append(entry)
        else:
            result.debit_entries.append(entry)


async def ocr_voucher_image(image_path: str) -> VoucherOCRResult:
    """对凭证图片执行 OCR + 结构化提取

    Args:
        image_path: 凭证图片文件路径

    Returns:
        VoucherOCRResult
    """
    from app.services.unified_ocr_service import UnifiedOCRService

    ocr_svc = UnifiedOCRService()
    ocr_result = await ocr_svc.recognize(image_path, doc_type="voucher")
    raw_text = ocr_result.get("text", "")

    return parse_voucher_from_text(raw_text)


async def batch_ocr_vouchers(image_paths: list[str]) -> list[VoucherOCRResult]:
    """批量凭证 OCR

    Args:
        image_paths: 凭证图片路径列表

    Returns:
        VoucherOCRResult 列表
    """
    results = []
    for path in image_paths:
        try:
            r = await ocr_voucher_image(path)
            results.append(r)
        except Exception as e:
            logger.warning("OCR failed for %s: %s", path, e)
            results.append(VoucherOCRResult(raw_text=f"[OCR失败: {e}]", confidence=0.0))
    return results
