"""Property-based tests for reference 运行时关系解析。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6 | Property 8**

Property 8: 对任意无环 reference 链，执行结果使用源公式当前版本；
源 definition 变化后引用方结果随之变化且被标 stale。

验证目标：
1. 运行时递归解析取源公式当前表达式，不复制 expression（Req 5.1/5.2）。
2. visited set 环检测正确返回结构化错误（Req 5.5）。
3. 固定版本参照验证 source_version/source_hash（Req 5.3）。
4. 固定版本参照版本/hash 不匹配时返回 stale 信号（Req 5.4）。
5. 悬空/跨项目返回结构化错误（Req 5.5）。
6. 源变更通过 outbox 标 stale（Req 5.6）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.formula_management.reference_resolver import (
    ReferenceResolution,
    OutboxStaleEvent,
    compute_expression_hash,
    get_formula_version,
    resolve_reference_chain,
    resolve_reference_expression,
    find_reference_dependents,
    mark_dependents_stale_via_outbox,
    _as_uuid,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test helpers / fakes
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PROJECT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


@dataclass
class FakeFormula:
    """Lightweight stand-in for WpFormula in unit tests."""

    id: uuid.UUID
    project_id: uuid.UUID
    expression: str | None = None
    formula_source: str = "custom"
    reference_formula_id: uuid.UUID | None = None
    definition_version: int | None = None
    updated_at: Any = None


def _build_chain(
    length: int,
    *,
    project_id: uuid.UUID = PROJECT_A,
    terminal_expression: str = "SUM(A1:A10)",
) -> dict[uuid.UUID, FakeFormula]:
    """Build a linear reference chain of given length.

    Returns dict[formula_id -> FakeFormula].
    The first entry is a reference pointing to the second, etc.
    The last entry is a non-reference formula with terminal_expression.
    """
    ids = [uuid.uuid4() for _ in range(length)]
    formulas: dict[uuid.UUID, FakeFormula] = {}
    for i, fid in enumerate(ids):
        if i < length - 1:
            formulas[fid] = FakeFormula(
                id=fid,
                project_id=project_id,
                expression=None,
                formula_source="reference",
                reference_formula_id=ids[i + 1],
                definition_version=1,
            )
        else:
            # terminal source formula
            formulas[fid] = FakeFormula(
                id=fid,
                project_id=project_id,
                expression=terminal_expression,
                formula_source="custom",
                reference_formula_id=None,
                definition_version=1,
            )
    return formulas


def _make_db_session(formulas: dict[uuid.UUID, FakeFormula]) -> AsyncMock:
    """Create a mock AsyncSession that resolves WpFormula lookups."""
    session = AsyncMock()

    async def _execute(stmt):
        # Extract the formula_id from the where clause
        # The query is: select(WpFormula).where(WpFormula.id == current_id)
        result = MagicMock()
        # Try to extract the id from compiled params
        try:
            # Access the whereclause to get the bound parameter
            compiled = stmt.compile()
            params = compiled.params
            # The param name is typically 'id_1' for WpFormula.id == value
            target_id = None
            for key, val in params.items():
                if "id" in key:
                    target_id = val
                    break
            if target_id is not None:
                if isinstance(target_id, str):
                    target_id = uuid.UUID(target_id)
                formula = formulas.get(target_id)
                result.scalar_one_or_none = MagicMock(return_value=formula)
            else:
                result.scalar_one_or_none = MagicMock(return_value=None)
        except Exception:
            result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    session.execute = _execute
    session.flush = AsyncMock()
    return session


def _make_db_for_dependents(
    source_id: uuid.UUID, dependents: list[FakeFormula]
) -> AsyncMock:
    """Mock session that returns dependents when querying for reference_formula_id."""
    session = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        # Check if this is a scalar_one_or_none or scalars().all() query
        compiled = stmt.compile()
        params = compiled.params
        # Detect dependent query (has reference_formula_id param)
        has_ref_id = any("reference_formula_id" in k for k in params.keys())
        if has_ref_id:
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=dependents)
            result.scalars = MagicMock(return_value=scalars_mock)
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    session.execute = _execute
    session.flush = AsyncMock()
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests: compute_expression_hash / get_formula_version
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeExpressionHash:
    """Unit tests for compute_expression_hash utility."""

    def test_none_expression_returns_empty_hash(self):
        h = compute_expression_hash(None)
        assert len(h) == 64  # SHA-256 hex
        assert h == compute_expression_hash("")

    def test_same_expression_same_hash(self):
        h1 = compute_expression_hash("SUM(A1:A10)")
        h2 = compute_expression_hash("SUM(A1:A10)")
        assert h1 == h2

    def test_different_expression_different_hash(self):
        h1 = compute_expression_hash("SUM(A1:A10)")
        h2 = compute_expression_hash("SUM(B1:B10)")
        assert h1 != h2

    @given(st.text(min_size=1, max_size=200))
    def test_hash_is_deterministic(self, expr: str):
        """**Validates: Requirements 5.3** - hash 确定性。"""
        assert compute_expression_hash(expr) == compute_expression_hash(expr)


class TestGetFormulaVersion:
    """Unit tests for get_formula_version."""

    def test_uses_definition_version_when_available(self):
        f = FakeFormula(id=uuid.uuid4(), project_id=PROJECT_A, definition_version=5)
        assert get_formula_version(f) == "5"

    def test_falls_back_to_updated_at(self):
        from datetime import datetime, timezone

        ts = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        f = FakeFormula(id=uuid.uuid4(), project_id=PROJECT_A, updated_at=ts)
        assert get_formula_version(f) == ts.isoformat()

    def test_returns_unknown_when_no_version_info(self):
        f = FakeFormula(id=uuid.uuid4(), project_id=PROJECT_A)
        assert get_formula_version(f) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests: resolve_reference_chain - basic scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveReferenceChain:
    """Unit tests for resolve_reference_chain core logic."""

    @pytest.mark.asyncio
    async def test_single_step_resolution(self):
        """Non-reference formula resolves to itself."""
        fid = uuid.uuid4()
        formulas = {
            fid: FakeFormula(
                id=fid,
                project_id=PROJECT_A,
                expression="A1 + B1",
                formula_source="custom",
                definition_version=3,
            )
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=fid, project_id=PROJECT_A
        )
        assert result.resolved is True
        assert result.expression == "A1 + B1"
        assert result.source_version == "3"
        assert result.source_hash == compute_expression_hash("A1 + B1")
        assert len(result.chain) == 1

    @pytest.mark.asyncio
    async def test_two_step_chain(self):
        """Reference -> Source resolves to source expression."""
        source_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        formulas = {
            ref_id: FakeFormula(
                id=ref_id,
                project_id=PROJECT_A,
                expression=None,
                formula_source="reference",
                reference_formula_id=source_id,
                definition_version=1,
            ),
            source_id: FakeFormula(
                id=source_id,
                project_id=PROJECT_A,
                expression="ROUND(X, 2)",
                formula_source="custom",
                definition_version=7,
            ),
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=ref_id, project_id=PROJECT_A
        )
        assert result.resolved is True
        assert result.expression == "ROUND(X, 2)"
        assert result.source_formula_id == str(source_id)
        assert result.source_version == "7"
        assert len(result.chain) == 2

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """**Validates: Requirements 5.5** - 环检测返回结构化错误。"""
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        formulas = {
            id_a: FakeFormula(
                id=id_a,
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=id_b,
                definition_version=1,
            ),
            id_b: FakeFormula(
                id=id_b,
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=id_a,
                definition_version=1,
            ),
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=id_a, project_id=PROJECT_A
        )
        assert result.resolved is False
        assert result.cycle is True
        assert result.issue is not None
        assert result.issue["code"] == "REFERENCE_CYCLE"
        assert len(result.issue["path"]) >= 2

    @pytest.mark.asyncio
    async def test_dangling_reference(self):
        """**Validates: Requirements 5.5** - 悬空引用返回结构化错误。"""
        missing_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        formulas = {
            ref_id: FakeFormula(
                id=ref_id,
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=missing_id,
                definition_version=1,
            ),
            # missing_id is NOT in formulas -> dangling
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=ref_id, project_id=PROJECT_A
        )
        assert result.resolved is False
        assert result.dangling is True
        assert result.issue["code"] == "DANGLING_REFERENCE"

    @pytest.mark.asyncio
    async def test_cross_project_reference(self):
        """**Validates: Requirements 5.5** - 跨项目源返回结构化错误。"""
        source_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        formulas = {
            ref_id: FakeFormula(
                id=ref_id,
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=source_id,
                definition_version=1,
            ),
            source_id: FakeFormula(
                id=source_id,
                project_id=PROJECT_B,  # different project!
                expression="SUM(X)",
                formula_source="custom",
                definition_version=2,
            ),
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=ref_id, project_id=PROJECT_A
        )
        assert result.resolved is False
        assert result.cross_project is True
        assert result.issue["code"] == "CROSS_PROJECT_REFERENCE"

    @pytest.mark.asyncio
    async def test_pinned_version_match(self):
        """**Validates: Requirements 5.3** - 固定版本匹配时正常解析。"""
        fid = uuid.uuid4()
        expr = "A1 * 2"
        formulas = {
            fid: FakeFormula(
                id=fid,
                project_id=PROJECT_A,
                expression=expr,
                formula_source="custom",
                definition_version=5,
            )
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db,
            formula_id=fid,
            project_id=PROJECT_A,
            reference_mode="pinned",
            pinned_version="5",
            pinned_hash=compute_expression_hash(expr),
        )
        assert result.resolved is True
        assert result.expression == expr

    @pytest.mark.asyncio
    async def test_pinned_version_mismatch(self):
        """**Validates: Requirements 5.4** - 固定版本不匹配返回 stale 信号。"""
        fid = uuid.uuid4()
        formulas = {
            fid: FakeFormula(
                id=fid,
                project_id=PROJECT_A,
                expression="NEW_EXPR",
                formula_source="custom",
                definition_version=6,
            )
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db,
            formula_id=fid,
            project_id=PROJECT_A,
            reference_mode="pinned",
            pinned_version="5",  # old version
            pinned_hash=compute_expression_hash("OLD_EXPR"),
        )
        assert result.resolved is False
        assert result.issue["code"] == "PINNED_VERSION_MISMATCH"
        assert "current_version" in result.issue
        assert "current_hash" in result.issue

    @pytest.mark.asyncio
    async def test_invalid_formula_id(self):
        """Invalid formula_id returns structured error immediately."""
        db = AsyncMock()
        result = await resolve_reference_chain(
            db, formula_id="not-a-uuid", project_id=PROJECT_A
        )
        assert result.resolved is False
        assert result.issue["code"] == "INVALID_FORMULA_ID"

    @pytest.mark.asyncio
    async def test_invalid_project_id(self):
        """Invalid project_id returns structured error immediately."""
        db = AsyncMock()
        result = await resolve_reference_chain(
            db, formula_id=uuid.uuid4(), project_id="bad"
        )
        assert result.resolved is False
        assert result.issue["code"] == "INVALID_PROJECT_ID"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests: resolve_reference_expression (legacy compat)
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveReferenceExpression:
    """Unit tests for the legacy-compat single-step resolve."""

    @pytest.mark.asyncio
    async def test_missing_reference_id(self):
        db = AsyncMock()
        result = await resolve_reference_expression(
            db, reference_formula_id=None
        )
        assert result.resolved is False
        assert result.issue["code"] == "MISSING_REFERENCE_ID"

    @pytest.mark.asyncio
    async def test_simple_resolve_without_project(self):
        """Without project_id does single-step lookup."""
        fid = uuid.uuid4()
        formula = FakeFormula(
            id=fid,
            project_id=PROJECT_A,
            expression="SUM(1,2,3)",
            definition_version=2,
        )
        session = AsyncMock()

        async def _execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=formula)
            return result

        session.execute = _execute
        result = await resolve_reference_expression(
            session, reference_formula_id=fid
        )
        assert result.resolved is True
        assert result.expression == "SUM(1,2,3)"

    @pytest.mark.asyncio
    async def test_dangling_without_project(self):
        """Without project_id, missing formula returns dangling."""
        session = AsyncMock()

        async def _execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            return result

        session.execute = _execute
        result = await resolve_reference_expression(
            session, reference_formula_id=uuid.uuid4()
        )
        assert result.resolved is False
        assert result.dangling is True


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests: find_reference_dependents
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindReferenceDependents:
    """Tests for find_reference_dependents."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_invalid_id(self):
        db = AsyncMock()
        result = await find_reference_dependents(db, source_formula_id="bad-uuid")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_dependents(self):
        source_id = uuid.uuid4()
        dep1 = FakeFormula(
            id=uuid.uuid4(), project_id=PROJECT_A,
            formula_source="reference", reference_formula_id=source_id,
        )
        dep2 = FakeFormula(
            id=uuid.uuid4(), project_id=PROJECT_A,
            formula_source="reference", reference_formula_id=source_id,
        )
        db = _make_db_for_dependents(source_id, [dep1, dep2])
        result = await find_reference_dependents(db, source_formula_id=source_id)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests: mark_dependents_stale_via_outbox (Req 5.6)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarkDependentsStaleViaOutbox:
    """Tests for outbox stale marking on source change."""

    @pytest.mark.asyncio
    async def test_no_dependents_returns_none(self):
        """No dependents → no outbox event written."""
        source_id = uuid.uuid4()
        db = _make_db_for_dependents(source_id, [])
        result = await mark_dependents_stale_via_outbox(
            db, source_formula_id=source_id, project_id=PROJECT_A
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_with_dependents_returns_event(self):
        """**Validates: Requirements 5.6** - 源变更写 outbox stale 事件。"""
        source_id = uuid.uuid4()
        dep = FakeFormula(
            id=uuid.uuid4(), project_id=PROJECT_A,
            formula_source="reference", reference_formula_id=source_id,
        )
        db = _make_db_for_dependents(source_id, [dep])
        # Patch outbox write to avoid real import
        with patch(
            "app.services.formula_management.reference_resolver.write_outbox_event",
            new_callable=AsyncMock,
            create=True,
        ):
            # The import inside the function may fail; that's fine for this test
            # since we're testing the event structure, not the actual write
            result = await mark_dependents_stale_via_outbox(
                db, source_formula_id=source_id, project_id=PROJECT_A
            )
        assert result is not None
        assert result.event_type == "reference_source_changed"
        assert str(dep.id) in result.dependent_formula_ids
        assert result.source_formula_id == str(source_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Property-based tests (P8: reference 动态一致)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReferenceRuntimePBT:
    """Property-based tests validating P8: reference 动态一致.

    **Validates: Requirements 5.2**
    """

    @given(
        chain_length=st.integers(min_value=2, max_value=5),
        expression=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_chain_resolves_to_terminal_expression(
        self, chain_length: int, expression: str
    ):
        """**Validates: Requirements 5.2**

        For any acyclic reference chain, resolution uses the current
        source formula's expression (not a saved copy).
        """
        formulas = _build_chain(
            chain_length, terminal_expression=expression
        )
        ids = list(formulas.keys())
        start_id = ids[0]
        terminal_id = ids[-1]
        db = _make_db_session(formulas)

        result = await resolve_reference_chain(
            db, formula_id=start_id, project_id=PROJECT_A
        )
        assert result.resolved is True
        assert result.expression == expression
        assert result.source_formula_id == str(terminal_id)
        assert len(result.chain) == chain_length

    @given(
        expression_before=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=30,
        ),
        expression_after=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_source_change_changes_resolution(
        self, expression_before: str, expression_after: str
    ):
        """**Validates: Requirements 5.2**

        When source definition changes, reference resolution uses the
        new expression (runtime, not saved copy).
        """
        assume(expression_before != expression_after)

        # Build chain with before expression
        formulas = _build_chain(2, terminal_expression=expression_before)
        ids = list(formulas.keys())
        start_id = ids[0]
        terminal_id = ids[-1]
        db = _make_db_session(formulas)

        result_before = await resolve_reference_chain(
            db, formula_id=start_id, project_id=PROJECT_A
        )
        assert result_before.resolved is True
        assert result_before.expression == expression_before

        # Simulate source definition change
        formulas[terminal_id].expression = expression_after
        formulas[terminal_id].definition_version = 2
        db2 = _make_db_session(formulas)

        result_after = await resolve_reference_chain(
            db2, formula_id=start_id, project_id=PROJECT_A
        )
        assert result_after.resolved is True
        assert result_after.expression == expression_after
        assert result_after.source_hash != result_before.source_hash

    @given(
        version_a=st.integers(min_value=1, max_value=100),
        version_b=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_pinned_detects_version_drift(
        self, version_a: int, version_b: int
    ):
        """**Validates: Requirements 5.3, 5.4**

        Pinned reference mode detects when source version drifts.
        """
        assume(version_a != version_b)
        fid = uuid.uuid4()
        formulas = {
            fid: FakeFormula(
                id=fid,
                project_id=PROJECT_A,
                expression="X",
                formula_source="custom",
                definition_version=version_b,
            )
        }
        db = _make_db_session(formulas)

        result = await resolve_reference_chain(
            db,
            formula_id=fid,
            project_id=PROJECT_A,
            reference_mode="pinned",
            pinned_version=str(version_a),
            pinned_hash=compute_expression_hash("X"),
        )
        # version_a != version_b → mismatch
        assert result.resolved is False
        assert result.issue["code"] == "PINNED_VERSION_MISMATCH"

    @given(
        n_deps=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_outbox_stale_covers_all_dependents(self, n_deps: int):
        """**Validates: Requirements 5.6**

        Source change produces outbox event listing ALL dependents.
        """
        source_id = uuid.uuid4()
        deps = [
            FakeFormula(
                id=uuid.uuid4(),
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=source_id,
            )
            for _ in range(n_deps)
        ]
        db = _make_db_for_dependents(source_id, deps)
        result = await mark_dependents_stale_via_outbox(
            db, source_formula_id=source_id, project_id=PROJECT_A
        )
        assert result is not None
        assert len(result.dependent_formula_ids) == n_deps
        # All dep ids are included
        dep_id_set = {str(d.id) for d in deps}
        assert set(result.dependent_formula_ids) == dep_id_set


# ═══════════════════════════════════════════════════════════════════════════════
# Edge case: self-referencing formula
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelfReference:
    """Self-referencing formula is a degenerate cycle (length=1)."""

    @pytest.mark.asyncio
    async def test_self_reference_detected_as_cycle(self):
        """A formula referencing itself triggers cycle detection."""
        fid = uuid.uuid4()
        formulas = {
            fid: FakeFormula(
                id=fid,
                project_id=PROJECT_A,
                formula_source="reference",
                reference_formula_id=fid,
                definition_version=1,
            )
        }
        db = _make_db_session(formulas)
        result = await resolve_reference_chain(
            db, formula_id=fid, project_id=PROJECT_A
        )
        assert result.resolved is False
        assert result.cycle is True


# ═══════════════════════════════════════════════════════════════════════════════
# Edge case: _as_uuid utility
# ═══════════════════════════════════════════════════════════════════════════════


class TestAsUuid:
    """Tests for the _as_uuid normalization helper."""

    def test_none(self):
        assert _as_uuid(None) is None

    def test_valid_uuid(self):
        u = uuid.uuid4()
        assert _as_uuid(u) == u

    def test_valid_string(self):
        u = uuid.uuid4()
        assert _as_uuid(str(u)) == u

    def test_invalid_string(self):
        assert _as_uuid("not-a-uuid") is None

    def test_integer(self):
        assert _as_uuid(12345) is None
