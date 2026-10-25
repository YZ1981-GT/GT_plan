# Design Document

## Overview

D2 应收账款的受管覆盖从 **1 张扩到 4 张**（`明细表D2-2` 已接 + 新增 `坏账准备明细表D2-3` /
`调整分录汇总表D2-4` / `审定表D2-1`），并清掉两处死代码。本 spec 是 D1 spec 的**消费方**：
引擎、注册表、`AdjudicationSheetSpec`、四态状态机全部由它交付，这里只写**声明**。

设计的全部判断都来自实测（模板 openpyxl 直读 + PG 直查 + grep），不是照 D1 推演 —— 事实证明
D2 与 D1 在最关键的一点上不同：**D2 是三册模板**。

## Architecture

### 三册约束与本 spec 的范围切法

```
entry ↔ template blob 是 1:1（TEMPLATE_RELATIVE_PATH 单路径）
_entry_id(document_type, source_file) 从宿主文件派生 + seen_entry_ids 碰撞检查
      ⇒ 一个宿主恰一个 entry
D2 的 16 张 sheet 全在同一宿主 GtD2AccountsReceivable.vue（按 tab 分流）
      ⇒ D2 现在只能有 1 个 entry，只能覆盖 1 册
```

```
第一册  D2-1至D2-4 …（Leap-常规程序）.xlsx   11 sheets   ← 本 spec（entry 已存在）
        ├ 底稿目录                    不接（导航）
        ├ 应收账款实质性程序表D2A       不接（步骤清单）
        ├ 审定表D2-1                  ✅ 新增（AdjudicationSheetSpec）
        ├ 附注披露 ×4                 不接（巨表 + 行模型不同构）
        ├ 明细表D2-2                  已接（d22-managed）
        ├ 坏账准备明细表D2-3           ✅ 新增（RowTableSheetSpec）
        ├ 调整分录汇总表D2-4           ✅ 新增（RowTableSheetSpec）
        └ GT_Custom                  不接（平台注入区）

第二册  D2-5 …（分析程序）.xlsx          4 sheets    ← 需新宿主，另立 spec
第三册  D2-6至D2-13 …（检查）.xlsx      12 sheets    ← 需新宿主，另立 spec
```

三个被否掉的替代方案及理由：

| 方案 | 否掉理由 |
|---|---|
| 改 `_entry_id` 派生规则支持一宿主多 entry | `entry_id` 是持久化键 —— `working_paper_sync_entry_state` / `workpaperSyncModeKey({entryId,wpId,sheetKey})` / room key 全用它。改它会让既有状态全部失配，风险远高于收益 |
| 合册（三册合一） | 权威模板是审计方法论产物，且 `template_sha256=31e7992b…` 已冻结在契约里。改模板要重走 review + 发布链 |
| 现在就为后两册建宿主 | 要动前端路由 + `htmlRendererRegistry` + manifest 生成 + 两个新 entry 的完整发布链。改动面跨层，应单独立项评估，不夹带 |

### 声明层结构（消费 D1 spec 的框架件）

```
backend/app/services/workpaper_sync/
  pilot_d2_large_json.py            循环层：ENTRY_ID / 模板路径 / sheet 清单 / 4 个开关
                                    （pilot_ 前缀函数保留别名，裁决不改名）
  phase5_d2_02_detail.py            已接 D2-2 的声明（D1 spec 阶段 3 拆出）
  phase5_d2_03_bad_debt.py          ✅ 新增：RowTableSheetSpec
  phase5_d2_04_adjustment.py        ✅ 新增：RowTableSheetSpec
  phase5_d2_01_adjudication.py      ✅ 新增：AdjudicationSheetSpec
```

## Components and Interfaces

### D2-3 坏账准备明细表（RowTableSheetSpec）

实测几何：27 行 × 14 列 / 69 公式，主公式列 `E`(13) `K`(11) `N`(11) `I`(5) —— 前三列计数
≈ 数据行数 ⇒ **列向形态**，正是行表引擎的表达域。

**三个受管区各一份 spec**（同 managed_sheet、不同行段与 UUID 列，形如 D4-20 的三区）：

