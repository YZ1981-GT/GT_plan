# 设计文档：高级查询查询证据与时效（advanced-query-artifact-and-freshness）

需求见 [requirements.md](requirements.md)。本文锚点用函数名、端点字面量与常量名，不写行号。

## §0 现状确认（2026-11-04；候选树 `204f58c61` = 远端分支头 v1.0.105；共享库只读查询与回滚事务探针）

### 0.1 执行与导出链路

| 环节 | 现状 | 本 spec 接入点 |
|---|---|---|
| 业务视图执行 | `routers/custom_query.execute_query`（`POST /api/custom-query/execute`）→ `ExecuteCompatibilityAdapter.execute` → `QueryOrchestrator.execute`：step1 归属 → step2 目标解析 → step3 缓存（键 = `cache_def()` + 项目 + `_scope_signature()`，TTL 30 秒）→ step4 `business_fetcher` → `paged_fetch.page` / `all_rows`（`_page_meta` 给 `ref_context` / `column_types` / `entry_accounts`） | step3 之前采集版本向量；缓存键追加版本摘要；路由层登记运行 |
| 模板执行 | `execute_template` 解析模板（`config_to_request`）后调用 `execute_query` | 传 `origin=template` |
| 构建器执行 | `routers/query_builder.execute_query`（`POST /api/query/execute`）：`_builder_scope` → `plan_builder_targets` → `_build_select` → `compute_cache_key(project_id="__query_builder__:{scope_signature}")` → COUNT 凭证主体 `{subject_of(user)}:{scope_signature}` | 缓存键与凭证主体追加版本摘要；登记运行 |
| 业务视图导出 | `export_query`（`POST /api/custom-query/export`）→ `query_export._business_export` → `respond_xlsx` → `export_service.stream_xlsx`（`tempfile.mkstemp` 写完后逐块 yield，`finally` 删文件） | 写进证据目录、封存后再流式返回 |
| 构建器导出 | `export_excel`（`POST /api/query/export-excel`）→ `query_export.export_builder_query` → 同上 | 同上 |
| 导出审计 | `audit_helper.record_export`：entry / source / year / row_count / columns | 增加证据编号、清单摘要、运行编号、版本摘要 |
| 事务 | `core/database.get_db` 只开会话、不提交；编排层只读 | 路由提交（§5.3） |

### 0.2 历史与版本信号

- 服务端没有运行记录与证据：`git grep -E "query_run|QueryRun|query_artifact|QueryArtifact" -- backend/app backend/migrations` 0 命中。
- 历史只有弹窗有：`QUERY_HISTORY_KEY = 'gt:cq:history'`，`pushQueryHistory` 存项目 / 年度 / 源 / 本页筛选文字 / 选区，最多 10 条；页面版与构建器没有历史。
- 四表是 B' 架构：可见性只由 `ledger_datasets.status` 决定（`DatasetService._set_dataset_visibility` 已是空操作），数据集内的行不改写 ⇒ 生效数据集编号是强信号。共享库 `tb_ledger` 共 6,971,441 行，只能靠数据集编号。
- `updated_at` 只由 ORM `onupdate` 维护（`models/base.py`），裸 SQL 不经过它。AST 口径（字符串常量含 `UPDATE <表>`、排除 docstring）不写 `updated_at` 的执行语句：试算表 4 处（`n1`~`n4` 四个税费服务改 `audited_amount`）、底稿 10 处、报表 1 处、附注 1 处 ⇒ 不能用 `max(updated_at)` 当版本。
- 报表运行记录 `financial_report.run_id` 在 v1.0.107 之前写不进去（§12.1）；修复后也只有之后生成的行带 `run_id`，报表版本仍不依赖它。
- 附注指标树已有 `X-Notes-Version`（`resolve_notes_context`：行数 + `max(updated_at)` + 循环章节），口径同样受裸 SQL 影响；本 spec 不改它，只在 §12 登记。

### 0.3 实测：分量摘要的成本（共享库，各表最大作用域，5 次的中位数 / 最大值，两次结果一致）

| 表（作用域） | 行数 | 行版本 `id:xmin` | 内容摘要（去时间戳） |
|---|---|---|---|
| trial_balance（项目年度） | 196 | 1.45 / 3.17 ms | 3.52 / 5.91 ms |
| financial_report（项目年度） | 352 | 1.11 / 2.21 ms | 4.54 / 5.97 ms |
| report_config（单准则） | 352 | 1.34 / 2.29 ms | 7.07 / 7.65 ms |
| adjustments（项目年度） | 10 | 1.07 / 2.31 ms | 1.06 / 2.45 ms |
| wp_index（项目） | 1,026 | 1.93 / 3.17 ms | 9.20 / 10.93 ms |
| disclosure_notes（项目年度） | 199 | 1.57 / 2.61 ms | 47.63 / 55.42 ms |
| working_paper（项目） | 1,026 | 1.79 / 3.04 ms | 18.50 / 26.85 ms |
| consol_note_data（项目年度） | 3,514 | 4.00 / 6.82 ms | 85.52 / 90.36 ms |

结论：小型取值表用内容摘要（≤ 11 ms，且「重写了但值没变」不算变化）；含大 JSON 列的表用行版本（≤ 7 ms）。探针在 `tmp_aq_phase0/probes/`（`p1_rowversion_cost.py`、`p1_content_digest_cost.py`，一次性，交付后清理）。

### 0.4 复用与不复用

| 现有能力 | 处理 |
|---|---|
| `asset_blobs`（V241 不可变字节） | 不复用：`AssetBlobService.register_bytes` 要把整个文件读进内存（导出最多 100 万行），可信根只含附件与知识库目录；晋升为附件属 Phase 2（§11） |
| `consol_artifact`（V246） | 沿用其做法：ready 必备字段约束、下载前重验大小与 SHA-256 |
| `workers/export_cleanup_worker`（启动跑一次 + 每小时，主副本锁 `try_acquire_leadership`） | 接入证据与运行记录清理 |
| `builder_scope.resolve_builder_scope` / `scope_predicates` / `scope_signature`、`builder_access.resolve_builder_access`、`ownership_guard`、`cycle_scope.CycleScopeCache`、`count_token` | 原样复用 |
| `attachment_upload_policy.ensure_within_root` | 证据路径校验 |
| `execution_guard.cancellable_query` | 分量采集的语句超时 |
| 前端 `utils/formatters` 的 `fmtDateTime` / `parseServerTime`；`utils/http.downloadFile`（返回响应，可读响应头） | 原样复用 |

### 0.5 行数（`len(text.split("\n"))`，与行数门同口径）

