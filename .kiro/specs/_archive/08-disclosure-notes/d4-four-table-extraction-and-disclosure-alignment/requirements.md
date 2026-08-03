# Requirements Document

## Introduction

D4 营业收入是 D 类循环中**唯一没有做过四表取数专属 spec** 的循环（D1 有 `d1-extraction-chain-completion` + `d1-four-table-extraction-formula-wiring`，D2/D3/D5/D6/D7 有 `d-cycle-extraction-chain-completion`）。本 spec 补齐 D4「四表入库 → 底稿刷新取数 → 披露表 → 附注模块」全链，并把两个披露表与附注两个章节按**源模板**（唯一裁决者）重建结构。

### 立项依据（全部为只读实证，非推断）

**源模板**（`backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`，openpyxl 逐格 + 合并区）

- 上市 sheet `附注披露信息（上市公司）` A1:I85，**8 个小节**：（1）营业收入和营业成本 / （2）按行业（或产品类型）划分 / （3）按地区划分 / （4）按分解信息 / （5）履约义务的说明 / （6）与剩余履约义务有关的信息 / （7）重大合同变更 / （8）试运行销售收入
- 国企 sheet `附注披露信息（国企）` A1:S72，**7 个小节**（无「（8）试运行销售收入」，（4）名为「营业收入分解信息」）
- （1）（2）（3）（8）均为 **5 列两级表头**：`项 目`(rowspan2) + `本期发生额{收入,成本}` + `上期发生额{收入,成本}`
- （4）为 **9 列列转置**：`A45:A47` 空(rowspan3) + `B45:I45` 合并「本期发生额」+ `消费品`(B46:C46)/`汽车`(D46:E46)/`能源`(F46:G46)/`其他`(H46:I46) + `收入`/`成本` × 4
- （6）为 **4 列**：`年 度` + 两个年度列（上市 R68 = 2024年/2025年）+ `合计`，行 `xx合同预计将确认的收入` + 空白动态行
- D4-1 审定表：`项目` + `本期数{未审数,账项调整,重分类调整,审定数}` + `上期数{...}`；**主营业务收入：/ 其他业务收入： 各有 4 行空白可扩行 + 小计**，末尾 `试算平衡表数` / `差异数`

**科目映射链**（`report_config` / `account_mapping` / `trial_balance` / `tb_balance` / `tb_ledger` 只读实证）

- `IS-001 一、营业收入 = SUM_TB('6001~6099','本期发生额')`，`IS-002 减：营业成本 = SUM_TB('6401~6499','本期发生额')` —— **四准则完全一致**，且均为**区间**而非单码
- `account_mapping` 逐项目反解齐全：项目 `0ec33ac9` 的标准码 `6001` → 原始码 `6001`/`6001.11`/`6001.11.01~.03`/`6001.12`/`6001.14`/`6001.14.01~.03`/`6001.15`/`6001.15.01~.02`/`6001.16`/`6001.16.01~.06`/`6001.17`（**逐项目不同**，故必须动态取数）
- **收入与成本子科目后缀天然镜像**：`6001.11 营业收入_批发` ↔ `6401.11 营业成本_批发`；`.12 零售`/`.14 物流`/`.15 物业与租赁`/`.16 医疗`/`.17 服务费及其他` 全部镜像。**名称不完全相等**（`.16` 收入侧「医疗收入」/ 成本侧「医疗支出」）→ 后缀优先、名称作校验
- 镜像**不保证完整**：项目 `2aa00f57` 的 `6001.15 物业与租赁` 有收入 3,614,997.94 但**无对应成本子科目** → 成本列必须允许留空

**已确认无存量污染**：全库 `note_section IN ('五、62','八、64')` 共 5 条，`last_sync_at` **全部为 NULL**、`sub_table_data` 全部不存在 → D4 从未同步过附注，结构改动无需存量清理脚本。

## Glossary

