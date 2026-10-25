# Requirements Document

## Introduction

本 spec 是 **H 循环（固定资产）9 条 Excel 独立 entry** 从 legacy 假双向接成真双向的**地基 spec**：
承载 H 循环共同裁决 **HC-1 ~ HC-16**、H 专属前置（BP-5 ~ BP-12）的处置边界、以及**首张 canary（H9 租赁负债明细表）**。
它是 umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure` **Task 50** 的下游实施 spec
（Task 50 只交付 H slice 与冻结口径，不接双向）。

上游沿用 F 循环共同裁决 **FC-1 ~ FC-13**（`f1-sync-coverage-and-first-canary/design.md`）
与 G 循环共同裁决 **GC-1 ~ GC-10**（`g-cycle-sync-foundation-and-first-canary/design.md`）；
🔴 **FC-3 在 H 成立**（一册一 entry，与 G 相反）、**FC-8 在 H 不适用**（9 宿主 OCR 实测全 0），
逐条重裁见 design §FC/GC 适用性重裁。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`HF-P{N}`**（H Foundation）。

🔴 **本 spec 与 slice 冲突时一律以实测为准**：Task 3 按值实测反驳了 slice 五处
（见 Requirement 3），spec 正文登记实测值并如实记录不一致，**不得为对齐 slice 伪造缺陷**。

### 三份下游 lane spec（本 spec 是它们的共同前置）

| lane spec | 覆盖 entry | 数 |
|---|---|---|
| `h3-h5-h7-variant-axis-and-dynamic-column-paradigm` | H3 / H5 / H7 | 3 |
| `h4-h8-sub-entry-lanes-and-seed-identity-defects` | H4 / H8（含 5 条 parent_duplicate 子入口） | 2 + 5 |
| `h2-h6-h10-pilot-cross-reference-lanes` | H2 / H6 / H10 | 3 |

canary（H9）在本 spec 内打通；其余 8 条由三份 lane spec 承接。
**HC-1 ~ HC-16 在本 spec 裁一次，三份 lane 只引用不复述。**

### 范围与排除（slice `slice_scope` 逐条实测 + manifest 现算复核）

**9 条独立 entry** = H 码 xlsx `independent_entry=true` 共 10 条 − H1（pilot）。
排除三类，均有依据：

1. **H1 固定资产**（`344f83216b9024e3…` / 199,413 B）—— umbrella Task 42 pilot `h1_grouped_dynamic`，
   契约 `h1.disposal_check.json` **已注册 adapter**（`register_from_manifest()` 现算命中 `{d2,d4,g7,h1}`）。
   🔴 本 spec **不得修改 H1 的契约 / adapter / golden digest**（HC-8）。
2. **H0 固定资产循环函证**（`b39df62c02be968c…` / 81,702 B）—— 归 umbrella Task 57 函证族，
   slice `belongs_to_entry=null` + `excluded_reason` 已记。
3. **5 条 parent_duplicate 子入口**（manifest 现算 `/hN/` 路径命中 5 条）—— 按 AC 1.6 不独立计数，
   但 **step 9 改线必须一并改**，实施归 `h4-h8-sub-entry-lanes-and-seed-identity-defects`。

**9 条 entry 的 manifest 实测字段（现算，非读 slice 快照）**：
`capability=single_onlyoffice` / **无 `capability_target` 字段（读取返 None）** / `adapter_id=None` /
`mounts=2` / 0 契约 / 0 representation。
🔴 slice 记的 `capability=null` / `capability_target=bidirectional` / `legacy_fake_bidirectional`
**均不是 manifest 字段值** —— 见 HC-1。

### 9 条 entry 清单（宿主 / 幻影码 / 模板 sha256+字节 / 载体族 / 专属阻塞）

| entry_id | 宿主 | 幻影码 | 模板 sha256 前 16 / 字节 | 写族 | 读族 | TB 门 | 专属阻塞 |
|---|---|---|---|---|---|---|---|
| `xlsx/gt-h2-construction-in-progress` | `GtH2ConstructionInProgress.vue` | H2C | `de9426a33e8d51e9` / 162,616 | host_inline | snapshot | 有 | BP-6 · BP-11×2 · HC-8 冻结 |
| `xlsx/gt-h3-investment-property` | `GtH3InvestmentProperty.vue` | H3I | `6526c9fc186230fa` / 146,096 | formdata | checklist GET | 有 | 变体轴×2 · BP-11×2 · HC-8 冻结(G13) |
| `xlsx/gt-h4-engineering-materials` | `GtH4EngineeringMaterials.vue` | H4E | `c2c3ee61b33f4a7c` / 112,937 | formdata | checklist GET | 有 | BP-6 · BP-11 · 2 子入口 |
| `xlsx/gt-h5-oil-gas-assets` | `GtH5OilGasAssets.vue` | H5O | `6dcc109bee631035` / 195,306 | per_tab_formdata_instance | checklist GET | 有 | BP-8 · BP-11 · HC-4 拼接键 · 变体轴 |
| `xlsx/gt-h6-asset-disposal-clearing` | `GtH6AssetDisposalClearing.vue` | H6A | `c7d0d78a798ce9c3` / 48,865 | host_inline | snapshot | 有 | BP-8 · BP-12 被害方 · HC-8 冻结 |
| `xlsx/gt-h7-biological-assets` | `GtH7BiologicalAssets.vue` | H7B | `df55f0051d9b3a67` / 225,641 | per_tab_self_persisting | checklist GET | 有（在 `useH7FormData`） | BP-8 · 变体轴×2 · SK-1~4 源头 |
| `xlsx/gt-h8-right-of-use-assets` | `GtH8RightOfUseAssets.vue` | H8R | `112053f0681642c3` / **465,476** | host_inline | render-config | **无** | 🔴 BP-5+6+7+8 · 3 子入口 · 变体轴 |
| **`xlsx/gt-h9-lease-liabilities`（canary）** | `GtH9LeaseLiabilities.vue` | H9L | `7b1afdb49f190854` / 67,693 | host_inline | render-config | **无** | 无专属（仅 BP-1~4） |
| `xlsx/gt-h10-asset-disposal-income` | `GtH10AssetDisposalIncome.vue` | H10A | `9f0d2a64dab1fd76` / 42,334 | formdata + checklist | 两者都有 | 有 | HC-10 localStorage · BP-12 发起方 · HC-8 冻结 |

### H 循环四个「干净点」（相对 D/F/G，守卫方向必须是断言「保持为无」）

1. 模板目录 11 文件**全部在 `_index.json`**、无 docx、无不可达冗余合册 ⇒ 无 F 的 BP-8 / D 的 BP-8。
2. **整册码回落实测 clean**：26 个 H 码逐个实跑 `find_template_file` / `_any`，候选集合大小**恒为 1**。
   根因是 H 按循环整册组织「一 wp_code 一册」（F2 是按 sheet 段拆 10 册共享一码）。
3. 程序表码 `H2A` 解析返 `None` 是**正确**的 ⇒ 守卫应断言 `resolved is None`，不是断言命中。
4. **FC-3 成立**（一册一 entry）。

---

## Requirements

### Requirement 1: H 循环共同裁决 HC-1 ~ HC-16 落地为可复核声明

**User Story:** 作为三份下游 lane spec 的实施者，我希望 H 循环的共性裁决只做一次并有判据锁死，
不要在四份 spec 里各裁一遍互相漂移。

#### Acceptance Criteria

1. WHEN 本 spec 交付 THEN design SHALL 承载 **HC-1 ~ HC-16** 完整裁决正文，三份 lane spec 只引用不复述。
2. WHEN 引用上游裁决 THEN SHALL 逐条给出 **FC-1~FC-13 与 GC-1~GC-10 在 H 的适用性重裁**，且
   🔴 **FC-3 SHALL 标为「在 H 成立」**（与 G 相反）、**FC-8 SHALL 标为「在 H 不适用」**
   （9 宿主 `OcrConfirm|runOcr` 实测命中 0）。
3. WHEN 声明任一 H entry 的阻塞项 THEN SHALL 逐元素取 slice `capability_target_blocked_by`（FC-13），
   **不得**跨 entry 套用；判据 SHALL 覆盖 9 条全集。
4. WHEN 登记四条「缺陷不存在」的结论（HC-14）THEN SHALL **现算**而非读 slice 快照；
   变异「往 H 模板目录塞一本未索引的册子」/「给任一 H 册加一个 definedName」SHALL 打红。
5. 🔴 WHEN 任一 lane spec 复述 HC-x 正文 THEN 跨 spec 复盘 SHALL 判为缺陷（漂移源）。

### Requirement 2: 载体族七分与「按文件名推断载体」的禁令

**User Story:** 作为实施者，我不要拿 F/G 的守卫套 H —— F 循环 8 条全是 `useFxFormData` 单一形态，
H 实测写路径 4 族、读路径 4 族、TB 发布门 2 族，照抄必假红或假绿。

#### Acceptance Criteria

1. WHEN 为任一 H entry 定位载体 THEN SHALL 按 **HD-1 写族**实测分派：
   `host_inline` 4（H2/H6/H8/H9，宿主自己 `import http from '@/utils/http'` 并 PUT）·
   `formdata_composable` 3（H3/H4/H10，`useHxFormData` 用 `api`）·
   `per_tab_formdata_instance` 1（H5，每个子 Tab 各实例化一份 `useH5FormData`）·
   `per_tab_self_persisting` 1（H7，`H7TabDetailCost.vue` 内联 `api`）。
2. WHEN 为任一 H entry 定位读路径 THEN SHALL 按 **HD-2 读族**实测分派：
   `checklist GET` 4（H3/H4/H5/H7）· `props.htmlData.responses_snapshot` 2（H2/H6，父级 render-config 透传）·
   `GET /render-config?force_component_type=…` 再合并 `sheets[].html_data.responses_snapshot` 2（H8/H9）·
   两者都有 1（H10）⇒ 🔴 **4 条 entry 的载体里没有 checklist GET**。
3. 🔴 WHEN 沿用 F 循环守卫「持久化 composable 必须自带 GET+PUT」THEN SHALL 判为**对 H 的 6 条必然假红**，
   守卫 SHALL 改成按实测族分派；判据 SHALL 对 9 条逐条给出期望族并断言族标签与实测一致。
4. WHEN 登记 **HD-7 TB 发布门**位置 THEN SHALL 断言实测事实：**宿主层只有 H10 命中 1 处**，
   真实位置在子 Tab / composable 层 —— 7 条有（H2/H3/H4/H5/H6/H7/H10）、
   🔴 **H8/H9 完全没有**；且 H5 的门在 `useH5FormData`、**H7 的门在 `useH7FormData`**。
5. WHEN 登记调整分录中央同步 THEN SHALL 断言 `useAdjustmentCentralSync` 在
   `h{2,3,4,5,6,7,8,9,10}/core/H*TabAdjustment.vue` **9/9 全覆盖**（宿主层 0）⇒
   roundtrip SHALL 把它视为 primary 表之外的**第二写入方**。

### Requirement 3: 五处 slice 与实测不一致的登记与处置

**User Story:** 作为维护者，我要看到 spec 明确写出「slice 说 A、实测是 B、按 B 走」，
而不是默默照抄 slice 导致按错误前提改代码。

#### Acceptance Criteria

1. 🔴 WHEN 处置 `useH9DualMode` THEN SHALL 登记：slice HD-3/BP-8 记其**零消费**，
   实测**生产消费 = 1**（`GtH9LeaseLiabilities.vue`）⇒ **不是孤儿，不得删**。
2. 🔴 WHEN 处置 `useH7FormData` THEN SHALL 登记：slice 记其**全仓零引用**，
   实测**生产消费 = 1**（`h7/core/H7TabAdjudicationCost.vue`）且**它承载 H7 唯一的 TB 发布门**
   （`publishToTb` 命中 2 处）⇒ 🔴 **明确禁止删除**；按 slice「删孤儿」执行会打断 H7 的 TB 发布链。
3. WHEN 声明 manifest 字段 THEN SHALL 按 HC-1 用实测值，并登记 slice 三个字段值不是 manifest 字段。
4. 🔴 WHEN 守卫比对主表键 THEN SHALL 登记：`H5-2-rows` **字面量全仓零命中**，
   H5 全部键由 `${ITEM_PREFIX}-rows` 拼接（`useH5Detail.ts#L53 ITEM_PREFIX='H5-2'`，拼接结果语义正确）
   ⇒ 字面量 grep 守卫 SHALL 加拼接解析分支（HC-4），否则必假红。
