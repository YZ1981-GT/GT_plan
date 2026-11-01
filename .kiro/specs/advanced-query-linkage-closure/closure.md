# advanced-query-linkage-closure 收口（closure.md）

本文件按 design §12 的要求写：逐条回显 §2 全部裁决（ADR-AQL-01~20）、§11 待拍板、跨 spec 待拍板，
写明「只做周末、不做节假日」的原因、§14.5 顺带发现的登记、新断点 AQ-38 的处置、
简报里那条构建器可见性基线的真实结果，以及「按裁决调整的基线」。**供用户复核，不代替用户拍板。**

现算口径：候选树 HEAD `53a1a4b83`（= 最新远端 `origin/spec/disclosure-note-doc-upload-and-batch-fill`
再叠加本 spec 改动），所有数字均在该树与共享库上现算，2026-11-01。

---

## 一、任务完成度

- 任务共 **48 项（0~47，无缺号）**，已勾 **46**，未勾 **2**：
  - `[ ]* 37` 浏览器全链路实测 —— **代码已改但未实测**，卡点与请求见第六节；
  - `[ ] 39` 本收口（本文件 + INDEX 行 + 终验 + 清理）。
- 原记为 data-blocked 的 `38`（合并项目路径）**已转为实测通过**：前置判断本身是错的，详见第五节。

## 二、ADR-AQL-01~20 逐条回显

| ADR | 裁决 | 落地现状（现算） |
|---|---|---|
| 01 | 结果下钻只到「有权威页面」的模块，唯一实现放 `queryResultLinks.buildRowDrill` | 已落地；账簿 query 由 `useLedgerUrlSync.buildLedgerQuery` 生成，`syncToUrl` 同源 |
| 02 | 查询结果**不能**回写底稿 / 附注 | 已落地；三个旧写回路径一律 `410 ADVANCED_QUERY_WRITEBACK_RETIRED`，e2e 用例逐一硬断言 |
| 03 | `param_sql_builder` 保留并接线 | 已落地；业务视图条件、旧筛选键、构建器条件共用 `build_portable_filter`；W3 新增三算子同此 |
| 04 | `cross_sheet_trace_orchestrator` 删除 → **2026-10-27 起暂缓** | **未删**（与 acnr D6 冲突）；三件保留不动、不改变现有行为，待拍板见第四节 |
| 05 | 常用审计预置模板：**做**（W3） | 已落地：`custom_query_presets.json` 10 条 + 服务端 `resolve` + 弹窗「系统预置」分区；真库 10 条逐条对账 |
| 06 | 计数 / 排序 / 分页下推到数据库；N1 不达标按预案①②③ | 已落地；N1 三项现均达标（见第三节），**本 spec 未提交任何索引迁移** |
| 07 | 分组 / 透视：保留内存处理但触顶即拒 | 已落地；超 5,000 行 → 400 `AGGREGATION_TOO_LARGE`（带实际行数） |
| 08 | 构建器准入与人员表按 `GET /api/query/access` 同一判定 | 已落地；前端 `useQueryBuilderAccess` 不再按系统角色自判 |
| 09 | 构建器作用域与 JOIN 由一个作用域函数统一生成谓词 | 已落地；基表谓词进 WHERE、JOIN 目标谓词并入该 JOIN 的 ON |
| 10 | 合并类叶子保留（评估 D7 修正） | 已落地；指标树保留合并叶子，四条路径本轮已实测（第五节） |
| 11 | 模板范围与删除按 D8 / D9 | 已落地；`scope` 读写兼容 team，前端不出现 |
| 12 | ACNR 选字段**移交** `acnr-foundation-defect-closure` D1（用户裁决 Q0） | 已落地；本 spec 不改面板、不改 `acnr_targets` 契约 |
| 13 | 删除清单按 §3.9 一类一提交 | 已落地；`POST /batch-execute` 已删（配方表第 29 行每格 404），cross-sheet-trace 按 ADR-04 暂缓 |
| 14 | 导出：按月完整导出；超 1,000,000 行拒绝而不截断 | 已落地；见第七节「按裁决调整的基线」 |
| 15 | 年度与入口上下文：映射只在 `queryEntryContext.ts`，年度不按日历年兜底 | 已落地；W6 的 `buildQueryEntry` 同处，年度 = `target.year ?? hostYear`，取不到交弹窗按项目审计年度解析 |
| 16 | 指标树：复用 `DisclosureEngine.get_notes_tree`，写明分组与缺省组名 | 已落地；schema 现为 **v15**（设计写的 14 已过期，按现读顺延） |
| 17 | 模板溯源（AQ-17） | 已落地；底稿清单行按 `wp_code` 发 `workpaper:` URI，登记了就跳模板库底稿模板页签 |
| 18 | 引用：`meta.ref_context` 下发 `template_type` 与年度，前端批量校验每批 ≤ 200 | 已落地；本轮把 `ref_context` 改成**最小列投影**（见第五节缺陷 ①） |
| 19 | 循环级可见性：试算表 / 调整分录按循环科目过滤，附注章节范围外 403 | 已落地；W6 的 `note_section` 筛选键先过这道门（403 `SECTION_OUT_OF_SCOPE`） |
| 20 | 业务页行级「按此查询明细」：**做**（W6），映射一处、科目解析在后端一处 | 已落地；四处入口 + `entry_accounts.py` + `entry_filters.py`，页面净增 TrialBalance −2 / DisclosureEditor 0 / WorkpaperEditor +3 / ReportView 0 |

---

## 三、N1 性能三项（ADR-AQL-06）

和平药房_2025 当前 active 数据集（ledger 1,066,675 行 / aux 2,731,915 行，1002 前缀 348,780）：

| 项 | 判据 | 实测中位 | 结论 |
|---|---|---|---|
| ① 序时账首页含 COUNT（total 1,066,675） | ≤ 3 s | **0.064 s** | 达标 |
| ② 辅助明细按科目 1002 首页含 COUNT（total 348,780） | ≤ 5 s | **0.203 s** | 达标 |
| ③ 10 万行级导出（1002 前缀 116,260 行，xlsx 约 4.19 MB） | ≤ 60 s | **6.379 s** | 达标 |

②此前（任务 21 / B13）为 13.3~17.3 s 不达标。本轮现查：任务 21 当时提给用户的 W12 索引**已由后续性能 spec 以
V226 落地**且 valid / ready（`idx_tb_aux_ledger_active_account_prefix(project_id, year, dataset_id, account_code text_pattern_ops) WHERE NOT is_deleted`）。
新 `EXPLAIN (ANALYZE, BUFFERS)`：COUNT 走 **Index Only Scan**（348,780 行、`Heap Fetches: 0`、**28.059 ms**），
首页走同索引的 Bitmap Index Scan + Bitmap Heap Scan（**181.673 ms**）；旧计划里「位图扫 273 万行、按 LIKE 过滤掉 238 万行」已消失。
**本 spec 没有新增也没有执行任何迁移**，只现算验证。W12 因此不再需要用户批准。

## 四、§11 待拍板逐条回显（推荐默认值；本 spec 均不做）

