# Design Document

## Overview

本设计以源模板为唯一权威，修复存货披露链路四类缺口：上市「按组合计提」比例口径（R1）、上市小节切分与摊销说明（R2）、两版补「确认为存货的数据资源」表（R3）、附注模块存货章节两级表头列结构（R4），并补齐 seed 列元数据到附注渲染的贯通（R5）。

### 权威源与已核对结论

| 目标 | 权威源 |
|------|--------|
| 底稿披露表结构/公式 | `F2-1至F2-14 ...xlsx` → sheet「附注披露信息（上市公司）」「附注披露信息（国企）」 |
| 附注模块表结构/文本 | `基础数据/附注模版/上市报表附注.md`（§存货）、`国企报表附注.md`（§存货） |
| 附注表编号与校验口径 | `backend/data/note_check_preset_formulas.json` → `check_presets_md.F9-*` |
| 分类行取数链 | F2-2 明细汇总表 `A17..A29` → F2-1 审定表 原值 `A36..A48` / 跌价 `A79..A91` / 净值 `A94..A106` |

**已核对无需改动**：两版披露表 (1) 存货分类的行集合、行序、多源合并口径与源模板单元格引用逐行一致；国企 (2) 转回/转销分列、「其中」行不计入合计的口径一致。

**F9-\* 校验预设对本设计的印证**：

- `F9-1 / F9-2 / F9-3a` → ①分类表必须 7 列（账面余额 / 跌价准备 / 账面价值 × 期末 / 期初）
- `F9-5` → ②变动表 `期初 + 计提 + 其他增加 − 转回 − 转销 − 其他减少 = 期末`
- `F9-7 ~ F9-13a` → ⑤数据资源存货表三段式、四列、期末递推、合计列 = 三源之和、「其中」子项之和 ≤ 父项、与①分类表「数据资源」行交叉

## Architecture

```
前端（底稿披露表）
├── composables/useF2DisclosureListed.ts        R1 比例口径 + R2 摊销文本 + R3 数据资源
├── composables/useF2DisclosureSoe.ts           R3 数据资源
├── composables/f2DisclosureSyncPayload.ts      R2/R3 载荷 + ColumnDef.group 两级表头
├── composables/f2DataResourceInventory.ts      新增：数据资源表纯函数模型（两版共用）
├── f2/core/F2TabDisclosureListed.vue           R2 小节切分 + R3 表 UI
└── f2/core/F2TabDisclosureSoe.vue              R3 表 UI

后端
├── app/services/disclosure_engine.py           R5 seed columns/_column_groups 贯通
├── data/note_template_listed.json  §五、9      R4 列结构 + 表名 + text_sections
├── data/note_template_soe.json     §八、10     R4 列结构 + text_sections
└── scripts/fix/fix_note_inventory_structure.py 新增：幂等修订脚本
```

### 关键复用（不新建机制）

两级表头链路平台已具备，本设计只补数据，不改渲染器：

```
ColumnDef.group  ──(后端)──>  _extract_column_groups  ──>  _column_groups
                                                            │
                              ┌─────────────────────────────┴────────────────────┐
                              ▼                                                  ▼
        DisclosureEditor.activeTableColumns                 note_word_exporter._build_two_level_header_rows
        （嵌套 el-table-column 两级表头）                     （fill_multi_header 两行表头）
```

seed 路径缺的一环是 `disclosure_engine._build_table_data` 丢弃了 seed 上的 `columns` / `_column_groups`，R5 补之。

## Components and Interfaces

### R1 — 「按组合计提」比例口径

`useF2DisclosureListed.enrichS3` 现状：

```ts
impairmentPct: safeRatio(r.impairment, impTotal)   // ✗ 占跌价合计比例
```

源模板 `F52 = D52/B52`、`F54 = D54/B54`，即计提比例。改为：

```ts
impairmentPct: safeRatio(r.impairment, r.balance)  // ✓ 计提比例
```

