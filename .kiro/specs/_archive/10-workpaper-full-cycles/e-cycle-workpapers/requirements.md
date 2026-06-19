# E 类底稿（货币资金循环）— 需求文档

## 1. 概述

E 类底稿覆盖"实质性程序—货币资金循环"阶段（审计循环代号 E），是 C 类控制测试结论的后续应对——根据 B50 风险评估结果和 C3 控制测试结论，执行实质性程序以获取货币资金（库存现金+银行存款+其他货币资金）的充分适当审计证据。包含 **1 个科目组 + 1 函证组、5 个模板文件、约 35+ 个子底稿 sheet**。

本 spec 目标：**补全 E 类底稿的完整注册、componentType 映射、程序表提取、联动实现**。

## 2. 现状与差距

### 2.1 已有实现

| 维度 | 现状 | 说明 |
|------|------|------|
| wp_account_mapping | 5 条（E0/E1/E1-1/E1-2/E1-3） | 缺大量子码 |
| generated YAML schema | 待查 | 可能已有部分 generated |
| _WP_CODE_OVERRIDE | 0 条 | E 类无显式 componentType 映射 |
| ConfirmationHub | E0 函证可路由到已有模块 | confirmation_service 共用 |
| risk_for_cycle | B50→E 风险读取就绪 | auto_data_resolvers 已注册 |
| control_test_result_for_cycle | C3→E 控制测试结论读取就绪 | auto_data_resolvers 已注册 |

### 2.2 待补缺口

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| E1 子码严重缺失（E1-4~E1-32 约 30 子底稿） | 无法精确路由各 sheet | P0 |
| _WP_CODE_OVERRIDE 全空 | render-config 走 fallback 路径 | P0 |
| E1A 程序表未提取模板 | 程序表步骤不在 procedure_table_templates.json | P1 |
| E 审定表→trial_balance 联动 | audited_amount 回写缺乏自动触发 | P2 |
| E 分析/检查/IPO 底稿无 address_registry | OnlyOffice 底稿孤立无联动 | P3 |

## 3. 术语表（Glossary）

- **货币资金循环系统（Cash_Cycle_System）**：平台中负责 E 类底稿渲染、编辑、联动的子系统
- **审定表（Audit_Determination_Table）**：E1-1 系列，记录货币资金审定金额+调整分录汇总
- **实质性程序表（Substantive_Procedure_Table）**：E1A 系列，列出货币资金具体审计程序步骤
- **明细表（Detail_Schedule）**：E1-2~E1-11 系列，按科目/银行/币种展开余额明细
- **分析程序表（Analytical_Procedure）**：E1-14~E1-15 系列，执行分析性程序
- **检查表（Inspection_Table）**：E1-18~E1-23 系列，逐笔检查抽样交易
- **函证（Confirmation）**：E0 系列，向银行确认存款余额
- **IPO 舞弊应对（IPO_Fraud_Response）**：E1-26~E1-32 系列，特殊项目舞弊应对程序

## 4. E 类底稿分组结构

| 组 | 编号范围 | 功能 | 模板文件 | componentType |
|----|---------|------|---------|---------------|
| G0 | E0/E0A/E0-1~E0-5 | 货币资金函证 | 1 xlsx | ConfirmationHub + `d-form-table` |
| G1 | E1/E1A/E1-1~E1-32 | 货币资金（库存现金+银行存款+其他货币资金） | 4 xlsx(合计~35 sheet) | 程序表=`a-program-console`，审定表/明细=`d-form-table`/`audit-sheet`，分析/检查/IPO=`audit-sheet` |

## 5. 各组详细需求

### G0: 货币资金函证 (E0)

**模板文件：** E0 货币资金 - 函证（Leap应对措施-函证）.xlsx

**Sheet 结构（推测）：**
- 底稿目录 / 函证程序表E0A / 函证结果汇总E0-1 / 核实被函证银行E0-2 / 跟函控制E0-3 / 差异调节E0-4 / 替代程序E0-5 / 差异检查示例

**需求点：**

#### Requirement G0-1: ConfirmationHub 集成

