"""start-dev.bat 的后端热重载开关 `GT_BACKEND_NO_RELOAD`（spec oo-return-to-form-dead-end-and-save-speed R5）。

判据：从 start-dev.bat **原样**取出开关几行与后端启动行，`start` 换成 echo，在 cmd 里两种模式各跑一次：

* 默认（变量未设）：带全部 `--reload*` 参数（行为不变）；
* `GT_BACKEND_NO_RELOAD=1`：一个 `--reload*` 参数都不带，其余参数逐字相同，并打印一行提示。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BAT = Path(__file__).resolve().parents[2] / "start-dev.bat"
RELOAD_ARGS = (
    "--reload", "--reload-dir app", "--reload-delay 2.0", '--reload-exclude "*.pyc"',
    '--reload-exclude "__pycache__"', '--reload-exclude ".hypothesis"', '--reload-exclude "*.json"',
    '--reload-exclude "tmp_*"',
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 展开行为只在 Windows 上有意义")


def _expanded(
    tmp_path: Path, *, no_reload: bool, runtime_mode: str | None = None,
) -> tuple[str, list[str]]:
    lines = BAT.read_bytes().decode("ascii").split("\r\n")
    first = next(i for i, line in enumerate(lines) if line.startswith('set "BACKEND_RELOAD_ARGS='))
    start = next(i for i, line in enumerate(lines) if line.startswith('start "%BACKEND_TITLE%"'))
    block = lines[first:start + 1]
    block[-1] = "echo CMD=" + block[-1][len("start "):]
    script = tmp_path / "probe.bat"
    script.write_bytes("\r\n".join([
        "@echo off", "setlocal EnableExtensions EnableDelayedExpansion",
        'set "BACKEND_TITLE=T"', 'set "BACKEND_DIR=B"', 'set "PY=P"', 'set "BACKEND_PORT=9980"', *block, "",
    ]).encode("ascii"))
    env = {
        k: v for k, v in os.environ.items()
        if k not in {"GT_BACKEND_NO_RELOAD", "GT_RUNTIME_MODE"}
    }
    if no_reload:
        env["GT_BACKEND_NO_RELOAD"] = "1"
    if runtime_mode is not None:
        env["GT_RUNTIME_MODE"] = runtime_mode
    out = subprocess.run(["cmd", "/c", str(script)], capture_output=True, env=env, timeout=60)
    text = out.stdout.decode("ascii", "replace").splitlines()
    command = next(line for line in text if line.startswith("CMD="))
    return command, [line.strip() for line in text if line.strip() and not line.startswith("CMD=")]


def test_default_keeps_every_reload_argument(tmp_path: Path) -> None:
    command, extra = _expanded(tmp_path, no_reload=False)
    assert all(arg in command for arg in RELOAD_ARGS), command
    assert extra == []


def test_switch_drops_only_the_reload_arguments(tmp_path: Path) -> None:
    default, _ = _expanded(tmp_path, no_reload=False)
    command, extra = _expanded(tmp_path, no_reload=True)
    assert "--reload" not in command, command
    stripped = default
    for arg in RELOAD_ARGS[::-1]:
        stripped = stripped.replace(" " + arg, "", 1)
    assert command.split() == stripped.split(), (command, stripped)
    assert any("GT_BACKEND_NO_RELOAD=1" in line for line in extra), extra


def test_stable_mode_drops_backend_reload_and_uses_built_frontend(tmp_path: Path) -> None:
    command, extra = _expanded(tmp_path, no_reload=False, runtime_mode="stable")
    assert "--reload" not in command
    assert any("Stable backend snapshot" in line for line in extra), extra

    source = BAT.read_bytes().decode("ascii")
    assert 'call npm --prefix "%FRONTEND_DIR%" run build:runtime' in source
    assert "npm run preview:stable" in source
    assert re.search(r'if /I "%GT_RUNTIME_MODE%"=="stable" set "BACKEND_RELOAD_ARGS="', source)


def test_runtime_mode_is_fail_closed() -> None:
    source = BAT.read_bytes().decode("ascii")
    assert 'GT_RUNTIME_MODE must be dev or stable' in source
    assert 'if /I "%GT_RUNTIME_MODE%"=="dev" goto runtime_mode_ok' in source
    assert 'if /I "%GT_RUNTIME_MODE%"=="stable" goto runtime_mode_ok' in source
