# D 类底稿（销售收入循环）— 需求文档

## 1. 概述

D 类底稿覆盖"实质性程序—销售收入循环"阶段（审计循环代号 D），是 C 类控制测试结论的后续应对——根据 B50 风险评估结果和 C2 控制测试结论，执行实质性程序以获取充分适当的审计证据。包含 **7 大科目组 + 1 函证组、17 个模板文件、约 80+ 个子底稿 sheet**。

本 spec 目标：**查清现有 D 类实现的覆盖范围，找出缺口，补全遗漏**。D 类是最早开发的循环底稿，基础注册和生成 schema 已存在，重点是：
1. 补全子底稿 wp_code 注册（从 13 条扩充到完整覆盖）
2. 补全 `_WP_CODE_OVERRIDE` componentType 映射
3. 确认/修正生成 schema 的 componentType 分配
4. 补全程序表模板提取
5. 完善联动链（B50→D + C2→D + D→trial_balance + D→disclosure_notes）

## 2. 现状与差距

### 2.1 已有实现

| 维度 | 现状 | 说明 |
|------|------|------|
| wp_account_mapping | 13 条（D0~D7 + D2-2/D2-3/D2-4/D5-1/D6-1/D7-1） | 缺大量 D1/D2/D4 子码 |
| generated YAML schema | 19 个文件（D0/D1/D2/D2-1/D2-5/D2-6/D3/D4/D4-1/D4-5/D4-6/D4-12/D4-13/D4-21/D4-22/D4-33/D5/D6/D7） | 有 sheet 结构但未经人工审核 |
| _WP_CODE_OVERRIDE | 0 条 | D 类完全无显式 componentType 映射 |
| pattern matching | 无 | 无 D 类通用 schema 规则 |
| ConfirmationHub | D0 函证已有独立模块 | confirmation_service 是函证事实唯一真源 |
| disclosure_notes | D 类附注已有 c-note-table 处理 | 附注披露 sheet 走 disclosure_notes 模块 |
| risk_for_cycle | B50→D 风险读取就绪 | auto_data_resolvers 已注册 |
| control_test_result_for_cycle | C2→D 控制测试结论读取就绪 | auto_data_resolvers 已注册 |
| account_package_summary | D 工作包摘要服务已有 | 消费 confirmation metrics |

### 2.2 待补缺口

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| D1 子码缺失（D1-1~D1-10 约 10+ 子底稿） | 无法精确路由各 sheet | P0 |
| D2 子码不完整（缺 D2-5~D2-13 检查/分析子码） | 应收账款检查底稿无法独立打开 | P0 |
| D4 子码严重缺失（D4-1~D4-36 大量子码） | 营业收入子底稿无法路由 | P0 |
| D3/D5/D6/D7 子码缺失 | 预收/融资/合同资产/负债子底稿不全 | P0 |
| _WP_CODE_OVERRIDE 全空 | render-config 走 fallback 路径，无法精确匹配 componentType | P0 |
| D{n}A 程序表未提取模板 | 程序表步骤不在 procedure_table_templates.json | P1 |
| D 审定表→trial_balance 联动 | audited_amount 回写缺乏自动触发 | P2 |
| D 附注→disclosure_notes 联动确认 | 需确认 c-note-table 渲染是否完整覆盖 | P2 |

## 3. 术语表（Glossary）

- **销售收入循环系统（Revenue_Cycle_System）**：平台中负责 D 类底稿渲染、编辑、联动的子系统
- **审定表（Audit_Determination_Table）**：D{n}-1 系列，记录科目审定金额+调整分录汇总
- **实质性程序表（Substantive_Procedure_Table）**：D{n}A 系列，列出该科目的具体审计程序步骤
- **明细表（Detail_Schedule）**：D{n}-2/D{n}-3 系列，按维度展开科目余额明细
- **检查表（Inspection_Table）**：D{n}-6~13 系列，逐笔检查抽样交易
- **分析程序表（Analytical_Procedure）**：D{n}-5/D4-6~11 系列，执行分析性程序
- **函证（Confirmation）**：D0 系列，向第三方确认应收余额
- **坏账准备（Allowance_for_Doubtful）**：D{n}-4 系列，测试应收款项减值准备

## 4. D 类底稿分组结构

