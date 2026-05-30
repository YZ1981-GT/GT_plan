---
spec: migration-runner-resilience
status: draft
version: v0.1
created: 2026-05-29
---

# 设计文档：D6 MigrationRunner 韧性化

## 一、架构总览

```
启动 lifespan (main.py)
  │
  ├─► _run_migrations()                ← 修改 1：per-migration 异常隔离
  │     └─► MigrationRunner.run_pending()
  │           └─► for mig in pending:
  │                 try:
  │                     _apply_migration(mig)
  │                 except Exception:
  │                     _record_failure(mig, exc)   ← 新增
  │                     continue                     ← 不再抛
  │
  ├─► _run_schema_drift_check()          ← 新增：启动 self-check（异步不阻塞）
  │     └─► SchemaDriftDetector.scan()
  │           ├─► ORM inspect → tables/columns
  │           ├─► DB pg_catalog → tables/columns
  │           ├─► PG enum vs Python Enum
  │           └─► write schema_drift_log
  │
  └─► /api/health endpoint                ← 修改 2：暴露 migration/drift
        └─► {
              status, db, redis, llm,
              migration: { applied: 24, failures: [...] },
              schema_drift: { count: 0, items: [...] }
            }
```

## 二、核心改造点

### 2.1 P-1 修复：批不中断（最优先）

**改造文件**：`backend/app/core/migration_runner.py`

**新增方法**：

```python
async def _record_failure(
    self,
    mig: MigrationFile,
    exc: Exception,
) -> None:
    """记录失败到 schema_migration_failures 表。下次启动时优先重试。"""
    async with self._engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO schema_migration_failures
              (version, filename, error_message, error_type, attempted_at)
            VALUES (:version, :filename, :err_msg, :err_type, NOW())
            ON CONFLICT (version) DO UPDATE
              SET error_message = EXCLUDED.error_message,
                  error_type = EXCLUDED.error_type,
                  attempted_at = NOW(),
                  attempt_count = schema_migration_failures.attempt_count + 1
        """), {
            "version": mig.version,
            "filename": mig.filename,
            "err_msg": str(exc)[:2000],
            "err_type": type(exc).__name__,
        })
```

**`run_pending` 改造**：

```python
async def run_pending(self) -> RunPendingResult:   # ← 改返回类型
    """执行所有未应用的迁移。

    返回:
        RunPendingResult(executed=[...], failed=[...])
    """
    await self.ensure_schema_version_table()
    await self.ensure_failure_table()              # ← 新增

    pending = self._compute_pending(...)

    executed: list[str] = []
    failed: list[FailureRecord] = []

    for mig in pending:
        try:
            await self._apply_migration(mig)
            executed.append(mig.version)
            await self._clear_failure(mig.version)  # 成功则清失败记录
        except Exception as e:
            logger.error(
                "[Migration] ❌ %s 失败: %s（继续后续迁移）",
                mig.filename, e, exc_info=True,
            )
            await self._record_failure(mig, e)
            failed.append(FailureRecord(version=mig.version, filename=mig.filename, error=str(e)))

    return RunPendingResult(executed=executed, failed=failed)
```

**`_apply_migration` 内部不变**（仍然单文件单事务），改的是外层调用语义。

**新表 schema_migration_failures**（V025）：

```sql
CREATE TABLE IF NOT EXISTS schema_migration_failures (
    version VARCHAR(10) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempt_count INT NOT NULL DEFAULT 1
);
```

### 2.2 P-2 修复：SQL 注释里 `:name` 剥离

**新增方法** `_strip_sql_binds_in_noncode(sql: str) -> str`：

```python
def _strip_sql_binds_in_noncode(sql: str) -> str:
    """
    将 SQL 注释 / 字符串字面量内的 :identifier 替换为 \\:identifier
    （SQLAlchemy text() 的转义语法），但仅注释与字符串内替换；
    代码区不动（保留真正的 bind parameter 能力）。

    更简单方案：禁用 text() 的自动 bind 解析。
    SQLAlchemy 提供 text(...).bindparams() 只允许显式声明的 bind，
    其余 :xxx 视为字面量。我们改用 sqlalchemy.text + execute_options。
    """
    # 识别注释（-- ... \n / /* ... */）
    # 识别字符串（'...' / "..." / $$ ... $$ / $tag$ ... $tag$）
    # 注释内 :foo → :\foo（标准转义）/ 字符串内已不解析所以不动
    ...
```

**实施选择**（更稳的方案）：

避开 `text()` 的 bind 解析，改用 `asyncpg` 原生 `conn.exec_driver_sql(stmt)`：

```python
async def _apply_migration(self, mig: MigrationFile) -> None:
    sql_content = mig.path.read_text(encoding="utf-8")
    statements = self._split_sql_statements(sql_content)

    async with self._engine.begin() as conn:
        for stmt in statements:
            # exec_driver_sql 跳过 SQLAlchemy bind 解析
            # 注释/字符串内的 :name 全部当字面量
            await conn.exec_driver_sql(stmt)

        # 唯独写 schema_version 这条用 text() 因为有真 bind
        await conn.execute(
            text("INSERT INTO schema_version ..."),
            {"version": mig.version, ...}
        )
```

**优点**：彻底绕开 `:name` 解析问题；不用维护字符串/注释解析器。

