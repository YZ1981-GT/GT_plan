#!/usr/bin/env python
"""守卫：依赖 setup 上下文的 composable 不得在函数体内调用。

## 背景（2026-07-30 J1 实证）

`useAuditContext()` 内部用 `useRoute()`（`inject`）+ `onScopeDispose()`，
**只能在 `<script setup>` 顶层同步调用**。J1 两个披露 Tab 历史实现写成：

    async function syncToDisclosureNotes() {
      const { body } = buildJ1SyncPayload({ ..., year: useAuditContext().year.value })
      await http.post(...)
    }

点击时 `inject` 拿不到 route → `route.params` 上 TypeError → **在 `http.post` 之前
就抛错，零网络请求**，只弹一句「同步失败」。两个 Tab 的同步按钮与自动同步
**一直是死的**（库里 `_last_sync_at` 恒 NULL），而 vitest 与 `get_diagnostics`
全绿查不出 —— 只有浏览器实测能发现。故用静态扫描兜住整个前端。

## 判定方法

对每个 `.vue` 的 `<script setup>`：去注释与字符串 → 用大括号深度 + 「函数起始」
识别函数体区间 → 若受管 composable 的调用点落在任一函数体内即报错。

顶层 `const x = useAuditContext()`、以及作为**顶层语句的实参**
（如 `useAdjudicationBringIn({ year: useAuditContext().year })`）都判为安全。

Usage::

    python backend/scripts/check/check_setup_scoped_composables.py
    python backend/scripts/check/check_setup_scoped_composables.py --json

spec: .kiro/specs/j1-disclosure-template-alignment/（Task 17 横向推广）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
SRC = _REPO / "audit-platform" / "frontend" / "src"

# 受管 composable：内部依赖 inject / effect scope，只能在 setup 顶层同步调用
SETUP_SCOPED = (
    "useAuditContext",
    "useRoute",
    "useRouter",
    "useDisplayPrefsStore",
)

# 允许在函数体内调用的例外（写明理由；例外应尽量为空）
ALLOWLIST: dict[str, str] = {}


def _blank_comments_and_strings(code: str) -> str:
    """把注释与字符串替换成同长度空白（保持下标不变，便于定位行号）。"""
    out = list(code)
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "*":
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if ch == "/" and nxt == "/":
            j = code.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            j = i + 1
            while j < n:
                if code[j] == "\\":
                    j += 2
                    continue
                if code[j] == quote:
                    j += 1
                    break
                j += 1
            for k in range(i, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


_FUNC_START = re.compile(
    r"(?:\bfunction\b\s*\*?\s*[\w$]*\s*\([^()]*\)\s*(?::[^{;=]+)?\s*\{)"  # function foo() {
    r"|(?:\)\s*=>\s*\{)"  # ) => {
    r"|(?:\b[\w$]+\s*=>\s*\{)"  # x => {
)


def _function_body_ranges(code: str) -> list[tuple[int, int]]:
    """返回全部函数体的 `[开括号下标, 闭括号下标)` 区间（含嵌套，取并集即可判定）。"""
    ranges: list[tuple[int, int]] = []
    for m in _FUNC_START.finditer(code):
        open_idx = code.rindex("{", m.start(), m.end())
        depth = 0
        for i in range(open_idx, len(code)):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    ranges.append((open_idx, i))
                    break
    return ranges


def _named_function_body(clean: str, name: str) -> tuple[int, int] | None:
    """定位 `function name(` / `const name = ... => {` 的函数体区间。"""
    pat = re.compile(
        rf"(?:\b(?:async\s+)?function\s+{re.escape(name)}\s*\()"
        rf"|(?:\bconst\s+{re.escape(name)}\s*=\s*(?:async\s*)?\()"
    )
    m = pat.search(clean)
    if not m:
        return None
    open_idx = clean.find("{", m.end())
    if open_idx < 0:
        return None
    depth = 0
    for i in range(open_idx, len(clean)):
        if clean[i] == "{":
            depth += 1
        elif clean[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_idx, i)
    return None


def scan_file(path: Path) -> list[dict[str, object]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<script setup[^>]*>([\s\S]*?)</script>", raw)
    if not m:
        return []
    body = m.group(1)
    offset = m.start(1)
    clean = _blank_comments_and_strings(body)
    ranges = _function_body_ranges(clean)
    rel = str(path.relative_to(_REPO)).replace("\\", "/")

    offenders: list[dict[str, object]] = []

    # ── 规则 1：setup 作用域 composable 不得在函数体内调用 ──
    for name in SETUP_SCOPED:
        for call in re.finditer(rf"\b{name}\s*\(", clean):
            idx = call.start()
            if not any(a < idx < b for a, b in ranges):
                continue
            if f"{rel}:{name}" in ALLOWLIST:
                continue
            offenders.append(
                {
                    "rule": "setup-scoped",
                    "file": rel,
                    "detail": f"{name}()",
                    "line": raw.count("\n", 0, offset + idx) + 1,
                }
            )

    # ── 规则 2：同步函数不得调度自己（自触发重复 POST） ──
    span = _named_function_body(clean, "syncToDisclosureNotes")
    if span is not None:
        a, b = span
        for call in re.finditer(r"scheduleAutoSync\s*\(", clean[a:b]):
            idx = a + call.start()
            if f"{rel}:self-schedule" in ALLOWLIST:
                continue
            offenders.append(
                {
                    "rule": "self-schedule",
                    "file": rel,
                    "detail": "syncToDisclosureNotes 内 scheduleAutoSync()",
                    "line": raw.count("\n", 0, offset + idx) + 1,
                }
            )
    return offenders


def main() -> int:
    ap = argparse.ArgumentParser(
        description="守卫：setup 作用域 composable 不得在函数体内调用"
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--path", default="components/workpaper", help="相对 src 的扫描子目录")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    root = SRC / args.path
    files = sorted(root.rglob("*.vue"))
    offenders: list[dict[str, object]] = []
    for f in files:
        offenders.extend(scan_file(f))

    if args.json:
        print(json.dumps({"scanned": len(files), "offenders": offenders}, ensure_ascii=False, indent=2))
        return 1 if offenders else 0

    print(f"扫描 {len(files)} 个 .vue（{args.path}）")
    if not offenders:
        print("[OK] 无违规：setup 作用域调用与同步自触发两项检查均通过")
        return 0

    scoped = [o for o in offenders if o["rule"] == "setup-scoped"]
    selfsched = [o for o in offenders if o["rule"] == "self-schedule"]

    if scoped:
        print(f"\n[FAIL] {len(scoped)} 处在函数体内调用 setup 作用域 composable：")
        for o in scoped:
            print(f"  {o['file']}:{o['line']}  {o['detail']}")
        print(
            "  → 运行时 inject 失效 → TypeError → 整个处理器在发请求前抛错，"
            "功能静默全废（vitest / get_diagnostics 查不出）。"
            "\n  修法：提到 <script setup> 顶层，如 "
            "`const { year: auditYear } = useAuditContext()`，处理器只读 .value。"
        )
    if selfsched:
        print(f"\n[FAIL] {len(selfsched)} 处同步函数调度自己（自触发）：")
        for o in selfsched:
            print(f"  {o['file']}:{o['line']}  {o['detail']}")
        print(
            "  → 手动同步成功后 800ms 再发一次同样的 POST，用户会收到莫名的失败提示。"
            "\n  修法：删掉该行；自动同步只由**数据变更**触发"
            "（增删行 / 从明细带入 / AI 写入 / persistXxx）。"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
