# Requirements Document

## Introduction

本 spec 解决「F2 存货底稿从四表库（`trial_balance` 试算表 / `tb_balance` 余额表 / `tb_ledger` 序时账 / `tb_aux_balance` 辅助余额表）刷新取数」这一主线，把 F2-1 审定表的四表库取数从**一次性静默 seed**升级为**显式取数公式驱动、可刷新、可查看可编辑**，对齐 E1 货币资金（`E1FourTableSourcePanel` + `TB()` 公式 + 🔄重新取数）与 D 循环（`d_cycle_extraction_presets.json` + 锚点注册 + Tier A/B 两层）已证范式。

### 实测现状与缺口（非猜测，逐文件核实）

F2-1 审定表**已有**四表库取数：后端 `_f2_inventory_main.py::_build_adjudication_prefill` 按 `F2_CATEGORIES`（rowKey→科目，前端 `f2AccountModel.ts` ∥ 后端一致）从 `tb_balance` 取各类别期初/期末余额，前端 `useF2Adjudication.seedFromTbValues()` 消费。三个真实缺口：

1. **无显式取数公式预设**：取数是后端黑盒启发式，`TB('1401','期末余额')` 这类公式没有任何地方被显式预设。`wp_surfaced_f.py` 的 F2-1「取数」条目只写「取自 F2-3~13 明细」「取自 F2-14 调整分录」（**跨表**），**没有 tb_balance 的 TB() 取数公式**——而实际驱动 F2-1 未审数的正是这条四表库取数。审计师在公式管理中心看不到「原材料期末 ← TB('1401','期末余额')」。
2. **一次性静默 seed，无刷新入口**：`seedFromTbValues()` 靠 `seeded` 标志 + 空表判定，**只在完全空表时 seed 一次**。余额表重导入 / 想重新取数时没有 🔄刷新取数 入口（E1 有）。
3. **取数口径不稳健**：后端用 `_row_depth` + `by_depth[max(keys)]`（取最深层级），而非 D 循环/E1 已验证的 `_is_leaf` 叶子判定 → 类别下混合层级子科目时有 rollup 双算风险；前端 seed 还用 `closing−opening` 粗猜 increase/decrease（应分别取 tb_balance 借/贷发生额）。

### F2 与 D 循环的关键差异（决定本 spec 更适合 Tier A）

D 循环审定表按信用风险组合/账龄/客户分类，**无法用单条 TB 公式表达**（宁缺勿造，只做 Tier B）；而 **F2-1 审定表是 13 个固定类别（每类恰好对应一个存货科目）**，故每个类别行的期初/本期增加/本期减少/期末**都能干净地表达为 `TB(account, 列)`**，是理想的 **Tier A 可编辑取数公式**载体。这是 F2 相较 D 循环的核心差异。

### 诚实的取数边界（宁缺勿造）

四表库中只有 `tb_balance`（科目级）适合 F2-1 审定表的类别级取数。**F2-3~F2-13 明细表是存货项目/规格级**（`tb_balance` 只有科目总额、无项目明细），故明细表项目行**不做四表库取数**（除非 Wave 0 核实 `tb_aux_balance` 确有存货规格/仓库维度，有则作可选补充，宁缺勿造）；F2-2 明细汇总是跨表聚合（F2-3~13 + F2-1），非四表库取数，不在本 spec。

## Requirements

### Requirement 1: F2-1 审定表 Tier A 取数公式预设

**User Story:** 作为审计助理，我希望 F2-1 审定表每个类别行的期初/增加/减少未审数由显式的 `TB(科目, 列)` 取数公式驱动，而不是黑盒启发式。

#### Acceptance Criteria

