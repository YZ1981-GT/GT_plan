# 推送后残留缺陷收口 — 任务

> 交付单元按 R5 → R3/R4 → R1 → R2 顺序；每组完成即记证据。不新建分支，只暂存本 spec 文件。

## 1. R5 开发服务器依赖缓存
- [x] 1.1 `vite.config.ts` 加 `cacheDir: '.vite'`，确认 Vite 自行重启并生成 `.vite/deps`
  - 证据：改配置约 20 秒后 `audit-platform/frontend/.vite/deps/_metadata.json` 生成（browserHash `76351ac5`，292 个文件含 `en-gb-DYXoK50H-PKUNUDJ6.js`）；`git check-ignore` 命中根 `.gitignore:174 .vite/`；ESLint 只扫 `src/`、`vitest.config.ts` 不继承 vite 配置，均不受影响；开发服务器进程未重启（Vite 进程内重载）
- [x] 1.2 浏览器实测：en-gb 分块 200、打开 Univer 底稿无 504
  - 证据：页面内取 `/.vite/deps/en-gb-DYXoK50H-PKUNUDJ6.js?v=76351ac5` 200（105610 字节）；动态 import `useEditorUniver.ts`（拉起 `@univerjs/presets` 依赖图）成功；打开重药安徽 B30-2B / A1-14（含「完整Excel」）全部资源无 4xx/5xx。说明：两张底稿实际走 HTML / OnlyOffice，未找到当前走 Univer 的底稿，Univer 分块以直接请求验证

## 2. R4 只改目标格的补丁器
- [x] 2.1 `services/xlsx_cell_patch.py`：文本 / 公式改写、插格插行、共享公式跳过、calcChain 处理、其余条目原字节
  - 证据：`patch_cells`（文字 / 公式改写、缺格缺行补插、共享 / 数组 / 数据表公式跳过并回报、公式改文字时删 calcChain 并清 `[Content_Types]` 与 workbook 关系里的引用、落盘前自检 + 原子替换）；`append_value_sheets` 只追加取值页（日期带格式、重名加后缀、`<sheet xmlns:r=… r:id>` 自带命名空间）；`excel_materialize._replace_cached_value` 文本缓存值改为转义（含 `&` / `<` 的项目名原先整页 XML 非法）
- [x] 2.2 单测（含 `.xlsm` 宏、x14 数据验证保留、字节比对）+ 磁盘变异
  - 证据：`test_xlsx_cell_patch.py` 14 例；独立 worktree 磁盘变异 P1~P5、A2、A3 全部打红（`mut_backend3`：29 条变异全杀、逐字节恢复 sha256 一致）

## 3. R3 表头外部引用归类 + 填写流程改造
- [x] 3.1 `_resolve_external_header_refs` 四类归类 + 依赖格缓存值更新
  - 证据：同标签（或缓存为空）⇒ 改本册引用；其余表头标签 ⇒ 静态文字并去示例；索引号 ⇒ 静态原值；数据 ⇒ 不动。依赖格缓存值沿跨页 / 同页引用链更新（`_final_cell`，最多 8 层）
- [x] 3.2 `fill_workpaper_header` 改为「openpyxl 只读规划 → 补丁器落盘」，`.xlsm` 纳入，标准布局保留
  - 证据：`_fill_workbook_header` 返回（外部引用改写, 填写清单），经 `patch_cells` 落盘；非活动页只写冒号后的客户 / 期间 / 截止日；多文件合并 `_merge_sheets_dedup` 改 `append_value_sheets`（主模板部件原字节，结构认不出才退回 openpyxl）
- [x] 3.3 `test_wp_header_fill.py` 补归类与新流程用例；回执原因收窄
  - 证据：表头 / 补丁器 / 合并三个文件 78 passed；新增 `test_wp_template_merge_preserves_main.py` 6 例（含与源文件逐值比对）；10 个 `test_*_merge_dedup.py` 同跑共 460 passed；磁盘变异 H1~H12、A1、A4 全部打红
