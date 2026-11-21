"""整包 ZIP 审计报告主源 + 归档 PDF 交付件条目守卫。

两类缺陷同源（v1.0.306~308 PDF 链接通后暴露）：

1. **整包 ZIP 的审计报告**（``ExportPackageService._build_audit_report_bytes``）
   只读旧 ``paragraphs`` 载体 —— Word 模板模式项目正文在
   ``report_body_json.sections``，会误判「无段落内容」整包失败。
   修复 = 经共享正文口径 ``extract_audit_report_paragraphs``（与 PDF 数据源同一份，
   防双写漂移）。
2. **归档清单不消费 PDF 交付件**（``archive_inventory`` 只收 Word 交付件）
   —— PDF 正式导出接通后，归档包缺一类正式件。修复 = 新增
   ``_pdf_deliverable_entries``（只收 completed、文件存在、大小一致、非 0 字节；
   evidence 绑定 task/年度/清单/policy 快照）。

Requirements: AC-20、AC-22
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.pdf_export_sources import extract_audit_report_paragraphs

PROJECT_ID = UUID("11111111-2222-3333-4444-555555555555")

def _inv_ok():
    from app.services.archive_inventory import OK

    return OK



# ---------------------------------------------------------------------------
# 共享正文口径
# ---------------------------------------------------------------------------


class TestExtractAuditReportParagraphs:
    def test_word_template_sections_take_priority(self):
        report = SimpleNamespace(
            report_body_json={"sections": [
                {"section_id": "op", "section_name": "审计意见段",
                 "section_order": 2, "content": "我们审计了……"},
                {"section_id": "in", "section_name": "引言段",
                 "section_order": 1, "content": "致：委托方"},
            ]},
            paragraphs={"旧载体段": "不应出现（sections 优先）"},
        )
        result = extract_audit_report_paragraphs(report)
        # sections 主源、按 section_order 排序；旧载体被忽略
        assert list(result) == ["引言段", "审计意见段"]
        assert "旧载体段" not in result

    def test_kam_items_merged_into_content(self):
        report = SimpleNamespace(
            report_body_json={"sections": [
                {"section_id": "kam", "section_name": "关键审计事项段",
                 "section_order": 1, "content": "",
                 "items": [{"matter": "收入确认", "response": "执行函证"}]},
            ]},
            paragraphs=None,
        )
        result = extract_audit_report_paragraphs(report)
        assert "收入确认" in result["关键审计事项段"]
        assert "执行函证" in result["关键审计事项段"]

    def test_falls_back_to_legacy_paragraphs(self):
        report = SimpleNamespace(
            report_body_json=None,
            paragraphs={"审计意见段": "我们审计了……"},
        )
        result = extract_audit_report_paragraphs(report)
        assert result == {"审计意见段": "我们审计了……"}

    def test_empty_both_returns_empty_dict(self):
        report = SimpleNamespace(report_body_json={"sections": []}, paragraphs={})
        assert extract_audit_report_paragraphs(report) == {}


# ---------------------------------------------------------------------------
# 整包 ZIP：审计报告用共享口径
# ---------------------------------------------------------------------------


class TestPackageAuditReportSource:
    def test_package_service_uses_shared_extractor(self):
        """整包必须经共享口径取正文（AST 判，防退回只读 paragraphs）。"""
        import ast
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "app/services/export_package_service.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        build = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_build_audit_report_bytes":
                build = node
                break
        assert build is not None, "找不到 _build_audit_report_bytes（夹具失锚）"
        body = ast.unparse(build)
        assert "extract_audit_report_paragraphs" in body, (
            "整包审计报告没有走共享正文口径（Word 模板模式项目会被误判无正文）"
        )

    def test_shared_extractor_keeps_docx_compatible_output(self):
        """共享口径输出仍是 {段名: 纯文本}（docx 路径不做 HTML 转义）。"""
        report = SimpleNamespace(
            report_body_json={"sections": [
                {"section_id": "x", "section_name": "段A", "section_order": 1,
                 "content": "存货 <1年"},
            ]},
            paragraphs=None,
        )
        result = extract_audit_report_paragraphs(report)
        # 不转义：docx.add_paragraph 直接吃纯文本
        assert result["段A"] == "存货 <1年"


# ---------------------------------------------------------------------------
# 归档 PDF 交付件条目
# ---------------------------------------------------------------------------


def _completed_task(**overrides):
    defaults = dict(
        id=UUID("cccccccc-0000-0000-0000-000000000001"),
        project_id=PROJECT_ID,
        export_year=2025,
        document_types=["balance_sheet"],
        document_type=None,
        status=SimpleNamespace(value="completed"),
        file_path="/storage/exports/x.pdf",
        file_size=1234,
        unit_policy_snapshot={"unit": "yuan", "divisor": 1, "_digest": "a" * 64},
        created_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeTaskDb:
    def __init__(self, tasks) -> None:
        self._tasks = tasks

    async def execute(self, _stmt):
        # 生产代码在 SQL 层过滤 status='completed'；替身按 status.value 复刻该过滤
        # （否则 failed 任务会混进来，用例测不到「只收 completed」这一判据）。
        rows = [t for t in self._tasks if getattr(getattr(t, "status", None), "value", None) == "completed"]
        class _Result:
            def scalars(self):
                return self

            def all(self):
                return list(rows)

        _Result._rows = rows
        return _Result()


class TestArchivePdfEntries:
    @pytest.mark.asyncio
    async def test_completed_task_binds_file_and_evidence(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import _ArcNames, _pdf_deliverable_entries
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-fake")
        task = _completed_task(file_path=str(pdf), file_size=pdf.stat().st_size)

        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file", lambda p: tmp_path / "x.pdf"
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([task]), PROJECT_ID, _ArcNames())
        assert len(entries) == 1
        entry = entries[0]
        assert entry.status == _inv_ok()
        assert entry.category == "pdf_deliverable"
        assert entry.evidence["task_id"] == str(task.id)
        assert entry.evidence["export_year"] == 2025
        assert entry.evidence["document_types"] == ["balance_sheet"]
        assert entry.evidence["policy_snapshot"]["unit"] == "yuan"
        assert entry.arcname.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_missing_file_is_missing_not_silent(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import MISSING, _ArcNames, _pdf_deliverable_entries
        task = _completed_task(file_path=str(tmp_path / "ghost.pdf"), file_size=100)
        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file", lambda p: None
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([task]), PROJECT_ID, _ArcNames())
        assert entries[0].status == MISSING
        assert "文件不存在" in entries[0].reason
        assert entries[0].arcname == ""

    @pytest.mark.asyncio
    async def test_size_mismatch_is_missing(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import MISSING, _ArcNames, _pdf_deliverable_entries
        pdf = tmp_path / "y.pdf"
        pdf.write_bytes(b"%PDF-fake")
        task = _completed_task(file_path=str(pdf), file_size=99999)  # 记录大小 ≠ 实际
        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file", lambda p: pdf
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([task]), PROJECT_ID, _ArcNames())
        assert entries[0].status == MISSING
        assert "大小不符" in entries[0].reason

    @pytest.mark.asyncio
    async def test_zero_byte_file_is_missing(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import MISSING, _ArcNames, _pdf_deliverable_entries
        pdf = tmp_path / "z.pdf"
        pdf.write_bytes(b"")
        task = _completed_task(file_path=str(pdf), file_size=0)
        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file", lambda p: pdf
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([task]), PROJECT_ID, _ArcNames())
        assert entries[0].status == MISSING
        assert "0 字节" in entries[0].reason

    @pytest.mark.asyncio
    async def test_failed_tasks_are_not_collected(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import _ArcNames, _pdf_deliverable_entries
        task = _completed_task(status=SimpleNamespace(value="failed"),
                               file_path=str(tmp_path / "f.pdf"))
        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file", lambda p: None
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([task]), PROJECT_ID, _ArcNames())
        assert entries == []

    @pytest.mark.asyncio
    async def test_empty_task_list_is_empty(self, tmp_path, monkeypatch):
        from app.services.archive_inventory import _ArcNames, _pdf_deliverable_entries
        monkeypatch.setattr(
            "app.services.attachment_upload_policy.resolve_local_attachment_file",
            lambda p: None,
        )
        entries = await _pdf_deliverable_entries(_FakeTaskDb([]), PROJECT_ID, _ArcNames())
        assert entries == []

    def test_inventory_includes_pdf_entries(self):
        """清单组装必须包含 PDF 条目函数（AST 判，防接线漏提交）。"""
        import ast
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1] / "app/services/archive_inventory.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        build = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "build_project_inventory":
                build = node
                break
        assert build is not None, "找不到 build_project_inventory（夹具失锚）"
        body = ast.unparse(build)
        assert "_pdf_deliverable_entries" in body, "归档清单没有接 PDF 交付件条目"
