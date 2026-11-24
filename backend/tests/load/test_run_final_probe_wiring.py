"""A1 接线单测 v2：真调 main() 的探针分支（不是把分支逻辑抄进测试）。

spec: platform-capacity-acceptance-and-heavy-defect-closure A1 收尾。
v1 教训（守卫假绿）：把 main() 的 skip/errors 分支逻辑 copy 进测试自己拼
stats，变异改 run_final.py 时测试路径根本不经过被改代码 ⇒ 恒绿。v2 通过
monkeypatch run_locust_full_shape 等重 I/O 边界后**真调 main()**：

1. ``--skip-safety-probes``：main 不调探针、不伪造 safety 全 0；
2. 探针 runner 报 ``probe_meta.errors`` 时原样进 ``stats["probe_errors"]``
   （吞掉错误再报全 0 = fail-open，判据红）；
3. 正常链路：before/after 两个时点各调一次 ``run_all_probes``，after 的
   ``safety`` 进 stats，证据文件落 evidence_dir；
4. ``run_probe_evidence`` 单独可调，把证据写到 evidence_dir。
"""
from __future__ import annotations

import json
import sys
from typing import Any

import pytest

import tests.load.run_final as rf


AFTER_SAFETY = {
    "unauthorized_successes": 0, "connection_leaks": 0,
    "connection_timeouts": 0, "event_loss": 0,
    "duplicate_side_effects": 0, "data_corruption": 0,
}


def _fake_run_all_probes(calls: list[dict[str, Any]], *, errors: list[str] | None = None):
    def _fake(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        if kwargs.get("phase") == "before":
            return {"safety": {}, "probe_meta": {"details": {}, "errors": []}}
        return {"safety": dict(AFTER_SAFETY), "probe_meta": {"details": {}, "errors": list(errors or [])}}

    return _fake


class _Args:
    """argparse.Namespace 替身（run_probe_evidence 用到的字段 + skip 开关）。"""

    def __init__(self, *, probe_project: str | None = None, skip: bool = False) -> None:
        self.probe_project = probe_project
        self.skip_safety_probes = skip
        self.probe_pg_dsn = None
        self.host = "http://probe"
        self.baseline = None
        self.safety_evidence = None
        self.evidence_dir = None
        self.worker_stats_dir = None
        self.resource_sample_interval = 15.0
        self.output = "final_report.md"


def _patch_main_edges(
    monkeypatch: pytest.MonkeyPatch, tmp_path, write_hook=None,
) -> None:
    """main() 的重 I/O 边界全部替换：locust 不真跑、报告不真写。

    ``write_hook`` 让调用方接管 write_evidence_json（捕获 stats）；缺省用替身。
    """
    monkeypatch.setattr(
        rf, "run_locust_full_shape",
        lambda host, evidence_dir, **kwargs: {"total": {"requests": 1}, "stages": []},
        raising=False,
    )
    monkeypatch.setattr(
        rf, "write_evidence_json",
        write_hook or (lambda *a, **k: tmp_path / "summary.json"),
        raising=False,
    )
    monkeypatch.setattr(
        rf, "generate_final_report",
        lambda stats, args: "# report",
        raising=False,
    )
    monkeypatch.setattr(
        rf, "compare_to_baseline", lambda stats, baseline: None, raising=False,
    )
    monkeypatch.setattr(
        rf, "evaluate_results",
        lambda stats: {
            "overall_pass": True, "evidence_errors": [], "safety_errors": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        rf, "_prepare_external_evidence", lambda args: ({}, None), raising=False,
    )
    # load_guard 真函数需要环境闸门，直接替身。
    class _Decision:
        reason = "ok"

    import tests.load.load_guard as guard

    monkeypatch.setattr(guard, "require_safe_load_target", lambda: _Decision(), raising=False)


def _run_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path, *, skip: bool, errors: list[str] | None,
    write_hook=None,
) -> tuple[int, dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    import tests.load.safety_probes as sp

    # run_probe_evidence 在函数体内延迟 import run_all_probes ⇒ patch 源模块。
    monkeypatch.setattr(sp, "run_all_probes", _fake_run_all_probes(calls, errors=errors), raising=False)
    monkeypatch.setattr(rf, "_admin_token_for_probe", lambda host: "admin-token", raising=False)
    monkeypatch.setattr(rf, "_probe_env_flags", lambda args: (True, "low", "lowpw"), raising=False)
    monkeypatch.setattr(rf, "_probe_pg_dsn", lambda args: None, raising=False)
    _patch_main_edges(monkeypatch, tmp_path, write_hook=write_hook)
    evidence_dir = tmp_path / "evidence"
    # main() 用 argparse 解析真实 sys.argv（pytest 参数会被吃掉）⇒ 换成最小 argv。
    monkeypatch.setattr(
        sys, "argv",
        ["run_final.py", "--evidence-dir", str(evidence_dir),
         *(["--skip-safety-probes"] if skip else [])],
        raising=False,
    )
    rc = rf.main()
    return rc, {"calls": calls, "evidence_dir": evidence_dir}


def test_main_normal_path_runs_probes_before_and_after(monkeypatch, tmp_path):
    """正常链路：before + after 各一次，after 的 safety 进 stats，证据落盘。"""
    rc, ctx = _run_main(monkeypatch, tmp_path, skip=False, errors=None)
    assert rc == 0
    phases = [call["phase"] for call in ctx["calls"]]
    assert phases == ["before", "after"]
    after_file = ctx["evidence_dir"] / "probe_evidence_after.json"
    assert after_file.is_file()
    assert json.loads(after_file.read_text(encoding="utf-8"))["safety"]["event_loss"] == 0
    # readback：run_probe_evidence 单独可调（用手工构造的 _Args）。
    payload = rf.run_probe_evidence(
        phase="after", host="http://probe", evidence_dir=tmp_path, args=_Args(),
    )
    assert payload["safety"] == AFTER_SAFETY


def test_main_skip_branch_does_not_fabricate_safety(monkeypatch, tmp_path):
    """--skip-safety-probes：不调探针；stats 里不得出现伪造的全 0 safety。"""
    captured: dict[str, Any] = {}

    def _capture_write(evidence_dir, stats, evaluation, **kwargs):
        captured["stats"] = stats
        return tmp_path / "summary.json"

    rc, ctx = _run_main(
        monkeypatch, tmp_path, skip=True, errors=None, write_hook=_capture_write,
    )
    assert rc == 0
    assert ctx["calls"] == []
    stats = captured["stats"]
    assert stats.get("probe_meta") == {"skipped": True}
    # 伪造证据即失败：skip 分支不得写入全 0 safety。
    assert "safety" not in stats or stats["safety"] == {}


def test_main_surfaces_probe_errors(monkeypatch, tmp_path):
    """探针报 errors 时原样进 stats['probe_errors']（fail-open 伪造 = 红）。"""
    captured: dict[str, Any] = {}

    def _capture_write(evidence_dir, stats, evaluation, **kwargs):
        captured["stats"] = stats
        return tmp_path / "summary.json"

    rc, ctx = _run_main(
        monkeypatch, tmp_path, skip=False,
        errors=["duplicate_side_effects: missing token"],
        write_hook=_capture_write,
    )
    stats = captured["stats"]
    assert stats.get("probe_errors") == ["duplicate_side_effects: missing token"]
    # safety 仍是探针给的原样（缺键留给校验层 fail-closed），不得在 runner 补 0。
    assert stats["safety"] == AFTER_SAFETY