合计行 `s3EndTotal` / `s3PriorTotal`：

| 字段 | 现状 | 目标 | 依据 |
|------|------|------|------|
| `balancePct` | `balance ? 1 : 0` | 不变 | `C54=1` |
| `impairmentPct` | `impairment ? 1 : 0` | `safeRatio(impairment, balance)` | `F54=D54/B54` |

`safeRatio` 已处理分母 0 / 非有限值 → 返回 0，UI `fmtPct(0)` 渲染 `-`，满足 R1.3。函数签名与导出不变。

### R2 — 上市披露表小节切分

```
(3) 按组合计提存货跌价准备                      ← 保留期末表 + 上年年末表
(4) 存货期末余额中含有借款费用资本化金额的说明     ← 独立 disclosure-card
    └ 合同履约成本本期摊销金额的说明              ← 新增文本框（同卡片第二块）
(5) 开发成本 / (6) 开发产品 / (7) 周转房
```

编号沿用源模板：借款费用资本化在 xlsx 为「（4）」（A63）；合同履约成本摊销在附注模版为无编号提示句，故并入 (4) 卡片作为第二个文本块。

新增状态：

| item_id | 字段 | 同步 `_note_texts.section` |
|---------|------|---------------------------|
| `F2-note-listed-note-amort` | `s4AmortText` | `listed-note-amort` |

与国企侧 `s4AmortText` / `soe-note-amort` 同名，便于附注侧统一处理。

### R3 — 数据资源表接口

纯函数导出（遵循「`useXFormulaEngine` 纯函数」约定，便于单测）：

```ts
export function buildDataResourceRows(values: DrValueMap, variant: 'listed' | 'soe'): DrRow[]
export function calcDrTotals(row: DrRawValues): number          // 合计列 = 三源之和
export function calcDrEnding(open: number, inc: number, dec: number): number
export function checkDrSubExcess(parent: number, subs: number[]): boolean
export function isDataResourceEmpty(values: DrValueMap): boolean
```

子项**不自动汇总到父项**：`F9-10` 是「子项之和 ≤ 父项」的**校验**而非公式，父项独立录入；超额时行内黄色告警（复用 `tie-warn`），不阻断保存（R3.4 / R3.9）。

### R5 — seed 列元数据贯通

`_build_table_data` 返回值语义不变，在两处多表装配点（约 1469 行与 2144 行）补透传：

```python
_CARRY_KEYS = ("columns", "_column_groups")

def _carry_seed_column_meta(seed: dict, built: dict) -> None:
    """把 seed 表的列元数据透传到生成的 table_data（缺省不写，零影响）。"""
    for k in _CARRY_KEYS:
        v = seed.get(k)
        if v and k not in built:
            built[k] = v
```

```python
built = await self._build_table_data(...)
if built:
    built["name"] = tbl.get("name", "")
    _carry_seed_column_meta(tbl, built)      # 新增
built_tables.append(built or {...})           # 降级分支同样补
```

不影响 `project_sub_tables`：该路径由 `_source in ('workpaper','workpaper_html')` 门控，seed 生成的附注 `_source` 不在其中，两条路径互斥（Property 7）。

## Data Models

### 数据资源表行模型（`f2DataResourceInventory.ts`）

逐字取自附注模版；`kind` 决定可编辑性与合计参与：

