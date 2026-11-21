"""多文档合并（TODO 15.4）守卫。

前端 PDFExportPanel 允许勾选多文档（task_type=full_archive），旧分派器一律
409「尚未实现」。本批接通合并链并钉住三类行为判据：

1. 分派器：多文档按固定顺序返回 ``[(renderer_type, data), ...]``（audit_report
   → 四张报表枚举序 → disclosure_notes）；任一源失败整体 409/422，不静默丢一类；
   未知类型先报。
2. 引擎：多文档逐块渲染 PDF 后 pypdf 合并；任一块输出非 PDF / 转换不可用 →
   整体失败，不产出半份产物；单文档路径行为不变（返回 tuple 而非 list）。
3. 真实栈：多选导出产出合并 PDF。

Requirements: AC-20、AC-22、TODO 15.4
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

import app.services.pdf_export_engine as engine_mod
import app.services.pdf_export_sources as src_mod
from app.services.pdf_export_sources import (
    PDFSourceUnavailable,
    build_pdf_source_data,
)

PROJECT_ID = UUID("11111111-2222-3333-4444-555555555555")
YEAR = 2025
_SNAPSHOT = {"unit": "yuan", "divisor": 1, "_digest": "a" * 64}


# ---------------------------------------------------------------------------
# 替身
# ---------------------------------------------------------------------------


class _FakeRowsDb:
    async def execute(self, _stmt):
        class _Result:
            def scalars(self):
                return self

            def all(self):
                return [
                    SimpleNamespace(
                        row_code="BS-001", row_name="货币资金",
                        current_period_amount=100, prior_period_amount=80,
                        is_total_row=False, indent_level=0,
                    )
                ]

        return _Result()


class _FakeAuditReport:
    def __init__(self, *, body, paragraphs, status="final") -> None:
        self.report_body_json = body
        self.paragraphs = paragraphs
        self.status = SimpleNamespace(value=status)


class _FakeAuditSvcDb:
    def __init__(self, report) -> None:
        self._report = report

    async def execute(self, _stmt):
        class _Result:
            def scalar_one_or_none(self):
                return self._report

        _Result._report = self._report
        return _Result()


class _FakeProjectDb:
    """替身：Project 查询返回脚本化项目；financial/附注表查询返回空行集。

    空行集让 financial builder 走「没有可导出的正式数据」409 —— 供
    「任一源失败整体失败」用例复用；audit/notes 走注入替身，不依赖本替身。
    """

    def __init__(self, *, report_scope="standalone", rows_for_other=()) -> None:
        self._project = SimpleNamespace(template_type="soe", report_scope=report_scope)
        self._rows_for_other = list(rows_for_other)

    async def execute(self, stmt):
        text = str(stmt)
        if "disclosure_notes" in text or "consol_note" in text:
            raise AssertionError("附注源不得自己查附注表")
        if "financial_report" in text:
            class _R:
                def scalars(self):
                    return self

                def all(self):
                    return list(self._rows_for_other)
            _R._rows_for_other = self._rows_for_other
            return _R()
        class _P:
            def scalar_one_or_none(self):
                return self._project
        _P._project = self._project
        return _P()


class _FakeNoteExporter:
    def __init__(self, notes) -> None:
        self._notes = notes

    async def _load_export_notes(self, project_id, year, *, template_type, report_scope):
        return list(self._notes)

    def _note_tables(self, note):
        tables = note.table_data
        if isinstance(tables, dict) and isinstance(tables.get("_tables"), list):
            return list(tables["_tables"])
        return [tables] if isinstance(tables, dict) else []


def _make_note(section, title, tables, text=None):
    return SimpleNamespace(
        note_section=section, section_title=title,
        table_data=tables[0] if len(tables) == 1 else {"_tables": tables},
        text_content=text, is_deleted=False, sort_order=1, source_template="soe",
    )


@contextmanager
def _patched_sources(*, report=None, notes=None):
    """临时替换 audit/note 两个接缝（逐字节还原）。"""
    original_audit = src_mod._new_audit_service
    original_note = src_mod._new_note_exporter
    if report is not None:
        async def _get_report(_pid, _year):
            return report

        svc = SimpleNamespace(get_report=_get_report)
        src_mod._new_audit_service = lambda db: svc
    if notes is not None:
        src_mod._new_note_exporter = lambda db: _FakeNoteExporter(notes)
    try:
        yield
    finally:
        src_mod._new_audit_service = original_audit
        src_mod._new_note_exporter = original_note


_AUDIT_OK = _FakeAuditReport(
    body={"sections": [{"section_id": "x", "section_name": "审计意见段",
                        "section_order": 1, "content": "我们审计了……"}]},
    paragraphs=None,
)
_NOTE_OK = _make_note("五、1", "货币资金",
                      [{"headers": ["项目", "金额"],
                        "rows": [{"label": "库存现金", "values": [100], "is_total": False}]}],
                      text="附注正文。")


# ---------------------------------------------------------------------------
# 分派器
# ---------------------------------------------------------------------------


class TestDispatcherMultiDoc:
    @pytest.mark.asyncio
    async def test_multi_doc_returns_ordered_parts(self):
        """顺序固定：audit_report → 报表枚举序 → disclosure_notes（与勾选顺序无关）。"""
        row = SimpleNamespace(
            row_code="BS-001", row_name="货币资金",
            current_period_amount=100, prior_period_amount=80,
            is_total_row=False, indent_level=0,
        )
        with _patched_sources(report=_AUDIT_OK, notes=[_NOTE_OK]):
            parts = await build_pdf_source_data(
                _FakeProjectDb(rows_for_other=[row, row]),
                project_id=PROJECT_ID, year=YEAR,
                document_types=["disclosure_notes", "equity_statement",
                                "audit_report", "balance_sheet"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert isinstance(parts, list)
        assert [r for r, _ in parts] == [
            "audit_report", "balance_sheet", "equity_statement", "disclosure_notes",
        ]

    @pytest.mark.asyncio
    async def test_multi_doc_failure_of_one_part_fails_all(self):
        """任一源失败整体 409 —— 不静默丢一类。"""
        from decimal import Decimal

        with pytest.raises(PDFSourceUnavailable) as excinfo:
            with _patched_sources(report=_AUDIT_OK, notes=[_NOTE_OK]):
                await build_pdf_source_data(
                    # 财务 builder 用的 db 是同一个替身：_FakeProjectDb 不支持
                    # financial 查询 ⇒ 财务块抛错，整体失败
                    _FakeProjectDb(), project_id=PROJECT_ID, year=YEAR,
                    document_types=["audit_report", "balance_sheet"],
                    unit_policy_snapshot=_SNAPSHOT,
                )
        assert excinfo.value.status_code == 409

    @pytest.mark.asyncio
    async def test_multi_doc_unknown_type_reported_upfront(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_pdf_source_data(
                _FakeProjectDb(), project_id=PROJECT_ID, year=YEAR,
                document_types=["audit_report", "mystery_doc"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert excinfo.value.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_types_deduplicated_to_single(self):
        """重复类型去重后是单文档 ⇒ 返回 tuple（既有契约）。"""
        with _patched_sources(report=_AUDIT_OK):
            result = await build_pdf_source_data(
                _FakeAuditSvcDb(None), project_id=PROJECT_ID, year=YEAR,
                document_types=["audit_report", "audit_report"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert isinstance(result, tuple)
        assert result[0] == "audit_report"

    @pytest.mark.asyncio
    async def test_multi_doc_audit_plus_notes(self):
        """audit + notes 两类（无财务）也按固定顺序返回两块。"""
        with _patched_sources(report=_AUDIT_OK, notes=[_NOTE_OK]):
            parts = await build_pdf_source_data(
                _FakeProjectDb(), project_id=PROJECT_ID, year=YEAR,
                document_types=["disclosure_notes", "audit_report"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert isinstance(parts, list)
        assert [r for r, _ in parts] == ["audit_report", "disclosure_notes"]

    @pytest.mark.asyncio
    async def test_single_doc_returns_tuple_not_list(self):
        """单文档契约不变：返回 (renderer_type, data)，既有调用方零改动。"""
        with _patched_sources(report=_AUDIT_OK):
            result = await build_pdf_source_data(
                _FakeAuditSvcDb(None), project_id=PROJECT_ID, year=YEAR,
                document_types=["audit_report"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert isinstance(result, tuple)
        assert result[0] == "audit_report"


# ---------------------------------------------------------------------------
# 引擎合并
# ---------------------------------------------------------------------------


def _make_task(**overrides):
    class _Task:
        id = UUID("aaaaaaaa-0000-0000-0000-000000000001")
        project_id = UUID("bbbbbbbb-0000-0000-0000-000000000002")
        document_type = None
        document_types = ["audit_report", "balance_sheet"]
        export_year = 2025
        unit_policy_snapshot = dict(_SNAPSHOT)
        status = engine_mod.ExportTaskStatus.queued
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


class TestEngineMultiDoc:
    @pytest.mark.asyncio
    async def test_multi_doc_produces_merged_pdf(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = engine_mod.PDFExportEngine(_EngineDb(task))
        monkeypatch.setattr(engine_mod, "EXPORT_DIR", tmp_path)

        async def _fake_dispatcher(_db, **_kw):
            return [
                ("audit_report", {"paragraphs": {"审计意见段": "我们审计了……"}}),
                ("balance_sheet", {"report_type": "balance_sheet", "unit_label": "元",
                                   "sections": [{"report_type": "balance_sheet",
                                                 "rows": [{"row_name": "货币资金",
                                                           "current_period_amount": 100,
                                                           "prior_period_amount": 80,
                                                           "is_total": False,
                                                           "indent_level": 0}]}]}),
            ]

        monkeypatch.setattr(engine_mod, "build_pdf_source_data", _fake_dispatcher)
        real_convert = engine_mod.PDFExportEngine._convert_html_to_pdf
        calls = {"n": 0}

        def _fake_convert(html_content):
            # 每块产出带序号的可区分 PDF（真 pypdf 合并后可验证块数）
            calls["n"] += 1
            return real_convert(f"<html><body><h1>BLOCK{calls['n']}</h1>{html_content}</body></html>")

        monkeypatch.setattr(
            engine_mod.PDFExportEngine, "_convert_html_to_pdf",
            staticmethod(_fake_convert),
        )

        result = await engine.execute_export(task.id)
        assert result.status == engine_mod.ExportTaskStatus.completed
        assert calls["n"] == 2
        pdf_path = tmp_path / "export_aaaaaaaa-0000-0000-0000-000000000001.pdf"
        assert pdf_path.exists()
        assert pdf_path.read_bytes().startswith(b"%PDF")
        # 合并产物应包含两块的文本（pypdf 提取验证，防「只渲染一块」的静默丢一类）
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "".join(page.extract_text() or "" for page in reader.pages)
        assert "BLOCK1" in text and "BLOCK2" in text

    @pytest.mark.asyncio
    async def test_multi_doc_non_pdf_block_fails_all(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = engine_mod.PDFExportEngine(_EngineDb(task))
        monkeypatch.setattr(engine_mod, "EXPORT_DIR", tmp_path)

        async def _fake_dispatcher(_db, **_kw):
            return [("audit_report", {"paragraphs": {"x": "y"}}),
                    ("balance_sheet", {"report_type": "balance_sheet", "rows": []})]

        monkeypatch.setattr(engine_mod, "build_pdf_source_data", _fake_dispatcher)
        # 第二块返回非 PDF 内容 ⇒ 整体失败
        monkeypatch.setattr(
            engine_mod.PDFExportEngine, "_convert_html_to_pdf",
            staticmethod(lambda _html: b"NOT-A-PDF"),
        )
        with pytest.raises(engine_mod.PDFConversionUnavailable) as excinfo:
            await engine.execute_export(task.id)
        assert "不是 PDF" in str(excinfo.value)
        assert task.status == engine_mod.ExportTaskStatus.failed
        # 不产出半份产物
        assert task.file_path is None

    @pytest.mark.asyncio
    async def test_multi_doc_conversion_unavailable_fails_all(self, tmp_path, monkeypatch):
        task = _make_task()
        engine = engine_mod.PDFExportEngine(_EngineDb(task))
        monkeypatch.setattr(engine_mod, "EXPORT_DIR", tmp_path)

        async def _fake_dispatcher(_db, **_kw):
            return [("audit_report", {"paragraphs": {"x": "y"}}),
                    ("balance_sheet", {"report_type": "balance_sheet", "rows": []})]

        monkeypatch.setattr(engine_mod, "build_pdf_source_data", _fake_dispatcher)
        monkeypatch.setattr(
            engine_mod.PDFExportEngine, "_convert_html_to_pdf",
            staticmethod(lambda _html: None),
        )
        with pytest.raises(engine_mod.PDFConversionUnavailable) as excinfo:
            await engine.execute_export(task.id)
        assert "第 1 块" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_single_doc_path_unchanged(self, tmp_path, monkeypatch):
        """单文档任务仍走 render_document（tuple 路径），不进合并分支。"""
        task = _make_task(document_types=["balance_sheet"])
        engine = engine_mod.PDFExportEngine(_EngineDb(task))
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
        monkeypatch.setattr(
            engine_mod.PDFExportEngine, "_convert_html_to_pdf",
            staticmethod(lambda _html: b"%PDF-1.7\nsingle"),
        )
        result = await engine.execute_export(task.id)
        assert result.status == engine_mod.ExportTaskStatus.completed
        # 单文档不写临时 block 文件（合并目录不会出现）
        assert result.file_path and result.file_path.endswith(".pdf")
