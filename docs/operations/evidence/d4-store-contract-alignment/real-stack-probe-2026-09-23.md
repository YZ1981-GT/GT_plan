# D4 store 契约对齐 —— 真栈实测证据

spec: `d4-html-to-oo-store-contract-alignment` · Task 18
日期：2026-09-23 · 环境：后端 9980 / 前端 3030 / PG `audit_platform`（真库，非 mock）
项目：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` · 底稿：`b3ab3c46-828f-4f48-950e-aee9bbdc923f`（D4 营业收入）
entry：`xlsx/gt-d4-operating-revenue` · 账号：admin

三条链路走**真实端点**（`PUT/GET /api/workpapers/{wp}/checklist-responses` 写读 store、
`GET /api/projects/{p}/workpapers/{wp}/sync/entries/{entry}/store-projection` 出方向投影），
不 mock 任何一端。

---

## 一、缺陷 A1 —— D4-1 金额随行落库 → 出方向带金额

写入 `D4-1-rows`（修复后形态：金额平铺进行对象顶层 + `derivedSnapshot`）：

```json
[{"rowId":"probeA","label":"探针-批发收入","source":"tb","accountCode":"6001",
  "sectionKey":"main-revenue","currentUnadjusted":12345.67,"currentAje":100.0,
  "currentRje":0,"priorUnadjusted":11000.0,"priorAje":0,"priorRje":0,
  "derivedSnapshot":{"currentUnadjusted":12345.67,"priorUnadjusted":11000.0}},
 {"rowId":"probeB","label":"探针-其他业务","source":"manual","accountCode":"6051",
  "sectionKey":"other-revenue","currentUnadjusted":777.77,"currentAje":0,"currentRje":0,
  "priorUnadjusted":0,"priorAje":0,"priorRje":0}]
```

落库读回形态确认（`remark` 字段承载，后端 `SELECT remark FROM checklist_responses`）：

```
[readback] rows=2 rows_with_amount_keys=2
[readback] probeA keys=['accountCode','currentAje','currentRje','currentUnadjusted',
                        'derivedSnapshot','label','priorAje','priorRje',
                        'priorUnadjusted','rowId','sectionKey','source']
[readback] probeA currentUnadjusted=12345.67
           derivedSnapshot={'currentUnadjusted': 12345.67, 'priorUnadjusted': 11000.0}
```

出方向 store-projection 端点返回（14 格逐值对上）：

```
adjudication_main_rows/probeA/current_unadjusted  = 12345.67
adjudication_main_rows/probeA/current_aje         = 100.0
adjudication_main_rows/probeA/current_rje         = 0
adjudication_main_rows/probeA/prior_unadjusted    = 11000.0
adjudication_main_rows/probeA/prior_aje           = 0
adjudication_main_rows/probeA/prior_rje           = 0
adjudication_main_rows/probeA/label               = '探针-批发收入'
adjudication_other_rows/probeB/current_unadjusted = 777.77
adjudication_other_rows/probeB/current_aje        = 0
adjudication_other_rows/probeB/current_rje        = 0
adjudication_other_rows/probeB/prior_unadjusted   = 0
adjudication_other_rows/probeB/prior_aje          = 0
adjudication_other_rows/probeB/prior_rje          = 0
adjudication_other_rows/probeB/label              = '探针-其他业务'
```

**修复前对比**：旧 `serializeRows` 只落 `{rowId,label,source,accountCode}`，金额在独立 item
`D4-1-{rowId}-{field}`，而 `build_store_projection_d41` 只读 `row.get(store_key)` ⇒ 6 金额恒 `None`
（切 OO 恒空表）。两区分别命中且不串区。

---

## 二、缺陷 C —— D4-13 两段正文进出方向

写入 `D4-13-process` / `D4-13-conclusion` 后，端点出方向：

```
d413_erp_check_fixed/process    = '探针-D4-13-核对过程正文（真栈）'
d413_erp_check_fixed/conclusion = '探针-D4-13-核对结论正文（真栈）'
```

**修复前对比**：`STORE_ITEM_IDS_D413_FIXED` 不被出方向装配循环遍历（它只遍历
`STORE_ITEM_IDS + STORE_ITEM_IDS_D45_FIXED`）⇒ 两键值恒 `''`（正文写不进 OO）。
固定键恒存在，故判据 P9-b 比**值**不比键数。

---

## 三、缺陷 C —— D4-35 其他业务收入核对表

写入 `D4-35-data`（dict store `{rows,periodAmount}`，行身份 `id`）后，
`build_combined_store_projection` 产出 **32 格**（overlay 前）：

```
other_revenue_check_rows/GTROW-D435-9001/amount          = 50000.0
other_revenue_check_rows/GTROW-D435-9001/content         = '探针-废料销售收入'
other_revenue_check_rows/GTROW-D435-9001/counter_account = '1002 银行存款'
other_revenue_check_rows/GTROW-D435-9001/date            = '2025-03-15'
other_revenue_check_rows/GTROW-D435-9001/check1..check6  = 'Y'（6 格）
（GTROW-D435-9002 同构 16 格，含 isAnomalous='Y' 异常样本）
```

**修复前对比**：`D4-35-data`（`STORE_ITEM_ID_D435_DICT`）既不在 `STORE_ITEM_IDS` 也不在
`STORE_ITEM_IDS_D45_FIXED` ⇒ 端点装配 **0 格**（切 OO 恒空）。P9-a 判据锁的正是 0 vs 32。

~~⚠️ **端点最终 values 里 D4-35 为 0 格**，原因是 `_overlay_with_published_substrate` 把 store
投影与 published substrate「求交」~~

🔴 **上面这条结论是错的，已于同日复核推翻（见 §六）**。根因是探针读响应时**取错了层级**：
投影体在 `data.projection.values`，不在 `data` 顶层。按错层级取当然是 0 格。
`overlay_store_on_baseline_projection` 的实际语义是**并集 + store 侧优先**，只丢「基线没有该键
**且** store 侧取值为 None」的占位 —— 它不会滤掉 store 的非空值。复核后 D4-35 在最终响应里
是 **32 格**，与对照组一致。

---

## 四、变异检验（判据不空转）

每项把实现改回缺陷形态 → 对应判据打红 → 还原：

| 判据 | 变异 | 结果 |
|---|---|---|
| P1 | 行清单剥掉金额键 | KILLED（投影 `currentUnadjusted=None`） |
| P4 | merge 不覆写行对象顶层 | KILLED（读回 100.0 ≠ OO 改后 777.77） |
| P8 | `all_store_item_ids()` 去掉 D4-35 | KILLED（门禁 exit 1，精确报 `D4-35-data` 漏项） |
| P8-前端 | `serializeRows` 金额不落行对象 | KILLED（valueCarrier 2 条红） |
| P9 | 单一口径去掉 D4-35/D4-13 | KILLED（D4-35 字段数 0 / D4-13 `process=''`） |
| P12 | `overridden` 改成 `stored≠derived` 错法 | KILLED（cellState 5 条红，含反证对照条） |
| P16 | 小计改跨表引用 | KILLED（模板 SUM 断言不成立） |

还原后：前端 33/33 全绿、`check_store_item_ids_fully_wired` 门禁绿（46 item 收敛）。

---

## 五、探针留下的数据

测试项目 D4 底稿写入了 4 条 store item（原 `D4-1-rows` ABSENT，其余 3 条原值 NULL）：
`D4-1-rows`（probeA/probeB 两行）、`D4-35-data`（2 行）、`D4-13-process`、`D4-13-conclusion`。
均为 `探针-` 前缀可识别数据，留作后续 E2E 种子；如需清除，PUT 同端点把 `remark` 置空。

---

## 六、Task 18 端点层复核（2026-09-23 同日，全栈在跑）

环境实测：后端 9980 healthy（`migration.applied_count=164`、`schema_drift.critical_count=0`）、
前端 3030 在跑、`audit-onlyoffice` 容器 healthy、PG/Redis healthy。

对**同一报障底稿**（project `0ec33ac9…` / wp `b3ab3c46…` / entry `xlsx/gt-d4-operating-revenue`）
重新拉 `GET …/store-projection`，按正确层级（`data.projection.values`）读最终 overlay 后的投影：

| 受管区 | 最终受管格数 | 内容 |
|---|---|---|
| `adjudication_main_rows/` | **21** | **7 个派生行** × 3 格（`label` + `current_unadjusted` + `prior_unadjusted`） |
| `adjudication_other_rows/` | **16** | 5 个派生行 × 3 格 + 手工行 `probeB` |
| `other_revenue_check_rows/`（D4-35） | **32** | 与修复前对照组的 32 格一致（修复前端点装配 0 格） |
| `d413_erp_check_fixed/` | **2** | `process` / `conclusion` 两键值 = store 正文（修复前恒 `''`） |

主营段真实金额（`row_keys.adjudication_main_rows` 同时含 4 个模板占位 `GTROW-D41MAIN-0008…0011`
与 7 个派生行 `xsheet-main-*`）：

```
xsheet-main-营业收入_批发_分销/current_unadjusted      = 153431246.06
xsheet-main-营业收入_批发_纯销/current_unadjusted      = 1528820416.32
xsheet-main-营业收入_批发_终端/current_unadjusted      = 89847600.45999998
xsheet-main-营业收入_服务费及其他/current_unadjusted   = 16389521.259999996
xsheet-main-营业收入_物业与租赁_物业/current_unadjusted = 175221.24
xsheet-main-营业收入_物业与租赁_租赁/current_unadjusted = 1100917.44
xsheet-main-营业收入_物流_仓储/current_unadjusted      = 1844830.88
```

**这就是用户报障的那 7 行主营金额**（报障时 HTML 有 7 行、OO 里 R8:R11 全空、小计 0）。
现在它们真的进了 projection，且是 overlay **之后**的最终值 —— 缺陷 B（派生行不落库）与缺陷 A1
（金额不随行落库）在真栈上均已通达。库里 `D4-1-rows` 现含 `{"rowId":"xsheet-main-营业收入_批发_分销",
"source":"tb","currentUnadjusted":…}` 形态的派生行，证明前端 Task 12 的落库在真实浏览器会话里已发生。

> 顺带实证了 Task 12 的孤儿清理：§五 写入的 `probeA`（`source='tb'` 但不在当前派生集里、无覆盖）
> 已被自动清掉，`probeB`（`source='manual'`）保留。

### 同时修正的一条错误结论

§三 原写「端点最终 D4-35 为 0 格，属既有 overlay 语义」。**那是探针读错层级导致的误判**，
已在 §三 就地划掉。真实语义：`overlay_store_on_baseline_projection` 是**并集 + store 优先**，
只丢「基线无该键且 store 值为 None」的占位，不会滤掉 store 非空值。

**教训**：`store_field_count`（1648）与 `field_count`（992）的差值不等于「store 被滤掉了多少业务值」
—— 它主要是模板占位行的空键收敛。拿两个计数的差去推断"数据被吞了"，在没读到真实键集之前
是没有依据的。

---

## 七、Task 18 浏览器层：真栈跑起来了，但被一个 **D4-2 侧的 materialize 500** 挡住

判据文件：`audit-platform/frontend/e2e/d4-1-adjudication-oo-visibility.spec.ts`
（`npx playwright test e2e/d4-1-adjudication-oo-visibility.spec.ts --workers=1`）
失败详情原始记录：`task18-browser-materialize-failure.json`（同目录）

### 跑到哪一步了

| 步骤 | 结果 |
|---|---|
| 登录 + 取 `store-projection` 主营区派生行 | ✅ 有非零派生行（未 skip） |
| 打开 D4-1（`.d4-tab-adjudication` 可见） | ✅ |
| **HTML 侧 7 行 label 全部在表格里可见** | ✅ `labelsMissingInHtml == []` |
| 点「在线编辑」→ `store-projection` | ✅ 200 |
| → `pending-mutations` | ✅ 200 |
| → `materialize` | 🔴 **500 ×3（重试三次全 500）** |
| OO canvas 上读 R8 起的格 | ⛔ 未到达 |

### 500 的真因（响应体原文，非推测）

```
error_code: excel_extract_identity_carrier_missing
message:   entry xlsx/gt-d4-operating-revenue: 契约声明动态行的首张表
           sheet='d42-managed' table='revenue_detail_rows' 一个 row identity 都没反读到
           —— 对应 Requirement 6.15 的「用户删除 identity 列」形态，contract 处置为拒绝，
           不得按中文表头或位置猜（Requirement 6.20）