```python
SPEC_D203_INDIVIDUAL = RowTableSheetSpec(
    managed_sheet="坏账准备明细表D2-3", sheet_key="d23-managed-individual",
    table_key="bad_debt_individual_rows", store_item_id="D2-bd-individual-rows",
    formula_columns=("E", "K", "N"),   # mask 由引擎 property 现算，不手写
    aging_layout=None,                 # D2-3 无账龄组（账龄在 D2-2）
    store_kind=StoreKind.rows,
    # first/last_data_row / footer_row / uuid_col / table_name 由 Task 1 实测填
)
SPEC_D203_AGING    = …  # store_item_id="D2-bd-aging-rows"
SPEC_D203_CUSTOMER = …  # store_item_id="D2-bd-customer-rows"
```

三区的行段划分须由 Task 1 实测确定（27 行 ×14 列里三类各占哪几行）。UUID 列按 D4-20 三区范式
各占一列。🔴 三区同 sheet ⇒ 上区插行会下推下区，必须有兄弟 Table ref 位移能力（裁决 E2 后果 1）。

`isSubRow`（展开子行）与 `isFixed`（分类汇总行不可删）映射到裁决 D4 的 `rowType`：
子行 → `dynamic`；分类汇总行 → `summary`（computed 不落库）。`isFixed` 不单独持久化。

### D2-4 调整分录汇总表（RowTableSheetSpec）

实测 25 行 × 10 列 / 仅 6 个公式（A/D/G 各 2，应为合计行）⇒ 最简形态，是引擎的
「无派生列 + footer 合计」基线样本。

`isPushedToAdjTable`（是否已推送到调整分录模块）是**平台流程状态而非 Excel 业务列** ⇒
声明为 store-only，不入受管格。这条有先例：D5 的 `postRealized` / `eclStage` 同样 store-only
不入契约。

借贷平衡校验（`BALANCE_TOLERANCE = 0.005`）继续以**合并后**的值参与，容差口径不变。

### D2-1 审定表（AdjudicationSheetSpec）

实测 62 行 × 13 列 / **311 公式**，公式密度 38%，主公式列 E(43) I(40) J(39) K(39) A(24)
H(24) F(22) G(22) —— 计数远超数据行数 ⇒ **逐格形态**，与 D4-1 的 48 格同类，不是列向区间。

与 D1-1 的形态差异（这是 `AdjudicationSheetSpec` 必须参数化的点，不是 if 分支）：

| | D1-1 | D2-1 |
|---|---|---|
| 区块 | 3（gross / bd / net） | 1 |
| 行 | **动态**票据种类（来源 D1-2） | **写死 4 行** individual / aging / customer-type / total |
| 取数 | D1-2 原值 + D1-4 按票据种类小计 | D2-2 **SUMIF**（按 `creditRiskClassification` 分类汇总） |
| 行 identity | 需动态 identity 列 | **不需要** —— 固定行按 `rowType='fixed'` + 静态行号声明 |

⇒ `AdjudicationSheetSpec` 至少要能表达 `sections: tuple[...]`（1 或 3）与
`row_mode: 'fixed_rows' | 'dynamic_identity'` 两个维度。D2-1 取
`sections=(1 个,)` + `row_mode='fixed_rows'`，`total` 行 `rowType='summary'`。

四态覆盖状态机复用 `shared/dynamicAdjudicationRows.resolveCellState` /
`displayValueForCellState`。现状 `isFromSumif: boolean` 归一到 `source`（`tb` = SUMIF 派生 /
`manual` = 人工）。

🔴 **D2-1 的逐格 mask 依赖 `merge._protection` 格级判定已入库**（需求 7.2）。若未入库，
只比列的旧实现会把 D2-1 声明 `editable` 的金额字段整列误判 `read_only_masked_cell` ——
这正是 D4-1 踩过的坑（六个金额字段全被挡、四态 UI 成死代码）。判定用 `git show HEAD:`。

### 前端接线改造（三处字面量改 Ref）

实测 `GtD2AccountsReceivable.vue` 现状是**单张写死**：

