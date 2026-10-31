# 平台全局显示设置收口：设计

## 概览

本设计把显示偏好拆成三个清晰边界：账号级“屏幕偏好”、项目级“正式输出默认单位”、数据集级“导入来源与存储单位”。前端只从一个 Pinia store 读取 effective 偏好；后端以当前用户 API 保存个人偏好，以项目配置保存正式单位，以导入元数据证明金额只换算一次；正式导出完全在后端或以项目策略驱动的受控前端导出器中决定单位，永不读取个人偏好。核心页先闭环，未清的全仓遗留进入可伪证单调台账。

技术栈锁定为现有 Python 3.12、FastAPI、Pydantic v2、SQLAlchemy async、PostgreSQL 16/SQLite 测试、Vue 3、Pinia、TypeScript、Element Plus、Decimal.js、Vitest、ESLint/vue-eslint-parser、Playwright、openpyxl/python-docx/LibreOffice。不得引入新运行时依赖、远程字体、i18n 或另一套状态管理。

## 1. 现状调查证据与评审复核（2026-10-28 工作树）

本轮先读 `tmp_global_display_settings/workflow_wf_bdd51ed745849c68/baseline.md`、`ownership.md`、`spec-review.json` 及完整评审文档，再按当前工作树复核源码。代码事实来自真实读取，不把归档结论当现状。

| 证据 | 现算结果与设计约束 |
|---|---|
| 偏好与入口 | `displayPrefs.ts` 仍只读写未分区 `gt_display_prefs`，可把越界 decimals 送入 `toLocaleString`；`ThreeColumnLayout.vue` 直接双绑 store。`/settings` 在 `router/domains/system.ts` 明确 `permission: admin`，所以普通用户必须走新 `/display-settings`，不能放开管理页。`UserSettingsExtension.vue` 无生产挂载，且内含超范围的本地默认准则/审计类型，本 spec 不挂它。 |
| 字体与字号 | `gt-tokens.css` 声明 GT Walsheim/FZYueHei/微软雅黑/苹方/Helvetica/Arial，但仓库无随包 woff/ttf/otf 与 `@font-face`；实际依赖系统回退。`global.css` 把 `--el-font-size-base` 绑到静态 15px，`gt-polish.css` 又以 `!important` 固定表头 12px。四档虽在 `formatters.ts` 定义为 11/12/13/14px，却未形成根级 Element Plus 合同。 |
| 生产接线 | `useGlobalTableLayout()` 只在自身测试调用；`exportUnit.ts` 只被 PBT 导入；`GtWpRenderer` 未绑定 `runtime.fontStyle`，`GtWorkpaperShell` 仅有测试/声明调用。显示相关四文件本轮实跑 **74/74 passed**，证明纯函数和单测存在仍不能证明生产接线。 |
| 公共表格与固定列 | `GtEditableTable` 自身仍把 header/body 固定 12px，`GtColumn` 没有 measure kind；`fixedColumns` 只有 store 单测，生产没有读取。TrialBalance、ReportView、DisclosureEditor 等核心页主要是原生 `el-table`，仓库中没有 `GtTableDisplaySettings.vue`。 |
| 页面与语义 | `ReportView`、`DisclosureEditor`、`ConsolidationIndex`、`ConsolNoteTab` 及 worksheet 仍有局部 11/12/13px。Dashboard 最近项目表仅有项目、年度、类型、阶段、进度、负责人、日期，没有金额字段，因此只验字号/密度。`DisclosureEditor` 对数值列统一用 `GtAmountCell :unit="noteUnit"` 并读写 `gt_note_amount_unit`。 |
| 项目与数据集单位 | `Project` ORM、项目详情 schema/mapper 均无 `amount_unit`；`project_config.py` GET 用 `getattr(...,'yuan')`，PUT 用 `hasattr` 且只校验登录，非法字符串可进 Pydantic。`project.ts` 已有 `contextSeq/resetProjectScopedState`，新字段必须沿用同一清空/晚到响应纪律。`LedgerPenetration` 从旧顶层 `source_summary.amount_unit` 取值后把显示单位重置为 yuan；TrialBalance 也把缺失元数据展示成“元”。 |
| 导入链 | detector 识别 `[万千百]?元`，所以“百元”会进入现有结果；`/submit` 命中缓存时不重算单位，且在创建 ImportJob 前调用会真实删除并自行 commit 的 `apply_incremental`。除三条拟保留 submit 外，实际注册的 `/account-chart/import` 仍调用 `run_account_chart_import`，`/api/projects/{project_id}/import` 仍调用 `start_import/start_import_streaming`；后者与 `/import/preview`、`/ledger-data/incremental/detect` 只有登录门。v2 pipeline/writer 与降级 smart engine 都分批 commit，`resume_from_checkpoint` 只按 current_phase 重新排队，故必须采用新 stage+attempt 协议而不能宣称一个长事务回滚。 |
| 附注列语义 | `note_table_header_library.ColumnKey.kind` 只有 label/amount/ratio/text；详情响应无 `column_kinds`。`note_template_table_look.render_cloned_table` 只凭值能否转数字调用 `fmt_amount_gt`。单体附注表有 section_id 但无稳定 table_id；合并附注每表已有 UUID `id`。 |
| 正式导出 | 单张报表路由自建 workbook；bulk package 自建试算表并吞导出异常；`wp_export/export_engine.py` 是 `export_workpaper_xlsx` 第二生产调用方，custom 导出只把 workbook 本体当 authority、无单位 metadata。`ExportPackageService` 捕获异常后写空 bytes并生成两个 placeholder；项目归档直接复制 `WordExportTask.file_path`，未绑定 exact version/hash/policy。OnlyOffice `created_via=onlyoffice_edit` 只继承 source snapshot，不继承单位 policy。PDF DTO 后端接单数 `document_type` 且无 year，前端发复数 `document_types`；引擎用空 rows/notes 并回退 HTML，相关端点只有登录鉴权。 |
| 失真守卫 | 本轮实跑旧格式脚本仍报 **1016** 个未登记命中；探针现算总 regex hits=1020，131 条行号 allowlist 仅 **4** 条仍有效、127 条失效。ESLint JSON 现算 `no-bare-amount-cell` 为 **2323 条/699 文件**，其中包含 formatter 已接入及非金额误报；baseline 同时保留 92/88 两个旧指标，CI 还以 `|| true` 吞 ESLint 退出码。 |
| 真实 PG 与环境 | 只读数字沿用开工基线证据：91 个 ledger dataset 中 45 个 active，均缺可证明的归一元数据，只能冻结为 `legacy_unknown`；该快照实施前必须重跑，不作为批量改值授权。开工时 3030 可访问、9980 超时且共享浏览器被会话接力，故当前没有可接受的 computedStyle 证据，终验必须用隔离上下文/端口。 |

调查产生的临时 ESLint JSON 与 allowlist 探针只放在 `tmp_global_display_settings/workflow_wf_bdd51ed745849c68/`，不进入产品提交。

## 2. 数据模型、迁移和后端 API

下列五项 schema 变更分成三组独立 V/R 配对，与 tasks.md 三个阶段一一对应：A 组 = 第 1、2 项，B 组 = 第 4 项，C 组 = 第 3、5 项。每组迁移号在该阶段实施时动态现扫：工作树 `backend/migrations`、`git ls-tree origin/spec/disclosure-note-doc-upload-and-batch-fill backend/migrations` 与 gt-plan `migration_status` 三处并集最大值 +1；三组号严格递增（B 组 > A 组，C 组 > B 组），实施时撞号即重扫取下一空号。恢复核对时三处并集最高为 V214（远端跟踪 ref 未 fetch），只作快照，不预占任何号。每组 V/R 各自配对，DDL 一律 `IF NOT EXISTS`/幂等且只含本组对象：

1. `projects.amount_unit VARCHAR(8) NOT NULL DEFAULT 'yuan'`，CHECK 仅 `yuan/qian/wan`；不读取或更新任何四表金额。
2. 新表 `user_display_preferences`：`user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE`、`amount_unit_override` nullable、`font_size`、`show_zero`、`decimals`、`negative_red`、`highlight_threshold NUMERIC(5,4)`、`density`、`grid_edit_mode`、`fixed_columns JSONB`、`revision`、`updated_at`。枚举/范围、JSON object 和 revision 均有 DB CHECK；SQLite 用 `sa.JSON().with_variant(JSONB, 'postgresql')` 并由 schema/service 重复校验。
3. 为现有 `export_tasks` 增加 nullable `export_year INTEGER`、`document_types JSONB NOT NULL DEFAULT '[]'` 与 nullable `unit_policy_snapshot JSONB`，把旧 `document_type` 非空值回填为单元素数组。新请求只写复数字段；旧单数字段仅供历史任务读取兼容，AST 守卫禁止新增写入。为 `word_export_task_versions` 增加 nullable `unit_policy_snapshot JSONB` 与 `unit_policy_digest VARCHAR(64)`，并增加 pair CHECK：两列必须同时为空或同时非空且 digest 匹配 64 位小写十六进制；所有 `doc_type=disclosure_notes` 且 `file_path IS NOT NULL` 的新版本不论 `created_via` 都必须成对写入，历史版本保持 null 并在 OnlyOffice 打开、刷新和归档时 fail closed。为 `working_paper_content_version` 增加 `export_surface_class`、`unit_policy_snapshot/unit_policy_digest` 和 `source_storage_unit`：formal 版本必须有 policy pair，data_exchange 版本必须有 `source_storage_unit` 且无 policy pair，template/non_amount 两类均不得伪带单位；CHECK 固定这些互斥关系，文件身份复用既有 `authoritative_artifact_id/sha256`。
4. 新表 `ledger_import_attempts`：`id UUID`、`job_id UUID`、`attempt_no`、`staged_dataset_id UUID`、nullable `base_dataset_id`、nullable `base_unit_contract_digest CHAR(64)`、`state`（`building|sealed|activating|activated|cleanup_pending|cleanup_done`）、`unit_contract_digest`、`bundle_digest`、逐表 `active_before_hashes/row_counts/pre_hashes/post_hashes JSONB`、`failure_code`、`created_at/sealed_at/finished_at`；`UNIQUE(job_id,attempt_no)` 与每个 staged dataset 唯一。`LedgerDataset` 当前没有 revision/version，本 spec 选择不可变 dataset UUID + unit contract digest 作为唯一 CAS token，不新增虚构整数版本。attempt 是恢复协议的权威状态，不再把 `ImportJob.current_phase` 当成可复用 staged 行的充分证据。
5. 新表 `custom_workbook_unit_authorities`：`id UUID`、`working_paper_id UUID`、`workbook_sha256 CHAR(64)`、`manifest JSONB`、`manifest_digest CHAR(64)`、`created_by/created_at`，`UNIQUE(working_paper_id,workbook_sha256)`；manifest/digest 必须成对且不可原地更新。当前 custom workbook 的每次内容版本只能指向与其完整文件 hash 相同、通过 schema 与 label binding 校验的 authority 行。

三组 R 迁移都必须在任何 `DROP` 前用同一事务内的 `DO`/`RAISE EXCEPTION` 执行本组无损回滚预检，不能只 warning；三组预检各自成立、只检查本组对象，回滚按 C→B→A 逆序执行。R_A 在存在 `projects.amount_unit <> 'yuan'` 或任一 `user_display_preferences` 行时中止；R_B 在存在任一 `ledger_import_attempts` 行时中止；R_C 在存在任一 `custom_workbook_unit_authorities` 行、任一 Word 版本 policy snapshot/digest，或任一底稿内容版本的 export surface/unit evidence 时中止，且 `export_tasks` 仅允许以下两类行通过：①`export_year`、`unit_policy_snapshot` 均为 null，`document_types=[]` 且旧 `document_type` 也为 null；②前两字段均为 null，`document_types` 是恰含一个非空字符串的数组，且旧 `document_type` 为 null 或与该值相同。第二类旧列为空时，R_C 先在同一事务回填 `document_type`；数组非 JSON array、多元素、空元素、与旧列冲突、年度或 policy 任一非空都 `RAISE EXCEPTION`。预检和单元素回填成功后才可删除本组新增列/表/约束；任一检查或 DDL 失败该组 R 整单回滚，不触碰正式文件或四表数据。

账号偏好选择独立 typed table，而不是扩充 User JSONB。现有 User 只有 `language`，没有可复用偏好容器；独立表可用 DB 约束和 revision CAS，避免用户资料时间戳及整块 JSON 并发覆盖。新增 `backend/app/models/user_display_preferences.py`、`backend/app/schemas/display_preferences.py`、`backend/app/services/user_display_preferences_service.py`、`backend/app/routers/user_display_preferences.py`，并在 models 与 `router_registry/system.py` 登记。

线协议固定 snake_case。GET 无记录不写库，返回：

```json
{"amount_unit_override":null,"font_size":"sm","show_zero":false,"decimals":2,"negative_red":true,"highlight_threshold":0.2,"density":"default","grid_edit_mode":"excel","fixed_columns":{},"revision":0,"updated_at":null}
```

`FontSize` 的唯一线值是 `xs|sm|md|lg`，像素映射 11/12/13/14 只在前端常量和跨语言契约测试中各声明一次。PATCH 使用 `extra='forbid'`，`base_revision>=0` 必填，至少一个除 base_revision 外的业务字段；decimals 0~6，threshold 0~1；fixed_columns 最多 100 个 pageKey，每 key/列 key 1~100 字符、每页最多 20 个不重复列、规范 JSON 不超过 64KiB。成功总返回完整结果。无记录首写放在 `begin_nested()`：唯一键竞争失败时回读 current，抛 typed conflict，由 router 返回 409 `DISPLAY_PREFS_REVISION_CONFLICT`；已有行用 `UPDATE ... WHERE user_id=current_user.id AND revision=base_revision`。service 只 `flush`，router 是唯一 commit/rollback 层；日志只记 user id、revision 和错误类别。

端点固定为 `GET/PATCH /api/users/me/display-preferences`，请求/路径均无 userId；只依赖 `get_current_user` 并始终以其 id 查询。数据库故障返回 500，前端降级但不把失败载荷写入其他账号缓存。

实际在 `main.py` 注册的是 `backend/app/middleware/audit_log.py::AuditLogMiddleware`，因此脱敏必须在该文件完成，而不是只限制 router logger。新增 `_redact_response(request, parsed)` 的精确规则：仅当 method=`PATCH` 且 path=`/api/users/me/display-preferences` 时，丢弃原始 response/data，只返回 `{revision, changed_fields}`；`changed_fields` 由 router 在校验后写入 `request.state.audit_changed_fields`，只含顶层字段名，`fixed_columns` 只能出现这个字段名，不能出现任一 pageKey/列 key。revision 从成功响应的规范结果读取；状态缺失或信封形状异常时 fail closed 为 `{redacted:true, changed_fields:[]}`，绝不回退完整载荷。其余路由沿用现有中间件行为。TestClient 必须在真实 middleware stack 上 PATCH 后查询 `logs.new_value`，并用移除该 route redactor 的故障注入证明完整响应会被测试抓住。

项目单位在 `models/core.py::Project`、`ProjectCreateResponse`、`project_wizard._to_project_response`、新 `project_config_service.py` 和 `project_config.py` 五层一致。`ProjectConfigUpdate.amount_unit` 改为严格枚举，config GET 使用 `require_project_access('readonly')`，PUT 使用 `require_project_permission('project:edit')`；service 只 flush，router commit，去掉 `getattr/hasattr`。非法值 422、非成员/无项目权限 403、归档写 423、不存在 404。PUT 成功返回完整 config 和 changed_fields，前端只在响应 project_id 等于当前项目时更新 store。

## 3. 前端 effective 层、缓存与可达设置入口

重写 `stores/displayPrefs.ts`，新增 `services/displayPreferencesApi.ts`、`utils/displayAmount.ts` 与 `composables/useDisplayPreferencesRuntime.ts`。store 内保存服务器字段、revision、`loadState`、`syncState`、`pendingPatch` 和当前 `ownerUserId`；唯一 effective `amountUnit` 为 `amountUnitOverride ?? projectStore.projectAmountUnit ?? 'yuan'`。`setUnit` 兼容旧调用但写 override，`followProjectUnit()` 写 null。每个 setter 先经过共享 normalizer，立即更新屏幕，以 300ms 防抖只 PATCH 脏字段。

缓存键固定 `gt_display_prefs:v3:${userId}`，载荷为 `{prefs,revision,pendingScalars,pendingFixedOps,cachedAt}`；每个 pending scalar/page op 都序列化自己的 mutation epoch、值及 `upsert|delete`，恢复后重新校验 epoch 为安全整数及 pageKey/列 key。TTL 恰 30 天。runtime 只在 `authStore.userId` 非空后读取对应 key；账号变化时先递增 request generation、取消 timer/AbortController、清空 pending/epoch 与内存默认，再读取新账号缓存。晚到 GET/PATCH 按 userId+generation 双检查后丢弃。旧 `gt_display_prefs` 只删除不迁移；过期缓存整份不用，连 pending patch/fixed ops 一并丢弃。JSON、范围和大小逐字段校验；`getItem/setItem/removeItem` 均捕获 SecurityError/QuotaExceededError。

GET 成功以服务端 current 为基底再叠加本账号未提交字段。store 维护全局递增的 `nextMutationEpoch`，并分开保存 `dirtyScalarEpochs:Map<key,{epoch,value}>` 与 `dirtyFixedOps:Map<pageKey,{epoch,kind:'upsert'|'delete',value?}>`；删除就是带 epoch 的 tombstone，不再用对象缺 key 推断。每个 setter 先递增 epoch、写本机值，再调度 flush。PATCH 发出时冻结 `ownerUserId/requestGeneration/baseRevision`、完整 wire payload和逐项 `{key,epoch,value|operation}`；同账号同一时刻只允许一个 PATCH in flight，新编辑只更新 map 并等待下一代请求。

成功响应先成为新 server base，但只删除当前 map 中 `epoch == sentEpoch` 的项；epoch 已前移的标量/页操作必须重新覆盖响应值并立即调度下一次 flush。409 的一次重试属于原发送代际：先以 `current` 为基底，只重放 epoch 仍等于发送快照的标量和 pageKey/tombstone；在途后产生的新 epoch 不进入旧代际重试，而是在重试响应后覆盖 current、由下一代 PATCH 提交。第二次 409 不清任何未确认 epoch并显示“待同步”。不同 pageKey 的设备修改由此并存，同一 pageKey 采用最新本机 epoch；账号变化、TTL 过期和主动登出必须递增 request generation、取消 AbortController/timer并清空全部 epoch/op，网络恢复只能重放当前 ownerUserId 的 map。网络失败时只使用同账号未过期缓存，否则平台默认；这些失败不抛到登录流程。PATCH 发送前再次限制 decimals/threshold/fixed_columns，保证损坏缓存永远到不了 Intl。

`stores/project.ts` 新增 `projectAmountUnit: Ref<AmountUnit|null>`。`syncFromRoute/loadProjectContext` 一旦识别项目 ID 改变，就与 year 一样同步清 null；`applyProjectInfo` 只由仍匹配 `contextSeq` 且 projectId 相同的响应赋值。合法三值保留；响应缺失/非法时设 `yuan` 并 `logger.warn`；详情请求失败保持 null，使 effective 层降级 yuan，绝不留上一项目值。config PUT 成功也须核对响应 projectId 与当前上下文后再写。

保留 `router/domains/system.ts` 中 `/settings` 的 `meta.permission='admin'`。新增 `views/DisplaySettingsView.vue` 与 child route `/display-settings`，只要求已登录并只渲染 `components/settings/DisplayPreferencesPanel.vue`。Aa popover使用 panel 的 `compact` 模式并提供“打开完整显示设置”；顶部设置图标对 admin 保持 `/settings`，普通用户转 `/display-settings`。管理员的 SystemSettings 可新增 panel Tab，但其余管理 Tab 和 API 不向普通用户开放。

`DisplayPreferencesPanel` props 固定为 `{compact?: boolean, showSyncState?: boolean}`，不接 userId；它只调用当前账号 store。emits 为 `changed`（完整归一偏好）与 `open-full-settings`。本 spec 不挂载、不修改 `UserSettingsExtension`，也不迁移 `gt-default-standard/gt-default-audit-type`；这两项若要跨设备另立需求。

## 4. 字体/CSS、度量合同、固定列与核心接线

### 4.1 根字体和字号合同

`gt-tokens.css` 保留现有 GT→系统回退顺序并补最终 `system-ui,sans-serif`；不加入字体文件、`@font-face` 或远程 URL。新增固定 `--gt-font-numeric: 'Arial Narrow',Arial,sans-serif` 与 `--gt-font-mono: Consolas,'Cascadia Mono',monospace`。这些 token 固定的是字体族；屏幕公式、代码和数字仍继承账号显示字号。`.gt-formal-document`、OnlyOffice iframe 内容、后端 Excel/Word/PDF 字体完全不消费屏幕变量。

`useDisplayPreferencesRuntime` 在 `document.documentElement` 写 `--gt-display-font-size`、`--gt-table-row-height`、`--gt-table-cell-padding-x/y`、`--wp-font-size` 和 `data-gt-font-size/data-gt-density`；默认 sm=12px。`global.css` 固定 `--el-font-size-base: var(--gt-display-font-size)`，body 数据正文继承该变量。`gt-table.css` 与最后加载的 `gt-polish.css` 对 `.el-table th.el-table__cell`、`td.el-table__cell`、`.cell`、表内 `.el-input__inner/.el-select__selected-item` 统一使用该变量和密度 padding；当前 `gt-polish.css` 表头 12px `!important` 必须改读变量。Teleport 只读 documentElement 变量，不复制 store。标题、标签、图标等语义 token可以保持固定层级，但不得落在核心数据格选择器上。

`DefaultLayout.vue` 在 setup 单点调用 runtime 与 `useGlobalTableLayout()`；后者同时监听 fontSize 和 density，在 nextTick 后重排全部真实 Element Plus 表。`GtWpRenderer.vue` 最外层真实生产容器绑定 `runtime.fontStyle`。`GtAmountCell` 去掉固定 `--gt-font-size-sm`，继承字号但保留 numeric family 与 `data-gt-value` 原始元值。

### 4.2 跨层度量合同

新增后端 `app/contracts/display_measure.py::DisplayMeasureKind`、`RatioScale` 与受校验的 `DisplayMeasureSpec`，前端在 `types/displayMeasure.ts` 定义逐值对拍的对应类型。kind 固定为 `amount|quantity|count|ratio|exchange_rate|unit_price|text`，scale 固定为 `fraction|percent_points`；模型级不变量是 `kind=ratio` 时 `ratio_scale` 必填，其他 kind 时必须为 null/缺省，否则 `DISPLAY_MEASURE_CONTRACT_INVALID`。`utils/displayAmount.ts` 是 Decimal 金额唯一实现；`GtAmountCell` 只允许 amount。`GtMeasureCell/formatMeasure` 对 `fraction` 先以 Decimal 乘 100、对 `percent_points` 原值追加 `%`，两者及其余非金额 kind 的 divisor 恒为 1；编辑控件与原始复制值不走展示换算。

现有比例合同只在显式适配层映射，不凭列名默认：`workpaper_sync.ValueType.ratio → fraction`、`ValueType.percent_points → percent_points`，G7 既有 `ratioScale='percent' → percent_points`、`'fraction' → fraction`。`GtEditableTable` 把输入列归一为 `NormalizedGtColumn`，其中 `measureKind` 必填；输入 `GtColumn.measureKind` 可省的唯一兼容默认仍是 `text`，但 `measureKind='ratio'` 时 `ratioScale` 必填，其他 kind 携带 ratioScale 直接报配置错误。核心表、`type:number`/右对齐只读列和所有新列若省略 kind，AST 守卫直接失败。render schema 同时增加 `measure_kind` 与条件字段 `ratio_scale`：既有 `render: amount` 可机械映射 amount，`percent/ratio` 只有配置明确 scale 后才可映射 ratio；核心未知或 ratio 缺 scale 拒绝渲染并给中文配置错误。

附注以 `note_table_header_library` + 逐表 override 生成受 `--check` 守护的 `note_table_measure_catalog.json`。`ColumnKey` 和 catalog 叶子列同时保存 kind 与 nullable ratio_scale；标题只可识别“这是比例列”，不能决定尺度，所以每个 ratio 必须由逐表 override 明示 scale，缺失时生成器和运行时都 fail closed。单体两版使用 section_id + 新持久化 UUID table_id，合并两版复用现有表 UUID id；catalog 为每个叶子列持久化 UUID column_id，ID 不从可变标题或位置临时计算。生成器先按 table_id 读取旧 catalog，再以规范表头路径匹配并复用 column_id；新增列只在显式 `--write --assign-new-ids` 时分配，删除/改名/重排无法唯一对应时 `--check` 失败并要求提交 remap，不静默换 ID。同步脚本保留既有 table_id，新增/歧义表要求人工确认。`note_table_enrichment.enrich_note_table_data` 与合并附注响应都下发和 headers 等长的 `column_ids/column_kinds/column_ratio_scales`，非 ratio 的 scale 槽固定 null。DisclosureEditor/ConsolNoteTab 把 kind+scale 一并传给 GtAmountCell/GtMeasureCell；`NoteWordExporter._render_table` 与 `note_template_table_look.render_cloned_table` 必须接收同一列 kind/scale，只有 amount 执行 policy divisor。

### 4.3 固定列合同

新增 `composables/usePreferredFixedColumns.ts`，供 `GtEditableTable` 与原生 `el-table` 共用。输入为 `pageKey/allowedColumns/mandatoryColumns`，输出 `effectiveKeys/staleKeys/fixedFor(key)/save(keys)`；不变量由 composable 单点执行：`effective = mandatory ∪ (saved ∩ allowed)`，用户选择只返回 `left|false`，重复/未知 key 删除，mandatory 不可取消。业务既有固定右操作列不进入用户配置。

