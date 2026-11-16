"""
正式导出出口注册表。

每个实际生产文件 sink（Excel/Word/PDF/ZIP）恰有一个分类：
formal / data_exchange / template / non_amount。

提供 validate_registry(app) 对比真实路由验证闭合。

design §9, R9, AC-20, AC-23.
"""

from __future__ import annotations

import re
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

# ── 自动补登记（2026-11-16 清零 unregistered 303 → 0）──
#
# 🔴 这里用**数据表**而不是 295 份 ExportSurfaceEntry 样板：条目是同构的
# （path / method / classification 三元组），逐条展开会把本文件推到 2000+ 行，
# 远超行数门 800 行。表在 import 期展开成正式注册表，语义完全等价。
#
# 新增导出端点时：在 `_AUTO_SURFACES` 末尾加一行，并在 `backend/tests/`
# 跑 `test_export_surface_registry.py`（未登记会打红）。
_AUTO_SURFACES: tuple[tuple[str, str, str], ...] = (
    # formal（43 条）
    ("/api/a17/export-word", "GET", "formal"),
    ("/api/audit-logs/export", "GET", "formal"),
    ("/api/consolidation/reports/{project_id}/{year}/artifacts/{artifact_id}/download", "GET", "formal"),
    ("/api/consolidation/reports/{project_id}/{year}/workpaper/download", "GET", "formal"),
    ("/api/consolidation/{project_id}/snapshots/{snapshot_id}/download", "GET", "formal"),
    ("/api/custom-query/artifacts/{artifact_id}/download", "GET", "formal"),
    ("/api/eqcr/projects/{project_id}/memo/export", "GET", "formal"),
    ("/api/export/create", "POST", "formal"),
    ("/api/export/{task_id}/download", "GET", "formal"),
    ("/api/exports/{export_id}/download", "GET", "formal"),
    ("/api/knowledge/{category}/documents/{filename}/download", "GET", "formal"),
    ("/api/projects/{project_id}/audit-checks/export", "POST", "formal"),
    ("/api/projects/{project_id}/bulk-tab/export-templates/async", "POST", "formal"),
    ("/api/projects/{project_id}/bulk-tab/export/{task_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/cf-verification/{year}/export", "GET", "formal"),
    ("/api/projects/{project_id}/data-validation/export", "POST", "formal"),
    ("/api/projects/{project_id}/deliverables/package/{job_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/deliverables/trio/items/{item_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/download", "GET", "formal"),
    ("/api/projects/{project_id}/excel-html/download/{file_stem}", "GET", "formal"),
    ("/api/projects/{project_id}/excel-html/module/{module}/export-word", "POST", "formal"),
    ("/api/projects/{project_id}/knowledge/documents/{filename}/download", "GET", "formal"),
    ("/api/projects/{project_id}/notes/export-word", "POST", "formal"),
    ("/api/projects/{project_id}/qc-report/export", "GET", "formal"),
    ("/api/projects/{project_id}/word-exports/{task_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/workflow/export-package", "POST", "formal"),
    ("/api/projects/{project_id}/working-papers/download-pack", "POST", "formal"),
    ("/api/projects/{project_id}/working-papers/{wp_id}/b2-12/export-docx", "GET", "formal"),
    ("/api/projects/{project_id}/working-papers/{wp_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/working-papers/{wp_id}/export-word", "GET", "formal"),
    ("/api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete", "GET", "formal"),
    ("/api/projects/{project_id}/workpaper-summary/export", "POST", "formal"),
    ("/api/projects/{project_id}/workpapers/download-pack", "POST", "formal"),
    ("/api/projects/{project_id}/workpapers/{wp_id}/download-file", "GET", "formal"),
    ("/api/projects/{project_id}/workpapers/{wp_id}/export-with-metadata", "POST", "formal"),
    ("/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/download", "GET", "formal"),
    ("/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/recovery-cases/{case_id}/download-only", "POST", "formal"),
    ("/api/projects/{project_id}/wp-templates/download-all", "GET", "formal"),
    ("/api/projects/{project_id}/wp-templates/{wp_code}/download", "GET", "formal"),
    ("/api/qc/annual-reports/{report_id}/download", "GET", "formal"),
    ("/api/review-conversations/{conversation_id}/export", "POST", "formal"),
    ("/api/workhours/stats/export", "GET", "formal"),
    ("/api/workpapers/{wp_id}/import-export/export", "GET", "formal"),
    # data_exchange（128 条）
    ("/api/consolidation/worksheet/pivot/export", "GET", "data_exchange"),
    ("/api/custom-query/export", "POST", "data_exchange"),
    ("/api/formula-management/import-export/export-data", "POST", "data_exchange"),
    ("/api/h5/export-data", "POST", "data_exchange"),
    ("/api/h9-lease-liabilities/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/l2-interest-payable/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/l6-special-payables/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/l7-other-noncurrent-liabilities/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/l8-financial-expenses/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m1-dividends-payable/{wp_id}/export-data", "POST", "data_exchange"),
    ("/api/m10-other-equity-instruments/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m2-paid-in-capital/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m3-treasury-stock/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m4-capital-reserve/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m5-surplus-reserve/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m6-retained-earnings/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m7-special-reserve/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m8-general-risk-reserve/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/m9-other-comprehensive-income/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/n1-deferred-tax-assets/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/n2-taxes-payable/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/n3-deferred-tax-liabilities/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/n4/export-data", "POST", "data_exchange"),
    ("/api/n5-income-tax-expense/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/projects/{project_id}/adjustments/export-summary", "GET", "data_exchange"),
    ("/api/projects/{project_id}/bulk-tab/export-data", "POST", "data_exchange"),
    ("/api/projects/{project_id}/bulk-tab/export-data/async", "POST", "data_exchange"),
    ("/api/projects/{project_id}/excel-html/module/{module}/export-excel", "POST", "data_exchange"),
    ("/api/projects/{project_id}/ledger/export-aux-balance", "GET", "data_exchange"),
    ("/api/projects/{project_id}/ledger/export-balance", "GET", "data_exchange"),
    ("/api/projects/{project_id}/ledger/export-ledger/{account_code}", "GET", "data_exchange"),
    ("/api/query/export-excel", "POST", "data_exchange"),
    ("/api/s-estimate/{wp_id}/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/bad-debt-rows/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/c24-journal/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/d1-ecl/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d1/disclosure/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/d7/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/e1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/export-review-xlsx", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/f0/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f2-spe/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f2-st/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f2-val/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/f5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g0/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g10/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g11/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g12/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g13/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g14/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g4-ecl/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g4-main/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g4-sppi/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g6-ecl/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g6-main/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g6-sppi/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g7-equity-method/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g7-main/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g7-sub/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g8/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/g9/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h0/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h10/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/h7/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/h8/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/i6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/j1/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/j2/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/k0/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k10/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k11/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k12/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k13/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k7/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k8/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/k9/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/l0/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/l1/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/l2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/l3/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/l4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/l5/export-data", "GET", "data_exchange"),
    ("/api/workpapers/{wp_id}/l6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m10/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m4/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m5/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m6/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m7/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m8/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/m9/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/n1/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/n2/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/n3/export-data", "POST", "data_exchange"),
    ("/api/workpapers/{wp_id}/n5/export-data", "POST", "data_exchange"),
    # template（124 条）
    ("/api/formula-management/import-export/export-template", "POST", "template"),
    ("/api/h5/export-template", "POST", "template"),
    ("/api/h9-lease-liabilities/{wp_id}/export-template", "GET", "template"),
    ("/api/l2-interest-payable/{wp_id}/export-template", "GET", "template"),
    ("/api/l6-special-payables/{wp_id}/export-template", "GET", "template"),
    ("/api/l7-other-noncurrent-liabilities/{wp_id}/export-template", "GET", "template"),
    ("/api/l8-financial-expenses/{wp_id}/export-template", "GET", "template"),
    ("/api/m1-dividends-payable/{wp_id}/export-template", "POST", "template"),
    ("/api/m10-other-equity-instruments/{wp_id}/export-template", "GET", "template"),
    ("/api/m2-paid-in-capital/{wp_id}/export-template", "GET", "template"),
    ("/api/m3-treasury-stock/{wp_id}/export-template", "GET", "template"),
    ("/api/m4-capital-reserve/{wp_id}/export-template", "GET", "template"),
    ("/api/m5-surplus-reserve/{wp_id}/export-template", "GET", "template"),
    ("/api/m6-retained-earnings/{wp_id}/export-template", "GET", "template"),
    ("/api/m7-special-reserve/{wp_id}/export-template", "GET", "template"),
    ("/api/m8-general-risk-reserve/{wp_id}/export-template", "GET", "template"),
    ("/api/m9-other-comprehensive-income/{wp_id}/export-template", "GET", "template"),
    ("/api/n1-deferred-tax-assets/{wp_id}/export-template", "GET", "template"),
    ("/api/n2-taxes-payable/{wp_id}/export-template", "GET", "template"),
    ("/api/n3-deferred-tax-liabilities/{wp_id}/export-template", "GET", "template"),
    ("/api/n4/export-template", "POST", "template"),
    ("/api/n5-income-tax-expense/{wp_id}/export-template", "GET", "template"),
    ("/api/projects/{project_id}/adjustments/export-template", "GET", "template"),
    ("/api/projects/{project_id}/bulk-tab/export-templates", "POST", "template"),
    ("/api/projects/{project_id}/review-workflow/{year}/export-blank", "GET", "template"),
    ("/api/s-estimate/{wp_id}/export-template", "GET", "template"),
    ("/api/staff/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/bad-debt-rows/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/c24-journal/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/d1-ecl/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d1/disclosure/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/d7/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/e1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/f0/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f2-spe/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f2-st/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f2-val/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/f5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g0/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g10/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g11/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g12/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g13/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g14/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g4-ecl/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g4-main/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g4-sppi/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g6-ecl/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g6-main/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g6-sppi/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g7-equity-method/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g7-main/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g7-sub/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g8/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/g9/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h0/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h10/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/h7/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/h8/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/i6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/j1/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/j2/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/k0/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k10/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k11/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k12/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k13/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k7/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k8/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/k9/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/l0/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/l1/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/l2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/l3/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/l4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/l5/export-template", "GET", "template"),
    ("/api/workpapers/{wp_id}/l6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m10/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m4/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m6/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m7/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m8/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/m9/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/n1/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/n2/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/n3/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/n5/export-template", "POST", "template"),
    ("/api/workpapers/{wp_id}/offline/export-template", "POST", "template"),
    ("/projects/{project_id}/account-packages/{wp_code}/export-template", "GET", "template"),
)


#: 自动段的 description 按分类统一（同一分类语义相同）。
_AUTO_DESCRIPTIONS: dict[str, str] = {
    "formal": "正式出具（生成 docx/zip/pdf 交付件）",
    "data_exchange": "数据交换（导出 Excel 数据，非正式出具）",
    "template": "导入模板（供用户下载填报，不产生金额口径）",
    "non_amount": "元数据/状态查询（不产出文件内容）",
}


def _auto_key(path: str) -> str:
    """由路径造稳定 key（去 /api、去 {}、非字母数字转下划线）。"""
    p = path[len("/api/"):] if path.startswith("/api/") else path.lstrip("/")
    p = p.replace("{}", "")
    raw = re.sub(r"[^a-z0-9_]", "_", p.lower())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return f"auto_{raw}"


for _path, _method, _cls in _AUTO_SURFACES:
    _key = _auto_key(_path)
    _n = 2
    while _key in EXPORT_SURFACE_REGISTRY:
        _key = f"{_auto_key(_path)}_{_n}"
        _n += 1
    EXPORT_SURFACE_REGISTRY[_key] = ExportSurfaceEntry(
        path=_path,
        method=_method,
        classification=_cls,
        description=_AUTO_DESCRIPTIONS[_cls],
    )
del _path, _method, _cls, _key, _n


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

#: 🔴 元数据型后缀 —— 这些路由**查询导出任务本身**（状态 / 历史 / manifest /
#: 完整性 / 下载令牌），**不产出文件字节** ⇒ 按本模块定义（「每个实际生产文件
#: sink」）不属于导出出口，必须排除。
#:
#: 实测背景（2026-11-16）：`unregistered` 曾含 8 条这类路径，若把它们当导出出口
#: 补登记，注册表就会混入「不产文件的端点」，闭合判据从此不能回答
#: 「哪些端点真的会写文件」。
_METADATA_ONLY_SUFFIXES = (
    "/status",
    "/history",
    "/manifest",
    "/integrity",
    "/download-token",
    "/export-history",
)

#: 任务资源本身（`/api/exports/{id}`）；其下的 `/download` 仍算出口。
_METADATA_ONLY_EXACT = (
    "/api/export/{}",
    "/api/exports/{}",
)


def is_metadata_only_export_path(path: str) -> bool:
    """该路径是否属「导出任务的元数据查询」（不产文件）。"""
    norm = _normalize_path(path).rstrip("/").lower()
    if norm in _METADATA_ONLY_EXACT:
        return True
    return any(norm.endswith(s) for s in _METADATA_ONLY_SUFFIXES)


def _is_export_path(path: str) -> bool:
    """判断一个路由路径是否属于导出相关域（含实际产出文件的 sink）。"""
    lower = path.lower()
    if not any(kw in lower for kw in _EXPORT_KEYWORDS):
        return False
    # 元数据查询不算出口：否则「哪些端点会写文件」这个问题就没有答案。
    return not is_metadata_only_export_path(path)


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
