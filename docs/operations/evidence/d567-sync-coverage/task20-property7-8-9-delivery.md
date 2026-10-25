# D567 Task 20 / 8 / 11 / 13 / 17 交付证据（2026-09-30）

spec：`.kiro/specs/d567-sync-coverage-via-row-table-engine/`

本文件只记**实测事实与可复现命令**，结论与裁决在 spec `tasks.md` / `design.md`。

---

## 一、Property 7：cell_mask 与模板册对账，修掉 96 格 fail-closed 误锁

判据：`backend/tests/workpaper_sync/test_d567_property7_cell_mask_vs_template.py`

### 1.1 判据口径（为什么不能照 D3-1 抄）

D3-1 的口径是「`value_source == manual` 且 `value_type == amount` ⇒ 不得 mask」。
**直接搬到 D5/D6 会产生 30 个假阳**：

| 表 | 假阳格数 | 原因 |
|---|---|---|
| D5-1 `main` R7-R8 | 10 | 模板里 B/C/D/F/G/H **真是 SUMIF 公式**（`=SUMIF('应收款项融资明细表D5-2'!…)`） |
| D6-1 `block3` R26-R30 | 20 | 模板里 B–I **真是** `=B8-B17` 这类派生公式 |

`_VALUE_SOURCES` 里的 `manual` 表达的是**前端 store 侧**语义（HTML 逐格存值），
与模板侧该格是否为公式是**两件事**。故判据改为锚定模板册的三向口径：

1. 模板该格**有公式** ⇒ 必须 mask（防 OO 回写覆盖公式）
2. 模板该格**无公式** 且字段**不是** `computed` ⇒ 必须**不** mask（Property 7 本体）
3. 模板该格**无公式** 且字段是 `computed` ⇒ **允许** mask（保守保护）

该口径与参考实现 D3-1 的**实际状态**自洽：D3-1 区2 的 F（`current_unadjusted`、
`cross_sheet`、模板无公式）在 D3-1 里确实**未** mask —— 「派生字段不可 OO 直写」由
`is_oo_writable()` 这条**独立**机制保证，与 mask 不是一回事。

### 1.2 修复前后（mask 集合 vs 模板公式格集合的对称差）

| 表 | 修复前 over-mask | 其中在数据行 | 修复前 under-mask | 修复后 over-mask |
|---|---|---|---|---|
| D5-1 | 0 | 0 | 0 | 0（**本就逐格一致**，46 == 46，未改动） |
| D6-1 | 71 | **60** | 10 | 11（全是非数据行 computed 列，属口径 ③ 允许项） |
| D7-1 | 36 | **36** | 0 | 0 |

修掉的误锁共 **96 格**（D6-1 区1 R8-R12 + 区2 R17-R21 的 B/C/D/F/G/H = 60；
D7-1 区1 R8-R13 的 B/C/D/F/G/H = 36）。危害：审计师在 OnlyOffice 里**改不了**
期初未审 / AJE / RJE / 期末 AJE / RJE。

### 1.3 声明为何会错（两处注释的前提不成立）

* `phase5_d7_01_adjudication.py` 原注释：「区1 数据行 R8-R13：B-K（性质区有 SUMIF cross_sheet 公式）」
  —— 模板 `审定表D7-1` 实测 R8-R13 的 B/C/D/F/G/H **全为空**，无任何公式。
* `phase5_d6_01_adjudication.py` 原注释：「区1 原值 R8-R12 数据行：B-K 公式（SUMIF cross_sheet）」
  —— 同上，模板里只有 E/I/J/K 是公式。

**表内自证**（最硬的一条）：`D7-1` 的区2（账龄 R20-R23）模板形态与区1 **完全一致**
（B/C/D/F/G/H 空、E/I/J/K 公式），而声明却只 mask E/I/J/K。两区声明自相矛盾，
坐实区1 是错的那一侧。

### 1.4 登记豁免（可伪证）