新增 `GtTableDisplaySettings.vue`，props 为 `{pageKey:string, columns:Array<{key:string,label:string}>, mandatoryKeys?:string[], disabled?:boolean}`，emits 为 `change({pageKey,savedKeys,effectiveKeys,staleKeys})`。组件从当前账号 store 读写，不接 userId；staleKeys 非空显示“部分已固定列在当前表中不存在，已忽略”。核心矩阵固定如下：

| pageKey | allowed 稳定 key | mandatory |
|---|---|---|
| `trial-balance` | `standard_account_code,account_name,direction,unadjusted_amount,rje_adjustment,aje_adjustment,wp_adjustment,audited_amount,wp_status` | `standard_account_code,account_name` |
| `report-view` | `row_code,row_name,note,current_period_amount,prior_period_amount`；compare 模式追加 `unadjusted_amount,adjustment,audited_amount,variance,variance_rate` | `row_code,row_name` |
| `disclosure-editor` | `label` 与响应的稳定 `column_id` | `label` |
| `workpaper:<componentType>` | render schema/GtColumn 的 `prop` | schema 明示 `fixed_required=true` 的身份列；未声明则空 |
| `consolidation:<tab>` | report 用 `row_code,row_name,current,prior`；note 用 `label,column_id`；trial/worksheet 用各列 prop | report=`row_code,row_name`；note=`label`；其余由 schema 明示 |

原生列缺 prop 时增加 `column-key` 数据属性并把 `:fixed="fixedFor(key)"` 绑定到每个叶子列。动态附注换表时 allowed 集合重算；旧表保存的 key 不会误固定新表。

### 4.4 核心页面接线矩阵

| 核心面 | 接线与稳定验收目标 | 金额/非金额边界 |
|---|---|---|
| Dashboard/项目看板 | `.dashboard-recent-table` 与卡片接根字号/密度；不新增金额卡 | 项目数、年度、工时、进度、日期均为非金额，切单位不变。 |
| TrialBalance | 主表、summary、trace、调整弹窗共用 amount/measure 组件与 `trial-balance` 固定列；详情区显示数据集单位状态 | 未审/AJE/RJE/底稿调整/审定为 amount；编码、方向、科目数为 text/count。 |
| ReportView | 普通、compare、权益、减值及核对弹窗移除局部 13px，列补稳定 key/kind | 报表值与差异为 amount；变动率为 ratio，行次为 text。 |
| DisclosureEditor | 删除 noteUnit 选择器和 `:unit`；消费 column_ids/kinds 与 `disclosure-editor` 固定列 | 仅 kind=amount 缩放，其他数值不猜。 |
| HTML 底稿 | `GtWpRenderer` runtime 根；GtEditableTable/render schema 传 kind/pageKey | amount 展示换算；输入、公式原值、quantity/rate 不变。 |
| 合并 | ConsolidationIndex、ConsolNoteTab、worksheet 去局部字号并按 tab 接固定列/kind | 合并数为 amount；持股比例 ratio、企业数量 count。 |
| LedgerPenetration | 金额格走 effective prefs；单位状态与显示单位分栏 | 借贷金额 amount；来源单位/因子是元数据，不改 effective。 |

Playwright 金额样本 10000 必须从 TrialBalance、ReportView、DisclosureEditor、HTML 底稿、合并页和 LedgerPenetration 的真实金额格各取一处；Dashboard 只做字号/密度与非金额反向验证。

## 5. 账套单位检测、归一、增量门与既有数据

新增 `backend/app/services/ledger_import/unit_normalization.py`，同时作为 Pydantic 合同与运行时单源。合同固定如下：

```python
class UnitDetectionSummary(BaseModel):
    status: Literal['detected', 'missing', 'conflict', 'unsupported']
    candidates: list[Literal['yuan', 'qian', 'wan']]
    unsupported_labels: list[str]
    suggested_unit: Literal['yuan', 'qian', 'wan'] | None
    detector_version: str
    evidence_digest: str

class UnitConfirmationInput(BaseModel):
    source_amount_unit: Literal['yuan', 'qian', 'wan']
    source_unit_confirmed: Literal[True]
    unit_evidence_digest: str  # 64 位小写 SHA-256
    unit_confirmation_reason: str | None = None  # 条件必填，1~200 字

class IncrementalSubmitInput(BaseModel):
    overlap_strategy: Literal['skip', 'overwrite']
    file_periods: list[int]  # 1~12，去重后仍至少一项
    base_dataset_id: UUID
    base_unit_contract_digest: str  # detect 返回的 64 位小写 SHA-256
    confirmed_overwrite: Literal[True] | None = None

class UnitNormalizationContract(BaseModel):
    source_unit: Literal['yuan', 'qian', 'wan']
    storage_unit: Literal['yuan'] = 'yuan'
    factor: Decimal
    normalization_version: Literal['normalized_v1']
    fields_version: Literal['amount_fields_v1']
    detection: UnitDetectionSummary
    confirmation_reason: str | None
    confirmed_by: UUID
    confirmed_at: datetime
    contract_digest: str  # 规范合同（排除本字段）的 64 位小写 SHA-256
```

`UnitConfirmationInput` 使用 `extra='forbid'`；digest 必须是 64 位小写十六进制。检测为 missing/conflict，或用户选择与 detected suggestion 不同时，reason 去首尾空白后必须为 1~200 字；unsupported 无论有无 reason 都不可构造合同。`UnitNormalizationContract` 使用 `model_validator(mode='after')` 固定 `storage_unit='yuan'`，并逐值强制 `yuan→Decimal('1')`、`qian→Decimal('1000')`、`wan→Decimal('10000')`；detected 且 source_unit 等于 suggestion 时 reason 可空，detected 覆盖 suggestion 以及 missing/conflict 时必须保留有效 confirmation_reason，unsupported 永不合法。`canonical_unit_contract` 对除 `contract_digest` 外的全部字段做枚举 value、UTC ISO 时间、Decimal 规范字符串和 sorted-key 紧凑 JSON 后取 SHA-256；builder 写入 digest，`parse_persisted_unit_contract(raw, job_created_by=...)` 在每次 claim/retry/resume 重新计算并同时要求 `confirmed_by == job.created_by`、`detection.evidence_digest == options.unit_confirmation.unit_evidence_digest`。factor、确认人、检测摘要或 digest 任一被改都在写入前 fail closed。`IncrementalSubmitInput` 使用 `extra='forbid'`，`base_unit_contract_digest` 必须为 64 位小写十六进制；只在增量导入出现，overwrite 时 `confirmed_overwrite=True` 必填。完整导入调用方必须显式传 `incremental_plan=None`，避免默认参数掩盖旧调用方。确认人只取服务端 `current_user.id`，不接受客户端 user id。

`detector._extract_amount_unit` 不再只返回首个中文标签。`LedgerImportUploadService.create_bundle` 在流式落盘时同时计算每文件 SHA-256 并写 manifest；旧 bundle 缺 hash 或提交/worker 复算不符时返回 `UPLOAD_BUNDLE_INTEGRITY_FAILED`，要求重新上传。`summarize_detected_units` 收集每个 file/sheet 的原始标签；元/千元/万元映射三枚举，百元/亿元/币种单位等进入 unsupported。`evidence_digest` 是 bundle 文件 hash/size、`detector_version` 以及按原始 file name、sheet name、raw label、normalized verdict 排序后的规范 JSON SHA-256。`ledger-import/detect` 与 `LedgerImportApplicationService.preview` 服务的 `/account-chart/preview`、`/ledger/smart-preview` 都以 `unit_detection` 字段返回同一个 `UnitDetectionSummary` wire shape。

`/ledger-data/incremental/detect` 在计算 periods 前通过新的 `load_incremental_base_token` 读取当前 active dataset，并只接受可严格解析的 `source_summary.unit_normalization`；响应增加 `base_dataset_id` 与 `base_unit_contract_digest`，后者就是当前 active 的 canonical unit contract digest，同时回显由 bundle 服务端检出的 `file_periods`。`GET /datasets/active` DTO同步暴露同一 digest供界面展示，但 submit 只信 detect 响应。没有 active 或 active 为 legacy 时 detect 返回 409 `BASE_DATASET_UNIT_UNVERIFIED`，不制造整数 version；前端 `LedgerDataManager` 将 ID、digest、periods 作为只读快照交给 `LedgerPenetration`，后者原样写入 `IncrementalSubmitInput`。

所有已注册的账套 preview/detect 必须先走路径项目 `require_project_access('edit')`，包括上述三条以及保留的 `/api/projects/{project_id}/import/preview`、`/ledger-data/incremental/detect`；后两条可保留各自只读结果，但不能只用 `get_current_user`。已注册的同步 `POST /api/projects/{project_id}/account-chart/import` 与 `POST /api/projects/{project_id}/import` 没有生产前端调用方，选择在本 spec 中退役而不是再维护第四、第五套提交合同：两者在 edit 鉴权后无条件返回 410 `{code:'LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB', message:'账套导入已迁移到单位确认作业，请重新预览并提交'}`，函数体不得 import/call `run_account_chart_import`、`import_service.start_import/start_import_streaming` 或 writer。`LEDGER_IMPORT_ENTRYPOINTS` 不是手写 URL 清单，而是以 `app.routes` 中注册 endpoint 身份为输入的可执行注册表：为每条 route 标记 `preview|retired|submit|status|recovery` 及允许到达的 ImportJob/writer/activate 符号；AST 从 `ImportJobService.create_job`、`DatasetService.activate`、`bulk_write_staged/copy_insert` 和旧 import service 反向追踪，任何未登记可达入口或登记 endpoint 未挂载都失败。`status` 只允许纯读并按 task/batch 反查项目 readonly；`recovery` 只允许 cancel/retry/rollback 已有作业，不得接收新文件或新金额值，必须验证对象属于路径项目并走 edit 门；其他任何可创建五表行或 active dataset 的 route 必须分类为三条 confirmed submit，不能用新增 registry 行充当豁免。

新增共享 `build_confirmed_unit_contract(*, project_id, upload_token, confirmation, confirmed_by, db)`。它从 project+token 重新物化不可变 bundle、逐文件复算 hash、重新 detect、构造摘要并核对 digest，再返回 immutable contract；不能读取仅含行数的 detection cache。v2 JSON submit 使用必填嵌套字段 `unit_confirmation: UnitConfirmationInput`；两个兼容 multipart submit 使用同名 JSON Form 字段并由同一 Pydantic 模型解析。兼容路由若收到 files/file 而没有可验证的 upload_token+confirmation，必须只经 `create_bundle` 落盘并完成检测，然后返回 HTTP 428，detail 固定为 `{code:'SOURCE_UNIT_CONFIRMATION_REQUIRED', message:'请确认账套金额单位后重新提交', upload_token, unit_detection}`；该分支不得取得队列锁、调用 `submit_import_job`、创建 ImportJob 或触碰四表。

`LedgerImportApplicationService.submit_import_job` 不再接收 `files/file`，签名固定为必传 token、确认和显式增量计划：

```python
async def submit_import_job(
    *, project_id: UUID, user_id: str, db: AsyncSession,
    upload_token: str, unit_confirmation: UnitConfirmationInput,
    year: int | None, custom_mapping: str | dict[str, Any] | None,
    payload_style: Literal['account_chart', 'ledger'],
    incremental_plan: IncrementalSubmitInput | None,
) -> dict[str, Any]: ...
```

`account_chart.import_async` 显式传 `incremental_plan=None`；`ledger_penetration.smart_import` 从 Form JSON 解析并显式传计划。两者都先调用 shared helper，再调用同一 active-dataset preflight：完整导入只形成不触碰当前 active 行的 replacement plan；增量导入在项目+年度 advisory lock 下要求当前 active 的 UUID 与 canonical unit contract digest 分别等于 `base_dataset_id/base_unit_contract_digest`，并通过 normalized_v1/yuan/证据门。最后才取得队列锁并用 `ImportJobService.create_job` 把 `unit_confirmation`、完整 `unit_contract`/`contract_digest`、`incremental_plan`、`payload_style` 和 token 一起写入 options。`AccountImportStep.vue` 与 `LedgerPenetration.vue` 必须保存 preview 的 `unit_detection`，展示建议/冲突/unsupported，并提交用户确认；`LedgerDataManager.vue` 还必须保存 incremental detect 的 base ID/digest，不得只传月份或让 service 猜单位。

`ledger_import_v2.submit_import` 与兼容 service 共用相同顺序，且不可调整：①鉴权和 DTO 校验；②取不可变 bundle；③调用 shared helper 重算 hash/摘要/digest；④digest 不同返回 409 `UNIT_DETECTION_CHANGED`，unsupported/未确认返回 422；⑤若 incremental，在项目+年度锁内查询当前 active dataset，逐值核对请求的 base UUID+unit contract digest，并验证 nested `source_summary.unit_normalization` 的 storage_unit、受支持 normalization_version、fields_version 和 evidence/hash 完整性；UUID/digest 已变化返回 409 `BASE_DATASET_CHANGED`，证据本身不合格返回 409 `BASE_DATASET_UNIT_UNVERIFIED`；⑥创建带完整合同/计划的 ImportJob 并由 router commit；⑦只 enqueue。任何错误都早于增量数据操作和 job 创建。seal 与 activation 在各自短事务中再次执行同一 `assert_incremental_base_unchanged`，不能使用 ImportJob.version、列表序号或创建时间替代 dataset UUID+digest。

现有 `POST /api/projects/{project_id}/ledger-data/incremental/apply` 保留路由形状用于明确退役，但在鉴权后无条件返回 HTTP 410，detail 为 `{code:'INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB', message:'增量覆盖已并入导入作业，请重新上传并提交'}`，不得 import/call `apply_incremental`。`LedgerDataManager.vue` 删除“执行清理”请求与成功后刷新逻辑，只保留 detect/策略确认，并把 `{year, overlap_strategy, file_periods, base_dataset_id, base_unit_contract_digest}` 通过 `request-incremental-upload` 交给 `LedgerPenetration`；后者逐值随 `smart-import.incremental_plan` 提交。服务端再次从 bundle 检出的月份必须与 file_periods 一致，否则 409 `INCREMENTAL_PERIODS_CHANGED`，不能信任手填月份。

把现有删除/合并逻辑拆为 `ledger_import/incremental_merge.py::apply_incremental_staged_merge(db, *, attempt_id, staged_dataset_id, base_dataset_id, plan)`；它只在目标仍为本 attempt 的 staged dataset 时工作，不得更新 active/superseded 行，也不得自行 commit。`ledger_import/pipeline.py`、`ledger_import/writer.py::{bulk_insert_staged,bulk_copy_staged,bulk_write_staged}` 与 `smart_import_engine.py` 的现有内部 commit 点全部纳入本 spec：允许保留流式批次 commit，但每个四表写入必须带 `attempt_id + staged_dataset_id` 并固定 `is_deleted=false`，SQL 只能命中该 stage；智能引擎当前 `is_deleted=true` 的四表路径必须改掉，旧 active 预删路径必须移除。两引擎不再自行 create/activate dataset；runner 在短状态事务中创建 attempt+stage 后把两者作为无默认参数传入。

四表可见性由 `dataset_query.py` 的唯一异步 predicate 拥有，而不是仅靠“dataset.status=staged”的假设。改造后的 `get_active_filter` 删除 `strict=False` 和异常 rollback：成功查到 active 时返回 `project_id/year/dataset_id=<active>/is_deleted=false`；明确查到无 active 时只返回 `project_id/year/dataset_id IS NULL/is_deleted=false`；查询失败原样上抛。`force_dataset_id` 仍只供已绑定快照，精确过滤指定 dataset。`active_rows_predicate` 对每个 project/year 使用同一规则；`sync_active_filter` 不得留生产调用方，同步场景只能先异步取得 active ID 后用 `get_filter_with_dataset_id`，或在已成功证明无 active 后调用显式 `legacy_rows_predicate`。因此首次导入期间无 legacy 行时所有生产读取为空，有 legacy NULL-dataset 行时只见 legacy，任何 staged UUID 行都不可见。

`LEDGER_TABLE_READ_SURFACES` 由 Python AST 从 `TbBalance/TbLedger/TbAuxBalance/TbAuxLedger` 的 `select/update-derived-read/aggregate` 符号反向产生并与版本化 registry 双向相等，覆盖 `note_trace.py`、`disclosure_trace.py`、`note_source_resolvers.py` 等现有裸读。每个生产读取必须调用上述 async predicate或显式 force ID；`project_id/year/is_deleted=false` 组合、只用 `dataset_id.in_(active_subquery)` 但无 legacy 规则、异常后 base filter、以及未登记 reader 都失败。PG 并发测试在每次批次 commit 后从每个登记 reader 读取 effective row-count/hash，而非只比较旧 active dataset 自身物理 hash。

`AccountChart` 不套四表的 `is_deleted=false` stage 规则。保留 `uq_account_chart_project_code_source WHERE is_deleted=false`：标准科目行继续独立可见；两个引擎写入的 staged 客户科目固定 `dataset_id=<stage>, is_deleted=true`。新增 `account_chart_active_predicate`：有 active 时只读该 dataset 的 client 行，无 active 时只读 `dataset_id IS NULL` 的 legacy client 行，active 查询失败同样上抛。激活短事务锁定项目年度的 attempt/stage/active 后，先把当前 active 客户科目以及首次切换时的 legacy NULL-dataset 客户科目标为 deleted，再把新 stage 客户科目标为未删；语句顺序由 partial unique 要求，任何唯一键或后续步骤失败都由事务恢复旧软删状态。dataset rollback 执行相反顺序：先隐藏当前、再放开 previous；seal 与 cleanup 只按 dataset_id 统计/删除，不依赖 is_deleted。

attempt 状态机固定为 `building → sealed → activating → activated`，失败分支为 `building|sealed|activating → cleanup_pending → cleanup_done`，失败原因单独保存在 `failure_code`，job 与 dataset 分别进入 failed。building 阶段执行 parse、convert、唯一 normalizer、批量 staged 写入，并物化增量 merge 所需的基准复制/删除候选与辅助汇总输入；每批可提交，但旧 active 的物理 hash和全部登记 reader 的 effective row-count/hash都必须保持 submit 前快照。全部写完后 runner 重新计算物理 row_counts 与 post_hashes，核对合同、bundle digest、`base_dataset_id/base_unit_contract_digest` 和预期计数，在项目年度锁内再次确认当前 active token 未变，然后于独立短事务封存证据并将 attempt 置 sealed。seal 前禁止 activation。

最终激活使用一个项目+年度 advisory lock 下的短事务：`SELECT FOR UPDATE` attempt/stage/当前 active，第三次要求当前 active 的 UUID+unit contract digest 等于 attempt 保存的 token，并重验 sealed 证据与导入合同；执行 staged merge 的最终标记，按上一段顺序切换客户科目软删位，再完成旧 active→superseded、新 stage→active、ActivationRecord、`LEDGER_DATASET_ACTIVATED` outbox 和 attempt→activated。四表不改 is_deleted，只靠读 predicate 随 dataset status 原子切换。事件发布仍在提交后按 outbox id 重放；发布失败不回滚已提交数据，但 outbox 保持 pending/failed。最终事务任一步失败全部回滚，旧 effective 四表/科目结果、active 状态和 sealed stage 均保持原状，可进入恢复判定。

任一 building 阶段异常、中断、取消、合同/hash 漂移、base token 变化或 seal 校验失败，runner 先用独立状态事务写 `cleanup_pending + failure_code`，再按 dataset_id 删除 AccountChart 与四表 staged 行、标 dataset failed、标 job failed，并在同一清理事务写 attempt `cleanup_done`；清理可幂等重跑，完成标准是五张表该 dataset_id 行数均为 0。`recover_jobs` 与 `resume_from_checkpoint` 只读取 `ledger_import_attempts`：仅 `sealed` 且合同 digest、bundle digest、row_counts、post_hashes、`base_dataset_id/base_unit_contract_digest` 及当前 active token 全部复验一致时允许 `activation_only`，不会再执行 converter/normalizer；`activated` 只补 job/queue 收尾；其他状态一律先完成清理，再以同一不可变 bundle 和原合同创建 `attempt_no+1`/新 stage 全量重建。`ImportJob.current_phase` 仅作进度显示，不能授权复用 staged 行。

`ImportOrchestrator.submit` 和兼容 `ImportJobService.create_job` 都把 `unit_confirmation`、`unit_contract`、contract digest 与计划完整写入 `ImportJob.options`。`ImportJobRunner._execute_after_claim` 在 feature flag 分流和任何 attempt/数据写入前调用 `parse_persisted_unit_contract(..., job_created_by=...)`；缺失或不合法的历史 queued/interrupted/retry job 直接转 failed，机器码 `SOURCE_UNIT_CONFIRMATION_REQUIRED` 或 `UNIT_CONTRACT_INVALID`。`execute_pipeline(..., unit_contract, incremental_plan, attempt_id, staged_dataset_id)` 与 `smart_import_streaming(..., unit_contract, incremental_plan, attempt_id, staged_dataset_id)` 均改为无默认必填，retry/resume 不能重猜、替换合同或在旧 stage 上重跑 normalizer。

`_AMOUNT_FIELDS_BY_TABLE` 是唯一字段表：balance/aux_balance 为 `opening_balance,opening_debit,opening_credit,debit_amount,credit_amount,closing_balance,closing_debit,closing_credit`；ledger/aux_ledger 为 `debit_amount,credit_amount`。它按转换后的真实 row dict 执行并由 converter 契约测试对拍。`opening_qty/debit_qty/credit_qty` 与全部 `*_fc` 保留原值；当前 converter 未产出的字段不会用 ORM 名字制造假覆盖。

金额 row contract 固定为 `Decimal|None`。两个 converter 共用 `parse_amount_cell(raw, locator)`：数据库/null/空字符串/纯空白返回 None；Decimal、整数及合法十进制字符串返回 finite Decimal；bool、其他类型或非空不可解析文本抛 `LEDGER_AMOUNT_INVALID`，携带 file/sheet/row/field 但不含原值；NaN、+Infinity、-Infinity 抛 `LEDGER_AMOUNT_NOT_FINITE`。唯一 `normalize_amount_value(value: Decimal|None, contract)` 对 None 原样返回；非空先再次断言 `is_finite()`，再执行 `value * factor`、`.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)`，最后要求结果位于 Numeric(20,2) 的 `-999999999999999999.99..999999999999999999.99`。canonical hash 对 None 写固定 JSON `null` token，对有限 Decimal 写规范字符串；converter、normalizer、legacy dry-run/hash 共用这两个 helper。它在 convert 后、首次 staged write 前对每个字段只执行一次。stage 的 sealed 证据和 dataset `source_summary.unit_normalization` 保存完整合同/digest、attempt id、字段版本、四表 row_counts、归一前/后 hash；检测到二次调用、非法值、非有限值、溢出或合同漂移均 fatal。active incremental 门以这里的 post-hash/row_counts 为完整证据。

新增 `dataset_unit_contract.py` 把 source_summary 归为 `normalized_v1|legacy_declared|legacy_unknown`，API 返回结构化状态。前端 `utils/datasetUnitPresentation.ts` 是 LedgerPenetration 与 TrialBalance 的唯一文案 presenter：normalized 才显示来源、因子和“存储单位：元”；旧顶层 amount_unit 只显示“历史声明：X，存储口径未验证”；无证据显示未知。任何状态都不修改 displayPrefs。

共享真实 PG 的只读入口与未来写入口物理分离。`backend/scripts/analyze/inspect_legacy_ledger_units.py` 只导入纯读取/hash helper，不导入 apply/rollback writer；它取得单一 `AsyncConnection` 后立即 begin，并把第一条业务 SQL 固定为 `SET TRANSACTION READ ONLY`，随后以 `SHOW transaction_read_only` 断言 `on`，所有 service 都显式接收该 connection/session且不得构造 engine/session，`finally` 一律 rollback。它按 normalized/legacy declared/legacy unknown 输出 dataset、四表行数、字段 sums/max、溢出风险与确定性 hash，不按金额大小猜单位。共享 PG baseline 与本脚本均走该入口。

未来写工具单独为 `backend/scripts/migrate/normalize_legacy_ledger_units.py`，没有默认写动作；`apply` 必须同时提供 `GT_ALLOW_REAL_LEDGER_UNIT_MIGRATION=1`、`--apply`、`--dataset-id`、相同的 `--confirm-dataset-id` 和 `--source-unit`。`rollback` 必须具备同一环境变量、`--apply`、双录 dataset id 与 `--rollback-normalization-version`，且该版本必须是最后一次未回滚 apply、当前 hash 等于其 after-hash。本 spec 的自动 apply/rollback 测试只连隔离 PG；本轮不在共享 PG 调用该写入口。

hash 对每张表分别计算：以主键顺序流式游标分批读取，编码 `(id, _AMOUNT_FIELDS_BY_TABLE[table] 的规范 finite Decimal 字符串或 null token)` 加 row_count 后滚动 SHA-256，不把百万行载入内存；总 hash 再按固定表序组合。新增 `_UNIT_METADATA_PATHS` 有限清单，只包含既有顶层 `amount_unit/source_unit/storage_unit/normalization_version/normalization_factor` 与 `unit_normalization`；`capture_unit_metadata` 以 `{path,present,value}` 表示缺失与显式 null，并生成 canonical snapshot+digest，不复制 `files/legal_hold`，`normalization_history` 保持独立 append-only。

apply 的 `source_summary.normalization_history[]` 追加 `{operation:'apply',version,source_unit,factor,fields_version,row_counts,before_hashes,after_hashes,before_unit_metadata_snapshot,before_unit_metadata_digest,at}`。rollback 先校当前 hash 等于该 apply 的 after-hash，反向换算后要求结果逐表等于 before-hash，再按 presence-aware snapshot 精确恢复每个单位键（原缺失的删除、原存在的恢复），并追加 `{operation:'rollback',rolled_back_apply_version,row_counts,before_hashes,after_hashes,restored_unit_metadata_digest,resulting_classification,at}`；恢复分类必须与 apply 前的 `legacy_declared|legacy_unknown` 相同，绝不能留下 normalized_v1，增量 preflight 随即再次拒绝。四表、unit metadata、history 与 hash 在单数据集事务中全成或全回滚；任一快照 digest、row count、hash、溢出或分类不符均 fatal。本轮真实 apply/rollback仍须用户再次放行。

