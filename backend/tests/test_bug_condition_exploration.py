"""
Bug Condition Exploration Test — pytest-residual-failures-cleanup spec

This test encodes the expected behavior (Property 1: Bug Condition):
  - failed_count <= 50
  - error_count == 0
  - pass_rate >= 0.99

On UNFIXED code, this test is EXPECTED TO FAIL, confirming the bug exists.
After all batches are applied, this test should PASS.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**
"""

import subprocess
import re
import sys


def test_bug_condition_test_suite_health():
    """
    Run the full pytest suite on backend/tests/ and assert health thresholds.

    Bug Condition C(X): failed_count > 50 OR error_count > 0
    Expected Behavior P: failed_count <= 50 AND error_count == 0 AND pass_rate >= 0.99

    This test asserts P (expected behavior). On unfixed code it FAILS,
    confirming the bug condition C(X) is present.
    """
    # Run the full test suite as a subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "--tb=no", "-q",
         "--ignore=backend/tests/test_bug_condition_exploration.py",
         "--ignore=backend/tests/test_preservation_property.py"],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes max for full suite
        cwd=".",
    )

    output = result.stdout + "\n" + result.stderr

    # Parse the summary line, e.g.:
    # "8436 passed, 259 failed, 14 errors, 41 skipped, 116 warnings in 1473.21s"
    # or "8436 passed, 259 failed, 14 errors in 1473.21s"
    passed_count = 0
    failed_count = 0
    error_count = 0

    # Extract passed count
    m_passed = re.search(r"(\d+)\s+passed", output)
    if m_passed:
        passed_count = int(m_passed.group(1))

    # Extract failed count
    m_failed = re.search(r"(\d+)\s+failed", output)
    if m_failed:
        failed_count = int(m_failed.group(1))

    # Extract error count
    m_errors = re.search(r"(\d+)\s+error", output)
    if m_errors:
        error_count = int(m_errors.group(1))

    # Calculate total and pass rate
    total = passed_count + failed_count + error_count
    pass_rate = passed_count / total if total > 0 else 0.0

    # Print diagnostic info for counterexample documentation
    print(f"\n{'='*60}")
    print(f"FULL SUITE RESULTS:")
    print(f"  Passed:    {passed_count}")
    print(f"  Failed:    {failed_count}")
    print(f"  Errors:    {error_count}")
    print(f"  Total:     {total}")
    print(f"  Pass Rate: {pass_rate:.4f} ({pass_rate*100:.2f}%)")
    print(f"{'='*60}")
    print(f"\nBug Condition C(X): failed > 50 OR errors > 0")
    print(f"  failed > 50? {failed_count} > 50 = {failed_count > 50}")
    print(f"  errors > 0?  {error_count} > 0 = {error_count > 0}")
    print(f"  Bug present: {failed_count > 50 or error_count > 0}")
    print(f"{'='*60}\n")

    # Assert expected behavior (Property 1)
    assert failed_count <= 50, (
        f"Bug condition confirmed: {failed_count} failed tests (threshold: <= 50). "
        f"Full results: {passed_count} passed / {failed_count} failed / {error_count} errors / "
        f"{pass_rate*100:.2f}% pass rate"
    )
    assert error_count == 0, (
        f"Bug condition confirmed: {error_count} errors (threshold: 0). "
        f"Full results: {passed_count} passed / {failed_count} failed / {error_count} errors / "
        f"{pass_rate*100:.2f}% pass rate"
    )
    assert pass_rate >= 0.99, (
        f"Bug condition confirmed: pass rate {pass_rate*100:.2f}% (threshold: >= 99%). "
        f"Full results: {passed_count} passed / {failed_count} failed / {error_count} errors"
    )
