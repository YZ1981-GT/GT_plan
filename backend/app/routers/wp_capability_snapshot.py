# -*- coding: utf-8 -*-
"""底稿能力快照 HTTP 面 — 前端 formula shell 挂载时拉取的授权真源。

前端 ``src/shell/formula/fetchCapabilitySnapshot.ts`` 打
``GET /api/workpapers/{wp_id}/capability-snapshot?project_id=..&ownerEpoch=..&sheetUid=..``，
据此门控公式壳层（右轨/公式管理器/双向回写触发器）与 AI/复核入口。

Spec: d4-adjustment-and-analysis-gap-closure Task 3（C2formula backbone）
Requirements: 2.3, 3.1
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from app.models.core import User
from app.services.workpaper_capability_matrix import (
    SnapshotSubject,
    assert_capability,
    build_full_capability_snapshot,
)

router = APIRouter(prefix="/api/workpapers/{wp_id}", tags=["workpaper-capability"])


@router.get("/capability-snapshot")
def get_capability_snapshot(
    wp_id: str,
    project_id: str = Query(..., alias="project_id"),
    owner_epoch: int = Query(0, alias="ownerEpoch"),
    sheet_uid: str | None = Query(None, alias="sheetUid"),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """签发当前用户在指定底稿/sheet/owner-epoch 下的九键能力快照。"""
    subject = SnapshotSubject(
        role=str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or ""),
        user_id=str(getattr(user, "id", "")),
        project_id=project_id,
        wp_id=wp_id,
        sheet_uid=sheet_uid,
        owner_epoch=owner_epoch,
    )
    return build_full_capability_snapshot(subject)


@router.get("/capability-assert")
def assert_capability_action(
    wp_id: str,
    project_id: str = Query(..., alias="project_id"),
    capability: str = Query(..., alias="capability"),
    owner_epoch: int = Query(0, alias="ownerEpoch"),
    sheet_uid: str | None = Query(None, alias="sheetUid"),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """服务端复核：当前用户此刻是否可执行某项能力（供敏感动作二次把关）。"""
    subject = SnapshotSubject(
        role=str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or ""),
        user_id=str(getattr(user, "id", "")),
        project_id=project_id,
        wp_id=wp_id,
        sheet_uid=sheet_uid,
        owner_epoch=owner_epoch,
    )
    snapshot = build_full_capability_snapshot(subject)
    return assert_capability(snapshot, capability, owner_epoch=owner_epoch)
