"""S7-3: 最小合成样本 smoke test — CI 必跑，不依赖真实 `数据/` 目录。

验证引擎对合成样本（balance + ledger + 核算维度）的完整识别+转换链路。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.ledger_import.converter import (
    convert_balance_rows,
    convert_ledger_rows,
)
from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify
from app.services.ledger_import.parsers.excel_parser import iter_excel_rows_from_path
from app.services.ledger_import.validator import validate_l1
from app.services.ledger_import.writer import prepare_rows_with_raw_extra

# 动态导入 fixture 生成函数
import sys
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ledger_samples"
sys.path.insert(0, str(_FIXTURE_DIR))
from minimal_balance_ledger import create_minimal_sample  # type: ignore


@pytest.fixture
def minimal_sample_path(tmp_path: Path) -> Path:
    """生成最小合成样本到临时目录。"""
    return create_minimal_sample(tmp_path / "minimal.xlsx")


def test_minimal_sample_detection(minimal_sample_path: Path):
    """Sheet 识别：余额表 → balance, 序时账 → ledger。"""
    fd = detect_file_from_path(str(minimal_sample_path), minimal_sample_path.name)
    types = {}
    for sheet in fd.sheets:
        identified = identify(sheet)
        types[identified.sheet_name] = identified.table_type

    assert "科目余额表" in types, f"应有'科目余额表' sheet, got {list(types)}"
    assert "序时账" in types, f"应有'序时账' sheet, got {list(types)}"
    assert types["科目余额表"] == "balance"
    assert types["序时账"] == "ledger"


def test_minimal_sample_balance_conversion(minimal_sample_path: Path):
    """Balance sheet 转换：期望主表 + 辅助余额都有数据。"""
    fd = detect_file_from_path(str(minimal_sample_path), minimal_sample_path.name)
    bal_sheet = None
    for sheet in fd.sheets:
        identified = identify(sheet)
        if identified.table_type == "balance":
            bal_sheet = identified
            break
    assert bal_sheet is not None

    col_mapping = {
        cm.column_header: cm.standard_field
        for cm in bal_sheet.column_mappings
        if cm.standard_field and cm.confidence >= 50
    }
    headers = bal_sheet.detection_evidence.get("header_cells", [])

    parsed = []
    for chunk in iter_excel_rows_from_path(
        str(minimal_sample_path), "科目余额表",
        data_start_row=bal_sheet.data_start_row,
    ):
        for raw in chunk:
            row_dict = {}
            for i, val in enumerate(raw):
                if i < len(headers):
                    row_dict[headers[i]] = val
            parsed.append(row_dict)

    std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
    _, cleaned = validate_l1(std_rows, "balance", column_mapping=col_mapping)
    bal, aux_bal = convert_balance_rows(cleaned)

    # 去重后主表按 (company, account_code) 分组：1001/1002/1122/2202/4103 = 5 组
    assert len(bal) == 5, f"预期主表精确 5 行（去重后每 account_code 1 条）, 实际 {len(bal)}"
    # account_code 不应重复
    codes = [r["account_code"] for r in bal]
    assert len(codes) == len(set(codes)), f"主表 account_code 重复: {codes}"
    # 1002 用原汇总行值（48000），不是聚合（48000）——此处恰好相等但标记不同
    b1002 = next(r for r in bal if r["account_code"] == "1002")
    assert not (b1002.get("raw_extra") or {}).get("_aggregated_from_aux"), \
        "1002 有汇总行，主表应用汇总行不应标记聚合"
    # 1122 仅有明细，应是聚合行
    b1122 = next(r for r in bal if r["account_code"] == "1122")
    assert (b1122.get("raw_extra") or {}).get("_aggregated_from_aux") is True, \
        "1122 无汇总行仅明细，主表应是聚合虚拟汇总"

    assert len(aux_bal) >= 4, f"预期辅助余额 ≥ 4 行（2 银行 + 2 客户 + 1 供应商）, 实际 {len(aux_bal)}"

    # 辅助维度类型必须含金融机构/客户/供应商
    aux_types = {r["aux_type"] for r in aux_bal if r.get("aux_type")}
    assert "金融机构" in aux_types, f"应含'金融机构', got {aux_types}"
    assert "客户" in aux_types, f"应含'客户', got {aux_types}"
    assert "供应商" in aux_types, f"应含'供应商', got {aux_types}"


def test_minimal_sample_ledger_conversion(minimal_sample_path: Path):
    """Ledger sheet 转换：主表 + 辅助明细都有数据。"""
    fd = detect_file_from_path(str(minimal_sample_path), minimal_sample_path.name)
    led_sheet = None
    for sheet in fd.sheets:
        identified = identify(sheet)
        if identified.table_type == "ledger":
            led_sheet = identified
            break
    assert led_sheet is not None

    col_mapping = {
        cm.column_header: cm.standard_field
        for cm in led_sheet.column_mappings
        if cm.standard_field and cm.confidence >= 50
    }
    headers = led_sheet.detection_evidence.get("header_cells", [])

    parsed = []
    for chunk in iter_excel_rows_from_path(
        str(minimal_sample_path), "序时账",
        data_start_row=led_sheet.data_start_row,
    ):
        for raw in chunk:
            row_dict = {}
            for i, val in enumerate(raw):
                if i < len(headers):
                    row_dict[headers[i]] = val
            parsed.append(row_dict)

    std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
    _, cleaned = validate_l1(std_rows, "ledger", column_mapping=col_mapping)
    ledger, aux_ledger, aux_stats = convert_ledger_rows(cleaned)

    assert len(ledger) >= 5, f"预期主表 ≥ 5 行, 实际 {len(ledger)}"
    assert len(aux_ledger) >= 3, f"预期辅助明细 ≥ 3 行, 实际 {len(aux_ledger)}"
    # 至少识别 3 种维度
    assert len(aux_stats) >= 3, f"预期 ≥ 3 种维度类型, 实际 {aux_stats}"


def test_minimal_sample_aux_code_null(minimal_sample_path: Path):
    """S6-7 验证：转换后 aux_code 应为 None 不是空串。"""
    fd = detect_file_from_path(str(minimal_sample_path), minimal_sample_path.name)
    for sheet in fd.sheets:
        identified = identify(sheet)
        if identified.table_type != "balance":
            continue
        col_mapping = {
            cm.column_header: cm.standard_field
            for cm in identified.column_mappings
            if cm.standard_field and cm.confidence >= 50
        }
        headers = identified.detection_evidence.get("header_cells", [])

        parsed = []
        for chunk in iter_excel_rows_from_path(
            str(minimal_sample_path), identified.sheet_name,
            data_start_row=identified.data_start_row,
        ):
            for raw in chunk:
                d = {}
                for i, v in enumerate(raw):
                    if i < len(headers):
                        d[headers[i]] = v
                parsed.append(d)
        std_rows, _ = prepare_rows_with_raw_extra(parsed, col_mapping, headers)
        _, cleaned = validate_l1(std_rows, "balance", column_mapping=col_mapping)
        _, aux_bal = convert_balance_rows(cleaned)

        # 所有有 aux_type 的行，aux_code 要么是非空 str 要么是 None
        for r in aux_bal:
            if r.get("aux_type"):
                assert r["aux_code"] is None or (
                    isinstance(r["aux_code"], str) and r["aux_code"].strip()
                ), f"aux_code 违反策略: {r}"
        break
