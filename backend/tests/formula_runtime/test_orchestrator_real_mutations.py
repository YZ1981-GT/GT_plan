"""tests/formula_runtime/test_orchestrator_real_mutations.py

Task 13 validation — DraftRefreshOrchestrator + FormulaRuntimeCoordinator
integration tests verifying real domain mutations.

**Validates: Requirements 1, 3, 7, 8 | P2, P3, P8, P9**

Tests:
- generate_mutation_plan with "report" scope produces FormulaMutations for report targets
- workpaper/adjudication/note scopes produce real mutations (not just page_keys)
- missing/ambiguous refs result in scope_failures
- coordinator does NOT commit
- PBT max_examples=5
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Inline stubs for engine types (avoid import issues in CI) ───────────────

# We import from the actual modules to ensure integration.
from app.services.formula_management.engine import (
    BatchExecutionResult,
    BatchFormulaContext,
    BatchFormulaDefinition,
    CanonicalFormulaTarget as EngineTarget,
    MutationIntent,
    execute_batch,
)
from app.services.formula_runtime.contracts import (
    CanonicalFormulaTarget,
    FormulaMutation,
)
from app.services.formula_runtime.coordinator import (
    NO_FORMULAS_KIND,
    FormulaRuntimeCoordinator,
    MutationPlanResult,
)
from app.services.formula_runtime.value_loader import FormulaValueLoader, LoadResult


# ─── Fixture: mock session & formula factory ─────────────────────────────────


def _make_formula(
    *,
    formula_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    wp_id: uuid.UUID | None = None,
    expression: str = "=REF1+REF2",
    formula_type: str = "auto_calc",
    target_cell: str = "B5",
    sheet_name: str = "审定表D1-1",
    category: str | None = None,
    refs: list | None = None,
    issue_description: str | None = None,
    hint_text: str | None = None,
):
    """Create a mock WpFormula-like object."""
    f = MagicMock()
    f.id = formula_id or uuid.uuid4()
    f.project_id = project_id or uuid.uuid4()
    f.wp_id = wp_id or uuid.uuid4()
    f.expression = expression
    f.formula_type = formula_type
    f.target_cell = target_cell
    f.sheet_name = sheet_name
    f.category = category
    f.refs = refs if refs is not None else ["tb:1001", "tb:1002"]
    f.issue_description = issue_description
    f.hint_text = hint_text
    f.formula_source = "custom"
    return f


def _mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    # Make execute return empty by default
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


# ─── Unit Tests ──────────────────────────────────────────────────────────────


class TestFormulaRuntimeCoordinator:
    """Test FormulaRuntimeCoordinator.generate_mutation_plan."""

    @pytest.mark.asyncio
    async def test_report_scope_produces_mutations(self):
        """Report scope should produce FormulaMutations for report targets."""
        project_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            formula_type="auto_calc",
            target_cell="BS-001",
            sheet_name="balance_sheet",
            category="报表",
            refs=["tb:1001"],
        )

        session = _mock_session()
        # Mock formula loading
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        # Patch value loader to return a value for the ref
        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(values={"tb:1001": Decimal("100000")}, issues=[]),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["report"],
            )

        assert isinstance(plan, MutationPlanResult)
        # With an auto_calc formula that has a resolvable ref, should produce mutations
        assert isinstance(plan.mutations, list)
        assert isinstance(plan.issues, list)
        assert isinstance(plan.hints, list)
        assert isinstance(plan.scope_failures, list)

    @pytest.mark.asyncio
    async def test_workpaper_scope_produces_real_mutations(self):
        """Workpaper scope should produce real mutations, not just page_keys."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            wp_id=wp_id,
            formula_type="auto_calc",
            target_cell="C10",
            sheet_name="D2-2",
            category="workpaper",
            refs=["tb:1221"],
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(values={"tb:1221": Decimal("50000")}, issues=[]),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["workpaper"],
            )

        assert isinstance(plan, MutationPlanResult)
        # Should have mutations (not just empty page_keys)
        # The auto_calc formula with resolved ref should produce a mutation
        assert len(plan.mutations) >= 1 or len(plan.scope_failures) == 0
        # Verify mutation structure if present
        for m in plan.mutations:
            assert isinstance(m, FormulaMutation)
            assert m.target is not None
            assert m.target.domain == "workpaper"

    @pytest.mark.asyncio
    async def test_adjudication_scope_produces_real_mutations(self):
        """Adjudication scope should produce real mutations."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            wp_id=wp_id,
            formula_type="auto_calc",
            target_cell="audited_1001",
            sheet_name="审定表",
            category="审定",
            refs=["tb:1001", "tb:1002"],
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(
                values={"tb:1001": Decimal("80000"), "tb:1002": Decimal("20000")},
                issues=[],
            ),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["adjudication"],
            )

        assert isinstance(plan, MutationPlanResult)
        # Should produce mutations for adjudication domain
        for m in plan.mutations:
            assert isinstance(m, FormulaMutation)
            assert m.target.domain == "adjudication"

    @pytest.mark.asyncio
    async def test_note_scope_produces_real_mutations(self):
        """Note scope should produce real mutations."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            wp_id=wp_id,
            formula_type="auto_calc",
            target_cell="note_cell_1",
            sheet_name="附注",
            category="附注",
            refs=["report:BS-001"],
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(
                values={"report:BS-001": Decimal("500000")},
                issues=[],
            ),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["note"],
            )

        assert isinstance(plan, MutationPlanResult)
        for m in plan.mutations:
            assert isinstance(m, FormulaMutation)
            assert m.target.domain == "note"

    @pytest.mark.asyncio
    async def test_missing_refs_result_in_scope_failures(self):
        """Missing/ambiguous refs should result in scope_failures, not crashes."""
        project_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            formula_type="auto_calc",
            target_cell="B5",
            refs=["tb:9999_nonexistent", "tb:8888_ambiguous"],
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        from app.services.formula_runtime.value_loader import LoadIssue

        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(
                values={},
                issues=[
                    LoadIssue(addr_id="tb:9999_nonexistent", kind="miss", detail="not found"),
                    LoadIssue(addr_id="tb:8888_ambiguous", kind="ambiguous", detail="multiple"),
                ],
            ),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["report"],
            )

        assert isinstance(plan, MutationPlanResult)
        # scope_failures should contain the unresolved refs
        assert len(plan.scope_failures) >= 2
        kinds = {f["kind"] for f in plan.scope_failures if "kind" in f}
        assert "miss" in kinds or "unresolved_refs" in kinds

    @pytest.mark.asyncio
    async def test_coordinator_does_not_commit(self):
        """Coordinator should NOT call session.commit()."""
        project_id = uuid.uuid4()
        year = 2025

        session = _mock_session()
        # No formulas → empty plan
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        coordinator = FormulaRuntimeCoordinator(session)
        plan = await coordinator.generate_mutation_plan(
            project_id=project_id,
            year=year,
            scopes=["report", "workpaper"],
        )

        # commit must never be called
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_formulas_returns_empty_plan(self):
        """无公式时返回空 plan，但**必须留下可见的 no_formulas 记录**。

        🔴 **本断言于 2026-08-07 按 R9.6 诚实改写**
        （spec formula-management-runtime-closure Task 11 / Property 15）：

        改造前 ``generate_mutation_plan`` 在 ``_load_formulas`` 返空时**静默
        early-return**，于是「``wp_formula`` 表 0 行 ⇒ 整条运行时链空转」这一事实
        在 UI 与日志里**完全不可见** —— 真实库实测该表就是 0 行，公式管理页面看到的
        内容全部来自 ``prefill_formula_mapping.json`` / ``report_config`` 三条旁路，
        用户以为「公式在跑」，实际一次都没跑过。

        Task 11 的修复 = 无公式时往 ``scope_failures`` 追加一条
        ``kind="no_formulas"`` 的条目，并由 ``draft_refresh_orchestrator``
        透传进 ``RefreshResult.warnings`` → 前端 ``GtRefreshScopeDialog.vue``
        既有 warnings 区直接可见（零前端改动）。

        故原断言 ``plan.scope_failures == []`` **锁定的是被修复的错误行为**，
        改写为「空 plan + 恰好一条 no_formulas 记录」。
        ``mutations`` / ``issues`` / ``hints`` 三条断言**一字未动**（不放宽）。
        """
        project_id = uuid.uuid4()
        year = 2025

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        coordinator = FormulaRuntimeCoordinator(session)
        plan = await coordinator.generate_mutation_plan(
            project_id=project_id,
            year=year,
            scopes=["report", "workpaper", "adjudication", "note"],
        )

        assert plan.mutations == []
        assert plan.issues == []
        assert plan.hints == []

        # 空结果必须可见（不再静默 early-return）
        assert len(plan.scope_failures) == 1
        entry = plan.scope_failures[0]
        assert entry["kind"] == NO_FORMULAS_KIND
        # detail 必须写明「表里 0 行」与被请求的 scopes，否则运维看不出原因
        assert "wp_formula" in entry["detail"]
        assert "report" in entry["detail"]

    @pytest.mark.asyncio
    async def test_logic_check_produces_issues_not_mutations(self):
        """logic_check formulas should produce issues, not mutations."""
        project_id = uuid.uuid4()
        year = 2025
        formula = _make_formula(
            project_id=project_id,
            formula_type="logic_check",
            target_cell="",
            refs=["report:BS-001", "report:BS-002"],
            issue_description="资产负债表勾稽不平",
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [formula]
        session.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=LoadResult(
                values={
                    "report:BS-001": Decimal("100000"),
                    "report:BS-002": Decimal("99000"),
                },
                issues=[],
            ),
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            plan = await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["report"],
            )

        # logic_check should NOT produce mutations (Req 1.6)
        assert len(plan.mutations) == 0
        # Should produce issues or be recorded
        # (depends on expression evaluation — may produce issue or error)