`D6-1` 的 `A17-A21` / `A26-A30` 在模板里是 `=A8` 这类**同列自引用镜像公式**（口径 ① 要求 mask），
但 A 列是 `editable` 项目名列，而框架不变量 `assert_data_cells_not_masked()` **禁止** mask
数据行的 editable 列 —— 两条规则直接冲突。本轮不擅自改任一侧，登记为**可伪证**豁免，
判据逐条验证：真在 A 列 + 真在数据行 + 模板值真是 `=A\d+` 镜像 + 名单无失效条目。

---

## 二、Property 8：四态覆盖状态机接入三家 + UI

判据：`d5/d6/d7CellOverrideRender.spec.ts`（59 条）+ `d567AdjCellOverrideUi.spec.ts`（15 条）

### 2.1 三家改造前的反模式（各不相同）

| 表 | 反模式 | 危害 |
|---|---|---|
| D5-1 | `cross !== 0 ? cross : manual` | 派生值恰为 0 时把手工值当派生用；上游变了无法区分覆盖与跟随 |
| D7-1 nature | `agg ? agg.X : manual` | 聚合对象**一存在就无条件**盖掉手工值（三家最激进） |
| D7-1 aging | `isFromCrossSheet = crossCurrent !== 0 \|\| crossPrior !== 0` | **一个标志管两列**，期末有值就把期初手工值切成 0 |
| D6-1 | `map.has(prefix-currentUnadjusted)` | ①空串 remark 也为 true 就掐断上游 ②只看 current 键却决定 prior ③**与同步器根本不兼容**：同步器把派生值落进 stored 后 `has` 恒真 ⇒ 上游取数被自己永久关掉 |

### 2.2 共享降级（三家共用一份）

`shared/dynamicAdjudicationRows.ts` 新增 `resolvePerCellDerivedState(stored, snap, derived)`。

`snap === null`（迁移前存过值的格 / 同步器没跑过）**不能**直接丢给 `resolveCellState`：
`resolveCellState(0, null, 100)` 判 **S4** ⇒ 显示 stored=0 ⇒ **上游 100 被吞**；
且 per-cell 形态下同步器判 S2/S4 会**跳过写 snap** ⇒ snap 永远 null ⇒ 该格**永久**
显示 0 且永久标已覆盖、**不可自愈**（D1 实测同形回归）。读侧与写侧**必须都走**这个入口。

### 2.3 block3 不接状态机的理由

D6-1 的 block3（净值）是 `block1 − block2` 的纯公式区（`isEditable: false`），消费的已是
block1/block2 的**显示值** ⇒ 覆盖自动透传，无需第二套状态机（已加判据钉死透传）。

### 2.4 UI

共享徽标 `shared/DerivedCellOverrideBadge.vue`（S2 黄「已人工覆盖」/ S4 红「覆盖·上游已变」
+ tooltip 三值并呈 + 「恢复取数」），接入三家 Tab 共 **1 + 2 + 4 = 7** 个派生列位。
不复制 D4 的内联块（9 个列位会复制九份必漂移）；组件只依赖 `cellOverrides[field]` 契约。

### 2.5 顺带修掉的自引缺陷

`useD6Adjudication.removeDynamicRow` 原不清 `-snap` 键 ⇒ 孤儿快照；同名类别日后重现时
`stored=null, snap=旧值, derived=新值` ⇒ 判 S4 ⇒ 显示 0 且错标已覆盖。

---

## 三、Task 13：裁决 G2 两条账龄路径对照

判据：`backend/tests/workpaper_sync/test_d567_task13_aging_layout_path_comparison.py`

### 3.1 现算路径差异

