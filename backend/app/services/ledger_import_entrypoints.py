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
        # 🔴 只登记**确认**返回 410 的端点。`/api/projects/{project_id}/import` 原先也登记成
        #    retired，但它实际仍 `POST` 并执行完整导入（`data_import.upload_and_import`，
        #    带 data_type / on_duplicate 参数，配套 preview / batches 一整套）。
        #    登记成 retired = 错标；本轮按现状改登为 preview（真实行为），
        #    该旧链是否正式退役需单独裁决（见 spec 复核记录 §范围外）。
        #    新判据 `_collect_retired_not_410` 会让这类错标在下一次立刻打红。
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/account-chart/import",
            method="POST",
            kind="retired",
            description="旧同步科目表导入：固定 410 LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import",
            method="POST",
            kind="preview",
            description=(
                "旧通用数据导入（upload_and_import）：仍真实执行导入，"
                "执行前需先走 /import/preview 确认；待裁决是否正式退役"
            ),
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-data/incremental/apply",
            method="POST",
            kind="retired",
            description="旧增量覆盖：固定 410 INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB",
        ),
        # ── status (只读) ──
        # 🔴 2026-11-14 对真实 `app.routes` 现算校正（原先登记了 3 条不存在的路径，
        #    同时漏登记 18 条真实端点 ⇒ 注册表只是"被测试读的副本"）：
        #    删除凭空登记的 `/import/progress/{batch_id}`、`/import/rollback/{batch_id}`、
        #    `/ledger-import/status`（真实 app 里全不存在）。
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/active-job",
            method="GET",
            kind="status",
            description="最近一次导入作业（替代原 `/ledger-import/status` 虚构路径）",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/import/batches",
            method="GET",
            kind="status",
            description="旧导入批次列表",
        ),
        # ── recovery ──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/resume",
            method="POST",
            kind="recovery",
            description="从检查点恢复导入作业",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry",
            method="POST",
            kind="recovery",
            description="重试失败的导入作业",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/takeover",
            method="POST",
            kind="recovery",
            description="接管他人租约的导入作业",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/datasets/{dataset_id}/rollback",
            method="POST",
            kind="recovery",
            description="数据集回滚到上一版本",
        ),
        # ── job lifecycle（作业进度 / 取消 / 诊断）──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs",
            method="GET",
            kind="status",
            description="导入作业列表",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}",
            method="GET",
            kind="status",
            description="导入作业详情",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/cancel",
            method="POST",
            kind="status",
            description="取消导入作业",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/diagnostics",
            method="GET",
            kind="status",
            description="导入作业诊断信息",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/jobs/{job_id}/stream",
            method="GET",
            kind="status",
            description="导入作业进度流（SSE）",
        ),
        # ── dataset（数据集版本治理）──
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/datasets",
            method="GET",
            kind="status",
            description="数据集列表",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/datasets/active",
            method="GET",
            kind="status",
            description="当前 active 数据集",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/datasets/history",
            method="GET",
            kind="status",
            description="数据集历史",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/activation-records",
            method="GET",
            kind="status",
            description="数据集激活记录",
        ),
        LedgerImportEntrypoint(
            path="/api/projects/{project_id}/ledger-import/artifacts",
            method="GET",
            kind="status",
            description="导入产物（artifact）列表",
        ),
        # ── validation rules（导入校验规则目录，只读）──
        LedgerImportEntrypoint(
            path="/api/ledger-import/validation-rules",
            method="GET",
            kind="status",
            description="导入校验规则清单（全局，无项目上下文）",
        ),
        LedgerImportEntrypoint(
            path="/api/ledger-import/validation-rules/{code}",
            method="GET",
            kind="status",
            description="单条导入校验规则",
        ),
    }
)


# ── 校验 ──────────────────────────────────────────────────

class EntrypointValidationError(Exception):
    """入口注册表与实际路由不一致。"""

    def __init__(
        self,
        *,
        unregistered: list[str],
        missing: list[str],
        retired_not_410: list[str] | None = None,
    ) -> None:
        self.unregistered = unregistered
        self.missing = missing
        self.retired_not_410 = retired_not_410 or []
        parts: list[str] = []
        if unregistered:
            parts.append(f"未注册的导入相关路由: {unregistered}")
        if missing:
            parts.append(f"已注册但未挂载的路由: {missing}")
        if self.retired_not_410:
            parts.append(
                "登记为 retired 但处理函数不返回 410: "
                f"{self.retired_not_410}"
            )
        super().__init__("; ".join(parts))


def _normalize_path(path: str) -> str:
    """将 Starlette 路径模板中的参数名归一化（仅保留花括号结构）。

    例: /api/projects/{project_id}/import/progress/{batch_id}
    →  /api/projects/{}/import/progress/{}
    """
    import re as _re

    return _re.sub(r"\{[^}]+\}", "{}", path)


