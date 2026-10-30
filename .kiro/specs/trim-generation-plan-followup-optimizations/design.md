# 设计：程序裁剪 → 生成计划后续优化

## 1. 目标与边界

本 spec 将 `trim-generation-plan-linkage` 的六条后续建议变成可部署代码。顺序按风险而非文件：先消除长事务与不可重放，再让数据库约束身份和当前态，随后拆分类字段，最后建立只读 UAT 与性能裁决。

不做：生成前逐模板细裁、先委派后生成、全平台所有历史 `business_category` 读者一次性重写、常驻分布式 worker、无实测依据的 UI 重构。

### 1.1 关键取舍

| 议题 | 采用 | 否决 |
|---|---|---|
| 两阶段执行 | 持久 operation，同一 HTTP 请求同步跑完；失败后同 id 可恢复 | 进程内 task / BackgroundTasks；先建半成品 WorkingPaper |
| 文件边界 | 同卷 operation staging + manifest + `os.replace` | 直接写正式路径后再补 operation |
| 幂等身份 | 客户端 UUID + canonical request hash | 服务端响应后才分配 id；仅靠“已有编码跳过” |
| scope CAS | 所选编码的 `trimmed` 判定摘要 | 全行 updated_at（无关变化假 stale）；只比 preview id（漏旁路状态写） |
| 分类拆分 | `business_category`=质控分类，现有 `scenario`=业务场景 | 新建第二个 scenario 字段；把 IPO 猜成某个 A 子类 |
| 虚拟化 | 先测 141，连续两轮超硬门才做 | 因总量 1,025 直接虚拟化；引入新依赖 |

### 1.2 数据写入边界

迁移与回填在隔离 PG schema / 临时库验证。共享 `audit_platform` 中真实项目保持只读；如需运行正向迁移，必须先备份并由用户另行放行。浏览器写入只使用【测试】项目。

## 2. 两阶段生成 operation

### 2.1 表结构

`workpaper_generation_operations`：

- `id UUID`：客户端 operation id，主键。
- `project_id/year/actor_user_id/kind/template_set_id/failure_policy`。
- `request_payload JSONB` + `request_hash CHAR(64)`；同 id 不同 hash 返回 409。
- `scope_revision CHAR(64)`；只覆盖本次请求编码的裁剪布尔判定。
- `status`：prepared/materializing/materialized/finalizing/succeeded/partial_failed/failed/stale。
- `lease_token/lease_expires_at/attempt/progress_total/progress_done`。
- `receipt JSONB/public_error TEXT/created_at/updated_at/started_at/finished_at`。

`workpaper_generation_items`：

- `id`、`operation_id`、`ordinal`、`wp_code/wp_name/audit_cycle`。
- 预留 `wp_index_id/wp_id`，保证重入路径稳定。
- `template_source JSONB/template_fingerprint`。
- `staging_path/final_path/file_sha256/from_template/status/error`。
- unique `(operation_id, wp_code)` 和 `(operation_id, ordinal)`。

正式行不增加 provisioning 状态。Phase A 与 materializing 期间，平台其他读取方完全看不到半成品。

### 2.2 请求规范形与状态接口

模板集规范形：`{kind, project_id, year, template_set_id, selected_codes(sorted unique canonical)}`；按编码规范形不含 template set。hash 使用 UTF-8、排序键、紧凑 JSON 的 SHA-256。

现有两个 POST 增加可选 `operation_id`。前端必须发送；内部旧调用方缺省时服务端生成。正常同步完成仍返回现有 `GenerationReceipt` 字段，并附 `operation_id/status`，不破坏旧调用方。

新增：

- `GET /api/projects/{project_id}/working-papers/generation-operations/{operation_id}`：状态、进度、terminal receipt、是否可恢复。
- POST 同 id 是唯一恢复入口：terminal 返回原 receipt；active lease 返回 202；lease 过期原子领取并从 manifest 继续。

状态读取须同时匹配 path project 和 operation.project_id。公开错误不含绝对路径、SQL 或凭据。

### 2.3 Phase A：prepare（短事务）