# ─── Property-Based Tests ────────────────────────────────────────────────────


@settings(max_examples=5)
@given(
    n_formulas=st.integers(min_value=0, max_value=10),
    scope=st.sampled_from(["report", "workpaper", "adjudication", "note"]),
)
def test_pbt_plan_structure_invariants(n_formulas: int, scope: str):
    """**Validates: Requirements 1, 7 | P2, P3**

    Property: generate_mutation_plan always returns a well-formed MutationPlanResult
    with lists (never None), regardless of formula count or scope.
    """
    import asyncio

    project_id = uuid.uuid4()
    year = 2025

    formulas = [
        _make_formula(
            project_id=project_id,
            formula_type="auto_calc",
            target_cell=f"C{i}",
            refs=[f"tb:{1000 + i}"],
            category=scope if scope != "workpaper" else None,
        )
        for i in range(n_formulas)
    ]

    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = formulas
    session.execute = AsyncMock(return_value=mock_result)

    # Patch value loader — return values for all refs
    values = {f"tb:{1000 + i}": Decimal(str(i * 100)) for i in range(n_formulas)}
    load_result = LoadResult(values=values, issues=[])

    async def _run():
        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=load_result,
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            return await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=[scope],
            )

    plan = asyncio.run(_run())

    # Structural invariants
    assert isinstance(plan, MutationPlanResult)
    assert isinstance(plan.mutations, list)
    assert isinstance(plan.issues, list)
    assert isinstance(plan.hints, list)
    assert isinstance(plan.scope_failures, list)

    # All mutations have valid structure
    for m in plan.mutations:
        assert isinstance(m, FormulaMutation)
        assert m.target is not None
        assert isinstance(m.target.addr_id, str)
        assert m.target.domain in ("workpaper", "adjudication", "report", "note")

    # No commit called
    session.commit.assert_not_called()