def _is_ledger_import_path(path: str) -> bool:
    """判断一个路由路径是否属于账套导入相关域。

    🔴 2026-11-14 实测收窄：原判据 `normalized.rstrip("/").endswith("/import")
    and "/projects/" in normalized` 会把**任何**项目级 import 抓进来 ——
    对真实 app 跑出 22 条假阳（`adjustments/import`、`bulk-tab/import`、
    `review-workflow/{}/import`、`account-chart/import-reset`、
    `ledger-import/validation-rules` 等全是别的业务域）。
    假阳会让人以为注册表严重欠登记，实际是判据太宽 ——
    而「扫描器命中 ≠ 本域有缺陷」（memory 铁律 ㉒）。

    现在的口径：
    - 精确等于「项目根 + /import」（只有这一条是旧通用导入）；
    - 或落在明确的账套/科目表导入子路径下；
    - `import-templates` / `import-intelligence` / `*-reset` / 其他域的
      `adjustments|bulk-tab|review-workflow|…` 一律排除。
    """
    normalized = path.lower()

    # ── 明确排除：这些不是账套导入域 ──
    excluded_markers = (
        "/import-templates",
        "/import-intelligence",
        "-reset",
        "/adjustments/",
        "/bulk-tab/",
        "/review-workflow/",
        "/account-chart/import-async",  # 虽属导入，但由 submit 语义单独登记判定
    )
    if any(m in normalized for m in excluded_markers):
        # import-async 在注册表里是 submit，仍需参与「已登记是否存在」比对，
        # 但不必参与「未登记」扫描（它本来就在注册表里）。
        return "/account-chart/import-async" in normalized

    # ── 账套 / 科目表导入的明确子路径 ──
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
    if any(kw in normalized for kw in keywords):
        return True

    # ── 精确：项目根下的旧通用导入 /api/projects/{project_id}/import ──
    stripped = normalized.rstrip("/")
    return stripped.endswith("/projects/{project_id}/import") or (
        stripped.endswith("/import") and "/projects/{}" in stripped.replace("{project_id}", "{}")
        and stripped.count("/") == 5
    )


def _endpoint_raises_410(endpoint: object) -> bool | None:
    """判定一个端点处理函数是否**无条件**以 410 结束。

    返回三态，**缺省为 None（无法判定）** —— 这一点很关键：
    既有测试用 `SimpleNamespace` 造假路由，这类对象没有 `endpoint`，
    若把「取不到」当成「不是 410」就会把一批正确用例误判成红
    （本轮实测：改了判据后 9 条既有用例里 2 条立刻假红）。

    用 AST 而不是文本匹配（memory 铁律 ㉖：注释 / docstring 正反两向
    都会骗过文本扫描器）。判据取「函数体第一条有效语句就是
    `raise HTTPException(status_code=410)`」：只看第一条，是因为
    「先做业务、末尾某个分支才 410」不算退役（那条路径仍然在写数据）。
    """
    import ast
    import inspect
    import textwrap

    if not callable(endpoint):
        return None

    target = inspect.unwrap(endpoint)
    try:
        source = textwrap.dedent(inspect.getsource(target))
    except (OSError, TypeError):
        # 取不到源码（C 实现 / 动态生成 / 假路由）：无法判定，交给上层跳过
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    func = next(
        (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )
    if func is None:
        return None

    body = [n for n in func.body if not isinstance(n, ast.Expr)]  # 跳过 docstring
    if not body:
        return False
    first = body[0]
    if not isinstance(first, ast.Raise) or first.exc is None:
        return False

    call = first.exc
    if not isinstance(call, ast.Call):
        return False
    func_name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
    if func_name != "HTTPException":
        return False

    for kw in call.keywords:
        if kw.arg != "status_code":
            continue
        val = kw.value
        if isinstance(val, ast.Constant) and val.value == 410:
            return True
        if isinstance(val, ast.Attribute) and val.attr == "GONE":
            return True
    return False


def _collect_retired_not_410(app: "Starlette") -> list[str]:
    """找出登记为 retired、但处理函数**确定**不返回 410 的路径。

    这是 spec platform-global-display-settings-closure 任务 8 的核心缺口：
    `validate_entrypoints` 原先只校验「路径存在」，于是
    `/account-chart/import` 明明还 `POST` 且真的执行导入写入，登记表却写
    `kind="retired"` —— 两边自相矛盾而校验全绿（复核记录模式②）。

    无法判定（假路由 / 取不到源码）的项不计入，避免把测试替身判成缺陷。
    """
    retired_paths = {
        _normalize_path(e.path): e.path
        for e in LEDGER_IMPORT_ENTRYPOINTS
        if e.kind == "retired"
    }
    if not retired_paths:
        return []

    offenders: list[str] = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        candidates = []
        if path is None:
            for sub in getattr(route, "routes", []):
                sub_path = getattr(sub, "path", None)
                if not sub_path:
                    continue
                prefix = getattr(route, "path", "") or ""
                candidates.append(
                    (prefix.rstrip("/") + "/" + sub_path.lstrip("/"), sub)
                )
        else:
            candidates.append((path, route))

        for full, r in candidates:
            norm = _normalize_path(full)
            if norm not in retired_paths:
                continue
            endpoint = getattr(r, "endpoint", None)
            verdict = _endpoint_raises_410(endpoint)
            if verdict is False:  # 只有「确定不是 410」才判红
                offenders.append(retired_paths[norm])
    return sorted(set(offenders))


def validate_entrypoints(app: "Starlette") -> None:
    """对比 app.routes 与 LEDGER_IMPORT_ENTRYPOINTS 的闭合性。

    Raises
    ------
    EntrypointValidationError
        存在未注册的导入相关路由、已注册路由不在 app.routes 中，
        或登记为 `retired` 的端点其实并不返回 410。
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
    retired_not_410 = _collect_retired_not_410(app)

    if unregistered or missing or retired_not_410:
        raise EntrypointValidationError(
            unregistered=unregistered,
            missing=missing,
            retired_not_410=retired_not_410,
        )
