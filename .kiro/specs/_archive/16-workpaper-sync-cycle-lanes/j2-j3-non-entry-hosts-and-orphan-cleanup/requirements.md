# Requirements Document

## Introduction

本 spec 是 **J 循环 lane**，覆盖 **J2（长期应付职工薪酬-设定受益计划净资产）与
J3（股份支付）两个「非 entry 宿主」**，以及挂在它们身上的 **4 个 orphan dual-mode composable**
与 1 个「长得像载体的死代码」。

🔴 **本 spec 的交付物类型与地基 spec 完全不同**：
地基 spec 交付 contract + provider + adapter + canary（为**是 entry** 的 J1 服务）；
本 spec 交付 **orphan 清理 + 缺陷登记 + 为将来接入做准备**（J2/J3 **不是** manifest entry，
现在不发 contract、不注册 adapter、不做 roundtrip）。
把两者合成一份会让「哪些任务是为 entry 服务的」说不清。

**为什么 J2 与 J3 合成一份而不拆两份**：两者的阻塞项**完全重合**（BP-6 / BP-7 都横跨 J2 与 J3）、
主题同一（非 entry 宿主 + orphan 清理）、且 4 个 orphan 里 J2 占 2 个 J3 占 2 个。
拆两份会把同一套可达性判据抄两遍。

**上游（只引用不复述）**：
`j-cycle-sync-foundation-and-first-canary`（**JC-1 ~ JC-20** 共同裁决 + canary `J1-6-short-term` 范式）·
umbrella Task 52 的 J slice · FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16 · IC-1~IC-20。

🔴 **JC-1 ~ JC-20 的正文在地基 spec 裁定，本 spec 一条都不复述**（复述即漂移）。

**不重造已有产物**：
`backend/tests/workpaper_sync/test_task52_j_cycle_migration.py`（含 `TestOrphanDualModeInventory`）·
🔴 `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`（变异注入，**直接复用**）·
🔴 `backend/data/workpaper_sync_j_cycle_deletion_plan.json`（**已有删除计划，按它执行不另起**）·
`backend/app/data/wp_render_schema/j2-defined-benefit-plan.yaml` · `j3-share-based-payment.yaml`。

🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得把 J2/J3 手写进 `workpaper_sync_entry_manifest.json`** —— 它们不是 entry
是 `selection_rule` **现算的结果**，手写会违反 slice step 1 的 forbidden 并让 selection_rule 不再可复算。

## 范围：2 个非 entry 宿主 / 15 sheets / 4 orphan + 1 lookalike

| 项 | J2 | J3 |
|---|---|---|
| 宿主 | `components/workpaper/j2/GtJ2DefinedBenefitPlan.vue`（**238 行**原始 / 226 剥注释） | `components/workpaper/j3/GtJ3ShareBasedPayment.vue`（**210 行** / 196） |
| componentType | `j2-defined-benefit-plan` | `j3-share-based-payment` |
| registry 源 | `registry/entries/specialized.ts` | 同 |
| htmlRendererRegistry | 有真 `defineAsyncComponent` 模块边 | 同 |
| 🔴 `GtOnlyOfficeSheet` | **0** | **0** |
| 🔴 `el-segmented` | **0** | **0** |
| manifest entry | 🔴 **不存在** | 🔴 **不存在** |
| 模板 | `J2 长期应付职工薪酬-设定受益计划净资产.xlsx` · sha256 `b9a4d87c95d275d7…` · 107,237 B · **9 sheets** | `J3 股份支付.xlsx` · sha256 `72e026f43612ec6b…` · 50,195 B · **6 sheets** |
| 审定表 | `审定表J2-1` | 🔴 **无审定表** |
| definedName | **37**（🔴 含 `#REF!` **30**） | 🔴 **502**（含 `#REF!` **479**） |
| 裸 IF | **12**（全在 `审定表J2-1`） | 🔴 **0**（整册） |
| 子 Tab 有 KEY 对象 | **6 个**（`J2TabIndex` 无） | **3 个**（`J3TabIndex` 无） |
| orphan dual-mode | `useJ2EntryDualMode.ts`（41 行，一阶）· `useJ2DualMode.ts`（35 行，二阶） | `useJ3EntryDualMode.ts`（37 行，一阶）· `useJ3DualMode.ts`（39 行，二阶） |
| lookalike 载体 | 🔴 `useJ2FormData.ts` **已被物理删除** | `useJ3FormData.ts`（**151 行**，仍在） |
| `useAdjustmentCentralSync` | 有（`J2TabAdjustment.vue`） | 🔴 **无**（J3 无独立科目） |
| `wp_guidance` | 🔴 **`J2.json` 缺失** | `J3.json` 存在 |

