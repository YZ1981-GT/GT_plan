# Design: F1 四表库取数链路根治 + 披露/附注结构收尾

## Overview

两条互不依赖的主线：

- **主线 A（取数）** 把 `_f1_prepayment.py` 的硬编码方言换成平台共享件
  `app/services/four_table/`，并补出 F1 从未有过的 `adjudication_prefill`（按性质分类）
  与减值准备解析；前端新增溯源面板 + 「从四表库带入未审数」按钮，消灭 dead output。
- **主线 B（披露）** 列头字面三向对齐源 xlsx、上市③二选一模式、8 处金额控件迁移、
  新建勾稽引擎与面板。

两条主线在 **Wave 5（勾稽面板）** 处有一个弱耦合：国企「逐段减值准备合计 = 四表库
`1231-04` 期末」这条规则需要主线 A 下发的 `impairment_prefill`；设计上让该规则在
`fourTableImpairment == null` 时返回 `skipped`，从而两条主线可并行开发、独立验证。

**不做的事**（明确划到范围外，避免返工）：

| 项 | 理由 |
|----|------|
| 改按账龄表为源 xlsx 国企 7 列三级表头 | 附注是交付物 → 列结构随**校验预设**（F7-6/F7-7/F7-8/F7-13 明确写「小计行 / **减值准备行** / 合计行」= 行形态），归档 spec 已据此裁决；国企源 xlsx 的逐段坏账准备列留在**底稿侧**作审计明细，同步时聚合为一行（信息不丢，两侧各守其源） |
| 改 `BS-008` 报表公式加 `- TB('1231-04')` | 平台级 data-hygiene（同 K1 spec 对 `BS-006` 的处置），另立 |
| `note_template` 的 `report_row_code` 全库陈旧 | 平台级，inert，另立 |
| F2/F3/F4 同类修复 | 沿用本 spec 范式另立 |
| F0 / F5 | 源模板无附注 sheet（已确认属正常） |

## Architecture

### 科目映射链路（本 spec 的核心认知，DB 只读实证）

```
tb_balance.account_code          客户原始码（点号分级）    1123 / 1123.02.01 / 1231.03
      │ account_mapping(project_id, original → standard)     ← 反解方向：standard → original
      ▼
trial_balance.standard_account_code  标准码（横杠分级）      1123 / 1231-04
      │ report_config.formula（按 applicable_standard 精确匹配）
      ▼
报表行 BS-008「预付款项」
   listed_standalone / listed_consolidated / soe_standalone / soe_consolidated
     一律 = TB('1123','期末余额')          ← 四个准则同形，且**不减备抵**
```

关键推论（决定实现形态）：

1. `BS-008` 公式**无备抵项** → `resolve_report_line_accounts` 的 `provision_std` 为空
   → 走 `spec.fallback_provision = ('1231-04',)`，该侧 `provision_resolved_from='fallback'`。
2. 实证 9 个项目的 `account_mapping` **全部没有** `1231-04` 记录（只有 `-01/-02/-03` 与裸
   `1231`）→ `to_original_codes_with_flag` 返回 `(['1231'], exact=False)`
   → **必须**叠名称过滤「预付」，否则 `1231` 宽前缀会把应收账款坏账（实证 `0ec33ac9`
   为 26,401,719.77）算进 F1。过滤后实证结果为**空集** → 减值准备无预填（宁缺勿造，正确）。
3. `1123` 的叶子子科目名带业务语义（`_预付货款` / `_长期资产款_工程款` / `_短期待摊费用`
   / `_其他`）→ 可干净映射到 F1-1「按性质分类」五桶，这是 F1 与 D3（2203 无性质维度、
   归档 spec 判定「宁缺勿造不做 prefill」）的**本质差异**，故 F1 做 prefill 是有据的。

### 取数级联（改动后）

```
四表入库
  ├─ tb_balance 1123 叶子 ──┬─→ [新] adjudication_prefill.nature{opening,closing}
  │                          │        → F1-1「按性质分类」未审数（手工 > F1-2 > 四表）
  │                          └─→ project_context.prepaid_tb_amount（既有，TB 核对标量）
  ├─ tb_balance 1231.*「预付」──→ [新] impairment_prefill{end,prior}
  │                                   → 上市披露 impairment-provision / -prior（无持久化时）
  │                                   → 国企：仅溯源展示 + 勾稽右值
  ├─ tb_balance 1401 / 2202 ─→ project_context.inventory/payable_balance_current（既有，改叶子口径）
  └─ tb_aux_balance 1123「客户」→ F1-det-rows（既有 useF1DetailAutoSeed → /f1/import-aux-balance）
                                   → useF1CrossSheet 聚合 → F1-1 按性质/按账龄 → 两个披露表 → 附注
```