```ts
const D2_SYNC_ENTRY_ID = 'xlsx/gt-d2-accounts-receivable'      // :304
const D2_MANAGED_SHEET_KEY = 'd22-managed'                     // :306
const isD2DetailSheet = computed(() => currentSheet.value === 'D2-2')   // :397
const syncEntryId = ref(D2_SYNC_ENTRY_ID)                      // :407  ← 已是 ref
const syncSheetKey = ref(D2_MANAGED_SHEET_KEY)                 // :408  ← 已是 ref
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,                                        // ✅ 桥内运行时取值
  sheetKey: syncSheetKey,                                      // ✅
  capability: capabilityForEntry(D2_SYNC_ENTRY_ID),            // 🔴 构造时字面量
  flushHtml: async () => { … entryId: D2_SYNC_ENTRY_ID, … sheetKey: D2_MANAGED_SHEET_KEY … },  // 🔴 闭包字面量
})
```

要改三处：
1. `isD2DetailSheet` → `isD2SyncedSheet`（按受管 sheet 集合判定，集合从 provider 的受管清单派生
   而非前端硬编码 4 个字面量）
2. `syncSheetKey` 随 `currentSheet` 计算（`D2-2→d22-managed` / `D2-3→d23-managed` / …）
3. `capability` 与 `flushHtml` 改读 ref —— entryId 在 D2 内**始终是同一个**（一册一 entry），
   所以这两处严格说不会因切 sheet 而变，但仍应改成读 ref 以消除「字面量与 ref 两个真源」

`entryId` 保持单值（D2 只有一个 entry）。桥的注释已记录一个相关事实：**D4 整册 40+ 张子 sheet
共用同一 entryId，于是不同子 sheet 间 `store-projection` / `materialize` 是同一个 URL，
http.ts 去重层会 abort 上一发在飞的同 URL 请求** —— D2 扩到 4 张后会进入同一情形，该去重坑
已在 D4 侧处理（桥内单独识别、不记 `lastError`），D2 直接受益，但真栈判据须覆盖「连续切两张
受管 sheet 都能进 OO」。

非受管 sheet 保持**直接禁用** + 中文原因（现状 `syncUnavailableReason` = 「统一路径 canary 仅
开放 D2-2 明细表在线编辑」，文案需按新集合改写）。🔴 **不得**退化成落 legacy
`GtOnlyOfficeSheet` —— D1 是那样做的，但 D1 的 legacy 分支 `migration_state` 标的就是
`legacy_fake_bidirectional`（OO 里改的东西不会合并回 `checklist_responses`，切回即丢）。
D2 现在没这个坑，不能因为「对齐 D1」而引入。

## 性能设计（本 spec 的一等约束）

分母事实：

```
D2-detail-rows 真库          4 行 / 3,061,466 字节（平均 765KB/行）
D2-2 模板数据区              35 行
D2-2 真库行数                1260 行           ⇒ materialize 单张要插 1200+ 行
离线剖析（push_html_to_excel） 10 行 6.7s / 50 行 8.8s / 200 行 15.9s / 729 行 59.3s（超线性）
统一 materialize 历史         HTTP >300s 超时
```

本 spec 的做法是**立门不优化**：每接一张就实测整册 materialize 耗时，超软上限即停并转性能
spec。理由是归因 —— 把「引擎声明化」与「性能优化」混在一起，出问题时分不清是声明错了还是
优化错了。

两条不得违反的判据纪律：
1. `BASELINE_EXTRACT_CACHE` 的命中语义不变（键 `{contract_id}:{artifact_sha256}`，内容寻址
   天然失效）。受管 sheet 增加不改变该键。
2. 🔴 **不得**用 `store_field_count` 与 `field_count` 作差推断数据丢失。D4 spec 已因此误判一次
   （1648 vs 992 被当成「store 被吞了 656 个业务值」，实际是 overlay 的并集语义）。要判就读
   真实键集。

## 关键裁决

### 裁决 E1：只扩第一册，后两册另立

依据是三条硬事实叠加：entry↔template blob 1:1、`_entry_id` 从宿主派生 + 碰撞检查、D2 的 16 张
sheet 全在一个宿主。三个替代方案（改 entry_id 规则 / 合册 / 现在建宿主）各有明确否掉理由
（见 Architecture 表）。

### 裁决 E2（**2026-09-25 复盘已反转**）：D2-3 是三受管区，与 D1-4 同型

