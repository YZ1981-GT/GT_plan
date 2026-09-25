# Design Document

## Overview

E1 货币资金从 **legacy 假双向** 接成真双向：先打通首张 canary（E1-2 现金明细），再扩到第一册内
可表达的 sheet，并对 E1-5 调整分录做可行性核。

🔴 **本 spec 与 D 类 spec 的差异只有一级（复盘修正）**：首版写「D 类都是已接 1 张扩到 N 张」，
查 D 循环 slice 实测推翻 —— 7 个 D 循环独立 entry 里**只有 D2/D4 真注册了 adapter**，
D1/D3/D5/D6/D7 均 `migration_state=legacy_fake_bidirectional` + `adapter_id=None` +
`unverifiable_reasons` 含 `no_registered_sync_adapter`，**与 E1 同态**。

真实差异只有 **provider 文件存在与否**：D1/D3/D5/D6/D7 有 provider（902/847/781/849/844 行）
且已声明受管 sheet，卡在发布链；E1 连 provider 都没有。⇒ 本 spec 的 canary 链路比它们多一步
（建 provider），其后的**契约发布链五环 + adapter 注册是六个循环共同的缺口**，且该缺口是
**平台级**的（umbrella BP-61-1：186 个 planned entry 一个都注册不上）。

## 上游锚定（复盘补：首版缺这一节）

本 spec 不是新开话题，而是 umbrella spec **`workpaper-html-onlyoffice-bidirectional-writeback-closure`
Task 47「逐一迁移 E 循环 Excel 独立 entry」**的下游 lane spec —— 与 D4 lane 在该 umbrella
的 `2026-09-22 D4 lane 登记` 附注里的关系同型。首版漏了这节，导致重复推导已冻结的事实，
并推出了**错的** `static_region` 判定。

### 已存在的上游产物（复用，不重造）

| 产物 | 位置 | 已冻结的内容 |
|---|---|---|
| E 循环 manifest slice | `backend/data/workpaper_sync_e_cycle_manifest_slice.json`（322 行） | `entry_id` / `migration_state` / 五个 null 供给位 / `scenario_profile_id` / `manifest_legacy_reasons` 三条 / `verification_state=UNVERIFIABLE` + 五条 `unverifiable_reasons` / `not_single_html_because` / `not_bidirectional_because` |
| D 循环 slice（姊妹） | `backend/data/workpaper_sync_d_cycle_manifest_slice.json`（1137 行） | 四个 D 类 spec 的同源上游 |
| 行身份守卫 | `composables/__tests__/e1SyncEntryRowIdentity.spec.ts` | umbrella Property 23「动态行身份不使用下标」的单点守卫，真跑 `useE1BankDetail` |
| variant 金额守卫 | `composables/__tests__/e1BankVariantIntegrity.spec.ts` | 本位币六列跨 `rmb`/`multi` 守恒，防 `recalcRow` 由原币反推抹零 |
| 迁移范式 | `backend/data/workpaper_sync_migration_paradigm.json` | slice 的 `paradigm_ref` |

⇒ 需求 1 的 `assert_entry_selectable` 四条事实**不需要重新调研**，slice 里已冻结；本 spec 的
Task 1 改为**核对 slice 与现状是否仍一致**（slice 冻结于 Task 47 执行时，可能已过期）。

### 🔴 结构性前置：E1 的 `parent_duplicate_count = 0`，而 D4 是 31

slice 原文：

> E1 的 30+ 子 sheet 由同一个宿主 `GtE1MonetaryFund.vue` 按 `currentSheet` 分发到结构化子组件，
> 子组件里没有第二个 `GtOnlyOfficeSheet` 挂载点 ⇒ manifest 里不产生 `parent_duplicate` 条目
> （与 D4 的 31 条 `parent_duplicate` 形态不同）。

这不是统计差异，是**接入机制差异**：D4 每个受管 sheet 在 manifest 里有自己的条目，E1 一条都没有。
⇒ 「声明层 +1 per sheet」在 E1 上**不足以**让 manifest 扫出受管 sheet。canary 段必须先裁决走哪条路：

```
路线 α  仿 D4：子组件各挂 GtOnlyOfficeSheet ⇒ manifest 产出 parent_duplicate 条目
        代价：改 30+ 子组件；但与 D4 范式一致，工具链全部复用
路线 β  单挂载点 + sheet 维度 entry 扩展 ⇒ 不改子组件，改 manifest 生成规则
        代价：manifest 生成器与 _entry_id 派生规则要支持「一宿主多 sheet entry」，
              与裁决 H2「一宿主恰一 entry」正面冲突 ⇒ 需先解 H2
```

**本 spec 取路线 α**，理由：β 要动 `_entry_id` 派生规则（持久化键，裁决 H2 已否决过同类改动），
且会让 E1 成为全平台唯一的例外形态；α 的改动面大但全在前端声明层，且十一个循环已验证。

### Property 编号必须 spec-scoped，不得撞 umbrella 全局编号

umbrella 有 Property 1–71 与 BP-10~BP-22，且**它自己踩过同号不同义的坑**：其 Task 61 附注记录
「全局 `BP-16`~`BP-22` 已被 Tasks 60/63/64 各自重复占用、同号不同义」，修法是改用 task-scoped
前缀 `BP-61-x` 并用 `re.fullmatch(r"BP-61-\d+")` 锁死。

