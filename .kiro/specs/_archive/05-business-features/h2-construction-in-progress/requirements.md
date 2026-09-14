# Requirements Document: H2 在建工程底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型），产出结构化摘要。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/H固定资产循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用/适用性条件/核心必做清单）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准（模板是最终交付物）；联动方向/认定映射/适用性规则以md为准（是方法论设计文档）。

### 功能方向（每个sheet组件必须考虑）

- **联动性**：跨sheet computed链 + 跨底稿EventBus + TB回写 + H2→H1转固联动
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级(导出模板/导出数据/导入数据) + useH2ImportExport composable
- **AI辅助**：多section按区域(/ai-generate端点) + 弹确认预览再填入
- **双/三模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md：每个功能域一个Requirement，Acceptance Criteria引用xlsx列头+md业务场景
- design.md：文件结构+composable接口+跨sheet数据流图+correctness properties
- tasks.md：按Phase0(双源输入)+Phase1(注册)+Phase2(公式引擎)+Phase3(composable)+Phase4(Vue组件)+Phase5(后端)+Phase6(集成)+Phase7(测试)排序

## Introduction

H2在建工程底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `h2-construction-in-progress`，覆盖来自 `H2 在建工程.xlsx` 的21个有效sheet。科目覆盖1604在建工程（借方/资产类）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发，外层GtWpRenderer提供目录行chips导航）。核心关注：在建工程三角勾稽（期末=期初+增加-减少-转固）、利息资本化2分支（有/无专门借款）、转固联动H1、工程造价比较、C7前置驱动。关键公式总数约130+。

## Glossary

- **Tab_Index**: 底稿目录，24行8列，sheet导航+进度统计
- **Procedure_Table_H2A**: 在建工程实质性程序表H2A，36行12列，审计程序清单（复用a-program-console）
- **Adjudication_H2_1**: 审定表H2-1，84行12列，科目1604在建工程（借方/资产类）；列结构=期初/期末×未审/账项调整/审定+同期比较（以xlsx为准，见 h2_conflict_resolution.md）
- **Disclosure_Listed**: 附注披露信息（上市公司），57行256列
- **Disclosure_SOE**: 附注披露信息（国有企业），47行255列
- **Detail_H2_2**: 明细表H2-2，48行50列，宽表拆分4区段Tab（基本信息/账面原值/审定原值/减值与净值）；三角勾稽在本表实施
- **Adjustment_H2_3**: 调整分录汇总H2-3，24行10列
- **Analysis_H2_4**: 分析表H2-4，25行24列10公式，含完工率/资本化率/工期分析
- **Transfer_Check_H2_5**: 转固时点检查表H2-5，28行15列，核心联动H1
- **Review_Record_H2_6**: 在建工程审核记录H2-6，39行12列，工程进度审核签章式
- **Cost_Comparison_H2_7**: 工程造价比较表H2-7，23行16列14公式，预算vs实际
- **Addition_Check_H2_8**: 增加检查表H2-8，57行24列
- **Decrease_Check_H2_9**: 减少检查表H2-9，44行27列
- **Interest_Cap_NoBorrow_H2_10**: 利息资本化测算表（无专门借款）H2-10，78行28列12公式
- **Interest_Cap_WithBorrow_H2_11**: 利息资本化测算表（有专门借款）H2-11，48行28列15公式
- **Stocktake_Plan_H2_12**: 监盘计划H2-12
- **Stocktake_Check_H2_13**: 盘点检查表H2-13
- **Stocktake_Summary_H2_14**: 监盘小结H2-14
- **Impairment_H2_15**: 减值测算表H2-15，34行28列15公式
- **Recoverable_H2_16**: 可收回金额测试表H2-16，63行28列12公式
- **Related_Party_H2_17**: 关联交易检查表H2-17，102行15列
- **Cross_Sheet_Engine**: 跨sheet公式引擎，H2-2→H2-1/H2-4；H2-5转固交叉验证；H2-10~11→H2-2利息列
- **Formula_Engine**: 前端公式引擎composable；H2-1审定=未审+账项调整；H2-2可拆AJE+RJE后合计为账项调整；三角勾稽期末=期初+增加-减少-转固（在H2-2）
- **Interest_Cap_Engine**: 利息资本化计算引擎，2分支：无专门借款（加权资本化率×累计支出加权）/有专门借款（专门借款利息-闲置收益+一般借款补充资本化）
- **Triangle_Reconciliation**: 三角勾稽，期末=期初+增加-减少-转固（在明细表H2-2实施；H2-1仅展示跨sheet差异警告）
- **Branch_Selector**: 分支选择器，H2-10/H2-11利息资本化2版本切换（无/有专门借款）
- **Dynamic_Row**: 动态行，用户可新增/删除的数据行
- **Summary_Row**: 合计行，自动SUM对应明细行（不可编辑）
- **Dual_Mode**: 双模式切换，HTML精美组件 ↔ OnlyOffice在线编辑
- **EventBus**: 进程内事件总线，跨底稿联动通信
- **GtIndexChip**: 交叉索引跳转芯片，点击跳转到目标底稿/位置
- **Review_Dialog**: 通用复核对话组件，任意位置可发起复核线程
- **AI_Assistant**: AI辅助生成，审计说明/变动分析/资本化说明等文本自动生成
- **Trial_Balance_Writeback**: 审定数回写试算平衡表（科目1604，资产类/借方）
- **FixedAssetStocktakeDialog**: 固定资产监盘对话组件（复用H1模式）
- **CAS4_Transfer_Condition**: CAS4转固五条件（达到预定可使用状态判断）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to H2在建工程底稿按sheetName prop分发到独立子组件, so that 21个sheet在一个统一入口中有序组织且代码可维护。

