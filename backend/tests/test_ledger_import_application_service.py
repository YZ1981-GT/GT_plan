"""LedgerImportApplicationService 单元测试

覆盖导入预览/结果协议的统一字段构造。
"""

from app.services.ledger_import_application_service import LedgerImportApplicationService


def test_build_account_chart_result_payload_includes_validation():
    result = {
        "total_accounts": 12,
        "by_category": {"asset": 8, "liability": 4},
        "errors": [],
        "data_sheets_imported": {"tb_balance": 20},
        "year": 2024,
        "sheet_diagnostics": [
            {
                "file": "trial-balance.xlsx",
                "sheet": "余额表",
                "data_type": "balance",
                "missing_cols": ["期末余额"],
                "missing_recommended": ["借方发生额"],
                "row_count": 20,
                "status": "ok",
                "message": None,
            }
        ],
    }

    payload = LedgerImportApplicationService.build_account_chart_result_payload(result)

    assert payload["total_imported"] == 12
    assert payload["year"] == 2024
    assert payload["sheet_diagnostics"][0]["sheet_name"] == "余额表"
    assert payload["validation"][0]["rule_code"] == "missing_required_columns"
    assert payload["validation"][0]["severity"] == "error"
    assert payload["validation"][0]["blocking"] is True
    assert payload["validation"][1]["rule_code"] == "missing_recommended_columns"
    assert payload["validation"][1]["severity"] == "warning"


def test_build_account_chart_failure_payload_includes_fatal_validation():
    payload = LedgerImportApplicationService.build_account_chart_failure_payload("boom")

    assert payload["total_imported"] == 0
    assert payload["errors"] == ["导入失败: boom"]
    assert len(payload["validation"]) == 1
    assert payload["validation"][0]["rule_code"] == "import_failed"
    assert payload["validation"][0]["severity"] == "fatal"
    assert payload["validation"][0]["blocking"] is True


def test_build_ledger_job_result_payload_includes_validation():
    result = {
        "data_sheets_imported": {"tb_ledger": 18},
        "year": 2025,
        "errors": [],
        "sheet_diagnostics": [
            {
                "file": "ledger.xlsx",
                "sheet": "序时账",
                "data_type": "ledger",
                "missing_cols": [],
                "missing_recommended": ["摘要"],
                "row_count": 18,
                "status": "ok",
                "message": None,
            }
        ],
    }

    payload = LedgerImportApplicationService.build_ledger_job_result_payload(result, job_batch_id=None)

    assert payload["imported"] == {"tb_ledger": 18}
    assert payload["year"] == 2025
    assert payload["diagnostics"][0]["sheet_name"] == "序时账"
    assert payload["validation"][0]["rule_code"] == "missing_recommended_columns"
    assert payload["validation"][0]["severity"] == "warning"
