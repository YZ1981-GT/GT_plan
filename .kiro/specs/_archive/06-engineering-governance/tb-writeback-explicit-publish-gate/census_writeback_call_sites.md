# Census: TB 回写直调调用点活/死盘点（census_writeback_call_sites.md）

> 只读盘点（未改任何生产代码）。方法：全仓 grep/PowerShell 单遍扫描 `audit-platform/frontend/src/**/*.{ts,vue}`（排除 `__tests__`/`.spec.`/`.test.`），逐组件实证 `writebackTB`/`writebackTrialBalance` 及内联 `api/http.put|post('.../trial-balance/writeback')` 是**真实被消费的活路径**还是**零消费死代码**。判据（复刻 M1 D 循环）：
> - **活**：writeback 函数（或内联 handler）能从真实 UI 动作（按钮 `@click` / 自动 watcher / window CustomEvent 监听且有 dispatcher / `onAfterSave` 回调）可达；且宿主组件确有 destructure/prop 绑定/inject 并 invoke。
> - **死**：`export`/`return` 出去但**无任何调用方**——host 不 destructure、adjudication 只 emit、或事件 emit 无 listener、或整条 composable 链不被任何渲染宿主 import。
> - **待改造时实证**：需运行时（render schema 动态 sheet 名）才能确认的项，如实标注，不猜死/活。

## 汇总统计

- **直调文字命中总量**：116 行（`trial-balance/writeback` 字面量），其中 **107 行为真实 HTTP 调用**、9 行为 D 循环已迁移的注释说明（D1/D2/D2SaveInject/D2Adjudication/D3/D5/D6/D7）。
- **另有 1 处变体端点**：`useG6MainFormData.writebackTB` 用旧端点 `POST /api/projects/{pid}/trial_balance`（**非** `trial-balance/writeback`），故不在 107 行内，但同属 TB 回写旁路——**死代码**（见 G 循环）。
- **定义总数**：`writebackTB`/`writebackTrialBalance` 函数定义 78 处（不含内联 .vue handler、不含 G6 变体）。
- **按活/死分布（以"组件的 TB 回写能力"为单位统计，D 循环 M1 已处置不计入本次盘点口径）**：

| 维度 | 数量 | 说明 |
|---|---|---|
| **活路径（真实被消费）** | **约 48 处** | E1 / F1–F5 / G1–G3,G5,G7–G14（form B）/ H1–H7,H9,H10（inline .vue 或 FormData）/ I1–I6（adjudication inline）/ K1–K4,K6,K8–K13（button/inline/adjudication）/ L1–L8 / M1–M10 / N1–N5 |
| **死代码（零消费）** | **约 40+ 处** | 全部 `useX FormData.writebackTB/writebackTrialBalance` 中被 adjudication/inline 取代的**重复定义** + H8 全链 + K5/K7 无回写 + J2 全模块 + createChecklistFormData 工厂 + D4FormData（M1 残留） |
| **多科目（≥2 科目）** | **8 处** | H1(1601/1602/1603) / H5(1631/1632) / H8(死,3科目) / H9(租赁负债+未确认融资费用) / I1(1701/1702/1703) / K1(1221+坏账准备) / K6(资产+负债,动态) / G7(权益+减值,动态) |
| **发生额口径（occurrence，前端已算最终值）** | **≥14 处** | 损益类：G10–G14 / H7 / H10 / K8(6601) / K9(6602) / K11(6701) / K12(6301) / K13(6711) / I6(6602) / M(部分) / N5(6801) 等 |
| **sheet 名不可解 / 存疑（R1 风险）** | **≥20 处（待改造时实证）** | 所有 form-B / 内联 .vue / adjudication-inline 路径当前用**旧端点（仅 account_code，无 sheet_name）**，迁移到 `publish-to-tb` 时需实证审定表真实 sheet 名能否解出 `[D-N]\d+-1`；损益类发生额审定表（G/K/N 的 xxx-1）尤其存疑 |
| **经共享工厂 createChecklistFormData** | **0 处（工厂本身零调用）** | 🔴 工厂 `createChecklistFormData(` **无任何调用点**——整个工厂含其 writebackTB 是死代码 |

## 最意外的发现（4 项，全部实证）

