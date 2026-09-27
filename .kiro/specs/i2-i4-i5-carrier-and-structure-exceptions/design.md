# Design Document

## Overview

本 design 承载 **lane 专属裁决 IE-1 ~ IE-8** 与 **I2 / I4 / I5 三份契约**。

🔴 **分工铁律**：`IC-1 ~ IC-20` 的正文、判据口径、枚举定义**全部在地基 spec**
（`i-cycle-sync-foundation-and-first-canary/design.md`）。本文件**只写编号 + 一句话用途**。

**本 lane 的技术主题**：**三条 entry 各自把某一维度推到了 I 循环的极端**，
所以每条判据都必须先回答「这是特例还是通例」。放在一份 spec 里就有了对照组：
I2 对照出「缺门控 / 门在 `.vue`」是特例、I4 对照出「definedName 非 0」是特例、
I5 对照出「载体在 composable / 三区 / 内置行重置」是特例。

## 与地基 spec 的引用清单（只引用，不复述）

| IC | 一句话用途 | 本 lane 实例化在 |
|---|---|---|
| IC-1 | manifest capability 口径 + 只走 `register_from_manifest()` | 三份契约 |
| IC-2 | 载体族二分（本 lane 把它推成**三分**） | **IE-1** |
| IC-3 | 消费方判定用 import 路径字面量（禁符号名） | **IE-5** |
| IC-5 | 分类三边校验 | **IE-5** |
| IC-7 | 删行语义三件事（removeRow 两族 + 内置行重置 + 身份 backfill） | **IE-4** |
| IC-8 | representation 三件事（嵌套 / 双字段名 / payload mode 未证实） | **IE-6** |
| IC-10 | 干净点与非干净点分别断言（definedName 基线不增长） | **IE-3** |
| IC-11 | sheet 命名四陷阱 | IE-7 |
| IC-12 | wp_index 禁依赖 | **IE-7** |
| IC-13 | footer 四形态 + 多 footer | IE-2 |
| IC-16 | I2 UI 门控唯一例外 | **IE-8** |
| IC-17 | 跨引用与键冻结 + 零回归现算 | **IE-7** |
| IC-18 | `derived_total_keys` 现算禁写死 | 三份契约 |
| IC-19 | 双区 / 三区派生区声明 | **IE-2** |
| IC-20 | Property 空分母纪律 | IE-P 表 |

未在上表出现的 IC-4 / IC-6 / IC-9 / IC-14 / IC-15 在本 lane 的状态：
IC-4（owner 常量现读）与 IC-9（per-file 裸 IF）按地基判据直接套用无增量 ·
🔴 **IC-6（位置化行身份）在本 lane 命中 0**（8 个 site 全在 lane 1 的 {I1, I3}）·
🔴 **IC-14（I3-2 四格）与本 lane 无关**（属 lane 1）·
IC-15（notice 挂载）复制 canary 范式。

🔴 **IC-6 命中 0 是判据的一部分**：本 lane SHALL 主动断言三条 entry 的位置化 site == 0，
否则后来者会照 lane 1 的口径来找、找不到就当判据通过（空分母重言式）。

---

## IE-1　载体从二分推成三分：`host_inline` / `host_inline + 第二写路径` / `formdata_composable`

### 三行实测

| entry | write | 第二写路径 | write_client | read |
|---|---|---|---|---|
| I2 | `host_inline` | 🔴 **有** | `http` | `host_inline_render_config_refetch` |
| I4 | `host_inline` | 无 | `http` | 同 |
| I5 | 🔴 **`formdata_composable`** | — | — | 同 |

### I2 的第二写路径是活代码，不是死代码

```
composables/useI2FormData.ts   500 行
  #L181  async function _doSave(items: ChecklistItem[]): Promise<boolean>
  #L185    await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
  #L186      project_id, items: items.map(item => ({ item_id, conclusion, remark }))
```

import 生产消费计数现算 **4** ⇒ 真被消费。

🔴 **这是本 lane 最容易误判的一处**：`useI2FormData` / `useI4FormData` / `useI6FormData`
三个文件名同型，但只有 I2 那个是活的。若按「I 循环的 FormData composable 都是孤儿」一刀切，
会把 I2 的写路径删掉 ⇒ 保存静默失效。

