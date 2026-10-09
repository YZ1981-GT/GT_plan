# Design Document

## Overview

本 design 承载 **lane 专属裁决 JN-1 ~ JN-7** 与 **J2/J3 接入前置清单**。

🔴 **分工铁律**：`JC-1 ~ JC-20` 的正文、判据口径、枚举定义**全部在地基 spec**
（`j-cycle-sync-foundation-and-first-canary/design.md`）。本文件**只写编号 + 一句话用途**。

**本 lane 的技术主题只有一个**：**把「从任何真实宿主都到不了、但看起来活着」的代码识别出来并删掉**，
同时把 J2/J3 接入 OO 前需要什么登记成清单。

🔴 **本 lane 不交付 contract / adapter / roundtrip** —— J2/J3 不是 manifest entry。

## 与地基 spec 的引用清单（只引用，不复述）

| JC | 一句话用途 | 本 lane 实例化在 |
|---|---|---|
| JC-1 | manifest 口径 + 禁手改 manifest | **JN-1** |
| JC-2 | 载体族第三种（`useChecklistPersistence`，client 是 `api`） | JN-3 / 接入清单 |
| JC-6 | 行身份五族划分 + JD-7（49 硬编码 id 登记不判缺陷）+ JD-8（判别式放宽） | **JN-4** |
| JC-10 | sheet 名三类空格禁 strip | JN-5 |
| JC-11 | 变体轴 + 跨循环串册 + 子码解析返册但 sheet 不存在 | JN-5 / 接入清单 |
| JC-13 | definedName 基线 + 断链登记 + 不删 | **JN-5** |
| JC-15 | BP-10 无声失败三要素（接入时不得重演） | 接入清单 |
| JC-16 | 宽/窄口径与差集现算 | **JN-2** |
| JC-20 | 空分母纪律 + 复用已有变异脚本 | 全篇 |

未在上表出现的 JC-3 / JC-4 / JC-5 / JC-7 / JC-8 / JC-9 / JC-12 / JC-14 / JC-17 / JC-18 / JC-19
在本 lane 的状态：
JC-3（六类端点）与 JC-14（裸 IF）按地基判据直接套用，本 lane 只补 J2/J3 的实测值 ·
🔴 **JC-4 / JC-5 / JC-8 / JC-9 / JC-12 / JC-18 / JC-19 与本 lane 无关**
（那些都是 J1 的一表三键、拼接键、三边锁、footer 三形态、derived_total、prefill）·
JC-7（removeRow 四形态）在本 lane 只有 J2/J3 侧的少数站点，无 lane 专属增量 ·
🔴 **JC-17（跨循环冻结不命中）在本 lane 须重新验**：J2/J3 的键同样无跨循环消费，
但 orphan 簇删除后 `events/publish` 与 `cross-wp-references/batch` 两条联动会一并消失（见 JN-3）。

---

## JN-1　「不是 entry」是可复算的结论，不是遗漏

### 四侧判据

```
① selection_rule 现算 entry 集合 == {xlsx/j1/gt-j1-employee-compensation}   恰 1 条
② manifest 里无任何 entry 的 host_path == J2/J3 宿主路径
③ 两宿主外层 <template> 里 GtOnlyOfficeSheet 与 el-segmented 命中各 0
④ htmlRendererRegistry 里 j2-defined-benefit-plan / j3-share-based-payment 的 import 真指向这两文件
```

**为什么四侧都要验**：只验 ① 会被「有人手写补两条 entry」绕过；只验 ③ 会漏掉「宿主确实可达」
这个事实而把它们当成死组件；只验 ④ 会得出「可达 ⇒ 应该是 entry」的错误推论。
四侧合起来才说得清「**产品上可达，OO 侧无入口，因此不是 entry**」。

🔴 **禁把 J2/J3 手写进 manifest**：违反 slice step 1 的 forbidden「手抄 entry 列表」，
且让 `selection_rule` 不再可复算。

### 宿主 import 段实测（证明「无 OO 侧入口」不是猜的）