1. WHEN 系统需要 F2 的 Tier A 默认取数公式 THEN 系统 SHALL 从预设库（`f2_extraction_presets.json` 或平台既有预设库结构，按 wp_code=F2 → 锚点/表达式/说明）读取，读时与用户已存 `wp_formula` 收敛（同锚点用户覆盖预设，预设不落库）。
2. WHERE 类别为原值类（1401 原材料 / 1402 材料采购在途 / 1403 周转材料 / 1404 自制半成品 / 1405 委托加工物资 / 1406 库存商品 / 1407 发出商品 / 1408 开发产品 / 1409 开发成本 / 1410 合同履约成本 / 1411 消耗性生物资产 / 1412 商品进销差价） THE 预设 SHALL 为对应锚点提供：期初 = `TB(account,'期初余额')`、本期增加 = `TB(account,'借方发生额')`、本期减少 = `TB(account,'贷方发生额')`。
3. WHERE 类别为跌价准备（1471，备抵科目、贷方余额） THE 预设 SHALL 取绝对值口径：期初 = `ABS(TB('1471','期初余额'))`、本期增加（计提）= `TB('1471','贷方发生额')`、本期减少（转回/核销）= `TB('1471','借方发生额')`。
4. WHERE 提取为存货项目/规格级明细（F2-3~13） THE 系统 SHALL NOT 为其注册可编辑取数公式（`tb_balance` 无项目级数据，无法用单条公式表达，宁缺勿造）。
5. IF 某锚点无法从四表库映射（审计判断/文本/账项调整） THEN 预设库 SHALL 不为其生成取数公式。
6. WHEN 交付 THEN 预设库每条 `target_cell` SHALL 属于从 `useF2Adjudication.ts` 反查的真实 `checklist_responses` item_id 锚点集（不臆造）。

### Requirement 2: 公式管理中心可查看可编辑 F2 取数公式

**User Story:** 作为审计助理/复核人，我希望在 F2 底稿页面公式管理里，按 sheet 看到 F2-1 各类别的 `TB()` 取数公式，并能编辑/恢复默认。

#### Acceptance Criteria

1. WHEN 打开 F2 底稿的公式管理面板 THEN 系统 SHALL 列出 F2-1 的 Tier A 有效取数公式（预设 ∪ 用户），展示锚点/表达式/来源（预设/自定义）/当前值，按 sheet 分组。
2. WHEN 用户编辑某 Tier A 取数公式并保存 THEN 系统 SHALL 经既有 `PUT /api/workpapers/{wp_id}/formulas` 落库（覆盖预设），保存前经悬空引用/不受支持函数校验（非法返 422 不写库）。
3. WHEN 用户对已覆盖预设的公式点「恢复默认」 THEN 系统 SHALL 删除用户 `wp_formula` 使其回落预设。
4. WHERE F2 取数公式作为只读溯源同时展示 THE 系统 SHALL 复用 `wp_surfaced_f.py` 的 surfacing（把 F2-1 现有的模糊「取自 F2-3~13 明细」补充/替换为显式 `TB(account,列)` 四表库取数条目），使公式管理中心真实反映四表库取数来源。
5. WHERE 公式管理面板 GET 列表 THE 系统 SHALL 按选中 sheet 过滤（复用 E1/D 已证的 sheet_codes 过滤），不逐条 GET 时重求值（避免慢/N+1）。
6. IF 用户无底稿编辑权限 THEN 编辑/保存/删除入口 SHALL 禁用或拒绝（沿用既有权限），只读用户仍可查看。

### Requirement 3: 🔄从四表库刷新取数入口（本 spec 核心 = 完整刷新）

**User Story:** 作为审计助理，余额表重导入或想重新对齐四表库时，我希望能一键从四表库刷新 F2-1 审定表未审数，而不是只能在空表时 seed 一次。

#### Acceptance Criteria

