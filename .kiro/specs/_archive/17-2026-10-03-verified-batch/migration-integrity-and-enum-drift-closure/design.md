# 迁移完整性与枚举漂移收口 — 设计

> 需求：#[[file:.kiro/specs/migration-integrity-and-enum-drift-closure/requirements.md]]

## 一、V171 / R171（Requirement 1）

真库现状（2026-09-29 现查）：`confirmation_action_log` 两个触发器 `trg_conf_action_log_no_update/no_delete`
→ 专用函数 `trg_conf_action_log_forbid_update/delete()`（`RAISE EXCEPTION` 无 ERRCODE ⇒ P0001）；两表无表注释。
其余 8 张 evgov 表用 `evgov_forbid_update()`（V108：`check_violation`）/ `evgov_forbid_delete()`（V111：`restrict_violation`），
真库函数体与 V108 / V111 一致。

```sql
-- 钉回 V108 / V111 原文（新库按当前 V128 执行后，UPDATE 函数被写成 restrict_violation；这里把两条路径收敛）
CREATE OR REPLACE FUNCTION evgov_forbid_update() … USING ERRCODE = 'check_violation';
CREATE OR REPLACE FUNCTION evgov_forbid_delete() … USING ERRCODE = 'restrict_violation';
DROP TRIGGER IF EXISTS trg_conf_action_log_no_update ON confirmation_action_log;
DROP TRIGGER IF EXISTS trg_conf_action_log_no_delete ON confirmation_action_log;
DROP FUNCTION IF EXISTS trg_conf_action_log_forbid_update();
DROP FUNCTION IF EXISTS trg_conf_action_log_forbid_delete();
CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_update BEFORE UPDATE … evgov_forbid_update();
CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_delete BEFORE DELETE … evgov_forbid_delete();
COMMENT ON TABLE confirmation_attachment_link / confirmation_action_log IS …（与 V128 当前文本逐字一致）
```

- 函数名与触发器名冲突检查：`trg_conf_action_log_forbid_update` 在首版里是**函数名**，在改写版里是**触发器名**，二者命名空间不同，DROP FUNCTION 与 CREATE TRIGGER 互不影响。
- 顺序：先 DROP 旧触发器再 DROP 其函数（否则依赖报错）；`DROP FUNCTION IF EXISTS` 不加 CASCADE（有意：若还有别的依赖应当失败而不是连带删除）。
- 新库路径（按当前 V128）：V128 已建新触发器、无旧触发器 ⇒ V171 的 DROP 全部 no-op，CREATE OR REPLACE 幂等 ⇒ 两条路径终态一致。
- R171：只撤销 V171 自己引入、且回滚后不会让表失去保护的部分 —— 删新触发器前**先恢复**首版触发器与函数（回到真库原状），注释置 NULL。evgov 函数体不回退（回退会让新库路径变成 V128 当前版的 restrict_violation，属于放大错误）。

## 二、零语句迁移（Requirement 2）

`MigrationRunner._apply_migration`：

```python
statements = self._split_sql_statements(sql_content)
if not statements and not _declares_noop(sql_content):
    raise EmptyMigrationError(f"{mig.filename} 分句后没有可执行语句 …")
```

- `_declares_noop`：注释中出现 `no-op`（大小写不敏感）。V001 已含 `(no-op: existing schema baseline)`；R168 这类有意 no-op 用 `SELECT 1`，不受影响。
- 抛错走既有 `run_pending` 失败分支：记 `schema_migration_failures`、不写 `schema_version`、下次启动重试 ⇒ 文件补上内容后自动执行。
- `EmptyMigrationError(RuntimeError)` 定义在 migration_runner，便于测试精确断言。

## 三、checksum 漂移登记（Requirement 3）

新模块 `app/core/migration_drift_ledger.py`：

```python
@dataclass(frozen=True)
class KnownChecksumDrift:
    version: str; stored: str; current: str; resolution: str

KNOWN_CHECKSUM_DRIFTS: tuple[KnownChecksumDrift, ...] = (…7 条…)

def unexplained_checksum_drift(drifts) -> list[ChecksumDrift]:
    """实测漂移中，(version, stored, current) 三者不与某登记项逐字相等的。"""
```