两宿主的 import 段只有 `CycleTabProcedure` + `useChecklistPersistence` +
`useWorkpaperScaffold` + `useWorkpaperReviewThreads` —— 无 OO 组件、无 dual-mode composable。
J2 宿主 238 行原始 / 226 剥注释；J3 宿主 210 / 196。

---

## JN-2　🔴 可达性判定（两阶）而不是入度判定 —— 本 lane 的核心方法

### 为什么入度判定会失效

`useJ2DualMode.ts` 的 statement-position 边数是 **2**（barrel + 1 个 spec）。
朴素判据「入度 > 0 ⇒ 不是孤儿」会**放它过去**。
真相：那条生产边指向的 barrel `composables/workpaper/j2/index.ts` **自身入边为 0** ——
全仓没有任何文件 import `@/composables/workpaper/j2`（J2 宿主与 6 个子 Tab 都走**逐模块深链**）。

### 两阶判定配方

```
一阶 orphan : statement 生产边 == 0 且测试边 == 0
二阶 orphan : 全部生产边都指向同一目录的 barrel index.ts，且该 barrel 的入边 == 0
```

### 4 个 orphan 现算

| id | 模块 | 行数 | 阶 | 生产边 | 测试边 | barrel 入边 |
|---|---|---|---|---|---|---|
| OD-1 | `components/workpaper/composables/useJ2EntryDualMode.ts` | **41** | 一阶 | **0** | **0** | — |
| OD-2 | `components/workpaper/composables/useJ3EntryDualMode.ts` | **37** | 一阶 | **0** | **0** | — |
| OD-3 | `composables/workpaper/j2/useJ2DualMode.ts` | **35** | 🔴 二阶 | 1（barrel） | 1（spec） | 🔴 **0** |
| OD-4 | `composables/workpaper/j3/useJ3DualMode.ts` | **39** | 🔴 二阶 | 1（barrel） | 0 | 🔴 **0** |

### OD-1 / OD-2 的 sheet 映射表：接上就坏

| orphan | 映射常量 | 目标数 | 模板真实 sheet 数 | 命中 |
|---|---|---|---|---|
| OD-1 | `J2_SHEET_MAP` | **8** | 9 | 🔴 **0/8** |
| OD-2 | `J3_SHEET_MAP` | **4** | 6 | 🔴 **0/4** |

`J2_SHEET_MAP` 的 8 个目标是 `J2-目录` / `J2A` / `J2-1`..`J2-4` / `J2附注(上市)` / `J2附注(国企)`；
模板真实 9 张是 `底稿目录` / `长期应付职工薪酬实质性程序表 J2A` / `长期应付职工薪酬实质性程序表 L2A` /
`审定表J2-1` / `附注披露信息（上市公司）` / `附注披露信息（国有企业）` / `明细表J2-2` /
`调整分录汇总表J2-3` / `计提情况检查表J2-4` ⇒ **一个都对不上**。

⇒ 即便有人把它接上宿主，OO 侧会按**不存在的 sheet 名**去取 ⇒ 这是「接上就坏」不是「接上能用」。
判据 SHALL 两侧都验：映射目标数现算 == 8 / 4，且与 `sheetnames` 的交集 == **空集**。

### OD-4 的违规直调

```
composables/workpaper/j3/useJ3DualMode.ts:
  http.get('/api/workpapers/onlyoffice/health')      🔴 命中 legacy_deletion_paradigm step 6 明禁项
```

该端点的调用**只能通过 sync bridge 的 materialize 协议**。它现在无危害只因整个模块不可达；
顺着 barrel 接起来就是一条**绕过 bridge 的旁路**。
SHALL 一并登记：它自带的 `checkOOHealth` 与共享基类的实现**重复且更弱**
（无 `_silent`、无信封双形态兼容）。

### 两个 orphan barrel + 🔴 不得过度宣称

