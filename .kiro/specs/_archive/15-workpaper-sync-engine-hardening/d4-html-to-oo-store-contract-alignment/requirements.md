# Requirements Document

## Introduction

**spec**：`d4-html-to-oo-store-contract-alignment`　**创建**：2026-09-23
**上游**：`workpaper-html-onlyoffice-bidirectional-writeback-closure`（平台总纲）
**参照**：`_archive/14-d4-bidirectional-writeback/d4-1-adjudication-bidirectional-writeback-and-formula-io`（12/12 已归档）

用户 2026-09-23 实测报障：「表格视图下是有数据的，但点击到在线编辑、切换到 OO 后，里面是空的，
没有实现写入。」真栈复现于 D4-1 营业收入审定表（项目 `0ec33ac9…` / 底稿 `b3ab3c46…`）：
HTML 主营段 7 行有真实金额，OO 里 R8:R11 全空、小计显示 0。

同一轮会话另一报障（「切回表格视图后无法再次切到在线编辑」）根因在 `utils/http.ts` 的请求
去重键**插入/删除不对称**（POST 键带 body 指纹入、不带 body 指纹删 ⇒ 键泄漏 5 分钟，
同 body 的 POST 在发出前即被 abort），**已当场根治并真栈验收 6/6**，判据
`src/utils/__tests__/httpDedupe.postKeySymmetry.spec.ts`（变异检验 2 条打红）。
它与本 spec 无关，**不在范围内**，此处登记仅为防止后来者把两件事混成一件。

### 范围裁定：为什么不是「D4 其余 34 张逐一修」

对同一底稿的 `GET …/store-projection` 做过逐表实测（43 张 row table，`field_count=923` /
`store_field_count=1525` / `row_count=399`）：**20 张「有行但零非空值」，其中 19 张对应的
store item 在 `checklist_responses` 里本就不存在或是空数组** —— 那些底稿 HTML 侧同样是空的，
不是缺陷。真正「HTML 有数据而 projection 没有」的只有审定表两区。

按存储模型逐个核对：其余 36 条 D4 store item **全部是单条 JSON 内联全量字段值**
（库中 16 条有数据的 item，其投影非空字段数全部 > 0）。「行清单 + per-field 值」这套模型
全平台只有 2 个消费方：`useD4Adjudication`（D4-1）与 `useK2Adjudication`（K2-1）。

⇒ **D4 内需要修的是 3 张（D4-1 / D4-35 / D4-13），分属两个互不相同的缺陷类。**

### 缺陷 A（D4-1 独有）：前后端存储模型错位，**两个方向都死**

后端 D4-1 provider 双向都假定「`D4-1-rows` 的**行对象**携带 label + 6 金额」：

* 出方向 `build_store_projection_d41` 逐行 `row.get(store_key)`，store_key ∈ `label /
  currentUnadjusted / currentAje / currentRje / priorUnadjusted / priorAje / priorRje`
  （`MANAGED_FIELD_SPECS`）；
* 回方向 `merge_projection_into_d41_rows` 逐字段 `target[store_key] = new_val`，已接在
  `merge_projection_into_all_d4_stores` 的 rows 循环里（`phase5_d4_revenue_detail.py`
  的 `STORE_ITEM_ID_D41:` 那一项）。

前端不是这么存的：共享件 `shared/dynamicAdjudicationRows.serializeRows()` **只落 4 个键**
`{rowId, label, source, accountCode}`（注释明说「派生列一律读时推导」）；金额由
`useD4Adjudication.persistFieldValue()` 落到**独立 item** `D4-1-{rowId}-{field}`，
读回也只走 `getRowFieldValue()` 读那些独立 item。两侧后果各自独立成立：

* **A1 出方向恒空**：6 个金额恒 `None`。库里唯一一条真 `D4-1-rows`（E2E 种子 wp
  `d4e2e000-…-d403`）正是 `[{"rowId":"seedmain","label":"…","source":"manual","accountCode":"6001"}, …]`
  —— 无任何金额键，实证这不是「该项目碰巧没填」。
* **A2 回方向不可见**：OO 侧改的值写进 `D4-1-rows` 的行对象，前端从不读那里。

