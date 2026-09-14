# Design Document: F 类四表取数与披露附注收口

## Overview

本设计把 G/K/D/N 循环已验证的「四表取数三层链路 + 分类桶单一真源 + 溯源下发 + 动态行」
范式推广到 F3/F4/F5，并复核 F1/F2 残余缺口与 F 类四个附注章节。

设计的核心约束来自三条平台铁律：

1. **禁硬编码科目前缀** —— 科目定位必须经 `report_config` 报表行公式解析 →
   `account_mapping` 反解 → `tb_balance` 原始码前缀匹配三层链路。
2. **只汇总叶子** —— 用 `four_table.select_leaves` 严格点号边界，不用 `startswith`。
   自检不变量：叶子和 == 父科目额。
3. **按名称归类，不按编码** —— 客户科目编码语义在项目间冲突（实证 `6402` 既是
   「其他业务成本」也是「其他业务支出」），分类必须走名称匹配 + 顺序优先级 + 否决词。

同时本设计对**两个平台级范围外缺陷**采取「暴露而非绕开」的策略：`trial_balance` 在部分
项目存在父子双算、损益类发生额口径恒为 0 —— F 类审定表并列展示「叶子聚合口径」与
「`trial_balance` 口径」，差异由溯源面板显式检出。

## Architecture

### 取数链路（F3 为例，F4/F5 同构）

```
report_config
  BS-044 应付票据 = TB('2201','期末余额')      ← 四准则一致
        │  resolve_report_line_accounts(ctx, F3_ACCOUNT_SPEC)
        ▼
  gross_standard = ['2201']                    标准码
        │  account_mapping 反解（to_original_codes_with_flag）
        ▼
  gross = ['2201']                             原始码前缀（极小前缀集）
        │  tb_balance 前缀匹配 + select_leaves（严格点号边界）
        ▼
  leaves = [2201.01 银行承兑, 2201.02 商业承兑, 2201.03 信用证]
        │  classify_f3_leaf(name, code)         按名称归类 + 否决词
        ▼
  buckets = {bank: …, commercial: …, letter_of_credit: …, supplychain: …, other: …}
        │  abs() 归一（两种符号约定并存）
        ├──→ tb_values          {opening_leaf, closing_leaf, opening_tb, closing_tb}
        ├──→ adjudication_prefill  按桶给期初/期末
        ├──→ parent_check       叶子和 − 父额
        └──→ tb_source_codes    溯源（row_code / resolved_from / 标准码 / 原始码）
```

### 分层与职责

| 层 | 位置 | 职责 |
|----|------|------|
| 共享件 | `backend/app/services/four_table/` | 科目定位 / 叶子聚合（已存在，本 spec 只消费） |
| 分类桶真源 | `four_table/f3_note_categories.py`、`f4_nature_buckets.py`、`f5_cost_segments.py` | 每循环一份声明式 dataclass，含 `source_ref` |
| render 策略 | `wp_render_strategies/_f{3,4,5}_*.py` | 纯函数 `build_*` + 一次查询，输出四个结构 |
| 前端科目真源 | `composables/f{3,4,5}AccountScope.ts` | 运行态取 render 下发的 `tb_source_codes`，常量只作兜底 |
| 前端消费 | `useF{3,4,5}Adjudication` + `F{3,4,5}FourTableSourcePanel.vue` | 预填（手工优先）+ 溯源展示 |
| 披露映射 | `composables/f{3,4}NoteSectionMap.ts` | 已存在，本 spec 增强动态行与账龄枚举 |
| 附注模板 | `backend/scripts/fix/fix_note_f_cycle_*.py` | 幂等脚本，只在复核发现不一致时改 |

### 溯源面板复用

平台已有共用件 `components/workpaper/shared/WpFourTableSourcePanel.vue` +
`composables/shared/tbSourceCodes.ts`（K2 spec 提升）。F3/F4/F5 各建薄壳传 props：
无备抵科目的循环不传 `provisionLabel` 即隐藏备抵行。**不再各造一份面板。**

### 两口径并列的展示设计

溯源面板新增一行「口径核对」：

```
叶子聚合口径   2201 期末  101,893,600.00   （2201.01 + 2201.02 + 2201.03）
trial_balance  2201 期末  101,893,600.00
差异                            0.00       ✓ 一致
```

差异非 0 时标 danger 并提示「试算平衡表可能未按最新口径重算，建议在数据管理页重跑」——
这样把范围外缺陷 G1/G2 暴露给审计师，而不是让底稿显示一个错数。

## Components and Interfaces

### 1. `four_table/f3_note_categories.py`（新建）

