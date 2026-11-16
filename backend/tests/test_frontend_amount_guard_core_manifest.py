"""frontend amount guard 的两条实证缺口守卫（spec platform-global-display-settings-closure 任务 11A）。

## 缺陷本体

2026-11-14 复核记录了四条「文件在但链路断」，本文件守其中两条最严重的：

1. **`core_files` 恒为空集合** —— `cli.py` 两处 `core_files: frozenset[str] = frozenset()`
   且**没有任何加载逻辑**。`run_scan(..., core_files=空集)` 里 `rel in core_files`
   恒 False ⇒ `total_core_violations` 恒 0 ⇒ AC-23「核心面零违规」这条结论
   建立在「核心面 = 空集」之上，等于没检。
2. **`_HISTORICAL_UPPER_LIMIT = 2000`** —— AC-23 要求 88，注释自陈「原占位值 88
   从未与真实基线对账」，实际放宽 22 倍。

外加一条本轮实测发现的：

3. **`--check` 通过时打印 `✅` 在 GBK 终端抛 `UnicodeEncodeError`**，退出码非 0
   但判据根本没跑完 —— 看起来像「门禁红了」，实际是崩在 print 上。

## 分组

A. 核心清单存在性 / 口径一致性 / 幂等（无子进程，纯读文件）。
B. `_load_core_files` 的反向判据：缺失 / 空列表必须抛错，不得静默退化成空集。
C. 两个上限常量必须分开且各自对各自的量（原实现共用一个，填 88 与 2000 必有一头错）。
D. 子进程跑真实 `--check`：断言 **stdout 有内容**（防解码失败假绿）+ 退出码 0。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
_CORE_MANIFEST = _REPO_ROOT / "audit-platform" / "frontend" / "scripts" / "amount-guard-core.json"
_GEN_SCRIPT = "scripts.gen.gen_frontend_amount_core_manifest"


def _py() -> str:
    return str(_REPO_ROOT / ".venv" / "Scripts" / "python.exe")


# ── A. 核心清单 ─────────────────────────────────────────────────────────────


def test_core_manifest_exists_and_non_empty() -> None:
    """清单必须存在且非空 —— 空清单正是缺陷成因。"""
    assert _CORE_MANIFEST.exists(), (
        f"缺少核心清单 {_CORE_MANIFEST}；先跑 "
        f"`python -m {_GEN_SCRIPT} --write`"
    )
    data = json.loads(_CORE_MANIFEST.read_text(encoding="utf-8"))
    files = data.get("files") or []
    assert len(files) > 0, "核心清单 files 为空（会让 total_core_violations 恒 0）"
    # 核心组件与格式化函数必须在册（这是口径的锚点，不是随手数量）
    for rel in (
        "components/common/GtAmountCell.vue",
        "components/common/GtMeasureCell.vue",
        "utils/formatAmount.ts",
        "utils/formatMeasure.ts",
    ):
        assert rel in files, f"核心清单缺少锚点文件: {rel}"


def test_core_manifest_has_no_test_files() -> None:
    """测试文件不得进核心清单（它们不决定屏幕显示，且会让违规数噪声化）。"""
    data = json.loads(_CORE_MANIFEST.read_text(encoding="utf-8"))
    offenders = [
        f
        for f in data["files"]
        if "__tests__" in f or f.endswith((".spec.ts", ".test.ts", ".spec.vue"))
    ]
    assert offenders == [], f"核心清单含测试文件: {offenders[:5]}"


def test_core_manifest_generator_check_is_idempotent() -> None:
    """生成器 `--check` 必须通过（内容不变则无 diff）。

    🔴 这条同时防止「往生成器里塞时间戳」——
    带时间戳的生成器 `--check` 永远红，而永红门禁等于没有门禁
    （memory 铁律 ㉗①：新增 CI 判据必问「没有违规时它真的会绿吗」）。
    """
    proc = subprocess.run(
        [_py(), "-m", _GEN_SCRIPT, "--check"],
        cwd=str(_BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, f"--check 失败：{proc.stdout}\n{proc.stderr}"
    assert "一致" in (proc.stdout or ""), f"stdout 无预期内容（需断言输出，防解码失败假绿）：{proc.stdout!r}"


# ── B. _load_core_files 的反向判据 ──────────────────────────────────────────


def test_load_core_files_raises_when_manifest_missing(tmp_path: Path) -> None:
    """清单缺失必须抛错，**不得**静默返回空 frozenset（那就是缺陷本体）。"""
    sys.path.insert(0, str(_BACKEND))
    from scripts.check.frontend_amount_guard.cli import _load_core_files

    with pytest.raises(FileNotFoundError):
        _load_core_files(tmp_path / "nope.json")


def test_load_core_files_raises_when_files_empty(tmp_path: Path) -> None:
    """清单 files 为空也必须抛错 —— 空集会让核心面判据恒绿。"""
    sys.path.insert(0, str(_BACKEND))
    from scripts.check.frontend_amount_guard.cli import _load_core_files

    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"files": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        _load_core_files(p)


def test_load_core_files_reads_real_manifest() -> None:
    """默认路径能读出真实清单（正向判据，防「函数只会抛错」的反向假绿）。"""
    sys.path.insert(0, str(_BACKEND))
    from scripts.check.frontend_amount_guard.cli import _load_core_files

    files = _load_core_files()
    assert len(files) > 0
    assert "utils/formatAmount.ts" in files


# ── C. 两个上限常量必须分开 ─────────────────────────────────────────────────


def test_upper_limits_are_two_distinct_constants() -> None:
    """核心违规上限与候选上限必须**分开**，且各自对各自的量。

    🔴 原实现只有一个 `_HISTORICAL_UPPER_LIMIT`，先填 88（AC-23 的核心违规上限）
    后改 2000（因 `total_candidates` 1451 立刻越限）。
    两个量放一个常量里，无论填哪个都必有一头错：
    - 填 88 ⇒ `total_candidates=1451 > 88` 恒红；
    - 填 2000 ⇒ 核心违规上限形同不存在。
    """
    sys.path.insert(0, str(_BACKEND))
    from scripts.check.frontend_amount_guard import cli

    assert hasattr(cli, "_CORE_VIOLATION_UPPER_LIMIT")
    assert hasattr(cli, "_CANDIDATE_UPPER_LIMIT")
    # 核心面必须零违规（AC-23 原文）
    assert cli._CORE_VIOLATION_UPPER_LIMIT == 0
    # 候选上限取实测值附近，且**远小于** 2000（原放宽值）
    assert cli._CANDIDATE_UPPER_LIMIT < 2000
    # 与真实基线同量级（防再次出现「占位值从未对账」）
    baseline = json.loads(
        (_REPO_ROOT / "audit-platform" / "frontend" / "scripts" / "amount-guard-baseline.json")
        .read_text(encoding="utf-8")
    )
    real = baseline["total_candidates"]
    assert real <= cli._CANDIDATE_UPPER_LIMIT, (
        f"实测 total_candidates={real} 已越过上限 {cli._CANDIDATE_UPPER_LIMIT}"
    )
    assert cli._CANDIDATE_UPPER_LIMIT - real <= 100, (
        "上限离实测值太远会让门禁失去意义（留量不得超过 100）"
    )


def test_no_legacy_single_limit_constant() -> None:
    """旧的单常量必须已退役（否则有人会继续用它，两个口径又混回去）。"""
    sys.path.insert(0, str(_BACKEND))
    from scripts.check.frontend_amount_guard import cli

    assert not hasattr(cli, "_HISTORICAL_UPPER_LIMIT")


# ── D. 子进程跑真实 --check ─────────────────────────────────────────────────


def test_check_passes_and_prints_result() -> None:
    """真实 `--check` 必须 exit 0，且 **stdout 有内容**。

    🔴 只看 returncode 会假绿：Windows 上 piped stdout 解码失败时
    `subprocess.run` 仍成功、`proc.stdout` 变 None（memory 铁律 ㉗⑦）。
    本轮修复的正是这条：`--check` 通过时打印 `✅` 曾抛 `UnicodeEncodeError`，
    崩在 print 上、退出码非 0。
    """
    proc = subprocess.run(
        [_py(), "-m", "scripts.check.frontend_amount_guard.cli", "--check"],
        cwd=str(_BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, f"--check 失败：\n{proc.stdout}\n{proc.stderr}"
    out = proc.stdout or ""
    assert out.strip(), "stdout 为空 —— 可能是解码失败导致的假绿"
    assert "core violations" in out, f"stdout 缺少核心违规报告：{out!r}"

    # 🔴 必须断言「核心文件数 > 0」：核心集恒空时 `total_core_violations` 也恒 0，
    #    只看「0 core violations」分不出「真的没问题」与「根本没检」（本轮变异 M1 坐实）。
    import re

    m = re.search(r"(\d+) core files scanned", out)
    assert m, f"stdout 未报告核心文件数，无法区分「零违规」与「零检查」：{out!r}"
    assert int(m.group(1)) > 0, "核心文件数为 0 —— 核心面判据退化成空集"
    # 与磁盘清单逐值对上（防止 cli 又改成硬编码空集）
    disk = json.loads(_CORE_MANIFEST.read_text(encoding="utf-8"))
    assert int(m.group(1)) == len(disk["files"])


def test_check_works_under_gbk_console() -> None:
    """GBK 控制台（不设 PYTHONIOENCODING）下 `--check` 也不得崩溃。

    CI 在 Linux（UTF-8）所以看不出这个问题，但本地 Windows 会直接崩。
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    env["PYTHONIOENCODING"] = "gbk"
    proc = subprocess.run(
        [_py(), "-m", "scripts.check.frontend_amount_guard.cli", "--check"],
        cwd=str(_BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )
    assert proc.returncode == 0, (
        f"GBK 下 --check 崩溃（原缺陷形态：打印 ✅ 抛 UnicodeEncodeError）：\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert "UnicodeEncodeError" not in (proc.stderr or "")