# 任务 4.2 浏览器实测证据（同 3.3）

> 实测日期：2026-10-25。浏览器：Chrome DevTools page 2，`http://127.0.0.1:3030`，已登录 `admin`，隔离上下文 `pcfc-admin`。本批只读，不创建/修改项目、不写底稿、不执行 `--apply`。
>
> 结论：有年度链路通过；缺年度链路未通过验收，实际复现了年度兜底为 2025 且没有中文提示。任务 4.2 不能标记为通过，需由生产代码修复后重测。

## 验证数据

- 有年度项目：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，名称「重药控股安徽有限公司_2025」，项目详情 `audit_year=2025`。
  - 底稿入口：`0898d6e5-3388-4371-b9cc-034fa7e8b593`，`wp_code=D2-1`。
- 缺年度项目：`a070397b-34b7-4b57-b832-125c4bffceec`，名称 `proj_a6242abd`，项目详情 `audit_year=null`。
  - 底稿入口：`24924bd1-9aef-483d-8016-11ae5feaef6b`，`wp_code=D2`；其底稿内有「审定表D2-1」子页。
  - 该项目与底稿原已存在，列表查询显示可读，未进行任何写操作。

## 测试步骤与结果

### A. 有项目审计年度

1. 直接打开 A1 编辑入口：
   `http://127.0.0.1:3030/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/workpapers/e1f6ee4c-cff9-4da1-b6a0-f1a6310e6807/edit`
2. 页面实际显示「A1 程序表」「签发流转控制表」「索引号：A1」以及项目截止日 `2025-12-31`，读取链完成；未显示「未设置审计年度」。
3. 另打开同一有年度项目的 D2-1 入口并点击「💰 审定表D2-1」子页。其 render-config 和年度取数请求均按 2025 返回成功；该次共享 Vite 会话在动态导入 `en-gb-*.js` 时出现 504，导致 D2-1 表体未稳定保留在最后快照，但不影响已抓到的后端读取结果。
4. render-config 返回 `audit_year=2025`，D2-1 `project_context.audit_year="2025"`、`bs_date="2025-12-31"`。

实际结果：年度来源和读取链通过；有年度项目按项目年度读取，不使用当前日历年份。A1 页面实际渲染通过；D2-1 的页面级复测受共享 Vite 动态导入 504 干扰，已单独登记为环境噪声，不能当作业务通过证据。

网络证据（Chrome DevTools request id）：

- `5678` `GET /api/workpapers/0898d6e5-3388-4371-b9cc-034fa7e8b593/render-config` → **200**，响应 `data.audit_year=2025`。
- `5797` `GET /api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/trial-balance?year=2025` → **200**，返回含 `1122 应收账款` 的试算表数据。
- `5808` `GET /api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/adjustments?year=2025&page_size=200` → **200**，返回 5 条调整分录。
- `5742` `GET /api/workpapers/0898d6e5-3388-4371-b9cc-034fa7e8b593/guidance?sheet_name=审定表D2-1` → **200**。
- A1 入口同批实际请求 `GET /api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/procedure-tables/A1?year=2025&resolver=review_dashboard_status` → **200**。

### B. 未设置项目审计年度

1. 直接打开：
   `http://127.0.0.1:3030/projects/a070397b-34b7-4b57-b832-125c4bffceec/workpapers/24924bd1-9aef-483d-8016-11ae5feaef6b/edit`
2. 页面显示 D2 底稿目录；点击「💰 审定表D2-1」子页。
3. 页面继续显示完整的「应收账款审定表 D2-1」结构和输入区，未显示「未设置审计年度」或「请先在项目基本信息中填写」中文提示。
4. 页面文本探针结果：`hasMissingYearText=false`、`hasPrompt=false`。
5. 项目 `GET /ledger/years` 返回 `years=[]`、`sibling_years=[]`，render-config 明确返回 `audit_year=null`；D2-1 的 `project_context.audit_year=""`、`bs_date=""`。

