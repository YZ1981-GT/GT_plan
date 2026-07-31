# Design Document

## Overview

K2 的修复复用 K1 spec 刚建立的两个共享件，**不新造第三套四表读取**：

- `four_table/report_line_accounts.py` —— 报表行 → 标准码 → `account_mapping` 反解 → 原始码
- `four_table/leaf_aggregation.py` —— 叶子口径聚合（叶子和 == 父科目额）

K2 只需声明自己的 `ReportLineAccountSpec`（`row_code='BS-014'`、兜底 `1901`、
`extra_standard_codes=('1131',)`）即可。这是共享件的**第三个消费者**（D1 / K1 / K2），
也是验证该抽象是否真的可复用的第一手证据。

第二条主线是**行模型从固定枚举改为动态行**。同循环的 `useK2Detail`（K2-2 明细表）
已有成熟的动态行实现（`addRow` + `prompt` 命名 + `removeRow` + `addRowDirect`），
K2-1 直接对齐它的范式，避免同一循环里两套行模型。

## Architecture

```
report_config: BS-014 其他流动资产
  soe_* / listed_consolidated : TB('1901','期末余额')
  listed_standalone           : TB('1901','期末余额') + TB('1131','期末余额')
        │ 标准码 → account_mapping 反解 → 客户原始码
        ▼
K2_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code='BS-014',
    fallback_gross=('1901',),
    fallback_provision=(),            # 其他流动资产无备抵科目
    extra_standard_codes=('1131',),   # 报表引用但不并入原值（已属 BS-009）
)
        ▼
_k2_other_current_assets.py::render
  ├─ resolve_report_line_accounts   → gross / extra / tb_source_codes
  ├─ select_leaves + aggregate_leaves(gross)   → tb_values
  ├─ _build_adjudication_prefill    → 动态行候选（叶子科目名 + 期初/期末）
  │     宁缺勿造：解析不出科目 → 返回 []（不再塞坏账准备、不再兜底「其他」行）
  └─ tb_source_codes（前端溯源面板消费）
        ▼
GtK2OtherCurrentAssets.vue
  ├─ tbData（读 tb_values，键名对齐）
  ├─ tbSourceCodes → K2FourTableSourcePanel（复用 K1 面板组件）
  └─ K2TabAdjudication
        └─ useK2Adjudication（**改造核心**）
              ├─ 动态行清单持久化 `K2-1-rows`（JSON: [{rowId, label}]）
              ├─ addRow(prompt) / renameRow / removeRow(清理 K2-1-{rowId}-*)
              ├─ migrateLegacyFixedRows()  ← 8 个旧 rowKey → 动态行
              ├─ seedFromPrefill()         ← 按叶子科目名建行（无持久化行时）
              └─ pullFromDetail()          ← 从 K2-2 按行名聚合
```

## Components and Interfaces

### 后端

#### `_k2_other_current_assets.py`（重写取数部分）

```python
K2_REPORT_ROW_CODE = "BS-014"
K2_FALLBACK_GROSS = "1901"          # 待处理财产损溢
K2_DIVIDEND_STANDARD = "1131"       # 报表引用但不并入原值

K2_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code=K2_REPORT_ROW_CODE,
    fallback_gross=(K2_FALLBACK_GROSS,),
    fallback_provision=(),
    extra_standard_codes=(K2_DIVIDEND_STANDARD,),
)

def _build_tb_values(leaves, accounts, tb_amounts) -> dict[str, float]
def _build_adjudication_prefill(leaves, accounts) -> list[dict]   # 纯函数，可单测
async def render(ctx) -> dict   # 新增 tb_source_codes
```

删除 `_K2_ACCOUNT_PREFIXES` / `_K2_ACCOUNT_PREFIX` / 旧 `_fetch_tb_data`
（死代码立即删，不留 DEPRECATED 注释）。

`tb_values` 键名保持 `other_current_unadjusted*` / `other_current_audited`
（前端已在读，改键名会静默断链），只改**取数口径**。

`K2_SHEETS` 的 `附注披露信息（国有企业）` → `附注披露信息（国企）`。

### 前端