1. 路由完成年度、项目 edit 权限与各端点原有前置检查。
2. 查 operation：同 hash terminal 重放；同 hash active 返回状态；不同 hash 409。
3. 取 `lock_project_procedure_scope`，调用 `plan_generation` 取锁后现读 scope/wp_index。
4. `scope_decision_revision(scope, requested_codes)` 对每个规范码只记录 `{code, trimmed}`。决定者变化但结果不变不制造 stale。
5. 解析模板集交集、名称、循环、项目模板覆盖和场景，预留稳定 UUID，写 operation/items；不读写文件、不建正式行。
6. commit，释放项目锁。

模板来源身份不在项目锁内做全文件哈希。operation commit 后、任何 staging 写入前，先解析并保存全部来源文件的相对路径、size、mtime_ns 与 SHA-256；此后逐项物化前复核。来源改变则 operation failed/stale，不能混用两个模板版本。

### 2.4 锁外 materialize

staging root：`wp_storage/{project_id}/.generation/{operation_id}/`。目标基础名使用预留 wp_id，扩展名由模板决定。`wp_template_init_service` 与 `wp_generate_file` 增加受控 `target_base_path`，默认值维持旧入口行为。

每项流程：核模板 fingerprint → 写 staging 临时名 → flush/fsync（能力允许时）→ 算 sha256 → 更新 item。模板集 `atomic` 任一失败即清全部 staging 并 failed；按编码 `per_item` 保留成功 item、失败写 item.error。

路径校验只接受服务端构造的 UUID 目录，并用 `Path.resolve().is_relative_to(storage_root)`。禁止按客户端字符串递归删除。

### 2.5 Phase B：finalize（短事务）

1. 原子把 operation 切到 finalizing；取同一项目锁。
2. 重新校验项目未删除/未归档、调用人仍有 edit；重跑 `plan_generation`。
3. 比较 scope revision。不同则 stale，清 staging，正式数据库/文件均为 0。
4. 对已被其他 operation 创建或移入回收站的编码更新 receipt 并丢弃对应 staging；模板集 atomic 仍允许“并发已存在”幂等降级，不把它当文件失败。
5. 以预留 UUID 建 WpIndex/WorkingPaper，绑定 dataset；按编码路径在 staging 上完成表头和 parsed_data，保持原语义。
6. `os.replace(staging, final)`，写 final 相对路径和摘要；flush 后 commit；另一次短事务保存 terminal receipt。

DB/文件无法跨介质原子提交，恢复按 deterministic UUID + manifest 处理：final 文件存在且 hash 一致可继续建/确认行；hash 不同 fail-closed；DB 行已存在且 operation id 对应的 UUID 全匹配则完成回执；不匹配绝不覆盖。

### 2.6 前端恢复

`generationOperationStore.ts` 管理 sessionStorage，键为项目 id，值含 operation id/request hash/request snapshot。点击时先持久化再 POST。网络错误后 GET：active 按 500ms→1s→2s（上限 3s）轮询；terminal 展示原 receipt；lease 过期以同 payload/id 重入。成功、失败确认或明确 stale 后清存储。

组件 open/project epoch 仍是 UI 接纳边界。旧项目 operation 可以继续在服务端完成，但不得 toast、emit 或关闭新弹窗。

## 3. 程序行身份与粗裁当前态

### 3.1 规范化身份

唯一函数 `normalize_procedure_identity(cycle, code, wp_code)` 返回 canonical 字段；init、supplement、custom、custom-with-template、查询和 resolver 共用。迁移先查冲突，存在即 `RAISE EXCEPTION` 并输出项目/循环/编码，不做自动“最新胜出”。

PG 约束：

```sql
CREATE UNIQUE INDEX ... ON procedure_instances
(project_id, upper(btrim(audit_cycle)), upper(btrim(procedure_code)))
WHERE is_deleted = false;
```

另以 CHECK 固定原值 canonical 和非空。SQLite 单测验证 service，PG 临时 schema 验证表达式部分索引。唯一冲突映射 409；初始化并发若冲突，rollback savepoint 后重读。

`delete_custom` 调 SoftDeleteMixin 的能力或显式同时写 `is_deleted=true, deleted_at=now()`。自定义编号继续扫描含已删行，不复用编号。

### 3.2 确认投影