| # | 事项 | 推荐默认 | 本轮状态 |
|---|---|---|---|
| W1 | 查询结果真回写底稿格 / 附注 | 不做，以「引用 + 下钻」交付 | 未做（ADR-02 一致） |
| W2 | cell-writeback / writeback-preview / writeback-confirm 是否整体下线 | 保留现状（已收窄并隔离） | 未做；三条现为 410 并有硬断言 |
| W3 | 常用审计预置模板 | — | **已纳入本 spec**（ADR-05，任务 41~44） |
| W4 | ACNR 选中格成为结果列 | **已移交 `acnr-foundation-defect-closure` D1**（用户裁决 Q0） | 本 spec 不做、不改面板与 `acnr_targets` 契约 |
| W5 | 弹窗指标树懒加载 | 不做（缓存按附注版本失效已覆盖重复打开） | 未做 |
| W6 | 业务页行级「按此查询明细」 | — | **已纳入本 spec**（ADR-20，任务 45~47） |
| W7 | 多底稿批量取数重做 | 不做（端点与工具条删除） | 未做 |
| W8 | 构建器纳入合并表 | 不做（原因是「0 个合并项目无法验收」） | 🔴 **这条理由已被本轮证伪**：按真实判据 `projects.report_scope` 现查有 **3 个**合并项目。是否改做请用户重判 |
| W9 | 业务视图分组 / 透视界面 | 不做（ADR-07） | 未做 |
| W10 | team 范围彻底下线（含历史数据迁移） | 保留读写兼容，前端不出现 | 未做 |
| W11 | 导出超 100 万行改为截断并在文件内写明 | **不改**，按 R8.2 拒绝并提示缩小范围 | 未做；见第七节 |
| W12 | 序时账 / 辅助明细复合索引迁移 | 须用户批准后执行 | **已不需要**：同等索引已由后续性能 spec 以 V226 落地，N1 ② 现已达标 |
| W13 | 恢复「报表行次映射 → 报表配置」JOIN | 不做，行名已在映射表上 | 未做 |
| W14 | 底稿单元格对未登记坐标也提供引用 | 不做，只对已登记坐标开放 | 未做 |
| W15 | 节假日凭证 | 不做，W3 只做周末 | 未做；原因见下 |
| W16 | C24 其余规则做成预置 | 不做（都要新增聚合 / 取模能力或数据来源） | 未做；第 2 轮评审后 C24 规则 9 / 12 / 13 已纳入（见 ADR-05） |

### 只做周末、不做节假日的原因（§14.1）
`weekday_in` 只依赖凭证日期本身，用 PG 的 `EXTRACT(DOW FROM ...)` 即可判定，无外部数据。
节假日凭证要**逐年维护的节假日 + 调休表**，平台现在没有这张日历，也没有定下由谁维护、何时更新年度数据。
硬编码某一年的节假日会在次年静默失效（且"静默"——查询照样返回结果，只是口径错），
因此 W3 只做周末；要做节假日，先定日历的维护人与年度更新流程（W15）。

## 五、跨 spec 待拍板

1. **cross-sheet-trace 三件（ADR-AQL-04 与 acnr D6）** —— 本 spec 原裁决删除 `cross_sheet_trace_orchestrator.py`、
   `GET /cross-sheet-trace` 与其前端调用；acnr 任务 20（D6）要改进它们。**默认暂缓删除、三件保留不动**
   （不改变任何现有行为）；推荐由 acnr D6 接手，本 spec 不删。权限配方表里该行仍留在第 29b 行。
   **请用户拍板：删除、还是交 acnr D6 改进。**
2. **W8（构建器纳入合并表）的前提变了** —— 见第四节 W8 行：原理由「0 个合并项目」不成立。
3. **W15（节假日日历）** —— 需要确定维护人与年度更新流程才能开工。

---

## 六、本轮抓到并修复的真实缺陷（5 处，都不是判据问题）

同一族：**为取一个字段却 `db.get(Project, ...)` 做全列 ORM 投影**。共享库缺任一与高级查询无关的新列时，
查询主体已经成功，却会在组装 `meta` / 说明 / 口径判定时整体 500。现查缺的是 `projects.amount_unit`
（远端迁移 **V235** 尚未落共享库）。五处逐一改成最小列投影，并各自补了「不得加载整项目行」的回归：

| # | 位置 | 后果（修前） |
|---|---|---|
| ① | `source_registry.ref_context` | 任何注册表源的 `meta.ref_context` 组装 500 |
| ② | `query_export._project_label` | 导出主体成功、写说明时 500 |
| ③ | `fetchers/disclosure._report_scope` | **每个合并项目的附注查询整体 500** |
| ④ | `routers/custom_query._resolve_project_template_type` | 指标树按准则取附注树时 500 |
| ⑤ | `routers/custom_query._resolve_project_report_scope` | 指标树判合并叶子时 500 |

①② 在任务 36 修，③④⑤ 在任务 38 修。修完全域复查：`custom_query` 包内已无同型写法。
修 ④ 直接消除了真 PG 基线里的一条红（`test_live_projects_structure_equals_effective_configs`）。

另一处独立缺陷（AQ-38 同族）：**`ws_{sheet}` 源键不下发 `sheet_key`**。
`_query_worksheet` 读 `filters.sheet_key`，而这个键此前**只有弹窗会设**（`CustomQueryDialog.requestFilters`）⇒
任何不设它的调用方（模板执行、导出、本轮用例）请求 `ws_elimination` 会**静默取到 `info` 工作底稿的数据**，
既不报错也看不出来。已按本文件既有的 `fixed_filters` 机制修（源键决定 sheet，覆盖请求同名键，
与 `report_{类型}` / `adj_aje` 一致）。🔴 既有配方表那一格原先把「空 `fixed_filters`」当成期望、
**固化了这个缺陷**，已更新并补「请求自带的 `sheet_key` 不得盖掉源键」一格。

### 任务 38 的前置判断被证伪
此前记「现库 0 个合并项目」是按 `projects.project_type = 'consolidated'` 判的，而该列的 PG 枚举
`projecttype` **根本没有这个取值**（现查 = `annual` / `special` / `ipo` / `internal_control` /
`capital_verification` / `tax_audit`）⇒ 那个条件**恒 0，与有没有数据无关**。生产代码的真实判据是
`fetchers/disclosure._report_scope` 读的 **`projects.report_scope`**：按它现查未删除项目
standalone 16 / **consolidated 3** / NULL 1。于是任务 38 从 data-blocked 转为**实测通过**（11 passed）。

### 新断点 AQ-38 的处置
模板库「📊 高级查询」按钮发的是**模板口径**的源 URI（`report:<类型>` / `note:<模板章节号>` / `workpaper:…`），
此前原样传给 `execute` ⇒ 恒 400 `UNKNOWN_SOURCE`。处置：映射收在 `queryEntryContext.resolveTemplateLibrarySource`
一处（`report:<类型>` → `report_<类型>`；`note:` → 附注目录 `disclosure` + 编号体系提示，**不猜**模板「五-1-1」
与项目「八、1」的对应；其余原样），布局经 `resolveDialogOpenContext` 下发 `initialSource` / `initialNotice`。
变异 #33（去掉 `report:` 映射）在 vitest 三种载荷用例上打红。本轮的 `ws_*` 缺陷是同族的第二例，已一并修。

## 七、简报那条构建器可见性基线的真实结果

简报要求回报「e2e_manager 构建器只返回可访问项目」。按 design §10.2 的口径现算：
该身份在共享库**可访问项目为 0 个**，构建器因此返回 **0 行**并给出排除提示
（`CYCLE_SCOPED_PROJECT` / `NO_PROJECT_REASON` 两类文案之一）。
这不是实现缺陷，而是把平台既有的可见性规则（循环范围受限项目不进构建器）用到本模块的结果；
按第 2 轮评审 #3 的结论照常推进，并在此如实回报**基线为 0 行 + 排除提示**，不写「通过」。

