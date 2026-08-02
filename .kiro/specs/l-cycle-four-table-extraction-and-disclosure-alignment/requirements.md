# Requirements Document

## Introduction

L 类（债务循环）共 8 个业务循环 —— L1 短期借款 / L2 应付利息 / L3 长期借款 / L4 应付债券 / L5 长期应付款 / L6 专项应付款 / L7 其他非流动负债 / L8 财务费用。本 spec 收口三件事：①四表库入库后的科目映射与取数链路；②底稿当页公式预设；③两个披露表（上市/国企）与附注模块对应章节的结构与内容对齐，并打通「披露表推送 → 附注有数据」。

本 spec 立项前已完成只读实证（`report_config` / `account_chart` / `tb_balance` / `note_template_variant_matrix.json` / 源 xlsx / 前后端源码），结论如下。

### 已实证的科目映射真源（report_config，四准则一致除注明）

| 循环 | 报表行（listed / soe） | formula | account_chart 实证 |
| --- | --- | --- | --- |
| L1 短期借款 | BS-044 / BS-055 | `TB('2001','期末余额')` | 2001 短期借款 |
| L2 应付利息 | BS-054「其中：应付利息」**仅 listed，formula=None** | — | 2231 应付利息 |
| L3 长期借款 | BS-061 / BS-085 | `TB('2501','期末余额')` | 2501 长期借款 |
| L4 应付债券 | BS-062 / BS-086 | `TB('2502','期末余额')` | 2502 应付债券 |
| L5 长期应付款 | BS-066 / BS-092 | `TB('2701','期末余额')` | 2701 长期应付款 |
| L6 专项应付款 | **report_config 无该行** | — | **2711 专项应付款** |
| L7 其他非流动负债 | BS-071 / BS-097 | `TB('2901','期末余额')` **与 BS-070/BS-096 递延所得税负债撞码** | 2901 = 递延所得税负债 |
| L8 财务费用 | IS-007 / IS-025 | `TB('6603','本期发生额')` | 6603 财务费用 |
| 一年内到期的非流动负债 | BS-057 / BS-080 | `TB('2502','期末余额')` **与应付债券撞码** | 无专属科目（重分类行） |

### 已实证的客户子科目 → 披露分项天然对应

- `2231.01` 分期付息到期还本的长期借款利息 / `.02` 企业债券利息 / `.03` 短期借款应付利息 / `.04` 应收账款出表利息 → 附注「应付利息」表分项行
- `2501.01` 长期借款 / `2501.02` 一年内到期的长期借款 → 长期借款主表 + 「一年内到期的长期借款」子表
- `2502.01` 面值 / `.02` 利息调整 / `.03` 应计利息 → 「应付债券（续）」变动列
- `2701.01` 应付融资租赁款 / `.02` 应付长期保证金 / `.03` 应付长期借款 / `.99` 一年内到期的长期应付款 → 「长期应付款（按款项性质列示）」+ 「一年内到期的长期应付款」
- `6603.01.01~.19` 利息支出各类 / `.02.01~.12` 利息收入各类 / `.03` 手续费支出 / `.04` 汇兑损益 / `.05` 现金折扣支出 / `.06` 担保费 / `.07.01~.03` 金融工具转移 / `.15` 现金折扣收取 → 财务费用「按费用性质列示」12 行

### 已实证的附注章节图谱（note_template_variant_matrix.json）

| 科目 | listed | soe |
| --- | --- | --- |
| 短期借款 | 五、33 | 八、33 |
| 一年内到期的非流动负债（父章） | 五、43 | 八、44 |
| （1）一年内到期的长期借款 | **None**（并入 五、43） | 八、45 |
| （2）一年内到期的应付债券 | **None** | 八、46 |
| （3）一年内到期的长期应付款 | **None** | 八、47 |
| 长期借款 | 五、45 | 八、49 |
| 应付债券 | 五、46 | 八、50 |
| 长期应付款 | 五、48 | 八、53 |
| 其他非流动负债 | 五、52 | 八、57 |
| 财务费用 | 五、67 | 八、68 |
| 应付利息（L2） | 无独立章节 → K3 五、42 | 无独立章节 → K3 八、42 |
| 专项应付款（L6） | 无独立章节 → L5 五、48 子表 | 无独立章节 → L5 八、53 子表 |

