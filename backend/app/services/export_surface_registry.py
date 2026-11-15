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
    """一个已知的生产导出出口。

    `retired=True` 表示**这条路径从未有过真实路由**（现算 `app.routes` 确认），
    保留条目是为了让「登记过什么」可追溯，不参与闭合判定。
    """

    path: str  # 路由路径模板
    method: str  # GET/POST
    classification: ExportSurfaceClass
    description: str
    retired: bool = False


# ── 注册表 ────────────────────────────────────────────────

EXPORT_SURFACE_REGISTRY: dict[str, ExportSurfaceEntry] = {
    # ── formal: 正式出具，受 ExportUnitPolicy 约束 ──
    "trial_balance_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/trial-balance/export",
        method="GET",
        classification="formal",
        description="试算表正式导出",
    ),
    # 🔴 2026-11-16 现算：`/trial-balance/summary/export` **从未存在**
    # （前端 `useTbSummary.ts:132` 在调它 ⇒ 点一次 404）。真实只有
    # `summary-with-adjustments`（GET，回 JSON **不是文件**）⇒ 它不是导出出口，
    # **从注册表移除**（不标 retired：`retired` 的语义是「登记过但从未有路由」，
    # 而这里我要表达的是「本来就不该在导出注册表里」）。
    #
    # 🔴 前端 `useTbSummary.exportTbSummary` / `exportTbSumTemplate` 的 404
    # 仍未修（属前端任务，已登记在 tasks.md 补七）。
    # 🔴 现算：`/trial-balance/bulk-export` 从未存在，前端也**零调用**
    # （`grep trial-balance/bulk-export` = 0）⇒ 退役。
    "trial_balance_bulk_export": ExportSurfaceEntry(
        path="/api/projects/{project_id}/trial-balance/bulk-export",
        method="POST",
        classification="formal",
        description="试算表批量导出（从未实现，前端零调用）",
        retired=True,
    ),
    "report_single_export": ExportSurfaceEntry(
        # 真实路由（现算）：前端 `P_rpt.exportExcel` → 此路径
        path="/api/reports/{project_id}/{year}/{report_type}/export-excel",
        method="GET",
        classification="formal",
        description="单张财务报表导出",
    ),
    "report_full_export": ExportSurfaceEntry(
        # 真实路由（现算）：前端 `P_rpt.exportAllExcel` → 此路径
        path="/api/projects/{project_id}/reports/export-excel",
        method="POST",
        classification="formal",
        description="整套财务报表导出",
    ),
    "note_word_export": ExportSurfaceEntry(
        # 真实路由（现算）：`routers/disclosure_notes.py` 的 export-word
        path="/api/disclosure-notes/{project_id}/{year}/export-word",
        method="POST",
        classification="formal",
        description="附注 Word 导出",
    ),
    "note_word_export_with_meta": ExportSurfaceEntry(
        # 真实路由（现算）：offline-export 才带 meta（export-word 是纯 Word）
        path="/api/disclosure-notes/{project_id}/{year}/offline-export",
        method="POST",
        classification="formal",
        description="附注 Word 含元数据导出（offline 包）",
    ),
    "workpaper_export_http": ExportSurfaceEntry(
        # 真实路由（现算）：底稿 xlsx 导出
        path="/api/workpapers/{wp_id}/export-xlsx",
        method="POST",
        classification="formal",
        description="底稿 HTTP 导出（xlsx）",
    ),
    # 🔴 现算：`/export-engine` 从未存在；前端 `export-engine` 零调用。
    # `WpExportEngine` 是内部 service（被 `export-xlsx` 调用），不是独立出口 ⇒ 退役。
    "workpaper_export_engine": ExportSurfaceEntry(
        path="/api/workpapers/{wp_id}/export-engine",
        method="POST",
        classification="formal",
        description="底稿 WpExportEngine 导出（内部 service，无独立路由）",
        retired=True,
    ),
    "pdf_direct_create": ExportSurfaceEntry(
        # 真实路由（现算）：底稿 PDF 导出（`/pdf-export` 是**前端路由**不是 API 路径）
        path="/api/projects/{project_id}/working-papers/{wp_id}/export-pdf",
        method="GET",
        classification="formal",
        description="直接 PDF 导出（底稿级）",
    ),
    "deliverable_package": ExportSurfaceEntry(
        path="/api/projects/{project_id}/deliverables/package",
        method="POST",
        classification="formal",
        description="组合导出包",
    ),
    "archive_package": ExportSurfaceEntry(
        # 真实路由（现算）：编排产出包是 `archive/orchestrate`，
        # 下载是 `archive/jobs/{job_id}/package`。登记编排端点（包由它产出）。
        path="/api/projects/{project_id}/archive/orchestrate",
        method="POST",
        classification="formal",
        description="项目归档包（编排产出；下载走 archive/jobs/{job_id}/package）",
    ),
    "audit_report_export": ExportSurfaceEntry(
        # 真实路由（现算）：审计报告经 word-exports 生成
        path="/api/projects/{project_id}/word-exports/audit-report/generate",
        method="POST",
        classification="formal",
        description="审计报告导出（含五个财务占位符）",
    ),
    # ── data_exchange: 数据交换，输出规范原值 + 非正式说明 ──
    "consol_trial_local_export": ExportSurfaceEntry(
        # 🔴 真实路由是 `/api/consolidation/trial/local-export` + query 参数
        # （consolidation 域全部用 query 风格，见 `consol_trial.py`）。
        # 注册表是**描述性清单**，应匹配真实路由；不给它单独造一套 path-param 风格。
        path="/api/consolidation/trial/local-export",
        method="GET",
        classification="data_exchange",
        description="合并试算表本地数据导出（元口径原值 + 非正式说明）",
    ),
    "consol_diff_local_export": ExportSurfaceEntry(
        path="/api/consolidation/trial/diff/local-export",
        method="GET",
        classification="data_exchange",
        description="合并差额表本地导出",
    ),
    "consol_note_local_export": ExportSurfaceEntry(
        path="/api/consolidation/notes/local-export",
        method="GET",
        classification="data_exchange",
        description="合并附注本地导出",
    ),
    # ── template: 模板，无金额载荷 ──
    "import_template_download": ExportSurfaceEntry(
        # 真实路由（现算）：参数名是 `import_type` 不是 `template_id`
        path="/api/import-templates/{import_type}/download",
        method="GET",
        classification="template",
        description="导入模板下载",
    ),
    # ── non_amount: 无金额内容 ──
    "knowledge_doc_download": ExportSurfaceEntry(
        # 真实路由（现算）：参数名是 `doc_id` 不是 `document_id`
        path="/api/knowledge-library/documents/{doc_id}/download",
        method="GET",
        classification="non_amount",
        description="知识库文档下载（无金额）",
    ),
    "attachment_download": ExportSurfaceEntry(
        # 真实路由（现算）：带 `:uuid` 转换器（省略它会让字面路径不匹配）
        path="/api/attachments/{attachment_id:uuid}/download",
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
    # `retired=True` 的条目**现算确认无真实路由**（保留仅为可追溯）⇒ 不参与闭合判定。
    # 若把它算进 `registered_paths`，`missing` 会永远挂着这几条；
    # 若完全不排除，又会让「退役」变成「悄悄删掉、没人记得曾经登记过」。
    for entry in EXPORT_SURFACE_REGISTRY.values():
        if entry.retired:
            continue
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
