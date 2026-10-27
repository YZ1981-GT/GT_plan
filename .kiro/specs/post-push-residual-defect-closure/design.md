# 推送后残留缺陷收口 — 设计

## 1. 现状核对（2026-10-26，HEAD `d0de87a6c`，基线 `213f19816`）

| 项 | 现算 | 方法 |
|---|---|---|
| 前端直接 GET 试算表列表 | 84 处 / 65 文件（另 `useAuditData` 2、`FormulaBar` 1、`useFormulaParamCache` 1） | 全仓扫 `` `/api/projects/${..}/trial-balance` `` + 变量拼址 |
| 不带 year 的调用 | 37 处（与审计年度 spec 登记一致；HEAD 同数） | 同上，逐处读 params |
| 读端点不返回的字段 | `debit_amount` / `credit_amount` / `period_debit/credit` / `borrowing/lending_amount` / `debit_occurrence` / `transaction_count` / `ending_balance` / `closing_balance` / `prior_*` / `begin/end_audited` | 端点 `get_trial_balance` 返回 12 个键（见 §2.1） |
| vue-tsc 新增 | 440 条 / 305 种（TS2322 266、TS2345 174） | 40GB 堆全量跑两棵树，按（文件, 码, 信息）计数差集 |
| 表头区外部单格引用 | 15 个模板 574 格：本册无该页 164（标签 145 / 数据 19）、本册有该页 410（标签 373 / 索引号 22 / 空 6 / 数据 9）；另 13 个复合公式 | openpyxl 公式 + data_only 缓存值逐格归类 |
| 含 x14 数据验证的模板 | 39 个 / 190 条 | zip 内 sheet XML 计 `x14:dataValidation` |
| `.vite/deps` | 不存在（仅 `.vite/vitest`） | 目录检查 + 浏览器 504 |

## 2. R1 试算表取数契约

### 2.1 端点（`routers/trial_balance.py::get_trial_balance`）

- `year: int | None = Query(None)`：省略 ⇒ `require_project_audit_year(db, project_id, None)`（与全平台 422 文案同源）。
- `account_prefix: str | None`：逗号分隔，按 `standard_account_code.startswith` 过滤；在缓存读出之后、scope 过滤之前做（缓存仍是全量，不分前缀存）。
- `include_movement: bool`：每行加 `period_debit` / `period_credit`（字符串金额，无数据为 `"0"`）。口径 = 未审数重算同一套「叶子节点 + 最长前缀映射」，抽到新模块 `services/tb_balance_rollup.py`（`leaf_condition` / `resolved_standard_code` / `aggregate_period_movement`），`recalc_unadjusted` 改调它（行为不变，现有用例守）。
- `include_prior: bool`：每行加 `prior_audited_amount`（上年同标准科目审定数，取不到为 null）；来源 `prior_year_context.resolve_prior_source`（与报表上期 / PREV 同一来源，已有「上年项目唯一才认」规则）。不另造跨项目规则。
- 基础行补 `wp_adjustment` / `wp_publish_base` / `wp_published_at`（ORM 已有列；`TrialBalance.vue hasPublishBaseChanged` 读它，原先恒假）。
- 响应形状不变：列表；v1 残留时 `{data, warning, sign_convention_ready}`（不在本 spec 改，前端统一解包）。

否决：只给前端补 `year`（把「待取数」变成静默错 0，字段问题仍在）；前端各处自行加参数（无单一入口，下次照样漂）；为前缀单独建缓存键（全量行 ≤ 千级，读出后过滤成本可忽略）。

### 2.2 前端单一入口 `src/services/trialBalanceRows.ts`

```ts
export interface TrialBalanceRow { standard_account_code; account_name; account_category; direction;
  unadjusted_amount; rje_adjustment; aje_adjustment; audited_amount; opening_balance;
  exceeds_materiality; below_trivial; updated_at; wp_adjustment; wp_publish_base; wp_published_at;
  period_debit?; period_credit?; prior_audited_amount? }
fetchTrialBalanceRows(projectId, { year?, accountPrefix?, includeMovement?, includePrior?, companyCode?, silent? })
  → Promise<{ rows: TrialBalanceRow[]; warning: string | null }>
tbNumber(v) / tbRowsUnder(rows, prefixes) / tbSumUnder(rows, prefixes, field) / tbOccurrence(row) → { debit, credit }
```

