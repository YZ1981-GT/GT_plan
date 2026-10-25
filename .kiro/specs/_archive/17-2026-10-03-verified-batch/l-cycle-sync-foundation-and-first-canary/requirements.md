# L 循环双向回写地基与首张 canary — 需求

## 引言

**上游**：umbrella Task 54 的 L slice（`backend/data/workpaper_sync_l_cycle_manifest_slice.json`，162,120 B，冻结 2026-08-31）+ 既存守卫 `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py`（2505 行 / 14 测试类）+ 删除计划 `backend/data/workpaper_sync_l_cycle_deletion_plan.json` + 前七轮共同裁决 FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / KC-1~24。

**本 spec 的 entry 范围**：`xlsx/gt-l1-short-term-loans`（**1 条**，canary 所在 entry 完整纳入，沿用 H/I/J/K 四轮既定形态）。

**承接策略**：以 **KC-1~24 为基准逐条重裁**。KC 已是 F/G/H/I/J 五轮的收口层（KC 各条自带「JC-x / IC-x 在 K 的扩展」标注），故 FC/GC/HC/IC/JC 经 KC 间接覆盖，本 spec 不再逐轮展开。KC-x 在 L 的适用性判定见 `design.md` 的 LC-1 ~ LC-26 对照表；**唯一不适用项（KC-17）必须显式声明，不得静默沿用**。

**既存守卫的边界**：`test_task54_l_cycle_migration.py` 锁的是「**现状诚实记录**」（capability 记 null + BP 齐备 + 计数可重算）。本 spec 锁的是「**改线后目标态**」。凡判据与既存守卫重叠，本 spec **引用既存测试名**而非重写。

## 术语与口径（先立规矩，后面 Req 直接引用）

- **L 域文件集（strict）**：前端 `audit-platform/frontend/src/` 下，路径含 `l{1..8}/` 目录段，**或**文件名匹配 `^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)` 的 `.ts`/`.vue`。🔴 **禁用宽口径 `L[1-8]`**——它会撞 G 循环的 **Level-3 公允价值**命名（见 LC-5）。
- **行数口径**：统一 `len(text.split("\n"))`。`splitlines()` 恒少 1，禁用。
- **计数现算**：所有数字一律从源现算并与 `design.md` 等值比对。禁写死。
- **判据锚点**：用常量名 / 端点字面量 / 形态特征。🔴 **禁写死行号**（`.vue` 行号会漂）。
- **注释剥离**：判 `el-segmented` / 端点调用前必须先剥块注释、行注释、HTML 注释（同长空白替换以保留行号）。
- **按索引删 / 按行身份删**：`removeRow` 首参匹配 `^\$?(?:original)?[Ii]ndex(?::\s*number)?$` 判前者；含 `rowId` 判后者。
- **位置化行身份**：除 `rowKey:` / `rowId:` 赋值外，**`item_id` 模板串里的 `row-${n}` / `row${i}` 段同样计入**（LC-8，slice 的 BP-10 扫描盲区）。
- **canary**：`L1-adj-*` 键组，宿主 sheet = `审定表L1-1`。

## Requirement 1：entry 边界与 manifest 分歧（BP-9）

**User Story:** 作为迁移实施者，我需要 L 循环 8 条 entry 的边界与 manifest 的分歧被显式登记，这样我不会把组件级默认值当成能力裁决。

### 验收准则

1. WHEN 按 slice 的 `selection_rule` 从 manifest 现算 THEN 系统 SHALL 得到恰 8 条 entry，且与 slice 的 `independent_entries` 等值（多一条或少一条都红）。
2. WHEN 读 manifest 里这 8 条 entry THEN 系统 SHALL 断言其 `capability` 全为 `single_onlyoffice`、`html_store` 全为 `unresolved`、**且 manifest entry 上不存在 `capability_target` 字段**。
3. WHEN 读 slice 里同 8 条 THEN 系统 SHALL 断言 `capability` 全为 `null`、`capability_target` 全为 `bidirectional`、`adapter_id` 全为 `null`。
4. WHEN 登记这一分歧 THEN 系统 SHALL 按 LC-1 的表述写明性质是「**overlay 的 `defaults_by_component.GtOnlyOfficeSheet` 默认值填充，不是逐 entry 裁决**」，🔴 **不得写成「数据冲突」或「manifest 错了」**。
5. WHEN 断言 L0 册被排除 THEN 系统 SHALL 用 slice 给出的三条证据而非「模板不存在」：① manifest 全量 entry 现算 `'l0' in entry_id.lower()` 命中 0；② `backend/wp_templates/_index.json` 里 L0 **有**独立条目；③ openpyxl 现读 L0 第 2 张 sheet 名 **含 `函证程序表F0A`**（F0 而非 L0）。

