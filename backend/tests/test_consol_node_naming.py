"""企业树节点展示名（spec consol-autotree-linkage-closure R2，用户 2026-10-26 拍板）。

合并项目三个节点：合并户 / 差额户 / 单体母公司户；母公司有分公司：母公司户，下挂母分差额户 / 本部单体户 /
各分公司；子公司、分公司自己有分公司：汇总户；其余数据节点用原名。节点键与展示名无关。
"""

from __future__ import annotations

import pytest

from app.services import consol_group_tree as tree_mod
from app.services import consol_node_naming as naming
from app.services.consol_node_naming import (
    KIND_AGGREGATE,
    KIND_DATA,
    KIND_ELIM,
    ROLE_BRANCH,
    ROLE_BRANCH_ELIM,
    ROLE_CONSOL,
    ROLE_CONSOL_ELIM,
    ROLE_HQ,
    ROLE_PARENT,
    ROLE_SUBSIDIARY,
    consol_label,
    display_name,
    node_key,
)


@pytest.mark.parametrize(
    ("role", "kind", "expected"),
    [
        (ROLE_CONSOL, KIND_AGGREGATE, "甲集团（合并户）"),
        (ROLE_CONSOL_ELIM, KIND_ELIM, "甲集团（差额户）"),
        (ROLE_PARENT, KIND_DATA, "甲集团（单体母公司户）"),
        (ROLE_PARENT, KIND_AGGREGATE, "甲集团（母公司户）"),
        (ROLE_HQ, KIND_DATA, "甲集团（本部单体户）"),
        (ROLE_BRANCH_ELIM, KIND_ELIM, "甲集团（母分差额户）"),
        (ROLE_SUBSIDIARY, KIND_AGGREGATE, "甲集团（汇总户）"),
        (ROLE_BRANCH, KIND_AGGREGATE, "甲集团（汇总户）"),
        (ROLE_SUBSIDIARY, KIND_DATA, "甲集团"),
        (ROLE_BRANCH, KIND_DATA, "甲集团"),
    ],
)
def test_display_name_table(role, kind, expected):
    assert display_name("甲集团", role, kind) == expected


def test_consol_label_is_the_consol_node_display_name():
    assert consol_label("甲集团") == display_name("甲集团", ROLE_CONSOL, KIND_AGGREGATE) == "甲集团（合并户）"


def test_node_key_does_not_depend_on_display_name():
    assert node_key("91110000100000000R", ROLE_PARENT) == "91110000100000000R:parent"


def test_group_tree_reexports_the_same_objects():
    """旧调用方 ``from consol_group_tree import display_name / ROLE_* / MODE_LABELS`` 不变。"""
    for name in ("display_name", "node_key", "ROLE_CONSOL", "ROLE_PARENT", "KIND_AGGREGATE", "MODE_LABELS",
                 "ELIM_ROLES", "ENTITY_ROLES"):
        assert getattr(tree_mod, name) is getattr(naming, name), name


def test_old_suffixes_are_gone_from_the_tree_module():
    """旧后缀「（合并差额）（母公司）（本部）（母分差额）」不能再作为展示名出现。"""
    for role, kind in ((ROLE_CONSOL, KIND_AGGREGATE), (ROLE_CONSOL_ELIM, KIND_ELIM), (ROLE_PARENT, KIND_DATA),
                       (ROLE_HQ, KIND_DATA), (ROLE_BRANCH_ELIM, KIND_ELIM)):
        label = display_name("X", role, kind)
        assert label.endswith("户）"), label
