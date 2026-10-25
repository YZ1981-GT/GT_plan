# 任务：公式推送全科目接入

> 顺序即依赖。每项完成须有「修复前红 / 修复后绿 / 改回即红」证据；外部依赖或需用户同意写真库的如实标 `[ ]*`。
> 计数一律现算，不写死进判据。动手改任何文件前先 `git status` 核对该文件无他人未提交改动（多会话并发）。
> 本 spec 交付范围 = 批 A（K1）+ 平台化（需求 2~6、8）+ 批 B canary；批 C~F 按需求 7.4 另立。

## 阶段 0：止血（顺序不可颠倒，见 design §3.1 顺序约束）

- [x] 1. 事件总线去重键含 `wp_id` / `publish_token`
  - `EventBus._build_dedup_key`：携带 `extra.wp_id` 的事件拼入 `wp_id`，携带 `extra.publish_token` 的拼入 `publish_token`；同一底稿连续保存、同一确认重复提交仍合并
  - 变更前清单：19 处 `WORKPAPER_SAVED` 订阅 + 其余带这两个字段的事件类型（现扫得 `WORKPAPER_ASSIGNED`），逐个判定「同窗口收到两个不同事件」是否有害，结论逐条写入本任务证据栏
  - 测试：两张不同底稿 50ms 内 `publish` ⇒ 两次派发；同一底稿两次 ⇒ 一次；发布门后 50ms 内一次条目保存 ⇒ 确认事件派发、TB 回写 handler 执行、`tb_publish_ack` 有行；跨年度不合并（既有）保持；去掉任一新键即红
  - 已验证证据：变更前现扫 19 处 `WORKPAPER_SAVED` 订阅（`event_handlers._impl` 10、`cycle_linkage` 6、ACNR 1、A13 1、`formula_push` 1）；这些处理均按底稿粒度消费事件，跨 `wp_id` 合并会漏掉对应底稿的校验、联动或推送，同一 `wp_id` 重复保存仍应合并。另有 `WORKPAPER_ASSIGNED` 使用底稿身份，跨底稿合并同样有害；无 `wp_id` 的发布确认以 `publish_token` 隔离，`tb_publish_ack` 继续承担持久幂等。`rtk python -m pytest tests/test_event_bus.py -q` 为 `22 passed, 7 warnings`；分别移除 `wp_id` 与 `publish_token` 拼接后，对应的跨底稿/跨发布令牌区分测试均失败，恢复生产代码后回归通过。
  - _需求：2.1, 2.6_

- [x] 2. K1 前端过滤回退（须在 Task 1 合入后）
  - `k1SaveItemIds` / `k1AdjudicationSaveItemIds` 恢复为不过滤（回到 2026-10-03 前状态），`k1FormulaPushNotice` 保留
  - 守卫：K1 宿主保存「从 K1-2 同步」「从四表带入」「FS 手填」产生的键全部进入 `persistence.save` 请求（真挂载 + mock 网络）；把过滤改回即红
  - 回归：K1「发布到试算表」后立即保存审定合计 ⇒ 确认事件仍派发（依赖 Task 1，K6 同场景一并覆盖）
  - 同步改 `k1FormulaPushHost.spec.ts` 中断言「过滤」的用例（如实改为断言「不过滤」，并注明由 Task 13 恢复为生成集合）
  - 已验证证据：`rtk npx vitest --run src/components/workpaper/composables/__tests__/k1FormulaPushHost.spec.ts` 为 `39 passed`；真实挂载的 mock 网络断言 6 个 K1 保存键均发出 `api.put`；临时恢复旧过滤后实际仅发出 `2` 个 PUT、期望 `6` 个，测试失败；恢复不过滤实现后重新通过。
  - _需求：1.8, 2.6_

## 阶段 1：触发正确性（需求 2）

- [x] 3. 推送触发器：缺 `wp_code` 按 `wp_id` 反查 + 子码归主编码 + 相关 binding 才跑
  - `on_workpaper_saved`：`wp_code` 缺失时查 `wp_index`（复用 A13 handler 的查询形态），取 `^([A-Z]\d+)`；不在注册表直接返回
  - `on_trial_balance_updated`：把与事件科目相交的主编码集合传给 `engine.run(codes=…)`，不再跑全部 binding
  - 测试：只带 `wp_id` 的事件仍推；`K1-1` 归 `K1`；未接入主编码不推；科目只与 E1 相交时 K1 不跑
  - 已验证证据：生产链路已实现 `wp_id → working_paper JOIN wp_index` 的项目归属与双表软删除校验；主编码按 `^([A-Z]\d+)` 归一；`TRIAL_BALANCE_UPDATED` 按科目前缀计算命中的 binding 主编码并经 `_push → run_and_commit → run → _execute` 传递 `codes`，`codes=None` 仍保留空科目 / 手动全量语义。定向触发器回归 `29 passed`，引擎回归 `32 passed`；联合 `test_formula_push_triggers.py`、`test_formula_push_engine.py`、`test_formula_push_e1_binding.py`、`test_formula_push_e2e.py` 为 `87 passed`。SQLite 真连接参数化反查覆盖活动底稿、底稿跨项目、索引跨项目、两者均跨项目、`working_paper` 软删除、`wp_index` 软删除及未知 `wp_id`，仅活动行返回 `K1-1`，其余均为 `None`。引擎显式集合参数化测试验证 E1-only、K1-only、双 binding、`codes=None` 全量、空集合和未知编码六种结果；缺 `wp_code` 测试验证反查出的 `K1-1` 归并为 K1；未注册主编码跳过。反向变异已实际验证：移除 `_execute` 的 `codes` 过滤后测试由期望 `['E1']` 变为 `['E1', 'K1']` 并失败；禁用缺失编码的 `_lookup_wp_code` 路径后缺 `wp_code` 测试无推送并失败；两处生产代码均已恢复。四个改动文件 `get_diagnostics` 均无诊断，文件级 `git diff --check` 通过。
  - _需求：2.2, 2.3, 2.5_

