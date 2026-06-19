# F 类底稿（采购存货循环）— 需求文档

## 1. 概述

F 类底稿覆盖"实质性程序—采购与存货循环"阶段（审计循环代号 F），是 C 类控制测试结论的后续应对——根据 B50 风险评估结果和 C4 控制测试结论，执行实质性程序以获取采购与存货相关科目的充分适当审计证据。包含 **5 大科目组 + 1 函证组、15 个模板文件、约 80+ 个子底稿 sheet**。

F 类是本平台最复杂的循环底稿，F2（存货）单科目即有 72+ 子底稿覆盖审定/明细/政策/分析/盘点/检查/计价/跌价/关联/IPO。

本 spec 目标：**补全 F 类底稿的完整注册、componentType 映射、程序表提取、特殊程序（存货监盘/跌价估计）、联动实现**。

## 2. 现状与差距

### 2.1 已有实现

| 维度 | 现状 | 说明 |
|------|------|------|
| wp_account_mapping | 8 条（F0/F1/F2/F3/F4/F5/F1-2/F1-3/F4-2） | 缺大量子码 |
| generated YAML schema | 待查 | 可能已有部分 |
| _WP_CODE_OVERRIDE | 0 条 | F 类无显式 componentType 映射 |
| ConfirmationHub | F0 函证可路由到已有模块 | confirmation_service 共用 |
| risk_for_cycle | B50→F 风险读取就绪 | auto_data_resolvers 已注册 |
| control_test_result_for_cycle | C4→F 控制测试结论读取就绪 | auto_data_resolvers 已注册 |

### 2.2 待补缺口

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| F1 子码缺失（F1-1~F1-10+ 约 10 子底稿） | 预付账款底稿无法路由 | P0 |
| F2 子码严重缺失（F2-1~F2-72 约 70 子底稿） | 存货最复杂科目无法精确路由 | P0 |
| F3/F4/F5 子码缺失 | 应付票据/账款/成本子底稿不全 | P0 |
| _WP_CODE_OVERRIDE 全空 | render-config 走 fallback 路径 | P0 |
| F{n}A 程序表未提取模板 | 程序表步骤不在 procedure_table_templates.json | P1 |
| F2 存货监盘（F2-21~26）特殊程序 | 盘点底稿有独特结构 | P4 |
| F2 跌价准备（F2-47~49）涉及会计估计 | 需联动 B51 舞弊三因素 | P4 |
| F 审定表→trial_balance 联动 | audited_amount 回写 | P2 |
| address_registry 未注册 | OnlyOffice 底稿孤立 | P3 |

## 3. 术语表（Glossary）

- **采购存货循环系统（Procurement_Inventory_System）**：平台中负责 F 类底稿渲染、编辑、联动的子系统
- **审定表（Audit_Determination_Table）**：F{n}-1 系列，记录科目审定金额+调整分录汇总
- **实质性程序表（Substantive_Procedure_Table）**：F{n}A 系列，列出该科目的具体审计程序步骤
- **明细表（Detail_Schedule）**：F{n}-2+ 系列，按维度展开科目余额明细
- **存货监盘（Inventory_Count）**：F2-21~F2-26 系列，记录存货盘点观察与测试结果
- **计价测试（Valuation_Test）**：F2-38~F2-44 系列，验证存货成本计算正确性
- **跌价准备测试（Impairment_Test）**：F2-47~F2-49 系列，评估存货跌价准备的合理性（会计估计）
- **函证（Confirmation）**：F0 系列，向供应商确认应付余额
- **合同履约成本（Contract_Performance_Cost）**：F2-55~F2-58 系列，新收入准则下合同成本资本化

## 4. F 类底稿分组结构

