# Requirements Document

## Introduction

本 spec 为 L/M/N 三循环（共 18 个科目底稿）的审定表从四表库（tb_balance/trial_balance/tb_ledger）刷新取数建立完整的取数公式预设体系，使公式管理中心能展示、编辑、刷新这些底稿的取数逻辑。

### 现状实证（代码核实）

**L 循环（L1-L8）**：后端 render 策略**零 TB 取数**（全部 8 个 `_l*` 策略只返回 responses_snapshot+project_context，从不查 tb_balance/trial_balance）。前端审定表行的未审数完全靠「从明细带入」或手工。是三循环中最大的取数缺口。

**M 循环（M1-M10）**：M3-M10 后端已有 `_fetch_tb_data`（返回科目级 opening/debit/credit/closing），但只写进 `html_data.trial_balance` 供底部 TB 核对条/校验用——**从不预填审定表行的未审数**（审定表行是按分类/项目的动态行，无法按科目自动拆分）。M1/M2 后端零 TB 取数。

**N 循环（N1-N5）**：全部后端已有 TB 取数。N5 有真正的 `_build_adjudication_prefill`（叶子级子科目按名称分类为当期/递延预填行），N1-N4 只取科目总额供核对。N5 是平台最完善的四表取数范式。

**公式管理中心（wp_surfaced_l/m/n.py）**：L/M/N 全部已有 surfacing 条目（只读展示用），但不是可编辑的 Tier A 取数公式预设，也不被 `formula_presets_seed.json` 覆盖。

### 科目清单与方向

| 底稿 | 科目 | 名称 | 方向 | 审定表取数口径 |
|------|------|------|------|----------------|
| L1 | 2001 | 短期借款 | 负债/贷方 | 期初余额+期末余额 |
| L2 | 2231 | 应付利息 | 负债/贷方 | 期初余额+期末余额 |
| L3 | 2501 | 长期借款 | 负债/贷方 | 期初余额+期末余额 |
| L4 | 2502 | 应付债券 | 负债/贷方 | 期初余额+期末余额 |
| L5 | 2701 | 长期应付款 | 负债/贷方 | 期初余额+期末余额 |
| L6 | 2601 | 专项应付款 | 负债/贷方 | 期初余额+期末余额 |
| L7 | 2801 | 其他非流动负债 | 负债/贷方 | 期初余额+期末余额 |
| L8 | 6603 | 财务费用 | 损益/借方 | 借方发生额−贷方发生额 |
| M1 | 2232 | 应付股利 | 负债/贷方 | 期初余额+期末余额 |
| M2 | 4001 | 实收资本 | 权益/贷方 | 期初余额+期末余额 |
| M3 | 4002 | 库存股 | 权益备抵/借方 | 借方发生额−贷方发生额 |
| M4 | 4002 | 资本公积 | 权益/贷方 | 期初余额+期末余额 |
| M5 | 4101 | 盈余公积 | 权益/贷方 | 期初余额+期末余额 |
| M6 | 4104 | 利润分配 | 权益/贷方 | 期初余额+期末余额 |
| M7 | 4201 | 专项储备 | 权益/贷方 | 期初余额+期末余额 |
| M8 | 4104 | 一般风险准备 | 权益/贷方 | 审定数(trial_balance) |
| M9 | 4103 | 其他综合收益 | 权益/贷方 | 期初余额+期末余额 |
| M10 | 4003 | 其他权益工具 | 权益/贷方 | 期初余额+期末余额 |
| N1 | 1811 | 递延所得税资产 | 资产/借方 | 期初余额+期末余额 |
| N2 | 2221 | 应交税费 | 负债/贷方 | 期初余额+期末余额 |
| N3 | 2901 | 递延所得税负债 | 负债/贷方 | 期初余额+期末余额 |
| N4 | 6403 | 税金及附加 | 损益/借方 | 借方发生额−贷方发生额 |
| N5 | 6801 | 所得税费用 | 损益/借方 | 借方发生额−贷方发生额(+子科目预填) |

### 撞码问题

