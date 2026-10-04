# Checksum 漂移调查报告（8 条，critical=0）

调查日期：2026-10-04 · 范围：后端启动 WARNING 报的 8 条 migration checksum 漂移 · 只读调查，未改任何代码/迁移/库。

## 结论摘要（先看这里）

8 条漂移经逐条 git diff + 真库逐对象核验，分类如下：

- **6 条 (a/b) 无需补迁移**：V006 / V010 / V016 是「`CREATE` → `CREATE … IF NOT EXISTS` / 包 `DO` 块」的幂等化改写，无新增 schema 对象，且声明对象在库中全部存在；V017、V051、V057 当前文件声明的全部对象在库中已存在（V017 的效果经其后迁移/途径已落库）。
- **2 条 (c) 需要写补齐迁移**，共缺 4 个对象：
  - **V005**：当前文件声明的 SECURITY DEFINER 函数 `admin_query_all_reports()` 在库中**缺失**（同文件的 `admin_query_all_working_papers()`、4 条 `project_isolation` 策略、3 个索引均已存在）。
  - **V019（磁盘文件已换成另一迁移）**：当前 `V019__add_note_section_id_columns.sql` 声明的 CHECK 约束 `ck_disclosure_notes_level_range` 与 2 个索引 `ix_disclosure_notes_project_year_section_id`、`ix_disclosure_notes_parent_section_id` 在库中**缺失**（7 个列已由 V051 补齐，存在）。

> 🔴 **V017 / V019 是「同版本号被换成全新迁移」的特殊漂移**：schema_version 登记的 stored filename 与磁盘文件名不同（见下表），MigrationRunner 按**版本号数字**匹配而非文件名，所以这两个版本槽现在装的是**与应用时完全不同的迁移**；由于版本号已登记为「已应用」，磁盘上的新迁移内容**从未被执行**。V017 的新内容效果恰好已由其它途径落库（import_jobs 列 / job_status_enum 均在），V019 的新内容只有 7 个列经 V051 落库，约束与索引仍缺。

### 总表

| version | stored(前12) | current(前12) | diff 性质 | 真库核验结论 | 裁定 | 需补迁移 |
|---|---|---|---|---|---|---|
| V005 | `4c3b449f79b7` | `1f090aa8e4b3` | 加注释 + 新增 4 条 RLS 策略 + 2 个 SECURITY DEFINER 函数（含 DDL） | 策略 4/4、函数仅 `admin_query_all_working_papers` 在；`admin_query_all_reports` **缺** | **c** | **是** |
| V006 | `5d8bc687d695` | `e208aa45e2fd` | 仅 `CREATE`→`CREATE IF NOT EXISTS`（表+3索引），无新对象 | eqcr_snapshots 表 + 3 索引全在 | a | 否 |
| V010 | `75b4426d7af3` | `14a8718657cf` | 仅 3 个 `CREATE INDEX`→`IF NOT EXISTS`，无新对象 | 3 索引全在 | a | 否 |
| V016 | `1b8bd5a05e34` | `d7ad301fcb44` | 把裸 ALTER/INDEX 包进 `DO $body$` 存在性守卫，对象集合不变 | version/previous_version_id 列 + 2 索引全在 | a | 否 |
| V017 | `4eaa3d8d8c33` | `fb46b27d6ab7` | **文件被替换**（stored=`v3_refinement_tables`，disk=`fix_schema_drift`）；新迁移从未执行 | 新文件声明的 job_status_enum / 3 列 / interrupted 值全在（经其它途径落库） | b | 否 |
| V019 | `72eadeb331ed` | `ee63dd219d63` | **文件被替换**（stored=`seed_workpaper_template_version`，disk=`add_note_section_id_columns`）；新迁移从未执行 | 7 列在（V051 补），**CHECK 约束 + 2 索引缺** | **c** | **是** |
| V051 | `48054d52f39a` | `5fac97552 4e9` | stored 匹配不上任何提交；磁盘==唯一提交版本 | 声明的全部列（12 表 deleted_at + 多表列）与 3 个 enum 值全在 | b | 否 |
| V057 | `d345271b6d5e` | `bf087518cfe4` | stored 匹配不上任何提交；磁盘==唯一提交版本 | editing_locks 表 + 3 索引全在 | b | 否 |

裁定图例：**a** = 仅注释/格式/等价重排，无 schema 影响；**b** = 含/可能含 DDL 但效果已在库；**c** = 含 DDL 且效果在库缺失，需补迁移。