| # | rowKey | label | kind | 公式 |
|---|--------|-------|------|------|
| 1 | `gross-section` | 一、账面原值 | `section` | — |
| 2 | `gross-open` | 1.期初余额 | `input` | — |
| 3 | `gross-inc` | 2.本期增加金额 | `input` | — |
| 4 | `gross-inc-purchase` | 其中：购入 | `sub` | — |
| 5 | `gross-inc-collect` | 采集加工 | `sub` | — |
| 6 | `gross-inc-other` | 其他增加 | `sub` | — |
| 7 | `gross-dec` | 3.本期减少金额 | `input` | — |
| 8 | `gross-dec-sale` | 其中：出售 | `sub` | — |
| 9 | `gross-dec-invalid` | 失效且终止确认 | `sub` | — |
| 10 | `gross-dec-other` | 其他减少 | `sub` | — |
| 11 | `gross-end` | 4.期末余额 | `derived` | `gross-open + gross-inc − gross-dec` |
| 12 | `imp-section` | 二、存货跌价准备 / 二、跌价准备 | `section` | 上市 / 国企 用词不同 |
| 13 | `imp-open` | 1.期初余额 | `input` | — |
| 14 | `imp-inc` | 2.本期增加金额 | `input` | — |
| 15 | `imp-dec` | 3.本期减少金额 | `input` | — |
| 16 | `imp-dec-reversal` | 其中：转回 | `sub` | — |
| 17 | `imp-dec-writeoff` | 转销 | `sub` | — |
| 18 | `imp-end` | 4.期末余额 | `derived` | `imp-open + imp-inc − imp-dec` |
| 19 | `nv-section` | 三、账面价值 | `section` | — |
| 20 | `nv-end` | 1.期末账面价值 | `derived` | `gross-end − imp-end` |
| 21 | `nv-open` | 2.期初账面价值 | `derived` | `gross-open − imp-open` |

列：`purchased` / `selfProcessed` / `other` / `total`（`total` 为 `derived` = 三源之和，对应 `F9-11`）。

### 持久化

单一 item 存 JSON，避免 21×3 个 item：

| variant | item_id |
|---------|---------|
| listed | `F2-note-listed-s8-data-resource` |
| soe | `F2-note-soe-s5-data-resource` |

值形状 `{ [rowKey]: { purchased, selfProcessed, other } }`；`derived` 行与 `total` 列不落库（读时重算），符合「公式列不持久化」惯例。

### 同步载荷：ColumnDef.group 化

`buildF2ListedColumns` / `buildF2SoeColumns` 当前把两级表头压平成 `期末账面余额`。改为使用平台既有 `ColumnDef.group`：

```ts
存货分类: [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_gross',      label: '账面余额',                      group: '期末余额', format: 'amount' },
  { key: 'end_impairment', label: '跌价准备/合同履约成本减值准备', group: '期末余额', format: 'amount' },
  { key: 'end_net',        label: '账面价值',                      group: '期末余额', format: 'amount' },
  { key: 'prior_gross',    label: '账面余额',                      group: '上年年末余额', format: 'amount' },
  // ...
]
```

标签列 label 校准：分类表统一「项目」（上市模版「项 目」/ 国企「项  目」），国企变动表保留「存货种类」。

新增子表键（两版同名）：`确认为存货的数据资源`，列 = 项目 / 外购的数据资源存货 / 自行加工的数据资源存货 / 其他方式取得的数据资源存货 / 合计。

### 附注模板 §五、9（上市）目标结构

| 表名（修订后） | headers（7 列） | `_column_groups` |
|---|---|---|
| 存货分类 | 项目 / 账面余额 / 跌价准备/合同履约成本减值准备 / 账面价值 / 账面余额 / 跌价准备/合同履约成本减值准备 / 账面价值 | `[{期末余额,1,3},{上年年末余额,4,3}]` |
| 存货跌价准备及合同履约成本减值准备 | 项目 / 期初余额 / 计提 / 其他 / 转回或转销 / 其他 / 期末余额 | `[{本期增加,2,2},{本期减少,4,2}]` |
| 存货跌价准备及合同履约成本减值准备（续） | 项目 / 确定可变现净值… / 本期转回或转销…原因 | — |
| 按组合计提存货跌价准备 | 组合 / 金额 / 比例(%) / 金额 / 计提标准 / 比例(%) / 账面价值 | `[{账面余额,1,2},{存货跌价准备,3,3}]` |
| 按组合计提存货跌价准备（续） | 同上 | 同上 |
| 按库龄组合计提存货跌价准备 | 同上 | 同上 |
| 按库龄组合计提存货跌价准备（续） | 同上 | 同上 |
| 确认为存货的数据资源 | 不变（5 列） | — |
| 开发成本 | 项目名称 / 开工时间 / 预计竣工时间 / 预计总投资 / 期末数 / 上年年末数 / 期末跌价准备 | — |
| 开发产品 / 周转房 | 不变 | — |