`composables/workpaper/j2/index.ts` 与 `j3/index.ts` 入边各 **0**。
🔴 但 SHALL **不宣称**整个 `composables/workpaper/j3/` 目录都是死的 ——
同目录的 `useJ3ImportExport.ts` 有一条**真实生产边**（`j3/core/J3TabDetail.vue` 走深链而非 barrel）。
过度宣称会让「删整个目录」变成一个看起来有依据的错误动作。

### 共享基类保留 + 🔴 窄口径

```
useWorkpaperEntryDualMode.ts     65 行 / localStorage 0
statement 窄口径消费边            29（现算）
J 循环贡献                        3（OD-1 + OD-2 + J1 宿主）
删完 J 的工作后剩                 26
🔴 宽口径现算                     34   ⇒ 用宽口径会得 31，让「删完还剩多少」说不清
🔴 宽−窄差集现算                  5 个（JC-16；slice 记 1 个已失效）
```

判据 SHALL 用**窄口径**（真语句边），并按 JC-16 写「差集**包含**
`workpaperSyncLegacyBaseline.generated.ts`」+ 现算清单，禁写死个数。

### 删除三件事齐备才动手

① 删前两阶可达性判定成立 ② 删前后全套测试零回归 ③ 独立 commit（便于回滚）
🔴 且 SHALL **按已有的 `backend/data/workpaper_sync_j_cycle_deletion_plan.json` 执行，不另起计划**。

---

## JN-3　`useJ3FormData.ts`：三条入边但整簇不可达

### 现算

```
composables/workpaper/j3/useJ3FormData.ts     151 行
入边 3 : j3/index.ts（barrel） + useJ3Detail.ts + useJ3Integration.ts
其中   : useJ3Detail 自身入边 1（只有 barrel）
         useJ3Integration 自身入边 0
⇒ 三者构成一个只经孤立 barrel 相连的簇，从任何真实宿主都不可达
```

🔴 **判据不能只看一层**：看一层会得「入边 3 ⇒ 活着」；看两层才看出整簇不可达。

### 它含完整持久化管道（这才是危险所在）

```
GET  /api/workpapers/{wpId}/render-config
PUT  /api/workpapers/{wpId}/checklist-responses
POST /api/projects/{projectId}/events/publish
item_id 形态 : `J3-${key}`        🔴 生产路径从未写过这种形态
verdict      : FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION
```

J3 的真实键是**三个子 Tab 各自 `KEY` 对象里的字面量**（`J3-1-plans` / `J3-2-vouchers` 等）。
⇒ 列入 `forbidden_carriers`（**改线时最容易误接的东西**）。

### 对照 J2 侧：风险已自然消解

`useJ2FormData.ts` **已被物理删除**（slice 2026-09-14 更新记载的动作已兑现，现算文件不存在）
⇒ 不再有可误接的实体。本 lane SHALL 断言该路径**不存在**，作为「删除动作真的做了」的正例锚点。

### 🔴 删除的连带影响（JC-17 在本 lane 须重验）

`useJ3FormData` 与 `useJ3Integration` 里有 `events/publish`（3 处）与
`cross-wp-references/batch`（1 处）两条联动。它们随整簇删除会**一并消失**。
⇒ 本 lane SHALL 在删除前**显式确认这些联动是否还需要**（现状：整簇不可达 ⇒ 这些联动本来就没跑过）。

### J3 的真实写路径（本轮实测超出 slice）

```
① 宿主经 useChecklistPersistence（JC-2 第三种族）
② 🔴 j3/core/J3TabDetail.vue 自己也直写 PUT /api/workpapers/{wpId}/checklist-responses
```

🔴 slice 说 J3 走宿主适配器，**未提 ② 这条直写** ⇒ 本 lane 须登记。

---

## JN-4　non_entry 侧 5 处位置化身份（JC-6 的实例化）

