# Design Document

## Overview

本 design 只承载 **lane 专属裁决 ID-1 ~ ID-8** 与 **I1 / I3 两份契约**。

🔴 **分工铁律**：`IC-1 ~ IC-20` 的正文、判据口径、枚举定义**全部在地基 spec**
（`i-cycle-sync-foundation-and-first-canary/design.md`）。本文件**只写编号 + 一句话用途**，
一条正文都不抄。抄一遍就等于造了第二真源，两边一改就漂移。

**本 lane 的技术主题只有一个**：**披露层的行身份从「位置」改成「值」**。
I1/I3 的其他形态（`host_inline` 载体 / `remark_only` 载荷 / 有发布门 / `rowId` 身份）都是 I 循环通例，
按 IC 判据实例化即可；真正需要新裁决的是位置化身份、分类真源双定义、以及 I3-2 那四格。

## 与地基 spec 的引用清单（只引用，不复述）

| IC | 一句话用途 | 本 lane 实例化在 |
|---|---|---|
| IC-1 | manifest capability 口径 + 只走 `register_from_manifest()` | ID-8 / 两份契约 |
| IC-2 | 载体族二分（I1/I3 都是 `host_inline`） | ID-5 |
| IC-5 | 分类三边校验（声明 / openpyxl 真读 / impl 常量） | **ID-2** |
| IC-6 | 行身份四族分治（族 A / A′ / B / D / C） | **ID-1** |
| IC-7 | 删行语义三件事（removeRow 两族） | **ID-6** |
| IC-10 | 干净点与非干净点分别断言（definedName 基线不增长） | ID-5 |
| IC-11 | sheet 命名四陷阱 | **ID-7** |
| IC-12 | wp_index 禁依赖 | 两份契约 `source_ref` |
| IC-13 | footer 四形态（含 `row_formula_applied`） | **ID-4** |
| IC-14 | I3-2 四格模板缺陷走覆盖层 | **ID-3** |
| IC-17 | 跨引用与键冻结 + 零回归现算 | **ID-8** |
| IC-18 | `derived_total_keys` 现算禁写死 | 两份契约 |
| IC-19 | 双区 / 三区派生区声明 | **ID-4** |
| IC-20 | Property 空分母纪律 | ID-P 表 |

未在上表出现的 IC-3 / IC-4 / IC-8 / IC-9 / IC-15 / IC-16 在本 lane **有效但无 lane 专属增量**，
按地基判据直接套用（IC-15 的 notice 挂载复制 canary 范式 · IC-16 的门控表本 lane 两行都「有二级门控」）。

---

## ID-1　位置化行身份的分治修复与 grandfather 策略

### 为什么不能一把梭改成新 id

三族的**风险等级和落库状态完全不同**，一把梭会同时造成两种伤：
把族 C 的展示序号也改掉（无意义的改动面）、把已落库的旧 id 冲掉（真的换身份 = 数据丢关联）。

| 族 | 风险 | 已落库？ | 处置 |
|---|---|---|---|
| **A′**（1 处） | 行序一变身份全错 | **是**（`_persistSection` → `http.put`） | 改生成器 + **旧值 grandfather** |
| **B**（5 处） | 仅在上游无 rowId 时错 | 可能 | 改回落分支 + 旧值 grandfather |
| **D**（2 处） | 同毫秒两次批量且 added 同起点才撞 | 可能 | 改生成器（无旧值兼容包袱：都是新增行） |
| **C**（20 处） | 无（不是身份） | — | 🔴 **不动**，反向断言不被点名 |

### grandfather 的精确边界

🔴 **已落库的位置化 id 一律保持原值**。改它等于换身份，会让历史行与新行对不上。
判据按前缀分：`cgu-` / `bv-` / `imp-` / `perf-` / `ap-` / `tc-i18-` 后面**紧跟纯数字**的即旧格式。

```
旧格式正则      : ^(cgu|bv|imp|perf|ap|tc-i18)-\d+$
新格式（族 A）  : ^(cgu|bv|imp|perf|ap|tc-i18)-[0-9a-z]+-[0-9a-z]{4,6}$   # Date.now(36) + random(36)
契约字段        : legacy_positional_ids_grandfathered = true
```

