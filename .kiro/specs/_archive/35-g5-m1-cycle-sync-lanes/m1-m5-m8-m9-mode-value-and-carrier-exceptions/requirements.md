# M1 / M5 / M8 / M9 —— mode 取值与载体例外收口 · 需求

## 引言

**上游**：`m-cycle-sync-foundation-and-first-canary`（MC-1 ~ MC-29 共同裁决的唯一出处）+ `m2-m3-m4-m7-m10-sheet-map-drift-and-collapse`（BP-6 / BP-8 判据的定义方）+ M slice + 删除清册 + 既存守卫 `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py`。

**本 spec 的 entry 范围（4 条，全名）**：
- `xlsx/gt-m1-dividends-payable`（M1D）
- `xlsx/gt-m5-surplus-reserve`（M5S）
- `xlsx/gt-m8-general-risk-reserve`（M8G）
- `xlsx/gt-m9-other-comprehensive-income`（M9O）

**切分依据**：本 spec 是**不含 BP-4 的补集**（扣掉 canary entry `xlsx/gt-m6-retained-earnings`）。

🔴 **本 spec 的缺陷集合不齐整是故意的，须先读这段再看后面的 Req**：切分以 BP-4（M 独有、最贵的一条）为主轴，lane 2 = 含 BP-4 的 5 条，本 spec = 补集。本 spec 内部按 entry 分支处理：**M1 → BP-6**（唯一含 6 不含 4 的）· **M8 → BP-8** · **M9 → 载体 `none` + 双孪生皆 orphan** · **M5 → 只公共项（干净对照组）**。硬凑齐整会让 BP-4 横跨两份 spec，判据必然漂移 —— 这是明确排除的方案。

🔴 **共同裁决只引用编号**：本 spec 出现的 `MC-x` 一律只写编号，**不复述内容**。

## Requirement 1：四条 entry 的 BP 归属现算门

**User Story:** 作为实施者，我需要四条 entry 的阻塞项被逐条现算归位，这样我能确认本 spec 恰是不含 BP-4 的补集。

### 验收准则

1. WHEN 现算四条的 `capability_target_blocked_by` THEN 系统 SHALL 得到：M1 **9** 项 · M5 **8** 项 · M8 **9** 项 · M9 **8** 项，且 🔴 **四条全部不含 BP-4**。
2. WHEN 断言补集完备性 THEN 系统 SHALL 现算全 M 域不含 BP-4 的 entry 集合，断言它恰是本 spec 4 条 **加上 canary entry `xlsx/gt-m6-retained-earnings`**（5 条），并断言 `5 + 5 = 10` == entry 总数。
3. WHEN 现算区分项 THEN 系统 SHALL 断言：**M1 独含 BP-6**（本 spec 唯一）· **M8 独含 BP-8**（本 spec 唯一）· **M5 与 M9 只含公共 8 项**。
4. WHEN M5 与 M9 的 BP 集合相同却归属不同缺陷组 THEN 系统 SHALL 显式写明理由：M9 的差异不在 BP 层而在 **载体层**（`dual_mode_carrier.kind == 'none'`）与 **SHEET_MAP 层**（2 处 missing 在 orphan 模块），而 M5 两层都干净 ⇒ M5 是本 spec 的**对照组**。
5. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 系统 SHALL 标 `[ ]*` 并引用 foundation 的登记，**不重复裁决**。
6. WHEN 处理 BP-5 / BP-7 / BP-9 / BP-10 / BP-11 THEN 系统 SHALL 引用 MC-16 / MC-12 / MC-1 / MC-8 / MC-26，**不重新裁决**。

## Requirement 2：M9 载体 `none` 与双孪生皆 orphan（MC-2）

**User Story:** 作为实施者，我需要 M9 的「无载体」形态被正确判定，这样它不会因「找不到活载体」被误判为已迁移、也不会被误判为可裁 single。

### 验收准则

