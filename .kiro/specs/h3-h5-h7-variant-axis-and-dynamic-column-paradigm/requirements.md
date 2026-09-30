# Requirements Document

## Introduction

本 spec 是 H 循环三份 lane spec 之一，覆盖 **H3 投资性房地产 / H5 油气资产 / H7 生产性生物资产** 三条 entry。

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（承载 **HC-1 ~ HC-16**）。
🔴 **本 spec 只引用 HC-x，不复述其正文**（复述即漂移，跨 spec 复盘会判缺陷）。

**聚类依据**（为什么这三条在一起）：**三条都有同尾码双 sheet 变体轴**（HC-5），
且 **H7 是全平台动态列范式（SK-1~SK-4）的源头**，H3/H5 的披露宽表都在该范式作业面上。
三条的**载体族各不相同**（HC-2），本 spec 如实登记差异、**不强行统一**。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`HV-P{N}`**（H Variant）。

### 三条 entry 实测底账

| entry_id | 宿主 | 幻影码 | 模板 sha256 前 16 / 字节 | 写族 | 读族 | TB 门位置 |
|---|---|---|---|---|---|---|
| `xlsx/gt-h3-investment-property` | `GtH3InvestmentProperty.vue` | H3I | `6526c9fc186230fa` / 146,096 | `formdata_composable`（`useH3FormData`，生产消费 37 处） | `GET /checklist-responses` | `H3TabAdjudicationCost.vue` |
| `xlsx/gt-h5-oil-gas-assets` | `GtH5OilGasAssets.vue` | H5O | `6dcc109bee631035` / 195,306 | `per_tab_formdata_instance`（每子 Tab 各实例化 `useH5FormData`） | `GET /checklist-responses` | **`useH5FormData.ts`** |
| `xlsx/gt-h7-biological-assets` | `GtH7BiologicalAssets.vue` | H7B | `df55f0051d9b3a67` / 225,641 | `per_tab_self_persisting`（`H7TabDetailCost.vue` 内联 `api`） | `GET /checklist-responses` | 🔴 **`useH7FormData.ts`** |

三条共同：`capability=single_onlyoffice` / 无 `capability_target` 字段 / `adapter_id=None` /
`mounts=2` / 0 契约 / 0 representation / 宿主 `bridge=0` `legacyOO=4` `notice=3` `ocr=0` /
`useAdjustmentCentralSync` 在各自 `H*TabAdjustment.vue` 命中 3 处。

### 主表几何（openpyxl 逐格实测）

| entry | 主表 sheet | 表头 | 数据区 | footer | 有效列/max_col | 公式数 | 裸 IF |
|---|---|---|---|---|---|---|---|
| H3 | `明细表（成本模式）H3-2` | 三级 R9/R10/R11 | R13-27 | R28 `SUM(C13:C27)` | 45/49 | 458 | 661 |
| H3 | `明细表（公允价值模式）H3-2` | — | — | — | 53r×31c | 270 | （同册计入） |
| H5 | `明细表H5-2` | **四级 R9/R10/R11/R12** | R13-32 | R33 合计 | 54/54 | 668 | 816 |
| H7 | `明细表（成本模式）H7-2` | **四级 R9/R10/R11/R12** | R13-36 | R37 合计 | 51/51 | **745（全 H 最大明细表）** | 1025 |
| H7 | `明细表（公允价值模式）H7-2` | — | — | — | 57r×47c | 416 | （同册计入） |

### 主表键与行身份（实测）

| 键 | 生产命中 | 身份字段 | 定位 | 备注 |
|---|---|---|---|---|
| `H3-2-cost-rows` | 8 | `rowId` | `useH3DetailCost.ts#L141` | — |
| `H3-2-fair-rows` | 9 | `rowId` | `useH3DetailFair.ts` | 🔴 **被 G 循环消费**（HC-8 冻结） |
| `H5-2-rows` | **0（字面量零命中）** | `rowId` | `useH5Detail.ts` 用 `${ITEM_PREFIX}-rows`，`#L53 ITEM_PREFIX='H5-2'` | HC-4 |
| `H7-2-cost-rows` | 1（写入点自己） | `rowId` | `h7/core/H7TabDetailCost.vue#L215` 内联 | HC-6 判**正常** |
| `H7-2-fair-rows` | 1（写入点自己） | `rowId` | `h7/core/H7TabDetailFair.vue` 内联 | 同上 |

### 变体轴实测（HC-5 的本 lane 实例）

