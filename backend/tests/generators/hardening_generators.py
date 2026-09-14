"""PBT generators for advanced-query-disclosure-integration-hardening.

Feature: advanced-query-disclosure-integration-hardening

Provides reusable Hypothesis strategies for properties P1–P12:
- Query request generator (valid old-format + optional new fields)
- Project permission set generator (random subset of project UUIDs)
- Pagination rows generator (list of dicts with consistent keys)
- Template scope generator (canonical + legacy aliases)
- Mutation fault point generator (sampled_from: none/mutate/commit/publish)

Uses repo fast profile (max_examples=5, deadline=None).
"""

from __future__ import annotations

import uuid

from hypothesis import strategies as st

# ─── 固定项目池 ────────────────────────────────────────────────────────────────
# 使用固定 UUID 池使权限集合可控地相交（避免随机 UUID 永不相交）。
_PROJECT_POOL: list[uuid.UUID] = [uuid.uuid4() for _ in range(8)]

# ─── 常量 ──────────────────────────────────────────────────────────────────────
_CANONICAL_SCOPES = ("private", "team", "project", "public")
_ACCEPTED_SCOPES = ("private", "team", "project", "public", "global")
_FAULT_POINTS = ("none", "mutate", "commit", "publish")
_SORT_DIRECTIONS = ("asc", "desc")
_NULLS_POSITIONS = ("first", "last")
_AGG_OPS = ("sum", "count", "avg", "min", "max")

# ─── Column/Field 名称策略 ─────────────────────────────────────────────────────
_FIELD_NAMES = (
    "amount", "balance", "account_code", "account_name",
    "debit", "credit", "period", "project_name", "voucher_no",
    "date", "description", "addr_id", "section", "category",
)

st_field_name = st.sampled_from(_FIELD_NAMES)


# ─── 1. Query Request Generator ───────────────────────────────────────────────
# Generates a HardenedQueryRequest-shaped dict with valid old-format fields
# and optional new fields (sort, group, pivot, acnr_targets).

st_sort_spec = st.fixed_dictionaries({
    "field": st_field_name,
    "direction": st.sampled_from(_SORT_DIRECTIONS),
}).flatmap(lambda d: st.just(d) | st.fixed_dictionaries({
    "field": st.just(d["field"]),
    "direction": st.just(d["direction"]),
    "nulls": st.sampled_from(_NULLS_POSITIONS),
}))

st_aggregate_spec = st.fixed_dictionaries({
    "field": st_field_name,
    "op": st.sampled_from(_AGG_OPS),
})

st_group_spec = st.fixed_dictionaries({
    "dimensions": st.lists(st_field_name, min_size=1, max_size=4),
    "aggregates": st.lists(st_aggregate_spec, min_size=1, max_size=3),
})

st_pivot_spec = st.fixed_dictionaries({
    "rowDimensions": st.lists(st_field_name, min_size=1, max_size=2),
    "columnDimensions": st.lists(st_field_name, min_size=1, max_size=2),
    "valueField": st_field_name,
    "aggregate": st.sampled_from(_AGG_OPS),
})

st_query_request = st.fixed_dictionaries({
    "project_id": st.sampled_from(_PROJECT_POOL).map(str),
    "year": st.integers(min_value=2020, max_value=2030),
    "source": st.sampled_from(["disclosure", "tb_balance", "tb_ledger", "trial_balance"]),
    "filters": st.just({}),  # minimal; specific tests can override
    "columns": st.lists(st_field_name, min_size=0, max_size=6),
    "limit": st.integers(min_value=1, max_value=500),
    "offset": st.integers(min_value=0, max_value=1000),
    "sort": st.lists(st_sort_spec, min_size=0, max_size=3),
    "group": st.none() | st_group_spec,
    "pivot": st.none() | st_pivot_spec,
    "acnr_targets": st.lists(
        st.text(min_size=3, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_/:-0123456789"),
        min_size=0, max_size=4,
    ),
})


# ─── 2. Project Permission Set Generator ──────────────────────────────────────
# Random subset of the project pool, simulating user's authorized projects.

st_project_permissions = st.frozensets(
    st.sampled_from(_PROJECT_POOL),
    min_size=0,
    max_size=len(_PROJECT_POOL),
).map(set)


# ─── 3. Pagination Rows Generator ─────────────────────────────────────────────
# Generates a list of row dicts with consistent column keys, suitable for
# testing stable pagination, deduplication, and ordering properties.

def _st_pagination_rows(
    min_rows: int = 0,
    max_rows: int = 50,
) -> st.SearchStrategy:
    """Generate a list of row dicts with consistent keys and a unique `_row_id`."""
    return st.integers(min_value=min_rows, max_value=max_rows).flatmap(
        lambda n: st.lists(
            st.fixed_dictionaries({
                "_row_id": st.uuids().map(str),
                "amount": st.floats(
                    min_value=-1e12, max_value=1e12,
                    allow_nan=False, allow_infinity=False,
                ),
                "account_code": st.text(
                    min_size=4, max_size=8,
                    alphabet="0123456789",
                ),
                "description": st.text(min_size=0, max_size=60),
            }),
            min_size=n,
            max_size=n,
        )
    )


st_pagination_rows = _st_pagination_rows()


# ─── 4. Template Scope Generator ──────────────────────────────────────────────
# Generates canonical scopes plus the legacy `global` alias.

st_canonical_scope = st.sampled_from(_CANONICAL_SCOPES)
st_accepted_scope = st.sampled_from(_ACCEPTED_SCOPES)

st_template_scope = st.fixed_dictionaries({
    "scope": st_accepted_scope,
    "shared_project_ids": st.lists(
        st.sampled_from(_PROJECT_POOL).map(str),
        min_size=0,
        max_size=5,
    ),
})


# ─── 5. Mutation Fault Point Generator ────────────────────────────────────────
# Samples from the state machine fault points for testing transaction behavior.

st_mutation_fault = st.sampled_from(_FAULT_POINTS)


# ─── Convenience: PROJECT_POOL export ─────────────────────────────────────────
PROJECT_POOL = _PROJECT_POOL
