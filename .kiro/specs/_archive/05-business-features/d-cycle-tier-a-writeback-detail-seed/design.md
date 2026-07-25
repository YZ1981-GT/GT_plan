# Design Document

## Overview

闭合前置 spec 两个 P0 缺口，**全部复用既有机制、不新造第 3 套四表库读取**：

- **P0-1（Tier A 真生效）** = 三段闭环：①保存时对 D-cycle 锚点（`target_cell ∈ known_anchors`）**跳过写错库 parsed_data + 返回 `evaluated_value` 供前端即时显示**（**不做 checklist_responses/DB 写回**）；②GET 对 Tier A 求值填 `value`（面板可核对）；③**render 用 `resolve_effective` 的 Tier A 公式 transient seed TB 核对行（进 `responses_snapshot`，不落库，手工优先，优先于硬编码 `project_context.tb_amount`）——此为使"编辑公式即生效"成立的主机制**（每次打开按当前有效公式重算，对齐 D6 Tier B `adjudication_prefill`）。三段共用既有 `evaluate_wp_formula_expression`（`get_active_filter`）。
- **P0-2（明细自动 seed，试点）** = render 打开明细表且完全空时，调既有后端归集 resolver（tb_aux_balance/序时账）**transient seed** 明细行（`detail_prefill`，不落库、手工优先、fail-open、保留前端手动一键取数）。先以 D6-2 明细表试点；受 P0-2 子开关门控。

灰度：P0-1 受**主开关** `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False）；P0-2 额外受**子开关** `D_CYCLE_DETAIL_SEED_ENABLED`（默认 False，被主开关 AND）——可"发 P0-1、压 P0-2"。任一关闭时逐字节等价前置 spec 状态。

## Architecture

```
┌─────────────────────────── P0-1：Tier A 真生效 ───────────────────────────┐
│                                                                           │
│  PUT /formulas (auto_calc)  [主开关 ON]                                    │
│    target_cell ∈ known_anchors(wp_code)?                                  │
│      ├─ 是(D-cycle 锚点) → 跳过 write_cell_to_parsed_data（不写错库）      │
│      │                    + 求值(get_active_filter) → 返回 evaluated_value │
│      │                      供前端即时本地显示（不 DB 持久化）             │
│      └─ 否(网格 cell)    → 现有 write_cell_to_parsed_data（零回归）         │
│                                                                           │
│  GET /formulas → _build_extraction_block                                  │
│    tierA[*].value = evaluate(get_active_filter)  ← 原本恒 None             │
│    tierB[*].value = None（不变）                                          │
│                                                                           │
│  render (D-cycle, 主开关 ON) ★主机制★                                      │
│    resolve_effective(Tier A) → 逐条 evaluate(get_active_filter)           │
│      → transient seed 锚点(TB 核对行) 进 responses_snapshot（不落库）      │
│         写入前端实际读取的字段(remark|conclusion, 逐锚点核实)             │
│      手工优先: 锚点持久层已有非空值 → 跳过; source=disabled → 跳过         │
│      fail-open: 出错静默沿用 project_context.tb_amount                    │
│    （编辑公式→下次 render 按新公式重算；保存后前端用返回 evaluated_value  │
│      即时更新，无需 DB 写回，规避冻结/来源混淆）                          │
└───────────────────────────────────────────────────────────────────────────┘

