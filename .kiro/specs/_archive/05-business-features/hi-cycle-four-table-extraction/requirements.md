# Requirements Document

## Introduction

本 spec 解决「H 循环（H5-H10）与 I 循环（I1-I6）实质性程序底稿从四表库（`trial_balance` 试算表 / `tb_balance` 余额表 / `tb_ledger` 序时账 / `tb_aux_balance` 辅助余额表）刷新取数」这一主线，把这些底稿审定表的四表库取数从**分散的一次性 loadTbData**升级为**显式取数公式驱动、可刷新、公式管理可查可编**，对齐 E1 货币资金（`E1FourTableSourcePanel` + `TB()` 公式 + 🔄重新取数）、H1 固定资产（`_build_category_prefill` + `h1_four_table_prefill` + `H1FourTableSourcePanel`，灰度 `H1_FOUR_TABLE_EXTRACTION_ENABLED`）、D 循环（`d_cycle_extraction` 模块：`build_d_adjudication_prefill` 叶子级 prefill + `d_cycle_extraction_presets.json` Tier A 可编辑公式 + 锚点注册 + `tier_a_seed`）已证范式。

### 实测现状与缺口（非猜测，逐文件核实）

已核实 H/I 全部渲染策略 `account_codes` 与前端 FormData composable 取数/回写：

**已完成（有四表取数扩展，灰度）**：
- H1（1601/1602/1603，`H1_FOUR_TABLE_EXTRACTION_ENABLED`）— 全套（category prefill + four-table prefill + 源面板 + 试算核对走规则映射）。
- H2（1604，`H2_FOUR_TABLE_EXTRACTION_ENABLED`）— `_build_h2_detail_prefill`。
- H4（report 映射，`H4_FOUR_TABLE_EXTRACTION_ENABLED`）— 四表取数。

**部分（有 prefill 但未纳入统一范式）**：
- H8（1901 + 190101 累计折旧）— 已有 `_build_h8_detail_prefill`（从 1901 叶子子科目种子 H8-2 明细），但**未受灰度门控、无 Tier A 预设取数公式、无刷新源面板**，需纳入统一范式（灰度 + 预设 + 面板）。

**缺口（仅有 `loadTbData`/`writeback`，无预设取数公式、无 render prefill、无刷新源面板）**：

| 底稿 | 科目 | 方向/类型 | 审定表结构 | Tier A 可行性 |
|------|------|-----------|-----------|--------------|
| H5 油气资产 | 1631 原值 / 1632 累计折耗 | 资产（balance） | 原值/累计折耗（备抵）/净值 | 原值段+折耗段各单科目 → 可 |
| H6 固定资产清理 | 1606 | 资产过渡（balance，期末应为 0） | 单科目 | 可（期末=0 核对） |
| H7 生产性生物资产 | 1621 | 资产（balance） | 原值/累计折旧/净值 | 可 |
| H8 使用权资产 | 1901 原值 / 190101 累计折旧 | 资产（balance） | 原值/累计折旧/净值 | 可（含已有 prefill） |
| H9 租赁负债 | 2205 / 未确认融资费用（子科目） | 负债（balance） | 租赁负债/减未确认融资费用/净值 | 可 |
| H10 资产处置损益 | 6115 | 损益（occurrence） | 处置利得/损失 | 可（发生额） |
| I1 无形资产 | 1701 原值 / 1702 累计摊销 / 1703 减值 | 资产（balance） | 原值/累计摊销/减值/净值 | 可 |
| I2 开发支出 | 1717 | 资产（balance） | 单科目 | 可 |
| I3 商誉 | 1711 | 资产（balance，不摊销仅减值） | 单科目 | 可 |
| I4 长期待摊费用 | 1801 | 资产（balance） | 单科目 | 可 |
| I5 其他非流动资产 | 1911 | 资产（balance） | 单科目 | 可 |
| I6 研发费用 | 6602 | 损益（occurrence） | 费用化/资本化转出等 | 可（发生额） |

三个共性缺口（与 F2 spec 同款，逐底稿核实）：

