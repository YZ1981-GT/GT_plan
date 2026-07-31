# N1 递延所得税资产披露表与附注对齐 — 设计

## Overview

三层链路对齐同一个权威源（底稿源 xlsx 的两张披露 sheet）：底稿披露组件按源模板逐字重建、
同步载荷把底稿形状投影成附注形状、附注模板 JSON 修掉 md 重建器造成的列压扁与缺表。
新增披露内部勾稽（规则全部取自源模板公式）与两级表头分段表共用组件。

关键约束三条：①两版表 1 的**子列序在源模板里相反**，必须单一真源；②附注**行集合**以
附注模板为准（seed 行会被底稿整表覆盖），只有**列结构**跟随源 xlsx；③取不到的金额写
`null`，禁止用 0 冒充。

## Architecture

见 §2 的三层分工图与裁决表。数据流：
源 xlsx（权威）→ 底稿披露组件（可编辑 + 勾稽）→ `buildN1SyncPayload` 列结构投影
→ `POST /disclosure-notes/sync-from-workpaper` → `disclosure_notes.sub_table_data`
→ 读时 `project_sub_tables` + `carry_template_guidance` → 附注 TAB / Word 导出。
seed 路径（新建项目）另从 `note_template_{listed,soe}.json` 生成骨架。

## Components and Interfaces

见 §5「前端结构」（组件与 composable 清单）、§4「幂等脚本」、§6「同步载荷」。
新增后端读时组件 `note_table_guidance.carry_template_guidance(tables, template_type, section_number)`。

## Data Models

见 §3「附注模板目标结构」（两版表清单 / headers / 表头形态 / 行骨架）、
§5.1「数据形态」（持久化键与 JSON 载荷）、§6（`sub_table_data` 行键与 `columns` 键序）。

## Correctness Properties

### Property 1: 键集合三方相等
`sub_table_data` 数据键集合 ≡ `columns` 键集合 ≡ 该变体子表名全集（listed 4 / soe 5）。
验证：`n1NoteSectionMap.spec.ts` Property 2/9。

**Validates: Requirements 5.3**

### Property 2: 子表名双向覆盖
子表名与附注模板 `tables[].name` 逐字一致，且模板该章节每张表都有映射（无孤儿、无遗漏）。
验证：`n1NoteSubtableContract.spec.ts` P1 / P6。

**Validates: Requirements 5.3, 6.2**

### Property 3: 表 1 两级表头且两版子列序相反
表 1 为 5 列两级表头；上市子列序 `[暂时性差异, 递延税资产/负债]`、国企 `[递延税资产/负债, 暂时性差异]`；
`columns` 键序必须跟随子列序（否则附注列错位）。验证：Property 12 / P9 / 后端 `test_unoffset_two_level_header`。

**Validates: Requirements 1.1, 2.2, 5.1**

### Property 4: 表头形态必须表态
每张表在 `group`（多级）与 `flat`（单级）之间明确表态，不得都无、不得并存；单级表不得带 `_column_groups`。
验证：后端 `test_every_table_declares_header_state` + 前端 P3。

**Validates: Requirements 4.5**

### Property 5: 行型判定先去空白
`normalizeN1RowLabel` 去空白后再判 `小计`/`合计`（源模板写 `小  计`、`合  计`），命中即打 `is_total`。

**Validates: Requirements 5.4**

### Property 6: 缺失写 null 不写 0
取不到的金额恒为 `null`；`sumNullable` 在全 null 时返回 `null`（不塌成 0）。

**Validates: Requirements 5.5**

### Property 7: 勾稽容差与 skip 语义
相等类容差 0.01 元；任一侧 `null` → `level='skip'`（不误报）；段内无明细行时不产出该条校验。

**Validates: Requirements 3.6**

### Property 8: 幂等与纯函数（后端）
幂等脚本重跑结果逐字节相等（`apply(check_only=True)` 返回 False）；`build_*_tables()` 为纯函数且不共享可变行对象。

**Validates: Requirements 4.9**

