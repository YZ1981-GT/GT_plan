# Requirements Document

## Introduction

H5 油气资产（科目 1631 油气资产 / 1632 累计折耗 / 减值准备）披露→附注链路存在**载荷与模板严重不符 + 4 个静默 bug**。与 H2/H3 不同，H5 的**附注模板结构本身是正确的**（与源模板 `backend/wp_templates/H/H5 油气资产.xlsx` 的「附注披露信息（国有企业）」逐行一致：5 列 `项目/期初余额/本期增加额/本期减少额/期末余额`，16 行四层结构），问题全在前端载荷侧。

实测欠账（2026-07-31）：

1. **🔴 载荷行是自造结构**：组件 `summaryRows` 推 4 行自拟标签（`油气资产原值` / `减：累计折耗` / `减：减值准备` / `油气资产净值`），而模板（= 源模板）要求 **15 行**四层：`一、原价合计` + 其中 3 类（探明矿区权益/未探明矿区权益/井及相关设施）、`二、累计折耗合计` + 其中 2 类、`三、油气资产减值准备累计金额合计` + 其中 3 类、`四、油气资产账面价值合计` + 其中 3 类 → 行标签全不匹配，附注拿到的是错的行。
2. **🔴 列数与列序都错**：`H5_SOE_COLUMNS` 只声明 **3 列**（`项目/期末余额/期初余额`），模板是 **5 列**（`项目/期初余额/本期增加额/本期减少额/期末余额`）；载荷行用**位置化** `values: [endBalance, beginBalance]`（仅 2 值、且顺序与模板相反）→ **期末余额会落进期初余额列**。
3. **🔴 `_note_texts` 放在载荷顶层被静默丢弃**：`SyncFromWorkpaperRequest` 无顶层 `_note_texts` 字段（pydantic 忽略额外字段），该元数据键必须放在 `sub_table_data` 内 → 「补充披露（国资监管要求）」文本从未进入附注。
4. **🔴 自动同步是假接入（自调度）**：`syncToNote()` 内部调 `autoSync.scheduleAutoSync(syncToNote)` = 调度自己 → 800ms 周期重复 POST，且骗过 `disclosureAutoSyncCoverage` 守卫（守卫只看有无该调用）；从未监听实际数据变更。
5. **期初余额恒为 0**：`summaryRows` 硬编码 `beginBalance: 0`。
6. **模板缺 `columns` / `guidance`**：§八、25 唯一表 `columns=0`（未表态）→ seed 路径走 `_infer_groups_from_headers` 前缀推断；无编制提示。
7. 本地重复定义 `ColumnDef`（不含 `flat`/`group`/`format`）而非复用共享 `disclosureColumnDefs`。

**上市侧不做**（已实证，非欠账）：`note_template_variant_matrix.json` 的 `you_qi_zi_chan.listed_standalone = null`，且 `note_template_listed.json` 中 `油气资产` 章节数 **实测为 0** —— 上市准则下油气资产不单独设附注章节。源 xlsx 虽有「附注披露信息（上市公司）」sheet（4 层列转置），但无落点，**不得凭空新建章节**（宁缺勿造）。

## Glossary

- **四层结构**: 原价 / 累计折耗 / 减值准备累计 / 账面价值，各层 1 合计行 + 「其中：」资产类别明细行。
- **flat**: 单行表头显式标记，抑制后端 `_infer_groups_from_headers` 前缀推断。
- **规范行形态**: `sub_table_data = {表名: [业务键 dict, ...]}`；位置化 `{label, values:[]}` 为非规范历史形态。
- **自调度**: 同步函数内部调用 `scheduleAutoSync(自己)`，导致周期重复 POST 且骗过覆盖率守卫。
- **seed 路径**: 新建项目/重新生成附注时从模板生成，尚未被底稿推送覆盖。

## Requirements

### Requirement 1: 载荷行集对齐源模板四层结构

**User Story:** 作为编制附注的审计助理，我希望推送到附注的行次与源模板一致，以便附注呈现的是准则要求的四层油气资产结构而非自拟摘要。

#### Acceptance Criteria