- 原「续：」×2 → `按组合计提存货跌价准备（续）`、`按库龄组合计提存货跌价准备（续）`；原长句表名（「本公司对于在同一地区…」）→ `按库龄组合计提存货跌价准备`，长句本身已在 `text_sections` 中，不丢失。
- 开发成本表头 `期末余额/上年年末余额` → `期末数/上年年末数`，与源 xlsx 及同步 `columns` 一致。
- 删除全部 `row_type: header_label` 行；按组合计提 4 表补 3 行空 `data` 行（模板即 3 空行），库龄版保留 `1年以内` / `1至2年` + 1 空行。

### 附注模板 §八、10（国企）目标结构

| 表名 | headers | `_column_groups` |
|---|---|---|
| 存货分类 | 项目 / 账面余额 / 跌价准备/合同履约成本减值准备 / 账面价值 / ×3 | `[{期末数,1,3},{期初数,4,3}]` |
| 存货跌价准备及合同履约成本减值准备 | 存货种类 / 期初数 / 计提 / 其他 / 转回 / 转销 / 其他 / 期末数（8 列） | `[{本期增加,2,2},{本期减少,4,3}]` |
| 确认为存货的数据资源 | 不变 | — |

`text_sections` 追加国企模版中缺失的数据资源提示段与「【提示：上述信息，若已在会计政策、其他项目附注中披露，可索引至相关内容。】」。

### 行不动原则

附注模块的**行集合以附注模版为准**（上市 7 类、国企 11 行含 2 个「其中」），**不引入**底稿披露表多出的「委托加工物资」「发出商品」——附注模版无此两行。同步时 `sub_table_data` 整表覆盖行，seed 行仅为初始骨架，不影响同步结果。仅列结构按模板修复。

## Correctness Properties

### Property 1: 计提比例口径

**Validates: Requirements 1.1, 1.2, 1.3, 1.5**

对任意组合行，`impairmentPct == impairment / balance`；`balance == 0` 时 `impairmentPct == 0`（不产生 `NaN` / `Infinity`）。合计行同式，分母取合计账面余额。源模板 `F52=D52/B52` / `F54=D54/B54`。验证：单测 + PBT。

### Property 2: 占比口径零回归

**Validates: Requirements 1.4**

`balancePct == balance / balanceTotal`，合计行恒为 `1`（源模板 `C54=1`）。本次改动不得触碰该口径。验证：单测。

### Property 3: 数据资源表合计列

**Validates: Requirements 3.3**

对任意行，`total == purchased + selfProcessed + other`。对应 `check_presets_md.F9-11`。验证：单测。

### Property 4: 数据资源表期末递推

**Validates: Requirements 3.5**

逐列成立：`gross-end == gross-open + gross-inc − gross-dec`，`imp-end == imp-open + imp-inc − imp-dec`。对应 `F9-7` / `F9-8`。验证：单测。

### Property 5: 数据资源表账面价值

**Validates: Requirements 3.6**

逐列成立：`nv-end == gross-end − imp-end`，`nv-open == gross-open − imp-open`。对应 `F9-9` / `F9-9a`。验证：单测。

### Property 6: 附注表列宽自洽

**Validates: Requirements 4.7**

修订后每张表满足 `len(headers) - 1 == len(row.values)`（对所有行）。验证：结构守卫测试。

### Property 7: `_column_groups` 区间合法

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

各分组区间互不重叠，且 `start >= 1`、`start + span <= len(headers)`。验证：结构守卫测试。