读取时两种都认，写入时只写新格式。🔴 **反向自检**：造一条 `cgu-3` 的历史行，
修复后再读 SHALL 仍是 `cgu-3`（不得被重写成新格式）。

### 生成器复用而不是新造

`useI3Disclosure.ts` 同文件 `#L521` / `#L570` / `#L629` / `#L690` 已经是族 A 形态
（`Date.now()` + `Math.random()`）⇒ 直接抽成本文件内的 `_stableRowId(prefix)`，
**不新引依赖、不新建 util 文件**。`i1DisclosureEnhance.ts#L241` 同法处理。

`i3/impairment/I3TabRecoverableTest.vue#L686` 这处 SHALL 从 `useI3Impairment.ts#L128` 现成的
`cgu-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` 生成器取值（同 entry 已有产物，不重造）。

### 🔴 扫描口径必须是形态口径

site #5 在 `.vue` 里。slice 与地基 design 初稿都把它当「site 维度第 6 处」单列、没并进族 B 计数，
本轮复算才并入 ⇒ **判据按 `r.rowId || <下标>` 形态扫，不按文件类型扫**。

变异表：

| 变异 | 期望 |
|---|---|
| 扫描限定 `composables/` 目录 | **打红**（漏 site #5） |
| 把 `useI6Detail#L250` 算进族 B | **打红**（它有 `Math.random()`，属族 A） |
| 把族 C 任一处报成缺陷 | **打红** |
| 正则不含 `${added}` | **打红**（漏 site #7/#8） |
| 把历史 `cgu-3` 重写成新格式 | **打红** |

---

## ID-2　分类真源：BP-7 的五项差异 + 🔴 CD-1 的 impl 边是**双定义**

### BP-7：`I1_SOE_CATEGORIES` 与两个真源都不符

impl（`composables/i1SoeDisclosureModel.ts#L29-42`，**12 条**，本轮逐行现读）：

```
其中：软件 / 土地使用权 / 房屋使用权 / 专利权 / 非专利技术 / 商标权 /
著作权 / 特许权 / 采矿权 / 探矿权 / 数据资源 / 其他
```

源模板 `附注披露信息（国有企业）!A9:A19`（**11 格**，openpyxl 真读）：

```
其中：软件… ✗   ← 源侧第 1 格是「其中：」前缀的另一类
土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 / 著作权 /
特许经营权 / 软件 / 矿产权 / 数据资源 / 其他
```

五项差异（Requirement 2 已列表，此处只给判据形状）：
条数 12↔11 · `软件` 位次 1↔8 · `房屋使用权`↔`住房使用权` ·
`特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`。

第二真源 `note_template_soe.json` 里 `采矿权` / `探矿权` / `房屋使用权` 命中 **0**
⇒ **两个真源都不支持 impl 的写法**。

🔴 **修法归业务确认（`[ ]*`）**。理由：这是会计披露口径问题（国企附注该用哪套分类名），
不是代码问题。本 lane 只交付三边判据 + 五项差异登记 + 「未修」的显式记录，**不擅自改分类名**。

### 🔴 CD-1 的 impl 边有两个独立真源（本轮新发现，slice 与地基 design 都只写了一个）

| 定义处 | 类型 | 条数 | 关系 |
|---|---|---|---|
| `composables/i1CategoryScope.ts#L19` | `I1CategorySlot[]`（key/label/seq/removable） | 11 | 权威侧（有 key、有 seq） |
| `composables/useI1Adjudication.ts#L105` | `readonly string[]`（纯中文串） | 11 | **第二份，独立维护** |

本轮现读两边 label **有序完全一致**（土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 /
著作权 / 特许经营权 / 软件 / 矿产权 / 数据资源 / 其他）⇒ **当前不冲突，但随时会漂**。

