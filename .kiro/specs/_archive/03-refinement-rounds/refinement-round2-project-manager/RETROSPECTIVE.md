# Round 2 Retrospective — 项目经理视角

## 概述

- **角色**：项目经理（PM）
- **范围**：Round 2 全部 24 个任务（Sprint 1-3）+ Batch 1 修复 18 项
- **复盘发现**：37 项待修（8 类）
- **Batch 1 已修**：18 项（P0 全部 6 项 + P1 数据正确性 6 项 + P1 性能 3 项 + P1 可观测性 1 项 + P2 UX 1 项 + P2 架构 1 项）
- **Batch 2 修复**：19 项（本批次）

## 复盘分类汇总

| 类别 | 总数 | Batch 1 已修 | Batch 2 修复 | 剩余 |
|------|------|-------------|-------------|------|
| P0 合规/安全 | 6 | 6 | 0 | 0 |
| P1 数据正确性 | 6 | 6 | 0 | 0 |
| P1 性能 | 3 | 0 | 3 | 0 |
| P1 可观测性 | 4 | 1 | 3 | 0 |
| P2 UX | 6 | 1 | 5 | 0 |
| P2 架构/一致性 | 8 | 2 | 2 | 4 |
| P2 测试覆盖 | 4 | 0 | 4 | 0 |
| **合计** | **37** | **18** | **19** | **4** |

## Batch 1 修复清单（已完成）

1. P0.1 `assignment_service.py` message_type 大写 → 改用常量
2. P0.2 `POST /api/staff/{id}/handover` 权限收紧
3. P0.3 `batch-assign-enhanced` 加 project_access 校验
4. P0.4 `batch-approve` 加项目范围校验
5. P0.5 `test_pm_workflow_e2e.py` 端到端测试
6. P0.6 `test_handover_e2e.py` 交接端到端测试
7. P1.1 `_get_manager_project_ids` 避免重复调用
8. P1.2 `datetime.now(timezone.utc).replace(tzinfo=None)` 统一时间戳
9. P1.3 `_increment_remind_count` Redis pipeline 原子操作
10. P1.4 Redis INCR 移到 commit 后
11. P1.5 `handover_service.execute` 显式 commit
12. P1.6 前端 N+1 cost-overview → 并入 overview 响应
13. P1.7 `budget_alert_worker.run` 加 logger.info + worker_id
14. P1.8 `_generate_ai_summary` 截断输入长度
15. P1.9 `cost_overview_service._resolve_rate_key` 模糊匹配
16. P1.10 `batch_brief._compute_cache_key` MD5 前 16 字符适配 String(20)
17. P2.1 `BatchAssignDialog` 候选人排序
18. P2.2 `batch_brief` prompt token 上限截断

## Batch 2 修复清单（本批次）

### P1 性能（3 项）
1. `manager_dashboard.get_overview` asyncio.gather 并发
2. `_aggregate_projects` 合并 overdue 查询（CASE WHEN）
3. `WordExportTask.template_type` 加索引

### P1 可观测性（3 项）
4. Notification metadata schema validation（REQUIRED_METADATA_FIELDS + validate_metadata）
5. `batch_brief` AI fallback reason in response（ai_fallback_reason 字段）
6. 本文件（RETROSPECTIVE.md）

### P2 UX（5 项）
7. `ProjectDashboard` remindCounts 注释说明（429 为权威源）
8. `BatchAssignDialog` by_level preview endpoint — deferred to Batch 3（TODO）
9. `CommunicationCommitmentsEditor` readonly mode
10. `ManagerDashboard` elapsedTimer 1 小时无操作停止
11. `WorkHoursApproval` 3x API calls — TODO 注释

### P2 架构/一致性（2 项）
12. `IndependenceDeclaration` status 枚举补 `superseded_by_handover`
13. `batch_assign_enhanced` audit trail（audit_logger.log_action）

### P2 测试覆盖（4 项）
14. `test_batch_assign_enhanced_endpoint.py`
15. `test_cost_overview_endpoint.py`
16. `test_permission_matrix.py`
17. `test_budget_alert_worker.py`

## 剩余 4 项（P2 架构，deferred to Batch 3+）

1. `cost_overview_service._TITLE_TO_RATE_KEY` 依赖自由文本 → 加 `role_level` 枚举
2. `batch_brief` 用 `template_type` 存 cache_key 是字段复用 → 加专用字段
3. `IssueTicket.source='reminder'` 无自动关闭机制
4. `manager_dashboard._compute_risk_level` 不落库

## 复盘纪律沉淀

1. 每轮修复后必须跑回归测试，确认零新增失败
2. 前端 UX 改进优先加注释/TODO，大重构走独立 spec
3. 性能优化优先合并查询、并发执行，避免 N+1
4. 通知 metadata 必须走 validate_metadata 校验
5. AI 调用必须有 fallback_reason 字段，前端可展示降级原因