| 术语 | 含义（本 spec 内） |
|------|------|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张导入表 |
| 报表行 | `report_config` 表的一行，`row_code` + `applicable_standard` + `formula`，是科目映射的**唯一真源** |
| 区间码 | 报表行公式中的 `SUM_TB('6001~6099', ...)` 形态，展开为一段标准码 |
| 标准码 | `trial_balance.standard_account_code`，平台统一科目码 |
| 原始码 | `tb_balance.account_code`，客户自有科目码，经 `account_mapping` 与标准码互查 |
| 叶子科目 | `tb_balance` 中不存在 `code + '.'` 前缀子行的科目；叶子和 == 父科目额 |
| 镜像配对 | 收入子科目 `6001.{suffix}` 与成本子科目 `6401.{suffix}` 按 suffix 配对 |
| 发生额 | 损益类科目的本期借/贷方发生金额；损益类科目**无余额概念** |
| 两级表头 | 附注 `ColumnDef.group`（父）+ `label`（叶子），经 `_column_groups` 投影 |
| 列转置 | 分类维度作**列头**、检查项作**行**的表形态（源模板（4）分解信息） |
| flat | `ColumnDef.flat = true`，声明该表为单级表头，禁止后端前缀推断父表头 |
| 孤儿子表 | 推送的 `sub_table_data` 键在附注模板 `tables[].name` 中不存在，附注永远渲染不出 |
| 宁缺勿造 | 无法从四表干净映射时返回空，不臆造行/列 |

## Requirements

### Requirement 1: 四表取数 resolver 口径纠正（P0，数字错误）

**User Story:** 作为审计助理，我把四表数据入库后打开 D4-2 主营业务收入明细表，希望能按月看到真实收入，而不是一整行 0。

#### Acceptance Criteria

1.1. WHEN `d4_ledger_monthly` 或 `d4_ledger_monthly_by_product` 从 `tb_ledger` 取发生额 THEN 系统 SHALL NOT 使用 `SUM(credit_amount - debit_amount)`，因为 `tb_ledger` 对侧列存 **NULL**（实测 10 个项目中 8 个该表达式整列返回 NULL，经 `COALESCE` 兜底后恒为 0）。
1.2. WHEN 取损益类科目发生额 THEN 系统 SHALL 按科目方向取单侧发生额（收入类取贷方、成本类取借方），并对 NULL 做 `COALESCE(col, 0)`。
1.3. WHEN 全年账含年末结转损益分录 THEN 系统 SHALL NOT 依赖「借贷净额」口径（实测 10 个项目中 7 个 `SUM(credit) == SUM(debit)` 精确相等，如 `a7fc75e5` 两侧均为 6,798,732,711.94）。
1.4. WHEN 任一 D4 resolver 查询 `tb_ledger` / `tb_balance` / `trial_balance` THEN 系统 SHALL 使用 `get_active_filter(db, table, project_id, year)`，SHALL NOT 裸写 `is_deleted = false`（实测 `tb_ledger` 有 `dataset_id` 列；项目 `0ec33ac9` 裸查 6001 贷方合计 1,801,755,477.21 = `trial_balance` 权威值 895,804,876.83 的 **2.01 倍**，即跨数据集双算）。
1.5. WHEN `trial_balance` 中损益类科目以负数存储贷方性质 THEN 系统 SHALL 做符号归一（实测项目 `df5b8403` 的 `6001` = **-38,258,743.63**），SHALL NOT 让披露表出现负收入。
1.6. WHEN 上期（`year - 1`）在 `trial_balance` 无数据 THEN 系统 SHALL 返回 `null` 而非 `0`，并由前端显示「上期无数据」提示，SHALL NOT 把缺数据伪装成 0。

### Requirement 2: 报表行驱动的动态科目定位（P0，取数正确性 + 溯源）

**User Story:** 作为现场经理，不同客户的收入科目结构完全不同（有的挂 `6001.11 批发`，有的挂 `6001.01 车辆租金收入`），我希望平台按报表映射规则自动定位，而不是写死几个科目码。

#### Acceptance Criteria