实测 `useD2BadDebt.ts:64-68`：

```ts
const CATEGORY_KEYS: Record<string, string> = {
  'individual':    'D2-bd-individual-rows',
  'aging':         'D2-bd-aging-rows',
  'customer-type': 'D2-bd-customer-rows',
}
```

⇒ **三个独立 store 键、三个受管区**，与 D1-4（`D1-bd-individual-rows` / `-portfolio-rows` /
`-notetype-rows`）同型。binding 数 **1→4**。

🔴 **首版裁决写成了相反结论**（「单一 store 载荷内的 category 字段、不拆受管区」）并据此立了
反向判据。根因：首轮 grep 用 `^const \w*(STORAGE_KEY|_KEY|KEYS)\w*\s*=\s*'`，而这三个键是
**dict 字面量的值**（`= {` 而非 `= '`）⇒ 模式匹配不到，我据不完整事实下了裁决。
**教训：store 键的 grep 必须同时覆盖 `= '常量'` 与 `= { ...: '值' }` 两种形态**，宁可用
`'D2-[a-z0-9-]+-rows'` 这种按值匹配的模式兜。

连带三个后果（首版全部漏了）：
1. D2-3 成为**同 sheet 多受管区** ⇒ 走兄弟 Table ref 位移路径 ⇒ 依赖 D1 spec 任务 24
   （位移判据清单改按 provider 参数化）先落，否则三区不进自动覆盖清单
2. binding 序列从 `1→2→3→4` 改为 `1→4→5→6`
3. 三个键有 **5 处下游消费方**（需求 1.7），零回归判据必须覆盖它们

### 裁决 E3：D2-1 走 `AdjudicationSheetSpec` 且以参数表达与 D1-1 的差异

`sections`（1 vs 3）+ `row_mode`（`fixed_rows` vs `dynamic_identity`）两个维度参数化。
**不得**在引擎里加 `if is_d1` / `if is_d2` —— 那会让 D1 spec 的框架层 AST 卡点直接打红
（需求 7.1：框架层零 wp_code 分支）。

### 裁决 E4：删代码不删数据

`useD2VoucherCheck.ts` 零消费方 ⇒ 删（310 行）。但旧套两个 store 键的数据（87B + 332B，
实测为空骨架/默认值）**保留读兼容**。「数据是空骨架」是一个判断，不是删数据的授权 ——
物理删除要走独立的数据迁移评估。

### 裁决 E5：非受管 sheet 保持禁用，不引入 legacy 假双向

D1 的做法是落 `GtOnlyOfficeSheet`（`migration_state = legacy_fake_bidirectional`，OO 改动
不合并回 store、切回即丢）。D2 现状是直接禁用 + 中文原因，这**更正确**，不能为了「对齐 D1」
而退化。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 前置（D1 框架层 / `_protection`）未入库 | 阶段 0 fail-closed 停工，判定用 `git show HEAD:` | 需求 7；D1 spec 曾因读工作树误登记 |
| specs 数 ≠ 契约 sheets 数 | attach fail-closed + 精确报差集 | D4-35 事故（7 vs 8 打挂整个 entry） |
| D2-3 被误声明成三受管区 | 对齐计数守卫打红 | 裁决 E2 |
| 整册 materialize 超软上限 | 显式 domain error + 停止接入 | 需求 5.2 |
| 非受管 sheet 切在线编辑 | 禁用 + 中文原因（不静默、不落 legacy） | 裁决 E5 |
| 旧套 store 键读不到 | 走读兼容返回空骨架，不抛 | 裁决 E4 |

## Data Models

本 spec **不新增**任何数据模型类型 —— 三个 spec 类（`RowTableSheetSpec` /
`AdjudicationSheetSpec` / `StoreItemSpec`）、四种 store 形态（`rows`/`dict`/`fixed_text`/
`dedicated`）、行模型（`rowId`/`rowType`/`source`）全部由 D1 spec 定义。这里只**实例化**。

### 本 spec 涉及的 store 载荷（落库形态不变）

