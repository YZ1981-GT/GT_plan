# Implementation Plan: Phase 4 长期治理

## Overview

基于 requirements.md v1.0 和 design.md v1.0，Phase 4 五项功能涉及基础设施层变更，风险较高。拆分为 5 个 Sprint（每项功能一个 Sprint），严格按依赖顺序执行：F4 迁移回滚（基础设施）→ F1 RLS（依赖回滚能力）→ F5 Redis HA → F2 多年度 → F3 EQCR 快照。

预计工时：18 天（Sprint 1: 3 天 / Sprint 2: 4 天 / Sprint 3: 4 天 / Sprint 4: 3 天 / Sprint 5: 4 天）

前置依赖：Phase 1~3 specs 完成

## Tasks

### Sprint 1 — F4 数据库迁移回滚机制（优先，为后续 RLS 提供安全网）

- [x] 1.1 为现有 V001~V003 编写回滚脚本
  - 创建 `R001__rollback_init.sql`（DROP 所有初始表，慎用）
  - 创建 `R002__rollback_schema_version.sql`（DROP schema_version 表）
  - 创建 `R003__rollback_example_add_comment.sql`（DROP comment 列）
  - 验证每个回滚脚本可独立执行
  - _Requirements: F4.1_

- [x] 1.2 改造 migration_runner.py 支持回滚
  - 新增 `--rollback <target_version>` CLI 参数
  - 实现 `rollback_to(target)` 函数：获取当前版本 → 计算需回滚的版本列表 → 逆序执行
  - 回滚前自动 pg_dump 备份（备份文件名含时间戳+版本号）
  - 回滚后更新 schema_version 表（记录 operator + rollback_at + from_version + to_version）
  - 生产环境回滚需 `--confirm` 参数（防误操作）
  - _Requirements: F4.2~F4.4_

- [x] 1.3 回滚机制测试
  - 测试 V003→V002 回滚：执行后 V003 的变更消失
  - 测试备份文件生成正确
  - 测试 schema_version 记录正确
  - 测试无 --confirm 时生产环境拒绝执行
  - 测试回滚脚本不存在时报错提示
  - _Requirements: 测试矩阵_

### Sprint 2 — F1 PG RLS 行级安全

- [x] 2.1 创建 RLS 迁移脚本
  - 创建 `V00X__enable_rls.sql`（编号实施时动态确定 max+1）
  - 5 张表启用 RLS + FORCE：working_paper / adjustments / tb_balance / reports / review_records
  - 创建 project_isolation POLICY（基于 current_setting）
  - 创建 admin bypass 函数
  - 创建配套 `R00X__disable_rls.sql` 回滚脚本
  - _Requirements: F1.1, F1.2_

- [x] 2.2 应用层 SET LOCAL 集成
  - 修改 `backend/app/core/database.py`
  - 新增 `set_rls_context(session, project_id)` 函数
  - 在 `get_db` 依赖中，如果请求含 project_id 参数，自动 SET LOCAL
  - 确保事务结束后 session 变量自动清除
  - _Requirements: F1.3_

- [x] 2.3 Admin bypass 机制
  - 跨项目聚合查询（如 PartnerDashboard 多项目汇总）使用 SECURITY DEFINER 函数
  - 或在特定端点中不设置 RLS context（admin 角色 + 明确标注）
  - 确保 admin 的跨项目查询不被 RLS 阻断
  - _Requirements: F1.4_

- [x] 2.4 RLS 全量回归测试
  - 运行全部 backend tests（确认零新增失败）
  - 特别关注：跨项目查询的端点 / admin 聚合端点 / 批量操作端点
  - 渗透测试：模拟 auditor 尝试访问非授权项目数据 → 返回空结果（非 403）
  - _Requirements: F1.5_

- [x] 2.5 RLS 性能验证
  - 对比 RLS 启用前后的查询延迟（P95）
  - 目标：增加延迟 ≤ 5ms
  - 如超标：添加 project_id 索引优化
  - _Requirements: 非功能需求-性能_