## 八、按裁决调整的基线（不写「通过」）

批次表批 5 原写「和平药房序时账可完整导出 1,147,414 行（或按上限截断并在文件内写明）」。
按 **ADR-AQL-14 / R8.2** 调整为：**按月完整导出（行数 = 该月 COUNT）+ 超过 1,000,000 行返回 400 且不产生文件**。
现算：该项目 active 数据集序时账 **1,066,675 行**（> 100 万），整表导出按裁决**拒绝**；
本轮按 1002 科目前缀导出 **116,260 行**（6.379 s、约 4.19 MB、临时文件零残留）作为 10 万行级判据。
W11（改为截断并在文件内写明）的推荐默认值是**不改**。此条**不记「通过」**，只记调整后的基线与实测值。

## 九、§14.5 顺带发现（归各自模块，登记不改）

1. `composables/usePenetrate.ts` 的 `toLedger` 推 `/ledger?code=&year=`，而账簿页只读 `account` / `level`
   ⇒ 试算表双击金额、错报金额、辅助汇总、附注右键「穿透到序时账」四处都停在余额表、不定位科目。**归账簿穿透**。
2. `ReportEngine.drilldown` 单码按 `standard_account_code == code`（精确），而报表取数按前缀
   ⇒ 试算表有子科目时「查看穿透」列出的科目少于金额实际构成。**归报表**。
   （本 spec 的 W6 `report_row` 筛选键按**前缀**实现，与报表取数同口径，并有子科目夹具用例钉住。）
3. 华氏、辽宁的重要性水平三档都存为负数。**归重要性水平**。
4. `mapping_service.get_sections_by_cycles` 只返回上市版章节号 ⇒ 国企项目受限成员的附注目录为空。
   **归平台鉴权 / 附注循环映射**。（W6 的附注章节解析因此**按准则分流**，不用那条通用字段，见下。）
5. `line-composition` 端点不传年度时取 `tb_balance` 最大年度，报表页调用时没有传年度。**归报表**。
6. 「大额」平台已有两处实现（C24 前端 `Math.max(借,贷) > 阈值`；抽凭 / 截止测试后端 `GREATEST(…) >= 阈值`），
   只在等于阈值时结论不同；W3 复用后端那一处（抽成 `ledger_line_amount`），**不新增第三处**。
   两处是否统一**归 C24 / 抽凭**。

---

## 十、设计偏离与过期数字（以本文件为准）

逐条都是**现算**出来的，不是推断；设计里的旧数字保留原文，差异写在这里。

| 处 | 设计原文 | 现算 | 处置 |
|---|---|---|---|
| 指标树 schema 版本 | 「届时应为 14」 | **v15** | 按现读顺延，不照抄过期版本号 |
| `DisclosureEditor.vue` HARD_CAP | 3,265 | cap **3,170** / 实际 **3,161** | 远端已两次下调；W6 仍按净 0 落地 |
| `ThreeColumnLayout.vue` | 现状 1,546 / 预算 ≤ 1,566 | 现 **1,613** / 白名单 1,598 ⇒ 门限 **1,677** | W6 只 +1 行（比设计预留的 3 行更少） |
| `CustomQueryTab.vue` | 1,245 | **1,011** | 仅更正，无改动 |
| R14.6 的 BS-002 快照 | 822,999,085.83 | **112,166,836.03** | 共享库重建后快照失效；用例改**现算双向对照**（报表本期金额 = 取数科目审定数之和，实测逐分相等），不引用快照 |
| 附注章节 → 底稿编码的唯一来源 | `note_account_mappings` | 该表共享库 **0 行** | 改为**两源并集**：`wp_account_mapping.json` 的按准则章节字段为主 + 原表仍接在链路上（填了即生效，有回滚事务用例钉住）。只用原表则该功能对任何真实项目都是死路 |
| JSON 里的通用 `note_section` 字段 | （设计未提） | 96 个有值行里 **80 行**与两套准则字段都不一致（`D3` 与 `D6` 的通用编号都写成「五、18」） | **刻意不用**；索引按 (准则, 章节号) 分键。两套准则间编号冲突现查 0 个 |
| `QueryEntrySwitch` | `{source, label}[]` | 需要可带 `filters` | 显式扩展：附注章节切到「相关科目（试算表）」要把筛选键从空换成 `note_section=<章节>`，只换源不换筛选取不到数 |
| `aux_ledger.required_filters` | `{account_code}` / `{aux_type}` | 增 `{wp_code}` | 底稿入口切到辅助明细时只带这个键，否则恒 `AUX_FILTER_REQUIRED`；提示文案不变 |

### 为满足行数门而做的压缩（不是重构，渲染结果不变）
- `TrialBalance.vue`：门限 `int(4491 × 1.05) = 4715`、改动前 4,714 ⇒ **只剩 1 行余量**，而 W6 要 +2 行。
  按「优先压缩不抬白名单」把同一块汇总右键菜单里「恢复公式」/「断开公式」两项的 3 行写法各压成 1 行
  （与其上方三条邻居本就是单行写法），省 4 行后再加 2 行 ⇒ **4,714 → 4,712**。
- `DisclosureEditor.vue`：把「穿透到序时账」那项的 3 行写法压成 1 行，腾出的 2 行放新入口与 import ⇒ **净 0**。

### 既有用例的契约变更（各写明理由）
1. `test_aql_source_registry.py` 的 `filter-list` 格原断言 `account_code: ["1001","1002"]` 为 `INVALID_FILTER_VALUE`，
   与 R14.2「值可为字符串或 ≤ 50 项的数组」冲突 ⇒ 改为 `voucher_no` 多值仍 400（普通键单值不变），
   并新增 `account_code` 空数组与 51 项各一格仍 400。
2. 同文件 `ws_consol_tb` 那格原期望空 `fixed_filters`、固化了第六节那个缺陷 ⇒ 改为 `{"sheet_key": "consol_tb"}`，
   并补 `ws_elimination` 与「请求自带 `sheet_key` 不得盖掉源键」两格。
3. `useC24AnalyticsEngine.pbt.spec.ts` 的借贷合计期望原用 `toBeCloseTo`，与生产「逐行取分后汇总」不等价
   （会掩盖真实的分币差异）⇒ 改为同口径精确相等，**不放宽为近似比较**。

## 十一、验证汇总（现算）

