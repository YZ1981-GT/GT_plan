# Requirements Document

## Introduction

G7 长期股权投资是 G 循环体量最大的底稿（源模板 22 个 sheet，两个披露 sheet 分别 243 / 355 行）。
本 spec 收口三件事，范围**只限 G7**（G1~G6 / G8~G14 后续各自另立）：

1. **四表库 → 底稿的取数链路补全**：`report_config` 报表行映射 → `account_mapping` 反解 →
   `tb_balance` 叶子聚合 → G7-1 审定表未审数预填 / G7-2 明细 / 披露表主表变动列，
   并同步修订该底稿页的公式预设（公式管理）。
2. **两个披露表（上市 / 国企）的结构与内容对齐源模板**，梳理披露逻辑后优化改进。
3. **附注模块对应章节的同步修订**（TAB 页签 + 表格结构 + 下方文本框），
   并让「披露表 → 刷新推送 → 附注」全链有数；动态插行区域必须识别出来，附注优先用动态行。

### 关键事实（已实证，作为需求的前提）

**科目映射链路**（postgres 只读实证）

| 环节 | 实证结果 |
|------|---------|
| `report_config` | `BS-024 长期股权投资 = TB('1511','期末余额')`，**四准则一致**；`IMP-009 八、长期股权投资减值准备 = TB('1512','期末余额')`（仅 `soe_standalone` 有公式，`soe_consolidated` 为 NULL） |
| `account_mapping` | 9 个项目一律 `1511.*` → 标准码 `1511`；`1512` → `1512`（`auto_exact`） |
| `tb_balance` 客户科目树 | `1511`（父）/ `1511.01 对子公司的投资` / `1511.02 联营企业投资成本` / `1511.03 损益调整` / `1511.04 其他权益变动` → `.04.01 属于其他综合收益` / `.04.02 不属于其他综合收益` / `1512 长期股权投资减值准备`（`closing_direction='credit'`，**负值存储**） |
| 叶子勾稽（项目 `2aa00f57`） | `1511.01` 期初 53,218,583.61 + `1511.03` 期初 −12,759,523.01 = 40,459,060.60 = 父科目 `1511` 期初 ✓ |
| 减值（项目 `2aa00f57`） | `1512` 期初 −2,840,032.97 / 贷 1,950,000.00 / 期末 **−4,790,032.97** |

**这套子科目天然对应披露主表的变动列**（与 F1 的 `1123` 叶子对应五性质桶同构）：
`.01/.02` → 分类（对子公司 / 对联营）；`.03` → 「权益法下确认的投资损益」；
`.04.01` → 「其他综合收益调整」；`.04.02` → 「其他权益变动」；`1512` → 减值准备期初/期末 + 「计提减值准备」。

**附注章节归属**（`note_template_variant_matrix.json` + 模板 JSON 实证）

| 源模板区段 | 上市附注落点 | 国企附注落点 |
|-----------|-------------|-------------|
| 长期股权投资变动表（上市 R5:R24 / 国企 R200:R222） | `五、18 长期股权投资`（章 `五、合并财务报表项目注释`） | `八、18 长期股权投资`（章 `八、财务报表主要项目注释`） |
| 在子公司中的权益 / 合营联营权益 / 共同经营（上市 R26:R243） | `七、1 在其他主体中的权益`（章 `七、在其他主体中的权益`） | — |
| 企业合并及合并财务报表（国企 R6:R199） | — | 章 `七、合并范围的变化` 下 15 个 level-2 节 |
| 重要合营/联营财务信息、超额亏损、未纳入合并结构化主体（国企 R225:R355） | （在 `七、1` 内） | `八、18` 内 |

> 用户提问中的「报表主要项目中的 N1」按上表理解为**上市 `五、18` + 国企 `八、18`**
> （`八` 的章名逐字为「财务报表主要项目注释」）；「N1」为上一会话遗留笔误，本 spec 按 G7 处理。
> 跨章落点（上市 `七、1` / 国企 `七、*`）因源模板同一 sheet 内混排，必须一并处理，否则表会落错章。

## Requirements

### Requirement 1: 四表取数走报表映射单一真源

**User Story:** 作为审计助理，我希望四表入库后 G7 底稿能按报表科目映射规则自动取到正确的数，
而不是依赖某个项目的科目编码巧合。

