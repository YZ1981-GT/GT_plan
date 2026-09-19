# S 类底稿（专项循环）— 需求文档

## 1. 概述

S 类底稿覆盖"专项"循环（审计循环代号 S），包含**特殊审计考虑事项和 IPO/上市专项核查**。与 D~N 循环不同，S 类不按科目分组，而是按**审计议题**分组。包含 **5 大类、90 个模板文件**。

S 类的特殊性：
1. **不按科目分组**——按审计议题/监管要求分组
2. **是数据消费者**——从 D~N 各循环审定结果读取数据，不是数据源
3. **无独立控制测试**——不存在 C 类对应测试（属于贯穿各循环的专项考虑）
4. **无函证组**——S 类不需要 confirmation-hub
5. **IPO 系列适用性**——S32~S35 仅 IPO/上市/新三板/再融资项目适用
6. **结构差异极大**——有程序表、检查表、计算表、.docx、.xls 等多种形态

本 spec 目标：**一次性注册全部 90 个 wp_code，分配 componentType，提取程序表，注册坐标，实现联动**。

## 2. 现状与差距

### 2.1 已有实现

| 维度 | 现状 | 说明 |
|------|------|------|
| wp_account_mapping | 0 条 | S 类完全未注册 |
| generated YAML schema | 0 个 | 无任何 S 类 schema |
| _WP_CODE_OVERRIDE | 0 条 | S 类无显式 componentType 映射 |
| pattern matching | 无 | 无 S 类规则 |
| ConfirmationHub | 不需要 | S 类无函证 |
| risk_for_cycle | 不适用 | S 类不对应单一风险评估 |
| control_test_result | 不适用 | S 类无控制测试 |

### 2.2 待补缺口

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| 90 个 wp_code 全部缺失 | S 类底稿完全无法打开 | P0 |
| _WP_CODE_OVERRIDE 全空 | render-config 无法路由 | P0 |
| 程序表未提取（S1~S16 系列） | 特殊审计考虑无步骤展示 | P1 |
| IPO 专项核查未注册（S32~S35） | IPO 项目核查底稿无法使用 | P2 |
| address_registry 未注册 | OnlyOffice 底稿无坐标落位 | P3 |
| .docx 文件未配置弹窗 | S12A/S33修订说明/S34-1-1 无法预览 | P4 |
| 联动（S→D~N 读取）未建立 | 专项核查无法取其他循环数据 | P5* |

## 3. 术语表（Glossary）

- **专项循环系统（Special_Cycle_System）**：平台中负责 S 类底稿渲染、编辑、联动的子系统
- **特殊审计考虑事项（Special_Audit_Consideration）**：S1~S16 系列，审计中需特别关注的议题
- **IPO 专项核查（IPO_Special_Verification）**：S32~S35 系列，首次公开发行/上市/再融资项目特有核查
- **证监会核查事项（CSRC_Verification_Items）**：S34 系列，证监会审核关注的 41 个专项事项
- **综合核查（Comprehensive_Verification）**：S33 系列，IPO 项目财务综合核查 9 项
- **程序表式底稿（Procedure_Program）**：含审计程序步骤的底稿，使用 a-program-console 渲染
- **逐项检查表（Checklist_Form）**：逐条核查条件并记录结论的底稿，使用 d-form-table 渲染
- **计算表（Calculation_Sheet）**：含公式/计算逻辑的底稿，使用 audit-sheet 渲染

## 4. S 类底稿分组结构

| 大类 | 编号范围 | 数量 | 功能 | 适用性 |
|------|---------|------|------|--------|
| S1~S16 | S1/S2/.../S16/S17 | 18 | 特殊审计考虑事项 | 所有项目 |
| S20~S21 | S20/S21 | 2 | 新准则底稿 | 所有项目 |
| S32 | S32-1~S32-13 | 13 | IPO 专项核查 | IPO/上市/新三板 |
| S33 | S33-1~S33-9 + 修订说明 | 10 | 综合核查 | IPO/上市/新三板 |
| S34 | S34-0~S34-41 + S34-1-1 | 43 | 证监会核查事项 | IPO/上市/新三板/再融资 |
| S35 | S35-1~S35-5 | 5 | 再融资核查 | 再融资 |
| **合计** | | **91** | | |

> 注：S7 无模板（已废止），实际 90 个文件。S12 含子文件 S12A。

## 5. 各大类详细需求

### 5.1 S1~S16: 特殊审计考虑事项