🔴 **J3 无独立科目**：宿主 docstring 明写「费用端走 K8/K9，权益端走 M4，现金端走 J1」
⇒ 即便将来接 OO 入口，它的审定表也**不回写 `trial_balance`**。

## Requirement 1：🔴 「不是 entry」必须是可复算的结论，不是遗漏

**User Story**：作为后来者，我要能自己跑一遍就确认 J2/J3 确实不在 manifest 里，
而不是怀疑上一轮漏迁了两条。

### Acceptance Criteria

1. WHEN 断言 J2/J3 非 entry THEN SHALL **四侧都验**：
   ① 按 slice `selection_rule` 现算 entry 集合，断言恰 **1 条** `xlsx/j1/gt-j1-employee-compensation`
   ② 断言 manifest 里**没有任何 entry** 的 `host_path` 等于这两个宿主路径
   ③ 断言两个宿主的外层 `<template>` 里 `GtOnlyOfficeSheet` 与 `el-segmented` 命中**各 0**
   ④ 断言 `htmlRendererRegistry` 里两条 componentType 的 import 路径**真指向**这两个文件
2. 🔴 WHEN 处理 manifest THEN SHALL **禁把 J2/J3 手写进 `workpaper_sync_entry_manifest.json`**
   —— 它们不在 manifest 是 `selection_rule` 现算的结果；手写会违反 slice step 1 的 forbidden
   「手抄 entry 列表」并让 selection_rule 不再可复算。
3. WHEN 说明「产品上可达但 OO 侧无入口」THEN SHALL 逐项落实测：两宿主的 import 段只有
   `CycleTabProcedure` + `useChecklistPersistence` + `useWorkpaperScaffold` + `useWorkpaperReviewThreads`
   —— **无 OO 组件、无 dual-mode composable**。
4. 🔴 WHEN 处理 manifest entries 总数 THEN SHALL **现算**（slice 多处写 186，现算 **155**）；
   任何写死该数的判据 SHALL 改为现算。
5. WHEN 声明本 spec 的边界 THEN SHALL 明确：本 spec **不发 contract、不注册 adapter、不做 roundtrip**
   （J2/J3 不是 entry），只做 orphan 清理 + 缺陷登记 + 为将来接入准备。

## Requirement 2：BP-6 —— 4 个 orphan dual-mode，两个一阶两个二阶

**User Story**：作为平台维护者，我要能识别「看起来有消费方但其实从任何真实宿主都到不了」的死代码，
而不是被入度骗过去。

### Acceptance Criteria

1. WHEN 判定 orphan THEN SHALL 做**可达性**判定而不是**入度**判定，两阶逐条现算：

| id | 模块 | 行数 | 阶 | statement 生产边 | 判定依据 |
|---|---|---|---|---|---|
| OD-1 | `components/workpaper/composables/useJ2EntryDualMode.ts` | **41** | 一阶 | **0**（测试边也 0） | 直接零边 |
| OD-2 | `components/workpaper/composables/useJ3EntryDualMode.ts` | **37** | 一阶 | **0**（测试边也 0） | 直接零边 |
| OD-3 | `composables/workpaper/j2/useJ2DualMode.ts` | **35** | 🔴 **二阶** | **1**（只 barrel `j2/index.ts`） | 🔴 barrel 自身入边 **0** |
| OD-4 | `composables/workpaper/j3/useJ3DualMode.ts` | **39** | 🔴 **二阶** | **1**（只 barrel `j3/index.ts`） | 🔴 barrel 自身入边 **0** |