2.1. WHEN D4 定位收入/成本科目 THEN 系统 SHALL 复用共享件 `app/services/four_table/`（`ReportLineAccountSpec` + `resolve_report_line_accounts` + `select_leaves` / `aggregate_leaves`），SHALL NOT 再造科目定位或聚合方言。
2.2. WHEN 解析报表行 THEN 系统 SHALL 以 `row_code='IS-001'`（收入）与 `row_code='IS-002'`（成本）为真源，并传入 `applicable_standards`。
2.3. WHEN 报表行公式为**区间**（`SUM_TB('6001~6099',...)`）THEN 系统 SHALL 走共享件既有的区间能力（`filter_by_code_specs` / `sql_prefixes_for_specs`，F1 的 `1401~1499` 已验证），SHALL NOT 把区间当单码前缀匹配。
2.4. WHEN 标准码需落到客户原始码 THEN 系统 SHALL 经 `account_mapping` 反解（逐项目），SHALL NOT 假设客户原始码等于标准码。
2.5. WHEN 聚合 `tb_balance` THEN 系统 SHALL 只汇总**叶子**科目（无 `code + '.'` 子行），且 SHALL 满足不变量「叶子和 == 父科目发生额」。
2.6. WHEN D4 render 完成 THEN 系统 SHALL 输出 `tb_source_codes`（含 `revenue_standard` / `cost_standard` / `resolved_from` / `unmapped`），且该输出 SHALL 有前端消费方（溯源面板），SHALL NOT 成为 dead output。
2.7. WHEN 报表行解析落空 THEN 系统 SHALL 回退到兜底码并把 `resolved_from` 标为 `fallback`，SHALL NOT 静默返回空。

### Requirement 3: D4-1 审定表四表预填（推翻既有「宁缺勿造」判定）

**User Story:** 作为审计助理，四表入库后我希望 D4-1 审定表的主营/其他业务明细行已按客户实际科目自动建好并填上未审数。

#### Acceptance Criteria

3.1. WHEN 评估 D4 是否可预填 THEN 系统 SHALL 以实证为准：`6001` 在 9 个在册项目中**存在业务板块级子科目**（批发/零售/物流/物业与租赁/医疗/服务费及其他），且 D4-1 源模板主营/其他两段各为 **4 行空白可扩行**（`R8:R11` / `R14:R17`）→ 既有 `_d4_operating_revenue.render` 中「无干净 TB→审定表明细行映射」的结论 SHALL 被推翻并在代码注释中记录推翻依据。
3.2. WHEN 生成审定表预填 THEN 系统 SHALL 按 `tb_balance` **叶子科目名**建行（复用 K2 建立的动态行范式 `composables/shared/dynamicAdjudicationRows.ts`），SHALL NOT 使用固定行。
3.3. WHEN 叶子科目归属主营/其他 THEN 系统 SHALL 按标准码归属判定（`6001` 子树 → 主营业务收入段，`6051` 子树 → 其他业务收入段），SHALL NOT 按名称猜测。
3.4. WHEN 该行已有手工录入值 THEN 系统 SHALL 保留手工值（手工优先），SHALL NOT 覆盖。
3.5. WHEN 四表重新入库后出现新子科目 THEN 系统 SHALL 支持自动插行；WHEN 已有行金额发生变化 THEN 系统 SHALL 弹确认（可选「仅补空值」），复用 K2 的 `previewSeedFromPrefill` 范式。
3.6. WHEN 无任何可映射叶子科目 THEN 系统 SHALL 返回空预填（宁缺勿造），SHALL NOT 臆造行。
3.7. WHEN 审定表渲染 `试算平衡表数` 行 THEN 系统 SHALL 取 `IS-001` 口径的 `trial_balance` 值，且 `差异数` = 审定合计 − 试算平衡表数。

### Requirement 4: 披露表结构对齐源模板（列结构 + 缺失表）

**User Story:** 作为审计助理，披露表应该长得跟源模板一样，我填完就能直接推送到附注，不需要在附注里再补一遍。

#### Acceptance Criteria

