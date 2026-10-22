# 设计文档：公式治理全覆盖收口

> spec：`formula-governance-coverage-closure` · 需求见 requirements.md（R1~R7）
> 原则：复用治理内核（`services/formula_settings/`）与既有执行器，不另起存储；新逻辑放新模块，
> 白名单大文件只做最小接线（`formula_push/engine.py` 951 / `report_engine.py` 2693 / `checklist_responses.py` 780）。

## 0. 对评估结论的一处更正

评估里把 `prefill_formula_mapping.json`（311 条映射）列为「不可治理」，**这是错的**：`WpStore.system_presets`
（`domain_stores.py` 第 72~104 行）早已把它作为底稿域的系统预设层，全局 / 本项目 / 模板层都能覆盖它。
真正不在内核里的是：公式推送规则（`formula_push/rules.py:39` 直读 JSON）与十余套校对规则。R2 / R3 据此定范围。

## 1. 现状核验（2026-10-22，代码与真库现查）

| # | 事实 | 出处 |
|---|---|---|
| F1 | `POST /api/formula/debug` 只挂 `get_current_user`，按请求体 `project_id` 直查试算表审定数 / 报表行 / 附注 / 底稿并原样回显；测试 8 例无 403 断言 | `routers/formula_debug.py:47-95`、`_build_context` |
| F2 | `wp_user_formulas` 四端点（列表 / 保存 / 恢复预设 / 校验预览）只挂 `get_current_user`，`_load_wp` 只按 id 取底稿；同类 `wp_formula.py` 有 `_authorize_wp_project` | `routers/wp_user_formulas.py:242/290/599/677`、`wp_formula.py:436-460` |
| F3 | `import-data` 只挂登录，`persist=true`（默认）调 `upsert_seed_presets` 改写**仓库跟踪文件** `formula_presets_seed.json`；同文件 `presets/custom` 已改为角色 + 候选审核 + 数据库 | `routers/formula_import_export.py:124-176`、`preset_library.py:559-606` |
| F4 | `GET /api/reports/{pid}/{year}/consistency-check` 只挂登录；`report_config` 中 logic_check / reasonability 公式真库 **0** 行 ⇒ 恒返回「0 条全部通过」 | `routers/reports.py:111-140`；真库计数 |
| F5 | 现有鉴权守卫只扫路径含 `{project_id}` 的端点（两个维度），上述 F1~F3 三类全在盲区 | `tests/test_project_endpoint_authorization_baseline.py` |
| F6 | 推送引擎 `rules = load_push_rules()` 读静态清单；独占键 `owned_item_ids(wp_code)` 只按文件算、不分项目 | `formula_push/engine.py:313`、`owned_keys.py:45`、`checklist_responses.py:215` |
| F7 | 推送规则 420 条，仅「公式来源」可改公式；`policy ∈ system/derived/editable`；system / derived 目标是 HTML 端保存时剔除的独占键 | `formula_push_rules.json`、`rules.py:42-62`、`checklist_responses.py:203-247` |
| F8 | 表间审核 `enable_aux` 预载：缺数据 ⇒ `aux_data[code]={}` ⇒ L1 `_handle_aux` 返回 0；PREV 同理；不看 `strict_context`；查询裸写 `is_deleted`；`except Exception` 重复两次 | `report_engine.py:874-933`、`formula_engine.py:884-917` |
| F9 | 上一条的后果：既有守卫 `test_user_rules_run_with_builtin_checks_and_unresolvable_is_failure` 现红（「取不到」规则得到「左侧 0 = 右侧 100.00 不成立」而非「无法取数」）；若另一侧也是 0 就会**冒充通过** | `tests/formula_settings/test_tb_detail_and_cross_check.py:139-160` |
| F10 | 底稿可编辑公式求值器只代入 WP / SUM_TB / TB，再以空上下文执行；矩阵把其余 7 个函数判不支持（保存即 422，fail-closed） | `wp_formula_eval_service.py:267-359`、`function_support_matrix.py` |
| F11 | 统一预载层 `aux_data` 恒为 `{}`；行次缓存必须调用方自带；`_load_tb` 裸写 `is_deleted` | `formula_preloader.py:355-401` |
| F12 | 5 个组件从未被任何提交挂载（`git log -S "<Name"` 为空）：`GtFormulaHintPanel` 262 / `GtFormulaIssuePanel` 247 / `GtRowNameAlignmentTag` 145 / `FormulaImportExportDropdown` 110 / `GtDraftStateBadge` 90（实施时按「当前无生产引用」现算为 6 个：另有曾挂过又被替换的 `NoteFormulaDialog` 340，见 §6） | `components/formula/` |
| F13 | `applyFormulaPackage` 用 `POST .../overrides`，后端只有 `PUT` ⇒ 「导入公式包」恒 405（唯一入口在未挂载的下拉里，所以无人发现） | `composables/useFormulaImportExport.ts:484`、`routers/formula_settings.py:323` |
| F14 | 公式管理中心打开时执行一次表间审核（`report-cross-check`），只取 `results` 画 ✅/❌，问题清单 `issue_list` 与提醒 `hints` 被丢弃 | `components/formula/composables/useCrossCheckRules.ts:61-98` |
| F15 | 初稿标记 `draft_marker` 无任何读接口；真库 16 行全是测试运行时产物（`_FMRUNTIME_*` sheet） | `services/draft_refresh_service.py`；真库现查 |
| F16 | 真库：`formula_setting` / `formula_template` / `formula_publish` / `formula_sync_item` 均 0 行；`report_config` 项目行 183 只属 1 个项目 | 真库现查 |
| F17 | 【测试】项目：公式同步集团 `3a3930db`（合并）+ 甲 `4c77f3e8` + 乙 `e8c40d30`，均 listed、无审计年度 | 真库现查 |

## 2. R1 越权修复

| 端点 | 改法 | 级别 |
|---|---|---|
| `POST /api/formula/debug` | 函数首句 `assert_project_permission(db, user, project_id, "readonly")`（项目在请求体，工厂依赖取不到）；无效 UUID 仍返回「无效的项目 ID」 | readonly |
| `GET /workpapers/{wp_id}/user-formulas` | 复用 `deps.authorize_wp_read`（对象反查项目，平台既有口径） | readonly |
| `PUT /workpapers/{wp_id}/user-formulas`、`DELETE …/{cell_key}` | 复用 `deps.authorize_wp_edit` | edit |
| `POST /workpapers/{wp_id}/validate-formula` | `authorize_wp_read` 反查项目；请求体 `project_id` 与之不一致 403；预览一律用反查出的项目 | readonly |
| `POST /formula-management/import-export/import-data` | 带 `project_id` 先校验 readonly；`persist=true` 需 `_CUSTOM_PRESET_WRITE_ROLES`；管理员 → `custom_presets.upsert`（数据库）+ 刷新缓存，其余 → `custom_presets.submit_candidate`（全局候选）；**删除对仓库 seed 文件的写入** | 角色 + 候选 |
| `GET /api/reports/{pid}/{year}/consistency-check` | `require_project_access("readonly")`；0 条可执行公式时返回 `no_result: true`，前端显示「暂无可执行的审核公式」而非「全部通过」 | readonly |

