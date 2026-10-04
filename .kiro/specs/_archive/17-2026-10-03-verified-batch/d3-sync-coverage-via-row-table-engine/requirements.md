# Requirements Document

## Introduction

本 spec 把 **D3 预收账款**的受管覆盖从 **1 张 sheet / 1 个受管区**（`预收账款明细表D3-2`）扩到
**6 张 sheet / 8 个受管区**，并对 `调整分录汇总表D3-3` 只做**可行性核 + 裁决**（默认倾向
`single_html`，见需求 5）。

它**消费**两个上游 spec，**不重造**引擎件、**不另起**平行裁决：
- `d1-sync-row-table-engine-and-d1-coverage` —— 框架层行表引擎 + `AdjudicationSheetSpec`
- **`d-cycle-sheet-bidirectional-expansion`（9/9 全绿）** —— D 循环 sheet 级扩容的裁决与分波真源

### 继承上游四条纪律（不再讨论）

1. **「一 entry 一 adapter」不变**。多受管 sheet 只扩契约 `sheets[]` + 宿主按 sheet 切
   `sheetKey`，禁止同 entry 注册第二个 `adapter_id`。
2. **诚实边界**：不是每张 sheet 都该双向。程序表 / 附注 / 与网格不对齐者判 `single_html`
   （另有第五形态 `paragraph_block_bidirectional`）。
3. **可行性核硬门**（上游 `blocking.8`）：「有行身份列」+「无专用同步链冲突」两条同时成立才可
   扩 `sheets[]`，否则判 `single_html` 并留证。
4. **D4-4 调整分录汇总已判 `single_html`**（无行身份列 / hub store 被
   `useAdjustmentCentralSync`→`AdjustmentSyncService` 占用 / 借贷平衡仅 HTML 侧强制 /
   排版占位）⇒ D3-3 据同判据走可行性核。

### D3 模板与几何实测（openpyxl 直读，非推演）

**单册 12 sheets**（`backend/wp_templates/D/D3 预收账款.xlsx`）。D2 的三册是特例，D3 与 D1 同为单册。

| sheet | rows | cols | 公式 | 主公式列 | 形态判定 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | 19 | 8 | 0 | — | 导航 | 不接 |
| 预收账款实质性程序表D3A | 28 | 10 | 6 | A2 C2 E2 | 步骤清单 | 不接 |
| **审定表D3-1** | 30 | 12 | **88** | E14 I12 J11 K11 | **逐格**（密度 24%） | ✅ `AdjudicationSheetSpec` |
| 附注披露信息(上市公司) | 26 | 5 | 33 | A13 B10 C10 | 披露 | 不接 |
| 附注披露信息(国企) | 16 | 4 | 22 | B9 C8 A5 | 披露 | 不接 |
| **预收账款明细表D3-2** | 39 | 27 | 79 | T14 H13 O13 Q13 | 行表 + nested 账龄 | 已接 `d32-managed` |
| **调整分录汇总表D3-3** | 23 | 10 | 6 | A2 D2 F2 | hub store | 🔍 **可行性核** |
| **预收账款分析表D3-4** | 38 | 9 | 22 | E8 D6 C3 | **双区**行表 | ✅ |
| **账龄1年以上的预收账款检查表D3-5** | 20 | 8 | 9 | A2 C2 E2 | 行表 | ✅ |
| **关联关系及交易检查表D3-6** | 34 | 12 | 16 | F6 D3 A2 | 行表 | ✅ |
| **预收账款检查表D3-7** | 48 | 18 | 19 | F5 G5 E3 | **双区**行表 | ✅ |
| GT_Custom | 8 | 2 | 0 | — | 平台注入区 | 不接 |

### 🔴 D3 的 store 键用**语义缩写**命名，不是 sheet 编号

按值 grep（`'D3-[A-Za-z0-9_-]+'`）实测 8 个行集键 —— **键名与 sheet 编号无对应关系**，
与 D5/D6/D7 大多用编号（`D5-2-rows` / `D6-3-rows`）的惯例不同：