| 文件 | 现行数 | 上限 | 本 spec 预算 |
|---|---|---|---|
| backend/app/routers/custom_query.py | 1990 | 白名单 1911 × 1.05 = 2006 | 执行主体移出，净减 |
| backend/app/services/custom_query/query_orchestrator.py | 743 | 800 | +30 以内 |
| backend/app/routers/query_builder.py | 494 | 800 | +40 以内 |
| backend/app/services/custom_query/query_export.py | 379 | 800 | +60 以内 |
| backend/app/services/custom_query/export_service.py | 608 | 800 | +40 以内 |
| audit-platform/frontend/src/components/query/CustomQueryDialog.vue | 1431 | 1500 | 净增 ≤ 0 |
| audit-platform/frontend/src/components/template-library/CustomQueryTab.vue | 1012 | 1500 | +50 以内 |
| audit-platform/frontend/src/views/AdvancedQueryBuilder.vue | 1149 | 1500 | +50 以内 |

### 0.6 迁移号

**更新（2026-11-07）**：磁盘最高 V267（255 个 V 文件、202 个 R 文件，`check_migration_versions` exit 0）；共享库 `schema_version` 最高 V267（任务 1 证据：V267 已由迁移器应用）；远端分支 `spec/disclosure-note-doc-upload-and-batch-fill` HEAD 最高 V267（2026-11-06 任务 1 推送）。三处一致，本 spec 新迁移取 V267。旧记（2026-11-04 扫描时）为 V251，已由任务 1 现取 V267。

## §1 总体流程

```
execute（业务视图 / 模板 / 构建器）
  鉴权、解析（不变）
  → 采集版本向量（新；取数之前；每个分量一个 SAVEPOINT）
  → 缓存键、COUNT 凭证主体追加版本摘要（改）
  → 取数、分组、透视、分页（不变）
  → 登记运行记录（新；同一会话 SAVEPOINT，路由提交）
  → 响应追加 run 键（新）

export（业务视图 / 构建器）
  鉴权、解析、行数预检、导出名额（不变）
  → 采集版本向量（新）
  → 登记运行记录（新；独立短事务，先拿到运行编号，供说明页使用）
  → 在证据目录写 .partial 文件（export_service.build_xlsx_file）
  → 封存：流式 SHA-256、原子改名、组清单；独立短事务写证据记录并提交
  → 从证据文件流式返回（不删除）
  失败降级：改走现有路径（临时文件、发完即删），响应头 X-Query-Artifact-Status: unavailable
```

## §2 设计决策（ADR）

**ADR-AQF-01 运行身份 = (用户, 入口, 定义摘要, 版本摘要)；身份不可变，计数可变。**
- 不采用「每次执行一行」：按每人每天 50 次、6,000 人估算约 30 万行 / 天，历史与清理都扛不住。
- 不采用「每个定义一行、版本覆盖更新」：屏上结果、证据和运行记录就不再对应同一版数据，过期判定会拿新版本去比。
- 代价：数据每变一次，同一定义再执行就多一行；由 R8.3 的保留规则（每人 500 条）约束总量。

**ADR-AQF-02 分量依据按表选择（数据集 / 内容摘要 / 行版本 / 范围），不用 `max(updated_at)` 作主依据。**
- `max(updated_at)`：§0.2 的裸 SQL 改写不写它，会把已变化判成未变化，违背 R2.1 的方向。只在超限退化时使用，并标为弱判据。
- 对查询结果全集算摘要：判定时要重跑全量，成本随结果规模增长（序时账可达百万行）。不采用。
- 内容摘要：`to_jsonb(行) - 'created_at' - 'updated_at'` 自动覆盖所有列，值没变的重写不算变化。迁移给表加列后，该表所有分量会变化一次（可接受，界面原因显示「内容变化」）。
- 行版本 `xmin`：任何物理改写都会让它变化，包括值没变的 UPDATE、`pg_repack` 重写表、从备份恢复，所以只会多报、不会漏报。表维护（`VACUUM FULL`、`CLUSTER`）是否改变 `xmin` 不作依赖：即使改变，也只会多报一次。同一事务（或同一 SAVEPOINT）内多次改写同一行时 `xmin` 不变，不影响跨请求比较；测试须把改写放进新的 SAVEPOINT。`xmin` 回卷让两次不同改写恰好得到同一 `xmin` 需要约 40 亿个事务，记为已知限制、不处理。
- 数据集：B' 架构下数据集内的行不改写；切换、回滚数据集都会换编号。

**ADR-AQF-03 采集先于取数；版本摘要进缓存键与 COUNT 凭证。**
- 先于取数 ⇒ current 不会是假的（R2.1）。
- 进缓存键 ⇒ 缓存命中时屏上结果与版本向量必然对应，同时消除「写入后 30 秒内仍返回旧结果」。
- 进 COUNT 凭证主体 ⇒ 写入后翻页会重算总数。
- 代价：每次执行多 1~3 条分量查询（§0.3 每条 ≤ 11 ms），缓存命中时也要采集。

**ADR-AQF-04 证据文件自管存储，不进 `asset_blobs`（理由见 §0.4）。** 路径 `{root}/{yyyy}/{mm}/{artifact_id}.xlsx`；先在同目录写 `.{artifact_id}.partial`，写成后 `os.replace` 改名；文件不覆盖、不改写。

**ADR-AQF-05 执行时的登记用请求会话 SAVEPOINT + 路由提交；导出时的登记与封存用独立短事务。**
- 执行频率高：独立会话会让每次执行多占一个连接（目标并发 6,000）。
- 导出要在开始流式发送之前把证据提交（发送可能持续数分钟、客户端可能中途断开），导出频率又低（本人 1 个、进程 4 个名额）。
- 独立会话工厂可注入；真 PG 测试注入回滚连接，避免写进共享库。
- 登记失败时：执行返回 `recorded = false`，导出返回 `unavailable`，都不让查询或导出失败。

**ADR-AQF-06 证据保存失败不阻断导出。** 现状本来就没有证据；保存成功才回 `stored`。

**ADR-AQF-07 历史按定义去重显示；移除只隐藏不删除；证据数按定义统计。** 同一定义在不同版本数据上的多次执行只显示最近一次；隐藏的运行仍可经证据追溯。

**ADR-AQF-08 只对创建者可见，读时重验访问；非创建者一律 404。** Phase 2 引入项目内共享（复核、归档）时另行设计，不在本 spec 预开口子。

**ADR-AQF-09 上限与弱判据。** 内容摘要上限 50,000 行、行版本上限 200,000 行，超限逐级退化；退化后的分量标弱判据，界面写明（R3.4）。项目级作用域直接算摘要（同一语句带行数）；跨项目作用域与四表退化先 COUNT 再选依据。

**ADR-AQF-10 前端三个宿主共用一个信息条组件、一个抽屉组件、一个组合式函数。** 后端给结构化字段（UTC 时间、行数、依据），前端统一格式化，避免三处各写一套文案。

## §3 数据模型

迁移 `V{n}__query_runs_and_artifacts.sql` / `R{n}__rollback_query_runs_and_artifacts.sql`（号见 §0.6）；ORM 在 `backend/app/models/query_evidence_models.py`（`QueryRun`、`QueryArtifact`，`Mapped[]`），并加入模型导入，使 schema 漂移检测纳入。

