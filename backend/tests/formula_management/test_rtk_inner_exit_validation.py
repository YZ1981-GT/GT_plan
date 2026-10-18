# -*- coding: utf-8 -*-
"""Task 8.5 · RTK 吞失败退出码修正（复用 §7.4③ 口径）单测 + 变异反证。

spec: formula-manager-closure · 需求 20.4 · design §5 步骤 8 · 20.4、§7.4③。

验收判据（tasks.md Task 8.5）：
  * **变异**：内层命令失败而 RTK 返 exit 0 时门禁应打红。
  * **反向断言**：内层成功时通过。
  * 断言 **stdout 内容**（非仅 returncode）。

本测试用一个「假 RTK」脚本模拟审计报告观察到的 RTK 吞失败行为（内层失败、外层硬返 0），
证明 :mod:`rtk_exit_validation` 的内层判定**不被外层 0 骗过**（靠 stdout 失败标记兜）；
并对 :mod:`check_rtk_inner_exit_validation` 的 AST/TS 扫描做正反变异（注入反模式→真红、
合规形态→不误报）。
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from app.services.formula_management.rtk_exit_validation import (
    GateInnerFailure,
    GateRunResult,
    assert_gate_passed,
    is_rtk_wrapped,
    run_gate_subprocess,
)

_REPO = Path(__file__).resolve().parents[3]
_CHECK_SCRIPT = _REPO / "backend" / "scripts" / "check" / "check_rtk_inner_exit_validation.py"


# ─────────────────────── 载入被测守卫脚本（文件路径 import）───────────────────────


def _load_check_module():
    spec = importlib.util.spec_from_file_location("_check_rtk_inner_exit", _CHECK_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHECK = _load_check_module()


# ─────────────────────── 假 RTK：模拟吞失败退出码 ───────────────────────


def _write_fake_rtk_swallow(tmp_path: Path) -> Path:
    """写一个假 RTK：无论内层成败，**外层硬返 exit 0**（审计报告观察到的吞码行为）。

    内层命令是 `python -c "...; sys.exit(N)"`，假 RTK 透传内层 stdout 但把退出码改成 0。
    """
    script = tmp_path / "fake_rtk_swallow.py"
    script.write_text(
        textwrap.dedent(
            """
            import subprocess, sys
            # argv[1:] 是被包装的命令。
            inner = subprocess.run(sys.argv[1:], capture_output=True, encoding="utf-8", errors="replace")
            sys.stdout.write(inner.stdout or "")
            sys.stderr.write(inner.stderr or "")
            # 🔴 吞码：无论内层 returncode 多少，外层一律返 0（这正是本任务要防的缺陷）。
            sys.exit(0)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def _inner_fail_cmd() -> list[str]:
    """内层命令：打印失败标记并以非 0 退出。"""
    return [
        sys.executable,
        "-c",
        "import sys; print('[FAIL] 内层确实失败了'); sys.exit(3)",
    ]


def _inner_ok_cmd() -> list[str]:
    """内层命令：打印成功标记并以 0 退出。"""
    return [
        sys.executable,
        "-c",
        "import sys; print('[OK] 内层通过'); sys.exit(0)",
    ]


# ─────────────────────── is_rtk_wrapped ───────────────────────


def test_is_rtk_wrapped_identifies_rtk_prefix():
    assert is_rtk_wrapped(["rtk", "python", "-m", "pytest"]) is True
    assert is_rtk_wrapped(["rtk.exe", "git", "status"]) is True
    assert is_rtk_wrapped([r"C:\Users\x\.local\bin\rtk", "ls"]) is True
    assert is_rtk_wrapped(["/home/x/.local/bin/rtk", "ls"]) is True


def test_is_rtk_wrapped_rejects_non_rtk():
    assert is_rtk_wrapped(["python", "x.py"]) is False
    assert is_rtk_wrapped(["rtkfoo", "x"]) is False  # 不是整词 rtk
    assert is_rtk_wrapped([]) is False


# ─────────────────────── 变异：RTK 返 0 内层失败 → 门禁打红 ───────────────────────