**User Story:** 作为审计项目组成员，我想通过平台已有的函证模块管理货币资金函证，以便统一管理银行询证函流程。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 将 E0 底稿的核心函证功能路由到已有的 ConfirmationHub 模块
2. THE Cash_Cycle_System SHALL 在 E0A 程序表中通过 ref_index chip 跳转到 ConfirmationHub 对应函证批次
3. WHEN 用户打开 E0 底稿时，THE Cash_Cycle_System SHALL 显示该项目 E 循环的函证摘要（已发函数/回函率/差异数）
4. THE Cash_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 E0-1（函证结果汇总）、E0-2（核实被函证银行）、E0-4（差异调节）、E0-5（替代程序）等辅助 sheet
5. THE Cash_Cycle_System SHALL 不渲染"差异检查示例" sheet（标记为参考不开发）

#### Requirement G0-2: E0A 函证程序表

**User Story:** 作为审计项目组成员，我想执行货币资金函证程序表中的步骤，以便确保函证流程完整。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 E0A 函证程序表
2. THE Cash_Cycle_System SHALL 从 xlsx 模板提取 E0A 全部程序步骤，注册到 procedure_table_templates.json
3. THE Cash_Cycle_System SHALL 在程序表步骤中包含 ref_index chip 跳转到 E0-1~E0-5 各辅助底稿


### G1: 货币资金 (E1)

**模板文件：**
- E1-1至E1-11 货币资金-审定表明细表（Leap-常规程序）.xlsx
- E1-14至E1-15 货币资金-分析程序（Leap应对措施-分析程序）.xlsx
- E1-18至E1-23 货币资金-检查（Leap应对措施-检查）.xlsx
- E1-26至E1-32 货币资金-IPO上市新三板重组舞弊应对.xlsx

**Sheet 结构（E1-1至E1-11）：**
- 底稿目录 / 程序表E1A / 审定表E1-1 / 附注披露（上市公司/国企）/ 库存现金明细E1-2 / 银行存款明细E1-3 / 其他货币资金明细E1-4 / 银行存款余额调节表E1-5 / 受限货币资金E1-6 / 大额现金收支检查E1-7 / 银行存款检查E1-8 / 利息测算E1-9 / 调整分录汇总E1-10 / 未达账项E1-11

**需求点：**

#### Requirement G1-1: E1A 程序表

**User Story:** 作为审计项目组成员，我想执行货币资金实质性程序，以便获取科目审计证据。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `a-program-console` componentType 渲染 E1A 程序表
2. THE Cash_Cycle_System SHALL 从 xlsx 模板提取 E1A 全部程序步骤，注册到 procedure_table_templates.json
3. WHEN 程序步骤标记为"已执行"时，THE Cash_Cycle_System SHALL 记录执行人和执行日期
4. THE Cash_Cycle_System SHALL 在程序表中通过 `auto_data_source: "risk_for_cycle"` 展示 B50 对应风险评估结论
5. THE Cash_Cycle_System SHALL 在程序表中通过 `auto_data_source: "control_test_result_for_cycle"` 展示 C3 控制测试结论
6. THE Cash_Cycle_System SHALL 在程序表中包含 ref_index chip 跳转到 E0（函证）、E1-1~E1-11（常规）、E1-14~15（分析）、E1-18~23（检查）、E1-26~32（IPO）

#### Requirement G1-2: E1-1 审定表

**User Story:** 作为审计项目组成员，我想编辑货币资金审定表，以便确定科目审定金额。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 E1-1 审定表
2. THE Cash_Cycle_System SHALL 在审定表中包含以下核心字段：科目名称、未审金额（从 trial_balance 自动取数）、审计调整借方、审计调整贷方、审定金额（公式计算）、差异说明
3. WHEN 审定表保存时，THE Cash_Cycle_System SHALL 将审定金额回写到 trial_balance.audited_amount
4. THE Cash_Cycle_System SHALL 支持从审定表跳转到对应调整分录（ref_index chip→调整分录底稿）

#### Requirement G1-3: 附注披露

**User Story:** 作为审计项目组成员，我想编辑货币资金附注披露信息，以便确保附注完整准确。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 将 E1 的附注披露 sheet 路由到 disclosure_notes 模块（c-note-table componentType）
2. THE Cash_Cycle_System SHALL 支持上市公司版本和国企版本两套附注模板的切换
3. WHEN 附注数据保存时，THE Cash_Cycle_System SHALL 通过 disclosure_notes 模块统一管理附注内容

#### Requirement G1-4: 明细表（E1-2~E1-6）

