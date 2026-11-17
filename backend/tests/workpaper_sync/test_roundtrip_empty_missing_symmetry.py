"""roundtrip 判据：提交侧「空表示」与反读侧「键不存在」必须视为同一件事。

🔴 回归背景（D4 真栈恒 500 `roundtrip_projection_mismatch`）：

  D4-27 的 10 个勾选列 value_type=boolean，未勾经 `_coerce_checkbox_to_store`
  映射成 `None`（源模板口径「勾选=1 / 未勾=空白」）。

  于是同一条 roundtrip 链上，两侧对「无值」的**表示形态不同**：

  | 侧 | 表示 |
  |---|---|
  | 提交侧 intended | `{"undisclosed_rp_rows/<uuid>/is_customer_legal": None}` |
  | 反读侧 extracted | 该键**不存在**（`excel_extract._collect_fields` 对空格 `if not present: continue`） |

  materialize 刻意把 `None` 写成**空格** `<c r=".."/>` —— 写成 `<v>0</v>` 会把「未填」
  变成「填了 false」，对「是否关联方 / 是否函证」这类审计字段是实质性语义错误
  （见 `excel_materialize.CellWriteKind.boolean_literal` 的注释）。

  裸 `set(left) - set(right)` 会把这种「双方都表示无值」判成「materialize 没写进去」
  ⇒ 报「staged representation 反读后缺少受管字段 ...（共 4 个）」，整个 D4 entry
  的在线编辑被打挂。

  修法 = missing 判据对**提交侧确实是空表示**的键豁免，复用与逐键比较**同一个**
  `_is_roundtrip_empty`（两套口径必然漂移，而漂移那天两边都「全绿」）。

  🔴 闸门仍是 fail-closed：这里同时对「提交侧非空而反读缺键」断言报 missing ——
  豁免过宽会让「materialize 整行没写」静默通过，那是比原缺陷更重的事故。

🔴 **测的是生产函数** `content_mutation.assert_roundtrip_equivalent`（`ContentMutationService`
  的 `_assert_roundtrip_equivalent` 只是转发薄壳）。`excel_extract.verify_roundtrip_equivalence`
  是**另一条**判据（它的 `missing_keys` 语义与生产不同），测它测不到本修复。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.content_mutation import (
    RoundtripEquivalenceError,
    assert_roundtrip_equivalent,
)

SHEET_CODE = "D4-27"
ROW = "GTROW-D427-0015"
BOOL_COLUMN = "is_customer_legal"
TEXT_COLUMN = "name"


def _make_contract():
    """用**真实** D4 契约（含 10 个 boolean 勾选列），不手捏 payload。

    🔴 手捏 payload 缺 `schema_version` ⇒ `parse_contract` 直接抛
    （`_require_schema_version`）—— 自造夹具必须先过契约校验，否则测的是夹具不是语义。
    D4-27 就是本缺陷的现场（10 个 boolean 列 + 未勾 → None），用它最有说服力。
    """
    from app.services.workpaper_sync import phase5_d4_revenue_detail as D4
    from app.services.workpaper_sync.contracts import parse_contract

    D4.assert_contract_file_matches_source()
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _projections(contract, *, intended_values, extracted_values):
    """按生产 `stable_key_for` 构造两侧 projection。

    `intended_values` / `extracted_values` 的键是 `column_key`；**不出现在
    extracted_values 里的列 = 反读无该键**（这正是空格读回的形态）。

    🔴 前缀用生产函数现算，不得手写 —— 手写前缀会让判据测到「表不存在」而不是「键缺失」。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.phase5_d4_ipo_checklist_sheets import (
        _SHEETS,
        stable_key_for,
    )

    table_key = _SHEETS[SHEET_CODE]["table_key"]
    by_column = {s.column_key: s for s in contract.all_fields()}

    def build(values):
        out = {}
        for column_key, value in values.items():
            spec = by_column[column_key]
            stable_key = stable_key_for(SHEET_CODE, column_key, ROW)
            out[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=ROW,
            )
        return Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=out,
            row_keys={table_key: (ROW,)},
        )

    return build(intended_values), build(extracted_values)


class TestEmptyRepresentationSymmetry:
    """提交侧空表示 vs 反读侧键不存在 ⇒ 不得判 missing。"""

    def test_unchecked_boolean_is_not_reported_as_missing(self) -> None:
        """D4-27 未勾形态：提交 None、反读无该键 ⇒ 必须通过。"""
        contract = _make_contract()
        intended, extracted = _projections(
            contract,
            intended_values={BOOL_COLUMN: None},
            extracted_values={},
        )
        assert_roundtrip_equivalent(
            intended=intended, extracted=extracted, contract=contract
        )

    def test_empty_text_is_not_reported_as_missing(self) -> None:
        """空 text 同型：提交 ``""``、写空格、反读无键 ⇒ 也必须通过。"""
        contract = _make_contract()
        intended, extracted = _projections(
            contract,
            intended_values={TEXT_COLUMN: ""},
            extracted_values={},
        )
        assert_roundtrip_equivalent(
            intended=intended, extracted=extracted, contract=contract
        )


