# 设计文档：S10　审计哈希链加固（audit-log-chain-integrity）

> 需求编号：requirements §1「设计输入」第 1~8 点记 I1~I8，「`append_audit_log` 调用方吞异常逐个裁决」记 I9。现状事实只写在本文 §1。
> 现状基线：分支 HEAD `4c0a1e0a6`；母 spec 代码未入库，以整合树 `tmp_fhic/integ`（`d91f5f804`）为准。三个审计主文件在两棵树里逐字节相同（母 spec 需求 11.3 的 0 改动成立）。§1 的数字是 2026-10-29 只读现算（共享库只读事务 + AST），实施第一步按同一口径重算，变化追加在 §1 末尾，不改原文。

## 0. 结论

审计链有三个根因：取链尾靠 `ts` 排序而不是链接关系；写入方之间没有可靠互斥（helper 无锁，worker 的锁键每个进程不同）；读链尾失败一律退回创世哈希。修法是把「写一条链」收口成一个内核：取链锁 → 读链尾表 → 判是否有人绕过链尾写入 → 插入 → 更新链尾。helper、worker、分叉确认工具都只调这个内核。校验改为按链接关系遍历，报出分叉、断头、缺前缀、内容不符四类原因。上线顺序固定：先交付只读扫描与确认工具、在共享库确认那 1 处分叉，再交付 fail-closed 代码。

## 1. 现状复核

