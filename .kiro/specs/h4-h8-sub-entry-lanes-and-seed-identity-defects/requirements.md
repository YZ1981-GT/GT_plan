# Requirements Document

## Introduction

本 spec 是 H 循环三份 lane spec 之一，覆盖 **H4 工程物资 / H8 使用权资产** 两条独立 entry
**+ 5 条 parent_duplicate 子入口**（全 H 的子入口都在这两条上）。

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（承载 **HC-1 ~ HC-16**）。
🔴 **本 spec 只引用 HC-x，不复述其正文**。

**聚类依据**（为什么这两条在一起）：
1. **5 条子入口全在 H4 / H8 上**（G 循环为 0 条）⇒ 子入口改线规则必须一次裁决；
2. **BP-5 / BP-6 / BP-7 全集在这两条上**（H8 独占 BP-5+6+7，H4 有 BP-6）；
3. H8 是全 H 最重（模板 465,476 B / 裸 IF **3710**），H4 有 **footer 第三形态**（派生单价列）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`HS-P{N}`**（H Sub-entry）。

### 两条独立 entry 实测底账

| entry_id | 宿主 | 幻影码 | 模板 sha256 前 16 / 字节 | 写族 | 读族 | TB 门 |
|---|---|---|---|---|---|---|
| `xlsx/gt-h4-engineering-materials` | `GtH4EngineeringMaterials.vue` | H4E | `c2c3ee61b33f4a7c` / 112,937 | `formdata_composable` | `GET /checklist-responses` | `useH4Adjudication.ts` + `H4TabAdjudication.vue` |
| `xlsx/gt-h8-right-of-use-assets` | `GtH8RightOfUseAssets.vue` | H8R | `112053f0681642c3` / **465,476（全 H 最大）** | `host_inline`（宿主 `checklist_put`=1） | `GET /render-config?force_component_type=…` → 合并 `sheets[].html_data.responses_snapshot` | 🔴 **无** |

两条共同：`capability=single_onlyoffice` / 无 `capability_target` 字段 / `adapter_id=None` /
`mounts=2` / 0 契约 / 0 representation / 宿主 `bridge=0` `legacyOO=4` `notice=3` `ocr=0` /
`useAdjustmentCentralSync` 在各自 `H*TabAdjustment.vue` 命中 3 处。

🔴 **H8 无 TB 发布门**（实测 `publishToTb` 在 H8 全链路 0 处）—— 与 H9 同，是 HD-7 的两条缺口之一。

### 5 条 parent_duplicate 子入口（manifest 现算 `/hN/` 路径）