**模板文件（18 个）：**
- S1 违反法规行为的考虑.xlsx
- S2 首次接受委托期初余额.xlsx
- S3 会计政策变更/前期差错/估计变更.xlsx
- S4 非货币性资产交换.xlsx
- S5 债务重组.xlsx
- S6 大股东资金占用/违规担保.xlsx
- S8 租赁.xlsx
- S9 电子商务考虑.xlsx
- S10 环境事项考虑.xlsx
- S11 利用服务机构.xlsx
- S12 利用专家工作.xlsx + S12A 评估专家报告.docx
- S13 利用管理层专家.xlsx
- S14 会计估计和相关披露.xlsx
- S15 每股收益和净资产收益率.xlsx
- S16 套期活动.xlsx
- S17 非经常性损益.xls

#### Requirement S-SPECIAL-1: 程序表式底稿渲染

**User Story:** 作为审计项目组成员，我想执行特殊审计考虑事项程序表中的步骤，以便记录对各专项议题的考虑和结论。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `a-program-console` componentType 渲染以下含程序步骤的底稿：S1/S2/S3/S8/S10/S11/S13
2. THE Special_Cycle_System SHALL 从各 xlsx 模板提取程序表步骤结构，注册到 procedure_table_templates.json
3. THE Special_Cycle_System SHALL 在程序表中包含 ref_index chip 跳转到相关 D~N 循环底稿

#### Requirement S-SPECIAL-2: 检查表式底稿渲染

**User Story:** 作为审计项目组成员，我想逐项检查各专项事项的适用条件并记录结论。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染以下逐项检查式底稿：S4/S5/S6/S9/S12/S14/S16
2. THE Special_Cycle_System SHALL 在 d-form-table 中包含"适用/不适用"判断字段和结论填写区
3. THE Special_Cycle_System SHALL 支持检查项的"是/否/不适用"三态选择

#### Requirement S-SPECIAL-3: 计算表底稿渲染

**User Story:** 作为审计项目组成员，我想使用含公式的计算底稿验证每股收益等指标。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染以下含公式/计算的底稿：S15/S17
2. THE Special_Cycle_System SHALL 在 `address_registry` 中注册 S15（每股收益/净资产收益率结论）和 S17（非经常性损益合计）的关键坐标
3. THE Special_Cycle_System SHALL 支持 S15 从 trial_balance 读取净利润/股本数据自动填充

#### Requirement S-SPECIAL-4: S12A 文档底稿

**User Story:** 作为审计项目组成员，我想预览和编辑"评估专家报告"Word 文档。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `word-template` componentType 渲染 S12A 评估专家报告.docx
2. THE Special_Cycle_System SHALL 在 wpPopupDocxConfigs 中注册 S12A 弹窗配置
3. THE Special_Cycle_System SHALL 支持 S12A 的 OnlyOffice 编辑/降级下载

### 5.2 S20~S21: 新准则底稿

**模板文件（2 个）：**
- S20 营业收入扣除情况核查.xlsx
- S21 数据资产.xlsx

#### Requirement S-NEW-1: 新准则底稿渲染

**User Story:** 作为审计项目组成员，我想使用新准则相关核查底稿。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S20 营业收入扣除情况核查（逐项核查式）
2. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S21 数据资产（逐项检查式）
3. THE Special_Cycle_System SHALL 在 S20 中支持从 D4（营业收入）循环读取收入数据

### 5.3 S32: IPO 专项核查（13 个）

**模板文件：** S32-1 ~ S32-13

| 编号 | 核查内容 |
|------|---------|
| S32-1 | 自我交易 |
| S32-2 | 串通 |
| S32-3 | 关联方代付 |
| S32-4 | 利益输送 |
| S32-5 | 体外资金 |
| S32-6 | 互联网造假 |
| S32-7 | 资本化 |
| S32-8 | 压缩薪金 |
| S32-9 | 延迟费用 |
| S32-10 | 资产减值 |
| S32-11 | 延迟转固 |
| S32-12 | 其他粉饰 |
| S32-13 | 期后下滑 |

#### Requirement S-IPO32-1: IPO 专项核查渲染

**User Story:** 作为 IPO 项目审计人员，我想使用 IPO 专项核查底稿逐项核查舞弊风险因素。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S32-1~S32-13 全部底稿
2. THE Special_Cycle_System SHALL 标记 S32-1~S32-13 的 applicable_when 为 `business_category IN ['ipo','listed','neeq']`
3. WHERE 项目类型为普通年审时，THE Special_Cycle_System SHALL 自动标记 S32 系列为"不适用"并灰显
4. THE Special_Cycle_System SHALL 在各核查底稿中包含"核查程序/核查结论/异常情况说明"字段

