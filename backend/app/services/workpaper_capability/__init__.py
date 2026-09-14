"""Workpaper capability matrix + snapshot (formula-toolbar Task 3).

Fail-closed: unknown role / missing membership / expired / epoch mismatch → deny.
Denied decisions carry Chinese UI copy without leaking formula/thread/guidance metadata.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping

CapabilityKey = Literal[
    "formulaView",
    "formulaEditUser",
    "formulaHistory",
    "aiReviewPage",
    "aiReviewBatch",
    "aiAssistChat",
    "humanReviewRead",
    "humanReviewWrite",
    "guidanceRead",
]

CAPABILITY_KEYS: tuple[CapabilityKey, ...] = (
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

RoleName = Literal[
    "admin",
    "supervisor",
    "lead",
    "assignee",
    "reviewer",
    "readonly",
    "anonymous",
]

SNAPSHOT_TTL_SECONDS = 60
SNAPSHOT_CONTRACT_VERSION = "1.0"
MATRIX_OWNER = "workpaper-capability-matrix"


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    reason_code: str | None
    owner: str | None
    next_action: str | None
    zh_message: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasonCode": self.reason_code,
            "owner": self.owner,
            "nextAction": self.next_action,
            "zhMessage": self.zh_message,
        }


@dataclass(frozen=True)
class CapabilityPrincipal:
    role: RoleName
    user_id: str
    project_id: str
    wp_id: str
    sheet_uid: str | None = None
    project_member: bool = True
    wp_visible: bool = True


#: role → frozenset of allowed capability keys (matrix). Missing ⇒ deny.
_ROLE_ALLOW: dict[RoleName, frozenset[CapabilityKey]] = {
    "admin": frozenset(CAPABILITY_KEYS),
    "supervisor": frozenset(CAPABILITY_KEYS),
    "lead": frozenset(
        {
            "formulaView",
            "formulaEditUser",
            "formulaHistory",
            "aiReviewPage",
            "aiReviewBatch",
            "aiAssistChat",
            "humanReviewRead",
            "humanReviewWrite",
            "guidanceRead",
        }
    ),
    "assignee": frozenset(
        {
            "formulaView",
            "formulaEditUser",
            "formulaHistory",
            "aiAssistChat",
            "humanReviewRead",
            "guidanceRead",
        }
    ),
    "reviewer": frozenset(
        {
            "formulaView",
            "formulaHistory",
            "aiReviewPage",
            "humanReviewRead",
            "humanReviewWrite",
            "guidanceRead",
        }
    ),
    "readonly": frozenset({"formulaView", "formulaHistory", "guidanceRead", "humanReviewRead"}),
    "anonymous": frozenset(),
}

_ZH_DENY: dict[str, tuple[str, str]] = {
    # reason_code → (zh_message, next_action)
    "not_project_member": ("您不是该项目成员，无法使用底稿公共能力。", "联系项目负责人加入项目"),
    "wp_not_visible": ("当前底稿对您不可见，相关能力已禁用。", "确认底稿委派或可见范围"),
    "role_denied": ("当前角色无权执行此操作。", "切换有权限的账号或联系项目负责人"),
    "snapshot_uninitialized": ("能力快照尚未就绪，请稍候。", "等待权限加载完成后重试"),
    "snapshot_expired": ("能力快照已过期，请刷新后重试。", "刷新底稿页以重新获取权限"),
    "epoch_mismatch": ("底稿上下文已切换，旧权限已失效。", "回到当前底稿后重试"),
    "unknown_capability": ("未知能力项，已拒绝。", "升级客户端或联系支持"),
}


def _deny(reason_code: str) -> CapabilityDecision:
    zh, nxt = _ZH_DENY.get(
        reason_code,
        ("当前无权执行此操作。", "联系项目负责人"),
    )
    return CapabilityDecision(
        allowed=False,
        reason_code=reason_code,
        owner=MATRIX_OWNER,
        next_action=nxt,
        zh_message=zh,
    )


def _allow() -> CapabilityDecision:
    return CapabilityDecision(
        allowed=True,
        reason_code=None,
        owner=MATRIX_OWNER,
        next_action=None,
        zh_message=None,
    )


def decide_capability(principal: CapabilityPrincipal, key: CapabilityKey) -> CapabilityDecision:
    """Authoritative single-key decision (server-side revalidation entry)."""
    if key not in CAPABILITY_KEYS:
        return _deny("unknown_capability")
    if not principal.project_member:
        return _deny("not_project_member")
    if not principal.wp_visible:
        return _deny("wp_not_visible")
    allowed_keys = _ROLE_ALLOW.get(principal.role, frozenset())
    if key not in allowed_keys:
        return _deny("role_denied")
    return _allow()


def _subject_digest(principal: CapabilityPrincipal, owner_epoch: int) -> str:
    payload = {
        "userId": principal.user_id,
        "projectId": principal.project_id,
        "wpId": principal.wp_id,
        "sheetUid": principal.sheet_uid,
        "role": principal.role,
        "ownerEpoch": owner_epoch,
        "projectMember": principal.project_member,
        "wpVisible": principal.wp_visible,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_capability_snapshot(
    principal: CapabilityPrincipal,
    *,
    owner_epoch: int,
    now: datetime | None = None,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
) -> dict[str, Any]:
    """Build versioned WorkpaperCapabilitySnapshot wire (camelCase)."""
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    expires = clock + timedelta(seconds=ttl_seconds)
    decisions = {key: decide_capability(principal, key).to_wire() for key in CAPABILITY_KEYS}
    return {
        "snapshotVersion": SNAPSHOT_CONTRACT_VERSION,
        "subjectDigest": _subject_digest(principal, owner_epoch),
        "ownerEpoch": owner_epoch,
        "expiresAt": expires.isoformat().replace("+00:00", "Z"),
        "issuedAt": clock.isoformat().replace("+00:00", "Z"),
        "projectId": principal.project_id,
        "wpId": principal.wp_id,
        "sheetUid": principal.sheet_uid,
        "role": principal.role,
        **decisions,
    }


def assert_snapshot_action_allowed(
    snapshot: Mapping[str, Any],
    key: CapabilityKey,
    *,
    owner_epoch: int,
    now: datetime | None = None,
) -> CapabilityDecision:
    """Shell / endpoint gate: ready + epoch + expiry + per-key decision."""
    if not snapshot:
        return _deny("snapshot_uninitialized")
    if snapshot.get("ownerEpoch") != owner_epoch:
        return _deny("epoch_mismatch")
    expires_raw = snapshot.get("expiresAt")
    if not isinstance(expires_raw, str) or not expires_raw:
        return _deny("snapshot_expired")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return _deny("snapshot_expired")
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if clock >= expires:
        return _deny("snapshot_expired")
    decision = snapshot.get(key)
    if not isinstance(decision, Mapping):
        return _deny("unknown_capability")
    if decision.get("allowed") is True:
        return _allow()
    # Re-hydrate deny without trusting client-supplied zh for authority —
    # but prefer server reasonCode when present.
    reason = decision.get("reasonCode") or "role_denied"
    if not isinstance(reason, str):
        reason = "role_denied"
    return _deny(reason)


def denial_leaks_sensitive_metadata(zh_message: str | None) -> bool:
    """Guard helper: denied copy must not leak formula/thread/guidance titles."""
    if not zh_message:
        return False
    lowered = zh_message.casefold()
    banned = (
        "formula=",
        "thread_id",
        "threadid",
        "guidance_title",
        "编制说明标题",
        "公式内容",
        "线程数",
    )
    return any(b in lowered or b in zh_message for b in banned)
