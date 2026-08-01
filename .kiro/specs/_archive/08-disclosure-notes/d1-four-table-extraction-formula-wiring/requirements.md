# Requirements Document

## Introduction

D1 应收票据循环底稿在「四表入库 → 底稿刷新取数 → 披露推送附注」这条链路上存在一个实证已确认的断点：**审定表 D1-1、原值明细表 D1-2（按类别）、坏账准备明细表 D1-4 在四表入库后仍渲染为全零空表**，审计师必须手工录入全部未审数。

历史上 `d-cycle-four-table-extraction-formulas` spec（已归档）对 D1 做了「宁缺勿造」决策，前提是「trial_balance / tb_balance 1121 只有科目总额、无『原值/坏账/净值 × 银行/商业』组合维度」。但对实际入库数据的只读核查证明该前提不成立：客户科目表在**叶子层**已干净编码了 D1 所需的两个维度——

- 原值：`1121.01 应收票据_银行承兑汇票` / `1121.02 应收票据_商业承兑汇票` / `1121.03 应收票据_信用证`
- 坏账准备：`1231.01 坏账准备_应收票据`

因此本 spec 的目标是：在**不破坏平台既有 `_build_adjudication_prefill` / `tier_a_seed` 范式**、遵守「叶子只汇总」「手工优先」「灰度开关」「fail-open」四条铁律的前提下，把 D1-2、D1-4（及经其派生的 D1-1）从四表库按科目映射刷新取数补齐；同时把 D1 各底稿间的连接取数公式、当页公式管理预设登记完整；最后复核两个披露表（上市/国企）与附注模块 D1 内容与源模板的一致性并做必要修订。

「科目映射」是本链路的关键：四表入库后，原始科目经 `account_mapping`（original_account_code → standard_account_code）标准化，标准科目经 `report_config` / `report_line_mapping` 映射到报表行、经 `note_account_mappings` 关联到附注章节。D1 取数须建立在「1121/1231 标准科目的叶子子科目」这一映射结果之上，而非臆造分类。

本 spec 仅覆盖 D1 相关底稿（D1-1 ~ D1-16 + 两个披露表 + 附注 五、4/八、4）。

## Requirements

### Requirement 1: D1-2 原值明细表（按类别）四表库取数补齐

**User Story:** 作为审计助理，我希望四表入库后 D1-2 原值明细表按票据种类自动带出期初/本期增减/期末未审数，这样我无需手工录入即可开始复核。

#### Acceptance Criteria

1.1 WHEN 四表提取灰度开关开启且 D1-2 无持久化行数据 THEN 系统 SHALL 从 `tb_balance` 科目 `1121` 的叶子子科目按名派生 D1-2 明细行（银行承兑汇票 / 商业承兑汇票 / 信用证等，随实际叶子科目而定）。
1.2 WHEN 构建 D1-2 明细行 THEN 每行 SHALL 取 `opening_balance` 作期初未审数、`debit_amount` 作本期增加、`credit_amount` 作本期减少，使 `期末未审 = 期初 + 增加 − 减少 = closing_balance`。
1.3 系统 SHALL 只汇总**叶子科目**（其 code 不是任何其它 code 的前缀），排除中间级 rollup 与科目本身（`1121`），防双算。
1.4 WHEN 某叶子子科目名称对应前端固定行（银行承兑汇票 / 商业承兑汇票）THEN 该行 SHALL 落到对应固定行（`fixed-bank` / `fixed-commercial`），其余叶子作动态行。
1.5 WHEN D1-2 已有持久化行数据（用户已编辑）THEN 系统 SHALL NOT 覆盖（手工优先）。
1.6 WHEN 无 `1121` 叶子子科目 或 查询异常 THEN 系统 SHALL 回退为既有默认固定空行且不阻断 render（fail-open）。
1.7 WHEN 灰度开关关闭（默认）THEN D1 render 输出 SHALL 与开关开启前逐字节等价（零回归）。

### Requirement 2: D1-4 坏账准备明细表四表库取数补齐

