# N 循环税务类披露表与附注对齐 — 设计

## Overview

三个循环、五个需要披露的 Tab（N4 国企不披露），全部按 N1 已验证的范式做：
底稿披露表逐字对齐源模板 → 载荷把底稿形状投影成附注形状 → 附注模板修掉 md 重建缺陷。
与 N1 的区别是这三个循环**同步链路从零建立**（此前完全没有入口），且 N4 国企要落成
「本版不适用」而不是造表。

复用 N1 已建的三个共用件：`N1DisclosureSegmentTable`（分段/两级表头/公式行/动态增行，
本 spec 的表都是单级平表，用 `label: ''` 单段模式）、`N1DisclosureConsistencyPanel`（勾稽展示）、
`n1DisclosureSegmentTypes`（渲染契约类型）。→ 三者从 `n1/shared` 提升到
`components/workpaper/shared/disclosure/`，N1 侧改为 re-export 保持零回归。

## Architecture

```
源 xlsx 披露 sheet（权威）
  └─► 底稿披露 Tab（可编辑 + 公式行 + 勾稽）
        └─► build{N2,N4,N5}SyncPayload  ← 列结构投影成附注形状
              └─► POST /disclosure-notes/sync-from-workpaper
                    └─► disclosure_notes.sub_table_data (+ _sub_table_columns)
                          └─► 读时 project_sub_tables + carry_template_guidance
                                └─► 附注 TAB / Word 导出
note_template_{listed,soe}.json ──► seed 路径（新建项目骨架，幂等脚本维护）
```

裁决表与 N1 一致：底稿行/列/文本随源 xlsx；附注**列结构**随源 xlsx（压扁是 md 重建 bug）；
附注**行集合 / 表名**以附注模板为准（唯一例外见 §3.3 N5 表名去重，因同名会丢表）。

## Components and Interfaces

| 文件 | 职责 |
|---|---|
| `backend/scripts/fix/fix_note_n_cycle_tax_structure.py` | 幂等修订 五、41 / 八、41 / 五、63 / 三、所得税费用 / 八、78 |
| `backend/tests/services/test_note_n_cycle_tax_structure.py` | 结构守卫 |
| `backend/tests/e2e/test_note_n_cycle_tax_detail_e2e.py` | 进程内 ASGI 验读时投影 + guidance |
| `composables/shared/disclosureConsistency.ts` | 从 `n1DisclosureConsistency` 提取的通用 `eqCheck` / `summarize` |
| `composables/n2NoteSectionMap.ts` | N2 章节/sheet/子表名/列定义/载荷 |
| `composables/n4NoteSectionMap.ts` | N4 同上；`soe` 返回 `null` |
| `composables/n5NoteSectionMap.ts` | N5 同上（含表名去重后的键） |
| `composables/useN2DisclosureTables.ts` 等 ×3 | 编制模型（行骨架 / 公式 / 勾稽入参 / 载荷组装 / 持久化键） |
| `n2/core/N2TabDisclosure{Listed,Soe}.vue` 等 | 渲染（重建） |
| `n4/core/N4TabDisclosureSoe.vue` | 改为「本版不适用」说明页 |

## Data Models

### 1. 源模板权威结构（实证）

#### N2 应交税费（`附注披露信息（上市公司）` A1:K27 / `附注披露信息（国企）` A1:K24）

上市（R7 表头，R8~R22 数据行取自 N2-1 审定表，R23 合计）：

```
税  项 | 期末余额 | 上年年末余额
…（动态税种行，源模板 15 行引用位）
合  计 | =SUM(B8:B22) | =SUM(C8:C22)
```

说明 R24~R26：`说明：` / `（小税（费）种可合并反映。）` /
`（对于满足条件将当期所得税资产及当期所得税负债以抵销后的净额列示的情况，…）`
提示 R27：`【提示：增值税，根据"应交税费-为交增值税、简易计税、转让金融商品应交增值税、代扣代缴增值税"科目贷方余额计算填列；】`
（⚠️ 源模板 R27 有错字「为交增值税」，附注模板已修为「未交增值税」→ **以附注模板为准**）

国企（R7 表头，R8~R22 取自 N2-2 明细，R23 合计）：

```
项  目 | 期初余额 | 本期应交 | 本期已交 | 期末余额
…（动态税种行）                          =B8+C8-D8
合  计 | =SUM(B8:B22) | =SUM(C8:C22) | =SUM(D8:D22) | =SUM(E8:E22)
```

提示 R24：`【提示：增值税，根据"应交税费-未交增值税、简易计税、转让金融商品应交增值税、代扣代缴增值税"科目贷方余额计算填列。】`