- `year` 省略交给后端按项目年度；调用方有年度就传（年度切换页面）。
- `tbOccurrence`：有 `period_debit/credit` 用真实发生额；否则按 `pl_occurrence` 同一拆分（费用类 → 借方 = 未审数、收入类 → 贷方 = 未审数）。
- 读取失败抛错（调用方决定「待取数」提示），不返回空数组冒充 0。
- `auditPlatformApi.getTrialBalance`、`workpaperAuditYear.fetchTrialBalanceByPrefix` / `fetchTbAmountByPrefix`、`useAuditData.getTbAmount` / `getPrevYear` 委托给它。

### 2.3 调用处改法（逐处，按循环分批）

| 读法 | 改为 |
|---|---|
| 不带 year / `year: undefined` | 不传（后端按项目年度），或传已解析的审计年度 |
| `account_code` / `account_codes` / `account_prefix` / `limit` 参数 | `accountPrefix`（后端真筛）+ 前端 `tbRowsUnder` |
| `debit_amount − credit_amount` 等期末余额 | `audited_amount` / `unadjusted_amount`（正数口径，方向见 `direction`） |
| 本期借 / 贷发生额、贷 − 借净发生额 | `includeMovement` + `period_debit/credit` |
| `ending_balance` / `closing_balance` / `end_audited` / `begin_audited` | `audited_amount` / `opening_balance` |
| 上年数（损益类） | `includePrior` + `prior_audited_amount`；资产负债类用 `opening_balance` |
| `transaction_count` | 端点无此数：改走序时账已有端点或去掉显示，逐处判 |
| `const { data } = await api.get` / 当单对象读 | 按列表解包 + 按科目取行 |

孤儿 composable（无生产引用方：useH7 / I4 / I6 / K2 / K6~K11 FormData）同样改（保持可用，不删；删除另议）。

### 2.4 守卫

- `src/__tests__/trialBalanceRowsSingleEntry.spec.ts`：扫 `src/`（剔注释 / 字符串外的写法同口径），除入口文件外不得出现试算表列表 GET（字面量与变量拼址两种形态；变异：新建违规样本必须命中）。
- `backend/tests/test_trial_balance_row_contract.py`：TestClient 真发请求，响应键 == 解析 `trialBalanceRows.ts` 的 `TrialBalanceRow` 键（含可选键在开关下出现）；year 省略取项目年度、项目无年度 422、前缀、发生额（叶子 + 父子不双计）、上年（同项目上年 / 无上年 null）、`wp_*`。
- 现有用例：`useAuditData.test.ts` 等按新参数改；mock 只给端点真实字段。

## 3. R2 年度空值类型债

规则（与审计年度 spec R3 同一口径）：年度 `number | null`；读请求为空不发 → 空态；写 / 用户点击的请求为空不发 → `MISSING_AUDIT_YEAR_MESSAGE`；纯计算（列头、默认截止日）为空给不含年度的写法。禁 `!` / `as number`。

| 家族（新增条数） | 根因位置 | 改法 |
|---|---|---|
| 抽凭引擎（68） | `GtVoucherSamplingEngine` prop + `useVoucherSampling` | prop `number \| null`；取重要性为空返回 null；抽样为空提示不发 |
| 截止测试抽样（12） | `GtCutoffAutoSampling` + `useCutoffAutoSampling` | 同上；默认截止日为空留空，年度到达后补 |
| 集中调整同步（78） | `useAdjustmentCentralSync` 的 `year` 选项 | `MaybeRefOrGetter<number \| null>`；手动同步提示不发、自动同步静默跳过 |
| 挂凭（84） | `listAttachedVouchers`（48）/ `importFromAttached` 调用处（36） | 列表为空返回 `[]`；导入处门控 + 提示（逐文件同形改） |
| 附注 / 披露（~40） | `GtWpDisclosureSyncBar`、D/N 披露 tab、`checkNoteConsistencyGeneric`、`getDisclosureNoteDetail`、D4 义务列 | 子组件 prop 放宽 + 内部门控；调用处门控；列头函数接受 null |
| I3~I6 定向检查（~20） | `asOfYear` / `getYear()` 入参 | 组合式函数入参放宽，内部按空处理 |
| 父组件传子组件 `year?: number`（~25） | 子组件 prop 声明 | 子组件 prop 改 `number \| null`，用处门控 |
| 视图页（~100） | 各视图 `year` computed | 每个请求函数入口门控；年度选择组件 prop 放宽 |

