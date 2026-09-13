"""Workpaper capability snapshot — authorization gate for user-editable surfaces.

This module backs :mod:`app.routers.wp_user_formulas_v2` (and any other workpaper
capability consumer). It answers one question, fail-closed: *given who the caller
is and which owner epoch they claim, are they allowed to perform a capability
action (e.g. edit a user formula)?*

Design notes
------------
- **Fail-closed by default.** Any unknown role, missing snapshot field, or epoch
  mismatch resolves to ``allowed=False``. We never default-allow.
- **Owner epoch is a race guard.** A snapshot is only actionable when the epoch it
  was minted against still matches the epoch the caller presents. A stale epoch
  (someone else took ownership / the context advanced) denies the action rather
  than silently applying an out-of-date decision.
- **Snapshot is a plain dict** so it can round-trip through JSON request bodies
  (``capabilitySnapshot`` on the wire) without a bespoke serializer.

The capability action vocabulary is intentionally small and explicit; adding an
action means adding it to :data:`CAPABILITY_ACTIONS` so an unknown action string
is denied instead of silently permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Mapping

__all__ = [
    "CapabilityPrincipal",
    "CapabilityDecision",
    "CAPABILITY_ACTIONS",
    "build_capability_snapshot",
    "assert_snapshot_action_allowed",
]

Role = Literal["admin", "superadmin", "assignee", "reviewer", "viewer"]

#: Roles that may edit user-authored formulas on a workpaper. Reviewers and viewers
#: are read-only for this action; anything not listed is denied (fail-closed).
_FORMULA_EDIT_ROLES: Final[frozenset[str]] = frozenset({"admin", "superadmin", "assignee"})

#: The closed vocabulary of capability actions. Each maps to the set of roles that
#: are permitted to perform it. Unknown actions are denied.
CAPABILITY_ACTIONS: Final[Mapping[str, frozenset[str]]] = {
    "formulaEditUser": _FORMULA_EDIT_ROLES,
}


@dataclass(frozen=True)
class CapabilityPrincipal:
    """The identity a capability snapshot is minted for.

    ``project_id`` / ``wp_id`` scope the snapshot so a decision minted for one
    workpaper can't be replayed against another; ``build_capability_snapshot``
    stamps them into the snapshot and :func:`assert_snapshot_action_allowed`
    treats a missing/blank action entry as denied.
    """

    role: Role
    user_id: str
    project_id: str
    wp_id: str


@dataclass(frozen=True)
class CapabilityDecision:
    """The result of evaluating one action against a snapshot."""

    allowed: bool
    action: str
    reason: str = ""


def _role_allows(role: str, action: str) -> bool:
    permitted = CAPABILITY_ACTIONS.get(action)
    if permitted is None:
        return False
    return str(role or "").lower() in permitted


def build_capability_snapshot(
    principal: CapabilityPrincipal, *, owner_epoch: int = 0
) -> dict[str, Any]:
    """Mint a capability snapshot for ``principal`` at ``owner_epoch``.

    The snapshot is a plain JSON-serializable dict of the shape::

        {
          "ownerEpoch": <int>,
          "principal": {"role", "userId", "projectId", "wpId"},
          "formulaEditUser": {"allowed": <bool>},
          ...one entry per action in CAPABILITY_ACTIONS...
        }
    """
    snapshot: dict[str, Any] = {
        "ownerEpoch": int(owner_epoch),
        "principal": {
            "role": principal.role,
            "userId": principal.user_id,
            "projectId": principal.project_id,
            "wpId": principal.wp_id,
        },
    }
    for action in CAPABILITY_ACTIONS:
        snapshot[action] = {"allowed": _role_allows(principal.role, action)}
    return snapshot


def assert_snapshot_action_allowed(
    snapshot: Mapping[str, Any],
    action: str,
    *,
    owner_epoch: int = 0,
) -> CapabilityDecision:
    """Evaluate whether ``action`` is permitted by ``snapshot`` at ``owner_epoch``.

    Fail-closed: a missing snapshot entry, an unknown action, or an owner-epoch
    mismatch all resolve to ``allowed=False`` with a human-readable Chinese reason.
    """
    if action not in CAPABILITY_ACTIONS:
        return CapabilityDecision(False, action, f"未知的能力动作: {action!r}")

    if not isinstance(snapshot, Mapping):
        return CapabilityDecision(False, action, "能力快照缺失或格式非法")

    snapshot_epoch = snapshot.get("ownerEpoch")
    if snapshot_epoch is None or int(snapshot_epoch) != int(owner_epoch):
        return CapabilityDecision(
            False,
            action,
            f"能力快照 ownerEpoch({snapshot_epoch}) 与当前上下文({owner_epoch})不匹配，"
            "快照已过期（可能有他人接管或上下文已推进），拒绝执行",
        )

    entry = snapshot.get(action)
    if not isinstance(entry, Mapping) or not bool(entry.get("allowed")):
        return CapabilityDecision(False, action, f"能力快照未授予 {action} 权限")

    return CapabilityDecision(True, action, "")
