# Requirements Document

## Introduction

本 spec 把 **D2 应收账款**的受管覆盖从 **1 张 sheet / 1 个受管区**扩到
**4 张 sheet / 6 个受管区**（`明细表D2-2` ① 已接 + `坏账准备明细表D2-3` **③** +
`调整分录汇总表D2-4` ① + `审定表D2-1` ①），并清理 D2 遗留的两处死代码。它**消费**
`workpaper-sync-row-table-engine-and-d1-coverage` 交付的框架层行表引擎与
`AdjudicationSheetSpec`，**不重造**任何引擎件。

用户裁决（2026-09-25）：**D1 / D2 / D4 各自独立成套**，顺序 **先 D1 再 D2**。⇒ 本 spec 的
阶段 0 有一条硬前置：D1 spec 的框架层必须已交付（需求 7）。

### 🔴 最关键的结构事实：D2 是三册模板，不是一册

实测 `backend/wp_templates/D/` 下 D2 有**三个** xlsx，而 **entry ↔ template blob 是 1:1**
（`TEMPLATE_RELATIVE_PATH` 是单路径），且 `generate_workpaper_sync_manifest._entry_id(document_type,
source_file)` **从宿主文件路径派生**并带 `seen_entry_ids` 碰撞检查 ⇒ **一个宿主恰一个 entry**。
而 D2 的 16 张 sheet 全在同一宿主 `GtD2AccountsReceivable.vue` 里按 tab 分流。

| 模板文件 | sheets | 含 | 本 spec |
|---|---|---|---|
| `D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx` | 11 | 底稿目录 / D2A / **审定表D2-1** / 披露×4 / **明细表D2-2**（已接）/ **坏账准备明细表D2-3** / **调整分录汇总表D2-4** / GT_Custom | ✅ **范围** |
| `D2-5  应收账款 -分析程序（Leap应对措施-分析程序）.xlsx` | 4 | 披露×2 / 应收账款分析表D2-5 / GT_Custom | ❌ 需新宿主，另立 |
| `D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx` | 12 | 底稿目录 / 披露×2 / D2-6 ~ D2-13 / GT_Custom | ❌ 需新宿主，另立 |

已接 entry `xlsx/gt-d2-accounts-receivable` 绑第一册（契约 `template_sha256=31e7992b…`，受管
`明细表D2-2` / `d22-managed`）。⇒ **本 spec 只扩第一册**；后两册要接必须先为它们建独立宿主组件
（改 entry_id 派生规则不可取：`entry_id` 是持久化键，`working_paper_sync_entry_state` /
mode storage key / room key 全用它）。

### 第一册各 sheet 几何实测（openpyxl 直读，非估算）

