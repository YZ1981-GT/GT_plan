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


def test_deleted_sections_produce_continuous_numbering():
    """删除中间章节后，剩余章节编号应连续（不跳号）。

    场景：五、1 ~ 五、11 中删除 2/3/9 → 剩 8 条 → 编号 1~8。
    修复前 all_numeric 分支直接取原始数字（1,4,5,6,7,8,10,11 跳号）。
    """
    # 模拟：五、2 / 五、3 / 五、9 已被 is_deleted 过滤，不在 tree 中
    tree = [
        _item("五、1"),   # 货币资金
        _item("五、4"),   # 应收票据
        _item("五、5"),   # 应收账款
        _item("五、6"),   # 应收款项融资
        _item("五、7"),   # 预付款项
        _item("五、8"),   # 其他应收款
        _item("五、10"),  # 合同资产
        _item("五、11"),  # 持有待售资产
    ]
    result = compute_section_numbers(tree, report_scope="both")
    assert result == {
        "五、1": "1",
        "五、4": "2",
        "五、5": "3",
        "五、6": "4",
        "五、7": "5",
        "五、8": "6",
        "五、10": "7",
        "五、11": "8",
    }


def test_deleted_sections_soe_continuous_numbering():
    """国企版八章同理：删除中间章节后编号应连续。"""
    tree = [
        _item("八、1"),
        _item("八、3"),  # 八、2 被删
        _item("八、5"),  # 八、4 被删
    ]
    result = compute_section_numbers(tree, report_scope="both")
    assert result == {
        "八、1": "1",
        "八、3": "2",
        "八、5": "3",
    }


def test_skip_empty_sections_continuous_numbering():
    """用户标记不导出的章节被跳过，后续编号连续。

    场景：五、2 和五、5 标记为不适用（不导出）。
    编号应为 1,2,3,4 而不是 1,2,3,4,5,6（含不导出的）。
    """
    tree = [
        _item("五、1", has_data=True),
        _item("五、2", has_data=False, status="not_applicable"),  # 不导出
        _item("五、3", has_data=True),
        _item("五、4", has_data=True),
        _item("五、5", has_data=False, status="not_applicable"),  # 不导出
        _item("五、6", has_data=True),
    ]
    result = compute_section_numbers(tree, report_scope="both", skip_empty=True)
    assert result == {
        "五、1": "1",
        "五、3": "2",
        "五、4": "3",
        "五、6": "4",
    }
    assert "五、2" not in result
    assert "五、5" not in result


def test_skip_empty_false_includes_all():
    """skip_empty=False 时不导出章节也参与编号（向后兼容）。"""
    tree = [
        _item("八、1", has_data=True),
        _item("八、2", has_data=False, status="not_applicable"),
        _item("八、3", has_data=True),
    ]
    result = compute_section_numbers(tree, report_scope="both", skip_empty=False)
    assert result == {
        "八、1": "1",
        "八、2": "2",
        "八、3": "3",
    }


def test_skip_empty_not_applicable_with_data_still_skipped():
    """status='not_applicable' 不论 has_data 值都跳过。

    用户明确标记不导出 = 不参与编号，即使章节里有数据。
    """
    tree = [
        _item("五、1", has_data=True),
        _item("五、2", has_data=True, status="not_applicable"),   # 有数据但不导出
        _item("五、3", has_data=True),
    ]
    result = compute_section_numbers(tree, report_scope="both", skip_empty=True)
    assert result == {
        "五、1": "1",
        "五、3": "2",
    }
    assert "五、2" not in result


def test_skip_empty_draft_empty_still_numbered():
    """has_data=False 但 status='draft' 的章节仍然参与编号。

    审计师刚生成附注、尚未填写的空章节保留编号，
    避免编号在填写过程中不稳定。
    """
    tree = [
        _item("五、1", has_data=True),
        _item("五、2", has_data=False, status="draft"),           # 空但保留
        _item("五、3", has_data=False, status="not_applicable"),  # 不适用，跳过
        _item("五、4", has_data=True),
    ]
    result = compute_section_numbers(tree, report_scope="both", skip_empty=True)
    assert result == {
        "五、1": "1",
        "五、2": "2",
        "五、4": "3",
    }
    assert "五、3" not in result


def test_skip_empty_confirmed_empty_still_numbered():
    """status='confirmed' 但 has_data=False 的章节仍然参与编号。

    审计师已确认但内容被清空的章节，仍保留编号（需要用户显式标记不导出才跳过）。
    """
    tree = [
        _item("五、1", has_data=True),
        _item("五、2", has_data=False, status="confirmed"),  # 已确认但空，保留
        _item("五、3", has_data=True),
    ]
    result = compute_section_numbers(tree, report_scope="both", skip_empty=True)
    assert result == {
        "五、1": "1",
        "五、2": "2",
        "五、3": "3",
    }
