"""整对象替换 ``app.core.config.settings`` 的测试隔离守卫。

``patch("app.core.config.settings", mock)`` 只换配置模块上的那个属性；替换期间**首次**导入的模块，其模块级
``from app.core.config import settings`` 绑定到 Mock，补丁退出后也不会恢复（模块只导入一次）：

- ``test_wopi.py`` 曾在替换期间 ``from app.main import app``：单独跑时那是后端应用的首次导入，``main.py`` 的
  ``settings.CORS_ORIGINS.split(",")`` 当场 AttributeError（夹具设成了 list）⇒ 单独跑必失败，
  跟别的用例一起跑（应用已被先导入）才碰巧通过；
- ``test_task30_capabilities.py`` 在替换期间首次导入 ai_chat 包（67 个模块）：之后 ``app.core.security`` 与
  ``dsh_discovery`` 一直拿着 Mock（``DSH_VENDOR_ROOT`` 成了 Mock 拼的路径），同进程后面的用例跟着受影响。

判据：
1. 这两个文件各自在新进程里**单独**跑必须通过，且跑完没有任何 ``app.*`` 模块的模块级 ``settings`` 是 Mock；
2. 整对象替换 settings 的写法只许出现在下面登记的文件里（只许删）：新写法请改用
   ``monkeypatch.setattr(settings, "X", 值)`` 只改一个属性；确实要换整个对象，先在测试模块顶层导入被测模块，
   单独跑一次确认不泄漏，再登记。
"""
from __future__ import annotations

import ast
import functools
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
_TARGET = "app.core.config.settings"

#: 现有的整对象替换写法（2026-10-26 逐个单独跑确认：跑完 0 个模块拿着 Mock）。
_REGISTERED = frozenset({
    "tests/dsh_agent_panel/test_task30_capabilities.py",  # 已在模块顶层先导入被测模块
    "tests/dsh_agent_panel/test_task31_phase_c_gate.py",
    "tests/f2_extraction/test_f2_prefill_gray.py",
    "tests/test_audit_log_enhanced.py",
    "tests/test_dsh_discovery_task27.py",
    "tests/test_migration_runner_rollback.py",
    "tests/test_pgbouncer_connection.py",
    "tests/test_vector_store_equivalence_pbt.py",
    "tests/test_wp_evidence_collection.py",
})

#: 修过「单独跑失败 / 泄漏 Mock」的文件：每个都在新进程里单独跑一遍
_RUN_ALONE = ("tests/test_wopi.py", "tests/dsh_agent_panel/test_task30_capabilities.py")


# ── 静态：哪些文件整对象替换了 settings（AST，注释 / 文档串里的写法不算） ─────────────────────


