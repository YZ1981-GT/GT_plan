"""recovery case 列表的只读投影（自 `wp_sync_router._load_recovery_cases` 原样迁出）。

spec workpaper-sync-switch-performance：router 行数门腾挪（新增 `materialize-from-store` 端点），
函数体逐字未改，只把 `svc.session` 换成显式 `session` 入参。AC 5.8 的「零业务内容」口径不变。
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa


async def load_recovery_cases(
    session: Any, *, room_id: uuid.UUID, generation: int
) -> list[dict[str, Any]]:
    """候选 prior confirmation 摘要 + `claim/download-only` 能力，**零业务内容**。

    AC 5.8：不返回业务内容或未授权资源存在性。因此这里只投影 reason/state/
    候选 confirmation id 与能力布尔 —— 没有 hash、没有整稿、没有 artifact 路径。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackRecoveryCase,
        WorkpaperOoClientConfirmation,
    )

    rows = list(
        (
            await session.execute(
                sa.select(WorkpaperCallbackRecoveryCase)
                .where(
                    WorkpaperCallbackRecoveryCase.room_id == room_id,
                    WorkpaperCallbackRecoveryCase.generation == generation,
                )
                .order_by(WorkpaperCallbackRecoveryCase.created_at)
            )
        ).scalars()
    )
    if not rows:
        return []
    candidates = list(
        (
            await session.execute(
                sa.select(
                    WorkpaperOoClientConfirmation.id,
                    WorkpaperOoClientConfirmation.participant_id,
                    WorkpaperOoClientConfirmation.content_version_id,
                    WorkpaperOoClientConfirmation.confirmed_at,
                )
                .where(WorkpaperOoClientConfirmation.room_id == room_id)
                .order_by(WorkpaperOoClientConfirmation.confirmed_at.desc())
            )
        ).all()
    )
    summary = [
        {
            "confirmation_id": str(c[0]),
            "participant_id": str(c[1]),
            "content_version_id": str(c[2]),
            "confirmed_at": c[3].isoformat() if c[3] is not None else None,
        }
        for c in candidates
    ]
    # 🔴 终态集从**状态机登记表**取，不写字符串字面量。
    # 第一版写死了 `("claimed", "download_only", "quarantined", "expired")`，
    # 而 `RecoveryCaseState` 里根本没有 `claimed`（真实值是 `application_created`）——
    # 后果是「已 claim 的 case 仍然显示可 claim/可 download-only」，前端据此给出两个
    # 按钮，点下去才由服务端拒绝。字面量与枚举漂移在功能测试里完全看不出来。
    from app.services.workpaper_sync.models import RecoveryCaseState, TERMINAL_STATES

    terminal_states = {s.value for s in TERMINAL_STATES["recovery_case"]} | {
        RecoveryCaseState.application_created.value
    }
    out: list[dict[str, Any]] = []
    for case in rows:
        terminal = str(case.state) in terminal_states
        out.append(
            {
                "case_id": str(case.id),
                "reason": str(case.reason),
                "state": str(case.state),
                # claim 前三实体全空 —— 这三个 None 就是 AC 5.8 的可观测事实。
                "operation_id": (
                    None if case.operation_id is None else str(case.operation_id)
                ),
                "application_id": (
                    None if case.application_id is None else str(case.application_id)
                ),
                "forcesave_request_id": (
                    None
                    if case.recovery_request_id is None
                    else str(case.recovery_request_id)
                ),
                "candidate_prior_confirmations": summary,
                "actions": {
                    "claim": not terminal,
                    "download_only": not terminal,
                },
            }
        )
    return out


__all__ = ["load_recovery_cases"]
