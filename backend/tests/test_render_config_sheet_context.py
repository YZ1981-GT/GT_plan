"""render-config canonical sheet identity 行为契约。"""
from __future__ import annotations

import pytest

from app.routers.wp_render_config import (
    annotate_sheet_identities,
    annotate_sheet_identity,
)


@pytest.mark.parametrize(
    ("sheet_name", "expected_code"),
    [
        ("询证函控制表D0-4b", "D0-4b"),
        ("C1-4-4企业层面控制测试", "C1-4-4"),
        ("函证程序F1-CONF", "F1-CONF"),
        ("底稿目录", None),
    ],
)
def test_annotate_sheet_identity_uses_canonical_parser(
    sheet_name: str,
    expected_code: str | None,
) -> None:
    sheet = {
        "sheet_name": sheet_name,
        "componentType": "d-form-table",
        "html_data": {"sentinel": "keep"},
    }

    result = annotate_sheet_identity(sheet)

    assert result is sheet
    assert result["sheet_code"] == expected_code
    assert result["sheet_code_reason"] == (
        "embedded_code" if expected_code else "no_canonical_code"
    )
    assert result["whole_workbook"] is False
    assert result["html_data"] == {"sentinel": "keep"}


def test_explicit_identity_and_null_reason_are_preserved() -> None:
    explicit = {
        "sheet_name": "询证函控制表D0-4b",
        "sheet_code": "D0-4b",
        "componentType": "d-form-table",
    }
    explicit_null = {
        "sheet_name": "自定义分析页",
        "sheet_code": None,
        "sheet_code_reason": "virtual_sheet_without_standard_code",
        "componentType": "custom",
    }

    assert annotate_sheet_identity(explicit)["sheet_code_reason"] == "explicit_code"
    assert annotate_sheet_identity(explicit_null)["sheet_code"] is None
    assert (
        explicit_null["sheet_code_reason"]
        == "virtual_sheet_without_standard_code"
    )


def test_whole_workbook_identity_is_preserved_and_conflicts_fail_closed() -> None:
    whole = {
        "sheet_name": "完整工作簿",
        "sheet_code": None,
        "whole_workbook": True,
        "componentType": "onlyoffice",
    }
    result = annotate_sheet_identity(whole)
    assert result["whole_workbook"] is True
    assert result["sheet_code"] is None
    assert result["sheet_code_reason"] == "whole_workbook"

    with pytest.raises(ValueError, match="sheet_code=null"):
        annotate_sheet_identity({
            "sheet_name": "完整工作簿",
            "sheet_code": "D0-1",
            "whole_workbook": True,
            "componentType": "onlyoffice",
        })

    with pytest.raises(ValueError, match="解析结果冲突"):
        annotate_sheet_identity({
            "sheet_name": "询证函控制表D0-4b",
            "sheet_code": "D0-5",
            "componentType": "d-form-table",
        })


def test_every_visible_render_sheet_gets_identity_or_explicit_null_reason() -> None:
    visible_sheets = [
        {"sheet_name": "底稿目录", "componentType": "b-index"},
        {"sheet_name": "询证函控制表D0-4b", "componentType": "d-form-table"},
        {"sheet_name": "函证程序F1-CONF", "componentType": "f1-prepayment"},
    ]

    assert annotate_sheet_identities(visible_sheets) is visible_sheets

    for sheet in visible_sheets:
        assert "sheet_code" in sheet
        assert sheet["sheet_code_reason"] in {"embedded_code", "no_canonical_code"}
        assert sheet["whole_workbook"] is False
        assert bool(sheet["sheet_code"]) == (
            sheet["sheet_code_reason"] == "embedded_code"
        )

    assert [sheet["sheet_code"] for sheet in visible_sheets] == [
        None,
        "D0-4b",
        "F1-CONF",
    ]
