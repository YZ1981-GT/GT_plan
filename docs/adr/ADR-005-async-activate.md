# ADR-005: 异步 Activate — 用户不等 200 万行 metadata 切换

**Status**: Proposed  
**Date**: 2026-05-11  
**Deciders**: 平台架构组

## Context

B' 架构下 `DatasetService.activate` 只修改 `ledger_datasets.status`（<1s），
用户体验已大幅改善。但未来如果需要做以下后处理，用户不应等待：

- integrity check（COUNT 校验 staged 行数 vs record_summary）
- `rebuild_aux_balance_summary`（辅助余额汇总重建）
- 下游 stale 标记（Workpaper/AuditReport/DisclosureNote `is_stale=true`）
- outbox event 广播（项目组 SSE 推送）

当前 activate 已 <1s 不急，但为未来 200 万行 rebuild 或跨服务调用预留。

## Decision

Pipeline 写入完成后立即返回 `status=completed`，activate 作为后台 task 异步执行。
前端通过 `GET /active-job` 轮询看到 `phase=activating` 直到完成。

实现草案：

```python
# pipeline.py 最后一步
async def _finalize(self, job: ImportJob, dataset_id: UUID):
    await self._persist_progress(job, phase="activating")
    fire_and_forget_activate(dataset_id, job_id=job.id)
    # 不 await — 用户感知到 "写完即完成"
```

`fire_and_forget_activate` 内部：
1. `DatasetService.activate(dataset_id)`
2. `rebuild_aux_balance_summary(dataset_id)`
3. 下游 stale 标记
4. `ImportJob.status = completed`（最终态）

## Consequences

**正面**：
- 用户感知从"写完等 activate"变成"写完即完成"
- YG2101 场景用户等待从 ~660s 降到 ~530s（省 activate + rebuild）

**负面**：
- activate 失败需要 `recover_jobs` 兜底（heartbeat 超时 → 重试）
- 前端需区分 `phase=activating`（数据暂不可查）vs `completed`（可查）
- 极端情况：activate 失败但用户已离开，需通知机制

## 当前状态

不急于实施。B' 架构 activate <1s 已满足 YG2101 级别需求。
当 rebuild_aux_summary 或 integrity check 耗时 >5s 时再启动本 ADR。