```python
@dataclass(frozen=True)
class F3Category:
    key: str                       # bank / commercial / letter_of_credit / supplychain / other
    label: str                     # 银行承兑汇票 / 商业承兑汇票 / 信用证 / 供应链票据 / 其他
    keywords: tuple[str, ...]      # 名称匹配关键字
    exclude_keywords: tuple[str, ...] = ()
    code_hints: tuple[str, ...] = ()   # 编码兜底（仅名称完全不含关键字时用）
    source_ref: str = ""           # 源 xlsx 单元格，如 '审定表F3-1!A7'
    always_show: bool = False      # 银行/商业承兑始终列示（源模板固定行）

F3_CATEGORIES: tuple[F3Category, ...]   # 顺序即优先级
def classify_f3_leaf(name: str, code: str) -> str
def f3_category_payload() -> list[dict]  # 下发前端，中文标签只一份
```

关键判定顺序：`信用证` 必须**先于**泛化匹配（源模板固定行只有银行/商业承兑，信用证走
第三类），`供应链` 独立一类（源模板 A11 法规括注专门讨论供应链票据）。

### 2. `four_table/f4_nature_buckets.py`（新建）

```python
F4_NATURE_BUCKETS: tuple[F4Bucket, ...] = (
    F4Bucket('goods',    '货款',   keywords=('货款','统购','采购'),
             source_ref='审定表F4-1!A8'),
    F4Bucket('project',  '工程款', keywords=('工程',),
             source_ref='审定表F4-1!A9'),
    F4Bucket('equipment','设备款', keywords=('设备',),
             source_ref='审定表F4-1!A10'),
    F4Bucket('service',  '服务费', keywords=('服务','劳务','运费','保养','维修'),
             source_ref='审定表F4-1!A11'),
    F4Bucket('other',    '其他',   keywords=(), is_catchall=True,
             source_ref='审定表F4-1!A12'),
)
```

**已知歧义（须留证）**：`2202.11 应付账款_工程设备款` 同时含「工程」与「设备」。声明顺序
把 `project` 置于 `equipment` 之前 → 归入「工程款」。理由：源模板 A9 工程款在 A10 设备款
之前，且该叶子无法拆分。溯源面板展示 `2202.11 应付账款_工程设备款 → 工程款`，审计师可在
审定表手工调整（预填只在无持久化时套用）。

**归类顺序铁律**：`暂估应付款` / `预提供应商返利` / `红字信息表` / `进项税` /
`商务系统` 均不含五桶关键字 → 落 `other` catchall，这是设计如此（它们不是采购性质分类，
而是客户内部核算科目），不得为凑数塞进货款。

### 3. `four_table/f5_cost_segments.py`（新建）

```python
F5_SEGMENTS: tuple[F5Segment, ...] = (
    F5Segment('main',  '主营业务成本',
              keywords=('主营业务成本','营业成本'),
              exclude_keywords=('其他业务',),
              source_ref='营业务成本审定表F5-1!A7'),
    F5Segment('other', '其他业务成本',
              keywords=('其他业务成本','其他业务支出'),
              source_ref='营业务成本审定表F5-1!A19'),
)
```

`exclude_keywords=('其他业务',)` 是必需的否决词：`其他业务成本` 含「业务成本」，若 `main`
的关键字含「业务成本」会误吃。实证 `6401` 名为「营业成本」或「主营业务成本」两种。

### 4. render 策略改造（三个文件同构）

每个策略新增纯函数（可独立单测，无 DB）：

```python
def build_f3_tb_values(leaves, tb_row) -> dict          # 双期 + 两口径
def build_f3_leaf_categories(leaves) -> list[dict]      # 叶子 → 桶（含未归类清单）
def build_f3_adjudication_prefill(categories) -> dict   # 按桶给期初/期末，空则 None
def build_f3_source_codes(accounts, parent_totals) -> dict   # 含 parent_check
```

删除的方言：`_F3_ACCOUNT` 硬编码常量作用降级为 `fallback_gross`；
`_fetch_f3_2201_tb_balance` 里的 `code.startswith(_F3_ACCOUNT)` 整段删除；
F5 的 `_ROLLFORWARD_ACCOUNTS` 前缀判定改共享件。

### 5. 前端科目真源 `f{3,4,5}AccountScope.ts`（新建，K2 范式）

```typescript
export const F3_REPORT_ROW_CODE = 'BS-044'
export const F3_GROSS_FALLBACK_STANDARD = '2201'
export function f3AccountCode(src?: TbSourceCodes | null): string
export function f3GrossQueryCodes(src?: TbSourceCodes | null): string[]
```

