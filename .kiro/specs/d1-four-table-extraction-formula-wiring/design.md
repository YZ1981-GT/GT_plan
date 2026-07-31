# Design Document

## Overview

本设计在**不新造第 3 套四表库读取**的前提下，补齐 D1 应收票据循环「四表入库 → 底稿刷新取数」链路。核心是把已归档 spec 对 D1 的「宁缺勿造」判断按实证数据纠正：客户科目表在叶子层已编码 D1 所需的原值维度（`1121.01/.02/.03`）与坏账维度（`1231.01`），因此 D1-2 / D1-4 可经既有 `build_d_adjudication_prefill` 叶子范式**诚实取数**（seed 实际叶子科目，审计师可调整），而非臆造分类。

设计遵守四条铁律：**叶子只汇总 / 手工优先 / 灰度开关 / fail-open**。D1 前端组件 `GtD1NotesReceivable` 为自加载组件，通过 `html_data.responses_snapshot` 接收 render 下发的持久层回显；因此 seed 采用**transient seed 进 responses_snapshot**（mirror 既有 `tier_a_seed` 范式），前端既有加载路径（`useD1DetailCategory` / `useD1BadDebt` 读 `D1-cat-rows` / `D1-bd-*-rows`）零改动即可消费。

披露与附注部分为复核 + 差异修订，复用既有 `useDisclosureAutoSync` 推送链路与 `fix_note_*_structure.py` 幂等脚本范式。

## Architecture

```
四表入库（tb_balance / trial_balance / tb_aux_balance / tb_ledger）
        │  account_mapping: original → standard（1121 / 1231）
        ▼
D1 render 策略 _d1_notes_receivable.py::render(ctx)
   ├─ [现状] project_context.tb_amount ← trial_balance 1121（审定汇总）
   ├─ [现状] seed_tier_a_reconciliation → D1-adj-tb-amount（TB('1121','期末余额')）
   ├─ [新增] seed_d1_detail_rows(ctx, responses_snapshot)   ← 本设计核心
   │        ├─ build_d1_category_rows_from_tb  ← tb_balance 1121 叶子（原值）
   │        └─ build_d1_bad_debt_rows_from_tb  ← tb_balance 1231.01（坏账）
   │        规则：灰度开关 / 手工优先（snapshot 已有则跳过）/ leaf-only / fail-open
   ▼
html_data.responses_snapshot（含 D1-cat-rows / D1-bd-*-rows transient seed）
        ▼
GtD1NotesReceivable（self-load）→ allResponses Map
   ├─ useD1DetailCategory 读 D1-cat-rows        （零改动）
   ├─ useD1BadDebt 读 D1-bd-individual/portfolio （零改动）
   └─ useD1Adjudication cross-sheet 派生 D1-1 原值/坏账/净值（零改动）
        ▼
D1 披露表（上市/国企）─ useDisclosureAutoSync ─▶ 附注 五、4 / 八、4
```

新增后端模块 `d_cycle_extraction/d1_detail_seed.py`（与 `detail_aggregation.py` 同层同范式），提供纯函数 + 可复用入口，供 render 按名调用。

## Components and Interfaces

### 后端

- **`d_cycle_extraction/d1_detail_seed.py`（新增）**
  - `build_d1_category_rows_from_tb(leaves: list[dict]) -> list[dict]`：纯函数。把 `build_d_adjudication_prefill(mode='balance')` 返回的 1121 叶子（含 code/name/opening/closing/debit/credit——需扩展 prefill 返回发生额，或本模块单独查）映射为 D1-cat-rows JSON 行：`{rowId, category, isFixed, priorUnadjusted=opening, currentIncrease=debit, currentDecrease=credit, currentAje:0, currentRje:0}`。名称含「银行承兑」→ `fixed-bank`；含「商业承兑」→ `fixed-commercial`；其余 → 动态行 `dynamic-{n}`。
  - `build_d1_bad_debt_rows_from_tb(leaves: list[dict], *, direction_map) -> tuple[list,list]`：纯函数。把 1231 中「应收票据」叶子映射为 D1-bd portfolio 行（`fixed-portfolio` 期初 priorUnadjusted、期末经 currentProvision 归一）；individual 留默认空行（宁缺勿造）。
  - `async seed_d1_detail_rows(ctx, responses_snapshot) -> None`：可复用入口。查 1121 / 1231 叶子（经 `get_active_filter` + leaf-only），构建行，**仅当 responses_snapshot 无对应 anchor 的非空 remark 时** transient seed（手工优先）；全程 fail-open。anchor 经 `is_known_anchor('D1', ...)` 校验。
