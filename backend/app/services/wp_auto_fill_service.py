"""底稿自动刷数服务 — 批量解析 cross_refs 中 source 标记的 cell 取值

从 TB/WP/REPORT 批量取数，返回 fill_results 含 value + source + label + status。
性能目标：≤200ms 完成批量取数。

优化策略：按 source_type 分组后单次 IN 查询批量取数，避免 N+1 问题。
6000 并发场景下，20 个 cross_refs 仅需 ≤3 次 DB 查询（每种 source_type 最多 1 次）。

锚定 spec workpaper-editor-slimdown Task 16.2
Validates: US-15（HTML 底稿自动刷数）
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance

logger = logging.getLogger(__name__)


# ─── 主入口（批量模式） ────────────────────────────────────────────────────────

async def _resolve_auto_fill_values(
    schema: dict,
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> dict[str, dict[str, Any]]:
    """批量解析 schema 中 source 标记的 cell，从 TB/WP/REPORT 取值。

    优化：按 source_type 分组 → 每种类型单次 IN 查询 → 内存 lookup 解析。
    20 个 cross_refs 最多 3 次 DB 查询（TB/WP/REPORT 各 1 次）。

    Args:
        schema: render_schema YAML 解析后的 dict（含 sheets.*.cross_refs）
        project_id: 项目 UUID
        year: 会计年度
        db: 数据库 session

    Returns:
        fill_results: {
            "sheet_name!cell": {
                "value": <number|str|None>,
                "source": "TB:1122:期末",
                "label": "应收账款期末余额",
                "status": "ok" | "unavailable"
            }
        }
    """
    start_time = time.monotonic()

    # 1. Collect all refs
    all_refs = _collect_all_refs(schema)
    if not all_refs:
        return {}

    # 2. Group by source type
    tb_refs = [r for r in all_refs if r["source_type"] == "TB"]
    wp_refs = [r for r in all_refs if r["source_type"] == "WP"]
    report_refs = [r for r in all_refs if r["source_type"] == "REPORT"]

    # 3. Batch fetch (1 query per source type)
    tb_cache = await _batch_fetch_tb(tb_refs, project_id, year, db) if tb_refs else {}
    wp_cache = await _batch_fetch_wp(wp_refs, project_id, db) if wp_refs else {}
    report_cache = await _batch_fetch_report(report_refs, project_id, year, db) if report_refs else {}

    # 4. Resolve from cache (no DB)
    fill_results: dict[str, dict[str, Any]] = {}
    for ref in all_refs:
        value = _resolve_from_cache(ref, tb_cache, wp_cache, report_cache)
        fill_results[ref["key"]] = {
            "value": _serialize_value(value),
            "source": ref["source"],
            "label": ref["label"],
            "status": "ok" if value is not None else "unavailable",
        }

    elapsed_ms = (time.monotonic() - start_time) * 1000
    logger.debug(
        "Auto-fill resolved %d values in %.1fms for project %s (TB:%d WP:%d REPORT:%d)",
        len(fill_results), elapsed_ms, project_id,
        len(tb_refs), len(wp_refs), len(report_refs),
    )

    return fill_results


# ─── 第一步：收集所有 refs ──────────────────────────────────────────────────────

def _collect_all_refs(schema: dict) -> list[dict[str, Any]]:
    """从 schema 中提取所有有效的 cross_ref，解析 source 字符串。"""
    refs: list[dict[str, Any]] = []
    sheets = schema.get("sheets", {})
    if not sheets:
        return refs

    for sheet_name, sheet_schema in sheets.items():
        if not isinstance(sheet_schema, dict):
            continue
        cross_refs = sheet_schema.get("cross_refs", [])
        if not cross_refs:
            continue

        for ref in cross_refs:
            if not isinstance(ref, dict):
                continue
            source = ref.get("source", "")
            cell = ref.get("cell", "")
            label = ref.get("label", "")

            if not source or not cell:
                continue

            parts = source.split(":")
            if len(parts) < 2:
                continue

            source_type = parts[0].upper()
            refs.append({
                "key": f"{sheet_name}!{cell}",
                "source": source,
                "source_type": source_type,
                "parts": parts,
                "label": label,
            })

    return refs


# ─── 批量取数：TB ──────────────────────────────────────────────────────────────

# 字段映射：中文 → ORM 字段名
_TB_FIELD_MAP = {
    "期末": "closing_balance",
    "期初": "opening_balance",
    "借方": "debit_amount",
    "贷方": "credit_amount",
    "审定数": "audited_amount",
    "调整后": "audited_amount",
    "未审数": "unadjusted_amount",
    # 英文 fallback
    "closing_balance": "closing_balance",
    "opening_balance": "opening_balance",
    "debit_amount": "debit_amount",
    "credit_amount": "credit_amount",
    "audited_amount": "audited_amount",
}


async def _batch_fetch_tb(
    refs: list[dict],
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """单次 IN 查询批量获取 TB 数据。

    Returns:
        {account_code: row_object} 映射
    """
    account_codes = list({r["parts"][1] for r in refs if len(r["parts"]) >= 3})
    if not account_codes:
        return {}

    try:
        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        return {row.standard_account_code: row for row in result.scalars()}
    except Exception as e:
        logger.warning("Batch TB fetch error: %s", e)
        return {}


# ─── 批量取数：WP ──────────────────────────────────────────────────────────────

async def _batch_fetch_wp(
    refs: list[dict],
    project_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """单次 IN 查询批量获取 WP 数据。

    Returns:
        {wp_code: wp_object} 映射
    """
    wp_codes = list({r["parts"][1] for r in refs if len(r["parts"]) >= 4})
    if not wp_codes:
        return {}

    try:
        from app.models.workpaper_models import WorkingPaper, WpIndex

        result = await db.execute(
            sa.select(WorkingPaper, WpIndex.wp_code)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.wp_code.in_(wp_codes),
                WpIndex.project_id == project_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        return {wp_code: wp for wp, wp_code in result}
    except Exception as e:
        logger.warning("Batch WP fetch error: %s", e)
        return {}


# ─── 批量取数：REPORT ─────────────────────────────────────────────────────────

async def _batch_fetch_report(
    refs: list[dict],
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """单次 IN 查询批量获取 REPORT 数据。

    Returns:
        {row_code: row_object} 映射
    """
    row_codes = list({r["parts"][1] for r in refs if len(r["parts"]) >= 2})
    if not row_codes:
        return {}

    try:
        from app.models.report_models import FinancialReport

        result = await db.execute(
            sa.select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.row_code.in_(row_codes),
                FinancialReport.is_deleted == sa.false(),
            )
        )
        return {row.row_code: row for row in result.scalars()}
    except Exception as e:
        logger.warning("Batch REPORT fetch error: %s", e)
        return {}


# ─── 从缓存解析值（纯内存，无 DB） ────────────────────────────────────────────

def _resolve_from_cache(
    ref: dict,
    tb_cache: dict[str, Any],
    wp_cache: dict[str, Any],
    report_cache: dict[str, Any],
) -> Decimal | str | None:
    """从预取缓存中解析单个 ref 的值。"""
    source_type = ref["source_type"]
    parts = ref["parts"]

    try:
        if source_type == "TB":
            return _resolve_tb_from_cache(parts, tb_cache)
        elif source_type == "WP":
            return _resolve_wp_from_cache(parts, wp_cache)
        elif source_type == "REPORT":
            return _resolve_report_from_cache(parts, report_cache)
        else:
            return None
    except Exception as e:
        logger.warning("Auto-fill resolve error for source=%s: %s", ref["source"], e)
        return None


def _resolve_tb_from_cache(
    parts: list[str],
    tb_cache: dict[str, Any],
) -> Decimal | None:
    """TB:account_code:field → 从缓存取值"""
    if len(parts) < 3:
        return None

    account_code = parts[1]
    field_name = parts[2]
    orm_field = _TB_FIELD_MAP.get(field_name, field_name)

    row = tb_cache.get(account_code)
    if row is None:
        return None

    val = getattr(row, orm_field, None)
    return Decimal(str(val)) if val is not None else None


def _resolve_wp_from_cache(
    parts: list[str],
    wp_cache: dict[str, Any],
) -> str | Decimal | None:
    """WP:wp_code:sheet:cell → 从缓存取值"""
    if len(parts) < 4:
        return None

    wp_code = parts[1]
    sheet_name = parts[2]
    cell_ref = parts[3]

    wp = wp_cache.get(wp_code)
    if wp is None or not wp.parsed_data:
        return None

    # 从 html_data 中取值
    html_data = wp.parsed_data.get("html_data", {})
    sheet_data = html_data.get(sheet_name, {})

    # cell_ref 格式如 "B7" → 从 cells dict 取值
    cells = sheet_data.get("cells", {})
    if cell_ref in cells:
        cell_val = cells[cell_ref]
        if isinstance(cell_val, dict):
            return cell_val.get("value") or cell_val.get("v")
        return cell_val

    return None


def _resolve_report_from_cache(
    parts: list[str],
    report_cache: dict[str, Any],
) -> Decimal | None:
    """REPORT:row_code:field → 从缓存取值"""
    if len(parts) < 3:
        return None

    row_code = parts[1]
    field_name = parts[2] if len(parts) > 2 else "amount"

    row = report_cache.get(row_code)
    if row is None:
        return None

    val = getattr(row, field_name, None)
    return Decimal(str(val)) if val is not None else None


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _serialize_value(value: Any) -> Any:
    """将 Decimal 等类型序列化为 JSON 兼容格式"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        # 保留精度，返回 float
        return float(value)
    return value


