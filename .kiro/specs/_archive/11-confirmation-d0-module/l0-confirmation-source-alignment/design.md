# Design Document

## Overview

L0 债务循环函证的源模板保真度修复。设计的核心判断是：**L0 的缺口不在共享组件，而在 L0 专属侧**。

逐 sheet 精读后核实，L0-2（核实被函证单位信息三区）/ L0-3（跟函过程控制三个控制核对点 + 工号 + 签名）/ L0-5（抽样参数 6 项 + 四区块 + 期初一致性 + 说明结论）/ L0-6（回函可靠性列集 + 注1~注3）/ L0-7（19 条舞弊迹象 + B50 推送）**已由 `e0/g0/h0/k0` 系列 spec 在共享组件里收口**，L0 无需改动即受益。真实缺口只有五处，全部落在 L0 专属或平台分发层：

| 缺口 | 层 | 实证 |
|---|---|---|
| 程序表加载错循环 | 后端数据 | `get_template('L0A')` 返回 None → `resolve_program_template_code` 兜底失败 → 回退 `F0A` → 加载「采购存货循环函证程序表」12 条，`ref_index` 全为 `F0-*` |
| 公式预设整块错 | 后端数据 | `sheet='审定表L0-1'`（源 xlsx 无此 tab）+ `account_codes=['2001','2501']`（短期借款/长期借款）+ 病态区间 `TB_SUM('2001~2501')`，而源模板 L0A 程序 1 明确排除银行借款 |
| L0-1 下区四块缺失 | 前端 | `GtConfirmationSummary.vue` 只有 `isE0`/`isF0`/`isG0`/`isH0` 分支，无 `isL0` |
| 列集偏离源模板 | 前端 | 伪列 `send_memo` + `row_conclusion` group 错 + 三列空列噪声 + 缺渠道列 + 13 处 label 分叉 |
| 隐藏 sheet 渲染成页签 | 平台分发 | `函证差异检查表（示例）` 在 L0 为 hidden，但 override 映射为 `confirmation-diff-checklist` |

### 三个关键设计判断

**判断 1：账面金额取数复用 `l_cycle_specs.py`，不新建科目定位。**
`L5_SPEC`（长期应付款 `BS-064` / 兜底 `2701`）与 `L4_SPEC`（应付债券 `BS-062` / 兜底 `2502`）已存在且经 DB 对账。L0-1 的两个品种恰好一一对应。新写一份等于制造双真源，且要重复踩「一码两义」「client chart 优先」那些坑。

**判断 2：矩阵与下区各自实现，不重构 E0/F0/G0/H0 的四份副本。**
沿用已生效的裁决 D-2（各自实现后另立收敛 spec）。对冲手段两条：① 模块头导出 `CONVERGENCE_TARGET`（矩阵 `confirmation-summary-matrix-convergence` / 下区 `confirmation-summary-lower-zone-convergence`），收敛 spec 直接 grep 即得全量清单；② 同源性守卫断言 `buildL0SummaryMatrix` 与 `buildF0SummaryMatrix` 对同一输入的 8 指标 `label`/`kind`/`editable`/`value` 逐字节相同，使副本在收敛前不会各自漂移。

**判断 3：隐藏 sheet 处置必须用复合键，不能用裸 sheet 名。**
`函证差异检查表（示例）` 在 D0/F0 是 **visible**、仅 L0 是 hidden（三处模板 openpyxl 实证）。按裸名标 `skip` 会同时杀掉 D0/F0 的真实页签。而现有 skip 判定三条路（全名精确 / 尾码 / 前缀码）都不带 wp_code 维度 → 必须在 `wp_render_config.py` 加一条 `{wp_code}-{sheet_name}` 复合键判定，接在三条之后（既有命中路径优先，行为逐字节不变）。componentType 判定侧早已有同形复合键 fallback，此改动是把 skip 侧补齐到同一水平。

## Architecture

