"""
# Feature: audit-report-deliverable-center, Property 16: 编辑器模式由状态决定
# Feature: audit-report-deliverable-center, Property 17: 编辑器类型由扩展名决定

PBT: OnlyOffice 编辑器配置属性测试（Task 21.3 / 21.4）

Property 16 — 编辑器模式由状态决定:
  For any 交付物，OnlyOffice 编辑器以只读模式打开当且仅当其状态属于
  {confirmed, signed, archived}；其余可编辑状态以编辑模式打开。
  **Validates: Requirements 6.5, 6.6**

Property 17 — 编辑器类型由扩展名决定:
  For any 交付物版本文件，扩展名为 .docx 时以 Document Editor 加载（word），
  为 .xlsx 时以 Spreadsheet Editor 加载（cell）。
  **Validates: Requirements 6.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.phase13_models import WordExportStatus
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 所有可能的交付物状态
ALL_STATUSES = [s.value for s in WordExportStatus]

# 只读状态集合
READONLY_STATUSES = {"confirmed", "signed", "archived"}

# 可编辑状态集合（所有状态减去只读集合）
EDITABLE_STATUSES = [s for s in ALL_STATUSES if s not in READONLY_STATUSES]

# 文件扩展名策略
docx_paths = st.sampled_from([
    "report_v1.docx",
    "审计报告.docx",
    "/storage/deliverables/abc/test.DOCX",
    "path/to/file.Docx",
])

xlsx_paths = st.sampled_from([
    "report_v1.xlsx",
    "财务报表.xlsx",
    "/storage/deliverables/abc/test.XLSX",
    "path/to/file.Xlsx",
])


# ---------------------------------------------------------------------------
# Property 16: 编辑器模式由状态决定
# Feature: audit-report-deliverable-center, Property 16: 编辑器模式由状态决定
# **Validates: Requirements 6.5, 6.6**
# ---------------------------------------------------------------------------


@given(status=st.sampled_from(list(READONLY_STATUSES)))
@settings(max_examples=5)
def test_property_16_readonly_statuses_yield_view_mode(status: str):
    """Property 16: confirmed/signed/archived 状态 → 编辑器以只读模式(view)打开。

    **Validates: Requirements 6.5, 6.6**
    """
    svc = OnlyOfficeCallbackService.__new__(OnlyOfficeCallbackService)
    mode = svc._editor_mode(status)
    assert mode == "view", f"状态 {status} 应为 view 模式，实际为 {mode}"


@given(status=st.sampled_from(EDITABLE_STATUSES))
@settings(max_examples=5)
def test_property_16_editable_statuses_yield_edit_mode(status: str):
    """Property 16: 非只读状态 → 编辑器以编辑模式(edit)打开。

    **Validates: Requirements 6.5, 6.6**
    """
    svc = OnlyOfficeCallbackService.__new__(OnlyOfficeCallbackService)
    mode = svc._editor_mode(status)
    assert mode == "edit", f"状态 {status} 应为 edit 模式，实际为 {mode}"


# ---------------------------------------------------------------------------
# Property 17: 编辑器类型由扩展名决定
# Feature: audit-report-deliverable-center, Property 17: 编辑器类型由扩展名决定
# **Validates: Requirements 6.2**
# ---------------------------------------------------------------------------


@given(file_path=docx_paths)
@settings(max_examples=5)
def test_property_17_docx_yields_word_document_type(file_path: str):
    """Property 17: .docx 扩展名 → Document Editor (word)。

    **Validates: Requirements 6.2**
    """
    svc = OnlyOfficeCallbackService.__new__(OnlyOfficeCallbackService)
    doc_type = svc._document_type(file_path)
    assert doc_type == "word", f"文件 {file_path} 应为 word 类型，实际为 {doc_type}"


@given(file_path=xlsx_paths)
@settings(max_examples=5)
def test_property_17_xlsx_yields_cell_document_type(file_path: str):
    """Property 17: .xlsx 扩展名 → Spreadsheet Editor (cell)。

    **Validates: Requirements 6.2**
    """
    svc = OnlyOfficeCallbackService.__new__(OnlyOfficeCallbackService)
    doc_type = svc._document_type(file_path)
    assert doc_type == "cell", f"文件 {file_path} 应为 cell 类型，实际为 {doc_type}"