平台其实已经收敛过一次：`i1ListedDisclosureModel.ts#L41` 的注释写着
「label 由 `i1CategoryScope.I1_DEFAULT_CATEGORIES` 派生，本文件不再抄第二份」
—— 那次收敛**漏掉了 `useI1Adjudication.ts`**。

**裁决**：
1. CD-1 判据 SHALL **同时比对两处**，不是任选一处。
2. 🔴 变异「只改 `i1CategoryScope.ts` 的第 8 条 `软件`」SHALL 打红 —— 单边判据会静默通过（假绿）。
3. 收敛方向 = 让 `useI1Adjudication.ts#L105` 改为 `I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生，
   保留导出名与 `as const` 兼容现有 22 处引用；零回归跑 `i1CategoryScope.spec.ts` /
   `useI1Adjudication.spec.ts` / `iCycleDynamicRows.spec.ts` / `i1DisclosureAddCategory.spec.ts`。
4. 收敛后 CD-1 的 impl 边变回单源 ⇒ 判据 SHALL 同时断言「第二份定义已不存在独立字面量」。

### 源模板内部的真源断链（登记不修，本 lane 承 I1 的 2 处）

源模板自己把 `底稿目录!A9:A19` 当分类真源（`附注披露信息（上市公司）!B10..L10` 逐格
`=底稿目录!A9`..`A19`），但：

| 位置 | 实测 | 后果 |
|---|---|---|
| `附注披露信息（上市公司）!K10` | 字面 `数据资源`（不是 `=底稿目录!A18`） | 改 `A18` 不传播 |
| `明细表I1-2!A29` | 字面 `数据资源` | 改 `A18` 不传播 |
| （`明细表I2-2!A17` 同型，属 I2 ⇒ **归 lane 2**） | — | — |

🔴 **不改模板字节**（FC-5 只给了 IC-14 一个覆盖层例外，这两处不属金额错误、不开新例外）；
本 lane 只登记「`底稿目录!A18` 的改动不会传播到这 2 处」，让后来者不会误以为源模板是单源。

---

## ID-3　`明细表I3-2!AA23:AD23` 四格：覆盖层修复与「只有减值区有数」的判据载荷

### 缺陷精确形状

```
sheet          : 明细表I3-2          max_row = 29
四级表头       : R10-13
数据区         : R14-22
footer         : R23                （IC-13 的 row_formula_applied）
错误四格       : AA23 / AB23 / AC23 / AD23  = SUM(AA27:AA30) 形态（各自列）
R27~R29        : 编制说明文本行      ← 不是数据行
R30            : 超出 max_row(29)    ← 引用区间整段落在数据区之外
应为           : SUM(<同列>14:<同列>22)
后果           : 减值准备区审定数四列合计恒 0
```

### 修法：覆盖层（FC-5 的第 5 个例外）

前四个例外是 `F2-26!J9` / `F5-7!G31` / `G5-2` 45 格 / `G5-1!B35`。本条是第 5 个。
🔴 `backend/wp_templates/` 字节不动 —— 模板是审计准则产物，改字节会破坏与纸质底稿的对应关系，
而且 sha256 变了会让 6 条 entry 的 `source_ref` 全部失效。

覆盖层只替换这 4 格的公式字符串，其余 `R23` 的列**一个都不碰**。

### 🔴 判据载荷必须是「只有减值准备区有数」

这是本条最容易假绿的地方：

| 载荷 | 修复前 AA23:AD23 | 修复后 | 判据有效？ |
|---|---|---|---|
| 全区都有数 | 非 0（因为 R27:R30 若被别的公式带出值） | 非 0 | ❌ **假绿** |
| **只有减值准备区（R14:R22 的 AA:AD）有数** | **0** | 数据区真实合计 | ✅ |
| 全区都是 0 | 0 | 0 | ❌ 恒真 |

⇒ 判据 SHALL 用第二种，并同时断言 **R23 的非 AA:AD 列在修复前后取值不变**（不得误伤）。

契约 `known_template_quirks` 里本条标 **`overlay_fixed`**，
与 I6 的 `S19=SUM(S9:S18)` 文本列求和恒 0（标 `registered_not_fixed`）是**两种不同处置**，不得混写。

---

## ID-4　I1 双区派生 + I3 footer 行公式套用

### 几何实测（两册主表）

| 项 | `明细表I1-2` | `明细表I3-2` |
|---|---|---|
| 表头 | **四级 R8-11** | **四级 R10-13** |
| 数据区 | R12-17 | R14-22 |
| footer | **R18 纯 SUM** | **R23 行公式套用** |
| 有效列 / `max_column` | **47 / 56** | **30 / 30** |
| 公式数 | 179 | 133 |
| merged | 72 | —（未计） |
| 第二区 | 🔴 **R19-30（派生）** | 无 |
| UUID 落位 | **48**（= 47+1） | **31**（= 30+1） |

### I1 第二区是派生区，不接受用户改行标签

R19-30 的行标签逐格引用 `底稿目录!A9:A19`（11 类）⇒ 按 IC-19 标 `derived`。
🔴 如果允许用户在这一区改行标签，改动会在下次 render 被 `底稿目录` 覆盖掉（静默丢失）。
⇒ 契约 `regions[1].editable_labels = false`，判据 SHALL 断言回写时**跳过该区的标签列**。

### I3 的 footer 是第四形态

`footer_kind = row_formula_applied`（IC-13 新增的第四值，不是 `pure_sum`）+ `footer_convention_split`。
🔴 若照 I1 的 `pure_sum` 口径去验 I3 的 R23，会因为「不是 SUM 开头」而假红。

### UUID 落位

用「有效列 + 1」，🔴 **不得放 `max_column` 之后**：I1 的 `max_column` 是 56 但有效只 47，
放 57 会在有效区与 max 之间留 9 个空列，OO 打开后列宽错位。I3 的两者都是 30，放 31。

---

## ID-5　I3 mount=4 是全 I 唯一例外 + legacy OO 6 条是全 I 最多

| 项 | I1 | I3 | 全 I 循环位置 |
|---|---|---|---|
| mount 数 | 2 | **4** | 🔴 I3 是唯一 mount≠2 的 entry |
| `legacyOO` | 4 | **6** | 🔴 I3 全 I 最多 |
| `http_import` | 1 | 1 | 通例（I5 是 0） |
| `isOoAvailable` | 2 | 2 | 通例（I2 是 0） |
| 「仅结构化视图」 | 1 | 1 | 通例（I2 是 0） |
| 裸 IF | **321** | 63 | 🔴 I1 全 I 最多（总 777） |
| definedName | 0 | 0 | 基线口径（I4=476 / I5=334） |
| `derived_total_keys` | **8** | **0** | 现算；I3 为 0 已由 IC-18 裁定非漏扫 |

**裁决**：
1. I3 的 `force_component_type` 判据 SHALL 覆盖**全部 4 个挂载点**；变异「只验 1 个」SHALL 打红。
   这是「分母为空的重言式」的反面 —— 分母是 4 却只验 1，同样是假绿。
2. `legacyOO` 分支**不删代码**，只断言注册 adapter 后不再被走到（删它会牵动 OO 不可用时的降级路径）。
3. 裸 IF 中性化 SHALL **per-file** 挂（IC-9），I1 的 321 与 I3 的 63 各挂各的；
   变异「整册统一挂」SHALL 打红。
4. definedName SHALL 用**基线不增长**口径（IC-10）而不是「断言全 0」—— 本 lane 两册虽都是 0，
   但判据要与 I4/I5 共用同一套口径，写成「全 0」到了 lane 2 会直接假红。

---

## ID-6　🔴 本 lane 是唯一「下标族删行 × 位置化行身份」双重叠

### 实测

| entry | removeRow | 签名 | IC-7 族 |
|---|---|---|---|
| I1 | `composables/useI1Detail.ts#L623` | `removeRow(rowIndex: number)` | **下标族** |
| I3 | `composables/useI3Detail.ts#L580` | `removeRow(rowIndex: number)` | **下标族** |

