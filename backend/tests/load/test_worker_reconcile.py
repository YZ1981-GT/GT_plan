"""A5 本机单测：进度读侧聚合 + 失效广播对账探针的判定语义。

spec: `platform-capacity-acceptance-and-heavy-defect-closure` A5。
判据与 run_stale_reconcile_probe / aggregate_job_progress 的 docstring 一一对应，
每条都有独立可红的反向形态（并发会话既有变异纪律：判据「红在哪个断言」须可点名）。
"""
from __future__ import annotations

import pytest

from tests.load.worker_reconcile import (
    STALE_RECONCILE_KEYS,
    aggregate_job_progress,
    run_stale_reconcile_probe,
)


# ---------------------------------------------------------------------------
# aggregate_job_progress
# ---------------------------------------------------------------------------


def test_aggregate_empty_rows_is_zero_not_error():
    """空行集 = 全零总览，不抛错（读侧对空项目也要能出报告）。"""
    report = aggregate_job_progress([])
    assert report["total_jobs"] == 0
    assert report["status_totals"] == {}
    assert report["attempt_conflicts"] == 0
    assert report["operations"] == []


def test_aggregate_sums_progress_across_workers():
    """两个 worker 各跑一半的同一 operation：进度求和、状态计数分开。"""
    rows = [
        {"operation": "export", "status": "succeeded", "progress_current": 500, "progress_total": 500, "attempt_count": 1},
        {"operation": "export", "status": "running", "progress_current": 300, "progress_total": 500, "attempt_count": 1},
    ]
    report = aggregate_job_progress(rows)
    assert report["total_jobs"] == 2
    assert report["status_totals"] == {"succeeded": 1, "running": 1}
    bucket = report["operations"][0]
    assert bucket["progress_current_sum"] == 800
    assert bucket["progress_total_sum"] == 1000
    assert "attempt_conflict" not in bucket


def test_aggregate_flags_attempt_conflict():
    """同一 operation 出现两个不同 attempt_count ⇒ attempt_conflicts 计数 +1。"""
    rows = [
        {"operation": "export", "status": "succeeded", "progress_current": 100, "attempt_count": 1},
        {"operation": "export", "status": "succeeded", "progress_current": 100, "attempt_count": 2},
    ]
    report = aggregate_job_progress(rows)
    assert report["attempt_conflicts"] == 1
    assert report["operations"][0].get("attempt_conflict") is True


def test_aggregate_negative_progress_clamped_to_zero():
    """脏数据 progress 为负数按 0 计（读侧不放大脏数据）。"""
    report = aggregate_job_progress([
        {"operation": "x", "status": "running", "progress_current": -5, "attempt_count": 1},
    ])
    assert report["operations"][0]["progress_current_sum"] == 0


def test_aggregate_missing_fields_do_not_crash():
    """缺 operation/status 的行落 unknown 桶（fail-open 到可见，不抛错）。"""
    report = aggregate_job_progress([{"progress_current": 3}])
    assert report["total_jobs"] == 1
    assert report["operations"][0]["operation"] == "unknown"
    assert report["status_totals"] == {"unknown": 1}


# ---------------------------------------------------------------------------
# run_stale_reconcile_probe
# ---------------------------------------------------------------------------


def test_probe_all_workers_clean_is_zero():
    """两个 worker 都完整收到 1..5 ⇒ 两类计数全 0。"""
    report = run_stale_reconcile_probe(
        broadcast_seq=[1, 2, 3, 4, 5],
        received_seqs={"w1": [1, 2, 3, 4, 5], "w2": [1, 2, 3, 4, 5]},
    )
    assert report["stale_event_loss"] == 0
    assert report["stale_event_duplicate"] == 0


def test_probe_counts_loss_per_worker():
    """w1 丢 3、w2 丢 2 和 5 ⇒ loss=3（逐号计数，不是按 worker 数）。"""
    report = run_stale_reconcile_probe(
        broadcast_seq=[1, 2, 3, 4, 5],
        received_seqs={"w1": [1, 2, 4, 5], "w2": [1, 3, 4]},
    )
    assert report["stale_event_loss"] == 3
    assert report["per_worker"]["w1"]["lost"] == [3]
    assert report["per_worker"]["w2"]["lost"] == [2, 5]


def test_probe_counts_duplicate():
    """同一号收到两次 ⇒ duplicate +1（重放的 worker 暴露出来）。"""
    report = run_stale_reconcile_probe(
        broadcast_seq=[1, 2, 3],
        received_seqs={"w1": [1, 2, 2, 3]},
    )
    assert report["stale_event_duplicate"] == 1
    assert report["per_worker"]["w1"]["duplicated"] == [2]
    assert report["stale_event_loss"] == 0


def test_probe_worker_extra_ids_are_ignored_not_loss():
    """worker 收到 master 没广播的号（如其他项目事件）：不算丢也不算重复。"""
    report = run_stale_reconcile_probe(
        broadcast_seq=[1, 2, 3],
        received_seqs={"w1": [1, 2, 3, 99]},
    )
    assert report["stale_event_loss"] == 0
    assert report["stale_event_duplicate"] == 0


def test_probe_keys_match_zero_contract():
    """输出的零值键与 STALE_RECONCILE_KEYS 一致（随 stage_stats 输出的契约面）。"""
    report = run_stale_reconcile_probe(broadcast_seq=[1], received_seqs={"w": [1]})
    assert set(report) >= set(STALE_RECONCILE_KEYS)
    assert STALE_RECONCILE_KEYS == ("stale_event_loss", "stale_event_duplicate")


@pytest.mark.parametrize("mutation", ["loss", "duplicate"])
def test_probe_detects_each_fault_shape(mutation: str):
    """两类故障各自独立可红（变异等价物：注入丢失/重放的输入必被计数）。"""
    seq = [1, 2, 3]
    if mutation == "loss":
        received = {"w1": [1, 3]}
    else:
        received = {"w1": [1, 2, 2, 3]}
    report = run_stale_reconcile_probe(broadcast_seq=seq, received_seqs=received)
    if mutation == "loss":
        assert report["stale_event_loss"] == 1
        assert report["stale_event_duplicate"] == 0
    else:
        assert report["stale_event_duplicate"] == 1
        assert report["stale_event_loss"] == 0
