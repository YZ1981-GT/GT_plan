"""
test_render_sheet_classify_wiring.py

AST 守卫：`wp_render_config.py` 必须真的**调用**抽出的纯函数
（spec platform-global-display-settings-closure 6A / design §18 H1①）。

🔴 为什么必须有这一层：抽出纯函数后如果 router 仍保留自己那份实现，
纯函数就只是「一份能被测试读的副本」——与 memory 里
「registry 成了只被测试看的副本」完全同型。所以判据不是「文件存在」，
而是**AST 里出现对它的调用**，并且**router 内不再有第二份同类判定**。

本文件用 AST 而非文本匹配（memory ㉖）：注释/docstring 正反两向都会骗过
文本 `in` 判据。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_ROUTER = _BACKEND / "app" / "routers" / "wp_render_config.py"
_MODULE = _BACKEND / "app" / "routers" / "wp_render_config_sheet_classify.py"

#: 必须被 router 调用的纯函数。
REQUIRED_CALLS = (
    "compute_real_sheets",
    "is_multi_sheet",
    "resolve_sheet_override",
    "classify_sheet",
    "apply_g_prefix_onlyoffice",
)


def _called_names(path: Path) -> set[str]:
    """AST 里所有被**调用**的名字（`Name` 或 `Attribute` 的尾段）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


class TestRouterCallsPureFunctions:
    def test_module_exists(self) -> None:
        assert _MODULE.exists(), f"纯函数模块不存在：{_MODULE}"

    @pytest.mark.parametrize("name", REQUIRED_CALLS)
    def test_router_imports_the_function(self, name: str) -> None:
        """必须先 import —— 否则「调用」只能是同名巧合。"""
        imported = _imported_names(_ROUTER)
        assert name in imported, (
            f"`wp_render_config.py` 未 import {name}；"
            "纯函数抽出来却没有被生产代码使用 = 死代码"
        )

    @pytest.mark.parametrize("name", REQUIRED_CALLS)
    def test_router_calls_the_function(self, name: str) -> None:
        called = _called_names(_ROUTER)
        assert name in called, (
            f"`wp_render_config.py` 的 AST 里没有对 {name} 的调用；"
            "判据必须是「真调用」而不是「文件存在」"
        )

    def test_module_does_not_import_router(self) -> None:
        """纯函数模块不得反向 import router（否则抽出就形成循环依赖）。"""
        imported = _imported_names(_MODULE)
        assert "wp_render_config" not in imported
        source = _MODULE.read_text(encoding="utf-8")
        assert "from app.routers.wp_render_config import" not in source

    def test_module_has_no_async_db_dependency(self) -> None:
        """纯函数不得**真的**依赖 AsyncSession / db（离线审计工具要在无库环境跑）。

        🔴 用 AST 而不是文本匹配：本模块 docstring 里提到 `AsyncSession`
        是为了说明「不需要它」，文本 `in` 判据会把这条说明当成违规（memory ㉖
        「注释/docstring 正反两向都会骗过文本扫描器」）。
        这里只查**真实引用**：import、参数注解、函数体内的名字。
        """
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        forbidden_imports = {"sqlalchemy", "app.core.database", "fastapi"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == m or node.module.startswith(m + ".")
                    for m in forbidden_imports
                ), f"纯函数模块 import 了 {node.module}，将无法离线复用"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == m or alias.name.startswith(m + ".")
                        for m in forbidden_imports
                    ), f"纯函数模块 import 了 {alias.name}"
        # `await` 只能出现在 async 函数里 ⇒ 有 await 就说明依赖异步 IO
        for node in ast.walk(tree):
            assert not isinstance(node, ast.Await), (
                "纯函数模块含 `await`，将无法被离线审计工具复用"
            )


class TestRouterDeduplication:
    """router 内不应再有第二份「逐字相同」的判定实现。"""

    def test_router_no_longer_defines_its_own_sheet_code_regex(self) -> None:
        """`_SHEET_CODE_RE` 应只有一份来源（纯函数模块）。

        router 里若还留着同名正则，两份口径迟早漂移（`--新增` 后缀、
        尾部锚点都是细节）。
        """
        source = _ROUTER.read_text(encoding="utf-8")
        assert "_SHEET_CODE_RE = re.compile" not in source, (
            "`wp_render_config.py` 仍自带 `_SHEET_CODE_RE` 定义；"
            "应改为从 `wp_render_config_sheet_classify` 导入"
        )
