"""
账套导入可执行入口注册表。

列出已知的导入相关路由路径（detect/preview/submit/410 退役端点），
并提供 validate_entrypoints(app) 对比 app.routes 验证闭合。

design §5, R8, AC-14, AC-15, AC-23.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from starlette.applications import Starlette

# ── 入口分类 ──────────────────────────────────────────────

EntrypointKind = Literal["preview", "detect", "submit", "retired", "status", "recovery"]


@dataclass(frozen=True)
class LedgerImportEntrypoint:
    """一个已知的账套导入相关路由入口。"""

    path: str
    method: str  # GET/POST/PUT/DELETE
    kind: EntrypointKind
    description: str


# ── 注册表 ────────────────────────────────────────────────

LEDGER_IMPORT_ENTRYPOINTS: frozenset[LedgerImportEntrypoint] = frozenset(
    {
        # ── detect ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/detect",
            method="POST",
            kind="detect",
            description="v2 账套导入检测：检测上传 bundle 中的金额单位",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-data/incremental/detect",
            method="POST",
            kind="detect",
            description="增量导入检测：返回当前 active 基准 ID/digest 与月份",
        ),
        # ── preview ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/account-chart/preview",
            method="POST",
            kind="preview",
            description="科目表预览：上传解析后返回预览结果与 unit_detection",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger/smart-preview",
            method="POST",
            kind="preview",
            description="智能导入预览：序时账/余额预览",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import/preview",
            method="POST",
            kind="preview",
            description="旧导入预览（保留只读）",
        ),
        # ── submit ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/submit",
            method="POST",
            kind="submit",
            description="v2 确认提交：需要 upload_token + UnitConfirmationInput",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/account-chart/import-async",
            method="POST",
            kind="submit",
            description="科目表异步导入：共用 UnitConfirmationInput",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger/smart-import",
            method="POST",
            kind="submit",
            description="智能导入提交：共用 UnitConfirmationInput",
        ),
        # ── retired (固定 410) ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/account-chart/import",
            method="POST",
            kind="retired",
            description="旧同步科目表导入：固定 410 LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import",
            method="POST",
            kind="retired",
            description="旧同步导入：固定 410 LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-data/incremental/apply",
            method="POST",
            kind="retired",
            description="旧增量覆盖：固定 410 INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB",
        ),
        # ── status (只读) ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/status",
            method="GET",
            kind="status",
            description="导入作业状态查询",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import/progress/{batch_id}",
            method="GET",
            kind="status",
            description="旧导入批次进度查询",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import/batches",
            method="GET",
            kind="status",
            description="旧导入批次列表",
        ),
        # ── recovery ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import/rollback/{batch_id}",
            method="POST",
            kind="recovery",
            description="旧批次回滚",
        ),
    }
)


# ── 校验 ──────────────────────────────────────────────────

class EntrypointValidationError(Exception):
    """入口注册表与实际路由不一致。"""

    def __init__(self, *, unregistered: list[str], missing: list[str]) -> None:
        self.unregistered = unregistered
        self.missing = missing
        parts: list[str] = []
        if unregistered:
            parts.append(f"未注册的导入相关路由: {unregistered}")
        if missing:
            parts.append(f"已注册但未挂载的路由: {missing}")
        super().__init__("; ".join(parts))


def _normalize_path(path: str) -> str:
    """将 Starlette 路径模板中的参数名归一化（仅保留花括号结构）。

    例: /api/projects/{project_id}/import/progress/{batch_id}
    →  /api/projects/{}/import/progress/{}
    """
    import re as _re

    return _re.sub(r"\{[^}]+\}", "{}", path)


def _is_ledger_import_path(path: str) -> bool:
    """判断一个路由路径是否属于账套导入相关域。"""
    normalized = path.lower()
    keywords = (
        "/ledger-import/",
        "/ledger-data/incremental/",
        "/account-chart/import",
        "/account-chart/preview",
        "/ledger/smart-import",
        "/ledger/smart-preview",
        "/import/preview",
        "/import/progress/",
        "/import/batches",
        "/import/rollback/",
    )
    # 精确匹配 POST /api/projects/{project_id}/import（不匹配 /import-templates 等）
    if normalized.rstrip("/").endswith("/import") and "/projects/" in normalized:
        return True
    return any(kw in normalized for kw in keywords)


def validate_entrypoints(app: "Starlette") -> None:
    """对比 app.routes 与 LEDGER_IMPORT_ENTRYPOINTS 的闭合性。

    Raises
    ------
    EntrypointValidationError
        存在未注册的导入相关路由，或已注册路由不在 app.routes 中。
    """
    # 收集 app 中实际注册的路由路径
    registered_paths: set[str] = set()
    for entry in LEDGER_IMPORT_ENTRYPOINTS:
        registered_paths.add(_normalize_path(entry.path))

    # 扫描 app.routes
    actual_import_paths: set[str] = set()
    all_app_paths: set[str] = set()

    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        if path is None:
            # 可能是 Mount 或其他包装器
            for sub_route in getattr(route, "routes", []):
                sub_path = getattr(sub_route, "path", None)
                if sub_path:
                    # Mount 前缀 + sub_route.path
                    prefix = getattr(route, "path", "")
                    full = prefix.rstrip("/") + "/" + sub_path.lstrip("/")
                    norm = _normalize_path(full)
                    all_app_paths.add(norm)
                    if _is_ledger_import_path(full):
                        actual_import_paths.add(norm)
            continue
        norm = _normalize_path(path)
        all_app_paths.add(norm)
        if _is_ledger_import_path(path):
            actual_import_paths.add(norm)

    unregistered = sorted(actual_import_paths - registered_paths)
    missing = sorted(registered_paths - all_app_paths)

    if unregistered or missing:
        raise EntrypointValidationError(unregistered=unregistered, missing=missing)
