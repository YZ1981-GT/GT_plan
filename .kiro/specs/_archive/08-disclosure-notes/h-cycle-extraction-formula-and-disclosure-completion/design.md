# Design Document

## Overview

本 spec 修复 H 类（H0~H10 共 11 个循环）「四表入库 → 底稿取数 → 披露表 → 附注模块」全链上的 6 类缺陷。

**设计立足点：不重建，只补缺口。** H 类后端语义定位骨架已完整（10 个 `h{n}_account_scope.py` + `h_cycle_specs.py` + 11 个 render 全部已调 `resolve_semantic_accounts`），前序 5 个已归档 spec 已把主章节附注对齐。本 spec 只做四件事：

1. **双族并取**（R1）—— 用加法式公式同时覆盖旧族 `1641/1642/1643/2601/2602` 与新族 `1651/1652/2651`，不改任何既有码
2. **注册缺失列名**（R2）—— `本期借方`/`本期贷方` 进 `COLUMN_ALIASES` + `tb_data` 产出该列 + 未知列改 fail-loud
3. **补四个 prefill + 修错块**（R3/R4/R5）—— H1/H2/H3/H4 的 `adjudication_prefill`、H3 贴错的公式块、硬编码项目号、H10 损益口径、`WP()` 联动
4. **会计政策章处置 + 收尾**（R7~R12）—— 政策表补列 / 重复落章处置 / 溯源面板 / 金额控件 / 账龄禁引 / 库龄点选

### 关键设计判断（三条，均有实证支撑）

**判断 1：双族用「加法」而非「改码」**

实证（`trial_balance` 9 项目逐项目）：两族在同一项目内**互斥**，唯一两族都有记录的项目 `0ec33ac9` 双方均为 `0.00`。故 `TB('1641')+TB('1651')` 的加和在全库**零双算**。

对比另一方案「把 `report_config` 的码从旧族改成新族」：memory 已记 V138 的教训 —— 「错 row_code + 零命中码」是稳定的假正确，一旦把码修对就暴雷（L3 因此在国企项目查了「其他综合收益」）。旧族在 `c8621493` 有真实余额 `160,078.75`，改成新族会让该项目**丢数**。加法式两侧都保留，无此风险。

**判断 2：改 `report_config` 对多槽循环的语义定位零影响**

`semantic_account_resolver` 的 `allow_report_config_tier = len(spec.slots) == 1`。H8 有 3 槽、H9 有 2 槽 ⇒ 两者**根本不消费** `report_config` 公式，改它只修正报表本身的取数。这一点必须由守卫钉死（Property 3），否则下个会话会误以为改 `report_config` 会影响底稿取数而不敢动。

**判断 3：未知列名必须 fail-loud，但要保留一条兼容缝**

`_handle_tb` 的静默回退是「数字错」的根源。改成 raise 后，全库 72 处 `本期借方`/`本期贷方` 会从「静默取错值」变成「显式报错」—— 但这 72 处里有 56 处不在 H 类（属其它循环），一次性 raise 会让它们从「悄悄错」变成「公式管理页整片红」。故设计为：**注册这两个列名（让它们取到正确值）+ 未知列 raise**。两步同时做，H 类与其它循环同时受益，不产生新的红。

## Architecture

### 数据流（改造后）

