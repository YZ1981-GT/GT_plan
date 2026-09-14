# Design Document

## Overview

本设计把 J 类（J1/J2/J3）的取数与披露链路收敛到平台既有共享件，并按源 xlsx 重建 J2 两版披露/附注结构。

核心判断三条：

1. **J2 是「取错整个科目族」级 P0**（`2221` 应交税费 → `2705` 长期应付职工薪酬），修法与 K2（`1231`→`1901`）、D6（`1402`→`1141`）同款：科目走报表行解析 + per-cycle 单一真源，常量只作兜底。
2. **J1/J2 的客户子科目天然对应披露行**，这是「四表入库后底稿即有数」的基础，无需臆造分类。
3. **J2 两版披露结构本质不同**（上市 3 张纵表 vs 国企 1 张 7 列横表），现附注模板把上市结构抄进了国企 → 删表而非补载荷。

## Architecture

```
tb_balance.account_code (客户原始码, 点号/平铺)
   │  account_mapping
   ▼
trial_balance.standard_account_code (标准码, 横杠)
   │  report_config.formula  ← 按 applicable_standard 挑
   ▼
报表行  J1: BS-051(listed) / BS-069(soe) = TB('2211','期末余额')
        J2: BS-067(listed) / BS-093(soe) = NULL → 兜底 2705
   │
   ▼  four_table/report_line_accounts.resolve_report_line_accounts
   ▼  four_table/leaf_aggregation.select_leaves + aggregate_leaves
   ▼
render 输出: tb_values / adjudication_prefill / detail_prefill / tb_source_codes
   │
   ▼  前端 composable（科目码只从 tb_source_codes 取）
J1-1/J2-1 审定表  ←→  J1-2/J2-2 明细表  →  披露 Tab
                                            │ buildJxSyncPayload
                                            ▼  sync-from-workpaper
                          附注 五、40/八、40 (J1)
                               五、49/八、54 (J2)
                               五、17        (J2 净资产分支, listed only)
```

### 变体相关的报表行选择

平台既有 `ReportLineAccountSpec.row_code` 是单值，而 J 类**两变体报表行编码不同**（J1 `BS-051`/`BS-069`；J2 `BS-067`/`BS-093`）。
本设计**不改共享件**，改在 per-cycle 模块内按 `fetch_applicable_standards(ctx)` 的结果挑 spec：

```python
J1_SPEC_BY_ENTITY = {
    "listed": ReportLineAccountSpec(row_code="BS-051", fallback_gross=("2211",)),
    "soe":    ReportLineAccountSpec(row_code="BS-069", fallback_gross=("2211",)),
}
```

理由：`resolve_report_line_accounts` 的末级回退是「任取一条非 project 配置」，两版公式恰好相同（都是 `TB('2211')`）故当前不会出错，
但语义上是巧合；显式按变体挑 spec 消除这个巧合，且不给共享件增加只有 J 类需要的字段。若后续 ≥3 个循环出现同形态，再提升为共享件字段。

## Components and Interfaces

### 后端新增/改造

| 文件 | 动作 | 要点 |
|---|---|---|
| `app/services/four_table/j_cycle_account_scope.py` | **新建** | `J1_SPEC_BY_ENTITY` / `J2_SPEC_BY_ENTITY` / `J1_CATEGORY_RULES`（dataclass，含 `source_ref`）/ `classify_j1_leaf()` / `classify_j2_leaf()` / `pick_spec(standards)` |
| `wp_render_strategies/_j1_employee_compensation.py` | 重写取数段 | 删 `ACCOUNT_CODE` 硬编码、删 `by_level` 最深层级、删无条件 `abs()`；改 `resolve_report_line_accounts` + `select_leaves`；新增纯函数 `build_j1_tb_values` / `build_j1_adjudication_prefill` / `build_j1_detail_prefill` / `build_j1_source_codes` |
| `wp_render_strategies/_j2_defined_benefit_plan.py` | 重写取数段 | `2221`→报表行解析（兜底 `2705`）；删自造 `_is_leaf`（缺点号边界）；同上四个纯函数 |
| `scripts/fix/fix_note_j1_compensation_structure.py` | **新建** | 幂等脚本：五、40 列头改上市口径 + 补 `……` 行 + 「其中：」序号；八、40 短期薪酬 12 行 4 项 |
| `scripts/fix/fix_note_j2_dbp_structure.py` | **新建** | 幂等脚本：八、54 删 2 表 / 表名与 group 正名 / 补 3 行；五、49 补 2 行；五、17 补 columns+guidance；八、54 交叉引用改 八、40 |
| `scripts/fix/fix_j_cycle_prefill_presets.py` | **新建** | 幂等脚本：J2 `2611`→`2705`；J1 `分析程序J1-3`→`调整分录汇总表J1-3`；J3 `审定表J3-1`→`股份支付情况表J3-1` + 科目改 `4001/4002`；删 12 条硬编码成本中心 AUX；补 `WP()` 联动；补两版披露 sheet 块 |