## Requirement 2：LC-1 ~ LC-26 共同裁决只裁一次

**User Story:** 作为后续 lane 的实施者，我需要共同裁决有唯一出处，这样三份 spec 的判据不会各自漂移。

### 验收准则

1. WHEN 任一 lane spec 需要共同裁决 THEN 它 SHALL 只引用 `LC-x` 编号，**不得复述判据内容**。
2. WHEN 本 spec 落 LC-x THEN 每条 SHALL 带「与 KC-x 的关系」标注，取值限于 `✅ 适用` / `⚠️ 扩展` / `⚠️ 变形` / `⚠️ 对偶` / `⚠️ 放大` / `L 独有` / `❌ 不适用`。
3. WHEN KC-17（prefill sheet 名逐字一致）被评估 THEN 系统 SHALL 显式判 **❌ 不适用**，理由是 L 域 `prefill` 命中仅 2 处、无 K 的 51 条分母 ⇒ **空分母，不宣称通过**。🔴 静默沿用即违规。
4. WHEN 复盘检查引用闭合性 THEN LC-1 ~ LC-26 SHALL 无缺号、无重号，且每条至少被一份 spec（含本 spec）引用。

## Requirement 3：写路径与发布门必须按端点字面量判定，且确认门在调用链上

**User Story:** 作为守卫作者，我需要写路径判定不依赖符号名、也不依赖「同文件有 confirm」，这样 8 条 entry 不会集体假红。

### 验收准则

1. WHEN 判 TB 发布门 THEN 系统 SHALL 按端点字面量 `audit-determination/publish-to-tb` 扫描，且 🔴 **必须能匹配反引号模板串**（真实调用形如 `` api.post(`/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`, {...}) ``）。
2. WHEN 统计命中 THEN 系统 SHALL 区分**代码行**与**注释行**（注释行以 `*` / `//` / `/*` 起），并断言：代码命中恰 **8** 处（8 个 `useL{n}FormData` 各 1）。
3. WHEN 扫旧端点 `trial-balance/writeback` THEN 系统 SHALL 断言命中 **8** 处且 **全部为注释**（形如 `* 此前直调旧端点 …`）⇒ 铁律未违反。🔴 只数命中数不判注释即误立缺陷。
4. WHEN 判二次确认门 THEN 系统 SHALL 落「**调用链上有 `ElMessageBox.confirm`**」：现算 confirm 所在文件集与发布门所在文件集**交集为空**（8/8 分居），故判据须验「`useL{n}Adjudication` → `useL{n}FormData` 的调用边存在且 Adjudication 侧有 confirm」。🔴 写成「同文件有 confirm」会让 8 条全假红。
5. WHEN 断言 Adjudication 模块分布 THEN 系统 SHALL 容忍两处路径：`src/composables/`（L1 / L3）与 `components/workpaper/composables/`（L2 / L4 ~ L8），合计 8 个。

## Requirement 4：载体族 L 内部三种并存

**User Story:** 作为守卫作者，我需要载体族判据按三分支写，这样 L3 / L4 不会因「找不到载体」被误判为缺陷、L5 ~ L8 也不会因「有开关」被误判为已达标。

### 验收准则