---

## 方法与证据

### checksum 算法（与 MigrationRunner 一致）

`backend/app/core/migration_runner.py::scan_migrations`（约 390-407 行）：
```python
content = f.read_text(encoding="utf-8")
checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
```
`detect_checksum_drift`（约 470-512 行）按 **version 数字** 把 `disk_by_version[version]` 与 schema_version 行的 stored checksum 比对，磁盘无同版本文件则跳过。本报告复算用同一方式（`read_text(utf-8)` 后 `sha256`），复算得到的 8 条漂移与启动日志完全一致：V005/V006/V010/V016/V017/V019/V051/V057（日志点名 5 条 + "还有 3 项" = V019/V051/V057）。

### 漂移清单（stored vs 磁盘 全值）

| version | stored checksum | current(disk) checksum | stored filename | disk filename |
|---|---|---|---|---|
| V005 | `4c3b449f79b731e05b0d5a956d6f45974e58bd0c13254f3767c6b7ccb42a5a72` | `1f090aa8e4b386f8fed4d1a0aadb7d997d8c3d7f4d6dd6afa4a4d83ebb907d97` | V005__enable_rls.sql | V005__enable_rls.sql |
| V006 | `5d8bc687d6955c41991a8c6e6fa2e779dbaf57ab3adacc0fa00117753062a826` | `e208aa45e2fd7711e28da2198c1d84761c5d9043a4af2879b53c733fdd3e7924` | V006__eqcr_snapshots.sql | V006__eqcr_snapshots.sql |
| V010 | `75b4426d7af3aa6329f7aa27c0df2c3e8d23fec96a297f17afdcb56052ea53f7` | `14a8718657cfb215d5532f0cf61be2f7f8ad1f91d6a4e4c93b60ea2de8adbea4` | V010__work_hour_entries.sql | V010__work_hour_entries.sql |
| V016 | `1b8bd5a05e34057a30282e5b0d48c0d5cb5ba0c10f1129172432d157c5ca4aed` | `d7ad301fcb44bcfffa59274533df28e3bca34b8d064cf5cc953d46aebdeeb69c` | V016__add_kb_document_version.sql | V016__add_kb_document_version.sql |
| V017 | `4eaa3d8d8c33f7fd57d2afa48ceb5326cc58b4d6e47f280ebcb0af8ab965aed3` | `fb46b27d6ab7f2e37c1c67c0a7969dbd3360b94e4684cd426aa0b8301caba3b6` | **V017__v3_refinement_tables.sql** | **V017__fix_schema_drift.sql** |
| V019 | `72eadeb331edeab7e9738d64984cfb74a0e657f9d37f357c61e65a41c5a2d1f6` | `ee63dd219d63ceadb782949e7cd67a6ffc74e5c9c705b15db63d20f33d6ad495` | **V019__seed_workpaper_template_version.sql** | **V019__add_note_section_id_columns.sql** |
| V051 | `48054d52f39a257c013aec7b9966bf7c45b122fa32378c943c3a37101ef36fcf` | `5fac975524e9fddf96e47c869cce17a976ea2f24cdac23179b5b9c56e882a9f1` | V051__fix_schema_drift_orm_extra.sql | V051__fix_schema_drift_orm_extra.sql |
| V057 | `d345271b6d5e092e835f10863d244962976836fc33012c268ce9dce1ba686dd4` | `bf087518cfe47ac97adbd1e990b0022b50dcfbeb3a817fa2e83586c1c01f1b79` | V057__editing_locks.sql | V057__editing_locks.sql |

补充观察：V017 的 stored checksum `4eaa3d8d…` 与 schema_version 里 **V037** 的 checksum 完全相同；V019 的 stored `72eadeb3…` 与 **V038** 相同。即原来的 `v3_refinement_tables` / `seed_workpaper_template_version` 迁移被重编号到 V037/V038（内容未变、校验值相同），V017/V019 版本槽被新迁移占用。

### 真库核验（docker exec audit-postgres psql -U <PG_USER> -d audit_platform）

PG 连接信息取自 `d:\GT_plan\.env`（`PG_USER` / `PG_DB=audit_platform` / `PG_PORT`，密钥值不回显）。查询用容器内 psql 最稳（规避宿主 5432 端口转发陈旧坑）。

---

## 逐条详述

### V005 — 裁定 c（需补迁移）