#### Acceptance Criteria

1. THE H2 组件 SHALL 注册新componentType: `h2-construction-in-progress`，主入口为 GtH2ConstructionInProgress.vue
2. THE GtH2ConstructionInProgress.vue SHALL 接收 `sheetName` prop（完整中文名），用正则提取末尾编码(H2-1/H2-2/...)，v-if 分发到对应子组件；未迁移sheet走OnlyOffice fallback
3. THE H2 组件 SHALL 使用 defineAsyncComponent 对所有子组件（除H2TabIndex外）进行懒加载
4. THE H2 组件 SHALL 将子组件按功能域拆分为独立子目录：h2/core/、h2/inspection/、h2/stocktake/、h2/interest/、h2/impairment/
5. THE H2 组件 SHALL 拆分为composable层：useH2FormData.ts + useH2FormulaEngine.ts(纯函数) + useH2CrossSheet.ts + useH2DualMode.ts + useH2ImportExport.ts + useH2InterestCapEngine.ts(纯函数) + sheet-specific composables
6. THE H2 组件 SHALL 在htmlRendererRegistry中注册'h2-construction-in-progress'→GtH2ConstructionInProgress映射
7. THE H2 组件 SHALL 在wp_code_overrides.json中将H2/H2-1~H2-17/H2A映射为'h2-construction-in-progress'
8. THE H2 组件 SHALL 在VALID_COMPONENT_TYPES中注册'h2-construction-in-progress'
9. THE GtH2ConstructionInProgress.vue SHALL 支持selfLoad（当htmlData prop为null时自行调render-config?force_component_type=h2-construction-in-progress）
10. THE H2 组件 SHALL 使用 checklist_responses 表存储数据，item_id前缀为"H2-{sheet编号}-{field}"格式

### Requirement 2: 审定表H2-1（期初/期末×未审/账项调整/审定 + 同期比较）

**User Story:** As a 审计助理, I want to 在精美HTML表格中查看和编辑在建工程审定表, so that 我能清晰看到各工程原值/减值/净值的期初与期末审定，并与 H2-2、TB、H2-5 交叉验证。