⇒ **判据必须逐文件现算**：I2 == 4（活）· I4 == 0（死）· I6 == 0（死，归地基 spec）。
变异「把三个 FormData 一起列入可删名单」SHALL 打红。

### 双写一致性

两条写路径打的是**同一个端点、同一套 item 形状** `{item_id, conclusion, remark}` ⇒
注册 adapter 后二者不应分叉。判据形状：

```
经 useI2FormData._doSave 保存 → 从 adapter 侧读 → 载荷 == 经宿主内联写入后读到的载荷
```

### I5 的反向断言

I5 宿主里**无任何 http / api client import**（写在 composable 里）⇒
🔴 变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 在 I5 上打红。
这条反向断言是 IC-2 从二分推成三分的直接证据。

### 三个 0 值的空分母处理

`http_import` I5 == 0 · `isOoAvailable` I2 == 0 · 「仅结构化视图」I2 == 0。
🔴 按 IC-20：断言「现算等于 0 且不是漏扫」，**不宣称该维度通过**。
每条 0 值 SHALL 附一句为什么是 0（I5 无导入入口靠 composable 建行 ·
I2 不做 OO 可用性探测 · I2 无该开关）—— 没有解释的 0 就是漏扫的伪装。

---

## IE-2　几何三形态：单区 / 双区 / 三区，footer 一到三个

| 项 | `明细表I2-2` | `明细表I4-2` | `明细表I5-2` |
|---|---|---|---|
| 表头 | 三级 R10-12 | 三级 R8-10 | 🔴 两级 R8-9 |
| 数据区 | R13-22 | R11-22 | 🔴 R11-21 / R24-34 / R37-47 |
| footer | R23 | R23 | 🔴 R22 / R35 / R48 |
| 派生区 | 无 | R24-28 | 第 3 区整区 |
| 有效列 / `max_column` | 20 / **61** | 22 / 25 | 17 / 26 |
| 公式数 | 92 | 98 | 🔴 **334** |
| UUID 落位 | 21 | 23 | 18 |

### I5 三区是镜像结构，第三区全派生

```
第 1 区  R11-21  原值        11 行   ← 用户输入
第 2 区  R24-34  减值准备    11 行   ← 用户输入
第 3 区  R37-47  净值        11 行   🔴 fully_derived_region（= 原值 − 减值，逐格算出）
footer   R22 / R35 / R48
```

**裁决**：
1. 第 3 区 SHALL 标 `fully_derived_region`，回写时**整区跳过**、不接受用户输入。
   若允许写入，用户改的净值会在下次 render 被公式覆盖（静默丢失）。
2. 🔴 三区**行数必须相同（各 11）且按行序镜像对应**；变异「把某一区改成 10 行」SHALL 打红
   —— 镜像一破，净值区就会按错行去减。
3. `footer_rows: [22, 35, 48]` SHALL **分别**标 `footer_kind`，不得只声明第一个。

### I2 的 `max_column` 61 而有效只 20

UUID 落位 SHALL 取 **21**（= 20+1）。🔴 放 62 会在有效区与 max 之间留 41 个空列，
OO 打开后列宽错位。这是全 I 循环「有效列与 `max_column` 差距最大」的一册（41 列之差）。

---

## IE-3　🔴 definedName 基线口径的唯一实证场

```
现算基线   I1: 0   I2: 0   I3: 0   I4: 476   I5: 334   I6: 0        # 合计 810
判据口径   登记基线 + 断言不增长                                     # 非「断言全 0」
```

**为什么这条只能在本 lane 验**：另四册都是 0，照 H 循环 HC-14 的「断言全 0」口径写，
在 I1/I2/I3/I6 上都恒真、悄悄通过；**只有 I4/I5 会把它打红**。
⇒ 本 lane 是全 I 唯一能捕获「照抄 H 口径」这个错误的地方。

**双变异**：
① 给 I1 加一个 definedName SHALL 打红（基线破坏）
② 🔴 把判据写成「definedName 全 0」SHALL 在 I4/I5 打红

**不删这 810 个 definedName**：它们是模板公式的命名引用，删了会让公式整片失效。
只声明「同步时不新增、不改写」。

### per-file 裸 IF

I4 = 186 · I2 = 113 · I5 = 49（全 I 总 777）。per-file 挂 `oo_crash_neutralization_fn`（IC-9），
变异「整册统一挂」SHALL 打红。

---

