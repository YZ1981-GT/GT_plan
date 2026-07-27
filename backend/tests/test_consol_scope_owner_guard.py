"""合并范围附注 owner 约束（P2-8）契约。

锁定 `is_consol_scope_owned_by_workpaper`：G7 soe 披露 sync 拥有的合并范围类
V2 slug 章节被判为 True（未来 V2 落 disclosure_notes 时须跳过防双写），
其它章节为 False。
"""

import pytest

from app.services.consol_disclosure_service import (
    is_consol_scope_owned_by_workpaper,
    _WORKPAPER_OWNED_CONSOL_SCOPE_SLUGS,
)


@pytest.mark.parametrize("slug", ["consol_scope", "important_subsidiaries", "scope_change"])
def test_owned_scope_slugs(slug):
    assert is_consol_scope_owned_by_workpaper(slug) is True


@pytest.mark.parametrize("slug", ["goodwill", "minority_interest", "八、18", "", None])
def test_non_scope_sections_not_owned(slug):
    assert is_consol_scope_owned_by_workpaper(slug) is False


def test_owned_set_is_exactly_three():
    """owner 集合固定为三张合并范围类章节，新增须显式改常量+更新本断言。"""
    assert _WORKPAPER_OWNED_CONSOL_SCOPE_SLUGS == frozenset(
        {"consol_scope", "important_subsidiaries", "scope_change"}
    )