- `upsert_seed_presets` **保留**：去掉在线导入调用后，仍被两个离线生成脚本使用（`scripts/gen/generate_note_cross_check_presets.py` / `generate_note_formula_data.py`，维护人员重生成基线 seed 后经 git 提交 —— 这是改仓库文件的正当通道）。只切断「在线端点改写仓库文件」这一条路径。
- 前端：导入入口（R4 挂载的下拉）按角色门控「导入数据」；非管理员导入后提示「已提交为全局候选，待管理员审核」。审核报表按钮对 `no_result` 走空态。
- 守卫（R1.7）：在 `test_project_endpoint_authorization_baseline.py` 加第三维「对象 / 请求体型」：
  路径含 `{wp_id}` 或函数参数里有 `project_id`（请求体模型字段或查询参数）、只挂身份认证、函数闭包（本模块二层）内无项目级 token 的端点 ⇒ 冻结基线（现算登记，只许变小）；
  本 spec 修过的 7 个端点逐个列入「已修钉子」，任一回退即红；扫描器配双向变异（注入缺口必命中、补上鉴权必放行）。
- 端点级测试（TestClient 真实鉴权链，只替换身份与取数下一层，禁 override 工厂）：非成员 403 且**不触达数据**（断言 `_build_context` / 写库函数未被调用）、成员 readonly 可读、edit 可写、管理员放行。

### 2.1 实施勘误与扩围（2026-10-22，以代码为准）

- 🔴 **更正评估**：`wp_user_formulas` 四个端点在生产经 `router_registry/workpaper.py` 的注册循环挂了 router 级 `dedicated_wp_gate`（可见性隔离，非委派 / 跨项目一律 404），不是「只校验登录」。处理函数里补的 `authorize_wp_read` / `authorize_wp_edit` 是第二道（项目成员 + 编辑级）。真缺口只有 validate-formula：可见性门只看路径上的底稿，预览却按**请求体**的 `project_id` 取数。测试分两层：生产注册确实挂了门 + 处理函数自身的项目级判定。
- 守卫没有改共享基线文件（多会话并发改同一文件，磁盘上后写者覆盖），第三维放新文件 `tests/test_project_endpoint_authz_body_carried.py`：
  - 「带项目」= 参数名 `project_id`，或从参数上读 `project_id`：属性（请求体模型）/ `["project_id"]` / `.get("project_id")`（首版只认属性，漏了地址库三个 `body: dict` 端点）；路径带 `{project_id}` / `{wp_id}` / `{wp_index_id}` 的归前两维与可见性门。
  - 「函数闭包二层」改为**额外项目级标识 + 证明链**：本地 / 服务层 helper（`check_project_access` / `_ensure_project_access` / `_authorize_doc_host` / `_authorize_report_config_read|write` / `_assert_writeback_authorized` / 本 spec 的 `_assert_context_project`）各登记一条 AST 证明链，末环须落到项目级判定（基线标识 / `ProjectUser` / SQL 里的 `FROM project_users` / 项目可见集 / 底稿可见性门），且路由里用到的必须是证明过的那一份（本地定义或从链上模块导入；属性引用、自写同名、同族名一律报出）。docstring 里的表名不算证据。
  - 冻结：仅登录 / 仅角色 **93**（首次现算 111；误判 21 个由证明链消除）；无鉴权 **5**（`_BODY_KNOWN_GAPS`，只许变短）；自鉴权 1（MCP scoped token）。
  - 变异：合成样本（四种带项目写法 × 三档）+ **真实源码 AST 变异**（逐个摘掉已修端点函数体里的项目级判定语句，扫描器必须判回仅登录）。
  - 路径维（第一维）的两个已修端点（报表审核、附注公式开关）在新文件里逐个钉住；第一维现算 200（共享基线常量 207，差 7 未超 20，未改共享文件）。
- 第三维抓到、属公式链路、本 spec 一并修的端点（都只有角色门或只有登录）：

| 端点 | 改法 | 级别 |
|---|---|---|
| `POST /api/workpapers/draft-refresh` | 按请求体项目 `assert_project_permission`（全局一键刷新批量改写底稿 / 报表 / 附注初稿） | edit |
| `POST /api/workpapers/draft-refresh/{run_id}/rollback` | 按运行记录反查项目；记录不存在 404 | edit |
| `GET /api/workpapers/refresh-scopes` | 按查询参数项目（枚举底稿循环） | readonly |
| `POST /api/formula-management/presets/custom` | 带 `project_id`（引用解析上下文）时校验，无效 UUID 400；与导入共用 `_assert_context_project` | readonly |
| `POST /api/workpapers/batch-refresh` | 按请求体项目（同文件另两个端点按底稿判编辑权，只有它路径没有 wp_id、可见性门 no-op） | edit |
| `PUT /api/disclosure-notes/{pid}/formula-gray` | 角色门之外再校项目（附注公式灰度开关） | edit |

- 前端（R1.8）：全局一键刷新入口按钮由「合伙人」改为「合伙人 + 本项目编辑级成员」（`roleContext.canEditInProject`，DefaultLayout 按路由项目加载）。其余收紧端点的入口本就只对编辑者 / 管理员可见。

### 2.2 范围外发现（冻结在守卫里，待用户裁决，不在本 spec 改）

| 优先级 | 端点 | 问题 |
|---|---|---|
| P0 | `GET /api/metabase/embed-url` | **未登录**即可按任意 `project_id` 签发 Metabase 嵌入 JWT（10 分钟有效） |
| P1 | `POST /api/linkage-bus/impact`、`GET /api/linkage-bus/impact-by-addr`、`POST /api/address-registry/v2/notify-cell-change` | 任一登录用户可给任意项目的底稿 / 报表 / 附注 / 交付件打 stale 标记（`stale_engine.on_change` 写库；GET 也写） |
| P1 | `GET /api/linkage-bus/audit-log` | 不带 `project_id` 时返回全部项目的联动日志 |
| P2 | 地址库 6 个端点、`/api/workpapers/field-overrides` 读写 | 仅登录，按请求里的项目读写 |
| P2 | `reports.py` 的 `get_report` / `drilldown_report_row` / `export_report_excel` | 路径带项目但只校验登录（第一维冻结项） |
| — | `metabase.build_drilldown_url`、`feature_flags` 旧端点、`b60_chapters.get_chapter_definitions` | 无鉴权，但不读库或只读静态定义 |
| — | 全局一键刷新角色集合 | 后端 draft-refresh 放行 admin，refresh-scopes 与前端入口不含 admin（真库 0 个合伙人 ⇒ 入口无人可见） |

## 3. R7a 表间审核严格取数

> 🔴 实施调整（2026-10-22）：`report_engine.py` 正被另一会话改 PREV / AUX 预载（工作树未提交，且其 AUX 预载仍从不存在的
> `app.models.four_table_models` 导入 ⇒ 恒失败、恒 0）。本 spec **不动 report_engine**：严格取数在表间审核自己的求值入口
> `cross_check_rules._evaluate` 做 —— 先用新模块把 PREV / AUX **按值代入**（缺数即报「无法取数」），再以
> `enable_prev=False, enable_aux=False` 交 `evaluate_formula_result`，不经过 report_engine 的预载分支。报表生成路径行为不变；
> report_engine 改调新模块、删重复分支留待对方提交后另行收口（登记在交付说明）。下面的模块口径不变。

