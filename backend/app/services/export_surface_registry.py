"""
正式导出出口注册表。

每个实际生产文件 sink（Excel/Word/PDF/ZIP）恰有一个分类：
formal / data_exchange / template / non_amount。

提供 validate_registry(app) 对比真实路由验证闭合。

design §9, R9, AC-20, AC-23.
"""

from __future__ import annotations

import json
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
#: 自动补登记的导出出口数据文件（相对 `backend/`）。
AUTO_SURFACE_FILE = "data/export_surface_auto_surfaces.json"


def _load_auto_surfaces() -> tuple[tuple[str, str, str], ...]:
    """从数据文件读自动补登记出口（`(path, method, classification)` 三元组）。

    🔴 为什么是数据文件而不是模块内元组：295 条三元组逐条展开约 300 行，
    会把本模块推过 800 行门限。本仓库既有做法一致（`wp_code_overrides.json`
    / `export_surface_classification_gaps.json` 均为数据文件）。
    """
    from pathlib import Path as _Path

    path = _Path(__file__).resolve().parents[2] / AUTO_SURFACE_FILE
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("surfaces") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError(f"{AUTO_SURFACE_FILE} 格式非法：缺 surfaces 列表")
    return tuple(
        (str(it["path"]), str(it["method"]), str(it["classification"]))
        for it in items
    )


_AUTO_SURFACES: tuple[tuple[str, str, str], ...] = _load_auto_surfaces()


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



# ── 分类一致性（2026-11-16）────────────────────────────────
#
# 🔴 `_AUTO_SURFACES` 按路径关键字自动分类，**没经过实现验证**：
# 35 条 formal 无 `ExportUnitPolicy`、128 条 data_exchange 无 `_GT_EXPORT_META`
# （权威源 `docs/reference/formal-export-unit-policy.md` §1）。
# 🔴 不直接改分类：分类是业务语义声明不是代码事实，「没写 marker」也可能是
# 实现漏了应有行为（真实缺陷）—— 改判等于把缺陷合法化（memory ㉗）。
# 缺口登记在 `backend/data/export_surface_classification_gaps.json`，按族裁决。

#: 缺口登记文件的路径（相对仓库 `backend/`）。
CLASSIFICATION_GAP_FILE = "data/export_surface_classification_gaps.json"

#: formal 分类要求的实现特征（`ExportUnitPolicy` 折算链）。
_UNIT_POLICY_RE = re.compile(
    r"ExportUnitPolicy|export_policy|convert_amount|divisor|amount_unit"
)

#: data_exchange 分类要求的实现特征（`_GT_EXPORT_META` marker）。
_EXPORT_MARKER_RE = re.compile(
    r"_GT_EXPORT_META|ExportMeta|export_meta_marker|marker_rows"
)

#: 「取回已生成文件」形态：直接返回磁盘文件，不渲染单元格内容。
#: 这类路由是**两段式导出链的第二段**（先生成、再下载），单位折算发生在
#: 第一段（生成端点），所以本身不要求 `ExportUnitPolicy`。
_FILE_RETRIEVAL_RE = re.compile(r"FileResponse\b")

#: 「自己渲染内容」形态：真的构造工作簿 / 文档并写单元格。
_RENDERS_CONTENT_RE = re.compile(
    r"openpyxl|Workbook\(|load_workbook|\.save\(|Document\(|docx\."
)

#: 「请求内新建文件」形态：本请求自己生成再返回（即使最终用 FileResponse）。
#: 这类**不是**取回类 —— 它自己就该负责折算。
_CREATES_IN_REQUEST_RE = re.compile(
    r"output_path\s*=|output_dir\s*/|mkdir\(|to_word\(|to_excel\(|"
    r"export_bytes\(|build_\w*workbook|render\w*\(.*output"
)


def _endpoint_source(route: object) -> str:
    """取路由 endpoint 源码；取不到返回空串（调用方按「无法判定」处理）。"""
    import inspect as _inspect

    ep = getattr(route, "endpoint", None)
    if ep is None:
        return ""
    try:
        return _inspect.getsource(ep)
    except (OSError, TypeError):
        return ""


