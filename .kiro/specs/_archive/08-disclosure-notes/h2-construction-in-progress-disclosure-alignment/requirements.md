# Requirements Document

## Introduction

H2 在建工程（construction in progress，科目 1604 + 工程物资 1605）披露三层（底稿披露表 / 同步映射 / 附注 §五、23 与 §八、23）与致同源模板 `backend/wp_templates/H/H2 在建工程.xlsx` 存在结构性偏差。四表取数与披露→附注同步链路已由归档 spec `h2-disclosure-linkage-and-prefill` 建好（`buildH2SyncPayload` / `_build_h2_detail_prefill` / 灰度 `H2_FOUR_TABLE_EXTRACTION_ENABLED`），但 **结构层未对齐**：

1. **两级表头被 md 重建压扁成单级**：
   - 上市「①在建工程明细」源模板为 `期末余额{账面余额/减值准备/账面净值} · 上年年末余额{账面余额/减值准备/账面净值}`（7 列两级），附注模板压成 3 列（项目/期末余额/上年年末余额）。
   - 国企「在建工程」汇总表与「（1）在建工程情况」源模板均为 `期末余额{账面余额/减值准备/账面价值} · 期初余额{账面余额/减值准备/账面价值}`（7 列两级），附注模板压成 3 列。
2. **垃圾表名**：上市第 6 张表在附注模板中被命名为表头首格泄漏值「项  目」，源模板实为「工程物资」（行：专用材料/专用设备/工器具/工程物资减值准备/合计），且前端 `h2NoteSectionMap.H2_LISTED_SUBTABLE.materials` 亦引用「项  目」→ 同步出孤儿子表。
3. **假数据行**：上市「在建工程明细」`rows[0]` 为 `row_type: header_label`（压扁的第二行表头残留）。
4. **columns / guidance 全缺**：上市 6 表 + 国企 4 表在附注模板中 `columns=0`（未表态）且无 `guidance`；seed 路径会走 `_infer_groups_from_headers` 前缀推断，制造凭空父表头，且金额列无 `format=amount`、附注 TAB 无编制提示。

本 spec 只做 H2 **结构对齐**：不改四表取数逻辑（已上线），不改已验证的同步触发机制，仅修正附注模板结构 + 前端映射/列定义使两级表头贯通，并补齐 columns/guidance。裁决者 = 源 xlsx（运行时权威 `backend/wp_templates/`）；附注列名以 `note_template_{listed,soe}.json` 既有 headers + 源 xlsx 为准。

## Glossary

- **两级表头**: 附注表列头分「父分组 + 叶子列」两层，经 `ColumnDef.group` → `_column_groups` 承载。
- **flat**: 单行表头显式标记，抑制后端 `_infer_groups_from_headers` 前缀推断。
- **seed 路径**: 新建项目 / 重新生成附注时从 `note_template_*.json` 生成，尚未被底稿推送覆盖。
- **push 路径**: `_source=workpaper`，投影器只渲染底稿推送的 `sub_table_data` + 载荷 columns。
- **孤儿子表**: 前端子表名与附注模板 `tables[].name` 不一致导致同步出的、附注 TAB 永空的表。

## Requirements

### Requirement 1: 附注模板两级表头结构对齐源模板

**User Story:** 作为编制附注的审计助理，我希望 H2 在建工程附注表按源模板呈现两级表头（期末/上年年末 各含 账面余额/减值准备/账面净值），以便附注列结构与底稿及源模板一致、不缺列不串味。

#### Acceptance Criteria

1. THE 附注模板 §五、23「在建工程明细」表 SHALL 具有两级表头：标签列「项目」+ 分组「期末余额」{账面余额, 减值准备, 账面净值} + 分组「上年年末余额」{账面余额, 减值准备, 账面净值}，共 7 个叶子列。
2. THE 附注模板 §八、23「在建工程」汇总表与「（1）在建工程情况」表 SHALL 各具有两级表头：标签列「项目」+ 分组「期末余额」{账面余额, 减值准备, 账面价值} + 分组「期初余额」{账面余额, 减值准备, 账面价值}，共 7 个叶子列（国企口径末列为「账面价值」而非上市的「账面净值」）。
3. THE 两级表头 SHALL 经 `ColumnDef.group` → `_column_groups` 单一机制承载，`group` 内不含 `/`，且 `_column_groups` 由 columns 派生自洽。
4. WHERE 源模板为单行表头的表（上市「在建工程」汇总/「重要在建工程项目变动情况」/「（续）」/「在建工程减值准备情况」/「工程物资」；国企「重要在建工程项目本期变动情况」/「本期计提在建工程减值准备情况」）, THE columns SHALL 显式标 `flat`（单级），不得残留 `_column_groups`。