```sql
CREATE TABLE IF NOT EXISTS query_runs (
    id                UUID PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    entry             VARCHAR(16) NOT NULL,            -- business / builder
    origin            VARCHAR(16) NOT NULL DEFAULT 'direct',  -- direct / template
    template_id       UUID NULL,                       -- 不加外键：模板软删后仍保留编号
    project_id        UUID NULL REFERENCES projects(id) ON DELETE CASCADE,  -- 构建器跨项目时为空
    year              INTEGER NULL,
    source_key        VARCHAR(200) NOT NULL,           -- 业务视图源键 / 构建器基表
    definition        JSONB NOT NULL,
    definition_hash   CHAR(64) NOT NULL,
    definition_version SMALLINT NOT NULL DEFAULT 1,
    scope             JSONB NOT NULL DEFAULT '{}'::jsonb,
    labels            JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 项目名、数据源名（登记时取）
    version_vector    JSONB NOT NULL,
    vector_hash       CHAR(64) NOT NULL,
    vector_weak       BOOLEAN NOT NULL DEFAULT false,
    captured_at       TIMESTAMPTZ NOT NULL,
    execution_count   INTEGER NOT NULL DEFAULT 1,
    first_executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_executed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_total        BIGINT NULL,
    last_warnings     JSONB NOT NULL DEFAULT '[]'::jsonb,
    hidden_at         TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_query_runs_identity UNIQUE (user_id, entry, definition_hash, vector_hash),
    CONSTRAINT ck_query_runs_entry CHECK (entry IN ('business', 'builder')),
    CONSTRAINT ck_query_runs_origin CHECK (origin IN ('direct', 'template')),
    CONSTRAINT ck_query_runs_hashes CHECK (definition_hash ~ '^[0-9a-f]{64}$' AND vector_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_query_runs_count CHECK (execution_count >= 1)
);
CREATE INDEX IF NOT EXISTS ix_query_runs_history ON query_runs (user_id, entry, last_executed_at DESC) WHERE hidden_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_query_runs_definition ON query_runs (user_id, definition_hash, last_executed_at DESC);
CREATE INDEX IF NOT EXISTS ix_query_runs_project ON query_runs (project_id);

CREATE TABLE IF NOT EXISTS query_artifacts (
    id               UUID PRIMARY KEY,
    run_id           UUID NULL REFERENCES query_runs(id) ON DELETE SET NULL,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    entry            VARCHAR(16) NOT NULL,
    project_id       UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    year             INTEGER NULL,
    source_key       VARCHAR(200) NOT NULL,
    definition_hash  CHAR(64) NOT NULL,
    version_vector   JSONB NOT NULL,
    vector_hash      CHAR(64) NOT NULL,
    scope            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           VARCHAR(16) NOT NULL DEFAULT 'ready',   -- ready / purged
    file_name        VARCHAR(255) NOT NULL,
    storage_key      TEXT NOT NULL,                  -- 相对证据根目录的路径
    media_type       VARCHAR(120) NOT NULL,
    byte_size        BIGINT NOT NULL,
    sha256           CHAR(64) NOT NULL,
    row_count        BIGINT NOT NULL,
    columns          JSONB NOT NULL,
    manifest         JSONB NOT NULL,
    manifest_sha256  CHAR(64) NOT NULL,
    retention_until  TIMESTAMPTZ NOT NULL,
    purged_at        TIMESTAMPTZ NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_query_artifacts_storage UNIQUE (storage_key),
    CONSTRAINT ck_query_artifacts_entry CHECK (entry IN ('business', 'builder')),
    CONSTRAINT ck_query_artifacts_status CHECK (status IN ('ready', 'purged')),
    CONSTRAINT ck_query_artifacts_purged CHECK ((status = 'purged') = (purged_at IS NOT NULL)),
    CONSTRAINT ck_query_artifacts_hashes CHECK (sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_query_artifacts_sizes CHECK (byte_size >= 0 AND row_count >= 0)
);
CREATE INDEX IF NOT EXISTS ix_query_artifacts_user ON query_artifacts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_query_artifacts_expiry ON query_artifacts (retention_until) WHERE status = 'ready';
CREATE INDEX IF NOT EXISTS ix_query_artifacts_run ON query_artifacts (run_id);
CREATE INDEX IF NOT EXISTS ix_query_artifacts_definition ON query_artifacts (user_id, definition_hash);
```

不可变触发器（PL/pgSQL，`BEFORE UPDATE`，写法同 V241 的 `gt_asset_blob_immutable`）：
- `query_runs`：身份字段（`user_id`、`entry`、`origin`、`template_id`、`project_id`、`year`、`source_key`、`definition`、`definition_hash`、`definition_version`、`scope`、`labels`、`version_vector`、`vector_hash`、`vector_weak`、`captured_at`、`first_executed_at`、`created_at`）任一 `IS DISTINCT FROM` 即抛错；其余字段可改。
- `query_artifacts`：除 `status`、`purged_at`、`updated_at`、`run_id` 外全部不可改；`status` 只允许 `ready → purged`；`run_id` 只允许改为 NULL（运行被清理时外键 `SET NULL` 触发的更新）。
- R 文件：删两个触发器与函数，再删两表（先 `query_artifacts`）。SQLite 单测按 ORM 建表，没有触发器；触发器只在真 PG 用例验证（P9）。

外键说明：平台只软删项目（`backend/app` 内没有删除 `projects` 行的语句），`ON DELETE CASCADE` 只是不阻塞手工运维删除；软删项目的记录由 R7.2 的访问重验挡住。

## §4 版本向量

### 4.1 结构（`backend/app/services/custom_query/version_capture.py`）

```python
@dataclass(frozen=True)
class VersionComponent:
    key: str                  # f"{table}|{规范化 scope}"，向量内唯一
    table: str
    label: str                # 中文名（如「试算平衡表」「账套数据集」），随响应返回，前端不另维护映射
    basis: Literal["dataset", "content", "row_version", "timestamp", "scope"]
    scope: dict               # 采集范围参数：project_id / year / standard / projects（项目集合或 "all"）
    rows: int | None
    digest: str | None        # 内容或行版本摘要、数据集编号、范围摘要
    latest_update: str | None # 只作说明，不进摘要、不参与比较
    dataset: dict | None      # {"id", "activated_at"}
    weak: bool                # basis == "timestamp"
    error: str | None         # 采集失败的中文原因
```

`vector_hash = sha256(规范 JSON([[c.key, c.basis, c.rows, c.digest, c.error is not None] for c in 按 key 排序]))`。规范 JSON：键排序、`ensure_ascii=False`、`separators=(",", ":")`，与 §5.1 的定义摘要同一函数。

### 4.2 采集语句（PostgreSQL）