**User Story:** 作为审计项目组成员，我想编辑货币资金各科目明细表，以便支持审定金额。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 E1-2（库存现金明细）
2. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-3（银行存款明细）、E1-4（其他货币资金明细）（含公式计算）
3. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-5（银行存款余额调节表）（含公式+企业账面→银行对账单调节）
4. THE Cash_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 E1-6（受限货币资金明细）
5. THE Cash_Cycle_System SHALL 在明细表的 `address_registry` 中注册关键坐标（合计行、余额列）
6. WHILE E1-1 审定表金额与明细表合计金额不一致时，THE Cash_Cycle_System SHALL 在审定表底部显示"⚠️ 审定表与明细表不平"警告

#### Requirement G1-5: 检查与测算（E1-7~E1-11）

**User Story:** 作为审计项目组成员，我想执行货币资金检查程序和利息测算，以便验证余额真实性。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-7（大额现金收支检查）、E1-8（银行存款检查）
2. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-9（利息测算）（含自动计算公式）
3. THE Cash_Cycle_System SHALL 使用 `d-form-table` componentType 渲染 E1-10（调整分录汇总）
4. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-11（未达账项明细）
5. THE Cash_Cycle_System SHALL 在 `address_registry` 中注册 E1-9 利息测算结论坐标

#### Requirement G1-6: E1-14~E1-15 分析程序

**User Story:** 作为审计项目组成员，我想对货币资金执行分析性程序，以便识别异常波动。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-14 和 E1-15 分析程序底稿
2. THE Cash_Cycle_System SHALL 在 `address_registry` 中注册各分析 sheet 的结论坐标
3. THE Cash_Cycle_System SHALL 支持从 trial_balance 自动取数填充分析基础数据

#### Requirement G1-7: E1-18~E1-23 检查程序

**User Story:** 作为审计项目组成员，我想对货币资金抽样执行检查程序，以便验证交易真实性和截止。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-18至E1-23 检查底稿（单文件多 sheet）
2. THE Cash_Cycle_System SHALL 在 `address_registry` 中注册各检查 sheet 的结论坐标
3. THE Cash_Cycle_System SHALL 支持检查结果汇总回写到 E1A 程序表对应步骤

#### Requirement G1-8: E1-26~E1-32 IPO/舞弊应对

**User Story:** 作为审计项目组成员，我想执行 IPO/上市/新三板/重组项目的货币资金舞弊应对程序，以便满足特殊监管要求。

**Acceptance Criteria:**

1. THE Cash_Cycle_System SHALL 使用 `audit-sheet` componentType 渲染 E1-26至E1-32 底稿
2. WHERE 项目类型为 IPO/上市/新三板/重组时，THE Cash_Cycle_System SHALL 自动标记 E1-26~E1-32 为"适用"
3. WHERE 项目类型为普通年审时，THE Cash_Cycle_System SHALL 自动标记 E1-26~E1-32 为"不适用"并灰显


## 6. 跨模块联动矩阵

| 源 | 目标 | 联动数据 | 方向 | 状态 |
|----|------|---------|------|------|
| B23-3 穿行测试 | C3 控制测试 | 设计有效性结论 | B→C→E（读取） | ✅ `_on_b23_saved` |
| B50-3 认定层次风险 | E1A 程序表 | 已识别风险展示 | B→E（读取） | ✅ 就绪 |
| C3 控制测试结论 | E1A 程序表 | 控制测试有效性 | C→E（读取） | ✅ 就绪 |
| E1-1 审定表 | trial_balance.audited_amount | 审定金额回写 | E→全局（写入） | 🔴 需补 |
| E1 附注 sheet | disclosure_notes 模块 | 附注内容 | E→全局（路由） | ✅ 复用 D 已有 |
| E0 函证 | ConfirmationHub | 函证流程 | E→全局（路由） | ✅ 已有 |
| E 各检查/分析结论 | E1A 程序表步骤 | 结论回写 | E→E（内部） | 🔴 需补 |
| E1-1 审定表 | A1-13 错报汇总 | 审计差异 | E→A（读取） | ✅ 已有路径 |

## 7. 技术约束

### 7.1 wp_code 注册规则

1. E 类底稿 wp_code 以 `E` 开头
2. 现有 5 条需扩充到完整覆盖（估计 35 条）
3. 子底稿规则：
   - E1A：实质性程序表
   - E1-1：审定表
   - E1-2~E1-11：常规明细/检查/测算
   - E1-14~E1-15：分析程序
   - E1-18~E1-23：检查程序
   - E1-26~E1-32：IPO/舞弊应对
   - E0-1~E0-5：函证辅助 sheet

### 7.2 componentType 分配原则