把 `report_engine.evaluate_formula_result` 里 PREV / AUX 的预载搬到新模块 `services/formula_ref_preload.py`（report_engine 净减行数）：

- `preload_prev(resolver, formula, *, strict)`：上年试算表**整体无行** ⇒ strict 抛 `ValueError("PREV：无上年试算表数据")`；有行但该科目无 ⇒ 0（科目上年不存在是合法 0）。
- `preload_aux(resolver, formula, *, strict)`：按 `AUX_PATTERN` 的（科目, 维度）取数；查询走 `get_active_filter(db, TbAuxBalance.__table__, …)`；该科目该维度无行 ⇒ strict 抛 `ValueError("AUX('科目','维度')：无辅助核算数据")`。
- 非 strict（报表生成路径）行为不变：仍按原样置 0（矩阵已标「报表路径不支持」）。
- `cross_check_rules._evaluate` 本来就传 `strict_context=True`，抛错被既有分支记为「无法取数（原因）」。
- 守卫更新：`test_user_rules_run…` 的「不支持」断言改为断言具体原因（AUX 已支持，原因变了；核心语义「取不到不冒充通过」不变）；新增「AUX 缺数 + 另一侧为 0 ⇒ 仍判无法取数、不通过」与「PREV 无上年数据」两例；变异：去掉 strict 抛错 ⇒ 两例必红。

## 4. R2 推送规则纳入治理内核

### 4.1 push 域定义

`definitions.DOMAINS["push"] = DomainSpec("push", "公式推送规则", exec_fields=("expression",), desc_fields=("description",), scope_kind="any")`。
公式位 = `rule_id`（如 `E1.tb_amount.ending`）；作用范围恒 `*`（规则本身不分准则，附注目标的准则差异在规则内部 `section_by_template`）。

| 预设规则 | 系统预设层定义 | 结构信息（`structure`，只读） |
|---|---|---|
| 公式来源 | `{"expression": 原公式, "description": 说明}` | `wp_code / stage / policy / source_kind / target / triggers` |
| 四表叶子 / 派生来源 | `{"expression": "", "description": 说明}` | 同上 + `formula_text`（中文算式） |
| 清单里 `status != active` | `{"disabled": true}` | 同上 |

### 4.2 新模块 `formula_settings/push_settings.py`

- `PushStore(SettingStore)`：`system_presets` 由 `formula_push.engine.load_push_rules()` 现算（按清单元组身份缓存）；`write_global` / `write_project` 先 `validate_push_definition`。
- `validate_push_definition(slot_key, definition, label)`（模板发布 `domain_stores.validate_definition` 同样调用）：
  1. 规则不存在 ⇒「推送规则不存在」；
  2. 停用：`policy ∈ system / derived` ⇒ 拒绝（R2.6，文案写明独占键原因）；其余放行；
  3. 非公式来源而 `expression` 非空 ⇒「该规则来源是四表明细 / 派生计算，只能停用或启用，不能改写公式」；
  4. 公式来源：`expression` 必填；用规则原 `context` 拼出候选来源，调 `rules._check_source(..., binding_spec=该底稿 binding)` —— 与清单加载**同一套**校验（语法、白名单、禁用列名、`TB()` 列名、binding 已装载列、context 与 TB / ADJ 匹配）。
- `effective_push_rules(db, project_id) -> (rules, issues)`：对静态清单逐条叠加本项目有效定义（`effective_slots(db, "push", pid)`）：停用 ⇒ `status="disabled"`；改写公式 ⇒ `dataclasses.replace(source, expression=新公式)`；运行时复验不过 ⇒ `status="invalid"` 并记入 `issues`（R2.5：跳过、不回退预设）；预设停用而上层启用 ⇒ `status="active"`。

### 4.3 接线

| 位置 | 改动 |
|---|---|
| `formula_push/engine.py::_execute` | `rules = load_push_rules()` → `rules, issues = await effective_push_rules(db, project_id)`；`issues` 写进运行结果的提示；新增运行触发来源 `FORMULA_CONFIG_CHANGED`（选规则时按 `manual` 口径，记录时保留原值） |
| `routers/formula_push.py::list_rules` | 返回本项目有效规则 + 每条 `layer / layer_label / disabled / pending / editable_formula / can_disable / local_version`；列出全部规则（含已停用），不再只列 active |
| `formula_settings/propagation.py` | `HANDLERS["push"] = propagate_push`：按公式位前缀得底稿主编码，合并项目跳过，无审计年度跳过，`run_and_commit(trigger=FORMULA_CONFIG_CHANGED, codes=…)` |
| `stores.get_store` / `domain_stores.validate_definition` / `definitions.display_formula` / `rollback.py` / `dependencies.FORMULA_FIELDS` / `routers/formula_settings.WIRED_DOMAINS` | 加 push 域（展示字段 `expression`） |
| 前端 `FormulaPushPanel.vue` | 规则表加「层级」列与操作列：改写公式（`FormulaDefinitionEditDialog`）/ 本项目停用 / 启用 / 恢复上游；走既有 `formulaSettingsApi.saveOverrides('push', …)` / `restoreGlobal`；保存后重载规则与最近运行 |
| 前端 `formulaPushView.ts` | `TRIGGER_LABELS` 加「公式规则变更」；新增纯函数 `ruleActions(rule)`（哪些操作可用及原因），单测覆盖 |
| 前端 `useFormulaSettings.definitionText` | `{"disabled": true}` 显示「（已停用）」；全局设置页对空表达式的 push 规则显示中文算式 |

### 4.4 不做

- 不改 `formula_push_rules.json`，不迁移到数据库（ADR-FGC-001）。
- 不开放目标、写入策略、触发事件的改写（改它们会破坏「一个单元格只有一个写入方」与独占键口径）。
- 独占键（前端生成文件 + 后端 `owned_keys`）保持按清单计算：因 R2.6 不允许停用系统值 / 派生值规则，独占集合不随项目变化，前后端无需改。

### 4.5 实施勘误与补充（2026-10-22，以代码为准）

