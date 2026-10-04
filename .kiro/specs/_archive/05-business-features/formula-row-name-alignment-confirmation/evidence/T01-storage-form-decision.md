# Task 1 — DEC-2 存储形态书面评估（阻塞门）

**结论：新建 `workpaper_row_name_mapping` 表 + 新迁移，不复用 `workpaper_field_overrides`。**

_Requirement 3.1 明令不得跳过；本结论解除 Task 7 阻塞。_

## 既有机制实况（实读）

来源：
- ORM `backend/app/models/workpaper_field_override_models.py`
- 迁移 `backend/migrations/V076__workpaper_field_overrides.sql`

| 维度 | `workpaper_field_overrides` 实况 |
|---|---|
| 主键 | `id UUID` |
| 作用域键 | `project_id` + `year` + `scope VARCHAR(50)` + `item_key VARCHAR(100)` + `field VARCHAR(50)` |
| 值列 | `value JSONB`（单值，可存 str/num/bool/object） |
| 唯一约束 | `UNIQUE(project_id, year, scope, item_key, field)` — 每个 (作用域,条目,字段) 恰好一条 value |
| 索引 | `ix_field_overrides_scope(project_id, year, scope)` |
| 留痕 | 仅 `updated_by` + `updated_at`（无历史版本、无 before/after 快照、无 `superseded_from`） |
| 版本/幂等 | 无 `mapping_version` / `base_mapping_version` / `idempotency_key` 列 |
| stale 判定 | 无 dataset 指纹列 |
| 形态定位 | 「单 scope 单字段 → 单 value」的键值覆盖存储 |

## 逐条判 N:M 承载能力（对照 Requirement 3.2 / 3.4 / 3.5 / 3.6 / 1.4）

1. **多目标身份可查询性（3.2 + 1.4）**：本 spec 每行需保存
   `targets: [{account_code, aux_type, aux_name, dimension_key, dataset_id}]` 数组。
   判 stale（1.4）要能按 `dataset_id` / `account_code` / `aux_type` 过滤扫描「目标身份在当前 active dataset 是否仍存在」。
   塞进 `value JSONB` 会退化成不可用 SQL 索引查询的 blob → **形态不足**。
   （即便 PG 支持 JSONB GIN，跨行按目标身份聚合判「多对一交集」也无法用既有唯一约束表达。）

2. **版本控制与幂等（3.6）**：批量确认需 `mapping_version` + `base_mapping_version` + `idempotency_key`
   独立列做冲突检测与重复请求幂等。既有表无这些列，塞进 JSONB 的版本号
   **无法用唯一约束/乐观锁保护** → 形态不足。

3. **覆盖留痕（3.5）**：需 `superseded_from` 指向旧版本行，保留 before/after。
   既有表是单值 UPSERT，原地覆盖天然丢历史 → 形态不足。

4. **作用域粒度（3.2）**：本 spec 需 `project + year + wp_code + sheet_code + row_key` 五段键。
   既有 `scope VARCHAR(50)` + `item_key VARCHAR(100)` 可勉强编码，但会把结构化键
   压成字符串拼接，丧失按 wp_code/sheet_code 独立查询能力 → 形态不足。

## 既有机制缺什么（新建理由汇总）

- 缺「可 SQL 查询的多目标身份」列（判 stale / 多对一交集必需）
- 缺版本/幂等/乐观锁列（3.6 批量确认原子性与冲突检测必需）
- 缺 `superseded_from` 留痕链（3.5 覆盖历史留痕必需）
- 缺 dataset 指纹列（1.4 stale 回落必需）

以上四项无一能在不「退化成 JSON 字符串塞既有列」的前提下承载，故 **新建表**。

## 新表形态（Task 7 落地依据）

`workpaper_row_name_mapping`（迁移 `backend/migrations/V*.sql`，全 DDL 幂等 `IF NOT EXISTS`）：
- 作用域：`project_id` / `year` / `wp_code` / `sheet_code` / `row_key`
- 目标身份：`targets JSONB`（数组，元素含 `account_code` / `aux_type` / `aux_name` / `dimension_key` / `dataset_id`）
  —— 目标身份「按身份可查询」由派生列或伴生 `*_targets` 明细表承载（Task 7 决定），不塞纯字符串
- 判 stale：`dataset_fingerprint`
- 版本/幂等：`mapping_version` / `base_mapping_version` / `idempotency_key`
- 留痕：`confirmed_by` / `confirmed_at` / `superseded_from`
- 唯一约束覆盖作用域键（active 版本）

_评估依据文件均为实读，非推测。_
