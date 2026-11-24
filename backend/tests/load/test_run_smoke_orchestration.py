"""A2 编排冒烟的本机单测：判定器与冒烟梯度注入（不起真 locust 进程）。

`run_smoke.py` 的进程编排（fakeserver + master + N worker）由真跑冒烟覆盖
（见 tasks.md A2 交付登记）；本文件钉住的是**判定器与注入契约**：
1. judge_smoke 的四条判据各自独立可红（worker 文件数 / 阶段用户数 / 覆盖秒 / 样本数）；
2. SMOKE_STAGES 经 ``GT_LOAD_SMOKE_STAGES_JSON`` 注入后 ``stage_timeline`` 与
   正式梯度共用同一时间线语义（稳态窗口 = duration − settle）；
3. 未设置注入变量时 stage_timeline 仍是正式 LOAD_STAGES（默认值零漂移）；
4. ``load_stage_stats.SMOKE_STAGES_ENV`` 的非法 JSON/缺字段必须抛错（不能静默回退）。
"""
from __future__ import annotations

import json

import pytest

from tests.load.load_contract import LOAD_STAGES
from tests.load.load_stage_stats import (
    SMOKE_STAGES_ENV,
    stage_timeline,
)
from tests.load.run_smoke import SMOKE_STAGES, judge_smoke


# ---------------------------------------------------------------------------
# judge_smoke 判据
# ---------------------------------------------------------------------------


def _stages(*, users=(10, 20), covered=(3.0, 3.0), requests=(14, 26)) -> list[dict]:
    return [
        {"users": u, "covered_seconds": c, "requests": r, "failures": 0,
         "p95": 2.0, "p99": 4.0}
        for u, c, r in zip(users, covered, requests)
    ]


def test_judge_passes_on_healthy_two_worker_run():
    errors = judge_smoke(
        _stages(), worker_count=2, worker_files=["stage_stats_worker0.json", "stage_stats_worker1.json"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert errors == []


def test_judge_worker_file_count_mismatch_is_error():
    errors = judge_smoke(
        _stages(), worker_count=2, worker_files=["only_one.json"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert any("worker 统计文件数" in e for e in errors)


def test_judge_user_count_drift_is_error():
    errors = judge_smoke(
        _stages(users=(10, 18)), worker_count=2, worker_files=["a", "b"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert any("用户数" in e for e in errors)


def test_judge_short_coverage_is_error():
    # covered=1.0s < required 3.0s：严格下限，必须红。
    errors = judge_smoke(
        _stages(covered=(1.0, 3.0)), worker_count=2, worker_files=["a", "b"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert any("第 0 阶段稳态覆盖" in e for e in errors)
    # covered=3.0s：恰好等于下限，放行（阴性对照）。
    ok = judge_smoke(
        _stages(covered=(3.0, 3.0)), worker_count=2, worker_files=["a", "b"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert not any("稳态覆盖" in e for e in ok)


def test_judge_zero_samples_is_error():
    errors = judge_smoke(
        _stages(requests=(0, 26)), worker_count=2, worker_files=["a", "b"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert any("0 请求" in e for e in errors)


def test_judge_stage_count_mismatch_is_error():
    errors = judge_smoke(
        _stages()[:1], worker_count=2, worker_files=["a", "b"],
        expected_users=(10, 20), min_covered=(3.0, 3.0),
    )
    assert any("阶段数" in e for e in errors)


# ---------------------------------------------------------------------------
# 冒烟梯度注入
# ---------------------------------------------------------------------------


SMOKE_JSON = json.dumps(
    [{"users": s["users"], "spawn_rate": s["spawn_rate"], "duration": s["duration"]}
     for s in SMOKE_STAGES],
    ensure_ascii=False,
)


def test_smoke_injection_produces_two_stage_timeline_with_settle_window(monkeypatch):
    monkeypatch.setenv(SMOKE_STAGES_ENV, SMOKE_JSON)
    timeline = stage_timeline()
    assert [item["users"] for item in timeline] == [10, 20]
    for item, stage in zip(timeline, SMOKE_STAGES):
        ramp = stage["users"] / stage["spawn_rate"]
        assert item["required_seconds"] == pytest.approx(stage["duration"] - 5.0)
        assert item["steady_start_s"] == pytest.approx(item["begin_s"] + ramp + 5.0)


def test_without_injection_timeline_is_formal_stages(monkeypatch):
    monkeypatch.delenv(SMOKE_STAGES_ENV, raising=False)
    timeline = stage_timeline()
    assert [item["users"] for item in timeline] == [s["users"] for s in LOAD_STAGES]


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ("[]", "非空"),
        ("{bad json", None),
        ('[{"users": 10}]', "缺"),
    ],
)
def test_invalid_smoke_injection_raises(monkeypatch, payload, why):
    monkeypatch.setenv(SMOKE_STAGES_ENV, payload)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        stage_timeline()


def test_smoke_stages_declaration_matches_injection_shape():
    """SMOKE_STAGES 每阶段稳态必须容得下 settle（防把 5 秒以下的 duration 塞进来）。"""
    for stage in SMOKE_STAGES:
        assert stage["duration"] > 5.0, f"{stage} 稳态时长不足 5 秒 settle"