1. WHEN 现算 8 条 entry 的 `dual_mode_carrier.kind` THEN 系统 SHALL 得到三类且互斥求和为 8：`shared_cycle_composable` **2**（L1 / L2）+ `none` **2**（L3 / L4）+ `child_tab_dedicated_composable` **4**（L5 ~ L8）。
2. WHEN 判 `switch_is_redeemable` THEN 系统 SHALL 承认**三态**：`true` 2（L1 / L2）· `null` 2（L3 / L4，**无开关可谈，非 false**）· `false` 4（L5 ~ L8，开关存在但 inert）。🔴 把 `null` 当 `false` 即口径错。
3. WHEN 判 L5 ~ L8 的 inert THEN 系统 SHALL 要求**三条同时成立**：① 子 Tab 里有 `el-segmented`；② 以 mode 为条件的 `v-if` / `v-else-if` / `v-show` 现算 **0** 处；③ 该文件内 `GtOnlyOfficeSheet` 命中 **0** 次。
4. WHEN 判 L1 / L2 的 redeemable THEN 系统 SHALL 验宿主模板里存在以 `currentMode` 为条件的 `GtOnlyOfficeSheet` 挂点（形态锚点，非行号）。
5. WHEN 判 L3 / L4 的 `none` THEN 系统 SHALL 验：宿主不 import 任何 `use*DualMode`，且唯一的 `GtOnlyOfficeSheet` 挂点是 `v-else` 兜底渲染器（服务未迁移 sheet `GT_Custom`），**不是模式切换**。

## Requirement 5：canary `L1-adj-*`（`审定表L1-1`）端到端闭环

**User Story:** 作为迁移实施者，我需要一张真库有非空载荷、宿主 sheet 明确、发布门链路已通的表作首例，这样闭环能真验而不是造数据。

### 验收准则

1. WHEN 按 canary 硬标准筛选 THEN 系统 SHALL 现算确认 `L1-adj-*` 是**唯一**合格者：① 真库 `checklist_responses` 里 `item_id ~ '^L1-'` 现算 **33** 行且 `remark` 非空 **33**；② 属 entry `xlsx/gt-l1-short-term-loans`；③ 非 parent_duplicate（L 域全域 0）；④ 单 sheet 单键组。
2. WHEN 排除其余候选 THEN 系统 SHALL 逐条给出现算理由：L2 的唯一非空载荷（`L2-L2-3-entries`，581 字节）**落在 `wp_code='G8'` 的底稿上**（LC-22）· L3 / L4 / L5 载荷全为 `'[]'` 或 `NULL` · L6 / L7 / L8 真库 **0 行**。
3. WHEN 确认 canary 宿主 sheet THEN 系统 SHALL 用符号锚点而非行号：`useL1FormData.ts` 里 `DETERMINATION_SHEET_NAME` 的值等于 `'审定表L1-1'`，且 `L1-adj-` 的解析正则形如 `^L1-adj-(\d+)-(\w+)$`。
4. WHEN 描述 `{n}` 的语义 THEN 系统 SHALL 写明它是 **`categoryIndex`**（对应默认分类「信用 / 抵押 / 保证 / 质押」，对齐源模板顺序），故**有语义锚但仍是位置化**——改分类顺序或增删分类即错位。
5. WHEN 定义 canary 的去位置化动作 THEN 系统 SHALL 要求把 `{n}` 换成**分类稳定码**，并在 contract 里登记 `stable_key` 与旧键的迁移映射；旧键 SHALL 保留只读兼容期。
6. WHEN 核 canary 与跨循环依赖的关系 THEN 系统 SHALL 断言 `h2L1LoanPull.ts` 消费的是 `L1-L1-5-rows` 与 `L1-int-{n}-{field}`（利息测算），**不含 `L1-adj-*`** ⇒ canary 改造不打断 H2-10。🔴 此断言必须现算，不得引用本文档结论。
7. WHEN 真库载荷被描述 THEN 系统 SHALL 如实写明**只第 1 行有真数值**（其余三行字段值均为 `'0'`），故闭环用例的断言 SHALL 针对第 1 行，不得假设四行都有业务值。
8. WHEN canary 的 contract 被起草 THEN 字段映射 SHALL 只映 `remark`；`conclusion` SHALL 标为不使用（L 域真库 `conclusion` 非空数现算 **0**，LC-24）。

## Requirement 6：L1 entry 的 BP 收口

**User Story:** 作为实施者，我需要 L1 这条 entry 上的阻塞项被逐条归位，这样我知道哪些能做完、哪些卡外部供给。

