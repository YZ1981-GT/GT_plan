# Implementation Plan — checksum 漂移 8 条处置

来源：本任务由权威报告 `d:\GT_plan\.agents\tasks\checksum-drift-8\findings.md` 驱动，报告已完成全部 8 条漂移（V005/V006/V010/V016/V017/V019/V051/V057，均 critical=0，health 仍 healthy）的 git diff + 真库逐对象核验。**不要重新调查漂移、不要重新推导裁定**，直接按报告实施。

关键事实（已核读源码确认）：
- checksum 算法（`backend/app/core/migration_runner.py::scan_migrations` 约 390-407 行）：`content = f.read_text(encoding="utf-8")` 然后 `hashlib.sha256(content.encode("utf-8")).hexdigest()`。守卫测试 `test_migration_drift_ledger.py` 的 `disk_checksums` fixture 用 `MigrationRunner(...).scan_migrations()` 复算磁盘 checksum，所以 ledger 里登记的 `current` 必须与此算法逐字一致。
- 当前最高版本 V177/R177 → 补迁移用 V178、V179（连号，不得与现有文件撞号；`scan_migrations` 对重复 version 抛 RuntimeError）。
- `V178` 要补的 `admin_query_all_reports()` 定义已在 `V005__enable_rls.sql` 中逐字声明（`RETURNS SETOF financial_report / LANGUAGE sql SECURITY DEFINER / AS 'SELECT * FROM financial_report WHERE is_deleted = false'`），V178 必须与 V005 的声明字节一致。
- `V179` 要补的 CHECK 约束 `ck_disclosure_notes_level_range`（`CHECK (level IS NULL OR (level BETWEEN 1 AND 5))`）与 2 索引 `ix_disclosure_notes_project_year_section_id (project_id, year, section_id)`、`ix_disclosure_notes_parent_section_id (parent_section_id)` 的定义已在 `V019__add_note_section_id_columns.sql` 中逐字声明；V179 以 V019 原文为准。
- 迁移是运行时机制（非 alembic）：`python -m app.core.migration_runner`（无参）调 `run_pending()`，按 version 数字顺序执行未应用的 `V*.sql`，并把 version/filename/checksum 写入 `schema_version`。
- `.env`：`PG_USER=postgres`、`PG_DB=audit_platform`。真库 = PG16 Docker 容器 `audit-postgres`。优先 `docker exec audit-postgres psql ...` 规避宿主 5432 端口转发陈旧坑。

环境铁律：Windows / PowerShell；python 用 `d:\GT_plan\.venv\Scripts\python.exe`（禁 python3）；禁用 `&&` 连接命令（用 `;` 或分开执行）；含中文注释的 SQL 文件用 fs_write 写入（禁 PowerShell `-replace` / `Set-Content`，中文会乱码）；不回显 `.env` 密钥值。

迁移/ledger 操作铁律（务必遵守）：
- 处置顺序 = 先补迁移落库缺失对象 → 跑迁移 → 再登记漂移。**绝不改写 `schema_version` 的 checksum 值**（那会抹掉"文件被事后编辑过"的唯一证据）。
- CREATE/ALTER 必须 IF NOT EXISTS 或 DO 块存在性守卫。
- V178 必须配 R178，V179 必须配 R179（D6 配对规则）。

---

- [ ] 1. 写补迁移 V178 + R178（补 V005 缺失的 `admin_query_all_reports()` SECURITY DEFINER 函数）。
      V178 内容：中文注释说明「V005 应用时为未提交中间版本，未建 admin_query_all_reports()，当前文件声明了但从未执行；补齐该 SECURITY DEFINER 函数（admin_query_all_working_papers 已在库，不重建）」+ 一条 `CREATE OR REPLACE FUNCTION admin_query_all_reports() RETURNS SETOF financial_report LANGUAGE sql SECURITY DEFINER AS 'SELECT * FROM financial_report WHERE is_deleted = false';`（函数签名/返回类型/函数体必须与 `V005__enable_rls.sql` 现声明字节一致；`CREATE OR REPLACE` 本身幂等）。R178 内容：`DROP FUNCTION IF EXISTS admin_query_all_reports();`（与 `R005__disable_rls.sql` 一致）。两个文件均用 fs_write 写入（含中文注释）。
      Files: `backend/migrations/V178__repair_v005_admin_query_all_reports.sql`（新建）、`backend/migrations/R178__rollback_repair_v005_admin_query_all_reports.sql`（新建）
      Verify: `d:\GT_plan\.venv\Scripts\python.exe -c "from app.core.migration_runner import MigrationRunner; from sqlalchemy.ext.asyncio import create_async_engine; r=MigrationRunner(engine=create_async_engine('sqlite+aiosqlite:///:memory:')); vs=[m.version for m in r.scan_migrations()]; assert '178' in vs; print('178 OK, no dup')"`（cwd=`d:\GT_plan\backend`）—— scan 不抛重复版本号 RuntimeError 且含 178，确认文件名合法、无撞号。