| 组 | 编号范围 | 功能 | 模板文件 | componentType |
|----|---------|------|---------|---------------|
| G0 | F0/F0A/F0-1~F0-5 | 存货循环函证 | 1 xlsx | ConfirmationHub + `d-form-table` |
| G1 | F1/F1A/F1-1~F1-10 | 预付账款 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table`/`audit-sheet` |
| G2 | F2/F2A/F2-1~F2-72 | 存货及跌价准备 | 11 xlsx(合计~72 sheet) | 程序表=`a-program-console`，审定/明细=`d-form-table`/`audit-sheet`，盘点=`inventory-count`/`audit-sheet`，计价/跌价/分析/检查/IPO=`audit-sheet` |
| G3 | F3/F3A/F3-1~F3-6 | 应付票据 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table`/`audit-sheet` |
| G4 | F4/F4A/F4-1~F4-6 | 应付账款 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table`/`audit-sheet` |
| G5 | F5/F5A/F5-1~F5-6 | 营业成本 | 1 xlsx | 程序表=`a-program-console`，审定/明细=`d-form-table`/`audit-sheet` |

## 5. 各组详细需求

### G0: 存货循环函证 (F0)

**模板文件：** F0 存货循环函证.xlsx

**Sheet 结构（推测）：**
- 底稿目录 / 函证程序表F0A / 函证结果汇总F0-1 / 核实被函证单位F0-2 / 跟函控制F0-3 / 差异调节F0-4 / 替代程序F0-5

**需求点：**

#### Requirement G0-1: ConfirmationHub 集成

**User Story:** 作为审计项目组成员，我想通过平台已有的函证模块管理采购循环函证，以便统一管理供应商函证流程。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 将 F0 底稿的核心函证功能路由到已有的 ConfirmationHub 模块
2. THE Procurement_Inventory_System SHALL 在 F0A 程序表中通过 ref_index chip 跳转到 ConfirmationHub 对应函证批次
3. WHEN 用户打开 F0 底稿时，THE Procurement_Inventory_System SHALL 显示该项目 F 循环的函证摘要
4. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F0-1~F0-5 辅助 sheet
5. THE Procurement_Inventory_System SHALL 不渲染"示例"类 sheet

#### Requirement G0-2: F0A 函证程序表

**User Story:** 作为审计项目组成员，我想执行采购循环函证程序表中的步骤。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F0A 函证程序表
2. THE Procurement_Inventory_System SHALL 从 xlsx 模板提取 F0A 全部程序步骤，注册到 procedure_table_templates.json
3. THE Procurement_Inventory_System SHALL 在程序表步骤中包含 ref_index chip 跳转到 F0-1~F0-5 各辅助底稿


### G1: 预付账款 (F1)

**模板文件：** F1 预付账款.xlsx

**Sheet 结构（推测）：**
- 底稿目录 / 程序表F1A / 审定表F1-1 / 附注披露 / 明细表F1-2 / 账龄分析F1-3 / 坏账准备F1-4 / 调整分录汇总F1-5 / 检查表F1-6

**需求点：**

#### Requirement G1-1: F1A 程序表

**User Story:** 作为审计项目组成员，我想执行预付账款实质性程序，以便获取科目审计证据。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F1A 程序表
2. THE Procurement_Inventory_System SHALL 从 xlsx 模板提取 F1A 全部程序步骤
3. THE Procurement_Inventory_System SHALL 在程序表中通过 `auto_data_source: "risk_for_cycle"` 展示 B50 对应风险评估结论
4. THE Procurement_Inventory_System SHALL 在程序表中通过 `auto_data_source: "control_test_result_for_cycle"` 展示 C4 控制测试结论

#### Requirement G1-2: F1-1 审定表 + 明细

**User Story:** 作为审计项目组成员，我想编辑预付账款审定表及明细，以便确定科目审定金额。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F1-1 审定表
2. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F1-2（明细表）、F1-3（账龄分析）
3. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F1-4（坏账准备）
4. WHEN F1-1 审定表保存时，THE Procurement_Inventory_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Procurement_Inventory_System SHALL 将 F1 附注披露 sheet 路由到 disclosure_notes 模块


### G2: 存货及跌价准备 (F2) — 最复杂科目

**模板文件（11 xlsx，合计 72+ sheet）：**
- F2-1至F2-14 存货及跌价准备-审定明细表类.xlsx
- F2-16 存货及跌价准备-会计政策.xlsx
- F2-18至F2-20 存货-分析类.xlsx
- F2-21至F2-26 存货-盘点类.xlsx
- F2-29至F2-35 存货-检查类.xlsx
- F2-38至F2-44 存货-计价测试.xlsx
- F2-47至F2-49 存货-跌价准备测试.xlsx
- F2-52 存货-关联交易.xlsx
- F2-55至F2-58 合同履约成本.xlsx
- F2-61至F2-72 存货-IPO舞弊应对.xlsx

**Sheet 结构（F2-1至F2-14 审定明细）：**
- 底稿目录 / 程序表F2A / 审定表F2-1 / 附注披露（上市/国企）/ 存货分类明细F2-2 / 存货增减变动F2-3 / 原材料明细F2-4 / 在产品明细F2-5 / 库存商品明细F2-6 / 在途物资明细F2-7 / 委托加工F2-8 / 工程施工F2-9 / 开发产品F2-10 / 跌价准备明细F2-11 / 跌价准备变动F2-12 / 调整分录汇总F2-13 / 存货担保/质押F2-14

**需求点：**

#### Requirement G2-1: F2A 程序表

**User Story:** 作为审计项目组成员，我想执行存货实质性程序，以便对存货认定获取充分证据。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F2A 程序表
2. THE Procurement_Inventory_System SHALL 从 xlsx 模板提取 F2A 全部程序步骤
3. THE Procurement_Inventory_System SHALL 在程序表中包含 ref_index chip 跳转到全部 F2 子底稿（F2-1~F2-72）
4. THE Procurement_Inventory_System SHALL 在程序表中展示 B50 风险评估结论和 C4 控制测试结论

#### Requirement G2-2: F2-1 审定表 + F2-2~F2-14 明细

**User Story:** 作为审计项目组成员，我想编辑存货审定表及各类明细，以便确定存货审定金额。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F2-1 审定表
2. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-2~F2-10（各类存货明细，含公式/多维度）
3. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F2-11（跌价准备明细）、F2-12（跌价变动）
4. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F2-13（调整分录汇总）、F2-14（担保质押）
5. WHEN F2-1 审定表保存时，THE Procurement_Inventory_System SHALL 将审定金额回写到 trial_balance.audited_amount

#### Requirement G2-3: F2-16 会计政策检查

**User Story:** 作为审计项目组成员，我想检查存货会计政策的合规性，以便确认成本计价方法适当。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F2-16 会计政策检查底稿
2. THE Procurement_Inventory_System SHALL 在 F2-16 中包含存货计价方法（先进先出/加权平均/个别计价）检查字段

#### Requirement G2-4: F2-18~F2-20 分析程序

**User Story:** 作为审计项目组成员，我想对存货执行分析性程序，以便识别异常波动。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-18至F2-20 分析程序底稿
2. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册各分析 sheet 的结论坐标
3. THE Procurement_Inventory_System SHALL 支持从 trial_balance 自动取数填充分析基础数据

#### Requirement G2-5: F2-21~F2-26 存货监盘（特殊程序）

**User Story:** 作为审计项目组成员，我想使用存货监盘底稿记录盘点观察与测试结果，以便验证存货存在性。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-21（监盘计划）、F2-22（盘点观察记录）、F2-23（盘点抽盘测试）
2. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-24（存货截止测试）、F2-25（盘点差异汇总）、F2-26（监盘结论）
3. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册 F2-21~F2-26 各 sheet 关键坐标（盘点日期/仓库/差异金额/结论）
4. THE Procurement_Inventory_System SHALL 支持盘点结果汇总回写到 F2A 程序表对应步骤
5. THE Procurement_Inventory_System SHALL 在 F2-25 差异汇总中支持自动计算盘盈盘亏金额

#### Requirement G2-6: F2-29~F2-35 检查程序

**User Story:** 作为审计项目组成员，我想对存货执行检查程序，以便验证存货交易真实性和计价。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-29至F2-35 检查底稿
2. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册各检查 sheet 的结论坐标
3. THE Procurement_Inventory_System SHALL 支持检查结果汇总回写到 F2A 程序表对应步骤

#### Requirement G2-7: F2-38~F2-44 计价测试

**User Story:** 作为审计项目组成员，我想执行存货计价测试，以便验证存货成本计算正确性。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-38至F2-44 计价测试底稿（含成本还原公式）
2. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册计价测试结论坐标
3. THE Procurement_Inventory_System SHALL 支持不同计价方法（加权平均/先进先出/个别计价）的测算模板

#### Requirement G2-8: F2-47~F2-49 跌价准备测试（会计估计）

**User Story:** 作为审计项目组成员，我想执行存货跌价准备测试，以便评估管理层会计估计的合理性。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-47至F2-49 跌价准备测试底稿
2. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册跌价准备测试结论坐标
3. THE Procurement_Inventory_System SHALL 通过 `auto_data_source: "accounting_estimate_b51"` 读取 B51 舞弊三因素评估结论
4. WHEN 跌价准备测试结论保存时，THE Procurement_Inventory_System SHALL 更新 F2-11/F2-12 跌价准备明细表的结论字段

#### Requirement G2-9: F2-52 关联交易检查

**User Story:** 作为审计项目组成员，我想检查存货相关关联交易，以便确认关联交易合规披露。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F2-52 关联交易检查底稿
2. THE Procurement_Inventory_System SHALL 通过 `auto_data_source: "related_party_transactions"` 自动拉取关联方交易数据

#### Requirement G2-10: F2-55~F2-58 合同履约成本

**User Story:** 作为审计项目组成员，我想编辑合同履约成本底稿，以便审计新收入准则下的合同成本资本化。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-55至F2-58 合同履约成本底稿
2. THE Procurement_Inventory_System SHALL 在 `address_registry` 中注册合同履约成本结论坐标
3. THE Procurement_Inventory_System SHALL 支持合同履约成本摊销测试的公式计算

#### Requirement G2-11: F2-61~F2-72 IPO/舞弊应对

**User Story:** 作为审计项目组成员，我想执行存货 IPO/舞弊应对程序，以便满足特殊监管要求。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` componentType 渲染 F2-61至F2-72 底稿
2. WHERE 项目类型为 IPO/上市/新三板/重组时，THE Procurement_Inventory_System SHALL 自动标记 F2-61~F2-72 为"适用"
3. WHERE 项目类型为普通年审时，THE Procurement_Inventory_System SHALL 自动标记 F2-61~F2-72 为"不适用"并灰显