# ─── 单条 fallback（保留兼容，重命名加 _single_ 前缀） ─────────────────────────

async def _single_fetch_source_value(
    source: str,
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> Decimal | str | None:
    """解析 source 字符串并从对应数据源取值（单条查询 fallback）。

    source 格式：
    - "TB:account_code:field"  → 试算表取数（field: 期末/期初/借方/贷方/审定数）
    - "WP:wp_code:sheet:cell"  → 其他底稿取数
    - "REPORT:row_code:field"  → 报表取数
    """
    parts = source.split(":")
    if len(parts) < 2:
        return None

    source_type = parts[0].upper()

    try:
        if source_type == "TB":
            return await _single_fetch_tb_value(parts, project_id, year, db)
        elif source_type == "WP":
            return await _single_fetch_wp_value(parts, project_id, db)
        elif source_type == "REPORT":
            return await _single_fetch_report_value(parts, project_id, year, db)
        else:
            logger.warning("Unknown auto-fill source type: %s", source_type)
            return None
    except Exception as e:
        logger.warning("Auto-fill fetch error for source=%s: %s", source, e)
        return None


async def _single_fetch_tb_value(
    parts: list[str],
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> Decimal | None:
    """TB:account_code:field → 试算表取数（单条）"""
    if len(parts) < 3:
        return None

    account_code = parts[1]
    field_name = parts[2]
    orm_field = _TB_FIELD_MAP.get(field_name, field_name)

    result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    val = getattr(row, orm_field, None)
    return Decimal(str(val)) if val is not None else None


async def _single_fetch_wp_value(
    parts: list[str],
    project_id: UUID,
    db: AsyncSession,
) -> str | Decimal | None:
    """WP:wp_code:sheet:cell → 其他底稿取数（单条）"""
    if len(parts) < 4:
        return None

    wp_code = parts[1]
    sheet_name = parts[2]
    cell_ref = parts[3]

    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WpIndex.wp_code == wp_code,
            WpIndex.project_id == project_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        ).limit(1)
    )
    wp = result.scalar_one_or_none()
    if wp is None or not wp.parsed_data:
        return None

    html_data = wp.parsed_data.get("html_data", {})
    sheet_data = html_data.get(sheet_name, {})
    cells = sheet_data.get("cells", {})
    if cell_ref in cells:
        cell_val = cells[cell_ref]
        if isinstance(cell_val, dict):
            return cell_val.get("value") or cell_val.get("v")
        return cell_val

    return None


async def _single_fetch_report_value(
    parts: list[str],
    project_id: UUID,
    year: int,
    db: AsyncSession,
) -> Decimal | None:
    """REPORT:row_code:field → 报表取数（单条）"""
    if len(parts) < 3:
        return None

    row_code = parts[1]
    field_name = parts[2] if len(parts) > 2 else "amount"

    from app.models.report_models import FinancialReport

    result = await db.execute(
        sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.row_code == row_code,
            FinancialReport.is_deleted == sa.false(),
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    val = getattr(row, field_name, None)
    return Decimal(str(val)) if val is not None else None


# ─── 向后兼容别名 ─────────────────────────────────────────────────────────────
# 旧代码可能直接调用 _fetch_source_value，保留别名指向 single fallback
_fetch_source_value = _single_fetch_source_value
