# Task 1 / 2 / 3 证据：slice 与 **spec 自身**的不一致清册（逐条现算 vs 登记值 vs 处置）

**执行日期**：2026-09-27　**判据文件**：`backend/tests/workpaper_sync/test_h_foundation_hc_guards.py`（181 passed）
**扫描器**：`backend/tests/workpaper_sync/h_cycle_facts.py`（四份 H spec 共用，只提供「怎么数」不提供「应该是几」）

## 一、spec design 已登记的五处 slice 不一致 —— 全部现算复核**属实**

| # | slice 记 | 现算 | 结论 |
|---|---|---|---|
| 1 | `useH9DualMode` 零消费 | 生产消费 **1**（`GtH9LeaseLiabilities.vue`） | 属实，**不得删** |
| 2 | `useH7FormData` 全仓零引用 | 生产消费 **1**（`h7/core/H7TabAdjudicationCost.vue`），且 `publishToTb` 在 H7 **只出现在它里面** | 属实，**禁删** |
| 3 | `capability=null` / `capability_target=bidirectional` / `legacy_fake_bidirectional` | manifest 实测 `capability='single_onlyoffice'`、**无 `capability_target` 字段**、`adapter_id=None`、独立 entry `mounts=2` / 子入口 `mounts=1`、`relationship` 字段亦不存在 | 属实，按实测写 |
| 4 | 主表键 `H5-2-rows` | 字面量**全仓零命中**；由 `` `${ITEM_PREFIX}-rows` `` 拼接，`useH5Detail.ts` 的 `ITEM_PREFIX='H5-2'` | 属实，守卫加拼接解析分支 |
| 5 | H5 有固定 `rowId:'subtotal'` 派生合计行需契约排除 | `useH5Adjudication.ts` 保存前 `.filter(r => !r.isSubtotal)`；`useH5Detail.ts` 的 `subtotalRow` 是 computed ⇒ **不落库** | 属实，契约无需排除 |

## 二、🔴 **本轮新发现：spec 自身有 7 处与实测不符**（按严重度排序）

### ①【最严重】9 个「幻影码」里有 2 个不是幻影码 —— 照 G2 写 provider 会直接抛错

`find_template_file` / `find_template_file_any` 实测：

| 幻影码 | 单册解析 | 根因 |
|---|---|---|
| `H2C` `H3I` `H4E` `H5O` `H7B` `H8R` `H9L` | **None**（7 条） | 真幻影码 |
| 🔴 `H6A` | `H6 固定资产清理.xlsx` | `H6A` **同时**是真实程序表码（`固定资产清理实质性程序表H6A`） |
| 🔴 `H10A` | `H10 资产处置损益.xlsx` | 同理（`资产处置损益实质性程序表H10A`） |

G2 provider 的 `assert_no_implicit_template_fallback()` 断言「幻影码不得命中任何模板」。
H6 / H10 照抄 ⇒ **注册路径上直接 `EntrySelectionError`**。

**处置**：不变量改成「幻影码不得命中**别的 entry** 的册子」。`H6A`→H6 自己的册、
`H10A`→H10 自己的册，是**同册别名**，无跨 entry 泄漏风险。
另：`find_all_template_files`（sheet 级）对 9 个幻影码**一律返 `[]`** ⇒ sheet 级零回退 9 条全成立。
判据 `test_phantom_codes_must_not_leak_into_another_entrys_workbook`。

### ②【反驳 HC-14 第 5 行】程序表码 `H2A` **不返 None**

spec：「程序表码 `H2A` 解析返 `None` 是**正确**的 ⇒ 守卫应断言 `resolved is None`」。
实测 5 个程序表码全部命中**父册**：`H2A`→H2 / `H3A`→H3 / `H5A`→H5 / `H7A`→H7 / `H8A`→H8。
照 spec 写守卫会在第一次运行就红，且红的方向会误导下一个人去"修" finder。
判据 `test_program_sheet_codes_resolve_to_their_parent_workbook`。

### ③【BP-12 清册从 1 处扩到 4 处，其中 1 条链**整体是死路**】

spec HC-9 只记 `h10RelatedH6Pull.ts#L59`（因为只扫了变量名 `const keys`）。
按**结构**扫描（数组里 ≥2 个带循环码前缀的 store item id + 被逐个试 + 循环体做 store 查表 + 有早退）现算 **4 处**：

| site | 键数 | 该键所属 entry 侧零生产的键数 | 后果 |
|---|---|---|---|
| `h10RelatedH6Pull.ts#L59` | 3 | 2 | spec 已记 |
| 🔴 `h3MortgageReconcile.ts#L75` | 2 | **2（全部）** | H3 抵押核对恒取不到 L1 质押行 |
| 🔴 `h6H10Pull.ts#L45`（变量名 `keyPriority`） | 4 | **4（全部）** | H6→H10 审定数反向勾稽**整条死路**，恒走「H10 暂无审定数」分支 |
| 🔴 `useH6Check.ts#L508` | 4 | 3 | 只有 `H10-detail-rows` 是真键 |

🔴 这同时**反驳 lane 3 spec Requirement 2.6**：它写「`h6H10Pull.ts` / `useH6Check.ts` 反向消费
`H10-1-audited-total` / `H10-adj-total` / `H10-1-gain-loss-total` ⇒ **双向耦合**」——
这三个键在 H10 侧**零生产**，反向耦合实际上**没有建立**。

🔴 判定口径也必须修正：不能用「消费方文件之外还有没有命中」——
`H6-detail-rows` 在 `h10RelatedH6Pull.ts` **与** `useH10CrossSheet.ts` 两处出现，
但两处都是 H10 侧消费方。正确口径 = 「**该键所属 entry 的作业面**里有没有生产者」
（`producers_in_owning_entry_scope`）。