```

### 归因：失败面在 D4-2，不在本 spec 改动的 D4-1 两区

对该 wp **最新 published substrate**（`working_paper_content_representation` gen=100，
今天 11:31 `content_commit`，`000000100-8b2de5620e1d.xlsx`，254026B）直接跑
`identity_inventory`（纯读字节，不经本 spec 任何改动）：

```
[D4-2 revenue_detail_rows] table=GT_D42_ROWS       col=W → row_uuids=26 条（GTROW-D42-0012…）
[D4-1 主营区]              table=GT_D41_MAIN_ROWS  col=W → row_uuids=4 条（GTROW-D41MAIN-0008…0011）
[D4-1 其他区]              table=GT_D41_OTHER_ROWS col=X → row_uuids=4 条（GTROW-D41OTHER-0014…0017）
```

⇒ **substrate 里 D4-2 的 identity 列是完好的（26 条）**。错误信息声称的「用户删除 identity 列」
形态在这份 substrate 上**不成立** —— 也就是说错误分类本身可能不准，真因还在 extract 侧
（binding 解析 / 受管区行范围 / staged 产物，尚未定位）。

**两条结论**：

1. 🔴 **这是一个当前真实存在的生产阻塞**：D4 整册 40+ 子 sheet 共用同一个
   `entry_id`，materialize 是共用的 ⇒ D4-2 侧反读失败会把**包括 D4-1 在内**的整册
   「在线编辑」全部打死。用户报障的「切 OO 后是空的」在浏览器层因此仍会复现，
   **但根因已经换了一个**：不再是本 spec 修的「store 里没有那些行/金额」（§六 已证明
   projection 侧完全通达），而是 materialize 阶段的 D4-2 identity 反读。
2. **不在本 spec 修复面**：本 spec 只改 D4-1 两区的前端存储形态 + store item 清单口径，
   未碰 D4-2 provider / binding / extract。归因证据即上面的 substrate 实测。

### 顺带发现一条可见性缺陷（独立于上面）

`excel_extract_identity_carrier_missing` 是 **domain error**，却以 **500** 返回。
`wp_sync_router.py` 自己的注释写明这类必须翻成 fail-visible 4xx（原文：「否则一路冒泡成
opaque 500，把整个 entry 的 store-projection/materialize 打成『服务器内部错误』而看不到
中文根因」）。这里正是它警告的形态：中文根因其实在响应体里，但 HTTP 语义是 500 ⇒
前端按「服务器内部错误」处理、还重试了 3 次。属另一范围，单独登记。

### 本条判据的价值

它**不是**空转：它把「切 OO 后看不到数据」从一句用户抱怨，拆成了三段可归因的事实 ——
HTML 侧行在（✅）、projection 侧值在（✅ §六）、materialize 阶段挂了（🔴 且根因在 D4-2）。
在此之前这三段是混在一起的，无法判断本 spec 修没修好。判据保留在仓库里，
D4-2 侧修好后它会自动转绿并完成需求 5.2 的 OO canvas 逐值对齐断言。

---

## 八、Task 18 第三轮复核（2026-09-24，全栈在跑）—— 🔴 推翻 §七 的归因结论

本节是**新增**章节（append-only），不回填改写 §一~§七。本轮范围：①核对已声明产物是否属实
②回归复核本 spec 既有判据 ③真栈 Playwright 重跑 ④对 500 的归因做对照实验。

### 8.1 已声明产物核对：全部属实

| 声明 | 核对结果 |
|---|---|
| 证据文档含变异检验登记 + 端点层两轮实测 | ✅ 存在（§四 / §六），非空壳 |
| `e2e/d4-1-adjudication-oo-visibility.spec.ts` | ✅ 存在，283 行真判据；`npx playwright test --list` 可正常收集（1 test） |
| `task18-browser-materialize-failure.json` | ✅ 存在，含三次 500 的完整响应体 |

⚠️ 一处**登记不全**（如实记录）：tasks.md 的变异检验表有 **12 项**，而本文件 §四 只逐项登记了
**7 项**（P1 / P4 / P8 / P8-前端 / P9 / P12 / P16）。缺 **P2 / P3 / P13 / P14 / P15** 五项 ——
这五项的变异与打红条数写在 tasks.md 的登记表里，但未落到本证据文件。需求 5.1 要求「红的证据
SHALL 登记（文件 + 条数）」，tasks.md 表里有文件与条数，故判为**登记位置不全、非证据缺失**。

### 8.2 回归复核：实跑数字与声称逐项一致

| 面 | 命令 | 实跑结果 | 与 tasks.md 声称对比 |
|---|---|---|---|
| 后端本 spec 5 新增 + 归档 spec D4-1 既有 5 + 门禁自测 = 11 文件 | `pytest`（逐文件路径） | ✅ **73 passed / 0 failed**（15.73s） | 声称 73 ✅ **完全一致** |
| CI 门禁 | `check_store_item_ids_fully_wired.py` | ✅ **exit 0**，46 item 全经 `all_store_item_ids()` 收敛 | 声称 exit 0 / 46 ✅ 一致 |
| 前端零回归集 13 文件 | `vitest run`（逐文件列出） | ✅ **13 files / 239 passed / 0 failed**（4.33s） | 声称 239 ✅ **完全一致** |

另：以 `-k "d4_1 or d4_store or d4_35 or d413 or store_item"` 宽选跑 `tests/workpaper_sync/` 得
**156 passed / 1 failed**。唯一失败项 =
`test_task42_h1_grouped_dynamic_pilot_pg.py::test_disposal_store_item_is_empty_across_the_whole_database`
—— 它是 **H1 固定资产处置 pilot** 的「真实库数据出现即打红」哨兵（断言 `H1-8-rows` 全库 0 行，
现测到 wp `c71b7c54…` 有 51B）。与 D4 无关、与本 spec 改动文件无交集，不计入本 spec 分母。

### 8.3 真栈 Playwright 第三轮：500 复现，且步骤 1/2 仍绿

环境实测：后端 9980 healthy（PG/Redis ok）、前端 3030 在跑、`audit-onlyoffice` 容器 healthy
（Up 36h）。`npx playwright test e2e/d4-1-adjudication-oo-visibility.spec.ts --workers=1`：

| 步骤 | 结果 |
|---|---|
| 登录 + `store-projection` 取到非零派生行（未 skip） | ✅ |
| **HTML 侧 7 行 label 全部在表格里可见**（`labelsMissingInHtml == []`） | ✅ |
| 切「在线编辑」→ `store-projection` / `pending-mutations` | ✅ 200 / 200 |
| → `materialize` | 🔴 **500 ×3** |
| OO canvas 逐值断言 | ⛔ 未到达 |

失败 JSON 已刷新（`captured_at` = `2026-09-23T23:07:43.171Z`），错误码与 §七 同：
`excel_extract_identity_carrier_missing`，文案报 `sheet='d42-managed' table='revenue_detail_rows'`。

### 8.4 🔴 归因对照实验 —— §七 的「失败面在 D4-2 / 属另一范围」**两条都是错的**

#### (a) 错误文案里的 D4-2 是**硬编码的首张动态表**，不是失败的那个 binding

`excel_extract.py:1253`：

```python
dynamic_tables = [(sheet.sheet_key, table.table_key) for sheet in contract.sheets
                  for table in sheet.tables if table.has_dynamic_rows]
if dynamic_tables and inventory.resolved_sheet_by is None:
    first_sheet, first_table = dynamic_tables[0]      # 🔴 恒取第 0 个
    raise IdentityCarrierMissingError(f"...首张表 sheet={first_sheet!r} table={first_table!r}...")
```

D4 契约的 `dynamic_tables[0]` 恒为 `('d42-managed', 'revenue_detail_rows')`，**无论哪个 binding
失败，文案都会报 D4-2**。⇒ 单凭响应体断定「失败面在 D4-2」没有依据。

#### (b) 钩住载体门后，真正失败的 binding 是 **D4-1 其他区**

`assert_identity_carriers_usable` 收的是**单个** inventory。给它套 trace 后（探针
`backend/scripts/_d42_stage.py`，真 substrate + 真库 store payload + 真 adapter.materialize）：

```
🔴 载体门失败于第 42 次调用：
   sheet='营业收入审定表D4-1'  table_ref='A14:X17'  uuid_col='X'
   uuids=0  resolved_by=None  empty_rows=4