```
┌─ 后端数据层（Wave 1，零碰共享件）────────────────────────────────────┐
│ backend/data/procedure_table_templates.json                          │
│   └─ tables.L0A ← 新增 12 items（description/category/ref_index/hint）│
│ backend/data/prefill_formula_mapping.json                            │
│   └─ L0 块 ← sheet/account_codes/cells 纠正                          │
│ backend/scripts/fix/fix_l0_prefill_presets.py（幂等 + round-trip 自检）│
│ backend/scripts/fix/fix_l0a_program_template.py（幂等）               │
└──────────────────────────────────────────────────────────────────────┘
                              │ get_template('L0A') 命中
                              ▼
┌─ 后端 render（Wave 2，加法式注入）──────────────────────────────────┐
│ backend/app/services/four_table/l0_book_amounts.py                   │
│   └─ 复用 l_cycle_specs.L5_SPEC / L4_SPEC + semantic_account_resolver │
│      + resolve_leaf_totals（负债类整族统一取向）                     │
│ backend/app/routers/wp_render_config_helpers.py                       │
│   └─ _inject_l0_book_amounts（wp_code 前缀门控，早于取数）            │
└──────────────────────────────────────────────────────────────────────┘
                              │ html_data.project_context.l0_book_amounts
                              ▼
┌─ 前端 L0 专属声明（Wave 2，零碰共享件）─────────────────────────────┐
│ confirmation/l0-confirmation/                                        │
│   l0SummaryMatrix.ts      2 品种 × 8 指标 + CONVERGENCE_TARGET        │
│   l0MatrixDataSources.ts  账面金额取数 + 手工覆盖键（指标 key 构键）  │
│   l0SummaryLowerZone.ts   四块文字真源（6 样本项 + 5 说明段 + 结论）  │
│   L0SummaryLowerZone.vue  下区渲染组件                               │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ 共享件接入（Wave 3，与 K0 spec 同一次刀）──────────────────────────┐
│ confirmationColumnSpec.ts       只增 L0 键（撤伪列/剔三列/渠道/label）│
│ GtConfirmationSummary.vue       isL0 门控 + 挂 L0SummaryLowerZone     │
│ ConfirmationSampling.vue        isL0 门控（6 项，与 G0 同构）         │
│ coordination/cycleConfirmationMeta.ts  三处笔误登记                  │
│ coordination/alternativeBlockManifest.ts  L05 三处 title 对齐         │
│ alternativeL05/GtConfirmationAlternativeL05.vue  同上                │
│ backend/app/routers/wp_render_config.py  复合键 skip 判定             │
└──────────────────────────────────────────────────────────────────────┘
```

### 波次隔离依据

Wave 1/2 的产物全是 L0 专属新文件或 L0 专属数据块 → 与并发的 K0/F0 spec 零交集，可立即推进。Wave 3 的七个文件全是七枢纽共享件，其中 `GtConfirmationSummary.vue` 与 K0 spec 的 Task 10 是同一处刀口 → 必须协调为一次编辑，且遵守 K0 spec 的 R11.5（F0 spec 仍有 `[-]`/`[~]` 期间不开工）。

## Components and Interfaces

### 1. `backend/data/procedure_table_templates.json` — `tables.L0A` 新增

**为什么往 `tables` 加而不是修 `get_template` 去读根级**：`get_template` 只读 `tables` 是运行时唯一入口，改它会让根级那 57 条与 `tables` 分叉的重复条目一起复活（memory 已登记为平台级议题）。本 spec 只解 L0 一条，往 `tables` 增补是最小半径。

根级既有 `L0A`（10 items，名「筹资循环函证实质性程序表」）**不是源模板忠实版本**（源模板 12 条）→ 新增条目按源模板 `函证程序表F0A!A7:G18` 重建，根级那条留待平台级收敛 spec 处置。

**字段名以 `tables` 既有形态为准（实证 `tables.F0A`）**：`{seq, content, ref_index, auto_data_source, applicable_default}`，其中 `content` 是 `procedure_table_auto_service` 的**必填**读取（`item["content"]` 而非 `.get`），写成 `description` 会 KeyError。另加 `program_category`（该服务读 `item.get("category") or item.get("program_category")`）。

```jsonc
"L0A": {
  "name": "长期应付款/应付债券函证程序",   // 源 A2 逐字
  "items": [
    { "seq": 1,
      "content": "以积极方式对长期应付款、应付债券进行函证。\n【提示】本函证不包含银行长期借款、银行短期借款函证，与银行借款相关函证详见货币资金循环",
      "program_category": "常规★",
      "ref_index": "L0-1",
      "auto_data_source": "confirmation_summary_for_cycle",
      "applicable_default": "yes" },
    // ... 共 12 条，program_category 取自 D7:D18，ref_index 取自 E7:E18
  ]
}
```

**🔴 源模板 G 列批注承载在 `content` 末尾的 `\n【提示】…` 段，不新增 `hint` 字段** —— `ProcedureTableService.get_procedure_table` 的 item 输出字段恒为 `{_key, seq, content, ref_index, phase, category, **merged}`，**没有 `hint` 透传通道**，新增字段会被静默丢弃（又一个 dead config）。两条批注（seq 1 银行借款排除声明、seq 8 第三方平台技术提示3号链接）都走这条路，守卫按「`content` 含该原文」断言。

`program_category` 而非 `applicable_default` —— 后者写 `"no"` 是死配置（`_check_applicable` 只把 `"na"` 映射成 `not_applicable`），真正驱动程序裁剪的是 `program_category`，`GtAProgramConsole.vue` 早有「类别」列 + 类别筛选 + 批量裁剪。`applicable_default` 统一写 `"yes"`（与 `tables.F0A` 同形）。

### 2. `backend/app/services/four_table/l0_book_amounts.py`

```python
L0_CATEGORY_SPECS: tuple[tuple[str, str, SemanticAccountSpec], ...] = (
    ("long_term_payable", "长期应付款", L5_SPEC),
    ("bonds_payable",     "应付债券",   L4_SPEC),
)

async def fetch_l0_book_amounts(db, project_id, year, standards) -> dict[str, dict]:
    """返回 {category_key: {"label", "amount"|None, "resolved_from", "codes", "found"}}"""
```