def test_mutation_rtk_swallows_failure_still_detected_as_failure(tmp_path):
    """变异（核心验收）：RTK 外层返 exit 0、内层实际失败 → inner_passed False、assert 抛错。

    这证明判定不靠外层 returncode（外层被吞成 0），而靠 stdout 的失败标记。
    """
    fake_rtk = _write_fake_rtk_swallow(tmp_path)
    argv = ["rtk", sys.executable, str(fake_rtk), *_inner_fail_cmd()]

    result = run_gate_subprocess(
        argv,
        expected_markers=["[OK]", "[FAIL]"],  # 成功/失败两类标记都登记
        failure_markers=["[FAIL]"],
    )

    # 外层被假 RTK 吞成 0（证明「只看 returncode」会假绿）。
    assert result.returncode == 0, "假 RTK 应把外层码吞成 0（否则本变异未生效）"
    # 但内层判定必须识别失败标记 → 不通过。
    assert result.failure_markers_hit == ["[FAIL]"]
    assert result.inner_passed() is False, "内层失败标记命中 ⇒ 不得因外层 0 判通过（假绿）"
    # 断言 stdout 内容（非仅 returncode）：失败标记真的出现在输出里。
    assert "[FAIL]" in result.stdout

    with pytest.raises(GateInnerFailure) as exc:
        assert_gate_passed(result)
    # 抛错消息含 stdout 摘要（断言内容，不只退出码）。
    assert "[FAIL]" in str(exc.value)


def test_reverse_rtk_wrapped_inner_success_passes(tmp_path):
    """反向断言：RTK 包装、内层成功 → inner_passed True、assert 不抛（不把干净态判缺陷，㉒）。"""
    fake_rtk = _write_fake_rtk_swallow(tmp_path)
    argv = ["rtk", sys.executable, str(fake_rtk), *_inner_ok_cmd()]

    result = run_gate_subprocess(
        argv,
        expected_markers=["[OK]", "[FAIL]"],
        failure_markers=["[FAIL]"],
    )
    assert result.markers_hit == ["[OK]"]
    assert result.failure_markers_hit == []
    assert "[OK]" in result.stdout
    assert result.inner_passed() is True
    assert_gate_passed(result)  # 不抛


# ─────────────────────── marker_missing：stdout 被吞成空 → 不假绿 ───────────────────────


def test_marker_missing_is_not_green(tmp_path):
    """stdout 无任何预期标记（解码被吞 / 空转）→ inner_passed False，断言抛错（教训㉗⑦）。"""
    # 内层不打印任何已登记标记，且外层（直调，不经 rtk）返 0。
    argv = [sys.executable, "-c", "import sys; print('完全无关的输出'); sys.exit(0)"]
    result = run_gate_subprocess(argv, expected_markers=["[OK]", "[FAIL]"])
    assert result.returncode == 0
    assert result.has_any_marker is False
    assert result.inner_passed() is False, "无预期标记 ⇒ 不得判通过（stdout 可能被吞成空）"
    with pytest.raises(GateInnerFailure) as exc:
        assert_gate_passed(result)
    assert "无任何预期标记" in str(exc.value)


def test_outer_nonzero_without_success_signal_fails():
    """外层 returncode 非 0 且无成功信号 → 失败（外层码『非 0 必失败』方向可信）。"""
    argv = [sys.executable, "-c", "import sys; print('[FAIL] x'); sys.exit(2)"]
    result = run_gate_subprocess(argv, expected_markers=["[FAIL]"], failure_markers=["[FAIL]"])
    assert result.inner_passed() is False


def test_three_state_ok_or_drift_marker_passes():
    """三态门（OK / DRIFT 皆有效）：命中 DRIFT 标记、无失败标记、外层码 2 → 仍可判「有效」。

    这对应 formula-manager 分母枚举器的三态退出码（OK=0 / DRIFT=2 / DB_UNAVAILABLE=3）——
    DRIFT 本身是**有效结论**（点名漂移），不该被当失败。调用方把 DRIFT 当成功信号时，
    failure_markers 不含 DRIFT，故 inner_passed 看外层非 0 但有成功信号 → True。
    """
    argv = [sys.executable, "-c", "import sys; print('[DRIFT] 漂移'); sys.exit(2)"]
    # DRIFT 登记为预期标记但不登记为失败标记 ⇒ 视为有效三态。
    result = run_gate_subprocess(argv, expected_markers=["[OK]", "[DRIFT]"], failure_markers=[])
    assert result.markers_hit == ["[DRIFT]"]
    assert result.inner_passed() is True