## IE-4　I5 内置行「删除」= 原位重置 + 换 rowId；`projectName` 是事实主键

### 实现逐行现读（`composables/useI5Detail.ts#L821-839`）

```
#L821  function removeRow(rowId: string): void {
#L822    const idx = rows.value.findIndex((r) => r.rowId === rowId)
#L823    if (idx < 0) return
#L824    const row = rows.value[idx]
#L825    if (row.isBuiltin) {
#L826      rows.value[idx] = emptyI5DetailRow({
#L827        projectName: row.projectName,
#L828        name: row.projectName,
#L829        isBuiltin: true,
#L830        indexRef: row.indexRef || I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)?.indexRef || '',
#L831      })
#L832    } else {
#L833      rows.value.splice(idx, 1)
#L834    }
#L838    _persist()
```

🔴 传入的 4 个字段**不含 `rowId`**，而 `emptyI5DetailRow` 内 `#L305 rowId: generateRowId()`
⇒ **重置后 rowId 变了**，而且 `_persist()` 会把新 rowId 直接落库。

### 为什么 `projectName` 是事实主键

`#L830` 的兜底逻辑自己就在用 `projectName` 反查 `indexRef`
（`I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)`）⇒
实现层面已经把 `projectName` 当成了内置行的稳定标识，只是契约层没声明。

### 修法：①+② 双保险

| 方案 | 动作 | 成本 | 收益 |
|---|---|---|---|
| ① | `#L826` 传入 `rowId: row.rowId` | 一行 | 消除 rowId 漂移 |
| ② | 契约声明 `builtin_row_identity_field = "projectName"` | 一字段 | 已落库的漂移数据仍能按 `projectName` 对上 |

🔴 采**两条都做**：①治未来、②治历史。判据 SHALL 分别验：
①修复后删内置行 → 重读 `rowId` **不变** ②按 `projectName` 查得到那一行。

### 删行两族在本 lane 是 1:2

| entry | site | 签名 | `row_delete_api_kind` |
|---|---|---|---|
| I2 | `composables/useI2Detail.ts#L505` | `removeRow(index: number)` | **`index`** |
| I4 | `composables/useI4Detail.ts#L672` | `removeRow(rowId: string)` | `identity` |
| I5 | `composables/useI5Detail.ts#L821` | `removeRow(rowId: string)` | `identity` |

🔴 对照 lane 1：那边两条 entry **100% 下标族**。
⇒ 两个 lane **不得复用同一个签名断言**，否则一边必然假红或假绿。

---

## IE-5　BP-5（I4 孤儿）· BP-8②（I4 分类无真源）· CD-3/CD-5/CD-6

### BP-5 的 I4 侧：零消费但不删文件

`composables/useI4FormData.ts` **394 行**，用 IC-3 的 import 路径字面量三形态
（`from` / `import(` / `vi.mock(`）现算消费方 == **0**。

🔴 **禁用符号名 grep**：I 循环有 4 处注释里链式提及 dual-mode composable，
符号名口径会把注释当消费边。

**处置 = 列入契约 `forbidden_carriers`，本 lane 不删文件。**
理由：删文件是跨 spec 的清理动作，与并发会话有冲突风险；禁接已经能防止它被误用。

### BP-8②：`CATEGORY_OPTIONS` 6 条 vs 源 1 条

```
impl  composables 侧 CATEGORY_OPTIONS  6 条
源    明细表I4-2!A11  = 使用权资产改良及维护支出     ← 唯一有名分类
      明细表I4-2!A9 / A10  空
      明细表I4-2!A12:A22   全空
verdict  PREFIX_MATCH_WITH_UNSOURCED_TAIL
无真源   第 2~4 条：租入固定资产改良支出 / 固定资产大修理支出 / 开办费
```

🔴 **修法标 `[ ]*`（业务确认）**：这三条是否属长期待摊费用的合法分类是会计判断。

### CD-3（I5，clean）与 CD-5 / CD-6（I2）

- **CD-3**：`I5_BUILTIN_CATEGORIES` **10 条** 对 `明细表I5-2!A11:A20`（10 格），**有序等值** ⇒ clean。
  一并登记 `A21` = `……`（可扩位）· `A22` = 合计 ⇒ 声明区间边界正确。
