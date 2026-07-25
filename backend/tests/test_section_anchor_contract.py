"""章节锚点命名契约测试 — deliverable-lineage-content-control Task 1 / Property 1.

锁定后端 `section_anchor_utils.anchor_name` 与前端
`useDeliverableLineage.ts::anchorNameFromSectionCode` 的规则一致（命名单一真源），
并验证单顿号章节码的 anchor ↔ section_code 双向一致（round-trip）。

前端规则（镜像）：
    sec_ + section_code.trim().replace('、','_').replace(' ','').replace('·','_')
"""

from __future__ import annotations

import pytest

from app.services.section_anchor_utils import anchor_name, section_code_from_anchor


def _frontend_anchor_rule(section_code: str) -> str:
    """前端 anchorNameFromSectionCode 的 Python 镜像（用于契约比对）。"""
    safe = section_code.strip().replace("、", "_").replace(" ", "").replace("·", "_")
    return f"sec_{safe}"


@pytest.mark.parametrize(
    "section_code,expected_anchor",
    [
        ("八、1", "sec_八_1"),
        ("五、1", "sec_五_1"),
        ("五、23", "sec_五_23"),
        ("五、12·1", "sec_五_12_1"),
        ("  八、2  ", "sec_八_2"),  # trim
    ],
)
def test_anchor_name_matches_expected(section_code: str, expected_anchor: str) -> None:
    assert anchor_name(section_code) == expected_anchor


@pytest.mark.parametrize(
    "section_code",
    ["八、1", "五、1", "五、23", "五、12·1", "  八、2  ", "七、3", "六、10"],
)
def test_anchor_name_mirrors_frontend_rule(section_code: str) -> None:
    """后端 anchor_name 必须与前端规则逐字符一致（命名单一真源）。"""
    assert anchor_name(section_code) == _frontend_anchor_rule(section_code)


@pytest.mark.parametrize(
    "section_code",
    ["八、1", "五、1", "五、23", "七、3", "六、10"],
)
def test_single_dun_roundtrip(section_code: str) -> None:
    """单顿号章节码：anchor → section_code 双向一致（Property 1）。"""
    assert section_code_from_anchor(anchor_name(section_code)) == section_code


def test_section_code_from_anchor_rejects_non_sec() -> None:
    assert section_code_from_anchor("note_section_八_1") is None
    assert section_code_from_anchor("") is None
    assert section_code_from_anchor("sec_") is None