1. WHEN 现算 M9 的载体 THEN 系统 SHALL 断言 `dual_mode_carrier.kind == 'none'` 且 `switch_is_redeemable` 为 `false`，并断言它是 10 条里**唯一**一条。
2. WHEN 现算 M9 的孪生模块 THEN 系统 SHALL 断言**两个都是 orphan**：`useM9DualMode.ts`（自带完整实现）与 `useM9EntryDualMode.ts`（薄封装），两者生产边与测试边**均为 0**；并断言 `entries_with_two_orphan_twins` 现算 **1**。
3. WHEN 现算 M9 宿主 THEN 系统 SHALL 断言 `GtM9OtherComprehensiveIncome.vue` 剥注释后**没有 `el-segmented`**、`ui_toolbar_gate.anchor` 为 `null`（`entries_without_any_ui_gate_anchor` 现算 1），且其 `GtOnlyOfficeSheet` 挂点是**未迁移 sheet 的兜底渲染器**而非模式切换。
4. WHEN 现算 M9 的 mount 数 THEN 系统 SHALL 断言它是 **1**（其余 9 条各 2）⇒ 全域 mount 合计 **19**。
5. WHEN M9 的 mode 类型形态被登记 THEN 系统 SHALL 断言 `useM9EntryDualMode.ts` 用**类型引用** `WorkpaperRenderMode` 而非字面量联合、且**无 localStorage 键** ⇒ 🔴 扫字面量枚举与扫 storage 键的判据**都会漏掉它**（引用 MC-16）。
6. WHEN 🔴 不得据此裁 single THEN 系统 SHALL 断言三条：① M9 有 HTML 对端（`checklist_responses` 通道实测存在）⇒ AC 12.8 禁 `single_onlyoffice`；② M9 册有真实业务 sheet（现算 9 张 / 公式格 470，10 册第二多）⇒ AC 12.9 的 `single_html` 不适用；③ 宿主经 `htmlRendererRegistry` 可达 ⇒ 非 `unreachable`。「没有开关」**不是** AC 12.9 的判据。
7. WHEN notice 落位被定义 THEN 系统 SHALL 引用 MC-12 断言 M9 的 notice **须与 sync bridge 的编辑宿主一并落位**（无既成锚点可挂）。

## Requirement 3：M9 的 SHEET_MAP 2 处 missing 登记不修（MC-23）

**User Story:** 作为实施者，我需要 M9 的映射错位被登记但不被当作活缺陷修，这样我不会去修一个不可达模块。

### 验收准则

1. WHEN 现算 M9 的 SHEET_MAP THEN 系统 SHALL 断言 `declared 8 = hit 6 + missing 2`，两处分别是 `其他综合收益实质性程序表M9A` → 真名 `'其他综合收益实质性程序表 M9A'`（丢中间空格）与 `OCI核对表M9-4` → 真名 `其他综合收益核对表M9-4`（**中英混写**，整段不同）。
2. WHEN 归属被判定 THEN 系统 SHALL 断言这 2 处落在 **orphan 模块**里（`defect_pairs_in_orphan_modules` 现算 2）⇒ **M9 不挂 BP-4**，故本 spec **只登记不修**。
3. WHEN 与全域计数的关系被写明 THEN 系统 SHALL 断言 `全域 missing 11 = lane 2 的活映射 9 + M9 的 orphan 2`，且 `entries_with_sheet_map_defects == 6` 与「BP-4 登记 5 条」**两个数并存**不互相覆盖。
4. WHEN 删除动作被执行 THEN 系统 SHALL 断言删掉 M9 两个 orphan 后这 2 处错位**随之消失**（不需要独立修复项），并现算验证 missing 从 11 降到 9。
5. WHEN 🔴 误修风险被登记 THEN 系统 SHALL 写明：若有人先「修」了 orphan 里的 SHEET_MAP 再删文件，等于做了无效功；判据须在删除前断言该模块**无人消费**。

## Requirement 4：BP-6 的 M1（跨 spec 交叉引用）

**User Story:** 作为实施者，我需要 M1 的 mode 枚举统一与 lane 2 用同一判据，这样两份 spec 不会各写一套。

### 验收准则

