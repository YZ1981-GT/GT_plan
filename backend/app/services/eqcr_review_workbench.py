"""EQCR 独立复核工作台 — P2-2 实现

聚合 KAM、重大估计、持续经营、关联方、集团范围、重大调整；
区分普通复核与 EQCR 批注；
建立 EQCR checklist；
EQCR 签出要求 checklist 完成。

Requirements: 5.1, 5.2, 5.3
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── EQCR Checklist 定义 ─────────────────────────────────────────────────────

class EqcrChecklistItem(BaseModel):
    """单项 EQCR checklist 条目"""
    id: str
    category: str  # kam / estimate / going_concern / related_party / group_scope / material_adjustment
    title: str
    description: Optional[str] = None
    required: bool = True
    completed: bool = False
    completed_at: Optional[str] = None
    completed_by: Optional[str] = None
    comment: Optional[str] = None


# 标准 EQCR Checklist 模板（配置驱动）
EQCR_CHECKLIST_TEMPLATE: list[dict[str, Any]] = [
    # KAM - 关键审计事项
    {
        "id": "eqcr-kam-01",
        "category": "kam",
        "title": "KAM 识别是否恰当",
        "description": "确认关键审计事项的识别与治理层沟通一致",
        "required": True,
    },
    {
        "id": "eqcr-kam-02",
        "category": "kam",
        "title": "KAM 应对程序是否充分",
        "description": "评估对每个 KAM 执行的审计程序是否足够",
        "required": True,
    },
    {
        "id": "eqcr-kam-03",
        "category": "kam",
        "title": "KAM 描述是否准确反映工作",
        "description": "审计报告中 KAM 描述与实际审计程序是否一致",
        "required": True,
    },
    # 重大估计
    {
        "id": "eqcr-est-01",
        "category": "estimate",
        "title": "重大会计估计识别完整性",
        "description": "确认已识别所有涉及重大判断的会计估计",
        "required": True,
    },
    {
        "id": "eqcr-est-02",
        "category": "estimate",
        "title": "管理层估计方法合理性",
        "description": "评估管理层所用估计方法和假设是否合理",
        "required": True,
    },
    {
        "id": "eqcr-est-03",
        "category": "estimate",
        "title": "估计不确定性披露充分性",
        "description": "确认财务报表是否充分披露估计不确定性",
        "required": True,
    },
    # 持续经营
    {
        "id": "eqcr-gc-01",
        "category": "going_concern",
        "title": "持续经营评估是否充分",
        "description": "确认对管理层持续经营假设的评估是否充分",
        "required": True,
    },
    {
        "id": "eqcr-gc-02",
        "category": "going_concern",
        "title": "持续经营相关事项或情况",
        "description": "确认是否存在可能导致对持续经营产生重大疑虑的事项",
        "required": True,
    },
    # 关联方
    {
        "id": "eqcr-rp-01",
        "category": "related_party",
        "title": "关联方识别完整性",
        "description": "确认关联方关系和交易是否已完整识别",
        "required": True,
    },
    {
        "id": "eqcr-rp-02",
        "category": "related_party",
        "title": "关联方交易披露恰当性",
        "description": "确认关联方交易是否按准则恰当披露",
        "required": True,
    },
    # 集团范围
    {
        "id": "eqcr-grp-01",
        "category": "group_scope",
        "title": "集团审计范围充分性",
        "description": "确认组成部分审计范围是否覆盖重大组成部分",
        "required": True,
    },
    {
        "id": "eqcr-grp-02",
        "category": "group_scope",
        "title": "组成部分审计师工作评价",
        "description": "确认对组成部分审计师工作的评价是否充分",
        "required": False,
    },
    # 重大调整
    {
        "id": "eqcr-adj-01",
        "category": "material_adjustment",
        "title": "重大审计调整恰当性",
        "description": "确认已识别调整分录的恰当性和完整性",
        "required": True,
    },
    {
        "id": "eqcr-adj-02",
        "category": "material_adjustment",
        "title": "未更正错报评价",
        "description": "确认未更正错报的汇总是否低于重要性",
        "required": True,
    },
]


# ─── EQCR 批注类型区分 ────────────────────────────────────────────────────────

class AnnotationType:
    """复核批注类型标识"""
    NORMAL_REVIEW = "normal_review"       # 普通项目组复核
    EQCR_INDEPENDENT = "eqcr_independent"  # EQCR 独立复核


class EqcrAnnotation(BaseModel):
    """EQCR 独立复核批注"""
    id: Optional[str] = None
    project_id: str
    category: str  # kam / estimate / going_concern / related_party / group_scope / material_adjustment
    content: str
    annotation_type: str = AnnotationType.EQCR_INDEPENDENT
    author_id: Optional[str] = None
    target_id: Optional[str] = None  # 关联的底稿/附件 ID
    target_type: Optional[str] = None  # workpaper / attachment / report
    created_at: Optional[str] = None


# ─── EQCR 独立复核工作台服务 ──────────────────────────────────────────────────

class EqcrReviewWorkbenchService:
    """EQCR 独立复核工作台

    Requirements 5.1/5.2/5.3:
    - 聚合 KAM、重大估计、持续经营、关联方、集团范围、重大调整
    - 区分普通复核与 EQCR 批注
    - 建立 EQCR checklist
    - EQCR 签出要求 checklist 完成
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── P2-2.1 聚合 KAM、重大估计、持续经营、关联方、集团范围、重大调整 ──

    async def get_eqcr_workbench(
        self, project_id: UUID, user_id: UUID
    ) -> dict[str, Any]:
        """返回 EQCR 工作台聚合数据。"""
        from app.services.eqcr_workbench_service import EqcrWorkbenchService

        base_svc = EqcrWorkbenchService(self.db)

        # 获取基础 overview
        try:
            overview = await base_svc.get_project_overview(user_id, project_id)
        except Exception as e:
            logger.warning(f"[EqcrReviewWorkbench] overview failed: {e}")
            overview = None

        # 获取 checklist 状态
        checklist = self.get_checklist_status(project_id)

        # 获取各维度摘要
        dimensions = self._build_dimension_summary(overview)

        return {
            "project_id": str(project_id),
            "overview": overview,
            "dimensions": dimensions,
            "checklist": checklist,
            "can_sign_off": self.can_sign_off(checklist),
        }

    def _build_dimension_summary(
        self, overview: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """构建 6 维度摘要。"""
        if not overview:
            return self._default_dimensions()

        opinion_by_domain = (
            overview.get("opinion_summary", {}).get("by_domain", {})
        )

        dimensions = [
            {
                "id": "kam",
                "title": "关键审计事项 (KAM)",
                "status": opinion_by_domain.get("materiality") or "not_reviewed",
                "route_suffix": "/eqcr/kam",
            },
            {
                "id": "estimate",
                "title": "重大会计估计",
                "status": opinion_by_domain.get("estimate") or "not_reviewed",
                "route_suffix": "/eqcr/estimates",
            },
            {
                "id": "going_concern",
                "title": "持续经营",
                "status": opinion_by_domain.get("going_concern") or "not_reviewed",
                "route_suffix": "/eqcr/going-concern",
            },
            {
                "id": "related_party",
                "title": "关联方",
                "status": opinion_by_domain.get("related_party") or "not_reviewed",
                "route_suffix": "/eqcr/related-parties",
            },
            {
                "id": "group_scope",
                "title": "集团审计范围",
                "status": "not_reviewed",  # 暂无直接 opinion 对应
                "route_suffix": "/eqcr/group-scope",
            },
            {
                "id": "material_adjustment",
                "title": "重大调整",
                "status": "not_reviewed",
                "route_suffix": "/eqcr/adjustments",
            },
        ]
        return dimensions

    def _default_dimensions(self) -> list[dict[str, Any]]:
        """无数据时的默认维度列表。"""
        return [
            {"id": "kam", "title": "关键审计事项 (KAM)", "status": "not_reviewed", "route_suffix": "/eqcr/kam"},
            {"id": "estimate", "title": "重大会计估计", "status": "not_reviewed", "route_suffix": "/eqcr/estimates"},
            {"id": "going_concern", "title": "持续经营", "status": "not_reviewed", "route_suffix": "/eqcr/going-concern"},
            {"id": "related_party", "title": "关联方", "status": "not_reviewed", "route_suffix": "/eqcr/related-parties"},
            {"id": "group_scope", "title": "集团审计范围", "status": "not_reviewed", "route_suffix": "/eqcr/group-scope"},
            {"id": "material_adjustment", "title": "重大调整", "status": "not_reviewed", "route_suffix": "/eqcr/adjustments"},
        ]

    # ─── P2-2.2 区分普通复核与 EQCR 批注 ────────────────────────────────────

    def classify_annotation(self, annotation_type: str) -> str:
        """区分批注类型：普通复核 vs EQCR 独立复核。"""
        if annotation_type == AnnotationType.EQCR_INDEPENDENT:
            return "eqcr"
        return "normal"

    def create_eqcr_annotation(
        self,
        project_id: str,
        category: str,
        content: str,
        author_id: str,
        target_id: str | None = None,
        target_type: str | None = None,
    ) -> EqcrAnnotation:
        """创建 EQCR 独立复核批注 (Property 5: 不混入普通复核流)。"""
        from uuid import uuid4

        return EqcrAnnotation(
            id=str(uuid4()),
            project_id=project_id,
            category=category,
            content=content,
            annotation_type=AnnotationType.EQCR_INDEPENDENT,
            author_id=author_id,
            target_id=target_id,
            target_type=target_type,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    # ─── P2-2.3 建立 EQCR checklist ─────────────────────────────────────────

    def get_checklist_status(
        self,
        project_id: UUID,
        completed_items: list[str] | None = None,
    ) -> dict[str, Any]:
        """获取 EQCR checklist 当前状态。

        基于 EQCR_CHECKLIST_TEMPLATE 配置，合并已完成状态。
        """
        completed_set = set(completed_items or [])

        items = []
        by_category: dict[str, dict[str, int]] = {}

        for tmpl in EQCR_CHECKLIST_TEMPLATE:
            item = EqcrChecklistItem(
                id=tmpl["id"],
                category=tmpl["category"],
                title=tmpl["title"],
                description=tmpl.get("description"),
                required=tmpl.get("required", True),
                completed=tmpl["id"] in completed_set,
            )
            items.append(item.model_dump())

            cat = tmpl["category"]
            if cat not in by_category:
                by_category[cat] = {"total": 0, "completed": 0, "required_total": 0, "required_completed": 0}
            by_category[cat]["total"] += 1
            if tmpl["id"] in completed_set:
                by_category[cat]["completed"] += 1
            if tmpl.get("required", True):
                by_category[cat]["required_total"] += 1
                if tmpl["id"] in completed_set:
                    by_category[cat]["required_completed"] += 1

        total_required = sum(1 for t in EQCR_CHECKLIST_TEMPLATE if t.get("required", True))
        completed_required = sum(
            1 for t in EQCR_CHECKLIST_TEMPLATE
            if t.get("required", True) and t["id"] in completed_set
        )

        return {
            "project_id": str(project_id),
            "items": items,
            "by_category": by_category,
            "total": len(EQCR_CHECKLIST_TEMPLATE),
            "total_required": total_required,
            "completed_count": len(completed_set & {t["id"] for t in EQCR_CHECKLIST_TEMPLATE}),
            "completed_required": completed_required,
            "all_required_done": completed_required >= total_required,
        }

    # ─── P2-2.4 EQCR 签出要求 checklist 完成 ───────────────────────────────

    def can_sign_off(self, checklist_status: dict[str, Any]) -> bool:
        """检查 EQCR 是否可以签出 — 所有 required 项必须完成。"""
        return checklist_status.get("all_required_done", False)

    def attempt_sign_off(
        self,
        checklist_status: dict[str, Any],
    ) -> tuple[bool, str]:
        """尝试 EQCR 签出。

        Returns:
            (success, error_message)
        """
        if not self.can_sign_off(checklist_status):
            required_total = checklist_status.get("total_required", 0)
            completed_required = checklist_status.get("completed_required", 0)
            remaining = required_total - completed_required
            return False, f"EQCR checklist 尚有 {remaining} 项必填未完成，无法签出"
        return True, ""
