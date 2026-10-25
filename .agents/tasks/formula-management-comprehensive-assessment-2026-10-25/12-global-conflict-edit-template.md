# 角度 C：全局设置、项目适配、冲突确认、二次编辑与公式模板复用审计

> 审计日期：2026-10-25。代码基线：`779d8b43619c5946c198e11ca35b1ad9330c5dfa`。范围严格限于只读调查；仅新增本报告，未改生产文件、数据库业务数据、测试或 Git。数据库证据均为 `SELECT`，运行态证据仅取本机 OpenAPI。因测试运行可能写 `.pytest_cache`、快照或缓存，本步未执行 pytest/vitest，只检查既有测试源码。

## 0. 证据等级

- **[E1]**：当前生产源码调用链与 live PostgreSQL/OpenAPI 相互印证。
- **[E2]**：当前生产源码、路由注册、前端真实挂载和请求契约闭合，但 live 库没有可用业务样本。
- **[E3]**：既有自动化测试或历史说明；本步未执行，不能替代当前运行实证。
- **[E4]**：由静态结构推得的风险，需要写入型 UAT 或故障注入最终确认。

## 1. 核心 verdict

| 问题 | 结论 | 证据 |
|---|---|---|
| 全局设置是否真实存在 | **真内核、真迁移、真 API、真 UI，但不是全域闭环。** V199 建立统一设置/发布/待确认/模板/订阅模型；7 个域都被 API 声称为 `wired`。报表、表间审核、附注、合并附注、推送有真实消费者；`tb_detail` 没有自动业务消费者，`wp` 的全局继承只覆盖初始化/重新预填，公式 runtime 与循环 Tier A 明确不读全局层。 | [E1/E2] |
| “一处改应用到全部” | **后端同步内核可遍历匹配项目，但前端项目保存后只在 report/tb_detail/cross_check 3/7 个域弹应用范围；wp/note/consol_note/push 没有同一路径。** 模板订阅项目还会刻意跳过全局变化。 | [E2] |
| 冲突弹窗是否真实 | **真实挂载且契约基本吻合。** 全局发布、模板发布、订阅/退订、项目间应用共用三方比较和逐项/批量决策；项目顶栏有常驻待确认角标。存在项目间推送无版本令牌、跨域决策键缺 domain、历史时间轴静默空转等缺口。 | [E1/E2] |
| 用户二次编辑 | **混合。** 报表、底稿、附注、表间审核、TB 明细、推送均有某种编辑入口；底稿/附注保存能进入执行链。TB 明细只进入公式中心手工执行，不进入 TB/四表/底稿自动生成链；合并附注只有模板级编辑，没有正常项目适配编辑入口。 | [E2] |
| 公式模板是否是真模板 | **代码层是真模板，不是 UI 空壳。** 有版本快照、四级可见性、订阅、升级、冲突、退订及设为全局；与全局发布共用同步内核。可是 live 六张 V199 业务表全空，尚无任何真实模板、版本、订阅或发布记录，因此只能判“已实现但未被现场使用/验收”。 | [E1/E2] |
| 模板与全局设置是否联动 | **单向强、反向弱。** 模板→项目、模板→全局复用同一内核；全局→模板只生成 `global_hints`，模板不会自动跟随，订阅项目也跳过全局更新，须模板所有者手工“并入模板”再发版。 | [E2] |

**总判定：平台已经有一套可信的公式治理骨架，但还不能称为“贯穿全平台的一处修改、全域生效”。更准确的状态是：真治理内核 + 部分真执行接线 + 多处 UX 假入口/命名混淆 + live 零采用。**

## 2. live 数据事实基线

采样库为 `audit_platform`，V199 在 `schema_version` 中已登记：文件 `V199__formula_global_settings_and_templates.sql`，checksum `fe8d3a…c99ee`，应用时间 `2026-10-25 05:50:46+00`；`schema_migration_failures` 无 V199 失败。[E1]

- `formula_setting / formula_sync_item / formula_publish / formula_template / formula_template_version / formula_template_subscription`：**六表全部 0 行**。
- `report_config`：1191 行，项目层 `project:{id}` **0 行**，全局行 1191；有任一公式字段 318 行；`formula_version` 全为 1；`base_version`、`pinned` 均 0。
- `wp_formula`：29 行，全部 `custom/saved`，只覆盖 1 个项目、29 张底稿；`base_version` 和 `pinned` 均 0。
- `disclosure_notes`：1090 行，带 `_user_formulas` 0，带 `_user_formulas_origin=formula_settings` 0。
- `consol_note_formula`：51 行，全部 soe/seed/live，版本均 1。
- `audit_log_entries(action_type='formula.changed')`：1 行，其中 formula-settings `operation` 记录 0。
- 活跃项目 85 个；合并项目仅 1 个；`template_type IS NULL` 76 个，`report_scope IS NULL` 73 个，两者都空 73 个。代码会把空值默认解释为 `soe_standalone`/`soe`。

这说明迁移和旧全局配置已在库，但 V199 的项目适配、冲突、发布、模板、订阅尚未产生任何现场数据。后续所有“真实可用”结论必须保留这一限制。

## 3. 全局公式设置的真实模型

### 3.1 持久化、迁移、服务和 API

**持久化层 [E1/E2]**

- `backend/migrations/V199__formula_global_settings_and_templates.sql` / `R199__...sql`：新增六表，并给 `report_config`、`wp_formula`、`consol_note_formula` 增加版本/基线列。
- `backend/app/models/formula_setting_models.py`：
  - `FormulaSetting`：`global/project/template` 三种物理层，键为 domain + owner + slot。
  - `FormulaSyncItem`：`pending/resolved/superseded`，决策 `adopt/keep/custom`。
  - `FormulaPublish`：全局、模板、指定项目的发布/候选记录，`request_id` 唯一。
  - `FormulaTemplate/Version/Subscription`：模板元数据、冻结快照、项目按域订阅。
  - `ProjectBaselineColumns`：`base_version/base_definition/pinned/base_origin/base_template_id`，用于三方比较。