1. **无显式取数公式预设**：各 FormData composable 用 `GET /trial-balance?account_prefix=` 黑盒取科目总额，`TB('1711','期末余额')` 这类公式没有任何地方被显式预设，审计师在公式管理中心看不到「商誉期末 ← TB('1711','期末余额')」。`wp_surfaced_h.py`/`wp_surfaced_i.py` 现有 surfacing 是跨表/计算公式，**无 tb_balance 的 `TB()` 四表库取数公式**。
2. **审定表分段/明细无 render prefill**：不像 H1 有 `_build_category_prefill` 从 tb_balance 叶子按分段（原值/累计折旧/减值）批量种子，H5-H10/I1-I6 审定表未审数要么靠前端 loadTbData 拿科目总额、要么手工，明细行零取数。
3. **无刷新取数入口 + 无口径统一**：余额表重导入/想重新对齐四表库时无 🔄刷新取数 入口（E1/H1 有源面板）；且各 loadTbData 口径分散（未统一叶子判定、未统一 `get_active_filter`、未统一借/贷发生额方向）。

### H/I 与 D 循环的关键差异（决定本 spec 更适合 Tier A）

D 循环审定表按信用风险组合/账龄/客户分类，**无法用单条 TB 公式表达**（宁缺勿造，只做 Tier B）；而 **H/I 审定表是固定分段结构**（资产类=原值/累计折旧或摊销/减值三段，每段恰好对应一个标准科目；单科目类=1 段；损益类=按发生额），故每段的期初/本期增加/本期减少/期末**都能干净地表达为 `TB(科目, 列)`**，是理想的 **Tier A 可编辑取数公式**载体（同 H1 已证）。这是 H/I 相较 D 循环的核心差异，也是本 spec 可行的前提。

### 诚实的取数边界（宁缺勿造，已实证）

- 四表库中只有 `tb_balance`（科目级）适合 H/I 审定表的分段级取数；`trial_balance` 供 TB 核对标量（审定数）。
- **明细表项目/资产卡片级不做四表库自动取数**：`tb_aux_balance` 无资产卡片维度（H1 已实证），`tb_balance` 只有科目总额、无单项资产明细 → 明细表逐项行不做取数（除非某底稿 Wave 0 核实 aux 确有可用维度，有则作可选补充，宁缺勿造）。
- **折旧/摊销费用归属不自动归集**：`tb_ledger` 对方科目填充率低且多为合并记账（H1 实证约 9%）→ 累计折旧/摊销的期末余额可从 tb_balance 备抵科目取，但其「费用归属到哪个成本/费用科目」不自动归集。
- **H3 投资性房地产不在本 spec**：H3 有成本模式/公允价值模式双计量，公允价值模式非简单 TB 取数，且已有 `h3-cross-workpaper-reconciliation` spec；若纳入需单独评估（仅成本模式适合 Tier A），本 spec 范围排除以免臆造公允价值取数。
- **H9 科目号以渲染策略实测为准**：`_h9_lease_liabilities.py` 现用 `2205`（含未确认融资费用子科目 220501）；本 spec 一律**沿用各渲染策略/FormData composable 已有的科目常量**（`ACCOUNT_CODE_*`），不改科目号、不臆造。

## Requirements

### Requirement 1: H/I 审定表 Tier A 取数公式预设

**User Story:** 作为审计助理，我希望 H5-H10/I1-I6 审定表每个分段（原值/累计折旧或摊销/减值/净值以外的可取数段）的期初/增加/减少/期末未审数由显式的 `TB(科目, 列)` 取数公式驱动，而不是分散的黑盒 loadTbData。

#### Acceptance Criteria