`procedure_trim_cycle_confirmations`：复合主键 `(project_id,audit_cycle)`，另含 `source_preview_id`、`confirmed_by`、`confirmed_at`、`request_id`、`cycle_revision_hash`、`revision_no`、timestamps；cycle 有 canonical CHECK。

`ProcedureOperationPreview.consume_and_apply` 的 apply_fn 成功返回后、preview 标 consumed 的同一事务中，根据 canonical request 中 scope entries 分组：每个 cycle 对 `{code,status,skip_reason}` 排序求 hash，再 upsert、revision_no +1。row-only 不写。

迁移回填以 `(consumed_at,id)` 作为稳定顺序。切换前的 verifier 同时运行旧扫描和投影读取，逐项目逐循环比较 confirmed_at/by；不一致抛错。上线后 `load_cycle_confirmations` 只查投影并 JOIN actor 名称，历史 preview 不删。

**实施补记（2026-10-29，代码为准）**：

- 迁移号：投影原计划写在 V217 后半部分。开发中的 V217 于 04:36 UTC 被登记进共享开发库（当时只有身份约束部分，来源未查明：开发服务热重载不跑迁移、日志里也没有启动迁移记录），之后再往 V217 追加内容不会在该库执行。因此投影独立为 **V218/R218**；V217 只修了一处真缺陷（三个 CHECK 的存在性按全库 `pg_constraint` 名字查，被 public 的同名约束骗过、随机 schema 里不建约束，改为按本表 `conrelid` 查）并登记 `migration_drift_ledger`（逐对象核验 public 效果一致）。迁移拆分清单因此是 V216 生成 operation / V217 身份约束 / V218 确认投影 / 分类迁移顺延为 V219。
- 写入：`consume_and_apply(after_consume=record_confirmations)`，凭证置 consumed 并 flush 之后在同一事务写；幂等重试分支直接返回旧结果、不调用。`record_confirmations` 只读凭证快照（与回填同一输入），单条多行 `INSERT … ON CONFLICT DO UPDATE`：`revision_no` 恒 +1，来源 / 操作人 / 时间 / 请求号 / 指纹只在本次 `(consumed_at,id)` 更大时覆盖 —— 投影是已消费凭证集合的纯函数，与提交先后、时钟偏差无关（并发由主键行锁串行，粗裁 apply 另有项目咨询锁）。
- 指纹：每循环 `[编码, 目标状态, 理由]`（非字符串记空串）按码点排序后 `json.dumps(ensure_ascii=False)` 再 SHA-256；SQL 用 `jsonb_agg(jsonb_build_array(...) ORDER BY ... COLLATE "C")::text`，两者逐字节一致（PG 用例含引号 / 反斜杠 / 换行 / 制表 / 控制字符 / emoji）。循环只认字符串、去首尾空格后大写、超过 10 个字符忽略。
- 自检：V218 回填后用 `DISTINCT ON` 另写一遍期望集合，与表做双向 `EXCEPT`，不一致 `RAISE`（整份迁移回滚）。运维对拍：`backend/scripts/check/check_trim_confirmation_projection.py`（READ ONLY；0 一致 / 1 不一致 / 2 未应用）。旧读法不归一循环、不挑字段类型，只在非规范 / 损坏条目上与投影不同，校验器把这类差异列为不一致、由人判断。
- 外键：`source_preview_id` → 预览凭证 `ON DELETE RESTRICT`（凭证是不可变真源，删凭证必须先删投影；`scripts/e2e/procedure_e2e_live.py` 的测试项目重置已先删投影）；`confirmed_by` → users `RESTRICT`；项目 `CASCADE`。去掉了原 ORM 草稿里无读者的 `(project_id, confirmed_at)` 索引。

## 4. 项目分类单一来源

### 4.1 模型

继续使用 `projects.business_category` 和 `projects.scenario`，不新建同义列：

- category：NULL / A / A1~A8 / B / B1~B6 / C；group 取首字母，但只在 resolver 内。
- scenario：normal / ipo / listed / refinancing / transfer / restructure / fraud_response。

`ProjectClassification` 是不可变 DTO：`category_code/category_group/defaulted/scenario/is_ipo/is_refinancing/is_capital_market`。defaulted 只表示缺分类时生成计划按 C，不把 C 写回数据库。