5. WHEN 处置 H5 小计行 THEN SHALL 登记实测：`useH5Adjudication.ts#L309-311` 保存前
   `.filter(r => !r.isSubtotal)`、`useH5Detail.ts#L138 subtotalRow` 是 computed ⇒ **小计行不落库**，
   契约无需把它排除在业务行之外；但 `isSubtotal` 字段落库且**恒为 false**，SHALL 声明为常量字段。
6. WHEN 确认零消费载体 THEN SHALL 按值 grep 消费方计数（HC-3），实测零消费 **5 个**：
   `useH5DualMode` / `useH7DualMode` / `useH6FormData`（测试引用 1）/ `useH8FormData` /
   `useH9FormData`（测试引用 1）；`useH2FormData` **文件不存在（定义 = 0）**。

### Requirement 4: H 专属前置 BP-5 ~ BP-12 的处置边界

**User Story:** 作为维护者，我要清楚哪些前置本 spec 修、哪些只立守卫、哪些明确归 lane spec。

#### Acceptance Criteria

1. WHEN 处置 **BP-5**（H8 四表明细种子写进零消费方 item_id）THEN 本 spec SHALL 只交付
   **HC-6 + HC-7 共性裁决与守卫**；具体修复（`GtH8RightOfUseAssets.vue#L588` 写 `H8-2-detail-prefill`，
   该字面量实测全仓仅 1 处 = 写入点自己，真库零载荷；真实主键是 `H8-2-rows`）归
   `h4-h8-sub-entry-lanes-and-seed-identity-defects`。
