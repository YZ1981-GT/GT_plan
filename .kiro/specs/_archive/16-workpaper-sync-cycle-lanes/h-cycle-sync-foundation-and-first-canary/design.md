# Design Document

## Overview

本 design 交付三件事：

1. **HC-1 ~ HC-16**：H 循环共同裁决全文（三份 lane spec 只引用不复述）。
2. **FC-1~FC-13 / GC-1~GC-10 在 H 的适用性重裁**（逐条给结论，不含糊）。
3. **canary H9 的端到端设计**（契约 / representation / provider / 守卫 / roundtrip）。

🔴 **本 design 的所有事实均来自三轮按值实测**（slice 读取 → openpyxl 逐格 → 前后端+真库 grep），
与 slice 冲突处以实测为准并在 §实测与 slice 的五处不一致 逐条登记。

🔴 **Property 编号**：本 spec `Property N` = `HF-P{N}`。

---

## 实测与 slice 的五处不一致（先登记，后面所有裁决基于实测值）

| # | slice 记 | 实测 | 处置 |
|---|---|---|---|
| 1 | `useH9DualMode` 零消费（HD-3/BP-8） | 生产消费 **1**（`GtH9LeaseLiabilities.vue`） | 不是孤儿，**不得删** |
| 2 | `useH7FormData` 全仓零引用 | 生产消费 **1**（`h7/core/H7TabAdjudicationCost.vue`），且**承载 H7 唯一 TB 发布门**（`publishToTb`×2） | 🔴 **明确禁删**，删则打断 H7 发布链 |
| 3 | `capability=null` / `capability_target=bidirectional` / `legacy_fake_bidirectional` | manifest 实测 `capability=single_onlyoffice` / **无 `capability_target` 字段（返 None）** / `adapter_id=None` / `mounts=2` | 按实测写，见 HC-1 |
| 4 | 主表键 `H5-2-rows` | **字面量全仓零命中**；全部由 `${ITEM_PREFIX}-rows` 拼接（`useH5Detail.ts#L53 ITEM_PREFIX='H5-2'`） | 语义正确、字面量不存在 ⇒ HC-4 加拼接解析 |
| 5 | H5/H7 有固定 `rowId:'subtotal'` 派生合计行需契约排除 | `useH5Adjudication.ts#L309-311` 保存前 `.filter(r=>!r.isSubtotal)`；`useH5Detail.ts#L138 subtotalRow` 是 computed ⇒ **不落库** | 契约无需排除；`isSubtotal` 字段落库恒 `false`，声明为常量 |

🔴 **方法论结论**：slice 是冻结快照（2026-08-31），其「零消费 / 键字面量 / manifest 字段值」三类结论
**必须在实施前重算**。本 spec 把重算固化为 HC-3（消费方计数）+ HC-4（拼接解析）+ HC-1（manifest 现算）。

---

## HC-1 ~ HC-16 共同裁决

### HC-1　manifest capability 的实测口径与迁移路径

**现状（现算 `backend/data/workpaper_sync_entry_manifest.json`，155 entries）**：
9 条 H 独立 entry 全部 `capability=single_onlyoffice`、`capability_target` 字段**不存在**（读取返 `None`）、
`adapter_id=None`、`mounts=2`。5 条子入口同为 `single_onlyoffice`，`relationship` 字段亦返 `None`。

**裁决**：

1. spec 与守卫**一律用实测值**；slice 的三个值不是 manifest 字段，引用时须标注来源是 slice 语义注记。
2. `capability` 从 `single_onlyoffice` → `bidirectional` 的迁移**只能**由
   `WorkpaperSyncAdapterRegistry.register_from_manifest()` 在注册成功后驱动，
   🔴 **禁止手改 manifest 文件**（手改会造出「manifest 说双向、实际无 adapter」的假绿）。
3. `capability_target` 作为**新增字段**引入，缺省视为 `None`（= 未表态），不得把缺省当 `bidirectional`。
4. 与 **FC-12** 及 **G 的 BP-6** 同源，本裁决是它们在 H 的具体形态，不重复立项。

**判据**：现算 manifest 后断言 9 条 `capability == 'single_onlyoffice'` 且 `capability_target is None`；
变异「把某条手改成 `bidirectional` 而 adapter 仍为 None」SHALL 打红。

### HC-2　载体族七分：写 4 族 × 读 4 族 × TB 门 2 族

**实测族表（9 条逐条，按值 grep 宿主与 composable）**：

| entry | 写族（HD-1） | 读族（HD-2） | TB 门（HD-7）位置 |
|---|---|---|---|
| H2 | `host_inline`（`import http from '@/utils/http'` + PUT，宿主 `checklist_put`=1） | `props.htmlData.responses_snapshot`（父级 render-config 透传） | `useH2Adjudication.ts` + `H2TabAdjudication.vue` |
| H3 | `formdata_composable`（`useH3FormData`，生产消费 37 处） | `GET /checklist-responses` | `H3TabAdjudicationCost.vue` |
| H4 | `formdata_composable` | `GET /checklist-responses` | `useH4Adjudication.ts` + `H4TabAdjudication.vue` |
| H5 | `per_tab_formdata_instance`（每子 Tab 各实例化 `useH5FormData`） | `GET /checklist-responses` | **`useH5FormData.ts`** |
| H6 | `host_inline`（宿主 `checklist_put`=2） | `props.htmlData.responses_snapshot` | `useH6Adjudication.ts` + `H6TabAdjudication.vue` |
| H7 | `per_tab_self_persisting`（`H7TabDetailCost.vue` 内联 `api`，宿主 `checklist_put`=2） | `GET /checklist-responses` | 🔴 **`useH7FormData.ts`**（slice 误判为孤儿） |
| H8 | `host_inline`（宿主 `checklist_put`=1） | `GET /render-config?force_component_type=…` → 合并 `sheets[].html_data.responses_snapshot` | 🔴 **无** |
| **H9** | `host_inline`（宿主 `checklist_put`=1） | 同 H8 | 🔴 **无** |
| H10 | `formdata_composable`（`useH10FormData`） | **两者都有** | `useH10Adjudication.ts` + `H10TabAdjudication.vue` + 宿主 1 处 |