1. **🔴 J2 整个 composable 模块是孤儿链**：`composables/workpaper/j2/`（含 `useJ2FormData.writebackTB`、`useJ2Integration.onAdjudicationComplete` 回写 2221）**没有任何渲染宿主 import**——J2 目录 10 个 `.vue`（`GtJ2DefinedBenefitPlan`/`J2Tab*`）一个都不 import 它们（既存测试 `ieOrphanBaseline.spec.ts` 已固化此判定）。J2 真实宿主 `J2TabAdjudication.vue` **根本没有 TB 回写**。⟹ 设计文档 §3 "J2 特例：保留 events/publish + actuarial 联动" **针对的是死代码**。
2. **🔴 共享工厂 `createChecklistFormData` 零调用**：`createChecklistFormData(` 全仓 0 个调用点。⟹ 设计/tasks Task 16 所述"供大批 checklist 型底稿复用，一改受益多个"**不成立**——它一个底稿都没接。
3. **🟡 K5/K7 的"回写TB"按钮是假回写**：K5 `handleTbWriteback` 弹 `已回写TB(2701)` 成功提示，但实际只 `emit('save',...)` + `publishAdjudicated()`（发事件），**从不写 trial_balance**；K7 同理只 emit save。⟹ 两者 `useK5/K7FormData.writebackTB` 是死代码，且这两个循环**当前根本没有真实 TB 回写**（改造时需决定是否补真回写，还是维持"仅审定不落 TB"）。
4. **🟡 D 循环 M1 残留死代码**：D4-1 迁移已从 `useD4Adjudication.publishAdjudicated` 移除 `dispatch('d4:writeback-trial-balance')`，但 `GtD4OperatingRevenue.vue` 仍注册 `handleD4Writeback` 监听器 + `useD4FormData.writebackTrialBalance` 仍在——**监听器无 dispatcher = 孤儿死代码**（与 M1 对 D1/D3/D5/D6/D7 的判法同源，M1 漏了 D4FormData 这一处）。

## 总表：循环/组件逐点盘点

> 列含义：**定义**=是否定义 writeback 函数或内联；**活/死**；**形态**（A=composable/adjudication 直调；B=window CustomEvent；btn=按钮 @click；inline=.vue 内联 handler；watcher=自动写）；**科目数**；**口径**（bal=余额；occ=发生额）；**sheet 可解**（迁 publish-to-tb 时 `[D-N]\d+-1` 是否可解）；**保留下游事件**；**归类**。

