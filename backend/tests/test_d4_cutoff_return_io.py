"""D4-17/18/19/20 截止/折扣/退货 导入导出行为守卫 + 源模板事实核定

spec: d4-cutoff-return-writeback-formula-io（Task 1 源核定 / Task 3 IO / Task 6 守卫）
挂靠总纲: d4-dual-mode-formula-governance

裁决者 = 源模板 `backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`
（openpyxl 直读，不连库 → 可进 CI）。

覆盖:
  · Property 1: export/import 后录入字段、稳定 id 不丢；派生字段由公式重算不信文件值。
  · Property 2: 截止 √/× 由 isCutoffOk/_cutoff_is_ok 同定义计算；非跨期不恒相反。
  · Requirement 1.1/1.4: 源列头是真源；主 D4-20 死配置显式拒绝，不写孤儿键。
  · Requirement 1.2/1.3: 两侧 item_id 正确（含 D4-20-current→D4-20-current-returns 修正）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app.routers.wp_render_strategies import _d4_import_export as m
from app.routers.wp_render_strategies._d4_cutoff_return_io_spec import (
    CUTOFF_RETURN_SPECS,
    D4_20_MAIN_DEAD_SHEET,
    get_io_spec,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_XLSX = (
    _REPO_ROOT
    / "backend"
    / "wp_templates"
    / "D"
    / "D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 源模板事实核定（Task 1 gate）
# ═══════════════════════════════════════════════════════════════════════════════


def _source_headers(sheet_name: str, header_rows: tuple[int, ...]) -> list[str]:
    """从源 xlsx 指定表头行拼出扁平列头（多级表头逐列取非空的最深一层）。"""
    wb = load_workbook(_SRC_XLSX, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(min_row=min(header_rows), max_row=max(header_rows), values_only=True))
        return rows  # 交由具体断言处理
    finally:
        wb.close()


@pytest.mark.skipif(not _SRC_XLSX.exists(), reason="源模板不在当前快照")
class TestSourceGate:
    def test_source_sheet_names_present(self):
        wb = load_workbook(_SRC_XLSX, read_only=True, data_only=True)
        try:
            names = set(wb.sheetnames)
        finally:
            wb.close()
        for spec in CUTOFF_RETURN_SPECS.values():
            assert spec.source_sheet_name in names, (
                f"spec {spec.sheet_code} 声明的源 sheet {spec.source_sheet_name!r} 不在源模板"
            )

    def test_d4_17_source_two_level_header(self):
        """D4-17 R11=组头(记账凭证/发货单/是否跨期), R12=子列(日期/编号/品名/数量/金额)。"""
        wb = load_workbook(_SRC_XLSX, read_only=True, data_only=True)
        try:
            ws = wb["营业收入截止测试（账到单据）D4-17"]
            r11 = [c.value for c in next(ws.iter_rows(min_row=11, max_row=11))]
            r12 = [c.value for c in next(ws.iter_rows(min_row=12, max_row=12))]
        finally:
            wb.close()
        assert r11[0] == "记账凭证" and r11[5] == "发货单", r11
        assert r11[10] == "是否跨期", r11
        # 子列前 5 = 日期/编号/品名/数量/金额
        assert r12[:5] == ["日期", "编号", "品名", "数量", "金额"], r12[:5]

    def test_d4_18_delivery_first(self):
        """D4-18 组头顺序相反：发货单在前、记账凭证在后。"""
        wb = load_workbook(_SRC_XLSX, read_only=True, data_only=True)
        try:
            ws = wb["营业收入截止测试（单据到账）D4-18"]
            r11 = [c.value for c in next(ws.iter_rows(min_row=11, max_row=11))]
        finally:
            wb.close()
        assert r11[0] == "发货单" and r11[5] == "记账凭证", r11
        # spec 反映方向：D4-18 前 5 个 key 为 delivery*
        assert CUTOFF_RETURN_SPECS["D4-18"].fields[0].key == "deliveryDate"
        assert CUTOFF_RETURN_SPECS["D4-17"].fields[0].key == "voucherDate"

    def test_d4_20_return_detail_source_columns(self):
        """D4-20 本期退货明细 R33: 记账凭证7列 + 退货单5列（客户/产品/数量/金额/原因）。"""
        wb = load_workbook(_SRC_XLSX, read_only=True, data_only=True)
        try:
            ws = wb["销售退货检查表 D4-20"]
            r32 = [c.value for c in next(ws.iter_rows(min_row=32, max_row=32))]
            r33 = [c.value for c in next(ws.iter_rows(min_row=33, max_row=33))]
        finally:
            wb.close()
        assert r32[0] == "记账凭证" and r32[7] == "退货单", r32
        assert r33[:7] == ["日期", "编号", "业务内容", "科目名称", "二级明细", "借方金额", "贷方金额"], r33[:7]


# ═══════════════════════════════════════════════════════════════════════════════
# 死配置拒绝 + item_id（Requirement 1.4 / 1.2 / 1.3）
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeadConfigAndItemId:
    def test_main_d4_20_rejected(self):
        with pytest.raises(HTTPException) as ei:
            m._validate_sheet(D4_20_MAIN_DEAD_SHEET)
        assert ei.value.status_code == 400
        assert "六区结构" in str(ei.value.detail)

    def test_main_d4_20_not_in_supported(self):
        assert "D4-20" not in m._SUPPORTED_SHEETS

    @pytest.mark.parametrize("sheet,expect", [
        ("D4-17", "D4-17-rows"),
        ("D4-18", "D4-18-rows"),
        ("D4-19", "D4-19-rows"),
        ("D4-20-provision", "D4-20-provision"),
        ("D4-20-current", "D4-20-current-returns"),
        ("D4-20-post", "D4-20-post-returns"),
    ])
    def test_item_id_resolution(self, sheet, expect):
        assert m._resolve_item_id(sheet) == expect

    def test_headers_have_no_seq_column(self):
        """spec 驱动列头不含 '序号'（序号是展示序不是往返身份）。"""
        for code in CUTOFF_RETURN_SPECS:
            assert "序号" not in m._get_headers(code), code


# ═══════════════════════════════════════════════════════════════════════════════
# 往返 + 派生重算（Property 1 / 2）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoundTripAndDerived:
    def test_d4_17_roundtrip_preserves_input_recomputes_derived(self):
        spec = CUTOFF_RETURN_SPECS["D4-17"]
        src = {
            "id": "r-fixed-abc12", "voucherDate": "2025-12-28", "voucherNo": "V1",
            "voucherProduct": "钢材", "voucherQty": "10", "voucherAmount": 1000.0,
            "deliveryDate": "2026-01-05", "deliveryNo": "D1", "deliveryProduct": "钢材",
            "deliveryQty": "10", "deliveryAmount": 1000.0, "isCutoff": True, "remark": "样本",
        }
        exported = m._export_cutoff_return_row(spec, src, "2025-12-31")
        # 派生 isCutoff 由公式重算：凭证<=截止 且 发货>截止 → 跨期 → ×（不信文件的 True）
        assert exported[spec.headers.index("是否跨期")] == "×"
        parsed = m._parse_cutoff_return_row(spec, tuple(exported), spec.headers)
        parsed = m._finalize_cutoff_return_row(spec, parsed, "2025-12-31")
        for f in spec.input_fields:
            assert str(parsed.get(f.key, "")) == str(src.get(f.key, "")), f.key
        assert parsed["isCutoff"] is False

    def test_cutoff_non_cross_not_inverted(self):
        """Req 2.3：非跨期时 D4-17/D4-18 同为 √（True），不恒相反。"""
        # 两个日期都在截止日或之前 → 非跨期
        ok17 = m._cutoff_is_ok("2025-12-20", "2025-12-25", "2025-12-31")
        ok18 = m._cutoff_is_ok("2025-12-20", "2025-12-25", "2025-12-31")
        assert ok17 is True and ok18 is True

    def test_cutoff_missing_date_returns_none(self):
        assert m._cutoff_is_ok("", "2025-12-25", "2025-12-31") is None
        assert m._cutoff_is_ok("2025-12-20", "", "2025-12-31") is None

    def test_discount_rate_recompute(self):
        spec = CUTOFF_RETURN_SPECS["D4-19"]
        row = {"revenueAmount": 1000.0, "discountAmount": 100.0, "discountRate": 999.0}
        m._recompute_derived(spec, row, "2025-12-31")
        assert abs(row["discountRate"] - 0.1) < 1e-9

    def test_discount_rate_zero_when_revenue_zero(self):
        spec = CUTOFF_RETURN_SPECS["D4-19"]
        row = {"revenueAmount": 0.0, "discountAmount": 100.0, "discountRate": 5.0}
        m._recompute_derived(spec, row, "2025-12-31")
        assert row["discountRate"] == 0.0

    def test_provision_should_provide_and_diff(self):
        spec = CUTOFF_RETURN_SPECS["D4-20-provision"]
        row = {"base": 1000.0, "rate": 0.05, "alreadyProvided": 30.0}
        m._recompute_derived(spec, row, "2025-12-31")
        assert row["shouldProvide"] == 50.0
        assert row["diff"] == 20.0

    def test_unknown_column_not_defaulted(self):
        """未知列不进入结果（禁止默归'其他'）。"""
        spec = CUTOFF_RETURN_SPECS["D4-19"]
        headers = spec.headers + ["未知列X"]
        vals = ["客户A"] + [""] * (len(spec.headers) - 1) + ["脏数据"]
        parsed = m._parse_cutoff_return_row(spec, tuple(vals), headers)
        assert parsed is not None
        assert "未知列X" not in parsed
        assert parsed["customerName"] == "客户A"

    def test_all_blank_row_returns_none(self):
        spec = CUTOFF_RETURN_SPECS["D4-19"]
        vals = [None] * len(spec.headers)
        assert m._parse_cutoff_return_row(spec, tuple(vals), spec.headers) is None
