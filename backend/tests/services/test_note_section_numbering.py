"""附注显示编号 compute_section_numbers 测试."""

from app.services.note_section_numbering import compute_section_numbers


def _item(note_section: str, **kwargs) -> dict:
    return {"note_section": note_section, **kwargs}


def test_group_renumber_within_prefix():
    tree = [_item("八、1"), _item("八、2"), _item("八、3")]
    assert compute_section_numbers(tree, report_scope="both") == {
        "八、1": "1",
        "八、2": "2",
        "八、3": "3",
    }


def test_single_item_in_group_not_numbered():
    tree = [_item("一"), _item("八、1")]
    assert compute_section_numbers(tree, report_scope="both") == {}


def test_standalone_excludes_consolidated_only_sections():
    tree = [
        _item("八、1"),
        _item("八、2"),
        _item("七、本期纳入合并报表范围的子公司基本情况"),
    ]
    result = compute_section_numbers(tree, report_scope="standalone", template_type="soe")
    assert "七、本期纳入合并报表范围的子公司基本情况" not in result
    assert result.get("八、1") == "1"
    assert result.get("八、2") == "2"


def test_consolidated_includes_consolidated_only():
    tree = [
        _item("八、1"),
        _item("八、2"),
        _item("七、本期纳入合并报表范围的子公司基本情况"),
        _item("七、重要非全资子公司"),
    ]
    result = compute_section_numbers(
        tree, report_scope="consolidated", template_type="soe"
    )
    assert result["七、本期纳入合并报表范围的子公司基本情况"] == "1"
    assert result["七、重要非全资子公司"] == "2"
    assert result["八、1"] == "1"
    assert result["八、2"] == "2"