### Property 9: guidance 回填零回归
按表名逐字命中才贴；已有非空 `guidance` 不覆盖；模板/章节/表名任一对不上则原样返回。

**Validates: Requirements 4.6**

### Property 10: 载荷构造为纯函数
`buildN1SyncPayload` 同输入多次调用深相等，且不修改入参 snapshot。

**Validates: Requirements 5.1**

## Error Handling

- 同步失败：`ElMessage.error` 提示；请求取消（`ERR_CANCELED`）不算失败；
  **失败时不 `markSynced`**（否则会把现存表当孤儿删）
- 缺项目上下文：同步/跳转前 `ElMessage.warning` 拦住，不发请求
- 读时 guidance 回填与投影都包在 `try/except` 内，失败降级不阻断读取
- 模板 JSON 损坏 / 章节缺失：`load_section_guidance` 返回空 dict（表现为提示为空，不报错）
- 幂等脚本遇章节数 ≠ 1 时 `SystemExit`，不做猜测性写入

## Testing Strategy

| 层 | 覆盖 |
|---|---|
| 后端结构守卫 | `test_note_deferred_tax_structure.py`（表数/列数/`_column_groups`/表态/guidance/text_sections/无假数据行/幂等） |
| 后端读时链路 | `test_note_deferred_tax_read_projection.py`（真实同步载荷形状走投影 + guidance 回填） |
| 后端 guidance 回填 | `test_note_table_guidance.py`（逐字命中/不覆盖/跨模板不串味/mtime 缓存失效） |
| 前端载荷 | `n1NoteSectionMap.spec.ts`（Property 1~12） |
| 前端契约 | `n1NoteSubtableContract.spec.ts`（共享 helper 5 条 + N1 专属 P6~P10） |
| 前端勾稽 | `n1DisclosureConsistency.spec.ts`（单测 + 4 条 PBT） |
| 平台守卫 | `disclosureColumnsCoverage` / `disclosureSheetNameRegistry` / `disclosureAutoSyncCoverage` |
| 实测 | chrome-devtools 驱动两 Tab + postgres 只读比对落库 |
| CI | job `note-deferred-tax-structure`（`--check` + 契约测试） |

## 1. 源模板权威结构（实证）

来源：`backend/wp_templates/N/N1 递延所得税资产.xlsx`（运行时权威目录；参考副本缺失）。
两张披露 sheet 逐行读取 + 合并单元格解析结果如下。

### 1.1 `附注披露信息（上市公司）` A1:K54

标题 R8 `递延所得税资产与递延所得税负债`。

**表（1）R9~R32 未经抵销的递延所得税资产和递延所得税负债**

合并单元格 `A10:A11`、`B10:C10`、`D10:E10` → 两级表头：

```
项  目 │      期末余额       │     上年年末余额
       │ 可抵扣/应纳税  递延 │ 可抵扣/应纳税  递延
       │ 暂时性差异   所得税 │ 暂时性差异   所得税
       │             资产/负债│             资产/负债
```

行（`A12:E12`、`A22:E22` 为整行合并的分组标题）：

| 行 | 内容 | 类型 |
|---|---|---|
| R12 | `递延所得税资产：` | 分组标题（整行合并） |
| R13~R19 | 资产减值准备 / 可抵扣亏损 / 内部交易未实现利润 / 公允价值变动 / 租赁负债 / 购入摊销年限小于税法规定的资产 / 其他 | 数据 |
| R20 | （空，预留插行） | 数据 |
| R21 | `小  计` = `SUM(B13:B20)` | 小计 |
| R22 | `递延所得税负债：` + F22 红字「递延所得税负债数据来源于递延所得税负债底稿」 | 分组标题（整行合并） |
| R23~R27 | 购入摊销年限大于税法规定的资产 / 可供出售金融资产公允价值变动 / 投资性房地产公允价值变动 / 使用权资产 / 其他 | 数据 |
| R28 | （空，预留插行） | 数据 |
| R29 | `小计` = `SUM(B23:B28)` | 小计 |