### 5.4 S33: 综合核查（10 个）

**模板文件：** S33-1 ~ S33-9 + 程序修订说明.docx

| 编号 | 核查内容 |
|------|---------|
| S33-1 | 内控制度 |
| S33-2 | 财务非财务印证 |
| S33-3 | 盈利异常 |
| S33-4 | 关联方 |
| S33-5 | 收入毛利 |
| S33-6 | 客户供应商 |
| S33-7 | 存货资产 |
| S33-8 | 现金收付 |
| S33-9 | 财务异常 |
| - | 程序修订说明.docx |

#### Requirement S-IPO33-1: 综合核查渲染

**User Story:** 作为 IPO 项目审计人员，我想使用综合核查底稿对项目财务进行全面核查。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S33-1~S33-9 全部底稿
2. THE Special_Cycle_System SHALL 标记 S33-1~S33-9 的 applicable_when 为 `business_category IN ['ipo','listed','neeq']`
3. THE Special_Cycle_System SHALL 使用 `word-template` componentType 渲染"程序修订说明.docx"
4. THE Special_Cycle_System SHALL 在 S33-5（收入毛利）中支持从 D4/F5 循环读取收入/成本数据

### 5.5 S34: 证监会核查事项（43 个）

**模板文件：** S34-0 清单 + S34-1~S34-41 各专项 + S34-1-1 信息披露豁免核查意见.docx

#### Requirement S-CSRC-1: 证监会核查事项渲染

**User Story:** 作为 IPO 项目审计人员，我想逐项执行证监会关注的核查事项。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S34-0（核查事项清单/总控表）
2. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S34-1~S34-41 全部专项核查底稿
3. THE Special_Cycle_System SHALL 标记 S34 全系列的 applicable_when 为 `business_category IN ['ipo','listed','neeq','refinancing']`
4. THE Special_Cycle_System SHALL 使用 `word-template` componentType 渲染 S34-1-1 信息披露豁免专项核查意见.docx
5. THE Special_Cycle_System SHALL 在 S34-0 总控表中支持各子项完成状态汇总展示

### 5.6 S35: 再融资核查（5 个）

**模板文件：** S35-1 ~ S35-5

| 编号 | 核查内容 |
|------|---------|
| S35-1 | 关联交易 |
| S35-2 | 财务性投资 |
| S35-3 | 现金分红 |
| S35-4 | 商誉减值 |
| S35-5 | 募集资金收购 |

#### Requirement S-REFIN-1: 再融资核查渲染

**User Story:** 作为再融资项目审计人员，我想使用再融资专项核查底稿。

**Acceptance Criteria:**

1. THE Special_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 S35-1~S35-5 全部底稿
2. THE Special_Cycle_System SHALL 标记 S35-1~S35-5 的 applicable_when 为 `business_category IN ['refinancing']`
3. WHERE 项目类型非再融资时，THE Special_Cycle_System SHALL 自动标记 S35 系列为"不适用"并灰显

## 6. 跨模块联动矩阵

| 源 | 目标 | 联动数据 | 方向 | 状态 |
|----|------|---------|------|------|
| D4 营业收入审定 | S20 营业收入扣除核查 | 收入金额/扣除项 | D→S（读取） | 🔴 需建 |
| D~N 各循环审定表 | S32~S35 专项核查 | 审定金额/差异 | D~N→S（读取） | 🔴 需建 |
| F5 营业成本审定 | S33-5 收入毛利核查 | 成本金额/毛利率 | F→S（读取） | 🔴 需建 |
| trial_balance | S15 每股收益 | 净利润/股本数 | 全局→S（读取） | 🔴 需建 |
| trial_balance | S17 非经常性损益 | 损益科目金额 | 全局→S（读取） | 🔴 需建 |
| B50 风险评估 | S14 会计估计 | 估计相关风险 | B→S（读取） | 🔴 需建 |
| S 类结论 | A17 总结报告 | 专项核查结论汇总 | S→A（被读取） | 🔴 需建 |

**特点：S 类是纯消费者**，只从 D~N 及全局数据读取，自身结论仅被 A 类总结报告引用。

## 7. 技术约束

### 7.1 wp_code 注册规则

