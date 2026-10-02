"""与上级关系默认规则（spec consol-tree-three-code-autobuild 任务 2 / 属性 P11）。

判据真源是共享夹具 ``backend/data/relation_to_parent_cases.json``：前端
``src/utils/__tests__/groupRelation.spec.ts`` 逐条跑同一份文件，两端结论必须完全一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.group_relation import (
    RELATION_BRANCH,
    RELATION_SUBSIDIARY,
    infer_relation_from_name,
    normalize_relation,
    resolve_relation,
)

_CASES_PATH = Path(__file__).resolve().parents[1] / "data" / "relation_to_parent_cases.json"
_CASES = json.loads(_CASES_PATH.read_text(encoding="utf-8"))["cases"]


def test_fixture_is_not_vacuous() -> None:
    """夹具必须两类都有、且含真库名称，否则两端「一致」可能是一起恒返回同一值。"""
    expected = {c["expected"] for c in _CASES}
    assert expected == {RELATION_SUBSIDIARY, RELATION_BRANCH}
    assert sum(1 for c in _CASES if c.get("real")) >= 7


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] or "<空>" for c in _CASES])
def test_infer_matches_shared_fixture(case: dict) -> None:
    assert infer_relation_from_name(case["name"]) == case["expected"]


def test_only_real_branch_name_is_linggang_store() -> None:
    """真库 7 个企业名里只有临港店判为分公司（需求 2 讨论时对用户的承诺）。"""
    branches = [c["name"] for c in _CASES if c.get("real") and infer_relation_from_name(c["name"]) == RELATION_BRANCH]
    assert branches == ["重庆医药集团宜宾医药有限公司新健康大药房临港店"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None), ("", None), ("  ", None),
        ("subsidiary", RELATION_SUBSIDIARY), (" Branch ", RELATION_BRANCH),
        ("子公司", RELATION_SUBSIDIARY), ("分公司", RELATION_BRANCH),
    ],
)
def test_normalize_relation(raw, expected) -> None:
    assert normalize_relation(raw) == expected


def test_normalize_relation_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="与上级关系"):
        normalize_relation("associate")


def test_resolve_relation_rules() -> None:
    # 无上级 ⇒ None（即使显式给了值）
    assert resolve_relation("branch", None, "某某分公司") is None
    assert resolve_relation("branch", "  ", "某某分公司") is None
    # 显式优先于名称
    assert resolve_relation("subsidiary", "91110000000000001A", "某某分公司") == RELATION_SUBSIDIARY
    # 缺省按名称
    assert resolve_relation(None, "91110000000000001A", "某某分公司") == RELATION_BRANCH
    assert resolve_relation("", "91110000000000001A", "某某有限公司") == RELATION_SUBSIDIARY


# ─────────────── 上级代码 = 本企业代码（需求 1.5，2026-09-29 用户更正：确认而非拒绝） ───────────────

from app.services.group_relation import (  # noqa: E402
    SELF_REFERENCE_NOTICES,
    SELF_TOP,
    SELF_ULTIMATE,
    effective_parent_code,
    self_reference_kind,
)

_SELF_CASES = json.loads(_CASES_PATH.read_text(encoding="utf-8"))["self_reference_cases"]


def test_self_reference_fixture_is_not_vacuous() -> None:
    kinds = {c["kind"] for c in _SELF_CASES}
    assert kinds == {SELF_TOP, SELF_ULTIMATE, None}
    assert any(c["effective_parent"] for c in _SELF_CASES), "夹具须含「上级照常有效」的反例"


@pytest.mark.parametrize("case", _SELF_CASES, ids=[c["label"] for c in _SELF_CASES])
def test_effective_parent_and_kind_match_shared_fixture(case: dict) -> None:
    assert effective_parent_code(case["own"], case["parent"]) == case["effective_parent"]
    assert self_reference_kind(case["own"], case["parent"], case["ultimate"]) == case["kind"]


def test_resolve_relation_self_parent_has_no_relation() -> None:
    own = "91110000300000000G"
    # 上级 = 本企业 ⇒ 本企业就是上级企业，没有「与上级关系」可言（显式值也丢弃）
    assert resolve_relation("branch", own, "某某分公司", own) is None
    assert resolve_relation(None, f" {own} ", "某某分公司", own) is None
    # 不传本企业代码时保持旧行为（向后兼容）
    assert resolve_relation(None, own, "某某分公司") == RELATION_BRANCH


def test_self_reference_notices_cover_both_kinds() -> None:
    assert set(SELF_REFERENCE_NOTICES) == {SELF_TOP, SELF_ULTIMATE}
    assert "本企业就是上级企业" in SELF_REFERENCE_NOTICES[SELF_TOP]
    assert "本企业即为最终控制方（集团总部或母公司）" in SELF_REFERENCE_NOTICES[SELF_ULTIMATE]
