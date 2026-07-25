# Requirements Document

## Introduction

本 spec 是 `d-cycle-four-table-extraction-formulas`（已完成）的**增量**，闭合其复盘发现的两个 P0 缺口——即让"提取公式在底稿页面公式管理中**可编辑且编辑真生效**"、"四表库有的内容**自动**填充（而非手工一键取数）"从半成品变为端到端可用。

前置 spec 已交付：Tier B（`build_d_adjudication_prefill` tb_balance 叶子级预填，仅 D6 真 seed）+ Tier A（`resolve_effective` 读时收敛的可编辑公式，预设 ∪ 用户 wp_formula）+ 评估器口径统一（`get_active_filter`）+ 公式管理面板分层展示 + 灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` + 审定/未审语义标注（P1-4）+ preset 锚点运行时守卫（P1-5）。

**复盘实证的两个 P0 缺口**：

- **P0-1：Tier A 可编辑公式对 D-cycle 实际脱钩（编辑基本无效）**。三处断裂：
  ①保存 auto_calc 公式时 `write_cell_to_parsed_data(cell_ref=target_cell)` 写进 **parsed_data 网格**，但 D-cycle 专属组件读 **checklist_responses（item_id 锚点）**，两存储不相交 → 编辑结果组件永不读；design 决策2 明写"走 checklist_responses 通道"但该路径从未实现。
  ②`GET /formulas` 的 Tier A `value` 恒 None → 面板只显示表达式不显示求值结果，审计师无法核对。
  ③render 的 TB 核对行 seed 来自既有硬编码 `project_context.tb_amount`，不是 Tier A 公式 → 改公式（期末余额→年初余额）底稿数字不变。
- **P0-2：真正 end-to-end 的"自动填充"只有 D6 审定表一处**。明细表维度归集（tb_aux_balance 客户/产品维度、序时账期后归集）是"四表库有的内容"的主体，但仍是前端**手工「一键取数」按钮**，非 render 自动 seed。

**收敛铁律（继承前置 spec）**：复用既有机制不新造第 3 套四表库读取；`get_active_filter` 唯一四表查询入口；四表库只读、写落 checklist_responses；手工优先；灰度默认关零回归；共享 `wp_formula` 端点对非 D-cycle 底稿零回归。

## Glossary

| 术语 | 含义 |
|------|------|
| Tier A | 可表达为单条 `TB('code','列')`/`SUM_TB` 的简单科目总额提取公式，注册为可编辑 `wp_formula`，`target_cell` = checklist_responses item_id 锚点 |
| Tier B | 四表库叶子级/维度级批量预填（`build_d_adjudication_prefill` 或明细归集 resolver），render 返回 seed，只读溯源不可编辑 |
| 锚点（anchor） | D-cycle 底稿字段的真实 `checklist_responses` item_id，登记于 `d_cycle_anchor_registry.json`，`is_known_anchor(wp_code, anchor)` 校验 |
| known_anchors | 某 wp_code 已登记的合法锚点集（精确 + `re:` 模式） |
| checklist_responses | D-cycle 专属组件的数据存储（item_id → value），区别于 parsed_data 网格 |
| parsed_data 网格 | 通用 grid 底稿的单元格存储（sheet!cell → value），D-cycle 组件不读 |
| resolve_effective | 读时收敛 Tier A 有效绑定（预设 ∪ 用户 wp_formula，禁用 > custom > preset） |
| 手工优先 | 自动 seed 仅在锚点/明细完全空（无非空用户值/无行）时并入；已有值/行不覆盖 |
| TB 核对行 | 审定表中与试算表审定数核对的标量行（如 `D6-1-tb-amount`/`D2-adj-tb-amount`），Tier A 公式的目标 |
| 主灰度开关 | `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False，前置 spec 已有），门控 P0-1 全部新行为 |
| P0-2 子开关 | `D_CYCLE_DETAIL_SEED_ENABLED`（默认 False，本 spec 新增），门控 P0-2 明细自动 seed，且被主开关 AND |
| transient seed | render 把求值/归集结果放入返回 payload（`responses_snapshot` / `detail_prefill`）供前端消费，**不 DB 持久化**；手工优先，只在锚点/明细完全空时并入（对齐 D6 Tier B `adjudication_prefill`） |
| 明细表归集 | 明细表按客户/产品/月维度从 tb_aux_balance/序时账聚合的行数据（前端既有一键取数） |

## Requirements

### Requirement 1: Tier A auto_calc 保存不写错库 + 返回求值供即时显示（不做 DB 写回）