迁移建 backup 表保存被改行的原 category/scenario；legacy IPO/refinancing 仅在 scenario=normal 时搬入 scenario，category 清 NULL。若 scenario 已有非 normal 且冲突，迁移 fail-closed。R 只根据 backup 且现值仍等于迁移目标时恢复，避免覆盖迁移后的人工修改。

### 4.2 写读链

`BasicInfoSchema`、`ProjectCreateResponse`、wizard store 与 BasicInfoStep 增加两个字段并做枚举校验。界面：

- 原“业务类型”改名“报告模板类型”，仍写 company_subtype。
- “质控业务分类”只提供 A/B/C 组级选择；已有详细 A1~B6 读回时保留并显示，不擅自改子类。
- “专项场景”提供登记值；项目类型选 IPO 时只给建议，不暗改用户已确认值。

`business_category_service.project_category` 改用 resolver；模板/生成场景读取改用 resolver。全仓旧直接读者按风险迁移：本次写路径和模板适用性全部改；纯展示/历史兼容登记 AST 棘轮，只许减少。行业误用另以明确 `industry` 来源替代，不继续把 category alias 成 industry。

客户端传 category 的 review/procedure-table 路径改为服务端项目值；如需测试 override，仅测试内部函数参数可用，不暴露生产 query。

**实施补记（2026-10-29，代码为准）**：

- 解释入口 `app/services/project_classification.py`：`resolve(分类, 场景, 报表模板)` 读取用、永不抛错；`normalize_category` / `normalize_scenario` 写入用，未登记值抛 `ClassificationValueError`（路由 422）。DTO 比 4.1 多一个 `tags`（适用性标签 = 场景标签 ∪ 参考标准里语义等价的细分类 A1/A7→listed、A2→ipo、A3→restructuring、A4→refinancing、B1→neeq ∪ 上市公司报表模板→listed），`is_ipo` / `is_refinancing` / `is_capital_market` 由标签推出，`flags()` 供模板 `applicable_when.business_category`。细分类等价只用于判定，不反向把 IPO 场景写成 A2。
- 迁移前后判定一致：resolver 认得旧值（分类列里的 IPO / refinancing 在场景仍为 normal 时按场景解释），V219 前后同一项目判定不变；PG 用例对共享库全部项目只读复制后逐行验证。
- 切到 resolver 的读者：生成计划分类、`get_category_prefix`、`business_category_flags`、chain_orchestrator、render-config 适用性、RenderContext（新增 `project_classification` 与 `project_classification_of(ctx)`）、D4（用自己查的项目行算分类，project_context 带 `project_classification`）、F2、A16 模板选择、A17-5、B60、模板填充、向导推荐、standard_unification、生成场景（`SCENARIO_TO_FILE_FILTER` 补 refinancing）、模板列表、复核清单。`wp_procedure_tables` / `review_workflow` 的客户端分类 query 删除。render-config 响应不加 `project_classification`（无消费方）。
- 写读链：`_sync_basic_info_to_project` 按 `model_fields_set` 写，旧客户端不发这两个键时不改库；创建 / 详情响应回规范值与 `project_classification`。前端 `@/types/projectClassification` 的选项与后端逐值对拍（`test_project_classification.py`）；`isIpoProject` 收对象入参时按标签精确匹配；向导三项为「报告模板类型」（company_subtype）、「质控业务分类」（组级选择，已有细分类原样保留显示）、「专项场景」，只给建议不自动写入。
- 约束与迁移：ORM 两个 CHECK + V219（预检 fail-closed、备份表 `project_classification_v219_backup`、去掉分类默认值 'C'、约束存在性按本表 `conrelid` 判断）；R219 只恢复现值仍等于迁移结果的行。
- 棘轮（只许减少）：后端 `tests/test_business_category_direct_readers_ratchet.py`（AST，基线 129 文件 / 577 处，大头是 70 余个 AI 生成与渲染策略里的项目上下文透传）；前端 `src/__tests__/businessCategoryReaderRatchet.spec.ts`（TS AST + 模板，24 文件 / 34 处）。
- **V219 已被别的进程在共享库执行（不是本会话执行的）**：本会话没有对共享库跑 V219（它会改真实项目「重庆和平药房连锁有限责任公司_2025」：分类 IPO→NULL、场景 normal→ipo，判定不变）。但 2026-10-29 08:00 UTC 另一会话起了一个挂载本工作树 `backend/` 的后端容器，应用启动按惯例跑工作树里全部待执行的 `V*.sql`，V219 随之执行（启动漂移检查日志 08:00:35 起出现 `project_classification_v219_backup` 的 db_extra 记录）；V217 早先 04:36 UTC 被登记，多半是同一机制。备份表在库里，R219 可按「现值仍等于迁移结果才恢复」回退；但只要 V219 文件还在 migrations 目录，任何一次应用启动都会再执行它。教训：未经放行的数据迁移不能留在共享工作树的 migrations 目录里。
- 范围外登记（未改）：①行业误用：H5 / H7 渲染策略与 H7 服务把 `business_category` 当行业读，适用行业集合是 oil_gas / agriculture 等行业名，分类码永不命中 ⇒ H5 对所有项目返回 industry_error、H7 恒「不适用」（共享库 H5、H7 各 3 份底稿）；`/api/h5/industry-check` 查不存在的 `projects.industry` 列必 500，且只校验登录。平台没有行业来源（projects 无 industry 列、向导无行业字段），需另立 spec 定来源。②前端按精确码 / 首字母判组别的旧读者（WpPopupSigning `=== 'A'`、WpPopupChecklist、GtA17Bundle `charAt(0)`）对细分类判错（A1 项目不算 A 类），已冻结进前端棘轮，待逐个改读 `project_classification.category_group`。

