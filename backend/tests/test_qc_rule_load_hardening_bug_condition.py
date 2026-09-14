"""Bug Condition Exploration PBT — QC Python Rule Load Hardening

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**

This test encodes the EXPECTED (fixed) behavior:
- Disallowed paths (not starting with allowed prefixes) MUST raise ImportError
- Non-admin users MUST get 403 when creating/editing python-type rules

On UNFIXED code, these tests WILL FAIL — confirming the bug exists.
After fix, these tests WILL PASS — confirming the bug is resolved.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock

from app.services.qc_rule_executor import _load_class_from_dotted_path


# ---------------------------------------------------------------------------
# Strategies: Generate disallowed dotted paths
# ---------------------------------------------------------------------------

# Prefixes that are NOT in the whitelist
_DISALLOWED_PREFIXES = [
    "app.services.data_lifecycle_service.",
    "app.services.import_job_runner.",
    "app.services.background_job_service.",
    "app.core.database.",
    "os.",
    "subprocess.",
]

# Strategy: generate a disallowed dotted path that looks like module.Class
disallowed_dotted_paths = st.sampled_from([
    "app.services.data_lifecycle_service.DataLifecycleService",
    "app.services.import_job_runner.ImportJobRunner",
    "app.core.database.AsyncSession",
    "app.services.background_job_service.BackgroundJobService",
])


# ---------------------------------------------------------------------------
# Property 1: Bug Condition - Disallowed Path MUST raise ImportError
# ---------------------------------------------------------------------------


class TestBugConditionDisallowedPath:
    """Property 1: Disallowed paths must raise ImportError after fix.

    **Validates: Requirements 2.1**
    """

    @settings(max_examples=5)
    @given(path=disallowed_dotted_paths)
    def test_disallowed_path_raises_import_error(self, path: str):
        """Any dotted path NOT starting with allowed prefixes must raise ImportError.

        On unfixed code: FAILS (paths load successfully — the bug)
        On fixed code: PASSES (ImportError raised)
        """
        with pytest.raises(ImportError, match="Disallowed rule class path"):
            _load_class_from_dotted_path(path)

    def test_concrete_data_lifecycle_service_disallowed(self):
        """Concrete case: DataLifecycleService path must be blocked.

        **Validates: Requirements 1.1, 2.1**
        """
        with pytest.raises(ImportError, match="Disallowed rule class path"):
            _load_class_from_dotted_path(
                "app.services.data_lifecycle_service.DataLifecycleService"
            )

    def test_concrete_import_job_runner_disallowed(self):
        """Concrete case: ImportJobRunner path must be blocked.

        **Validates: Requirements 1.2, 2.1**
        """
        with pytest.raises(ImportError, match="Disallowed rule class path"):
            _load_class_from_dotted_path(
                "app.services.import_job_runner.ImportJobRunner"
            )


# ---------------------------------------------------------------------------
# Property 2: Bug Condition - Non-Admin MUST get 403 for python rules
# ---------------------------------------------------------------------------


class TestBugConditionNonAdminPythonRule:
    """Property 2: Non-admin users must get 403 when creating python-type rules.

    **Validates: Requirements 2.2**

    Tests the router-level check by importing and calling the endpoint
    with a mocked non-admin user. The guard should fire BEFORE any service call.
    """

    @pytest.mark.asyncio
    async def test_non_admin_create_python_rule_returns_403(self):
        """role='qc' user creating python rule must get 403.

        On unfixed code: FAILS (no guard, reaches service layer)
        On fixed code: PASSES (returns 403 before service call)
        """
        from fastapi import HTTPException
        from app.routers.qc_rules import create_rule, QcRuleCreateRequest

        # Mock the db session (AsyncMock so awaits don't crash)
        from unittest.mock import AsyncMock
        mock_db = AsyncMock()

        # Mock a non-admin user (role='qc')
        mock_user = MagicMock()
        mock_user.role = "qc"
        mock_user.id = "test-user-id"

        body = QcRuleCreateRequest(
            rule_code="QC-TEST-EXPLOIT",
            severity="blocking",
            scope="workpaper",
            title="Test exploit rule",
            description="Attempting to create python rule as non-admin",
            expression_type="python",
            expression="app.services.data_lifecycle_service.DataLifecycleService",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_rule(body=body, db=mock_db, current_user=mock_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_update_python_rule_returns_403(self):
        """role='qc' user updating to python rule must get 403.

        On unfixed code: FAILS (no guard, reaches service layer)
        On fixed code: PASSES (returns 403 before service call)
        """
        from uuid import uuid4
        from fastapi import HTTPException
        from unittest.mock import AsyncMock
        from app.routers.qc_rules import update_rule, QcRuleUpdateRequest

        # Mock the db session (AsyncMock so awaits don't crash)
        mock_db = AsyncMock()

        # Mock a non-admin user (role='qc')
        mock_user = MagicMock()
        mock_user.role = "qc"
        mock_user.id = "test-user-id"

        body = QcRuleUpdateRequest(
            expression_type="python",
            expression="app.services.data_lifecycle_service.DataLifecycleService",
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_rule(
                rule_id=uuid4(), body=body, db=mock_db, current_user=mock_user
            )

        assert exc_info.value.status_code == 403