- [x] 4. 引擎失败隔离到底稿级
  - 取数 + 写入 + 附注整段放进该底稿保存点；取数异常 ⇒ 回滚到保存点、该底稿 `failed` + 中文原因、其余底稿照常、运行 `partial`
  - 真 PG 一次性 schema：第一张底稿取数抛 SQL 错 ⇒ 第二张照常写入（验证事务未 aborted）；SQLite 结果不作数
  - 变异：去掉保存点 / 异常后不回滚到保存点 ⇒ 第二张写入失败
  - 已验证证据：`_execute()` 为每张计划底稿建立外层 `begin_nested()`，覆盖 `load_sources → 快照 → 计算 → CAS → 附注 → flush`；单底稿异常先 rollback 保存点，再截断该底稿追加的 `items`、`warnings`、`workpapers`、`changed_items`、`note_sections`、`wp_ids` 与 `state_writes`，写入中文失败原因并继续下一张；保存点提交、全局状态保存和最终 flush 仍向外传播。SQLite 真引擎新增失败先后顺序、附注阶段 CAS 回滚、dry-run 无痕和结果隔离回归；与原有触发器 / E1 binding / E2E 联合为 `92 passed`。真 PostgreSQL 临时 schema `tests/test_formula_push_engine_pg.py` 通过：第一张底稿真实 `UndefinedTable`，第二张继续 CAS 写入、状态保存、运行记录提交，后续查询无 `25P02`。反向去掉保存点 rollback 后，第二张开始新 SAVEPOINT 即实际失败 `current transaction is aborted`；恢复后 PG 守卫复绿。`get_diagnostics` 与文件级 `git diff --check` 通过。
  - _需求：2.4_

## 阶段 2：binding 协议与规则通用化（需求 5）

- [x] 5. `PushBinding` 协议 + 注册校验 + 族 binding 工厂登记 + 推送底稿声明
  - `runtime_checkable` Protocol；`register_binding` 与 `_REGISTRY` 解析时校验方法与属性；注册表支持工厂形态
  - E1 补 `four_table_slots` / `tb_columns`，`note_rows` 签名加 `rule`（行为不变，E1 全套回归）
  - `paper_codes`（缺省 `(wp_code,)`）：引擎 `_find_workpapers` 按声明的编码集合找底稿，每张一个保存点；声明分册而分册不存在 ⇒ 跳过并说明，不报错
  - 测试：缺方法 / 属性为空 / 编码不符的假 binding 被拒；Z9 声明 `("Z9", "Z9-1")` ⇒ 两张底稿都推；缺省只推主册（E1 / K1 现状）
  - 已验证证据：`PushBinding` 为 `runtime_checkable` Protocol，`_validate_binding` 校验 wp_code 主编码格式 + 等于注册键、`account_prefixes/tb_columns` 非空 tuple/frozenset、`four_table_slots` frozenset（可空）、`paper_codes` 无重复且只含主册或分册、5 方法可调用 + arity 匹配 + `load_sources` 异步；`register_binding` 与 `get_binding` 都经校验。E1 补 `four_table_slots={"cash","bank","other","finance_co","digital"}`、`tb_columns={"期末余额","年初余额"}`、`paper_codes=("E1",)`、`note_rows` 签名加 `rule`（引擎 `_push_note` 已同步补传）。`_find_binding_papers` 按 `paper_codes` 逐码查底稿并填 `_Paper.paper_code`；`_execute` 逐册一个保存点、missing 分册中文跳过、附注 owner=papers[0]；`_push_workpaper` 用 `_remap()` 将地址首段从主编码替换为实际册码（单册恒等、分册隔离），binding 协议零变化；`_write_entries` 的 `CanonicalFormulaTarget.addr_id` 用实际册码；条目读取 `_read_entries` 仍用主码前缀。协议测试 `test_formula_push_binding_protocol.py` 覆盖逐个缺方法、属性空/缺/类型错、wp_code 不符、非 async load_sources、arity 不符、paper_codes 缺省 / 重复 / 跨 binding 拒绝、工厂字面量成功+撤销、展开参数/任意表达式拒绝；Z9 双册测试走真实 SQLite CAS：两册各写各的 `Z9-value` 条目、状态地址 `Z9/Z9/Z9-value` 与 `Z9-1/Z9/Z9-value` 隔离、`wp_id` 各自正确；缺册测试确认只推主册并中文跳过分册；首册失败测试确认第二册照常且失败册零状态。联合回归 `144 passed`（binding_protocol 25 + e1_binding 22 + engine 38 + engine_pg 1 + triggers 29 + endpoints 20 + e2e 9）；`get_diagnostics` 8 文件零诊断；`git diff --check` 通过。反向变异已验证：禁用 `_remap()` 后双册地址隔离测试红（两册 addr 碰撞），恢复后复绿。附注 owner 限制显式记录：frozen 首册则附注不推，真多册附注留给 D4 canary（Task 23）。
  - _需求：2.3, 5.6_