┌──────── P0-2：明细表维度归集自动 seed（试点 D6-2，子开关门控） ────────┐
│  render (D-cycle 明细表, 主开关 ON ∧ D_CYCLE_DETAIL_SEED_ENABLED ON)       │
│    明细行完全空? ─是→ 调既有归集(可复用后端函数，Wave0 核实/必要时先抽取) │
│                        → transient seed 明细行进 render(detail_prefill)   │
│                 └否→ 不 seed（手工优先，不覆盖既有一键取数/手工行）         │
│    复用既有聚合不新造；fail-open 空；前端手动按钮保留                     │
└───────────────────────────────────────────────────────────────────────────┘
```

### 关键设计决策

**决策1（A，核心简化）：保存不做 DB 写回，render transient seed 作"编辑即生效"唯一权威。**
`PUT /formulas` 的 auto_calc 分支现无条件 `write_cell_to_parsed_data(cell_ref=target_cell)`。改为：先解析 wp_code，若 `is_known_anchor(base_wp_code, target_cell)` 为真（D-cycle 锚点，如 `D6-1-tb-amount`）且主开关开 → **跳过 write_cell_to_parsed_data**（写进网格对 D-cycle 专属组件无意义、且误导后续读 parsed_data 者），并返回 `evaluated_value`（供前端即时本地显示）；否则（普通网格 cell 如 `B5`）沿用 `write_cell_to_parsed_data`（零回归）。**不新增任何 checklist_responses/DB 写回**——"编辑即生效"由决策3 的 render transient seed 承担。**放弃 DB 写回的理由**：①持久化的是"公式派生值"，落进 checklist_responses 后与"真人工值"无法区分 → 决策3 的手工优先会把它当人工值 → TB 变了也不刷新（冻结）；②对齐 D6 Tier B（从不持久化，手工优先只挡真人工编辑）；③对共享端点侵入更小（只条件跳过一处写，不新增 DB 写路径）。锚点注册表天然区分 D-cycle 锚点 vs 网格 cell（grid cell 不 ∈ known_anchors）。

**决策2（C，写对字段）：render seed 写入前端实际读取的 responses_snapshot 字段（remark vs conclusion）。**
D-cycle per-field 值在 `responses_snapshot`/checklist_responses 有 `conclusion` 与 `remark` 两字段，各锚点前端 composable 读取的字段不一（memory 有 L1 因存 conclusion 但读 remark 导致 round-trip 断裂的先例）。故 Wave 0 **逐锚点从 composable 核实其读取字段**并登记（扩 `d_cycle_anchor_registry.json` 或 seed 时对齐）；render transient seed 必须写入该字段，否则前端读不到 = 假 seed。**不新建表、不做 DB 写**（seed 只进 render 返回 payload）。

**决策3：render transient seed Tier A 优先于硬编码 tb_amount，默认值等价（P0-1 R3，主机制）。**
D-cycle render 现将审定数写入 `project_context.tb_amount`（前端 TB 核对行 fallback 读）。改为：render 额外用 `resolve_effective` 的 Tier A 公式求值，**transient seed** 锚点进 `responses_snapshot`（手工优先，不落库）。前端 seed 优先级 = 持久层非空值 > responses_snapshot seed > project_context fallback。**默认预设 `TB('1402','期末余额')` 求值 = trial_balance 审定数 = 现 project_context.tb_amount**（口径一致，默认行为不变，R3.6）；仅用户编辑/禁用时才产生差异。保留 project_context.tb_amount 作 fail-open 回退（R3.4）。因不落库，每次打开按当前有效公式重算，编辑公式即在下次 render 生效，无冻结、无来源混淆。

**决策4（B，先核实可复用性）：P0-2 复用既有归集，必要时先抽纯函数，子开关门控，试点 D6-2。**
明细表维度归集（如 D6-2 ← tb_aux_balance 1402 客户/合同维度、D4-2 ← 序时账 6001 按产品×月）中，`d4_ledger_monthly_by_product` 已是可复用 resolver；但 **tb_aux_balance 客户维度归集可能仅存在于 HTTP handler（`/import-aux-balance`）内、非可复用后端函数**。故 Wave 0 **核实 D6-2 aux 归集形态**：若仅在 handler 内，先将聚合抽取为纯函数（**不改原 HTTP 端点行为**）再供 render 调用（R4.4）。render 打开明细表且**完全空**时调该函数得明细行，作 `detail_prefill` transient 返回（不落库）。**试点选 D6-2**（D6 已是 Tier B 主试点）；受 P0-2 子开关 `D_CYCLE_DETAIL_SEED_ENABLED`（默认 False，被主开关 AND）门控。其余循环增量、可回退。不新造读取。

**决策5：手工优先与 fail-open 一致复用前置 spec 判定。**
render seed（P0-1 R3 / P0-2 R4）沿用 D6 已有的 `_block1_has_user_data(responses_snapshot)` 同款"锚点/明细完全空才并入"判定；任一环异常 `logger.warning`（非用户通知）+ 省略 seed（始终 fail-open，含严重/系统级错误，不阻断 render）。

**决策6（G，灰度独立可回退）：主开关 + P0-2 子开关。**
P0-1 受主开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`；P0-2 明细 seed 额外受子开关 `D_CYCLE_DETAIL_SEED_ENABLED`（默认 False），生效条件 = 主开关 ∧ 子开关。故可"发 P0-1、压 P0-2"（真正独立灰度与回退，满足 R5.2）。P0-1 与 P0-2 代码路径独立，其一 fail-open 不牵连其二。

## Components and Interfaces

### 后端

**`PUT /api/workpapers/{wp_id}/formulas`（改 `wp_formula.py`，决策1）**
- auto_calc 分支：`if 主开关 and is_known_anchor(base_wp_code, target_cell): 跳过 write_cell_to_parsed_data（不写错库）` else 现有 `write_cell_to_parsed_data`。两分支都求值并在响应返回 `evaluated_value`（前端即时显示）；求值失败 → 不返回错误/0 值 + eval_warnings（R1.4）。**不新增 checklist_responses/DB 写回**（无 write helper）。

