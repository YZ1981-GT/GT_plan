# -*- coding: utf-8 -*-
"""D4-1「营业收入审定表」—— 双区 store projection roundtrip 守卫（Task 9）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 9
Requirements 5.1 / 5.3 / 5.4 · Property 3（双区动态行 materialize→extract 往返一致）

判据落在真实契约（`D4.build_contract_payload()` → `parse_contract`）+ 生产 provider
`phase5_d4_adjudication_sheet` 的 `build_store_projection_d41` / `merge_projection_into_d41_rows`
上（非 stub、非自造 payload）。本文件是 **store 层** 双区往返守卫（build→merge），与
Task 11 e2e 的 OO 真栈往返互补。

覆盖（对齐 design §Testing Strategy）：
  1. 两区 build_store_projection→merge 往返：label + 6 金额逐字段一致（主营 + 其他都测）。
  2. 两区 rowId 各自唯一、按 table_key 归属不串区：主营区 rowId 不泄漏进其他区，反之亦然。
  3. formula_mask（E/I 审定数 + 小计/合计/差异行 12/18/19/21）不进投影、不回写。
  4. 缺行身份 / 重复行身份 / 非法载荷 → fail closed（ValueError），不静默兜底。
  5. hypothesis PBT：随机两区动态行往返逐字段一致（max_examples=5，遵 workspace 规则）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_adjudication_sheet as A  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

# 六金额 store_key（与前端 useD4Adjudication 逐项对齐）。
_AMOUNT_KEYS = (
    "currentUnadjusted",
    "currentAje",
    "currentRje",
    "priorUnadjusted",
    "priorAje",
    "priorRje",
)
_ALL_FIELDS = ("label", *_AMOUNT_KEYS)


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _row(rid: str, section: str, label: str, base: float) -> dict[str, Any]:
    """构造一条 D4-1-rows 行（label + 6 金额，各金额取相互区分的值以侦测串列）。"""
    return {
        A.ROW_IDENTITY_STORE_KEY_D41: rid,
        "label": label,
        A.SECTION_KEY_FIELD: section,
        "currentUnadjusted": base + 0.5,
        "currentAje": base + 1.0,
        "currentRje": -(base + 2.0),
        "priorUnadjusted": base + 3.0,
        "priorAje": base + 4.0,
        "priorRje": -(base + 5.0),
    }


def _empty_base(rid: str, section: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        A.ROW_IDENTITY_STORE_KEY_D41: rid,
        "label": "",
        A.SECTION_KEY_FIELD: section,
    }
    for key in _AMOUNT_KEYS:
        row[key] = 0
    return row


def _assert_row_equal(got: dict[str, Any], src: dict[str, Any]) -> None:
    assert got["label"] == src["label"], f"label 串列/丢值：{got.get('label')!r} != {src['label']!r}"
    for key in _AMOUNT_KEYS:
        assert abs(float(got[key]) - float(src[key])) <= 0.005, (
            f"{key} 金额往返超容差：{got.get(key)!r} != {src[key]!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 两区往返：label + 6 金额逐字段一致（主营 + 其他都覆盖）
# **Validates: Requirements 5.3, Property 3**
# ═══════════════════════════════════════════════════════════════════════════


def test_two_region_roundtrip_preserves_every_managed_field(contract: Any) -> None:
    """主营 + 其他两区各若干动态行经 build→merge 往返后，label + 6 金额逐字段一致。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发收入", 100.0),
        _row("m-2", A.SECTION_KEY_MAIN, "零售收入", 200.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流服务", 50.0),
        _row("o-2", A.SECTION_KEY_OTHER, "物业与租赁", 60.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    # 7 字段 × 4 行 = 28 个 FieldValue。
    assert len(proj.values) == len(_ALL_FIELDS) * len(rows)

    base = [_empty_base(r[A.ROW_IDENTITY_STORE_KEY_D41], r[A.SECTION_KEY_FIELD]) for r in rows]
    merged, applied, visited, touched = A.merge_projection_into_d41_rows(
        projection=proj, base_rows=base
    )
    assert len(merged) == len(rows)
    assert applied == len(_ALL_FIELDS) * len(rows)
    assert visited >= applied
    assert touched == {r[A.ROW_IDENTITY_STORE_KEY_D41] for r in rows}

    by_id = {r[A.ROW_IDENTITY_STORE_KEY_D41]: r for r in merged}
    for src in rows:
        rid = src[A.ROW_IDENTITY_STORE_KEY_D41]
        _assert_row_equal(by_id[rid], src)
        # sectionKey 由 extract 权威区归属回填，与源一致。
        assert by_id[rid][A.SECTION_KEY_FIELD] == src[A.SECTION_KEY_FIELD]


def test_projection_row_keys_routed_by_section(contract: Any) -> None:
    """build_store_projection 按 sectionKey 分流两区 row_keys（main→主营 / other→其他）。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0),
        _row("m-2", A.SECTION_KEY_MAIN, "零售", 2.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 3.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    assert proj.row_keys[A.ROWS_TABLE_KEY_MAIN] == ("m-1", "m-2")
    assert proj.row_keys[A.ROWS_TABLE_KEY_OTHER] == ("o-1",)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 两区 rowId 各自唯一不串：主营 rowId 不进其他区，反之亦然
# **Validates: Requirements 5.3, Property 3**
# ═══════════════════════════════════════════════════════════════════════════


def test_region_row_keys_are_disjoint_in_projection(contract: Any) -> None:
    """投影里两区 row_keys 互不相交 —— 主营 rowId 绝不出现在其他区，反之亦然。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0),
        _row("m-2", A.SECTION_KEY_MAIN, "零售", 2.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 3.0),
        _row("o-2", A.SECTION_KEY_OTHER, "租赁", 4.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    main_ids = set(proj.row_keys[A.ROWS_TABLE_KEY_MAIN])
    other_ids = set(proj.row_keys[A.ROWS_TABLE_KEY_OTHER])
    assert main_ids == {"m-1", "m-2"}
    assert other_ids == {"o-1", "o-2"}
    assert main_ids.isdisjoint(other_ids), (
        f"两区 rowId 串区：交集 {main_ids & other_ids}"
    )
    # 投影 stable_key 前缀也必须与 rowId 归属一致（不出现主营区键带其他区 rowId）。
    for key in proj.stable_keys():
        sk = str(key)
        rid = sk.rsplit("/", 1)[0].split("/", 1)[1]  # {table}/{rid}/{col} → rid
        if sk.startswith(A.ROWS_TABLE_KEY_MAIN + "/"):
            assert rid in main_ids, f"主营区键 {sk} 带非主营 rowId {rid}"
        elif sk.startswith(A.ROWS_TABLE_KEY_OTHER + "/"):
            assert rid in other_ids, f"其他区键 {sk} 带非其他 rowId {rid}"


def test_merge_routes_regions_by_table_key_not_crossing(contract: Any) -> None:
    """merge 按 table_key 前缀回填 sectionKey，主营/其他两区各归各位不串。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 10.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 20.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    # base 故意把 sectionKey 写反 —— merge 必须以 table_key 归属为权威纠正回来。
    base = [
        {A.ROW_IDENTITY_STORE_KEY_D41: "m-1", "label": "", A.SECTION_KEY_FIELD: A.SECTION_KEY_OTHER},
        {A.ROW_IDENTITY_STORE_KEY_D41: "o-1", "label": "", A.SECTION_KEY_FIELD: A.SECTION_KEY_MAIN},
    ]
    merged, _a, _v, _t = A.merge_projection_into_d41_rows(projection=proj, base_rows=base)
    by_id = {r[A.ROW_IDENTITY_STORE_KEY_D41]: r for r in merged}
    assert by_id["m-1"][A.SECTION_KEY_FIELD] == A.SECTION_KEY_MAIN, "主营行被串到其他区"
    assert by_id["o-1"][A.SECTION_KEY_FIELD] == A.SECTION_KEY_OTHER, "其他行被串到主营区"
    # 值也不能串行。
    _assert_row_equal(by_id["m-1"], rows[0])
    _assert_row_equal(by_id["o-1"], rows[1])


def test_row_id_is_unique_store_wide_across_both_regions(contract: Any) -> None:
    """`D4-1-rows` 是单条扁平数组：rowId 必须**全店唯一**，跨区撞 id 也 fail closed。

    这是「两区 rowId 各自唯一不串」的最强形态 —— provider 用单一 `seen` 集合把守，
    即便两区分处不同 section，字面相同的 rowId 也不得静默合并（否则 merge 回填时
    一个 rowId 会同时命中两区键，归属歧义）。
    """
    rows = [
        _row("dup", A.SECTION_KEY_MAIN, "主营同名", 1.0),
        _row("dup", A.SECTION_KEY_OTHER, "其他同名", 9.0),
    ]
    with pytest.raises(ValueError, match="重复行身份"):
        A.build_store_projection_d41(rows, contract=contract)


def test_distinct_row_ids_generate_region_scoped_stable_keys(contract: Any) -> None:
    """不同 rowId 的两区键各带 table_key 前缀，主营/其他生成的 stable_key 互不相同。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "主营", 1.0),
        _row("o-1", A.SECTION_KEY_OTHER, "其他", 9.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    main_key = A.stable_key_for_main("label", "m-1")
    other_key = A.stable_key_for_other("label", "o-1")
    assert main_key in proj.values and other_key in proj.values
    assert main_key != other_key, "两区键前缀未区分 —— 会互相覆盖"
    assert proj.values[main_key].value == "主营"
    assert proj.values[other_key].value == "其他"


# ═══════════════════════════════════════════════════════════════════════════
# 3. formula_mask（E/I + 12/18/19/21）不进投影、不回写
# **Validates: Requirements 5.4, Property 3**
# ═══════════════════════════════════════════════════════════════════════════


def test_projection_never_emits_formula_or_derived_columns(contract: Any) -> None:
    """投影只产 label + 6 金额；审定数/小计/合计/差异等派生列绝不出现在 stable_keys。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 2.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    allowed_cols = {ck for ck, *_ in A.MANAGED_FIELD_SPECS}
    for key in proj.stable_keys():
        col = str(key).rsplit("/", 1)[-1]
        assert col in allowed_cols, f"投影泄漏非受管列 {col!r}（key={key}）"
    # 派生 store_key 绝不出现。
    leaked = [
        k for k in proj.stable_keys()
        if str(k).endswith(("/currentAudited", "/priorAudited", "/subtotal", "/total", "/diff"))
    ]
    assert not leaked, f"派生列泄漏进投影: {leaked}"


def test_formula_mask_covers_audited_and_footer_cells() -> None:
    """provider FORMULA_MASK 覆盖 E/I 数据行 + 小计/合计/差异行(12/18/19/21) B–I，且 48 格。"""
    mask = set(A.FORMULA_MASK)
    assert len(A.FORMULA_MASK) == 48
    # E/I 审定数数据行（主营 8-11 / 其他 14-17）。
    for row in (8, 11, 14, 17):
        assert f"E{row}" in mask and f"I{row}" in mask, f"E/I{row} 审定数未入 mask"
    # 小计/合计/差异行 B–I。
    for r in (12, 18, 19, 21):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I"):
            assert f"{col}{r}" in mask, f"{col}{r} 未入 formula_mask"


def test_merge_ignores_injected_formula_mask_keys(contract: Any) -> None:
    """即便投影里被塞进 formula_mask 派生列的键，merge 也不把它回写进 store 行。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    rows = [_row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0)]
    proj = A.build_store_projection_d41(rows, contract=contract)
    # 人为注入一个「审定数」派生列键（模拟错误上游）：column_key=current_audited 不在受管映射。
    tampered_values = dict(proj.values)
    bad_key = f"{A.ROWS_TABLE_KEY_MAIN}/m-1/current_audited"
    tampered_values[bad_key] = FieldValue(
        stable_key=bad_key,
        value=999999.0,
        value_type=ValueType.amount,
        mode=FieldMode.editable,
        row_key="m-1",
    )
    tampered = Projection(
        contract_id=proj.contract_id,
        semantic_version=proj.semantic_version,
        document_type=proj.document_type,
        values=tampered_values,
        row_keys=proj.row_keys,
    )
    base = [_empty_base("m-1", A.SECTION_KEY_MAIN)]
    merged, _a, _v, _t = A.merge_projection_into_d41_rows(projection=tampered, base_rows=base)
    out = merged[0]
    assert "current_audited" not in out, "formula_mask 派生列被回写进 store 行"
    assert "currentAudited" not in out, "formula_mask 派生列被回写进 store 行"
    # 正常 6 金额仍逐字段一致。
    _assert_row_equal(out, rows[0])


# ═══════════════════════════════════════════════════════════════════════════
# 4. fail-closed：缺行身份 / 重复行身份 / 非法载荷
# **Validates: Requirements 5.4, Property 3**
# ═══════════════════════════════════════════════════════════════════════════


def test_row_without_identity_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="稳定行身份"):
        A.build_store_projection_d41(
            [{"label": "无身份", A.SECTION_KEY_FIELD: A.SECTION_KEY_MAIN}],
            contract=contract,
        )


