# ADR-024: 数据库迁移系统选型 — D6 SQL 替代 Alembic

- **Date**: 2026-05-29
- **Status**: Accepted
- **Spec**: migration-runner-resilience

## Context

仓库历史曾用 alembic 维护数据库迁移：

- `backend/alembic/versions/` 含 60+ 历史版本（按日期命名 `view_refactor_*` / `round*_*` / `phase17_*`）
- alembic chain 在 2026-05 Q2 已**事实断裂**（多处缺 down_revision / 多 head）
- 多个 spec（disclosure-note-full-revamp、note-dynamic-tables）实施时发现 alembic 不再可靠
- 同时存在 D6 自研系统：`backend/migrations/V*.sql` + `R*.sql` + `MigrationRunner` 启动时执行

D6 的优势在 2026-05 实测中已显现：
- 单条 SQL 单事务执行（避免 alembic 单 revision 多语句的事务粒度问题）
- 启动时自动跑（无需 `alembic upgrade head` 命令）
- 历史 alembic 迁移与 D6 SQL 同时执行无冲突（双轨并行 6+ 月）

## Decision

**保留 D6 作为唯一迁移系统，删除 alembic 残留**：

1. `backend/migrations/V0XX__xxx.sql` + `R0XX__rollback_xxx.sql` 配对（`IF NOT EXISTS` 幂等）
2. 启动时由 `MigrationRunner.run_pending()` 自动执行
3. 失败追踪：`schema_migration_failures` 表 + `/api/health.migration.failures` 暴露
4. schema 漂移检测：启动 self-check `SchemaDriftDetector`
5. 完全删除 `backend/alembic/` 目录 + `backend/alembic.ini` + `requirements.txt` 中 `alembic`

## Alternatives Considered

### 选 alembic（重启活路）

- 优点：行业惯例 + autogenerate
- 缺点：当前 chain 已断 6+ 月，修复需重写 60+ 迁移 + 解决多 head；ROI 远低于"直接删"
- 拒绝理由：D6 已稳定运行半年，重启 alembic 是反向折腾

### 双轨并存

- 优点：零改动
- 缺点：新人混淆 / IDE 提示错误 / 文档需维护两份
- 拒绝理由：长期维护成本远高于一次性清理

### 选其他工具（dbmate / sqitch / atlas）

- 优点：现代设计
- 缺点：引入新依赖 + 学习曲线
- 拒绝理由：D6 已能力够用，无引入必要

## Consequences

### 正面

- 单一真理基线 = `backend/migrations/V*.sql`
- 减少新人困惑（README + 部署文档统一指 D6）
- 启动自动迁移 + 失败可见（`/api/health.migration.failures`）
- 幂等性强（`IF NOT EXISTS` 标准）

### 负面

- 不能用 alembic autogenerate（需手写 V*.sql）
- 多人并发新加迁移可能编号撞车（V025 vs V025）→ memory 已沉淀「打开新 spec 前先 grep `V0` 看下一个可用编号」铁律

## Migration

完成时间：2026-05-29

- 删 `backend/alembic/`（106 .py + 14 其他文件）
- 删 `backend/alembic.ini`
- 删 `requirements.txt` 中 `alembic` 行
- 删 2 个 alembic 测试文件（`test_alembic_migrations.py` / `test_migration_day7_update.py`）
- README.md / docs/deployment/phase8/ 引用全改写为 D6
- `.kiro/specs/INDEX.md` 顶部新增「迁移系统 D6 唯一入口」章节
- git tag `pre-alembic-removal-2026-05-29` 防回退

## Verification

- 启动后端 5s 内健康（D6 自动执行 V025/V026）
- `/api/health` 返回 `migration: {applied_count: N, failures: []}`
- 全仓 grep `^from alembic|^import alembic` 0 匹配
- pytest 全集 96/96 全绿