4.1. WHEN 渲染（1）主表 THEN 系统 SHALL 使用 5 列两级表头（`项目` + `本期发生额{收入,成本}` + `上期发生额{收入,成本}`），SHALL NOT 把两级拍平成组合列名。
4.2. WHEN 渲染（2）按行业（或产品类型）划分 与（3）按地区划分 THEN 系统 SHALL 提供**4 个数据列**（本期收入/本期成本/上期收入/上期成本）；WHEN 变体为上市 THEN 现有仅 2 列（缺上期）SHALL 被补齐（国企 Tab 已有 4 列，两版当前不对称）。
4.3. WHEN 渲染（3）按地区划分的叶子列名 THEN 上市变体 SHALL 用「主营业务收入 / 主营业务成本」（源 R37），国企变体 SHALL 用「收入 / 成本」（源 R31）；两版列名 SHALL NOT 统一。
4.4. WHEN 渲染（4）分解信息 THEN 系统 SHALL 实现**列转置 + 动态类别列**（类别作列头、`在某一时点确认`/`在某一时段确认`/`租赁收入` 作行），列 key SHALL 使用稳定标识 `{slot}_{seq}` 而非 label（H7 范式：类别默认名可能重复，用 label 会撞键）。
4.5. WHEN 渲染（6）与剩余履约义务有关的信息 THEN 系统 SHALL 提供结构化录入区块（动态年度列 + 动态合同行 + 合计派生列），SHALL NOT 仅以文本框承载（源模板为结构化表）。
4.6. WHEN 变体为上市 THEN 系统 SHALL 额外提供（8）试运行销售收入录入区块（5 列两级，行 `固定资产试运行收入` / `研发样品销售收入`）；WHEN 变体为国企 THEN 该区块 SHALL 不存在（源模板国企 sheet 无此小节）。
4.7. WHEN 动态年度列生成 THEN 系统 SHALL 由审计年度派生，SHALL NOT 硬编码年份。
4.8. WHEN 披露表存在死代码数据类型（`Top5CustomerRow` / `ContractBalanceRow`，源模板披露 sheet 无「前五大客户」「合同资产负债变动」内容）THEN 系统 SHALL 删除，SHALL NOT 保留 DEPRECATED 注释。

### Requirement 5: 附注模板结构修订（两版 11 张表）

**User Story:** 作为质量控制复核合伙人，我在附注模块看到的表格结构必须与源模板一致，列头不能是系统猜的。

#### Acceptance Criteria

5.1. WHEN 修订附注模板 THEN 系统 SHALL 通过**幂等脚本**（带 `--dry-run` / `--check` / `_aligned_by` 标记）修改 `note_template_listed.json` 五、62 与 `note_template_soe.json` 八、64，SHALL NOT 手改 JSON。
5.2. WHEN 表为源模板两级表头 THEN 模板 `columns` SHALL 声明 `group`；WHEN 表为单级表头 THEN `columns` SHALL 显式标 `flat`（当前 11 张表 `columns` 全为 0，退化前缀推断会把「本期发生额/上期发生额」猜成父表头）。
5.3. WHEN 表首行为压扁的第二行表头残留（`row_type: header_label`）THEN 系统 SHALL 删除该假数据行；（4）分解信息表当前有**两连** `header_label` SHALL 一并删除。
5.4. WHEN 表名与源模板不一致 THEN 系统 SHALL 改名并走 `rule(aliases=)` 而非 `drop_tables`：（4）表当前两版均为「营业收入、营业成本按商品转让时间划分」，源模板上市为「营业收入、营业成本按分解信息」、国企为「营业收入分解信息」；（6）表当前表名是**段落文本泄漏**（`分摊至尚未履行的履约义务的交易价格为xxx元，截止xx年xx月xx日，对于上述金额确认为收入的预计时间如下：`）SHALL 正名为「与剩余履约义务有关的信息」。
5.5. WHEN （6）表存在硬编码年份列（上市 `2026年/2027年`、国企 `2025年/2026年`）THEN 系统 SHALL 改为随审计年度派生。
5.6. WHEN 试运行销售收入表行名与源模板不一致 THEN SHALL 修正为「固定资产试运行收入」/「研发样品销售收入」，并删除源模板不存在的合计行。
5.7. WHEN 补 `guidance` THEN 内容 SHALL 只取源模板红字/提示（R57-R62 分解类别指引、R66 剩余履约义务要求、R71-R77 简化操作方法、R81 准则解释第 15 号试运行销售），SHALL NOT 自造，且 SHALL 为纯文本（禁 markdown 粗体）。
5.8. WHEN 修订 `text_sections` THEN 上市当前 10 段**全部为裸表名/裸标题**（不匹配 `_is_table_title_paragraph` 判定 → 会落进 `text_content` 变成正文污染）SHALL 加 `#### ` 前缀或改为 `（N）xxx` 编号形态；国企当前仅 4 段 SHALL 补齐源模板（1)~(7) 小节标题与 R50-R70 说明段。
5.9. WHEN 修订完成 THEN `_aligned_by` SHALL 被写入，`--check` SHALL 返回 0 项欠账。