### 披露 → 附注（改动后）

```
F1TabDisclosureListed/Soe
  ├─ useF1DisclosureListed/Soe.getSyncSnapshot()
  │     + [新] listed: top5Mode（'separate' | 'summary'）
  ├─ f1DisclosureSyncPayload.buildF1{Listed,Soe}SubTableData()
  │     · columns 字面对齐源 xlsx（期末数/上年年末数/账  龄/金  额/金 额）
  │     · listed top5Mode='summary' → 不推③表 + _removed_table_keys 含③表名
  │     · listed top5Mode='separate' → 推③表 + 不推 listed-top5-summary
  └─ POST /disclosure-notes/sync-from-workpaper（自动同步：包装 save，已有）
        → note_template §五、7 / §八、7（seed 侧由 fix_note_prepayment_structure.py 对齐）
```

## Components and Interfaces

### 后端

#### `backend/app/routers/wp_render_strategies/_f1_prepayment.py`（改）

```python
_F1_CROSS_CYCLE_PREFIXES = ("1401", "2202")   # F1-4 跨循环锚点（非 F1 主科目）

F1_REPORT_LINE_SPEC = ReportLineAccountSpec(
    row_code="BS-008",
    fallback_gross=("1123",),
    fallback_provision=("1231-04",),
    provision_name_filter="预付",
)

async def _resolve_f1_accounts(ctx) -> ReportLineAccounts: ...
async def _fetch_f1_leaf_rows(ctx, prefixes) -> list[LeafRow]: ...   # get_active_filter + SQL 下推

# 纯函数（可单测，无 DB）
def classify_f1_nature(account_name: str) -> str: ...               # → rowKey
def build_nature_prefill(leaves, gross_prefixes) -> dict: ...       # → {rowKey:{opening,closing}}
def build_impairment_prefill(leaves, provision_prefixes, name_filter) -> dict | None: ...
```

`render()` 新增输出：

```jsonc
{
  "adjudication_prefill": {                  // 无数据时整键省略
    "nature": { "goods": {"opening": 17898830.40, "closing": 13576792.21}, … }
  },
  "impairment_prefill": null,                // 或 {"end": x, "prior": y}
  "project_context": {
    "tb_source_codes": {                     // 由 list[str] 升级为结构化（前端消费）
      "row_code": "BS-008",
      "formula": "TB('1123','期末余额')",
      "gross_standard": ["1123"], "gross": ["1123"],
      "provision_standard": ["1231-04"], "provision": ["1231"],
      "resolved_from": "report_config", "provision_resolved_from": "fallback",
      "provision_exact": false, "use_provision_name_filter": true
    }
  }
}
```

> 🔴 兼容：`tb_source_codes` 由 `list[str]` 变 `dict` —— 已确认前端 **0 消费**
> （grep `tb_source_codes` 仅命中 render 自身），故无破坏性；后端 characterization
> 测试须显式钉死新形态。

#### `backend/data/prefill_formula_mapping.json`（改）

F1-1 块补 6 条 + 新增 F1-2 / F1-4 两块。**F1-2 块不得含 `WP(`**（防 F1-1 ↔ F1-2 循环，
与 N1-2 / K1-2 同约束，由 `test_h1_two_level_chain` 同族守卫覆盖）。

#### `backend/scripts/fix/fix_note_prepayment_structure.py`（改）

`_aging_patch()` 参数化标签字面：

```python
def _aging_patch(end_group, prior_group, amount_label, pct_label, label_col="账  龄"): ...

# listed: _aging_patch("期末数", "上年年末数", "金  额", "比例%")
# soe:    _aging_patch("期末数", "期初数",     "金 额",  "比例（%）")
```

`ALIGNED_BY` 追加本 spec 名（保留旧值兼容 `--check` 的历史断言 → 改为集合成员判定）。

#### `backend/tests/`（新增）