⇒ 本 spec 的 `Property N` 一律读作 **`E1-P{N}`**，引用 umbrella 判据时必须写全
`umbrella Property 23`。已知冲突：本 spec Property 3 与 umbrella Property 3 同号不同义；
本 spec 的行身份判据对应 umbrella Property 23（**已有守卫，不重写**）。

## Architecture

### 5 册约束 ⇒ 只覆盖第一册（与 D2 三册同款）

```
entry ↔ template blob 是 1:1；_entry_id 从宿主文件派生 + seen_entry_ids 碰撞检查
      ⇒ 一宿主恰一 entry
E1 的 56 张 sheet 分散在 5 册，全在同一宿主 GtE1MonetaryFund.vue 按 tab 分流
      ⇒ 只能覆盖 1 册
```

```
第 1 册  E1-1至E1-11 …（Leap-常规程序）.xlsx        16 sheets  ← 本 spec
         ├ 底稿目录 / E1A 程序表 / 披露×2              不接
         ├ 货币资金审定表E1-1        47r×10c/193f      ✅ AdjudicationSheetSpec（密度 41%）
         ├ 现金明细表E1-2            34r×22c/38f       ✅ 首张 canary
         ├ 银行存款明细E1-3 ×2       92r×28c/185f
         │                          89r×41c/567f      🔍 同编号双 sheet，先裁决
         ├ 数字货币明细表E1-4        22r×17c/52f       ✅
         ├ 调整分录汇总E1-5          26r×10c/7f        🔍 可行性核（第八张同型）
         ├ 银行存款余额调节表E1-6    56r×17c/14f       ✅ 形态待判
         ├ 库存现金盘点E1-7/E1-8     67r×9c/27f
         │                          78r×12c/48f       ✅ 行表（E1-cash-count-{rmb|fx}-rows）
         ├ 银行存单盘点表E1-9        34r×15c/7f        ✅ 行表（E1-cash-count-cert-rows）
         ├ 账户清单核对表E1-10       37r×12c/7f        ✅ 行表 + OCR（E1-account-list-rows）
         └ 银行账户情况承诺E1-11     31r×7c/7f         ✅ **唯一 static_region 候选**（零 rows 键）
         + GT_Custom                                  不接

第 2~5 册  40 张                                      ❌ 需新宿主，另立
```

### canary 链路（本 spec 前半段，D 类 spec 没有这段）

```
① assert_entry_selectable  真 manifest + 真 finder 核四条事实 + 零回退
     实测已满足三条：entry 存在 / independent=true /
     profile == xlsx.editable.shared.single.room_service_wired.v1（与 D1/D2/D3 同型）
     待核第四条：wp_code 落点
② provider 从零建   phase5_e1_monetary_fund.py（照 phase5_d1/d3 同构）
③ 契约发布          build_contract_payload → 生成器 --apply
                    → assert_contract_file_matches_source
④ 发布链            approved bundle → published representation → entry_state
⑤ adapter 注册      register_from_manifest() 真注册
     ⇒ migrationState: legacy_fake_bidirectional → adapter_registered
     ⇒ reasonCodes 三条全消（template_only_open / no_durable_forcesave_ack / missing_adapter）
⑥ 宿主接桥          useWorkpaperSyncBridge + WorkpaperSyncEditorHost，
                    保留 legacy GtOnlyOfficeSheet 给未接 sheet（D1 宿主同款 v-if/v-else-if）
⑦ §9.6 三谓词       confirm 200 / forcesave cs_error=0 / store_mirrored + marker_visible
```

### 接入顺序（形态驱动，不是编号驱动）

```
1 (canary E1-2 现金明细)              行表，38f，独立键，零 OCR，零跨 sheet 取数
  → 2   E1-4 数字货币（22r 最小行表）  验「第二张复用框架层零改动」
  → 3   E1-11 账户承诺                 唯一 static_region，验第二种 BindingKind
  → 4   E1-6 余额调节表
  → 7   E1-7 / E1-8 / E1-9            一次三张，验 useE1CashCount variant 参数化
  → 8   E1-10 账户清单                 首次遭遇 OCR 冲突源（裁决 H7）
  → 9   E1-3                          双 sheet 共享键（裁决 H4）+ 567 公式
  → 10  E1-1 审定表                    per-cell + 跨 sheet 聚合 + 跨册取数 + TB 发布门
  —     E1-5 可行性核，不计入
```

🔴 **本顺序是复盘修正后的结果，原顺序基于错误的形态判定**。首版把 E1-9/E1-10/E1-11 三张一起
排在 canary 之后第二位，理由是「各只 7 个公式 ⇒ `static_region` 强命中」。实证推翻其中两张：

```
E1-9  存单盘点   E1TabCertificateCount.vue(564) + useE1CashCount(variant='cert')
                 键 E1-cash-count-cert-rows，addRow/删行 ×4   ⇒ 动态行表
E1-10 账户清单   E1TabAccountList.vue(681) + useE1AccountList(340)
                 键 E1-account-list-rows，另读 E1-bank-detail-rows（跨 sheet）
                 + E1-account-commit-snapshot（与 E1-11 联动），OCR 提及 ×43   ⇒ 动态行表
E1-11 账户承诺   E1TabAccountCommitment.vue(700)，**零 rows 键**
                 键 E1-account-commit / -check-summary，OCR ×43   ⇒ static_region 候选
```

