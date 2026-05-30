---
spec: migration-runner-resilience
status: draft
version: v0.1
created: 2026-05-29
owner: 全局改进 #2（memory 记录）
priority: P0（阻塞所有后续迁移 / 生产可复发）
---

# 需求文档：D6 MigrationRunner 韧性化

## 一、问题陈述

D6 MigrationRunner（`backend/app/core/migration_runner.py`）是项目实际跑的迁移系统（alembic 已死代码）。
2026-05-29 实测暴露 4 个体系性问题，**根因机制不消除则下次新加迁移仍会复发**：

### P-1 批中断（最致命）

**复现**：
- `V005__enable_rls.sql` 历史版本注释里写过 `:pid` 字面量
- SQLAlchemy `text()` 即使在 `--` 行注释中也会扫描 `:name` 当成 bind parameter
- 报错 `bind parameter 'pid' required` → 整个文件事务回滚 → 抛到 `run_pending` for 循环外
- 后续 V021/V022/V023 全部静默不跑
- 现象：dev 启动看似正常（main.py 用 `try/except` 吞掉警告），但运行时业务接口 500

**代码路径**（`migration_runner.py:617-642`）：
```python
async def _apply_migration(self, mig: MigrationFile) -> None:
    async with self._engine.begin() as conn:        # 单事务包整个文件
        for stmt in statements:
            await conn.execute(text(stmt))           # 任一失败 → 全文件回滚
        await conn.execute(...)                       # 不写 schema_version

# run_pending（line 158-173）
for mig in pending:
    await self._apply_migration(mig)                  # 无 per-migration 异常隔离
    executed.append(mig.version)
```

### P-2 SQL 注释 `:name` 陷阱

`text()` 会扫 `--` 与 `/* */` 注释里的 `:identifier` 当 bind parameter。
**触类旁通 grep**：本仓库目前 24 个 V*.sql 中只有 V005 历史踩过，但**机制不防御则任何后续 SQL 注释都可能踩**。

### P-3 schema 漂移自检缺失

memory 已沉淀 4 处实测漂移：
- V022 `cell_annotations.annotation_type`（ORM 用了但 DB 没有）
- V023 `financial_report.is_stale`（同上）
- V024 `wp_file_status` enum 缺 3 值（ORM 用了但 DB 没有）
- V005 RLS 失败导致 V021/22/23 全没跑（漂移由 P-1 间接造成）

**当前漂移暴露路径** = 业务接口 500 → 用户截图 → 人肉定位。
**应该的暴露路径** = 启动 self-check → health=degraded → DegradedBanner + 启动日志 ERROR。

### P-4 alembic 双轨残留

- `backend/alembic/` 整目录死代码（运行时不跑）
- `backend/alembic.ini` 配置文件保留但无人维护
- 新人 / 文档 / IDE 提示混淆「是否要 `alembic revision`」
- 已有 spec 工作（disclosure-note-full-revamp、note-dynamic-tables）发现 alembic chain 已断裂数月

## 二、范围

### 必做（P0，本 spec 闭环）

- R1 **批不中断**：单文件失败不阻塞后续 pending 迁移
- R2 **SQL 注释剥离**：执行前自动剥离注释里的 `:xxx` 字面量
- R3 **启动自检 + 漂移可视化**：ORM↔DB diff 写 `schema_drift_log` + `/api/health` 暴露
- R4 **alembic 残留清理**：删 `backend/alembic/` + `backend/alembic.ini` + 文档/CI 引用
- R5 **V005 RLS 防御测试**：PBT 注入随机 `:name` 注释验证不再爆

### 不做（明确划出）

- ❌ 替换 D6 改用 alembic（反向翻案，alembic chain 已断且 D6 已稳）
- ❌ 接 Prometheus/Grafana 全监控（→ observability-baseline 另立 spec）
- ❌ 迁移分布式锁（多实例并发问题，本仓库本地优先轻量方案不需要）
- ❌ 改 V005 RLS 策略本身（已工作正常）

## 三、用户故事

### US-1（项目经理 / 部署运维）

**作为**部署运维，**我希望**单个迁移文件出错时其他迁移仍能继续跑，**以便**避免因为某个新加迁移有 bug 导致整批未应用。

**验收**：
- AC-1.1 给一个 `V099__bad.sql` 故意写 `SELECT 1/0;` 启动后 V099 标记 failed，V100 仍执行
- AC-1.2 `schema_version` 表只记录成功的版本
- AC-1.3 新建 `schema_migration_failures` 表记录失败版本 + 异常摘要 + 时间戳
- AC-1.4 `/api/health` JSON 返回 `migration: { status: "degraded", failures: [...] }`

### US-2（后端开发）

**作为**后端开发，**我希望**写 SQL 注释时不需要担心 `:name` 字面量被 SQLAlchemy 误解析，**以便**自然地写中文/英文注释。