**`_build_extraction_block`（改 `wp_formula.py`）**
- Tier A：对每条 binding 调 `evaluate_wp_formula_expression`（get_active_filter）填 `value`；条目有界（≤2/循环），单条失败 → value=None fail-open（R2）。Tier B value 不变（None）。

**D-cycle render 策略（改 `_d{1..7}_*.py`，先 TB 核对行锚点所在循环）**
- 主开关 ON 时：`resolve_effective(db, wp_id, wp_code, project_id)` → 逐条 evaluate → 手工优先 **transient seed** 锚点进 `responses_snapshot`（**不落库**，R3）；写入前端实际读取字段（remark|conclusion，Wave0 逐锚点核实，决策2）。默认与 project_context.tb_amount 等价，保留其作 fail-open 回退。

**明细 seed（改 render，P0-2 试点 D6-2，子开关门控）**
- 主开关 ∧ `D_CYCLE_DETAIL_SEED_ENABLED` ON + 明细表完全空：调既有归集（可复用后端函数；若仅在 handler 内则 Wave0 先抽纯函数）→ `detail_prefill` transient 返回（R4，不落库）。fail-open 空。

**Wave 0 核实（决策2/决策4/B/C）**
- 逐 Tier A 锚点核实前端 composable 读取字段（remark vs conclusion）；核实 D6-2 aux 归集是否为可复用后端函数（否则先抽纯函数不改 HTTP 行为）。

**配置（决策6/G）**
- 新增 `settings.D_CYCLE_DETAIL_SEED_ENABLED`（默认 False）；P0-2 生效 = 主开关 ∧ 子开关。

**契约守卫（扩 `test_contract_guards.py`）**
- G6：D-cycle 锚点 auto_calc 保存**不写 parsed_data**（跳过）且**不做 DB 写回**、返回 evaluated_value；G7：明细归集复用既有函数（不新造四表读取）；G8：GET value / render seed 同经 get_active_filter。

### 前端

**`FormulaStatusPanel.vue`（改）**
- Tier A `value` 现由后端填（P0-1 R2）→ 面板"当前值"显示真实求值结果（已有 `displayValue` 渲染，无需大改，值不再恒 `—`）。

**D-cycle 专属组件（核验，可能微调）**
- 确认 TB 核对行读 `responses_snapshot` seed 优先于 `project_context.tb_amount` fallback；保存后用 PUT 响应 `evaluated_value` 即时本地更新核对行（无需 DB 写回 / 无需刷新）；render transient seed 后手工编辑（持久化）不被回写（手工优先）。保留手动一键取数按钮（R4.6）。

## Data Models

**PUT /formulas 响应（D-cycle 锚点，决策1）**
```
{ saved: {...formula record...}, evaluated_value: "<求值结果>",   # 供前端即时显示
  eval_warnings?: [...] }                                          # 不写 parsed_data / 不写 DB
```

**render `responses_snapshot` 的 Tier A transient seed（不落库，决策2/3）**
```
responses_snapshot[anchor] = { <前端读取字段 remark|conclusion>: 格式化求值值 }
# 仅锚点持久层完全空且非 disabled 时并入；source 语义 = 公式驱动 seed（非人工值）
```

**GET /formulas 的 Tier A binding（扩 value）**
```
{ wp_code, sheet_name, anchor, expression, source, tier:"A",
  semantic(P1-4已加), value: <求值结果|None>(P0-1新填) }
```

**render `detail_prefill`（P0-2，transient，对齐 adjudication_prefill 结构，不落库）**
```
list[{ ...明细行字段(按各循环明细 schema) , source:"four-table" }]  # 仅明细完全空时
```

## Correctness Properties

### Property 1: D-cycle 锚点保存不写 parsed_data + 返回 evaluated_value + 不做 DB 写回
主开关 ON 且 target_cell ∈ known_anchors 时，保存 auto_calc **跳过** write_cell_to_parsed_data（parsed_data 该 cell 不被写）、响应返回 evaluated_value、且不向 checklist_responses/DB 持久化任何值。
**Validates: Requirements 1.1, 1.2**

### Property 2: 非锚点走 parsed_data 零回归
target_cell ∉ known_anchors（普通网格 cell / 非 D-cycle）时，沿用 write_cell_to_parsed_data，行为与改动前一致。
**Validates: Requirements 1.3, 6.1**

### Property 3: 求值失败不静默落空
保存求值失败/有 eval_errors 时，返回 eval_warnings 且不返回错误/0 的 evaluated_value。
**Validates: Requirements 1.4**

