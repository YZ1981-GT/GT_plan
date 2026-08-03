# Design Document

## Overview

本设计把 L 类 8 个循环的四表取数收敛到平台既有共享件 `app/services/four_table/`，纠正三处 P0 科目缺陷与一处整块错位的公式预设，并按源 xlsx 重建/对齐 10 个附注章节的表结构与两版披露表。

设计遵循平台既有范式，不新建机制：

- 取数：`resolve_report_line_account_codes`（报表行 → 标准码 → `account_mapping` 反解 → 原始码前缀）+ `select_leaves` / `aggregate_leaves`
- 分类：per-cycle 声明式分类器（名称优先 + 否决词 + 编码兜底），单一真源
- 科目字面量：per-cycle `xAccountScope.ts`，运行态取 render 下发的 `tb_source_codes`
- 附注模板：幂等脚本 + `_note_structure_kit` 共享工具
- 两级表头：`ColumnDef.group` → `_column_groups`，seed 与推送两处同时表态
- 同步：`useDisclosureAutoSync` + `buildXSyncPayload` + `_removed_table_keys`

## Architecture

### 取数链路（四表入库 → 底稿有数据）

```
tb_balance.account_code (客户原始码, 点号分层)
        │  account_mapping
        ▼
trial_balance.standard_account_code (标准码, 横杠)
        │  report_config.formula (按 applicable_standard)
        ▼
report_line row_code (BS-044 / IS-007 ...)
        │  resolve_report_line_account_codes(row_code, standards)
        ▼
标准码集合 → account_mapping 反解 → 原始码前缀集合
        │  select_leaves (点号边界)
        ▼
叶子行 → 分类器 → adjudication_prefill / tb_values / tb_source_codes
        │  render html_data
        ▼
前端 xAccountScope + 「从四表库带入未审数」+ 溯源面板
```

### 披露 → 附注链路

```
披露 Tab 录入 → watch 实际数据 → useDisclosureAutoSync(800ms)
        │  buildXSyncPayload(variant)
        ▼
POST /disclosure-notes/sync-from-workpaper
   { note_section, sheet_name, sub_table_data, _sub_table_columns, _note_texts, _removed_table_keys }
        │  detect_standard_conflict 守卫（entity 维度）
        ▼
disclosure_notes.table_data → note_sub_table_projector 读时投影
        ▼
附注编辑页 / Word 导出（两级表头同源）
```

### 章节路由（含两版不对称）

| 循环 | listed 目标 | soe 目标 | payload 数 |
| --- | --- | --- | --- |
| L1 | 五、33 | 八、33 | 1 / 1 |
| L2 | K3 五、42 子表 | K3 八、42 子表 | 豁免（K3 承载） |
| L3 | 五、45 + 五、43 子表 | 八、49 + 八、45 | 2 / 2 |
| L4 | 五、46 + 五、43 子表 | 八、50 + 八、46 | 2 / 2 |
| L5 | 五、48 | 八、53 + 八、47 | 1 / 2 |
| L6 | 五、48 子表 | 八、53 子表 | 1 / 1（浅合并） |
| L7 | 五、52 | 八、57 | 1 / 1 |
| L8 | 五、67 | 八、68 | 1 / 1 |

## Components and Interfaces

### 后端新增/改造

`backend/app/services/l_cycle_extraction/account_scope.py`（新建）

```python
@dataclass(frozen=True)
class LCycleSpec:
    wp_code: str
    row_code_listed: str | None      # 报表行编码（上市）
    row_code_soe: str | None
    fallback_codes: tuple[str, ...]  # 报表行解析落空时的兜底
    kind: Literal["balance", "income"]
    current_portion_keywords: tuple[str, ...] = ()   # 一年内到期识别词
    prefill_buckets: tuple[LBucket, ...] = ()

L_CYCLE_SPECS: dict[str, LCycleSpec]   # L1..L8 单一真源
def resolve_l_scope(wp_code, standards) -> ResolvedScope
def classify_l_leaf(wp_code, code, name) -> str          # 名称优先 + 否决词
def is_current_portion(name) -> bool                     # 一年内到期判定
```

`backend/app/routers/wp_render_strategies/_lmn_tb_helper.py`（改造）