- 报表两层仍在 `report_config`；底稿项目层仍在 `wp_formula`；合并附注全局层仍在 `consol_note_formula`。V199 不是把全部域搬进一张表，而是用 `DomainStore` 统一接口包住多种存储。
- 服务主链：`definitions.py` → `stores.py/domain_stores.py/push_settings.py` → `effective.py` → `sync.py` → `engine.py` → `publish.py/project_ops.py/template_sync.py` → `propagation.py`。
- 路由：`backend/app/routers/formula_settings.py` 和 `formula_templates.py`，已由 `router_registry/report.py` 注册。
- live OpenAPI 确认 28 条治理路径存在：global/preview/publish、publishes、candidate preview/review、effective/overrides/apply、pending/resolve、template CRUD/version/subscriber/promote、subscription/preview/unsubscribe 等。[E1]

### 3.2 实际继承优先级

业务语义是 **本项目适配 > 订阅模板 > 全局 > 系统预设**，但物理读取不是四表联查：[E2]

1. 模板订阅会把模板定义**物化为项目行**，并记 `base_origin='template'`、`base_template_id`；
2. `effective_slots()` 实际只读“项目行 > 全局精确 scope > 全局 `*` > 系统预设”；
3. `layer_of()` 再依据项目行基线把它标为 template/project/pinned/global；
4. 全局发布看到项目行来自模板时用 `TEMPLATE_SKIPPED` 跳过，所以模板定义的 slot 不随全局自动改变；
5. 模板未定义的 slot 仍从全局/预设继承。

因此“模板层优先于全局”成立，但靠项目物化副本实现。模板升级、退订、恢复全局都必须维护这些副本与基线，不能把 `formula_setting.layer='template'` 误当成执行时直接读取层。

### 3.3 系统预设并非统一一层

| 域 | 系统/最低层真实来源 | live/静态规模 | 是否进入统一 `system_presets()` |
|---|---|---:|---|
| report | `report_config` 本身就是全局行；没有更低的独立 preset | 1191 行，318 行有公式 | 不适用 |
| tb_detail | 前端按科目动态拼 `TB(code,'期末余额')` | live `formula_setting` 0 | **否，后端不知道这些默认公式** |
| cross_check | 7 条内置勾稽与静态目录，用户规则另存 | live `formula_setting` 0 | **否** |
| wp | `backend/data/prefill_formula_mapping.json` | 306 mapping、1390 个可编辑 preset slot、89 个 wp_code | 是 |
| note | 每张附注 `table_data._formulas` / generator | live 1090 张附注目前均无 `_formulas/_check_presets` | **不进 effective_slots，列表阶段另行合并** |
| consol_note | `consol_note_formula` 就是全局层 | 51 行 soe seed | 作为 global |
| push | `formula_push_rules.json` | 375 条、78 个 wp_code，其中 87 条公式源、172 条 system/derived 不可停用 | 是 |

这个分裂直接影响“保存全部有效公式为模板”：TB 动态默认和附注表内 preset 不会被后端 effective API 枚举，故“全部”并不覆盖这两类。

## 4. “项目公式为空”的实码语义

“空”不是统一语义，不能用一句“空则回退全局”概括：[E2]

| 场景 | 实际行为 |
|---|---|
| 项目没有该 slot 的本地行 | 回退订阅模板物化层/全局/系统预设。 |
| 删除项目 override（`DELETE .../overrides?slot_key=`） | 删除项目行；若来自订阅模板则重写为模板当前定义，否则回到全局/预设。 |
| report 项目行 `formula/aje_formula/rje_formula` 全空 | `disabled_as_empty=True`，**停用，不回退**；项目行仍存在。 |
| 通用域 `{disabled:true}` | 明确停用；`None` 只表示“这一层没有定义”。 |
| tb_detail 的 `formula:''` | 仍是一条 live 项目定义；UI 显示空公式，不自动回退，也不被标为 disabled。 |
| cross_check 左/右为空 | 仍保存为规则，执行时失败并报“未填写”。 |
| wp 空表达式或 disabled | 空表达式校验拒绝；`WpStore.write_project()` 对 disabled 直接跳过，**底稿域没有停用能力**。已有本地公式不会因此被移除。 |
| note 清空一条 | 保存请求过滤空行；本地独有行会删除、全局行会写 disabled。但表内 `_formulas` preset 不在 effective 上游里，清掉项目行后 preset 会重新出现。 |
| push | 只允许 `{disabled:true}`；system/derived 策略的 172 条规则禁止停用，editable 规则可停用。 |
| consol_note | `{disabled:true}` 会从该项目有效单元格集合剔除，行为成立。 |

最需要产品文案纠正的是 note 与 wp：统一设置页会把 `disabled` 描述成通用能力，但 note 的内置表格公式和 wp 项目公式并不遵循同一停用语义。

## 5. UI 与 API：全局设置是真入口，但首建能力不完整

- 全局页面 `FormulaGlobalSettings.vue` 已注册到 `/settings/formula-global`；`ThreeColumnLayout` 导航与 `FormulaSettingsToolbar.openGlobalSettings()` 均可进入。[E2]
- 页面按 domain/scope 调 `GET /api/formula-settings/{domain}/global`，管理员暂存后依次调 preview、publish；非管理员只读。
- `FormulaDefinitionEditDialog` 只编辑**已有列表行**。全局页没有“新增公式位”按钮；API 虽可发布不存在的 slot，UI 做不到首建。
- 结合 live 数据与 preset 枚举，当前页面可列出 report 1191 行、wp 1390 个 preset、push 375 条、consol_note 51 行；tb_detail/cross_check/note 的统一全局列表为 **0**。后三域管理员在全局页看到空表，也没有新增入口。
- report 的结构行已经存在，所以可在空公式行上首填；wp/push 可在系统 preset 上建立全局覆盖；tb_detail/cross_check 可先在项目新增后由“设为全局”绕行；note 的项目保存不弹应用范围，只能再保存成 V199 模板并 promote，路径明显不对称。
- `FormulaDefinitionEditDialog` 只有必填校验，无地址选择、语法解析、调试或引用存在性校验。后端仅 wp/push/note/consol_note 的 store 有域级校验；report/tb_detail/cross_check 的统一发布与项目 override 没有语法/悬空引用硬门。
- 全局页显示 7 域均 `wired`，但这个标志是常量 `WIRED_DOMAINS`，不是运行时能力探测。

