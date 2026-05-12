"""EQCR 路由包共享 Pydantic 模型"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 意见 CRUD
# ---------------------------------------------------------------------------


class EqcrOpinionCreate(BaseModel):
    """POST /api/eqcr/opinions 请求体。"""

    project_id: UUID = Field(..., description="项目 ID")
    domain: str = Field(
        ...,
        description=(
            "判断域；允许值 materiality / estimate / related_party / "
            "going_concern / opinion_type / component_auditor"
        ),
    )
    verdict: str = Field(
        ...,
        description="评议结论；允许值 agree / disagree / need_more_evidence",
    )
    comment: str | None = Field(None, description="意见说明")
    extra_payload: dict[str, Any] | None = Field(
        None,
        description="附加结构化数据；需求 11 组成部分审计师场景可携带 auditor_id/name",
    )


class EqcrOpinionUpdate(BaseModel):
    """PATCH /api/eqcr/opinions/{id} 请求体；所有字段可选。"""

    verdict: str | None = Field(None)
    comment: str | None = Field(None)
    extra_payload: dict[str, Any] | None = Field(None)


# ---------------------------------------------------------------------------
# 影子计算
# ---------------------------------------------------------------------------


class ShadowComputeRequest(BaseModel):
    """POST /api/eqcr/shadow-compute 请求体。"""

    project_id: UUID = Field(..., description="项目 ID")
    computation: str = Field(
        ...,
        description=(
            "计算类型；允许值 cfs_supplementary / debit_credit_balance / "
            "tb_vs_report / intercompany_elimination"
        ),
    )
    params: dict[str, Any] | None = Field(None, description="计算参数")


# ---------------------------------------------------------------------------
# 审批门禁
# ---------------------------------------------------------------------------


class EqcrApproveRequest(BaseModel):
    """POST /api/eqcr/projects/{project_id}/approve 请求体。"""

    verdict: str = Field(
        ...,
        description="审批结论；允许值 approve / disagree",
    )
    comment: str = Field(..., min_length=1, description="审批意见说明")
    shadow_comp_refs: list[UUID] | None = Field(
        None, description="引用的影子计算记录 ID 列表"
    )
    attached_opinion_ids: list[UUID] | None = Field(
        None, description="附带的 EQCR 意见 ID 列表"
    )


class EqcrUnlockOpinionRequest(BaseModel):
    """POST /api/eqcr/projects/{project_id}/unlock-opinion 请求体。"""

    reason: str = Field(..., min_length=1, description="回退原因（必填）")


# ---------------------------------------------------------------------------
# 笔记
# ---------------------------------------------------------------------------


class EqcrNoteCreate(BaseModel):
    """POST /api/eqcr/projects/{project_id}/notes 请求体。"""

    title: str = Field(..., min_length=1, max_length=200, description="笔记标题")
    content: str | None = Field(None, description="笔记内容")


class EqcrNoteUpdate(BaseModel):
    """PATCH /api/eqcr/projects/{project_id}/notes/{note_id} 请求体。"""

    title: str | None = Field(None, min_length=1, max_length=200, description="笔记标题")
    content: str | None = Field(None, description="笔记内容")


# ---------------------------------------------------------------------------
# 关联方
# ---------------------------------------------------------------------------

VALID_RELATION_TYPES = frozenset(
    ["parent", "subsidiary", "associate", "joint_venture",
     "key_management", "family_member", "other"]
)

VALID_TRANSACTION_TYPES = frozenset(
    ["sales", "purchase", "loan", "guarantee", "service", "asset_transfer", "other"]
)

WRITABLE_PROJECT_ROLES = frozenset(
    ["manager", "signing_partner", "partner", "admin"]
)


class RelatedPartyCreate(BaseModel):
    """POST 关联方注册请求体。"""

    name: str = Field(..., min_length=1, max_length=200, description="关联方名称")
    relation_type: str = Field(..., description="关系类型")
    is_controlled_by_same_party: bool = Field(False, description="是否同一控制")


class RelatedPartyUpdate(BaseModel):
    """PATCH 关联方注册请求体（部分更新）。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    relation_type: str | None = Field(None)
    is_controlled_by_same_party: bool | None = Field(None)


class RelatedPartyTransactionCreate(BaseModel):
    """POST 关联方交易请求体。"""

    related_party_id: UUID = Field(..., description="关联方 ID")
    amount: Decimal | None = Field(None, description="交易金额")
    transaction_type: str = Field(..., description="交易类型")
    is_arms_length: bool | None = Field(None, description="是否公允")
    evidence_refs: Any = Field(None, description="证据引用 JSONB")


class RelatedPartyTransactionUpdate(BaseModel):
    """PATCH 关联方交易请求体（部分更新）。"""

    related_party_id: UUID | None = Field(None)
    amount: Decimal | None = Field(None)
    transaction_type: str | None = Field(None)
    is_arms_length: bool | None = Field(None)
    evidence_refs: Any = Field(None)


# ---------------------------------------------------------------------------
# 备忘录
# ---------------------------------------------------------------------------


class EqcrMemoSaveRequest(BaseModel):
    """保存备忘录编辑内容"""
    sections: dict[str, str]


# ---------------------------------------------------------------------------
# 工时追踪
# ---------------------------------------------------------------------------


class EqcrTimeTrackStartRequest(BaseModel):
    """开始复核计时"""
    pass


class EqcrTimeTrackStopRequest(BaseModel):
    """结束复核计时，生成工时记录"""
    description: str | None = None


# ---------------------------------------------------------------------------
# 独立性声明
# ---------------------------------------------------------------------------


class AnnualDeclarationSubmitRequest(BaseModel):
    """提交年度独立性声明"""
    year: int | None = None
    answers: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 历年对比
# ---------------------------------------------------------------------------


class LinkPriorYearRequest(BaseModel):
    """手动关联上年项目"""
    prior_project_id: UUID