三条口径约束：
- **负债类整族统一取向** —— 走 `resolve_leaf_totals(rows, prefix, absolute=True)`（取与父额勾稽成立的那一种符号约定），不逐行 `abs()`
- **🔴 `2702 未确认融资费用` 是独立一级科目，不是 `2701` 的子科目** —— DB 实证 `account_chart` 里 `2701` 的子科目只有 `.01 应付融资租赁款` / `.02 应付长期保证金` / `.03 应付长期借款` / `.99 一年内到期的长期应付款`，未确认融资费用挂在独立码 `2702`（含 1 个项目 client 侧名为「长期应付款未确认融资费用」但码仍是 2702）⇒ `LIKE '2701%'` **扫不到它**，「父族聚合已净掉」的说法不成立。且 `BS-064 = TB('2701','期末余额')` 本身**不减** 2702（与 H9 租赁负债 `BS-063 = TB('2601')-TB('2602')` 减未确认融资费用的口径**不同**，属 `report_config` 既有口径差异，不在本 spec 半径）。→ **实现按 `BS-064` 口径不减 2702**，`net_of_slots` 为空；溯源 `formula_hint` 与 `notes` 如实标注该口径
- **`2701.99 一年内到期的长期应付款`** 会计上应重分类到 `BS-052`，但 `BS-064 = TB('2701')` 会把它计入长期应付款 —— 属 `report_config` 既有重分类派生行议题（同 memory 已记的 `BS-052 2501`），溯源里如实提示，不在本 spec 修正
- **`found=False` 时 `amount` 返 `None` 不返 `0`** —— 「本项目无此科目」与「余额为 0」必须可区分（R3.4）

### 3. `_inject_l0_book_amounts`（`wp_render_config_helpers.py`）

加法式注入，仿 `_inject_h0_book_amounts`。**不注册 `RENDERER_DISPATCH`** —— `confirmation-summary` 是七枢纽共享 componentType，注册即让另六个枢纽载荷改道。

```python
async def _inject_l0_book_amounts(ctx, sheet_html_data) -> None:
    if not str(ctx.wp_code or "").upper().startswith("L0"):   # 门控早于取数
        return
    if not isinstance(sheet_html_data, dict):
        return
    ...
    sheet_html_data.setdefault("project_context", {})["l0_book_amounts"] = payload
```

「注入整体失败」与「本项目无此科目」必须可区分：前者键不存在，后者键存在值为 `null`。前端**不得写 `?? {}` 兜底**（会把前者变成后者，全部品种显示「本项目无此科目」）。

### 4. `confirmation/l0-confirmation/l0SummaryMatrix.ts`

```ts
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'

// 🔴 key 逐字沿用 G0/`g0SummaryMatrix.ts` 的命名 —— 收敛 spec 合并副本时无需再改名，
//    同源守卫（Property 9）也能直接按 key 对齐比对。
export type L0MetricKey =
  | 'book_amount' | 'send_amount' | 'send_ratio' | 'reply_confirmed'
  | 'reply_over_send' | 'reply_over_book'
  | 'alt_confirmed' | 'reply_alt_over_book'

export interface L0MatrixCell {
  metric: L0MetricKey          // 稳定 key（不是中文 label）
  label: string                // 源模板 C30:C37 字面
  kind: 'amount' | 'ratio'
  editable: boolean            // 仅 book_amount 可手工覆盖
  value: number | null
}

export function buildL0SummaryMatrix(input: {
  rows: ConfirmationRow[]
  bookAmounts?: Record<string, number | null>
  manualOverrides?: Record<string, number>
}): L0MatrixCell[][]
```

**8 指标与 F0/G0 逐条同构**（源模板 `E31/E32/.../E37` 公式与 F0-1 同形）→ 守卫做同源性断言。**`metric` 是 key + `label` 独立字段** —— F0 侧的 `F0MatrixCell.metric` 直接存中文 label（label-as-key 形态），收敛时以 L0/G0 形态为目标；守卫另加一条「F0 仍是 label-as-key」断言，一旦 F0 改形即打红提醒收敛可推进。

### 5. `l0MatrixDataSources.ts`

```ts
export function matrixOverrideItemId(categoryKey: string, metric: L0MetricKey): string {
  return `L0-1-matrix-${categoryKey}-${metric}`     // 指标 key 构键，非中文 label
}
export async function loadL0MatrixSources(projectId: string, wpId: string): Promise<L0MatrixSources>
```

取数全程 `_silent: true`，但 **`diagnostics.errors` 必须有渲染出口**（F0 那轮的教训：只收集不渲染，让「链路失效」与「本项目确实没这科目」不可区分）。

跨底稿取数一律 `import { api } from '@/services/apiProxy'`（返回业务数据本身），**不得**用 `@/utils/http` 的 default export（返回 AxiosResponse，按 apiProxy 语义读会恒 undefined）。并行请求不得对同一 URL 发多次（GET 去重会 abort 先发者）。