实际结果：**失败 / 阻塞**。缺年度页面没有按 R3.3 / 任务 4.2 进入中文空态，也没有阻止年度依赖读取；反而按 2025 发出了年度请求。

网络证据（Chrome DevTools request id）：

- `4509` `GET /api/workpapers/24924bd1-9aef-483d-8016-11ae5feaef6b/render-config` → **200**，响应 `data.audit_year=null`，D2-1 `project_context.audit_year=""`。
- `4520` `GET /api/projects/a070397b-34b7-4b57-b832-125c4bffceec/ledger/years` → **200**，响应 `years=[]`、`sibling_years=[]`。
- `4630` `GET /api/projects/a070397b-34b7-4b57-b832-125c4bffceec/adjustments?year=2025&page_size=200` → **200**，响应为空列表；该请求的 `year=2025` 是错误的日历/默认年度兜底证据。
- 页面同批还请求了 `GET /api/workpapers/24924bd1-9aef-483d-8016-11ae5feaef6b/checklist-responses`（无 `year` 参数）；不能抵消已确认的错误年度请求。

## 控制台证据

- 缺年度 D2-1 实测期间未出现缺年度提示，也未出现由年度校验主动抛出的前端 error；主要是既有 Element Plus/Vue transition directive warning，以及 render-config 慢请求 warning。
- 有年度 D2-1 实测期间主要是同类既有 Vue warning；另有一次浏览器环境的 `504 Outdated Optimize Dep` / 动态导入失败，重试后读取链请求仍返回 200，和年度选择无关。
- 不能将这些既有 warning 当作通过依据；决定任务结果的是缺年度页面探针和 `adjustments?year=2025` 网络证据。

## 修改文件与阻塞项

- 修改文件：仅新增本证据文件 `evidence/read-batch-4.2.md`；未修改生产代码、测试代码、任务清单或数据库。
- 阻塞项：任务要求的缺年度行为当前未满足。需要修复底稿 D~N 读取入口的年度来源/空态门控，至少阻止缺年度项目发出 `adjustments?year=2025`，并显示「未设置审计年度，请先在项目基本信息中填写」中文提示；修复后重新执行本批 A/B 对照。


## 修复后复测与根因收口（2026-10-25）

### 生产修复

上次失败的根因不是测试口径，而是年度兜底链路：`GtWpRenderer.vue` 的 `preparationYear` 在 `render-config.audit_year=null` 时读取 `useProjectStore().year`。该 store 年度是可切换 UI 状态，初始化为当前年减一；缺年度项目因此被静默解析成 2025，年度组件随即挂载并发出 `adjustments?year=2025` / `trial-balance?year=2025`。

本次修复：

- `WorkpaperEditor.vue`：HTML 渲染器、Univer 编辑器、`WpGuidancePanel`、`CycleDialogHost`、`WorkpaperSidePanel`、非 HTML 版本 Host 均以项目 API 返回的 `projectYear != null` 为挂载门；项目年度请求完成前显示中文读取态，确认缺失后显示「未设置审计年度 / 请先在项目基本信息中填写审计年度」。HTML 渲染器接收同一 `auditYear`。
- `GtWpRenderer.vue`：`preparationYear` 只认当前 render-config 的 `audit_year`，配置缺省时才回退父 Shell 传入的同项目年度；删除路由年度和 `useProjectStore().year` 的猜测兜底。年度缺失时不挂载注册表 HTML 子组件，改显示中文空态。
- `GtWpRenderer.runtime-boundary.test.ts`：增加回归用例，模拟 render-config 缺年度但全局 store 仍为 2025，断言运行时年度为 `null`、标准年度组件不挂载且空态文案可见。

### 修复后前端验证