2. WHEN 处置 **BP-6**（三处种子行身份整体取数组下标）THEN 本 spec SHALL 只立 **HC-7 判据**：
   `GtH2ConstructionInProgress.vue#L616` `rowId:` seed-${i} · `h4DetailPrefill.ts#L50` `seed-${idx}` ·
   `GtH8RightOfUseAssets.vue#L578` `seed-${idx}`；修复分别归 lane 3（H2）与 lane 2（H4/H8）。
3. WHEN 处置 **BP-7**（H8 附注把稳定动态列 key 降级成可变 label）THEN 本 spec SHALL 只立
   **SK-1 判据**（`h8DisclosureSyncPayload.ts#L51` `cats.map(c=>({key:c.label,…}))` + `#L110` `row[c.label]=…`）；
   修复归 lane 2。🔴 SHALL 登记 BP-7 是 H 循环内部**唯一背离 H7 动态列范式的地方**。
4. WHEN 处置 **BP-8**（孤儿 legacy 载体）THEN SHALL 按 Requirement 3.1/3.2/3.6 重算成员，
   **不得**照抄 slice 的 5 条名单；本 spec 交付 HC-3 判据，删除动作归各 lane。
5. WHEN 处置 **BP-9**（manifest capability）THEN 本 spec SHALL 交付 HC-1 全部正文与迁移路径
   （必须走 `register_from_manifest()`，不得手改 manifest 文件），与 FC-12 / G 的 BP-6 同源。