| 族 | 站点 | 表达式 | 写入键 | 真库证据 |
|---|---|---|---|---|
| 🔴 **A 纯序号真落库** | `j2/J2TabAdjustment.vue` | `id: i + 1` | `J2-3-entries` | 🔴 **171 B 载荷里 `"id":1` 已落库** |
| B 下标兜底 | `j2/J2TabAdjustment.vue` | `id: e.id ?? i + 1` | 同上 | — |
| B 下标兜底 | `j3/core/J3TabDetail.vue` | `id: p.id ?? i + 1` | `J3-1-plans` | 251 B 有载荷 |
| B 下标兜底 | `j3/core/J3TabCheck.vue`（**两处**） | `id: r.id ?? i + 1` | `J3-2-vouchers` 等 | 165 B 有载荷 |

合计 **5 处**（family_a 1 + family_b 4）。

### family_a 的严重性用真库实证，不用推演

```
J2-3-entries 真库 171 B:
[{"id":1,"description":"重分类一年内到期辞退福利","category":"账项调整",
  "reportItem":"长期应付职工薪酬","accountName":"","noteItem":"",
  "debitAmount":0,"creditAmount":0,"indexRef":"","remark":""}]
```

⇒ `"id":1` **真落库**。删中间一行再新增，后续行 id 全部左移、历史备注与金额串到另一笔分录。
🔴 这是全 J 域**唯一**的 family_a，且**已有真实数据受影响** ⇒ 本 lane 的最高优先修项。

### 修法与 grandfather

family_a 换安全生成器（含 `Math.random()` 且回落分支不是下标，口径见 JC-6）；
🔴 **已落库的 `id: 1..N` 一律 grandfather 不重写**（改它等于换身份）；
契约层声明 `legacy_ordinal_ids_grandfathered: true`。
family_b 四处只改**回落分支**，保留「上游有 id 时优先用上游 id」语义。

### J2 侧披露层同型复核

`J2TabDisclosureListed.vue`（**11 键**）与 `J2TabDisclosureSoe.vue`（**9 键**）是与 J1 同型的双变体披露 Tab
⇒ JC-6 的 JD-7「49 个硬编码 id + 四条真实风险」SHALL 在 J2 侧**同口径复核**
（本 lane 只做复核与登记，**不复述** JC-6 正文；修法标 `[ ]*`，涉用户可见披露口径）。

### 传输键 owner：只冻结已登记的常量，不冻结全集

```
J2 : 6 个子 Tab 各自的组件局部 KEY 对象   🔴 J2TabIndex.vue 无 KEY 对象（只读不写）
J3 : 3 个子 Tab 各自的组件局部 KEY 对象   🔴 J3TabIndex.vue 无 KEY 对象
```

🔴 **slice 首版把 `J3TabIndex` 列进 owner 清单，被守卫打红改正** ——
所以「四个 Tab」这个数是错的、**实为三个**。本 lane 把这条改正过程一并登记，
让后来者知道「三个」是被验证过的而不是抄漏了一个。

🔴 **不冻结 J2/J3 的键全集**：它们不是 entry，冻结全集会造出一份**没有消费方的死声明**
（additive 注入即死代码）。判据只验两件事：
① 真实形态 == 各 Tab 的字面量 `KEY` 对象 ② orphan 载体的形态（`J3-${key}`）≠ 真实形态。

---

## JN-5　模板层：definedName 断链是本 lane 最重的技术债

### 现算基线 + 断链数

| 册 | definedName | 含 `#REF!` | 占比 | 裸 IF | retired sheet |
|---|---|---|---|---|---|
| J2 | **37** | **30** | 81% | **12**（全在 `审定表J2-1`） | **0** |
| J3 | 🔴 **502** | 🔴 **479** | **95%** | 🔴 **0**（整册） | **0** |

### J3 的 502 个是跨循环复制残留（逐条实测名字）

```
_1固定资产数据库_筛选打印                 ← H 循环（固定资产）
_2其他资产_开办费除外_明细表               ← K 循环（其他资产）
_2、主要业务活动                          ← B 循环（控制了解）
_1、受本循环影响的相关交易和账户余额         ← B 循环
_.dbf  /  AS2DocOpenMode  /  _00510  /  _13  /  _1w6_
```