**diff 性质**：stored checksum `4c3b449f…` 不匹配任何 git 提交（应用时为一个未提交的中间版本）。相对最早提交版本（`b98cdc51f`，只有 ALTER ENABLE/FORCE + 3 索引），当前磁盘新增了：4 条 `CREATE POLICY project_isolation`（working_paper/adjustments/tb_balance/review_records）、2 个 `CREATE OR REPLACE FUNCTION … SECURITY DEFINER`（`admin_query_all_working_papers`、`admin_query_all_reports`）。这些是 schema 对象。

**真库核验**：
```
pg_class.relrowsecurity/relforcerowsecurity: 4 表均 t/t ✓
pg_policies project_isolation:  working_paper/adjustments/tb_balance/review_records 4/4 ✓
pg_proc admin_query_all%: 仅 admin_query_all_working_papers  ← admin_query_all_reports 缺失 ✗
to_regclass('public.financial_report'): financial_report  ← 目标表存在，函数可建
索引 idx_{working_paper,adjustments,tb_balance}_project_id: 3/3 ✓
```
git 侧佐证：b98cdc51f 版本无任何 policy/function；d0b1d9b19 与 5453e3e09 才同时加入两个函数。stored 对应的中间版本显然建了策略 + 第一个函数（已在库），但未建 `admin_query_all_reports`。

**裁定理由**：当前文件声明的 `admin_query_all_reports()` 含 DDL 且库中缺失 → **(c)**。`backend/migrations/R005__disable_rls.sql` 已含 `DROP FUNCTION IF EXISTS admin_query_all_reports();`，可作补迁移回滚参考。

### V006 — 裁定 a

**diff**（vs 应用版 b98cdc51f）：`CREATE TABLE eqcr_snapshots` → `CREATE TABLE IF NOT EXISTS …`；3 个 `CREATE [UNIQUE] INDEX` → 加 `IF NOT EXISTS`。无新增/修改对象，纯幂等化。
**真库**：`to_regclass eqcr_snapshots` 存在；索引 `idx_eqcr_snapshots_current/project_year/created_at` 3/3 存在。→ 无 schema 影响，可直接登记。

### V010 — 裁定 a

**diff**（vs b98cdc51f）：3 个 `CREATE INDEX` → `IF NOT EXISTS`，表定义未变。
**真库**：`idx_whe_user_date/project_status/project_cycle` 3/3 存在。→ 纯幂等化。

### V016 — 裁定 a

**diff**（vs d0b1d9b19）：把两条 `ALTER TABLE knowledge_documents ADD COLUMN` + 2 索引 + 2 COMMENT 包进 `DO $body$ … END $body$;` 存在性守卫（表不存在时 RAISE NOTICE 跳过）。声明对象集合不变。
**真库**：列 `version`、`previous_version_id` 存在；索引 `idx_kb_documents_version_chain`、`idx_kb_documents_previous_version` 存在。→ 幂等/防御化改写，无 schema 影响。

### V017 — 裁定 b（文件被替换，新内容恰已落库）

**diff 性质**：版本槽文件名由 `V017__v3_refinement_tables.sql`（stored）替换为 `V017__fix_schema_drift.sql`（disk）。原 `v3_refinement_tables` 内容重编号到 V037（checksum 相同）。磁盘新文件声明：`job_status`→`job_status_enum` 重命名/新建 enum、`ADD VALUE 'interrupted'`、`import_jobs` 加 `version`/`force_submit`/`creator_chain`。因版本号 017 已登记应用，**此新文件从未由 runner 执行**。
**真库**：`pg_type` 存在 `job_status_enum`（无 `job_status`）；`interrupted` 值 present=t；`import_jobs` 列 `version`/`force_submit`/`creator_chain` 3/3 存在。全部效果已在库（经 ORM 创建枚举 / 其它途径落库）。
**裁定理由**：声明对象虽含 DDL，但效果已全部存在 → **(b)**，无需补迁移。

### V019 — 裁定 c（文件被替换，新内容部分缺失）