2. 🔴 WHEN 编写判据 THEN SHALL 写反证：`useJ2DualMode` 的 statement 边数是 **2**
   （barrel + 1 个 spec）—— 朴素的「入度 > 0 ⇒ 不是孤儿」判据会**放它过去**。
   ⇒ 判据 SHALL 顺着 barrel 再问一层：全仓没有任何文件 import `@/composables/workpaper/j2`
   （J2 宿主与 6 个子 Tab 都是**逐模块深链**，不走 barrel）。
3. 🔴 WHEN 处置 OD-1 / OD-2 的 sheet 映射表 THEN SHALL 断言**映射目标一个都不存在**：
   - `J2_SHEET_MAP` **8 条**目标（`J2-目录` / `J2A` / `J2-1`..`J2-4` / `J2附注(上市)` / `J2附注(国企)`）
     vs 模板真实 9 张 sheet 名（`底稿目录` / `长期应付职工薪酬实质性程序表 J2A` /
     `长期应付职工薪酬实质性程序表 L2A` / `审定表J2-1` / `附注披露信息（上市公司）` /
     `附注披露信息（国有企业）` / `明细表J2-2` / `调整分录汇总表J2-3` / `计提情况检查表J2-4`）
     ⇒ **8/8 不在 sheetnames 里**
   - `J3_SHEET_MAP` **4 条**目标（`J3-目录` / `J3A` / `J3-1` / `J3-2`）
     vs 模板真实 6 张 ⇒ **4/4 不在 sheetnames 里**
   ⇒ 即便有人把它接上宿主，OO 侧会按不存在的 sheet 名去取 ⇒ 这是「接上就坏」不是「接上能用」。
4. 🔴 WHEN 处置 OD-4 THEN SHALL 断言它**直调 legacy 端点**：
   `GET /api/workpapers/onlyoffice/health` —— 命中 `legacy_deletion_paradigm` **step 6 明禁项**
   （该端点的调用只能通过 sync bridge 的 materialize 协议）。
   它现在无危害只因整个模块不可达；但顺着 barrel 接起来就是一条**绕过 bridge 的旁路**。
   SHALL 一并登记它自带的 `checkOOHealth` 与共享基类的实现**重复且更弱**（无 `_silent`、无信封双形态兼容）。
5. WHEN 处置**两个 orphan barrel** THEN SHALL 断言 `composables/workpaper/j2/index.ts` 与
   `j3/index.ts` 入边各 **0**；🔴 但 SHALL **不宣称**整个 `composables/workpaper/j3/` 目录都是死的 ——
   同目录的 `useJ3ImportExport.ts` 有一条**真实生产边**（`j3/core/J3TabDetail.vue` 走深链而非 barrel）。
6. WHEN 执行删除 THEN SHALL 🔴 **按已有的 `workpaper_sync_j_cycle_deletion_plan.json` 执行，不另起计划**；
   删前 SHALL 断言 4 个路径的可达性判定全部成立，删后 SHALL 全套测试零回归。
7. WHEN 处置共享基类 THEN SHALL 断言 `useWorkpaperEntryDualMode.ts` **保留**：
   现算 statement 边 **29**，J 循环贡献 **3**（OD-1 + OD-2 + J1 宿主）⇒ 删完 J 的工作后剩 **26**；
   🔴 计数口径必须是**窄口径（真语句边）**；宽口径现算 **34** 会得 31 而让「删完还剩多少」说不清。
8. 🔴 WHEN 用宽/窄口径 THEN SHALL 按 JC-16 的口径：差集现算 **5 个**不是 slice 说的 1 个
   ⇒ 判据写「差集**包含** `workpaperSyncLegacyBaseline.generated.ts`」+ 现算清单，禁写死个数。

## Requirement 3：BP-7 —— `useJ3FormData.ts` 是「长得像载体的死代码」

### Acceptance Criteria

1. WHEN 判定 THEN SHALL 现算 `composables/workpaper/j3/useJ3FormData.ts`（**151 行**）
   只经孤立 barrel 可达，却含**完整持久化管道**：
   `GET /api/workpapers/{wpId}/render-config` + `PUT /api/workpapers/{wpId}/checklist-responses`
   + `POST /api/projects/{projectId}/events/publish`
2. 🔴 WHEN 判定它的传输键形态 THEN SHALL 断言它把 item_id 拼成 `` `J3-${key}` `` ——
   而**生产路径从未写过这种形态**（J3 的真实键是三个子 Tab 各自 `KEY` 对象里的字面量）
   ⇒ verdict `FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION`。