这些名字与股份支付业务毫无关系 ⇒ 是从别的工作簿复制模板时带进来的。

🔴 **裁决：不删**（删会让 `max_column` 内的公式整片失效），只声明「同步时不新增、不改写」；
清理 definedName 属**模板治理**另一条链路，标 `[ ]*`。
🔴 **比 I 循环严重一级**：I 是「definedName 非 0」（I4 476 / I5 334，**未查断链**）；
J 是「非 0 **且绝大多数断链**」。

### `明细表J2-2` 六子区 ↔ 六键一一对应

| 子区 | 行 | footer 公式 | 对应键 |
|---|---|---|---|
| 主表 | R11-18（两级表头 R11/R12） | R18 `=C13+C16-C17` | `J2-2-main` |
| 到期分析 | R20-27 | R27 `=SUM(C22:C26)`（🔴 含预留空行 R26） | `J2-2-maturity` |
| 设定受益计划情况 | R30-47 | R47 `=C32+C33+C38-C43`；🔴 **三级嵌套** R38 `=C39` → R39 `=SUM(C40:C42)` | `J2-2-dbp-status` |
| 计划资产 | R49-61 | R61 `=C51+C52+C56+C60` | `J2-2-plan-assets` |
| 精算假设 | R63 起 | — | `J2-2-assumptions` |
| 敏感性分析 | 末区 | — | `J2-2-sensitivity` |

r=90 c=14 f=221 merged=30。
🔴 **列语义与 `明细表J1-2 ` 逐字相同**（A 序号 / B 项目名称 / C-F 未审数[期初,本期增,本期减,期末] /
G 期初调整 / H-I 账项调整 / J-M 审定数[期初,本期增,本期减,期末] / N 备注）
⇒ 将来 J2 接 OO 入口时**契约可共用列映射**，不必重裁。有效列 14 == max_column ⇒ UUID 列 **15**。

### `股份支付情况表J3-1`：整表零业务公式

```
r=43  c=18  f=7      🔴 那 7 个公式全是 R3/R4 的 =底稿目录!A2 / A3
数据区 R20-27        R21 = '以权益工具结算'，R22-27 空
footer               🔴 无合计行
有效列 14 vs max_column 18（差 4）⇒ UUID 列 15
14 列语义            A 股份支付项目名称 / B 类型 / C 授予日 / D 批准部门 / E 行权日 /
                     F 权益工具数量 / G 等待期 / H 公允价值确定方法和数据来源 /
                     I 协议变更、取消情况 / J 资产负债表日估计更新情况 / K 剩余等待期限 /
                     L 协议索引号 / M 股份支付计算表索引号 / N 结论
```

⇒ J3 是**零公式表单**，与 D~I 的所有 entry 形态都不同。

### 🔴 J3 无审定表且无独立科目

6 张 sheet 里**没有** `审定表J3-*`（`底稿目录` / `股份支付实质性程序表 J3A` / `股份支付情况表J3-1` /
`股份支付检查表J3-2` / `IPO企业股权激励工具关注的审计重点` / `首发业务解答二`）。
宿主 docstring 明写「费用端走 K8/K9，权益端走 M4，现金端走 J1」
⇒ 即便将来接 OO 入口，它的审定表也**不回写 `trial_balance`**
⇒ 判据 SHALL **不要求** J3 有 TB 发布门（要求了就是假红）。

### sheet 名与串册

J2/J3 **无尾部空格**；**名中空格 3 张**（`长期应付职工薪酬实质性程序表 J2A` · `…L2A` ·
`股份支付实质性程序表 J3A`）禁 strip。
🔴 `长期应付职工薪酬实质性程序表 L2A` 现算是 **hidden**（slice 未记 hidden）且属 **L 循环**串册
—— 与 J1 册的 `应付职工薪酬实质性程序表 L1A-原`（🔴 slice 漏记）同型，两处都登记不修。

### 干净点（按 JC-20 空分母纪律）