> **权威来源**：列名/列组以 `H2 在建工程.xlsx` 为准（见 `h2_conflict_resolution.md` 冲突#1~#3）。  
> 增减/转固列属于 H2-2，**不**出现在 H2-1。三角勾稽在 H2-2 实施；H2-1 仅展示跨 sheet 差异警告。

#### Acceptance Criteria

1. THE Adjudication_H2_1 SHALL 渲染为三块结构：一、原值(1604) → 二、减值准备 → 三、净值(=原值−减值)；各块按工程项目分行（行数动态）+ 小计/合计行
2. THE Adjudication_H2_1 SHALL 显示以下列（xlsx 12 列）：项目 | 期初数{未审数, 账项调整, 审定数} | 期末数{未审数, 账项调整, 审定数} | 本期未审与上期未审比较{变动额, 变动率} | 本期审定与上期审定比较{变动额, 变动率}
3. WHEN 用户编辑未审数/账项调整单元格时, THE Formula_Engine SHALL 自动计算审定数（=未审+账项调整）；表单层可将 AJE/RJE 分录录入后合并写入「账项调整」单列
4. THE Adjudication_H2_1 SHALL NOT 在本表对行实施三角勾稽（期末=期初+增加-减少-转固）；该校验由 Detail_H2_2 实施
5. THE Adjudication_H2_1 SHALL 自动计算合计行（=SUM 所有工程项目行各金额列），合计行不可编辑；净值行按原值−减值派生
6. WHEN H2-2 三角勾稽存在差额时, THE Adjudication_H2_1 SHALL 展示跨 sheet 差额警告（来自 H2-2），不得在本表假造增减/转固列做校验
7. THE Adjudication_H2_1 SHALL 在底部显示试算平衡表核对（科目1604在建工程，并可核对1605工程物资）和差异行（=审定数-试算表数），差异不为零时红色高亮
8. WHEN 审定数合计与H2-2合计行不一致时, THE Adjudication_H2_1 SHALL 显示黄色警告"审定数≠H2-2明细合计，差额：±xxx元"
9. WHEN H2-2/H2-5 转固合计与交叉验证口径不一致时, THE Adjudication_H2_1 SHALL 显示黄色警告"转固数≠H2-5合计，差额：±xxx元"（转固金额取自 H2-2/H2-5，非本表列）
10. THE Adjudication_H2_1 SHALL 在底部显示结构化审计说明（含净值重大变动原因/本期转入固定资产情况等）+ AI生成 + GtIndexChip，以及审计结论区域
11. WHEN 审定数计算完成且发生变化时, THE Adjudication_H2_1 SHALL 调用writebackTrialBalance将最新审定数回写trial_balance.audited_amount（科目1604）并通过EventBus发布'substantive:adjudicated'事件
12. THE Adjudication_H2_1 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）
13. WHEN 净值变动率绝对值≥30%时, THE Adjudication_H2_1 SHALL 标红并要求在审计说明中解释重大变动原因

### Requirement 3: 明细表H2-2（50列宽表拆分4区段Tab + 三角勾稽）

**User Story:** As a 审计助理, I want to 在精美HTML宽表中管理在建工程明细, so that 我能通过4个区段Tab分别查看基本信息/账面原值/审定原值/减值与净值，并自动验证三角勾稽。

#### Acceptance Criteria

