"""底稿模块静默吞异常守卫测试。

扫描底稿 service + router + render 策略，检测"宽异常静默 handler"：
  - except 类型为 裸 / Exception / BaseException
  - body 为纯 pass 或 return 空值（None/{}/[]/""/0）
  - handler 内无任何 logger.* 调用

这类 handler 把真实故障（DB 超时、IO 失败、联动断裂）伪装成空数据，
违反项目铁律「禁 try/except:pass 吞异常」。本测试在 CI 阻断新增。

窄类型异常降级（except (ValueError, TypeError): ...）属合理用法，不在管辖范围。

Requirements: 3.1, 3.2, 3.3, 3.4
"""
from __future__ import annotations

import ast
import glob
import os

# 扫描范围：底稿模块
_BASE = os.path.join(os.path.dirname(__file__), "..", "app")
_PATTERNS = [
    os.path.join(_BASE, "services", "wp_*.py"),
    os.path.join(_BASE, "services", "workpaper_*.py"),
    os.path.join(_BASE, "services", "auto_data_resolvers.py"),
    os.path.join(_BASE, "routers", "wp_*.py"),
    os.path.join(_BASE, "routers", "working_paper.py"),
    os.path.join(_BASE, "routers", "wp_render_strategies", "*.py"),
]

# 确需静默的极少数例外：(相对 backend/ 的路径, 行号特征或函数名)。
# 每条须附理由注释。当前为空——70 处全部整改留痕。
_SILENT_EXCEPTION_WHITELIST: set[tuple[str, int]] = set()

_LOG_METHODS = {"warning", "error", "exception", "info", "debug", "critical"}


def _is_empty_body(handler: ast.ExceptHandler) -> bool:
    """body 仅为 pass 或 return 空值。"""
    if len(handler.body) != 1:
        return False
    stmt = handler.body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Return):
        v = stmt.value
        if v is None:
            return True
        if isinstance(v, ast.Constant) and v.value in (None, "", 0):
            return True
        if isinstance(v, ast.Dict) and not v.keys:
            return True
        if isinstance(v, ast.List) and not v.elts:
            return True
    return False


def _is_wide(handler: ast.ExceptHandler) -> bool:
    """裸 except / except Exception / except BaseException。"""
    t = handler.type
    if t is None:
        return True
    if isinstance(t, ast.Name):
        return t.id in ("Exception", "BaseException")
    return False


def _has_logger(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Attribute) and node.attr in _LOG_METHODS:
            return True
    return False


def _collect_files() -> list[str]:
    files: list[str] = []
    for p in _PATTERNS:
        files.extend(glob.glob(p))
    return sorted(set(files))


def _find_violations() -> list[tuple[str, int]]:
    violations: list[tuple[str, int]] = []
    backend_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    for fp in _collect_files():
        try:
            tree = ast.parse(open(fp, encoding="utf-8").read())
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _is_wide(node) and _is_empty_body(node) and not _has_logger(node):
                rel = os.path.relpath(fp, backend_root).replace("\\", "/")
                violations.append((rel, node.lineno))
    return violations


def test_no_silent_wide_exception_in_workpaper_module():
    """底稿模块不得存在无日志留痕的宽异常静默 handler。"""
    violations = _find_violations()
    unexpected = [v for v in violations if v not in _SILENT_EXCEPTION_WHITELIST]
    assert not unexpected, (
        f"发现 {len(unexpected)} 处静默吞异常（宽异常 + 纯 pass/return 空 + 无 logger）：\n"
        + "\n".join(f"  {f}:{ln}" for f, ln in unexpected)
        + "\n请补 logger.warning/debug 留痕，或加入 _SILENT_EXCEPTION_WHITELIST（附理由）。"
    )