### G3: 应付票据 (F3)

**模板文件：** F3 应付票据.xlsx

**需求点：**

#### Requirement G3-1: F3 全套

**User Story:** 作为审计项目组成员，我想编辑应付票据实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F3A 程序表
2. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F3-1 审定表
3. THE Procurement_Inventory_System SHALL 将 F3 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN F3-1 审定表保存时，THE Procurement_Inventory_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` 渲染 F3 明细表（含公式）
6. THE Procurement_Inventory_System SHALL 使用 `d-form-table` 渲染 F3 检查表


### G4: 应付账款 (F4)

**模板文件：** F4 应付账款.xlsx

**需求点：**

#### Requirement G4-1: F4 全套

**User Story:** 作为审计项目组成员，我想编辑应付账款实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F4A 程序表
2. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F4-1 审定表
3. THE Procurement_Inventory_System SHALL 将 F4 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN F4-1 审定表保存时，THE Procurement_Inventory_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` 渲染 F4-2（应付账款明细表）、F4-3（账龄分析）
6. THE Procurement_Inventory_System SHALL 使用 `d-form-table` 渲染 F4-4（调整分录汇总）
7. THE Procurement_Inventory_System SHALL 在程序表中展示 B50 风险评估结论和 C4 控制测试结论


### G5: 营业成本 (F5)

