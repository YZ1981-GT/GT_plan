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