## 6. 正式导出 authority、调用方收口与 PDF

### 6.1 机器可读模板单位

新增 `backend/data/audit_report_templates/export_unit_policy.json` 与 JSON Schema。每个 document variant 都显式含 `default_unit: yuan|qian|wan|null`；null 表示该文档无模板默认，继续取项目单位。附注 `table_units` 的键固定为 `<section_id>/<table_id>`；财务报表/底稿区域使用模板 manifest 中稳定 variant+sheet/region id。每个区域还声明有限 `label_binding`（`xlsx_cell`、`docx_table_header` 或 `generated_header`）及稳定地址。优先级严格为 table/region unit > non-null document default > project amount_unit > yuan。validator 只读取 label_binding 指定的单元格/表头/生成槽核对标签，不扫描章节叙述、表体或其他自由文本，也不从文字反推 authority。

单体 `note_template_soe/listed.json` 的每张表增加持久化 `table_id`；合并 `consol_note_sections_soe/listed.json` 复用现有 UUID id。`sync_note_templates_from_word.py` 只能保留已有 ID，新表无法唯一匹配时 fail closed 并要求人工分配。`validate_template_manifest.py` 增加 `--check`（保留 `--strict` 兼容）并同时验证：sidecar schema、单位枚举、variant 存在、section/table/column ID 唯一且存在、每个输出区域恰一个 authority、标签与数值 policy 一致。sidecar 与 measure catalog 的 `--check` 都必须幂等。

自定义 workbook 不使用额外的 `source='workbook'`。新增 `custom_workbook_unit_authority.schema.json` 与 Pydantic `CustomWorkbookAuthorityManifest`：顶层固定 `schema_version='custom-workbook-unit-v1'`、`workbook_sha256`、`preflight_digest`、`contains_amounts`、非重复 `regions`；每个 region 必须有稳定 `region_id`、`sheet_uid`、A1 `cell_range`、`measure_kind='amount'`、`unit:yuan|qian|wan`、`values_already_in_declared_unit: Literal[True]`，以及只允许引用 preflight 候选的 `label_binding_id` 和期望中文单位标签。`mapping.py::CustomProjectionManifest` 同步增加每个 managed region 的稳定 `region_id/sheet_uid/cell_range/measure_kind`，不保存单位；`contains_amounts=false` 只在 semantic preflight 的所有 managed numeric region 都被明确分类为非 amount 时成立，unknown/重叠 region 是 blocker。

选择两阶段确认而不是在首次上传前要求服务端身份。该模块保持现有 camelCase wire：

1. `POST /api/custom-template-ingestion/ingest` 仍只接一个 xlsx/xlsm 文件，沿用 quarantine 大小/MIME/magic 校验，返回 `artifactId/sha256/state`；不接 authority manifest，也不调用 preflight/finalize/instantiate。
2. 新增 `POST /api/custom-template-ingestion/artifacts/{artifact_id}/preflight`，strict body 只含 `artifactSha256`。router 先按认证用户组织 scope 取 artifact 并比较 64 位 hash，再调用现有 `run_semantic_preflight` 和 mapping 生成器；响应含 `artifactId/artifactSha256/preflightDigest` 及逐 sheet 的稳定 `sheetUid`、逐 region 的 `regionId/cellRange/measureKind/labelCandidates`。`preflightDigest` 对 artifact hash、scanner/policy版本和排序后的 region/label 候选取 canonical SHA-256。
3. 新增 `PUT /api/custom-template-ingestion/artifacts/{artifact_id}/unit-authority`。strict body 为 `artifactSha256`、`preflightDigest` 和最多 500 个 `regions`；region ID 不重复，且必须恰好覆盖 preflight 的全部 amount region、不得包含非 amount/unknown region。每项只提交 `regionId/unit/labelBindingId/valuesAlreadyInDeclaredUnit=true`，sheet/range/kind 与期望标签由服务端候选回填，客户端不能改。canonical JSON 上限 64KiB；服务端在 quarantine 内原子写 hash-bound authority manifest/digest。同 artifact+digest 重放幂等，已有不同确认返回 409而不覆盖。
4. 新增 `POST /api/custom-template-ingestion/artifacts/{artifact_id}/finalize`，strict body 只含 `artifactSha256/preflightDigest/unitAuthorityDigest/approvalIntentId/idempotencyKey`。router 从服务端记录构造 `FinalizeLock`，调用现有 `run_finalize_saga`；缺 authority、任一 digest 漂移或 ACK 未全通过不得 ACTIVE。新增 `POST /api/custom-template-ingestion/publications/{publication_id}/instantiate`，strict body 为 `projectId/workingPaperId`；先校验项目 edit、底稿归属和 `custom_template.instantiate` capability，再调用 `instantiate_from_active`。同一事务创建/推进 `ProjectWorkbookInstance`、绑定当前 artifact，并把 manifest/digest 写入 `custom_workbook_unit_authorities`；service 只 flush，router commit。

`CustomIngestionWizard.vue` 从静态壳改为上述五步：文件选择与上传、preflight 结果、逐 amount region 单位/标签确认、finalize 状态、选择本项目底稿后 instantiate。artifact 字节或 preflightDigest 变化时清空确认并回到 preflight；仅 workbook 值变化但 region/label 逐值不变时也须对新 hash 重新运行 preflight，服务端可展示“沿用上次声明”建议，但 PUT 仍显式确认；结构/标签变化必须逐区域重确认。旧 `/api/custom-templates` 仍可读历史元数据，但它的 create/publish/version ID 不能传给 instantiate，AST 只允许新 ACTIVE publication 调 `instantiate_from_active/create_workbook_instance`。

scope 不符或无项目权限返回 403，artifact/publication/WP 不存在返回 404；artifact hash、preflight 或 authority CAS 变化返回 409 `CUSTOM_WORKBOOK_AUTHORITY_STALE`，结构漂移返回 409 `CUSTOM_WORKBOOK_STRUCTURE_CHANGED` 并携带新 preflight 摘要；schema、漏 region、非法单位/label 返回 422 `EXPORT_UNIT_POLICY_INVALID`。`validate_template_manifest.py --check` 同时校验 custom authority schema 与测试 manifest；只读 `scripts/check/check_custom_workbook_unit_authorities.py --check` 按当前 WorkingPaper artifact 重算 hash、region 和标签，不写库。历史 custom 文件不反推单位，没有匹配 authority 时仍可屏幕编辑，但正式导出/归档被阻断。

HTML 单元格写入、离线上传或 OnlyOffice forcesave 产生新 workbook bytes 时，`rebind_custom_workbook_authority` 必须先对新字节重跑同一 preflight。region/sheet/range/kind/label 集合逐值相同才可从旧 manifest 生成新 hash 的不可变 authority 行后推进 current artifact；任一结构/标签漂移则保持旧 current artifact，返回上述结构变化码并由向导重确认，不能自动沿用旧 hash。

新增 `amount_unit_policy.py`：

```python
@dataclass(frozen=True)
class ExportUnitRegion:
    region_id: str
    unit: AmountUnit
    divisor: Decimal
    label: str
    source: Literal['template_region','template_document','project','platform']
    values_already_in_declared_unit: bool = False

@dataclass(frozen=True)
class ExportUnitPolicy:
    policy_version: str
    document_type: str
    variant: str | None
    project_amount_unit: AmountUnit
    template_policy_digest: str
    custom_manifest_digest: str | None
    default: ExportUnitRegion
    regions: Mapping[str, ExportUnitRegion]
```

`resolve_export_policy(db, project_id, year, document_type, variant, region_ids, workpaper_id=None)` 是唯一解析入口。项目字段非法、sidecar 冲突/失效、同一区域多 authority、unknown amount kind、ratio 缺 scale，或 custom workpaper 当前文件 hash 没有匹配 authority 均抛 typed `ExportUnitPolicyError`。标准模板的优先级仍严格为 region > document > project > platform；custom authority 的 region 对外仍标 `source='template_region'`，但 `values_already_in_declared_unit=true`，exporter 只验证并原样保留该 region，绝不再除一次。该 flag 只允许来自 hash 匹配的 `CustomWorkbookAuthorityManifest`，其他来源必须为 false。`ExportUnitPolicy` 同时封存当次 `project_amount_unit`、标准 sidecar 的 `template_policy_digest` 和可空 `custom_manifest_digest`，即使局部 region 覆盖项目默认也保留完整 authority 输入；因此项目配置、模板 sidecar 或 custom manifest 任一变化都会产生新 policy digest并要求正式版本重建。`canonical_export_policy(policy)` 把枚举写为 wire value、Decimal divisor 写为规范十进制字符串、regions 按 region_id 排序，并用 UTF-8、sorted keys、紧凑分隔符生成 JSON bytes；`export_policy_digest` 只对此字节串取 SHA-256。snapshot 必须可由 `parse_export_policy_snapshot` 严格还原并重算出同一 digest，禁止把时间戳、绝对路径或用户偏好放入 snapshot。当数据集是 `legacy_unknown/legacy_declared` 时，divisor=1 的兼容导出可保持现有值并返回“单位口径未验证”warning；任何 qian/wan 缩放返回 409 `DATASET_UNIT_UNVERIFIED`，不得猜测。正式 exporter 的函数签名要求显式 `export_policy`，不得默认读取 displayPrefs。

前端 `utils/exportUnit.ts` 不再示例读取 displayPrefs，也不负责正式数值缩放；它改为校验 `ExportUnitPolicy` DTO、生成“正式导出单位：X（来源）”提示和 policy digest。新增只读 preflight `POST /api/export/unit-policy/preview`，请求含 project_id/year/document_types 及可选 workpaper_id，按 body 项目鉴权、含 wp 时再 `authorize_wp_read`，返回逐文档 policy 与 aggregate digest。TrialBalance、`useReportExport`、`useNoteExport` 和底稿公共导出入口都必须先经共享 `prepareFormalExport` 调 preflight，并把 `X-GT-Export-Policy-Digest` 传给正式请求；后端重算不一致返回 409 `EXPORT_POLICY_CHANGED`。客户端永远不提交单位值，所以个人偏好不能改变 authority。

### 6.2 正式导出接线矩阵

| 产物 | 唯一实现与必须收口的生产调用方 |
|---|---|
| 试算表 | 新 `trial_balance_exporter.py` 同时服务 `GET /api/projects/{id}/trial-balance/export?year=&view=detail|summary`、TrialBalance 两个正式导出按钮和 `bulk_tab._write_project_data_files`。summary 的浏览器 `exportMultiSheetData` 改为下载该端点；空白导入模板仍可客户端生成但不含金额。 |
| 合并本地数据交换 | `ConsolTrialBalanceTab.exportTrial`、`ConsolReportBreakdownView.exportBreakdown`、`ConsolNoteTab.exportNoteData/batchExportAllData` 及同类穿透数据出口固定为 `data_exchange`，只从未按 display prefs 缩放的原始模型构建。`useExcelIO` 注入首个可见“导出说明”sheet 与机器可读 `_GT_EXPORT_META`，至少含 `classification=data_exchange`、`formal=false`、`source_storage_unit=yuan`、project/year/source symbol；模板导出另归 `template`，审核结果等无金额出口归 `non_amount`。 |
| 财务报表 | `ReportExcelExporter.export(..., export_policy=...)` 负责缩放与标签；`reports.py` 单张路由删除自建 Workbook，改传 `report_types=[type]`；`report_export.py` 整套、bulk package、交付中心和 PDF 都调用同一 exporter。 |
| 附注 Word | `NoteWordExporter.export`、`export_with_meta`、`_export_template_mode` 与 `_export_template_mode_with_meta` 均新增无默认 keyword-only `export_policy`；programmatic/template 两支显式透传。`_render_table` 与 `render_cloned_table` 的共享输入固定为 `ExportUnitRegion + column_kinds + column_ratio_scales`，不从 exporter 实例默认值取单位；`note_template_block_fill.rebuild_block` 按稳定 `<section_id>/<table_id>` 从传入 policy 取 region 后交给普通/clone 内核。`disclosure_notes.py`、`note_export.py`、bulk/PDF，以及 `deliverable.py::render_disclosure_notes`、`full_deliverables_executor._run_disclosure_notes` 两个 `export_with_meta` 调用方均显式传同一 policy。 |
| 底稿 Excel | `export_workpaper_xlsx(..., export_policy=...)` 无默认参数。`wp_xlsx_export.py` 先 `authorize_wp_read(db,current_user,wp_id)`，再解析项目/模板 policy；`WpExportEngine.export_single` 是第二调用方，也必须传。`useAuditSheetTable.onExportData` 不再本地拼可归档 xlsx，改调用该正式路由。普通模板默认跟项目，render schema 可用稳定 region 声明模板单位；custom 路径必须加载与当前 workbook SHA-256 精确匹配的 `CustomWorkbookAuthorityManifest`，每个 region 以 `values_already_in_declared_unit=true` 原样保留。缺 manifest/hash/label/region 一律 `EXPORT_UNIT_POLICY_INVALID`，不得回退空白 workbook。 |
| 审计报告 | `placeholder_mapping_registry.json` 的 `total_assets/total_liabilities/total_equity/total_revenue/net_profit` 增加稳定 `region_id` 与 `measure_kind=amount`。`ReportBodyService.fill_placeholders(..., export_policy=...)` 改无默认 keyword-only 参数，以 region policy 同时格式化数值和单位标签，不再 `str(value)`；`refresh_financial_placeholders`、报告生成路由、full executor、组合包和 PDF source resolver 逐跳显式传同一 policy。 |
| 组合包 | `chain_workflow.export_package → ExportPackageService.export_package` 进入正式消费者注册表。财务报表与附注分别调用上述 exporter；可选审计报告调用 `ReportBodyService` 的真实 docx；可选审定表调用 `TrialBalanceExporter`。任何来源/policy 错误整包失败并删除半成品，不再捕获后写 `b''`，也不生成 `Audit report placeholder`/`Workpapers placeholder`；manifest 为每个成员记录 file hash 与 policy digest。 |
| 归档包 | `archive_inventory._deliverable_entries → archive_package_builder.build_archive_package` 是 copy-only consumer。inventory 必须选每个 task 的精确最新 `WordExportTaskVersion`，验证 task.file_path 与 version.file_path、version.file_hash 与磁盘 hash、policy pair 与当前解析 digest；custom workpaper 另验证 workbook authority hash。任一不符作为 blocking missing item，不进入 zip。 |
| PDF | `PDFExportEngine` 复用上述报表/附注 bytes；审计报告按 project+year 读取 `AuditReport.report_body_json`，用 `ReportBodyService.fill_placeholders/render_docx` 写到任务临时目录，正文未就绪 409。Office→PDF 后按固定文档顺序用已安装的 `pypdf` 合并；源 policy 随 task 保存供审计，不进行第二次缩放。 |

正式附注全量生成在开始渲染前只解析一次 policy，并把同一对象传到全部表格路径；生成完成后把 `canonical_export_policy(policy)` 和 digest 传给 `DeliverableService.render_and_store`。`render_and_store`、`create_version` 与 `_create_version_locked` 增加成对的 `unit_policy_snapshot/unit_policy_digest` 参数并统一调用 `validate_version_policy_pair(task, file_path, snapshot, digest)`：两者只允许同时为 null 或同时有效；当 `task.doc_type='disclosure_notes'` 且 `file_path` 非空时不论 `created_via` 都必须非 null，service 重算 digest 后才写 `WordExportTaskVersion`。DB pair CHECK 防止单列写入；其他含金额的正式 doc_type 由 `FORMAL_AMOUNT_DOC_TYPES` 注册表决定是否同样必填，非金额历史版本才可保持 null。

`OnlyOfficeCallbackService.build_editor_config` 在返回 config 前按所选 `version_no` 调 `validate_version_policy_pair`；正式附注底版无证据、pair 损坏或 snapshot 无法还原时返回 409 `EXPORT_POLICY_CHANGED_REQUIRES_FULL_REBUILD`，不创建编辑 room。回调从 doc key 取得 `base_version_no` 后，只从该版本读取 snapshot/digest，重算底版 digest 并把原 pair 显式传给 `render_and_store(..., inherit_unit_policy_from_version=base_version_no)`；禁止调用 `resolve_export_policy` 取得回调时的当前 policy。项目单位在打开与保存之间变化时，编辑版仍继承旧底版证据；该旧版之后可保存但不能通过 refresh/归档的当前-policy 检查，直到整份 rebuild。

`DeliverableRefreshService.refresh_section/refresh_all_stale_sections` 必须先通过 `DeliverableService.get_current_version` 同时取得文件、snapshot 和 digest，再按 task 的 project/year/template/report_scope 重新 `resolve_export_policy`。版本证据缺失、snapshot 无法严格解析、snapshot 自身 digest 不符或当前 digest 不等于版本 digest，均在解析 docx、清 stale 或创建新版本前抛 `ExportPolicyChangedRequiresFullRebuild`；router 固定映射为 409 `{code:'EXPORT_POLICY_CHANGED_REQUIRES_FULL_REBUILD', message:'正式导出单位策略已变化，请整份重新生成附注'}`。digest 相同时，`_replace_block_content`、`deliverable_refresh_rebuild.rebuild_refresh_block` 和 `note_template_block_fill.rebuild_block` 显式接收当前 policy，并把当前版本的同一 snapshot/digest写入 `refresh_section/refresh_stale` 新版本。只有 `render_disclosure_notes` 或全套生成的整份重建可采用新 policy 并建立新基线；局部刷新不得混写。

新增版本化 `backend/app/services/export_surface_registry.py` 与前端 `src/utils/exportSurfaceRegistry.ts`，二者共享 JSON Schema 定义 `surface_id/language/file/symbol/sink/classification/formal_policy_source/source_storage_unit/verify`。`EXPORT_SURFACE_REGISTRY` 不是人工挑选 exporter 的清单：Python AST 从 `FileResponse/StreamingResponse/Response` 的 Office/PDF/ZIP media type、zip `write/writestr` 和文件复制入口反查；TS AST 从直接 `XLSX.writeFile` 及 `exportData/exportMultiSheetData/exportToBytes` 的生产调用方反查。实际 sink 集合与 registry 必须双向相等，每个 symbol 恰一分类 `formal|data_exchange|template|non_amount`，登记 symbol 或 sink 失效也失败。

前端 `useExcelIO` 的数据型 API 增加无默认 `surfaceId`，由 registry 决定行为，调用方不能自行声称 classification。formal surface 必须先取得服务端 policy preflight，且 amount region 按 policy处理、禁止 import displayPrefs；data_exchange 必须提供 canonical raw rows 与合法 `sourceStorageUnit`，helper 自动写可见“数据交换文件（非正式出具）”说明页和 `_GT_EXPORT_META`，缺元数据拒绝下载；template 的运行时/fixture 谓词证明只有表头说明没有业务行；non_amount 的列 kind/fixture 必须全为非 amount。直接 `XLSX.writeFile` 除 `useExcelIO` 内部唯一 sink 外禁止存在。具体裁决固定为：TrialBalance summary 与 `useAuditSheetTable.onExportData` 改后端 formal；合并试算、差额、附注当前/批量数据为 data_exchange；合并模板为 template；审核报告若字段仅状态/文本/差异说明且无金额才可 non_amount，否则按 amount kind 归 formal/data_exchange，不能靠名称豁免。

后端 formal 行继续由 `FORMAL_EXPORT_CALLERS` 作为 registry 的派生视图，逐跳扫描 `ReportExcelExporter.export`、`NoteWordExporter.export/export_with_meta`、`ReportBodyService.fill_placeholders`、`export_workpaper_xlsx`、TrialBalance workbook、PDF source resolver、`chain_workflow.export_package → ExportPackageService.export_package`，以及 refresh 的 `rebuild_refresh_block → rebuild_block → _render_table/render_cloned_table` 私有链；要求每层显式传 policy/region、column kinds/ratio scales和版本 digest。copy-only 派生视图至少含 `archive_inventory._workpaper_entries/_deliverable_entries`、`archive_package_builder.build_archive_package` 与 custom workbook copy，并从 source symbol 逐跳到版本/hash/policy或 source-unit validator。新增调用未分类、policy 参数/版本证据/digest preflight被删除、或 verify 谓词无法从 AST/fixture取值都失败，不允许添加自由文本豁免。

归档 inventory 的 `InventoryEntry` 为交付件增加 `version_id/version_no/expected_file_sha256/unit_policy_snapshot/unit_policy_digest`。`_deliverable_entries` 按 `version_no DESC` 精确取 latest，要求 task 当前路径等于该 version 路径且磁盘 SHA-256 等于 version.file_hash；对 formal amount doc 重新解析当前项目/模板 policy，并与 version snapshot/digest 逐字节一致。

`_workpaper_entries` 不再凭 `WorkingPaper.file_path` 直接复制。它必须解析当前 `WorkpaperSyncEntryState → WorkpaperContentRepresentation → WorkpaperContentVersion → WorkpaperArtifact`，要求 file_path 指向的字节 hash 等于 current authoritative artifact hash。formal 内容版本必须有可严格还原且与当前 policy一致的 snapshot/digest；data_exchange 内容版本必须有 `source_storage_unit`，且文件内 `_GT_EXPORT_META` 逐值一致；custom formal 还须 authority manifest hash匹配。template/non_amount 只能在 `EXPORT_SURFACE_REGISTRY` 的对应谓词通过时归档。找不到当前不可变版本或金额历史文件缺 evidence 固定记 `ARCHIVE_WORKPAPER_UNIT_EVIDENCE_MISSING`，不以当前项目单位倒推旧文件。

交付件缺失记 `ARCHIVE_EXPORT_POLICY_MISSING`，变化记 `ARCHIVE_EXPORT_POLICY_STALE`，文件不符记 `ARCHIVE_DELIVERABLE_FILE_CHANGED`；底稿使用上述专用 code，均进入 `inventory.missing` 阻断包。`archive_package_builder` 只消费已验证字段并把 content/version id/no、file sha256、classification、policy digest或 source storage unit 写进每个 manifest entry；打包期间再次流式算出的 hash 不同则删 `.part` 并失败。项目单位变化后旧 formal 版本因此必定阻断，用户必须先整份重建。

`ExportPackageService` 对一致性警告仍可按既有 `force_export` 生成 `_warnings.txt`，但 source/policy 错误绝不受 force 影响。报表、附注、审计报告、审定表四类请求产物必须真实非空且通过各自文件 magic/解析校验后才写 zip；任一失败清理内存包并向 route 返回对应 409/422/503，不把内部异常值或业务数据写日志。bulk 中普通无数据 tab 可按既有规则 fail-soft，但 `ExportUnitPolicyError`、custom authority 错误和正式组合包必需文件缺失一律 fatal。

### 6.3 直接 PDF 合同与鉴权

`ExportTaskCreate` 改为 `extra='forbid'`，字段为 `project_id: UUID`、`year: int(2000..2100)`、`document_types: 1..6 个去重 Literal['audit_report','balance_sheet','income_statement','cash_flow_statement','equity_statement','disclosure_notes']` 和 `password: str | None = None`；task_type 由数量派生，`password_protected` 不再是请求字段。password 为 `None` 时不加密；非 null 时按原字符串 `len(password.encode('utf-8'))` 校验 1~127 bytes，`''`、128 bytes 及以上返回 422 `EXPORT_PASSWORD_INVALID`，不 trim、不按字符数计。前端 `createExportTask`/`PDFExportPanel` 从 project store 取已解析年度，先用同一 `prepareFormalExport` 预检全部 document_types并发送 policy digest；年度为空不发请求，并停止发送漂移的 `password_protected`/单数类型。`PDFExportPanel` 同时删除没有协议承接的“报表语言”选择器与 `exportLanguage` 状态，组件测试断言该选择器不存在；本 spec 不做双语 PDF（第三轮评审 NIT，阶段 C 任务 10）。

密码在 FastAPI 进入 router 前即可触发 `RequestValidationError`，因此脱敏所有权放在实际注册的 `middleware/error_handler.py::validation_exception_handler`。对 `request.method='POST'` 且 path=`/api/export/create`，handler 对 `exc.errors()` 每一项只保留规范 `type/loc/msg`，结构化删除全部 `input` 与 `ctx`；`loc` 含 `password` 时把 msg 固定为“导出密码格式无效”，不得包含 validator 原异常。该路由的 body 根错误和额外字段错误也删除 input/context，防止整段 input 间接包含 password；其余路由保持现有错误详情。禁止序列化后字符串替换。空串、128-byte、list/dict 错误类型，以及“合法密码+额外字段”都使用唯一 marker 测响应、应用日志和审计日志零明文；移除 route redactor 的故障注入必须红。

create 在任何任务/文件写入前调用 `assert_project_permission(db,current_user,body.project_id,'readonly')`。status/download 先以 task_id 查询最小 `{id,project_id}`，不存在 404，再对该 project 调同一门；history 对路径 project_id 先鉴权。响应增加 export_year/document_types。任何路由都不允许仅凭 task UUID 读取另一项目。

新增 `formal_pdf_source_resolver.py` 与 `office_to_pdf.py`。财务报表类型调用 `ReportExcelExporter` 的真实行，附注调用 `NoteWordExporter`；审计报告按 project+year 读取唯一 `AuditReport.report_body_json`，调用 `ReportBodyService.fill_placeholders` 后在任务临时目录 `render_docx`，正文为空则 409，不复用其他年度文件也不生成占位页。转换只接受真实 PDF 输出：LibreOffice 不可用、超时、返回码非零、文件缺失或 MIME/`%PDF-` 头不符时，task 标 failed、清理临时文件、router commit 失败记录并返回中文 503；不得写 HTML fallback。多个 PDF 固定按审计报告→资产负债表→利润表→现金流量表→权益变动表→附注顺序用 pypdf 合并，任一来源失败整任务失败且 `file_path` 为空。