**模板文件：** F5 营业成本.xlsx

**需求点：**

#### Requirement G5-1: F5 全套

**User Story:** 作为审计项目组成员，我想编辑营业成本实质性程序底稿，以便完成该科目审计。

**Acceptance Criteria:**

1. THE Procurement_Inventory_System SHALL 使用 `a-program-console` componentType 渲染 F5A 程序表
2. THE Procurement_Inventory_System SHALL 使用 `d-form-table` componentType 渲染 F5-1 审定表
3. THE Procurement_Inventory_System SHALL 将 F5 附注披露 sheet 路由到 disclosure_notes 模块
4. WHEN F5-1 审定表保存时，THE Procurement_Inventory_System SHALL 将审定金额回写到 trial_balance.audited_amount
5. THE Procurement_Inventory_System SHALL 使用 `audit-sheet` 渲染 F5 明细表（含成本结转公式）
6. THE Procurement_Inventory_System SHALL 在 F5A 程序表中包含 ref_index chip 跳转到 F2（存货联动）


## 6. 跨模块联动矩阵

| 源 | 目标 | 联动数据 | 方向 | 状态 |
|----|------|---------|------|------|
| B23-4/B23-5 穿行测试 | C4 控制测试 | 设计有效性结论 | B→C→F（读取） | ✅ `_on_b23_saved` |
| B50-3 认定层次风险 | F{n}A 程序表 | 已识别风险展示 | B→F（读取） | ✅ 就绪 |
| C4 控制测试结论 | F{n}A 程序表 | 控制测试有效性 | C→F（读取） | ✅ 就绪 |
| F{n}-1 审定表 | trial_balance.audited_amount | 审定金额回写 | F→全局（写入） | 🔴 需补 |
| F{n} 附注 sheet | disclosure_notes 模块 | 附注内容 | F→全局（路由） | ✅ 复用 |
| F0 函证 | ConfirmationHub | 函证流程 | F→全局（路由） | ✅ 已有 |
| F2-52 关联方 | related_party_transactions | 关联交易数据 | 全局→F（读取） | ✅ 已有 |
| F2-47~49 跌价 | B51 舞弊三因素 | 会计估计风险 | B→F（读取） | 🔴 需补 |
| F 各检查/分析结论 | F{n}A 程序表步骤 | 结论回写 | F→F（内部） | 🔴 需补 |
| F{n}-1 审定表 | A1-13 错报汇总 | 审计差异 | F→A（读取） | ✅ 已有路径 |
| F5 营业成本 | F2 存货 | 成本结转联动 | F→F（内部） | 🔴 需补 |

