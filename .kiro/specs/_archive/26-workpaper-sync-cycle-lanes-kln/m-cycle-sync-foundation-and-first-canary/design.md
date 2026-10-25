# M 循环双向回写地基与首张 canary — 设计

## 上游与边界

| 项 | 值 |
|---|---|
| slice | `backend/data/workpaper_sync_m_cycle_manifest_slice.json`（227,879 B，Task 55，冻结 2026-08-31） |
| 删除清册 | `backend/data/workpaper_sync_m_cycle_deletion_plan.json`（93,321 B，`schema_version = m-cycle-deletion-plan:v1`） |
| 既存守卫 | `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py`（**2752** 行 / 14 测试类 / 152 test） |
| 前轮裁决 | FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / KC-1~24 / **LC-1~26**（本轮以 LC 为重裁基准） |
| 本 spec entry | `xlsx/gt-m6-retained-earnings`（1 条） |
| canary | entry `xlsx/gt-m6-retained-earnings`，宿主 sheet `审定表M6-1`，键前缀 `M6-` |

**既存守卫锁的是「现状诚实记录」，本 spec 锁的是「改线后目标态」。** 既存 14 测试类：`TestGuardSelfChecks` / `TestSliceScopeIsRecomputable` / `TestAdjudicationLegality` / `TestHtmlCounterpartIsSourceBacked` / **`TestMCycleFormDifferences`** / `TestOrphanDualModeInventory` / **`TestModeSwitchResolution`** / `TestSheetGranularityAndRouter` / **`TestProperty24ProtectedFormulaAndSummary`** / `TestProperty28DefinitionDriftFailClosed` / `TestProperty69EvidenceAndCounters` / `TestProperty70CrossEntryIsolation` / `TestDeletionPlanConsistency` / `TestParadigmCompliance`。凡本文档判据与之重叠，实施时**引用测试名**，不重写。

🔴 **与 L 轮既存守卫的类名差异（不可照抄测试名）**：M 有 `TestMCycleFormDifferences` / `TestModeSwitchResolution` / `TestProperty24ProtectedFormulaAndSummary`；**L 有而 M 无**的是 `TestProperty20AndProperty3` 与 `TestProperty23StaticStructure`（Property 23 已并入 form_differences，Property 20 分母在 M 为空）。

🔴 **Property 集换代**：前几轮是 20 / 22 / 23，本轮是 **24 / 28 / 69 / 70**。`property_24` 是新出现的，论证方向必须按其原文（受保护字段冲突），**不得**照抄 Property 20 的「generated col 占位」分母论证。

## 10 条 entry 权威表（现算自 slice `independent_entries` + 删除清册，非推演）