| 文件 | 内容 |
|------|------|
| `test_f1_four_table_extraction.py` | 纯函数：`classify_f1_nature` 参数化（含实证 6 个真实科目名）、`build_nature_prefill` 五桶和 == 叶子合计、点号边界、备抵名称过滤断言不含 `1231.02`、空数据返回 `None`/`{}` |
| `test_f1_render_characterization.py` | render 在依赖缺失（无 `report_config` / 无 `account_chart` / 无 `account_mapping`）时输出与改动前等价的兜底科目；`tb_source_codes` 新形态钉死 |
| `services/test_note_prepayment_structure.py`（扩展） | **openpyxl 直读源 xlsx** 三向比对：`A8=='账  龄'`、listed `B8=='期末数'`/`D8=='上年年末数'`/`B9=='金  额'`、soe `B10=='金 额'` ↔ 模板 `columns` ↔ `f1DisclosureSyncPayload.ts` 源码正则抽取；含反向自检 |
| `test_f1_prefill_presets.py` | F1 条目归 `workpaper:F1`、`formula_type` 受支持、F1-2 块无 `WP(`、坏账/借贷/AUX/WP 条目齐备 |

### 前端

| 文件 | 动作 |
|------|------|
| `composables/f1FourTableSource.ts` | **新增**。纯函数 `normalizeF1TbSource(raw)`（兼容旧 `list[str]` 与新 dict）+ `describeResolvedFrom(v)`（中文化 tag） |
| `composables/useF1Adjudication.ts` | 改：新增 `naturePrefill?: Ref<Record<string,{opening,closing}>>` 选项 + `pullNatureFromTB()`（持久化，只覆盖出现的桶）；`buildRow` 的 seed 链改为「手工 > 明细 > 四表」 |
| `composables/f1DisclosureSyncPayload.ts` | 改：列 label/group 字面；`F1ListedSyncSnapshot.top5Mode`；`buildF1ListedSubTableData` 按 mode 分支 + `_removed_table_keys` |
| `composables/useF1DisclosureListed.ts` | 改：`top5Mode` ref（持久化 `F1-note-listed-top5-mode`）+ `setTop5Mode()`；`impairmentProvision/Prior` 加 `impairmentPrefill` 只读回退（手工优先） |
| `composables/useF1DisclosureSoe.ts` | 改：暴露 `fourTableImpairment`（只读，供勾稽） |
| `composables/f1DisclosureConsistency.ts` | **新增**。纯函数引擎，`buildF1ConsistencyChecks(variant, input) → F1CheckResult[]` |
| `f1/F1FourTableSourcePanel.vue` | **新增**。紧凑单行 bar + 折叠明细（报表行 / 公式 / 标准码 / 原始码 / 来源 tag） |
| `f1/F1DisclosureConsistencyPanel.vue` | **新增**。bar + 折叠明细表 + 规则 tooltip + `GtIndexChip` |
| `f1/F1TabAdjudication.vue` | 改：顶部挂溯源面板；工具条加「从四表库带入未审数」（`:loading` + `:disabled="isReadonly"`） |
| `f1/F1TabDisclosureListed.vue` | 改：4 处 `el-input-number` → `WpAmountInput`；列头字面改引常量；③区块加 `el-radio-group`；挂勾稽面板 + 溯源面板 |
| `f1/F1TabDisclosureSoe.vue` | 改：4 处 `el-input-number` → `WpAmountInput`；列头字面改引常量；挂勾稽面板 + 溯源面板 |
| `GtF1Prepayment.vue` | 改：`f1NaturePrefill` / `f1ImpairmentPrefill` / `f1TbSource` computed（读 `htmlData`）并 provide / 透传 |

#### 列头字面单一真源

`f1DisclosureSyncPayload.ts` 新增导出（Tab 模板与同步载荷同源，杜绝双真源）：

```ts
export const F1_AGING_LABEL_COL = '账  龄'
export const F1_LISTED_AGING_GROUPS = { end: '期末数', prior: '上年年末数' } as const
export const F1_SOE_AGING_GROUPS   = { end: '期末数', prior: '期初数' } as const
export const F1_LISTED_AMOUNT_LABEL = '金  额'   // 源 B9 双空格
export const F1_SOE_AMOUNT_LABEL    = '金 额'    // 源 B10 单空格
export const F1_LISTED_PCT_LABEL = '比例%'
export const F1_SOE_PCT_LABEL    = '比例（%）'
```

Tab 模板改为 `:label="F1_LISTED_AGING_GROUPS.end"` 等，由契约测试正则锁死
「Tab 源码不得出现 `label="期末余额"` 字面」。

