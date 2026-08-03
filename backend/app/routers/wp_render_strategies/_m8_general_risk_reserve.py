"""M8 一般风险准备 — 专属渲染策略.

component_type = "m8-general-risk-reserve"

M8 前端组件 GtM8GeneralRiskReserve 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/风险测试/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M8 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

一般风险准备（**贷方/权益类！**）：期末=期初+贷方-借方
M股东权益循环中的权益类科目。从净利润计提时贷方增加，转回/使用时借方减少。
金融企业（银行/证券/保险）专属。按风险资产期末余额1.5%计提测试。
数据持久化在 checklist_responses 表，item_id 前缀为 "M8-*"。

🔴 **2026-08-03 修掉的科目定位缺陷**：本模块原先硬编码 `_M8_ACCOUNT_CODE = "4302"`
并按 `LIKE '4302%'` 取数，而 **`4302` 在 `account_chart` 两张表（10 个项目）里都不存在**
→ `tb_snapshot` **恒为空**（表现为「本项目没有一般风险准备」，不报错、不崩溃）。
本文件 docstring 原写「科目4104」也是错的（`4104` client/standard 双侧都是**利润分配**）。

现改走 `four_table.m_cycle_specs.M8_SPEC` 语义定位：按科目名「一般风险准备」在本项目
科目表里找。全库确实没有该名科目 → `found=False`，`tb_snapshot` 为空**且溯源如实说明
「本项目无此科目」**（宁缺勿造），而不是让审计师以为取数坏了。
报表行 `BS-124 △一般风险准备`（仅 soe，公式为 None）。

Requirements: 1.1-1.11
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.m_cycle_specs import M8_SPEC
from app.services.four_table.semantic_account_resolver import (
    resolve_semantic_accounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

_ADJUDICATED_ITEM_ID = "M8-1-adjudicated-amount"

M8_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "一般风险准备实质性程序表M8A", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "审定表M8-1", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "明细表M8-2", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "调整分录汇总M8-3", "component_type": "m8-general-risk-reserve"},
    {"sheet_name": "一般风险准备测试表M8-4", "component_type": "m8-general-risk-reserve"},
]


# ─── 权益类公式验证（纯函数，可独立测试）─────────────────────────────────────

TOLERANCE = 0.01


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN check
    except (ValueError, TypeError):
        return 0.0


async def render(ctx: RenderContext) -> dict[str, Any]:
    """返回 M8 一般风险准备轻量 html_data.

    前端自加载模式：子组件各自拉 checklist-responses，
    本函数仅返回 project_context（行业信息）+ tb_snapshot（一般风险准备余额）。
    """
    db = ctx.db
    project_id = ctx.project_id

    # ── 语义定位科目（不再硬编码 `4302`，该码全库不存在）─────────────────
    accounts = await resolve_semantic_accounts(ctx, M8_SPEC)
    gross_codes = accounts.codes_of("gross")

    # ── 取 TB 余额 ──────────────────────────────────────────────────────
    tb_data: dict[str, Any] = {}
    if gross_codes:
        try:
            active_filter = await get_active_filter(
                ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
            )
            stmt = sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance.label("begin_balance"),
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_balance.label("end_balance"),
            ).where(
                TbBalance.project_id == str(project_id),
                sa.or_(
                    *[TbBalance.account_code.startswith(c) for c in gross_codes]
                ),
                active_filter,
            )
            result = await db.execute(stmt)
            for row in result.fetchall():
                tb_data[row.account_code] = {
                    "begin_balance": _parse_num(row.begin_balance),
                    "end_balance": _parse_num(row.end_balance),
                    "debit_amount": _parse_num(row.debit_amount),
                    "credit_amount": _parse_num(row.credit_amount),
                }
        except Exception as exc:
            logger.warning("[M8 render] TB query failed: %s", exc)

    # ── 取项目行业信息（用于行业守卫） ───────────────────────────────────
    project_info: dict[str, Any] = {}
    try:
        from app.models.audit_platform_models import Project
        result = await db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        proj = result.scalar_one_or_none()
        if proj:
            project_info = {
                "industry": getattr(proj, "industry", "") or "",
                "client_industry": getattr(proj, "client_industry", "") or "",
                "client_name": getattr(proj, "client_name", "") or "",
            }
    except Exception as exc:
        logger.warning("[M8 render] Project query failed: %s", exc)

    return {
        "component_type": "m8-general-risk-reserve",
        "sheets": M8_SHEETS,
        "tb_snapshot": tb_data,
        "project_info": project_info,
        # 解析出的科目码（空列表 = 本项目无「一般风险准备」科目，宁缺勿造）
        "account_codes": gross_codes,
        "tb_source_codes": accounts.as_dict(),
        "direction": "credit",  # 权益类贷方
    }