文本：
- R30 `说明：其中一年后预期转回的递延所得税资产和递延所得税负债分别为X.XX元、X.XX元。`（**可编辑正文**）
- R31 `【提示：连续亏损的情况下，仍将较大金额的未抵扣亏损确认递延所得税资产，对当期净利润影响较大，甚至扭亏为盈，应当披露相关判断依据】`
- R32 `【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】`

**表（2）R33~R36 以抵销后净额列示的递延所得税资产或负债（不适用的删除）**

单级 5 列：`项  目` / `递延所得税资产和负债期末互抵金额` / `抵销后递延所得税资产或负债期末余额` /
`递延所得税资产和负债期初互抵金额` / `抵销后递延所得税资产或负债期初余额`。
行：`递延所得税资产` / `递延所得税负债`。

**表（3）R37~R43 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细**

3 列：`项  目` / `期末余额` / `上年年末余额`。
行：`可抵扣暂时性差异` / `可抵扣亏损` / （空）/ `合  计` = `B39+B40`。
注 R43：`列示由于未来能否获得足够的应纳税所得额具有不确定性，因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。`

**表（4）R44~R53 未确认递延所得税资产的可抵扣亏损将于以下年度到期**

4 列：`年  份` / `期末余额` / `上年年末余额` / `备注`。
行：2022~2027 年（首年备注列示 `——`、末年上年年末列示 `——`）+ `合  计` = `SUM(B46:B51)`。
注 R53：`无法在资产负债表日确定全部可抵扣亏损情况的，可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。`

**勾稽 R54**：`=B40=B52` / `=C40=C52` → 表（3）「可抵扣亏损」行 = 表（4）`合  计`（期末列 + 上年年末列各一条）。

### 1.2 `附注披露信息（国企）` A1:IV74

标题 R6 `递延所得税资产和递延所得税负债`。
R7 前置口径：`递延所得税资产和递延所得税负债不以抵销后的净额列示的，按（1）披露；若递延所得税资产和递延所得税负债以抵销后的净额列示的，按（2）披露。`

**表（1）R8~R31**（`（1）…不以抵销后的净额列示` / `A、已确认递延所得税资产和递延所得税负债`）

合并 `A10:A11`、`B10:C10`、`D10:E10` → 两级 5 列，父表头 `期末余额` / `年初余额`。
🔴 **子列序与上市相反**：`递延所得税资产/负债` 在前、`可抵扣/应纳税暂时性差异` 在后。

行：`一、递延所得税资产`（R12）+ R13~R19 引用上市 A13:A19 同 7 项 + 空行 + `小 计`（R21）；
`递延所得税负债：`（R22 整行合并）+ R23~R27（第 4 项为 **`租赁形成`**，上市是 `使用权资产`）+ 空行 + `小计`（R29）。

提示 R30 `【提示：资产减值准备，含"持有待售资产减值准备"】`；
注 R31 `【注：计入其他综合收益的其他金融资产为计入其他综合收益的其他债权投资、其他权益工具投资。】`

**表（2）R32~R52**（`（2）…以抵销后的净额列示` / `A、互抵后的…`）

单级 5 列：`项  目` / `报告期末互抵后的递延所得税资产或负债` / `报告期末互抵后的可抵扣或应纳税暂时性差异` /
`报告年初互抵后的递延所得税资产或负债` / `报告年初互抵后的可抵扣或应纳税暂时性差异`。
行：`一、递延所得税资产` + 7 项 + `小 计`（R44）+ `二、递延所得税负债` + 5 项 + `小 计`（R52）。

**表（3）R54~R58**（`B、递延所得税资产和递延所得税负债互抵明细：`）

2 列：`项  目` / `本期互抵金额`；行为空（自行填列）。

**表（4）R59~R63 未确认递延所得税资产明细** —— 3 列（`项  目` / `期末余额` / `年初余额`）+ `合  计` = `B61+B62`。

**表（5）R64~R73** 同上市表（4），期初列名为 `年初余额`。

**勾稽 R74**：`=B72=B62` / `=C72=C62` → 表（5）`合  计` = 表（4）「可抵扣亏损」行。

