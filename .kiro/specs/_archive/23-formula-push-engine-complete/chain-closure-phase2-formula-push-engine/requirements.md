# 需求：全链条闭环 · 阶段二（公式推送引擎 + 货币资金 E1 全链 canary）

## 背景

用户诉求（2026-09-28，原话）：四表库项目数据入库后，自动通过公式管理模块刷新到试算表未审数、
底稿明细表/披露表/审定表；项目组确认调整分录后，自动推送到底稿审定表和披露表、报表审定数、
试算表审计调整、调整分录大厅；披露表按国企或上市推送到附注科目数据。**推送都经公式管理模块。**

上游：`chain-closure-phase1-root-cause-fixes`（R3 报表准则 / R4 financial_report stale 已在 HEAD；
R1/R2 在工作树未提交）。本会话已另修三个断点（v2 入库不发激活事件 / year 缺失静默跳过 /
auto_map 失败不可见）与委派缓存缺口，见 `#dev-history` 2026-09-29。

## 现状实证（2026-09-29，全部现读或真库现查；数字均标口径，禁写死到判据）

| 段 | 判定 | 证据（口径） |
|---|---|---|
| ① 四表→试算表未审数 | 绿 | 阶段一真库实测 + 本会话断点 1/2/3 修复 |
| ②③ 四表→底稿明细/审定 | 红 | 专用组件只在**打开底稿且键缺失**时种子一次（`GtE1MonetaryFund` onMounted `!allResponses.has(...)`）；重新导入后既有值永不刷新；全仓无事件驱动的底稿写入 |
| ④ 四表→底稿披露 | 红 | 披露数由前端从审定表键实时派生，源头不刷新则永远旧 |
| ⑤⑥ 调整→底稿审定/披露 | 红 | E1-1「账项调整」只读底稿自己的调整页（`E1-adjustment-by-item-*` ← E1-5），调整分录大厅已批准分录不进审定表（即阶段一「冲突⑤」） |
| ⑦ →报表审定数 | 绿 | 阶段一 R3（`on_trial_balance_updated` 传真实准则）已在 HEAD |
| ⑧ →试算表审计调整 | 绿 | `adjustment_approved_recalc_handler` |
| ⑨ →调整分录大厅 | 绿 | 大厅本身即权威（`GET adjustments/summary` 查询即得），无需推送 |
| ⑩ 披露表→附注 | 部分 | 仅底稿页打开且数据变化时前端防抖推送；附注中 `_source=workpaper` 的章节 **341** 个，其中**从未真正同步**（`last_sync_wp_id IS NULL` 且无 `_last_sync_wp_id`）**261** 个，被模板刷新**永久跳过** |
| ⑪ 经公式管理推送 | 红 | 运行时流水线端到端空转（见下表） |

公式运行时现状（⑪ 的拆解）：

| 环节 | 现状 |
|---|---|
| 公式定义 | `wp_formula` 真库 **2 行**（均为和平物流测试行）；coordinator 只读这张表 |
| 目标定位 | coordinator 对所有域统一构造 `{wp_id,item=sheet_name,cell}`，与 report/note/adjudication 三个 adapter 的 locator 契约**全不匹配** ⇒ `prepare_many` 抛错走降级 |
| 写入 | `DraftRefreshService.refresh` 只写 `draft_marker`（真库 **0 行**）不写业务值；唯一调 `apply_many` 的 `execute_refresh` **0 调用方** |
| 底稿 adapter | `WorkpaperMutationAdapter` 的 UPSERT 缺 `project_id`；真 PG 实测（一次性 schema）**已存在行与新行两种情况都抛 `NotNullViolation`**；其单测用的 SQLite 表 `project_id` 可空 ⇒ 假绿 |

补充实证（均为本轮现查，口径随行给出）：