6. 🔴 WHEN 处置 **BP-11**（新发现：语义耦合行身份 7 处）THEN 本 spec SHALL 交付 HC-7 三族分治裁决 +
   全仓扫描判据；SHALL 登记 slice `positional_identity_inventory` **只扫下标族、完全漏掉这族**。
   7 处：`useH2Adjudication.ts#L194` `row-total-${name}` · `#L389` `net-${name}` ·
   `useH3Adjustment.ts#L311` `${kind}-${cat}` · `useH3RentalIncome.ts#L148` `subtotal-${cat}` ·
   `useH4Adjudication.ts#L436` `net-${name}` · `useH5Adjudication.ts#L136` `row-${prefix}-${cat}` ·
   `useH8Adjudication.ts#L572` `h81-net-${cat}`。
   唯一安全形态 `useH8Adjudication.ts#L145` `h81-${block}-${category}-${rand5}`（带随机后缀）。
7. 🔴 WHEN 处置 **BP-12**（新发现：跨 entry 取数用键名猜测回退链）THEN 本 spec SHALL 交付 HC-9 裁决；
   实测 `h10RelatedH6Pull.ts#L59` `const keys = ['H6-2-rows','H6-detail-rows','H6-clearing-rows']`，
   后两键 H6 侧**零生产且真库零载荷** ⇒ 修复（收敛单一权威键 + fail-loud）归 lane 3。