**宿主统一实测**：9 条全部 `bridge=0`（无 `useWorkpaperSyncBridge` / `WorkpaperSyncEditorHost`）·
`legacyOO=4`（`GtOnlyOfficeSheet`）· `notice=3`（`GtEntrySyncCapabilityNotice`）· `ocr=0` ·
`adjCentral=0` · `localStorage=0`；`http_import` 命中 7（H2/H3/H5/H6/H7/H8/H9，H4/H10 用 `api`）·
`force_component_type` 命中同 7 条。

**裁决**：

1. 载体定位**禁止按文件名推断**。每条 entry 的载体三元组（写 / 读 / TB 门）必须按值实测后写入契约。
2. 🔴 F 循环守卫「持久化 composable 必须自带 GET+PUT」在 H **对 6 条必然假红**
   （host_inline 4 条的 PUT 在宿主、H7 的 PUT 在 Tab、H5 的 GET/PUT 在被多实例化的 composable）⇒
   守卫改成：按族标签分派检查，族标签本身由实测表驱动。
3. `useAdjustmentCentralSync` 实测 **9/9 全覆盖**（`h{2..10}/core/H*TabAdjustment.vue` 各 3 处引用），
   宿主层 0 ⇒ roundtrip 必须把「调整分录中央同步」当作 primary 表之外的**第二写入方**，
   否则 OO 侧改调整分录后中央同步反向推，会被判成 OO 侧数据丢失。

**判据**：对 9 条逐条断言族标签 == 实测值；变异「把 H5 的族标签改成 `formdata_composable`」SHALL 打红。

### HC-3　孤儿载体判定必须按值 grep 消费方计数

**实测（全仓 `.ts`/`.vue`，按 `\b<name>\b` 计数，区分 生产 / 测试 / 定义）**：

| 载体 | 生产消费 | 测试 | 定义 | 结论 |
|---|---|---|---|---|
| `useH5DualMode` | 0 | 0 | 1 | 零消费，可删 |
| `useH7DualMode` | 0 | 0 | 1 | 零消费，可删 |
| `useH6FormData` | 0 | 1 | 1 | 零消费（仅测试引用），可删 |
| `useH8FormData` | 0 | 0 | 1 | 零消费，可删 |
| `useH9FormData` | 0 | 1 | 1 | 零消费（仅测试引用），可删 |
| `useH9DualMode` | **1**（`GtH9LeaseLiabilities.vue`） | 0 | 1 | 🔴 **不是孤儿** |
| `useH7FormData` | **1**（`h7/core/H7TabAdjudicationCost.vue`） | 0 | 1 | 🔴 **禁删**（承载 H7 唯一 TB 发布门） |
| `useH8DualMode` | 2（`useH9DualMode.ts` / `h8/impairment/H8TabRecoverable.vue`） | 0 | 1 | 在用，链式复用 |
| `useH4DualMode` | 5（宿主 + `useH6DualMode.ts` + `useH8DualMode.ts` + `H4TabImpairment.vue` + `H4TabRecoverable.vue`） | 1 | 1 | 在用，**跨 4 条 entry 链式复用** |
| `useH2FormData` | 0 | 0 | **0** | 文件不存在 |

**裁决**：

1. 删除任何 legacy 载体前，**必须**跑消费方计数并留证；**只有生产消费 == 0 才可删**。
2. 🔴 `useH7FormData` 与 `useH9DualMode` **明确不在可删名单**（slice 名单错）。
3. `useH4DualMode` 被 4 条 entry 链式复用 ⇒ 改它等于同时改 H4/H6/H8 + 2 条子入口，
   任何改动必须在 lane 2 与 lane 3 之间协调（本 spec 只立判据，不改）。
4. 「additive 注入即死代码」是**假绿第 ① 源**：按文件名对得上就当载体，会接到死代码上 ——
   宿主行为不变而守卫因「文件确实被改了」全绿。守卫必须断言**宿主/Tab 侧确实引用了新载体**。

**判据**：对上表 10 项逐条断言计数；变异「把 `useH7FormData` 列入删除清册」SHALL 打红。

### HC-4　主表键必须解析模板拼接后再比对

**实测主表键 9 条（生产命中数 / 定位）**：

| 键 | 生产命中 | 身份字段 | 定位 |
|---|---|---|---|
| `H2-2-rows` | 16 | `rowId` | `useH2Detail.ts#L260` |
| `H3-2-cost-rows` | 8 | `rowId` | `useH3DetailCost.ts#L141` |
| `H3-2-fair-rows` | 9 | `rowId` | `useH3DetailFair.ts` |
| `H4-2-rows` | 11 | `rowId` | `useH4Detail.ts#L249` |
| **`H5-2-rows`** | **0（字面量零命中）** | `rowId` | `useH5Detail.ts` 用 `${ITEM_PREFIX}-rows`，`#L53 ITEM_PREFIX='H5-2'` |
| `H6-2-rows` | 8 | `rowId` | `useH6Detail.ts#L294` |
| `H7-2-cost-rows` | 1（= 写入点自己） | `rowId` | `h7/core/H7TabDetailCost.vue#L215` 内联 |
| `H7-2-fair-rows` | 1（= 写入点自己） | `rowId` | `h7/core/H7TabDetailFair.vue` 内联 |
| `H8-2-rows` | 12 | `rowId` | `useH8Detail.ts#L229` |
| `H9-2-rows` | 10 | `rowId` | `useH9Detail.ts#L172` |
| `H10-detail-rows` | 9 | **`id`** | `useH10Detail.ts#L48` |