验证：单区域 vue-tsc 逐批（只查改动文件，配变异：注入 `const x: number = null` 应报 TS2322）；收尾全量 vue-tsc（40GB 堆）候选树对比 HEAD 与基线，新增 440 条清零且无新增。

### 3.1 实施记录（2026-10-26~27）

- 改动面：178 个前端文件（源码 164 / 用例 14；新增用例 `__tests__/auditYearLiteralFallbackGuard.spec.ts`、`components/common/__tests__/WorkflowProgress.year.spec.ts`）。
- 共用：抽凭引擎、截止测试、集中调整同步（手动提示 / 自动静默）、挂凭列表（为空返回 `[]`）、附注同步条、批注 / 影响预览 / 联动角标等组合式函数的 `year` 放宽为 `number | null`。合并页 `effectiveConsolYear()` 改返回 `number | null`，模板用 `consolYear` 计算属性收窄后再传给只收 `number` 的子组件（函数调用结果在模板里收窄不了）；一键刷新 / 重新汇总冻结上下文年度为空返回 null、提示后不发起。
- 底稿：「从序时账挂入导入」入口 60 处全部门控（补 49 处，另 11 处原先已拦截）；K1 / K3 / K7 / K8 / K9 / M1 / M2 原先把 `year`（ComputedRef 对象本身）当年度实参传给 `listAttachedVouchers` / `pullSamplesForWorkpaper` ⇒ 改 `year.value`；K3 / K5 / K7 用 `ElMessage` 却没导入（`vite.config` 的 AutoImport 只挂 vue / vue-router / pinia）⇒ 运行时 ReferenceError，已补导入；I3 / I4 / I5 定向检查年度为空时，按日期年份推断的代理行不计入本期借方（原先 null 当「不过滤」，把全部历史原值算成本期新增）；D4 附注（6）剩余履约义务表头原先 `?? 2025`（两张披露页都没传年度 ⇒ 表头恒为 2026 / 2027），改为传 `auditYear` + `section6Rows`，年度为空不推该表。
- 视图：报表 / 试算表 / 调整分录 / 交付中心 / 审计报告 / 现金流量表 / 错报 / 合伙人签字 / 账表穿透 / 导入历史 / 合并页入口门控。年度只取路由的页（审计报告、现金流量表、错报）改为「路由年度 ?? 项目审计年度」并加 `yearResolved`（问完项目年度前不显示「未设置」，免得加载时闪一下）。试算表的冻结状态、余额表 / 映射完成率检测与工作流进度条在年度为空时不再发请求（浏览器实测原先在无年度项目上各回一次 422）。路由 query 里 `String(year)` 年度为空时不带 year（原先带成 `year=null`）。
- 字面量年度兜底（`?? 2025` / `|| 2025` / `= 2025` / `ref(2025)`）与今年兜底同类，一并清掉；`auditYearLiteralFallbackGuard.spec.ts` 守住，唯一豁免是 `buildD4ObligationColumns` 的零参默认值（覆盖率扫描用）。
- 候选树：HEAD 干净检出 + 本 spec 文件。混有并发会话改动的 7 个文件（合并页、eventBus、D2 附注披露体、auditPlatformApi、附注编辑页、附注公式弹窗、`trial_balance_service.py`）按 `git diff -U0` 逐 hunk 挑本 spec 的那部分复放；R1 清单补登记漏掉的 8 个文件（G9 / G10 / G11 / G14 取数解析、I2 开发支出主入口、试算表行类型用例、G11 收益率余额映射用例）。
- 收尾回归里补的（全量 vitest / 后端选集与 HEAD 逐条比对抓到）：
  - 运行时上下文 `WorkpaperRuntimeContext.year` 按实际口径声明为 `number | null | undefined`：渲染器原样传项目年度（null）。先前为消类型错在调用处把 null 改成 undefined，撞了既有用例「缺少项目审计年度时不使用全局年度」（断言运行时拿到 null）⇒ 改在被调方放宽类型；H10 检查页 prop 随之放宽。
  - 报表页行数上限 1950（门禁 1949），加年度门控后到 1965 ⇒ 附注就绪章节取数抽到 `useReportData.fetchNoteSectionsWithData`（年度为空不请求，失败返回 null 由调用方保留原值，配用例），回到 1943。
  - 单一入口补漏 3 处（tasks 5.7）：G6 审定表 / E0 品种矩阵的 `/api/trial-balance/query`、附注公式弹窗的 `/api/trial-balance/`，后端都没有这些路由。
  - 既有用例按新语义改写：`test_generate_from_codes_endpoint` 的 D2-5 原断言「表头填不上、回执报外部链接」，R3 之后表头能填上 ⇒ 改为断言活动页表头有项目名、回执不报；G 循环红基线两家 TB 只读引用的代码计数 1 → 0（读路径仍在，换了入口）。
  - 截止测试抽样 / 挂凭列表补用例（`r2AuditYearNullComposables.spec.ts`）。