### Requirement 5: 首张 canary（H9 租赁负债明细表 H9-2）端到端打通

**User Story:** 作为实施者，我要一条**有真库非空载荷**的 entry 先打通全链路，
否则 roundtrip 断言只能造数据，等于伪实证。

#### Acceptance Criteria

1. WHEN 选定 canary THEN SHALL 是 **H9**，并 SHALL 在 design 记录三条硬依据与三条逆风（§canary 选型）；
   🔴 判据 SHALL 现算 `checklist_responses` 确认 `H9-2-rows` 非空（实测 819 B / 2 行），
   且确认其余 8 条主表键零载荷或空 `[]`（实测 `H8-2-rows` / `H10-detail-rows` 为 `[]`，其余无行）。
2. WHEN 声明 H9-2 几何 THEN SHALL 按实测：两级表头 **R7/R8** · 数据区 **R9-13（5 行）** ·
   footer **R14 合计 `SUM(B9:B13)`** · 22 列（`max_column`=22，有效列 22）· 54 个公式 ·
   公式列 E/I/J/K/L/N（`E=B-C+D` · `L=I-J+K` · `N=L-M`）· 裸 `IF(` 24 处。
3. 🔴 WHEN 声明 H9-2 representation THEN SHALL 覆盖真库实测 **23 字段**全集，且：
   `terminatedFromH8` SHALL 声明为 **H8 回传的跨 entry 派生标记、OO 侧不可编辑**；
   `isRelatedParty` / `isConfirmed` / `isTerminated` SHALL 声明为**中文枚举字符串**（实测值 `"否"`），
   **不得**声明为布尔（HC-11）。
4. WHEN 声明 H9-2 行身份 THEN SHALL 覆盖真库实测两形态：
   `row-liab-H91-FILL-1784691549786`（H9-1 联动填充，带时间戳）与 `row-mrvjayxr-u0mc`（随机）⇒
   两者都属 HC-7 安全族，canary **不含**身份改造。
5. WHEN canary 通过 THEN SHALL 产出 `h9.lease_liability_detail.json` 契约 + provider
   `phase5_lease_liability_detail`，并 SHALL 走 `register_from_manifest()` 注册；
   🔴 provider 范式 SHALL 是 `phase5_*`（**不照** G7/H1 的 `pilot_*`），
   唯一复用 pilot 的是 `oo_crash_neutralization_fn`。
6. 🔴 WHEN 声明 canary 覆盖边界 THEN SHALL 明确：H9 **无 TB 发布门**（HD-7）⇒
   canary **不覆盖发布链**，发布链首例归 `h2-h6-h10-pilot-cross-reference-lanes`。
7. WHEN 声明 canary 读路径 THEN SHALL 明确它是 HD-2 **第三族**（`render-config?force_component_type`），
   即 canary 顺带把最复杂读路径先打通；判据 SHALL 断言 `force_component_type` 在 H9 宿主命中 1 处。

### Requirement 6: 跨 entry / 跨循环引用回归与主表键冻结

**User Story:** 作为维护者，我不要因为改 H 的键名而静默打断已注册的 H1 pilot 与 G13 取数。

#### Acceptance Criteria

1. 🔴 WHEN 本 spec 或任一 lane spec 触及以下键 THEN SHALL **冻结键名不改**（HC-8）：
   `H2-2-rows`（`h1CipH2Pull.ts` 消费）· `H6-1-rows` / `H6-2-rows` / `H6-1-end-balance-audited`
   （`h1SoeClearingH6Pull.ts` 消费）· `H10-detail-rows`（`h1RelatedH10Pull.ts` + `useH1LeaseCheck.ts` 消费）·
   `H3-2-fair-rows`（G 循环 `g13SourceDetailPull.ts` + `gCycleSourceFv.ts` 消费）。
2. WHEN 必须改上述任一键 THEN SHALL 另立 spec，且 SHALL 在同一变更内改 H1 / G13 侧取数文件
   并回归 H1 契约 golden digest。