**diff 性质**：版本槽文件名由 `V019__seed_workpaper_template_version.sql`（stored，重编号到 V038）替换为 `V019__add_note_section_id_columns.sql`（disk）。磁盘新文件声明 `disclosure_notes` 加 7 列（section_id/level/parent_section_id/sort_index/auto_numbering/lock_number/locked_number）+ 1 CHECK 约束 `ck_disclosure_notes_level_range` + 2 索引。因版本号 019 已登记应用，**此新文件从未由 runner 执行**。
**真库**：
```
7 列: section_id/level/parent_section_id/sort_index/auto_numbering/lock_number/locked_number 全在 ✓（由 V051 第 5 节同样 ADD COLUMN 落库）
pg_constraint ck_disclosure_notes_level_range: 0 行  ← 缺失 ✗
pg_indexes ix_disclosure_notes_project_year_section_id / ix_disclosure_notes_parent_section_id: 0 行  ← 均缺失 ✗
（disclosure_notes 现有约束仅 pkey + 2 fkey；现有索引仅 pkey / consol_breakdown / uq_active）
```
**裁定理由**：当前文件声明的 CHECK 约束与 2 个索引含 DDL 且库中缺失（V051 只补了列，没补约束和索引）→ **(c)**。`backend/migrations/R019__rollback_note_section_id_columns.sql` 已含对应 DROP，可作回滚参考。

> 注：缺失的 CHECK 约束保证 `level ∈ {NULL,1..5}`，缺失会放过越界 level；2 索引影响 numbering service 的 (project_id,year,section_id) 定位与 parent_section_id 树遍历性能。补约束前宜先查 `disclosure_notes` 是否已有越界 level 行（见补迁移清单备注）。

### V051 — 裁定 b

**diff 性质**：stored `48054d52…` 不匹配任何提交；磁盘内容 == 唯一提交版本（b0756b35e）。即应用时跑的是一个与最终提交略有差异的未提交working-tree 版本，最终提交后未再改。
**真库**：当前文件声明的全部对象逐一核验存在——12 张表的 `deleted_at`（12/12）、attachment_working_paper 2 列、tb_aux_balance.accounting_period、t_account_entries 5 列、import_batches 2 列、review_messages 7 列、wp_template_custom.formula_valid、custom_query_templates 4 列、time_machine_snapshots 4 列、review_conversations 6 列、gate_decisions.context；enum 值 `activation_type.force_unbind`、`subsequent_event_type.ADJUSTING/NON_ADJUSTING` present=t。
**裁定理由**：声明对象（含 DDL）效果在库全在 → **(b)**，无需补迁移。

### V057 — 裁定 b

**diff 性质**：同 V051，stored 不匹配任何提交，磁盘 == 唯一提交版本（b61079c5f）。
**真库**：`to_regclass editing_locks` 存在；索引 `idx_editing_locks_resource`、`idx_editing_locks_heartbeat`、`uq_editing_locks_active` 3/3 存在。
**裁定理由**：声明对象全在 → **(b)**。

---

## 需补迁移清单（2 条，取 V177 之后连号）

> 处置顺序遵循 `migration_drift_ledger.py` docstring：先补齐迁移落库缺失对象，**再**把漂移登记到 `KNOWN_CHECKSUM_DRIFTS`；**绝不**改写 schema_version 的 checksum。两条漂移在补迁移跑完后 schema 层缺口即消除，但 checksum 漂移本身依然存在（文件被事后编辑是既成事实），因此仍需登记。

### 补迁移 1：V178 — 补 V005 缺失的 admin bypass 函数

```sql
-- V178__repair_v005_admin_query_all_reports.sql
-- V005 应用时的中间版本未建 admin_query_all_reports()，当前文件声明了但从未执行。
-- 补齐该 SECURITY DEFINER 函数（admin_query_all_working_papers 已在库，不重建亦无害）。
CREATE OR REPLACE FUNCTION admin_query_all_reports()
RETURNS SETOF financial_report
LANGUAGE sql SECURITY DEFINER
AS 'SELECT * FROM financial_report WHERE is_deleted = false';
```
配套回滚 **R178**：`DROP FUNCTION IF EXISTS admin_query_all_reports();`（与 R005 一致）。

### 补迁移 2：V179 — 补 V019 缺失的 CHECK 约束 + 2 索引