**User Story:** 作为审计助理，我希望四表入库后 D1-4 坏账准备明细表自动带出期初余额，这样期末坏账准备勾稽有起点。

#### Acceptance Criteria

2.1 WHEN 四表提取灰度开关开启且 D1-4 无持久化行数据 THEN 系统 SHALL 从 `tb_balance` 科目 `1231`（坏账准备）中名称含「应收票据」的叶子子科目（如 `1231.01`）派生 D1-4 期初/期末坏账准备数。
2.2 坏账准备为备抵科目 THEN 系统 SHALL 按 `closing_direction` 方向列带符号取数（绝对值口径下须按方向归一为计提口径正值）。
2.3 WHEN 无可干净映射的坏账准备叶子科目 THEN 系统 SHALL 只填 `按组合计提` 期初未审数、其余明细留空（宁缺勿造，不臆造单项/组合拆分）。
2.4 WHEN D1-4 已有持久化行数据 THEN 系统 SHALL NOT 覆盖（手工优先）。
2.5 WHEN 灰度开关关闭 THEN 输出 SHALL 逐字节等价（零回归）。

### Requirement 3: D1-1 审定表取数链完整可追溯

**User Story:** 作为现场经理，我希望 D1-1 审定表的原值/坏账/净值未审数在四表入库后自动就位，并能看到取数来源，这样复核有据可查。

#### Acceptance Criteria

3.1 WHEN D1-2 / D1-4 由四表库 seed 后 THEN D1-1 原值/坏账区块未审数 SHALL 经既有 cross-sheet 派生自动就位，净值 = 原值 − 坏账（computed 不落库）。
3.2 D1-1 的 `D1-adj-tb-amount`（TB↔审定净值核对行）SHALL 继续由 Tier A 可编辑公式 `TB('1121','期末余额')` 求值 seed（现状保留）。
3.3 系统 SHALL 在公式管理面板经 `tier_b_provenance` 展示 D1-2 / D1-4 的四表库取数来源描述（只读溯源，不可当单条公式编辑）。
3.4 D1-1 审定净值合计与 TB(1121) 的差异行 SHALL 可见，供审计师核对。

### Requirement 4: D1 当页公式管理预设与各底稿间连接取数公式登记

**User Story:** 作为审计助理，我希望在 D1 公式管理面板看到本循环底稿间的连接取数关系，这样能理解数据从哪来、到哪去。

#### Acceptance Criteria

4.1 系统 SHALL 在 `d_cycle_extraction_presets.json` 的 D1 段保留 Tier A 可编辑公式 `TB('1121','期末余额')`（现状）。
4.2 系统 SHALL 在 `tier_b_provenance` 的 D1 段登记 D1-2（← tb_balance 1121 叶子）与 D1-4（← tb_balance 1231.01）的四表库取数来源描述。
4.3 系统 SHALL 登记 D1 各底稿间的连接取数关系为只读溯源条目，至少覆盖：D1-1 原值 ← D1-2 小计、D1-1 坏账 ← D1-4 小计、D1-4 期末坏账 ↔ D1-15 ECL 测算、D1-1/披露表外项 ← D1-8 背书贴现未终止确认合计、D1-3 期后兑付 ← 序时账 1121 贷方。
4.4 每条连接取数溯源条目 SHALL 标注源 sheet、目标锚点、口径说明，且 `editable=False`（复杂 cross-sheet 归集不压成单条公式）。
4.5 WHEN 登记的 seed 目标锚点 THEN 该锚点 SHALL ∈ `d_cycle_anchor_registry.json` 的 D1 已知锚点集（未知锚点丢弃 + 告警）。

### Requirement 5: 两个披露表结构与源模板一致性复核

**User Story:** 作为质量控制复核合伙人，我希望 D1 上市/国企披露表的表结构、列头、动态插行区域、账龄枚举与源模板一致，这样附注披露合规。

#### Acceptance Criteria