| 编号 | 事实 | 口径 / 证据 |
|---|---|---|
| F1 | E1 真实数据集中在 4 个项目；`重药控股安徽_2025` E1 底稿 25 个条目，含 `E1-cash-detail-rows`（种子行 `fixed-rmb`）、`E1-bank-detail-rows`（3 行 `-ft-`）与**已落库**的 `E1-cash-detail-total-unaudited=376.73`；银行汇总键**未落库**（只存了行） | `checklist_responses` 按 wp_id 现查 |
| F2 | 同一张 E1-1 上，现金未审数读落库值（重导入后不刷新），银行未审数读每次打开时的四表种子（会刷新）——**同表两行刷新语义不同** | `GtE1MonetaryFund.seedFromFourTable` 仅在键缺失时种子 |
| F3 | E1-1 模板「试算平衡表数」行（R20/R38）**无公式**，差异数 `D21=D18−D20`、`G21=G18−G20` 位于**审定数列** ⇒ 该行语义是试算表**审定数**；现渲染种子 `project_context.tb_amount` 取四表叶子**未审**合计 | openpyxl 直读 `E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx` |
| F4 | E1-1「账项调整」列只读底稿调整页 E1-5 的 `E1-adjustment-by-item-*`；调整分录大厅直接录入并已批准的分录**不进审定表** | `useE1Adjudication.getAdjustment` |
| F5 | 试算表调整列口径**排除** `origin='workpaper'`（防与审定表发布门双计）；大厅真库当前 **0** 笔未删除分录 | `adjustment_amount_source` 口径矩阵 + 真库 |
| F6 | 附注三种 `table_data` 形态：F1 顶层 `rows/values/_cell_modes`（模板生成，由既有 refill 按试算表审定数维护）；F2 `sub_table_data{表:[{label,end_amount,prior_amount}]}`（底稿同步产物）；F3 `sub_table_data{表:[{label,values,_cell_meta,_cell_modes}]}`（历史迁移脚本产物，`_source` 被置为 workpaper） | 真库 `五、1/八、1` 逐节现查 |
| F7 | `宜宾_2025 八、1` 为 F2 且标签是旧字面「现金」（非「库存现金」），数值全 0 而试算表 1002=110.30 ⇒ 曾把空底稿同步到附注 | 真库 |
| F8 | `pull-from-workpapers`（附注生成/刷新前必调）会把**从未同步过**的章节也打上 `_source=workpaper` ⇒ 这些章节此后被模板刷新永久跳过；该端点 HEAD 前一直 500（漏 import），**修复后一上线就会批量扩大死区** | `disclosure_notes.py::pull_from_workpapers` + 前端 2 处调用 |
| F9 | 全仓 `INSERT INTO checklist_responses` **93** 处，缺 `project_id` **51** 处、写不存在列（`value`/`status`/`content`）**7** 处，分布 **39** 个文件；真 PG 缺 `project_id` 必失败（见上表） | 探针 `_cr_insert_probe.py`（f-string 占位列另计 5 处，需运行时判定） |
| F10 | 试算表存在陈旧数据：`重庆和平药房_2025` 1012 试算表未审 8,280,881.84 = 叶子合计 4,140,440.92 的 **2 倍**（最后重算 06-08，早于叶子修复）；`四川物流` 1002 叶子 4,048.93 而试算表 0（未映射） | 探针 `_leaf_vs_tb_probe.py` |
| F11 | 附注模块按 `projects.template_type` 取准则；`重药控股安徽` `template_type=listed` 而 `applicable_standard_v2.entity_type=soe`，五、/八、章节并存（78/92） | 真库 |

## 需求

### 需求 1：推送规则登记在公式管理，可见可控

**用户故事**：作为审计人员，我要在公式管理里看到「哪个底稿单元格由什么公式、在什么事件后自动推送」，并能对有差异的单元格决定采用或保留。