```
四表入库
  │
  ├─ tb_balance (点号码, 客户原始码, 含 debit_amount/credit_amount)
  │     │
  │     └─→ account_mapping 反解 ─→ standard_account_code
  │
  └─ trial_balance (横杠码/标准码, unadjusted/audited/opening, 无发生额列)
        │
        ├─────────────────────────────────────────────────┐
        │                                                 │
   [路径 A: 底稿取数]                              [路径 B: 公式管理]
   semantic_account_resolver                      formula_engine
   （按科目名在本项目 account_chart 定位）          （按 prefill_formula_mapping 的字面码）
        │                                                 │
        │  多槽 spec 不消费 report_config                  │  TB() 读 ctx.tb_data
        │  单槽 spec 才启用 report_config 兜底              │  ★ R2: tb_data 须含 本期借方/本期贷方
        │                                                 │  ★ R1: 公式须双族加和
        ├─→ tb_values (前端 seed)                          │
        ├─→ tb_source_codes (溯源面板)                     └─→ 审定表/明细表单元格值
        ├─→ adjudication_prefill  ★ R3: H1/H2/H3/H4 缺失
        └─→ parent_check (三口径勾稽)
        │
        ▼
   底稿披露 Tab
        │  ★ R7: 动态插行区识别
        │  ★ R11: 禁引账龄枚举
        │  useDisclosureAutoSync (800ms 防抖)
        ▼
   sync_from_workpaper  →  disclosure_notes
        │  定位键 = (project_id, year, note_section)
        │  ★ R6: 会计政策章不得成为推送目标
        ▼
   附注模块 (主章节, 已 _aligned_by)
```

### 双族并取的三个落点（必须同时改，缺一即分叉）

| 落点 | 文件 | 改法 |
|------|------|------|
| ① 报表公式 | `report_config` (DB, 迁移 V145) | `BS-031` / `BS-063` 四准则改双族加和 |
| ② 公式预设 | `prefill_formula_mapping.json` | H8-1/H8-2/H9-1/H9-2/H9-3 的 `TB()` 改双族加和；`account_codes` 补新族码 |
| ③ 语义兜底码 | `h8_account_scope.py` / `h9_account_scope.py` | `fallback_standard_codes` 补新族码 |

三者是**独立路径**：① 只影响报表；② 只影响公式管理页；③ 只在科目表按名定位失败时才用。改一处另两处不动 = 分叉，故 Property 2 交叉锁死三者。

### 会计政策章两类条目的分辨判据

不能按章节号一刀切，须按**表结构**判：

| 类型 | 判据 | 处置 |
|------|------|------|
| **政策表** | headers 含 `使用年限`/`残值率`/`年折旧率`/`折耗率`/`摊销年限` 任一 | 保留，补 `columns` + `guidance` |
| **重复落章** | 与主章节某表 `headers` 归一后逐字相同，或 rows 数 ≥ 主章节同名表的 90% | 处置（清 rows + 标注指向主章节） |
| **空壳** | `tables=0` | 补政策表骨架（soe 五个循环全部如此） |

listed `三、使用权资产` 实测 39 行 / headers `['项  目','房屋及建筑物','机器设备','运输设备','……','合  计']`，与 `五、25` 的 39 行 / `['项目','房屋及建筑物','机器设备','运输设备','其他','合计']` 归一后相同 ⇒ 判为重复落章。

## Components and Interfaces

### 组件 1：`h_cycle_dual_family.py`（新建，后端共享件）

双族收口的**单一真源**。位置 `backend/app/services/four_table/h_cycle_dual_family.py`。

```python
@dataclass(frozen=True)
class DualFamilySlot:
    """一个语义槽的双族码声明。"""
    slot_key: str                    # 'gross' / 'accum_dep' / 'impairment'
    legacy_codes: tuple[str, ...]    # 旧族，如 ('1641',)
    current_codes: tuple[str, ...]   # 新族，如 ('1651',)
    source_ref: str                  # 实证依据（trial_balance 逐项目查询）

#: H8 使用权资产 / H9 租赁负债的双族声明
H_DUAL_FAMILY: dict[str, tuple[DualFamilySlot, ...]]

def dual_family_codes(cycle: str, slot_key: str) -> tuple[str, ...]:
    """返回该槽的全部码（旧族 + 新族），供 fallback_standard_codes 使用。"""

def dual_family_tb_expr(cycle: str, slot_key: str, column: str) -> str:
    """生成双族加和的 TB 表达式，如 "TB('1641','期末余额')+TB('1651','期末余额')"。
    供迁移脚本与公式预设脚本共用，杜绝两处各写一份。"""

def mutual_exclusion_holds(rows: list[dict]) -> bool:
    """反向自检：给定 trial_balance 行，验证两族在同一项目内互斥。
    互斥不成立时返回 False —— 此时加法式会双算，须改为择一。"""
```