- **CD-5**：I2 无 impl 分类常量 ⇒ `NO_IMPL_CLASSIFICATION_BY_DESIGN` / clean。
- **CD-6**：`defaultPerCapitaPeers` ⇒ `HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF` /
  `scanned_and_classified_not_a_defect`。**不是缺陷**的理由：它是「同业人均数」对照表的默认行数种子，
  模板里本来就没有对应分类区间 ⇒ 无真源是设计而非漏登记。
- 🔴 CD-5 与 CD-6 **同属 I2 但是两个 verdict**：status 维度上 CD-5 计 clean、CD-6 计
  classified_not_defect，**两者不相加**（IC-5 已裁）。

### 源模板真源断链（本 lane 承 I2 的 1 处）

`明细表I2-2!A17` 是字面 `数据资源`（不是 `=底稿目录!A18`）⇒ 改 `底稿目录!A18` 不传播。
另 2 处在 I1 ⇒ 归 lane 1。🔴 登记不修模板字节。

---

## IE-6　payload mode 两条未证实 + I5 真库载荷是 E2E 种子

```
真库 I 循环 checklist_responses：7 个 item_id，payload 列 7 行全 remark_only
  （remark 非空 / conclusion 为 null）
主表键非空只 2 条：I5-2-rows 745 B  ·  I6-2-detail-rows 194 B（后者归地基 spec canary）
```

⇒ 🔴 **I4 的 `dual_write` 与 I5 的 `passthrough` 都标 `unverified_in_live_db`**
（对照：I6 的 `remark_only` 已被真库证实，见地基 spec）。

### I5 那 745 B 不能当基线

| 项 | 实测 | 后果 |
|---|---|---|
| `rowId` | **`e2e-i52-contract`** | 🔴 是 **E2E 种子**，随 E2E 套件可被重置 |
| 嵌套 | `gross` / `impairment` **各 15 字段** | 对应三区的前两区（净值区派生不入载荷） |

⇒ 标 `live_payload_is_e2e_seed_not_business_data`；
**不得**据此宣称 `passthrough` 已被业务数据证实；roundtrip 用合成载荷并标 `synthetic_payload`。

### representation

按 IC-8 落 I5 嵌套路径 `gross.*` / `impairment.*`（各 15 字段）·
中英双字段名两侧都声明（不得只声明一侧）·
`dual_write` 落地时断言写 `conclusion` 列**不破坏** `remark_only` 读侧
（I2 第二写路径与 lane 1 的 `useI1AdditionCheck` 都会读 `conclusion` 兜底）。

---

## IE-7　wp_index 最严重一例在 I2 + 跨 lane 键冻结

### 🔴 `I2-1` 一码两名两底稿

```
真库 wp_index：I2-1  →  商誉减值测试     ×1     ← 业务上属 I3，不属 I2
                     →  开发支出审定表   ×3
```

⇒ 契约 `source_ref` SHALL **只用** `{workbook_sha256, sheet_name}`，
**不含任何 wp_index 来源字段**，schema 校验层面卡死（IC-12）。
🔴 变异「用 wp_index 的 `I2-1` 反查底稿」SHALL 打红（会取到 I3 的底稿）。

另登记两套编号体系例：`I2-3` 子码与模板尾码不对应。

### `I2-2-rows` 是跨 lane 冻结键

| 消费方 | 归属 | 读法 |
|---|---|---|
| `composables/useI1AdditionCheck.ts#L250-251` | **lane 1（I1）** | `?.remark ?? ?.conclusion` |
| `composables/i2ConsistencyModel.ts#L213` | I2 自身 | 前缀映射 `'I2-2-': ['I2-2-rows']` |
| 其余 I2 内部引用点 | I2 自身 | 现算集合（当前 **16 处**，禁写死） |

🔴 本 lane **不得改该键名**（会同时打断 lane 1 的消费边与一致性检查前缀表），
也不得在未通知 lane 1 的情况下改 I2 的 payload 列语义（对方读 `conclusion` 兜底）。

### I2 读 I6

`composables/useI2Analysis.ts` 消费 **`I6-2-detail-rows`** ⇒ canary 注册后 SHALL 仍取到同一载荷。
🔴 同键还被 **H1 pilot**（`h1DepAllocCounterpartPull.ts`）消费 ⇒ 断言 **H1 golden digest 不变**（IC-17）。

---

## IE-8　I2 的两条门：缺二级 UI 门控 + 发布门在 `.vue` 自建