| sheet | store item | kind | 行模型要点 |
|---|---|---|---|
| 明细表D2-2（已接） | `D2-detail-rows` | `rows` | 39 列 + **三套 nested 账龄**（`agingPrior`/`agingCurrent`/`agingAudited`）；真库 4 行 / 3.06MB |
| 坏账准备明细表D2-3 | **三个键**：`D2-bd-individual-rows` / `D2-bd-aging-rows` / `D2-bd-customer-rows` | `rows` ×3 | **三受管区**（裁决 E2，已反转）；`isSubRow`→`rowType=dynamic`、分类汇总行→`summary`；**5 处下游消费方**见需求 1.7 |
| 调整分录汇总表D2-4 | `D2-entry-rows` | `rows` | `isPushedToAdjTable` 为 **store-only 不入受管格** |
| 审定表D2-1 | `D2-adj-{rowKey}-{field}`（per-cell 锚点） | — | 4 行写死（`individual`/`aging`/`customer-type`/`total`，末行 `rowType=summary`）；`isFromSumif` 归一到 `source` |

### 保留读兼容、不物理删除的旧载荷（裁决 E4）

```
D2-voucher-params     1 行 87B   {"method":"随机","populationSize":0,"sampleSize":0,…}   空骨架
D2-voucher-samples    1 行 332B  [{rowId:"vc-…",seq:1,voucherNo:"",amount:0,…}]          空骨架
```

同一 wp `e2c95d10`。代码侧 `useD2VoucherCheck.ts` 删除，store 键读兼容保留。

## Correctness Properties

判据面。每条都必须被变异打红，否则重写而非保留（需求 8.1）。

### Property 1: D2-2 的 golden digest 在 D2 扩容前后不变

**Validates: Requirements 6.1**　变异：D2-3 声明串进 D2-2 的 `table_key`。

### Property 2: 其余 7 个 contract 的 digest 不变

**Validates: Requirements 6.2**　变异：动 provider 共享常量。

### Property 3: D2-3 的 `formula_mask` ≡ `E`/`K`/`N` 三列 × 数据行区间

**Validates: Requirements 1.2**　mask 由引擎 property 现算。变异：`formula_columns` 少一列。

### Property 4: D2-3 是**三**受管区，binding 数 1→4，且三键各自读回等值

**Validates: Requirements 1.3, 1.6**　钉住裁决 E2（已反转）：三个独立 store 键
`D2-bd-individual-rows` / `-aging-rows` / `-customer-rows`，与 D1-4 同型。
变异：只声明一个受管区（首版的错法）⇒ 另两键的数据在 OO 里不可见、回写丢失，必红。

### Property 4b: D2-3 三个键的 5 处下游消费方在 OO 回写后仍正确重算

**Validates: Requirements 1.7**　`useD2Adjudication.eclCrossValidation`(:618) /
`useD2Ecl.d3BadDebtTotal`(:308) / `useD2WriteoffCheck.reversalConsistencyWarning`(:135-137) /
`useD2DisclosureNote.badDebtSummary`(:481) + `importIndividualFromBadDebt`(:971) /
`useD2CrossSheet`(:199-201)。变异：OO 回写只更新一个键 ⇒ 下游汇总缺一类，必红。
🔴 只验 D2-3 自身读回等值会放过「下游看不到回写」这类缺陷。

### Property 5: D2-4 的 `isPushedToAdjTable` 不出现在受管格集合里

**Validates: Requirements 2.2**　它是平台流程状态而非 Excel 业务列。变异：声明成 editable 列。

### Property 6: D2-1 的 4 行是固定行，无动态 identity 列需求

**Validates: Requirements 3.3**　变异：改成 `row_mode='dynamic_identity'`。

### Property 7: D2-1 逐格 mask 下 6 个金额字段仍判 `editable`

**Validates: Requirements 3.2, 7.2**　依赖 `merge._protection` 格级判定已入库。
变异：把 `_protection` 换回 `column_in_ranges` ⇒ 必红（钉住 D4-1 踩过的坑：6 个声明 editable
的金额字段被整列误判 `read_only_masked_cell`、四态 UI 成死代码）。

### Property 8: 上游变化后纯派生格不得被标成人工覆盖

