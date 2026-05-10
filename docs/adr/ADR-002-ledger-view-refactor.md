# ADR-002：账表导入可见性视图化重构（B' 架构）

**状态**：Sprint 1-2 已实施（2026-05-10），Sprint 3+ 进行中
**决策者**：`ledger-import-view-refactor` spec
**相关代码**：
- `backend/app/services/dataset_service.py` — `activate/rollback/_set_dataset_visibility`
- `backend/app/services/dataset_query.py` — `get_active_filter/get_filter_with_dataset_id`
- `backend/app/services/ledger_import/pipeline.py` — `_insert` 写入路径
- `.github/workflows/ci.yml` — B' view refactor guard 防回归

---

## 背景

### 性能瓶颈
9 家真实样本实测（YG2101 128MB/200 万行）：
- `DatasetService.activate` 耗时 **127-193s**（占总导入时间 30-40%）
- 根因 = `_set_dataset_visibility` UPDATE 200 万行 `is_deleted` 字段
- PG WAL 串行写入 + MVCC（UPDATE = 删旧 tuple + 写新 tuple + 索引维护）

### 架构缺陷
可见性状态（`is_deleted=false` vs `true`）**存在每一行数据里**，而不是元数据层：
- 200 万行切换 = 200 万次物理 UPDATE
- 每次切换产生 200 万 dead tuple，autovacuum 追不上 → 磁盘膨胀
- 并发 activate/rollback 需要锁 200 万行，容易死锁

## 决策

**可见性从"行级 `is_deleted` 字段"升级到"`ledger_datasets.status` 元数据"**

### 核心原则
- 物理行 `is_deleted` 恒为 `false`（除回收站场景）
- 可见性完全由 `ledger_datasets.status = 'active'` 控制
- 查询层统一通过 `dataset_query.get_active_filter` 过滤：`project_id + year + dataset_id(当前 active) + is_deleted=false（兜底）`

### 四路径改造对比

| 路径       | 改造前                         | 改造后                   |
|----------|----------------------------|------------------------|
| activate | UPDATE 新旧两份各 200 万行       | UPDATE 2 行元数据         |
| rollback | UPDATE 新旧两份                | UPDATE 2 行元数据         |
| failed   | 物理 DELETE staged 行         | 保持不变                 |
| purge    | 无                          | 定期 DELETE 超过 N 代 superseded |

### 代码层收束
- `DatasetService.activate/rollback` 去除 `_set_dataset_visibility` 调用
- `_set_dataset_visibility` 保留签名（兼容），实现改为 `logger.warning + return None`
- pipeline `_insert` 写入 `is_deleted=False`（之前是 True，靠 activate 批量 UPDATE 成 False）
- 业务查询 40+ 处统一走 `get_active_filter`，禁止直接 `TbX.is_deleted == False`

## Sprint 执行顺序（重要）

**原设计 Sprint 1→2→3 无法独立运行**：
- 若先改 activate/写入 → 业务查询仍查 `is_deleted`，活化后看不到新数据
- 若写入改 false 但 activate 仍 UPDATE → 老查询能看到 staged 数据（重复显示）

**正确顺序**：
1. **Sprint 1（业务查询迁移，26 task）**：15 service + 2 router 的 40+ 处 `TbX.is_deleted == False` 迁移到 `get_active_filter`；6 处 raw SQL 改为 EXISTS 子查询。此阶段语义不变（`get_active_filter` 返回 `dataset_id + is_deleted=false` 双条件）。
2. **Sprint 2（原子 commit）**：一次性改 activate/rollback + `_set_dataset_visibility` no-op + 写入改 false。必须一起测试再提交。
3. **Sprint 3+（加固/文档）**：CI grep 卡点、集成测试、ADR、运维规约。

## 迁移策略（三阶段）

| 阶段  | 动作 | 效果 |
|------|------|------|
| Day 0 | Deploy B' 代码 | 新导入写 false / 查询走 dataset_id；**老 is_deleted=true 数据靠 fallback 仍可见** |
| Day 7 | 一次性 UPDATE 老 active 行 `is_deleted=false`（Alembic 迁移，分块执行） | 所有 active 数据 is_deleted=false 一致 |
| Day 30 | `DROP INDEX CONCURRENTLY idx_tb_*_activate_staged`（55MB 回收） | 稳定后移除废弃索引 |

## 性能收益（预期）

| 指标                     | 改造前    | B' 改造后   |
|------------------------|--------|---------|
| YG2101 activate 阶段    | 127-193s | **<1s** |
| YG2101 总耗时            | 400-482s | **<300s** |
| 磁盘 dead tuple 累积     | 每次 activate +200 万 | **0** |
| rollback 耗时            | 127s   | **<1s** |

## 回滚方案

- **Sprint 1 单文件改错**：`git checkout <file>`；`get_active_filter` 兜底分支仍返回 `is_deleted=false` 能看到数据
- **Sprint 2 原子 commit 失败**：`git reset --hard HEAD~1` 回退整组；Sprint 1 的查询迁移不会失效（仍语义正确）
- **生产灰度失败**：feature flag `ledger_import_view_refactor_enabled` 项目级关闭，单项目降级老逻辑（F19 独立 Sprint 实施）

## 风险 + 缓解

### 风险 1：漏改查询 → 前端看到旧数据
- CI grep 卡点防回归：`backend-lint` job 扫 `TbX.is_deleted ==` 命中 > baseline 即 fail（2026-05-10 baseline=6，均为 year=None 兜底）
- `get_active_filter` 兜底：dataset 不可达时降级 `is_deleted=false`

### 风险 2：activate 失败数据不一致
- 改造前：部分 UPDATE + 部分未 UPDATE 可能数据混乱
- 改造后：只改 2 行元数据，事务回滚即可；物理数据不动 **更安全**

### 风险 3：rollback 语义变化
- 旧行（`status=rolled_back`）的物理数据仍在表里，但业务查询自然看不到（`get_active_filter` 靠 `status='active'`）
- 集成测试 `backend/tests/integration/test_dataset_rollback_view_refactor.py` 覆盖

### 风险 4：并发项目互相污染
- 靠 `project_id` 隔离（四表均有）；跨项目 staged/active 数据不交叉
- 集成测试覆盖：`test_project_isolation_staged_does_not_leak_across_projects`

### 风险 5：历史 `dataset_id=NULL` 老行
- `get_active_filter` 兜底分支仍用 `is_deleted=false`，历史数据仍可见
- 未来如要彻底清理，需先 migration 回填 dataset_id

## 规约沉淀

### 强制规则（CI 卡点）
1. **业务查询禁用 `TbX.is_deleted == False`**（Tb* = TbBalance/TbLedger/TbAuxBalance/TbAuxLedger）
2. **四表查询必须走 `get_active_filter(db, TbX.__table__, project_id, year)`**
3. **year=None 场景用 Template B**：`LedgerDataset` 子查询 + `dataset_id.in_(active_ids)` + `is_deleted=false` 兜底

### 允许清单（CI baseline=6）
- `wp_chat_service.py` `generate_ledger_analysis` year=None 兜底
- `sampling_enhanced_service.py` `analyze_aging` year=None 兜底
- `report_trace_service.py` `trace_section` year=None 兜底
- `ocr_service_v2.py` `match_with_ledger` year=None 跨年匹配
- `routers/report_trace.py` `aux_summary` year=None 兜底（2 处）

### 写入路径
- pipeline 新写入统一 `is_deleted=False`
- 回收站 / archive / restore 场景仍用 `is_deleted=true`（见 `data_lifecycle_service.py`、`ledger_data_service.py` 软删除）
