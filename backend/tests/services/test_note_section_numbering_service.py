"""A.0.7 单元测试 25 用例 — NoteSectionNumberingService + 工具函数.

覆盖：cn_number / circled_number / render_section_number /
      render_sections（basic / scope / lock / auto_numbering / reorder / multi-level）
"""

from app.services.note_section_numbering_service import (
    NoteSectionNumberingService,
    cn_number,
    circled_number,
    render_section_number,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sec(section_id: str, level: int, parent: str | None = None,
          sort_index: int = 0, **kwargs) -> dict:
    """构造最小 section dict."""
    d = {
        "section_id": section_id,
        "level": level,
        "parent_section_id": parent,
        "sort_index": sort_index,
        "auto_numbering": True,
        "lock_number": False,
        "locked_number": None,
        "scope": "both",
        "is_deleted": False,
    }
    d.update(kwargs)
    return d


svc = NoteSectionNumberingService()


# ===========================================================================
# 1. cn_number utility (4 tests)
# ===========================================================================

def test_cn_number_1():
    assert cn_number(1) == "一"


def test_cn_number_10():
    assert cn_number(10) == "十"


def test_cn_number_11():
    assert cn_number(11) == "十一"


def test_cn_number_35():
    assert cn_number(35) == "三十五"


# ===========================================================================
# 2. circled_number utility (2 tests)
# ===========================================================================

def test_circled_number_1_and_20():
    assert circled_number(1) == "①"
    assert circled_number(20) == "⑳"


def test_circled_number_fallback():
    assert circled_number(21) == "(21)"


# ===========================================================================
# 3. render_section_number (5 tests)
# ===========================================================================

def test_render_section_number_level1():
    assert render_section_number(1, 4) == "四、"


def test_render_section_number_level2():
    assert render_section_number(2, 3) == "（三）"


def test_render_section_number_level3():
    assert render_section_number(3, 5) == "5."


def test_render_section_number_level4():
    assert render_section_number(4, 2) == "(2)"


def test_render_section_number_level5():
    assert render_section_number(5, 1) == "①"


# ===========================================================================
# 4. render_sections — basic (3 tests)
# ===========================================================================

def test_render_single_root():
    sections = [_sec("s1", 1, sort_index=1)]
    result = svc.render_sections(sections)
    assert result["s1"] == "一、"


def test_render_root_with_2_children():
    sections = [
        _sec("root", 1, sort_index=1),
        _sec("c1", 2, parent="root", sort_index=1),
        _sec("c2", 2, parent="root", sort_index=2),
    ]
    result = svc.render_sections(sections)
    assert result["root"] == "一、"
    assert result["c1"] == "一、（一）"
    assert result["c2"] == "一、（二）"


def test_render_3_roots():
    sections = [
        _sec("r1", 1, sort_index=1),
        _sec("r2", 1, sort_index=2),
        _sec("r3", 1, sort_index=3),
    ]
    result = svc.render_sections(sections)
    assert result["r1"] == "一、"
    assert result["r2"] == "二、"
    assert result["r3"] == "三、"


# ===========================================================================
# 5. Scope filtering (3 tests)
# ===========================================================================

def test_scope_standalone_filters_consolidated():
    sections = [
        _sec("s1", 1, sort_index=1, scope="standalone"),
        _sec("s2", 1, sort_index=2, scope="consolidated"),
        _sec("s3", 1, sort_index=3, scope="standalone"),
    ]
    result = svc.render_sections(sections, scope="standalone")
    assert "s1" in result
    assert "s2" not in result
    assert "s3" in result
    # s3 should be numbered as 二、 (s2 filtered out)
    assert result["s1"] == "一、"
    assert result["s3"] == "二、"


def test_scope_consolidated_filters_standalone():
    sections = [
        _sec("s1", 1, sort_index=1, scope="standalone"),
        _sec("s2", 1, sort_index=2, scope="consolidated"),
        _sec("s3", 1, sort_index=3, scope="both"),
    ]
    result = svc.render_sections(sections, scope="consolidated")
    assert "s1" not in result
    assert "s2" in result
    assert "s3" in result
    assert result["s2"] == "一、"
    assert result["s3"] == "二、"


def test_scope_both_includes_all():
    sections = [
        _sec("s1", 1, sort_index=1, scope="standalone"),
        _sec("s2", 1, sort_index=2, scope="consolidated"),
        _sec("s3", 1, sort_index=3, scope="both"),
    ]
    result = svc.render_sections(sections, scope="both")
    assert result["s1"] == "一、"
    assert result["s2"] == "二、"
    assert result["s3"] == "三、"


# ===========================================================================
# 6. lock_number (3 tests)
# ===========================================================================

def test_lock_number_with_locked_value():
    sections = [
        _sec("s1", 1, sort_index=1, lock_number=True, locked_number="五、(三)"),
    ]
    result = svc.render_sections(sections)
    assert result["s1"] == "五、(三)"


def test_lock_number_true_but_no_locked_number():
    """lock_number=True but locked_number=None → normal auto-numbering (lock ignored)."""
    sections = [
        _sec("s1", 1, sort_index=1, lock_number=True, locked_number=None),
    ]
    result = svc.render_sections(sections)
    # When lock_number=True but locked_number is None/falsy, the code path
    # falls through to auto_numbering check → renders normally
    assert result["s1"] == "一、"


def test_lock_number_false_normal_numbering():
    sections = [
        _sec("s1", 1, sort_index=1, lock_number=False),
        _sec("s2", 1, sort_index=2, lock_number=False),
    ]
    result = svc.render_sections(sections)
    assert result["s1"] == "一、"
    assert result["s2"] == "二、"


# ===========================================================================
# 7. auto_numbering=False (1 test)
# ===========================================================================

def test_auto_numbering_false_renders_empty_no_counter():
    """auto_numbering=False → rendered as "", does NOT consume counter."""
    sections = [
        _sec("s1", 1, sort_index=1, auto_numbering=True),
        _sec("s2", 1, sort_index=2, auto_numbering=False),
        _sec("s3", 1, sort_index=3, auto_numbering=True),
    ]
    result = svc.render_sections(sections)
    assert result["s1"] == "一、"
    assert result["s2"] == ""       # empty
    assert result["s3"] == "二、"   # counter not consumed by s2


# ===========================================================================
# 8. Reordering / drag (2 tests)
# ===========================================================================

def test_reorder_after_drag():
    """After changing sort_index order (simulating drag), numbers follow new order."""
    # Original order: A=1, B=2, C=3 → drag B to position 3, C to position 2
    sections = [
        _sec("A", 1, sort_index=1),
        _sec("B", 1, sort_index=3),  # was 2, dragged to 3
        _sec("C", 1, sort_index=2),  # was 3, now 2
    ]
    result = svc.render_sections(sections)
    assert result["A"] == "一、"
    assert result["C"] == "二、"  # sort_index=2 comes before sort_index=3
    assert result["B"] == "三、"


def test_insert_between_sections():
    """Inserting a section between two existing ones → correct renumbering."""
    sections = [
        _sec("s1", 1, sort_index=1),
        _sec("new", 1, sort_index=2),   # inserted between s1 and s3
        _sec("s3", 1, sort_index=3),
    ]
    result = svc.render_sections(sections)
    assert result["s1"] == "一、"
    assert result["new"] == "二、"
    assert result["s3"] == "三、"


# ===========================================================================
# 9. Multi-level (3 levels deep) (2 tests)
# ===========================================================================

def test_three_level_tree():
    """Level 1 → Level 2 → Level 3 renders correctly."""
    sections = [
        _sec("L1", 1, sort_index=1),
        _sec("L2", 2, parent="L1", sort_index=1),
        _sec("L3", 3, parent="L2", sort_index=1),
    ]
    result = svc.render_sections(sections)
    assert result["L1"] == "一、"
    assert result["L2"] == "一、（一）"
    assert result["L3"] == "一、（一）1."


def test_five_level_deep_tree():
    """5-level deep tree renders all 5 formats correctly."""
    sections = [
        _sec("lv1", 1, sort_index=1),
        _sec("lv2", 2, parent="lv1", sort_index=1),
        _sec("lv3", 3, parent="lv2", sort_index=1),
        _sec("lv4", 4, parent="lv3", sort_index=1),
        _sec("lv5", 5, parent="lv4", sort_index=1),
    ]
    result = svc.render_sections(sections)
    assert result["lv1"] == "一、"
    assert result["lv2"] == "一、（一）"
    assert result["lv3"] == "一、（一）1."
    assert result["lv4"] == "一、（一）1.(1)"
    assert result["lv5"] == "一、（一）1.(1)①"