1. THE Detail_H2_2 SHALL 将宽表拆分为4个区段Tab：基本信息(工程名称/预算/进度/状态/资金来源等) | 账面原值(期初+增分项−转固−其他减=期末；利息子列) | 审定原值(期初/账项调整→审定；与H2-1交叉验证) | 减值与净值
2. THE Detail_H2_2 SHALL 在4个区段Tab切换时保持行同步（选中行高亮跨Tab一致）
3. THE Formula_Engine SHALL 自动计算每行：期末余额=期初+增加合计-减少-转固；增加合计=材料+人工+机械+利息+其他；完工进度=累计投入/预算×100%；并实施三角勾稽校验，失败时红色高亮差额
4. THE Detail_H2_2 SHALL 在底部显示合计行（=SUM所有工程项目行各金额列），合计行不可编辑
5. THE Detail_H2_2 SHALL 对合计行与H2-1审定表进行交叉验证：期末余额合计=H2-1审定数合计
6. WHEN 用户点击"添加工程项目"按钮时, THE Detail_H2_2 SHALL 弹出ElMessageBox.prompt输入工程名称后新增一行
7. THE Detail_H2_2 SHALL 固定前2列（工程名称/预算金额）使各区段Tab内横滚时仍可辨识行
8. THE Detail_H2_2 SHALL 对所有金额列应用右对齐+金额格式化（千分位/负数红色括号/零值"-"）
9. WHEN 完工进度>100%时, THE Detail_H2_2 SHALL 以红色高亮该行提示"超预算"
10. THE Detail_H2_2 SHALL 在底部显示"审计说明"区域（textarea + AI生成按钮）和"审计结论"区域
11. THE Detail_H2_2 SHALL 支持导入导出（el-dropdown三级：导出模板/导出数据/导入数据；导出按4区段分sheet）
12. THE Detail_H2_2 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 4: 调整分录H2-3

**User Story:** As a 审计助理, I want to 在精美HTML表格中录入和管理在建工程调整分录, so that 我能快速创建AJE/RJE并联动审定表和A13错报汇总。

#### Acceptance Criteria

1. THE Adjustment_H2_3 SHALL 显示10列：序号 | 调整事项说明 | 类别(AJE/RJE) | 科目代码 | 科目名称 | 摘要 | 借方金额 | 贷方金额 | 索引 | 备注
2. WHEN 用户点击"新增调整分录"按钮时, THE Adjustment_H2_3 SHALL 新增一行可编辑空行
3. THE Adjustment_H2_3 SHALL 在底部显示借贷合计行，借方合计=贷方合计时显示绿色"✓平衡"，否则红色"✗不平衡：差额xxx"
4. WHEN 调整分录保存成功时, THE Adjustment_H2_3 SHALL 通过EventBus发布'adjustment:created'事件（payload含wpCode='H2'/entryType/amount）
5. THE Adjustment_H2_3 SHALL 双向同步AJE/RJE合计到 Adjudication_H2_1 对应列
6. WHEN 用户点击"推送至A13"按钮时, THE Adjustment_H2_3 SHALL 将选中分录通过EventBus发布至A13错报汇总
7. THE Adjustment_H2_3 SHALL 在底部显示编制提示（`<details>`折叠，琥珀色左边线+浅黄背景，默认收起）
8. THE Adjustment_H2_3 SHALL 支持导入导出（el-dropdown三级）

### Requirement 5: 分析表H2-4（10公式，含完工率/资本化率/工期分析）

**User Story:** As a 审计助理, I want to 在精美HTML组件中查看在建工程分析, so that 我能直观判断工程进度是否合理、资本化金额是否异常。

#### Acceptance Criteria

