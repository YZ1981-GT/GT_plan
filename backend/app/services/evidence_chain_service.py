"""审计证据链服务

管理和追踪审计证据的完整链条，支持证据收集、整理和关联分析。
证据链验证：收入循环、采购循环、费用报销、银行流水深度分析。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIEvidenceChain,
    AIEvidenceItem,
    AIContent,
    AIContentType,
    ConfidenceLevel,
    Contract,
    ContractType,
    DocumentMatch,
    DocumentScan,
    DocumentType,
    EvidenceChain,
    EvidenceChainType,
    ChainMatchStatus,
    RiskLevel,
)
from app.models.audit_platform_models import TbLedger

logger = logging.getLogger(__name__)

# 匹配容差常量
AMOUNT_TOLERANCE = 0.05  # 金额容差 ±5%
DATE_TOLERANCE_DAYS = 7  # 日期容差 ±7天
LARGE_AMOUNT_THRESHOLD = 100000  # 大额交易阈值
ROUND_NUMBER_THRESHOLD = 50000  # 整数金额大额转账阈值
PERIOD_END_DAYS = 5  # 期末集中天数
WORKING_HOURS_START = 8  # 工作时间开始
WORKING_HOURS_END = 20  # 工作时间结束
CIRCULAR_FUND_MIN_AMOUNT = 10000  # 循环资金最小金额


class EvidenceChainService:
    """审计证据链服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_chain(
        self,
        project_id: UUID,
        chain_name: str,
        business_cycle: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AIEvidenceChain:
        """创建证据链"""
        chain = AIEvidenceChain(
            project_id=project_id,
            chain_name=chain_name,
            business_cycle=business_cycle,
            description=description,
            completeness_score=0.0,
            user_id=user_id,
        )
        self.db.add(chain)
        await self.db.commit()
        await self.db.refresh(chain)
        return chain

    async def add_evidence_item(
        self,
        chain_id: UUID,
        evidence_name: str,
        evidence_type: str,
        source_module: str,
        source_id: Optional[str] = None,
        description: Optional[str] = None,
        file_path: Optional[str] = None,
        ocr_text: Optional[str] = None,
        is_key_evidence: bool = False,
        completeness: float = 0.0,
    ) -> AIEvidenceItem:
        """添加证据项"""
        # 更新序号
        result = await self.db.execute(
            select(AIEvidenceItem)
            .where(AIEvidenceItem.chain_id == chain_id)
            .order_by(AIEvidenceItem.item_order.desc())
            .limit(1)
        )
        last_item = result.scalar_one_or_none()
        next_order = (last_item.item_order + 1) if last_item else 1

        item = AIEvidenceItem(
            chain_id=chain_id,
            evidence_name=evidence_name,
            evidence_type=evidence_type,
            source_module=source_module,
            source_id=source_id,
            description=description,
            file_path=file_path,
            ocr_text=ocr_text,
            is_key_evidence=is_key_evidence,
            completeness=completeness,
            item_order=next_order,
        )
        self.db.add(item)

        # 更新证据链完整性评分
        await self._update_chain_score(chain_id)

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def _update_chain_score(self, chain_id: UUID) -> None:
        """更新证据链完整性评分"""
        result = await self.db.execute(
            select(AIEvidenceItem).where(AIEvidenceItem.chain_id == chain_id)
        )
        items = result.scalars().all()

        if not items:
            return

        # 评分公式：基于证据完整性和关键证据覆盖率
        total_score = sum(item.completeness for item in items)
        key_evidence = [i for i in items if i.is_key_evidence]
        key_coverage = len(key_evidence) / max(len(items), 1)

        # 权重：完整性 70%，关键证据覆盖率 30%
        completeness_score = total_score / len(items)
        final_score = completeness_score * 0.7 + key_coverage * 100 * 0.3

        # 更新链记录
        chain_result = await self.db.execute(
            select(AIEvidenceChain).where(AIEvidenceChain.id == chain_id)
        )
        chain = chain_result.scalar_one_or_none()
        if chain:
            chain.completeness_score = min(100.0, round(final_score, 2))

    async def link_evidence(
        self,
        from_item_id: UUID,
        to_item_id: UUID,
        relationship: str,
        description: Optional[str] = None,
    ) -> dict:
        """关联两个证据项（记录到描述中）"""
        # 查找源证据项
        result = await self.db.execute(
            select(AIEvidenceItem).where(AIEvidenceItem.id == from_item_id)
        )
        from_item = result.scalar_one_or_none()
        if not from_item:
            raise ValueError(f"Source evidence item {from_item_id} not found")

        # 追加关联信息到描述
        existing_links = from_item.description or ""
        new_link = f"\n[关联证据]: {to_item_id} ({relationship})"
        if description:
            new_link += f" - {description}"

        from_item.description = existing_links + new_link

        await self.db.commit()

        return {
            "from_item": str(from_item_id),
            "to_item": str(to_item_id),
            "relationship": relationship,
        }

    async def get_chain(self, chain_id: UUID) -> Optional[AIEvidenceChain]:
        """获取证据链"""
        result = await self.db.execute(
            select(AIEvidenceChain).where(AIEvidenceChain.id == chain_id)
        )
        return result.scalar_one_or_none()

    async def get_chain_items(
        self, chain_id: UUID, include_ocr: bool = False
    ) -> list[AIEvidenceItem]:
        """获取证据链中的所有证据项"""
        result = await self.db.execute(
            select(AIEvidenceItem)
            .where(AIEvidenceItem.chain_id == chain_id)
            .order_by(AIEvidenceItem.item_order)
        )
        items = result.scalars().all()

        if not include_ocr:
            for item in items:
                item.ocr_text = None

        return list(items)

    async def update_item_completeness(
        self, item_id: UUID, completeness: float
    ) -> Optional[AIEvidenceItem]:
        """更新证据项完整性"""
        result = await self.db.execute(
            select(AIEvidenceItem).where(AIEvidenceItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None

        item.completeness = min(100.0, max(0.0, completeness))
        await self.db.commit()
        await self.db.refresh(item)

        # 重新计算链评分
        await self._update_chain_score(item.chain_id)
        await self.db.commit()

        return item

    async def analyze_chain(
        self,
        chain_id: UUID,
        ai_service: Any,
    ) -> dict[str, Any]:
        """
        AI 分析证据链的完整性和逻辑关系

        Args:
            chain_id: 证据链 ID
            ai_service: AI 服务实例

        Returns:
            分析结果
        """
        chain = await self.get_chain(chain_id)
        if not chain:
            raise ValueError(f"Evidence chain {chain_id} not found")

        items = await self.get_chain_items(chain_id, include_ocr=True)

        # 构建证据摘要
        evidence_summary = []
        for item in items:
            evidence_summary.append({
                "order": item.item_order,
                "name": item.evidence_name,
                "type": item.evidence_type,
                "source": item.source_module,
                "key": item.is_key_evidence,
                "completeness": item.completeness,
                "description": item.description[:200] if item.description else "",
            })

        prompt = f"""你是一名资深审计师，请分析以下审计证据链的完整性和逻辑关系。

证据链名称：{chain.chain_name}
业务循环：{chain.business_cycle}
描述：{chain.description or '无'}

证据项列表：
{__import__('json').dumps(evidence_summary, ensure_ascii=False, indent=2)}

请执行以下分析：
1. 证据链完整性评估
2. 关键证据是否充分
3. 证据之间的逻辑关系
4. 缺失的证据建议
5. 审计风险点识别

以 JSON 格式返回分析结果：
{{
  "completeness_assessment": "...",
  "key_evidence_adequate": true/false,
  "logical_relationships": [...],
  "missing_evidence": [...],
  "risk_points": [...],
  "recommendations": [...]
}}"""

        try:
            response = await ai_service.chat(
                messages=[{"role": "user", "content": prompt}],
                model="audit",
            )

            content = response.get("content", "")

            # 尝试解析 JSON
            import re
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    analysis = __import__("json").loads(json_match.group())
                    return analysis
                except __import__("json").JSONDecodeError:
                    pass

            return {
                "analysis": content,
                "model": response.get("model"),
            }

        except Exception as e:
            logger.exception(f"Evidence chain analysis failed")
            return {"error": str(e)}

    async def list_chains(
        self,
        project_id: UUID,
        business_cycle: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AIEvidenceChain]:
        """列出项目的证据链"""
        query = select(AIEvidenceChain).where(
            AIEvidenceChain.project_id == project_id
        )
        if business_cycle:
            query = query.where(AIEvidenceChain.business_cycle == business_cycle)
        query = query.order_by(AIEvidenceChain.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize_string(s: str | None) -> str:
        """规范化字符串用于比对"""
        if not s:
            return ""
        return s.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """计算两个字符串的相似度"""
        norm_a = EvidenceChainService._normalize_string(a)
        norm_b = EvidenceChainService._normalize_string(b)
        if not norm_a or not norm_b:
            return 0.0
        return SequenceMatcher(None, norm_a, norm_b).ratio()

    @staticmethod
    def _amount_within_tolerance(amount1: float | None, amount2: float | None, tolerance: float = AMOUNT_TOLERANCE) -> bool:
        """检查两个金额是否在容差范围内"""
        if amount1 is None or amount2 is None:
            return False
        if amount2 == 0:
            return amount1 == 0
        ratio = abs(amount1 - amount2) / abs(amount2)
        return ratio <= tolerance

    @staticmethod
    def _date_within_tolerance(d1: date | datetime | None, d2: date | datetime | None, days: int = DATE_TOLERANCE_DAYS) -> bool:
        """检查两个日期是否在容差天数内"""
        if d1 is None or d2 is None:
            return False
        if hasattr(d1, 'date'):
            d1 = d1.date()
        if hasattr(d2, 'date'):
            d2 = d2.date()
        diff = abs((d1 - d2).days)
        return diff <= days

    @staticmethod
    def _extract_amount_from_doc(doc: DocumentScan) -> dict[str, Any]:
        """从单据提取金额信息"""
        result = {"amount": None, "tax_amount": None, "total_amount": None}
        # 通过 document_scan 关联的 extracted_fields 获取金额
        return result

    # -------------------------------------------------------------------------
    # Task 10.1: 收入循环证据链验证
    # -------------------------------------------------------------------------

    async def verify_revenue_chain(self, project_id: UUID) -> dict[str, Any]:
        """
        收入循环证据链验证：合同 → 出库 → 物流 → 发票 → 凭证 → 回款
        
        匹配规则：
        - 金额容差 ±5%
        - 日期容差 ±7天
        - 交易对手名称相似度匹配
        
        Returns:
            {
                "matched": [...],      # 匹配的证据链
                "missing": [...],       # 缺失的证据
                "inconsistent": [...],  # 不一致的证据
                "total": N
            }
        """
        # 1. 查询收入循环相关单据
        # 合同（销售合同）
        contracts_result = await self.db.execute(
            select(Contract).where(
                and_(
                    Contract.project_id == project_id,
                    Contract.contract_type == ContractType.sales,
                    Contract.is_deleted == False,
                )
            )
        )
        contracts = list(contracts_result.scalars().all())

        # 销售发票
        sales_invoices_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.sales_invoice,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        sales_invoices = list(sales_invoices_result.scalars().all())

        # 出库单/发货单
        outbound_orders_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.outbound_order,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        outbound_orders = list(outbound_orders_result.scalars().all())

        # 物流单
        logistics_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.logistics_order,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        logistics_orders = list(logistics_result.scalars().all())

        # 银行收款单
        bank_receipts_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.bank_receipt,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        bank_receipts = list(bank_receipts_result.scalars().all())

        # 凭证（从序时账获取）
        vouchers_result = await self.db.execute(
            select(TbLedger).where(
                and_(
                    TbLedger.project_id == project_id,
                    TbLedger.is_deleted == False,
                    # 收入类科目 (6开头)
                    TbLedger.account_code.like("6%"),
                )
            )
        )
        vouchers = list(vouchers_result.scalars().all())

        # 2. 构建匹配关系
        matched_chains = []
        missing_chains = []
        inconsistent_chains = []

        # 辅助函数：从合同获取交易对手
        def get_contract_party(contract: Contract) -> str:
            return contract.party_b or ""

        # 辅助函数：从发票提取买方名称（通过摘要或备注）
        def get_invoice_buyer(invoice: DocumentScan) -> str:
            # 从文件名或摘要中提取
            return invoice.file_name or ""

        # 辅助函数：从银行收款获取付款方
        def get_receipt_payer(receipt: DocumentScan) -> str:
            return receipt.file_name or ""

        # 3. 匹配发票与合同
        for invoice in sales_invoices:
            invoice_amount = self._get_doc_amount(invoice)
            invoice_date = self._get_doc_date(invoice)
            invoice_buyer = get_invoice_buyer(invoice)

            # 查找匹配的合同
            matched_contract = None
            for contract in contracts:
                contract_amount = float(contract.contract_amount or 0)
                if self._amount_within_tolerance(invoice_amount, contract_amount):
                    matched_contract = contract
                    break

            # 查找匹配的收款
            matched_receipt = None
            for receipt in bank_receipts:
                receipt_amount = self._get_doc_amount(receipt)
                receipt_date = self._get_doc_date(receipt)
                if (self._amount_within_tolerance(invoice_amount, receipt_amount) and
                    self._date_within_tolerance(invoice_date, receipt_date, 30)):  # 回款允许更长时间
                    matched_receipt = receipt
                    break

            # 构建匹配链
            chain_entry = {
                "invoice_id": str(invoice.id),
                "invoice_no": invoice.file_name,
                "invoice_amount": invoice_amount,
                "invoice_date": str(invoice_date) if invoice_date else None,
                "contract_id": str(matched_contract.id) if matched_contract else None,
                "receipt_id": str(matched_receipt.id) if matched_receipt else None,
            }

            if matched_contract and matched_receipt:
                # 检查一致性
                contract_party = get_contract_party(matched_contract)
                if self._similarity(invoice_buyer, contract_party) < 0.7:
                    chain_entry["status"] = "inconsistent"
                    chain_entry["reason"] = f"买方名称不一致: 发票={invoice_buyer}, 合同={contract_party}"
                    inconsistent_chains.append(chain_entry)
                else:
                    chain_entry["status"] = "matched"
                    matched_chains.append(chain_entry)
            elif matched_contract:
                chain_entry["status"] = "missing"
                chain_entry["reason"] = "无匹配的银行收款记录"
                missing_chains.append(chain_entry)
            else:
                chain_entry["status"] = "inconsistent"
                chain_entry["reason"] = "无匹配的合同记录"
                inconsistent_chains.append(chain_entry)

        # 4. 保存验证结果到 EvidenceChain 表
        for chain_data in matched_chains + missing_chains + inconsistent_chains:
            chain_record = EvidenceChain(
                project_id=project_id,
                chain_type=EvidenceChainType.revenue,
                source_document_id=UUID(chain_data.get("invoice_id", "0" * 32)),
                target_document_id=UUID(chain_data.get("receipt_id", "0" * 32)) if chain_data.get("receipt_id") else None,
                chain_step=1,
                match_status=ChainMatchStatus.matched if chain_data["status"] == "matched"
                           else ChainMatchStatus.missing if chain_data["status"] == "missing"
                           else ChainMatchStatus.mismatched,
                mismatch_description=chain_data.get("reason"),
                risk_level=RiskLevel.high if chain_data["status"] == "inconsistent" else RiskLevel.low,
            )
            self.db.add(chain_record)

        await self.db.commit()

        return {
            "matched": matched_chains,
            "missing": missing_chains,
            "inconsistent": inconsistent_chains,
            "total": len(matched_chains) + len(missing_chains) + len(inconsistent_chains),
        }

    def _get_doc_amount(self, doc: DocumentScan) -> float | None:
        """从单据提取金额"""
        # 尝试从 extracted_fields 中获取 amount
        for field in doc.extracted_fields:
            if field.field_name in ("amount", "total_amount", "tax_amount"):
                try:
                    return float(field.field_value or 0)
                except (ValueError, TypeError):
                    continue
        return None

    def _get_doc_date(self, doc: DocumentScan) -> date | None:
        """从单据提取日期"""
        for field in doc.extracted_fields:
            if field.field_name in ("invoice_date", "transaction_date", "date"):
                val = field.field_value
                if val:
                    try:
                        return datetime.strptime(val[:10], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
        return None

    # -------------------------------------------------------------------------
    # Task 10.2: 采购循环证据链验证
    # -------------------------------------------------------------------------

    async def verify_purchase_chain(self, project_id: UUID) -> dict[str, Any]:
        """
        采购循环证据链验证：合同 → 入库 → 发票 → 凭证 → 付款
        
        检测异常：
        - has_payment_no_grn: 有付款但无入库单
        - quantity_mismatch: 数量不匹配
        - supplier_mismatch: 供应商不一致
        
        Returns:
            {
                "has_payment_no_grn": [...],
                "quantity_mismatch": [...],
                "supplier_mismatch": [...],
                "total_anomalies": N
            }
        """
        # 1. 查询采购循环相关单据
        # 采购合同
        contracts_result = await self.db.execute(
            select(Contract).where(
                and_(
                    Contract.project_id == project_id,
                    Contract.contract_type == ContractType.purchase,
                    Contract.is_deleted == False,
                )
            )
        )
        purchase_contracts = list(contracts_result.scalars().all())

        # 采购入库单 (inbound_order)
        grn_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.inbound_order,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        grns = list(grn_result.scalars().all())

        # 采购发票
        purchase_invoices_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.purchase_invoice,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        purchase_invoices = list(purchase_invoices_result.scalars().all())

        # 银行付款单
        bank_payments_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.bank_receipt,  # 收款单包含付款
                    DocumentScan.is_deleted == False,
                )
            )
        )
        bank_payments = list(bank_payments_result.scalars().all())

        # 2. 检测异常
        has_payment_no_grn = []
        quantity_mismatch = []
        supplier_mismatch = []

        # 2.1 检查付款与入库匹配
        for payment in bank_payments:
            payment_amount = self._get_doc_amount(payment)
            payment_date = self._get_doc_date(payment)
            payment_supplier = payment.file_name or ""

            # 查找匹配的入库单
            matched_grn = None
            for grn in grns:
                grn_amount = self._get_doc_amount(grn)
                grn_date = self._get_doc_date(grn)
                if (self._amount_within_tolerance(payment_amount, grn_amount) and
                    self._date_within_tolerance(payment_date, grn_date, 30)):
                    matched_grn = grn
                    break

            if not matched_grn:
                has_payment_no_grn.append({
                    "payment_id": str(payment.id),
                    "payment_amount": payment_amount,
                    "payment_date": str(payment_date) if payment_date else None,
                    "reason": "有付款记录但无匹配的入库单",
                })

        # 2.2 检查发票与入库数量匹配
        for invoice in purchase_invoices:
            invoice_amount = self._get_doc_amount(invoice)
            invoice_date = self._get_doc_date(invoice)
            invoice_supplier = invoice.file_name or ""

            # 查找匹配的入库单
            matched_grn = None
            for grn in grns:
                grn_amount = self._get_doc_amount(grn)
                grn_date = self._get_doc_date(grn)
                grn_supplier = grn.file_name or ""

                if (self._amount_within_tolerance(invoice_amount, grn_amount) and
                    self._date_within_tolerance(invoice_date, grn_date, 30)):
                    matched_grn = grn

                    # 检查供应商一致性
                    if self._similarity(invoice_supplier, grn_supplier) < 0.7:
                        supplier_mismatch.append({
                            "invoice_id": str(invoice.id),
                            "grn_id": str(grn.id),
                            "invoice_supplier": invoice_supplier,
                            "grn_supplier": grn_supplier,
                            "reason": "发票供应商与入库单供应商不一致",
                        })
                    break

            # 检查数量差异（发票金额与入库金额差异超过容差）
            if matched_grn:
                grn_amount = self._get_doc_amount(matched_grn)
                diff_ratio = abs(invoice_amount - grn_amount) / grn_amount if grn_amount else 0
                if diff_ratio > AMOUNT_TOLERANCE:
                    quantity_mismatch.append({
                        "invoice_id": str(invoice.id),
                        "grn_id": str(matched_grn.id),
                        "invoice_amount": invoice_amount,
                        "grn_amount": grn_amount,
                        "difference": invoice_amount - grn_amount,
                        "reason": f"发票金额与入库金额差异{diff_ratio*100:.1f}%",
                    })

        # 2.3 保存异常到 EvidenceChain 表
        for anomaly in has_payment_no_grn:
            chain_record = EvidenceChain(
                project_id=project_id,
                chain_type=EvidenceChainType.purchase,
                source_document_id=UUID(anomaly.get("payment_id", "0" * 32)),
                chain_step=1,
                match_status=ChainMatchStatus.missing,
                mismatch_description=anomaly["reason"],
                risk_level=RiskLevel.high,
            )
            self.db.add(chain_record)

        for anomaly in quantity_mismatch + supplier_mismatch:
            chain_record = EvidenceChain(
                project_id=project_id,
                chain_type=EvidenceChainType.purchase,
                source_document_id=UUID(anomaly.get("invoice_id", "0" * 32)),
                target_document_id=UUID(anomaly.get("grn_id", "0" * 32)) if anomaly.get("grn_id") else None,
                chain_step=1,
                match_status=ChainMatchStatus.mismatched,
                mismatch_description=anomaly["reason"],
                risk_level=RiskLevel.high,
            )
            self.db.add(chain_record)

        await self.db.commit()

        total_anomalies = len(has_payment_no_grn) + len(quantity_mismatch) + len(supplier_mismatch)

        return {
            "has_payment_no_grn": has_payment_no_grn,
            "quantity_mismatch": quantity_mismatch,
            "supplier_mismatch": supplier_mismatch,
            "total_anomalies": total_anomalies,
        }

    # -------------------------------------------------------------------------
    # Task 10.3: 费用报销证据链验证
    # -------------------------------------------------------------------------

    async def verify_expense_chain(self, project_id: UUID) -> dict[str, Any]:
        """
        费用报销证据链验证：申请 → 发票 → 报销单 → 审批 → 凭证
        
        检测异常：
        - date_mismatch: 日期不匹配
        - location_inconsistency: 地点不一致
        - consecutive_invoice_numbers: 发票连号
        - approval_threshold_bypass: 金额卡审批临界值
        - weekend_large_amount: 周末大额报销
        
        Returns:
            异常列表
        """
        # 1. 查询费用报销相关单据
        # 费用报销单
        expense_reports_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.expense_report,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        expense_reports = list(expense_reports_result.scalars().all())

        # 发票（费用发票）
        expense_invoices_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.purchase_invoice,  # 费用发票用采购发票类型
                    DocumentScan.is_deleted == False,
                )
            )
        )
        expense_invoices = list(expense_invoices_result.scalars().all())

        # 凭证
        vouchers_result = await self.db.execute(
            select(TbLedger).where(
                and_(
                    TbLedger.project_id == project_id,
                    TbLedger.is_deleted == False,
                    TbLedger.account_code.like("6%"),  # 费用类科目
                )
            )
        )
        vouchers = list(vouchers_result.scalars().all())

        # 2. 检测异常
        anomalies = {
            "date_mismatch": [],
            "location_inconsistency": [],
            "consecutive_invoice_numbers": [],
            "approval_threshold_bypass": [],
            "weekend_large_amount": [],
        }

        # 审批临界值（可配置）
        approval_threshold = 5000  # 5000元以上需要高级审批

        # 2.1 日期不匹配检查
        for report in expense_reports:
            report_date = self._get_doc_date(report)
            report_amount = self._get_doc_amount(report)

            if report_date is None:
                continue

            # 查找关联发票
            for invoice in expense_invoices:
                invoice_date = self._get_doc_date(invoice)
                if invoice_date is None:
                    continue

                # 日期差异超过30天视为异常
                if report_date and abs((report_date - invoice_date).days) > 30:
                    anomalies["date_mismatch"].append({
                        "report_id": str(report.id),
                        "invoice_id": str(invoice.id),
                        "report_date": str(report_date),
                        "invoice_date": str(invoice_date),
                        "reason": f"报销单日期与发票日期差异{abs((report_date - invoice_date).days)}天",
                    })

        # 2.2 周末大额报销检测
        for report in expense_reports:
            report_date = self._get_doc_date(report)
            report_amount = self._get_doc_amount(report) or 0

            if report_date is None:
                continue

            # 检查是否为周末（周六=5，周日=6）
            if report_date.weekday() >= 5 and report_amount > approval_threshold:
                anomalies["weekend_large_amount"].append({
                    "report_id": str(report.id),
                    "report_date": str(report_date),
                    "amount": report_amount,
                    "weekday": report_date.strftime("%A"),
                    "reason": f"周末大额报销 {report_amount} 元",
                })

        # 2.3 金额卡审批临界值检测
        for report in expense_reports:
            report_amount = self._get_doc_amount(report) or 0

            # 检查金额是否刚好在临界值附近（如4999、5001等）
            if abs(report_amount - approval_threshold) <= 100:
                anomalies["approval_threshold_bypass"].append({
                    "report_id": str(report.id),
                    "amount": report_amount,
                    "threshold": approval_threshold,
                    "reason": f"金额 {report_amount} 接近审批临界值 {approval_threshold}",
                })

        # 2.4 发票连号检测（简单实现：按文件名排序后检查编号连续性）
        sorted_invoices = sorted(expense_invoices, key=lambda x: x.file_name or "")
        for i in range(len(sorted_invoices) - 1):
            curr_name = sorted_invoices[i].file_name or ""
            next_name = sorted_invoices[i + 1].file_name or ""

            # 提取发票号中的数字部分
            import re
            curr_nums = re.findall(r'\d+', curr_name)
            next_nums = re.findall(r'\d+', next_name)

            if curr_nums and next_nums and curr_nums[-1] != next_nums[-1]:
                try:
                    diff = int(next_nums[-1]) - int(curr_nums[-1])
                    if 1 <= diff <= 5:  # 连续5张以内的发票
                        anomalies["consecutive_invoice_numbers"].append({
                            "invoice_1": str(sorted_invoices[i].id),
                            "invoice_2": str(sorted_invoices[i + 1].id),
                            "invoice_no_1": curr_name,
                            "invoice_no_2": next_name,
                            "reason": f"发票号连续或接近：{curr_nums[-1]} → {next_nums[-1]}",
                        })
                except (ValueError, IndexError):
                    continue

        # 3. 保存异常到 EvidenceChain 表
        for anomaly_type, anomaly_list in anomalies.items():
            for anomaly in anomaly_list:
                chain_record = EvidenceChain(
                    project_id=project_id,
                    chain_type=EvidenceChainType.expense,
                    source_document_id=UUID(anomaly.get("report_id", anomaly.get("invoice_1", "0" * 32))),
                    chain_step=1,
                    match_status=ChainMatchStatus.mismatched,
                    mismatch_description=f"{anomaly_type}: {anomaly['reason']}",
                    risk_level=RiskLevel.medium if anomaly_type == "consecutive_invoice_numbers" else RiskLevel.high,
                )
                self.db.add(chain_record)

        await self.db.commit()

        # 汇总
        total_anomalies = sum(len(v) for v in anomalies.values())

        return {
            **anomalies,
            "total_anomalies": total_anomalies,
        }

    # -------------------------------------------------------------------------
    # Task 10.4: 银行流水深度分析
    # -------------------------------------------------------------------------

    async def analyze_bank_statements(self, project_id: UUID) -> dict[str, Any]:
        """
        银行流水深度分析：
        - large_transactions: 大额异常交易（>100000）
        - circular_fund: 循环资金检测 A→B→C→A
        - related_party_flow: 关联方资金往来
        - period_end_concentrated: 期末集中收付款（>80%在最后5天）
        - after_hours: 非营业时间交易（早8点前/晚8点后）
        - round_number_transfer: 整数金额大额转账（金额%10000==0 且 >50000）
        
        Returns:
            银行流水分析结果
        """
        # 1. 查询银行流水单据
        bank_statements_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.bank_statement,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        bank_statements = list(bank_statements_result.scalars().all())

        # 银行收款单
        bank_receipts_result = await self.db.execute(
            select(DocumentScan).where(
                and_(
                    DocumentScan.project_id == project_id,
                    DocumentScan.document_type == DocumentType.bank_receipt,
                    DocumentScan.is_deleted == False,
                )
            )
        )
        bank_receipts = list(bank_receipts_result.scalars().all())

        all_transactions = bank_statements + bank_receipts

        # 2. 分析结果
        result = {
            "large_transactions": [],
            "circular_fund": [],
            "related_party_flow": [],
            "period_end_concentrated": [],
            "after_hours": [],
            "round_number_transfer": [],
        }

        if not all_transactions:
            return result

        # 2.1 大额异常交易
        for txn in all_transactions:
            amount = self._get_doc_amount(txn)
            if amount and amount > LARGE_AMOUNT_THRESHOLD:
                result["large_transactions"].append({
                    "transaction_id": str(txn.id),
                    "transaction_date": str(self._get_doc_date(txn)) if self._get_doc_date(txn) else None,
                    "amount": amount,
                    "counterparty": txn.file_name,
                    "reason": f"单笔交易金额 {amount} 超过阈值 {LARGE_AMOUNT_THRESHOLD}",
                })

        # 2.2 整数金额大额转账
        for txn in all_transactions:
            amount = self._get_doc_amount(txn)
            if amount and amount > ROUND_NUMBER_THRESHOLD and amount % 10000 == 0:
                result["round_number_transfer"].append({
                    "transaction_id": str(txn.id),
                    "transaction_date": str(self._get_doc_date(txn)) if self._get_doc_date(txn) else None,
                    "amount": amount,
                    "counterparty": txn.file_name,
                    "reason": f"整数金额大额转账 {amount}",
                })

        # 2.3 循环资金检测（简化版：检测三方转账闭环）
        # 构建资金流向图
        fund_flow = defaultdict(list)  # from -> [to1, to2, ...]
        txn_details = {}  # txn_id -> {from, to, amount, date}

        for txn in all_transactions:
            amount = self._get_doc_amount(txn)
            counterparty = txn.file_name or "unknown"
            txn_date = self._get_doc_date(txn)

            # 假设收款方在文件名中
            from_party = "company"
            to_party = counterparty

            if amount and amount > CIRCULAR_FUND_MIN_AMOUNT:
                fund_flow[from_party].append(to_party)
                txn_details[str(txn.id)] = {
                    "from": from_party,
                    "to": to_party,
                    "amount": amount,
                    "date": txn_date,
                }

        # 检测闭环 A -> B -> C -> A
        def find_circular_flow(start: str, visited: set, path: list) -> list | None:
            """DFS 检测闭环"""
            if start in visited and len(path) >= 3:
                # 找到闭环
                idx = path.index(start)
                return path[idx:] + [start]
            if start in visited:
                return None

            for next_party in fund_flow.get(start, []):
                if find_circular_flow(next_party, visited | {start}, path + [next_party]):
                    return path

            return None

        circular_paths = []
        all_parties = set(fund_flow.keys()) | {p for plist in fund_flow.values() for p in plist}
        for party in all_parties:
            if fund_flow.get(party):
                circular = find_circular_flow(party, set(), [])
                if circular and circular not in circular_paths:
                    circular_paths.append(circular)

        for path in circular_paths:
            # 查找路径上的交易
            involved_txns = []
            for i, from_p in enumerate(path[:-1]):
                to_p = path[i + 1]
                for txn_id, details in txn_details.items():
                    if details["from"] == from_p and details["to"] == to_p:
                        involved_txns.append({
                            "transaction_id": txn_id,
                            "from": from_p,
                            "to": to_p,
                            "amount": details["amount"],
                        })

            if involved_txns:
                result["circular_fund"].append({
                    "path": " → ".join(path),
                    "transactions": involved_txns,
                    "reason": f"检测到资金闭环：{' → '.join(path)}",
                })

        # 2.4 期末集中收付款检测
        # 统计每月最后5天的交易占比
        monthly_stats = defaultdict(lambda: {"total_amount": 0, "period_end_amount": 0, "count": 0, "period_end_count": 0})

        for txn in all_transactions:
            amount = self._get_doc_amount(txn) or 0
            txn_date = self._get_doc_date(txn)
            if not txn_date:
                continue

            month_key = txn_date.strftime("%Y-%m")
            last_day = (txn_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

            monthly_stats[month_key]["total_amount"] += amount
            monthly_stats[month_key]["count"] += 1

            # 检查是否在期末5天内
            days_to_month_end = (last_day - txn_date).days
            if 0 <= days_to_month_end <= PERIOD_END_DAYS:
                monthly_stats[month_key]["period_end_amount"] += amount
                monthly_stats[month_key]["period_end_count"] += 1

        for month, stats in monthly_stats.items():
            if stats["total_amount"] > 0:
                concentration_ratio = stats["period_end_amount"] / stats["total_amount"]
                if concentration_ratio > 0.8:  # 超过80%
                    result["period_end_concentrated"].append({
                        "month": month,
                        "total_amount": stats["total_amount"],
                        "period_end_amount": stats["period_end_amount"],
                        "concentration_ratio": round(concentration_ratio * 100, 1),
                        "transaction_count": stats["count"],
                        "period_end_count": stats["period_end_count"],
                        "reason": f"{month} 月期末5天内交易金额占比 {concentration_ratio*100:.1f}%",
                    })

        # 2.5 非营业时间交易（需要从单据提取时间信息，这里简化处理）
        # 实际实现需要从 extracted_fields 中获取 transaction_time
        for txn in all_transactions:
            txn_date = self._get_doc_date(txn)
            if not txn_date:
                continue

            # 检查文件创建时间或提取的时间字段
            if hasattr(txn, 'created_at') and txn.created_at:
                created_time = txn.created_at
                hour = created_time.hour
                if hour < WORKING_HOURS_START or hour >= WORKING_HOURS_END:
                    amount = self._get_doc_amount(txn) or 0
                    if amount > 0:  # 只记录有金额的交易
                        result["after_hours"].append({
                            "transaction_id": str(txn.id),
                            "transaction_date": str(txn_date),
                            "transaction_time": created_time.strftime("%H:%M:%S"),
                            "amount": amount,
                            "reason": f"非营业时间交易: {created_time.strftime('%H:%M:%S')}",
                        })

        # 3. 保存分析结果
        for large_txn in result["large_transactions"]:
            chain_record = EvidenceChain(
                project_id=project_id,
                chain_type=EvidenceChainType.expense,  # 复用
                source_document_id=UUID(large_txn.get("transaction_id", "0" * 32)),
                chain_step=1,
                match_status=ChainMatchStatus.mismatched,
                mismatch_description=f"大额异常交易: {large_txn['reason']}",
                risk_level=RiskLevel.high,
            )
            self.db.add(chain_record)

        await self.db.commit()

        # 统计
        total_anomalies = sum(len(v) for v in result.values())

        return {
            **result,
            "total_anomalies": total_anomalies,
        }

    # -------------------------------------------------------------------------
    # Task 10.5: 生成证据链验证汇总报告
    # -------------------------------------------------------------------------

    async def generate_chain_summary(self, project_id: UUID, chain_type: str) -> dict[str, Any]:
        """
        生成证据链验证汇总报告
        
        Returns:
            {
                "total": N,
                "matched": N,
                "mismatched": N,
                "missing": N,
                "high_risk": N,
            }
        """
        # 1. 查询该项目的证据链记录
        chain_type_enum = EvidenceChainType(chain_type) if chain_type else None

        query = select(EvidenceChain).where(
            and_(
                EvidenceChain.project_id == project_id,
                EvidenceChain.is_deleted == False,
            )
        )

        if chain_type_enum:
            query = query.where(EvidenceChain.chain_type == chain_type_enum)

        result = await self.db.execute(query)
        chains = list(result.scalars().all())

        # 2. 统计
        total = len(chains)
        matched = sum(1 for c in chains if c.match_status == ChainMatchStatus.matched)
        mismatched = sum(1 for c in chains if c.match_status == ChainMatchStatus.mismatched)
        missing = sum(1 for c in chains if c.match_status == ChainMatchStatus.missing)
        high_risk = sum(1 for c in chains if c.risk_level == RiskLevel.high)

        summary = {
            "project_id": str(project_id),
            "chain_type": chain_type,
            "total": total,
            "matched": matched,
            "mismatched": mismatched,
            "missing": missing,
            "high_risk": high_risk,
            "match_rate": round(matched / total * 100, 2) if total > 0 else 0,
        }

        # 3. 如果有高风险项，自动生成 AI 内容风险提示
        if high_risk > 0:
            high_risk_chains = [c for c in chains if c.risk_level == RiskLevel.high]
            risk_alert_text = self._generate_risk_alert_text(chain_type, high_risk_chains)

            ai_content = AIContent(
                project_id=project_id,
                content_type=AIContentType.risk_alert,
                content_text=risk_alert_text,
                data_sources={"evidence_chains": [str(c.id) for c in high_risk_chains]},
                confidence_level=ConfidenceLevel.high,
                confirmation_status="pending",
            )
            self.db.add(ai_content)
            await self.db.commit()

            summary["ai_content_id"] = str(ai_content.id)

        return summary

    def _generate_risk_alert_text(self, chain_type: str, high_risk_chains: list) -> str:
        """生成风险提示文本"""
        chain_type_names = {
            "revenue": "收入循环",
            "purchase": "采购循环",
            "expense": "费用报销",
        }
        type_name = chain_type_names.get(chain_type, chain_type)

        alert_text = f"""## 证据链验证风险提示

### {type_name}证据链验证发现 {len(high_risk_chains)} 项高风险异常：

"""

        for chain in high_risk_chains[:10]:  # 最多显示10条
            alert_text += f"- **异常类型**: {chain.match_status.value}\n"
            if chain.mismatch_description:
                alert_text += f"  - 描述: {chain.mismatch_description}\n"
            alert_text += "\n"

        if len(high_risk_chains) > 10:
            alert_text += f"\n... 还有 {len(high_risk_chains) - 10} 项异常未显示。\n"

        alert_text += "\n### 建议措施\n"
        alert_text += "1. 复核上述异常证据链\n"
        alert_text += "2. 与相关方确认不一致原因\n"
        alert_text += "3. 必要时补充审计程序\n"
        alert_text += "4. 在底稿中记录异常情况\n"

        return alert_text