| # | 交接结论 | 现算（2026-10-29） | 判定 |
|---|---|---|---|
| 1 | I1：按 `ts DESC` 取链尾 | helper 与 worker 的 `_get_prev_hash` 都是 `payload->>'project_id'` 过滤后 `ORDER BY ts DESC LIMIT 1`；真库同链同 `ts` 49 组 | 成立 |
| 2 | `prev_hash` 无索引 | 成立；`payload->>'project_id'` 也没有表达式索引；`entry_hash` 有两个等价唯一索引（`audit_log_entries_entry_hash_key`、`idx_audit_log_entries_entry_hash`，后者来自 ORM 的 `Index(unique=True)`） | 成立；重复索引只登记 |
| 3 | worker 锁键进程随机、取锁失败降级无锁；helper 无锁 | `lock_id = hash(lock_key) & 0x7FFF…`，Python 对 `str` 的 `hash` 每进程加盐，两个 worker 进程锁不到同一个键；取锁异常后照常写 | 成立 |
| 4 | I8：读链尾异常返回 GENESIS | helper `except Exception: return GENESIS_HASH`；worker 同样只记 warning。PG 上 SQL 失败会中止事务，随后的 INSERT 也失败（p1-10 改述）；只有非 SQL 异常（如方言判断走错分支）会真的落一条新链首 | 成立（按改述） |
| 5 | worker 一批多链同事务、超重试上限即丢弃 | 同一事务写全部链，任一链失败整批回滚进重试队列；`retry_count >= 3` 记「entries lost」并发管理员通知后丢弃 | 成立 |
| 6 | F44：1736 行 / 387 链 / 全局链 893 行，1 处未确认分叉 | 1836 行 / 403 条链 / 全局链 948 行；每条链恰 1 个创世条目；全局链 `prev_hash` 前缀 `9f4c6bb42517` 有 2 个后继（`download` 一支无后继、`view` 一支继续），链尾总数 404 = 403 + 1；断头（`prev_hash` 非创世且链内找不到）0；空哈希行 0 | 数字已变，分叉仍是同一处 |
| 7 | 唯一 `formula.changed` 行按 v1 重算不等于存值 | 不符共 12 行：1 行 `formula.changed`（`resource_id` 不是 UUID ⇒ `object_id` 存 NULL，写入时却用原字符串参与哈希）+ 11 行 `cell_writeback`（2026-10-03/04 写入，`wp_code` 是 32 位十六进制、旧值「A节点原值」、新值「新写入值」，是测试写进共享库的数据；`ts` 四种写法 × 是否去掉 `project_id` × 是否置空 `object_id` 共 16 种组合都不命中，原因未定） | 规模变大；v1 只能按「不可重算」计，不能当篡改 |
| 8 | （交接未列）绕过 helper 的写入方 | 3 处，且都写不进去：①`routers/role_workbench.confirm_warning_item` 用 ORM 直接构造、不给哈希 ⇒ 两个哈希列 NOT NULL 无默认值 ⇒ 恒 500；前端不调用（前端的确认走 `signoff_checklist`，写 `app_audit_log`）。②`note_data_lock_service.unlock` 原生 SQL 写 `action / details / created_at`，这三列不存在 ⇒ 解锁恒 500；前端只有路径常量 `dataLock.unlock`，无界面调用。③`wp_disclosure_sync_service._write_audit_log` 同①，`db.add` 包在 try 里，失败发生在之后的 commit ⇒ HTML 渲染器附注同步整体 500；真库 `last_sync_source='workpaper_html'` 的附注 0 行，前端无调用。真库这几种 action 0 行 | 新增 |
| 9 | （交接未列）哈希函数副本 | 4 份：helper、worker、`routers/audit_logs.py` 各一份，`audit_logger_enhanced._compute_entry_hash` 一份（`user_id` 不做 `or ''`，与另外三份不同） | 新增 |
| 10 | I9：41 处 / 25 个文件 | AST 现算两棵树都是 41 / 25；其中 20 处 / 11 个文件位于不重抛的 `except Exception` 内（吞异常），2 处在 `begin_nested` 内 | 成立；吞异常清单见 §5 |
| 11 | F50：verify-chain 鉴权与排序 | admin 或项目角色 ∈ {partner, signing_partner, qc, eqcr, manager}；按 `(ts, id)` 排序；首条 `prev_hash` 任意值都采信（删掉前缀仍判有效）；时间片没有片外锚点；只返回第一处断裂；不识别分叉。`tests/test_audit_log_hash_chain_property.py` 在测试里自己重写了一份校验函数，没有调用路由 | 成立；该属性测试是假绿 |
| 12 | I5：审计链锁最后取 | 应用内事务级咨询锁 12 个取锁点（`formula_settings.engine` 域锁 / 项目锁、`workpaper_sync.repository`、`draft_refresh_service`、`draft_refresh_orchestrator`、`formula_push.engine`、`consol_push_service`、`consol_elimination_sheet_service`、`consol_note_formula_service`、`formula_settings.template_sync`、`attachment_service` 链锁、`adjustment_service` 编号、`chain_orchestrator`）；审计链目前没锁，违规点要等加锁后实测 | 成立；违规清单待实测 |
| 13 | I4：`/api/health` 增字段 | 现状 `status` 只看 PG / Redis、迁移失败、critical 漂移 | 成立 |
| 14 | I6：兼容公式审计载荷里的 `year` | 母 spec 需求 11.1 的 `formula.changed` 载荷已带 `year` | 成立 |
| 15 | 迁移号 | 三路合扫（git 全部引用 ∪ 各 worktree 工作区 ∪ 共享库 `schema_version`）最高 V220（母 spec 的 V218~V220，尚未入库）⇒ 本 spec 取号 ≥ V221，实施时重扫 | — |

**Task 0 重算（2026-10-29，HEAD `1fc47bb3a`）**：15 行全部复核，DB 数字无变化——total 1836 / 403 链 / 全局 948 / 链尾 404 / 分叉 1（同一处 `9f4c6bb42517`）/ 断头 0 / v1 不符 12 / 同链同 ts 49 组；AST 41 处 / 25 文件、吞异常 20 处（去重后）/ 11 文件、begin_nested 2 处、AuditLogEntry 构造 4 处（绕过 3 处）、哈希副本 4 份；取锁点数量 12（`chain_orchestrator` 实际用 asyncio.Lock 不用 advisory，不变）。迁移三路合扫：git 最高 V216、磁盘最高 V216（V212 仅磁盘未入 git）、共享库 schema_version 最高 V217（V218~V220 仍未入库）⇒ ≥ V221 仍有效。探针输出存 `tmp_audit_chain/baseline/`。

## 2. 架构裁定

**ADR-ALC-01 单一写链内核。** 新包 `backend/app/services/audit_chain/`（每个模块 ≤ 300 行）：

