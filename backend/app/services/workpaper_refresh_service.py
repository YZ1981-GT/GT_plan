"""批量刷新底稿取数服务（batch-refresh-workpaper-data spec Task 1）。

对指定的 wp_id 列表逐个执行行名对齐 + 自动确认 auto_matched 映射，
跳过 ambiguous/unmatched 行（不弹窗），前端 reload render-config 即可获取最新数据。

串行处理避免 DB 并发压力；每个底稿独立 try/catch 不影响其余。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class RefreshResult:
    """单底稿刷新结果。"""
    wp_id: str
    wp_code: str
    ok: bool
    error: str | None = None
    auto_matched: int = 0
    pending: int = 0


async def batch_refresh_workpapers(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_ids: list[uuid.UUID],
) -> list[RefreshResult]:
    """批量刷新底稿取数。

    对每个底稿：
    1. 解析 wp_code / year
    2. 从 wp_account_mapping.json 获取科目前缀
    3. 调 build_alignment_wire 做行名对齐
    4. 对 auto_matched 行自动写入映射（跳过 ambiguous/unmatched）
    5. 汇总结果

    Args:
        db: 数据库会话
        project_id: 项目 ID
        wp_ids: 要刷新的底稿 ID 列表

    Returns:
        每个底稿的刷新结果列表
    """
    from app.routers.row_name_alignment_router import (
        _resolve_account_prefixes,
        _resolve_wp_scope,
    )
    from app.services.four_table.row_name_alignment import (
        MatchState,
        TargetIdentity,
    )
    from app.services.row_name_alignment_wire import (
        RowAlignmentInput,
        build_alignment_wire,
    )
    from app.services.row_name_mapping_service import (
        MappingScope,
        RowConfirmInput,
        RowNameMappingService,
    )

    results: list[RefreshResult] = []

    for wp_id in wp_ids:
        try:
            wp_code, pid, year = await _resolve_wp_scope(db, wp_id)
            if str(pid) != str(project_id):
                results.append(RefreshResult(
                    wp_id=str(wp_id), wp_code="", ok=False,
                    error="底稿不属于当前项目",
                ))
                continue

            # 获取科目前缀
            prefixes = _resolve_account_prefixes(wp_code, wp_code)
            if not prefixes:
                results.append(RefreshResult(
                    wp_id=str(wp_id), wp_code=wp_code, ok=True,
                    error=None, auto_matched=0, pending=0,
                ))
                continue

            # 构建行输入（用 wp_code 作为 sheet_code，取顶层对齐行）
            # 批量刷新不依赖前端传行名，直接用科目前缀做对齐
            scope = MappingScope(
                project_id=pid, year=year,
                wp_code=wp_code, sheet_code=wp_code,
            )

            # 从已有映射获取行名
            svc = RowNameMappingService(db)
            saved = await svc.load_active_mappings(scope)

            rows: list[RowAlignmentInput] = []
            for rk, m in saved.items():
                rows.append(RowAlignmentInput(
                    row_key=rk,
                    row_label=rk,  # 用 row_key 作为 label 的 fallback
                    account_prefixes=prefixes,
                ))

            if not rows:
                # 无已有映射行，标记为成功但无操作
                results.append(RefreshResult(
                    wp_id=str(wp_id), wp_code=wp_code, ok=True,
                    auto_matched=0, pending=0,
                ))
                continue

            # 执行对齐
            wire = await build_alignment_wire(db, scope, rows)
            wire_rows = wire.get("rows", [])

            # 自动确认 auto_matched 行
            auto_rows: list[RowConfirmInput] = []
            auto_count = 0
            pending_count = 0

            for wr in wire_rows:
                state = wr.get("match_state", "")
                if state == MatchState.AUTO_MATCHED.value:
                    auto_count += 1
                    targets_raw = wr.get("target_identity", [])
                    if targets_raw:
                        auto_rows.append(RowConfirmInput(
                            row_key=wr["row_key"],
                            targets=[
                                TargetIdentity(
                                    source_kind=t["source_kind"],
                                    account_code=t["account_code"],
                                    aux_type=t.get("aux_type"),
                                    aux_name=t["aux_name"],
                                    dimension_key=t["dimension_key"],
                                    dataset_id=t.get("dataset_id"),
                                )
                                for t in targets_raw
                            ],
                        ))
                elif state in (MatchState.UNMATCHED.value, MatchState.AMBIGUOUS.value):
                    pending_count += 1

            # 批量写入 auto_matched 映射
            if auto_rows:
                try:
                    await svc.batch_confirm(
                        scope, auto_rows,
                        confirmed_by=None,
                        idempotency_key=f"batch-refresh-{wp_id}-{uuid.uuid4().hex[:8]}",
                    )
                    await db.flush()
                except Exception as exc:
                    logger.warning(
                        "batch-refresh: auto_confirm 写入失败 wp=%s: %s",
                        wp_code, exc,
                    )

            results.append(RefreshResult(
                wp_id=str(wp_id), wp_code=wp_code, ok=True,
                auto_matched=auto_count, pending=pending_count,
            ))

        except Exception as exc:
            logger.error(
                "batch-refresh: 刷新失败 wp_id=%s: %s",
                wp_id, exc, exc_info=True,
            )
            results.append(RefreshResult(
                wp_id=str(wp_id), wp_code="", ok=False,
                error=str(exc)[:200],
            ))

        # 串行间隔，避免 DB 压力
        await asyncio.sleep(0.05)

    return results
