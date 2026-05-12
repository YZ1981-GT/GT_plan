# EXPLAIN ANALYZE — 账表四表查询改造前后对比

> 文档对应 spec：`.kiro/specs/ledger-import-view-refactor/` · Sprint 9.4
>
> 目的：记录 B' 视图重构前后几条代表性查询的执行计划差异，确保重构不引入
> > 1.2× 的回归成本（requirements §3.3 成功判据）。
>
> 本文为**运维剧本**，不是自动化测试；Day 0 部署前后各跑一次，生产环境观察
> 实际 planner 选择。

## 方法论

### 跑 EXPLAIN ANALYZE 的前置条件

- PG 生产库或预发布库（每表 ≥ 100 万行，和真实 YG2101 / 辽宁卫生规模相当）
- 开启 `SET track_io_timing = on;` 读取 I/O 分布
- 每条查询连跑 3 次取第 2、3 次的均值（第 1 次受磁盘冷缓存影响）
- 关闭 `auto_explain` 外其他采样以免干扰

### 采样策略

- **重构前基线**（Day 0 前）：在 `master` 分支 `TbX.is_deleted == False` 原生查询上跑
- **重构后**（Day 0 后）：在 `feature/ledger-import-view-refactor` 分支
  `get_active_filter` 产出的查询上跑
- 用例覆盖：
  1. 单科目明细账查询（索引命中）
  2. 年度全科目汇总（聚合）
  3. 辅助余额多维度聚合
  4. 跨表比对（L3 校验场景）
  5. 批量激活前后快速校验（dataset_id 过滤）

### 判定标准

| 维度 | 基线 | 允许上限 |
|------|------|---------|
| Rows Out | B 行 | B 行（完全一致） |
| Planning Time | T_0 ms | T_0 × 1.5 ms |
| Execution Time | E_0 ms | E_0 × 1.2 ms |
| Buffers Hit | H_0 页 | H_0 × 1.2 页 |

**超限处理**：超 > 1.2× 且非首次冷启动 → 记录为"架构性回归"，回到 sprint 加
索引或调整 `get_active_filter` 模板。

## 代表性查询对照

### Q1 — 单科目明细账（索引命中）

业务场景：前端点击"科目 1001 现金"查序时账明细。

#### 改造前（基线）

```sql
-- 对应代码：wp_chat_service.py:123 / report_trace_service.py:89
EXPLAIN (ANALYZE, BUFFERS)
SELECT voucher_date, voucher_no, debit_amount, credit_amount, summary
FROM tb_ledger
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND account_code = '1001'
  AND is_deleted = false
ORDER BY voucher_date, voucher_no;
```

**预期 plan**：
- Index Scan on `idx_tb_ledger_project_year_account` (project_id + year + account_code)
- Filter: `is_deleted = false`
- Rows Out: ~数百-数千

#### 改造后

```sql
-- 对应代码：get_active_filter 返回
EXPLAIN (ANALYZE, BUFFERS)
SELECT voucher_date, voucher_no, debit_amount, credit_amount, summary
FROM tb_ledger
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND account_code = '1001'
  AND dataset_id = '<active_dataset_id>'::uuid  -- 新增
  AND is_deleted = false
ORDER BY voucher_date, voucher_no;
```

**预期 plan**：
- Index Scan on `idx_tb_ledger_project_year_account`
- Filter: `dataset_id = X AND is_deleted = false`
- Rows Out: 与基线一致（staged dataset 的行不会有相同 account_code + is_deleted=false 组合）

**改造后建议索引**（已通过 `view_refactor_activate_index_20260510` 迁移落地）：
```
idx_tb_ledger_active_queries
  ON tb_ledger (project_id, year, dataset_id)
  WHERE is_deleted = false
```

---

### Q2 — 年度全科目汇总（聚合）

业务场景：TB 试算表生成 —— 对所有科目汇总借贷发生额。

#### 改造前

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_code, SUM(debit_amount), SUM(credit_amount)
FROM tb_ledger
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND is_deleted = false
GROUP BY account_code;
```

**预期 plan**：
- Index Scan or Bitmap Index Scan on `idx_tb_ledger_project_year_deleted`
- HashAggregate
- Rows In: 数十万-数百万；Rows Out: 数百

#### 改造后

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_code, SUM(debit_amount), SUM(credit_amount)
FROM tb_ledger
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND dataset_id = '<active>'::uuid
  AND is_deleted = false
GROUP BY account_code;
```