#### N4 税金及附加（`附注披露信息（上市公司）` A1:L18 / `附注披露信息（国企）` A1:K17）

上市：

```
项  目 | 本期发生额 | 上期发生额
…（R8~R16 取自 N4-1 审定表）
合  计 | =SUM(B8:B16) | =SUM(C8:C16)
```

说明 R18：`各项税金及附加的计缴标准详见附注四、税项。`

国企：R5 `附注披露信息：` + R6 **`无`** —— 全 sheet 无表。**国企版不披露**。

#### N5 所得税费用（`附注披露信息（上市公司）` A1:L29 / **`附注披露信息（国企`** A1:IU32）

上市表（1）R7~R11：

```
（1）所得税费用明细
项  目 | 本期发生额 | 上期发生额
按税法及相关规定计算的当期所得税
递延所得税费用
合  计 | =SUM(C9:C10) | =SUM(D9:D10)
```

上市表（2）R12~R25：标题 `（2）所得税费用与利润总额的关系列示如下：（不适用项目可删除，"其他"金额不应过大）`，
3 列，13 行（R14~R25 取自 N5-2 明细 A9:A20）。
注 R27~R29：`所得税费用等于第二行至倒数第二行之和` / `对以前期间当期所得税的调整`定义 /
`"不可抵扣的成本、费用和损失"、"未确认可抵扣亏损和可抵扣暂时性差异的纳税影响"不应为负数`。

国企表（1）R7~R11：3 列，行 = `当期所得税费用` / `递延所得税调整` / `其他` / `合  计`（`=SUM(C8:C10)`）。
国企表（2）R13~R28：标题 `（2）会计利润与所得税费用调整过程：（国资委格式未要求披露，建议披露）`，
3 列（R14 表头 `项  目` / `本期发生额` / `上期发生额`），14 行动态（取自 N5-2 A9:A22）。
注 R30~R32 同上市口径。

🔴 **国企 sheet 的 xlsx tab 名是 `附注披露信息（国企`（缺右括号）**，A2 单元格才是完整的
`附注披露信息（国企）`。`workpaper_sheet_classification` 记的是 tab 名 → 同步 `sheet_name` 用 tab 名。

### 2. 附注模板目标结构

| 章节 | 表 | headers | 表头形态 |
|---|---|---|---|
| 五、41 应交税费 | 应交税费 | `税项`/`期末余额`/`上年年末余额` | `flat` |
| 八、41 应交税费 | 应交税费 | `项目`/`期初余额`/`本期应交`/`本期已交`/`期末余额` **（3→5 列）** | `flat` |
| 五、63 税金及附加 | 税金及附加 | `项目`/`本期发生额`/`上期发生额` | `flat` |
| 三、所得税费用 | **所得税费用明细**（原 `项  目`） | `项目`/`本期发生额`/`上期发生额` | `flat` |
| 三、所得税费用 | **所得税费用与利润总额的关系**（原 `项  目`） | 同上 | `flat` |
| 八、78 所得税费用 | 所得税费用 | `项目`/`本期发生额`/`上期发生额` | `flat` |
| 八、78 所得税费用 | **会计利润与所得税费用调整过程**（原 `所得税费用`） | `项目`/`本期发生额`/`上期发生额` **（2→3 列）** | `flat` |

行集合全部保持附注模板既有值（逐字见幂等脚本常量）。

### 3. 前端数据形态

一表一持久化 item，`conclusion` 存整表 JSON：

| item_id | 内容 |
|---|---|
| `N2-disclosure-{v}-taxes` | `[{item, end, prior}]`（上市）/ `[{item, opening, payable, paid}]`（国企，`end` 为公式不落库） |
| `N4-disclosure-listed-taxes` | `[{item, current, prior}]` |
| `N5-disclosure-{v}-detail` | 表（1）`[{item, current, prior}]` |
| `N5-disclosure-{v}-reconcile` | 表（2）`[{item, current, prior}]` |
| `{X}-disclosure-{v}-conclusion` | `remark` = 披露说明与结论 |
| `{X}-disclosure-{v}-synced-tables` | `conclusion` = 已同步表名 JSON（孤儿清理基线） |

`saveBatch` 调用点按 itemId 去重（同批重复 id 后端整批拒绝）。

## Correctness Properties

### Property 1: 键集合三方相等

`sub_table_data` 数据键 ≡ `columns` 键 ≡ 该变体子表名全集（N2 各 1 / N4 listed 1 / N5 各 2）。

**Validates: Requirements 6.3**

### Property 2: 子表名双向覆盖且无重名

子表名与附注模板 `tables[].name` 逐字一致、双向无遗漏，且**同章节内互不重名**
（重名会让 `sub_table_data` 键互相覆盖丢表）。