3. 🔴 WHEN 判定可达性 THEN SHALL **不能只看一层**：它有 **3 条入边**（barrel + `useJ3Detail.ts` +
   `useJ3Integration.ts`），但后两者自身也只经孤立 barrel 可达
   （`useJ3Detail` 入边 1 = 只有 barrel；`useJ3Integration` 入边实测 **0**）
   ⇒ 三者构成一个**只经孤立 barrel 相连的簇**，从任何真实宿主都不可达。
4. WHEN 处置 THEN SHALL 列入 `forbidden_carriers`（**改线时最容易误接的东西**）；
   删除 SHALL 按已有 deletion plan 执行，且 SHALL 一并评估 `useJ3Detail.ts` / `useJ3Integration.ts`
   是否同批删（它们是这个簇的其余成员）。
5. WHEN 对照 J2 侧 THEN SHALL 登记 `useJ2FormData.ts` **已被物理删除**
   （slice 2026-09-14 更新记载的动作已兑现，现算文件不存在）⇒ 风险已自然消解，不再有可误接的实体。
6. 🔴 WHEN 对照真实载体 THEN SHALL 断言 J3 的真实写路径是宿主经 `useChecklistPersistence`
   （JC-2 的第三种族）+ 🔴 **`j3/core/J3TabDetail.vue` 自己也直写** `PUT …/checklist-responses`
   —— 后者是本轮实测发现（slice 说 J3 走宿主适配器，未提直写）。

## Requirement 4：non_entry 侧的 5 处位置化身份 + 披露层同型风险

### Acceptance Criteria

1. WHEN 处置 BP-8 的 non_entry 部分 THEN SHALL 落 **5 处**（JC-6 的族划分，本 spec 只实例化）：

| 族 | 站点 | 表达式 | 写入键 | 严重度 |
|---|---|---|---|---|
| 🔴 **A 纯序号真落库** | `j2/J2TabAdjustment.vue` | `id: i + 1` | `J2-3-entries` | **最重** |
| B 下标兜底 | `j2/J2TabAdjustment.vue` | `id: e.id ?? i + 1` | 同上 | 次之 |
| B 下标兜底 | `j3/core/J3TabDetail.vue` | `id: p.id ?? i + 1` | `J3-1-plans` | 次之 |
| B 下标兜底 | `j3/core/J3TabCheck.vue`（两处） | `id: r.id ?? i + 1` | `J3-2-vouchers` 等 | 次之 |

2. 🔴 WHEN 论证 family_a 的严重性 THEN SHALL 用**真库实证**而不是推演：
   `J2-3-entries` 真库 171 B 载荷实测
   `[{"id":1,"description":"重分类一年内到期辞退福利","category":"账项调整",…}]`
   ⇒ **`"id":1` 已真落库**。删中间一行再新增，后续行 id 全部左移、历史备注与金额串到另一笔分录。
3. WHEN 修 family_a THEN SHALL 换成安全生成器（含 `Math.random()` 且回落分支不是下标）；
   🔴 已落库的 `id: 1..N` **一律 grandfather 不重写**（改它等于换身份）；
   契约层 SHALL 声明 `legacy_ordinal_ids_grandfathered: true`。
4. WHEN 修 family_b 四处 THEN SHALL 只改**回落分支**，保留「上游有 id 时优先用上游 id」语义。
5. 🔴 WHEN 处置披露层 THEN SHALL 登记 **J2 侧有与 J1 同型的双变体披露 Tab**
   （`J2TabDisclosureListed.vue` / `J2TabDisclosureSoe.vue`，键分别 11 个 / 9 个）
   ⇒ JC-6 的 JD-7「49 个硬编码 id」四条风险 SHALL 在 J2 侧**同口径复核**
   （本 spec 只做复核与登记，**不复述** JC-6 正文）。