| 项 | 结果 |
|---|---|
| 后端 SQLite 定向（`tests/advanced_query_linkage` + 4 个相关文件） | **602 passed / 0 failed** |
| 后端真 PG（本 spec 新增 4 个文件：conditions / presets / entry_accounts / consolidated） | **47 passed**（3 + 11 + 11 + 11，另 11 为 entry 的首轮） |
| 后端真 PG 全目录归因 | 候选 120 failed / 204 passed（324 例）；干净基线 121 failed / 167 passed（288 例）；**逐节点新增失败 0、消除 1**。合 v1.0.89 时对基线 `53a1a4b83` 得同一结论（`evidence/pg_attribution.json`），合 v1.0.91 后把 base worktree 切到 `93402de37` 重跑，结论不变（`evidence/pg_attribution2.json`）。解析出的节点数与 pytest 摘要逐项闭合（117+167+4=288、116+204+4=324） |
| 前端定向 vitest（W3 9 文件 + W6 10 文件，去重后） | W3 **143 passed**；W6 **132 passed**（含新增 `QueryDetailEntry` 9 + `queryEntryPageWiring` 17 + `queryEntryBuild` 24 + `useQueryEntry` 13 + `QueryEntryBanner` 8） |
| ESLint（本轮改动文件） | **0 error**（21 条既有 `gt-audit` 风格 warning） |
| `vue-tsc --noEmit -p tsconfig._aql-linkage.json` | **退出码 0** |
| Ruff（本轮后端改动文件） | **All checks passed** |
| `check_file_size.py --staged --files-from -`（本 spec 相对远端的 74 个净改动代码文件） | 剔除 `DisclosureEditor.vue` 后 **退出码 0**；含它则 exit 1（远端 3273 > cap 3170，本 spec 对它净 0 行，见 §十五.4） |
| `tests/scripts/test_hard_cap_ratchet.py` | 合 v1.0.91 后 1 failed / 17 passed，唯一一条就是上面那个 `DisclosureEditor.vue` 硬上限（远端侧）；原先 ReportView 那两条已随远端修掉 |
| `check_staged_tree_self_consistency.py` / `check_router_registration.py` | 均 **退出码 0** |
| 逐个 import `app` 下全部模块 | **3068 / 3068 成功、失败 0**（`evidence/scan_imports2.json`；合 v1.0.89 时为 3066 / 2 失败，见 §十五.2 A） |
| 全前端重复 import 扫描 | 8678 个 `.vue/.ts/.tsx`，真实重复 **0**（修掉 `ThreeColumnLayout.vue` 后），2 个命中为测试夹具模板字符串内的假阳并充当阳性对照 |
| 变异（design §10.4 既定编号） | W3 #24 / #25 / #31 + T43、W6 #26 / #27 / #28 / #34 全红；额外 #27b / #34b 全红；**5 条阴性对照全绿**；**15/15 逐字节恢复 sha256 一致** |
| `gen_journal_entry_rules_ts.py --check` | 退出码 0（输出幂等，按项目既有 `--check` 约定，不用 `--write` + `git diff`） |
| 共享库残留 | `AQL-W3-%` / `AQL-T40-BLANK-%` 均 **0**；`custom_query_templates` 整表 **0 行**；`materiality` 无 `AQL-%` 注记 |

### 预存失败（非本 spec，未代改）
- `test_hard_cap_ratchet.py`：合 v1.0.89 前是 3 条（`ReportView.vue` 1,946 > cap 1,943；`DisclosureEditor.vue` cap 3,170 而实际 3,161 余量 9 > 0；连带 `test_ratchet_detects_artificially_raised_cap`）。合 v1.0.91 后剩 **1 条**：`DisclosureEditor.vue` 实际 **3,273** > cap 3,170 —— 这条由远端把该文件从 3,161 撑到 3,273 造成，本 spec 对它 `--numstat` 为 4 增 4 删 = **净 0 行**。
- `ThreeColumnLayout.year.spec.ts` 6 条（合 v1.0.89 前）：用当时 HEAD 版该文件原样复跑**同样 6 条红**（`evidence/tcl_year_attribution.json`，复原后 sha256 一致）。
- `test_aql_publish_rows_callers.py` 1 条：远端新增第 6 个 `publish_rows` 调用方未登记。在**纯远端** base worktree 单独复跑同红（`evidence/base_publish_guard.log`）；按棘轮契约登记后转绿（§十五.3）。
- 真 PG 基线 121 条红的两大成因：**41 条**是 `column projects.amount_unit does not exist`（远端 `V235__display_preferences…` 未落共享库 —— 现已直接查库证实：`projects.amount_unit` / `user_display_preferences` / `report_generation_run` / `adjustments.content_revision` 在共享库里都不存在），其余主要是 `gold.py` 固定项目 UUID 失效导致的 403 / 空集。
- 仓库整体 `ruff check backend/` 有 6000+ 预存违规且仓库**没有任何 ruff 配置文件**（跑的是 ruff 默认 E4/E7/E9/F），CI `backend-lint` 因此长期红。本 spec 只负责「本轮改动文件 ruff 干净」，现为 **All checks passed**。

---

## 十二、唯一待用户放行项：任务 37 的浏览器实测

**结论先说：代码已改但未实测，卡点是环境而非代码。合并最新远端 `93402de37`（v1.0.91）后卡点升级了
—— 不再是「差一条迁移」，而是远端树自己就起不来。**

- 候选栈已备好：候选后端 9981（`DATABASE_URL` 指共享库、`REDIS_URL=redis://localhost:6379/9` 独占库、不 reload）
  + 候选前端 3040（`.env.local` 把 `VITE_API_BASE_URL` **在配置文件里定死**为 `http://127.0.0.1:9981`，
  避免只改端口导致写请求落到共享后端 9980）。
- 🔴 **阻断（远端侧，本 spec 未代改）：`backend/migrations` 有 3 组重复版本号** ⇒
  `MigrationRunner.scan_migrations()` 直接抛
  `RuntimeError: [Migration] 检测到重复版本号迁移文件（须重编号，否则靠后者被静默跳过）`，
  配对的 R 文件同样 3 组重复 ⇒ **后端在任何库上都起不来**，与「某条迁移是否落库」无关。

  | 版本号 | 两个文件 | 引入提交 | 共享库是否已应用 |
  |---|---|---|---|
  | V233 | `display_preferences_and_project_amount_unit.sql` ｜ `project_creation_grants.sql` | `cd45ec129`（10-31 22:27）｜ `b410cfb0c`（10-31 20:16） | 只有 `project_creation_grants` 已应用（10-30 16:34） |
  | V235 | `adjustment_review_tasks_and_group_revision.sql` ｜ `display_preferences_and_project_amount_unit.sql` | `3cd7352a6`（11-01 14:58）｜ `bb29a49f6`（11-01 13:11） | 两个都未应用 |
  | V236 | `ai_chat_run_context_request_snapshot.sql` ｜ `formula_provenance_report_runs.sql` | `a6c1fa93a`（11-01 14:23）｜ `113be0cfa`（11-01 14:22） | 两个都未应用 |

- 现算（本次合并后）：磁盘 **249** 个 `V*.sql`（最高 V249）；共享库 `schema_version` **最高 V234**；
  `report_generation_run` / `user_display_preferences` / `projects.amount_unit` / `adjustments.content_revision`
  **在共享库里都不存在** ⇒ 上表「未应用」是直接查库得出的，不是推断。
  合并前本 spec 候选 `5be63f167` 侧 233 个 V 文件、最高 V235、**零重复** ⇒ 三组撞号全在远端侧。
- V233 那组是**合并复活**：`V233__display_preferences…` 与 `V235__display_preferences…` 逐行只差注释里的
  版本号字符串（`-- V233：` vs `-- V235：`，R 文件另差 3 处报错文案），且 `d17a1587a` 已经删过 V233 这份；
  另一会话在 `.kiro/specs/formula-template-dual-project-pilot/tasks.md:75` 里已写明
  「共享库权威编号是 V235」。
- 建议的最小修法（**需用户放行，涉及 3 个他域 spec 的已推送产物**；因三组都未落库，**不需要动
  `schema_version` 记账**）：① 删 `V233__display_preferences…` + `R233__rollback_display_preferences…`
  （权威是 V235）② 把到得更晚的 `V235__adjustment_review_tasks_and_group_revision`（+R）改号
  ③ 把到得更晚的 `V236__ai_chat_run_context_request_snapshot`（+R）改号。
  新号按铁律取 `max(磁盘 249, 共享库 234) + 1` ⇒ V250 / V251。