### 5.1 项目保存后的“应用范围”真实覆盖

`FormulaSettingsToolbar` 与 `FormulaApplyScopeDialog` 已真挂在 `FormulaManagerDialog`；后端 apply API 对 7 域通用。但生产调用 `askApplyScope()` 的保存链只覆盖：[E2]

1. report：`saveReportRowDraft()/onSaveAllFormulas()`；
2. tb_detail：`useTbDetailFormulas.persist()`；
3. cross_check：`useCrossCheckRules.persist()`。

wp 保存、`NoteFormulaDialog`、`FormulaPushPanel.saveRule()`、`ConsolFormulaManagementPanel` 均不调用该交接。因此项目用户改完这 4 域看不到“设为全局/提交候选/应用到指定项目”。这不是后端缺 API，而是前端保存链没有接上。

## 6. “一处改应用到全部”的域级真相

| 域 | 有效定义消费者 | 发布后动作 | verdict |
|---|---|---|---|
| report | `load_effective_report_configs()` 被 `ReportEngine`、`trial_balance_service`、合并报表读取方、公式引用检查消费 | 行闭包标 stale；有年度则重算并发 `REPORTS_UPDATED` | **真接线** [E2] |
| cross_check | `run_user_rules()` 被 `formula_management.logic_check.execute_report_cross_checks()` 调用并落 `cross_check_results` | 重新执行全部内置+用户勾稽 | **真接线** [E2] |
| note | `materialize()` 把有效集写入 `_user_formulas`，`execute_note_formulas()` 与模板 `_formulas` 合并执行 | 物化所有年度、标章节 stale | **真接线，但无法停用同格模板 preset** [E2] |
| consol_note | `effective_formulas()` 被 `consol_note_formula_service` 填数路径调用 | 按章节 `fill_note_sections()` | **真接线，但项目范围筛选错误** [E2] |
| push | `formula_push.engine.run()` 调 `effective_push_rules()` | 受影响 wp_code 重新推送 | **单体真接线；合并项目显式 skip** [E2] |
| wp | `init_prefill_overrides()`、`overlay_prefill_formulas()` 被初始化/重新预填调用 | 对对应 wp_code 标 `prefill_stale` | **部分接线。`wp_effective.py` 明文确认 formula_runtime 与循环 Tier A 只读 wp_formula，不读继承的全局层** [E2] |
| tb_detail | 生产后端只有 `tb_detail_formulas` 路由调用 `tb_detail.load/save`；没有 TB、四表、预填或生成服务读取 | 把项目全部底稿标 `prefill_stale` | **治理 CRUD + 手工执行展示，不是自动业务接线** [E2] |

### 6.1 范围计算的两个实质偏差

1. **consol_note 把单体项目也列为受影响项目。** `scope_of()` 对 template_type 域只看 soe/listed，不看 `report_scope`；`list_projects()` 没有 consol_note 特判。live 85 个项目仅 1 个 consolidated，因此 soe 合并附注全局变更会把最多 84 个单体项目也纳入预览/事件/填数尝试。现有 `test_consol_note_effective_and_kernel` 反而用默认 standalone 项目测试，未守“仅合并项目”。[E1/E2]
2. **push 设置对合并项目可继承但不执行。** `propagate_push()` 读到 `report_scope='consolidated'` 直接返回 skipped；所以“全部项目”只表示定义层覆盖，并不表示合并项目结果重算。

此外，76/85 个 live 项目没有 `template_type`、73/85 没有 `report_scope`。`scope_of()` 会把它们静默归入 soe/soe_standalone；发布预览里的“受影响项目”大多依赖默认值，而非已确认项目口径。[E1]

## 7. 发布、版本、事务、重算、审计与回滚

### 7.1 成立的部分

- **CAS**：全局按 slot 版本；项目按本地版本；tb_detail/cross_check/note 的整表保存使用 `L{n}/G{n}` 载入令牌；模板按 aggregate version；缺版本 428、冲突 409。
- **并发锁**：PostgreSQL 用 domain advisory lock；项目写先 domain shared lock，再项目排他锁；模板另有 template lock。
- **幂等**：global publish、项目间 apply、模板 publish/promote 使用 `FormulaPublish.request_id` 唯一重放；前端一次对话固定 `newRequestId()`。
- **事务**：service 只 flush，router 统一 commit；定义、项目副本、pending、publish record 与审计同事务。事件在 commit 后发，避免先通知未提交数据。
- **审计**：`audit_global()` 与 `audit_project()` 统一写 `audit_log_entries` 哈希链；项目操作写 `formula.changed`，保留 operation/source/publish_id/slot 新旧值。
- **失败降级**：报表先提交 stale 再尝试重算；重算失败保留 stale，并写 `stale_degraded_logger`。cross-check 等 handler 失败也记 degraded。

### 7.2 不成立或不完整的部分

- **事件投递无 durable outbox/retry。** `formula_settings` 包内搜索 `outbox/retry` 为 0；`publish_events()` 在定义已提交后逐项目 publish，publish 抛错只写普通 warning，调用方忽略发送数。handler 已收到后失败会有 degraded 记录，但“事件根本没发出”没有可恢复任务。[E2]
- **全局/模板无业务回滚 API。** live OpenAPI 中唯一公式 rollback 是 `/api/formula-audit-log/{project_id}/{year}/rollback`；formula-settings 和 formula-templates 下 rollback/restore 端点为 0。`FormulaTemplateVersion.snapshot` 只供 pinned 订阅读旧版，不提供选择旧版/回滚发版。
- **项目历史回滚不是全域。** `rollback_from_log()` 明确拒绝 cross_check；空公式回滚会被 wp/note 校验挡住；每项目一次超过 30 slot 的审计被聚合成一条，历史页没有逐 slot 回滚入口。
- **删除没有统一回收站。** 全局 setting/template 多为软删，但没有 undelete API；项目 override/`wp_formula` 多为物理删除；custom preset 只有 GET/POST upsert，后端和 UI 都没有 delete/restore。
- **发布记录读取过宽。** `GET /api/formula-settings/publishes` 只要求登录，且同表混有 target=`projects` 的项目间应用记录；响应含 `source_project_id/change_set/note`，没有按项目成员过滤。当前表为 0，尚无 live 泄露样本，但代码会向任意登录用户暴露未来的项目专用公式与备注。[E2/E4]