## 2. 三层分工与裁决

```
源 xlsx 披露 sheet ──► 底稿披露组件（行/列逐字，含审计可编辑区）
                          │  buildN1SyncPayload（列结构投影成附注形状）
                          ▼
                    disclosure_notes.sub_table_data（_source=workpaper，整表覆盖）
                          ▲
note_template_{listed,soe}.json ─► seed 路径（新建项目 / 重新生成附注时的骨架）
```

**裁决规则**

| 维度 | 权威 | 理由 |
|---|---|---|
| 底稿披露表行/列/文本 | 源 xlsx | 底稿是底稿 |
| 附注**列结构** | 源 xlsx（因附注模板的压扁是 `rebuild_note_from_md.py` 已知 bug） | 压扁签名 = 残留 `header_label` 假数据行，两版表 1 均有 |
| 附注**行集合** | 附注模板既有（md 派生） | 附注是交付物；且 `_source=workpaper` 时 seed 行会被底稿整表覆盖，行骨架只服务"从未同步过的项目" |
| 附注**表名** | 附注模板既有 | 改名产生孤儿表，收益低 |
| 措辞冲突（`期初` vs `上年年末`） | 附注模板 | listed 全节统一 `上年年末`；源 xlsx 表 2 用「期初」属其内部不一致 |

国企表 2 是唯一例外：模板只有 2 行（`一、递延所得税资产` / `二、递延所得税负债`）是 md 简写，
源 xlsx 明确列了与表 1 同构的明细 → 按 xlsx 补齐骨架（同 G9 国企的既有裁决）。

## 3. 附注模板目标结构

### 3.1 listed 五、30（4 表）

| # | 表名（不变） | headers | 表头 |
|---|---|---|---|
| 1 | 未经抵销的递延所得税资产和递延所得税负债 | `项目` + `可抵扣/应纳税暂时性差异`,`递延所得税资产/负债` ×2 | `_column_groups` = `期末余额`(1,2) / `上年年末余额`(3,2) |
| 2 | 以抵销后净额列示的递延所得税资产或负债 | 5 列（保持现状文案） | `flat` |
| 3 | 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细 | `项目`/`期末余额`/`上年年末余额` | `flat` |
| 4 | 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | `年份`/`期末余额`/`上年年末余额`/`备注` | `flat` |

表 1 行（删首行假数据行 `项目`，其余不动）：
`递延所得税资产：`(data,1811/BS-018) / 资产减值准备 / 内部交易未实现利润 / 开办费 / 可抵扣亏损 / 租赁负债(2601/BS-042) /
`小计`(subtotal) / `递延所得税负债：` / 非同一控制企业合并资产评估增值 / 交易性金融工具、衍生金融工具的估值 /
计入其他综合收益的应收款项融资公允价值变动 / 计入其他综合收益的其他债权投资公允价值变动 / 使用权资产(1641~1643/BS-019) / `小计`(subtotal)。

### 3.2 soe 八、31（5 表）

| # | 表名 | headers | 表头 |
|---|---|---|---|
| 1 | 未经抵销的递延所得税资产和递延所得税负债 | `项目` + `递延所得税资产/负债`,`可抵扣/应纳税暂时性差异` ×2 | `group` = `期末余额`(1,2) / `年初余额`(3,2) |
| 2 | 以抵销后净额列示的递延所得税资产或负债 | 5 列（报告期末/报告年初 × {资产或负债, 可抵扣或应纳税暂时性差异}） | `flat` |
| 3 | **递延所得税资产和递延所得税负债互抵明细**（新增） | `项目`/`本期互抵金额` | `flat` |
| 4 | 未确认递延所得税资产明细 | `项目`/`期末余额`/`期初余额` | `flat` |
| 5 | 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | `年份`/`期末余额`/`期初余额`/`备注` | `flat` |

