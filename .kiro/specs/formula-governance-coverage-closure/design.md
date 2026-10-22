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
| F12 | 5 个组件从未被任何提交挂载（`git log -S "<Name"` 为空）：`GtFormulaHintPanel` 262 / `GtFormulaIssuePanel` 247 / `GtRowNameAlignmentTag` 145 / `FormulaImportExportDropdown` 110 / `GtDraftStateBadge` 90 | `components/formula/` |
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

## 6. R4 零挂载组件处置

| 组件 | 判定 | 处置 |
|---|---|---|
| `GtFormulaIssuePanel` + `GtFormulaHintPanel`（+ `useFormulaIssueHint`） | 有独立价值：现有面板只画 ✅/❌（F14），问题明细与合理性提醒无处可看 | 接进 `FormulaCrossCheckPanel`；数据取自 `useCrossCheckRules.loadExecItems` **同一次**响应（新增 `issues / hints / lastComputedAt`），不再额外执行一次审核（该接口每调一次就落一次运行记录） |
| `FormulaImportExportDropdown` | 有独立价值：导入导出后端在、前端无入口 | 接进 `FormulaSettingsToolbar`；修 F13（`POST` → `PUT`、请求体按 `OverridesBody`）；「导入数据」按角色门控 |
| `GtRowNameAlignmentTag` | 与 `GtRowNameAlignmentDialog` 内联的状态标签重复（同一组 match_state 文案 / 颜色两份） | 弹窗行内改用该组件，删掉弹窗里的重复映射 |
| `GtDraftStateBadge` | 无数据源：初稿标记无读接口，真库 16 行全是测试产物（F15） | 删除；「初稿状态展示」需新增标记查询接口与报表 / 底稿行级接入，另立 spec |

守卫：`components/formula/**/*.vue` 每个组件至少被一处生产代码引用（排除测试、`components.d.ts`、stories），PascalCase 与 kebab-case 两种写法都认。

## 7. R6 底稿可编辑公式补齐函数

现状：求值器先把 WP / SUM_TB / TB 代成数值，再以空上下文跑 L1；矩阵把其余函数判不支持，保存即 422（fail-closed，F10）。改为：

1. **统一预载层补数据源**（`formula_preloader.py`）：
   - `_load_aux(specs)`：按（科目, 维度）汇总 `tb_aux_balance.closing_balance`，过滤条件 `get_active_filter(db, TbAuxBalance.__table__, pid, year)`；填 `ctx.aux_data[科目][维度]`（现恒 `{}`）。
   - `_load_report_rows(codes)`：调用方未给 `row_cache` 且公式含 ROW / SUM_ROW / REPORT 时，从 `financial_report` 取本期 `current_period_amount` 与上期 `prior_period_amount`（项目 + 年度、未删除）。
   - 返回取数缺口 `ctx.missing`（新增可选字段，供调用方报错）：上年试算表整体无行、辅助核算无该（科目, 维度）、报表行未生成、附注无该项。
2. **求值器**（`wp_formula_eval_service.evaluate_wp_formula_expression`）：保留现有 WP / 跨 sheet / TB 代入；新增 `REPORT('行次','期间')` 代入（期间为期初 / 上期 / 年初取上期金额，其余取本期 —— L1 的 `REPORT` 忽略期间参数，代入前置可避开）；其余（ROW / SUM_ROW / NOTE / PREV / AUX / ADJ）由 `preload(..., adj_exclude_origins=frozenset())` 建上下文后交 L1；`ctx.missing` 逐条写进 `errors`（R6.3）。
3. **矩阵**：`wp_evaluator` 维度 ROW / SUM_ROW / REPORT / NOTE / PREV / AUX / ADJ 改为支持，删除对应不支持原因；重算 golden `tests/fixtures/function_support_matrix.json`；前端 `functionSupportMatrix.ts` 同步（两侧对拍测试保持绿）。
4. 预载层 `_load_tb` 的 `is_deleted` 裸写保留：`trial_balance` 不是四表（不受数据集版本治理），与报表取数同口径；只有 `tb_aux_balance` 走 `get_active_filter`。

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

## 9. 范围外发现（登记，不在本 spec 修）

- 🔴 **签字前一致性门禁「取不到数冒充通过」**：`services/consistency_gate/_impl.py` 现算 82 处 `passed=True`，其中「数据不完整，跳过检查」41 处、「检查异常」40 处 ⇒ 数据缺失或代码异常时门禁放行。修它会让签字门禁在数据不全时开始阻断，属产品决策，需用户拍板后另立 spec。
- L1 `_handle_report` 忽略期间参数（`REPORT('X','期初')` 与本期同值）；本 spec 只在底稿求值器前置代入规避，内核修正与报表 / 表间审核路径的影响面另评估。
- `prefill_engine` 内仍有旧 resolver 兼容残留（spec 60 Task 11 有意保留），不动。

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
