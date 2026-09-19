# Requirements Document

## Introduction

本 spec 解决「四表库（`trial_balance` 试算表 / `tb_balance` 余额表 / `tb_ledger` 序时账 / `tb_aux_balance` 辅助余额表）中已有的数据，自动、系统地提取填充到 D1–D7 底稿（应收票据 / 应收账款 / 预收账款 / 营业收入 / 应收款项融资 / 合同资产 / 合同负债），并让能表达为公式的提取在底稿当前页面公式管理中**可查看、可编辑**」这一主线。

经复盘（逐 render 策略 + 评估器 + 既有 prefill 范式实测），修正初版设计，采用**两层**架构，避免造第 3/4 套 prefill 机制：

- **Tier B（批量自动填充，占大头）**：D1–D7 补齐平台已成熟的 `_build_adjudication_prefill` 范式（K/M/N 循环已有：直查 `tb_balance` 多级子科目 + `get_active_filter` 数据集版本 + 只取叶子科目防双算 + 手工优先）。D1–D7 现只从 `trial_balance` 取一个科目前缀标量 `tb_amount`，是真正缺口。补齐即交付大部分「自动提取填充」，零新机制、与全平台一致。
- **Tier A（可编辑提取公式）**：把能表达为单条公式的简单提取（科目/子目总额）注册为可编辑 `wp_formula`，在底稿页面公式管理中查看/编辑；分类/账龄/客户/叶子按名归集等复杂 prefill（Tier B）**不伪装成可编辑公式**，改为只读溯源展示。

### 实测缺口（非猜测）

1. **D1–D7 无 `_build_adjudication_prefill`**：K/M/N（`_k1`/`_k9`/`_n5`/`_m*`）已有 `tb_balance` 叶子级 + `get_active_filter` + 手工优先的审定表预填，返回 `adjudication_prefill`；D1–D7 只取 `trial_balance` 标量 `tb_amount`（供 TB↔审定核对行），审定表未审分类行/子目全空。
2. **公式管理面板坏的**：`FormulaStatusPanel.vue` 调 `GET /api/projects/{pid}/workpapers/{wpId}/formulas`（不存在，真实端点 `GET /api/workpapers/{wp_id}/formulas` 返 `{items}` 非 `{formulas}`）→ catch 恒空；且只读无编辑。
3. **评估器口径漂移**：公式管理 PUT 用的 `evaluate_wp_formula_expression` 只支持 `TB/SUM_TB/WP` 正则，**不支持 `AUX/PREV/序时账`**，且读裸 `trial_balance`+`is_deleted`（**不用 `get_active_filter`**，可能读 superseded/staged）；而 Tier B prefill 用 `tb_balance`+`active_filter`+叶子级。二者若不统一，面板求值值 ≠ render 填充值（双真源发散）。

## Requirements

### Requirement 1: Tier B 四表库审定表预填补齐（对齐 `_build_adjudication_prefill` 范式）

**User Story:** 作为审计助理，我打开 D1–D7 底稿时希望审定表未审数已从四表库子科目自动填好，与 K/M/N 循环体验一致。

#### Acceptance Criteria

1. WHEN D1–D7 底稿 render AND 审定表相关锚点无持久化用户值 THEN 系统 SHALL 从 `tb_balance` 该科目前缀（D1=1121 / D2=1122 / D3=2203 / D4=6001 / D5=1124 / D6=1402 / D7=2205）的**叶子子科目**（`account_code != 前缀` 且非其它 code 前缀）汇总取数，返回 `adjudication_prefill`（对齐 K9/K1/N5 的 render 返回结构）。
2. WHERE 科目为余额类（D1/D2/D3/D5/D6/D7） THE 系统 SHALL 取 `opening_balance`/`closing_balance`（期初/期末余额）；WHERE 科目为发生额类（D4 收入 6001） THE 系统 SHALL 取 `debit_amount`/`credit_amount` 发生额（或序时账），方向与该科目一致。
3. WHEN 查询四表库 THEN 系统 SHALL 用 `get_active_filter(db, TbBalance.__table__, project_id, year)`（数据集版本过滤），不用裸 `is_deleted`。
4. WHEN 汇总子科目 THEN 系统 SHALL 只取叶子科目（防中间级 rollup 与子科目双算），跳过零发生/零余额与无名称子科目。
5. WHERE 某审定表锚点在 `checklist_responses` 已有非空用户值（手工录入或既有一键取数结果） THE 系统 SHALL 不覆盖它（手工优先）。
6. IF `tb_balance` 无该科目子科目 THEN 系统 SHALL 返回空 `adjudication_prefill`（前端回退默认/空，不报错、不阻断 render）。