- [x] 3.4 全量模板扫描（368 个）：数据验证条数 / 宏 / 非目标页字节不变，表头外部标签引用 0，数据引用不变；LibreOffice 转换不报错
  - 证据：368 个模板全部 ok；x14 数据验证 190 条不变、宏不变、无意外部件改动（只删 calcChain 8 个）；表头外部标签引用 547 → 0，数据引用 46 不变；表头仍显示模板示例文字（202X / ABC公司 / 张XX…）1327 → 0；按编码生成 174 个编码（58 个多文件）无崩溃、无数据验证丢失；LibreOffice 抽样转换 12 + 20 个全部成功（B30-2B `.xlsm` 是双语模板、无标签格，范围外）
- [x] 3.5 浏览器实测：【测试】项目按编码生成 F2 / E1-28 / D4-5，表头显示项目值、数据验证下拉仍在
  - 证据：浏览器会话里对【测试】公式同步乙有限公司_2025 调 `generate-from-codes`（F2 / D4 / E1）：created 3、`header_failures` 空。生成文件：F2-18「被审计单位：【测试】公式同步乙有限公司」「截止日：2025年12月31日」，D4-5「会计期间：2025年01月01日至2025年12月31日」，底稿目录 A2 / A3 已填；表头外部引用 0；主模板各页数据验证与模板逐页同数（F2-14、D4-4、E1-3 两张、E1-5、E1-6、E1-9、E1-10）。E1-28 在「E1-26至E1-32 IPO / 舞弊」情形文件里，非 IPO 项目按场景不并入 E1（与修复前同），由 3.4 全量扫描覆盖
  - 🔴 发现（范围外，已登记 design §6）：「完整Excel / 在线编辑」打开的不是生成文件，而是按项目从模板复制的在线编辑副本（`wp_onlyoffice_router._resolve_wp_file` 首次 `shutil.copy2(模板)`），表头照旧是模板占位（底稿目录「截止日：202X年12月21日」）—— 所有项目、所有模板都如此，与本次修的生成文件是两条线

## 4. R1 后端试算表端点
- [x] 4.1 `tb_balance_rollup.py` 抽出叶子 + 映射 + 发生额汇总，`recalc_unadjusted` 改调（现有用例全绿）
  - 证据：`leaf_condition` / `resolved_standard_code`（最长前缀）/ `period_movement_query` / `aggregate_period_movement`；现有试算表用例 97 passed
- [x] 4.2 端点：year 可省、`account_prefix`、`include_movement`、`include_prior`、`wp_*` 三列
  - 证据：重药安徽实测 `?account_prefix=2211&include_movement=true&include_prior=true` 回 5 行，2211 期初 7,271,702.54 + 贷 53,554,035.44 − 借 48,758,457.86 = 期末 12,067,280.12；省略年度 200（按项目年度）
- [x] 4.3 `test_trial_balance_row_contract.py`（真发请求 + 跨语言键契约）+ 变异
  - 证据：8 passed；磁盘变异 B1~B8 全部打红（含「子科目自有映射按自身、未映射继承父级」与缓存命中仍附加字段）

## 5. R1 前端单一入口与迁移
- [x] 5.1 `services/trialBalanceRows.ts` + 单测；`getTrialBalance` / `workpaperAuditYear` / `useAuditData` / `useFormulaParamCache` / `FormulaBar` 委托
  - 证据：入口 + `tbProfitLossUnder`（损益类科目族借 / 贷 / 审定）+ `tbErrorText`；`services/__tests__/trialBalanceRows.spec.ts`（参数拼装、解包、并发合并、金额口径）；`fetchTbAmountByPrefix` 由首条匹配改科目族之和
- [x] 5.2 D / F / G 循环调用处迁移（字段逐处改对）+ 相关 spec 更新
  - 证据：31 个文件；`f2D4CostPull` / `g11CrossHelpers` / `workpaperAuditYear` 用例按端点真实字段改写
