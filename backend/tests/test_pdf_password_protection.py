"""PDF 密码保护（TODO 15.5）守卫。

钉住四条行为判据（不是源码文本）：

1. 带密码导出 ⇒ 产物用正确密码能打开、错误密码被拒（pypdf 真实验证）；
   任务标 ``password_protected=True``。
2. 无密码导出 ⇒ 产物无加密、任务 ``password_protected=False``（行为不变）。
3. 加密失败 ⇒ 文件删除、任务不上抛错配（不产出未加密文件标已加密）。
4. 多文档合并 + 密码 ⇒ 合并产物整体加密。
5. 明文密码不落库（``export_tasks`` 无密码列是有意设计）。

Requirements: 7.5、TODO 15.5
"""
from __future__ import annotations

import io
from uuid import UUID

import pytest

import app.services.pdf_export_engine as engine_mod

mod = engine_mod
from app.models.report_models import ExportTaskStatus

PROJECT_ID = UUID("bbbbbbbb-0000-0000-0000-000000000002")
TASK_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
PASSWORD = "cv-secret-123"


def _make_task(**overrides):
    class _Task:
        id = TASK_ID
        project_id = PROJECT_ID
        document_type = "balance_sheet"
        document_types = ["balance_sheet"]
        export_year = 2025
        unit_policy_snapshot = {"unit": "yuan", "divisor": 1, "_digest": "a" * 64}
        password_protected = False
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


class _Result:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _EngineDb:
    def __init__(self, value) -> None:
        self._value = value
        self.flushes = 0

    async def execute(self, _stmt):
        return _Result(self._value)

    async def flush(self):
        self.flushes += 1


def _wire(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine_mod, "EXPORT_DIR", tmp_path)

    async def _fake_dispatcher(_db, **_kw):
        return ("balance_sheet", {"report_type": "balance_sheet", "unit_label": "元",
                                  "sections": [{"report_type": "balance_sheet",
                                                "rows": [{"row_name": "货币资金",
                                                          "current_period_amount": 100,
                                                          "prior_period_amount": 80,
                                                          "is_total": False,
                                                          "indent_level": 0}]}]})

    monkeypatch.setattr(engine_mod, "build_pdf_source_data", _fake_dispatcher)
    def _fake_convert(_html: str) -> bytes:
        # 产出一个**合法**最小 PDF（替身字节会让 pypdf 解析失败）
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    monkeypatch.setattr(
        engine_mod.PDFExportEngine, "_convert_html_to_pdf", staticmethod(_fake_convert)
    )


class TestPasswordProtection:
    @pytest.mark.asyncio
    async def test_password_encrypts_and_marks_task(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = mod.PDFExportEngine(_EngineDb(task))
        _wire(engine, monkeypatch, tmp_path)

        result = await engine.execute_export(TASK_ID, password=PASSWORD)
        assert result.status == ExportTaskStatus.completed
        assert result.password_protected is True
        pdf_path = tmp_path / "export_aaaaaaaa-0000-0000-0000-000000000001.pdf"
        assert pdf_path.exists()

        from pypdf import PdfReader
        # 正确密码能打开
        reader = PdfReader(str(pdf_path))
        assert reader.is_encrypted
        assert reader.decrypt(PASSWORD) != 0
        # 错误密码被拒（pypdf 6.x：decrypt 返回 0 = NOT_DECRYPTED，不抛）
        reader2 = PdfReader(str(pdf_path))
        assert reader2.decrypt("wrong-password") == 0

    @pytest.mark.asyncio
    async def test_no_password_keeps_plain_and_flag_false(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = mod.PDFExportEngine(_EngineDb(task))
        _wire(engine, monkeypatch, tmp_path)

        result = await engine.execute_export(TASK_ID)
        assert result.status == ExportTaskStatus.completed
        assert result.password_protected is False
        pdf_path = tmp_path / "export_aaaaaaaa-0000-0000-0000-000000000001.pdf"
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        assert not reader.is_encrypted

    @pytest.mark.asyncio
    async def test_encryption_failure_deletes_file_and_fails_task(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = mod.PDFExportEngine(_EngineDb(task))
        _wire(engine, monkeypatch, tmp_path)

        # 🔴 故障注在**内层**（pypdf 层），让真实 _encrypt_pdf_file 的
        # 「删除半成品」逻辑真的执行 —— 替换整个函数会让删除逻辑空转。
        # patch PdfReader 构造（_encrypt_pdf_file 的第一行）。
        import app.services.pdf_export_engine as eng

        real_reader = eng.PdfReader if hasattr(eng, "PdfReader") else None

        def _boom_reader(*_a, **_kw):
            raise RuntimeError("encryption boom")

        # _encrypt_pdf_file 函数内 import pypdf.PdfReader —— patch 源头模块
        import pypdf
        monkeypatch.setattr(pypdf, "PdfReader", _boom_reader)
        # 加密失败是**业务失败**（非环境问题）：被 execute_export 的通用
        # except 捕获 → 任务标 failed 返回（不抛 5xx），但**绝不能**产出
        # 「未加密文件 + password_protected=True」的错配。
        result = await engine.execute_export(TASK_ID, password=PASSWORD)
        assert result.status == ExportTaskStatus.failed
        assert "encryption boom" in (result.error_message or "")
        # 半成品被删除
        assert not (tmp_path / "export_aaaaaaaa-0000-0000-0000-000000000001.pdf").exists()
        # 任务不得标已加密（错配比不加密更危险）
        assert task.password_protected is False

    @pytest.mark.asyncio
    async def test_multi_doc_with_password_encrypted(self, tmp_path, monkeypatch):
        task = _make_task(document_types=["balance_sheet", "audit_report"])
        engine = mod.PDFExportEngine(_EngineDb(task))
        monkeypatch.setattr(engine_mod, "EXPORT_DIR", tmp_path)

        async def _fake_dispatcher(_db, **_kw):
            return [
                ("audit_report", {"paragraphs": {"审计意见段": "我们审计了……"}}),
                ("balance_sheet", {"report_type": "balance_sheet", "rows": []}),
            ]

        monkeypatch.setattr(engine_mod, "build_pdf_source_data", _fake_dispatcher)
        def _fake_convert_block(_html: str) -> bytes:
            from pypdf import PdfWriter

            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        monkeypatch.setattr(
            engine_mod.PDFExportEngine, "_convert_html_to_pdf",
            staticmethod(_fake_convert_block),
        )
        result = await engine.execute_export(TASK_ID, password=PASSWORD)
        assert result.password_protected is True
        pdf_path = tmp_path / "export_aaaaaaaa-0000-0000-0000-000000000001.pdf"
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        assert reader.is_encrypted
        assert reader.decrypt(PASSWORD) != 0

    def test_password_never_persisted_to_model(self):
        """``ExportTask`` 无密码列 —— 明文凭据不入审计链（有意设计）。"""
        from app.models.report_models import ExportTask

        column_names = {c.name for c in ExportTask.__table__.columns}
        password_like = [c for c in column_names if "password" in c.lower()]
        assert password_like == ["password_protected"], (
            f"export_tasks 出现了疑似明文密码列：{password_like}"
        )

    def test_router_passes_password_to_engine(self):
        """路由必须把 DTO 的 password 传给引擎（AST 判，防断链）。"""
        import ast
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "app/routers/export.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        create = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_export_task":
                create = node
                break
        assert create is not None
        body = ast.unparse(create)
        assert "password=data.password" in body, "路由没有把密码传给 execute_export"
