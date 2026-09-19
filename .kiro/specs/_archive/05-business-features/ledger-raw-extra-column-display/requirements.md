# Requirements Document

## Introduction

账套导入时，未被识别为标准字段的原始列（企业特有的备注、内部编号、经办人等）会被 `prepare_rows_with_raw_extra` 原样保存进 `tb_ledger.raw_extra` JSONB 列（导入界面「非关键列」档已明示"将原样复制到 raw_extra JSONB 字段中"）。数据没丢，但**在凭证/序时账查询时无法显示**：`ledger_penetration_service.py` 所有凭证查询的 `sa.select(...)` 都是写死的固定列，无一 select `raw_extra`，前端凭证明细表格也是固定列——非关键列"存了但查不出、看不见"。

本 spec 目标：让这些进了 `raw_extra` 的额外字段，在**查询凭证/序时账明细时能作为额外列正常显示**，同时过滤掉系统内部标记（`_` 前缀键），且对现有查询/显示零回归。

本文档为 requirements-first 流程第一阶段，除需求外附**可行性分析**（见末节），供决定是否推进 design/tasks。

## Glossary

| 术语 | 含义 |
|------|------|
| raw_extra | `tb_ledger`（及其它四表）的 JSONB 列，存导入时未映射到标准字段的原始列，形如 `{原始列名: 原始值}` |
| 系统标记 | raw_extra 中以 `_` 前缀的内部键：`_discarded_mappings`（多对一映射被丢弃的值）、`_aggregated_from_aux`/`_aux_row_count`（tb_balance 聚合标记），**非业务字段** |
| 业务额外字段 | raw_extra 中非 `_` 前缀的键，即导入时的非关键列，本 spec 要显示的对象 |
| 凭证查询端点 | `ledger_penetration_service.py` 中返回分录行的方法：`get_ledger_entries` / `get_ledger_entries_cursor` / `get_all_ledger_entries` / `get_voucher_entries` / `get_aux_ledger_entries` / `get_aux_ledger_entries_cursor` |
| 动态列 | 前端凭证明细表格在固定列（日期/凭证号/摘要/借/贷…）之后，按本次查询结果中出现的 raw_extra 业务键动态追加的额外列 |

## Requirements

### Requirement 1: 后端凭证查询透出 raw_extra 业务字段

**User Story:** 作为审计人员，我希望查询凭证/序时账明细时，接口能返回导入时保留的非关键列，以便看到企业特有的备注/编号等信息。

#### Acceptance Criteria

1. WHEN 调用序时账明细查询（`get_ledger_entries` / `get_ledger_entries_cursor`）THEN 返回的每条分录 SHALL 包含一个 `extra_fields` 字段（对象/字典），内容为该行 `raw_extra` 中**非 `_` 前缀键**的键值对。
2. WHEN 调用凭证分录查询（`get_voucher_entries`）THEN 返回的每条分录 SHALL 同样包含 `extra_fields`。
3. WHEN 调用全量序时账查询（`get_all_ledger_entries`）THEN 返回的每条分录 SHALL 同样包含 `extra_fields`。
4. WHEN 调用辅助明细查询（`get_aux_ledger_entries` / `get_aux_ledger_entries_cursor`）THEN 返回的每条分录 SHALL 同样包含 `extra_fields`。
5. WHERE 某行 `raw_extra` 为 NULL、为空对象、或仅含 `_` 前缀键 THEN 该行的 `extra_fields` SHALL 为空对象 `{}`（不报错、不遗漏该行）。

### Requirement 2: 系统内部标记必须过滤，不得作为业务字段透出

**User Story:** 作为审计人员，我不希望看到系统内部标记（如 `_discarded_mappings`），只想看真实的业务额外列。

#### Acceptance Criteria

1. WHEN 构建 `extra_fields` THEN 系统 SHALL 排除所有以 `_` 开头的键（`_discarded_mappings` / `_aggregated_from_aux` / `_aux_row_count` 及任何未来 `_` 前缀标记）。
2. WHEN `raw_extra` 同时含业务键与 `_` 前缀键 THEN `extra_fields` SHALL 只保留业务键，且业务键的值保持原始内容。

### Requirement 3: 前端凭证明细表格动态显示额外列

**User Story:** 作为审计人员，我希望凭证明细表格在固定列之后自动出现这些额外字段列，列名即原始列名。

#### Acceptance Criteria

1. WHEN 凭证/序时账明细表格渲染一批分录 THEN 表格 SHALL 在既有固定列之后，为本批结果中出现过的 `extra_fields` 键**并集**动态追加列，列标题为该原始键名。
2. WHEN 某分录缺少某个额外列的值 THEN 该单元格 SHALL 显示为空（不显示 `undefined`/`null`）。
3. WHEN 本批结果中所有分录的 `extra_fields` 均为空 THEN 表格 SHALL 不追加任何额外列（视觉与当前一致）。
4. WHEN 额外列数量较多 THEN 追加列 SHALL 有合理最小宽度并允许横向滚动，不挤压固定列。

