"""EQCR 常量端点（Improvement 13）"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/constants")
async def get_eqcr_constants():
    """返回 EQCR 模块使用的枚举常量，供前端下拉/校验使用。"""
    return {
        "domains": [
            "materiality",
            "estimate",
            "related_party",
            "going_concern",
            "opinion_type",
            "component_auditor",
        ],
        "verdicts": ["agree", "disagree", "need_more_evidence"],
        "progress_states": ["not_started", "in_progress", "approved", "disagree"],
    }