运行态一律取 render 下发的 `tb_source_codes.gross_standard`，常量只作兜底与展示。
守卫按文件参数化断言「源码不得出现 `'2201'` 作科目码/请求参数/事件载荷」。

### 6. 披露表增强

- **F3**：`orderF3ClassRows` 增加 `letter_of_credit` 档位，并接受 render 下发的
  `f3_category_payload` 决定哪些行列示（有金额或 `always_show` 才出行）。
- **F4 国企**：账龄行改由 `useAgingConfig` 的段驱动（现已部分支持，补齐 5 年段 / 自定义），
  文案走 `disclosureAgingLabels.ts` 单一真源（已存在）。
- **F4 上市**：按性质行接 `composables/shared/dynamicAdjudicationRows.ts`
  （K2 spec 建的平台共享件），支持增删改名；迁移时历史固定行 `rowId` 沿用旧 rowKey 保零丢数。

### 7. 附注模板复核脚本 `fix_note_f_cycle_extraction_alignment.py`（新建，可能空操作）

沿用共享 kit `backend/scripts/fix/_note_structure_kit.py`（`flat_columns` /
`two_period_columns` / `rule` / `run_section` / `build_cli`）。

**预期多数为空操作** —— 前序 spec 已对齐四章节。脚本存在的价值是：
① 用 `--check` 把「已对齐」这件事变成 CI 可验证的断言；
② 复核发现的任何不一致有落地入口。

## Data Models

### `tb_source_codes`（render 输出，前端消费）

```jsonc
{
  "row_code": "BS-044",
  "resolved_from": "report_config",        // 或 "fallback"
  "gross_standard": ["2201"],              // 标准码
  "gross": ["2201"],                       // 原始码前缀（极小前缀集）
  "formula": "TB('2201','期末余额')",
  "signed_codes": [["2201", 1]],
  "leaf_codes": ["2201.01", "2201.02", "2201.03"],
  "parent_check": {                        // 自证取数正确
    "leaf_sum_closing": 101893600.00,
    "parent_closing": 101893600.00,
    "diff": 0.00
  },
  "tb_cross_check": {                      // 暴露平台级 G1/G2 缺陷
    "leaf_closing": 101893600.00,
    "trial_balance_closing": 101893600.00,
    "diff": 0.00
  },
  "unmapped": []                           // 未归类叶子（宁缺勿造，不硬塞）
}
```

### `adjudication_prefill`（render 输出）

```jsonc
{
  "bank":             { "opening": 15000000.00, "closing": 8450000.00,
                        "codes": ["2201.01"], "label": "银行承兑汇票" },
  "letter_of_credit": { "opening": 40000000.00, "closing": 93443600.00,
                        "codes": ["2201.03"], "label": "信用证" }
}
```

无子科目时整体为 `null`（宁缺勿造）。金额已 `abs()` 归一。

### `tb_values`（render 输出，双期两口径）

```jsonc
{
  "2201":                 101893600.00,   // 兼容键：既有前端已在读，语义 = 期末权威值
  "2201_opening":          55000000.00,
  "2201_closing_leaf":    101893600.00,
  "2201_closing_tb":      101893600.00,
  "2201_opening_leaf":     55000000.00
}
```

**兼容性**：既有键 `tb_values['2201']` / `project_context.tb_amount` 保持不变，
前端 `useF3Adjudication.tbAmountSeed` / `useF4Adjudication.trialBalance` 零改动可用；
新键是增量。

### 分类桶归类结果（`leaf_categories`，供溯源面板逐叶子展示）

```jsonc
[
  { "code": "2201.01", "name": "应付票据_银行承兑汇票",
    "bucket": "bank", "bucket_label": "银行承兑汇票",
    "opening": 15000000.00, "closing": 8450000.00 },
  { "code": "2202.11", "name": "应付账款_工程设备款",
    "bucket": "project", "bucket_label": "工程款",
    "ambiguous": true,                       // 命中多桶，提示审计师复核
    "matched_buckets": ["project", "equipment"] }
]
```

## Correctness Properties

### Property 1: 叶子聚合等于父科目额

对任一项目、任一 F 类科目族，`select_leaves` 聚合结果（按方向带符号）等于该父科目在
`tb_balance` 中的余额；若不等，`parent_check.diff` 必须非零并被前端检出。

**Validates: Requirements 1.2, 2.2, 4.1**

### Property 2: 分类桶金额之和等于叶子合计

对任一项目，`adjudication_prefill` 各桶金额之和（期初、期末各自）等于该科目族叶子合计。
未归类叶子进 `unmapped` 并计入合计校验，不得静默丢弃。