1. WHEN 系统需要某 H/I 底稿的 Tier A 默认取数公式 THEN 系统 SHALL 从预设库（沿用 `d_cycle_extraction` 的预设结构或平台既有预设库，按 wp_code → 锚点/表达式/说明）读取，读时与用户已存 `wp_formula` 收敛（同锚点用户覆盖预设，预设不落库）。
2. WHERE 底稿为资产原值段（如 H5 1631 / H7 1621 / H8 1901 / I1 1701 / I2 1717 / I3 1711 / I4 1801 / I5 1911 / H6 1606） THE 预设 SHALL 为对应锚点提供：期初 = `TB(科目,'期初余额')`、本期增加 = `TB(科目,'借方发生额')`、本期减少 = `TB(科目,'贷方发生额')`、期末 = `TB(科目,'期末余额')`（资产借方口径）。
3. WHERE 底稿为累计折旧/折耗/摊销/减值备抵段（如 H5 1632 / H8 190101 / I1 1702·1703 / H9 未确认融资费用） THE 预设 SHALL 取绝对值口径：期末 = `ABS(TB(科目,'期末余额'))`、本期增加（计提）= `TB(科目,'贷方发生额')`、本期减少（转回/核销/结转）= `TB(科目,'借方发生额')`（备抵口径，方向与原值相反）。
4. WHERE 底稿为损益类（H10 6115 资产处置损益 / I6 6602 研发费用） THE 预设 SHALL 按发生额（occurrence）取数：`TB(科目,'审定数')` 或借/贷发生额（损益类 `trial_balance.audited_amount` 存审定发生额），不取余额。
5. WHERE 提取为资产卡片/存货规格/单项明细级（各底稿明细表逐项行） THE 系统 SHALL NOT 为其注册可编辑取数公式（`tb_balance` 无项目级数据，宁缺勿造）。
6. IF 某锚点无法从四表库映射（审计判断/文本/账项调整/净值 computed） THEN 预设库 SHALL 不为其生成取数公式。
7. WHEN 交付 THEN 预设库每条 `target_cell` SHALL 属于从各底稿审定表 composable（`useH5Adjudication` … `useI6Adjudication` / 对应 FormData）反查的真实 `checklist_responses` item_id 锚点集（不臆造），并经锚点注册校验（未知锚点拒绝）。

### Requirement 2: 公式管理中心可查看可编辑 H/I 取数公式

**User Story:** 作为审计助理/复核人，我希望在各 H/I 底稿页面公式管理里，按 sheet 看到审定表各分段的 `TB()` 取数公式，并能编辑/恢复默认。

#### Acceptance Criteria

1. WHEN 打开某 H/I 底稿的公式管理面板 THEN 系统 SHALL 列出该底稿审定表的 Tier A 有效取数公式（预设 ∪ 用户），展示锚点/表达式/来源（预设/自定义）/当前值，按 sheet 分组。
2. WHEN 用户编辑某 Tier A 取数公式并保存 THEN 系统 SHALL 经既有 `PUT /api/workpapers/{wp_id}/formulas` 落库（覆盖预设），保存前经悬空引用/不受支持函数校验（非法返 422 不写库）。
3. WHEN 用户对已覆盖预设的公式点「恢复默认」 THEN 系统 SHALL 删除用户 `wp_formula` 使其回落预设。
4. WHERE H/I 取数公式作为只读溯源同时展示 THE 系统 SHALL 复用 `wp_surfaced_h.py`/`wp_surfaced_i.py` 的 surfacing，把各底稿现有跨表/计算条目**补充**显式 `TB(科目,列)` 四表库取数条目（不删除既有跨表/计算条目），使公式管理中心真实反映四表库取数来源。
5. WHERE 公式管理面板 GET 列表 THE 系统 SHALL 按选中 sheet 过滤（复用 E1/D 已证 sheet_codes 过滤），不逐条 GET 时重求值（避免慢/N+1）。
6. IF 用户无底稿编辑权限 THEN 编辑/保存/删除入口 SHALL 禁用或拒绝（沿用既有权限），只读用户仍可查看。

### Requirement 3: 🔄从四表库刷新取数入口（本 spec 核心）

**User Story:** 作为审计助理，余额表重导入或想重新对齐四表库时，我希望能在各 H/I 底稿一键从四表库刷新审定表未审数，而不是只能靠一次性 loadTbData。

#### Acceptance Criteria