1. THE 载荷 SHALL 推送 **15 行**（4 个层合计 + 11 个「其中：」类别行；累计折耗层源模板只列 2 类），行标签逐字等于模板 `rows[].label`：`一、原价合计` / `其中：1．探明矿区权益` / `2．未探明矿区权益` / `3．井及相关设施` / `二、累计折耗合计` / `其中：1．探明矿区权益` / `2．井及相关设施` / `三、油气资产减值准备累计金额合计` / `其中：1．探明矿区权益` / `2．未探明矿区权益` / `3．井及相关设施` / `四、油气资产账面价值合计` / `其中：1．探明矿区权益` / `2．未探明矿区权益` / `3．井及相关设施`。
2. THE 四个层合计行 SHALL 标 `is_total`。
3. WHERE 底稿仅能提供层级合计（原值/折耗/减值/净值），THE 载荷 SHALL 只填对应层合计行的 `期末余额`，其「其中：」类别行与 `期初余额`/`本期增加额`/`本期减少额` SHALL 为 `null`（宁缺勿造，不得用 0 冒充已知值）。
4. THE `四、油气资产账面价值合计` 期末值 SHALL 等于 原价期末 − 累计折耗期末 − 减值准备期末（派生自洽）。

### Requirement 2: 列定义与行形态规范化

**User Story:** 作为审计助理，我希望数据落在正确的列，而不是期末余额跑到期初余额列。

#### Acceptance Criteria

1. THE `H5_SOE_COLUMNS` SHALL 声明 5 列，`key`/`label` 与模板 `headers` 一一对应：`label→项目`（`is_label` + `flat`）/ `begin→期初余额` / `increase→本期增加额` / `decrease→本期减少额` / `end→期末余额`，金额列标 `format: 'amount'`。
2. THE 载荷行 SHALL 为业务键 dict（键 ⊆ columns 的 key 集合），SHALL NOT 使用位置化 `values` 数组。
3. THE `ColumnDef` SHALL 复用共享 `composables/disclosureColumnDefs`，不在本文件重复定义。
4. THE 源模板列示约定（`四、账面价值合计` 层的 `本期增加额`/`本期减少额` 填「—」）SHALL 体现在 `guidance` 中。

### Requirement 3: `_note_texts` 位置纠正

**User Story:** 作为审计助理，我希望填写的「补充披露（国资监管要求）」真的出现在附注正文里。

#### Acceptance Criteria

1. THE `_note_texts` SHALL 放在 `sub_table_data` 内（`sub_table_data._note_texts`），不得置于载荷顶层（顶层会被 pydantic 静默丢弃）。
2. THE 每条 `_note_texts` SHALL 带中文 `title`，空文本 SHALL 过滤。

### Requirement 4: 自动同步真接入

**User Story:** 作为审计助理，我希望改完披露数据不点按钮也会同步，且不产生周期性重复请求。

#### Acceptance Criteria

1. THE `syncToNote()` 内部 SHALL NOT 调用 `scheduleAutoSync(syncToNote)`（自调度 → 800ms 周期重复 POST 且骗过覆盖率守卫）。
2. THE 组件 SHALL 用 `watch` 监听**构建载荷所用的实际数据**（`summaryRows` 与说明文本）触发 `scheduleAutoSync(syncToNote)`。
3. THE watch SHALL NOT 使用 `_xxxMounted` 一次性防护（会吞掉「切走再切回后的第一次编辑」）。

### Requirement 5: 模板 columns / guidance 补齐

**User Story:** 作为新建项目的审计助理，我希望首次生成的 §八、25 即带正确列元数据与编制提示，而非依赖前缀推断。

#### Acceptance Criteria

1. THE §八、25 唯一表 SHALL 具有 `columns`（5 列、显式 `flat`、`columns[0].label == headers[0]`、首列 `is_label`）。
2. THE 该表 SHALL 具有非空 `guidance`（取源模板列示约定 + 层间勾稽，不自造披露口径）。
3. THE 修订 SHALL 由幂等脚本完成（`--dry-run`/`--check`），复用 `_note_structure_kit`。

### Requirement 6: 守卫与零回归

**User Story:** 作为维护者，我希望这些静默 bug 与上市豁免结论被守卫固化，不会被后人或并发会话回退。

#### Acceptance Criteria

1. THE 后端守卫 SHALL 校验 §八、25 结构（表名/行集 16 行四层/flat/columns key 与前端一致/guidance），并用 openpyxl 直读源 xlsx 表头与行标签交叉比对，含反向自检。
2. THE 前端守卫 SHALL 校验：行标签逐字等于模板、行形态为 dict、列定义 5 列且与模板对应、`_note_texts` 在 `sub_table_data` 内、无自调度、账面价值层派生正确。
3. THE 上市侧豁免 SHALL 在守卫中显式登记并写明依据（`variant_matrix` listed=null + listed 模板实测 0 章节），防后人误建章节。
4. THE H5 既有测试 SHALL 保持通过；附注模板 JSON SHALL 保持可解析。
