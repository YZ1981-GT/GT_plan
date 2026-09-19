"""Pure compatibility adapter for custom-query template visibility scopes.

The adapter deliberately has no database or authorization dependency.  Routers and
services can normalize wire/storage values first, then perform project edit checks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

CanonicalTemplateScope = Literal["private", "team", "project", "public"]
AcceptedTemplateScope = Literal[
    "private", "team", "project", "public", "global", "personal"
]

_ACCEPTED_SCOPES = frozenset(
    {"private", "team", "project", "public", "global", "personal"}
)


class TemplateScopeValidationError(ValueError):
    """Raised when a scope payload cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class NormalizedTemplateScope:
    scope: CanonicalTemplateScope
    shared_project_ids: tuple[uuid.UUID, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "shared_project_ids": [str(project_id) for project_id in self.shared_project_ids],
        }


def normalize_scope(scope: Any) -> CanonicalTemplateScope:
    """Return canonical scope; legacy ``global``/``personal`` are input-only."""
    if not isinstance(scope, str):
        raise TemplateScopeValidationError("scope must be a string")
    normalized = scope.strip().lower()
    if normalized not in _ACCEPTED_SCOPES:
        raise TemplateScopeValidationError(f"unsupported template scope: {scope!r}")
    aliases = {"global": "public", "personal": "private"}
    return aliases.get(normalized, normalized)  # type: ignore[return-value]


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def normalize_project_ids(
    scope: CanonicalTemplateScope,
    values: Any,
    *,
    config_project_id: Any = None,
) -> tuple[uuid.UUID, ...]:
    """Return explicit project-sharing targets for a scope.

    Only ``project`` owns a non-empty ``shared_project_ids`` set. ``team`` uses
    ``config.project_id`` as a separate authorization anchor, so callers that only
    normalize the explicit sharing column always receive an empty tuple for team.
    Equivalent project sets are sorted by UUID text to avoid storage/order drift.
    """
    if scope in {"private", "team", "public"}:
        return ()
    if not isinstance(values, (list, tuple, set)) or not values:
        raise TemplateScopeValidationError(
            "project scope requires at least one shared_project_id"
        )

    project_ids: set[uuid.UUID] = set()
    for raw in values:
        project_id = _as_uuid(raw)
        if project_id is None:
            raise TemplateScopeValidationError(f"invalid shared project id: {raw!r}")
        project_ids.add(project_id)

    if not project_ids:
        raise TemplateScopeValidationError(
            "project scope requires at least one shared_project_id"
        )
    return tuple(sorted(project_ids, key=str))


def _valid_project_ids(values: Any) -> set[uuid.UUID]:
    result = {_as_uuid(value) for value in (values or [])}
    result.discard(None)
    return result  # type: ignore[return-value]


def is_template_visible(
    *,
    scope: Any,
    owner_id: Any,
    user_id: Any,
    shared_project_ids: Any = None,
    config_project_id: Any = None,
    accessible_project_ids: set[uuid.UUID] | None,
) -> bool:
    """Apply the canonical owner/public/project/team visibility contract.

    ``None`` for ``accessible_project_ids`` means the user can access every project.
    Team templates use ``config.project_id`` as their canonical team anchor and also
    accept legacy team records whose anchor was stored in ``shared_project_ids``.
    Missing anchors fail closed instead of becoming implicitly public.
    """
    owner = _as_uuid(owner_id)
    viewer = _as_uuid(user_id)
    if owner is not None and owner == viewer:
        return True

    try:
        canonical_scope = normalize_scope(scope)
    except TemplateScopeValidationError:
        return False
    if canonical_scope == "public":
        return True
    if canonical_scope == "private":
        return False

    shared = _valid_project_ids(shared_project_ids)
    if canonical_scope == "team":
        anchor = _as_uuid(config_project_id)
        # Canonical/new records are visible only through config.project_id. Legacy
        # records without that field may fall back to their stored sharing anchors.
        team_projects = {anchor} if anchor is not None else shared
        return bool(team_projects) and (
            accessible_project_ids is None
            or bool(team_projects & accessible_project_ids)
        )

    return bool(shared) and (
        accessible_project_ids is None or bool(shared & accessible_project_ids)
    )


class TemplateScopeAdapter:
    """Single pure entry point for scope, project-list and visibility normalization."""

    @staticmethod
    def normalize(
        scope: Any,
        shared_project_ids: Any = None,
        *,
        config_project_id: Any = None,
    ) -> NormalizedTemplateScope:
        canonical_scope = normalize_scope(scope)
        return NormalizedTemplateScope(
            scope=canonical_scope,
            shared_project_ids=normalize_project_ids(
                canonical_scope,
                shared_project_ids,
                config_project_id=config_project_id,
            ),
        )

    @staticmethod
    def normalize_record(
        scope: Any,
        shared_project_ids: Any = None,
        *,
        config_project_id: Any = None,
    ) -> NormalizedTemplateScope:
        """Normalize persisted/legacy records for canonical API output.

        Read compatibility is intentionally more tolerant than new writes: a legacy
        team record without ``config.project_id`` may use its stored sharing anchors;
        malformed project records remain fail-closed for visibility but can still be
        serialized for their owner.
        """
        canonical_scope = normalize_scope(scope)
        if canonical_scope == "team":
            # New records keep the anchor in config.project_id, not in the explicit
            # project-sharing column. Legacy records without an anchor retain their
            # stored IDs so owners can still inspect and migrate them.
            anchor = _as_uuid(config_project_id)
            ids = set() if anchor is not None else _valid_project_ids(shared_project_ids)
        elif canonical_scope == "project":
            ids = _valid_project_ids(shared_project_ids)
        else:
            ids = set()
        return NormalizedTemplateScope(
            scope=canonical_scope,
            shared_project_ids=tuple(sorted(ids, key=str)),
        )

    is_visible = staticmethod(is_template_visible)