**Validates: Requirements 1.4, 2.3, 3.3, 8.2**

### Property 3: 科目定位恒非空且标注来源

`resolve_report_line_accounts` 对 F3/F4/F5 的 spec 恒返回非空 `gross`；
`resolved_from` 为 `report_config` 或 `fallback` 二者之一，不得为空字符串。

**Validates: Requirements 1.1, 2.1, 3.1**

### Property 4: 归类顺序敏感性（反向自检）

打乱 `F4_NATURE_BUCKETS` / `F5_SEGMENTS` 的声明顺序后，至少一条已知样本的归类结果改变
（如 `其他业务成本` 被 `main` 桶吃掉、`工程设备款` 落入 `equipment`），
证明「顺序即优先级」这条约定确实生效而非空操作。

**Validates: Requirements 2.4, 2.5, 3.3, 8.1**

### Property 5: 符号约定归一

对同一份业务数据的正数存法与负数存法两种 fixture，`build_*_adjudication_prefill` 输出
逐字相等（均为正数口径）。

**Validates: Requirements 1.3, 2.2**

### Property 6: 损益类不得使用借贷相减

F5 取数函数对「`debit_amount == credit_amount` 的全年结转账」fixture 返回非零金额
（等于叶子 `debit_amount` 之和）；若实现改回 `debit - credit`，该测试必红。

**Validates: Requirements 3.2**

### Property 7: 手工优先，预填不覆盖

对已有持久化审定数的底稿，`adjudication_prefill` 不改变任何已录入值；
只对「四表有数据且该行无手工值」的桶写入。

**Validates: Requirements 1.4, 2.3, 3.4**

### Property 8: 公式预设科目码与报表行一致

F1~F5 每个预设块引用的科目码集合，必须是「该循环报表行公式引用的标准科目集合」的子集，
且每个码都存在于标准科目表；`AUX()` 的维度值不得是虚构占位（`TOP1` / `A类` / `长库龄`）。

**Validates: Requirements 5.1, 5.2, 5.3, 8.3**

### Property 9: 预设无成环

明细表块不得反向引用审定表块（`WP()` 有向图无环），且 sheet 名与源 xlsx tab 名逐字一致。

**Validates: Requirements 5.4, 5.5, 5.6, 5.7, 8.3**

### Property 10: 子表名与附注模板逐字一致

F1/F2/F3/F4 同步载荷的每个子表名存在于对应 `note_template_{listed,soe}.json` 的
`tables[].name`；同步 `columns` 的标签列 label 等于该表 `headers[0]`。

**Validates: Requirements 7.1, 7.2**

### Property 11: 动态区整表覆盖且清理孤儿

票据种类 / 账龄档位 / 性质行发生增删后再次同步，附注该章节的子表键集等于本次推送键集；
`_removed_table_keys` 与本次推送键无交集。

**Validates: Requirements 6.1, 6.2, 6.3, 7.3**

### Property 12: 列头三向一致

源 xlsx 表头（openpyxl 直读）、`note_template` 的 `headers`、同步载荷 `columns[].label`
三者逐字一致；单行表头的表必须显式标 `flat`（seed 与推送两侧都标）。

**Validates: Requirements 7.1, 7.2, 8.1**

### Property 13: 两口径差异必须可见

当 `trial_balance` 口径与叶子聚合口径差异超过容差时，`tb_cross_check.diff` 非零，
且前端溯源面板渲染 danger 状态；SHALL NOT 静默取其一。

**Validates: Requirements 1.7, 3.5, 4.1**

### Property 14: 无披露 sheet 的循环无披露 Tab

F0 / F5 在前端不存在 `*TabDisclosure*.vue` 组件、不存在 `f{0,5}NoteSectionMap.ts`，
且在平台守卫 `CYCLES_WITHOUT_DISCLOSURE` 中有登记依据。

**Validates: Requirements 7.5**

### Property 15: 前端契约完备

每个新增取数消费点：宿主模板已传 `:html-data` 与 `:project-id`；
composable 最外层 `return {}` 的键集 ⊇ 组件解构键集；
`buildXColumns` 零入参可调且返回完整列集。

**Validates: Requirements 8.4**

## Error Handling

**fail-open 铁律**：取数链路任一环失败（`report_config` 无该行 / `account_chart` 空 /
`account_mapping` 空 / DB 异常）一律回退到 spec 的兜底码，在 `resolved_from` 标注
`fallback`，绝不阻断 render。这是 `four_table` 共享件既有行为，本 spec 只消费。

