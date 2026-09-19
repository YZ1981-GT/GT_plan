# -*- coding: utf-8 -*-
"""D4-15/16 检查表：**生产路径** store projection roundtrip（B1 provider）。

spec: d4-inspection-writeback-formula-io · B1 后端 workpaper_sync provider
参照 test_d4_ipo_checklist_store_roundtrip.py（IPO 同族），钉住新 provider
`phase5_d4_inspection_sheets` 的 build_store_projection / merge_projection_into_rows。

判据落在真实契约（`D4.build_contract_payload()` → `parse_contract`），非 stub。

D4-15/16 与 IPO 的关键差异（本测试重点覆盖）：
  1. **嵌套 json_path**：D4-15 delivery/invoice/voucher 三层（`delivery/amount` 等），
     `set_json_path` 建中间 dict —— IPO 全是扁平列，这是首个嵌套投影生产覆盖。
  2. **无 checkbox 列**：D4-15/16 无 boolean 勾选列（不测 checkbox 桥接）。
  3. **formula_mask 派生列**：D4-15 Q(一致性)/D4-16 D,I(差异) 不进受管契约（前端重算）。
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

from app.services.workpaper_sync import phase5_d4_inspection_sheets as INS  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _json_paths(code: str) -> list[str]:
    return [spec[4] for spec in INS._SHEETS[code]["fields"]]


def _be_key(code: str, json_path: str) -> str:
    for spec in INS._SHEETS[code]["fields"]:
        if spec[4] == json_path:
            return spec[0]
    raise KeyError(f"{code}: 找不到 json_path={json_path}")


def _set_nested(row: dict, json_path: str, value: Any) -> None:
    """按 slash 路径写入 row（建中间 dict），构造嵌套 store 行。"""
    parts = json_path.split("/")
    cur = row
    for seg in parts[:-1]:
        cur = cur.setdefault(seg, {})
    cur[parts[-1]] = value


def _get_nested(row: dict, json_path: str) -> Any:
    cur: Any = row
    for seg in json_path.split("/"):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
    return cur


def _build_row(code: str, rid: str, value_fn) -> dict:
    row: dict = {"id": rid}
    for spec in INS._SHEETS[code]["fields"]:
        _set_nested(row, spec[4], value_fn(spec))
    return row


# ═══════════════════════════════════════════════════════════════════════════
# P7：嵌套 rows → projection → rows 逐字段相等（含 delivery/invoice/voucher 三层）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_roundtrip_preserves_every_managed_field(code: str, contract: Any) -> None:
    """每个受管列（含嵌套三层）值经 build → merge 往返后逐字段相等。"""
    def _val(spec):
        return 1234.56 if spec[3] == "amount" else f"v-{spec[4]}"

    payload = [_build_row(code, "row-A", _val)]
    proj = INS.build_store_projection(code, payload, contract=contract)
    merged, applied, visited, touched = INS.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"id": "row-A"}]
    )
    assert len(merged) == 1
    got = merged[0]
    for spec in INS._SHEETS[code]["fields"]:
        expected = 1234.56 if spec[3] == "amount" else f"v-{spec[4]}"
        actual = _get_nested(got, spec[4])
        if spec[3] == "amount":
            assert abs(float(actual) - expected) <= 0.005, f"{code}: {spec[4]} 金额往返超容差"
        else:
            assert actual == expected, f"{code}: {spec[4]} 往返丢值/串列（实得 {actual!r}）"
    assert applied > 0 and visited >= applied
    assert touched == {"row-A"}


def test_d415_nested_three_dimensions_preserved(contract: Any) -> None:
    """🔴 D4-15 三维嵌套专项：delivery/invoice/voucher 三层结构 merge 回来仍是嵌套 dict。"""
    payload = [{
        "id": "c-1",
        "delivery": {"date": "2025-01-05", "number": "FH-001", "productName": "甲", "quantity": "10", "amount": 12000.0},
        "invoice":  {"date": "2025-01-06", "number": "FP-001", "productName": "甲", "quantity": "10", "amount": 12000.0},
        "voucher":  {"date": "2025-01-07", "number": "PZ-001", "productName": "甲", "quantity": "10", "amount": 12000.0},
    }]
    proj = INS.build_store_projection("D4-15", payload, contract=contract)
    merged, _a, _v, _t = INS.merge_projection_into_rows(
        "D4-15", projection=proj, base_rows=[{"id": "c-1"}]
    )
    got = merged[0]
    # 三层都必须是 dict（嵌套结构未被压平）
    for dim in ("delivery", "invoice", "voucher"):
        assert isinstance(got[dim], dict), f"D4-15 {dim} 被压平了（不再是嵌套 dict）"
    assert got["delivery"]["number"] == "FH-001"
    assert got["invoice"]["number"] == "FP-001"
    assert got["voucher"]["number"] == "PZ-001"
    assert abs(float(got["delivery"]["amount"]) - 12000.0) <= 0.005


# ═══════════════════════════════════════════════════════════════════════════
# 派生列（formula_mask）：不进受管契约，投影不覆盖
# ═══════════════════════════════════════════════════════════════════════════


def test_d415_consistency_column_masked_and_unmanaged(contract: Any) -> None:
    """D4-15 Q(所载信息是否一致) 不在受管字段（前端 checkConsistency 重算）+ Q 区间入 mask。"""
    paths = _json_paths("D4-15")
    assert "isConsistent" not in paths, "D4-15 isConsistent 进了受管契约 —— 会覆盖前端重算"
    assert any(m.startswith("Q") for m in INS._SHEETS["D4-15"]["formula_mask"])
    # 即便 store 带 isConsistent，投影也不产出
    proj = INS.build_store_projection(
        "D4-15", [{"id": "c-1", "isConsistent": True, "delivery": {"amount": 1}}], contract=contract
    )
    leaked = [k for k in proj.stable_keys() if str(k).endswith("/isConsistent")]
    assert not leaked, f"isConsistent 泄漏进 projection: {leaked}"


def test_d416_diff_columns_masked_and_unmanaged(contract: Any) -> None:
    """D4-16 portsDiff/taxDiff 不在受管契约（前端 calcChangeAmount 重算）+ D,I 列入 mask。"""
    paths = _json_paths("D4-16")
    assert "portsDiff" not in paths and "taxDiff" not in paths, "D4-16 差异列进了受管契约"
    masks = INS._SHEETS["D4-16"]["formula_mask"]
    assert any(m.startswith("D") for m in masks) and any(m.startswith("I") for m in masks)
    proj = INS.build_store_projection(
        "D4-16", [{"id": "r-1", "bookAmount": 100, "portsDiff": 99, "taxDiff": 88}], contract=contract
    )
    leaked = [k for k in proj.stable_keys() if str(k).endswith(("/portsDiff", "/taxDiff"))]
    assert not leaked, f"差异列泄漏进 projection: {leaked}"


# ═══════════════════════════════════════════════════════════════════════════
# amount 往返容差 + 行身份权威 + 空/缺身份/重复身份 + 超占位不截断
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_amount_roundtrip_within_tolerance(code: str, contract: Any) -> None:
    amount_paths = [s[4] for s in INS._SHEETS[code]["fields"] if s[3] == "amount"]
    assert amount_paths, f"{code}: 无 amount 列，判据恒真"
    row: dict = {"id": "row-A"}
    for p in amount_paths:
        _set_nested(row, p, 987.65)
    proj = INS.build_store_projection(code, [row], contract=contract)
    merged, _a, _v, _t = INS.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"id": "row-A"}]
    )
    for p in amount_paths:
        assert abs(float(_get_nested(merged[0], p)) - 987.65) <= 0.005, f"{code}: {p} 超容差"


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_row_identity_is_authoritative_not_ordinal(code: str, contract: Any) -> None:
    """merge 按 id 对齐（base_rows 倒序也不串行）—— 后端行定位靠 UUID 列非下标。"""
    first_path = _json_paths(code)[0]
    r1: dict = {"id": "row-1"}; _set_nested(r1, first_path, "第一行")
    r2: dict = {"id": "row-2"}; _set_nested(r2, first_path, "第二行")
    proj = INS.build_store_projection(code, [r1, r2], contract=contract)
    merged, _a, _v, _t = INS.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"id": "row-2"}, {"id": "row-1"}]
    )
    by_id = {r["id"]: r for r in merged}
    assert _get_nested(by_id["row-1"], first_path) == "第一行", f"{code}: 行按下标串了"
    assert _get_nested(by_id["row-2"], first_path) == "第二行", f"{code}: 行按下标串了"


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_row_without_identity_is_rejected(code: str, contract: Any) -> None:
    with pytest.raises(INS.D4InspectionDigestError, match="稳定行身份"):
        INS.build_store_projection(code, [{"delivery": {"amount": 1}}], contract=contract)


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_duplicate_row_identity_is_rejected(code: str, contract: Any) -> None:
    with pytest.raises(INS.D4InspectionDigestError, match="重复行身份"):
        INS.build_store_projection(code, [{"id": "dup"}, {"id": "dup"}], contract=contract)


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_empty_store_yields_no_rows(code: str, contract: Any) -> None:
    proj = INS.build_store_projection(code, [], contract=contract)
    tk = INS._SHEETS[code]["table_key"]
    assert proj.row_keys[tk] == ()
    merged, applied, _v, touched = INS.merge_projection_into_rows(code, projection=proj, base_rows=[])
    assert merged == [] and applied == 0 and touched == set()


@pytest.mark.parametrize("code", INS.INSPECTION_SHEET_CODES)
def test_rows_beyond_template_placeholder_are_not_truncated(code: str, contract: Any) -> None:
    s = INS._SHEETS[code]
    placeholder = s["last_data_row"] - s["first_data_row"] + 1
    n = placeholder + 5
    first_path = _json_paths(code)[0]
    payload = []
    for i in range(n):
        r: dict = {"id": f"row-{i}"}; _set_nested(r, first_path, f"值{i}")
        payload.append(r)
    proj = INS.build_store_projection(code, payload, contract=contract)
    assert len(proj.row_keys[s["table_key"]]) == n, f"{code}: last_data_row 被误当截断点"
    merged, _a, _v, _t = INS.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"id": f"row-{i}"} for i in range(n)]
    )
    assert len(merged) == n
    by_id = {r["id"]: r for r in merged}
    for i in range(placeholder, n):
        assert _get_nested(by_id[f"row-{i}"], first_path) == f"值{i}", f"{code}: 超占位第 {i} 行丢失"


def test_all_mapping_digests_match_frozen_values() -> None:
    """D4-15/16 mapping_digest 与冻结值一致（改列字母/列序/表头即红）。"""
    INS.assert_all_inspection_mapping_digests()