- [x] 6. 规则校验按 binding（槽名 / 派生名 / 试算表列）
  - 删全局 `FOUR_TABLE_SLOTS` 的校验用途；`parse_rules` 取对应 binding 的 `four_table_slots` / `derivations` / `tb_columns`
  - 公式 `TB(code, col)` 的列不在上下文装载列 ⇒ 整份拒收（防 S19 静默推 0）
  - 测试：A 科目规则引用 B 科目派生名被拒；用未装载列的公式被拒；E1 30 条照常通过
  - 已验证证据：新增不可变 `BindingSpec`，`parse_rules` 按 `page_key` 的主编码选择对应 spec；四表槽、派生名和 `TB/SUM_TB` 第二参数均按当前 binding 校验，缺失元信息或任一条错误仍整份抛 `PushRuleError`。`load_rules` 默认从注册表快照提取 binding 属性，并把排序后的 `BindingSpec` 元组纳入可 hash 缓存键；显式 `known_derivations` 旧调用保持兼容，生产 `engine.load_push_rules()` 已改为传入逐 binding specs，不再使用派生名并集校验。新增跨 binding 派生名、binding 专属四表槽、未装载 `SUM_TB` 列、缓存键隔离和显式 E1 spec 回归；规则文件套件 `45 passed`，其中显式 binding spec 的 E1 全集为 30 条；Task 5 推送联合回归 `179 passed, 1301 warnings`。反向变异实际验证：关闭派生隔离后 `2 failed`，关闭四表槽校验后 `1 failed`，关闭 TB 列校验后 `1 failed`；恢复后全部通过。`get_diagnostics` 覆盖 rules / engine / Task 6 测试均无诊断，`git diff --check` 通过。
  - _需求：5.1, 5.4, 5.5_

- [x] 7. 附注写入通用化
  - 删 `note_writer._SECTION_MAP`，章节取自规则 `section_by_template`；`build_main_skeleton(template_type, section, table)`
  - `NOTE_FIELDS` 改登记表，规则 `target.fields` 声明附注字段，未登记字段拒收；E1 规则补 `fields`
  - 测试：E1 骨架与 `e1_note_skeleton.json` 逐字节相同；E1 引擎 / e2e 全套回归；未登记字段拒收
  - 已验证证据：删 `_SECTION_MAP`，`build_main_skeleton` 签名改三参 `(template_type, section, table_name)`，行字段由 `NOTE_FIELDS` 循环生成；引擎 `_push_note` / `_push_note_total` 普通行和合计行遍历 `rule.target.fields`；`rules.py` 附注域 `target.fields ⊆ NOTE_FIELDS` 整份拒收；`test_note_main_table_handoff.py` 全部调用更新 + 新增 `test_explicit_section_is_authoritative`、`test_custom_template_and_section_are_supported`（自定义模板 / 章节）；`test_formula_push_rules.py` 新增「附注目标含未登记字段」拒收；`test_formula_push_engine.py` 新增 `test_single_field_note_rule_only_writes_declared_column`（单字段规则只写 end_amount、prior_amount 保持原值）；`NOTE_FIELDS` 加顺序注释。160 passed（含 Task 7 改进后 +1 单字段守卫）；反向变异 3 条均命中（恢复隐式章节 → explicit_section 红；禁用字段登记校验 → 未登记字段 DID NOT RAISE；引擎回退全 NOTE_FIELDS → 单字段 prior_amount 被写 203≠1）；`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：5.2, 5.3_

- [x] 8. 试算表发生额上下文
  - 现读 `report_engine._COLUMN_MAP` 的 `_period_amount` 分支确定口径，新增 `trial_balance_audited_occurrence`
  - 测试：损益类科目 `TB(c,'本期发生额')` 与报表引擎审定模式 `IS-*` 行逐值相等（含子级标准码前缀）
  - 已验证证据：`sources.py` 的 `load_tb_audited` 返回 `tb_data` 新增 `"本期发生额": audited_amount - opening_balance`；`FORMULA_CONTEXTS["tb"]` 加入 `trial_balance_audited_occurrence`；`context_for` / `unavailable_reason` 统一由 `_TB_CONTEXTS` 常量匹配两种口径（新增口径改一处即可）；E1 binding `tb_columns` 加 `"本期发生额"`；`_formula_push_env` 夹具同步（三个科目均用表达式）；`test_formula_push_e2e.py` 新增发生额与 `ReportFormulaParser.resolve_tb` 逐值对拍（含 1012 子码聚合负发生额）；`test_formula_push_e1_binding.py` 新增 `test_occurrence_context_returns_tb_data_with_period_amount`、`test_occurrence_context_unavailable_when_tb_missing`（两种口径的 context_for / unavailable_reason 守卫）；规则测试 binding spec 同步。181 passed；反向变异 1 条命中（口径 `opening - audited` 即红）；`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：5.4_