### 6. `l0SummaryLowerZone.ts` + `L0SummaryLowerZone.vue`

```ts
export const CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'
export const L0_LOWER_KEY_PREFIX = 'L0-1-lower'

export const L0_SAMPLE_SELECTION_DEFS: readonly LowerZoneTextDef[]  // 6 项，源 J29~J35
export const L0_AUDIT_NOTE_DEFS: readonly LowerZoneTextDef[]        // 5 段，源 S29/W29/S33/S34/S36
export const L0_SECTION_TITLES: Readonly<Record<string, string>>    // 含笔误更正
export const L0_REFERENCE_CONCLUSIONS: readonly string[]            // 源 A65:B68 三条，只读
```

**三处「一句话被源模板拆成两格」必须合并渲染**（否则界面出现半句话）：
- `W30` + `W31` = 误差界定条件（「界定误差构成条件：［不符事项的金额高于或低于账户余额人民币」+「（）万元，并且被审计单位不能合理解释其差异并提供相应依据］」）
- `S34` + `S35` = 针对不符事项的程序（`S35` 是其补充说明）
- `K35` + `K36` = 抽样过程（「使用IDEA（XX抽样工具）选取样本进行函证，长期应付款选择XX个供应商、金额XX的样本，」+「抽样工具中的样本选择过程和结果见<XX>底稿」，前者以逗号结尾即续行标志）

另 `K33`（「如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿」）是 `J32 确定的抽样样本量` 的括注，作提示文本不作独立录入项。

**`S33` 的索引号「（L0-6）」是正确的**，不在三处笔误之列 —— 判索引号对错一律回查底稿目录 `F4:F11`。

「三、审计说明」的序号：源 `S28` 字面是「二、审计说明」，而 `C28`=「一、」/ `J28`=「二、」/ `C39`=「四、」→ 判定为源模板序号笔误，展示「三、审计说明」+ tooltip 标注。

### 7. 共享件改动（Wave 3）

| 文件 | 改动 | 零回归判据 |
|---|---|---|
| `confirmationColumnSpec.ts` | `CYCLE_VARIANT_COLUMNS.L0` = `['send_channel','l0_row_conclusion']`（撤 `send_memo`、`row_conclusion` 换注册 key）；`CYCLE_EXCLUDED_COLUMNS.L0` = 三列；新增 `CYCLE_COLUMN_LABEL_OVERRIDES.L0` | 只增/改 L0 键 → 另六枢纽 resolve 输出逐字节不变 |
| `GtConfirmationSummary.vue` | `isL0` computed + `<L0SummaryLowerZone v-if="isL0">` | `v-if` 门控 → 另六枢纽模板逐字节不变 |
| `ConfirmationSampling.vue` | `isL0` 门控（6 项，与 `isG0` 同构） | 同上 |
| `cycleConfirmationMeta.ts` | L0 三处 `indexTypoNote` 登记 | `*Code` 字段一个不删 |
| `alternativeBlockManifest.ts` + `GtConfirmationAlternativeL05.vue` | L05 三处 title 对齐源模板 | 不改 `block` key / 列 key / `SUM_FIELDS` |
| `wp_render_config.py` | 复合键 skip 判定 | 接在既有三条之后，既有命中路径优先 |

**`l0_row_conclusion` 另立注册 key 的理由**：列 `key` 仍是 `row_conclusion`（与 `COMMON_KEYS` 同字段 → `resolve ⊆ manifest` 恒成立，且与 K0/H0/G0 共享同一持久化字段），但 `group` 必须是 `row_summary`、`source` 必须如实指向 `L0-1·AB列`。复用 `h0_row_conclusion` 会让溯源标注串枢纽（与 `g0_row_conclusion` 同理）。

**`send_memo` 撤列后既有值只读呈现**：撤的是渲染，不是字段。若该项目 `send_memo` 有历史值，在行详情面板以只读文本 + 「源模板此处为段头，本值为历史录入」提示呈现（R4.2 数据零丢失红线）。

## Data Models

### `l0_book_amounts` 载荷（后端 → 前端）

```jsonc
// html_data.project_context.l0_book_amounts
{
  "long_term_payable": {
    "label": "长期应付款",
    "amount": 12345678.90,          // null = 本项目无此科目（≠ 0）
    "found": true,
    "resolved_from": "account_chart_client",
    "codes": ["2701"],
    "row_code": "BS-064",
    "net_of_skipped": ["2702"],     // 已在父族聚合内净掉、未二次减的备抵子族
    "parent_check": { "diff": 0.0 }
  },
  "bonds_payable": { "label": "应付债券", "amount": null, "found": false, ... }
}
```

### 下区持久化键（`checklist_responses`）

| 键 | 承载 |
|---|---|
| `L0-1-matrix-{categoryKey}-book_amount` | 账面金额手工覆盖（仅此一个指标可覆盖） |
| `L0-1-lower-sample-{n}`（n=1..6） | 二、样本选择 6 项 |
| `L0-1-lower-audit-note-{n}`（n=1..5） | 三、审计说明 5 段 |
| `L0-1-lower-conclusion` | 四、审计结论 |