## Glossary

| 术语 | 含义 |
| --- | --- |
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张导入表 |
| 报表行解析 | 由 `report_config.formula` 按准则解析出标准科目码的过程 |
| 反解 | 标准码经 `account_mapping` 还原为客户原始科目码前缀 |
| 叶子科目 | `tb_balance` 中不存在 `code + '.'` 子行的科目 |
| 一年内到期部分 | 长期科目中将于一年内到期、需重分类至流动负债的金额 |
| 兜底码 | 报表行解析落空时使用的科目码，标记 `resolved_from='fallback'` |
| 宁缺勿造 | 无法干净映射时不预填，而非机械摊派 |
| 两级表头 | `ColumnDef.group` 声明的父表头 + 叶子列名，投影为 `_column_groups` |
| flat 表态 | 单级表头的显式声明，阻止后端前缀推断凭空造父表头 |
| 孤儿子表 | 载荷表名与附注模板 `tables[].name` 不一致导致附注永空的表 |
| 自调度 | `scheduleAutoSync` 写在同步函数内造成周期重复 POST 的错误接线 |
| 三向比对 | 源 xlsx ↔ 附注模板 `headers` ↔ 载荷 `columns` 一致性校验 |

## Requirements

### Requirement 1: L 类取数改走四表共享件与报表行解析

**User Story:** 作为审计助理，我希望四表入库后 L 类底稿的未审数自动出现且科目正确，这样我不必手工录入也不必担心取错科目。

#### Acceptance Criteria

1. WHEN L1~L8 render 执行取数 THEN 系统 SHALL 通过 `four_table.report_line_accounts.resolve_report_line_account_codes` 按 `applicable_standards` 解析科目码，而非硬编码字面量
2. WHEN 报表行公式解析落空 THEN 系统 SHALL 回退到本 spec 声明的兜底码，并在 `tb_source_codes.resolved_from` 标记 `fallback`
3. WHEN 叶子聚合执行 THEN 系统 SHALL 委托 `four_table.leaf_aggregation.select_leaves`，且叶子判定 SHALL 带点号边界
4. WHEN 任一循环完成取数 THEN 系统 SHALL 在 `html_data` 输出 `tb_source_codes`，且该输出 SHALL 有前端消费方
5. WHEN 叶子聚合完成 THEN 叶子金额之和 SHALL 等于父科目行金额

### Requirement 2: 修正 L6 / L7 / L8 三处取数缺陷

**User Story:** 作为现场经理，我需要底稿显示的金额是该科目真实的金额，而不是别的科目的钱或恒零。

#### Acceptance Criteria

1. WHEN L6 专项应付款取数 THEN 系统 SHALL 使用 `2711`，而非现行 `2601`（`2601` 实为租赁负债，`tb_balance` 该前缀 0 行）
2. WHEN L7 其他非流动负债取数 THEN 系统 SHALL NOT 使用 `2901`（递延所得税负债，已被 BS-070/BS-096 占用），且 SHALL NOT 使用 `2801`（预计负债）
3. IF L7 在客户科目表中无可干净映射的科目 THEN 系统 SHALL 不预填（宁缺勿造）并在 `tb_source_codes` 记录依据
4. WHEN L8 财务费用取数 THEN 系统 SHALL 取 `trial_balance` 本期发生额口径，兜底 `tb_balance.debit_amount`，且 SHALL NOT 使用 `debit - credit`
5. WHEN L8 取数完成 THEN 结果 SHALL NOT 恒为 0（现行 `6603` 及全部子科目 `debit == credit`）

### Requirement 3: 一年内到期的非流动负债重分类取数

**User Story:** 作为审计助理，我需要「减一年内到期」列有数据，这样长期借款/应付债券/长期应付款的审定表与披露表才能勾稽。

#### Acceptance Criteria

