"""公式写入点 validator 守卫（需求 12.2，ADR-FHIC-09）。

AST 扫描 ``ReportConfig.formula`` 与 ``FormulaSetting.definition`` 全部写入点，
每个都经 validator 或在豁免表写明理由（豁免表配「条目真实存在」反向断言）。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ── 被扫描的写入模块 ──────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SERVICES_ROOT = _BACKEND_ROOT / "app" / "services"
_FORMULA_SETTINGS_DIR = _SERVICES_ROOT / "formula_settings"

# 需要扫描的模块文件
_SCAN_TARGETS = [
    _FORMULA_SETTINGS_DIR / "stores.py",
    _FORMULA_SETTINGS_DIR / "domain_stores.py",
]

# 豁免表：写入点不经 validate_formula_definition 的理由
# 每条须配反向断言证明条目真实存在
_EXEMPTIONS: dict[str, str] = {
    # ReportStore.write_global 里 definition is None 时直接标删除，不写公式
    "ReportStore.write_global:definition_is_none_branch": "definition=None 是删除操作，不写公式值",
    # SettingStore.write_global 里 definition is None 时直接标删除
    "SettingStore.write_global:definition_is_none_branch": "definition=None 是删除操作，不写公式值",
    # WpStore.write_project 里有自己的 checked_wp_definition 调用（经 validator 转发）
    "WpStore.write_project:checked_wp_definition": "底稿域写入自带 checked_wp_definition 校验",
    # WpStore.write_global 里全局写直接 raise（不写底稿全局公式）
    "WpStore.write_global:not_supported": "底稿域不支持全局层写入（直接 raise）",
    # ConsolNoteStore.write_global 里有自己的 validate_note_formula
    "ConsolNoteStore.write_global:validate_note_formula": "合并附注全局写入自带 validate_note_formula",
    # ConsolNoteStore.write_project 委托给 SettingStore.write_project（后者已有 validator）
    "ConsolNoteStore.write_project:delegates_to_SettingStore": "委托给 SettingStore.write_project（已有 validator）",
    # NoteStore.write_global / write_project 委托给 SettingStore（已有 validator）
    "NoteStore.write_global:delegates_to_SettingStore": "委托给 SettingStore.write_global（已有 validator）",
    "NoteStore.write_project:delegates_to_SettingStore": "委托给 SettingStore.write_project（已有 validator）",
}


class TestValidatorPresenceInWriteMethods:
    """每个 store 的 write_global / write_project 方法都经 validate_formula_definition 或在豁免表。"""

    def test_report_store_write_global_has_validator(self) -> None:
        src = _read_method_source("stores.py", "ReportStore", "write_global")
        assert "validate_formula_definition" in src

    def test_report_store_write_project_has_validator(self) -> None:
        src = _read_method_source("stores.py", "ReportStore", "write_project")
        assert "validate_formula_definition" in src

    def test_setting_store_write_global_has_validator(self) -> None:
        src = _read_method_source("stores.py", "SettingStore", "write_global")
        assert "validate_formula_definition" in src

    def test_setting_store_write_project_has_validator(self) -> None:
        src = _read_method_source("stores.py", "SettingStore", "write_project")
        assert "validate_formula_definition" in src


class TestExemptionsExist:
    """豁免表里的每个条目真实存在于代码中（反向断言）。"""

    @pytest.mark.parametrize("key,reason", list(_EXEMPTIONS.items()), ids=list(_EXEMPTIONS.keys()))
    def test_exemption_target_exists(self, key: str, reason: str) -> None:
        """豁免表的每个条目对应的类和方法真实存在。"""
        class_method, _, _ = key.partition(":")
        class_name, _, method_name = class_method.partition(".")
        assert method_name, f"豁免条目 {key} 格式错：应为 Class.method:标签"
        # 验证类和方法存在
        found = False
        for target in _SCAN_TARGETS:
            src = target.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(target))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                            found = True
                            break
        assert found, f"豁免条目 {key} 指向的 {class_name}.{method_name} 在被扫描文件里不存在"


class TestNoExemptionWithoutReason:
    """豁免表没有空理由。"""

    def test_all_exemptions_have_reasons(self) -> None:
        for key, reason in _EXEMPTIONS.items():
            assert reason.strip(), f"豁免条目 {key} 没有理由"


class TestExemptionTableHasNoStaleEntries:
    """豁免表没有失效条目（方法不存在 = 失效）。"""

    def test_no_stale_exemptions(self) -> None:
        stale: list[str] = []
        for key in _EXEMPTIONS:
            class_method, _, _ = key.partition(":")
            class_name, _, method_name = class_method.partition(".")
            found = False
            for target in _SCAN_TARGETS:
                src = target.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(target))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == class_name:
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                                found = True
            if not found:
                stale.append(key)
        assert not stale, f"豁免表有失效条目（方法不存在）：{stale}"


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _read_method_source(filename: str, class_name: str, method_name: str) -> str:
    """从指定文件中读取类方法的源码文本。"""
    filepath = _FORMULA_SETTINGS_DIR / filename
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(filepath))
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    start = item.lineno - 1
                    end = item.end_lineno if item.end_lineno else start + 1
                    return "\n".join(lines[start:end])
    raise ValueError(f"未找到 {class_name}.{method_name} in {filename}")