上区 grid 载荷落 `parsed_data.html_data['函证结果汇总表L0-1']`，与下区键空间互不重叠（R3.10）。

**下区录入一律直接 `PUT /api/workpapers/{id}/checklist-responses`**，不得 `emit('save', {itemId, value})` —— 宿主 save 处理器会把载荷整体写成该 sheet 的 `html_data`，一次点击就把上区函证行全丢并让 sheet 退化成「旧格式只读」。

### `procedure_table_templates.json` 的 `L0A` item

```jsonc
{ "seq": 1, "description": "…", "program_category": "常规★", "ref_index": "L0-1", "hint": "…" }
```

`category` / `program_category` 两个字段名 `_a_program.py` 都认（`it.get("category") or it.get("program_category")`），统一写后者与平台既有 `D4-22A` 的 18 个 item 一致。

## Correctness Properties

### Property 1: L0A 模板运行时可解析且内容忠于源模板

`get_template('L0A')` 返回非 None，`items` 长度恰 12，每条 `content` 以源 xlsx `函证程序表F0A!B{7+i}` 原文开头，`program_category` 与 `D{7+i}` 相等，`ref_index` 与 `E{7+i}` 相等（源为空则为 `null`/`""`）。字段名与 `tables` 既有形态一致（`content` 必填，无 `description`/`hint`）。

**Validates: Requirements 1.1, 1.3, 1.4, 1.5, 1.9**

### Property 2: 程序表编码解析落到 L0A

`resolve_program_template_code('函证程序表F0A', 'L0') == 'L0A'`。反向自检：删除 `tables.L0A` 后该函数返回 `'F0A'`（复现修复前行为），证明断言非空转。

**Validates: Requirements 1.2**

### Property 3: L0A 新增不污染既有程序表

`tables` 的键集在改动前后满足「改后 = 改前 ∪ {L0A}」；`F0A` / `E0A` / `D0A` / `G0A` / `H0A` / `K0A` 六条的序列化结果逐字节相等。

**Validates: Requirements 1.7, 1.8, 10.3**

### Property 4: 银行借款排除声明可见

`L0A` 的 seq=1 item 的 `content` 含源模板 `G7` 原文（银行借款排除声明），seq=8 的 `content` 含 `G14` 原文；两处以 `\n【提示】` 分隔。全部 item 中出现「银行」二字的位置仅在排除声明处。反向断言：L0 公式预设的 `account_codes` 与全部 `formula` 中不得出现 `2001` / `2501`。

**Validates: Requirements 1.6, 2.2, 2.3**

### Property 5: 公式预设指向正确科目与真实 tab

L0 预设块满足：`sheet == '函证结果汇总表L0-1'` 且该字面存在于源 xlsx `wb.sheetnames`；`account_codes` 含 `2701` 与 `2502` 且不含 `2001`/`2501`；全部 `formula` 不含 `SUM_TB` / `TB_SUM` / `TB(`；两个 cell 的 `cell_ref` 恰为 `L0-1-matrix-长期应付款-book_amount` 与 `L0-1-matrix-应付债券-book_amount`，`formula_type` 均为 `PLACEHOLDER`。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.8, 2.9**

### Property 6: 幂等脚本可重入且不重排文件

`fix_l0_prefill_presets.py --apply` 连跑两次，第二次 `--check` 返回 0 项欠账且文件 md5 不变；脚本内 round-trip 自检（`json.dumps` 复现原文）通过。

**Validates: Requirements 2.5, 2.6**

### Property 7: 校验器只扫语义字段

给某 cell 的 `description` 塞入被禁字样（如 `TB_SUM('2001~2501')`）时 `--check` 仍返回 0 项欠账；给 `formula` 塞入同一字样时 `--check` 必须打红。

**Validates: Requirements 2.7**

### Property 8: 矩阵结构与源模板一致

`buildL0SummaryMatrix` 输出恰 2 个品种维度、每维 8 个 cell；8 个 `label` 与源 xlsx `C30:C37` 逐字相等；`kind` 序列为 `[amount, amount, ratio, amount, ratio, ratio, amount, ratio]`；仅 `book_amount` 的 `editable` 为 true。

**Validates: Requirements 3.1, 3.2**

### Property 9: 矩阵指标与 F0 同源

对同一输入，`buildL0SummaryMatrix` 与 `buildF0SummaryMatrix` 的 8 指标 `label` / `kind` / `editable` / `value` 逐字节相同（收敛前防漂移）。另断言 `F0MatrixCell` 仍是 label-as-key 形态 —— 一旦 F0 改为 key+label 即打红，提示收敛可推进。

**Validates: Requirements 3.2**

### Property 10: 比例列按源模板兜底

分母为 0 或非有限值时，三个比例列返回 `0`（源模板 `IF(ISERROR(...),0,...)` 口径），不返回 `null`、不抛异常；末行按 `(alt + replied) / book` 计算。

**Validates: Requirements 3.2**