### 3.2 项目 store 年度空值化（tasks 6.5，2026-10-27 用户拍板「先根治初始值是去年」）

- 现状（6.3 浏览器实测）：`stores/project.ts` 的 `year` 初值是去年，换到没填审计年度的项目时不清空、沿用上一个项目的年度；`currentProjectContext.year` 声明为 `number`。下游 `DefaultLayout`（待重算详情跳转、全量重算）与 `useStaleStatus`（重算）在 store 年度之后又兜底去年；切项目 `handleProjectSwitch` 把当前项目的年度带给目标项目。
- store：`year: number | null`（初值 null）+ `yearStatus: 'idle' | 'loading' | 'ready' | 'failed'`。`syncFromRoute`：非项目页 ⇒ null / idle；换项目时路由带年度 ⇒ 用路由年度、ready；不带 ⇒ 先置 null + loading，取到项目信息后 = 项目审计年度（没填为 null）+ ready，取失败 ⇒ failed（与「没填」分开）。取项目信息不参与 GET 去重（`_dedupe:false`，免得被同址 GET 取消；并发会话 R16 已把 `getProject` 改走 apiProxy 共享同址在途请求，本 spec 的选项在其上保留，apiProxy 的共享键区分是否参与去重）；期间又换了项目 ⇒ 丢弃旧响应（序号）。同项目、路由不带年度 ⇒ 保持当前年度。`retryProjectContext()` 供重试；`loadProjectContext` 同口径；`yearOptions` 的日历年是下拉选项，进日历豁免表。
- 挂载时序：DefaultLayout 路由内容区套 `ProjectContextGate`：项目页 loading ⇒「正在读取项目信息…」，failed ⇒「读取项目信息失败」+ 重试，都不渲染页面 ⇒ 页面挂载时拿到的就是本项目的最终年度（或 null），不会先按上一个项目 / 去年取数。页面本就按 `fullPath` 重挂；页内切年度仍走 `changeYear` / `year:changed`，不变。
- 否决：路由守卫里 await 项目信息（http 超时 180 秒会卡住导航，守卫原注释明确不等 API）；`useAuditContext` 加监听 store 年度（与订阅 `year:changed` 的页面重复取数，GET 去重会取消前一次）；保留去年初值、只在页面里加门控（6.3 已证明门控碰不到 null）。
- 附注编辑页（3265 行 = HARD_CAP，全程按年度取数）：路由改挂壳 `DisclosureEditorRoute.vue`，年度 = 路由 → store，没有就整页提示、不挂编辑页；编辑页里的年度仍同步读「路由 → store」，壳传入的 `auditYear` 只作离开项目那一刻的兜底（类型因此是 `number`）。否决只用 prop：父组件重渲染前 prop 还是旧值，信息栏切年度后紧接着的 `fetchTree()` 会取到上一年（浏览器实测切年度时排查出来；改后信息栏切 2024 立即按 2024 取）。
- 同类日历兜底一并清（前端棘轮基线清零，只剩日历豁免）：`useStaleStatus` / `DefaultLayout` 重算缺年度提示不发、跳转缺年度不带；`usePenetrate` / `ThreeColumnLayout` 年度 = 路由 → store，缺则不带（`GtRefreshScopeDialog` 缺年度不打开、`CustomQueryDialog` prop 放宽）；`useFCycleEditor` F2 计价抽样原先恒用今年，改用项目年度、缺则提示不发；`useEditorSave` / `useStaleImpact` 缺年度不发影响分析；drilldown store 初值 null、缺年度不取数；`useBatchQuery` / `consolidationApi` 两个无调用方的函数年度改必填 / 解析不到不请求；`useWorkpaperListContext` 测试桩默认 null。

