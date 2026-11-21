"""审计报告与附注的正式 PDF 数据来源守卫。

钉住三类行为判据（不是源码文本）：

1. 审计报告：``report_body_json.sections`` 为主源（KAM items 合入、按
   ``section_order`` 排序、HTML 转义），旧 ``paragraphs`` 载体回退；两者都空
   409；draft/review 状态 409；报告不存在 409。
2. 附注：复用 NoteWordExporter 读取链后补软删/口径过滤，多表章节第 2+ 张表
   表名并入标题；全部为空 409。
3. 分派器：多类文档选择必须明确拒绝（不静默丢一类），未知类型 422。

Requirements: AC-20、AC-22
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from contextlib import contextmanager

from app.services.pdf_export_sources import (
    PDFSourceUnavailable,
    build_audit_report_pdf_data,
    build_disclosure_notes_pdf_data,
    build_pdf_source_data,
)

PROJECT_ID = UUID("11111111-2222-3333-4444-555555555555")
YEAR = 2025
_SNAPSHOT = {"unit": "yuan", "divisor": 1, "_digest": "a" * 64}


def _make_report(*, body: dict | None, paragraphs: dict | None, status: str = "final"):
    return SimpleNamespace(
        project_id=PROJECT_ID,
        year=YEAR,
        report_body_json=body,
        paragraphs=paragraphs,
        status=SimpleNamespace(value=status),
    )


class _FakeAuditSvcDb:
    """按 get_report 的查询口径返回脚本化报告。"""

    def __init__(self, report) -> None:
        self._report = report

    async def execute(self, _stmt):
        class _Result:
            def scalar_one_or_none(self):
                return self._report

        _Result._report = self._report
        return _Result()


# ---------------------------------------------------------------------------
# 审计报告
# ---------------------------------------------------------------------------


class TestAuditReportSource:
    @pytest.mark.asyncio
    async def test_sections_become_ordered_paragraphs_with_kam_items(self):
        body = {
            "sections": [
                {"section_id": "opinion", "section_name": "审计意见段",
                 "section_order": 2, "content": "我们审计了……"},
                {"section_id": "intro", "section_name": "引言段",
                 "section_order": 1, "content": "致：委托方"},
                {"section_id": "kam", "section_name": "关键审计事项段",
                 "section_order": 3, "content": "",
                 "items": [{"matter": "收入确认", "response": "执行函证"}]},
            ]
        }
        data = await build_audit_report_pdf_data(
            _FakeAuditSvcDb(_make_report(body=body, paragraphs=None)),
            project_id=PROJECT_ID,
            year=YEAR,
        )
        names = list(data["paragraphs"])
        # 按 section_order 排序，不按 dict 插入序
        assert names == ["引言段", "审计意见段", "关键审计事项段"]
        # KAM items 与 render_docx 同口径合入正文
        assert "收入确认" in data["paragraphs"]["关键审计事项段"]
        assert "执行函证" in data["paragraphs"]["关键审计事项段"]

    @pytest.mark.asyncio
    async def test_user_content_is_escaped(self):
        body = {"sections": [
            {"section_id": "x", "section_name": "段A", "section_order": 1,
             "content": "存货 <1年 & 应收"},
        ]}
        data = await build_audit_report_pdf_data(
            _FakeAuditSvcDb(_make_report(body=body, paragraphs=None)),
            project_id=PROJECT_ID,
            year=YEAR,
        )
        assert "<1年 & 应收" not in data["paragraphs"]["段A"]
        assert "&lt;1年 &amp; 应收" in data["paragraphs"]["段A"]

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_paragraphs(self):
        data = await build_audit_report_pdf_data(
            _FakeAuditSvcDb(_make_report(
                body=None, paragraphs={"审计意见段": "我们审计了……"}
            )),
            project_id=PROJECT_ID,
            year=YEAR,
        )
        assert data["paragraphs"]["审计意见段"] == "我们审计了……"

    @pytest.mark.asyncio
    async def test_empty_body_and_paragraphs_is_409(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_audit_report_pdf_data(
                _FakeAuditSvcDb(_make_report(body={"sections": []}, paragraphs={})),
                project_id=PROJECT_ID,
                year=YEAR,
            )
        assert excinfo.value.status_code == 409
        assert "没有正文内容" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_draft_status_is_rejected(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_audit_report_pdf_data(
                _FakeAuditSvcDb(_make_report(
                    body=None, paragraphs={"审计意见段": "x"}, status="draft"
                )),
                project_id=PROJECT_ID,
                year=YEAR,
            )
        assert excinfo.value.status_code == 409
        assert "draft" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_missing_report_is_409(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_audit_report_pdf_data(
                _FakeAuditSvcDb(None), project_id=PROJECT_ID, year=YEAR
            )
        assert excinfo.value.status_code == 409
        assert "尚未生成" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_missing_year_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_audit_report_pdf_data(
                _FakeAuditSvcDb(None), project_id=PROJECT_ID, year=None
            )
        assert excinfo.value.status_code == 422


# ---------------------------------------------------------------------------
# 附注
# ---------------------------------------------------------------------------


class _FakeNote:
    def __init__(self, *, section: str, title: str, tables: list, text: str | None = None,
                 is_deleted: bool = False, sort_order: int = 1):
        self.note_section = section
        self.section_title = title
        self.table_data = {"_tables": tables} if len(tables) > 1 else (tables[0] if tables else None)
        self.text_content = text
        self.is_deleted = is_deleted
        self.sort_order = sort_order
        self.source_template = "soe"


class _FakeNoteExporter:
    """替身 NoteWordExporter：脚本化 _load_export_notes / _note_tables。"""

    def __init__(self, notes: list[_FakeNote], *, scope="standalone", template="soe") -> None:
        self._notes = notes
        self.scope = scope
        self.template = template

    async def _load_export_notes(self, project_id, year, *, template_type, report_scope):
        assert template_type == self.template
        assert report_scope == self.scope
        return list(self._notes)

    def _note_tables(self, note):
        tables = note.table_data
        if isinstance(tables, dict) and isinstance(tables.get("_tables"), list):
            return [t for t in tables["_tables"] if t.get("export_enabled", True)]
        return [tables] if isinstance(tables, dict) else []


class _FakeProjectDb:
    """替身：Project 查询返回脚本化项目。

    附注读取**不走本替身** —— 生产代码在函数内构造 ``NoteWordExporter``，
    测试在模块命名空间注入替身 exporter；若生产代码绕开 exporter 直接查
    附注表，这里的防御断言立即打红（「复用正式读取链」是核心约束）。
    """

    def __init__(self, *, project=None) -> None:
        self._project = project or SimpleNamespace(
            template_type="soe", report_scope="standalone"
        )

    async def execute(self, stmt):
        text = str(stmt)
        if "disclosure_notes" in text or "consol_note" in text:
            raise AssertionError("附注源不应自己查附注表（必须委托 exporter）")
        class _P:
            def scalar_one_or_none(self):
                return self._project
        _P._project = self._project
        return _P()


class _FakeFinancialDb:
    """财务路径替身：返回空结果集（走「没有可导出的正式数据」判定）。"""

    async def execute(self, _stmt):
        class _Result:
            def scalars(self):
                return self

            def all(self):
                return []

        return _Result()


class TestDisclosureNotesSource:
    @pytest.mark.asyncio
    async def test_tables_and_text_become_notes_entries(self):
        note = _FakeNote(
            section="五、1", title="货币资金",
            tables=[{"headers": ["项目", "金额"],
                     "rows": [{"label": "库存现金", "values": [Decimal("100")],
                               "is_total": False}]}],
            text="主要为库存现金。",
        )
        with _with_exporter([note]) as db:
            data = await build_disclosure_notes_pdf_data(
                db, project_id=PROJECT_ID, year=YEAR, unit_policy_snapshot=_SNAPSHOT
            )
            assert data["unit_label"] == "元"
            assert len(data["notes"]) == 2  # 一张表 + 一段文字
            first = data["notes"][0]
            assert first["table_data"]["rows"][0]["values"] == [Decimal("100")]
            assert first["table_data"]["rows"][0]["is_total"] is False
            assert data["notes"][1]["text_content"] == "主要为库存现金。"
    @pytest.mark.asyncio
    async def test_multi_table_section_appends_table_name(self):
        note = _FakeNote(
            section="五、8", title="其他应收款",
            tables=[
                {"name": "按款项性质", "headers": ["项目"], "rows": []},
                {"name": "账龄分析", "headers": ["账龄"], "rows": []},
            ],
        )
        with _with_exporter([note]) as db:
            data = await build_disclosure_notes_pdf_data(
                db, project_id=PROJECT_ID, year=YEAR, unit_policy_snapshot=_SNAPSHOT
            )
            titles = [n["section_title"] for n in data["notes"]]
            assert titles[0] == "其他应收款"
            assert titles[1] == "其他应收款｜账龄分析"
    @pytest.mark.asyncio
    async def test_deleted_notes_are_filtered(self):
        note = _FakeNote(section="五、1", title="货币资金", tables=[], text="x", is_deleted=True)
        with _with_exporter([note]) as db:
            with pytest.raises(PDFSourceUnavailable) as excinfo:
                await build_disclosure_notes_pdf_data(
                    db, project_id=PROJECT_ID, year=YEAR, unit_policy_snapshot=_SNAPSHOT
                )
            assert excinfo.value.status_code == 409
    @pytest.mark.asyncio
    async def test_cell_dict_carrier_is_unpacked_and_scaled(self):
        note = _FakeNote(
            section="五、1", title="货币资金",
            tables=[{"headers": ["项目", "金额"],
                     "rows": [{"label": "库存现金",
                               "values": [{"value": Decimal("35000"), "manual_value": 1}],
                               "is_total": False}]}],
        )
        with _with_exporter([note]) as db:
            data = await build_disclosure_notes_pdf_data(
                db, project_id=PROJECT_ID, year=YEAR,
                unit_policy_snapshot={"unit": "wan", "divisor": 10000, "_digest": "b" * 64},
            )
            row = data["notes"][0]["table_data"]["rows"][0]
            assert row["values"] == [Decimal("3.50")]
            assert data["unit_label"] == "万元"
    @pytest.mark.asyncio
    async def test_formula_text_is_escaped_not_scaled(self):
        note = _FakeNote(
            section="五、1", title="货币资金",
            tables=[{"headers": ["项目", "备注"],
                     "rows": [{"label": "说明",
                               "values": ["<b>见底稿</b>"], "is_total": False}]}],
        )
        with _with_exporter([note]) as db:
            data = await build_disclosure_notes_pdf_data(
                db, project_id=PROJECT_ID, year=YEAR, unit_policy_snapshot=_SNAPSHOT
            )
            assert "&lt;b&gt;见底稿&lt;/b&gt;" in str(data["notes"][0]["table_data"]["rows"][0]["values"])
    @pytest.mark.asyncio
    async def test_no_notes_is_409(self):
        with _with_exporter([]) as db:
            with pytest.raises(PDFSourceUnavailable) as excinfo:
                await build_disclosure_notes_pdf_data(
                    db, project_id=PROJECT_ID, year=YEAR, unit_policy_snapshot=_SNAPSHOT
                )
            assert excinfo.value.status_code == 409
# ---------------------------------------------------------------------------
# 分派器
# ---------------------------------------------------------------------------


class TestDispatcher:
    @pytest.mark.asyncio
    async def test_multiple_document_kinds_are_rejected_not_dropped(self):
        """多选必须明确拒绝：静默丢一类会让任务 completed 但产物缺失。"""
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_pdf_source_data(
                _with_exporter([]),
                project_id=PROJECT_ID, year=YEAR,
                document_types=["audit_report", "balance_sheet"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert excinfo.value.status_code == 409
        assert "多文档合并尚未实现" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_unknown_type_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_pdf_source_data(
                _with_exporter([]),
                project_id=PROJECT_ID, year=YEAR,
                document_types=["mystery_doc"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert excinfo.value.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_year_is_422(self):
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_pdf_source_data(
                _with_exporter([]),
                project_id=PROJECT_ID, year=None,
                document_types=["balance_sheet"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert excinfo.value.status_code == 422

    @pytest.mark.asyncio
    async def test_financial_type_dispatches_to_financial_builder(self):
        """财务类型走财务构建器（替身返回空行集 ⇒ 落在「没有可导出的正式数据」）。"""
        with pytest.raises(PDFSourceUnavailable) as excinfo:
            await build_pdf_source_data(
                _FakeFinancialDb(),
                project_id=PROJECT_ID, year=YEAR,
                document_types=["balance_sheet"],
                unit_policy_snapshot=_SNAPSHOT,
            )
        assert "没有可导出的正式数据" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 测试注入：生产代码在函数内 import NoteWordExporter；替身经上下文管理器
# 临时替换模块符号（逐字节还原），保证「附注源必须委托正式读取链」。
# ---------------------------------------------------------------------------


@contextmanager
def _injected_exporter(exporter: _FakeNoteExporter):
    import app.services.pdf_export_sources as src_mod

    original = src_mod._new_note_exporter
    src_mod._new_note_exporter = lambda db: exporter
    try:
        yield
    finally:
        src_mod._new_note_exporter = original


class _InjectedSourceDb:
    """进入 with 时注入替身 exporter，退出时还原（逐字节）。"""

    def __init__(self, notes: list, *, project=None) -> None:
        self._notes = notes
        self._project_arg = project

    def __enter__(self):
        project = self._project_arg or SimpleNamespace(
            template_type="soe", report_scope="standalone"
        )
        self._ctx = _injected_exporter(_FakeNoteExporter(self._notes, scope=project.report_scope))
        self._ctx.__enter__()
        return _FakeProjectDb(project=project)

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)


def _with_exporter(notes: list, *, project=None) -> _InjectedSourceDb:
    return _InjectedSourceDb(notes, project=project)