6. WHEN 处置 J2/J3 的传输键 THEN SHALL 断言 owner 是**各子 Tab 的组件局部 `KEY` 对象**
   （J2 **6 个** / J3 **3 个**），无共享常量模块；
   🔴 SHALL 断言 `J2TabIndex.vue` 与 `J3TabIndex.vue` **无 `KEY` 对象**（只读 allResponses 算完成度、不写库）
   —— slice 首版把 `J3TabIndex` 列进 owner 清单被守卫打红改正，所以「四个 Tab」这个数是错的、**实为三个**。
7. 🔴 WHEN 声明键集合 THEN SHALL **只冻结已登记的 owner 常量，不冻结 J2/J3 的键全集**
   —— 它们不是 entry，冻结全集会造出一份**没有消费方的死声明**（additive 注入即死代码）。
   判据只验「真实形态 = 各 Tab 的字面量 `KEY` 对象」与「orphan 载体的形态 ≠ 真实形态」两件事。

## Requirement 5：J2/J3 模板层 —— definedName 断链是本 lane 最重的技术债

### Acceptance Criteria

1. WHEN 处置 definedName THEN SHALL 落现算基线与断链数，并按 JC-13 口径**登记 + 断言不增长 + 不删**：

| 册 | definedName | 含 `#REF!` | 占比 |
|---|---|---|---|
| J2 | **37** | **30** | 81% |
| J3 | 🔴 **502** | 🔴 **479** | **95%** |

2. 🔴 WHEN 论证 J3 的 502 个是**跨循环复制残留** THEN SHALL 逐条列实测名字样本：
   `_1固定资产数据库_筛选打印`（H 循环）· `_2其他资产_开办费除外_明细表`（K 循环）·
   `_2、主要业务活动`（B 循环）· `_.dbf` · `AS2DocOpenMode` · `_1、受本循环影响的相关交易和账户余额`
   ⇒ 这些名字与股份支付业务毫无关系，是从别的工作簿复制模板时带进来的。
3. 🔴 WHEN 裁定处置 THEN SHALL **不删**（删会让 `max_column` 内的公式整片失效），
   只声明「同步时不新增、不改写」；清理 definedName 属**模板治理**另一条链路，标 `[ ]*`。
4. 🔴 WHEN 对照 I 循环 THEN SHALL 登记 **J 比 I 严重一级**：
   I 是「definedName 非 0」（I4 476 / I5 334，未查断链）；J 是「**非 0 且绝大多数断链**」。
5. WHEN 声明裸 IF THEN SHALL 落 J2 **12**（全在 `审定表J2-1`）· 🔴 J3 **0**（整册）；
   per-file 挂中性化函数；变异「整册统一挂」SHALL 打红。
6. WHEN 声明 J2 主表几何 THEN SHALL 落 `明细表J2-2` r=90 c=14 f=221 merged=30 **六个子区**，
   与 6 个传输键一一对应：

| 子区 | 行 | 对应键 |
|---|---|---|
| 主表 | R11-18（两级表头 R11/R12 · footer R18 `=C13+C16-C17`） | `J2-2-main` |
| 到期分析 | R20-27（footer R27 `=SUM(C22:C26)`） | `J2-2-maturity` |
| 设定受益计划情况 | R30-47（🔴 **三级嵌套** R38→R39→R40:R42 · footer R47 `=C32+C33+C38-C43`） | `J2-2-dbp-status` |
| 计划资产 | R49-61（footer R61 `=C51+C52+C56+C60`） | `J2-2-plan-assets` |
| 精算假设 | R63 起 | `J2-2-assumptions` |
| 敏感性分析 | 末区 | `J2-2-sensitivity` |

7. 🔴 WHEN 声明列映射 THEN SHALL 登记 **`明细表J2-2` 与 `明细表J1-2 ` 的 14 列语义逐字相同**
   （A 序号 / B 项目名称 / C-F 未审数[期初,本期增,本期减,期末] / G 期初调整 / H-I 账项调整 /
   J-M 审定数[期初,本期增,本期减,期末] / N 备注）
   ⇒ 将来 J2 接 OO 入口时**契约可共用列映射**，不必重裁。
8. 🔴 WHEN 声明 J3 主表几何 THEN SHALL 落 `股份支付情况表J3-1` r=43 c=18 f=**7** ——
   那 7 个公式**全是 R3/R4 的 `=底稿目录!A2` / `A3`**，即 🔴 **整表零业务公式**；
   数据区 R20-27（R21=`以权益工具结算`，R22-27 空）· **无 footer 合计** ·
   有效列 **14** vs max_column **18**（差 4）⇒ UUID 列 **15**。