**Validates: Requirements 5.2, 6.3, 7.1**

### Property 3: 两版列结构本质不同不得共用

N2 上市 3 列双期 vs 国企 5 列变动 —— 列定义必须分别构造；反向断言两者列数与键集不等。

**Validates: Requirements 1.5**

### Property 4: N4 国企不产出载荷也不产出章节

`buildN4SyncPayload('soe', …)` 恒返回 `null`；`variant_matrix` 的 `shui_jin_ji_fu_jia.soe_*` 保持 `None`；
模板不含国企税金及附加章节。

**Validates: Requirements 2.4, 5.7, 6.5**

### Property 5: sheet 名逐字（含缺括号）

`N5_DISCLOSURE_SHEET_NAME.soe === '附注披露信息（国企'`，且与
`workpaper_sheet_classification` / `note_workpaper_sync_registry` 逐字一致。

**Validates: Requirements 6.2, 7.3**

### Property 6: 表头形态必须表态

每张表任一列带 `flat`（本 spec 全是单级表头），不得未表态（否则 seed 路径被前缀推断塞父表头）。

**Validates: Requirements 5.4**

### Property 7: 行型判定先去空白

`合  计` 去空白后判定并打 `is_total`。

**Validates: Requirements 6.4**

### Property 8: 缺失写 null 不写 0

取不到的金额恒 `null`；求和全 null 时返回 `null`。

**Validates: Requirements 6.4**

### Property 9: N2 国企期末余额恒等式

每行 `期末余额 = 期初余额 + 本期应交 − 本期已交`（源模板 `=B8+C8-D8`），容差 0.01 元；
任一项为 `null` → skip。

**Validates: Requirements 4.2**

### Property 10: N5 跨表勾稽

表（2）`所得税费用` 行 = 表（1）`合  计`；表（2）`所得税费用` 行 = 第 2 行至倒数第 2 行之和。

**Validates: Requirements 4.5, 4.6**

### Property 11: 幂等与纯函数

幂等脚本重跑逐字节相等；载荷构造同输入深相等且不改入参。

**Validates: Requirements 5.8**

### Property 12: 孤儿键上报

N5 表名去重后，既有已同步项目的旧键（`项  目` / 重复的 `所得税费用`）进 `_removed_table_keys`；
本次推送的键绝不进（推送优先）。

**Validates: Requirements 6.7**

## Error Handling

- 同步失败 `ElMessage.error`；请求取消不算失败；**失败时不 `markSynced`**
- 缺项目上下文：拦在发请求前
- N4 国企 Tab 点同步：不显示同步按钮（无载荷），只显示「本版不适用」说明
- 幂等脚本遇章节数 ≠ 1 → `SystemExit`，不猜
- 读时 guidance 回填/投影异常已由 N1 spec 的 try/except 兜住

## Testing Strategy

| 层 | 覆盖 |
|---|---|
| 后端结构 | `test_note_n_cycle_tax_structure.py`（列数/表名去重/表态/guidance/text_sections/幂等） |
| 后端读时 | `test_note_n_cycle_tax_detail_e2e.py`（进程内 ASGI，表数/列/guidance） |
| 前端载荷 | `n{2,4,5}NoteSectionMap.spec.ts`（Property 1~8, 11, 12） |
| 前端契约 | `n{2,4,5}NoteSubtableContract.spec.ts`（共享 helper 5 条 + 无重名 + 全表 guidance） |
| 前端勾稽 | `nCycleTaxConsistency.spec.ts`（含 PBT：N2 恒等式、N5 跨表） |
| 平台守卫 | `disclosureColumnsCoverage` / `disclosureSheetNameRegistry` / `disclosureAutoSyncCoverage`（清单变短） |
| 实测 | chrome-devtools 5 Tab + postgres 只读 |
| CI | job `note-n-cycle-tax-structure` |

## 风险与规避

| 风险 | 规避 |
|---|---|
| N5 表名去重使既有项目产生孤儿键 | `_removed_table_keys` + `N5_TABLE_NAMESPACE` 基线播种；契约测试锁旧键在 `legacyObsolete` |
| 共用件从 `n1/shared` 提升路径 | N1 侧留 re-export，N1 全量测试作回归门 |
| N4 国企「不适用」被误当成缺功能 | Tab 内写明源模板依据（`附注披露信息：无`）+ 指向上市版；契约测试反向断言 `null` |
| 章节 `三、所得税费用` 位置不对 | 本 spec 不动；tasks 记为跨 spec 依赖并在交付说明标注 |
| 并发会话回退同一文件 | 幂等脚本 + 契约测试；可能已存在的文件用 `str_replace` |