- 登记结论（逐条来自现查）：V042 应用时为空文件 → V168 补回；V046/105/143/151/163 文件编辑后声明对象在 public 全部存在（逐对象核验）；V143 登记值 `manual` 为人工补登；V128 → V171 补齐。
- 比较三元组而不只比版本号：文件再被改（current 变）或有人改了 schema_version（stored 变）都会重新变成「未解释」。
- 接线：`SchemaDriftDetector.scan()` 追加 `_diff_checksums()`（复用 `MigrationRunner(engine=self._engine).detect_checksum_drift()`，不建新引擎），产出 `DriftItem(table=f"V{version}", column=None, drift_type="checksum_drift", detail=…)`。
- critical 类型单一真源：`schema_drift_detector.CRITICAL_DRIFT_TYPES = frozenset({"orm_extra", "enum_mismatch", "checksum_drift"})`；`health._query_schema_drift`、`startup_registry._task_run_schema_drift_check` 改为引用它。`main._run_schema_drift_check` 有并发会话在改，**本 spec 不动**（它与 startup_registry 同体，登记为已知残留，见 §七）。
- `DriftType` Literal 追加 `checksum_drift`；`schema_drift_log.drift_type` 是 VARCHAR（V026），无需迁移（实施前现查确认）。
- 扫描失败不 fail-open：`_diff_checksums` / `_diff_enums` 采集抛错时各返回一条可见的 critical 项（`(checksum_scan)` / `(enum_scan)`），health 会 degraded，而不是把「扫描坏了」当成「无漂移」。

### 三补、实施中新发现：过滤名单吞掉 ORM 表的 critical 漂移

`scan()` 原先对**全部**漂移类型套三张过滤名单（`KNOWN_ALLOWLIST` / 外部租户前缀 / 列级 allowlist）。外部租户前缀
`notification` 命中 ORM 表 `notifications` ⇒ 该表的 orm_extra / type_mismatch / enum_mismatch 全部被静默丢弃
（探针：320 张 ORM 表中恰 1 张被前缀命中）。三张名单描述的都是「DB 有、ORM 无」的对象，故改为 `_apply_suppressions`：
**只**作用于 `db_extra`，且外部租户前缀只作用于不在 ORM 里的表。现场复扫 `notifications` 当前 0 条（未掩盖真实缺口），
属潜伏漏洞。checksum 漂移的 table 是版本号（`V128`），在过滤之后追加。

## 四、枚举漂移（Requirement 4）

```python
@dataclass(frozen=True)
class OrmEnumColumn:
    table: str; column: str; type_name: str; labels: frozenset[str]

def collect_orm_enum_columns(metadata) -> list[OrmEnumColumn]  # native_enum=True 的 sa.Enum 列；labels = col.type.enums
def diff_enum_columns(orm_cols, db_columns, db_enums) -> list[DriftItem]  # 纯函数
```

- `db_columns`：`information_schema.columns WHERE table_schema='public'` 的 `(table, column) → (data_type, udt_name)`；`db_enums`：`pg_enum JOIN pg_type JOIN pg_namespace WHERE nspname='public'`。
- 判定：列不存在 → 跳过（由 orm_extra 负责）；`data_type != 'USER-DEFINED'` 或 `udt_name != type_name` → 「ORM 声明原生枚举 X，DB 列是 Y」；否则 `labels - db_enums[udt_name]` 非空 → 「DB 类型缺标签」。
- `DriftItem.table/column` 填真实表列（旧实现填类型名），health 展示可定位。
- 删除 `_camel_to_snake` 的 enum 用途（函数保留，现有单测仍在用）。

## 五、模型修复（Requirement 5）

- `GTWpCoding.wp_type`：`sa.Enum(GTWpType, name="gt_wp_type", native_enum=False, create_constraint=False, length=50)`。`native_enum=False` 时绑定为 VARCHAR，读出仍转成 `GTWpType`，`_to_dict` 的 `.value` 分支不变。
- `WorkpaperReviewRecord.review_status`：`Enum(ReviewStatus, name="review_status_enum")`。`ReviewStatus` 在同文件第 49 行，已被 `risk_assessments.review_status` 共用。零调用方，无行为迁移。