**为什么要 `mutual_exclusion_holds`**：加法式的正确性**依赖**互斥这个数据事实。若将来某项目同时启用两族且都有余额，加和就会双算。该函数供 Task 21 的真实库验收调用，把「互斥」从一次性实证升级为可复验的判据。

### 组件 2：`formula_engine` 列名注册扩展（改造）

```python
COLUMN_ALIASES: dict[str, str] = {
    ...,                      # 既有 8 个键逐字不动
    "本期借方": "本期借方",
    "本期借方发生额": "本期借方",
    "本期贷方": "本期贷方",
    "本期贷方发生额": "本期贷方",
}

def _handle_tb(args, ctx, trace) -> Decimal:
    resolved_col = COLUMN_ALIASES.get(col_name)
    if resolved_col is None:
        raise FormulaError(f"未注册的列名 '{col_name}'，支持: {sorted(set(COLUMN_ALIASES))}")
    account_data = ctx.tb_data.get(code, {})
    if resolved_col not in account_data:
        # 列已注册但该科目无此列数据 → 返回 0 并 trace 标注，不回退别的列
        trace.append(f"TB('{code}','{col_name}') = 0 (列无数据)")
        return Decimal("0")
    ...
```

**关键**：区分「列名未注册」（配置错，raise）与「列已注册但无数据」（数据缺，返 0 + trace）。原实现把两者都回退成期末余额，是两个不同问题共用一个错误处置。

### 组件 3：`tb_data` 发生额产出（改造两个构造点）

`wp_template_files._get_tb_data_for_prefill` 与 `adjudication_writeback._build_context` 都只产出余额列。改法：**additive 补两列，从 `tb_balance` 按叶子聚合取**。

```python
# 新增：从 tb_balance 取发生额（trial_balance 无此列）
async def _fetch_occurrence_by_standard_code(db, project_id, year) -> dict[str, dict[str, Decimal]]:
    """返回 {standard_code: {'本期借方': x, '本期贷方': y}}。

    经 account_mapping 把 tb_balance 的原始码归集到标准码；
    只汇总叶子科目（平台铁律）；按 closing_direction 带符号。
    """
```

零回归保证：新键是**追加**，既有 4 个键（期初余额/期末余额/未审数/审定数）取值逐字不变 ⇒ 既有公式结果不变（Property 5 用 characterization 钉死）。

### 组件 4：`h_cycle_adjudication_prefill.py`（新建，复用 G 类范式）

G 类已有 `g_cycle_adjudication_prefill.py`，H1/H2/H3/H4 直接复用其结构，只声明各自的归类规则。

```python
@dataclass(frozen=True)
class HCycleRowRule:
    row_key: str                      # 审定表行标识
    field: str                        # 目标字段
    name_keywords: tuple[str, ...]    # 按科目名归类
    exclude_keywords: tuple[str, ...] # 否决词（顺序即优先级）
    source_ref: str                   # 源模板单元格

H_ADJUDICATION_RULES: dict[str, tuple[HCycleRowRule, ...]]  # H1/H2/H3/H4

def build_h_adjudication_prefill(cycle, leaves, slots) -> dict:
    """下发逐叶子明细（不做桶预聚合），聚合在前端做。"""
```

**必须下发逐叶子明细而非预聚合**（memory 已记 E1 的教训）：审计师改了某叶子的归属后，前端要能重算两侧余额；预聚合是有损表示。

### 组件 5：`hCycleAdjudicationSeed.ts`（新建，前端）

复用平台既有 `composables/shared/adjudicationPrefillPlan.ts`（plan → resolve → describe），只提供 H 类的归类声明与默认落点。