| sheet | rows | cols | 公式数 | 主公式列（计数） | 形态判定 |
|---|---|---|---|---|---|
| 底稿目录 | 19 | 8 | 0 | — | 导航，不接 |
| 应收账款实质性程序表D2A | 44 | 10 | 6 | A/C/F 各 2 | 步骤清单，不接 |
| **审定表D2-1** | 62 | 13 | **311** | E43 I40 J39 K39 A24 H24 F22 G22 | **逐格 mask**（密度 38%）⇒ `AdjudicationSheetSpec` |
| 附注披露信息(上市公司）D2-1 | 134 | 9 | 191 | C42 D39 E37 | 披露巨表，不接 |
| 附注披露信息（国企）D2-1 | 102 | 10 | 170 | C46 E32 B29 | 同上 |
| 附注披露信息(上市公司) | 181 | 9 | 158 | D36 C32 G25 | 同上 |
| 附注披露信息(国企) | 138 | 11 | 113 | C30 B19 F13 | 同上 |
| **明细表D2-2**（已接） | 35 | **39** | 107 | AB17 S15 Q14 | 行表，列向 mask `Q/S/AB` |
| **坏账准备明细表D2-3** | 27 | 14 | 69 | **E13 K11 N11** I5 | **列向**（计数≈数据行数）⇒ 行表引擎 |
| **调整分录汇总表D2-4** | 25 | 10 | 6 | A/D/G 各 2 | 行表引擎 |
| GT_Custom | 8 | 2 | 0 | — | 平台注入区，不接 |

模板原始态**无任何 Excel Table**（`tables=[]` 全 sheet）—— Table 由 `instrument_workbook_bytes_multi`
注入时建，属正常。

### 其余红基线（实测）

| 事实 | 实测值 | 出处 |
|---|---|---|
| `D2-detail-rows` 真库体量 | **4 行 / 3,061,466 字节**（平均 765KB/行） | PG 直查 |
| D2-2 模板数据区 | 模板 **35 行**，真库 **1260 行** ⇒ materialize 需插 **1200+ 行** | 模板 + 契约 |
| D2-2 离线剖析 | 10 行 6.7s / 50 行 8.8s / 200 行 15.9s / **729 行 59.3s**（超线性），走统一 materialize 曾 HTTP **>300s 超时** | `workpaper-sync-materialize-large-table-performance` |
| `useD2VoucherCheck`（旧套） | **全仓零消费方**（只有自身定义 + `export default`），**死模块 310 行** | grep |
| 前端实际挂载 | `D2TabVoucherCheck.vue` import `useD2VoucherCheckEnhanced` | grep |
| 旧套 store 数据 | `D2-voucher-params` 1 行 87B = `{"method":"随机","populationSize":0,"sampleSize":0,…}`；`D2-voucher-samples` 1 行 332B = 1 条全空骨架行；同一 wp `e2c95d10` | PG 直查 |
| 新套 store 数据 | `D2-vc-current-rows` / `D2-vc-post-rows` **全库 0 行** | PG 直查 |
| 死降级路径 | `useD2Adjudication:182-188` 逐行读 `D2-detail-{i}-{field}`，`useD2Detail` **只写** `D2-detail-rows` ⇒ 全仓零写入方、恒返 0 | grep |
| D2 非受管 sheet 行为 | **直接禁用**在线编辑（`syncUnavailableReason` = 「统一路径 canary 仅开放 D2-2 明细表在线编辑」），与 D1 落 legacy `GtOnlyOfficeSheet` 不同 | `GtD2AccountsReceivable.vue:443` |
| 桥的 entry 动态性 | `useWorkpaperSyncBridge` 的 `entryId: Ref<string>` **运行时取值**；但 `capability: capabilityForEntry(D2_SYNC_ENTRY_ID)` 与 `flushHtml` 闭包里是**构造时字面量** | `:309/:410/:417` |
| 「矩阵」实为行数组 | `createDefaultMigrationMatrix(): MigrationRateRow[]` = `{rowId, agingBand, year1Rate, year2Rate, year3Rate, avgRate, expectedLossRate}` ⇒ 标准行表，非二维 | `useD2Ecl` / `useD2PolicyCheck` |
| D2 披露行模型 | 用 `kind`（`D2AgingRowKind`/`D2ClassRowKind`/`category\|subtotal\|total`），行标识用 **`key`** 而非 `rowId`（仅 `D2IndividualRow` 用 `rowId`） | `useD2DisclosureNote` 12 行接口 |

### 本 spec 冻结的裁决

1. **只扩第一册**。后两册（D2-5 / D2-6~D2-13）需新建独立宿主组件才能有 entry，属独立立项
   （`d2-analysis-and-inspection-sync-hosts`），本 spec 显式登记不做。
2. **不改 `entry_id` 派生规则**。它是持久化键，改它会让既有 entry_state / mode storage / room key
   全部失配。
3. **不改权威模板**（不合册）。三册是审计方法论产物且 `template_sha256` 已冻结在契约里。
4. **D2-1 审定表走 `AdjudicationSheetSpec`**（D1 spec 交付），不进行表引擎 —— 实测 311 公式 /
   密度 38% / 逐格形态 / 写死 4 行 + SUMIF 取数，与行表域不同。
5. **删 `useD2VoucherCheck.ts`**（310 行，grep 零消费方）。旧套两个 store 键的**读兼容保留**
   （数据是空骨架但不主动丢），物理删除归后续 spec。
6. **删 `useD2Adjudication` 的死降级路径**（零写入方，恒返 0）。
7. **性能是本 spec 的一等约束**，不是附带项。D2-2 单表就是平台最大分母，受管 sheet 从 1 涨到 4
   会让整册 materialize 的 binding 数翻倍 ⇒ 需求 5 立硬门。
8. **D2A 程序表与 4 张披露 sheet 不接**。程序表是步骤清单（同 D1A）；披露是 102~181 行巨表
   且行模型（`kind`/`key`）与平台 `rowType`/`rowId` 不同构。

## Requirements

### Requirement 1：D2-3 坏账准备明细表接入（首张新增，行表引擎验证样本）

**User Story:** 作为审计助理，我希望 D2-3 坏账准备明细表能切「在线编辑」并把 OO 里的改动写回结构化视图。

#### Acceptance Criteria

1. WHEN 声明 D2-3 THEN 它 SHALL 用 D1 spec 交付的 `RowTableSheetSpec`，声明模块
   `phase5_d2_03_bad_debt.py` + 灰度开关，循环层 provider 只追加 sheet 清单项。
2. WHEN 声明公式列 THEN `formula_columns` SHALL 为实测的 `E` / `K` / `N` 三列（计数 13/11/11
   ≈ 数据行数 ⇒ 列向形态），mask 由引擎 property 现算，**不手写字面量**。
3. WHEN D2-3 的行分三类（`category: individual | aging | customer-type`）THEN 它们 SHALL 声明为
   **三个受管区**，对应实测的三个独立 store 键
   （`useD2BadDebt.CATEGORY_KEYS` = `D2-bd-individual-rows` / `D2-bd-aging-rows` /
   `D2-bd-customer-rows`），与 D1-4 **同型**。
   🔴 **本条是 2026-09-25 复盘修正项**：首版据不完整 grep 写成「单一 store 载荷内的 category
   字段、不拆受管区」并立了反向判据，实测 `useD2BadDebt.ts:64-68` 是 dict 字面量形式的三键
   映射（首轮 grep 模式 `^const \w+_KEY\s*=\s*'` 匹配不到 dict 内的值），结论完全相反。
4. WHERE D2-3 因此成为**同 sheet 多受管区** THE 它 SHALL 复用已修的兄弟 Table ref 位移 +
   `_GT_SYNC` footer 重冻结 + `CompositeRowShift` 累积归一化三层能力，且 SHALL 依赖 D1 spec
   任务 24（位移判据清单改按 provider 参数化）先落 —— 否则 D2-3 的三区不进
   `test_sibling_table_ref_row_shift.py` 的自动覆盖清单。
5. WHEN D2-3 含 `isSubRow` 展开子行与 `isFixed` 分类汇总行 THEN 它们 SHALL 映射到裁决 D4 的
   `rowType`（`dynamic` / `summary`），`isFixed` 不单独持久化。
6. WHEN 接入完成 THEN 整册 materialize SHALL 返回 200、`verify_unmanaged_regions` 全绿、
   binding 数从 **1 增至 4**（三个受管区），且耗时按需求 5 记录。
7. WHEN D2-3 的三个 store 键被 OO 回写 THEN 其**全部下游消费方**的 computed SHALL 仍正确重算 ——
   实测下游有 5 处：`useD2Adjudication.eclCrossValidation`(:618) / `useD2Ecl.d3BadDebtTotal`(:308) /
   `useD2WriteoffCheck.reversalConsistencyWarning`(:135-137) /
   `useD2DisclosureNote.badDebtSummary`(:481) 与 `importIndividualFromBadDebt`(:971) /
   `useD2CrossSheet`(:199-201)。判据 SHALL 覆盖它们，不得只验 D2-3 自身读回等值。

### Requirement 2：D2-4 调整分录汇总表接入

**User Story:** 作为审计助理，我希望 D2-4 调整分录也能在 Excel 里编辑并回写。

#### Acceptance Criteria

1. WHEN 声明 D2-4 THEN 它 SHALL 用 `RowTableSheetSpec`（25 行 × 10 列 / 仅 6 个公式 ⇒ 最简形态），
   store 键 `D2-entry-rows`。
2. WHEN 行含 `isPushedToAdjTable`（是否已推送到调整分录模块）THEN 该字段 SHALL 为 store-only，
   **不入**受管格 —— 它是平台流程状态，不是 Excel 上的业务列。
3. WHEN 借贷金额回写 THEN 既有借贷平衡校验（`BALANCE_TOLERANCE = 0.005`）SHALL 继续以合并后的
   值参与，容差口径不变。
4. WHEN 接入完成 THEN binding 数增至 3，门同需求 1.5。

### Requirement 3：D2-1 审定表接入（消费 `AdjudicationSheetSpec`）

**User Story:** 作为审计助理，我希望 D2-1 审定表的 SUMIF 取数与我的人工覆盖不互相吞掉。

#### Acceptance Criteria

1. WHEN 声明 D2-1 THEN 它 SHALL 用 D1 spec 交付的 `AdjudicationSheetSpec`，**不**用行表引擎。
2. WHEN 声明 mask THEN 它 SHALL 是**逐格**形态（实测 311 公式 / 62 行 13 列 / 密度 38%），且
   SHALL 依赖已入库的 `merge._protection` 格级判定 + `_mask_spans_data_column`
   （见需求 7.2 前置）。
3. WHEN D2-1 的四行（`individual` / `aging` / `customer-type` / `total`）是**写死**的 THEN spec
   SHALL 声明为固定行（`rowType='fixed'`，`total` 行为 `summary`），**不**走动态行 identity。
4. WHEN D2-1 的取数来自 D2-2 的 SUMIF（按 `creditRiskClassification` 分类汇总）THEN 它 SHALL
   接入四态覆盖状态机（`resolveCellState` / `displayValueForCellState`），复用
   `shared/dynamicAdjudicationRows`，**不得**在 D2 侧另写一套。
5. WHEN 现状 `isFromSumif: boolean` 标记存在 THEN 它 SHALL 归一到 `source` 维度
   （`tb` = SUMIF 派生 / `manual` = 人工），布尔标记删除。
6. WHEN 覆盖发生 THEN S2 SHALL 标「已人工覆盖」、S4 SHALL 同时呈现覆盖值 / 原派生值 / 现派生值
   且**不自动二选一**，并提供逐格「恢复取数」。
7. WHERE D2-1 与 D1-1 的行模型不同（写死 4 行 vs 动态票据种类）THE `AdjudicationSheetSpec`
   SHALL 以参数表达该差异，**不得**在引擎里加 `if is_d1` / `if is_d2` 分支。

### Requirement 4：两处死代码清理

**User Story:** 作为维护者，我不希望接 sync 时把死路径一起接进去，让「哪套是权威」变得更不清楚。

#### Acceptance Criteria

1. WHEN 删除 `useD2VoucherCheck.ts` THEN 删前 SHALL grep 证明零消费方（实测：仅自身定义 +
   `export default`，无任何 `.vue`/`.ts` import），删前删后测试 SHALL 全绿。
2. WHEN 删除该模块 THEN 旧套两个 store 键（`D2-voucher-params` / `D2-voucher-samples`，实测
   1 行 87B + 1 行 332B 且内容为空骨架/默认值）SHALL 保持**读兼容**，物理删除归后续 spec ——
   「数据是空骨架」是判断，不是删数据的授权。
3. WHEN 删除 `useD2Adjudication:182-188` 的死降级路径 THEN SHALL 同时断言主路径
   （读 `D2-detail-rows` JSON）行为逐值不变；变异去掉主路径 ⇒ 判据必红。
4. WHERE `useD2VoucherCheckEnhanced` 是唯一活路径 THE 它 SHALL 在本 spec 中**不接 sync**
   （D2-7 在第三册模板，属范围外），只作为「删旧套后唯一权威」的事实登记。
5. WHEN 清理完成 THEN 全仓 grep `D2-voucher-params|D2-voucher-samples|D2-detail-\{` SHALL 只在
   读兼容路径与本 spec 判据中出现。

### Requirement 5：性能硬门（本 spec 的一等约束）

**User Story:** 作为多人平台，我不接受 D2 受管 sheet 翻倍后 materialize 变成不可用。

#### Acceptance Criteria

1. WHEN 每接入一张 sheet THEN SHALL 实测一次整册 materialize 耗时并登记（脚本现测，不手抄）。
2. IF 整册 materialize 耗时超过配置软上限 THEN 接入 SHALL 停止并转性能 spec，**不得**带着退化
   继续铺量 —— D2-2 模板 35 行 vs 真库 1260 行 ⇒ 单张就要插 1200+ 行，实测 729 行已 59.3s。
3. WHEN 受管 sheet 从 1 增至 4 张（受管区从 1 增至 **6** 个）THEN SHALL 断言
   `BASELINE_EXTRACT_CACHE` 命中语义不变（键 `{contract_id}:{artifact_sha256}`，同 substrate
   二次请求命中）。
4. WHEN store-projection 被请求 THEN 其 `store_field_count` 与 `field_count` SHALL 记录实测值；
   🔴 判据**不得**用二者作差推断数据丢失（D4 spec 已因此误判一次：1648 vs 992 的差值 ≠
   store 被吞了多少业务值）。
5. WHERE `lock_room_oo_apply` 是 per-room 会话级锁横跨整个 CPU 段 THE 本 spec SHALL 登记
   「D2 多人同编同底稿会串行排队」这一既有事实，**不在本 spec 解决**（归性能 spec 的 ROI-6）。

### Requirement 6：零回归 —— 已接的 D2-2 与其余 7 个 contract 不变

**User Story:** 作为质控，我要求扩 D2 不动已经能用的 D2-2 和其他循环。

#### Acceptance Criteria

1. WHEN D2 受管 sheet 增加 THEN D2-2 的 `build_store_projection` / merge 输出 SHALL 逐字段等价，
   其 golden digest（D1 spec 交付的 24 digest 之一）SHALL 不变。
2. WHEN D2 provider 被改 THEN 其余 7 个 contract（b60/d1/d3/d4/d5/d6/d7）的 digest SHALL 不变。
3. WHEN 前端 `GtD2AccountsReceivable.vue` 的 sync 接线被改（`isD2DetailSheet` 从单张扩到多张）
   THEN 既有 `d2SyncHostWiring.spec.ts` / `d2SyncDurableGate.spec.ts` SHALL 仍绿或按新形态显式
   改写（改写须加反向断言「旧形态不得复活」）。
4. WHEN `capability` 与 `flushHtml` 改为按当前 sheet 解析 THEN 它们 SHALL 从 `Ref` 读取而非
   构造时字面量（实测现状：`entryId` 已是 `Ref` 但这两处是字面量），且 SHALL 断言切 sheet 后
   capability 随之变化。
5. WHERE D2 非受管 sheet 现状是**直接禁用**在线编辑 THE 扩容后未接的 sheet SHALL 保持禁用 +
   显式中文原因，**不得**退化成静默无反应或落 legacy 假双向。

### Requirement 7：前置依赖

**User Story:** 作为维护者，我不希望本 spec 建立在尚未交付或未入库的前提上。

#### Acceptance Criteria

1. WHEN 本 spec 开工前 THEN `workpaper-sync-row-table-engine-and-d1-coverage` 的框架层
   （`RowTableSheetSpec` / `StoreItemSpec` 注册表 / `attach_sibling_bindings(provider=…)`）
   SHALL 已交付并入库；需求 1/2 依赖它。
2. WHEN 需求 3（D2-1 审定表）开工前 THEN 两件 SHALL 已在 HEAD：①D1 spec 的
   `AdjudicationSheetSpec` ②`merge._protection` 的格级判定 + `_mask_spans_data_column`。
   判定 SHALL 用 `git show HEAD:<path>` 而非工作树 —— D1 spec 调研期间正因读工作树而把
   `_protection` 误登记为「已修复」（实测 HEAD 当时仍是只比列旧实现）。
3. IF 前置 1 未满足 THEN 本 spec 全部阻塞。IF 仅前置 2 未满足 THEN 需求 3 阻塞，需求 1/2/4/5
   可照常推进（D2-3/D2-4 的 mask 是列向、行范围恰等数据区 ⇒ 只比列与格级判定等价）。
4. WHEN 登记任一「已存在/已修复」前提 THEN SHALL 标注其入库状态，不得笼统表述。

### Requirement 8：变异检验与证据

#### Acceptance Criteria

1. WHEN 每条核心判据落地 THEN SHALL 配一次变异并记录打红条数；未能打红的判据重写而非保留。
2. WHEN 变异覆盖 THEN SHALL 至少含：D2-3 的 `formula_columns` 少一列 / D2-1 的固定 4 行改成动态
   identity / 四态用 `stored ≠ derived` 错法判覆盖 / 删掉 D2-2 主路径读 / 整册 materialize 去掉
   兄弟 Table ref 位移。
3. WHEN 真栈验收 THEN SHALL 覆盖：切「在线编辑」→ D2-3/D2-4/D2-1 的 OO canvas 逐值断言 →
   改一格 → forcesave → 回读结构化视图等值。`--workers=1`。
4. WHERE 真栈判据写法有已知陷阱 THE 本 spec SHALL 沿用 D4 spec 的三条结论：**不能**用
   `page.on('response')` 判 callback（OO 容器直接 POST 后端不经浏览器，须读后端
   `application_bound_at`）；**不能**用内部 `asc_*` API 写格（未经协同通道 ⇒ forcesave
   回 `cs_error=4` no_changes），只有真实键盘输入（名称框 `#ce-cell-name` → `keyboard.type`
   → Enter）才产生 changes；模式切换条选择器**须实测确认**不得照抄 D4。
5. WHEN 证据登记 THEN SHALL 落 `docs/operations/evidence/d2-sync-coverage/`，数字脚本现测。

### 不在本 spec 范围

- **D2-5 分析表**（第二册模板）与 **D2-6 ~ D2-13 检查表**（第三册模板）：需各建独立宿主组件
  才能有 entry，登记为 `d2-analysis-and-inspection-sync-hosts` 另立。含 D2-7 凭证抽查
  （双视图 + OCR + 方法论面板）、D2-8 政策（段落 + 两行表）、D2-10 ECL（三行表含连乘派生）、
  D2-11 转回核销、D2-12 质押保理、D2-13 业务模式（问卷）、D2-9 坏账测算。
- **D2A 程序表**（步骤清单）与**四张附注披露 sheet**（102~181 行巨表，`kind`/`key` 行模型与平台
  `rowType`/`rowId` 不同构）。
- **旧套 store 键物理删除**（本 spec 只删代码模块 + 保留读兼容）。
- **性能根因优化**（归 `oo-html-writeback-performance` 与
  `workpaper-sync-materialize-large-table-performance`）。本 spec 只立硬门、不优化。
- **`entry_id` 派生规则改造**（持久化键，风险高于收益）。
- **权威模板合册**（审计方法论产物 + `template_sha256` 已冻结）。
