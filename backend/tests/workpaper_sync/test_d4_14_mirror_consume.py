# -*- coding: utf-8 -*-
"""D4-14 OO→HTML 消费侧（第四维判据）守卫。

spec: d4-14-walkthrough-writeback · Wave 5 · Property 5

对齐 test_d4_mirror_shape_invariants.py 判据面，专测 D4-14：
- D4-14-transactions ∈ STORE_ITEM_IDS（rows 循环可读 base，不走专用 dict 块）
- merge_projection_into_all_d4_stores 对 D4-14 返回 4-tuple（mirror 硬解包不抛）
- applied>0 时不抹 HTML-only 维度字段、不静默投空（list base 正确消费）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.phase5_d4_14_occurrence import (  # noqa: E402
    STORE_ITEM_ID_D414,
    stable_key_for_d414,
)


@pytest.fixture(scope="module")
def contract() -> Any:
    return D4.assert_contract_file_matches_source()


def test_d414_in_store_item_ids_rows_loop() -> None:
    """D4-14 store 是裸数组行 store，须在 STORE_ITEM_IDS（rows 循环消费，非专用 dict 块）。"""
    assert STORE_ITEM_ID_D414 in D4.STORE_ITEM_IDS


def test_merge_all_returns_four_tuple_for_d414(contract: Any) -> None:
    """merge_projection_into_all_d4_stores 对 D4-14 返回 4-tuple（mirror 硬解包不抛）。"""
    projection = D4.build_combined_store_projection({}, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(projection=projection, base_by_item={})
    assert STORE_ITEM_ID_D414 in updates, "D4-14 未进 merge_all 输出"
    v = updates[STORE_ITEM_ID_D414]
    assert isinstance(v, tuple) and len(v) == 4, f"D4-14 应返回 4-tuple，实得 {type(v).__name__}"
    rows, applied, _visited, _touched = v  # 复刻 mirror 硬解包
    assert isinstance(rows, list)


def test_mirror_consume_preserves_html_only_and_not_empty(contract: Any) -> None:
    """applied>0 时受管字段回写、HTML-only 维度字段保留、不静默投空（list base 消费）。"""
    rid = "t-mirror-1"
    # projection 只投受管字段（模拟 OO 侧回读）
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values = {
        stable_key_for_d414("voucher_customer_name", rid): FieldValue(
            stable_key=stable_key_for_d414("voucher_customer_name", rid),
            value="甲公司", value_type="text", mode="editable", row_key=rid,
        ),
        stable_key_for_d414("invoice_amount", rid): FieldValue(
            stable_key=stable_key_for_d414("invoice_amount", rid),
            value=8888.0, value_type="amount", mode="editable", row_key=rid,
        ),
    }
    projection = Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={"walkthrough_transactions": (rid,)},
    )
    # base 含 id + HTML-only 派生字段
    base = [{"id": rid, "voucher": {"month": "6"}, "consistencyScore": 100, "conclusion": "无异常"}]
    updates = D4.merge_projection_into_all_d4_stores(
        projection=projection, base_by_item={STORE_ITEM_ID_D414: base}
    )
    rows, applied, _v, touched = updates[STORE_ITEM_ID_D414]
    assert applied > 0 and rid in touched, "applied 应 >0 且命中该行（未静默投空）"
    by_id = {r["id"]: r for r in rows}
    assert by_id[rid]["voucher"]["customerName"] == "甲公司", "受管字段回写"
    assert by_id[rid]["invoice"]["amount"] == 8888.0
    # HTML-only 派生字段不被抹
    assert by_id[rid]["voucher"]["month"] == "6", "HTML-only month 应保留"
    assert by_id[rid]["consistencyScore"] == 100, "HTML-only consistencyScore 应保留"
    assert by_id[rid]["conclusion"] == "无异常"


def test_empty_base_does_not_crash_and_no_phantom_rows(contract: Any) -> None:
    """空 base + 空 projection：不抛、不产生幻影行。"""
    projection = D4.build_combined_store_projection({STORE_ITEM_ID_D414: []}, contract=contract)
    updates = D4.merge_projection_into_all_d4_stores(
        projection=projection, base_by_item={STORE_ITEM_ID_D414: []}
    )
    rows, applied, _v, _t = updates[STORE_ITEM_ID_D414]
    assert rows == [] and applied == 0