1. WHEN 现算 M1 的 mode 枚举 THEN 系统 SHALL 断言 `useM1DualMode.ts` 声明为 `'structured' | 'onlyoffice'`，与 M2 / M3 / M4 同批。
2. WHEN 判据归属被指定 THEN 系统 SHALL 🔴 **引用 lane 2 定义的 BP-6 判据函数**，不得在本 spec 另写一套；并断言 BP-6 成员总数 `3（lane 2）+ 1（本 spec）= 4`。
3. WHEN 统一被执行 THEN 系统 SHALL 断言该动作**只对 orphan 生效**（活路径 0 键，引用 MC-16）⇒ 与 M1 的 orphan 删除动作合并执行。
4. WHEN 🔴 分界线不重合被登记 THEN 系统 SHALL 引用 MC-15 断言 M1 同时属「BP-6 批（M1~M4）」与「item_id 重复前缀批（M1~M3）」⇒ M1 是**两条分界线同侧**的唯一 entry 之一，与 M4 的「两侧归属不同」形成对照。

## Requirement 5：BP-8 的 M8 —— Q8A 无拦截与「删除」sheet（MC-27）

**User Story:** 作为实施者，我需要 M8 的历史 sheet 折叠被修，且不把源模板作者标注的「删除」sheet 当成删除对象。

### 验收准则

1. WHEN 现算 M8 的折叠 THEN 系统 SHALL 断言 **11 张 sheet → 10 个 dispatch code**，来源是 `一般风险准备实质性程序表 Q8A  (修订前)`（**双空格**）被折叠到本版 `procedure`。
2. WHEN 根因被区分 THEN 系统 SHALL 断言 M8 与 M10 的成因**不同**：M8 是**完全没有拦截代码**（`实质性程序表` 先命中），M10 是**写了拦截但排在后面**（不可达死代码）⇒ 🔴 两者修法都是「把历史 sheet 判断排到前面」，但 M8 需**新增**代码、M10 需**移动**代码。
3. WHEN 修法被执行 THEN 系统 SHALL 引用 MC-27 的正面样板（foundation 抽出的共用判据函数），并断言修后 `Q8A (修订前)` 不再命中 `procedure`。
4. WHEN `针对性测试M8-5-删除` 被处理 THEN 系统 SHALL 断言「删除」二字是**源模板作者的标注**，该 sheet 落 OO 兜底是**正确处置**；🔴 **不得据此裁 single、不得真删 sheet**（引用删除清册 `excluded_from_plan`）。
5. WHEN M8 的 OO 兜底数被断言 THEN 系统 SHALL 现算 **2** 张（`GT_Custom` + `针对性测试M8-5-删除`），并声明它与按 hidden 状态分类的差异（引用 MC-11 第 ⑤ 项）。
6. WHEN 判据归属被指定 THEN 系统 SHALL 🔴 **引用 lane 2 定义的 BP-8 判据**，并断言 BP-8 成员总数 `2（lane 2）+ 1（本 spec）= 3`。
7. WHEN 后端根治的关系被写明 THEN 系统 SHALL 引用 MC-24 断言后端单一过滤是根治、本条是前端补救，两者**不互相替代**。

## Requirement 6：M1 的科目性质分支（MC-22）

**User Story:** 作为实施者，我需要 M1 的科目性质被现算确认为负债类，这样四表判据与 TB 发布口径不会按权益类写。

### 验收准则

1. WHEN M1 的科目性质被断言 THEN 系统 SHALL **现算科目码确认**它属**负债类**，🔴 **不得推演**（判据须落真实科目码或 `wp_account_mapping` 的现算查询结果）。
2. WHEN 与其余 9 条的对照被写明 THEN 系统 SHALL 断言 M2 ~ M10 属**权益类**（贷方），M1 是 10 条里**唯一**的负债类 ⇒ 四表判据按**两分支**写（引用 MC-22）。
3. WHEN TB 发布口径被验 THEN 系统 SHALL 现算 M1 的发布调用实参形态，断言它与权益类的取数口径一致或不一致，并把结论如实登记（🔴 不得预设答案）。
4. WHEN 本条的分母被声明 THEN 系统 SHALL 写明这是 1 : 9 的分支，不是 5 : 5 —— 判据写成「M 全域都是权益类」会让 M1 假绿。

## Requirement 7：M1 ↔ K3 跨循环键守卫（MC-19，已归档 spec 未做项）

**User Story:** 作为实施者，我需要「M1 推送的子表键与 K3 推送的键无交集」这条守卫被真正落地，这样两个循环不会互相覆盖子表数据。