| 文件 | 改动 |
|------|------|
| `composables/shared/dynamicAdjudicationRows.ts`（新建，**平台级共享件**） | 零 Vue 依赖纯函数：行清单序列化/反序列化、`rowId` 生成、重名判定、历史固定行迁移、四表 seed、行键清理。**不含任何循环专属常量** —— 循环差异全部由入参 `DynamicRowsSpec` 声明 |
| `composables/k2AdjudicationRows.ts`（新建，薄壳） | 只放 K2 的 `DynamicRowsSpec`（前缀 `K2-1`、8 个历史 rowKey、3 条外来行警示文案），逻辑一律委托共享件 |
| `composables/useK2Adjudication.ts` | 行集由动态清单驱动；新增 `addRow`/`renameRow`/`removeRow`/`pullFromDetail`；`seedFromPrefill` 去掉模糊匹配与 `other` 兜底 |
| `k2/core/K2TabAdjudication.vue` | 「新增项目行」「删除」「从 K2-2 带入」「从四表库带入」按钮 + 行名可编辑 + 外来行警示 tag + 溯源面板 |
| `GtK2OtherCurrentAssets.vue` | 透传 `tbSourceCodes` |
| `k2/core/K2FourTableSourcePanel.vue` | 薄壳复用 K1 的 `K1FourTableSourcePanel`（同结构，仅报表行不同）→ 实际做法是把 K1 面板提升为 `shared/WpFourTableSourcePanel.vue` 供两循环共用 |

### 守卫

| 文件 | 作用 |
|------|------|
| `backend/tests/four_table/test_k2_account_scope.py` | 科目解析不含 `1231*`、叶子口径、最长前缀、fail-open、`tb_source_codes` 形态、sheet 名 |
| `backend/tests/four_table/test_k2_formula_presets.py` | 无 `6601`/`1231`、含 `1901`、K2-2 无 `WP(` |
| `composables/__tests__/dynamicAdjudicationRows.spec.ts` | **共享件**纯函数 + PBT（往返/迁移/清理/宁缺勿造），用与任何循环无关的替身 spec 驱动 |
| `composables/__tests__/k2AdjudicationRows.spec.ts` | K2 的 spec 声明正确（前缀/历史 rowKey/外来行）+ 动态行在 K2 语境下的行为 |
| `composables/__tests__/k2FourTableWiring.spec.ts` | 溯源透传 + 按钮接线 + 无硬编码枚举残留（反向自检） |

## Data Models

### `K2-1-rows`（动态行清单，持久化到 `checklist_responses`）

```json
[
  { "rowId": "row-1a2b3c", "label": "待摊费用", "source": "tb", "accountCode": "1901.01" },
  { "rowId": "row-4d5e6f", "label": "应收退货成本", "source": "manual" },
  { "rowId": "contract-cost", "label": "合同取得成本", "source": "legacy" }
]
```

- `rowId` 对历史固定行**沿用旧 rowKey**（`contract-cost` 等），使 `K2-1-contract-cost-unadj`
  等既有持久化键继续命中 → 迁移零丢数（R2.4）。
- `source`：`tb`（四表 seed）/ `manual`（手工新增）/ `legacy`（历史固定行迁移）。
- `accountCode` 仅 `source='tb'` 时有值，供溯源展示。

### `tb_source_codes`（render 输出）

```json
{
  "row_code": "BS-014",
  "gross": ["1901"],
  "provision": [],
  "gross_standard": ["1901"],
  "provision_standard": [],
  "extra": { "1131": ["1131"] },
  "signed_codes": [["1901", 1], ["1131", 1]],
  "formula": "TB('1901','期末余额') + TB('1131','期末余额')",
  "resolved_from": "report_config",
  "provision_resolved_from": "fallback",
  "provision_exact": false,
  "use_provision_name_filter": true
}
```

其他流动资产无备抵科目 → `provision` 为空是正常态，守卫须允许。

### `LEGACY_FOREIGN_ROWS`（属于其它报表行的历史固定行）

```ts
export const LEGACY_FOREIGN_ROWS: Record<string, string> = {
  'prepayment':      '预付款项属于报表行 BS-008（F1 循环），列在其他流动资产会重复计入资产',
  'contract-asset':  '合同资产有独立报表行（D6 循环）',
  'deposit':         '押金保证金属于其他应收款的款项性质（K1 循环）',
}
```

UI 对这三行显示警示 tag + tooltip，**不自动删除**（R2.5）。

## Correctness Properties

### Property 1: K2 原值科目集不含坏账准备族

`resolve_report_line_accounts(BS-014)` 返回的 `gross` / `gross_standard` 与
`{1231, 1231-01..05, 1231.01..05}` 交集为空；`render` 输出的 `account_codes` 同理。

**Validates: Requirements 1.1, 1.2**

### Property 2: 附加科目不并入原值

`1131` 出现在 `extra` 而不在 `gross_standard`；`tb_values` 的
`other_current_*` 不含 `1131` 的金额。

**Validates: Requirements 1.3**

### Property 3: 叶子口径与点号边界

叶子集合互不为前缀；前缀过滤要求 `code == p` 或 `code.startswith(p + '.')`，
`1901` 不命中 `19010`；`trial_balance` 求和按最长前缀归属，父子不双计。