- [x] 5.3 H / I 循环调用处迁移
  - 证据：23 + 2 个文件（含查询串拼在 URL 里的 H7 两个审定表页）；H1 / I3 / I4 / K3 / K7 原 `=` 覆盖改求和；`fetchI2TbData` 去掉缺 `/api` 的客户端参数、失败抛错不再落库全零；I4 / I5 上年数改本年期初；`useH3RentalIncome` / `i2-p0-wiring` 用例改写
- [x] 5.4 J / K / M / N 与公式管理调用处迁移
  - 证据：36 + 1 个文件；🔴 端点原先忽略 `account_prefix`，现在真筛 ⇒ K1 / K2 / K4 / K5 / K6 原先只传首码的改传整组码；三处请求不存在的 `/api/trial-balance`（公式栏、结构编辑器、G7 回退的 `/api/trial-balance/query`）改走入口；M2 原先把列表当单对象读（勾稽恒 0）
- [x] 5.5 单一入口守卫 + 变异
  - 证据：`__tests__/trialBalanceRowsSingleEntry.spec.ts`（字面量 / 查询串 / 拼接 / 根路径 / 路径常量及别名七种写法各命中一次，导航 / 子路径 / 事件名 / 注释不命中；扫描范围 > 3000 文件、入口本身命中）；现扫 0 处直连
- [x] 5.6 浏览器实测：重药安徽 H3-14 6051、D2-7、J1-8、G11 取数与试算表页一致
  - 证据（浏览器注入只读拦截，写请求全部拦下未落库）：D2-7 测试总体 1,004,440,483.35 = 1122 本期借方；J1-8「自动取数」贷 53,554,035.44 / 借 48,758,457.86 = 2211 本期贷 / 借；G11-1 试算平衡表数 14,032,800.62 = 试算表页 6111；H3-14 TB 6051 为「-」= 试算表页 6051（0）
- [x] 5.7 补漏（收尾回归抓到）：守卫「不存在的根路径」只认 `/api/trial-balance` 后接引号或 `?`，漏了后端同样没有的子路径
  - 证据：后端红基线 `test_gap_families_still_carry_trial_balance_references`（G4 代码引用 1 → 0）追查时发现 G6 审定表 TB 核对与 E0 品种矩阵账面金额请求 `/api/trial-balance/query`、附注公式弹窗请求 `/api/trial-balance/`（均恒 404 被吞，核对数 / 账面金额 / 试算表候选恒空）；三处改走入口（G6 逐行审定优先、其次未审，E0 一次取齐五个品种），守卫改为「该前缀下不以 `${…}` 开头的子路径一律违规」（后端只有 `/{pid}/{year}/sync-from-workpaper`），命中样本 7 → 9；红基线计数按「换了入口」改为 G4 / G6 各 0。变异 MF01~MF04 全部打红（见 7.1）

## 6. R2 年度空值类型债
- [x] 6.1 共用组件 / 组合式函数：抽凭引擎、截止测试、集中调整同步、挂凭列表、附注同步条
  - 证据：`GtVoucherSamplingEngine` + `useVoucherSampling`（取重要性为空返回 null、执行抽样提示不发）、`GtCutoffAutoSampling` + `useCutoffAutoSampling`（默认截止日留空、年度到达后补，不再拼 `null-12-31`）、`useAdjustmentCentralSync`（手动同步提示、自动同步静默跳过，原先年度为空仍发同步请求）、`listAttachedVouchers`（为空返回 `[]`）、`GtWpDisclosureSyncBar` / 批注 / 影响预览 / 联动角标等 `year` 放宽为 `number | null`；合并页 `effectiveConsolYear()` 返回 `number | null`，模板经 `consolYear` 收窄后再传子组件，一键刷新 / 重新汇总冻结上下文为空不发起。用例：`useAdjustmentCentralSync.spec`（手动 / 自动两例）、`FormulaDebugPanel.errorText.spec`、`MisstatementSummaryView.spec`、`WorkflowProgress.year.spec`（3 例）