### 验收准则

1. WHEN 已归档 spec 的欠账被确认 THEN 系统 SHALL 现读 `_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md`，断言该守卫任务**未勾选** ⇒ 🔴 **不得因该 spec 已归档就认为已完成**。
2. WHEN 守卫被实现 THEN 系统 SHALL 现算 M1 推送的子表键集合与 K3 推送的键集合，断言**交集为空**；若不为空则逐键登记并判红。
3. WHEN 键集合的取法被定义 THEN 系统 SHALL 从代码现算（`ITEM_PREFIX` 常量 + 模板串展开），🔴 **不得只查真库**（真库 M 域仅 6 行，分母不足）。
4. WHEN 方向被写明 THEN 系统 SHALL 引用 MC-19 断言 M 是**被引用方**（与 L 被 H2 引用的方向相反），并断言本 spec 不改动 M 键的四类跨循环消费者。
5. WHEN 守卫覆盖面被定义 THEN 系统 SHALL 覆盖 M1 与 K3 两侧，且 🔴 扩展到「任意两个循环的子表键集合两两无交集」以防同类复发（现算两两比对，违例逐条登记）。

## Requirement 8：M1 真库的 AI 会话记录行处置（MC-18）

**User Story:** 作为实施者，我需要真库里那行唯一非空的记录被正确定性，这样它不会被当成业务载荷用于闭环验证。

### 验收准则

1. WHEN 现算 M1 真库 THEN 系统 SHALL 断言 **2** 行：`M1-M1-2-full-data`（`remark` 为 `NULL`）与 `M1-review-session-20260725075149`（`remark` 现算约 261 字节，内容含 `session_id`）。
2. WHEN 后者被定性 THEN 系统 SHALL 断言它是 **AI 复核会话记录不是业务数据** ⇒ 🔴 **不得用于闭环验证**，也不得据此宣称「M1 有真载荷」。
3. WHEN 处置被裁定 THEN 系统 SHALL 在「迁移到专用表」与「只登记不动」之间**显式裁定并写明理由**（默认只登记 + 标 `[ ]*`，因动生产数据需业务确认）。
4. WHEN 契约字段映射被起草 THEN 系统 SHALL 断言只映 `remark`、`conclusion` 标不使用（M 域 `conclusion` 非空现算 **0**，引用 MC-18）。
5. WHEN 🔴 键命名空间污染被检查 THEN 系统 SHALL 断言 `M1-review-session-*` 这类键**不符合** `ITEM_PREFIX` + sheet 段 + field 段的三段式命名（引用 MC-15），并把它登记为「命名空间被非业务用途借用」的实证。

## Requirement 9：definedName 污染溯源（MC-9）

**User Story:** 作为实施者，我需要 M1 与 M9 的污染来源被登记，这样清理时不会误以为是 M 循环自己产生的。

### 验收准则

1. WHEN 现算本 spec 4 册的 definedName THEN 系统 SHALL 断言 **M9 与 M1 显著高于 M5 / M8**，而 M5 / M8 的 broken 数与其余 6 册**彼此相同**（引用 MC-9）。
2. WHEN 污染源被溯源 THEN 系统 SHALL 断言 M1 / M9 另含**中文名与跨循环名**（至少列出 3 个样本，如 `_1、受本循环影响的相关交易和账户余额` / `_1固定资产数据库_筛选打印` / `CarryKnown`）⇒ **M1 / M9 是从别的底稿册复制来的**。
3. WHEN 两种新形态被容忍 THEN 系统 SHALL 断言解析器对 `{#N/A,…,"BBPREP"}`（打印区域宏残留）与 `[1]Breakdown!#REF!`（外部工作簿引用）**不崩**。
4. WHEN 清理归属被声明 THEN 系统 SHALL 🔴 断言**本 spec 不清理污染**（归全域批次），只登记溯源结论 + 冻结基线。
5. WHEN 与 L 的关系被写明 THEN 系统 SHALL 断言短名污染（`AFV` / `bs` / `CCD` / `CDE` / `DEX` / `EDC` / `FAD` 等）与 L 循环**同源**，而中文名与跨循环名是 M 独有 ⇒ 两类污染来源不同，清理时不可一刀切。

