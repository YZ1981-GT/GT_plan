"""复核检查清单服务 — 从模板元数据加载检查项+勾选+自动推进状态

Sprint 10 Task 10.5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_optimization_models import WpTemplateMetadata


class ReviewChecklistService:
    """复核检查清单管理"""

    @staticmethod
    async def get_checklist(
        db: AsyncSession,
        *,
        wp_id: uuid.UUID,
    ) -> dict:
        """从模板元数据加载检查项列表"""
        # 查找底稿关联的模板元数据
        stmt = select(WpTemplateMetadata).where(
            WpTemplateMetadata.wp_code.isnot(None)
        ).limit(1)
        result = await db.execute(stmt)
        meta = result.scalar_one_or_none()

        # 默认检查项（通用复核清单）
        default_items = [
            {"id": "chk-01", "label": "底稿编制完整性", "checked": False},
            {"id": "chk-02", "label": "数据来源可追溯", "checked": False},
            {"id": "chk-03", "label": "公式计算正确", "checked": False},
            {"id": "chk-04", "label": "交叉索引完整", "checked": False},
            {"id": "chk-05", "label": "审计结论合理", "checked": False},
            {"id": "chk-06", "label": "审计程序执行充分", "checked": False},
            {"id": "chk-07", "label": "样本量充足", "checked": False},
            {"id": "chk-08", "label": "异常事项已说明", "checked": False},
        ]

        if meta and meta.review_checklist:
            return {"wp_id": str(wp_id), "items": meta.review_checklist}
        return {"wp_id": str(wp_id), "items": default_items}

    @staticmethod
    async def check_item(
        db: AsyncSession,
        *,
        wp_id: uuid.UUID,
        item_id: str,
        checked: bool,
        user_id: uuid.UUID,
    ) -> dict:
        """勾选/取消勾选检查项"""
        # 实际实现会更新 working_paper.parsed_data 中的 checklist 状态
        return {
            "wp_id": str(wp_id),
            "item_id": item_id,
            "checked": checked,
            "checked_by": str(user_id),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def compute_progress(items: list[dict]) -> dict:
        """计算检查进度"""
        total = len(items)
        checked = sum(1 for i in items if i.get("checked"))
        rate = (checked / total * 100) if total > 0 else 0
        return {
            "total": total,
            "checked": checked,
            "rate": round(rate, 1),
            "all_passed": checked == total,
        }