- B 解决后，任务 37 还需要第二步放行：候选栈启动会把共享库从 V234 推到 V251（**约 16 条他域迁移**），
  属跨 spec 的共享资源变更。

**请用户拍板两件事**：① 是否按上面三条修掉重复迁移号（只改文件名与文件内注释里的版本号，不动库）；
② 是否允许候选栈把那批他域迁移落到共享库。两条都放行后即可跑任务 37 的 11 个 Playwright 用例与
W3 / W6 走查；在此之前任务 37 保持 `[ ]*`，**不以「代码已改」充当实测**。

## 十三、清理

- 本轮临时产物一律在仓库根 `tmp_advanced_query_remaining/`（`tmp_*` 已 gitignore）：
  `probes/`（探针与变异驱动）、`evidence/`（证据 JSON）、`*.log`、`*.cmd`、`*.xml`。
- 两个锁定的 worktree：`wt`（候选，已合并到远端 `93402de37`）与 `base`（归因基线，已切到同一远端提交）。
  收尾按 unlock → `cmd /c rmdir` 拆 `eslint-plugin-gt-audit` 联接 → 删目录 → `git worktree prune` 处置
  （🔴 联接必须先用 `cmd /c rmdir` 只拆链接，不能 `Remove-Item -Recurse`，否则会顺着联接删真目录）。
- `wt/audit-platform/frontend/.env.local`（候选栈代理配置，被 `*.env.local` gitignore）随 worktree 一并删除。
- 上一批次遗留的 `tmp_aql_linkage/` 按 design §12 一并清理（结论都已落到 tasks.md 与本文件）。

## 十四、本轮过程失误（诚实记录）

1. 🔴 **违反「禁用 PowerShell 处理中文」铁律**：我用 `(Get-Content -Raw) -replace | Set-Content` 改
   `paged_fetch.py`，把中文写坏；随后从 **HEAD** 恢复该文件，又连带丢掉**任务 40** 对它的改动
   （`_NO_VALUE_CONDITION_OPS` / `_contains_unresolved_param` / `_condition_value_missing` /
   `_condition_where` 改用 `spec.condition_columns` 与 `CONDITION_VALUE_REQUIRED`），表现为 9 例红。
   已用 Python 逐块补回并复跑全绿，另新增 `probes/check_encoding.py` 作例行核对
   （断言本轮 16 个文件都是合法 UTF-8、无 U+FFFD）。**教训**：改含中文的文件一律用 Python 写字节；
   「从 HEAD 恢复」只在确认该文件在本轮之前没有未提交改动时才安全。
2. **锚点不带换行会多命中**：10 空格缩进的那行把 8 空格的写法整体包含在内，`count()` 得 2 ⇒
   锚点一律带前导换行。
3. **我写的金标准口径错过两次**：合并附注按 `consol_note_data` 记录数算（实际是把每章节 `data.rows`
   展平、每章节上限 100 行）；`ws_*` 按「无 sheet 必 0 行」假设（实际当时会静默回落 `info`）。
   两次都是**用例打红后现读实现**才改对 —— 这正是「判据必须拿真数据对账」的价值。
4. **我自己的探针也写过不一致的过滤**：查合并项目时漏了 `p.is_deleted`，一度把已删除的首汽租车算进来。

## 十五、合并最新远端（`93402de37` / v1.0.91）与由此抓到的远端侧缺陷

本 spec 候选先合 `4390aaaa3`（v1.0.89），期间远端又推进两个提交，故再合 `93402de37`（v1.0.91，自动合并无冲突）。
合并链：`5be63f167`（本 spec）→ `a81387be1`（合 v1.0.89，4 处冲突手工解）→ `7582ffb01`（合 v1.0.91）。

### 1. 四处冲突的解法（合 v1.0.89 时）

- `CustomQueryDialog.vue`：以**本 spec 版**为基 + 移植远端 `openRevision` 4 处。
  理由：远端 `a6c1fa93a`（platform-perf）用陈旧副本回退了本 spec 已推送的
  `countToken`×9 / `queryGeneration`×6 / `invalidateQueryResult`×4，按 lineage 现查后恢复。
- `ThreeColumnLayout.vue` / `ThreeColumnLayout.customQuery.spec.ts`：以**远端版**为基 + 叠加本 spec 的
  `:entry` 接线与 `'openRevision', 'entry'` 载荷断言。
- `.kiro/specs/INDEX.md`：以远端版为基，更新本 spec 行为 46/48，并恢复被 `a6c1fa93a` 丢掉的
  `advanced-query-safety-and-consistency-closure` 行。现算：与远端 INDEX 的差异恰好 2 行（1 改 1 加），
  表格行的未转义 pipe 计数多重集与远端逐值相同（各 125 行非 4-pipe，都是文件里本来就有的其他表形状）。

### 2. 远端侧缺陷三条（都不是本 spec 引入）

| # | 缺陷 | 判据与证据 | 处置 |
|---|---|---|---|
| A | `backend/app/routers/adjustment_import.py:82` 用 `require_project_permission`，第 15 行没导入它（签名默认值在模块导入期求值 ⇒ NameError） | 逐个 import `app` 下全部模块：v1.0.89 上 **3066 成功 / 2 失败**（`app.main` 与 `app.routers.adjustment_import`，同一行）；同族 6 个 router 都有这一行；`deps.py:336` 确有该函数 | **远端已自行修掉**（v1.0.91 第 15 行已补）。合并后现扫 **3068 / 3068 全部导入成功、失败 0**（`evidence/scan_imports2.json`） |
| B | `backend/migrations` 3 组重复版本号（V233 / V235 / V236 + 配对 R） | `MigrationRunner.scan_migrations()` 抛 RuntimeError；在**纯远端** base worktree 上单独复跑同样抛；合并前本 spec 侧零重复 | **未代改，待用户放行**（见 §十二） |
| C | `ThreeColumnLayout.vue` 有**两行一模一样**的 `import { useMountOnFirstOpen } …` ⇒ `vue/compiler-sfc` 报 `Identifier 'useMountOnFirstOpen' has already been declared`，**应用外壳整文件编译不过** | 逐侧现查：本 spec 合并前候选 **1 处**，远端 v1.0.89 与 v1.0.91 **都是 2 处**（行 406 / 412）⇒ 远端合并残留 | **本轮修掉**（删掉靠后那一行，保留与 `defineAsyncComponent` 相邻的那行；1639 → 1638 行） |

C 的发现途径值得记一笔：本 spec 的单区域 `tsconfig._aql-linkage.json` **刻意不含** `ThreeColumnLayout.vue`
（§十 已说明：含它会拖入 16 条预存类型错），所以 `vue-tsc` 这一侧是绿的；真正打红的是本 spec 的
`ThreeColumnLayout.customQuery.spec.ts` —— 它**真实挂载**该布局，于是在 collect 阶段就炸。
这正是「静态类型检查 ≠ 能编译」的一个样本。

**触类旁通**：写了 `probes/scan_duplicate_imports.py` 扫全前端 **8678** 个 `.vue/.ts/.tsx`
（按顶层 import 语句解析本地绑定名，不做文本匹配），只剩 2 个命中且**都是假阳**
—— `ieWiringIntegrity.spec.ts` 与 `e1SetupOrder.spec.ts` 里的 import 行位于测试夹具的模板字符串内
（多个独立夹具各带一份 import，合法）。即「真实重复 import 全仓只有 `ThreeColumnLayout.vue` 这一处」，
且这 2 个假阳同时充当扫描器的**阳性对照**（证明它确实能发现重复，不是空转）。