#### Acceptance Criteria

1.1 WHEN render 解析 G7 取数科目 THEN 系统 SHALL 通过 `four_table/report_line_accounts.resolve_report_line_accounts` 解析报表行 `BS-024`（原值）与 `IMP-009`（备抵），并传入项目 `applicable_standards`；解析不到时回退 `('1511',)` / `('1512',)`。
1.2 WHEN 标准码反解为客户原始码 THEN 系统 SHALL 经 `account_mapping` 反解，禁止把标准码直接当 `tb_balance.account_code` 前缀用。
1.3 WHEN 聚合金额 THEN 系统 SHALL 使用共享件 `four_table/leaf_aggregation` 的 `select_leaves` / `filter_by_prefixes` / `aggregate_leaves`，删除本文件自造的 `_is_leaf` 与 `_sum_leaf_by_prefix`（两者的前缀判定缺点号边界，`1511` 会误命中 `15110` 这类不同科目）。
1.4 WHEN 聚合备抵科目 `1512` THEN 系统 SHALL 以 `absolute=True` 对**聚合结果**取绝对值（活体为负值存储），使前端「减值准备」列与审定表「二、减值准备」段的正数口径一致。
1.5 WHEN 叶子分类归桶 THEN 系统 SHALL **按科目名称优先**归类（`对子公司`/`子公司`→subsidiary，`合营`→jv，`联营`→associate，`损益调整`→equity_profit，`其他综合收益`→oci，`其他权益变动`→other_equity），科目编码仅作兜底；禁止像现状那样把 `1511.01`/`1511.04.01` 等客户编码写死（平台已实证同类编码在客户间语义冲突）。
1.6 WHEN render 输出溯源 THEN `project_context.tb_source_codes` SHALL 含 `report_row` / `provision_report_row` / `gross_standard` / `provision_standard` / `gross`（叶子码）/ `provision`（叶子码）/ `provision_exact`，供前端溯源面板消费。
1.7 IF 取数任一步失败 THEN 系统 SHALL fail-open（warning + 空值），不阻断 render。
1.8 WHEN 自检不变量 THEN 叶子聚合结果 SHALL 满足「叶子和 == 父科目 `1511` 行金额」，并在 `tb_source_codes` 暴露两口径差异供审计追溯。

### Requirement 2: G7-1 审定表未审数四表预填

**User Story:** 作为审计助理，我希望打开 G7-1 审定表时未审数已按四表库子科目预填好，而不是从零手填。

#### Acceptance Criteria

2.1 WHEN render THEN 系统 SHALL 输出 `adjudication_prefill`，形如 `{gross: {subsidiary,jv,associate,other}, impairment: {...}}`，每项含 `opening/increase/decrease/closing`。
2.2 WHEN 某分类无可识别叶子科目 THEN 系统 SHALL **不 seed 该行**（宁缺勿造），不塞 0 占位。
2.3 WHEN 叶子科目按名称无法归入子公司/合营/联营任一类（如 `损益调整`、`其他权益变动`）THEN 系统 SHALL 归入源模板每块**第 4 行空白可扩行**（源 `A11:B11` / `A16:B16` 等合并空单元格即为该占位），并在行名标注来源科目名，禁止机械摊入前三类。
2.4 WHEN 减值准备段预填 THEN 系统 SHALL 取 `1512` 叶子聚合（abs 归一），无子科目时只填合计层、分类行留空。
2.5 WHEN 前端 G7-1 审定表 THEN SHALL 提供「从四表库带入未审数」按钮，仅覆盖四表命中的格子；已有手工/持久化值时弹确认，可选「仅补空值」。
2.6 WHEN 审定表顶部 THEN SHALL 挂 `WpFourTableSourcePanel` 溯源面板（复用平台共用件，传 `provisionLabel='长期股权投资减值准备'`）。

### Requirement 3: 披露表可从四表库刷新取数

**User Story:** 作为审计助理，我希望四表入库后点一下就能把披露主表的变动列带出来。

#### Acceptance Criteria