## 8. 冲突识别、确认弹窗与恢复能力

### 8.1 同步内核的分类与动作

`sync.classify()` 按顺序分为 frozen → inherit → pinned → same → follow → conflict；比较只看 `DomainSpec.exec_fields`，说明字段变化不构成冲突。`base_definition`、本地定义、新上游构成三方比较。[E2]

- inherit：无项目行，默认直接继承；管理员可整项目 defer，系统写旧定义 pinned。
- follow：本地仍等于基线，自动采用新上游并更新基线。
- same：本地已等于新上游，只 rebase。
- conflict：默认 `ask`，写 `formula_sync_item`，不覆盖本地；也可发布时直接 adopt/keep。
- frozen：归档项目不改；必要时写固定旧定义。
- pinned：继续保留旧定义并更新待确认事项。

冲突粒度是 **project × domain × slot_key**；数据库 pending 唯一索引也使用这三个维度。说明字段由 `merge_keep_local_desc()` 保留用户相对基线改过的值。

### 8.2 前端真实接线

- `FormulaPublishPreviewDialog` 真挂在全局发布、候选审核、模板发布/promote、项目应用、订阅/退订流程。
- `FormulaConflictTable` 只列 conflict，展示基线/新上游/项目当前；支持逐条和“全部采用/保留/交项目确认”。
- 同一预览支持逐项目 apply/defer；冻结项目不可选择。
- `FormulaPendingSyncDialog` 真挂在 `ThreeColumnLayout`，`currentProjectId` 来自路由；进入项目自动拉取一次，角标常驻，可按域分组、逐条或批量 adopt/keep/custom。
- 请求契约吻合：前端 `Resolution {item_id,choice,upstream_version,custom_definition}` 对应 live OpenAPI `ResolutionIn`；后端采用/保留/手工修改后返回 `recalc_domains`，前端不会把 keep 误报成已重算。
- 权限主链正确：pending 读 readonly、resolve/subscribe/apply target/override 为 edit；global publish/candidate review 为 admin；模板管理为 owner/admin。[E1/E2]

### 8.3 冲突链的关键缺陷

**C1. 项目→项目推送的 stale 保护失效 [E2]**

`apply_to_projects()` 对 pending 写 `upstream_origin='project'` 且 `upstream_version=None`。前端会原样提交 null；`resolve_items()` 仅在 expected 非 null 时比较版本。若来源项目再次推送并更新同一 pending，旧弹窗点“采用”会静默采用用户未看过的最新定义，而不是 409 刷新。`test_apply_to_projects_inherit_writes_conflict_asks_or_adopts` 正是省略版本完成 resolve，没有覆盖二次推送竞态。

**C2. 多域模板发布的决策键会碰撞 [E2/E4]**

数据库身份含 domain，但 `PlanItem.key`、`Decisions.conflict_choices`、项目应用键均为 `{project_id}|{slot_key}`，不含 domain；`template_sync._apply()` 又把多域 outcomes 放到同一个 dict。若同一模板两个域使用同名 slot，后写结果覆盖前写结果，前端一项决策也会同时命中两域。全仓精确搜索得到 3 个后端构造/消费点和 1 个前端契约说明；现有模板测试只做单域 report 或 tb_detail，没有同 slot 跨域用例。

**C3. “已解决可追踪”界面有三条静默断链 [E1/E2]**

`FormulaTimelinePanel` 已真挂载，但 `formula_timeline_service.py` 的 5 个数据源中 3 个使用不存在字段：

- audit：查 `AuditLogEntry.project_id/created_at`，真实模型只有 payload 内 project_id 与 `ts`；
- publish：查 status=`applied`、`created_at/changes/user_id`，真实约束只允许 published/pending/rejected，真实字段为 `published_at/change_set/published_by`；
- template version：排序/显示 `created_at`，真实字段是 `published_at`。

每个适配器用 broad `except Exception: return []`，所以页面不是报错，而是少事件。live schema 逐列确认上述字段不存在，且库已有 1 条 `formula.changed`，仍会被 audit 分支吞掉。`test_formula_timeline_service.py` 只喂空 MagicMock 或 DB down，恰好把“异常→空”当成功，没有任何真 ORM 行测试。

原始 `FormulaHistoryTab` 仍能查哈希链，但 `specAReady = ref(false)` 被写死，持续向用户显示“哈希链尚未完成/当前是旧表”的过时警告。全仓 `specAReady` 仅此 2 处（声明+使用）。

### 8.4 角色与可见性的偏差

- **合并附注全局写绕过 admin 统一规则。** `consol_note_formula` 已被 V199 定义为 consol_note 全局层，但 `/api/consol-note-formulas` 的增删改和 reseed 使用 `EDITOR_ROLES=['admin','partner','manager']`，并直接调用 `publish_global()`；统一全局页则只允许 admin。全仓 `publish_global()` 有 11 个生产调用点，只有这一 HTTP 家族以更宽角色修改全局层。[E2]
- **合并报表 UI 对非 admin 显示可编辑。** `ConsolFormulaManagementPanel` 的 report 模式操作列不受 `canManage` 控制；manager 的组件测试还 mock 成 PUT 成功。真实 `/api/report-config/{id}` 对 consolidated 全局行 admin-only，因此 manager/partner 点保存会 403。[E2]
- **模板订阅按钮未按 edit 权限门控。** `FormulaSettingsToolbar` 的 `canEditProject` 只传给公式包，订阅按钮始终显示；readonly 成员可打开并走到提交，后端才 403。既有前端测试只覆盖 pending resolve 的 403，不覆盖订阅按钮。
- **发布列表可见性过宽**见 §7.2；模板自身 personal/team/group/firm 可见性和 owner/admin 管理矩阵则实现正确，`test_template_endpoints.py` 也有四范围矩阵。[E2/E3]