**Validates: Requirements 3.4**　反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数必须
为 0。🔴 另须有一条**跑同步器**的判据 —— D4 spec 有 13 条纯函数判据全绿而生产坏掉（同步器把
显示值当派生值写回 snap ⇒ 覆盖标记自我擦除）。变异：用 `stored ≠ derived` 错法。

### Property 9: `isFromSumif` 归一到 `source` 后语义有定义

**Validates: Requirements 3.5**　变异：保留布尔标记。

### Property 10: 删 `useD2VoucherCheck` 后全仓零引用且测试全绿

**Validates: Requirements 4.1, 4.5**　变异：保留一处 import ⇒ 判据红。

### Property 11: 删死降级路径后 D2-2 主路径（读 `D2-detail-rows` JSON）逐值不变

**Validates: Requirements 4.3**　变异：删掉主路径 ⇒ 必红。

### Property 12: 整册 materialize 200 + verify 全绿（4 受管 sheet）

**Validates: Requirements 1.5, 2.4**　🔴 判据必须**穿过** `verify_unmanaged_regions`。
变异：去掉兄弟 Table ref 位移。

### Property 13: `BASELINE_EXTRACT_CACHE` 同 substrate 二次请求命中

**Validates: Requirements 5.3**　键 `{contract_id}:{artifact_sha256}` 内容寻址天然失效。
变异：把键改成含时间戳。

### Property 14: `capability` / `flushHtml` 从 Ref 读取而非构造时字面量

**Validates: Requirements 6.4**　变异：改回字面量 ⇒ 切 sheet 后 capability 不变，必红。

### Property 15: 连续切两张受管 sheet 都能进 OO

**Validates: Requirements 6.3**　同 entryId 不同子 sheet 的 `store-projection`/`materialize`
是同一 URL，http.ts 去重层会 abort 在飞请求（桥内已处理）。变异：去掉桥内同 URL abort 识别。

### Property 16: 非受管 sheet 禁用 + 显式中文原因

**Validates: Requirements 6.5**　变异：改成落 legacy `GtOnlyOfficeSheet` ⇒ 必红（那条
`migration_state=legacy_fake_bidirectional`，OO 改动不合并回 store、切回即丢）。

## Testing Strategy

**红判据先行。** 阶段 0 先取 D2-2 的 golden digest 基线（必绿）+ 打红 Q4/Q7
（Q4：现状只有 1 个受管区，声明三区会红；Q7：若 `_protection` 未入库则现在就红，正好作为
前置门的可执行判据）。

**禁止两端各自 mock。** 真链必须：真 contract + 真 provider + 真 materialize
（`build_workbook_bytes`）+ 真 extract + 真 merge + **穿过 `verify_unmanaged_regions`**。
D4 spec 的教训：判据只覆盖 adapter 两方法 ⇒「判据绿而生产 500」。

**真栈判据的三条已知陷阱**（D4 spec 踩过，本 spec 直接沿用结论）：
1. 不能用 `page.on('response')` 判 callback —— OO 容器直接 POST 后端不经浏览器，须读后端
   `working_paper_sync_operation.application_bound_at`
2. 不能用内部 `asc_*` API 写格 —— 未经协同通道 ⇒ forcesave 回 `cs_error=4` no_changes、
   operation 直接 rejected。只有真实键盘输入（名称框 `#ce-cell-name` → `keyboard.type` → Enter）
   才产生 changes
3. 模式切换条选择器**须实测确认** —— D4-1 是 `.d4-tab-adjudication .sync-mode-bar`、D4-2 是
   `.d4-mode-toolbar`，D2 的须现场读，照抄会找不到元素

**零回归分母要诚实。** 前端全量 vitest 现有既存失败（L2/L4 披露、K 系附注、G7 列对齐、
F3/F5 集成等）与本 spec 改动文件无交集 ⇒ 不计入分母，但需在证据里列明归因。

## 不在本 spec 范围

见 requirements §不在本 spec 范围。摘要：**第二册**（D2-5 分析表）与**第三册**（D2-6~D2-13
检查表，含 D2-7 凭证抽查双视图+OCR / D2-8 段落+两行表 / D2-10 ECL 三行表含连乘 / D2-11 /
D2-12 / D2-13 问卷 / D2-9）需各建独立宿主，登记为 `d2-analysis-and-inspection-sync-hosts`；
D2A 程序表与四张附注披露 sheet；旧套 store 键物理删除；性能根因优化；`entry_id` 派生规则改造；
权威模板合册。