⇒ **模板公式数少**只说明模板里公式少，**不说明**前端是静态区域。形态判定必须走前端实证
（store 键 + addRow/删行信号 + composable 归属），这是裁决 F2「按值 grep 禁推演」的适用面扩展，
见裁决 H8。

## Components and Interfaces

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_e1_monetary_fund.py        循环层（**从零新建**）：ENTRY_ID / 模板路径 /
                                    sheet 清单 / 灰度开关 / assert_entry_selectable
  phase5_e1_02_cash_detail.py       ✅ canary  RowTableSheetSpec  E1-cash-detail-rows
  phase5_e1_04_digital.py           ✅ RowTableSheetSpec  E1-digital-rows
  phase5_e1_11_commitment.py        ✅ StaticRegionSheetSpec（唯一一张，零 rows 键）
  phase5_e1_06_reconciliation.py    ✅ RowTableSheetSpec  E1-reconciliation-rows
  phase5_e1_07_08_09_cash_count.py  ✅ RowTableSheetSpec ×3（variant 参数化，见下）
  phase5_e1_10_account_list.py      ✅ RowTableSheetSpec  E1-account-list-rows（OCR 冲突）
  phase5_e1_03_bank_detail.py       ✅ 待裁决双 sheet  E1-bank-detail-rows
  phase5_e1_01_adjudication.py      ✅ AdjudicationSheetSpec（193 公式逐格 + 跨册）
```

🔴 **E1-7/8/9 合一个声明文件**，因为三张共享 `useE1CashCount`（470 行）且只差 `variant`
参数 —— 与 D5/D6/D7 共享 33 个同名函数、只差 `aging_layout` 一参是同一范式。三张的
`RowTableSheetSpec` 只应差 `variant` 与列集，不得复制三份。

### 🔴 `store_item_id` **四种**命名风格并存，必须逐个实测

```
① 语义命名     E1-cash-detail-rows / E1-bank-detail-rows / E1-digital-rows
               E1-adjustment-rows / E1-reconciliation-rows / E1-account-list-rows
② 编号嵌套     E1-ipo-E1-26-rows … E1-ipo-E1-32-rows   ← 键名里嵌了两次 E1（第 4 册）
③ 模板化       E1-cash-count-${variant}-rows            variant ∈ rmb|fx|cert
               → E1-cash-count-rmb-rows / -fx-rows / -cert-rows
               副键 ${storageKey}-summary（E1-7/E1-8 的结转 summary，cert 无）
④ 无连字符     E1-cashcount-elements-${variant}         ← 注意是 cashcount 不是 cash-count
               E1-cashcount-audit-note-${variant}
               E1-cashcount-audit-conclusion-${variant}
   legacy 兜底 E1-cashcount-fx-summary-fx               ← 双 -fx 后缀，历史键，仍在读
```

⇒ 同一张底稿（E1-8）上 `E1-cash-count-fx-rows` 与 `E1-cashcount-audit-note-fx` **两种风格并存**，
且 `cash-count` / `cashcount` 只差一个连字符。按 `E1-{n}-rows` 或按任一单一风格推演都会**全错**。

本 spec 沿用 D3 裁决 F2，该裁决已有**六次事故背书**：D2-3 三键 / D1-15 双键 / D1-13 双键 /
D3 语义缩写 / D567 三处必错 / **E1 四风格并存 + cash-count｜cashcount 一字之差**。
Property 2 专项钉住。

## Data Models

本 spec **不新增**任何数据模型类型 —— 声明类、store 形态、行模型、形态谱系三维全部由上游
D1 spec 定义。涉及的 store 载荷（第一册范围内）：

| sheet | store 键 | 形态候选 | 受管区 | 写入方 |
|---|---|---|---|---|
| E1-2（canary） | `E1-cash-detail-rows` | `rows` / `excel_table` | 1 | `useE1CashDetail`(354) |
| E1-4 | `E1-digital-rows` | `rows` | 1 | `E1TabDigitalCurrency`(661) |
| E1-11 | `E1-account-commit` + `-check-summary` | **`static_region`**（零 rows 键） | 1 | `E1TabAccountCommitment`(700) |
| E1-6 | `E1-reconciliation-rows` | `rows` | 1 | `useE1Reconciliation`(392) |
| E1-7 | `E1-cash-count-rmb-rows` + `-summary` | `rows` | 1 | `useE1CashCount`(534, variant=rmb) |
| E1-8 | `E1-cash-count-fx-rows` + `-summary` | `rows` | 1 | 同上 variant=fx（+legacy 兜底键） |
| E1-9 | `E1-cash-count-cert-rows` + `E1-cert-signatures` | `rows` | 1 | 同上 variant=cert |
| E1-10 | `E1-account-list-rows` + `E1-account-commit-snapshot` | `rows` + OCR | 1 | `useE1AccountList`(340) |
| E1-3 | `E1-bank-detail-rows`（**两 variant 共用**） | `rows` | 1 或 2 | `useE1BankDetail`(413) |
| E1-1 | **per-cell**：`E1-adj-*` / `E1-adj-total-*` / `E1-adjustment-by-item-*` | `AdjudicationSheetSpec` | 逐格 | `useE1Adjudication`(725) |
| E1-5 | `E1-adjustment-rows` | hub store | 🔍 核 | `useE1Adjustment`(382) |

**E1-1 实测已不是「per-cell 候选」而是 per-cell 确证**，且是五循环审定表里唯一三重形态叠加的：

```
per-cell 键        E1-adj-tb-amount-opening / -ending / E1-adj-diff-note / E1-adj-total-note
                   E1-adj-accrued_interest-opening-unadj   ← 编号+字段+口径三段拼接