### 3. 本 spec 自己的两处问题（合并暴露出来的）

1. `ThreeColumnLayout.customQuery.spec.ts` 新增的 W6 两例用了 `nextTick` 但没导入，且
   远端已把 `CustomQueryDialog` 改成 `defineAsyncComponent` + `useMountOnFirstOpen(showCustomQuery)`
   （首次打开才挂载）⇒ 只等 `nextTick` 拿不到实例。改为 `flushPromises()` 并写明原因；
   该文件 14 例全绿。**此前被 C 的编译失败整体掩盖**（整文件 collect 失败时它报的是 `Test Files 1 failed`
   而 `Tests 366 passed` —— 用例数全绿、文件数不绿，只看 `Tests` 一行会判成通过）。
2. `test_aql_publish_rows_callers.py` 的调用方棘轮：远端 `3cd7352a6` 新增了第 6 个合法调用方
   `services/tb_publish_service.py`（经发布门 `publish_rows` 写入，生产调用方是
   `routers/wp_html_save.py:840` 的 publish-to-tb 路径，非死模块）⇒ 按棘轮自己的契约登记并写明理由。
   该红在**纯远端** base worktree 上单独复跑同样为红（`evidence/base_publish_guard.log`），即远端头本就红。

### 4. 为过行数门做的两处压缩（渲染结果不变）

- `TrialBalance.vue`：远端 4718 行 > 门限 `int(4491 × 1.05) = 4715`。本 spec 对它净 −2（压两项右键菜单 + 加入口与 import）
  后仍 4716，又把同一菜单块里 `onTbSumCtxCopy` 那 3 行压成 1 行（与同块邻居写法一致）⇒ **4714**，过门。
- `ThreeColumnLayout.vue`：删掉重复 import 后 1638 行，门限 1677，过门。
- 🔴 **`DisclosureEditor.vue` 过不了，且不是本 spec 能解的**：远端 **3273** 行 > hard cap **3170**；
  本 spec 对它 `git diff --numstat` 为 **4 增 4 删 = 净 0 行**（远端 3273 → 合并后 3273）。
  该文件的 cap 属它自己的瘦身预算，处置只有两条（都该由该文件的 owner 定）：继续瘦身到 3170 以内，
  或按棘轮提示把 cap 重定基为真实值 3273 作为只许变小的棘轮。本 spec **不动它的 cap**，如实登记。

## 十六、阶段 0 第二轮（2026-11-01）：安全合入最新远端 + 可做的判据补齐 + 一处决定性现算

本节只记**本轮现算**的结果与处置，不改前十五节的原文。候选树 = 最新远端
`85af801a0`（v1.0.100）+ 本 spec，提交链见下。

### 16.1 安全合入（用户 Phase 0 第 1 条）

主工作树有并发会话的大量脏改动（现算 180+ 个已跟踪文件被改、含 `components.d.ts`
这类生成物），**不在主工作树做合并**，也不 `git stash`（它写全仓共享的 `refs/stash`）。
做法：在仓库根建锁定的临时 worktree `tmp_advanced_query_phase0/merge_wt`，起点取仓库里
已有的、干净的安全合并提交 `589c14c4c`（父 = 远端 `919424f00` + 本地 `7fbd522c8`，已含本
spec 候选 `79d07ccad`），再合最新远端 `85af801a0`。

| 项 | 结果 |
|---|---|
| 合并冲突 | **0**（`git diff --diff-filter=U` 为空；仅 3 个文件进入暂存：INDEX.md、memory.md、新增的 INDEX 一致性守卫） |
| 祖先核对 | `79d07ccad`（本 spec 候选）· `85af801a0`（远端头）· `7fbd522c8`（本地头）· `68458e2e3`（v1.0.98）· `a77026baf`（v1.0.95）**五个全部是候选的祖先** |
| 迁移完整性 | 248 个 `V*.sql`、最高 **V251**、**重复版本号 0 组** |
| 应用可导入 | `import app.main` 成功 |

🔴 合并**暴露出一条两侧单独都不红的红**：远端 v1.0.100 新增的
`backend/tests/test_spec_index_consistency.py` 要求每个活跃 spec 目录在 INDEX.md 里至少被
一个**本地链接**（`](路径)`）指到；而 `workpaper-html-onlyoffice-bidirectional-writeback-closure`
的目录由并发会话在本地分支重新置为活跃，INDEX 里有 **8 处纯反引号提及、0 个链接**。
纯远端侧没有这个目录（守卫绿），纯本地侧没有这个守卫（也绿）⇒ 只有合并后才红。
处置：**不往棘轮基线加条目**（那是只许减少的历史债棘轮，加一行就是把洞合法化），也**不代写
它的完成度**（守卫 docstring 明确说「别人在建的 spec，不代写其状态」）；只把 INDEX 里已有的
那句「未随本批归档（仍 active）：① …」的反引号名加上指向其 `tasks.md` 的链接 —— 1 行改动、
不新增状态文案、表格 pipe 结构与总行数不变。改后该守卫 **16 passed**。

### 16.2 三个写端点在最终运行栈为 410（用户 Phase 0 第 5 条）—— 已确认并补成常驻守卫

现算（生产 `app.main`，TestClient 真发请求）：

| 路径 | 首条命中端点 | 同路径候选 | 声明码 | 实发状态 | 错误码 | 依赖 |
|---|---|---|---|---|---|---|
| `/api/custom-query/cell-writeback` | `cell_writeback_gone` | 1 | 410 | **410** | `ADVANCED_QUERY_WRITEBACK_RETIRED` | 无 |
| `/api/custom-query/writeback-preview` | `writeback_preview_gone` | 1 | 410 | **410** | 同上 | 无 |
| `/api/custom-query/writeback-confirm` | `writeback_confirm_gone` | 1 | 410 | **410** | 同上 | 无 |

阳性对照：`GET /api/health` 为 503（不是 410）⇒ 判据不是对所有路径空转。

判据写成 `tests/advanced_query_linkage/test_aql_writeback_retired_runtime.py`（10 passed），
分三层：**路由表层**（按 Starlette 首条命中语义解析，命中的必须是退役桩本身、同路径只许 1 条
—— 只数「路径存在」会被同路径旧实现遮蔽或被重复注册的另一份接走，平台有过 13 条路由遮蔽的
先例）·**响应层**（无登录态 + 畸形请求体仍 410 且错误码一致，即退役早于鉴权与请求体校验，
否则旧客户端拿到的是 401 / 422，看不出「已下线」）·**实现层**（桩不依赖 `get_db`，不占连接池）。

磁盘变异（每条改盘 → 跑守卫 → 逐字节恢复并核对 sha256，4/4 恢复一致）：

| 变异 | 期望 | 实得 | 打红的那一条 |
|---|---|---|---|
| M1 `cell-writeback` 装饰器声明码 410 → 200 | RED | **RED** | 路由表层（1 failed）。🔴 注意**响应层仍是 410**：桩里 `raise` 的 410 压过装饰器声明，所以这条变异只能被「声明码」判据抓到 —— 我起初写的「两层都会红」不成立，按实测更正 |
| M2 退役错误码改名 | RED | **RED** | 响应层错误码（3 failed） |
| M3 给退役桩加 `Depends(get_db)` | RED | **RED** | 实现层「不占连接池」（1 failed） |
| N1 阴性对照：只加一行注释 | GREEN | **GREEN** | — （证明守卫不是对任何改动都红） |

