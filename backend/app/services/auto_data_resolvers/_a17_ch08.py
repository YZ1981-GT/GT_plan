"""A17-1 第八章「已审财务报表分析」auto_data resolver.

从 analytical_review_service 取 A1-13/A1-14 显著变动项目，
返回结构化列表供前端 GtA171Chapter8 表格展示。

注册名: a17_ch08_analytical_review
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from . import auto_resolver

logger = logging.getLogger(__name__)


def _fmt(val: Decimal | float | None) -> str:
    """格式化金额为千分位字符串"""
    if val is None:
        return "—"
    return f"{float(val):,.0f}"


def _pct(val: Decimal | float | None) -> float | None:
    if val is None:
        return None
    return round(float(val) * 100, 1) if abs(float(val)) < 100 else round(float(val), 1)


@auto_resolver("a17_ch08_analytical_review")
async def resolve_a17_ch08(db: AsyncSession, project_id: UUID, year: int, **_) -> dict:
    """返回显著/关注变动项目列表 + 统计摘要"""
    from app.services.analytical_review_service import get_analytical_review_data

    items: list[dict] = []
    sig_count = 0
    att_count = 0
    materiality: float | None = None

    configs = [("A1-13", "standalone", "母公司"), ("A1-14", "consolidated", "合并")]

    for wp_code, scope, label in configs:
        try:
            data = await get_analytical_review_data(db, project_id, year, wp_code=wp_code, scope=scope)
            if materiality is None and data.get("materiality"):
                materiality = data["materiality"]

            sheets = data.get("sheets", data)  # v2 has .sheets, v1 is flat
            for sheet_key, sheet_label in [
                ("bs_horizontal", f"{label}资产负债表"),
                ("is_horizontal", f"{label}利润表"),
            ]:
                sheet_data = sheets.get(sheet_key, {})
                for row in sheet_data.get("rows", []):
                    status = row.get("status")
                    if status not in ("significant", "attention"):
                        continue
                    if status == "significant":
                        sig_count += 1
                    else:
                        att_count += 1
                    items.append({
                        "sheet": sheet_label,
                        "name": row.get("name", ""),
                        "prior": _fmt(row.get("prior_amount")),
                        "current": _fmt(row.get("current_amount")),
                        "pct": _pct(row.get("change_pct")),
                        "status": status,
                    })
        except Exception as e:
            logger.warning("a17_ch08 resolver %s failed: %s", wp_code, e)
            continue

    return {
        "items": items,
        "significant_count": sig_count,
        "attention_count": att_count,
        "materiality": materiality,
        "summary": f"显著变动 {sig_count} 项，关注 {att_count} 项",
    }
