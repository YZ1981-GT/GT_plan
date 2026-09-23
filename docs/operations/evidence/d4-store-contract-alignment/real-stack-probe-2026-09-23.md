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