### Property 11: 账面金额取数复用 L 循环规格

科目定位的唯一入口是 `resolve_semantic_accounts(ctx, cat.spec)`，且 `L0_MATRIX_CATEGORY_SPECS` 各条的 `spec` 与 `l_cycle_specs.L5_SPEC` / `L4_SPEC` **对象身份相同**（`is` 判定，不是复制品）；模块内不出现按码直查的形态（`LIKE '27`、`startswith("2701"`、`filter_by_prefixes(` 等）。

🔴 **判据不是「源码不含四位数字」** —— `formula_hint` 与 `notes` 是**溯源展示文案**，逐字写明 `BS-064 = TB('2701')` 口径与 `2702` 不扣减的理由，属审计追溯能力（平台铁律「审计 UI 必须有逻辑追溯能力」），一律禁数字会把它们一起禁掉。判据落在**取数形态**上而非字符出现上。

**Validates: Requirements 3.3, 10.4**

### Property 12: 「无此科目」与「余额为 0」可区分

`found=False` 时 `amount` 为 `None`；`found=True` 且余额为 0 时 `amount` 为 `0.0`。前端消费侧对 `undefined`（注入整体失败）、`null`（无此科目）、`0`（余额为零）三态渲染文案互不相同，且源码不含 `?? {}` 形式的兜底。

**Validates: Requirements 3.4**

### Property 13: 手工覆盖键用指标 key 构键

`matrixOverrideItemId` 输出匹配 `^L0-1-matrix-(长期应付款|应付债券)-[a-z_]+$` —— 品种段是源模板中文字面（与 SUMIF criteria 同源），**指标段是稳定 key 不得含中文**。反向自检：把指标段换成中文 label 的朴素实现必须被断言打红；另断言键形与 K0/G0 同构（`X0-1-matrix-{品种}-{指标key}`）。

**Validates: Requirements 3.5**

### Property 14: 下区文案忠于源模板

`L0_SAMPLE_SELECTION_DEFS` 恰 6 项且 label 与源 `J29/J30/J31/J32/J34/J35` 逐字相等；`J33` 括注不作为独立录入项而作为提示文本存在；`L0_AUDIT_NOTE_DEFS` 恰 5 段且与源 `S29/W29/S33/S34/S36` 对应；`W30`+`W31`、`S34`+`S35`、`K35`+`K36` 三处各合并为一段完整文字（源模板把一句话拆两格，只取前格会渲染出半句话）。

**Validates: Requirements 3.6, 3.7**

### Property 15: 审计说明序号笔误已更正且留证

`L0_SECTION_TITLES` 中审计说明段的展示值以「三、」开头；源模板字面「二、审计说明」被登记为笔误说明文本；参考结论 3 条与后附证据说明以只读方式存在。

**Validates: Requirements 3.8, 3.9**

### Property 16: 下区键空间不与上区冲突

下区全部持久化键以 `L0-1-lower` 或 `L0-1-matrix` 开头；上区 grid 载荷写入路径为 `html_data['函证结果汇总表L0-1']`。源码级断言下区录入不经 `emit('save', ...)`，而是直接调 `checklist-responses` 端点。

**Validates: Requirements 3.10**

### Property 17: 下区门控不波及其余枢纽

`GtConfirmationSummary.vue` 中 `L0SummaryLowerZone` 的渲染受 `isL0` 门控；对 D0/E0/F0/G0/H0/K0 六个 cycle 值，该组件不出现在渲染树中。标签存在性断言使用带边界的正则（`<L0SummaryLowerZone(?=[\s/>])`）。

**Validates: Requirements 3.11, 8.5**

### Property 18: 伪列已撤且字段未删

`CYCLE_VARIANT_COLUMNS.L0` 不含 `send_memo`；`resolveConfirmationColumns('L0')` 输出的 key 集合不含 `send_memo`；但 `ConfirmationRow` 类型仍保留该字段，且行详情面板存在只读呈现分支。

**Validates: Requirements 4.1, 4.2, 10.6**

### Property 19: 行级审计结论归属独立段

`resolveConfirmationColumns('L0')` 中 `row_conclusion` 列的 `group === 'row_summary'`；其 `source` 字面指向 `L0-1` 而非 `K0-1/L0-1` 或 `H0-1`。

**Validates: Requirements 4.3**

### Property 20: 空列噪声已剔除

`CYCLE_EXCLUDED_COLUMNS.L0` 恰为 `['contact_person', 'contact_phone', 'currency']`；三者不在 `resolveConfirmationColumns('L0')` 输出中；反向断言源 xlsx `L0-1` 第 5/6 行表头不含「联系人」「联系电话」「币种」。

**Validates: Requirements 4.4**

### Property 21: 渠道列与函证类型列显式区分

`resolveConfirmationColumns('L0')` 同时含 `send_channel` 与 `confirmation_method`，两者 label 不相等；`confirmation_method` 的 L0 label 含「积极式」与「消极式」；源码级断言 `confirmation_method` 未被改绑渠道枚举（其可确认金额派生分支保持不变）。

