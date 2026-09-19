# Design Document

## Overview

两层架构把四表库 → D1–D7 提取做透，且**收敛到平台既有范式、不造新机制**：

- **Tier B（批量预填）**：为 D1–D7 补齐 K/M/N 已有的 `_build_adjudication_prefill` 范式（`tb_balance` 叶子级 + `get_active_filter` + 手工优先），render 返回 `adjudication_prefill`，前端专属组件消费 seed。这是「自动提取填充」的主体。
- **Tier A（可编辑公式）**：把可表达为单条公式的简单提取（科目/子目总额）注册为 `wp_formula`，在底稿页面公式管理可查可编；复杂归集（Tier B）只读溯源展示不伪装公式。二者**共用同一评估口径**（`get_active_filter`）消除双真源漂移。

## Architecture

```
四表库(只读, get_active_filter 数据集版本)
  trial_balance / tb_balance / tb_ledger / tb_aux_balance
        │
        ├── Tier B: _build_d_adjudication_prefill(ctx)  [复用 K/M/N 范式]
        │     tb_balance 叶子级汇总(opening/closing 或 debit/credit)
        │     → render 返回 adjudication_prefill
        │     → 前端专属组件 seed(手工优先) → 审定表未审数
        │
        └── Tier A: d_cycle_extraction_presets.json (预设) ∪ 用户 wp_formula
              expression=TB/SUM_TB (与 Tier B 同口径 tb_balance)
              target_cell=checklist_responses item_id(锚点)
              → 公式管理面板 GET/PUT/DELETE/禁用(可编)
              → 求值经统一口径(get_active_filter) → seed 到锚点
```

### 关键设计决策

**决策1（复盘修正）：Tier B 走 `_build_adjudication_prefill` SQL 预填，不做公式驱动。**
K/M/N 已证明该范式（K9/K1/N5：`get_active_filter` + `tb_balance` 叶子级 SUM + 手工优先 + 防双算 → render 返回 `adjudication_prefill`，前端无持久化时建行）。D1–D7 补齐同款。分类/账龄/客户归集本就靠此 SQL（含名称/code 段分类），无法压成单条可编辑公式，故不强塞 wp_formula。

**决策2：Tier A 复用 `wp_formula`，`target_cell` = checklist_responses item_id 锚点，不建新表。**
简单科目/子目总额提取可表达为 `TB('1402','期末余额')`，锚点用底稿字段真实 item_id。复用现有 `GET/PUT/DELETE /api/workpapers/{wp_id}/formulas` + 悬空校验。auto_calc 对 D-cycle 锚点回填走 checklist_responses 通道（非 parsed_data 网格）。

**决策3：评估器口径统一（消除漂移，本 spec 核心修复）。**
现 `evaluate_wp_formula_expression` 读裸 `trial_balance`+`is_deleted`、只支持 TB/SUM_TB/WP。修法二选一（Design 定为方案 a）：
- **方案 a（采纳）**：Tier A 允许函数收紧为 `TB`/`SUM_TB`，并让其 `_resolve_tb`/`_resolve_sum_tb` 改用 `get_active_filter` 读（与 Tier B 同口径）；`AUX`/`PREV`/序时账 暂不作为可编辑公式（保存时拒绝返 422，不静默返 0）——因为这些正是 Tier B 复杂归集，由 prefill 承担。
- 方案 b（不采纳，留后续）：给评估器补 AUX/PREV/序时账真实实现。
理由：Tier A 只需简单总额，方案 a 最小、最快消除漂移，且与「复杂归集归 Tier B」一致。

**决策4：预设库文件驱动 + 读时收敛（Tier A）。**
`backend/data/d_cycle_extraction_presets.json` 按 wp_code 列 Tier A 默认公式（锚点/表达式/说明）。有效 = 预设 ∪ 用户 wp_formula（同锚点用户覆盖），预设不落库。用户「禁用」写一条 `formula_type='auto_calc'`、`expression=''`（或独立禁用标记 `wp_formula.category='__disabled__'`）使该锚点不填。