3.1 WHEN 披露表工具栏 THEN SHALL 在「从源表取数」旁增设「从四表库带入」，取数范围 = 主表（上市 `investment-movement` / 国企 `lte-movement`、`lte-classification`）的 期初余额 / 期末余额 / 权益法下确认的投资损益 / 其他综合收益调整 / 其他权益变动 / 减值准备期初·期末 各列。
3.2 WHEN 四表带入 THEN 系统 SHALL 手工优先（已有非空值不覆盖，除用户显式选择覆盖），并在行 `source` 标注 `四表库 tb_balance 1511.xx`。
3.3 IF 灰度开关关闭 THEN 该按钮 SHALL 显示为禁用并提示原因，不静默无反应。

### Requirement 4: 公式预设修订

**User Story:** 作为审计助理，我希望在底稿当页的公式管理里看到与本科目口径一致的公式预设。

#### Acceptance Criteria

4.1 WHEN G7-1 块 THEN SHALL 补 `TB('1512','期初余额')` / `TB('1512','期末余额')` 两条（审定表有减值准备段，且 `writebackTB` 会写 1512），并补 `WP('G7','明细表G7-2',…)` 联动（审定表可用 `WP`）。
4.2 WHEN G7-2 明细表块 THEN SHALL 删除 5 条硬编码具体客户编码的 `AUX('1511.01','客户','007960',…)` 式公式（属某一项目的实测污染，对其它项目无意义），并补 `1511.04.01` / `1511.04.02` / `1512` 子科目条目。
4.3 WHEN 明细表块 THEN SHALL **不含 `WP()`**（防循环，与平台 `test_h1_two_level_chain` 守卫一致）。
4.4 WHEN 预设 `sheet` 字段 THEN SHALL 与源 xlsx tab 名逐字一致；同时修正 render 下发的 `sheetName`（现为 `审定表G7-1`，源 xlsx 为 `长期股权投资审定表G7-1`），保留旧名兼容分发。
4.5 WHEN 守卫 THEN SHALL 断言 G7 预设中不出现具体客户/供应商编码字面量，且每条 `cell_ref` 在本 `page_key` 内唯一。

### Requirement 5: 披露表结构对齐源模板

**User Story:** 作为现场经理，我希望披露表的列结构、行集、分组与源模板逐字一致，交付物不缩水。

#### Acceptance Criteria

5.1 WHEN 主表列头 THEN SHALL 声明两级表头：`本期增减变动` 作为 8 个子列（追加/新增投资、减少投资、权益法下确认的投资损益、其他综合收益调整、其他权益变动、宣告发放现金股利或利润、计提减值准备、其他）的父分组；其余列 rowspan=2 不给 group（混合分组）。
5.2 WHEN 基本情况类表的 `持股比例%` THEN SHALL 声明 `直接` / `间接` 两子列的父分组（上市 `E28:F28`、`E111:F112`、`E235:F236`）。
5.3 WHEN 非全资子公司主要财务信息 THEN SHALL 保留源模板的 `期末数` / `期初数` / `本期发生额` / `上期发生额` 父分组，不压扁为「本期营业收入」式组合列名。
5.4 WHEN 上市「重要联营企业主要财务信息」行集 THEN SHALL 为源模板 R171:R187 的 **17 行**；现模型多出「其中：现金和现金等价物」（该行只在合营表 R135 存在）→ 必须删除。
5.5 WHEN 上市主表行集 THEN SHALL 含源模板的 `①合营企业` / `②联营企业` 分组标签行 + 各自 `小  计` + `合  计`；行型判定 SHALL 先去空白（源模板字面带空格）。
5.6 WHEN 国企联营 FS 表末两行 THEN SHALL 采用附注模板已修正的「对联营企业权益投资的账面价值」（源模板 R268 字面为「对合营企业…」，属源模板笔误，此判断须在代码注释与守卫中留证）。
5.7 WHEN 金额录入控件 THEN SHALL 全部使用 `WpAmountInput`，`el-input-number` 残留 SHALL 为 0；比例/持股比例列不得套用。
5.8 WHEN 只读金额展示 THEN SHALL 走 `displayPrefs.fmtAmount()`，删除自造 `toLocaleString('zh-CN')`。
5.9 WHEN 披露表 THEN SHALL 提供勾稽面板，规则只取源模板可判定的勾稽（分类表 `小计 − 减值准备 = 合计`、主表 `期初 + 增 − 减 = 期末`、主表期末合计 ↔ G7-1 审定数、分类表 ↔ 主表合计）。

### Requirement 6: 附注模板结构修订