| 组 | 编号范围 | 功能 | 模板文件 | componentType |
|----|---------|------|---------|---------------|
| G0 | D0/D0A/D0-1~D0-5 | 收入循环函证 | 1 xlsx(11 sheet) | ConfirmationHub（已有）+ `d-form-table` |
| G1 | D1/D1A/D1-1~D1-10+ | 应收票据 | 1 xlsx(21 sheet) | 程序表=`a-program-console`，审定表/明细=`d-form-table`/`audit-sheet` |
| G2 | D2/D2A/D2-1~D2-13 | 应收账款 | 3 xlsx(合计~30 sheet) | 程序表=`a-program-console`，审定表/明细=`d-form-table`，检查/分析=`audit-sheet` |
| G3 | D3/D3A/D3-1~D3-4 | 预收账款 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table` |
| G4 | D4/D4A/D4-1~D4-36 | 营业收入 | 7 xlsx(合计~60+ sheet) | 程序表=`a-program-console`，审定/明细=`d-form-table`，分析/检查/IPO=`audit-sheet` |
| G5 | D5/D5A/D5-1~D5-4 | 应收款项融资 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table` |
| G6 | D6/D6A/D6-1~D6-9 | 合同资产 | 1 xlsx | 程序表=`a-program-console`，审定/明细/测算=`audit-sheet`，检查=`d-form-table` |
| G7 | D7/D7A/D7-1~D7-4 | 合同负债 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table` |

## 5. 各组详细需求

### G0: 收入循环函证 (D0)

**模板文件：** D0 收入循环函证.xlsx（11 sheet）

**Sheet 结构：**
- 底稿目录 / 函证程序表D0A / 函证结果汇总D0-1 / 核实被函证单位D0-2 / 跟函控制D0-3 / 差异调节D0-4 / 差异检查示例 / 替代程序D0-5

**需求点：**

#### Requirement G0-1: ConfirmationHub 集成

**User Story:** 作为审计项目组成员，我想通过平台已有的函证模块管理收入循环函证，以便统一管理函证流程。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 将 D0 底稿的核心函证功能路由到已有的 ConfirmationHub 模块
2. THE Revenue_Cycle_System SHALL 在 D0A 程序表中通过 ref_index chip 跳转到 ConfirmationHub 对应函证批次
3. WHEN 用户打开 D0 底稿时，THE Revenue_Cycle_System SHALL 显示该项目 D 循环的函证摘要（已发函数/回函率/差异数）
4. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D0-1（函证结果汇总）、D0-2（核实被函证单位）、D0-4（差异调节）、D0-5（替代程序）等辅助 sheet
5. THE Revenue_Cycle_System SHALL 不渲染"差异检查示例" sheet（标记为参考不开发）

#### Requirement G0-2: D0A 函证程序表

**User Story:** 作为审计项目组成员，我想执行函证程序表中的步骤，以便确保函证流程完整。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D0A 函证程序表
2. THE Revenue_Cycle_System SHALL 从 xlsx 模板提取 D0A 全部程序步骤，注册到 procedure_table_templates.json
3. THE Revenue_Cycle_System SHALL 在程序表步骤中包含 ref_index chip 跳转到 D0-1~D0-5 各辅助底稿


### G1: 应收票据 (D1)

**模板文件：** D1 应收票据.xlsx（21 sheet）

**Sheet 结构：**
- 底稿目录 / 程序表D1A / 审定表D1-1 / 附注披露（上市公司）/ 附注披露（国企）/ 原值明细（按类）D1-2 / 原值明细（按客户）D1-3 / 坏账准备D1-4 / 减值测算 / 调整分录汇总 / 检查表 / 分析程序 / 关联方检查 / ...

**需求点：**

#### Requirement G1-1: D1A 程序表

**User Story:** 作为审计项目组成员，我想执行应收票据实质性程序，以便获取科目审计证据。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D1A 程序表
2. THE Revenue_Cycle_System SHALL 从 xlsx 模板提取 D1A 全部程序步骤，注册到 procedure_table_templates.json
3. WHEN 程序步骤标记为"已执行"时，THE Revenue_Cycle_System SHALL 记录执行人和执行日期
4. THE Revenue_Cycle_System SHALL 在程序表中通过 `auto_data_source: "risk_for_cycle"` 展示 B50 对应风险评估结论
5. THE Revenue_Cycle_System SHALL 在程序表中通过 `auto_data_source: "control_test_result_for_cycle"` 展示 C2 控制测试结论

#### Requirement G1-2: D1-1 审定表

**User Story:** 作为审计项目组成员，我想编辑应收票据审定表，以便确定科目审定金额。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D1-1 审定表
2. THE Revenue_Cycle_System SHALL 在审定表中包含以下核心字段：科目名称、未审金额（从 trial_balance 自动取数）、审计调整借方、审计调整贷方、审定金额（公式计算）、差异说明
3. WHEN 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount
4. THE Revenue_Cycle_System SHALL 支持从审定表跳转到对应调整分录（ref_index chip→调整分录底稿）

#### Requirement G1-3: 附注披露

**User Story:** 作为审计项目组成员，我想编辑应收票据附注披露信息，以便确保附注完整准确。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 将 D1 的附注披露 sheet 路由到 disclosure_notes 模块（c-note-table componentType）
2. THE Revenue_Cycle_System SHALL 支持上市公司版本和国企版本两套附注模板的切换
3. WHEN 附注数据保存时，THE Revenue_Cycle_System SHALL 通过 disclosure_notes 模块统一管理附注内容

#### Requirement G1-4: 明细表与坏账

**User Story:** 作为审计项目组成员，我想编辑应收票据明细表和坏账准备明细，以便支持审定金额。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D1-2（原值明细按类）、D1-3（原值明细按客户）（含公式计算）
2. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D1-4（坏账准备明细）
3. THE Revenue_Cycle_System SHALL 在 D1-2/D1-3 明细表的 `address_registry` 中注册关键坐标（合计行、余额列）
4. WHILE D1-1 审定表金额与 D1-2 明细表合计金额不一致时，THE Revenue_Cycle_System SHALL 在审定表底部显示"⚠️ 审定表与明细表不平"警告


### G2: 应收账款 (D2)

**模板文件：**
- D2-1至D2-4 应收账款-审定表明细表（Leap-常规程序）.xlsx（11 sheet）
- D2-5 应收账款-分析程序（Leap应对措施-分析程序）.xlsx
- D2-6至D2-13 应收账款-检查（Leap应对措施-检查）.xlsx

**Sheet 结构（D2-1至D2-4）：**
- 底稿目录 / 程序表D2A / 审定表D2-1 / 附注披露（上市/国企）/ 明细表D2-2 / 账龄分析D2-3 / 坏账准备D2-4

**需求点：**

#### Requirement G2-1: D2A 程序表

**User Story:** 作为审计项目组成员，我想执行应收账款实质性程序，以便对这一重要科目获取充分证据。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D2A 程序表
2. THE Revenue_Cycle_System SHALL 从 xlsx 模板提取 D2A 全部程序步骤
3. THE Revenue_Cycle_System SHALL 在程序表中通过 `auto_data_source: "risk_for_cycle"` 展示 B50 风险评估结论
4. THE Revenue_Cycle_System SHALL 在程序表中通过 `auto_data_source: "control_test_result_for_cycle"` 展示 C2 控制测试结论
5. THE Revenue_Cycle_System SHALL 在程序表中包含 ref_index chip 跳转到 D0（函证）、D2-1~D2-4（常规）、D2-5（分析）、D2-6~D2-13（检查）

#### Requirement G2-2: D2-1 审定表 + D2-2~D2-4 明细

**User Story:** 作为审计项目组成员，我想编辑应收账款审定表及明细，以便确定科目审定金额。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D2-1 审定表
2. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D2-2（明细表）、D2-3（账龄分析）（含公式+排序）
3. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D2-4（坏账准备明细）
4. WHEN D2-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount

#### Requirement G2-3: D2-5 分析程序

**User Story:** 作为审计项目组成员，我想对应收账款执行分析性程序，以便识别异常波动。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D2-5 分析程序底稿
2. THE Revenue_Cycle_System SHALL 在 D2-5 的 `address_registry` 中注册结论坐标
3. THE Revenue_Cycle_System SHALL 支持从 trial_balance 自动取数填充分析基础数据

#### Requirement G2-4: D2-6~D2-13 检查程序

**User Story:** 作为审计项目组成员，我想对应收账款抽样执行检查程序，以便验证交易真实性。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D2-6至D2-13 检查底稿（单文件多 sheet）
2. THE Revenue_Cycle_System SHALL 在 `address_registry` 中注册各检查 sheet 的结论坐标
3. THE Revenue_Cycle_System SHALL 支持检查结果汇总回写到 D2A 程序表对应步骤


### G3: 预收账款 (D3)

**模板文件：** D3 预收账款.xlsx

**需求点：**

#### Requirement G3-1: D3 全套

**User Story:** 作为审计项目组成员，我想编辑预收账款实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D3A 程序表
2. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D3-1 审定表
3. THE Revenue_Cycle_System SHALL 将 D3 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN D3-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` 或 `d-form-table` 渲染 D3 明细表


