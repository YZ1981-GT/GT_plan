# Requirements Document

## Introduction

`semantic_account_resolver`（语义驱动逐项目科目定位）已在 9 个 render 策略落地验证，本 spec 将剩余 **70 个**四表取数类 render 策略（10 G + 19 D/F + 11 H/I + 11 K + 10 L + 4 M + 5 N）分 6 批迁移到语义解析件，并落地 7 个平台级优化建议。

### 背景

- 已迁移（9）：G4-ecl、G4-sppi、G6-ecl、G6-main、G8、G9、G14、E1、H3
- 仍在 `report_line_accounts`（40）：D2/F1~F5/G1~G5/G7/G10~G13/H1/J1~J2/K1~K13/M4~M9/N1~N5
- 在「neither」桶（有 `_fetch_tb` 但用各自硬编码前缀，31）：D1/D3~D7/H2/H5~H10/I1~I6/L1~L8/M1~M3/M6/M8/M10/N2

共 71 个策略（含 `_g6_other_bond_investment_main_service.py` 子策略）需迁移。

### 迁移收益

1. **消除科目硬编码** — 当前 40 个 `report_line_accounts` 消费者里 `report_config` 有 4 行错码会让定位静默取错；31 个 neither 桶里的硬编码前缀在 `1504~1507`/`1519`/旧准则项目**必然取空或取错**
2. **统一溯源面板** — 迁移后 `tb_source_codes` 输出含 `slots`/`conflicts`/`unmapped_candidates`/`chart_available` 四个审计追溯信号
3. **统一叶子聚合** — 消除 `_is_leaf`/`_row_depth`/`_aggregate_prefix_deepest` 等各自发明的「取最深层级」bug（实证丢 21.7% 叶子）
4. **落地 7 个优化** — 含新增 `_cycle_specs.py` / `pl_occurrence` 损益类共享件 / `is_liability` 按变体声明 / 统一 `adjudication_prefill` 输出 / per-cycle AccountSpec 守卫 / 前端溯源面板接线 / CI 回归覆盖

## Requirements

### 1. 批次结构

1.1. 分 6 批，各批内策略循环间无依赖，可并行（同批内同文件则串行）
1.2. 每批完成后运行**该批 + 前序批**的回归测试，确认零回归后方可推进下一批
1.3. G 循环（批 1）是最快批：`g_cycle_specs.py` 14 个规格已全部声明，只需 render 侧改引用

### 2. 迁移模式（每个策略的变更模式）

2.1. 删除策略内的硬编码前缀常量（`_XX_ACCOUNT_PREFIX`/`_XX_ACCOUNT_PREFIXES`/`_XX_ACCOUNT_CODE`）
2.2. 引入 `from app.services.four_table.{cycle}_specs import XX_SPEC`（或新建 `{cycle}_specs.py`）
2.3. `_fetch_tb_data` 内改调 `resolve_semantic_accounts(ctx, XX_SPEC)` 取 `codes_of("gross")`
2.4. 删除自造叶子判定（`_is_leaf`/`_row_depth`/`startswith` 无点号边界），改用 `select_leaves` + `filter_by_prefixes`
2.5. 输出 `tb_source_codes = accounts.as_dict()` 置于 `project_context`
2.6. 输出 `adjudication_prefill`（逐叶子明细，格式 `[{code, name, opening, closing}]`）
2.7. 负债/权益循环须声明 `is_liability=True`（跳过备抵拆分）
2.8. 损益循环须用 `pl_occurrence` 取发生额（禁 `debit - credit`）

### 3. 新建 per-cycle `_specs.py`

3.1. D 循环：`d_cycle_specs.py`（D1~D7，7 个 `SemanticAccountSpec`）
3.2. H 循环：`h_cycle_specs.py`（H1~H10，10 个 `SemanticAccountSpec`，含 H3 多槽）
3.3. I 循环：`i_cycle_specs.py`（I1~I6，6 个）
3.4. K 循环：`k_cycle_specs.py`（K1~K13，13 个）— 资产类 K1/K2 已有独立 spec 文件
3.5. L 循环：`l_cycle_specs.py`（L1~L8，8 个，均为负债类须声明 `is_liability=True`）
3.6. M 循环：`m_cycle_specs.py`（M1~M10，10 个，均为权益类须声明 `is_liability=True`）
3.7. N 循环：`n_cycle_specs.py`（N1~N5，5 个）
3.8. F 循环：`f_cycle_specs.py`（F1~F5，5 个）
3.9. 每个文件都含 `CYCLE_SPECS: dict[str, SemanticAccountSpec]`、`spec_of(wp_code)` 查询函数、`CYCLE_PL_CYCLES`（如有）