| 模块 | 内容 |
|---|---|
| `canonical.py` | `GENESIS_HASH`；`canonical_payload(obj)`：递归规范化，`float` → `format(Decimal(repr(x)), 'f')` 字符串，`Decimal` → 字符串，`UUID` → 字符串，`datetime` → UTC ISO（微秒）；`NaN` / `Inf` 抛 `AuditPayloadError`；`hash_v2(fields)`；`hash_v1(...)`（只供校验旧行，四份旧副本删除） |
| `head.py` | `chain_key_of(project_id)`（`project:<uuid>` / `__global__`）；`lock_chain(db, key)`：`pg_advisory_xact_lock(hashtextextended('audit_chain:' \|\| :key, 0))`，SQLite 不加锁；`read_head(db, key)`；`append_entry(db, key, fields) -> AuditLogEntry` |
| `forks.py` | `scan_forks(db)`（只读）；`append_fork_ack(db, key, *, survivor_entry_id, dead_entry_id, operator_id, reason)` |
| `verify.py` | 按链接关系校验（ADR-05） |
| `call_sites.py` | 调用方裁决登记表（ADR-07） |
| `lock_order.py` | 事务内咨询锁顺序探测（ADR-09） |

`append_entry` 在一个事务内依次：①`lock_chain`；②`read_head`；③`EXISTS(SELECT 1 FROM audit_log_entries WHERE prev_hash = :tail)` 为真 ⇒ 抛 `AuditChainBypassed`（有人绕过链尾表写过这条链）；④按 v2 计算哈希并插入；⑤更新链尾表。任何一步失败都抛出，不退回创世哈希（I8）。`audit_log_helper.append_audit_log` 改成薄封装（校验 `event_type` 必需字段 → 组装字段 → `append_entry`），签名与返回值不变；`GENESIS_HASH` 保留再导出。

**ADR-ALC-02 链尾表 + 锁内惰性初始化（对 I1 的变形）。** 新表 `audit_chain_head(chain_key varchar(80) PK, tail_entry_id uuid NOT NULL, tail_hash varchar(64) NOT NULL, entry_count bigint NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())`。I1 要求一次性回填；改为 `read_head` 在锁内发现没有链尾行时现算：该链 0 条 ⇒ 创世；未确认链尾恰 1 个 ⇒ 采用并写入链尾行；多于 1 个 ⇒ 抛 `AuditChainForked`。理由：迁移先于新代码上线（X1 顺序），这段时间旧代码仍按 `ts` 续写，一次性回填的链尾在新代码上线时已经过期，第一笔写入就会被判成「绕过写入」。另给运维脚本 `backend/scripts/ops/audit_chain_heads.py`（默认只读列出每条链的链尾与状态，`--apply` 预先写入链尾行），上线后可执行一次，省掉首写时的现算。「未确认链尾」= 链内没有后继的条目，减去该链分叉确认条目里点名的 `dead_entry_id`。

**ADR-ALC-03 分叉确认先于 fail-closed（I2、I4）。** 确认条目：`action_type='audit.fork_ack'`、`object_type='audit_log_entry'`，载荷含 `survivor_entry_id / dead_entry_id / reason / operator_id`，`prev_hash` = survivor 的 `entry_hash`，直接插入、不经链尾查找。前置校验在链锁内做：该链未确认链尾集合恰为 {survivor, dead}，否则拒绝并列出实际集合。入口只有命令行 `backend/scripts/ops/audit_chain_fork_ack.py`（默认只读演示，`--apply` 才写，`--operator` 必须是 admin 用户），不开 HTTP 端点。交付分两批：批 A 只读扫描、确认工具、健康字段、校验端点；用户在共享库执行确认（§7 Y1）后再合入批 B 的 fail-closed 代码。批 B 合入前的检查记录必须含「共享库未确认分叉 = 0」的扫描输出。

