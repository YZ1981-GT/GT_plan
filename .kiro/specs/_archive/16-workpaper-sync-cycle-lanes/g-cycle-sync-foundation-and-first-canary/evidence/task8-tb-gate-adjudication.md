# Task 8 证据：GC-9 三家 TB 发布门缺口 —— 书面裁决

**执行时间**：2026-09-27　**方法**：四层逐处**按值核**（不推断）

## 🔴 裁决结论：缺口是**两家**，不是三家 —— spec RG-6 误判了 G1

spec `requirements.md` RG-6 与 design §GC-9 都写「G1 / G4-main / G6-main **三家**未接 TB 显式发布门」，
依据是 `publishToTb` 在 `useG{N}Adjudication.ts` 里的计数为 0。
**该依据只覆盖一层**。TB 显式发布门在 G 循环实际分布在四层，G1 的门在**组件层**。

| family | 裁决 | 依据（逐处按值） |
|---|---|---|
| **G1** | ✅ **已接，不是缺口** | 见下 §一 |
| **G4-main** | 🔴 **真缺口** | 见下 §二 |
| **G6-main** | 🔴 **真缺口，且是回归** | 见下 §三 |

## 一、G1：门在组件层，composable 层的引用全是注释

四层逐处（`audit-determination/publish-to-tb` 端点字面量 + `publishToTb` 名字）：

| 层 | 文件 | 命中 | 性质 |
|---|---|---|---|
| composable | `useG1Adjudication.ts` | `publishToTb` ×1（L487 JSDoc） | **注释**：记录 TB 回写改由审定表显式门承载 |
| FormData | `useG1TraFinFormData.ts:107-108` | ×2 | **注释**：`// 已改由 G1-1 审定表「发布到试算表」显式确认门（G1TabAdjudication.handlePublishToTb → POST publish-to-tb…）承载，故移除此重复定义及其 return export。` |
| **组件** | `G1TabAdjudication.vue` | ×4 | 🔴 **活代码**：L251 `@click="handlePublishToTb"` · L352 注释 · **L356 `async function handlePublishToTb(): Promise<void>`** · L376 `` `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb` `` |
| 宿主 | `GtG1TradingFinancialAssets.vue:475` | ×1 | **注释**：同上记录 |

`G1TabAdjudication.vue` 的门带**中文二次确认**（L360）：
「发布后将把交易性金融资产审定数（科目 1501）写入试算表（trial_balance），并触发报表/错报评价等下游重算。确认发布？」

`useG1Adjudication.ts` 的 `trial-balance` 两处（L483 / L484）逐字在同一段 JSDoc 内：

```
 * 原此函数额外 dispatch `g1:writeback-trial-balance`（→ 宿主 handleG1Writeback →
 * useG1TraFinFormData.writebackTrialBalance → 旧端点 PUT trial-balance/writeback，绕过显式
 * 确认门，且在 watch(closingAudited) 数据变化时自动触发，违反 Req 1）。现移除该 dispatch，
 * TB 回写改由 G1-1 审定表「发布到试算表」显式确认门（G1TabAdjudication.handlePublishToTb）承载。
```

⇒ **裁决：注释/死代码记录，非活路径。G1 不进硬门，可以受管。**

判据：`test_gate_presence_by_layer[G1]`（要求四层里**有**代码命中）+
`test_g1_trial_balance_references_are_comments_only`（要求全文有、代码无）。

## 二、G4-main：真缺口（从来没接过）

全仓 `*G4*` 文件按 `publishToTb|handlePublishToTb|publish-to-tb` 现算：**零命中**。
`G4TabAdjudication.vue` 只**读** TB：L194 `试算表数: adj.trialBalanceAmount.value` ·
L334 `adj.fetchTrialBalance()` —— 无任何发布入口、无端点字面量。

`useG4MainAdjudication.ts` 去注释后：`trial-balance` ×1（`/api/trial-balance/query` 读取）·
`writeback` ×2（`applyAdjustmentWriteback` 族，落 `checklist_responses` 不碰 `trial_balance`）。

⇒ **裁决：活路径都是「只读 TB 做核对」，写入路径不存在。G4-main 审定数无法回写 TB。**

## 三、G6-main：真缺口，且是 `tb-writeback-explicit-publish-gate` 的**回归**

`useG6MainFormData.ts:401-406` 逐字：

```
  // 原 writebackTB(adjudicatedAmount) 走 TB 回写变体端点
  // POST /api/projects/{pid}/trial_balance（科目 1503）。实证 GtG6OtherBondMain.vue 未
  // destructure/调用它、无任何测试消费 ⇒ 零消费死代码。G6 真实回写在 useG6MainAdjudication
  // （aggregateG6WritebackNets）。已移除 —— TB 回写走显式发布门 publish-to-tb。
  // 该变体端点字面量亦纳入 task 18 CI 守卫。
  // spec: tb-writeback-explicit-publish-gate Task 17 批C（Property 9）
```

注释声称「TB 回写走显式发布门 publish-to-tb」，但现算：
`G6TabAdjudication.vue` **没有** `publish-to-tb`（只有 L233 `试算表数: adj.trialBalanceAmount.value` 读取）。

⇒ **裁决：旧路径已删、新门未建。G6-main 审定数现在没有任何 TB 回写通路。**
这是 `tb-writeback-explicit-publish-gate` Task 17 批C 的**遗漏**：
它按「零消费死代码」删掉了旧变体端点（删得对），但没有补上替代门。