| sheet | store 键 | 受管区 | 写入方 |
|---|---|---|---|
| D3-2 明细（已接） | `D3-det-rows` | 1 | `useD3Detail` |
| D3-3 调整分录 | `D3-aje-rows` | 🔍 核 | `useD3Adjustment` |
| D3-4 分析表 | `D3-ana-credit-rows` / `D3-ana-debit-rows` | **2** | `useD3Analysis` |
| D3-5 账龄 1 年以上 | `D3-lt-rows` | 1 | `useD3LongTerm` |
| D3-6 关联关系及交易 | `D3-rp-rows` | 1 | `useD3RelatedParty` |
| D3-7 检查表（凭证抽查） | `D3-vc-current-rows` / `D3-vc-post-rows` | **2** | `useD3VoucherCheck` |

⇒ **spec 声明里的 `store_item_id` 必须逐个取自实测，不得按 `D3-{n}-rows` 推演**。
这条有事故背书：D1/D2 三处受管区计数错误全部源于「按模式推演键名」而非按值 grep。

### 其余红基线（实测）

| 事实 | 实测值 | 出处 |
|---|---|---|
| entry 与受管 sheet | `xlsx/gt-d3-prepaid-accounts` / `d32-managed`，宿主 gating `isD3DetailSheet = currentSheet === 'D3-2'` | `GtD3PrepaidAccounts.vue` |
| **D3-3 有中央同步 hub** | `D3TabAdjustment.vue` 接 `useAdjustmentCentralSync` **3 处** | grep |
| 真库 store 数据 | `D3-det-rows` **全库 0 行**（同 D5/D6 的空表单） | 上游 registry 登记 |
| provider 现状 | `phase5_d3_prepaid_receipts.py` 847 行，`aging_layout=nested`，`FORMULA_MASK` 列向 4 条（`H`/`O`/`Q`/`T`） | grep |
| `adapter_registered` | **False** —— 真库 `register_from_manifest()` 当前只注册 `{d2,d4,g7,h1}`，D3 因 store 全库 0 行、无 current published representation 而未注册 | `adapters/registry.py` |

🔴 **`adapter_registered=False` 是本 spec 的真实前置风险**（D1/D2 没有）：D3 的 adapter 在真库
**尚未注册成功**，因为它没有 published representation。⇒ 任何「整册 materialize 实测」在真库上
都跑不起来，除非先造 seed 数据走通发布链。见需求 7。

## Glossary

| 术语 | 含义 |
|------|------|
| 受管区 / binding | 契约声明的一个 `(sheet, table)` 受管数据区。一张 sheet 可含多个 |
| `RowTableSheetSpec` | 行表型受管 sheet 的声明数据类，由上游 D1 spec 交付 |
| `AdjudicationSheetSpec` | 审定表型声明数据类，以 `sections` + `row_mode` 参数表达形态差异 |
| store 键 / store item | `checklist_responses.item_id`，一条 store 载荷的标识 |
| `bidirectional` | 该 sheet 走真双向回写（HTML ↔ OO 单元格级合并） |
| `single_html` | 诚实裁决：不做单元格双向（无行身份列 / 有专用同步链冲突 / 与网格不对齐） |
| `paragraph_block_bidirectional` | 第五形态：段落块 + 分组紧凑表双向（D4-5 范式） |
| 可行性核硬门 | 上游 `blocking.8`：有行身份列 + 无专用同步链冲突，否则不得扩 `sheets[]` |
| hub store | 被多条专用链共同占用的 store 键（如 `D3-aje-rows` 被借贷平衡 + 中央登记占用） |
| golden digest | 零回归度量：`build_contract_payload` / `build_store_projection` / `instrumentation_spec(s)` 的 canonical JSON sha256 |
| 整册 materialize | 对该 entry 全部 binding 逐趟跑 + `verify_unmanaged_regions` 逐 binding 全跑，任一失败整册 500 |
| `adapter_registered` | registry 是否真注册成功；False 表示缺 published representation，真库跑不起来 |

## Requirements

### Requirement 1: D3-6 关联关系及交易检查表接入（首张，最简样本）

**User Story:** 作为审计助理，我希望 D3-6 能切「在线编辑」并把 OO 里的改动写回结构化视图。

#### Acceptance Criteria

