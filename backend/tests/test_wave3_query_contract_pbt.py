"""Wave 2.5/3 pure contract tests for template scope, identity, and paging."""

from __future__ import annotations

import copy
import uuid

import pytest
from hypothesis import given, settings, strategies as st

from app.core.pagination import PaginationParams
from app.services.custom_query.query_cache import QueryCache
from app.services.custom_query.template_scope_adapter import (
    TemplateScopeAdapter,
    TemplateScopeValidationError,
    normalize_scope,
)


@settings(max_examples=5)
@given(scope=st.sampled_from(["private", "team", "public", "global"]))
def test_p7_scope_normalization_never_emits_global(scope: str) -> None:
    """Feature: advanced-query-disclosure-integration-hardening, Property P7."""
    normalized = TemplateScopeAdapter.normalize(scope)
    assert normalized.scope in {"private", "team", "public"}
    assert normalized.scope == ("public" if scope == "global" else scope)
    assert normalized.shared_project_ids == ()


@settings(max_examples=5)
@given(project_ids=st.lists(st.uuids(), min_size=1, max_size=8))
def test_p7_project_scope_requires_nonempty_and_deduplicates(project_ids) -> None:
    """Feature: advanced-query-disclosure-integration-hardening, Property P7."""
    duplicated = project_ids + list(reversed(project_ids))
    normalized = TemplateScopeAdapter.normalize("project", duplicated)
    assert normalized.scope == "project"
    assert list(normalized.shared_project_ids) == sorted(set(project_ids), key=str)
    assert "global" not in normalized.to_payload().values()


def test_p7_project_scope_rejects_empty_project_list() -> None:
    with pytest.raises(TemplateScopeValidationError, match="at least one"):
        TemplateScopeAdapter.normalize("project", [])
    assert normalize_scope(" global ") == "public"


_BASE_IDENTITY = {
    "contract_version": "aq-disclosure-v1",
    "schema_version": "v1",
    "project_id": str(uuid.UUID(int=1)),
    "user_scope_signature": "scope-a",
    "source": "workpaper",
    "filters": {"year": 2025, "status": "active"},
    "columns": ["code", "amount"],
    "limit": 20,
    "offset": 0,
    "sort": [{"field": "amount", "direction": "desc"}],
    "group": {"dimensions": ["code"], "aggregates": []},
    "pivot": None,
    "acnr_targets": ["D2/D2-2/A1", "D2/D2-2/B1"],
}
@settings(max_examples=5)
@given(field=st.sampled_from(["columns", "offset", "sort", "group", "pivot", "acnr_targets"]))
def test_p3_identity_is_key_order_invariant_but_semantic_field_sensitive(field: str) -> None:
    """Feature: advanced-query-disclosure-integration-hardening, Property P3."""
    cache = QueryCache()
    reordered = dict(reversed(list(_BASE_IDENTITY.items())))
    base_key = cache.cache_key(_BASE_IDENTITY, _BASE_IDENTITY["project_id"], "scope-a")
    assert base_key == cache.cache_key(reordered, _BASE_IDENTITY["project_id"], "scope-a")

    changed = copy.deepcopy(_BASE_IDENTITY)
    replacements = {
        "columns": ["amount", "code"],
        "offset": 20,
        "sort": [{"field": "amount", "direction": "asc"}],
        "group": {"dimensions": ["amount"], "aggregates": []},
        "pivot": {"rowDimensions": ["code"], "columnDimensions": ["year"]},
        "acnr_targets": ["D2/D2-2/B1", "D2/D2-2/A1"],
    }
    changed[field] = replacements[field]
    assert base_key != cache.cache_key(changed, changed["project_id"], "scope-a")


@settings(max_examples=5)
@given(
    rows=st.lists(st.integers(min_value=-10_000, max_value=10_000), unique=True, max_size=80),
    page_size=st.integers(min_value=1, max_value=20),
)
def test_p5_stable_pages_reconstruct_full_result_without_overlap(rows, page_size: int) -> None:
    """Feature: advanced-query-disclosure-integration-hardening, Property P5."""
    stable_rows = sorted(rows)
    pages: list[list[int]] = []
    page_number = 1
    while True:
        params = PaginationParams(page=page_number, page_size=page_size)
        current = stable_rows[params.offset : params.offset + params.limit]
        if not current:
            break
        pages.append(current)
        page_number += 1

    flattened = [row for page in pages for row in page]
    assert flattened == stable_rows
    assert all(set(left).isdisjoint(right) for left, right in zip(pages, pages[1:]))
    assert all(len(stable_rows) == len(rows) for _page in pages or [[]])
