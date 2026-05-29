# ADR-025: 迁移 SQL 用 exec_driver_sql 绕开 SQLAlchemy bind 解析

- **Date**: 2026-05-29
- **Status**: Accepted
- **Spec**: migration-runner-resilience

## Context

`MigrationRunner._apply_migration` 历史用 `conn.execute(text(stmt))` 执行用户 SQL：

```python
async with self._engine.begin() as conn:
    for stmt in statements:
        await conn.execute(text(stmt))   # ← 这里有坑
```

**问题**：SQLAlchemy `text()` 的 bind parameter 解析是基于词法扫描，会扫**包括 SQL 注释和字符串字面量内**的 `:identifier` 模式：

```sql
-- V005__enable_rls.sql 里写过：
-- 而非 SET LOCAL ... = :pid（PG 的 SET 命令不支持 prepared statement 绑定参数）
-- ↑ 这条注释里的 :pid 被 text() 误认为 bind parameter
ALTER TABLE working_paper ENABLE ROW LEVEL SECURITY;
```

报错：`A value is required for bind parameter 'pid'` → 整个文件事务回滚 → 后续 V021/V022/V023 全部静默不执行（批中断）。

memory 已沉淀「SQLAlchemy text() SQL 注释 :name 陷阱」铁律，但仅靠"约定写注释时不带 `:`"是脆弱的：
- 中文/英文注释自然包含冒号
- 字符串字面量内 `:foo` 也会触发（如 `RAISE 'use :pid here'`）
- 字符串中含 `:` 的业务数据（PG/MySQL 错误消息）也踩

## Decision

**改用 `conn.exec_driver_sql(stmt)` 替代 `conn.execute(text(stmt))`**：

```python
async with self._engine.begin() as conn:
    for stmt in statements:
        # exec_driver_sql 跳过 SQLAlchemy bind 解析，直接传 dbapi
        await conn.exec_driver_sql(stmt)

    # 唯独 INSERT INTO schema_version 仍用 text + bind（系统 SQL 可控）
    await conn.execute(
        text("INSERT INTO schema_version (version, filename, checksum) VALUES (:v, :f, :c)"),
        {"v": ..., "f": ..., "c": ...}
    )
```

`exec_driver_sql` 是 SQLAlchemy 2.0 提供的"原始 SQL"接口：
- 不做 bind 解析
- 不做 dialect 转换
- 直接传给 dbapi cursor.execute()
- 注释/字符串内 `:name` 全部当字面量

## Alternatives Considered

### 写正则注释剥离器

- 思路：执行前用正则把注释 / 字符串内 `:name` 转义
- 缺点：字符串边界识别复杂（`'`/`"`/`$$`/`$tag$`）+ 注释嵌套（`/* /* */ */`）+ 易踩边界 case
- 拒绝理由：维护一个 SQL parser 是 over-engineering

### 用 Pydantic 风格 escape

- `text()` 提供 `\:foo` 转义语法（即写 `\:pid`）
- 缺点：要求所有迁移文件作者注意手动转义，违反"自然写注释"
- 拒绝理由：靠人记规约不可靠

### 改用 raw asyncpg（绕过 SQLAlchemy）

- 优点：彻底绕开
- 缺点：失去 SQLAlchemy connection pool / engine 抽象
- 拒绝理由：仅迁移这一处用 raw 不值

## Consequences

### 正面

- **彻底解决** SQL 注释 / 字符串字面量内 `:name` 陷阱（V005 历史踩坑根因）
- 5 用例 PBT（hypothesis 20 example）全绿
- 新加 V*.sql 写中文 / 英文注释含 `:` 都不会爆
- 启动迁移更稳定（per-migration try/except + exec_driver_sql 双保险）

### 负面

- `exec_driver_sql` 不能传 bind parameter（那条 INSERT schema_version 仍要 text+bind）
- 失去 dialect 自动转换（但本仓库迁移直接写 PG SQL，本就不需要 dialect 抽象）

## Verification

- `test_migration_comment_strip_property.py`（5 case + hypothesis 20 examples）覆盖 V005 历史回归 + 块注释 + 字符串字面量 + dollar-quote
- 现有 24 个 V*.sql 全部回放无异常
- pytest 96/96 全绿

## References

- [SQLAlchemy 2.0 Connection.exec_driver_sql](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Connection.exec_driver_sql)
- migration-runner-resilience spec / Sprint 1 / Task 1.2