### 验收准则

1. WHEN 读 L1 的 `capability_target_blocked_by` THEN 系统 SHALL 现算得到 7 项：BP-1 / BP-2 / BP-3 / BP-5 / BP-7 / BP-9 / **BP-10**，并断言 L1 是 8 条里**唯一**含 BP-10 的。
2. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 本 spec SHALL 标 `[ ]*`（依赖外部供给：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针），**不承诺完成**。
3. WHEN 处理 BP-5（orphan）THEN 系统 SHALL 现算 L1 的 orphan 孪生模块 = `src/composables/useL1DualMode.ts`，断言它零生产消费边、是一阶 orphan（barrel 不存在 ⇒ 二阶恒 0），并按删除计划在 step 9 之前可删。
4. WHEN 处理 BP-7（notice）THEN 系统 SHALL 断言 L 域 notice 符号命中 **0**，并要求 notice 与 sync bridge 的编辑宿主**一并落位**；判据 SHALL 写明所用符号名。
5. WHEN 处理 BP-10（位置化）THEN 系统 SHALL 按 LC-8 的扩展口径收口，**不得只按 slice 的 `total_hits: 1`**（详见 Requirement 11）。
6. WHEN 处理 BP-9 THEN 系统 SHALL 按 Requirement 1 第 4 条登记，不重复裁决。
7. WHEN 共享载体 `useCycleHtmlOoDualMode.ts` 的消费面被评估 THEN 系统 SHALL 现算窄生产边 **3** 处（L1 宿主 + L2 宿主 + `shared/CycleStandaloneProcedureShell.vue`），并断言改线后**剩 1**（Shell），且 Shell 自身仍被 `GtCycleAProgramRouter.vue` 消费 ⇒ 🔴 **该共享件是「部分收缩」，不可删**。
8. WHEN 共享基类 `useWorkpaperEntryDualMode.ts` 被评估 THEN 系统 SHALL 现算 L 域贡献 **0** ⇒ 该基类消费面**不变**，改线不触及。

## Requirement 7：模板层登记（不修，只冻结基线）

**User Story:** 作为实施者，我需要模板层缺陷有基线，这样后续改动会被发现而不是静默漂移。

### 验收准则

1. WHEN 现读 `backend/wp_templates/L/` THEN 系统 SHALL 断言 9 册 / **100** sheets，其中 owned **90**（= 100 − L0 的 10），且 8 册的 sha256 与 sheet_count 与 slice 的 `template_ref` 等值。
2. WHEN 登记 sheet 名字符缺陷 THEN 系统 SHALL 按 LC-10 收 **3** 处空格（L1 前导 / L4 尾随 / L4 内部），🔴 **禁归一化**——它们是 router 兜底规则的真实输入。
3. WHEN 登记 `#REF!` 死公式 THEN 系统 SHALL 现算 **8** 处 = `逾期贷款检查表L1-7` 4 + `逾期贷款检查表L3-7` 4，并按 LC-25 要求**两张都断言**（L1 属本 spec、L3 属 lane 2，本 spec 只冻结 L1 侧基线并登记同源关系）。
4. WHEN 登记 definedName 断链 THEN 系统 SHALL 现算 owned 的 total / broken / ok 三个数并与 `design.md` 等值比对（🔴 **禁写死**，清理污染后这三个数会变），且断言：污染只在 L3 / L5 / L6 / L7 四册、四册的 broken 数**彼此相同**、**L1 册为 0/0/0**。
5. WHEN 登记 footer 形态 THEN 系统 SHALL 现算 `&P/&N` 重复两次的 **3** 处（L2 / L3 / L4 的实质性程序表），并断言 **L1 的程序表 footer 正常**（单个 `&P/&N`）⇒ 5 正 3 误。
6. WHEN 登记幽灵行 THEN 系统 SHALL 用 `max_row − last_value_row` 现算，并声明该口径（openpyxl 的 `max_row` 含无值但有格式的行）。
7. WHEN 本 Requirement 的任一计数被写入守卫 THEN 它 SHALL 现算比对，禁写死。

## Requirement 8：结构性零必须现算且带变异证明

