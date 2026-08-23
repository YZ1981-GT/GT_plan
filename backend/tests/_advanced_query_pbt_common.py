"""高级查询硬化 PBT 的共享夹具与策略（非测试文件，故用 `_` 前缀）。

由 `test_advanced_query_hardening_properties.py`（契约与分页域）与
`test_advanced_query_hardening_properties_scope.py`（作用域·执行路径·治理域）共用。
拆分原因：原单文件 917 行触发 pre-commit 行数门禁（上限 800），而门禁的指引是
「优先拆分或抽伴生模块」。测试替身与策略是数据/夹具而非判据，抽出后两侧判据各自
仍与其对照组同文件，不产生「判据与反空转关系跨文件」的问题。
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.routers.custom_query import QueryRequest as ApiQueryRequest
from app.services.custom_query import builder_scope as bs
from app.services.custom_query.builder_scope import (
    BuilderScope,
    apply_scope_to_select,
    scope_signature,
)
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.pagination import (
    MAX_LIMIT,
    MIN_LIMIT,
    apply_pagination,
    collect_available_columns,
    resolve_sort,
    validate_pagination,
)
from app.services.custom_query.query_orchestrator import (
    Agg,
    ColumnMeta,
    PivotConfig,
    QueryOrchestrator,
    QueryRequest,
    QueryResult,
)
from app.services.custom_query.table_whitelist import (
    JOIN_WHITELIST,
    MAX_AGGREGATES,
    MAX_GROUP_DIMS,
    MAX_JOINS_PER_QUERY,
    TABLE_WHITELIST,
    derive_field_tiers,
    enforce_complexity_budget,
    enforce_join_business_key,
    enforce_pii_field_access,
    join_business_keys,
)

PBT = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

_IDENT = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=12,
)
_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10**6, max_value=10**6),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=8),
)


# ── 测试替身 ────────────────────────────────────────────────────────────────
class _Guard:
    async def assert_target_accessible(self, *, user, project_id, db):
        return None

    async def filter_accessible_rows(self, rows, *, user, db):
        return rows

    async def get_accessible_project_ids(self, user, db):
        return None


class _Addressing:
    async def resolve_many(self, targets, *, project_id, db):
        return []


class _PassthroughCache:
    def cache_key(self, query_def, project_id, scope_sig):
        return f"{project_id}:{scope_sig}:{hash(str(query_def))}"

    async def get_or_compute(self, key, compute, *, ttl=30):
        return await compute()


def _orch(fetcher):
    return QueryOrchestrator(
        guard=_Guard(),
        addressing=_Addressing(),
        cache=_PassthroughCache(),
        business_fetcher=fetcher,
    )


def _run(coro):
    return asyncio.run(coro)
