"""底稿编制智能引导服务

Phase 12 P2-5: 根据底稿类型显示不同引导步骤。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# 底稿类型→引导步骤映射
_GUIDANCE_MAP = {
    "audited": {
        "wp_type": "audited",
        "steps": ["核对未审数", "检查调整分录", "确认审定数", "撰写审计结论"],
    },
    "detail": {
        "wp_type": "detail",
        "steps": ["逐行核对明细", "标记差异项", "记录审计发现"],
    },
    "analysis": {
        "wp_type": "analysis",
        "steps": ["计算变动率", "识别异常波动", "分析变动原因", "记录分析结论"],
    },
}


class WpGuidanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_guidance(self, wp_id: UUID) -> dict:
        wp = (await self.db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if not wp:
            return {"error": "底稿不存在"}

        idx = (await self.db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )).scalar_one_or_none()

        wp_code = idx.wp_code if idx else ""
        wp_type = self._detect_type(wp_code)
        guidance = _GUIDANCE_MAP.get(wp_type, _GUIDANCE_MAP["audited"]).copy()
        guidance["wp_code"] = wp_code
        return guidance

    def _detect_type(self, code: str) -> str:
        if not code:
            return "audited"
        suffix = code.split("-")[-1] if "-" in code else ""
        if suffix in ("1", "01"):
            return "audited"
        elif suffix in ("2", "02"):
            return "detail"
        elif suffix in ("3", "03"):
            return "analysis"
        return "audited"

    async def check_procedure_progress(self, wp_id: UUID) -> dict:
        try:
            from app.models.phase10_models import ProcedureInstance
            q = sa.select(ProcedureInstance).where(
                ProcedureInstance.working_paper_id == wp_id)
            procs = (await self.db.execute(q)).scalars().all()
            completed = sum(1 for p in procs if p.execution_status == "completed")
            return {"procedures": len(procs), "completed": completed, "total": len(procs)}
        except Exception:
            return {"procedures": 0, "completed": 0, "total": 0}