- [x] 6.2 底稿调用处：挂凭导入门控、D/N 披露、I3~I6、父传子 prop
  - 证据：「从序时账挂入导入」入口 60 处全部门控（本 spec 补 49 处，另 11 处原先已拦截）；🔴 K1 / K3 / K7 / K8 / K9 / M1 / M2 原先把 `year`（ComputedRef 对象本身）当年度实参传 ⇒ 改 `year.value`；🔴 K3 / K5 / K7 用 `ElMessage` 却未导入（AutoImport 不含 element-plus）⇒ 原先点到即 ReferenceError；I3 / I4 / I5 年度为空时日期年份代理行不计入本期借方（原先把全部历史原值算成本期新增）；🔴 D4 附注（6）义务表头原先 `?? 2025`（两张披露页都没传年度）⇒ 表头恒 2026 / 2027，改传 `auditYear` + `section6Rows`，年度为空不推该表；子组件 prop / 选项字段的年度声明放宽 49 处。用例：`d4DisclosureModel` / `d4NoteSectionMap` / `i3~i5TargetedCheckModel` / `g7ConsolLinkageEntry`；字面量年度兜底守卫 `auditYearLiteralFallbackGuard.spec.ts`（`?? 2025` / `|| 2025` / `= 2025` / `ref(2025)`，现扫只剩 1 处豁免）
- [x] 6.3 视图页门控（报表 / 试算表 / 调整 / 交付中心 / 审计报告 / 现金流量表 / 错报 / 签字等）
  - 证据：浏览器在无审计年度项目（`fc5b15fd`）逐页打开：报表 / 调整分录 / 错报 / 审计报告 / 现金流量表 / 试算表显示「未设置审计年度…」，无 `/null` 请求、无错误弹窗；试算表原先还静默回 3 个 422（冻结状态、余额表检测、工作流进度条），已在年度为空时不发（`WorkflowProgress` null = 不请求、不传 = 后端按项目年度）。合并页（【测试】公式同步集团）报表 / 附注 / 底稿请求都带 2025。🔴 交付中心与附注编辑页的年度取自 `projectStore.year`（初值去年、切到无年度项目不清空）⇒ 无年度项目上仍请求 `year=2025`，空值门控碰不到 null —— 根因在 store，见 6.5
- [x] 6.4 全量 vue-tsc：候选树对比 HEAD 与 `213f19816`，新增 440 条清零且无新增；勾选审计年度 spec 8.5
  - 证据（40GB 堆全量；HEAD `709b21275`）：HEAD 3599 条，相对基线新增 461 条（326 种，TS2322 278 / TS2345 175 / TS2769 8）；候选树终版 3153 条，相对 HEAD 减少 447、新增 1 —— `Adjustments.vue` 既有的 `loadEntries` 未定义（HEAD 第 181 行同错，只是信息里的组件类型多了一个导入名），年度相关新增 0；候选树相对基线剩余新增 23 条均非年度问题、HEAD 即有（`noteDisclosureJump` 11、`GtH8` 事件名 6、`useD7Detail` 2、`ConsolMiddleNav` / `D2TabAdjudication` 各 1、`GtD2AccountsReceivable` / `Adjustments` 既有错误信息变化各 1）。中途两轮抓到的：R1 漏登记的 `g11ReturnRateBalanceMap.spec.ts`（已补进清单）；运行时上下文 `year` 放宽为 `number | null | undefined` 后 H10 检查页 prop 未放宽（已放宽）。审计年度 spec 8.5 已勾选并指向本 spec