- M3(库存股) 与 M4(资本公积) **共用 4002**：M3 取子科目特定子项(备抵)，M4 取全部。预设公式取全码 4002 只供 TB 核对合计，不自动拆分到分类行。
- M6(未分配利润) 与 M8(一般风险准备) **共用 4104**：M6 取 4104（或 4104.05 子科目），M8 取金融机构专属子科目。预设公式取全码 4104 供核对，不自动拆分。

### 宁缺勿造边界

- L/M 审定表分类行（如 L1 的信用/抵押/保证/质押、M 的投资项目名）**无法从四表库单条公式表达**（TB 只有科目总额无分类维度），预设公式只给**合计级 TB 核对**，不臆造分类行预填。
- N5 已有 Tier B 子科目预填（`_build_adjudication_prefill`），本 spec 为其补 Tier A 可编辑公式+刷新入口，不重造 Tier B。
- 四表库无法推导的字段（审计判断/分类/文本/账龄）不预填不标 auto_calc。

## Requirements

### Requirement 1: L 循环后端 TB 取数补齐

**User Story:** 作为审计师，我希望 L1-L8 审定表能自动从试算表获取科目余额数据，以便审定表底部展示「试算平衡表数」与审定合计的差异。

#### Acceptance Criteria

1.1. L1-L7（负债余额类）取 opening_balance + closing_balance（科目精确或前缀 LIKE，优先精确行回退叶子聚合防双算）。
1.2. L8（损益类 6603）取 debit_amount + credit_amount 发生额（净发生额=借−贷）。
1.3. 全部 8 个 `_l*` render 策略加 `_fetch_tb_data`，返回统一结构 `html_data.trial_balance = {account_code, begin_balance, end_balance, debit_amount, credit_amount}`。
1.4. 查询失败 fail-open（result 各字段置 0，log warning，不阻断 render）。

### Requirement 2: M 循环后端 TB 取数口径修正

**User Story:** 作为审计师，我希望 M1/M2 也能显示 TB 核对数据（M3-M10 已有），且 M8 使用与其它 M 循环一致的数据源口径。

#### Acceptance Criteria

2.1. M1（2232 应付股利）新增 `_fetch_tb_data`。
2.2. M2（4001 实收资本）新增 `_fetch_tb_data`。
2.3. M8 现用 `TrialBalance`（trial_balance 表，查 `is_deleted`），改为 `TbBalance` + `get_active_filter`（与 M3-M7/M9/M10 一致，消除 recalc 借贷方向 bug 风险）。
2.4. 失败 fail-open 不阻断。

### Requirement 3: Tier A 取数公式预设注册

**User Story:** 作为审计师，我希望在公式管理中心看到 L/M/N 审定表的取数公式并可编辑/恢复默认，以便追溯数据来源和按项目定制取数逻辑。

#### Acceptance Criteria

3.1. 新增 `formula_presets_seed.json` 条目，page_key 为 `workpaper:{code}-1`（如 `workpaper:L1-1`），分类 `auto_calc`。
3.2. 负债/权益/资产余额表类：期初=`TB('{code}','期初余额')`、期末=`TB('{code}','期末余额')`。
3.3. 损益类（L8/N4/N5）：本期发生额=`TB('{code}','借方发生额')-TB('{code}','贷方发生额')`。
3.4. M3 库存股（借方备抵）：`TB('4002','借方发生额')-TB('4002','贷方发生额')`（方向特殊）。
3.5. M8 一般风险准备：`SUM_TB('4104','审定数')`（取 trial_balance 审定额口径）。
3.6. 每条预设附 `refs:['{code}']`（溯源科目码），`category:'auto_calc'`，`description` 说明取数口径。
3.7. 复用既有 `preset_library.build_preset_library` 读时收敛（预设∪用户 wp_formula），用户覆盖预设优先，不落新 DB 表。

### Requirement 4: 前端 TB 核对行消费

**User Story:** 作为审计师，我希望 L 循环审定表底部展示「试算平衡表数」和「差异数」，以便一目了然核对审定合计与试算表是否一致。

#### Acceptance Criteria