| entry | 轴 | 双 sheet 实测全名 |
|---|---|---|
| H3 | `measurement_model` | `审定表（成本模式）H3-1` / `审定表（公允价值模式）H3-1` · `明细表（成本模式）H3-2` / `明细表（公允价值模式）H3-2` · `增减检查表`×2 |
| H3 | `impairment_included` | H3-7 `折旧测算表（成本模式不含减值）` / `（成本模式含减值）` |
| H5 | `impairment_included` | H5-12 `折耗测算表（不含减值）` / `（含减值）` |
| H7 | `measurement_model` | `审定表`×2 · `明细表（成本模式）H7-2` / `明细表（公允价值模式）H7-2` · `增加检查表`×2 · `减少检查表`×2 |
| H7 | `impairment_included` | H7-11 `折旧测算表（不含减值）-直线法` / `（含减值）` |

🔴 **H3 与 H7 的两套计量模式各有独立键**（`H3-2-cost-rows` / `H3-2-fair-rows`），
与 E1-3 `currency_variant`「两张同尾码 sheet 共用一个键」**不同源** ⇒ 不继承抹零风险，
但继承「按尾码定位会二选一错」的风险。

### 真库现状（HC-6 / canary 依据的对照）

现算 `checklist_responses`（载荷列 `remark`）：
- **三条主表键全部零载荷**（`H3-2-cost-rows` / `H3-2-fair-rows` / `H5-2-rows` / `H7-2-cost-rows` 均无行）
- H3 有 5 个 item_id 落库（全是附注披露：`H3-disc-listed-rows-cost-original` 204 B ·
  `H3-disc-soe-rows-soe-cost` 256 B · `-soe-cost-dep` 199 B · `-soe-impair` 201 B · `-soe-unlicensed` 201 B）
- H5 有 7 个 item_id 落库，其中 🔴 **`H5-1-cost-rows` 1059 B 实证 `"rowId":"row-c-油井资产"`**
  + `"isSubtotal":false,"isEditable":true`；`H5-1-depletion-rows` 1059 B 同形（`row-d-油井资产`）
- **H7 真库零载荷**（0 个 item_id）

⇒ 本 lane **三条都不具备 canary 资格**（HC-6 / foundation §canary 选型已裁决 canary = H9）。

---

## Requirements

### Requirement 1: 引用而不复述 foundation 的 HC-1 ~ HC-16

#### Acceptance Criteria

1. WHEN 本 spec 需要任一 HC-x 裁决 THEN SHALL 只写「见 `h-cycle-sync-foundation-and-first-canary/design.md` §HC-x」
   + 本 lane 的实例化参数，**不得**复述裁决正文。
2. WHEN 跨 spec 复盘 THEN 发现本 spec 复述 HC 正文 SHALL 判为缺陷。
3. WHEN foundation 的某条 HC-x 尚未交付 THEN 依赖它的本 lane 任务 SHALL 阻塞，**不得**自行裁决绕过。

### Requirement 2: 变体轴三维声明的三条实例化（HC-5）

**User Story:** 作为实施者，我要三条 entry 的每一对同尾码 sheet 都有唯一可寻址的契约坐标，
不要按 `sheet_code` 定位时二选一错。

#### Acceptance Criteria

1. WHEN 为 H3 / H5 / H7 写契约 THEN SHALL 用 `(variant_axis, variant_value, sheet_code)` 三维
   **或**逐 sheet 全名声明；判据 SHALL 覆盖上表 5 组轴 × 全部双 sheet。
2. 🔴 WHEN 契约只声明 `(measurement_model, sheet_code)` 两维 THEN SHALL 打红并指出
   H3-7 / H5-12 / H7-11 的 `impairment_included` 轴无处安放。
3. WHEN 按 `sheet_code` 定位 THEN 守卫 SHALL 断言命中 **2 张** sheet 并要求补 `variant_value` 消歧，
   **不得**静默取第一张。
4. WHEN 声明 H3 / H7 的双计量键 THEN SHALL 断言两套**各有独立键**（`*-cost-rows` / `*-fair-rows`），
   并登记与 E1-3 `currency_variant` 的差异。
5. WHEN H5 声明变体 THEN SHALL 只在 H5-12 折耗测算表上声明 `impairment_included`；
   H5 主表 `H5-2` **无变体轴**（实测单张）。

### Requirement 3: H7 动态列范式 SK-1 ~ SK-4 的守卫落地

**User Story:** 作为维护者，我要 H7 这套已被 5 个模块逐字引用的范式有可执行判据，
而不是只存在于注释里。

#### Acceptance Criteria