- 🔴 **新增第五类拒绝「推送取数给不出数」**（设计时漏了）：推送上下文只按底稿 binding 的科目取试算表审定数 / 大厅调整（`load_tb_audited` 以这些科目为**键**），公式引擎对缺键按 0 取值 ⇒ 改写成别的科目或别的取数函数（PREV / AUX / REPORT / SUM_TB …）会**静默推 0**。`push_settings.push_context_errors`：函数只限 TB / ADJ + ABS / ROUND / MAX / MIN / IF，TB / ADJ 的科目必须是带引号的文本且属于该底稿推送取数科目。写入各层与运行时复验同一函数。
- 🔴 该校验对规则清单本身现算出 **5 条系统规则恒推 0**（登记 §9，守卫 `KNOWN_PRESET_CONTEXT_GAPS` 只许减少）。
- 失效定义的提示按规则的底稿编码过滤（不按 `rule_id` 前缀猜）；传播 handler 同样按规则清单反查底稿编码，规则不存在 ⇒ `no_rule`；年度不符等业务不可推（`PushActionError`）记 `not_pushable`，与推送事件同口径不算故障。
- 定义里的 `_structure`（模板条目随带）接收但不落库；全局 / 本项目层读出时按规则清单补结构，全局设置页对四表明细 / 派生来源显示中文算式。
- 公式目录（`formula_catalog`）随 `DOMAINS` 自动纳入 push 域：92 条公式来源规则以系统预设进目录（`test_stats_aggregation` 改为现算）。
- 规则列表的旧守卫写死「E1 有 30 条」，清单早已是 31 条（HEAD 上就红）⇒ 改为按清单现算；端点鉴权 AST 守卫把全局静态端点 `push_coverage` 当项目端点（HEAD 上就红）⇒ 显式豁免 + 反向断言（路径无项目、只依赖登录）。
- 顺带修推送反向校验面板：`handleApiError(e, { silent: true })` 把对象当操作名传入，弹「[object Object]：…」且返回 void ⇒ 改静默请求 + 面板内中文原因。

## 5. R3 校对规则统一目录

新服务 `services/formula_check_catalog.py`：一张登记表 `SOURCES`，每个来源 = 键、中文名、分类、执行位置、能否在平台里编辑（及去哪编辑）、加载函数。只读现有规则源，不新增存储。

| 来源 | 规则源 | 执行位置（现查） | 可编辑 |
|---|---|---|---|
| 报表勾稽内置 | `formula_management/logic_check.py::_CROSS_CHECK_SEEDS`（7） | 公式管理中心打开 / 表间审核执行 | 否 |
| 表间审核规则 | `formula_setting` 域 cross_check（全局层；项目层在公式管理中心看） | 同上（`run_user_rules`） | 是：公式管理中心 / 全局公式设置 |
| 表间审核预置 | `cross_check_preset_rules.json`（6） | 现无消费方 ⇒ 本 spec 接到「新增规则」弹窗的「从预置选用」 | 选用后可改 |
| 报表审核公式 | `report_config` 类别为 logic_check / reasonability | 报表页「审核」 | 是：公式管理中心报表公式 |
| 合并附注勾稽 | `consol_note_sections_{soe,listed}.json` 的 check_rules（`note_check_rules.load_all_check_rules`） | 合并附注页 | 否（随模板） |
| 附注预置勾稽 | `note_check_preset_formulas.json` 中类别 logic_check 的条目 | 附注公式执行 | 是：附注公式 |
| 附注披露平衡 | `note_disclosure_balance_rules.json`（6） | `NoteDisclosureBalanceService`（现无调用方，如实标注） | 否 |
| 底稿跨科目校验 | `cross_account_rules.json`（8）+ 项目自定义 | 底稿跨科目校验 `wp_cross_check` | 项目自定义规则可增 |
| 循环校验规则 | `*_cycle_validation_rules.json`（12 个文件） | 签字前一致性门禁（代码实现同编号规则）/ 底稿校验规则展示 | 否 |
| A17 一致性 | `a17_consistency_rules.json`（8） | A17 汇总 / 导出 | 否 |
| 质控规则 | `qc_rule_definitions_seed.json`（22） | 质控引擎 | 质控规则管理 |
| 跨底稿引用 | `cross_wp_references.json` | 底稿关系图 / 依赖图 | 否（取数关系，非校对，单列） |

- 接口：`GET /api/formula-catalog/check-rules`（登录即可：静态规则，不含项目数据），返回 `sources[]`（含 `rule_count` 与 `rules[]`，每条 `id / label / expression / severity / scope`）。
- 前端：`components/formula/settings/FormulaCheckCatalog.vue`（来源列表 + 规则表 + 搜索）；全局公式设置页加「校对规则目录」页签（`?tab=checks` 直达）；公式管理中心表间审核面板加「全平台校对规则目录」入口；新增表间审核规则弹窗加「从预置选用」。
- 守卫：`backend/data/` 下文件名含 `rule` / `check` 的 JSON，必须在 `SOURCES` 登记或在 `EXCLUDED`（附理由，如运维告警、账套识别、解析规则）登记；`EXCLUDED` 无失效条目；每个来源加载不报错且规则数 > 0（表间审核全局层允许 0）。

### 5.1 实施勘误（2026-10-22，以代码为准）

- 接口三种形态：不带参数只回来源清单与计数（不带规则，免得一次拉 1650 条）；`?source=` 回该来源全部规则；`?q=` 跨来源检索（每来源最多 500 条，带 `matched`）。单个来源加载失败只标在该来源（`error`），不拖垮目录。
- 现算规模 12 个来源 / 1650 条（不含两个全局设置来源）：报表内置 7、表间审核预置 6、合并附注勾稽 117、附注预置 932（勾稽 792 + 提醒 140：提醒类同属校对，一并收录）、附注披露平衡 6、底稿跨科目 8、循环校验 114（12 个文件）、A17 8、质控 27（`qc_rule_definitions_seed` 22 + `audit_log_rules_seed` 5）、跨底稿引用 425（旧注释写的 400 已过期）。
- `EXCLUDED` 12 项（含 `workpaper_sync_contracts/` 目录前缀：文件名里的 check 是底稿名）；静态来源按文件修改时间缓存，全局设置来源每次读库（包保存点）。
- 「从预置选用」放在表间审核编辑弹窗页脚（选中即填名称 / 两侧 / 运算符 / 说明，保存前可改）；放表单顶部会与另一会话在同一文件的未提交改动挤进同一个差异块。

## 6. R4 零挂载组件处置

现算 6 个（初稿写 5 个，漏了 `NoteFormulaDialog`：2026-04-29 挂进附注页，05-02 被公式管理中心替换后再没挂过）。逐个查来历、数据源与功能重叠：

