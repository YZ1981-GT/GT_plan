"""S34 核查事项清单服务 — 返回 S34ChecklistItem[] 含 regRef/applicability/status.

数据源：S34-0 核查事项清单（静态 regRef 映射 + 动态适用性/完成状态从 wp_index 查询）。
regRef 映射来自 s34_structure_reference.md Section 六。

Requirements: 3.2, 9.1, 12.1
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 静态 regRef 映射数据（来源 S34-0 核查事项清单 行3~54）
# ═══════════════════════════════════════════════════════════════════════════════

S34_CHECKLIST_DATA: list[dict[str, Any]] = [
    {
        "seq": 1,
        "wp_code": "S34-1",
        "name": "军工等涉秘业务企业信息披露豁免",
        "reg_ref": {"csrc": None, "sse": "2-6", "szse": "15-1", "bse": "1-23", "title": "军工等涉秘业务企业信息披露豁免"},
    },
    {
        "seq": 2,
        "wp_code": "S34-2",
        "name": "期权激励计划",
        "reg_ref": {"csrc": None, "sse": "2-5", "szse": "10-1/2/3", "bse": None, "title": "期权激励计划"},
    },
    {
        "seq": 3,
        "wp_code": "S34-3",
        "name": "股份支付",
        "reg_ref": {"csrc": "5-1", "sse": "3-1", "szse": "29-1", "bse": "2-25", "title": "股份支付"},
    },
    {
        "seq": 4,
        "wp_code": "S34-4",
        "name": "关联交易",
        "reg_ref": {"csrc": "4-11", "sse": "2-17/2-30/3-21", "szse": "22-1/6-1/22-3", "bse": "1-13", "title": "关联交易"},
    },
    {
        "seq": 5,
        "wp_code": "S34-5",
        "name": "应收款项减值",
        "reg_ref": {"csrc": "5-2", "sse": "3-2", "szse": "32-1", "bse": "2-22", "title": "应收款项减值"},
    },
    {
        "seq": 6,
        "wp_code": "S34-6",
        "name": "固定资产使用及减值",
        "reg_ref": {"csrc": None, "sse": "3-32", "szse": "35-1", "bse": None, "title": "固定资产使用及减值"},
    },
    {
        "seq": 7,
        "wp_code": "S34-7",
        "name": "税收优惠",
        "reg_ref": {"csrc": "5-6", "sse": "3-6", "szse": "30-1", "bse": "2-24", "title": "税收优惠"},
    },
    {
        "seq": 8,
        "wp_code": "S34-8",
        "name": "合并中无形资产认定与客户关系",
        "reg_ref": {"csrc": "5-3", "sse": "3-3", "szse": "36-2", "bse": "2-26", "title": "合并中无形资产认定与客户关系"},
    },
    {
        "seq": 9,
        "wp_code": "S34-9",
        "name": "共同投资",
        "reg_ref": {"csrc": "4-15", "sse": "2-21", "szse": "22-2", "bse": "1-16", "title": "共同投资"},
    },
    {
        "seq": 10,
        "wp_code": "S34-10",
        "name": "财务性投资",
        "reg_ref": {"csrc": None, "sse": "3-34", "szse": "34-1", "bse": None, "title": "财务性投资"},
    },
    {
        "seq": 11,
        "wp_code": "S34-11",
        "name": "业务重组",
        "reg_ref": {"csrc": None, "sse": "3-36", "szse": "3-1", "bse": None, "title": "业务重组"},
    },
    {
        "seq": 12,
        "wp_code": "S34-12",
        "name": "经营业绩下滑",
        "reg_ref": {"csrc": None, "sse": None, "szse": None, "bse": "2-9", "title": "经营业绩下滑"},
    },
    {
        "seq": 13,
        "wp_code": "S34-13",
        "name": "持续经营能力",
        "reg_ref": {"csrc": "5-7", "sse": "3-7", "szse": "14-1", "bse": "2-7", "title": "持续经营能力"},
    },
    {
        "seq": 14,
        "wp_code": "S34-14",
        "name": "财务内控",
        "reg_ref": {"csrc": "5-8", "sse": "3-8", "szse": "25-1", "bse": "2-10", "title": "财务内控"},
    },
    {
        "seq": 15,
        "wp_code": "S34-15",
        "name": "现金交易",
        "reg_ref": {"csrc": "5-10", "sse": "3-10", "szse": "26-8", "bse": "2-11", "title": "现金交易"},
    },
    {
        "seq": 16,
        "wp_code": "S34-16",
        "name": "第三方回款",
        "reg_ref": {"csrc": "5-11", "sse": "3-11", "szse": "26-7", "bse": "2-12", "title": "第三方回款"},
    },
    {
        "seq": 17,
        "wp_code": "S34-17",
        "name": "会计政策变更和差错更正",
        "reg_ref": {"csrc": "5-9", "sse": "3-9", "szse": "24-1", "bse": "2-5", "title": "会计政策变更和差错更正"},
    },
    {
        "seq": 18,
        "wp_code": "S34-18",
        "name": "引用第三方数据",
        "reg_ref": {"csrc": None, "sse": "4-4", "szse": "15-2", "bse": "1-24", "title": "引用第三方数据"},
    },
    {
        "seq": 19,
        "wp_code": "S34-19",
        "name": "经销商模式",
        "reg_ref": {"csrc": "5-12", "sse": "3-12", "szse": "26-2", "bse": "2-15", "title": "经销商模式"},
    },
    {
        "seq": 20,
        "wp_code": "S34-20",
        "name": "劳务外包",
        "reg_ref": {"csrc": None, "sse": "3-22", "szse": "27-2", "bse": None, "title": "劳务外包"},
    },
    {
        "seq": 21,
        "wp_code": "S34-21",
        "name": "委外加工",
        "reg_ref": {"csrc": None, "sse": "3-23", "szse": None, "bse": None, "title": "委外加工"},
    },
    {
        "seq": 22,
        "wp_code": "S34-22",
        "name": "股权集中企业治理",
        "reg_ref": {"csrc": None, "sse": None, "szse": None, "bse": "1-15", "title": "股权集中企业治理"},
    },
    {
        "seq": 23,
        "wp_code": "S34-23",
        "name": "互联网业务信息系统核查",
        "reg_ref": {"csrc": "5-13", "sse": "3-13", "szse": "26-4", "bse": "2-16", "title": "互联网业务信息系统核查"},
    },
    {
        "seq": 24,
        "wp_code": "S34-24",
        "name": "信息系统专项核查",
        "reg_ref": {"csrc": "5-14", "sse": "3-14", "szse": "25-2", "bse": "2-17", "title": "信息系统专项核查"},
    },
    {
        "seq": 25,
        "wp_code": "S34-25",
        "name": "资金流水核查",
        "reg_ref": {"csrc": "5-15", "sse": "3-15", "szse": "25-3", "bse": "2-18", "title": "资金流水核查"},
    },
    {
        "seq": 26,
        "wp_code": "S34-26",
        "name": "尚未盈利/累计未弥补亏损",
        "reg_ref": {"csrc": "5-16", "sse": "3-16", "szse": "31-1", "bse": "2-19", "title": "尚未盈利/累计未弥补亏损"},
    },
    {
        "seq": 27,
        "wp_code": "S34-27",
        "name": "研发投入的认定及内控",
        "reg_ref": {"csrc": "9-1", "sse": "1-4/1-5/2-26", "szse": "29-3/29-4", "bse": "2-4", "title": "研发投入的认定及内控"},
    },
    {
        "seq": 28,
        "wp_code": "S34-28",
        "name": "研发支出资本化",
        "reg_ref": {"csrc": "5-4", "sse": "3-4", "szse": "36-1", "bse": None, "title": "研发支出资本化"},
    },
    {
        "seq": 29,
        "wp_code": "S34-29",
        "name": "科研项目政府补助",
        "reg_ref": {"csrc": "5-5", "sse": "3-5", "szse": "30-3", "bse": "2-23", "title": "科研项目政府补助"},
    },
    {
        "seq": 30,
        "wp_code": "S34-30",
        "name": "对赌协议",
        "reg_ref": {"csrc": "4-3", "sse": "2-9", "szse": "2-1-3", "bse": None, "title": "对赌协议"},
    },
    {
        "seq": 31,
        "wp_code": "S34-31",
        "name": "存货",
        "reg_ref": {"csrc": None, "sse": "3-30", "szse": "33-1/2/27-1", "bse": None, "title": "存货"},
    },
    {
        "seq": 32,
        "wp_code": "S34-32",
        "name": "期间费用核查",
        "reg_ref": {"csrc": None, "sse": "3-28", "szse": "29-2", "bse": None, "title": "期间费用核查"},
    },
    {
        "seq": 33,
        "wp_code": "S34-33",
        "name": "商誉减值",
        "reg_ref": {"csrc": None, "sse": "3-33", "szse": "37-1", "bse": None, "title": "商誉减值"},
    },
    {
        "seq": 34,
        "wp_code": "S34-34",
        "name": "涉农企业",
        "reg_ref": {"csrc": None, "sse": "4-9", "szse": "13-4", "bse": "2-14", "title": "涉农企业"},
    },
    {
        "seq": 35,
        "wp_code": "S34-35",
        "name": "收入核查",
        "reg_ref": {"csrc": None, "sse": "3-24/3-25/3-26/3-27", "szse": "23-1/26-1/5/26-3/28-1/26-6", "bse": "2-13", "title": "收入核查"},
    },
    {
        "seq": 36,
        "wp_code": "S34-36",
        "name": "投资收益占比",
        "reg_ref": {"csrc": "5-18", "sse": "3-18", "szse": "30-4", "bse": "2-21", "title": "投资收益占比"},
    },
    {
        "seq": 37,
        "wp_code": "S34-37",
        "name": "现金流异常",
        "reg_ref": {"csrc": None, "sse": None, "szse": "38-1", "bse": None, "title": "现金流异常"},
    },
    {
        "seq": 38,
        "wp_code": "S34-38",
        "name": "估值调整协议",
        "reg_ref": {"csrc": None, "sse": None, "szse": None, "bse": "1-3", "title": "估值调整协议"},
    },
    {
        "seq": 39,
        "wp_code": "S34-39",
        "name": "应收票据和应收款项融资",
        "reg_ref": {"csrc": None, "sse": "3-29", "szse": "32-2", "bse": None, "title": "应收票据和应收款项融资"},
    },
    {
        "seq": 40,
        "wp_code": "S34-40",
        "name": "在建工程",
        "reg_ref": {"csrc": None, "sse": "3-31", "szse": "35-2", "bse": None, "title": "在建工程"},
    },
    {
        "seq": 41,
        "wp_code": "S34-41",
        "name": "主要客户和供应商",
        "reg_ref": {"csrc": "5-17", "sse": "3-17/3-19/3-20", "szse": "16-1/2/3/4/17-1/2/4", "bse": "2-8", "title": "主要客户和供应商"},
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# 服务函数
# ═══════════════════════════════════════════════════════════════════════════════


def _wp_status_to_completion(status: str | None) -> str:
    """将 wp_index.status 映射到 completion status."""
    if status in ("draft_complete", "review_passed", "archived"):
        return "completed"
    elif status == "in_progress":
        return "in_progress"
    else:
        return "not_started"


async def get_s34_checklist(
    project_id: UUID,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """获取 S34 核查事项清单，附带适用性与完成状态.

    逻辑：
    1. 加载静态 S34_CHECKLIST_DATA（41 项 regRef 映射）
    2. 查询 wp_index 获取当前项目下 S34-* 底稿的 wp_id 与 status
    3. 有 wp_id → applicable，无 → not_applicable
    4. status 映射为 completed / in_progress / not_started

    Returns:
        list[S34ChecklistItem dict]
    """
    # 查询项目内所有 S34-* 底稿的 wp_code → (id, status)
    result = await db.execute(
        sa.text(
            "SELECT wp_code, id, status "
            "FROM wp_index "
            "WHERE project_id = :project_id "
            "  AND wp_code LIKE 'S34-%' "
            "  AND is_deleted = false"
        ),
        {"project_id": str(project_id)},
    )
    rows = result.fetchall()

    # 构建 wp_code → {wp_id, status} 映射
    wp_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        wp_map[row[0]] = {"wp_id": str(row[1]), "status": row[2]}

    # 组装结果
    checklist: list[dict[str, Any]] = []
    for item in S34_CHECKLIST_DATA:
        wp_code = item["wp_code"]
        wp_info = wp_map.get(wp_code)

        if wp_info:
            applicability = "applicable"
            status = _wp_status_to_completion(wp_info["status"])
        else:
            applicability = "not_applicable"
            status = "not_started"

        checklist.append({
            "seq": item["seq"],
            "wp_code": wp_code,
            "name": item["name"],
            "reg_ref": item["reg_ref"],
            "applicability": applicability,
            "status": status,
        })

    return checklist
