"""Property-based test for StalePropagationEngine 起点身份判定（P6，按 T21 新契约改写）。

原 Spec: .kiro/specs/acnr-consumer-wiring（design.md Correctness Property P6）要求 ``_detect_and_normalize``
用正则从表显示名猜 sheet_code 再拼 addr_id。acnr-foundation-defect-closure T21（需求 9.3、design §10.2）
取消这一做法：写 stale 的入口只按 exact_identity 判定的身份，``_detect_and_normalize`` 已删除。
本文件改为钉住新契约：

- ``WP:`` 写法与 addr_id 形态都得到 ``CanonicalNode``，``addr_id`` 与 ``unresolved_reason`` 恰有其一；
- 非 WP 域（REPORT: / TB: / NOTE: …）返回 None，按字面查图；
- 表名里带别的编码时不按正则猜（G12「…G12A-修订前」归 G12 本身，不归 G12A）。
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.stale_propagation_engine import _identity_of

_wp_code = st.from_regex(r"\A[A-N]\d{1,2}(?:-\d)?[A-Z]?\Z")
_sheet_code = st.from_regex(r"\A[A-Z]\d{1,2}(?:-\d{1,2})?[A-Z]?\Z")
_sheet_prefix = st.sampled_from(["明细表", "审定表", "分析表", "汇总表", ""])
_last = st.one_of(st.from_regex(r"\A[A-Z]{1,3}\d{1,4}\Z"), st.sampled_from(["审定数", "期初余额", "AJE调整"]))
_non_wp_domain = st.sampled_from(["REPORT", "TB", "NOTE", "ADJ", "MAPPING"])


@st.composite
def _wp_uri(draw: st.DrawFn) -> str:
    return f"WP:{draw(_wp_code)}:{draw(_sheet_prefix)}{draw(_sheet_code)}:{draw(_last)}"


@st.composite
def _addr_id(draw: st.DrawFn) -> str:
    return f"{draw(_wp_code)}/{draw(_sheet_code)}/{draw(_last)}"


@st.composite
def _non_wp_uri(draw: st.DrawFn) -> str:
    return f"{draw(_non_wp_domain)}:{draw(st.text())}"


def _exactly_one(node) -> bool:
    return (node.addr_id is None) != (node.unresolved_reason is None)


@settings(max_examples=5, deadline=None)
@given(uri=st.one_of(_wp_uri(), _addr_id()))
def test_p6_wp_and_addr_inputs_get_exactly_one_identity_field(uri: str) -> None:
    node = _identity_of(uri)
    assert node is not None
    assert _exactly_one(node), node


@settings(max_examples=5, deadline=None)
@given(uri=_non_wp_uri())
def test_p6_non_wp_domain_is_literal(uri: str) -> None:
    assert _identity_of(uri) is None


def test_example_non_wp_domains_literal() -> None:
    for uri in ["REPORT:BS-009::", "TB:1122::期末余额", "NOTE:五、1:0:total"]:
        assert _identity_of(uri) is None


def test_example_code_in_sheet_name_is_not_guessed() -> None:
    """「净敞口套期收益审计程序表G12A-修订前」是 G12 本身的表名；旧正则会猜成 G12A。"""
    node = _identity_of("WP:G12:净敞口套期收益审计程序表G12A-修订前:审定数")
    assert node.sheet_addr_id == "G12/G12", node
    assert node.identity_key == "G12/G12#审定数"


def test_example_unknown_sheet_gives_chinese_reason() -> None:
    node = _identity_of("WP:D2:并不存在的表:E100")
    assert node.identity_key is None and node.unresolved_code == "sheet_not_in_catalog"
    assert "不在地址目录" in node.unresolved_reason
