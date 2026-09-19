"""判据模块（`_test_*_criteria.py`）可编译性守卫

## 立项直因（2026-08-21 实测）

`backend/tests/` 下有 5 个 `_test_*_criteria.py`，是为绕过 pre-commit 的 800 行
门禁而从用例文件拆出的判据层。其中 **4 个存在同一个语法错误**：

    SyntaxError: from __future__ imports must occur at the beginning of the file

真因是拆分脚本把「原文件 docstring」原样贴在它自己写的说明 docstring 之后，
模块顶层因此出现**两个字符串字面量**。Python 只允许 future import 之前存在
一个 docstring（外加注释与空行），第二个字符串是普通表达式语句，future import
就不再位于文件开头。

## 为什么必须有这条守卫

这个 bug 的危害不是「测试失败」，而是**测试根本没跑却看不出来**：
4 个 criteria 文件被 6 个用例文件 import，collection 阶段就炸，
**138 条守卫断言长期零执行**，而 CI 里表现为 collection error 混在
一大堆输出里，很容易被当成环境问题跳过。修复后 collected 从
39374(+6 errors) 变成 39512(0 errors)，多出的 138 条正是这些。

这属于 memory 记载的假绿形态：守卫存在但从未执行。

## 判据形态

- 用 `compile()` 真编译，不是 grep「文件里有没有 from __future__」。
- 顶层 docstring 数量用 `ast` 结构判定，不用字符串计数。
- 覆盖面是**目录扫描得来的全集**，新增 criteria 文件自动纳入，
  不维护手写清单（漏名就等于不设防）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TESTS_ROOT = Path(__file__).resolve().parent

# 覆盖面 = 目录扫描全集。新增 criteria 文件自动进入守卫，无需改本文件。
_CRITERIA_FILES = sorted(_TESTS_ROOT.rglob("_test_*_criteria.py"))


def test_criteria_files_discovered():
    """自检：扫描本身必须有产出，否则后面的参数化会空转成假绿。"""
    assert _CRITERIA_FILES, (
        "未发现任何 _test_*_criteria.py —— 若判据层已整体重命名，"
        "请同步更新本守卫的扫描模式，不要留一个空转的参数化"
    )


@pytest.mark.parametrize("path", _CRITERIA_FILES, ids=lambda p: p.name)
def test_criteria_module_compiles(path: Path):
    """每个判据模块必须能编译。

    编译失败 = 其全部断言零执行，且用例文件在 collection 阶段就 ERROR。
    """
    src = path.read_text(encoding="utf-8")
    try:
        compile(src, str(path), "exec")
    except SyntaxError as exc:
        pytest.fail(
            f"{path.name} 无法编译：{exc.msg}（line {exc.lineno}）\n"
            f"若是 'from __future__ imports must occur at the beginning of the file'，"
            f"检查模块顶层是否有两个 docstring（拆分脚本的已知缺陷）"
        )


@pytest.mark.parametrize("path", _CRITERIA_FILES, ids=lambda p: p.name)
def test_criteria_module_has_single_top_docstring(path: Path):
    """模块顶层只允许一个 docstring。

    第二个字符串字面量会成为表达式语句，把 future import 挤出文件开头。
    这里用 AST 判定，而不是数 `\"\"\"` 出现次数 —— 后者会被正文里的引号骗到。
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        pytest.skip("编译已在 test_criteria_module_compiles 中报红，此处不重复")

    bare_strings = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert len(bare_strings) <= 1, (
        f"{path.name} 顶层有 {len(bare_strings)} 个裸字符串字面量（应 ≤1）。"
        f"多余的那个会把 from __future__ 挤出文件开头，"
        f"导致整个模块 collection 阶段 SyntaxError、其断言零执行。"
        f"修法是合并 docstring，不要删正文。"
    )


@pytest.mark.parametrize("path", _CRITERIA_FILES, ids=lambda p: p.name)
def test_future_import_is_first_statement_when_present(path: Path):
    """若模块用了 `from __future__`，它必须是首条语句。

    这是对上一条的正向补充：上一条禁「多余字符串」，这条直接锁「位置」，
    两条一起把该 bug 的两种表现形式都盖住。
    """
    src = path.read_text(encoding="utf-8")
    if "from __future__" not in src:
        pytest.skip("该模块未使用 future import")

    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        pytest.skip("编译已在 test_criteria_module_compiles 中报红，此处不重复")

    # 跳过模块 docstring 后的第一条语句
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]

    assert body, f"{path.name} 除 docstring 外没有任何语句"
    first = body[0]
    assert isinstance(first, ast.ImportFrom) and first.module == "__future__", (
        f"{path.name} 的 from __future__ 不是首条语句，"
        f"实际首条是 {type(first).__name__}（line {first.lineno}）"
    )