| 失败点 | 处理 | 用户可见效果 |
|--------|------|--------------|
| 报表行公式缺失 | 回退 `fallback_gross` | 溯源面板显示「兜底科目」标记 |
| `account_mapping` 无记录 | 标准码降级为一级前缀 | `provision_exact=False`，需叠名称过滤 |
| 叶子聚合与父额不等 | `parent_check.diff` 非零 | 溯源面板 danger + 提示核查科目映射 |
| `trial_balance` 与叶子不等 | `tb_cross_check.diff` 非零 | 溯源面板 danger + 提示重跑 recalc |
| 叶子名未命中任何桶 | 进 `unmapped`，**不硬塞 catchall 以外的桶** | 溯源面板列出未归类叶子 |
| 无子科目 | `adjudication_prefill = None` | 审定表回退手工录入，TB 核对行仍有总额 |
| 归类命中多桶 | 取首个 + `ambiguous=true` | 溯源面板黄色提示，审计师可手工调整 |

**前端**：预填一律「手工优先」——已有持久化值不覆盖。`seedFromPrefill({overwrite})` 在
四表数据有变化时弹确认（可选「仅补空值」），历史手工录入永不被静默改写。

**同步失败**：`_removed_table_keys` 只删「上次由本底稿推过」的表（与
`previouslySyncedTables` 求交集），越权删会打断同章节其它底稿。同步失败时不 `markSynced`。

## Testing Strategy

### 后端

| 文件 | 覆盖 |
|------|------|
| `backend/tests/four_table/test_f3_account_scope.py` | Property 1~5, 7；含反向自检 |
| `backend/tests/four_table/test_f4_nature_buckets.py` | Property 2, 4；两变体参数化 + PBT |
| `backend/tests/four_table/test_f5_cost_segments.py` | Property 4, 6；结转账 fixture |
| `backend/tests/test_f_cycle_account_codes.py` | Property 8（码 ∈ 标准科目表 ∧ ∈ 本循环报表行） |
| `backend/tests/test_f_cycle_formula_presets.py` | Property 8, 9（语法 / 成环 / sheet 名） |
| `backend/tests/test_note_f_cycle_structure.py` | Property 10, 12（openpyxl 三向比对 + 反向自检） |

**测试替身铁律**（D1 已踩）：fake session 必须按 SQL/params 区分同一张表的多次查询
（F3/F4 render 会分别查 `tb_balance` 与 `trial_balance`），否则两次返回同一行会让守卫变噪声。
`get_active_filter` 的 mock 返回值必须是真实 `sa.true()`，不能是 `MagicMock()`
（否则 `sa.and_` 拒绝后被 fail-open 吞成空 = 假绿）。

### 前端

| 文件 | 覆盖 |
|------|------|
| `composables/__tests__/f3AccountScope.spec.ts` | 科目字面量清零 + 运行态取 render 值 |
| `composables/__tests__/f4NatureRows.spec.ts` | Property 7, 11；动态行迁移零丢数 |
| `composables/__tests__/fCycleNoteSubtableContract.spec.ts` | Property 10, 12（共享 helper P1~P6） |
| `composables/__tests__/fCycleHostPropWiring.spec.ts` | Property 15（扫宿主模板 + 解构键集比对） |

读源码型守卫必须先 `stripComments()` 并配反向自检（断言原始源码确实含被禁字样），
否则守卫注释里的反例会被数成真实调用、或正则失效导致断言空转。

### 实测（Property 13, 11 的最终裁决）

1. **真实 DB 直跑 render**：对 `0ec33ac9`（有信用证大额）、`2aa00f57`（负数存法 +
   `trial_balance` 双算）、`c8621493`（数据稀疏）三个项目分别跑 F3/F4/F5 的 render，
   逐项核对 `parent_check.diff == 0`、`tb_cross_check` 差异被检出、桶之和 == 叶子合计。
2. **浏览器实测**：F3/F4 披露 Tab 录入 → 不点按钮验自动同步 → `postgres` 只读核对
   `disclosure_notes.table_data` 的子表键集 / 列元数据 / `_column_groups` / `last_sync_at`。
3. **数据复原**：实测前捕获完整快照，实测后逐字复原（含 `last_sync_at` 回 NULL）。

### 已知不可测项

- **上市变体无活体**：在册项目 `entity_type` 多为 soe，上市侧披露 Tab 被
  `applicable_standards` 门控关闭 → 上市侧只能靠契约测试 + 后端守卫双向锁死，
  不做浏览器实测（不为测试临时改项目准则，会污染数据）。
- **范围外缺陷 G1/G2** 的修复效果无法在本 spec 验证（需重跑 recalc + 改
  `trial_balance_service`），本 spec 只验「差异被正确检出并展示」。