3. WHEN 声明零回归基线 THEN SHALL **现算**（GC-10），**不得**写死 digest 个数或契约文件数；
   判据 SHALL 现算 `backend/data/workpaper_sync_contracts/*.json`（现算值 13 个，含新增 `f1.prepayment_detail.json`）
   与 `register_from_manifest()` 已注册集合（现算值 `{d2,d4,g7,h1}`）。
4. WHEN 登记 H 内部跨 entry 耦合 THEN SHALL 覆盖实测：H10 消费 H6（`h10RelatedH6Pull.ts` / `useH10CrossSheet.ts`）·
   H8 ↔ H9 互相消费（`useH8CrossSheet.ts` / `useH8DisposalCheck.ts` 消费 `H9-2-rows`）。

### Requirement 7: 模板侧事实与 instrumentation 边界

**User Story:** 作为实施者，我要 instrumentation 按有效内容列作业，不要在 250 列宽表上白扫。

#### Acceptance Criteria

1. WHEN 挂 OO 崩溃中性化 THEN SHALL **per-file** 挂 `oo_crash_neutralization_fn`（HC-12），
   **不得**整册统一；判据 SHALL 覆盖 9/9 全命中的实测计数：
   H8 **3710**（主源 `使用权资产 租赁负债初始及后续计量（按月）H8-6` 361r×16c / 3626 公式）·
   H7 1025 · H5 816 · H3 661 · H2 138 · H10 56 · H4 48 · H9 24 · H6 12。
2. WHEN instrumentation 扫描列 THEN SHALL 按**有效内容列**而非 `max_column`（HC-13）；
   判据 SHALL 覆盖 11 张附注披露宽表实测（`max_column` 250~257 / 有效列 6~14）：
   H2 256c/10 + 255c/14 · H3 250c/6 + 252c/9 · H4 254c/6 + 254c/8 · H5 257c/8 + 253c/6 ·
   H7 257c/11 + 256c/6 · H8 国企侧 255c/6。
3. WHEN 放 UUID 列 THEN SHALL 放在「**有效内容列 +1**」而非 `max_col+1`，
   与 G 的 16384 列策略**同源引用同一规则**（不重复裁决）。
4. WHEN 声明 footer 形态 THEN SHALL 覆盖 **HC-16 第三形态**：
   H4-2 合计行含派生单价列（`F=G28/E28` / `I=J28/H28` / `L=M28/K28` / `O=P28/N28`，非纯 SUM，
   行内同型 `F=G12/E12` 有除零风险）· H6-2 标签是 **「　合计」带全角空格前缀** ·
   H10-2 有**第二 footer 行 R18「各月比例」**；`footer_marker` 匹配 SHALL 容错全角与多 footer。
5. WHEN 声明表头层级 THEN SHALL 断言 H 是**全平台最深的 3~4 级**，其中五条是四级表头
   （H2 R9-R12 · H4 R8-R11 · H5 R9-R12 · H7 R9-R12 · H8 R8-R11）。
6. WHEN 声明同尾码双 sheet THEN SHALL 按 **HC-5 三族**（slice HD-5 只覆盖第一族）：
   计量模式（H3 / H7）· **含否减值**（H3-7 / H5-12 / H7-11 / H8-8）· **按年按月**（H8-6）⇒
   两维 `(measurement_model, sheet_code)` 声明不足，SHALL 用
   `(variant_axis, variant_value, sheet_code)` 三维或逐 sheet 全名。
7. WHEN 登记模板其他事实 THEN SHALL 断言：9 册 152 sheets · **无一个 Excel Table** ·
   H9/H10 各有 `GT_Custom` hidden sheet（其余 7 册无）。

### Requirement 8: wp_index 三处实测风险的显式规避

**User Story:** 作为实施者，我不要让契约的 sheet 定位依赖一个登记不全且按项目漂移的表。

#### Acceptance Criteria

1. 🔴 WHEN 契约声明 sheet 定位 THEN SHALL **禁止按 `wp_index.wp_name` 匹配 sheet**（HC-15）：
   实测 `H1-2` 在 project `df5b8403`（首汽租车）名为「固定资产增减变动表」，
   其余 4 个 project 名为「固定资产明细表」⇒ per-project 命名漂移。
2. 🔴 WHEN 契约声明 `sheet_code` THEN SHALL **不得依赖 wp_index 子码登记**：
   实测 H2 子码止于 `H2-6` 但前端有 `H2-14-summary` / `H2-16-dcf-assumptions`；
   H8 子码止于 `H8-6` 但前端有 `H8-10-params`。