### G4: 营业收入 (D4)

**模板文件（7 xlsx，合计 60+ sheet）：**
- D4-1至D4-4 营业收入-审定表明细表（Leap-常规程序）.xlsx
- D4-5 营业收入-会计政策（Leap-常规程序）.xlsx
- D4-6至D4-11 营业收入-分析程序（Leap应对措施-分析程序）.xlsx
- D4-12 营业收入-合同检查（Leap-常规程序）.xlsx
- D4-13至D4-20 主营业务收入-检查（Leap应对措施-检查）.xlsx
- D4-21 营业收入-关联方检查（Leap-常规程序）.xlsx
- D4-22至D4-32 营业收入-IPO上市新三板重组舞弊应对.xlsx
- D4-33至D4-36 其他业务收入.xlsx

**需求点：**

#### Requirement G4-1: D4A 程序表

**User Story:** 作为审计项目组成员，我想执行营业收入实质性程序，以便对收入认定获取充分证据。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D4A 程序表
2. THE Revenue_Cycle_System SHALL 从 xlsx 模板提取 D4A 全部程序步骤
3. THE Revenue_Cycle_System SHALL 在程序表中包含 ref_index chip 跳转到全部 D4 子底稿（D4-1~D4-36）
4. THE Revenue_Cycle_System SHALL 在程序表中展示 B50 风险评估结论和 C2 控制测试结论