**预期 plan**：
- Index Scan on `idx_tb_ledger_active_queries` (project + year + dataset_id)
- HashAggregate
- **改善**：partial index 让 active 查询扫描更紧凑（只含 is_deleted=false 行）

---

### Q3 — 辅助余额多维度聚合（balance-tree 核心查询）

业务场景：`GET /api/projects/{pid}/ledger/balance-tree` 返回三层树。

#### 改造前

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_code, aux_type, aux_code, aux_name,
       SUM(opening_debit - opening_credit) AS opening_balance,
       SUM(closing_debit - closing_credit) AS closing_balance,
       COUNT(*) AS record_count
FROM tb_aux_balance
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND is_deleted = false
GROUP BY account_code, aux_type, aux_code, aux_name;
```

#### 改造后

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_code, aux_type, aux_code, aux_name,
       SUM(opening_debit - opening_credit) AS opening_balance,
       SUM(closing_debit - closing_credit) AS closing_balance,
       COUNT(*) AS record_count
FROM tb_aux_balance
WHERE project_id = '<pid>'::uuid
  AND year = 2024
  AND dataset_id = '<active>'::uuid
  AND is_deleted = false
GROUP BY account_code, aux_type, aux_code, aux_name;
```

**预期**：planner 选择 `idx_tb_aux_balance_active_queries`；聚合开销与基线
一致（同样的 rows，只是索引形状更紧）。

---

### Q4 — 跨表比对（L3 validator `balance vs ledger`）

业务场景：`validator._validate_l3_balance_ledger_consistency` 检查余额表科目
闭合与序时账累计发生额一致。

#### 改造前

```sql
-- 两端分别按 is_deleted=false 查
EXPLAIN (ANALYZE, BUFFERS)
WITH balance_agg AS (
  SELECT account_code, SUM(closing_debit - closing_credit) AS bal_close
  FROM tb_balance
  WHERE project_id = '<pid>' AND year = 2024 AND is_deleted = false
  GROUP BY account_code
),
ledger_agg AS (
  SELECT account_code,
         SUM(COALESCE(debit_amount, 0) - COALESCE(credit_amount, 0)) AS led_net
  FROM tb_ledger
  WHERE project_id = '<pid>' AND year = 2024 AND is_deleted = false
  GROUP BY account_code
)
SELECT b.account_code, b.bal_close, l.led_net,
       ABS(b.bal_close - l.led_net) AS diff
FROM balance_agg b
JOIN ledger_agg l USING (account_code)
WHERE ABS(b.bal_close - l.led_net) > 1.0;
```

#### 改造后

```sql
-- dataset_id 过滤 + partial index
EXPLAIN (ANALYZE, BUFFERS)
WITH balance_agg AS (
  SELECT account_code, SUM(closing_debit - closing_credit) AS bal_close
  FROM tb_balance
  WHERE project_id = '<pid>' AND year = 2024
    AND dataset_id = '<active>' AND is_deleted = false
  GROUP BY account_code
),
ledger_agg AS (
  SELECT account_code,
         SUM(COALESCE(debit_amount, 0) - COALESCE(credit_amount, 0)) AS led_net
  FROM tb_ledger
  WHERE project_id = '<pid>' AND year = 2024
    AND dataset_id = '<active>' AND is_deleted = false
  GROUP BY account_code
)
SELECT b.account_code, b.bal_close, l.led_net,
       ABS(b.bal_close - l.led_net) AS diff
FROM balance_agg b
JOIN ledger_agg l USING (account_code)
WHERE ABS(b.bal_close - l.led_net) > 1.0;
```

**预期**：两端 CTE 都能走 active_queries partial index；整体不会因 dataset_id
多加一个条件而触发 Bitmap→Seq Scan 切换（partial index 已针对 active 预过滤）。

---

### Q5 — activate 前快速校验（integrity check）

业务场景：`DatasetService.activate` 在激活前核对 staged 物理行数。

```sql
-- 对应代码：DatasetService._row_counts_for_dataset
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM tb_balance WHERE dataset_id = '<staging>'::uuid;
```