5.1 系统 SHALL 以源模板 `backend/wp_templates/D/D1 应收票据.xlsx` 的两个披露 sheet（附注披露信息（上市公司）/（国企））为裁决者，复核现有 D1 上市/国企披露表的表结构、列头、两级表头。
5.2 WHEN 现有披露表或 `d1NoteSectionMap` 列结构与源模板不一致 THEN 系统 SHALL 参照源模板修复（列头、`group`/`flat` 表态、动态插行区域）。
5.3 系统 SHALL 识别披露表中的动态插行区域（按组合计提项目、账龄明细等），并接入账龄枚举模块（3 年段 / 5 年段 / 自定义）。
5.4 复核结论 SHALL 记录为可追溯的差异清单（无差异亦须显式记录）。

### Requirement 6: 披露表推送附注模块 D1 内容同步

**User Story:** 作为审计助理，我希望点击披露表「推送到附注」后，附注模块 D1（五、4/八、4）的 TAB 页签、各表结构、文本框内容都同步填充，这样附注模块有数据。

#### Acceptance Criteria

6.1 WHEN 用户在 D1 披露表点击推送到附注 THEN 附注 五、4（上市）/ 八、4（国企）SHALL 收到与披露表同构的子表数据（含两级表头、动态插行、账龄段）。
6.2 WHEN 披露表列结构与附注模板 `note_template_{listed,soe}.json` 的 D1 章节不一致 THEN 系统 SHALL 以源模板为准修复附注侧列结构（不压扁两级表头、不丢列）。
6.3 附注 D1 章节下的文本框内容 SHALL 与披露表文本域键集一一对应（无缺无余）。
6.4 WHEN 附注侧存在自造 / 与源模板不符的表结构 THEN 系统 SHALL 参照源模板重写，且经幂等脚本 + 契约测试固化。
6.5 推送 SHALL 复用既有 `useDisclosureAutoSync` / `syncToDisclosureNotes` 链路，不新造机制。

### Requirement 7: 零回归与守卫

**User Story:** 作为质量控制复核合伙人，我希望本次改动有测试守卫且不破坏既有功能，这样可放心合并。

#### Acceptance Criteria

7.1 灰度开关关闭时 D1 render 输出 SHALL 与改动前逐字节等价（characterization 测试）。
7.2 系统 SHALL 提供后端测试覆盖 D1-2 / D1-4 四表库 seed 的叶子选取、手工优先、fail-open、方向归一。
7.3 系统 SHALL 提供前端测试覆盖 D1-2 / D1-4 消费 seed（无持久化时 seed 就位、有持久化时不覆盖）。
7.4 披露表 / 附注结构修订 SHALL 由幂等脚本（`--dry-run` / `--check`）+ 契约测试固化。
7.5 关键链路（四表入库 → D1-1/D1-2/D1-4 有数据 → 披露推送附注有数据）SHALL 经浏览器实测复验（chrome-devtools + postgres 只读）。

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | trial_balance / tb_balance / tb_ledger / tb_aux_balance |
| 科目映射 | `account_mapping`（original→standard）+ `report_config`/`report_line_mapping`（standard→报表行）+ `note_account_mappings`（报表行→附注章节）|
| 叶子科目 | code 不是任何其它 code 前缀的科目（防中间级 rollup 与子科目双算）|
| 手工优先 | 已有持久化用户数据时不被 seed 覆盖 |
| Tier A | 可编辑单条公式（`TB(code,列)`），读 trial_balance 审定口径 |
| Tier B | 四表库明细/维度归集预填（tb_balance/tb_aux_balance/序时账），只读溯源 |
| 宁缺勿造 | 无法干净映射的分类行不 seed（不臆造）|
| 灰度开关 | `settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` |
| cross-sheet 派生 | 前端从同一 `allResponses` Map 读兄弟 sheet 数据 computed |
| D1-cat-rows | D1-2 原值明细行持久化 item_id（remark = JSON 数组）|
| D1-bd-*-rows | D1-4 坏账准备明细行持久化 item_id（individual/portfolio）|