**User Story:** 作为审计助理，我希望附注模块的 TAB 页签、表格结构和下方文本框与源模板一致，推送后能正确落位。

#### Acceptance Criteria

6.1 WHEN 上市 `五、18` THEN 幂等脚本 SHALL 把主表 `headers` 由 5 列还原为源模板 13 列（两级 `group`）、补 `columns` / `guidance`、删 `row_type: header_label` 假行、按源模板补 `text_sections`（现仅 2 段裸标题）。
6.2 WHEN 上市 `七、1 在其他主体中的权益` THEN 脚本 SHALL 把现状（`tables=0` / `text_sections=187`）重建为源模板 R26:R243 的表集 + 文本段，使 14 张表有落点。
6.3 WHEN 国企 `八、18` THEN 脚本 SHALL：分类表补源模板 R203「对子公司投资」行；两张**同名** `续：` 表正名（`sub_table_data` 以表名为键，同名会互相覆盖丢整张表）；表[8]/[9] 的段落文本泄漏名正名；10 张表补 `columns`(含两级 `group`)/`guidance`。
6.4 WHEN 国企 `七、*` 15 个节 THEN 脚本 SHALL 把表头首格泄漏的表名（`序号`/`公司名称`/`项  目`）正名为可读表名、补 `columns` / `guidance`。
6.5 WHEN 模板 `headers` / `columns[].label` / `rows[].label` THEN SHALL 为纯文本，剥离 `<br/>` 等 HTML。
6.6 WHEN 源模板单行表头的表 THEN `columns` SHALL 标 `flat`（否则前缀推断会造出凭空父表头）；**`flat` / `group` 必须在模板 seed 与同步载荷两处都表态**。
6.7 WHEN 脚本 THEN SHALL 幂等（`--dry-run` / `--check` / `--apply`）并写 `_aligned_by` 标记；禁止手改 JSON。

### Requirement 7: 动态插行区域

**User Story:** 作为审计助理，我希望被投资单位这类不定行数的区域在底稿和附注里都能自由增删行。

#### Acceptance Criteria

7.1 WHEN 识别动态区 THEN SHALL 以源模板的 `…` / `……` / 空白可扩行 / 「可无限量添加行」为依据，逐表登记为 `dynamic`。
7.2 WHEN `…` / `……` 出现在**列头** THEN SHALL 展开为实际类别或丢弃（永远收不到数据）；出现在**行**且属纯占位 THEN SHALL 从附注 seed 删除，语义移入 `guidance`；出现在行且**参与小计/是真实可扩明细行** THEN SHALL 保留（H7/H8 已两次实证语义相反）。
7.3 WHEN 附注渲染 THEN 行数 SHALL 由底稿推送的实际行数决定（`_source=workpaper` 下投影器只渲染推送内容，不与模板 `_tables` 合并）。
7.4 WHEN 底稿删除某动态表的全部行 THEN SHALL 通过 `_removed_table_keys` 清理附注侧该表，避免残留过时明细；仅对**本底稿推过**的表名生效（与 `previouslySyncedTables` 求交集）。

### Requirement 8: 披露 → 附注推送落点正确

**User Story:** 作为审计助理，我点「同步到附注」后，希望每张表都落到它该去的章节，而不是全部堆在长期股权投资节里。

#### Acceptance Criteria

8.1 WHEN 上市侧推送 THEN SHALL 改为**多章节 payload**（对齐国企侧已有的 `buildG7SoeSyncPayloads` + `sync-batch-from-workpaper`）：主表与减值说明 → `五、18`；子公司权益 / 合营联营 / 共同经营 → `七、1`。现状把 15 张表全推 `五、18`，其中 14 张在该章节是孤儿表。
8.2 WHEN 载荷表名 THEN SHALL 与目标章节 `note_template_*.json` 的 `tables[].name` 逐字一致。
8.3 WHEN 载荷 `_note_texts` THEN SHALL 放在 `sub_table_data` 内（`_` 前缀元数据键），且每条带中文 `title`，空文本过滤。
8.4 WHEN 新建 `g7NoteSectionMap.ts` THEN SHALL 满足 `note_workpaper_sync_registry` 生成器的硬约束（文件名匹配 `^([a-z]+\d+)NoteSectionMap\.ts$`、章节号为内联字符串字面量、对象体内不写注释、`X_DISCLOSURE_SHEET_NAME` 写成单个对象），并重生成 registry（G7 现完全不在 registry 中，附注侧「打开同步底稿」反查不到）。
8.5 WHEN 披露 sheet 名 THEN SHALL 与源 xlsx tab 名逐字一致（`附注披露信息（上市公司）` / `附注披露信息（国企）`，全角括号），守卫用 openpyxl 直读比对。