**Validates: Requirements 4.5, 4.6**

### Property 22: label 覆盖逐条取自源模板

`CYCLE_COLUMN_LABEL_OVERRIDES.L0` 的每个 value 与源 xlsx `L0-1` 第 5/6 行对应格字面相等（`diff_ref_index` 除外，见 Property 23）；另六枢纽的 override 表条目未被改动。

**Validates: Requirements 4.7, 4.9, 10.1**

### Property 23: 调节索引笔误已更正

`diff_ref_index` 的 L0 label 指向 `L0-4` 而非源字面的 `F0-4`；且存在登记项说明源模板字面为 `调节索引（F0-4）`。

**Validates: Requirements 4.8, 6.2**

### Property 24: 列出处 manifest 覆盖 resolve 输出

`resolveConfirmationColumns('L0')` 的 key 集合 ⊆ `CONFIRMATION_SOURCE_MANIFEST.L0` 声明的 key 集合；`confirmationColumnSpec.spec.ts` 的 `NO_EXCLUSION_CYCLES` 白名单不含 L0。

**Validates: Requirements 4.10, 9.6**

### Property 25: 隐藏 sheet 不进 render-config

L0 的 render-config `sheets` 恰 9 项，与源 xlsx 中 `sheet_state == 'visible'` 的 9 张逐字一致（顺序亦一致）；`函证差异检查表（示例）` 不在其中。

**Validates: Requirements 5.1**

### Property 26: 复合键 skip 不误伤同名可见 sheet

D0 与 F0 的 render-config `sheets` 中 `函证差异检查表（示例）` 仍存在；`_WP_CODE_OVERRIDE` 中不存在裸键 `函证差异检查表（示例）` → `skip` 的映射。反向自检：把复合键改成裸键后，D0/F0 断言必须打红。

**Validates: Requirements 5.2, 5.3, 5.5**

### Property 27: skip 判定既有路径优先且行为不变

复合键判定位于既有三条（全名 / 尾码 / 前缀码）之后；对全库既有 skip 条目，判定结果在改动前后逐条相同（characterization 快照比对）。

**Validates: Requirements 5.4, 10.2**

### Property 28: 差异检查表编码声明与渲染一致

`cycleConfirmationMeta.L0.diffChecklistCode === null`，且 `buildCrossWorkpaperNavDefs('L0')` 不产出差异检查表项 —— 与 Property 25 的不渲染结论一致（避免「meta 说没有、页签却在」的自相矛盾）。

**Validates: Requirements 5.6**

### Property 29: 笔误登记走既有机制

L0 的三处笔误经 `ConfirmationSheetRef` 的 `sheetName` / `indexLabel` / `indexTypoNote` 表达；`indexLabel` 取自底稿目录 `F4:F11`，`sheetName` 取自源 xlsx 真实 tab 名；源码级断言未新建第二套笔误登记结构。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 30: meta 加法式改动

`cycleConfirmationMeta.L0` 的既有 `*Code` 字段（`summaryCode` ~ `fraudCode`）取值在改动前后逐字节相同。

**Validates: Requirements 6.4**

### Property 31: L0-5 区块标题对齐源模板

`ALTERNATIVE_BLOCK_MANIFEST.L05` 的三处 title 与源 xlsx `L0-5!A13/A20/A28` 语义对应；block2 title 不含「银行对账单」「借款合同」；block3 借贷副标题对应 `A29`/`A37`；block4 仍标 `sourceExtra: true`。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 32: 区块标题改动不影响持久化

`ALTERNATIVE_BLOCK_MANIFEST.L05` 各条的 `block` key、`columns` 数组、以及 `useAlternativeL05Data` 的 `SUM_FIELDS` 在改动前后逐字节相同；manifest title 与组件渲染 title 逐字一致。

**Validates: Requirements 7.5, 7.6**

### Property 33: 源模板事实守卫以 openpyxl 为裁决者且含反向自检

后端守卫直读源 xlsx，固化 sheet 状态 / 目录索引 / 五段表头 / 28 列字面 / 8 指标公式 / 2 品种 / 12 条程序 / 四处真实 DV / 三处笔误。含反向自检：断言镜像残留 sqref（`JK8:JL27` 等）存在于文件中但不覆盖 `L0-1` 的真实数据列。

**Validates: Requirements 8.1, 8.2**

### Property 34: 前后端交叉锁死

前端守卫以 `fs.readFileSync` 直读后端源模板 fixture / `l_cycle_specs.py`，比对矩阵 `row_code`、兜底码、指标 key 与下区文案；`REPO_ROOT` 以双哨兵具体文件向上查找。

**Validates: Requirements 8.3, 8.7**

### Property 35: 守卫经变异检验

每条新增守卫配一次变异检验记录（改一字 → 必须变红）；读源码型守卫先 `stripComments()` 且配「原始源码确实含被禁字样」的反向自检。

**Validates: Requirements 8.4, 8.6**

### Property 36: 共享件改动为加法式最小 hunk