1. WHEN 声明 D3-6 THEN 它 SHALL 用上游交付的 `RowTableSheetSpec`，声明模块
   `phase5_d3_06_related_party.py` + 灰度开关，循环层 provider 只追加 sheet 清单项。
2. WHEN 声明 `store_item_id` THEN 它 SHALL 取实测值 **`D3-rp-rows`**，不得按 `D3-6-rows` 推演。
3. WHEN 声明公式列 THEN `formula_columns` SHALL 由 Task 1 按 openpyxl 实测填（模板 34 行 ×12 列 /
   16 公式，主列 `F`6 `D`3 `A`2 —— 需判定哪些是数据行列向公式、哪些是 footer/表头），
   mask 由引擎 property 现算，**不手写字面量**。
4. WHEN 接入完成 THEN 受管区 SHALL 从 1 增至 2，整册 materialize 200 且
   `verify_unmanaged_regions` 全绿，耗时按需求 6 记录。
5. WHEN `D3-rp-rows` 被 OO 回写 THEN 其下游 computed 消费方 SHALL 仍正确重算（Task 1 需 grep 出
   完整清单，已知 `D3TabIndex.vue` 的完成度判定读它）。

### Requirement 2: D3-4 分析表（双区）+ D3-5 账龄 1 年以上检查表接入

**User Story:** 作为审计助理，我希望分析表的借贷双区和账龄检查表也能双向。

#### Acceptance Criteria

1. WHEN 声明 D3-4 THEN 它 SHALL 声明**两个受管区**，对应实测的两个独立 store 键
   `D3-ana-credit-rows` / `D3-ana-debit-rows`（`useD3Analysis`），**不得**合并为单区。
2. WHERE D3-4 因此成为**同 sheet 多受管区** THE 它 SHALL 复用已修的兄弟 Table ref 位移 +
   `_GT_SYNC` footer 重冻结 + `CompositeRowShift` 累积归一化三层能力，且 SHALL 依赖上游 D1 spec
   任务 24（位移判据清单按 provider 参数化）先落。
3. WHEN 声明 D3-5 THEN `store_item_id` SHALL 取实测值 **`D3-lt-rows`**（`useD3LongTerm`），
   不得按 `D3-5-rows` 推演。
4. WHEN 两张接入完成 THEN 受管区 SHALL 从 2 增至 5（D3-4 +2 / D3-5 +1），门同需求 1.4。

### Requirement 3: D3-7 预收账款检查表（双区，凭证抽查）接入

**User Story:** 作为审计助理，我希望凭证抽查的本期/期后双区也能在 Excel 里编辑并回写。

#### Acceptance Criteria

1. WHEN 声明 D3-7 THEN 它 SHALL 声明**两个受管区**，对应 `D3-vc-current-rows` /
   `D3-vc-post-rows`（`useD3VoucherCheck`）。
2. WHERE D3-7 与 D2-7 凭证抽查同族 THE 本 spec SHALL 先确认 D3 侧**没有**「新旧两套并存」问题
   （D2 侧实测 `useD2VoucherCheck` 旧套零消费方 + `Enhanced` 新套才是活路径）；D3 只有
   `useD3VoucherCheck` 一个模块 ⇒ 无此债，但 Task 1 须实证。
3. WHEN 接入完成 THEN 受管区 SHALL 从 5 增至 7，门同需求 1.4。
4. WHEN `D3-vc-post-rows` 被 OO 回写 THEN `useD3CrossSheet` 对它的读取 SHALL 仍正确重算
   （实测它是 `D3-vc-post-rows` 的下游消费方）。

### Requirement 4: D3-1 审定表接入（消费 `AdjudicationSheetSpec`）

**User Story:** 作为审计助理，我希望审定表的取数与我的人工覆盖不互相吞掉。

#### Acceptance Criteria

1. WHEN 声明 D3-1 THEN 它 SHALL 用上游交付的 `AdjudicationSheetSpec`，**不**用行表引擎。
2. WHEN 声明 mask THEN 它 SHALL 是**逐格**形态（实测 30 行 ×12 列 / 88 公式 / 密度 24%），
   且 SHALL 依赖已入库的 `merge._protection` 格级判定 + `_mask_spans_data_column`（需求 7.2）。
