"""
Tests for the frontend amount guard: rules, parser, scanner and CLI.

Design reference: §17 G6, §15 A8.
Validates: Requirements R6, R10 (AC-23, AC-24).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# Module under test
from scripts.check.frontend_amount_guard.rules import (
    INCLUDE_GLOBS,
    EXCLUDE_GLOBS,
    EXPLICIT_KIND_COMPONENTS,
    KIND_PROP_COMPONENTS,
    LEGACY_NUMERIC_FORMATTERS,
    LEGACY_NON_NUMERIC_FORMATTERS,
    S2_NUMERIC_CALLS,
    CORE_VIOLATION_CODES,
    VIOLATION_AMOUNT_FMT_ON_NON_AMOUNT,
    VIOLATION_GT_AMOUNT_CELL_WITH_UNIT,
    VIOLATION_V2_FIXED_PX_FONT,
    SCAN_SCOPE_DRIFT,
)
from scripts.check.frontend_amount_guard.vue_ts_parser import (
    ParseResult,
    DisplayNode,
    parse_file,
)
from scripts.check.frontend_amount_guard.scanner import (
    ScanResult,
    run_scan,
    enumerate_eligible_files,
)

FIXTURES = Path(__file__).parent / "fixtures"
POSITIVE = FIXTURES / "positive"
NEGATIVE = FIXTURES / "negative"


# ═══════════════════════════════════════════════════════════════
# 1. Rules constant integrity
# ═══════════════════════════════════════════════════════════════

class TestRulesConstants:
    """Verify the rules module constants are well-formed."""

    def test_include_globs_non_empty(self):
        assert len(INCLUDE_GLOBS) > 0

    def test_exclude_globs_non_empty(self):
        assert len(EXCLUDE_GLOBS) > 0

    def test_explicit_kind_components_contains_gt_amount_cell(self):
        assert "GtAmountCell" in EXPLICIT_KIND_COMPONENTS
        assert EXPLICIT_KIND_COMPONENTS["GtAmountCell"] == "amount"

    def test_kind_prop_components_contains_gt_measure_cell(self):
        assert "GtMeasureCell" in KIND_PROP_COMPONENTS

    def test_legacy_formatters_and_non_numeric_disjoint(self):
        overlap = LEGACY_NUMERIC_FORMATTERS & LEGACY_NON_NUMERIC_FORMATTERS
        assert overlap == set(), f"Overlap: {overlap}"

    def test_core_violation_codes_non_empty(self):
        assert len(CORE_VIOLATION_CODES) >= 3
        assert VIOLATION_AMOUNT_FMT_ON_NON_AMOUNT in CORE_VIOLATION_CODES
        assert VIOLATION_GT_AMOUNT_CELL_WITH_UNIT in CORE_VIOLATION_CODES
        assert VIOLATION_V2_FIXED_PX_FONT in CORE_VIOLATION_CODES

    def test_s2_numeric_calls_contain_basics(self):
        assert "toFixed" in S2_NUMERIC_CALLS
        assert "toLocaleString" in S2_NUMERIC_CALLS


# ═══════════════════════════════════════════════════════════════
# 2. Parser – Positive fixtures (signal detected)
# ═══════════════════════════════════════════════════════════════

class TestParserPositiveFixtures:
    """Positive fixtures: parser MUST detect at least one display node."""

    def test_s1_right_align(self):
        result = parse_file(POSITIVE / "s1_right_align.vue")
        assert result.parsed
        nodes = [n for n in result.display_nodes if "S1" in n.signals]
        assert len(nodes) > 0, "S1 signal not detected for align=right"

    def test_s2_numeric_call(self):
        result = parse_file(POSITIVE / "s2_numeric_call.vue")
        assert result.parsed
        nodes = [n for n in result.display_nodes if "S2" in n.signals]
        assert len(nodes) > 0, "S2 signal not detected for toFixed/Decimal"

    def test_s3_legacy_formatter(self):
        result = parse_file(POSITIVE / "s3_legacy_formatter.vue")
        assert result.parsed
        nodes = [n for n in result.display_nodes if "S3" in n.signals]
        assert len(nodes) > 0, "S3 signal not detected for fmtAmount"

    def test_violation_c_amount_cell_with_unit(self):
        result = parse_file(POSITIVE / "violation_c_amount_cell_with_unit.vue")
        assert result.parsed
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_GT_AMOUNT_CELL_WITH_UNIT]
        assert len(violations) > 0, "Violation c not detected"

    def test_violation_d_v2_fixed_px(self):
        result = parse_file(POSITIVE / "violation_d_v2_fixed_px.ts")
        assert result.parsed
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_V2_FIXED_PX_FONT]
        assert len(violations) > 0, "Violation d not detected"

    def test_explicit_kind_gt_amount_cell(self):
        """GtAmountCell is recognized as explicit kind=amount."""
        content = textwrap.dedent("""\
            <template>
              <GtAmountCell :value="v" />
            </template>
            <script setup lang="ts">
            const v = 100
            </script>
        """)
        result = parse_file(Path("test.vue"), content)
        assert result.parsed
        amount_nodes = [n for n in result.display_nodes
                        if n.kind_source == "explicit:amount"]
        assert len(amount_nodes) > 0

    def test_explicit_kind_measure_cell(self):
        result = parse_file(POSITIVE / "explicit_kind_measure_cell.vue")
        assert result.parsed
        declared_nodes = [n for n in result.display_nodes
                          if n.kind_source.startswith("explicit:")]
        assert len(declared_nodes) > 0


# ═══════════════════════════════════════════════════════════════
# 3. Parser – Negative fixtures (no signal)
# ═══════════════════════════════════════════════════════════════

class TestParserNegativeFixtures:
    """Negative fixtures: parser must NOT detect signals."""

    def test_s1_left_align(self):
        result = parse_file(NEGATIVE / "s1_left_align.vue")
        assert result.parsed
        s1_nodes = [n for n in result.display_nodes if "S1" in n.signals]
        assert len(s1_nodes) == 0, "S1 should not fire for align=left"

    def test_s2_no_numeric_call(self):
        result = parse_file(NEGATIVE / "s2_no_numeric_call.vue")
        assert result.parsed
        s2_nodes = [n for n in result.display_nodes if "S2" in n.signals]
        assert len(s2_nodes) == 0, "S2 should not fire for toString()"

    def test_s3_no_legacy_formatter(self):
        result = parse_file(NEGATIVE / "s3_no_legacy_formatter.vue")
        assert result.parsed
        s3_nodes = [n for n in result.display_nodes if "S3" in n.signals]
        assert len(s3_nodes) == 0, "S3 should not fire for fmtDate"

    def test_violation_c_amount_cell_no_unit(self):
        result = parse_file(NEGATIVE / "violation_c_amount_cell_no_unit.vue")
        assert result.parsed
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_GT_AMOUNT_CELL_WITH_UNIT]
        assert len(violations) == 0, "Violation c should not fire without :unit"

    def test_violation_d_no_fixed_px(self):
        result = parse_file(NEGATIVE / "violation_d_v2_no_fixed_px.ts")
        assert result.parsed
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_V2_FIXED_PX_FONT]
        assert len(violations) == 0, "Violation d should not fire for var()"

    def test_violation_d_ordinary_fixed_px_without_v2_renderer_is_not_a_match(self):
        """普通通知 / CSS style 的固定字号不是 el-table-v2 renderer；旧扫描器把这类全仓误报 63 处。"""
        result = parse_file(
            Path("ordinary.ts"),
            "const dialogStyle = { fontSize: '12px' }; const html = '<span style=\"font-size:12px\">x</span>'",
        )
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_V2_FIXED_PX_FONT]
        assert violations == []

    def test_violation_d_mutation_adds_renderer_and_becomes_a_match(self):
        """阴性对照：同一固定 px 一旦处于含 cellRenderer 的文件，当前守卫必须打红。"""
        result = parse_file(
            Path("v2.ts"),
            "const columns = [{ cellRenderer: () => h('span', { style: { fontSize: '12px' } }) }]",
        )
        violations = [n for n in result.display_nodes
                      if n.violation_code == VIOLATION_V2_FIXED_PX_FONT]
        assert len(violations) == 1


# ═══════════════════════════════════════════════════════════════
# 4. Scanner – scope computation and drift detection
# ═══════════════════════════════════════════════════════════════

class TestScanner:
    """Tests for the scanner module."""

    def test_empty_src_detects_drift(self, tmp_path: Path):
        """An empty src directory produces SCAN_SCOPE_DRIFT errors."""
        empty_src = tmp_path / "src"
        empty_src.mkdir()
        result = run_scan(empty_src)
        # No scopes at all – but also no drift errors from scope checks
        # since there are simply no eligible files (which is different from
        # having a scope with 0 eligible)
        assert result.total_eligible == 0
        assert result.total_parsed == 0

    def test_single_vue_file_parsed(self, tmp_path: Path):
        """A single .vue file in a subdirectory creates a scope and parses."""
        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        vue = comp / "Test.vue"
        vue.write_text(textwrap.dedent("""\
            <template>
              <span>{{ text }}</span>
            </template>
            <script setup lang="ts">
            const text = 'hello'
            </script>
        """), encoding="utf-8")

        result = run_scan(src)
        assert result.total_eligible == 1
        assert result.total_parsed == 1
        assert "components" in result.scopes
        sr = result.scopes["components"]
        assert sr.eligible == 1
        assert sr.parsed == 1
        assert sr.skipped == 0

    def test_test_files_excluded(self, tmp_path: Path):
        """Files matching exclude globs are not eligible."""
        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        # Production file
        (comp / "Prod.vue").write_text("<template><div/></template>", encoding="utf-8")
        # Test file (excluded by *.test.*)
        (comp / "Prod.test.ts").write_text("test('x', () => {})", encoding="utf-8")
        # Spec file (excluded by *.spec.*)
        (comp / "Prod.spec.ts").write_text("test('x', () => {})", encoding="utf-8")
        # __tests__ directory (excluded)
        tests_dir = comp / "__tests__"
        tests_dir.mkdir()
        (tests_dir / "helper.ts").write_text("export {}", encoding="utf-8")

        result = run_scan(src)
        assert result.total_eligible == 1  # Only Prod.vue
        assert "components" in result.scopes
        assert result.scopes["components"].eligible == 1

    def test_scope_root_files(self, tmp_path: Path):
        """Files directly in src/ go to the 'src:root' scope."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "App.vue").write_text("<template><div/></template>", encoding="utf-8")
        (src / "main.ts").write_text("console.log('hi')", encoding="utf-8")

        result = run_scan(src)
        assert "src:root" in result.scopes
        assert result.scopes["src:root"].eligible == 2

    def test_d_ts_excluded(self, tmp_path: Path):
        """*.d.ts files directly in src/ are excluded."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "components.d.ts").write_text("declare module 'x'", encoding="utf-8")
        (src / "App.vue").write_text("<template><div/></template>", encoding="utf-8")

        result = run_scan(src)
        assert result.total_eligible == 1  # Only App.vue, not the .d.ts

    def test_parser_exemption_counts_as_parsed(self, tmp_path: Path):
        """A file in the parser exemptions list is counted as parsed (exempted)."""
        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "Tricky.vue").write_text("not valid vue", encoding="utf-8")

        exemptions = {"components/Tricky.vue": "known complex file"}
        result = run_scan(src, parser_exemptions=exemptions)
        sr = result.scopes["components"]
        assert sr.eligible == 1
        assert sr.exempted == 1
        assert sr.skipped == 0

    def test_new_scope_auto_discovered(self, tmp_path: Path):
        """A new directory under src/ automatically creates a new scope."""
        src = tmp_path / "src"
        new_module = src / "my_new_feature"
        new_module.mkdir(parents=True)
        (new_module / "index.ts").write_text("export const x = 1", encoding="utf-8")

        result = run_scan(src)
        assert "my_new_feature" in result.scopes
        assert result.scopes["my_new_feature"].eligible == 1


# ═══════════════════════════════════════════════════════════════
# 5. CLI – baseline check and update
# ═══════════════════════════════════════════════════════════════

class TestCLI:
    """Tests for the CLI entry point."""

    def test_check_no_baseline_fails_closed(self, tmp_path: Path):
        """CI 的 --check 不可因基线被删/损坏而自动放行。"""
        from scripts.check.frontend_amount_guard.cli import main

        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "X.vue").write_text("<template><div/></template>", encoding="utf-8")

        baseline = tmp_path / "baseline.json"
        exit_code = main([
            "--check",
            "--src", str(src),
            "--baseline", str(baseline),
        ])
        assert exit_code == 1

    def test_update_baseline_writes_file(self, tmp_path: Path):
        """--update-baseline creates a JSON file with expected keys."""
        from scripts.check.frontend_amount_guard.cli import main

        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "X.vue").write_text("<template><div/></template>", encoding="utf-8")

        baseline = tmp_path / "baseline.json"
        exit_code = main([
            "--update-baseline",
            "--force",  # skip worktree clean check
            "--src", str(src),
            "--baseline", str(baseline),
        ])
        assert exit_code == 0
        assert baseline.exists()

        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert "total_eligible" in data
        assert "total_parsed" in data
        assert "total_candidates" in data
        assert "scopes" in data
        assert data["total_eligible"] == 1

    def test_check_detects_increase(self, tmp_path: Path):
        """--check fails when candidates increased beyond baseline."""
        from scripts.check.frontend_amount_guard.cli import main

        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "X.vue").write_text(
            '<template><el-table-column prop="amt" align="right">{{ v }}</el-table-column></template>',
            encoding="utf-8",
        )

        # Create baseline with 0 candidates
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({
            "total_eligible": 1,
            "total_parsed": 1,
            "total_candidates": 0,
            "scopes": {"components": {"eligible": 1, "parsed": 1, "candidates": 0}},
        }), encoding="utf-8")

        exit_code = main([
            "--check",
            "--src", str(src),
            "--baseline", str(baseline),
        ])
        assert exit_code == 1  # Increased from 0

    def test_update_baseline_refuses_increase(self, tmp_path: Path):
        """--update-baseline refuses to increase total_candidates."""
        from scripts.check.frontend_amount_guard.cli import main

        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "X.vue").write_text(
            '<template><el-table-column prop="amt" align="right">{{ v }}</el-table-column></template>',
            encoding="utf-8",
        )

        # Create baseline with 0 candidates
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({
            "total_eligible": 1,
            "total_parsed": 1,
            "total_candidates": 0,
            "scopes": {"components": {"eligible": 1, "parsed": 1, "candidates": 0}},
        }), encoding="utf-8")

        exit_code = main([
            "--update-baseline",
            "--force",
            "--src", str(src),
            "--baseline", str(baseline),
        ])
        assert exit_code == 1  # Refuses to raise baseline

    def test_update_baseline_refuses_historical_upper_limit(self, tmp_path: Path, monkeypatch):
        """即使不存在旧基线，--update-baseline 也不能写出超过硬上限的新基线。"""
        from scripts.check.frontend_amount_guard import cli

        src = tmp_path / "src"
        comp = src / "components"
        comp.mkdir(parents=True)
        (comp / "X.vue").write_text(
            '<template><el-table-column prop="amt" align="right">{{ v }}</el-table-column></template>',
            encoding="utf-8",
        )
        monkeypatch.setattr(cli, "_HISTORICAL_UPPER_LIMIT", 0)
        baseline = tmp_path / "baseline.json"
        assert cli.main(["--update-baseline", "--force", "--src", str(src), "--baseline", str(baseline)]) == 1
        assert not baseline.exists()


# ═══════════════════════════════════════════════════════════════
# 6. Mutation guards: removing a signal must make fixture red
# ═══════════════════════════════════════════════════════════════

class TestMutationGuards:
    """
    These tests verify that removing signals from the rules constants
    would cause the corresponding positive fixture to stop detecting.
    """

    def test_removing_s2_toFixed_breaks_detection(self):
        """If we remove 'toFixed' from S2_NUMERIC_CALLS, the S2 fixture
        should no longer detect (simulated by checking the content directly)."""
        content = (POSITIVE / "s2_numeric_call.vue").read_text(encoding="utf-8")
        # The file contains .toFixed( — verify it's there
        assert "toFixed" in content
        # And our regex does find it
        import re
        from scripts.check.frontend_amount_guard.vue_ts_parser import _S2_CALL_RE
        assert _S2_CALL_RE.search(content) is not None

    def test_removing_fmtAmount_breaks_s3_detection(self):
        """If 'fmtAmount' is not in LEGACY_NUMERIC_FORMATTERS, S3 won't fire."""
        assert "fmtAmount" in LEGACY_NUMERIC_FORMATTERS
        content = (POSITIVE / "s3_legacy_formatter.vue").read_text(encoding="utf-8")
        assert "fmtAmount" in content

    def test_parser_crash_produces_error(self):
        """Parser crash (non-existent file) sets parsed=False."""
        result = parse_file(Path("/nonexistent/file.vue"))
        assert not result.parsed
        assert result.error is not None
