"""报告正文 POC 校验冒烟."""

from pathlib import Path

from scripts.validate_report_body_template import validate

POC = (
    Path(__file__).resolve().parent.parent.parent
    / "data/audit_report_templates/report_body/"
    "1.1 模板A-无保留意见审计报告模板（上市公司、三板创新层及公开发债）-简版.docx"
)


def test_report_body_poc_passes():
    issues = validate(POC)
    assert issues == [], issues
