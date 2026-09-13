# -*- coding: utf-8 -*-
"""D4-9 Task 4 守卫：store 投影 / 合并 / 身份（行为级）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 4
Requirements: 3.1, 3.3, 3.4, 4.2
"""

from __future__ import annotations

import json

import pytest

from app.services.workpaper_sync import phase5_d4_customer_structure as M


@pytest.fixture(scope="module")
def contract():
    return M.assert_contract_file_matches_source()


def _store() -> dict:
    return {
        "current": {
            "rows": [
                {"rowId": "c1", "name": "客户甲", "amount": 1000, "quantity": 5, "priorRank": "2", "amountRatio": 0.5, "quantityRatio": 0.5},
                {"rowId": "c2", "name": "客户乙", "amount": 2000, "quantity": 8, "priorRank": "1"},
            ],
            "totalAmount": 3000,
            "totalQuantity": 13,
        },
        "prior": {
            "rows": [
                {"rowId": "p1", "name": "客户丙", "amount": 500, "quantity": 3, "priorRank": ""},
            ],
            "totalAmount": 500,
            "totalQuantity": 3,
        },
    }


class TestProjection:
    def test_three_regions_projected(self, contract) -> None:
        proj = M.build_combined_store_projection(json.dumps(_store()), contract=contract)
        # row_keys 按 table_key 分区。
        assert proj.row_keys[M.CUR_TABLE_KEY] == ("c1", "c2")
        assert proj.row_keys[M.PRI_TABLE_KEY] == ("p1",)
        # totals 4 个字段 row_key=None。
        for fk in ("current_total_amount", "current_total_quantity", "prior_total_amount", "prior_total_quantity"):
            fv = proj.get(M.stable_key_for_total(fk))
            assert fv is not None and fv.row_key is None
        assert proj.get(M.stable_key_for_total("current_total_amount")).value == 3000
        assert proj.get(M.stable_key_for_total("prior_total_quantity")).value == 3

    def test_row_values_projected(self, contract) -> None:
        proj = M.build_combined_store_projection(json.dumps(_store()), contract=contract)
        name = proj.get(M.stable_key_for_row(M.CUR_TABLE_KEY, "customer_name", "c1"))
        assert name.value == "客户甲" and name.row_key == "c1"
        amt = proj.get(M.stable_key_for_row(M.CUR_TABLE_KEY, "sales_amount", "c2"))
        assert amt.value == 2000

    def test_ratio_fields_are_protected(self, contract) -> None:
        proj = M.build_combined_store_projection(json.dumps(_store()), contract=contract)
        ratio = proj.get(M.stable_key_for_row(M.CUR_TABLE_KEY, "amount_ratio", "c1"))
        assert ratio.is_protected, "占比 formula 字段必须 protected"


class TestRoundtrip:
    def test_build_then_merge_back_preserves_editable(self, contract) -> None:
        store = _store()
        proj = M.build_combined_store_projection(json.dumps(store), contract=contract)
        merged, applied = M.merge_projection_into_store(projection=proj, base_payload=None)
        # 可编辑字段逐一还原到对应区域。
        cur_rows = {r["rowId"]: r for r in merged["current"]["rows"]}
        assert cur_rows["c1"]["name"] == "客户甲"
        assert cur_rows["c2"]["amount"] == 2000
        pri_rows = {r["rowId"]: r for r in merged["prior"]["rows"]}
        assert pri_rows["p1"]["name"] == "客户丙"
        # totals 还原。
        assert merged["current"]["totalAmount"] == 3000
        assert merged["prior"]["totalQuantity"] == 3
        # 占比 protected 不回写。
        assert "amountRatio" not in cur_rows["c1"] or cur_rows["c1"].get("amountRatio") is None

    def test_merge_does_not_cross_regions(self, contract) -> None:
        proj = M.build_combined_store_projection(json.dumps(_store()), contract=contract)
        merged, _ = M.merge_projection_into_store(projection=proj, base_payload=None)
        cur_ids = {r["rowId"] for r in merged["current"]["rows"]}
        pri_ids = {r["rowId"] for r in merged["prior"]["rows"]}
        assert cur_ids == {"c1", "c2"}
        assert pri_ids == {"p1"}
        assert not (cur_ids & pri_ids)


class TestFailClosed:
    def test_missing_row_id_fails_closed(self, contract) -> None:
        bad = {"current": {"rows": [{"name": "无id"}], "totalAmount": 0, "totalQuantity": 0}, "prior": {"rows": []}}
        with pytest.raises(M.StorePayloadError, match="缺稳定行身份"):
            M.build_combined_store_projection(json.dumps(bad), contract=contract)

    def test_duplicate_row_id_fails_closed(self, contract) -> None:
        bad = {
            "current": {"rows": [{"rowId": "x", "name": "a"}, {"rowId": "x", "name": "b"}], "totalAmount": 0, "totalQuantity": 0},
            "prior": {"rows": []},
        }
        with pytest.raises(M.StorePayloadError, match="重复行身份"):
            M.build_combined_store_projection(json.dumps(bad), contract=contract)

    def test_non_object_payload_fails_closed(self, contract) -> None:
        with pytest.raises(M.StorePayloadError):
            M.build_combined_store_projection("[]", contract=contract)

    def test_same_row_id_across_regions_is_allowed(self, contract) -> None:
        # 区域内唯一即可；current 与 prior 用同名 rowId 不冲突（按 table_key 归属）。
        store = {
            "current": {"rows": [{"rowId": "r1", "name": "甲"}], "totalAmount": 0, "totalQuantity": 0},
            "prior": {"rows": [{"rowId": "r1", "name": "乙"}], "totalAmount": 0, "totalQuantity": 0},
        }
        proj = M.build_combined_store_projection(json.dumps(store), contract=contract)
        assert proj.row_keys[M.CUR_TABLE_KEY] == ("r1",)
        assert proj.row_keys[M.PRI_TABLE_KEY] == ("r1",)
        cur = proj.get(M.stable_key_for_row(M.CUR_TABLE_KEY, "customer_name", "r1"))
        pri = proj.get(M.stable_key_for_row(M.PRI_TABLE_KEY, "customer_name", "r1"))
        assert cur.value == "甲" and pri.value == "乙"