1. THE Analysis_H2_4 SHALL 渲染为三区域结构：(1)工程进度分析（各工程完工率/超期情况）+ (2)资本化率分析（利息资本化率/总投入占预算比）+ (3)工期分析（预计vs实际工期/逾期天数）
2. THE Formula_Engine SHALL 自动计算10个公式：完工率=累计投入/预算；资本化率=资本化利息/总利息支出；工期偏差=实际工期-预计工期；投入增长率=(本期投入-上期投入)/上期；预算执行率=累计投入/调整后预算；剩余投资=预算-累计投入；单位造价=累计投入/建筑面积(或数量)；超预算率=(累计投入-预算)/预算；年化资本化金额=本期资本化/资本化月数×12；完工百分比偏差=完工率-形象进度
3. THE Analysis_H2_4 SHALL 从H2-2明细表自动取数（各工程期初/增加/转固/期末/预算）
4. WHEN 工期偏差>180天时, THE Analysis_H2_4 SHALL 以红色高亮该工程行提示"严重超期，需评估减值迹象"
5. WHEN 超预算率>20%时, THE Analysis_H2_4 SHALL 以黄色高亮显示并在审计说明区自动标记需关注项
6. THE Analysis_H2_4 SHALL 在底部显示"审计说明"textarea（AI生成按钮，基于异常项自动生成）和"审计结论"textarea
7. THE Analysis_H2_4 SHALL 通过GtIndexChip跳转H2-5转固/H2-7造价比较的对应检查详情
8. THE Analysis_H2_4 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 6: 转固时点检查表H2-5（核心联动H1，CAS4转固条件判断）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行转固时点检查, so that 我能验证各工程项目是否在达到预定可使用状态时及时转固，并联动H1固定资产入账。

#### Acceptance Criteria

1. THE Transfer_Check_H2_5 SHALL 显示15列：工程名称 | 转固日期 | 转固金额 | 条件1(实体建造完成) | 条件2(达到设计要求) | 条件3(试运转合格) | 条件4(竣工决算已办or可确定) | 条件5(已投入使用or可使用) | 五条件全满足 | 是否及时转固 | 延迟天数 | 对应H1资产 | H1入账金额 | 差异 | 备注
2. THE Transfer_Check_H2_5 SHALL 对CAS4转固五条件自动判定：当5个条件列全部为"Y"时，"五条件全满足"自动显示"✓"
3. WHEN 五条件全满足且转固日期为空时, THE Transfer_Check_H2_5 SHALL 以红色高亮该行并提示"已达预定可使用状态，应及时转固"
4. WHEN 转固日期晚于五条件满足日期>30天时, THE Transfer_Check_H2_5 SHALL 计算延迟天数并以黄色高亮提示"转固延迟{N}天"
5. THE Transfer_Check_H2_5 SHALL 对每行验证：转固金额=对应H1入账金额（差异列自动计算），差异≠0时红色高亮
6. THE Transfer_Check_H2_5 SHALL 在底部显示转固合计（=SUM转固金额），并与H2-1"本期转固"列合计交叉验证
7. THE Transfer_Check_H2_5 SHALL 在"对应H1资产"列提供GtIndexChip跳转至H1固定资产审定表对应行
8. THE Transfer_Check_H2_5 SHALL 通过EventBus发布'h2:transfer-to-h1'事件（payload含工程名/金额/日期），H1订阅后验证一致性
9. THE Transfer_Check_H2_5 SHALL 在顶部显示方法论上下文区域（琥珀色左边线+浅黄背景，CAS4第9条关于转固时点判断的准则原文摘要）
10. THE Transfer_Check_H2_5 SHALL 在底部显示"审计说明"textarea（AI + 💬复核）和"审计结论"textarea

### Requirement 7: 审核记录H2-6（工程进度审核，签章式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中记录在建工程审核过程, so that 我能逐项记录工程进度审核意见并形成签章式审核记录。

#### Acceptance Criteria

1. THE Review_Record_H2_6 SHALL 渲染为签章式审核记录卡片：(1)工程基本信息区 + (2)审核事项逐条区 + (3)审核结论+签名区
2. THE Review_Record_H2_6 SHALL 在审核事项区显示12列：审核事项 | 审核内容 | 合同约定 | 实际情况 | 差异 | 审核意见 | 是否异常 | 进一步程序 | 证据索引 | 审核人 | 日期 | 备注
3. THE Review_Record_H2_6 SHALL 在签名区显示编制人/复核人/日期签章格式（只读展示已保存的签章信息）
4. THE Review_Record_H2_6 SHALL 在底部显示整体审核结论区域（textarea + AI生成按钮 + 💬复核）
5. THE Review_Record_H2_6 SHALL 支持按工程项目筛选显示（el-select工程名称列表，来源H2-2）