## Data Models

### `F1NaturePrefill`（render → 前端）

```ts
type F1NatureRowKey = 'goods' | 'construction' | 'equipment' | 'service' | 'other'
interface F1NaturePrefill {
  [k in F1NatureRowKey]?: { opening: number; closing: number }
}
```

### `F1TbSource`（溯源）

```ts
interface F1TbSource {
  rowCode: string                 // 'BS-008'
  formula: string | null
  grossStandard: string[]         // ['1123']
  gross: string[]                 // 原始码前缀
  provisionStandard: string[]     // ['1231-04']
  provision: string[]             // 反解结果（可能退化为 ['1231']）
  resolvedFrom: 'report_config' | 'fallback'
  provisionResolvedFrom: 'report_config' | 'fallback'
  provisionExact: boolean
  useProvisionNameFilter: boolean
}
```

### `F1CheckResult`（勾稽）

```ts
type F1CheckLevel = 'pass' | 'warning' | 'error' | 'skipped'
interface F1CheckResult {
  id: string              // 'F7-6-end' 等，与校验预设 id 对齐
  label: string           // 中文规则名
  rule: string            // 公式原文（tooltip）
  left: number | null
  right: number | null
  diff: number | null
  level: F1CheckLevel
  detail: string          // 差异说明 / 跳过原因
  refs: string[]          // GtIndexChip 值，如 ['wp:F1-1','wp:F1-2','Note:五、7']
}
```

### `top5Mode` 持久化

| item_id | 值域 | 默认 |
|---------|------|------|
| `F1-note-listed-top5-mode` | `'separate'` \| `'summary'` | `'separate'`（分别披露；与改动前推表行为一致，升级零回归） |

## Correctness Properties

### Property 1: 叶子聚合等于父科目额
对任意 `tb_balance` 科目树，`aggregate_leaves(select_leaves(rows), ['1123'])` 的 closing
等于 `parent_totals(rows,'1123')` 的 closing（容差 0.01）。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: 性质归类不丢科目
`build_nature_prefill` 输出五桶的 opening/closing 之和分别等于入参叶子的 opening/closing
之和；且任意科目名都能归到且仅归到一个桶。

**Validates: Requirements 3.1, 3.2**

### Property 3: 备抵侧宽前缀必叠名称过滤
当 `provision_exact == false` 时，聚合 SHALL 只纳入科目名含 `provision_name_filter` 的叶子；
对含 `1231.01/.02/.03` 的实证数据集，结果不包含这三支的金额。

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 4: fail-open 与 characterization
在 `report_config` / `account_chart` / `account_mapping` / DB 任一缺失或异常时，
`render()` 均返回可用结果且 `project_context` 的既有字段
（`prepaid_tb_amount` / `inventory_balance_current` / `payable_balance_current`）
与改动前逐值相等。

**Validates: Requirements 1.6, 2.5**

### Property 5: 手工优先且预填幂等
`pullNatureFromTB()` 连续调用两次的持久化结果相同；存在手工值时预填不覆盖；
预填中未出现的性质桶不被清零。

**Validates: Requirements 3.4, 3.5, 3.6, 3.7, 4.1**

### Property 6: 列字面三向一致
源 xlsx 单元格文本（含空格）== `note_template` 该表 `headers` / `columns[].label`·`group`
== `f1DisclosureSyncPayload` 的 `F1_*_COLUMNS` 对应项；数据 `key` 集合在改动前后不变。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 11.2, 11.3**

### Property 7: 上市③二选一互斥且可逆
对任意 `top5Mode`，载荷中「③表存在」与「`listed-top5-summary` 存在」恰有一者为真；
`summary` 模式下 `_removed_table_keys` 含③表名，`separate` 模式下不含；
两次切换后载荷回到初始值。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 8: 勾稽规则集完备且不误判
`buildF1ConsistencyChecks` 对两个变体输出的 `id` 集合分别等于该变体在
`note_check_preset_formulas.json` 中 `note_section='五、7'` 的可判定规则集（跳过的显式标
`skipped`）；缺数据一律 `skipped` 而非 `error`。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 9: 账龄枚举驱动且尾部三行恒在
对 3年段 / 5年段 / 自定义 2~10 段任意配置，①表 data 行数 == 段数，
尾部恒为 `小计` / `减：减值准备` / `合计`，且 `小计`·`合计` 带 `is_total`。