### 二级 UI 门控（IC-16）

I2 是**唯一无二级门控**的 entry。判据 SHALL **按 toolbar class 定位区块**
（防 `I1#L171` / `I4#L142` 那类误判）。

🔴 **反向自检**：把判据改成「全 slice 都有二级门控」SHALL 在 I2 上**从静默恒真变打红**。
若改了还恒真，说明判据分母是空的 —— 这正是 IC-20 要防的重言式。

### 🔴 发布门层级：I2 在 `.vue`，I4/I5 在 composable

| entry | composable 层 | `.vue` 层 | `gate_layer` |
|---|---|---|---|
| I4 | `useI4Adjudication.ts#L371` 定义 / `#L489` 导出 | `I4TabAdjudication.vue#L510` import / `#L634` 调用 | `composable` |
| I5 | `useI5Adjudication.ts#L362` 定义 / `#L472` 导出 | `I5TabAdjudication.vue#L548` import / `#L718` 调用 | `composable` |
| **I2** | 🔴 **0 命中** | 🔴 **自建 4 处**：`I2TabAdjudication.vue#L74` 按钮 / `#L359` 区块注释 / `#L381` 注释 / `#L384` 定义 | **`host_tab`** |

**裁决**：
1. 「I 循环 6/6 全有发布门」是 **entry 维度**成立的结论。
2. 🔴 若判据写成「composable 里必须有 `publishToTb`」，**I2 会假红**。
   ⇒ 判据按 entry 维度找门（composable 或宿主 Tab 任一处有即算有），并记录 `gate_layer`。
3. 三条 entry 一律只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 二次确认；
   禁 `watch` / `onMounted` / debounce 内发布；**复用**平台既有 2 道 CI 守卫与
   `iAdjudicationPublishGate.spec.ts`，不重造。
4. 🔴 **本 lane 不把 I2 的门收敛到 composable**：收益是判据统一，风险是动按钮与二次确认链路 ⇒
   只登记 `gate_layer: "host_tab"`，收敛动作标 `[ ]*`（需 UI 回归实测）。

---

## 三份契约

### `i2.development_expenditure_detail.json`

```
entry_id        : xlsx/gt-i2-development-expenditure
provider_id     : phase5_development_expenditure_detail
source_ref      : { workbook_sha256: a93c298b1f4adfe2…, sheet_name: "明细表I2-2" }
                  # 🔴 禁任何 wp_index 字段（I2-1 一码两底稿）
primary_table   : { item_id: "I2-2-rows", owner_module: "composables/useI2Detail.ts",
                    owner_constant: "ITEM_ID_ROWS", identity_field: "rowId",
                    header_rows: [10, 11, 12], data_rows: [13, 22],
                    footer_rows: [23], effective_columns: 20 }   # max_column 是 61
frozen_key      : true
frozen_reason   : "lane 1 的 useI1AdditionCheck.ts#L250-251 跨 entry 读它（remark 优先/conclusion 兜底）；
                   i2ConsistencyModel.ts#L213 前缀映射也依赖它"
row_delete_api  : { kind: "index", signature: "removeRow(index: number)",
                    site: "composables/useI2Detail.ts#L505" }
carrier         : { write: "host_inline", write_client: "http",
                    read: "host_inline_render_config_refetch", mounts: 2,
                    second_write_path: "composables/useI2FormData.ts#L185",  # 🔴 活代码，消费计数 4
                    force_component_type: "i2-development-expenditure",
                    tb_publish_gate: "i2/core/I2TabAdjudication.vue#L384",
                    gate_layer: "host_tab",                      # 🔴 唯一不在 composable
                    secondary_ui_gate: false }                    # 🔴 唯一缺二级门控（IC-16）
oo_flags        : { legacyOO: 5, http_import: 1, isOoAvailable: 0, structured_only_switch: 0 }
classification  : { impl_constant: null, verdict: "NO_IMPL_CLASSIFICATION_BY_DESIGN",
                    status: "clean" }                             # CD-5
classification_extra : { impl_constant: "defaultPerCapitaPeers",
                    verdict: "HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF",
                    status: "scanned_and_classified_not_a_defect" }  # CD-6，与 CD-5 不相加
positional_identity : { sites: [] }        # 🔴 IC-6 在本 entry 命中 0（主动断言，非漏扫）
excluded_sheets : ["GT_Custom"]
template_source_break : ["明细表I2-2!A17 是字面「数据资源」，改底稿目录!A18 不传播（登记不修）"]
derived_total_keys : <现算 2 个，禁写死>
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，113
uuid_column     : 21          # 有效 20 + 1；🔴 不得放 62（max_column 61，差 41 列）
defined_name_baseline : 0
payload_column_mode : "remark_only"
variant_axis    : null
```

