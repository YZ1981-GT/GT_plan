# -*- coding: utf-8 -*-
"""projection digest 必须对**数值表示**稳定，否则 AC 3.6 的幂等复用是死代码。

2026-09-22 真栈实测（wp b3ab3c46 / entry xlsx/gt-d4-operating-revenue，revision 120）：

* 已提交 projection 与当次 flush 的 projection **899 个键逐键相等**（0 增 0 减 0 改）；
* 但 canonical 字节 121485 vs 121487、digest `ecb4f807…` vs `f22f1e75…`；
* 首个差异在 `revenue_detail_rows/GTROW-D42-0012/period_total`：``"value":0`` vs
  ``"value":0.0`` —— 同一个金额零，一侧 int、一侧 float。

后果：`_find_business_identity_reuse` 比的就是这个 digest，于是「内容一字未改」**永远**
判不出来，每次点「在线编辑」都走全量 materialize（D4 实测 30s+，换页签 31.5s）。
`_projection_payload` 的 docstring 早就写明它存在的理由是「同一份业务内容必须算出同一
digest，否则相同 projection ⇒ 幂等复用永远不成立」，而 `json_safe` 只规范了
`Decimal`/`date`，裸 int/float 原样透出。

本文件锁住的不变量：**同一业务内容的不同 Python 数值表示必须产出同一 digest**，
同时**不得**把语义不同的值折叠（None / 空串 / 0 三者互不相等）。
"""
from __future__ import annotations

import hashlib

import pytest

from app.services.workpaper_sync.adapters.base import (
    FieldMode,
    Projection,
    FieldValue,
    ValueType,
)
from app.services.workpaper_sync.content_mutation import _projection_payload
from app.services.workpaper_sync.projection_digest_value import (
    canonical_value_for_digest,
)
from app.services.workpaper_sync.definitions import canonical_json_bytes


def _field(value, value_type=ValueType.amount, mode=FieldMode.editable):
    return FieldValue(
        stable_key="t/r1/f",
        value=value,
        value_type=value_type,
        mode=mode,
        row_key="r1",
    )


def _projection(value, value_type=ValueType.amount) -> Projection:
    return Projection(
        contract_id="c1",
        semantic_version="1.0.0",
        document_type="xlsx",
        values={"t/r1/f": _field(value, value_type)},
        row_keys={"t": ("r1",)},
    )


def _digest(value, value_type=ValueType.amount) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_projection_payload(_projection(value, value_type)))
    ).hexdigest()


# ═══ 1. 表示差异必须折叠（这条红 = 复用永不命中） ═══


@pytest.mark.parametrize(
    "left,right",
    [
        (0, 0.0),
        (0.0, -0.0),
        (100, 100.0),
        (1.5, 1.50),
        (7, 7.000),
    ],
)
def test_amount_digest_ignores_int_float_representation(left, right) -> None:
    assert _digest(left) == _digest(right), (
        f"amount 的 {left!r} 与 {right!r} 算出不同 digest —— "
        "同一金额的两种 Python 表示会让「内容未改」判不出来，"
        "materialize 的幂等复用（AC 3.6）变成死代码，每次切换都全量重物化"
    )


@pytest.mark.parametrize("left,right", [(0, 0.0), (3, 3.0)])
def test_integer_digest_ignores_int_float_representation(left, right) -> None:
    assert _digest(left, ValueType.integer) == _digest(right, ValueType.integer)


def test_the_exact_real_stack_case_is_covered() -> None:
    """真栈那条差异（period_total 的 0 vs 0.0）逐字节复现并锁住。"""
    left = canonical_json_bytes(_projection_payload(_projection(0)))
    right = canonical_json_bytes(_projection_payload(_projection(0.0)))
    assert left == right, (
        f"0 与 0.0 的 canonical 字节仍不同：\n  {left!r}\n  {right!r}"
    )
    assert b'"value":0.0' not in left, (
        "canonical 字节里仍出现裸 float 表示 —— 只要有一侧产出 float，"
        "另一侧产出 int，digest 就会分叉"
    )


# ═══ 2. 语义不同的值**不得**折叠（反向锁） ═══


def test_none_amount_serialises_as_json_null_not_any_flavour_of_zero() -> None:
    """🔴 直接钉 canonical 字节里的形态，而不是只比「两个 digest 不等」。

    只比不等是**弱判据**：本轮变异检验实测，把 None 回退成 `json_safe(0)` 时两个
    digest 仍然不等（回退路径产出 int `0`、正常路径产出字符串 `"0"`），于是那条
    语义折叠的变异 SURVIVED。「未填」必须就是 `null`。
    """
    raw = canonical_json_bytes(_projection_payload(_projection(None)))
    assert b'"value":null' in raw, (
        f"None 的 amount 没有序列化成 JSON null：{raw!r} —— "
        "「未填」被折叠成某种零，审计上是两种事实"
    )
    assert b'"value":0' not in raw and b'"value":"0"' not in raw


def test_none_zero_and_empty_string_stay_distinct() -> None:
    zero = _digest(0)
    none = _digest(None)
    assert zero != none, "None 被折叠成 0 —— 「未填」与「填了零」是两种审计事实"

    text_empty = _digest("", ValueType.text)
    text_zero = _digest("0", ValueType.text)
    assert text_empty != text_zero, "空串与 '0' 被折叠"
    assert none != text_empty, "None 与空串被折叠"