**ADR-ALC-04 v2 可重放哈希（I6）。** 参与哈希的字段：`{"v": 2, "ts", "user_id", "action_type", "object_type", "resource_id", "project_id", "year", "payload", "prev_hash"}`，`json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 后 sha256。`ts` 由应用生成、写库与哈希用同一个值，格式 `astimezone(UTC).isoformat(timespec="microseconds")`；`resource_id` 用调用方原字符串（解决 §1 第 7 行的 `object_id` 丢失）；`payload` 是规范化后的业务载荷。落库载荷另带保留键 `_hash_v: 2`、`_resource_id`、`_year`（调用方给了年度才写），保留键不进 `payload` 字段的哈希输入。浮点存成定点字符串后，JSONB 往返不再改变数字写法（`1e20` 原先会变成 `100000000000000000000`）。没有 `_hash_v` 的旧行按 v1 公式重算：一致计 `legacy_verified`，不一致计 `legacy_unverifiable`，不算断链；链接关系照常校验。载荷读者（公式历史、时间轴等读 `result_value` 之类数值字段的地方）实施时逐个现读，数值改成字符串后展示不受影响的才放行，否则在读者处转回数值。

**ADR-ALC-05 按链接关系校验（I7）。** `GET /api/audit-logs/verify-chain` 鉴权不变。读出整条链（只取校验需要的列），按 `entry_hash → 条目`、`prev_hash → 后继列表` 建索引，从创世条目沿链走：

| 原因 | 判据 |
|---|---|
| `fork` | 一个哈希有多个后继，且多出的分支没有被确认条目点名 |
| `orphan` | `prev_hash` 不是创世哈希，链内也找不到该哈希 |
| `missing_prefix` | 链内没有创世条目；或时间片模式下片内首条的前驱在片外不存在 |
| `content_mismatch` | v2 条目重算哈希与存值不同 |

响应保留旧字段（`valid`、`entries_checked`、`broken_at_entry_id`、`message`，取第一处问题），新增 `problems[]`、`legacy_verified`、`legacy_unverifiable`；时间片模式新增 `anchor{entry_id, entry_hash, ts}`（片外前驱）。`legacy_unverifiable` 不影响 `valid`。

**ADR-ALC-06 worker 逐链事务 + 隔离区（对 I3 的变形）。** I3 要求一个事务内每条链一个保存点。改为每条链一个事务：同一事务里持有多条链的锁会把锁持有时间拉到整批结束，并且多链加锁顺序与请求路径不一致时可能互相等待；每链一个事务时 worker 任一时刻只持有一条链的锁。链失败只回滚该链，条目原样推入 Redis 列表 `audit:log:quarantine:<chain_key>`，不计重试次数、不丢弃。原「重试 3 次后丢弃」改为：非链类错误（数据库不可用等）重试到上限后同样进隔离区。worker 每 30 轮（约 1 分钟）对隔离区非空的链各尝试一次重放，成功才出列；分叉、绕过写入等链类错误留在隔离区，等运维用确认工具处理。删除 `hash(lock_key)` 与取锁失败后的无锁降级（I8）。

**ADR-ALC-07 调用方逐个裁决（I9）。** 三种策略写在 `audit_chain/call_sites.py` 的登记表里（键 = 模块路径 + 函数名，值 = 策略 + 理由）：

| 策略 | 形态 | 适用 |
|---|---|---|
| `mandatory` | 不捕获，审计失败即业务失败 | 改数据、改定义、审批、回滚、解锁、归档类 |
| `best_effort` | `async with db.begin_nested()` 包住调用，捕获后记 warning 与计数 `audit_best_effort_failures`，业务继续 | 执行留痕、运行生命周期、回调拒绝记录类 |
| `own_session` | 在独立会话内写并自行提交 | AI 对话运行协调器（已是此形态） |

AST 守卫 `tests/audit_chain/test_audit_call_site_policy.py`：全仓每个 `append_audit_log(` 调用都必须在登记表里；登记为 `mandatory` 的不得位于不重抛的 `except Exception` 内；`best_effort` 的必须同时在 `begin_nested` 内并被捕获；登记表里不存在的函数即红。20 处吞异常的默认裁决见 §5，交用户确认（§7 Y2）。

**ADR-ALC-08 绕过写入方收口。** §1 第 8 行三处改为调 `append_audit_log`（`unlock`、`sync_from_html` 记 `mandatory`；`confirm-warning` 见 §7 Y3）。AST 守卫：`AuditLogEntry(` 构造只允许出现在 `audit_chain/head.py`、`audit_chain/forks.py`；`backend/app` 内任何 SQL 文本不得含 `INSERT INTO audit_log_entries`；守卫带违规样本自检。

**ADR-ALC-09 锁顺序（I5）。** `lock_order.py` 在 `Session` 上挂 `do_orm_execute` 监听：语句含 `pg_advisory_xact_lock` / `pg_advisory_lock` 时，若本事务已持有审计链锁且这次不是审计链锁 ⇒ 记一次违规；同一事务取第二条审计链锁时链键必须大于已持有的全部链键，否则也记违规。`after_transaction_end` 清空记录。设 `GT_AUDIT_LOCK_ORDER_STRICT=1`（测试 conftest 设置）时违规抛 `AuditLockOrderViolation`，生产只记 error 日志与计数。新增 `append_audit_log_batch(db, payloads)`：按链键升序写入，同一事务写多条链的调用方（`formula_settings.audit` 的逐项目留痕等，实施时现扫）改用它。存量违规以严格模式跑回归得出，能挪到事务末尾的就挪，挪不了的进白名单（写理由，只许变短）。

**ADR-ALC-10 健康检查字段（I4）。** `/api/health` 增 `audit_chain{unacknowledged_forks, quarantined_entries, checked_at}`：`unacknowledged_forks > 0` 或 `quarantined_entries > 0` ⇒ `degraded`。分叉数用 `prev_hash` 索引分组统计后减去已确认的分支，结果进程内缓存 300 秒；隔离区条数用 `SCAN audit:log:quarantine:*` + `LLEN` 求和，Redis 不可用时该项为 `null` 且不参与判定。端点无需登录，只暴露计数。

## 3. 数据与迁移

迁移 `V{n}`（实施时三路合扫取号，现值 ≥ V221）：`CREATE TABLE IF NOT EXISTS audit_chain_head (...)`；`CREATE INDEX IF NOT EXISTS idx_audit_log_entries_prev_hash ON audit_log_entries (prev_hash)`；`CREATE INDEX IF NOT EXISTS idx_audit_log_entries_chain ON audit_log_entries ((payload->>'project_id'))`。`R{n}` 删表与两个索引。ORM 新增 `AuditChainHead`（`audit_log_models.py`），三层一致测试覆盖。不改 `audit_log_entries` 的列，不删重复索引（只登记）。新表、新索引对旧代码无影响 ⇒ 可以先迁移后推送。

## 4. 测试与变异

- 纯函数（SQLite / 无库）：`canonical_payload`（`1e20`、`0.1`、`Decimal`、嵌套、`NaN` / `Inf` 拒绝）；`hash_v2` 经 `json.loads(json.dumps(...))` 往返后重算一致；校验四类原因与 legacy 计数各一组夹具（`test_audit_chain_verify.py`）；惰性初始化三种状态；确认前置校验；登记表与绕过写入两个 AST 守卫；锁顺序探测器（构造语句序列）。
- 真 PG：一次性库 `gt_s10_<pid>_<时间>`（`CREATE DATABASE`，只用 ORM 元数据建 `audit_log_entries` 与 `audit_chain_head` 两张表，结束删库并核对 `pg_database` 无残留），测试会真提交，不连共享库写：两个独立会话同链并发各写 1 条 ⇒ 链长 2 且衔接；绕过写入后下一笔 `AuditChainBypassed`；分叉链确认后可续写；worker 两条链其一注入失败 ⇒ 另一条已提交、失败条目在隔离区（Redis 15 号库，结束清空）；`1e20` 经真 JSONB 往返重算一致；verify-chain 端点在一次性库上用 TestClient 跑四类原因（覆盖 `get_db`、`get_current_user`）。
- 共享库只读：`scan_forks` 报出且只报出 §1 第 6 行那一处，输出贴进任务记录。
- 既有测试改写：`test_audit_log_helper.py`（首条 `prev_hash` 仍为创世）、`test_audit_log_enhanced.py`（整对象替换 `app.core.config.settings` 的写法按 memory ⑬ 改成只替换属性）、`test_audit_log_hash_chain_property.py`（改为调用 `verify.py`，不再自带一份校验）。
- 磁盘变异（备份放 `tmp_audit_chain/mutations/`，单独一条命令跑，跑完 sha256 核对）：去掉 `lock_chain` ⇒ 并发用例红；读链尾异常改回返回创世 ⇒ fail-closed 用例红；去掉 `EXISTS` 绕过检查 ⇒ 绕过用例红；浮点不规范化 ⇒ `1e20` 往返用例红；校验恢复「首条 prev_hash 任意采信」⇒ `missing_prefix` 用例红；worker 改回整批一个事务 ⇒ 隔离用例红；登记表守卫跳过 `mandatory` 形态检查 ⇒ 守卫自检红。

## 5. 吞异常调用点的默认裁决（20 处 / 11 个文件，§7 Y2 确认）

判据：调用记录的是「数据或定义被改了」⇒ `mandatory`；记录的是「某次执行发生过」⇒ `best_effort`。其余 21 处现在就不吞异常，登记为 `mandatory`（实施时逐个现读确认）。

| 文件 · 函数 | 记录内容 | 默认裁决 |
|---|---|---|
| `routers/consol_report.py` · `_write_consol_formula_audit` | 合并报表公式执行结果 | best_effort |
| `routers/report_config.py`（整合树已搬到 `report_config_execute.py`，实施时按函数名定位）· 批量执行留痕 | 公式执行结果 | best_effort |
| `routers/wp_formula.py`（整合树在 `wp_formula_audit.py`）· `_write_wp_formula_audit` | 底稿公式增改（已在 `begin_nested` 内） | mandatory |
| `routers/wp_user_formulas.py` · `update_user_formulas`、`restore_preset_formula` | 底稿用户公式修改 / 恢复预设 | mandatory |
| `services/ai_chat/audit.py` 8 个函数 | AI 运行与工具生命周期、拒绝访问、转存、采纳、附件清理 | best_effort（协调器内已用独立会话的保持 `own_session`） |
| `services/bulk_tab/bulk_import_service.py` · `_write_import_audit_log` | 批量导入写数 | mandatory |
| `services/bulk_tab/workflow_gate.py` · `_write_revert_audit_log` | 回退 | mandatory |
| `services/event_handlers/_impl.py` · `_advance_project_status_on_dataset_activated` | 系统自动推进项目状态 | best_effort |
| `services/formula_management/cross_check_run.py` · `_write_audit` | 表间审核执行 | best_effort |
| `services/onlyoffice_callback_service.py` · `write_security_log`、`_log_stale_base_save` | 回调被拒、陈旧底版保存 | best_effort（回调必须及时应答） |
| `services/report_config_service.py` · `review_candidate` | 全局候选审核（已在 `begin_nested` 内） | mandatory |

## 6. 风险与降级

| 风险 | 处理 |
|---|---|
| 批 B 先于分叉确认合入 ⇒ 全局链首写抛 `AuditChainForked`，公式全局发布等写全局链的操作失败 | ADR-03 的合入前检查记录；批 B 的 PG 用例之外再加一条只读用例：共享库存在未确认分叉时打印清单并 `xfail(strict=True)`，确认后转为必须通过 |
| `mandatory` 改动让原先「审计失败照样成功」的操作开始失败 | 内核不再因链尾查询失败而写新链首，真实失败只剩数据库不可用、载荷含 NaN、链被绕过写入三类，都应该让操作失败；best_effort 失败计数进 `/api/health` 之外的日志告警 |
| 惰性初始化在大链上首写变慢 | `prev_hash` 与链键两个索引；运维脚本可预先写链尾行 |
| 多进程 worker 与请求并发写同一链 | 同一个咨询锁键（`hashtextextended`，跨进程稳定）；worker 每链一个事务 |
| 载荷浮点改字符串影响读者 | ADR-04 的读者现读；只改新写入的行，旧行不动 |
| 11 行测试垃圾与 1 行 `formula.changed` 永远 `legacy_unverifiable` | 不删（审计表只追加）；校验结果单列，不算断链 |

## 7. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| Y1 | 在共享库执行那 1 处分叉的确认：survivor = 继续延伸的 `view` 支的当前链尾，dead = 无后继的 `download` 条目 | 批 A 交付后执行；执行前后各跑一次 `scan_forks` 贴记录 |
| Y2 | §5 默认裁决 | 按表执行；改选某处只改登记表与该调用点 |
| Y3 | `role_workbench` 的 `POST …/role-workbench/confirm-warning`：恒 500、前端不调用 | 删除端点（签发清单的确认走 `signoff_checklist`）；若保留则改走 helper |
| Y4 | 迁移落共享库与推送 | 与母 spec X1 同顺序：先 `MigrationRunner(...).run_pending()` 落库，再推送 |
