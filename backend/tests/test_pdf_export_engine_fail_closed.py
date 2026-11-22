"""PDF 导出不得把 HTML 冒充 PDF 标 completed（AC-20 / AC-22）。

## 为什么需要这个守卫

`PDFExportEngine.render_document` 旧实现在 WeasyPrint 缺失时**写 HTML 文件并
返回该路径**，`execute_export` 照样把任务标 `completed`、`file_path` 指向
`.html`。用户点「导出 PDF」得到一个 HTML 文件、界面显示成功 ——
**报成功的失败比报失败更糟**（它让用户以为交付件已就绪）。

本守卫钉住三条行为判据（不是源码文本判据）：

1. 转换链可用 ⇒ 真的写出 `.pdf` 且内容以 `%PDF` 开头；
2. 转换链不可用 ⇒ 抛 `PDFConversionUnavailable`，**不写任何 `.html` 冒充**；
3. `execute_export` 遇到转换链不可用 ⇒ 任务标 `failed` 且**上抛**（路由据此 503）。

以及一条路由判据：policy 快照构造失败必须 422，不是静默放行。

Requirements: AC-20、AC-22、AC-26（未清遗留如实保留）
"""
from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _engine_module():
    from app.services import pdf_export_engine

    return pdf_export_engine


class TestRenderDocumentNeverFakesPdf:
    def test_unavailable_converter_raises_and_writes_nothing(self, tmp_path: Path, monkeypatch):
        """两条链都不可用 ⇒ 抛 PDFConversionUnavailable，目录里不得出现 .html。"""
        mod = _engine_module()
        engine = mod.PDFExportEngine(object())

        monkeypatch.setattr(
            mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(lambda _html: None)
        )
        with pytest.raises(mod.PDFConversionUnavailable) as excinfo:
            engine.render_document("financial_report", {"rows": []}, tmp_path / "out")
        assert "转换链不可用" in str(excinfo.value)
        leftovers = sorted(p.name for p in tmp_path.iterdir())
        assert leftovers == [], f"转换失败仍留下了文件：{leftovers}"

    def test_available_converter_writes_real_pdf(self, tmp_path: Path, monkeypatch):
        """转换链可用 ⇒ 写 .pdf 且内容是 PDF 魔数开头。"""
        mod = _engine_module()
        engine = mod.PDFExportEngine(object())
        monkeypatch.setattr(
            mod.PDFExportEngine,
            "_convert_html_to_pdf",
            staticmethod(lambda _html: b"%PDF-1.7\nfake\n"),
        )
        out = engine.render_document("financial_report", {"rows": []}, tmp_path / "out")
        assert out.suffix == ".pdf"
        assert out.exists()
        assert out.read_bytes().startswith(b"%PDF")

    def test_no_html_fallback_branch_in_source(self):
        """源码里不得再有「WeasyPrint 不可用就写 HTML」的降级分支（AST 判据）。"""
        src = (BACKEND / "app/services/pdf_export_engine.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        render_doc = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "render_document":
                render_doc = node
                break
        assert render_doc is not None, "找不到 render_document（夹具失锚）"
        # 🔴 必须剥掉 docstring 再判：函数自己的说明文字里就写着「`.html`」
        # 作为**缺陷描述**，纯文本 `not in` 会让说明文字把判据打红
        # （memory 铁律 ㉖ 正反两向都踩过 —— 这是第三次）。
        node = ast.parse(ast.unparse(render_doc)).body[0]
        assert isinstance(node, ast.FunctionDef)
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
        body = ast.unparse(node)
        assert ".html" not in body, f"render_document 仍有写 HTML 的降级分支：{body}"
        # 必须调用转换器并检查返回值
        assert "_convert_html_to_pdf" in body


class TestExecuteExportFailsClosed:
    @pytest.mark.asyncio
    async def test_conversion_unavailable_marks_failed_and_raises(self, tmp_path, monkeypatch):
        """转换链不可用 ⇒ 任务 failed + error_message + 上抛（路由据此 503）。"""
        mod = _engine_module()
        from app.models.report_models import ExportTask, ExportTaskStatus, ExportTaskType

        class _Task:
            id = UUID("aaaaaaaa-0000-0000-0000-000000000001")
            document_type = "financial_report"
            status = ExportTaskStatus.queued
            started_at = None
            completed_at = None
            progress_percentage = 0
            file_path = None
            file_size = None
            error_message = None

        task = _Task()

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

        db = _DB()
        engine = mod.PDFExportEngine(db)
        monkeypatch.setattr(mod, "EXPORT_DIR", tmp_path)
        monkeypatch.setattr(
            mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(lambda _html: None)
        )

        with pytest.raises(mod.PDFConversionUnavailable):
            await engine.execute_export(task.id)
        assert task.status == ExportTaskStatus.failed
        assert task.error_message and "转换链不可用" in task.error_message
        assert task.completed_at is not None
        # 不得把 HTML 路径写进 file_path
        assert task.file_path is None


class TestExportRouterGate:
    def test_policy_snapshot_failure_is_422_not_warning(self):
        """policy 快照构造失败必须 422（AST 判：except 分支里有 422 的 raise）。"""
        src = (BACKEND / "app/routers/export.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        create = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "create_export_task":
                create = node
                break
        assert create is not None, "找不到 create_export_task（夹具失锚）"
        body = ast.unparse(create)
        assert "422" in body, "policy 快照失败没有 422 分支"
        assert "logger.warning" not in body, "policy 快照失败仍只记 warning（静默放行）"

    def test_conversion_unavailable_maps_to_503(self):
        src = (BACKEND / "app/routers/export.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        assert "PDFConversionUnavailable" in names, "路由没有捕获 PDFConversionUnavailable"
        body = ast.unparse(tree)
        assert "503" in body, "转换链不可用没有映射到 503"
