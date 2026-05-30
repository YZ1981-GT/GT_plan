---
spec: migration-runner-resilience
status: draft
version: v0.1
created: 2026-05-29
total_tasks: 19
total_estimate: 3 人天
---

# 实施任务：D6 MigrationRunner 韧性化

## Sprint 1：批不中断 + 注释剥离（1 人天）

### Task 1.1 ✅ 新建 V025 schema_migration_failures + R025 回滚
- `backend/migrations/V025__schema_migration_failures.sql` ✅
- `backend/migrations/R025__rollback_schema_migration_failures.sql` ✅
- 4 列 + PK(version) + 幂等 `CREATE TABLE IF NOT EXISTS` ✅

### Task 1.2 ✅ MigrationRunner 改 `exec_driver_sql`
- `_apply_migration` 内 `for stmt: await conn.exec_driver_sql(stmt)` 替代 `text(stmt)` ✅
- 仅 `INSERT INTO schema_version` 仍用 `text + bind` ✅
- 现有 54 测试全绿（test_migration_runner.py 29 + test_migration_runner_rollback.py 25）✅

### Task 1.3 ✅ MigrationRunner 加 per-migration 异常隔离
- `run_pending` 改返回 `RunPendingResult(executed, failed)` + `__eq__/__iter__/__len__/__bool__` 向后兼容 ✅
- 内层 try/except + `_record_failure` ✅
- `ensure_failure_table` 幂等 PG/SQLite 双方言 + `_clear_failure` + `get_failures` ✅

### Task 1.4 ✅ main.py `_run_migrations` 消费新返回值
- INFO 级打印 executed ✅
- ERROR 级打印每个 failed + 末尾汇总一行 ✅

### Task 1.5 ✅ 测试 `test_migration_runner_batch_resilience.py`
- TC-1：bad V099 + good V100 → V100 跑 + 099 写 failure 表 ✅
- TC-2：失败修复后下次启动重试成功 + failure 记录清除 ✅
- TC-3：连续 3 个 bad → 不影响后续 good ✅
- TC-4：attempt_count 递增（3 次启动 → count=3） ✅
- TC-5：RunPendingResult 向后兼容（list 比较 / iter / len / bool） ✅

## Sprint 2：schema 漂移自检（1 人天）

### Task 2.1 ✅ 新建 V026 schema_drift_log + R026 回滚
- `backend/migrations/V026__schema_drift_log.sql` ✅
- `backend/migrations/R026__rollback_schema_drift_log.sql` ✅
- 5 列 + 2 索引 (drift_type / detected_at DESC) + 幂等 ✅

### Task 2.2 ✅ 新建 `backend/app/core/schema_drift_detector.py`
- 约 360 行（DriftItem dataclass + SchemaDriftDetector + run_drift_check_with_timeout） ✅
- 4 类 drift：orm_extra / db_extra / type_mismatch / enum_mismatch ✅
- KNOWN_ALLOWLIST 含 schema_version / schema_migration_failures / schema_drift_log / alembic_version / pg_stat_statements ✅
- 非 PG 方言（SQLite 测试）退化为返回空列表 ✅
- 类型归一化（VARCHAR/CHARACTER VARYING / TIMESTAMPTZ / INTEGER / INT4 / INT8 / BOOL 等 PG 别名） ✅

### Task 2.3 ✅ main.py lifespan 加 `_run_schema_drift_check`
- 在 `_run_migrations` 之后跑（同 lifespan 序列） ✅
- 60s timeout + 异常吞掉（不阻塞启动） ✅
- drift>0 启动末尾 `print()` 兜底（绕过 LOG_LEVEL 过滤） ✅
- WARN 级日志最多前 5 条详情避免淹没启动 ✅

### Task 2.4 ✅ `/api/health` 增字段
- `migration: { applied_count, failures }` ✅
- `schema_drift: { count, items }` ✅
- 任一非空 → status="degraded"（200，仍可用，前端 banner 警告） ✅
- PG/Redis 不可达 → status="unhealthy"（503，优先级高于 degraded） ✅

### Task 2.5 ✅ 测试 `test_schema_drift_detector.py`
- 23 测试全绿 = 6 _normalize_type + 3 _camel_to_snake + 3 _diff_tables + 4 _diff_columns + 1 KNOWN_ALLOWLIST + 3 非 PG 退化 + 3 run_drift_check_with_timeout（超时/异常/正常） ✅

### Task 2.6 ✅ 测试 `test_health_endpoint_degraded.py`
- 5 测试全绿 = clean → healthy / migration failure → degraded / drift → degraded / pg_unhealthy 优先级 / JSON 契约稳定 ✅
- 旧 `test_health.py` 4 测试已加 mock 兼容（patch `_query_migration_status` + `_query_schema_drift`） ✅

## Sprint 3：注释剥离 PBT 防御（0.3 人天）