### Requirement 8: 工程造价比较表H2-7（预算vs实际14公式，差异分析）

**User Story:** As a 审计助理, I want to 在精美HTML表格中对比在建工程预算与实际造价, so that 我能分析各项工程的造价偏差并评估合理性。

#### Acceptance Criteria

1. THE Cost_Comparison_H2_7 SHALL 显示16列：工程名称 | 合同预算 | 调整预算 | 预算变更说明 | 累计实际支出-材料 | 累计实际支出-人工 | 累计实际支出-机械 | 累计实际支出-其他 | 累计实际合计 | 超支金额 | 超支率 | 节余金额 | 节余率 | 预算执行率 | 造价偏差原因 | 备注
2. THE Formula_Engine SHALL 自动计算14个公式：累计实际合计=材料+人工+机械+其他；超支金额=实际-调整预算(正值)；超支率=超支金额/调整预算×100%；节余金额=调整预算-实际(正值)；节余率=节余金额/调整预算×100%；预算执行率=累计实际/调整预算×100%；材料占比=材料/合计；人工占比=人工/合计；机械占比=机械/合计；变更率=(调整预算-合同预算)/合同预算；单位造价=合计/工程量；造价指数=本期实际/上期实际；资金使用率=实际支付/累计实际；结转率=已转固/累计实际
3. THE Cost_Comparison_H2_7 SHALL 从H2-2明细表自动取数（各工程累计投入分项）
4. WHEN 超支率>10%时, THE Cost_Comparison_H2_7 SHALL 以红色高亮超支率单元格
5. WHEN 预算执行率>100%时, THE Cost_Comparison_H2_7 SHALL 以红色高亮预算执行率单元格
6. THE Cost_Comparison_H2_7 SHALL 在底部显示合计行 + 审计说明textarea（AI + 💬复核）
7. THE Cost_Comparison_H2_7 SHALL 在工程名称列提供GtIndexChip跳转至H2-2明细表对应行

### Requirement 9: 增加/减少检查表H2-8/H2-9（含抽凭+OCR）

**User Story:** As a 审计助理, I want to 在精美HTML表格中执行在建工程增加/减少检查, so that 我能逐笔核对工程投入的入账依据和减少的合规性。

#### Acceptance Criteria

1. THE Addition_Check_H2_8 SHALL 显示为双区域结构：(1)抽样参数区（测试总体/抽样方法/样本量/覆盖率） + (2)增加明细检查表24列
2. THE Addition_Check_H2_8 检查表列：序号 | 工程名称 | 日期 | 摘要 | 金额 | 费用类别(材料/人工/机械/利息/其他) | 合同编号 | 发票号 | 发票金额 | 付款日期 | 付款金额 | 供应商 | 验收单 | 资本化判断 | 计量确认 | 进度确认 | 审批文件 | 质量证明 | 📎附件 | OCR结果 | 审计结论 | GtIndexChip | 抽凭状态 | 备注
3. THE Decrease_Check_H2_9 SHALL 显示为双区域结构：(1)抽样参数区 + (2)减少明细检查表27列
4. THE Decrease_Check_H2_9 检查表列含：工程名称 | 减少日期 | 减少原因(报废/毁损/转出/其他) | 原账面值 | 残值 | 损失金额 | 审批文件 | 评估报告 | 保险理赔 | 审计结论等
5. THE Addition_Check_H2_8/Decrease_Check_H2_9 SHALL 集成抽凭引擎（voucher-sampling-engine）
6. THE Addition_Check_H2_8 SHALL 在📎附件列支持行级OCR：上传后调用contract-ocr端点→ElMessageBox确认→merge填入
7. THE 增加/减少检查表 SHALL 在底部显示汇总统计 + 审计说明textarea（AI + 💬复核）
8. THE 增加/减少检查表 SHALL 支持导入导出（el-dropdown三级）

