"""四件生成物原子入口的判据（tasks 1.7）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

被测物：`backend/scripts/gen/generate_workpaper_sync_artifacts.py`。它只做「按依赖序调用
四个既有生成器 + 统一结算」，**不复制**任何生成算法。

为什么需要它：四件生成物是单向依赖（manifest → legacy baseline / current-state /
cycle projection）。逐个手跑时漏跑或顺序错，会留下互相矛盾的事实，而四个 `--check` 各自
全绿也发现不了 —— 每个只跟自己的输入比。本轮它第一次运行就抓到一处真实 stale：样板宿主
接入 readiness 单源后 source digest 变了，而此前只跑过下游三件的 `--check`。

判据：
1. 声明序必须是拓扑序（把某件挪到上游之前 ⇒ 立刻失败）；
2. `--check` 一个字节都不写（跑完四件生成物 mtime + sha 不变）；
3. 真实仓库上 `--check` 必须全绿（当下四件已一致）；
4. 任一件 stale ⇒ exit 1 且**逐件点名**，不短路到第一条；
5. 写入后复检不一致 ⇒ exit 2（比「某件过期」更重，指向生成不幂等）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOST = ROOT / "backend/scripts/gen/generate_workpaper_sync_artifacts.py"

_spec = importlib.util.spec_from_file_location("_sync_artifacts_host", HOST)
assert _spec and _spec.loader
H = importlib.util.module_from_spec(_spec)
# 🔴 `dataclass` 解析注解时会 `sys.modules.get(cls.__module__).__dict__` —— 模块不在
#    `sys.modules` 里就是 None.__dict__（AttributeError）。按路径加载带 dataclass 的模块
#    必须先登记（同仓先例：tests/test_migrate_sign_convention_v2.py）。
sys.modules["_sync_artifacts_host"] = H
_spec.loader.exec_module(H)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_outputs() -> list[Path]:
    return [ROOT / rel for stage in H.STAGES for rel in stage.outputs]


def _run_host(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(HOST), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


# ════════════════════════════════════════════════════════════════════════════


def test_stage_denominator_and_outputs_exist() -> None:
    assert len(H.STAGES) == 4, f"声明了 {len(H.STAGES)} 件 —— 与四件生成物不符"
    for stage in H.STAGES:
        assert (HOST.parent / stage.script).is_file(), f"生成器不存在：{stage.script}"
        assert stage.outputs, f"{stage.key} 没声明产物"
        for rel in stage.outputs:
            assert (ROOT / rel).is_file(), f"{stage.key} 声明的产物不在磁盘：{rel}"


def test_declaration_order_is_topological() -> None:
    H._assert_dependency_order()  # 不抛即通过


def test_dependency_order_check_is_falsifiable(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 manifest 挪到它的下游之后 ⇒ 自检必须抛。"""
    reordered = (H.STAGES[1], H.STAGES[0], *H.STAGES[2:])
    monkeypatch.setattr(H, "STAGES", reordered)
    with pytest.raises(H.ArtifactHostError, match="依赖序"):
        H._assert_dependency_order()


def test_duplicate_stage_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(H, "STAGES", (H.STAGES[0], H.STAGES[0]))
    with pytest.raises(H.ArtifactHostError, match="重复 key"):
        H._assert_dependency_order()


@pytest.mark.slow
def test_check_is_green_and_writes_nothing(tmp_path: Path) -> None:
    before = {path: (_sha(path), path.stat().st_mtime_ns) for path in _all_outputs()}
    report_path = tmp_path / "check.json"
    proc = _run_host("--check", "--json", str(report_path))
    after = {path: (_sha(path), path.stat().st_mtime_ns) for path in _all_outputs()}

    assert before == after, (
        "`--check` 改动了产物（内容或 mtime）—— 它必须是纯只读"
    )
    assert proc.returncode == 0, (
        f"真实仓库上 `--check` 不绿（rc={proc.returncode}）：\n{proc.stdout}\n{proc.stderr}"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "check"
    assert report["state_counts"] == {"ok": 4}, report["state_counts"]
    assert {row["key"] for row in report["stages"]} == {
        stage.key for stage in H.STAGES
    }


def test_stale_stage_is_named_without_short_circuiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两件 stale 时必须都被点名 —— 短路到第一条会让人反复跑。"""
    calls: list[str] = []

    def fake_run(stage, *, write: bool):
        calls.append(stage.key)
        bad = stage.key in {"legacy_baseline", "cycle_projection"}
        return H.StageOutcome(
            key=stage.key,
            script=stage.script,
            mode="write" if write else "check",
            returncode=1 if bad else 0,
            state="stale" if bad else "ok",
            tail="fake",
        )

    monkeypatch.setattr(H, "_run", fake_run)
    outcomes = H.check_all()
    assert calls == [stage.key for stage in H.STAGES], "有件被短路跳过"
    stale = sorted(item.key for item in outcomes if item.state == "stale")
    assert stale == ["cycle_projection", "legacy_baseline"]


def test_write_skips_downstream_when_upstream_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manifest 写失败 ⇒ 三个下游必须 skipped（它们会读到半截上游）。"""

    def fake_run(stage, *, write: bool):
        failed = stage.key == "manifest"
        return H.StageOutcome(
            key=stage.key,
            script=stage.script,
            mode="write" if write else "check",
            returncode=2 if failed else 0,
            state="failed" if failed else "ok",
            tail="fake",
        )

    monkeypatch.setattr(H, "_run", fake_run)
    produced, _ = H.write_all()
    states = {item.key: item.state for item in produced}
    assert states["manifest"] == "failed"
    assert [states[key] for key in ("legacy_baseline", "current_state", "cycle_projection")] == [
        "skipped",
        "skipped",
        "skipped",
    ]


def test_non_idempotent_write_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    """写入全成功但复检 stale ⇒ exit 2（与「某件过期」区分开）。"""
    monkeypatch.setattr(
        H,
        "write_all",
        lambda: (
            [
                H.StageOutcome(
                    key=stage.key, script=stage.script, mode="write",
                    returncode=0, state="ok", tail="fake",
                )
                for stage in H.STAGES
            ],
            [
                H.StageOutcome(
                    key=stage.key, script=stage.script, mode="check",
                    returncode=1 if stage.key == "current_state" else 0,
                    state="stale" if stage.key == "current_state" else "ok",
                    tail="fake",
                )
                for stage in H.STAGES
            ],
        ),
    )
    monkeypatch.setattr(H, "_assert_dependency_order", lambda: None)
    assert H.main(["--write"]) == 2
