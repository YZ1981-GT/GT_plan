"""AI-Driven Risk Assessment Service — 财务报表整体风险评估（AI驱动）

提供：
- assess_financial_risk: 财务报表整体风险评估（AI驱动）
- identify_material_items: 识别重大科目和重要事项
- suggest_audit_procedures: 根据风险评估结果建议审计程序
- auto_update_assessment: 根据新发现自动更新风险评估

对接：
- TrialBalance: 试算表数据查询
- Materiality: 重要性水平
- AuditFinding: 审计发现
- AuditProcedure: 审计程序
- AIService: AI能力抽象层
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, and_, func, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountCategory,
    Materiality,
    TrialBalance,
)
from app.models.collaboration_models import (
    AuditFinding,
    AuditProcedure,
    ProcedureType,
    RiskAssessment,
    RiskLevel,
    SeverityLevel,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 风险类型 → 审计程序映射表
# ---------------------------------------------------------------------------
RISK_TO_PROCEDURE_MAPPING: dict[str, list[dict]] = {
    "revenue_recognition": [
        {
            "procedure_code": "SP-REV-001",
            "procedure_name": "营业收入截止测试",
            "procedure_type": "substantive",
            "description": "测试12月31日前后5天营业收入记录的正确截止日期，抽样检查销售出库单、发票、记账凭证日期是否一致",
        },
        {
            "procedure_code": "SP-REV-002",
            "procedure_name": "销售退回截止测试",
            "procedure_type": "substantive",
            "description": "检查期后销售退回及折让，确认是否存在跨期情况",
        },
        {
            "procedure_code": "SP-REV-003",
            "procedure_name": "销售收入的函证确认",
            "procedure_type": "substantive",
            "description": "对大额客户发函确认全年销售金额及期末应收账款余额",
        },
        {
            "procedure_code": "RA-REV-001",
            "procedure_name": "收入变动分析性复核",
            "procedure_type": "risk_assessment",
            "description": "分析本年收入与上年及行业平均水平的变动情况，识别异常波动",
        },
    ],
    "account_receivable": [
        {
            "procedure_code": "SP-AR-001",
            "procedure_name": "应收账款账龄分析",
            "procedure_type": "substantive",
            "description": "取得或编制应收账款账龄分析表，复核账龄划分的准确性",
        },
        {
            "procedure_code": "SP-AR-002",
            "procedure_name": "应收账款函证",
            "procedure_type": "substantive",
            "description": "对期末大额应收账款余额发函确认，特别关注长期挂账款项",
        },
        {
            "procedure_code": "SP-AR-003",
            "procedure_name": "期后回款检查",
            "procedure_type": "substantive",
            "description": "检查资产负债表日后应收账款回款情况，评估可回收性",
        },
        {
            "procedure_code": "CT-AR-001",
            "procedure_name": "赊销审批控制测试",
            "procedure_type": "control_test",
            "description": "测试赊销审批流程是否按规定执行，检查批准权限",
        },
    ],
    "inventory": [
        {
            "procedure_code": "SP-INV-001",
            "procedure_name": "存货监盘",
            "procedure_type": "substantive",
            "description": "对原材料、半成品、产成品实施监盘程序，观察存货状况",
        },
        {
            "procedure_code": "SP-INV-002",
            "procedure_name": "存货成本计价测试",
            "procedure_type": "substantive",
            "description": "测试存货发出计价方法是否一贯，确认成本计算准确性",
        },
        {
            "procedure_code": "SP-INV-003",
            "procedure_name": "存货跌价准备评估",
            "procedure_type": "substantive",
            "description": "复核存货可变现净值，评估跌价准备计提是否充分",
        },
        {
            "procedure_code": "RA-INV-001",
            "procedure_name": "存货周转分析",
            "procedure_type": "risk_assessment",
            "description": "分析存货周转天数变化，识别积压或短缺风险",
        },
    ],
    "fixed_assets": [
        {
            "procedure_code": "SP-FA-001",
            "procedure_name": "固定资产实地盘点",
            "procedure_type": "substantive",
            "description": "对固定资产实施监盘程序，确认资产存在性及状况",
        },
        {
            "procedure_code": "SP-FA-002",
            "procedure_name": "累计折旧复核",
            "procedure_type": "substantive",
            "description": "复核折旧计算的正确性，验证折旧年限是否符合会计政策",
        },
        {
            "procedure_code": "SP-FA-003",
            "procedure_name": "资本化利息测算",
            "procedure_type": "substantive",
            "description": "测算应予资本化的借款利息金额，与账面记录核对",
        },
        {
            "procedure_code": "CT-FA-001",
            "procedure_name": "固定资产购置审批控制测试",
            "procedure_type": "control_test",
            "description": "测试固定资产购置授权审批流程",
        },
    ],
    "related_party": [
        {
            "procedure_code": "SP-RP-001",
            "procedure_name": "关联方交易识别",
            "procedure_type": "risk_assessment",
            "description": "获取管理层声明书，询问并检查是否存在未披露的关联方交易",
        },
        {
            "procedure_code": "SP-RP-002",
            "procedure_name": "关联方交易测试",
            "procedure_type": "substantive",
            "description": "检查关联交易定价公允性，与非关联方交易对比分析",
        },
        {
            "procedure_code": "SP-RP-003",
            "procedure_name": "关联方往来函证",
            "procedure_type": "substantive",
            "description": "对关联方往来余额发函确认，特别关注非经营性往来",
        },
    ],
    "tax": [
        {
            "procedure_code": "SP-TAX-001",
            "procedure_name": "税务申报复核",
            "procedure_type": "substantive",
            "description": "复核各税种纳税申报表的准确性，核对税务局的完税证明",
        },
        {
            "procedure_code": "SP-TAX-002",
            "procedure_name": "所得税费用测算",
            "procedure_type": "substantive",
            "description": "测算当期所得税费用、递延所得税资产/负债变动，核对账面记录",
        },
        {
            "procedure_code": "SP-TAX-003",
            "procedure_name": "税收优惠适用性复核",
            "procedure_type": "substantive",
            "description": "复核高新技术企业等税收优惠政策的适用条件是否持续满足",
        },
    ],
    "commitments": [
        {
            "procedure_code": "SP-COM-001",
            "procedure_name": "或有事项函证",
            "procedure_type": "substantive",
            "description": "向律师函证未决诉讼、仲裁情况，评估预计负债充分性",
        },
        {
            "procedure_code": "SP-COM-002",
            "procedure_name": "担保及背书检查",
            "procedure_type": "substantive",
            "description": "检查对外担保及票据背书情况，获取管理层声明书确认完整性",
        },
    ],
    "going_concern": [
        {
            "procedure_code": "RA-GC-001",
            "procedure_name": "持续经营评估分析",
            "procedure_type": "risk_assessment",
            "description": "分析公司财务状况恶化指标：连续亏损、现金流紧张、到期债务无法展期等",
        },
        {
            "procedure_code": "SP-GC-001",
            "procedure_name": "借款合同检查",
            "procedure_type": "substantive",
            "description": "检查借款合同条款，评估银行是否可能抽贷，是否存在交叉违约条款",
        },
        {
            "procedure_code": "SP-GC-002",
            "procedure_name": "改善措施可行性评估",
            "procedure_type": "substantive",
            "description": "评估管理层改善计划的可行性，包括资产处置、再融资计划等",
        },
    ],
    "general": [
        {
            "procedure_code": "RA-GEN-001",
            "procedure_name": "会计政策变更检查",
            "procedure_type": "risk_assessment",
            "description": "检查本期是否存在会计政策或会计估计变更，是否按规定披露",
        },
        {
            "procedure_code": "SP-GEN-001",
            "procedure_name": "报表项目截止测试",
            "procedure_type": "substantive",
            "description": "对重要报表项目进行截止测试，确认无跨期错误",
        },
        {
            "procedure_code": "SP-GEN-002",
            "procedure_name": "报表项目勾稽关系核对",
            "procedure_type": "substantive",
            "description": "核对报表间及报表内各项目之间的勾稽关系",
        },
    ],
}


# ---------------------------------------------------------------------------
# RiskAssessmentService 类
# ---------------------------------------------------------------------------


class RiskAssessmentService:
    """AI驱动的财务报表整体风险评估服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # 12.1 assess_financial_risk: 财务报表整体风险评估（AI驱动）
    # -------------------------------------------------------------------------

    async def assess_financial_risk(self, project_id: UUID) -> dict:
        """
        财务报表整体风险评估（AI驱动）

        流程：
        1. 查询试算表数据，计算关键财务指标
        2. 获取重要性水平
        3. 汇总审计发现情况
        4. 调用AI服务生成风险评估报告
        5. 返回风险等级、关键风险领域、置信度评分

        Returns:
            {
                "risk_level": "high" | "medium" | "low",
                "confidence_score": float,  # 0.0-1.0
                "key_risk_areas": [
                    {
                        "area": str,           # 风险领域名称
                        "risk_type": str,      # 风险类型
                        "risk_level": str,      # high/medium/low
                        "description": str,     # 风险描述
                        "affected_accounts": [str],  # 涉及科目
                        "suggested_response": str,   # 建议应对
                    }
                ],
                "risk_indicators": {
                    "current_ratio": float,
                    "debt_to_equity": float,
                    "profit_margin": float,
                    "revenue_growth": float,
                    "inventory_turnover": float,
                },
                "ai_assessment_text": str,  # AI生成的完整评估文字
                "material_findings_count": int,
                "overall_materiality": Decimal,
                "performance_materiality": Decimal,
            }
        """
        # Step 1: 查询试算表数据
        trial_balance_data = await self._get_trial_balance_data(project_id)

        # Step 2: 计算关键财务指标
        risk_indicators = self._calculate_risk_indicators(trial_balance_data)

        # Step 3: 获取重要性水平
        materiality = await self._get_materiality(project_id)

        # Step 4: 汇总审计发现情况
        findings_summary = await self._get_findings_summary(project_id)

        # Step 5: 识别关键风险领域
        key_risk_areas = self._identify_key_risk_areas(
            trial_balance_data,
            materiality,
            findings_summary,
        )

        # Step 6: 确定整体风险等级
        risk_level = self._determine_overall_risk_level(
            key_risk_areas,
            findings_summary,
            risk_indicators,
        )

        # Step 7: 调用AI服务生成评估文字
        ai_assessment_text = await self._generate_ai_assessment(
            project_id,
            trial_balance_data,
            risk_indicators,
            key_risk_areas,
            risk_level,
        )

        # Step 8: 计算置信度评分
        confidence_score = self._calculate_confidence_score(
            trial_balance_data,
            materiality,
        )

        return {
            "risk_level": risk_level,
            "confidence_score": confidence_score,
            "key_risk_areas": key_risk_areas,
            "risk_indicators": risk_indicators,
            "ai_assessment_text": ai_assessment_text,
            "material_findings_count": findings_summary.get("total_count", 0),
            "overall_materiality": (
                materiality.overall_materiality if materiality else Decimal("0")
            ),
            "performance_materiality": (
                materiality.performance_materiality if materiality else Decimal("0")
            ),
        }

    # -------------------------------------------------------------------------
    # 12.2 identify_material_items: 识别重大科目和重要事项
    # -------------------------------------------------------------------------

    async def identify_material_items(self, project_id: UUID) -> list[dict]:
        """
        识别重大科目和重要事项

        重大科目判断标准（满足任一即视为重大）：
        - 金额 > 重要性水平阈值（整体重要性或实际执行重要性）
        - 金额占总资产/总收入的比例 > 5%
        - 涉及复杂会计判断（资产减值、公允价值等）
        - 存在较高审计发现率的历史科目

        Returns:
            [
                {
                    "account_code": str,
                    "account_name": str,
                    "account_category": str,
                    "amount": Decimal,
                    "ratio_to_total": float,       # 占汇总金额的比例
                    "materiality_threshold": Decimal,
                    "is_material": bool,
                    "materiality_basis": str,      # "exceeds_threshold" | "high_ratio" | "complex_accounting"
                    "risk_indicators": {
                        "complex_judgment": bool,
                        "prior_findings": bool,
                        "related_party": bool,
                        "estimate_involved": bool,
                    },
                    "suggested_procedures": [str],  # 建议审计程序代码列表
                }
            ]
        """
        # Step 1: 获取重要性水平
        materiality = await self._get_materiality(project_id)
        if not materiality:
            # 默认使用0作为阈值（将基于比例判断）
            threshold = Decimal("0")
        else:
            threshold = materiality.performance_materiality

        # Step 2: 获取试算表数据
        trial_balance_data = await self._get_trial_balance_data(project_id)

        # Step 3: 计算汇总金额（用于计算比例）
        total_assets = sum(
            item["closing_balance"]
            for item in trial_balance_data
            if item.get("account_category") == "asset" and item.get("closing_balance")
        )
        total_revenue = sum(
            item["closing_balance"]
            for item in trial_balance_data
            if item.get("account_category") == "revenue" and item.get("closing_balance")
        )
        # 使用资产总额作为分母
        denominator = total_assets if total_assets > 0 else Decimal("1")

        # Step 4: 获取审计发现涉及科目
        affected_accounts = await self._get_findings_affected_accounts(project_id)

        # Step 5: 识别重大科目
        material_items = []
        for item in trial_balance_data:
            amount = item.get("closing_balance", Decimal("0"))
            if amount is None:
                amount = Decimal("0")

            # 计算占比
            ratio = float(amount / denominator) if denominator else 0.0

            # 判断是否重大
            is_material = False
            materiality_basis = None

            if threshold > 0 and abs(amount) > threshold:
                is_material = True
                materiality_basis = "exceeds_threshold"
            elif ratio > 0.05:  # 占比超过5%
                is_material = True
                materiality_basis = "high_ratio"

            # 复杂会计判断科目（硬编码识别逻辑）
            complex_accounts = [
                "固定资产", "无形资产", "商誉", "投资性房地产",
                "长期股权投资", "交易性金融资产", "应付债券",
                "资产减值准备", "公允价值变动", "递延所得税",
            ]
            if any(ca in item.get("account_name", "") for ca in complex_accounts):
                if not is_material:
                    is_material = True
                    materiality_basis = "complex_accounting"

            if is_material:
                # 确定风险指标
                risk_indicators = {
                    "complex_judgment": any(
                        ca in item.get("account_name", "")
                        for ca in complex_accounts
                    ),
                    "prior_findings": item.get("account_code") in affected_accounts,
                    "related_party": "关联方" in item.get("account_name", ""),
                    "estimate_involved": any(
                        kw in item.get("account_name", "")
                        for kw in ["准备", "预计", "摊销", "减值"]
                    ),
                }

                # 建议审计程序
                suggested_procedures = self._suggest_procedures_for_account(
                    item.get("account_name", ""),
                    item.get("account_category", ""),
                )

                material_items.append({
                    "account_code": item.get("account_code"),
                    "account_name": item.get("account_name"),
                    "account_category": item.get("account_category"),
                    "amount": amount,
                    "ratio_to_total": round(ratio, 4),
                    "materiality_threshold": threshold,
                    "is_material": is_material,
                    "materiality_basis": materiality_basis,
                    "risk_indicators": risk_indicators,
                    "suggested_procedures": suggested_procedures,
                })

        # Step 6: 按金额排序
        material_items.sort(key=lambda x: abs(float(x["amount"])), reverse=True)

        return material_items

    # -------------------------------------------------------------------------
    # 12.3 suggest_audit_procedures: 根据风险评估结果建议审计程序
    # -------------------------------------------------------------------------

    async def suggest_audit_procedures(self, risk_items: list[dict]) -> list[dict]:
        """
        根据风险评估结果建议审计程序

        输入风险项目列表，输出建议的审计程序列表。
        映射规则见 RISK_TO_PROCEDURE_MAPPING。

        Args:
            risk_items: 风险项目列表，格式如 identify_material_items 返回

        Returns:
            [
                {
                    "procedure_code": str,
                    "procedure_name": str,
                    "procedure_type": str,     # risk_assessment / control_test / substantive
                    "description": str,
                    "target_accounts": [str],  # 针对的科目名称
                    "risk_level": str,        # high / medium / low
                    "priority": int,           # 1=最高
                    "estimated_hours": float,  # 预计工时
                }
            ]
        """
        suggested_procedures = []
        seen_codes = set()

        for item in risk_items:
            risk_type = self._classify_risk_type(item)
            procedures = RISK_TO_PROCEDURE_MAPPING.get(risk_type, RISK_TO_PROCEDURE_MAPPING["general"])

            # 确定风险等级
            risk_level = self._assess_item_risk_level(item)

            # 确定优先级
            priority = self._determine_priority(item, risk_level)

            # 预计工时（基于风险等级）
            estimated_hours = {
                "high": 8.0,
                "medium": 4.0,
                "low": 2.0,
            }.get(risk_level, 4.0)

            for proc in procedures:
                if proc["procedure_code"] in seen_codes:
                    continue
                seen_codes.add(proc["procedure_code"])

                suggested_procedures.append({
                    "procedure_code": proc["procedure_code"],
                    "procedure_name": proc["procedure_name"],
                    "procedure_type": proc["procedure_type"],
                    "description": proc["description"],
                    "target_accounts": [item.get("account_name", "")],
                    "risk_level": risk_level,
                    "priority": priority,
                    "estimated_hours": estimated_hours,
                })

        # 按优先级排序
        suggested_procedures.sort(key=lambda x: (x["priority"], x["procedure_code"]))

        return suggested_procedures

    # -------------------------------------------------------------------------
    # 12.4 auto_update_assessment: 根据新发现自动更新风险评估
    # -------------------------------------------------------------------------

    async def auto_update_assessment(
        self,
        project_id: UUID,
        finding_id: UUID,
    ) -> dict:
        """
        根据新发现自动更新风险评估

        当新的审计发现被记录时，自动重新计算相关科目的风险等级，
        并更新风险评估记录。

        Args:
            project_id: 项目ID
            finding_id: 新发现的ID

        Returns:
            {
                "updated": bool,
                "previous_risk_level": str,
                "new_risk_level": str,
                "assessment_changes": [
                    {
                        "account_code": str,
                        "change_type": str,   # "increased" | "decreased" | "unchanged"
                        "previous_level": str,
                        "new_level": str,
                        "reason": str,
                    }
                ],
                "ai_summary": str,  # AI生成的风险变化摘要
            }
        """
        # Step 1: 获取新发现详情
        finding = await self._get_finding_detail(finding_id)
        if not finding:
            raise ValueError(f"Finding not found: {finding_id}")

        # Step 2: 获取当前风险评估
        current_assessment = await self._get_current_assessment(project_id)

        # Step 3: 确定受影响的科目
        affected_account = finding.get("affected_account")
        finding_severity = finding.get("severity", "medium")

        # Step 4: 获取该科目的现有风险评估
        existing_account_risk = await self._get_account_risk_level(
            project_id, affected_account
        )

        # Step 5: 计算新的风险等级
        previous_level = existing_account_risk.get("combined_risk", "low")
        new_level = self._recalculate_risk_with_finding(
            previous_level, finding_severity
        )

        # Step 6: 更新风险评估记录
        assessment_changes = []
        if new_level != previous_level:
            change_type = "increased" if self._risk_to_score(new_level) > self._risk_to_score(previous_level) else "decreased"
            assessment_changes.append({
                "account_code": affected_account,
                "change_type": change_type,
                "previous_level": previous_level,
                "new_level": new_level,
                "reason": f"新发现编号{finding.get('finding_code')}（严重程度：{finding_severity}）",
            })

            # 更新数据库中的风险评估记录
            await self._update_account_risk_level(
                project_id, affected_account, new_level
            )

        # Step 7: 重新计算整体风险等级
        overall_previous = current_assessment.get("overall_risk", "low") if current_assessment else "low"
        overall_new = await self._recalculate_overall_risk(project_id)

        # Step 8: 生成AI摘要
        ai_summary = await self._generate_finding_impact_summary(
            project_id,
            finding,
            assessment_changes,
            overall_previous,
            overall_new,
        )

        return {
            "updated": len(assessment_changes) > 0,
            "previous_risk_level": overall_previous,
            "new_risk_level": overall_new,
            "assessment_changes": assessment_changes,
            "ai_summary": ai_summary,
        }

    # -------------------------------------------------------------------------
    # 内部辅助方法
    # -------------------------------------------------------------------------

    async def _get_trial_balance_data(self, project_id: UUID) -> list[dict]:
        """获取试算表数据"""
        result = await self.db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        rows = result.scalars().all()

        return [
            {
                "id": str(row.id),
                "account_code": row.standard_account_code,
                "account_name": row.account_name,
                "account_category": row.account_category.value if row.account_category else None,
                "unadjusted_amount": row.unadjusted_amount,
                "rje_adjustment": row.rje_adjustment,
                "aje_adjustment": row.aje_adjustment,
                "audited_amount": row.audited_amount,
                "closing_balance": row.audited_amount or row.unadjusted_amount,
            }
            for row in rows
        ]

    async def _get_materiality(self, project_id: UUID) -> Materiality | None:
        """获取重要性水平"""
        result = await self.db.execute(
            select(Materiality).where(
                Materiality.project_id == project_id,
                Materiality.is_deleted == False,  # noqa: E712
            ).order_by(Materiality.year.desc())
        )
        return result.scalar_one_or_none()

    async def _get_findings_summary(self, project_id: UUID) -> dict:
        """获取审计发现汇总"""
        result = await self.db.execute(
            select(AuditFinding).where(
                AuditFinding.project_id == project_id,
                AuditFinding.is_deleted == False,  # noqa: E712
            )
        )
        findings = list(result.scalars().all())

        severity_counts = {"high": 0, "medium": 0, "low": 0}
        total_amount = Decimal("0")

        for f in findings:
            severity = f.severity.value if f.severity else "medium"
            if severity in severity_counts:
                severity_counts[severity] += 1
            if f.finding_amount:
                total_amount += f.finding_amount

        return {
            "total_count": len(findings),
            "severity_counts": severity_counts,
            "total_amount": total_amount,
        }

    async def _get_findings_affected_accounts(self, project_id: UUID) -> set[str]:
        """获取有审计发现的科目代码集合"""
        result = await self.db.execute(
            select(AuditFinding.affected_account).where(
                AuditFinding.project_id == project_id,
                AuditFinding.is_deleted == False,  # noqa: E712
                AuditFinding.affected_account.isnot(None),  # noqa: E712
            )
        )
        return {row[0] for row in result.all() if row[0]}

    def _calculate_risk_indicators(self, tb_data: list[dict]) -> dict:
        """计算关键财务指标"""
        # 汇总各类型科目
        total_assets = Decimal("0")
        total_liabilities = Decimal("0")
        total_equity = Decimal("0")
        total_revenue = Decimal("0")
        total_expense = Decimal("0")
        inventory = Decimal("0")
        receivables = Decimal("0")
        payables = Decimal("0")

        for item in tb_data:
            amount = item.get("closing_balance") or Decimal("0")
            category = item.get("account_category")

            if category == "asset":
                total_assets += amount
                # 识别特定科目
                name = item.get("account_name", "")
                if any(kw in name for kw in ["存货", "库存"]):
                    inventory += amount
                if any(kw in name for kw in ["应收", "账款"]):
                    receivables += amount
            elif category == "liability":
                total_liabilities += amount
                name = item.get("account_name", "")
                if any(kw in name for kw in ["应付", "账款"]):
                    payables += amount
            elif category == "equity":
                total_equity += amount
            elif category == "revenue":
                total_revenue += amount
            elif category == "expense":
                total_expense += amount

        # 计算比率
        current_ratio = (
            float(total_assets / total_liabilities)
            if total_liabilities > 0 else 0.0
        )
        debt_to_equity = (
            float(total_liabilities / total_equity)
            if total_equity > 0 else 0.0
        )
        profit_margin = (
            float((total_revenue - total_expense) / total_revenue)
            if total_revenue > 0 else 0.0
        )
        revenue_growth = 0.0  # 需要上年数据对比
        inventory_turnover = (
            float(total_revenue / inventory)
            if inventory > 0 else 0.0
        )

        return {
            "total_assets": float(total_assets),
            "total_liabilities": float(total_liabilities),
            "total_equity": float(total_equity),
            "total_revenue": float(total_revenue),
            "total_expense": float(total_expense),
            "current_ratio": round(current_ratio, 2),
            "debt_to_equity": round(debt_to_equity, 2),
            "profit_margin": round(profit_margin, 4),
            "revenue_growth": revenue_growth,
            "inventory_turnover": round(inventory_turnover, 2),
        }

    def _identify_key_risk_areas(
        self,
        tb_data: list[dict],
        materiality: Materiality | None,
        findings_summary: dict,
    ) -> list[dict]:
        """识别关键风险领域"""
        risk_areas = []

        # 重要性阈值
        threshold = (
            float(materiality.performance_materiality)
            if materiality else 0.0
        )

        # 按风险类型分组分析
        risk_rules = [
            {
                "area": "收入确认",
                "risk_type": "revenue_recognition",
                "keywords": ["收入", "销售", "主营", "其他业务收入"],
                "categories": ["revenue"],
                "description": "收入确认时点、金额截止、跨期风险",
                "suggested_response": "实施截止测试、函证确认、分析性复核",
            },
            {
                "area": "应收账款",
                "risk_type": "account_receivable",
                "keywords": ["应收"],
                "categories": ["asset"],
                "description": "应收账款可收回性、账龄结构、坏账准备",
                "suggested_response": "函证确认、账龄分析、期后回款检查",
            },
            {
                "area": "存货",
                "risk_type": "inventory",
                "keywords": ["存货", "库存"],
                "categories": ["asset"],
                "description": "存货存在性、计价方法、跌价风险",
                "suggested_response": "监盘程序、计价测试、跌价评估",
            },
            {
                "area": "固定资产",
                "risk_type": "fixed_assets",
                "keywords": ["固定", "在建工程"],
                "categories": ["asset"],
                "description": "固定资产存在性、折旧计算、减值迹象",
                "suggested_response": "实地盘点、折旧复核、减值测试",
            },
            {
                "area": "关联方交易",
                "risk_type": "related_party",
                "keywords": ["关联方", "关联"],
                "categories": ["asset", "liability", "revenue", "expense"],
                "description": "关联方交易披露完整性、定价公允性",
                "suggested_response": "识别检查、交易测试、披露复核",
            },
            {
                "area": "税务风险",
                "risk_type": "tax",
                "keywords": ["税"],
                "categories": ["liability", "expense"],
                "description": "税务申报准确性、税收优惠合规性",
                "suggested_response": "税务申报复核、所得税测算",
            },
            {
                "area": "或有事项",
                "risk_type": "commitments",
                "keywords": ["预计负债", "或有", "担保", "诉讼"],
                "categories": ["liability"],
                "description": "未决诉讼、担保责任、承诺事项",
                "suggested_response": "律师函证、条款检查、管理层声明",
            },
            {
                "area": "持续经营",
                "risk_type": "going_concern",
                "keywords": [],  # 综合判断
                "categories": [],
                "description": "财务困难迹象、到期债务、现金流紧张",
                "suggested_response": "财务指标分析、借款合同检查、改善措施评估",
            },
        ]

        # 检查每类风险
        high_severity_count = findings_summary.get("severity_counts", {}).get("high", 0)

        for rule in risk_rules:
            affected_items = []
            total_amount = Decimal("0")

            for item in tb_data:
                name = item.get("account_name", "")
                category = item.get("account_category")

                match = False
                if rule["keywords"]:
                    match = any(kw in name for kw in rule["keywords"])
                elif rule["categories"]:
                    match = category in rule["categories"]

                if match:
                    amount = item.get("closing_balance") or Decimal("0")
                    total_amount += abs(amount)
                    affected_items.append({
                        "account_code": item.get("account_code"),
                        "account_name": name,
                        "amount": float(amount),
                    })

            if not affected_items:
                continue

            # 确定风险等级
            risk_level = "low"
            if total_amount > threshold or high_severity_count > 0:
                risk_level = "medium"
            if total_amount > threshold * 2:
                risk_level = "high"

            # 综合判断特定风险
            if rule["risk_type"] == "going_concern" and high_severity_count >= 2:
                risk_level = "high"

            risk_areas.append({
                "area": rule["area"],
                "risk_type": rule["risk_type"],
                "risk_level": risk_level,
                "description": rule["description"],
                "affected_accounts": [a["account_name"] for a in affected_items[:5]],
                "suggested_response": rule["suggested_response"],
            })

        # 按风险等级排序
        risk_order = {"high": 0, "medium": 1, "low": 2}
        risk_areas.sort(key=lambda x: risk_order.get(x["risk_level"], 2))

        return risk_areas

    def _determine_overall_risk_level(
        self,
        risk_areas: list[dict],
        findings_summary: dict,
        indicators: dict,
    ) -> str:
        """确定整体风险等级"""
        # 统计各等级风险
        high_count = sum(1 for r in risk_areas if r["risk_level"] == "high")
        medium_count = sum(1 for r in risk_areas if r["risk_level"] == "medium")

        # 审计发现影响
        high_findings = findings_summary.get("severity_counts", {}).get("high", 0)

        # 财务指标异常
        debt_to_equity = indicators.get("debt_to_equity", 0)
        profit_margin = indicators.get("profit_margin", 0)

        # 综合判断
        score = high_count * 3 + medium_count * 1 + high_findings * 2

        if debt_to_equity > 2.0:
            score += 2
        if profit_margin < 0:
            score += 2

        if score >= 5:
            return "high"
        elif score >= 2:
            return "medium"
        else:
            return "low"

    async def _generate_ai_assessment(
        self,
        project_id: UUID,
        tb_data: list[dict],
        indicators: dict,
        risk_areas: list[dict],
        risk_level: str,
    ) -> str:
        """调用AI生成风险评估文字"""
        try:
            ai_service = AIService(self.db)

            # 构建提示词
            prompt = self._build_risk_assessment_prompt(
                indicators, risk_areas, risk_level, len(tb_data)
            )

            messages = [
                {
                    "role": "system",
                    "content": "你是一位经验丰富的审计师，专注于财务报表风险评估。请基于提供的财务数据和风险分析结果，生成专业的风险评估报告。报告应简明扼要，突出关键风险点。",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            response = await ai_service.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )

            return response

        except Exception as e:
            logger.warning(f"AI assessment generation failed: {e}")
            return (
                f"基于财务数据分析，整体风险等级为{risk_level}。"
                f"关键风险领域：{', '.join(r['area'] for r in risk_areas if r['risk_level'] in ['high', 'medium'])}。"
                f"建议重点关注相关审计程序的执行。"
            )

    def _build_risk_assessment_prompt(
        self,
        indicators: dict,
        risk_areas: list[dict],
        risk_level: str,
        account_count: int,
    ) -> str:
        """构建AI提示词"""
        high_risks = [r for r in risk_areas if r["risk_level"] == "high"]
        medium_risks = [r for r in risk_areas if r["risk_level"] == "medium"]

        prompt = f"""
## 财务报表风险评估请求

### 整体风险等级
{risk_level.upper()}

### 关键财务指标
- 资产总额：{indicators.get('total_assets', 0):,.2f}
- 负债总额：{indicators.get('total_liabilities', 0):,.2f}
- 净资产：{indicators.get('total_equity', 0):,.2f}
- 营业收入：{indicators.get('total_revenue', 0):,.2f}
- 营业成本：{indicators.get('total_expense', 0):,.2f}
- 流动比率：{indicators.get('current_ratio', 0)}
- 资产负债率：{indicators.get('debt_to_equity', 0)}
- 毛利率：{indicators.get('profit_margin', 0):.2%}

### 高风险领域（{len(high_risks)}项）
"""
        for r in high_risks:
            prompt += f"- **{r['area']}**：{r['description']}，涉及科目：{', '.join(r['affected_accounts'][:3])}\n"

        prompt += f"\n### 中风险领域（{len(medium_risks)}项）\n"
        for r in medium_risks:
            prompt += f"- {r['area']}：{r['description']}\n"

        prompt += f"""
### 试算表科目数量
共{account_count}个科目

### 要求
请生成一段专业、简洁的风险评估文字（300-500字），包括：
1. 整体风险评价
2. 主要风险点及原因分析
3. 建议重点关注的审计领域
4. 审计策略建议
"""
        return prompt

    def _calculate_confidence_score(
        self,
        tb_data: list[dict],
        materiality: Materiality | None,
    ) -> float:
        """计算评估置信度"""
        score = 0.5  # 基础分

        # 数据完整性
        if len(tb_data) > 50:
            score += 0.2
        elif len(tb_data) > 20:
            score += 0.1

        # 重要性水平已设定
        if materiality:
            score += 0.15

        # 金额数据完整
        complete_count = sum(
            1 for item in tb_data
            if item.get("closing_balance") is not None
        )
        if complete_count / max(len(tb_data), 1) > 0.9:
            score += 0.15

        return min(score, 1.0)

    def _classify_risk_type(self, item: dict) -> str:
        """根据科目信息分类风险类型"""
        name = item.get("account_name", "").lower()

        if any(kw in name for kw in ["收入", "销售", "主营"]):
            return "revenue_recognition"
        elif any(kw in name for kw in ["应收"]):
            return "account_receivable"
        elif any(kw in name for kw in ["存货", "库存"]):
            return "inventory"
        elif any(kw in name for kw in ["固定", "在建"]):
            return "fixed_assets"
        elif any(kw in name for kw in ["关联"]):
            return "related_party"
        elif any(kw in name for kw in ["税"]):
            return "tax"
        elif any(kw in name for kw in ["预计负债", "或有", "担保", "诉讼"]):
            return "commitments"
        else:
            return "general"

    def _assess_item_risk_level(self, item: dict) -> str:
        """评估单个项目的风险等级"""
        risk_indicators = item.get("risk_indicators", {})

        # 高风险指标计数
        high_risk_count = sum(
            1 for v in risk_indicators.values()
            if v is True
        )

        ratio = item.get("ratio_to_total", 0)
        amount = abs(float(item.get("amount", 0)))

        # 综合判断
        if high_risk_count >= 2 or ratio > 0.15 or amount > 10000000:
            return "high"
        elif high_risk_count >= 1 or ratio > 0.05:
            return "medium"
        else:
            return "low"

    def _determine_priority(self, item: dict, risk_level: str) -> int:
        """确定审计程序优先级"""
        priority_map = {"high": 1, "medium": 2, "low": 3}

        # 涉及复杂判断的科目优先级更高
        risk_indicators = item.get("risk_indicators", {})
        if risk_indicators.get("complex_judgment") or risk_indicators.get("estimate_involved"):
            return 1

        return priority_map.get(risk_level, 3)

    def _suggest_procedures_for_account(
        self,
        account_name: str,
        category: str,
    ) -> list[str]:
        """根据科目推荐审计程序"""
        risk_type = self._classify_risk_type({
            "account_name": account_name,
            "account_category": category,
        })
        procedures = RISK_TO_PROCEDURE_MAPPING.get(risk_type, RISK_TO_PROCEDURE_MAPPING["general"])
        return [p["procedure_code"] for p in procedures[:3]]

    async def _get_finding_detail(self, finding_id: UUID) -> dict | None:
        """获取发现详情"""
        result = await self.db.execute(
            select(AuditFinding).where(
                AuditFinding.id == finding_id,
                AuditFinding.is_deleted == False,  # noqa: E712
            )
        )
        finding = result.scalar_one_or_none()
        if not finding:
            return None

        return {
            "id": str(finding.id),
            "finding_code": finding.finding_code,
            "finding_description": finding.finding_description,
            "severity": finding.severity.value if finding.severity else "medium",
            "affected_account": finding.affected_account,
            "finding_amount": finding.finding_amount,
        }

    async def _get_current_assessment(self, project_id: UUID) -> dict | None:
        """获取当前风险评估"""
        result = await self.db.execute(
            select(func.count(AuditFinding.id)).where(
                AuditFinding.project_id == project_id,
                AuditFinding.is_deleted == False,  # noqa: E712
            )
        )
        count = result.scalar_one()

        # 简单计算整体风险
        if count >= 5:
            return {"overall_risk": "high"}
        elif count >= 2:
            return {"overall_risk": "medium"}
        else:
            return {"overall_risk": "low"}

    async def _get_account_risk_level(
        self,
        project_id: UUID,
        account_code: str | None,
    ) -> dict:
        """获取科目当前风险等级"""
        if not account_code:
            return {"combined_risk": "low"}

        result = await self.db.execute(
            select(RiskAssessment).where(
                RiskAssessment.project_id == project_id,
                RiskAssessment.account_or_cycle == account_code,
                RiskAssessment.is_deleted == False,  # noqa: E712
            ).order_by(RiskAssessment.created_at.desc())
        )
        assessment = result.scalar_one_or_none()

        if assessment:
            return {
                "combined_risk": assessment.combined_risk.value
                if assessment.combined_risk else "low"
            }
        return {"combined_risk": "low"}

    def _recalculate_risk_with_finding(
        self,
        current_level: str,
        finding_severity: str,
    ) -> str:
        """根据新发现重新计算风险等级"""
        current_score = self._risk_to_score(current_level)
        severity_score = self._risk_to_score(finding_severity)

        new_score = min(current_score + severity_score - 1, 3)

        return self._score_to_risk(new_score)

    @staticmethod
    def _risk_to_score(level: str) -> int:
        """风险等级转分数"""
        mapping = {"high": 3, "medium": 2, "low": 1}
        return mapping.get(level.lower(), 2)

    @staticmethod
    def _score_to_risk(score: int) -> str:
        """分数转风险等级"""
        if score >= 3:
            return "high"
        elif score >= 2:
            return "medium"
        else:
            return "low"

    async def _update_account_risk_level(
        self,
        project_id: UUID,
        account_code: str,
        new_risk_level: str,
    ) -> None:
        """更新科目风险等级"""
        result = await self.db.execute(
            select(RiskAssessment).where(
                RiskAssessment.project_id == project_id,
                RiskAssessment.account_or_cycle == account_code,
                RiskAssessment.is_deleted == False,  # noqa: E712
            ).order_by(RiskAssessment.created_at.desc())
        )
        assessment = result.scalar_one_or_none()

        if assessment:
            assessment.combined_risk = RiskLevel(new_risk_level)
        else:
            # 创建新记录
            new_assessment = RiskAssessment(
                project_id=project_id,
                assertion_level="valuation",  # 默认
                account_or_cycle=account_code,
                inherent_risk=RiskLevel(new_risk_level),
                control_risk=RiskLevel("medium"),
                combined_risk=RiskLevel(new_risk_level),
                is_significant_risk=(new_risk_level == "high"),
                risk_description=f"根据审计发现自动更新风险等级为{new_risk_level}",
            )
            self.db.add(new_assessment)

        await self.db.commit()

    async def _recalculate_overall_risk(self, project_id: UUID) -> str:
        """重新计算整体风险等级"""
        result = await self.db.execute(
            select(RiskAssessment).where(
                RiskAssessment.project_id == project_id,
                RiskAssessment.is_deleted == False,  # noqa: E712
            )
        )
        assessments = list(result.scalars().all())

        if not assessments:
            return "low"

        # 统计各等级数量
        risk_counts = {"high": 0, "medium": 0, "low": 0}
        for a in assessments:
            level = a.combined_risk.value if a.combined_risk else "low"
            if level in risk_counts:
                risk_counts[level] += 1

        # 综合判断
        total = len(assessments)
        high_ratio = risk_counts["high"] / total if total > 0 else 0

        if high_ratio >= 0.3 or risk_counts["high"] >= 3:
            return "high"
        elif high_ratio >= 0.1 or risk_counts["high"] >= 1:
            return "medium"
        else:
            return "low"

    async def _generate_finding_impact_summary(
        self,
        project_id: UUID,
        finding: dict,
        changes: list[dict],
        previous_overall: str,
        new_overall: str,
    ) -> str:
        """生成发现影响摘要"""
        try:
            ai_service = AIService(self.db)

            prompt = f"""
审计发现影响分析：

发现编号：{finding.get('finding_code')}
严重程度：{finding.get('severity')}
涉及科目：{finding.get('affected_account') or '未指定'}
发现金额：{finding.get('finding_amount') or '未披露'}
描述：{finding.get('finding_description') or '无'}

风险变化：
- 整体风险从 {previous_overall} 调整为 {new_overall}
- 受影响科目数：{len(changes)}

请用100字以内总结此发现对审计风险的影响。
"""

            messages = [
                {
                    "role": "system",
                    "content": "你是一位专业的审计师，请简洁总结审计发现对整体风险的影响。",
                },
                {"role": "user", "content": prompt},
            ]

            response = await ai_service.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=300,
            )

            return response

        except Exception as e:
            logger.warning(f"AI summary generation failed: {e}")
            return (
                f"新发现（{finding.get('finding_code')}，严重程度：{finding.get('severity')}）"
                f"导致整体风险从{previous_overall}调整为{new_overall}。"
            )
