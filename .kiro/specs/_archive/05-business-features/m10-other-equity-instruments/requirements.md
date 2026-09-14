# Requirements Document: M10 其他权益工具底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **永续债/优先股负债权益区分（CAS37）判定** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM10ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M10其他权益工具底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m10-other-equity-instruments`，覆盖来自 `M10 其他权益工具.xlsx` 的10个有效sheet（含1个Q10A修订前sheet跳过）。科目覆盖4003其他权益工具（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M10核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方）②**负债与权益区分（CAS37核心！）**：永续债、优先股等金融工具需按CAS37《金融工具列报》判定是否分类为权益工具（是否存在交付现金/金融资产的合同义务），M10-4负债与权益区分检查表逐条判定③**归入权益的部分才计入M10，归入负债的计入负债科目**。关键公式总数约60+（审定表29公式 + 明细M10-2 13公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M10A**: 其他权益工具实质性程序表M10A（复用a-program-console）
- **Adjudication_M10_1**: 审定表M10-1，38×14，29公式，科目4003其他权益工具(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），47×19
- **Disclosure_SOE**: 附注披露信息（国有企业），12×19
- **Detail_M10_2**: 明细表M10-2，45×30，13公式，其他权益工具明细（永续债/优先股）
- **Adjustment_M10_3**: 其他权益工具调整分录汇总M10-3
- **Classification_Check_M10_4**: 负债与权益区分检查表M10-4，64×8，CAS37判定
- **Instrument_Check_M10_5**: 其他权益工具检查表M10-5
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **Classification_Engine**: 负债权益区分引擎（纯函数，CAS37）
- **Trial_Balance_Writeback**: 审定数回写（科目4003）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M10其他权益工具底稿按sheetName分发, so that 10个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M10 组件 SHALL 注册新componentType: `m10-other-equity-instruments`，主入口为 GtM10OtherEquityInstruments.vue
2. THE GtM10OtherEquityInstruments.vue SHALL 接收 `sheetName` prop，正则提取编码(M10-1)，v-if分发
3. THE M10 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M10 组件 SHALL 拆为：m10/core/（审定+明细+调整+附注）、m10/inspection/（区分检查+工具检查）
5. THE M10 组件 SHALL composable分层：useM10FormData + useM10FormulaEngine + useM10ClassificationEngine(纯函数) + useM10CrossSheet + useM10DualMode + useM10ImportExport
6. THE M10 组件 SHALL 在htmlRendererRegistry中注册'm10-other-equity-instruments'
7. THE M10 组件 SHALL 在wp_code_overrides.json中将M10/M10-1~M10-5/M10A映射为'm10-other-equity-instruments'
8. THE M10 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm10-other-equity-instruments'
9. THE GtM10OtherEquityInstruments.vue SHALL 支持selfLoad
10. THE M10 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M10-{sheet}-{field}"
11. THE 未迁移sheet及Q10A修订前sheet SHALL 走 OnlyOffice fallback或跳过

### Requirement 2: 审定表M10-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看其他权益工具数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M10_1 SHALL 渲染为单区块：其他权益工具(贷方/权益，按工具类型：永续债/优先股分类+小计)
2. THE Adjudication_M10_1 SHALL 显示列：项目 | 期初 | 贷方发生(发行) | 借方发生(赎回/转换) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**（发行在贷方，赎回在借方）
5. THE Adjudication_M10_1 SHALL 与M10-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4003)+发布'substantive:adjudicated'
7. THE Adjudication_M10_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M10-2（永续债/优先股明细）

**User Story:** As a 审计助理, I want to 管理其他权益工具明细, so that 每项工具可追溯。

#### Acceptance Criteria

1. THE Detail_M10_2 SHALL 显示列：工具名称 | 工具类型(永续债/优先股) | 发行日 | 发行金额 | 期初 | 本期发行 | 本期赎回 | 利息/股息 | 期末
2. THE Detail_M10_2 SHALL 自动计算：期末=期初+本期发行-本期赎回（权益类）；13公式实时计算
3. THE Detail_M10_2 SHALL 30列宽表拆分：按工具信息/发行赎回/分派区段Tab（行同步）
4. THE Detail_M10_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入工具名）+导入导出
5. THE Detail_M10_2 SHALL 与M10-1审定表交叉验证

### Requirement 4: 负债与权益区分检查表M10-4（CAS37核心！）

**User Story:** As a 审计助理, I want to 按CAS37逐条判定金融工具的负债/权益分类, so that 分类准确性得到验证。

#### Acceptance Criteria

1. THE Classification_Check_M10_4 SHALL 逐条列示CAS37判定要素：是否存在交付现金/金融资产的合同义务 | 是否强制付息 | 是否有到期赎回义务 | 结算方式(固定/可变数量自身权益工具) | 判定结论(权益/负债)
2. THE Classification_Engine SHALL 根据判定要素输出分类结论：无合同义务交付现金→权益工具；有合同义务→金融负债
3. THE Classification_Check_M10_4 SHALL 计算归入权益金额 + 归入负债金额 = 工具总额
4. WHEN 判定为权益 SHALL 计入M10(4003)；WHEN 判定为负债 SHALL 提示计入负债科目
5. THE Classification_Check_M10_4 SHALL 64行8列逐条判定+提供核对清单+审计结论区（el-card包裹）+AI辅助按钮

### Requirement 5: 检查表M10-5 + 调整分录M10-3 + 附注

**User Story:** As a 审计助理, I want to 完成其他权益工具检查并管理调整, so that 审计结论完整。

#### Acceptance Criteria

1. THE Instrument_Check_M10_5 SHALL 提供核对清单+审计结论区（el-card包裹）
2. THE Instrument_Check_M10_5 SHALL 每个文本section标题行右侧放AI辅助按钮
3. THE Adjustment_M10_3 SHALL 借贷平衡校验+EventBus+双向同步M10-1
4. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
5. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 6: 区分引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现负债权益区分纯函数引擎并集成标准能力, so that CAS37判定可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE Classification_Engine SHALL classifyInstrument(hasContractualObligation): 有合同义务→'liability'；无→'equity'
2. THE Classification_Engine SHALL splitAmount(total, equityPart)=负债部分=total-equityPart
3. THE Classification_Engine SHALL calcClassificationConsistency(equity, liability, total): equity+liability===total
4. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
5. THE M10 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
6. THE M10 SHALL 支持导入导出三级（useM10ImportExport，http带Authorization）
7. THE M10 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
