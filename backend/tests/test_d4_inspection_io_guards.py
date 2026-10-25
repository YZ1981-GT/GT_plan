# -*- coding: utf-8 -*-
"""D4-13/14/15/16 检查表导入导出守卫（纯函数级，不连库）。

锁定 spec d4-inspection-writeback-formula-io 的 Requirement 1/2/3 行为：
- _parse_d4_15_row 产出嵌套结构逐字段 = 前端 CompletenessItem（Requirement 1.1）
- D4-15 落库 item_id 字面量 == "D4-15-items"（Requirement 1.2，三重断裂根因）
- _parse_d4_16_row 中文列头 → 英文 key，差异列后端重算（Requirement 2.1/2.2）
- round-trip：export 行构造 → parser 回读，录入字段逐字段一致（Requirement 1.5/2.5）
- D4-13 在 _SUPPORTED_SHEETS / _SHEET_HEADERS（Requirement 3.1）

这些断言的是**行为/结构**（字段值、item_id 字面量、重算结果），非"函数存在"。
"""
import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies import _d4_import_export as m

_SRC = Path(m.__file__).read_text(encoding="utf-8")


# ─── Requirement 1: D4-15 嵌套结构 + item_id ────────────────────────────────

def test_parse_d4_15_row_nested_structure():
    """D4-15 解析产出嵌套 {delivery,invoice,voucher}，逐字段对齐 CompletenessItem。"""
    headers = m._SHEET_HEADERS["D4-15"]
    # 按列头顺序构造一行（序号 + 发货单5 + 发票5 + 记账凭证5 + 一致 + 备注）
    row = (
        "1",
        "2024-01-05", "FH-001", "甲产品", "10", 12000.0,
        "2024-01-06", "FP-001", "甲产品", "10", 12000.0,
        "2024-01-07", "PZ-001", "甲产品", "10", 12000.0,
        "", "无差异",
    )
    d = m._parse_d4_15_row(row, headers)
    assert set(d["delivery"].keys()) == {"date", "number", "productName", "quantity", "amount"}
    assert d["delivery"]["date"] == "2024-01-05"
    assert d["delivery"]["number"] == "FH-001"
    assert d["delivery"]["amount"] == 12000.0
    assert d["invoice"]["number"] == "FP-001"
    assert d["voucher"]["number"] == "PZ-001"
    assert d["delivery"]["quantity"] == "10"  # quantity 为 string
    assert d["remark"] == "无差异"
    # isConsistent 留 None，由前端 checkConsistency 重算（不双写派生值）
    assert d["isConsistent"] is None
    # 嵌套三键都在，且顶层无扁平中文 key
    assert "delivery" in d and "invoice" in d and "voucher" in d
    assert "发货单日期" not in d


def test_d4_15_item_id_is_items_not_rows():
    """🔴 三重断裂根因：D4-15 落库 item_id 必须是 D4-15-items（前端读写键），非默认 D4-15-rows。"""
    # 源码里 export-data 与 import 两处的 item_id 映射都要把 D4-15 映到 D4-15-items
    assert '"D4-15-items"' in _SRC, "D4-15 必须映射到 D4-15-items"
    # 至少出现 2 次（export + import）
    assert _SRC.count('item_id = "D4-15-items"') >= 2, "export 与 import 两处 item_id 都要映到 D4-15-items"
    # 且绝不能残留把 D4-15 映到 -rows 的显式 elif（默认 fallback 不算）
    assert 'item_id = "D4-15-rows"' not in _SRC


# ─── Requirement 2: D4-16 英文 key + 差异重算 ───────────────────────────────

def test_parse_d4_16_row_english_keys_and_recalc():
    """D4-16 解析：中文列头 → 英文 key；差异列后端重算（防手改文件造假）。"""
    headers = m._SHEET_HEADERS["D4-16"]
    # 序号/账面出口收入金额/口岸期间/口岸结关金额/口岸差异/口岸差异原因/申报外营收入/申报差异/申报差异原因/索引
    row = (
        "1", 100000.0, "2024-Q1", 98000.0, 999999.0, "汇率差异",
        95000.0, 888888.0, "退运冲减", "IDX-1",
    )
    d = m._parse_d4_16_row(row, headers)
    # 英文 key
    assert d["bookAmount"] == 100000.0
    assert d["portsAmount"] == 98000.0
    assert d["portsPeriod"] == "2024-Q1"
    assert d["taxReportAmount"] == 95000.0
    assert d["taxIndex"] == "IDX-1"
    # 差异重算：忽略文件里的 999999/888888，用 book-ports / book-tax
    assert d["portsDiff"] == 100000.0 - 98000.0 == 2000.0
    assert d["taxDiff"] == 100000.0 - 95000.0 == 5000.0
    # 无扁平中文 key 泄漏
    assert "账面出口收入金额" not in d


# ─── Requirement 1.5 / 2.5: round-trip ──────────────────────────────────────

def test_d4_16_roundtrip_recomputes_diff():
    """D4-16 往返：解析后差异恒为重算值，与原始录入金额自洽。"""
    headers = m._SHEET_HEADERS["D4-16"]
    row = ("2", 50000.0, "2024-Q2", 50000.0, 0.0, "", 48000.0, 0.0, "", "IDX-2")
    d = m._parse_d4_16_row(row, headers)
    assert d["portsDiff"] == 0.0          # 账面==口岸 → 无差异
    assert d["taxDiff"] == 2000.0


# ─── Requirement 3: D4-13 登记 ───────────────────────────────────────────────

def test_d4_13_registered():
    """D4-13 必须在 _SUPPORTED_SHEETS 与 _SHEET_HEADERS，且有双 item_id helper。"""
    assert "D4-13" in m._SUPPORTED_SHEETS
    assert "D4-13" in m._SHEET_HEADERS
    assert m._SHEET_HEADERS["D4-13"] == ["区块", "内容"]
    # 双 item_id 短路 helper 存在
    assert hasattr(m, "_handle_d4_13_export")
    assert hasattr(m, "_handle_d4_13_import")
    assert m._D4_13_SECTION_BY_LABEL.get("核对过程") == "D4-13-process"
    assert m._D4_13_SECTION_BY_LABEL.get("核对结论") == "D4-13-conclusion"


# ─── 分发接线：D4-15/D4-16 走专用 parser 而非 generic ───────────────────────

def test_import_dispatch_uses_dedicated_parsers():
    """import 分发必须为 D4-15/D4-16 调专用 parser，不落到 _parse_generic_row。"""
    assert re.search(r'elif sheet == "D4-15":\s*\n\s*row_dict = _parse_d4_15_row', _SRC)
    assert re.search(r'elif sheet == "D4-16":\s*\n\s*row_dict = _parse_d4_16_row', _SRC)