**决策5：锚点真实键发现前置（Wave 0）。**
先从各 D-cycle composable（`useD{n}Adjudication`/`useD{n}Detail`）反查真实 item_id，产出 `d_cycle_anchor_registry.json`（wp_code → 已知锚点集）。prefill/公式的 target 必须 ∈ 该集合，否则拒绝/告警（防静默丢失）。

**决策6：灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False）。**
关闭时 render 不调 prefill、不返 `adjudication_prefill`、面板不列 Tier A 预设 → 逐字节等价当前。D6/D2 试点 → 铺 D1/D3/D4/D5/D7，单循环可回退。

**决策7：公式管理面板端点修复 + 分层展示 + 复用 seed 值。**
`FormulaStatusPanel` 改真实端点解析 `items`；GET 端点返回 Tier A（预设∪用户，source 区分）+ Tier B 只读溯源；每条附最近一次 render seed 值（面板不逐条重求值）；按 sheet 分组；编辑/恢复默认/禁用按权限门控。

## Components and Interfaces

### 后端

**`backend/app/services/d_cycle_extraction/prefill.py`（新建，Tier B 通用）**
- `build_d_adjudication_prefill(ctx, *, account_prefix, mode, anchor_map) -> dict|list`：镜像 `_k9/_k1` 范式——`get_active_filter(db, TbBalance.__table__, pid, year)` + 叶子级 SUM（`mode='balance'`→opening/closing；`mode='occurrence'`→debit/credit）+ 跳零/无名 + 手工优先由调用方（render）用 responses_snapshot 判定。
- 供 D1–D7 render 以各自 `account_prefix`/`mode` 调用（D1=1121/balance、D4=6001/occurrence 等）。

**`backend/app/services/d_cycle_extraction/presets.py`（新建，Tier A）**
- `load_presets(wp_code) -> list[Binding]`（读 `d_cycle_extraction_presets.json`，mtime 缓存）。
- `resolve_effective(db, wp_id, wp_code, project_id) -> list[Binding]`（预设 ∪ 用户 wp_formula 收敛，source=preset/custom/disabled）。
- `known_anchors(wp_code) -> set[str]`（读 `d_cycle_anchor_registry.json`，合法性校验）。

**D1–D7 render 策略（改）`_d{1..7}_*.py`**：开关开 → 调 `build_d_adjudication_prefill` → 手工优先并入 → 返回 `adjudication_prefill`（additive，保留 tb_amount 等）。

**`GET /api/workpapers/{wp_id}/formulas`（改 `wp_formula.py`）**：合并 Tier A 预设（读时收敛，source 字段）+ Tier B 只读溯源条目；附 seed 值（可选）。

**`evaluate_wp_formula_expression`（改 `wp_formula_eval_service.py`）**：`_resolve_tb`/`_resolve_sum_tb` 改用 `get_active_filter`；保存端点对 AUX/PREV/序时账函数返 422（方案 a）。

### 前端

**`FormulaStatusPanel.vue`（改）**：端点改 `GET /api/workpapers/{wpId}/formulas` 解析 `items`；按 sheet 分组；Tier A 可编辑（PUT）/恢复默认（DELETE）/禁用、Tier B 只读溯源；权限门控（`usePermissionMatrix`）；值复用 seed。

**D1–D7 专属组件（改，逐循环）**：消费 `adjudication_prefill` seed（手工优先，标注自动取数），可编辑覆盖后不被回写。

## Data Models

**Binding（内存，不新建表）**
```
{ "wp_code":"D6", "sheet_name":"D6-1", "anchor":"D6-1-block1-endUnadjusted",
  "expression":"TB('1402','期末余额')", "formula_type":"auto_calc",
  "description":"合同资产原值-期末未审(1402)", "source":"preset|custom|disabled",
  "tier":"A" }
```
**`d_cycle_extraction_presets.json`**：`{ "D1":[Binding...], ..., "D7":[...] }`（仅 Tier A）。
**`d_cycle_anchor_registry.json`**：`{ "D1":["D1-1-...", ...], ..., "D7":[...] }`（Wave 0 从 composable 反查）。
**`adjudication_prefill`（render 返回）**：对齐 K9/K1/N5 结构（`list[{name, unadjusted*}]` 或 `dict`，按各循环组件既有消费形状）。