对照：lane 2 的 I2 也是下标族（`useI2Detail.ts#L505 removeRow(index: number)`），
但 I4/I5 是 id 族（`useI4Detail.ts#L672` / `useI5Detail.ts#L821` 都 `removeRow(rowId: string)`）。
⇒ **lane 1 的两条 entry 100% 落在下标族**，而披露层的行身份又曾是位置化的。

### 组合判据（本 lane 专属，两条单独判据都抓不到）

```
给披露区 5 行 → 删第 3 行（按下标）→ 重新读取
断言：剩余 4 行的 rowId 集合 == 原 1/2/4/5 行的 rowId 集合
```

🔴 修复**前** SHALL 打红（族 A′ 的 `cgu-${i}` 会让原第 4/5 行变成 `cgu-2`/`cgu-3`，
与原第 3/4 行的 id 重合 ⇒ 数据串行）；修复**后** SHALL 通过。

契约 `row_delete_api_kind = "index"`（两条 entry 同值）。

---

## ID-7　参考页排除与 sheet 命名不得 strip

| sheet | entry | 形态 | 处置 |
|---|---|---|---|
| `审定表I1` | I1 | 🔴 **无 `-1` 尾码** | 按全名匹配，禁按 `审定表I1-1` 找 |
| `摊销测算表（不含减值）I1-10（剩余年限法）` | I1 | 括号后缀 ×2 | 禁 strip 括号 |
| `附注披露信息（上市公司）` / `附注披露信息（国有企业）` | I1 | 多「信息」二字 | 禁按 `附注披露（…）` 找 |
| `参考－商誉减值测试示例` | I3 | 🔴 **全角连字符 `－`**，非 hidden，104 行 / 114 公式 | `excluded_from_sync` |
| `市场平均收益率2017` | I3 | hidden，167 行 | `excluded_from_sync` |
| `GT_Custom` | I1 + I3 | hidden（6 册全有） | `excluded_from_sync` |