1. WHEN H/I 底稿审定表工具栏 THEN 系统 SHALL 提供「🔄从四表库刷新取数」入口（对齐 E1 `E1FourTableSourcePanel` / H1 `H1FourTableSourcePanel` 的 🔄重新取数），可用性受编辑权限门控。
2. WHEN 用户点刷新取数 THEN 系统 SHALL 用有效 Tier A 取数公式（预设 ∪ 用户覆盖）从 `tb_balance`/`trial_balance` 重新求值各分段期初/增加/减少/期末，回填对应锚点。
3. WHERE 某锚点已有手工录入值或来自明细跨表带入 THE 刷新 SHALL 先弹确认（提示将以四表库值覆盖），用户确认后才覆盖；未确认不覆盖（避免静默覆盖手工/明细成果）。
4. WHEN 刷新完成 THEN 系统 SHALL 显示各分段取数来源与结果（科目/期初/增加/减少/期末），使审计师可核对四表库取数 provenance（对齐 E1/H1 源面板）。
5. WHERE 刷新写入锚点 THE 值 SHALL 与 render 时 Tier B 预填、公式管理求值三者口径一致（同 `get_active_filter` + 同叶子判定 + 同借/贷方向）。
6. WHEN 灰度开关关闭 THEN 刷新入口 SHALL 不显示，各 H/I 底稿表现同当前（零回归）。

### Requirement 4: Tier B render 预填口径统一（叶子判定 + 分别取发生额 + 分段）

**User Story:** 作为平台维护者，我要求 H/I 审定表的四表库预填口径与 E1/H1/D 循环一致、无双算、增减方向正确。

#### Acceptance Criteria

1. WHEN 后端为某 H/I 底稿构建审定表分段预填 THEN 系统 SHALL 复用 `d_cycle_extraction/prefill.py::build_d_adjudication_prefill`（或等价的 `_is_leaf` 叶子判定），按科目前缀取叶子子科目余额/发生额，防中间级 rollup 与子科目双算。
2. WHEN 预填提供期初/本期增加/本期减少 THEN 系统 SHALL 分别取 `tb_balance` 的 `opening_balance` / `debit_amount` / `credit_amount`（原值类；备抵/负债备抵类增加=`credit_amount`、减少=`debit_amount`），不用 `closing−opening` 粗猜。
3. WHEN 查询四表库 THEN 系统 SHALL 用 `get_active_filter`（数据集版本），跳过全零/无名称子科目，备抵科目取绝对值。
4. WHERE 某锚点在 `checklist_responses` 已有非空用户值或明细跨表带入 THE render 预填 SHALL 不覆盖它（手工/明细优先），刷新覆盖走 Req3.3 确认。
5. IF `tb_balance` 无该科目子科目 THEN 系统 SHALL 返回空、不报错、不阻断 render。
6. WHERE H8 已有 `_build_h8_detail_prefill` THE 系统 SHALL 将其纳入统一灰度门控与口径（`_is_leaf`/`get_active_filter`），不新造第 2 套 H8 预填。

### Requirement 5: 统一评估器口径与支持列（消除双真源漂移）

**User Story:** 作为平台维护者，我要求公式管理保存/求值、render 预填、刷新取数三处的四表库读取口径一致。

#### Acceptance Criteria

1. WHEN Tier A 取数公式经公式管理保存/即时求值或刷新求值 THEN 求值 SHALL 与 Tier B 预填共用同一数据源口径：读 `tb_balance`/`trial_balance` 用 `get_active_filter`（数据集版本），不用裸 `is_deleted`。
2. WHERE Tier A 允许的列名 THE 系统 SHALL 明确并强制至少支持 `期初余额`/`期末余额`/`借方发生额`/`贷方发生额`/`审定数`；Wave 0 SHALL 核实评估器（`evaluate_wp_formula_expression` / `_resolve_tb` 列名映射）是否支持发生额列与 `ABS()`，IF 不支持 THEN 系统 SHALL 补入映射，ELSE 不静默返 0。
3. WHERE 表达式含评估器不支持的函数（`AUX`/`PREV`/序时账等） THE 系统 SHALL 在保存时拒绝（返 422），不静默落空。
4. WHEN 同一四表库快照下多次求值同一 Tier A 公式 THEN 结果 SHALL 一致（幂等）；求值失败/引用不存在 SHALL 返 None、不产错值、不阻断。

### Requirement 6: 零回归、灰度可回退、复用而非另造

**User Story:** 作为平台维护者，我要求不破坏 H/I 现有链路，可灰度回退，且不改科目号。

#### Acceptance Criteria