### `i4.long_term_prepaid_detail.json`

```
entry_id        : xlsx/gt-i4-long-term-prepaid
provider_id     : phase5_long_term_prepaid_detail
source_ref      : { workbook_sha256: 8bfb85884705e471…, sheet_name: "明细表I4-2" }
primary_table   : { item_id: "I4-2-rows", owner_module: "composables/useI4Detail.ts",
                    owner_constant: "ITEM_ID_ROWS", identity_field: "rowId",
                    header_rows: [8, 9, 10], data_rows: [11, 22],
                    footer_rows: [23], effective_columns: 22 }   # max_column 是 25
regions         : [ { idx: 0, rows: [11, 22], kind: "editable" },
                    { idx: 1, rows: [24, 28], kind: "derived" } ]  # IC-19
row_delete_api  : { kind: "identity", signature: "removeRow(rowId: string)",
                    site: "composables/useI4Detail.ts#L672" }
classification  : { impl_constant: "CATEGORY_OPTIONS",            # 6 条
                    source_ref: "明细表I4-2!A11",                  # 真读 1 条
                    verdict: "PREFIX_MATCH_WITH_UNSOURCED_TAIL",
                    status: "defect_registered_not_fixed",         # BP-8②
                    unsourced_tail: ["租入固定资产改良支出", "固定资产大修理支出", "开办费"],
                    fix_blocked_by: "business_confirmation" }
forbidden_carriers : ["composables/useI4FormData.ts"]              # 🔴 BP-5，394 行零消费；本 lane 不删文件
positional_identity : { sites: [] }                                # IC-6 命中 0
carrier         : { write: "host_inline", write_client: "http",
                    read: "host_inline_render_config_refetch", mounts: 2,
                    force_component_type: "i4-long-term-prepaid",
                    tb_publish_gate: "composables/useI4Adjudication.ts#L371 + i4/core/I4TabAdjudication.vue#L634",
                    gate_layer: "composable", secondary_ui_gate: true }
oo_flags        : { legacyOO: 5, http_import: 1, isOoAvailable: 2, structured_only_switch: 1 }
excluded_sheets : ["GT_Custom"]
sheet_name_traps: ["摊销测算表I4-7（工作量法）"]                    # 🔴 禁 strip 括号
derived_total_keys : []        # 现算 0；空分母不宣称通过（IC-18/IC-20）
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，186
uuid_column     : 23
defined_name_baseline : 476    # 🔴 基线不增长口径；写成「全 0」会在此打红
payload_column_mode : "dual_write"
payload_column_mode_status : "unverified_in_live_db"               # 🔴 真库 7 行全 remark_only
variant_axis    : null
```

### `i5.other_noncurrent_assets_detail.json`

