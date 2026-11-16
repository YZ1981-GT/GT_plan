"""Task 30：既有治理版本的 alias-only 回填判定。"""
from __future__ import annotations

from uuid import uuid4

from app.services.evidence_governance.backfill_runner import (
    assess_existing_version_chain,
)


def _root(*, version: int = 1, current=None, project=None, year=2025):
    return {
        "id": uuid4(),
        "project_id": project or uuid4(),
        "audit_year": year,
        "version": version,
        "current_version_id": current,
    }


def _version(root, number: int, *, previous=None, availability="available"):
    return {
        "id": uuid4(),
        "project_id": root["project_id"],
        "audit_year": root["audit_year"],
        "version_no": number,
        "previous_version_id": previous,
        "availability": availability,
    }


def test_no_existing_versions_means_normal_creation_path():
    root = _root()
    assert assess_existing_version_chain(root, []) is None


def test_single_existing_version_is_alias_only_safe():
    root = _root()
    version = _version(root, 1)
    root["current_version_id"] = version["id"]

    result = assess_existing_version_chain(root, [version])

    assert result is not None and result.safe
    assert result.target_version_id == version["id"]
    assert result.resolution_kind == "root"


def test_existing_linear_chain_maps_legacy_id_to_current_version():
    root = _root(version=2)
    first = _version(root, 1)
    second = _version(root, 2, previous=first["id"])
    root["current_version_id"] = second["id"]

    result = assess_existing_version_chain(root, [second, first])

    assert result is not None and result.safe
    assert result.target_version_id == second["id"]
    assert result.resolution_kind == "current_version"


def test_existing_chain_scope_or_current_mismatch_is_blocked():
    root = _root()
    version = _version(root, 1, availability="inactive")
    root["current_version_id"] = uuid4()

    result = assess_existing_version_chain(root, [version])

    assert result is not None and not result.safe
    assert result.reason == "current_version_id 未指向最高版本"