## 5. 只读 UAT 安全基座

### 5.1 账号工具

`backend/scripts/e2e/provision_readonly_uat_user.py` 默认只报告。apply 要求：`--project-id`、`--username`、`--apply`、`--confirm-project-id` 完全一致；密码从 `GT_READONLY_UAT_PASSWORD` 或 `getpass` 读取。

工具只允许：创建/复用 `User(role=readonly,is_active=true)`，创建/复用 `ProjectUser(role=readonly,permission_level=readonly)`。发现同名账号角色不符、成员权限高于 readonly、项目删除/归档则拒绝。`--revoke` 只软删这条成员并停用该专用用户。全程单事务，不创建 staff/assignment，不触碰业务数据。

### 5.2 浏览器防火墙

新增 `playwright.readonly-uat.config.ts` 与 `e2e-readonly/fixtures/readonlyUatGuard.ts`。测试使用独立 BrowserContext，`serviceWorkers:'block'`，在建 page 前安装 context route 与 WebSocket block。

- 登录 POST 是唯一控制面例外，使用独立 APIRequestContext 完成；业务 page 建立后所有 POST/PUT/PATCH/DELETE/WS 一律 abort 且记录。
- API GET/HEAD 采用显式 allowlist；未知 API GET 也 abort，防“名为 GET 的副作用”。静态资源只允许 127.0.0.1 Vite 必需路径。
- `attemptedWrites` 非空即失败，即使请求已 abort；popup 继承 context guard。
- trace/screenshot/video 全关，避免真实项目内容落盘；配置无 globalSetup、无 seed、workers=1/retries=0。

前端 `usePermissionMatrix` 显式加入 readonly，`toMatrixRole` 不再把未知/readonly 降为 assistant。未知角色采用最小只读矩阵，不能放大权限。

**实施补记（2026-10-29，代码为准）**：