### Requirement 6: 披露表 → 附注推送载荷对齐

**User Story:** 作为审计助理，我在披露表点「同步到附注」后，附注里的表格应该和我填的一模一样，不能少表少列。

#### Acceptance Criteria

6.1. WHEN 构建 sync payload THEN `sub_table_data` 各子表键 SHALL 与附注模板 `tables[].name` 逐字一致（否则产生孤儿子表）。
6.2. WHEN 推送（2）（3）表 THEN 载荷 SHALL 包含上期两列（当前 `d4NoteSectionMap` 只推 2 列，国企 Tab 已录的上期数据是 dead input）。
6.3. WHEN 推送（4）分解信息 THEN 载荷 SHALL 按列转置结构推送动态类别列的 `columns` 与 `group`。
6.4. WHEN 推送（6）（8）表 THEN 载荷 SHALL 包含这两张表（当前完全未推送）。
6.5. WHEN 底稿改版导致子表键变化 THEN 载荷 SHALL 上报 `_removed_table_keys`，且该集合 SHALL 与本次推送键求差集（防误删）。
6.6. WHEN 推送文本 THEN `_note_texts` SHALL 位于 `sub_table_data` 内、SHALL 带中文 `title`、SHALL 过滤空文本。
6.7. WHEN 单级表 THEN 载荷 `columns` SHALL 显式标 `flat`（`flat` 必须 seed 与推送**两处**都加，H8 已踩过只加一侧的坑）。
6.8. WHEN 变体为国企且当前项目不适用上市附注 THEN 上市 Tab SHALL 显示「不适用」且零写入（服务端 `detect_standard_conflict` 已提供 409 兜底）。

### Requirement 7: 公式预设重写（当页公式管理）

**User Story:** 作为现场经理，我在底稿当页打开公式管理，应该能看到这张表每个取数格子的公式，且公式口径是对的。

#### Acceptance Criteria

7.1. WHEN D4 公式预设取损益类科目 THEN 公式 SHALL 使用 `'本期发生额'` 口径，SHALL NOT 使用 `'期初余额'` / `'期末余额'`（当前 4 条预设全部错用余额口径，损益类科目无余额概念）。
7.2. WHEN 预设引用收入区间 THEN SHALL 对齐 `IS-001` 的 `'6001~6099'`，SHALL NOT 写 `'6001~6051'`；其他业务收入 `6051` SHALL 单列。
7.3. WHEN 同一 wp_code 下有多个块 THEN 每块 SHALL 声明 `sheet_name`（当前 6 个块全为 `sheet=None`，`page_key=workpaper:D4` 忽略 sheet 导致 `上年审定数` 在两个块间撞键被吞）。
7.4. WHEN 披露表需要成本数据 THEN SHALL 补 `6401` / `6402` 侧预设（当前完全缺失）。
7.5. WHEN 披露 sheet 打开公式管理 THEN SHALL 有对应预设块（当前两个披露 sheet 零预设，公式管理页空白）。
7.6. WHEN 存在贴错标签的预设块 THEN SHALL 纠正：块 `营业收入明细表` 在源 xlsx 无此 tab（真实 tab 为 `主营业务收入明细表D4-2` / `其他业务收入明细表D4-3`），且其 `TB_AUX('6001','客户','期末余额')` 口径与维度双错（D4-2 是按月×产品，非按客户）。
7.7. WHEN 审定表块使用 `WP()` 引用明细表 THEN 明细表块 SHALL NOT 反向引用审定表（防成环）。
7.8. WHEN 预设改动完成 THEN SHALL 由幂等脚本落地（`--dry-run` / `--check`），且 SHALL 有守卫断言科目码属于 `IS-001`/`IS-002` 引用的科目集合（平台守卫盲区：既有测试只校验公式语法合法性，从不校验科目码是否属于本循环）。