## 4. R3 / R4 表头填写

### 4.1 只改目标格：`services/xlsx_cell_patch.py`

`patch_cells(path, edits)`；`edits: [{sheet, cell, value | formula, cached}]`。

- 读 `xl/workbook.xml` + rels 定位页签对应的 sheet XML；只重写含目标格的 sheet XML，其余 zip 条目原字节拷贝（压缩方式沿用）。
- 文本：`<c r s t="inlineStr"><is><t xml:space="preserve">…</t></is></c>`，保留 `s`；公式：`<f>` 改写 + `<v>` 写新缓存值、`t="str"`。
- 目标格不存在 ⇒ 按列序插入 `<c>`（行不存在按行序插入 `<row>`，超出 `spans` 删 `spans`）。
- 共享公式 / 数组公式格不改，返回 `skipped`（调用方写进回执原因）。
- 删掉了公式（外部引用改静态文字）⇒ 删 `calcChain.xml` 及其 rel / content type（Excel 重建；残留条目指向非公式格会触发修复提示）。不设 `fullCalcOnLoad`（避免打开时更新外部链接的提示）。

否决：openpyxl 存后再把 extLst 塞回（数据验证之外还丢缓存值、条件格式扩展、自定义 XML，补不全）；改模板库文件本身（模板是运行时权威源、只读守卫在守）；删外部链接部件（其余格的 `[N]` 序号随之错位）。

### 4.2 外部引用归类（`wp_header_service._resolve_external_header_refs`）

对每页表头区（前 10 行 × 12 列）的 `=[N]页签!格` 单格引用，按 data_only 缓存值：

| 缓存值 | 本册有同名页签且该格同一标签（或缓存为空且该格是表头标签） | 否则 |
|---|---|---|
| 表头标签 `标签：…`（标签在已知表头标签内） | 改本册引用 `=页签!格`，目标格并入表头填写 | 静态 `标签：`（客户 / 期间 / 截止日 / 编制人 / 复核人 / 两个日期去掉示例），随后按标签填值 |
| 底稿索引号（`F2-18`） | —— | 静态文字原值 |
| 空 | 改本册引用 | 不动 |
| 其他文字 / 数字 / 复合公式 | 不动 | 不动 |

改写后的格与「本册单格引用指向被改格」的格（各页表头区，最多跟 3 层）一并写新缓存值。

### 4.3 填写流程

openpyxl 只读规划（`_fill_workbook_header` 改为返回带新值的编辑清单，外部引用归类先于标签填写）→ `patch_cells` 落盘。`.xlsx` / `.xlsm` 走同一路径；`is_custom` 与空白底稿标准布局仍用 openpyxl 存（它们本就由 openpyxl 生成）。`_unfillable_external_header` 改为「仍有未处理的表头标签外部引用（如共享公式跳过）」才报。

### 4.4 验证

- 单测：补丁器（插格 / 插行 / 公式改写 / 共享公式跳过 / calcChain 删除 / 其他条目字节相同）、归类各分支、`.xlsm` 宏保留。
- 全量模板扫描（368 个）：复制后填写，比对 x14 数据验证条数、`vbaProject.bin`、非目标 sheet XML 字节、表头外部标签引用数（应为 0）、数据区外部引用数（不变）；Excel 兼容用 LibreOffice 无头转换不报错 + openpyxl 可读回。

## 5. R5 开发服务器缓存

`vite.config.ts` 加 `cacheDir: '.vite'`（相对前端根，`.gitignore` 已有 `.vite/`；`vitest.config.ts` 不继承 vite 配置，不受影响）。改配置 Vite 自行重启并重建预构建；不杀开发服务器进程（并发会话在用）。验证：`.vite/deps/_metadata.json` 生成、en-gb 分块 200、打开 Univer 底稿无 504。

## 6. 范围外（登记不改）