### Requirement 10: 利息资本化H2-10/H2-11（2分支：无/有专门借款，加权资本化率公式）

**User Story:** As a 审计助理, I want to 在精美HTML组件中测算利息资本化金额, so that 我能验证被审计单位利息资本化金额的准确性，支持无专门借款和有专门借款两种模式。

#### Acceptance Criteria

1. THE Interest_Cap SHALL 使用el-segmented分支选择器在2个版本间切换：(A)无专门借款 → H2TabInterestCapNoBorrow.vue | (B)有专门借款 → H2TabInterestCapWithBorrow.vue
2. THE H2TabInterestCapNoBorrow (H2-10) SHALL 显示28列78行（12公式）：借款明细(借款人/金额/利率/期限/利息) + 累计支出加权平均数计算(各月支出/占用天数/加权金额) + 加权资本化率计算 + 应予资本化金额
3. THE H2TabInterestCapWithBorrow (H2-11) SHALL 显示28列48行（15公式）：专门借款明细(金额/利率/利息/闲置投资收益) + 一般借款补充资本化(累计超额支出×加权资本化率) + 应予资本化金额合计
4. THE Interest_Cap_Engine SHALL 计算无专门借款公式：加权资本化率=Σ(各笔借款利息×权重)/Σ(各笔借款本金×权重)；应予资本化金额=累计支出加权平均数×加权资本化率
5. THE Interest_Cap_Engine SHALL 计算有专门借款公式：专门借款资本化=专门借款利息-闲置收益；一般借款补充资本化=超出专门借款的累计支出加权平均数×一般借款加权资本化率；合计=专门+一般
6. WHEN 计算的资本化金额与被审计单位账面资本化金额差异>重要性水平时, THE Interest_Cap SHALL 以红色高亮差异行
7. THE Interest_Cap SHALL 与H2-2明细表"利息"列交叉验证（资本化合计应=各工程利息列之和）
8. THE Interest_Cap SHALL 在底部显示审计说明textarea（AI生成按钮）+ 审计结论 + 💬复核
9. THE Interest_Cap SHALL 联动L(财务费用)底稿：publish 'h2:interest-capitalized'事件（payload含资本化金额/利息总额/资本化率）
10. THE Interest_Cap SHALL 支持导入导出（el-dropdown三级）

### Requirement 11: 监盘组H2-12~H2-14（复用FixedAssetStocktakeDialog）

**User Story:** As a 审计助理, I want to 在精美HTML组件中完成在建工程监盘全流程（计划→盘点→小结）, so that 我能系统性记录工程现场踏勘情况并追踪实际进度。

#### Acceptance Criteria

1. THE Stocktake_Plan_H2_12 SHALL 渲染为3区域：(1)监盘基本信息（踏勘日期/工程地点/参与人/踏勘范围） + (2)工程选取表（工程名称/选取理由/计划踏勘内容） + (3)时间安排
2. THE Stocktake_Check_H2_13 SHALL 显示盘点检查表：工程名称 | 现场位置 | 形象进度 | 施工状态(施工中/停工/完工) | 施工人员 | 材料堆存 | 设备状况 | 安全措施 | 工程质量观感 | 照片 | 与账面进度差异 | 审计结论 | 备注
3. THE Stocktake_Summary_H2_14 SHALL 渲染为段落型+表格混合：(1)踏勘总体情况 + (2)异常工程清单 + (3)监盘结论
4. THE 监盘组三sheet SHALL 共享FixedAssetStocktakeDialog组件（复用H1模式）
5. WHEN 施工状态为"停工"时, THE Stocktake_Check_H2_13 SHALL 以红色高亮并提示"需评估减值迹象"
6. THE 监盘组 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 12: 减值H2-15/H2-16（DCF资产组）

**User Story:** As a 审计助理, I want to 在精美HTML组件中执行在建工程减值测试, so that 我能评估长期停工/超预算工程的可收回金额。