**Validates: Requirements 10.1, 10.2, 10.5**

### Property 10: 动态行整表覆盖
上市②/国企②表增删任意行后，载荷该表行数 == 界面明细行数 + 1（合计行）；
清空到无行时仍推送仅含合计行的表且不进 `_removed_table_keys`。

**Validates: Requirements 10.3, 10.4**

### Property 11: 公式预设收敛
F1 全部预设条目归入 `workpaper:F1`、`formula_type` 属受支持集合；F1-2 块不含 `WP(`。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 12: 金额控件归零
两个披露 Tab 的 `el-input-number` 出现次数为 0；`WpAmountInput` 渲染点数 == 可编辑金额格数；
比例 / 账龄 / 笔数字段不使用 `WpAmountInput`。

**Validates: Requirements 9.1, 9.2, 9.3**

## Error Handling

| 失败点 | 处理 | 用户可见表现 |
|--------|------|-------------|
| `report_config` 无 `BS-008` 行 / 准则派生失败 | `resolve_report_line_accounts` 内部捕获 → 用 `fallback_gross=('1123',)` | 溯源面板来源 tag 显示「兜底科目」（橙色） |
| `account_chart` 查询失败 | `split_gross_provision` 降级为码族启发（`1231` 前缀） | 无感；溯源面板仍显示解析结果 |
| `account_mapping` 无记录 / 查询失败 | 退化为 `normalize_standard_prefix`（`1231-04` → `1231`）+ `provision_exact=false` → **强制叠名称过滤** | 溯源面板显示「原始码：1231（宽口径，已按『预付』过滤）」 |
| `tb_balance` 查询异常 | `except` + `rollback`，返回空 balances | 预填为空；TB 核对行显示「未取数」而非 0 |
| 四表库无 `1123` 叶子 | 预填整键省略 | 「从四表库带入未审数」按钮点击后提示「四表库暂无预付款项明细科目数据」 |
| 四表库无「预付」备抵科目 | `impairment_prefill = null` | 减值准备格保持手工；勾稽规则「逐段合计 vs 四表库」标 `skipped`「四表库无坏账准备-预付账款」 |
| 披露同步 HTTP 失败 / 409 `STANDARD_MISMATCH` | 自动同步静默（`catch`），手动按钮给 `ElMessage.warning` | 手动按钮提示失败；自动同步不打断录入 |
| AI 生成失败 | 既有 `useF1AiGenerate` 的 `ElMessage.warning('AI 生成失败')` | 零改动 |
| 保存批次失败 | 现有 `debouncedSave` 单 item 保存（无累积器）→ 无同 id 风险 | 零改动 |

## Testing Strategy

| 层 | 手段 |
|----|------|
| 纯函数 | pytest 参数化 + hypothesis（`max_examples=5`）覆盖 Property 1/2/3 |
| render | characterization（Property 4）+ 新输出形态钉死 |
| 模板结构 | `--check` 零欠账 + openpyxl 三向比对 + 反向自检（Property 6） |
| 前端契约 | 扩展 `f1NoteSubtableContract.spec.ts` / `f1DisclosureColumns.spec.ts`；新增 `f1DisclosureConsistency.spec.ts` / `f1Top5Mode.spec.ts` / `f1AmountInputMigration.spec.ts`（读 SFC 源码，先 `stripComments()` 并自检）|
| 端到端 | chrome-devtools 驱动 + postgres 只读比对（`last_sync_at` 前移、`_sub_table_columns` group 字面、子表数）；测试数据复原 |

## Rollout / Risk

- **无灰度开关**：F1 取数改动是「口径修正 + 新增预填」，且预填严格手工优先 + fail-open，
  与 D1 的 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 不同侧（那是 D 循环公用开关）。
  风险由 characterization 测试兜住。
- **模板改动只对新建项目 / 重新生成附注生效**（`_source=workpaper` 时投影器完全覆盖模板
  rows）→ 交付说明必须写清；既有项目由「同步到附注」整表覆盖。
- **并发会话风险**：`note_template_{listed,soe}.json` 与 `prefill_formula_mapping.json`
  是多 spec 共改的共享真源 → 改动一律走幂等脚本 + `--check`，测试红了先重跑脚本。
- **`ALIGNED_BY` 改动**：`--check` 现断言 `_aligned_by == ALIGNED_BY` 单值，改为集合判定，
  否则重跑脚本前 CI 必红。