3. WHEN 确定 D3-1 的区块数与行模型 THEN 它们 SHALL 由 Task 1 **实测**确定，**不得**按 D1-1
   （3 区 gross/bd/net + 动态票据种类）或 D2-1（1 区 + 写死 4 行）推演 —— 三个循环的审定表
   形态实测互不相同，这正是 `AdjudicationSheetSpec` 要参数化的维度。
4. WHEN D3-1 的取数来自 cross-sheet 派生 THEN 它 SHALL 接入四态覆盖状态机
   （`resolveCellState` / `displayValueForCellState`），复用 `shared/dynamicAdjudicationRows`，
   **不得**在 D3 侧另写一套。
5. WHEN 覆盖发生 THEN S2 SHALL 标「已人工覆盖」、S4 SHALL 同时呈现覆盖值 / 原派生值 / 现派生值
   且**不自动二选一**，并提供逐格「恢复取数」。
6. WHEN 接入完成 THEN 受管区 SHALL 从 7 增至 8（按 D3-1 实测区块数调整），门同需求 1.4。

### Requirement 5: D3-3 调整分录汇总表 —— 先可行性核再裁决（**不直接接入**）

**User Story:** 作为维护者，我不希望把已被中央登记链占用的 hub store 强行接成单元格双向。

#### Acceptance Criteria

1. WHEN D3-3 进入评估 THEN 它 SHALL 先过上游可行性核硬门：「有行身份列」+「无专用同步链冲突」。
2. WHERE D3-3 与已判 `single_html` 的 D4-4 同型 THE 默认倾向 `single_html`。已实证：
   `D3TabAdjustment.vue` **接了 `useAdjustmentCentralSync`（3 处）** ⇒ 经后端
   `AdjustmentSyncService` 中央登记；`D3-aje-rows` 是 hub store。
   待核：借贷平衡不变式是否仅 HTML 侧强制、模板 23 行 ×10 列有无行身份列。
3. WHEN 裁决产出 THEN SHALL 落证据 JSON（照 `T08-d44-single-html-adjudication.json` 范式），
   逐条记录依据，**不改任何生产代码**（上游诚实边界红线）。
4. IF 核出「有行身份列 + 无同步链冲突」THEN 才可改判并另起接入任务。
5. 📌 **触类旁通已闭环**：**六张**调整分录汇总表全部同型（D1-5 `D1-entry-rows` /
   D2-4 `D2-entry-rows` / D3-3 `D3-aje-rows` / D4-4 `D4-4-rows`（已判）/ D5-3 `D5-3-rows` /
   D6-4 `D6-4-rows` / D7-3 `D7-3-rows`），各自宿主均接 `useAdjustmentCentralSync`。
   ⇒ 建议 D 类全部调整分录汇总表**一次性统一裁决**，不逐循环重复核（见「不在本 spec 范围」）。

### Requirement 6: 性能门与零回归

**User Story:** 作为多人平台的现场经理，我要求扩 D3 受管区不让 materialize 变慢、也不动已经
能用的 D3-2 与其他循环。

#### Acceptance Criteria

1. WHEN 每接入一张 sheet THEN SHALL 实测一次整册 materialize 耗时并登记（脚本现测，不手抄）。
2. IF 整册 materialize 耗时超过配置软上限 THEN 接入 SHALL 停止并转性能 spec，**不得**带退化铺量。
3. WHEN D3 受管区增加 THEN `D3-det-rows`（已接 D3-2）的 golden digest SHALL 不变，
   其余 7 个 contract（b60/d1/d2/d4/d5/d6/d7）digest SHALL 不变。
4. WHEN store-projection 被请求 THEN `store_field_count` 与 `field_count` SHALL 记录实测值；
   🔴 判据**不得**用二者作差推断数据丢失（D4 spec 曾因此误判 1648 vs 992）。
