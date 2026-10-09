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

🔴 2026-09-30 补盲区（原判据漏掉了唯一真实的违例）：本文件原先只按**点号形态**
（`from scripts.x import` / `import scripts.x`）找"被测试 import 的脚本"，据此宣称
"两者交集当前为 **0**"。实际交集不是 0 —— `tests/test_wp_template_index_lifecycle.py`
用**路径式动态加载**取脚本：

```python
spec = importlib.util.spec_from_file_location("...", BACKEND_ROOT / "scripts" / "ops" / "setup_wp_templates_dir.py")
```

点号正则看不见它，于是 `scripts/ops/setup_wp_templates_dir.py` 的模块级重绑一直在
判据视野之外。后果与立此判据时一模一样：那个测试文件的 7 个用例**从来没真正跑过**
（现象是 `EEEEEFF` 后崩在 `_pytest/capture.py`，不是失败）。

⇒ 本次把扫描口径扩成「点号 ∪ 路径式」，并为 `setup_wp_templates_dir` 补一条与
`seed_fix_projects` 同形的正面回归。**「交集为 0」这句话本身就是盲区的产物** ——
所以下面额外加了一条判据，要求路径式识别器在本仓至少命中 1 个真实站点，
免得口径再次悄悄失效。
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

#: 路径式动态加载：`"scripts" / "ops" / "setup_wp_templates_dir.py"` 这类由目录片段
#: 拼出来的脚本路径。取其**文件名主干**（脚本名），与磁盘脚本按 stem 匹配。
#: 不写成「解析整条 Path 表达式」——那要跑常量折叠，且各处基准目录变量名不一样
#: （`BACKEND_ROOT` / `_BACKEND` / `REPO`）；按 stem 匹配足够且不会漏。
_PATH_LOAD_RE = re.compile(r'"scripts"\s*(?:/\s*"[\w.\-]+"\s*)+')
_PY_STEM_RE = re.compile(r'"([\w\-]+)\.py"')


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


def _script_stems_path_loaded_by_tests() -> set[str]:
    """被测试**按路径**动态加载的脚本文件名主干集合（点号正则看不见的那一类）。"""
    found: set[str] = set()
    for path in _TESTS.rglob("test_*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for frag in _PATH_LOAD_RE.findall(text):
            found.update(_PY_STEM_RE.findall(frag))
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


def test_path_based_script_loading_is_detected():
    """结构性零守卫（针对新补的路径式口径）：它必须真的在本仓命中站点。

    🔴 这条是为了防「口径再次悄悄失效」而立：原判据的点号正则对
    `spec_from_file_location(... "scripts" / "ops" / "xxx.py")` 恒不命中，
    于是「零违规」其实是「没看见」。若将来有人改动测试写法使本识别器归零，
    这里会打红，逼着更新识别器而不是静默失去覆盖。
    """
    stems = _script_stems_path_loaded_by_tests()
    assert "setup_wp_templates_dir" in stems, (
        "路径式加载识别器抓不到 test_wp_template_index_lifecycle.py 里的 "
        f"setup_wp_templates_dir（现命中 {sorted(stems)}）⇒ 口径失效"
    )


def test_no_test_imported_script_rebinds_stdout_at_module_level():
    imported = _modules_imported_by_tests()
    path_loaded_stems = _script_stems_path_loaded_by_tests()
    offenders: list[str] = []
    scanned = 0
    for path in sorted(_SCRIPTS.rglob("*.py")):
        dotted = _dotted(path)
        if dotted not in imported and path.stem not in path_loaded_stems:
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


def _calls_inside(source: str, func_name: str) -> set[str]:
    """`func_name` 函数体内**实际调用**的名字集合（AST，不看注释/docstring）。"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return {
                sub.func.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            }
    return set()


def test_setup_wp_templates_dir_is_import_safe_and_still_forces_utf8():
    """回归：`setup_wp_templates_dir.py` 被路径式加载，重绑必须在函数里**且真被调用**。

    🔴 2026-09-30 根因修复的正面判据。它原先在模块级重绑 `sys.stdout`，而
    `tests/test_wp_template_index_lifecycle.py` 在**模块导入期**按路径加载它
    ⇒ pytest capture 被换掉、会话 teardown 崩 ⇒ 那 7 个用例从来没跑过。

    🔴 「搬进函数」有个配套陷阱：搬完**忘了在 `main()` 里调**。那样 import 安全了，
    但 CLI 在 GBK 终端重新乱码，且没有任何判据会红 —— 我本轮就先犯了一次。
    所以这里用 **AST** 断言 `main()` 体内真的有 `_force_utf8_console()` 调用
    （文本匹配会被 docstring 里提到函数名骗过去）。
    """
    source = (_SCRIPTS / "ops" / "setup_wp_templates_dir.py").read_text(encoding="utf-8")
    assert _module_level_stdout_rebinds(source) == [], "模块级重绑又回来了"
    assert "sys.stdout = io.TextIOWrapper" in source, (
        "重绑逻辑被整段删掉 ⇒ CLI 在 GBK 终端会乱码"
    )
    assert "_force_utf8_console" in _calls_inside(source, "main"), (
        "`_force_utf8_console` 定义了但 `main()` 没调用 ⇒ CLI 丢 UTF-8 输出"
    )


def test_seed_fix_projects_also_calls_its_console_helper():
    """同款反向锚点：2026-09-28 那次搬迁也必须真的在 `main()` 里调。

    两条一起立，`_calls_inside` 就有两个真实正样本 —— 免得它某天因 AST 口径变化
    恒返回空集而两条判据一起假绿。
    """
    source = (_SCRIPTS / "e2e" / "seed_fix_projects.py").read_text(encoding="utf-8")
    assert "_force_utf8_console" in _calls_inside(source, "main")


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