### 缺陷 B（D4-1 独有）：跨表派生行不落库，store 里根本没有那些行

HTML 主营/其他两段显示的行**主体是派生行**：`useD4Adjudication.crossSheetMainRows` /
`crossSheetOtherRows` 由 `mainRevenueByProduct`（读 `D4-2-rows`）/ `otherRevenueByItem`
（读 `D4-3-rows`）现算聚合，`rowKey = xsheet-{section}-{labelKey}`、`isFromCrossSheet=true`，
**从不进 `dynamicRows`、从不落 `D4-1-rows`**。报障底稿的 `D4-1-rows` 在库里**完全不存在**，
两区因此向 projection 贡献 0 行，overlay 退回 substrate 基线（模板占位空行
`GTROW-D41MAIN-0008…0011`）⇒ OO 空表 + 小计 0，与用户截图逐项吻合。

### 缺陷 C（D4-35 / D4-13）：store item 清单与端点装配不对齐，**只错在出方向**

`store_projection_response.py` 装配 payloads 只遍历两个来源：`provider.STORE_ITEM_IDS`
与 `provider.STORE_ITEM_IDS_D45_FIXED`。而 provider 另外声明了：

| provider 侧声明 | 在 `STORE_ITEM_IDS` | 出方向消费 | 回方向 `oo_to_html` 消费 |
|---|---|---|---|
| `D4-35-data`（`STORE_ITEM_ID_D435_DICT`，注释明写"不进 STORE_ITEM_IDS"） | ✗ | ✗ | ✓ |
| `STORE_ITEM_IDS_D413_FIXED`（`D4-13-process` / `-conclusion`） | ✗ | ✗ | ✓ |
| `STORE_ITEM_IDS_D47_DEDICATED`（`D4-7-products` / `-monthly`） | ✓ | ✓ | ✓ |
| `STORE_ITEM_IDS_D45_FIXED` | ✗ | ✓（端点显式补喂） | ✓ |

代码探针实证（同一 contract、同一份非空 payload，两条路径对照）：

* **D4-35**：按端点真实装配规则 → `other_revenue_check_rows/*` **0 个字段**；手动塞入对照组
  → **32 个字段**（键形如 `other_revenue_check_rows/GTROW-D435-0015/check1`）。
* **D4-13**：固定键恒存在，故**必须比值不能比键数** —— 对照组两键值均为探针正文，
  端点真实装配下两键值均为 `''`。

⇒ D4-35 切 OO 恒空、D4-13 两段正文恒写不进 OO；且回方向拿不到 base，merge 会按空基线
覆盖（总纲已登记过的同型风险：HTML-only 字段丢失）。

### 爆炸半径：其余 13 张审定表今天不爆，但同源

`*TabAdjudication.vue` 全仓 grep：**只有 `d4/core/D4TabAdjudication.vue` 接了同步桥**
（`useD4SyncMode` + `WorkpaperSyncEditorHost`）。K2/D2/D6/D7/F3/E1/F5/G8/G9/G12/K4/L8/M5
以及 `shared/CycleTabAdjudication.vue` 均未接桥 ⇒ 缺陷 A/B 在它们身上是**潜伏**的。
其中 `useK2Adjudication` 与 D4-1 **共用同一套 per-field 存储模型**；`isFromCrossSheet`
派生行在 D2-1/D6-1/D7-1/F3-1 同样存在。

⇒ 修复必须落在**共享层**，使那 13 张将来接桥时自动继承，而不是只给 D4-1 打补丁。

## Glossary

| 词 | 含义 |
|---|---|
| 行清单 item | `{prefix}-rows`，共享件落的行身份数组（`rowId/label/source/accountCode`） |
| per-field item | `{prefix}-{rowId}-{field}`，共享件落的单格值 |
| 派生行 | `isFromCrossSheet=true` 的行，由上游明细现算聚合，`rowKey=xsheet-*`，当前不落库 |
| 出方向 | HTML → OO（`store-projection` → `pending-mutations` → `materialize`） |
| 回方向 | OO → HTML（forcesave → extract → `oo_to_html` merge 回 store） |
| overlay | store-projection = substrate extract 基线 ⊕ store；store 空时基线（模板占位）胜出 |
| `FORMULA_MASK` | D4-1 的 48 格 Excel 内部公式（E/I 审定数 + R12/18/19/21 的 B–I），不受普通值投影覆盖 |