## Requirement 10：`procedure` 键的三种 hit 写法作正面样板（MC-23）

**User Story:** 作为实施者，我需要把三条写对了的 `procedure` 声明抽成正面样板，这样 lane 2 的 5 处修正有可比对的参照。

### 验收准则

1. WHEN 现算 `procedure` 键的 hit 集合 THEN 系统 SHALL 断言恰 **3** 条且**全在本 spec**：M1 `'应付股利实质性程序表M1'`（🔴 **10 册唯一不带 `A`**）· M5 `'盈余公积实质性程序表 M5A'`（带中间空格）· M8 `'一般风险准备实质性程序表 M8A '`（带中间 + 尾随空格，与真名完全一致）。
2. WHEN 🔴 「hit 不等于写法统一」被登记 THEN 系统 SHALL 断言这 3 条**写法互不相同** ⇒ 它们是「碰巧与真名一致」而非「按统一规则生成」⇒ **不能直接当规则抄，只能当逐条比对的参照**。
3. WHEN M1 的异类形态被登记 THEN 系统 SHALL 断言 M1 是 10 册里唯一 `procedure` 不带 `A` 的（真 sheet 名也不带），🔴 这解释了为何 canary 选型排除 M1（引用 foundation 的排除理由）。
4. WHEN 与 M6 的对照被写明 THEN 系统 SHALL 断言 **M6 根本没有 `procedure` 键**（只 6 对，走 `skip-q6a` 专用分支）⇒ `procedure` 键的状态是「4 种写法 + 1 处缺键」（引用 MC-23）。
5. WHEN 正面样板被交付 THEN 系统 SHALL 产出一份「sheet code → 真名」的逐条对照表供 lane 2 引用，并断言该表的每个值都 ∈ 权威册 sheet 名集合（现算）。

## Requirement 11：M5 作为干净对照组

**User Story:** 作为守卫作者，我需要一条各项都干净的 entry 作对照，这样能证明判据不是一律判红。

### 验收准则

1. WHEN M5 被断言为对照组 THEN 系统 SHALL 现算四项全干净：`must_fix_before_wiring` 只 8 项公共 · SHEET_MAP **9/9/0** · `switch_is_redeemable == true` · 载体 `per_entry_wrapper_over_shared_base`。
2. WHEN 对照作用被落位 THEN 系统 SHALL 要求本 spec 的每条「缺陷判据」都在 M5 上跑一遍并**应绿** ⇒ 🔴 证明判据能区分「有缺陷」与「无缺陷」，而非一律判红。
3. WHEN M5 与 canary M6 的差异被写明 THEN 系统 SHALL 断言 M5 仅在两项上劣于 M6：公式格 **193 > 175**、且 M5 **无「正确处理先例」**（M5 册无 Q 表）⇒ 这正是 canary 选 M6 不选 M5 的理由（引用 foundation）。
4. WHEN M5 的真库状态被断言 THEN 系统 SHALL 现算 **0** 行 ⇒ 闭环同样标 `[ ]*`。

## Requirement 12：位置化与 removeRow 在本 spec 的份额收口

**User Story:** 作为实施者，我需要本 spec 名下的位置化行身份与 removeRow 变体被完整枚举处理，含 M9 的特有模块。

### 验收准则

