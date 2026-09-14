# Requirements Document

## Introduction

N1（递延所得税资产）底稿的四表库取数链路、两张披露表结构、以及附注 `五、30` / `八、31`
两节的行列结构存在系统性欠账。本 spec 以 **源模板 xlsx 为唯一裁决者**
（`backend/wp_templates/N/N1 递延所得税资产.xlsx` 的 `附注披露信息（上市公司）` A1:K54 与
`附注披露信息（国企）` A1:IV74，已逐格 + 合并单元格 + 公式实测），以 **`report_config` DB 表为
科目映射唯一真源**（已只读实证），收口以下五类问题：

1. **四表取数断链**：N1 render 硬编码科目 `1811`，未走 `resolve_report_line_account_codes`
   映射规则；**递延所得税负债 `2901` 完全没有取数**，导致披露表负债段与抵销后净额表在
   四表入库后依然全空。
2. **披露表未接四表直通**：披露表 (1) 资产段只从 N1-2 明细按类别预填，而 N1-2 本身无四表 seed
   → 四表入库后披露表仍无数据。但后端 `adjudication_prefill` 的 7 类与前端
   `N1_ASSET_ITEMS` 7 项**逐字同构**，可直接直通。
3. **附注模板行集是自造的**：`note_template_listed.json` 五、30 表 0 资产段 5 行（含源模板
   不存在的「开办费」）、负债段 5 行有 4 行与源模板不符；`note_template_soe.json` 八、31 同类
   偏离，且残留 5 处 `……` 占位假数据行；亏损到期表 11 年 + `无使用期限` 亦非源模板结构。
4. **报表行编码错误**：附注模板行上 `report_row_code="BS-018"`，而 DB 实证 `BS-018` 在上市是
   「流动资产合计」、在国企是「存货」；正确应为 `BS-036`（递延所得税资产）与 `BS-067`
   （递延所得税负债）。另有 `租赁负债` 行挂 `account_codes:['2601']`、`使用权资产` 行挂
   `['1641','1642','1643']` —— 这些是**底层资产/负债科目**，若被取数会把租赁负债余额拉进
   递延所得税列。
5. **公式预设污染与缺口**：`prefill_formula_mapping.json` 有一个 `wp_code=N1` 却名为
   「税金分析程序」的块（科目 `2221`/`6401`/`6403`，sheet `分析程序N1-3` 在 N1 源模板中不存在，
   且 `TB_SUM('2221~6403')` 是跨越负债/权益/成本/损益的病态区间）；同时 N1-4 测算表、
   N1-5 亏损检查表、两张披露 sheet 均无任何公式预设。

范围限定为 **N1 及其直接依赖**。N3（递延所得税负债，科目 `2901`）本身的底稿改造、
以及 `page_key` 忽略 sheet 导致的 `上年审定数` 平台级撞键（25+ 循环共有），均不在本 spec 内。

## Requirements

### Requirement 1: 四表库科目映射走 report_config 真源

**User Story:** 作为审计助理，我希望 N1 底稿的取数科目由报表行映射规则决定，这样当项目自定义了
报表行公式（如把递延所得税资产映射到额外科目）时，底稿取数能自动跟随，而不是被代码写死。

#### Acceptance Criteria

1. WHEN N1 render 执行取数 THEN 系统 SHALL 通过 `resolve_report_line_account_codes(db, project_id, 'BS-036', fallback=['1811'])` 解析资产侧科目集，而非使用硬编码常量。
2. WHEN N1 render 执行取数 THEN 系统 SHALL 通过 `resolve_report_line_account_codes(db, project_id, 'BS-067', fallback=['2901'])` 解析负债侧科目集。
3. WHEN 映射解析失败或该项目无 `report_config` 记录 THEN 系统 SHALL 回退到 fallback 科目集并继续渲染，不得抛错阻断。
4. WHEN render 返回 html_data THEN 系统 SHALL 输出 `tb_source_codes` 追溯键，形如 `{"asset": {"row_code": "BS-036", "codes": [...]}, "liability": {"row_code": "BS-067", "codes": [...]}}`，供前端展示取数溯源。
5. WHEN `tb_source_codes` 被输出 THEN 前端 SHALL 至少有一个消费点（禁止 dead output）。

### Requirement 2: 递延所得税负债（2901）四表取数

**User Story:** 作为审计助理，我希望四表入库后披露表的递延所得税负债段能自动带出数据，
而不需要我把 N3 底稿的数字手工抄一遍。

#### Acceptance Criteria

