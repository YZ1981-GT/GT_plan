"""底稿 router 共享请求模型（Pydantic）

从 `working_paper.py` 抽出的中性请求模型，供主 router 及拆分后的功能域子
router（wp_editor_router / wp_review_router / wp_batch_router / wp_relation_router）
共同 import，避免子 router 反向依赖主 router。

零行为变更：字段名/类型/默认值与原 `working_paper.py` 内定义逐字一致。
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    recorded_version: int


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    assigned_to: UUID | None = None
    reviewer: UUID | None = None
    # 被委派人可见范围不含该循环（400 out_of_scope）时带理由重试 ⇒ 同事务扩大其可见范围
    # （spec procedure-trim-generation-delegation-chain 需求 4.4）
    expand_scope: bool = False
    scope_reason: str | None = Field(default=None, max_length=500)


class ReviewStatusRequest(BaseModel):
    review_status: str
    reason: str | None = None  # 退回时必填