**预期 plan**：
- Index Only Scan on `tb_balance_dataset_id_idx`
- Rows In: staged dataset 行数；Execution Time: 通常 < 100ms

此查询和 B' 无关（不过 is_deleted），纯粹验证 `dataset_id` 索引是否仍然
高效。

## YG2101 基准引用

YG2101 是本 spec 最重要的性能基准（128MB/200 万行 xlsx）：

| Phase | 改造前 | 改造后（B'） |
|-------|--------|-------------|
| detect + identify | ~20s | ~20s |
| parse + write | 270-360s | 270-360s |
| **activate（UPDATE 200 万行）** | **127-193s** | **< 1s**（仅 metadata） |
| rebuild_aux_summary | 0.7s | 0.7s |
| **Total** | **399-482s** | **270-280s** |

业务查询端（balance-tree / drill-down）保持同等响应延迟；activate 消失的
127-193s 完全是 activate UPDATE Tb* 行的 PG WAL 写入瓶颈，改造后该阶段只
UPDATE `ledger_datasets` 2 行元数据 + 写 ActivationRecord + 发 outbox 事件。

## 灰度验证 Checklist

- [ ] Day 0 部署前：Q1-Q5 在 `master` 跑 3 次取均值，记录 baseline
- [ ] Day 0 部署后 10 分钟：新老查询并存，pg_stat_statements 查 top 50 slow query
      确认无新增回归 SQL
- [ ] Day 7（`view_refactor_cleanup_old_deleted_20260517` 迁移后）：
      Q1-Q5 再跑 3 次，对比 Day 0 baseline 必须 < 1.2×
- [ ] Day 30（DROP `idx_tb_*_activate_staged` 后）：
      再跑 Q1-Q5 验证 planner 仍选择 `active_queries` 索引

## 相关索引清单

见 `backend/alembic/versions/view_refactor_activate_index_20260510.py`：

| 索引名 | 表 | 列 | WHERE | 大小（YG2101 量级） |
|--------|-----|-----|-------|----|
| `idx_tb_balance_active_queries` | tb_balance | (project_id, year, dataset_id) | is_deleted=false | ~5MB |
| `idx_tb_ledger_active_queries` | tb_ledger | (project_id, year, dataset_id) | is_deleted=false | ~30MB |
| `idx_tb_aux_balance_active_queries` | tb_aux_balance | (project_id, year, dataset_id) | is_deleted=false | ~10MB |
| `idx_tb_aux_ledger_active_queries` | tb_aux_ledger | (project_id, year, dataset_id) | is_deleted=false | ~95MB |

待 Day 30 DROP 的废弃索引：

| 索引名 | 表 | 废弃原因 | 节省 |
|--------|-----|---------|-----|
| `idx_tb_balance_activate_staged` | tb_balance | B' 后 activate 不再 UPDATE 行，此索引无用 | ~5MB |
| `idx_tb_ledger_activate_staged` | tb_ledger | 同上 | ~15MB |
| `idx_tb_aux_balance_activate_staged` | tb_aux_balance | 同上 | ~5MB |
| `idx_tb_aux_ledger_activate_staged` | tb_aux_ledger | 同上 | ~30MB |

合计约 ~55MB 可回收。

## 快速排障

- 若 Execution Time 显著退化（> 1.2× baseline）：
  1. `EXPLAIN (ANALYZE, BUFFERS)` 对比 Rows Out 是否一致 — 不一致说明
     `dataset_id` 过滤丢失（可能是 `get_active_filter` 未生效）
  2. 查 `pg_stat_user_indexes.idx_scan` — active_queries 索引是否真的在用
  3. `SELECT * FROM pg_stat_statements WHERE query LIKE '%tb_ledger%'`
     top 10 看是否有新加的 Full Scan
- 若 Planning Time 退化：
  1. `ANALYZE tb_ledger;` 刷新统计信息
  2. 检查 autovacuum 是否追得上（见 conventions.md 表膨胀检测）

## 相关文档

- `docs/adr/ADR-002-ledger-view-refactor.md` — 架构决策
- `docs/adr/ADR-003-ledger-import-recovery-playbook.md` — 故障剧本
- `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` §可见性架构 — 业务逻辑层解读
- `.kiro/specs/ledger-import-view-refactor/requirements.md` §3.3 性能目标
