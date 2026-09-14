"""财务报表 POC 校验冒烟."""

from pathlib import Path

from scripts.validate_financial_template import validate


def test_soe_standalone_financial_poc():
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "data/audit_report_templates/financial_statements/soe_standalone.xlsx"
    )
    assert validate(path) == []


def test_cell_mapping_poc_exists():
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "data/audit_report_templates/cell_mapping.json"
    )
    assert path.is_file()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    variant = data["variants"]["soe_standalone"]
    assert len(variant["rows"]) >= 20
