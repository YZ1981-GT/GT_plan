# Requirements Document

## Introduction

H3 投资性房地产（科目 1521 投资性房地产 / 1525 投资性房地产累计折旧摊销 / 1526 投资性房地产减值准备，报表行 `BS-027`）披露三层（底稿披露表 / 同步映射 / 附注 §五、21 与 §八、21）与致同源模板 `backend/wp_templates/H/H3 投资性房地产.xlsx` 严重不符。与 H1（仅缺 seed columns）、H2（两级表头压扁）不同，**H3 的同步映射是一个从未与模板对齐过的半成品**：

1. **🔴 章节号错误（数据污染）**：`h3NoteSectionMap.H3_NOTE_SECTION.soe` 原为 `'八、22'`，而 `八、22` 是**固定资产**章节（投资性房地产 soe 实为 `八、21`，`note_template_variant_matrix.json` 与 DB 双证）→ H3 国企披露推送会写进固定资产章节。**本会话已先行修正**，本 spec 负责补守卫防回归。
2. **载荷表名与模板表名完全不匹配** → 同步必产孤儿子表（附注 TAB 永空）：
   - 载荷用 `以成本模式计量的投资性房地产（账面原值）` / `（累计折旧和累计摊销）` / `（减值准备）` / `以公允价值模式计量的投资性房地产`（国企另一套 `投资性房地产（账面原值）`…）；
   - 模板上市实为 `按成本计量的投资性房地产` / `按公允价值计量的投资性房地产` / `未办妥产权证书的情况`；国企实为 `以成本计量` / `以公允价值计量` / 第三张重名 `以公允价值计量`（表名重复 → 同名互相覆盖丢整表）。
3. **载荷行形态非规范**：`buildTableRows` 产出 `{label, values:[]}` 位置化行，而 `sub_table_data` 唯一规范形态是 `{key: list[dict]}`（业务键行）。
4. **国企两级表头被压扁**：源模板「以成本计量」为 7 列两级（`本期增加{购置或计提, 自用房地产或存货转入}` / `本期减少{处置, 转为自用房地产}`），「以公允价值计量」为 8 列两级（`本期增加{购置, 自用房地产或存货转入, 公允价值变动损益}` / `本期减少{处置, 转为自用房地产}`）；模板均压成 5 列。
5. **上市结构被压扁成变动矩阵**：源模板上市是**列转置**结构（列 = 房屋、建筑物 / 土地使用权 / 在建工程 / 合计；行 = 四层 38 行明细：账面原值 / 累计折旧和累计摊销 / 减值准备 / 账面价值，各含期初/本期增加(外购·转入·合并)/本期减少(处置·其他转出)/期末），而载荷按「一行一类别 + 期初增减期末」的行式变动表推送 → 与模板行列关系相反。
6. **国企第 3 张表重名 + 上市缺表**：国企 `tables[2]` 名为 `以公允价值计量`（与 `tables[1]` 同名）应为「未办妥产权证书的投资性房地产」；上市模板缺源模板 (4)「房地产转换情况及改变计量模式的情况」纯文本段。
7. **无自动同步**：`GtH3InvestmentProperty.vue` 无 `useDisclosureAutoSync` / `syncToDisclosureNotes` / `scheduleAutoSync`（grep 0 命中）→ 不点按钮永不进附注。
8. **columns / guidance 全缺**：两版共 6 表 `columns=0`（未表态）且无 `guidance`。

本 spec 目标：以源 xlsx 为唯一裁决者，重建 H3 披露三层结构，使「底稿录入 → 推送 → 附注」列结构、表名、行形态全链一致，并补齐自动同步与守卫。不改 H3 既有四表取数与跨底稿勾稽（`h3TransferReconcile` / `h3MortgageReconcile` 已上线）。

## Glossary

- **两级表头**: 附注表列头分「父分组 + 叶子列」两层，经 `ColumnDef.group` → `_column_groups` 承载。
- **flat**: 单行表头显式标记，抑制后端 `_infer_groups_from_headers` 前缀推断。
- **列转置结构**: 列 = 资产类别（房屋、建筑物/土地使用权/在建工程/合计），行 = 变动层次明细（上市 H3 即此形态）。
- **孤儿子表**: 载荷子表名与附注模板 `tables[].name` 不一致而同步出的、附注 TAB 永空的表。
- **规范行形态**: `sub_table_data = {表名: [业务键 dict, ...]}`；位置化 `{label, values:[]}` 为非规范历史形态。
- **计量模式**: 成本计量 vs 公允价值计量（源模板「不适用的删除」= 二选一条件性披露）。