| 依据 | 语句（`{scope}` 为范围谓词） |
|---|---|
| content | `SELECT count(*), md5(string_agg(md5((to_jsonb(t) - 'created_at' - 'updated_at')::text), '' ORDER BY t.id)), max(t.updated_at) FROM {table} t WHERE {scope}` |
| row_version | `SELECT count(*), md5(string_agg(t.id::text \|\| ':' \|\| t.xmin::text, ',' ORDER BY t.id)), max(t.updated_at) FROM {table} t WHERE {scope}` |
| timestamp | `SELECT count(*), max(t.updated_at) FROM {table} t WHERE {scope}` |
| dataset（单项目） | `SELECT id, activated_at FROM ledger_datasets WHERE project_id = :p AND year = :y AND status = 'active' ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1` |
| dataset（构建器多项目） | 同条件按项目集合（与年度）取每个项目年度最新一条，`md5(string_agg(project_id \|\| ':' \|\| year \|\| ':' \|\| id, ',' ORDER BY project_id, year))` |
| scope | 不查库：业务视图取 `CycleScopeCache.cycles(project)`（与 `_scope_signature` 同源）；构建器取 `scope_signature(scope)` + 角色 + `excluded_cycle_scoped` + `unscoped_tables` |

- 表名与列名只来自登记表常量，不来自请求；范围值一律绑定参数。
- 每个分量在 `db.begin_nested()` 内、`cancellable_query(db, 2_000)` 下执行；失败只回滚该 SAVEPOINT，`error` 记中文原因（如「采集超时」「来源表不存在」）。
- 上限（ADR-AQF-09）：content 行数 > 50,000 改 row_version；row_version > 200,000 改 timestamp（`weak = true`）。
- SQLite（只用于接线单测）：没有 `xmin`、`to_jsonb`，content 与 row_version 都用 Python 侧行内容摘要实现；依据语义只在真 PG 用例验证。

### 4.3 登记表（`backend/app/services/custom_query/version_registry.py`）

业务视图按 `source_registry.resolve_source` 的解析结果登记（SQL 源按 `spec.key`，内存源按取数器）：

| 源（含别名与前缀形态） | 分量：表 / 依据 / 范围 |
|---|---|
| trial_balance（含 tb_detail、`consol_unit:*:tb_detail`） | trial_balance / content / 项目 + 年度 |
| account_balance、ledger_entries、aux_balance、aux_ledger（含 `consol_unit` 对应类型） | ledger_datasets / dataset / 项目 + 年度；没有生效数据集时改为对应 `tb_*` 表 / row_version / 项目 + 年度 |
| workpaper（含 `workpaper:{编码}[\|sheet]` 清单形态） | working_paper / row_version / 项目；wp_index / content / 项目 |
| workhours | work_hours / content / 项目 + 年度（按 `work_date`） |
| report、`report_{类型}` | financial_report / content / 项目 + 年度；report_config / content / 本次解析出的准则 ∪ 本项目副本行 |
| report_lines | report_config / content / 全部非项目副本行 ∪ 本项目副本行 |
| adjustment、adj_aje、adj_rje（含 adj_rcl、`consol_unit:*:adjustment`） | adjustments / content / 项目 + 年度 |
| tb_summary、worksheet、`ws_*` | consol_worksheet_data / row_version / 项目 + 年度 |
| disclosure、`disclosure_note:{章节}` | disclosure_notes / row_version / 项目 + 年度；合并项目另加 consol_note_data / row_version / 项目 + 年度 |
| 底稿选区（`workpaper:` 带 `cell_range`、`workpaper` + `wp_code` + `cell_range`） | working_paper / row_version / 项目 |
| 任意源带 `acnr_targets` | 追加 working_paper / row_version / 项目 |
| 全部业务视图 | scope / 本人循环范围 |

合并单位（`company_code`）不缩小分量范围，按项目级采集（宁可多报）。

构建器按 `TABLE_WHITELIST` 逐表登记（基表与每个 JOIN 目标各一个分量；现算 18 张）：

| 依据 | 表 |
|---|---|
| dataset | tb_balance、tb_ledger、tb_aux_balance、tb_aux_ledger（即 `DATASET_SCOPED_TABLES`） |
| content | trial_balance、adjustments、unadjusted_misstatements、report_line_mapping、report_config、wp_index、financial_report、account_chart、materiality、staff_members、work_hours |
| row_version | working_paper、disclosure_notes、projects |

构建器分量的范围谓词 = `builder_scope.scope_predicates(table, scope, year=body.year)`（与查询同一谓词）；分量 `scope` 里记项目集合（admin / partner 全项目记 `"all"`）与年度。另加一个 scope 分量。

守卫（任务 2）：遍历 `SOURCE_REGISTRY`、`SOURCE_ALIASES`、`JSON_SOURCES`、`JSON_PREFIXES`、`WORKPAPER_CELLS`、`CONSOL_UNIT_KINDS`、`REPORT_TYPES` 前缀与 `TABLE_WHITELIST`，每一项都必须解析到至少一个分量；含 JSONB 大列的表（working_paper、disclosure_notes、consol_note_data、consol_worksheet_data、projects）不得登记为 content。

### 4.4 采集时机

| 入口 | 位置 |
|---|---|
| 业务视图执行 | `QueryOrchestrator.execute`：step3 里 `_scope_signature`（建好 `CycleScopeCache`）之后、计算缓存键之前。结果写入 `req.version_hash`（不进 `cache_def()`）与 `QueryResult.version`（不进 `to_payload()`，缓存命中时用本次采集的向量）；`scope_sig` 追加 `\|v={vector_hash}`。`ExecuteCompatibilityAdapter.execute` 改为同时返回响应与向量 |
| 构建器执行 | `_build_select` 之后、`get_cached_result` 之前 |
| 业务视图导出 | `prepare_export` 之后、`acquire_export_slot` 之前 |
| 构建器导出 | `_build_select(for_export=True)` 之后、取导出名额之前 |

采集器以构造参数注入编排器（默认实现即生产采集器），单测可替换；真 PG 用例必须走生产采集器。

### 4.5 比较与原因（`backend/app/services/custom_query/version_compare.py`）

判定按记录里的分量 `scope` 重新采集，不重新解析数据源（数据源下线也能判定）；报表准则在判定时重新解析一次，与记录比较（R2.7）。

| 情形 | 分量结论 | 原因文案 |
|---|---|---|
| 摘要相同 | 一致 | — |
| 数据集编号不同 | 变化 | 生效数据集已切换（原激活于 {t1}，现激活于 {t2}） |
| 原有生效数据集、现在没有 / 原来没有、现在有 | 变化 | 生效数据集已失效 / 已导入生效数据集 |
| 摘要不同、行数不同 | 变化 | {表名}行数 {a} → {b} |
| 摘要不同、行数相同 | 变化 | {表名}有行被修改（最近更新 {t}） |
| 准则不同 | 变化 | 报表准则由 {x} 变为 {y} |
| 范围分量不同 | 变化 | 您的审计循环范围已变化 / 查询作用域已变化 |
| 本次采集失败 | 无法判定 | {原因} |
| 当初采集就失败 | 无法判定 | 查询时该来源的版本未能采集 |