## 顺带发现（登记，不在本 spec 处理）

1. **四张附注披露 sheet 跨册重复**：第一册有 4 张（`附注披露信息(上市公司）D2-1` /
   `（国企）D2-1` / `(上市公司)` / `(国企)`，后两张无 `D2-1` 后缀），第二册与第三册各有前 2 张
   的同名副本。⇒ 同一张披露表存在**多个物理载体**，若将来接披露，须先裁定哪个是权威。
2. **D2 sheet 名带 `D2-1` 后缀的披露表是命名陷阱**：`d2Constants.ts` 已有注释记录 —— 源模板
   tab 名形如 `附注披露信息（国企）D2-1`，若先跑 `/D2(?:-\d+)?[A-Z]?$/` 会被判成 `D2-1`
   （审定表），披露组件永远挂不上（2026-07-30 Playwright 实测过）。本 spec 接 D2-1 审定表时
   须确认该正则的分派不受影响。
3. **每册都有 `GT_Custom` sheet**（8 行 × 2 列，0 公式）—— 平台注入区，不接但须确认
   instrumentation 不误把它算进受管清单。

## 上游锚定（2026-09-25 第三轮复盘补：首版缺这一节）

🔴 **本 spec 是 umbrella spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的
Task 46「逐一迁移 D 循环 Excel 独立 entry」的下游 lane spec**，与 D4 lane 同型。首版零引用该
umbrella 与其已冻结的 D 循环 slice，属 spec 卫生缺陷。

| 产物 | 位置 | 已冻结内容 |
|---|---|---|
| D 循环 manifest slice | `backend/data/workpaper_sync_d_cycle_manifest_slice.json`（1137 行） | Task 46 冻结的 7 个 D 循环独立 entry 逐项裁决 |
| umbrella Property 面 | umbrella design.md（1993 行） | Property 1–71；Task 46 声明验证 Property 20 / 21 / 28 / 69 / 70 |

### ✅ slice 实测支持本 spec 的前提：D2 是 7 家里唯一另一个已注册 adapter 的

```
xlsx/gt-d2-accounts-receivable    adapter_registered   adapter=d2.receivable_detail   mount_count=1
xlsx/gt-d4-operating-revenue      adapter_registered   adapter=d4.revenue_detail
其余五家（D1/D3/D5/D6/D7）        legacy_fake_bidirectional   adapter=None
```

⇒ **D2 与 D4 是 7 家里唯一两个 adapter 真注册的循环** ⇒ 本 spec 是少数「真栈判据能跑起来」的
D 类 spec，D1/D3/D5/D6/D7 那四个 spec 的真栈判据都卡在 `no_registered_sync_adapter`。
这一事实提升本 spec 的优先级：**它能提供 D 类唯一可跑通的扩容样本**（D4 已有 30 受管 sheet，
但 D4 走 bugfix spec 不是扩容 spec）。

⚠️ 但 slice 的 `adapter_registered` 与 umbrella 的 **BP-61-1** 并不矛盾：BP-61-1 说的是
**published representation 供给平台级为 0**（186 个 planned entry 一个都注册不上）。二者口径不同
—— slice 记的是 manifest 侧的 `migration_state`/`adapter_id` 声明，BP-61-1 记的是库里
`working_paper_content_representation` 的真实行数。⇒ 本 spec 真栈段开工前须**实测确认** D2 的
`register_from_manifest()` 当前是否真注册成功（D3 spec 裁决 F5 实测「只注册 `{d2,d4,g7,h1}`」
支持 slice 口径），**不得只读 slice 就宣称可跑**。

### Property 编号必须 spec-scoped

umbrella 自己踩过同号不同义的坑（Task 61 附注：全局 `BP-16`~`BP-22` 被 Tasks 60/63/64 重复占用，
修法是 task-scoped 前缀 `BP-61-x` + `re.fullmatch` 锁死）。⇒ 本 spec 的 `Property N` /
`Q{N}` 一律读作 **`D2-P{N}`**，引用上游须写全 `umbrella Property N`。
