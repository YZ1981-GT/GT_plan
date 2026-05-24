"""跨 sheet 公式追溯 — Property-Based Tests + E2E

Feature: advanced-query-enhancements-p1p2
Tests:
  - Property 6: 跨 sheet 引用解析
  - Property 7: 深度终止
  - Property 8: 循环检测
  - E2E: 追溯端点集成测试
"""

import pytest
from hypothesis import given, settings, strategies as st, assume

from app.services.custom_query.cross_sheet_resolver import (
    CrossSheetResolver,
    RefChainNode,
    RefChainResponse,
    cross_sheet_resolver,
    parse_cross_sheet_refs,
    _cell_ref_to_indices,
)


# ─── Strategies ──────────────────────────────────────────────────────────────

# Valid sheet names (must start with letter or Chinese char, matching the regex)
st_sheet_name = st.text(
    alphabet=st.sampled_from(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        "审定表底稿目录资产负债利润现金流量"
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: "!" not in s and "'" not in s and s[0].isalpha())

# Valid cell references (A1 to ZZ9999)
st_col_letter = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=2
)
st_row_number = st.integers(min_value=1, max_value=9999)
st_cell_ref = st.builds(lambda c, r: f"{c}{r}", st_col_letter, st_row_number)


# ─── Property 6: Cross-sheet reference parsing ──────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 6: Cross-sheet reference parsing
# For any formula with cross-sheet refs, parser extracts all (sheet, cell) pairs correctly;
# for formulas without cross-sheet refs, returns empty list.