## Requirements

### 需求 1：D4-1 出方向必须把「表格视图看得见的东西」全部带进 OO

**用户故事**：作为在 D4-1 核对完审定数、要去 Excel 上复核公式的审计助理，我切「在线编辑」
之后必须看到和表格视图**同一批行、同一批金额**，而不是一张空模板。

#### 验收标准

1.1. 对 HTML 表格视图中主营/其他两段**每一条可见数据行**（含派生行与手工行），
     `GET …/store-projection` 的 `row_keys.adjudication_main_rows` /
     `adjudication_other_rows` SHALL 包含其行身份，且 `values` SHALL 为该行的 `label`
     与 6 个金额各产出一个键。判据 SHALL 按**逐行逐字段等值**断言，不得只断言「行数 > 0」
     或「字段数 > 0」—— 本缺陷的现场形态正是「有 4 个行身份、0 个字段」。

1.2. 物化产物 SHALL 反读等值：materialize 之后 `extract` 出的两区字段集合与值，与 1.1 的
     projection SHALL 逐项相等。这条挡的是「projection 对了但 binding 没写」。

1.3. `FORMULA_MASK` 的 48 格 SHALL 仍由 Excel 内部公式产生、**不**被普通值投影覆盖。
     判据 SHALL 显式断言这 48 格在 projection 中不产键或 `is_protected`。

1.4. 派生行在 store 与 OO 侧 SHALL 与手工行**可区分**（`source='tb'` vs `'manual'`）。
     派生行的**默认**值来源仍是 D4-2/D4-3 现算聚合。

1.5. OO 侧对派生行金额的改动 SHALL **生效**并成为该格的权威值（2026-09-23 用户拍板选项 b）。
     HTML SHALL 显示覆盖后的值并**显式标记「已人工覆盖」**，SHALL NOT 静默显示派生值
     （静默显示派生值 = 用户在 Excel 里改的数看起来没生效，正是本 spec 起因的同型形态）。

1.6. 覆盖 SHALL 是**逐格**的，不是逐行：只被改过的那一格转为覆盖态，同行其余格 SHALL
     继续跟随上游。逐行标记会让未被改的 5 格悄悄冻结在当时的快照值上、从此不再跟随 D4-2/D4-3。

### 需求 2：D4-1 回方向必须让 OO 的改动在表格视图里看得见

**用户故事**：作为在 Excel 里改了手工行金额再切回表格视图的审计师，我必须看到我改的数，
否则我会以为改动丢了、然后改第二遍。

#### 验收标准

2.1. OO 侧改动经 forcesave → `oo_to_html` merge 落库后，HTML 侧重载 SHALL 读到新值。
     判据 SHALL 是一条**真链**（store → materialize → 改产物 → extract → merge → HTML 读回），
     不得两端各自 mock。现状缺陷正是「merge 写进了行对象、HTML 读的是 per-field item」，
     两端分别 mock 的测试对此天生是盲的。

2.2. 回方向 SHALL NOT 丢 HTML-only 字段（`source` / `accountCode` / 非受管列）。

2.3. 出方向与回方向 SHALL 走**同一份**「行 → 存储键」映射声明，不得各写一遍。
     判据 SHALL 能证明二者引用同一符号（改一处另一处必然跟着变）。

### 需求 3：store item 清单单源，端点装配不得漏项

**用户故事**：作为维护者，我不希望「provider 声明了一条 store item，而某个方向的装配
代码忘了喂它」这种缺陷再发生第三次。

#### 验收标准

3.1. provider SHALL 暴露**一个**权威口径回答「本 entry 的全部 store item」；出方向
     （`store_projection_response`）与回方向（`oo_to_html`）SHALL 都只从它取，
     不得各自维护并集。