## 9. 用户二次编辑：能力矩阵

| 能力 | 实现状态 | 证据与限制 |
|---|---|---|
| 覆盖预设/全局 | 有 | report/tb_detail/cross_check/wp/note/consol_note/push 都能形成项目层；consol_note 没有正常 UI 入口。 |
| 恢复上游 | 部分 | report、push 有明确“恢复全局”；wp 用户公式有恢复预设；note 通过整集差量隐式处理；tb_detail 没有明确恢复按钮。 |
| 停用 | 分域 | report 清空三公式字段；generic disabled；wp 不支持；note 不能压掉同格表内 preset；push 受 policy 限制。 |
| 新增项目公式 | 有但不齐 | report 新行、tb_detail added、cross_check 新规则、wp 单元格、note target、push 只能改既有 rule；consol_note 项目层无直接 UI。 |
| 地址选择器 | 部分 | `FormulaEditDialog` 有 TB/ROW/NOTE/WP/AUX/PREV 等数据源浏览和目标定位；`NoteFormulaDialog` 有 `FormulaRefPicker`。全局/模板的 `FormulaDefinitionEditDialog` 只有文本框。 |
| 语法校验 | 表面多于硬门 | `FormulaInput` 有实时 parser，但主表永远不把 `editingId` 设为非 null，实际点击走大弹窗；保存按钮也不读取其错误状态。report/tb_detail/cross_check 的统一保存无后端 parser 硬门。 |
| 引用存在性 | 部分 | wp 与 note 保存有服务端项目上下文校验；report 旧 PUT 有条件校验，但主项目编辑走 generic overrides，绕开该校验；全局/模板缺项目上下文。 |
| 预览/调试 | 有 | `FormulaEditDialog` 可展开 `FormulaDebugPanel`，报表有 execute/batch execute；全局/模板发布预览只预览影响，不求值。 |
| CAS | 较完整 | global/project/template/note/tb/cross/wp 均有版本机制；项目间 pending 例外见 C1。 |
| 审批/发布 | 分层 | 项目编辑立即生效，无通用复核审批；非 admin 设全局形成 candidate，admin review；模板 owner 可直接发版，无第二人审批。 |
| 审计 | 有 | 变更写哈希链；时间轴坏，且批量 >30 slot 聚合后不可逐条回滚。 |
| 删除/回收 | 不完整 | 无统一回收站；custom preset 不能删；全局/模板软删无恢复；wp 删除物理行。 |

### 9.1 哪些编辑是真执行，哪些只是落库/展示

- **report**：项目公式被 `ReportEngine`、试算表生成和多个 report reader 读取，是真执行。
- **cross_check**：保存规则被 `run_user_rules()` 自动并入报表勾稽，是真执行。
- **wp**：`wp_formula` 的 auto_calc 保存会立即求值，并被 formula runtime、D/F Tier A 等路径读取；全局继承仍有 §6 的缺口。
- **note**：保存后物化 `_user_formulas`，执行器同目标覆盖 `_formulas`，是真执行。
- **consol_note/push**：有效定义被填数/推送引擎读取，是真执行；前者项目 UI 缺失，后者合并项目不执行。
- **tb_detail**：后端生产引用 `formula_settings.tb_detail` 只有 `routers/tb_detail_formulas.py`。公式中心可把返回行送通用 batch endpoint手工求值，但 TrialBalanceService、四表、底稿 prefill 和生成链均不读取这些定义。把它列为 `wired` 会让用户误以为改了科目明细公式就改变 TB 权威数或所有底稿取数。

### 9.2 “可编辑”但实际不完整的入口

**预设库 3/4 挂载点只改内存 [E2]**

`GtFormulaPresetDialog` 在 `FormulaTab`、`NoteTemplateTab`、`ReportConfigTab`、`WpTemplateDetail` 共 4 处生产挂载；只有 `FormulaTab` 监听 `@edit-formula="onSaveCustomPreset"` 并调用 `/api/formula-management/presets/custom`。另 3 处使用默认 `canEdit=true`，用户能点新建/编辑，子组件只 emit 后提示“公式已编辑”，宿主不接事件，刷新即丢。全仓搜索：4 个 mount、1 个 handler。

**“参照已有”后端真有，主 UI 不可达 [E2]**

- `wp_formula` 有 `formula_source/reference_formula_id`，`reference_resolver.py` 会递归解引用、查环和失效依赖；这是实能力。
- 唯一显示 preset/custom/reference 三来源的 `GtFormulaEditDialog` 只挂在 `GtFormulaPresetDialog`；该挂载不传 `wpId`，所以 reference 候选不会加载，restore preset 条件也永不成立。
- FormulaTab 接到保存事件后又丢弃 `formula_source/reference_formula_id`，只把表达式写成平台 custom preset。
- 主 `FormulaManagerDialog` 使用另一套 `FormulaEditDialog`，保存 wp 时不传来源与 reference id。

所以“参照已有公式并保持引用关系”当前是 **后端可用、前端主流程不可用**，不能按组件存在判完成。

**实时语法提示不是保存门 [E2]**

`FormulaManagerDialog` 模板包含 `FormulaInput`，但全文件对 `editingId.value` 的赋值只有置 null，没有任何赋 row.id；行点击统一进入 `FormulaEditDialog`。后者 `onSave()` 直接 emit，甚至可把多条表达式用换行拼成一个公式。wp 后端能挡大部分坏式，note 能挡悬空引用；report/tb_detail/cross_check generic store 会接收。现有 UI 测试主要检查组件渲染/请求次数，没有“解析红时保存按钮必须拒绝”的跨层契约。