### 16.3 决定性现算：`gold.py` 的 9 个固定项目 UUID **全部失效**（用户 Phase 0 第 3 条）

前十五节把真 PG 基线里那批红归因为「`gold.py` 固定项目 UUID 失效导致的 403 / 空集」。本轮
直接查库把它量化了：**9/9 个 UUID 在 `projects` 表里根本不存在**（不是「软删」，是查不到行）。

| 代号 | 文件里的注释 | 现状 |
|---|---|---|
| HS / HP / YB / LN / MD / WL | 华氏 / 和平药房 / 宜宾临港店 / 辽宁卫生服务 / 医疗器械 / 和平物流 | **UUID 均不存在**；同名业务项目大多还在，但 id 已换（如华氏现为 `a7fc75e5…`、和平药房 2025 现为 `2aa00f57…`） |
| UA / UB / UP | 【UAT】子公司A / 子公司B / 合成集团母公司 | **UUID 不存在，且现库没有任何以 UAT 命名的未删除项目**（唯一的 3 个【测试】项目是「公式同步甲 / 乙 / 集团」） |

后果不是「少测了几条」，而是**那 15 个 `tests/advanced_query_linkage/*_pg.py` 文件现在证明不了
任何东西**：要么在「前置」断言上红，要么拿 403 / 空集与空金标准互相印证而假绿。
`code_file_counts` 现算：HS 11 文件 · UA 8 · YB 5 · HP 4 · WL 3 · UB 2 · LN 1 · UP 1 · **MD 0（导入即死码）**。

本轮同时把每个代号承担的**数据能力**现在落在哪些活项目上查了出来，作为「按稳定业务条件动态
选择」的判据素材（只列第一名）：

| 能力（用例真正依赖的） | 现在的承载项目 | 现算量 |
|---|---|---|
| 序时账行数最多（HP 的大数据角色） | 和平药房_2025 `2aa00f57` | aux 363,891 行（aux 第一） |
| 辅助余额次多（HS 的角色之一） | 华氏_2025 `a7fc75e5` | 132,575 |
| 试算表行数最多 | 重药安徽_2025 `0ec33ac9` | 196 |
| 六类报表齐全（HS 的报表角色） | 和平药房_2025 / 安徽 / 某测试集团_2098 | 各 6 类 |
| 余额表方向列非空（**LN 的角色**） | 宜宾 `c8621493` / 安徽 `0ec33ac9` | 各 2,436 |
| 有 tb_balance 但**无 active 数据集**（**WL 的角色**） | 和平药房_2025 `2aa00f57` | 367 |
| 合并附注有数据（**UP 的角色**） | 某测试集团_2098 `80b4355b` | 3,514 |
| 有 AJE 调整分录（HS 的调整角色） | 重药安徽_2025 `0ec33ac9` | 8 |

⇒ 每个角色都**有**活项目能承担，但没有一个还是原来那个 id；且三个可写角色（UA/UB/UP 里的
写入部分）已经没有同类【UAT】项目可用，只能在回滚事务里自建。

**本轮未动这 15 个文件**，原因写明：改法有两种语义（按能力动态解析真实项目 / 在回滚事务里自建
夹具），选哪种会改变这些判据的性质 —— 口径类断言（如「Σ审定 = 金标准」「2.7M 行下 COUNT 不
截断」「方向列分布」）只有在**真实数据分布**上才有意义，合成夹具会把它们降级成「实现与实现
自比」（这正是方法论铁律 ㉓ 点名的坑）；而「写入隔离」类判据反过来必须用自建夹具，不能依赖
某个真实项目恰好存在。建议的分工与待确认点见 16.4。

### 16.4 建议的改法（待用户确认后实施）

- **只读口径类（HS / HP / YB / LN / WL 共 14 个文件）→ 按稳定业务条件动态解析**：新增
  `tests/advanced_query_linkage/project_picks.py`，每个角色一个**能力判据**（例如
  「未删除 + 有 active 数据集 + 余额表方向列非空行数最多」），用显式列的裸 SQL 查（**不可**
  `db.get(Project, ...)` 全列投影 —— 共享库缺 `projects.amount_unit` 时会整体 500，这正是前十五
  节那 5 处 500 的同一机理），按确定性排序取第一名，**取不到就 `pytest.fail` 并打印判据与实际
  候选**（绝不跳过、绝不退化成空集）。角色名保留 HS / HP / … 作夹具名，15 个文件改为注入夹具。
- **写入隔离类（UA / UB / UP 的写入部分）→ 回滚事务自建**：在 `pg_rollback_session` 里建名称带
  【测试】的项目与必要行，事务结束整体回滚；合并角色（UP）自建 `report_scope='consolidated'`
  的项目 + `consol_note_data` 行。
- **死码**：`MD` 现算 0 个文件引用，直接删。
- 待用户确认的两点：① 上面这条「只读用真实项目、写入用自建」的分工是否就按这么定；
  ② 动态解析会让同一条用例在不同时间落到不同项目上（判据恒定、数据随库变），是否接受 ——
  不接受就只能改成「每次手工更新 9 个 UUID」，那等于把本次的失效模式留在原地。

### 16.5 本轮提交（候选 worktree `tmp_advanced_query_phase0/merge_wt`，未推送）

| 提交 | 内容 |
|---|---|
| `a691f1eb6` | merge: 合并远端 `85af801a0`（v1.0.100） |
| `b057d4555` | docs(specs): INDEX 给仍活跃的 writeback 总纲 spec 补本地链接（过远端新增的一致性守卫） |
| `2ec262ace` | test(advanced-query): 三个写端点在最终运行栈为 410 的三层守卫 + 阳性对照 |

本轮临时产物在仓库根 `tmp_advanced_query_phase0/`（`tmp_*` 已 gitignore）：`probes/` 四个探针
（INDEX 链接修改、gold 用量普查、410 三层核验、410 守卫变异驱动）与现算输出。

### 16.6 共享库迁移状态核实（用户 2026-11-01「以实际为准」）

直接查共享库 + 按 `MigrationRunner` 同口径（文件名里的**数字**版本号）比对磁盘，现算结果：

| 项 | 现算 |
|---|---|
| 共享库 `schema_version` | **234 行，最高 V234，1~234 无缺号**，最后一次应用 2026-11-01 06:38:25 |
| 候选树磁盘 | **248 个 `V*.sql`，最高 V251，重复版本号 0 组**；缺号 200 / 201 / 240 |
| **待执行** | **16 条**：V235~V239、V241~V251（V240 磁盘上不存在） |
| 关键对象仍缺 | `projects.amount_unit` · `user_display_preferences` · `report_generation_run` · `adjustments.content_revision` 四项在共享库里**都不存在** |

🔴 **更正**：§十二与任务 37 此前写「约 16~17 条」是估数，现算**恰为 16 条**，逐条列明如上。
16 条**全部是他域 spec 的产物**（adjustment 复核 / ai_chat 快照 / ai 模型信任域 / ai 任务 /
asset_blob / 附件血缘 / 平台耐久任务 / 合并运行 / 抵销工作表 / 报表生成运行 / 合并附注投影 /
公式推送溯源 / 附注公式运行 / 显示偏好 / 公式溯源报表），**本 spec 零迁移**（本 spec 的 V214 早已应用）。