4.1. L1-L8 各审定表组件加 `tbReconcile` computed（审定合计 vs `html_data.trial_balance.end_balance`，差异>1元告警）。
4.2. TB 核对行仅当 `trial_balance.end_balance !== 0` 时展示（`hasTb` 守卫，避免 TB 未导入时误报）。
4.3. M1/M2 同法补 TB 核对（M3-M10 已有）。

### Requirement 5: 公式管理面板 surface 补齐

**User Story:** 作为审计师，我希望在公式管理中心打开 L/M/N 审定表节点时能看到取数公式及其数据来源标注，以便了解每个数字的追溯逻辑。

#### Acceptance Criteria

5.1. `wp_surfaced_l/m/n.py` 已有只读 surfacing 条目（`取数`分类），补充对齐 Req3 注册的公式预设（公式文案精确对齐，如 `TB('2001','期末余额')`）。
5.2. FormulaStatusPanel 对底稿 sheet 节点展示 Tier A 条目时附 `semantic` 标签（如「试算表期末余额(tb_balance)」）。

### Requirement 6: 刷新取数入口（L 循环试点）

**User Story:** 作为审计师，我希望在四表导入/recalc 后能手动刷新 L 循环审定表的 TB 核对数据，以便即时看到最新试算表数字而无需重新打开底稿。

#### Acceptance Criteria

6.1. L1-L8 审定表组件工具栏加「🔄 刷新 TB 数据」按钮（调 render-config 重取 trial_balance，只刷核对行不覆盖手工审定行）。
6.2. M/N 循环已有 TB 数据（render 已取），无需额外刷新按钮（切 tab / reloadAll 已刷）。
6.3. 刷新按钮仅刷 TB 核对行，禁止覆盖审计师手工录入的审定行（手工优先铁律）。

### Requirement 7: 灰度与零回归

**User Story:** 作为项目经理，我希望新增的 L 循环 TB 取数能通过灰度开关控制，以便上线前零风险验证。

#### Acceptance Criteria

7.1. 默认 False。L 循环 `_fetch_tb_data` 仅在开关为 True 时执行（False 时 result 置 0 同现状）。
7.2. M/N 循环已有 TB 取数不受开关约束（已生产就位，仅 L 是新增）。
7.3. 前端 TB 核对行在 `trial_balance` 数据全 0 时不渲染（`hasTb` 守卫=逐字节等价当前无 TB 数据时审定表无核对行）。
7.4. 公式预设注册（Req3）为 additive 数据（只新增 seed 条目），开关关闭时公式管理面板仍可展示但标注「取数未启用」。

### Requirement 8: 正确性属性可测

**User Story:** 作为开发者，我希望取数逻辑、公式预设、TB 核对的正确性可被自动化测试验证，以便防止回归。

#### Acceptance Criteria

8.1. 后端取数纯函数可独立单测（不依赖真实 DB session，mock row 即可验证方向/聚合逻辑）。
8.2. 公式预设格式校验（每条含 page_key/expression/category/refs，expression 仅含 TB/SUM_TB 合法函数）。
8.3. 前端 tbReconcile computed 可 vitest 验证（mock allResponses + trial_balance prop）。

## Glossary

| 术语 | 含义 |
|------|------|
| Tier A | 可编辑取数公式（注册 formula_presets_seed，审计师可在公式管理中心修改/恢复默认） |
| Tier B | 子科目级预填（render 策略从 tb_balance 叶子拆分行级 seed，如 N5、K9） |
| TB 核对行 | 审定表底部「试算平衡表数/差异数」展示行（只读，不参与审定计算） |
| 灰度 | 配置开关 `LMN_FOUR_TABLE_EXTRACTION_ENABLED`（config.py Settings 层） |
| get_active_filter | 四表查询统一入口（按 dataset 版本+项目+年度过滤，禁裸 is_deleted） |
| 手工优先 | 审计师录入的审定行数值优先于任何自动取数/预填，自动值仅供核对不覆盖 |
| 宁缺勿造 | 无法从四表库干净推导的字段（分类/判断/文本）不预填不标 auto_calc |
