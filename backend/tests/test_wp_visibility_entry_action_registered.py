"""守卫：`enforce_attachment_wp_visibility` / `gate_wp` / `try_gate_wp` 调用点传的
(entrypoint, action) 必须在 Action_Matrix 里登记。

## 为什么需要

`WpBoundGate` 的九维键里 entrypoint 与 action 各占一维，**两者都要命中同一条完整允许项**。
调用点如果把 entrypoint 写成矩阵里没有的名字（如 `attachment.rollback`），或把 action 写成
该 entrypoint 登记之外的动作（如 DELETE 端点传 `attach_read`），九维键就永不命中 ⇒
`_match_grants` 恒空 ⇒ **任何用户（含 admin）都拿到 404**，而端点看起来「有鉴权」。

2026-11-16 实测到两处这种错配（spec platform-performance-residual-findings-closure 走查批）：

- `DELETE /api/attachments/{id}` 传 `action="attach_read"` + `entrypoint="attachment.delete"`
  ⇒ 矩阵登记的是 `("attachment.delete", "DELETE", "attach_delete")` ⇒ 附件删除按钮从未可用。
- `POST /api/attachments/{id}/versions/{vid}/rollback` 传 `entrypoint="attachment.rollback"`
  ⇒ 矩阵里根本没有这个 entrypoint（版本回滚登记为 `version.restore`）⇒ 恒 404。

## 口径

纯 AST（memory 铁律 ㉖：注释 / docstring 会骗过文本匹配）：
  1. 找函数名在 `_GATED_CALLS` 里的 `Call` 节点；
  2. 取关键字实参里的 `entrypoint=` / `action=` 字符串字面量；
  3. 逐对断言 `(entrypoint, action)` 命中 `ActionMatrix` 的登记集合。

只认字面量：变量拼出来的值静态判不了，登记在 `_DYNAMIC_ALLOWLIST` 并注明原因（只许删不许加）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# 走 WpBoundGate 且要求 (entrypoint, action) 同时命中的入口。
_GATED_CALLS = frozenset({
    "enforce_attachment_wp_visibility",
    "gate_wp",
    "try_gate_wp",
})

# 动态拼参的调用点（文件相对路径 → 原因）。空集合 = 全部静态可判。
_DYNAMIC_ALLOWLIST: dict[str, str] = {}


def _iter_py_files() -> list[Path]:
    return sorted(p for p in APP_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _literal_kwarg(call: ast.Call, name: str) -> str | None:
    """取 `name=<str literal>` 的值；非字面量返回 None。"""
    for kw in call.keywords:
        if kw.arg != name:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
        return None
    return None


def _has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _collect_call_sites() -> list[tuple[str, int, str, str]]:
    """(相对路径, 行号, entrypoint, action)；只收两者都是字面量的调用。"""
    out: list[tuple[str, int, str, str]] = []
    for path in _iter_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # 语法错由别的守卫管，这里不重复报
            continue
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name not in _GATED_CALLS:
                continue
            ep = _literal_kwarg(node, "entrypoint")
            action = _literal_kwarg(node, "action")
            if ep is None or action is None:
                continue
            out.append((rel, node.lineno, ep, action))
    return out


def _registered_pairs() -> set[tuple[str, str]]:
    from app.security.coverage_guard import matrix_registered_pairs

    return matrix_registered_pairs()


def test_guard_finds_call_sites() -> None:
    """分母非空：扫不到调用点说明扫描口径坏了（不是「全部合规」）。"""
    sites = _collect_call_sites()
    assert len(sites) >= 10, f"只扫到 {len(sites)} 个静态调用点，扫描口径可能已失效"
    # 抽样自检：确认解析出的是真实调用（不是随便抓了个同名函数）
    files = {s[0] for s in sites}
    assert any("attachments.py" in f for f in files), f"未扫到 attachments.py：{sorted(files)[:5]}"


def test_every_entrypoint_action_pair_is_registered() -> None:
    """每个调用点传的 (entrypoint, action) 都必须在 Action_Matrix 登记。

    失败信息直接给出「矩阵里该 entrypoint 登记了哪些 action」，便于定位是
    entrypoint 写错还是 action 写错。
    """
    registered = _registered_pairs()
    by_entrypoint: dict[str, set[str]] = {}
    for ep, action in registered:
        by_entrypoint.setdefault(ep, set()).add(action)

    bad: list[str] = []
    for rel, lineno, ep, action in _collect_call_sites():
        if rel in _DYNAMIC_ALLOWLIST:
            continue
        if (ep, action) in registered:
            continue
        known = by_entrypoint.get(ep)
        if known is None:
            hint = "矩阵里没有这个 entrypoint"
        else:
            hint = f"该 entrypoint 登记的动作是 {sorted(known)}"
        bad.append(f"{rel}:{lineno} entrypoint={ep!r} action={action!r} → {hint}")

    assert bad == [], (
        "以下调用点的 (entrypoint, action) 未在 Action_Matrix 登记 ⇒ WpBoundGate 九维键永不命中，"
        "任何用户（含 admin）都会拿到 404：\n  " + "\n  ".join(bad)
    )


def test_dynamic_allowlist_entries_still_exist() -> None:
    """豁免清单不许留失效条目（文件已不存在或已无动态调用）。"""
    sites = _collect_call_sites()
    static_files = {s[0] for s in sites}
    stale = [f for f in _DYNAMIC_ALLOWLIST if f not in static_files]
    assert stale == [], f"豁免清单里的文件已无静态调用点，应删除该条：{stale}"


@pytest.mark.parametrize(
    ("entrypoint", "method", "action", "expected"),
    [
        # 2026-11-16 修的三处：错误组合必须判否，修好的组合必须判是。
        ("attachment.delete", "DELETE", "attach_read", False),
        ("attachment.delete", "DELETE", "attach_delete", True),
        ("attachment.rollback", "POST", "attach_read", False),
        ("version.restore", "POST", "version_restore", True),
        ("ai_chat.project_attachment", "POST", "attach_read", False),
        ("attachment.read", "GET", "attach_read", True),
        # 既有正确组合（对照组，防止守卫变成「对任何输入都说 YES」）。
        ("attachment.upload", "POST", "attach_upload", True),
        ("attachment.unlink", "DELETE", "attach_associate", True),
    ],
)
def test_matrix_lookup_selfcheck(
    entrypoint: str, method: str, action: str, expected: bool,
) -> None:
    """机制自检：守卫依赖的 (entrypoint, method, action) 判定对已知正反例给出预期结果。"""
    from app.services.wp_visibility.action_matrix import (
        AK_ADMIN,
        UC_ADMIN,
        ActionMatrix,
        MatrixKey,
    )

    key = MatrixKey(
        user_class=UC_ADMIN,
        access_kind=AK_ADMIN,
        identity="admin",
        entrypoint=entrypoint,
        route=None,
        method=method,
        action=action,
        source_state="none",
        target_state="none",
    )
    assert (ActionMatrix.lookup(key) is not None) is expected, (
        f"({entrypoint}, {method}, {action}) 期望 registered={expected}"
    )