3.2. 修复后 D4-35 与 D4-13 的出方向 SHALL 真的拿到 payload：
     * `other_revenue_check_rows/*` 在有 store 数据时字段数 SHALL > 0（现状 0，对照组 32）；
     * `d413_erp_check_fixed/process` 与 `/conclusion` 的值 SHALL 等于 store 中的正文
       （现状恒 `''`）。
     判据 SHALL 对 D4-13 **比值**而不是比键数（固定键恒存在，比键数恒绿）。

3.3. SHALL 有一条结构判据枚举 provider 上所有 `STORE_ITEM_IDS*` 形态的声明与 dict-store
     常量，断言它们**逐个**被两个方向消费；新增一条未接线的声明 SHALL 打红。这条 SHALL
     落成 CI 卡点（`backend/scripts/check/`），而不是只放在 pytest 里 ——
     `tests/workpaper_sync/` 存在与本 spec 无关的既存失败，在那个分母上「pytest 红了」
     不是可归因信号。

### 需求 4：修在共享层，其余 13 张审定表接桥即继承

**用户故事**：作为下一个要给 K2-1 或 D6-1 接双向回写的人，我不该再踩一遍同一个坑。

#### 验收标准

4.1. 缺陷 A 的修复 SHALL 落在 `shared/dynamicAdjudicationRows` 这一层（或其同级的单一真源），
     使 `useK2Adjudication` 无需改业务代码即获得同样的存储形态。判据 SHALL 断言两个消费方
     读写的是同一套序列化实现。

4.2. 存储形态变更 SHALL 对既有数据向后兼容：已落库的 per-field item SHALL 被一次性迁移或
     在读侧兼容，**不得**让任何已填过 D4-1/K2-1 的项目出现金额归零。判据 SHALL 包含一条
     「旧形态数据读回等值」的迁移用例。

4.3. SHALL NOT 改动 D1/J1 等**未使用** per-field 金额模型的消费方的行为
     （`useD1DetailCategory` 等自带 `serializeRows` 的另一套实现不在范围内）。

### 需求 5：判据不得空转

#### 验收标准

5.1. 本 spec 每一条新判据 SHALL 做一次**变异检验**：把被修的那行改回缺陷形态，判据必须打红。
     红的证据 SHALL 登记（文件 + 条数）。

5.2. 验收 SHALL 含真栈 Playwright 实测：D4-1 表格视图 → 在线编辑，OO 里 R8 起的行与 HTML
     逐行对齐；D4-35 / D4-13 各一次同款实测。`getDiagnostics` 与单测全绿 SHALL NOT 被当作
     验收（总纲已登记过的教训）。

5.3. 需求 6 的覆盖态 SHALL 有一次真栈往返实测：在 OO 里改一个派生行金额 → 保存 → 切回
     表格视图 → 该格显示改后值且带「已人工覆盖」标记 → 再改 D4-2 的对应产品金额 →
     该格进入需求 6.4 的冲突态并两值都可见。

### 需求 6：人工覆盖的状态封闭、可见、可撤销

**用户故事**：作为在 Excel 里手工改过 D4-1 某格、之后 D4-2 又被别人改过的复核人，我必须
同时看见「我改的数」和「上游现在的数」，由我决定用哪个 —— 系统不许替我二选一。

选项 b 的代价就在这里：一旦 OO 侧的覆盖生效，「覆盖值」与「上游派生值」就成了两个可能同时
存在且不相等的事实。本需求把这四种组合穷举封闭，不留「看运气」的格。

#### 验收标准

6.1. 覆盖判定 SHALL 基于**显式落库的派生快照**（design 裁定其形态），SHALL NOT 用
     「store 值 ≠ 当前派生值」作判据 —— 上游一变，所有纯派生格都会满足那个条件而被误判成
     人工覆盖。这条是本需求最容易写错的一处，必须有判据钉住（上游变化后纯派生格不得被标覆盖）。