|  | flat（D6-2） | nested（D7-2 / D3-2） |
|---|---|---|
| `segments` 元组数 | **3**（flat_key, col, label） | **2**（seg_key, col） |
| `leaf_labels` | **空**（label 在 segment 内） | **非空**（与 segments 并行） |
| `json_prefix` | **空串** | `agingPrior` / `agingAudited` |
| key 派生 | `snake(flat_key)` → `age_prior1y` | `{snake(prefix)}_{seg.lower()}` → `aging_prior_within1` |
| json_key | `agePrior1y`（**无 `/`**） | `agingPrior/within1`（**有 `/`**） |
| 展开条数 | 8（2 组 × 4 段） | 8（2 组 × 4 段） |

**展开条数相同、只有命名规则不同** —— 这是「差异必须能归因到 `aging_layout` 而非别处」
的精确表述：数量维度不受 layout 影响，命名维度完全由它决定。

### 3.2 归因的决定性证据：只翻 layout 会响亮失败

```
dataclasses.replace(SPEC_D62, aging_layout=nested) → ValueError: 账龄组  有 4 段，
    但 leaf_labels 有 0 个 —— 段与标签必须一一对应
dataclasses.replace(SPEC_D72, aging_layout=flat)   → ValueError: not enough values
    to unpack (expected 3, got 2)
```

layout 与 `aging_groups` 在**三处同时**耦合（元组数 / leaf_labels / json_prefix）
⇒ 不存在「layout 写错但键照样产出」的静默路径。比「输出差异能归因到 layout」更强：
**形态错配根本走不到产键那一步**。

### 3.3 Task 13 原判断复核成立

`D5-2` / `D7-5` / `D7-6` 的 `aging_layout` 确为 `None`、`aging_groups == ()`、
`expand_aging_fields()` 恒为空 ⇒「本轮新增 sheet 上没有 nested/flat 对照分母」成立。
对照由**已接入**的 D6-2 / D7-2 承载。

---

## 四、Task 11：Property 5「无分母」复核 + 新发现的静默面

判据：`backend/tests/workpaper_sync/test_d567_task11_layout_groups_invariant.py`

### 4.1 三张 D6 新 sheet 实测

| 表 | layout | groups | field_specs | managed_field_specs | 账龄尾 | store 键 |
|---|---|---|---|---|---|---|
| D6-3 | None | 0 | 14 | 14 | 0 | `D6-3-rows` |
| D6-5 | None | 0 | 14 | 14 | 0 | `D6-5-rows` |
| D6-8 | None | 0 | 8 | 8 | 0 | `D6-8-single-rows`（**不是** `-rows`） |

⇒ Property 5（flat 键派生 ≡ 原写法）在这三张上确实**无分母**，不是漏测。

### 4.2 🔴 静默面：`aging_groups` 为空时 `aging_layout` 完全惰性

实测：把 `SPEC_D603`（`layout=None, groups=()`）的 layout 翻成 `flat` 或 `nested`，
`expand_aging_fields()` **都不报错**、都返回 0 条，`managed_field_specs()` 输出**逐项相同**。
机理：flat/nested 两分支都是 `for group in spec.aging_groups`，空序列零次迭代。

后果：某张有账龄列的 sheet 声了 `aging_layout=flat` 却**忘了给 `aging_groups`**，
会**静默丢掉全部账龄列**且无任何报错。

**这个风险不是假想**：Task 9 的原始 bullet 写的是「`D6-3-rows` / `D6-5-rows`；`aging_layout=flat`」，
而交付事实是 `aging_layout=None`（narrative 行记对了）。当时若照 bullet 把代码改成 `flat`
而没补 `aging_groups`，产出会与现在**一模一样、零报错** —— 这条声明矛盾至今无害靠的是运气。

### 4.3 全仓不变量已冻结

现算基线（2026-09-30）：**124** 个 `RowTableSheetSpec` 实例，
layout 分布 `None=120 / nested=3 / flat=1`（印证「flat 唯一样本 = D6-2」）。

| 违规类 | 含义 | 现算 |
|---|---|---|
| A | `layout` 非 None 但 `groups` 空 ⇒ 账龄列静默丢失 | **0** |
| B | `groups` 非空但 `layout` 为 None ⇒ 账龄声明永不展开 | **0** |

