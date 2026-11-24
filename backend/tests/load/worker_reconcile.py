"""A5 本机部分：多 worker 进度读侧聚合 + 失效（stale 广播）对账探针。

spec: `platform-capacity-acceptance-and-heavy-defect-closure` A5。
tasks.md A5 登记「进度读侧聚合与失效对账探针本机可做；多 worker 实跑需容量环境」。
上游 E2 的架构结论（`_archive/188` tasks.md E2 2026-11-15 更新）：

- ``platform_jobs`` 已 DB 耐久，**跨 worker 认领经 SKIP LOCKED + attempt 围栏**
  （`platform_job_service.claim_next`），「每 job 恰被执行一次」由
  `test_platform_job_fault_injection.py` 5 例钉住 —— 本模块**不重复实现**执行侧，
  只做**读侧聚合**（每个 worker 行各自的 progress / attempt 汇总成一个总览）；
- 失效状态（``is_stale`` 类标记）经 EventBus 广播在多 worker 下天然跨进程，
  补**对账探针**：广播方写下的序列号 vs 两个 adapter（内存/Redis）各自视角的
  可见序列，缺口即丢失、重复即重放。

两个入口（runner 编排职责，不经 HTTP）：

- ``aggregate_job_progress(rows)``：把每个 worker 上报的 job 行聚合成
  总览（按 operation 分组计 running/succeeded/failed、进度求和、
  attempt 一致性检查）；纯函数，行来自 DB 查询或 runner 采集。
- ``run_stale_reconcile_probe(broadcast_seq, received_seqs)``：多 worker
  失效广播对账——以 master 广播序列为基准，逐 worker 序列找缺口与重复；
  任一 worker 缺号或重号 ⇒ 计数 > 0（fail-closed，与六类安全计数同形）。

多 worker 2/4/8 实跑仍属 ``[ ]*``：需专用容量环境（≥3 进程 + Redis）。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

__all__ = [
    "STALE_RECONCILE_KEYS",
    "aggregate_job_progress",
    "run_stale_reconcile_probe",
]

#: 对账探针输出的零值键（与六类安全计数同形，随 stage_stats.json 输出）。
STALE_RECONCILE_KEYS: tuple[str, ...] = (
    "stale_event_loss",
    "stale_event_duplicate",
)


def aggregate_job_progress(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """把各 worker 的 job 行聚合成读侧总览。

    每行至少含 ``operation`` / ``status`` / ``progress_current`` /
    ``progress_total`` / ``attempt_count``（与 ``job_snapshot`` 字段同名）；
    ``worker_id`` 可选（有则按 worker 分桶，无则并成一个桶）。

    聚合语义（读侧只读、不改任何行）：

    - 按 operation 分组：各状态计数（queued/running/succeeded/failed/cancelled/
      retry_wait）+ progress 求和 + attempt 不一致检测——同一 operation
      在多 worker 下应共享同一份 DB 行，attempt_count 必须唯一；出现多个
      不同值即「多 worker 各自改了同一 job」⇒ ``attempt_conflicts`` +1。
    - 顶层：总 job 数、各状态计数、progress 合计、attempt_conflicts 总数。
    """
    by_operation: dict[str, dict[str, Any]] = {}
    total = 0
    attempt_conflicts = 0
    for row in rows:
        total += 1
        operation = str(row.get("operation") or "unknown")
        status = str(row.get("status") or "unknown")
        bucket = by_operation.setdefault(
            operation,
            {
                "operation": operation,
                "jobs": 0,
                "status_counts": {},
                "progress_current_sum": 0,
                "progress_total_sum": 0,
                "attempt_values": set(),
            },
        )
        bucket["jobs"] += 1
        bucket["status_counts"][status] = bucket["status_counts"].get(status, 0) + 1
        bucket["progress_current_sum"] += max(0, int(row.get("progress_current") or 0))
        bucket["progress_total_sum"] += max(0, int(row.get("progress_total") or 0))
        bucket["attempt_values"].add(int(row.get("attempt_count") or 0))
    for bucket in by_operation.values():
        if len(bucket.pop("attempt_values")) > 1:
            attempt_conflicts += 1
            bucket["attempt_conflict"] = True
    status_totals: dict[str, int] = {}
    for bucket in by_operation.values():
        for status, count in bucket["status_counts"].items():
            status_totals[status] = status_totals.get(status, 0) + count
    return {
        "total_jobs": total,
        "status_totals": status_totals,
        "attempt_conflicts": attempt_conflicts,
        "operations": sorted(by_operation.values(), key=lambda item: item["operation"]),
    }


def run_stale_reconcile_probe(
    broadcast_seq: Iterable[int],
    received_seqs: Mapping[str, Iterable[int]],
) -> dict[str, int | dict[str, Any]]:
    """失效（stale）广播对账：master 序列 vs 各 worker 视角序列。

    - ``broadcast_seq``：master 广播的事件序号全量（如 EventBus 广播
      ``is_stale`` 标记时写下的递增 id）。
    - ``received_seqs``：每个 worker 收到的序号序列（worker_id → 序号列表）。

    判定（fail-closed）：

    - **丢失**：某 worker 序列里缺 master 集合中的号 ⇒ ``stale_event_loss`` +1/号；
    - **重复**：某 worker 序列里同一号出现两次 ⇒ ``stale_event_duplicate`` +1/号；
    - ``per_worker`` 明细列出各 worker 的丢失/重复清单，便于定位是哪条链路丢的。
    """
    expected = sorted({int(seq) for seq in broadcast_seq})
    expected_set = set(expected)
    total_loss = 0
    total_duplicate = 0
    per_worker: dict[str, dict[str, Any]] = {}
    for worker_id, raw in received_seqs.items():
        seqs = [int(seq) for seq in raw]
        counter = Counter(seqs)
        lost = sorted(expected_set - set(counter))
        duplicated = sorted(seq for seq, count in counter.items() if count > 1)
        total_loss += len(lost)
        total_duplicate += len(duplicated)
        per_worker[str(worker_id)] = {
            "received": len(seqs),
            "lost": lost,
            "duplicated": duplicated,
        }
    return {
        "stale_event_loss": total_loss,
        "stale_event_duplicate": total_duplicate,
        "per_worker": per_worker,
    }