汇总：任一分量变化 → stale；否则任一无法判定 → unknown；否则 current；`weak` = 任一分量依据为 timestamp。原因文案里的表名取分量的 `label`（试算平衡表、报表、报表配置、调整分录、底稿、底稿索引、附注、合并附注、合并工作底稿、工时、账套数据集等），只在后端 `version_registry.py` 维护一份。

### 4.6 COUNT 凭证绑定

- 业务视图：`FetchContext` 新增 `version_hash`（`business_fetchers._sql_context` 从 `req.version_hash` 取）；`paged_fetch._count_page` 的主体由 `subject_of(user)` 改为 `subject_of(user) + "|v=" + version_hash`（无向量时不追加）。
- 构建器：`count_subject = f"{subject_of(user)}:{scope_signature(scope)}:v={vector_hash}"`。
- 凭证格式与 TTL 不变；上线后旧凭证自然失效一次（多算一次 COUNT）。

## §5 运行记录（`backend/app/services/custom_query/query_runs.py`）

### 5.1 定义规范化

- 业务视图：`QueryRequest.model_dump(mode="json", exclude={"limit", "offset", "count_token"})`；导出请求（`QueryExportRequest`）先丢掉 `headers` / `file_name` 再按同一规则处理。
- 构建器：`QueryDSL.model_dump(mode="json", exclude={"limit", "offset", "count_token"})`；`ExportDSL` 同样丢掉 `headers` / `file_name`。
- 规范化：字典键排序；UUID 统一小写；列表保序（条件、列、排序、JOIN 的顺序有语义）；`definition_version = 1`。摘要 = SHA-256（规范 JSON，§4.1 同一函数）。
- 模板执行：用 `config_to_request` 之后真正执行的那个 `QueryRequest`；`origin = template`、`template_id` 记模板编号。
- 显示标签（`labels`）登记时由服务端生成：项目名（`projects.name`）、数据源名（SQL 源取 `SourceSpec.label`；内存源按取数器给固定中文名；构建器取 `TABLE_WHITELIST[table]["label"]` 与 JOIN 表名）。

### 5.2 登记语句（PostgreSQL）

```sql
INSERT INTO query_runs (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uq_query_runs_identity DO UPDATE
   SET execution_count  = query_runs.execution_count + 1,
       last_executed_at = now(),
       last_total       = EXCLUDED.last_total,
       last_warnings    = EXCLUDED.last_warnings,
       hidden_at        = NULL,
       updated_at       = now()
 WHERE query_runs.last_executed_at < now() - interval '60 seconds'
    OR query_runs.hidden_at IS NOT NULL
RETURNING id, execution_count, last_executed_at
```

没有返回行（60 秒内重复执行）时按身份再 `SELECT` 一次取编号。SQLite 单测用 `INSERT OR IGNORE` + 同条件 `UPDATE`。

### 5.3 接线

- `routers/custom_query.execute_query` 的主体移到 `services/custom_query/business_execute.execute_business_query(body, response, db, user, *, origin=None)`；路由函数名与签名不变（契约测试直接调用它）。`execute_template` 调同一个服务函数并传 `origin=("template", 模板编号)`。抽取前按任务 0 的清单保留测试里的 monkeypatch 点。

**任务 0 monkeypatch 补丁点清单（2026-11-07 现算，抽取时必须保留）**

| 补丁点 | 文件 | 说明 |
|---|---|---|
| `app.services.custom_query.query_orchestrator.read_acnr_target_values` | `tests/test_advanced_query_hardening_wave012.py:713` | 编排器内部 ACNR 钩子，抽取时保持字符串路径不变 |
| `app.services.custom_query.query_export.acquire_export_slot` | `tests/advanced_query_linkage/test_aql_export_pg.py:169` | 导出名额守卫 spy |
| `ExecuteCompatibilityAdapter.execute`（类方法级） | `tests/test_advanced_query_ddl_cross_lock.py:285` | 适配器执行替换（DDR 锁测试），适配器类本身不能改名 |
| `ExecuteCompatibilityAdapter.execute`（类方法级） | `tests/test_advanced_query_hardening_properties_scope.py:177/193` | 范围属性测试临时替换，同上 |
| `app.services.custom_query.ownership_guard.set_rls_context` | `tests/advanced_query_linkage/test_aqs_safety_closure.py:70` | RLS 上下文捕获，权限闭环测试 |
- 服务函数顺序：编排器执行 → `query_runs.record(...)`（`db.begin_nested()` 内）→ `await db.commit()` → 响应加 `run` 键。登记出错只回滚 SAVEPOINT，`run = {"recorded": false, "reason": ...}`。
- 构建器：读写缓存之后、成功审计之前登记并提交；`run` 不进缓存（同 `acnr_results` 的处理）。
- 导出：采集向量后先在独立短事务里登记运行并提交，拿到运行编号（说明页要用）；`last_total` 取导出前的行数预检结果。证据记录在封存后另一个短事务里提交（§6.3）。
- 迁移未落库：`query_evidence_available(db)`（PG `to_regclass`、SQLite `sqlite_master`，进程内缓存 60 秒）为假时直接返回 `recorded = false`、原因「查询证据功能尚未启用（数据库迁移未执行）」。

### 5.4 列表、隐藏与清理

- 列表：`ROW_NUMBER() OVER (PARTITION BY definition_hash ORDER BY last_executed_at DESC) = 1`，再按最近执行时间倒序（PG 与 SQLite 同一写法），`limit ≤ 100`，`before` 游标翻页；按 R7.2 过滤项目（业务视图用本人可读项目集合一次取出，构建器按记录的项目集合与本人当前作用域比较）。
- 证据数：同用户、同 `definition_hash` 的证据条数（含已清理）。
- 隐藏：`hidden_at = now()`；`clear` 只隐藏本人、可按入口限定。
- 清理（`prune_runs`）：删除 `last_executed_at < now() - QUERY_RUN_RETENTION_DAYS` 或本人按最近执行时间排名 > `QUERY_RUN_KEEP_PER_USER` 的运行，且没有 `status = 'ready'` 的证据引用；每批 1,000 行。

## §6 查询证据（`backend/app/services/custom_query/query_artifacts.py`）

### 6.1 目录与配置（`backend/app/core/config.py`）

| 配置 | 缺省 | 说明 |
|---|---|---|
| `QUERY_ARTIFACT_ROOT` | 空 = `{STORAGE_ROOT}/query_artifacts` | 首次导出时 `mkdir(parents=True, exist_ok=True)`；所有路径经 `ensure_within_root` |
| `QUERY_ARTIFACT_RETENTION_DAYS` | 30（D1） | 证据保留天数 |
| `QUERY_RUN_RETENTION_DAYS` | 90（D2） | 运行记录保留天数 |
| `QUERY_RUN_KEEP_PER_USER` | 500（D2） | 每人保留条数 |

### 6.2 导出改造（`export_service`）