**验收**：
- AC-2.1 `V099__test.sql` 注释里写 `-- 用 :pid 替换为...` 启动不报错
- AC-2.2 PBT 用 hypothesis 生成含随机 `:identifier` 的注释 100 case 全绿
- AC-2.3 `/* :foo */` 块注释也剥离
- AC-2.4 字符串字面量内的 `:name` 不剥离（如 `RAISE 'error: :foo'`）

### US-3（项目经理 / 部署运维）

**作为**运维，**我希望**启动时立即知道 schema 是否漂移，**以便**在用户报 500 之前主动修复。

**验收**：
- AC-3.1 ORM `Mapped[]` 缺 DB 列 → 写 `schema_drift_log(table, column, drift_type='orm_extra')`
- AC-3.2 DB 多 ORM 没有的列 → 写 `drift_type='db_extra'`（仅 INFO 级，不阻塞）
- AC-3.3 enum 值漂移（PG `pg_enum` vs Python `Enum.__members__`）→ 写 `drift_type='enum_mismatch'`
- AC-3.4 `/api/health` JSON 返回 `schema_drift: { count: N, items: [...] }`
- AC-3.5 启动日志末尾若 drift>0 用 `[GT-Backend] WARNING: N schema drifts detected` ERROR 级输出

### US-4（新人 / 文档维护者）

**作为**新人，**我希望**仓库里只有一套迁移系统，**以便**不混淆 D6 vs alembic。

**验收**：
- AC-4.1 `backend/alembic/` 目录已删
- AC-4.2 `backend/alembic.ini` 已删
- AC-4.3 `requirements.txt` 移除 `alembic` 依赖
- AC-4.4 `docs/` / README / steering 全文 grep `alembic` 0 匹配（除 dev-history 历史档案）
- AC-4.5 INDEX.md 加入「迁移系统：仅 D6 / V*.sql」一行说明

### US-5（QC / 防回归）

**作为**质控，**我希望**每个新加 V*.sql 自动跑防御测试，**以便**不再踩 P-2 / P-3 类型陷阱。

**验收**：
- AC-5.1 `test_migration_comment_strip_property.py` PBT 5 case 全绿
- AC-5.2 `test_migration_runner_batch_resilience.py` 5 case 覆盖 P-1 复现 + 修复后行为
- AC-5.3 `test_schema_drift_detector.py` 6 case 覆盖 ORM↔DB 4 类漂移 + diff 写库 + health 暴露
- AC-5.4 CI（pytest）一次跑通 0 失败

## 四、卡点（Continuous Integration / Validation）

| 编号 | 描述 | 实施位置 |
|------|------|----------|
| CI-1 | 单文件迁移失败 → 后续仍执行 + failure 表写入 + schema_version 不写 | `_apply_migration` per-statement try/except + outer for 不抛 |
| CI-2 | SQL 注释里 `:name` 不引发 bind error | `_strip_sql_bind_in_comments` 预处理 |
| CI-3 | `text()` 字符串字面量内 `:name` 保留 | 字符串边界识别（`'`/`"`/`$$`） |
| CI-4 | 启动 self-check 在 60s 内完成（不阻塞 health） | timeout + 异步并行 |
| CI-5 | `schema_drift_log` 表幂等创建（若不存在） | `CREATE TABLE IF NOT EXISTS` |
| CI-6 | `/api/health` JSON 含 migration / schema_drift 两字段 | health router 改 |
| CI-7 | alembic 删除后启动无报错 | smoke test 启动 5s |
| CI-8 | `requirements.txt` 移除 alembic 后 `pip install -r` 成功 | `_verify_requirements.py` |

## 五、依赖前置

| 编号 | 描述 | 责任方 | 状态 |
|------|------|--------|------|
| P-1 | docker exec audit-postgres 可访问 | 自有 | ✅ |
| P-2 | hypothesis ≥6.x 已装 | 自有 | ✅ |
| P-3 | ORM 反射工具（SQLAlchemy `inspect`） | 自有 | ✅ |

无外部前置。

## 六、风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 删 alembic 影响某个老脚本 import | 低 | grep `from alembic` / `import alembic` 全仓 0 业务依赖才删 |
| schema diff 假阳性 | 中 | 维护 `KNOWN_DRIFT_ALLOWLIST`（如 partition 子表 / extension 系统表） |
| 启动 self-check 拖慢启动 | 低 | 60s timeout + 后台异步（不阻塞 lifespan） |
| 历史失败的迁移再次执行 | 中 | failure 表保留版本号，重启时优先重试 failure 而非跳过 |

## 七、验收数字汇总

- 验收总数：5 user stories × 平均 4 AC = **20 AC**
- 卡点总数：**8 CI**
- 必做范围：**5 R**（R1~R5）
- 测试目标：**16 测试**（PBT 11 + 集成 5）
- 工作量估计：**3 人天**（设计 0.5 + R1+R2 1 天 + R3 1 天 + R4 0.3 + R5 + UAT 0.2）

## 八、版本

- v0.1（2026-05-29）：初版，全局改进建议 #2 落地