```

`sheet='营业收入审定表D4-1'` + `ref='A14:X17'` + `col='X'` ⇒ 这是 **`GT_D41_OTHER_ROWS`
（D4-1 其他业务收入区）**，正是本 spec 改动的两区之一。**不是 D4-2。**

对照：同一 binding 在**未经 materialize 的 published substrate**（gen=100）上是好的 ——
探针 `_d42_repro.py` 逐 binding 复刻生产 `region.row_span` 口径，**36 个 binding 全部 ok**：

```
GT_D42_ROWS        W  12..37  非空 26  空 0  ok
GT_D41_MAIN_ROWS   W   8..11  非空  4  空 0  ok
GT_D41_OTHER_ROWS  X  14..17  非空  4  空 0  ok
…（共 36 个，[真正会抛错的 binding] 无）
```

⇒ 零 UUID 的状态**不在 substrate 上**，是 materialize 过程中产生的。

#### (c) A/B 对照实验：阻塞由**本 spec 的派生行入 store** 触发

同 substrate / 同 contract / 同 adapter，**只差 store payload 一项**：

| 组 | store payload | projection 行数 | materialize 结果 |
|---|---|---|---|
| **A（现状）** | 真库原样，含 `D4-1-rows` | main 7 / other 6 | 🔴 `IdentityCarrierMissingError` @ `sheet='营业收入审定表D4-1' ref='A14:X17' col='X' uuids=0` |
| **B（反事实）** | 摘掉 `D4-1-rows`，回到本 spec 之前形态 | main 0 / other 0 | ✅ **OK，`managed_field_count=1294`** |

**A 红 B 绿** ⇒ 阻塞是本 spec Task 12/14「派生行入 store」的**直接下游后果**，不是「另一范围的
既有缺陷」。机制（与观测一致）：受管区要落的行数超过模板 Table ref 覆盖的行数 ⇒ materialize
在**同一 sheet** 的主营区插行 ⇒ 其他区数据被下推，但其他区的 Excel Table ref 仍停在
`A14:X17` ⇒ 那个陈旧窗口里现在是主营区的行（UUID 在 W 列不在 X 列）⇒ X 列 4 行全空
（`uuids=0 empty_rows=4`，与观测逐项吻合）。

> 措辞节制：插行位移的精确算术（插几行、其他区被推到哪）本轮**未**逐行验证，
> 上面只主张「陈旧 Table ref + 同 sheet 插行」与观测到的 `ref='A14:X17' / uuids=0 /
> empty_rows=4` 一致，不主张已完成位移链的逐步证明。

### 8.5 结论与 Task 18 判定

1. **§七 的两条结论予以推翻**（本节就地更正，§七 原文保留作审计轨迹）：
   * ~~失败面在 D4-2~~ → 实为 **D4-1 其他区 `GT_D41_OTHER_ROWS`**；
   * ~~属另一范围，本 spec 不修~~ → **由本 spec 的改动触发**（A/B 实验），不能声称与本 spec 无关。
2. **缺陷所在层**仍不是本 spec 的需求面：「同 sheet 插行后 sibling 受管区 Excel Table ref 未同步
   维护」属 materialize 行位移层，归 `excel-structural-row-insertion-and-shift-aware-verification`
   / `excel-workbook-wide-row-change-propagation` 两 spec 的面。本 spec 的 requirements 未覆盖
   Table ref 维护 ⇒ **本轮不擅自修**，但**必须**按「本 spec 触发的阻塞」登记，而非「别人的 bug」。
3. **Task 18 保持 `[ ]*`**：需求 5.2 的 OO canvas 逐值对齐与需求 5.3 的覆盖往返**均未实测**，
   代码已改但未实测。解除条件 = 受管区插行时同步更新同 sheet 其他受管区的 Table ref
   （或 materialize 侧改为按 ref 重算而非信任陈旧 ref）。
4. **可观测性缺陷（独立，沿用 §七 的登记）**：`excel_extract_identity_carrier_missing` 是
   domain error 却以 **500** 返回。本轮新增一条同类事实：它的**文案还会指错对象**
   （恒报 `dynamic_tables[0]`）—— 两者叠加时，排障者会被导向完全无关的底稿。

### 8.6 本轮探针与清理

| 文件 | 性质 |
|---|---|
| `backend/scripts/_d42_repro.py` | 前序会话留下，逐 binding 复刻生产 row_span 口径（published substrate） |
| `backend/scripts/_d42_stage.py` | 前序会话留下，钩载体门 + 真 materialize，定位真正失败的 binding |
| `backend/scripts/_d42_trigger.py` | **本轮新增**，A/B 归因对照实验；结论已登记于 8.4(c)，用完即删 |
| `backend/_d42*.txt` | 前序会话的原始输出（UTF-16 混编，可读性差，结论已转录入本节） |

`_` 前缀 = 一次性脚本，按规约用完即删。本轮删除 `_d42_trigger.py` 与两个 `_d42_*_tmp/` 产物目录；
前序会话的 `_d42_repro.py` / `_d42_stage.py` / `_d42*.txt` 保留待其归属会话处置（它们是 8.4(b)
的复现脚手架，删早了 D4-2 侧排障要重写）。

---

## 八、materialize 500 的逐层定位与修复（§七 的续）

判据：`backend/tests/workpaper_sync/test_sibling_table_ref_row_shift.py`（4 passed + 1 xfail）

### 先推翻 §七 的一个归因

§七 写「失败面在 D4-2，不在本 spec 改动的 D4-1 两区」。**这个归因是错的**，来源是错误文案：

```python
# excel_extract.py:1252
if dynamic_tables and inventory.resolved_sheet_by is None:
    first_sheet, first_table = dynamic_tables[0]     # ← 只是「契约里第一张动态表」
    raise IdentityCarrierMissingError(f"...首张表 sheet={first_sheet!r} table={first_table!r}...")
```

判定量是**当前 binding** 的 `inventory.resolved_sheet_by`，而文案打印的是 `dynamic_tables[0]`
（恒为 `d42-managed/revenue_detail_rows`）。两者无关 ⇒ 任何 binding 失败都会被报成「D4-2 坏了」。

钩住载体门打印每次 inventory 后拿到真身：

```
🔴 载体门失败于第 42 次调用：sheet='营业收入审定表D4-1' table_ref='A14:X17'
   uuid_col='X' uuids=0 resolved_by=None empty_rows=4
