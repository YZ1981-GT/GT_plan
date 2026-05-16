"""系统字典 API — 枚举字典集中管理 [R4.1]

GET /api/system/dicts — 返回所有枚举字典
  响应格式: { [dictKey]: Array<{ value: str, label: str, color: str }> }
  color 对应 Element Plus el-tag type（success/warning/danger/info/空字符串）

GET /api/system/dicts/{dict_key}/usage-count — 返回各枚举值的引用计数
  [template-library-coordination Sprint 6 Task 6.2 / 需求 21.4]

POST/PUT /api/system/dicts/{dict_key}/items — 拒绝写操作（D13 ADR：枚举字典硬编码在代码中）
  [template-library-coordination Sprint 6 Task 6.3 / 需求 21.3, 21.5]

前端启动时加载一次，sessionStorage 缓存，配合 useDictStore 使用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

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
        {"value": "draft",          "label": "草稿",       "color": "info"},
        {"value": "review",         "label": "复核中",     "color": "warning"},
        {"value": "eqcr_approved",  "label": "EQCR已锁",  "color": ""},
        {"value": "final",          "label": "已定稿",     "color": "success"},
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
    # 工时状态 [R7-S2-06]
    "workhour_status": [
        {"value": "draft",     "label": "草稿",   "color": "info"},
        {"value": "tracking",  "label": "计时中", "color": "warning"},
        {"value": "confirmed", "label": "已确认", "color": ""},
        {"value": "approved",  "label": "已审批", "color": "success"},
        {"value": "rejected",  "label": "已退回", "color": "danger"},
    ],
}


@router.get("/dicts")
async def get_system_dicts(
    current_user: User = Depends(get_current_user),
):
    """返回所有枚举字典，前端启动时加载一次并缓存到 sessionStorage"""
    return _DICTS


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.2 — 枚举引用计数端点
# ──────────────────────────────────────────────────────────────────────────

# 字典键 → 数据源映射（表名 + 列名 + 可选过滤条件）
# 每个 dict_key 对应一条 SQL：SELECT col, COUNT(*) FROM table [WHERE ...] GROUP BY col
# 表/列必须与实际 DB schema 对齐（已 grep 核验：models/workpaper_models / audit_platform_models /
# report_models / phase15_models / core / staff_models）
_USAGE_COUNT_QUERIES: dict[str, dict[str, str]] = {
    "wp_status": {
        "table": "working_paper",
        "column": "status",
        "where": "is_deleted = false",
    },
    "wp_review_status": {
        "table": "working_paper",
        "column": "review_status",
        "where": "is_deleted = false",
    },
    "adjustment_status": {
        "table": "adjustments",
        "column": "status",
        "where": "is_deleted = false",
    },
    "report_status": {
        "table": "audit_report",
        "column": "status",
        "where": "is_deleted = false",
    },
    "project_status": {
        "table": "projects",
        "column": "status",
        "where": "is_deleted = false",
    },
    "issue_status": {
        "table": "issue_tickets",
        "column": "status",
        "where": "",
    },
    "workhour_status": {
        "table": "work_hours",
        "column": "status",
        "where": "",
    },
    # 以下字典暂无对应业务表（template_status 由代码维护，pdf_task_status 是临时任务态），
    # 返回全部 0，保持响应结构一致。
    "template_status": {
        "table": "",
        "column": "",
        "where": "",
    },
    "pdf_task_status": {
        "table": "",
        "column": "",
        "where": "",
    },
}


@router.get("/dicts/{dict_key}/usage-count")
async def get_dict_usage_count(
    dict_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回某字典各枚举值的引用计数。

    Response: `[{"value": "draft", "count": 12}, {"value": "approved", "count": 0}, ...]`

    - 字典中所有枚举值都会出现在响应中（即使 count=0），方便前端 UI 直接 join
    - 不存在对应业务表的字典返回全部 0
    - 单条查询失败（表不存在/列不存在）时记录 warning 并返回该字典全部 0
    """
    if dict_key not in _DICTS:
        raise HTTPException(status_code=404, detail={"error_code": "DICT_NOT_FOUND", "dict_key": dict_key})

    entries = _DICTS[dict_key]
    # 默认全部 0（保证响应结构稳定）
    counts: dict[str, int] = {e["value"]: 0 for e in entries}

    cfg = _USAGE_COUNT_QUERIES.get(dict_key)
    if cfg and cfg["table"]:
        sql = f"SELECT {cfg['column']} AS v, COUNT(*) AS c FROM {cfg['table']}"
        if cfg["where"]:
            sql += f" WHERE {cfg['where']}"
        sql += f" GROUP BY {cfg['column']}"
        try:
            result = await db.execute(text(sql))
            for row in result.fetchall():
                value = str(row[0]) if row[0] is not None else ""
                if value in counts:
                    counts[value] = int(row[1] or 0)
        except Exception as exc:
            # 失败时回滚事务避免后续查询全部失败（asyncpg session 污染）
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning(
                "usage_count query failed for dict_key=%s table=%s column=%s: %s",
                dict_key, cfg["table"], cfg["column"], exc,
            )

    return [{"value": v, "count": c} for v, c in counts.items()]


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.3 — 枚举项 CRUD 端点（拒绝写操作 / D13 ADR）
# ──────────────────────────────────────────────────────────────────────────

_DICT_HARDCODED_HINT = (
    "枚举字典当前为代码定义（backend/app/routers/system_dicts.py 中的 _DICTS），"
    "如需新增/修改/禁用枚举项请提交 PR 编辑 _DICTS 字典后重启后端。"
    "已被引用的值不允许物理删除，只能在代码中标记为 deprecated/disabled。"
)


@router.post("/dicts/{dict_key}/items", status_code=405)
async def reject_dict_item_create(dict_key: str):
    """拒绝新增枚举项 — 字典硬编码在代码中（D13 ADR）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "ENUM_DICT_HARDCODED",
            "dict_key": dict_key,
            "hint": _DICT_HARDCODED_HINT,
        },
    )


@router.put("/dicts/{dict_key}/items/{item_value}", status_code=405)
async def reject_dict_item_update(dict_key: str, item_value: str):
    """拒绝修改枚举项 — 字典硬编码在代码中（D13 ADR）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "ENUM_DICT_HARDCODED",
            "dict_key": dict_key,
            "item_value": item_value,
            "hint": _DICT_HARDCODED_HINT,
        },
    )


@router.delete("/dicts/{dict_key}/items/{item_value}", status_code=405)
async def reject_dict_item_delete(dict_key: str, item_value: str):
    """拒绝删除枚举项 — 字典硬编码在代码中（D13 ADR）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "ENUM_DICT_HARDCODED",
            "dict_key": dict_key,
            "item_value": item_value,
            "hint": _DICT_HARDCODED_HINT,
        },
    )
