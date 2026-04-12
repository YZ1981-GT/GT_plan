"""函证 AI 服务 v2

辅助审计函证流程，包括：
- 函证地址核查（函证对象地址 vs 注册地址 vs 历史回函地址比对）
- 回函扫描件OCR识别
- 印章检测与名称比对
- 不符差异原因智能分析

对应需求: 7.1-7.6
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_models import (
    AIConfirmationAudit,
    AIModelType,
    ConfirmationAICheck,
    ConfirmationCheckType,
    ConfirmationRiskLevel,
)
from app.models.collaboration_models import (
    ConfirmationList,
    ConfirmationResult,
    ConfirmationAttachment,
    ConfirmationType,
    ConfirmationListStatus,
    ConfirmationResultStatus,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class AIServiceUnavailableError(Exception):
    """AI服务不可用"""
    pass


# ============================================================================
# ConfirmationAIService — 函证AI辅助服务
# ============================================================================

class ConfirmationAIService:
    """函证 AI 辅助服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AIService(db)

    # -------------------------------------------------------------------------
    # 13.1 — verify_address / verify_addresses
    # -------------------------------------------------------------------------

    async def verify_address(
        self,
        project_id: UUID,
        confirmation_id: UUID,
    ) -> dict[str, Any]:
        """
        函证地址核查（函证对象地址 vs 注册地址 vs 历史回函地址比对）

        返回:
            {
                "check_id": UUID,
                "confirmation_id": UUID,
                "match_score": float,  # 0-100
                "discrepancies": list[str],
                "registered_address": str | None,
                "confirmation_address": str | None,
                "historical_addresses": list[str],
                "check_result": str,  # normal / suspicious / mismatch
                "risk_level": str,
            }
        """
        # 1. 查询函证记录
        result = await self.db.execute(
            select(ConfirmationList).where(
                ConfirmationList.id == confirmation_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
            )
        )
        confirmation = result.scalar_one_or_none()
        if not confirmation:
            raise ValueError(f"Confirmation not found: {confirmation_id}")

        confirmation_address = confirmation.counterparty_address or ""
        counterparty_name = confirmation.counterparty_name

        # 2. 模拟获取注册地址（实际应从工商数据/企业信息API获取）
        registered_address = await self._get_registered_address(counterparty_name)

        # 3. 查询历史回函地址
        historical_addresses = await self._get_historical_addresses(
            project_id, counterparty_name, confirmation_id
        )

        # 4. 地址比对分析
        match_score, discrepancies, check_result = await self._analyze_address_match(
            confirmation_address, registered_address, historical_addresses
        )

        # 5. 确定风险等级
        risk_level = self._classify_address_risk(
            match_score, discrepancies, confirmation_address, registered_address
        )

        # 6. 写入 confirmation_ai_check 表
        check_record = ConfirmationAICheck(
            confirmation_list_id=confirmation_id,
            check_type=ConfirmationCheckType.address_verify,
            check_result={
                "match_score": match_score,
                "discrepancies": discrepancies,
                "confirmation_address": confirmation_address,
                "registered_address": registered_address,
                "historical_addresses": historical_addresses,
                "check_result": check_result,
            },
            risk_level=ConfirmationRiskLevel(risk_level) if risk_level else None,
            human_confirmed=False,
        )
        self.db.add(check_record)
        await self.db.commit()
        await self.db.refresh(check_record)

        return {
            "check_id": str(check_record.id),
            "confirmation_id": str(confirmation_id),
            "match_score": match_score,
            "discrepancies": discrepancies,
            "registered_address": registered_address,
            "confirmation_address": confirmation_address,
            "historical_addresses": historical_addresses,
            "check_result": check_result,
            "risk_level": risk_level,
        }

    async def verify_addresses(
        self,
        project_id: UUID,
        confirmation_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        批量地址核查：
        - 比对工商登记地址
        - 比对上年函证地址
        - 标注疑似异常地址
        - 银行函证校验开户行名称与网点地址
        """
        # 查询项目下的函证记录
        query = select(ConfirmationList).where(
            ConfirmationList.project_id == project_id,
            ConfirmationList.is_deleted == False,  # noqa: E712
        )
        if confirmation_type:
            try:
                ct = ConfirmationType(confirmation_type)
                query = query.where(ConfirmationList.confirmation_type == ct)
            except ValueError:
                pass

        result = await self.db.execute(query)
        confirmations = result.scalars().all()

        results = []
        for conf in confirmations:
            try:
                check_result = await self.verify_address(project_id, conf.id)
                results.append(check_result)
            except Exception as e:
                logger.warning(f"Address verification failed for {conf.id}: {e}")
                results.append({
                    "confirmation_id": str(conf.id),
                    "error": str(e),
                    "check_result": "failed",
                })

        return results

    async def _get_registered_address(self, counterparty_name: str) -> str | None:
        """
        获取工商登记地址
        实际应调用工商数据API或企业信息查询服务
        此处模拟返回
        """
        # 模拟：从企业信息缓存中获取（实际应查询 company_info 或外部API）
        return None  # 暂无注册地址数据

    async def _get_historical_addresses(
        self,
        project_id: UUID,
        counterparty_name: str,
        current_confirmation_id: UUID,
    ) -> list[str]:
        """查询历史回函地址"""
        # 查询同一方但不同期间的历史函证
        result = await self.db.execute(
            select(ConfirmationList).where(
                ConfirmationList.project_id == project_id,
                ConfirmationList.counterparty_name == counterparty_name,
                ConfirmationList.id != current_confirmation_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
            ).order_by(ConfirmationList.created_at.desc()).limit(5)
        )
        historical = result.scalars().all()

        addresses = []
        for h in historical:
            if h.counterparty_address:
                addresses.append(h.counterparty_address)

        return addresses

    async def _analyze_address_match(
        self,
        confirmation_address: str,
        registered_address: str | None,
        historical_addresses: list[str],
    ) -> tuple[float, list[str], str]:
        """分析地址匹配度"""
        discrepancies = []
        match_details = []

        # 空地址检查
        if not confirmation_address:
            return 0.0, ["函证地址为空"], "suspicious"

        # 与注册地址比对
        if registered_address:
            similarity = self._calculate_text_similarity(
                confirmation_address, registered_address
            )
            if similarity < 0.7:
                discrepancies.append(
                    f"函证地址与注册地址不符（相似度{similarity:.0%}）"
                )
            else:
                match_details.append("注册地址匹配")
        else:
            # 无注册地址时，标记为待核实
            discrepancies.append("未查询到工商登记地址")

        # 与历史地址比对
        if historical_addresses:
            for hist_addr in historical_addresses:
                if hist_addr == confirmation_address:
                    match_details.append("与历史回函地址一致")
                    break
            else:
                # 与所有历史地址都不一致
                discrepancies.append(
                    f"函证地址与历史回函地址均不一致（共{len(historical_addresses)}条历史记录）"
                )

        # 计算总分
        base_score = 100.0
        for disc in discrepancies:
            if "不符" in disc or "不一致" in disc:
                base_score -= 30
            elif "为空" in disc or "未查询" in disc:
                base_score -= 15

        match_score = max(0, min(100, base_score))

        # 判断结果
        if match_score >= 80 and not any("不符" in d for d in discrepancies):
            check_result = "normal"
        elif match_score >= 50:
            check_result = "suspicious"
        else:
            check_result = "mismatch"

        return match_score, discrepancies, check_result

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度（简单字符级）"""
        if not text1 or not text2:
            return 0.0

        # 标准化：去除空格和标点，转小写
        t1 = re.sub(r"[\s\，。、；：""''（）【】]", "", text1.lower())
        t2 = re.sub(r"[\s\，。、；：""''（）【】]", "", text2.lower())

        if t1 == t2:
            return 1.0

        # 简单Jaccard相似度（字符级）
        set1, set2 = set(t1), set(t2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _classify_address_risk(
        self,
        match_score: float,
        discrepancies: list[str],
        confirmation_address: str,
        registered_address: str | None,
    ) -> str:
        """分类地址风险等级"""
        if match_score >= 80 and not discrepancies:
            return "low"
        elif match_score >= 50:
            return "medium"
        else:
            return "high"

    # -------------------------------------------------------------------------
    # 13.2 — ocr_reply_scan
    # -------------------------------------------------------------------------

    async def ocr_reply_scan(
        self,
        project_id: UUID,
        confirmation_id: UUID,
        file_path: str,
    ) -> dict[str, Any]:
        """
        回函扫描件OCR识别

        - 使用 PaddleOCR 提取文字
        - LLM 提取回函单位名称、确认金额、签章、回函日期
        - 与原始函证金额比对
        - 写入 confirmation_ai_check 表

        返回:
            {
                "check_id": UUID,
                "replying_entity": str | None,
                "confirmed_amount": float | None,
                "original_amount": float | None,
                "amount_difference": float | None,
                "amount_match": bool,
                "seal_detected": bool,
                "seal_name": str | None,
                "reply_date": str | None,
                "full_ocr_text": str,
                "risk_level": str,
            }
        """
        # 1. 查询函证记录获取原始金额
        result = await self.db.execute(
            select(ConfirmationList).where(
                ConfirmationList.id == confirmation_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
            )
        )
        confirmation = result.scalar_one_or_none()
        if not confirmation:
            raise ValueError(f"Confirmation not found: {confirmation_id}")

        original_amount = (
            float(confirmation.balance_or_amount)
            if confirmation.balance_or_amount
            else None
        )

        # 2. OCR 识别
        try:
            ocr_result = await self.ai.ocr_recognize(file_path)
            ocr_text = ocr_result.get("text", "")
            regions = ocr_result.get("regions", [])
        except Exception as e:
            logger.warning(f"OCR failed for {file_path}: {e}")
            ocr_text = ""
            regions = []

        # 3. LLM 提取关键字段
        extracted = await self._extract_reply_fields(ocr_text, confirmation.counterparty_name)

        replying_entity = extracted.get("replying_entity")
        confirmed_amount = extracted.get("confirmed_amount")
        seal_detected = extracted.get("seal_detected", False)
        seal_name = extracted.get("seal_name")
        reply_date = extracted.get("reply_date")

        # 4. 金额比对
        amount_match = None
        amount_difference = None
        if original_amount is not None and confirmed_amount is not None:
            amount_difference = abs(confirmed_amount - original_amount)
            # 容差 ±1% 视为匹配
            tolerance = original_amount * 0.01
            amount_match = amount_difference <= tolerance
        elif confirmed_amount is not None:
            amount_match = False
            amount_difference = confirmed_amount

        # 5. 判断风险等级
        risk_level = self._classify_reply_risk(
            amount_match, amount_difference, seal_detected, replying_entity,
            confirmation.counterparty_name
        )

        # 6. 写入 confirmation_ai_check 表
        check_record = ConfirmationAICheck(
            confirmation_list_id=confirmation_id,
            check_type=ConfirmationCheckType.reply_ocr,
            check_result={
                "replying_entity": replying_entity,
                "confirmed_amount": confirmed_amount,
                "original_amount": original_amount,
                "amount_difference": amount_difference,
                "amount_match": amount_match,
                "seal_detected": seal_detected,
                "seal_name": seal_name,
                "reply_date": reply_date,
                "ocr_text": ocr_text[:500],  # 截断存储
            },
            risk_level=ConfirmationRiskLevel(risk_level) if risk_level else None,
            human_confirmed=False,
        )
        self.db.add(check_record)
        await self.db.commit()
        await self.db.refresh(check_record)

        return {
            "check_id": str(check_record.id),
            "confirmation_id": str(confirmation_id),
            "replying_entity": replying_entity,
            "confirmed_amount": confirmed_amount,
            "original_amount": original_amount,
            "amount_difference": amount_difference,
            "amount_match": amount_match,
            "seal_detected": seal_detected,
            "seal_name": seal_name,
            "reply_date": reply_date,
            "full_ocr_text": ocr_text,
            "risk_level": risk_level,
        }

    async def _extract_reply_fields(
        self,
        ocr_text: str,
        expected_entity: str,
    ) -> dict[str, Any]:
        """使用 LLM 从 OCR 文本中提取回函关键字段"""
        if not ocr_text:
            return {}

        system_prompt = """你是专业的审计函证回函分析助手。请从以下OCR识别的回函扫描件文本中提取关键信息。

需要提取的字段：
- replying_entity: 回函单位名称（盖章单位）
- confirmed_amount: 确认金额（数字，如无明确金额填null）
- seal_detected: 是否检测到印章（true/false）
- seal_name: 印章名称（如"XX银行XX支行业务专用章"）
- reply_date: 回函日期（YYYY-MM-DD格式）

返回JSON格式：
{
  "replying_entity": "XXX",
  "confirmed_amount": 1234567.00,
  "seal_detected": true,
  "seal_name": "XX银行XX支行",
  "reply_date": "2024-01-15"
}

如果无法确定某字段，填null。不要输出除JSON外的其他内容。"""

        try:
            model = await self.ai.get_active_model(AIModelType.chat)
            model_name = model.model_name if model else "qwen2.5:7b"

            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请分析以下回函文本（前2000字符）：\n{ocr_text[:2000]}\n\n预期回函单位：{expected_entity}"},
                ],
                model=model_name,
                temperature=0.1,
            )

            # 解析JSON响应
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                extracted = json.loads(json_match.group())
                return extracted

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        # 回退：使用规则提取金额
        amount = self._extract_amount_by_rules(ocr_text)
        seal_name = self._extract_seal_by_rules(ocr_text)

        return {
            "confirmed_amount": amount,
            "seal_detected": bool(seal_name),
            "seal_name": seal_name,
        }

    def _extract_amount_by_rules(self, text: str) -> float | None:
        """使用规则提取金额"""
        # 匹配金额模式：可能有"确认金额"、"余额"等关键词
        patterns = [
            r"确认金额[：:]\s*([\d,]+\.?\d*)",
            r"余额[：:]\s*([\d,]+\.?\d*)",
            r"截止\d{4}年\d{1,2}月\d{1,2}日[余额：:]\s*([\d,]+\.?\d*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except ValueError:
                    pass
        return None

    def _extract_seal_by_rules(self, text: str) -> str | None:
        """使用规则提取印章名称"""
        # 匹配印章模式
        patterns = [
            r"([^\s]+银行[^\s]+支行?[业务专用章]*)",
            r"([^\s]+有限公司[^\s]*)",
            r"([^\s]+合作社[^\s]*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _classify_reply_risk(
        self,
        amount_match: bool | None,
        amount_difference: float | None,
        seal_detected: bool,
        replying_entity: str | None,
        expected_entity: str,
    ) -> str:
        """分类回函风险等级"""
        # 印章缺失
        if not seal_detected:
            return "high"

        # 金额不匹配
        if amount_match is False:
            if amount_difference and amount_difference > 100000:
                return "high"
            return "medium"

        # 回函单位不符
        if replying_entity and expected_entity:
            if replying_entity not in expected_entity and expected_entity not in replying_entity:
                return "medium"

        return "low"

    # -------------------------------------------------------------------------
    # 13.3 — check_seal
    # -------------------------------------------------------------------------

    async def check_seal(
        self,
        project_id: UUID,
        confirmation_id: UUID,
    ) -> dict[str, Any]:
        """
        印章检测与名称比对

        - 检测印章存在性
        - 提取印章文字
        - 与函证对象名称比对
        - 银行函证校验银行业务专用章

        返回:
            {
                "check_id": UUID,
                "has_seal": bool,
                "seal_text": str | None,
                "matches_bank": bool,
                "matches_counterparty": bool,
                "risk_level": str,
            }
        """
        # 1. 查询函证记录
        result = await self.db.execute(
            select(ConfirmationList).where(
                ConfirmationList.id == confirmation_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
            )
        )
        confirmation = result.scalar_one_or_none()
        if not confirmation:
            raise ValueError(f"Confirmation not found: {confirmation_id}")

        # 2. 查询最新OCR结果
        ocr_result = await self.db.execute(
            select(ConfirmationAICheck).where(
                ConfirmationAICheck.confirmation_list_id == confirmation_id,
                ConfirmationAICheck.check_type == ConfirmationCheckType.reply_ocr,
                ConfirmationAICheck.is_deleted == False,  # noqa: E712
            ).order_by(ConfirmationAICheck.created_at.desc())
        )
        ocr_record = ocr_result.scalars().first()

        has_seal = False
        seal_text = None
        ocr_text = ""

        if ocr_record and ocr_record.check_result:
            has_seal = ocr_record.check_result.get("seal_detected", False)
            seal_text = ocr_record.check_result.get("seal_name")
            ocr_text = ocr_record.check_result.get("ocr_text", "")

        # 如果没有OCR记录，尝试从附件获取
        if not ocr_record:
            attachment_result = await self.db.execute(
                select(ConfirmationAttachment).where(
                    ConfirmationAttachment.confirmation_list_id == confirmation_id,
                    ConfirmationAttachment.is_deleted == False,  # noqa: E712
                ).order_by(ConfirmationAttachment.created_at.desc())
            )
            attachment = attachment_result.scalars().first()

            if attachment:
                try:
                    ocr_result = await self.ai.ocr_recognize(attachment.file_path)
                    ocr_text = ocr_result.get("text", "")
                    extracted = await self._extract_reply_fields(ocr_text, confirmation.counterparty_name)
                    has_seal = extracted.get("seal_detected", False)
                    seal_text = extracted.get("seal_name")
                except Exception as e:
                    logger.warning(f"OCR failed for attachment: {e}")

        # 3. 比对印章名称与银行/对方单位
        is_bank_confirmation = confirmation.confirmation_type == ConfirmationType.bank
        matches_bank = False
        matches_counterparty = False

        if seal_text:
            counterparty_name = confirmation.counterparty_name

            # 银行函证：印章应为银行业务专用章
            if is_bank_confirmation:
                bank_keywords = ["银行", "支行", "业务专用章", "储蓄所"]
                if any(kw in seal_text for kw in bank_keywords):
                    matches_bank = True
                    # 进一步检查是否包含对方银行名称关键词
                    if any(kw in seal_text for kw in counterparty_name):
                        matches_bank = True

            # 非银行函证：印章应与对方单位名称匹配
            else:
                # 简单匹配：印章文字包含对方单位名
                for part in counterparty_name.split():
                    if len(part) >= 2 and part in seal_text:
                        matches_counterparty = True
                        break

        # 4. 判断风险等级
        risk_level = self._classify_seal_risk(
            has_seal, matches_bank, matches_counterparty, is_bank_confirmation
        )

        # 5. 写入 confirmation_ai_check 表
        check_record = ConfirmationAICheck(
            confirmation_list_id=confirmation_id,
            check_type=ConfirmationCheckType.seal_check,
            check_result={
                "has_seal": has_seal,
                "seal_text": seal_text,
                "matches_bank": matches_bank,
                "matches_counterparty": matches_counterparty,
                "is_bank_confirmation": is_bank_confirmation,
            },
            risk_level=ConfirmationRiskLevel(risk_level) if risk_level else None,
            human_confirmed=False,
        )
        self.db.add(check_record)
        await self.db.commit()
        await self.db.refresh(check_record)

        return {
            "check_id": str(check_record.id),
            "confirmation_id": str(confirmation_id),
            "has_seal": has_seal,
            "seal_text": seal_text,
            "matches_bank": matches_bank,
            "matches_counterparty": matches_counterparty,
            "risk_level": risk_level,
        }

    def _classify_seal_risk(
        self,
        has_seal: bool,
        matches_bank: bool,
        matches_counterparty: bool,
        is_bank_confirmation: bool,
    ) -> str:
        """分类印章风险等级"""
        if not has_seal:
            return "high"

        if is_bank_confirmation:
            if matches_bank:
                return "low"
            return "medium"

        if matches_counterparty:
            return "low"

        return "medium"

    # -------------------------------------------------------------------------
    # 13.3 — analyze_mismatch_reason
    # -------------------------------------------------------------------------

    async def analyze_mismatch_reason(
        self,
        project_id: UUID,
        confirmation_id: UUID,
        original_amount: float,
        reply_amount: float,
    ) -> dict[str, Any]:
        """
        不符差异原因智能分析

        - 匹配在途款项（期后银行流水/收付款记录）
        - 识别记账时间差（凭证日期比对）
        - 生成差异原因建议

        返回:
            {
                "check_id": UUID,
                "likely_reasons": list[str],
                "in_transit_items": list[dict],
                "timing_differences": list[dict],
                "suggested_reconciliation": str,
                "risk_level": str,
            }
        """
        # 1. 查询函证记录
        result = await self.db.execute(
            select(ConfirmationList).where(
                ConfirmationList.id == confirmation_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
            )
        )
        confirmation = result.scalar_one_or_none()
        if not confirmation:
            raise ValueError(f"Confirmation not found: {confirmation_id}")

        # 2. 计算差异
        difference = abs(original_amount - reply_amount)
        difference_ratio = difference / original_amount if original_amount else 0

        # 3. 查询在途款项（模拟：实际应查询银行流水/收付款记录）
        in_transit_items = await self._find_in_transit_items(
            project_id, confirmation.counterparty_name, difference
        )

        # 4. 识别时间差（模拟：实际应查询凭证日期）
        timing_differences = await self._find_timing_differences(
            project_id, confirmation.counterparty_name, confirmation.as_of_date
        )

        # 5. LLM 生成差异原因分析
        ai_analysis = await self._generate_mismatch_analysis(
            original_amount, reply_amount, difference, difference_ratio,
            confirmation.counterparty_name, confirmation.confirmation_type.value,
            in_transit_items, timing_differences
        )

        # 6. 判断风险等级
        risk_level = "low"
        if difference_ratio > 0.1:  # 差异超过10%
            risk_level = "high"
        elif difference_ratio > 0.01:  # 差异超过1%
            risk_level = "medium"

        # 7. 写入 confirmation_ai_check 表
        check_record = ConfirmationAICheck(
            confirmation_list_id=confirmation_id,
            check_type=ConfirmationCheckType.amount_compare,
            check_result={
                "original_amount": original_amount,
                "reply_amount": reply_amount,
                "difference": difference,
                "difference_ratio": difference_ratio,
                "likely_reasons": ai_analysis.get("likely_reasons", []),
                "in_transit_items": in_transit_items,
                "timing_differences": timing_differences,
                "suggested_reconciliation": ai_analysis.get("suggested_reconciliation", ""),
            },
            risk_level=ConfirmationRiskLevel(risk_level),
            human_confirmed=False,
        )
        self.db.add(check_record)
        await self.db.commit()
        await self.db.refresh(check_record)

        return {
            "check_id": str(check_record.id),
            "confirmation_id": str(confirmation_id),
            "original_amount": original_amount,
            "reply_amount": reply_amount,
            "difference": difference,
            "difference_ratio": difference_ratio,
            "likely_reasons": ai_analysis.get("likely_reasons", []),
            "in_transit_items": in_transit_items,
            "timing_differences": timing_differences,
            "suggested_reconciliation": ai_analysis.get("suggested_reconciliation", ""),
            "risk_level": risk_level,
        }

    async def _find_in_transit_items(
        self,
        project_id: UUID,
        counterparty_name: str,
        difference: float,
    ) -> list[dict[str, Any]]:
        """
        查找在途款项
        实际应查询银行对账单、收付款记录
        """
        # 模拟返回，实际应从 journal_entries 或银行流水中查询
        # 查找期后（函证截止日后）的大额收付款
        return []

    async def _find_timing_differences(
        self,
        project_id: UUID,
        counterparty_name: str,
        as_of_date: date | None,
    ) -> list[dict[str, Any]]:
        """
        识别记账时间差
        实际应查询凭证日期分布
        """
        # 模拟返回，实际应从 journal_entries 查询
        # 比对双方入账日期差异
        return []

    async def _generate_mismatch_analysis(
        self,
        original_amount: float,
        reply_amount: float,
        difference: float,
        difference_ratio: float,
        counterparty_name: str,
        confirmation_type: str,
        in_transit_items: list[dict],
        timing_differences: list[dict],
    ) -> dict[str, Any]:
        """使用 LLM 生成不符原因分析"""

        system_prompt = f"""你是一名资深审计师，请分析以下函证不符的原因。

背景信息：
- 函证类型：{confirmation_type}
- 对方单位：{counterparty_name}
- 账面余额：{original_amount:,.2f}
- 回函确认金额：{reply_amount:,.2f}
- 差异金额：{difference:,.2f}
- 差异比例：{difference_ratio:.2%}

可能的不符原因包括：
1. 在途款项（已付款但对方尚未收到，或已收款但我方尚未入账）
2. 时间性差异（双方入账时间不一致，如月末最后一天的交易）
3. 未达账项（银行已收付但企业未记账）
4. 记账差错（一方或双方存在记账错误）
5. 交易取消（已入账交易后来被取消）
6. 部分确认（对方仅确认部分金额）
7. 汇率差异（外币业务因汇率波动产生差异）

请给出：
1. likely_reasons: 最可能的3-5个原因（按可能性排序）
2. suggested_reconciliation: 建议的追查程序（100字以内）

只返回JSON格式：
{{
  "likely_reasons": ["原因1", "原因2", "原因3"],
  "suggested_reconciliation": "建议的追查程序..."
}}"""

        try:
            model = await self.ai.get_active_model(AIModelType.chat)
            model_name = model.model_name if model else "qwen2.5:7b"

            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "请分析不符原因并给出建议。"},
                ],
                model=model_name,
                temperature=0.3,
            )

            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.warning(f"LLM mismatch analysis failed: {e}")

        # 回退：基于差异比例给出建议
        if difference_ratio > 0.1:
            likely_reasons = [
                "差异金额较大，可能存在未达账项或在途款项",
                "建议核对银行对账单及收付款记录",
            ]
        elif difference_ratio > 0.01:
            likely_reasons = [
                "差异金额较小，可能为时间性差异或四舍五入所致",
                "建议核对双方记账日期",
            ]
        else:
            likely_reasons = ["差异金额很小，可能无需进一步追查"]

        return {
            "likely_reasons": likely_reasons,
            "suggested_reconciliation": "核对银行对账单和收付款记录，确认是否存在未达账项。",
        }

    # -------------------------------------------------------------------------
    # AI 检查结果管理
    # -------------------------------------------------------------------------

    async def get_ai_checks(
        self,
        project_id: UUID,
        confirmation_id: UUID | None = None,
        check_type: ConfirmationCheckType | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """获取AI检查结果列表"""
        query = (
            select(ConfirmationAICheck)
            .join(
                ConfirmationList,
                ConfirmationAICheck.confirmation_list_id == ConfirmationList.id,
            )
            .where(
                ConfirmationList.project_id == project_id,
                ConfirmationList.is_deleted == False,  # noqa: E712
                ConfirmationAICheck.is_deleted == False,  # noqa: E712
            )
        )

        if confirmation_id:
            query = query.where(ConfirmationAICheck.confirmation_list_id == confirmation_id)

        if check_type:
            query = query.where(ConfirmationAICheck.check_type == check_type)

        query = query.order_by(ConfirmationAICheck.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        checks = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "confirmation_id": str(c.confirmation_list_id),
                "check_type": c.check_type.value,
                "check_result": c.check_result,
                "risk_level": c.risk_level.value if c.risk_level else None,
                "human_confirmed": c.human_confirmed,
                "confirmed_by": str(c.confirmed_by) if c.confirmed_by else None,
                "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in checks
        ]

    async def confirm_ai_check(
        self,
        check_id: UUID,
        user_id: UUID,
        action: str,  # accept / reject
        notes: str | None = None,
    ) -> dict[str, Any]:
        """确认AI检查结果"""
        result = await self.db.execute(
            select(ConfirmationAICheck).where(
                ConfirmationAICheck.id == check_id,
                ConfirmationAICheck.is_deleted == False,  # noqa: E712
            )
        )
        check = result.scalar_one_or_none()
        if not check:
            raise ValueError(f"AI check not found: {check_id}")

        check.human_confirmed = True
        check.confirmed_by = user_id
        check.confirmed_at = datetime.utcnow()

        if notes:
            # 将确认备注追加到 check_result
            if check.check_result:
                check.check_result["confirmation_notes"] = notes
            else:
                check.check_result = {"confirmation_notes": notes}

        await self.db.commit()
        await self.db.refresh(check)

        return {
            "id": str(check.id),
            "human_confirmed": check.human_confirmed,
            "confirmed_by": str(check.confirmed_by),
            "confirmed_at": check.confirmed_at.isoformat(),
        }

    # -------------------------------------------------------------------------
    # 原有方法（保持向后兼容）
    # -------------------------------------------------------------------------

    async def audit_confirmation(
        self,
        project_id: UUID,
        confirmation_type: str,
        original_text: str,
        response_text: str | None,
        audit_period: str,
        user_id: str | None = None,
    ) -> AIConfirmationAudit:
        """
        审核函证内容（原有方法，保持向后兼容）

        Args:
            project_id: 项目 ID
            confirmation_type: 函证类型
            original_text: 发出函证内容
            response_text: 回函内容
            audit_period: 审计期间
            user_id: 用户 ID

        Returns:
            审核记录
        """
        audit = AIConfirmationAudit(
            project_id=project_id,
            confirmation_type=confirmation_type,
            original_content=original_text,
            response_content=response_text,
            audit_period=audit_period,
            status="pending",
            user_id=user_id,
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(audit)

        try:
            # 构建审核提示词
            prompt = self._build_audit_prompt(
                confirmation_type,
                original_text,
                response_text,
                audit_period,
            )

            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="audit",
            )

            content = response if isinstance(response, str) else ""

            # 解析审核结果
            parsed = self._parse_audit_result(content)

            audit.status = "completed"
            audit.audit_result = parsed

            await self.db.commit()
            await self.db.refresh(audit)

            return audit

        except Exception as e:
            logger.exception(f"Confirmation audit failed")
            audit.status = "failed"
            await self.db.commit()
            raise

    def _build_audit_prompt(
        self,
        confirmation_type: str,
        original_text: str,
        response_text: str | None,
        audit_period: str,
    ) -> str:
        """构建审核提示词"""
        response_section = (
            f"回函内容：\n{response_text}"
            if response_text
            else "（暂无回函内容）"
        )

        return f"""你是一名资深审计师，请审核以下审计函证内容。

函证类型：{confirmation_type}
审计期间：{audit_period}

发出函证内容：
{original_text}

{response_section}

请执行以下审核：
1. 核对发出函证与回函内容是否一致
2. 识别差异类型（金额差异/日期差异/信息缺失/不符）
3. 评估差异的审计重要性
4. 提出后续审计建议

以 JSON 格式返回审核结果：
{{
  "match_score": 85,
  "discrepancy_type": "金额差异",
  "discrepancy_description": "银行回函金额与发出函证金额差异 XXX 元",
  "action": "需进一步追查",
  "risk_level": "低/中/高"
}}"""

    def _parse_audit_result(self, content: str) -> dict[str, Any]:
        """解析审核结果"""
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {
            "description": content[:500],
            "action": "请人工复核",
            "match_score": 0,
        }

    async def get_audit(self, audit_id: UUID) -> AIConfirmationAudit | None:
        """获取审核记录"""
        result = await self.db.execute(
            select(AIConfirmationAudit).where(AIConfirmationAudit.id == audit_id)
        )
        return result.scalar_one_or_none()

    async def list_audits(
        self,
        project_id: UUID,
        confirmation_type: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AIConfirmationAudit]:
        """列出审核记录"""
        query = select(AIConfirmationAudit).where(
            AIConfirmationAudit.project_id == project_id
        )
        if confirmation_type:
            query = query.where(
                AIConfirmationAudit.confirmation_type == confirmation_type
            )
        query = query.order_by(AIConfirmationAudit.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