| 组件 | 判定 | 处置 |
|---|---|---|
| `GtFormulaIssuePanel` | 有独立价值：表间审核面板只画 ✅/❌（F14），不通过项的左右值 / 差额无处可看 | 接进 `FormulaCrossCheckPanel`：「报表 ↔ 附注」分组节点看全部，单条勾稽节点只看自己（`formulaIssueHint.issueRunForNode`）；树点击原先只认叶子 ⇒ 有子节点的分组节点选不中，「报表 ↔ 附注」（有内置结论时）与「合并 ↔ 报表」（恒有三个子项）的规则集恒点不到，一并修为分组节点可选中；数据取自 `loadExecItems` **同一次**响应（`issueHintFromRun`），不另调（该接口每调一次落一次运行记录）；「刷新 / 重试」= 显式重跑，只刷新勾稽结论不重载用户规则 |
| `GtFormulaHintPanel`（+ `useFormulaIssueHint`） | 无数据源：接口的 `hints` 是字符串、组件按对象收；真库 33 次运行 `hint_count` 全 0，没有合理性公式产出提醒 | 删除；`hints` 非空时在表间审核面板内联显示。合理性提醒要先有产出方（另立 spec） |
| `FormulaImportExportDropdown` | 有独立价值：后端在、前端无入口 | 按两类数据分开挂（`mode`）：**预设库 Excel**（导出模板 / 导出数据 / 导入数据）挂「公式预设库」弹窗，导入按写预设角色门控（`PRESET_WRITE_ROLES` 与后端 `_CUSTOM_PRESET_WRITE_ROLES` 守卫对齐），非管理员导入提示「已提交为全局候选」（原先一律报「成功导入」）；**本项目公式包**（JSON）挂公式管理中心顶栏 |
| `GtRowNameAlignmentTag` | 与对齐弹窗内联的状态标签重复（同一组 match_state 文案 / 颜色两份） | 弹窗行列表改用该组件（弹窗内模式：点击不发「打开弹窗」事件 —— 会清掉弹窗里未确认的勾选；「重新确认」= 激活该行），删除弹窗里的重复映射；未知状态照实显示 |
| `GtDraftStateBadge` | 无数据源：初稿标记无读接口，真库 16 行全是测试产物（F15）；且无标记时显示「已审定」会误导 | 删除；「初稿状态展示」需新增标记查询接口与报表 / 底稿行级接入，另立 spec |
| `NoteFormulaDialog` | **不是被取代**：附注章节公式集的保存（PUT 附注章节公式，带载入令牌，写本项目适配）只有它在调；公式管理中心里附注行按 `formulaRowKind` 的「其余 → report」分派，「编辑」发 report-config 必失败，「+ 新增公式」只加在页面上不保存，「💾 保存」对附注行一条不存还报「已保存 0 个」 | 接进公式管理中心附注节点：「✏️ 编辑本章节公式」（没有具体章节时禁用），附注行的编辑 / 新增 / 保存全部交给它；在附注根节点从某行进入时用该行所属章节，且须是本项目附注里的章节（预设行章节号来自模板，国企 / 上市编号不同：实测安徽项目货币资金是「八、1」、预设行是「五、1」），找不到就提示、不打开空弹窗；`formulaRowKind` 新增 `note` 分派；保存后强制重取本章节公式（不用已加载缓存）并通知宿主 |

本项目公式包（`composables/formula/formulaPackage.ts`）：

- 导出只收本项目适配（本项目 / 模板 / 暂缓采用）；系统预设、全局设置不进包 —— 每个环境本来就有，带进包再导入会把全局复制成目标项目的适配，以后全局一更新这个项目反倒要逐条确认。任一类读取失败整体失败，不生成缺类的包；0 条不生成文件并说明原因。
- 导入走 `PUT overrides`（F13：原 `POST` 恒 405）+ 本地修订号；与目标项目现有定义相同的不写；适用范围不同（同一行编号在国企 / 上市模板里不是同一项）或项目已归档整类跳过；逐类报告写入 / 未改 / 跳过 / 失败。须有本项目公式编辑权限。
- 类别清单取后端 `/formula-settings/domains`（含推送规则），不在前端写死；只在项目上下文提供（原全局导出用 `scope='*'`，对多数类别取不到行）。

守卫（`components/formula/__tests__/formulaComponentMounts.spec.ts`）：`components/formula/**/*.vue` 每个组件至少被一处**生产代码**引用（import 路径，或 PascalCase / kebab-case 标签）；测试、`components.d.ts`、stories、注释里提到、自身引用都不算；扫描面非空自检 + 判据双向自检。

实施勘误（与初稿不同处）：

- 导入导出下拉初稿整个挂公式管理中心顶栏：顶栏已有「📤 导出模板」（导出当前节点公式），预设库 Excel 再挂进去会出现两个含义不同的「导出模板」，且预设库是平台级不是项目级 ⇒ 按数据分开挂。
- 提醒面板初稿接入，查实无产出方后删除。
- `NoteFormulaDialog` 初判「被公式管理中心取代、删除」，核对保存路径后改为接入（详见上表）。
- 表间审核内置勾稽的请求原用 `validateStatus < 600`，403 / 500 被当成「无结果」；改为失败如实呈现（原因 + 重试）。

## 7. R6 底稿可编辑公式补齐函数

现状：求值器先把 WP / SUM_TB / TB 代成数值，再以空上下文跑 L1；矩阵把其余函数判不支持，保存即 422（fail-closed，F10）。但读取 / 渲染时求值预设不经保存端点，AUX / PREV / TB_AUX / LEDGER_DETAIL 等落进 L1 空上下文就是静默 0。改为（实施结果，与原设计的差异见文末勘误）：

1. **严格按值代入**（`formula_ref_preload.substitute_value_refs`，与 R7a 表间审核同一模块）：PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 在求值前换成数值，取不到数写原因：
   - PREV：上年试算表、科目前缀聚合；上年整体无数据 ⇒ 缺数；有数据无该科目 ⇒ 0。三参 `PREV('底稿','表','单元格')` 是上年底稿取数 ⇒ 不支持（原先被当成试算表取数、报「列名无法识别」）。
   - AUX：辅助余额当前数据集（`get_active_filter(strict=True)`）、科目前缀。四参按（辅助类型, 辅助项）；三参 / 两参的第二参先按辅助类型（该类型合计），不是类型再按辅助项名称或编码（地址选择器生成的就是这种写法）；同一辅助项出现在多个辅助类型下 ⇒ 缺数（报歧义，不跨类型相加）。列名另认地址库登记的「期末 / 期初」。
   - ROW / SUM_ROW 取本年度报表本期金额；REPORT 期间按关键词先认上期（期初 / 上期 / 上年 / 年初）再认本期（期末 / 本期 / 本年 / 年末），认不出 ⇒ 缺数。本年度报表没有任何行、行次不存在、金额为空 ⇒ 缺数（【测试】项目上期金额全为空，`REPORT(…,'期初')` 如实报缺数）。
   - NOTE（`disclosure_notes`）：先找主表，主表没有该行再找其余表格（多张都有 ⇒ 歧义）；「合计」无同名行时取主表最后一个合计行；列名精确匹配表头，只写期间（期末 / 期初 …）时按期间语义找唯一一列（多列 ⇒ 请写完整列名）；表头与数据列数不一致、单元格为空 ⇒ 缺数。