class TestProperty6CrossSheetRefParsing:
    """Property 6: 跨 sheet 引用解析

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=20)
    @given(sheet=st_sheet_name, cell=st_cell_ref)
    def test_single_ref_extracted(self, sheet: str, cell: str):
        """For any single cross-sheet ref =Sheet!Cell, parser extracts (sheet, cell)."""
        formula = f"={sheet}!{cell}"
        refs = parse_cross_sheet_refs(formula)
        assert len(refs) >= 1
        # At least one match should have the correct sheet and cell (uppercased)
        found = any(s == sheet and c == cell.upper() for s, c in refs)
        assert found, f"Expected ({sheet}, {cell.upper()}) in {refs}"

    @settings(max_examples=20)
    @given(sheet=st_sheet_name, cell=st_cell_ref)
    def test_quoted_sheet_extracted(self, sheet: str, cell: str):
        """For any quoted sheet ref ='Sheet'!Cell, parser extracts (sheet, cell)."""
        formula = f"='{sheet}'!{cell}"
        refs = parse_cross_sheet_refs(formula)
        assert len(refs) >= 1
        found = any(s == sheet and c == cell.upper() for s, c in refs)
        assert found, f"Expected ({sheet}, {cell.upper()}) in {refs}"

    @settings(max_examples=20)
    @given(
        sheet1=st_sheet_name,
        cell1=st_cell_ref,
        sheet2=st_sheet_name,
        cell2=st_cell_ref,
    )
    def test_multiple_refs_extracted(
        self, sheet1: str, cell1: str, sheet2: str, cell2: str
    ):
        """For formulas with multiple cross-sheet refs, all pairs are extracted."""
        formula = f"={sheet1}!{cell1}+{sheet2}!{cell2}"
        refs = parse_cross_sheet_refs(formula)
        assert len(refs) >= 2
        found1 = any(s == sheet1 and c == cell1.upper() for s, c in refs)
        found2 = any(s == sheet2 and c == cell2.upper() for s, c in refs)
        assert found1, f"Expected ({sheet1}, {cell1.upper()}) in {refs}"
        assert found2, f"Expected ({sheet2}, {cell2.upper()}) in {refs}"

    @settings(max_examples=20)
    @given(
        local_formula=st.sampled_from([
            "=A1+B2",
            "=SUM(A1:A10)",
            "=IF(A1>0,B1,C1)",
            "=VLOOKUP(A1,B:C,2,FALSE)",
            "123",
            "hello",
            "",
        ])
    )
    def test_no_cross_sheet_returns_empty(self, local_formula: str):
        """For formulas without cross-sheet refs, returns empty list."""
        refs = parse_cross_sheet_refs(local_formula)
        assert refs == []

    def test_none_formula_returns_empty(self):
        """None formula returns empty list."""
        assert parse_cross_sheet_refs(None) == []

    def test_empty_formula_returns_empty(self):
        """Empty string formula returns empty list."""
        assert parse_cross_sheet_refs("") == []


# ─── Property 7: Resolver depth termination ──────────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 7: Resolver depth termination
# For any chain of depth D > 3, resolver stops at depth 3, marks last node truncated=True.


class TestProperty7DepthTermination:
    """Property 7: 深度终止

    **Validates: Requirements 3.3**
    """

    def _build_deep_chain_snapshot(self, depth: int) -> dict:
        """Build a snapshot with a chain of cross-sheet refs of given depth.

        Sheet0!A1 → Sheet1!A1 → Sheet2!A1 → ... → SheetN!A1
        """
        sheets = []
        for i in range(depth + 1):
            sheet_name = f"Sheet{i}"
            if i < depth:
                # This cell references the next sheet
                formula = f"=Sheet{i + 1}!A1"
                cell_data = {"0": {"0": {"v": i * 10, "f": formula}}}
            else:
                # Terminal cell (no cross-sheet ref)
                cell_data = {"0": {"0": {"v": 999}}}
            sheets.append({"name": sheet_name, "cellData": cell_data})
        return {"univer_snapshot": {"sheets": sheets}}

    @settings(max_examples=20)
    @given(depth=st.integers(min_value=4, max_value=10))
    def test_deep_chain_truncated_at_3(self, depth: int):
        """For any chain deeper than 3, resolver stops at depth 3 with truncated=True."""
        parsed_data = self._build_deep_chain_snapshot(depth)
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet0",
            cell_ref="A1",
            max_depth=3,
        )
        # Should have nodes at depth 0, 1, 2, 3 (4 nodes total for linear chain)
        assert len(result.chain) == 4
        # Last node should be truncated
        last_node = result.chain[-1]
        assert last_node.truncated is True
        assert last_node.depth == 3
        # Should not have cycle
        assert result.has_cycle is False
        # truncated_at_depth should be 3
        assert result.truncated_at_depth == 3

    @settings(max_examples=20)
    @given(depth=st.integers(min_value=1, max_value=2))
    def test_shallow_chain_not_truncated(self, depth: int):
        """For chains within depth limit, no truncation occurs."""
        parsed_data = self._build_deep_chain_snapshot(depth)
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet0",
            cell_ref="A1",
            max_depth=3,
        )
        # No node should be truncated (chain fits within limit)
        for node in result.chain:
            assert node.truncated is False
        assert result.truncated_at_depth is None

    def test_max_depth_clamped_to_3(self):
        """max_depth > 3 is clamped to 3."""
        parsed_data = self._build_deep_chain_snapshot(5)
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet0",
            cell_ref="A1",
            max_depth=10,  # Should be clamped to 3
        )
        assert len(result.chain) == 4  # depth 0, 1, 2, 3
        assert result.chain[-1].truncated is True


# ─── Property 8: Cycle detection ─────────────────────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 8: Resolver cycle detection
# For any circular reference (A→B→A), resolver detects cycle and marks node cycle=True.


class TestProperty8CycleDetection:
    """Property 8: 循环检测

    **Validates: Requirements 3.4**
    """

    def _build_cycle_snapshot(self, cycle_length: int) -> dict:
        """Build a snapshot with a cycle of given length.

        Sheet0!A1 → Sheet1!A1 → ... → Sheet(N-1)!A1 → Sheet0!A1 (cycle back)
        """
        sheets = []
        for i in range(cycle_length):
            next_idx = (i + 1) % cycle_length
            formula = f"=Sheet{next_idx}!A1"
            cell_data = {"0": {"0": {"v": i * 100, "f": formula}}}
            sheets.append({"name": f"Sheet{i}", "cellData": cell_data})
        return {"univer_snapshot": {"sheets": sheets}}

    @settings(max_examples=20)
    @given(cycle_length=st.integers(min_value=2, max_value=3))
    def test_cycle_detected(self, cycle_length: int):
        """For any circular reference chain, resolver detects cycle."""
        # A cycle of length 2: A→B→A (detected at depth 2)
        # A cycle of length 3: A→B→C→A (detected at depth 3)

        parsed_data = self._build_cycle_snapshot(cycle_length)
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet0",
            cell_ref="A1",
            max_depth=3,
        )
        # Should detect cycle
        assert result.has_cycle is True
        # At least one node should have cycle=True
        cycle_nodes = [n for n in result.chain if n.cycle]
        assert len(cycle_nodes) >= 1

    def test_simple_a_b_a_cycle(self):
        """Simple A→B→A cycle is detected."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "SheetA",
                        "cellData": {"0": {"0": {"v": 10, "f": "=SheetB!A1"}}},
                    },
                    {
                        "name": "SheetB",
                        "cellData": {"0": {"0": {"v": 20, "f": "=SheetA!A1"}}},
                    },
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="SheetA",
            cell_ref="A1",
            max_depth=3,
        )
        assert result.has_cycle is True
        # Chain: SheetA!A1 (depth 0) → SheetB!A1 (depth 1) → SheetA!A1 (depth 2, cycle)
        assert len(result.chain) == 3
        assert result.chain[0].uri == "SheetA!A1"
        assert result.chain[0].cycle is False
        assert result.chain[1].uri == "SheetB!A1"
        assert result.chain[1].cycle is False
        assert result.chain[2].uri == "SheetA!A1"
        assert result.chain[2].cycle is True

    def test_no_cycle_in_linear_chain(self):
        """Linear chain without cycle has has_cycle=False."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "Sheet1",
                        "cellData": {"0": {"0": {"v": 1, "f": "=Sheet2!A1"}}},
                    },
                    {
                        "name": "Sheet2",
                        "cellData": {"0": {"0": {"v": 2, "f": "=Sheet3!A1"}}},
                    },
                    {"name": "Sheet3", "cellData": {"0": {"0": {"v": 3}}}},
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        assert result.has_cycle is False
        for node in result.chain:
            assert node.cycle is False

    def test_self_reference_cycle(self):
        """Self-reference (A→A) is detected as cycle."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "Sheet1",
                        "cellData": {"0": {"0": {"v": 42, "f": "=Sheet1!A1"}}},
                    },
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        assert result.has_cycle is True
        assert len(result.chain) == 2
        assert result.chain[0].cycle is False
        assert result.chain[1].cycle is True
        assert result.chain[1].uri == "Sheet1!A1"


