"""
正式导出出口注册表。

每个实际生产文件 sink（Excel/Word/PDF/ZIP）恰有一个分类：
formal / data_exchange / template / non_amount。

提供 validate_registry(app) 对比真实路由验证闭合。

design §9, R9, AC-20, AC-23.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from starlette.applications import Starlette

# ── 数据结构 ──────────────────────────────────────────────

ExportSurfaceClass = Literal["formal", "data_exchange", "template", "non_amount"]


@dataclass(frozen=True)
class ExportSurfaceEntry:
    """一个已知的生产导出出口。"""

    path: str  # 路由路径模板
    method: str  # GET/POST
    classification: ExportSurfaceClass
    description: str


# ── 注册表 ────────────────────────────────────────────────

EXPORT_SURFACE_REGISTRY: dict[str, ExportSurfaceEntry] = {
    # ── formal: 正式出具，受 ExportUnitPolicy 约束 ──
    "trial_balance_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/trial-balance/export",
        method="GET",
        classification="formal",
        description="试算表正式导出",
    ),
    "trial_balance_summary_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/trial-balance/summary/export",
        method="GET",
        classification="formal",
        description="试算表汇总导出",
    ),
    "trial_balance_bulk_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/trial-balance/bulk-export",
        method="POST",
        classification="formal",
        description="试算表批量导出",
    ),
    "report_single_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/reports/{report_id}/export",
        method="GET",
        classification="formal",
        description="单张财务报表导出",
    ),
    "report_full_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/reports/export-all",
        method="POST",
        classification="formal",
        description="整套财务报表导出",
    ),
    "note_word_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/disclosure-notes/export",
        method="POST",
        classification="formal",
        description="附注 Word 导出",
    ),
    "note_word_export_with_meta": ExportSurfaceEntry(
        path="/api/projects/{project_id}/disclosure-notes/export-with-meta",
        method="POST",
        classification="formal",
        description="附注 Word 含元数据导出",
    ),
    "workpaper_export_http": ExportSurfaceEntry(
        path="/api/workpapers/{workpaper_id}/export",
        method="GET",
        classification="formal",
        description="底稿 HTTP 导出",
    ),
    "workpaper_export_engine": ExportSurfaceEntry(
        path="/api/workpapers/{workpaper_id}/export-engine",
        method="POST",
        classification="formal",
        description="底稿 WpExportEngine 导出",
    ),
    "pdf_direct_create": ExportSurfaceEntry(
        path="/api/projects/{project_id}/pdf-export",
        method="POST",
        classification="formal",
        description="直接 PDF 导出",
    ),
    "deliverable_package": ExportSurfaceEntry(
        path="/api/projects/{project_id}/deliverables/package",
        method="POST",
        classification="formal",
        description="组合导出包",
    ),
    "archive_package": ExportSurfaceEntry(
        path="/api/projects/{project_id}/archive/package",
        method="POST",
        classification="formal",
        description="项目归档包",
    ),
    "audit_report_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/audit-report/export",
        method="POST",
        classification="formal",
        description="审计报告导出（含五个财务占位符）",
    ),
    # ── data_exchange: 数据交换，输出规范原值 + 非正式说明 ──
    "consol_trial_local_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/consolidation/trial-balance/local-export",
        method="GET",
        classification="data_exchange",
        description="合并试算表本地数据导出（元口径原值 + 非正式说明）",
    ),
    "consol_diff_local_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/consolidation/diff/local-export",
        method="GET",
        classification="data_exchange",
        description="合并差额表本地导出",
    ),
    "consol_note_local_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/consolidation/notes/local-export",
        method="GET",
        classification="data_exchange",
        description="合并附注本地导出",
    ),
    # ── template: 模板，无金额载荷 ──
    "import_template_download": ExportSurfaceEntry(
        path="/api/import-templates/{template_id}/download",
        method="GET",
        classification="template",
        description="导入模板下载",
    ),
    # ── non_amount: 无金额内容 ──
    "knowledge_doc_download": ExportSurfaceEntry(
        path="/api/knowledge-library/documents/{document_id}/download",
        method="GET",
        classification="non_amount",
        description="知识库文档下载（无金额）",
    ),
    "attachment_download": ExportSurfaceEntry(
        path="/api/attachments/{attachment_id}/download",
        method="GET",
        classification="non_amount",
        description="附件下载（无金额）",
    ),
}


# ── 校验 ──────────────────────────────────────────────────

class RegistryValidationError(Exception):
    """导出出口注册表与实际路由不一致。"""

    def __init__(
        self,
        *,
        unregistered: list[str] | None = None,
        missing: list[str] | None = None,
        duplicate_classification: list[str] | None = None,
    ) -> None:
        self.unregistered = unregistered or []
        self.missing = missing or []
        self.duplicate_classification = duplicate_classification or []
        parts: list[str] = []
        if self.unregistered:
            parts.append(f"未注册的导出路由: {self.unregistered}")
        if self.missing:
            parts.append(f"已注册但未挂载的路由: {self.missing}")
        if self.duplicate_classification:
            parts.append(f"重复分类: {self.duplicate_classification}")
        super().__init__("; ".join(parts) if parts else "校验通过")


def _normalize_path(path: str) -> str:
    """归一化路径参数。"""
    import re

    return re.sub(r"\{[^}]+\}", "{}", path)


_EXPORT_KEYWORDS = (
    "/export",
    "/export-all",
    "/export-with-meta",
    "/export-engine",
    "/bulk-export",
    "/local-export",
    "/pdf-export",
    "/deliverables/package",
    "/archive/package",
    "/audit-report/export",
    "/download",
)


def _is_export_path(path: str) -> bool:
    """判断一个路由路径是否属于导出相关域。"""
    lower = path.lower()
    return any(kw in lower for kw in _EXPORT_KEYWORDS)


def validate_registry(app: "Starlette") -> None:
    """对比 app.routes 与 EXPORT_SURFACE_REGISTRY 的闭合性。

    Raises
    ------
    RegistryValidationError
        存在未注册的导出路由、已注册路由不在 app.routes 中或重复分类。
    """
    registered_paths: set[str] = set()
    for entry in EXPORT_SURFACE_REGISTRY.values():
        registered_paths.add(_normalize_path(entry.path))

    # 检查重复分类（同一 path 不应出现两次）
    seen_paths: dict[str, str] = {}
    duplicates: list[str] = []
    for key, entry in EXPORT_SURFACE_REGISTRY.items():
        norm = _normalize_path(entry.path)
        if norm in seen_paths:
            duplicates.append(f"{norm} (keys: {seen_paths[norm]}, {key})")
        else:
            seen_paths[norm] = key

    # 扫描 app.routes
    actual_export_paths: set[str] = set()
    all_app_paths: set[str] = set()

    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        if path is None:
            for sub_route in getattr(route, "routes", []):
                sub_path = getattr(sub_route, "path", None)
                if sub_path:
                    prefix = getattr(route, "path", "")
                    full = prefix.rstrip("/") + "/" + sub_path.lstrip("/")
                    norm = _normalize_path(full)
                    all_app_paths.add(norm)
                    if _is_export_path(full):
                        actual_export_paths.add(norm)
            continue
        norm = _normalize_path(path)
        all_app_paths.add(norm)
        if _is_export_path(path):
            actual_export_paths.add(norm)

    unregistered = sorted(actual_export_paths - registered_paths)
    missing = sorted(registered_paths - all_app_paths)

    if unregistered or missing or duplicates:
        raise RegistryValidationError(
            unregistered=unregistered,
            missing=missing,
            duplicate_classification=duplicates,
        )