5. WHERE D3 的 store 真库全 0 行 THE 零回归门 SHALL 以**合成 payload** 驱动，不得因无数据而跳过。
6. WHEN 前端宿主 gating 从单张扩到多张 THEN `capability` 与 `flushHtml` SHALL 从 `Ref` 读取
   而非构造时字面量，受管 sheet 集合 SHALL **从 provider 受管清单派生**而非前端硬编码；
   非受管 sheet SHALL 保持现状行为 + 显式中文原因，**不得**退化成 legacy 假双向。

### Requirement 7: 前置依赖

**User Story:** 作为维护者，我不希望本 spec 建立在未交付的引擎、未入库的修复或未注册的 adapter 上 ——
那样判据会以无法归因的方式红。

#### Acceptance Criteria

1. WHEN 本 spec 开工前 THEN 上游 `d1-sync-row-table-engine-and-d1-coverage` 的框架层
   （`RowTableSheetSpec` / `StoreItemSpec` 注册表 / `attach_sibling_bindings(provider=…)` /
   D3 provider 声明化）SHALL 已入 HEAD。
2. WHEN 需求 4（D3-1 审定表）开工前 THEN 两件 SHALL 已在 HEAD：①`AdjudicationSheetSpec`
   ②`merge._protection` 的格级判定 + `_mask_spans_data_column`。判定 SHALL 用
   `git show HEAD:<path>` 而非工作树 —— 上游 spec 调研期间正因读工作树而误登记过一次。
3. 🔴 WHEN 任何「真库整册 materialize 实测」开工前 THEN D3 的 `adapter_registered` SHALL 已为
   True。实测现状为 **False**（真库 `register_from_manifest()` 只注册 `{d2,d4,g7,h1}`，D3 因
   `D3-det-rows` 全库 0 行、无 current published representation 而未注册）。
   ⇒ 需先造 seed 数据走通发布链（approved bundle + published representation + entry_state），
   否则需求 1.4 / 6.1 的实测在真库跑不起来。IF 未就绪 THEN 相关判据如实标 `[ ]*`
   并写明「代码已改但未实测」，**不得**以合成测试冒充真栈。
4. IF 前置 1 未满足 THEN 本 spec 全部阻塞。IF 仅前置 2 未满足 THEN 需求 4 阻塞，需求 1/2/3/5
   可推进。IF 仅前置 3 未满足 THEN 代码与合成判据可推进，真栈实测阻塞。

### Requirement 8: 变异检验与证据

**User Story:** 作为质量控制复核合伙人，我要求每条判据都被证明不是永绿的装饰，且数字可复算。

#### Acceptance Criteria

1. WHEN 每条核心判据落地 THEN SHALL 配一次变异并记录打红条数；未能打红的判据重写而非保留。
2. WHEN 变异覆盖 THEN SHALL 至少含：`store_item_id` 按编号推演（`D3-6-rows` 而非 `D3-rp-rows`）
   / D3-4 只声明一个受管区 / D3-1 的固定区块数改错 / 四态用 `stored ≠ derived` 错法 /
   去掉兄弟 Table ref 位移。
3. WHEN 真栈验收 THEN SHALL 覆盖切「在线编辑」→ 各张 OO canvas 逐值断言 → 改一格 → forcesave
   → 回读结构化视图等值。`--workers=1`。
4. WHERE 真栈判据有已知陷阱 THE 沿用上游三条结论：不能用 `page.on('response')` 判 callback
   （OO 容器直接 POST 后端，须读 `application_bound_at`）；不能用 `asc_*` API 写格（未经协同
   通道 ⇒ `cs_error=4` no_changes），只有真实键盘输入（`#ce-cell-name` → `keyboard.type`
   → Enter）；模式切换条选择器**须实测确认**不得照抄。
5. WHEN 证据登记 THEN SHALL 落 `docs/operations/evidence/d3-sync-coverage/`，数字脚本现测。

### 不在本 spec 范围

- **D3A 程序表**（步骤清单）、**两张附注披露**、**底稿目录**、**GT_Custom**。
- **六张调整分录汇总表的统一裁决**：D1-5 / D2-4 / D3-3 / D5-3 / D6-4 / D7-3 全部同型
  （各自宿主均接 `useAdjustmentCentralSync`，D4-4 已判 `single_html`）⇒ 建议**一次性统一裁决**
  而非逐循环重复核。本 spec 只对 D3-3 做核并留证，统一裁决归
  `d-cycle-adjustment-sheets-single-html-adjudication`（建议新立）。