### Requirement 8: 平台级 UI 铁律与 AI 辅助

**User Story:** 作为审计助理，披露表的金额录入要有千分符，文本框要有 AI 辅助，跟其他循环体验一致。

#### Acceptance Criteria

8.1. WHEN 披露表录入金额 THEN SHALL 使用 `components/workpaper/shared/WpAmountInput.vue`（当前两个 Tab 共 33 个裸 `el-input type="number"`、0 个 `WpAmountInput`）。
8.2. WHEN 只读展示金额 THEN SHALL 走 `displayPrefs.fmtAmount()`（当前有 2 处自造 `toLocaleString`）；SHALL 以 setup 顶层 `inject` 或 `useDisplayPrefsStore()` 取用，SHALL NOT 从 `@/stores/displayPrefs` 命名导入 `fmtAmount`（该导出不存在，会让整页崩）。
8.3. WHEN 披露表有文本域 THEN 每个文本域 SHALL 配 AI 辅助按钮（当前 8 个文本框零 AI），且 SHALL 调 `POST /api/workpapers/{wpId}/ai/generate-text`，`context` SHALL 为 `dict[str,str]`。
8.4. WHEN 注册 AI section THEN SHALL 同时登记后端 `_SECTION_PROMPTS` + `_SUPPORTED_SECTIONS` 与前端联合类型 + Tab 内 `AI_TARGETS` 四处，且每条 prompt SHALL ≥20 字并含「不得虚构」约束。
8.5. WHEN 宿主向披露 Tab 传参 THEN SHALL 传 `:project-id` 与 `:html-data`，且 SHALL 经 `useHostApplicableStandards` 提供 `applicableStandards`（当前宿主 `applicableStandards` 命中 0 次 = 变体门恒开）。
8.6. WHEN 自动同步 THEN SHALL 监听**实际数据**变化，SHALL NOT 在 `syncToDisclosureNotes` 内自调度 `scheduleAutoSync(syncToDisclosureNotes)`。

### Requirement 9: 守卫与实测

**User Story:** 作为 EQCR 技术复核人，我要确信这些修复不会在下一次改动中静默退化。

#### Acceptance Criteria

9.1. WHEN 编写附注结构守卫 THEN SHALL 用 openpyxl **直读源 xlsx** 与模板 `headers` / 同步 `columns` 做三向比对，并包含**反向自检**（断言归一函数与提取正则确实命中，防空转）。
9.2. WHEN 编写取数守卫 THEN SHALL 以**真实签名真实 await 调用**被测函数并断言返回非零，SHALL NOT 只测导入可用性（N5 曾因此让 `get_active_filter` 单参调用错误静默通过）。
9.3. WHEN 编写测试替身 THEN mock 的 `get_active_filter` SHALL 返回真实 `sa.true()`，SHALL NOT 返回 `MagicMock()`（会被 `sa.and_` 拒绝后 fail-open 吞成空结果 = 假绿）。
9.4. WHEN 替身需区分同一张表的多次查询 THEN SHALL 按 SQL 内容或绑定参数区分（D1 曾因替身不区分导致备抵 == 原值、净额恒 0）。
9.5. WHEN 声明 `build*Columns` THEN SHALL 零入参可调（平台 `disclosureColumnsCoverage.spec.ts` 用空入参 sweep），参数化版本 SHALL 另起名并由零参包装对外导出。
9.6. WHEN 新增 builder THEN SHALL 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`。
9.7. WHEN 交付 THEN SHALL 用真实数据库直跑 render 验证取数金额，并用浏览器（chrome-devtools 或 Playwright）+ postgres 只读验证「披露表推送 → 附注落库」链路，SHALL 在验证后复原测试数据。
9.8. WHEN 新增 CI job THEN SHALL 覆盖附注结构脚本 `--check` 与前端契约测试。
9.9. WHEN 读源码型守卫 THEN SHALL 先 `stripComments()` 并对该函数加反向自检（守卫注释里通常写有被禁字样的反例）。
