# Requirements Document: M2 实收资本（股本）底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **验资核对 + 外币投资汇率折算** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM2ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M2实收资本（股本）底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m2-paid-in-capital`，覆盖来自 `M2 实收资本（股本）.xlsx` 的11个有效sheet。科目覆盖4001实收资本/股本（**贷方/权益类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M2核心特殊**：①**贷方权益类科目**（期末=期初+贷方-借方，权益增加在贷方）②**上市/非上市双版本明细表**（M2-2有上市公司版38×36和非上市公司版37×24两个版本，用el-segmented分支选择器切换）③**验资核对**（实收资本与验资报告核对）④**外币投资汇率测算**（M2-4，外币出资折算）。关键公式总数约130+（审定表73公式 + 附注41公式 + 外币投资M2-4 13公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M2A**: 实收资本实质性程序表M2A（复用a-program-console）
- **Adjudication_M2_1**: 审定表M2-1，49×12，73公式，科目4001实收资本/股本(贷方/权益)
- **Disclosure_Listed**: 附注披露信息（上市公司），15×19，41公式
- **Disclosure_SOE**: 附注披露信息（国有企业），20×19
- **Detail_Listed_M2_2**: 明细表(上市公司)M2-2，38×36，按股东列示股本
- **Detail_Unlisted_M2_2**: 明细表(非上市公司)M2-2，37×24，按出资人列示实收资本
- **Adjustment_M2_3**: 实收资本调整分录汇总M2-3
- **FX_Invest_M2_4**: 外币投资汇率测算表M2-4，20×7，13公式，外币出资折算
- **Capital_Check_M2_5**: 实收资本(股本)检查表M2-5（含验资核对）
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable（权益类！贷方科目）
- **FX_Engine**: 外币投资折算引擎（纯函数）
- **Verify_Engine**: 验资核对引擎（纯函数）
- **Branch_Selector**: 上市/非上市明细分支选择器
- **Trial_Balance_Writeback**: 审定数回写（科目4001）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M2实收资本底稿按sheetName分发, so that 11个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M2 组件 SHALL 注册新componentType: `m2-paid-in-capital`，主入口为 GtM2PaidInCapital.vue
2. THE GtM2PaidInCapital.vue SHALL 接收 `sheetName` prop，正则提取编码(M2-1)，v-if分发
3. THE M2 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M2 组件 SHALL 拆为：m2/core/（审定+明细+调整+附注）、m2/calc/（外币投资汇率）、m2/inspection/（检查表+验资）
5. THE M2 组件 SHALL composable分层：useM2FormData + useM2FormulaEngine + useM2FxEngine(纯函数) + useM2VerifyEngine(纯函数) + useM2CrossSheet + useM2DualMode + useM2ImportExport
6. THE M2 组件 SHALL 在htmlRendererRegistry中注册'm2-paid-in-capital'
7. THE M2 组件 SHALL 在wp_code_overrides.json中将M2/M2-1~M2-5/M2A映射为'm2-paid-in-capital'
8. THE M2 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm2-paid-in-capital'
9. THE GtM2PaidInCapital.vue SHALL 支持selfLoad
10. THE M2 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M2-{sheet}-{field}"
11. THE 未迁移sheet SHALL 走 OnlyOffice fallback

### Requirement 2: 审定表M2-1（权益类贷方科目）

**User Story:** As a 审计助理, I want to 在精美审定表中查看实收资本数据, so that 我能验证权益类科目的期末余额。

#### Acceptance Criteria

1. THE Adjudication_M2_1 SHALL 渲染为单区块：实收资本(贷方/权益，按出资人/股东分类+小计)
2. THE Adjudication_M2_1 SHALL 显示列：项目 | 期初 | 贷方发生(增资) | 借方发生(减资) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益类：**期末=期初+贷方-借方**（增资在贷方，减资在借方）
5. THE Adjudication_M2_1 SHALL 与M2-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4001)+发布'substantive:adjudicated'
7. THE Adjudication_M2_1 SHALL subscribe附注EventBus刷新

### Requirement 3: 明细表M2-2（上市/非上市双版本分支选择器）

**User Story:** As a 审计助理, I want to 根据企业类型切换上市/非上市明细版本, so that 明细结构与企业性质匹配。

#### Acceptance Criteria

1. THE Detail_M2_2 SHALL 提供 el-segmented 分支选择器：上市公司版 / 非上市公司版
2. WHEN 选择"上市公司版" SHALL 渲染 Detail_Listed_M2_2（38×36，列：股东名称|股份性质|期初股数|本期增加|本期减少|期末股数|持股比例）
3. WHEN 选择"非上市公司版" SHALL 渲染 Detail_Unlisted_M2_2（37×24，列：出资人|出资方式|期初出资|本期增资|本期减资|期末出资|出资比例）
4. THE Detail_M2_2 SHALL 自动计算：期末=期初+本期增加-本期减少（权益类）
5. THE Detail_M2_2 SHALL 36列宽表拆分：按出资人信息/增减变动/比例区段Tab（行同步）
6. THE Detail_M2_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入出资人名）+导入导出
7. THE Detail_M2_2 SHALL 与M2-1审定表交叉验证

### Requirement 4: 外币投资汇率测算表M2-4（外币出资折算）

**User Story:** As a 审计助理, I want to 对外币出资按汇率折算, so that 外币出资折算准确。

#### Acceptance Criteria

1. THE FX_Invest_M2_4 SHALL 显示列：出资人 | 原币出资 | 币种 | 出资日汇率 | 折算本位币 | 账面本位币 | 折算差异
2. THE FX_Engine SHALL 计算折算本位币=原币出资×出资日汇率
3. THE FX_Engine SHALL 计算折算差异=折算本位币-账面本位币
4. WHEN |折算差异|>阈值时 SHALL 红色高亮+提示（差异计入资本公积M4）
5. THE FX_Invest_M2_4 SHALL 13公式全部前端实时计算

### Requirement 5: 验资核对（检查表M2-5）

**User Story:** As a 审计助理, I want to 核对实收资本与验资报告, so that 出资真实性得到验证。

#### Acceptance Criteria

1. THE Capital_Check_M2_5 SHALL 显示列：出资人 | 认缴出资 | 实缴出资 | 验资金额 | 差异 | 验资机构
2. THE Verify_Engine SHALL 计算验资差异=实缴出资-验资金额
3. THE Verify_Engine SHALL 计算出资到位率=实缴出资/认缴出资
4. WHEN |验资差异|>阈值时 SHALL 红色高亮
5. THE Capital_Check_M2_5 SHALL 提供核对清单+审计结论区（el-card包裹）+AI辅助按钮

### Requirement 6: 调整分录M2-3 + 附注

**User Story:** As a 审计助理, I want to 管理调整分录并生成附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_M2_3 SHALL 借贷平衡校验+EventBus+双向同步M2-1
2. THE Disclosure_Listed/SOE SHALL 根据企业类型自动切换附注模板
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 7: 引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现外币折算+验资核对纯函数引擎并集成标准能力, so that 差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE FX_Engine SHALL calcFxConverted(amount, rate)=amount×rate
2. THE FX_Engine SHALL calcFxDiff(converted, booked)=converted-booked
3. THE Verify_Engine SHALL calcVerifyDiff(paid, verified)=paid-verified
4. THE Verify_Engine SHALL calcPaidInRate(paid, subscribed)=paid/subscribed
5. THE Formula_Engine SHALL calcEquityEndBalance(begin, credit, debit)=begin+credit-debit
6. THE M2 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
7. THE M2 SHALL 支持导入导出三级（useM2ImportExport，http带Authorization）
8. THE M2 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
