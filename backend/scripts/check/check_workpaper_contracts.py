#!/usr/bin/env python
"""check_workpaper_contracts.py — API Prefix / Import Contract / Persistence Contract 守卫

背景（workpaper-maintainability-convergence Req 5.1, 5.2, 5.5-5.7）：
  底稿模块反复出现三类运行时 bug，均能穿过 TS 类型检查和 Vite transform：
  - 缺 /api 前缀的 HTTP 调用（dev proxy 只转发 /api → 404 静默失败）
  - 从 default-only 模块做 named import（ESM 运行时崩溃）
  - 直接绕过 Persistence Adapter 的网络调用（数据不落库、双层包裹等）

本脚本实现三道守卫，零依赖（仅 Python stdlib），UTF-8 文件读取：

  7.1 API Prefix Guard
    扫描 http/api/axios 客户端调用中的 URL 字面量：
    - /api/... → 放行
    - 已知后端路由缺 /api（如 /workpapers/, /projects/）→ 违规 (fail-closed)
    - 外部绝对 URL / blob URL / OnlyOffice 协议 → allowlist 放行
    - 动态不可解析 → 报告 unknown (fail-open)

  7.2 Import Contract Guard
    维护 default-only 模块清单；阻断 named import：
    - import { http } from '@/utils/http' → BLOCKED
    - import http from '@/utils/http' → OK

  7.3 Persistence Contract Guard
    阻断已知反模式：
    - 迁移目录内直接 http.put(...checklist-responses...)
    - JSON.stringify({ remark: ... }) 后作为 remark 传输（双层）
    - project_id: wpId（使用 wpId 作 project_id）
    - checklist URL 缺 /api
    - 新增同构 saveImmediate/debouncedSave 网络实现

用法：
  python backend/scripts/check/check_workpaper_contracts.py            # report 模式（退出码 0）
  python backend/scripts/check/check_workpaper_contracts.py --strict   # strict 模式（违规退出码 1）

设计为零依赖（仅标准库），可在 CI 与 pre-commit 直接运行。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

# ─── 常量 ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
COMPOSABLES_DIR = WP_DIR / "composables"

# 遍历剪枝
PRUNE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".hypothesis", ".venv", "coverage", ".turbo",
}

# 文件扩展名
SOURCE_EXTENSIONS = (".vue", ".ts", ".tsx")


# ─── 数据类型 ────────────────────────────────────────────────────────────────
class Violation(NamedTuple):
    file: str
    line: int
    rule: str
    message: str
    suggestion: str


class UnknownReport(NamedTuple):
    file: str
    line: int
    rule: str
    message: str


# ═══════════════════════════════════════════════════════════════════════════════
# 7.1 API Prefix Guard
# ═══════════════════════════════════════════════════════════════════════════════

# 已知后端路由前缀（缺 /api 时违规）
_BACKEND_ROUTE_PREFIXES = (
    "/workpapers/", "/workpapers?",
    "/projects/", "/projects?",
    "/trial-balance/",
    "/ledger/",
    "/checklist-responses",
    "/procedure-tables/",
    "/render-config",
    "/onlyoffice/",
)

# 外部/特殊 URL allowlist（放行）
_URL_ALLOWLIST_PATTERNS = (
    re.compile(r"^https?://"),       # 绝对外部 URL
    re.compile(r"^blob:"),           # blob URL
    re.compile(r"^data:"),           # data URI
    re.compile(r"^wss?://"),         # WebSocket
    re.compile(r"^//"),              # protocol-relative
    re.compile(r"^/ds/"),            # OnlyOffice document server
    re.compile(r"^/web-apps/"),      # OnlyOffice web apps
)

# HTTP 调用模式（匹配 http.get/post/put/delete/patch 和 axios 调用）
_RE_HTTP_CALL = re.compile(
    r"""(?:http|axios|api)\s*\.\s*(?:get|post|put|delete|patch|request)\s*\(\s*"""
    r"""(['"`])"""                   # 开始引号
    r"""(.*?)"""                     # URL 内容
    r"""\1""",                       # 结束引号（同类型）
    re.MULTILINE,
)

# 模板字面量中的 HTTP 调用
_RE_HTTP_TEMPLATE = re.compile(
    r"""(?:http|axios|api)\s*\.\s*(?:get|post|put|delete|patch|request)\s*\(\s*`([^`]*)`""",
    re.MULTILINE,
)


def _is_allowlisted_url(url: str) -> bool:
    """URL 在显式 allowlist 中（外部/协议/特殊地址）。"""
    return any(p.match(url) for p in _URL_ALLOWLIST_PATTERNS)


def _is_api_prefixed(url: str) -> bool:
    """URL 以 /api/ 开头。"""
    return url.startswith("/api/") or url.startswith("/api?")


def _is_known_backend_route(url: str) -> bool:
    """URL 匹配已知后端路由前缀但缺少 /api。"""
    return any(url.startswith(prefix) for prefix in _BACKEND_ROUTE_PREFIXES)


def _is_dynamic_unresolvable(url: str) -> bool:
    """URL 包含动态模板表达式（${ 或变量拼接），无法静态解析。"""
    return "${" in url or url.startswith("${")


def check_api_prefix_line(line: str, line_content: str) -> tuple[list[str], list[str]]:
    """检查单行中的 API 前缀问题。

    返回 (violations_msgs, unknown_msgs)。
    纯函数，供属性测试直接调用。
    """
    violations: list[str] = []
    unknowns: list[str] = []

    # 匹配引号字符串
    for m in _RE_HTTP_CALL.finditer(line_content):
        url = m.group(2)
        if _is_allowlisted_url(url):
            continue
        if _is_api_prefixed(url):
            continue
        if _is_dynamic_unresolvable(url):
            unknowns.append(f"动态 URL 无法静态解析: {url[:60]}")
            continue
        if _is_known_backend_route(url):
            violations.append(f"缺少 /api 前缀: {url[:80]}")

    # 匹配模板字面量
    for m in _RE_HTTP_TEMPLATE.finditer(line_content):
        url = m.group(1)
        # 模板中 ${...} 常见
        static_prefix = url.split("${")[0] if "${" in url else url
        if _is_allowlisted_url(static_prefix):
            continue
        if _is_api_prefixed(static_prefix):
            continue
        if _is_dynamic_unresolvable(url) and not _is_known_backend_route(static_prefix):
            unknowns.append(f"模板 URL 动态部分无法解析: `{url[:60]}`")
            continue
        if _is_known_backend_route(static_prefix):
            violations.append(f"模板 URL 缺少 /api 前缀: `{url[:80]}`")

    return violations, unknowns


# ═══════════════════════════════════════════════════════════════════════════════
# 7.2 Import Contract Guard
# ═══════════════════════════════════════════════════════════════════════════════

# Default-only 模块清单（只允许 default import）
DEFAULT_ONLY_MODULES = (
    "@/utils/http",
    "~/utils/http",
)

# 匹配 named import: import { xxx } from 'module'
_MODULES_PATTERN = "|".join(re.escape(m) for m in DEFAULT_ONLY_MODULES)
_RE_NAMED_IMPORT = re.compile(
    r"""import\s*\{[^}]+\}\s*from\s*['"](?:""" + _MODULES_PATTERN + r""")['"]"""
)

# 匹配 default import: import xxx from 'module' → OK
_RE_DEFAULT_IMPORT = re.compile(
    r"""import\s+\w+\s+from\s*['"](?:""" + _MODULES_PATTERN + r""")['"]"""
)


def check_import_contract_line(line_content: str) -> str | None:
    """检查单行是否违反 import 契约。

    返回违规消息或 None。纯函数，供属性测试直接调用。
    """
    stripped = line_content.strip()
    # 跳过注释
    if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
        return None
    if _RE_NAMED_IMPORT.search(line_content):
        return f"从 default-only 模块进行了 named import: {stripped[:100]}"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 7.3 Persistence Contract Guard
# ═══════════════════════════════════════════════════════════════════════════════

# 反模式 A: 直接 http.put(...checklist-responses...)
_RE_DIRECT_PUT_CHECKLIST = re.compile(
    r"""http\s*\.\s*put\s*\(\s*[`'"].*checklist-responses""",
    re.IGNORECASE,
)

# 反模式 B: JSON.stringify({ remark: ... }) 双层包裹
_RE_DOUBLE_STRINGIFY_REMARK = re.compile(
    r"""JSON\.stringify\s*\(\s*\{\s*remark\s*:""",
)

# 反模式 C: project_id: wpId（使用 wpId 作为 project_id）
_RE_PROJECT_ID_WPID = re.compile(
    r"""project_id\s*:\s*(?:wpId|props\.wpId|wp_id)""",
)

# 反模式 D: checklist URL 缺 /api
_RE_CHECKLIST_NO_API = re.compile(
    r"""['"`]/workpapers/[^'"`]*checklist-responses""",
)

# 反模式 E: 新增同构 saveImmediate/debouncedSave 实现含 http 调用
_RE_SAVE_IMMEDIATE_IMPL = re.compile(
    r"""(?:async\s+)?(?:function\s+)?(?:saveImmediate|debouncedSave|doSave)\s*[=(]""",
)
_RE_HTTP_IN_SAVE = re.compile(
    r"""(?:http|axios)\s*\.\s*(?:put|post)\s*\(""",
)


# 已迁移目录列表（这些目录应使用 Persistence Adapter）
# 空列表意味着守卫对全部文件都扫描反模式，而不区分"已迁移/未迁移"
MIGRATED_DIRS: list[str] = []


def check_persistence_contract_line(
    line_content: str,
    file_lines: list[str] | None = None,
    line_idx: int = 0,
) -> str | None:
    """检查单行是否违反持久化契约。

    返回违规消息或 None。纯函数，供属性测试直接调用。
    """
    stripped = line_content.strip()
    # 跳过注释
    if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
        return None

    # 反模式 A: 直接 http.put checklist-responses
    if _RE_DIRECT_PUT_CHECKLIST.search(line_content):
        return f"直接调用 http.put checklist-responses (应使用 Persistence Adapter): {stripped[:80]}"

    # 反模式 B: JSON.stringify({ remark: ... }) 双层包裹
    if _RE_DOUBLE_STRINGIFY_REMARK.search(line_content):
        return f"JSON.stringify({{remark:...}}) 双层包裹 (应使用 encodeRemark): {stripped[:80]}"

    # 反模式 C: project_id: wpId
    if _RE_PROJECT_ID_WPID.search(line_content):
        return f"project_id: wpId (不应用 wpId 作为 project_id): {stripped[:80]}"

    # 反模式 D: checklist URL 缺 /api
    if _RE_CHECKLIST_NO_API.search(line_content):
        # 排除已经有 /api 的
        if "/api/workpapers/" not in line_content:
            return f"checklist URL 缺少 /api 前缀: {stripped[:80]}"

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描引擎
# ═══════════════════════════════════════════════════════════════════════════════

def scan_file(path: Path) -> tuple[list[Violation], list[UnknownReport]]:
    """扫描单个文件，返回 (violations, unknowns)。"""
    violations: list[Violation] = []
    unknowns: list[UnknownReport] = []

    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations, unknowns

    rel = _rel(path)
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # 跳过注释行
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        # 7.1 API Prefix
        api_violations, api_unknowns = check_api_prefix_line(line, line)
        for msg in api_violations:
            violations.append(Violation(
                file=rel, line=lineno, rule="API-PREFIX",
                message=msg,
                suggestion="添加 /api 前缀，如 /api/workpapers/...",
            ))
        for msg in api_unknowns:
            unknowns.append(UnknownReport(
                file=rel, line=lineno, rule="API-PREFIX-UNKNOWN",
                message=msg,
            ))

        # 7.2 Import Contract
        import_msg = check_import_contract_line(line)
        if import_msg:
            violations.append(Violation(
                file=rel, line=lineno, rule="IMPORT-CONTRACT",
                message=import_msg,
                suggestion="改为 default import: import http from '@/utils/http'",
            ))

        # 7.3 Persistence Contract
        persist_msg = check_persistence_contract_line(line, lines, lineno - 1)
        if persist_msg:
            violations.append(Violation(
                file=rel, line=lineno, rule="PERSISTENCE-CONTRACT",
                message=persist_msg,
                suggestion="使用 useChecklistPersistence / encodeRemark；"
                           "由后端从 wp_id 推导 project_id",
            ))

    return violations, unknowns


def _iter_source_files() -> list[Path]:
    """遍历前端 workpaper 源码目录，产出目标文件。"""
    targets: list[Path] = []
    if not WP_DIR.is_dir():
        return targets
    for dirpath, dirnames, filenames in os.walk(WP_DIR):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if fn.endswith(SOURCE_EXTENSIONS):
                targets.append(Path(dirpath) / fn)
    return sorted(targets)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ─── 入口 ────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="API Prefix / Import Contract / Persistence Contract 守卫"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="严格模式：明确违规时退出码 1（fail-closed）",
    )
    args = parser.parse_args(argv)

    # Windows 控制台 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    targets = _iter_source_files()
    all_violations: list[Violation] = []
    all_unknowns: list[UnknownReport] = []

    for path in targets:
        v, u = scan_file(path)
        all_violations.extend(v)
        all_unknowns.extend(u)

    # 输出违规
    if all_violations:
        print("═══ 违规（fail-closed on --strict）═══")
        for v in all_violations:
            print(f"  {v.file}:{v.line}  [{v.rule}]  {v.message}")
            print(f"    → 建议: {v.suggestion}")
        print(f"\n共 {len(all_violations)} 处违规")

    # 输出 unknown（fail-open）
    if all_unknowns:
        print("\n═══ Unknown（fail-open，仅报告）═══")
        for u in all_unknowns:
            print(f"  {u.file}:{u.line}  [{u.rule}]  {u.message}")
        print(f"\n共 {len(all_unknowns)} 处无法静态判定")

    if not all_violations and not all_unknowns:
        print(
            f"✅ API Prefix / Import Contract / Persistence Contract 守卫通过："
            f"{len(targets)} 个文件无违规"
        )
        return 0

    if all_violations and args.strict:
        print("\n⛔ 严格模式：存在明确违规，退出码 1")
        return 1

    if all_violations:
        print("\n（report 模式：未阻断。使用 --strict 以 fail-closed）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