# ─────────────────────── §7.4③：子进程强制 utf-8 + errors='replace' ───────────────────────


def test_subprocess_forces_utf8_and_replace_on_bad_bytes():
    """内层打印非法字节时不崩、不吞成 None——errors='replace' 保证输出可读（§7.4③）。"""
    # 打印一个在 gbk 下会炸的中文标记 + 一段任意字节，验证 utf-8/replace 不丢标记。
    code = "import sys; print('[OK] 货币资金校验✓'); sys.exit(0)"
    argv = [sys.executable, "-c", code]
    result = run_gate_subprocess(argv, expected_markers=["[OK]"])
    assert "[OK]" in result.stdout, "中文标记在 utf-8 下必须稳定出现（否则 Windows gbk 假绿）"
    assert result.inner_passed() is True


# ─────────────────────── AST 守卫：正反变异 ───────────────────────


def test_guard_flags_rtk_subprocess_that_only_checks_returncode(tmp_path):
    """变异：注入「rtk 包装的 subprocess + 只看 returncode」反模式 → AST 守卫命中。"""
    bad = tmp_path / "bad_gate.py"
    bad.write_text(
        textwrap.dedent(
            """
            import subprocess

            def run_gate():
                r = subprocess.run(["rtk", "python", "-m", "pytest", "x"], capture_output=True)
                if r.returncode != 0:
                    raise SystemExit(1)
                return True
            """
        ),
        encoding="utf-8",
    )
    hits = CHECK.scan_python_file(bad)
    assert len(hits) == 1, f"应命中 1 处 rtk-只看码 反模式，实际 {hits}"
    assert hits[0]["lang"] == "python"


def test_guard_passes_rtk_subprocess_that_asserts_stdout(tmp_path):
    """反向：rtk 包装但访问了 stdout（内层校验）→ AST 守卫不误报（㉒）。"""
    good = tmp_path / "good_gate.py"
    good.write_text(
        textwrap.dedent(
            """
            import subprocess

            def run_gate():
                r = subprocess.run(["rtk", "python", "-m", "pytest", "x"], capture_output=True, encoding="utf-8")
                assert "[OK]" in r.stdout  # 断言 stdout 内容，非仅 returncode
                return r.returncode
            """
        ),
        encoding="utf-8",
    )
    hits = CHECK.scan_python_file(good)
    assert hits == [], f"访问 stdout 的合规形态不应命中，实际 {hits}"


def test_guard_ignores_non_rtk_subprocess(tmp_path):
    """反向：直调 python（不经 rtk）即便只看 returncode 也不在本门禁范围（不误报）。"""
    plain = tmp_path / "plain_gate.py"
    plain.write_text(
        textwrap.dedent(
            """
            import subprocess

            def run_gate():
                r = subprocess.run(["python", "-m", "pytest", "x"])
                return r.returncode == 0
            """
        ),
        encoding="utf-8",
    )
    assert CHECK.scan_python_file(plain) == []


def test_guard_ignores_rtk_in_comment_and_docstring(tmp_path):
    """变异反证（铁律㉖）：注释/docstring 里出现 rtk 字面量不得被误判为调用。"""
    noisy = tmp_path / "noisy.py"
    noisy.write_text(
        textwrap.dedent(
            '''
            """这个脚本演示 subprocess.run(["rtk", "pytest"]) 只看 returncode 是不对的。"""
            import subprocess

            def run_gate():
                # 下面这行曾经写成 subprocess.run(["rtk", ...]) 只看 r.returncode —— 已改。
                r = subprocess.run(["python", "x.py"], capture_output=True, encoding="utf-8")
                assert "[OK]" in r.stdout
                return r.returncode
            '''
        ),
        encoding="utf-8",
    )
    # 唯一真实调用是直调 python（非 rtk）⇒ 0 命中；注释/docstring 里的 rtk 不进 AST。
    assert CHECK.scan_python_file(noisy) == []


