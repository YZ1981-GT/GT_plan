"""ReportExcelExporter manifest 路径加载测试."""

from unittest.mock import MagicMock

from app.services.report_excel_exporter import ReportExcelExporter


def test_load_template_from_manifest():
    exporter = ReportExcelExporter(MagicMock())
    wb = exporter._load_template("soe_standalone")
    assert wb is not None
    assert any("资产负债表" in n for n in wb.sheetnames)


def test_resolve_sheet_balance_sheet():
    exporter = ReportExcelExporter(MagicMock())
    wb = exporter._load_template("soe_standalone")
    assert wb is not None
    ws = exporter._resolve_sheet(wb, "balance_sheet", "soe_standalone")
    assert ws is not None
    assert "资产负债表" in ws.title
