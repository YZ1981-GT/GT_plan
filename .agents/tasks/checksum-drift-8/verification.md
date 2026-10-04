# Checksum 漂移处置 — 真库验证证据（iteration 2 补齐）

本文件补齐 review.json / review.md 唯一 blocking finding「Verification evidence absent」所要求的实测证据。
代码半（V178/R178、V179/R179、ledger 追加 8 条）已由 commit `e96f11171` 完成且 review 判为 correct；本轮只补证据，未改任何迁移/ledger 代码。

验证日期：见运行记录 · 真库 = PG16 Docker 容器 `audit-postgres` / db `audit_platform` · 查询一律 `docker exec audit-postgres psql -U <PG_USER> -d audit_platform`（规避宿主 5432 转发陈旧）。

---

## 步骤 2（V179 前置安全检查）：无越界 level 数据

```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT count(*) FROM disclosure_notes WHERE level IS NOT NULL AND level NOT BETWEEN 1 AND 5;"
```
结果：
```
 count
-------
     0
(1 row)
```
count = 0 → ADD CONSTRAINT 不会失败，V179 可安全应用（无需清洗数据）。

## 步骤 4a：schema_version 已有 V178/V179 行（迁移经 MigrationRunner 正式路径落库）

```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT version, filename FROM schema_version WHERE version IN ('178','179') ORDER BY version;"
```
结果：
```
 version |                           filename
---------+---------------------------------------------------------------
 178     | V178__repair_v005_admin_query_all_reports.sql
 179     | V179__repair_v019_disclosure_notes_constraint_and_indexes.sql
(2 rows)
```
schema_version 写入了 178/179 两行 → 下次启动不会把它们当待应用重跑。

## 步骤 4b：3 个缺失对象现已存在

### admin_query_all_reports（pg_proc）
```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT proname FROM pg_proc WHERE proname='admin_query_all_reports';"
```
```
         proname
-------------------------
 admin_query_all_reports
(1 row)
```

### ck_disclosure_notes_level_range（pg_constraint）
```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT conname FROM pg_constraint WHERE conname='ck_disclosure_notes_level_range';"
```
```
             conname
---------------------------------
 ck_disclosure_notes_level_range
(1 row)
```

### ix_disclosure_notes_project_year_section_id + ix_disclosure_notes_parent_section_id（pg_indexes）
```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('ix_disclosure_notes_project_year_section_id','ix_disclosure_notes_parent_section_id') ORDER BY indexname;"
```
```
                  indexname
---------------------------------------------
 ix_disclosure_notes_parent_section_id
 ix_disclosure_notes_project_year_section_id
(2 rows)
```

## 步骤 5 旁证：ledger stored 与真库 schema_version checksum 逐值一致

```
docker exec audit-postgres psql -U <PG_USER> -d audit_platform \
  -c "SELECT version, checksum FROM schema_version WHERE version IN ('005','006','010','016','017','019','051','057') ORDER BY version;"
```
```
 version |                             checksum
---------+------------------------------------------------------------------
 005     | 4c3b449f79b731e05b0d5a956d6f45974e58bd0c13254f3767c6b7ccb42a5a72
 006     | 5d8bc687d6955c41991a8c6e6fa2e779dbaf57ab3adacc0fa00117753062a826
 010     | 75b4426d7af3aa6329f7aa27c0df2c3e8d23fec96a297f17afdcb56052ea53f7
 016     | 1b8bd5a05e34057a30282e5b0d48c0d5cb5ba0c10f1129172432d157c5ca4aed
 017     | 4eaa3d8d8c33f7fd57d2afa48ceb5326cc58b4d6e47f280ebcb0af8ab965aed3
 019     | 72eadeb331edeab7e9738d64984cfb74a0e657f9d37f357c61e65a41c5a2d1f6
 051     | 48054d52f39a257c013aec7b9966bf7c45b122fa32378c943c3a37101ef36fcf
 057     | d345271b6d5e092e835f10863d244962976836fc33012c268ce9dce1ba686dd4
(8 rows)
```
与 `migration_drift_ledger.py` 新增 8 条的 stored 全 64 位值逐一相等（未改写 schema_version 任何值）。

## 步骤 6：守卫测试全绿（37 passed）

```
cd d:\GT_plan\backend
..\.venv\Scripts\python.exe -m pytest tests/test_migration_drift_ledger.py -v --tb=short
```
结果：`37 passed, 1 warning in 1.13s`，含 8 条新增：
- `test_entry_current_matches_disk[V005|V006|V010|V016|V017|V019|V051|V057]` 全 PASSED（current 等于磁盘实算 checksum）
- `test_entry_is_a_real_drift_with_a_resolution[V005..V057]` 全 PASSED（三元组自洽 + resolution ≥20 字）
- `test_ledger_has_no_duplicate_versions` / `test_exact_triples_are_explained` / 变异用例 全 PASSED

## scan_migrations 同版本号检测：不误报 178/179

```
cd d:\GT_plan\backend
..\.venv\Scripts\python.exe -c "from app.core.migration_runner import MigrationRunner; from sqlalchemy.ext.asyncio import create_async_engine; r=MigrationRunner(engine=create_async_engine('sqlite+aiosqlite:///:memory:')); vs=[m.version for m in r.scan_migrations()]; assert '178' in vs and '179' in vs; assert len(vs)==len(set(vs)); print('178/179 present, no duplicate version')"
```
结果：`178/179 present, no duplicate version`（无 RuntimeError，磁盘各一个 V178/V179）。

## 步骤 7：一次性脚本已清理

```
cd d:\GT_plan
.venv\Scripts\python.exe -c "import glob; print('scripts:', glob.glob('backend/scripts/analyze/_cd8_*')); print('diffs:', glob.glob('.agents/tasks/checksum-drift-8/_diffs.txt'))"
# scripts: []   diffs: []
docker exec audit-postgres sh -c "ls /tmp/_cd8_* 2>/dev/null || echo NONE"   # NONE
```
`_cd8_*` 脚本、`_diffs.txt`、容器 /tmp 拷贝均不存在；findings.md / plan.md 保留。

---

## 结论

迁移已通过 MigrationRunner 正式路径应用（schema_version 有 178/179 行）；3 个缺失对象（1 函数 + 1 CHECK 约束 + 2 索引）在真库全部存在；8 条漂移登记的 stored 与真库逐值一致、current 与磁盘实算一致（守卫 37 passed）；scan 无撞号；一次性脚本已清理。review.json 的唯一 blocking finding（验证证据缺失）已补齐。
