# -*- coding: utf-8 -*-
"""`check_file_size.py --files-from` 与 pre-commit 的清单传法。

起因（2026-10-26）：一次提交暂存了 503 个代码文件（路径共 35114 字符），pre-commit 把它们直接摆在
python 的命令行上，超过 Windows 命令行 32767 字符上限 ⇒ Git Bash 报 `Argument list too long`
（exit 126）⇒ hook 把它当成「行数超限」拒提交，而行数门**根本没运行**。改成清单走标准输入。
"""
from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = _REPO / "backend" / "scripts" / "check" / "check_file_size.py"
_HOOK_SRC = _REPO / ".git-hooks" / "pre-commit"
_OK_FILE = "backend/scripts/check/check_file_size.py"  # 自身：在限内、已入库
_MISSING = "backend/tests/__files_from_missing__.py"


def _load():
    """每次重新 exec —— 模块级状态（`_STAGED_MODE`）不串测。"""
    spec = importlib.util.spec_from_file_location("_check_file_size_files_from", _CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_listed_compliant_file_passes(tmp_path: Path) -> None:
    lst = tmp_path / "list.txt"
    lst.write_text(f"\n{_OK_FILE}\n\n", encoding="utf-8")
    assert _load().main(["--files-from", str(lst)]) == 0


def test_listed_paths_are_really_checked(tmp_path: Path) -> None:
    """清单真的被读了：里面有不存在的路径 ⇒ 与命令行传参同样报错（rc=2），不是静默通过。"""
    lst = tmp_path / "list.txt"
    lst.write_text(f"{_OK_FILE}\n{_MISSING}\n", encoding="utf-8")
    assert _load().main(["--files-from", str(lst)]) == 2


def test_stdin_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """`-` = 标准输入（hook 的用法）。"""
    fake = io.TextIOWrapper(io.BytesIO(f"{_MISSING}\n".encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", fake)
    assert _load().main(["--files-from", "-"]) == 2


def test_empty_list_checks_nothing_and_never_full_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空清单 = 没有要查的文件 ⇒ 通过；🔴 不得退回全仓扫描（全仓有预存超限，退回去必然误拒）。"""
    mod = _load()

    def _boom():
        raise AssertionError("给了 --files-from 却走了全仓扫描")

    monkeypatch.setattr(mod, "scan_default", _boom)
    lst = tmp_path / "empty.txt"
    lst.write_text("\n\n", encoding="utf-8")
    assert mod.main(["--files-from", str(lst)]) == 0


def test_unreadable_list_is_an_error(tmp_path: Path) -> None:
    assert _load().main(["--files-from", str(tmp_path / "no_such_list.txt")]) == 2


_PROBE = (
    "if printf '' | \"$PY\" backend/scripts/check/check_file_size.py --staged --files-from - > /dev/null 2>&1; then"
)
_STDIN_CALL = (
    "printf '%s\\n' \"${SIZE_ARGS[@]}\" | \"$PY\" backend/scripts/check/check_file_size.py --staged --files-from -"
)


def _passes_list_on_argv(line: str) -> bool:
    """调用行是否把文件清单摆在 python 的命令行上（`check_file_size.py` 之后出现 `SIZE_ARGS`）。"""
    return "SIZE_ARGS" in line.split("check_file_size.py", 1)[1]


def _argv_calls_outside_fallback(text: str) -> list[str]:
    """命令行传清单的调用行里，不在「脚本还不认 --files-from」那个 else 分支内的（= 违规）。

    `.git/hooks` 是所有 worktree 共用的，停在旧提交的 worktree 里脚本不认新参数 ⇒ 只允许那里退回旧传法。
    """
    bad: list[str] = []
    saw_probe = in_fallback = False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == _PROBE:
            saw_probe = True
        elif saw_probe and line == "else":
            in_fallback = True
        elif in_fallback and line == "fi":
            saw_probe = in_fallback = False
        elif "check_file_size.py" in line and _passes_list_on_argv(line) and not in_fallback:
            bad.append(line)
    return bad


def test_hook_feeds_list_through_stdin() -> None:
    src = _HOOK_SRC.read_text(encoding="utf-8")
    assert _PROBE in src and _STDIN_CALL in src, "hook 的行数门不再从标准输入喂清单"
    assert _argv_calls_outside_fallback(src) == [], (
        "hook 又在新脚本路径上把暂存文件清单摆回命令行：暂存文件多时超过 Windows 32767 字符上限、门禁根本不运行"
    )


def test_mutation_probe_removed_is_caught() -> None:
    """变异反证：去掉「脚本认不认 --files-from」的判断 ⇒ 命令行传法暴露在主路径上，判据必须判红。"""
    src = _HOOK_SRC.read_text(encoding="utf-8")
    assert _PROBE in src, "锚点没命中 —— 变异证明不了判据"
    assert _argv_calls_outside_fallback(src.replace(_PROBE, "if true; then")) != []


def _hook_gate_function() -> str:
    m = re.search(r"^run_size_gate\(\) \{\n.*?\n\}$", _HOOK_SRC.read_text(encoding="utf-8"), re.S | re.M)
    assert m, "hook 里找不到 run_size_gate 函数"
    return m.group(0)


def _run_gate_in_bash(func_src: str, n_paths: int, cwd: Path = _REPO) -> subprocess.CompletedProcess:
    """在 Git Bash 里用 hook 的同一段函数跑一遍：清单是 n 个不存在的长路径（不存在 ⇒ 脚本很快 rc=2 返回）。"""
    py = Path(sys.executable).as_posix()
    script = "\n".join([
        f'cd "{cwd.as_posix()}"',
        f'PY="{py}"',
        "SIZE_ARGS=()",
        f"for i in $(seq 1 {n_paths}); do",
        '  SIZE_ARGS+=("backend/tests/__files_from_probe__/a/fairly/long/path/to/exceed/argv/limit/f_${i}_abcdefghij.py")',
        "done",
        func_src,
        'if run_size_gate; then echo "rc=0"; else echo "rc=$?"; fi',
    ])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([_BASH, "-c", script], capture_output=True, env=env, timeout=120)


def _git_bash() -> str | None:
    """hook 由 Git 自带的 bash 执行。🔴 Windows 上 PATH 里的 `bash` 常是 WSL 启动器（System32），不能用。"""
    if sys.platform != "win32":
        return shutil.which("bash")
    try:
        exec_path = subprocess.run(
            ["git", "--exec-path"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    root = Path(exec_path).parents[2]  # <Git>/mingw64/libexec/git-core → <Git>
    for cand in (root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"):
        if cand.exists():
            return str(cand)
    return None


_BASH = _git_bash()
_needs_bash = pytest.mark.skipif(_BASH is None, reason="没有 Git 自带的 bash（hook 本身也跑不了）")


@_needs_bash
def test_hook_gate_runs_with_600_staged_paths() -> None:
    """实跑 hook 里那段函数：600 个路径（远超 32767 字符）⇒ 门禁真的运行并按「路径不存在」报 rc=2，不是 126。"""
    proc = _run_gate_in_bash(_hook_gate_function(), 600)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    assert "rc=2" in out and "路径不存在" in err, (out, err[-800:])


@_needs_bash
def test_hook_gate_falls_back_for_old_checkout(tmp_path: Path) -> None:
    """`.git/hooks` 各 worktree 共用：停在旧提交的检出里脚本不认 `--files-from` ⇒ 退回命令行传参照常检查。"""
    old = tmp_path / "backend" / "scripts" / "check" / "check_file_size.py"
    old.parent.mkdir(parents=True)
    old.write_text(
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('files', nargs='*')\n"
        "p.add_argument('--staged', action='store_true')\n"
        "a = p.parse_args()\n"
        "print(f'OLD files={len(a.files)}')\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    proc = _run_gate_in_bash(_hook_gate_function(), 5, cwd=tmp_path)
    out = proc.stdout.decode("utf-8", "replace")
    assert "OLD files=5" in out and "rc=3" in out, (out, proc.stderr.decode("utf-8", "replace")[-800:])


@_needs_bash
@pytest.mark.skipif(sys.platform != "win32", reason="命令行长度上限是 Windows 的（Linux ARG_MAX 大得多）")
def test_old_argv_form_really_fails_on_windows() -> None:
    """反证：同样 600 个路径用旧写法（摆在命令行上）⇒ 126 `Argument list too long`，脚本根本没运行。"""
    old = 'run_size_gate() {\n    "$PY" backend/scripts/check/check_file_size.py --staged "${SIZE_ARGS[@]}"\n}'
    proc = _run_gate_in_bash(old, 600)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    assert "rc=126" in out and "路径不存在" not in err, (out, err[-800:])