#### 验收标准
1. THE 推送规则 SHALL 以声明式清单登记（目标地址 + 来源公式 + 写入策略 + 触发事件），E1 全部规则可经只读端点列出。
2. THE 目标地址 SHALL 使用 ACNR 底稿域 addr_id 形态 `{wp_code}/{sheet_code}/{coordinate}`，coordinate 由「条目 id + 行选择器 + 字段」组成，禁止新造第二套地址语法。
3. 系统值规则（试算平衡表数、大厅已确认调整）SHALL 经公式内核 `formula_engine.execute` 求值；规则表达式 SHALL NOT 使用内核里语义不唯一的列名（`未审数` / `期末余额` 与 `审定数` 同指一列），由守卫测试钉死。
4. 公式管理弹窗 SHALL 新增「公式推送」入口：规则表、最近一次推送统计、待处理差异清单（当前值 / 公式值 / 状态）、「立即推送」「采用公式值」「保持并锁定」操作；界面文本全中文。

### 需求 2：事件驱动的真实写入（不是只打标记）

#### 验收标准
1. WHEN `TRIAL_BALANCE_UPDATED` 到达（覆盖四表入库重算与调整分录审批重算两条来路）THEN 系统 SHALL 对该项目该年度的 E1 底稿执行推送，写入**业务值**本身。
2. WHEN E1 底稿保存（`WORKPAPER_SAVED` 且 `wp_code=E1`）THEN 系统 SHALL 重算派生值并推送附注；推送引擎自身写入 SHALL NOT 再发布 `WORKPAPER_SAVED`（防回环）。
3. THE 手动入口 SHALL 为项目级「编辑」权限；端点 SHALL 有 TestClient 真请求测试（含无权限用户被拒）。
4. 写入 `checklist_responses` SHALL 带 `project_id`、推进 `content_version`、刷新 `updated_at`，并按 `updated_at` 做乐观锁；并发改动时该条目跳过并如实记为「并发修改」，不覆盖。
5. 底稿处于「复核通过 / 已归档」时 SHALL 跳过并记原因，不改冻结底稿。
6. 每次推送 SHALL 落一条运行记录（触发来源、各类计数、目标级明细），并广播 `formula.pushed` SSE。

### 需求 3：三态覆盖规则（自动覆盖 / 人工保留 / 锁定保留）

#### 验收标准
1. 系统值（用户界面不可编辑的单元格）与派生值（由明细行按固定算式得出）SHALL 每次按公式值写入。
2. 可编辑值 SHALL 按「上次推送值」判定：当前值仍等于上次推送值 ⇒ 视为自动，覆盖为新值；当前值 ≠ 上次推送值且 ≠ 新值 ⇒ 视为人工修改，保留并记录差异。
3. 首次推送遇到来源不明的已有值：为空 ⇒ 写入；等于新值 ⇒ 静默采纳；不等 ⇒ 记为「待确认」，保留当前值并展示差异，SHALL NOT 静默覆盖。
4. 用户锁定的目标 SHALL 永不覆盖，差异照常展示；「采用公式值」SHALL 把最近一次公式值写入并转为自动。
5. 附注单元格的三态 SHALL 以附注自身标记为准：`_cell_modes` 为 `manual`/`locked` 或章节 `_manual_override=True` 时保留；底稿同步写入不视为人工修改。

### 需求 4：E1 全链闭环（canary）