### Requirement 2: 垃圾表名与假数据行清理

**User Story:** 作为编制附注的审计助理，我希望附注表名与源模板一致、无表头残留的假数据行，以便 TAB 页签显示正确、同步不产生孤儿子表。

#### Acceptance Criteria

1. THE 附注模板 §五、23 第 6 张表 SHALL 命名为「工程物资」（当前为「项  目」），固定行为 专用材料 / 专用设备 / 工器具 / 工程物资减值准备 / 合计。
2. THE 附注模板 §五、23「在建工程明细」表 SHALL 不含任何 `row_type: header_label` 行。
3. WHEN 表名从「项  目」迁移为「工程物资」, THE 前端 `h2NoteSectionMap.H2_LISTED_SUBTABLE.materials` SHALL 同步更新为「工程物资」，且旧键经同步载荷 `_removed_table_keys` 清理，避免附注残留孤儿子表。

### Requirement 3: columns 与 guidance 补齐（seed 路径）

**User Story:** 作为新建项目的审计助理，我希望首次生成的 H2 附注即带正确列元数据与编制提示，而非依赖前缀推断。

#### Acceptance Criteria

1. THE 附注模板 §五、23（6 表）与 §八、23（4 表）的每张表 SHALL 具有 `columns`，且 `columns[0].label == headers[0]`、首列标 `is_label`。
2. THE 每张表 SHALL 具有非空 `guidance`（取源模板红字 / 15 号文条款 / 「勾稽：」工具提示；不得自造披露口径）。
3. THE columns 的列 `key` SHALL 与前端同步载荷（`h2NoteSectionMap` / `buildH2SyncPayload`）的列 key 逐字一致，使 seed 路径与推送路径列键不漂移。
4. THE 金额列 SHALL 标 `format: "amount"`；文本列（计提原因 / 资金来源 / 工程进度 等）不标 format。

### Requirement 4: 前端同步载荷两级列定义与结构守卫

**User Story:** 作为审计助理，我希望点击披露表「推送到附注」后，附注两级表头正确落库且与底稿列结构一致。

#### Acceptance Criteria

1. THE 前端 `h2NoteSectionMap` SHALL 为「在建工程明细」（上市）与「在建工程」汇总/「（1）在建工程情况」（国企）提供带 `group` 的两级列定义，叶子列名与附注模板一致。
2. THE `buildH2SyncPayload` 推送的行对象键 SHALL 与两级 columns 的叶子列 key 一致（如 `end_book`/`end_impairment`/`end_net` 等），使投影器渲染出正确两级表头。
3. THE 契约测试 SHALL 校验：子表名逐字等于附注模板 `tables[].name`、标签列头等于 `headers[0]`、两级分组自洽、无孤儿子表名「项  目」残留；且含反向自检防守卫空转。
4. THE 后端结构守卫（`--check` + pytest）SHALL 校验 §五、23 / §八、23 对齐（表数/表名/两级/flat/columns/guidance），并直接 openpyxl 读源 xlsx tab 名与关键表头交叉比对。

### Requirement 5: 零回归与实测

**User Story:** 作为维护者，我希望 H2 结构对齐不破坏既有四表取数与同步链路，并经实测确认。

#### Acceptance Criteria

1. THE 改动 SHALL 不修改 `_h2_construction_in_progress.py` 的四表取数逻辑与灰度默认值。
2. THE 附注模板 JSON SHALL 保持可解析（`json.load` 成功），且既有 rows/text_sections 语义不被破坏。
3. THE H2 相关既有后端与前端测试 SHALL 保持通过。
4. THE 披露→附注推送 SHALL 经浏览器 + 只读 DB 实测：两级表头正确落库、`项  目` 孤儿表不再产生、`_last_sync_at` 前移。