复用共享件（不新建）：`four_table/report_line_accounts`、`four_table/leaf_aggregation`、`scripts/fix/_note_structure_kit`。

### 前端新增/改造

| 文件 | 动作 | 要点 |
|---|---|---|
| `composables/jAccountScope.ts` | **新建** | 科目单一真源：`J1_REPORT_ROW_BY_VARIANT` / `J2_REPORT_ROW_BY_VARIANT` / `J1_GROSS_FALLBACK='2211'` / `J2_GROSS_FALLBACK='2705'` / `jGrossQueryCodes(src)` / `jAccountCode(src)`；运行态一律取 `tb_source_codes.gross_standard` |
| `composables/j1NoteSectionMap.ts` | 改 | 列定义按变体拆：`j1ListedColumns()`（`上年年末数`/`期末数`）/ `j1SoeColumns()`（`期初余额`/`期末余额`）；`buildJ1ListedColumns` / `buildJ1SoeColumns` 零入参 |
| `composables/j2DisclosureSyncPayload.ts` | 改 | `J2_SOE_SUBTABLE.change` 表名 → `设定受益计划情况`；group / 叶子 label 正名；删 soe 侧对已删表的引用；`J2_LEGACY_OBSOLETE_TABLES` + `_removed_table_keys`；新增 `buildJ2NetAssetPayload()`（五、17，净资产分支） |
| `composables/j2NoteSectionMap.ts` | 改 | 补 `J2_NET_ASSET_NOTE_SECTION = { listed: '五、17', soe: null }` |
| `composables/shared/dbpDynamicRows.ts` | **新建** | J2 动态插行纯函数（零 Vue 依赖）：`DbpDynamicSpec` 声明可扩位、稳定 key `{group}_{seq}`、父行 SUM 派生 |
| `j1/core/J1TabDisclosureListed.vue` / `...Soe.vue` | 改 | 接 `J1FourTableSourcePanel`；「从四表库带入未审数」 |
| `j2/J2TabDisclosureListed.vue` / `...Soe.vue` | 改 | 接动态插行 + 溯源面板 + 净资产分支推送 + `WpAmountInput` |
| `j1/core/J1TabAdjudication.vue` / `j2/J2TabAdjudication.vue` | 改 | 「从四表库带入未审数」+ 溯源面板 + 刷新取数（科目码优先匹配） |
| `shared/WpFourTableSourcePanel.vue` | 复用 | J 类无备抵科目 → 不传 `provisionLabel`（面板自动隐藏备抵行） |

### 守卫

| 文件 | 覆盖 |
|---|---|
| `backend/tests/four_table/test_j_cycle_account_scope.py` | 报表行按变体挑选 / 叶子口径 / 分类规则顺序敏感性 / 反向自检（旧口径确实命中税种行）|
| `backend/tests/test_note_j1_structure.py` | openpyxl 直读 J1 源 xlsx 三向比对（列头两版必须不同 / 八、40 四项 / 五、40 `……` 行在位）|
| `backend/tests/test_note_j2_structure.py` | openpyxl 直读 J2 源 xlsx；八、54 表数=6 且无同名表；group/叶子 label 逐字；行集含补齐的 3 行；敏感性两版用语不得统一 |
| `backend/tests/test_j_cycle_formula_presets.py` | 科目码 ∈ 标准科目表 ∧ ∈ 本循环报表行科目集；sheet 名 ∈ 源 xlsx tab 名；无硬编码成本中心；明细表禁 `WP()` |
| `frontend/.../__tests__/jAccountScope.spec.ts` | 源码级：J1/J2 组件不得出现 `'2221'`/`'2611'`/`'2705'` 作请求参数或事件载荷 |
| `frontend/.../__tests__/j2NoteSubtableContract.spec.ts` | 扩展：P1~P6 全量真断言 + 两级 group + 净资产分支 |
| `frontend/.../__tests__/dbpDynamicRows.spec.ts` | 动态插行纯函数 + PBT（key 唯一 / 父行 = Σ子行 / 删行后合计变化）|
| `frontend/.../__tests__/jMaturityBandsNotAging.spec.ts` | **反向锁死**：到期分析 4 档不得引用账龄枚举模块 |