## Correctness Properties

### Property 1: 只取叶子防双算
`build_d_adjudication_prefill` 汇总时排除「是其它 code 前缀」的中间级科目，合计不含 rollup 双计。
**Validates: Requirements 1.4**

### Property 2: 手工优先不覆盖
锚点在 checklist_responses 已有非空用户值（含一键取数）时，prefill/seed 不写入。
**Validates: Requirements 1.5, 2.2, 2.3**

### Property 3: active_filter 同口径
Tier B 预填与 Tier A 求值均经 `get_active_filter`；同一 (project,year) 快照下二者对同科目总额口径一致。
**Validates: Requirements 1.3, 4.1**

### Property 4: 无数据→空不报错
`tb_balance` 无该科目子科目时返回空 `adjudication_prefill`，render 正常返回。
**Validates: Requirements 1.6, 4.4**

### Property 5: 读时收敛（预设∪用户覆盖∪禁用）
`resolve_effective` 每锚点唯一：禁用>用户custom>预设；预设未落库不丢失。
**Validates: Requirements 3.3, 5.4, 5.5**

### Property 6: 不支持函数保存拒绝
Tier A 保存含 `AUX/PREV/序时账` 或其它不受支持函数时返 422 不写库、不静默返 0。
**Validates: Requirements 4.2**

### Property 7: 悬空引用保存拒绝
Tier A 保存含 `not_found` 引用时 PUT 返 422 不写库。
**Validates: Requirements 5.3**

### Property 8: 未知锚点拒绝
prefill/公式 target 不属于该 wp_code 的 `known_anchors` 时拒绝/告警，不静默写空。
**Validates: Requirements 6.2**

### Property 9: 灰度关闭零回归
开关关闭时 D-cycle render 返回值与未接入本 spec 逐字节一致（无 adjudication_prefill、面板无 Tier A 预设）。
**Validates: Requirements 7.1, 7.2**

### Property 10: 求值幂等
同一四表库快照下多次求值同一 Tier A 公式结果一致。
**Validates: Requirements 4.3, 8.2**

### Property 11: 来源可溯
每个 seed 值可回指其 Tier A 公式表达式或 Tier B prefill 来源。
**Validates: Requirements 8.2, 5.2**

### Property 12: 复用范式不新造
Tier B 走 `_build_adjudication_prefill` 范式与 `get_active_filter`；无第 3 套四表库读取；四表库只读守卫（读四表库写底稿允许、auto_calc target 四表库仍拒）兼容。
**Validates: Requirements 7.3**

## Error Handling

- prefill 单科目查询失败 → `logger.warning` + 该循环返空 prefill（fail-open）。
- 预设文件缺失/解析失败 → 返 `[]`（该 wp 无 Tier A）。
- 未知锚点 → 拒绝写入 + 告警（Property 8）。
- Tier A 保存不支持函数/悬空 → 422（Property 6/7）。
- 四表库查询失败 → 沿用现 render try/except 降级（tb_amount=0 等不变）。

## Testing Strategy

- 后端 PBT/单测：Property 1–12（`tests/d_cycle_extraction/`），tb_balance 用内存/mock 快照。
- render 集成：每循环 D1–D7 开关开/关（零回归 + prefill 并入 + 手工优先）。
- 前端 vitest：`FormulaStatusPanel` 端点修正 + 分层展示 + 编辑/恢复默认/禁用 + 权限门控。
- Playwright（收尾，需实例化项目）：打开 D6/D2 → 审定表自动取数 seed + 公式管理列 Tier A 可编/Tier B 只读 → 编辑保存 → 手工覆盖后不被回写。