```
entry_id        : xlsx/gt-i5-other-noncurrent-assets
provider_id     : phase5_other_noncurrent_assets_detail
source_ref      : { workbook_sha256: 7e8ec9c22580e05d…, sheet_name: "明细表I5-2" }
primary_table   : { item_id: "I5-2-rows", owner_module: "composables/useI5Detail.ts",
                    owner_constant: "ITEM_ID_ROWS", identity_field: "rowId",
                    builtin_row_identity_field: "projectName",      # 🔴 IE-4 事实主键
                    builtin_row_delete_semantics: "reset_in_place",
                    header_rows: [8, 9],                            # 🔴 两级（全 I 最浅）
                    effective_columns: 17 }                          # max_column 是 26
regions         : [ { idx: 0, rows: [11, 21], kind: "editable", role: "gross" },
                    { idx: 1, rows: [24, 34], kind: "editable", role: "impairment" },
                    { idx: 2, rows: [37, 47], kind: "fully_derived_region",
                      role: "carrying", formula: "gross - impairment" } ]
region_mirror   : { row_count_each: 11, mirrored_by: "row_order" }   # 🔴 三区行数必须相同
footer_rows     : [22, 35, 48]                                       # 🔴 三个分别标 kind
row_delete_api  : { kind: "identity", signature: "removeRow(rowId: string)",
                    site: "composables/useI5Detail.ts#L821",
                    builtin_branch: "composables/useI5Detail.ts#L825-831",
                    builtin_rowid_regenerated_by: "composables/useI5Detail.ts#L305 generateRowId()" }
classification  : { impl_constant: "I5_BUILTIN_CATEGORIES",          # 10 条
                    source_ref: "明细表I5-2!A11:A20",                 # 真读 10 格
                    verdict: "MATCH", status: "clean",               # CD-3
                    boundary_note: "A21=…… 可扩位 / A22=合计 ⇒ 区间边界正确" }
positional_identity : { sites: [] }                                  # IC-6 命中 0
carrier         : { write: "formdata_composable",                    # 🔴 全 I 唯一
                    read: "host_inline_render_config_refetch", mounts: 2,
                    host_has_http_import: false,                     # 🔴 反向断言
                    force_component_type: "i5-other-noncurrent-assets",
                    tb_publish_gate: "composables/useI5Adjudication.ts#L362 + i5/core/I5TabAdjudication.vue#L718",
                    gate_layer: "composable", secondary_ui_gate: true }
oo_flags        : { legacyOO: 5, http_import: 0, isOoAvailable: 2, structured_only_switch: 1 }
                  # 🔴 http_import 0：无导入入口，靠 composable 建行（空分母不宣称通过）
representation  : { nested_paths: ["gross.*（15 字段）", "impairment.*（15 字段）"],
                    payload_column_mode: "passthrough",
                    payload_column_mode_status: "unverified_in_live_db",
                    live_payload_note: "I5-2-rows 745 B 存在但 rowId=e2e-i52-contract",
                    live_payload_flag: "live_payload_is_e2e_seed_not_business_data" }
excluded_sheets : ["GT_Custom"]
derived_total_keys : []        # 现算 0；空分母不宣称通过
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，49
uuid_column     : 18
defined_name_baseline : 334    # 🔴 基线不增长口径
variant_axis    : null
```

---

## roundtrip：三条都只能用合成载荷

| entry | 真库状态 | roundtrip 载荷 |
|---|---|---|
| I2 | `I2-2-rows` 无行 | 合成 |
| I4 | `I4-2-rows` 无行 | 合成（且 `dual_write` 本身未证实） |
| I5 | `I5-2-rows` 745 B 但是 **E2E 种子** | 🔴 合成（种子不可作基线） |

合成载荷 SHALL 满足四条件：
1. **IE-2 专用**：I5 三区各 11 行且行序镜像对应，用于验第三区整区跳过。
2. **IE-4 专用**：含 ≥1 个 `isBuiltin: true` 的内置行，用于验重置后 `rowId` 不变。
3. **IE-1 专用**：I2 的载荷同时经两条写路径各写一次，验不分叉。
4. **IE-6 专用**：I4 的载荷写 `conclusion` 列，验不破坏 `remark_only` 读侧。

roundtrip 期间三条冻结（IC-2 / IC-17 / IC-18 已裁，此处只列实例）：
冻结 `useAdjustmentCentralSync`（`I2TabAdjustment.vue#L374` / `I4TabAdjustment.vue#L450` /
`I5TabAdjustment.vue#L467`）· 排除 `derived_total_keys`（I2 现算 2 / I4 0 / I5 0）·
不改 `I2-2-rows`/`I4-2-rows`/`I5-2-rows` 键名 · 完成后回归 H1 pilot golden digest 不变。

---

## Property（IE-P）