## Data Models

### `J1CategoryRule`（后端，声明式单一真源）

```python
@dataclass(frozen=True)
class J1CategoryRule:
    key: str                       # 'short_term' | 'defined_contribution' | 'severance' | 'other_long_term'
    label: str                     # 中文标签（源 xlsx 逐字）
    keywords: tuple[str, ...]      # 科目名匹配词（顺序即优先级）
    exclude_keywords: tuple[str, ...] = ()
    code_segments: tuple[str, ...] = ()   # 2211 二级段兜底：('01',) / ('02','07')
    source_ref: str = ""           # 'J1!附注披露信息（上市公司）!A7'
```

顺序敏感性：`辞退` 必须先于 `短期`（`2211.01.99.05 辞退经济补偿` 含「短期薪酬」父名）；
`设定受益` 必须先于 `设定提存`（前者属 J2，J1 侧应否决）。

### `tb_source_codes`（render 输出，前端溯源面板消费）

```
{ gross: ['2211'], gross_standard: ['2211'], provision: [], provision_standard: [],
  signed_codes: [['2211', 1]], formula: "TB('2211','期末余额')",
  row_code: 'BS-069', resolved_from: 'report_config',
  provision_resolved_from: 'fallback', provision_exact: false }
```

### `DbpDynamicSpec`（前端动态插行声明）

```ts
interface DbpDynamicSpec {
  group: string              // 'equity' | 'debt' | 'dbo_other' | 'asset_other' | 'assume'
  parentKey: string | null   // 父行 key（SUM 派生）；null = 无父行
  defaultLabel: string       // 源模板默认名（'1、……' 等）
  minRows: number            // 源模板预留位数
}
```

## Correctness Properties

### Property 1: 报表行按变体解析且兜底非空
对任意项目与变体，`resolve_report_line_accounts` 返回的 `gross` 恒非空；listed 命中 `BS-051`/`BS-067`，soe 命中 `BS-069`/`BS-093`；公式为 NULL 时 `resolved_from == 'fallback'` 且 `gross_standard == ('2211'|'2705')`。

**Validates: Requirements 1.1, 1.4, 2.1**

### Property 2: 叶子和等于父额
对任意项目，`select_leaves` 聚合出的各叶子期末金额之和 == 父科目（`2211` / `2705`）期末金额，误差 < 0.01。参差科目树与四级科目均不丢段。

**Validates: Requirements 1.3, 2.1, 2.2**

### Property 3: 符号保留
存在借方性质负余额叶子时，聚合结果保留符号；套 `abs()` 会使 Property 2 不成立（守卫用该反例反向自检）。

**Validates: Requirements 2.4**

### Property 4: 分类规则顺序敏感
打乱 `J1_CATEGORY_RULES` 顺序后，至少一个已知叶子（`2211.01.99.05 辞退经济补偿`）被归错类 —— 证明顺序即优先级不是巧合。

**Validates: Requirements 3.1, 3.2**

### Property 5: 科目码零字面量
J1/J2 前端源码（`stripComments()` 后）不含 `'2211'` / `'2705'` / `'2221'` / `'2611'` 作请求参数、事件载荷或查询码；常量仅出现在 `jAccountScope.ts` 的兜底声明处。

**Validates: Requirements 3.3, 3.4, 1.5**

### Property 6: 预设科目码双重合法
每条 J 类预设的科目码同时满足：① ∈ `account_chart` 标准科目表；② ∈ 本循环报表行公式引用的科目集合。`2611` 违反 ①，`2221` 违反 ②。

**Validates: Requirements 4.1, 4.6**

### Property 7: 预设 sheet 名存在
每条 J 类预设的 `sheet` ∈ 对应源 xlsx 的 `wb.sheetnames`（含尾空格差异按逐字比对）。`分析程序J1-3` 与 `审定表J3-1` 违反。

**Validates: Requirements 4.2, 4.3**

### Property 8: 两变体列头必须不同
J1 主表列定义 listed ≠ soe（`上年年末数`/`期末数` vs `期初余额`/`期末余额`）；J2 敏感性分析末列 listed(`计划负债减少`) ≠ soe(`计划负债减小`)。

**Validates: Requirements 5.1, 5.2, 6.7**