#### Requirement G4-2: D4-1 审定表 + D4-2~D4-4 明细

**User Story:** 作为审计项目组成员，我想编辑营业收入审定表及明细，以便确定收入审定金额。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D4-1 审定表
2. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D4-2（收入明细按类别）、D4-3（收入明细按客户）、D4-4（收入明细按月份）
3. WHEN D4-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount

#### Requirement G4-3: D4-5 会计政策检查

**User Story:** 作为审计项目组成员，我想检查营业收入会计政策的合规性，以便确认收入确认方法适当。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D4-5 会计政策检查底稿
2. THE Revenue_Cycle_System SHALL 在 D4-5 中包含收入确认五步法的各步骤检查字段

#### Requirement G4-4: D4-6~D4-11 分析程序

**User Story:** 作为审计项目组成员，我想对营业收入执行多维度分析程序，以便识别收入异常波动。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D4-6至D4-11 分析程序底稿
2. THE Revenue_Cycle_System SHALL 在 `address_registry` 中注册各分析 sheet 的结论坐标
3. THE Revenue_Cycle_System SHALL 支持从 trial_balance 和 tb_ledger 自动取数填充分析基础

#### Requirement G4-5: D4-12 合同检查 + D4-13~D4-20 收入检查

**User Story:** 作为审计项目组成员，我想对营业收入执行合同检查和交易检查，以便验证收入真实性和截止。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D4-12 合同检查底稿
2. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D4-13至D4-20 检查底稿
3. THE Revenue_Cycle_System SHALL 在 `address_registry` 中注册检查底稿的结论坐标

#### Requirement G4-6: D4-21 关联方检查

**User Story:** 作为审计项目组成员，我想检查关联方收入交易，以便确认关联交易合规披露。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D4-21 关联方检查底稿
2. THE Revenue_Cycle_System SHALL 通过 `auto_data_source: "related_party_transactions"` 自动拉取关联方交易数据
3. THE Revenue_Cycle_System SHALL 在 D4-21 中显示关联方交易金额与 D4-1 收入占比

#### Requirement G4-7: D4-22~D4-32 IPO/舞弊应对