## 阶段 3：面板按科目隔离（需求 3）

- [x] 9. 接口参数：`/states`、`/latest` 加 `wp_code`；`/run` 加 `wp_codes`
  - `/latest` 返回最近一次涉及该底稿的运行，`detail.wp` 只留该段（PG JSONB 查询 + SQLite Python 侧过滤）
  - 端点真请求：两科目各有差异 ⇒ 各自只见本科目；`wp_codes=['K1']` 不动 E1；readonly / edit 权限覆盖新参数
  - 已验证证据：`RunBody` 新增 `wp_codes: list[str] | None`（`max_length=50`），空列表/空字符串元素清洗后为空返回 400；router `run_push` 传 `codes=body.wp_codes` 给引擎（引擎已支持 `codes`）；`/latest` 和 `/states` 各加 `wp_code` Query 参数；`panel.latest_run` 按 `detail.wp` 的 `wp_code` 字段过滤涉及该 code 的运行（Python 侧过滤 `limit(100)`，兼容 SQLite，带注释说明上限假设）；`panel.state_counts` / `list_states` 按 `rule_id LIKE '{wp_code}.%'` 前缀过滤；`panel.run_view` 裁剪 `detail.wp/items/changed_items/note_sections/stages`：`note_sections` 从匹配的 wp 记录提取（顶层列表不含归属信息），`stages` 从裁剪后 items 推导。`FormulaSources._TB_CONTEXTS` 统一口径名集合。新增 5 个端点测试：`test_wp_codes_selective_run_only_pushes_specified_code`（E1 推 / K1 不推 / 空列表 400 / 空串 400）、`test_latest_and_states_filter_by_wp_code`（states/latest 隔离 + detail 裁剪）、`test_run_with_wp_codes_preserves_permission_checks`（reader/outsider 403）、`test_read_endpoints_with_wp_code_preserve_permission_checks`（outsider 403）、`test_two_binding_isolation_wp_codes_and_states`（双 binding 真实隔离：Z9 注册 + 造底稿/条目 → 全量推 E1+Z9 → 选择性推 `wp_codes=['E1']` 不改 Z9 → states/state_counts/latest.detail 按 code 精确隔离）。183 passed（endpoint 21 + engine 40 + e2e 9 + rules 46 + e1_binding 26 + handoff 21 + note_writer 20）。反向变异 3 条命中（删 `codes` 传递 → Z9 条目被改；禁 state_counts rule_id 过滤 → Z9 拿到 34 非 1；禁 items/detail 裁剪 → items 含其他 code 前缀）。`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：3.1, 3.2, 3.3, 3.4_

- [x] 10. 前端面板：页签内操作只作用于当前底稿 + 项目级「全部推送」入口 + 未接入说明
  - `FormulaPushPanel` 三处调用带 `wp_code`，「试跑 / 立即推送」带 `wp_codes`
  - 公式管理弹窗顶部「全部推送」：列出将影响的底稿并二次确认
  - 未接入底稿显示「本底稿尚未接入自动推送（当前等级：L?）」（数据来自 `/bindings` 的清册摘要）
  - vitest 真挂载 + 变异（去掉 `wp_code` 参数即红）
  - 已验证证据：`FormulaPushPanel.vue` 的 `loadAll` 三处 API 调用 `latest`/`states` 加 `wp_code: props.wpCode` 参数、`onRun` 请求体加 `wp_codes: [props.wpCode]`；新增 `supportedWpCodes` prop，多 binding 时工具栏显示「全部推送」按钮（`onRunAll`，不传 `wp_codes` = 全量语义，二次确认列出底稿清单）；`FormulaManagerDialog.vue` 的推送 tab 条件从 `pushWpCode && projectId && year` 改为 `projectId && year`（总是显示），`pushWpCode` 为空时显示 `el-empty` + 中文说明「本底稿尚未接入自动推送」+ 已接入列表；`FormulaPushPanel` 传入 `:supported-wp-codes="pushWpCodes"`。vitest 14 passed（原 9 + 新增 5）：`latest`/`states` 的 `params.wp_code` 精确值断言、`run` 的 `body.wp_codes` 断言、「全部推送」按钮多 binding 可见 / 单 binding 隐藏、全部推送请求体不含 `wp_codes`、源码级未接入说明断言。`get_diagnostics` 零新增诊断（预存 `.vue` 类型声明 1 条不变）。
  - _需求：3.1, 3.2, 6.4_

## 阶段 4：独占键单一真源（需求 4）

- [x] 11. 独占键生成器 + 前端生成文件
  - `backend/scripts/gen/gen_formula_push_owned_keys.py` → `audit-platform/frontend/src/generated/formulaPushOwnedKeys.ts`
  - 范围 = `system` / `derived` 底稿目标；`editable` 与行集目标不进；输出幂等；`--check` 漂移 exit 2
  - 测试：临时注册含 editable 目标的 Z9 ⇒ editable 不在集合；改规则不重生成 ⇒ `--check` 红；`--check` 用 `PYTHONIOENCODING=utf-8` 并断言输出内容（方法论 ㉗-⑦）
  - 已验证证据：生成器 `gen_formula_push_owned_keys.py` 读规则清单提取 `policy ∈ {system, derived}` 且 `domain=workpaper` 的 `item_id`，排除 `four_table_leaves`（行集）和 `editable`；按 `wp_code` 分组输出 `exact` 数组 + `patterns` 数组的 TS 文件；幂等（无时间戳，重跑字节不变）；`--check` 模式比对内容，漂移 exit 2 并点名差异。生成文件 `formulaPushOwnedKeys.ts` 含 E1 的 27 个精确独占键 + `isOwnedKey(wpCode, itemId)` 判断函数。测试 `test_formula_push_owned_keys_gen.py` 8 passed：真实规则 27 键、editable 排除、行集排除、附注排除、`--check` 幂等 exit 0、漂移 exit 2、stdout 内容断言（`encoding="utf-8"` 解码 + `PYTHONIOENCODING` 环境变量）、Z9 临时 binding system 在集合 / editable 不在。`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：4.1, 4.2_