**排除理由逐条写明**（不是笼统「参考页不同步」）：
`参考－商誉减值测试示例` 是**示例数据不是项目数据**，同步会把示例数字当审定数 ·
`市场平均收益率2017` 是**固定年份的基准表**，不随项目变 · `GT_Custom` 是平台自用隐藏页。

🔴 变异「把参考页纳入 sheet 白名单」SHALL 打红。
🔴 变异「用 `参考-商誉减值测试示例`（半角连字符）匹配」SHALL 找不到而打红。

prefill 侧本 lane **不改口径**：16 条 I mapping 已正确用 sheet 全名、`items` 里 `cells` 型 == 0
（IC-11 已裁），本 lane 只复核。

---

## ID-8　跨 lane 键冻结：I1 读 I2，I1 也读 I6

### 三条跨边实测

| 消费方 | 读的键 | 归属 | 后果 |
|---|---|---|---|
| `composables/useI1AdditionCheck.ts#L250-251` | **`I2-2-rows`**（`remark` 优先 / `conclusion` 兜底） | I1 读 **I2** | 🔴 `I2-2-rows` 对 lane 2 是**冻结键** |
| `composables/expenseWpI1AmortPull.ts` | `I6-2-detail-rows` | I1 读 **I6** | canary 注册后须仍取到同一载荷 |
| `composables/i1AmortAllocCounterpartPull.ts` | `I6-2-detail-rows` | I1 读 **I6** | 同上 |

另有 `h1DepAllocCounterpartPull.ts`（**H1 pilot**）与 `h8DepAllocCounterpartPull.ts` 也读
`I6-2-detail-rows` ⇒ 🔴 本 lane 任何改动**不得触及 H1 pilot 的契约 / adapter / golden digest**（IC-17）。

### 🔴 `remark` + `conclusion` 双列读是一个隐藏耦合

`useI1AdditionCheck.ts` 读 `I2-2-rows` 时是 `?.remark ?? ?.conclusion`。
⇒ 如果 lane 2 把 I2 的 `payload_column_mode` 从 `remark_only` 改成别的（比如 `dual_write`），
本消费边的取值会变。两个 lane SHALL 在**地基 spec IC-17 的同一张跨引用表**上对账，
本 design **不复制那张表**。