两侧都**无报错** ⇒ 只能靠门拦。已写成判据 + 双向变异。

---

## 五、Property 9：回写后下游重算（四组）

判据：`audit-platform/frontend/src/components/workpaper/composables/__tests__/d567Property9DownstreamRecompute.spec.ts`

### 5.1 四组链路（现读实证）

| # | store 键 | 消费方 | 层数 |
|---|---|---|---|
| ① | `D5-4-rows` | `useD5CrossSheet`：fairValueRows → fairValueTotal(Σ `row.fairValue`) → ociChange(小计 − 公允价值合计) → adjudicationForDisclosure | 3 |
| ② | `D6-8-single-rows` | `useD6CrossSheet`：eclReferenceValues.single(Σ `r.expectedProvision`) → .total → eclVsImpairmentDiff / eclForDisclosure | 3 |
| ③ | `D7-7-post-rows` | `useD7CrossSheet.voucherPostTransferTotal`(Σ `r.creditAmount`) | 1 |
| ④ | `D7-7-post-rows` | `useD7Detail` 的 **watch**：按 `customerName` 聚合 → 写 `postTransfer` 到 `companyName` 匹配行 → `persistRows()` | 1 + 落库 |

判据形态：每组做**两轮回写**（A → B → C），逐轮断言跟上。只测一轮会漏掉
「首次读取正确但之后不再跟随」（`ref` 误用的典型症状）。

### 5.2 🔴 抓到的真缺陷：D7 期后结转联动在打开底稿时不生效

根因：`D7-7-post-rows` 的 watch 是 `immediate: true`，在 setup **当场**跑一次，
而那一刻 `rows` 还是空数组 —— rows 的 watch 被 `if (!segments.value.length) return`
挡着（账龄段是**异步** fetch）。等 rows 真加载好，post-rows watch 的源（remark）**没变**
⇒ **永不重跑** ⇒ `postTransfer` 停在 0。只有事后再改一次 D7-7 才会补上。

修法：watch 源加 `() => rows.value.length`。
**不能**直接用 `rows` 当源：回调内 `rows.value = rows.value.map(...)` 每次产生新数组引用
⇒ 自触发死循环；`map` 不改变长度，故用长度当源安全。

### 5.3 测试构造的两个坑（实测踩过）

1. `useD7Detail` 必须**真组件挂载**（`mount` + `defineComponent`）。`effectScope` **不触发**
   `onMounted` ⇒ `useAgingConfig.fetchConfig()` 不跑 ⇒ segments 恒空 ⇒ rows 恒空
   ⇒ 判据测不到东西（首版就是这样，报 `expected undefined to be 300`）。
2. 必须 `vi.mock('@/services/apiProxy')` 提供 `api.get`，返回
   `{preset, effective_segments, subject_overrides}`，并在 `beforeEach` 调
   `clearAgingConfigCache()`。

---

## 六、变异清单（13 处，逐一验证判据承重）

| 变异 | 内容 | 结果 |
|---|---|---|
| A | 摘掉 D5 的 `snap===null` 降级 | 2 红，形态 `expected +0 to be 100`（上游值被显示成 0） |
| B | D5 同步器不冻结 snap | 6 红，形态 `snap 追上了新派生值 ⇒ 覆盖标记会自我擦除` |
| C | D7 nature 退回 `agg ? agg.X : manual` | 5 红，形态 `expected 200 to be 9999` |
| D | D7 aging 退回一个标志管两列 | 3 红，形态 `expected +0 to be 777` |
| E | D7 同步器不冻结 snap | 6 红，形态 `覆盖格丢了 cellOverrides` |
| F | D6 退回 `map.has()` | 8 红 |
| G | D6 摘掉 `removeDynamicRow` 的 snap 清理 | 精确 1 红 |
| H | D7-1 cell_mask 退回整行 mask | 精确点名 36 格 |
| I | D5-1 cell_mask 漏掉 B9 | 精确点名 `B9` |
| J | 摘掉 D7 一个覆盖徽标 | 1 红，`徽标数应为 4，实得 3` |
| K | 引擎 flat 分支 key 加前缀 | 2 红 |
| L | 真给 `SPEC_D62` 摘掉 `aging_layout` | 3 红，精确点名 `phase5_d6_contract_assets.SPEC_D62` + `flat 分支已无承载样本` + 8→0 字段 |
| M | `useD7Detail` watch 退回单源 | 1 红，精确复现 `expected +0 to be 300` |