```

失败的是 **D4-1 其他区**。另外对 published substrate 逐 binding 复刻生产口径
（`raw_uuid_by_row = {row: cells[uuid_col+row] for row in region.row_span}`）扫 36 个 binding：
**全部非空、零空行** ⇒ substrate 没问题，失败发生在 materialize 写出的中间产物上。

### 三层缺陷，逐层实证

**① 同 sheet 兄弟 Table 的 ref 不随插行位移（已修）**

D4-1 主营 `A7:W11` / 其他 `A14:X17` 同在一张 sheet。主营段 7 个派生行 > 4 行占位 ⇒ 需插行 ⇒
`_try_single_pass_materialize` 因「任一 binding 需插行」**decline** ⇒ 回落**逐趟链式**
（`adapters/excel.py`：`current = target`，上一趟产物当下一趟 substrate）。
而 `_grow_managed_table_ref` 只更新 `plan.table_part`（**本 binding** 那一个 Table part）：

```
修复前：其他区 ref  A14:X17 → A14:X17（主营插了 7 行，应为 A21:X24）
```

于是其他区那趟按旧 ref 读 14..17 —— 那里已是主营区的新行，X 列无 UUID ⇒ 500。
**修复**：新增 `_shift_sibling_table_refs`，走 worksheet rels 找同 sheet 全部 Table part，
用 `shift.shift()` 对首末行各调一次（天然覆盖：整体下移 / 跨插入点扩张 / 上方不动）。
⚠️ 兄弟表末行边界是 `>= insert_at`，**不是**本 binding 的 `>= insert_at - 1` —— 后者是
「追加插行紧贴本表末行」的本表专属语义。

**② `_GT_SYNC` 里兄弟区的 footer 坐标不随插行重冻结（已修）**

修①后露出下一层：`FooterAnchorDriftError: footer marker '小计' 实测在第 25 行，
representation 冻结的 GT_FOOTER_ROW=18`。`_refresh_gt_sync_runtime_binding` 只放行
`GT_FOOTER_ROW_{managed_tid}`，注释写「D4-1 主营插行只移位 `_D41MAIN`，不误动 `_D41OTHER`」
—— 那句话把「同 sheet 兄弟」和「不同 sheet」混成一类了：不同 sheet（D42 vs D43）确实不该动，
**同 sheet 必须动**（插行是物理的）。
**修复**：按 worksheet rels → 兄弟 Table displayName → `GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS`
平行清册，算出**同 sheet 全部 template_id**，对这组键放行；移不移仍由 `shift.shift` 按各自
行号与插入点的关系决定。

**③ verify 的归一化表达不了「同 sheet 多趟累积插行」（未修，已 xfail(strict) 登记）**

修①②后 materialize 产物本身已正确（判据 3：两区 13 个派生行全部能反读回来；判据 4：
`GT_FOOTER_ROW_D41OTHER` 与三个 per-region definedName 都按同一 delta 同步）。但生产
coordinator 在 materialize 之后还要跑 `verify_unmanaged_regions`，那里换成：

```
adapter_unmanaged_region_drift: managed_sheet_unmanaged_cells 280 → 340
```

根因：D4-1 两区同 sheet 且**两趟都插行**（主营 7 + 其他 2）⇒ 同一个 sheet part 被插两次。
而 verify 的归一化是「按 `region.table_key` 取**本表那一趟**的 `row_shift` 反向归一化」
（`per_table_shift.get(region.table_key, (None, ()))`），表达不了累积位移。
**已排除「调用方少传声明」**：判据里加了前置断言，证明 `per_table_shift` 确实随产物带出且
含主营那趟，喂进去后仍 280 → 340。
⇒ 真修需要让 verify 支持 per-sheet 累积 shift，或让同 sheet 多区在**一趟**里完成全部插行。
两者都动核心模型，须独立立项。

### 一条方法论教训

判据 3（`materialize` + `extract` 全绿）与生产 500 并存过一段时间 —— 因为判据只覆盖了
adapter 两个方法，而生产路径在它们**之后**还有 `verify_unmanaged_regions`。
「判据绿而生产红」从来不是玄学，是判据没覆盖真实路径。判据 5 就是补这一段而加的。

### 验证

| 面 | 结果 |
|---|---|
| 新判据 `test_sibling_table_ref_row_shift.py` | 4 passed + 1 xfail(strict) |
| 变异检验 | 2/2 KILLED（去掉兄弟 ref 位移 → 判据 2+3 红；footer 放行改回单 tid → 判据 3+4 红） |
| 零回归 | `pytest tests/workpaper_sync -k "d4 or D4 or materialize or shift"` ⇒ **906 passed / 1 xfailed / 0 failed** |
| diagnostics | 0 |

### 对 Task 18 浏览器层的影响

浏览器层 e2e 的错误已从 `excel_extract_identity_carrier_missing` 前进到
`adapter_unmanaged_region_drift` —— ①② 确实修好了，但因 ③ 未修，
**D4-1 切「在线编辑」目前仍是 500**，真栈①/② 继续阻塞。

---

## 九、第三层修复完成 —— 浏览器层真栈**通过**，报障闭环

判据：`audit-platform/frontend/e2e/d4-1-adjudication-oo-visibility.spec.ts`
`npx playwright test … --workers=1` ⇒ **1 passed (1.1m)**
原始证据：`task18-browser-oo-visibility.json`（同目录）

### OO canvas 上真实读回的格（报障对照）

```
activeSheet = 营业收入审定表D4-1
B8  = ''                 ← 模板 4 个占位行（projection 里没有它们，保持空）
B9  = ''
B10 = ''
B11 = ''
B12 = '153431246.06'     ← 7 个主营派生行金额，与 projection 逐值相等
B13 = '1528820416.32'
B14 = '89847600.46'
B15 = '16389521.26'
B16 = '175221.24'
B17 = '1100917.44'
B18 = '1844830.88'
B19 = '=SUM(B8:B18)'     ← 合计公式已正确扩张，把新行包进来
console_errors = []
```

**对照用户报障原文**：「表格视图下是有数据的，但点击到在线编辑、切换到 OO 后，里面是空的」
—— 真栈形态是「HTML 主营段 7 行有金额，OO 里 R8:R11 全空、小计显示 0」。
现在 OO 里 **B12:B18 有那 7 行真实金额、合计公式 `=SUM(B8:B18)`**。报障闭环。

### 第三层修了什么（三处缺一不可）

`verify_unmanaged_regions` 的归一化原本按 `region.table_key` 取**单趟** `row_shift`，
而 D4-1 两区同 sheet 且**两趟都插行**（实测 main `insert_at=12 count=7` /
other `insert_at=25 count=6`）⇒ 同一个 sheet part 被插两次，累积映射表达不了。

| # | 文件 | 改动 |
|---|---|---|
| ③-1 | `excel_row_shift.py` | 新增 `CompositeRowShift`：链式 `unshift`（**逆序**还原）/ 正序 `shift` / `inserted_rows`（每趟新行经其后各趟 `shift` 映射到 after 口径后取并集）+ `unextend_total_formula_chain`。**单趟仍传原 `RowShiftPlan`** ⇒ 单区/Word 路径逐字节不变 |
| ③-2 | `excel_workbook_row_change.py` | `normalise_propagated_part` 的逆替换改为**从链尾往前**：同一处被两趟各改一次时声明成链（`$A$18→$A$25`、`$A$25→$A$31`），顺序反了会停在中间态 `$A$25` ⇒ `workbook_and_styles` 误判 drift。新增 `_chain_depth` 排序键，无链时退化为原「长的先替换」 |
| ③-3 | `adapters/excel.py` | 新增 `_sheet_cumulative_shift` + verify 里 `sheet_of_table` 映射：按 `sheet_part` 分组合成 composite；**合并 `total_formula_rows` 时把每趟的中间口径映射回最初 before** —— 其他区合计行在模板是 18，而其他区那趟声明的是 **25**（= 18 + 主营插的 7），verify 用最初 before 坐标比对，拿 25 永远不中 ⇒ 合计扩张不被还原 |

### 错误码演进（逐层剥开的完整轨迹）

```
excel_extract_identity_carrier_missing      ← ①兄弟 Table ref 不位移
  → excel_materialize_footer_anchor_drift   ← ②_GT_SYNC 兄弟区 footer 不重冻结
  → adapter_unmanaged_region_drift           ← ③-2 workbook_and_styles（链式声明顺序）
     (workbook_and_styles 3/3 项内容不等)
  → adapter_unmanaged_region_drift           ← ③-1 累积 shift（项数都对不上）
     (managed_sheet_unmanaged_cells 280→340)
  → adapter_unmanaged_region_drift           ← ③-3 合计行口径（项数已对齐、内容不等）
     (managed_sheet_unmanaged_cells 292/292)
  → ✅ 全绿
```

### 影响面：不止 D4-1

从 provider 的 `instrumentation_specs()` **动态**统计（不硬编码清单）：D4 共 **30 个受管
sheet**，其中 **5 张是同 sheet 多受管区**，全部适用本次修复：

| 受管 sheet | 区数 | 受管区（首数据行升序） |
|---|---|---|
| 销售退货检查表 D4-20 | **3** | D420PROV(H) 25..29 / D420CUR(P) 34..36 / D420POST(Q) 40..42 |
| 其他业务收入合同测算表 D4-34 | 2 | D434RENT(L) 13..17 / D434CONS(M) 20..24 |
| 其他业务收入截止性测试 D4-36 | 2 | D436FWD(L) 16..23 / D436BWD(M) 36..43 |
| 营业收入审定表 D4-1 | 2 | D41MAIN(W) 8..11 / D41OTHER(X) 14..17 |
| 重要客户结构分析 D4-9 | 2 | D49C(W) 13..22 / D49P(X) 27..36 |

D4-20 是**三区**（中间区既被上区推、又要推下区），与两区不是同一个边界情形，已单独覆盖。

### 判据与验证

`backend/tests/workpaper_sync/test_sibling_table_ref_row_shift.py` —— **14 passed**：

| 判据 | 覆盖 |
|---|---|
| 1 前提 | 两区同 sheet、主营在其他区之上、要落行数 > 模板占位 ⇒ 必插行 |
| 2 | 上区插行后兄弟区 Table ref 必须下移（修复前 `A14:X17 → A14:X17`） |
| 3 | 双区真 adapter materialize + extract，13 个派生行全部反读回 |
| 4 | 兄弟区 `GT_FOOTER_ROW_D41OTHER` + 三个 per-region definedName 按同一 delta 同步 |
| 5 | **`verify_unmanaged_regions` 通过**（补的就是「判据绿而生产红」那一段） |
| 6 ×5 | **参数化覆盖全部 5 张同 sheet 多区底稿**（清单从 provider 动态算，新增受管区不会漏） |
| 7 ×3 | **单区路径纯增量**：单趟返回原 plan 对象本身（`is` 判等）、`plans` 顺序=逐趟顺序、totals 映射回最初 before、单区 sheet 零改动且 entries 逐字节不变 |

| 面 | 结果 |
|---|---|
| 变异检验 | 3/3 KILLED（去兄弟 ref 位移 → 8 条红含全部 5 张参数化；footer 放行改回单 tid → 2 条红；`_writeIfChanged` 去幂等 → 9 条红） |
| 零回归（覆盖改动全路径） | `pytest tests/workpaper_sync -k "d4 or D4 or materialize or shift or verify or propagat or unmanaged"` ⇒ **1032 passed / 0 failed** |
| 位移/传播专项 5 文件 | 190 passed |
| diagnostics | 0 |

### 一处如实登记的观察（不是缺陷）

OO 里 `B8:B11`（模板 4 个占位行）是**空的**，7 个派生行落在 `B12:B18`。原因：projection 的
`row_keys` 只含 7 个派生 rowId，不含模板占位 UUID（`GTROW-D41MAIN-0008…0011`），而
materialize 对不在 projection 里的既有行不写任何东西 ⇒ 占位行保持模板原样。
合计 `=SUM(B8:B18)` 已把它们包含，数值正确。属既有 overlay/占位语义，非本次修复面；
若审计上要求表首无空行，需另立「占位行复用/压缩」范围。

---

## 十、覆盖面论证 + D4-2 e2e 失败的归因

### 为什么「D4-1 真栈通过」已经覆盖到 D4 全部受管区

不是逐张跑 e2e 才算覆盖 —— **materialize 是整册的**：
`ExcelSyncAdapter._materialize_within_scope` 对 `bindings`（primary + 35 sibling）
`for index, binding in enumerate(bindings)` **逐趟**跑 `materialize_projection`，
`verify_unmanaged_regions` 同样 `for binding, region in regions_by_binding` **逐 binding 全跑**
并逐个 `assert_equivalent()`。

⇒ D4-1 e2e 拿到 `materialize` **200** 这一件事本身就意味着：**36 个 binding 的
plan → 位移 → Table ref 增长 → `_GT_SYNC` 重冻结 → workbook 传播 → 逐 binding verify
全部通过**，其中包含 5 张同 sheet 多受管区底稿（D4-20 三区 / D4-34 / D4-36 / D4-1 / D4-9）。
任何一个 binding 在这条链上失败都会让整个 materialize 500 —— 这正是修复前发生的事
（D4-1 其他区反读不到 identity ⇒ 整册在线编辑全死）。

配套的**结构层**覆盖由判据 6 承担：它从 `instrumentation_specs()` 动态算出多区清单，
逐张验证「上区插行 ⇒ 下方每个兄弟区 ref 整体下移 + 其它 sheet 一处不动」，
5 张全覆盖且变异检验全部打红。

### D4-2 的 `g5-1-d4-unified-path` e2e 失败 —— 归因：OO 交互层，非本次修复

`npx playwright test e2e/g5-1-d4-unified-path.spec.ts --workers=1` ⇒ 1 failed（10.0m）
失败断言：`html_dom_roundtrip.store_mirrored` / `marker_visible`。

evidence（`.kiro/specs/d4-revenue-matrix-bidirectional/evidence/g5-1-d4-unified-path/`）
显示**后端侧全部通过**：

```
store-projection            200
materialize                 成功（room_id=a41f914a…，materialize_has_jwt_token=True）
confirm_descriptor_200      True
host_mounted                True
OO canvas 写 A12            inserted=true entered=true（activeSheet=主营业务收入明细表D4-2）
forcesave                   HTTP 202, cs_error=0, cs_outcome=accepted
d2_sync_hits                0（不打旧路径）
callback_url_keys           room_id / generation / doc_key / route_credential_id / route_token 五项齐
```

卡点在这一句（宿主自己的状态文案）：

```
host_status = 等待 OnlyOffice 回传结果超时，保存尚未落地。
              请点「重试回写」重新发送保存命令，或退出在线编辑后重新进入。
