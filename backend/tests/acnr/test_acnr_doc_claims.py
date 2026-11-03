"""ACNR 模块文档里的「存在性说法」与代码一致（段四审计 F4-13 / A5）。

1. `backend/app/services/acnr/**/*.py` 的文档字符串与注释（tokenize 取 COMMENT / 文档字符串，
   不扫代码）里点名的测试（`test_xxx` 或 `tests/.../test_xxx.py`）必须真实存在：
   要么 backend/tests 下有同名测试文件，要么某个测试文件里定义了同名 test_ 函数（AST）。
   ——此前 catalog.py / catalog_release.py 注释引用了从未存在的 test_only_generator_writes_catalog。
2. exact_identity 模块文档写「生产代码里只有发布门禁 catalog_release 导入它」，这句话必须与
   AST 现算的生产导入方一致；T10 等接入新的使用者后，本用例会要求同步更新文档。
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
import warnings
from functools import lru_cache
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_ACNR = _BACKEND / "app" / "services" / "acnr"
_TESTS = _BACKEND / "tests"
_TEST_REF_RE = re.compile(r"\b(test_[a-z0-9_]+)(?:\.py)?\b")


def _doc_and_comment_text(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    parts: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            parts.append(tok.string)
    tree = ast.parse(src)
    for node in [tree, *ast.walk(tree)]:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                parts.append(doc)
    return "\n".join(parts)


@lru_cache(maxsize=1)
def _test_files() -> tuple[tuple[Path, bytes], ...]:
    return tuple((p, p.read_bytes()) for p in _TESTS.rglob("test_*.py"))


@lru_cache(maxsize=None)
def _test_exists(name: str) -> bool:
    """同名测试文件，或某测试文件里定义了同名 test_ 函数（文本预筛 + AST 判定）。"""
    files = _test_files()
    if any(p.stem == name for p, _ in files):
        return True
    for p, raw in files:
        if name.encode() not in raw:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)  # 他人测试文件里的无效转义，与本判据无关
                tree = ast.parse(raw.decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in ast.walk(tree)):
            return True
    return False


def test_acnr_docs_only_reference_existing_tests():
    problems: list[str] = []
    files = sorted(_ACNR.rglob("*.py"))
    assert files, "扫描范围为空（防空转）"
    for p in files:
        for name in sorted(set(_TEST_REF_RE.findall(_doc_and_comment_text(p)))):
            if not _test_exists(name):
                problems.append(f"{p.relative_to(_BACKEND).as_posix()}: 引用了不存在的测试 {name}")
    assert not problems, "ACNR 模块文档引用了不存在的测试（守卫落地前不得引用）：\n" + "\n".join(problems)


def test_scanner_sees_existing_references():
    """防空转：已知真实存在的引用（catalog_integrity 文档点名的守卫）必须被扫到。"""
    text = _doc_and_comment_text(_ACNR / "catalog_integrity.py")
    assert "test_production_report_release_or_registered_legacy" in _TEST_REF_RE.findall(text)


def _production_importers(module: str) -> set[str]:
    hits: set[str] = set()
    for root in (_BACKEND / "app", _BACKEND / "scripts"):
        for p in root.rglob("*.py"):
            raw = p.read_bytes()
            if module.encode() not in raw:
                continue
            tree = ast.parse(raw.decode("utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom):
                    mods = [n.module or ""] + [a.name for a in n.names]
                elif isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                else:
                    continue
                if any(m == module or m.endswith("." + module) for m in mods):
                    hits.add(p.relative_to(_BACKEND).as_posix())
                    break
    return hits - {f"app/services/acnr/{module}.py"}


def test_exact_identity_doc_importer_claim_matches_ast():
    doc = ast.get_docstring(ast.parse((_ACNR / "exact_identity.py").read_text(encoding="utf-8"))) or ""
    claim = "生产代码里只有发布门禁 `catalog_release` 导入它" in doc
    importers = _production_importers("exact_identity")
    actual_only_release = importers == {"app/services/acnr/catalog_release.py"}
    assert claim == actual_only_release, (
        f"exact_identity 文档的导入方说法与 AST 现算不符：文档声称只有 catalog_release={claim}，"
        f"现算导入方={sorted(importers)}"
    )