```sql
-- V179__repair_v019_disclosure_notes_constraint_and_indexes.sql
-- V019 版本槽被新迁移替换，新内容从未执行；7 列已由 V051 补，约束+2 索引仍缺。
-- 补约束前确认无越界 level 数据：
--   SELECT count(*) FROM disclosure_notes WHERE level IS NOT NULL AND level NOT BETWEEN 1 AND 5;
-- 若 >0 需先清洗，否则 ADD CONSTRAINT 会失败。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_disclosure_notes_level_range') THEN
        ALTER TABLE disclosure_notes
            ADD CONSTRAINT ck_disclosure_notes_level_range
            CHECK (level IS NULL OR (level BETWEEN 1 AND 5));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_disclosure_notes_project_year_section_id
    ON disclosure_notes (project_id, year, section_id);
CREATE INDEX IF NOT EXISTS ix_disclosure_notes_parent_section_id
    ON disclosure_notes (parent_section_id);
```
配套回滚 **R179**：
```sql
DROP INDEX IF EXISTS ix_disclosure_notes_parent_section_id;
DROP INDEX IF EXISTS ix_disclosure_notes_project_year_section_id;
ALTER TABLE disclosure_notes DROP CONSTRAINT IF EXISTS ck_disclosure_notes_level_range;
```
（即 R019 的子集，仅针对补齐的 3 个对象。）

### 登记到 migration_drift_ledger.py 的 KnownChecksumDrift 文案建议（全部 8 条）

补迁移跑完后，把这 8 条新增进 `KNOWN_CHECKSUM_DRIFTS`（三元组 version/stored/current 必须与实测逐字一致；stored/current 用全 64 位值，下表给前缀，全值见上「漂移清单」表）。resolution 文案建议：

| version | stored | current | resolution 文案建议 |
|---|---|---|---|
| 005 | `4c3b449f…`(全64位) | `1f090aa8…` | 应用时为未提交中间版本（已建 4 策略 + admin_query_all_working_papers）；当前文件新增的 admin_query_all_reports() 从未执行，已由 V178 补齐。逐对象核验其余策略/函数/索引在 public 全部存在。 |
| 006 | `5d8bc687…` | `e208aa45…` | 应用后被编辑：仅 CREATE→CREATE IF NOT EXISTS 幂等化，无新增对象；eqcr_snapshots 表 + 3 索引在 public 全部存在，无需补迁移。 |
| 010 | `75b4426d…` | `14a87186…` | 应用后被编辑：仅 3 个 CREATE INDEX 加 IF NOT EXISTS，无新对象；3 索引在 public 全部存在，无需补迁移。 |
| 016 | `1b8bd5a0…` | `d7ad301f…` | 应用后被编辑：ALTER/INDEX 包进 DO $body$ 存在性守卫，对象集合不变；version/previous_version_id 列 + 2 索引在 public 全部存在，无需补迁移。 |
| 017 | `4eaa3d8d…` | `fb46b27d…` | 版本槽文件被替换（原 v3_refinement_tables 重编号至 V037）；新文件 fix_schema_drift 从未由 runner 执行，但其声明的 job_status_enum/interrupted/import_jobs 三列效果经其它途径已在 public 全部存在，无需补迁移。 |
| 019 | `72eadeb3…` | `ee63dd21…` | 版本槽文件被替换（原 seed_workpaper_template_version 重编号至 V038）；新文件 add_note_section_id_columns 从未执行，7 列已由 V051 补，缺失的 ck_disclosure_notes_level_range + 2 索引已由 V179 补齐。 |
| 051 | `48054d52…` | `5fac9755…` | 应用时为未提交 working-tree 版本，最终提交后未再改；当前文件声明的全部列（12 表 deleted_at + 多表列）与 3 个 enum 值在 public 全部存在，无需补迁移。 |
| 057 | `d345271b…` | `bf087518…` | 应用时为未提交 working-tree 版本；editing_locks 表 + 3 索引在 public 全部存在，无需补迁移。 |

---

## 调查用一次性脚本（交付后清理）

- `backend/scripts/analyze/_cd8_compute.py` — 复算磁盘 checksum + 对比 schema_version，列出 8 条漂移
- `backend/scripts/analyze/_cd8_matchblob.py` — 对每个漂移在 git 历史里找 stored checksum 对应提交
- `backend/scripts/analyze/_cd8_diff.py` / `_cd8_diff3.py` — 产出 applied-version vs 磁盘 diff
- `backend/scripts/analyze/_cd8_verify.sql` — 真库逐对象核验（已 docker cp 到容器 /tmp）
- `.agents/tasks/checksum-drift-8/_diffs.txt` — diff 原始输出（UTF-16）

（`_` 前缀 = 一次性用完即删，按仓库 scripts 规约应在交付后清理；本次为只读调查未删，留待处置阶段清理。）