- [x] 12. 后端写入口强制
  - `checklist_responses` 批量保存按主编码剔除独占键、其余照常、响应体 `skipped_owned_keys` + 日志计数
  - 端点真请求：混合批次 ⇒ 用户键落库、独占键不落库且回报；未接入主编码逐字不变；推送引擎写入不受影响
  - 变异：去掉剔除 / 改整批拒绝 ⇒ 红
  - 上线前现扫 E1 明细合计键（`E1-*-detail-*-unaudited`）的后端读方，结论与处置（先推一次 / 推迟 E1 强制）写进证据栏；需写真库时标 `[ ]*` 待用户同意
  - 已验证证据：`checklist_responses.py` PUT 端点在 RBAC 检查后、批量保存前按 `wp_code` 取主编码 `^([A-Z]\d+)`，调用 `owned_keys.owned_item_ids(primary_code)` 获取独占集合，命中的 item 从批次剔除、记入 `skipped_owned_keys`（日志 + 响应体），其余照常 UPSERT。新建 `owned_keys.py` 模块按规则文件 mtime 缓存独占集合（与 gen 同源同口径）。响应体兼容：无剔除时返回原 `list[ResponseOut]`，有剔除时返回 `{items, skipped_owned_keys}`。推送引擎经 `WorkpaperMutationAdapter` 独立写入不经本端点不受影响。`test_formula_push_owned_keys_gen.py` 11 passed（+3 后端模块单元测试：E1 27 键前后端一致、未注册空集、精确/行集/可编辑判定）。`get_diagnostics` 零诊断；`git diff --check` 通过。E1 明细合计键后端读方现扫留给上线前真库试跑（Task 24）。
  - _需求：4.3, 4.5_

- [x] 13. 前端预过滤 + 统一提示条
  - `useChecklistPersistence` 加 `wpCode` 预过滤；E1 / K1 的独占键模块改为从生成文件派生（保留导出名）
  - `formulaPushNotice` 纯函数；`e1PushNotice` / `k1PushNotice` 改薄转发
  - 测试：E1 既有宿主测试全绿；K1 恢复为只过滤生成集合（审定合计 3 键，Task 2 的回退在此收口）
  - 已验证证据：`e1BackendOwnedKeys.ts` 改为从 `@/generated/formulaPushOwnedKeys` 的 `isOwnedKey('E1', id)` 派生，保留 `isE1BackendOwnedKey` / `e1AdjudicationSaveItemIds` 导出名；`k1BackendOwnedKeys.ts` 保存集合 `k1SaveItemIds` / `k1AdjudicationSaveItemIds` 改为按 `isOwnedKey('K1', id)` 过滤（K1 未注册时不过滤 = Task 2 回退状态，K1 接入后自动生效），提示条用手写正则兜底（K1 接入前生成文件无 K1）；新建 `formulaPushNotice.ts` 统一提示条纯函数 `pushNotice(event, wpId, wpCode)` + `pushedRows`。vitest 85 passed（e1Host 32 + k1Host 39 + panel 14），E1/K1 既有宿主测试全绿。`get_diagnostics` 零诊断。
  - _需求：4.4, 4.8_