槽位驱动           E1TabAdjudication.vue 的 E1_SLOT_ORDER 常量定顺序
跨 sheet 聚合      E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited  6 键
                   ← 从 E1-3 的三个分组小计取数（useE1BankDetail:80-90）
跨册取数           E1-accrued-interest-rows  ← E1-20 应计利息测算在**第 3 册**（检查.xlsx）
TB 发布门          data-testid="e1-publish-tb" → publishToTb（裁决 H9）
```

⇒ E1-1 受管时，其 per-cell 值有三个来源（本 sheet 人工 / E1-3 聚合 / 第 3 册跨册），
`AdjudicationSheetSpec` 必须能表达「派生格不可由 OO 侧直接写」，否则 OO 回写会覆盖聚合结果。

Task 1 必须 grep 补全每个键的**下游 computed 消费方**（上游 P18 教训：只验该 sheet 自身读回等值
会放过「下游看不到回写」）。已知 `e1RestrictedScope.ts` 读 `E1-bank-detail-rows`、
`useE1AccountList` 读它与 `E1-account-list-rows`。

## 关键裁决

### 裁决 H1：E1 是 canary 不是扩容，前半段必须走完整发布链

D 类四个 spec 都能从「已接 1 张」起步；E1 的 `missing_adapter` 意味着连 adapter 都没有。
⇒ 需求 1 的七条 AC 是**后续全部需求的硬前置**，canary 未通之前不得声明第二张受管 sheet
（照 `d-cycle-sheet-bidirectional-expansion` Wave 0→1 的顺序纪律）。

### 裁决 H2：只覆盖第一册；后四册需新宿主，另立

5 册 / 56 sheets，而 `entry ↔ template blob` 1:1 + 一宿主一 entry。三个替代方案与 D2 spec
裁决 E1 同样被否：改 `_entry_id` 派生规则（它是持久化键）/ 合册（权威模板是方法论产物）/
现在建四个新宿主（跨前端路由 + registry + manifest 生成 + 四条完整发布链，改动面过大）。

### 裁决 H3（复盘已修正）：接入顺序形态驱动，但只有 E1-11 是 `static_region`

**首版裁决错误，此处保留错法与纠正以防复发。**

```
首版（错）  E1-9/E1-10/E1-11 各只 7 个公式 ⇒ 三张全是 static_region 强命中
            ⇒ 排在 canary 之后第二位，受管区 1→4 且绕开整条位移链
实证（对）  E1-9  → useE1CashCount(variant=cert) + addRow×4  ⇒ 动态行表
            E1-10 → useE1AccountList + 跨 sheet 读 + OCR×43  ⇒ 动态行表
            E1-11 → 零 rows 键，仅 dict/文本                 ⇒ static_region（唯一）
```

⇒ 低风险跳板只剩一张。修正后的顺序把「验证第二张复用框架层零改动」交给 **E1-4**（22r 最小行表、
独立键、零 OCR、零跨 sheet），把 `static_region` 第二种 `BindingKind` 的首次验证交给 **E1-11**。

🔴 **纠正的不是三个 sheet 的归类，而是判定方法**：模板公式数是 xlsx 侧的几何量，`BindingKind`
取决于**前端是否有动态行**。两者无因果关系。见裁决 H8。

### 裁决 H8（复盘新增）：「禁推演」铁律适用面从**键名**扩展到**形态**

裁决 F2 原文只约束 `store_item_id`「逐个按值 grep，禁止按编号推演」。本轮 E1-9/E1-10 误判证明
同一类错误会换个维度复发：键名走了实证，**形态**却走了几何推演（7 公式 ⇒ static_region）。

⇒ 铁律扩展为三项**都**必须前端实证，缺一即 fail-closed：

| 维度 | 实证判据 | 禁止的推演源 |
|---|---|---|
| `store_item_id` | 按**值** grep 字面量与模板拼接 | 底稿编号、同循环邻居的键 |
| `BindingKind` | store 键是否存在 + `addRow`/`removeRow` 信号 + composable 归属 | 模板公式数、行数、列数 |
| `row_identity_key` | 真跑一次构造，比对两次输出的 id | 声明里写的类型名 |

第三行沿用仓内既有范式 —— `e1SyncEntryRowIdentity.spec.ts` 头注已写明「判据必须是**真跑一次**…
不做字符串扫源码…改名/改实现只要行为不变就不该打红，行为一变就必须打红」。

### 裁决 H9（复盘新增）：E1-1 受管后 TB 回写仍只经显式发布门

`E1TabAdjudication.vue:336` 有 `data-testid="e1-publish-tb"`，`:338` 绑 `publishToTb` ——
E1-1 是平台 `tb-writeback-explicit-publish-gate` 统一发布门的接入方之一（同型接入方实测遍布
F1~F5 / G1~G14 / H1~H10 / D2）。

⇒ 双向回写**不得**成为 TB 回写的第二条路径。三条红线：

```
① sync 回写路径（extract → merge → store）不得触达 trial_balance 任何列
② OO 侧改 E1-1 审定数 → 只落 checklist_responses 的 per-cell 键，发布仍须人工点 publishToTb
③ 接入 E1-1 前后，两道既有 CI 守卫必须保持绿：
   check_tb_writeback_no_direct_call / check_tb_publish_confirm_gate