2. **求值器流程**（`wp_formula_eval_service.evaluate_wp_formula_expression`）：含不支持函数（序时账 LEDGER / COUNT_LEDGER / LEDGER_DETAIL、TB_AUX、PREV 三参）⇒ 报错且不求值、不取数 → 跨 sheet 引用 → 严格代入（须先于 TB：`PREV(TB(…))` 里的 TB 是上年）→ WP / SUM_TB / TB（参数间允许空白，原正则不认空白 ⇒ 静默 0）→ 代入后仍残留取数函数 ⇒ 报「写法无法识别」→ ADJ 经 `preload(adj_exclude_origins=frozenset(), gaps=…)` 交 L1（底稿口径含底稿来源分录；报表口径排除，同一数据 130 / 100 两口径有用例钉住）。
3. **统一预载层**（R6.5，预填充同一入口）：AUX 按引用写法逐个取数（与 1 同一取数函数 `resolve_aux_refs`），存 `aux_data[科目][aux_ref_key(参数)]`；L1 `_handle_aux` 先取该键、没有再退回旧口径 `aux_data[科目][维度]`（报表路径按维度预载，不受影响）。调用方没给 `row_cache` 且公式引用 ROW / SUM_ROW / REPORT 时读本年度报表本期金额。`gaps` 出参收集取数缺口（报表未生成、辅助核算取不到、调整分录取数失败），预填充不传、行为不变。
4. **矩阵**：`wp_evaluator` 十个函数全部支持、删对应原因；golden 重算；前端 `functionSupportMatrix.ts` 同步（两侧对拍绿）。保存端点 422 逐项给原因（矩阵外函数的原因来自 `UNSUPPORTED_FUNCTION_REASONS`）并列出可编辑公式支持的函数（由矩阵算出）；F2 取数公式保留自己的拒绝清单（AUX / PREV / 序时账 / TB_AUX，F2 不走通用求值器）。
5. **保存时的引用校验（地址库）三处缺陷**——函数门放开后才暴露：
   - ROW 一律转成 `#本期`，资产负债表行登记的期间是「期末 / 期初」⇒ 资产负债表 ROW 恒判悬空；改按报表类型的本期名。
   - 附注域按「模板是列表」遍历，而模板文件是 `{"sections": [...]}` ⇒ 遍历到的是字典键、异常被吞、附注域恒为空 ⇒ 任何 NOTE 都判悬空；章节键改用章节编号（`section_number`，= `note_section` = NOTE 第一参）。
   - 辅助余额只登记辅助项、且按明细科目（真库 1122.01）登记，而 AUX 按科目前缀合计 ⇒ 类型合计与一级科目写法判悬空；补登记类型合计地址，AUX 校验认科目前缀。
6. **前端**：公式栏只挂在附注结构编辑器里，却缺省按底稿求值器门控 ⇒ 改为显式 `executor="note_executor"`（否则矩阵改动后会放行附注执行器不认的 ROW / SUM_ROW），并把年度 / 模板类型传下去；新守卫要求每个公式栏挂载点都声明执行器。公式栏取数弹窗：宿主没加载地址库时先按本项目 + 年度 + 模板加载；NOTE 改用地址库登记写法（原先拿地址标签当章节、列写死「期末」，插入即悬空）；地址库给不出附注条目时回退附注目录接口（原写的 `/api/disclosure-notes/tree` 不存在 ⇒ 回退恒为空列表），章节用编号；REPORT 用登记写法（含期间）；ROW / SUM_ROW 按行次去重。
7. 预载层 `_load_tb` 的 `is_deleted` 裸写保留：`trial_balance` 不是四表（不受数据集版本治理），与报表取数同口径；只有 `tb_aux_balance` 走 `get_active_filter`。

### 7.1 勘误（实施与原设计的差异）

- 原设计：ROW / SUM_ROW / NOTE / PREV / AUX / ADJ 由 `preload` 建上下文交 L1、`REPORT` 前置代入。实施：PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 全部严格按值代入，只有 ADJ 走 `preload`。理由：①`preload._load_note` 依赖另一会话尚未入库的 `formula_push/bindings/disclosure_source.py`，干净检出走 `_load_note_fallback`（把 `values` 列表当字典取，附注存在即抛错），两条路径都不按「行 × 列」取数；②L1 `_handle_prev` 不看列名、`_handle_report` 不看期间，经 L1 会得到错误的数而不是缺数；③按值代入能逐条写明缺数原因。
- 原设计：`_load_aux(specs)` 按（科目, 维度）汇总、填 `aux_data[科目][维度]`。按此实现，四参 `AUX('2001','金融机构','XX单位1','期末余额')` 会被 L1 读成「该类型合计」（L1 把第三参当列名）——比 0 更糟。改为按写法逐个取数 + L1 同键。
- 原设计：`FormulaContext` 新增 `missing` 字段。实施改为 `preload(..., gaps=list)` 出参，L1 数据类不加字段（严格调用方传列表，预填充不传）。
- 原设计未列、实施中发现并修：地址库三处缺陷（§7 第 5 条）、公式栏执行器与取数写法（第 6 条）、TB 参数空白静默 0、TB_AUX / LEDGER_DETAIL 在底稿求值器静默 0、F2 拒绝清单独立、PREV 三参被当成试算表取数。

### 7.2 验证（2026-10-22）

- 干净检出（基线 e018fc336 / 本提交 ebd13ffe6）同一测试集：基线 92 红 / 1476 绿，本提交 92 红 / 1506 绿，失败集合逐条相同（d-cycle 端点测试 `list_formulas() got an unexpected keyword argument '_user'` 等 HEAD 预存），新增失败 0。
- 一次性变异 23（后端）+ 8（前端）全部打红：报表未生成静默 0 / REPORT 忽略期间 / 附注不优先主表 / 期间模糊匹配放宽 / 跨类型同名辅助项相加 / 三参不认辅助项 / 不支持函数照样求值 / 代入非严格 / TB 先于 PREV / 残留写法不报错 / ADJ 用报表口径 / 预载 AUX 键漏列名 / 预载不读报表 / L1 不认预载键 / ROW 写死本期 / 附注域遍历字典键 / 附注章节键用 section_id / AUX 校验不认前缀 / 不登记类型合计地址 / 422 只给矩阵内原因 / 矩阵 ROW 回退 / F2 放行 AUX / PREV 三参放行；前端：附注结构编辑器不声明执行器 / NOTE 用标签当章节 / REPORT 不用登记写法 / ROW 不去重 / 前端矩阵回退 / 地址库未加载不先加载 / 回退又用 /tree / 结构编辑器不传年度。未变异基线全绿、逐字节恢复。单区域 vue-tsc：报出 6 处均在未改动的行（FormulaStatusPanel 第 359 行 `category: null`、stores/project.ts 5 处），基线 e018fc336 同 6 处，本次新增 0。
- 浏览器（无头 Chromium，安徽附注只读）：「📐 表样」→ 公式栏「📋 选择」：TB / NOTE / WP / REPORT 可点，ROW / SUM_ROW 置灰并提示附注执行器原因（修复前按底稿求值器门控，ROW / SUM_ROW / NOTE / REPORT 全灰）；NOTE 弹窗列出 166 个章节、插入 `NOTE('八、1','合计','期末余额')`（修复前空列表）；REPORT 弹窗插入 `REPORT('BS-002','期末')` / `REPORT('BS-002','期初')`；全程除登录外无写请求。底稿可编辑公式的保存 / 求值浏览器实测并入 R5（【测试】项目暂无底稿，走查中现建）。
- 真库只读核对（事务回滚）：安徽 `NOTE('八、1','合计','期末余额')` = 9,182,572.99 = BS-002 本期 = 附注合计行；`NOTE('八、1','银行存款','期初')` = 22,944,619.45；`REPORT('IS-001','本期')` = 894,804,876.83；`AUX('1122','客户','期末余额')` = 624,025,343.06（当前数据集；全部未删行合计 12.49 亿含已被替换的数据集，证明走的是 `get_active_filter`）；`ADJ('1122','aje_net')` = −1,000,000（已审批手工分录贷方 100 万）；`PREV('1001','期末余额')` 报「上年（2024）试算表无数据」；【测试】甲 `REPORT('BS-002','期初')` 报「上期金额为空」、`ROW('BS-002')` = 350、`NOTE('五、1',…)` 报「附注没有章节」。保存时校验：上述 ROW / REPORT / NOTE 合计行 / PREV 两参在真库通过（修复前 ROW 资产负债表行与 NOTE 全部判悬空）。

