# -*- coding: utf-8 -*-
"""D2 模板骨架行在 OO→HTML 镜像里的去留 —— spec d2-online-edit-platform-closure · R12。

═══ 锁的是什么缺陷 ═══

2026-10-11 和平药房 D2 实测：OO 里改了 D2-2 一格并保存，content version 已前进到 rev 40，
而镜像进 checklist 那一步抛

    StorePayloadError: 组合区行 'GTROW-D23CMB-0018' 无法判定归属（aging/customer-type）

—— D2-3 的 store 为空（绝大多数企业如此），模板受管区原样留着骨架行，首行带模板文字
「其中：」；extract 把它读回来，merge 想给它建 store 行却没有 category 信号。整次镜像失败
⇒ OO 侧已落库的编辑永远进不了 HTML。同源的 D2-2 一侧更隐蔽：和平药房的 D2-2 store 里
已经躺着 12 条 `GTROW-D22-*` 示例行（序号 1~12 +「单项计提 / 组合1…组合X」），是早先某次
镜像把模板示例当业务行写进去的。

═══ 判据全在行为上 ═══

模板原样的骨架行跳过；用户往模板空行里填了内容的骨架行照常镜像（不静默丢数据）；
base 里已有的骨架行照常更新；组合区「无 category 不猜」的 fail-closed 不放宽。
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.workpaper_sync import d2_bidirectional_bridge as B
from app.services.workpaper_sync import phase5_d2_03_bad_debt as D23
from app.services.workpaper_sync import pilot_d2_large_json as P
from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.template_skeleton_baseline import (
    SkeletonBaseline,
    pure_template_skeleton_rows,
)

_D22 = P.ROWS_TABLE_KEY
_IND = D23.ROWS_TABLE_KEY_INDIVIDUAL
_CMB = D23.ROWS_TABLE_KEY_COMBINED


def _fv(table: str, rid: str, field: str, value: Any, vt: ValueType, mode: FieldMode = FieldMode.editable) -> FieldValue:
    key = f"{table}/{rid}/{field}"
    return FieldValue(stable_key=key, value=value, value_type=vt, mode=mode, row_key=rid)


def _projection(*fvs: FieldValue) -> Projection:
    values = {fv.stable_key: fv for fv in fvs}
    row_keys: dict[str, list[str]] = {}
    for fv in fvs:
        table = fv.stable_key.split("/", 1)[0]
        bucket = row_keys.setdefault(table, [])
        if fv.row_key not in bucket:
            bucket.append(fv.row_key)
    return Projection(
        contract_id=P.PILOT_ADAPTER_ID,
        semantic_version="1.0.0",
        document_type="xlsx",
        values=values,
        row_keys={t: tuple(r) for t, r in row_keys.items()},
    )


def _d22_template_row(rid: str, *, seq: int, classification: str | None = None, group: str | None = None) -> list[FieldValue]:
    """模板原样的 D2-2 骨架行：序号 + 分类示例 + 三个公式列（受保护）。"""
    out = [
        _fv(_D22, rid, "seq", seq, ValueType.integer),
        _fv(_D22, rid, "end_balance", "0", ValueType.amount, FieldMode.formula),
        _fv(_D22, rid, "current_unadjusted", "0", ValueType.amount, FieldMode.formula),
        _fv(_D22, rid, "customer_name", "", ValueType.text),
    ]
    if classification is not None:
        out.append(_fv(_D22, rid, "credit_risk_classification", classification, ValueType.enum))
    if group is not None:
        out.append(_fv(_D22, rid, "group_name", group, ValueType.text))
    return out


def _d23_template_rows() -> list[FieldValue]:
    """两区首行的模板文字「其中：」+ 公式列（D2-3 store 为空时 extract 读回的原样内容）。"""
    return [
        _fv(_IND, "GTROW-D23IND-0013", "label", "其中：", ValueType.text),
        _fv(_IND, "GTROW-D23IND-0013", "prior_audited", "0", ValueType.amount, FieldMode.formula),
        _fv(_IND, "GTROW-D23IND-0014", "prior_audited", "0", ValueType.amount, FieldMode.formula),
        _fv(_CMB, "GTROW-D23CMB-0018", "label", "其中：", ValueType.text),
        _fv(_CMB, "GTROW-D23CMB-0018", "current_audited", "0", ValueType.amount, FieldMode.formula),
        _fv(_CMB, "GTROW-D23CMB-0019", "current_audited", "0", ValueType.amount, FieldMode.formula),
    ]


def _rid_list(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("rowId")) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 基线来自权威模板（不是手写常量）
# ═══════════════════════════════════════════════════════════════════════════


def test_baseline_covers_every_skeleton_identity_of_every_d2_spec() -> None:
    baseline = P.template_skeleton_baseline()
    expected = {
        spec.row_uuid(row)
        for spec in P.instrumentation_specs()
        for row in range(spec.first_data_row, spec.last_data_row + 1)
    }
    assert set(baseline.cells) == expected
    assert len(expected) == 12 + 4 + 4, "D2-2 R13~24 / D2-3 单项 R13~16 / 组合 R18~21"


def test_baseline_holds_the_template_literals_that_caused_the_incident() -> None:
    cells = P.template_skeleton_baseline().cells
    assert cells["GTROW-D22-0013"]["A"] == 1
    assert cells["GTROW-D22-0013"]["AI"] == "单项计提"
    assert cells["GTROW-D22-0018"]["AJ"] == "组合X"
    assert cells["GTROW-D22-0024"]["A"] == 12
    assert "AJ" not in cells["GTROW-D22-0019"], "R19 起是模板空行"
    assert cells["GTROW-D23IND-0013"]["A"] == "其中："
    assert cells["GTROW-D23CMB-0018"]["A"] == "其中："


# ═══════════════════════════════════════════════════════════════════════════
# 2. D2-2：模板原样跳过；用户内容保留；base 已有照常更新
# ═══════════════════════════════════════════════════════════════════════════


def test_d22_pure_template_rows_are_not_fabricated_into_an_empty_store() -> None:
    proj = _projection(
        *_d22_template_row("GTROW-D22-0013", seq=1, classification="单项计提", group="单项计提"),
        *_d22_template_row("GTROW-D22-0018", seq=6, classification="客户类型组合", group="组合X"),
        *_d22_template_row("GTROW-D22-0020", seq=8),
        _fv(_D22, "dr-real-1", "customer_name", "真实客户", ValueType.text),
    )
    rows, applied, _visited, touched = B.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert _rid_list(rows) == ["dr-real-1"], "模板示例行不得被当成业务行写进 HTML"
    assert touched == {"dr-real-1"} and applied == 1


def test_d22_placeholder_row_filled_in_oo_is_mirrored_not_silently_dropped() -> None:
    proj = _projection(
        *_d22_template_row("GTROW-D22-0019", seq=7)[:-1],
        _fv(_D22, "GTROW-D22-0019", "customer_name", "往模板空行里填的客户", ValueType.text),
    )
    rows, _applied, _visited, touched = B.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert _rid_list(rows) == ["GTROW-D22-0019"]
    assert rows[0]["customerName"] == "往模板空行里填的客户"
    assert rows[0]["seq"] == 7
    assert touched == {"GTROW-D22-0019"}


def test_d22_changed_template_text_counts_as_user_content() -> None:
    proj = _projection(*_d22_template_row("GTROW-D22-0014", seq=2, classification="客户类型组合", group="组合A"))
    rows, *_ = B.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert _rid_list(rows) == ["GTROW-D22-0014"], "改了模板文字（组合1→组合A）就是用户内容"


def test_d22_template_text_merely_cleared_is_not_user_content() -> None:
    proj = _projection(
        _fv(_D22, "GTROW-D22-0013", "seq", 1, ValueType.integer),
        _fv(_D22, "GTROW-D22-0013", "group_name", "", ValueType.text),
        _fv(_D22, "GTROW-D22-0013", "credit_risk_classification", "", ValueType.enum),
    )
    rows, *_ = B.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert rows == [], "只删了示例文字、没写新内容 ⇒ 没有可镜像的业务内容"


def test_d22_skeleton_rows_already_in_store_keep_updating() -> None:
    """和平药房的现状：12 条骨架行早已在 store 里 ⇒ 它们是 store 行，照常更新。"""
    base = [{P.ROW_IDENTITY_STORE_KEY: "GTROW-D22-0014", "seq": 2, "groupName": "组合1"}]
    proj = _projection(*_d22_template_row("GTROW-D22-0014", seq=2, classification="客户类型组合", group="组合9"))
    rows, applied, _visited, touched = B.merge_projection_into_store_rows(projection=proj, base_rows=base)
    assert rows[0]["groupName"] == "组合9"
    assert "GTROW-D22-0014" in touched and applied >= 1


def test_d22_store_row_reverted_to_template_text_in_oo_is_still_written() -> None:
    """base 已有的骨架行**不参与**模板判据：OO 侧把它改回模板原文也是一次真编辑。

    若判据不看 base（「与模板一致就跳过」一刀切），这次回改会被静默吞掉，store 永远停在旧值。
    """
    base = [{P.ROW_IDENTITY_STORE_KEY: "GTROW-D22-0014", "seq": 2, "groupName": "组合9"}]
    proj = _projection(*_d22_template_row("GTROW-D22-0014", seq=2, classification="客户类型组合", group="组合1"))
    rows, _applied, _visited, touched = B.merge_projection_into_store_rows(projection=proj, base_rows=base)
    assert rows[0]["groupName"] == "组合1"
    assert "GTROW-D22-0014" in touched


def test_d22_numeric_text_of_template_seq_is_still_template() -> None:
    """规范化口径复用 merge.values_equal：'7' 与模板 7 同值（integer）。"""
    proj = _projection(_fv(_D22, "GTROW-D22-0019", "seq", "7", ValueType.integer))
    rows, *_ = B.merge_projection_into_store_rows(projection=proj, base_rows=[])
    assert rows == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. D2-3：「其中：」不再打断镜像；单项区用户内容保留；组合区 fail-closed 不放宽
# ═══════════════════════════════════════════════════════════════════════════


def test_d23_template_rows_no_longer_break_the_mirror() -> None:
    merged, applied, _visited, touched = D23.merge_projection_into_d23_stores(
        projection=_projection(*_d23_template_rows()), base_states={}
    )
    assert all(rows == [] for rows in merged.values())
    assert (applied, touched) == (0, set())


def test_d23_individual_placeholder_filled_in_oo_is_mirrored() -> None:
    proj = _projection(
        *_d23_template_rows(),
        _fv(_IND, "GTROW-D23IND-0014", "label", "单项计提客户甲", ValueType.text),
    )
    merged, *_ = D23.merge_projection_into_d23_stores(projection=proj, base_states={})
    ind = merged[D23.STORE_ITEM_ID_INDIVIDUAL]
    assert _rid_list(ind) == ["GTROW-D23IND-0014"]
    assert ind[0]["category"] == "individual" and ind[0]["label"] == "单项计提客户甲"


def test_d23_combined_placeholder_filled_in_oo_still_fails_closed() -> None:
    """组合区的 category 不在 Excel 里：用户内容进来时**仍然**不猜归属。"""
    proj = _projection(
        *_d23_template_rows(),
        _fv(_CMB, "GTROW-D23CMB-0019", "label", "账龄1年以内", ValueType.text),
    )
    with pytest.raises(D23.StorePayloadError, match="无法判定归属"):
        D23.merge_projection_into_d23_stores(projection=proj, base_states={})


def test_bridge_whole_entry_merge_survives_template_rows_in_both_sheets() -> None:
    """镜像真正调用的入口（store_item_registry → merge_all_fn）。"""
    proj = _projection(
        *_d22_template_row("GTROW-D22-0013", seq=1, classification="单项计提", group="单项计提"),
        _fv(_D22, "dr-real-1", "company_code", "RT-OO-1011", ValueType.text),
        *_d23_template_rows(),
    )
    updates = B.merge_projection_into_all_d2_stores(
        projection=proj,
        base_by_item={P.STORE_ITEM_ID: [{P.ROW_IDENTITY_STORE_KEY: "dr-real-1", "companyCode": ""}]},
    )
    d22_rows, d22_applied, _v, d22_touched = updates[P.STORE_ITEM_ID]
    assert _rid_list(d22_rows) == ["dr-real-1"] and d22_rows[0]["companyCode"] == "RT-OO-1011"
    assert d22_applied == 1 and d22_touched == {"dr-real-1"}
    for sid in (D23.STORE_ITEM_ID_INDIVIDUAL, D23.STORE_ITEM_ID_AGING, D23.STORE_ITEM_ID_CUSTOMER):
        assert updates[sid][0] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. 判据的保守方向与惰性
# ═══════════════════════════════════════════════════════════════════════════


def test_unknown_skeleton_identity_is_treated_as_user_content() -> None:
    """比不了 ⇒ 当用户内容（多建一行可见可删；反方向是静默丢数据）。"""
    proj = _projection(_fv(_D22, "GTROW-ZZZ-0001", "customer_name", "x", ValueType.text))
    assert pure_template_skeleton_rows(
        proj, table_key=_D22, base_identities=set(), baseline=SkeletonBaseline()
    ) == frozenset()


def test_baseline_is_not_read_when_there_are_no_candidate_rows() -> None:
    def _must_not_be_called() -> SkeletonBaseline:
        raise AssertionError("没有候选骨架行时不得读模板")

    proj = _projection(_fv(_D22, "dr-1", "customer_name", "a", ValueType.text))
    rows, *_ = B.merge_projection_into_store_rows(
        projection=proj, base_rows=[], skeleton_baseline=_must_not_be_called
    )
    assert _rid_list(rows) == ["dr-1"]