# ─── E2E: 追溯端点集成测试 ──────────────────────────────────────────────────


class TestCrossSheetTraceE2E:
    """追溯 e2e — 端点集成测试"""

    def test_missing_sheet_marked(self):
        """When referenced sheet doesn't exist, node is marked missing=True."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "Sheet1",
                        "cellData": {
                            "0": {"0": {"v": 10, "f": "=NonExistent!B2"}}
                        },
                    },
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        # First node is Sheet1!A1 (exists)
        assert result.chain[0].missing is False
        # Second node is NonExistent!B2 (missing)
        assert result.chain[1].missing is True
        assert result.chain[1].uri == "NonExistent!B2"

    def test_empty_parsed_data(self):
        """Empty parsed_data returns single missing node."""
        result = cross_sheet_resolver.resolve(
            parsed_data={},
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        assert len(result.chain) == 1
        assert result.chain[0].missing is True
        assert result.has_cycle is False

    def test_none_parsed_data(self):
        """None parsed_data returns single missing node."""
        result = cross_sheet_resolver.resolve(
            parsed_data=None,
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        assert len(result.chain) == 1
        assert result.chain[0].missing is True

    def test_cell_with_no_formula(self):
        """Cell with value but no formula returns single node, no further traversal."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "Sheet1",
                        "cellData": {"0": {"0": {"v": 42}}},
                    },
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Sheet1",
            cell_ref="A1",
            max_depth=3,
        )
        assert len(result.chain) == 1
        assert result.chain[0].value == 42
        assert result.chain[0].formula is None
        assert result.has_cycle is False
        assert result.truncated_at_depth is None

    def test_branching_refs(self):
        """Formula with multiple refs creates branching BFS traversal."""
        parsed_data = {
            "univer_snapshot": {
                "sheets": [
                    {
                        "name": "Main",
                        "cellData": {
                            "0": {"0": {"v": 30, "f": "=Left!A1+Right!A1"}}
                        },
                    },
                    {
                        "name": "Left",
                        "cellData": {"0": {"0": {"v": 10}}},
                    },
                    {
                        "name": "Right",
                        "cellData": {"0": {"0": {"v": 20}}},
                    },
                ]
            }
        }
        result = cross_sheet_resolver.resolve(
            parsed_data=parsed_data,
            sheet_name="Main",
            cell_ref="A1",
            max_depth=3,
        )
        # BFS: Main!A1 (depth 0) → Left!A1 (depth 1) → Right!A1 (depth 1)
        assert len(result.chain) == 3
        assert result.chain[0].uri == "Main!A1"
        assert result.chain[0].depth == 0
        # Both Left and Right at depth 1
        depth1_uris = {n.uri for n in result.chain if n.depth == 1}
        assert "Left!A1" in depth1_uris
        assert "Right!A1" in depth1_uris
        assert result.has_cycle is False


# ─── Unit tests for helper functions ─────────────────────────────────────────


class TestCellRefToIndices:
    """Unit tests for _cell_ref_to_indices helper."""

    def test_a1(self):
        assert _cell_ref_to_indices("A1") == (0, 0)

    def test_b3(self):
        assert _cell_ref_to_indices("B3") == (2, 1)

    def test_z1(self):
        assert _cell_ref_to_indices("Z1") == (0, 25)

    def test_aa1(self):
        assert _cell_ref_to_indices("AA1") == (0, 26)

    def test_invalid(self):
        assert _cell_ref_to_indices("") == (None, None)
        assert _cell_ref_to_indices("123") == (None, None)
        assert _cell_ref_to_indices("!A1") == (None, None)