### 🔴 诚实登记：两条判据在变异 F 下仍绿

变异 F（D6 退回 `map.has()`）下，`d6CellOverrideRender.spec.ts` 里的「①空串」与
「③同步器落库后」两条**仍然通过** —— 因为同步器（未被变异）会先把空串/旧值规范成派生值，
把读侧的 `map.has` 问题掩盖掉。故这两条的定性是**结果级回归守卫**，**不是**该反模式的
鉴别判据；鉴别力在「覆盖检出组 + ②」。已在判据文件内就地写明，并补一条直接断言
空串 → `null` 的鉴别判据（①b）。

---

## 七、可复现命令

```powershell
# 后端（cwd = 仓库根）
& ".venv\Scripts\python.exe" -m pytest `
  backend/tests/workpaper_sync/test_d567_property7_cell_mask_vs_template.py `
  backend/tests/workpaper_sync/test_d567_property2_store_item_id_exact_match.py `
  backend/tests/workpaper_sync/test_d567_property3_12_dual_zone_and_residual.py `
  backend/tests/workpaper_sync/test_d567_task13_aging_layout_path_comparison.py `
  backend/tests/workpaper_sync/test_d567_task11_layout_groups_invariant.py -q

# 前端（cwd = audit-platform/frontend）
npx vitest run `
  src/components/workpaper/composables/__tests__/d5CellOverrideRender.spec.ts `
  src/components/workpaper/composables/__tests__/d6CellOverrideRender.spec.ts `
  src/components/workpaper/composables/__tests__/d7CellOverrideRender.spec.ts `
  src/components/workpaper/composables/__tests__/d567Property9DownstreamRecompute.spec.ts `
  src/components/workpaper/__tests__/d567AdjCellOverrideUi.spec.ts
```

🔴 **前端禁用 `-t` 过滤**（会超时），必须指定单文件路径。
🔴 测试计数要可靠请用 `--reporter=json --outputFile=x.json` 再用 Python 读
（PowerShell 中文输出会乱码，`Select-String` 抓不到摘要行）。

---

## 八、仍未解除的外部依赖

| 项 | 阻塞 |
|---|---|
| 整册 materialize 真栈（Property 13） | 三家 `adapter_registered=False`，需 reviewed overlay + 发布链（umbrella Task 36/77） |
| Property 4 位移链 2 红 | 同上（需真实 instrumentation 注入） |
| 真栈三段（切在线编辑 → OO canvas 逐值 → 改一格 → forcesave → 回读等值） | 同上 |
| Playwright 实测徽标与「恢复取数」交互 | 待 `start-dev.bat` 环境 |
| D6-1 的 A 列镜像公式是否该 mask | 与框架不变量 `assert_data_cells_not_masked()` 冲突，需框架层裁决 |

### 预存失败（非本轮引入，已实证归因）

`audit-platform/frontend/src/components/workpaper/__tests__/useD7AgingLifecycle.spec.ts`
的 `Property 6: 长期挂账筛选 + 账龄 label（importFromD72）` 是 fast-check 随机 seed 偶发，
**实测偶发率 ~30%**（`git stash` 掉本轮 `useD7Detail.ts` 改动后，10 次跑出 3 次失败）。
该测试不涉及 `D7-7-post-rows` / `postTransfer`，本轮改动在该场景下回调首行即 `return`，
是可证明的 no-op。根因是浮点并列时「顺序首个最大值优先」的判定，属该测试自身的口径问题。