**User Story:** 作为审计师，我希望编辑 Tier A 提取公式并保存后，底稿核对行不再被写进它读不到的 parsed_data 网格（无效），而是保存后即时看到求值结果、并在重新打开时由公式驱动填充（render seed 见 Requirement 3），让"可编辑"名副其实。

#### Acceptance Criteria

1. WHEN 保存的 auto_calc 公式其 `target_cell` ∈ 该底稿 `known_anchors(wp_code)`（D-cycle 锚点）且主灰度开关开，THE 系统 SHALL 跳过 `write_cell_to_parsed_data`（该 cell 对 D-cycle 专属组件无意义，写入=误导），并在响应返回 `evaluated_value` 供前端即时本地显示。
2. WHEN 保存 D-cycle 锚点 auto_calc 公式，THE 系统 SHALL NOT 向 `checklist_responses` / DB 持久化该求值结果（持久化交由 Requirement 3 的 render transient seed + 用户手工编辑负责，避免"公式派生值"与"真人工值"来源混淆及持久后冻结不刷新）。
3. WHERE `target_cell` ∉ known_anchors（普通网格 cell 或非 D-cycle 底稿），THE 系统 SHALL 沿用现有 `write_cell_to_parsed_data`（parsed_data 网格），行为逐字节不变。
4. WHEN 保存公式求值失败或产生 eval_errors，THE 系统 SHALL 返回 eval_warnings 且 SHALL NOT 返回错误/0 的 `evaluated_value`（不静默落空）。
5. THE Tier A 保存求值 SHALL 经 `get_active_filter`（与 Tier B 预填同数据集版本口径）。
6. WHEN 主灰度开关关闭，THE 保存路径 SHALL 对 D-cycle 锚点也沿用现有 parsed_data 写回行为（不跳过），保持逐字节零回归。

### Requirement 2: GET /formulas 的 Tier A 附求值结果 value

**User Story:** 作为审计师，我希望公式管理面板显示每条 Tier A 公式的当前求值结果，以便核对公式产出什么。

#### Acceptance Criteria

1. WHEN `GET /api/workpapers/{wp_id}/formulas` 且灰度开且 D-cycle 底稿，THE 系统 SHALL 对每条 Tier A binding 求值并填其 `value`（经 `get_active_filter`）。
2. THE Tier A 求值 SHALL 避免 N+1（同科目/批量合并查询，或条目数有界的逐条求值），GET 响应时延不显著增加。
3. WHEN 单条 Tier A 求值失败，THE 该条 `value` SHALL 为 None 且 SHALL NOT 阻断其它条目或整个 GET（fail-open）。
4. WHEN 灰度关闭或非 D-cycle 底稿，THE 响应 SHALL 无 `extraction` 字段，与前置 spec 现状逐字节一致（零回归）。
5. THE Tier B 只读溯源条目 `value` SHALL 仍为 None（不重求值，seed 值由 render 的 adjudication_prefill 提供，行为不变）。

### Requirement 3: render 用 Tier A 公式驱动 TB 核对行 seed

**User Story:** 作为审计师，我编辑 Tier A 公式后重新打开底稿时，TB 核对行应按我改的公式取数，而不是永远显示硬编码值。

#### Acceptance Criteria

1. WHEN D-cycle render 且主灰度开关开，THE 系统 SHALL 用 `resolve_effective` 的有效 Tier A 公式求值，**transient seed** 对应锚点（TB 核对行）进 `responses_snapshot` payload（**不 DB 持久化**，对齐 D6 Tier B `adjudication_prefill`），其结果优先于硬编码 `project_context.tb_amount`。**此为使"编辑公式即生效"成立的主机制**（每次打开按当前有效公式重算）。
2. WHERE 某 Tier A 锚点在 `checklist_responses`（持久层）已有非空用户值，THE render SHALL NOT 覆盖（手工优先——仅真人工编辑会持久，故不会被公式 seed 误挡）。
3. WHERE 某 Tier A 绑定 source=disabled（用户禁用），THE render SHALL NOT seed 该锚点。
4. WHEN render 求值失败（含公式错误，或严重/系统级错误），THE 系统 SHALL **始终 fail-open**——静默沿用现有 `project_context.tb_amount` 或留空、不向用户提示、不阻断 render（内部可 `logger.warning` 记录，属非用户可见日志而非用户通知）。
5. WHEN 主灰度开关关闭，THE render 返回值 SHALL 与前置 spec 灰度关状态逐字节一致（零回归，不新增 Tier A seed）。
6. WHERE 默认预设未被用户编辑，THE Tier A 公式求值结果 SHALL 与现有 `project_context.tb_amount` 口径一致（默认行为不变，仅用户编辑/禁用时才改变）。
7. THE render seed SHALL 写入前端专属组件对该锚点实际读取的 `responses_snapshot` 字段（`remark` 或 `conclusion`，逐锚点从 composable 核实，避免错列导致 round-trip 断裂）。