- [ ] 2. 在写 V179 之前，先查真库是否有越界 level 数据（CHECK 约束的前置安全检查）。
      运行 `docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT count(*) FROM disclosure_notes WHERE level IS NOT NULL AND level NOT BETWEEN 1 AND 5;"`。
      - 若 count = 0：继续步骤 3。
      - 若 count > 0：**暂停**（调 send_message severity "warning"，报告有越界 level 行、ADD CONSTRAINT 会失败、需用户决定是否清洗数据），**不要触碰数据、不要写/跑 V179**，等待用户答复后再继续。
      Files: 无（只读查询）
      Verify: 命令返回单个计数值；记录该值用于分支决策。

- [ ] 3. 写补迁移 V179 + R179（补 V019 缺失的 CHECK 约束 + 2 索引），仅在步骤 2 count=0 时执行。
      V179 内容：中文注释说明「V019 版本槽被新迁移替换、新内容从未执行；7 列已由 V051 补，约束+2 索引仍缺」+ 用 DO 块（`IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_disclosure_notes_level_range') THEN ALTER TABLE disclosure_notes ADD CONSTRAINT ck_disclosure_notes_level_range CHECK (level IS NULL OR (level BETWEEN 1 AND 5)); END IF;`）+ `CREATE INDEX IF NOT EXISTS ix_disclosure_notes_project_year_section_id ON disclosure_notes (project_id, year, section_id);` + `CREATE INDEX IF NOT EXISTS ix_disclosure_notes_parent_section_id ON disclosure_notes (parent_section_id);`（约束表达式与索引列顺序以 `V019__add_note_section_id_columns.sql` 原文为准）。R179 内容：`DROP INDEX IF EXISTS ix_disclosure_notes_parent_section_id;` + `DROP INDEX IF EXISTS ix_disclosure_notes_project_year_section_id;` + `ALTER TABLE disclosure_notes DROP CONSTRAINT IF EXISTS ck_disclosure_notes_level_range;`（即 R019 的子集）。两个文件均用 fs_write 写入（含中文注释）。
      Files: `backend/migrations/V179__repair_v019_disclosure_notes_constraint_and_indexes.sql`（新建）、`backend/migrations/R179__rollback_repair_v019_disclosure_notes_constraint_and_indexes.sql`（新建）
      Verify: `d:\GT_plan\.venv\Scripts\python.exe -c "from app.core.migration_runner import MigrationRunner; from sqlalchemy.ext.asyncio import create_async_engine; r=MigrationRunner(engine=create_async_engine('sqlite+aiosqlite:///:memory:')); vs=[m.version for m in r.scan_migrations()]; assert '178' in vs and '179' in vs; print('178/179 OK, no dup')"`（cwd=`d:\GT_plan\backend`）—— scan 不抛 RuntimeError 且含 178 与 179。

- [ ] 4. 把 V178/V179 应用到真库（优先 MigrationRunner，确保 schema_version 行被写入）。
      运行 `d:\GT_plan\.venv\Scripts\python.exe -m app.core.migration_runner`（cwd=`d:\GT_plan\backend`）执行待应用迁移（会按 version 顺序只跑未应用的 178/179，并写 schema_version 行）。若因环境无法连库而改用 `docker exec audit-postgres psql ...` 直接执行 V178/V179 的 DDL，则随后必须手工确认 schema_version 里有 178/179 行（否则下次启动仍会把它们当待应用）。
      Files: 无（执行迁移）
      Verify:
      - schema_version 有新行：`docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT version, filename FROM schema_version WHERE version IN ('178','179') ORDER BY version;"` → 返回 178、179 两行。
      - 对象存在（逐对象核验）：
        - `docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT proname FROM pg_proc WHERE proname='admin_query_all_reports';"` → 1 行。
        - `docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT conname FROM pg_constraint WHERE conname='ck_disclosure_notes_level_range';"` → 1 行。
        - `docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('ix_disclosure_notes_project_year_section_id','ix_disclosure_notes_parent_section_id') ORDER BY indexname;"` → 2 行。

