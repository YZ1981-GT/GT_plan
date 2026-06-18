"""export-word 统一分发服务（PRE-2 端点骨架）.

按 wp_code 前缀分发到各 spec 编排服务（a17_word_exporter、
regulatory_letter_service 等）。当前无编排服务就绪，全部返回 501。

设计要点（见 .kiro/specs/completion-phase-infra/requirements.md PRE-2）：
- 本层是纯分发/编排，**禁止**在此重新实现颜色语义（那在 docx_template_filler.py）
- wp_code 查 wp_index 表（WorkingPaper.wp_index_id → WpIndex.wp_code）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# ─── 导出分发注册表 ──────────────────────────────────────────────────────────
# 键=wp_code 前缀（如 "A17"、"A18"），值=async callable(db, project_id, wp_id) -> bytes
# 各 spec 实现就绪后在此注册。
ExportHandler = Callable[..., Coroutine[Any, Any, bytes]]
CheckHandler = Callable[..., Coroutine[Any, Any, dict]]

EXPORT_DISPATCH: dict[str, ExportHandler] = {}
CHECK_DISPATCH: dict[str, CheckHandler] = {}


def _register_a17_handlers() -> None:
    """延迟注册 A17 导出/检查 handler（避免循环导入）。"""
    if "A17-1" not in EXPORT_DISPATCH:
        from app.services.a17_word_exporter import a17_check_incomplete, a17_export_word

        EXPORT_DISPATCH["A17-1"] = a17_export_word
        CHECK_DISPATCH["A17-1"] = a17_check_incomplete

    if "A17-2-1" not in EXPORT_DISPATCH:
        from app.services.a17_word_exporter import (
            a17_kam_check_incomplete,
            a17_kam_export_word,
        )

        EXPORT_DISPATCH["A17-2-1"] = a17_kam_export_word
        CHECK_DISPATCH["A17-2-1"] = a17_kam_check_incomplete


def _register_a18_handlers() -> None:
    """延迟注册 A18-2 导出/检查 handler。"""
    if "A18-2" not in EXPORT_DISPATCH:
        from app.services.regulatory_letter_service import (
            a18_check_incomplete,
            a18_export_word,
        )

        EXPORT_DISPATCH["A18-2"] = a18_export_word
        CHECK_DISPATCH["A18-2"] = a18_check_incomplete


_register_a17_handlers()
_register_a18_handlers()


# ─── 辅助：查 wp_code ────────────────────────────────────────────────────────


async def _resolve_wp_code(db: AsyncSession, wp_id: UUID) -> str | None:
    """通过 wp_id 查 wp_index.wp_code。返回 None 表示 wp 不存在或无索引。"""
    stmt = (
        select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row


def _match_dispatch_key(wp_code: str, registry: dict) -> str | None:
    """按 wp_code 前缀匹配分发表键（最长匹配优先）。"""
    # 精确匹配优先
    if wp_code in registry:
        return wp_code
    # 前缀匹配（降序长度）
    for key in sorted(registry.keys(), key=len, reverse=True):
        if wp_code.startswith(key):
            return key
    return None


# ─── 公共接口 ────────────────────────────────────────────────────────────────


async def export_word(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> tuple[bytes | None, str | None, int]:
    """执行 Word 导出。

    Returns:
        (file_bytes, wp_code, http_status)
        - 成功: (bytes, wp_code, 200)
        - 未实现: (None, wp_code, 501)
        - 底稿不存在: (None, None, 404)
    """
    wp_code = await _resolve_wp_code(db, wp_id)
    if wp_code is None:
        return None, None, 404

    dispatch_key = _match_dispatch_key(wp_code, EXPORT_DISPATCH)
    if dispatch_key is None:
        logger.info("export-word 未注册: wp_code=%s, wp_id=%s", wp_code, wp_id)
        return None, wp_code, 501

    handler = EXPORT_DISPATCH[dispatch_key]
    file_bytes = await handler(db, project_id, wp_id)
    return file_bytes, wp_code, 200


async def check_incomplete(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> tuple[dict, int]:
    """执行完整性检查。

    Returns:
        (result_dict, http_status)
        - 未实现时返回 complete=False + reason
        - 底稿不存在返回 404
    """
    wp_code = await _resolve_wp_code(db, wp_id)
    if wp_code is None:
        return {"error": "底稿不存在"}, 404

    dispatch_key = _match_dispatch_key(wp_code, CHECK_DISPATCH)
    if dispatch_key is None:
        logger.info("check-incomplete 未注册: wp_code=%s, wp_id=%s", wp_code, wp_id)
        return {
            "complete": False,
            "missing_fields": [],
            "wp_code": wp_code,
            "reason": "检查服务未就绪",
        }, 501

    handler = CHECK_DISPATCH[dispatch_key]
    result = await handler(db, project_id, wp_id)
    return result, 200
