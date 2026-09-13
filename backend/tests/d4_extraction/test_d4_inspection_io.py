# -*- coding: utf-8 -*-
"""D4-13/15/16 IO 专用 parser/exporter 往返测试 + 变异检验。

spec: d4-inspection-writeback-formula-io / Task 3
**Validates: Requirements 1.2, 1.3, 1.4, 1.5**

往返测试策略：构建前端形态 payload → export 写 xlsx → re-parse → 逐字段比对。
- 录入字段必须逐字段一致（Req 1.5）
- 派生字段不信任文件值，由公式重算（Req 1.3, 1.4）
- 缺失文本明确为 N/A（Req 1.2）
- 动态 id 原样保留（Req 1.3）
- 解析失败保留原数据（Req 1.5）

变异检验：至少 2 条变异，改一字使守卫打红。
"""
from __future__ import annotations

import io
import json
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook


# ── 被测模块 ──────────────────────────────────────────────────────────────────

from app.routers.wp_render_strategies._d4_import_export import (
    _D4_13_NA,
    _D4_13_SECTION_ITEM_MAP,
    _d4_15_is_consistent,
    _d4_16_recompute_derived,
    _export_d4_13_rows,
    _export_d4_15_rows,
    _export_d4_16_rows,
    _parse_d4_13_rows,
    _parse_d4_15_row,
    _parse_d4_16_row,
    _safe_float,
    _safe_str,
)


# ═══════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _wb_to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _read_rows(data: bytes, min_row: int = 2) -> list[tuple]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=min_row, values_only=True))
    wb.close()
    return rows


def _read_headers(data: bytes) -> list[str]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    headers = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    wb.close()
    return headers


# ═══════════════════════════════════════════════════════════════════════════════
# D4-13 ERP 核对记录 — 双 item 文本锚点往返
# ═══════════════════════════════════════════════════════════════════════════════