9. WHEN 声明 J3 的会计边界 THEN SHALL 登记 🔴 **J3 无审定表且无独立科目**：
   6 张 sheet 里没有 `审定表J3-*`；宿主 docstring 明写「费用端走 K8/K9，权益端走 M4，现金端走 J1」
   ⇒ 即便将来接 OO 入口，它的审定表也**不回写 `trial_balance`**
   ⇒ 判据 SHALL **不要求** J3 有 TB 发布门（要求了就是假红）。
10. WHEN 声明 sheet 名 THEN SHALL 按 JC-10 断言 J2/J3 **无尾部空格**，
    但**名中空格 3 张**（`长期应付职工薪酬实质性程序表 J2A` · `…L2A` · `股份支付实质性程序表 J3A`）禁 strip；
    🔴 SHALL 登记 `长期应付职工薪酬实质性程序表 L2A` 现算是 **hidden**（slice 未记）且属 **L 循环**串册。
11. WHEN 断言干净点 THEN SHALL 逐项现算为 0 并按 JC-20 空分母纪律处理：
    J2/J3 的越界引用 **0** · 宽表 **0** · Excel Table **0** · retired sheet **0**（两册都无 `-删除`/`-原版`）。

## Requirement 6：为将来接入做准备（不现在接）

**User Story**：作为下一轮的实施者，我要能直接拿到「J2/J3 接 OO 入口时需要什么」的清单，
而不是重新调查一遍。

### Acceptance Criteria

1. 🔴 WHEN 本 spec 收尾 THEN SHALL 产出**接入前置清单**（不执行，只登记），逐条给现状与缺口：
   ① 宿主需挂 `GtOnlyOfficeSheet`（现状 0）
   ② 宿主需 `el-segmented` 模式切换器 + **二级门控**（现状 0；🔴 不得重演 J1 的无声失败，见 JC-15）
   ③ 需 per-entry dual-mode 或复用共享基类（🔴 现有 4 个 orphan **一个都不能接**，见 Requirement 2/3）
   ④ 需 `GtEntrySyncCapabilityNotice` 挂载 + 文案真源（现状 0）
   ⑤ 需 per-entry contract（现状 0；🔴 J2 的列映射可**共用 J1 的 14 列语义**，见 Requirement 5.7）
   ⑥ J3 🔴 **不需要** TB 发布门（无独立科目，见 Requirement 5.9）
   ⑦ `wp_guidance/J2.json` **缺失**（现状：只有 `J1.json` / `J3.json`）
2. WHEN 登记 `wp_guidance/J2.json` 缺失 THEN SHALL 标**登记不补**：J2 不是 entry，
   现在补会造出一份没有消费方的文件（additive 即死代码）；接入时一并补。
3. WHEN 登记 J2/J3 的 render schema THEN SHALL 断言两份**已存在**
   （`j2-defined-benefit-plan.yaml` / `j3-share-based-payment.yaml`）⇒ 接入时**不重造**。
4. 🔴 WHEN 登记 J2 的披露写路径 THEN SHALL 落它已在用**第三条写路径**：
   `J2TabDisclosureListed.vue` 与 `J2TabDisclosureSoe.vue` 都调
   `POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper`
   ⇒ 写的是**另一张表**（不是 `checklist_responses`）⇒ 接入时契约必须同时覆盖两条路径。
5. WHEN 登记 J2/J3 的事件路径 THEN SHALL 落 `POST /api/projects/{projectId}/events/publish`
   （`useJ2CrossSheet` / `useJ3CrossSheet` / `useJ3Integration`）+
   `POST /api/projects/{projectId}/cross-wp-references/batch`（`useJ3Integration`）
   —— 🔴 其中经 orphan 簇的那些（`useJ3FormData` / `useJ3Integration`）**删除后会一并消失**，
   接入时须确认这些联动是否还需要。