1. WHEN 系统取「一年内到期」金额 THEN 系统 SHALL NOT 使用 `BS-057/BS-080` 的 `TB('2502')`（与应付债券撞码）
2. WHEN L3 取一年内到期金额 THEN 系统 SHALL 从 `2501` 子科目中按名称识别「一年内到期」叶子
3. WHEN L5 取一年内到期金额 THEN 系统 SHALL 从 `2701` 子科目中按名称识别「一年内到期」叶子
4. WHEN 名称识别执行 THEN 判定 SHALL 使用单一真源分类器且带否决词，SHALL NOT 按子科目编码写死
5. WHEN 长期科目拆分完成 THEN 「非流动部分 + 一年内到期部分」SHALL 等于该科目叶子合计

### Requirement 4: 审定表未审数四表预填与溯源

**User Story:** 作为审计助理，我希望点一个按钮就把四表库的未审数带进审定表，并能看到这笔数来自哪个科目。

#### Acceptance Criteria

1. WHEN L1~L8 render 执行 THEN 系统 SHALL 输出 `adjudication_prefill`，按叶子科目名归入审定表分类行
2. WHEN 审定表已有持久化值 THEN 系统 SHALL NOT 覆盖（手工优先）
3. WHEN 用户点击「从四表库带入未审数」THEN 系统 SHALL 只覆盖四表命中的行，并对「四表无数据且无手工值」的行显式写 0
4. WHEN 审定表渲染 THEN 系统 SHALL 展示四表取数溯源面板，复用 `WpFourTableSourcePanel`
5. WHEN 无可映射科目 THEN 系统 SHALL 不预填并保持既有行为逐字等价

### Requirement 5: 公式预设纠错与补齐

**User Story:** 作为审计助理，我在公式管理页需要看到本循环真实可用的取数公式，而不是别的循环的科目。

#### Acceptance Criteria

1. WHEN 读取 L2/L4/L5/L6/L7 公式预设 THEN `wp_name` 与 `account_codes` SHALL 与该 wp_code 的真实科目一致（现行整块错位一位）
2. WHEN 预设声明科目码 THEN 该码 SHALL 存在于标准科目表，且 SHALL 属于本循环报表行引用的科目集合
3. WHEN L1~L8 公式预设加载 THEN 每个循环的条目数 SHALL 大于 0（现行全部为 0）
4. WHEN 审定表块声明公式 THEN 系统 MAY 使用 `WP()` 引用本循环明细表
5. WHEN 明细表块声明公式 THEN 系统 SHALL NOT 使用 `WP()` 引用本循环审定表（防成环）
6. WHEN 预设声明 sheet 名 THEN 该名 SHALL 与源 xlsx tab 名逐字一致

### Requirement 6: 披露表结构对齐源模板

**User Story:** 作为业务合伙人，我需要披露表的列结构与致同源模板一致，否则交付物不可用。

#### Acceptance Criteria

1. WHEN 披露表渲染 THEN 列结构 SHALL 以源 xlsx 为唯一裁决者
2. WHEN 源模板为两级表头 THEN 系统 SHALL 使用 `ColumnDef.group` + 叶子列名，SHALL NOT 压扁为带前缀单级
3. WHEN 源模板为单级表头 THEN 系统 SHALL 在 seed 与推送两处均标 `flat`
4. WHEN 源模板存在动态插行区 THEN 系统 SHALL 提供增删行能力，SHALL NOT 写死行数
5. WHEN 披露表涉及账龄 THEN 系统 SHALL 复用 `disclosureAgingLabels` 单一真源，支持 3 年段 / 5 年段 / 自定义
6. WHEN 披露表金额录入 THEN 系统 SHALL 使用 `WpAmountInput`，SHALL NOT 使用 `el-input-number :formatter`

### Requirement 7: 附注模板结构修订

**User Story:** 作为审计助理，我需要附注章节的表格结构与源模板一致，且 TAB 页签有编制提示。

#### Acceptance Criteria

