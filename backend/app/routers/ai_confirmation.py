"""AI 函证辅助路由

提供函证AI辅助功能：
- 函证地址核查
- 回函扫描件OCR识别
- 印章检测与名称比对
- 不符差异原因智能分析
- AI检查结果确认

对应需求: 7.1-7.6
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.models.ai_models import ConfirmationCheckType
from app.services.confirmation_ai_service import ConfirmationAIService
from app.services.permission_service import Permission, check_project_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["AI-函证辅助"])


# =============================================================================
# 请求/响应模型
# =============================================================================

class AddressVerifyRequest(BaseModel):
    """地址核查请求"""
    confirmation_type: Optional[str] = Field(None, description="函证类型筛选: bank/customer/vendor")


class AddressVerifyResponse(BaseModel):
    """地址核查响应"""
    check_id: str
    confirmation_id: str
    match_score: float
    discrepancies: list[str]
    registered_address: Optional[str]
    confirmation_address: str
    historical_addresses: list[str]
    check_result: str
    risk_level: str


class OCRReplyRequest(BaseModel):
    """回函OCR识别请求"""
    file_path: Optional[str] = Field(None, description="回函文件路径")


class OCRReplyResponse(BaseModel):
    """回函OCR识别响应"""
    check_id: str
    confirmation_id: str
    replying_entity: Optional[str]
    confirmed_amount: Optional[float]
    original_amount: Optional[float]
    amount_difference: Optional[float]
    amount_match: Optional[bool]
    seal_detected: bool
    seal_name: Optional[str]
    reply_date: Optional[str]
    risk_level: str


class MismatchAnalysisRequest(BaseModel):
    """差异分析请求"""
    original_amount: float = Field(..., description="原始函证金额")
    reply_amount: float = Field(..., description="回函确认金额")


class MismatchAnalysisResponse(BaseModel):
    """差异分析响应"""
    check_id: str
    confirmation_id: str
    original_amount: float
    reply_amount: float
    difference: float
    difference_ratio: float
    likely_reasons: list[str]
    in_transit_items: list[dict]
    timing_differences: list[dict]
    suggested_reconciliation: str
    risk_level: str


class AICheckResponse(BaseModel):
    """AI检查结果"""
    id: str
    confirmation_id: str
    check_type: str
    check_result: dict
    risk_level: Optional[str]
    human_confirmed: bool
    confirmed_by: Optional[str]
    confirmed_at: Optional[str]
    created_at: str


class ConfirmCheckRequest(BaseModel):
    """确认AI检查请求"""
    action: str = Field(..., description="操作: accept/reject")
    notes: Optional[str] = Field(None, description="确认备注")


class ConfirmCheckResponse(BaseModel):
    """确认AI检查响应"""
    id: str
    human_confirmed: bool
    confirmed_by: str
    confirmed_at: str


# =============================================================================
# 路由实现
# =============================================================================

@router.post("/{project_id}/confirmations/ai/address-verify", response_model=list[AddressVerifyResponse])
async def verify_addresses(
    project_id: str,
    request: AddressVerifyRequest = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    批量函证地址核查

    - 比对工商登记地址
    - 比对上年函证地址
    - 标注疑似异常地址
    - 银行函证校验开户行名称与网点地址
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_READ):
        raise HTTPException(status_code=403, detail="No permission")

    service = ConfirmationAIService(db)

    try:
        results = await service.verify_addresses(
            project_id=UUID(project_id),
            confirmation_type=request.confirmation_type if request else None,
        )
        return results
    except Exception as e:
        logger.exception(f"Address verification failed")
        raise HTTPException(status_code=500, detail=f"地址核查失败: {e}")


@router.post("/{project_id}/confirmations/{confirmation_id}/ai/ocr-reply", response_model=OCRReplyResponse)
async def ocr_reply_scan(
    project_id: str,
    confirmation_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    回函扫描件OCR识别

    - 上传回函扫描件（图片或PDF）
    - PaddleOCR 提取文字
    - LLM 提取回函单位名称、确认金额、签章、回函日期
    - 与原始函证金额比对
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")

    # 保存上传的文件
    import os
    import tempfile
    from datetime import datetime

    upload_dir = os.path.join("uploads", "confirmations", "replies", project_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".png"
    temp_path = os.path.join(upload_dir, f"{confirmation_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_ext}")

    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.exception(f"File upload failed")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")

    service = ConfirmationAIService(db)

    try:
        result = await service.ocr_reply_scan(
            project_id=UUID(project_id),
            confirmation_id=UUID(confirmation_id),
            file_path=temp_path,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"OCR reply scan failed")
        raise HTTPException(status_code=500, detail=f"回函OCR识别失败: {e}")


@router.post("/{project_id}/confirmations/{confirmation_id}/ai/mismatch-analysis", response_model=MismatchAnalysisResponse)
async def analyze_mismatch_reason(
    project_id: str,
    confirmation_id: str,
    request: MismatchAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    不符差异原因智能分析

    - 分析原函金额与回函确认金额的差异
    - 匹配在途款项（期后银行流水/收付款记录）
    - 识别记账时间差（凭证日期比对）
    - 生成差异原因建议
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_READ):
        raise HTTPException(status_code=403, detail="No permission")

    service = ConfirmationAIService(db)

    try:
        result = await service.analyze_mismatch_reason(
            project_id=UUID(project_id),
            confirmation_id=UUID(confirmation_id),
            original_amount=request.original_amount,
            reply_amount=request.reply_amount,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Mismatch analysis failed")
        raise HTTPException(status_code=500, detail=f"差异分析失败: {e}")


@router.post("/{project_id}/confirmations/{confirmation_id}/ai/seal-check")
async def check_seal(
    project_id: str,
    confirmation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    印章检测与名称比对

    - 检测印章存在性
    - 提取印章文字
    - 与函证对象名称比对
    - 银行函证校验银行业务专用章
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_READ):
        raise HTTPException(status_code=403, detail="No permission")

    service = ConfirmationAIService(db)

    try:
        result = await service.check_seal(
            project_id=UUID(project_id),
            confirmation_id=UUID(confirmation_id),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Seal check failed")
        raise HTTPException(status_code=500, detail=f"印章检测失败: {e}")


@router.get("/{project_id}/confirmations/ai/checks", response_model=list[AICheckResponse])
async def get_ai_checks(
    project_id: str,
    confirmation_id: Optional[str] = Query(None, description="函证ID筛选"),
    check_type: Optional[str] = Query(None, description="检查类型: address_verify/reply_ocr/amount_compare/seal_check"),
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取AI检查结果列表

    支持按函证ID和检查类型筛选
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_READ):
        raise HTTPException(status_code=403, detail="No permission")

    service = ConfirmationAIService(db)

    # 解析检查类型
    check_type_enum = None
    if check_type:
        try:
            check_type_enum = ConfirmationCheckType(check_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的检查类型: {check_type}，可选值: address_verify, reply_ocr, amount_compare, seal_check",
            )

    try:
        results = await service.get_ai_checks(
            project_id=UUID(project_id),
            confirmation_id=UUID(confirmation_id) if confirmation_id else None,
            check_type=check_type_enum,
            skip=skip,
            limit=limit,
        )
        return results
    except Exception as e:
        logger.exception(f"Get AI checks failed")
        raise HTTPException(status_code=500, detail=f"获取AI检查结果失败: {e}")


@router.put("/{project_id}/confirmations/ai/checks/{check_id}/confirm", response_model=ConfirmCheckResponse)
async def confirm_ai_check(
    project_id: str,
    check_id: str,
    request: ConfirmCheckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    确认AI检查结果

    - accept: 接受AI检查结果
    - reject: 拒绝AI检查结果，需提供备注说明原因
    """
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")

    if request.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action 必须是 accept 或 reject")

    if request.action == "reject" and not request.notes:
        raise HTTPException(status_code=400, detail="拒绝时必须提供 notes 说明原因")

    service = ConfirmationAIService(db)

    try:
        result = await service.confirm_ai_check(
            check_id=UUID(check_id),
            user_id=user.id,
            action=request.action,
            notes=request.notes,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Confirm AI check failed")
        raise HTTPException(status_code=500, detail=f"确认失败: {e}")


# =============================================================================
# 原有路由（保持向后兼容）
# =============================================================================

from pydantic import BaseModel
from typing import Optional as OptStr

class ConfirmationAuditRequest(BaseModel):
    """函证审核请求"""
    project_id: str
    confirmation_type: str
    original_text: str
    response_text: OptStr[str] = None
    audit_period: str


@router.post("/ai/confirmation/audit")
async def audit_confirmation(
    request: ConfirmationAuditRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    AI 审核函证内容（原有接口，保持向后兼容）
    """
    from uuid import UUID

    valid_types = ["bank", "customer", "vendor", "lawyer", "other"]
    if request.confirmation_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的函证类型: {request.confirmation_type}",
        )

    service = ConfirmationAIService(db)

    try:
        audit = await service.audit_confirmation(
            project_id=UUID(request.project_id),
            confirmation_type=request.confirmation_type,
            original_text=request.original_text,
            response_text=request.response_text,
            audit_period=request.audit_period,
            user_id=str(user.id),
        )

        return {
            "audit_id": str(audit.id),
            "confirmation_type": audit.confirmation_type,
            "status": audit.status,
            "audit_result": audit.audit_result,
            "created_at": audit.created_at.isoformat() if audit.created_at else None,
        }
    except Exception as e:
        logger.exception("Confirmation audit failed")
        raise HTTPException(status_code=500, detail=f"审核失败: {e}")


@router.get("/ai/confirmation/audit/{audit_id}")
async def get_confirmation_audit(
    audit_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """获取函证审核记录"""
    from uuid import UUID

    service = ConfirmationAIService(db)
    audit = await service.get_audit(UUID(audit_id))

    if not audit:
        raise HTTPException(status_code=404, detail="审核记录不存在")

    return {
        "audit_id": str(audit.id),
        "confirmation_type": audit.confirmation_type,
        "original_content": audit.original_content,
        "response_content": audit.response_content,
        "audit_period": audit.audit_period,
        "status": audit.status,
        "audit_result": audit.audit_result,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
    }


@router.get("/ai/confirmation/audits")
async def list_confirmation_audits(
    project_id: str,
    confirmation_type: OptStr[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """列出项目的函证审核记录"""
    from uuid import UUID

    service = ConfirmationAIService(db)
    audits = await service.list_audits(
        project_id=UUID(project_id),
        confirmation_type=confirmation_type,
        skip=skip,
        limit=limit,
    )

    return [
        {
            "audit_id": str(a.id),
            "confirmation_type": a.confirmation_type,
            "audit_period": a.audit_period,
            "status": a.status,
            "audit_result": a.audit_result,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in audits
    ]