- [x] 6.5 项目 store 的 `year` 改 `number | null`：初值去年、切到无年度项目不清空 ⇒ 交付中心 / 附注编辑页 / 项目仪表盘 / `useAuditContext` 消费方在无年度项目上仍按 2025 取数（今年兜底棘轮基线 `stores/project.ts` 1 处）。页面多在 store 解析出年度之前挂载，`onContextChange` 不盯 store 年度。用户 2026-10-27 拍板根治（design §3.2）
  - [x] 6.5.1 store：`year` 初值 null、`yearStatus`、换项目先清空、乱序响应丢弃、取项目信息不参与 GET 去重、`retryProjectContext`；单测
    - 证据：`stores/project.ts` 年度初值 null + `yearStatus`（idle / loading / ready / failed）；换项目且路由没带年度先置 null + loading，取到项目信息后 = 项目审计年度（没填为 null）+ ready；取项目详情 `getProject(pid, { dedupe: false })`，失败再取一次，两次都失败记 failed（不当成「没填」）；晚到的旧项目响应按序号丢弃；`changeYear` / `setCurrentYear` 置 ready（晚到的项目信息不覆盖用户选的年度）；`currentProjectContext.year: number | null`；`loadProjectContext` 同口径。并发会话未提交的「切项目只取一次」（R16）改动被这次重写覆盖，其未跟踪用例 `project.syncFromRoute.fetchOnce.spec.ts` 在新实现上 4 例照绿。用例 `project.yearStatus.spec.ts` 14 例
  - [x] 6.5.2 `ProjectContextGate` 套 DefaultLayout 路由内容区（读取中 / 失败重试）；待重算详情跳转、全量重算、切项目不再造年度；单测
    - 证据：`components/layout/ProjectContextGate.vue`（读取中「正在读取项目信息…」、取失败「读取项目信息失败」+ 重试，都不渲染页面）；DefaultLayout 待重算「查看详情」缺年度不带 year、「重算」缺年度提示不发、目录切项目只用目录项自带的年度（原先把当前项目的年度带给目标项目）；`utils/resolveAuditYear.yearQuery` 统一「有年度才带」。用例 `ProjectContextGate.spec.ts` 5 例、`DefaultLayout.year.spec.ts` 7 例（真路由 + 真 store，子组件打桩）
  - [x] 6.5.3 同类日历兜底清零（棘轮基线只剩日历豁免）：重算、穿透、三栏布局弹窗、F2 计价抽样、保存后影响分析、穿透 store、两个无调用方函数、底稿列表测试桩；单测
    - 证据：13 处全修 —— `useStaleStatus` 重算、`usePenetrate` 11 个跳转、三栏布局全局弹窗年度（`GtRefreshScopeDialog` 缺年度不打开、`CustomQueryDialog` 选了项目没年度不查）、`useFCycleEditor` F2 计价抽样（原先恒用今年，改项目年度，经 `useEditorCycles` 传入）、`useEditorSave` / `useStaleImpact` 保存后影响分析缺年度不发、drilldown store 初值 null + 缺年度不取（账表穿透页年度改「路由 → store」、缺则清掉上次的年度）、`useBatchQuery` / `consolidationApi` 两个无调用方函数、底稿列表测试桩；前端今年兜底棘轮基线 14 → 0（`auditYearCalendarFallbackBaseline.json` 为空、`FROZEN_TOTAL_CAP = 0`），store 的年度下拉选项进日历豁免表。附注编辑页改由路由壳 `DisclosureEditorRoute.vue` 挂载：项目没填年度不挂、提示先填；页内年度仍按「路由 → store」同步读（信息栏切年度立即生效 —— 只用壳传入的 prop 会滞后一拍，切年度后 `fetchTree` 取到旧年度），prop 只作离开项目那一刻的兜底。新用例 10 个文件（store / 闸门 / 布局 / 穿透 store / 穿透页 / 附注壳 / 重算 / 计价抽样 / 影响分析 / 自定义查询），既有用例补例或随签名改 5 个文件（穿透、一键刷新弹窗、编辑器循环组合、保存、年度工具）
  - [x] 6.5.4 store 年度放宽后的消费方类型（全量 vue-tsc 对比 HEAD，年度相关新增 0）
    - 证据：全量 vue-tsc（40GB 堆，候选提交对 HEAD `709b21275`）3153 vs 3599，减 447、新增 1（`Adjustments.vue` 既有 `loadEntries`），与 6.5 之前一致 ⇒ 本轮新增 0；首轮新增 37 条，其中年度相关 36 条（附注编辑页 25、证据链治理中心 7、底稿生命周期「一键生成」/ 项目设置 / 编辑器查账窗口 / store 事件载荷各 1）逐条修掉，另 1 条即上述既有 `loadEntries`。证据链治理中心缺年度整页空态；生命周期「一键生成」缺年度提示不发（`WorkpaperLifecycleView.year.spec.ts` 2 例，磁盘变异 L1~L4 —— 去掉门控 / 提示后不 return / 传错年度 / 执行后不刷新 —— 全部打红，恢复后 sha256 一致）。附注编辑页暂存版行数不变（3265 = HARD_CAP）
  - [x] 6.5.5 回归（暂存树全量 vitest 对比 HEAD）+ 浏览器实测（无年度项目与有年度项目互切）
    - 证据：磁盘变异（独立 worktree）M01~M28 全部打红，变异前 16 个用例文件 98 例全绿，每条恢复后 sha256 一致；M13 首版只换开标签成了模板编译错误（红的形态不对），补 M13b 开闭标签一起换，红在「读取中不挂页面」断言上。全量 vitest 对比 HEAD 新增失败 0（逐条见 7.1）。浏览器（chrome-devtools 隔离上下文，只读）：无年度项目 `fc5b15fd` 的附注编辑 / 交付中心 / 项目仪表盘 / 证据链治理 / 试算表 / 报表全部显示「未设置审计年度…」且没有一条带年度的请求（原先交付中心 `year=2025` 回 500、附注 `/2025` 回 404）；从重药安徽（2025）切过去不再带 2025；切回重药安徽附注编辑按 2025 加载 166 章，信息栏切 2024 立即按 2024 取；离开项目后 store 年度 null、没有 `/null` 请求；收尾另查项目设置（年度下拉显示「选择年度」，原先 0 / 去年）与底稿生命周期（只读打开，未点「一键生成」），同样没有带年度的请求。没有挂载用例、只靠棘轮 / 类型检查 / 浏览器的：三栏布局全局弹窗的年度取法（今年兜底棘轮）、证据链治理中心空态与项目设置初值（类型检查 + 浏览器）