### Requirement 4: 明细表四表库维度归集 render 自动 seed（P0-2，试点增量）

**User Story:** 作为审计师，我希望打开 D-cycle 明细表时，四表库有的维度明细（客户/产品/月）自动填充，而不必每次手动点"一键取数"。

#### Acceptance Criteria

1. WHEN D-cycle 明细表 render 且主灰度开关开且 P0-2 子开关 `D_CYCLE_DETAIL_SEED_ENABLED` 开且该明细表行完全空，THE 系统 SHALL 调用既有后端归集（tb_aux_balance/序时账 resolver）**transient seed** 明细行到 render 返回（`detail_prefill` payload，**不 DB 持久化**，对齐 D6 Tier B）。
2. WHERE 明细表已有任一行（手工录入或既有一键取数结果），THE 系统 SHALL NOT 自动 seed（手工优先，不覆盖）。
3. THE 明细归集 SHALL 复用既有后端 resolver/聚合逻辑，SHALL NOT 新造第 3 套四表库读取。
4. IF 目标明细归集逻辑仅存在于 HTTP handler（如 `/import-aux-balance`）而非可复用后端函数，THEN 实现 SHALL 先将聚合抽取为纯函数（不改原 HTTP 端点行为）再供 render 调用；此核实为 P0-2 前置（Wave 0）。
5. WHEN 归集查询失败，THE 系统 SHALL fail-open 返回空明细 seed（不阻断 render）。
6. THE 前端手工"一键取数"按钮 SHALL 保留（自动 seed 为叠加，用户仍可手动刷新/覆盖）。
7. THE P0-2 SHALL 逐循环增量落地、单循环可回退，先以一个循环的明细表试点（D6-2；不要求一次覆盖全部 D1–D7 明细）。

### Requirement 5: 灰度与独立可回退

**User Story:** 作为技术负责人，我希望本增量默认关闭零回归，且 P0-1 与 P0-2 能独立灰度、单独回退。

#### Acceptance Criteria

1. THE P0-1（Requirement 1/2/3）新行为 SHALL 受**主开关** `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False）门控。
2. THE P0-2（Requirement 4）明细自动 seed SHALL 额外受**子开关** `D_CYCLE_DETAIL_SEED_ENABLED`（默认 False）门控，且被主开关 AND（主开关关则子开关无效）；故可"发 P0-1、压 P0-2"实现真正独立灰度与回退。
3. WHEN 任一开关关闭，THE 相应行为 SHALL 逐字节等价前置 spec 状态（零回归）；P0-1 与 P0-2 代码路径独立，其一失败不牵连其二。
4. WHEN 任一 D-cycle 循环的 render seed 出错，THE 系统 SHALL fail-open，不影响其它循环或其它底稿。

### Requirement 6: 共享端点与四表库只读零回归

**User Story:** 作为技术负责人，我希望改共享 `wp_formula` 端点与 render 不破坏非 D-cycle 底稿、不破坏四表库只读契约。

#### Acceptance Criteria

1. THE `PUT /api/workpapers/{wp_id}/formulas` 现有 parsed_data 网格写回行为 SHALL 对**所有底稿类型**逐字节不变；D-cycle 锚点的 checklist_responses 写回为**新增附加分支**（仅灰度开 + `target_cell` ∈ known_anchors 时启用），不修改现有网格写回路径。
2. THE 四表库（trial_balance/tb_balance/tb_ledger/tb_aux_balance）SHALL 保持只读；写入仅落 checklist_responses / parsed_data，不写四表库。
3. THE auto_calc 公式 target 指向四表库仍 SHALL 拒绝（沿用既有只读守卫）。
4. THE logic_check / reasonability 类型公式 SHALL NOT 改值（不写回锚点或网格，沿用既有语义）。

### Requirement 7: 正确性属性可测

**User Story:** 作为技术负责人，我希望关键不变量以属性/契约测试锁定，防回归与漂移。

#### Acceptance Criteria

1. THE 手工优先、灰度零回归、写对存储（checklist_responses vs parsed_data）、口径统一、fail-open、复用不新造 等不变量 SHALL 由 PBT/契约测试覆盖。
2. THE 契约守卫 SHALL 断言：D-cycle 锚点求值走 checklist_responses 写路径、明细归集复用既有 resolver（不新造）、评估器与 render 同经 get_active_filter。