## 7. 技术约束

### 7.1 wp_code 注册规则

1. F 类底稿 wp_code 以 `F` 开头
2. 现有 8 条需扩充到完整覆盖（估计 80 条）
3. 子底稿规则：
   - F{n}A：实质性程序表（每个科目一个）
   - F{n}-1：审定表
   - F1-2~F1-6：预付账款明细/检查
   - F2-1~F2-14：存货审定+明细
   - F2-16：会计政策
   - F2-18~F2-20：分析
   - F2-21~F2-26：盘点
   - F2-29~F2-35：检查
   - F2-38~F2-44：计价
   - F2-47~F2-49：跌价
   - F2-52：关联交易
   - F2-55~F2-58：合同履约成本
   - F2-61~F2-72：IPO
   - F3-1~F3-6：应付票据
   - F4-1~F4-6：应付账款
   - F5-1~F5-6：营业成本
   - F0-1~F0-5：函证辅助

### 7.2 componentType 分配原则

| sheet 类型 | componentType | 判定依据 |
|-----------|---------------|---------|
| 程序表（F{n}A） | `a-program-console` | 有序号/步骤/执行人/结论 |
| 审定表（F{n}-1）| `d-form-table` | 结构化表单+联动取数 |
| 附注披露 | `c-note-table`（disclosure_notes 路由） | 附注统一管理 |
| 简单明细/坏账/调整分录/关联方 | `d-form-table` | 逐行填写+enum 字段 |
| 复杂明细/分析/检查/盘点/计价/跌价/IPO | `audit-sheet` | 含公式/大数据量/多 sheet |
| 会计政策检查 | `d-form-table` | 结构化政策检查字段 |
| 底稿目录 | 不渲染 | 平台自动生成导航 |
| 选项清单/示例 | 不渲染 | 参考不开发 |

### 7.3 审定表→trial_balance 回写

复用统一 handler，F1-1/F2-1/F3-1/F4-1/F5-1 保存时触发回写。正则 `^F\d+-1$` 匹配。

### 7.4 IPO 适用性

F2-61~F2-72 通过 `applicable_when` 字段控制（与 D4-22/E1-26 相同模式）。