1. WHEN 登记范式来源 THEN SHALL 写明：源模板 `H7 生产性生物资产.xlsx!附注披露信息（上市公司）`
   两级表头下**四个产业的默认叶子列名都是同一个字面 `类别`**（`H7_DEFAULT_CATEGORY_LABEL`）⇒
   用 label 作 key 必然四列撞成一列；H7 改用 `{industryKey}_{seq}`。
   下游逐字引用「H7 已踩」的 5 处：`g7SlotColumns.ts` · `d4DisclosureModel.ts` ·
   `i1SoeDisclosureModel.ts` · `e1CurrencyScope.ts` · `e1RestrictedScope.ts`。
2. **SK-1**（key 由稳定前缀+序号构成、label 独立可改）：判据 SHALL 断言
   `h7ListedDisclosureModel.ts#L50-57` interface 三字段分离 +
   `createDefaultH7Categories()#L60` 用 `${ind.key}_1`。
3. **SK-2**（新序号取 `max+1`，**不复用已删序号**）：判据 SHALL 断言
   `nextH7CategoryKey#L74-86` 出现 `${prefix}${max+1}`，且
   🔴 **全 H 源码不得出现 `length+1` / `${i}` / `${idx}` 作为动态列序号**（会让历史金额串到新列）；
   国企侧同形 `h7SoeDisclosureModel.ts#L104-115` 一并断言。
4. **SK-3**（合计列对动态数组 `reduce`）：判据 SHALL 断言 `h7TotalCellValue#L295` 用 `reduce`，
   且全 H 源码**不得出现** `公司1..公司N` 横向展开字面量（实测 0 处，守卫方向是保持为 0）。
5. **SK-4**（动态区骨架行数不写死）：判据 SHALL 断言 `H7_COST_MOVEMENT_ROWS` 34 行 /
   `H7_FAIR_MOVEMENT_ROWS` 11 行逐行对应源模板 R11-44 / R53-64，且
   **不得出现** `blankRows(x, <整数>)`（实测 0 处）。
6. 🔴 WHEN 扫描全 H 是否有背离该范式的地方 THEN SHALL 断言**唯一背离点是 BP-7**
   （H8 `h8DisclosureSyncPayload.ts`），它归 `h4-h8-sub-entry-lanes-and-seed-identity-defects`；
   本 lane 内 SHALL 命中 **0 处**背离。

### Requirement 4: 三条载体族各异的接线（HC-2 实例化）

**User Story:** 作为实施者，我要按实测族接线，不要把 H5 的多实例 composable 当成单实例、
不要把 H7 的 Tab 内联当成 composable 持久化。

#### Acceptance Criteria

1. WHEN 接 H3 THEN SHALL 按 `formdata_composable` 族：载体 `useH3FormData`（实测生产消费 **37 处**，
   是全 H 最活跃的 FormData composable）；读路径 `GET /checklist-responses`。
2. 🔴 WHEN 接 H5 THEN SHALL 按 `per_tab_formdata_instance` 族：**每个子 Tab 各实例化一份**
   `useH5FormData` ⇒ 接线点是 **N 个**而非 1 个；判据 SHALL 现算实例化点个数并逐点断言。
3. 🔴 WHEN 接 H7 THEN SHALL 按 `per_tab_self_persisting` 族：持久化在 `H7TabDetailCost.vue` 内联 `api`，
   主表键也内联在该 Tab（`#L215`）；`useH7DetailCost.ts` 是 **26 行取值 stub**，
   **不是**持久化载体 ⇒ 接到它上面是假绿。
4. WHEN 处置本 lane 的 legacy 载体 THEN SHALL 按 HC-3 实测名单：
   可删 `useH5DualMode`（生产消费 0）· `useH7DualMode`（0）；
   🔴 **禁删 `useH7FormData`** —— 实测生产消费 1（`h7/core/H7TabAdjudicationCost.vue`）
   且**承载 H7 唯一 TB 发布门**（`publishToTb` 命中 2 处）。
5. WHEN 删除 `useH5DualMode` THEN SHALL 同时处置 HC-10 的第四存储风险：
   该文件有 `STORAGE_PREFIX = 'h5-dual-mode:'`，删除是最干净的处置；
   若改为接线激活它 THEN SHALL 显式说明 localStorage 与 `checklist_responses` 的一致性方案。
6. WHEN 为三条 entry 声明 TB 发布门 THEN SHALL 按实测位置：
   H3 → `H3TabAdjudicationCost.vue` · H5 → `useH5FormData.ts` · H7 → `useH7FormData.ts`；
   🔴 **三条都有发布门**（与 H8/H9 不同）。

### Requirement 5: 主表键与行身份的本 lane 处置

#### Acceptance Criteria