| sheet 类型 | componentType | 判定依据 |
|-----------|---------------|---------|
| 程序表（E1A/E0A） | `a-program-console` | 有序号/步骤/执行人/结论 |
| 审定表（E1-1）| `d-form-table` | 结构化表单+联动取数 |
| 附注披露 | `c-note-table`（disclosure_notes 路由） | 附注统一管理 |
| 库存现金明细/受限资金/调整分录（简单结构） | `d-form-table` | 逐行填写+enum 字段 |
| 银行存款明细/其他货币资金/余额调节/利息测算（含公式） | `audit-sheet` | 复杂计算+公式 |
| 分析程序（含公式/图表） | `audit-sheet` | 复杂计算+可视化 |
| 检查程序（多 sheet） | `audit-sheet` | 大量 sheet 检查 |
| IPO/舞弊应对 | `audit-sheet` | 复杂多 sheet |
| 底稿目录 | 不渲染 | 平台自动生成导航 |
| 选项清单/示例 | 不渲染 | 参考不开发 |

### 7.3 审定表→trial_balance 回写

复用 D 类已有 `_on_audit_determination_saved` handler 模式：E1-1 保存时触发 EventBus `WORKPAPER_SAVED` → handler 识别 wp_code 为审定表类型 → 从 parsed_data 提取审定金额 → UPDATE trial_balance。

### 7.4 IPO 适用性

E1-26~E1-32（IPO/舞弊应对）通过 `applicable_when` 字段控制：
- `business_category IN ('ipo', 'listed', 'neeq', 'restructuring')` → 适用
- 普通年审 → 自动标记不适用

### 7.5 导入导出

1. 程序表（E1A/E0A）：标准程序表导出
2. 审定表（E1-1）：d-form-table 通用导出
3. 明细表/分析/检查（audit-sheet）：OnlyOffice 原生导出
4. 支持从 Excel 导入填充已有结构化底稿
5. 批量导出：项目归档时 E 类全量打包 zip

## 8. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：扩充 wp_account_mapping 到完整 E 类 wp_code + _WP_CODE_OVERRIDE 全量映射 | 必做 | 无 |
| P1 | 程序表：E0A+E1A 程序表模板提取 + 注册 procedure_table_templates.json | 必做 | P0 |
| P2 | 审定表+联动：E1-1 审定表 schema + audited_amount 回写 | 必做 | P0 |
| P3 | OnlyOffice 底稿：分析/检查/IPO address_registry 坐标注册 | 必做 | P0 |
| P4 | 特殊程序：E1-5 余额调节表 + E1-9 利息测算 | 必做 | P0 |
| P5* | 联动完善：E→trial_balance 回写 + 检查结论回写 | 增强 | P2 |
| P6 | 导入导出 + E2E | 必做 | P1~P4 |

## 9. 跨循环依赖提示

> 📌 **全局交叉索引**：`.kiro/specs/CYCLE-CROSS-REFERENCE.md`

- **前置依赖**：D 类 P0~P2 已完成（E 复用审定表回写 handler 和 confirmation 模式）
- **B23 穿行编号**：E 对应 B23-3（收款/货币资金循环穿行测试）
- **C 类编号**：E 对应 C3（现金收付控制），非 C2
- **完整链路**：B23-3 穿行→C3 控制测试→E1A 实质性程序表（三层数据依次传递）
- **后续被依赖**：S15（每股收益）从 trial_balance 读取净利润；S17 从 trial_balance 读取损益科目
- **IPO 适用性**：E1-26~32 与 D4-22~32、F2-61~72 共用 applicable_when 模式

## 10. B/C/D 经验教训应用

| # | 经验 | E 类应对 |
|---|------|---------|
| 1 | wp_code 注册不完整 | P0 一次性扩充全部 E 类子码（~35 条） |
| 2 | componentType 映射遗漏 | P0 在 _WP_CODE_OVERRIDE 显式映射每个 wp_code |
| 3 | VBA 选项清单 sheet 不渲染 | 底稿目录/选项清单/示例 sheet 统一标记不渲染 |
| 4 | OnlyOffice 底稿必须地址坐标落位 | P3 阶段所有 audit-sheet 底稿强制 address_registry 注册 |
| 5 | 联动链完整 | B50→E + C3→E 读取就绪，补 E→trial_balance 写入 |
| 6 | D4-22 IPO 适用性模式复用 | E1-26~32 复用 applicable_when 机制 |
| 7 | 三表统一 HTML | 目录表自动导航、审定表 d-form-table、附注 c-note-table |