- 从 `stream_xlsx` 抽出 `build_xlsx_file(rows, columns, *, directory, file_stem, info_rows, sheet_title, extra_sheets) -> BuiltXlsx(path, row_count)`：即现有步骤 1~4（列容量守卫、表头、逐行写入与行上限守卫、说明页与附加页、保存），保存位置由参数决定。
- `stream_xlsx` 改为调用 `build_xlsx_file` 再逐块读出、最后删除，对现有调用方行为不变（既有导出测试不改即绿）。

### 6.3 封存流程（`seal_and_respond`）

1. 运行编号已在 §5.3 的导出登记里拿到；预先生成 `artifact_id`。说明页四行（R4.2）用这两个编号与版本摘要生成，经现有 `_InfoRows` 在写入时按实际行数组装。
2. `build_xlsx_file(directory=证据根/{yyyy}/{mm}, file_stem=".{artifact_id}")` 写出 `.partial`。
3. `hashlib.file_digest` 流式算 SHA-256，`stat` 取大小；`os.replace` 改名为 `{artifact_id}.xlsx`。
4. 组清单（§6.4）并算清单摘要；独立短事务（会话工厂可注入，缺省 `core.database.async_session`）写证据记录并提交。
5. 响应从最终文件逐块读出、不删除；`GatedStreamingResponse` 照旧负责释放导出名额。响应头带 `X-Query-Run-Id`、`X-Query-Artifact-Id`、`X-Query-Artifact-Status: stored`。

步骤 2~4 任一失败：删除本次产生的文件（证据记录尚未提交时），改走现有路径（临时文件、发完即删），响应头 `X-Query-Artifact-Status: unavailable`，导出审计记原因；已登记的运行记录保留（它记录的是一次真实执行）。运行登记本身失败时，说明页的查询编号写「未记录」，证据照常封存、`run_id` 为空。行数硬上限、列容量等现有 400 照旧在首字节之前返回，不算证据失败。

### 6.4 清单 v1（规范 JSON，键排序）

```
schema           "gt.query-artifact/v1"
artifact_id, run_id, entry, origin, template_id
project          {id, name}        year
source           {key, label}
definition, definition_hash
scope, version_vector, vector_hash, vector_weak, captured_at
columns          [{key, title}]    row_count    warnings    info_rows
file             {name, byte_size, sha256, media_type}
generated_at     generated_by {user_id, username}
```

`manifest_sha256 = sha256(规范 JSON 字节)`；`GET .../manifest` 返回同一规范序列化的字节，响应头 `X-Manifest-SHA256`。

### 6.5 下载

所有权（非本人 404）→ 重验访问（R7.2）→ 状态（purged 返回 410）→ 流式重算大小与 SHA-256（不一致返回 409 并记审计）→ 逐块返回（文件名按 RFC 5987，复用 `build_content_disposition`）→ 记 `custom_query.artifact_download` 审计。重算与发送之间文件被改的窗口不另加锁：证据目录只有后端进程写入（记为已知限制）。

### 6.6 清理

`purge_expired_artifacts`：`status = 'ready' AND retention_until < now()`，每批 500 条：删除文件（不存在也继续）→ 置 `purged` 与 `purged_at`；证据目录里超过 1 天的 `.partial` 一并删除。与 `prune_runs` 一起接入 `export_cleanup_worker`：启动时跑一次，之后每小时在主副本跑；日志记删除数。

## §7 接口（新 router `backend/app/routers/query_evidence.py`，前缀 `/api/custom-query`）

在 `router_registry/system.py` 紧随 `cq_router` 注册；路径与 `custom_query.py` 现有路由不重叠（该文件没有 `/{参数}` 形态的顶层路由）。

| 方法与路径 | 说明 | 成功 | 错误 |
|---|---|---|---|
| `GET /runs` | 本人历史：`entry`、`project_id`、`limit`（≤ 100）、`before` | 200 列表 | 401、503 |
| `GET /runs/{run_id}` | 详情：定义、范围、版本分量、该定义下的证据 | 200 | 401、403、404、503 |
| `GET /runs/{run_id}/freshness` | 过期判定 | 200 | 401、403、404、503 |
| `DELETE /runs/{run_id}` | 隐藏 | 204 | 401、404、503 |
| `POST /runs/clear` | 隐藏本人全部（`entry` 可选） | 200 `{hidden}` | 401、503 |
| `GET /artifacts` | 本人证据：`entry`、`project_id`、`limit`、`before` | 200 列表 | 401、503 |
| `GET /artifacts/{artifact_id}` | 证据详情（不含文件） | 200 | 401、403、404、503 |
| `GET /artifacts/{artifact_id}/download` | 重验后下载 | 200 文件流 | 401、403、404、409、410、503 |
| `GET /artifacts/{artifact_id}/manifest` | 清单 | 200 JSON + `X-Manifest-SHA256` | 401、403、404、503 |
| `GET /artifacts/{artifact_id}/freshness` | 过期判定 | 200 | 401、403、404、503 |

- 对象端点在函数体内先按 `id` 与 `user_id` 同时取对象（取不到 → 404），再重验访问（R7.2）；鉴权依赖 `get_current_user`，项目校验在函数体内调用 `ownership_guard.assert_target_accessible`，使端点鉴权基线识别为项目级判定。
- 只读端点不提交；`DELETE` 与 `clear` 由路由提交。
- 错误体沿用平台 `{error_code, message}`；503 为 `QUERY_EVIDENCE_UNAVAILABLE`。

## §8 前端

### 8.1 新文件

| 文件 | 职责 |
|---|---|
| `src/components/query/queryRunFormat.ts` | 分量与范围的显示格式：依据说明、北京时间、千分位、过期原因排版（表名用分量自带的 `label`） |
| `src/components/query/useQueryRunEvidence.ts` | 当前运行；判定（单飞 + 代际号丢弃旧响应；页面可见且距上次判定 ≥ 60 秒时自动判定）；历史与证据列表；隐藏、清空；下载、清单 |
| `src/components/query/QueryRunBanner.vue` | 信息条：范围、版本、采集时间、时效；检查 / 重新查询 / 历史入口；未登记、弱判据、无法判定、迁移未执行的提示 |
| `src/components/query/QueryEvidenceDrawer.vue` | 抽屉：「查询历史」「导出证据」两页；重新查询（向宿主发出定义）、检查时效、移除、清空、下载、查看清单 |
| `src/services/apiPaths/system.ts` | `customQuery` 增 `runs`、`runDetail(id)`、`runFreshness(id)`、`runsClear`、`artifacts`、`artifactDetail(id)`、`artifactDownload(id)`、`artifactManifest(id)`、`artifactFreshness(id)` |

### 8.2 宿主接入