J2/J3 的越界引用 **0** · 宽表（max_column ≥ 200）**0** · Excel Table **0** · retired sheet **0**
⇒ 一律写「现算为 0 且不是漏扫」，并复用已有变异脚本证明非空跑。

---

## JN-6　J2/J3 接入前置清单（登记，不执行）

| # | 项 | 现状 | 缺口 / 注意 |
|---|---|---|---|
| ① | 宿主挂 `GtOnlyOfficeSheet` | **0** | 挂上后才会被 `selection_rule` 枚举成 entry |
| ② | `el-segmented` 模式切换器 + **二级门控** | **0** | 🔴 **不得重演 J1 的无声失败**（JC-15） |
| ③ | dual-mode composable | 🔴 现有 4 个**全是 orphan** | 🔴 **一个都不能接**（sheet 映射全错 + OD-4 违规直调）；应复用共享基类（照 J1 的 JD-2 形态） |
| ④ | `GtEntrySyncCapabilityNotice` + 文案真源 | **0** | 文案真源必须是 `workpaperEntrySyncNotice.ts` |
| ⑤ | per-entry contract | **0** | 🔴 **J2 的列映射可共用 J1 的 14 列语义**（JN-5）；契约须同时覆盖 disclosure-notes 那条路径 |
| ⑥ | TB 发布门 | J2 待定 / 🔴 **J3 不需要** | J3 无独立科目（JN-5）⇒ 要求它有门就是假红 |
| ⑦ | `wp_guidance` | J3 有 / 🔴 **J2 缺** | **登记不补**（J2 不是 entry，现在补即死代码）；接入时一并补 |
| ⑧ | render schema | 🔴 **两份都已存在** | `j2-defined-benefit-plan.yaml` / `j3-share-based-payment.yaml` ⇒ 接入时**不重造** |

### J2/J3 真库都有非空载荷 ⇒ 将来满足 canary 硬标准

```
J2 : J2-2-dbp-status 2731 B · J2-soe-change 2556 B · J2-2-plan-assets 1581 B ·
     J2-1-dbo 1503 B · J2-2-main 1101 B · J2-2-maturity 842 B · J2-1-main 583 B ·
     J2-soe-assets 520 B · J2-4-measurement 527 B · … · J2-3-entries 171 B
J3 : J3-2-variation 288 B · J3-1-plans 251 B · J3-2-vouchers 165 B · J3-1-expert 121 B
     （另 6 个 J3 键 remark 为空串）
```

🔴 本 lane SHALL 把这个结论**显式登记给下一轮**：J2/J3 成为 entry 时**满足 canary 硬标准**
（对比 J1 的 primary managed table 三键真库全空，反而不满足）。

### 子码解析的反直觉（接入时不得误判）

`J2-5..J2-10` 与 `J3-3..J3-10` 这些**源模板里并不存在对应 sheet** 的子码，
两个解析函数**仍返回各自的册**（按册前缀解析而非按 sheet）
⇒ 接入时判据**不得写**「解析结果非 None ⇒ 该 sheet 存在」（JC-11）。

### 写路径与事件路径全清单（接入时契约必须覆盖）

```
J2 : PUT  /api/workpapers/{wpId}/checklist-responses            （宿主经 useChecklistPersistence）
     POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper   🔴 两个披露 Tab，写另一张表
     POST /api/projects/{projectId}/events/publish              （useJ2CrossSheet）
     GET  /api/workpapers/{wpId}/render-config                  （useJ2CrossSheet）
     POST /api/workpapers/{wpId}/j2/{import-data|export-data|export-template}
J3 : PUT  /api/workpapers/{wpId}/checklist-responses            （宿主 + 🔴 J3TabDetail.vue 直写）
     POST /api/projects/{projectId}/events/publish              （🔴 部分在 orphan 簇内，删除后消失）
     POST /api/projects/{projectId}/cross-wp-references/batch    （🔴 在 orphan 簇内）
     POST /api/workpapers/{wpId}/ai/generate-text                （3 个子 Tab）
     POST /api/workpapers/{wpId}/import-export/{import|export|template}
```