def test_blank_row_identity_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="稳定行身份"):
        A.build_store_projection_d41(
            [{A.ROW_IDENTITY_STORE_KEY_D41: "   ", "label": "空白身份"}],
            contract=contract,
        )


def test_duplicate_row_identity_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="重复行身份"):
        A.build_store_projection_d41(
            [
                _row("dup", A.SECTION_KEY_MAIN, "第一", 1.0),
                _row("dup", A.SECTION_KEY_MAIN, "第二", 2.0),
            ],
            contract=contract,
        )


def test_non_array_payload_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="行对象数组"):
        A.build_store_projection_d41(42, contract=contract)  # type: ignore[arg-type]


def test_malformed_json_string_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="不是合法 JSON"):
        A.build_store_projection_d41("{not json", contract=contract)


def test_empty_store_yields_no_rows(contract: Any) -> None:
    proj = A.build_store_projection_d41([], contract=contract)
    assert proj.row_keys[A.ROWS_TABLE_KEY_MAIN] == ()
    assert proj.row_keys[A.ROWS_TABLE_KEY_OTHER] == ()
    merged, applied, _v, touched = A.merge_projection_into_d41_rows(projection=proj, base_rows=[])
    assert merged == [] and applied == 0 and touched == set()


# ═══════════════════════════════════════════════════════════════════════════
# 5. hypothesis PBT：随机两区动态行往返逐字段一致（max_examples=5，workspace 规则）
# **Validates: Requirements 5.3, Property 3**
# ═══════════════════════════════════════════════════════════════════════════

