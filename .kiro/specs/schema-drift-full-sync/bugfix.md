# Bugfix Requirements Document

## Introduction

应用启动时 `schema_drift_detector` 报告 965 个 `orm_extra` 类型漂移（ORM 模型定义了列但 PG 数据库中不存在），导致 health=degraded。这是长期积累的 ORM-vs-DB 不一致：各 spec 添加了 ORM 模型字段但对应的 ALTER TABLE 迁移从未创建或从未在本地 PG 执行。

影响：
- 每次启动 health=degraded（噪音，掩盖真实问题）
- 查询这些列的 service 运行时 500（如 time_machine_cleanup_worker）
- 依赖这些列的新功能静默失败

修复方式：编写 Python 内省脚本生成完整 ALTER TABLE SQL，创建 V033 迁移一次性同步所有缺失列。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the application starts THEN the system reports 965 critical drifts of type `orm_extra` via `schema_drift_detector` and sets health status to "degraded"

1.2 WHEN a service queries a column that exists in ORM but not in PG (e.g. `time_machine_snapshots` columns, `applicable_standard_v2`, various spec-added fields) THEN the system raises `UndefinedColumn` / 500 at runtime

1.3 WHEN a new feature depends on ORM-defined columns that have no corresponding DB column THEN the system silently returns NULL or fails without clear error

### Expected Behavior (Correct)

2.1 WHEN the application starts after V033 migration has run THEN the system SHALL report 0 critical `orm_extra` drifts and health status SHALL be "healthy" (or degraded only for known allowlist items)

2.2 WHEN a service queries any ORM-defined column THEN the system SHALL find the column in PG and execute the query without `UndefinedColumn` errors

2.3 WHEN a new feature depends on ORM-defined columns THEN the system SHALL have those columns present in PG with correct types and defaults matching the ORM definition

### Unchanged Behavior (Regression Prevention)

3.1 WHEN existing data is stored in tables that already have all their columns THEN the system SHALL CONTINUE TO preserve all existing data without modification or loss

3.2 WHEN `db_extra` type drifts exist (DB columns not in ORM) THEN the system SHALL CONTINUE TO report them as INFO-level without affecting health status

3.3 WHEN the migration is re-run (idempotent) THEN the system SHALL CONTINUE TO succeed without errors (all ALTER TABLE statements use `IF NOT EXISTS` or equivalent guards)

3.4 WHEN `KNOWN_ALLOWLIST` tables are present THEN the system SHALL CONTINUE TO exclude them from drift calculations

3.5 WHEN enum values already exist in PG THEN the system SHALL CONTINUE TO not duplicate them (use `ADD VALUE IF NOT EXISTS`)
