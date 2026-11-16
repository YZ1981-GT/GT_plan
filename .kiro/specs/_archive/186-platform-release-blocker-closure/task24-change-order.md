# Task 24 外部停点变更单（待用户批准后执行）

> 本批（platform-release-blocker-closure）**不执行**下列任何共享库写操作。本文件是调查结论 +
> 需用户逐项批准的变更清单，含备份与回退 SQL。所有调查均为只读（SELECT / pg_catalog / 平台只读方法）。
> 调查日期 2026-11-05，库 `localhost:5432/audit_platform`。

---

## 一、审计链 10 个分叉 —— 已全部确认，**无需任何操作**

原 tasks.md / requirements.md 写「调查审计链 10 个分叉」。实测结论：**这 10 个分叉在 2026-11-04
已由 `audit.fork_ack` 全部确认完毕，当前每条链恰好一个未确认链尾，无阻断。**

证据（只读）：
- `audit_log_entries` 共 6470 行；`prev_hash` 出现多后继的分叉点 9 个（另有创世哈希
  `0000…` 作为 1336 条独立链的共同起点，按 `scan_forks` 口径不算分叉）。
- 9 个分叉点全部 `survivors = 1`（存活后继恰好 1 个），其余后继已被 `fork_ack` 标为死端。
- `fork_ack` 确认条目共 11 条（两批：`batch_id=826f7705…` 10 条于 11-04 11:56:32、
  `batch_id=b9a600e4…` 1 条于 11-04 11:56:41，operator `b6f8e8d0…`，reason
  "legacy concurrent branches; preserve latest connected branch"）。其中 1 条属项目
  `0ec33ac9…`（重药安徽），其余为 `__global__` 链。
- 平台只读工具 `python -m scripts.ops.audit_chain_fork_ack` 输出：
  「✅ 没有被阻断的链（每条链恰好一个未确认链尾）」「分叉点扫描：9 处，其中未确认 0 处」。
- 等价 SQL（`head._tail_ids` 口径）复算：未确认链尾 ≠ 1 的链 = **0**。

> 说明：原记录「10 个分叉」与实测「9 个分叉点 + 11 条确认条目」的数字差，来自口径不同
> （9 是 prev_hash 分叉点数、11 是确认条目数、其中有 1 个 3-后继分叉点需 2 条确认）。
> 无论按哪种口径，**当前都已全部确认、无待办**。本项**从变更单移除**，仅作现状记录。

---

## 二、迁移销案 —— **无需执行任何迁移**

用平台自己的 `MigrationRunner`（只读方法 `inspect_readiness` / `detect_checksum_drift`，
`ensure_schema_version_table` 已替换 no-op 保证零 DDL）核对：

- 磁盘迁移文件 252、`schema_version` 已登记 254、`schema_migration_failures` = 0。
- **pending（待执行）= []**、**failures = []**、`is_complete = True`。
- 历史孤儿（库里有/磁盘无）= V200 / V201 —— 两条均已在 `migration_drift_ledger` 标
  `file_removed=True`（内容合并到 V186），runner 扫不到、运行期不报漂移。
- checksum 漂移 11 条，经 `unexplained_checksum_drift` 判定**未解释 = 0**（本批新登记
  V233 / V234 两条，逐对象核验见下）。

结论：**共享库迁移集合完整，无需执行待迁移。** 本项**从变更单移除**。

### V233 / V234 漂移的逐对象核验（已在代码登记，非共享库写）
- 两条均为 2026-10-30-31 开发号 V227/V228 以其内容登记后、10-31 改号为 V233/V234 时只改了
  版本号文字（V233 改首行注释；V234 改 3 行注释 + 函数注释字面量 'V228：'→'V234：'），
  SQL 语句体逐字不变。
- 逐对象核验 public（只读）：
  - V233：表 `project_creation_grants`（15 列）、3 CHECK、3 FK、PK、2 部分索引
    (`uq_..._active` / `ix_..._grantee_valid`)、表注释、version 列注释 —— **全部存在**。
  - V234：函数 `gt_is_valid_uscc(p_code text)` 存在且 IMMUTABLE/STRICT/PARALLEL SAFE、
    库内函数体与当前文件逐字一致、约束 `ck_project_creation_grants_code_checksum` 存在且
    convalidated、数据不变式（未撤销且 USCC 校验失败的授权 = 0）成立；函数与
    `uscc_validator.validate_uscc` 在 39 个码（33 真实 company_code + 6 合成）上**逐值一致**。
  - 唯一未生效差异：V234 函数注释里版本号文字库内仍为 'V228：…'（纯文档，无行为影响）。
    为此单开迁移风险 > 收益，**不补迁移**；日后若有别的 COMMENT 修补迁移可顺带改正。
- 已在 `backend/app/core/migration_drift_ledger.py` 登记这两条（代码改动，非共享库写），
  真库守卫 `test_migration_integrity_pg.py` 17 passed；摘除这两条登记后该守卫
  `test_no_unexplained_checksum_drift` / `test_checksum_comparison_actually_ran` 打红（变异已证，已逐字节还原）。

---

## 三、10 条 NOT VALID 约束 VALIDATE —— **待批准（安全，0 违反行）**