def _config_module_names(tree: ast.Module) -> set[str]:
    """本文件里指向 ``app.core.config`` 模块的名字（``from app.core import config as c`` / ``import app.core.config``）。"""
    names = {"app.core.config"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core":
            names |= {a.asname or a.name for a in node.names if a.name == "config"}
        elif isinstance(node, ast.Import):
            names |= {a.asname for a in node.names if a.name == "app.core.config" and a.asname}
    return names


def _whole_settings_replacements(source: str) -> list[int]:
    """整对象替换的调用所在行：``patch("app.core.config.settings", …)`` / ``monkeypatch.setattr("app.core.config.settings", …)``
    / ``patch.object(config, "settings")`` / ``monkeypatch.setattr(config, "settings", …)``。
    只换一个属性（``patch("app.core.config.settings.X")``、``setattr(settings, "X", …)``）与换别的模块里的绑定
    （``patch.object(某服务模块, "settings")``，退出即恢复、不影响首次导入）都不算。"""
    tree = ast.parse(source)
    config_names = _config_module_names(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        first = node.args[0]
        if name in ("patch", "setattr") and isinstance(first, ast.Constant) and first.value == _TARGET:
            lines.append(node.lineno)
        elif (
            name in ("object", "setattr") and len(node.args) >= 2 and ast.unparse(first) in config_names
            and isinstance(node.args[1], ast.Constant) and node.args[1].value == "settings"
        ):
            lines.append(node.lineno)
    return lines


@functools.lru_cache(maxsize=1)
def _files_replacing_whole_settings() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for f in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8-sig")
            if "settings" not in text or "app.core" not in text:  # 各种写法的必要条件，省掉逐个解析（约 10 秒）
                continue
            with warnings.catch_warnings():  # 别的测试文件里的无效转义（SyntaxWarning）与本判据无关
                warnings.simplefilter("ignore", SyntaxWarning)
                lines = _whole_settings_replacements(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        if lines:
            found[f.relative_to(BACKEND).as_posix()] = lines
    return found


def test_whole_settings_replacement_only_in_registered_files():
    found = _files_replacing_whole_settings()
    new = sorted(set(found) - _REGISTERED)
    assert not new, (
        "这些文件整对象替换了 app.core.config.settings：替换期间首次导入的模块会永久拿着 Mock"
        "（test_wopi.py 单独跑必失败即此）。改用 monkeypatch.setattr(settings, \"X\", 值)；确实要换整个对象，"
        "先在测试模块顶层导入被测模块、单独跑一次确认不泄漏，再登记到 _REGISTERED：\n"
        + "\n".join(f"{f}:{found[f]}" for f in new)
    )


def test_registered_files_still_replace_whole_settings():
    """名单只许删：不再整对象替换的文件要从 _REGISTERED 移除（否则名单会变成放行后门）。"""
    stale = sorted(_REGISTERED - set(_files_replacing_whole_settings()))
    assert not stale, f"这些文件已不再整对象替换 settings，请从 _REGISTERED 删掉：{stale}"


@pytest.mark.parametrize("source", [
    'with patch("app.core.config.settings") as s:\n    pass\n',
    'from unittest import mock\nwith mock.patch("app.core.config.settings", m):\n    pass\n',
    'monkeypatch.setattr("app.core.config.settings", m)\n',
    'from app.core import config\nwith patch.object(config, "settings", m):\n    pass\n',
    'import app.core.config as cfg\nmonkeypatch.setattr(cfg, "settings", m)\n',
])
def test_detector_flags_whole_object_replacement(source):
    assert _whole_settings_replacements(source)


@pytest.mark.parametrize("source", [
    '# with patch("app.core.config.settings") as s:\n',
    '"""原先用 patch("app.core.config.settings") 换整个对象"""\n',
    'with patch("app.core.config.settings.STORAGE_ROOT", "x"):\n    pass\n',
    'from app.core.config import settings\nmonkeypatch.setattr(settings, "STORAGE_ROOT", "x")\n',
    'import app.services.file_scan_service as fsm\nwith patch.object(fsm, "settings") as s:\n    pass\n',
])
def test_detector_ignores_attribute_patch_comment_and_other_modules(source):
    assert not _whole_settings_replacements(source)


def test_detector_sees_registered_usage():
    """判据自检：登记文件里的真实写法确实被认出（否则上面两条都会空转）。"""
    found = _files_replacing_whole_settings()
    assert "tests/test_audit_log_enhanced.py" in found
    assert "tests/test_wopi.py" not in found, "test_wopi.py 已改为只改 STORAGE_ROOT 一个属性"


# ── 动态：单独跑（新进程，测试文件就是第一个导入后端模块的） ─────────────────────────────────

_ALONE_PROBE = r'''
import json, os, sys
from unittest.mock import NonCallableMock
backend, target = sys.argv[1], sys.argv[2]
os.chdir(backend)
sys.path.insert(0, backend)
import pytest
code = pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "-p", "no:playwright", target])
leaked = sorted(n for n, m in list(sys.modules.items())
                if n.split(".")[0] == "app" and isinstance(getattr(m, "settings", None), NonCallableMock))
print("[alone] " + json.dumps({"exit": int(code), "leaked": leaked}))
'''


@pytest.mark.slow
@pytest.mark.parametrize("target", _RUN_ALONE)
def test_file_passes_alone_without_leaking_mock_settings(target, tmp_path):
    from tests.conftest import ENVIRON_AT_START

    probe = tmp_path / "alone_probe.py"
    probe.write_text(_ALONE_PROBE, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(probe), str(BACKEND), target],
        cwd=BACKEND, env=dict(ENVIRON_AT_START, PYTHONIOENCODING="utf-8"),
        capture_output=True, timeout=600,
    )
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    line = next((ln for ln in out.splitlines() if ln.startswith("[alone] ")), None)
    assert line is not None, f"探针没有输出结果（子进程崩了？）：\n{out[-3000:]}"
    result = json.loads(line[len("[alone] "):])
    assert result["exit"] == 0, f"{target} 单独跑失败：\n{out[-3000:]}"
    assert " passed" in out, out[-3000:]
    assert result["leaked"] == [], f"{target} 跑完这些模块的模块级 settings 还是 Mock：{result['leaked']}"