| 循环/组件 | 定义 writeback | 活/死 | 形态 | 科目数 | 口径 | sheet 可解 | 保留下游事件 | 归类 |
|---|---|---|---|---|---|---|---|---|
| **E1** `useE1Adjudication` | 是（byCode 遍历，self-invoke） | **活** | A（同文件 invoke） | 多科目(byCode) | bal | 待实证（E1-1?） | substantive:adjudicated | 真实改造 |
| **F1** `useF1FormData`+GtF1 | 是(1123) | **活** | B（f1:writeback-trial-balance） | 单 | bal | 待实证(F1-1) | substantive:adjudicated；保留 f1:save-items | 真实改造 |
| **F2** `useF2FormData`+GtF2 | 是(参数) | **活** | B（f2:writeback-trial-balance） | 单(参数) | bal | 待实证(F2-1) | substantive:adjudicated；f2:save-items | 真实改造 |
| **F3** `useF3FormData`+GtF3 | 是(参数) | **活** | B（f3:writeback-trial-balance） | 单(参数) | bal | 待实证(F3-1) | substantive:adjudicated；f3:save-items | 真实改造 |
| **F4** `useF4FormData`+GtF4 | 是(参数) | **活** | B（f4:writeback-trial-balance） | 单(参数) | bal | 待实证(F4-1) | substantive:adjudicated；f4:save-items | 真实改造 |
| **F5** `useF5CosSalFormData`+GtF5 | 是(参数) | **活** | B（f5:writeback-trial-balance） | 单(参数) | occ(成本) | 待实证(F5-1) | substantive:adjudicated；**f5:save-items + F5-7 校验区** | 真实改造 |
| **G1** `useG1TraFinFormData`+GtG1 | 是 | **活** | B（g1:writeback-trial-balance，eventBus+window 双听） | 单 | bal | 存疑(G1-1?) | substantive:adjudicated | 真实改造 |
| **G2** `useG2IntRecFormData`+GtG2 | 是 | **活** | B（g2:writeback-trial-balance） | 单 | bal | 存疑(G2-1?) | substantive:adjudicated；g2:save-items | 真实改造 |
| **G3** `useG3FormData`+GtG3 | 是 | **活** | B（provide `G3WritebackTbKey`） | 单 | bal | 存疑(G3-1?) | substantive:adjudicated；G3SaveItemsKey | 真实改造 |
| **G4** — | 否（无 TB 回写；仅分类 writeback 事件 `G4_CLASSIFICATION_WRITEBACK_EVENT`） | n/a | — | — | — | — | 分类 writeback（正交，非 TB） | 不在范围 |
| **G5** `useG5LonRecFormData`+GtG5 | 是 | **活** | B（g5:writeback-trial-balance） | 单 | bal | 存疑(G5-1?) | substantive:adjudicated；g5:save-items | 真实改造 |
| **G6** `useG6MainFormData` | 是(1503，**变体端点 `POST /trial_balance`**) | **死** | — | 单 | bal | 存疑 | — | 死代码清理（含变体端点） |
| **G7** `useG7FormData`+GtG7 | 是(动态 g7AccountCode+减值) | **活** | B（`writebackTb:true` 守卫的 CustomEvent） | 多(动态) | bal | 存疑(G7-1?) | substantive:adjudicated | 真实改造（多科目） |
| **G8** `useG8FormData`+GtG8 | 是(forceToast) | **活** | B（g8:writeback-trial-balance） | 单 | occ/bal | 存疑(G8-1?) | substantive:adjudicated；g8:save-items | 真实改造 |
| **G9** `useG9FormData`+GtG9 | 是(forceToast) | **活** | B（g9:writeback-trial-balance） | 单 | occ/bal | 存疑(G9-1?) | substantive:adjudicated | 真实改造 |
| **G10** `useG10FormData`+GtG10 | 是(forceToast，内部 writebackTB→writebackTrialBalance) | **活** | B（g10:writeback-trial-balance） | 单 | occ | 存疑(G10-1?) | substantive:adjudicated；g10:save-items | 真实改造 |
| **G11** `useG11FormData`+GtG11 | 是 | **活** | B（g11:writeback-trial-balance） | 单 | occ | 存疑(G11-1?) | substantive:adjudicated | 真实改造 |
| **G12** `useG12FormData`+GtG12 | 是 | **活** | B（g12:writeback-trial-balance） | 单 | occ | 存疑(G12-1?) | substantive:adjudicated | 真实改造 |
| **G13** `useG13FormData`+GtG13 | 是 | **活** | B（g13:writeback-trial-balance） | 单 | occ | 存疑(G13-1?) | substantive:adjudicated | 真实改造 |
| **G14** `useG14FormData`+GtG14 | 是 | **活** | B（g14:writeback-trial-balance） | 单 | occ | 存疑(G14-1?) | substantive:adjudicated | 真实改造 |
| **H1** `useH1FormData.writebackTrialBalance` | 是(cost/dep) | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H1** `H1TabAdjudication.vue` onWritebackTB（→useH1Adjudication.publishAdjudicated） | inline | **活** | inline callback | 多(1601/1602/1603) | bal | 待实证(H1-1) | substantive:adjudicated（onPublishEvent） | 真实改造（多科目） |
| **H2** `useH2FormData.writebackTrialBalance` | (无该 fn，H2 无 FormData writeback) | — | — | — | — | — | — | — |
| **H2** `H2TabAdjudication.vue` onWritebackTB(→useH2Adjudication) | inline | **活** | inline callback | 单(1604) | bal | 待实证(H2-1) | substantive:adjudicated | 真实改造 |
| **H3** `useH3FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H3** `H3TabAdjudicationCost.vue` 局部 writebackTrialBalance（debouncedWritebackTb watcher） | inline | **活** | watcher（1.5s debounce） | 多(grossCode/accumDepCode，本项目无则不写) | bal | 待实证(H3-1) | — | 真实改造（防跨循环污染） |
| **H4** `useH4FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H4** `H4TabAdjudication.vue` onWritebackTB(→useH4Adjudication.publishAdjudicated) | inline | **活** | inline callback | 单(1605，LIKE 前缀) | bal | 待实证(H4-1) | substantive:adjudicated | 真实改造 |
| **H5** `useH5FormData.writebackTB` | 是 | **活** | A（H5.vue onWritebackTB→formData.writebackTB('1631'/'1632')） | 多(1631/1632) | bal | 待实证(H5-1) | substantive:adjudicated | 真实改造（多科目） |
| **H6** `useH6FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H6** `H6TabAdjudication.vue` onWritebackTB(→useH6Adjudication.publishAdjudicated) | inline | **活** | inline callback | 单 | bal | 待实证(H6-1) | substantive:adjudicated（eventBus） | 真实改造 |
| **H7** `useH7FormData.writebackTB` | 是(post) | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H7** `H7TabAdjudicationCost/Fair.vue` 直调 api.put | inline | **活** | inline（publishing flag） | 单(1621) | occ/bal | 待实证(H7-1) | — | 真实改造（cost/fair 两组件） |
| **H8** `useH8FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H8** `H8TabAdjudication.vue` onWritebackTB→`emit('writeback-tb')` | inline | **🔴 死** | emit 无 listener | 多(cost/dep/impair) | bal | — | — | 死代码清理（GtH8 不绑 @writeback-tb，全链断） |
| **H9** `useH9FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **H9** `H9TabAdjudication.vue` onWritebackTB(→useH9Adjudication.publishAdjudicated) | inline | **活** | inline callback | 多(租赁负债+未确认融资费用) | bal | 待实证(H9-1) | substantive:adjudicated | 真实改造（多科目；端点路径缺 /api 前缀需归一） |
| **H10** `useH10FormData.writebackTB`（return 别名 writebackTrialBalance） | 是(H10_ACCOUNT_CODE) | **活** | A+B（GtH10 prop 绑定 + CustomEvent handler） | 单 | occ | 待实证(H10-1) | substantive:adjudicated；disposal 联动正交 | 真实改造 |
| **I1** `useI1FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate，BP-5） |
| **I1** `useI1Adjudication.saveAdjudication`（→I1.vue handleSave/onCellChange） | 是 | **活** | A（inline http.put，多科目） | 多(1701/1702/1703) | bal | 待实证(I1-1) | substantive:adjudicated | 真实改造（多科目） |
| **I2** `useI2FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate，BP-5） |
| **I2** `I2TabAdjudication.vue` writebackTb（onAfterSave） | inline | **活** | inline（**新端点 `/api/workpapers/{wpId}/writeback-trial-balance`**） | 单 | occ/bal | **已用 per-wp 端点**（非 project 旧端点） | substantive:adjudicated | 特例：已部分现代化，评估是否并入 publish-to-tb |
| **I3** `useI3FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate，BP-5） |
| **I3** `useI3Adjudication.saveAdjudication`（→I3.vue handleSave） | 是 | **活** | A（inline http.put） | 单(1711) | bal | 待实证(I3-1) | substantive:adjudicated | 真实改造 |
| **I4** `useI4FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（BP-5，tasks 已标） |
| **I4** `useI4Adjudication.writeback`（→I4.vue handleSave） | 是 | **活** | A（inline http.put） | 单(1801) | bal | 待实证(I4-1) | substantive:adjudicated | 真实改造 |
| **I5** `useI5FormData.writebackTrialBalance` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate，BP-5） |
| **I5** `useI5Adjudication.writeback`（→I5.vue handleSave） | 是 | **活** | A（inline http.put） | 单(1911) | bal | 待实证(I5-1) | substantive:adjudicated | 真实改造 |
| **I6** `useI6FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（BP-5，tasks 已标） |
| **I6** `useI6Adjudication.writeback`（→I6.vue adj.writeback() 按钮） | 是 | **活** | btn+A（inline http.put，发生额） | 单(6602) | occ | 待实证(I6-1) | substantive:adjudicated；research:expense-updated（I6→I2）；i6:adjustment-writeback | 真实改造（发生额；保留 I6→I2 联动） |
| **J1** `J1TabAdjudication.vue` writebackTB（@click 按钮） | inline | **活** | btn+inline http.put | 单(2211) | bal | 待实证(J1-1) | — | 真实改造 |
| **J2** `useJ2FormData.writebackTB`（2221） | 是 | **🔴 死** | — | 单(2221) | bal | — | (设计称 events/publish+actuarial，均死) | 死代码清理（整模块孤儿） |
| **J2** `useJ2Integration.onAdjudicationComplete`（2221） | 是 | **🔴 死** | — | 单(2221) | bal | — | events/publish + actuarial:assumption-changed→B51（均在死代码内） | 死代码清理（整模块孤儿；J2 真实宿主无 TB 回写） |
| **K1** `useK1FormData.writebackTB` | 是 | **活** | btn（K1.vue handleWritebackTB→writebackTB(rec, badDebt)） | 多(1221+坏账准备) | bal | 待实证(K1-1) | substantive:adjudicated | 真实改造（多科目） |
| **K2** `useK2FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K2** `K2TabAdjudication.vue` handleWritebackTB（@click 按钮，inline http.put） | inline | **活** | btn+inline | 单(tbAccountCode) | bal | 待实证(K2-1) | substantive:adjudicated | 真实改造 |
| **K3** `useK3FormData.writebackTB` | 是 | **活** | btn（K3.vue handleWritebackTB→writebackTB） | 单(2241) | bal | 待实证(K3-1) | substantive:adjudicated | 真实改造 |
| **K4** `useK4FormData.writebackTB` | 是 | **活** | btn（K4.vue handleWritebackTB→writebackTB） | 单(2245) | bal | 待实证(K4-1) | substantive:adjudicated | 真实改造 |
| **K5** `useK5FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理 |
| **K5** `K5TabAdjudication.vue` handleTbWriteback | inline | **🟡 死（假回写）** | btn 但**只 emit save + publishAdjudicated，从不写 TB** | (2701) | — | — | substantive:adjudicated | 特例：K5 当前无真实 TB 回写；改造须决定补真回写 or 维持"仅审定" |
| **K6** `useK6FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K6** `GtK6HeldForSale.vue` writebackTB（provide `k6WritebackTB`→K6.vue inject+btn） | inline | **活** | btn+inline（Promise.all 双 put） | 多(资产+负债，`tb_source_codes` 动态) | bal | 待实证(K6-1) | — | 真实改造（多科目动态） |
| **K7** `useK7FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理 |
| **K7** `K7TabAdjudication.vue` handleTbWriteback | inline | **🟡 死（假回写）** | btn 但**只 emit('save', K7-1-audited-total)，不写 TB** | (2401) | — | — | — | 特例：K7 当前无真实 TB 回写 |
| **K8** `useK8FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K8** `useK8Adjudication.writeback`（→K8.vue handleTbWriteback 按钮） | 是 | **活** | btn+A（inline http.put，发生额） | 单(6601) | occ | 待实证(K8-1) | substantive:adjudicated | 真实改造（发生额） |
| **K9** `useK9FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K9** `useK9Adjudication.writeback`（→K9.vue handleTbWriteback 按钮） | 是 | **活** | btn+A（inline http.put，发生额） | 单(6602) | occ | 待实证(K9-1) | substantive:adjudicated | 真实改造（发生额） |
| **K10** `useK10FormData.writebackTB`（→useK10Adjudication.writebackTB param→K10.vue btn） | 是 | **活** | btn+A | 单 | occ | 待实证(K10-1) | substantive:adjudicated | 真实改造 |
| **K11** `useK11FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K11** `useK11Adjudication.writeback`（→K11.vue handleTbWriteback 按钮） | 是 | **活** | btn+A（inline http.put，发生额） | 单(6701) | occ | 待实证(K11-1) | substantive:adjudicated | 真实改造（发生额） |
| **K12** `useK12FormData.writebackTB`（→useK12Adjudication.writebackTB param） | 是 | **死（FormData 层）** | — | — | — | — | — | 死代码清理（duplicate） |
| **K12** `K12TabAdjudication.vue` handleWritebackTBInternal（@click handleWritebackTB，inline http.put） | inline | **活** | btn+inline | 单(6301) | occ | 待实证(K12-1) | substantive:adjudicated | 真实改造（发生额） |
| **K13** `useK13FormData.writebackTB` | 是 | **死** | — | — | — | — | — | 死代码清理（duplicate） |
| **K13** `K13TabAdjudication.vue` handleWritebackTBInternal（@click，inline http.put） | inline | **活** | btn+inline | 单(6711) | occ | 待实证(K13-1) | substantive:adjudicated | 真实改造（发生额） |
| **L1** `useL1FormData.writebackTB`（src/composables/） | 是(2001) | **活** | A（useL1Adjudication destructure+invoke） | 单(2001) | bal | 待实证(L1-1) | substantive:adjudicated | 真实改造（src/composables 路径，非 components/） |
| **L2** `useL2FormData.writebackTB` | 是 | **活** | A（useL2Adjudication + L2.vue destructure+invoke） | 单 | bal | 待实证(L2-1) | substantive:adjudicated | 真实改造 |
| **L3** `useL3FormData.writebackTB`（src/composables/useL3Adjudication） | 是 | **活** | A（useL3Adjudication destructure+invoke） | 单 | bal | 待实证(L3-1) | substantive:adjudicated | 真实改造 |
| **L4** `useL4FormData.writebackTB` | 是 | **活** | A（useL4Adjudication invoke） | 单 | bal | 待实证(L4-1) | substantive:adjudicated | 真实改造 |
| **L5** `useL5FormData.writebackTB` | 是(对象参数) | **活** | A（useL5Adjudication invoke） | 单(对象) | bal | 待实证(L5-1) | substantive:adjudicated | 真实改造 |
| **L6** `useL6FormData.writebackTB` | 是 | **活** | A（useL6Adjudication invoke） | 单 | bal | 待实证(L6-1) | substantive:adjudicated | 真实改造 |
| **L7** `useL7FormData.writebackTB` | 是 | **活** | A（useL7Adjudication invoke） | 单 | bal | 待实证(L7-1) | substantive:adjudicated | 真实改造 |
| **L8** `useL8FormData.writebackTB` | 是 | **活** | A+btn（useL8Adjudication invoke + L8.vue handleWritebackTB→formData.writebackTB） | 单 | bal | 待实证(L8-1) | substantive:adjudicated | 真实改造 |
| **M1–M10** `useM{1..10}FormData.writebackTB` | 是（各 10 个） | **活** | A（各 useM{n}Adjudication `const {writebackTB}=formData` + `await writebackTB(totalRow...)`） | 单 | bal（M 权益类） | 待实证(M{n}-1) | substantive:adjudicated | 真实改造（10 个同构） |
| **N1** `useN1FormData.writebackTB` | 是(1811) | **活** | A+btn+watcher（N1.vue handleWritebackTB→formData.writebackTB；useN1Adjudication debounce watcher 亦 formData.writebackTB） | 单(1811) | bal(期末) | 待实证(N1-1) | substantive:adjudicated；确认 DEPRECATED 裸 SQL 旁路不复活 | 真实改造（注意 watcher 自动写需改显式） |
| **N2** `useN2FormData.writebackTB(amt, year)` | 是 | **活** | A+btn（useN2Adjudication + N2.vue writebackTB(amt,year)） | 单 | bal | 待实证(N2-1) | substantive:adjudicated | 真实改造 |
| **N3** `useN3FormData.writebackTB` | 是(2901) | **活** | A+btn（useN3Adjudication + N3.vue） | 单(2901) | bal | 待实证(N3-1) | substantive:adjudicated | 真实改造 |
| **N4** `useN4FormData.writebackTB` | 是 | **活** | A+btn（useN4Adjudication + useN4AdjudicationV2 + N4.vue） | 单 | bal | 待实证(N4-1) | substantive:adjudicated | 真实改造（V1+V2 两 adjudication） |
| **N5** `useN5FormData.writebackTB` | 是(6801) | **活** | btn（N5.vue handleWritebackTB→formData.writebackTB） | 单(6801) | occ(本期发生额) | 待实证(N5-1) | substantive:adjudicated | 真实改造（发生额） |
| **共享工厂** `createChecklistFormData.writebackTB` | 是（逐科目 put + emit） | **🔴 死** | — | 多(Record) | bal | — | substantive:adjudicated | 死代码清理（工厂零调用点） |
| **D4（M1 残留）** `useD4FormData.writebackTrialBalance` + GtD4 `handleD4Writeback` 监听 | 是 | **死** | B 监听无 dispatcher | 单(参数) | bal | — | — | 死代码清理（D4-1 已移除 dispatcher，监听器+FormData 成孤儿；M1 漏处置） |

## 分循环小结 + 实际改造工作量修正

> 修正原则：**活路径**才需完整改造（前端二次确认+改走 publish-to-tb+单测+集成测试）；**死代码**只需删除+收口（grep 0 调用方后删，配 M1 已建的注释范式）；**假回写/无回写**需先做产品决策（是否补真回写）。

- **E 循环（1）**：E1 活（多科目 byCode，self-invoke）。工作量=1 个真实改造（多科目 writeback_rows）。
- **F 循环（5）**：F1–F5 全活，均 form B（`f{n}:writeback-trial-balance`）。工作量=5 个真实改造（移除 CustomEvent 链 + 保留 save-items/F5-7 校验）。**FormData 层无死代码重复**（F 的 writeback 就在 FormData，被 GtF host 监听消费）。
- **G 循环（12 直调 + G4 无 + G6 变体死）**：G1–G3,G5,G7–G14 **全活**（form B）；G4 无 TB 回写（分类 writeback 正交，排除）；**G6 死**（变体端点 `POST /trial_balance`，零消费）。工作量=**11 真实改造 + 1 死代码清理（G6）**。G7 多科目动态。**关键：G8–G14 多为损益类发生额，sheet 名 R1 风险最高**。
- **H 循环（16 直调）**：**活=H1,H2,H4,H6,H9（inline .vue callback）+ H3（inline watcher）+ H5,H10（FormData writebackTB）+ H7（inline api.put）= 9 个循环真实改造**；**死=useH1/H3/H4/H6/H8/H9 FormData.writebackTrialBalance（6 处 duplicate）+ H8 整条链（emit 无 listener）**。工作量=9 真实改造 + 7 死代码清理。注意 H1(3 科目)/H5(2)/H9(2)多科目、H3 防跨循环污染、H9 端点路径缺 /api 前缀。
- **I 循环（11 直调）**：**活=I1–I6 的 Adjudication 层 inline writeback（6 个循环真实改造）**；**死=useI1/I2/I3/I4/I5 FormData.writebackTrialBalance + useI6FormData.writebackTB（6 处 duplicate，即 tasks 所述 BP-5）**。I1 多科目(3)、I6 发生额+I6→I2 联动。**I2 特例**：已用新 per-wp 端点 `/api/workpapers/{wpId}/writeback-trial-balance`（非旧 project 端点）——评估是否直接并入 publish-to-tb 或本就合规。工作量=6 真实改造（I2 可能减负）+ 6 死代码清理。
- **J 循环（3 直调）**：**J1 活**（按钮 inline，2211）=1 真实改造；**J2 全死**（useJ2FormData + useJ2Integration 整模块孤儿，2 处）=死代码清理，且**设计文档"保留 J2 events/publish + actuarial 联动"针对死代码，应从 spec 删除该约束**。工作量=1 真实改造 + 2 死代码清理（可连带整个 j2 孤儿模块登记）。
- **K 循环（20 直调）**：**活=K1,K2,K3,K4,K6,K8,K9,K10,K11,K12,K13（11 个循环真实改造）**；**死=useK2/K5/K6/K7/K8/K9/K11/K12/K13 FormData.writebackTB（duplicate）**；**假回写=K5,K7（按钮只 emit 不写 TB）**。工作量=11 真实改造 + ~9 死代码清理 + **2 产品决策（K5/K7 是否补真回写）**。多科目=K1,K6；发生额=K8,K9,K11,K12,K13。K6 动态科目（tb_source_codes）。
- **L 循环（8 直调）**：L1–L8 **全活**（A 形态，各 useL{n}Adjudication destructure+invoke；L1/L3 在 src/composables/，L2/L8 .vue 亦接）。工作量=8 真实改造。**FormData 层无死代码重复**（L 的 writeback 就在 FormData 被 Adjudication 消费）。
- **M 循环（10 直调）**：M1–M10 **全活**（10 个同构 A 形态：useM{n}Adjudication `const {writebackTB}=formData` + invoke）。工作量=10 真实改造（高度同构，可批量套模板）。**无死代码重复**。
- **N 循环（5 直调）**：N1–N5 **全活**。工作量=5 真实改造。**N1 有 debounce watcher 自动写**（useN1Adjudication）——改造须把自动写改成显式确认（否则违反 Req 1）；N5 发生额(6801)；N4 有 V1+V2 两 adjudication。确认 N1 后端 DEPRECATED 裸 SQL 旁路不复活。**无死代码重复**。

**工作量总修正**：
- 设计原估"100 前端文件逐一改造"高估。**真正需完整改造的活路径约 48 处**（E1 / F1-5 / G 11 / H 9 / I 6 / J1 / K 11 / L 8 / M 10 / N 5）。
- **死代码清理约 40+ 处**（H/I/K 的 FormData duplicate + J2 模块 + 工厂 + D4 残留 + G6 变体 + H8 链），只需 grep 0 调用后删除+注释，**无需二次确认/端点改造/端到端测试**——工作量远低于真实改造。
- **2 处产品决策先行**（K5/K7 假回写）。
- **高度同构可批量**：M1–M10（10 个几乎一样）、L2–L8、N2–N5、G8–G14（form B 发生额）——套模板一次改多个。

## R1 风险清单：sheet 名不可解 / 存疑组件（供 spec 决定规整命名 or 降级）

> `publish-to-tb` 端点靠 `extract_determination_wp_code(sheet_name)`（正则 `([D-N]\d+-1)\b`）解出子码，handler 门控 `wp_code ~ ^[D-N]\d+-1$`。**所有当前活路径都用旧端点（仅传 account_code，无 sheet_name）**，故迁移到 publish-to-tb 时每个都要实证审定表真实 sheet 名。以下按风险从高到低分层：

### 高风险（损益类发生额审定表，sheet 子码是否 `xxx-1` 存疑，须运行时/render schema 实证）
- **G8, G9, G10, G11, G12, G13, G14**（损益/公允/减值类，form B）
- **K8(6601), K9(6602), K11(6701), K12(6301), K13(6711)**（损益发生额）
- **N5(6801)** 本期发生额
- **I6(6602)** 研发费用发生额
- **H7(1621)** 投资性房地产公允；**H10** 资产处置损益发生额

### 中风险（G 系列非标准审定表，sheet 命名多样）
- **G1(G1-1?), G2, G3, G5, G7**——G 循环底稿 sheet 名历史上不统一，须逐一 grep render schema / SheetLabels 实证是否含 `G{n}-1`。

### 低风险（标准余额类审定表，子码大概率 `xxx-1`，仍需确认）
- E1 / F1-F5 / H1-H6,H9 / I1-I5 / J1 / K1-K4,K6 / L1-L8 / M1-M10 / N1-N4

### 处置建议（切换点 = 端点 `extract_determination_wp_code` 返回 None → 400）
1. 每个组件改造任务的**第一步**：`grep 组件 sheetName / render schema (backend/data/.../wp_render_schema/) / SheetLabels.ts / wp_code`，实证真实 sheet 名。
2. 可解 `[D-N]\d+-1` → 直接改走 publish-to-tb。
3. 不可解 → 任务内先规整 sheet 名（走审定表命名）；或对该单点评估是否放宽端点正则 / 保留旁路并单独登记（记录降级）。
4. **本盘点无法确定运行时 sheet 名的，全标"待改造时实证"，未猜死/活**——sheet 可解性是运行时属性（render schema 动态），静态 grep 只能定"存疑/大概率"。

## 附：判定方法可复核性（供质控复核）

- 全部结论基于单遍 PowerShell 扫描 + 定向 grep_search + 关键文件 read_file 实证，**未运行前端、未改任何生产代码**。
- 活/死判据三要素：①函数是否 export/return；②是否有跨文件 destructure/prop 绑定/inject/CustomEvent 监听；③该消费点是否被真实 UI 动作触发（button @click / watcher / onAfterSave / 有 dispatcher 的 CustomEvent）。三者缺一即判死。
- J2 孤儿判定另有既存测试 `components/workpaper/__tests__/ieOrphanBaseline.spec.ts` 交叉印证（该测试独立断言 `composables/workpaper/j2/` 11 个 composable 全链不可达渲染宿主）。
- 未纳入本盘点：S 类独立回写服务（`SEstimateTBWritebackService`/`STransactionTBWritebackService`，设计明确正交非目标）；处置/函证正交联动（disposal:completed 等）。