| 宿主 | 改动 |
|---|---|
| `CustomQueryDialog.vue` | 删除 `QueryHistoryItem`、`QUERY_HISTORY_KEY`、`loadQueryHistory`、`pushQueryHistory`、`applyHistory` 与「🕘 历史」下拉；工具栏加「历史与证据」按钮；`QueryEntryBanner` 之后放信息条；执行成功时记下 `data.run`；回放 = 把定义写回项目、年度、源、旧筛选键、选区、条件、排序后调用 `executeQuery()`；首次加载执行 `localStorage.removeItem('gt:cq:history')`；「导出全部」读证据响应头给出提示 |
| `CustomQueryTab.vue` | 结果头下方放信息条；结果操作区加「历史与证据」；回放写回 `formCtx`、筛选、条件、列、排序；导出提示 |
| `AdvancedQueryBuilder.vue` | 信息条承接 `resultScopeText`（`data-testid="aqb-result-scope"` 移到信息条的范围段）；回放写回 `dsl` 各字段与项目范围；导出提示 |
| `queryServerExport.ts` | `exportAllQueryRows` 返回 `{ runId, artifactId, status }`（读 `downloadFile` 返回的响应头） |

- 不支持的设置：各宿主声明自己能写回的定义键；回放时把其余非空键列成中文清单，经确认框让用户选择继续（按可支持部分执行）或取消。
- 请求一律带 `_silent`，错误在信息条或抽屉内显示后端中文原因与追踪号；判定请求由组合式函数单飞，避免平台 GET 去重取消先发请求。
- 部署为跨域时需在 CORS 配置增加 `expose_headers`（当前后端未配置，开发环境经 Vite 代理、生产经 Nginx 均为同源，不受影响）。

## §9 权限矩阵（真 PG，回滚事务内自建【测试】项目与身份）

身份：A 创建者（项目成员、edit）；B 同项目另一成员；C 非成员；D admin 非创建者；E 创建者已被移出项目（成员行软删）；F 构建器记录的创建者已失去准入；G 未登录。

| 端点 | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| `GET /runs` | 含本人记录 | 不含 A 的 | 不含 A 的 | 不含 A 的 | 不含该项目的 | 不含构建器记录 | 401 |
| `GET /runs/{id}`、`/freshness`（业务视图记录） | 200 | 404 | 404 | 404 | 403 | — | 401 |
| `GET /runs/{id}`、`/freshness`（构建器记录） | 200 | 404 | 404 | 404 | 403 | 403 | 401 |
| `DELETE /runs/{id}` | 204 | 404 | 404 | 404 | 204 | 204 | 401 |
| `GET /artifacts/{id}`、`/manifest`、`/download`、`/freshness` | 200 | 404 | 404 | 404 | 403 | 403（构建器证据） | 401 |

隐藏本人记录不泄露数据，失去访问后仍允许（E、F 的 `DELETE` 为 204）。

## §10 测试与验收

### 10.1 单测（SQLite / 纯函数）

- 定义规范化 PBT（max_examples=5）：键序、UUID 大小写不影响摘要；`limit` / `offset` / `count_token` / `headers` / `file_name` 不影响摘要；条件顺序影响摘要。
- 登记表完整性守卫（§4.3 末段）；依据声明守卫（JSONB 大列表不得用 content）。
- 比较规则表驱动（§4.5 每行一例）；`latest_update` 不同但摘要相同判一致。
- 降级：表不存在时 `recorded = false`、导出 `unavailable`、接口 503。
- 说明页四行；清单规范序列化往返（序列化 → 解析 → 再序列化字节相同）。
- 业务视图与构建器既有响应键、类型不变（N2，对比改动前的键集合）。

### 10.2 真 PG（`backend/tests/advanced_query_linkage/test_aqf_*.py`，复用 `pg_rollback_session`、`new_project`、`business`、`builder` 夹具）

| 编号 | 用例 |
|---|---|
| P1 | 采集 → 新 SAVEPOINT 内用裸 SQL 改试算表 `audited_amount`（不写 `updated_at`）→ 判定 stale，原因「试算平衡表有行被修改」 |
| P2 | 只改试算表 `updated_at` → 判定 current（内容依据） |
| P3 | 改底稿 `parsed_data` → 判定 stale（行版本依据） |
| P4 | 回滚事务内新建并激活数据集 → 判定 stale，原因「生效数据集已切换」 |
| P5 | 取数钩子里写入（模拟查询进行中提交）→ 判定 stale |
| P6 | 写入后 30 秒内再执行同一查询 → 不命中旧缓存，返回新值 |
| P7 | 写入后带旧 COUNT 凭证翻页 → total 重算为新行数 |
| P8 | 同一定义翻页命中同一运行；写入后再执行得新运行；60 秒内重复执行不更新记录（执行次数与 `updated_at` 不变）；隐藏后再执行取消隐藏 |
| P9 | 触发器：改运行或证据的身份字段报错；改执行次数、`ready → purged` 可以；`purged → ready` 报错 |
| P10 | 导出 → 文件 SHA-256 = 记录 = 清单；改文件 1 字节 → 409；清理后 → 410；证据目录不可写 → 导出照常、`unavailable` |
| P11 | 清理：过期证据删文件、标 purged；被未清理证据引用的运行不删；超过 500 条删最早的 |
| P12 | §9 权限矩阵逐格 |
| P13 | 某分量采集语句出错 → 本次查询照常返回、该分量 `error`、判定 unknown；同一请求后续语句仍成功（事务未被污染） |

### 10.3 前端 vitest

信息条各状态（current / stale / unknown / 未登记 / 弱判据 / 503）；自动判定节流与代际丢弃；抽屉列表、回放事件、下载与清单；三宿主回放映射与不支持设置提示；弹窗不再写 `gt:cq:history` 且首次加载删除该键；导出提示读响应头；`aqb-result-scope` 锚点仍在。

### 10.4 变异（磁盘注入，逐字节还原后核对 sha256）

| 编号 | 变异 | 预期打红 |
|---|---|---|
| M1 | 采集挪到取数之后 | P5 |
| M2 | 缓存键去掉版本摘要 | P6 |
| M3 | COUNT 凭证主体去掉版本摘要 | P7 |
| M4 | 内容摘要不去掉 `updated_at` | P2 |
| M5 | 试算表依据改为 timestamp | P1 |
| M6 | 数据集分量只比较行数 | P4 |
| M7 | 登记表删除 adj_rje | 登记表完整性守卫 |
| M8 | 定义摘要包含 `offset` | P8（翻页同一运行） |
| M9 | 删除运行记录不可变触发器 | P9 |
| M10 | 下载不重验摘要 | P10（改文件 409） |
| M11 | 证据保存失败时抛错 | P10（目录不可写） |
| M12 | 非创建者返回 403 | P12 |
| M13 | 失去项目访问仍可下载 | P12 |
| M14 | 分量采集失败当作一致 | P13 |
| M15 | 清理时删除被引用的运行 | P11 |
| F1 | 信息条不显示弱判据说明 | 信息条弱判据用例 |
| F2 | 自动判定不节流 | 节流用例 |
| F3 | 弹窗仍写 `gt:cq:history` | 弹窗本地存储用例 |
| F4 | 回放静默丢弃不支持的设置 | 回放提示用例 |