```typescript
export interface HSeedSpec {
  cycle: 'H1' | 'H2' | 'H3' | 'H4'
  rules: readonly HRowRule[]
  defaults: readonly HDefaultCell[]   // 空数组 = 未命中不兜底（进「待归类」面板）
}
```

`defaults` 一律为空 —— 未命中的叶子进「待归类科目」面板由审计师显式归入（G11 已确立的范式：自动路径不兜底，显式归入是独立处理器 + 确认框）。

### 组件 6：`fix_h_cycle_prefill_presets.py`（新建，幂等脚本）

```
--dry-run   默认，只打印计划
--check     有欠账即 exit 1（供 CI）
--apply     写入
```

变更项（共 6 类 / 约 34 处）：
| 类别 | 处数 | 说明 |
|------|------|------|
| 双族加和 | 5 块 / 17 cells | H8-1/H8-2/H9-1/H9-2/H9-3 |
| H3 贴错块重写 | 1 块 / 5 cells | 改回 `1521/1525/1526/1527` |
| 硬编码项目号删除 | 4 cells | H2 明细表 `AUX(...'B510003'...)` |
| H10 期初改 PREV | 1 cell | 损益类无期初 |
| `WP()` 联动新增 | 6 cells | H1-1←H1-2/H1-12、H2-1←H2-2、H8-1←H8-2、H9-1←H9-2/H9-3 |
| `account_codes` 补码 | 5 块 | 补新族码 |

脚本带 **round-trip 自检**（`json.dumps` 不能逐字复现原文即 exit 2），防全文件重排与并发冲突（G 类脚本已验证有效）。

### 组件 7：`fix_note_h_policy_chapter_structure.py`（新建，幂等脚本）

按「组件分辨判据」处置会计政策章。**先分类再处置**，分类结果写进 `--dry-run` 输出供人工复核。

### 组件 8：`H3TabAdjudicationCost/Fair` 接溯源面板（改造）

两个 Tab 的 `SourcePanel` 计数实测为 0。接线三步：宿主 `GtH3InvestmentProperty` 传 `:html-data`（已有 3 处，确认覆盖这两个 Tab）→ Tab 内 `<WpFourTableSourcePanel>` → props 按 `defineProps` 逐字对齐（memory 已记「传不存在的 prop = 静默失效，四层验证全查不出」）。

## Data Models

### 迁移 V145（`report_config` 双族并取）

```sql
-- 使用权资产 BS-031：四准则一律双族加和
UPDATE report_config SET formula =
  'TB(''1641'',''期末余额'')+TB(''1651'',''期末余额'')'
  '-TB(''1642'',''期末余额'')-TB(''1652'',''期末余额'')'
  '-TB(''1643'',''期末余额'')'
WHERE report_type='balance_sheet' AND row_code='BS-031'
  AND formula = 'TB(''1641'',''期末余额'')-TB(''1642'',''期末余额'')-TB(''1643'',''期末余额'')';

-- 租赁负债 BS-063
UPDATE report_config SET formula =
  'TB(''2601'',''期末余额'')+TB(''2651'',''期末余额'')-TB(''2602'',''期末余额'')'
WHERE report_type='balance_sheet' AND row_code='BS-063'
  AND formula = 'TB(''2601'',''期末余额'')-TB(''2602'',''期末余额'')';
```

**WHERE 带原值断言**（幂等 + 防覆盖并发改动）。**注意 `2651.02 未确认融资费用` 是 `2651` 的子科目** ⇒ 新族侧不再单独减 `2602`（父族聚合已按方向净掉，再减即双算，memory 已记 `c8621493` 的实证）。

迁移号须在应用前用 `migration_status` 实测确认（V139~V144 已占用，永不复用）。

### `prefill_formula_mapping.json` 结构（不变）

字段名是 `sheet` 不是 `sheet_name`；`applies_when` 在该文件**无消费方**（死字段，不要新增）。

### `note_template_*.json` 会计政策章补列（additive）

只补 `columns` / `guidance`，`rows=None`（不动行集）。政策表列定义示例：