## Requirements

### Requirement 1: 章节号与表名对齐模板（消除数据污染与孤儿子表）

**User Story:** 作为审计助理，我希望 H3 披露推送落到正确章节与正确表，以便附注能看到我录的数据，且不污染固定资产章节。

#### Acceptance Criteria

1. THE `H3_NOTE_SECTION` SHALL 为 `{listed: '五、21', soe: '八、21'}`（与 `note_template_variant_matrix.json` 及 DB 实存一致）。
2. THE 载荷子表名 SHALL 逐字等于附注模板 `tables[].name`；上市为「按成本计量的投资性房地产」/「按公允价值计量的投资性房地产」/「未办妥产权证书的情况」，国企为「以成本计量」/「以公允价值计量」/「未办妥产权证书的投资性房地产」。
3. THE 附注模板国企 `tables[2]` SHALL 由重名 `以公允价值计量` 改为「未办妥产权证书的投资性房地产」（消除同名互相覆盖丢表）。
4. WHEN 表名迁移发生, THE 载荷 SHALL 通过 `_removed_table_keys` 上报旧表名，避免附注残留孤儿空表。
5. THE 守卫 SHALL 断言两版章节号与全部子表名逐字命中模板，且 `八、22` 不出现在 H3 任何映射中。

### Requirement 2: 国企两级表头按源模板重建

**User Story:** 作为编制附注的审计助理，我希望国企投资性房地产表呈现源模板的两级表头，以便列结构与致同模板一致。

#### Acceptance Criteria

1. THE 附注模板 §八、21「以成本计量」表 SHALL 为 7 列两级：标签列「项目」+「期初余额」+ 分组「本期增加」{购置或计提, 自用房地产或存货转入} + 分组「本期减少」{处置, 转为自用房地产} +「期末余额」。
2. THE 附注模板 §八、21「以公允价值计量」表 SHALL 为 8 列两级：标签列「项目」+「期初公允价值」+ 分组「本期增加」{购置, 自用房地产或存货转入, 公允价值变动损益} + 分组「本期减少」{处置, 转为自用房地产} +「期末公允价值」。
3. WHERE 列本身为 rowspan=2 的独立列（期初余额 / 期末余额 / 期初公允价值 / 期末公允价值）, THE columns SHALL 不带 `group`（混合分组）。
4. THE 两级表头 SHALL 经 `ColumnDef.group` → `_column_groups` 单一机制承载，`group` 内不含 `/`，且 `_column_groups` 与 columns 自洽。

### Requirement 3: 行集按源模板层次重建

**User Story:** 作为审计助理，我希望附注行次与源模板一致（分层合计 + 其中类别），以便披露完整可勾稽。

#### Acceptance Criteria

1. THE §八、21「以成本计量」行集 SHALL 为 5 层，每层 1 个合计行 + 2 个类别行：一、账面原值合计 / 二、累计折旧和累计摊销合计 / 三、投资性房地产账面净值合计 / 四、投资性房地产减值准备累计金额合计 / 五、投资性房地产账面价值合计，各层下为「1、房屋、建筑物」「2、土地使用权」。
2. THE §八、21「以公允价值计量」行集 SHALL 为 3 层（一、成本合计 / 二、公允价值变动合计 / 三、投资性房地产账面价值合计），各层下为「其中：1、房屋、建筑物」「2、土地使用权」。
3. THE §五、21「按成本计量的投资性房地产」行集 SHALL 按源模板四层列示（一、账面原值{1.期初余额, 2.本期增加金额(（1）外购/（2）存货\\固定资产\\在建工程转入/（3）企业合并增加), 3.本期减少金额(（1）处置/（2）其他转出), 4.期末余额} / 二、累计折旧和累计摊销{…（1）计提或摊销/（2）企业合并增加/（3）其他增加…} / 三、减值准备{…（1）计提/（2）其他增加…} / 四、账面价值{1.期末账面价值, 2.期初账面价值}），且列为 房屋、建筑物 / 土地使用权 / 在建工程 / 合计（列转置）。
4. THE §五、21「按公允价值计量的投资性房地产」行集 SHALL 为 一、期初余额 / 二、本期变动（加：外购 / 存货\\固定资产\\在建工程转入 / 企业合并增加 / 减：处置 / 其他转出 / 公允价值变动）/ 三、期末余额。
5. THE 模板 rows SHALL 不含「可无限量添加行」占位说明行（源模板占位语义移入 `guidance`），且不含 `row_type: header_label` 假数据行。

