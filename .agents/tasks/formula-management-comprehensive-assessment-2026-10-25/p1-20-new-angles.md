# P1-20 新视角补充：性能规模 / 前端可维护性 / UI 中文化（只记影响整改的发现）

调查日期 2026-10-25，只读。依据：现读源码 + 真库只读查询（`audit-postgres`）+ Python 现算行数（`splitlines()`，与 `backend/scripts/check/check_file_size.py` 同口径；`split('\n')` 恒多 1）。
标「估」的数字是按代码路径推算、未压测。

## 0. 真库规模基线（2026-10-25 现查）

| 对象 | 数量 | 说明 |
|---|---|---|
| projects（未删） | 85 | 69 个 template_type/report_scope 为空、9 个 soe/standalone、1 个 consolidated |
| report_config 全局行 | 1191 | soe_standalone 352 / soe_consolidated 352 / listed_consolidated 244 / listed_standalone 243；**有公式的行仅 78~82 / 准则**，TB( 记号 66~68、ROW( 21~29、NOTE/WP 0 |
| report_config 项目层（`project:<id>`） | 0 | |
| formula_setting / formula_sync_item / formula_publish | **0 / 0 / 0** | 全局设置 / 待确认 / 发布记录在真库**从未被使用** ⇒ 下面的规模风险全部未被真实数据触发过 |
| working_paper / disclosure_notes / financial_report / trial_balance | 1991 / 1090 / 2464 / 743 | |

结论：单项目求值量很小（每次报表生成约 70 次 TB 取数），风险集中在「一次全局发布 × 项目数」的扇出，不在单次求值。

## 1. 性能 / 规模风险（目标并发 6000）

部署事实：`docker-compose.yml` 后端 `--workers 1`（单事件循环承载全部用户）；连接池 `core/config.py` `DB_POOL_SIZE=50` + `DB_MAX_OVERFLOW=100` = 150、`pool_timeout=30`（`core/database.py`）。

### P-1 全局发布后的传播是无界并发扇出（高）
- 位置：`services/formula_settings/propagation.py::publish_events` 每项目发一条 `FORMULA_CONFIG_CHANGED`；`services/event_bus.py::EventBus.publish` 用 `loop.call_later(debounce_ms)` + `asyncio.ensure_future(_dispatch)`，去重键 `_build_dedup_key` 含 `project_id`（同一 `publish_token` 也按项目各自成键）。
- 后果：一次发布影响 P 个项目 ⇒ 约 500 ms 后 **P 个 `_dispatch` 同时起跑**，每个 `propagate_*` 各开一个 `async_session`；全文件无 `Semaphore` / 分批（grep `formula_settings/*.py` 为 0）。
- 量化（估）：P ≤ 150 时连接池够用；P > 150 后排队，等满 30 s 抛 `TimeoutError`。🔴 `propagate_report` 的**第一步「标过期」也要连接**，拿不到连接就整个被 `on_formula_config_changed` 吞成降级日志 ⇒ 定义已提交、报表**连过期标记都没有**（静默不一致，R8.4「可见降级」只落在日志里）。现 85 个项目不会触发；6000 用户 / 每项目约 5 人 ≈ 1000+ 项目时必然触发。
- 叠加：`propagate_report` 每项目还会同步跑 `ReportEngine.recalculate_stale_rows`（CPU + 约 70 次 TB 查询 + ROW 引用 ACNR 解析），P 个并发重算全压在单事件循环上。
- 整改建议：传播加全局 `asyncio.Semaphore`（如 8~16）或改成队列 worker；把「标过期」从重算里拆出来，在发布事务内批量 UPDATE（一条 SQL 覆盖全部项目），这样后台重算失败也不会丢过期标记。

### P-2 发布请求内逐（项目 × 公式位）串行读写，且持有域排他锁（高）
- 位置：`formula_settings/publish.py::publish_global` → `_plan`（逐项目 × 逐变更建 `PlanItem` 并 `classify`）→ 逐条 `engine.py::apply_effect` → `stores.py::{ReportStore,SettingStore}.write_project`（每条先 `_find` 一次 SELECT 再 `flush`；报表层缺结构时再加 `project_scope` + `_find` 全局行，共 3 次往返）+ `upsert_pending` / `close_pending`（每条再 1~2 次往返）。`write_global` 也是逐公式位 `_find`，虽然 `_build` 已用 `list_global_exact` 读过同一批行（重复 SELECT）。
- 锁：`engine.py::lock_domain` 发布取**域级排他**咨询锁，项目侧写取共享锁 ⇒ 发布期间该域**所有项目**的公式保存都在等。
- 量化（估）：种子发布（`fill_all_formulas` → `publish_global(source=seed)`）S≈352 个报表公式位；某准则 P 个项目 ⇒ P×352 个 PlanItem。P=1000 时 35 万个对象在单事件循环里 classify（按每条 20~100 µs 估 7~35 s 纯 CPU，期间**全站请求卡住**）；其中需写入的条目按 3~4 次往返 × ~1 ms 计，每 1 万条约 30~40 s，全程持有排他锁。`preview_global` 走同一个 `_build`，「只读预览」本身也有同样的 CPU 成本。
- tb_detail / push 域全局作用范围是 `*`（memory 已记），P = 全部项目。
- 整改建议：按项目分批（每批独立事务或至少分段 flush）；`write_project` 改批量 upsert（`INSERT … ON CONFLICT`）；`_plan` 对无本项目层的项目直接按 inherit 批处理不逐条建对象；`write_global` 复用 `_build` 已读的 `current`。

### P-3 模板发布的订阅方 N+1（中）
- `formula_settings/template_sync.py::_publish_plan`：每个订阅记录依次 `get_project` + `upstream_records`（**同一作用范围不缓存**，每个订阅都重读全局 + 预设）+ `store.list_project` + `subscribed_definitions` ⇒ 约 4~5 次查询 / 订阅项目；`publish_template` 再逐（项目 × 域）`lock_project`。
- 对照：`apply_ops.py::apply_to_projects` 已有 `upstream_cache` 按作用范围缓存，这里没复用。
- 整改建议：按作用范围缓存 upstream、`list_project_many` 一次取全部订阅项目。

### P-4 tb_detail 全局发布 = 全平台底稿全部标 prefill_stale（中）
- `propagation.py::propagate_tb_detail` 按项目把**全部**底稿标 `prefill_stale`（docstring 自认「无法按 wp_code 精准缩小范围」），作用范围 `*` ⇒ 全部项目。
- 量化：现 1991 张底稿全部过期；下次打开逐张重新预填。规模上去后是「周一早上集中打开」的惊群。
- 整改建议：按公式位里的科目码反查用到它的底稿（`formula_reverse_index` 已有 TB 维度索引）再标。

### P-5 进程内缓存的失效点只在本进程（中，扩成多 worker / 多副本时生效）
- `formula_reverse_index.py::get_reverse_index` 是进程单例，`invalidate_reverse_index()` 只在处理发布的那个进程里调用（`propagation.py::publish_events`）。
- `formula_settings/custom_presets.py` 已有 60 s（`REFRESH_SECONDS`）读时补刷，可作同类先例；`push_settings._cache`、`domain_stores._mapping_cache` 按文件身份 / mtime 失效，不受影响。
- 现 `--workers 1` 无问题；为 6000 并发加 worker 后，其他进程的反向索引一直是旧的（影响「谁引用了这个单元格」与旧 handler 的影响分析）。整改建议：改用 Redis 版本号或沿用 custom_presets 的时效补刷模式。

### P-6 报表求值的小额浪费（低，修主路径时顺手）
- `report_engine.py::_generate_report` 每个报表类型新建 `ReportFormulaParser`（L1340），`_tb_cache` / `_tb_prefix_cache` 不跨报表类型共享 ⇒ 同一科目最多查 6 次（单项目只有约 70 次 TB 记号，绝对值小）。
- `evaluate_formula_result` 每条公式把整个 `row_values`（跨报表累积到约 350 行）重建一次 Decimal 字典 ⇒ 每次生成约 350×350≈12 万次 `Decimal(str())`。
- `WPExecutor.execute` / `load_note_values` 按单条公式取数、跨公式不缓存（现在报表公式里 NOTE/WP 记号为 0，暂无影响；用户自定义报表公式引用附注后才会出现 N+1）。
- `ReportEngine.get_report_cached` **全仓零调用方**，但 `generate_all_reports` 每次仍写 6 次 Redis `SETEX` ⇒ 只写不读的缓存（失效逻辑 `_invalidate_report_cache` 也随之是空转）。整改时要么删、要么接上读路径，别当成「有缓存」。

### P-7 前端每次保存还额外打一次传播（低，但会和后端事件重复）
- `FormulaManagerDialog.vue::propagateFormulaStale`（约 L3515）每次保存 / 恢复全局后再 `POST linkageBus.impact`（`source_uri = FORMULA:<节点>::config_changed`），`validateStatus: s < 600` + 空 catch ⇒ 任何失败都静默。后端已经由 `FORMULA_CONFIG_CHANGED` 传播一次，这是第二条路径：重复计算，且两条路径口径可能不一致。整改时应裁定只留后端事件。
- `settings/reportEffectiveRows.ts::saveReportRows` 对无项目（模板 / 旧口径）行逐行 `api.put`（N 个串行请求）。

## 2. 前端可维护性

### 2.1 行数与门禁余量（现算，splitlines 口径）

| 文件 | 现行数 | 白名单基线 | 门限（基线×1.05 或默认） | 余量 |
|---|---|---|---|---|
| `components/formula/FormulaManagerDialog.vue` | **4215** | 4502 | 4727 | 512 |
| `components/formula/FormulaEditDialog.vue` | 1579 | 1541 | 1618 | **39** |
| `backend/app/services/formula_push/engine.py` | 988 | 951 | 998 | **10** |
| `backend/app/services/consol_note_formula_service.py` | 1520 | 1470 | 1543 | **23** |
| `backend/app/routers/wp_formula.py` | 1507 | 1461 | 1534 | **27** |
| `backend/app/services/formula_engine.py` | 2197 | 2137 | 2243 | 46 |
| `backend/app/services/note_formula_generator.py` | 1483 | 1483 | 1557 | 74 |
| `backend/app/services/report_formula_service.py` | 780 | 未登记 | 800 | **20** |
| `backend/app/routers/wp_user_formulas.py` | 751 | 未登记 | 800 | 49 |
| `backend/app/services/wp_formula_service.py` | 737 | 未登记 | 800 | 63 |
| `backend/app/services/report_engine.py` | 2624 | 2693 | 2827 | 203 |

- FormulaManagerDialog **当前不超门**（memory 里「4959 > 4268」「4819 > 4481」两条记录已过期；HEAD `25a506a57` 现为 4215，工作树干净）。但基线 4502 比真实值高 287 行，门禁不做向下棘轮 ⇒ 实际允许回弹到 4727。整改时若触碰该文件，建议同步把基线下调到真实行数。
- 真正卡整改的是**余量 ≤ 40 行**的 5 个文件：formula_push/engine.py（10）、report_formula_service.py（20，一过 800 就要新登记）、consol_note_formula_service.py（23）、wp_formula.py（27）、FormulaEditDialog.vue（39）。凡是要往这几个文件里加冲突弹窗 / CAS / 鉴权的修复，先抽伴生模块再加功能，否则 pre-commit 必拦。
- whitelist 注释「consolSheetRows 静态数据约 900 行」已过期：`consolSheetRows`（L2643 起）现约 150 行。

### 2.2 FormulaManagerDialog 结构（4215 行）
- template 1~519（519 行，单个 `el-dialog`、8 个 `el-tab-pane`）/ script 521~3902（约 3380 行：49 个 import、63 个 ref、41 个 computed、43 个 async function、21 处直接 api/http 调用）/ style 3 段约 310 行（含一段**未 scoped** 的全局样式 L4105~4193）。
- 已有拆分先例可照抄：`components/formula/composables/useCrossCheckRules.ts`（247）、`useTbDetailFormulas.ts`（110）、`panels/*`、`settings/*`、纯函数模块 `noteScopeTargeting.ts` / `sheetIdentityMatch.ts` / `leftPanelAnchors.ts`。

### 2.3 建议拆分轴（按 script 内注释分区现测，行号为 HEAD）

| 优先 | 区段 | 约行数 | 抽成 | 与整改的关系 |
|---|---|---|---|---|
| 1 | 全局设置 / 本项目适配 / 模板（L3349~3530）含 `settingsDomain`、`onFormulaSettingsChanged`、`askApplyScope`、`onRestoreGlobal`、`propagateFormulaStale` | 180 | `composables/useFormulaSettingsBridge.ts` | 本次整改主战场（冲突弹窗、一处改全处生效）。🔴 顺带发现：`settingsDomain` 只区分 tb_detail / cross_ / 附注，**底稿、合并、辅助、推送节点一律落到 `report` 域** ⇒ 在底稿节点上点「应用范围 / 恢复全局」操作的是报表域，需在整改里核实 |
| 2 | 树导航数据：合并附注树（L957~1058）、动态附注树（L1096~1242）、静态附注树（L1242~1365）、ACNR 五域树（L1365~1716） | 约 750 | `composables/useFormulaNavTree.ts` + 静态树数据移 `.ts` 常量 | 纯数据构建，依赖少，最易抽、收益最大 |
| 3 | 右栏「当前页公式」sheet 归属匹配（L1916~2317） | 约 400 | 并入已有 `sheetIdentityMatch.ts` / `leftPanelAnchors.ts` 的组合式函数 | |
| 4 | 公式看板（L3530~3778） | 约 250 | 并入已有 `FormulaDashboardDialog.vue` | |
| 5 | 公式编辑弹窗编排（L3011~3335） | 约 325 | `composables/useFormulaEditFlow.ts` | 与 CAS / 保存提示改动重叠，抽之前先确认 `dialogSession` 闭包依赖（whitelist 注释：依赖 monkeypatch 符号或共享 `dialogSession` 闭包的 handler 不能搬） |
| 6 | 项目级 ↔ 主模板差异（L793~941） | 约 150 | `composables/useMasterTemplateDiff.ts` | |
| 7 | 合并工作表静态行 `consolSheetRows`（L2643~2793） | 约 150 | 数据常量 `.ts` | |

- 🔴 抽取的隐性成本：**15 个测试按源码文本断言 FormulaManagerDialog**（读 `.vue` 文本做字符串 / 正则匹配），其中 5 个在后端（`test_formula_runtime_zero_regression.py`、`test_workpaper_formula_scope.py`、`test_workpaper_route_task1_baseline.py`、`test_wp_formula_ref_template_type.py`、`workpaper_sync/test_phase5_e1_sheet_specs.py`），前端 10 个（如 `formulaComponentMounts.spec.ts`、`noteListFormulasWiring.spec.ts`、`fullInventoryGate.spec.ts`、`formulaPaths.spec.ts`）；另有 10 个前端测试直接 mount 该组件。搬代码会让这些「源码里必须出现 X」的守卫打红 ⇒ 每个拆分批次要把守卫改成读新文件（或改成行为断言），工作量要算进任务。
- 类型检查：全量 `vue-tsc` 在本仓库 OOM（memory ㉔），抽取后用单区域 tsconfig 只查改动文件并配一处变异证明。

## 3. UI 中文化一致性（公式相关界面）

扫描范围：`components/formula/**`、`views/FormulaGlobalSettings.vue`、`components/template-library/FormulaTab.vue` / `FormulaCoverageChart.vue`、`components/workpaper/FormulaStatusPanel.vue`、`components/CellFormulaDetail.vue`、`components/custom-query/FormulaTracePopover.vue`、`composables/formula/**`（72 个文件）。插值 / 绑定表达式造成的误报已逐条剔除，下面是确认会显示给用户的英文。

### 3.1 前端硬编码英文（确认）
| 位置 | 现文案 | 建议 |
|---|---|---|
| `components/CellFormulaDetail.vue` L14 | `⚠ Stale` 标签 | 「待更新」 |
| `components/template-library/FormulaTab.vue` L226、`components/workpaper/FormulaStatusPanel.vue` L538 | 表头 `label="Sheet"` | 「工作表」 |
| `components/formula/CellSelector.vue` L113、`FormulaRefPicker.vue` L106 | 占位「…选择底稿 Sheet」 | 「…选择底稿工作表」 |
| `FormulaTab.vue` L142 | 占位「搜索 wp_code / wp_name / sheet」 | 「搜索底稿编号 / 底稿名称 / 工作表」 |
| `FormulaTab.vue` L398 | 占位「搜索 source / target / 描述」 | 「搜索来源 / 目标 / 描述」 |
| `FormulaTab.vue` L203 | 提示「ACNR formula_ref：…（无 ACNR grammar_v1 等价，待迁移）」 | 改成「地址库引用：…（尚无等价写法，待迁移）」 |
| `FormulaManagerDialog.vue` L206 | 说明「系统预设公式（来自 prefill_formula_mapping.json）」 | 去掉文件名，「来自系统预设」 |
| `components/formula/StructureEditor.vue` L710 | `ElMessage.info('溯源跳转：查看数据来源（调用 trace-forward API）')`（且下一行 `// TODO`，是未实现的占位按钮） | 中文化同时按「空壳标开发中」处理 |

### 3.2 后端值原样显示成英文（确认，需后端或前端映射）
- 附注公式弹窗「来源」列：`components/formula/NoteFormulaDialog.vue` L48 `{{ row.source }}` 原样输出；来源值由 `note_formula_generator.py` / `note_formula_derivation.py` 写入，现算取值有 `check_presets.book_value`、`check_presets.movement`、`check_presets.sub_item`、`user_formula`（新建行前端写「手工」，与存量英文混排）。需要来源 → 中文标签映射。
- 公式校对目录「适用范围」列：`components/formula/settings/FormulaCheckCatalog.vue` L49 `prop="scope"`，来自 `services/formula_check_catalog.py`：
  - `_cross_check_preset` 把规则 `category` 直接当范围 ⇒ 显示 `income_statement` / `tb_vs_report` / `balance_sheet` / `cross_module`；
  - `_qc_rules` 范围 = `scope + category` ⇒ 显示 `workpaper 复核流程`、`submit_review 程序裁剪`、`audit_log 异常操作`；表达式列显示 `python：…`。
  - 同文件已有 `_SEVERITY_LABEL` / `_STD_LABEL` 映射先例，按同样方式补范围映射即可。
- 公式解析 / 求值错误：`services/formula_engine.py`（L451/463/505/537/571/1155/1163/1179/1192）与 `services/formula_parse_utils.py`（L133/143/176/204/233）抛英文 `Unexpected end of formula` / `Unexpected token` / `Empty formula` / `Unsupported function: X`；`routers/wp_user_formulas_v2.py` L117 `formula not found`。这些经公式试算、校验结果、保存失败提示回到界面（未逐条做浏览器实证，属代码路径推断）。

### 3.3 可接受（不改）
公式函数名 `TB` / `ROW` / `REPORT` / `ADJ` 按钮（`FormulaCrossCheckPanel.vue` L111~112）、示例 `ADJ('6001','aje_net')` 等属公式语法本身，按 UI 规范「技术术语保留英文」保留。

## 4. 对整改 spec 的直接输入（汇总）
1. 传播加并发上限 + 「标过期」移进发布事务（P-1），否则冲突弹窗 / 一处改全处生效在项目上千时会静默丢过期标记。
2. 发布 / 预览分批 + 批量 upsert + 缩短排他锁持有时间（P-2），模板发布按作用范围缓存（P-3）。
3. tb_detail 精准标过期（P-4）；反向索引跨进程失效（P-5）；删除或接通 Redis 报表缓存（P-6）；前端传播二选一（P-7）。
4. 改 formula_push/engine.py、report_formula_service.py、consol_note_formula_service.py、wp_formula.py、FormulaEditDialog.vue 前先抽伴生模块（余量 10~39 行）。
5. FormulaManagerDialog 先抽「全局设置桥」与「树导航数据」两块（约 930 行），每批同步改 15 个源码文本守卫并下调白名单基线；核实 `settingsDomain` 对底稿 / 合并 / 推送节点落到 report 域的问题。
6. 中文化 8 处前端文案 + 2 处后端值映射 + 公式解析错误信息中文化。