```json
{"key": "category", "label": "类别", "flat": true},
{"key": "useful_life", "label": "使用年限（年）", "flat": true},
{"key": "residual_rate", "label": "残值率%", "flat": true},
{"key": "annual_rate", "label": "年折旧率%", "flat": true}
```

**必须标 `flat`**：源模板单行表头，不标会被 `_infer_groups_from_headers` 反猜出凭空父表头（memory 已记 F2/H8 两次踩中）。

## Error Handling

| 场景 | 处置 | 判据 |
|------|------|------|
| `TB()` 列名未注册 | **raise `FormulaError`** | 配置错误，静默回退会产出错数字 |
| `TB()` 列已注册但科目无该列 | 返 0 + trace 标注 | 数据缺失，与「列名错」区分 |
| `account_mapping` 反解不到 | 用原始码前缀匹配 + WARNING | fail-open，但不得静默（memory 已记 fail-open 吞掉接线错误的教训） |
| 双族互斥不成立 | 验收脚本 **FAIL 并打印冲突项目** | 加法式前提被破坏，须改择一 |
| 会计政策章分类不确定 | `--dry-run` 标 `NEEDS_REVIEW`，**不自动处置** | 误删政策表 = 丢披露内容 |
| `adjudication_prefill` 归类未命中 | 进「待归类」面板，**不兜底** | 宁缺勿造（G11 定论） |
| 附注推送目标是会计政策章 | **拒绝写入 + WARNING** | fail-closed，写错章节污染附注 |
| 溯源面板 prop 不匹配 | 守卫从 `defineProps` 动态抽取比对 | 传不存在的 prop 静默失效 |

## Testing Strategy

### 后端守卫（新建 5 个文件）

| 文件 | 覆盖 | 反向自检 |
|------|------|----------|
| `test_h_dual_family.py` | R1 / Property 1,2,3 | 单族公式必红；两族都有余额时 `mutual_exclusion_holds` 必返 False |
| `test_formula_column_registry.py` | R2 / Property 4,5 | 未注册列必 raise；旧静默回退行为必红 |
| `test_h_adjudication_prefill.py` | R3 / Property 6,7 | 预聚合形态必红；未命中兜底必红 |
| `test_h_prefill_presets_integrity.py` | R4 / Property 8,9,10 | H3 旧公式必红；硬编码项目号必红 |
| `test_note_h_policy_chapter.py` | R6 / Property 11,12 | 政策表被误判为重复落章必红 |

### 前端守卫（新建 4 个文件）

| 文件 | 覆盖 |
|------|------|
| `hCycleAdjudicationSeed.spec.ts` | R3 前端侧 + 跨文件交叉锁死（读后端 py 抽规则） |
| `h3SourcePanelWiring.spec.ts` | R8 + `defineProps` 动态抽取比对 |
| `hCycleAgingProhibition.spec.ts` | R11 反向锁死（源码禁引 `disclosureAgingLabels`/`useAgingConfig`） |
| `hCycleAmountControl.spec.ts` | R9 金额控件 + 反向边界（折旧率/残值率不得套用） |

### 变异检验（强制）

每个守卫写完必须真做一次变异（改一字看是否变红）。ANCHOR-MISS 是第三种结果，不能当 GREEN 处理。变异脚本：备份写 `.bak` + `try/finally` 无条件还原 + 一个脚本只做一个变异（memory 已记中断导致变异残留的教训）。

**共享热点文件**（`formula_engine.py` / `prefill_formula_mapping.json` / 两个 note_template JSON）的判据改用**替身字符串**在测试内验证，不做磁盘变异。

### 真实库验收（Task 21）

新建 `backend/scripts/diagnose/verify_h_cycle_extraction_live.py`（只读，默认 dry-run）：