- 删 `_is_leaf`（缺点号边界），委托 `four_table.leaf_aggregation.select_leaves`
- `fetch_tb_for_balance(ctx, codes: Sequence[str])` 入参改科目码集合
- `fetch_tb_for_income` 改 `trial_balance` 本期发生额优先 + `tb_balance.debit_amount` 兜底，删 `debit - credit`
- 新增 `build_tb_source_codes(...) -> dict`

`_l1..._l8` 各 render：改走 `resolve_l_scope`，输出 `tb_source_codes` / `adjudication_prefill` / `current_portion`

### 前端新增/改造

- `composables/l{1,3,4,5,6,7,8}AccountScope.ts`：科目字面量单一真源，运行态读 `tb_source_codes`
- `composables/lCycleFourTableSeed.ts`：审定表/披露表共用 seed 纯函数
- `composables/l{1,3,4}NoteSectionMap.ts`：新建/重写，含 `X_NOTE_SECTION` / `X_DISCLOSURE_SHEET_NAME` / `X_LEGACY_OBSOLETE_TABLES`
- `composables/l4ListedDisclosureModel.ts`：应付债券变动引擎（动态债券行 + 派生期末）
- `L{1,3,4}TabDisclosure{Listed,Soe}.vue`：按源模板重建列结构、接自动同步
- 复用 `shared/WpFourTableSourcePanel.vue` / `shared/dynamicAdjudicationRows.ts` / `disclosureAgingLabels.ts`

### 脚本

- `backend/scripts/fix/fix_note_l1_short_term_loans_structure.py`
- `backend/scripts/fix/fix_note_l3_l4_structure.py`（含 五、43 / 八、44~46）
- 复用 `_note_structure_kit`（`flat_columns` / `two_period_columns` / `rule` / `run_section` / `build_cli`）

## Data Models

### `tb_source_codes`（render → 前端）

```ts
interface LTbSourceCodes {
  wp_code: string
  report_row_code: string | null
  gross_standard: string[]        // 标准码
  gross_query: string[]           // 反解后的客户原始码前缀
  resolved_from: 'report_config' | 'fallback'
  current_portion_codes: string[] // 一年内到期叶子
  leaf_total: number
  parent_check: { parent_code: string; parent_amount: number; diff: number }
  unmapped: string[]
}
```

### `adjudication_prefill`（render → 审定表）

```ts
type LAdjudicationPrefill = Record<string, {
  bucket_key: string
  label: string
  opening: number
  closing: number
  account_codes: string[]
}>
```

### 披露载荷（前端 → 后端）

```ts
interface LSyncPayload {
  note_section: string
  sheet_name: string             // 源 xlsx tab 名逐字
  sub_table_data: Record<string, Array<Record<string, unknown>>>
  _sub_table_columns: Record<string, ColumnDef[]>
  _note_texts: Array<{ section: string; title: string; text: string }>
  _removed_table_keys: string[]
}
```

### 源 xlsx 披露 sheet 名（实证，禁"修正"）

| 循环 | listed | soe |
| --- | --- | --- |
| L1 | 附注披露信息核对（上市公司） | 附注披露信息核对（国企） |
| L2 | 附注披露（上市公司）信息 | 附注披露（国企）信息 |
| L3 | 附注披露信息核对（上市公司） | 附注披露（国企）信息核对 |
| L4 | 附注披露信息核对（上市公司） | 附注披露信息核对（国企） |
| L5 | 附注披露信息（上市公司） | 附注披露信息（国企） |
| L6 | 附注披露（上市公司）信息 | 附注披露（国企）信息 |
| L7 | 附注披露信息（上市公司） | 附注披露信息(国企) |
| L8 | 附注披露信息（上市公司） | 附注披露信息（国企） |

## Correctness Properties

### Property 1: 叶子聚合守恒

对任一循环，`select_leaves` 结果的金额之和等于该科目父行金额（容差 0.01 元）；分类桶金额之和等于叶子合计。

**Validates: Requirements 1.5, 3.5**

### Property 2: 科目码属本循环

每个循环解析出的标准码集合，均属该循环报表行公式引用的科目集合；兜底码存在于标准科目表。

