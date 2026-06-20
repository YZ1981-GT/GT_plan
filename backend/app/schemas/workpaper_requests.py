"""底稿 router 共享请求模型（Pydantic）

从 `working_paper.py` 抽出的中性请求模型，供主 router 及拆分后的功能域子
router（wp_editor_router / wp_review_router / wp_batch_router / wp_relation_router）
共同 import，避免子 router 反向依赖主 router。

零行为变更：字段名/类型/默认值与原 `working_paper.py` 内定义逐字一致。
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class UploadRequest(BaseModel):
    recorded_version: int


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class ReviewStatusRequest(BaseModel):
    review_status: str
    reason: str | None = None  # 退回时必填