### Requirement 2: Tier B 前端消费预填种子（尊重手工覆盖 + 来源标注）

**User Story:** 作为审计助理，自动填的数应显示为自动取数、可被我手工覆盖，且覆盖后不被回写。

#### Acceptance Criteria

1. WHEN D1–D7 专属组件收到 `adjudication_prefill` AND 对应行无持久化值 THEN 组件 SHALL 据此建行/填未审数，标注来源（自动取数）。
2. WHEN 用户手工修改自动取数值并保存 THEN 该锚点 SHALL 视为已填，后续 render 的预填 SHALL 不再覆盖它。
3. WHERE 既有手工「一键取数」按钮（D3/D5/D6/D7 `import-aux-balance`、D4 序时账拉取）与自动预填写同一锚点 THE 系统 SHALL 定义精度：自动预填仅在锚点完全空时并入；一键取数/明细导入结果视为已填，不被自动预填覆盖。
3. WHEN 灰度开关关闭 THEN 前端 SHALL 表现同当前（无 `adjudication_prefill` 消费），零回归。

### Requirement 3: Tier A 简单提取注册为可编辑公式

**User Story:** 作为审计助理/复核人，我希望能在底稿页面公式管理里看到并编辑「从某科目取某列」这类简单提取公式。

#### Acceptance Criteria

1. WHERE 提取可表达为单条公式（科目/子目总额，如 `TB('1402','期末余额')` / `SUM_TB('起始~结束','列')`） THE 系统 SHALL 支持将其注册为 `formula_type='auto_calc'` 的 `wp_formula`，`target_cell` 为该字段的 `checklist_responses` item_id（锚点），`sheet_name` 为该 sheet 编码。
2. WHERE 提取为分类/账龄/客户/叶子按名归集（Tier B） THE 系统 SHALL NOT 将其注册为可编辑公式（无法用单条公式表达），改由 Req1 的 prefill 承担 + Req5 只读溯源展示。
3. WHEN 系统需某 wp_code 的 Tier A 默认公式 THEN 系统 SHALL 从预设库（`d_cycle_extraction_presets.json`，按 wp_code → 锚点/表达式/说明）读取，读时与用户已存 `wp_formula` 收敛（同锚点用户覆盖预设，预设不落库）。
4. IF 某 D-cycle 字段无法从四表库映射（审计判断/说明文本） THEN 预设库 SHALL 不为其生成公式（宁缺勿造）。

### Requirement 4: 统一评估器口径（消除双真源漂移）

**User Story:** 作为平台维护者，我要求公式管理里保存/求值的值与渲染时填充的值口径一致，来源同一。

#### Acceptance Criteria

1. WHEN Tier A 公式经公式管理保存/即时求值 THEN 求值 SHALL 与 Tier B 预填共用同一数据源口径：读四表库用 `get_active_filter`（数据集版本），不用裸 `is_deleted`。
2. WHERE Tier A 允许的函数集 THE 系统 SHALL 明确并强制：至少支持 `TB`/`SUM_TB`（与 Tier B 同口径的 `tb_balance`/`trial_balance` 读）；IF 决定支持 `AUX`/`PREV`/序时账 THEN 系统 SHALL 在评估路径（`evaluate_wp_formula_expression` 或其调用的引擎）真实实现之，ELSE 系统 SHALL 在保存时拒绝这些不受支持函数（返 422），不静默落空返 0。
3. WHEN 同一四表库快照下多次求值同一 Tier A 公式 THEN 结果 SHALL 一致（幂等）。
4. WHERE 求值失败/引用不存在 THE 系统 SHALL 返 None/记 issue，不产错值、不阻断。

### Requirement 5: 底稿页面公式管理可查看和编辑

**User Story:** 作为审计助理/复核人，我希望在底稿当前页面公式管理里，按 sheet 看到 Tier A 可编辑公式与 Tier B 只读溯源，并能编辑/恢复默认/禁用。

#### Acceptance Criteria

1. WHERE 公式管理面板此前端点错配（`FormulaStatusPanel` 调不存在的 projects 作用域端点、解析 `data.formulas`） THE 系统 SHALL 修正为真实端点 `GET /api/workpapers/{wp_id}/formulas` 并解析 `items`，不再恒空。
2. WHEN 打开公式管理面板 THEN 系统 SHALL 列出该底稿 Tier A 有效公式（预设 ∪ 用户）与 Tier B 只读溯源描述，按 sheet 分组（可按当前 sheet 过滤），展示锚点/表达式/来源（预设/自定义/只读）/当前值。
3. WHEN 用户编辑 Tier A 公式并保存 THEN 系统 SHALL 经 `PUT /api/workpapers/{wp_id}/formulas` 落库（覆盖预设），保存前经悬空引用校验（`not_found` 返 422 不写库）。
4. WHEN 用户对已覆盖预设的公式点「恢复默认」 THEN 系统 SHALL 删除用户 `wp_formula` 使其回落预设。
5. WHEN 用户「禁用」某预设提取 THEN 系统 SHALL 记录禁用标记使该锚点不再自动填充（区别于恢复默认）。
6. WHERE GET 面板列表 THE 系统 SHALL 复用 render 已算的 seed 值展示，不对每条公式在 GET 时逐条重求值（避免慢/N+1）。
7. IF 用户无底稿编辑权限 THEN 编辑/保存/删除/禁用入口 SHALL 禁用或拒绝（沿用既有权限），只读用户仍可查看。

