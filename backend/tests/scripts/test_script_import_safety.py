"""守卫：被测试 import 的 `scripts.*` 模块不得带破坏性 import 副作用。

🔴 2026-09-28 立此判据的由来：`scripts/e2e/seed_fix_projects.py` 在**模块级**执行
```python
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
```
只要 pytest 进程 import 它，pytest 的 capture 对象就被换掉，teardown 时
`readouterr()` 撞 `ValueError: I/O operation on closed file` —— **整个测试会话崩在
收尾**，且报错位置在 `_pytest/capture.py`，完全看不出是哪个模块干的。

后果是连锁的：因为"不能 import"，`test_seed_fix_f2_e2e.py` 当初只能**手抄**一份
`F2_E2E_WP_CODES`；权威源后来加了 `F2-29`，手抄那份没跟 ⇒ 恒红。
根因修复 = 把控制台重绑移进 `main()`，同时立本守卫防复发。

分母如实声明（现算）：`backend/tests/**` 里被 import 的 `scripts.*` 模块 33 个，
`backend/scripts/**` 里模块级重绑 stdout/stderr 的脚本 10 个，两者交集当前为 **0**。
交集为零不等于判据没用——它守的正是"把某个 CLI 脚本拿来 import"这一步。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPTS = _BACKEND / "scripts"
_TESTS = _BACKEND / "tests"

_IMPORT_RE = re.compile(r"(?:from|import)\s+(scripts(?:\.[\w.]+)?)")


def _module_level_stdout_rebinds(source: str) -> list[int]:
    """模块级（含顶层 `if` / `try` 分支内）重绑 `sys.stdout` / `sys.stderr` 的行号。

    只看**顶层**：函数体内重绑是 CLI 的正当做法（`main()` 里改），不算违规。
    """
    tree = ast.parse(source)
    hits: list[int] = []

    def scan(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr in {"stdout", "stderr"}
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "sys"
                    ):
                        hits.append(node.lineno)
            elif isinstance(node, (ast.If, ast.Try)):
                scan(node.body)
                scan(list(getattr(node, "orelse", []) or []))
                for handler in getattr(node, "handlers", []) or []:
                    scan(handler.body)
                scan(list(getattr(node, "finalbody", []) or []))

    scan(tree.body)
    return hits


def _modules_imported_by_tests() -> set[str]:
    found: set[str] = set()
    for path in _TESTS.rglob("test_*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.update(_IMPORT_RE.findall(text))
    return found


def _dotted(path: Path) -> str:
    rel = path.relative_to(_SCRIPTS).with_suffix("")
    return "scripts." + rel.as_posix().replace("/", ".")


def test_tests_actually_import_some_scripts_modules():
    """结构性零守卫：扫描器必须真的扫到 import（否则"零违规"可能是扫不到）。"""
    imported = _modules_imported_by_tests()
    assert len(imported) >= 10, imported
    # 锚点：本轮涉及的三个模块确实在集合里，证明正则口径有效
    for anchor in (
        "scripts.e2e.seed_fix_projects",
        "scripts.check.workpaper_component_manifest",
        "scripts.validate_report_body_template",
    ):
        assert anchor in imported, f"{anchor} 未被识别 —— import 扫描口径失效"


def test_no_test_imported_script_rebinds_stdout_at_module_level():
    imported = _modules_imported_by_tests()
    offenders: list[str] = []
    scanned = 0
    for path in sorted(_SCRIPTS.rglob("*.py")):
        dotted = _dotted(path)
        if dotted not in imported:
            continue
        scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        try:
            lines = _module_level_stdout_rebinds(source)
        except SyntaxError:  # pragma: no cover
            continue
        if lines:
            offenders.append(f"{dotted} lines={lines}")

    assert scanned >= 10, f"只扫到 {scanned} 个被 import 的脚本 —— 口径可能失效"
    assert offenders == [], (
        "以下脚本被测试 import 却在模块级重绑 sys.stdout/stderr，"
        "会替换 pytest capture 导致会话 teardown 崩溃；"
        f"请把重绑移进 main()：{offenders}"
    )


def test_seed_fix_projects_is_import_safe_and_exposes_constants():
    """回归：权威源模块必须可安全 import 并暴露常量（本轮根因修复的正面判据）。"""
    from scripts.e2e.seed_fix_projects import F2_E2E_WP_CODES, F2_WP_TEMPLATE_FILES

    assert F2_E2E_WP_CODES, "清单为空"
    assert set(F2_E2E_WP_CODES) <= set(F2_WP_TEMPLATE_FILES), "有 wp_code 缺模板映射"

    source = (_SCRIPTS / "e2e" / "seed_fix_projects.py").read_text(encoding="utf-8")
    assert _module_level_stdout_rebinds(source) == [], "模块级重绑又回来了"
    # 重绑逻辑必须仍然存在（只是搬进函数）——否则 CLI 在 GBK 终端会乱码
    assert "_force_utf8_console" in source
    assert "sys.stdout = io.TextIOWrapper" in source


@pytest.mark.parametrize(
    ("snippet", "expected_hits"),
    [
        # 模块级裸赋值 —— 必须命中
        ("import sys\nsys.stdout = object()\n", 1),
        # 顶层 if 分支内 —— 也是 import 时执行，必须命中
        (
            "import sys\nif sys.platform == 'win32':\n    sys.stdout = object()\n",
            1,
        ),
        # 顶层 try 内 —— 同样 import 时执行
        ("import sys\ntry:\n    sys.stderr = object()\nexcept Exception:\n    pass\n", 1),
        # 函数体内 —— CLI 的正当做法，不得命中
        ("import sys\ndef main():\n    sys.stdout = object()\n", 0),
        # 只是读取，不是重绑 —— 不得命中
        ("import sys\nprint(sys.stdout)\n", 0),
        # 同名但不是 sys —— 不得命中
        ("class F:\n    stdout = None\nf = F()\nf.stdout = 1\n", 0),
    ],
)
def test_rebind_detector_both_directions(snippet, expected_hits):
    """双向变异：该命中的必须命中，不该命中的必须不命中。

    只做单向会把「在 main() 里重绑」的正确脚本判成违规。
    """
    assert len(_module_level_stdout_rebinds(snippet)) == expected_hits
