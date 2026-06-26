# Requirements Document

## Introduction

底稿数据有 4 条写入路径（wp_html_save / wp_editor_router / onlyoffice_callback / custom_query.snapshot_writer），各自独立实现乐观锁（4 种字段）、事件发布（其中一条发到孤立总线）、stale 标记、审计日志。行为不一致且维护负担重。

本 spec 抽取 `WorkpaperSaveOrchestrator` 统一后处理层：所有写入路径在完成"数据写入"后调同一函数做版本递增 + stale 标记 + 审计日志 + 事件发布 + 乐观锁字段更新。

覆盖条目：§2.2/§2.17/§5.7/§5.8/§5.14/§10.1。

## Glossary

- **file_version**：`working_paper` 表的版本号字段，作为统一乐观锁
- **孤立总线**：`custom_query/metrics._EventBus`，独立于主 event_bus，无下游订阅者

## Requirements

### Requirement 1: 统一后处理函数

**User Story:** As a 底稿模块维护者, I want 所有保存路径共享同一后处理逻辑, so that 事件发布/版本/审计行为一致。

#### Acceptance Criteria

1. WHEN 任一写入路径成功写入数据后 THEN 调用 `WorkpaperSaveOrchestrator.after_save(db, wp, user, trigger, extra)` 统一执行后处理
2. WHEN `after_save` 执行 THEN 系统 SHALL 递增 `file_version`、标记 `prefill_stale=True`、写审计日志、发布 `WORKPAPER_SAVED` 到主 event_bus
3. WHEN custom_query 写回路径调用 `after_save` THEN 系统 SHALL 发布到主 event_bus（而非孤立本地总线），触发下游 stale/cross_ref/SSE

### Requirement 2: 统一乐观锁

**User Story:** As a 并发用户, I want 所有路径共用同一冲突检测字段, so that 不同路径并发写时能互相感知。

#### Acceptance Criteria

1. WHEN `after_save` 执行 THEN `file_version` 单调递增作为统一乐观锁字段
2. WHEN 任一路径提交写入且 `expected_version != current file_version` THEN 返回 409 冲突
3. WHEN html_save/univer_save/onlyoffice/custom_query 并发写同一底稿 THEN 后提交者检测到冲突

### Requirement 3: 删除孤立 EventBus

**User Story:** As a 代码维护者, I want 系统只保留一个 EventBus, so that 事件总线语义清晰。

#### Acceptance Criteria

1. WHEN `custom_query.metrics._EventBus` 被删除 THEN snapshot_writer 改用主 `event_bus.publish`
2. WHEN snapshot_writer 写回成功 THEN 主 event_bus 接收 `WORKPAPER_SAVED` → 触发 cross_ref 检测 + SSE + stale 传播