### Task 3.1 ✅ 测试 `test_migration_comment_strip_property.py`（PBT）
- 用 hypothesis 生成含 `:identifier` 的 SQL 注释 ✅
- 5 个测试 case 全绿（V005 历史回归 + 块注释 + 字符串字面量 + PBT 20 example + dollar-quote 字符串） ✅
- 历史 V005 注释 case 显式回归 ✅

## Sprint 4：alembic 清理（0.3 人天）

### Task 4.1 ✅ grep 验证无业务依赖
- `backend/scripts/_verify_no_alembic_imports.py` 一次性脚本（已删，用完即删） ✅
- **业务代码 backend/app/**/*.py：0 个 alembic import** ✅
- 测试代码 2 个文件 import alembic（已删 ↓）

### Task 4.2 ✅ 物理删除
- `git tag pre-alembic-removal-2026-05-29`（防回退备份） ✅
- `Remove-Item -Recurse -Force backend/alembic`（106 .py + 14 其他文件全删） ✅
- `Remove-Item backend/alembic.ini` ✅
- `requirements.txt` 删 `alembic` 行 ✅
- `backend/tests/ledger_import/test_alembic_migrations.py` 删（pg_only mark + 直接 import alembic 包） ✅
- `backend/tests/ledger_import/test_migration_day7_update.py` 删（迁移文件已删测试无对象） ✅

### Task 4.3 ✅ 文档清理
- `README.md` 4 处 alembic 引用全改写为 D6 / `backend/migrations/` 路径（grep 0 匹配） ✅
- `docs/deployment/phase8/deployment.md` 数据库迁移段 + 验证清单 + 回滚方案改写为 D6 ✅
- `docs/deployment/phase8/guide.md` 2.4/2.6 段改写 ✅
- `.kiro/specs/INDEX.md` 顶部加「迁移系统（D6 唯一入口）」章节 ✅
- `docs/proposals/*` / `docs/adr/*` / `docs/architecture/*` 等历史档案保留（按"历史档案不回填"铁律） 📌

### Task 4.4 ✅ 启动 smoke 测试
- `python -c "from app.main import app"` 通过（无 alembic 相关 import error） ✅
- pytest 96/96 全绿（含 health 端点 + migration 全集回归） ✅

## Sprint 5：UAT + 收尾（0.4 人天）

### Task 5.1 ⏳ 跑 pytest 全集回归
- `..\.venv\Scripts\python.exe -m pytest backend/tests/test_migration_runner.py backend/tests/test_migration_runner_rollback.py backend/tests/test_migration_runner_batch_resilience.py backend/tests/test_schema_drift_detector.py backend/tests/test_health_endpoint_degraded.py backend/tests/test_migration_comment_strip_property.py -v`

### Task 5.2 ⏳ Playwright 实测 health endpoint
- 启动后端
- 浏览器访问 `http://127.0.0.1:9980/api/health`
- 截图保留 `.playwright-mcp/health-{ts}.png`
- 验证 JSON 含 migration / schema_drift 字段

### Task 5.3 ⏳ 故意制造 drift 复测
- 用 SQL `ALTER TABLE financial_report DROP COLUMN is_stale;`（V023 复盘场景）
- 重启后端 → health=degraded + schema_drift.count>0
- 再 `ALTER TABLE financial_report ADD COLUMN is_stale BOOLEAN DEFAULT false;`
- 重启 → 恢复 ok
- 截图前后对比 `.playwright-mcp/drift-{before,after}.png`

### Task 5.4 ⏳ ADR 沉淀
- `docs/adr/ADR-024-d6-vs-alembic-selection.md`
- `docs/adr/ADR-025-exec-driver-sql-bind-bypass.md`

### Task 5.5 ⏳ memory.md 更新
- 「真正待办」#2 标记完成
- 「关键引用指南 / 操作铁律」加入「迁移注释 :name 用 exec_driver_sql 防御」铁律

## 总计

| Sprint | 子任务 | 测试新增 | 工作量 |
|--------|--------|----------|--------|
| 1 批不中断 | 5 | 5 | 1 人天 |
| 2 schema diff | 6 | 10 | 1 人天 |
| 3 注释 PBT | 1 | 5 PBT | 0.3 人天 |
| 4 alembic 清理 | 4 | 1 smoke | 0.3 人天 |
| 5 UAT 收尾 | 5 | - | 0.4 人天 |
| **合计** | **21** | **21** | **3 人天** |

（task header 写 19 是早期估算，实际 21；Sprint 2 拆得更细，工作量不变）

## 验收确认

- [ ] 20/20 AC 全绿（requirements.md §三）
- [ ] 8/8 CI 卡点全过（requirements.md §四）
- [ ] 21/21 测试 0 失败
- [ ] alembic grep 0 业务匹配
- [ ] Playwright 截图 4 张（health 正常 + 故意 drift 前后 + alembic 删除后启动）
- [ ] 启动日志 + `/api/health` JSON 各 1 段贴入 dev-history.md
