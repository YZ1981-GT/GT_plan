"""报表 stale 联动服务 — US-2

底稿保存后检查 wp_code 是否在 report_line_mapping 中有映射，
有则标记对应 FinancialReport 行 is_stale=True 并发 SSE 通知。

链路：wp_code → wp_account_mapping.json → account_codes
      → report_line_mapping → report_line_code
      → financial_report.is_stale = True

Validates: Requirements US-2 验收标准 1-5
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import ReportLineMapping
from app.models.report_models import FinancialReport

logger = logging.getLogger(__name__)

# ─── wp_account_mapping 缓存 ─────────────────────────────────────────────────

_WP_MAPPING_CACHE: dict[str, list[str]] | None = None


def _load_wp_account_mapping() -> dict[str, list[str]]:
    """加载 wp_account_mapping.json，返回 {wp_code: [account_codes]} 索引。"""
    global _WP_MAPPING_CACHE
    if _WP_MAPPING_CACHE is not None:
        return _WP_MAPPING_CACHE

    mapping_path = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
    if not mapping_path.exists():
        logger.warning("wp_account_mapping.json not found at %s", mapping_path)
        _WP_MAPPING_CACHE = {}
        return _WP_MAPPING_CACHE

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mappings = data.get("mappings", [])
        result: dict[str, list[str]] = {}
        for m in mappings:
            wp_code = m.get("wp_code", "")
            account_codes = m.get("account_codes", [])
            if wp_code and account_codes:
                result[wp_code] = account_codes
        _WP_MAPPING_CACHE = result
        return result
    except Exception as exc:
        logger.warning("Failed to load wp_account_mapping.json: %s", exc)
        _WP_MAPPING_CACHE = {}
        return _WP_MAPPING_CACHE


# ─── Service ─────────────────────────────────────────────────────────────────


class ReportStaleService:
    """报表 stale 标记服务"""

    async def mark_if_mapped(
        self, wp_code: str, project_id: UUID, db: AsyncSession
    ) -> list[str]:
        """检查 wp_code 是否在 report_line_mapping 中有映射，有则标记 stale。

        Returns:
            受影响的 report_line_code 列表（空列表表示无映射）
        """
        # Step 1: wp_code → account_codes
        wp_mapping = _load_wp_account_mapping()
        account_codes = wp_mapping.get(wp_code, [])
        if not account_codes:
            logger.debug(
                "mark_if_mapped: wp_code=%s has no account mapping, skip", wp_code
            )
            return []

        # Step 2: account_codes → report_line_codes via report_line_mapping
        stmt = (
            sa.select(ReportLineMapping.report_line_code)
            .where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code.in_(account_codes),
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
            .distinct()
        )
        result = await db.execute(stmt)
        affected_line_codes = [r[0] for r in result.fetchall()]

        if not affected_line_codes:
            logger.debug(
                "mark_if_mapped: wp_code=%s accounts=%s have no report_line_mapping",
                wp_code,
                account_codes[:3],
            )
            return []

        # Step 3: 标记 FinancialReport 行 is_stale=True（幂等）
        await db.execute(
            sa.update(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.row_code.in_(affected_line_codes),
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            .values(is_stale=True)
        )

        # Step 4: 发 SSE 通知
        self._broadcast_stale(project_id, affected_line_codes)

        logger.info(
            "mark_if_mapped: wp_code=%s → %d report lines marked stale",
            wp_code,
            len(affected_line_codes),
        )
        return affected_line_codes

    def _broadcast_stale(self, project_id: UUID, affected_rows: list[str]) -> None:
        """发布 report.stale SSE 事件（非阻塞）。"""
        try:
            from app.services.event_bus import event_bus

            event_bus.broadcast_raw(
                event_type="report.stale",
                extra={
                    "project_id": str(project_id),
                    "rows": affected_rows,
                },
            )
        except Exception as exc:
            # SSE 发布失败不阻断主流程
            logger.warning("Failed to broadcast report.stale SSE: %s", exc)


# ─── Module-level singleton ──────────────────────────────────────────────────

report_stale_service = ReportStaleService()