**H5 的 16 个 PREFIX 常量实值（按值解析）**：
`useH5Adjudication.ts` `H5-1` · `useH5Detail.ts` **`H5-2`** · `useH5Adjustment.ts` `H5-3` ·
`useH5IdleCheck.ts` `H5-4` · `useH5PolicyCheck.ts` `H5-5` · `useH5Analysis.ts` `H5-6` ·
`useH5AdditionCheck.ts` `H5-7` · `useH5DisposalCheck.ts` `H5-8` ·
`useH5Stocktake.ts` `PLAN_PREFIX=H5-9` / `CHECK_PREFIX=H5-10` / `SUMMARY_PREFIX=H5-11` ·
`useH5TitleCheck.ts` `H5-16` · `useH5RelatedParty.ts` `H5-17` ·
`useH5Lease.ts` `OP_PREFIX=H5-18` / `FIN_PREFIX=H5-19`。

**裁决**：

1. 任何「键字面量必须出现在源码里」的守卫，**必须**带拼接解析分支：
   识别 `` `${CONST}-suffix` `` 形态、解析 `CONST` 的字面量值、再比对拼接结果。
2. H5 的键**语义正确**（拼接结果确实是 `H5-2-rows`），不是缺陷；把它判成缺陷是守卫的问题。
3. `H7-2-cost-rows` / `H7-2-fair-rows` 生产命中 1 是**正常**（见 HC-6），不是 BP-5 那种缺陷。
4. `H10-detail-rows` 身份字段是 **`id` 而非 `rowId`**，且实测 `useH10Detail.ts` 有
   `addRow#L159` / `removeRow#L172` + `id: raw.id ?? generateId()#L72` ⇒
   模板 9 个固定项目行**只是种子、用户可增删** ⇒ slice 记 `generated_opaque_string`/`id` **正确**，
   **不是** `stable_template_row_key` 族。

**判据**：守卫对 11 个键逐条解析并断言命中数；变异「删掉拼接解析分支」SHALL 使 `H5-2-rows` 打红。

### HC-5　变体轴三维声明（slice HD-5 只覆盖第一族）

**实测三族**：