两项顺带核实（都不是缺陷，登记备查）：
- 缺号 200 / 201 是**已应用但文件按裁决移除**（`V200__consol_note_mapping_reuse_and_reference` /
  `V201__partner_manager_edit_level_backfill`），与现有记录一致；
- V189 在库里记的文件名是 `V189__deliverable_edit_and_writeback_integrity.sql`，磁盘上留的是
  `V189__create_share_change_event_table.sql`（历史撞号残留，磁盘那份因版本号已登记而**永远不会执行**）。
  查库确认两侧的产物**都在**（`share_change_event`、`deliverable_section_state`、
  `word_export_task_versions` 三张表齐全）⇒ 无实际损害，不代改。

### 16.7 真 PG 夹具改造（用户 2026-11-01「按你建议来」）—— 基础设施已落地并验证

#### 改法定稿

新增 `tests/advanced_query_linkage/project_picks.py`：**按数据能力解析项目**，而不是按项目代号。
之所以不是「把 9 个 UUID 换成 9 个解析器」，是因为本轮现算证明**老的角色划分已经无解**：
原 `HS` 同时被要求「有 AJE」「RJE 恰好 0 行」「有底稿」「有附注」「六类报表且过期与未过期都有」，
而现库里华氏 `a7fc75e5` 的 adjustments 与底稿都是 0、重药安徽 `0ec33ac9` 有 8 条 AJE 但
**RJE 有 2 条**（原用例断言 RJE == 0）——**没有任何一个活项目能同时满足**。

三条实现纪律写进了模块说明：① 只用显式列的裸 SQL，**禁 `db.get(Project, ...)`**（共享库缺
`projects.amount_unit` 时全列投影会整体 500，正是前十五节那 5 处 500 的同一机理）；
② 取不到候选就**当场失败并打印库内度量前 8 名**，绝不 skip、绝不退化成「空集也算过」；
③ 排序确定（`度量 DESC, id ASC`），同一个库必须选出同一个项目。

#### 13 条能力的现算解析结果（共享库，2026-11-01）

| 能力 | 判据要点 | 本次解析到 | 度量 |
|---|---|---|---|
| `tb_detail` | 审计年度的试算表有行 | 重药安徽_2025 | 196 |
| `balance_direction_columns` | 余额表期末方向列有值 | 重药安徽_2025 | 2,436 |
| `aux_balance_direction_columns` | 辅助余额期末方向列有值 | 陕西华氏_2025 | 132,575 |
| `aux_multi_dimension` | 辅助维度 ≥ 2 个 | 重药安徽_2025 | 23 |
| `ledger_over_fetch_cap` | 生效数据集序时账 > 5,000 行 | 陕西华氏_2025 | 2,532,279 |
| `ledger_over_export_hard_limit` | 生效数据集序时账 > 1,000,000 行 | 陕西华氏_2025 | 2,532,279 |
| `report_full_with_stale_mix` | 报表**既有过期又有未过期** | 重药安徽_2025 | 352 |
| `report_absent` | 有试算表但**没有任何报表** | 和平物流_2025 | 174 |
| `workpapers` | 有未删除底稿 | 宜宾临港店_2025 | 1,026 |
| `disclosure_notes` | 有附注章节 | 【测试】公式同步甲_2025 | 199 |
| `adjustments_aje` | 有 AJE 调整分录 | 重药安徽_2025 | 8 |
| `balance_without_active_dataset` | 有余额表行但该年度无 active 数据集 | 和平药房_2025 | 367 |
| `consolidated_with_notes` | 合并口径且有合并附注数据 | 某测试集团_2098 | 3,514 |

自测 `test_aql_project_picks_pg.py`（**28 passed**，真库）钉三件事：每条能力都真能解析出项目 ·
解析确定（另起一个解析器绕过缓存，两次必须同一个项目）· **一条故意不可满足的能力必须失败**
（反向断言；若 `resolve` 在无候选时静默返回兜底值，上面那些「都能解析」会在数据消失后继续全绿）。
🔴 写这条反向断言时踩到：`pytest.fail` 抛的 `Failed` 继承 **BaseException 而不是 Exception**，
`pytest.raises(Exception)` 抓不到 —— 改用 `pytest.raises(pytest.fail.Exception)`。

#### 首个转换文件与**归因证明**

`test_aql_columns_pg.py`（HS + LN → `tb_detail` / `balance_direction_columns` /
`aux_balance_direction_columns`，年度改取所选项目自己的 `audit_year`）：

| 树 | 结果 |
|---|---|
| 转换前（`HEAD` 原文，临时同名探针跑真库） | **3 failed** —— 1 条 `FORBIDDEN_PROJECT`（403，正是写死 UUID 失效的那种形态）+ 2 条卡在「前置：辽宁卫生服务的方向列有值」 |
| 转换后 | **3 passed** |

即这次改动修的是**真的不工作的用例**，不是换个写法。`BusinessClient` 顺带支持直接传 `Pick`
（项目与年度一起带出，年度不再默认常量 2025）；裸 UUID 的旧调用方行为不变。
`ruff check` 本轮 6 个文件 **All checks passed**。

#### 余下 14 个文件的逐文件能力映射（下一步按此转换）

| 文件 | 原代号 | 对应能力 |
|---|---|---|
| `test_aql_fixtures.py` | WL、YB | `balance_without_active_dataset`、`tb_detail` |
| `test_aql_dataset_predicate_pg.py` | WL、YB | 同上 |
| `test_aql_cycle_scope_pg.py` | HS | `tb_detail` + `disclosure_notes`（复制源） |
| `test_aql_disclosure_source_pg.py` | HS | `disclosure_notes` |
| `test_aql_aux_source_pg.py` | HP、HS、UA | `aux_multi_dimension`、`report_full_with_stale_mix`、可写自建 |
| `test_aql_business_view_pg.py` | HP、HS、WL、YB | `ledger_over_fetch_cap`、`tb_detail`、`workpapers`、`balance_without_active_dataset` |
| `test_aql_builder_scope_pg.py` | HS、UA、YB | `tb_detail`、可写自建、`balance_direction_columns` |
| `test_aql_builder_total_refs_pg.py` | HP、HS、YB | `ledger_over_fetch_cap`、`tb_detail` |
| `test_aql_builder_sql_shape.py` | （无真实项目依赖，按现状复核） | — |
| `test_aql_report_source_pg.py` | HS、UA、UB | `report_full_with_stale_mix`、`report_absent`、可写自建 |
| `test_aql_adjustment_source_pg.py` | HS、UA | `adjustments_aje` + **RJE 断言改按金标准现算**（不再断言恒 0） |
| `test_aql_join_cardinality_pg.py` | HS、UA | `tb_detail`、可写自建 |
| `test_aql_export_pg.py` | HP、HS、UA | `ledger_over_export_hard_limit`、可写自建 |
| `test_aql_templates_pg.py` | UA | 可写自建 |
| `test_aql_writeback_isolation_pg.py` | UA、UB、UP | 可写自建（含 `report_scope='consolidated'` + `consol_note_data`） |

另：`MD` 代号现算 **0 个文件引用**（导入即死码），随上述转换一并删除 `gold.py` 的 9 个常量。
🔴 **`test_aql_adjustment_source_pg.py` 有一处判据必须改而不是换项目**：原来断言「RJE 行数 == 0」，
那是华氏当年**恰好没有** RJE 的偶然事实，不是业务不变式 —— 改为与金标准现算的 RJE 行数相等
（空与非空都对），否则这条用例会在任何有 RJE 的项目上红，而红的原因与被测行为无关。