6.2. 逐格状态域 SHALL 恰为四态且穷举封闭：
     * S1 纯派生（store = 快照 = 现算）→ 显示现算值，无标记；
     * S2 人工覆盖、上游未变（store ≠ 快照，快照 = 现算）→ 显示 store 值 + 「已人工覆盖」；
     * S3 无覆盖、上游已变（store = 快照 ≠ 现算）→ 自动跟随，把 store 与快照一并推到现算；
     * S4 人工覆盖 且 上游已变（store ≠ 快照 ≠ 现算）→ 见 6.4。
     判据 SHALL 逐态各一条，且 SHALL 有一条断言「不存在第五态」。

6.3. S3 的自动跟随 SHALL 是幂等的（值未变不写库），否则每次渲染都会推一次内容版本。

6.4. S4 SHALL 显式冲突可见：HTML SHALL 同时呈现覆盖值与**当前**派生值（以及被覆盖时的
     原派生值），并 SHALL NOT 自动二选一。SHALL 提供「恢复取数」动作把该格退回 S1。

6.5. 「恢复取数」SHALL 只影响被点的那一格，且 SHALL 在 OO 侧下一次物化时把该格写回派生值
     （否则 HTML 退回派生、OO 还留着旧覆盖值，两侧再次分叉）。

6.6. 覆盖 SHALL NOT 使该行脱离 D4-2/D4-3 的交叉验证：既有 `mainCrossValidation` /
     `otherCrossValidation` 告警 SHALL 继续按覆盖后的值参与比对 —— 覆盖的目的是让审计师
     的判断生效，不是让差异消失。

### 需求 7：本期 AJE/RJE 小计两侧口径必须一致（既有缺陷，被选项 b 放大）

**用户故事**：作为在两个视图之间来回核的复核人，同一张表的同一个小计格在 HTML 和 Excel 里
必须是同一个数。

#### 背景（模板实测）

`backend/wp_templates/D/D4 收入底稿.xlsx` 的受管 sheet 实测公式：
`C12 = =SUM(C8:C11)` / `D12 = =SUM(D8:D11)`（本期账项/重分类调整小计 = **逐行汇总**）。
而 HTML 的 `buildSubtotalRow(..., adjTotals.mainAje, adjTotals.mainRje)` 把本期 AJE/RJE 小计
取成 **D4-4 调整分录汇总额**，**不**逐行汇总（上期 AJE/RJE 小计反而是逐行汇总的）。

⇒ 两侧本期 AJE/RJE 小计**今天就可能不等且无任何告警**。这不是本 spec 引入的，但选项 b
让逐行 AJE/RJE 可被用户在 OO 侧写入，会把它从「理论不一致」变成「一改就不一致」。

同一处另有两条与之相关的死代码（实测）：`buildCrossSheetRow` 把派生行
`currentAje/currentRje/priorAje/priorRje` **硬编码 0**，而其上方注释写「AJE/RJE 仍从
per-field 键读 ⇒ 审计师对派生行填的调整不丢」——注释描述的行为并不存在；
`isEditable: r.source !== 'tb' || true` 的 `|| true` 使前半段成为死表达式。

#### 验收标准

7.1. HTML 与 OO 的本期 AJE/RJE 小计 SHALL 同口径。判据 SHALL 以模板公式为第三边
     （不是两侧互相比对 —— 两侧同错会自洽）。

7.2. 若逐行 AJE/RJE 之和与 D4-4 汇总额不等，SHALL 显式告警，SHALL NOT 用任一侧静默盖掉
     另一侧。D4-4 仍是调整分录的权威源，但「D4-1 逐行填的调整 ≠ D4-4 汇总」本身是一条
     需要审计师知道的事实。告警 SHALL 复用本组件既有 `mainCrossValidation`/
     `otherCrossValidation`（小计 vs D4-2/D4-3）的同构范式（computed 返回提示串、
     超容差才亮、不改任一侧、不阻塞），SHALL NOT 另造校验机制。

     「D4-1 小计恒等于 D4-4」若为审计要求，SHALL 由审计师依告警调平实现，SHALL NOT 通过
     改变小计算法（算法恒按模板逐行汇总）或让系统自动盖掉某侧来"消除"差异。

7.3. 上述两条死代码 SHALL 一并清掉（注释改成与实现一致、或把实现补成注释所述并加判据）。
     SHALL NOT 留下「注释声明了一种行为而代码是另一种」的状态。