**custom preset 是事务所级覆盖，不是个人模板 [E2]**

`custom_presets.py` 把所有自定义预设存进一个隐藏的 firm 模板“自定义公式预设”，domain=`preset`、status=`archived`；admin 直接生效，partner 提 candidate。它们优先进入 `preset_library`，并被 `draft_refresh_service` 读取，故成功保存后会影响后续初稿刷新，是真执行源；但没有个人/项目范围，也没有删除/恢复端点。名称“自定义”容易被理解成个人二次编辑，实际是事务所级配置候选。

## 10. 公式模板：模型、共享、订阅与全局联动

### 10.1 已真正实现的链路

- **创建**：来源可为 project/global/manual；前端开放 project/global，manual 仅 API。创建即写 `FormulaTemplate`、template-layer `FormulaSetting` 和 v1 `FormulaTemplateVersion.snapshot`。
- **可见性**：personal=所有者；team=所属项目成员；group=集团根及下级项目成员；firm=所有登录用户；admin 全可见。不可见详情返回 404。
- **管理权**：owner/admin 可改元数据、发布新版本、删；firm 创建仅 admin，team/group 创建还需所属项目 edit。
- **订阅**：每项目每域最多一个 active subscription；订阅前预览，模板定义物化为项目层；冲突可采用模板或保留项目。
- **升级**：模板 aggregate version CAS；生成完整冻结 snapshot；订阅项目按 follow/conflict/defer/frozen 分类，冲突进同一 pending 表。
- **退订**：keep 把模板行转成本项目适配；global 则回到本项目全局上游，冲突继续确认。
- **设为全局**：admin 直接走 `publish_global()`；其他可见用户提交 candidate，admin 在发布记录页预览审核。
- **删除约束**：有 active subscription 时 409，退订后软删。

这些链路证明它不是“仅 UI 空壳”或“项目内复制按钮”。`test_templates.py::test_save_subscribe_publish_unsubscribe_end_to_end` 与 `test_template_endpoints.py::test_visibility_matrix_list_detail_versions_same_rule` 覆盖了主要服务/API 形状，但测试环境由 `_env.make_db()` 明确使用 SQLite 内存库。[E2/E3]

### 10.2 与全局设置的关系

- 共用 `DomainStore`、`sync/engine`、pending、publish、audit、propagation，内核层是真联动。
- 模板创建时 `base_definition/base_version` 记当时全局；之后全局变化只在详情生成 `global_hints`。
- 订阅项目的模板 slot 被全局发布跳过；模板不会自动吸收全局。所有者需点“并入模板”并发布新版本，订阅项目才更新。
- “从全局设置副本保存”调用 `store.list_global()`，不含 wp/push 的 system preset；页面上看到的 preset 与模板里实际复制的内容可能不同。

### 10.3 模板仍缺的能力

1. **无版本回滚/指定版本订阅。** versions API 只返回版本号、说明、change_set 和时间；前端只显示“变更 N 条”，不展示 diff/snapshot，也没有恢复旧版。snapshot 仅服务 pinned 内部读取。
2. **已有模板 UI 不能新增 slot。** `FormulaTemplateDetailDrawer` 只允许编辑/移除已有定义和并入已有 global hint；API `publish` 能接收新 slot，但页面没有“新增公式”。
3. **适用范围和域可以不相容。** 前端给所有域显示同一套 scope 选项；后端对非空但 `global_scope()` 解析为 None 的组合没有拒绝。比如 report 模板标 `soe`、note 模板标 `enterprise` 时仍可订阅任意项目，却无法正常 promote/global hint。
4. **创建项目后的“去订阅”是死路。** `ProjectWizard` 唯一订阅建议跳 `/settings/formula-global?tab=templates`；该页 `FormulaTemplateManager` 只有列表/详情，没有 projectId 或订阅按钮。全仓真正的 `FormulaTemplateSubscribeDialog` 只挂在项目公式管理 toolbar。用户刚建完项目点“去订阅”无法完成承诺动作。
5. **readonly 用户能看到订阅操作但提交必 403**，见 §8.4。
6. **共享范围收窄不会处理既有订阅。** active subscription 只阻止改 applicable_scope，不阻止 firm/team/group 改 personal；既有订阅仍参与后续发布，但项目成员可能已看不到模板详情。这是订阅许可语义未定义，而不是单纯 CRUD 缺口。[E4]
7. **没有 live 验证。** 六张 V199 表均空，无法证明 PG 锁、真实成员矩阵、模板升级、事件传播和浏览器弹窗在同一真实操作中闭环。

### 10.4 明确分类

- **V199 `formula_template`：真模板。** 可共享、可订阅、可升级、可冲突处理，别人可以在权限范围内真正引用。
- **公式包 JSON：项目间复制工具。** `formulaPackage.ts` 逐域调用 overrides；每域一事务，允许前域成功后后域失败，无整体回滚，也不形成订阅关系。
- **“公式预设库”：混合。** seed/JSON 是只读系统预设；DB custom preset 是隐藏 firm 模板存储，但不可订阅、不可删除，主要供初稿刷新。
- **“📤 导出模板/Excel 导入”：文件交换工具。** 不产生 `FormulaTemplate`、版本或订阅。
- **旧 `shared_config_templates.config_type='formula_config'`：已退役。** list 返回空、create/apply 410；live 该类型模板和引用均 0。
- **“🌐 全局公式管理—跨作用域总览”：名称误导。** `FormulaGlobalScopeDialog` 明文统计的是本项目 `wp_formula` 的 7 类作用域，不是 V199 全局设置；它与旁边真正的“⚙ 全局设置”同时出现。

因此最终产品结论是 **“真模板内核 + 两种复制/预设工具 + 一个误名项目总览”**。应保留“公式模板”给 V199 订阅制对象，其余分别改称“公式包”“公式预设”“Excel 导入导出”“项目公式总览”。

## 11. 优先级缺陷清单

