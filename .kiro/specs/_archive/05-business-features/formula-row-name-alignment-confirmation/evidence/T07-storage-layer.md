# Task 7 — 映射存储层

产物：
- 迁移 `backend/migrations/V160__workpaper_row_name_mapping.sql`（全 DDL `IF NOT EXISTS` 幂等）
- ORM `backend/app/models/workpaper_row_name_mapping_models.py`
- 服务 `backend/app/services/row_name_mapping_service.py`
- 守卫 `backend/tests/four_table/test_row_name_mapping_service.py`（8 passed）

## 真库应用 + 幂等验证（实测）

一次性脚本对 `audit_platform` 库连续应用 V160 **两遍**均成功（DDL 幂等）：
```
MIGRATION_APPLIED_TWICE_OK
TABLES: ['workpaper_row_name_mapping', 'workpaper_row_name_mapping_target']
INDEXES: ix_row_name_mapping_scope / ix_row_name_mapping_target_identity /
         ix_row_name_mapping_target_mapping / uq_row_name_mapping_active_scope /
         uq_row_name_mapping_idempotency / *_pkey ×2
MAIN_COLS: id project_id year wp_code sheet_code row_key targets match_state
           dataset_fingerprint mapping_version base_mapping_version idempotency_key
           is_active superseded_from confirmed_by confirmed_at created_at updated_at
```
脚本已删除（tmp_ 产物）。`schema_version` 当前最高 159；V160 未登记 —— 由后端启动时
MigrationRunner 走正常路径登记（`IF NOT EXISTS` 保证重跑安全）。**新迁移须重启后端才写 schema_version。**

## 作用域与目标身份（Requirement 3.2）

- 作用域键：`project_id + year + wp_code + sheet_code + row_key`；`row_key` 来自模板/契约稳定业务键（非行号/下标）
- active 版本对作用域键**部分唯一索引** `uq_row_name_mapping_active_scope ... WHERE is_active`
- 目标身份保存：主表 `targets JSONB`（快照）**+** 伴生表 `workpaper_row_name_mapping_target`
  （`source_kind / account_code / aux_type / aux_name / dimension_key / dataset_id`）让身份**可 SQL 查询**
  （判 stale / 多对一交集用 `ix_row_name_mapping_target_identity(dimension_key, dataset_id)`）；名称仅展示

## 版本 / 幂等 / 留痕（Requirement 3.5 / 3.6）

- 版本模型：每次确认写**新行**（`mapping_version+1`，`is_active=true`），旧行 `is_active=false`
  且被新行 `superseded_from` 指向 → 覆盖历史天然留痕、不原地改
- 幂等：`uq_row_name_mapping_idempotency(project_id, idempotency_key) WHERE key IS NOT NULL`；
  服务层 `batch_confirm` 先按 key 短路，重复请求返回第一次结果不重复写
- 版本冲突：`base_mapping_version` 不匹配当前 active 版本 → `MappingConflictError`；
  **先全部校验再全部写** → 任一行冲突即抛，无部分写（全回滚语义，由上层事务回滚）
- 空目标身份拒绝写入（`ValueError`）

## stale 指纹（Requirement 1.4 / Property 2）

`compute_dataset_fingerprint(dataset_id, targets)` = `fp1-<sha256[:24]>`，由 dataset_id +
排序后的目标身份元组集组成 → 目标身份集变化或 dataset 变化即指纹变化 → 判 stale。

## 守卫覆盖（8 passed）

- 确认→读回往返 + 目标明细可查询
- 幂等重复不双写
- 版本冲突抛 + 全回滚（r2 不写入）
- 空目标拒绝 + 回滚
- 覆盖写 v2 + supersede v1 留痕（两物理行、v1 is_active=false、v2.superseded_from=v1.id）
- 指纹随 targets / dataset 变化，顺序无关稳定