**变异**：lane 2 把 `I2-2-rows` 改名 SHALL 让本 lane 的判据打红（跨 lane 回归闸）。

### wp_index 两套编号体系（本 lane 命中 4 例）

`I1-3` / `I1-4` / `I1-5` / `I3-3` 的 wp_index 子码与模板尾码**不对应**。
⇒ 契约 `source_ref` SHALL **不含任何 wp_index 来源字段**（IC-12），schema 校验层面卡死。

---

## 两份契约

### `i1.intangible_assets_detail.json`

```
entry_id        : xlsx/gt-i1-intangible-assets
provider_id     : phase5_intangible_assets_detail                # phase5_* 范式
source_ref      : { workbook_sha256: 97eced1f58ab3925…, sheet_name: "明细表I1-2" }
primary_table   : { item_id: "I1-2-rows", owner_module: "composables/useI1Detail.ts",
                    owner_constant: "ITEM_ID_ROWS", identity_field: "rowId",
                    header_rows: [8, 9, 10, 11], data_rows: [12, 17],
                    footer_rows: [18], footer_kinds: { 18: "pure_sum" },
                    effective_columns: 47 }                       # max_column 是 56
regions         : [ { idx: 0, rows: [12, 17], kind: "editable" },
                    { idx: 1, rows: [19, 30], kind: "derived",    # ID-4 / IC-19
                      label_source: "底稿目录!A9:A19", editable_labels: false } ]
row_delete_api  : { kind: "index", signature: "removeRow(rowIndex: number)",
                    site: "composables/useI1Detail.ts#L623" }
classification  : { impl_constants: ["composables/i1CategoryScope.ts#I1_DEFAULT_CATEGORIES",
                                     "composables/useI1Adjudication.ts#I1_DEFAULT_CATEGORIES"],
                    source_ref: "底稿目录!A9:A19", verdict: "MATCH", status: "clean",
                    dual_definition: true,                        # 🔴 ID-2 本轮新发现
                    dual_definition_converge_target:
                      "useI1Adjudication.ts 改为从 i1CategoryScope 派生" }
soe_classification : { impl_constant: "composables/i1SoeDisclosureModel.ts#I1_SOE_CATEGORIES",
                    source_ref: "附注披露信息（国有企业）!A9:A19",
                    verdict: "MISMATCH", status: "defect_registered_not_fixed",  # BP-7
                    diff_count: 5, fix_blocked_by: "business_confirmation" }
positional_identity : { sites: ["composables/i1DisclosureEnhance.ts#L241"],   # 8 site 里 I1 占 1
                    legacy_positional_ids_grandfathered: true }
excluded_sheets : ["GT_Custom"]
sheet_name_traps: ["审定表I1（无 -1 尾码）",
                   "摊销测算表（不含减值）I1-10（剩余年限法）",
                   "附注披露信息（上市公司）", "附注披露信息（国有企业）"]
carrier         : { write: "host_inline", write_client: "http",
                    read: "host_inline_render_config_refetch", mounts: 2,
                    force_component_type: "i1-intangible-assets",
                    tb_publish_gate: "composables/useI1Adjudication.ts#L659 + i1/core/I1TabAdjudication.vue#L1119" }
derived_total_keys : <现算 8 个，禁写死>
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，本册 321
uuid_column     : 48          # 有效 47 + 1，不得放 57
defined_name_baseline : 0     # 基线不增长口径，非「断言全 0」
variant_axis    : null
```

### `i3.goodwill_detail.json`