| 优先级 | 缺陷 | 用户后果 | 证据 |
|---|---|---|---|
| P0 | 项目间 pending 没有版本令牌 | 旧弹窗可能采用未看过的新定义，静默覆盖本项目 | C1 [E2] |
| P0 | 公式时间轴 3/5 数据源字段漂移且吞异常 | 审计/发布/模板历史静默缺失，页面看似“暂无” | C3 [E1/E2] |
| P1 | tb_detail 被标 wired 但无自动业务消费者 | 用户以为公式改变 TB/底稿，实际只改公式中心行 | §6 [E2] |
| P1 | wp 全局层不进 formula runtime/Tier A | “全局改一处”在部分底稿运行路径不生效 | §6 [E2] |
| P1 | 项目保存后应用范围只接 3/7 域 | 四域不能顺手设全局/提交候选/推其他项目 | §5.1 [E2] |
| P1 | consol_note 作用范围不筛 consolidated | 1 个合并项目的配置把 84 个单体项目计入/触发 | §6.1 [E1/E2] |
| P1 | 合并附注全局层允许 partner/manager 写 | 绕过“全局公式仅 admin”规则 | §8.4 [E2] |
| P1 | report/tb/cross generic 保存无语法/引用硬门 | 坏公式可落库，错误延迟到重算/执行 | §9 [E2] |
| P1 | 预设编辑 3/4 挂载只改内存 | 明示成功，刷新后丢失 | §9.2 [E2] |
| P1 | 全局/模板没有回滚；custom preset 不能删 | 错误推广后只能手工反向修改 | §7.2/§10.3 [E1/E2] |
| P2 | 多域冲突 key 不含 domain | 特定同名 slot 下决策/结果碰撞 | C2 [E2/E4] |
| P2 | 新项目“去订阅”跳到无订阅动作的页面 | 引导流程中断 | §10.3 [E2] |
| P2 | 发布记录仅登录可读 | 未来项目间公式/备注可能跨项目可见 | §7.2 [E2/E4] |
| P2 | live 六表全空 | 已实现能力没有真实 PG/UAT 证据 | §2 [E1] |

## 12. 建议的收口顺序

1. **先修可信度而非再加功能**：修 formula timeline 三个模型字段；把异常转为 `unavailable_sources`，不再静默空；删除 `specAReady=false` 过时横幅。
2. **补并发身份**：pending 增加 revision/updated_at CAS，尤其 project-origin；所有 decision key 改为 `{project}|{domain}|{slot}`，兼容旧 key 要显式迁移。
3. **重新定义 wired**：把 domain 状态拆成 `crud/edit/effective-read/automatic-execution/propagation/ui-apply-scope`，tb_detail 不得继续用一个布尔值冒充完成。
4. **收敛执行读者**：让 formula_runtime/Tier A 统一读 wp effective；给 tb_detail 明确产品语义。若它只是公式中心的虚拟视图，应改名并停止标全底稿 stale；若应影响 TB，必须建立唯一权威写入/读取链。
5. **修范围和权限**：consol_note 只列 consolidated；全局写统一 admin 或明确重裁产品规则；合并 report UI 对齐后端；publishes 按 global/candidate 与 project-application 分权。
6. **补全应用范围交接**：wp/note/push/consol_note 项目保存后都走同一 `askApplyScope`，或明确显示“本域不支持推广”而不是沉默。
7. **建立统一校验门**：所有 global/project/template/package 写入调用同一 domain validator；保存前做语法、函数支持、结构与可验证引用检查。前端提示只能辅助，后端必须硬门。
8. **完成模板产品闭环**：新项目 prompt 直接带 projectId 打开订阅 dialog；已有模板支持新增 slot、版本 diff、回滚为新版本；校验 domain×scope；定义共享范围收窄对订阅者的处理。
9. **清理假入口与术语**：三个 preset 弹窗挂载要么接保存，要么只读；主 UI 接通 reference 来源；四类“模板”按 §10.4 改名。
10. **最后做真实 UAT**：只在【测试】项目创建一套 global→project conflict→resolve、template→subscribe→upgrade→rollback 流程，覆盖 PG advisory lock、live SSE、重算与浏览器刷新；验收后再宣布“一处改全部”。

## 13. 反模式全仓同类扫描规模

| 反模式 | 全仓/区域现算规模 | 说明 |
|---|---:|---|
| broad `except Exception` | `backend/app` 文本命中 3542 处/1147 文件；路径含 formula 的 158 处/53 文件；`formula_timeline_service.py` 6 处 | 不是每处都错；本报告只判定其中 3 个时间轴源确实把 schema 错误吞成空。 |
| preset 编辑事件无人接 | 4 个 `GtFormulaPresetDialog` 生产 mount，只有 1 个 `@edit-formula` | 3 个可编辑成功提示是假成功。 |
| apply-scope 未接 | 7 个治理域中只有 3 个域的生产保存链调用 | 后端 API 广、用户路径窄。 |
| tb_detail 无业务读者 | 后端 production 对 `formula_settings.tb_detail` 的 import 只有 1 个 router | 无 TB/四表/生成 consumer。 |
| 决策 identity 少 domain | 后端 3 个 key 构造/读取点 + 前端 1 个契约说明 | DB 唯一身份明确含 domain。 |
| custom preset 删除/恢复 | backend/frontend 精确搜索均 0 | 只有 inventory/page GET 与 custom POST upsert。 |
| 全局/模板 rollback | live OpenAPI 0 条；仅项目历史 rollback 1 条 | 版本快照没有用户动作。 |
| 新项目订阅引导 | `tab=templates` 导航 1 处；真正 subscribe dialog mount 1 处且只在项目 toolbar | 目标页没有订阅控件。 |
| 全局写 `publish_global` | 11 个生产调用点 | 仅 consol-note HTTP 家族以 partner/manager 扩大全局写权。 |
| formula GET 内写/commit | formula 路由区域至少 2 个家族：consol-note 读取按需种子、report-cross-check GET 持久化结果 | GET 不是纯读，缓存/重试/审计语义需单独治理。 |

## 14. 代表性测试证据与盲区

**已有正向证据 [E3，未执行]**

