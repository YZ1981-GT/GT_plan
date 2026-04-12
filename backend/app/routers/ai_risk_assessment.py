"""AI Risk Assessment Router — AI驱动的财务报表风险评估接口

提供：
- POST /api/projects/{id}/risk-assessment/assess — 运行风险评估
- GET /api/projects/{id}/risk-assessment/material-items — 获取重大科目
- GET /api/projects/{id}/risk-assessment/suggestions — 获取审计程序建议
- POST /api/projects/{id}/risk-assessment/update — 根据发现自动更新评估

对接：
- RiskAssessmentService: AI驱动的风险评估服务
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.risk_assessment_service import RiskAssessmentService

logger = logging.getLogger(__name__)

# ============================================================================
# Router Configuration
# ============================================================================
router = APIRouter(prefix="/api/projects", tags=["AI-风险评估"])

PROJECT_ID_DESC = "项目ID"
FINDING_ID_DESC = "审计发现ID"


# ============================================================================
# Pydantic Schemas
# ============================================================================

class RiskAssessmentResponse(BaseModel):
    """风险评估响应"""
    risk_level: str  # high / medium / low
    confidence_score: float
    key_risk_areas: list[dict[str, Any]]
    risk_indicators: dict[str, Any]
    ai_assessment_text: str
    material_findings_count: int
    overall_materiality: float
    performance_materiality: float


class MaterialItem(BaseModel):
    """重大科目"""
    account_code: str
    account_name: str
    account_category: str
    amount: float
    ratio_to_total: float
    materiality_threshold: float
    is_material: bool
    materiality_basis: str
    risk_indicators: dict[str, Any]
    suggested_procedures: list[str]


class MaterialItemsResponse(BaseModel):
    """重大科目列表响应"""
    items: list[MaterialItem]
    total_count: int
    material_count: int


class SuggestedProcedure(BaseModel):
    """建议审计程序"""
    procedure_code: str
    procedure_name: str
    procedure_type: str
    description: str
    target_accounts: list[str]
    risk_level: str
    priority: int
    estimated_hours: float


class SuggestionsResponse(BaseModel):
    """审计程序建议响应"""
    procedures: list[SuggestedProcedure]
    total_count: int
    by_priority: dict[str, int]


class AutoUpdateRequest(BaseModel):
    """自动更新请求"""
    finding_id: str


class AssessmentChange(BaseModel):
    """评估变更"""
    account_code: str
    change_type: str
    previous_level: str
    new_level: str
    reason: str


class AutoUpdateResponse(BaseModel):
    """自动更新响应"""
    updated: bool
    previous_risk_level: str
    new_risk_level: str
    assessment_changes: list[AssessmentChange]
    ai_summary: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/{project_id}/risk-assessment/assess")
async def assess_financial_risk(
    project_id: Annotated[UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RiskAssessmentResponse:
    """
    运行AI驱动的财务报表整体风险评估

    评估流程：
    1. 查询试算表数据，计算关键财务指标
    2. 获取重要性水平设定
    3. 汇总已有审计发现情况
    4. 识别关键风险领域
    5. 调用AI服务生成风险评估报告

    Returns:
        - risk_level: 整体风险等级（high/medium/low）
        - confidence_score: 评估置信度（0.0-1.0）
        - key_risk_areas: 关键风险领域列表
        - risk_indicators: 关键财务指标
        - ai_assessment_text: AI生成的完整评估文字
        - material_findings_count: 重大发现数量
        - overall_materiality: 整体重要性水平
        - performance_materiality: 实际执行重要性水平
    """
    service = RiskAssessmentService(db)

    try:
        result = await service.assess_financial_risk(project_id)

        # 转换 Decimal 为 float
        return RiskAssessmentResponse(
            risk_level=result["risk_level"],
            confidence_score=result["confidence_score"],
            key_risk_areas=result["key_risk_areas"],
            risk_indicators=result["risk_indicators"],
            ai_assessment_text=result["ai_assessment_text"],
            material_findings_count=result["material_findings_count"],
            overall_materiality=float(result["overall_materiality"]),
            performance_materiality=float(result["performance_materiality"]),
        )

    except Exception as e:
        logger.exception(f"Risk assessment failed for project {project_id}")
        raise HTTPException(
            status_code=500,
            detail=f"风险评估失败: {str(e)}"
        )


@router.get("/{project_id}/risk-assessment/material-items")
async def get_material_items(
    project_id: Annotated[UUID, Path(description=PROJECT_ID_DESC)],
    only_material: Annotated[
        bool,
        Query(description="仅返回重大科目")
    ] = True,
    min_ratio: Annotated[
        Optional[float],
        Query(description="最小占比阈值（0.0-1.0）")
    ] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MaterialItemsResponse:
    """
    获取重大科目和重要事项列表

    重大科目判断标准（满足任一即视为重大）：
    - 金额超过重要性水平阈值
    - 金额占总资产/总收入的比例超过5%
    - 涉及复杂会计判断（减值、估计等）
    - 存在审计发现的历史科目

    Query Parameters:
        only_material: 是否仅返回重大科目
        min_ratio: 最小占比阈值筛选

    Returns:
        - items: 科目列表
        - total_count: 总数
        - material_count: 重大科目数量
    """
    service = RiskAssessmentService(db)

    try:
        items = await service.identify_material_items(project_id)

        # 应用筛选条件
        if min_ratio is not None:
            items = [i for i in items if i["ratio_to_total"] >= min_ratio]

        if only_material:
            items = [i for i in items if i["is_material"]]

        # 转换 Decimal 为 float
        converted_items = []
        for item in items:
            converted_items.append(MaterialItem(
                account_code=item["account_code"],
                account_name=item["account_name"],
                account_category=item["account_category"],
                amount=float(item["amount"]),
                ratio_to_total=item["ratio_to_total"],
                materiality_threshold=float(item["materiality_threshold"]),
                is_material=item["is_material"],
                materiality_basis=item["materiality_basis"],
                risk_indicators=item["risk_indicators"],
                suggested_procedures=item["suggested_procedures"],
            ))

        material_count = sum(1 for i in converted_items if i.is_material)

        return MaterialItemsResponse(
            items=converted_items,
            total_count=len(converted_items),
            material_count=material_count,
        )

    except Exception as e:
        logger.exception(f"Get material items failed for project {project_id}")
        raise HTTPException(
            status_code=500,
            detail=f"获取重大科目失败: {str(e)}"
        )


@router.get("/{project_id}/risk-assessment/suggestions")
async def get_audit_procedure_suggestions(
    project_id: Annotated[UUID, Path(description=PROJECT_ID_DESC)],
    risk_levels: Annotated[
        Optional[str],
        Query(description="风险等级筛选，逗号分隔（如: high,medium）")
    ] = None,
    procedure_types: Annotated[
        Optional[str],
        Query(description="程序类型筛选，逗号分隔（如: substantive,control_test）")
    ] = None,
    max_procedures: Annotated[
        int,
        Query(description="最大返回数量", ge=1, le=100)
    ] = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SuggestionsResponse:
    """
    根据风险评估结果建议审计程序

    基于已识别的重大科目和风险领域，自动映射建议的审计程序。
    审计程序映射规则见 RISK_TO_PROCEDURE_MAPPING。

    Query Parameters:
        risk_levels: 风险等级筛选（high/medium/low）
        procedure_types: 程序类型筛选（risk_assessment/control_test/substantive）
        max_procedures: 最大返回数量（默认50）

    Returns:
        - procedures: 建议程序列表
        - total_count: 总数
        - by_priority: 按优先级统计的数量
    """
    service = RiskAssessmentService(db)

    try:
        # 首先获取重大科目
        material_items = await service.identify_material_items(project_id)

        # 获取建议程序
        suggestions = await service.suggest_audit_procedures(material_items)

        # 应用筛选条件
        if risk_levels:
            levels = [l.strip().lower() for l in risk_levels.split(",")]
            suggestions = [s for s in suggestions if s["risk_level"] in levels]

        if procedure_types:
            types = [t.strip().lower() for t in procedure_types.split(",")]
            suggestions = [s for s in suggestions if s["procedure_type"] in types]

        # 限制数量
        suggestions = suggestions[:max_procedures]

        # 转换并统计
        converted = [
            SuggestedProcedure(
                procedure_code=s["procedure_code"],
                procedure_name=s["procedure_name"],
                procedure_type=s["procedure_type"],
                description=s["description"],
                target_accounts=s["target_accounts"],
                risk_level=s["risk_level"],
                priority=s["priority"],
                estimated_hours=s["estimated_hours"],
            )
            for s in suggestions
        ]

        by_priority = {
            "high": sum(1 for s in converted if s.priority == 1),
            "medium": sum(1 for s in converted if s.priority == 2),
            "low": sum(1 for s in converted if s.priority == 3),
        }

        return SuggestionsResponse(
            procedures=converted,
            total_count=len(converted),
            by_priority=by_priority,
        )

    except Exception as e:
        logger.exception(f"Get audit procedure suggestions failed for project {project_id}")
        raise HTTPException(
            status_code=500,
            detail=f"获取审计程序建议失败: {str(e)}"
        )


@router.post("/{project_id}/risk-assessment/update")
async def auto_update_assessment(
    project_id: Annotated[UUID, Path(description=PROJECT_ID_DESC)],
    data: AutoUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AutoUpdateResponse:
    """
    根据新发现自动更新风险评估

    当新的审计发现被记录时，自动重新计算相关科目的风险等级，
    并更新整体风险评估。

    触发条件：
    - 新发现严重程度为 high：相关科目风险等级+1
    - 新发现严重程度为 medium：维持当前风险等级
    - 新发现严重程度为 low：相关科目风险等级-1（最低为low）

    Request Body:
        finding_id: 新发现的UUID

    Returns:
        - updated: 是否有风险等级变更
        - previous_risk_level: 变更前的整体风险等级
        - new_risk_level: 变更后的整体风险等级
        - assessment_changes: 具体变更明细
        - ai_summary: AI生成的风险变化摘要
    """
    service = RiskAssessmentService(db)

    try:
        finding_id = UUID(data.finding_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的finding_id格式: {data.finding_id}"
        )

    try:
        result = await service.auto_update_assessment(project_id, finding_id)

        # 转换变更记录
        changes = [
            AssessmentChange(
                account_code=c["account_code"],
                change_type=c["change_type"],
                previous_level=c["previous_level"],
                new_level=c["new_level"],
                reason=c["reason"],
            )
            for c in result["assessment_changes"]
        ]

        return AutoUpdateResponse(
            updated=result["updated"],
            previous_risk_level=result["previous_risk_level"],
            new_risk_level=result["new_risk_level"],
            assessment_changes=changes,
            ai_summary=result["ai_summary"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Auto update assessment failed for project {project_id}")
        raise HTTPException(
            status_code=500,
            detail=f"自动更新评估失败: {str(e)}"
        )


# ============================================================================
# Summary Endpoint (Additional)
# ============================================================================

@router.get("/{project_id}/risk-assessment/summary")
async def get_risk_assessment_summary(
    project_id: Annotated[UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    获取风险评估综合摘要

    一次性返回：
    - 整体风险评估结果
    - 重大科目列表
    - 高优先级审计程序建议

    用于风险评估概览页面的一次性加载。
    """
    service = RiskAssessmentService(db)

    try:
        # 并行获取各项数据
        import asyncio

        assessment_task = service.assess_financial_risk(project_id)
        material_items_task = service.identify_material_items(project_id)

        assessment, material_items = await asyncio.gather(
            assessment_task,
            material_items_task,
        )

        # 获取建议程序（仅高优先级）
        suggestions = await service.suggest_audit_procedures(material_items)
        high_priority_suggestions = [
            s for s in suggestions if s["risk_level"] == "high"
        ][:10]

        # 统计重大科目
        material_count = sum(1 for i in material_items if i["is_material"])

        return {
            "risk_assessment": {
                "risk_level": assessment["risk_level"],
                "confidence_score": assessment["confidence_score"],
                "key_risk_areas": assessment["key_risk_areas"],
                "material_findings_count": assessment["material_findings_count"],
            },
            "material_items": {
                "total_count": len(material_items),
                "material_count": material_count,
                "top_items": [
                    {
                        "account_code": i["account_code"],
                        "account_name": i["account_name"],
                        "amount": float(i["amount"]),
                        "ratio_to_total": i["ratio_to_total"],
                    }
                    for i in material_items[:5]
                ],
            },
            "priority_procedures": high_priority_suggestions,
            "high_priority_count": len(high_priority_suggestions),
        }

    except Exception as e:
        logger.exception(f"Get risk summary failed for project {project_id}")
        raise HTTPException(
            status_code=500,
            detail=f"获取风险摘要失败: {str(e)}"
        )
