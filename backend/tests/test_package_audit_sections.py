"""整包 ZIP 审计报告必须经共享正文口径（Word 模板 sections 主源）。

旧实现只读 ``paragraphs``：Word 模板模式项目的正文在
``report_body_json.sections`` ⇒ 组合包误判「无段落内容」整包失败，
而 PDF 数据源（同一项目）能正常导出 —— 双写漂移的真实形态。
本组用例真调 ``ExportPackageService.export_package``（include_audit_report=True）
钉住：sections-only 项目必须产出含正文段落的 docx；行为级（不是 AST 文本）。
"""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from uuid import UUID

import pytest

PROJECT_ID = UUID("11111111-2222-3333-4444-555555555555")
YEAR = 2025


class _FakeProject:
    id = PROJECT_ID
    name = "测试项目_2025"
    client_name = "测试客户"
    template_type = "soe"
    report_scope = "standalone"
    # get_company_short_name 等取项目字段的路径按需补齐；缺失属性用 None 兜底
    def __getattr__(self, item):
        return None


class _SectionsOnlyReport:
    """Word 模板模式：正文只在 report_body_json.sections，paragraphs 为空。"""

    report_body_json = {"sections": [
        {"section_id": "in", "section_name": "引言段", "section_order": 1,
         "content": "致：委托方"},
        {"section_id": "op", "section_name": "审计意见段", "section_order": 2,
         "content": "我们认为，后附财务报表在所有重大方面公允反映……"},
    ]}
    paragraphs = {}
    year = YEAR


class _FakeDb:
    """按查询次序返回 project → report；其余查询返回空。"""

    def __init__(self) -> None:
        self.execute_count = 0

    async def execute(self, _stmt):
        self.execute_count += 1

        class _R:
            def __init__(self, value) -> None:
                self._value = value

            def scalar_one_or_none(self):
                return self._value

            def first(self):
                return None

            def scalars(self):
                return self

            def all(self):
                return []

        # 1: Project；2: audit_report（include_audit_report=True 路径）
        if self.execute_count == 1:
            return _R(_FakeProject())
        if self.execute_count == 2:
            return _R(_SectionsOnlyReport())
        return _R(None)


class _OkGate:
    async def run_all_checks(self, _pid, _year):
        return SimpleNamespace(
            overall=True,
            has_blocking_failures=False,
            checks=[],
        )


def _gate_ok(monkeypatch):
    import app.services.consistency_gate as gate_mod

    monkeypatch.setattr(gate_mod, "ConsistencyGate", lambda db: _OkGate())
    monkeypatch.setattr(gate_mod, "gate_decision", lambda result, consumer: SimpleNamespace(blocks=False, summary="ok"))


class _OkExcelExporter:
    def __init__(self, db) -> None:
        pass

    async def export(self, **_kw):
        return io.BytesIO(b"PK\x03\x04fake-excel")


class _OkNoteExporter:
    def __init__(self, db) -> None:
        pass

    async def export(self, **_kw):
        return io.BytesIO(b"PK\x03\x04fake-docx")


class _OkPolicy:
    pass


@pytest.mark.anyio
async def test_sections_only_report_produces_real_docx(monkeypatch):
    """sections-only（Word 模板模式）项目 ⇒ 整包产出含正文段落的 docx。

    旧实现（只读 paragraphs）对这类项目抛「审计报告无段落内容」⇒ 整包失败；
    共享口径后与 PDF 数据源同口径，docx 里应有两段标题。
    """
    from app.services.export_package_service import ExportPackageService

    _gate_ok(monkeypatch)
    monkeypatch.setattr(
        "app.services.report_excel_exporter.ReportExcelExporter", _OkExcelExporter
    )
    monkeypatch.setattr(
        "app.services.note_word_exporter.NoteWordExporter", _OkNoteExporter
    )
    monkeypatch.setattr(
        "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
        _fake_snapshot,
    )

    service = ExportPackageService(_FakeDb())
    output = await service.export_package(
        PROJECT_ID, YEAR, include_audit_report=True
    )
    with zipfile.ZipFile(output) as zf:
        names = [n for n in zf.namelist() if n.endswith(".docx") and "审计报告" in n]
        assert names, f"zip 里没有审计报告 docx：{zf.namelist()}"
        # python-docx 读回验证正文来自 sections（不是空壳）
        from docx import Document

        doc = Document(io.BytesIO(zf.read(names[0])))
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert "引言段" in headings, headings
        assert "审计意见段" in headings, headings


@pytest.mark.anyio
async def test_sections_only_with_kam_items_included(monkeypatch):
    """sections 带 KAM items ⇒ docx 正文含 matter/response（与 render_docx 同口径）。"""
    from app.services.export_package_service import ExportPackageService

    _gate_ok(monkeypatch)
    monkeypatch.setattr(
        "app.services.report_excel_exporter.ReportExcelExporter", _OkExcelExporter
    )
    monkeypatch.setattr(
        "app.services.note_word_exporter.NoteWordExporter", _OkNoteExporter
    )
    monkeypatch.setattr(
        "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
        _fake_snapshot,
    )

    kam_report = SimpleNamespace(
        report_body_json={"sections": [
            {"section_id": "kam", "section_name": "关键审计事项段",
             "section_order": 1, "content": "",
             "items": [{"matter": "收入确认", "response": "执行函证"}]},
        ]},
        paragraphs={},
        year=YEAR,
    )

    class _Db(_FakeDb):
        async def execute(self, _stmt):
            self.execute_count += 1

            class _R:
                def __init__(self, value) -> None:
                    self._value = value

                def scalar_one_or_none(self):
                    return self._value

                def first(self):
                    return None

                def scalars(self):
                    return self

                def all(self):
                    return []

            if self.execute_count == 1:
                return _R(_FakeProject())
            if self.execute_count == 2:
                return _R(kam_report)
            return _R(None)

    service = ExportPackageService(_Db())
    output = await service.export_package(PROJECT_ID, YEAR, include_audit_report=True)
    with zipfile.ZipFile(output) as zf:
        names = [n for n in zf.namelist() if n.endswith(".docx") and "审计报告" in n]
        assert names
        from docx import Document

        doc = Document(io.BytesIO(zf.read(names[0])))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        assert "收入确认" in full_text
        assert "执行函证" in full_text


async def _fake_snapshot(db, *, project_id, year=None, regions=None):
    return '{"unit":"yuan","divisor":1,"_digest":"' + "a" * 64 + '"}'