- 9 项目 × 10 循环逐个跑 render，断言 `tb_source_codes` 非空、`parent_check.diff` 为 0
- 双族互斥复验（调 `mutual_exclusion_holds`）
- H8/H9 取数金额与 `trial_balance` 新族值逐分比对
- **诚实报告**：取不到数就报「本项目无此科目」，不用 fixture 冒充

### 回归基线

- 后端：`pytest backend/tests/four_table backend/tests/test_h*` （**从仓库根跑**，从 `backend/` 跑会让 16 个用相对路径的测试假红）
- 前端：`npx vitest run h1 h2 h3 h4 h5 h6 h7 h8 h9 h10`
- 判「失败是否自己造成」：traceback 行号是否落在自己改的行上 + 该文件 `git status` 是否干净

## Correctness Properties

### Property 1: 双族加和覆盖全部有数据的项目

对任意项目，H8/H9 的取数结果必须等于该项目实际启用那一族的 `trial_balance` 值；不得出现「只取到 0.04%」（旧族 160,078.75 vs 新族 386,272,594.21）。

**Validates: Requirements 1.1, 1.2, 1.4**

### Property 2: 双族三个落点交叉一致

`report_config` 公式、`prefill_formula_mapping` 公式、`h8/h9_account_scope.fallback_standard_codes` 三处的码集合必须相等（经 `h_cycle_dual_family` 派生），任一处漏改即打红。

**Validates: Requirements 1.3, 1.5**

### Property 3: 改 report_config 不改变多槽循环的语义定位

H8（3 槽）/H9（2 槽）在改 `report_config` 前后，`resolve_semantic_accounts` 返回的 `slots` 逐字节相同。判据 = `allow_report_config_tier` 对多槽 spec 为 False。

**Validates: Requirements 6.4**

### Property 4: 未注册列名 fail-loud

`TB('1601','不存在的列')` 必须 raise，不得返回期末余额。

**Validates: Requirements 2.2, 2.3**

### Property 5: 列注册零回归

注册 `本期借方`/`本期贷方` 后，既有 8 个列名的取值逐字不变（characterization 钉死全部 H 类公式的求值结果）。

**Validates: Requirements 2.1, 2.5**

### Property 6: 发生额取叶子且带符号

`本期借方`/`本期贷方` 的值 = 该标准码下**叶子**科目按 `closing_direction` 带符号求和，父子不双算。

**Validates: Requirements 2.4**

### Property 7: prefill 下发逐叶子明细

H1/H2/H3/H4 的 `adjudication_prefill` 必须含逐叶子 `code`/`name`/金额，不得是预聚合桶。

**Validates: Requirements 3.1, 3.4**

### Property 8: prefill 未命中不兜底

归类未命中的叶子进 `unclassified`，`defaults` 为空数组。

**Validates: Requirements 3.5**

### Property 9: 公式预设块与声明科目自洽

每个块的 `TB()`/`ADJ()` 实参科目码必须 ⊆ 该块 `account_codes`（H3 贴错块正是违反此条）。

**Validates: Requirements 4.1, 4.2**

### Property 10: 预设无项目专属污染

`prefill_formula_mapping` 的 H 类块不得含具体项目号/客户编码字面量（`AUX(...,'B510003',...)`）。

**Validates: Requirements 4.3**

### Property 11: H10 损益类期初走 PREV

H10 的「期初余额」不得与「未审数」公式相同；损益类上年数只能走 `PREV()`。

**Validates: Requirements 4.4**

### Property 12: 会计政策章分类不误伤政策表

含 `使用年限`/`残值率`/`年折旧率` 的表必须判为政策表并保留；判为重复落章的表必须与主章节某表 headers 归一后相同。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 13: 会计政策章不得成为推送目标

全前端 `*NoteSectionMap.ts` 不得指向 `三、`/`四、` 下的 H 类条目；后端 `sync_from_workpaper` 对该类章节 fail-closed。

**Validates: Requirements 6.5**

### Property 14: 政策表列必须标 flat

新补的 `columns` 每列带 `flat: true`，且不得声明 `group`（源模板单行表头）。