switched_to_html = false   marker_visible = false   store_mirrored = false
dom_error = Test timeout of 600000ms exceeded
```

⇒ **forcesave 已被 OO 接受（`cs_error=0`）但 OO 没在超时内回传 `onlyoffice-callback`**，
后端那一侧的代码根本没被执行。三条独立证据说明与本次修复无关：

1. **后端全路径已通**：`materialize` 成功（含 36 binding 的位移 + verify）、`confirm-descriptor`
   200、`forcesave` accepted —— 我改的那三层全部在这次运行里跑过且通过。
2. **同一条路径上 D4-1 e2e 通过**：它走同样的 materialize/verify，若改动破坏了这条链，
   D4-1 也会失败。
3. **1032 passed / 0 failed**：`-k "d4 or D4 or materialize or shift or verify or propagat
   or unmanaged"` 覆盖改动的全部代码路径。

网络侧已排除：`docker exec audit-onlyoffice curl host.docker.internal:9980/api/health` ⇒ **200**
（OO 容器回调宿主机是通的）。

**可疑点（留给后续排查，不在本次范围）**：evidence 里 `host_dirty_before_forcesave = False`
—— e2e 在 OO canvas 里写了 A12，但宿主没收到「文档已改」（dirty）。若 OO 认为文档未修改，
forcesave 会被接受却不产生新版本 ⇒ 自然没有 callback ⇒ 等待超时。这属 OO 交互层
（`asc_insertInCell` / `asc_enterText` 是否真的置位 `asc_isDocumentModified`），
g5-1 系列 spec 里对此已有多重写入尝试的兜底逻辑，说明它本身就是个不稳定点。

⚠️ **如实登记，不标绿**：D4 的 **OO→HTML 回写往返（forcesave → callback → merge）在本轮
没有拿到真栈证据**。本轮拿到的是 **HTML→OO 方向的完整真栈闭环**（报障本身的方向）。

### 零回归的覆盖口径（说明为什么不是跑「全套」）

`pytest tests/workpaper_sync/ tests/workpaper_sync_frontend/` 全套（8600+ 用例）在本机
**超过 30 分钟未跑完**，故改为**按改动面精确覆盖**，两条互补：

1. **按关键词宽选**：`-k "d4 or D4 or materialize or shift or verify or propagat or unmanaged"`
   ⇒ **1032 passed / 0 failed**。
2. **按 import 关系补齐**：grep `backend/tests/**` 里 import 了本次改动 5 个模块
   （`excel_row_shift` / `excel_workbook_row_change` / `excel_materialize` / `excel_extract` /
   `adapters.excel`）的测试文件，把宽选没覆盖到的补跑 ——
   `test_excel_row_insertion_wiring.py` / `test_json_cell_roundtrip.py` /
   `test_post_durable_failure_reason_is_visible.py` / `test_projection_first_publication.py` /
   `test_single_pass_materialize.py` / `test_d4_1_footer_anchor_per_region.py`
   ⇒ **148 passed / 0 failed**。

另有位移/传播专项 5 文件 **190 passed**、本次新判据 **14 passed**。

### 本次改动清单（5 个源文件 + 1 个新判据文件）

| 文件 | 改动 |
|---|---|
| `excel_materialize.py` | 新增 `_sheet_table_parts`（worksheet rels → 同 sheet 全部 Table part）/ `_shift_sibling_table_refs`；`_grow_managed_table_ref` 末尾调它；`_refresh_gt_sync_runtime_binding` 的 footer 放行集从 `{managed_tid}` 扩为「同 sheet 全部 tid」 |
| `excel_row_shift.py` | 新增 `CompositeRowShift` + `unextend_total_formula_chain`，并加入 `__all__` |
| `excel_extract.py` | `unextend_total_formula` → `unextend_total_formula_chain`；`row_shift` 类型标注加 `CompositeRowShift` |
| `excel_workbook_row_change.py` | `normalise_propagated_part` 的逆替换排序加 `_chain_depth`（链尾优先） |
| `adapters/excel.py` | 新增 `_sheet_cumulative_shift`；verify 里建 `sheet_of_table` 并改走它 |
| `tests/workpaper_sync/test_sibling_table_ref_row_shift.py` | 新增，14 判据（含 5 张参数化 + 3 条单区纯增量纪律） |

### 清理

一次性探针脚本全部删除（`_p2_probe` / `_mut_p2` / `_t18_probe` / `_t18_attrib` / `_d42_repro` /
`_d42_stage` / `_wbdiff` / `_show_ev` / `_g5d4` 及其 tmp 目录）。
另删掉 `g5-1-d4-unified-path.spec.ts` 跑测时在 `.kiro/specs/d4-revenue-matrix-bidirectional/`
下重建的 evidence 目录 —— 那个 spec 已归档，e2e 里的 `EVIDENCE_DIR` 仍指向 active 路径
（既有小瑕疵，登记不修；归因结论已在本文档 §十）。

### 附：顺带修掉的一条可见性缺陷（错误信息指错对象）

`excel_extract.assert_identity_carriers_usable` 的载体缺失分支原本打印
`dynamic_tables[0]` —— D4 契约第 0 项恒为 `('d42-managed','revenue_detail_rows')`，于是
**无论哪个 binding 失败，文案都指向 D4-2**。真栈上真正失败的是 D4-1 其他区
（`table_ref='A14:X17' uuid_col='X'`），排查因此先绕去核对 D4-2 的 identity 列（结果是好的），
白走一圈。**错误信息指错对象，比信息少更贵。**

已改为打印**当前 binding 的真实身份**（`table_sheet` / `table_ref` / `uuid_column` /
空 UUID 行数），并显式提示第二种可能：「也可能是 Table ref 与实际数据行错位（同 sheet 多受管区
上区插行后未同步维护下区 ref），那时 identity 列本身是好的 —— 请先比对 ref 区间与真实 UUID
行号，不要只看列是否存在」。

回归：`pytest tests/workpaper_sync -k "identity_carrier or carrier_missing or identity or extract"`
⇒ **729 passed / 0 failed**（既有判据不依赖该文案的具体措辞）。

> 另一条**未修**的同类问题如实留在此处：该 domain error 以 **HTTP 500** 返回，而
> `wp_sync_router.py` 自己的注释明写这类必须翻成 fail-visible 4xx（「否则一路冒泡成
> opaque 500…看不到中文根因」）。现状导致前端按「服务器内部错误」处理并自动重试 3 次。
> 属 router 错误分类范围，不在本次改动面。

---

## 十一、🔴 纠正 §十 末尾那条「未修的 500」—— 真因不在后端分类，在前端认不出码

§十 末尾（上一段引用块）把「materialize domain error 以 HTTP 500 返回」记成了缺陷，并说
`wp_sync_router.py` 的注释要求这类必须翻 4xx。**这条归因有两处错**，本节推翻并给出实证。

### 错误一：引用错了注释

那条「否则一路冒泡成 opaque 500…看不到中文根因」的注释针对的是 **`ContractDriftError`**，
不是 `classify_materialize_rejection` 的默认分支。后者的 docstring 写得很清楚：未登记的
失败**故意**返回 500 而不是默认 400 —— 「未知失败必须 fail visible」。把未知失败降成 4xx
恰好会让它变安静。所以**不改** `classify_materialize_rejection` 的 500 默认。

### 错误二：真因是前端根本读不到 `error_code`

真栈实测（2026-09-24，后端 9980，admin token）后端有**两种错误形状并存**：

```
GET /api/projects/00000000-0000-0000-0000-000000000000
  => 404  {"code":404,"message":"项目不存在"}       ← 业务 HTTPException，无 detail 键
GET /api/projects/{id}/workpapers/{id}/render-config
  => 404  {"detail":"Not Found"}                     ← starlette 原生，有 detail
```

`backend/app/main.py:654` 注册的是 `fastapi.HTTPException` → 平台全局
`http_exception_handler`，它把 `exc.detail` 放进 **`message`**（`{code, message}` 是平台统一
信封）。dict 形态的 detail 原样透出，所以 `message` 也可以是 dict。

而前端下游**普遍只读 `detail`**：

| 读取点 | 后果 |
| --- | --- |
| `utils/errorHandler.ts::handleApiError:43`（平台统一错误处理器，全仓大量视图在用） | 400/409/503 的后端中文根因全部退化成兜底文案；422 的 `AI_CONTENT_NOT_CONFIRMED` / `CROSS_MODULE_CONFLICT_UNRESOLVED` 特化分派**从未生效** |
| 几十个视图里的 `e?.response?.data?.detail` | 同上 |
| `sync/useWorkpaperSyncBridge.ts::readWireError` | `classifySyncFailure` 的 error_code 分派在生产从未生效；domain error 落「本地失败」桶被判可重试而重试 3 次 |

所以 §十 看到的「前端按服务器内部错误处理并重试 3 次」**不是** 500 造成的 —— 就算后端返回
422，前端一样读不到 `error_code`，一样走兜底。这才是那条现象的真因。

一个反差可以佐证它是「同一知识被重复实现 N 次、只有 1 处正确」：`utils/http.ts` 里的
`extractErrorDetail`（第 187 行）**早就写对了** `detail ?? message`，所以拦截器自己弹的全局
toast 一直是好的 —— 坏的全是下游各自手写的那几十份。

### 修法：收敛到拦截器一处做信封适配

前端 axios 拓扑实证：`utils/http.ts` 是**唯一**业务实例（`services/*` 含 `apiProxy`、
sync 的 `workpaperSyncApi` 全部 `import http from '@/utils/http'`；`stores/auth.ts` 的
`authHttp` 只服务 login/refresh/logout）。因此在错误拦截器里 normalize 一次即可覆盖全仓：