⚠️ soe 表 4/5 的第 3 列模板既有文案是 `期初余额`（源 xlsx 是 `年初余额`）→ 按裁决表保持模板文案，
但底稿披露表 UI 用源 xlsx 的 `年初余额`，同步 `columns` 的 label 必须与模板 headers 对齐（否则表头错位）。
**结论**：附注侧统一 `期初余额`；底稿 UI 侧标注 `年初余额（期初）` 会引入双真源 → 底稿 UI 也用 `期初余额`，
并在 guidance 注明「源模板称年初余额」。

表 2 行骨架（新，对齐表 1 明细）：
`一、递延所得税资产` + 表 1 资产段 7 项 + `小计` + `二、递延所得税负债` + 表 1 负债段 4 项 + `小计`。

### 3.3 `text_sections`

统一 `#### {表名}` 作表标题（`_is_table_title_paragraph` 对任意 `#` 前缀都判为标题，不进正文），
实质披露文本作无前缀段落。

listed：
```
#### 未经抵销的递延所得税资产和递延所得税负债
说明：其中一年后预期转回的递延所得税资产和递延所得税负债分别为X.XX元、X.XX元。
【提示：连续亏损的情况下，…应当披露相关判断依据】
【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】
{证监会会计类第5号可转债段落 —— 保留模板既有原文，不补全其截断}
#### 以抵销后净额列示的递延所得税资产或负债（不适用的删除）
#### 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细
注：列示由于未来能否获得足够的应纳税所得额具有不确定性，…
#### 未确认递延所得税资产的可抵扣亏损将于以下年度到期
注：无法在资产负债表日确定全部可抵扣亏损情况的，…
```

soe：
```
#### 未经抵销的递延所得税资产和递延所得税负债
递延所得税资产和递延所得税负债不以抵销后的净额列示的，按（1）披露；…按（2）披露。
【提示：资产减值准备，含"持有待售资产减值准备"】
【注：计入其他综合收益的其他金融资产为…】
#### 以抵销后净额列示的递延所得税资产或负债
#### 递延所得税资产和递延所得税负债互抵明细
#### 未确认递延所得税资产明细
#### 未确认递延所得税资产的可抵扣亏损将于以下年度到期
【注：无法在资产负债表日确定全部可抵扣亏损情况的，…】
```

### 3.4 `guidance`

只取源模板红字 / 附注模板既有【提示】【注】/ 以「勾稽：」前缀标注的工具口径。
例（listed 表 1）：
> 资产段与负债段分别列示，各段末置小计。负债段数据来源于递延所得税负债底稿（源模板 F22 红字）。
> 勾稽：小计 = 段内各项之和。

## 4. 幂等脚本

`backend/scripts/fix/fix_note_deferred_tax_structure.py`

- 结构由 `build_listed_tables()` / `build_soe_tables()` 纯函数产出；`apply()` 比对 `tables` / `text_sections` / `_aligned_by`
- `--dry-run`（默认打印 diff 摘要不写盘）/ `--check`（不一致则 exit 1，供 CI）/ 默认写盘
- `_aligned_by = "n1-deferred-tax-disclosure-template-alignment"`
- 落盘保持 `json.dumps(..., ensure_ascii=False, indent=2)` + `write_bytes`（LF、无尾随换行），避免整文件 diff

## 5. 前端结构

```
composables/
  n1NoteSectionMap.ts            重写：5 表 columns（group/flat）+ 载荷构造
  n1DisclosureConsistency.ts     新建：勾稽纯函数引擎
  __tests__/n1NoteSubtableContract.spec.ts   新建：契约（共享 helper + 附加断言）
  __tests__/n1DisclosureConsistency.spec.ts  新建：勾稽单测 + PBT
n1/core/
  N1TabDisclosureListed.vue      重写：4 表 + 说明区 + 勾稽面板
  N1TabDisclosureSoe.vue         重写：5 表 + 前置口径 + 勾稽面板
n1/shared/
  N1DisclosureConsistencyPanel.vue  新建：紧凑 bar + 折叠明细（范式抄 H1）
  N1DisclosureGroupTable.vue        新建：两级表头 + 分段小计的共用表组件（两变体共用，列序/父表头由 props 驱动）
```