## 8. R5 真库全链路走查

用【测试】公式同步集团（`3a3930db`，合并）/ 甲（`4c77f3e8`）/ 乙（`e8c40d30`），均 listed、无审计年度。推送链路需审计年度与已接入底稿：走查前现查是否有合适的【测试】/【E2E】项目，没有就用平台同一路径临时建【测试】项目，用完软删。

| 步骤 | 验证点 |
|---|---|
| 甲本项目改 1 条 tb_detail 公式 → 全局发布同一公式位的新定义 | 预览：甲冲突、乙自动跟随；发布后甲出现待确认 |
| 进入甲 | 待确认弹窗自动弹出，三方对比；选「保留本项目」后弹窗消失、角标归零 |
| 甲「保存为模板」→ 乙订阅 → 模板发新版 | 乙的有效定义变为模板层；发版后乙按分类处理（未改过自动跟随） |
| push 域：本项目改写 1 条公式来源规则 / 停用 1 条可编辑规则 | 规则表层级为「本项目」；重新推送后运行记录触发来源为「公式规则变更」；停用的规则不再写入 |
| 停用一条系统值规则 | 被拒，提示独占键原因 |
| 校对规则目录 | 各来源计数与规则文件现算一致 |

清理：按写入表逐项对账（`formula_setting` / `formula_sync_item` / `formula_publish` / `formula_template*` / 审计日志 / 推送运行与状态），全局层改动复原；保留项写进 tasks 交付记录。

### 8.1 勘误（实施与上表的差异，2026-10-22）

- 第 1 步改用报表公式：tb_detail（与 push）全局层适用范围是「*」，全局发布会触达全部真实项目（即使选暂缓，也会给每个项目固定旧定义并生成待确认）；报表公式按适用范围分层，上市单体只有甲 / 乙。
- 甲、乙有审计年度（`projects.audit_year = 2025`，只是没填审计期间），推送链路不用另建项目；底稿 E1 经平台「按编码生成」现建 —— 该端点恒 500，见 §8.2 ①。平台没有删除底稿的入口，E1 保留在甲上作回归数据。
- 「停用的规则不再写入」：甲没有附注，停用的 `E1.note.main_rows` 原本每次都「跳过：附注尚未生成」；可观察的证据是停用后的运行明细里不再有这条规则（29 → 28 条），写入值的变化在甲上无法观察。

### 8.2 走查发现并修复

| # | 现象（真库 / 浏览器） | 根因 | 修法 |
|---|---|---|---|
| ① | 「按编码生成底稿」对任何调用 500（前端「生成底稿」在模板集生成 5xx 时回退到它，回退同样失败） | 函数体 import 全仓从未实现的 `populate_parsed_data`（懒导入守卫的待修基线里冻结着）；唯一的 property 测试在内存里模拟端点、从未真发请求 | 与准则转换生成路径共用 `wp_parsed_data_service.ensure_parsed_data_placeholder`（为空才写最小占位）；验证脚本同改；守卫基线删该条；端点守卫真发请求 |
| ② | 底稿公式取不到数（REPORT 期初 / PREV 无上年 / 附注无章节）网格写成 0，回执带 `evaluated_value: "0"`；公式管理中心只提示「公式已保存」，自定义底稿编辑器只报「告警 N 条」 | 保存端点对网格单元格「逐字节零回归」：有错照写求值器的 0 占位（D-cycle 锚点早已不回值） | 求值有错 ⇒ 格子留空（清掉旧值）、只回 `eval_warnings`；三个调用方经 `wpFormulaSaveNotice` 写明单元格与原因（R6.3） |
| ③ | 公式管理中心同一行第二次保存 409「已被他人修改」；自定义底稿编辑器改已有公式 428 | 版本号在回执的 `saved` 下，公式管理中心读顶层（恒取不到，行上版本不更新）；编辑器根本不带 `expected_version` | `savedDefinitionVersion` 取回执里的新版本；编辑器从公式清单带版本号；守卫：每处保存的请求体都带 `expected_version`、不从回执顶层读版本 |
| ④ | 待确认选「保留本项目」后提示「相关报表 / 附注会按新定义重算」 | 前端提示写死；后端只在有效定义真的变了才发重算事件，但事件不回给前端 | 接口回 `recalc_domains`；全保留 ⇒「本项目有效公式未变，无需重算」 |
| ⑤ | 模板发布预览「版本」列整列「— → —」 | 模板变更行没有逐公式位版本（模板版本在标题里） | 无逐位版本时不显示该列 |
| ⑥ | 公式管理中心刚打开就点「订阅模板」，几秒内显示「没有可订阅的模板（看不到的模板说明未共享给你）」 | 先等域清单回来才开始加载模板清单，期间列表空、也不在加载态 | 并行加载（加载态随之同步进入） |
| ⑦ | 树上点「E1 货币资金」只高亮不切换；推送页提示「本底稿尚未接入自动推送 · 已接入：…E1…」 | 树点击只认叶子；推送页空状态不区分「没选底稿」 | 底稿工作簿节点（带底稿编码、无页编码）可选中整本；空状态先引导去选底稿 |
| ⑧ | 推送面板「最近一次推送」、运行历史、表间审核历史显示 `2026-10-22T15:19:56.808508+00:00` | 直接插值后端 ISO 串 | `fmtDateTime` |
| ⑨ | 无附注项目每次打开公式管理中心 / 编辑公式弹窗都弹「附注数据不存在，请先生成附注」，且没加载模板目录 | `getDisclosureNoteTree` 只收两个参数（AI 采纳目标传的 `{ _silent: true }` 也被丢弃，HEAD 上 vue-tsc TS2554）；404 落进外层 catch，跳过了模板目录降级 | 透传请求配置；404 静默改用模板目录，其他错误提示「暂按模板目录显示」 |

## 9. 范围外发现（登记，不在本 spec 修）