**User Story:** 作为审计项目组成员，我想执行 IPO/上市/新三板/重组项目的收入舞弊应对程序，以便满足特殊监管要求。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D4-22至D4-32 底稿
2. WHERE 项目类型为 IPO/上市/新三板/重组时，THE Revenue_Cycle_System SHALL 自动标记 D4-22~D4-32 为"适用"
3. WHERE 项目类型为普通年审时，THE Revenue_Cycle_System SHALL 自动标记 D4-22~D4-32 为"不适用"并灰显

#### Requirement G4-8: D4-33~D4-36 其他业务收入

**User Story:** 作为审计项目组成员，我想编辑其他业务收入底稿，以便完成全部收入审计。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `d-form-table` 或 `audit-sheet` componentType 渲染 D4-33至D4-36 底稿
2. THE Revenue_Cycle_System SHALL 在 D4A 程序表中为其他业务收入步骤提供 ref_index chip 跳转到 D4-33~D4-36


### G5: 应收款项融资 (D5)

**模板文件：** D5 应收款项融资.xlsx

**需求点：**

#### Requirement G5-1: D5 全套

**User Story:** 作为审计项目组成员，我想编辑应收款项融资实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D5A 程序表
2. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D5-1 审定表
3. THE Revenue_Cycle_System SHALL 将 D5 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN D5-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` 渲染 D5 明细表/减值测算（含公式）


### G6: 合同资产 (D6)

**模板文件：** D6 合同资产.xlsx（已有 generated/D6.yaml 详细结构）

**Sheet 结构（from generated schema）：**
- 底稿目录 / 程序表D6A / 程序表D7A（原）/ 审定表D6-1 / 明细表D6-2 / 减值准备明细D6-3 / 调整分录汇总D6-4 / 关联关系及交易检查D6-5 / 检查表D6-6 / 减值准备会计政策检查D6-7 / 减值准备测算D6-8 / 减值准备转回核销检查D6-9

**需求点：**

#### Requirement G6-1: D6 全套

**User Story:** 作为审计项目组成员，我想编辑合同资产实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D6A 程序表
2. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 D6-1（审定表）、D6-2（明细表）、D6-3（减值准备明细）、D6-8（减值测算）——这些含复杂公式
3. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D6-6（检查表）、D6-9（转回核销检查）——结构化逐项检查
4. THE Revenue_Cycle_System SHALL 使用 `d-form-paragraph` componentType 渲染 D6-7（会计政策检查）——段落式文本
5. THE Revenue_Cycle_System SHALL 在 `address_registry` 中注册 D6 各 sheet 关键坐标
6. WHEN D6-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount


### G7: 合同负债 (D7)

**模板文件：** D7 合同负债.xlsx

**需求点：**

#### Requirement G7-1: D7 全套

**User Story:** 作为审计项目组成员，我想编辑合同负债实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Revenue_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 D7A 程序表
2. THE Revenue_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 D7-1 审定表
3. THE Revenue_Cycle_System SHALL 将 D7 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN D7-1 审定表保存时，THE Revenue_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Revenue_Cycle_System SHALL 使用 `audit-sheet` 或 `d-form-table` 渲染 D7 明细表


## 6. 跨模块联动矩阵

| 源 | 目标 | 联动数据 | 方向 | 状态 |
|----|------|---------|------|------|
| B50-3 认定层次风险 | D{n}A 程序表 | 已识别风险展示 | B→D（读取） | ✅ 就绪 |
| C2 控制测试结论 | D{n}A 程序表 | 控制测试有效性 | C→D（读取） | ✅ 就绪 |
| D{n}-1 审定表 | trial_balance.audited_amount | 审定金额回写 | D→全局（写入） | 🔴 需补 |
| D{n} 附注 sheet | disclosure_notes 模块 | 附注内容 | D→全局（路由） | ✅ 已有 |
| D0 函证 | ConfirmationHub | 函证流程 | D→全局（路由） | ✅ 已有 |
| D4-21 关联方 | related_party_transactions | 关联交易数据 | 全局→D（读取） | 🔴 需补 |
| D 各检查/分析结论 | D{n}A 程序表步骤 | 结论回写 | D→D（内部） | 🔴 需补 |
| D{n}-1 审定表 | A1-13 错报汇总 | 审计差异 | D→A（读取） | ✅ 已有路径 |

## 7. 技术约束

### 7.1 wp_code 注册规则

1. D 类底稿 wp_code 以 `D` 开头
2. 现有 13 条需扩充到完整覆盖（估计 50~60 条）
3. 子底稿规则：
   - D{n}A：实质性程序表（每个科目一个）
   - D{n}-1：审定表
   - D{n}-2~：明细表/坏账/检查/分析
   - D0-1~D0-5：函证辅助 sheet
4. D4 因营业收入结构最复杂，子码最多（D4-1~D4-36）

### 7.2 componentType 分配原则

| sheet 类型 | componentType | 判定依据 |
|-----------|---------------|---------|
| 程序表（D{n}A） | `a-program-console` | 有序号/步骤/执行人/结论 |
| 审定表（D{n}-1）| `d-form-table` | 结构化表单+联动取数 |
| 附注披露 | `c-note-table`（disclosure_notes 路由） | 附注统一管理 |
| 明细表（含公式/大数据量）| `audit-sheet` | OnlyOffice 处理公式 |
| 检查表（逐项结构化）| `d-form-table` | 逐行填写+enum 字段 |
| 分析程序（含公式/图表）| `audit-sheet` | 复杂计算+可视化 |
| 会计政策检查 | `d-form-paragraph` | 段落式文本描述 |
| 底稿目录 | 不渲染 | 平台自动生成导航 |
| 选项清单/示例 | 不渲染 | VBA 替代/参考不开发 |

### 7.3 审定表→trial_balance 回写

D 类审定表是 trial_balance.audited_amount 的写入源。回写逻辑：
1. D{n}-1 保存时触发 EventBus `WORKPAPER_SAVED`
2. handler 识别 wp_code 为审定表类型
3. 从 parsed_data 提取各科目审定金额
4. UPDATE trial_balance SET audited_amount = X WHERE project_id AND year AND standard_account_code

### 7.4 D4 特殊适用性

D4-22~D4-32（IPO/舞弊应对）通过 `applicable_when` 字段控制：
- `business_category IN ('ipo', 'listed', 'neeq', 'restructuring')` → 适用
- 普通年审 → 自动标记不适用

### 7.5 导入导出

1. 程序表（D{n}A）：标准程序表导出
2. 审定表（D{n}-1）：d-form-table 通用导出
3. 明细表/分析/检查（audit-sheet）：OnlyOffice 原生导出
4. 支持从 Excel 导入填充已有结构化底稿
5. 批量导出：项目归档时 D 类全量打包 zip

## 8. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：扩充 wp_account_mapping 到完整 D 类 wp_code + _WP_CODE_OVERRIDE 全量映射 | 必做 | 无 |
| P1 | 程序表：D0A~D7A 程序表模板提取 + 注册 procedure_table_templates.json | 必做 | P0 |
| P2 | 审定表+联动：D{n}-1 审定表 schema 确认 + audited_amount 回写 handler | 必做 | P0 |
| P3 | OnlyOffice 底稿：明细表/分析/检查 address_registry 坐标注册 | 必做 | P0 |
| P4 | D4 营业收入：最大子集的完整覆盖（D4-1~D4-36） | 必做 | P0 |
| P5 | 联动完善：D→trial_balance 回写 + 关联方取数 + 检查结论回写 | 增强 | P2 |
| P6 | 导入导出 + E2E | 必做 | P1~P4 |

## 9. B/C 经验教训应用

| # | 经验 | D 类应对 |
|---|------|---------|
| 1 | wp_code 注册不完整 | P0 一次性扩充全部 D 类子码（估计 50+） |
| 2 | componentType 映射遗漏 | P0 在 _WP_CODE_OVERRIDE 显式映射每个 wp_code |
| 3 | VBA 选项清单 sheet 不渲染 | 底稿目录/选项清单/示例 sheet 统一标记不渲染 |
| 4 | OnlyOffice 底稿必须地址坐标落位 | P3 阶段所有 audit-sheet 底稿强制 address_registry 注册 |
| 5 | 联动链完整 | B50→D + C2→D 读取就绪，补 D→trial_balance 写入 |
| 6 | 导入导出同步规划 | P6 独立 Phase |
| 7 | 通用 schema 复用 | D 类各科目结构相似度不够高（D6 有 9 sheet，D3 只有几个），不适合统一 generic schema，按科目独立配置 |