1. WHEN N1 render 执行 THEN 系统 SHALL 从 `tb_balance` 按负债侧科目集取科目级余额（无科目级行时取**叶子**子科目聚合，防与父级双算），输出为 `trial_balance_liability`。
2. WHEN N1 render 执行 THEN 系统 SHALL 从 `tb_balance` 负债侧**叶子**子科目按源模板负债段 5 个语义槽聚合，输出为 `liability_prefill`。
3. WHEN 子科目名无法归入前 4 个语义槽 THEN 系统 SHALL 归入 `other` 槽。
4. WHEN 某语义槽期初与期末绝对值均小于 0.005 THEN 系统 SHALL 跳过该槽（不输出全零槽）。
5. WHEN 只存在父级科目而无子科目 THEN 系统 SHALL 返回空 `liability_prefill`（不虚构分类）。
6. WHEN `tb_balance` 查询抛异常 THEN 系统 SHALL 返回空结果并记录 warning，不阻断渲染。
7. WHEN `liability_prefill` 的槽键被消费 THEN 系统 SHALL 使用**语义槽键**（非中文显示名），因为源模板负债段第 4 项两版用语不同（上市「使用权资产」/ 国企「租赁形成」）。

### Requirement 3: 披露表 (1) 四表直通预填

**User Story:** 作为审计助理，我希望四表入库并刷新后，披露表 (1) 的资产段与负债段就有数，
点「推送到附注」附注也就有数，不需要先手工编制 N1-2。

#### Acceptance Criteria

1. WHEN 披露表加载且资产段某行四个值全为空 AND `adjudication_prefill` 含该行同名类别 THEN 系统 SHALL 用该类别的 `closing` 填入期末递延所得税资产列、`opening` 填入期初递延所得税资产列。
2. WHEN 资产段某行已有任一非空值 THEN 系统 SHALL NOT 覆盖（手工优先）。
3. WHEN N1-2 明细已按类别有数 THEN 系统 SHALL 优先使用 N1-2 派生值（明细优于科目余额，因明细含暂时性差异列）。
4. WHEN 披露表加载且负债段某行四个值全为空 AND `liability_prefill` 含该行对应语义槽 THEN 系统 SHALL 填入递延所得税负债列的期初/期末值。
5. WHEN 四表无对应科目余额 THEN 系统 SHALL 保持 `null`（禁止写 0 冒充「已核实为零」）。
6. WHEN 预填仅能提供递延所得税资产/负债金额而无法提供暂时性差异 THEN 系统 SHALL 只填金额列，暂时性差异列保持 `null`。

### Requirement 4: 披露表结构对齐源模板

**User Story:** 作为项目经理，我希望披露表的行骨架与列口径与致同源模板逐字一致，这样交付的
附注不会因为多一行少一列被复核退回。

#### Acceptance Criteria

1. WHEN 亏损到期表初始化 THEN 系统 SHALL 生成 6 个年度行（`auditYear` 至 `auditYear+5`），对齐源模板 R46:R51 的 6 行设计（首年只在上年年末列有值、末年只在期末列有值）。
2. WHEN 国企抵销后净额表 (2)A 初始化或表 (1) 行发生增删改名 THEN 系统 SHALL 使 (2)A 的行标签镜像表 (1)（源模板 A36=`=A13` … A50=`=A27`）。
3. WHEN 国企披露表渲染 THEN 系统 SHALL 提供「不以抵销后净额列示 / 以抵销后净额列示」二选一开关（源模板 R7 分支规则），且未选中的分支表 SHALL 进入 `_removed_table_keys`。
4. WHEN 上市披露表渲染 THEN 系统 SHALL 提供表 (2) 适用性开关（源模板 R33 括注「不适用的删除」），关闭时该表进入 `_removed_table_keys`。
5. WHEN 二选一开关切换 THEN 系统 SHALL 持久化该选择，且两分支共用行 state 不得双真源。

### Requirement 5: 附注模板行集与报表行编码对齐

**User Story:** 作为质量控制复核合伙人，我希望附注里的行名来自致同源模板，而不是开发按常识造的，
这样我复核时能逐行对上模板。

#### Acceptance Criteria

