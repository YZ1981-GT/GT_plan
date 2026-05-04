"""系统字典 API — 枚举字典集中管理 [R4.1]

GET /api/system/dicts — 返回所有枚举字典
  响应格式: { [dictKey]: Array<{ value: str, label: str, color: str }> }
  color 对应 Element Plus el-tag type（success/warning/danger/info/空字符串）

前端启动时加载一次，sessionStorage 缓存，配合 useDictStore 使用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/system", tags=["system-dicts"])


# ── 字典定义（与前端 statusMaps.ts 保持一致） ──

_DICTS: dict[str, list[dict[str, str]]] = {
    # 底稿状态
    "wp_status": [
        {"value": "not_started",          "label": "未开始",       "color": "info"},
        {"value": "in_progress",          "label": "编制中",       "color": "warning"},
        {"value": "draft",                "label": "草稿",         "color": "warning"},
        {"value": "draft_complete",       "label": "初稿完成",     "color": ""},
        {"value": "edit_complete",        "label": "编制完成",     "color": ""},
        {"value": "under_review",         "label": "复核中",       "color": ""},
        {"value": "revision_required",    "label": "退回修改",     "color": "danger"},
        {"value": "review_passed",        "label": "复核通过",     "color": "success"},
        {"value": "review_level1_passed", "label": "一级复核通过", "color": "success"},
        {"value": "review_level2_passed", "label": "二级复核通过", "color": "success"},
        {"value": "archived",             "label": "已归档",       "color": "info"},
    ],
    # 底稿复核状态
    "wp_review_status": [
        {"value": "not_submitted",      "label": "未提交",     "color": "info"},
        {"value": "pending_level1",     "label": "待一级复核", "color": "warning"},
        {"value": "level1_in_progress", "label": "一级复核中", "color": "warning"},
        {"value": "level1_passed",      "label": "一级通过",   "color": "success"},
        {"value": "level1_rejected",    "label": "一级退回",   "color": "danger"},
        {"value": "pending_level2",     "label": "待二级复核", "color": "warning"},
        {"value": "level2_in_progress", "label": "二级复核中", "color": "warning"},
        {"value": "level2_passed",      "label": "二级通过",   "color": "success"},
        {"value": "level2_rejected",    "label": "二级退回",   "color": "danger"},
    ],
    # 调整分录状态
    "adjustment_status": [
        {"value": "draft",          "label": "草稿",   "color": "info"},
        {"value": "pending_review", "label": "待复核", "color": "warning"},
        {"value": "approved",       "label": "已批准", "color": "success"},
        {"value": "rejected",       "label": "已驳回", "color": "danger"},
    ],
    # 报告状态
    "report_status": [
        {"value": "draft",  "label": "草稿",   "color": "info"},
        {"value": "review", "label": "复核中", "color": "warning"},
        {"value": "final",  "label": "已定稿", "color": "success"},
    ],
    # 模板状态
    "template_status": [
        {"value": "draft",      "label": "草稿",   "color": "info"},
        {"value": "published",  "label": "已发布", "color": "success"},
        {"value": "deprecated", "label": "已废弃", "color": "danger"},
    ],
    # 项目状态
    "project_status": [
        {"value": "created",    "label": "已创建", "color": "info"},
        {"value": "planning",   "label": "计划中", "color": "warning"},
        {"value": "execution",  "label": "执行中", "color": ""},
        {"value": "completion", "label": "已完成", "color": "success"},
        {"value": "reporting",  "label": "报告",   "color": ""},
        {"value": "archived",   "label": "已归档", "color": "info"},
    ],
    # 问题工单状态
    "issue_status": [
        {"value": "open",            "label": "待处理", "color": "info"},
        {"value": "in_fix",          "label": "修复中", "color": "warning"},
        {"value": "pending_recheck", "label": "待复验", "color": "warning"},
        {"value": "closed",          "label": "已关闭", "color": "success"},
        {"value": "rejected",        "label": "已驳回", "color": "danger"},
    ],
    # PDF 导出任务状态
    "pdf_task_status": [
        {"value": "queued",     "label": "排队中", "color": "info"},
        {"value": "processing", "label": "处理中", "color": "warning"},
        {"value": "completed",  "label": "已完成", "color": "success"},
        {"value": "failed",     "label": "失败",   "color": "danger"},
    ],
}


@router.get("/dicts")
async def get_system_dicts(
    current_user: User = Depends(get_current_user),
):
    """返回所有枚举字典，前端启动时加载一次并缓存到 sessionStorage"""
    return _DICTS