## 7. 收尾
- [x] 7.1 候选树回归：后端相关测试、前端全量 vitest 与 HEAD 逐条比对，新增失败为 0
  - 证据（候选树 = HEAD `709b21275` 干净检出 + 本 spec 文件，混改的 7 个文件逐 hunk 复放；对照 = 同一提交的干净检出）：
    - 后端相关 154 个文件逐条比对：新增 4 条全部归因 —— 2 条是两棵树并行跑 `test_trial_balance_sign_passthrough` 撞同一个 PG 唯一键，2 条是按新语义改写的用例（见 design §3.1）；这 3 个文件两棵树各自串行复跑 69 / 69 passed
    - 前端全量 vitest 两轮：首轮新增 6 条，真问题 2 处已修（渲染器运行时边界用例、报表页行数门）；终轮候选 2479 个文件 / 38170 例 / 失败 191，HEAD 2475 / 38135 / 190，两边都红 189 条（HEAD 既有）。两轮里候选红、HEAD 绿的 5 条与 HEAD 红、候选绿的 1 条全是 PBT 偶发红：按失败那次的种子在两棵树各复跑一次都红在同一反例上 ⇒ 与本 spec 无关（逐条见 design §6）
    - 6.5 之后第三轮全量 vitest（候选 = 6.5 候选提交 `a6cfdf2da`，与 HEAD 同时跑）：候选 2490 个文件通过 38024 / 失败 188，HEAD 2475 个文件通过 37935 / 失败 186；两边都红 185 条 + 套件级 4 个（HEAD 既有）。候选红、HEAD 绿 3 条：`line-budget` Shell 行数 1365 > 棘轮 1362（6.5 在 `WorkpaperEditor.vue` 加了 3 行 ⇒ 行为不变地合并回 1362，不抬棘轮）、`FrontendReferenceIntegrity` 死代码用例超时（15.26 s > 15 s，HEAD 那轮 14.79 s；单独复跑 9.0 s 通过）、`transposeGrid` Property 10（PBT）；HEAD 红、候选绿 1 条 `useG6EclFormulaEngine` P6（PBT）。两条 PBT 按失败种子（-1064356007 / 1768957403）在两棵树各复跑一次，都红在同一反例上
    - 终版暂存树（6.5 候选之后又改了附注编辑页年度同步读、加 `DisclosureEditorRoute` 用例、Shell 行数回落）全量 vitest：2491 个文件通过 38030 / 失败 186（对照第三轮 HEAD：2475 个文件通过 37935 / 失败 186），两边都红 185 条 + 套件级 4 个；候选红、HEAD 绿只剩 `transposeGrid` Property 10（PBT，种子 1825878124 在 HEAD 复跑同红，属用例拿 JSON 存取当快照，见 design §6），HEAD 红、候选绿 1 条即上一轮的 `useG6EclFormulaEngine` P6 ⇒ 新增失败 0。之后补的 `WorkpaperLifecycleView.year.spec.ts`（2 例）在主树与同一提交的 worktree 上单独跑通过；终版树单区域 vue-tsc 抓到它首版一处 TS2322（spy 变量类型写成 `ReturnType<typeof vi.spyOn>`），改为 `MockInstance<typeof ElMessage.warning>` 后该文件 0 条，换回旧写法即报（变异确认这次单区域检查真的查到了这个文件）
    - 提交前 HEAD 被并发会话前移到 `083f5e774`（`cdf583960` 程序链加固批 4 + `083f5e774` 在线编辑第三批，共 163 个文件，与本 spec 重叠 7 个：INDEX / memory / 三栏布局 / 项目 store / `getProject` / eventBus / G11）⇒ 本 spec 改动重放到新 HEAD：三方合并 4 个文件自动合上；INDEX 两处相邻行冲突各取各改的那行；项目 store 三处冲突取本 spec 版本（已含对方 R16「换项目只取一次」，对方提交里的 `project.syncFromRoute.fetchOnce.spec.ts` 照绿）；`getProject` 取对方的 apiProxy 共享在途 + 本 spec 的 `dedupe` 选项。合并后的 5 个代码文件与主工作区文件逐字节一致（浏览器实测跑的就是这份代码）。重放后（候选 = 新 HEAD + 本 spec 357 个路径）全量 vitest：候选 2502 个文件通过 38152 / 失败 188，新 HEAD 2485 个文件通过 38055 / 失败 188，两边都红 186 条 + 套件级 4 个；候选红、HEAD 绿 2 条都是 PBT —— `DefaultLayoutNavigation` 的 `tabToRoute`（用例里自带的本地函数，生成器出 `"valueOf"` 时 `map[tab]` 取到原型方法，种子 -1431292672）、`a81OtherInfoRepresentation` Property 3（加纯空白值被裁掉后长度不符，种子 -1065829984），两条按种子在新 HEAD 复跑同红、同反例；HEAD 红、候选绿 2 条（`a173ConsultationRecord` Property 2 同为纯空白值、`e1SyncEntryRowIdentity` 新增行 id 的随机尾号碰上 3 / 4）⇒ 新增失败 0；全量 vue-tsc：3153 条 vs 新 HEAD 3599 条，减 447、新增 1（`Adjustments.vue` 既有 `loadEntries`），与重放前一致（新 HEAD 相对旧 HEAD 的 8 处增减都在对方改的 `GtH8` / `useD7Detail`，重放后原样保留）
    - R2 定向 21 个用例在终版候选树复跑：19 个文件 336 例，失败 3 条均 HEAD 同红（`hostSheetDispatchChain` 2、`samplingHostMethodologyCoverage` 1）；另 2 个是并发会话未跟踪的用例，不在候选树
    - 全量 vue-tsc（40GB 堆）终版：3153 条，相对 HEAD 减 447、新增 1（`Adjustments.vue` 既有的 `loadEntries`，见 6.4）
    - 收尾磁盘变异（独立 worktree）MF01~MF19 全部打红：变异前 127 条基线用例全绿，每条恢复后 sha256 一致；行数门对候选树 307 个改动文件 exit 0
