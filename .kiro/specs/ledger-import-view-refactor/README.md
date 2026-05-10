# Ledger Import View Refactor — spec 三件套索引

## 背景

B2 + B3 优化把 YG2101 (128MB / 200 万行) 总耗时从基线 19 分钟压到 ~7 分钟，
但剩余瓶颈无法继续压缩：

- **parse 87s**：calamine 全量解码 sheet（Rust 侧），无法再降
- **insert 151s**：PG COPY 写入 200 万行 + 索引维护，PG 吞吐极限
- **activate 127s**：UPDATE 200 万行 `is_deleted=false` + 所有索引同步维护

前两者是 I/O 物理极限无法突破；**activate 127s 是纯架构浪费**——
data 已经在物理表里了，只是切换"哪份是 active"，却要 UPDATE 200 万行。

## 根因

业务查询 **全部** 通过 `Tb*.is_deleted=false` 过滤可见性；pipeline
写入时 `is_deleted=true`（隐藏 staged 数据）；activate 必须物理 UPDATE
把 is_deleted 改为 false 才能让业务查询看到新数据。

这是**"可见性状态存在每一行数据里"**的设计缺陷：200 万行的可见性
切换就要改 200 万行。

## 目标

把"可见性"从**行级字段**升级到**表级 metadata**：
`ledger_datasets.status='active'` 一行 UPDATE 即完成切换。

预期：YG2101 activate 阶段 **127s → <1s**，总耗时 ~400s → ~270s。

## 三件套

- **[requirements.md](./requirements.md)** 22 个需求（功能/非功能/回归）
- **[design.md](./design.md)** 架构设计 + 改造清单 + 迁移步骤 + 风险缓解
- **[tasks.md](./tasks.md)** 3 个 Sprint，细化到单文件改造任务

## 实施原则

1. **原子提交**：所有改造在一个 commit（或一个 PR 内多个小 commit），
   要么全通要么全回滚；绝不留中间状态
2. **强制回归**：改完必须跑完整 pytest + YG4001-30 smoke + YG2101 E2E
3. **可测量效果**：Sprint 完成前后跑 YG2101 实测，写入 dev-history 归档
4. **partial index 保留**：已建的 activate_staged / active_queries 索引
   兼容新架构（dataset_id 查询路径直接走它们）

## 成功判据

- YG2101 E2E 400s → 270s（±10% 波动范围）
- `pytest tests/ledger_import/` 全绿，无测试需要修改才能通过
- `scripts/e2e_full_pipeline_validation.py` 11 阶段通过
- `scripts/e2e_yg4001_smoke.py` 通过
- `DatasetService._set_dataset_visibility` 废弃为 no-op 或删除
- rollback 测试验证过（不仅 activate）

## 失败回退

出问题直接 `git revert`：
- Alembic 迁移 view_refactor_activate_index 保留（不影响）
- dataset_query.py 保留兼容（新签名 + 原行为）
