"""LedgerImportApplicationService 单元测试
 
 覆盖导入预览/结果协议的统一字段构造。
 """
 
from uuid import uuid4
 
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
    assert payload["diagnostics"] == payload["sheet_diagnostics"]
    assert payload["validation"][0]["rule_code"] == "missing_required_columns"
    assert payload["validation"][0]["severity"] == "error"
    assert payload["validation"][0]["blocking"] is True
    assert payload["validation"][1]["rule_code"] == "missing_recommended_columns"
    assert payload["validation"][1]["severity"] == "warning"
    assert payload["validation_summary"]["total"] == 2
    assert payload["validation_summary"]["blocking_count"] == 1
    assert payload["validation_summary"]["has_blocking"] is True
    assert payload["validation_summary"]["by_severity"]["error"] == 1
    assert payload["validation_summary"]["by_severity"]["warning"] == 1


def test_build_account_chart_failure_payload_includes_fatal_validation():
    payload = LedgerImportApplicationService.build_account_chart_failure_payload("boom")

    assert payload["total_imported"] == 0
    assert payload["errors"] == ["导入失败: boom"]
    assert len(payload["validation"]) == 1
    assert payload["validation"][0]["rule_code"] == "import_failed"
    assert payload["validation"][0]["severity"] == "fatal"
    assert payload["validation"][0]["blocking"] is True
    assert payload["validation_summary"]["total"] == 1
    assert payload["validation_summary"]["blocking_count"] == 1
    assert payload["validation_summary"]["has_blocking"] is True
    assert payload["validation_summary"]["by_severity"]["fatal"] == 1


def test_build_account_chart_failure_payload_preserves_diagnostics():
    diagnostics = [
        {
            "file": "chart.xlsx",
            "sheet": "科目表",
            "data_type": "account_chart",
            "missing_cols": ["account_name"],
            "missing_recommended": [],
            "row_count": 0,
            "status": "error",
            "message": "科目表缺少必需列: 科目名称",
        }
    ]

    payload = LedgerImportApplicationService.build_account_chart_failure_payload(
        "科目表缺少必需列: 科目名称",
        diagnostics=diagnostics,
        errors=["chart.xlsx/科目表: 科目表缺少必需列: 科目名称"],
        year=2024,
    )

    assert payload["year"] == 2024
    assert payload["errors"] == ["chart.xlsx/科目表: 科目表缺少必需列: 科目名称"]
    assert payload["sheet_diagnostics"][0]["sheet_name"] == "科目表"
    assert payload["sheet_diagnostics"][0]["missing_cols"] == ["account_name"]
    assert payload["diagnostics"] == payload["sheet_diagnostics"]
    assert payload["validation"][0]["rule_code"] == "parse_error"
    assert payload["validation"][0]["message"] == "科目表缺少必需列: 科目名称"
    assert payload["validation_summary"]["total"] == 1
    assert payload["validation_summary"]["blocking_count"] == 1
    assert payload["validation_summary"]["has_blocking"] is True
    assert payload["validation_summary"]["by_severity"]["fatal"] == 1


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
    assert payload["diagnostics"] == payload["sheet_diagnostics"]
    assert payload["validation"][0]["rule_code"] == "missing_recommended_columns"
    assert payload["validation"][0]["severity"] == "warning"
    assert payload["validation_summary"]["total"] == 1
    assert payload["validation_summary"]["blocking_count"] == 0
    assert payload["validation_summary"]["has_blocking"] is False
    assert payload["validation_summary"]["by_severity"]["warning"] == 1


def test_build_ledger_failure_payload_preserves_diagnostics():
    diagnostics = [
        {
            "file": "ledger.csv",
            "sheet": "CSV",
            "data_type": "ledger",
            "missing_cols": ["account_code"],
            "missing_recommended": [],
            "row_count": 0,
            "status": "error",
            "message": "CSV 序时账缺少必需列: 科目编码",
        }
    ]

    payload = LedgerImportApplicationService.build_ledger_failure_payload(
        "CSV 序时账缺少必需列: 科目编码",
        job_batch_id=None,
        diagnostics=diagnostics,
        errors=["ledger.csv: CSV 序时账缺少必需列: 科目编码"],
        year=2024,
    )

    assert payload["year"] == 2024
    assert payload["errors"] == ["ledger.csv: CSV 序时账缺少必需列: 科目编码"]
    assert payload["diagnostics"][0]["sheet_name"] == "CSV"
    assert payload["diagnostics"][0]["missing_cols"] == ["account_code"]
    assert payload["diagnostics"] == payload["sheet_diagnostics"]
    assert payload["validation"][0]["rule_code"] == "parse_error"
    assert payload["validation"][0]["message"] == "CSV 序时账缺少必需列: 科目编码"
    assert payload["validation_summary"]["total"] == 1
    assert payload["validation_summary"]["blocking_count"] == 1
    assert payload["validation_summary"]["has_blocking"] is True
    assert payload["validation_summary"]["by_severity"]["fatal"] == 1


async def test_preview_includes_validation_summary(monkeypatch):
    async def _fake_resolve_file_sources(cls, **kwargs):
        return "upload-token", [("trial-balance.xlsx", b"fake")]

    monkeypatch.setattr(
        LedgerImportApplicationService,
        "resolve_file_sources",
        classmethod(_fake_resolve_file_sources),
    )
    monkeypatch.setattr(
        "app.services.ledger_import_application_service.smart_parse_files",
        lambda *args, **kwargs: {
            "year": 2024,
            "aux_dimensions": [],
            "diagnostics": [
                {
                    "file": "trial-balance.xlsx",
                    "sheet": "余额表",
                    "data_type": "balance",
                    "missing_cols": ["期末余额"],
                    "missing_recommended": ["借方发生额"],
                    "preview_rows_data": [{"科目编码": "1001"}],
                    "row_count": 12,
                    "total_row_estimate": 12,
                    "status": "ok",
                    "message": None,
                    "headers": ["科目编码"],
                    "column_mapping": {"科目编码": "account_code"},
                    "header_count": 1,
                    "header_start": 0,
                }
            ],
        },
    )

    payload = await LedgerImportApplicationService.preview(
        project_id=uuid4(),
        user_id="tester",
        files=[],
    )

    assert payload["validation_summary"]["total"] == 2
    assert payload["validation_summary"]["blocking_count"] == 1
    assert payload["validation_summary"]["has_blocking"] is True
    assert payload["validation_summary"]["by_severity"]["error"] == 1
    assert payload["validation_summary"]["by_severity"]["warning"] == 1
    assert payload["upload_token"] == "upload-token"
