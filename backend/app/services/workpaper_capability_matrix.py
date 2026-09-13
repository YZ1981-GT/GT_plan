# -*- coding: utf-8 -*-
"""底稿能力矩阵 — 9 键能力快照的 role→capability 真源（fail-closed）。

前端 formula shell（``src/shell/formula/workpaperCapabilitySnapshot.ts``）在挂载时
拉 ``GET /api/workpapers/{wp_id}/capability-snapshot``，据此门控公式查看/编辑/历史、
AI 复核（页/批）、AI 助手、人工复核读写、编制指导阅读九项能力。缺这个端点 → 前端
拉不到快照 → **fail-closed 到 snapshot_uninitialized**，整个公式壳层（右轨、公式管理器、
双向回写触发器）都打不开。这个模块补上后端的 role→capability 真源与快照签发。

设计要点
--------
- **单一真源**：九项能力的 role 白名单集中在 :data:`CAPABILITY_MATRIX`，新增能力/调整
  角色只改这一处；未列入的能力对任何角色默认拒绝。
- **fail-closed**：未知角色、未知能力、缺字段一律 ``allowed=False``。
- **owner epoch 竞态门**：快照带 ``ownerEpoch``，前端 ``assertCapabilityAllowed`` 只在
  epoch 相等时放行；他人接管/上下文推进 → epoch 变化 → 旧快照自动失效。
- **拒绝文案不泄敏**：``zhMessage`` 只给角色级中文原因，绝不带公式内容/线程 id/指导标题
  （前端 ``denialLeaksSensitiveMetadata`` 会实测这一点）。
- **不改并发在途的** :mod:`app.services.workpaper_capability`：本模块**组合**它的
  ``CapabilityPrincipal`` 与 ``build_capability_snapshot``（formulaEditUser 单键），
  在其之上补齐其余八键，两处对 formulaEditUser 的判定保持一致（见
  :func:`_formula_edit_allowed_cross_check`）。

Spec: d4-adjustment-and-analysis-gap-closure Task 3（C2formula backbone）
Requirements: 2.3, 3.1
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final, Mapping

from app.services.workpaper_capability import (
    CapabilityPrincipal,
    build_capability_snapshot as _build_formula_edit_snapshot,
)

__all__ = [
    "CAPABILITY_SNAPSHOT_VERSION",
    "CAPABILITY_KEYS",
    "CAPABILITY_MATRIX",
    "SnapshotSubject",
    "build_full_capability_snapshot",
    "assert_capability",
]

#: 与前端 ``CAPABILITY_SNAPSHOT_VERSION`` 常量对齐；主版本不符前端 fail-closed 到 null。
CAPABILITY_SNAPSHOT_VERSION: Final[str] = "1.0"

#: 快照有效期（分钟）。过期后前端 ``assertCapabilityAllowed`` 判 ``snapshot_expired``。
_SNAPSHOT_TTL_MINUTES: Final[int] = 30

#: 九项能力键，顺序/拼写与前端 ``CAPABILITY_KEYS`` 严格一致。
CAPABILITY_KEYS: Final[tuple[str, ...]] = (
    "formulaView",
    "formulaEditUser",
    "formulaHistory",
    "aiReviewPage",
    "aiReviewBatch",
    "aiAssistChat",
    "humanReviewRead",
    "humanReviewWrite",
    "guidanceRead",
)

#: 系统角色（``app.models.base.UserRole``）→ 归一化能力角色。
#: readonly/未知 → viewer（只读）；auditor → assignee（现场执行）；
#: manager/qc/eqcr/partner → reviewer（复核）；admin → admin。
_ROLE_NORMALIZATION: Final[Mapping[str, str]] = {
    "admin": "admin",
    "superadmin": "admin",
    "partner": "reviewer",
    "manager": "reviewer",
    "qc": "reviewer",
    "eqcr": "reviewer",
    "auditor": "assignee",
    "assignee": "assignee",
    "editor": "assignee",
    "readonly": "viewer",
    "viewer": "viewer",
}

#: 能力矩阵：能力键 → 允许的（归一化）角色集合。未列入的角色一律拒绝。
#:
#: - 只读类（formulaView/formulaHistory/humanReviewRead/guidanceRead/aiAssistChat）：
#:   admin/reviewer/assignee/viewer 全可（viewer 也能看）。
#: - 编辑/发起类（formulaEditUser/aiReviewPage/aiReviewBatch）：admin/reviewer/assignee，
#:   viewer 拒绝。批量 AI 复核（aiReviewBatch）成本高，仅 admin/reviewer。
#: - 人工复核写（humanReviewWrite）：仅 admin/reviewer（复核结论只有复核角色能落）。
CAPABILITY_MATRIX: Final[Mapping[str, frozenset[str]]] = {
    "formulaView": frozenset({"admin", "reviewer", "assignee", "viewer"}),
    "formulaEditUser": frozenset({"admin", "reviewer", "assignee"}),
    "formulaHistory": frozenset({"admin", "reviewer", "assignee", "viewer"}),
    "aiReviewPage": frozenset({"admin", "reviewer", "assignee"}),
    "aiReviewBatch": frozenset({"admin", "reviewer"}),
    "aiAssistChat": frozenset({"admin", "reviewer", "assignee", "viewer"}),
    "humanReviewRead": frozenset({"admin", "reviewer", "assignee", "viewer"}),
    "humanReviewWrite": frozenset({"admin", "reviewer"}),
    "guidanceRead": frozenset({"admin", "reviewer", "assignee", "viewer"}),
}

#: 拒绝原因码 → 中文文案（不泄敏）。
_DENY_ZH: Final[Mapping[str, str]] = {
    "role_denied": "当前角色无权执行此操作。",
    "viewer_read_only": "只读角色不能编辑或发起此操作。",
    "unknown_capability": "未知能力项，已拒绝。",
}


def normalize_role(raw: str | None) -> str:
    """系统角色 → 归一化能力角色；未知一律 viewer（最小权限，fail-closed）。"""
    return _ROLE_NORMALIZATION.get(str(raw or "").strip().lower(), "viewer")


@dataclass(frozen=True)
class SnapshotSubject:
    """快照签发主体：谁、在哪个项目/底稿/sheet、哪个 owner epoch。"""

    role: str
    user_id: str
    project_id: str
    wp_id: str
    sheet_uid: str | None = None
    owner_epoch: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _subject_digest(subject: SnapshotSubject) -> str:
    """稳定主体指纹：绑定 role/project/wp/sheet/epoch，换底稿/换 epoch 即变。

    前端 ``subjectDigest`` 用来判「这份快照是给当前主体的吗」，因此必须把会改变
    授权语义的字段都纳入指纹，避免一份快照被跨底稿/跨 epoch 重放。
    """
    raw = "|".join(
        [
            subject.role,
            subject.project_id,
            subject.wp_id,
            subject.sheet_uid or "",
            str(subject.owner_epoch),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decision(allowed: bool, *, reason_code: str | None = None) -> dict[str, Any]:
    """一项能力的判定结果（前端 ``CapabilityDecision`` 形状）。"""
    if allowed:
        return {
            "allowed": True,
            "reasonCode": None,
            "owner": None,
            "nextAction": None,
            "zhMessage": None,
        }
    code = reason_code or "role_denied"
    return {
        "allowed": False,
        "reasonCode": code,
        "owner": "workpaper-capability-matrix",
        "nextAction": "联系项目负责人",
        "zhMessage": _DENY_ZH.get(code, _DENY_ZH["role_denied"]),
    }


def _capability_allowed(norm_role: str, key: str) -> tuple[bool, str | None]:
    permitted = CAPABILITY_MATRIX.get(key)
    if permitted is None:
        return False, "unknown_capability"
    if norm_role in permitted:
        return True, None
    # 更贴切的原因码：viewer 被编辑类能力拒绝时给「只读」文案。
    if norm_role == "viewer":
        return False, "viewer_read_only"
    return False, "role_denied"


def _formula_edit_allowed_cross_check(principal: CapabilityPrincipal, owner_epoch: int) -> bool:
    """用并发在途的 :mod:`workpaper_capability` 复核 formulaEditUser 判定，防两处漂移。

    两个模块对「谁能编辑用户公式」若给出不同答案，说明矩阵与 v2 路由的判据分叉了 ——
    这里直接把底层判定拿来做交叉校验，不一致时以底层（路由实际用的那套）为准。
    """
    snap = _build_formula_edit_snapshot(principal, owner_epoch=owner_epoch)
    entry = snap.get("formulaEditUser") or {}
    return bool(entry.get("allowed"))


def build_full_capability_snapshot(subject: SnapshotSubject) -> dict[str, Any]:
    """签发九键能力快照（前端 wire 形状）。

    返回的 dict 直接可 JSON 序列化，键与 ``WorkpaperCapabilitySnapshot`` 一一对应。
    formulaEditUser 与 :mod:`app.services.workpaper_capability` 交叉校验保持一致。
    """
    norm_role = normalize_role(subject.role)
    now = _now()

    snapshot: dict[str, Any] = {
        "snapshotVersion": CAPABILITY_SNAPSHOT_VERSION,
        "subjectDigest": _subject_digest(subject),
        "ownerEpoch": int(subject.owner_epoch),
        "issuedAt": _iso(now),
        "expiresAt": _iso(now + timedelta(minutes=_SNAPSHOT_TTL_MINUTES)),
        "projectId": subject.project_id,
        "wpId": subject.wp_id,
        "sheetUid": subject.sheet_uid,
        "role": norm_role,
    }

    for key in CAPABILITY_KEYS:
        allowed, reason = _capability_allowed(norm_role, key)
        snapshot[key] = _decision(allowed, reason_code=reason)

    # formulaEditUser 交叉校验：以 v2 路由实际使用的底层判定为准，杜绝两处分叉。
    principal = CapabilityPrincipal(
        role="admin" if norm_role == "admin" else ("assignee" if norm_role in {"assignee", "reviewer"} else "viewer"),  # type: ignore[arg-type]
        user_id=subject.user_id,
        project_id=subject.project_id,
        wp_id=subject.wp_id,
    )
    # reviewer 在底层归到 assignee 白名单内（都能编辑用户公式）；viewer 不在。
    cross = _formula_edit_allowed_cross_check(principal, subject.owner_epoch)
    matrix_says = snapshot["formulaEditUser"]["allowed"]
    if bool(matrix_says) != bool(cross):
        # 不一致时取底层（fail-closed 到更严格的一边）。
        snapshot["formulaEditUser"] = _decision(
            matrix_says and cross,
            reason_code=None if (matrix_says and cross) else "role_denied",
        )

    return snapshot


def assert_capability(
    snapshot: Mapping[str, Any],
    key: str,
    *,
    owner_epoch: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """服务端复核一份快照是否放行某能力（前端 ``assertCapabilityAllowed`` 的后端对应）。

    fail-closed：缺快照/未知能力/epoch 不匹配/已过期/被拒 → allowed=False + 中文原因。
    """
    at = now or _now()
    if key not in CAPABILITY_MATRIX:
        return {"status": "blocked", "reasonCode": "unknown_capability",
                "zhMessage": _DENY_ZH["unknown_capability"]}
    if not isinstance(snapshot, Mapping):
        return {"status": "blocked", "reasonCode": "snapshot_uninitialized",
                "zhMessage": "能力快照尚未就绪，请稍候。"}
    snap_epoch = snapshot.get("ownerEpoch")
    if snap_epoch is None or int(snap_epoch) != int(owner_epoch):
        return {"status": "blocked", "reasonCode": "epoch_mismatch",
                "zhMessage": "底稿上下文已切换，旧权限已失效。"}
    expires_raw = str(snapshot.get("expiresAt") or "")
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return {"status": "blocked", "reasonCode": "snapshot_expired",
                "zhMessage": "能力快照已过期，请刷新后重试。"}
    if at >= expires:
        return {"status": "blocked", "reasonCode": "snapshot_expired",
                "zhMessage": "能力快照已过期，请刷新后重试。"}
    entry = snapshot.get(key)
    if not isinstance(entry, Mapping) or not bool(entry.get("allowed")):
        code = (entry or {}).get("reasonCode") if isinstance(entry, Mapping) else None
        return {"status": "blocked", "reasonCode": code or "role_denied",
                "zhMessage": (entry or {}).get("zhMessage") if isinstance(entry, Mapping) else None
                or _DENY_ZH["role_denied"]}
    return {"status": "allowed"}