- **`_d1_notes_receivable.py::render`（修改）**：在既有 `seed_tier_a_reconciliation` 之后、灰度开关分支内，`await seed_d1_detail_rows(ctx, responses_snapshot)`（fail-open 包裹）。删除/更新原「宁缺勿造」注释为「实证叶子取数」说明。
- **`presets.py::_TIER_B_PROVENANCE['D1']`（修改）**：把 D1-2/D1-4 的溯源描述从「不从四表库填」更新为「← tb_balance 1121/1231.01 叶子」；新增 D1 各底稿间连接取数溯源条目（R4.3）。
- **`d_cycle_extraction_presets.json` D1 段（保留 + 可选补充）**：Tier A `TB('1121','期末余额')` 保留。

### 前端（零/极小改动）

- `useD1DetailCategory` / `useD1BadDebt`：既有 `loadFromResponses` 已读 `D1-cat-rows` / `D1-bd-*-rows`；seed 走 responses_snapshot → 无需改动。若需区分「seed 值 vs 真人工编辑」以支持「重新从四表取数」按钮，则新增可选 refresh action（Wave 3，非必须）。
- 披露/附注：按复核结论做差异修订（Wave 4）。

### 披露/附注

- 复核基准：`backend/wp_templates/D/D1 应收票据.xlsx` 两个披露 sheet + `note_template_{listed,soe}.json` 五、4/八、4 + `d1NoteSectionMap.ts`。
- 修订工具：`scripts/fix/fix_note_d1_notes_receivable_structure.py`（已存在，阶段一产出）+ 契约 `d1NoteSubtableContract.spec.ts`（已存在）。本 spec 若发现新差异则增量扩展，不新建脚本。

## Data Models

### D1-cat-rows（D1-2 明细行，remark = JSON 数组）

```
{ rowId, category, isFixed, priorUnadjusted, priorAje, priorRje,
  currentIncrease, currentDecrease, currentAje, currentRje }
```
seed 映射：`priorUnadjusted=opening_balance`，`currentIncrease=debit_amount`，`currentDecrease=credit_amount`（→ currentUnadjusted computed = closing_balance）。

### D1-bd-*-rows（D1-4 坏账明细行，remark = JSON 数组）

```
{ rowId, category:'individual'|'portfolio', label, isSubRow,
  priorUnadjusted, priorAje, priorRje,
  currentProvision, currentRecovery, currentReversal, currentWriteOff, currentOther,
  currentAje, currentRje }
```
seed 映射：portfolio `fixed-portfolio` 行 `priorUnadjusted=坏账期初（方向归一）`，`currentProvision=本期净计提（方向归一）`；individual 留空。

### tb_balance 相关列

`account_code / account_name / opening_balance / closing_balance / debit_amount / credit_amount / closing_direction`（无符号绝对值 + 方向列）。

### 科目映射（只读依据）

`account_mapping(original_account_code → standard_account_code, mapping_type)` / `report_config(row_code, formula, applicable_standard)` / `note_account_mappings(report_row_code, note_section_code, wp_code, fetch_mode)`。D1 取数以 standard 科目 1121/1231 的叶子子科目为准。

## Correctness Properties

### Property 1: 叶子只汇总
D1-2 / D1-4 seed 只纳入叶子科目（其 code 不是任何其它 code 前缀），排除科目本身 `1121`/`1231` 与中间级，防双算。
**Validates: Requirements 1.3, 2.1**