**Validates: Requirements 6.4**

### Property 15: 动态插行区标记忠实于源模板

披露表的可扩行位置必须与源 xlsx 的 `……`/`预留`/`可改名`/`可无限量添加行` 标记一一对应，不凭空插行也不漏。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 16: H3 溯源面板真实渲染且 prop 匹配

`H3TabAdjudicationCost/Fair` 含 `<WpFourTableSourcePanel>` 且传入的属性名全部存在于其 `defineProps`，必填 prop 已传。

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 17: 金额控件按语义分流

H 类金额格用 `WpAmountInput`；折旧率/残值率/年限/笔数保持 `el-input-number`，不得套用。

**Validates: Requirements 9.1, 9.2**

### Property 18: WP() 联动无环

新增的 `WP()` 引用不得形成环（审定表可引明细表，明细表禁引审定表）。

**Validates: Requirements 10.1, 10.4**

### Property 19: H 类禁引账龄枚举

H 类源码不得 import `disclosureAgingLabels`/`useAgingConfig`/`AGING_BANDS`。

**Validates: Requirements 11.1, 11.2**

### Property 20: 库龄独立且不与账龄同构

H4/H6 的库龄枚举独立声明，取值域与账龄段不同（不得出现「1年以内（含1年）」这类账龄字面量）。

**Validates: Requirements 11.3, 11.4**

### Property 21: 真实库验收诚实报告

验收脚本对取不到数的槽报「本项目无此科目」，不用 fixture 冒充；双族互斥不成立时 FAIL。

**Validates: Requirements 12.1, 12.2, 12.5**

### Property 22: 迁移幂等且号未复用

V145 重复应用零行影响；迁移号在 `schema_version` 中不存在。

**Validates: Requirements 6.3, 6.6**

### Property 23: 无落点变体的不适用声明自洽

对声明「本版不适用」的变体（H5 listed）：`variant_matrix` 该变体取值为 `null` **且** 对应模板章节实测数为 0（两条件同时成立才允许声明）；组件不得含 `useDisclosureAutoSync`/`scheduleAutoSync`；`buildH5SyncPayload` 对该变体恒返 `null`；源码不得出现 `?? '五、油气资产'` 一类**编造章节号**的兜底。

反向自检：把 payload 改成返非 null 必红；把编造章节号加回必红；把 `variant_matrix` 替身改成有取值时「允许声明」必红。

**Validates: Requirements 12.1, 12.4, 12.5, 12.6**

## Notes

### 范围外（明确不做）

- **H0 函证循环的九品种账面金额**：`h0_book_amounts.py` 已完备（15 KB + 18 KB 守卫），本 spec 不动
- **主章节附注结构**：前序 5 个 spec 已对齐并带 `_aligned_by`，不重做
- **`report_config` 其它错码**：归 `report-config-account-code-integrity`（已 12/12）
- **全库 56 处非 H 类的 `本期借方`/`本期贷方`**：R2 的列注册会让它们自动取到正确值，但不逐个验证其业务正确性
- **金额控件存量全平台替换**：只做 H 类，平台级收口另立 spec
- **`h5_oil_gas_assets_service` 等大文件重构**：与本 spec 无关

### 待用户裁决（已在本轮定案，此处留证）

1. **双族收口方式** → 加法式并取，不改码（依据：项目内互斥实证 + V138 改码暴雷教训）
2. **H4/H6 库龄** → 独立枚举件，不复用账龄（依据：长期资产无账龄维度，同 J2「到期分析」定论）

### 执行顺序硬约束

- **Task 2（守卫）必须先于 Task 3~5（修订）** —— 先改后写无法区分「守卫有效」与「空转」
- **Task 6（列注册）必须先于 Task 7（tb_data 产出）** —— 列没注册时产出该列数据无消费方
- **Task 12（会计政策章分类）必须先于 Task 13（处置）** —— 分类结果要人工复核
- **Task 21（真实库验收）最后** —— 依赖前面全部改动落地