```
entry_id        : xlsx/gt-i3-goodwill
provider_id     : phase5_goodwill_detail
source_ref      : { workbook_sha256: 96cd6d6cb70698ce…, sheet_name: "明细表I3-2" }
primary_table   : { item_id: "I3-2-rows", owner_module: "composables/useI3Detail.ts",
                    owner_constant: "ITEM_ID_ROWS", identity_field: "rowId",
                    header_rows: [10, 11, 12, 13], data_rows: [14, 22],
                    footer_rows: [23],
                    footer_kinds: { 23: "row_formula_applied" },   # 🔴 IC-13 第四值
                    footer_convention_split: true,
                    effective_columns: 30 }                        # max_column 也是 30
row_delete_api  : { kind: "index", signature: "removeRow(rowIndex: number)",
                    site: "composables/useI3Detail.ts#L580" }
classification  : { impl_constant: null, source_ref: null,
                    verdict: "SOURCE_ITSELF_DERIVES_FROM_DETAIL", status: "clean" }  # CD-7
positional_identity : { sites: ["composables/useI3Disclosure.ts#L488",   # 族 A′
                               "composables/useI3Disclosure.ts#L441",   # 族 B ×3
                               "composables/useI3Disclosure.ts#L463",
                               "composables/useI3Disclosure.ts#L503",
                               "i3/impairment/I3TabRecoverableTest.vue#L686",  # 🔴 族 B 第 5 处
                               "composables/useI3Disclosure.ts#L665",   # 族 D ×2
                               "composables/useI3Disclosure.ts#L725"],
                    legacy_positional_ids_grandfathered: true,
                    persist_chain: "useI3Disclosure#L497 _persistSection('cgu_allocation') → "
                                   "#L870 _persistSection → GtI3Goodwill.vue#L319 http.put",
                    persist_keys: ["I3-disc-listed-cgu_allocation-rows",
                                   "I3-disc-soe-cgu_allocation-rows"] }
positional_labels : ["composables/useI3Disclosure.ts#L442", "#L464", "#L504"]  # 登记不修，业务确认
known_template_quirks : [ { cells: ["明细表I3-2!AA23", "AB23", "AC23", "AD23"],
                            actual: "=SUM(<列>27:<列>30)", expected: "=SUM(<列>14:<列>22)",
                            root_cause: "R27-29 是编制说明文本行；R30 超 max_row(29)",
                            effect: "减值准备区审定数四列合计恒 0",
                            handling: "overlay_fixed" } ]           # 🔴 非 registered_not_fixed
excluded_sheets : ["GT_Custom", "参考－商誉减值测试示例", "市场平均收益率2017"]
carrier         : { write: "host_inline", write_client: "http",
                    read: "host_inline_render_config_refetch", mounts: 4,   # 🔴 全 I 唯一 ≠2
                    force_component_type: "i3-goodwill",
                    tb_publish_gate: "composables/useI3Adjudication.ts#L402 + i3/core/I3TabAdjudication.vue#L708" }
derived_total_keys : []        # 现算 0，IC-18 已裁非漏扫
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，本册 63
uuid_column     : 31
defined_name_baseline : 0
variant_axis    : null
```

---

## roundtrip：本 lane 只能用合成载荷

🔴 **真库 `I1-2-rows` 与 `I3-2-rows` 都没有行**（I 循环真库只 `I5-2-rows` 745 B 与
`I6-2-detail-rows` 194 B 两条非空）⇒ 本 lane **不具备 canary 资格**，
roundtrip 必须复用地基 spec 的 I6 canary 范式，并在证据里标
`synthetic_payload_no_live_db_baseline`。

合成载荷 SHALL 满足三个条件（否则判据会假绿）：

1. **ID-3 专用载荷**：只有减值准备区（R14:R22 的 AA:AD）有数，其他区为 0。
2. **ID-6 专用载荷**：披露区 ≥ 5 行且每行 `rowId` 互不相同，用于「删中间一行」组合判据。
3. **ID-1 grandfather 载荷**：混入至少 1 条 `cgu-3` 形态的旧 id 行，验证它不被重写。

roundtrip 期间的四条冻结（IC-2 / IC-17 / IC-18 已裁，此处只列实例）：
冻结 `useAdjustmentCentralSync`（I1 `I1TabAdjustment.vue#L391` / I3 `I3TabAdjustment.vue#L456`）·
排除 `derived_total_keys`（I1 现算 8 / I3 0）· 不改 `I1-2-rows`/`I3-2-rows`/`I2-2-rows` 键名 ·
完成后回归 H1 pilot golden digest 不变。