1. WHERE 为某 H/I 循环引入 Tier A 取数公式预设、刷新入口、口径统一 THE 系统 SHALL 受灰度开关控制（每循环一个开关或统一 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`，默认 False），关闭时 render 逐字节等价当前、无刷新入口、无预设 surfacing。
2. WHEN 接入 THEN 系统 SHALL 只新增取数公式列出/刷新/口径统一，不删除或改写既有 `tb_values`/loadTbData/writeback、明细跨表带入、调整分录、审定 TB 核对、附注联动、导入导出。
3. WHERE Tier A/B 四表库读取 THE 系统 SHALL 复用既有 `d_cycle_extraction` 范式（`build_d_adjudication_prefill`/`_is_leaf`/`get_active_filter`/`presets.resolve_effective`/`anchor_registry`）与既有 `wp_formula` CRUD 端点，不新造第 2 套四表库读取或公式存储。
4. WHERE 预填/刷新写入锚点 THE 系统 SHALL 只在锚点属对应底稿真实键集合时写入（校验未知锚点拒绝，防静默写空）。
5. WHERE 各 H/I 底稿科目号 THE 系统 SHALL 一律沿用渲染策略/FormData composable 已有科目常量（`ACCOUNT_CODE_*`/`account_codes`），不改、不臆造（尤其 H9 沿用现用科目号）。
6. WHERE 增量交付 THE 系统 SHALL 可按底稿逐个接入、单底稿可回退（一个底稿的接入失败不影响其它）。

### Requirement 7: 正确性属性可测

**User Story:** 作为质控，我希望关键正确性属性有属性测试守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖：R4.1 只取叶子防双算、R4.2 增减分别取借/贷发生额（含备抵/负债备抵方向相反）、R4.4/R3.3 手工/明细优先不静默覆盖、R4.5 无数据→空不报错、R1.1 预设读时收敛、R5.1 active_filter 同口径、R5.2 支持列名、R5.3 不支持函数保存拒绝、R5.4 幂等、R2.3 恢复默认回落、R6.1 灰度零回归、R6.4 未知锚点拒绝、R1.3 备抵绝对值口径、R1.4 损益取发生额 等属性。
2. WHERE 刷新/求值 THE 属性测试 SHALL 断言来源可溯（每个取数值可回指其 `TB()` 公式来源）与三处口径一致（render 预填 / 公式管理求值 / 刷新求值同快照同值）。

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张源数据表 |
| H/I 审定表 | H5-H10 / I1-I6 各底稿的审定表（X-1），固定分段结构（资产类原值/累计折旧或摊销/减值/净值；单科目类；损益类按发生额） |
| Tier A 取数公式 | 可表达为单条 `TB(科目,列)` 的分段级四表库提取，注册为可编辑 `wp_formula`，锚点=checklist_responses item_id |
| Tier B 预填 | render 时按 `build_d_adjudication_prefill` 从 `tb_balance` 叶子级批量 seed（空表时），与 Tier A 同口径 |
| 锚点 (anchor) | 审定表字段的 `checklist_responses` item_id，各底稿从其 composable 反查（design 阶段逐底稿登记，禁臆造） |
| `_is_leaf` | 叶子判定（code 不是任何其它 code 前缀），防中间级 rollup 双算（复用 `d_cycle_extraction/prefill.py`） |
| get_active_filter | 四表查询统一入口（数据集版本 staged/active/superseded，禁裸 is_deleted） |
| 备抵科目 | 累计折旧/折耗/摊销/减值/未确认融资费用等，方向与原值相反（增加取贷方、减少取借方），取绝对值口径 |
| 损益类 occurrence | H10 6115 / I6 6602，取审定发生额（`trial_balance.audited_amount`），不取余额 |
| 手工/明细优先 | 锚点已有非空用户值或来自明细跨表带入时不被自动预填覆盖；刷新覆盖需确认 |
| 刷新取数 | 各 H/I 审定表工具栏「🔄从四表库刷新取数」，用有效取数公式重新求值回填（对齐 E1/H1 源面板） |
| 预设库 | H/I Tier A 默认取数公式（沿用 `d_cycle_extraction` 预设结构或平台既有），读时与用户 wp_formula 收敛 |
| 灰度开关 | 每循环/统一开关，默认关，关闭时 render 零回归、无刷新入口 |
| 范围排除 | H1/H2/H4（已完成，仅 H8 需纳入范式）、H3 投资性房地产（双计量，公允价值非简单取数，另评估） |