1. WHEN 现算本 spec 份额 THEN 系统 SHALL 按 MC-8 的四族口径分别报数，覆盖 4 条 entry 对应的 `useM{n}Adjudication.ts` / `useM{n}FormData.ts` / `M{n}Tab*.vue`，**以及 M9 特有的 `useM9OciReconcile.ts`**。
2. WHEN `useM9OciReconcile.ts` 被处理 THEN 系统 SHALL 断言它是持久化键族 11 个命中文件里**唯一非 `useM{n}Adjudication.ts` 形态**的一个，且同样恰 **1** 处 `const n = idx + 1` ⇒ 判据不能只扫 `Adjudication` 命名。
3. WHEN removeRow 变体被枚举 THEN 系统 SHALL 按 MC-7 四元组逐一登记本 spec 名下变体，含 **`M9TabDetail.vue` 的 `handleRemove(displayIndex)` → `removeRow(globalIdx)`** 这条双套映射链。
4. WHEN 🔴 双层索引映射被消除 THEN 系统 SHALL 断言两层**同时**消除（引用 MC-6），并构造用例证明只改一层会造成新的错位。
5. WHEN 去位置化被执行 THEN 系统 SHALL 🔴 **复用 foundation 在 M6 上建立的正面样板形态**（引用 MC-6：M 域零可抄模块），断言**不新造第二种形态**（与 lane 2 同一形态）。
6. WHEN item_id 命名轴被处理 THEN 系统 SHALL 引用 MC-15 断言 M1 属重复前缀型 + snake_case，M5 / M8 / M9 属不重复型 + kebab-case ⇒ 🔴 **本 spec 内部横跨两批**，迁移映射按 entry 分别写。
7. WHEN 熵键假象与双基准被处理 THEN 系统 SHALL 引用 MC-8，断言迁移映射同时处理 0-based 与 1-based。

## Requirement 13：模板层基线引用（不修）

**User Story:** 作为实施者，我需要本 spec 的模板层基线只引用不改。

### 验收准则

1. WHEN 模板层事实被引用 THEN 系统 SHALL 只引用 foundation 的基线（MC-9 / MC-10 / MC-11），但 SHALL 现算本 spec 4 册的逐册值。
2. WHEN 本 spec 4 册的特征被登记 THEN 系统 SHALL 覆盖：**M9 公式格 470**（10 册第二多）· **M9 明细表是宽表之一**（列 × 行现算）· M1 `明细表M1-2` 公式格最多（现算）· M8 有 `针对性测试M8-5-删除` · **M8 / M6 的 Q 表 sheet 名双空格**（M10 单空格，引用 MC-27）· 「合计 / 小计」中文分散对齐在 M7 / M8 / M9 的分布（现算处数）。
3. WHEN 🔴 本 spec 不改模板 THEN 系统 SHALL 断言 4 册的 sha256 在本 spec 前后**不变**（与 lane 2 改 M10 册形成对照）。
4. WHEN 幽灵行被引用 THEN 系统 SHALL 现算本 spec 4 册的值并声明 `max_row − last_value_row` 口径（引用 MC-11）。

## Requirement 14：端到端闭环（阻塞）与本 spec 自检

**User Story:** 作为质控，我需要知道本 spec 的闭环为什么不能现在验，且引用与计数自洽。

### 验收准则

1. WHEN 闭环被排期 THEN 系统 SHALL 标 `[ ]*`，理由是现算：M1 **2** 行（1 行 `NULL` + 1 行是 AI 复核会话记录）· M9 **1** 行（`M9-2-detail-rows`，`remark` 为 `NULL`）· **M5 / M8 各 0 行** ⇒ 四条均无有效业务载荷。
2. WHEN BP-1 / BP-2 / BP-3 被引用 THEN 系统 SHALL 引用 foundation 的登记，不重复裁决。
3. WHEN 自检被执行 THEN 系统 SHALL 断言本 spec 三文件里的 `MC-x` 引用**只出现编号不出现判据复述**。
4. WHEN entry 被引用 THEN 系统 SHALL 用 `entry_id` 全名，断言 4 条无重无漏。
5. WHEN 计数自检被执行 THEN 系统 SHALL 断言：sheets `11+10+11+9 = 41` 且 `41 + 51（lane 2）+ 10（M6）= 102` · HTML `10+9+9+8 = 36` 且 `36 + 44 + 9 = 89` · OO 兜底 `1+1+2+1 = 5` 且 `5 + 7 + 1 = 13` · 公式格 `338+193+227+470 = 1228` 且 `1228 + 1534 + 175 = 2937` · MAP declared `10+9+8+8 = 35` 且 `35 + 43 + 6 = 84` · MAP missing `0+0+0+2 = 2` 且 `2 + 9 + 0 = 11`。
6. WHEN 「N 处」表述被使用 THEN 它 SHALL 与紧随其后的列举项数相等。
7. WHEN Property 编号被检查 THEN `MB-P` 系列 SHALL 无缺号无重号；文档 SHALL 无 U+FFFD。