| # | 表 | 约束 | 类型 | 行数 | 违反行 |
|---|---|---|---|---|---|
| 1 | adjustment_entries | ck_adjustment_entries_nonnegative | CHECK | 16 | 0 |
| 2 | adjustment_entries | ck_adjustment_entries_one_side | CHECK | 16 | 0 |
| 3 | adjustments | ck_adjustments_audit_phase | CHECK | 16 | 0 |
| 4 | adjustments | ck_adjustments_content_revision | CHECK | 16 | 0 |
| 5 | evidence_links | fk_evidence_links_wp | FK | 0 | 0（空表平凡满足） |
| 6 | evidence_links | fk_evidence_links_attachment | FK | 0 | 0 |
| 7 | workpaper_extraction_log | chk_extraction_log_fill_mode | CHECK | 1 | 0（该行 fill_mode='append'） |
| 8 | workpaper_extraction_log | chk_extraction_log_status | CHECK | 1 | 0（status='filled'） |
| 9 | workpaper_extraction_log | chk_extraction_log_type | CHECK | 1 | 0（type='voucher_sampling'） |
| 10 | workpaper_extraction_log | fk_extraction_log_user | FK | 1 | 0（user_id 存在于 users） |

> 注：`workpaper_extraction_log` 实为 1 行（2026-10-13 重药安徽抽凭记录，非本批产生；
> 首次核验时 `pg_stat_user_tables.n_live_tup` 为过期统计显示 0，已用直接 COUNT 纠正）。该行满足全部 3 CHECK + FK。

- 全部已是 CHECK / FK（建表时以 `NOT VALID` 加，仅跳过对历史行的一次性校验，对**新写入**始终生效）。
- `VALIDATE CONSTRAINT` 只取 `SHARE UPDATE EXCLUSIVE` 锁，不阻塞读写；现有数据 0 违反，秒级完成。
- 风险极低：若真有违反行会直接报错回滚（不会破坏数据）。

**执行 SQL（逐条，可分批）：**
```sql
ALTER TABLE adjustment_entries VALIDATE CONSTRAINT ck_adjustment_entries_nonnegative;
ALTER TABLE adjustment_entries VALIDATE CONSTRAINT ck_adjustment_entries_one_side;
ALTER TABLE adjustments        VALIDATE CONSTRAINT ck_adjustments_audit_phase;
ALTER TABLE adjustments        VALIDATE CONSTRAINT ck_adjustments_content_revision;
ALTER TABLE evidence_links     VALIDATE CONSTRAINT fk_evidence_links_wp;
ALTER TABLE evidence_links     VALIDATE CONSTRAINT fk_evidence_links_attachment;
ALTER TABLE workpaper_extraction_log VALIDATE CONSTRAINT chk_extraction_log_fill_mode;
ALTER TABLE workpaper_extraction_log VALIDATE CONSTRAINT chk_extraction_log_status;
ALTER TABLE workpaper_extraction_log VALIDATE CONSTRAINT chk_extraction_log_type;
ALTER TABLE workpaper_extraction_log VALIDATE CONSTRAINT fk_extraction_log_user;
```

**回退（如需恢复 NOT VALID 状态，极少需要）：** VALIDATE 只是把 `convalidated` 置 true，
无数据改动。若确需回退：`DROP CONSTRAINT` 后按原定义 `ADD CONSTRAINT ... NOT VALID` 重建
（原定义见 `pg_get_constraintdef`，已在调查中留存）。因无数据风险，通常无需回退。

**执行前再次只读确认（必跑）：** 对 4 条 CHECK 重算违反行数应全部 = 0；若非 0 则暂停并上报。

---

## 四、3 个膨胀索引 REINDEX —— **待批准**

| 索引 | 表 | 当前大小 | 膨胀 | 表大小 |
|---|---|---|---|---|
| idx_tb_aux_ledger_active_window | tb_aux_ledger | 1800 MB | 368.5 MB | 19 GB |
| tb_aux_ledger_pkey | tb_aux_ledger | 602 MB | 183.1 MB | 19 GB |
| idx_tb_ledger_active_window | tb_ledger | 660 MB | 129.6 MB | 7354 MB |

- invalid index = 0，三者 `indisvalid = True`，均在用。
- 平台已有运维脚本 `backend/scripts/ops/maintain_table_bloat.py`（默认 dry-run，生产优先 pg_repack）。
- 建议用 **REINDEX INDEX CONCURRENTLY**（不长时间持有写锁；需在业务低峰，且不能在事务块内）。
  `tb_aux_ledger_pkey` 为主键唯一索引，`REINDEX ... CONCURRENTLY` 支持（PG12+）。

**执行命令（每条单独、非事务块、低峰执行）：**
```sql
REINDEX INDEX CONCURRENTLY idx_tb_aux_ledger_active_window;
REINDEX INDEX CONCURRENTLY idx_tb_ledger_active_window;
REINDEX INDEX CONCURRENTLY tb_aux_ledger_pkey;
```

**风险与回退：**
- REINDEX CONCURRENTLY 失败会留下 `*_ccnew` 残留无效索引，需 `DROP INDEX` 清理后重试；原索引不受影响（回退 = 什么都不做，旧索引继续用）。
- 需确保执行期磁盘有额外空间（约等于被重建索引大小：峰值 +1.8 GB）。
- 收益：三者合计回收约 680 MB 膨胀 + 提升 active-window 扫描效率。非紧急（vacuum 无 wraparound 风险）。

---

## 五、批准方式

请对 **三、四** 两节逐节批准（一、二已无待办）。批准后我在**执行前再跑一次只读确认**
（VALIDATE 的 0 违反行、REINDEX 的磁盘空间与低峰窗口），确认通过才执行，并在执行后复验
`convalidated = true` / 新索引 `indisvalid = true` 且无 `*_ccnew` 残留。
