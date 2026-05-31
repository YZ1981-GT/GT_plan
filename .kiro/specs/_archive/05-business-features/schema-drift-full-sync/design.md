# Design Document — Schema Drift Full Sync

## 概述

编写 Python 内省脚本，对比 SQLAlchemy ORM `Base.metadata` 与实际 PG schema，自动生成 `V033__sync_schema_columns.sql` 迁移文件，一次性消除所有 `orm_extra` 类型漂移。

## 技术方案

### 核心流程

1. **Import 所有 ORM 模型** → 让 `Base.metadata.tables` 收集完整
2. **连接 PG** → 用 `information_schema.columns` 获取实际表/列
3. **Diff** → 找出 ORM 有但 DB 没有的表和列
4. **生成 DDL** → 对每个缺失项生成幂等 SQL
5. **输出** → 写入 `backend/migrations/V033__sync_schema_columns.sql`
6. **执行** → 通过 SQLAlchemy 直接执行或 docker exec psql

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 类型编译 | `col.type.compile(dialect=pg_dialect())` | 获取正确 PG 类型字符串（JSONB/UUID/ARRAY 等） |
| 缺失列 | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` | PG 9.6+ 原生幂等，无需 DO 块 |
| 缺失表 | `CREATE TABLE IF NOT EXISTS` 从 ORM DDL 生成 | 完整建表含约束 |
| NOT NULL 无默认值 | 安全默认值（VARCHAR→''，INTEGER→0，BOOLEAN→false，JSONB→'{}'，UUID→gen_random_uuid()） | 避免 NOT NULL 约束失败 |
| Enum 类型 | 先 `CREATE TYPE IF NOT EXISTS` + `ADD VALUE IF NOT EXISTS` | 确保 enum 存在再引用 |
| Nullable | 匹配 ORM 定义 | 保持一致性 |
| server_default | 从 ORM 提取 | 保持一致性 |
| 排除表 | `KNOWN_ALLOWLIST`（schema_version/alembic_version 等） | 与 drift detector 一致 |

### 安全默认值映射

```
VARCHAR/TEXT       → DEFAULT ''
INTEGER/BIGINT     → DEFAULT 0
FLOAT/NUMERIC      → DEFAULT 0
BOOLEAN            → DEFAULT false
JSONB/JSON         → DEFAULT '{}'
UUID (PK)          → DEFAULT gen_random_uuid()
UUID (non-PK)      → NULL (nullable)
TIMESTAMP/TIMESTAMPTZ → DEFAULT NOW()
ARRAY              → DEFAULT '{}'
ENUM               → NULL (nullable) 或第一个枚举值
```

### 脚本位置

`backend/scripts/gen/gen_schema_sync_migration.py` — 永久工具（无 `_` 前缀），可重复运行。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 生成的类型字符串不正确 | 用 `compile(dialect=...)` 而非手写映射 |
| NOT NULL 列加到有数据的表 | 提供安全默认值 |
| Enum 不存在 | 先 CREATE TYPE 再 ADD COLUMN |
| 脚本 import 失败 | try/except 包裹每个 model 模块 |
| 迁移执行失败 | 所有语句幂等，可重跑 |