6. 🔴 WHEN 登记 J2/J3 的真库载荷 THEN SHALL 落现算：J2 侧 `J2-2-dbp-status` **2731 B** ·
   `J2-soe-change` **2556 B** · `J2-2-plan-assets` 1581 B · `J2-1-dbo` 1503 B · `J2-2-main` 1101 B ·
   `J2-3-entries` 171 B；J3 侧 `J3-2-variation` 288 B · `J3-1-plans` 251 B · `J3-2-vouchers` 165 B ·
   `J3-1-expert` 121 B（另 6 个键 remark 为空串）
   ⇒ **J2/J3 真库都有非空载荷** ⇒ 将来它们成为 entry 时**满足 canary 硬标准**，
   本 spec SHALL 把这个结论显式登记给下一轮。
7. WHEN 登记 J2-5..J2-10 / J3-3..J3-10 THEN SHALL 按 JC-11 断言这些子码**源模板无对应 sheet**
   但两个解析函数**仍返回各自的册**（按册前缀解析）⇒ 接入时判据不得写「解析非 None ⇒ sheet 存在」。

## Requirement 7：零回归 + 不复述 JC + 证据

### Acceptance Criteria

1. WHEN 实施任一 Task THEN SHALL 先**现算**零回归基线（契约目录 `*.json` 个数与文件名集合 ·
   `DELIVERED_PER_ENTRY_CONTRACTS` 条数与 entry_id 集合 · `adapter_registered=True` 集合 ·
   `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员），🔴 **禁写死个数**
   （会随地基 spec 的 canary 注册而变）。
2. 🔴 WHEN 引用 JC-1~JC-20 THEN SHALL **只写编号 + 一句话用途**，正文一律不抄；
   交付后 SHALL 脚本核「本 spec 的 `JC-\d+` 引用集合 ⊆ 地基 spec 的 `### JC-\d+` 定义集合」。
3. WHEN 写「N 处」类表述 THEN N SHALL 与同段列举项数**逐条相等**。
4. WHEN 产出证据 THEN SHALL 落 `evidence/` 下逐 Task 一份，含 openpyxl 真读片段与
   可达性判定的两阶计算过程；SHALL 断言全文无 U+FFFD。
5. 🔴 WHEN 执行删除 THEN SHALL 三件事齐备才动手：
   ① 删前可达性判定成立（两阶）② 删前后全套测试零回归 ③ 独立 commit（便于回滚）
   —— 且 SHALL **按已有的 `workpaper_sync_j_cycle_deletion_plan.json` 执行，不另起计划**。
6. WHEN 复用变异证明 THEN SHALL 🔴 用已有的
   `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`，**不新写变异脚本**。

## 阻塞项

**平台级（全循环共有，只标 `[ ]*` 不承诺）**：
BP-1 instrumentation candidate · BP-2 per-entry contract · BP-3 authority model + bundle ·
BP-4 真 OnlyOffice 9.4 required scenario set。
🔴 **但对本 spec 而言这四条都不是阻塞**：J2/J3 不是 entry，本 spec 不发 contract 不注册 adapter
⇒ SHALL 明确登记「本 spec 的交付不依赖 BP-1~BP-4」。

**本 lane 承接**：

| BP / 事项 | 状态 | 说明 |
|---|---|---|
| **BP-6** 4 个 orphan dual-mode | 本 lane 交付删除 | 两个一阶 + 两个二阶；按已有 deletion plan 执行 |
| **BP-7** `useJ3FormData.ts` 死代码 | 本 lane 交付 `forbidden_carriers` + 删除 | 连带评估 `useJ3Detail` / `useJ3Integration` 同批 |
| **BP-8**（non_entry 5 处） | 本 lane 交付修复 | family_a 1（真库已落库，grandfather）+ family_b 4 |
| J2/J3 definedName 断链（30 / 479） | 登记 + 断言不增长 + **不删** | 清理属模板治理另一链路，`[ ]*` |
| J2 侧披露层 49 硬编码 id 同型复核 | 本 lane 复核 + 登记 | 修法 `[ ]*`（涉用户可见披露口径） |
| `wp_guidance/J2.json` 缺失 | **登记不补** | J2 不是 entry；接入时一并补 |
| J2/J3 接入前置清单 7 条 | 本 lane 交付清单（不执行） | Requirement 6 |
| BP-5 / BP-9 / BP-10 / BP-11 | **地基 spec** | 不在本 lane |