1. WHEN F2-1 审定表工具栏 THEN 系统 SHALL 提供「🔄从四表库刷新取数」入口（对齐 E1 `E1FourTableSourcePanel` 的 🔄重新取数），可用性受编辑权限门控。
2. WHEN 用户点刷新取数 THEN 系统 SHALL 用有效 Tier A 取数公式（预设 ∪ 用户覆盖）从 `tb_balance` 重新求值各类别期初/增加/减少，回填对应锚点。
3. WHERE 某锚点已有手工录入值或来自 F2-3~13 明细跨表带入（`isFromCrossSheet`） THE 刷新 SHALL 先弹确认（提示将以四表库值覆盖），用户确认后才覆盖；未确认不覆盖（避免静默覆盖手工/明细成果）。
4. WHEN 刷新完成 THEN 系统 SHALL 显示各类别取数来源与结果（期初/增加/减少/期末），使审计师可核对四表库取数 provenance（对齐 E1 source 面板）。
5. WHERE 刷新写入锚点 THE 值 SHALL 与 render 时 Tier B 预填、公式管理求值三者口径一致（同 `get_active_filter` + 同叶子判定）。
6. WHEN 灰度开关关闭 THEN 刷新入口 SHALL 不显示，F2 表现同当前（零回归）。

### Requirement 4: Tier B 预填口径修正（叶子判定 + 分别取发生额）

**User Story:** 作为平台维护者，我要求 F2-1 的四表库预填口径与 E1/D 循环一致、无双算、增减方向正确。

#### Acceptance Criteria

1. WHEN 后端 `_build_adjudication_prefill` 汇总某类别科目 THEN 系统 SHALL 改用 D 循环/E1 已验证的 `_is_leaf` 叶子判定（code 不是任何其它 code 前缀），替换现有 `_row_depth` + `by_depth[max(keys)]` 深度启发式，防中间级 rollup 与子科目双算。
2. WHEN 预填提供期初/本期增加/本期减少 THEN 系统 SHALL 分别取 `tb_balance` 的 `opening_balance` / `debit_amount` / `credit_amount`（原值类；跌价备抵类增加=`credit_amount`、减少=`debit_amount`），不再用 `closing−opening` 粗猜 increase/decrease。
3. WHEN 查询四表库 THEN 系统 SHALL 用 `get_active_filter`（数据集版本），跳过全零/无名称子科目，跌价准备取绝对值。
4. WHERE 某锚点在 `checklist_responses` 已有非空用户值或明细跨表带入 THE render 预填 SHALL 不覆盖它（手工/明细优先），刷新覆盖走 Req3.3 确认。
5. IF `tb_balance` 无该科目子科目 THEN 系统 SHALL 返回空、不报错、不阻断 render。

### Requirement 5: 统一评估器口径与支持列（消除双真源漂移）

**User Story:** 作为平台维护者，我要求公式管理保存/求值、render 预填、刷新取数三处的四表库读取口径一致。

#### Acceptance Criteria

1. WHEN Tier A 取数公式经公式管理保存/即时求值或刷新求值 THEN 求值 SHALL 与 Tier B 预填共用同一数据源口径：读 `tb_balance` 用 `get_active_filter`（数据集版本），不用裸 `is_deleted`。
2. WHERE Tier A 允许的列名 THE 系统 SHALL 明确并强制至少支持 `期初余额`/`期末余额`/`借方发生额`/`贷方发生额`；Wave 0 SHALL 核实评估器（`evaluate_wp_formula_expression` / `_resolve_tb` 的列名映射）是否支持发生额列，IF 不支持 THEN 系统 SHALL 补入其列名映射，ELSE 不静默返 0。
3. WHERE 表达式含评估器不支持的函数（`AUX`/`PREV`/序时账等） THE 系统 SHALL 在保存时拒绝（返 422），不静默落空。
4. WHEN 同一四表库快照下多次求值同一 Tier A 公式 THEN 结果 SHALL 一致（幂等）；求值失败/引用不存在 SHALL 返 None、不产错值、不阻断。

### Requirement 6: 零回归、灰度可回退、复用而非另造

**User Story:** 作为平台维护者，我要求不破坏 F2 现有链路，可灰度回退。