#### 验收标准
1. 四表 → 明细表：已落库的四表种子行（`fixed-rmb` / `cash-ft-*` / `bank-principal-*-ft-*`）SHALL 按四表叶子刷新「期初 / 本期增加 / 本期减少」；人工新增行与用户字段（汇率、调整、备注、银行名等）SHALL NOT 被改；四表新增叶子 SHALL NOT 由后端自建行（种子口径由前端决定账户级或叶子级），而是在报告中列出；明细条目不存在时 SHALL NOT 创建。
2. 明细 → 审定表未审数：各跨表汇总键 SHALL 由（推送后的）明细行按与前端逐式一致的算式重算，前后端一致性由双侧共享夹具守卫。
3. 试算平衡表数 SHALL 为试算表审定数（期末 = Σ 审定数，期初 = Σ 年初余额，科目 1001/1002/1012），对齐模板差异数位于审定列的语义（F3）。
4. 调整分录审批 → 审定表：大厅已批准、**非底稿来源**的 AJE SHALL 按科目 1001/1002/1012 推入审定表对应主行的账项调整，与 E1-5 本地调整相加；底稿来源分录 SHALL NOT 重复计入（它们已在 E1-5）。
5. 审定合计键 `E1-adj-total-*` SHALL 由后端按前端同式派生并持久化，供披露表与附注读取；前端 SHALL NOT 再以「先持久化优先」回放陈旧审定合计，且保存时 SHALL NOT 回写后端独占的系统值与派生值。
6. 披露表 → 附注：按附注模块同一准则权威（`template_type`：上市 → 五、1，国企 → 八、1）把「库存现金 / 银行存款 / 其他货币资金 / 合计」的期末与期初数写入附注主表；「存放财务公司款项 / 数字货币」按前端同式扣减；期初手工覆盖项 SHALL 保留；章节不存在 SHALL 跳过并报告；由模板取数维护的 F1 章节 SHALL NOT 被推送改写。
7. 用户已打开该底稿时，SHALL 以提示条告知「后台已更新 N 项」并提供「载入最新数据」，SHALL NOT 静默替换未保存的编辑。

### 需求 5：堵住附注死区扩大（F8）

#### 验收标准
1. `pull-from-workpapers` SHALL 只给**真正同步过**的章节（`last_sync_wp_id` 非空或 `table_data._last_sync_wp_id` 存在）刷新标记；从未同步的章节 SHALL NOT 被打上 `_source=workpaper`，并在返回值中计入 `skipped_never_synced`。
2. SHALL 有端点级测试覆盖「已同步章节被标记 / 未同步章节保持原样」两向。

### 需求 6：修复运行时底稿写入适配器并冻结同类缺陷（F9）

#### 验收标准
1. `WorkpaperMutationAdapter` 的 UPSERT SHALL 带 `project_id`；其测试建表 SHALL 与真库约束一致（`project_id NOT NULL`），修复前该测试 SHALL 打红。
2. SHALL 新增全仓静态守卫：统计 `INSERT INTO checklist_responses` 缺 `project_id` / 写不存在列的站点，现值冻结为基线且只许下降；清单列出站点；本 spec 不改他域文件（跨 39 个文件、多数有他人未提交改动，另立 spec）。

### 需求 7：每项修复有变异证明（横切，沿用阶段一需求 5）

#### 验收标准
1. 每个判据 SHALL 有修复前会红的测试；「零 / 非零」类判据 SHALL 配反向样本。
2. 推送写入 SHALL 有真 PG 验证（一次性 schema，结束删除），SQLite 通过不作为 PG 行为的证据。
3. 真实项目验证 SHALL 以事务内试跑 + 回滚完成，真实数据写入须经用户确认。

## 非目标（明确排除，留后续 spec）

- E1 以外循环的推送规则（本 spec 只做 E1 canary，引擎按循环可扩展）。
- E1-3 账户级明细行（`-acct-`，来自辅助账银行账户维度）与 E1-4 数字货币行的推送：真库当前 0 项目有此类行，报告中如实列为「未纳入」。
- F3 迁移章节的通用刷新（261 个从未同步章节，23 个含非零数）：需改 refill 支持 `sub_table_data`，另立 spec。
- F9 其余 38 个文件的 `checklist_responses` 写入缺陷修复。
- F10 陈旧试算表：属数据重算问题，推送在下一次 `TRIAL_BALANCE_UPDATED`（重算后）自然纠正；差异数行会如实暴露。
- `audited_amount` 单列被发布门与重算争夺（阶段一冲突①）。