- 账号工具只写 `users` / `project_users` 两张表（PG 用例按语句捕获逐条核对）。多了 `--scope-cycles`：只读成员没有团队分配时有效范围为空、看不到任何底稿（`wp_visibility.effective_scope` 受限口径），工具不建团队分配，改为显式写这条成员行的 `scope_cycles`（不给则不改）。复用同名只读账号要校验密码（工具不重置密码，损坏的哈希按不符）；并发创建同名账号靠唯一索引兜底，后到的整体回滚并拒绝。`--revoke` 软删本项目只读成员行并停用账号，账号还在别的项目有成员行时回执里列出。
- 服务端零写入证据：`scripts/check/check_readonly_uat_writes.py`（只读事务）统计审计中间件给该账号记的成功写请求（`logs` 表；GET 与登录 / 刷新不记）。
- 前端：`readonly` 进 `Role` 与权限表（只能查看）；未登记 / 空角色兜底 `readonly`，只认映射表自有键（`constructor` / `__proto__` 不当角色）；操作码级 `can()` 仍镜像后端 `ROLE_OPERATIONS`（后端没有 readonly ⇒ 只读角色没有操作码）。
- 防火墙细节：放行走 `route.fallback()`；Vite 热更新 WebSocket（同源、根路径、带 token）单独记 `blockedInfra`，不算写入；Playwright 的 `serviceWorkers:'block'` 是把 `register` 换成空实现（照样 resolve，但不返回注册对象），测试按「注册结果 + 已注册列表」判定，并用测试进程内的临时 HTTP 服务做可注册的对照。
- 实测发现（范围外，未改）：生成弹窗打开时 `listGenerationTemplateSets` 先 POST `/api/template-sets/seed`（幂等初始化内置模板集）⇒ 只读走查若打开生成弹窗会被记为写入尝试（后端对只读账号拒绝、前端吞掉）。默认走查页面不打开该弹窗。
- `e2e-readonly/` 必须在 `vitest.config.ts` 的 exclude 里（vitest 的 include 是 `**/*.spec.ts`，会把 Playwright 用例当单测跑、整文件报错）；守卫 `src/__tests__/playwrightDirsExcludedFromVitest.spec.ts` 要求每个 `playwright*.config.ts` 的 testDir 都被排除。
- 未做：真实项目只读走查 `e2e-readonly/readonlyUat.spec.ts` 没有跑——需要用户指定项目并放行在共享库建账号（provision `--apply`）。
- 勘误（2026-10-29，spec `trim-followup-residual-findings-closure` R2）：上面「后端对只读账号拒绝」不成立——当时 `/api/template-sets/seed` 只校验登录，只读账号打开生成弹窗也会真写（幂等，编码不变时不改行）。已改：弹窗只发 GET，内置集由启动任务 `seed_builtin_template_sets` 初始化，手动端点限 admin / partner。

## 6. 明细性能裁决

新增独立、全 mock 的 `generation-plan-dialog-perf.spec.ts`，不访问共享 PG。fixture 覆盖 141/250/500/1025 项和“单组/每项一组”两种形态；必须断言节点数，避免空跑。

记录 20 次热态和至少 5 次冷态的 median/p95/max、Long Task、DOM 节点与滚动 RAF。共享 CI 只把 141 档硬门作为发布判据；压力档输出曲线。

ROI：当前单展开最大 141，且没有性能红证据。预估改动为 1 个新明细组件 + 模型扁平化 + 4~6 个测试文件，风险是动态高度、tooltip 与键盘可访问性回归。只有连续两轮 141 档超硬门时收益才高于风险；否则 task 记录实测“不实施”，这仍是完成裁决，不是假绿跳过。

若需虚拟化，阈值从曲线拐点取且至少 250；使用 `element-plus/es/components/virtual-list` 的 DynamicSizeList 或固定单行布局。循环汇总、checkbox 和单展开状态不变。

**实施补记（2026-10-29，代码为准）**：

- 夹具页 `e2e/perf-harness/generation-plan-dialog.html`（Vite 开发服务直接提供、不进生产构建，只挂生成计划弹窗，接口由页面路由应答）；专用配置 `playwright.perf.config.ts`（没有 globalSetup：主配置的 globalSetup 会往共享库播种）。「单组」= 全部底稿由同一条程序行决定，「每项一组」= 每个底稿一条程序行（分组标题最多，最坏情况）。
- 测量口径修正：最初在 `page.evaluate` 里 `button.click()`，CDP 求值里的同步工作不计入 Long Task（自检的 140ms 忙等抓不到）⇒ Vue 同步渲染整段漏测。改为 Playwright 真实点击 + 捕获阶段监听记 `event.timeStamp` + 两帧 RAF；自检用同一路径验证能抓到 >100ms 的长任务和计时。也去掉了 serial 模式（一档超门不能让后面的档跳过）。
- 四轮结果（桌面 / 窄屏 × 单组 / 每项一组）：141 档展开 p95 59~112ms、max ≤ 120ms、滚动 60 FPS、p95 帧 16.8ms；最长 Long Task 57~97ms，只有第 2 轮（开跑前 CPU 负载 74%，同机有别的会话的全量测试）窄屏「每项一组」为 115ms 超门，其余三轮全过 ⇒ 没有连续两轮超门，**不实施虚拟化**。展开基本是一整个长任务，所以「无 >100ms Long Task」是最先触到的门。
- 容量曲线（低负载的第 3 轮）：250 档 p95 96~160ms、长任务 94~157ms（「每项一组」已超 100ms）；500 档 p95 183~334ms；1025 档 p95 345~726ms、长任务 708~827ms。若以后单循环到 250 项以上（或接近一项一组），按 250 起实施明细虚拟化。
- 未接入 CI（CI 只跑 render-smoke 那组 Playwright）；结果文件写在已忽略的 `test-results/perf/`。

