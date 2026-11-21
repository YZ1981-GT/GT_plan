"""PDF 引擎必须消费真实数据来源，不能回退到空 rows 冒充成功。

`test_pdf_export_sources.py` 只测 resolver 本体；一个「engine 挂着 resolver 但从不
调用它」的变异在那一组里全绿（本轮实测第四个变异存活）。因此这里从 **engine 层**
钉住接线：带年度的任务必须调用 resolver 并把结果交给 renderer，resolver 报不可用
时任务标 failed 且上抛。
"""
from __future__ import annotations

from uuid import UUID

import pytest

import app.services.pdf_export_engine as mod
from app.models.report_models import ExportTaskStatus
from app.services.pdf_export_sources import PDFSourceUnavailable

PROJECT_ID = UUID("bbbbbbbb-0000-0000-0000-000000000002")
TASK_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _make_task(**overrides):
    class _Task:
        id = TASK_ID
        project_id = PROJECT_ID
        document_type = "balance_sheet"
        document_types = ["balance_sheet"]
        export_year = 2025
        unit_policy_snapshot = {"unit": "yuan", "divisor": 1, "_digest": "a" * 64}
        status = ExportTaskStatus.queued
        started_at = None
        completed_at = None
        progress_percentage = 0
        file_path = None
        file_size = None
        error_message = None

    task = _Task()
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


def _make_db(task):
    class _Result:
        def scalar_one_or_none(self):
            return task

    class _DB:
        def __init__(self):
            self.flushes = 0

        async def execute(self, _stmt):
            return _Result()

        async def flush(self):
            self.flushes += 1

    return _DB()


@pytest.mark.asyncio
async def test_engine_calls_source_resolver_with_task_year(tmp_path, monkeypatch):
    """带年度任务必须调 resolver，且把解析出的 rows 交给 renderer。"""
    task = _make_task()
    db = _make_db(task)
    engine = mod.PDFExportEngine(db)
    monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)

    calls: list[dict] = []

    async def _fake_resolver(_db, *, project_id, year, document_types, unit_policy_snapshot):
        calls.append(
            {
                "project_id": project_id,
                "year": year,
                "document_types": list(document_types),
                "snapshot": unit_policy_snapshot,
            }
        )
        return {
            "report_type": "balance_sheet",
            "unit_label": "元",
            "sections": [
                {
                    "report_type": "balance_sheet",
                    "rows": [
                        {
                            "row_code": "BS-001",
                            "row_name": "货币资金",
                            "current_period_amount": 100,
                            "prior_period_amount": 80,
                            "is_total": False,
                            "indent_level": 0,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(mod, "build_financial_pdf_data", _fake_resolver)
    monkeypatch.setattr(
        mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(lambda _html: b"%PDF-1.7\n")
    )

    result = await engine.execute_export(TASK_ID)
    assert result.status == ExportTaskStatus.completed
    assert calls and calls[0]["year"] == 2025
    assert calls[0]["document_types"] == ["balance_sheet"]
    assert calls[0]["snapshot"] == task.unit_policy_snapshot


@pytest.mark.asyncio
async def test_engine_renders_resolved_rows_not_empty_payload(tmp_path, monkeypatch):
    """渲染输入必须来自 resolver 的 rows；空 rows 冒充会让这条断言打红。"""
    task = _make_task()
    engine = mod.PDFExportEngine(_make_db(task))
    monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)
    captured: dict = {}

    async def _fake_resolver(*_a, **_kw):
        return {
            "report_type": "balance_sheet",
            "unit_label": "万元",
            "sections": [
                {
                    "report_type": "balance_sheet",
                    "rows": [
                        {
                            "row_code": "BS-001",
                            "row_name": "货币资金",
                            "current_period_amount": "0.04",
                            "prior_period_amount": "0.00",
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(mod, "build_financial_pdf_data", _fake_resolver)
    real_render = mod.PDFExportEngine.render_document

    def _spy_render(self, document_type, data, output_path):
        captured["document_type"] = document_type
        captured["data"] = data
        return real_render(self, document_type, data, output_path)

    monkeypatch.setattr(mod.PDFExportEngine, "render_document", _spy_render)
    monkeypatch.setattr(
        mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(lambda _html: b"%PDF-1.7\n")
    )

    await engine.execute_export(TASK_ID)
    sections = captured["data"]["sections"]
    assert sections and sections[0]["rows"][0]["row_code"] == "BS-001"
    assert captured["data"]["unit_label"] == "万元"


@pytest.mark.asyncio
async def test_engine_marks_failed_and_raises_when_source_unavailable(tmp_path, monkeypatch):
    """来源不可用 ⇒ 任务 failed 且上抛（路由据此 409/422），不产出空 PDF。"""
    task = _make_task()
    engine = mod.PDFExportEngine(_make_db(task))
    monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)

    async def _raise(*_a, **_kw):
        raise PDFSourceUnavailable("没有可导出的正式数据")

    monkeypatch.setattr(mod, "build_financial_pdf_data", _raise)
    monkeypatch.setattr(
        mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(lambda _html: b"%PDF-1.7\n")
    )

    with pytest.raises(PDFSourceUnavailable):
        await engine.execute_export(TASK_ID)
    assert task.status == ExportTaskStatus.failed
    assert task.error_message and "没有可导出的正式数据" in task.error_message
    # 不得留下任何产物路径
    assert task.file_path is None


class TestRouterRequiresYear:
    """正式端点缺年度必须 422；不得落到 engine 的空 rows 兼容分支。"""

    def test_router_rejects_missing_export_year(self):
        import ast
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "app/routers/export.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        create = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_export_task"
        )
        body = ast.unparse(create)
        assert "export_year is None" in body, "路由没有拒绝缺年度的正式请求"
        assert "422" in body, "缺年度没有映射到 422"
        assert "build_financial_pdf_data" not in body, "路由不应自己拼报表 SQL"
