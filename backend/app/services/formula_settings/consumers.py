"""各域有效定义的生产读取入口登记与 wired 派生（ADR-FHIC-22）。

``READER_ENTRIES`` 写死每个域的有效定义读取函数（模块路径 + 函数名）。
``wired_domains()`` 返回入口非空且在 ``backend/app``（排除 ``formula_settings``
包与 ``routers/formula_settings.py``）中至少被一个生产模块调用的域。

通用 ``effective_slots`` 是目录 / 依赖面板读全部域的入口，不计为读者。
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Sequence

# ── 读取入口登记 ──────────────────────────────────────────────────────────────

#: 每个域的有效定义读取入口。值为 ``(模块路径, 函数名)`` 元组的元组。
#: tb_detail 无读者 ⇒ 空元组。
READER_ENTRIES: dict[str, tuple[tuple[str, str], ...]] = {
    "report": (
        ("app.services.formula_settings.effective_report", "load_effective_report_configs"),
    ),
    "push": (
        ("app.services.formula_settings.push_settings", "effective_push_rules"),
    ),
    "consol_note": (
        ("app.services.formula_settings.consol_note_settings", "effective_formulas"),
    ),
    "cross_check": (
        ("app.services.formula_settings.cross_check_rules", "run_user_rules"),
    ),
    "note": (
        ("app.services.formula_settings.note_settings", "materialize_quietly"),
    ),
    "wp": (
        ("app.services.formula_settings.wp_effective", "init_prefill_overrides"),
        ("app.services.formula_settings.wp_effective", "overlay_prefill_formulas"),
    ),
    "tb_detail": (),
}


def _function_names(entries: Sequence[tuple[str, str]]) -> frozenset[str]:
    """提取入口函数名集合。"""
    return frozenset(name for _, name in entries)


def _scan_callers(func_names: frozenset[str], app_root: Path) -> bool:
    """AST 扫描 ``backend/app`` 下的 .py 文件（排除 formula_settings 包与路由），
    判断 *func_names* 中至少有一个被生产模块引用。

    只认 ``ast.Name``（直接名字引用）和 ``ast.Attribute``（属性末段），
    不计 ``effective_slots``。
    """
    excluded_dir = app_root / "services" / "formula_settings"
    excluded_file = app_root / "routers" / "formula_settings.py"
    for dirpath, _dirnames, filenames in os.walk(app_root):
        dp = Path(dirpath)
        # 排除 formula_settings 包
        if dp == excluded_dir or excluded_dir in dp.parents:
            continue
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = dp / fname
            if fpath == excluded_file:
                continue
            try:
                tree = ast.parse(fpath.read_bytes(), filename=str(fpath))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in func_names:
                    return True
                if isinstance(node, ast.Attribute) and node.attr in func_names:
                    return True
    return False


def wired_domains(*, app_root: Path | None = None) -> set[str]:
    """返回入口非空且在生产代码中被调用的域。

    *app_root* 默认按本文件位置推导：
    ``backend/app/services/formula_settings/consumers.py`` → ``backend/app``。
    """
    if app_root is None:
        app_root = Path(__file__).resolve().parent.parent.parent  # services → app
    result: set[str] = set()
    for domain, entries in READER_ENTRIES.items():
        if not entries:
            continue
        names = _function_names(entries)
        if _scan_callers(names, app_root):
            result.add(domain)
    return result