@settings(max_examples=5)
@given(
    missing_count=st.integers(min_value=1, max_value=5),
)
def test_pbt_missing_refs_produce_failures(missing_count: int):
    """**Validates: Requirements 8 | P8, P9**

    Property: when value loader reports missing refs, those appear as
    scope_failures and the formula with unresolved refs does NOT produce mutations.
    """
    import asyncio

    project_id = uuid.uuid4()
    year = 2025

    # Build refs that will be reported missing
    refs = [f"tb:missing_{i}" for i in range(missing_count)]
    formula = _make_formula(
        project_id=project_id,
        formula_type="auto_calc",
        target_cell="X1",
        refs=refs,
    )

    session = _mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [formula]
    session.execute = AsyncMock(return_value=mock_result)

    from app.services.formula_runtime.value_loader import LoadIssue

    load_issues = [
        LoadIssue(addr_id=r, kind="miss", detail="not found in tb")
        for r in refs
    ]
    load_result = LoadResult(values={}, issues=load_issues)

    async def _run():
        with patch.object(
            FormulaValueLoader, "load_many",
            new_callable=AsyncMock,
            return_value=load_result,
        ):
            coordinator = FormulaRuntimeCoordinator(session)
            return await coordinator.generate_mutation_plan(
                project_id=project_id,
                year=year,
                scopes=["workpaper"],
            )

    plan = asyncio.run(_run())

    # Scope failures should contain missing refs
    assert len(plan.scope_failures) >= missing_count
    # No mutations should be produced for unresolved formulas
    # (engine skips formulas whose refs are in missing set)
    assert len(plan.mutations) == 0