1. WHEN 附注 `五、30` 表 0 被 seed THEN 资产段行 SHALL 逐字等于源模板 R13:R19 的 7 项，负债段行 SHALL 逐字等于源模板 R23:R27 的 5 项。
2. WHEN 附注 `八、31` 表 0 与表 1 被 seed THEN 行集 SHALL 逐字等于源模板对应区段（负债段第 4 项为「租赁形成」）。
3. WHEN 附注模板任一表被 seed THEN 系统 SHALL NOT 包含 `……` 占位行（该语义移入 `guidance`）。
4. WHEN 附注 `八、31` 表 2（互抵明细）被 seed THEN 系统 SHALL 输出空行骨架（源模板 R56:R58 全空，属纯动态行区域）。
5. WHEN 亏损到期表被 seed THEN 两版 SHALL 均为 6 个年度行 + 合计行。
6. WHEN 附注模板行携带 `report_row_code` THEN 递延所得税资产相关行 SHALL 用 `BS-036`、递延所得税负债相关行 SHALL 用 `BS-067`（DB 实证值）。
7. WHEN 附注模板行携带 `account_codes` THEN 该科目 SHALL 是递延所得税科目（`1811` / `2901`）；底层资产负债科目（`2601` / `1641` / `1642` / `1643`）SHALL 被移除。
8. WHEN 附注 `五、30` 的 `text_sections` 被 seed THEN 系统 SHALL NOT 包含截断的证监会指引段落（源模板无此内容且该段在句中被截断）。
9. WHEN 幂等脚本以 `--check` 运行于已对齐的模板 THEN 系统 SHALL 报告 0 欠账并以 exit 0 结束。

### Requirement 6: 公式预设清理与补齐

**User Story:** 作为审计助理，我在 N1 底稿页打开公式管理时，希望看到的预设都与递延所得税资产
相关，且每张有取数需求的 sheet 都有可用预设。

#### Acceptance Criteria

1. WHEN 加载 `workpaper:N1` 的公式预设 THEN 系统 SHALL NOT 包含应交税费（`2221`）/ 税金及附加（`6403`）相关预设。
2. WHEN 加载 `workpaper:N1` 的公式预设 THEN 系统 SHALL NOT 包含跨科目大类的区间求和表达式（如 `TB_SUM('2221~6403', ...)`）。
3. WHEN N1-2 明细表预设被加载 THEN 系统 SHALL 同时提供 `1811.01`~`1811.07` 的期初余额与期末余额预设。
4. WHEN N1-4 测算表 / N1-5 亏损检查表 / 披露表存在可确定的取数口径 THEN 系统 SHALL 提供对应预设。
5. WHEN 新增预设 THEN 每条表达式 SHALL 可被 `formula_engine.validate_formula` 解析。
6. WHEN 预设涉及跨底稿引用 THEN 系统 SHALL 遵守「审定表可用 `WP()`，明细表禁 `WP()` 防循环」铁律。

### Requirement 7: 守卫与实测

**User Story:** 作为技术复核人，我希望这些结构约束被测试锁死，避免下一次 md 重建或并发会话
把它们改回去。

#### Acceptance Criteria

1. WHEN 后端守卫运行 THEN 系统 SHALL 直读源模板 xlsx 交叉比对附注模板行集与列结构，并含反向自检（断言比对逻辑本身非空转）。
2. WHEN 前端契约运行 THEN 系统 SHALL 校验披露载荷列键、两版子列序、子表名逐字一致、二选一分支的 `_removed_table_keys`。
3. WHEN 后端守卫运行 THEN 系统 SHALL 断言 `report_row_code` 与 `account_codes` 白名单。
4. WHEN 公式预设守卫运行 THEN 系统 SHALL 断言 `workpaper:N1` 预设不含禁用科目。
5. WHEN 实测执行 THEN 系统 SHALL 在活体项目上验证「四表已入库 → 打开披露表有数 → 推送后附注落库」全链，并在验证后复原测试数据。

## Glossary

| 术语 | 含义 |
|------|------|
| 源模板 | `backend/wp_templates/N/N1 递延所得税资产.xlsx`（运行时权威副本），本 spec 的唯一结构裁决者 |
| 语义槽 | 负债段 5 个行位的稳定英文键（`depreciation` / `afs_fv` / `investment_property_fv` / `lease` / `other`），因两版第 4 项中文用语不同故不用中文名作键 |
| 资产段 7 类 | 源模板 R13:R19 = 资产减值准备 / 可抵扣亏损 / 内部交易未实现利润 / 公允价值变动 / 租赁负债 / 购入摊销年限小于税法规定的资产 / 其他；与后端 `_N1_ADJUDICATION_CATEGORIES` 逐字同构 |
| 四表直通 | 四表入库后，底稿无需人工编制前置表即可带出数据的取数路径 |
| 二选一分支 | 源模板国企 R7 规定的「不以抵销后净额列示按 (1) 披露 / 以抵销后净额列示按 (2) 披露」互斥关系 |
| `_removed_table_keys` | 同步载荷字段，令后端删除附注中不再由本底稿承载的子表，防孤儿表残留 |
