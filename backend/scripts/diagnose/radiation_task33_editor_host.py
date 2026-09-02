# -*- coding: utf-8 -*-
"""Task 33 辐射面：按 **import / 符号引用** 反查受本次改动影响的测试文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 33
Requirements: 14.7

## 为什么不跑全量

`backend/tests` 根下约 2285 个测试文件，前台跑数分钟无输出会被当成卡死；前端全量
同理。故只跑「真的引用了本次改动物」的文件 —— 判据是 **AST/import 级引用**，
不是词面搜索：`grep 'bridge'` 会把无关注释也算进来，而漏掉 `from '../x'` 这种相对路径。

## 改动物

* 新增 `WorkpaperSyncEditorHost.vue` / `workpaperSyncEditorHostRuntime.ts`
* 修改 `useWorkpaperSyncBridge.ts`（新增 `notifyHostFailure` 上报口）

## 用法

    py -3 backend/scripts/diagnose/radiation_task33_editor_host.py
    py -3 backend/scripts/diagnose/radiation_task33_editor_host.py --json <path>
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND_SRC = REPO / "audit-platform" / "frontend" / "src"
BACKEND_TESTS = REPO / "backend" / "tests"

#: 本次改动的前端模块（仓库相对，POSIX）。
CHANGED_FRONTEND = (
    "audit-platform/frontend/src/components/workpaper/sync/useWorkpaperSyncBridge.ts",
    "audit-platform/frontend/src/components/workpaper/sync/WorkpaperSyncEditorHost.vue",
    "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncEditorHostRuntime.ts",
)

#: 改动物的模块名（去扩展名），用于匹配 import 说明符的末段。
CHANGED_MODULE_NAMES = {
    "useWorkpaperSyncBridge",
    "WorkpaperSyncEditorHost",
    "workpaperSyncEditorHostRuntime",
}

#: 新增/改动的符号 —— 后端侧的跨文档判据是读**源码文本**的，故按符号名反查。
CHANGED_SYMBOLS = (
    "notifyHostFailure",
    "WorkpaperSyncEditorHost",
    "workpaperSyncEditorHostRuntime",
    "useWorkpaperSyncBridge",
)

#: 🔴 **不能**用 `(?:import|export)[^\n;]*?from` —— 平台里绝大多数 import 是多行大括号
#: 形态（`import {\n  A,\n  B,\n} from '...'`），禁换行的类字符集会把它们全漏掉。
#: 首轮实测就是这么漏的：`useWorkpaperSyncBridge.spec.ts` 明明 import 了改动物却没被反查到，
#: 只有单行 import 的 host spec 被找到 ⇒ 辐射面看起来「只有 1 个」。
#: 剥过注释之后，`from '<spec>'` 只可能出现在 import/export 语句里，故直接收全部。
_IMPORT_RE = re.compile(r"""\bfrom\s*(['"])([^'"]+)\1""")
_SIDE_EFFECT_RE = re.compile(r"""(?:^|\n)\s*import\s*(['"])([^'"]+)\1""")
_DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*(['"])([^'"]+)\1\s*\)""")


def _strip_ts_comments(text: str) -> str:
    """剥 `/* */`、`//`、`<!-- -->`。判据一律读剥过注释的源码。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|[^:])//[^\n]*", r"\1", text)


def _frontend_specifiers(path: Path) -> set[str]:
    body = _strip_ts_comments(path.read_text(encoding="utf-8", errors="replace"))
    found: set[str] = set()
    for pattern in (_IMPORT_RE, _SIDE_EFFECT_RE, _DYNAMIC_IMPORT_RE):
        found |= {match[1] for match in pattern.findall(body)}
    return found


def _resolves_to_changed(spec: str, source: Path) -> bool:
    """import 说明符是否指向改动物（相对路径按真实文件系统解析，别名按末段）。"""
    tail = spec.split("/")[-1]
    stem = tail.rsplit(".", 1)[0] if tail.endswith((".ts", ".vue")) else tail
    if stem not in CHANGED_MODULE_NAMES:
        return False
    if spec.startswith("."):
        base = (source.parent / spec).resolve()
        for candidate in (base, base.with_suffix(".ts"), base.with_suffix(".vue")):
            rel = candidate.relative_to(REPO).as_posix() if candidate.is_relative_to(REPO) else ""
            if rel in CHANGED_FRONTEND:
                return True
        return False
    # `@/...` 别名
    if spec.startswith("@/"):
        candidate = FRONTEND_SRC / spec[2:]
        for probe in (candidate, candidate.with_suffix(".ts"), candidate.with_suffix(".vue")):
            rel = probe.relative_to(REPO).as_posix() if probe.is_relative_to(REPO) else ""
            if rel in CHANGED_FRONTEND:
                return True
    return False


def frontend_radiation() -> list[str]:
    hits: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in (".ts", ".tsx", ".vue"):
            continue
        if not re.search(r"\.(spec|test)\.[cm]?tsx?$", path.name):
            continue
        for spec in _frontend_specifiers(path):
            if _resolves_to_changed(spec, path):
                hits.append(path.relative_to(REPO).as_posix())
                break
    return sorted(set(hits))


def backend_radiation() -> list[str]:
    """后端判据靠读前端源码做跨文档比对 ⇒ 按**字符串常量 + 符号名**的 AST 命中反查。"""
    hits: list[str] = []
    for path in BACKEND_TESTS.rglob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        literals: set[str] = set()
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.add(node.value)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        blob = " ".join(literals)
        if any(symbol in blob or symbol in names for symbol in CHANGED_SYMBOLS):
            hits.append(path.relative_to(REPO).as_posix())
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 33 辐射面反查")
    ap.add_argument("--json", metavar="PATH", help="结果落盘路径")
    args = ap.parse_args()

    fe = frontend_radiation()
    be = backend_radiation()
    print(f"[FE] 引用改动模块的前端测试文件 {len(fe)} 个")
    for item in fe:
        print(f"     {item}")
    print(f"[BE] 引用改动符号的后端测试文件 {len(be)} 个")
    for item in be:
        print(f"     {item}")
    if not fe and not be:
        print("[FAIL] 辐射面为空 —— 反查必然出错（改动物至少被自己的判据引用）")
        return 1
    if args.json:
        Path(args.json).write_text(
            json.dumps({"frontend": fe, "backend": be}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n结果已落盘：{args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