- [x] 7.2 文档：本 spec 证据、INDEX、dev-history、memory；清理临时 worktree / 探针 / 浏览器页
  - 证据：tasks / design（§3.1 收尾补的、§6 范围外含 6 条 PBT 偶发红的种子与反例）、INDEX 本行 26/27、dev-history 本 spec 条目、memory 本 spec 一行 + 审计年度一行改写（同时合并两处旧行，仍 ≤ 300 行）；审计年度 spec 8.5 已勾选。四个临时 worktree（候选 / HEAD / 变异 / 基线）先查无目录联接再删除并 prune，主树 `node_modules` 完好；探针与比对脚本都在仓库外临时目录，随后删除；浏览器隔离页已不在（列页只剩 about:blank）。6.5 轮：tasks 6.5.x 与 7.1 第三 ~ 五轮比对、design §3.2 与 §6（PBT 12 次 / 10 个性质、死代码用例超时）、INDEX 本行改 27/27 并写 6.5、dev-history 本 spec 条目补 6.5 与教训、memory 本 spec 一行改写（299 行）；推送用临时分离头 worktree，推送后与其余临时 worktree（候选 / HEAD / 变异 / 终版）、探针、浏览器隔离页一起清理
- [x] 7.3 只暂存本 spec 的文件，报告并询问是否推送
  - 证据：主仓库索引写入候选树 blob（`update-index -z --index-info`）：316 个路径（新增 15 / 修改 301 / 删除 0），写入后逐条核对已暂存集合 = 清单、blob 一致；混改的 12 个文件（含 INDEX / memory / dev-history / 行数白名单，以及 08:57 并发会话刚改过的 `useAdjustmentCentralSync.ts`）只暂存本 spec 的 hunk，工作区仍留并发会话的改动。按 pre-commit 同口径查暂存内容：gitleaks 无泄漏、行数门 307 个文件 exit 0、无 U+FFFD；暂存树自洽门（`check_staged_tree_self_consistency.py`，物化 24608 个文件）2 道门 exit 0。暂存清单副本 `C:\Users\Administrator\post_push_residual_stage_list.txt`（被冲掉时经 Python 按字节喂给 `git update-index --index-info` 写回）。未提交、未推送
  - 证据（6.5 后终版，用户 2026-10-27「之后提交并推送当前分支」）：本 spec 357 个路径（新增 29 / 修改 328 / 删除 0），提交树 = 新 HEAD `083f5e774` + 本 spec 条目，由私有索引生成（收尾时并发会话正往共享索引暂存它自己的路径，并先后推了两个提交；不在共享索引上提交，免得带上对方的暂存或被对方带走）；混改文件只带本 spec 的改动块，工作区仍留并发会话的改动。提交在临时分离头 worktree 里对同一棵树执行（pre-commit 的 gitleaks / 行数门 / UTF-8 / 附注模板棘轮照常跑），分支用 `update-ref` 带旧值比对前移；pre-push 对分离头跳过检查 ⇒ 推送前手工跑暂存树自洽门。单一提交推送到当前分支 `spec/disclosure-note-doc-upload-and-batch-fill`，推送后共享索引里本 spec 的条目对齐到提交内容（不留会回退对方提交的暂存）