* 新增 `export function normaliseErrorEnvelope(response)`：仅当 `detail === undefined &&
  message !== undefined` 时回填 `detail = message`；跳过 `Array` / `Blob` / 非对象。
  「只在缺失时回填」是必需的 —— starlette 原生 404 的 `detail` 与 422 的字段级错误**数组**
  都不能被 `message` 那句「请求参数校验失败」覆盖。
* 接线在错误拦截器最开头（`removePending` 之后、任何 `return`/`reject` 之前），
  保证每条错误出口的 `data` 形状一致。与成功路径「统一解包 ApiResponse」对称。

**没有改后端**：`{code, message}` 是平台信封的有意设计，仓里已有两处判据注释为证
（`test_signed_report_rollback_protection.py:284`「全局 http_exception_handler 把
HTTPException.detail 放到 message 字段」、`test_audit_log_enhanced.py:583` 同款）。
前端按 FastAPI 原生 `detail` 的假设才是错的那一方。

### 判据与变异

`audit-platform/frontend/src/utils/__tests__/errorEnvelopeNormalisation.spec.ts` —— **12 passed**，三层：

1. 纯函数 6 条形状：字符串 detail 回填 / **dict 恢复成对象**（不是 `String()` 化）/
   starlette 404 不动 / 422 数组不被覆盖 / `detail: null` 视为已有值 / 非对象载荷不崩；
2. **拦截器接线** 1 条：真实取 `http.interceptors.response.handlers[0].rejected` 跑一遍
   （用 `_silent` + status 409 让它在弹 toast/重试之前 reject，断言的是「入口处已 normalize」）；
3. `handleApiError` 端到端 5 条：400 / 409 / 422×2 / 503 —— 断言弹出的是**后端中文根因**
   而不是兜底文案，且两条 422 `error_code` 特化分支真的命中。

变异 **3/3 KILLED**：

| 变异 | 结果 |
| --- | --- |
| M1 拦截器不调用 `normaliseErrorEnvelope` | KILLED（精确杀接线那 1 条） |
| M2 去掉「仅在缺失时回填」改成无条件覆盖 | KILLED（杀 422 数组 + `detail: null` 两条） |
| M3 `d.detail = String(d.message)` | KILLED（杀 6 条 —— dict 形态 + 409/422×2/503 端到端 + 接线） |

`bridgeFailureRealEnvelope.spec.ts`（sync 桥侧，按真实 `{code,message}` 信封构造）**9 passed**（修前 5 failed）。

### 后端跨层契约锚点（新增 2 条）

`backend/tests/test_error_handler.py` 本来就注册了真 handler，所以它测的是生产形状。补两条：

* `test_http_exception_dict_detail_stays_dict` —— 新增端点 `/api/conflict-dict` 抛
  `detail={"error_code":..., "server_version":5}`，断言 `body["message"]` 仍是 **dict**。
  这条塌了，前端所有 `detail.error_code` 分派就会静默退化成兜底。
* `test_http_exception_body_has_no_detail_key` —— 断言业务 HTTPException 的响应体
  `set(keys) == {"code","message"}`。它是**前端那段适配存在的理由锚点**：哪天后端改成同时
  输出 `detail`，这条会转红，提醒去评估前端适配该不该一并收敛，而不是两边默默各写一份。

`pytest tests/test_error_handler.py` ⇒ **9 passed**。

### 顺带登记：假绿的第二源（未修）

全仓有**几十个**后端测试文件断言 `resp.json()["detail"]["error_code"]` 这类形状，且能通过
—— 因为它们用的是裸 `FastAPI()` fixture，**没注册**全局 handler，于是测到的是 FastAPI 默认
的 `{"detail": ...}`，而那个形状在生产上不存在。这不影响生产正确性（生产侧已被前端 normalize
修好），但它是一类真实的假绿：照着这些测试的心智模型写新前端代码就会踩坑。

建议卡点（本轮未做）：统一错误响应断言的 fixture，或加 CI 检查禁止在「注册了全局 handler 的
app」上断言 `detail`。

### 零回归

`npx vitest run src/utils src/__tests__/property-m1-handle-api-error.spec.ts src/components/workpaper/sync`
⇒ **1350 passed / 9 failed**，9 条全部既存，逐条对照过：

* 5 条 `src/utils/__tests__/parseIndexRef.test.ts` —— `git stash push -- src/utils/http.ts`
  拿基线：不带本轮改动同样是 56 passed / 5 failed；
* 4 条 sync 既存（`task69IndependentRegression` / `workpaperSyncLegacyBaseline` ×2 /
  `WorkpaperSyncStatusBar`）—— 同法对照，两侧一致。

---

## 十二、Task 18 浏览器层补齐：D4-35 动态行表 + D4-13 静态受管区（**通过**）

§十 用「整册 materialize 200」论证了覆盖面，但那是**端点层**论证。D4-35 / D4-13 走的是
另外两条引擎路径，画布层此前确实没证据。本节补上。

### 先澄清一个结构事实（省掉了一半工作）

D4-35 / D4-13 与 D4-1 **同属一个 entry**（`xlsx/gt-d4-operating-revenue`）的同一份
`store-projection` —— 一次 `store-projection` 响应里就有 27 个 table_key（`adjudication_main_rows`
21 格 / `other_revenue_check_rows` 32 格 / `d413_erp_check_fixed` 2 格 / …）。所以浏览器层
不需要另找入口，就是同一次切「在线编辑」之后在 OO 里多切两个 sheet 读格。

| | D4-35 | D4-13 |
| --- | --- | --- |
| sheet | `其他业务收入检查表D4-35` | `营业收入账面金额与ERP系统核对记录D4-13` |
| 引擎路径 | dict store（`D4-35-data`，行身份 `id`）→ 16 列动态行表 | `BindingKind.static_region`，**不建 Table / 不注 UUID 列 / 不插行** |
| 几何 | 表头 13/14，数据区占位 15..25 | `process`→A6、`conclusion`→A16 |
| 修复前形态 | `D4-35-data` 不在任何 STORE_ITEM_IDS ⇒ 端点装配 **0 格** ⇒ 切 OO 恒空 | 两键恒 `''` |

### 判据

`audit-platform/frontend/e2e/d4-35-d4-13-oo-visibility.spec.ts`（`--workers=1`）。取值方式与
D4-1 同规矩：不解析 HTML 列索引，拿 `store-projection` 与 OO canvas 读回值比对。六条断言：

| 编号 | 内容 |
| --- | --- |
| 5a | **切对了表**（`matchedBy !== 'none'`）—— 切错表上「读到空」会被误当成缺陷，先钉这一步 |
| 5b | D4-35 扫描窗口内非空格 > 0（修复前必然全空） |
| 5c | projection 每个值都在画布上读到（文本等值 / 金额容差 0.01） |
| 5e | 同一 store 行的各列落在**同一个 Excel 行**（抓列错位/行错配 —— 只比「值出现过」抓不到） |
| 5f | 不同 store 行占**不同 Excel 行**（抓互相覆盖丢数据） |
| 5d | D4-13 **比值不比键数**：两段正文精确命中 A6 / A16；另扫 A1:A20 出 `stray_hits` 供诊断 |

### 真栈结果（通过）

```
materialize_200 = True
D4-35  matched=exact  active=其他业务收入检查表D4-35
  GTROW-D435-9001  content=探针-废料销售收入 →行26   amount=50000 →行26   voucher_no=记-0312 →行26
  GTROW-D435-9002  content=探针-租金收入     →行27   amount=2500.5→行27   voucher_no=记-0620 →行27
  missing = []
D4-13  process    @A6  == '探针-D4-13-核对过程正文（真栈）'
       conclusion @A16 == '探针-D4-13-核对结论正文（真栈）'
       stray_hits = []          console_errors = []
```

证据：`task18-browser-d435-d413-visibility.json`。两次干净 run 复验一致。

### 顺带钉住一条 materialize 几何语义

D4-35 的真实行落在 **26 / 27**，而模板数据区占位是 15..25 —— 说明 materialize 是
**保留模板占位行、把真实派生行追加在占位区之后**。这与 D4-1 完全同规律（首数据行 8 + 模板
4 行占位 ⇒ 实测 `insert_at=12`）。

首版判据把扫描窗口设成 3..26，正好把第二行切在窗口外，于是第 1 行命中 26、第 2 行被判
`missing` 而 FAIL。**这次误报有正面价值**：它是这条判据「不是永绿、且能精确定位到具体行/字段」
的自然变异证据。窗口已改 3..45，并在文件注释里记下了这个坑。

### 变异检验状态（如实）

* 5c：**有**自然变异证据（上一段）。
* 5a（切错表）：**两次人工变异尝试均未生效** —— 证据 JSON 里的 `managed_sheet` 字段取自
  `SHEET_D435` 常量，两次都记录为正确表名，说明 playwright 跑的是未变异代码，那次
  "SURVIVED" 判定无效（**不是**判据弱）。第二次尝试还因为命令超时把驱动脚本打断，
  `finally` 没执行、变异残留在文件里；已 grep 确认清除并重跑 e2e 复验通过。
  教训：e2e 的变异检验必须跑在能跑完的后台进程里，不能被命令超时截断。

---

## 十三、🔴 forcesave「拿不到 callback」的真因 —— 推翻 §十 的两条归因

§十 把 D4-2 e2e 失败归为「OO 交互层既有不稳定点」，可疑点记的是
`host_dirty_before_forcesave=False`（推测「OO 写格未置位 dirty ⇒ forcesave 空保存 ⇒ 无
callback」）。本节用一次专门诊断 + DB 事件流水把真因钉到具体错误码，**推翻那两条归因**。

诊断脚本（一次性，已删；证据保留在 `diag-oo-dirty-path.json`）在真栈上逐条试输入路径，
每步都记 `asc_isDocumentModified()` 与宿主 `data-dirty`：

| 路径 | 值写进格子 | `asc_isDocumentModified()` | 宿主 `data-dirty` |
| --- | --- | --- | --- |
| baseline | 空 | false | 0 |
| B 名称框 `#ce-cell-name` + **真实键盘** | **成功** | false | 0 |
| C canvas 点击 + 真实键盘 | （落到别的格） | false | 0 |
| D 内部 API（`asc_insertInCell` + `asc_closeCellEditor(true)`） | **成功** | **true** | **0** |
| E forcesave（紧接 D，此时 modified=true） | — | 之后复位回 false | 0 |

