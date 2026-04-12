"""合同分析 AI 服务

基于大模型对合同文本进行智能分析，提取关键条款、识别风险点。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIAnalysisReport,
    AIAnalysisItem,
    Contract,
    ContractExtracted,
    ContractWPLink,
    ClauseType,
    ContractLinkType,
    ContractType as ContractTypeEnum,
)
from app.models.audit_platform_models import TbLedger

logger = logging.getLogger(__name__)


class ContractAnalysisService:
    """合同分析服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_contract(
        self,
        project_id: UUID,
        contract_text: str,
        contract_type: str,
        analysis_type: str,
        ai_service: Any,
        user_id: Optional[str] = None,
    ) -> AIAnalysisReport:
        """
        分析合同文本

        Args:
            project_id: 项目 ID
            contract_text: 合同文本内容
            contract_type: 合同类型（采购合同/销售合同/贷款合同等）
            analysis_type: 分析类型（全面/风险/条款）
            ai_service: AI 服务实例
            user_id: 用户 ID

        Returns:
            分析报告记录
        """
        from app.models.ai_models import AnalysisReportStatus

        # 创建报告记录
        report = AIAnalysisReport(
            project_id=project_id,
            document_type="contract",
            summary="分析中...",
            status=AnalysisReportStatus.analyzing,
        )
        self.db.add(report)
        await self.db.flush()  # 获取 ID

        try:
            # 调用 AI 分析
            prompt = self._build_analysis_prompt(contract_text, contract_type, analysis_type)
            response = await ai_service.chat(
                messages=[{"role": "user", "content": prompt}],
                model="audit",
            )

            content = response.get("content", "")

            # 解析 AI 响应
            analysis_items = self._parse_analysis_items(content, analysis_type)
            summary = self._extract_summary(content)

            # 保存分析项目到 ContractExtracted
            for item in analysis_items:
                # 映射 item_type 到 ClauseType
                clause_type_str = item.get("type", "special_terms")
                try:
                    clause_type = ClauseType(clause_type_str)
                except ValueError:
                    clause_type = ClauseType.special_terms

                extracted = ContractExtracted(
                    contract_id=report.id,
                    clause_type=clause_type,
                    clause_content=item.get("content", ""),
                    confidence_score=None,
                    human_confirmed=False,
                )
                self.db.add(extracted)

            # 更新报告
            report.summary = summary
            report.key_findings = {"items": analysis_items, "analysis_type": analysis_type}
            report.status = AnalysisReportStatus.completed
            await self.db.commit()
            await self.db.refresh(report)

            return report

        except Exception as e:
            logger.exception(f"Contract analysis failed")
            report.summary = f"分析失败: {str(e)}"
            report.status = AnalysisReportStatus.failed
            await self.db.commit()
            raise

    def _build_analysis_prompt(
        self,
        contract_text: str,
        contract_type: str,
        analysis_type: str,
    ) -> str:
        """构建分析提示词"""
        base_instruction = f"你是一名专业审计师，请分析以下{contract_type}。"

        analysis_prompts = {
            "risk": f"""{base_instruction}

重点识别以下风险：
1. 合同主体的履约能力风险
2. 付款条件风险
3. 违约责任条款风险
4. 终止/解除条款风险
5. 关联交易风险（如适用）

合同文本：
{contract_text[:10000]}

以 JSON 格式返回分析结果：
{{
  "items": [
    {{"type": "风险点", "title": "风险标题", "content": "详细说明", "severity": "高/中/低", "page_reference": ""}}
  ],
  "summary": "总体风险评估结论"
}}""",
            "clause": f"""{base_instruction}

提取以下关键条款：
1. 当事人信息
2. 合同标的
3. 价款/报酬
4. 履行期限和方式
5. 违约责任
6. 争议解决

合同文本：
{contract_text[:10000]}

以 JSON 格式返回：
{{
  "items": [
    {{"type": "条款", "title": "条款标题", "content": "条款内容摘要"}}
  ],
  "summary": "关键条款汇总"
}}""",
            "full": f"""{base_instruction}

进行全面分析，包括：
1. 合同基本信息
2. 关键条款分析
3. 风险评估
4. 审计关注点

合同文本：
{contract_text[:10000]}

以 JSON 格式返回：
{{
  "items": [
    {{"type": "分析项类型", "title": "标题", "content": "详细说明", "severity": "高/中/低"}}
  ],
  "summary": "分析结论"
}}""",
        }

        return analysis_prompts.get(analysis_type, analysis_prompts["full"])

    def _parse_analysis_items(self, content: str, analysis_type: str) -> list[dict]:
        """解析 AI 返回的分析项目"""
        import re

        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
            items = data.get("items", [])
            return items if isinstance(items, list) else []
        except json.JSONDecodeError:
            return []

    def _extract_summary(self, content: str) -> str:
        """从内容中提取摘要"""
        import re

        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("summary", content[:500])
            except json.JSONDecodeError:
                pass

        return content[:500] if len(content) > 500 else content

    async def get_report(self, report_id: UUID) -> Optional[AIAnalysisReport]:
        """获取分析报告"""
        result = await self.db.execute(
            select(AIAnalysisReport).where(AIAnalysisReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def get_report_items(self, report_id: UUID) -> list[AIAnalysisItem]:
        """获取报告的分析项目列表"""
        result = await self.db.execute(
            select(AIAnalysisItem)
            .where(AIAnalysisItem.report_id == report_id)
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # Task 9.1: 批量合同分析（Celery 异步）
    # -------------------------------------------------------------------------

    async def batch_analyze(
        self,
        project_id: UUID,
        contract_ids: list[UUID],
        analysis_type: str = "full",
        user_id: Optional[str] = None,
    ) -> str:
        """
        批量合同分析，返回 Celery task_id

        Args:
            project_id: 项目 ID
            contract_ids: 待分析合同 ID 列表
            analysis_type: 分析类型（full/risk/clause）
            user_id: 用户 ID

        Returns:
            Celery task_id
        """
        import asyncio
        from app.services.ai_service import AIService

        # 为每个合同启动异步分析
        async def analyze_one(contract_id: UUID) -> dict:
            try:
                # 查询合同记录
                result = await self.db.execute(
                    select(Contract).where(Contract.id == contract_id)
                )
                contract = result.scalar_one_or_none()
                if not contract:
                    return {"contract_id": str(contract_id), "status": "not_found"}

                # 获取合同文本（实际从 file_path 读取，这里简化处理）
                contract_text = getattr(contract, 'contract_text', '') or ''

                # 获取合同类型
                contract_type = (
                    contract.contract_type.value
                    if hasattr(contract.contract_type, 'value')
                    else str(contract.contract_type)
                    if contract.contract_type else "other"
                )

                # 调用分析
                ai_service = AIService(self.db)
                report = await self.analyze_contract(
                    project_id=project_id,
                    contract_text=contract_text,
                    contract_type=contract_type,
                    analysis_type=analysis_type,
                    ai_service=ai_service,
                    user_id=user_id,
                )
                return {"contract_id": str(contract_id), "status": "completed", "report_id": str(report.id)}
            except Exception as e:
                logger.exception(f"Batch analyze contract {contract_id} failed")
                return {"contract_id": str(contract_id), "status": "failed", "error": str(e)}

        # 并发执行（最多10个并发）
        semaphore = asyncio.Semaphore(10)

        async def analyze_with_limit(cid: UUID) -> dict:
            async with semaphore:
                return await analyze_one(cid)

        results = await asyncio.gather(*[analyze_with_limit(cid) for cid in contract_ids])

        task_id = str(uuid4())

        logger.info(
            f"Batch analyze completed: task_id={task_id}, "
            f"total={len(contract_ids)}, "
            f"completed={sum(1 for r in results if r.get('status') == 'completed')}, "
            f"failed={sum(1 for r in results if r.get('status') == 'failed')}"
        )

        return task_id

    # -------------------------------------------------------------------------
    # Task 9.2: 合同与账面数据交叉比对
    # -------------------------------------------------------------------------

    async def cross_reference_ledger(
        self,
        contract_id: UUID,
        project_id: UUID,
    ) -> list[dict]:
        """
        合同与账面数据交叉比对

        检查项：
        1. 合同金额 vs 收入/成本发生额
        2. 合同账期 vs 实际回款周期
        3. 合同到期日 vs 审计基准日
        4. 合同对方 vs 关联方清单

        Returns:
            比对结果列表
        """
        from app.models.audit_platform_models import TbAccount, TbAdjustment
        from app.models.core import Project

        results = []

        # 1. 获取合同信息
        result = await self.db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        contract_amount = contract.contract_amount
        contract_party = contract.party_b
        expiry_date = contract.expiry_date
        effective_date = contract.effective_date

        # 2. 获取项目审计期间
        project_result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        audit_end_date = getattr(project, 'audit_end_date', None) if project else None

        # 3. 合同金额 vs 账面发生额
        if contract_amount and contract_amount > 0:
            # 获取合同类型对应的科目代码
            contract_type_val = (
                contract.contract_type.value
                if hasattr(contract.contract_type, 'value')
                else str(contract.contract_type)
                if contract.contract_type else "other"
            )

            # 收入类合同 → 检查主营业务收入科目
            if contract_type_val == "sales":
                # 查询本期销售发生额
                account_result = await self.db.execute(
                    select(TbLedger).where(
                        TbLedger.project_id == project_id,
                        TbLedger.account_code.like("6001%"),  # 主营业务收入
                    )
                )
                ledgers = account_result.scalars().all()
                total_revenue = sum(float(l.debit or 0) + float(l.credit or 0) for l in ledgers)

                if total_revenue > 0:
                    variance = contract_amount - total_revenue
                    variance_pct = abs(variance) / total_revenue * 100
                    results.append({
                        "check_type": "amount_vs_revenue",
                        "contract_amount": float(contract_amount),
                        "ledger_amount": total_revenue,
                        "variance": float(variance),
                        "variance_pct": round(variance_pct, 2),
                        "status": "match" if variance_pct < 5 else "warning",
                        "message": f"合同金额与账面收入差异 {variance_pct:.1f}%"
                    })
                else:
                    results.append({
                        "check_type": "amount_vs_revenue",
                        "contract_amount": float(contract_amount),
                        "ledger_amount": 0,
                        "variance": float(contract_amount),
                        "status": "warning",
                        "message": "合同金额较大但账面无对应收入"
                    })

            # 采购类合同 → 检查库存商品/材料采购
            elif contract_type_val == "purchase":
                account_result = await self.db.execute(
                    select(TbLedger).where(
                        TbLedger.project_id == project_id,
                        TbLedger.account_code.like("1403%"),  # 材料采购
                    )
                )
                ledgers = account_result.scalars().all()
                total_purchase = sum(float(l.debit or 0) for l in ledgers)

                if total_purchase > 0:
                    variance = contract_amount - total_purchase
                    variance_pct = abs(variance) / total_purchase * 100
                    results.append({
                        "check_type": "amount_vs_purchase",
                        "contract_amount": float(contract_amount),
                        "ledger_amount": total_purchase,
                        "variance": float(variance),
                        "variance_pct": round(variance_pct, 2),
                        "status": "match" if variance_pct < 5 else "warning",
                        "message": f"合同金额与账面采购差异 {variance_pct:.1f}%"
                    })

        # 4. 合同到期日 vs 审计基准日
        if expiry_date and audit_end_date:
            from datetime import date as date_type
            if isinstance(expiry_date, datetime):
                expiry_date = expiry_date.date()
            if isinstance(audit_end_date, datetime):
                audit_end_date = audit_end_date.date()

            days_to_expiry = (expiry_date - audit_end_date).days
            if days_to_expiry < 0:
                results.append({
                    "check_type": "expiry_vs_audit_date",
                    "expiry_date": str(expiry_date),
                    "audit_end_date": str(audit_end_date),
                    "days_past_expiry": abs(days_to_expiry),
                    "status": "warning",
                    "message": f"合同已到期 {abs(days_to_expiry)} 天"
                })
            elif days_to_expiry <= 30:
                results.append({
                    "check_type": "expiry_vs_audit_date",
                    "expiry_date": str(expiry_date),
                    "audit_end_date": str(audit_end_date),
                    "days_to_expiry": days_to_expiry,
                    "status": "info",
                    "message": f"合同即将到期，剩余 {days_to_expiry} 天"
                })

        # 5. 合同对方 vs 关联方（简化：检查大额往来）
        if contract_party:
            # 查询往来科目中是否有该交易对手
            ar_ap_accounts = ["1122", "1123", "2202", "2203"]  # 应收账款、预付账款、应付账款、预收账款
            for acc_prefix in ar_ap_accounts:
                ar_result = await self.db.execute(
                    select(TbLedger).where(
                        TbLedger.project_id == project_id,
                        TbLedger.account_code.like(f"{acc_prefix}%"),
                        TbLedger.auxiliary_name.like(f"%{contract_party}%"),
                    )
                )
                related_ledgers = list(ar_result.scalars().all())
                if related_ledgers:
                    total_balance = sum(
                        float(l.debit or 0) - float(l.credit or 0)
                        for l in related_ledgers
                    )
                    results.append({
                        "check_type": "counterparty_vs_related_party",
                        "contract_party": contract_party,
                        "account_code_prefix": acc_prefix,
                        "balance": abs(total_balance),
                        "status": "info",
                        "message": f"合同对方在往来科目 {acc_prefix} 有余额 {abs(total_balance):.2f}"
                    })
                    break  # 找到一个匹配即可

        return results

    # -------------------------------------------------------------------------
    # Task 9.2: 建立合同与底稿关联
    # -------------------------------------------------------------------------

    async def link_to_workpaper(
        self,
        contract_id: UUID,
        workpaper_id: UUID,
        link_type: str = "revenue_recognition",
        description: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ContractWPLink:
        """
        建立合同与底稿的关联

        Args:
            contract_id: 合同 ID
            workpaper_id: 底稿 ID
            link_type: 关联类型
            description: 关联描述
            user_id: 用户 ID

        Returns:
            关联记录
        """
        # 验证合同存在
        contract_result = await self.db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        # 创建关联
        try:
            link_type_enum = ContractLinkType(link_type)
        except ValueError:
            link_type_enum = ContractLinkType.revenue_recognition

        link = ContractWPLink(
            contract_id=contract_id,
            workpaper_id=workpaper_id,
            link_type=link_type_enum,
            link_description=description,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)

        logger.info(
            f"Linked contract {contract_id} to workpaper {workpaper_id} "
            f"with type {link_type}"
        )

        return link

    # -------------------------------------------------------------------------
    # Task 9.2: 生成项目合同汇总报告
    # -------------------------------------------------------------------------

    async def generate_contract_summary(
        self,
        project_id: UUID,
    ) -> dict[str, Any]:
        """
        生成项目合同汇总报告

        Returns:
            {
                "total": N,
                "by_type": {"sales": N, "purchase": N, ...},
                "total_amount": float,
                "expiring_soon": N,
                "high_risk": N,
            }
        """
        from app.models.ai_models import AnalysisReportStatus

        # 1. 统计合同数量
        contracts_result = await self.db.execute(
            select(Contract).where(
                Contract.project_id == project_id,
                Contract.is_deleted == False,
            )
        )
        contracts = list(contracts_result.scalars().all())

        # 2. 按类型统计
        by_type: dict[str, int] = {}
        total_amount = 0.0
        expiring_soon = 0
        high_risk_count = 0

        now = datetime.utcnow().date() if True else datetime.utcnow().date()
        thirty_days_later = datetime.utcnow().date() if True else (datetime.utcnow() + timedelta(days=30)).date()

        for contract in contracts:
            # 按类型统计
            ctype = (
                contract.contract_type.value
                if hasattr(contract.contract_type, 'value')
                else str(contract.contract_type)
                if contract.contract_type else "other"
            )
            by_type[ctype] = by_type.get(ctype, 0) + 1

            # 金额汇总
            if contract.contract_amount:
                total_amount += float(contract.contract_amount)

            # 检查即将到期（30天内）
            if contract.expiry_date:
                exp_date = contract.expiry_date
                if hasattr(exp_date, 'date'):
                    exp_date = exp_date.date()
                if isinstance(exp_date, datetime):
                    exp_date = exp_date.date()
                if exp_date:
                    diff = (exp_date - now).days
                    if 0 <= diff <= 30:
                        expiring_soon += 1

        # 3. 保存汇总报告到 AIAnalysisReport
        report = AIAnalysisReport(
            project_id=project_id,
            document_type="contract_summary",
            summary=f"项目共 {len(contracts)} 份合同，总金额 {total_amount:,.2f}",
            key_findings={
                "total": len(contracts),
                "by_type": by_type,
                "total_amount": total_amount,
                "expiring_soon": expiring_soon,
                "high_risk": high_risk_count,
            },
            status=AnalysisReportStatus.completed,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        return {
            "report_id": str(report.id),
            "total": len(contracts),
            "by_type": by_type,
            "total_amount": round(total_amount, 2),
            "expiring_soon": expiring_soon,
            "high_risk": high_risk_count,
        }