### Property 8: 修订脚本幂等

**Validates: Requirements 4.10**

连续执行两次后，目标 section 的表数量、表名集合、`text_sections` 长度均不变。验证：结构守卫测试。

### Property 9: seed 透传缺省无副作用

**Validates: Requirements 5.2**

seed 表未声明 `columns` / `_column_groups`（或声明为空/非法类型）时，`_carry_seed_column_meta` 不向 `built` 写入任何键。验证：后端单测。

### Property 10: workpaper 投影路径不受影响

**Validates: Requirements 5.3**

`_source in ('workpaper', 'workpaper_html')` 的附注，其 `_tables` 仍由 `project_sub_tables` 产出，R5 改动不参与。验证：后端单测。

## Error Handling

| 场景 | 处理 |
|------|------|
| 组合账面余额为 0 | `safeRatio` 返 0 → UI `-`，不抛错 |
| 数据资源表 JSON 解析失败 | `safeParseJson` 回退空对象，表渲染为全 0 |
| 「其中」子项之和 > 父项 | 行内黄色告警文字，不阻断保存、不阻断同步 |
| 分类表「数据资源」为 0 且明细表全空 | `el-alert type="info"` 提示可不填，不隐藏表 |
| 修订脚本目标 section 缺失 | 打印 warning 并以非零退出码结束，不写文件 |
| 修订脚本表名旧名与新名同时存在 | 跳过迁移，保留新名表，warning 提示人工确认 |
| seed 透传遇到非法类型（非 list/dict） | 视为缺省不写，避免污染 `table_data` |

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 前端单测 | `__tests__/useF2DisclosureListed.spec.ts` | R1 全部 5 条；R2 `s4AmortText` 持久化 |
| 前端单测 | `__tests__/f2DataResourceInventory.spec.ts`（新） | P3~P5 + 空态 + 子项超额 |
| 前端单测 | `__tests__/useF2DisclosureSoe.spec.ts` | R3 国企侧行标题「二、跌价准备」 |
| 前端契约 | `__tests__/disclosureSyncUrlContract.spec.ts` | 既有，回归 |
| 后端单测 | `tests/services/test_note_sub_table_projector.py` | 既有 `_extract_column_groups`，回归 |
| 后端单测 | `tests/services/test_disclosure_engine_seed_column_meta.py`（新） | P9 / P10 |
| 后端数据 | `tests/services/test_note_inventory_structure.py`（新） | P6 / P7 / P8 + 无 `header_label` + 表名唯一 |
| 数据校验 | `backend/scripts/validate_note_docx_placeholders.py`（原 `validate_note_template.py`） | R6.4 —— 注：只校 docx 占位符，非 JSON 守卫 |
| 数据校验 | `backend/scripts/fix/fix_note_inventory_structure.py --check` | R12.1 —— JSON 结构真守卫（已挂 CI） |
| 实测 | Playwright | R6.5：两个披露 Tab + 附注存货章节两级表头与 TAB 页签 |
| 实测 | Word 导出 | R5.4：存货章节两行表头 |

## 不做

- 不给附注模块存货分类表加「委托加工物资」「发出商品」行（附注模版无，见「行不动原则」）
- 不改 `note_check_preset_formulas.json`（F9-\* 已与目标结构一致）
- 不动 `note_template_bindings.json`（本次不涉及公式取数绑定）
- 不改其它章节的 `header_label` 行（超出本 spec 范围；R5 的贯通已为后续同类修复铺路）

---

## Sprint 7 设计：源 xlsx 裁决 + 库龄二选一

### 裁决顺序修订

原设计的三源裁决（源 xlsx / 附注模版 md / 校验预设）中，**附注模版 md 在本仓库不存在**，
故本轮裁决顺序收敛为：**源 xlsx（`backend/wp_templates/` 运行时权威）> 校验预设
`note_check_preset_formulas.json` > 现状模板 JSON**。凡 xlsx 可实证的行/列，一律以 xlsx 为准。