_labels = st.text(
    alphabet="收入批发零售物流服务费医疗租赁ABC ",
    min_size=1,
    max_size=8,
)
_amounts = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
).map(lambda v: round(v, 2))


@st.composite
def _region_rows(draw, section: str, prefix: str):
    n = draw(st.integers(min_value=0, max_value=4))
    rows = []
    for i in range(n):
        row = {
            A.ROW_IDENTITY_STORE_KEY_D41: f"{prefix}-{i}",
            "label": draw(_labels),
            A.SECTION_KEY_FIELD: section,
        }
        for key in _AMOUNT_KEYS:
            row[key] = draw(_amounts)
        rows.append(row)
    return rows


@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    main_rows=_region_rows(A.SECTION_KEY_MAIN, "m"),
    other_rows=_region_rows(A.SECTION_KEY_OTHER, "o"),
)
def test_property_two_region_roundtrip_field_identical(
    contract: Any, main_rows: list, other_rows: list
) -> None:
    """Property 3：任意两区动态行 build→merge 往返，label+6 金额逐字段一致、两区不串。"""
    rows = list(main_rows) + list(other_rows)
    proj = A.build_store_projection_d41(rows, contract=contract)
    # 两区 row_keys 与来源分区一致且不相交。
    assert proj.row_keys[A.ROWS_TABLE_KEY_MAIN] == tuple(
        r[A.ROW_IDENTITY_STORE_KEY_D41] for r in main_rows
    )
    assert proj.row_keys[A.ROWS_TABLE_KEY_OTHER] == tuple(
        r[A.ROW_IDENTITY_STORE_KEY_D41] for r in other_rows
    )
    assert set(proj.row_keys[A.ROWS_TABLE_KEY_MAIN]).isdisjoint(
        proj.row_keys[A.ROWS_TABLE_KEY_OTHER]
    )

    base = [_empty_base(r[A.ROW_IDENTITY_STORE_KEY_D41], r[A.SECTION_KEY_FIELD]) for r in rows]
    merged, _a, _v, _t = A.merge_projection_into_d41_rows(projection=proj, base_rows=base)
    by_id = {r[A.ROW_IDENTITY_STORE_KEY_D41]: r for r in merged}
    assert len(by_id) == len(rows)
    for src in rows:
        rid = src[A.ROW_IDENTITY_STORE_KEY_D41]
        _assert_row_equal(by_id[rid], src)
        assert by_id[rid][A.SECTION_KEY_FIELD] == src[A.SECTION_KEY_FIELD]