---

## Property（ID-P）

| # | Property | 引用 |
|---|---|---|
| ID-P1 | 位置化 site 清单 8 项 == 实测（A′ 1 / B 5 / D 2），按 entry 拆 I3 7 + I1 1 | ID-1 |
| ID-P2 | 扫描按形态口径；限定 `composables/` 目录 SHALL 打红（漏 site #5） | ID-1 |
| ID-P3 | 族 C 的 20 处**不被点名**（反向自检） | ID-1 |
| ID-P4 | 历史 `^(cgu\|bv\|imp\|perf\|ap\|tc-i18)-\d+$` id 修复后原值不变 | ID-1 |
| ID-P5 | `I1_SOE_CATEGORIES` 12 条 vs 源 11 格的**五项差异**逐条命中；有序比对非集合比对 | ID-2 |
| ID-P6 | `采矿权`/`探矿权`/`房屋使用权` 在 `note_template_soe.json` 命中 0 | ID-2 |
| ID-P7 | 🔴 CD-1 的 impl 边**两处同时比对**；只改 `i1CategoryScope.ts` 第 8 条 SHALL 打红 | ID-2 |
| ID-P8 | 收敛后 `useI1Adjudication.ts` 不再有独立字面量；22 处引用零回归 | ID-2 |
| ID-P9 | `明细表I3-2!AA23:AD23` 修复前求值 == 0、修复后 == R14:R22 合计 | ID-3 |
| ID-P10 | R23 的非 AA:AD 列在覆盖层前后取值**不变**（不误伤） | ID-3 |
| ID-P11 | 判据载荷是「只有减值准备区有数」；用「全区有数」载荷 SHALL 打红 | ID-3 |
| ID-P12 | 两册几何七项 == 实测（表头/数据区/footer/有效列/max_column/公式数/UUID 列） | ID-4 |
| ID-P13 | I1 R19-30 标 `derived` 且 `editable_labels=false`；回写跳过标签列 | ID-4 |
| ID-P14 | I3 footer 判据用 `row_formula_applied`；照 `pure_sum` 验 SHALL 假红被捕获 | ID-4 |
| ID-P15 | I3 的 4 个挂载点全验；只验 1 个 SHALL 打红 | ID-5 |
| ID-P16 | 裸 IF per-file 挂（I1 321 / I3 63）；整册统一挂 SHALL 打红 | ID-5 |
| ID-P17 | definedName 用基线不增长口径（I1 0 / I3 0），非「断言全 0」 | ID-5 |
| ID-P18 | `derived_total_keys` 现算（I1 8 / I3 0），禁写死 | ID-5 |
| ID-P19 | 🔴 组合判据：删中间一行后剩余行 rowId 集合不变；修复前打红、修复后通过 | ID-6 |
| ID-P20 | 两条 entry `row_delete_api_kind == "index"` | ID-6 |
| ID-P21 | 3 张排除 sheet + 4 类命名陷阱逐条；半角连字符匹配 SHALL 打红 | ID-7 |
| ID-P22 | `I2-2-rows` 改名 SHALL 打红（跨 lane 回归闸）；双列读耦合已登记 | ID-8 |
| ID-P23 | H1 pilot golden digest 不变；两条 I1 读 I6 的边 canary 注册后仍取到同一载荷 | ID-8 |
| ID-P24 | 契约 `source_ref` 不含任何 wp_index 字段；4 例两套编号已登记 | ID-8 |
| ID-P25 | 零回归基线**现算**（契约目录个数 / 注册集 / adapter 成员），禁写死 | Req 7 |
| ID-P26 | 合成载荷三条件齐备；证据标 `synthetic_payload_no_live_db_baseline` | roundtrip |

🔴 **空分母纪律（IC-20）**：ID-P18 的 I3 侧分母为 0（`derived_total_keys` 空）⇒
该侧 SHALL **不宣称通过**，只断言「现算等于 0 且不是漏扫」；
ID-P17 两侧基线都是 0 同理 —— 断言的是「不增长」不是「为 0」。