xlsx 之外的两组表（「按库龄组合计提」×2、「确认为存货的数据资源」）保留：前者源自
15 号文第十六条（十二），后者源自《企业数据资源相关会计处理暂行规定》，均非 xlsx 披露 sheet
覆盖范围，但属交付物必需，不删。

### R18/R19 落点：扩展既有幂等脚本

`fix_note_inventory_structure.py` 已有 `rows` 模式机制（`strip` / `portfolio_blank` /
`portfolio_aging` / `keep`）。新增两个模式，行集常量单一真源：

- `LISTED_CATEGORY_LABELS`（9 项）→ 模式 `listed_categories`（分类/变动）与
  `listed_categories_qual`（续表，合计行不带金额）
- `SOE_CATEGORY_ROWS`（13 项，含 `kind=detail` 的「其中：」行）→ 模式 `soe_categories`

`rows` 模式从 `strip`（保留既有行、只删 header_label）改为显式行集重建 —— 因为 seed 行是
骨架而非用户数据（用户数据一律经 `sub_table_data` 整表覆盖），重建无数据丢失风险。

`_classification()` 增 `label_header` 形参：上市传「存货种类」，国企传「项目」。
`LISTED_MOVEMENT` / 上市续表的 `headers[0]` / `columns[0].label` 同步改「存货种类」。

守卫 `validate_section` 已有「headers[k] == columns[k].label」逐位断言，改错会立刻红。

### R20 落点：`buildNoteTexts` 化

`f2DisclosureSyncPayload.ts` 内联的 `_note_texts` 字面量数组改为经
`buildF2NoteTexts(entries)`：入参 `[section, title, text]` 三元组，过滤空文本，
输出 `{section, title, text}`。与 D1/D2 的 `buildXNoteTexts` 同形。

`F2SoeSyncSnapshot` 增 `landNote: string`；`useF2DisclosureSoe.getSyncSnapshot` 补该字段
（`landNote` ref 已存在，只是没进快照）。

### R21 落点：计提方式开关

- `useF2DisclosureListed` 增持久化项 `F2-note-listed-s3-mode`（`'portfolio' | 'aging'`，
  默认 `'portfolio'`），暴露 `s3Mode` + `setS3Mode`。
- 表数据复用既有 `s3EndRaw` / `s3PriorRaw`（同一列结构），**不再开第二套 state** ——
  源模板两表列结构完全相同，仅表名与行标签语义不同（组合名 vs 库龄段），
  且二选一互斥，共用一套 state 即可，避免双真源。
- 切到 `aging` 时若行为空，`groupName` 预填库龄段（`1年以内` / `1至2年`）作为骨架提示。
- `buildF2ListedSubTableData(snap)` 按 `snap.s3Mode` 决定推送表名，并写
  `_removed_table_keys` = 未选中的那一组两个表名（`sync_from_workpaper` 的
  `_drop_removed_tables` 会跳过本次推送键，故不会误删）。

### R22 落点：`retitle_text_sections`

新增幂等 helper：`{plain: '### plain'}` 映射，仅当 `plain` 精确存在且
`'### ' + plain` 不存在时替换。`SOE_TEXT_ANCHOR` 随之改为 `### 确认为存货的数据资源`，
并对旧锚点做兼容查找（先找新锚点，未命中再找旧锚点）。

---

## Sprint 8 设计：分类表取数补全

### R23/R24：上市分类常量重排

`F2_LISTED_DISCLOSURE_CATEGORIES` 9 → 11 行，顺序与 `sourceKeys`：