### ④【反驳 HC-6 第 4 条的区分依据】`H7-2-fair-total` **不存在**

spec：「BP-5 无 total 键；H7 **有**对应 `H7-2-cost-total` / `H7-2-fair-total`」。
实测 `H7-2-cost-total` 存在（`useH7CrossSheet.ts` 读它），
🔴 **`H7-2-fair-total` 全仓零命中** —— 公允价值侧根本没有 total 键。

⇒ 若判据写成「有无 total 键」，`H7-2-fair-rows` 会被误判成 BP-5 同形缺陷。
**权威判据改为「有无读取点」**（`key_read_sites`，支持模块常量间接引用）：
* `H8-2-detail-prefill` —— 全仓只有 `map.set(...)`，**零读取点** ⇒ 缺陷；
* `H7-2-{cost,fair}-rows` —— 各自的 Tab 里 `getString('H7-2-*-rows')` 回读 ⇒ 正常。

### ⑤【反驳 HC-2 第 2 条的误判类型】F 版守卫在 H 上是 **2 假红 + 3 假绿**，不是「6 条假红」

| entry | `useH{n}FormData` 实测 | F 版口径 | 真实 | 误判 |
|---|---|---|---|---|
| H2 | **文件不存在** | 红 | `host_inline` | 假红 |
| H7 | get=5 / **put=0** | 红 | PUT 在 `H7TabDetailCost.vue` 内联 | 假红 |
| H6 / H8 / H9 | get=12~13 / put=1，**生产消费 0** | 绿 | `host_inline`，该 composable 是**死代码** | 🔴 **假绿** |

假绿比假红危险 —— 正是 HC-3 第 4 条点名的「additive 注入即死代码」。
H3/H4/H5/H10 在 F 版口径下**正确通过**（H5 只是多实例化，属族差异非误判）。

### ⑥【HC-10 口径过宽 + 清册漏项】第三处**数据**存储只有 H10，但 localStorage 命中 12 处

按「文件里出现 `localStorage`」现算命中 **12 个** H 作业面文件：
* **9 个** `useH{2..10}DualMode.ts` —— 存**视图模式字符串**（`setItem(STORAGE_PREFIX + wpId, mode)`，H10 是 `target`），是 UI 偏好；
* **2 处**列隐藏偏好（`useH8DetailColumnPrefs.ts` / `h6/inspection/H6TabCheck.vue`，`JSON.stringify(hidden)`）；
* **1 处**真正的数据存储 `useH10FormData.ts`（键按 `itemId` 分片：`h10-draft:{wpId}:{itemId}`）。

🔴 判据口径不能用「值里有 `JSON.stringify`」（会把两处列偏好算进来），
必须用「**localStorage 键按 `itemId` 分片**」—— 按这个口径现算**只有 H10**，spec 结论成立。
🔴 但 spec 说「其余 8 条零 localStorage」不对：9 个 DualMode 里 **4 个（H4/H6/H8/H9）在生产是活的**，
只是存的不是业务数据，不构成 HC-10 的 roundtrip 风险。

### ⑦【HC-5 变体轴清册漏 1 组 + sheet 全名漏尾码】

* 🔴 漏记 **`H8-8 折旧测算表（不含减值）/（含减值）`** ⇒ `impairment_included` 族实测 **4 组**
  （H3-7 / H5-12 / H7-11 / **H8-8**）不是 3 组；加上 `period_granularity`（H8-6）共 5 组非 measurement_model。
* 🔴 spec 正文写的 sheet 名**去掉了尾码**（如「折旧测算表（成本模式不含减值）」），
  实测全名是「折旧测算表（成本模式不含减值）**H3-7**」。契约用全名消歧时**必须带尾码**，
  否则 `wb[name]` 直接 `KeyError`。
* 另现算补齐三组 spec 未逐条列出的：`H3-5 增减检查表`×2 / `H7-6 增加检查表`×2 / `H7-7 减少检查表`×2。

## 三、canary H9 载荷字段数：**22** 不是 23

spec Requirement 5.3 写「覆盖真库实测 **23 字段**全集」，但其**自身枚举只列了 22 个**。
真库 `H9-2-rows`（819 B / 2 行）逐字段现算 = **22**，与 `useH9Detail.ts` 的 `_persist()`
落盘字段列表逐字段一致。⇒ 按 **22** 写契约。

行身份两形态与 spec 一致：`row-liab-H91-FILL-1784691549786`（H9-1 联动填充带时间戳）
与 `row-mrvjayxr-u0mc`（随机）—— 均属 HC-7 族 A，canary 不含身份改造。

## 四、其余 spec 事实逐条现算**属实**（无需修正）

manifest 14 条（9 entry + 5 子入口）全部字段 · 11 个模板 sha256/字节 · 宿主 6 项统一信号
（bridge 0 / legacyOO 4 / notice 3 / ocr 0 / adjCentral 0 / localStorage 0）·
`http_import` 与 `force_component_type` 各命中 7 条 · `checklist_put`（H2=1 H6=2 H7=2 H8=1 H9=1）·
TB 发布门 7 有 2 无（**H8/H9 全链路 0 处**）· `useAdjustmentCentralSync` 9/9 ·
载体消费方 10 项 · 族 B `seed-${` **恰 3 处** · 族 C **恰 7 处** ·
definedName 9 册全 0 · 无 Excel Table · `GT_Custom` 只在 H9/H10 ·
裸 IF per-file 最重 H8 / 最轻 H6（差 ≥20 倍）· H9 次轻 ·
11 张宽表 `max_column` ≥100 而有效列 ≤20（差 200+ 列）·
footer 9 条形态（H6「　合计」全角空格 · H4 派生单价 4 列且无 IFERROR · H10 双 footer）。
