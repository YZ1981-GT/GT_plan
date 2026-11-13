# 操作手册：公式来源信封 schema 对齐

> spec: `formula-hub-release-blockers` R2
> 日期: 2026-11-01
> 状态: 2026-11-04 只读核对 —— 共享库 `audit_platform` 已应用至 V251（V235 / V237~V247 / V250 / V251 于 11-03 13:48 UTC，
> V236 / V248 / V249 于 15:24 UTC 登记，checksum 与仓库文件一致），**本手册不需再对共享库执行**，保留作其他库的操作与回退参考。
> 迁移器分句自 spec `formula-management-repair-closure` R0.2 起认字符串字面量与开头 BOM；更早的迁移器执行 V236 / V248 / V249 必失败。

## 背景

当前工作树 ORM 已经使用以下数据结构，但共享库尚未应用对应迁移：

| 迁移 | 内容 | ORM 引用 |
|------|------|---------|
| V246 | `report_generation_run` 表 + `consol_artifact` 表 + `financial_report.run_id/provenance` | `ReportGenerationRun`, `ConsolArtifact`, `FinancialReport.run_id/provenance` |
| V248 | `formula_push_state.provenance` 列 | `FormulaPushState.provenance` |
| V251 | 重复建 `report_generation_run`（幂等）+ `financial_report` 外键 | 同 V246 |

编写时（2026-11-01）共享库最高已应用版本为 V234。V235~V251 中的其他迁移（非来源信封相关）也需按顺序执行。

## 前置条件

- 后端服务**已停止**或以 `GT_BOOTSTRAP_DONE=1` 启动（不自动跑迁移）
- 已确认当前连接的是目标共享库（`audit_platform`）
- 有 PG 超级用户或表所有者权限

## 操作步骤

### 1. 备份受影响表

```bash
pg_dump -Fc \
  -t financial_report \
  -t formula_push_state \
  -t schema_version \
  -d audit_platform \
  -f backup_formula_provenance_$(date +%Y%m%d_%H%M%S).dump
```

### 2. 执行待应用迁移

在 Python 环境中（已激活 `.venv`）：

```python
import asyncio
from app.core.config import settings
from app.core.migration_runner import MigrationRunner

async def main():
    runner = MigrationRunner(settings.DATABASE_URL)
    readiness = await runner.inspect_readiness()
    print(f"待应用: {readiness.pending_count} 条")
    print(f"待应用列表: {[m.filename for m in readiness.pending]}")

    # 确认无误后执行
    result = await runner.run_pending()
    print(f"已应用: {len(result)} 条")

    # 验证
    final = await runner.inspect_readiness()
    print(f"is_complete: {final.is_complete}")
    print(f"critical_count: {final.critical_count}")
    await runner.close()

asyncio.run(main())
```

预期输出：
- `is_complete: True`
- `critical_count: 0`

### 3. 验证关键表

```sql
-- report_generation_run 表应存在
SELECT COUNT(*) FROM information_schema.tables
WHERE table_name = 'report_generation_run';
-- 预期: 1

-- financial_report 应有 run_id 和 provenance 列
SELECT column_name FROM information_schema.columns
WHERE table_name = 'financial_report' AND column_name IN ('run_id', 'provenance');
-- 预期: 2 行

-- formula_push_state 应有 provenance 列
SELECT column_name FROM information_schema.columns
WHERE table_name = 'formula_push_state' AND column_name = 'provenance';
-- 预期: 1 行

-- 存量 financial_report 的 calc_version 应仍为 NULL（不批量回填）
SELECT COUNT(*) AS total, COUNT(calc_version) AS with_version
FROM financial_report WHERE NOT is_deleted;
-- 预期: with_version = 0（存量行等下次正常生成/stale 重算时按正确版本写入）
```

### 4. 重启后端

```bash
# 正常启动（不带 GT_BOOTSTRAP_DONE=1），让应用检测到 schema 已就绪
start-dev.bat
```

## 回退

如果执行后发现问题：

```bash
# 恢复备份
pg_restore -d audit_platform --clean --if-exists backup_formula_provenance_XXXXXXXX.dump
```

对应的回滚脚本已存在于 `backend/migrations/`：
- `R246__rollback_report_generation_run_and_consol_artifact.sql`
- `R248__rollback_formula_push_provenance.sql`
- `R251__rollback_formula_provenance_report_runs.sql`

## 重要说明

1. **不批量回填 `calc_version`**：存量 2935 条报表行的 `calc_version` 保持 NULL。按当前版本判据（`calc_version IS DISTINCT FROM 2`），这些行会被正确识别为过期。下次各项目正常报表生成或 stale 重算时会按正确计算版本逐项目写入。

2. **V246 与 V251 幂等**：两份 DDL 都用 `CREATE TABLE IF NOT EXISTS` 和 `ADD COLUMN IF NOT EXISTS`，按磁盘版本号顺序执行即可，先到先建、后到跳过。

3. **formula_push_state.provenance**：新列 `JSONB NULL`，存量 902 行该列为 NULL，下次公式推送运行时按行写入来源信封。
