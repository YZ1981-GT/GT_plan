# Requirements Document: H4 工程物资底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + H4↔H2在建工程联动
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useH4ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase0(双源输入)+Phase1(注册)+Phase2(公式引擎)+Phase3(composable)+Phase4(Vue组件)+Phase5(后端)+Phase6(集成)+Phase7(测试)排序

## Introduction

H4工程物资底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h4-engineering-materials`，覆盖来自 `H4 工程物资.xlsx` 的13个有效sheet（含GT_Custom占位）。科目覆盖1605工程物资（借方/资产类）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

H4工程物资是H循环中相对精简的底稿，但仍需完整覆盖：审定表(51公式)+明细表(20公式)+增加/减少检查+盘点+减值+关联交易。核心联动：H4审定→H2在建工程物资消耗、H4减少→H2转入在建。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录，25行8列，sheet导航+进度统计
- **Procedure_Table_H4A**: 工程物资实质性程序表H4A，29行12列，审计程序清单（复用a-program-console）
- **Adjudication_H4_1**: 审定表H4-1，64行10列51公式，科目1605工程物资
- **Disclosure_Listed**: 附注披露信息（上市公司），14行254列
- **Disclosure_SOE**: 附注披露信息（国有企业），12行254列
- **Detail_H4_2**: 明细表H4-2，51行67列20公式，按物资分类的宽表
- **Adjustment_H4_3**: 调整分录汇总H4-3，22行10列
- **Addition_Check_H4_4**: 增加检查表H4-4，42行19列，新增物资凭证核对
- **Disposal_Check_H4_5**: 减少检查表H4-5，40行29列，领用/转出核对+联动H2
- **Stocktake_Check_H4_6**: 盘点检查表H4-6，43行12列，实物盘点逐项核对
- **Impairment_H4_7**: 减值测算表H4-7，31行31列15公式，可收回金额vs账面
- **Recoverable_H4_8**: 可收回金额测试表H4-8，58行28列12公式，DCF测试
- **Related_Party_H4_9**: 关联交易检查表H4-9，97行16列
- **Cross_Sheet_Engine**: 跨sheet公式引擎，H4-1→H4-2/H4-4/H4-5联动
- **Formula_Engine**: 前端公式引擎composable，资产类借方科目公式（期末=期初+借方-贷方；审定=未审+AJE+RJE）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件
- **AI_Assistant**: AI辅助生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1605，资产类/借方）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H4工程物资底稿按sheetName prop分发到独立子组件, so that 13个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE H4 组件 SHALL 注册新componentType: `h4-engineering-materials`，主入口为 GtH4EngineeringMaterials.vue
2. THE GtH4EngineeringMaterials.vue SHALL 接收 `sheetName` prop（完整中文名），用正则提取末尾编码(H4-1/H4-2/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE H4 组件 SHALL 使用 defineAsyncComponent 对所有子组件（除H4TabIndex外）进行懒加载
4. THE H4 组件 SHALL 将子组件按功能域拆分为独立子目录：h4/core/、h4/inspection/、h4/impairment/
5. THE H4 组件 SHALL 拆分为composable层：useH4FormData.ts + useH4FormulaEngine.ts(纯函数) + useH4CrossSheet.ts + useH4DualMode.ts + useH4ImportExport.ts + sheet-specific composables
6. THE H4 组件 SHALL 在htmlRendererRegistry中注册'h4-engineering-materials'→GtH4EngineeringMaterials映射
7. THE H4 组件 SHALL 在wp_code_overrides.json中将H4/H4-1~H4-9/H4A映射为'h4-engineering-materials'
8. THE H4 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h4-engineering-materials'
9. THE GtH4EngineeringMaterials.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=h4-engineering-materials）
10. THE H4 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H4-{sheet编号}-{field}"格式

### Requirement 2: 审定表H4-1（资产类借方科目51公式）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑工程物资审定表, so that 我能清晰地看到各类物资的审定数据并自动验证三角勾稽。

#### Acceptance Criteria

1. THE Adjudication_H4_1 SHALL 渲染为固定结构：工程物资分类行（按物资类别）+ 小计 + 合计
2. THE Adjudication_H4_1 SHALL 显示以下列：项目 | 期初余额 | 本期借方发生(增加) | 本期贷方发生(减少) | 期末余额 | 未审数 | AJE | RJE | 审定数
3. WHEN 用户编辑未审数/AJE/RJE单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+AJE+RJE）
4. THE Formula_Engine SHALL 自动校验：期末余额=期初余额+借方发生-贷方发生（资产类借方科目1605）
5. THE Adjudication_H4_1 SHALL 自动计算合计行（=SUM所有分类行），合计行不可编辑
6. THE Adjudication_H4_1 SHALL 在底部显示试算平衡表数行（自动从TB取数科目1605）和差异行（=审定数-试算表数），差异不为零时红色高亮
7. WHEN 审定数与H4-2合计行不一致时, THE Adjudication_H4_1 SHALL 显示黄色警告"审定数≠H4-2合计，差额：±xxx元"
8. WHEN 审定数计算完成且发生变化时, THE Adjudication_H4_1 SHALL 调用writebackTrialBalance将最新审定数回写trial_balance.audited_amount（科目1605）并通过EventBus发布'substantive:adjudicated'事件
9. THE Adjudication_H4_1 SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮）和"审计结论"区域
10. THE Adjudication_H4_1 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 3: 明细表H4-2（67列宽表拆分3区段Tab）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理工程物资明细, so that 我能通过3个区段Tab分别查看基础信息/入库变动/出库变动而无需大量横滚。

#### Acceptance Criteria

1. THE Detail_H4_2 SHALL 将67列拆分为3个区段Tab：基础(物资分类/名称/规格/数量/单位/供应商) | 入库(期初金额/本期采购/其他增加/入库小计) | 出库(领用出库/退货/报废/其他减少/期末余额)
2. THE Detail_H4_2 SHALL 在3个区段Tab切换时保持行同步（选中行高亮跨Tab一致）
3. THE Formula_Engine SHALL 自动计算每行：期末余额=期初+入库合计-出库合计
4. THE Detail_H4_2 SHALL 在底部显示合计行（=SUM所有物资行各金额列），合计行不可编辑
5. THE Detail_H4_2 SHALL 对合计行与H4-1审定表进行交叉验证：明细合计=H4-1审定数
6. WHEN 用户点击"添加物资行"按钮时, THE Detail_H4_2 SHALL 弹出ElMessageBox.prompt输入物资分类名称后新增一行
7. THE Detail_H4_2 SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
8. THE Detail_H4_2 SHALL 支持导入导出（el-dropdown三级：导出模板/导出数据/导入数据）
9. THE Detail_H4_2 SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮）

### Requirement 4: 调整分录H4-3

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理工程物资调整分录, so that 我能快速创建AJE/RJE并联动审定表。

#### Acceptance Criteria

1. THE Adjustment_H4_3 SHALL 显示10列：序号 | 调整事项说明 | 类别(AJE/RJE) | 科目代码 | 科目名称 | 摘要 | 借方金额 | 贷方金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_H4_3 SHALL 新增一行可编辑空行
3. THE Adjustment_H4_3 SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_H4_3 SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='H4'/entryType/amount）
5. THE Adjustment_H4_3 SHALL 双向同步AJE/RJE合计到 Adjudication_H4_1 对应列
6. THE Adjustment_H4_3 SHALL 支持导入导出（el-dropdown三级）

### Requirement 5: 增加检查表H4-4

**User Story:** As a 审计助理, I want to 检查本期新增工程物资的真实性和计价准确性, so that 我能验证入库单/发票/合同是否一致。

#### Acceptance Criteria

1. THE Addition_Check_H4_4 SHALL 显示19列：序号 | 物资名称 | 规格型号 | 数量 | 单价 | 金额 | 供应商 | 合同编号 | 入库日期 | 入库单号 | 发票号 | 发票金额 | 差异 | 验收人 | 抽凭结果 | 附件 | 核查结论 | 备注 | 索引
2. THE Addition_Check_H4_4 SHALL 自动计算差异列：差异=金额-发票金额
3. WHEN 差异绝对值>0时, THE Addition_Check_H4_4 SHALL 红色高亮差异单元格
4. THE Addition_Check_H4_4 SHALL 支持行级抽凭（GtVoucherSamplingEngine dialog）
5. THE Addition_Check_H4_4 SHALL 支持附件列📎上传+OCR识别（复用/d4/contract-ocr端点）
6. THE Addition_Check_H4_4 SHALL 支持动态行新增（ElMessageBox.prompt输入物资名称）
7. THE Addition_Check_H4_4 SHALL 在底部显示统计摘要：已检查x笔/总金额xxx/差异笔数x

### Requirement 6: 减少检查表H4-5（联动H2在建工程）

**User Story:** As a 审计助理, I want to 检查本期工程物资减少的合规性, so that 我能验证领用出库/退货/报废是否有据可查且与H2在建工程一致。

#### Acceptance Criteria

1. THE Disposal_Check_H4_5 SHALL 显示29列，拆为2区块：基础(序号/物资名/规格/数量/金额/减少原因/日期) | 证据(领料单号/领用部门/领用工程项目/审批人/对应H2编号/核查结论/备注/索引)
2. THE Disposal_Check_H4_5 SHALL 对"减少原因"提供下拉选项：领用出库/退货/报废/盘亏/其他
3. WHEN 减少原因为"领用出库"时, THE Disposal_Check_H4_5 SHALL 要求填写"对应H2编号"列，并提供GtIndexChip跳转到H2在建工程对应行
4. THE Disposal_Check_H4_5 SHALL 支持行级抽凭（GtVoucherSamplingEngine dialog）
5. THE Disposal_Check_H4_5 SHALL 支持动态行新增
6. THE Disposal_Check_H4_5 SHALL 在底部显示合计行（本期减少合计金额）

### Requirement 7: 盘点检查表H4-6 + 减值测算H4-7/H4-8

**User Story:** As a 审计助理, I want to 完成工程物资的盘点核对和减值测试, so that 我能确认物资存在性并评估是否存在减值迹象。

#### Acceptance Criteria

1. THE Stocktake_Check_H4_6 SHALL 显示12列：序号 | 物资名称 | 规格 | 账面数量 | 账面金额 | 盘点数量 | 盘点金额 | 差异数量 | 差异金额 | 存放位置 | 盘点日期 | 备注
2. THE Stocktake_Check_H4_6 SHALL 自动计算差异：差异数量=盘点数量-账面数量；差异金额=盘点金额-账面金额
3. WHEN 差异不为零时, THE Stocktake_Check_H4_6 SHALL 黄色高亮差异行
4. THE Impairment_H4_7 SHALL 以OnlyOffice渲染（31行31列15公式，复杂矩阵计算）
5. THE Recoverable_H4_8 SHALL 以OnlyOffice渲染（58行28列12公式，DCF资产组测试）
6. THE Impairment_H4_7/H4_8 SHALL 支持双模式切换（OO ↔ HTML简化视图）

### Requirement 8: 关联交易检查表H4-9

**User Story:** As a 审计助理, I want to 检查工程物资采购中的关联交易, so that 我能识别非公允定价和异常关联采购。

#### Acceptance Criteria

1. THE Related_Party_H4_9 SHALL 显示16列：序号 | 物资名称 | 交易对手 | 关联关系 | 交易金额 | 市场价格 | 价差率 | 合同日期 | 合同编号 | 定价依据 | 审批流程 | 是否公允 | 决策程序 | 披露情况 | 核查结论 | 备注
2. THE Formula_Engine SHALL 自动计算：价差率=(交易金额-市场价格)/市场价格×100%
3. WHEN 价差率绝对值>10%时, THE Related_Party_H4_9 SHALL 红色高亮该行
4. THE Related_Party_H4_9 SHALL 支持动态行新增
5. THE Related_Party_H4_9 SHALL 在底部显示统计摘要：关联交易笔数/总金额/异常笔数
