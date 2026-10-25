# Requirements Document

## Introduction

本 spec 把 **D5 应收款项融资 / D6 合同资产 / D7 合同负债** 三个循环的受管覆盖从各 1 张明细扩到
**合计 20 个受管区**，并对三张调整分录汇总表（D5-3 / D6-4 / D7-3）只做可行性核。

**三家合一个 spec 是用户 2026-09-25 的裁决（B 方案）**，依据是实测的高度同型：同一套 33 个函数
provider（`phase5_d5_receivables_financing` 781 行 / `phase5_d6_contract_assets` 849 行 /
`phase5_d7_contract_liabilities` 844 行，函数名逐字相同）、账龄形态只差一个参数
（**nested**=D7 / **flat**=D6 / **无**=D5）、各自只接了 1 张明细（`d52`/`d62`/`d72-managed`）。
分三份写会有八成样板重复。

它**消费**两个上游，**不重造**引擎件、**不另起**平行裁决：
- `d1-sync-row-table-engine-and-d1-coverage` —— 框架层行表引擎 + `AdjudicationSheetSpec`
- **`d-cycle-sheet-bidirectional-expansion`（9/9 全绿）** —— 其分波表 **Wave 5 = D5-3/D6-3/D7-3**
  正是本 spec 的作业面；四条纪律全部继承（一 entry 一 adapter · 诚实边界 · 可行性核硬门
  「有行身份列 + 无专用同步链冲突」· D4-4 已判 `single_html` 的判据）

### 三册模板实测（openpyxl 直读，全部单册）

| 循环 | 模板 | sheets | entry / 已接受管 sheet | 账龄形态 |
|---|---|---|---|---|
| D5 | `D5 应收款项融资.xlsx` | 8 | `xlsx/gt-d5-receivables-financing` / `d52-managed` | 无（FVOCI） |
| D6 | `D6 合同资产.xlsx` | 15 | `xlsx/gt-d6-contract-assets` / `d62-managed` | **flat** |
| D7 | `D7 合同负债.xlsx` | 13 | `xlsx/gt-d7-contract-liabilities` / `d72-managed` | **nested** |

三家均**单册**（与 D1/D3 同，不同于 D2 的三册）⇒ 不受 `entry ↔ template blob` 1:1 的范围约束。

### D5 各 sheet 几何与 store 键

| sheet | rows | cols | 公式 | store 键（按值 grep 实测） | 受管区 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | 19 | 8 | 0 | — | — | 不接 |
| 应收款项融资审计程序表D5A | 23 | 10 | 6 | — | — | 不接 |
| **审定表D5**（🔴 无 `-1` 后缀） | 18 | 12 | **52** | 待实测 | 待实测 | ✅ 逐格 |
| 附注披露信息（上市公司） | 43 | 7 | 21 | `D5-note-listed-impairment-rows` | — | 不接 |
| 附注披露信息（国企） | 18 | 7 | 8 | — | — | 不接 |
| **应收款项融资明细表D5-2** | 26 | 17 | 40 | `D5-2-rows` | 1 | 已接 |
| **调整分录汇总表D5-3** | 29 | 10 | 6 | `D5-3-rows` | 🔍 核 | 可行性核 |
| **应收款项融资公允价值测算表D5-4** | 26 | 13 | 18 | `D5-4-rows` | 1 | ✅ |

🔴 **`审定表D5` 的 sheet 名没有 `-1` 后缀**，与 D1-1 / D2-1 / D3-1 / D6-1 / D7-1 的命名惯例不同。
声明时必须用实测名，按 `审定表D5-1` 推演会 sheet 找不到。

### D6 各 sheet 几何与 store 键