`confirmationColumnSpec.ts` 的三个 record 中，L0 之外的键取值逐字节不变；与 K0 spec 的兼容判据（双方 record 键互不重叠）成立。

**Validates: Requirements 9.1, 9.2, 10.1**

### Property 37: L 循环与共享组件零回归

`l_cycle_specs.py` 未被修改（本 spec 只读）；reliability / followup / alternativeD05 `CheckBlock` / entityVerify / fraudRisk 五个共享组件的 props 与渲染逻辑逐字节不变。

**Validates: Requirements 10.4, 10.5**

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| `get_template('L0A')` 仍为 None（模板未加载） | 程序表按 xlsx 兜底提取，但守卫必须打红 | 静默回退 F0A 是本 spec 要消除的缺陷，不能再留兜底掩盖 |
| 账面金额取数抛异常 | fail-open 记 WARNING，载荷该品种键**不写入** | 「注入失败」与「无此科目」必须可区分（Property 12） |
| 某品种科目在本项目不存在 | `found=False` + `amount=None`，前端显示「本项目无此科目」info tag | 宁缺勿造；「无此科目」是正确行为而非告警 |
| 叶子和与父额勾稽不成立 | 载荷带 `parent_check.diff`，前端溯源面板显示差异 | 保留审计追溯能力，不静默取某一口径 |
| `2702 未确认融资费用` 与父族同时命中 | 父族聚合已净掉 → 跳过二次减，记 `net_of_skipped` | 二次减即双算 |
| 下区取数失败 | `diagnostics.errors` 渲染为 warning 提示条 | 只收集不渲染会掩盖链路失效 |
| 复合键 skip 判定命中但既有判定也命中 | 既有判定优先（顺序在前） | 保证 Property 27 的行为不变 |
| `send_memo` 有历史值但列已撤 | 行详情面板只读呈现 + 来源说明 | 数据零丢失红线 |
| 幂等脚本 round-trip 自检失败 | 非零码退出，不写盘 | 防全文件重排与并发冲突 |

## Testing Strategy

### 后端

- `backend/tests/test_l0_source_template_facts.py` — openpyxl 直读源 xlsx，固化 Property 33 的全部事实 + 反向自检；不连库，可进 CI
- `backend/tests/test_l0a_program_template.py` — Property 1 / 2 / 3 / 4；Property 2 的反向自检用临时移除 `tables.L0A` 的方式复现旧行为，**移除操作放 `finally` 里无条件写回**
- `backend/tests/test_l0_prefill_presets.py` — Property 5 / 6 / 7
- `backend/tests/four_table/test_l0_book_amounts.py` — Property 11 / 12；含真实库直跑脚本 `backend/scripts/diagnose/verify_l0_book_amounts_live.py`（只读，逐项目逐品种打印 `resolved_from` / `codes` / `amount` / `parent_check.diff`）
- `backend/tests/test_l0_render_sheets.py` — Property 25 / 26 / 27；Property 27 用 characterization 快照（改动前后全库 skip 判定结果比对）

### 前端

- `l0-confirmation/__tests__/l0SummaryMatrix.spec.ts` — Property 8 / 9 / 10 / 13；含 PBT（任意 rows 输入下比例列不产生 NaN/Infinity）
- `l0-confirmation/__tests__/l0LowerZone.spec.ts` — Property 14 / 15 / 16
- `l0-confirmation/__tests__/l0ColumnAlignment.spec.ts` — Property 18 ~ 24 / 36
- `l0-confirmation/__tests__/l0SheetMeta.spec.ts` — Property 28 / 29 / 30 / 31 / 32
- `confirmation/__tests__/l0LowerZoneWiring.spec.ts` — Property 17（含带边界的标签存在性断言）

### 变异检验清单

每条守卫落地后逐条执行并记录（Property 35）：改 label 一字 / 删一个指标 / 把 key 换成中文 / 撤销剔除列 / 把 group 改回 `send_memo` / 把复合键改成裸键 / 删 `tables.L0A` / 把科目码换回 `2001` —— 八项变异必须各自打红对应断言。**变异没打红说明守卫有缺陷，而不是代码没问题。**

### 实测（三件套，缺一不算实测）

1. **录 ≥2 行真实数据** —— L0-1 上区录两行不同品种（长期应付款 / 应付债券），填金额、回函金额、替代确认金额
2. **看目标区域真出数** —— 下区矩阵 2 品种 × 8 指标逐格核对；比例列按源模板口径；程序表页签显示 12 条债务循环程序且 `ref_index` 为 `L0-*`
3. **postgres 查落库** —— `checklist_responses` 的下区 4 类键 + `parsed_data.html_data` 的上区载荷

**实测入口必须用 `wp_code=L0` 的整册工作簿**（9 sheet）—— 单 sheet 遗留 wp_code（`L0-1`）render 出 `html_data=null`，会误判「注入没生效」。

实测完毕后按实测前快照**逐字节复原**（含 `parsed_data`、`checklist_responses`、`updated_at` 语义），并核实同表同类底稿的常态作为基线交叉验证。