**User Story:** 作为质控，我需要「某项为 0」不是漏扫的结果，这样守卫不会空跑通过。

### 验收准则

1. WHEN 断言结构性零 THEN 系统 SHALL 覆盖 **10** 项并逐项现算：L 前缀契约 0 · L adapter 0 · parent_duplicate 0 · excluded_pilot 0 · barrel 0 · 二阶 orphan 0 · 真实越界引用 0 · 真实跨 sheet 断链 0 · 真库 `conclusion` 非空 0 · L6/L7/L8 真库载荷 0。
2. WHEN 每项零被断言 THEN 系统 SHALL 同时给出**非空分母**或显式标注「结构性零」；🔴 不得只写「为 0 故通过」。
3. WHEN 变异证明被要求 THEN 系统 SHALL 对至少「L adapter 0」「barrel 0」「真实越界 0」三项构造反例（人为注入后守卫必红），证明扫描非空跑。
4. WHEN 契约目录被现算 THEN 系统 SHALL 声明口径：目录下 `.json` 总数为现算值（slice 冻结时为 11，现算已增长）、生产口径需排除 `_` 前缀的 candidate 样例，且断言 **L 前缀契约恒 0**。🔴 总数禁写死。
5. WHEN `adapter_id` 被现算 THEN 系统 SHALL 分开两个分母：「全 manifest 非空 `adapter_id` 数」与「**L 域非空数（恒 0）**」，并声明 manifest **无 `adapter_registered` 字段**（「契约已发」≠「adapter 已注册」）。

## Requirement 9：空分母纪律

**User Story:** 作为质控，我需要「没有 contract 所以 Property 通过」这种重言式被显式拒绝。

### 验收准则

1. WHEN 某 Property 的 L 侧分母为空 THEN 系统 SHALL 在 `design.md` 的 Property 清单里标 `不宣称通过`，并指明承载该部分的既有测试文件。
2. WHEN 分母非空 THEN 系统 SHALL 写出分母的现算方式（扫什么、排除什么、得几个）。
3. WHEN KC-17 被判不适用 THEN 理由 SHALL 是「分母为空」而非「L 没有这个问题」。

## Requirement 10：L 域文件集口径必须 strict

**User Story:** 作为守卫作者，我需要 L 域文件集不把 G 循环的 Level-3 公允价值文件算进来，这样所有比例类判据的分母是对的。

### 验收准则

1. WHEN 建立 L 域文件集 THEN 系统 SHALL 用 strict 口径（见术语节），现算文件数并与 `design.md` 等值比对。
2. WHEN 验口径有效性 THEN 系统 SHALL **两侧都验**：strict 集合的现算值，以及宽口径多出的文件集合——后者 SHALL 恰为 G / H 循环的跨用文件（`useG9L3Reconciliation` / `useG10L3Reconciliation` / `G9TabL3Reconciliation.vue` / `G10TabL3Reconciliation.vue` / `g10L3Cross*` / `h2L1LoanPull` 及其测试），且断言其中**无一属 L 循环 entry**。
3. WHEN 任何「按索引删 N 处」「位置化 N 处」类比例被写入 THEN 分母 SHALL 声明为 strict 口径。🔴 混用口径即判据失效。
4. WHEN `h2L1LoanPull.ts` 被处理 THEN 系统 SHALL 明确：它**不属** L 域文件集，但是 L1 的**下游消费者**，须按 Requirement 12 单独约束。

## Requirement 11：item_id 层位置化行身份必须纳入 BP-10

**User Story:** 作为迁移实施者，我需要 BP-10 的范围覆盖 item_id 里的行序号段，这样去位置化不会只改了一处就宣称完成。

### 验收准则