| sheet | rows | cols | 公式 | store 键（实测） | 受管区 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | 22 | 8 | 0 | — | — | 不接 |
| 合同资产实质性程序表 D6A | 33 | 10 | 7 | — | — | 不接 |
| 🔴 `合同资产实质性程序表 D7A（原）` | 104 | 13 | 0 | — | — | **历史残留**，不接 |
| **审定表D6-1** | 43 | 13 | **177** | 待实测 | 待实测 | ✅ 逐格（密度 32%） |
| 附注披露信息(上市公司） | 89 | 11 | 163 | `D6-note-listed-s2-prior-rows` / `-s3-prior-rows` | — | 不接 |
| 附注披露信息（国企） | 37 | 10 | 50 | — | — | 不接 |
| **明细表D6-2** | 38 | 32 | 69 | `D6-2-rows` | 1 | 已接 |
| **合同资产减值准备明细表D6-3** | 29 | 14 | 63 | `D6-3-rows` | 1 | ✅ |
| **调整分录汇总表D6-4** | 25 | 10 | 7 | `D6-4-rows` | 🔍 核 | 可行性核 |
| **关联关系及交易检查D6-5** | 30 | 14 | 19 | `D6-5-rows` | 1 | ✅ |
| **合同资产检查表D6-6** | 53 | 17 | 19 | `D6-6-block1-rows` / `D6-6-block2-rows` | **2** | ✅ |
| 合同资产减值准备会计政策检查D6-7 | 58 | 18 | 7 | 待实测 | 待核 | 🔍 形态核 |
| **减值准备测算D6-8** | 48 | 15 | 58 | `D6-8-single-rows` | 1 | ✅ |
| **减值准备转回、核销检查表D6-9** | 30 | 8 | 10 | `D6-9-reversal-rows` / `D6-9-writeoff-rows` | **2** | ✅ |
| GT_Custom | 8 | 2 | 0 | — | — | 不接 |

### D7 各 sheet 几何与 store 键

| sheet | rows | cols | 公式 | store 键（实测） | 受管区 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | 20 | 8 | 0 | — | — | 不接 |
| 合同负债实质性程序表 D7A | 29 | 10 | 6 | — | — | 不接 |
| 🔴 `合同负债实质性程序表 D8A（原）` | 66 | 12 | 0 | — | — | **历史残留**，不接 |
| **审定表D7-1** | 32 | 12 | **84** | 待实测 | 待实测 | ✅ 逐格 |
| 附注披露信息(上市公司) | 37 | 5 | 27 | `D7-note-listed-section2-rows` / `-section3-rows` | — | 不接 |
| 附注披露信息(国企) | 25 | 5 | 27 | `D7-note-soe-section2-rows` | — | 不接 |
| **明细表D7-2** | 41 | 27 | 82 | `D7-2-rows` | 1 | 已接 |
| **调整分录汇总表D7-3** | 23 | 10 | 7 | `D7-3-rows` | 🔍 核 | 可行性核 |
| **合同负债分析表D7-4** | 43 | 8 | 32 | `D7-4-credit-rows` / `D7-4-debit-rows` | **2** | ✅ |
| **账龄1年以上合同负债检查表D7-5** | 20 | 8 | 9 | `D7-5-rows` | 1 | ✅ |
| **关联方关系及交易检查表D7-6** | 31 | 11 | 15 | `D7-6-rows` | 1 | ✅ |
| **合同负债检查表D7-7** | 48 | 21 | 19 | `D7-7-period-rows` / `D7-7-post-rows` | **2** | ✅ |
| GT_Custom | 8 | 2 | 0 | — | — | 不接 |

### 🔴 两处必须登记的模板事实

1. **D6 册里有 `合同资产实质性程序表 D7A（原）`（104 行）、D7 册里有 `合同负债实质性程序表
   D8A（原）`（66 行）** —— 历史残留 sheet，命名与所属循环不符（D6 册含 D7A、D7 册含 D8A）。
   两张均 0 公式。声明时必须显式排除，且须确认 sheet 分派正则不会把它们误判成本循环的程序表。
2. **D6/D7 底稿目录完成度判定引用了无写入方的聚合键**（缺陷，本 spec 修）：
   `D6TabIndex.vue:54` 读 `D6-6-rows`（真实写入方用 `D6-6-block1-rows`/`-block2-rows`）、
   `:56` 读 `D6-8-rows`（真实 `D6-8-single-rows`）、`D7TabIndex.vue:50` 读 `D7-4-rows`
   （真实 `D7-4-credit-rows`/`-debit-rows`）、`:56` 读 `D7-7-rows`（真实 `D7-7-period-rows`/
   `-post-rows`）。四键全仓**零写入点** ⇒ 这四张在目录里完成度恒显示「未填」。与 D1 那个
   「四处拼锚点三处拼错、测试镜像同款错误恒绿而生产恒死」同型。

### 其余红基线（实测）

| 事实 | 实测值 |
|---|---|
| **三张调整分录汇总表全部有中央同步 hub** | `D5TabAdjustment.vue` / `D6TabAdjustment.vue` / `D7TabAdjustment.vue` 各接 `useAdjustmentCentralSync` **3 处** |
| 宿主 gating（三家同形，均单张写死） | `isD5DetailSheet = currentSheet === 'D5-2'` / `isD6DetailSheet === 'D6-2'` / `isD7DetailSheet === 'D7-2'` |
| `adapter_registered` | **三家全 False** —— 真库 `register_from_manifest()` 只注册 `{d2,d4,g7,h1}`；D5/D6 的 store 全库 0 行、无 current published representation |
| provider `FORMULA_MASK` | 三家均列向：D5 `F`/`J`/`L`/`O` · D6 `J`/`Q`/`T`（3 条）· D7 `I`/`P`/`R`/`U` |
| `MANAGED_FIELD_SPECS` 元组 | **D5 是 7 元组**（内联 `group_header_cell`），D6/D7 是 6 元组 + 独立 `GROUP_HEADER_CELLS` mapping ⇒ 上游 spec 裁决 3 统一为内联 7 元组 |

## Glossary

| 术语 | 含义 |
|------|------|
| 受管区 / binding | 契约声明的一个 `(sheet, table)` 受管数据区。一张 sheet 可含多个 |
| `RowTableSheetSpec` | 行表型受管 sheet 的声明数据类，由上游 D1 spec 交付 |
| `AdjudicationSheetSpec` | 审定表型声明数据类，以 `sections` + `row_mode` 参数表达形态差异 |
| store 键 / store item | `checklist_responses.item_id`，一条 store 载荷的标识 |
| `aging_layout` | 账龄组形态参数：`nested`(D7) / `flat`(D6) / `None`(D5) |
| `bidirectional` | 该 sheet 走真双向回写（HTML ↔ OO 单元格级合并） |
| `single_html` | 诚实裁决：不做单元格双向（无行身份列 / 有专用同步链冲突 / 与网格不对齐） |
| `paragraph_block_bidirectional` | 第五形态：段落块 + 分组紧凑表双向（D4-5 范式） |
| 可行性核硬门 | 上游 `blocking.8`：有行身份列 + 无专用同步链冲突，否则不得扩 `sheets[]` |
| hub store | 被多条专用链共同占用的 store 键（如 `D*-3-rows` 被借贷平衡 + 中央登记占用） |
| golden digest | 零回归度量：`build_contract_payload` / `build_store_projection` / `instrumentation_spec(s)` 的 canonical JSON sha256 |
| 整册 materialize | 对该 entry 全部 binding 逐趟跑 + `verify_unmanaged_regions` 逐 binding 全跑，任一失败整册 500 |
| `adapter_registered` | registry 是否真注册成功；False 表示缺 published representation，真库跑不起来 |
| 聚合键缺陷 | `D*TabIndex` 的完成度判定读了无写入方的聚合键（如 `D6-6-rows`），导致进度恒「未填」 |

## Requirements

### Requirement 1: D5 接入（2 张，最小循环）

**User Story:** 作为审计助理，我希望 D5 的公允价值测算表与审定表能切「在线编辑」并把改动写回。

#### Acceptance Criteria

1. WHEN 声明 D5-4 公允价值测算表 THEN 它 SHALL 用 `RowTableSheetSpec`，`store_item_id` 取实测值
   **`D5-4-rows`**；几何由 Task 1 实测（26 行 ×13 列 / 18 公式，主列 K6 I4）。
2. WHEN 声明 D5 审定表 THEN `managed_sheet` SHALL 取实测名 **`审定表D5`**（🔴 **无 `-1` 后缀**），
   按 `审定表D5-1` 推演会 sheet 找不到；`sections`/`row_mode` 由 Task 1 实测（18 行 ×12 列 /
   52 公式 ⇒ 逐格形态），**不得**照 D1-1/D2-1/D3-1 推演。
3. WHEN D5 接入完成 THEN 受管区 SHALL 从 1 增至 3，整册 materialize 200 且
   `verify_unmanaged_regions` 全绿。
4. WHERE D5 的 `aging_layout=None`（FVOCI 无账龄组）THE 声明 SHALL 不带账龄参数 —— 它是引擎
   「无分组」路径的基准样本。
5. WHEN `D5-4-rows` 被 OO 回写 THEN 其下游消费方 SHALL 仍正确重算（实测 `useD5CrossSheet` 读它）。

### Requirement 2: D6 接入（6 张，最大循环）

**User Story:** 作为审计助理，我希望 D6 的减值准备三张、关联方、检查表、审定表都能双向。

#### Acceptance Criteria

1. WHEN 声明 D6-3 减值准备明细表 THEN `store_item_id` = **`D6-3-rows`**；几何 29 行 ×14 列 /
   63 公式（主列 N12 E11 K11 ⇒ 列向），由 Task 1 实测定 `formula_columns`。
2. WHEN 声明 D6-5 关联关系及交易检查 THEN `store_item_id` = **`D6-5-rows`**（30 行 ×14 列 / 19 公式）。
3. WHEN 声明 D6-6 合同资产检查表 THEN 它 SHALL 声明**两个受管区**对应
   `D6-6-block1-rows` / `D6-6-block2-rows`（`useD6Inspection`），**不得**合并为单区，
   也**不得**使用无写入方的聚合键 `D6-6-rows`。
4. WHEN 声明 D6-8 减值准备测算 THEN `store_item_id` = **`D6-8-single-rows`**（不是 `D6-8-rows`，
   后者全仓零写入点）；48 行 ×15 列 / 58 公式（主列 D21 F21）。
5. WHEN 声明 D6-9 转回核销检查表 THEN 它 SHALL 声明**两个受管区**对应
   `D6-9-reversal-rows` / `D6-9-writeoff-rows`（`useD6WriteoffCheck`）。
6. WHEN 声明 D6-1 审定表 THEN 逐格 mask（43 行 ×13 列 / **177 公式** / 密度 32%，三循环里最高），
   `sections`/`row_mode` 由 Task 1 实测。
7. WHERE D6-7 减值准备会计政策检查（58 行 ×18 列 / 仅 7 公式）形态未定 THE 它 SHALL 先做形态核 ——
   候选 `paragraph_block_bidirectional`（D4-5 范式：段落 + 分组紧凑表）或 `single_html`。
8. WHEN D6 接入完成 THEN 受管区 SHALL 从 1 增至 9（D6-3 +1 / D6-5 +1 / D6-6 +2 / D6-8 +1 /
   D6-9 +2 / D6-1 +1，按审定表实测区块数调整）。
9. WHERE D6 的 `aging_layout=flat` THE 声明 SHALL 用 flat 键派生（`agePrior1y`/`ageEnd1y` 平铺），
   它是引擎 flat 路径的唯一样本。

### Requirement 3: D7 接入（5 张）

**User Story:** 作为审计助理，我希望 D7 的分析表、账龄检查、关联方、检查表、审定表都能双向。

#### Acceptance Criteria

1. WHEN 声明 D7-4 合同负债分析表 THEN 它 SHALL 声明**两个受管区**对应
   `D7-4-credit-rows` / `D7-4-debit-rows`（`useD7Analysis`），**不得**使用无写入方的聚合键
   `D7-4-rows`；43 行 ×8 列 / 32 公式（主列 E13 D11）。
2. WHEN 声明 D7-5 账龄 1 年以上检查表 THEN `store_item_id` = **`D7-5-rows`**（20 行 ×8 列 / 9 公式）。
   📌 它与 D3-5 同型（同为「账龄1年以上…检查表」，几何逐项相同）⇒ 声明骨架可互相复制。
3. WHEN 声明 D7-6 关联方关系及交易检查表 THEN `store_item_id` = **`D7-6-rows`**（31 行 ×11 列 / 15 公式）。
4. WHEN 声明 D7-7 合同负债检查表 THEN 它 SHALL 声明**两个受管区**对应
   `D7-7-period-rows` / `D7-7-post-rows`，**不得**使用无写入方的聚合键 `D7-7-rows`；
   48 行 ×21 列 / 19 公式。
5. WHEN 声明 D7-1 审定表 THEN 逐格 mask（32 行 ×12 列 / 84 公式），`sections`/`row_mode` 实测。
6. WHEN D7 接入完成 THEN 受管区 SHALL 从 1 增至 8（D7-4 +2 / D7-5 +1 / D7-6 +1 / D7-7 +2 /
   D7-1 +1，按审定表实测区块数调整）。
7. WHERE D7 的 `aging_layout=nested` THE 声明 SHALL 用 nested 键派生
   （`agingPrior`/`agingAudited` 子对象），它与 D3 同路径。
8. WHEN `D7-7-post-rows` 被 OO 回写 THEN `useD7CrossSheet` 与 `useD7Detail` 对它的读取 SHALL
   仍正确重算（实测两者都是它的下游）。

### Requirement 4: 三张调整分录汇总表 —— 可行性核（**不直接接入**）

**User Story:** 作为维护者，我不希望把已被中央登记链占用的 hub store 强行接成单元格双向。

#### Acceptance Criteria

1. WHEN D5-3 / D6-4 / D7-3 进入评估 THEN 三张 SHALL 各过上游可行性核硬门。
2. WHERE 三张与已判 `single_html` 的 D4-4 同型 THE 默认倾向 `single_html`。已实证：
   三家宿主（`D5TabAdjustment.vue` / `D6TabAdjustment.vue` / `D7TabAdjustment.vue`）
   **各接 `useAdjustmentCentralSync` 3 处** ⇒ 经后端 `AdjustmentSyncService` 中央登记；
   `D5-3-rows` / `D6-4-rows` / `D7-3-rows` 均为 hub store。
3. WHEN 裁决产出 THEN SHALL 落证据 JSON（照 `T08-d44-single-html-adjudication.json` 范式），
   **不改任何生产代码**（上游诚实边界红线）。
4. 📌 **触类旁通已闭环：七张调整分录汇总表全部同型** —— D1-5 `D1-entry-rows` /
   D2-4 `D2-entry-rows` / D3-3 `D3-aje-rows` / D4-4 `D4-4-rows`（已判）/ D5-3 / D6-4 / D7-3。
   ⇒ 本 spec 的三张核**建议与 D1/D2/D3 的四张合并为一次统一裁决**
   （`d-cycle-adjustment-sheets-single-html-adjudication`），避免在五个 spec 里重复五遍同一判据。
   IF 统一裁决 spec 已立 THEN 本需求降级为「引用其结论」。

### Requirement 5: 修 D6/D7 底稿目录的聚合键缺陷

**User Story:** 作为审计助理，我填满了 D6-6 / D6-8 / D7-4 / D7-7，底稿目录应显示已完成而不是未填。

#### Acceptance Criteria

1. WHEN 修 `D6TabIndex.vue` THEN `:54` 的 `hasJsonRows(m, 'D6-6-rows')` SHALL 改为判
   `D6-6-block1-rows` 与 `D6-6-block2-rows`（任一有行即算已填），`:56` 的 `'D6-8-rows'`
   SHALL 改为 `D6-8-single-rows`。
2. WHEN 修 `D7TabIndex.vue` THEN `:50` 的 `'D7-4-rows'` SHALL 改为判 `D7-4-credit-rows` 与
   `D7-4-debit-rows`，`:56` 的 `'D7-7-rows'` SHALL 改为判 `D7-7-period-rows` 与 `D7-7-post-rows`。
3. WHEN 判据落地 THEN 它 SHALL 以「播种真实写入方的键 ⇒ 完成度为已填」驱动；变异改回聚合键
   ⇒ 必红。🔴 **判据不得镜像错误键名** —— D1 那次「三个消费方的单测都镜像了同款错误锚点，
   故测试恒绿而生产恒死」是同源事故。
4. WHEN 修完 THEN SHALL grep 全仓确认这四个聚合键零残留引用。
5. WHERE 该缺陷独立于受管扩容 THE 它 SHALL 可在阶段 0 独立交付，不阻塞也不被阻塞。

### Requirement 6: 性能门与零回归

**User Story:** 作为多人平台的现场经理，我要求扩三个循环不让 materialize 变慢、也不动已接的三张明细。

#### Acceptance Criteria

1. WHEN 每接入一张 sheet THEN SHALL 实测一次该 entry 的整册 materialize 耗时并登记（脚本现测）。
2. IF 耗时超过配置软上限 THEN 接入 SHALL 停止并转性能 spec，**不得**带退化铺量。
3. WHEN 任一循环的受管区增加 THEN 其余 7 个 contract 的 golden digest SHALL 不变，
   已接三张明细（`D5-2-rows` / `D6-2-rows` / `D7-2-rows`）的 digest SHALL 不变。
4. WHERE D5/D6 的 store 真库全 0 行 THE 零回归门 SHALL 以**合成 payload** 驱动，不得跳过。
5. WHEN 前端宿主 gating 从单张扩到多张 THEN 受管 sheet 集合 SHALL **从 provider 受管清单派生**
   而非前端硬编码；`capability` 与 `flushHtml` SHALL 从 `Ref` 读取；非受管 sheet 保持现状行为
   + 显式中文原因，**不得**退化成 legacy 假双向。
6. WHEN 声明任一 sheet THEN 两张历史残留（D6 册的 `合同资产实质性程序表 D7A（原）` /
   D7 册的 `合同负债实质性程序表 D8A（原）`）SHALL 被显式排除，且 SHALL 确认 sheet 分派正则
   不会把它们误判成本循环的程序表。

### Requirement 7: 前置依赖

**User Story:** 作为维护者，我不希望本 spec 建立在未交付的引擎、未入库的修复或未注册的 adapter 上。

#### Acceptance Criteria

1. WHEN 本 spec 开工前 THEN 上游 `d1-sync-row-table-engine-and-d1-coverage` 的框架层
   （`RowTableSheetSpec` / `StoreItemSpec` 注册表 / `attach_sibling_bindings(provider=…)` /
   D5/D6/D7 三家 provider 声明化 + `aging_layout` 参数化）SHALL 已入 HEAD。
   🔴 本 spec 对上游的依赖比 D3 更重：**flat/nested 两条账龄路径的收敛正是在 D6/D7 身上验证的**，
   上游任务 16 未落则本 spec 的 D6/D7 声明无形态可依。
2. WHEN 三张审定表（D5 / D6-1 / D7-1）开工前 THEN 两件 SHALL 已在 HEAD：①`AdjudicationSheetSpec`
   ②`merge._protection` 格级判定 + `_mask_spans_data_column`。判定用 `git show HEAD:`。
3. 🔴 WHEN 任何真库整册 materialize 实测开工前 THEN 该循环的 `adapter_registered` SHALL 已为 True。
   实测现状 **三家全 False**（真库只注册 `{d2,d4,g7,h1}`；D5/D6 的 store 全库 0 行、无 current
   published representation）⇒ 需先造 seed 走通发布链。IF 未就绪 THEN 真栈判据如实标 `[ ]*`
   并写明「代码已改但未实测，卡 adapter 未注册」，**不得**以合成测试冒充真栈。
4. WHEN 上游位移判据（D1 spec 任务 24）未按 provider 参数化 THEN 本 spec 的四组双区
   （D6-6 / D6-9 / D7-4 / D7-7）SHALL 不进 `test_sibling_table_ref_row_shift.py` 自动覆盖清单
   ⇒ 双区接入阻塞。
5. IF 前置 1 未满足 THEN 全部阻塞。IF 仅 2 未满足 THEN 三张审定表阻塞。IF 仅 3 未满足 THEN
   代码与合成判据可推进、真栈阻塞。IF 仅 4 未满足 THEN 四组双区阻塞、单区可推进。
   需求 5（聚合键缺陷）**不受任何前置阻塞**。

### Requirement 8: 变异检验与证据

**User Story:** 作为质量控制复核合伙人，我要求每条判据都被证明不是永绿的装饰，且数字可复算。

#### Acceptance Criteria

1. WHEN 每条核心判据落地 THEN SHALL 配一次变异并记录打红条数；未能打红的重写而非保留。
2. WHEN 变异覆盖 THEN SHALL 至少含：`审定表D5` 写成 `审定表D5-1` / D6-8 用聚合键 `D6-8-rows` /
   四组双区任一只声明单区 / D6 的 flat 走 nested 派生 / 聚合键缺陷判据镜像错误键名 /
   去掉兄弟 Table ref 位移。
3. WHEN 真栈验收 THEN SHALL 按循环分三段（D5 / D6 / D7），各自切「在线编辑」→ OO canvas 逐值
   断言 → 改一格 → forcesave → 回读等值。`--workers=1`。
4. WHERE 真栈判据有已知陷阱 THE 沿用上游三条结论：不能用 `page.on('response')` 判 callback；
   不能用 `asc_*` API 写格（须真实键盘输入 `#ce-cell-name` → `keyboard.type` → Enter）；
   模式切换条选择器**须逐循环实测**不得照抄。
5. WHEN 证据登记 THEN SHALL 落 `docs/operations/evidence/d567-sync-coverage/`，按循环分子目录，
   数字脚本现测。

### 不在本 spec 范围

- **三家的程序表**（D5A / D6A / D7A）、**两张历史残留**（`D7A（原）` / `D8A（原）`）、
  **六张附注披露**、**底稿目录**、**GT_Custom**。
- **七张调整分录汇总表的统一裁决**：建议另立
  `d-cycle-adjustment-sheets-single-html-adjudication`；本 spec 只对 D5-3/D6-4/D7-3 做核并留证，
  IF 统一 spec 已立 THEN 降级为引用其结论。
- **D6-7 减值准备会计政策检查的接入**：本 spec 只做形态核（候选
  `paragraph_block_bidirectional` / `single_html`），接入归后续。
- **性能根因优化**（归两个性能 spec）。本 spec 只立门。
- **发布链 seed**（需求 7.3 的三家 `adapter_registered=False` 解除）——属 provisioning 范围。

### Requirement 9: 消费 D4 已验证的形态谱系（**复盘补**）

**User Story:** 作为维护者，我不希望把纯静态区硬塞进行表引擎 —— 引擎已有 `static_region` 路径
且能绕开整条位移链，而本 spec 恰有几张是它的强命中。

#### Acceptance Criteria

1. WHEN 判定形态 THEN 本 spec SHALL 消费上游 D1 spec 需求 11 定义的三维谱系
   （`binding_kind` 二分 / `row_identity_key` 三形态 / HTML-only item 子集），**不新造**。
2. 🔴 WHERE **D6-7 减值准备会计政策检查**（58 行 ×18 列 / **仅 7 公式**，主列 A2 C2 E2 I1
   —— 大表但几乎无公式、无明显数据行区）THE 它是 **`static_region` 的强命中**。
   首版需求 2.7 只给了 `paragraph_block_bidirectional` / `single_html` 两个候选，**漏了
   `static_region`** —— 而后者恰是 D4-13（A1:E19 无动态行无公式）已验证的那条路径。
   形态核 SHALL 把 `static_region` 列为**第一候选**。
3. 🔴 WHERE **D7-5 账龄 1 年以上合同负债检查表**（20 行 ×8 列 / 9 公式）与 **D3-5 同型**
   THE 两者 SHALL 用同一次形态判定的结论（UUID 动态行 / 稳定 key 固定行 / `static_region`），
   **不得**一个判行表另一个判静态区。首版只写「与 D3-5 同型、骨架可复制」，未做形态判定。
4. 🔴 WHERE **D6-9 减值准备转回、核销检查表**（30 行 ×8 列 / 10 公式）与
   **D6-5 关联关系及交易检查**（30 行 ×14 列 / 19 公式）公式密度都很低
   THE 它们 SHALL 各自做形态判定，不默认按行表声明。
5. WHEN 某张判为 `static_region` THEN 它 SHALL **绕开整条位移链**（无 `row_shift` / footer 两门 /
   minted UUID / workbook 传播 / 兄弟 Table ref 维护）⇒ **风险显著低于行表**，
   接入顺序 SHALL 相应提前（静态区先行、双区最后）。这会改变首版的阶段顺序。
6. WHEN 各 sheet 的 note / conclusion / procedures 类 item 落在 footer 之下 THEN 逐项核是否命中
   「footer 下 `static_row` 与插行 fail-closed 冲突」（先例 `HTML_ONLY_ITEM_IDS_D45`），
   命中则登记 HTML-only 子集而非强行受管。
7. WHEN 前端三家宿主接线 THEN 各 SHALL 覆盖**两套 gating** —— `isD*DetailSheet` +（若引入专用
   同步 sheet，如三张审定表走独立宿主）第二套。**漏登记会工具条叠加冲突**（D4-35 / D4-13 踩过）。
   首版需求 6.5 只提一套。
8. 🔴 WHEN 受管区总数被重算 THEN 首版的 D5 `1→3` / D6 `1→9` / D7 `1→8` SHALL 按形态判定结果
   修正 —— 判为 `static_region` 的 sheet 其受管区数按 definedName 锚点数而非行数计。