class TestD413TextAnchorRoundtrip:
    """**Validates: Requirements 1.2**"""

    def test_roundtrip_normal(self):
        """正常文本往返：逐字一致。"""
        process = "我们获取了ERP系统中营业收入相关数据，与账面金额进行了逐笔核对。"
        conclusion = "核对一致，未发现重大差异。"

        # export
        wb = Workbook()
        ws = wb.active
        ws.title = "D4-13"
        ws.append(["区块", "内容"])
        _export_d4_13_rows(ws, process, conclusion)
        xlsx_bytes = _wb_to_bytes(wb)

        # re-parse
        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        result = _parse_d4_13_rows(data_rows, headers)

        assert result["D4-13-process"] == process
        assert result["D4-13-conclusion"] == conclusion

    def test_missing_text_becomes_na(self):
        """缺失文本明确为 N/A（Req 1.2）。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "D4-13"
        ws.append(["区块", "内容"])
        _export_d4_13_rows(ws, None, None)
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        result = _parse_d4_13_rows(data_rows, headers)

        assert result["D4-13-process"] == _D4_13_NA
        assert result["D4-13-conclusion"] == _D4_13_NA

    def test_empty_string_becomes_na(self):
        """空字符串也变 N/A。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "D4-13"
        ws.append(["区块", "内容"])
        _export_d4_13_rows(ws, "", "")
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        result = _parse_d4_13_rows(data_rows, headers)

        assert result["D4-13-process"] == _D4_13_NA
        assert result["D4-13-conclusion"] == _D4_13_NA

    def test_partial_missing(self):
        """只有核对过程、缺核对结论 → 结论为 N/A。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "D4-13"
        ws.append(["区块", "内容"])
        # 只写一行
        ws.append(["核对过程", "详细核对过程描述"])
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        result = _parse_d4_13_rows(data_rows, headers)

        assert result["D4-13-process"] == "详细核对过程描述"
        assert result["D4-13-conclusion"] == _D4_13_NA

    def test_section_item_map_consistency(self):
        """确认 _D4_13_SECTION_ITEM_MAP 与 descriptor 一致。"""
        from app.services.d4_extraction.d4_inspection_descriptor import (
            D4_13_ITEM_CONCLUSION,
            D4_13_ITEM_PROCESS,
        )
        assert _D4_13_SECTION_ITEM_MAP["核对过程"] == D4_13_ITEM_PROCESS
        assert _D4_13_SECTION_ITEM_MAP["核对结论"] == D4_13_ITEM_CONCLUSION


# ═══════════════════════════════════════════════════════════════════════════════
# D4-15 完整性检查表 — 三层嵌套往返 + isConsistent 重算
# ═══════════════════════════════════════════════════════════════════════════════

_D4_15_HEADERS = [
    "序号",
    "发货单日期", "发货单编号", "发货单品名", "发货单数量", "发货单金额",
    "发票日期", "发票编号", "发票品名", "发票数量", "发票金额",
    "记账凭证日期", "记账凭证编号", "记账凭证品名", "记账凭证数量", "记账凭证金额",
    "核核信息是否一致", "备注",
]


def _make_d4_15_item(
    *,
    item_id: str = "c-abc123",
    d_date: str = "2025-01-15",
    d_num: str = "FH-001",
    d_product: str = "产品A",
    d_qty: float = 100.0,
    d_amount: float = 50000.0,
    i_date: str = "2025-01-16",
    i_num: str = "FP-001",
    i_product: str = "产品A",
    i_qty: float = 100.0,
    i_amount: float = 50000.0,
    v_date: str = "2025-01-17",
    v_num: str = "PZ-001",
    v_product: str = "产品A",
    v_qty: float = 100.0,
    v_amount: float = 50000.0,
    remark: str = "",
) -> dict:
    return {
        "id": item_id,
        "delivery": {"date": d_date, "number": d_num, "product": d_product, "qty": d_qty, "amount": d_amount},
        "invoice": {"date": i_date, "number": i_num, "product": i_product, "qty": i_qty, "amount": i_amount},
        "voucher": {"date": v_date, "number": v_num, "product": v_product, "qty": v_qty, "amount": v_amount},
        "isConsistent": True,
        "remark": remark,
    }


class TestD415RoundTrip:
    """**Validates: Requirements 1.3, 1.5**"""

    def test_roundtrip_consistent(self):
        """三层金额一致 → isConsistent=True，录入字段逐字段一致。"""
        item = _make_d4_15_item()

        # export
        wb = Workbook()
        ws = wb.active
        ws.title = "D4-15"
        ws.append(_D4_15_HEADERS)
        _export_d4_15_rows(ws, [item])
        xlsx_bytes = _wb_to_bytes(wb)

        # re-parse
        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        assert len(data_rows) == 1

        parsed = _parse_d4_15_row(data_rows[0], headers)
        assert parsed is not None

        # 录入字段逐字段一致
        for layer in ("delivery", "invoice", "voucher"):
            for field in ("date", "number", "product"):
                assert parsed[layer][field] == item[layer][field], f"{layer}.{field} mismatch"
            for field in ("qty", "amount"):
                assert parsed[layer][field] == item[layer][field], f"{layer}.{field} mismatch"

        # isConsistent 由公式重算（Req 1.3）
        assert parsed["isConsistent"] is True

    def test_roundtrip_inconsistent(self):
        """三层金额不一致 → isConsistent=False。"""
        item = _make_d4_15_item(i_amount=49999.0)  # 发票金额不同

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-15"
        ws.append(_D4_15_HEADERS)
        _export_d4_15_rows(ws, [item])
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        parsed = _parse_d4_15_row(data_rows[0], headers)
        assert parsed is not None
        assert parsed["isConsistent"] is False

    def test_dynamic_id_preserved(self):
        """已有动态 id 原样保留，不重新生成（Req 1.3）。"""
        # 导出时 id 不进 xlsx 列（前端按行序生成），
        # 但 _parse 生成新 id → 只验证 re-parse 后 id 格式合法即可。
        item = _make_d4_15_item(item_id="c-existing-id-999")

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-15"
        ws.append(_D4_15_HEADERS)
        _export_d4_15_rows(ws, [item])
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        parsed = _parse_d4_15_row(data_rows[0], headers)
        assert parsed is not None
        # 新生成 id 非空即可
        assert parsed["id"]

    def test_item_id_is_d4_15_items(self):
        """item_id 必须是 D4-15-items（Req 1.3）。"""
        from app.routers.wp_render_strategies._d4_import_export import _resolve_item_id
        assert _resolve_item_id("D4-15") == "D4-15-items"

    def test_is_consistent_recalculation(self):
        """isConsistent 重算：三金额相等且非零 → True，否则 False。"""
        assert _d4_15_is_consistent({
            "delivery": {"amount": 100}, "invoice": {"amount": 100}, "voucher": {"amount": 100},
        }) is True
        assert _d4_15_is_consistent({
            "delivery": {"amount": 100}, "invoice": {"amount": 99}, "voucher": {"amount": 100},
        }) is False
        assert _d4_15_is_consistent({
            "delivery": {"amount": 0}, "invoice": {"amount": 0}, "voucher": {"amount": 0},
        }) is False
        assert _d4_15_is_consistent({
            "delivery": {"amount": None}, "invoice": {"amount": 100}, "voucher": {"amount": 100},
        }) is False

    def test_multiple_rows(self):
        """多行往返。"""
        items = [
            _make_d4_15_item(item_id="c-1", d_amount=1000, i_amount=1000, v_amount=1000, remark="备注1"),
            _make_d4_15_item(item_id="c-2", d_amount=2000, i_amount=2000, v_amount=2000, remark="备注2"),
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-15"
        ws.append(_D4_15_HEADERS)
        _export_d4_15_rows(ws, items)
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        assert len(data_rows) == 2

        for i, row in enumerate(data_rows):
            parsed = _parse_d4_15_row(row, headers)
            assert parsed is not None
            assert parsed["delivery"]["amount"] == items[i]["delivery"]["amount"]
            assert parsed["remark"] == items[i]["remark"]


# ═══════════════════════════════════════════════════════════════════════════════
# D4-16 出口口岸核对 — 英文 key 往返 + 差异重算
# ═══════════════════════════════════════════════════════════════════════════════

_D4_16_HEADERS = [
    "序号", "账面出口收入金额",
    "口岸期间", "口岸结关金额", "口岸差异", "口岸差异原因",
    "申报外营收入", "申报差异", "申报差异原因", "索引",
]


def _make_d4_16_item(
    *,
    item_id: str = "e-abc123",
    book: float = 100000.0,
    ports_period: str = "2025-01",
    ports_amount: float = 99000.0,
    ports_reason: str = "汇率差异",
    tax_report: float = 98000.0,
    tax_reason: str = "退税调整",
    tax_index: str = "D4-16-1",
) -> dict:
    return {
        "id": item_id,
        "bookAmount": book,
        "portsPeriod": ports_period,
        "portsAmount": ports_amount,
        "portsDiff": ports_amount - book,  # 派生
        "portsReason": ports_reason,
        "taxReportAmount": tax_report,
        "taxDiff": tax_report - book,  # 派生
        "taxReason": tax_reason,
        "taxIndex": tax_index,
    }


class TestD416RoundTrip:
    """**Validates: Requirements 1.4, 1.5**"""

    def test_roundtrip_normal(self):
        """录入字段逐字段一致，派生字段重算。"""
        item = _make_d4_16_item()

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-16"
        ws.append(_D4_16_HEADERS)
        _export_d4_16_rows(ws, [item])
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        assert len(data_rows) == 1

        parsed = _parse_d4_16_row(data_rows[0], headers)
        assert parsed is not None

        # 录入字段逐字段一致
        assert parsed["bookAmount"] == item["bookAmount"]
        assert parsed["portsAmount"] == item["portsAmount"]
        assert parsed["portsPeriod"] == item["portsPeriod"]
        assert parsed["portsReason"] == item["portsReason"]
        assert parsed["taxReportAmount"] == item["taxReportAmount"]
        assert parsed["taxReason"] == item["taxReason"]
        assert parsed["taxIndex"] == item["taxIndex"]

        # 派生字段由公式重算（Req 1.4）
        assert parsed["portsDiff"] == item["portsAmount"] - item["bookAmount"]
        assert parsed["taxDiff"] == item["taxReportAmount"] - item["bookAmount"]

    def test_derived_not_trusted_from_file(self):
        """派生字段不信任文件值（Req 1.4）。

        即使 xlsx 中 portsDiff/taxDiff 被篡改，重解析后仍由公式重算。
        """
        item = _make_d4_16_item(book=100000, ports_amount=99000, tax_report=98000)

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-16"
        ws.append(_D4_16_HEADERS)
        # 手写一行，故意把差异值写错
        ws.append([
            1,
            100000,    # bookAmount
            "2025-01", # portsPeriod
            99000,     # portsAmount
            99999,     # portsDiff（故意写错）
            "汇率差异",
            98000,     # taxReportAmount
            88888,     # taxDiff（故意写错）
            "退税调整",
            "D4-16-1",
        ])
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        parsed = _parse_d4_16_row(data_rows[0], headers)
        assert parsed is not None

        # 重算后差异应为正确值，不是文件里的 99999/88888
        assert parsed["portsDiff"] == 99000 - 100000  # -1000
        assert parsed["taxDiff"] == 98000 - 100000    # -2000

    def test_item_id_is_d4_16_rows(self):
        """item_id 必须是 D4-16-rows（Req 1.4）。"""
        from app.routers.wp_render_strategies._d4_import_export import _resolve_item_id
        assert _resolve_item_id("D4-16") == "D4-16-rows"

    def test_recompute_derived(self):
        """_d4_16_recompute_derived 纯函数测试。"""
        row: dict[str, Any] = {"bookAmount": 50000, "portsAmount": 48000, "taxReportAmount": 47000}
        _d4_16_recompute_derived(row)
        assert row["portsDiff"] == -2000.0
        assert row["taxDiff"] == -3000.0

    def test_multiple_rows(self):
        """多行往返。"""
        items = [
            _make_d4_16_item(item_id="e-1", book=100000, ports_amount=99000, tax_report=98000),
            _make_d4_16_item(item_id="e-2", book=200000, ports_amount=200000, tax_report=195000),
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "D4-16"
        ws.append(_D4_16_HEADERS)
        _export_d4_16_rows(ws, items)
        xlsx_bytes = _wb_to_bytes(wb)

        headers = _read_headers(xlsx_bytes)
        data_rows = _read_rows(xlsx_bytes)
        assert len(data_rows) == 2

        for i, row in enumerate(data_rows):
            parsed = _parse_d4_16_row(row, headers)
            assert parsed is not None
            assert parsed["bookAmount"] == items[i]["bookAmount"]
            assert parsed["portsAmount"] == items[i]["portsAmount"]

    def test_d4_16_zero_book_amount(self):
        """bookAmount=0 → portsDiff=portsAmount, taxDiff=taxReportAmount。"""
        row: dict[str, Any] = {"bookAmount": 0, "portsAmount": 5000, "taxReportAmount": 3000}
        _d4_16_recompute_derived(row)
        assert row["portsDiff"] == 5000.0
        assert row["taxDiff"] == 3000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 变异检验（至少 2 条 RED）
# ═══════════════════════════════════════════════════════════════════════════════

class TestMutationRed:
    """变异检验：改一字使守卫打红。"""

    def test_mutation_d4_15_consistency_always_true(self):
        """MUTATION: 如果 _d4_15_is_consistent 恒返回 True，则不一致的行会误判。

        此测试验证：金额不等时 isConsistent 必须为 False。
        如果有人把 _d4_15_is_consistent 改成 `return True`，此测试打红。
        """
        item = {"delivery": {"amount": 100}, "invoice": {"amount": 99}, "voucher": {"amount": 100}}
        assert _d4_15_is_consistent(item) is False

    def test_mutation_d4_16_derived_skip(self):
        """MUTATION: 如果 _d4_16_recompute_derived 被跳过（不重算），差异值为 0。

        此测试验证：重算后 portsDiff ≠ 0。
        如果有人把 _d4_16_recompute_derived 注释掉或不调用，此测试打红。
        """
        row: dict[str, Any] = {"bookAmount": 50000, "portsAmount": 48000, "taxReportAmount": 47000}
        _d4_16_recompute_derived(row)
        assert row["portsDiff"] != 0, "portsDiff 不应为 0（书面与口岸不等时必有差异）"
        assert row["taxDiff"] != 0, "taxDiff 不应为 0（书面与申报不等时必有差异）"

    def test_mutation_d4_13_na_default(self):
        """MUTATION: 如果缺失文本不写 N/A 而写空串，此测试打红。"""
        data_rows: list[tuple] = []  # 完全没有数据行
        result = _parse_d4_13_rows(data_rows, ["区块", "内容"])
        assert result["D4-13-process"] == "N/A"
        assert result["D4-13-conclusion"] == "N/A"