#### Acceptance Criteria

1. WHERE 引入 Tier A 取数公式预设、刷新入口、口径修正 THE 系统 SHALL 受灰度开关（`F2_FOUR_TABLE_EXTRACTION_ENABLED`，默认 False）控制，关闭时 render 逐字节等价当前、无刷新入口。
2. WHEN 接入 THEN 系统 SHALL 只新增取数公式列出/刷新/口径修正，不删除或改写既有 `tb_values`/`adjudication_prefill` seed（空表时）、F2-3~13 明细跨表带入、F2-14 调整分录、审定 TB 核对、附注联动、导入导出。
3. WHERE Tier A/B 四表库读取 THE 系统 SHALL 复用既有 `d_cycle_extraction` 范式（`build_d_adjudication_prefill` 的 `_is_leaf` / `get_active_filter`）与既有 `wp_formula` CRUD 端点，不新造第 2 套四表库读取或公式存储。
4. WHERE 预填/刷新写入锚点 THE 系统 SHALL 只在锚点属 `useF2Adjudication` 真实键集合时写入（校验未知锚点拒绝，防静默写空）。

### Requirement 7: 正确性属性可测

**User Story:** 作为质控，我希望关键正确性属性有属性测试守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖：R4.1 只取叶子防双算、R4.2 增减分别取借/贷发生额、R4.4/R3.3 手工/明细优先不静默覆盖、R4.5 无数据→空不报错、R1.1 预设读时收敛、R5.1 active_filter 同口径、R5.2 支持列名、R5.3 不支持函数保存拒绝、R5.4 幂等、R2.3 恢复默认回落、R6.1 灰度零回归、R6.4 未知锚点拒绝 等属性。
2. WHERE 刷新/求值 THE 属性测试 SHALL 断言来源可溯（每个取数值可回指其 `TB()` 公式来源）与三处口径一致（render 预填 / 公式管理求值 / 刷新求值同快照同值）。

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张源数据表 |
| F2-1 审定表 | 存货审定表，13 个固定类别（原值 1401-1412 + 跌价 1471），原值/跌价/净值三块 |
| Tier A 取数公式 | 可表达为单条 `TB(科目,列)` 的类别级四表库提取，注册为可编辑 `wp_formula`，锚点=checklist_responses item_id |
| Tier B 预填 | render 时按 `_build_adjudication_prefill` 范式从 `tb_balance` 叶子级批量 seed（空表时），与 Tier A 同口径 |
| 锚点 (anchor) | F2-1 字段的 `checklist_responses` item_id：`F2-1-{block}-{rowKey}-{field}`，block∈{gross,impairment}，field∈{opening,increase,decrease} |
| `_build_adjudication_prefill` | F2 既有四表库→审定表预填（本 spec 修口径+加显式公式驱动+刷新） |
| `_is_leaf` | 叶子判定（code 不是任何其它 code 前缀），防中间级 rollup 双算（复用 `d_cycle_extraction/prefill.py`） |
| get_active_filter | 四表查询统一入口（数据集版本 staged/active/superseded，禁裸 is_deleted） |
| 手工/明细优先 | 锚点已有非空用户值或来自 F2-3~13 明细跨表带入时不被自动预填覆盖；刷新覆盖需确认 |
| 刷新取数 | F2-1 工具栏「🔄从四表库刷新取数」，用有效取数公式重新求值回填（对齐 E1 🔄重新取数） |
| 预设库 | F2 Tier A 默认取数公式（`f2_extraction_presets.json` 或平台既有结构），读时与用户 wp_formula 收敛 |
| 灰度开关 | `F2_FOUR_TABLE_EXTRACTION_ENABLED`，默认关，关闭时 render 零回归、无刷新入口 |
| 账户映射 | 已核实一致：前端 `f2AccountModel.ts::F2_ROW_KEY_ACCOUNT` ∥ 后端 `_f2_inventory_main.F2_CATEGORIES` |
