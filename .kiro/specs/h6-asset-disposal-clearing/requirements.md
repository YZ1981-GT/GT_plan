# Requirements Document: H6 固定资产清理底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + H1处置联动 + H10损益联动
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip数据来源 + 公式列虚线下划线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示折叠
- **导入导出**：el-dropdown三级 + useH6ImportExport composable
- **AI辅助**：多section AI生成
- **双模式**：el-segmented(结构化视图/在线编辑) + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

H6固定资产清理底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h6-asset-disposal-clearing`，覆盖来自 `H6 固定资产清理.xlsx` 的8个有效sheet。科目覆盖1606固定资产清理（借方/资产类，过渡科目）。

**H6核心特殊：过渡科目**。1606固定资产清理是过渡科目，期末余额应为0（清理完毕）。联动H1处置（H1-8减少检查转入H6）和H10资产处置损益（H6清理完毕结转H10）。审定表59公式较多但sheet数少。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录，19行8列
- **Procedure_Table_H6A**: 固定资产清理实质性程序表H6A，23行12列
- **Adjudication_H6_1**: 审定表H6-1，51行9列59公式，过渡科目1606
- **Disclosure_Listed**: 附注披露信息（上市公司），18行5列
- **Disclosure_SOE**: 附注披露信息（国有企业），18行5列
- **Detail_H6_2**: 明细表H6-2，36行25列16公式，清理项目明细
- **Adjustment_H6_3**: 调整分录汇总H6-3，21行10列
- **Check_H6_4**: 检查表H6-4，34行18列8公式，清理过程逐项检查
- **Cross_Sheet_Engine**: 跨sheet引擎，H6-1→H6-2联动 + H1/H10跨底稿
- **Formula_Engine**: 前端公式引擎composable
- **Transit_Account_Rule**: 过渡科目规则：期末余额应为0
- **Dynamic_Row**: 动态行
- **Summary_Row**: 合计行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转芯片
- **Review_Dialog**: 通用复核对话组件
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写（科目1606）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H6固定资产清理底稿按sheetName prop分发到独立子组件, so that 8个sheet在一个统一入口中有序组织。

#### Acceptance Criteria

1. THE H6 组件 SHALL 注册新componentType: `h6-asset-disposal-clearing`，主入口为 GtH6AssetDisposalClearing.vue
2. THE GtH6AssetDisposalClearing.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(H6-1/H6-2/...)，v-if 分发到对应子组件
3. THE H6 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE H6 组件 SHALL 将子组件拆分为：h6/core/（审定+明细+调整+附注）、h6/inspection/（检查表）
5. THE H6 组件 SHALL 拆分composable：useH6FormData + useH6FormulaEngine(纯函数) + useH6CrossSheet + useH6DualMode + useH6ImportExport
6. THE H6 组件 SHALL 在htmlRendererRegistry中注册'h6-asset-disposal-clearing'→GtH6AssetDisposalClearing映射
7. THE H6 组件 SHALL 在wp_code_overrides.json中将H6/H6-1~H6-4/H6A映射为'h6-asset-disposal-clearing'
8. THE H6 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h6-asset-disposal-clearing'
9. THE GtH6AssetDisposalClearing.vue SHALL 支持selfLoad
10. THE H6 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H6-{sheet编号}-{field}"

### Requirement 2: 审定表H6-1（过渡科目59公式+期末应为零）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑固定资产清理审定表, so that 我能追踪清理过程各阶段金额并确认期末余额为零。

#### Acceptance Criteria

1. THE Adjudication_H6_1 SHALL 渲染为清理过程结构：清理收入 | 清理支出(账面价值/清理费用/税费) | 清理净损益 | 期初余额 | 本期发生 | 期末余额
2. THE Adjudication_H6_1 SHALL 显示列：项目 | 期初余额 | 本期借方 | 本期贷方 | 期末余额 | 未审数 | AJE | RJE | 审定数
3. THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 校验过渡科目规则：期末余额=期初+借方-贷方（资产类借方1606）
5. WHEN 期末审定数≠0时, THE Adjudication_H6_1 SHALL 显示红色警告"⚠ 过渡科目期末余额应为0，当前余额：xxx元，请检查是否有未完成清理项目"
6. THE Adjudication_H6_1 SHALL 自动计算清理净损益=清理收入-清理支出（需与H10联动核对）
7. WHEN 清理净损益与H10对应金额不一致时, THE Adjudication_H6_1 SHALL 黄色警告"净损益≠H10资产处置损益，差额：±xxx"
8. WHEN 审定数发生变化时, THE Adjudication_H6_1 SHALL 回写trial_balance（科目1606）并发布'substantive:adjudicated'
9. THE Adjudication_H6_1 SHALL 在底部显示"审计说明"和"审计结论"+复核入口

### Requirement 3: 明细表H6-2（清理项目25列）

**User Story:** As a 审计助理, I want to 管理固定资产清理的明细项目, so that 我能追踪每笔清理项目的全过程。

#### Acceptance Criteria

1. THE Detail_H6_2 SHALL 显示25列拆为2区块：基础(序号/资产名称/原值/累计折旧/净值/清理原因/开始日期) | 清理(处置收入/清理费用/税费/净损益/结转科目/完成日期/状态/联动H1编号/联动H10编号)
2. THE Formula_Engine SHALL 自动计算：净值=原值-累计折旧；净损益=处置收入-净值-清理费用-税费
3. THE Detail_H6_2 SHALL 对"状态"列提供选项：清理中/已完成/已结转
4. WHEN 状态为"已结转"且期末余额≠0时, THE Detail_H6_2 SHALL 红色警告
5. THE Detail_H6_2 SHALL 提供GtIndexChip跳转：联动H1编号→H1-8减少检查；联动H10编号→H10明细
6. THE Detail_H6_2 SHALL 支持动态行新增+导入导出
7. THE Detail_H6_2 SHALL 合计行与H6-1审定表交叉验证

### Requirement 4: 调整分录H6-3 + 检查表H6-4

**User Story:** As a 审计助理, I want to 录入调整分录和完成清理过程检查, so that 我能确保清理过程合规且所有会计处理正确。

#### Acceptance Criteria

1. THE Adjustment_H6_3 SHALL 显示10列+借贷平衡+EventBus
2. THE Adjustment_H6_3 SHALL 双向同步AJE/RJE到H6-1
3. THE Check_H6_4 SHALL 显示18列含：检查项目/清理审批/资产评估/税务处理/会计处理/收入确认/费用归集/结转时点/核查结论
4. THE Check_H6_4 SHALL 对每个检查项提供"合规/不合规/不适用"选择
5. WHEN 存在"不合规"项时, THE Check_H6_4 SHALL 在顶部红色摘要"发现x项不合规，请关注"
6. THE Check_H6_4 SHALL 与H6-2明细表项目联动：每个检查行对应一个清理项目

### Requirement 5: 跨底稿联动（H1处置+H10损益）

**User Story:** As a 审计助理, I want to H6与H1固定资产处置和H10资产处置损益正确联动, so that 清理全流程可追溯。

#### Acceptance Criteria

1. THE H6 组件 SHALL 通过GtIndexChip将清理项目链接到H1-8减少检查对应行
2. THE H6 组件 SHALL 通过GtIndexChip将清理净损益链接到H10明细对应行
3. THE H6 组件 SHALL subscribe H1的'disposal:initiated'事件自动创建H6清理项目行
4. WHEN H6清理完成结转时, THE H6 SHALL publish 'disposal:completed'事件通知H10

### Requirement 6: 过渡科目特殊校验

**User Story:** As a 项目经理, I want to 系统自动提醒过渡科目期末余额异常, so that 我能确保所有清理项目在期末已结转完毕。

#### Acceptance Criteria

1. THE H6 组件 SHALL 在底稿目录(Index)顶部显示状态栏：期末余额为0→绿色"✓ 所有清理已结转"；不为0→红色"⚠ 存在未结转项目"
2. THE H6 组件 SHALL 在审定表和明细表同时高亮未结转项目
3. THE 后端 SHALL 在期末报告生成时校验1606余额，不为0时添加审计提醒