**Validates: Requirements 1.1, 5.2, 11.3**

### Property 3: L8 非零性

在 `debit == credit` 的结转损益账套下，L8 取数结果不为 0，且等于 `trial_balance` 本期发生额。

**Validates: Requirements 2.4, 2.5**

### Property 4: 灰度关闭等价

`LMN_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，L1~L8 render 输出与本 spec 改动前逐字节等价。

**Validates: Requirements 10.2**

### Property 5: 手工优先

审定表存在持久化值时，任何自动预填路径不覆盖该值；`seedFromPrefill` 仅覆盖四表命中行。

**Validates: Requirements 4.2, 4.3**

### Property 6: 分类器否决词生效

分类器对「名称同时含 A 桶与 B 桶关键字」的叶子，按否决词判定归属；打乱规则顺序会使至少一条用例失败（反向自检）。

**Validates: Requirements 3.4**

### Property 7: 子表名逐字一致

每个循环载荷声明的子表名，均存在于对应变体附注模板的 `tables[].name`；标签列头等于该表 `headers[0]`。

**Validates: Requirements 8.2, 7.3**

### Property 8: 列元数据双侧表态

每张表的 `columns` 在 seed（模板 JSON）与推送（载荷）两处均显式表态 `flat` 或 `group`；单级表不得声明 `group`。

**Validates: Requirements 6.2, 6.3, 7.4**

### Property 9: 源模板三向比对

openpyxl 直读源 xlsx 的表名与末级列名，与附注模板 `headers`、载荷 `columns` 三者一致；反向自检断言源文件确实被读取。

**Validates: Requirements 6.1, 11.1**

### Property 10: 幂等性

附注修订脚本连续执行两次，第二次 `--check` 报 0 项欠账；`apply_plan` 对已修订章节为空操作。

**Validates: Requirements 7.1**

### Property 11: 孤儿表清理求差集

`_removed_table_keys` 与本次推送的表名集合无交集，且仅包含「曾由本底稿推送」的表名。

**Validates: Requirements 8.4**

### Property 12: 账龄枚举贯通

披露表账龄行由项目账龄配置驱动；3 年段项目不出现 5 年段行键，自定义段落按配置输出。

**Validates: Requirements 6.5**

### Property 13: 公式预设无环且标签正确

审定表块可引用明细表，明细表块不引用审定表；每个块的 `wp_name` 与 `account_codes` 与该 wp_code 真实科目一致；sheet 名存在于源 xlsx tab 名集合。

**Validates: Requirements 5.1, 5.4, 5.5, 5.6**

### Property 14: 一年内到期拆分守恒

「非流动部分 + 一年内到期部分」等于该科目叶子合计；一年内到期金额不等于应付债券金额（排除 BS-057 撞码口径）。

**Validates: Requirements 3.1, 3.5**

## Error Handling

- 报表行解析异常 / DB 异常：fail-open，`tb_source_codes.resolved_from='fallback'` + `logger.warning`，不阻断 render
- `account_mapping` 反解落空：退化为标准码前缀查询，并在 `unmapped` 记录
- 分类器未命中：归入 `other` 桶，不丢弃金额
- 披露同步 409 `STANDARD_MISMATCH`：前端静默（宁可不写也不写错章节）
- 附注脚本 `--apply` 失败：per-section savepoint 隔离，记 failures 后继续

## Testing Strategy

- 后端单测：`backend/tests/l_cycle_extraction/`（分类器参数化 + PBT + 反向自检）
- 后端结构守卫：`test_note_l1_structure.py` / `test_note_l3_l4_structure.py`（openpyxl 三向比对）
- 后端预设守卫：`test_l_cycle_formula_presets.py`（科目码属本循环 + 无环 + sheet 名）
- 前端契约：`lCycleNoteSubtableContract.spec.ts` 接入共享 helper P1~P6 + 本 spec 专属断言
- 前端接线守卫：`lCycleFourTableWiring.spec.ts`（科目字面量清零 + 溯源面板消费 + 自动同步 watch 目标）
- 实测：真实 DB 直跑 render + chrome-devtools 浏览器往返 + postgres 只读复核，测试数据用后复原