### 5.1 数据形态

单一持久化键（per variant）承载全部表，避免 40+ 个 checklist item：

| item_id | 内容 |
|---|---|
| `N1-disclosure-{v}-unoffset` | `conclusion` = JSON `{asset:[{item,diffEnd,taxEnd,diffPrior,taxPrior}], liability:[...]}` |
| `N1-disclosure-{v}-netoffset` | `conclusion` = JSON（listed 2 行 / soe 资产+负债两段） |
| `N1-disclosure-soe-offsetdetail` | `conclusion` = JSON `[{item, amount}]` |
| `N1-disclosure-{v}-unrecognized` | `conclusion` = JSON `[{item,end,prior}]` |
| `N1-disclosure-{v}-lossexpiry` | `conclusion` = JSON `[{year,end,prior,remark}]` |
| `N1-disclosure-{v}-rollback-note` | `remark` = R30 说明正文 |
| `N1-disclosure-{v}-conclusion` | `remark` = 披露说明与结论 |

🔴 `saveBatch` 调用点按 itemId 去重（同批重复 id 会让后端整批拒绝）。

### 5.2 两级表头渲染

嵌套 `el-table-column`：外层 `label="期末余额"` 内嵌两个子列。列序由 `variant` 决定：

```ts
const endSubCols = variant === 'listed'
  ? [['diff', '可抵扣/应纳税暂时性差异'], ['tax', '递延所得税资产/负债']]
  : [['tax', '递延所得税资产/负债'], ['diff', '可抵扣/应纳税暂时性差异']]
```

同步 `columns` 的 `key` 顺序必须与之一致，否则附注列错位。

### 5.3 勾稽引擎

`n1DisclosureConsistency.ts`：

```ts
export interface N1CheckResult {
  label: string; rule: string
  left: number | null; right: number | null; diff: number | null
  level: 'ok' | 'warn' | 'error' | 'skip'
  detail?: string; refs?: string[]
}
export function runN1DisclosureChecks(variant, snapshot): N1CheckResult[]
```

- 容差 0.01 元（`eqCheck`）
- 任一侧为 `null` → `level='skip'`（不误报）
- 规则集：R3.1~R3.5

## 6. 同步载荷

`buildN1SyncPayload(variant, snapshot, ctx)`：

- `sub_table_data` 键 = `N1_SUB_TABLE_KEYS[variant]` 的值（逐字取自附注模板 `tables[].name`）
- 行型判定 `normalizeRowLabel(s) = s.replace(/\s+/g,'')` 后 `startsWith('小计'|'合计')`
- 结构行（分组标题）推 `row_type: 'header_label'`；小计/合计推 `is_total: true`
- 空值列写 `null` 保列键齐备
- `_removed_table_keys` 由 `buildRemovedTableKeys({previouslySynced, legacyObsolete, pushed})` 产出；
  `N1_TABLE_NAMESPACE` 声明固定表名全集，`seedSyncedTablesFromNote()` 首次同步前播种基线
- `_note_texts`：`rollback`（R30 说明）+ `conclusion`；空则不写该键

## 7. 风险与规避

| 风险 | 规避 |
|---|---|
| 并发会话回退同一文件 | 幂等脚本 + 契约测试；改前 `grep` 消费方；已存在文件用 `str_replace` |
| 既有项目附注不生效 | 交付说明写清；不做存量回填（本节 seed 行本就会被同步覆盖） |
| `columns` 键序与 UI 列序不一致 → 附注错位 | 契约测试断言 `columns` 顺序与 `variant` 子列序表一致 |
| soe 新增表在既有项目产生"孤儿"错觉 | 新增不是重命名，无需 `_removed_table_keys`；但仍纳入 `N1_TABLE_NAMESPACE` |
| 中文引号进 Vue 模板属性触发 Vite 崩溃 | `【提示：…含"持有待售资产减值准备"】` 只作为 JS 字符串常量/JSON 值，不写进模板属性 |

**Validates: Requirements 5.1**