## 7. 迁移与文件计划

实施前再次现扫最高版本，分配连续三组 V/R：

1. generation operation/items；
2. active identity + cycle confirmation 投影和回填；
3. category/scenario backup、搬迁与 CHECK。

主要新增文件：

- `app/models/wp_generation_models.py`
- `app/services/wp_generation_operation_service.py`
- `app/services/project_classification.py`
- `scripts/e2e/provision_readonly_uat_user.py`
- 对应 migrations/tests/contracts
- `frontend/src/services/generationOperationStore.ts`
- `frontend/e2e-readonly/fixtures/readonlyUatGuard.ts`
- `frontend/playwright.readonly-uat.config.ts`
- `frontend/e2e/generation-plan-dialog-perf.spec.ts`

主要修改文件：`wp_template.py`、`template_engine.py`、`wp_generate_file.py`、`wp_template_init_service.py`、`procedure_scope_retention.py`、`procedure_trim_service.py`、`procedure_generation_plan.py`、`procedure_models.py`、`core.py`、wizard schema/service/store/BasicInfoStep、GenerationPlanDialog/API、权限矩阵及契约导出。

## 8. 验证矩阵

| 风险 | 必须有的证据 |
|---|---|
| 项目锁仍覆盖文件 IO | barrier 挂起 materialize 时，另一事务能完成 scope lock；旧实现反向变异打红 |
| response lost 重复生成 | 同 id 同 payload terminal 逐字段同 receipt；不同 payload 409 |
| 崩溃留下孤儿 | staging 中断、rename 后 commit 前、commit 后响应前三窗口恢复测试 |
| scope 陈旧 | Phase A 后改影响所选码的状态，finalize stale 且正式三方为 0 |
| 并发生成同码 | 两 session 最终一个 active WpIndex/WorkingPaper，两个 operation 均有确定回执 |
| 身份重复 | 大小写/空白/循环变体 PG 约束打红；软删与 active 语义明确 |
| 投影漂移 | 回填前后 54 条 consumed preview 全量对拍；no-op apply 仍确认 |
| 分类误迁移 | NULL/C/A1/IPO/refinancing/冲突矩阵；R 不覆盖后续人工修改 |
| readonly 误放权 | readonly/read 成功，review/edit 403；HTTP 写和 WS 变异均被浏览器守卫抓住 |
| 性能假绿 | fixture 节点数、detail=1、observer 有样本；删除展开动作后测试必须红 |

磁盘变异不得改被测生产函数为测试拷贝。DB/文件故障注入放下一层，逐次恢复 sha256。PG 用例在隔离 schema/事务中运行，不写共享真实项目。

## 9. 已知风险与降级

- 没有常驻 worker：进程崩溃后 operation 需客户端以同 id 重入；GET 会给出 `resumable_after`。这比现状可恢复，但不是无人值守队列。若以后要求离线批量，再以同表接 durable worker。
- 模板集路径不填表头，按编码路径填表头，继续保持；收敛 service 不能“顺手统一”。
- DB 与文件系统没有真正两阶段提交，deterministic ids + manifest + hash + 重入是补偿机制；任何不确定状态都 fail-closed，不自动覆盖文件。
- 分类旧读者数量较多。本轮以 resolver、核心写路径和棘轮收口；不能为了清零扫描在不了解业务语义时批量替换。
- 只读 UAT 工具不会在共享库自动创建账号。代码和隔离测试完成后，真实项目 UAT 仍需用户给出目标项目与凭据并显式 apply。