### 推翻一：`host_dirty` 是无关变量

pathE 实测：`save_btn_enabled=true`、`host_dirty_at_click="0"`，forcesave 照样发出并被受理 ——
HTTP **202**，响应体 `{state:"accepted", cs_error:0, cs_outcome:"accepted", callback_expected:true}`。
forcesave 是**后端直接调 OO Command Service**，跟宿主那个 UI 指示器没有因果关系。
而且 `oo_after.modified` 从 true 变回 **false** ⇒ **OO 真的执行了保存动作**，不是「空保存」。

顺带澄清宿主接线本身没问题：`WorkpaperSyncEditorHost.vue` 的
`:data-dirty="bridge.dirty.value ? '1' : '0'"` ← `onDocumentStateChange` →
`readDocumentDirty(event)` → `bridge.notifyDirty`，链路完整。`data-dirty` 停在 0 只说明
OO 没为**程序化**修改发 `onDocumentStateChange`，不影响保存。

### 推翻二：callback 其实一直到了 —— 是判据在错的地方看

诊断脚本一度记下 `callback_arrived=false`，那是**判据自身的缺陷**：OO 容器是**直接**把
callback POST 给后端的，根本不经过浏览器，`page.on('response')` 永远抓不到。

后端权威状态（`working_paper_sync_operation`）显示得很清楚：

```
5b50a166…  oo_to_html  state='error'              application_bound_at=2026-09-24 02:26:27
71dc8828…  oo_to_html  state='application_bound'  application_bound_at=2026-09-24 02:32:15
```

`application_bound_at` 有值 = **后端收到了 callback 并绑定了 application**。

### 真正的失败点：`excel_materialize_editable_write_failed`

`working_paper_sync_operation_event` 的完整流水（operation `5b50a166`）：

| # | from → to | stage | error_code |
| --- | --- | --- | --- |
| 1 | → created | request_frozen | |
| 2 | created → application_bound | application_bound | ← **callback 到达** |
| 3 | application_bound → extracting | extract#1 | |
| 4 | extracting → merging | merge#1 | |
| 5 | merging → rematerializing | rematerialize#1 | |
| 6 | rematerializing → **error** | post_durable#1 | **`excel_materialize_editable_write_failed`** |

所以 OO→HTML 往返**走完了五步**（callback → extract → merge → rematerialize），
在最后写回时才失败。这与「拿不到 callback」是完全不同的结论。

**失败的直接原因是诊断脚本自己造成的**：它为了不污染受管值，刻意往 D4-1 受管 sheet 的
**D30 / E30** 写 marker —— 那是受管 sheet 上的**非受管格**。回写阶段自然写不下去。
换句话说：这一条 error 是探针的副作用，不是产品在正常改受管格时的行为。

### 另一条独立证据：OO 侧 `UpdateVersion expired`

OO 容器 `docservice/out.log` 今天只有两条业务 WARN，都是同一条：

```
[2026-09-24T02:06:03] [wpsync-731508001a1d7747a1b6652d-g101] nodeJS - UpdateVersion expired
[2026-09-24T02:25:34] [wpsync-731508001a1d7747a1b6652d-g101] nodeJS - UpdateVersion expired
```

结合 DB：`working_paper_oo_room` 的 g101 room **created_at = 2026-09-24 00:26 UTC、state=active**，
而当天全部 e2e（10:06 / 10:09 / 10:13 / 10:17 / 10:25 本地）都复用它。
`derive_doc_key(wp_id, entry_id, generation)` 只随 **representation generation** 轮转
（generation 历史 …97, 98, 99, 100, 101，各自一个 doc_key），所以这期间 5+ 次 materialize
重写了 staged xlsx，doc_key 却恒为 `-g101` ⇒ OO 按 doc_key 缓存的文档与磁盘上最新的
staged xlsx 分叉 ⇒ 它在写版本时判定过期。

实测 `docker restart audit-onlyoffice`（清掉 OO 的文档缓存）之后，同样的操作序列不再落到
`state='error'`，而是正常推进到 `application_bound`。这支持上面的成因判断。

> **对前面几节证据的影响（如实标注）**：§九 / §十二 里从 OO canvas 读回的值，有可能来自 OO
> 缓存的那份文档而不是最后一次 materialize 的产物。但那期间 store 数据没变、materialize 是
> 确定性的，两者内容等价，所以「HTML 的行与金额在 OO 里可见」这个结论不受影响。

### 留给后续的两个独立问题（不在本 spec 范围）

1. **同一 generation 内重复 materialize 会让 OO 缓存与磁盘分叉。** 真实用户只要
   「切表格视图 → 再切在线编辑」就可能触发。相关既有设施：`materialize_reuse_verdict`
   模块（`REUSE_METRIC` / `SINGLE_PASS_DECLINE_METRIC` / `single_pass_decline_scope`），
   以及 spec 名 `oo-single-pass-materialize-and-room-leave` 本身就暗示「单次物化」是前提。
   要修的是「重复物化时如何让 OO 重新取文档」——属 room 协议层，需单独立项。
2. **多个历史 generation 的 room 仍是 `state='active'`**（g96/g97/g99/g100/g101 并存），
   AC 2.8 的「发布新 generation 显式 supersede 旧 room」看起来没有全程生效。同样需单独核。

---

## 十四、真栈②覆盖往返：链路**打通**，但撞上一个更深的缺陷 —— S2/S4 在后端不可达

判据：`e2e/d4-1-override-roundtrip.spec.ts`（新增，正式判据）。做法：取 projection 里某个
主营派生行的 `current_unadjusted` 原值 → 在 OO 里把那一格改成 `原值 + 12345.67` →
forcesave → 等**后端** operation 走到 `applied` → 切回表格视图看 S2 标记。

### 先修正判据自身的两个错法（都是真栈教出来的）

1. **不能用浏览器网络判 callback**（见 §十三）⇒ 改为轮询
   `GET …/sync/entries/{entry}/operations/{opId}` 的 `state`。
2. **不能用内部 `asc_*` API 写格。** `asc_insertInCell` + `asc_closeCellEditor(true)` 只改
   **浏览器端**文档，改动没通过协同通道同步到 OO 服务端 ⇒ forcesave 时 Command Service 回
   `cs_error=4`（no_changes），operation 直接 `rejected`，往返根本不开始。
   DB 实证：`state='rejected' error_code='cs_error=4'`。
   **只有真实键盘输入**（名称框 `#ce-cell-name` 定位 → `keyboard.type` → Enter）才会产生
   changes 并同步到服务端。改用键盘后拿到 `cs_error=0` 并真的走进 `extracting`。

### 往返链路本身：走通了

```
oo_to_html  trail: created → application_bound → extracting → merging → conflict
```

callback 到达 → extract → merge 全部成功。`working_paper_sync_conflict` 里那条记录把
OO 的改动**精确**认了出来：

```
stable_field_key : adjudication_main_rows/xsheet-main-营业收入_批发_分销/current_unadjusted
oo_location      : 营业收入审定表D4-1!B@row=xsheet-main-营业收入_批发_分销
field_source     : onlyoffice_cell
base_value       : 153431246.06
current_value    : 153431246.06
incoming_value   : 153443591.73   ← 恰好等于「原值 + 12345.67」
conflict_kind    : protected
protection_policy: read_only_masked_cell
suggested_action : keep_current        resolution: None
```

所以 **OO→HTML 方向的管线是好的**：值取到了、行身份对上了、坐标对上了。

### 🔴 新发现的缺陷：整列 mask 判定把 6 个金额字段全判成只读

失败点是 `conflict_kind='protected'`。根因在 `merge.py::_FieldLocatorTable._protection`：

```python
if (
    spec.cell is not None
    and template.formula_mask
    and column_in_ranges(spec.cell.column, template.formula_mask)   # ← 只比列，不比行
):
    return ProtectionPolicy.read_only_masked_cell
```

`contracts.column_in_ranges` 的 docstring 写明它判的是「列是否落在任一 A1 区域的**列跨度**内」。
对 mask 恰好覆盖整个数据区的底稿（D2 `Q13:Q25`、D6/D7 同形）列判定等价于格判定，没问题。
但 **D4-1 的 mask 是逐格声明的 48 格**，内容是「各区数据行的 E/I（审定数 `=SUM`）+
小计/合计/差异行（12/18/19/21）的 B–I」——数据区之外的那几行把 B…I 八列全带进了列跨度。

实证（`MANAGED_FIELD_SPECS` × `column_in_ranges` 逐字段跑）：

| 字段 | 列 | 契约 `mode` | 判定结果 |
| --- | --- | --- | --- |
| `label` | A | editable | False（可写） |
| `current_unadjusted` | B | editable | **True → read_only_masked_cell** |
| `current_aje` | C | editable | **True** |
| `current_rje` | D | editable | **True** |
| `prior_unadjusted` | F | editable | **True** |
| `prior_aje` | G | editable | **True** |
| `prior_rje` | H | editable | **True** |

这与 D4-1 provider 自己的注释**直接矛盾**：

> E/I 审定数（=SUM）与小计/合计/差异行（12/18/19/21）的 B–I 落 `FORMULA_MASK`，
> 普通值投影不覆盖；**受管数据行 B/C/D/F/G/H 绝不入 mask**。

契约的**格**声明是对的（那几行确实是公式，确实该保护）。错的是 merge 把逐格 mask 读成了整列。

### 后果（为什么这条比它看起来严重）

* **需求 1.5（2026-09-23 用户拍板的选项 b：OO 改动 SHALL 生效并成为该格权威值）在后端完全
  不可达** —— D4-1 六个金额格的任何 OO 改动都只会产生一条 `protected` conflict +
  `suggested_action=keep_current`，`stored` 永不改变。
* 于是需求 6.2 的 **S2（人工覆盖、上游未变）与 S4（覆盖且上游已变）永远不可能出现**
  （两者都以 `stored ≠ snap` 为前提）。前端 Task 15 已经实现的那套四态 UI
  （`D4TabAdjudication.vue` 的 `.override-tag`、S4 三值 tooltip、「恢复取数」按钮）
  目前是**死代码**。
* 这条缺陷**端点层判据测不到**：它们不经过 merge 的 protection 判定。只有真栈往返能暴露。

### 判据当前状态（如实）

