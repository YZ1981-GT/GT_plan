"""
Preservation Property Tests — pytest-residual-failures-cleanup spec

Property 2: No Regression on Currently-Passing Tests
  - passed_count >= 8436 (baseline from unfixed code)
  - 0 files modified in backend/app/ (production code untouched)

These tests verify that fixes to test infrastructure do NOT regress
currently-passing tests or modify production code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

import subprocess
import re
import sys
from pathlib import Path


BASELINE_PASSED_COUNT = 8436


def test_preservation_no_regression():
    """
    Run the full pytest suite and assert passed_count >= baseline.

    This confirms that test infrastructure fixes do not break
    any currently-passing tests.

    **Validates: Requirements 3.1, 3.2**
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "--tb=no", "-q",
         "--ignore=backend/tests/test_bug_condition_exploration.py",
         "--ignore=backend/tests/test_preservation_property.py"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=".",
    )

    output = result.stdout + "\n" + result.stderr

    passed_count = 0
    m_passed = re.search(r"(\d+)\s+passed", output)
    if m_passed:
        passed_count = int(m_passed.group(1))

    print(f"\nPreservation Check: passed_count={passed_count}, baseline={BASELINE_PASSED_COUNT}")

    assert passed_count >= BASELINE_PASSED_COUNT, (
        f"Regression detected: {passed_count} passed (baseline: {BASELINE_PASSED_COUNT}). "
        f"Some previously-passing tests are now failing."
    )


def test_preservation_no_production_code_changes():
    """
    Verify that no files in backend/app/ have been modified.

    This confirms that all fixes are confined to test infrastructure
    and production code remains untouched.

    **Validates: Requirements 3.2**
    """
    result = subprocess.run(
        ["git", "diff", "--stat", "backend/app/"],
        capture_output=True,
        text=True,
        cwd=".",
    )

    diff_output = result.stdout.strip()

    print(f"\ngit diff --stat backend/app/:\n{diff_output or '(no changes)'}")

    assert diff_output == "", (
        f"Production code modified! Changes detected in backend/app/:\n{diff_output}"
    )