### Property 4: 口径统一
保存求值、GET value、render seed 三处 Tier A 求值均经 get_active_filter（与 Tier B 同数据集版本）。
**Validates: Requirements 1.5, 2.1, 7.2**

### Property 5: GET Tier A 附 value 且 fail-open
flag ON + D-cycle 时每条 Tier A 填 value；单条求值失败 value=None 不阻断其它条目与整体 GET。
**Validates: Requirements 2.1, 2.3**

### Property 6: render Tier A transient seed 手工优先 + 写对字段
render seed TB 核对行仅在锚点持久层完全空时并入（已有非空用户值 / source=disabled → 不覆盖）；seed 写入前端实际读取的 responses_snapshot 字段（remark|conclusion），round-trip 可被前端读到。
**Validates: Requirements 3.1, 3.2, 3.3, 3.7**

### Property 7: 默认预设 render seed 等价 tb_amount
未被用户编辑的默认 Tier A 预设求值结果与现 project_context.tb_amount 口径一致（默认行为不变）。
**Validates: Requirements 3.6**

### Property 8: 明细 seed 手工优先 + 子开关门控
明细自动 seed 仅在主开关 ∧ `D_CYCLE_DETAIL_SEED_ENABLED` ∧ 明细表完全空时并入；已有任一行 → 不 seed；子开关关 → 无 detail seed。
**Validates: Requirements 4.1, 4.2, 5.2**

### Property 9: 明细 seed 复用既有函数不新造
明细 seed 调既有后端归集函数/聚合（必要时先抽取的纯函数），不新增第 3 套四表库读取。
**Validates: Requirements 4.3, 4.4, 7.2**

### Property 10: 灰度关闭零回归
主开关 OFF 时保存走旧 parsed_data、GET 无 extraction、render 无 Tier A seed；子开关 OFF 时无 detail seed；全部逐字节等价前置 spec 状态。
**Validates: Requirements 1.6, 2.4, 3.5, 5.1, 5.3**

### Property 11: 独立可回退 + fail-open
P0-1 受主开关、P0-2 受主∧子开关，二者路径独立；任一 render seed / 求值出错始终 fail-open（含严重/系统级错误），不阻断该底稿其它内容或其它底稿。
**Validates: Requirements 4.5, 5.2, 5.3, 5.4, 3.4**

### Property 12: 四表库只读 + logic_check 不改值
四表库不被写；auto_calc target 指向四表库仍拒；logic_check/reasonability 不写回锚点/网格。
**Validates: Requirements 6.2, 6.3, 6.4**

### Property 13: seed 全程 transient 不落库
render 的 Tier A seed 与 P0-2 明细 seed 均只进返回 payload（responses_snapshot / detail_prefill），不写 checklist_responses/DB；仅用户手工编辑才持久化。
**Validates: Requirements 1.2, 3.1, 4.1**

## Error Handling

- 保存求值失败 → 不返回错误/0 evaluated_value + `payload.eval_warnings`（Property 3）；不写 parsed_data、不写 DB。
- GET 单条 Tier A 求值失败 → value=None，继续其它（Property 5）。
- render Tier A seed 求值失败 → `logger.warning`（非用户通知）+ 静默沿用 project_context.tb_amount（Property 11，始终 fail-open）。
- 明细归集失败 → `logger.warning` + 空 detail seed（Property 11）。
- 无 checklist_responses/DB 写回路径（决策1），故无写库/项目 ID/冲突处理面。

## Testing Strategy

- 后端 PBT/单测（`tests/d_cycle_extraction/`）：Property 1–13，保存跳过 parsed_data + 返回 evaluated_value + 不写库 / GET value / render transient seed 手工优先+写对字段 / 明细 seed 手工优先+子开关，用 fake async session + mock resolver。
- 契约守卫（扩 `test_contract_guards.py`）：G6（D-cycle 锚点保存不写 parsed_data 且不写 DB、返回 evaluated_value）、G7（明细复用既有函数不新造）、G8（GET value/render seed 同经 get_active_filter）。
- render 集成：D6（P0-1 transient seed + P0-2 D6-2 明细 seed）主/子开关开·关零回归 + 手工优先 + fail-open。
- 前端 vitest：`FormulaStatusPanel` Tier A value 显示真实求值（不再恒 `—`）；D-cycle 组件保存后用 evaluated_value 即时更新核对行。
- Playwright（收尾，需实例化项目）：编辑 Tier A 公式保存 → 底稿锚点变化；打开 D6-2 空明细 → 自动 seed；手工覆盖后重开不被回写。