```

🔴 这条 D 类四个 spec 都没有，因为 D1/D3/D5/D6/D7 的审定表接入排序都在最后且未触及；D2-1 虽接
`publishToTb`，但 D2 spec 只扩第一册且 D2-1 未进受管清单。E1-1 是第一次「受管 sheet 与 TB 发布门
落在同一张底稿」。

### 裁决 H10（复盘新增）：OCR 是 E1 独有的第二写入方，必须定优先级

实测 OCR 维度分布：

```
e1  7 个 OCR 确认弹窗 / 全目录提及 454 次
    E1AccountListOcrConfirmDialog / E1CommitOcrConfirmDialog / E1CreditOcrConfirmDialog
    E1CutoffOcrConfirmDialog / E1KeyPersonFlowOcrConfirmDialog / E1LargeCheckOcrConfirmDialog
    E1StatementOcrConfirmDialog
d4  0 个弹窗 / 提及 0 次        ← D4 范式完全不含 OCR
d1/d2/d3  0 个弹窗 / 66·46·34 次（零散提及，无确认流）
d5/d6/d7  全 0
```

⇒ E1 的 `-rows` 键有**两个批量写入方**：OCR 确认弹窗（一次写整表）与 OO forcesave 回写。
D4 的冲突模型只有「HTML 单格编辑 vs OO 单格编辑」，**不含批量覆盖**。且 OCR 正好落在要接的
sheet 上（E1-10 账户清单 ×43、E1-11 承诺 ×43）。

本 spec 的裁决：**OCR 确认弹窗在受管 sheet 处于 OO 编辑态时禁用**（与 forcesave 卸编辑态同理），
不做字段级三方合并。理由：OCR 是整表替换语义，字段级合并需要 OCR 侧也有 per-field 溯源，
当前 `E1*OcrConfirmDialog` 只有整表确认粒度 ⇒ 现在做三方合并是在没有溯源的前提下猜。

替代方案否决记录：①「OCR 写入后自动触发 forcesave」—— 会在 OO 未持有编辑态时写脏；
②「以 OCR 为权威覆盖 OO」—— 用户在 OO 里的未保存编辑会静默丢失。

### 裁决 H4（复盘强化）：E1-3 双 sheet 共享同一 store 键但**列集不同**，默认只接一张

`(仅人民币)` 92r×28c/185f 与 `(人民币及外币)` 89r×**41c**/**567f**（全平台单 sheet 公式最多）。
复盘实测把风险从「待裁决」升级为**数据损坏级**：

```
useE1BankDetail.ts:9    type BankDetailVariant = 'rmb' | 'multi'
E1TabBankDetail.vue:35  variant = props.sheetName?.includes('人民币及外币') ? 'multi' : 'rmb'
                        ← variant 由 sheet 名推导，不是独立配置
useE1BankDetail.ts:61   VARIANT_KEY = 'E1-bank-variant'   ← variant 选择本身被持久化
两 variant 共用同一个    E1-bank-detail-rows
但列集刻意不同           rmb 版**不下发**原币列（fxCurrency / fxRate）
                        useE1BankDetail:110 注释明写「两 variant 字段集不同是 AC 1.9 的意图」