### 7.5 存货监盘特殊性

F2-21~F2-26 为存货监盘系列底稿，结构特殊：
- F2-21 监盘计划（仓库/日期/人员/范围）
- F2-22 盘点观察记录（逐项记录盘点过程）
- F2-23 抽盘测试（从存货记录→实物 / 从实物→记录 双向）
- F2-24 截止测试（最后入库单/出库单号）
- F2-25 差异汇总（盘盈盘亏金额）
- F2-26 监盘结论

均使用 `audit-sheet` componentType（含公式+表格+双向抽盘特殊结构）。

### 7.6 跌价准备与会计估计联动

F2-47~F2-49 涉及会计估计审计：
- 需读取 B51 舞弊三因素评估（管理层偏向/估计不确定性/复杂性）
- 跌价准备测试结论影响 F2-11/F2-12 明细
- auto_data_source: `accounting_estimate_b51` 需新增

### 7.7 导入导出

1. 程序表（F{n}A）：标准程序表导出
2. 审定表（F{n}-1）：d-form-table 通用导出
3. 明细表/分析/检查/盘点/计价/跌价/IPO：OnlyOffice 原生导出
4. 支持从 Excel 导入
5. 批量导出：项目归档时 F 类全量打包 zip

## 8. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：扩充 wp_account_mapping 到完整 F 类 wp_code (~80条) + _WP_CODE_OVERRIDE 全量映射 | 必做 | 无 |
| P1 | 程序表：F0A~F5A 共 6 个程序表模板提取 + 注册 | 必做 | P0 |
| P2 | 审定表+联动：F{n}-1 审定表 schema + audited_amount 回写 | 必做 | P0 |
| P3 | OnlyOffice 底稿：address_registry 坐标注册 | 必做 | P0 |
| P4 | 特殊程序：F2-21~26 存货监盘 + F2-47~49 跌价估计 + F2-38~44 计价测试 | 必做 | P0 |
| P5* | 联动完善：F→trial_balance + B51→F2跌价 + F5↔F2成本结转 | 增强 | P2 |
| P6 | 导入导出 + E2E | 必做 | P1~P4 |

## 9. 跨循环依赖提示

> 📌 **全局交叉索引**：`.kiro/specs/CYCLE-CROSS-REFERENCE.md`

- **前置依赖**：D 类 P0~P2 已完成（F 复用审定表回写 handler）
- **B23 穿行编号**：F 对应 B23-4（采购循环）+ B23-5（存货/生产循环）
- **C 类编号**：F 对应 C4（采购付款控制），非 C3
- **完整链路**：B23-4/5 穿行→C4 控制测试→F{n}A 实质性程序表
- **后续被依赖**：F5 营业成本→M6 未分配利润（经净利润汇总）；F2-47 跌价→需 B51 就绪
- **内部科目联动**：F5 营业成本↔F2 存货 成本结转需在 P5 阶段实现
- **会计估计关键路径**：F2-47~49 跌价准备→B51 舞弊三因素（需 `accounting_estimate_b51` resolver）

## 10. B/C/D 经验教训应用

| # | 经验 | F 类应对 |
|---|------|---------|
| 1 | wp_code 注册不完整 | P0 一次性扩充全部 F 类子码（~80 条，F2 最多） |
| 2 | componentType 映射遗漏 | P0 在 _WP_CODE_OVERRIDE 显式映射每个 wp_code |
| 3 | VBA 选项清单 sheet 不渲染 | 底稿目录/选项清单/示例 sheet 统一标记不渲染 |
| 4 | OnlyOffice 底稿必须地址坐标落位 | P3 阶段所有 audit-sheet 底稿强制 address_registry 注册 |
| 5 | 联动链完整 | B50→F + C4→F 读取就绪，补 F→trial_balance + B51→F2跌价 |
| 6 | D4-22 IPO 适用性模式复用 | F2-61~72 复用 applicable_when 机制 |
| 7 | 三表统一 HTML | 目录表自动导航、审定表 d-form-table、附注 c-note-table |
| 8 | 会计估计需联动风险评估 | F2 跌价准备新增 accounting_estimate_b51 读取 |
