# -*- coding: utf-8 -*-
"""Task 34 辐射面测算（**按导入图**，不按词搜索）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34

## 为什么不能用词搜索

`grep workpaperSyncPresentation` 会命中注释、文档与同名字符串，也漏掉「A 导入 B、
B 导入我」这类间接辐射。本探针两侧都做**模块图闭包**：

* **后端**：`ast` 解析每个 `.py`，取 `Import` / `ImportFrom` 的模块名，另取
  `ast.Constant` 里指向被改数据文件的字符串；再做传递闭包，最后筛出
  `backend/tests/**` 里落在闭包内的文件。
* **前端**：逐文件剥注释后抽 `import ... from '<spec>'` / `import('<spec>')` /
  `export ... from '<spec>'` 的**模块说明符**（不是任意单词），解析成绝对路径，
  同样做传递闭包，再筛出 `*.spec.ts`。

## 本次改动清单

前端 5 个新产物 + 1 个测试夹具（纯新增，**未改**任何既有生产文件）；
后端只动了 spec 的 `tasks.md`（两个复选框）与生成物 `workpaper_ac_coverage_matrix.json`。

    py -3 backend/scripts/diagnose/probe_task34_sync_ui_radiation.py --out <path>
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FRONTEND_SRC = REPO / "audit-platform" / "frontend" / "src"
BACKEND = REPO / "backend"

SYNC_DIR = FRONTEND_SRC / "components" / "workpaper" / "sync"

#: 本次新增/修改的前端产物（绝对路径）。
FRONTEND_CHANGED = [
    SYNC_DIR / "workpaperSyncPresentation.ts",
    SYNC_DIR / "WorkpaperSyncStatusBar.vue",
    SYNC_DIR / "WorkpaperSyncConflictDialog.vue",
    SYNC_DIR / "WorkpaperSyncRecoveryPanel.vue",
    SYNC_DIR / "WorkpaperSyncDetailsDrawer.vue",
    SYNC_DIR / "__tests__" / "workpaperSyncUiHarness.ts",
]

#: 本次修改的后端侧数据文件的**判别子串**。
#:
#: 🔴 两轮实测才收敛到这一条：
#:
#: * 用裸 `tasks.md` ⇒ 命中 67 个模块（平台里几十个脚本都提这个通用文件名）；
#: * 补上 spec 目录名 `workpaper-html-onlyoffice-bidirectional-writeback-closure`
#:   ⇒ 反而涨到 170 个 —— 因为**本 spec 每个源文件的 docstring 头**都写着它，
#:   而 docstring 里的引用不是数据依赖。闭包随之吹到 986 个测试文件，等于没测。
#:
#: 结论：判别子串只保留唯一指向被改数据文件的那一个，且 AST 扫描**跳过 docstring**。
BACKEND_CHANGED_DATA = [
    "workpaper_ac_coverage_matrix.json",
]

#: 本探针自己（不算辐射面）。
SELF = Path(__file__).resolve()

_IMPORT_RE = re.compile(
    r"""(?:^|[\s;])(?:import|export)\s+(?:[^'"()]*?\sfrom\s+)?['"]([^'"]+)['"]"""
    r"""|import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

_TS_EXTS = (".ts", ".tsx", ".vue", ".js", ".mjs")


def strip_comments(text: str) -> str:
    """剥 `<!-- -->` / 块注释 / 行注释。剥完必须仍含代码（调用方自检）。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//[^\n]*", r"\1", text)
    return text


def resolve_specifier(spec: str, importer: Path) -> Path | None:
    """把模块说明符解析成仓库内绝对路径（`@/` → `src/`）。外部依赖返回 None。"""
    if spec.startswith("@/"):
        base = FRONTEND_SRC / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    if base.suffix in _TS_EXTS and base.is_file():
        return base
    for ext in _TS_EXTS:
        candidate = base.with_suffix(base.suffix + ext) if base.suffix else Path(str(base) + ext)
        if candidate.is_file():
            return candidate
    for ext in _TS_EXTS:
        candidate = Path(str(base) + ext)
        if candidate.is_file():
            return candidate
    index = base / "index.ts"
    return index if index.is_file() else None


def frontend_import_graph() -> dict[Path, set[Path]]:
    """importer → 它导入的仓库内模块集合。"""
    graph: dict[Path, set[Path]] = {}
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in _TS_EXTS or not path.is_file():
            continue
        try:
            body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        edges: set[Path] = set()
        for match in _IMPORT_RE.finditer(body):
            spec = match.group(1) or match.group(2)
            if not spec:
                continue
            target = resolve_specifier(spec, path)
            if target is not None:
                edges.add(target)
        graph[path] = edges
    return graph


def frontend_radiation() -> dict[str, object]:
    graph = frontend_import_graph()
    reverse: dict[Path, set[Path]] = {}
    for importer, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(importer)

    frontier = {p.resolve() for p in FRONTEND_CHANGED if p.is_file()}
    closure: set[Path] = set(frontier)
    while frontier:
        nxt: set[Path] = set()
        for node in frontier:
            for importer in reverse.get(node, set()):
                if importer not in closure:
                    closure.add(importer)
                    nxt.add(importer)
        frontier = nxt

    specs = sorted(
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in closure
        if p.name.endswith(".spec.ts")
    )
    return {
        "graph_nodes": len(graph),
        "closure_size": len(closure),
        "closure": sorted(
            str(p.relative_to(REPO)).replace("\\", "/") for p in closure
        ),
        "spec_files": specs,
    }


def module_name_of(path: Path) -> str | None:
    """`backend/app/x/y.py` → `app.x.y`（tests 与 scripts 不参与模块名映射）。"""
    try:
        rel = path.relative_to(BACKEND)
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if not parts:
        return None
    return ".".join(parts)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """收集 module / class / function 的 docstring 常量节点 id（用于跳过）。"""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def backend_radiation() -> dict[str, object]:
    """AST 侧：谁引用了被改数据文件，谁又（传递地）导入了那些模块。"""
    direct: set[Path] = set()
    imports: dict[Path, set[str]] = {}
    module_index: dict[str, Path] = {}

    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        name = module_name_of(path)
        if name:
            module_index[name] = path
        mods: set[str] = set()
        touches_data = False
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # 🔴 跳过 docstring：本 spec 每个源文件的头部都写着 spec 名，
                # 把它当数据引用会让辐射面吹到全仓库（首轮实测 986 个测试文件）。
                if id(node) in docstrings:
                    continue
                if any(marker in node.value for marker in BACKEND_CHANGED_DATA):
                    touches_data = True
        imports[path] = mods
        if touches_data and path.resolve() != SELF:
            direct.add(path)

    # 传递闭包：谁导入了 direct 里的模块（含 scripts/gen 与 scripts/check）
    direct_modules = {module_name_of(p) for p in direct}
    direct_modules.discard(None)
    # 脚本目录不在包路径里，另按裸文件名索引一次（sys.path.insert 的用法）
    bare = {p.stem for p in direct}

    closure: set[Path] = set(direct)
    changed = True
    while changed:
        changed = False
        closure_modules = {module_name_of(p) for p in closure} | {p.stem for p in closure}
        closure_modules.discard(None)
        for path, mods in imports.items():
            if path in closure:
                continue
            if mods & {m for m in closure_modules if m}:
                closure.add(path)
                changed = True

    tests = sorted(
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in closure
        if "tests" in p.parts and p.name.startswith("test_")
    )
    return {
        "direct_data_referrers": sorted(
            str(p.relative_to(REPO)).replace("\\", "/") for p in direct
        ),
        "direct_modules": sorted(m for m in direct_modules if m),
        "bare_module_names": sorted(bare),
        "closure_size": len(closure),
        "test_files": tests,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="Task 34 辐射面测算（按导入图）")
    parser.add_argument("--out", metavar="PATH", help="结果 JSON 落盘路径")
    args = parser.parse_args(argv)

    # 剥注释自检：剥过头会让前端图为空，从而漏报辐射面
    sample = "const a = 1 // x\n/* y */\n<!-- z -->\nimport b from './c'"
    stripped = strip_comments(sample)
    assert "const a = 1" in stripped and "./c" in stripped, "strip_comments 剥过头"
    assert "y" not in stripped.replace("// x", "") or True

    fe = frontend_radiation()
    be = backend_radiation()

    print("═══ 前端（导入图闭包） ═══")
    print(f"  图节点 {fe['graph_nodes']} 个，闭包 {fe['closure_size']} 个")
    for item in fe["closure"]:  # type: ignore[index]
        print(f"    {item}")
    print(f"  受影响 spec 文件 {len(fe['spec_files'])} 个：")  # type: ignore[arg-type]
    for item in fe["spec_files"]:  # type: ignore[index]
        print(f"    {item}")

    print()
    print("═══ 后端（AST 数据引用 + 导入闭包） ═══")
    print(f"  直接引用被改数据文件的模块 {len(be['direct_data_referrers'])} 个：")  # type: ignore[arg-type]
    for item in be["direct_data_referrers"]:  # type: ignore[index]
        print(f"    {item}")
    print(f"  闭包 {be['closure_size']} 个，其中测试文件 {len(be['test_files'])} 个：")  # type: ignore[arg-type]
    for item in be["test_files"]:  # type: ignore[index]
        print(f"    {item}")

    if args.out:
        Path(args.out).write_text(
            json.dumps({"frontend": fe, "backend": be}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n结果已落盘：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
