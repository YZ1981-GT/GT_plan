"""符号约定 API — 方向异常列表、用户方向覆盖、批量确认。

Tasks: 5.4, 5.5, 7.1, 7.6
Requirements: 4.4, 4.5, 5.3, 6.3, 6.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.services.ledger_import.sign_convention_types import (
    CURRENT_SIGN_CONVENTION,
    SignAnomaly,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/datasets/{dataset_id}/sign-convention",
    tags=["符号约定"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class SignAnomalyItem(BaseModel):
    """单条方向异常。"""
    account_code: str
    account_name: str | None = None
    expected_direction: str
    actual_direction: str
    balance_amount: float
    category: str
    reason: str
    review_status: str = "pending"  # pending | accepted | corrected


class SignAnomalyListResponse(BaseModel):
    """方向异常列表响应。"""
    anomalies: list[SignAnomalyItem]
    total: int
    sign_convention_version: str


class DirectionOverrideRequest(BaseModel):
    """用户方向覆盖请求。"""
    table_name: str = Field(..., description="tb_balance | tb_aux_balance")
    record_id: UUID
    override_direction: str = Field(..., description="debit | credit")
    override_reason: str = Field(..., min_length=1)


class DirectionOverrideResponse(BaseModel):
    """方向覆盖响应。"""
    id: UUID
    original_direction: str | None
    override_direction: str
    override_reason: str
    override_by: UUID
    override_at: datetime


class BatchConfirmRequest(BaseModel):
    """批量确认异常请求。"""
    anomaly_ids: list[str] = Field(..., description="account_codes to confirm")
    confirm_reason: str = Field(..., min_length=1)


class BatchConfirmResponse(BaseModel):
    """批量确认响应。"""
    confirmed_count: int
    failed_ids: list[str]


class TrialBalanceDirectionFields(BaseModel):
    """试算表 API 方向扩展字段（Task 7.1 response model）。"""
    direction: str | None = None  # debit | credit | unknown
    direction_source: str | None = None
    direction_review_status: str | None = None  # pending | accepted | corrected
    sign_anomaly_flags: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# 5.4: GET /anomalies — 方向异常列表
# ---------------------------------------------------------------------------


@router.get("/anomalies", response_model=SignAnomalyListResponse)
async def list_sign_anomalies(
    project_id: UUID,
    dataset_id: UUID,
    review_status: Optional[str] = Query(None, description="筛选复核状态"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SignAnomalyListResponse:
    """获取方向异常列表。

    真正 DB 查询在 V064 部署后实现；当前返回空列表结构。
    """
    # TODO: 真实查询 — SELECT rows WHERE sign_anomaly_flags IS NOT NULL
    return SignAnomalyListResponse(
        anomalies=[],
        total=0,
        sign_convention_version=CURRENT_SIGN_CONVENTION,
    )


# ---------------------------------------------------------------------------
# 5.5: POST /direction-override — 用户确认/修正方向
# ---------------------------------------------------------------------------


@router.post("/direction-override", response_model=DirectionOverrideResponse)
async def create_direction_override(
    project_id: UUID,
    dataset_id: UUID,
    body: DirectionOverrideRequest,
) -> DirectionOverrideResponse:
    """用户覆盖方向，记录原因和留痕。

    写入 direction_override 表（V064 已建），保留原始导入行不变。
    当前为 stub：返回结构正确的 mock 数据。
    """
    # TODO: 真实 DB 插入 direction_override 表
    now = datetime.now(timezone.utc)
    mock_user_id = UUID("00000000-0000-0000-0000-000000000001")
    return DirectionOverrideResponse(
        id=uuid4(),
        original_direction=None,
        override_direction=body.override_direction,
        override_reason=body.override_reason,
        override_by=mock_user_id,
        override_at=now,
    )


# ---------------------------------------------------------------------------
# 7.6: POST /anomalies/batch-confirm — 批量确认
# ---------------------------------------------------------------------------


@router.post("/anomalies/batch-confirm", response_model=BatchConfirmResponse)
async def batch_confirm_anomalies(
    project_id: UUID,
    dataset_id: UUID,
    body: BatchConfirmRequest,
) -> BatchConfirmResponse:
    """批量确认异常为正确（真实业务余额）。

    将 review_status 更新为 accepted，记录确认原因。
    当前为 stub。
    """
    # TODO: 真实 DB 批量 UPDATE sign_anomaly_flags->review_status
    return BatchConfirmResponse(
        confirmed_count=len(body.anomaly_ids),
        failed_ids=[],
    )