- **性能根因优化**（归 `oo-html-writeback-performance` /
  `workpaper-sync-materialize-large-table-performance`（已归档 `_archive/15-workpaper-sync-engine-hardening/`））。本 spec 只立门。
- **发布链 seed**（需求 7.3 的 `adapter_registered=False` 解除）——属 provisioning 范围。

### 顺带发现（登记，不在本 spec 处理）

**D6/D7 底稿目录完成度判定引用了无写入方的聚合键**（触类旁通 grep 抓到，与 D1 那个
「四处拼锚点三处拼错、测试镜像同款错误恒绿而生产恒死」同型）：

| 位置 | 判定读的键 | 真实写入方用的键 | 后果 |
|---|---|---|---|
| `D6TabIndex.vue:54` | `D6-6-rows` | `D6-6-block1-rows` / `-block2-rows` | 完成度恒「未填」 |
| `D6TabIndex.vue:56` | `D6-8-rows` | `D6-8-single-rows` | 同上 |
| `D7TabIndex.vue:50` | `D7-4-rows` | `D7-4-credit-rows` / `-debit-rows` | 同上 |
| `D7TabIndex.vue:56` | `D7-7-rows` | `D7-7-period-rows` / `-post-rows` | 同上 |

四个聚合键全仓**零写入点**（grep `item_id: 'X'` 与 `set('X'` 均 0）。D3 侧未见同类
（`D3TabIndex` 读的键都有写入方）。建议随 D5/D6/D7 spec 一并修或单独立项。

### Requirement 9: 消费 D4 已验证的形态谱系（**复盘补**）

**User Story:** 作为维护者，我不希望把纯静态区硬塞进行表引擎，也不希望重复解决 D4 已解答过的
「固定行要不要 identity 列」这类问题。

#### Acceptance Criteria

1. WHEN 判定形态 THEN 本 spec SHALL 消费上游 D1 spec 需求 11 定义的三维谱系
   （`binding_kind` 二分 / `row_identity_key` 三形态 / HTML-only item 子集），**不新造**。
2. 🔴 WHERE **D3-5 账龄 1 年以上检查表**（20 行 ×8 列 / 仅 9 公式，主列 A2 C2 E2 —— 公式数少且
   集中在前几列，形似固定结构）THE Task 1 SHALL 实测判定它属三形态中的哪一种：
   UUID 动态行 / **稳定 key 固定行**（D4-6 范式）/ **`static_region`**（若无行维度）。
   首版直接标「行表 + `D3-lt-rows`」未做形态判定。
3. 🔴 WHERE **D3-6 关联关系及交易检查表**（34 行 ×12 列 / 16 公式）是本 spec 的首张接入
   THE 它 SHALL 同样先过形态判定 —— 它被选作「最简样本」的前提是它确实是动态行表；
   若实测为固定行或静态区，接入顺序与声明形态都要改。
4. WHEN D3 各 sheet 的 note / conclusion / procedures 类 item 落在 footer 之下 THEN 逐项核是否
   命中「footer 下 `static_row` 与插行 fail-closed 冲突」（先例 `HTML_ONLY_ITEM_IDS_D45`），
   命中则登记 HTML-only。
5. WHEN 前端宿主接线 THEN SHALL 覆盖**两套 gating**（`isD3DetailSheet` + 若引入专用同步 sheet
   则另一套）—— 漏登记会工具条叠加冲突（D4-35 / D4-13 踩过）。首版需求 6.6 只提一套。
6. WHERE D3-1 审定表走独立宿主 THE 它属「专用同步 sheet」类 ⇒ 必须登记第二套 gating。
7. 🔴 WHEN 受管区总数被重算 THEN 首版路线 `1→2→4→5→7→8` SHALL 按形态判定结果修正 ——
   若 D3-5 / D3-6 中有走 `static_region` 的，它们绕开整条位移链（无 row_shift / footer 两门 /
   兄弟 Table ref 维护），**风险显著低于行表**，接入顺序应优先于双区。