### Property 2: 手工优先
WHEN responses_snapshot 已有对应 anchor 的非空 remark THEN seed 不覆盖。
**Validates: Requirements 1.5, 2.4**

### Property 3: 灰度关零回归
WHEN `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 关闭 THEN D1 render 输出（含 responses_snapshot）与改动前逐字节等价。
**Validates: Requirements 1.7, 2.5, 7.1**

### Property 4: fail-open
WHEN 四表查询异常 / year 缺失 / 无叶子科目 THEN seed 跳过、render 不阻断、返回既有默认。
**Validates: Requirements 1.6, 7.2**

### Property 5: 余额勾稽一致
seed 后的 D1-2 行满足 `期初 + 本期增加 − 本期减少 = 期末`（opening + debit − credit = closing）。
**Validates: Requirements 1.2**

### Property 6: 固定行映射
WHEN 叶子名称含「银行承兑」/「商业承兑」THEN 落到 `fixed-bank`/`fixed-commercial`；其余叶子作动态行且不丢失。
**Validates: Requirements 1.4**

### Property 7: 锚点合法
所有 transient seed 目标锚点 ∈ `is_known_anchor('D1', anchor)`；未知锚点丢弃 + 告警。
**Validates: Requirements 4.5**

### Property 8: 溯源不臆造
`tier_b_provenance('D1')` 只登记确由四表库/cross-sheet 填充的锚点；无法干净映射者标注宁缺勿造，`editable=False`。
**Validates: Requirements 3.3, 4.2, 4.4**

### Property 9: 披露列结构随源模板
D1 披露表 / `d1NoteSectionMap` / 附注 五、4·八、4 列结构与源模板 xlsx 一致（两级表头不压扁、不丢列）。
**Validates: Requirements 5.2, 6.2**

### Property 10: 推送同构
披露表推送后，附注子表数据与披露表同构（含动态插行、账龄段），文本框键集一一对应。
**Validates: Requirements 6.1, 6.3**

## Error Handling

- **查询失败 / year 缺失 / 无叶子**：`seed_d1_detail_rows` 全程 try/except，`logger.warning` + 跳过 seed（不 raise），render 照常返回既有 html_data（fail-open / Property 4）。
- **未知锚点**：seed 前经 `is_known_anchor('D1', anchor)` 校验，未知则丢弃 + 告警，绝不静默写不存在字段。
- **坏账方向不确定**：`1231` 叶子方向列缺失或异常时，坏账 seed 跳过该行（宁缺勿造，R2.3），不写猜测值。
- **前端 seed 值非法**：既有 `useD1*` 的 `parseNum`（`Number.isFinite` 守卫）兜底，非法值降级为 0，不写 NaN。
- **披露推送失败**：复用既有 `syncToDisclosureNotes` 的错误提示，不静默 `catch {}` 吞。

## Testing Strategy

- **后端 characterization（Property 3）**：灰度关时 D1 render 输出与基线逐字节等价（新增 `test_d1_extraction_seed.py::test_flag_off_byte_equivalent`）。
- **后端单元（Property 1/2/4/5/6）**：`build_d1_category_rows_from_tb` / `build_d1_bad_debt_rows_from_tb` 纯函数覆盖叶子选取、勾稽一致、固定行映射；`seed_d1_detail_rows` 覆盖手工优先、fail-open。
- **后端契约（Property 7/8）**：`tier_b_provenance('D1')` 锚点全 ∈ 登记表；溯源条目 editable=False。
- **前端单元（Property 2）**：`useD1DetailCategory` / `useD1BadDebt` 消费 seed（无持久化 seed 就位、有持久化不覆盖）。
- **披露契约（Property 9/10）**：`d1NoteSubtableContract.spec.ts` 现有 + 增量；`fix_note_d1_notes_receivable_structure.py --check` 绿。
- **浏览器实测（R7.5）**：chrome-devtools 登录 → D1 底稿四表入库后 D1-1/D1-2/D1-4 有数据 → 披露推送 → postgres 只读验附注 五、4/八、4 落库；测试数据用后复原。