1. WHEN 现算位置化行身份 THEN 系统 SHALL 用**两组**扫描口径并分别报数：① slice 既有口径（`.vue`/`.ts` 里 `rowKey:` / `rowId:` 赋值）；② 🔴 **本 spec 新增口径**（`item_id` / `itemId` 模板串里的 `row-${…}` / `row${…}` / `-${n}-` 序号段）。
2. WHEN 报口径 ② 的结果 THEN 系统 SHALL 现算并与 `design.md` 等值比对，且按模块列出分布；🔴 **不得沿用 slice 的 `total_hits: 1`**——那是口径 ① 的结果。
3. WHEN 登记分隔符差异 THEN 系统 SHALL 断言存在**两型**：`row-${…}`（带连字符）与 `row${…}`（不带），并指出后者仅出现在两个 L6 Disclosure 组件。
4. WHEN 登记索引基准差异 THEN 系统 SHALL 断言存在写侧用 `${i + 1}`、读侧用 `${i}` 的模块对，并把它作为「读写键形态不闭合」的候选风险项登记（本 spec 不修，归 lane 3）。
5. WHEN 本 spec 收口 L1 的位置化 THEN 范围 SHALL 限于 L1 的 4 处（`useL1FormData.ts` 的 `L1-adj-${n}-*` 与泛型工厂 `L1-${prefix}-${n}-${field}`）+ slice 口径 ① 的 1 处；其余模块归 lane 2 / lane 3。
6. WHEN slice 的扫描盲区被登记 THEN 系统 SHALL 如实写明「slice 的 `dynamic_row_identity` 口径不覆盖 item_id 拼接」，🔴 **不得表述为 slice 记错**——它的口径内结论是对的。

## Requirement 12：跨循环键冻结（H2 ← L1）

**User Story:** 作为实施者，我需要 L1 键的下游消费者被冻结登记，这样改键不会静默打断 H2-10。

### 验收准则

1. WHEN 现算 L1 的下游消费者 THEN 系统 SHALL 定位 `components/workpaper/composables/h2L1LoanPull.ts`，并断言其导出的拉取函数服务于 **H2-10 一般借款表**。
2. WHEN 登记其读取路径 THEN 系统 SHALL 断言**双路径并存**：优先按 `item_id === 'L1-L1-5-rows'` 读 JSON 数组，失败回退旧 flat 键正则 `^L1-int-(\d+)-(\w+)$` 按行号归并。
3. WHEN 登记口径转换风险 THEN 系统 SHALL 指出利率归一化函数靠 **`> 1` 启发式**判「小数 vs 百分数」，并把「年利率恰为 1（即 100%）时判错」作为已知缺陷登记（本 spec 不修，属 H2 spec 范围）。
4. WHEN 冻结基线 THEN 系统 SHALL 断言这两组键（`L1-L1-5-rows` / `L1-int-*`）在本 spec 内**不被改动**；若后续 lane 需改，SHALL 先在 `h2-h6-h10-pilot-cross-reference-lanes` 侧同步。
5. WHEN 断言 canary 安全性 THEN 系统 SHALL 现算确认 `h2L1LoanPull.ts` 不引用 `L1-adj-` ⇒ canary 与该依赖正交。

## Requirement 13：五处扫描误报必须如实登记

**User Story:** 作为质控，我需要本轮自查出的误报被写进文档，这样后续实施者不会照着误报去「修」不存在的缺陷。

### 验收准则

1. WHEN 登记误报 THEN 系统 SHALL 覆盖 **5** 项并各自写明「错误口径 → 正确口径 → 修正后现算值」：① 越界引用（按本 sheet `max_row` 比跨 sheet 行号 → 按引用目标 sheet 的 `max_row` → **0**）；② 跨 sheet 断链（正则把 `#REF!` 的 `REF` 当 sheet 名 → 先排除 `#REF!` → **0**）；③ 合计漏加小计（「SUM 区间含标签行」对横向 SUM 无意义 → 逐行核结构 → **0**）；④ OCR（`recognize` 撞 `unrecognizedRows` → 排除业务词 → 现算值）；⑤ L 域文件集（宽口径撞 G Level-3 → strict → 现算值）。
2. WHEN 登记第 ③ 项 THEN 系统 SHALL 写明 `审定表L4-1` 的 `=B11+B16+B17` 形态是**正确的避重复**（小计1 + 小计2 + 单行），🔴 不得列为缺陷。
3. WHEN 守卫实现这些判据 THEN 它 SHALL 同时保留**修正后**的扫描，且对每项构造一个「用错误口径会红、用正确口径应绿」的自检用例。