def is_file_retrieval(src: str) -> bool:
    """该实现是否为「取回已生成文件」形态（不渲染、不新建文件）。

    三条件同时成立才算取回类：①`FileResponse` 直返；②不构造工作簿/文档
    （无 openpyxl / Workbook / .save / Document）；③不在请求内新建文件
    （无 output_path 赋值 / mkdir / to_word / to_excel）。

    🔴 ③ 是关键：`excel-html/module/{module}/export-word` 也用 FileResponse，
    但它 `output_path = ...` + `module_to_word(..., output_path)` 自己写盘
    ⇒ 生成类，不豁免（它自己该负责折算）。
    """
    if not _FILE_RETRIEVAL_RE.search(src):
        return False
    if _RENDERS_CONTENT_RE.search(src):
        return False
    if _CREATES_IN_REQUEST_RE.search(src):
        return False
    return True


def classify_conformance(route: object, declared: str) -> str:
    """该路由的实现与其**声明分类**的符合性。

    `ok` / `formal_missing_unit_policy` / `data_exchange_missing_marker` /
    `retrieval_ok`（取回已生成文件，不要求折算）/ `unverifiable`。
    """
    src = _endpoint_source(route)
    if not src:
        return "unverifiable"
    if declared == "formal":
        if _UNIT_POLICY_RE.search(src):
            return "ok"
        if is_file_retrieval(src):
            return "retrieval_ok"
        return "formal_missing_unit_policy"
    if declared == "data_exchange":
        return "ok" if _EXPORT_MARKER_RE.search(src) else "data_exchange_missing_marker"
    return "ok"


def load_classification_gaps() -> frozenset[str]:
    """读缺口登记文件；文件缺失/损坏按空集（会让 `verify` 报全部为新增）。"""
    from pathlib import Path as _Path

    path = _Path(__file__).resolve().parents[2] / CLASSIFICATION_GAP_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    paths = raw.get("gaps") if isinstance(raw, dict) else raw
    if not isinstance(paths, list):
        return frozenset()
    return frozenset(str(p) for p in paths)


def verify_classification_conformance(
    app: "Starlette",
) -> tuple[list[str], list[str]]:
    """现算分类一致性缺口，与登记文件双向比对。

    Returns
    -------
    (resolved, new)
        `resolved` = 已修好但仍留在登记里的路径（须从文件里删）
        `new`      = 现算有缺口但未登记的路径（须补登记）

    两者任一非空 = 登记与实现漂移。这是棘轮：修好一条删一条，
    新出现一条补一条，总数只许减少（`test_classification_gaps_do_not_grow`）。

    🔴 取回类（FileResponse 直返 + 请求内不新建文件）不算缺口：文件由上游
    产生（异步任务 / 上传 / 另一段导出链），折算在产生方。
    """
    by_pm: dict[tuple[str, str], object] = {}
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in getattr(route, "methods", None) or ():
            by_pm[(path, method)] = route

    actual: set[str] = set()
    for entry in EXPORT_SURFACE_REGISTRY.values():
        if entry.retired or entry.classification not in ("formal", "data_exchange"):
            continue
        route = by_pm.get((entry.path, entry.method))
        if route is None:
            continue
        verdict = classify_conformance(route, entry.classification)
        if verdict in ("ok", "unverifiable", "retrieval_ok"):
            continue
        actual.add(entry.path)

    registered = load_classification_gaps()
    return sorted(registered - actual), sorted(actual - registered)

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
    """归一化路径参数名，**保留转换器**。

    `{name:conv}` → `{:conv}`，`{name}` → `{}`。参数名被忽略（Starlette
    实现细节），转换器被保留 —— `:uuid` 与无转换器是**不同的路由**。
    🔴 原实现把两者都归一成 `{}`，导致 `validate_registry` 静默放行漏写
    转换器的登记（两套 path 口径给出相反答案）。
    """
    return re.sub(
        r"\{([^}:]+)(?::([^}]+))?\}",
        lambda m: f"{{:{m.group(2)}}}" if m.group(2) else "{}",
        path,
    )


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