```

⇒ 若两张 sheet 同时受管：同一批 store 行要同时满足两个不同列集的投影，而 `rmb` 侧的投影里
根本没有原币列。OO 在 `rmb` sheet 上 forcesave 回写整行 ⇒ `multi` 侧的原币列会被写成缺省/抹零。
**这正是 `e1BankVariantIntegrity.spec.ts` 已在守的缺陷形态**（`recalcRow` 由原币反推导致抹零），
只是那条守卫守的是 HTML 侧跨 variant，OO 回写会从第二个方向引入同一后果。

**裁决：默认只接 `multi`（人民币及外币）一张**，`rmb` 张保持 legacy 并显式登记。理由：
`multi` 是列集超集，`rmb` 是它的投影子集；接超集不会丢列。若将来要两张都接，硬前置是
**先把 `E1-bank-detail-rows` 拆成两个键**（或引入 per-variant 列集投影），而不是让引擎支持
「一 store item 投影到两张列集不同的 sheet」。

🔴 该形态 D 类从未出现过（D4 每 sheet 一个独立 `table_key`），因此不存在可抄的先例。
排序上把 E1-3 放在倒数第二位（仅先于 E1-1），因为 567 公式 + 共享键两个风险叠加。

### 裁决 H5：公式管理不改 —— E1 是范式源头

`GtE1MonetaryFund.vue:256` 的注释与 `D4TabOtherMargin.vue:32` 的「**同 E1 范式**」互证：
公式管理是全局一套（各页 emit `open-formula-manager` → 顶层 `FormulaManagerDialog` →
后端 `wp_formula` 表 + CAS + 审计），**D4 是照 E1 做的**。本 spec 只加两条判据：
①接 sync 后公式管理入口在两种渲染模式下行为一致 ②不新建第二个按钮 owner
（`workpaper-page-formula-toolbar-closure` 需求 1.4/2.4 红线）。

🔴 **两个「公式」概念不在一层，不得混淆**：
```
公式管理        wp_formula 表 / workpaper scope / 全局弹窗   审计师维护的跨底稿取数公式
formula_mask   契约声明 / 逐格或列向区间                    模板里的 Excel 内部公式
```
本 spec 只碰后者。用户表述「参照 D4 实现公式管理」易被读成要改前者 —— 实测 E1 侧已完整，
且 D4 是抄它的。

### 裁决 H6：E1-5 是第八张同型调整分录表，建议去掉统一裁决 spec 的 `d-` 前缀

八张同型（D1-5/D2-4/D3-3/D4-4 已判/D5-3/D6-4/D7-3/**E1-5**），宿主均接
`useAdjustmentCentralSync`。E1-5 的加入证明它**不只是 D 类问题** ⇒ 原建议的
`d-cycle-adjustment-sheets-single-html-adjudication` 应改名为
`cycle-adjustment-sheets-single-html-adjudication`。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 上游框架层 / 形态谱系未入 HEAD | 阶段 0 fail-closed 停工，判定用 `git show HEAD:` | 需求 7.1 |
| `assert_entry_selectable` 四条事实任一不成立 | fail-closed 并精确报哪条不成立 | 需求 1.2；照六家 canary 范式 |
| 发布链任一环缺供给（bundle / representation / entry_state） | `register_from_manifest()` 返回显式 reason，不静默跳过 | 需求 1.4/1.5 |
| `store_item_id` 按编号推演 | Property 2 打红 | 五次事故背书 |
| `static_region` 三张被误判成行表 | Property 3 打红 | 裁决 H3 |
| E1-3 双 sheet 未裁决就声明 | 阶段 fail-closed，先出证据 JSON | 裁决 H4 |
| 公式管理在 OO 模式下弹窗挂不上 | Property 8 打红 | 需求 6.2 |
| 整册 materialize 超软上限 | 显式 domain error + 停止接入 | 需求 8.2 |
| 未接 sheet 切在线编辑 | 保持 legacy 但**显式登记**仍是假双向 | 需求 8.5（缩小范围不掩盖） |

## Correctness Properties

判据面。每条都必须被变异打红，否则重写而非保留（需求 9.1）。

### Property 1: canary 打通后 migrationState 与 reasonCodes 正确变更

**Validates: Requirements 1.5**　`legacy_fake_bidirectional` → `adapter_registered`，三条
reasonCodes（`template_only_open` / `no_durable_forcesave_ack` / `missing_adapter`）全消。
变异：跳过发布链任一环 ⇒ 注册失败、状态不变，必红。

### Property 2: 每个 `store_item_id` 逐字等于按值 grep 实测值

**Validates: Requirements 1.3**　变异：把 `E1-cash-detail-rows` 写成 `E1-2-rows` ⇒ 投影恒空、
回写丢失。🔴 E1 有**三种命名风格**（语义 / 编号嵌套 `E1-ipo-E1-26-rows` / 混合），
按编号推演会全错；该裁决有五次事故背书。

### Property 3: `BindingKind` 取自前端实证，不取自模板公式数

**Validates: Requirements 2.2**　对第一册每张受管 sheet 断言三元组一致：
`(store 键是否存在, addRow/removeRow 信号数, composable 归属)` → `BindingKind`。
实证基线：E1-11 是**唯一** `static_region`（零 rows 键）；E1-9 / E1-10 是动态行表。

变异 ①：把 E1-9 或 E1-10 声明成 `static_region` ⇒ `_plan_static_writes` 绝对坐标直写，
插行后坐标全错，必红。
变异 ②：把判据改成「公式数 < 10 ⇒ static_region」⇒ 三张都会判成 static_region，必红
（这正是首版裁决 H3 的错法，判据必须能打红它自己的历史错误）。
变异 ③：把 E1-11 声明成行表 ⇒ 会走整条位移链（`row_shift` / footer 两门 / minted UUID /
兄弟 Table ref 维护）而它没有 Table，必红。

### Property 16: OCR 确认弹窗在受管 sheet 的 OO 编辑态下禁用

**Validates: Requirements 2.6（复盘新增）**　E1 有 7 个 `E1*OcrConfirmDialog`，是 `-rows` 键的
第二个**批量**写入方（D4 范式零 OCR）。判据：受管 sheet 处于 OO 编辑态时，OCR 确认入口
`disabled` 且中文原因可见。

变异 ①：去掉 disabled ⇒ OCR 整表替换与 OO 未保存编辑同时在飞，必红。
变异 ②：改成「OCR 写入后自动 forcesave」⇒ 在 OO 未持编辑态时写脏，必红。
变异 ③：只在 E1-10 上禁用而漏 E1-11 ⇒ 必红（两张 OCR 提及各 43 次，成对出现）。

### Property 17: E1-1 受管后 TB 回写仍只经 `publishToTb` 显式门

**Validates: Requirements 4.6（复盘新增）**　三条断言：
①sync 回写路径（extract → merge → store）对 `trial_balance` 的写次数为 **0**；
②OO 侧改 E1-1 审定数后，未点 `e1-publish-tb` 前 `trial_balance` 不变；
③两道既有 CI 守卫 `check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate` 保持绿。

变异 ①：让 merge 顺带写 `trial_balance` ⇒ ①③ 同时红。
变异 ②：在 sync 回写里调 `publishToTb` ⇒ ② 红（绕过人工二次确认）。

### Property 18: E1-3 两 variant 的列集差异不被 OO 回写抹掉

**Validates: Requirements 3.6（复盘新增）**　`rmb` 与 `multi` 共用 `E1-bank-detail-rows` 但
`rmb` 不下发原币列。判据：在受管的 `multi` sheet 上 OO 回写一行后，该行原币列
（`fxCurrency`/`fxRate`）与回写前逐字相等（未被缺省值覆盖）。

变异 ①：两张 sheet 都声明受管同一键 ⇒ `rmb` 侧回写抹零原币列，必红。
变异 ②：把投影列集写成两 variant 的交集 ⇒ `multi` 的原币列进不了投影，必红。
🔴 本判据与既有 `e1BankVariantIntegrity.spec.ts` 分工：那条守 HTML 侧跨 variant 的金额守恒，
本条守 **OO 回写方向**引入的同一后果。两者互相独立地红/绿。

### Property 4: §9.6 三谓词 + DB 三谓词

**Validates: Requirements 1.7**　`confirm 200` / `forcesave cs_error=0` /
`store_mirrored`+`marker_visible`；DB 留 op / marker / store 键证据。

### Property 5: E1-3 双 sheet 裁决先于声明，且不改生产代码

**Validates: Requirements 3.1, 3.5**　变异：裁决阶段改了 provider ⇒ 违反诚实边界红线。

### Property 6: E1-1 的 `sections`/`row_mode` 取自实测，非照其他循环推演

**Validates: Requirements 4.3**　五循环审定表形态已证互不相同。变异：照 D1-1 的 3 区声明。

### Property 7: E1-1 逐格 mask（193 公式 / 密度 41%）下受管金额字段仍判 `editable`

**Validates: Requirements 4.2, 7.2**　依赖 `merge._protection` 格级判定已入库。
变异：换回 `column_in_ranges` ⇒ 必红（D4-1 踩过的坑，E1-1 密度更高风险更大）。

### Property 8: 公式管理入口在两种渲染模式下行为一致

**Validates: Requirements 6.2**　结构化视图与在线编辑模式切换后，`open-formula-manager` 事件
仍到达顶层全局 `FormulaManagerDialog`。变异：在 OO 分支里丢掉事件绑定 ⇒ 必红。
🔴 本判据同时钉住「不新建第二个按钮 owner」（需求 6.3）。

### Property 9: 上游变化后纯派生格不得被标成人工覆盖

**Validates: Requirements 4.4**　反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数为 0。
🔴 另须一条**跑同步器**的判据（上游 13 条纯函数判据全绿而生产坏掉的教训）。

### Property 10: 每个 store 键的下游 computed 在 OO 回写后仍正确重算

**Validates: Requirements 2.5**　已知 `e1RestrictedScope.ts` / `useE1AccountList` 读
`E1-bank-detail-rows`；完整清单由 Task 1 grep 补全。变异：回写只更新一个键。

### Property 11: 整册 materialize 200 + verify 全绿（每批次）

**Validates: Requirements 8.1**　🔴 判据必须**穿过** `verify_unmanaged_regions`。
变异：去掉 sibling 受管坐标并入 `extra_managed_coords`。

### Property 12: 其余 10 个 contract 的 golden digest 不变

**Validates: Requirements 8.3**　b60/d1/d2/d3/d4/d5/d6/d7/g7/h1。变异：动共享常量。

### Property 13: 未接 sheet 保持 legacy 且假双向被显式登记

**Validates: Requirements 8.5**　变异：把未接 sheet 也接上桥（半接状态）⇒ 必红。

### Property 14: E1-5 可行性核只产裁决与证据，不改生产代码

**Validates: Requirements 5.3**　变异：核阶段改了 provider。

### Property 15: 前端受管 sheet 集合从 provider 派生 + 两套宿主 gating

**Validates: Requirements 8.6, 8.7**　变异：前端硬编码 sheet 字面量 / 漏登记专用同步 sheet 链
⇒ 工具条叠加冲突（D4-35/D4-13 踩过）。

## Testing Strategy

**红判据先行。** 阶段 0 先打红 Property 1（现状 `legacy_fake_bidirectional` ⇒ 必红）+
Property 2/3（键名与形态未声明 ⇒ 必红）+ Property 8（现状只有 legacy 模式，双模式一致性无从验证），
它们是后续"打通了"的唯一归因依据。

**canary 段禁止跳步。** 发布链五环（contract → bundle → representation → entry_state →
register）任一环缺供给都会让 `register_from_manifest()` 静默不注册。判据须逐环断言产物存在，
**不得**只看最终 `migrationState`。

**禁止两端各自 mock。** 真链必须：真 contract + 真 provider + 真 materialize + 真 extract +
真 merge + **穿过 `verify_unmanaged_regions`**。

**真栈三陷阱沿用上游结论**，且 E1 的模式切换条选择器**须实测**（`GtE1MonetaryFund.vue:24` 有
`<el-segmented>`，与 D4-1 的 `.sync-mode-bar` / D4-2 的 `.d4-mode-toolbar` 都不同）。

**公式管理判据要覆盖两模式。** 这是 E1 独有的一条 —— D 类 spec 都没写，因为它们的宿主没有
公式管理入口（只有 E1/D4 等少数有）。

### 沿用 D4 的批量 e2e 范式（复盘补：首版只写「真栈逐张断言」，未吸收这套）

D4 lane 已交付一套 fixture 驱动的全盘 L2 判据，E1 直接照搬结构而非重新设计：

```
e2e/d4-l2-oo-to-html-all.spec.ts   541 行  全盘逐张：进 OO → 改一格 → forcesave → 验落库 → 回表
e2e/d4-l2-fast-batch.spec.ts       343 行  快批（回归用）
e2e/d4-bidirectional-acceptance.spec.ts    497 行  验收
e2e/fixtures/d4-l2-cases.json      389 行  每 case: code / excel_name / sheet_key / table_key /
                                           edit_col / edit_key / edit_vt / first_data_row / last_data_row