def test_guard_ast_not_fooled_by_rtk_in_string_value(tmp_path):
    """AST 只认 argv 首元素字面量 rtk；把 'rtk' 当普通字符串值的调用不误报。"""
    s = tmp_path / "strval.py"
    s.write_text(
        textwrap.dedent(
            """
            import subprocess

            def run_gate():
                tool_name = "rtk"  # 只是个变量名/值
                r = subprocess.run(["python", "report.py", "--label", tool_name])
                return r.returncode == 0
            """
        ),
        encoding="utf-8",
    )
    assert CHECK.scan_python_file(s) == []


# ─────────────────────── TS 守卫：正反变异 ───────────────────────


def test_ts_guard_flags_rtk_spawn_without_stdout(tmp_path):
    """变异：TS 门禁 spawnSync('rtk', ...) 后只看 .status → 命中。"""
    bad = tmp_path / "bad.spec.ts"
    bad.write_text(
        textwrap.dedent(
            """
            import { spawnSync } from 'node:child_process'
            function runGate() {
              const r = spawnSync('rtk', ['python', 'gate.py'], { encoding: 'utf-8' })
              expect(r.status).toBe(0)
              return r.status
            }
            """
        ),
        encoding="utf-8",
    )
    hits = CHECK.scan_ts_file(bad)
    assert len(hits) >= 1, f"应命中 rtk-spawn-只看 status，实际 {hits}"


def test_ts_guard_passes_rtk_spawn_with_stdout(tmp_path):
    """反向：TS 门禁 spawnSync('rtk', ...) 后断言 stdout → 不误报。"""
    good = tmp_path / "good.spec.ts"
    good.write_text(
        textwrap.dedent(
            """
            import { spawnSync } from 'node:child_process'
            function runGate() {
              const r = spawnSync('rtk', ['python', 'gate.py'], { encoding: 'utf-8' })
              expect(r.stdout).toContain('[OK]')
              expect(r.status).toBe(0)
              return r.status
            }
            """
        ),
        encoding="utf-8",
    )
    assert CHECK.scan_ts_file(good) == []


def test_ts_guard_ignores_non_rtk_spawn(tmp_path):
    """反向：直调 python 的 spawnSync（现状 runProbeCheck）不在本门禁范围。"""
    plain = tmp_path / "plain.spec.ts"
    plain.write_text(
        textwrap.dedent(
            """
            import { spawnSync } from 'node:child_process'
            function runGate() {
              const r = spawnSync('python', ['gate.py'], { encoding: 'utf-8' })
              expect(r.status).toBe(0)
            }
            """
        ),
        encoding="utf-8",
    )
    assert CHECK.scan_ts_file(plain) == []


def test_ts_guard_handles_rtk_in_argv_array(tmp_path):
    """变异：spawnSync(py, ['rtk', 'python', ...]) —— rtk 在 argv 数组首元素也要命中。"""
    bad = tmp_path / "bad2.spec.ts"
    bad.write_text(
        textwrap.dedent(
            """
            import { spawnSync } from 'node:child_process'
            function runGate() {
              const r = spawnSync('bash', ['rtk', 'python', 'gate.py'])
              if (r.status !== 0) throw new Error('fail')
            }
            """
        ),
        encoding="utf-8",
    )
    hits = CHECK.scan_ts_file(bad)
    assert len(hits) >= 1, f"rtk 在 argv 数组首元素应命中，实际 {hits}"


# ─────────────────────── 全仓现状：命中 0（棘轮基线）───────────────────────


def test_repo_currently_has_no_rtk_only_returncode_gate():
    """现状全仓扫描：无 rtk 包装命令仅看 returncode（CI/pre-push/门禁 spec 均合规）。

    这是防回归棘轮基线——日后任何人把门禁命令包成 rtk 又只看退出码，本条立即红。
    """
    violations = CHECK.scan_all()
    assert violations == [], (
        "全仓检出 rtk 包装命令仅看 returncode（RTK 吞失败假绿风险）：\n"
        + "\n".join(f"  [{v['lang']}] {v['file']}:{v['line']}  {v['detail']}" for v in violations)
    )