def test_distinct_amounts_stay_distinct() -> None:
    assert _digest(1) != _digest(2)
    assert _digest(0.1) != _digest(0.2)
    # 小数精度不得被四舍五入抹平
    assert _digest("0.01") != _digest("0.02")


def test_boolean_is_not_folded_into_numbers() -> None:
    """True 不等于 1（merge.normalize_value 对此有明确判据，digest 侧不得放宽）。"""
    assert _digest(True, ValueType.boolean) != _digest(1, ValueType.integer)


# ═══ 3. 规范化失败不得让 flush 失败 ═══


def test_unnormalizable_value_falls_back_instead_of_raising() -> None:
    """坏值由 merge 记 `type_normalization_failure` 交人工裁决；
    canonicalization 不得把它升级成一次 flush 异常。"""
    payload = _projection_payload(_projection("not-a-number"))
    raw = canonical_json_bytes(payload)
    assert b"not-a-number" in raw
    # 同一坏值两次仍须同 digest（否则 pending token 的 digest 比对会随机失败）
    assert raw == canonical_json_bytes(_projection_payload(_projection("not-a-number")))


def test_digest_is_stable_across_repeated_calls() -> None:
    first = _digest(1234.5)
    for _ in range(5):
        assert _digest(1234.5) == first


# ═══ 4. 全 value_type 必须能走完整条 canonical 路径（2026-09-22 真栈 500） ═══
#
# 上面三节只喂了 amount / integer / text / boolean —— 于是 `value_type=json` 这一支
# 从未被驱动，而它的比较键是 `canonical_json_bytes({"v": value})`（**bytes**）。
# 把比较键当 payload 值放进去，`_projection_payload()` 的产物整份过
# `canonical_json_bytes()` 时抛 `TypeError: Object of type bytes is not JSON
# serializable` ⇒ `POST …/pending-mutations` **500**，D4 连「在线编辑」都进不去
# （真栈：2026-09-22 restart 后首次真实 flush 即崩，而单测全绿）。
#
# 判据按**枚举全集**写而不是补一个 json 用例：ValueType 将来加成员时，漏测的那一支
# 会立刻在这里红，而不是等一次真实 flush 500。


@pytest.mark.parametrize(
    "value_type,value",
    [
        (ValueType.amount, 12.5),
        (ValueType.integer, 7),
        (ValueType.text, "文本"),
        (ValueType.boolean, True),
        (ValueType.date, "2026-09-22"),
        (ValueType.datetime, "2026-09-22T10:11:12"),
        (ValueType.enum, "option_a"),
        (ValueType.json, {"b": 2, "a": [1, {"c": 3}]}),
        (ValueType.rate, "0.0325"),
        (ValueType.ratio, "0.6180"),
    ],
    ids=lambda v: getattr(v, "value", str(v))[:18],
)
def test_every_value_type_survives_the_full_canonical_path(
    value_type: ValueType, value: object
) -> None:
    """每一种 value_type 都必须能被 `canonical_json_bytes` 序列化，且两次同字节。"""
    payload = _projection_payload(_projection(value, value_type))
    first = canonical_json_bytes(payload)
    assert isinstance(first, bytes) and first
    assert first == canonical_json_bytes(
        _projection_payload(_projection(value, value_type))
    ), f"{value_type.value} 的 canonical 字节不稳定 —— 幂等复用会随机失效"


def test_no_value_type_is_left_untested_by_the_full_path_matrix() -> None:
    """反向自检：上面的矩阵必须覆盖 `ValueType` 的**全部**成员。

    没有这条，新增一个 value_type 时矩阵会静默漏掉它 —— 而漏掉的那一支正是本节在修的
    那种「单测全绿、真实 flush 500」。
    """
    covered = {
        ValueType.amount,
        ValueType.integer,
        ValueType.text,
        ValueType.boolean,
        ValueType.date,
        ValueType.datetime,
        ValueType.enum,
        ValueType.json,
        ValueType.rate,
        ValueType.ratio,
    }
    missing = sorted(m.value for m in ValueType if m not in covered)
    assert missing == [], f"这些 value_type 没进 canonical 路径矩阵：{missing}"


def test_canonical_value_for_digest_never_returns_bytes() -> None:
    """单点判据：任何 value_type 都不得让**比较键**（bytes）泄进 payload。

    与上面的端到端矩阵不重复：那条测「整份能序列化」，这条钉住「泄漏形态」本身，
    于是错误信息直接指向 `canonical_value_for_digest` 而不是一句 json.dumps 的 TypeError。
    """
    for value_type, value in (
        (ValueType.json, {"a": 1}),
        (ValueType.json, [1, 2, 3]),
        (ValueType.json, "already-a-string"),
        (ValueType.text, "文本"),
        (ValueType.amount, "1.50"),
    ):
        got = canonical_value_for_digest(_field(value, value_type))
        assert not isinstance(got, (bytes, bytearray)), (
            f"{value_type.value} 的规范表示是 {type(got).__name__} —— "
            "比较键不是 payload 值（见 projection_digest_value 模块 docstring）"
        )
