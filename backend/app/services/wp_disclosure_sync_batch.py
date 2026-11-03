"""底稿披露多章节同步的事务编排。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User


async def run_sync_batch_from_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    wp_id: UUID,
    current_standard: str,
    items: list[dict[str, Any]],
    user: User,
    year: int | None = None,
    propagation_origin: Literal["user_edit", "system_recompute"] = "user_edit",
    require_all_applied: bool = False,
    sync_one: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """多章节一次事务同步；严格模式下任何语义性 no-op 也整批回滚。"""
    if not items:
        raise ValueError("items 不能为空")

    results: list[dict[str, Any]] = []
    try:
        for item in items:
            section_id = str(item.get("section_id") or "").strip()
            sheet_name = str(item.get("sheet_name") or "").strip()
            if not section_id or not sheet_name:
                raise ValueError("每个 item 必须包含 section_id 与 sheet_name")
            sub_table_data = item.get("sub_table_data") or {}
            if not isinstance(sub_table_data, dict):
                raise ValueError(f"section {section_id} 的 sub_table_data 必须为对象")
            sub_table_columns = item.get("columns")
            if sub_table_columns is not None and not isinstance(sub_table_columns, dict):
                raise ValueError(f"section {section_id} 的 columns 必须为对象")
            owner_key = item.get("owner_key")
            replace_owned_tables = bool(item.get("replace_owned_tables", False))
            if replace_owned_tables and not str(owner_key or "").strip():
                raise ValueError(
                    f"section {section_id} 启用 replace_owned_tables 时必须提供 owner_key"
                )
            result = await sync_one(
                db,
                project_id,
                wp_id=wp_id,
                sheet_name=sheet_name,
                section_id=section_id,
                sub_table_data=sub_table_data,
                current_standard=current_standard,
                user=user,
                year=year,
                sub_table_columns=sub_table_columns,
                propagation_origin=propagation_origin,
                owner_key=owner_key,
                replace_owned_tables=replace_owned_tables,
                commit=False,
            )
            if "skipped_reason" in result:
                # 项目没有审计年度、载荷也没带年度：单章节端点回 422（R3）；批量原先把它当成功汇总 ⇒ 读 results[-1]["synced_at"]
                # KeyError、对外 500（L3 国企 / G7 走批量）。抛 ValueError ⇒ 整批回滚、路由回 422 中文原因
                # （spec note-pull-followup-closure R1 实施中发现，与 R3 同口径）
                raise ValueError(f"附注未同步：{result['skipped_reason']}")
            if require_all_applied:
                if result.get("blocked_by_manual_override"):
                    raise ValueError(f"附注 {section_id} 被整节人工覆盖保护拦截")
                if result.get("skipped"):
                    reason = str(result.get("reason") or "章节不适用")
                    raise ValueError(f"附注 {section_id} 未同步：{reason}")
                unresolved = [
                    str(name) for name in (result.get("row_scope_unresolved") or [])
                    if str(name)
                ]
                if unresolved:
                    reasons = result.get("row_scope_unresolved_reasons") or {}
                    detail = "、".join(
                        f"{name}（{reasons[name]}）" if reasons.get(name) else name
                        for name in unresolved
                    )
                    raise ValueError(f"附注 {section_id} 分段同步未写入：{detail}")
            results.append(result)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "success": True,
        "sections_synced": len(results),
        "rows_synced": sum(int(item.get("rows_synced") or 0) for item in results),
        "texts_synced": sum(int(item.get("texts_synced") or 0) for item in results),
        "results": results,
        "synced_at": results[-1]["synced_at"] if results else datetime.now(timezone.utc).isoformat(),
    }
