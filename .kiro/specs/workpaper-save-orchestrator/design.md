# Design Document

## Overview

新建 `backend/app/services/workpaper_save_orchestrator.py`，提供 `after_save(db, wp, user, trigger, extra)` 异步方法。4 条写入路径在完成数据写入后统一调用此方法，该方法按固定顺序执行：file_version++ → prefill_stale=True → 审计日志 → event_bus.publish(WORKPAPER_SAVED)。

## Architecture

```python
class WorkpaperSaveOrchestrator:
    async def after_save(
        self, db, wp: WorkingPaper, user, *,
        trigger: str,  # "html_save" | "univer_save" | "onlyoffice_callback" | "custom_query_writeback"
        extra: dict,   # content_hash, sheets, cells, etc.
        expected_version: int | None = None,  # 乐观锁校验
    ) -> int:  # 返回新 file_version
        # 1. 乐观锁：expected_version != wp.file_version → raise 409
        # 2. wp.file_version += 1
        # 3. wp.prefill_stale = True
        # 4. wp.updated_at = now
        # 5. 审计日志（Log model）
        # 6. event_bus.publish(EventPayload(WORKPAPER_SAVED, ...))
        # 7. flush (不 commit，交由 router)
```

### 迁移策略（渐进）

Phase 1：创建 orchestrator + 让 snapshot_writer 调用（消除孤立总线 §5.7/§5.8）。
Phase 2：wp_html_save / wp_editor_router 迁移（统一乐观锁 §2.17）。
Phase 3：onlyoffice_callback 迁移（需适配 docserver 回调语义）。

### 删除 `custom_query.metrics._EventBus`

Phase 1 中 snapshot_writer 改用 `from app.services.event_bus import event_bus` 后，删除 `metrics.py` 中的 `_EventBus` 类和 `event_bus` 实例。

## Components and Interfaces

- **`WorkpaperSaveOrchestrator`** — `backend/app/services/workpaper_save_orchestrator.py`，提供 `after_save(db, wp, user, trigger, extra, expected_version)` 异步方法，统一后处理逻辑

## Data Models

N/A — 无新表。使用现有 `working_paper.file_version` 字段作为统一乐观锁。

## Correctness Properties

Property 1: 所有路径 after_save 后 file_version 单调递增

Property 2: event_bus 收到 WORKPAPER_SAVED → cross_ref/stale/SSE 触发（与 html_save 一致）

Property 3: 并发写同一 wp → 后提交者 409（无论哪条路径）

## Testing Strategy

- Unit：mock 4 路径 → verify after_save 被调用 + file_version 递增
- PBT：随机并发 (trigger_A, trigger_B) → 恰好一个成功一个 409
- Integration：snapshot_writer writeback → verify SSE event received