### Property 9: 附注表名唯一
任一附注章节内 `tables[].name` 互不重复（八、54 删 2 表后 `计划资产` 唯一）；同步载荷 `sub_table_data` 的键集 ⊆ 模板表名集。

**Validates: Requirements 6.1, 6.2**

### Property 10: 三向行集一致
源 xlsx 数据行标签（归一化去空格/NBSP/序号差异后）≡ 模板 `rows[].label` ≡ 同步载荷行标签。J1 八、40 短期薪酬为 12+1 行 4 项「其中：」；J2 八、54 的 7 列表为 16 行。

**Validates: Requirements 5.3, 5.4, 5.5, 6.4, 6.5, 6.6**

### Property 11: 动态行 key 唯一且父行派生
任意增删序列后，动态行 key 全局唯一（不用 label 作 key）；父行金额 == Σ 子行；删除子行后父行随之变化；载荷不含已删行。

**Validates: Requirements 7.1, 7.3, 7.4, 7.5**

### Property 12: 净资产分支互斥且不误删
J2-1 净负债表期末 > 0（净负债）时不推 五、17；< 0（净资产）时上市侧推 五、17；国企侧恒不推。任一情形下都不把 五、49/八、54 的表键放进 五、17 的 `_removed_table_keys`。

**Validates: Requirements 8.2, 8.3, 8.4**

### Property 13: 到期分析不是账龄
「未折现的离职后福利预计到期分析」档位恒为源模板 4 档（一年以内/一到两年/二到五年/五年以上），不随项目账龄配置（3 年段/5 年段/自定义）变化；源码不引用 `disclosureAgingLabels` / `useAgingConfig`。

**Validates: Requirements 10.5**

### Property 14: 刷新取数手工优先
对已有手工录入的行执行「刷新取数」后，该行金额不变；仅四表新增叶子会插新行；已有四表行金额变化时需用户确认。

**Validates: Requirements 9.2, 9.3**

## Error Handling

全链 fail-open，任一环失败都不阻断 render：

| 环节 | 失败表现 | 处置 |
|---|---|---|
| `fetch_applicable_standards` | 项目无 `applicable_standard_v2` | 返 `[]`，`pick_spec` 取 soe（活体全 soe） |
| `resolve_report_line_accounts` | `report_config` 无该行 / 公式 NULL | 回退 `fallback_gross`，`resolved_from='fallback'` |
| `account_mapping` 反解 | 无映射记录 | 退化为标准码一级段前缀，`*_exact=False` |
| `tb_balance` 查询 | DB 异常 | `logger.warning` + 返空预填，底稿走手工录入 |
| 叶子聚合为空 | 科目族无数据（`2705` 活体多为 NULL） | 返空预填（宁缺勿造），不回退其它科目族 |
| 附注推送 409 `STANDARD_MISMATCH` | 跨主体类型推送 | 前端静默吞（宁可不写也不写错章节） |
| 净资产分支判定不确定 | 净负债表期末为 0 | 视为净负债，不推 五、17，不删该章内容 |

守卫要求：`get_active_filter` 的 mock 必须返回真实 `sa.true()`（`MagicMock` 会被 `sa.and_` 拒绝后被 fail-open 吞成空 = 假绿）。

## Testing Strategy

三层，逐层收窄：

1. **纯函数单测（无 DB）** —— `classify_j1_leaf` / `classify_j2_leaf` / `build_*_prefill` / `dbpDynamicRows`。
   含 PBT（hypothesis，`max_examples=5`）：叶子和守恒、动态行 key 唯一、父行 = Σ子行。
2. **源码级契约守卫** —— openpyxl 直读源 xlsx 做三向比对（源 ↔ 模板 ↔ 载荷）；前端正则守卫先 `stripComments()` 且配反向自检。
   所有幂等脚本提供 `--check` 并挂 CI。
3. **真实数据 / 浏览器实测** —— 单测替身与错误假设同构时全绿也查不出（G7 备抵方向即前例）：
   - 真实 DB 直跑 render 三个项目，验 `resolved_from` / 叶子和 == 父额 / 空科目返空
   - chrome-devtools 驱动浏览器 + postgres 只读比对落库（`sub_table_data` 键集 / `_sub_table_columns` / `last_sync_at` 前移）
   - 测试数据实测后逐字复原

预存在基线：前端 `src/views/composables/__tests__` 9 例 / 5 文件失败与本 spec 无关，不计入回归。
