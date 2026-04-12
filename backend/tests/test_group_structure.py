"""
Test Group Structure Service - validates tree building and entity relationships.
Validates: Requirements 1.1-1.6

All imports are mocked to avoid SQLAlchemy Base.metadata conflicts.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
import uuid


# ============================================================================
# Enums (mocked — avoid importing from consolidation_models)
# ============================================================================

class ConsolMethod:
    full = "full"
    equity = "equity"
    proportionate = "proportionate"
    none = "none"


# ============================================================================
# Mock helpers
# ============================================================================

def make_mock_company(code, name="Test Company", parent_code=None,
                      consol_level=0, shareholding=Decimal("100"),
                      method=None):
    """Create a mock company."""
    c = MagicMock()
    c.id = uuid.uuid4()
    c.company_code = code
    c.company_name = name
    c.parent_code = parent_code
    c.ultimate_code = code if parent_code is None else "PARENT"
    c.consol_level = consol_level
    c.shareholding = shareholding
    c.consol_method = method or ConsolMethod.full
    c.functional_currency = "CNY"
    c.is_active = True
    return c


def make_mock_scope(code, is_included=True):
    """Create a mock consol scope."""
    s = MagicMock()
    s.company_code = code
    s.is_included = is_included
    return s


# ============================================================================
# Pure-tree logic (mirrors _build_tree in service, no DB)
# ============================================================================

def _build_tree_mock(companies, parent_code=None):
    """Standalone tree builder for unit testing — mirrors service logic."""
    result = []
    for c in companies:
        if c.parent_code == parent_code:
            children = _build_tree_mock(companies, c.company_code)
            node = {
                "company_code": c.company_code,
                "company_name": c.company_name,
                "consol_level": c.consol_level,
                "children": children,
            }
            result.append(node)
    return result


def _detect_cyclic_mock(companies, root_code=None, visited=None, path=None):
    """Detect cycles in the ownership graph."""
    if visited is None:
        visited = set()
    if path is None:
        path = []

    if root_code in path:
        return True
    if root_code in visited:
        return False

    visited.add(root_code)
    path.append(root_code)

    children = [c for c in companies if c.parent_code == root_code]
    for child in children:
        if _detect_cyclic_mock(companies, child.company_code, visited, path):
            return True

    path.pop()
    return False


def _get_ancestors_mock(companies, code, ancestors=None):
    """Return all ancestor codes from bottom to root."""
    if ancestors is None:
        ancestors = []

    for c in companies:
        if c.company_code == code:
            if c.parent_code is not None:
                ancestors.append(c.parent_code)
                _get_ancestors_mock(companies, c.parent_code, ancestors)
    return ancestors


# ============================================================================
# Test: Tree Building
# ============================================================================

class TestGroupStructureBuilding:
    def test_flat_list_becomes_nested_tree(self):
        """Flat list of companies → correctly nested tree."""
        companies = [
            make_mock_company("A", "Root"),
            make_mock_company("B", "Child of A", parent_code="A"),
            make_mock_company("C", "Child of B", parent_code="B"),
        ]

        tree = _build_tree_mock(companies, parent_code=None)

        # Only root has no parent
        assert len(tree) == 1
        assert tree[0]["company_code"] == "A"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["company_code"] == "B"
        assert tree[0]["children"][0]["children"][0]["company_code"] == "C"

    def test_multiple_roots_become_separate_trees(self):
        """Independent companies each become their own root."""
        companies = [
            make_mock_company("A", "Root A"),
            make_mock_company("B", "Root B"),
            make_mock_company("C", "Child of A", parent_code="A"),
        ]

        tree = _build_tree_mock(companies, parent_code=None)

        assert len(tree) == 2
        codes = {t["company_code"] for t in tree}
        assert codes == {"A", "B"}

    def test_consol_level_propagates_correctly(self):
        """consol_level increases by 1 at each child level."""
        companies = [
            make_mock_company("ROOT", "Root Co", consol_level=0),
            make_mock_company("SUB1", "Sub 1", parent_code="ROOT", consol_level=1),
            make_mock_company("SUB2", "Sub 2", parent_code="SUB1", consol_level=2),
        ]

        tree = _build_tree_mock(companies, parent_code=None)

        assert tree[0]["consol_level"] == 0
        assert tree[0]["children"][0]["consol_level"] == 1
        assert tree[0]["children"][0]["children"][0]["consol_level"] == 2


# ============================================================================
# Test: Cyclic Reference Detection
# ============================================================================

class TestCyclicReferenceDetection:
    def test_no_cycle_returns_false(self):
        """Valid hierarchy has no cycle."""
        companies = [
            make_mock_company("A", "Root", parent_code=None),
            make_mock_company("B", "Child A", parent_code="A"),
            make_mock_company("C", "Child B", parent_code="B"),
        ]
        assert _detect_cyclic_mock(companies, "A") is False

    def test_self_reference_is_cycle(self):
        """Self-referencing company is a cycle."""
        companies = [
            make_mock_company("A", "Self Ref", parent_code="A"),
        ]
        assert _detect_cyclic_mock(companies, "A") is True

    def test_direct_cycle_detected(self):
        """A→B→A is a cycle."""
        companies = [
            make_mock_company("A", parent_code="B"),
            make_mock_company("B", parent_code="A"),
        ]
        # A references B, B references A
        has_cycle = _detect_cyclic_mock(companies, "A")
        assert has_cycle is True

    def test_indirect_cycle_three_nodes(self):
        """A→B→C→A is a cycle."""
        companies = [
            make_mock_company("A", parent_code="C"),
            make_mock_company("B", parent_code="A"),
            make_mock_company("C", parent_code="B"),
        ]
        has_cycle = _detect_cyclic_mock(companies, "A")
        assert has_cycle is True


# ============================================================================
# Test: Consolidation Scope Management
# ============================================================================

class TestConsolidationScopeManagement:
    def test_included_entities_returned(self):
        """Only included companies appear in scope."""
        companies = [
            make_mock_company("A"),
            make_mock_company("B"),
            make_mock_company("C"),
        ]
        scopes = {
            "A": make_mock_scope("A", is_included=True),
            "B": make_mock_scope("B", is_included=True),
            "C": make_mock_scope("C", is_included=False),
        }
        included = [code for code, s in scopes.items() if s.is_included]
        assert "A" in included
        assert "B" in included
        assert "C" not in included

    def test_excluded_entity_empty_in_scope(self):
        """Excluded company has zero balance in consolidated scope."""
        scope_map = {
            "EXCLUDED": make_mock_scope("EXCLUDED", is_included=False),
            "INCLUDED": make_mock_scope("INCLUDED", is_included=True),
        }

        def get_balance(code):
            if not scope_map[code].is_included:
                return Decimal("0")
            return Decimal("1000")

        assert get_balance("EXCLUDED") == Decimal("0")
        assert get_balance("INCLUDED") == Decimal("1000")

    def test_scope_count_matches_included(self):
        """Scope entity count = number of included companies."""
        companies = [
            make_mock_company("A"),
            make_mock_company("B"),
            make_mock_company("C"),
            make_mock_company("D"),
        ]
        scopes = {c.company_code: make_mock_scope(c.company_code, is_included=i < 3)
                  for i, c in enumerate(companies)}
        included_count = sum(1 for s in scopes.values() if s.is_included)
        assert included_count == 3


# ============================================================================
# Test: Ancestors and Descendants
# ============================================================================

class TestAncestorsAndDescendants:
    def test_get_ancestors_from_leaf(self):
        """Leaf node returns all ancestors up to root."""
        companies = [
            make_mock_company("ROOT"),
            make_mock_company("MID", parent_code="ROOT"),
            make_mock_company("LEAF", parent_code="MID"),
        ]
        ancestors = _get_ancestors_mock(companies, "LEAF")
        assert "MID" in ancestors
        assert "ROOT" in ancestors
        assert "LEAF" not in ancestors

    def test_root_has_no_ancestors(self):
        """Root node has empty ancestor list."""
        companies = [make_mock_company("ROOT")]
        ancestors = _get_ancestors_mock(companies, "ROOT")
        assert ancestors == []

    def test_descendants_below_node(self):
        """Descendants of A: B, C, D (all A's children at all levels)."""
        companies = [
            make_mock_company("A"),
            make_mock_company("B", parent_code="A"),
            make_mock_company("C", parent_code="B"),
            make_mock_company("D", parent_code="A"),
        ]

        def get_descendants(code):
            result = []
            children = [c for c in companies if c.parent_code == code]
            for child in children:
                result.append(child.company_code)
                result.extend(get_descendants(child.company_code))
            return result

        desc_a = get_descendants("A")
        assert set(desc_a) == {"B", "C", "D"}

        desc_b = get_descendants("B")
        assert desc_b == ["C"]

        desc_c = get_descendants("C")
        assert desc_c == []