判据 `test_g6_main_gate_removal_without_replacement_is_registered` 把这个回归锁成不变式
（补上门之后该判据会打红，提示更新登记 —— 这是**故意**的，让闭合动作必须同步 evidence）。

## 四、遗漏项交棒 → `tb-writeback-explicit-publish-gate`

本 spec **不改造** TB 回写路径（GC-9 明令）。交棒清单：

| # | 项 | entry | 处置 |
|---|---|---|---|
| 1 | 补显式发布门 | `xlsx/gt-g4-bond-investment-main` | 在 `g4-bond-investment-main/core/G4TabAdjudication.vue` 加 `handlePublishToTb`（照 G1 范式：中文二次确认 + `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`） |
| 2 | 补显式发布门（**回归修复**） | `xlsx/gt-g6-other-bond-main` | 同上，在 `g6-other-bond-investment-main/core/G6TabAdjudication.vue`；优先级高于 ①，因为它是「删了旧路径没建新门」 |
| 3 | 活错码收口 | G1 / G4 / G6 | 见 §五 |

## 五、🔴 顺带发现：生产代码里有一族**活的错科目码**（触类旁通 grep）

需求 6.4 只要求修 `useG6MainAdjudication.ts:53` 的错注释（已修）。
按「发现一处反模式立即 grep 全仓找同类」现算 `G{N}_ACCOUNT_CODE` 常量：

| 声明处 | 值 | 真码（`G_ACCOUNT_CODES`） | 判定 |
|---|---|---|---|
| `g1AccountScope.G1_GROSS_FALLBACK_STANDARD`（经 `g1NoteSectionMap` / `g1DisclosureItems` / `g1AdjudicationItems` 转发） | — | 1101 | 走 scope 单源 ✅ |
| `useG1Adjustment.G1_ACCOUNT_CODE` | **`'1501'`** | **1101** | 🔴 错码（1501 = 旧准则持有至到期投资） |
| `useG1Disclosure.G1_ACCOUNT_CODE` | **`'1501'`** | **1101** | 🔴 错码 |
| `G1TabAdjudication.vue:360` 二次确认**文案** | 「科目 1501」 | 1101 | 🔴 错码已到**用户可见层** |
| `g2AdjudicationItems` / `g2NoteSectionMap` | `'1132'` | 1132 | ✅ |
| `g4AdjudicationItems.G4_ACCOUNT_CODE` | **`'1501'`** | **1504** | 🔴 错码（1501 在 `KNOWN_BAD_CODES['G4']`） |
| `g4NoteSectionMap.G4_ACCOUNT_CODE` | **`'1501'`** | **1504** | 🔴 错码 |
| `useG4MainAdjustment.G4_ACCOUNT_CODE` | **`'1501'`** | **1504** | 🔴 错码 |
| `g6AdjudicationItems.G6_ACCOUNT_CODE` | 转发 `g6AccountScope.G6_GROSS_FALLBACK_STANDARD`（=1506） | 1506 | ✅（2026-08-02 已修） |
| `useG6MainAdjustment.G6_ACCOUNT_CODE` | **`'1503'`** | **1506** | 🔴 错码（1503 在 `KNOWN_BAD_CODES['G6']`） |

`dev-history.md` 已登记过 G6 那两处中的一处（「`useG6MainAdjustment.G6_ACCOUNT_CODE='1503'`（旧准则可供出售金融资产，**未修**）」），
并给出了不能只改常量的理由：整个 `G6_OTHER_BOND_ACCOUNTS`（`1503`/`150301`/…）建在旧准则科目族上，
改默认码而不重建清单会打断 `G6_OTHER_BOND_ACCOUNTS.find()`。**G1 / G4 的同族错码此前未登记**，本轮补登。

影响面（为什么不是纯显示问题）：这些常量同时喂
`/api/trial-balance/query?account_code=`（TB 核对查错科目 ⇒ 核对数恒为空）与
`substantive:adjudicated` 事件的 `accountCode`（审定数记到错科目名下）。

**本 spec 不改**（属 `tb-writeback-explicit-publish-gate` / 四表取数的作业面，且需连带重建硬编码科目族清单）。
交棒条目 = §四 第 3 项。

## 六、其余需求逐条

| 需求 | 处置 |
|---|---|
| 6.4 修 `useG6MainAdjudication.ts:53` 错注释 | ✅ 已修：注释现写明真码 **1506**、1505 与 1503 **都在** `KNOWN_BAD_CODES['G6']`、键名 `G6-1-adj-tb-1503` 里的 1503 只是历史痕迹不得改名 |
| 6.4 TB 键按值取不按科目码推演 | ✅ 判据 `test_tb_keys_are_taken_by_value_not_derived_from_account_code`：断言源码里有 `G4-1-adj-tb-1501` / `G6-1-adj-tb-1503`，且**没有**按 `G_ACCOUNT_CODES` 推演的 `G4-1-adj-tb-1504` / `G6-1-adj-tb-1506` |
| 6.5 损益类口径 | ✅ 判据锁 `PL_CYCLES == {G11,G12,G13,G14}` |
| 6.2 本地硬门 | ✅ `test_gap_families_are_blocked_from_being_managed`：`g4.bond_main` / `g6.other_bond_main` 一旦注册 adapter 而门仍缺即打红 |
| FC-9 红线 | ✅ `test_no_gap_family_writes_trial_balance_directly`：四层代码不得含 `trial-balance/writeback` 或 `/trial_balance` 端点字面量（探针用**带分隔符**的字面量 —— 裸词会把 G1 二次确认的中文文案误判成写入路径，本轮实测踩过一次） |
