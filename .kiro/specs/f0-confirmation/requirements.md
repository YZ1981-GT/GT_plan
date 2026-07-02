# Requirements Document: F0 存货循环函证模块

## Introduction

F0存货循环函证（采购与付款循环），覆盖科目：预付账款/应付票据/应付账款/采购。源模板1个xlsx文件11个sheet。

**核心架构决策（对齐D0实际实现）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用
- F0-1~F0-4/F0-4b/F0-7/F0-8直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-diff-checklist / confirmation-reliability / confirmation-fraud-risk）
- **仅F0-5/F0-6需要新建**：替代程序4区块按科目不同（预付账款 vs 应付账款），参照D0-5/D0-6模式
- F0A程序表复用`a-program-console`

**与D0的差异**：
- D0科目：应收账款/合同资产/其他应收款（收入循环）
- F0科目：预付账款/应付票据/应付账款/采购（采购与付款循环）
- F0-5替代程序4区块：期后收货/期末余额证据/本期付款/本期采购证据
- F0-6替代程序4区块：期后付款/期末余额证据/本期采购/本期入库证据

**源模板sheet清单（openpyxl实读2026-07-01）**：

| # | Sheet名 | wp_code | componentType | 新建/复用 |
|---|---------|---------|---------------|-----------|
| 1 | 底稿目录 | - | b-index | 复用 |
| 2 | 函证程序表F0A | F0A | a-program-console | 复用 |
| 3 | 函证结果汇总表F0-1 | F0-1 | confirmation-summary | 复用D0 |
| 4 | 核实被函证单位信息F0-2 | F0-2 | confirmation-entity-verify | 复用D0 |
| 5 | 跟函函证过程控制F0-3 | F0-3 | confirmation-followup | 复用D0 |
| 6 | 函证差异调节表F0-4 | F0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | 函证差异检查表（示例）| 函证差异检查表（示例）| confirmation-diff-checklist | 复用D0 |
| 8 | 预付及采购替代程序F0-5 | F0-5 | confirmation-alternative-f05 | **新建** |
| 9 | 应付及采购替代程序F0-6 | F0-6 | confirmation-alternative-f06 | **新建** |
| 10 | 邮件传真回函可靠性验证F0-7 | F0-7 | confirmation-reliability | 复用D0 |
| 11 | 函证程序舞弊风险评价表F0-8 | F0-8 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType（confirmation-summary/entity-verify/followup/diff-reconcile/diff-checklist/reliability/fraud-risk + 循环特有的alternative-xxx）
- **替代程序**: 对未回函的被询证单位执行的审计替代程序（检查期后收付款/余额支持性证据等），4区块检查宽表结构按科目不同

## Requirements

### Requirement 1: F0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to F0各sheet映射到D0共享组件, so that F0函证底稿获得与D0相同的专属渲染。

#### Acceptance Criteria

1. THE wp_code_overrides.json SHALL 包含完整映射：F0→confirmation-hub, F0A→a-program-console, F0-1→confirmation-summary, F0-2→confirmation-entity-verify, F0-3→confirmation-followup, F0-4→confirmation-diff-reconcile, F0-4b→confirmation-diff-checklist, F0-5→confirmation-alternative-f05, F0-6→confirmation-alternative-f06, F0-7→confirmation-reliability, F0-8→confirmation-fraud-risk
2. THE F0.yaml render schema SHALL 准确反映11个sheet的component_type和class_code
3. THE account_package_registry.json SHALL 包含F0包（11 sheets按模板顺序）

### Requirement 2: F0-5预付及采购替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的预付账款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE F0-5 SHALL 注册componentType: `confirmation-alternative-f05`
2. THE F0-5 SHALL 多公司Master-Detail（一公司一检查表，参照D0-5 GtConfirmationAlternativeD05模式）
3. THE F0-5 SHALL 抽样配置区+余额汇总+4区块检查宽表
4. THE F0-5 4区块 SHALL 为：①预付账款期后收货检查②预付账款期末余额支持性证据③预付账款本期付款检查④预付账款本期采购证据
5. THE F0-5 SHALL 支持从confirmation-hub的F0-1带入未回函公司（反向联动）
6. THE F0-5 SHALL 支持增删行+动态宽表编辑
7. THE F0-5 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry

### Requirement 3: F0-6应付及采购替代程序组件（新建）

**User Story:** As a 审计助理, I want to 对未回函的应付账款执行替代程序, so that 我能获取充分适当证据。

#### Acceptance Criteria

1. THE F0-6 SHALL 注册componentType: `confirmation-alternative-f06`
2. THE F0-6 SHALL 多公司Master-Detail（一公司一检查表，参照D0-6 GtConfirmationAlternativeD06模式）
3. THE F0-6 SHALL 抽样配置区+余额汇总+4区块检查宽表
4. THE F0-6 4区块 SHALL 为：①应付账款期后付款检查②应付账款期末余额支持性证据③应付账款本期采购检查④应付账款本期入库证据
5. THE F0-6 SHALL 支持从confirmation-hub的F0-1带入未回函公司（反向联动）
6. THE F0-6 SHALL 支持增删行+动态宽表编辑
7. THE F0-6 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的2个componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

1. THE `confirmation-alternative-f05` SHALL 在VALID_COMPONENT_TYPES中注册
2. THE `confirmation-alternative-f06` SHALL 在VALID_COMPONENT_TYPES中注册
3. THE htmlRendererRegistry SHALL 包含f05/f06→对应Vue组件的映射
4. THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含f05/f06
5. THE 后端RENDERER_DISPATCH SHALL 有f05/f06的render策略（复用confirmation通用renderer）