| entry_id | wp_code | sheets | 公式格 | dispatch | HTML 覆盖 | OO 兜底 | mount | 载体 kind | redeem | MAP d/h/m | blocked_by |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-m1-dividends-payable` | M1D | 11 | 338 | 11 | 10 | 1 | 2 | per_entry_wrapper | `true` | 10/10/0 | 1,2,3,5,**6**,7,9,10,11 |
| `xlsx/gt-m2-paid-in-capital` | M2P | 11 | 574 | 10 | 10 | 1 | 2 | per_entry_wrapper | `true` | 9/6/**3** | 1,2,3,**4**,5,**6**,7,**8**,9,10,11 |
| `xlsx/gt-m3-treasury-stock` | M3T | 10 | 255 | 10 | 8 | 2 | 2 | per_entry_wrapper | `true` | 8/7/**1** | 1,2,3,**4**,5,**6**,7,9,10,11 |
| `xlsx/gt-m4-capital-reserve` | M4C | 9 | 193 | 9 | 8 | 1 | 2 | per_entry_wrapper | `true` | 8/7/**1** | 1,2,3,**4**,5,**6**,7,9,10,11 |
| `xlsx/gt-m5-surplus-reserve` | M5S | 10 | 193 | 10 | 9 | 1 | 2 | per_entry_wrapper | `true` | 9/9/0 | 1,2,3,5,7,9,10,11 |
| **`xlsx/gt-m6-retained-earnings`** | M6R | 10 | **175** | 10 | 9 | 1 | 2 | per_entry_wrapper | `true` | **6/6/0** | 1,2,3,5,7,9,10,11 |
| `xlsx/gt-m7-special-reserve` | M7S | 10 | 233 | 10 | 9 | 1 | 2 | per_entry_wrapper | `true` | 9/8/**1** | 1,2,3,**4**,5,7,9,10,11 |
| `xlsx/gt-m8-general-risk-reserve` | M8G | 11 | 227 | 10 | 9 | 2 | 2 | per_entry_wrapper | `true` | 8/8/0 | 1,2,3,5,7,**8**,9,10,11 |
| `xlsx/gt-m9-other-comprehensive-income` | M9O | 9 | 470 | 9 | 8 | 1 | **1** | **`none`** | **`false`** | 8/6/**2** | 1,2,3,5,7,9,10,11 |
| `xlsx/gt-m10-other-equity-instruments` | M10O | 11 | 279 | 10 | 9 | 2 | 2 | per_entry_wrapper | `true` | 9/6/**3** | 1,2,3,**4**,5,7,**8**,9,10,11,**12** |

**算术自检**：sheets 合计 **102**（无 M0）· 公式格合计 **2937** · 带公式 sheet **81** · HTML 覆盖 **89** + OO 兜底 **13** = 102 ✓ · MAP declared **84** = hit **73** + missing **11** ✓ · mount 合计 **19**（M9 只 1）· dual-mode 模块 **20** = orphan **11** + live **9** ✓

🔴 **M9 的 MAP 有 2 处 missing 但它不挂 BP-4** —— 因为 M9 的 SHEET_MAP 在 orphan 模块里（不可达）。故 `entries_with_sheet_map_defects = 6` 与「BP-4 登记 5 条 entry」**两个数都对**，不可互相覆盖。

## M 与前九轮的形态差异（MD-1 ~ MD-8 由 slice 提出，本节给现算复核结论）

| 差异 | slice 的说法 | 本轮现算复核 |
|---|---|---|
| **MD-1** 载体成对孪生 | 20 == entry × 2；orphan 11 ≠ live 9（M9 双孪生皆 orphan） | ✅ 属实。orphan 行数 1911 / live 396（`splitlines()` 口径）。🔴 L 是 9 文件 / 8 entry 三分、K 是 13 == 13 二分，**照抄任一种都会把分母算错** |
| **MD-2** 开关裁决分布 | redeemable 9 + no_switch 1 + **inert 0** | ✅ 属实。删除清册 `inert_switch_blocks_to_remove = 0` 印证。🔴 抄 L 的 `switch_present_but_inert` 会直接判错 |
| **MD-3** SHEET_MAP 声明层 | 84 对里 11 对指向不存在的 sheet | ✅ 属实，**本轮最贵**。slice 自述「前九轮从不核这一层」（L 核的是 HTML 承载与 dispatch 重复）⇒ 这是 AC 6.10 在 **sheet-name 层**的缺口，现状静默错位 |
| **MD-4** 3 张「修订前」Q 表 | wp 码前缀是 **Q** 不是 M；三种待遇 | ✅ 属实。M6 `skip-q6a` 正确 / M8 无拦 / M10 死代码。🔴 sheet 名空格数还不一致（M6·M8 双空格、M10 单空格） |
| **MD-5 ~ MD-8** | 见 slice 原文 | 本 spec 在 MC-x 里按需引用；凡引用必现算复核，不转述 |

### 🔴 slice 未记录的新事实（本轮实测补出）

| 新事实 | 内容 | 归属 |
|---|---|---|
| 历史 sheet 过滤两侧不一致 | 后端已有 `_should_skip_historical_sheet` 且对 M 命中 4/4，但消费方只 2 处、`wp_render_config.py` 无此过滤 ⇒ HTML 侧看得到 Q 表、OO 侧看不到 | **MC-24**（foundation 修） |
| 已归档 spec 假绿遗留 | `m10-other-equity-instruments` 写错 sheet 名并被代码照抄；另一份已归档 spec 记对了名 ⇒ 无单一真源 | **MC-25**（lane 2 修） |
| M10 合计漏加小计 10 列 | `明细表M10-2` r26 漏加 r25「三、转股特征」小计 + 2 列派生污染 | **MC-17**（lane 2） |
| 真库 row-0 基准 | `M7-disclosure-soe-row-0-policy` 是 0-based，与代码侧 `idx + 1` 并存 | **MC-8**（全域） |
| M10 跨册文案残留 | `M10A` 的审计目标段整段写「其他综合收益」等 | **MC-21**（lane 2） |

## canary 选型：🔴 对 K / L 口径的显式偏离

**K / L 两轮的硬标准**：「真库有非空业务载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组」。

**该标准在 M 域无解**（现算证据）：`checklist_responses` 里 `item_id` 匹配 M 命名空间的**只 6 行**（M1 2 行 · M2 / M6 / M7 / M9 各 1 行 · **M3 / M4 / M5 / M8 / M10 各 0 行**），`remark` 非空**仅 1 行**，而那行是 `M1-review-session-20260725075149`（**AI 复核会话记录**，内容形如 `{"session_id": …}`）⇒ **业务载荷合格者为空集**。`conclusion` 非空现算 **0**。

**替代判据（五条，全部现算）**：

| 判据 | M6 | 对照 |
|---|---|---|
| ① `must_fix_before_wiring` 为最少档（**8** 项，全是公共项） | ✅ BP-1/2/3/5/7/9/10/11 | M5 / M9 同 8 项；M2 最多 |
| ② SHEET_MAP 零错位且 declared 最少 | ✅ **6 / 6 / 0** | M1 10/10/0 · M5 9/9/0 · M8 8/8/0 |
| ③ `switch_is_redeemable == true` | ✅ | M9 是 `none` / `false` ⇒ 排除 |
| ④ 权威册公式格最少 | ✅ **175** | M2 574 · M9 470 · M1 338 · M5 193 |
| ⑤ 有正确处理先例可作正面样板 | ✅ **3 张 Q 表里唯一正确**（`skip-q6a` 专用分支 + `el-empty`） | M8 无拦 · M10 死代码 |

**排除理由（逐条现算）**：**M1** 含 BP-6 + `procedure` 声明是 10 册唯一不带 `A` 的异类 + item_id 属重复前缀型；**M5** 判据 ①②③ 同样干净但公式格 193 > 175 且无判据 ⑤；**M9** 载体 `none`、双孪生皆 orphan、无 UI 门锚点；**M3 / M4 / M5 / M8 / M10** 真库 0 行。

🔴 **canary 闭环必标 `[ ]*`**：M6 真库唯一行 `M6-4-explanation` 的 `remark` 为 `NULL`，端到端闭环须先造业务载荷。这是与 L 轮（L1 有 33 行真载荷）的根本差异，**不得用 `M1-review-session-*` 那行冒充业务数据**。

## MC-1 ~ MC-29 共同裁决

> **承接策略**：以 LC-1~26 为基准逐条重裁。LC 已是 F/G/H/I/J/K 六轮的收口层，故前六轮裁决经 LC 间接覆盖。
> lane spec **只引用 `MC-x` 编号，不复述内容**。
> 每条带「与 LC-x 的关系」标注。**五处 ❌ 不适用必须显式声明**（见本节末）。

### MC-1 manifest 口径与 BP-9 分歧必须显式登记（LC-1 ✅ 适用）

10 条 entry 的 `manifest_mirror` 一致记 `capability: single_onlyoffice` / `html_store: unresolved`，`why_not_adopted` 明写这两个值来自 **overlay 的 `defaults_by_component.GtOnlyOfficeSheet` 默认值填充，不是逐 entry 裁决（AP-3）**。manifest entry 上**不存在** `capability_target` 字段。🔴 表述为「数据冲突」或「manifest 错了」即违规。🔴 **M slice 另明写守卫方向是「必须不一致且已登记 BP-9」，不是断言两侧相等** —— 判据写成 `assert manifest == slice` 会把正确现状判红。

### MC-2 载体族是成对孪生，只两种 kind（LC-2 ⚠️ 变形）

`per_entry_wrapper_over_shared_base` **9** + `none` **1**（M9）。模块总数 **20 = entry × 2**，而 **orphan 11 ≠ live 9**（M9 双孪生皆 orphan，`entries_with_two_orphan_twins` 现算 1）。🔴 M **没有** L 的 `child_tab_dedicated_composable`、**没有** K/H 的宿主内联 IIFE（`const dualMode = (() =>` 现算各 0）。`switch_is_redeemable` 在 M 是**二值**（9 `true` + M9 `false`），不是 L 的三态 —— L 的 `null`（无开关可谈）在 M 由 `false` + `no_switch_at_all` verdict 承载。

### MC-3 写路径按端点字面量判定且必须认反引号（LC-3 ✅ 适用）

端点字面量 `audit-determination/publish-to-tb`，代码命中恰 **10**（10 个 `useM{n}FormData` 各 1）。旧端点 `trial-balance/writeback` 的命中**全部是迁移记录注释**（代码命中 **0**）⇒ 铁律未违反。🔴 只数命中数不判注释，会把注释误立成违规。

### MC-4 确认门与发布门分居不同文件（LC-4 ✅ 适用）

发布门代码命中所在文件集 = **10** 个 `useM{n}FormData`；`ElMessageBox.confirm` 所在文件集为现算值；**两集合交集为空**。这是分层设计（Adjudication 弹确认 → FormData 发布），不是缺陷。🔴 判据必须落「**调用链上有 confirm**」；写成「同文件有 confirm」会让 10 条全假红。

### MC-5 M 域文件集口径必须 strict，且 `loose_only` 为空（LC-5 ⚠️ 换义）

strict 口径 = 路径含 `m{1..10}/` 目录段 **或** 文件名匹配 `^(?:use|Gt)?M(?:10|[1-9])(?![0-9])(?:[A-Z]|$|\.)`。🔴 **`M10` 分支必须排在 `M1` 之前**且带 `(?![0-9])`，否则 `M1` 吞 `M10`。🔴 **与 L 反向**：L 的宽口径差集非空（撞 G 循环 Level-3 公允价值 + H2 跨用），M 的 `loose_only` 现算 **0** —— M 的命名不撞任何其他循环。故 LC-5 的「撞 G Level-3」在 M **无对象**，本条改为**反向断言**（差集必须为空），须显式声明而非静默沿用。

### MC-6 行身份判别式：零正面样板（LC-6 ⚠️ 恶化）

`removeRow` / `handleRemove` 全量命中现算值里，**按索引删 : 按行身份删 = 全部 : 0**。🔴 **M 域零正面样板**（L 有 3 个生成真 rowId 的模块可抄）⇒ 去位置化改造在 M 必须**自建**样板，不能「抄同循环已有的对的那个」。🔴 更深一层：变量名出现 `rawIdx` / `globalIdx` / `displayIndex` / `tableIndex` ⇒ 存在「显示索引 ↔ 原始索引」**双套映射**（如 `M9TabDetail.vue` 的 `handleRemove(displayIndex)` → `removeRow(globalIdx)`）⇒ 去位置化必须同时消除两套映射，只改一层会造成新的错位。

### MC-7 removeRow 契约需四元组（LC-7 ✅ 适用）

M 域实测 **13 种签名**：`removeRow(index: number)` · `removeRow(rawIdx)` · `removeRow(index)` · `removeRow($index)` · `handleRemove($index)` · `removeRow(globalIdx)` · `handleRemove(index: number)` · `handleRemove(displayIndex: number)` · `removeRow(tableIndex)` · `removeRow(idx)` · `removeRow('capital', $index)` · `removeRow('expense', $index)` · `removeRow(type, idx: number)`（13 项，与「13 种」相等）。契约须记「函数名 + 首参形态 + 身份来源 + 所属模块」四元组，禁只记函数名。

### MC-8 位置化行身份四族 + 熵键假象 + 双索引基准（LC-8 ⚠️ 反转 + 新增）

四族口径：① 渲染键（`rowKey:` / `rowId:` 赋值）；② **持久化键**（`itemId` 模板串里的 `row-${…}` 段）；③ 展示序号（`seq: idx + 1`）；④ 熵键（`${Date.now()}` / `${Math.random()}` 拼接）。
🔴 **与 L 反转**：L 的 slice 在族 ② 上有盲区（只记 `total_hits: 1`），**M 的 slice 已纳入 item_id 口径**（`dynamic_row_identity` 现算与本 spec 族 ② 一致）⇒ 不得抄 L 的「slice 记漏」表述。族 ② 的配套事实：命中文件 = 10 个 `useM{n}Adjudication.ts` + `useM9OciReconcile.ts`，每个恰 **1** 处 `const n = idx + 1`。
🔴 **两点 M 新增**：① **熵键假象** —— 内存里行身份是 `${Date.now()}-${Math.random()}`（看似 opaque），落库 `item_id` 却是 `row-1 … row-N` 纯位置 ⇒ 只看内存会误判已达标；② **双索引基准并存** —— 代码侧 `const n = idx + 1` 是 1-based，真库实证存在 **0-based** 行（`M7-disclosure-soe-row-0-policy`）⇒ 迁移映射必须同时处理两种基准，否则整表错位一行。该事实 slice 未记录。

### MC-9 definedName 断链登记 + 两种新形态（LC-9 ✅ + 新形态）

10 册的 `total` / `broken` 现算（🔴 禁写死，清理后会变），分布形态：**M9 与 M1 显著高于其余 8 册、其余 8 册的 broken 数彼此相同** ⇒ 同一污染源。污染名与 L 循环**同源**（`AFV` / `bs` / `bs_1` / `CCD` / `CDE` / `DEX` / `EDC` / `FAD`），但 🔴 M1 / M9 另有**中文名与跨循环名**（`_1、受本循环影响的相关交易和账户余额` / `_2、主要业务活动` / `_1固定资产数据库_筛选打印` / `CarryKnown` / `_.dbf` / `_00510`）⇒ M1 / M9 是从**别的底稿册**复制来的。
🔴 **两种 L 轮未见的新形态**：`('bs', '{#N/A,#N/A,FALSE,"BBPREP"}')` = **打印区域宏残留**（BBPREP）· `('FAD', '[1]Breakdown!#REF!')` = **带外部工作簿引用 `[1]`**。判据须容忍这两种形态而不崩。

### MC-10 sheet 名禁归一化（LC-10 ✅ 加强）

🔴 **BP-4 的 6 处丢空格就是 strip 造成的** —— 这是本轮对 LC-10 的加强证据。现算形态：**10 册的实质性程序表 sheet 名全部含中间空格**（`实质性程序表` 与 `M{n}A` 之间），其中 M2 / M3 / M7 另有**前导**空格、M6 / M7 / M8 另有**尾随**空格，**M7 是前导 + 中间 + 尾随三重**。另有参考页用**全角连字符**（`参考－会计规定`，属 M3 册）。判据必须用 openpyxl 真读的 `wb.sheetnames` 逐字比对，**任何 `.strip()` 都会让 6 处缺陷凭空消失**。

### MC-11 五处扫描口径差必须如实登记（LC-13 ✅ 适用）

| # | 错误口径 | 正确口径 | 后果 |
|---|---|---|---|
| ① 熵键正则 | 本 spec 较宽 | slice 较窄 | **两值不等**，须两侧都报，不得择一 |
| ② 共享基类消费边 | 宽口径 token 文件数 | 窄口径 statement 边 | 两值不等（删除清册给窄 29 / 宽 33），差集须逐项解释 |
| ③ 行数 | `split("\n")` | slice 用 `splitlines()` | 每文件差 1，见 MC-29 |
| ④ 「小计」标签 | 全表扫 | **限 A 列或首个非空列** | 否则把 M10 `明细表M10-2` 的 `R10='小计'`（两级表头列名）当小计行 |
| ⑤ OO 兜底分类 | 按 hidden 状态得 **14** | slice 按 dispatch 得 **13** | 两套口径都要声明；混用必红 |

🔴 第 ⑤ 项的两套分解：slice 的 13 = `GT_Custom` 10 + 参考页 1 + 带「删除」1 + unmatched_by_dispatch 1（`pre_revision_q` 计 **0**，因 M8/M10 的 Q 表折叠到 `procedure` 由 HTML 承载、M6 走 `skip-q6a` 渲染 `el-empty`）；按 hidden 状态的 14 = `GT_Custom` 10 + **3 张 Q 表** + 带「删除」1。

### MC-12 BP-7 notice 从零补，且 tooltip 不算满足（LC-14 ✅ 加强）

M 域 notice 符号命中 **0**，10 条 entry 的 `mounts_ac14_notice` 全 `false`。AC 1.4 的单一真源是 `audit-platform/frontend/src/components/workpaper/sync/workpaperEntrySyncNotice.ts` 与 `.../sync/GtEntrySyncCapabilityNotice.vue`。🔴 **slice 明写「只放 `el-tooltip` 不算满足」**（EP teleport + 仅 hover 才进 DOM）⇒ 必须**常显摘要 + tooltip 细节**双落位。M9 是唯一 `ui_toolbar_gate.anchor` 为 `null` 的 entry（`entries_without_any_ui_gate_anchor` 现算 1）⇒ 它的 notice 须与 sync bridge 的编辑宿主**一并落位**。

### MC-13 el-segmented 门控形态 + 先剥注释（LC-15 ⚠️ 变形）

M 域二形态：宿主门控开关 **9**（redeemable）+ 完全无开关 **1**（M9）。🔴 **inert 现算 0** ⇒ 抄 L 的 `switch_present_but_inert` verdict 会直接判错，且删除清册的 `inert_switch_blocks_to_remove` 容器在 M 上**恒空**。🔴 `segmented_sites_that_are_not_mode_switches` 在 M 也**为空**（L4 有 `bondBranch` 分期/到期分支选择器，M 无对应物）。slice 顶层 `verdict` 是复合描述 **`switch_redeemable_but_mis_targeted`**（`verdict_is_binary: false`），后缀指 BP-4：开关能渲染出 OO，但声明给 OO 的 tab 名有 9 处指向不存在的 sheet ⇒ 判据不得把顶层 verdict 当三值枚举成员比对。

### MC-14 derived_total 双正则必需（LC-16 ✅ 适用）

两种位置形态都真实存在且都非零：**TAIL**（`-total` 结尾）与 **MID**（`-total-` 中置）。🔴 **M 的比例与 L 反向** —— M 是 MID 占绝对多数（现算 TAIL 9 : MID 35，L 是 5 : 3）⇒ 单正则只扫 TAIL 会漏八成。

### MC-15 item_id 命名轴：前缀重复轴 3 : 7 且 field 命名同步分裂（LC-17 ⚠️ 变形）

| 轴 | 分裂 |
|---|---|
| ① `ITEM_PREFIX` 常量 | **10 / 10 全有**（L 是 6 / 8）⇒ 判据可落常量名，不必兼容字面量 |
| ② 前缀重复轴 | **重复型 `M{n}-M{n}-{sheet}-…`：M1 / M2 / M3（3 条）** vs **不重复型 `M{n}-{sheet}-…`：M4 ~ M10（7 条）** |
| ③ field 命名风格 | 🔴 **与 ② 完全同步**：M1~M3 用 snake_case（`audited_amount`）· M4~M10 用 kebab-case（`adjudicated-amount`） |
| ④ 前缀互不吞并 | 现算 `'M10-'.startswith('M1-')` 为 `False`（`M1-` 第 3 字符是 `-`）⇒ 键层面安全，但**文件名层面**仍须靠 MC-5 的正则顺序保证 |

🔴 ② 与 ③ 同步分裂 ⇒ **M1~M3 与 M4~M10 是两批不同时期写的**。而 BP-6（mode 枚举 `structured` 未统一）的分界是 **M1~M4 / M5~M10** ⇒ 🔴 **两条分界线不重合，M4 在两侧归属不同**，切分与判据都不能假设「一条线切开 M」。

### MC-16 localStorage：活路径零键（LC-18 ⚠️ 反转）

🔴 **与 L 反转**：L 的活载体有键要迁移，**M 的活路径 0 键** —— 共享基类把 mode 存**内存 `ref`**，每次挂载重置默认值。键只出现在 **10 个 orphan**（`m{n}-dual-mode`，`localStorage_prefix_declaration_sites` 现算 10）且**全部按 wpId 分区**（L 有 1 个不分区）；M9 的第二个 orphan `useM9EntryDualMode.ts` 无键。⇒ 抄 L 的「活载体键要迁移」会去找一个**不存在的东西**；`legacy_deletion_paradigm` 的 step 5（统一键前缀）在 M 上**只对 orphan 生效**。
🔴 orphan 的 mode 枚举也分裂：M1~M4 是 `'structured' | 'onlyoffice'`（BP-6）· M5~M10 是 `'html' | 'onlyoffice'` · M9 的第二个孪生用**类型引用** `WorkpaperRenderMode` 而非字面量联合 ⇒ 判据扫字面量会漏掉它。

### MC-17 合计漏加小计：M 是真错（LC-21 ⚠️ 换形）

🔴 **与 LC-21 性质相反**：L 的 `审定表L4-1` 的 `=B11+B16+B17` 是**正确的避重复**，M10 `明细表M10-2` 的 r26 是**真错**。三段结构（r11 优先股 → r15 小计 · r16 永续债 → r20 小计 · r21 转股特征 → r25 小计）里：**10 列漏加 r25**（形如 `=SUM(H15,H20)`）⇒ 「三、转股特征」整段金额在合计里被吞掉；**4 列加齐**（形如 `=U25+U20+U15`）；**2 列派生污染**（`Y26 = S26+U26-W26` / `Z26 = T26+V26-X26` 基于漏加的 S26/T26）⇒ 污染「审计调整后期末账面价值」列。全域复扫（限 A 列行标签）**只有这一处** ⇒ `missing_subtotal` 现算 10。归 lane 2。

### MC-18 真库零业务载荷 ⇒ canary 判据必须换（LC-22 ⚠️ 换义）

现算 6 行 / `remark` 非空 1 行（且那 1 行是 AI 复核会话记录）/ `conclusion` 非空 0 ⇒ canary 判据换成五条替代标准（见上节）。🔴 **LC-22 的「跨 entry 键污染」在 M 不适用** —— 6 行的 `wp_code` 与 `item_id` 前缀现算全部匹配，无 L2 键落在 `wp_code='G8'` 那类污染。`conclusion` 在 M 与 L 同样是死字段 ⇒ contract 映射时**只映 `remark`**。

### MC-19 跨循环键冻结换向：M 是被引用方（LC-23 ⚠️ 换向）

🔴 **方向与 L 相反**：L1 是被 H2 引用（L 是被引用方的单例），**M 全域是被引用方**。生产文件（排除 `__tests__/`）四类：① `components/workpaper/composables/useL6Adjustment.ts`（**L6 → M**）· ② `components/workpaper/composables/g2NoteSectionMap.ts` · ③ `components/workpaper/composables/factories/createChecklistFormData.ts`（共享工厂）· ④ `components/workpaper/shared/cycleImportExportRegistry.generated.ts`（**生成物**，改键须改生成器）。
🔴 且已归档披露 spec 有**未完成**的跨循环守卫「**M1 推送的子表键与 K3 推送的键无交集**」⇒ 纳入本系列（归 lane 3 的 M1 分支），不得因已归档 spec 的完成度标记就认为已做。

### MC-20 空分母纪律 + M 的结构性零清单（LC-24 ✅ 适用）

19 项结构性零（逐项现算 + 至少 4 项变异证明）：M 前缀契约 0 · M 域 `adapter_id` 0 · `parent_duplicate` 0 · `excluded_pilot` 0 · `'m0'` 命中 0 · barrel 0 · 二阶 orphan 0 · **`#REF!` 公式 0** · **越界引用 0** · **dangling sheet 0** · **倒挤减法链 0** · **OCR 0** · **prefill 0** · **inert 0** · notice 0 · `onlyoffice-config` 0 · **按行身份删 0** · `conclusion` 非空 0 · M3/M4/M5/M8/M10 真库 0 行。
🔴 公式层四项零（`#REF!` / 越界 / dangling / 倒挤链）的分母是**权威册全部公式格现算值**（2937，非空分母）；L 在这四项上分别有 **8 / 0 / 0 / 6** 处 ⇒ **抄 L 的这四条缺陷会在 M 上误立**。

### MC-21 两批分界 + M10 跨册复制重灾区（LC-25 ⚠️ 换形）

🔴 **M1~M3 vs M4~M10 两批分界**（item_id 重复轴与 field 命名风格同步分裂，见 MC-15）。
🔴 **M10 是跨册复制重灾区**（slice 未记录）：① 模板文案跨科目残留 —— `其他权益工具实质性程序表 M10A` 的审计目标段整段写「**其他综合收益**」、B17 写「获取或编制**实收资本（股本）**明细表」（抄 M2）、`Q10A (修订前)` 同样抄 M2、`明细表M10-2` 的审计目标同样写「其他综合收益」，现算处数须与列举项数相等；② 附注 sheet 命名抄了 M2 / M9 的形态（M10 真名用 `附注披露信息核对（…）` + 「国企」，M2 / M9 用 `附注披露信息（…）` + 「国有企业」）⇒ **BP-4 的 M10 两处 + BP-12 同源**。
🔴 **反例须一并登记**：M2 册里 4 处跨科目命中经核是**正当业务表述**（如 `实收资本实质性程序表 M2A` 的「如果存在库存股交易：…」）⇒ **不算残留**，判据必须能区分。

### MC-22 科目性质分支：M1 与 M2~M10 不同（LC-26 ⚠️ 变形）

M2 ~ M10 属**权益类**（贷方；slice 引已归档 spec 的「科目 4003 其他权益工具（贷方/权益类）」），🔴 **M1 应付股利属负债类** ⇒ 四表判据（审定表 / 明细表 / 调整分录汇总 / 附注披露）按**两分支**写。🔴 M1 的科目码必须现算确认，**不得推演**。

### MC-23 🔴🔴 `M{n}_SHEET_MAP` 11 对错位（**M 独有，本轮最贵**）

declared **84** = hit **73** + missing **11**（slice `m_cycle_form_differences.MD-3` 与删除清册 `oo_sheet_map_defects_to_fix_not_delete.counters` 三方等值）。三种错法 **6 + 4 + 1 = 11**：

| 错法 | n | 逐条（声明值 → 权威册真名） |
|---|---|---|
| ① 丢空格 | **6** | M2 `实收资本实质性程序表M2A` → `' 实收资本实质性程序表 M2A'` · M3 `库存股实质性程序表M3A` → `' 库存股实质性程序表 M3A'` · M4 `资本公积实质性程序表M4A` → `'资本公积实质性程序表 M4A'` · M7 `专项储备实质性程序表M7A` → `' 专项储备实质性程序表 M7A '`（三重） · M9 `其他综合收益实质性程序表M9A` → `'其他综合收益实质性程序表 M9A'` · M10 `其他权益工具实质性程序表M10A` → `'其他权益工具实质性程序表 M10A'` |
| ② 整段不同 | **4** | M2 `检查表M2-5` → `实收资本（股本）检查表M2-5` · M9 `OCI核对表M9-4` → `其他综合收益核对表M9-4`（中英混写） · M10 `附注披露信息（上市公司）` → `附注披露信息核对（上市公司）` · M10 `附注披露信息（国有企业）` → `附注披露信息核对（国企）`（双重差异） |
| ③ 同码压成一个 | **1** | M2 `明细表M2-2` → 真册是 `明细表（上市公司）M2-2` + `明细表（非上市公司）M2-2` **两张** |

**缺陷归属**：`entries_with_defects` **6**（M2 3 + M3 1 + M4 1 + M7 1 + M9 2 + M10 3 = 11 ✓）· `defect_pairs_in_live_modules` **9** · `defect_pairs_in_orphan_modules` **2**（M9）⇒ 🔴 **BP-4 只登记 5 条 entry**（M9 的 MAP 在 orphan 模块里不可达）。

**反向判据（证明比对器不是恒判不存在）**：`procedure` 键 10 条声明现算 **hit 3 / miss 6 / 无此键 1** —— hit 的 3 条是 M1 `'应付股利实质性程序表M1'`（🔴 **10 册唯一不带 `A`**）· M5 `'盈余公积实质性程序表 M5A'`（带中间空格）· M8 `'一般风险准备实质性程序表 M8A '`（带中间 + 尾随，与真名完全一致）；**M6 根本没有 `procedure` 键**（只 6 对，走 `skip-q6a` 专用分支）。且 10 条 fallback 字面量 `审定表M{n}-1` **全部命中**真 sheet（现算 10）。
⇒ 🔴 **`procedure` 一个键就有 4 种写法 + 1 处缺键 = 逐模块手写、无单一真源的铁证**。

**危害为何长期不可见**：MAP miss 时代码回落 fallback，而 fallback 全部命中真 sheet ⇒ 用户看到的是**错的 tab 但不是空白**。AC 6.10 要求 fail closed，**现状零 fail closed**。

### MC-24 🔴🔴 历史 sheet 过滤两侧口径不一致（**M 独有，slice 未记录**）

`backend/app/services/wp_template_finder.py` 的 `_should_skip_historical_sheet` 规则集：含「修订前」/「（原）」/「(原)」· `G\d+` 配合「删除」或「移至」· 以 `-删除` 结尾 · 含「（示例）」或以「示例」结尾。对 M 的 4 张历史 sheet 命中 **4/4**（3 张 Q 表 + `针对性测试M8-5-删除`），反向判据成立（`审定表M6-1` / `明细表M10-2` / 带前导空格的程序表名全部保留）。
🔴 **消费方只 2 处**：`backend/app/routers/wp_onlyoffice_router.py` · `backend/app/services/wp_template_init_service.py`。🔴 **`backend/app/services/wp_render_config.py`（前端 sheet 列表主来源）无此过滤** ⇒ **HTML 侧看得到 Q 表、OO 侧看不到** ⇒ 两侧 sheet 集合不等、`sheet_key` 无法一一对应 ⇒ 这是 BP-8 在 HTML 侧可观察的原因。
🔴 `wp_onlyoffice_router.py` 里形如 `if not sheet_names: sheet_names = all_names` 的兜底是 **fail-open**，与 AC 6.10 的 fail-closed 要求冲突。
**修法**：两侧共用同一个过滤函数（单一真源），且过滤结果为空时 **fail closed**（报错而非回落全集）。本条是**平台级修**，不属任何单条 entry，收在 foundation。

### MC-25 🔴🔴 已归档 spec 的假绿遗留（**M 独有**）

| 证据 | 内容 |
|---|---|
| 错名源 | `_archive/05-business-features/m10-other-equity-instruments/requirements.md` 写「附注披露信息（**国有企业**）」，真名是 `附注披露信息核对（国企）`（**双重差异**：少「核对」+「国有企业」vs「国企」） |
| 传播 | 前端 `useM10EntryDualMode.ts` 的 SHEET_MAP 与宿主判断串**照抄错名** ⇒ BP-4 的 M10 两处 + BP-12 全部同源 |
| 假绿验收 | 同 spec 的 `m10_conflict_resolution.md` 写「Q10A 修订前 sheet 跳过 ✅ 通过」，实测该跳过代码是**不可达死代码** |
| 🔴 结论冲突 | **另一份已归档 spec 记对了名** —— `_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md` 明写「M10 sheet 名分叉：`附注披露信息核对（上市公司）`/`…核对（国企）` 与其余循环命名规则不同」⇒ **两份已归档 spec 结论不一致，代码采纳了错的那份** ⇒ 无单一真源 |
| 遗留欠账 | 该披露 spec 有**未完成**任务（6 个 `m{n}NoteSubtableContract.spec.ts` + 复用 `useAgingConfig` 首档判「超过 1 年」+ `el-input-number` → `WpAmountInput` + 跨循环键无交集守卫），现算处数禁写死 |

**处置**：① 前端 SHEET_MAP 改为 openpyxl 真名（归 lane 2）；② 🔴 **已归档 spec 的 requirements 不回填修改**（历史档案 append-only），勘误登记在本 spec；③ 加守卫「SHEET_MAP 的每个 value 必须在权威册 sheet 名集合里」防复发。

### MC-26 BP-11 受保护公式欠账（Property 24，**M 独有**）

源侧事实：权威册公式格 **2937** / 带公式 sheet **81**（口径 `data_only=False` + `isinstance(v, str) and len(v) > 1 and v.startswith('=')`）。🔴 守卫须**显式断言 `data_only=True` 会得到 0**，证明扫描口径是判据不是巧合。
消费侧事实：**18 处公式重算列**（判据是「同文件内被 `row.<f> = calc*(…)` 赋值」**且**「被 `String(row.<f>)` 持久化」两条同时成立）+ **28 处分类/汇总派生值**（含 M10 的三处 `M10-4-summary-*`），被当普通字段写进 `checklist_responses`。
承载者事实：`ProtectionPolicy` 五值枚举 + 三类只读来源判别式 + `protected_conflicts_from_incoming` 对 Task 37 函数的**包装**关系（分母 = 4 个后端模块）。
🔴 **宁缺勿造**：不为 M 造 contract、不猜 `formula_mask` 区域、不把公式格投影成可写字段。空分母那侧（端到端「OO 改公式格 → 生成 protected 冲突」）**不宣称通过**，只断言前提（M 侧 contract 数 0、`formula_mask` 声明数 0）与承载者结构。

### MC-27 3 张 Q 表三种待遇（**M 独有**）

| 宿主 | 待遇 | 形态 |
|---|---|---|
| **M6** | ✅ **唯一正确** —— `Q6A` + `修订前` 判断排在 `实质性程序表` **之前** ⇒ 专用 code `skip-q6a` ⇒ 渲染 `el-empty` | sheet 名双空格 |
| M8 | ❌ 完全没拦（`实质性程序表` 先命中）⇒ 折叠到 `procedure` | sheet 名双空格 |
| M10 | ❌ 写了拦但**排在后面** ⇒ 不可达死代码 ⇒ 同样折叠 | sheet 名**单空格** |

🔴 三张 sheet 的 wp 码前缀是 **Q** 不是 M（Q6A / Q8A / Q10A）⇒ 按 wp 码前缀选 entry 不会命中它们，但按 sheet 数做覆盖面结论时必须逐张判。🔴 空格数不一致 ⇒ 按字面量比对必须逐张取真名，禁写统一模板。
**正面样板抽取**：把 M6 的「先判历史 sheet、再判业务 sheet」顺序固化为可复用判据，M8 / M10 按同一顺序修。🔴 与 MC-24 的关系：后端过滤是**根治**，本条的宿主顺序修是**前端侧补救**，两者不互相替代（后端过滤生效后前端仍可能收到旧缓存的 sheet 列表）。Q 表本身**不是删除对象**（删除清册 `excluded_from_plan` 已登记：它们是权威模板里的 sheet，不是要删的前端文件）。

### MC-28 `resolveProcedureSheetKey.ts` 的 M 段缺 4 条（**M 独有**）

已交付平台工具 `audit-platform/frontend/src/utils/resolveProcedureSheetKey.ts`（行数现算）按 wp_code 前缀路由程序表 sheetKey，**M 段只 6 条**（M2 / M4 / M5 / M6 / M9 / M10）⇒ 🔴 **缺 M1 / M3 / M7 / M8**。该文件注释写明「G10+ 必须在 G1 之前判断」（防 `startsWith` 误匹配），🔴 **M10 同理但 M 段无该注释**。补齐时：① M10 分支排在 M1 之前并补注释；② sheetKey 取值与 openpyxl 真名对齐（**不是**与 SHEET_MAP 现有声明对齐 —— 后者本身错 6 处）；③ 4 个既存测试文件（`.spec.ts` / `.test.ts` / `.j-cycle.spec.ts` / `.m-cycle.spec.ts`）全绿且断言不改，仅新增用例。本条归 **foundation**（平台工具全循环共用）。

### MC-29 行数与计数口径差异必须声明（**M 独有**）

M slice 与删除清册用 `splitlines()`，本系列铁律用 `len(text.split("\n"))` ⇒ **每文件差 1**。可完全解释的偏移量：orphan 侧 **11** 文件 ⇒ 偏移 11（slice 记 1911，本口径 1922）· live 侧 **9** 文件 ⇒ 偏移 9（slice 记 396，本口径 405）· 共享基类单文件 ⇒ 偏移 1（删除清册记 65）。🔴 守卫比对时须指明用哪个口径，直接比必红；差异无法用文件数解释时判红，**不得取较大值或较小值**。

## LC-x 在 M 判 ❌ 不适用的五项（空分母，不宣称通过）

| 项 | L 侧分母 | M 侧现算 | 承载者处置 |
|---|---|---|---|
| **LC-11** `#REF!` 死公式 | L 有 8 处（`逾期贷款检查表L1-7` / `L3-7`） | **0** | 保持既有测试原样；M 侧只断言「公式格分母非空且 `#REF!` 为 0」 |
| **LC-12** footer 异常形态 | L 有 3 处 `&P/&N` 重复两次 | **0**（M 全域统一单个 `&P/&N`） | 同上 |
| **LC-19** OCR 借 D4 端点 | L 有 15 处 | **0** | 同上 |
| **LC-20** 倒挤减法链 | L 有 6 处（两种变体） | **0** | 同上 |
| **KC-17** prefill sheet 名逐字一致 | K 有 51 条 | **0**（与 L 同） | 同上 |

🔴 五项理由一律是「**M 侧分母为空**」，**不得**写成「M 没有这个问题」，也不得静默沿用。

## Property 清单 MF-P1 ~ MF-P76（本 spec 自有，lane 用 MA-P / MB-P 独立编号）

| Property | 断言 | Req | MC |
|---|---|---|---|
| MF-P1 | 按 `selection_rule` 现算 entry 集合 == slice `independent_entries`，且大小 == 10 | 1.1 | MC-1 |
| MF-P2 | manifest 侧 10 条 `capability == single_onlyoffice` / `html_store == unresolved` / **无 `capability_target` 键** | 1.2 | MC-1 |
| MF-P3 | slice 侧 10 条 `capability is None` / `capability_target == bidirectional` / `adapter_id is None` / `html_counterpart_verdict == exists` | 1.3 | MC-1 |
| MF-P4 | `manifest_mirror.why_not_adopted` 含 overlay 默认值填充表述；🔴 守卫方向是「必须不一致」不是「相等」 | 1.4 | MC-1 |
| MF-P5 | `'m0' in entry_id.lower()` 命中 == 0 且 `_index.json` 的 `M/M0` 条目 == 0（M0 根本不存在，非「有条目但排除」） | 1.5 | MC-20 |
| MF-P6 | 逐文件读契约 `review.entry_id` 得已迁移集合，断言无一属 M；集合大小现算；与 `adapter_id` 非空数是两个分母 | 1.6 | MC-20 |
| MF-P7 | MC-1 ~ MC-29 无缺号无重号，且每条至少被一份 spec 引用 | 2.4 | — |
| MF-P8 | LC-11 / LC-12 / LC-19 / LC-20 / KC-17 各自现算为 0 且被标「空分母不宣称通过」 | 2.3 | MC-20 |
| MF-P9 | `audit-determination/publish-to-tb` 代码命中 == 10；扫描器能匹配反引号模板串 | 3.1 / 3.2 | MC-3 |
| MF-P10 | `trial-balance/writeback` 代码命中 == 0，命中总数现算且全为注释 | 3.3 | MC-3 |
| MF-P11 | 发布门文件集与 `ElMessageBox.confirm` 文件集交集 == 0 | 3.4 / 3.5 | MC-4 |
| MF-P12 | `useM{n}Adjudication` → `useM{n}FormData` 调用边存在，且 Adjudication 侧有 confirm | 3.4 | MC-4 |
| MF-P13 | `useAdjustmentCentralSync` 命中现算（import 与调用成对），比对 L 同形 | 3.x | MC-3 |
| MF-P14 | `dual_mode_carrier.kind` 只两类：`per_entry_wrapper_over_shared_base` 9 + `none` 1 | 4.1 | MC-2 |
| MF-P15 | 宿主内联 IIFE `const dualMode = (() =>` 命中 == 0（10 宿主逐个验） | 4.1 | MC-2 |
| MF-P16 | dual-mode 模块 == 20 == entry × 2；orphan == 11；live == 9；`entries_with_two_orphan_twins` == 1 | 4.2 | MC-2 |
| MF-P17 | `switch_is_redeemable` 9 `true` + M9 `false`；`inert` == 0；`entries_with_inert_switch` == 0 | 4.3 | MC-13 |
| MF-P18 | 9 条 redeemable 三条件同时成立（剥注释后有 `el-segmented` + mode 门控 `v-if` + `v-else` 下挂 `GtOnlyOfficeSheet`） | 4.4 | MC-13 |
| MF-P19 | M9 无 `el-segmented`、`ui_toolbar_gate.anchor is None`、双孪生生产边与测试边均 0 | 4.5 | MC-2 |
| MF-P20 | 共享基类窄口径 statement 边现算；扣除 M 路径 10 条后剩余值现算 ⇒ 消费面**会收缩** | 4.6 | MC-11 / MC-29 |
| MF-P21 | legacy health 直调点删 orphan 后 == 1（非 0）；`onlyoffice-config` == 0；barrel 不存在 ⇒ 二阶 orphan == 0 | 4.7 / 4.8 | MC-16 |
| MF-P22 | 真库 `item_id` 匹配 M 命名空间的行数 == 6；`remark` 非空 == 1；`conclusion` 非空 == 0 | 5.1 | MC-18 |
| MF-P23 | 那 1 行非空的 `item_id == 'M1-review-session-20260725075149'` 且内容含 `session_id` ⇒ 非业务数据 | 5.1 | MC-18 |
| MF-P24 | M3 / M4 / M5 / M8 / M10 真库行数各 == 0 | 5.1 / 5.7 | MC-20 |
| MF-P25 | M6 `must_fix_before_wiring` == {BP-1,2,3,5,7,9,10,11}（8 项，全公共项） | 5.3 | MC-2 |
| MF-P26 | M6 SHEET_MAP declared/hit/missing == 6/6/0 且 declared 是 10 条最小值 | 5.4 | MC-23 |
| MF-P27 | M6 册公式格 == 175 且是 10 册最小值 | 5.5 | MC-26 |
| MF-P28 | M6 是 3 张 Q 表里唯一正确处理者（`skip-q6a` 判断在 `实质性程序表` 之前） | 5.6 | MC-27 |
| MF-P29 | M6 orphan 孪生 `useM6DualMode.ts` 零生产边零测试边、一阶 orphan、自带 `m6-dual-mode` 键（wpId 分区） | 6.2 | MC-16 |
| MF-P30 | 该 orphan 内容完整（`currentMode` / `modeOptions` / `switchMode` / `checkOOHealth` 全在）；改线后宿主不再 import 它 | 6.3 | MC-16 |
| MF-P31 | M 域 notice 符号命中 == 0；M6 锚点存在（形态锚点）；常显摘要 + tooltip 双落位 | 6.4 | MC-12 |
| MF-P32 | M6 活封装 `useM6EntryDualMode.ts` 恰 1 条生产边、委托共享基类、是 `resolveOoSheetName` 唯一实现方 ⇒ 不可在改线前删 | 6.8 | MC-2 |
| MF-P33 | BP-1 / BP-2 / BP-3 标 `[ ]*`，守卫只断言「前提不成立」不断言通过 | 6.1 | MC-20 |
| MF-P34 | canary 闭环标 `[ ]*`，理由是 M6 唯一行 `remark` 为 `NULL` | 5.8 | MC-18 |
| MF-P35 | 10 册 sha256 与 `sheet_count` 与 slice `template_ref` 10/10 等值；sheets == 102 | 7.1 | MC-9 |
| MF-P36 | `102 == HTML 89 + OO 兜底 13`；同时声明按 hidden 状态的 14 ⇒ 两套口径 | 7.2 | MC-11 |
| MF-P37 | 10 册程序表 sheet 名全含中间空格；M2/M3/M7 有前导；M6/M7/M8 有尾随；M7 三重；🔴 任何 `.strip()` 使 6 处缺陷消失 | 7.3 | MC-10 |
| MF-P38 | 参考页属 M3、名为 `参考－会计规定`（全角连字符）；带「删除」的属 M8 且不得据此裁 single | 7.4 / 7.5 | MC-11 |
| MF-P39 | definedName `total` / `broken` 现算（禁写死）；M9 与 M1 显著高、其余 8 册彼此相同；容忍 `{#N/A,…,"BBPREP"}` 与 `[1]Breakdown!#REF!` 两形态 | 7.6 | MC-9 |
| MF-P40 | footer 全域 == 单个 `&P/&N`（LC-12 空分母） | 7.7 | MC-20 |
| MF-P41 | 幽灵行用 `max_row − last_value_row` 现算并声明口径；最大值在 M6 `调整分录汇总M6-3` | 7.8 | MC-11 |
| MF-P42 | 「合计/小计」中文分散对齐处数现算；扫标签**限 A 列**，反例是 M10 `明细表M10-2` 的 `R10='小计'` | 7.9 / 7.10 | MC-11 |
| MF-P43 | 19 项结构性零逐项现算，每项带非空分母或显式「结构性零」标注 | 8.1 / 8.2 | MC-20 |
| MF-P44 | 至少 4 项（M adapter 0 / barrel 0 / 越界 0 / 按行身份删 0）构造反例，注入后必红 | 8.3 | MC-20 |
| MF-P45 | 公式层四项零的分母 == 2937（非空）；并写明 L 侧对应值 8/0/0/6 ⇒ 抄 L 会误立 | 8.5 | MC-20 |
| MF-P46 | 空分母 Property 一律标 `不宣称通过` 并指明承载者；slice `property_denominators` 含 `property_24` | 9.1 / 9.4 | MC-26 |
| MF-P47 | strict 文件集现算；`M10` 分支不被 `M1` 吞（正则顺序 + `(?![0-9])` 自检） | 10.1 / 10.2 | MC-5 |
| MF-P48 | `loose_only` 集合大小 == 0（反向断言：L 非空、M 为空） | 10.3 | MC-5 |
| MF-P49 | 位置化四族分别报数；族 ② 与 slice `dynamic_row_identity` 一致（🔴 与 L 反转） | 11.1 / 11.2 | MC-8 |
| MF-P50 | 族 ④ 两侧口径值都报（本 spec 更宽 vs slice 更窄），不择一 | 11.3 | MC-11 |
| MF-P51 | 熵键假象：内存 opaque 但落库 `row-1..N`；双基准并存（`idx + 1` 1-based vs 真库 `row-0` 0-based） | 11.4 / 11.5 | MC-8 |
| MF-P52 | removeRow 13 种签名逐一登记四元组；按行身份删 == 0（零正面样板）；双套索引映射须同时消除 | 8.6 | MC-6 / MC-7 |
| MF-P53 | M 键的跨循环消费者四类逐一定位（`useL6Adjustment.ts` / `g2NoteSectionMap.ts` / `factories/createChecklistFormData.ts` / `cycleImportExportRegistry.generated.ts`），🔴 方向是 M 被引用 | 12.1 | MC-19 |
| MF-P54 | generated 注册表标为生成物，改键须改生成器；本 spec 内引用点不变 | 12.2 / 12.3 | MC-19 |
| MF-P55 | 已归档披露 spec 的跨循环守卫「M1 键 ∩ K3 键 == ∅」现算为**未完成**并纳入本系列；canary 安全性：四类消费者均不引用 `M6-` 前缀 | 12.4 / 12.5 | MC-19 |
| MF-P56 | 5 项口径差各写「错误口径 → 正确口径 → 两侧现算值」，每项带「错口径必红、正口径应绿」自检 | 13.1 / 13.3 | MC-11 |
| MF-P57 | 行数差用文件数完全解释（orphan 11 / live 9 / 基类 1）；无法解释时判红，禁取较大或较小值 | 13.2 / 13.4 | MC-29 |
| MF-P58 | SHEET_MAP `declared 84 == hit 73 + missing 11`，三方等值（现算 / slice MD-3 / 删除清册 counters） | 14.1 | MC-23 |
| MF-P59 | `entries_with_defects == 6` 且 `live 9 + orphan 2 == 11`；BP-4 登记 5 条 entry —— 两个数并存不互相覆盖 | 14.2 | MC-23 |
| MF-P60 | 三种错法 `6 + 4 + 1 == 11`，每类逐条列出「声明值 → 真名」，列举项数与计数相等 | 14.3 | MC-23 |
| MF-P61 | 反向判据：`procedure` 键 hit 3 / miss 6 / 无此键 1（M6）；10 条 fallback `审定表M{n}-1` 全部命中 | 14.4 / 14.5 | MC-23 |
| MF-P62 | 危害不可见的机制被断言（miss → fallback 命中真 sheet ⇒ 错 tab 非空白）；AC 6.10 现状零 fail closed；M6 的 6 对全命中可原样迁移且**无 `procedure` 键** | 14.6 / 14.7 | MC-23 |
| MF-P63 | `_should_skip_historical_sheet` 规则集逐条断言；对 M 的 4 张历史 sheet 命中 4/4 | 15.1 / 15.2 | MC-24 |
| MF-P64 | 反向判据：正常 sheet 全部保留（样本含 `审定表M6-1` / `明细表M10-2` / 带前导空格的程序表名） | 15.3 | MC-24 |
| MF-P65 | 消费方现算 == 2 处；`wp_render_config.py` 现算**无**该过滤 ⇒ 两侧 sheet 集合不等 | 15.4 / 15.5 | MC-24 |
| MF-P66 | `if not sheet_names: sheet_names = all_names` 形态锚点定位（禁行号）并断言与 AC 6.10 冲突；修后两侧共用单一真源且空结果 fail closed | 15.6 / 15.7 | MC-24 |
| MF-P67 | 错名源与真名逐字比对（`附注披露信息（国有企业）` vs `附注披露信息核对（国企）`）；传播到前端 SHEET_MAP 与宿主判断串 | 16.1 / 16.3 | MC-25 |
| MF-P68 | 另一份已归档 spec 记对了名 ⇒ 两份结论不一致；`m10_conflict_resolution.md` 的「✅ 通过」是假绿（死代码） | 16.2 / 16.4 | MC-25 |
| MF-P69 | 该披露 spec 未完成任务数现算（禁写死）并逐条列出；🔴 已归档 spec **不回填修改**，勘误登记在本 spec；加「SHEET_MAP value ∈ 真 sheet 名集合」守卫 | 16.5 / 16.6 | MC-25 |
| MF-P70 | 公式格 == 2937 / 带公式 sheet == 81；🔴 显式断言 `data_only=True` 得 0 | 17.1 | MC-26 |
| MF-P71 | 消费侧两族现算（公式重算列判据两条同时成立 + 分类/汇总派生值）；🔴 宁缺勿造：M 侧 contract 数 == 0 且 `formula_mask` 声明数 == 0，端到端不宣称通过 | 17.2 / 17.3 / 17.4 | MC-26 |
| MF-P72 | 3 张 Q 表三种待遇逐宿主复刻 dispatch 顺序验证；M6 → `skip-q6a`、M8 → `procedure`、M10 → `procedure` | 18.1 | MC-27 |
| MF-P73 | 3 张 sheet 真名空格数不一致（M6/M8 双空格、M10 单空格）；wp 码前缀是 Q 不是 M；Q 表不是删除对象 | 18.2 / 18.5 | MC-27 |
| MF-P74 | `resolveProcedureSheetKey.ts` 行数与 M 段条数现算；M 段 == 6 且缺 M1/M3/M7/M8 | 19.1 | MC-28 |
| MF-P75 | 补齐后 M10 分支在 M1 之前且补顺序注释；sheetKey 与 openpyxl 真名对齐；4 个既存测试文件全绿断言不改 | 19.2 / 19.3 / 19.4 | MC-28 |
| MF-P76 | 行数口径在至少一个真实文件上现算证明差 1；与 slice / 删除清册比对时显式加偏移量；「N 处」与列举项数相等 | 20.1 ~ 20.4 | MC-29 |

## 三份 spec 的分工（1 + 5 + 4 = 10 ✓）

| # | 目录名 | entry（全名） | 缺陷集合 | Property 前缀 |
|---|---|---|---|---|
| 1 | `m-cycle-sync-foundation-and-first-canary` | `xlsx/gt-m6-retained-earnings` | canary + MC-1~29 全量裁决 + 公共 8 项 BP + **Q 表正确先例抽取** + MC-24 平台级修 + MC-28 平台工具补齐 | `MF-P` |
| 2 | `m2-m3-m4-m7-m10-sheet-map-drift-and-collapse` | `xlsx/gt-m2-paid-in-capital` · `xlsx/gt-m3-treasury-stock` · `xlsx/gt-m4-capital-reserve` · `xlsx/gt-m7-special-reserve` · `xlsx/gt-m10-other-equity-instruments` | **BP-4 全部 5 条**（11 处错位里的 9 处活映射）+ BP-8 的 M2/M10 + **BP-12**（M10）+ BP-6 的 M2/M3/M4 + MC-17 + MC-21 + MC-25 修正 | `MA-P` |
| 3 | `m1-m5-m8-m9-mode-value-and-carrier-exceptions` | `xlsx/gt-m1-dividends-payable` · `xlsx/gt-m5-surplus-reserve` · `xlsx/gt-m8-general-risk-reserve` · `xlsx/gt-m9-other-comprehensive-income` | **BP-6 的 M1**（唯一含 6 不含 4 的）+ **BP-8 的 M8** + **M9 载体 `none` + 双孪生皆 orphan** + M5 只公共项 + MC-19 的 M1↔K3 守卫 | `MB-P` |

**切分依据**：以 **BP-4（M 独有、最贵的一条）** 为主轴 —— lane 2 = 含 BP-4 的 5 条；lane 3 = 不含 BP-4 的补集（扣掉 canary entry M6）。

🔴 **为什么不按 L 的方式切**：M 的 BP 集合是**交叉重叠**不是互斥二分 —— BP-4（5 条）/ BP-6（4 条）/ BP-8（3 条）/ BP-12（1 条）两两相交（M2 同时含 4/6/8；M10 含 4/8/12；M1 只含 6；M8 只含 8）。且**两条分界线不重合**：mode 枚举分界是 M1~M4 / M5~M10，item_id 与 field 命名分界是 M1~M3 / M4~M10 ⇒ **M4 在两侧归属不同**。L 轮的「完全互斥集合」切法在 M 上不成立。

🔴 **lane 3 的缺陷集合不齐整是故意的**：BP-4 是最贵项，切分优先与它对齐；lane 3 内部按 entry 分支处理（M1 → BP-6 · M8 → BP-8 · M9 → 载体 `none` · M5 → 只公共项）。硬凑齐整会让 BP-4 横跨两份 spec，判据必然漂移。

## 算术自检（复盘必跑）

| 等式 | 值 |
|---|---|
| entry 数 | 1 + 5 + 4 = **10** ✓ |
| sheets | 11+11+10+9+10+10+10+11+9+11 = **102** ✓ |
| sheet 归属 | HTML 89 + OO 兜底 13 = **102** ✓ |
| 公式格 | 338+574+255+193+193+175+233+227+470+279 = **2937** ✓ |
| SHEET_MAP | declared 84 = hit 73 + missing 11 ✓；missing 6+4+1 = 11 ✓；live 9 + orphan 2 = 11 ✓ |
| SHEET_MAP 逐 entry declared | 10+9+8+8+9+6+9+8+8+9 = **84** ✓ |
| dual-mode 模块 | orphan 11 + live 9 = **20** = entry × 2 ✓ |
| 开关裁决 | redeemable 9 + no_switch 1 + inert 0 = **10** ✓ |
| 载体 kind | per_entry_wrapper 9 + none 1 = **10** ✓ |
| 行数偏移 | orphan 1911 + 11 = 1922；live 396 + 9 = 405；基类 65 + 1 = 66 ✓ |
| BP-4 成员 | M2 · M3 · M4 · M7 · M10 = **5** ✓（与 lane 2 entry 数相等） |
| MC 编号 | MC-1 ~ MC-29 连续无缺号，其中 M 独有 7 条（MC-23 ~ MC-29） ✓ |
| Property 编号 | MF-P1 ~ MF-P76 连续无缺号 ✓ |