`d4-1-override-roundtrip.spec.ts` 目前**红**，卡在第一条断言
`operation_final_state === 'applied'`（实际 `conflict`）。这条红是**正确的红** —— 它精确地
指着上面那个缺陷，证据 `task18-override-roundtrip.json` 里落了完整的
`operation_state_trail` 与 conflict 明细。修好缺陷后它应当自然转绿，届时后两条断言
（store 侧值 = 新值、HTML 侧出现「已人工覆盖」）才会被真正检验到。

### 修法方向与风险（**待用户拍板，本轮未改**）

要让 `editable` 字段不被数据区之外的 mask 行连带保护，判定必须从「列交集」收紧。难点是
动态行字段的 `spec.cell` 是 `{column, row_from: 'row_identity'}`，**运行时才有行号**，
所以无法做纯粹的格级判定。可行的收紧方式是：**只用落在该表数据区行范围内的 mask 格参与
列判定**（D4-1 数据区内的 mask 只有 E/I ⇒ B/C/D/F/G/H 解除保护，E/I 仍受保护，符合契约意图）。

风险必须显式登记：`_protection` 是 **merge 的平台级判定，影响所有走 sync 的底稿**。
凡是「mask 声明了整列/整个数据区」的底稿行为不变；只有「mask 含数据区之外的行」的底稿会
从只读变可写 —— 那正是要修的形态，但需要逐张确认没有别的底稿在靠这条列判定保护真公式格。
因此这不是一处局部改动，需单独立项 + 全量 sync 回归，**不在本轮擅自变更**。

### §十四 实测数字（`task18-override-roundtrip.json`，captured 2026-09-24T03:02:20Z）

```
target        row_id=xsheet-main-营业收入_批发_分销  label=营业收入_批发_分销
              old=153431246.06  new=153443591.73   cell_ref=B12（扫描命中 hitRow=12，非硬编码）
键盘写入后      oo_cell_text_after_typing = "153443591.73"        ← 值真的进了格子
materialize    200
forcesave      cs_error=0  cs_outcome=accepted  callback_expected=true   ← 服务端认了改动
operation      created → application_bound → conflict                    （final=conflict）
store 侧        153431246.06                                              ← 原值，未被覆盖
```

逐环都有实数：值写进去了、OO 服务端认了改动、callback 到了、merge 认出了 incoming 值，
最后因 `protected` 判定把它挡在 store 之外。**这正是「OO 里改的数看起来没生效」那类形态** ——
与本 spec 起因同型，只是方向相反（起因是 HTML→OO 不可见，这条是 OO→HTML 不落库）。

> 附带说明：证据里 `html.error` 是「切回表格视图时找不到 `.el-table`」。原因是 operation 停在
> `conflict`，participant 的 leave 被后端以 409 `participant_leave_refused_in_flight` 拒绝
> （「该 participant 还有 4 个未终结的写请求」），UI 因此没能正常切回。这是 conflict 的**后果**，
> 不是另一个独立缺陷 —— 缺陷修好后这一段才会走到。

### 顺带拿到的一条真栈信封证据（回证 §十一）

上面那条 409 的**真实响应体**：

```json
{"code":409,
 "message":{"error_code":"participant_leave_refused_in_flight",
            "message":"该 participant 还有 4 个未终结的写请求 —— 同步进行中离开会让 UI 与服务端脱钩，请等它结束"}}
```

**没有 `detail` 键，且 `message` 是 dict**（内含 `error_code` 与中文根因）。这正是 §十一 描述
的生产形状，来自真实后端而非构造 —— 修前前端读 `data.detail` 会得到 `undefined`，
于是 `error_code` 认不出、那句中文根因也到不了用户眼前。


---

## 十五、修复整列 mask 误判 —— 真栈②覆盖往返闭环（2026-09-25）

§十四 定位到根因：`merge.py::_FieldLocatorTable._protection` 的第三类判定
（受保护单元格）用 `column_in_ranges(spec.cell.column, formula_mask)` **只比列不比行**。
用户拍板实修。本节记录修复、全仓安全论证、判据与真栈闭环。

### 全仓穷尽盘点（改前实测）

一次性脚本遍历 `DELIVERED_PER_ENTRY_CONTRACTS` 全部 **10 个 entry** 的真实契约，逐字段跑
`_protection`：

| 结论 | 数字 |
| --- | --- |
| 被整列 mask 误判为只读的 `editable` 字段 | **311** |
| — 其中集中在 D4 这一个 entry 的表数 | 9 张 |
| — 静态格「其实该格不在 mask 里」（0 例外） | 286 |
| — 动态行（同列 mask 格全落在数据区之外） | 25 |
| **9 个非 D4 entry（b60/D2/H1/G7/D1/D7/D3/D6/D5）误伤** | **0** |

9 个非 D4 entry 的 mask 都是 `{col}{FIRST}:{col}{LAST}` 形态（恰好覆盖数据区），列判定与
格判定等价 ⇒ **本次收紧对它们零影响**。误伤全是 D4 逐格式 mask 的副作用，且当前列判定
**没有保护任何一个真该保护的 editable 格**（286 个静态格无一例外「其实不在 mask 里」）。

### 修法

`contracts.py` 新增格级纯函数（`column_in_ranges` 保留给 CS-13 的声明完备性校验，列级足够）：

```python
def cell_in_ranges(column: str, row: int, ranges) -> bool:
    """某个格（列 + 行）是否落在任一 A1 区域内 —— 与 column_in_ranges 的区别就是同时看行。"""
```

`merge.py::_protection` 第三类判定按 `spec.cell.row_from` 分流：

* **静态格**（`static` + `static_row`）：`cell_in_ranges(column, static_row, mask)` 精确判定；
* **动态行**（`row_identity`）：只有 `_mask_spans_data_column(column, first_data_row, mask)` 为真
  才保护 —— 该函数要求「存在同列 mask **多行区间**且**覆盖首数据行**」
  （`first_data_row = anchor 行 + header_rows`）。

这条动态行判据是关键：它精确区分两种形态 ——

| 形态 | 例 | 判定 |
| --- | --- | --- |
| mask 声明**整个数据区列**只读 | G7 `K8:K200`（首数据行 9，多行、覆盖 9） | **保护**（editable 但整列受保护） |
| mask 针对**模板固定行** | D4-1 `B12`（首行 9，单格小计行坐标） | **不保护**（materialize 插行后 12 已是数据行） |
| footer 单行 | D4-9 `C23:F23`（单行合计行） | **不保护** |
| 数据区外多行 | mask 到了下一个 section | **不保护** |

拿不到 anchor 行时 `first_data_row=None`，动态行判定退化为「不保护」——安全侧（少保护的动态行
由 CS-13 要求声明 `mode=formula` 兜住，不会把该保护的公式格放开）。

### 判据与变异

`backend/tests/workpaper_sync/test_masked_cell_protection_is_cell_level.py` —— **33 passed**：

* `TestD41AmountFieldsAreWritable`：D4-1 六个金额字段（B/C/D/F/G/H）不再被判只读；
  反面锚点确认 E/I 审定数未进契约字段（进了要重新评估）；
* `TestNonD4EntriesAreUnaffected`（参数化 9 entry）：被 mask 误判的 editable = 0、formula 字段仍只读；
* `TestWholeRepoHasNoMaskedEditableField`：动态遍历全 entry，被 mask 误判的 editable 字段总数 = 0
  （不硬编码 311，新增受管区不会漏）；
* `TestCellInRanges`：单格命中/不命中、跨列区间 `C23:F23`、跨行区间 `Q13:Q25`、双字母列 `AF37`、空 mask；
* `TestStaticCellTrulyInMaskStaysProtected`：**防修过头** —— 构造静态格真落在 mask 里，必须仍只读
  （真实契约里这种字段一个都没有，只能构造 payload 钉住，否则「受保护单元格」类会永不被测到）；
* `TestDynamicRowWholeColumnMaskStaysProtected`：G7 `K8:K200` 整列 mask 动态行仍保护，
  D4-1 `B12` 单格 / D4-9 单行 / 数据区外多行都不保护。

变异 **3/3 KILLED**：M1 回退列级 → 杀不变式+全仓收口；M2 `cell_in_ranges` 丢行判定 →
杀单元+静态格解除；M3 静态格判定恒放行 → 杀「真在 mask 内仍只读」。

### 零回归

`tests/workpaper_sync -k "protection or protected or mask or merge or conflict or task14 or task15
or task27 or contract or cell or column"` ⇒ **1938 passed / 1 failed**。唯一失败
`test_task42_h1_...test_contract_declares_the_observed_emptiness` 经 `git stash` 基线对照确认
**是既存失败**（不带本轮改动同样红），非本轮引入。

一处**真回归当场修掉**：`test_task14_merge_conflicts` 的 `masked_note`（G7 `equity_changes` 的
K 列，mask `K8:K200`）在「动态行完全不看 mask」的首版实现下被误放开。这暴露了「动态行整列
mask」这个第四类形态 —— 由此补出 `_mask_spans_data_column` 的「多行区间 + 覆盖首数据行」判据，
既修好 D4-1 又保住 G7。

### 真栈闭环

`e2e/d4-1-override-roundtrip.spec.ts` ⇒ **1 passed (1.7m)**。证据 `task18-override-roundtrip.json`：

```
target        B12   old=153480628.74 → new=153492974.41   （键盘写入 oo_cell_text="153492974.41"）
materialize   200
forcesave     cs_error=0  cs_outcome=accepted
operation     created → application_bound → rematerializing → applied     ← 不再是 conflict
store 侧       153492974.41                                                ← 新值真的落库
HTML          table_has_new_value=true + 「已人工覆盖」标记
```

与 §十四 的 `conflict / store 原值不变` 决定性对比：**需求 1.5（选项 b）后端可达，需求 6.2 的
S2 态在真栈出现，Task 15 的四态 UI 不再是死代码。**

> 环境踩坑（与修复无关，登记备查）：e2e 的 `baseURL` 是 `http://127.0.0.1:3030`（IPv4），
> 而当时在跑的 vite 只监听 `::1`（IPv6）⇒ 每次 login 首步就失败、看起来像 D4 缺陷。
> 用 `npm run dev -- --host 127.0.0.1` 重启前端到 IPv4 后即通过。此外顺手给 e2e 的 `login` 与
> forcesave 加了瞬时抖动重试（后端 `--reload` 窗口 / OO 协同通道推送延迟），让判据只对真缺陷转红。