| 子入口 entry_id | 幻影码 | manifest `relationship` | 关键事实 |
|---|---|---|---|
| `xlsx/h4/impairment/h4-tab-impairment` | H4T | **None**（字段不存在） | 与父宿主**共用** `useH4DualMode` |
| `xlsx/h4/impairment/h4-tab-recoverable` | H4T | None | 同上 |
| `xlsx/h8/impairment/h8-tab-recoverable` | H8T | None | 🔴 **`useH8DualMode` 的消费方之一**，父宿主内联自己的实现 |
| `xlsx/h8/measurement/h8-tab-measurement-annual` | H8T | None | 对应 H8-6 按年 sheet（61r×17c/263f） |
| **`xlsx/h8/measurement/h8-tab-measurement-monthly`** | H8T | None | 🔴 **slice「第五条待补读」已由 manifest 现算补齐**；对应 H8-6 按月 sheet（361r×16c/**3626f**，是 H8 3710 裸 IF 的主来源） |

🔴 slice 原文：step 9 改线**必须把它们一并改** —— H4 两个子 Tab 与父宿主共用 `useH4DualMode`
（父宿主删 composable 而不改子 Tab 会直接打断子入口）；`H8TabRecoverable` 更极端，
按「删 composable + 改宿主」常规套路走会**完全漏掉它**。

🔴 **`useH4DualMode` 实测生产消费 5 处**：`GtH4EngineeringMaterials.vue` ·
`composables/useH6DualMode.ts` · `composables/useH8DualMode.ts` ·
`h4/impairment/H4TabImpairment.vue` · `h4/impairment/H4TabRecoverable.vue` ⇒
**跨 H4/H6/H8 三条 entry 链式复用**，改它需与 `h2-h6-h10-pilot-cross-reference-lanes` 协调。
`useH8DualMode` 实测生产消费 2 处（`useH9DualMode.ts` + `h8/impairment/H8TabRecoverable.vue`）。

### 主表几何（openpyxl 逐格实测）

| entry | 主表 sheet | 表头 | 数据区 | footer | 有效列/max_col | 公式数 | 裸 IF |
|---|---|---|---|---|---|---|---|
| H4 | `明细表H4-2` | **四级 R8/R9/R10/R11** | R12-27 | R28 🔴 **含派生单价列** | 49/**67** | 635 | 48 |
| H8 | `明细表H8-2` | **四级 R8/R9/R10/R11** | R12-31 | R32 纯 SUM | **58/58（全 H 最宽）** | 685 | **3710（全册）** |

🔴 **H4-2 footer 是 HC-16 第三形态**：合计行含派生单价列
`F=G28/E28` · `I=J28/H28` · `L=M28/K28` · `O=P28/N28`，**不是纯 SUM**；
行内同型 `F=G12/E12` 有**除零风险**（同族先例 F4-7 `G=365/(E/F)`）。

🔴 **H8 公式列 17 个**（如 `K=SUM(D:G)-SUM(H:J)`）。

### 主表键与行身份（实测）

| 键 | 生产命中 | 真库 | 身份字段 | 定位 | 备注 |
|---|---|---|---|---|---|
| `H4-2-rows` | 11 | **零载荷** | `rowId` | `useH4Detail.ts#L249` | BP-6 种子 |
| `H8-2-rows` | 12 | **`[]` 空数组**（2 B） | `rowId` | `useH8Detail.ts#L229` | BP-6 种子 |
| **`H8-2-detail-prefill`** | **1（= 写入点自己）** | **零载荷** | — | `GtH8RightOfUseAssets.vue#L588` | 🔴 **BP-5**：写错键，真实主键是 `H8-2-rows` |

**真库其他实测**：H8 有 **28 个 item_id** 落库（全 H 最多），其中
🔴 `H8-1-rows` **3656 B** 实证 `"rowId":"h81-cost-房屋及建筑物-ya2jc"`
（= HC-7 **族 A 安全形态**，`useH8Adjudication.ts#L145` `h81-${block}-${category}-${rand5}`）；
**H4 真库零载荷**（0 个 item_id）。

### 本 lane 的三条专属缺陷（BP-5 / BP-6 / BP-7）

| BP | 位置 | 形态 | 真库证据 |
|---|---|---|---|
| **BP-5** | `GtH8RightOfUseAssets.vue#L588` | 四表明细种子写进 `H8-2-detail-prefill`，该字面量全仓仅 1 处 = 写入点自己 | 真库零载荷；且**无对应 total 键**（与 H7 的正常情形区分，见 HC-6） |
| **BP-6** | `h4DetailPrefill.ts#L50` `seed-${idx}` · `GtH8RightOfUseAssets.vue#L578` `seed-${idx}` | 种子路径行身份**整体由数组下标构成**且写进 primary managed table | — |
| **BP-7** | `h8DisclosureSyncPayload.ts#L51` `cats.map(c=>({key:c.label,…}))` + `#L110` `row[c.label]=…` | 附注同步把**稳定动态列 key 降级成可变 label** | 🔴 是 **H 循环内部唯一背离 H7 动态列范式（SK-1）的地方** |

🔴 BP-6 的第三处 `GtH2ConstructionInProgress.vue#L616` `` rowId:`seed-${i}` `` 在 H2 ⇒
归 `h2-h6-h10-pilot-cross-reference-lanes`。

---

## Requirements

### Requirement 1: 引用而不复述 foundation 的 HC-1 ~ HC-16

#### Acceptance Criteria

1. WHEN 本 spec 需要任一 HC-x 裁决 THEN SHALL 只写引用 + 本 lane 实例化参数，**不得**复述正文。
2. WHEN foundation 的某条 HC-x 尚未交付 THEN 依赖它的本 lane 任务 SHALL 阻塞，不得自行裁决绕过。
3. WHEN 跨 spec 复盘 THEN 发现复述 HC 正文 SHALL 判为缺陷。

### Requirement 2: 5 条子入口的改线一并处置（本 spec 的头号风险）

**User Story:** 作为实施者，我不要按「删 composable + 改宿主」的常规套路走，
那会打断 H4 两个子 Tab、并完全漏掉 `H8TabRecoverable`。

#### Acceptance Criteria

1. 🔴 WHEN 本 lane 任一改线触及 `useH4DualMode` THEN SHALL **同时改 5 个消费点**：
   `GtH4EngineeringMaterials.vue` · `composables/useH6DualMode.ts` · `composables/useH8DualMode.ts` ·
   `h4/impairment/H4TabImpairment.vue` · `h4/impairment/H4TabRecoverable.vue`；
   判据 SHALL 现算消费点个数并断言 == 5，漏任一点 SHALL 打红。
2. 🔴 WHEN 改动跨到 `useH6DualMode.ts` / `useH9DualMode.ts` THEN SHALL 与
   `h2-h6-h10-pilot-cross-reference-lanes` 协调（`useH4DualMode` → `useH6DualMode` → `useH8DualMode`
   → `useH9DualMode` 是一条链式复用链），**不得**单方面改。
3. 🔴 WHEN 处置 `xlsx/h8/impairment/h8-tab-recoverable` THEN SHALL 显式登记它是
   `useH8DualMode` 的消费方、而父宿主 `GtH8RightOfUseAssets.vue` **内联自己的实现** ⇒
   按常规套路走会**完全漏掉它**；判据 SHALL 断言该子入口的双向链路独立可验。
4. WHEN 声明 5 条子入口 THEN SHALL 用 manifest 现算的**完整 entry_id 全名**
   （entry_id 是持久化键，表格不得缩写）；SHALL 包含补齐的
   `xlsx/h8/measurement/h8-tab-measurement-monthly`。
5. WHEN 登记子入口 manifest 字段 THEN SHALL 按实测：`capability=single_onlyoffice` /
   `relationship` 字段**不存在（返 None）** ⇒ slice 记的 `parent_duplicate` 是 slice 语义注记而非 manifest 值。
6. WHEN 为子入口写 representation THEN SHALL 按 **GC-1** 用 `entry_id` 作 pointer，
   **不得**用 wp_code —— 5 条子入口共用父级 wp_code_pattern（`H4T` / `H8T`），按 wp_code 必撞。

### Requirement 3: BP-5 修复（H8 写进零消费方 item_id）

**User Story:** 作为维护者，我要 H8 的四表明细种子写进真实主键，
而不是写进一个全仓只有写入点自己、真库零载荷的键。

#### Acceptance Criteria

1. 🔴 WHEN 修 BP-5 THEN SHALL 把 `GtH8RightOfUseAssets.vue#L588` 的写入目标从
   `H8-2-detail-prefill` 改为真实主键 **`H8-2-rows`**；
   判据 SHALL 断言 `H8-2-detail-prefill` 字面量修后全仓命中 **0**。
2. WHEN 判定 BP-5 是缺陷而 H7 的同形（`H7-2-cost-rows` 命中 1）不是 THEN SHALL 按 HC-6 判据区分：
   BP-5 **无对应 total 键 + 真库零载荷**；H7 **有对应 `H7-2-cost-total`** 且勾稽走它。
   🔴 判据混用会把 H7 误判成缺陷。
3. WHEN 改写入目标 THEN SHALL 同时处置 BP-6（同一段种子代码 `#L578` 用 `seed-${idx}`）——
   两者在同一路径上，分两次改会留中间态。
4. WHEN 修复后 THEN SHALL 断言真库能落到 `H8-2-rows`（当前实测是 `[]` 空数组，
   说明键对但种子没进去）。

### Requirement 4: BP-6 修复（种子行身份取数组下标）

#### Acceptance Criteria

1. 🔴 WHEN 修 BP-6 THEN 本 lane SHALL 覆盖 **2 处**（第三处在 H2，归 lane 3）：
   `h4DetailPrefill.ts#L50` `seed-${idx}` · `GtH8RightOfUseAssets.vue#L578` `seed-${idx}`。
2. WHEN 替换身份生成 THEN SHALL 对齐 HC-7 **族 A** 形态，参照同仓已有的安全实现
   `useH8Adjudication.ts#L145` `h81-${block}-${category}-${Math.random().toString(36).slice(2,7)}`
   （真库实证 `h81-cost-房屋及建筑物-ya2jc`）。
3. 🔴 WHEN 替换后 THEN SHALL 带**旧身份迁移映射**：真库 `H8-2-rows` 当前是 `[]`、`H4-2-rows` 无行 ⇒
   本 lane 的 BP-6 迁移风险**低**（无既有 `seed-*` 数据），判据 SHALL 现算确认这一点后才可省略映射；
   若现算发现有 `seed-` 前缀落库 THEN 迁移映射 SHALL 变为必需。
4. WHEN 断言修复 THEN 全 H 源码 `` rowId:`seed-${ `` 形态命中 SHALL 降为 **1**（剩 H2 那处），
   修完 lane 3 后降为 **0**。
5. WHEN 登记 prefill 归属 THEN SHALL 按 HC/Req：**后端 prefill 零参与**
   （`prefill_formula_mapping.json` 的 306 条 mappings 里 H 命中 24 条但 `sheet` 全为 None；
   `prefill_anchor_map.py` / `prefill_engine.py` H 字面量 0）⇒ 修复**只在前端**，
   判据 SHALL 断言后端 prefill 侧无需同步改动。

### Requirement 5: BP-7 修复（H 循环唯一背离 H7 动态列范式的地方）

**User Story:** 作为维护者，我要 H8 的附注同步别把 H7 已经踩过坑换来的稳定 key 又降级回 label。

#### Acceptance Criteria

1. 🔴 WHEN 修 BP-7 THEN SHALL 改 **2 处**：`h8DisclosureSyncPayload.ts#L51`
   `cats.map(c => ({ key: c.label, … }))` 与 `#L110` `row[c.label] = …`，
   改为用稳定 key（`{prefix}{seq}` 形态），label 只作展示。
2. WHEN 断言修复 THEN SHALL 满足 `h3-h5-h7-variant-axis-and-dynamic-column-paradigm` 的
   **SK-1 判据**（key 由稳定前缀+序号构成、label 独立可改）；
   🔴 修复后全 H「背离该范式的地方」SHALL 降为 **0 处**。
3. WHEN 登记该缺陷性质 THEN SHALL 写明它是 H 循环内部**唯一**背离点，
   且 H7 的范式正是为「四个产业默认叶子列名同为 `类别`」而创（label 作 key 必四列撞一列）。
4. WHEN 修复涉及既有落库数据 THEN SHALL 现算 H8 附注相关键
   （实测 `H8-listed-categories` 137 B · `H8-listed-movement` `[]`）并评估 label→key 迁移映射需求。

### Requirement 6: H4 footer 第三形态（派生单价列 + 除零）

#### Acceptance Criteria

1. 🔴 WHEN 声明 H4-2 footer THEN SHALL 按 HC-16 **第三形态**：R28 含派生单价列
   `F=G28/E28` · `I=J28/H28` · `L=M28/K28` · `O=P28/N28`，**不是纯 SUM**；
   契约 SHALL 把这 4 列声明为 `derived`。
2. 🔴 WHEN 声明行内同型公式 THEN SHALL 覆盖 `F=G12/E12` 族并带**除零守卫**：
   分母为 0 时结果应为空/0，**不得**产出 `#DIV/0!`（同族先例 F4-7 `G=365/(E/F)`）。
3. WHEN 守卫比对 footer THEN SHALL 断言 `footer_kind == "derived_unit_price"`（非 `pure_sum`）；
   变异「按纯 SUM 校验 H4 footer」SHALL 打红。
4. WHEN 声明 H4-2 列边界 THEN SHALL 按实测**有效列 49 / `max_column` 67**（两者不等）⇒
   UUID 列放 **50**（有效列+1，HC-13），**不得**放 68。

### Requirement 7: H8 模板侧重负载（3710 裸 IF + 最宽主表）

#### Acceptance Criteria

1. 🔴 WHEN 挂中性化 THEN SHALL **per-file**（HC-12）：H8 实测 **3710**（全平台最多），
   主来源是 `使用权资产 租赁负债初始及后续计量（按月）H8-6`（361r×16c / **3626 公式**）；
   H4 实测 **48**。变异「整册统一挂」SHALL 打红（3710 与 48 差 77 倍）。
2. WHEN 处理 H8-6 双 sheet THEN SHALL 按 HC-5 用 `period_granularity` 轴或 sheet 全名：
   `（按年）`（61r×17c/263f）/ `（按月）`（361r×16c/3626f）；
   🔴 这两张分别对应两条子入口（`h8-tab-measurement-annual` / `-monthly`）。
3. 🔴 WHEN 触及 H8-6 THEN SHALL 登记 HC-15 风险 ③：`wp_index` 记 H8-6 为「使用权资产调整分录」，
   模板实测是「使用权资产 租赁负债初始及后续计量（按年/按月）」⇒ 契约 SHALL 用模板 sheet 全名消歧，
   并登记该冲突待平台侧修正（本 spec **不修** wp_index）。
4. WHEN 声明 H8 宽表 THEN SHALL 按有效内容列扫描（HC-13）：H8 国企侧 `255c/有效6`
   （上市侧仅 7c，不在宽表之列）；H4 两张 `254c/6` + `254c/8`。
5. WHEN 声明 H8-2 列边界 THEN SHALL 按实测 **58/58**（全 H 最宽主表，17 个公式列）⇒ UUID 列放 59。

### Requirement 8: TB 发布门缺口与载体接线（HC-2 实例化）

#### Acceptance Criteria

1. 🔴 WHEN 声明 H8 的 TB 发布门 THEN SHALL 断言**无**（实测 `publishToTb` 在 H8 全链路 0 处）——
   与 H9 同，是 HD-7 的两条缺口；契约 `tb_publish_gate: null`。
2. WHEN 补 H8 发布门 THEN SHALL **不在本 spec 内做**（发布链首例归
   `h2-h6-h10-pilot-cross-reference-lanes`），本 spec 只登记缺口。
3. WHEN 接 H4 THEN SHALL 按 `formdata_composable` 族；TB 门在
   `useH4Adjudication.ts` + `H4TabAdjudication.vue`（`publishToTb` 各 2 处）。
4. WHEN 接 H8 THEN SHALL 按 `host_inline` 族（宿主自己 `import http from '@/utils/http'` + PUT，
   `checklist_put`=1）+ 读路径 `render-config?force_component_type`（宿主命中 1 处）。
5. WHEN 处置本 lane legacy 载体 THEN SHALL 按 HC-3 实测：**删 `useH8FormData`**（生产消费 0）；
   🔴 `useH8DualMode` **不可删**（生产消费 2）· `useH4DualMode` **不可删**（生产消费 5）。
6. WHEN 守卫校验接线 THEN SHALL 断言宿主/Tab 侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）。

### Requirement 9: 族 C 语义耦合身份与派生合计

#### Acceptance Criteria

1. WHEN 修本 lane 族 C（HC-7）THEN SHALL 覆盖 **2 处**：
   `useH4Adjudication.ts#L436` `net-${name}` · `useH8Adjudication.ts#L572` `h81-net-${cat}`；
   🔴 `useH8Adjudication.ts#L145` **属族 A 不得改**（有 `${rand5}` 后缀，真库实证安全）。
2. WHEN 声明 `derived_total_keys`（HC-6）THEN SHALL 现算（当前现算值）：
   🔴 **H8 21 个（全 H 最多）**（`H8-1-cost-audited-total` / `H8-1-cost-begin-total` /
   `H8-1-cost-credit-total` / `H8-1-cost-debit-total` / `H8-1-dep-audited-total` /
   `H8-1-dep-begin-total` / `H8-1-dep-credit-total` / `H8-1-dep-debit-total` /
   `H8-1-impair-audited-total` / `H8-1-net-audited-total` / `H8-10-supplement-total` /
   `H8-8-depreciation-total` …）· **H4 15 个**（`H4-1-adjudicated-total` / `H4-1-begin-total` /
   `H4-1-credit-total` / `H4-1-debit-total` / `H4-1-end-total` / `H4-2-decrease-total` /
   `H4-2-detail-total` / `H4-2-impair-total` / `H4-2-increase-total` / `H4-4-addition-total` /
   `H4-5-disposal-total` / `H4-8-total-recoverable` / `H4-6B-summary` / `H4-8-dcf-assumptions` /
   `H4-soe-summary`）。🔴 判据与现算基线比对，**不得写死个数**。
3. WHEN 声明 H8 常量/派生字段（HC-11）THEN SHALL 覆盖真库实证 `H8-1-rows` 载荷字段
   （`rowId` / `category` / `name` / `block` / `beginUnadjusted` / `beginAdjustment` /
   `endUnadjusted` / `endAdjustment` / `beginBalance` / `unadjusted` / `aje` / `rje` /
   `debitAmount` / `creditAmount`），其中 `block` 是分组键（`cost` / `dep` / `impair` …）。

### Requirement 10: 跨 entry 引用与键冻结

#### Acceptance Criteria

1. WHEN 触及 `H9-2-rows` THEN SHALL 登记 H8 侧消费方 `useH8CrossSheet.ts` / `useH8DisposalCheck.ts`
   ⇒ 该键**冻结**（改它会打断 H8），与 foundation §HC-8 同源。
2. WHEN 本 lane 键改动 THEN SHALL 现算跨引用图确认 `H4-2-rows` / `H8-2-rows` **未被 H1 pilot 消费**
   （实测 H1 只消费 H2/H6/H10 的键）⇒ 这两个键**不在冻结名单**，可改但须带迁移映射。
3. WHEN 声明零回归基线 THEN SHALL **现算**（GC-10），不得写死契约数或注册集。

---

## 阻塞项

- **BP-1 ~ BP-4**：平台级供给，相关任务标 `[ ]*`
- **BP-5 / BP-6（2 处）/ BP-7**：本 spec 修（Req 3 / 4 / 5）
- **BP-8**：本 lane 成员按 HC-3 重算 = 删 `useH8FormData`；
  🔴 `useH8DualMode`（消费 2）与 `useH4DualMode`（消费 5）**不可删**
- **BP-11**（新）：本 lane 族 C 2 处（Req 9.1）
- 🔴 **无 canary**：H4 真库零载荷、H8 主表键是 `[]` ⇒ canary 由 foundation 的 H9 承担
- 🔴 **H8 TB 发布门缺口**：本 spec 只登记，补门归 lane 3