阴性对照 N1：只改原因文案，全部判据保持绿（证明判据不是对任何改动都红）。

### 10.5 候选栈浏览器走查（写后读回）

候选栈沿用阶段 0 的做法：候选后端 9981（`--lifespan off`、`GT_BOOTSTRAP_DONE=1`、Redis 第 9 库），候选前端 3040（代理到 9981）。前提：迁移已落共享库（D3）。写入只在【测试】项目、走平台写入路径，结束后还原并对账。

| 编号 | 步骤与判据 |
|---|---|
| W1 | 弹窗查【测试】项目的审计调整分录（AJE）与试算表 → 信息条显示范围、版本、采集时间；「检查是否过期」→ 未变化 |
| W2 | 在调整分录页给该项目录入一笔 AJE → 切回查询页（页面重新可见触发自动判定）→ AJE 查询显示已过期与原因「调整分录行数 a → b」→ 「重新查询」→ 未变化；最后删除该分录，库内对账恢复（只录草稿、不审批，试算表不受影响） |
| W3 | 「导出全部」→ 说明页含四个新行；抽屉「导出证据」可见该证据；下载文件的 SHA-256 与清单一致；openpyxl 读出的数据行数 = 记录行数 |
| W4 | 三个宿主各执行两种查询 → 历史按定义去重、回放结果一致；「清空历史」后历史为空、证据仍可下载 |
| W5 | admin 在构建器跨项目查询 → 信息条范围段文案与原范围标签一致 |

全程浏览器 console error 为 0。

### 10.6 性能

探针在共享库最大作用域对试算表、报表、序时账、附注、底稿五类来源各执行 50 次，记录采集耗时 p50 / p95 与单次判定耗时，结果写进本文收口节（N1、R3.3）。

### 10.7 门禁

`check_router_registration`、`check_file_size`、`check_migration_versions`、`check_staged_tree_self_consistency` 全部 exit 0；端点鉴权基线（`test_project_endpoint_authorization_baseline.py`、`test_project_endpoint_authz_body_carried.py`）计数不增；`test_route_shadow_guard.py`、迁移完整性用例、`test_spec_index_consistency.py` 通过；单区域 vue-tsc 0 错误，并用注入错误证明它真的在检查。

## §11 Phase 2 预留（本 spec 不实施）

- 证据转附件：把证据文件复制进附件根、登记 `asset_blobs`、建 `attachment_versions`，写法同 `knowledge_evidence_promotions`，记录来源证据编号与清单摘要。
- 关联：`evidence_links` 增加「查询证据」来源（证据编号 + 行键），目标为底稿、单元格、凭证。
- 问题单：从选中结果行建问题单，带运行编号、行唯一键与版本摘要。
- 复核快照：复核时固定证据编号与其判定结果。
- 归档：`archive_inventory` 纳入项目内被关联的证据（清单摘要进归档 manifest）。
- 被关联或已归档的证据不受到期清理：Phase 2 增加固定标记，`purge_expired_artifacts` 的条件随之增加一项。

## §12 现状确认中发现的范围外问题（本 spec 不修）

### 12.1 🔴 P0：报表生成的运行记录在 PostgreSQL 上写不进去

- `report_generation_run` 被 V246（合并运行与产物）和 V251（公式来源运行记录）各建一次，两份结构不同，都用 `CREATE TABLE IF NOT EXISTS`。共享库按先执行的 V246 建表：`status` 的 CHECK 只允许 building / succeeded / failed / stale，`calc_version` 为 integer，没有 `error_summary`。ORM `report_generation_models.ReportGenerationRun` 也是 V246 结构。
- `report_provenance.generation_context`（由 `install_report_generation_provenance` 在导入 `report_engine.py` 时装到 `generate_all_reports`、`recalculate_stale_rows`、`regenerate_affected` 三条路径上）写入 `status = "running"`、`calc_version = "report:2"`；`finish_generation` 再写 `status = "partial"` 与 ORM 里不存在的 `error_summary`。
- 回滚事务实测（【测试】项目；探针 `tmp_aq_phase0/probes/p1_report_run_probe.py`）：调用 `generation_context` → asyncpg `DataError: invalid input for query argument $11: 'report:2'`；手工插入 `status = 'running'`、`calc_version = 2` → `CheckViolationError: ck_report_generation_run_status`。表在探针前后都是 0 行。
- 影响：三条报表生成 / 重算路径在 PostgreSQL 上一进入运行上下文就失败。守卫 `test_report_provenance_migration_matches_model_surface` 只检查迁移文本里的字符串，没有对数据库实际插入，所以一直是绿的。
- 处置（用户 2026-11-04 裁决，requirements D4）：采用并发会话的修复口径，本 spec 不另修。开始写 `building`、结束写 `succeeded`（部分行失败时失败行数记 `failed_rows`、原因写 `error`），`calc_version` 存整数 `CALC_VERSION`，来源接口读 `run.error`（响应键仍为 `error_summary`），不加迁移。
- 落地情况（写入本条时）：生成失败已由 v1.0.107 的 `ddcde5244`（spec `note-disclosure-pull-regression-and-headless-backend` R2.5 / ADR-NPR-07）按同一口径修复，另加对外状态换算 `run_display_status`（`building` 显示 running，`succeeded` 且 `failed_rows > 0` 显示 partial）。`formula-management-repair-closure` R0.1 也做了同样的修复（未推送）；其中 R251 的更正（只撤销 V251 实际新增的外键与两个索引）远端还没有：远端的 R251 仍会删掉 V246 的表与 `run_id` / `provenance` 两列。
- 共享库回滚事务实测（2026-11-04，表前后都是 0 行、CHECK 不变）：`59e1e3bca` 上「全部成功」与「含一行失败」两次生成都报 `DataError`（`'report:2'` 写进整数列）；v1.0.107（`6046ebab4`）两次都写入成功，含失败行的那次 `failed_rows = 1`、`error` 有原因。`59e1e3bca` 上 14 个报表相关测试目标共 209 条红，其中 101 条的失败原因就是本漂移。
- 本会话另做过「新增迁移把 `partial` 加进 CHECK」的方案，未提交、已作废：要改合并 spec 的 `REPORT_RUN_STATUSES` 与 CHECK，还要共享库迁移放行；而读取方只有合并模块按状态过滤（且内连接合并操作表，单体报表的运行记录不受影响），`partial` 没有消费方。

### 12.2 其他

- INDEX「一、Active Specs」中 `advanced-query-safety-and-consistency-closure` 记为「0/8（实施中）」，而其 tasks.md 为 8/8 且逐项附证据（提交 `38d58ff5a`）。本 spec 提交时按 tasks.md 一并更正。
- 附注指标树版本 `X-Notes-Version` 用 `max(updated_at)`，受 §0.2 的裸 SQL 改写影响，可能漏报变化；不在本 spec 修改。