1. S 类底稿 wp_code 以 `S` 开头
2. 90 个 wp_code 一次性全部注册
3. 命名规则：
   - S{n}：S1~S17/S20~S21（特殊考虑+新准则）
   - S{n}A：程序表（仅对有程序步骤的底稿）
   - S32-{n}：IPO 专项核查子项
   - S33-{n}：综合核查子项
   - S33-REV：程序修订说明（docx）
   - S34-{n}：证监会核查子项
   - S34-1-1：信息披露豁免核查意见（docx）
   - S35-{n}：再融资核查子项
   - S12A：评估专家报告（docx）

### 7.2 componentType 分配原则

| 底稿类型 | componentType | 判定依据 |
|----------|--------------|---------|
| 含程序步骤的（S1/S2/S3/S8/S10/S11/S13） | `a-program-console` | 有序号/步骤/执行人/结论 |
| 逐项检查式（S4/S5/S6/S9/S12/S14/S16/S20/S21/S32/S33/S34/S35） | `d-form-table` | 逐条核查+结论填写 |
| 含公式计算的（S15/S17） | `audit-sheet` | 含公式/大数据量 |
| .docx 文件（S12A/S33-REV/S34-1-1） | `word-template` | 纯文档 |
| 底稿目录/选项清单 | 不渲染 | 平台自动导航 |

### 7.3 IPO 适用性控制

- S32 系列：`applicable_when: business_category IN ['ipo','listed','neeq']`
- S33 系列：`applicable_when: business_category IN ['ipo','listed','neeq']`
- S34 系列：`applicable_when: business_category IN ['ipo','listed','neeq','refinancing']`
- S35 系列：`applicable_when: business_category IN ['refinancing']`
- S1~S21：所有项目适用（无 applicable_when 限制）

### 7.4 导入导出

1. 程序表（S{n}A）：标准程序表导出
2. 检查表（d-form-table）：通用 d-form-table 导出
3. 计算表（audit-sheet）：OnlyOffice 原生导出
4. docx 文件：直接下载原始 Word
5. 批量导出：项目归档时 S 类全量打包 zip

### 7.5 S 类无审定表回写

S 类底稿不含审定表（不对应具体科目），无需 audited_amount → trial_balance 回写。这是与 D~N 循环的核心差异。

## 8. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：90 个 wp_code + componentType 映射 | 必做 | 无 |
| P1 | 程序表：S1~S16 中程序表式底稿提取 + 注册 | 必做 | P0 |
| P2 | IPO 专项核查注册：S32/S33/S34/S35 d-form-table + applicable_when | 必做 | P0 |
| P3 | address_registry：仅 audit-sheet 类（S15/S17）坐标注册 | 必做 | P0 |
| P4 | docx 文件注册：S12A/S33-REV/S34-1-1 word-template 配置 | 必做 | P0 |
| P5* | 联动：S→D~N 读取 + IPO 适用性前端灰显 | 增强 | P2 |
| P6 | 导入导出 + E2E | 必做 | P1~P4 |

## 9. 跨循环依赖提示

> 📌 **全局交叉索引**：`.kiro/specs/CYCLE-CROSS-REFERENCE.md`

- **前置依赖**：S 是纯消费者——D~N 全部 P2 审定表完成后 S 的联动才有数据
- **无 C 类**：S 不对应任何控制测试（贯穿各循环的专项考虑）
- **无审定表**：S 不按科目审计，不回写 trial_balance
- **后续被依赖**：S 各底稿结论→A17 ch15"其他特殊考虑"汇总
- **IPO 适用性**：S32~S35 全系列仅特定项目类型适用（与 D4/F2 IPO 底稿共用 applicable_when 模式）
- **⚠️ S 类 P0~P4 可先于 D~N 联动完成（仅注册+渲染），P5 联动需等 D~N 审定数据就绪**

## 10. D~N 经验教训应用

| # | 经验 | S 类应对 |
|---|------|---------|
| 1 | wp_code 注册不完整 | P0 一次性注册全部 90 条 |
| 2 | componentType 映射遗漏 | P0 在 _WP_CODE_OVERRIDE 显式映射每个 wp_code |
| 3 | 底稿目录/选项 sheet 不渲染 | 统一标记不渲染 |
| 4 | OnlyOffice 底稿必须坐标落位 | P3 仅 audit-sheet（S15/S17）需要坐标 |
| 5 | IPO 适用性复用 applicable_when | S32~S35 全部标记 |
| 6 | .docx 走 word-template | S12A/S33-REV/S34-1-1 三个 docx 文件 |
| 7 | 联动是核心价值 | S 类作为消费者从 D~N 读取数据 |
| 8 | 不使用 generic schema | S 类各底稿结构差异极大，逐一映射 |
