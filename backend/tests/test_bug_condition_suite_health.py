"""
Bug Condition Exploration Test: Test Suite Health Below Threshold

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**

This test encodes the EXPECTED behavior after the bugfix is applied:
- failed_count <= 50
- error_count == 0
- pass_rate >= 0.99

On UNFIXED code, this test is EXPECTED TO FAIL, confirming the bug exists.
The counterexample documents the actual suite health metrics.

Bug Condition (formal):
  isBugCondition(X) = X.failed_count > 50 OR X.error_count > 0
"""

import subprocess
import re
import sys


def _run_full_suite() -> dict:
    """Run the full pytest suite and parse the summary line.

    Returns dict with keys: passed, failed, errors, warnings, skipped, total, pass_rate
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "--tb=no", "-q"],
        capture_output=True,
        text=True,
        timeout=600,  # 10 minutes max
        cwd=".",
    )

    # Combine stdout and stderr for parsing
    output = result.stdout + "\n" + result.stderr

    # Parse the pytest summary line, e.g.:
    # "8436 passed, 259 failed, 41 skipped, 14 errors, 116 warnings in 1473.21s"
    # or variants like "8436 passed, 259 failed, 14 errors in 1473.21s"
    passed = 0
    failed = 0
    errors = 0
    skipped = 0
    warnings = 0

    # Look for the summary line (last non-empty lines)
    lines = output.strip().split("\n")

    for line in reversed(lines):
        # Match patterns like "X passed", "X failed", "X error(s)", etc.
        passed_match = re.search(r"(\d+)\s+passed", line)
        failed_match = re.search(r"(\d+)\s+failed", line)
        error_match = re.search(r"(\d+)\s+error", line)
        skipped_match = re.search(r"(\d+)\s+skipped", line)
        warnings_match = re.search(r"(\d+)\s+warning", line)

        if passed_match or failed_match or error_match:
            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
            if error_match:
                errors = int(error_match.group(1))
            if skipped_match:
                skipped = int(skipped_match.group(1))
            if warnings_match:
                warnings = int(warnings_match.group(1))
            break

    total = passed + failed + errors
    pass_rate = passed / total if total > 0 else 0.0

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "warnings": warnings,
        "total": total,
        "pass_rate": pass_rate,
    }


def test_suite_health_below_threshold():
    """
    Property 1: Bug Condition - Test Suite Health Below Threshold

    Asserts the test suite meets acceptable health thresholds:
    - failed_count <= 50
    - error_count == 0
    - pass_rate >= 0.99

    On UNFIXED code this WILL FAIL, confirming the bug exists.
    The failure message documents the actual counterexample.
    """
    metrics = _run_full_suite()

    # Build detailed failure message as counterexample documentation
    counterexample = (
        f"Full suite reports: "
        f"{metrics['failed']} failed / "
        f"{metrics['errors']} errors / "
        f"{metrics['passed']} passed / "
        f"{metrics['pass_rate']:.2%} pass rate "
        f"(total={metrics['total']}, skipped={metrics['skipped']})"
    )

    # Assert health thresholds
    assert metrics["failed"] <= 50, (
        f"Bug condition confirmed: failed_count={metrics['failed']} > 50. "
        f"Counterexample: {counterexample}"
    )
    assert metrics["errors"] == 0, (
        f"Bug condition confirmed: error_count={metrics['errors']} > 0. "
        f"Counterexample: {counterexample}"
    )
    assert metrics["pass_rate"] >= 0.99, (
        f"Bug condition confirmed: pass_rate={metrics['pass_rate']:.4f} < 0.99. "
        f"Counterexample: {counterexample}"
    )

    # If we reach here, the bug is fixed
    print(f"Suite health OK: {counterexample}")