1. WHEN 修订附注模板 THEN 系统 SHALL 通过幂等脚本执行，支持 `--dry-run` / `--check` / `--apply`
2. WHEN 表名为表头首格泄漏或段落文本泄漏 THEN 系统 SHALL 改为源模板小节名，并通过 aliases 改名而非 drop
3. WHEN 同章节存在同名表 THEN 系统 SHALL 消除重名（表名是 `sub_table_data` 键，同名互相覆盖丢整表）
4. WHEN 表缺 `columns` THEN 系统 SHALL 补齐并显式表态 `flat` 或 `group`
5. WHEN 表缺 `guidance` THEN 系统 SHALL 补齐纯文本编制提示，内容取源模板红字或准则条款，SHALL NOT 含 markdown 粗体
6. WHEN `rows` 含「可无限量添加行」等占位说明或 `header_label` 假行 THEN 系统 SHALL 删除
7. WHEN `text_sections` 含裸表名 THEN 系统 SHALL 加 `#### ` 前缀

### Requirement 8: 披露表推送到附注链路打通

**User Story:** 作为审计助理，我在披露表录完数据点推送，附注模块就应该有数据。

#### Acceptance Criteria

1. WHEN 披露 Tab 数据变更 THEN 系统 SHALL 通过 `useDisclosureAutoSync` 自动同步，且 watch 目标 SHALL 与载荷字段一致
2. WHEN 载荷构建 THEN 子表名 SHALL 与附注模板 `tables[].name` 逐字一致
3. WHEN 载荷含合计行 THEN 合计行字面 SHALL 按本章节实证取值
4. WHEN 底稿改版移除子表 THEN 系统 SHALL 上报 `_removed_table_keys`，且 SHALL 与本次推送键求差集
5. WHEN 国企侧存在多个目标章节 THEN 系统 SHALL 发送多个 payload（定位键不含 standard）
6. WHEN 上市侧无对应章节 THEN 系统 SHALL 不推送并显示「当前不适用」
7. WHEN L6 推送 THEN 系统 SHALL 推 L5 章节的「专项应付款」子表，SHALL NOT 越界重定义 L5 自有表列

### Requirement 9: L4 应付债券披露重建

**User Story:** 作为审计助理，我需要应付债券的增减变动表能推送到附注，现在它是空缺的。

#### Acceptance Criteria

1. WHEN L4 披露 Tab 渲染 THEN 组件数据模型 SHALL 与源模板同构（主表 + 增减变动 + 续表 + 其他金融工具变动）
2. WHEN L4 载荷构建 THEN 系统 SHALL 覆盖上市 5 表 / 国企 2 表
3. WHEN L4 接入同步 THEN `MISSING_SYNC_PATH` 中 L4 两条 SHALL 被移除
4. WHEN 源模板为纯文本小节 THEN 系统 SHALL 落到 `_note_texts` 而非自造表格

### Requirement 10: 灰度开关与运行态可用

**User Story:** 作为现场经理，我需要「四表入库后刷新取数」这句话在当前环境真实成立。

#### Acceptance Criteria

1. WHEN 评估 `LMN_FOUR_TABLE_EXTRACTION_ENABLED` THEN 系统 SHALL 记录其默认值为 False 导致 L 类取数全返 0
2. WHEN 开关关闭 THEN 系统行为 SHALL 与本 spec 改动前逐字节等价
3. WHEN 开关开启 THEN L1~L8 SHALL 返回真实四表数据
4. WHEN 决定默认值 THEN 该决定 SHALL 由用户裁决后执行

### Requirement 11: 守卫与零回归

**User Story:** 作为质量控制复核合伙人，我需要这些修复被测试钉死，不能下次被并发改动悄悄退回。

#### Acceptance Criteria

1. WHEN 校验附注结构 THEN 守卫 SHALL 用 openpyxl 直读源 xlsx 与模板、同步 `columns` 三向比对
2. WHEN 守卫读取源码 THEN 系统 SHALL 先 `stripComments()` 并加反向自检
3. WHEN 校验科目码 THEN 守卫 SHALL 断言码属标准科目表且属本循环报表行科目集合
4. WHEN 既有测试锁定旧错误行为 THEN 系统 SHALL 诚实修改该测试并补一条旧实现必红的用例
5. WHEN 本 spec 完成 THEN CI SHALL 新增对应 job