---

## JN-7　本 lane 的交付边界（明确写死，防越界）

### 本 lane **交付**

orphan 删除（4 个 + `useJ3FormData` 簇）· non_entry 5 处位置化修复 ·
definedName 断链登记 + 不增长断言 · J2 侧披露层 49 硬编码 id 同口径复核 ·
J2/J3 模板几何登记 · 接入前置清单 8 条 · 零回归。

### 本 lane **不交付**（写明理由）

| 不交付项 | 理由 |
|---|---|
| per-entry contract | J2/J3 不是 manifest entry |
| adapter 注册 | 同上 |
| roundtrip / evidence | 同上（没有 entry 就没有 scenario set） |
| canary | 地基 spec 已交付 `J1-6-short-term` |
| definedName 清理 | 属模板治理另一链路（删会让公式整片失效） |
| `wp_guidance/J2.json` | J2 不是 entry，现在补即死代码 |
| BP-1 ~ BP-4 | 🔴 **对本 lane 都不是阻塞**（不发 contract 不注册 adapter） |

🔴 **「BP-1~BP-4 对本 lane 不是阻塞」必须显式登记** —— 否则后来者会以为本 lane 也卡在平台供给上，
而它其实可以立刻实施完。

---

## Property（JN-P）

| # | Property | 引用 |
|---|---|---|
| JN-P1 | 四侧都验 J2/J3 非 entry（selection_rule 现算 1 条 / host_path 不在 / OO 与 segmented 各 0 / registry 真指向） | JN-1 |
| JN-P2 | 🔴 禁把 J2/J3 手写进 manifest；变异「手写补两条 entry」SHALL 打红 | JN-1 |
| JN-P3 | 宿主 import 段实测四项（无 OO 组件、无 dual-mode）；行数 238/210 原始 | JN-1 |
| JN-P4 | manifest entries 总数**现算**（155，slice 写 186）；写死该数 SHALL 打红 | JN-1 |
| JN-P5 | 🔴 两阶可达性判定：OD-1/OD-2 一阶零边 · OD-3/OD-4 二阶（边 1，barrel 入边 0） | JN-2 |
| JN-P6 | 🔴 反证：`useJ2DualMode` 边数 2，朴素「入度>0」判据 SHALL 放它过去而打红 | JN-2 |
| JN-P7 | 🔴 `J2_SHEET_MAP` 8 目标 / `J3_SHEET_MAP` 4 目标与 `sheetnames` 交集 == **空集** | JN-2 |
| JN-P8 | 🔴 OD-4 直调 `onlyoffice/health` 命中 step 6 明禁；其 `checkOOHealth` 比基类弱（无 `_silent`） | JN-2 |
| JN-P9 | 两个 barrel 入边各 0；🔴 **不宣称**整个 `j3/` 目录死（`useJ3ImportExport` 有真边） | JN-2 |
| JN-P10 | 共享基类保留；窄口径 29 / J 贡献 3 / 删后 26；🔴 宽口径 34 会得 31 ⇒ 必须用窄口径 | JN-2 |
| JN-P11 | 🔴 差集判据「**包含**生成文件」+ 现算清单（现算 5 个），禁写死 1 个 | JC-16 |
| JN-P12 | 🔴 `useJ3FormData` 三条入边但整簇不可达（两层判定）；只看一层 SHALL 判成活着而打红 | JN-3 |
| JN-P13 | `useJ3FormData` 的 `J3-${key}` 形态在生产路径命中 **0** ⇒ FABRICATED | JN-3 |
| JN-P14 | `useJ2FormData.ts` **不存在**（删除已兑现）—— 作为「删除真做了」的正例锚点 | JN-3 |
| JN-P15 | 🔴 删除前显式确认 `events/publish` 3 处 + `cross-wp-references/batch` 1 处的联动是否还需要 | JN-3 |
| JN-P16 | 🔴 `j3/core/J3TabDetail.vue` 自己直写 checklist-responses（slice 未提）已登记 | JN-3 |
| JN-P17 | non_entry 位置化 **5 处**（family_a 1 + family_b 4）逐条落表 | JN-4 |
| JN-P18 | 🔴 family_a 用**真库 171 B 载荷**实证 `"id":1` 已落库，不用推演 | JN-4 |
| JN-P19 | 已落库 `id: 1..N` **grandfather 不重写**；`legacy_ordinal_ids_grandfathered: true` | JN-4 |
| JN-P20 | family_b 四处只改回落分支，保留上游 id 优先语义 | JN-4 |
| JN-P21 | J2 侧披露层（11 键 / 9 键）按 JD-7 同口径复核；**不复述** JC-6 正文 | JN-4 |
| JN-P22 | 🔴 `J2TabIndex` / `J3TabIndex` **无 KEY 对象**；「四个 Tab」是错的、实为三个 | JN-4 |
| JN-P23 | 🔴 **不冻结 J2/J3 键全集**（会造无消费方的死声明）；只验真实形态 ≠ orphan 形态 | JN-4 |
| JN-P24 | definedName 基线 `{J2:37, J3:502}` + 🔴 **断链 `{30, 479}`** + 不增长 + **不删** | JN-5 |
| JN-P25 | 🔴 J3 的 502 个逐条列跨循环来源样本（H/K/B 循环名字）证明是复制残留 | JN-5 |
| JN-P26 | 裸 IF J2 **12** / 🔴 J3 **0**；per-file 挂；整册统一挂 SHALL 打红 | JN-5 |
| JN-P27 | `明细表J2-2` 六子区 ↔ 六键一一对应；三级嵌套 R38→R39→R40:R42 | JN-5 |
| JN-P28 | 🔴 J2 与 J1 的 14 列语义**逐字相同** ⇒ 接入时契约可共用列映射 | JN-5 |
| JN-P29 | 🔴 `股份支付情况表J3-1` **整表零业务公式**（7 个公式全是 `=底稿目录!A2/A3`）· 无 footer | JN-5 |
| JN-P30 | 🔴 J3 无审定表 + 无独立科目 ⇒ 判据**不要求** J3 有 TB 发布门 | JN-5 |
| JN-P31 | 名中空格 3 张禁 strip；🔴 `L2A` 现算 hidden（slice 未记）且属 L 循环串册 | JN-5 |
| JN-P32 | 干净点四项（越界 / 宽表 / Excel Table / retired）各 0，按空分母纪律 + 变异证明 | JN-5 |
| JN-P33 | 接入前置清单 **8 条**逐项给现状与缺口 | JN-6 |
| JN-P34 | 🔴 J2/J3 真库都有非空载荷 ⇒ 将来满足 canary 硬标准（与 J1 primary 全空相反） | JN-6 |
| JN-P35 | 子码解析返册但 sheet 不存在 ⇒ 接入判据不得写「非 None ⇒ 存在」 | JN-6 |
| JN-P36 | 写路径与事件路径全清单落表（J2 五类 / J3 五类） | JN-6 |
| JN-P37 | 🔴 交付边界表：七项不交付各有理由；**BP-1~BP-4 对本 lane 不是阻塞**须显式登记 | JN-7 |
| JN-P38 | 删除三件事齐备（两阶判定 + 零回归 + 独立 commit）；🔴 按已有 deletion plan 不另起 | JN-2 / Req 7.5 |
| JN-P39 | 零回归基线**现算**（契约目录 / 注册集 / adapter 成员），禁写死 | Req 7.1 |
| JN-P40 | 🔴 复用已有变异脚本 `mutate_task52_j_cycle_migration_guards.py`，不新写 | Req 7.6 |

🔴 **空分母纪律（JC-20）**：JN-P7 / JN-P13 / JN-P32 里所有「为 0 / 空集」的断言 SHALL 写成
「现算为 0 **且不是漏扫**」，并复用已有变异脚本逐条证明非空跑。