| 轴 | 成员 | sheet 实测 |
|---|---|---|
| `measurement_model`（计量模式） | H3 / H7 | H3 `审定表（成本模式）H3-1`/`（公允价值模式）H3-1` · `明细表（成本模式）H3-2`(48r×49c/458f)/`（公允价值模式）H3-2`(53r×31c/270f) · `增减检查表`×2；H7 `审定表`×2 · `明细表（成本模式）H7-2`(61r×51c/**745f**)/`（公允价值模式）H7-2`(57r×47c/416f) · `增加检查表`×2 · `减少检查表`×2 |
| `impairment_included`（含否减值） | H3 / H5 / H7 / H8 | H3-7 `折旧测算表（成本模式不含减值）`/`（成本模式含减值）` · H5-12 `折耗测算表（不含减值）`/`（含减值）` · H7-11 `折旧测算表（不含减值）-直线法`/`（含减值）` · H8-8 `折旧测算表（不含减值）`/`（含减值）` |
| `period_granularity`（按年按月） | H8 | H8-6 `使用权资产 租赁负债初始及后续计量（按年）`(61r×17c/263f) / `（按月）`(361r×16c/**3626f**) |

**裁决**：

1. 契约 SHALL 用 **`(variant_axis, variant_value, sheet_code)` 三维**或**逐 sheet 全名**声明，
   两维 `(measurement_model, sheet_code)` 声明**不足**（会让含否减值族与按年按月族撞进同一格）。
2. 与 **E1-3 的 `currency_variant` 不同源**：E1-3 是两张同尾码 sheet **共用一个键**（故有 variant 切换抹零风险），
   H 的三族是**各有独立键**（如 `H3-2-cost-rows` / `H3-2-fair-rows`）⇒ 不继承 E1-3 的抹零风险，
   但继承「按尾码定位会二选一错」的风险。
3. 本裁决在本 spec 裁一次；lane 2（H3/H5/H7）与 lane 2 的 H8-6 部分（在 lane 3）只引用。

**判据**：对上表 11 组双 sheet 逐组断言两张 sheet 全名不同且 sheet_code 尾码相同；
变异「只按 sheet_code 定位」SHALL 打红并指出命中 2 张。

### HC-6　派生合计副本（`derived_total_keys`）

**实测（现算，非估算）**：H 循环有 **89 个**独立 checklist 键承载派生合计
（`*-total` / `*-subtotal` / `*-summary`），其中 H1 pilot 侧 4 个、**本轮 9 条 entry 侧 85 个**。
逐 entry 分布：**H8 21（最多）** · H4 15 · H3 14 · H9 9 · H6 8 · H7 6 · H5 5 · H2 4 · H10 3 ·（H1 4）。
样例：`H4-2-detail-total`（3 处消费）· `H8-1-cost-audited-total`（4 处）·
`H6-2-subtotal-gain-loss`（4 处）· `H7-2-cost-total`（1 处）· `H3-2-cost-increase-total`（2 处）。

**裁决**：

1. 契约 SHALL 声明 `derived_total_keys` 列表，这些键 **排除在 roundtrip 业务比对之外** ——
   否则「OO 侧改明细 → 平台重算合计」会被判成用户编辑了合计。
2. 契约 SHALL 指定**重算责任方**：OO 侧改 primary 表后，由 adapter 在回写阶段重算并更新对应 total 键；
   不得依赖前端下次加载时顺手算（那会让 checklist 里存陈旧值，交叉勾稽读到错数）。
3. 🔴 `H7-2-cost-rows` / `H7-2-fair-rows` 生产命中 1（仅写入点自己）**判为正常非缺陷**：
   H7 审定表勾稽走独立 total 键（`useH7CrossSheet.ts#L52 getNum('H7-2-cost-total')`、
   `#L49` 注释「H7-1 审定表原值合计 vs H7-2 明细表期末合计」），**不遍历明细行**。
4. 与 **BP-5**（H8 写进零消费方 `H8-2-detail-prefill`）**必须区分**：BP-5 是写错键（真实主键是 `H8-2-rows`），
   H7 是键正确但无人交叉引用。判据须分开，否则会把 H7 误判成缺陷。

**判据**：现算全仓 total 键集合并与**现算基线**比对（🔴 **禁止写死阈值** —— 当前现算 89 / 9 条 entry 侧 85，
数量会随功能演进变化，写死会造假红）；对 `H7-2-cost-rows` 断言「命中 1 且存在对应 total 键」为通过；
变异「把 `H8-2-detail-prefill` 当正常」SHALL 打红（它无对应 total 键且真库零载荷）。

### HC-7　行身份三族分治（含 slice 漏掉的 BP-11 语义耦合族）

**族 A（安全）**：身份含随机 / 时间戳后缀，业务名改动不影响身份。
真库实证：`row-mrvjayxr-u0mc`（H9-2）· `row-liab-H91-FILL-1784691549786`（H9-2，H9-1 联动填充）·
`h81-cost-房屋及建筑物-ya2jc`（H8-1，`useH8Adjudication.ts#L145` `h81-${block}-${category}-${rand5}`）·
`useH5Detail.ts#L108` `row-${Math.random().toString(36).slice(2,10)}` ·
`useH5Detail.ts#L166` `row-${Date.now()}-${Math.random()...slice(2,6)}`。

**族 B（BP-6 下标身份，3 处，slice 已记）**：身份值整体由数组下标构成且写进 primary managed table。
`GtH2ConstructionInProgress.vue#L616` `` rowId:`seed-${i}` `` ·
`h4DetailPrefill.ts#L50` `seed-${idx}` · `GtH8RightOfUseAssets.vue#L578` `seed-${idx}`。

**族 C（BP-11 语义耦合身份，7 处，🔴 slice 完全漏）**：身份内嵌业务名称且无随机后缀 ⇒
类别 / 项目改名即身份漂移，roundtrip 判成「删一行 + 增一行」。

| 位置 | 形态 | 真库实证 |
|---|---|---|
| `useH2Adjudication.ts#L194` | `` `row-total-${name}` `` | — |
| `useH2Adjudication.ts#L389` | `` `net-${name}` `` | — |
| `useH3Adjustment.ts#L311` | `` `${kind}-${cat}` `` | — |
| `useH3RentalIncome.ts#L148` | `` `subtotal-${cat}` `` | — |
| `useH4Adjudication.ts#L436` | `` `net-${name}` `` | — |
| `useH5Adjudication.ts#L136` | `` `row-${prefix}-${cat}` `` | 🔴 `H5-1-cost-rows` 1059 B 实证 `"rowId":"row-c-油井资产"` |
| `useH8Adjudication.ts#L572` | `` `h81-net-${cat}` `` | — |

**裁决**：

1. 族 B 与族 C **都必须**改为稳定身份（族 A 形态）。
2. 🔴 改造 SHALL 带**旧身份迁移映射**：真库已落库族 C 身份（`row-c-油井资产` 等），
   直接换生成规则会让既有行全部变成「新行」，历史金额串位。
3. 🔴 slice `positional_identity_inventory` 的扫描口径（17 命中分三族、只识别下标族）
   **必须扩充**为同时识别族 C 正则 `` rowId\s*:\s*`[^`]*\$\{[^}]*(category|name|label|item|cat)[^}]*\}[^`]*` ``
   且排除带随机后缀的形态。
4. slice 对族 B/C 之外的 B/C 两族（H3/H6 的展示序号）判定**仍然有效**：那是展示序号非身份，
   不分开会把展示序号误判成位置化身份（G12 踩过同一坑）。

**判据**：族 C 扫描 SHALL 命中 7 处（现算）；变异「把 `useH8Adjudication.ts#L145` 也算进族 C」
SHALL 打红（它有 `${rand5}` 后缀，属族 A）。

### HC-8　跨 entry / 跨循环引用回归与主表键冻结

**实测跨引用图**：

| 消费方 | 所属 | 消费的 H 键 |
|---|---|---|
| `h1CipH2Pull.ts` | H1 pilot（**adapter 已注册**） | `H2-2-rows` |
| `h1SoeClearingH6Pull.ts` | H1 pilot | `H6-1-rows` / `H6-2-rows` / `H6-1-end-balance-audited` |
| `h1RelatedH10Pull.ts` | H1 pilot | `H10-detail-rows` |
| `useH1LeaseCheck.ts` | H1 pilot | `H10-detail-rows`（+ 一批 H1 自有键） |
| `g13SourceDetailPull.ts` | **G 循环** | `H3-2-fair-rows` |
| `gCycleSourceFv.ts` | **G 循环** | `H3-2-fair-rows` |
| `h10RelatedH6Pull.ts` | H10 | `H6-2-rows`（+ 两个不存在的猜测键，见 HC-9） |
| `useH10CrossSheet.ts` | H10 | `H6-2-rows` / `H6-clearing-rows` / `H6-detail-rows` |
| `useH8CrossSheet.ts` / `useH8DisposalCheck.ts` | H8 | `H9-2-rows` |

**裁决**：

1. 🔴 **本轮冻结以下键名不改**：`H2-2-rows` · `H6-1-rows` · `H6-2-rows` · `H6-1-end-balance-audited` ·
   `H10-detail-rows` · `H3-2-fair-rows`。理由：前 5 个被**已注册 adapter 的 H1 pilot** 消费
   （golden digest 已锁），第 6 个被 G 循环消费。本轮只补契约与 adapter，**不动键名**。
2. 必须改上述任一键时 SHALL 另立 spec，且在同一变更内改 H1 / G13 侧取数文件 + 回归 H1 golden digest。
3. 🔴 **零回归基线一律现算**（GC-10）：
   契约目录现算 **13 个 json**（`_example.candidate` / b60 / d1 / d2 / d3 / d4 / d5 / d6 / d7 / e1 /
   **f1.prepayment_detail** / g7 / h1）· `register_from_manifest()` 已注册现算 **`{d2,d4,g7,h1}}`** ·
   `registry.py` 有 `DELIVERED_ENGINE_ADAPTERS#L901` / `PENDING_ENGINE_ADAPTERS#L927` 两清单。
   **不得**在 spec / 守卫里写死这些个数。

**判据**：守卫现算跨引用图并断言 9 行全在；变异「改 `H6-2-rows` 为 `H6-2-detail-rows`」
SHALL 使 H1 侧 3 个 Pull 文件的引用打红。

### HC-9　猜键回退链（BP-12）

**实测**：`h10RelatedH6Pull.ts#L59` `const keys = ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']`。
`H6-detail-rows` / `H6-clearing-rows` 在 **H6 侧生产命中 0**（只被 H10 侧两个文件引用：
`h10RelatedH6Pull.ts` + `useH10CrossSheet.ts`），且**真库零载荷** ⇒ 是猜测键不是别名。
同文件 `#L4` 注释已写明真源：「H6 明细在 H6 WP 的 checklist『H6-2-rows』，不在 H10 allResponses ——
须 HTTP 拉取后勾稽」。

**裁决**：

1. 回退链 SHALL 收敛为**单一权威键** `H6-2-rows` + **fail-loud**（拉不到就报错 / 显式空态），
   **禁止**静默取空 —— 现状是 H6 改键后 H10 勾稽静默变 0，无任何提示。
2. 同型扫描 SHALL 覆盖全 H：任何 `const keys = [...]` 形态的多键回退都要登记并逐键验证生产存在性。
3. 修复归 lane 3（`h2-h6-h10-pilot-cross-reference-lanes`），本 spec 只立判据。

**判据**：扫描 `const keys\s*=\s*\[` 形态并对每个键断言「H 侧生产命中 > 0」；
`H6-detail-rows` / `H6-clearing-rows` SHALL 打红。

### HC-10　客户端第三处存储（localStorage 草稿）

**实测 `useH10FormData.ts`（228 行）**：
`#L11 const DRAFT_PREFIX = 'h10-draft'` · `#L13-14 draftKey(wpId,itemId) = ${DRAFT_PREFIX}:${wpId}:${itemId}` ·
`#L105 localStorage.setItem(draftKey(...), JSON.stringify(updated))`（PUT 重试 3 次全败时）·
`#L97 localStorage.removeItem(draftKey(...))`（PUT 成功时）·
`#L24-37 restoreDrafts()` 遍历 `localStorage` 前缀匹配、`JSON.parse` 回灌、`#L35 removeItem`、`#L54` 在初始化时调用。

**裁决**：

1. 🔴 roundtrip 的前提「HTML 侧内容 == `checklist_responses`」在**有未同步草稿时不成立** ⇒
   roundtrip 前 SHALL 先 flush 草稿（触发重试成功）**或**断言草稿键集合为空；
   否则会把草稿里的改动判成 OO 侧删除。
2. 🔴 接线 dual-mode composable 时 SHALL 避开引入**第四处存储**：
   实测 `useH5DualMode.ts` 有 `STORAGE_PREFIX = 'h5-dual-mode:'`。该 composable 当前生产零消费，
   但按「接线到同名 composable」的常规套路走就会把它激活 ⇒ H5 的接线方案必须显式说明如何处置。
3. H10 的具体处置归 lane 3；H5 的处置归 lane 1（`h3-h5-h7-...`）。

**判据**：roundtrip 前置断言 `localStorage` 中 `h10-draft:` 前缀键数 == 0；
变异「造一条草稿后跑 roundtrip」SHALL 打红并指出草稿键名。

### HC-11　中文枚举域与跨 entry 派生字段的 representation

**实测（`H9-2-rows` 真库载荷 819 B，23 字段）**：
`rowId` · `lessor` · `contractNo` · `assetDesc` · `ibrRate` · `leaseTerm` · `beginBalance` ·
`repayment` · `interestAccrued` · `beginAje` · `repayAje` · `interestAje` · `reclassification` ·
`dueWithin1Y` · `due1To2Y` · `due2To3Y` · `dueOver3Y` ·
**`isRelatedParty` / `isConfirmed` / `isTerminated` = `"否"`（中文枚举字符串，不是布尔）** ·
`terminationDate`（`""` 空串）· **`terminatedFromH8` = `false`（H8 回传派生标记）**。

**裁决**：

1. representation SHALL 把 `is*` 三字段声明为**枚举域 = 中文字面量集合**（至少 `{"是","否"}`，
   实际取值域须在 lane 实施时按前端 options 现算补全），**不得**声明为 boolean ——
   否则回写会把 `"否"` 写成 `false`，前端下拉框失配。
2. `terminatedFromH8` SHALL 声明为**跨 entry 派生字段、OO 侧不可编辑**（`readonly` / `derived`）——
   它由 H8 终止租赁流程回传，OO 侧编辑会被 H8 下次回传覆盖，属于必然丢失编辑的字段。
3. `H8-1-rows` 的 `isSubtotal` / `isEditable` 同属该类（实测 `H5-1-cost-rows` 载荷含
   `"isSubtotal":false,"isEditable":true`）⇒ 声明为常量 / 派生，见实测不一致第 5 条。
4. 同类扫描 SHALL 覆盖全 H 主表键载荷：凡值域是中文字面量或名字带 `From{Entry}` 的字段都按本裁决处理。

**判据**：canary representation 断言 23 字段全覆盖、3 个枚举域为中文、
`terminatedFromH8` 标 `derived`；变异「把 `isConfirmed` 声明为 boolean」SHALL 打红。

### HC-12　per-file 裸 IF 中性化

**实测裸 `IF(` 逐册**（按 `_BARE_IF_CALL` 真实正则，9/9 全命中）：
H8 **3710**（主源 `使用权资产 租赁负债初始及后续计量（按月）H8-6` 361r×16c / 3626 公式）·
H7 1025 · H5 816 · H3 661 · H2 138 · H10 56 · H4 48 · H9 **24** · H6 **12**。

**裁决**：

1. `StoreMergePlan.oo_crash_neutralization_fn` SHALL **per-file** 挂载，**不得**整册统一 ——
   H8 的 3710 与 H6 的 12 差 300 倍，统一挂会在 H6 上白跑、在 H8 上一次处理量过大。
2. 这是 H 循环**唯一复用 pilot 产物**的地方（复用 `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas`）；
   其余一律走 `phase5_*` 范式。
3. 🔴 前置核查 SHALL 用 `git show HEAD:` 确认该函数**函数体**在 HEAD
   （历史上有「调用点在 HEAD、函数体从未落地、两处 import 跑在 `ImportError` 上」的先例）。

**判据**：对 9 册逐册断言中性化前后裸 IF 计数差 == 该册命中数；变异「整册统一挂」SHALL 打红。

### HC-13　宽表有效列边界

**实测 11 张附注披露宽表**（`max_column` / 有效列）：
H2 `256/10` + `255/14` · H3 `250/6` + `252/9` · H4 `254/6` + `254/8` ·
H5 `257/8` + `253/6` · H7 `257/11` + `256/6` · H8 国企侧 `255/6`。
（H8 上市侧仅 7c · H6 5c · H9 6c · H10 17c/5c 不在其列。）

**裁决**：

1. instrumentation SHALL 按**有效内容列**扫描，不按 `max_column` —— 否则每张表白扫 240+ 空列。
2. UUID 列 SHALL 放「**有效内容列 +1**」，**同源引用** G 的 16384 列策略（`g4-g6-shared-workbook-three-entry-lanes`
   与 `g5-nested-sections-and-template-defects` 引用的同一规则），本 spec 不重复裁决。
3. 这 11 张正是 H7 动态列范式（SK-3「列数由数据决定」）的作业面 ⇒ lane 1 实施时须与 SK-3 联动。

**判据**：断言 11 张表的有效列数 == 实测值；变异「按 `max_column` 放 UUID」SHALL 打红（落在 251+ 列）。

### HC-14　四个干净点的守卫方向：断言「保持为无」

**实测**：

| 项 | H 实测 | 对照 |
|---|---|---|
| definedName 残留 | **9 册全 0** | G3 约 480 · G4 29 · F1-F5 有残留 |
| 合计行漏加小计 | **0 格** | G5-2 45 格 · G7-2 36 格 |
| 越界引用 | **0 格** | G5-1!B35 · F5-7!G31 |
| 整册码回落 | **clean**（26 码逐个实跑 `find_template_file`/`_any`，候选集合大小恒 1） | F2 按 sheet 段拆 10 册共享一码 |
| 程序表码 `H2A` 解析 | 返 **None**（正确） | — |

**裁决**：

1. 这四项（+ `H2A`）的守卫方向是**断言保持为无 / 为 None**，不是断言命中。
2. 🔴 结论 SHALL **现算**而非读 slice 快照；变异「往 H 模板目录塞一本未索引的册子」
   / 「给任一 H 册加一个 definedName」/「把 `H2A` 守卫写成断言 resolved 非空」SHALL 打红。
3. 根因登记：H 按循环整册组织「一 wp_code 一册」⇒ FC-3 在 H 成立、无 F 的 BP-8 / D 的 BP-8。

**判据**：4 项现算断言 + `H2A` 断言 `resolved is None`。

### HC-15　wp_index 三处风险的显式规避

**实测**：

1. **per-project 命名漂移**：`wp_index` 按 `project_id` 一项目一行（**非重复缺陷**）；
   但 `H1-2` 在 project `df5b8403…`（首汽租车）`wp_name` = 「固定资产增减变动表」，
   其余 4 个 project = 「固定资产明细表」。
2. **子码登记不全**：H2 子码止于 `H2-6`（审定/明细/利息资本化/转固/分析/调整），
   但前端有 `H2-14-summary` / `H2-16-dcf-assumptions`；H8 子码止于 `H8-6`，但前端有 `H8-10-params`。
   根因：9 册共 152 sheets，wp_index 登记的 H 子码约 50 个。
3. **H8-6 语义冲突**：`wp_index` 记「使用权资产调整分录」，模板实测 H8-6 是
   「使用权资产 租赁负债初始及后续计量（按年/按月）」。

**裁决**：

1. 🔴 契约 `source_ref` **禁止按 `wp_index.wp_name` 匹配 sheet**（风险 1）。
2. 🔴 契约 `sheet_code` **不得依赖 wp_index 子码登记**（风险 2）—— 以模板 sheet 全名为准。
3. 🔴 涉及 H8-6 时 SHALL 用模板 sheet 全名消歧（风险 3），并在 lane 3 登记该冲突待平台侧修正。
4. 本 spec **不修** wp_index（跨 spec 范围），只立规避判据。

**判据**：契约 schema 校验断言 `source_ref` 不含 `wp_name` 字段来源；
变异「用 wp_name 定位 H1-2」SHALL 在 `df5b8403` 项目上打红。

### HC-16　footer 第三形态与多 footer

**实测 9 主表 footer**：

| entry | footer | 形态 |
|---|---|---|
| H2 | R21 `SUM(J13:J20)` | 纯 SUM |
| H3 | R28 `SUM(C13:C27)` | 纯 SUM |
| **H4** | R28 | 🔴 **含派生单价列**：`F=G28/E28` · `I=J28/H28` · `L=M28/K28` · `O=P28/N28`；行内同型 `F=G12/E12` |
| H5 | R33 | 纯 SUM |
| **H6** | R16 | 🔴 标签 **「　合计」带全角空格前缀** |
| H7 | R37 | 纯 SUM |
| H8 | R32 | 纯 SUM |
| **H9（canary）** | R14 `SUM(B9:B13)` | 纯 SUM |
| **H10** | R17 合计 + 🔴 **R18「各月比例」第二 footer 行** | 双 footer |

**裁决**：

1. footer 第三形态（派生列）SHALL 声明为 `derived` 并带**除零守卫**（`E28`=0 时 `F` 应为空/0 而非 `#DIV/0!`）；
   同族先例 F4-7 `G=365/(E/F)`。
2. `footer_marker` 匹配 SHALL 容错**全角空格前缀**（同 F3 的「合␠␠计」族）与**多 footer**。
3. H10-2 的 `T/Y` 占比列引合计行（`=IF($Q$17=0,0,Q8/$Q$17)`，同 G11-2 `$F$31` 形态）
   与 `Z` 列嵌套 IF 判断式（`=IF(AND(X8=0,Q8>0),1,IF(AND(X8…`）SHALL 一并声明为 derived。
4. H10-2 的 12 个月度列 B-M + `N=SUM(B8:M8)` 属月度矩阵族（同 F5-2 / D4-2），
   声明规则同源引用，不重复裁决。

**判据**：对 9 条逐条断言 footer 形态标签；变异「H6 footer_marker 写成不含全角空格的『合计』」SHALL 打红。

---

## FC-1 ~ FC-13 与 GC-1 ~ GC-10 在 H 的适用性重裁

### FC 系列（来源 `f1-sync-coverage-and-first-canary/design.md`）

| 裁决 | 在 H 的结论 | 依据 |
|---|---|---|
| FC-1 | 适用 | — |
| FC-2 | 适用 | — |
| **FC-3** | 🔴 **成立**（与 G 相反） | H 按循环整册组织「一 wp_code 一册」；26 码回落候选恒 1 |
| FC-4 | 适用 | — |
| FC-5 | 适用（H 无首例外，不触发） | H 模板缺陷为 0（HC-14） |
| FC-6 | 适用 | — |
| FC-7 | 适用 | — |
| **FC-8** | 🔴 **不适用（零命中）** | 9 宿主 `OcrConfirm\|runOcr` 实测命中 **0** |
| FC-9 | 适用 | — |
| FC-10 | 适用 | — |
| **FC-11** | 适用性待定 → **本 spec 判为不命中** | FC-11 是 F3 的工具链根因（按 sheet 段拆册共享一码），H 一册一码故无此形态 |
| **FC-12** | 适用，具体形态 = **HC-1** | manifest capability，与 G BP-6 / H BP-9 同源 |
| FC-13 | 适用（逐元素取 `capability_target_blocked_by`，不跨 entry 套用） | 9 条阻塞项各异 |

### GC 系列（来源 `g-cycle-sync-foundation-and-first-canary/design.md`）

| 裁决 | 在 H 的结论 | 备注 |
|---|---|---|
| GC-1（representation entry pointer 按 `entry_id` 不按 wp_code） | **适用且更强需要** | H 有 5 条子入口共用父级 wp_code_pattern（`H4T` / `H8T`），按 wp_code 会撞 |
| GC-2（`oo_crash_neutralization_fn`） | 适用，具体化为 **HC-12**（per-file） | — |
| GC-3 | 适用 | — |
| GC-4（`TransposedSheetSpec`） | **不命中** | H 9 主表无转置形态（全部 row-table） |
| GC-5 | 适用 | — |
| GC-6 | 适用 | — |
| GC-7 | 适用 | — |
| GC-8 | 适用 | — |
| GC-9（TB 发布门三家缺口） | **适用且在 H 扩大**：H8/H9 **完全无发布门**（HD-7） | 见 HC-2 第 4 行 |
| GC-10（零回归基线现算） | **适用，强制** | 见 HC-8 第 3 条；契约数现算 13、注册集现算 `{d2,d4,g7,h1}` |
| 16384 列 / UUID 放「有效内容列 +1」 | 适用，同源引用（**不重复裁决**） | 见 HC-13 |

---

## canary 选型：为什么是 H9

### 三条硬依据

1. 🔴 **真库唯一非空主表载荷**。现算 `checklist_responses`（载荷列 = `remark`）：
   9 条主表键只有 3 条命中 —— `H8-2-rows` = `[]`（2 B 空数组）· `H10-detail-rows` = `[]` ·
   **`H9-2-rows` = 819 B / 2 行真实数据**；H2/H3cost/H3fair/H4/H5/H6/H7 主表键**无行**。
   沿用 G2 的选型标准「真库有非空载荷」——否则 roundtrip 断言只能造数据，等于伪实证。
2. **几何最简族**：两级表头 R7/R8 · 数据区 R9-13（**仅 5 行**）· footer R14 `SUM(B9:B13)` ·
   22 列 · 54 公式 · 裸 IF 24（次少，仅多于 H6 的 12）。
3. **无专属阻塞**：`capability_target_blocked_by` 在 BP-1~BP-4 之外为空
   （对比 H8 的 BP-5+6+7+8 四条、H5/H6/H7 的 BP-8）。

### 三条逆风与代价（如实登记）

1. 🔴 H9 **无 TB 发布门**（实测 `publishToTb` 在 H9 全链路 0 处）⇒
   **canary 不覆盖发布链**，发布链首例移到 lane 3（H6 或 H10）。
2. H9 读路径是 HD-2 **第三族**（`GET /render-config?force_component_type=…` 再合并
   `sheets[].html_data.responses_snapshot`），不是最简的 checklist GET ⇒
   代价是 canary 复杂度上升，收益是**最复杂读路径先打通**，后两族更简单。
3. H9 载荷含**跨 entry 派生标记** `terminatedFromH8` + **3 个中文枚举字段** ⇒
   契约必须先解决 HC-11 两类声明，canary 不能绕开。

### 否决 H6 的理由

H6 在几何上更简（裸 IF **12** 全 H 最少 · 16 有效列最少 · 两级表头 · 42 公式 · 数据区仅 R11-15），
且**有** TB 发布门，但被否决：

1. 🔴 **真库零载荷** ——`H6-2-rows` 无行，roundtrip 无法真库实证（与依据 1 直接冲突）。
2. 🔴 被**已注册的 H1 pilot** 与 H10 **双向跨引用**（`h1SoeClearingH6Pull.ts` 取 3 个 H6 键 ·
   `h10RelatedH6Pull.ts` / `useH10CrossSheet.ts` 取 `H6-2-rows`）⇒ 改键风险全 H 最高。
3. footer 是「　合计」全角空格（HC-16 特例），canary 不宜先吃特例。
4. 它是 **BP-12 猜键回退链的被害方**，处置前提是先修 HC-9。

---

## canary H9 端到端设计

### 契约 `h9.lease_liability_detail.json`

```
entry_id           : xlsx/gt-h9-lease-liabilities          # GC-1：按 entry_id 不按 wp_code
provider_id        : phase5_lease_liability_detail          # phase5_* 范式，不照 pilot_*
source_ref         : { workbook_sha256: 7b1afdb49f190854…, sheet_name: "租赁负债明细表H9-2" }
                     # HC-15：用 sheet 全名，禁用 wp_index.wp_name
primary_table      : { item_id: "H9-2-rows", identity_field: "rowId",
                       header_rows: [7, 8], data_rows: [9, 13], footer_row: 14,
                       footer_kind: "pure_sum", footer_formula: "SUM(B9:B13)",
                       effective_columns: 22 }
derived_total_keys : ["H9-2-detail-total-audited", "H9-2-total-end"]   # HC-6，现算补全
derived_fields     : ["terminatedFromH8"]                              # HC-11
enum_fields        : { isRelatedParty: ["是","否"], isConfirmed: ["是","否"],
                       isTerminated: ["是","否"] }                      # HC-11 中文枚举
formula_columns    : ["E","I","J","K","L","N"]   # E=B-C+D / L=I-J+K / N=L-M
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # HC-12 per-file
uuid_column        : 23        # HC-13：有效内容列(22) + 1
carrier            : { write: "host_inline", read: "render_config_force_component_type",
                       tb_publish_gate: null }                          # HC-2 实测族
variant_axis       : null      # HC-5：H9 无变体轴
```

### representation（23 字段，真库实证驱动）

按 HC-11 声明：17 个数值/文本字段常规、3 个中文枚举、1 个 derived（`terminatedFromH8`）、
`rowId` 为 identity、`terminationDate` 为可空日期字符串（实测空串 `""`）。

🔴 行身份两形态均属 HC-7 **族 A（安全）**：`row-liab-H91-FILL-1784691549786`（H9-1 联动填充带时间戳）
与 `row-mrvjayxr-u0mc`（随机）⇒ **canary 不含身份改造**，改造留给 lane 1/2/3。

### roundtrip 前置断言

1. HC-10：`localStorage` 中 `h10-draft:` 前缀键数 == 0（H9 本身无 localStorage，但同页可能有 H10 草稿）。
2. HC-2：`useAdjustmentCentralSync` 被 `h9/core/H9TabAdjustment.vue` 消费（3 处）⇒
   roundtrip 期间**冻结**调整分录中央同步，否则第二写入方会污染比对。
3. HC-6：`derived_total_keys` 排除在业务比对之外。
4. HC-8：不改 `H9-2-rows` 键名（虽然 H9 不在冻结名单，但它被 `useH8CrossSheet.ts` /
   `useH8DisposalCheck.ts` 消费 ⇒ 改键会打断 H8，同样冻结）。

### Property（HF-P）

| # | Property | 判据 |
|---|---|---|
| HF-P1 | manifest 9 条 `capability=='single_onlyoffice'` 且 `capability_target is None` | HC-1 |
| HF-P2 | 载体族表 9 行 == 实测 | HC-2 |
| HF-P3 | 消费方计数 10 项 == 实测；`useH7FormData`/`useH9DualMode` 不在删除清册 | HC-3 |
| HF-P4 | 11 个主表键解析（含拼接）命中数 == 实测 | HC-4 |
| HF-P5 | 11 组同尾码双 sheet 全名不同且尾码相同 | HC-5 |
| HF-P6 | total 键集合与现算基线一致（当前 89 / entry 侧 85，禁写死）；`H7-2-cost-rows` 判正常 | HC-6 |
| HF-P7 | 族 C 扫描命中 7 处；`#L145` 不入族 C | HC-7 |
| HF-P8 | 跨引用图 9 行全在；6 个冻结键未改 | HC-8 |
| HF-P9 | `const keys=[...]` 逐键生产存在性；2 个猜测键打红 | HC-9 |
| HF-P10 | roundtrip 前草稿键数 == 0 | HC-10 |
| HF-P11 | canary representation 23 字段 + 3 中文枚举 + 1 derived | HC-11 |
| HF-P12 | 9 册裸 IF 中性化前后差 == 实测计数 | HC-12 |
| HF-P13 | 11 张宽表有效列 == 实测；UUID 落在有效列+1 | HC-13 |
| HF-P14 | 4 个干净点现算保持为无；`H2A` 断言 None | HC-14 |
| HF-P15 | 契约 `source_ref` 不依赖 `wp_name` / wp_index 子码 | HC-15 |
| HF-P16 | 9 条 footer 形态标签 == 实测；H6 全角空格容错 | HC-16 |
| HF-P17 | canary 真库 `H9-2-rows` 非空（现算 ≥ 819 B） | canary 依据 1 |
| HF-P18 | 零回归基线现算（契约数 / 注册集），不写死 | GC-10 / HC-8 |