backend/scripts/e2e/seed_d4_l2_empty_sheets.py   509 行
backend/scripts/e2e/seed_d4_publish_e2e.py       395 行
```

E1 对应产物：`e2e/fixtures/e1-l2-cases.json` + `e2e/e1-l2-oo-to-html-all.spec.ts` +
`backend/scripts/e2e/seed_e1_publish_e2e.py`（**E1 的 seed 必须额外解除 `missing_adapter`**，
D4 的 seed 不需要这段，因为 D4 早已注册 adapter）。

必须照搬的四条纪律（全部来自 D4 踩过的坑，写在其 spec 头注里）：

| 纪律 | D4 的原因 |
|---|---|
| **逐张而非批量** | UI forcesave 会卸编辑态；批量多格曾触发 `footer_anchor_drift` / conflict |
| **只改安全目标** | 只改投影里 `\|amount\| > 1` 且 key 不在 `SKIP_KEYS`（`seq`/`index`/`row_no`/`no`/`order`/`month`）的金额格；文本/空数据记 `no_safe_target` 而非硬失败 |
| **API 直打后端** | 走 `http://127.0.0.1:9980` 而非 vite 代理，避免代理中途挂掉导致 `page.request ECONNREFUSED` |
| **七态结果枚举** | `applied_store_ok` / `applied_store_miss` / `no_safe_target` / `type_fail` / `op_error` / `op_timeout` / `enter_fail` —— 区分「引擎错」与「这张没有可安全编辑的格」，否则全盘统计会把后者误报成失败 |