### 4. 七个优化建议落地

4.1. **统一 `adjudication_prefill` 输出格式** — 所有循环的 `adjudication_prefill` 统一为 `list[dict]` 格式 `[{code, name, opening, closing, debit?, credit?}]`，禁用桶预聚合
4.2. **`pl_occurrence` 共享件** — 损益类取发生额统一走 `four_table/pl_occurrence.py`（K8~K13 已建，G11~G14/N4/N5/I6/H10/L8 接入）
4.3. **`is_liability` 按循环声明** — J/K3~K7/L/M 类在 `_specs.py` 里 `is_liability=True`
4.4. **per-cycle AccountSpec 守卫** — 新建 `test_{cycle}_account_specs.py`，断言每个 spec 的 `row_code` 存在于 `report_config`（row_code=None 除外）+ 兜底码存在于 `account_chart` JSON + 跨循环互斥（同一兜底码不得出现在两个循环）
4.5. **前端溯源面板接线** — 所有循环的 `XFourTableSourcePanel.vue`/`WpFourTableSourcePanel.vue` 统一消费 `tb_source_codes.slots`，渲染四个追溯信号
4.6. **CI 回归覆盖** — 每批新增 CI job `semantic-resolver-batch-{n}`（跑该批所有 `test_*_account_specs.py` + render characterization）
4.7. **`report_line_accounts` 降级守卫** — 迁移完成后新增守卫：render 策略目录内禁止新增 `from app.services.four_table.report_line_accounts import`（存量不变）

### 5. 回归安全

5.1. 每个策略迁移须保证 `tb_source_codes.as_dict()` 的扁平投影（`gross`/`provision`/`resolved_from`）与迁移前**语义等价**（允许来源从 `report_config` 变为 `account_chart_*`）
5.2. 已有 `adjudication_prefill` 消费方的循环，须保证格式契约不变或向后兼容（新增字段可以，删字段不行）
5.3. 迁移不得改变 render 的其他输出（sheet 列表、组件类型、formulaPreset 等）
5.4. **`report_line_accounts` 模块本身不删不改**（它是过渡期兼容层 + 新增循环在确认 `g_cycle_specs` 范式成熟前的 fallback）

### 6. 批次分配

6.1. **批 1：G 循环剩余**（10 策略，最快）— G1/G2/G3/G4-main/G5/G7/G10/G11/G12/G13
6.2. **批 2：D/F 循环**（11 策略）— D1/D2/D3/D4/D5/D6/D7/F1/F2/F3/F4/F5
6.3. **批 3：H/I 循环**（16 策略）— H1/H2/H5/H6/H7/H8/H9/H10/I1/I2/I3/I4/I5/I6
6.4. **批 4：K 循环**（13 策略）— K1~K13
6.5. **批 5：L/M 循环**（18 策略）— L1~L8/M1~M10
6.6. **批 6：N/J 循环 + 收口**（7 策略）— N1~N5/J1/J2 + 降级守卫 + CI 总控

### 7. D 循环特殊处理

7.1. D1~D7 已有独立的 `d_cycle_extraction/` 子模块（D1 账龄/D4 营收等），迁移只在最外层 render `_fetch_tb_data` 改引用
7.2. D1 的 `d1_account_resolver.py` 是 `report_line_accounts` 的薄壳，改引 `d_cycle_specs.D1_SPEC` + `resolve_semantic_accounts`

### 8. 损益类特殊处理

8.1. G11~G14 / K8~K13 / N4/N5 / I6 / H10 / L8 均为损益类
8.2. `tb_balance.closing_balance` 在含年末结转损益的全年账上结构性恒为 0 → 禁 `closing`
8.3. `debit - credit` 因结转分录恒为 0 → 必须声明正方向（`G_PL_POSITIVE_SIDE` 范式）单侧取
8.4. 统一走 `four_table/pl_occurrence.py` 的 `fetch_pl_occurrence` + `PL_POSITIVE_SIDE`

### 9. 非功能性

9.1. 每个 `_specs.py` 文件须含完整的 docstring（科目映射真源实证 + 特殊处理说明）
9.2. 每个 spec 的 `names` 必须与 `account_chart`（`source='standard'`）实测的一级科目名逐字一致
9.3. `exclude_names` / `legacy_standard_names` 不得为空元组（显式声明 = 设计意图，空 = 审查遗漏）
