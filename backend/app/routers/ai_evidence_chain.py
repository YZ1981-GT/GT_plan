"""AI 证据链路由

提供审计证据链的创建、证据管理和分析接口。
包括：
- AI证据链管理（创建/添加证据项/关联/分析）
- 证据链验证（收入/采购/费用/银行流水）
- 验证汇总报告
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.evidence_chain_service import EvidenceChainService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# ============================================================================
# 项目级证据链验证 API（按需求 5.1-5.6）
# ============================================================================
project_router = APIRouter(prefix="/api/projects", tags=["AI-证据链验证"])


class EvidenceChainCreate(BaseModel):
    """创建证据链"""
    project_id: str
    chain_name: str
    business_cycle: str
    description: Optional[str] = None


class EvidenceItemAdd(BaseModel):
    """添加证据项"""
    chain_id: str
    evidence_name: str
    evidence_type: str
    source_module: str
    source_id: Optional[str] = None
    description: Optional[str] = None
    file_path: Optional[str] = None
    ocr_text: Optional[str] = None
    is_key_evidence: bool = False
    completeness: float = 0.0


class EvidenceLinkRequest(BaseModel):
    """关联证据请求"""
    from_item_id: str
    to_item_id: str
    relationship: str
    description: Optional[str] = None


# 项目ID路径参数描述
PROJECT_ID_DESC = "项目ID"


# -------------------------------------------------------------------------
# Task 10.6: 证据链验证 API 端点
# -------------------------------------------------------------------------

@project_router.post("/{project_id}/evidence-chain/revenue")
async def verify_revenue_chain(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    收入循环证据链验证
    
    验证合同→出库→物流→发票→凭证→回款的完整链条，
    按金额/日期/客户名匹配，标注缺失和不一致的证据。
    
    Returns:
        - matched: 匹配的证据链列表
        - missing: 缺失的证据列表
        - inconsistent: 不一致的证据列表
        - total: 总数
    """
    service = EvidenceChainService(db)
    try:
        result = await service.verify_revenue_chain(project_id)
        return result
    except Exception as e:
        logger.exception(f"收入循环证据链验证失败: {project_id}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@project_router.post("/{project_id}/evidence-chain/purchase")
async def verify_purchase_chain(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    采购循环证据链验证
    
    验证合同→入库→发票→凭证→付款的完整链条。
    
    检测异常：
    - has_payment_no_grn: 有付款但无入库单
    - quantity_mismatch: 数量/金额不匹配
    - supplier_mismatch: 供应商不一致
    
    Returns:
        - has_payment_no_grn: 有付款无入库列表
        - quantity_mismatch: 数量不匹配列表
        - supplier_mismatch: 供应商不一致列表
        - total_anomalies: 异常总数
    """
    service = EvidenceChainService(db)
    try:
        result = await service.verify_purchase_chain(project_id)
        return result
    except Exception as e:
        logger.exception(f"采购循环证据链验证失败: {project_id}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@project_router.post("/{project_id}/evidence-chain/expense")
async def verify_expense_chain(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    费用报销证据链验证
    
    验证申请→发票→报销单→审批→凭证的完整链条。
    
    检测异常：
    - date_mismatch: 日期不匹配
    - location_inconsistency: 地点不一致
    - consecutive_invoice_numbers: 发票连号
    - approval_threshold_bypass: 金额卡审批临界值
    - weekend_large_amount: 周末大额报销
    
    Returns:
        - 各类异常列表
        - total_anomalies: 异常总数
    """
    service = EvidenceChainService(db)
    try:
        result = await service.verify_expense_chain(project_id)
        return result
    except Exception as e:
        logger.exception(f"费用报销证据链验证失败: {project_id}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@project_router.post("/{project_id}/evidence-chain/bank-analysis")
async def analyze_bank_statements(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    银行流水深度分析
    
    分析项目银行流水中以下异常：
    - large_transactions: 大额异常交易（>100000）
    - circular_fund: 循环资金检测 A→B→C→A
    - related_party_flow: 关联方资金往来
    - period_end_concentrated: 期末集中收付款（>80%在最后5天）
    - after_hours: 非营业时间交易（早8点前/晚8点后）
    - round_number_transfer: 整数金额大额转账
    
    Returns:
        - 各类异常列表
        - total_anomalies: 异常总数
    """
    service = EvidenceChainService(db)
    try:
        result = await service.analyze_bank_statements(project_id)
        return result
    except Exception as e:
        logger.exception(f"银行流水分析失败: {project_id}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@project_router.get("/{project_id}/evidence-chain/summary")
async def get_chain_summary(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    chain_type: Annotated[str, Query(description="证据链类型: revenue/purchase/expense")],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    获取证据链验证汇总报告
    
    统计指定类型证据链的匹配情况：
    - total: 总数
    - matched: 匹配数
    - mismatched: 不匹配数
    - missing: 缺失数
    - high_risk: 高风险数
    
    当 high_risk > 0 时，自动生成 AI 内容风险提示记录。
    
    Returns:
        - 汇总统计数据
        - ai_content_id: (可选) 生成的风险提示记录ID
    """
    service = EvidenceChainService(db)
    try:
        result = await service.generate_chain_summary(project_id, chain_type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"生成证据链汇总失败: {project_id}")
        raise HTTPException(status_code=500, detail=f"汇总生成失败: {str(e)}")


@project_router.get("/{project_id}/evidence-chains")
async def list_evidence_chains(
    project_id: Annotated[uuid.UUID, Path(description=PROJECT_ID_DESC)],
    chain_type: Annotated[Optional[str], Query(description="证据链类型筛选")] = None,
    risk_level: Annotated[Optional[str], Query(description="风险等级筛选")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    获取项目证据链列表
    
    Returns:
        - data: 证据链列表
        - total: 总数
    """
    from sqlalchemy import select, and_
    from app.models.ai_models import EvidenceChain, EvidenceChainType
    
    query = select(EvidenceChain).where(
        and_(
            EvidenceChain.project_id == project_id,
            EvidenceChain.is_deleted == False,
        )
    )
    
    if chain_type:
        try:
            query = query.where(EvidenceChain.chain_type == EvidenceChainType(chain_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的证据链类型: {chain_type}")
    
    if risk_level:
        query = query.where(EvidenceChain.risk_level == risk_level)
    
    # 统计总数
    count_query = select(EvidenceChain.id).where(
        and_(
            EvidenceChain.project_id == project_id,
            EvidenceChain.is_deleted == False,
        )
    )
    if chain_type:
        count_query = count_query.where(EvidenceChain.chain_type == EvidenceChainType(chain_type))
    if risk_level:
        count_query = count_query.where(EvidenceChain.risk_level == risk_level)
    
    total_result = await db.execute(count_query)
    total = len(list(total_result.scalars().all()))
    
    # 分页查询
    query = query.order_by(EvidenceChain.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    chains = list(result.scalars().all())
    
    return {
        "data": [
            {
                "id": str(c.id),
                "chain_type": c.chain_type,
                "source_document_id": str(c.source_document_id) if c.source_document_id else None,
                "target_document_id": str(c.target_document_id) if c.target_document_id else None,
                "chain_step": c.chain_step,
                "match_status": c.match_status,
                "mismatch_description": c.mismatch_description,
                "risk_level": c.risk_level,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chains
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ============================================================================
# AI证据链管理 API（原有功能）
# ============================================================================
router = APIRouter(prefix="/api/ai/evidence-chain", tags=["AI-证据链"])


@router.post("/chains")
async def create_evidence_chain(
    data: EvidenceChainCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """创建证据链"""
    from uuid import UUID

    service = EvidenceChainService(db)
    chain = await service.create_chain(
        project_id=UUID(data.project_id),
        chain_name=data.chain_name,
        business_cycle=data.business_cycle,
        description=data.description,
        user_id=str(user.id),
    )

    return {
        "chain_id": str(chain.id),
        "chain_name": chain.chain_name,
        "business_cycle": chain.business_cycle,
        "completeness_score": chain.completeness_score,
        "status": "created",
    }


@router.post("/items")
async def add_evidence_item(
    data: EvidenceItemAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """添加证据项"""
    from uuid import UUID

    service = EvidenceChainService(db)

    item = await service.add_evidence_item(
        chain_id=UUID(data.chain_id),
        evidence_name=data.evidence_name,
        evidence_type=data.evidence_type,
        source_module=data.source_module,
        source_id=data.source_id,
        description=data.description,
        file_path=data.file_path,
        ocr_text=data.ocr_text,
        is_key_evidence=data.is_key_evidence,
        completeness=data.completeness,
    )

    # 获取更新后的链评分
    chain = await service.get_chain(item.chain_id)

    return {
        "item_id": str(item.id),
        "chain_id": str(item.chain_id),
        "evidence_name": item.evidence_name,
        "item_order": item.item_order,
        "completeness_score": chain.completeness_score if chain else 0.0,
    }


@router.post("/link")
async def link_evidence_items(
    data: EvidenceLinkRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """关联两个证据项"""
    from uuid import UUID

    service = EvidenceChainService(db)

    result = await service.link_evidence(
        from_item_id=UUID(data.from_item_id),
        to_item_id=UUID(data.to_item_id),
        relationship=data.relationship,
        description=data.description,
    )

    return result


@router.post("/analyze/{chain_id}")
async def analyze_evidence_chain(
    chain_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """AI 分析证据链"""
    from uuid import UUID

    service = EvidenceChainService(db)
    ai_service = AIService(db)

    try:
        analysis = await service.analyze_chain(
            chain_id=UUID(chain_id),
            ai_service=ai_service,
        )
        return analysis
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Evidence chain analysis failed")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")


@router.get("/chains/{chain_id}")
async def get_evidence_chain(
    chain_id: str,
    include_items: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取证据链详情"""
    from uuid import UUID

    service = EvidenceChainService(db)
    chain = await service.get_chain(UUID(chain_id))

    if not chain:
        raise HTTPException(status_code=404, detail="证据链不存在")

    items = []
    if include_items:
        chain_items = await service.get_chain_items(chain.id)
        items = [
            {
                "item_id": str(i.id),
                "evidence_name": i.evidence_name,
                "evidence_type": i.evidence_type,
                "source_module": i.source_module,
                "source_id": i.source_id,
                "description": i.description,
                "is_key_evidence": i.is_key_evidence,
                "completeness": i.completeness,
                "item_order": i.item_order,
            }
            for i in chain_items
        ]

    return {
        "chain_id": str(chain.id),
        "chain_name": chain.chain_name,
        "business_cycle": chain.business_cycle,
        "description": chain.description,
        "completeness_score": chain.completeness_score,
        "created_at": chain.created_at.isoformat() if chain.created_at else None,
        "items": items,
    }


@router.get("/chains")
async def list_evidence_chains(
    project_id: str,
    business_cycle: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出项目的证据链"""
    from uuid import UUID

    service = EvidenceChainService(db)
    chains = await service.list_chains(
        project_id=UUID(project_id),
        business_cycle=business_cycle,
        skip=skip,
        limit=limit,
    )

    return [
        {
            "chain_id": str(c.id),
            "chain_name": c.chain_name,
            "business_cycle": c.business_cycle,
            "description": c.description,
            "completeness_score": c.completeness_score,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in chains
    ]


@router.patch("/items/{item_id}/completeness")
async def update_item_completeness(
    item_id: str,
    completeness: float,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """更新证据项完整性评分"""
    from uuid import UUID

    service = EvidenceChainService(db)
    item = await service.update_item_completeness(
        item_id=UUID(item_id),
        completeness=completeness,
    )

    if not item:
        raise HTTPException(status_code=404, detail="证据项不存在")

    # 获取更新后的链评分
    chain = await service.get_chain(item.chain_id)

    return {
        "item_id": str(item.id),
        "completeness": item.completeness,
        "chain_completeness_score": chain.completeness_score if chain else 0.0,
    }