### Requirement 9: 灰度开关与可用性

**User Story:** 作为项目负责人，我需要知道四表取数在本环境到底是开还是关。

#### Acceptance Criteria

9.1 WHEN 现状 THEN `G7_FOUR_TABLE_EXTRACTION_ENABLED` 默认为 `False` → `tb_leaf_categories` 与「从四表取数」端点运行态全部返回空。本 spec SHALL 在实现完成后向用户确认「本环境 opt-in 还是翻默认」，并把裁决结果写入 tasks.md。
9.2 WHEN 开关关闭 THEN 已实现的取数路径 SHALL 不产生任何写库副作用，且 UI 明示「未启用」而非静默空白。
9.3 WHEN 开关打开 THEN `_fetch_tb_values`（现未受开关约束）与 `adjudication_prefill` / `tb_leaf_categories` SHALL 口径一致，不出现两套数。

### Requirement 10: 测试与实测

**User Story:** 作为质量控制复核合伙人，我要求每项改动都有守卫兜底，且关键数字经真实数据实测，任务标记不能假绿。

#### Acceptance Criteria

10.1 WHEN 后端守卫 THEN SHALL 含 `test_g7_account_scope.py`（报表行解析 / 点号边界 / abs 归一 / 名称优先分类 / fail-open / 反向自检「旧口径确实会误命中」）与 `test_note_g7_structure.py`（openpyxl 直读源 xlsx ↔ 模板 headers ↔ 同步 columns 三向比对 + 反向自检）。
10.2 WHEN 前端守卫 THEN SHALL 含 `g7NoteSubtableContract.spec.ts`（复用共享 helper 的 P1~P6）+ `g7FourTableWiring.spec.ts`（溯源面板接线 / 按钮存在 / `el-input-number` 归零 / `fmtAmount` 走 store）。
10.3 WHEN 实测 THEN SHALL 用真实项目跑 render（`2aa00f57` 有 1511/1512 活体数据）验证叶子和 == 父额、备抵为正数；并用浏览器实测披露表两版渲染 + 推送后 postgres 只读复核落库表数/列元数据/`_column_groups`/`_last_sync_sheet`，实测数据用后复原。
10.4 WHEN CI THEN SHALL 新增 job `g7-four-table-extraction` 与 `note-g7-structure`。

### Requirement 11: 禁硬编码（单一真源 + 守卫锁死）

**User Story:** 作为平台维护者，我要求 G7 的科目、分类、章节号、表名、列头、行数都来自单一真源，
不许在多处写死字面量 —— 否则换一个客户、换一版模板就静默算错。

#### Acceptance Criteria

11.1 WHEN 前端需要科目码 THEN SHALL 收敛到新建的单一真源 `composables/g7AccountScope.ts`
（对齐平台已验证的 `k2AccountScope.ts` 范式）：`G7_REPORT_ROW_CODE='BS-024'` /
`G7_PROVISION_REPORT_ROW_CODE='IMP-009'` / `G7_GROSS_FALLBACK_STANDARD` /
`G7_PROVISION_FALLBACK_STANDARD` / `g7GrossQueryCodes(src)` / `g7AccountCode(src)`；
**运行态一律取 render 下发的 `tb_source_codes`**，常量只作兜底与展示。
现存散落字面量 SHALL 清零：`GtG7LongTermEquityMain.vue` 的 `G7_ACCOUNT_CODE='1511'` /
`G7_IMPAIRMENT_CODE='1512'`、两个披露 Tab 各自的 `ACCOUNT_CODE='1511'`。

11.2 WHEN 后端 render 输出 `project_context.account_code` / `account_code` THEN SHALL 为
**报表行解析结果**，而非常量 `_G7_ACCOUNT_PREFIX`。

