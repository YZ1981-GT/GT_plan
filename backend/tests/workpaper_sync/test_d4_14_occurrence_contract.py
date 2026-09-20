# -*- coding: utf-8 -*-
"""D4-14 营业收入发生检查表（穿行测试）契约结构守卫（纯函数级，不连库）。

spec: d4-14-walkthrough-writeback · Wave 5（守卫）

锁定 Requirement 3.4 / Property 4：
- 契约含 d414-managed（header_rows=2 + 7 维嵌套 json_pointer + formula_mask G37/X37/AF37/G39）
- item_id 字面量 = D4-14-transactions（store_item_id）
- 34 受管字段逐列（B-AK 除 A 序号/AG-AH 占位），value_type 金额=amount 其余 text
- 加 D4-14 后同 entry 既有张仍 parse（不打挂）
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
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.phase5_d4_14_occurrence import (  # noqa: E402
    FORMULA_MASK_D414,
    MANAGED_FIELD_SPECS_D414,
    ROWS_TABLE_KEY_D414,
    ROW_IDENTITY_STORE_KEY_D414,
    SHEET_KEY_D414,
    STORE_ITEM_ID_D414,
    UUID_COL_D414,
    stable_key_for_d414,
)


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    return D4.build_contract_payload()


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _d414_sheet(payload: dict[str, Any]) -> dict[str, Any]:
    hit = [s for s in payload["sheets"] if s["sheet_key"] == SHEET_KEY_D414]
    assert len(hit) == 1, f"契约应恰含 1 张 {SHEET_KEY_D414}，实得 {len(hit)}"
    return hit[0]


def test_d414_present_in_contract_payload(payload: dict[str, Any]) -> None:
    assert SHEET_KEY_D414 in [s["sheet_key"] for s in payload["sheets"]]


def test_d414_table_geometry(payload: dict[str, Any]) -> None:
    sheet = _d414_sheet(payload)
    table = sheet["tables"][0]
    assert table["table_key"] == ROWS_TABLE_KEY_D414
    assert table["header_rows"] == 2, "两级表头 R13-14"
    # 行身份是前端 id，store 是裸数组 → row_identity json_pointer 无 /rows 包装
    assert table["row_identity"]["json_pointer"] == f"/*/{ROW_IDENTITY_STORE_KEY_D414}"
    assert table["footer_anchor"]["marker"] == "合计"
    assert set(table["formula_mask"]) == set(FORMULA_MASK_D414) == {"G37", "X37", "AF37", "G39"}


def test_d414_fields_full_managed_set(payload: dict[str, Any]) -> None:
    """34 受管字段逐列：column_key / 嵌套 json_pointer / value_type / store_item_id。"""
    sheet = _d414_sheet(payload)
    fields = sheet["tables"][0]["fields"]
    assert len(fields) == len(MANAGED_FIELD_SPECS_D414) == 34
    by_key = {f["column_key"]: f for f in fields}
    for column_key, column, mode, value_type, json_path, _hdr in MANAGED_FIELD_SPECS_D414:
        assert column_key in by_key, f"缺字段 {column_key}"
        f = by_key[column_key]
        assert f["store_item_id"] == STORE_ITEM_ID_D414
        assert f["value_type"] == value_type
        # 7 维嵌套 json_pointer：/{row_uuid}/<维度>/<字段>
        assert f["json_pointer"] == f"/{{row_uuid}}/{json_path}"
        assert f["cell"]["column"] == column
        assert f["stable_field_key"] == stable_key_for_d414(column_key)


def test_d414_nested_pointers_cover_all_seven_dimensions(payload: dict[str, Any]) -> None:
    """7 维证据链每维都有受管字段（voucher/contract/delivery/shipping/receipt/invoice/other）。"""
    sheet = _d414_sheet(payload)
    dims = {f["json_pointer"].split("/")[2] for f in sheet["tables"][0]["fields"]}
    assert dims == {"voucher", "contract", "delivery", "shipping", "receipt", "invoice", "other"}


def test_d414_amount_columns_are_amount_type(payload: dict[str, Any]) -> None:
    """G/X/AF 三金额列 value_type=amount，数量列（前端 string）为 text。"""
    sheet = _d414_sheet(payload)
    by_col = {f["cell"]["column"]: f for f in sheet["tables"][0]["fields"]}
    for col in ("G", "X", "AF"):
        assert by_col[col]["value_type"] == "amount", f"{col} 应为 amount"
    for col in ("F", "M", "R", "W", "AE"):  # 各维数量列（string 型）
        assert by_col[col]["value_type"] == "text", f"{col} 数量列应为 text"


def test_d414_parses_and_item_id_literal(contract: Any) -> None:
    d414 = next((s for s in contract.sheets if s.sheet_key == SHEET_KEY_D414), None)
    assert d414 is not None, "d414-managed 未解析"
    table = d414.tables[0]
    assert table.header_rows == 2
    assert len(table.fields) == 34
    # item_id 字面量守卫（映射漂移即红）——payload 侧 store_item_id 全指向 D4-14-transactions
    sheet_payload = _d414_sheet(D4.build_contract_payload())
    assert all(f["store_item_id"] == "D4-14-transactions" for f in sheet_payload["tables"][0]["fields"])
    assert STORE_ITEM_ID_D414 == "D4-14-transactions"
    assert UUID_COL_D414 == "AL"


def test_d414_does_not_break_sibling_sheets(contract: Any) -> None:
    """加 D4-14 后同 entry 既有张仍在（不打挂）。"""
    keys = {s.sheet_key for s in contract.sheets}
    for sibling in ("d42-managed", "d43-managed", "d435-managed", "d47-managed", "d48-managed"):
        assert sibling in keys, f"既有 {sibling} 丢失（D4-14 打挂 entry）"