密码只沿 `create_export_task` 请求栈以内存变量传给无默认 keyword-only `PDFExportEngine.execute_export(task_id, *, password: str | None)`，不得传给 `create_export_task` 的 options/metadata，也不得放入 ORM、policy snapshot、临时文件名、日志 context 或异常文案。`execute_export` 在全部来源合并后创建最终 `PdfWriter`；password 非 null 时调用 `writer.encrypt(password)` 后写最终文件，成功后才把 `ExportTask.password_protected=True`，None 则保持 false。加密/写盘失败只记录不含输入值的错误类别，清理临时与最终半成品，task 记 failed/file_path=null；请求作用域结束后不保留 password 引用。测试固定覆盖 `''`=0 bytes 拒绝、1 byte 成功、127 bytes 成功、128 bytes 拒绝，以及 `"密"*42+"a"`=127 bytes 成功、`"密"*42+"ab"`=128 bytes 拒绝，并捕获 ORM 写入、日志、task options、policy snapshot 和错误响应证明均无明文。

## 7. 错误处理与不变量所有者

| 操作 | 失败条件 | 调用方结果、恢复性与日志 |
|---|---|---|
| 偏好 GET/PATCH | 未登录；schema 非法；revision/首写竞争；DB 故障；审计摘要状态缺失 | 401/422；409 带 current 可恢复并只重试一次；DB 500。router 对 5xx `logger.exception`，不记录完整 prefs；实际 AuditLogMiddleware 精确路由 redactor 只写 revision/changed_fields，摘要缺失时写 redacted 标记而非原响应；前端缓存降级，不阻塞登录。账号隔离由 service 查询条件和 DB PK 双层负责。 |
| 本机缓存 | JSON/枚举/范围/大小非法，TTL>30天，Storage API 抛错 | 丢弃非法字段或整份过期缓存，回默认并标待同步；warning 仅开发日志。normalizer 是防 RangeError 的最后边界。 |
| 项目单位/store | 项目不存在、无权、归档、非法值；详情失败/晚到 | 404/403/423/422，无半写；详情失败 projectAmountUnit 保持 null，晚到响应丢弃。后端 enum+DB CHECK 拥有存储不变量，store sequence 拥有页面隔离。 |
| R 迁移（A/B/C 三组） | R_A：非默认项目单位、偏好行；R_B：import attempt；R_C：custom authority、export task 年度/policy/多文档或冲突镜像、Word policy 或底稿内容版本证据存在 | PostgreSQL `RAISE EXCEPTION`，该组 R 事务整单回滚且不 drop；仅 R_C 的无损单元素先回填旧列。迁移错误记运维 error，不自动清数据。 |
| 固定列 | 保存 key 不在 allowed、mandatory 被取消、列已删除、两设备 revision 冲突、PATCH 在途时再次本机编辑 | 运行时取交集并提示 stale；API 非法载荷 422。每项 mutation epoch只在响应确认同 epoch 时清除；409 以 server current 为基底只重放原代际未变化操作，一次重试后仍冲突则保留待同步，新 epoch进入下一次 flush；账号切换取消请求并清空 epoch。composable 拥有显示集合，displayPrefs store 拥有并发代际，页面不得自行拼 fixed。 |
| 单位检测/确认 | 非 edit 成员；bundle 缺失/hash 不全、digest 变化、missing/conflict 未确认、unsupported 标签；兼容 submit 仅带直接文件；调用旧同步 POST | 401/403；bundle 缺失 404/410；digest 变化 409 可重新预览；未确认/unsupported 422；直接文件只落 bundle 后 428 `SOURCE_UNIT_CONFIRMATION_REQUIRED`；两个旧同步 POST 固定 410 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB`。均在 queue/job/incremental 前；用户输入 warning，不记录账套正文，检测器崩溃 error。 |
| 增量入口/基准 | 调旧 apply；active dataset 缺失、不是 normalized_v1/yuan、证据/hash 不全、月份摘要变化、请求的 base UUID/digest 与当前 active 不同 | 旧 apply 410 且零调用；不合格基准 409 `BASE_DATASET_UNIT_UNVERIFIED`，CAS 变化 409/worker failed `BASE_DATASET_CHANGED`。submit/seal/activation 三次锁内复验同一 token；所有批次只写新 stage，可改做完整导入。 |
| 归一 worker/可见性 | 合同缺失/因子或 digest 篡改、确认人不符、非法/非有限 Decimal、重复归一、溢出、字段表不匹配、active 查询失败、stage seal 失败 | `LEDGER_AMOUNT_INVALID/NOT_FINITE` 携 locator 不携值；job/dataset 记 failed，attempt 先 cleanup_pending 后按 dataset_id 清空五表并 cleanup_done。四表 reader 查询 active 失败原样上抛，绝不退为裸未删；只有 sealed 且全证据/base token 复验一致可 activation-only。日志仅含 job/attempt/dataset/table/field。unit_normalization+attempt service+active predicate 是唯一边界。 |
| legacy inspect/apply/rollback | 共享 dry-run 未进入只读事务或 helper 另开连接；写入口闸门缺失；hash/row count 不符；不是最后未回滚版本；单位元数据快照/digest 或恢复分类不符 | 共享入口在第一条业务 SQL 前 `SET TRANSACTION READ ONLY`，状态不是 on 即 fatal并 finally rollback；误 UPDATE 由 PG 拒绝。写入口立即拒绝或单事务全回滚。apply 保存 presence-aware 单位快照；rollback 只在 after→before hash闭合后恢复原 legacy 分类并追加 history。本轮不调用真实写模式。 |
| 模板 sidecar/measure catalog/custom authority | JSON/schema 失败、ID 失效/重复、authority 冲突、kind unknown、ratio scale 缺失/越界、artifact/preflight CAS 变化、custom hash/region/label 不符 | `--check` 非零；运行时 409 `CUSTOM_WORKBOOK_AUTHORITY_STALE/STRUCTURE_CHANGED` 或 422 `EXPORT_UNIT_POLICY_INVALID`/`DISPLAY_MEASURE_CONTRACT_INVALID`，不 finalize/instantiate/生成文件。向导可重新 preflight/确认。标准 sidecar、custom 两阶段 manifest 与 catalog/override各自拥有不变量，exporter 不猜自由文本。 |
| 正式/数据交换 Excel、Word、组合包、归档 | 出口未分类/重复分类、formal 漏 policy、data_exchange 漏 source unit/说明、项目单位非法、unknown 数据需缩放、版本 policy pair 缺失/变化、custom manifest 不符、组合来源失败、底稿/交付件版本/hash/evidence 不符 | `EXPORT_SURFACE_REGISTRY` 静态门先阻断未分类；运行时通常 409/422/500/503。OnlyOffice 与 Word refresh 策略变化固定 409且零版本写入；data_exchange 缺 metadata 不下载；组合包无空文件/placeholder；归档缺底稿内容版本证据以 blocking code 阻断并删 `.part`。日志不含业务值。 |
| PDF | DTO/密码字节或类型边界/额外字段、无权、源未就绪、转换器缺失或失败、非 PDF 或加密写盘失败 | 422 `EXPORT_PASSWORD_INVALID`、401/403/409/503；全局 validation handler 对 create route 结构化移除所有 error input/context，密码项使用固定消息。失败 task 可留审计状态但 file_path 为空，临时文件删除；日志只记错误类别。请求 PDF 不允许返回 HTML，任何持久层/日志/错误响应不得含密码。 |
| AST 守卫 | parser 崩溃、输出缺键、固定生产 root 漂移、eligible 文件未解析/未登记跳过、核心符号未命中、扫描或候选 0、ledger schema/谓词失效、基线上升 | 一律非零退出并输出机器 JSON+中文摘要；范围问题固定 `SCAN_SCOPE_DRIFT`，CI 不使用 `|| true`。脚本通过 root 收窄、核心文件排除、parser skip、正反 fixture 和故障注入证明没有空转。 |

显著不变量及所有者：偏好合法性由 Pydantic+DB CHECK；当前用户隔离由 API 无 userId 加 service WHERE；偏好日志最小化由实际注册的 AuditLogMiddleware route redactor；effective 优先级与账号/项目时序由 Pinia store，scalar/page/tombstone mutation epoch由 displayPrefs 单点拥有。数据存元和只换算一次由 finite Decimal parser、unit contract validator、attempt state和worker；四表 staged 不可见由 fail-closed active predicate+read registry，客户科目可见性由独立 predicate、partial unique及短激活/回滚事务；增量 CAS 唯一 token 是 active dataset UUID+unit contract digest。正式单位 authority 与 canonical digest由标准 sidecar/custom 两阶段 hash-bound manifest+`amount_unit_policy`；Word 与普通底稿版本证据分别由 DeliverableService 和 WorkpaperContentVersion 写入校验；所有文件出口分类与调用方完整性由 `EXPORT_SURFACE_REGISTRY`。金额/非金额及比例尺度由 measure catalog/render schema；PDF 密码 DTO与结构化 422 脱敏由 schema+全局 error handler，明文生命周期由同步 router→engine 栈；legacy 可逆性由 presence-aware单位快照，shared PG 物理只读由独立 inspector 的第一条 SQL和单连接约束；迁移可逆性由 R 的数据库内 preflight；遗留单调性由范围闭合 AST 守卫。页面组件只消费这些结果，不重复判定。

## 8. 守卫、遗留台账与测试设计

### 8.1 唯一 AST 守卫

新增 `eslint-rules/lib/amount-display-analysis.cjs`，用 `vue-eslint-parser` 和 TypeScript parser 分析 Vue template/script AST；`no-bare-amount-cell.cjs` 与 `scripts/check-format-single-source.mjs` 只调用该库。分析器识别组件、formatter 的 import/局部别名、GtColumn/render schema kind、输入控件、正式输出代码和测试文件；不以 label/prop 关键字单独定罪。核心矩阵中 unknown numeric display 直接 violation，其他域才允许进入遗留台账。

扫描范围由版本化 `scripts/amount-display-scan-scope.json` 固定，不接受 CLI 用任意 root 覆盖；其 JSON Schema 用 `const`/完整集合约束 production scopes 恰为 `src/views/**/*.{vue,ts}`、`src/components/**/*.{vue,ts}`、`src/layouts/**/*.{vue,ts}`、`src/composables/**/*.ts`、`src/services/**/*.ts`、`src/stores/**/*.ts`、`src/utils/**/*.ts` 和 `src/types/**/*.ts`，只允许固定排除 `**/__tests__/**`、`**/*.spec.*`、生成的 `components.d.ts`。`--update-baseline` 无权改 scope/exclude；要变范围必须单独修改 schema 常量并经范围变异评审，不能与 baseline 更新同路。CLI 在仓库根调用 `git ls-files -z --cached --others --exclude-standard` 后按这些 scope 计算 `eligible_files`；每个 eligible 文件必须进入 `parsed_files`，或在有 JSON Schema 的 `parser_exemptions` 中以 path+reason_code+fingerprint 登记，其他 skip 均以 `SCAN_SCOPE_DRIFT` 失败。JSON 按 scope 输出 `eligible/parsed/skipped/exempted` 的数量与路径，且逐 scope 要满足 `eligible = parsed + exempted`；不能用全局非零掩盖某一目录被排除。

另建 `scripts/amount-display-core-symbols.json`，逐项登记 Dashboard、TrialBalance、ReportView、DisclosureEditor、GtWpRenderer、ConsolidationIndex/ConsolNoteTab/worksheet、LedgerPenetration、`GtAmountCell/GtMeasureCell/GtEditableTable/GtTableDisplaySettings`、displayPrefs/runtime，以及 Trial/Report/Note/WP/PDF 前端正式导出触发函数的文件、AST symbol/component 名和预期 scope。CLI 必须证明每项文件仍 eligible、被成功解析且符号命中；登记符号失效或核心文件从 Git 候选集中消失也报 `SCAN_SCOPE_DRIFT`。后端/前端全部文件出口由 §6.2 的 `EXPORT_SURFACE_REGISTRY` 闭合，账套入口由 `LEDGER_IMPORT_ENTRYPOINTS`、四表/客户科目读取由 `LEDGER_TABLE_READ_SURFACES` 闭合；各 registry 结果摘要并入 CLI JSON，但后端文件不进入前端 eligible 等式。合法新增生产文件自动进入对应 AST 反查集合，不要求先手工扩计数。

CLI 唯一 CI 命令为 `node scripts/check-format-single-source.mjs --check --json`，JSON 必含 `schema_version,scopes,eligible_files,scanned_files,parsed_files,skipped_files,candidates,core_symbol_results,ledger_read_surface_results,export_surface_results,core_violations,legacy_violations,exemptions,ledger_entries,baseline`；解析失败、字段缺失、任一 production scope 空、scanned_files/candidates=0、范围等式或任一 registry 双向集合不成立均 exit 2，违规/漂移 exit 1。`.github/workflows/ci.yml` 删除旧 ESLint 临时 JSON+`|| true` 统计 step，只运行该命令。`baselines.json` 删除 `_v3_eslint_rules.no-bare-amount-cell-tables` 和 `_v3_coverage_guards.no-bare-amount-cell-violations`，保留独立的 GtAmountCell usage 指标；新增唯一 `display-format-legacy-violations`。`--update-baseline` 只能在 scope/core manifest/ledger 全部可验证且新值不大于已提交值时写入；初始新口径必须经核心修复降到 ≤88，否则任务不完成。测试分别把 include root 收窄、排除一个核心文件、让 Vue parser 对一类文件返回 skipped，三者必须红在 `SCAN_SCOPE_DRIFT`；新增一个生产 `.vue` fixture 必须自动使 eligible+1。

`format-legacy-allowlist.json` 退役，改为 `scripts/amount-display-legacy-ledger.json` 和 `.schema.json`。每项固定字段为 path、AST node type、normalized fingerprint、measure_kind、disposition(`deferred|exempt`)、reason_code、owner、next_batch、verify。verify 只允许有限谓词：`bare-amount-display`、`component-prop`、`formatter-call`、`input-control`、`non-amount-kind`，各自参数由 schema 限定，禁止任意表达式/自由文本绕过。CI 逐项验证文件/指纹存在、谓词为真、分类与 analyzer 一致；已合规或理由失效的条目也失败，迫使删除。每个谓词都有正例、反例、parser crash 和空目录 fixture。

### 8.2 后端与前端测试

后端单元测试覆盖 schema 默认/边界、CAS 首写竞争、项目单位、UnitDetectionSummary digest、UnitConfirmationInput 条件字段、active dataset UUID+unit digest token、合同 factor/确认人/digest validator、Decimal None/null-token/非法/非有限值、正负 `ROUND_HALF_UP` 半分与 Numeric 边界、真实 converter 字段表、dataset/attempt 状态、ratio 两种 scale、ExportUnitPolicy canonical snapshot/digest、四版 sidecar、custom 两阶段 authority DTO/manifest、export surface 四分类和 PDF 密码 UTF-8 bytes/422 redactor边界。SQLite 测纯逻辑；PG 集成测唯一键竞争、CHECK、跨用户、所有已注册 preview/detect 的 edit 门、两个同步 POST 410 零旧服务调用、三条 submit、兼容直接文件 428 零 job、submit/seal/activation 三次 base token CAS、两引擎 staged 每批提交后的全登记 reader 可见结果、首次无 active/legacy NULL 行、active 查询故障、AccountChart partial unique/激活/rollback、每个故障点清 stage、sealed activation-only 与非 sealed 重建、短激活事务全败、custom ingest→preflight→authority→finalize→instantiate→WorkingPaper、旧 custom 链阻断、generate→OnlyOffice→refresh policy继承、组合包无 placeholder、普通底稿与交付件归档版本/hash/policy、R 迁移保护和对象级导出鉴权。端点必须用 TestClient 真发 GET/PATCH/config、全部 ledger preview/retired/submit/recovery、custom 五步、OnlyOffice config/callback、Word refresh、组合包、归档与 PDF 请求，不以 service 单测替代依赖链。

偏好日志测试必须挂载 `main.py` 的真实 middleware 顺序，PATCH 一个包含可识别金额单位、阈值和固定列 pageKey 的载荷，等待 `_write_log` 完成后直接查 `logs.new_value`；断言只含 revision/changed_fields，且对响应信封和 raw response 两种形状都成立。入口闭合测试从实际 `app.routes` endpoint identity 起步，与 `LEDGER_IMPORT_ENTRYPOINTS` 双向集合相等，再用 AST 调用图反查 ImportJob 创建、五表 writer、activate 与 resume，不能只断言已知三条 URL 存在。四表读取测试同样从 ORM table symbol 反查 `LEDGER_TABLE_READ_SURFACES`，逐个证明 exact active/force/legacy predicate，不接受文本命中注释。

PDF 422 测试使用真实 `main.py` exception handler 和唯一 marker，分别发送空、超长、list/dict password及“合法 password+额外字段”；响应 JSON、caplog、AuditLogMiddleware 持久结果都不得包含 marker或 `input/context`。结构化删除 redactor 后必须只红在泄漏断言。共享 PG 只读门在隔离 PostgreSQL 测试库开启事务后故障注入 UPDATE，精确断言 SQLSTATE `25006`/`ReadOnlySqlTransaction`，同时用 AST 证明 inspector 调用闭包不构造第二 engine/session。

前端 Vitest 使用真实 Pinia、fake timers 与真实 Element Plus DOM，覆盖默认 JSON、TTL/Storage 异常、300ms PATCH、账号与项目乱序、409 一次重试、两设备修改不同/相同 fixed pageKey、删除 tombstone，以及首个 PATCH 挂起时二次修改同一 scalar、同页 upsert→delete/delete→upsert、异页修改和账号切换；逐项断言只有发送 epoch 被清、新 epoch进入下一代。另覆盖 CSS 五类 computedStyle、fixed column 五 pageKey、amount/六种非金额、fraction/percent_points 双尺度、附注 column kinds/scales、Ledger/Trial presenter、三个导入 UI 的单位确认与 base UUID/digest原样提交、LedgerDataManager 不再调用旧 apply、custom wizard 五步/结构漂移重确认、设置路由权限、四类 export surface行为和 PDF DTO。PBT 只用于 Decimal/优先级/集合不变量，`max_examples=5`。

导出集成测试解析实际 xlsx/docx/pdf/zip：核对 raw元→policy值、单位标签、table region override、ratio 两种 scale、个人 prefs 切换不变、legacy_unknown 非元缩放被拒；custom workbook 跑完整 API 两阶段链后以当前 hash+manifest 原样导出，缺 manifest、改一字节、漏 region/label冲突/旧 custom template实例化均拒绝。审计报告五个财务 placeholder 各以非整值金额验证 policy divisor与标签，删除任一调用方参数必须红。`EXPORT_SURFACE_REGISTRY` 测实际 sink双向集合、四类正反谓词；合并 data_exchange 解析 `_GT_EXPORT_META`、可见说明及规范元值，useAuditSheetTable 不再触达本地 writeFile。HTTP、bulk、交付中心、两个 `export_with_meta`、组合包与 refresh rebuild 逐路径覆盖；组合包断言无零字节和 placeholder。Word 测所有有文件的 disclosure 版本 pair CHECK、snapshot可严格还原、digest一致、generate→OnlyOffice save→refresh继承、打开后项目 policy 改变仍继承底版但后续 refresh/归档阻断、历史无证据底版409、整份重建建立新基线。归档同时测试交付件和普通底稿 exact current version/artifact hash、formal policy pair或 data_exchange source unit，manifest含版本/hash/classification/evidence；历史金额底稿无证据、项目单位变化或文件字节变化均阻断。PDF 测 `%PDF-`、真实业务行、无 HTML fallback、跨项目 task id、加密后需正确密码读取。

### 8.3 故障注入与运行验收

所有新守卫做磁盘变异并逐字节还原，至少逐项删除/破坏：偏好鉴权和 user_id WHERE、revision 条件、AuditLogMiddleware 路由 redactor、userId cache key、scalar/page/tombstone mutation epoch 与发送代际清理、project contextSeq、DefaultLayout runtime、`--el-font-size-base`/gt-polish、GtWpRenderer style、五类 fixed 列、任一 measure kind/ratio_scale、附注普通/clone scale、bundle 重检测/digest、所有 preview/detect edit 门、两个同步 POST 410、三个 submit 合同必传、base UUID/digest 任一次复验、factor/confirmed_by/digest validator、旧 incremental apply 410、四表 writer `is_deleted=false`、active predicate 的 exact active/legacy NULL/fail-closed 三分支、每个登记 reader、AccountChart staged=true及激活/rollback顺序、attempt seal/cleanup/activation-only/短事务、每个金额字段、None/null token、非有限检查、ROUND_HALF_UP、shared inspector `READ ONLY`/单连接、legacy apply/rollback闸门及单位快照恢复、R 每个阻断条件、custom ingest/preflight/authority/finalize/instantiate逐跳CAS与旧链阻断、`EXPORT_SURFACE_REGISTRY` 每个 sink/分类谓词、审计报告五个placeholder policy、useAuditSheetTable formal改线、data_exchange marker/raw unit、每个正式 exporter policy、组合包 fail-fast、普通底稿/交付件 copy evidence、OnlyOffice/refresh pair、wp read鉴权、PDF对象鉴权、密码 validator/422结构化 redactor/内存-only、HTML fallback、扫描 root/核心文件/parser skip和每个 legacy-ledger谓词。变异必须红在预期断言，不接受因 import/语法先崩而“间接打红”。

Playwright 禁止复用共享 3030/9980、共享浏览器或随机现存业务数据。先完成产品代码、三件套、INDEX 本 spec 行及所有将提交的受跟踪文件更新，再用私有 index `write-tree`/`commit-tree` 生成不移动分支 ref 的 candidate commit，记录 `candidate_commit` 与 Git `tree_oid`；从该 commit 在 `tmp_global_display_settings/verify_wt` 建立、锁定 detached worktree，启动前要求 `git diff --quiet HEAD --` 与 `git diff --cached --quiet`。不再使用自算文件 digest作为代码身份。

后端启动钩子与 `vite.config.ts` 必须分别以自身 cwd 执行等价于 `git rev-parse HEAD^{tree}` 的只读解析，得到 `actual_tree_oid`，并与启动参数 `GT_EXPECTED_CANDIDATE_TREE_OID` 比较；解析失败、worktree不干净或不相等时进程拒绝启动。后端启动日志、`/api/health` body及 `X-GT-Candidate-Tree-Expected/Actual` headers，前端构建日志和 `document.documentElement.dataset.gtCandidateTreeExpected/Actual` 都暴露两值。Playwright 建会话前逐项要求 expected=actual=验收清单 tree_oid；仅回显环境变量的实现必须在“从错误 worktree启动”变异中失败。

终验结束后再次验证 detached worktree无受跟踪改动。任何测试后 spec/INDEX 修订、冲突合并或其他受跟踪文件变化都会产生新 tree OID，使现有证据失效并要求重建 candidate、重跑受影响门。允许创建本地提交时，提交必须直接引用已测 tree（可复用 candidate commit或用同 tree创建最终 commit），并断言 `git show -s --format=%T <final_commit>` 逐值等于验收记录；不得在受测 tree之上再提交未测文档修订。

新增版本化 `backend/tests/fixtures/global_display_settings_e2e.json` 和正式工具 `backend/scripts/e2e/prepare_global_display_settings_fixture.py`。fixture 只接受名称含【测试】的一个 standalone 项目和一个 consolidated 项目，以及由环境变量提供、已经用户批准的 A/B 测试账号；密码不进文件/日志。`--prepare` 幂等地通过平台 API创建/确认项目、把 standalone 作为数据节点挂入 consolidated 企业树并建立 A/B 两账号的明确项目成员关系，通过受控 seed 在独立 fixture namespace 写入 TrialBalance、ReportView、DisclosureEditor、HTML 底稿、合并页、LedgerPenetration 各一处可按稳定 ID 定位的原值 10000，并输出项目/账号/数据集/行/底稿/附注/合并节点对象 ID、before row counts/hashes 和 created/reused 标记。禁止 DOM 注入或直接改页面响应伪造金额。

测试以 `try/finally` 调 `--cleanup --run-manifest <path>`：本轮创建的对象走平台删除/回收站路径；复用对象只按记录 ID 恢复 before snapshot；受控 seed 行按 run_id 精确删除，随后逐表核对 before/after row count 与 canonical hash。清理失败使 AC-25 失败并保留 manifest 供人工恢复，不能报通过。逐页覆盖 Dashboard、TrialBalance、ReportView、DisclosureEditor、一个 HTML 底稿、合并页和 LedgerPenetration：读取 body/header/input/Teleport/wp cell 的 computedStyle，六个稳定金额格验证 10000 元→1.00 万元，切页/刷新/重登保持，B 账号不继承，dataset load 不重置，并下载解析五类正式文件证明个人偏好不影响。缺测试账号、standalone/consolidated 夹具、LibreOffice或独占服务时任务保持未完成；候选树 vue-tsc 与同一 HEAD 按文件/错误码/归一化信息比较并注入 TS2322，pytest/vitest/ESLint 失败也在同 HEAD 复跑归因。

## 9. 文件边界、实施顺序与外部依赖

后端新增/修改边界：

- 迁移/模型/API：三组动态 V/R（§2，A/B/C 各一对）、`models/user_display_preferences.py`、`models/core.py` 的 Project 字段、`models/report_models.py` 的 export task字段、`models/phase13_models.py::WordExportTaskVersion` 的 policy pair、`models/workpaper_sync_models.py::WorkpaperContentVersion` 的 surface/policy/source-unit证据、`models/dataset_models.py`/新 attempt model、`models/custom_workbook_unit_authority.py`、`schemas/display_preferences.py`、`models/report_schemas.py`、`services/user_display_preferences_service.py`、`routers/user_display_preferences.py`、`services/project_config_service.py`、`routers/project_config.py`、`models/audit_platform_schemas.py`、`routers/project_wizard.py`、`router_registry/system.py`。`middleware/audit_log.py` 只增加偏好 PATCH redactor；`middleware/error_handler.py` 只增加 PDF create validation error 的结构化字段删除；`main.py` 不改注册顺序。各组 R 包含 §2 的本组 fail-closed 无损预检。
- 导入：`ledger_import/{unit_normalization,attempt_service,entrypoint_registry}.py`、`dataset_unit_contract.py`、`dataset_query.py`、`dataset_service.py`、`account_chart_service.py`、`ledger_import/{detector,orchestrator,pipeline,converter,writer,incremental_merge}.py`、`ledger_import_upload_service.py`、`ledger_import_application_service.py`、`routers/{ledger_import_v2,ledger_datasets,account_chart,data_import,ledger_penetration,ledger_data}.py`、`import_job_runner.py`、`smart_import_engine.py`、`LEDGER_TABLE_READ_SURFACES` 登记的全部四表/客户科目生产 reader、只读 inspector 和未来写工具。只动项目 edit 门、两个同步 POST退役、单位合同、base UUID+digest CAS、active predicate/read registry、AccountChart可见性、attempt/stage-only writer、旧 apply退役与 convert→write/短激活事务块，不改其他账套管理能力。
- 度量/模板：`contracts/display_measure.py`、`note_table_header_library.py`、`note_table_enrichment.py`、`note_template_table_look.py`、`note_template_block_fill.py`、两版 standalone/两版 consolidated 目录的稳定 ID、ratio scale override、`note_table_measure_catalog.json`、`audit_report_templates/export_unit_policy.json` 及 schema/generator/validator。custom 路径增加 authority schema/model/service，并在 `routers/custom_template_ingestion.py` 增加 preflight/authority/finalize/instantiate 四条生产路由，复用 `services/custom_template_ingestion/{quarantine,semantic_preflight,mapping,finalize_saga,publication_ops,workbook_instance}.py`；HTML/离线上传/OnlyOffice 推进点只接新 hash preflight/rebind。旧 `custom_templates.py` 只加不能进入正式 instantiate 的门，不重构元数据功能。
- 导出：`amount_unit_policy.py`、新 `export_surface_registry.py`、`placeholder_mapping_registry.json`、`report_body_service.py`、`formal_pdf_source_resolver.py`、`office_to_pdf.py`、`trial_balance_exporter.py`、report/note/wp exporter、deliverable/OnlyOffice/refresh、`export_package_service.py`、`archive_inventory.py`、`archive_package_builder.py`、bulk/PDF，以及 chain/deliverable/export 和 trial/report/note/wp routers。只合并 policy/pair/hash/surface分类/fail-fast 块；普通底稿内容版本证据与 copy validator 同批。

前端新增/修改边界：

- 状态与设置：`stores/displayPrefs.ts`、`stores/project.ts`、`services/displayPreferencesApi.ts`、`services/auditPlatformApi.ts`、`services/apiPaths/{system,project}.ts`、`composables/useDisplayPreferencesRuntime.ts`、`utils/displayAmount.ts`、`types/displayMeasure.ts`、`views/DisplaySettingsView.vue`、`components/settings/DisplayPreferencesPanel.vue`、`router/domains/system.ts`、`layouts/{DefaultLayout,ThreeColumnLayout}.vue`、SystemSettings 仅 admin 复用面板块；displayPrefs 只新增 per-scalar/per-page mutation epoch、发送快照与冲突代际，不动 GridKernel 行为；不动 UserSettingsExtension。
- 公共显示：`styles/{gt-tokens,global,gt-table,gt-polish}.css`、`GtAmountCell.vue`、新 `GtMeasureCell.vue`、`GtEditableTable.vue`、新 `GtTableDisplaySettings.vue`、新 `usePreferredFixedColumns.ts`、`useGlobalTableLayout.ts`、`GtInfoBar.vue`、`GtWpRenderer.vue`。
- 核心页：Dashboard 只动字号/密度；TrialBalance、ReportView/权益/减值、DisclosureEditor、ConsolidationIndex/ConsolNoteTab/ConsolTrialBalanceTab/ConsolReportBreakdownView/worksheet、LedgerPenetration只动本 spec 的字号、kind/ratioScale、fixed、formatter、单位状态与明确 export surface块。`useExcelIO.ts` 只增加 mandatory surfaceId及四类受控行为，`useAuditSheetTable.onExportData` 改走正式后端。导入边界包含 AccountImportStep、LedgerPenetration、LedgerDataManager/Dialog/Page、ledgerImportApi/accounting paths 的摘要确认、base UUID/digest和旧 apply移除；`views/extension/CustomIngestionWizard.vue` 与新 API service 实现 custom 五步。PDFExportPanel/API 对齐 strict DTO 与密码提示，并删除“报表语言”选择器与 `exportLanguage` 状态（§6.3）。
- 治理与文档：共享 AST analyzer、格式守卫、scan-scope/core-symbol manifests、parser exemption与legacy ledger/schema、ledger reader和export surface registries、CI 单一步骤和 baseline、三份开发文档（屏幕 `docs/frontend/display-preferences.md`、导入 `docs/reference/ledger-import-unit-normalization.md`、导出 `docs/reference/formal-export-unit-policy.md`）、`scripts/check/candidate_tree_identity.py`、`backend/app/api/health.py` 的 expected/actual Git tree marker、`vite.config.ts`+`src/main.ts` 的 build marker、E2E fixture/tool和新测试。运行时必须从自身 `HEAD^{tree}` 得 actual，不能只回显启动注入。历史 `_archive` 只在本 spec/INDEX追加勘误，不回填旧文件。

实施顺序固定为阶段 A → B → C → 终验（任务号见 tasks.md，拆分说明见 §14），每阶段内仍是本批验证通过再进入下一批：

- 阶段 A 显示偏好与屏幕显示：1A 只读基线与 A 组迁移 → 2 偏好 API → 3 项目单位 → 4 effective store → 5 设置路由/CSS/固定列 → 6A measure 合同、附注 catalog 与核心屏幕 → 7 附注单位删除与数据集三态 presenter → 11A 前端 AST 守卫/legacy ledger/CI 单一步骤 → 12A 屏幕文档 → 13A 候选 tree 身份工具 → A-V 冒烟 → A-BK 备份。
- 阶段 B 账套导入单位归一：1B 只读基线与 B 组迁移 → 8 单位合同、入口闭集、staged 可见性与 base UUID+digest → 9 legacy 只读 inspector/未来写工具 → 11B 读取面与入口闭集接入守卫 → 12B 导入文档 → B-V → B-BK。
- 阶段 C 正式导出单位策略：1C 只读基线与 C 组迁移 → 10 标准 sidecar、custom 两阶段链、ExportUnitPolicy、正式 exporter/组合包/归档/PDF → 6C 附注普通/clone 内核消费 kind/scale（与 10 的附注路径同批）→ 11C export surface 接入守卫 → 12C 导出文档 → C-V → C-BK。
- 终验：13 冻结最终 candidate tree 后做全量回归与 HEAD 归因、全部变异、全页 Playwright 与正式下载、独立总评审和最终本地提交。

跨阶段依赖：A 不依赖 B/C。B 依赖 A 的任务 7 分类器/presenter（由任务 8 接入 normalized_v1）、11A 守卫 CLI 与 13A。C 依赖 A 的 `projects.amount_unit`（任务 3）、measure kind/ratio_scale 合同、附注 catalog 与稳定 table/column ID（任务 6A）；C 的 `DATASET_UNIT_UNVERIFIED` 门读取任务 7 的同一分类器，B 落地后 normalized_v1 数据集才允许非元缩放。

外部条件和降级点：字体只用本机系统回退，无下载依赖；偏好服务/Storage 失败按 §3 降级；LibreOffice 缺失时普通 Office 文件仍可生成，但“直接 PDF”验收保持失败并返回 503，不能用 HTML 代替；共享 PG baseline/dry-run 只经数据库级 READ ONLY 入口（legacy dry-run 为任务 9 inspector；其落地前及非账套状态的 baseline 用同纪律只读探针，§14），真实金额 apply/rollback 等用户再次放行；第二测试账号或【测试】项目不可用时相应 Playwright 不勾选。与 `ledger-incremental-append-true-merge` 并发实现重叠时不复制其合并算法：若其无 commit staged helper 已入库，本 spec 适配并加合同门/唯一调用方；否则实现 §5 的最小 staged helper。无论哪种，旧 HTTP apply 都必须 410，submit 前不得删 active 行。

工作只在当前分支进行，不新建分支、不 stash/reset/checkout 覆盖并发改动、不触碰 dev1.0、不推送。临时探针、截图、下载、日志和分离头验证 worktree 只放 `tmp_global_display_settings/`；`INDEX.md`、`models/core.py`、`LedgerPenetration.vue`、`gt-table.css` 等共享文件只合并 ownership 登记的块。并发状态不允许时保留未提交改动并报告，不强行提交。

## 10. 对设计评审 findings 的响应

`spec-review.json` 仍由独立评审方维护，本次没有改写或伪造评审结论。17 项 finding 均在 spec 层处理，无延期或忽略：

| Finding | 响应 |
|---|---|
| 1 | §5 固定服务端 bundle 重检测、完整 UnitDetectionSummary/digest、先合同后任何增量操作，并让两 worker 参数必填、旧 job fail closed。 |
| 2 | §5 增加 active dataset normalized_v1/yuan/证据完整门，legacy 返回 `BASE_DATASET_UNIT_UNVERIFIED` 且零写。 |
| 3 | §5 为 rollback 增加与 apply 等价五重闸门、逐表 canonical hash、history 位置和单事务反向更新。 |
| 4 | §6.1 新增受 `--check` 守护的结构化 sidecar、稳定 section/table ID 和逐区域 ExportUnitPolicy，自由文本只校验。 |
| 5 | §4.2 定义七类跨层 kind、column_ids/kinds、GtColumn/render schema 和两条 Word 路径。 |
| 6 | §6.3 统一 PDF strict DTO、四类对象鉴权、真实 source exporter、PDF-only/503。 |
| 7 | §6.2 纳入 TrialBalance summary/bulk、WpExportEngine 第二调用方和 wp read 鉴权，并加 AST caller registry/逐调用方变异。 |
| 8 | §5 的 dataset presenter 明确 normalized/legacy declared/legacy unknown 三态，后两者不显示“存储单位元”。 |
| 9 | §4.3 新增 wrapper/原生表共用 composable、组件 props/emits 和五类 pageKey allowed/mandatory 矩阵。 |
| 10 | §3 保留 `/settings` admin 门，新建认证 `/display-settings`，普通用户不接触系统配置。 |
| 11 | §2/§3 固定默认 JSON、四档线值、首写 409 current、PATCH 完整响应、30 天 TTL 与 Storage 异常。 |
| 12 | §3 把 projectAmountUnit 清空/sequence/失败降级落到 project store。 |
| 13 | §5 删除单列 opening_fc 设想，改真实 converter 对拍的 `_AMOUNT_FIELDS_BY_TABLE`，全部 qty/*_fc 不换算。 |
| 14 | §1/§4.4/§8.3 把 Dashboard 限为字号/密度/非金额验收，真实金额放六个有金额页面。 |
| 15 | §3 和 Out of Scope 删除 UserSettingsExtension 挂载与两个本地 key 迁移。 |
| 16 | §4.1 纳入 gt-polish，明确 Element Plus/输入/Teleport/wp 选择器和真实 DOM computedStyle。 |
| 17 | §8.1 退役 92/88 双指标，改唯一 fail-closed JSON 命令、拒绝上调 baseline 与有限谓词 ledger schema。 |

## 11. 恢复轮独立复审 findings 的响应

本节只响应 `tmp_global_display_settings/workflow_wf_85c9819dba953884/spec-review-recovery.md` 的 6 项 HIGH/MEDIUM finding；未重算基线、未改变已批准产品决策，也未扩展到评审未列出的产品代码。

| Finding | 处置 | 本次修订 |
|---|---|---|
| 1 HIGH | 已处理 | §5 将 `/account-chart/import-async`、`/ledger/smart-import` 及两个 preview 明确纳入同一 `UnitConfirmationInput`/shared helper；兼容直接文件请求只落 bundle 后 428，service 改为 token+确认无默认必传，三条 submit 都在 job 前重算并写完整合同。§8.2/§8.3、§9 和任务 8 同步补端点与 feature flag 两侧零写/换算证据。 |
| 2 HIGH | 已处理 | §5 固定退役 `/ledger-data/incremental/apply` 为 410，LedgerDataManager 只传计划；合并逻辑收为 worker 后不 commit 的 staged helper，AST 唯一调用方和 PG 整单回滚验收已补。 |
| 3 HIGH | 已处理 | §6.2 将 `export_with_meta` 两个生产调用方、template/programmatic、普通/clone 与 refresh 私有链全部纳入显式 policy；选择 `WordExportTaskVersion` 专用 snapshot+digest 列，刷新缺失/变化固定 409，只允许整份重建。 |
| 4 HIGH | 已处理 | §2 把 R 改为数据库内 `RAISE EXCEPTION` 的无损预检；年度、policy、多文档、冲突镜像、Word policy、项目单位或偏好存在均阻断，仅可表示单元素先回填旧列。任务 1 与 AC-21 补逐类回滚保护。 |
| 5 MEDIUM | 已处理 | §4.2 增加条件必填 `ratio_scale=fraction|percent_points`，贯穿标题行库/override/catalog/API/GtColumn/render schema/屏幕和两条 Word 路径；固定 0.2 与 20 双夹具，未知核心比例尺度 fail closed。 |
| 6 MEDIUM | 已处理 | §6.3 固定 PDF password 的 None/1~127 UTF-8 bytes 合同、0/128 拒绝、不 trim；明文只在同步 router→engine 内存参数中存在，数据库只写 `password_protected`，补中文边界和无明文持久化/日志测试。 |

六项均已处理，无 backlog 或忽略项。

## 12. 本次恢复复审 findings 的响应

本节响应当前门文件 `tmp_global_display_settings/workflow_wf_85c9819dba953884/spec-review-recovery.json` 指向评审的 5 项 HIGH、5 项 MEDIUM；按恢复契约未重跑基线、未改变已批准产品决策、未修改评审门文件或 INDEX，也未顺手实现 NIT。本节与当前 §2~§9 的具体协议覆盖 §11 中已被本轮证明过窄的历史响应措辞，§11 保留作审计轨迹，不作为相冲突的实现选择。

| Finding | 处置 | 本次修订 |
|---|---|---|
| 1 HIGH | 已处理 | R8、§5、任务 8、AC-14/15 将已注册 `/account-chart/import` 与 `/api/projects/{project_id}/import` 固定退役为 410，全部 preview/detect 改项目 edit 门；新增从真实 `app.routes` 及 ImportJob/五表 writer/activate 反查的可执行入口注册表和 TestClient/AST 双向守卫。 |
| 2 HIGH | 已处理 | §2/§5 引入 `ledger_import_attempts` 与 staged 原子可见协议。两引擎/writer 的批次 commit 只写新 stage，active 在 seal 前不变；失败确定性清空，只有证据完整 sealed stage 可 activation-only，其余 retry 新建 stage；最终 merge/active 切换/记录/outbox/attempt 用短事务。 |
| 3 HIGH | 已处理 | R9、§2/§6.2 把 policy pair 约束扩大到所有有文件的正式附注版本；OnlyOffice 打开前验底版，回调严格按 `base_version_no` 继承，项目 policy 并发变化不改写旧证据；refresh 继承，整份 rebuild 才建立新 policy，并增加 DB pair CHECK。 |
| 4 HIGH | 已处理 | R9、§6.2、任务 10、AC-20/22 登记组合包和 copy-only 归档消费者；组合包删空 bytes/placeholder 并 fail-fast，归档绑定 exact latest version、文件 hash、snapshot/digest 与当前 policy，manifest 记录版本/hash/digest。 |
| 5 HIGH | 已处理 | R9、§2/§6.1/§6.2 删除 `source='workbook'`；选择与 workbook SHA-256 绑定的不可变 custom authority manifest，逐 amount region 声明单位/label/已是声明单位。入库与每次内容版本推进都核验/rebind；缺失、hash 或结构漂移时两个导出调用方和归档均 fail closed。 |
| 6 MEDIUM | 已处理 | R2、§3、任务 4/5、AC-04/09 将 fixed 冲突粒度降到 pageKey：独立 dirty 集合和 tombstone，409 以 server current 为基底只重放脏页；覆盖不同页、同页、删除、第二次冲突与账号切换。 |
| 7 MEDIUM | 已处理 | NFR、§2/§7、任务 2、AC-02 指定实际注册的 `middleware/audit_log.py` route redactor，只落 revision/顶层 changed_fields，缺摘要也不回退完整响应；真实 middleware TestClient 查询 logs 并做移除 redactor 变异。 |
| 8 MEDIUM | 已处理 | R8、§5、任务 8、AC-15/17 固定 factor 映射、canonical contract digest、detection/confirmation/created_by 关系；每次 claim/retry 重验。金额唯一使用 `Decimal(str(value))*factor`、`ROUND_HALF_UP` 到 0.01，再检查 18 位整数边界。 |
| 9 MEDIUM | 已处理 | R10、§8.1、任务 11、AC-23 增加固定 Git 候选 scope、逐 scope eligible/parsed/skipped/exempted 等式和核心符号 manifest；root 收窄、排除核心文件、parser skip 均红 `SCAN_SCOPE_DRIFT`，新生产文件自动纳入。 |
| 10 MEDIUM | 已处理 | §8.3、任务 13、AC-25 禁止共享 3030/9980；锁定 detached 候选 worktree，前后端 marker 对拍 tree digest；版本化【测试】fixture 准备 standalone/consolidated、A/B 成员和六处 10000，finally 按对象 ID 恢复/删除并做 row/hash 对账。 |
| 11 NIT | 本轮未改 | 恢复契约限定只修 HIGH/MEDIUM，故没有借本轮删除 PDF“报表语言”控件，也没有新增双语 PDF。该 NIT 不改变上述需求与架构，可由后续实施评审决定是否单独收口。 |

本轮 10 项 HIGH/MEDIUM 均已处理，无 HIGH/MEDIUM backlog 或忽略项。

## 13. 当前门第二次迭代 findings 的响应

本节只响应当前 `spec-review-recovery.json` 所指评审的 4 项 HIGH、6 项 MEDIUM。未重跑 baseline、未改变已批准产品决策、未编辑门文件或 INDEX，也未处理 NIT。§12 保留为上一轮历史；本节及修订后的 §2~§9 是本次实现依据。

| Finding | 处置 | 本次修订 |
|---|---|---|
| 1 HIGH | 已处理 | R8、§5、任务 8、AC-16 固定四表 staged=`is_deleted=false` + fail-closed active predicate；无 active 只读 NULL-dataset legacy，查询失败上抛。AccountChart staged=true，激活/rollback按 partial unique顺序切换；read registry与逐批并发读测试闭合全部生产读者。 |
| 2 HIGH | 已处理 | 删除所有 `base_dataset_version`，选择现有不可变 dataset UUID + canonical unit contract digest。incremental detect、前端 DTO、job/attempt及 submit/seal/activation 三次锁内复验贯通，变化统一 `BASE_DATASET_CHANGED`。 |
| 3 HIGH | 已处理 | §6.1 改为 ingest→preflight→unit-authority PUT→finalize→instantiate 可达协议；首传不要求服务端身份。CustomIngestionWizard接真实 API和漂移重确认，旧 custom-templates不能正式实例化，API→WorkingPaper authority用全链测试守护。 |
| 4 HIGH | 已处理 | R9、§6.2、任务 10/11、AC-20/22 新增从前后端真实文件 sink反查的 `EXPORT_SURFACE_REGISTRY` 与四类强制分类；审计报告五金额 placeholder显式 policy；useAuditSheetTable改正式后端，合并本地导出固定 data_exchange；普通底稿归档绑定内容版本/hash/policy或source unit。 |
| 5 MEDIUM | 已处理 | R2、§3、任务 4、AC-04/09 为标量、pageKey和tombstone增加 mutation epoch与发送快照；响应仅清同 epoch，新编辑进入下一代，409一次重试不吞在途新值。 |
| 6 MEDIUM | 已处理 | R8、§5、任务 8、AC-17 固定 converter 输出 `Decimal|None`、None hash null token、非法非空值 fatal、乘法前后 finite检查及 `LEDGER_AMOUNT_NOT_FINITE`，两引擎/dry-run/hash共用 helper。 |
| 7 MEDIUM | 已处理 | R9、§6.3、§7、任务 10、AC-21 指定真实 `middleware/error_handler.py` 对 PDF create全部 validation errors结构化删除 input/context，密码项固定消息；错误类型与额外字段也做 marker无泄漏测试。 |
| 8 MEDIUM | 已处理 | R10、§8.3、§9、任务 13、AC-24/25 改用私有 index生成 candidate commit/tree；后端与 Vite从自身 cwd解析 `HEAD^{tree}` 并比较 expected/actual，最终提交 tree OID必须等于受测 tree，后改即重验。 |
| 9 MEDIUM | 已处理 | R8、§5、任务 9、AC-18 为 apply history保存 presence-aware单位元数据 snapshot+digest；rollback先闭合 after→before hash，再精确恢复原 legacy分类并追加独立 history，增量门重新拒绝。 |
| 10 MEDIUM | 已处理 | NFR、§5/§8、任务 1/9、AC-18 将共享 PG baseline/dry-run分离为只读 inspector；第一条业务 SQL为 `SET TRANSACTION READ ONLY`、单连接、finally rollback，并以 SQLSTATE 25006故障注入和三类 hash对拍守护。 |
| 11 NIT | 本轮未改 | 门契约只允许修 HIGH/MEDIUM；PDF“报表语言”控件未在本次删除，也未扩展双语 PDF。 |

本次 10 项 HIGH/MEDIUM 全部处理，无 backlog 或忽略项。

## 14. 阶段拆分（2026-10-29 结构调整）

本节只说明 tasks.md 按 brief 改为「阶段 A 显示偏好与屏幕显示 → 阶段 B 账套导入单位归一 → 阶段 C 正式导出单位策略 → 终验」分段门禁后的设计落点。§2~§9 的协议与已批准产品决策不变，§10~§13 已响应的评审项不重新处理；迁移分组见 §2，顺序与跨阶段依赖见 §9，AC 归属见 requirements「AC 与交付阶段对应」。

| 原任务 | 拆分后 | 依据 |
|---|---|---|
| 1 | 1A / 1B / 1C | §2 三组 V/R；每组先现扫迁移号并做本阶段只读基线 |
| 6 | 6A / 6C | 6A：七类 kind、ratio_scale、附注 catalog、稳定 table/column ID 与屏幕；6C：`NoteWordExporter._render_table` 与 `render_cloned_table` 消费 kind/scale，依赖任务 10 的 `ExportUnitRegion` |
| 11 | 11A / 11B / 11C | 11A：前端屏幕金额 AST 守卫、legacy ledger、CI 单一步骤；11B：`LEDGER_TABLE_READ_SURFACES` 与 `LEDGER_IMPORT_ENTRYPOINTS` 闭集；11C：`EXPORT_SURFACE_REGISTRY` |
| 12 | 12A / 12B / 12C | 屏幕、导入、导出三份文档（§9 治理与文档） |
| 13 | 13A + 13 | 13A 候选 tree 身份工具先于阶段 A 冒烟实现；其余留终验 13 |

只在阶段之间成立的三处临时状态：①任务 7 的后端数据集分类器在阶段 A 只产出 legacy_declared 与 legacy_unknown（存在 `unit_normalization` 也按 legacy_unknown fail closed），API 枚举与前端 presenter 已含 normalized_v1 并以 DTO 夹具测试；阶段 B 任务 8 接入 `unit_normalization.py` 的严格合同解析（与增量基准门同一口径重算 canonical digest）后才产出 normalized_v1。②§8.1 的 CLI JSON 键按阶段递增：阶段 A 固定前端键，`ledger_read_surface_results` 自阶段 B、`export_surface_results` 自阶段 C 起成为必含键，每次递增 `schema_version`；终验以 §8.1 完整键集合为准，任何阶段都不得用空结果或“待实现”占位键充当通过。③§5 规定共享 PG baseline 走数据库级只读入口，而正式 inspector 由阶段 B 任务 9 交付；在此之前及非账套状态（1A 项目/schema、1C 导出任务与版本证据）使用 `tmp_global_display_settings/` 下的只读探针，纪律与 inspector 相同：第一条业务 SQL `SET TRANSACTION READ ONLY`、`SHOW transaction_read_only` 为 on、单连接、finally rollback，隔离 PG 故障注入 UPDATE 得 SQLSTATE 25006；任务 9 落地后，数据集单位分类与 legacy dry-run 一律以 inspector 输出为准。

阶段收口：每阶段末 `-V` 从 13A 锁定的分离头候选 worktree 启动独占端口做运行时冒烟/验证，只用【测试】项目或回滚事务，A/B 测试账号不可用即暂停请示；该证据不替代终验 AC-24/AC-25。`-BK` 用私有 index `write-tree`/`commit-tree` 生成不移动任何 ref 的备份 commit，OID 记入工作流目录。第三轮评审 NIT 并入阶段 C 任务 10：删除 PDF“报表语言”选择器与 `exportLanguage` 状态并加组件断言，不做双语 PDF（§6.3、§9）；§12/§13 中“本轮未改”的行保留为当时记录。

## 15. 阶段 A 设计门响应（wf_daadceb7157e9d26 首轮自检）

本节是阶段 A 设计门首轮的设计作者自检。当时门文件尚不存在，没有评审 finding 可响应；复核按 HEAD `236cd334e` 工作树逐项读取阶段 A 涉及的代码，只补三类问题：与代码现状不符、阶段 A 任务缺可执行判据、A 与 B/C 的接口不清。已批准产品决策与 §10~§13 已响应项不变。A1~A10 与 §2~§9、§14 冲突时以本节为准，原节保留为历史；任务对应关系见 tasks.md 任务 0 的本轮记录。探针与输出在 `tmp_global_display_settings/workflow_wf_daadceb7157e9d26/`。

**A1 迁移取号与落库前核对（1A/1B/1C 与各 `-V`）。** `MigrationRunner.run_pending` 只按版本号判断是否已应用（磁盘 V 文件减去 `schema_version.version`），gt-plan `migration_status` 也只扫磁盘。§2 的三处来源都看不到目标库里其他会话已登记、却未入库的版本；一旦撞号，本组 V 会被当成已应用而静默跳过。取号因此增加第四处来源：目标库 `schema_version` 的最大版本号，经 §14 同纪律的只读探针读取，取号为四处最大值 +1。落库只经显式 `MigrationRunner(...).run_pending()`；执行前用只读探针计算「候选树 V 文件 − 已登记版本」，结果必须恰好是本组 V 文件且该号仍未登记。结果含其他版本（包括他人已入库、尚未落库的迁移）即停止并请示，不代他人落库。候选后端按 A2 的候选模式启动，不跑启动期迁移。

**A2 候选验证实例（13A，供 A-V、B-V、C-V 与终验复用）。**
- 触发：只有进程环境含 `GT_EXPECTED_CANDIDATE_TREE_OID`（40 位小写十六进制）时进入候选模式，值非法即拒启动。未设置时身份钩子不调用 git，health 返回 `candidate_tree: null` 且不加 header，Vite 不注入 marker；共享开发服务、`start-dev.bat` 与 `build_exe.py` 打包行为不变。
- 后端：在 `app/core/startup_registry.py::STARTUP_TASKS` 首位新增 critical 任务 `verify_candidate_tree_identity`（先于 `run_migrations`），以 backend 目录为 cwd 执行 `git rev-parse HEAD^{tree}`，并按 §8.3 口径检查受跟踪改动；不相等、有改动或解析失败即抛错，lifespan 失败，进程退出。结果在启动时只算一次并缓存，`/api/health` 读缓存输出 body `candidate_tree:{expected,actual}` 和 `X-GT-Candidate-Tree-Expected/Actual` header，请求期不调用 git。候选模式还要求环境变量 `PORT` 存在且不等于 9980。
- 共享状态隔离：候选实例与共享后端连同一 PG 和 Redis，所以只运行只读或进程内初始化任务。新增 `CANDIDATE_MODE_POLICY: dict[任务名, 'run'|'skip']`，守卫断言其键集合与 `STARTUP_TASKS` 的任务名集合逐值相等，新增任务未登记即失败。当前裁决：`run_migrations`、`replay_startup_events`（重放共享事件与导入 outbox）、`acnr_invalidation_outbox_start`、`recover_ai_chat_runs`、`acnr_catalog_snapshot_gc` 以及 workers 阶段全部任务（`_WORKER_BINDINGS` 的 13 个 worker 与 ImportJobRunner）为 skip，其余为 run。不跳过时，候选实例会认领他人的导入作业、重放他人的 outbox，并成为审计日志 writer 的第二个副本。现有 `run_startup_tasks` 把 skip_condition 抛错当作「照常运行」，候选模式的跳过判定不得沿用这一点：判定出错即启动失败。
- 前端：校验只写在 `vite.config.ts` 的 `defineConfig` 回调里，模块顶层不调用 git。候选模式要求 `VITE_DEV_PORT` 不等于 3030、`VITE_API_BASE_URL` 必填且端口不等于 9980，并关闭 AutoImport 与 Components 的 `dts` 输出；否则开发服会改写受跟踪的 `src/components.d.ts` 与 `src/auto-imports.d.ts`，worktree 随即变脏。marker 经 `define` 注入，`src/main.ts` 先判断 `typeof` 再写 `dataset`，未设置时不写。
- 配置与读取：DATABASE_URL、Redis、`STORAGE_ROOT` 等经进程环境变量注入主工作树的现值，不把 `.env` 或密钥复制进候选树；阶段 A 冒烟对 storage 只读。Playwright 建会话前经前端代理读取 `/api/health`，要求 expected=actual=验收 tree OID，这同时证明代理没有指向共享 9980。
- 判据：在 §8.3 的三种变异之外，再用磁盘注入并逐字节还原验证三点：未设置环境变量时 git 调用次数为 0；候选模式下 skip 集合内的任务在启动报告中为 skipped；代理目标端口为 9980 或开发端口为 3030 时拒启动。

**A3 运行时安装点（任务 5）。** 顶层路由 `/ledger-workbench/:projectId` 的 `LedgerStandalonePage.vue` 不在 DefaultLayout 下，却直接挂载核心页 LedgerPenetration；只在 DefaultLayout 调用 runtime，这个窗口就既不加载账号偏好，也不写根变量。`useDisplayPreferencesRuntime()` 改为按 Pinia 实例幂等安装：首次调用在 detached `effectScope` 中建立账号加载、根变量与 `useGlobalTableLayout` 监听，之后的调用返回同一句柄，组件卸载不销毁。调用点为 DefaultLayout（R5）和 LedgerStandalonePage。守卫按路由表 AST 遍历带 `meta.requireAuth` 的顶层路由：根组件必须是这两者之一，或列在带理由的豁免表中（当前只有 `/ai-chat` 的 AIChatView，无核心金额表）。新增顶层路由未归类即失败，删除任一调用点的变异必须红。

**A4 displayPrefs 改写的兼容合同（任务 4、5）。** 探针现算 245 个生产文件调用 `useDisplayPrefsStore()`，其中 `fmt` 169 次、`fmtAmount` 55 次、`fontConfig` 28 次、`fmtDateTime` 与 `unitSuffix` 各 9 次。改写保留全部现有公开成员与签名，语义变化只有一处：`amountUnit` 改为只读的 effective computed（override ?? 项目 ?? yuan），`fmt/fmtAmount/unitSuffix/unitDivisor` 随之读 effective 单位与归一后的 decimals。其余偏好字段同样只读，写入只经 setter：新增 `followProjectUnit()` 与写删除墓碑的 `clearFixedColumns(pageKey)`，`setFixedColumns` 记 upsert epoch。生产代码里唯一的直接双绑是 ThreeColumnLayout Aa 面板的 6 处 `v-model="displayPrefs.*"`，随 compact 面板替换一并删除；vitest 源码守卫禁止生产代码对该 store 字段 v-model 或赋值。`ownerUserId` 为空时 setter 只改内存，不写缓存也不 PATCH，登录后被该账号的缓存或服务端值覆盖（`test/setup.ts` 在未登录时就调用 setter）。线值枚举沿用现有前端类型：`density=compact|default|comfortable`、`grid_edit_mode=excel|click|classic`、`font_size=xs|sm|md|lg`、`amount_unit_override=yuan|qian|wan|null`。PATCH 字段使用 strict 类型（StrictBool/StrictInt，不接受字符串数字，也不把布尔转成整数）；`highlight_threshold` 是 JSON number，取值 0~1 且至多 4 位小数，否则 422；DB 列为 `NUMERIC(5,4)`，响应必须输出 JSON number，不得序列化成 Decimal 字符串。

**A5 数据集单位状态 DTO（任务 7；A/B/C 接口）。** `GET /api/projects/{project_id}/ledger-import/datasets/active` 在有 active 时增加 `unit_state`，`GET .../ledger-import/datasets` 的每一项同样增加。原 `source_summary` 保留给其他读者，但 TrialBalance 与 LedgerPenetration 不再读 `source_summary.amount_unit`（源码守卫）。形状固定为 `{classification, declared_unit_label, source_unit, storage_unit, factor, normalization_version, contract_digest}`，由 `dataset_unit_contract.classify_dataset_unit_state(source_summary) -> DatasetUnitState`（frozen dataclass）唯一产生；阶段 C 的 `DATASET_UNIT_UNVERIFIED` 门读同一函数。阶段 A 判定：含 `unit_normalization` 键时为 legacy_unknown；否则顶层 `amount_unit` 为非空字符串时为 legacy_declared，`declared_unit_label` 取去首尾空白的原文（最多 20 字，`yuan/qian/wan` 映射为中文标签）；其余为 legacy_unknown。分类结果用不到的字段一律为 null。阶段 B 只替换「含 `unit_normalization`」这一分支：严格解析成功为 normalized_v1，并填来源单位、存储单位、因子、版本与 digest；解析失败仍为 legacy_unknown；字段名不变。前端 presenter 的输入是 `DatasetUnitState | null`：null（无 active 或请求失败）时不显示单位行；未知 classification 按 legacy_unknown 处理并记开发告警。

**A6 附注表对不上目录时的屏幕行为（任务 6A）。** `note_table_enrichment.carry_template_table_names` 先按表名、再按位序匹配模板表，首列表头不符就不对齐；这类已存表以及模板之外的表都没有 catalog 条目。附注详情与合并附注响应在 headers 同一层增加 `measure_status`：对上目录为 `matched`；对不上为 `unmatched`，此时 `column_ids/column_kinds/column_ratio_scales` 仍与 headers 等长，首槽（行标签列）的 ID、kind、scale 固定为 `label`、`text`、null，其余槽为 null；目录自相矛盾（如 ratio 缺 scale）为 `invalid`，同样置 null，接口不报 500。屏幕上 kind 为 null 的数值格只显示原值，不除单位也不加 %，表头旁显示「本表列语义未登记，数值按原值显示，未随金额单位换算」；固定列 allowed 集只含 `label` 与非 null 的 column_id。测试夹具包含一张首列表头不符的已存表和一张模板之外的表。

**A7 两处易错接线（任务 5、6A、7）。** ①`GtWpRenderer` 的 `runtime` 是 `useWorkpaperScaffold()` 返回的普通对象，`<script setup>` 模板不会解包其中的 ComputedRef；须先解构 `const { fontStyle } = runtime`，再绑定到 `.gt-wp-renderer` 根元素。测试断言根元素内联 `--wp-font-size` 在四档下依次为 11/12/13/14px，改成绑定嵌套 `runtime.fontStyle` 的变异必须红。②删除 `GtAmountCell` 的 `unit` prop：唯一生产调用方是 DisclosureEditor 的 7 处 `:unit="noteUnit"`，随任务 7 一并删除，GtGridCell 的文档示例同步修改；11A 分析器把 `<GtAmountCell :unit>` 判为核心违规。

**A8 扫描范围与代码现状（任务 11A；修订 §8.1 与 AC-23）。** §8.1 列出的 8 个 scope 漏掉 `src/shell`（33 个生产文件，含 2 个 .vue）、`router`、`constants`、`shared`、`directives`、`generated`、`config`、`i18n`、`permissions` 和根目录的 `App.vue`、`main.ts`，共 62 个生产文件；排除项只认 `__tests__` 与 `*.spec.*`，会把 components、composables 下 17 个 `*.test.ts` 算作生产代码。修订后，JSON Schema 的 `const` 固定的是 include 与 exclude 规则，不再固定目录清单：include 为 `src/**/*.{vue,ts}`，exclude 为 `**/__tests__/**`、`**/*.spec.*`、`**/*.test.*`、`src/stories/**`、`src/test/**` 与 `src/*.d.ts`（含生成的 `components.d.ts`、`auto-imports.d.ts`）。scope 按 Git 候选现算，为 `src/` 下每个顶层目录各一个，另加 `src:root`；新建顶层目录里的生产文件自动成为新 scope 的 eligible。include 与 exclude 只能通过修改 schema 常量改变，`--update-baseline` 与命令行参数都无权改；实际扫描规则与常量不一致即报 `SCAN_SCOPE_DRIFT`。每个 scope 要求 eligible 与 parsed 非零且 `eligible = parsed + exempted`；candidates 逐 scope 输出，只要求全局非零，因为 `permissions`、`types` 这类 scope 本来就没有金额展示候选。AC-23 已改为同一口径。按当前 HEAD 计有 18 个 scope、5439 个生产文件，实施时重算。

**A9 现有列语义模块的边界（任务 6A、11A）。** `components/workpaper/shared/amountColumnSemantics.ts` 与 `wpAmountInput.isAmountColumn` 按列标题选择可编辑控件（WpAmountInput 或 el-input-number），继续只用于输入控件选型。核心屏幕的显示换算只认 GtColumn、render schema 和 catalog 的显式 kind，不得调用这两个函数推断 measure kind。分析器把显示路径上由它们决定 kind 的格判为 unknown：在核心矩阵内是违规，其他位置进入 legacy ledger。

**A10 只读故障注入与 A-V 恢复口径（任务 1A、A-V）。** 仓库没有独立的 PG 测试库：pytest 默认用 SQLite，`pg_only` 用例连接当前 `DATABASE_URL`。1A 的故障注入因此固定为同一只读连接内对 `schema_version` 的恒假谓词 UPDATE（`... WHERE false`）。PostgreSQL 在执行器启动时按目标表拒绝该语句，期望 SQLSTATE 25006；即使只读门失效，这条语句也不改任何行，随后 rollback。A-V「恢复并核对前后值」只比较业务字段，不比较 `revision/updated_at`。偏好没有删除 API，A-V 前不存在的偏好行在 A-V 后以默认值保留，并写入证据；按 §2，这些行会阻断共享库上的 R_A，清理需另行授权。

文件边界在 §9 的基础上增加 `backend/app/core/startup_registry.py`（A2）、`audit-platform/frontend/src/views/LedgerStandalonePage.vue`（A3）、`backend/app/routers/ledger_datasets.py` 的 `unit_state` 块（A5）、`components/grid/GtGridCell.vue` 的文档示例（A7）与 `src/test/setup.ts` 的偏好初始化（A4）；均已登记 ownership 台账，实施前重读其工作树状态。

## 16. 阶段 A 设计门第 2 轮响应（wf_daadceb7157e9d26）

门文件 `spec-review-phaseA.json` 为 CHANGES_REQUESTED（阶段 A 与跨阶段 HIGH 2、MEDIUM 9、NIT 9），reviewDoc 为同目录 `spec-review-phaseA.md`。本节逐项响应全部 11 项 HIGH/MEDIUM，F1~F11 即评审编号；阶段 B、C 的 6 项已在 `phaseB-backlog.md`、`phaseC-backlog.md`，不在此处理。与某个 F 项属同一规则的 NIT 并入该项，其余 NIT 的处置见本节末表。本节与 §2~§15 冲突时以本节为准，旧节保留为历史；tasks.md 中与本节矛盾的子项已同步改写，清单见任务 0 的本轮记录。核对时 HEAD 为 `6c17996ad`（首轮之后新增的 5 个提交都属 ACNR 会话，不涉及本 spec 路径）；探针与输出在 `tmp_global_display_settings/workflow_wf_daadceb7157e9d26/probe_r2_*`。

**F1 迁移先于 ORM（任务 1A、A-V；阶段 B、C 沿用，见 backlog B-3、C-2）。** 共享后端从主工作树以 `--reload --reload-dir app` 运行，热重载出的进程继承 `GT_BOOTSTRAP_DONE=1`，不跑迁移；先改 ORM 会让所有 `select(Project)` 报缺列。1A 因此固定为五步。①在本工作流目录起草 A 组 V/R，用 F7 的临时 schema 夹具跑通 V/R、CHECK、R_A 与 drift 用例（夹具的迁移目录可经测试专用环境变量 `GT_DISPLAY_PREFS_MIGRATIONS_DIR` 指向草稿目录），全绿之前不放入 `backend/migrations/`：文件一旦被任何会话的全量重启登记，再改就成了 critical 的 checksum_drift。②按 A1 取号，逐字节复制进 `backend/migrations/`；此时不改 ORM、schema、router 或前端。③落库前用 §14 同纪律的只读探针确认目标号未登记、`user_display_preferences` 表与 `projects.amount_unit` 列都不存在，然后执行 `MigrationRunner(database_url=settings.DATABASE_URL, migrations_dir=<只含本组 V 文件的临时目录>).run_pending()`。主工作树里还有他人未跟踪的 V212/R212，用默认目录会把它们一起落库，所以只给本组文件。`run_pending` 是 resilient 模式，失败只记录不抛出，因此必须断言 `result.executed == [本组版本]` 与 `result.failed == []`，再用只读探针核对 `schema_version` 该行的 filename、checksum 与 `backend/migrations/` 中的文件一致（N2）；任一不符即停止并 warning 请示，不重试，也不手改 `schema_version`。这是 brief 允许的增量 DDL 落库入口（与原 A-V 计划相同，只是提前），不涉及决策 5 所限的账套金额改写。④落库成功后才改 `models/core.py`、`models/__init__.py`、新偏好模型、`audit_platform_schemas.py`、`project_wizard.py`、新 router 与 `router_registry/system.py`。V_A 只含带默认值的新列和新表，HEAD 代码不读它们；从落库到改 ORM 之间，drift 检测只报 INFO 级 db_extra（`CRITICAL_DRIFT_TYPES` 不含它）。前端改动不依赖这一步：项目详情缺 `amount_unit` 时按 R3 降级为元，偏好 API 不可用时按 R3 用本机缓存或默认值。⑤A-V 不再落库，启动候选实例前只用只读探针核对「候选树 V 文件 − 已登记版本」为空；非空（包括 HEAD 已有而共享库未落的他人迁移）即 warning 请示，不代他人落库。第②步之后，任何会话全量重启 start-dev 都会经 `run_uvicorn.py` 预引导落库 V_A，所以第①步必须先跑通，V_A 也必须对 HEAD 代码向后兼容。

**F2 候选模式不跑预引导迁移，启动任务按理由码闭集裁决（任务 13A；修订 §15 A2）。** ①`backend/run_uvicorn.py` 在模块末尾调用 `_bootstrap_before_uvicorn()` 之前增加候选分支：进程环境含 `GT_EXPECTED_CANDIDATE_TREE_OID` 时必须已有 `GT_BOOTSTRAP_DONE=1`（由 13A 启动器设置），否则向 stderr 写中文原因并 `sys.exit(2)`。候选模式下该文件不调用 git，也不构造 `MigrationRunner`；身份比对仍只在 lifespan 中做，从错误 worktree 启动也不会先落库。②身份任务 `verify_candidate_tree_identity` 放在 `setup_logging` 之后、`run_migrations` 之前（N1），候选模式下另外断言 `GT_BOOTSTRAP_DONE=1`；`FROZEN_STARTUP_SEQUENCE_NAMES` 由注册表派生，`test_startup_registry.py` 的里程碑子序列用例不受影响。③`CANDIDATE_MODE_POLICY` 的值改为 `(动作, 理由码)`，理由码是闭集：skip 用 `writes_shared_state`、`replays_shared_queue`、`optional_prewarm`；run 用 `in_process_only`、`file_or_config_read`、`read_only_sql`、`passive_subscribe`。§15 A2 原有的 skip 项按副作用取前两个理由码，另新增三项 skip：`run_schema_drift_check`（`write_log` 对共享 `schema_drift_log` 先 DELETE 后 INSERT，`_diff_checksums` 还经 `ensure_schema_version_table` 执行 DDL），`run_ai_chat_health_check`（有 local-only 违规时经 `audit_event` 写审计哈希链），`warm_workpaper_sync_registry`（只为预热，跳过只让首请求变慢）。其余任务为 run：`setup_logging`、`migration_mark_complete`、三个 `register_*`、`install_sigterm_handler`、`print_ready` 为 in_process_only；`verify_candidate_tree_identity`、`validate_grammar_on_startup`、`validate_procedure_rollout_config`、`validate_template_manifest`、`warm_render_caches`、`check_attachment_security_gates`、`check_libreoffice_health`（只找可执行文件，不起进程）为 file_or_config_read；`check_gin_index_status`（只查 `pg_stat_progress_create_index` 与 `pg_index`）为 read_only_sql；`acnr_redis_inject`、`start_epoch_subscriber`（取客户端、订阅与只读轮询，清的是本进程缓存）为 passive_subscribe。守卫断言键集合等于 `STARTUP_TASKS` 名称集合、理由码属于闭集、动作与理由码类别一致。④判据，全部不连共享库：a）子进程经 `runpy` 加载 `run_uvicorn.py`（`run_name` 不是 `__main__`，不启动 uvicorn），`DATABASE_URL` 指向 pytest 临时 SQLite 文件，包装脚本先把 `MigrationRunner.run_pending` 换成写标记文件的替身；设 `GT_EXPECTED_CANDIDATE_TREE_OID`、不设 `GT_BOOTSTRAP_DONE` 时退出码为 2、stderr 含中文原因且没有标记文件；删掉候选分支的变异必须红在「启动期执行了迁移」断言上。b）进程内以候选模式运行 `run_startup_tasks`（身份任务的 git 解析层用替身返回期望值；这里被测的是策略层，身份比对本身由 §8.3 三种变异覆盖），用 SQLAlchemy `Engine` 级 `before_cursor_execute` 记录全部语句，SELECT、PRAGMA、SHOW、SET 以外的语句数为 0；skip 任务的 `run` 一次也不被调用；只在 PG 上才写库的入口（`SchemaDriftDetector.write_log`、`event_bus.replay_pending_events`、`ImportEventOutboxService.replay_pending`、`audit_event`、`run_db_aware_gc`、`recover_lease_expired_runs`）以 spy 断言调用 0 次。把任一 skip 改成 run 的变异必须红在对应断言上。

**F3 端口只经 uvicorn 认可的通道传入，监听后再核对（任务 13A；修订 §15 A2 的 PORT 检查）。** uvicorn 0.44.0 的 click 命令只认 `--port` 与 `UVICORN_*` 环境变量，并以 SO_REUSEADDR 绑定；后端唯一读 `PORT` 的是 `_task_print_ready` 的打印。§15 A2 中「`PORT` 存在且不等于 9980」的检查作废。13A 启动器只经 `UVICORN_PORT` 传端口、`UVICORN_HOST=127.0.0.1` 传地址，并在启动前确认该端口没有监听者（连 `127.0.0.1:<端口>` 失败）。身份任务在候选模式下断言：`UVICORN_PORT` 为数字且不等于 9980；`UVICORN_HOST` 为 `127.0.0.1`；`UVICORN_RELOAD`、`UVICORN_UDS`、`UVICORN_FD`、`UVICORN_WORKERS` 均未设置；`sys.argv[1:]` 不含 `--port`、`--host`、`--uds`、`--fd`、`--reload`、`--workers`（含 `--x=值` 写法）。`/api/health` 的候选块增加 `server_port`（取 `request.scope["server"][1]`），Playwright 建会话前要求它等于候选端口。前端同理：启动器只经 `VITE_DEV_PORT` 传端口；`defineConfig` 回调拒绝 `process.argv` 中的 `--port`、`--host`；候选模式下注入一个内联插件，在 `configureServer` 里监听 `httpServer` 的 listening 事件，实际 `address().port` 不等于 `VITE_DEV_PORT` 或等于 3030 即 `process.exit(1)`。判据：以 `--port 9980` 参数、`UVICORN_PORT=9980`、`UVICORN_RELOAD=true` 启动候选后端，以及 Vite 带 `--port 3030` 启动，四种输入都必须拒绝启动；删除对应检查的变异必须让相应用例变红。

**F4 AC-08 的 computedStyle 证据来自真实浏览器（任务 5、A-V；修订 §8.2）。** vitest 的 jsdom 25 对 `var()` 原样返回字符串，子元素也不继承字号（评审探针 `review_probe_jsdom_css.cjs`），所以 vitest 只验三件事：①runtime 在四档下写入的根变量、`data-gt-font-size` 与密度变量；②CSS 合同：用 jsdom 自带的 CSSOM（把四个样式文件的文本插进 `<style>`，读 `document.styleSheets[i].cssRules`，不新增 postcss 等直接依赖）断言 §4.1 与 F10 的每个数据格选择器至少出现一次、其 font-size 为 `var(--gt-display-font-size)` 或 `inherit`，且这些选择器上没有固定 px 加 `!important`（「至少出现一次」防止解析器静默丢规则造成假绿）；③真实 Element Plus 渲染出的相关类名存在。AC-08 本身由 A-V 的浏览器核对证明，A-V 拆成两部分。A-V① 需要一个已批准的测试账号，不得用 admin 或任何他人账号：偏好按账号跨设备同步，改 admin 的字号会改变其他会话的界面，而且偏好行没有删除 API。它在【测试】项目上验四档 computedStyle（表格 body、header、表内输入、Teleport 弹窗、HTML 底稿格）、一处非表格的默认尺寸组件（N5：`el-input` 等读 `--el-font-size-base` 的组件会从现在的 15px 改为所选档位，核对字号随档变化且不溢出容器）、元→万元、页面切换、刷新与重登、密度、固定列和项目单位变更。A-V② 需要第二个已批准账号，验 A/B 隔离。任一账号不可用时一律按 brief 用 warning 暂停请示；用户确认只缺第二账号时，只有 A-V② 保持未完成。

**F5 只有顶层列可以由用户固定（任务 5、6A；修订 §4.3、§4.4）。** Element Plus 的 `updateChildFixed` 用父列的 `fixed` 覆盖全部子列，`fixedColumns` 只从顶层列取，分组下的叶子不能单独固定。现有分组表头有四处：DisclosureEditor 的 `_column_groups` 两级表头、ConsolNoteTab 两张表的两级表头、ConsolidationIndex 的「本期增加额 / 本期减少额」、TrialBalance 试算平衡表视图的「审计调整 / 重分类调整」。规则：可固定单元是顶层列；有分组的表，allowed 只含 `label` 与未分组的顶层列 ID，分组列和其叶子都不开放用户固定，GtTableDisplaySettings 不列出它们，并在表头含分组时提示「分组表头下的列不能单独固定」。不新增 group_id：需求没有要求固定分组，而给分组建持久 ID 要在 catalog 与合并模板里再加一套 remap 规则。`:fixed` 只绑在顶层 `el-table-column` 上；render schema 的 `fixed_required=true` 落在分组叶子上时按配置错误拒绝。Element Plus 把固定列按声明顺序移到左侧，这是接受的交互，设置面板提示「固定后该列移到表格左侧」。TrialBalance 的 `trial-balance` 只作用于明细主表；试算平衡表视图、trace 与调整弹窗的列与主表不同，不接用户固定列，保留现有 fixed 属性，也不显示设置入口（§4.4 TrialBalance 行的「共用 `trial-balance` 固定列」作废，amount/measure 组件仍共用）。AC-09 用例在 DOM 层断言：被固定顶层列的单元格带 `el-table-fixed-column--left`；把分组叶子 key 写进 saved 后，它出现在 staleKeys，单元格不带该类。

**F6 PATCH 区分「显式 null」与「未提交」（任务 2、4；补 §2、§15 A4）。** 字段是否提交只按 Pydantic v2 的 `model_fields_set` 判断，service 只用 `model_dump(exclude_unset=True)`，源码守卫禁止 `exclude_none`。`amount_unit_override` 的类型是 `AmountUnit | None`，显式 null 表示跟随项目并存为 NULL。其余业务字段注解为不可空类型、`Field(default=None)`（Pydantic v2 默认不校验默认值）：省略即未提交，显式 null 因类型不符返回 422。空补丁定义为 `model_fields_set - {"base_revision"}` 为空，返回 422。用例：`{base_revision:0, amount_unit_override:null}` 成功，随后 GET 返回 null；`{base_revision:0, font_size:null}`、`{base_revision:0, fixed_columns:null}`、`{base_revision:0}` 均为 422。前端 `followProjectUnit()` 发出的 PATCH 体必须含键 `"amount_unit_override": null`（用 null 不用 undefined，缓存里的 pendingScalars 同样保留 null），vitest 断言请求体。把 `exclude_unset` 换成 `exclude_none` 的变异必须红在「跟随项目保存成功」用例上。

**F7 阶段 A 的 PG 用例隔离协议（任务 1A、2、3；补 §8.2）。** `MigrationRunner` 的 `_apply_migration` 与 `_execute_rollback_script` 自己开 `engine.begin()` 并在成功时提交，审计中间件的 `_write_log` 用绑定 `settings.DATABASE_URL` 的 `async_session`，所以不能靠外层回滚隔离。新建夹具模块 `backend/tests/display_prefs_pg_world.py`（文件名不匹配 `test_*.py`），只读复用 `tests/level_backfill_world.py` 的 `database_url()` 与 `make_engine(search_path)`：管理引擎提交 `CREATE SCHEMA gds_world_<随机>`；世界引擎每条连接的 search_path 只含该 schema；在其中建 V_A 依赖的最小 `users(id)`、`projects(id)` 与 7 列 `schema_version`（理由同 level_backfill_world 文件头：执行器补列的 DO 块不限定 schema）；结束时（含失败）`DROP SCHEMA … CASCADE` 并现查已不存在；不在 public 建任何对象，也不写 public 的任何表。这是仓库已在用的隔离写法。V/R、CHECK、R_A 两类阻断、无阻断时 R_A 删除本组对象、drift（V_A 执行后按 `information_schema.columns WHERE table_schema=<该 schema>`，与 ORM 中本组新增的表和列逐列比对名称、类型、可空与默认值，不调用 `write_log`）一律在该 schema 内，经 `MigrationRunner(engine=<世界引擎>, migrations_dir=<只含本组 V/R 的临时目录>)` 与 `_execute_rollback_script` 执行。AC-03 首写竞争在同一世界里用两个 AsyncSession：A 插入后不提交，B 调 service（SAVEPOINT 内 flush），用 `pg_stat_activity` 确认 B 在等锁后再提交 A，断言 B 得到 409 且 current 为 A 的值。AC-02 审计日志用例用 SQLite 即可：发请求前 monkeypatch `app.middleware.audit_log.async_session` 为绑定测试引擎的 sessionmaker，先断言其 URL 不等于 `settings.DATABASE_URL`，PATCH 后从测试库查 `logs`。守卫：对 ownership 登记的阶段 A 新增测试文件做 AST 检查，禁止直接调用 `run_pending`、`rollback_to`、`_execute_rollback_script`，只能经夹具；夹具执行前断言 `current_schemas(false)` 恰为本世界 schema。

**F8 附注表的列级判定（任务 6A；A/C 共用接口，修订 §15 A6）。** `_align_table_to_template` 只在模板列数不少于数据列数时替换表头，替换后的表头不能证明数值按模板列排列。①`carry_template_table_names` 改为返回本次对齐结果（已存表下标 → 模板表及其 `table_id`），`_align_table_to_template` 返回首列交叉校验是否通过；`enrich_note_table_data` 在调用它之前保存每张已存表的原表头与 `_column_groups`。②判 `matched` 须同时满足：该表被分配到模板表且首列校验通过；用原表头经 `note_table_header_library.column_paths` 得到的逐列路径，与 catalog 中该 `table_id` 的叶子路径逐列满足 `note_template_workpaper_alignment.same_text`，或原表头是长度至少为 2 的前缀（读时增强在尾部补空列，已有列位置不变）。`same_text` 是用户 2026-10-24 认可的同义口径（期末余额≡期末数、年初≡期初、坏账准备≡减值准备，比例的「(%)」注记不计）；本轮探针 `probe_r2_sametext.json` 核对这些写法判为相同，期末与期初互换判为不同。③其余情形整表判 `unmatched`：数据列多于模板、同列数但列序或计量不同、推送投影表（`_source_sub_table_key`）的列与 catalog 不同、未分配到模板表、首列校验失败、模板外的表。不做逐列部分匹配，否则同一张表会一半换算、一半原值，6C 与 sidecar 也要多处理一种状态。④响应在 headers 同层增加 `table_id`，只在 matched 时非空，取自同一对齐结果；`column_ids/column_kinds/column_ratio_scales` 与响应 headers 等长，matched 时取 catalog（前缀匹配时尾部补齐的列也取 catalog），unmatched 时按 §15 A6。合并附注以已存表的 `id`（复制自合并模板条目的 UUID）为 table_id，该 `id` 不在 catalog 中即 unmatched，列级判定相同。6C 与阶段 C 的 sidecar 只消费 matched 表的这组 ID；unmatched 表的正式导出处理见 backlog C-1。表头替换本身仍按现有读时增强逻辑，本 spec 不改，unmatched 只影响 kind 下发与屏幕提示。⑤夹具：同义写法表头与列数少于模板的前缀（matched），数据列多于模板、同列数换序、推送投影表、模板外的表、首列不符（unmatched）；把前缀规则放宽为任意子集、或把 `same_text` 换成只比列数的变异，必须红在对应夹具上。

**F9 遗留违规的计数单位与 ≤88 的执行口径（任务 11A；修订 §8.1）。** 计数单位是一个「显示节点」：Vue 模板插值、`v-text`/`v-html`、`el-table-column` 的 `formatter` 返回值或 `#default` 插槽中的输出表达式、渲染函数（含 el-table-v2 的 cellRenderer）生成的文本子节点。非核心文件里的显示节点满足下列任一条即计 1 条，同一节点只计一次：kind 解析为 amount 或未知数值，且未经唯一 formatter（`GtAmountCell`、`GtMeasureCell`、`displayAmount`，以及 `useDisplayPrefsStore()` 返回值上的 `fmt`、`fmtAmount`，均按 import 与局部别名识别）；唯一金额 formatter 作用于已知非 amount 的 kind（N7：引入项目默认单位后，从未选过万元的用户也会看到这些值被除）。核心矩阵内满足同样条件判 core violation，直接失败，不进台账。`legacy_violations` 等于台账中 `disposition=deferred` 的条目数，两者逐项一一对应；`exempt` 条目不计入，但每条须由有限谓词证明该节点确实不经金额换算，谓词不成立即判失效。旧 88 是 2026-05-30 旧规则的列级计数（`el-table-column` 带 `align="right"`、prop/label 命中金额关键字、子树没有 GtAmountCell 或格式化调用），与新单位不可比，88 只作为 R10 规定的上限沿用。执行：11A 的第一步在 13A 的候选 worktree 上运行新分析器，按 scope 与核心/非核心输出计数，写入工作流目录；修完核心与公共路径后若仍大于 88，用 warning 请父会话向用户请示（扩大本轮修复范围，或调整 R10/AC-23 的上限），不得自行扩大范围、改计数单位或增加 exempt 凑数。`--update-baseline` 要求 `git status --porcelain` 为空，否则拒绝，所以只能在候选 worktree 中生成；`--check` 仍按 R10 计入未跟踪的候选文件。另按 N8，§15 A8 的 include 扩为 `src/**/*.{vue,ts,tsx,js,jsx,mjs,cjs}`（现有生产 JS 只有 `src/components/ai/index.js`），exclude 不变。

**F10 el-table-v2 的字号与密度（任务 5、6A；补 §4.1、§4.4）。** 字号：Element Plus 的 `el-table-v2.css` 在 `.el-table-v2` 上声明 `font-size: var(--el-font-size-base)`，v2 单元格经它继承显示字号；§4.1 的选择器合同增加 `.el-table-v2__header-cell`、`.el-table-v2__row-cell`（读变量或继承，不得固定 px），核心页的 cellRenderer/headerCellRenderer 不得写固定字号（11A 分析器判为核心违规）。密度：新增 `composables/useTableDensityMetrics.ts`，按 density 返回 `{rowHeight, headerHeight, estimatedRowHeight}`，数值与 runtime 写 `--gt-table-row-height` 所用的常量同源，另返回 `layoutKey`（字号或密度变化时递增）。核心页里的 v2 只有 LedgerPenetration 三处（`ledgerTotal > 1000` 等分支）：`header-height`、`estimated-row-height` 绑定 helper，并以 `:key="layoutKey"` 在字号或密度变化后重新挂载。原因是动态行高模式下 Element Plus 只在行挂载时测一次高，纯 CSS 变化不会重测，而 TableV2 只暴露 `scrollTo*`，不暴露 `resetAfterRowIndex`。重新挂载会回到表顶，显示设置很少改动，这是接受的交互。非核心的 `GtVirtualTable` 与 25 个底稿 Tab 组件用固定行高，跟随字号、不跟随密度，写入 12A 文档，本轮不改。验证：vitest 组件测试用超过 1000 行的夹具走 LedgerPenetration 的 v2 分支，断言两项高度随 density 变化、`layoutKey` 变化后 v2 组件实例被重建；v2 单元格的浏览器 computedStyle 放到终验，任务 13 的 fixture 为 LedgerPenetration 另外准备超过 1000 行的受控序时账以进入 v2 分支。

**F11 项目单位变更对其他用户的生效时点（任务 3、A-V；补 §3）。** 选择不推送：修改者在 PUT 成功且响应 project_id 等于当前项目时立即更新 store；同一项目的其他在线用户在下一次加载项目上下文时生效（刷新页面、切换项目或年度，由 `loadProjectContext` 重取详情）。理由：项目单位通常每个项目只设一次；project store 现在只发 `project:reset`、`year:changed` 与 `sse:*` 事件，没有项目配置变更的订阅，推送需要新增后端事件、SSE 转发与前端重取，验收还要求两个账号同时在线。R4「选择跟随项目的用户立即看到新单位」按此验收：修改者立即看到，其他跟随项目的用户在下次加载项目上下文时看到。AC-06 的用例补一条：A 账号修改后，B 账号的 store 在下一次 `loadProjectContext` 之前保持旧值，之后为新值。A-V① 验修改者立即生效、刷新后保持；A-V② 验 B 账号刷新后看到新单位。ProjectSettingsCenter 的字段名定为「项目默认金额单位」，说明文字为「影响正式导出，以及选择跟随项目的成员的屏幕显示；其他成员在刷新或重新进入项目后生效」（N6）。

| NIT | 处置 |
|---|---|
| N1 身份任务位置 | 并入 F2② |
| N2 `run_pending` 结果断言 | 并入 F1③ |
| N3 `ValueType.rate/integer` | 6A 不做机械映射；出现在核心列时必须显式声明 kind（rate 映射 ratio 并显式给 scale，integer 映射 count 或 quantity），否则按核心未知 fail closed |
| N4 原币列 | render schema 中的原币列（如 `E0.yaml` 的 `balance_orig`）不按 `render: amount` 机械映射，显式声明为 `quantity`（数值格式、不随本位币单位缩放、表头保留「原币」），在 12A 文档说明并加夹具 |
| N5 非表格组件字号 | 并入 F4（A-V①）；影响面写入 12A 文档 |
| N6 项目单位字段名 | 并入 F11 |
| N7 fmt 作用于非金额 | 并入 F9 的计数单位 |
| N8 `.js` 生产文件 | 并入 F9 |
| N9 自动注册与 d.ts | 新组件（GtMeasureCell、GtTableDisplaySettings、DisplayPreferencesPanel、DisplaySettingsView 等）在使用处显式 import，不依赖 unplugin 自动注册；本任务不提交 `src/components.d.ts`、`src/auto-imports.d.ts` 的改动，候选树保留 HEAD 版 |

文件边界在 §9、§15 的基础上增加：`backend/run_uvicorn.py` 的候选分支（F2）；新夹具 `backend/tests/display_prefs_pg_world.py`（F7，`tests/level_backfill_world.py` 只读复用）；新 `audit-platform/frontend/src/composables/useTableDensityMetrics.ts`（F10）；`backend/app/services/note_table_enrichment.py` 的对齐结果返回与原表头保存（F8）；`backend/app/api/health.py` 候选块的 `server_port`（F3）；`vite.config.ts` 的候选模式 argv 检查与端口核对插件（F3）；`audit-platform/frontend/src/views/ProjectSettingsCenter.vue` 的项目默认金额单位字段块（F11；工作树已有他会话 +2 行未提交改动，只合并本任务块）。以上均已追加到 ownership 台账，实施前重读其工作树状态。

## 17. 阶段 A 设计门第 3 轮响应（wf_ea78292dbbb03cbb）

门文件 `tmp_global_display_settings/workflow_wf_ea78292dbbb03cbb/spec-review-phaseA.json` 为 CHANGES_REQUESTED（HIGH 1、MEDIUM 8、NIT 15），reviewDoc 为同目录 `spec-review-phaseA.md`。本节逐项响应 9 项 HIGH/MEDIUM，G1~G9 即评审编号 1~9。与某个 G 项改的是同一段规则的 NIT（N1、N13、N14、N15）并入该项，其余 NIT 本轮不处理，见本节末表。阶段 B、C 的发现在同目录 `phaseB-backlog.md`、`phaseC-backlog.md`，不在此处理。本节与 §2~§16 冲突时以本节为准，旧节保留为历史。

本轮新核对的代码事实（HEAD `219018c28`）：两版合并附注模板 `backend/data/consol_note_sections_{soe,listed}.json` 分别有 251、422 个条目，每个条目都有 UUID 格式的 `id`，`id` 与 `section_id` 在各自版本内一一对应，两版之间没有相同的 `id`；`get_section_detail` 的返回值不含 `id`。三份手写 `c-note-table` render schema 是 `C-D1-disclosure.yaml`、`C-D2-disclosure.yaml`、`C-L-disclosure.yaml`；其中的 `monetary_unit` 字段只是底稿正文里的「金额单位」文字，前端只把它当上下文值读写，不参与换算。`resolve_project_context` 的合并权限是项目角色权限与系统角色权限的并集。

**G1 render schema 的 kind 映射与核心范围（任务 6A、12A；阶段 C 复用同一 schema；修订 §4.2 末句与 §16 末表 N3/N4）。**

①映射表，由后端 `wp_render_schema_service` 在加载 YAML 时统一换算，结果随 render-config 下发为每列的 `measure_kind/ratio_scale`，前端不再自行推断：

| YAML 写法 | 换算结果 |
|---|---|
| 显式 `measure_kind`（可带 `ratio_scale`） | 原样采用，按 §4.2 的 `DisplayMeasureSpec` 校验，ratio 缺 scale 或非 ratio 带 scale 为 invalid |
| `render: amount` 或 `render: amount_formula`，或 `type: amount` | amount |
| `render: percent` 或 `render: percent_formula`，或 `type: percent` | ratio；必须同时写 `ratio_scale`，否则为 unknown |
| `type: number` 且无 `render` | unknown |
| 原币列（§16 末表 N4） | 必须显式 `measure_kind: quantity`，否则按上面各行处理 |
| `ValueType.rate/integer` 映射来的列（§16 末表 N3） | 必须显式声明，否则 unknown |

②运行时：编辑控件始终读写原始元值，不需要 kind，也不因缺 kind 拒绝编辑。kind 只决定展示路径。非核心 schema 里一个列集合的宿主（sheet 的 `columns` 或一个 `sub_tables[]` 条目，下同称「一张表」）只要含一个 unknown 或 invalid 的数值列，整张表的数值列都走 G4 的「未登记」分支：除数恒为 1、不加 %，表头旁显示「本表列语义未登记，数值按原值显示，未随金额单位换算」。不按列部分换算，理由与 §16 F8③ 相同：同一张表里一部分按万元、一部分按元，用户无法分辨。不拒绝渲染。

③核心清单是版本化文件 `backend/data/display_measure/render_schema_core.json`，初始只列上述三份 `c-note-table` 文件，每项写 wp_code、componentType 与理由；AC-12、AC-25 的「HTML 底稿」样本必须取自清单里的文件（任务 13 用 `C-D1-disclosure` 所在的 D1 底稿）。核心文件中的 unknown 或 invalid 列：`--check` 失败；运行时 `wp_render_schema_service` 抛 `DISPLAY_MEASURE_CONTRACT_INVALID`，render-config 对该 sheet 返回结构化错误，前端显示「本底稿列语义配置有误，请联系管理员」，不渲染该 sheet。6A 把这三份文件的数值列逐列显式写好（快照：6 个 `type: number` 无 render，27 个 percent 类列需写 `ratio_scale`），scale 由该列的取数来源决定，不按标题猜。

④非核心 schema 的 unknown 列由新只读工具 `backend/scripts/check/render_schema_measure_audit.py` 现算：计数单位是（schema 文件, sheet, 表 id, 列 field），`--check` 与已提交基线 `backend/data/display_measure/render_schema_unknown_baseline.json` 逐文件比较，任一文件计数上升、出现基线外文件或核心文件非零即退出 1，解析失败退出 2；`--update-baseline` 拒绝任何上升。按评审探针快照，手写 YAML 中 unknown 约 1,471 列（其中核心 33 列），实施时现算，数值写进 12A 文档。这个基线与 §16 F9 的「≤88」是两个独立指标：前者数 YAML 列，后者数 Vue/TS 显示节点。非核心的 unknown 列不进 6A 修复范围。

⑤测试：映射表每行一个夹具；非核心表含一个 unknown 时整表不换算并显示提示；核心文件写入 unknown 时 `--check` 红、render-config 返回结构化错误；删除 percent→ratio 的 scale 要求、或把 unknown 改成 amount 的变异必须红在对应夹具上。

**G2 合并附注的 table_id（任务 6A；阶段 C sidecar 同用；修订 §16 F8④、§4.2「合并两版复用现有表 UUID id」与 tasks 6A 第 2 条）。** 合并附注的 `table_id` 是项目合并模板版本（soe 或 listed）中按 `section_id` 查到的模板条目 `id`。禁止使用 `ConsolNoteData.id`：它是数据行自己的随机主键。catalog 生成器读取两版模板时校验 `section_id → id` 一一对应、两版之间 `id` 不重复，任一不成立即 `--check` 失败。`GET /api/consol-note-sections/{standard}/{section_id}` 增加 `table_id/column_ids/column_kinds/column_ratio_scales/measure_status`，数据接口不重复下发。`measure_status`：模板条目存在且其 `id` 在该版 catalog 中为 matched，catalog 中缺该 `id` 为 unmatched，catalog 自相矛盾为 invalid。ConsolNoteTab 沿用现有逻辑：已存数据列数与模板不同时不使用已存数据；只有它接受了已存数据且 `measure_status=matched` 时才按 kind 换算，其余情形在屏幕上按 unmatched 处理并显示 §15 A6 的提示。夹具：`data` 里没有 `id` 的已存数据判 matched；把 table_id 取成数据行主键的变异必须红。阶段 C sidecar 的 `<section_id>/<table_id>` 对合并附注取同一个模板 `id`，已登记到 `phaseC-backlog.md` C-5。

同时并入 N1：§16 F8① 保存的「原表头」改为在调用 `_align_table_to_template` 之前对整张已存表的 `headers`、`multi_header`、`header_rows`、`_column_groups`、`columns` 做深拷贝，`column_paths` 用这份拷贝计算。

**G3 固定列的持久化键带表或模式身份（任务 2、4、5、6A；修订 §2 fixed_columns 线协议、§4.3 矩阵与 `save(keys)`）。**

①键：

| 页面 | 持久化键 | allowed | mandatory |
|---|---|---|---|
| TrialBalance 明细主表 | `trial-balance` | §4.3 原表 | §4.3 原表 |
| ReportView | `report-view:normal`、`report-view:compare` | 各模式各自的列，见 §4.3 原表 | `row_code,row_name` |
| ReportView 权益表、减值表 | 不提供用户固定列 | — | 保留现有 fixed |
| DisclosureEditor | `disclosure-editor:<table_id>`，只在 `measure_status=matched` 时有键 | `label` 与该表未分组的顶层 `column_id` | `label` |
| HTML 底稿（render schema） | `workpaper:<componentType>:<schema wp_code>/<sheet 名>/<表 id>`；sheet 直接带 `columns` 时表 id 写 `_` | 该表的顶层 `field` | `fixed_required=true` 的顶层列 |
| HTML 底稿（GtEditableTable） | `workpaper:<componentType>:<displayKey>`，`displayKey` 是新增的可选 prop；不传则不提供用户固定列 | 该表的 GtColumn `prop` | 同上 |
| 合并页 | `consolidation:consol_tb`、`consolidation:consol_report`、`consolidation:consol_note:<table_id>`、`consolidation:worksheets:<activeSheet>`（`ConsolWorksheetTabs` 当前子表的 `activeSheet` 值，如 `info`、`cost`） | 各表顶层列 | report 为 `row_code,row_name`，note 为 `label` |

键超过 100 字符，或没有键（unmatched 附注表、未传 `displayKey`），GtTableDisplaySettings 显示为禁用并提示「本表没有稳定标识，不能保存固定列」，mandatory 列照常固定。§4.3 中 `report-view`、`disclosure-editor`、`consolidation:<tab>` 三个不带身份的键作废。

②stale 只在同一个键内计算：staleKeys = 该键已保存列 − 该键当前 allowed。切到另一张表就是另一个键，不再出现「已忽略」提示。`save(keys)` 只替换当前键，不影响其他键。

③线协议：`fixed_columns` 的值由列数组改为对象。PATCH 请求为 `{pageKey: {columns: string[]}}`，`columns` 以外的键 422（`extra='forbid'`）；GET 与 PATCH 响应为 `{pageKey: {columns: string[], saved_at: string}}`，`saved_at` 是 UTC ISO 时间，由服务端写入。PATCH 带的是完整的目标映射（server current 叠加本机未确认操作，§3 与 §16 F6 不变），请求中没有的键即删除。service 逐键比较：`columns` 与已存值相同的保留原 `saved_at`，新增或改变的写当前时间。§2 的上限不变（最多 100 个键、每键最多 20 列、键与列 1~100 字符），64KiB 改为对存储后的规范 JSON 计算。默认 JSON 仍为 `fixed_columns: {}`。功能尚未上线，没有需要迁移的已存键；旧 `gt_display_prefs` 里的固定列随旧键删除（§3）。

④上限淘汰在客户端做：`usePreferredFixedColumns` 维护本页已挂载键的模块级集合（挂载时登记、卸载时移除）。生成 PATCH 前若键数会超过 100，按 `saved_at` 从旧到新（相同时按键名排序）选未挂载、且不在本次发送里的键，各记一条 delete 墓碑（走 §3 同一套 epoch），并提示「已清除最久未修改的 N 张表的固定列设置」。可淘汰的键不够时不保存本次修改，恢复到修改前，并提示「固定列设置已达 100 张表的上限，本次未保存」。

⑤测试：表 X 固定后切到表 Y，Y 没有 stale 提示，回到 X 仍生效；compare 与 normal 互不影响；超上限时淘汰最旧的未挂载键、当前页不受影响；可淘汰键不够时本次不保存；service 对未改变的键保留 `saved_at`；PATCH 带 `saved_at` 为 422。把键改回不带身份、或 `save` 改成整体替换的变异必须红。

**G4 逐 kind 显示规则（任务 6A；修订 §4.2；requirements R6 与 AC-11 改为 `20.00%`）。** `formatMeasure` 与 `GtMeasureCell` 按下表执行，`GtAmountCell` 只处理 amount 一行。所有数值格都用 `--gt-font-numeric` 与 `font-variant-numeric: tabular-nums`，`data-gt-value` 恒为原始元值。

| kind | 除数 | 小数位 | 千分位 | 零值（`show_zero`） | 负数红色（`negative_red`） | 高亮阈值 |
|---|---|---|---|---|---|---|
| amount | effective 金额单位 | 账号 `decimals` | 是 | 生效 | 生效 | 生效 |
| ratio | 1；fraction 先以 Decimal 乘 100 | 固定 2 位，加 `%` | 是 | 生效 | 生效 | 不生效 |
| count | 1 | 0 位；原值带小数时按 quantity 规则显示并记一次开发告警 | 是 | 生效 | 生效 | 不生效 |
| quantity、exchange_rate、unit_price | 1 | 原值的有效小数位：以原值字符串构造 Decimal、去掉尾零后的小数位数，最多 6 位，超过 6 位按 ROUND_HALF_UP 保留 6 位 | 是 | 生效 | 生效 | 不生效 |
| text | — | 原样输出，不做数值格式化 | — | — | — | — |
| 未登记（kind 为 null 或 unknown） | 1 | 账号 `decimals` | 是 | 生效 | 生效 | 不生效 |

「零值生效」指沿用 store 现有 `show_zero` 的显示规则。比例固定 2 位与 `formatters.fmtPercent` 的默认值一致，所以 AC-11 的期望值改为：fraction 0.2 与 percent_points 20 都输出 `20.00%`。按此规则，切到万元后数量 10000 显示 `10,000`，汇率 7.2 显示 `7.2`，单价 10000 显示 `10,000`。每行配一个夹具，含零值、负数与 6 位以上小数；把 count 改成账号小数位、或让 ratio 读账号小数位的变异必须红。

**G5 未登记表的格式与真实 matched 比例（任务 6A、12A、13；修订 §15 A6「只显示原值」）。** ①unmatched、invalid 的附注表与 G1② 的非核心未登记表，数值格都走 `GtMeasureCell` 的未登记分支：能按 Decimal 解析的按 G4 末行格式化，不能解析的原样输出。这与现在 DisclosureEditor 经 `GtAmountCell` 的元口径显示一致，元口径用户看不到退化。②6A 增加一步：用 §14 同纪律的只读探针（第一条业务 SQL `SET TRANSACTION READ ONLY`、单连接、finally rollback），读共享库全部未删除项目的单体附注已存表与合并附注数据，在内存里调用候选树的 `enrich_note_table_data`（导入路径指向候选 worktree 的 `backend`）与 G2 的合并判定，按标准、项目、表输出 matched、unmatched、invalid 数量与原因分布（§16 F8③ 的各类原因分别计数）。结果写入当前工作流目录与 12A 文档；不按结果放宽匹配规则。③任务 13 的 fixture 断言 DisclosureEditor 与合并附注金额样本所在的表 `measure_status=matched`；若 fixture 选定的表不是 matched，就换一张 matched 表，不改规则。

**G6 分析器的数值候选判定（任务 11A；补 §8.1 与 §16 F9）。** 判定规则写成 `eslint-rules/lib/amount-display-analysis.cjs` 中的常量 `NUMERIC_CANDIDATE_RULES`，ESLint rule 与 CLI 共用。计数对象是 §16 F9 定义的显示节点。

①显式 kind 来源（优先，命中即不再看结构信号）：`<GtAmountCell>` 视为 amount；`<GtMeasureCell kind="…">` 取字面值；`<GtMeasureCell :kind="x.measure_kind">` 或 `formatMeasure(v, col)` 这类把列定义整体传入的写法视为 kind 来自运行时列定义，记为「已声明」；GtColumn 对象字面量的 `measureKind`；附注列 `column_kinds[i]` 的绑定。YAML 列本身的 unknown 由 G1④ 的工具计数，不由前端分析器计数。

②结构信号，任一成立即为数值候选：S1 所在 `el-table-column` 带 `align="right"` 或 `header-align="right"`（静态或绑定字符串字面量）；S2 输出表达式含 `toFixed(`、`toLocaleString(`、`Intl.NumberFormat`、`Number(`、`parseFloat(`、`new Decimal(`/`Decimal(`；S3 输出表达式调用 `utils/formatters.ts` 的数值类导出（名单为常量 `LEGACY_NUMERIC_FORMATTERS`，守卫断言该文件的每个导出都被归为数值类或非数值类，新增导出未归类即失败）；S4 GtColumn 对象字面量 `type: 'number'`。el-table-v2 的列定义对象按 S1、S4 同样判断，cellRenderer 返回的文本节点按 S2、S3 判断。

③不是显示节点：`el-input`、`el-input-number`、`WpAmountInput` 与 GridKernel 编辑器的值，`data-gt-value` 等 HTML 属性。

④prop 或 label 命中关键字常量 `AMOUNT_KEYWORDS`（金额、余额、借方、贷方、发生额、审定、未审、调整、`amount`、`balance`、`debit`、`credit` 等）只把已有候选标为「疑似金额」，写在 JSON 的该条目里供分诊，不单独产生候选。

⑤数值候选且没有显式 kind = 未知数值，按 §16 F9 计数。核心违规谓词（并入 N13）：a）核心矩阵内的未知数值；b）唯一金额 formatter 作用于已知非 amount 的 kind；c）`<GtAmountCell>` 带 `unit` 属性或 `:unit` 绑定（§15 A7）；d）核心文件里 el-table-v2 的 cellRenderer、headerCellRenderer 中 `style` 对象字面量含以 `px` 结尾的 `fontSize` 或 `font-size` 字面值（§16 F10）。

⑥每个信号、显式来源与核心谓词各配一个正例和一个反例 fixture；从常量里删除任一信号的变异必须让对应正例变红。

**G7 候选 worktree 工具先于 11A（任务 13A-1、11A、13A；修订 §9 阶段 A 顺序）。** 把 13A 里与启动无关的部分拆为新任务 13A-1，排在任务 7 之后、11A 之前：`scripts/check/candidate_tree_identity.py` 的 `build` 子命令按清单文件（逐项写路径与来源：整文件取工作树，或取 tmp 下预先合好的本任务块内容）在私有 index 上 `read-tree HEAD`、`update-index`、`write-tree`、`commit-tree`，私有 index 路径只经子进程 env 传入；`checkout` 子命令建立分离头 worktree 到 `tmp_global_display_settings/<名称>` 并 `git worktree lock`，建好后要求 `git status --porcelain` 为空；`release` 子命令先 `cmd /c rmdir` 拆掉自建的 node_modules 联接，再 unlock、删目录、`git worktree prune`。13A 保留启动身份钩子、候选模式策略与端口检查。阶段 A 顺序改为：1A → 2 → 3 → 4 → 5 → 6A → 7 → 13A-1 → 11A → 12A → 13A → A-V → A-BK。11A 在 13A-1 建立的候选 worktree 上首次计数并运行 `--update-baseline`，生成的基线文件逐字节复制回主工作树（本任务文件，已登记），之后的候选树都包含它，并须在新候选树上 `--check` 通过。13A-1 的测试：`build` 前后 `git for-each-ref` 结果逐行相同（不移动任何 ref）；父进程 `os.environ` 不含 `GIT_INDEX_FILE`；所用 index 文件不是 `.git/index`；worktree 已锁定；`release` 后联接目标目录仍在。把私有 index 换成默认 index 的变异必须红。

**G8 A-V 的前提清单（任务 A-V；并入 N15②）。** A-V 开始前用只读探针核对下列前提，任一不满足就用 warning 请示，请示内容固定列出这几项的现状，不自行补齐：

1. 账号 A：用户已批准的测试账号，不是 admin；对一个指定的【测试】standalone 项目 P，`resolve_project_context` 算出的权限含 `project:edit`（项目角色 manager 或 signing_partner，或系统角色 partner、manager），且 `require_project_access('readonly')` 放行。
2. 账号 B：用户已批准的第二个测试账号，是 P 的项目成员（至少 readonly 项目角色）。只缺 B 时按 §16 F4，A-V② 保持未完成。
3. P 上有数据：试算表行、已生成的报表、至少一张 `measure_status=matched` 的附注表、一份带 `C-D1-disclosure` sheet 数据的 D1 底稿、一个 active 账套数据集。缺哪页的数据，请示里写明，由用户决定提供别的项目或把该页留到终验；A-V 不造数据（造数据是任务 13 fixture 工具的职责）。
4. A-V 只在 P 上冒烟 TrialBalance、ReportView、DisclosureEditor、D1 底稿与 LedgerPenetration；合并页需要 consolidated 项目，留到终验，A-V 证据里写明。
5. 成员关系不满足时只请示。用户同意经平台建立时，由文档登记的 admin 经平台项目成员接口建立，记录 assignment ID，finally 经同一接口移除并核对；不改任何用户账号本身。
6. 恢复：开始前记录 A、B 两个账号的偏好与 P 的 `amount_unit`；finally 用 PATCH 把两个账号的偏好恢复到记录值（只比业务字段，§15 A10），用 config PUT 恢复 P 的 `amount_unit` 并回读核对。原本没有偏好行的账号，行会以恢复后的值保留；按 §2 与 AC-21，这些行会让共享库上的 R_A 阻断，写进证据，清理需另行授权。

**G9 迁移草稿阶段同时起草 ORM（任务 1A；修订 §16 F1 第①、③、④步与 F7 drift 段）。** ①在工作流目录同时起草 V/R 与 ORM 草稿模块 `orm_draft_display_prefs.py`：它不在 `backend/` 下，`app` 不会导入；内容是一个独立 `MetaData`，含 `user_display_preferences` 全部列（类型、可空、`server_default`、CHECK 约束名与条件）和只含 `id`、`amount_unit` 的 `projects` 表。F7 的 drift 用例改为参数化：比较对象由测试专用环境变量 `GT_DISPLAY_PREFS_ORM_SOURCE` 指定草稿文件，未设置时用 `app.models` 的真实元数据；比较项为本组每一列的名称、PG 方言下的类型（含长度与精度）、可空、默认值与 CHECK 条件。第①步在临时 schema 内让 V/R、CHECK、R_A 与「V_A vs 草稿」的 drift 一起通过，才进入第②步。变异：把草稿里任一列的默认值改掉，第①步的 drift 用例必须红。③（并入 N15①）若目标版本号已登记：filename 与 checksum 都与本组文件一致时，说明他人全量重启已落库，跳过 `run_pending`，记录这一情况，并用只读探针核对表与列存在；不一致才 warning 请示。④落库后把草稿的列定义写进 `models/user_display_preferences.py` 与 `models/core.py::Project.amount_unit`（DB 有默认值的列同时声明 `server_default`），然后在临时 schema 内不设环境变量重跑同一 drift 用例，并用工作流目录下的一次性脚本比较草稿与真实 ORM 的上述各项逐项相同，输出存入工作流目录。若不相同，以草稿为准改 ORM（V 已不能改）。依赖 ORM `create_all` 的 SQLite CHECK 用例排在第④步之后。

| NIT | 处置 |
|---|---|
| N1 原表头深拷贝 | 并入 G2 |
| N13 两条核心违规谓词 | 并入 G6⑤ |
| N14 tasks 6A 第 3 条引用已作废的 §4.4 TrialBalance 行 | tasks 6A 第 3 条已改为「按 §4.4 与 §16 F5、本节 G3」 |
| N15 ① 已按同一 checksum 落库 ② A-V 偏好恢复 | ①并入 G9③，②并入 G8 第 6 条 |
| N2~N12 | 本轮未处理：门契约只修 HIGH/MEDIUM，这些 NIT 不改变本节的设计选择，留给后续评审裁决或实施时处理 |

文件边界在 §9、§15、§16 的基础上增加：`backend/data/display_measure/render_schema_core.json`（新）、`backend/data/display_measure/render_schema_unknown_baseline.json`（新）、`backend/scripts/check/render_schema_measure_audit.py`（新）、`backend/app/services/wp_render_schema_service.py` 的 kind 换算与核心校验块、`backend/app/routers/consol_note_sections.py::get_section_detail` 的 measure 字段块、`audit-platform/frontend/src/components/workpaper/GtCNoteTable.vue` 的 kind 消费与未登记提示块、三份 `C-*-disclosure.yaml` 的列 kind 声明（G1）；`audit-platform/frontend/src/components/consolidation/worksheets/ConsolWorksheetTabs.vue` 的固定列接线块（G3）。以上均已追加到 ownership 台账，核对时 `git status` 均为干净，实施前重读。

## 18. 阶段 A 设计门第 4 轮响应（wf_ea78292dbbb03cbb）

门文件 `tmp_global_display_settings/workflow_wf_ea78292dbbb03cbb/spec-review-phaseA.json` 为 CHANGES_REQUESTED（HIGH 1、MEDIUM 2、NIT 16），reviewDoc 为同目录 `spec-review-phaseA.md`。本节逐项响应 3 项 HIGH/MEDIUM，H1~H3 即评审编号 R4-1~R4-3。R4-N2 与 H1 改的是同一段规则，并入 H1；其余 NIT 本轮不处理，见本节末表。阶段 C 的新发现 C-7 已在同目录 `phaseC-backlog.md`。本节与 §2~§17 冲突时以本节为准，旧节保留为历史。

本轮新核对的代码事实（HEAD `626bcef99`）：
- `backend/data/account_package_registry.json` 中 D1 有科目工作包（`primary_wp_code` D1，`schema_refs` 含 `C-D1-disclosure.yaml`），两个附注 sheet 在包内；D2 同样有工作包，附注 sheet `附注披露信息(上市公司)` 在包内；没有 `primary_wp_code` 为 L 的工作包。
- `backend/app/data/wp_code_overrides.json`：D1 → `d1-notes-receivable`，D2 → `d2-accounts-receivable`，A7-2 → `c-note-table`。
- render-config 的生产路径是 `wp_render_config._get_render_config_impl` 里的逐 sheet 循环。`wp_render_pipeline.plan_sheets` 是另一套实现，最近一次修改在 2026-09-08，没有生产调用方。
- `resolve_package_sheets(None, wp_code, project_id)` 在 db 为 None 时跳过项目与事务所自定义工作包，只读内置注册表，不连库。
- render schema 的每个 sheet 条目自带 `component_type`；三份 `C-*-disclosure.yaml` 都是 `c-note-table`。
- `d1/D1TabDisclosure.vue` 2534 行（白名单基线 2527）：金额格共 41 处 `fmtAmt(...)`，经 `v-html` 输出，`fmtAmt` 调 `displayPrefs.fmtAmount`，零值显示「-」、负数加括号；「比例(%)」与「预期信用损失率(%)」由 `fmtPct` 输出（原值乘 100、保留 2 位）。表格 th/td 与表内输入的字号读 `--wp-font-size`；固定 12px 只出现在 `.excel-tip`、`.excel-hint`、`.detail-band`、`.portfolio-methodology` 四类说明文字上。主表「票据种类」列带 `fixed`，金额列在 `MAIN_TABLE_GROUPS` 分组表头之下。
- `backend/app/routers/wp_render_config.py` 1184 行，白名单基线 1135（+5% 上限约 1191）；白名单注释写明的拆分方向是把逐 sheet 分类循环抽为 `wp_render_config_sheet_classify.py`。

**H1 核心 render schema 按实际路由判定；HTML 底稿核心面改为 D1TabDisclosure（R4-1；修订 §17 G1③、G8 第 3/4 条与 §4.4「HTML 底稿」行；并入 R4-N2）。**

①路由判定抽成纯函数。新建 `backend/app/routers/wp_render_config_sheet_classify.py`，把 `_get_render_config_impl` 中从 `_real_sheets` 计算起、到「G- 前缀改走 OnlyOffice」为止的逐 sheet 判定原样移入两个同步函数：`is_multi_sheet(classifications, overrides) -> bool` 与 `classify_render_sheets(wp_code, classifications, *, is_multi_sheet, requested_sheet_name, has_package_sheets, overrides) -> list[SheetRoute]`。`SheetRoute` 是 frozen dataclass，字段为 `classification`、`component_type`、`onlyoffice_forced`；被跳过的 sheet 不出现在结果里。`_sheet_name_matches`、`_SHEET_CODE_RE`、`_WHOLE_WP_MULTISHEET_DEDICATED` 移入新模块，router 从新模块导入同名对象，现有导入路径继续可用。router 仍负责模板 sheet 排序（异步读模板文件，排在调用 `classify_render_sheets` 之前）、`force_component_type`、schema 加载与 renderer 调用。新模块不接收数据库会话、不做 IO。不复用 `wp_render_pipeline.plan_sheets`：它不在生产路径上，与现行判定是否等价没有证据。本步只移动代码，不改任何判定。等价性证据有三项：16 个 `test_*render_config*.py` 在候选树与同一 HEAD 上的失败集合相同；新增表驱动用例 `backend/tests/test_render_sheet_classify.py`，覆盖 D1 工作包的两张附注 sheet → `d1-notes-receivable`、D2 附注 sheet → `d2-accounts-receivable`、A7-2 单 sheet → `c-note-table`、整册专属组件、`B-` 合成目录、`G-` 改走 OnlyOffice、sheet 级 override、历史/删除/原版 sheet 跳过；AST 守卫断言 router 的逐 sheet 循环调用 `classify_render_sheets`，且 `_get_render_config_impl` 函数体内不再出现 `_WHOLE_WP_MULTISHEET_DEDICATED`。删除 `elif pkg_sheets and ovr` 分支的磁盘变异必须红在 D1 用例上。`wp_render_config.py` 因此净减行数，新文件不超过 800 行。

②reached_by。`render_schema_measure_audit.py` 遍历内置科目工作包注册表里的每个 `primary_wp_code`：用 `resolve_package_sheets(None, wp_code, <固定占位 UUID>)` 取 sheet 清单；先用 `is_multi_sheet` 判定，再以 `has_package_sheets=True`、`requested_sheet_name=None` 与当前 `wp_code_overrides.json` 调 `classify_render_sheets`，得到每个 sheet 的 componentType；用 `WpRenderSchemaService._resolve_schema_path(wp_code)` 找 schema 文件，用 `_unpack_sheet_schema` 取该 sheet 的 schema 条目。条目的 `component_type` 等于路由结果且 `onlyoffice_forced` 为假时，向该 schema 文件的 reached_by 记一条 `{wp_code, sheet, componentType}`。工具不连库，不读项目数据。不记 host_vue：componentType 到 Vue 组件的映射由 htmlRendererRegistry 单一来源决定并有它自己的守卫，这里再记一份只会多一处漂移。离线算不到的两类路由写进 12A 文档：项目或事务所自定义工作包（存在库里），以及没有内置工作包、sheet 清单来自数据库分类结果的底稿。只经这两类路由到达的 schema 不能成为核心项，因为 `--check` 无法重算它们。

③核心清单。`render_schema_core.json` 的形状为 `{"version": 1, "entries": [{"schema_file", "reached_by", "reason"}]}`。`--check` 重算每个 entry 的 reached_by：结果为空，或与文件记录不一致（按 wp_code、sheet、componentType 排序后逐项比较），退出 1。不在清单里而 reached_by 非空的 schema 只列在 JSON 输出的 `reached_non_core` 中，不失败，按 §17 G1② 的非核心规则显示。清单的初始内容由 6A 第 1 步决定：三份 `c-note-table` 中只有 reached_by 非空的才写入。按本轮核对的路由，三份都应为空，清单初始为 `"entries": []`；6A 不再给这 33 列逐列写 kind，它们留在非核心 unknown 基线里，三份 YAML 不改。核心项的运行时校验与 `--check` 失败仍按 §17 G1③ 实现，用测试夹具里的核心清单验证。render-config 的错误形状（并入 R4-N2）：HTTP 仍为 200，该 sheet 条目的 `schema` 为 null，另带 `measure_contract_error: {code: "DISPLAY_MEASURE_CONTRACT_INVALID", message: "本底稿列语义配置有误，请联系管理员"}`；GtWpRenderer 遇到该字段时显示 message、不挂载该 sheet 的组件，其他 sheet 照常渲染。

④HTML 底稿核心面采用评审方案 (a)。D1TabDisclosure 是 D1 底稿附注页签上用户实际看到的组件，D1 底稿也是前几轮已选定的样本底稿，换成它不需要另找数据。方案 (b) 不采用：按②，当前没有 reached_by 非空的 `c-note-table` schema；其他 componentType 的 schema 是否被前端组件当作列定义消费，要逐组件核对，本轮没有这项证据。核心面写作 `GtD1NotesReceivable.vue` 挂载的 `d1/D1TabDisclosure.vue`（listed 与 soe 两个 variant 是同一文件）；AC-12、AC-25 与 A-V 的 HTML 底稿样本是 D1 底稿的「附注上市」页签。6A 对该文件的改动：
- 全部 `v-html="fmtAmt(...)"` 金额格改为 `<GtAmountCell :value="...">`，删除 `fmtAmt` 和这些 `v-html`。零值与负数改按账号的 `show_zero`、`negative_red` 显示，不再是「-」与括号；这是有意的统一，写进 12A 文档。
- 全部 `fmtPct(...)` 改为 `<GtMeasureCell kind="ratio" ratio-scale="fraction" :value="...">`，删除 `fmtPct`。取 fraction 的依据是现有 `fmtPct` 对原值乘 100。
- `WpAmountInput` 等输入控件不变，读写原始元值。
- 字号：表格 th/td 与表内输入已读 `--wp-font-size`，不改；四类 12px 说明文字不是数据格，保留，并写进 12A 文档。
- 固定列：本组件不提供用户固定列，保留「票据种类」列现有的 `fixed`，不显示设置入口；金额列在分组表头下，按 §16 F5 本就不能单独固定。§17 G3① 的键表增加「D1TabDisclosure：不提供用户固定列，保留现有 fixed」一行。
- §4.4 核心矩阵「HTML 底稿」行增加该文件；11A 的核心 symbol manifest 加入该文件；ownership 台账登记该文件的金额与比例显示块。改动删除两个函数与 v-html 包装，行数净减，不调整白名单。

D2 的附注组件、D1 其余 Tab 与其他专属组件不在本轮核心面，按 §16 F9 进入 11A 的 legacy ledger。

⑤GtCNoteTable 的单位字段。schema 上下文字段 `name === 'monetary_unit'` 时，GtCNoteTable 把屏幕标签显示为「附注披露金额单位（正式输出用）」，并在卡片表头旁显示只读的「屏幕显示单位：<effective 单位中文名>」。YAML 里的 `label` 不改：正式输出也读这些 schema，它是不是模板单位 authority 由阶段 C 的 C-7 决定。组件测试断言 effective 切到万元后两处文字同时正确显示，字段值不变。

⑥§17 G8 第 3 条改为「P 上有一份 D1 底稿，其『附注上市』页签主表有数据（主表金额取自审定表 D1-1）」；第 4 条的冒烟范围写作「D1 底稿『附注上市』页签」。任务 13 的 HTML 底稿样本同此，不再写 `C-D1-disclosure`。

⑦测试：路由纯函数的表驱动用例与 AST 守卫（①）；审计工具对 D1、D2 算出的 c-note-table reached_by 为空，用临时 overrides 映射把 D1 附注 sheet 路由到 `c-note-table` 时非空（②；夹具传入映射，不改真实 JSON）；核心 entry 的 reached_by 为空或与记录不一致时 `--check` 退出 1（③）；render-config 核心错误形状与 GtWpRenderer 的提示（③）；D1TabDisclosure 组件测试：10000 元在万元下显示 1.00、在元下显示 10,000.00，0.2 显示 20.00%，`data-gt-value` 为原值（④）；把任一 `GtAmountCell` 换回 `fmtAmount` 字符串、把比例格改成 amount 的变异必须红。

**H2 13A-1 移为阶段 A 第一个任务（R4-2；修订 §17 G7 的阶段 A 顺序）。** 13A-1 只用 git 与文件系统，不依赖 1A~7 的任何产物。阶段 A 顺序改为：13A-1 → 1A → 2 → 3 → 4 → 5 → 6A → 7 → 11A → 12A → 13A → A-V → A-BK。需要候选树的任务各自用 `build` 与 `checkout` 现建、用完 `release`：1A 第 3 条「schema 变更不改账套金额」在含 1A 改动的候选树上运行；6A 的 §17 G5② 只读探针在含 6A 改动的候选树上运行，探针放子进程，cwd 为候选 worktree 的 `backend`，`sys.path` 首项为该目录，不从主工作树导入。候选树清单只列 ownership 已登记的本任务路径。13A-1 自身的测试不变。阶段 B、C 的依赖说明不变，它们依赖 13A-1 与 13A，本就排在后面。

**H3 drift 比较让两侧都经 PG 渲染（R4-3；修订 §16 F7 的 drift 段与 §17 G9①④）。** 比较不读 `information_schema.columns`，也不比 ORM 的原始文本。V_A 在世界 schema 中执行后，用例在同一 schema 为本组每张表建一张探针表 `gds_orm_probe_<表名>` 并 `create`：
- 列取自待比较元数据（`GT_DISPLAY_PREFS_ORM_SOURCE` 指向的草稿；未设置时为 `app.models`），对本组每列用 `Column(c.name, c.type, nullable=c.nullable, server_default=c.server_default, primary_key=c.primary_key)` 重建，不复制外键（外键不在比较项内）；`projects` 只取 `amount_unit`，另加占位主键 `_probe_pk integer`。
- CHECK 约束用 `CheckConstraint(ck.sqltext, name=ck.name)` 按原名复制；PG 的 CHECK 约束名只需在表内唯一，同名不冲突。

然后对 V_A 建出的表与探针表执行同一条目录查询，逐项比较：
- 列：只取本组列，常量 `GROUP_COLUMNS = {"user_display_preferences": <全部列>, "projects": ("amount_unit",)}`；比较 `attname`、`format_type(atttypid, atttypmod)`、`attnotnull` 与 `pg_get_expr(adbin, adrelid)`（无默认值时为 NULL）。
- CHECK：取 `contype = 'c'` 且 `conkey` 只涉及本组列的约束，按 `(conname, pg_get_constraintdef(oid))` 的集合比较。
- 主键与唯一约束：只比较 `pg_get_constraintdef(oid)`（形如 `PRIMARY KEY (id)`），不比较名称，因为它们占用 schema 内的索引命名空间，探针表上的名称必然不同；`projects` 不比较主键。

用例先断言两侧取到的列集合都等于 `GROUP_COLUMNS` 且非空，防止空比较假绿。三项磁盘变异各自必须红：改草稿某列的 `server_default`、从 CHECK 枚举中去掉 `wan`、改某个 `String` 的长度。§16 F7 中「按 `information_schema.columns` 逐列比对」的写法与 §17 G9① 未规定方法的比较项都以本条为准。

| NIT | 处置 |
|---|---|
| R4-N2 render-config 核心错误形状 | 并入 H1③ |
| R4-N1、R4-N3、R4-N4、R4-N5 与沿用的 N2~N12 | 本轮未处理：门契约只修 HIGH/MEDIUM，这些 NIT 不改变本节的设计选择，留给后续评审裁决或实施时处理 |

文件边界在 §9、§15、§16、§17 的基础上增加：`backend/app/routers/wp_render_config_sheet_classify.py`（新）、`backend/tests/test_render_sheet_classify.py`（新）、`backend/app/routers/wp_render_config.py` 的逐 sheet 判定块（移出到新模块并改为调用，核对时干净）、`audit-platform/frontend/src/components/workpaper/d1/D1TabDisclosure.vue` 的金额与比例显示块（核对时干净）、`GtCNoteTable.vue` 的单位字段标签与屏幕单位块、`GtWpRenderer.vue` 的 `measure_contract_error` 提示块（工作树已有他会话未提交改动，只合并本任务块）。§17 登记的三份 `C-*-disclosure.yaml` 只在 6A 第 1 步算出 reached_by 非空时才改。以上均已追加到 ownership 台账，实施前重读。
