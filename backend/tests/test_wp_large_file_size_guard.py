"""底稿模块大文件拆分守卫（P0 / pass3）

断言 3 个 pass3 目标文件拆分后 ≤800 行；同时断言 pass2 已达标文件未回升超 800
（防止拆分误伤已瘦身链路）。

拆分前红灯（3 目标超标），拆分后全绿。
"""
from __future__ import annotations

import os

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_LIMIT = 800

# pass3 拆分目标：模块或其转包后的 __init__.py
_TARGETS = [
    "app/routers/working_paper.py",
    "app/services/workpaper_fill_service.py",
    # auto_data_resolvers 转包后核对包的 __init__.py；转包前核对单文件
    ["app/services/auto_data_resolvers.py", "app/services/auto_data_resolvers/__init__.py"],
]

# pass4 拆分目标（服务层 3 文件）
_TARGETS_PASS4 = [
    "app/services/wp_template_init_service.py",
    "app/services/wp_standard_conversion_service.py",
    "app/services/wp_fine_rule_engine.py",
]

# pass2 已达标，绝不能因本次拆分回升超标
_MUST_STAY_SMALL = [
    "app/routers/wp_render_config.py",
    "app/services/wp_classification_service.py",
    "app/routers/wp_template_files.py",
    "app/routers/wp_template_xlsx.py",
    "app/routers/wp_template_docx.py",
]


def _line_count(rel: str) -> int:
    fp = os.path.join(_BACKEND, rel)
    with open(fp, encoding="utf-8") as f:
        return sum(1 for _ in f)


def _resolve(target) -> str | None:
    """返回实际存在的相对路径（支持单文件或包 __init__ 两种形态）。"""
    candidates = target if isinstance(target, list) else [target]
    for rel in candidates:
        if os.path.isfile(os.path.join(_BACKEND, rel)):
            return rel
    return None


def test_pass3_target_files_within_limit():
    """3 个 pass3 目标文件（或其转包 __init__）行数 ≤800。"""
    violations = []
    for target in _TARGETS:
        rel = _resolve(target)
        assert rel is not None, f"目标文件不存在: {target}"
        n = _line_count(rel)
        if n > _LIMIT:
            violations.append(f"{rel}: {n} 行 > {_LIMIT}")
    assert not violations, "以下 pass3 目标文件仍超标:\n" + "\n".join(f"  {v}" for v in violations)


def test_pass2_files_not_regressed():
    """pass2 已达标文件未因拆分回升超过 800 行。"""
    violations = []
    for rel in _MUST_STAY_SMALL:
        if os.path.isfile(os.path.join(_BACKEND, rel)):
            n = _line_count(rel)
            if n > _LIMIT:
                violations.append(f"{rel}: {n} 行 > {_LIMIT}")
    assert not violations, "pass2 已达标文件意外回升超标:\n" + "\n".join(f"  {v}" for v in violations)


def test_pass4_target_files_within_limit():
    """3 个 pass4 服务层目标文件行数 ≤800（拆分前红灯，拆分后全绿）。"""
    violations = []
    for rel in _TARGETS_PASS4:
        assert os.path.isfile(os.path.join(_BACKEND, rel)), f"目标文件不存在: {rel}"
        n = _line_count(rel)
        if n > _LIMIT:
            violations.append(f"{rel}: {n} 行 > {_LIMIT}")
    assert not violations, "以下 pass4 目标文件仍超标:\n" + "\n".join(f"  {v}" for v in violations)
