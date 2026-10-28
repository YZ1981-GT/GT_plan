"""检查模式守卫：两份清单脚本 ``--check`` 与双次 ``--out`` 生成逐字节一致。

Feature: partner-manager-edit-permission, Task 8.10

子进程分别跑 ``gen_note_write_inventory.py --check`` 与 ``gen_edit_level_impact_inventory.py --check``，
断言退出码 0 与中文结论（无替换字符）。两脚本各以 ``--out`` 写两次临时文件，与已提交产物逐字节相同。

不加任何跳过或慢测排除标记。
Requirements: 1.10, 9.1, 12.12
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ─── 常量 ───────────────────────────────────────────────────────────────────

PYTHON = sys.executable
REPO = Path(__file__).resolve().parents[1].parent  # backend/tests → 仓库根
BACKEND = REPO / "backend"

NOTE_SCRIPT = BACKEND / "scripts" / "gen" / "gen_note_write_inventory.py"
IMPACT_SCRIPT = BACKEND / "scripts" / "gen" / "gen_edit_level_impact_inventory.py"

NOTE_PRODUCT = BACKEND / "data" / "authz" / "note_write_inventory.json"
IMPACT_PRODUCT = BACKEND / "data" / "authz" / "edit_level_impact_inventory.json"

NOTE_CONSISTENT = "附注写端点清册与仓库现状一致"
IMPACT_CONSISTENT = "edit 级影响清单与仓库现状一致"

# 子进程环境：保证 UTF-8 输出
_SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _run_script(script: Path, args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """以子进程执行脚本，UTF-8 解码并检查无替换字符。"""
    result = subprocess.run(
        [PYTHON, str(script), *args],
        capture_output=True,
        env=_SUBPROCESS_ENV,
        cwd=str(REPO),
        timeout=timeout,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    # 断言输出非空
    assert stdout or stderr, f"脚本 {script.name} 输出为空（stdout 和 stderr 都为空）"
    # 断言无替换字符 (\ufffd)
    assert "\ufffd" not in stdout, f"脚本 {script.name} stdout 含替换字符（解码失败）：{stdout[:200]}"
    assert "\ufffd" not in stderr, f"脚本 {script.name} stderr 含替换字符（解码失败）：{stderr[:200]}"
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ─── 检查模式：退出码 0 与中文结论 ────────────────────────────────────────────


class TestCheckMode:
    """两脚本 ``--check`` 退出码 0 且 stdout 含中文一致结论。"""

    def test_note_write_inventory_check_mode(self) -> None:
        result = _run_script(NOTE_SCRIPT, ["--check"])
        assert result.returncode == 0, (
            f"附注写端点清册 --check 退出码 {result.returncode}（期望 0）\n"
            f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )
        assert NOTE_CONSISTENT in result.stdout, (
            f"附注写端点清册 --check stdout 中缺少一致结论「{NOTE_CONSISTENT}」\n"
            f"stdout: {result.stdout[:500]}"
        )

    def test_edit_level_impact_inventory_check_mode(self) -> None:
        result = _run_script(IMPACT_SCRIPT, ["--check"])
        assert result.returncode == 0, (
            f"edit 级影响清单 --check 退出码 {result.returncode}（期望 0）\n"
            f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )
        assert IMPACT_CONSISTENT in result.stdout, (
            f"edit 级影响清单 --check stdout 中缺少一致结论「{IMPACT_CONSISTENT}」\n"
            f"stdout: {result.stdout[:500]}"
        )


# ─── 双次生成逐字节一致 ──────────────────────────────────────────────────────


class TestDoubleGenerateIdentical:
    """两脚本各以 ``--out`` 写两次临时文件，与已提交产物逐字节相同。"""

    def test_note_write_inventory_double_generate(self, tmp_path: Path) -> None:
        # 已提交产物按 LF 归一后比（index 是 LF，Windows 检出是 CRLF；spec note-pull-followup-closure R21）
        committed = NOTE_PRODUCT.read_bytes().replace(b"\r\n", b"\n")
        out1 = tmp_path / "note_1.json"
        out2 = tmp_path / "note_2.json"

        r1 = _run_script(NOTE_SCRIPT, ["--out", str(out1)])
        assert r1.returncode == 0, (
            f"附注写端点清册第一次 --out 退出码 {r1.returncode}\n"
            f"stdout: {r1.stdout[:500]}\nstderr: {r1.stderr[:500]}"
        )

        r2 = _run_script(NOTE_SCRIPT, ["--out", str(out2)])
        assert r2.returncode == 0, (
            f"附注写端点清册第二次 --out 退出码 {r2.returncode}\n"
            f"stdout: {r2.stdout[:500]}\nstderr: {r2.stderr[:500]}"
        )

        gen1 = out1.read_bytes()
        gen2 = out2.read_bytes()

        assert gen1 == gen2, "附注写端点清册两次生成结果不逐字节相同"
        assert b"\r\n" not in gen1, "生成结果应恒为 LF"
        assert gen1 == committed, (
            f"附注写端点清册生成结果与已提交产物不逐字节相同"
            f"（生成 {len(gen1)} 字节，已提交 {len(committed)} 字节）"
        )

    def test_edit_level_impact_inventory_double_generate(self, tmp_path: Path) -> None:
        committed = IMPACT_PRODUCT.read_bytes().replace(b"\r\n", b"\n")
        out1 = tmp_path / "impact_1.json"
        out2 = tmp_path / "impact_2.json"

        r1 = _run_script(IMPACT_SCRIPT, ["--out", str(out1)])
        assert r1.returncode == 0, (
            f"edit 级影响清单第一次 --out 退出码 {r1.returncode}\n"
            f"stdout: {r1.stdout[:500]}\nstderr: {r1.stderr[:500]}"
        )

        r2 = _run_script(IMPACT_SCRIPT, ["--out", str(out2)])
        assert r2.returncode == 0, (
            f"edit 级影响清单第二次 --out 退出码 {r2.returncode}\n"
            f"stdout: {r2.stdout[:500]}\nstderr: {r2.stderr[:500]}"
        )

        gen1 = out1.read_bytes()
        gen2 = out2.read_bytes()

        assert gen1 == gen2, "edit 级影响清单两次生成结果不逐字节相同"
        assert b"\r\n" not in gen1, "生成结果应恒为 LF"
        assert gen1 == committed, (
            f"edit 级影响清单生成结果与已提交产物不逐字节相同"
            f"（生成 {len(gen1)} 字节，已提交 {len(committed)} 字节）"
        )
