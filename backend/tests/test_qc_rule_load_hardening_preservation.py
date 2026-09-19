"""Preservation PBT — QC Python Rule Load Hardening

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

These tests confirm that ALLOWED behavior is preserved both before and after fix:
- Whitelisted paths (app.services.qc_engine.*) load successfully
- JSONPath rules are unaffected by any role
- SQL/regex still raise NotImplementedError
- Timeout behavior unchanged

On UNFIXED code: MUST PASS (baseline behavior intact)
On FIXED code: MUST STILL PASS (no regressions)
"""

import asyncio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.qc_rule_executor import (
    _load_class_from_dotted_path,
    execute_python_rule,
    execute_jsonpath_rule,
    execute_rule,
    RuleExecutionResult,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known whitelisted classes that exist in app.services.qc_engine
_EXISTING_QC_ENGINE_CLASSES = [
    "app.services.qc_engine.ConclusionNotEmptyRule",
    "app.services.qc_engine.AIFillConfirmedRule",
    "app.services.qc_engine.FormulaConsistencyRule",
    "app.services.qc_engine.ReviewerAssignedRule",
    "app.services.qc_engine.UnresolvedAnnotationsRule",
    "app.services.qc_engine.ManualInputCompleteRule",
    "app.services.qc_engine.SubtotalAccuracyRule",
    "app.services.qc_engine.CrossRefConsistencyRule",
]

whitelisted_paths = st.sampled_from(_EXISTING_QC_ENGINE_CLASSES)

# Roles for jsonpath rule creation
all_roles = st.sampled_from(["qc", "admin", "partner"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule_def(
    rule_code: str = "QC-TEST",
    expression_type: str = "python",
    expression: str = "app.services.qc_engine.ConclusionNotEmptyRule",
    severity: str = "blocking",
    scope: str = "workpaper",
    parameters_schema: dict | None = None,
) -> MagicMock:
    """Create a mock QcRuleDefinition."""
    rule = MagicMock()
    rule.rule_code = rule_code
    rule.expression_type = expression_type
    rule.expression = expression
    rule.severity = severity
    rule.scope = scope
    rule.parameters_schema = parameters_schema
    return rule


# ---------------------------------------------------------------------------
# Property 3: Preservation — Allowed Path Loads Successfully
# ---------------------------------------------------------------------------


class TestPreservationAllowedPathLoads:
    """Property 3: Whitelisted paths load successfully.

    **Validates: Requirements 3.1, 3.3**
    """

    @settings(max_examples=5)
    @given(path=whitelisted_paths)
    def test_whitelisted_path_loads_class(self, path: str):
        """Any dotted path starting with allowed prefix AND existing module/class
        must load successfully (same behavior as original).

        **Validates: Requirements 3.1**
        """
        cls = _load_class_from_dotted_path(path)
        assert cls is not None
        # Verify it's actually a class with the expected name
        expected_class_name = path.rsplit(".", 1)[1]
        assert cls.__name__ == expected_class_name

    def test_concrete_conclusion_not_empty_rule_loads(self):
        """Concrete: ConclusionNotEmptyRule always loads.

        **Validates: Requirements 3.1**
        """
        cls = _load_class_from_dotted_path(
            "app.services.qc_engine.ConclusionNotEmptyRule"
        )
        assert cls.__name__ == "ConclusionNotEmptyRule"
        # Should have check method (QCRule protocol)
        assert hasattr(cls, "check")


# ---------------------------------------------------------------------------
# Property 4: Preservation — JsonPath Rules Unaffected
# ---------------------------------------------------------------------------


class TestPreservationJsonpathUnaffected:
    """Property 4: JsonPath rules unaffected by any role.

    **Validates: Requirements 3.2**
    """

    @pytest.mark.asyncio
    async def test_jsonpath_rule_execution_unaffected(self):
        """JSONPath rule execution works regardless of this fix.

        **Validates: Requirements 3.2**
        """
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={"expect_match": True},
        )
        parsed_data = {"conclusion": "审计结论已填写"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is True
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_jsonpath_rule_finding_generated(self):
        """JSONPath rule produces findings when condition unmet.

        **Validates: Requirements 3.2**
        """
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={"expect_match": True},
        )
        parsed_data = {}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is False
        assert len(result.findings) > 0


# ---------------------------------------------------------------------------
# Preservation — SQL/Regex still raise NotImplementedError
# ---------------------------------------------------------------------------


class TestPreservationSqlRegexUnchanged:
    """SQL and Regex types continue to raise NotImplementedError.

    **Validates: Requirements 3.4**
    """

    @pytest.mark.asyncio
    async def test_sql_type_raises_not_implemented(self):
        """expression_type='sql' still raises NotImplementedError."""
        rule_def = _make_rule_def(expression_type="sql", expression="SELECT 1")
        with pytest.raises(NotImplementedError, match="sql"):
            await execute_rule(rule_def)

    @pytest.mark.asyncio
    async def test_regex_type_raises_not_implemented(self):
        """expression_type='regex' still raises NotImplementedError."""
        rule_def = _make_rule_def(expression_type="regex", expression=".*")
        with pytest.raises(NotImplementedError, match="regex"):
            await execute_rule(rule_def)


# ---------------------------------------------------------------------------
# Preservation — Timeout behavior unchanged
# ---------------------------------------------------------------------------


class TestPreservationTimeoutUnchanged:
    """Timeout behavior remains the same.

    **Validates: Requirements 3.5**
    """

    @pytest.mark.asyncio
    async def test_timeout_returns_timed_out_error(self):
        """execute_python_rule timeout → RuleExecutionResult(passed=False, error contains 'timed out')"""
        rule_def = _make_rule_def(
            expression="app.services.qc_engine.ConclusionNotEmptyRule"
        )

        # Mock a slow check method
        async def slow_check(ctx):
            await asyncio.sleep(5)
            return []

        with patch(
            "app.services.qc_rule_executor._load_class_from_dotted_path"
        ) as mock_load:
            mock_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.check = slow_check
            mock_cls.return_value = mock_instance
            mock_load.return_value = mock_cls

            result = await execute_python_rule(rule_def, MagicMock(), timeout=0.1)
            assert result.passed is False
            assert "timed out" in result.error.lower()