- 数据区外部链接（如 F2 附注披露信息 13 个复合公式、A3-8 数据格）仍显示缓存值：属模板跨文件拆分遗留，需模板侧决定。
- `trial-balance` v1 残留响应形状 `{data, warning}`：前端已统一解包，端点形状另议。
- 🔴「完整Excel / 在线编辑」打开的是按项目从**模板**复制的在线编辑副本（`wp_onlyoffice_router._resolve_wp_file`：缓存不存在时 `shutil.copy2(模板)`），不是 `working_paper.file_path` 的生成文件 ⇒ 在线编辑里表头恒为模板占位（如 F2 底稿目录「截止日：202X年12月21日」），与项目、模板无关；本 spec 修的是生成文件那条线（3.5 实测）。在线编辑副本是工作底稿同步框架的表示层（`wpsync-*` 文档键、冻结契约身份），首建时补表头要与在途的 `oo-writeback-template-parity-closure` 一起定，另议。
- 🔴 I6 研发费用审定数发布到 `6602`：`useI6Adjudication` 的发布科目与 `useI6FormData` 取数科目都是 `6602`（标准科目表里是**管理费用**，研发费用是 `6604`；主入口 `GtI6` 取数已用 `6604`）。发布门 `publish-to-tb` 的「前端预算行」路径不校验科目是否属本底稿 ⇒ 点发布会把研发费用审定数写进管理费用。已在 `cycleWrongLegacyAccountCodes.spec.ts` 棘轮里登记为待决（I6 基线 69），本 spec 只迁移取数入口、科目不动。
- I2 `1717`（开发支出应为 `1704`）、I5 `1911`（无标准独立码）同为上述棘轮登记的待决错码；本 spec 迁移时不新增出现处（迁移首版把 `ACCOUNT_CODE_1717` / `ACCOUNT_CODE_1911` 摊进多行，棘轮打红 63 > 60、57 > 55；改为先取局部常量再用，棘轮转绿）。
- 🔴 项目 store 的 `year` 初值是 `new Date().getFullYear() - 1`（今年兜底棘轮基线 `stores/project.ts` 1 处），切到没填审计年度的项目时不清空 ⇒ 读 `projectStore.year` 的地方（交付中心、附注编辑页、项目仪表盘、`useAuditContext` 的全部消费方）在无年度项目上照样按 2025 取数，本 spec 在这些地方加的空值门控碰不到 null。浏览器实测（无年度项目 `fc5b15fd`）：交付中心请求 `completeness?year=2025` 回 500、附注编辑页取 `/disclosure-notes/{pid}/2025` 回 404。根治要把 store 的 `year` 改成 `number | null` 并在切项目时清空，但页面多在 store 解析出年度之前就挂载取数，且 `useAuditContext.onContextChange` 只盯路由与准则、不盯 store 年度 ⇒ 改了以后不监听年度的页会停在空白（tasks 6.5；2026-10-27 用户拍板根治，做法见 §3.2：年度定下来之前不挂载页面）。
- 合并页一键刷新后的附注重读恒判「已切换」：`reloadNoteForRefresh` 传给 `ConsolNoteTab.reloadCurrentSectionAfterRefresh` 的冻结上下文缺 `variant`，`sameNoteContext` 比较 `variant`（undefined ≠ soe / listed）⇒ 每次都 stale，刷新后附注从未真的重读；`213f19816` / HEAD 同有（TS2345，基线就有）。
- 并发会话未提交的 `ConsolCatalog.loadProjectStandard` 挂载时发与合并页 `loadProjectInfo` 同址同参的 `GET /api/projects/{pid}` ⇒ http GET 去重取消合并页那一次 ⇒ `projectInfoLoaded` 恒 false、信息栏年度「请选择」、合并工作底稿页空白（【测试】公式同步集团 `3a3930db` 两次重载均复现，XHR 打桩看到合并页那次根本没发出；手动重跑 `loadProjectInfo` 即恢复）。修法：新调用带 `_dedupe: false`，或改读合并页广播的口径。
- 账表穿透页年度只取路由：无年度项目上余额表请求不带年度 ⇒ 后端 422（静默），页面显示「暂无账套数据，请先导入账套」而不是「未设置审计年度」；有年度的项目靠后端按项目年度取，行为正确。
- 调整分录页模板引用未定义的 `loadEntries`（TS2339，HEAD 即有）；`d4FourTableWiring.spec.ts` 11 例在 HEAD 即红（`D4TabExport.vue` / `useD4InspectionWriteback.ts` 写死 `6001`）；`noteDisclosureJump.ts` 的 wpCode 联合类型 11 处（HEAD 相对基线新增）—— 均非年度问题，登记不改。
- 全量 vitest 五轮比对时偶发红的 PBT 共 12 次、10 个性质（前两轮候选 5 次、HEAD 1 次；6.5 之后第三轮候选 `transposeGrid` Property 10、HEAD `useG6EclFormulaEngine` P6 各 1 次；终版暂存树那轮候选 `transposeGrid` Property 10 又 1 次；重放到新 HEAD `083f5e774` 那轮候选 `DefaultLayoutNavigation` 的 `tabToRoute`、`a81OtherInfoRepresentation` Property 3，HEAD `a173ConsultationRecord` Property 2 各 1 次）：按失败那次的种子在候选树与 HEAD 树各复跑一次，都红在同一反例上 ⇒ 与本 spec 无关，属用例或被测函数自身的边界问题。另有 1 次非 PBT 的随机红：HEAD 那轮 `e1SyncEntryRowIdentity` Property 23 ③ 断言新增行 id 不以 3 / 4 结尾，而 id 带时间戳随机尾号。六条看得出是用例写法：`DefaultLayoutNavigation` 测的是用例里自带的 `tabToRoute` 副本，`map[tab] || 默认值` 遇到生成器给的 `"valueOf"` 取到原型方法（种子 -1431292672）；`a81OtherInfoRepresentation` / `a173ConsultationRecord` 的增删一致性生成器会给纯空白值，被实现裁掉后长度不符（种子 -1065829984 / -703104387，反例都是 `[{"type":"add","value":" "}]`）；`n1DisclosurePrefillAndBranch` Property 4 生成器会出 `-0`，经 JSON 存取变成 `0`，`toBe`（Object.is）判不等（种子 -1364814347，反例 `[-0, 0]`）；`guidanceBar` Property 5 用 `text()`（会去首尾空白）比原文，原文带尾空格即不等（种子 1088896932，反例 `"! "`）；`transposeGrid` Property 10「纯函数：不修改入参」拿 `JSON.parse(JSON.stringify(grid))` 当快照再 `toEqual`，JSON 把 `-0` 变 `0`、`Infinity` 变 `null` ⇒ 生成器出这两个值即判「入参被改」（种子 -1064356007 反例含 `Number.POSITIVE_INFINITY`、1825878124 反例含 `-0`）。其余四个性质未定位：`g7AuxExtraction` Property 2（种子 -2054566208，两行同名「乙」金额 0.01 与 0.010000000000000002）、`useA38Goodwill` Property 5（种子 -893553447，账面价值 5e-324）、`useG6EclFormulaEngine` P6（种子 1153914608 / 1768957403，两次的反例都是列头为空格）、`workpaperSyncBridgeMachine` Property 46（种子 694779836，从 `recovery_download_only` 经 reset → 恢复认领 → `close_successor_applied` → `flush_started` 走到 applied —— 可能是状态机真缺陷，也可能是判据没放 reset，需该 spec 判定）。
- `FrontendReferenceIntegrity`「已登记的死代码文件确实零活消费方」单条约 15 s，贴着 vitest 的 15 s 超时：6.5 之后第三轮全量并行时候选那次 15.26 s 超时、HEAD 那次 14.79 s 通过，单独复跑 9.0 s / 6.5 s 通过 ⇒ 用例自身耗时问题，登记不改；同文件「不存在未登记的坏 import」两边都红（HEAD 的 `components.d.ts` 登记了 4 个已不存在的 `_test_*` 临时组件）。
- 主工作树 `utils/eventBus.ts` 曾经陈旧：移植提交（`97b3534c2` 等）加的 N4 `expense:taxes-surcharges-updated`、N5 `effectiveTaxRate: number | null`、`disclosure:refresh.source` 没进主工作树文件（提交走的独立索引）⇒ 已按提交内容补回工作树（与 HEAD 一致，不动并发会话的改动）。