🔴 **E1 需在 fixture 上加两个 D4 没有的字段**：`variant`（E1-3 的 `rmb|multi`、E1-7/8/9 的
`rmb|fx|cert`）与 `ocr_dialog`（该 sheet 是否有 OCR 确认弹窗，用于 Property 16 的禁用断言）。

### E1 目录完成度：38 键全有写入方，零缺陷（与 D567 相反）

`E1TabDirectory.vue` 声明 19 个编号 × `noteKey`/`conclusionKey` = 38 个键，逐键反查写入方实测
**零缺失**（其中 10 个走模板化拼接：`E1-cashcount-*-${variant}` / `E1-credit-*-${variant}` /
`E1-cutoff-*-${variant}`，需按前缀匹配才能查到写入方，按全字符串 grep 会误判成零写入）。

⇒ 本 spec **不需要** D567 spec Task 1 那类「目录读的键零写入点、完成度恒未填」的修复任务。
同时这条给出一个反向教训：**查「零写入键」时必须同时匹配模板化拼接**，否则会造出不存在的 bug。

🔴 顺带：目录覆盖 E1-1~E1-11 + E1-14/15 + E1-18~E1-23，**跨 4 册**。本 spec 只接第一册 ⇒
须有判据确认目录完成度在「仅第一册受管」状态下不回归（未受管 sheet 的完成度仍走 HTML 原路径）。

## 不在本 spec 范围

见 requirements §不在本 spec 范围。摘要：第 2~5 册 40 张（含全平台公式最多的 E1-30，389r/1187f）·
E1A 程序表 · 两张附注披露 · E0 册 9 张残留/参考 sheet 与 `E0-5` 编号重复 ·
`货币资金分析表F1-6 (修订前)` · 八张调整分录汇总表统一裁决（建议
`cycle-adjustment-sheets-single-html-adjudication`，去掉 `d-` 前缀）· 公式管理任何改动 ·
性能根因优化。

## 顺带发现（登记，不在本 spec 处理）

**E 循环模板治理债**（比 D6/D7 各 1 张残留严重得多）：
1. **E0 函证册 9 张残留/参考 sheet**：`函证程序表-原版本备份` / `参考用-往来函证程序` /
   `函证结果汇总表E0-1（原）` / `函证结果汇总表E0-1 (备份)` / `回函情况汇编` /
   `货币资金及借款函证结果汇总表-旧版` / `函证结果汇总表-旧版` / `核实被函证单位信息F1-10-原` /
   `邮件传真回函核对记录F1-12`（**F1 编号出现在 E0 册**）。
2. **`E0-5` 编号重复两张**：`应付银行承兑汇票发函记录表E0-5` 与 `银行函证其他信息核对表E0-5`
   —— 接第 5 册前必须先裁决。
3. **`货币资金分析表F1-6 (修订前)`** 在第 2 册（E1-14 册）里，**F1 编号出现在 E1 册**。
4. ⇒ 建议模板治理单独立项：这些残留会让 sheet 分派正则、`dSheetLabels`/`eSheetLabels` 类
   generated 映射、以及将来的受管清单都面临"同名/异循环编号"的歧义。