## 六、测试

| 测试 | 层级 | 覆盖 |
|------|------|------|
| `test_migration_integrity_pg.py` | 真库 | 回滚事务内：`confirmation_action_log` UPDATE→23514 / DELETE→23001（报文含表名）；每条 evgov 绑定与事件匹配 + 临时表实测两个共享函数的拒绝码（空表的 evgov 表由此推出）+ 有数据的 evgov 表逐表实测；函数体钉回 V108/V111；两表注释与 V171 逐字一致；未解释漂移为 0 且比较确实发生；现场枚举漂移为 0；`GTWpCoding` 插入/查询、`review_status=pending_review` 插入读回；反向对照（原生 `gt_wp_type` 绑定 42704、`pending` 写共享枚举 22P02、他 schema 同名类型不并入 public 标签）；结束复查零残留 |
| `test_migration_runner.py`（**实施调整**：并入既有文件，未新建 `_empty_guard`） | SQLite | 纯注释 / 空白 / 空文件 3 种被拒且未登记、补内容后成功；`no-op` 声明放行；真实 V001 仍声明 no-op |
| `test_migration_drift_ledger.py` | 离线 | 登记项 current 与磁盘实算（runner 同一算法）一致；三元组任一不同即未解释；无重复版本；V042 登记值 = sha256 空串 |
| `test_enum_drift_columns.py` | 离线 | 三处旧缺陷各一例 + 两个误报样本不报 + 两个真缺口同形样本；真实 metadata：同一 PG 类型的列标签一致、`gt_wp_coding` 按 varchar 绑定 |
| `test_schema_drift_detector.py`（追加） | 离线 | 过滤只作用于 db_extra（§三补）；checksum 只报未解释项、扫描失败可见；critical 单一真源（AST 判定 health / startup_registry 无类型字面量）；`main.py` 残留以 `xfail(strict=True)` 钉住；scan 接线五类来源 |
| `test_properties_pbt.py` 两个 xfail 占位 | — | 删除（改由真库用例覆盖），避免 `xfail + assert False` 恒「预期失败」的假绿 |

真库用例要求**已迁移的现场库**（本机开发库）；非 PostgreSQL 直接失败不 skip。CI 的空库仅靠迁移建 schema，而 V001 是
no-op 基线、`users` / `projects` / 两张模型表不由迁移创建 —— 该用例在那里会以「现场库缺表 [...]」的采集错误报红
（开头先查表是否存在，给出明确原因而不是散落的 KeyError），属既有 CI 环境欠账，如实登记不改成 skip。

变异（`_mig_mutation_check.py`，一次性，12 条）：G1 去掉空语句拒绝 / G2 登记比较只看版本 / G3 枚举期望标签改 `.value` /
G4 标签查询去 schema 限定 / G5、G6 回退两处模型修复 / G7 过滤作用于全部类型 / G12 外部租户前缀作用于 ORM 表 /
G8 health 手写二元集合 / G9 checksum 扫描失败 fail-open / G10 不经登记表 / G11 scan 不接 checksum。

## 七、范围外（显式登记）

- `main._run_schema_drift_check` 与 `startup_registry` 同体重复：main.py 有并发会话未提交改动，本 spec 不触碰；它仍按旧二元集合判 critical，只影响启动日志措辞，不影响 health（health 读 `schema_drift_log` + 单一真源集合）。已用 `xfail(strict=True)` 钉住：修掉后 XPASS 即红，提示删标记。
  - 现查：真实启动路径是 `main.lifespan → _run_schema_drift_check`；`startup_registry` 未接入 main（`test_startup_registry.py` 的 `test_health_includes_startup_report` / `test_main_reexports_start_workers` 预存红即此，改动文件换回 HEAD 复跑同样 2 红）。
- `test_zero_downtime_migration_compat::test_property9_vr_pairing_complete` 预存红（41 个 V060+ 无 R 文件）：属历史欠账，本 spec 新增的 V171 自带 R171，不扩大欠账。
- 7 个 `tmp_*` 残留 schema：属测试夹具泄漏，归环境卫生处理。