### Requirement 4: 载荷行形态规范化与条件性计量模式

**User Story:** 作为审计助理，我希望切换计量模式后附注只保留适用的表，且推送的数据能正确落格。

#### Acceptance Criteria

1. THE 载荷 `sub_table_data` SHALL 为 `{表名: [业务键 dict, ...]}` 规范形态，行键与该表 `columns[].key` 一致（不得用位置化 `values` 数组）。
2. WHEN `measurementModel === 'cost'`, THE 载荷 SHALL 推成本计量表并把公允价值计量表名列入 `_removed_table_keys`；WHEN `'fair_value'`, 反之。
3. THE 「未办妥产权证书」表 SHALL 两种计量模式下均推送（不受模式门控），无行时按条件表语义不推空表且列入 `_removed_table_keys`。
4. THE 合计行 SHALL 由载荷层统一补齐（与 UI 合计同源、对已带合计行幂等），字面取本章节实证值。

### Requirement 5: 自动同步与文本段

**User Story:** 作为审计助理，我希望录完披露数据不点按钮也能进附注，且定性披露有录入位置。

#### Acceptance Criteria

1. THE `GtH3InvestmentProperty.vue`（或其披露 Tab）SHALL 接入 `useDisclosureAutoSync`，watch **构建载荷所用的实际数据**（非提示横幅可见性、非 `scheduleAutoSync` 自调度）。
2. THE 披露 Tab SHALL 由宿主传入 `:project-id`（缺失会让同步永久静默失败）。
3. THE §五、21 SHALL 覆盖源模板 (4)「房地产转换情况及改变计量模式的情况」定性披露段（含转换为公允价值计量的说明、房地产开发企业出租开发产品披露），并在底稿提供文本域 + AI 辅助 + 复核触发器。
4. THE `_note_texts` 每条 SHALL 带中文 `title`（缺 title 会让附注正文渲染成英文 section 键），空文本过滤。

### Requirement 6: columns / guidance 补齐与守卫

**User Story:** 作为新建项目的审计助理，我希望首次生成的 H3 附注即带正确列元数据与编制提示。

#### Acceptance Criteria

1. THE 两版共 6 表 SHALL 具有 `columns`，`columns[0].label == headers[0]`、首列标 `is_label`；单行表头表显式 `flat`。
2. THE 每表 SHALL 具有非空 `guidance`（取源模板红字 / 15 号文 / 证监会年报会计监管报告提示 / 「勾稽：」，不自造披露口径）。
3. THE 后端守卫 SHALL 校验两版结构（表数/表名/两级/flat/columns/guidance/无 header_label/无重名），并用 openpyxl 直读源 xlsx tab 名与关键两级表头交叉比对，含反向自检。
4. THE 前端契约守卫 SHALL 复用 `_disclosureSubtableContract.helper`（P1~P6）+ H3 专属（章节号、两级分组、行形态规范、无 `八、22`）。
5. THE CI SHALL 挂载 `note-h3-structure` job 跑 `--check` + 两侧守卫。

### Requirement 7: 零回归与实测

**User Story:** 作为维护者，我希望 H3 重建不破坏既有勾稽与取数，并经实测确认。

#### Acceptance Criteria

1. THE 改动 SHALL 不修改 `_h3_investment_property.py` 四表取数逻辑与 `h3TransferReconcile` / `h3MortgageReconcile` 勾稽语义。
2. THE 附注模板 JSON SHALL 保持可解析，§五、21 / §八、21 之外章节不变。
3. THE H3 既有前后端测试 SHALL 保持通过。
4. THE 两变体 SHALL 经浏览器 + 只读 DB 实测：Tab 正确挂载、推送后两级表头与表名正确落库、无孤儿表、`last_sync_at` 前移；测试数据复原。