- **R5 走查发现（未修，登记）**：①`/working-papers/generate` 的请求模型没有 `selected_templates`，前端裁剪弹窗确认的编码被丢弃 ⇒ 按模板集整套生成；②`generate-from-codes` 按 `gt_template_library.json` 的 `code` 精确匹配，E1 这类多页底稿在库里是「E1-1至E1-11」⇒ 生成空白工作簿、名称「底稿E1」（其余入口有按编码解析多页册的逻辑，未复用）；③平台没有删除底稿的入口（回收站支持底稿类型，但没有任何端点把底稿置删除）；④两个生成端点只校验登录（已在鉴权基线「仅登录」里）；⑤自定义底稿编辑器保存写死 `template_type: 'soe'`，上市项目按国企口径校验引用；⑥d-cycle Tier A 三个测试文件 28 例恒红（假会话缺 `get`、`list_formulas` 形参改名，HEAD 同）—— 它们是保存端点锚点 / 网格分流的主要守卫，处于失效状态；⑦`backend/pytest.ini` 加 `pythonpath = tests`（cad40da77）后，`tests/playwright/` 包遮蔽真实 playwright，不带 `-p no:playwright` 的 pytest 一启动就崩；⑧`ChatAdoptNoteTarget.spec.ts` 8 例 HEAD 同红（请求体与后端模型不同步）。
- **最终回归（8.1）的预存失败（未修，登记）**：后端 137 例全部在本 spec 开工点 d28f1de8a 同红 —— d-cycle 提取 85 例（`list_formulas` 不收 `_user` 37、假会话缺 `get` 21，其余 27 是 detail_prefill / 渲染基线键 / D6 汇总字段等契约过时）；推送 26 例（批次 E 附注 15：「H / I 不应有 note.main 规则」「L6 / N3 应在 sync_registry 中」；批次 C 附注 3：0 ≠ 800000；覆盖率 3：清册与注册表不一致；D4 canary、行包含匹配、安徽真库跳过 311 超棘轮 85、E1 独占键新增 `e1_builder.py`、K2 真库 canary 测试间污染各 1）；`test_note_edit_stamp_writers` 6（夹具缺 `project_assignments` 表）；`test_wp_generation_pipeline_property` 6 —— 5 例 import 全仓不存在的 `wp_parsed_data_service._read_xlsx_structure`，与 §8.2 ① 的 `populate_parsed_data` 同源（wp-generation-pipeline 设想的「按模板读 sheet 结构填 `html_data`」从未实现，`ensure_parsed_data_placeholder` 只写空占位），1 例 componentType 期望已过时（如期望 `e-control-test` 实为 `e1-monetary-fund`）；`test_formula_runtime_zero_regression` 4（`_FORMULA_RESOLVERS` 已删、注册表新增函数）；附注公式端点鉴权「不变」守卫 3（附注编辑门禁改造后鉴权写法变了，守卫仍按旧写法抽）；`test_adj_formula_function` 2；懒导入 2（他会话的缺失模块）；预设语法 / ACNR 漂移 2（`migrated` ≠ `pending`）；`test_user_formulas_override` 1。前端 9 个文件 20 例同在 d28f1de8a 红（AI 采纳请求体对账 8、销售标签 2、账龄 3、AI 能力 2、C24 1、C 控制测试 1、formulaPaths 2、views composables 1）。
- **R6 发现（未修，登记）**：①预填充模板预设里 PREV 三参（上年底稿取数）184 条，统一预载层只按试算表取 ⇒ 恒 0（需上年底稿取数源，另评估）；②L1 `_handle_prev` 不看列名（恒取上年期末）、`_handle_report` 不看期间（报表 / 预填充路径；底稿求值器已绕开）；③地址库附注域只登记合计行（逐行登记约 6~9 千条 / 项目，选择器体量待评估）⇒ 底稿公式保存的 NOTE 只能引用合计行，求值器本身支持任意行；④预填充仍是非严格（缺数按 0），未接 `gaps`；⑤前端地址库 store 一次取 5000 条、后端按 report → tb → note → wp → aux 顺序截断 ⇒ 真实项目（安徽：报表 2810 + 试算表 2744 已超 5000）附注 / 底稿 / 辅助余额域在前端恒为空，各选择器只能回退旧端点（公式栏的回退已修；FormulaRefPicker / CellSelector 等其余选择器待查）。
- 🔴 **签字前一致性门禁「取不到数冒充通过」**：`services/consistency_gate/_impl.py` 现算 82 处 `passed=True`，其中「数据不完整，跳过检查」41 处、「检查异常」40 处 ⇒ 数据缺失或代码异常时门禁放行。修它会让签字门禁在数据不全时开始阻断，属产品决策，需用户拍板后另立 spec。
- L1 `_handle_report` 忽略期间参数（`REPORT('X','期初')` 与本期同值）；本 spec 只在底稿求值器前置代入规避，内核修正与报表 / 表间审核路径的影响面另评估。
- `prefill_engine` 内仍有旧 resolver 兼容残留（spec 60 Task 11 有意保留），不动。
- 🔴 **5 条推送系统规则的科目与 binding 取数科目不一致 ⇒ 审定表「试算表金额」恒推 0**（R2 新校验现算，2026-10-22 真库核对）：

  | 规则 | 规则公式 | binding 取数科目 | 试算表实情 |
  |---|---|---|---|
  | `H6.1_tb_amount` 固定资产清理 | `TB('1606',…)` | `1606B`（映射码） | 有 1606；两个项目 5,383.76 / 33,886.68，推送状态记 0 |
  | `I1.1_tb_impair` 无形资产减值准备 | `TB('1703',…)` | `1701 / 1702 / 1703B` | 有 1703 |
  | `H9.1_tb_amount` 租赁负债 | `TB('2205',…)` | `2802` | 2205 是合同负债；无 2802 |
  | `I2.1_tb_amount` 开发支出 | `TB('1717',…)` | `1704` | 无 1717，有 1704 |
  | `I5.1_tb_amount` | `TB('1911',…)` | `1901` | 无 1911，1901 是待处理财产损溢 |

  修法要先定「binding 科目以映射码还是试算表标准码为准」（H6 binding 只有 `1606B`，整张底稿的推送都取不到数；I1 缺减值准备），且这几个底稿的推送规则正被另一会话改动，不在本 spec 修；守卫冻结、只许减少。

## 10. 决策记录

- ADR-FGC-001 推送规则清单不迁表：JSON 作系统预设层，用户改动走 `formula_setting`（与底稿域用预填映射作预设层同一模式）。
- ADR-FGC-002 推送规则只开放「改写公式 + 启用 / 停用」；系统值 / 派生值规则不许停用（独占键）。
- ADR-FGC-003 运行时改写失效 ⇒ 跳过并报原因，不回退预设（宁缺毋错）。
- ADR-FGC-004 校对规则目录只读、不收编执行器：先让用户看得见全部规则，执行器收敛另议。
- ADR-FGC-005 零挂载组件按「有数据源且不重复才接」裁决；无数据源的删除并登记。
- ADR-FGC-006 导入公式不再写仓库文件：与自定义预设同一数据库存储与候选审核。

## 11. 测试

- 后端：端点级鉴权（7 个端点 × 非成员 / 成员 / 管理员）；守卫第三维与双向变异；push 域内核（预设、校验四类拒绝、有效规则叠加、失效跳过）；引擎读有效规则（改写公式生效、停用不推、失效进提示）；传播 handler（合并 / 无年度跳过、触发来源）；表间审核严格取数（含另一侧为 0 的反例）；预载层 AUX / 报表行；求值器 7 个函数与缺口报错；矩阵 golden；校对目录登记守卫；组件挂载守卫。
- 前端：`formulaPushView.ruleActions`、`definitionText` 停用、推送面板操作接线、校对目录组件、问题清单 / 提醒数据接线、导入导出下拉（PUT + 角色门控）、行名对齐标签复用。
- 回归：`tests/formula_settings/` 全套、`formula_push` 相关、`test_project_endpoint_authorization_baseline.py`、函数矩阵前后端对拍、前端 formula 目录全套。
- 浏览器：§8 走查。