### Requirement 4: 覆盖凭证查询的全部相关端点，口径一致

**User Story:** 作为审计人员，无论从科目穿透、凭证号穿透还是全量列表进入，我看到的额外字段行为都应一致。

#### Acceptance Criteria

1. WHEN 任一凭证查询端点（Glossary 所列）返回分录 THEN `extra_fields` 的构建口径（过滤规则、空值处理）SHALL 完全一致（应由单一共享 helper 实现，避免多处分叉）。
2. IF 某端点当前不 select `raw_extra` THEN 实现时 SHALL 在其 `sa.select(...)` 中补上 `raw_extra` 列。

### Requirement 5: 零回归

**User Story:** 作为平台维护者，我要求本改动不破坏现有凭证查询与显示、不改数据库结构。

#### Acceptance Criteria

1. WHEN 本改动上线 THEN 所有凭证查询的**既有固定字段**（id/voucher_date/voucher_no/account_code/account_name/debit_amount/credit_amount/summary/counterpart_account/preparer/running_balance 等）SHALL 保持字段名与取值不变。
2. WHEN 本改动上线 THEN SHALL 不新增/修改任何数据库表或列（`raw_extra` 已存在），不改导入写入逻辑。
3. WHEN 某项目/年度的凭证行本就无非关键列（`raw_extra` 全空）THEN 查询响应除多出一个恒为 `{}` 的 `extra_fields` 外，与当前完全一致；前端表格视觉与当前完全一致。
4. WHEN 现有依赖这些端点的功能（如 C24 会计分录细节测试、抽凭联动、损益按月取数 `expenseLedgerMonthlyPull`）运行 THEN SHALL 不受影响（它们只读既有固定字段，`extra_fields` 为附加字段）。

### Requirement 6: 正确性属性可测

**User Story:** 作为平台维护者，我要求关键行为有属性级测试守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN SHALL 覆盖：`_` 前缀键被过滤 / 业务键保序透出 / raw_extra 为 NULL 或空 → `extra_fields={}` / 既有固定字段不变（零回归锚点）/ 前端动态列取本批键并集。

## 可行性分析（Feasibility）

### 结论：可行，低风险，改动集中

现有基建已具备全部前置条件，本质是"把已存好的数据接出来显示"，非新增数据流。

### 支撑证据（已核实代码）

1. **数据已存好**：`ledger_import/writer.py::prepare_rows_with_raw_extra` 导入时把未映射列写入 `raw_extra`（`{原始列名:原始值}`），并已 `_sanitize_raw_extra` 保证 JSONB 可序列化。多对一丢弃值进 `_discarded_mappings`。
2. **系统标记有清晰约定**：非业务键统一 `_` 前缀（`_discarded_mappings`/`_aggregated_from_aux`/`_aux_row_count`），过滤规则简单可靠（`k for k in raw_extra if not k.startswith('_')`）。
3. **后端改动点明确且集中**：`ledger_penetration_service.py` 的 6 个查询方法，各自 `sa.select(...)` 补 `tbl.c.raw_extra` + 序列化时用单一 helper 展开 `extra_fields`。改动为纯 additive（多返一个字段）。
4. **前端改动点明确**：主查询组件 `LedgerPenetration.vue`（序时账/凭证明细表格）改为固定列后按 `extra_fields` 键并集动态追加 `el-table-column`。Element Plus 原生支持 `v-for` 动态列。

### 风险与注意点

- **零回归**：新增字段/列为 additive，既有消费者（C24 分录测试、抽凭、按月取数）只读固定字段不受影响；需以测试锚定固定字段集合不变。
- **展开成本**：raw_extra 是逐行 JSONB，展开在 Python 侧做（select 已多取一列），大分页（entries-all 最大 5000/页）下为轻量字典过滤，开销可忽略。
- **动态列一致性**：前端动态列取"本批结果键并集"，翻页/换科目时列集合可能变化——需在 design 明确列集合作用域（按当前已加载数据算，或每页重算），避免列闪烁。
- **导出对齐（可选）**：`export-ledger/{account_code}` Excel 导出目前也是固定列，是否同步导出额外列可在 design 定为可选项。

### 工作量预估

- 后端：1 个共享 helper + 6 处 select/序列化改动 + 属性测试，改动小。
- 前端：1 个巨型组件（`LedgerPenetration.vue` 3700+ 行）内的表格列渲染改造 + 动态列逻辑，需谨慎定位但范围局部。
- 属于跨前后端联动但范围可控，适合小 spec 落地。