### 2.3 P-3 修复：schema 漂移自检

**新文件** `backend/app/core/schema_drift_detector.py`（约 200 行）：

```python
@dataclass
class DriftItem:
    table: str
    column: str | None       # None 表示表级漂移
    drift_type: Literal["orm_extra", "db_extra", "type_mismatch", "enum_mismatch"]
    detail: str

class SchemaDriftDetector:
    """启动时扫描 ORM ↔ DB schema 差异。"""

    KNOWN_ALLOWLIST = {
        # PG 系统/分区表 / extension 表
        "schema_version", "schema_migration_failures", "schema_drift_log",
        "alembic_version",   # 历史残留
        # 业务允许的漂移（手动列入）
    }

    async def scan(self) -> list[DriftItem]:
        orm_tables = self._collect_orm_tables()      # 反射 Base.metadata
        db_tables = await self._collect_db_tables()  # 查 pg_catalog
        items = []
        items.extend(self._diff_tables(orm_tables, db_tables))
        items.extend(self._diff_columns(orm_tables, db_tables))
        items.extend(await self._diff_enums())
        return [i for i in items if i.table not in self.KNOWN_ALLOWLIST]

    async def write_log(self, items: list[DriftItem]) -> None:
        """写 schema_drift_log（每次启动覆盖）。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("DELETE FROM schema_drift_log"))
            for it in items:
                await conn.execute(text("""
                    INSERT INTO schema_drift_log
                      (table_name, column_name, drift_type, detail, detected_at)
                    VALUES (:t, :c, :dt, :d, NOW())
                """), {"t": it.table, "c": it.column, "dt": it.drift_type, "d": it.detail})
```

**新表 schema_drift_log**（V026）：

```sql
CREATE TABLE IF NOT EXISTS schema_drift_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100),
    drift_type VARCHAR(50) NOT NULL,
    detail TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_schema_drift_type ON schema_drift_log(drift_type);
```

**`/api/health` 改造**：

```python
@router.get("/api/health")
async def health(...):
    ...
    migration_failures = await _query_failures()
    drift_items = await _query_drift()

    overall_status = "ok"
    if migration_failures or drift_items:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "db": db_status,
        "redis": redis_status,
        "llm": llm_status,
        "migration": {
            "applied_count": applied_count,
            "failures": [{"version": f.version, "error": f.error} for f in migration_failures],
        },
        "schema_drift": {
            "count": len(drift_items),
            "items": [...]
        }
    }
```

### 2.4 P-4 alembic 清理

**步骤**：
1. `grep -r "from alembic\|import alembic" backend/` 确认无业务依赖
2. `Remove-Item -Recurse backend/alembic`
3. `Remove-Item backend/alembic.ini`
4. `requirements.txt` 删 `alembic==X.Y.Z`
5. `docs/` 全文 grep `alembic` → README / 部署文档相应改写
6. `.gitignore` 留下；`backend/alembic/` 标记为 deleted（git rm）
7. INDEX.md 顶部加：「迁移系统 = D6 / `backend/migrations/V*.sql` 唯一入口；alembic 已废弃」

## 三、API 契约变更

### `/api/health` 响应增量

**Before**：
```json
{ "status": "ok", "db": "ok", "redis": "ok", "llm": "ok" }
```

**After**：
```json
{
  "status": "ok|degraded",
  "db": "ok",
  "redis": "ok",
  "llm": "ok",
  "migration": {
    "applied_count": 26,
    "failures": []
  },
  "schema_drift": {
    "count": 0,
    "items": []
  }
}
```

**前端 DegradedBanner**（已有组件）需要消费 `migration.failures.length>0 || schema_drift.count>0` 触发 warning。

## 四、迁移文件

新增 2 个 V*.sql：
- `V025__schema_migration_failures.sql`（+ R025 回滚）
- `V026__schema_drift_log.sql`（+ R026 回滚）

## 五、测试设计

| 测试文件 | 数量 | 覆盖 |
|----------|------|------|
| `test_migration_runner_batch_resilience.py` | 5 | P-1 修复（CI-1） |
| `test_migration_comment_strip_property.py` | 5 PBT | P-2 注释里 `:name` 不爆（CI-2/CI-3） |
| `test_schema_drift_detector.py` | 6 | P-3 4 类漂移检测（CI-3） |
| 现有 `test_migration_runner.py` 回归 | - | 不能破坏 |
| 启动 smoke | 1 | alembic 删除后正常启动（CI-7） |

## 六、回滚策略

- V025/V026 分别有 R025/R026 配套
- `_apply_migration` 改造保留旧行为开关 `MIGRATION_RESILIENT_MODE`（默认 True，可设 False 回退）
- alembic 删除前 git 打 tag `pre-alembic-removal-2026-05-29`，需要时一键 `git checkout`

## 七、不在范围内（明确划出）

- ❌ Prometheus metrics（→ observability-baseline 另立 spec）
- ❌ structlog 替换 stdlib logger（同上）
- ❌ asyncpg pool 监控（同上）
- ❌ 多实例迁移分布式锁（本仓库本地优先轻量方案）

## 八、ADR

- ADR-024：D6 vs alembic 选型（保留 D6 删 alembic）
- ADR-025：用 `exec_driver_sql` 绕开 `text()` bind 解析

## 九、版本

- v0.1（2026-05-29）：初版