- Vitest：`src/components/workpaper/GtWpRenderer.runtime-boundary.test.ts` + `src/utils/__tests__/resolveAuditYear.spec.ts`，**2 files / 9 tests passed**。
- ESLint：3 个改动文件 **0 errors**；4 条 warning 均为既有 `gt-audit/no-status-string-literal` 领域 warning。
- `get_diagnostics`：`WorkpaperEditor.vue`、`GtWpRenderer.vue`、`GtWpRenderer.runtime-boundary.test.ts` 均无诊断。
- 单区域 `vue-tsc` 已尝试，但仓库依赖图在 4GB 堆上仍 OOM（`FATAL ERROR: Reached heap limit`），因此不将类型检查记为通过；上述 Vitest/ESLint/编辑器诊断为实际验证证据。

### 浏览器复测

浏览器：Chrome DevTools page 2，`http://127.0.0.1:3030`，已登录 `admin`，隔离上下文 `pcfc-admin`。开发服务未由本次会话托管；对 3030 现有服务执行了忽略缓存的硬刷新，页面已加载本次生产代码。

#### A. 有年度项目（通过）

项目：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，重药控股安徽有限公司_2025，`audit_year=2025`；底稿：`0898d6e5-3388-4371-b9cc-034fa7e8b593`，D2-1。

- 页面显示「应收账款审定表 D2-1」、完整输入/审定结构和「截止日 2025-12-31」，未显示缺年度空态。
- 网络请求：`reqid=7598` `GET /api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/trial-balance?year=2025` → **200**；`reqid=7609` `GET /api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/adjustments?year=2025&page_size=200` → **200**；`reqid=7543` `GET /api/workpapers/0898d6e5-3388-4371-b9cc-034fa7e8b593/guidance?sheet_name=审定表D2-1` → **200**。
- 结论：有年度项目仍按项目年度正常读取，未回归到空态。

#### B. 缺年度项目 D2（通过）

项目：`a070397b-34b7-4b57-b832-125c4bffceec`，项目 API 返回 `audit_year=null`；底稿：`24924bd1-9aef-483d-8016-11ae5feaef6b`。

- 页面显示 uid 35_42「未设置审计年度」和 uid 35_43「请先在项目基本信息中填写审计年度，再打开底稿读取数据。」；未渲染 D2/D2-1 表格、工具栏或输入区。
- 该次完整请求批次中，`reqid=8213` `GET /api/workpapers/24924bd1-9aef-483d-8016-11ae5feaef6b/render-config` → **200**，但没有任何 `trial-balance?year=...`、`adjustments?year=...` 或 `/guidance` 请求。项目详情 `reqid=7705` 和 `reqid=7777` 均 → **200**，`ledger/years` `reqid=7776` → **200**；这些是项目上下文读取，不是年度业务取数。
- 控制台：无 error；仅既有 Element Plus/Vue transition/directive warning，以及一次 `ledger-import/active-job` 慢请求 warning。没有动态模块 504、未捕获 Promise 或年度相关错误。

#### C. 缺年度项目 D2-1 深链（通过）

在同一缺年度项目打开：
`/projects/a070397b-34b7-4b57-b832-125c4bffceec/workpapers/24924bd1-9aef-483d-8016-11ae5feaef6b/edit?sheet=审定表D2-1`

- 页面仍显示 uid 36_32「未设置审计年度」和 uid 36_33「请先在项目基本信息中填写审计年度，再打开底稿读取数据。」；没有因深链重新挂载 D2-1 子组件。
- 页面探针确认 `document.body.innerText` 包含「未设置审计年度」；复测期间没有 `trial-balance?year=...`、`adjustments?year=...` 或 `/guidance` 请求。
- 控制台无 error；仅既有 Vue warning 和 `ledger-import/active-job` 慢请求 warning。个别页面切换期间的项目初始化请求出现 `ERR_ABORTED/pending`，属于导航取消/后台轮询，不是年度依赖业务请求，也未影响空态显示。

### 任务结论

修复前 evidence 中记录的 `adjustments?year=2025` 缺陷已复现、定位并修复；修复后有年度与缺年度两条浏览器链路均符合要求。`tasks.md` 状态未修改。