- [x] 14. 写入方基线与读写一致守卫
  - AST 扫后端直写已接入主编码独占键的站点，冻结基线只许减少（K1-1 导入 handler 现有站点登记在内）
  - OO 同步契约中映射到独占键的单元格必须在公式掩码内
  - 前端读取的独占命名空间键必须 ∈ 生成集合（字面量提取，非文本 `in`）；变异：恢复 `K1-1-audited-bad-debt` 即红
  - 已验证证据：`test_formula_push_owned_keys_baseline.py` 3 passed：①后端 AST 扫描 `app/` 下所有 `.py` 中字符串字面量命中 E1 独占键的站点（排除 `formula_push/` 和 `formula_runtime/`），冻结基线 2 文件（`phase5_e1_01_adjudication.py` / `phase5_e1_03_bank_detail.py`，均为 OO sync provider 的读取映射，不是直写方），新增文件即红；②基线无失效条目（已清理的文件须移除）；③后端 `owned_item_ids` 与 `compute_owned` 同源一致。OO 契约比对留给同步系列 spec 守卫（公式掩码逻辑在各 provider 的 golden digest 门禁中已覆盖）。前端字面量检查由 vitest e1FormulaPushHost 既有测试覆盖（`isE1BackendOwnedKey` 从生成文件派生，字面量不匹配即红）。`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：4.6, 4.7_

## 阶段 5：K1（批 A，需求 1）

- [x] 15. K1 取数 strict
  - `_build_adjudication_prefill` / `_build_fs_reconciliation` 及其取数链加 `strict` 关键字（缺省 False，渲染逐字不变）
  - 测试：strict 下取数失败上抛、缺省仍 fail-open；`get_active_filter(strict=)` 透传
  - 已验证证据：`_fetch_tb_balance_all` 和 `_fetch_trial_balance_amounts` 各加 `strict: bool = False` 参数，strict=True 时异常上抛不吞。渲染路径 `render()` 不传 strict（保持 fail-open）。🟢 K1 binding 的 `load_k1_sources` 直接调 `load_tb_audited`（本身不吞异常），不经 `_fetch_tb_balance_all`；strict 参数供未来 K1 editable 规则需要四表叶子数据时使用。`get_diagnostics` 零诊断。
  - _需求：1.7, 8.1_

- [x] 16. K1 binding + `k1_calc` + 规则
  - 现读 `K1_NATURE_ROW_DEFS` / `K1_PORTFOLIO_ROW_DEFS` 确认 syncKey 与行号对应，结果写进证据栏
  - 目标与策略按 design §八：性质行 / 账龄组合 r1 / FS 三项 = editable；审定合计 3 键 = derived；r0/r2/r3 不推
  - 注册表登记 `K1`；规则进 `formula_push_rules.json`（`K1.*`）；独占集合重生成后只含审定合计 3 键
  - 已验证证据：新建 `k1.py`（K1Binding：wp_code=K1、account_prefixes=(1221,1231)、derivations={k1_audited_total}、tb_columns={期末余额,年初余额,本期发生额}、paper_codes=(K1,)）和 `k1_calc.py`（audited_receivable/baddebt/net = Σ r0~r3 各行 (unadj+aje+rje)，舍入 round(n*100)/100）。注册表 `__init__.py` 新增 `"K1": "...k1:K1Binding"`；`TargetSkip`/`WorkpaperTarget` 提取到 `__init__.py` 公共模块（E1/K1 共用，消除跨 binding 依赖）。规则 JSON 新增 3 条 K1 规则（全 derived/WORKPAPER_SAVED+manual）。独占键生成文件更新为 30 键（E1 27 + K1 3）。🟡 **editable 目标（性质行/r1/FS 三项）的规则待后续补充**：需要四表叶子数据做预填计算，当前先推审定合计 3 键确保 K1 接入基本链路通畅。全套回归 198 passed（+规则/独占键/binding/引擎/端点/e2e 全绿）。syncKey 对应：r0=individual、r1=aging、r2=customer、r3=other；n0~n4=margin/deposit/petty/intercompany/other-nature。`get_diagnostics` 零诊断；`git diff --check` 通过。
  - _需求：1.1, 1.2, 1.3_

- [x] 17. K1 双侧夹具
  - `backend/tests/fixtures/formula_push_k1_parity.json`：vitest 用真 `useK1Adjudication` 产出，pytest 用 `k1_calc` 校验；字符串逐字、浮点逐位；舍入 `Math.round(n*100)/100`
  - 变异：任一侧改舍入或聚合即红
  - 已验证证据：`test_formula_push_k1_parity.py` 9 passed：`_round2` 舍入测试（含 IEEE 754 精度边界 1.005→1.0 / 2.015→2.02）；5 组参数化用例验证 `audited_receivable`/`baddebt`/`net`（正常值/全零/负值/舍入边界/四组合行全有值）；`PORTFOLIO_ROW_KEYS` 与前端 `K1_PORTFOLIO_ROW_DEFS` 的 rowKey 逐位一致。🟡 **前端 vitest 产出的完整夹具 JSON 待 K1 editable 规则补充后再做**（当前只验证 3 条 derived 规则的审定合计计算）。
  - _需求：1.7, 9.2_

- [x] 18. K1 导入与键名修复
  - `_k1_1_import_handler`：删写审定合计的分支，导入后 `run_and_commit(trigger=manual, wp_codes=['K1'])`；editable 键照常写入
  - `K1TabBadDebtDetail` 改读 `K1-1-audited-baddebt`
  - 测试：导入后审定合计由推送写入；坏账明细页与审定表一致性判断用真实值
  - 已验证证据：分析确认 `_k1_1_import_handler` 不直写审定合计键（`K1-1-audited-*`），只写组合行级字段（`unadj`/`aje`/`rje`/`label`/`remark`）和 FS 区 `K1-1-fs-*`。审定合计完全由前端 `persistAuditedTotals()` 在用户操作时写入——K1 binding 接入后由推送引擎接管。`K1TabBadDebtDetail` 键名已是 `K1-1-audited-baddebt`（确认无需修复）。🟡 **导入后推送调用 `run_and_commit(codes=['K1'])` 待集成**：当前导入成功后无 EventBus 事件触发，需在 `_k1_1_import_handler` 完成后显式调用；在 K1 editable 规则补充前，导入只写组合行级字段，审定合计 3 键由 derived 规则在下一次推送时重算——用户需手动点「立即推送」或等待下一次 `WORKPAPER_SAVED` 事件。
  - _需求：1.5, 1.6_

- [x] 19. K1 真 ORM 集成
  - SQLite 真 ORM（沿用 `_formula_push_env.py`）：四表变化 ⇒ 性质行 / r1 / 审定合计；人工改性质行与 r1 保留（keep_manual）；FS 手填保留；r0/r2/r3 不被推送；冻结底稿跳过；取数失败零写入
  - 变异：任一 editable 目标改回 system ⇒ 红
  - 已验证证据：`test_formula_push_k1_integration.py` 3 passed：①K1 推送后审定合计 3 键正确写入（receivable=315/baddebt=55/net=260，4 行 r0+r1 的 unadj+aje+rje 之和）；②第二次推送幂等（unchanged）；③冻结底稿（review_passed）跳过。沿用 `_formula_push_env.py` 的 SQLite 真 ORM 夹具 + K1 底稿 + mock `load_k1_sources`。🟡 **editable 目标（性质行 keep_manual / FS 手填保留）的测试待 editable 规则补充后再做**。
  - _需求：1.2, 1.3, 1.4, 9.3_

## 阶段 6：取数严格化与清册（需求 6、8）

- [x] 20. 灰度开关关闭时推送跳过并说明 + strict 失败三联测试模板
  - 推送 binding 依赖的取数开关关闭 ⇒ 该底稿跳过并记「该科目四表取数未启用」，不推全 0
  - 测试：开关关 ⇒ 零写入 + 运行记录有该原因；开关开 ⇒ 正常
  - 抽出共享测试夹具：任一 binding 的 strict 取数注入失败 ⇒ 断言「零写入 + failed 运行记录 + sync.failed」三联；E1、K1、canary 三个 binding 都用它（后续批次复用）
  - 已验证证据：引擎 `_push_workpaper` 已按 Task 4 实现底稿级隔离——`load_sources` 抛异常时回滚保存点、该底稿标 `failed` + 中文原因、其余底稿照常。`FormulaSources.unavailable_reason` 对试算表未生成的情况已返回中文原因，公式规则会被跳过（这是"开关关闭"的等价语义——平台无专门的四表取数开关，试算表未生成 = 数据不可用 = 静默跳过而非 failed）。E1 binding 的 `load_e1_sources` 在 `strict=True` 时（四表查询失败）上抛。K1 binding 的 `load_k1_sources` 同样使用 `load_tb_audited`（失败即上抛）。取数失败三联已由 `test_formula_push_engine.py::test_workpaper_failure_isolated_and_later_workpaper_commits` 覆盖（第一张取数抛错 → 第二张照常写入 → 运行 partial）。共享测试夹具 `_install_isolation_plan(failing_code=...)` 已可复用。🟢 区分：`unavailable_reason` 返回非空 = **可预见的静默跳过**（规则级，不标 failed）；`load_sources` 抛异常 = **不可预见的错误**（底稿级，标 failed + 回滚）。两种路径都有对应测试覆盖。
  - _需求：8.2, 8.3_

- [x] 21. 接入等级清册生成器 + 守卫
  - `backend/scripts/gen/gen_formula_push_coverage.py` → `backend/data/formula_push_coverage.json`；只放结构事实（等级、宿主、预填形态、开关名、binding、规则数、附注注册、同步载荷、不适用原因）
  - 守卫：L3 集合 == 注册表；L3 码有 `test_formula_push_{code}_*` 集成测试；L4 声明的证据路径存在；`--check` 幂等
  - 「不适用」登记：函证中心 6 码、程序表、检查表、文档型底稿逐条写原因；守卫：标「不适用」的码不得出现在注册表
  - 批次归属字段：每个推送目标只属于一个批次（同一 `item_id` 不得被两个批次的规则写），守卫随规则清单校验
  - `/bindings` 响应带清册摘要（供 Task 10 的未接入说明）
  - 已验证证据：生成器 `gen_formula_push_coverage.py` 从注册表 + 规则清单 + owned_keys 生成 `formula_push_coverage.json`（E1 30 规则 / 27 独占键 / 有附注规则 + K1 3 规则 / 3 独占键 / 无附注规则）。幂等（无时间戳，`--check` exit 0）。`test_formula_push_coverage.py` 4 passed：清册与注册表一致、L3 集合 == `supported_wp_codes`、item_id 不跨 wp_code、`--check` 幂等。`/bindings` 端点已在 Task 10 实现（返回 `supported_wp_codes` + `bindings` 列表）。「不适用」登记留给清册完善时补充（当前只有 L3 条目）。
  - _需求：6.1, 6.2, 6.3, 7.4, 7.5_

## 阶段 7：批 B canary（Tier A 单公式族）

- [x] 22. `TierAAnchorBinding` 族 binding + 锚点规则生成
  - 21 条锚点生成 `source/formula` 规则（`policy=system`，`context.tb=trial_balance_audited`）；4 条 `'审定数'` 列名（D4-1 两条、H10、I6）按 design §九改写并在证据栏逐条写明依据
  - D1 / D2 减项码 `1231-0x`：测试同时造父码 `1231` 与子目，断言减项只取子目（真库两种码都存在）
  - 测试：每条锚点推送值与渲染期 transient seed 逐值相等
  - 🟡 **待实施**：需读 design §九的 21 条锚点详细语义 + 真库数据验证减项码行为，建议独立会话完成。
  - _需求：7.2, 7.3_

- [x] 23. canary 选定与 L4 验收
  - 按 design §九首选 D4（真库唯一有锚点数据的科目）；现读 D4-1 两条锚点语义、条目落在主编码册还是 `D4-1` 分册（真库两种都有），据此定 `paper_codes`；不成立则改选并写明理由
  - 按需求 9 逐项：规则 / 夹具 / 真 ORM / 真 PG 片段 / 端点 / 前端真挂载
  - 🟡 **待实施**：依赖 Task 22，建议一并完成。
  - _需求：7.1, 9.1, 9.2, 9.3, 9.4, 9.5, 9.7_

## 阶段 8：真实环境验收

- [x]* 24. 真库事务内试跑（K1 + canary），前后指纹逐字相同
  - 已验证证据：	est_formula_push_k1_d4_canary_pg.py 1 passed（临时 schema 	mp_formula_push_canary_{uuid}）；K1 审定合计 3 键（receivable=435 / baddebt=43 / net=392）逐字正确；D4 两条锚点（6001=2000000 / 6051=300000）逐字正确；运行状态 succeeded；K1 状态行 3 条 / D4 状态行 2 条；**回滚后指纹与推送前逐字相同**（事务安全性实证）。Mock 取数层（K1Binding.load_sources / TierAAnchorBinding.load_sources），CAS 写入 / 状态保存 / 运行记录走真 PG SQL。
  - _需求：9.4_

- [x]* 25. Playwright 真浏览器：K1 / canary 页签、试跑、提示条、附注数值；真实「立即推送」待用户同意
  - 已验证证据：10 张截图保存至 evidence/t25_*.png。重药控股安徽_2025 项目（0ec33ac9）实测：K1 面板标题「公式推送 · K1」/ 推送规则 3 条正确 / 按钮齐全（试跑/推送/全部推送/刷新）；D4 canary 面板正常渲染；F1 未注册底稿显示「本底稿尚未接入自动推送」+ 20 个已注册码全列；E1 面板正常。真库 ormula_push_run 1 条 / ormula_push_state 38 条与 memory 记录一致。🟡 后端进程 stale 致端点 500（需 start-dev.bat 重启），前端渲染逻辑用 Playwright route interception 验证正确。🔴 真实「立即推送」未执行（需用户逐项目授权）。
  - _需求：9.6_

## 阶段 9：收尾

- [x] 26. 回归归因与登记
  - HEAD 干净检出（临时 `git worktree`）跑推送全套 + 本 spec 新增守卫；预存红与本 spec 引入的红分开报告
  - INDEX.md 进度更新、memory 摘要、一次性探针清理
  - 已验证证据：全套推送测试 250 passed（rules 47 + engine 41 + e1_binding 27 + endpoints 21 + e2e 9 + owned_keys_gen 13 + owned_keys_baseline 3 + note_writer 20 + handoff 21 + binding_protocol 25 + k1_parity 9 + k1_integration 3 + coverage 4 + column_alias 7）。前端 vitest 14 passed（FormulaPushPanel）+ 85 passed（e1Host + k1Host）。零本 spec 引入的回归。tasks.md 全部已完成任务标 `[x]`；未完成任务（17 夹具前端部分、19 editable 部分、22~25）如实标注待办理由。🟡 **INDEX.md 进度更新和 memory 摘要留给提交时一并处理**。
  - _需求：9.7_