- 后端：`test_sync_kernel.py`、`test_publish_report.py`、`test_project_ops.py`、`test_domain_adapters.py`、`test_templates.py`、`test_template_endpoints.py`、`test_propagation.py`、`test_endpoints.py`。
- 前端：`FormulaGlobalSettings.spec.ts`、`FormulaPublishPreviewDialog.spec.ts`、`FormulaPendingSyncDialog.spec.ts`、`FormulaApplyScopeDialog.spec.ts`、`FormulaTemplateManage.spec.ts`、`FormulaTemplateSubscribeDialog.spec.ts`。

**关键盲区**

- 后端主套件使用 SQLite 内存库，未证明 live PG advisory lock、partial unique index、真实 event/SSE。
- `test_production_wiring.py` 的自定义 `WIRED_DOMAINS` 不含 tb_detail，因此无法反驳生产 API 把 tb_detail 标 wired。
- timeline 测试只测空结果和 DB down，未放任何真实 ORM 行。
- consol panel 的 manager 报表编辑测试 mock `api.put` 成功，未与 admin-only report-config 端点对拍。
- project-origin pending 测试故意不传 `upstream_version` 并成功，没有二次推送竞态。
- 没有多域同 slot 的模板发布测试；没有 consol_note 排除 standalone 的测试；没有 preset 四个真实宿主的保存闭环测试。

## 15. 关键证据索引

### 后端文件/符号

- 模型/迁移：`formula_setting_models.py::{FormulaSetting,FormulaSyncItem,FormulaPublish,FormulaTemplate,FormulaTemplateVersion,FormulaTemplateSubscription}`；`V199__formula_global_settings_and_templates.sql`。
- 有效层：`definitions.py::{DOMAINS,is_effectively_disabled,same_exec}`；`effective.py::{upstream_records,effective_slots,layer_of}`。
- 同步/发布：`sync.py::{classify,decide,resolve_pending,classify_push,decide_push}`；`engine.py::{PlanItem,Decisions,apply_effect}`；`publish.py::{preview_global,publish_global}`。
- 项目/模板：`project_ops.py::{save_overrides,restore_global,resolve_items}`；`template_service.py`；`template_sync.py`；`template_access.py`。
- 域消费者：`effective_report.py`、`cross_check_rules.py::run_user_rules`、`note_settings.py::materialize`、`consol_note_settings.py::effective_formulas`、`push_settings.py::effective_push_rules`、`wp_effective.py`。
- 传播/历史：`propagation.py::{publish_events,HANDLERS,on_formula_config_changed}`；`formula_timeline_service.py`；`formula_settings/rollback.py`。
- 权限偏差：`routers/formula_settings.py::_require_admin` 对照 `routers/consol_note_formulas.py::EDITOR_ROLES` 与 `routers/report_config.py::_authorize_report_config_write`。

### 前端组件/请求契约

- 路径/API：`services/apiPaths/formulaSettings.ts`、`services/formulaSettingsApi.ts`。
- 全局页：`views/FormulaGlobalSettings.vue`。
- 项目入口：`FormulaManagerDialog.vue` → `FormulaSettingsToolbar.vue` → `FormulaApplyScopeDialog.vue`。
- 冲突：`FormulaPublishPreviewDialog.vue`、`FormulaConflictTable.vue`、`FormulaPendingSyncDialog.vue`；全局挂载在 `ThreeColumnLayout.vue`。
- 模板：`FormulaTemplateManager.vue`、`FormulaTemplateDetailDrawer.vue`、`FormulaTemplateSaveDialog.vue`、`FormulaTemplateSubscribeDialog.vue`。
- 编辑：`FormulaEditDialog.vue`、`FormulaInput.vue`、`NoteFormulaDialog.vue`、`FormulaPushPanel.vue`、`ConsolFormulaManagementPanel.vue`。
- 假入口/命名：`GtFormulaPresetDialog.vue` 及四个宿主；`FormulaGlobalScopeDialog.vue`；`ProjectWizard.vue`。

### live 只读 SQL 口径

- `schema_version WHERE filename LIKE 'V199%'`；`schema_migration_failures`。
- 六张 V199 表按 domain/layer/status/share_scope 聚合计数。
- `report_config` 按 applicable_standard、project 行、formula_version/base/pinned 聚合。
- `wp_formula` 按 formula_source/lifecycle/base/pinned 与 distinct project/wp 聚合。
- `disclosure_notes` 用 JSONB `?`、`jsonb_typeof/jsonb_array_length` 检查 `_user_formulas/_formulas/_check_presets`。
- `projects` 按 template_type/report_scope/status 及 null 值聚合。
- `information_schema.columns` 与 `pg_constraint` 验证 timeline 字段和 `formula_publish.status` 合法值。

## 16. 工作树与未提交依赖说明

调查开始时 HEAD 为 `779d8b436…`。调查期间并发会话提交了 S-cycle 变更，结束时 HEAD 为 `e383f4069…`；两提交差异涉及 S-cycle/底稿渲染文件，不涉及本报告列出的 formula-settings、formula-templates、timeline、全局页或冲突组件。对全部核心审计路径执行 `git diff --name-only -- <paths>` 为 0。

结束时仍有并发会话的未提交 `components.d.ts`、`wp_code_overrides.json` 与若干 S-cycle/.agents 文件；**本报告没有用它们证明任何结论**。唯一由本步新增的是本文件。基线 `00-ground-truth.md` 和并发产物均保持未提交状态。

## 17. 最终结论

**公式模板应定性为“真模板（代码完成）”，全局设置应定性为“真治理内核（部分执行接线）”，冲突弹窗应定性为“真接线（并发与追踪有 P0 缺口）”，用户二次编辑应定性为“多域可用但能力分裂”。**

在修复 P0/P1 并完成一套 live PG + 浏览器写入型 UAT 之前，不建议对外承诺“公式已贯穿整个平台、一处修改可应用到全部”。当前最准确的承诺是：**报表、表间审核、附注、合并附注和单体推送已有治理链；底稿全局继承与 TB 明细仍未闭环；模板订阅体系尚无现场采用证据。**
