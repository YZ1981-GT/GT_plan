# Requirements Document

## Introduction

H8 使用权资产（科目 1641 使用权资产 / 1642 使用权资产累计折旧 / 1643 使用权资产减值准备，报表行 `BS-031` = `TB('1641')−TB('1642')−TB('1643')`）披露→附注链路的**行集结构已与源模板一致**（`backend/wp_templates/H/H8 使用权资产.xlsx`），欠账集中在列元数据与文本元数据：

实测（2026-07-31）：

1. **两版模板 `columns=0` + 无 `guidance`**：上市 §五、25 与国企 §八、26 各 1 张表均未表态 → seed 路径走 `_infer_groups_from_headers` 前缀推断（国企 `本期增加`/`本期减少` 会被反猜出凭空「本期」父表头）、金额列无 `format`、附注 TAB 无编制提示。
2. **🔴 上市模板 `……` 占位列头**：headers 为 `['项目','房屋及建筑物','机器设备','运输设备','……','合计']`，而底稿默认分类（`H8_LISTED_DEFAULT_CATEGORIES`）第 4 类是 **`其他`**，同步载荷 `buildH8ListedColumns` 推的也是 `其他` → **seed 路径渲染出一个永远收不到数据的 `……` 列**（与 H1「`……` 占位列头必须展开成实际类别」同款）。
3. **🔴 `_note_texts` 缺中文 `title`**：三条文本（`listed-short-low` / `listed-impairment` / `soe-impairment`）只有 `section` + `text`。后端 `_format_note_texts` 缺 title 时用 `section` 兜底 → 附注正文渲染成 **`【listed-short-low】`** 等英文键（违反 UI 全中文化）。
4. **`_note_texts` 无空文本过滤**：`text: state.noteShortLow || ''` 会推入空串条目。
5. 国企 `text_sections` 为 `[]`（**实证正确**，源 xlsx 国企 sheet 行 7~31 只有表格无说明段，非欠账）。

**非欠账（实证确认，勿改）**：
- 行集：上市 38 行四层（含每层 `……` 可扩行）与源 xlsx 行 7~45 逐行一致；国企 25 行五层（原值/累计折旧/账面净值/减值准备/账面价值 × 合计+土地/房屋建筑物/机器运输办公设备/其他）与源 xlsx 行 7~31 一致。
- **上市 `……` 行必须保留**：它们是底稿模型的**真实可扩行**（`cost_inc_ellipsis` 等键参与 `sumOf` 汇总），与「可无限量添加行」那类纯占位说明不同 —— 删掉会破坏载荷↔模板行对齐。
- 自动同步：两个 Tab 的 `scheduleAutoSync` 位于 `onSave` 回调（数据变更触发），**无自调度**。
- 国企层 三/五（账面净值/账面价值）的 `本期增加`/`本期减少` 在源模板填 `——`（推导层不作变动分析），载荷已用 `movementNa` 置 `null`，正确。

## Glossary

- **flat**: 单行表头显式标记，抑制后端 `_infer_groups_from_headers` 前缀推断。
- **列转置**: 列 = 资产类别、行 = 变动层次明细（H8 上市即此形态）。
- **`……` 可扩行**: 源模板每个增减块末尾的省略号行，在底稿模型中是**真实可录入行**并参与小计，非占位说明。
- **seed 路径**: 新建项目/重新生成附注时从模板生成，尚未被底稿推送覆盖。
- **`_note_texts`**: `sub_table_data` 内的 `_` 前缀元数据键，服务层 pop 后写入 `text_content`；缺 `title` 会以 `section` 英文键兜底渲染。

## Requirements

### Requirement 1: 模板 columns 补齐与 `……` 列头展开

**User Story:** 作为新建项目的审计助理，我希望首次生成的使用权资产附注表列头正确、列可收到数据，而不是出现一个永远空白的「……」列。

#### Acceptance Criteria

1. THE 上市 §五、25 表 headers 的 `……` SHALL 展开为 `其他`，与底稿默认分类 `H8_LISTED_DEFAULT_CATEGORIES` 第 4 类及同步载荷列名一致（最终 6 列：项目/房屋及建筑物/机器设备/运输设备/其他/合计）。
2. THE 上市与国企表 SHALL 各具备 `columns`，`columns[0].label == headers[0]`、首列标 `is_label`、单行表头显式 `flat`、金额列标 `format: 'amount'`。
3. THE 上市列 `key` SHALL 与载荷 `buildH8ListedColumns` 同口径（资产类别名作 key，合计列 key 为 `合计`）；THE 国企列 `key` SHALL 为 `label/begin/increase/decrease/end`。
4. THE 单级表头 SHALL NOT 残留 `_column_groups`。

### Requirement 2: guidance 补齐

**User Story:** 作为编制附注的审计助理，我希望附注 TAB 有编制提示与勾稽说明。

#### Acceptance Criteria

1. THE 两版表 SHALL 具备非空 `guidance`，内容仅取源模板/15 号文口径与勾稽关系，不自造披露口径。
2. THE 上市 `guidance` SHALL 说明：四层结构（账面原值/累计折旧/减值准备/账面价值）、各层 期末 = 期初 + 本期增加 − 本期减少、账面价值 = 原值 − 累计折旧 − 减值准备、合计列 = 各类别之和、`……` 行为可扩明细行、短期租赁与低价值资产租赁费用见对应附注、15 号文减值测试披露要求。
3. THE 国企 `guidance` SHALL 说明：五层结构与各层「其中：」四类别、层间派生（账面净值 = 原值 − 累计折旧；账面价值 = 账面净值 − 减值准备）、以及源模板列示约定（三、账面净值 与 五、账面价值 两层的「本期增加/本期减少」填 `——`）。

### Requirement 3: `_note_texts` 中文标题与空文本过滤

**User Story:** 作为审计助理，我希望附注正文显示中文小标题，而不是 `【listed-short-low】` 这类英文键。

#### Acceptance Criteria

1. THE 三条 `_note_texts` SHALL 各带中文 `title`：`listed-short-low` → 「短期租赁及低价值资产租赁费用说明」；`listed-impairment` / `soe-impairment` → 「使用权资产减值情况说明」。
2. THE 空白（trim 后为空）文本 SHALL 不产生 `_note_texts` 条目；全部为空时 SHALL 不产生 `_note_texts` 键。
3. THE `_note_texts` SHALL 位于 `sub_table_data` 内（现状已正确，守卫固化防回退）。

### Requirement 4: 守卫与零回归

**User Story:** 作为维护者，我希望这些结论被守卫固化，不被 md 重建或并发会话回退。

#### Acceptance Criteria

1. THE 后端守卫 SHALL 校验两版：表名、行集（上市 38 行四层含 `……` 可扩行、国企 25 行五层）、`columns` 表态与 key、`columns[0].label == headers[0]`、`guidance` 非空、无 `_column_groups`、headers 中不得再出现 `……`；并用 openpyxl 直读源 xlsx 交叉比对表头与行标签；含反向自检。
2. THE 前端守卫 SHALL 校验：载荷列 key 与模板 `columns` key 一致、`_note_texts` 每条有中文 title、空文本被过滤、`_note_texts` 在 `sub_table_data` 内、两 Tab 无自调度（`scheduleAutoSync` 不得出现在 `syncToNotes` 函数体内）。
3. THE CI SHALL 挂载 `note-h8-structure` job。
4. THE H8 既有测试 SHALL 保持通过；附注模板 JSON SHALL 保持可解析；上市 `……` 行 SHALL 保留（守卫正向断言，防被误删）。