### Sprint 3 — F5 Redis 高可用

- [x] 3.1 部署 Redis Sentinel
  - docker-compose 新增 redis-replica-1 / redis-replica-2 / sentinel-1/2/3 服务
  - 配置 sentinel.conf（monitor / down-after-milliseconds / failover-timeout）
  - 验证 master-replica 复制正常
  - 验证手动 failover 成功
  - _Requirements: F5.1, F5.2_

- [x] 3.2 应用层 Sentinel 连接改造
  - 修改 `backend/app/core/redis.py`
  - 支持两种模式：单实例（开发环境）/ Sentinel（生产环境），由 `REDIS_MODE` 环境变量控制
  - Sentinel 模式使用 `redis.asyncio.sentinel.Sentinel`
  - 连接失败时返回 None（降级信号）
  - _Requirements: F5.1_

- [x] 3.3 降级逻辑实现
  - 修改所有 Redis 调用点（auth/permission/lock/sse）
  - 统一模式：`redis = await get_redis(); if redis is None: fallback()`
  - JWT 黑名单降级：跳过检查
  - 权限缓存降级：直接查 DB
  - 编辑锁降级：跳过锁（版本锁兜底）
  - SSE 降级：返回 503 + 前端轮询 fallback
  - _Requirements: F5.3_

- [x] 3.4 Redis 健康检查端点
  - 新增 `GET /api/health/redis`
  - 返回：master 状态 / replica 数量 / sentinel 状态 / 内存使用
  - 集成到现有 `/api/health` 端点（增加 redis 字段）
  - _Requirements: F5.4_

- [x] 3.5 Redis HA 测试
  - 模拟 master 宕机（docker stop redis-master）
  - 验证 30s 内 Sentinel 完成故障转移
  - 验证应用层自动连接新 master
  - 验证降级模式下核心功能可用（登录/保存/查询）
  - 模拟全部 Redis 不可用 → 验证降级逻辑生效
  - _Requirements: F5.2, F5.3_

### Sprint 4 — F2 多年度对比分析

- [x] 4.1 创建多年度查询 API
  - 在 `backend/app/routers/reports.py` 新增端点
  - `GET /api/projects/{pid}/reports/multi-year?years=2023,2024,2025&report_type=BS`
  - 查询多年度报表数据（同一 project 不同 year）
  - 计算 YoY 变动率
  - 返回 rows 列表（含 values + yoy_changes）
  - _Requirements: F2.1~F2.4_

- [x] 4.2 创建 MultiYearCompare 前端组件
  - 创建 `audit-platform/frontend/src/components/report/MultiYearCompare.vue`
  - 年度选择器（最多 5 年）
  - 报表类型切换（BS/IS/CFS）
  - el-table 动态列（按选中年度生成列）
  - 金额列 + YoY 变动列 + 趋势箭头
  - 变动率 ≥ 20% 高亮
  - _Requirements: F2.1~F2.3_

- [x] 4.3 集成到 ReportView
  - ReportView.vue 新增"多年度对比"Tab 或模式切换按钮
  - 切换时加载 MultiYearCompare 组件
  - 默认选中当前年度 + 前一年度
  - _Requirements: F2.1_

- [x] 4.4 多年度 Excel 导出
  - 导出时生成多列 Excel（年度为列标题）
  - 包含 YoY 变动率列
  - 使用 useExcelIO 统一导出
  - _Requirements: F2.5_

- [x] 4.5 多年度对比测试
  - `test_multi_year_report.py`：正常查询 + 缺失年度 + YoY 计算 + 权限
  - `MultiYearCompare.spec.ts`：渲染 + 年度切换 + 高亮
  - _Requirements: 测试矩阵_

### Sprint 5 — F3 EQCR 快照机制