3. 🔴 WHEN 处理 H8-6 THEN SHALL 登记语义冲突：wp_index 记「使用权资产调整分录」，
   模板实测 H8-6 是「使用权资产 租赁负债初始及后续计量（按年/按月）」⇒
   同一子码在两处指不同对象，契约 SHALL 用模板 sheet 全名消歧。
4. WHEN 登记 `wp_index` 多行 THEN SHALL 断言根因是 **project_id 维度**（每项目一行），**不是重复缺陷**。

### Requirement 9: 派生合计副本与客户端第三存储的一致性前提

**User Story:** 作为实施者，我要 roundtrip 的「HTML 侧内容 == checklist_responses」前提真的成立。

#### Acceptance Criteria

1. 🔴 WHEN 契约声明纳管键 THEN SHALL 声明 `derived_total_keys`（HC-6）：现算 **89 个**
   `*-total` / `*-subtotal` / `*-summary` 独立 checklist 键（H1 侧 4 个 + 本轮 9 条 entry 侧 **85 个**；
   逐 entry **H8 21（最多）** · H4 15 · H3 14 · H9 9 · H6 8 · H7 6 · H5 5 · H2 4 · H10 3）；
   这些键 SHALL **排除在 roundtrip 业务比对之外**，并 SHALL 指定重算责任方。
   🔴 判据 SHALL 与现算基线比对，**不得写死阈值**（数量随功能演进变化）。
2. WHEN 处置 `H7-2-cost-rows` 仅写入点自己 THEN SHALL 判为**正常非缺陷**：
   H7 审定表勾稽走 `useH7CrossSheet.ts#L52 getNum('H7-2-cost-total')`（独立 total 键），
   不遍历明细行；`H7-2-fair-rows` 同形。
3. 🔴 WHEN roundtrip 前 THEN SHALL 先 flush H10 localStorage 草稿或断言草稿为空（HC-10）：
   实测 `useH10FormData.ts` `DRAFT_PREFIX='h10-draft'#L11` ·
   `draftKey = ${DRAFT_PREFIX}:${wpId}:${itemId}#L13-14` · `setItem#L105`（PUT 重试 3 次全败时）·
   `removeItem#L97`（成功时）· `restoreDrafts#L24-37`（下次加载回灌后删）⇒
   有未同步草稿时前提不成立，roundtrip 会把草稿改动判成 OO 侧删除。
4. WHEN 接线任一 dual-mode composable THEN SHALL 避开引入第四处存储：
   实测 `useH5DualMode.ts` 有 `STORAGE_PREFIX='h5-dual-mode:'`（该 composable 当前零消费，
   一旦按「接线到同名 composable」套路走就会引入）。

### Requirement 10: prefill 归属与后端零参与的登记

**User Story:** 作为实施者，我不要去后端 prefill 引擎里找 H 的种子逻辑。

#### Acceptance Criteria

1. WHEN 定位 H 的四表种子 prefill THEN SHALL 登记实测：后端**零参与** ——
   `prefill_formula_mapping.json` 的 306 条 `mappings` 里 H 前缀命中 24 条但 `sheet` 字段**全部为 None**；
   `prefill_anchor_map.py`（691 行）与 `prefill_engine.py`（1658 行）的 H 字面量命中 **0**。
2. WHEN 修 BP-6 种子行身份 THEN SHALL 在前端改（`h4DetailPrefill.ts` / 两个宿主 .vue），
   判据 SHALL 断言后端 prefill 侧无需同步改动。

---

## 阻塞项（BP-1 ~ BP-4，9 条 entry 共有的平台级供给）

沿用 FC-13 逐元素口径，本 spec **不承诺**在缺供给时交付，相关任务在 tasks.md 标 `[ ]*`：

- **BP-1** instrumentation candidate 的平台级供给
- **BP-2** 人工审核契约的平台级契约与流程
- **BP-3** approved bundle 的发布链
- **BP-4** 真 OnlyOffice 9.4 场景集

🔴 这四条是**全循环共有**（D/E/F/G/H 同），不是 H 专属；H 专属是 BP-5 ~ BP-12。
