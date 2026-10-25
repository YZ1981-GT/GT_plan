# -*- coding: utf-8 -*-
"""C 控制测试汇总表 provider 与契约守卫。

spec: c-cycle-sync-foundation-and-first-canary · Task 22/23

覆盖：
  - 几何自证（mapping digest / 模板 sha256 / 15 列 A~O）
  - 契约强校验 + 双重漂移门
  - 🔴 store ↔ projection 往返（C 域独有 per-field 标量行形态）
  - 🔴 行身份用业务键 controlId，禁位置化（引擎 FORBIDDEN_ROW_IDENTITY_KINDS）
  - 🔴 HTML 侧重排行后不错位（差异 2 的落地判据）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_c_control_test as P  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    FORBIDDEN_ROW_IDENTITY_KINDS,
    parse_contract,
)


@pytest.fixture(scope="module")
def contract():
    return P.load_contract_from_disk()


# ═══════════════════════════════════════════════════════════════════════════
# §1 几何自证
# ═══════════════════════════════════════════════════════════════════════════


class TestGeometry:
    def test_mapping_digest_selfcheck_passes(self) -> None:
        P.assert_mapping_digest()

    def test_template_sha256_not_drifted(self) -> None:
        P.assert_entry_selectable()

    def test_15_fields_columns_a_to_o(self) -> None:
        assert len(P.MANAGED_FIELD_SPECS) == 15
        cols = [f[1] for f in P.MANAGED_FIELD_SPECS]
        assert cols == [chr(ord("A") + i) for i in range(15)]

    def test_data_area_15_rows(self) -> None:
        assert P.LAST_DATA_ROW - P.FIRST_DATA_ROW + 1 == 15
        assert P.FIRST_DATA_ROW == 7
        assert P.LAST_DATA_ROW == 21

    def test_footer_after_data_area(self) -> None:
        assert P.FOOTER_ROW > P.LAST_DATA_ROW
        assert P.FOOTER_MARKER == "提示1：与控制相关的风险"

    def test_uuid_col_right_of_managed(self) -> None:
        assert P.MANAGED_LAST_COL == "O"
        assert P.UUID_COL == "P"

    def test_formula_mask_empty_data_area_zero_formula(self) -> None:
        """🔴 数据区零公式 ⇒ mask 为空（全册 6 公式在 r3/r4 页眉）。"""
        assert P.FORMULA_MASK == ()

    def test_28_wp_codes(self) -> None:
        """CC-61: 一 entry 覆盖 28 个 wp_code。"""
        assert len(P.WP_CODES) == 28
        assert len(P.WP_CODES_MAIN) == 14
        assert len(P.WP_CODES_DEVIATION) == 14
        assert "C2" in P.WP_CODES
        assert "C15-2" in P.WP_CODES


# ═══════════════════════════════════════════════════════════════════════════
# §2 契约
# ═══════════════════════════════════════════════════════════════════════════


class TestContract:
    def test_contract_file_exists(self) -> None:
        assert P.contract_path().exists()

    def test_contract_parses(self, contract) -> None:
        assert contract.contract_id == P.ADAPTER_ID
        assert contract.document_type == "xlsx"

    def test_contract_15_editable_fields(self, contract) -> None:
        assert len(contract.all_fields()) == 15
        assert len(contract.editable_field_keys()) == 15

    def test_drift_gate_passes(self) -> None:
        """双重漂移门：磁盘契约 == provider 现算。"""
        P.assert_contract_file_matches_source()

    def test_single_managed_sheet(self, contract) -> None:
        assert len(contract.sheets) == 1
        assert contract.sheets[0].excel_name == P.MANAGED_SHEET
        assert contract.sheets[0].sheet_key == P.SHEET_KEY

    def test_review_records_canary_scope(self) -> None:
        """🔴 契约须显式登记「一 entry 28 码 / 声明 C2 册为样本」。"""
        payload = json.loads(P.contract_path().read_bytes().decode("utf-8"))
        scope = payload["review"]["canary_scope"]
        assert scope["wp_code_count"] == 28
        assert scope["homogeneous_main_books"] == 14
        assert scope["declared_workbook"] == P.TEMPLATE_RELATIVE_PATH


# ═══════════════════════════════════════════════════════════════════════════
# §3 行身份：业务键，禁位置化
# ═══════════════════════════════════════════════════════════════════════════


class TestRowIdentityIsBusinessKey:
    def test_identity_field_is_control_id(self) -> None:
        assert P.ROW_IDENTITY_FIELD == "controlId"

    def test_contract_declares_field_kind(self, contract) -> None:
        table = contract.sheets[0].tables[0]
        assert table.row_identity is not None
        assert table.row_identity.kind.value == "field"
        assert table.row_identity.json_pointer == "/rows/*/controlId"

    def test_positional_kinds_are_forbidden_by_engine(self) -> None:
        """🔴 引擎明令禁位置化 —— 这是不能用 `m` 作行身份的根据。"""
        for kind in ("index", "ordinal", "position", "array_index"):
            assert kind in FORBIDDEN_ROW_IDENTITY_KINDS

    def test_contract_does_not_leak_storage_slot(self) -> None:
        """🔴 存储槽 `m` 不得出现在契约的 row_identity / json_pointer 里。"""
        payload = json.loads(P.contract_path().read_bytes().decode("utf-8"))
        table = payload["sheets"][0]["tables"][0]
        assert "slot" not in json.dumps(table["row_identity"])
        for f in table["fields"]:
            assert "{m}" not in f["json_pointer"]


# ═══════════════════════════════════════════════════════════════════════════
# §4 store ↔ projection 往返（🔴 C 域独有 per-field 标量行形态）
# ═══════════════════════════════════════════════════════════════════════════


def _store_rows(cycle: int, rows: list[dict]) -> list[dict]:
    """把行对象列表铺成 per-field 标量 checklist_responses（模拟真库形态）。"""
    items: list[dict] = []
    for i, row in enumerate(rows, start=1):
        for field, _col, _mode, _vt, _label in P.MANAGED_FIELD_SPECS:
            if field not in row:
                continue
            slot_name = P.store_slot_of(field)
            val = row[field]
            text = None if val is None else str(val)
            items.append(
                {
                    "item_id": P.summary_item_id(cycle, i, field),
                    "conclusion": text if slot_name == "conclusion" else None,
                    "remark": text if slot_name == "remark" else None,
                }
            )
    return items


_ROW_A = {
    "subProcess": "销售与收款",
    "controlId": "SC-01",
    "controlName": "销售订单审批",
    "description": "所有销售订单经销售总监审批后方可执行",
    "affectedItems": "营业收入、应收账款",
    "assertion": "发生",
    "attribute": "人工控制",
    "frequency": "每笔交易",
    "relatedRisk": "未经授权的销售",
    "testMethod": "检查",
    "sampleSize": 25,
    "hasDeviation": "否",
    "remediation": "",
    "defect": "",
    "indexRef": "C2-1-1",
}
_ROW_B = {
    "subProcess": "销售与收款",
    "controlId": "SC-02",
    "controlName": "发货单与订单核对",
    "description": "仓库发货前核对发货单与销售订单一致性",
    "affectedItems": "营业收入",
    "assertion": "完整性",
    "attribute": "人工控制",
    "frequency": "每笔交易",
    "relatedRisk": "发货与订单不符",
    "testMethod": "重新执行",
    "sampleSize": 40,
    "hasDeviation": "是",
    "remediation": "2025Q3 起增加双人复核",
    "defect": "ITGC#1",
    "indexRef": "C2-1-2",
}


class TestStoreProjectionRoundtrip:
    """🔴 真库分母非空（136 行），但本测试用合成载荷以覆盖全 15 字段。"""

    def test_parse_store_rows_rebuilds_from_scalar_rows(self) -> None:
        store = _store_rows(2, [_ROW_A, _ROW_B])
        # 15 字段 × 2 行 = 30 个 checklist_responses 行
        assert len(store) == 30
        parsed = P.parse_store_rows(store, cycle_number=2)
        assert [identity for identity, _s, _r in parsed] == ["SC-01", "SC-02"]
        assert [slot for _i, slot, _r in parsed] == [1, 2]

    def test_roundtrip_preserves_all_15_fields(self, contract) -> None:
        store = _store_rows(2, [_ROW_A, _ROW_B])
        proj = P.build_store_projection(store, contract=contract, cycle_number=2)
        assert proj.row_keys[P.TABLE_KEY] == ("SC-01", "SC-02")

        back = P.merge_projection_into_store_items(
            projection=proj, base_responses=store, cycle_number=2
        )
        reparsed = {i: r for i, _s, r in P.parse_store_rows(back, cycle_number=2)}
        for identity, src in (("SC-01", _ROW_A), ("SC-02", _ROW_B)):
            for field, _c, _m, _vt, _l in P.MANAGED_FIELD_SPECS:
                expected = src[field]
                actual = reparsed[identity].get(field)
                # 全字段以文本落库；空串与 None 等价
                if expected in ("", None):
                    assert actual in ("", None), f"{identity}.{field}={actual!r}"
                else:
                    assert str(actual) == str(expected), (
                        f"{identity}.{field}: {actual!r} != {expected!r}"
                    )

    def test_reorder_does_not_misplace_rows(self, contract) -> None:
        """🔴 差异 2 的落地判据：HTML 侧重排行后，按 controlId 定位仍正确。

        原序 [SC-01(slot1), SC-02(slot2)] → 重排为 [SC-02, SC-01]。
        位置化身份会把 SC-02 的数据写进 slot1（错位）；业务键身份不会。
        """
        original = _store_rows(2, [_ROW_A, _ROW_B])
        reordered = _store_rows(2, [_ROW_B, _ROW_A])  # SC-02 现在占 slot1

        proj = P.build_store_projection(reordered, contract=contract, cycle_number=2)
        # 投影的行身份跟着业务键走，不是跟着槽走
        assert proj.row_keys[P.TABLE_KEY] == ("SC-02", "SC-01")

        # 以**原序** store 为 base 合并重排后的投影：SC-02 应回写到它在 base 里的槽 2
        merged = P.merge_projection_into_store_items(
            projection=proj, base_responses=original, cycle_number=2
        )
        by_id = {it["item_id"]: it for it in merged}
        # SC-02 在 base（原序）占 slot 2 ⇒ 其 controlName 应写到 slot 2
        assert by_id["C2-sum-2-controlName"]["remark"] == _ROW_B["controlName"]
        assert by_id["C2-sum-1-controlName"]["remark"] == _ROW_A["controlName"]

    def test_missing_identity_fails_closed(self, contract) -> None:
        """🔴 controlId 为空即抛，禁用下标兜底。"""
        bad = dict(_ROW_A)
        bad["controlId"] = ""
        store = _store_rows(2, [bad])
        with pytest.raises(P.StorePayloadError, match="缺少行身份"):
            P.parse_store_rows(store, cycle_number=2)

    def test_duplicate_identity_fails_closed(self, contract) -> None:
        """🔴 控制编号重复即抛。"""
        store = _store_rows(2, [_ROW_A, dict(_ROW_A)])
        with pytest.raises(P.StorePayloadError, match="重复"):
            P.parse_store_rows(store, cycle_number=2)

    def test_other_cycle_rows_are_ignored(self, contract) -> None:
        """跨循环隔离：C10 的行不会被 C2 的投影吸进来（CC-19）。"""
        mixed = _store_rows(2, [_ROW_A]) + _store_rows(10, [_ROW_B])
        parsed = P.parse_store_rows(mixed, cycle_number=2)
        assert [i for i, _s, _r in parsed] == ["SC-01"]

    def test_conclusion_vs_remark_slot_split(self) -> None:
        """枚举类 6 字段 + sampleSize 存 conclusion 槽，其余存 remark。"""
        assert P.store_slot_of("assertion") == "conclusion"
        assert P.store_slot_of("hasDeviation") == "conclusion"
        assert P.store_slot_of("sampleSize") == "conclusion"
        assert P.store_slot_of("controlName") == "remark"
        assert P.store_slot_of("description") == "remark"