**Validates: Requirements 1.4, 1.5**

### Property 4: fail-open 恒不抛且 gross 非空

任意依赖缺失组合下 `render` 不抛异常，`gross` 非空，`resolved_from='fallback'`。

**Validates: Requirements 1.6**

### Property 5: 动态行往返一致

对任意动态行清单 `R`（0~20 行，行名含中文/空格/特殊字符），
`deserialize(serialize(R)) == R`；`rowId` 唯一；行名重复被拒。

**Validates: Requirements 2.1, 2.2**

### Property 6: 历史固定行迁移不丢数

对任意包含 8 个旧 rowKey 子集的 `allResponses`，`migrateLegacyFixedRows` 产出的动态行
清单中，每个有非零金额的旧 rowKey 都存在同名 `rowId` 的行，且 `K2-1-{rowKey}-*` 键值不变。

**Validates: Requirements 2.4, 2.5**

### Property 7: 删除行清理干净

`removeRow(rowId)` 后，`allResponses` 中不存在任何 `K2-1-{rowId}-` 前缀键，
且其它行的键不受影响。

**Validates: Requirements 2.3**

### Property 8: 宁缺勿造

当 `adjudication_prefill` 为空或不含可识别科目名时，`seedRowsFromPrefill` 返回空清单，
**不产生**「其他」兜底行。

**Validates: Requirements 2.6**

### Property 9: 合计覆盖全部动态行

对任意动态行集合，`subtotalRow` 各金额列 == 对应列在全部数据行上的和；
三角勾稽 `期末 = 期初 + 借 − 贷` 与 `审定 = 未审 + AJE + RJE` 在动态行下成立。

**Validates: Requirements 2.8**

### Property 10: 公式预设科目正确

K2 块的所有 `formula` 不含 `6601` 与 `1231`；至少含 `TB('1901','期初余额')`、
`TB('1901','期末余额')`、`WP('K2','明细表K2-2',…)`；K2-2 块不含 `WP(`。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 11: sheet 名三处一致

后端 `K2_SHEETS` 的披露 sheet 名 == 前端 `K2_DISCLOSURE_SHEET_NAME` == 源 xlsx tab 名（逐字）。

**Validates: Requirements 4.1, 4.2**

## Error Handling

| 失败点 | 处理 | 可观测性 |
|--------|------|----------|
| `report_config` 无 `BS-014` | 用 `spec.fallback_gross=('1901',)`，`resolved_from='fallback'` | 溯源面板显示「兜底」tag |
| `BS-017` 同名行（listed，formula 为 NULL）干扰 | 解析按 **`row_code` 精确匹配 `BS-014`**，不按 `row_name` | — |
| `account_mapping` 无 `1901` 记录 | `normalize_standard_prefix` 宽前缀兜底 | `provision_exact` / 日志 |
| `tb_balance` 查询异常 | 返回空叶子 → `tb_values` 空、`adjudication_prefill` `[]` | `logger.warning` + rollback |
| `1901` 全为 0（本库现状） | 返回空预填，不建行 | 前端提示「四表库暂无其他流动资产数据」 |
| `K2-1-rows` JSON 损坏 | 解析失败回退历史固定行迁移路径，不白屏 | 控制台 warn |
| 动态行改名撞名 | `ElMessage.warning` 拒绝，不写库 | UI 提示 |

原则：render 绝不因取数失败抛错；行模型改造对既有数据**只增不删**。

## Testing Strategy

1. **纯函数优先** —— 动态行序列化/迁移/seed、`_build_adjudication_prefill`、
   `_build_tb_values` 全部做成无 DB 纯函数，PBT（`max_examples=5`）覆盖 Property 5~9。
2. **fixture 用实测值** —— 以 `0ec33ac9` 的坏账准备三行（26,401,719.77 /
   1,162,288.03 / 900,217.36）作**反向断言**：修复后 K2 不得再出现这些金额。
3. **characterization** —— K2 render 在依赖缺失路径下不抛、键名不变（前端零改动即可读）。
4. **三处一致守卫** —— openpyxl 直读源 xlsx ↔ 后端 `K2_SHEETS` ↔ 前端常量。
5. **端到端实测** —— chrome-devtools 驱动 + postgres 只读复核 + 数据复原。

命令：

```
python -m pytest backend/tests/four_table -v --tb=short
npx vitest run src/components/workpaper/composables/__tests__/k2AdjudicationRows.spec.ts src/components/workpaper/composables/__tests__/k2FourTableWiring.spec.ts
```

**不做的事**：不动 K2 披露列结构与附注模板（归档 spec 已完成 + 实测）；
不为 K2 新建第二套四表读取；不静默删除用户已录数据。