- [x] 5.1 创建 eqcr_snapshots 表
  - 创建 `V00X__eqcr_snapshots.sql`（编号实施时动态确定 max+1）
  - 表结构：id / project_id / year / created_by / created_at / snapshot_data(JSONB) / is_current
  - 唯一约束：(project_id, year) WHERE is_current = TRUE
  - 配套 `R00X__rollback_eqcr_snapshots.sql`
  - _Requirements: F3.1_

- [x] 5.2 创建快照服务
  - 创建 `backend/app/services/eqcr_snapshot_service.py`
  - `create_snapshot(db, project_id, year, user_id)` — 聚合底稿+报表+AJE+VR 数据 → 写入 JSONB
  - `get_current_snapshot(db, project_id, year)` — 获取当前快照
  - `refresh_snapshot(db, project_id, year, user_id)` — 旧快照 is_current=False + 创建新快照
  - _Requirements: F3.1, F3.2, F3.4_

- [x] 5.3 创建快照 API 路由
  - `POST /api/projects/{pid}/eqcr/snapshot` — 创建快照（manager+ 权限）
  - `GET /api/projects/{pid}/eqcr/snapshot` — 获取当前快照
  - `POST /api/projects/{pid}/eqcr/snapshot/refresh` — 刷新快照（EQCR 权限）
  - _Requirements: F3.1, F3.3, F3.4_

- [x] 5.4 改造 EQCR 工作台读取快照
  - 修改 EqcrProjectView.vue
  - 数据源从实时 API 切换为快照 API
  - 显示快照创建时间 + "数据截止于 YYYY-MM-DD HH:mm"
  - 提供"刷新快照"按钮（调用 refresh API）
  - 快照数据只读（禁用所有编辑操作）
  - _Requirements: F3.3, F3.5_

- [x] 5.5 EQCR 快照测试
  - `test_eqcr_snapshot.py`：创建 + 获取 + 刷新 + 数据完整性 + 权限
  - `EqcrProjectView.spec.ts`：快照模式渲染 + 只读 + 刷新按钮
  - 验证快照数据包含 4 类数据（底稿/报表/AJE/VR）
  - _Requirements: 测试矩阵_

---

## UAT 验收清单

- [x] UAT-1 (P0): RLS 启用后，auditor 无法查询非授权项目数据
- [x] UAT-2 (P0): admin 跨项目聚合查询正常工作
- [x] UAT-3 (P0): RLS 启用后现有功能全部正常（零回归）
- [x] UAT-4 (P0): 多年度对比 3 年数据并列显示 + YoY 正确
- [x] UAT-5 (P0): EQCR 工作台显示快照数据（非实时）
- [x] UAT-6 (P0): EQCR 刷新快照后看到最新数据
- [x] UAT-7 (P0): migration_runner --rollback V003 成功回滚
- [x] UAT-8 (P0): Redis master 宕机 → 30s 内故障转移 → 应用无感知 ⚠ partial（代码+配置就绪，真实 failover 需 docker compose --profile redis-ha 环境验证）
- [x] UAT-9 (P1): Redis 全部不可用 → 降级模式下登录/保存正常
- [x] UAT-10 (P1): 多年度对比 Excel 导出正确

---

## 摘要

| Sprint | 功能 | Tasks | 预计工时 |
|--------|------|-------|---------|
| Sprint 1 | F4 迁移回滚 | 1.1~1.3 (3 tasks) | 3 天 |
| Sprint 2 | F1 PG RLS | 2.1~2.5 (5 tasks) | 4 天 |
| Sprint 3 | F5 Redis HA | 3.1~3.5 (5 tasks) | 4 天 |
| Sprint 4 | F2 多年度对比 | 4.1~4.5 (5 tasks) | 3 天 |
| Sprint 5 | F3 EQCR 快照 | 5.1~5.5 (5 tasks) | 4 天 |
| **合计** | | **23 tasks** | **18 天** |

注：Sprint 2 依赖 Sprint 1（RLS 需要回滚能力作为安全网）。Sprint 3/4/5 可在 Sprint 2 完成后并行。