#### Acceptance Criteria

1. THE Impairment_H2_15 SHALL 渲染为双区域：(1)减值迹象判断区（6项迹象逐条Y/N） + (2)减值测算表（账面值/可收回金额/减值金额）
2. THE Impairment_H2_15 减值迹象6项：①停工超12个月 ②技术淘汰 ③预算超支>50% ④市场环境恶化 ⑤用途变更 ⑥其他迹象
3. THE Recoverable_H2_16 SHALL 渲染DCF模型：(1)假设区（折现率/预测期/增长率/终值） + (2)预测期现金流表 + (3)折现计算 + (4)敏感性分析矩阵
4. THE Formula_Engine SHALL 计算：可收回金额=MAX(公允价值-处置费用, 使用价值DCF)；减值金额=MAX(账面-可收回, 0)
5. WHEN 存在减值迹象≥2项时, THE Impairment_H2_15 SHALL 强制要求完成H2-16可收回金额测试
6. THE Impairment_H2_15 SHALL 在"停工超12个月"迹象处提供GtIndexChip跳转H2-13盘点表（停工状态行）
7. THE 减值组 SHALL 在审计说明/结论区域放置复核对话入口（💬图标）

### Requirement 13: 关联交易H2-17

**User Story:** As a 审计助理, I want to 在精美HTML表格中检查在建工程关联交易, so that 我能评估关联方施工/供材/设计等交易的定价合理性。

#### Acceptance Criteria

1. THE Related_Party_H2_17 SHALL 显示15列：序号 | 关联方名称 | 关联关系 | 交易类型(施工/供材/设计/监理) | 合同金额 | 本期发生额 | 累计发生额 | 定价方式 | 市场价参考 | 价格差异 | 差异率 | 审批文件 | 独立董事意见 | 审计结论 | 备注
2. THE Formula_Engine SHALL 自动计算：价格差异=合同金额-市场价参考；差异率=差异/市场价×100%
3. WHEN 差异率绝对值>10%时, THE Related_Party_H2_17 SHALL 以红色高亮提示"定价偏离市场价>10%"
4. THE Related_Party_H2_17 SHALL 在底部显示合计行（本期发生额合计/累计发生额合计）
5. THE Related_Party_H2_17 SHALL 在底部显示审计说明textarea（AI + 💬复核）
6. THE Related_Party_H2_17 SHALL 支持导入导出（el-dropdown三级）

### Requirement 14: 跨Sheet联动+双模式+导入导出+AI+持久化

**User Story:** As a 审计助理, I want to H2在建工程底稿各sheet之间数据联动且支持双模式切换/导入导出/AI辅助, so that 我的工作流高效且数据一致。

#### Acceptance Criteria

1. THE H2 组件 SHALL 支持双模式切换：HTML精美组件 ↔ OnlyOffice在线编辑（el-segmented + OO健康检查）
2. THE H2 组件 SHALL 在切换到OnlyOffice前自动保存HTML数据
3. THE H2 组件 SHALL 支持导入导出composable（useH2ImportExport.ts，axios请求三端点）
4. THE H2 组件 SHALL 对H2-2宽表导出时按4区段分sheet
5. THE H2 组件 SHALL 支持AI审计说明生成（/h2/ai-generate端点，6 section）
6. THE H2 组件 SHALL 支持跨sheet联动：H2-2→H2-1审定表 / H2-5→H2-1转固列 / H2-10/11→H2-2利息列 / H2-4→分析取数
7. THE H2 组件 SHALL 支持跨底稿联动：H2-5→H1(转固) / H2-10/11→L(财务费用借入端) / C7(前置控制测试)
8. THE H2 组件 SHALL 集成useVersionTrail（autoSnapshot on save）
9. THE H2 组件 SHALL 所有数据存储到checklist_responses表（item_id前缀"H2-"）
10. THE H2 组件 SHALL 集成provide/inject openReviewDialog供子组件使用
