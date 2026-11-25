"""
test_streaming_db_scope_ratchet.py

流式路由 DB 作用域棘轮守卫
（spec platform-heavy-jobs-and-capacity-closure A6）。

判据：
1. 基线存在且非空（缺失即失败，不能静默退化成「无候选」）。
2. 候选数**只减不增**。
3. 基线**不得虚高**（防「改大基线蒙过关」）。
4. `--write` 拒绝上调。
5. 扫描器真的能命中（用真实候选现算非零，防「扫描器坏了返回空」）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_BACKEND = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND / "scripts" / "check" / "check_streaming_db_scope.py"
_BASELINE = _BACKEND / "data" / "streaming_db_scope_baseline.json"


def _run(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.check.check_streaming_db_scope", *args],
        cwd=str(_BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


class TestBaseline:
    def test_script_exists(self) -> None:
        assert _SCRIPT.exists()

    def test_baseline_exists_and_non_empty(self) -> None:
        """基线缺失或 count=0 会让守卫恒绿。"""
        assert _BASELINE.exists(), f"缺少基线 {_BASELINE}；先跑 --write"
        data = json.loads(_BASELINE.read_text(encoding="utf-8"))
        assert data["count"] > 0, "基线 count=0，守卫会恒绿"
        assert len(data["candidates"]) == data["count"]

    def test_baseline_criteria_documented(self) -> None:
        data = json.loads(_BASELINE.read_text(encoding="utf-8"))
        assert "StreamingResponse" in data["criteria"]
        assert "FileResponse" in data["criteria"]
        assert "scope" in data["criteria"]


class TestScannerHits:
    def test_scanner_finds_candidates(self) -> None:
        """扫描器必须真的命中（返回空会让棘轮无意义）。"""
        from scripts.check.check_streaming_db_scope import scan

        candidates = scan()
        assert len(candidates) > 0
        # 每条都要有完整字段
        for c in candidates[:5]:
            assert c["file"].endswith(".py")
            assert c["function"]
            assert isinstance(c["lineno"], int)


class TestCheckPasses:
    def test_check_passes_on_frozen_baseline(self) -> None:
        """`--check` 必须与冻结基线一致。

        🔴 断言 stdout 有内容（只判 returncode 会漏掉解码失败导致的假绿）。
        """
        rc, out, err = _run("--check")
        assert out.strip(), f"无输出（stderr={err!r}）"
        assert rc == 0, f"{out}\n{err}"

    def test_check_fails_when_baseline_missing(self, tmp_path: Path, monkeypatch) -> None:
        """基线缺失必须失败（不能当「无候选」放行）。"""
        from scripts.check import check_streaming_db_scope as mod

        monkeypatch.setattr(mod, "_BASELINE", tmp_path / "nope.json")
        rc = mod.main(["--check"])
        assert rc == 1

    def test_check_fails_when_candidates_increase(self, monkeypatch) -> None:
        """候选增加必须失败，且点名新增项。"""
        from scripts.check import check_streaming_db_scope as mod

        real = mod.scan()
        # 把基线改成比真实少一条
        monkeypatch.setattr(
            mod, "_load_baseline",
            lambda: {"count": max(0, len(real) - 1), "candidates": real[:-1]},
        )
        rc = mod.main(["--check"])
        assert rc == 1

    def test_check_fails_when_baseline_inflated(self, monkeypatch) -> None:
        """基线虚高必须失败（防「改大基线蒙过关」）。"""
        from scripts.check import check_streaming_db_scope as mod

        real = mod.scan()
        monkeypatch.setattr(
            mod, "_load_baseline",
            lambda: {"count": len(real) + 100, "candidates": []},
        )
        rc = mod.main(["--check"])
        assert rc == 1


class TestWriteRefusesRaise:
    def test_write_refuses_to_raise_baseline(self, monkeypatch) -> None:
        """`--write` 在候选增加时必须拒绝（否则棘轮失效）。"""
        from scripts.check import check_streaming_db_scope as mod

        real = mod.scan()
        monkeypatch.setattr(
            mod, "_load_baseline",
            lambda: {"count": max(0, len(real) - 3), "candidates": []},
        )
        wrote: list[int] = []
        monkeypatch.setattr(mod, "_write_baseline", lambda c: wrote.append(len(c)))
        rc = mod.main(["--write"])
        assert rc == 1
        assert wrote == [], "拒绝上调时不应写盘"


class TestA6DocReference:
    def test_tasks_md_records_the_ratchet(self) -> None:
        """A6 的棘轮必须在 tasks.md 里有登记（防「建了守卫但 spec 不知道」）。"""
        p = _BACKEND.parent / ".kiro" / "specs" / "_archive" / "188-platform-heavy-jobs-and-capacity-closure" / "tasks.md"
        text = p.read_text(encoding="utf-8")
        assert "check_streaming_db_scope" in text
        assert "streaming_db_scope_baseline" in text