11.3 WHEN 定义分类桶 THEN SHALL 建**一份**声明式真源 `G7_INVESTMENT_BUCKETS`
（每项含 `bucket` / 源模板 label / `name_keywords` / `code_fallback` / `priority` /
`is_movement_nature`），由后端分类器、`adjudication_prefill` 行标签、前端 seed **共同读取**；
禁止像现状那样把 `1511.01`→cost 这类映射写死在渲染策略里，也禁止把同一批中文标签
在后端与前端各抄一份。守卫 SHALL 用 openpyxl 直读源 xlsx 交叉比对这些 label。

11.4 WHEN 声明附注章节号 THEN 字面量 SHALL 仅因 registry 生成器约束保留在
`g7NoteSectionMap.ts`，且守卫 SHALL 与 `note_template_variant_matrix.json` 交叉锁死；
国企 15 个 `noteSectionId`（md 截断值如 `七、本期纳入合并报表`）SHALL 逐条与
`note_template_soe.json` 的 `section_number` 比对，禁自拟。

11.5 WHEN 声明表名 / 列 label / 行集 THEN 真源分别为 `note_template_*.json` 的
`tables[].name` 与源 xlsx 单元格文本；契约测试 SHALL 双向锁死（模板→载荷、载荷→模板），
禁在代码里自拟或"顺手改顺眼"。

11.6 WHEN 表的列数取决于被投资单位/子公司数量 THEN SHALL 改为**动态列**（沿用 H7 已验证的
稳定 key `{slot}_{seq}` + 可增删改名），不得按「公司1..公司N」写死。现存写死项：
上市 `companyColumns`(6)、`associateMatrixColumns`(3)；国企
`multiCompanyCurrentPriorColumns`(5)、`soldFsPositionColumns`(2)、`soldFsResultColumns`(5)、
`ownershipChangeImpactColumns`(3)、`associateFsMatrixColumns`(3)、`associatePlMatrixColumns`(3)。

11.7 WHEN 生成动态区骨架行 THEN 行数 SHALL 不写死（现状 `blankRows(prefix, 3|5|10, …)`）——
由四表库 / G7-2 明细表的实际行数 seed，用户可自由增删；无数据时给 1 行空行即可，
不预置 3~10 行空占位（否则未填行会被推成占位披露行）。

11.8 WHEN 出现容差 / 灰度开关名 / sheet 名 / 响应键名 THEN SHALL 引用集中常量，
不得字面量散落多处；守卫 SHALL 扫源码计数。

11.9 WHEN 幂等脚本声明变更 THEN 表名 / 列名 / guidance 文本 SHALL 从源 xlsx 读取或集中在
脚本顶部的声明式 `RULES` 表，禁散落在各函数体内。

## Glossary

| 术语 | 含义 |
|------|------|
| G7 | 长期股权投资底稿（22 sheet：G7A 程序表 / G7-1 审定表 / G7-2 明细表 / G7-3 调整分录 / 两个披露 sheet / G7-4~G7-18 专项测试表 / 底稿目录） |
| BS-024 | 报表行「长期股权投资」，四准则一律 `TB('1511','期末余额')` |
| IMP-009 | 报表行「八、长期股权投资减值准备」，`soe_standalone` 为 `TB('1512','期末余额')`，`soe_consolidated` 公式为 NULL |
| 原值 / 备抵 | 原值 = `1511` 长期股权投资；备抵 = `1512` 长期股权投资减值准备 |
| 叶子科目 | `tb_balance` 中不存在以「本码 + `.`」开头的同数据集兄弟行的最明细行；其金额之和等于父科目行金额 |
| 变动性质桶 | `1511.03 损益调整` / `1511.04.01 其他综合收益` / `1511.04.02 其他权益变动` —— 描述**变动原因**而非**被投资单位类别**，不可摊入子公司/合营/联营 |
| 五、18 / 八、18 | 附注「长期股权投资」节（上市在章「五、合并财务报表项目注释」，国企在章「八、财务报表主要项目注释」） |
| 七、1 | 上市附注章「七、在其他主体中的权益」下唯一 level-2 节，现状 `tables=0` / `text_sections=187` |
| 七、* | 国企附注章「七、合并范围的变化」下 15 个 level-2 节 |
| 动态插行区 | 源模板中以 `…` / `……` / 空白可扩行 / 「可无限量添加行」标记的不定行数区域 |
| 孤儿子表 | 同步载荷推送了目标章节模板中不存在的表名 → 附注渲染出不属于该章节的表 |