- [ ] 5. 在 `KNOWN_CHECKSUM_DRIFTS` 末尾追加全部 8 条 `KnownChecksumDrift(version, stored, current, resolution)`。
      - version 用 3 位字符串（`"005"`/`"006"`/`"010"`/`"016"`/`"017"`/`"019"`/`"051"`/`"057"`）。
      - stored 用全 64 位值，取自 findings.md「漂移清单（stored vs 磁盘 全值）」表，并先与真库核对一致：`docker exec audit-postgres psql -U postgres -d audit_platform -c "SELECT version, checksum FROM schema_version WHERE version IN ('005','006','010','016','017','019','051','057') ORDER BY version;"`（登记值必须等于真库 schema_version 的 checksum；**不得改写 schema_version**）。
      - current 用磁盘实算值，用与 runner 一致的算法从磁盘重算（而非照抄报告前缀）：`d:\GT_plan\.venv\Scripts\python.exe -c "import hashlib,pathlib; [print(v, hashlib.sha256(pathlib.Path('migrations')/next(p for p in __import__('os').listdir('migrations') if p.startswith('V'+v+'__')) and (pathlib.Path('migrations')/next(p for p in __import__('os').listdir('migrations') if p.startswith('V'+v+'__'))).read_text(encoding='utf-8').encode('utf-8')).hexdigest()) for v in ['005','006','010','016','017','019','051','057']]"`（cwd=`d:\GT_plan\backend`；若该一行脚本不便，改为逐版本 `read_text(encoding='utf-8')` 后 `sha256` 的小脚本）。更稳妥：直接用 `MigrationRunner(engine=create_async_engine('sqlite+aiosqlite:///:memory:')).scan_migrations()` 取各 version 的 `.checksum`，与守卫 fixture 完全同源。
      - resolution 用报告「登记到 migration_drift_ledger.py 的文案建议（全部 8 条）」表的中文文案（每条 ≥20 字）：V005 → 含「已由 V178 补齐」；V019 → 含「已由 V179 补齐」；其余 6 条（006/010/016/017/051/057）→ 对象在 public 全部存在，无需补迁移（照报告逐条文案）。
      Files: `backend/app/core/migration_drift_ledger.py`（仅在 `KNOWN_CHECKSUM_DRIFTS` 元组末尾追加 8 条，不改既有条目）
      Verify: `d:\GT_plan\.venv\Scripts\python.exe -c "from app.core.migration_drift_ledger import KNOWN_CHECKSUM_DRIFTS as K; vs=[k.version for k in K]; assert len(vs)==len(set(vs)); assert {'005','006','010','016','017','019','051','057'}.issubset(set(vs)); print(len(K),'entries, no dup')"`（cwd=`d:\GT_plan\backend`）—— 无重复 version 且 8 条都在。

- [ ] 6. 跑守卫测试，确认 ledger 登记逐字正确（current 等于磁盘实算、三元组自洽、无重复 version、每条 resolution ≥20 字）。
      运行 `rtk d:\GT_plan\.venv\Scripts\python.exe -m pytest backend/tests/test_migration_drift_ledger.py -v --tb=short`（cwd=`d:\GT_plan`）。若 `test_entry_current_matches_disk` 对某条红，说明该条 current 与磁盘实算不符 → 回步骤 5 用 scan_migrations 的值修正（不要反向改磁盘文件）。
      Files: 无（运行测试）
      Verify: 全部用例通过，包括 8 条新增的 `test_entry_current_matches_disk[V005..V057]` 与 `test_exact_triples_are_explained`。

- [ ] 7. 清理一次性调查脚本（保留 findings.md）。
      删除 `backend/scripts/analyze/_cd8_compute.py`、`_cd8_matchblob.py`、`_cd8_diff.py`、`_cd8_diff3.py`、`_cd8_verify.sql`，以及 `.agents/tasks/checksum-drift-8/_diffs.txt`；若容器 `/tmp` 有 `_cd8_verify.sql` 拷贝（`docker exec audit-postgres ls /tmp` 确认后）一并 `docker exec audit-postgres rm -f /tmp/_cd8_verify.sql`。findings.md 与本 plan.md 保留。
      Files: 删除上述 `_cd8_*` 脚本 + `_diffs.txt`
      Verify: `d:\GT_plan\.venv\Scripts\python.exe -c "import glob; print(glob.glob('backend/scripts/analyze/_cd8_*')); print(glob.glob('.agents/tasks/checksum-drift-8/_diffs.txt'))"`（cwd=`d:\GT_plan`）→ 两个列表均为空 `[]`。

## 收尾校验（可选，确认启动不再报这 8 条漂移）
补迁移跑完后，V005/V019 的 schema 缺口已消除，但 checksum 漂移本身仍在（文件被事后编辑是既成事实）——它们现已全部登记进 ledger，`detect_checksum_drift` 仍会检出 8 条但 `unexplained_checksum_drift` 返回空。启动日志的 WARNING 行为既有诊断机制输出，登记后属于"已解释"漂移，无需进一步消除。