| # | rowKey | label | sourceKeys |
|---|---|---|---|
| 1 | `raw-materials` | 原材料 | raw-materials, material-in-transit |
| 2 | `work-in-progress` | 在产品 | **semi-finished**（删死键 `work-in-progress`） |
| 3 | `dev-costs` | **开发成本**（新增） | dev-costs |
| 4 | `outsourced-processing` | 委托加工物资 | outsourced-processing |
| 5 | `finished-goods` | 库存商品 | finished-goods, **price-difference** |
| 6 | `dev-products` | **开发产品**（新增） | dev-products |
| 7 | `goods-in-transit` | 发出商品 | goods-in-transit |
| 8 | `revolving-materials` | 周转材料 | revolving-materials |
| 9 | `contract-performance` | 合同履约成本 | contract-performance |
| 10 | `consumable-bio` | 消耗性生物资产 | consumable-bio |
| 11 | `data-resources` | 数据资源 | （无科目 → R25 联动） |

`rowKey` 保留 `work-in-progress` 作**行标识**（持久化键，改了会丢既有 `s2Overrides` /
`s2QualMap` 数据），只把它从 `sourceKeys` 里删掉 —— 行标识与取数键是两回事。

国企侧 `wip-combined` 同样从 `sourceKeys` 删 `work-in-progress`（保留 semi-finished、dev-costs）。

守卫：新增 Property「`sourceKeys` 并集 ⊇ 审定表全部非跌价 rowKey」，
两版各一条，直接从 `f2AccountModel.F2_ROW_KEY_ACCOUNT` 取全集，防再漏科目。

### R25：数据资源行联动

`f2DataResourceInventory.ts` 已有 `calcDrTotals`（按行的 4 列合计）。新增纯函数：

```ts
export function deriveDataResourceClassRow(values: DrValueMap, variant: F2DrVariant)
  : { endGross; endImpairment; priorGross; priorImpairment }
```

取 `gross-end` / `gross-open` / `imp-end` / `imp-open` 四行的 `total`（= 外购 + 自行加工 +
其他方式）。`gross-end` / `imp-end` 是派生行（`calcDrEnding`），已有算法复用。

两个 composable 的 `loadClassRow` 对 `rowKey === 'data-resources'` 走该分支：
- 数据资源表为空（`isDataResourceEmpty`）→ 仍返回 0（不制造凭空数字）
- 非空 → 返回联动值

`buildDataResourceTieChecks` 的入参不变（仍传分类表该行），联动后差额恒 0，
面板从"告警"变为恒通过；`drTieFailures` 自然为空。

### R26：国企「其他」「土地储备」手工录入

复用 `s2Overrides` 范式，新增独立持久化项 `F2-note-soe-s1-overrides`：

```ts
type S1Override = Partial<Record<
  'endGross'|'endImpairment'|'priorGross'|'priorImpairment', number>>
Record<rowKey, S1Override>   // 仅 'other' | 'land-reserve' 两个键被接受
```

`endNet` / `priorNet` 仍由 `calcNetValue` 派生（不可直接录入，避免与余额-准备不自洽）。
`updateS1Field(rowKey, field, value)` 白名单校验 rowKey，非白名单直接 return
（防误开放跨表取数行的手工覆盖，破坏 F2-1 权威性）。

UI：国企 (1) 表的六个金额列对这两行渲染 `WpAmountInput`，其余行保持只读跨表取数样式。

### 连带改动清单

1. `f2DisclosureSyncPayload.ts`：无需改结构（行由快照 map 而来，行数自动跟随）
2. `fix_note_inventory_structure.py`：`LISTED_CATEGORY_LABELS` 9 → 11 项（同序）
3. 后端 `_f2_disclosure_import_export.py`：`_LISTED_CATEGORIES` / `LISTED_CATEGORIES`
   两处镜像常量同步（正则契约测试会强制两侧一致）
4. 测试：`test_note_inventory_structure`（行集参数化 + `.ts` 常量逐字比对）、
   `useF2DisclosureListed.spec`、`f2NoteSectionMap.spec`、`f2NoteSubtableContract`、
   `f2DataResourceInventory.spec`、后端 `test_f2_disclosure_import_export`