| # | Property | 引用 |
|---|---|---|
| IE-P1 | 载体三行 == 实测且互不相同（`host_inline` / +第二写路径 / `formdata_composable`） | IE-1 |
| IE-P2 | `useI2FormData` 消费计数 == 4（活）· `useI4FormData` == 0（死）；三个一起列可删 SHALL 打红 | IE-1 / IE-5 |
| IE-P3 | I2 双写路径写同端点同 item 形状；经第二写路径保存后 adapter 侧读到同一载荷 | IE-1 |
| IE-P4 | I5 宿主无 http/api client import；按 F 版守卫要求宿主自带 GET+PUT SHALL 打红 | IE-1 |
| IE-P5 | 三个 0 值（I5 `http_import` / I2 `isOoAvailable` / I2 结构化开关）各附解释，**不宣称通过** | IE-1 / IC-20 |
| IE-P6 | 三册几何七项 == 实测；I2 的 UUID 落 21 不落 62 | IE-2 |
| IE-P7 | I5 第三区标 `fully_derived_region` 且回写整区跳过 | IE-2 |
| IE-P8 | 🔴 I5 三区行数各 11 且行序镜像；改成 10 行 SHALL 打红 | IE-2 |
| IE-P9 | I5 `footer_rows: [22,35,48]` 三个**分别**标 kind；只声明第一个 SHALL 打红 | IE-2 |
| IE-P10 | definedName 基线 `{I1:0,I2:0,I3:0,I4:476,I5:334,I6:0}` 且不增长 | IE-3 |
| IE-P11 | 🔴 把判据写成「definedName 全 0」SHALL 在 I4/I5 打红（照抄 H 口径的捕获器） | IE-3 |
| IE-P12 | 810 个 definedName 不删，只声明同步不新增不改写 | IE-3 |
| IE-P13 | per-file 裸 IF（I4 186 / I2 113 / I5 49）；整册统一挂 SHALL 打红 | IE-3 |
| IE-P14 | I5 内置行重置后 rowId 变（现象被断言）；`projectName` 与 `indexRef` 被保留 | IE-4 |
| IE-P15 | 修复①后删内置行 rowId **不变**；修复②后按 `projectName` 查得到那一行 | IE-4 |
| IE-P16 | `row_delete_api_kind` 三值 `index`/`identity`/`identity`；与 lane 1 不复用签名断言 | IE-4 |
| IE-P17 | BP-8② 三边校验命中 `PREFIX_MATCH_WITH_UNSOURCED_TAIL`，无真源 3 条逐条 | IE-5 |
| IE-P18 | CD-3 有序等值 10 条；`A21`=…… / `A22`=合计 边界登记 | IE-5 |
| IE-P19 | CD-5 与 CD-6 同属 I2 但两 verdict，status 维度**不相加** | IE-5 |
| IE-P20 | `明细表I2-2!A17` 断链登记；改 `底稿目录!A18` 不传播 | IE-5 |
| IE-P21 | I4 `dual_write` / I5 `passthrough` 均标 `unverified_in_live_db` | IE-6 |
| IE-P22 | I5 真库 `rowId == e2e-i52-contract` 标 E2E 种子；**不得**作 roundtrip 基线 | IE-6 |
| IE-P23 | I5 嵌套 `gross`/`impairment` 各 15 字段；中英双字段名两侧都声明 | IE-6 |
| IE-P24 | 🔴 `I2-1` 一码两底稿登记；用 wp_index 反查 SHALL 打红 | IE-7 |
| IE-P25 | `I2-2-rows` 引用点集合现算（当前 16 处，禁写死）；改名 SHALL 打红 | IE-7 |
| IE-P26 | `useI2Analysis.ts` 读 `I6-2-detail-rows` canary 后仍取到同一载荷；H1 golden 不变 | IE-7 |
| IE-P27 | 🔴 I2 `secondary_ui_gate == false`；判据改成「全 slice 都有」SHALL 从恒真变打红 | IE-8 |
| IE-P28 | 🔴 `gate_layer` 三值 `host_tab`/`composable`/`composable`；写成「composable 必须有」I2 SHALL 假红被捕获 | IE-8 |
| IE-P29 | 三条 entry 发布只走显式端点 + 二次确认；禁 watch/onMounted/debounce | IE-8 |
| IE-P30 | 🔴 三条 entry 的位置化 site **主动断言 == 0**（IC-6 在本 lane 命中 0，非漏扫） | IC-6 |
| IE-P31 | 零回归基线**现算**（契约目录 / 注册集 / adapter 成员），禁写死 | Req 9 |
| IE-P32 | 合成载荷四条件齐备；证据标 `synthetic_payload` | roundtrip |

🔴 **空分母纪律（IC-20）**：IE-P5 / IE-P30 断言的都是「查过且为 0」——
SHALL 写成「现算等于 0 且不是漏扫」，**不宣称该维度通过**；
IE-P10 的 I1/I2/I3/I6 四侧同理，断言的是「不增长」不是「为 0」。