### Requirement 6: 锚点真实键发现与合法性校验（最高风险前置）

**User Story:** 作为实现者，我要保证提取种子写到底稿真实字段，而不是静默丢失。

#### Acceptance Criteria

1. WHEN 为某 D-cycle 编写预设/prefill THEN 系统 SHALL 先从该循环专属组件 composable（`useD6Adjudication`/`useD6Detail` 等）反查真实 `checklist_responses` item_id 键作为锚点，不臆造。
2. WHERE 锚点被用作 Tier A 公式 target_cell 或 Tier B 种子目标 THE 系统 SHALL 校验其属于该 wp_code 的已知锚点集合；未知锚点 SHALL 拒绝/告警，不静默写空。
3. WHEN 交付 THEN 系统 SHALL 产出每 D-cycle 的锚点-来源对照表（覆盖字段 vs 未覆盖字段，宁缺勿造清单）。

### Requirement 7: 零回归、灰度可回退、复用而非另造

**User Story:** 作为平台维护者，我要求不破坏 D1–D7 现有链路，可灰度回退。

#### Acceptance Criteria

1. WHERE 引入 Tier B 预填与 Tier A 公式 THE 系统 SHALL 受灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False）控制，关闭时 render 逐字节等价当前。
2. WHEN 接入 THEN 系统 SHALL 只新增 `adjudication_prefill`/公式列出，不删除/改写既有 `tb_amount` 核对行、手工一键取数、明细导入导出、审定 TB 核对、附注联动。
3. WHERE Tier B 取数 THE 系统 SHALL 复用既有 `_build_adjudication_prefill` 范式与 `get_active_filter`，不新造第 3 套四表库读取。
4. WHEN D1–D7 逐个接入 THEN 系统 SHALL 增量、可回退（单循环失败不阻断其他），先 D6/D2 试点。

### Requirement 8: 正确性属性可测

**User Story:** 作为质控，我希望关键正确性属性有属性测试守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖：R1.4 只取叶子防双算、R1.5/R2.2 手工优先不覆盖、R1.6 无数据→空不报错、R3.3 读时收敛、R4.1 active_filter 同口径、R4.2 不支持函数保存拒绝、R4.3 幂等、R5.4 恢复默认回落、R5.5 禁用、R7.1 灰度零回归、R6.2 未知锚点拒绝 等属性。
2. WHERE Tier A 求值 THE 属性测试 SHALL 断言来源可溯（每个种子值可回指其公式/prefill 来源）。

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张源数据表 |
| Tier B 预填 | 对齐 `_build_adjudication_prefill` 的批量审定表预填：`tb_balance` 叶子级 + `get_active_filter` + 手工优先，render 返回 `adjudication_prefill` |
| Tier A 公式 | 可表达为单条公式（TB/SUM_TB…）的简单提取，注册为可编辑 `wp_formula`，锚点=checklist_responses item_id |
| `_build_adjudication_prefill` | K/M/N 循环既有的四表库→审定表预填范式（本 spec 为 D1–D7 补齐） |
| get_active_filter | 四表查询统一入口（数据集版本 staged/active/superseded，禁裸 is_deleted） |
| 锚点 (anchor) | D-cycle 字段的 `checklist_responses` item_id（如 `D6-1-block1-endUnadjusted`） |
| 只取叶子 | 汇总时只取无更深子科目的 code，防中间级 rollup 双算 |
| 手工优先 | 锚点已有非空用户值（含一键取数结果）时不被自动预填覆盖 |
| 预设库 | `d_cycle_extraction_presets.json`，Tier A 默认公式，读时与用户 wp_formula 收敛 |
| 评估器口径统一 | Tier A 求值与 Tier B 预填共用 `get_active_filter` 数据源，消除双真源漂移 |
| 公式管理面板 | 底稿侧面板"公式"Tab（`FormulaStatusPanel`），列 Tier A 可编 + Tier B 只读溯源 |
| 灰度开关 | `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`，默认关，关闭时 render 零回归 |