class TestExemptionStaysFailClosed:
    """豁免不得放宽到「真没写」。"""

    @pytest.mark.parametrize(
        ("column_key", "value", "label"),
        [
            (BOOL_COLUMN, True, "勾选态 True"),
            (BOOL_COLUMN, False, "False 是真实值、不算空"),
            (TEXT_COLUMN, "张某某", "非空文本"),
        ],
    )
    def test_non_empty_value_missing_on_extract_still_fails(
        self, column_key, value, label
    ) -> None:
        """提交侧非空而反读缺键 ⇒ **必须**报 missing（那才是 materialize 真没写）。"""
        contract = _make_contract()
        intended, extracted = _projections(
            contract,
            intended_values={column_key: value},
            extracted_values={},
        )
        with pytest.raises(RoundtripEquivalenceError) as exc_info:
            assert_roundtrip_equivalent(
                intended=intended, extracted=extracted, contract=contract
            )
        assert "缺少受管字段" in str(exc_info.value), (
            f"{label} 通过得太容易，但报错形态不对：{exc_info.value}"
        )
        assert column_key in str(exc_info.value), (
            f"{label} 的报错没有点名该字段 —— 无法定位：{exc_info.value}"
        )

    def test_zero_amount_is_not_empty(self) -> None:
        """``_is_roundtrip_empty`` 刻意排除数值 0 / False / Decimal(0) —— 它们是真实值。"""
        from decimal import Decimal

        from app.services.workpaper_sync.content_mutation import _is_roundtrip_empty

        assert _is_roundtrip_empty(None) is True
        assert _is_roundtrip_empty("") is True
        assert _is_roundtrip_empty("   ") is True
        for real_value in (False, True, 0, Decimal("0"), 0.0, "0", "false"):
            assert _is_roundtrip_empty(real_value) is False, (
                f"{real_value!r} 被当成空表示 —— 「未填」与「填了 false/0」是两件事"
            )


def test_single_source_of_empty_predicate() -> None:
    """**同一条判据只有一份**：missing 与逐键比较都用 `_is_roundtrip_empty`。

    🔴 「两套口径必然漂移」的直接防护：若将来谁在 missing 那段内联一份
    「value is None」的实现，本条即红（它会在 ``""`` 与 ``"  "`` 上分叉）。
    🔴 判据实现已移入 `roundtrip_equivalence`（`content_mutation` 只留转发），
       所以这里扫**实现所在的那个模块** —— 扫转发壳会恒 0 次而假红/假绿。
    """
    import inspect

    from app.services.workpaper_sync import roundtrip_equivalence as RT

    source = inspect.getsource(RT.assert_roundtrip_equivalent)
    calls = source.count("_is_roundtrip_empty(")
    assert calls >= 2, (
        f"assert_roundtrip_equivalent 里 _is_roundtrip_empty 只被调用 {calls} 次 —— "
        "missing 判据与逐键比较必须共用同一个空表示口径"
    )
    parts = source.split("missing = sorted(", 1)
    assert len(parts) == 2, "找不到 missing 判据块（判据已改形态，需同步更新本守卫）"
    head_of_block = parts[1].split("if missing:", 1)[0]
    assert "_is_roundtrip_empty(" in head_of_block, (
        "missing 判据没有复用 _is_roundtrip_empty —— 自己写一套口径就是漂移源"
    )
    assert "is None" not in head_of_block, (
        "missing 判据内联了 `is None` —— 那只覆盖 None，漏掉空字符串（两套口径）"
    )


def test_thin_shell_still_forwards_to_production_function() -> None:
    """`content_mutation` 的薄壳必须真的转发到实现模块（否则调用方测的不是生产路径）。"""
    import inspect

    from app.services.workpaper_sync import content_mutation as CM
    from app.services.workpaper_sync import roundtrip_equivalence as RT

    # 薄壳必须调那个转发别名
    source = inspect.getsource(CM.assert_roundtrip_equivalent)
    assert "_roundtrip_assert(" in source, (
        "content_mutation 的薄壳不再转发到 roundtrip_equivalence —— 调用方会走到空实现"
    )
    # 反向：两者是**同一个**函数对象（不是各写一份）
    assert CM.assert_roundtrip_equivalent is not RT.assert_roundtrip_equivalent
    # 转发别名必须就是实现本身
    assert CM._roundtrip_assert is RT.assert_roundtrip_equivalent, (
        "转发的不是同一个函数对象 ⇒ 两套实现必漂移"
    )
    # 空表示口径也必须是同一个对象
    assert CM._is_roundtrip_empty is RT._is_roundtrip_empty, (
        "_is_roundtrip_empty 被复制成两份 —— 两套口径必漂移"
    )