1. 🔴 WHEN 守卫比对 `H5-2-rows` THEN SHALL 用 HC-4 拼接解析分支；字面量 grep **必假红**。
   判据 SHALL 落表 H5 的 16 个 PREFIX 常量实值（`H5-1`..`H5-19`，见 foundation §HC-4）。
2. WHEN 处置 `H7-2-cost-rows` / `H7-2-fair-rows` 生产命中 1 THEN SHALL 按 HC-6 判**正常非缺陷**：
   H7 审定表勾稽走 `useH7CrossSheet.ts#L52 getNum('H7-2-cost-total')`（`#L49` 注释
   「H7-1 审定表原值合计 vs H7-2 明细表期末合计」），不遍历明细行。
3. 🔴 WHEN 触及 `H3-2-fair-rows` THEN SHALL **冻结键名不改**（HC-8）——
   被 G 循环 `g13SourceDetailPull.ts` / `gCycleSourceFv.ts` 消费。
4. WHEN 修本 lane 的族 C 语义耦合身份（HC-7）THEN SHALL 覆盖 **3 处**
   （全 H 共 7 处 = 本 lane 3 + lane 2 的 2 + lane 3 的 2）：
   `useH3Adjustment.ts#L311` `${kind}-${cat}` · `useH3RentalIncome.ts#L148` `subtotal-${cat}` ·
   `useH5Adjudication.ts#L136` `row-${prefix}-${cat}`（🔴 真库已落库 `row-c-油井资产`）
   —— 并 SHALL 带旧身份迁移映射，否则既有行全部变「新行」、历史金额串位。
5. WHEN 处置 H5 小计行 THEN SHALL 按 foundation §实测不一致第 5 条：**小计行不落库**
   （`useH5Adjudication.ts#L309-311` 保存前 `.filter(r=>!r.isSubtotal)`；
   `useH5Detail.ts#L138 subtotalRow` 是 computed）⇒ 契约无需排除；
   `isSubtotal` 字段落库**恒 false**、`isEditable` 恒 true，SHALL 按 HC-11 声明为常量/派生。
6. WHEN 声明 `derived_total_keys`（HC-6）THEN SHALL 现算本 lane 三条的 total 键（当前现算值）：
   **H3 14 个**（`H3-1-cost-increase-total` / `H3-2-cost-begin-total` / `H3-10-supplement-total` …）·
   **H5 5 个**（`H5-1-cost-total` / `H5-2-cost-total` / `H5-12-depletion-total` / `H5-7-addition-total` /
   `H5-8-disposal-total`）· **H7 6 个**（`H7-1-cost-total` / `H7-2-cost-total` / `H7-11-dep-total` /
   `H7-12-total` / `H7-14-transfer-in-total` / `H7-14-transfer-out-total`）。
   🔴 判据与现算基线比对，**不得写死个数**。

### Requirement 6: 模板侧 instrumentation（HC-12 / HC-13 实例化）

#### Acceptance Criteria

1. WHEN 挂中性化 THEN SHALL per-file（HC-12），本 lane 实测裸 IF：H7 **1025** · H5 **816** · H3 **661**。
2. WHEN 扫描披露宽表列 THEN SHALL 按有效内容列（HC-13），本 lane 实测 6 张：
   H3 `250c/有效6` + `252c/9` · H5 `257c/8` + `253c/6` · H7 `257c/11` + `256c/6`。
3. WHEN 放 UUID 列 THEN SHALL 放「有效内容列 +1」，同源引用 G 的规则。
4. WHEN 断言干净点（HC-14）THEN 本 lane 三册 SHALL 全部命中：definedName 0 · 漏加小计 0 · 越界引用 0 ·
   无 Excel Table · **无 `GT_Custom` hidden sheet**（该 sheet 只在 H9/H10 两册）。
5. WHEN 声明 footer 形态（HC-16）THEN 本 lane 三条 SHALL 全部是**纯 SUM**
   （H3 R28 `SUM(C13:C27)` · H5 R33 · H7 R37）⇒ 不触发第三形态与全角空格特例。

---

## 阻塞项

- **BP-1 ~ BP-4**：平台级供给（全循环共有），相关任务标 `[ ]*`
- **BP-8**：本 lane 成员按 HC-3 实测重算 = 可删 `useH5DualMode` / `useH7DualMode`，
  🔴 **`useH7FormData` 移出删除清册**（slice 名单错）
- **BP-11**（新）：本 lane 族 C **3 处**（全 H 7 处中的 3 处），见 Requirement 5.4
- 🔴 **无 canary**：本 lane 三条真库主表键全部零载荷，canary 由 foundation 的 H9 承担
