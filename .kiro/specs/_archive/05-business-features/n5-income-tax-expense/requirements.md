# Requirements Document: N5 所得税费用底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/N税费循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **N1/N3递延所得税核对** + **I6/I2研发费用加计扣除接收** + **A类利润表会计利润接收** + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 纳税调整仪表板 + 进度条 + 107行大表虚拟滚动
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级 + useN5ImportExport composable（纳税调整明细分sheet导出）
- **AI辅助**：多section按区域AI + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

N5所得税费用底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `n5-income-tax-expense`，覆盖来自 `N5 所得税费用.xlsx` 的15个sheet（其中N3A原底稿为辅助sheet标记skip）。科目覆盖6801所得税费用（**损益类科目**）。

**N5核心特殊**（N循环最复杂底稿）：①**损益类科目**！取本期发生额（从tb_ledger，与N4同款）②**当期所得税计算**：应纳税所得额=会计利润±纳税调整；当期所得税=应纳税所得额×税率 ③**纳税调整明细107行大表**（调增/调减，虚拟滚动）④研发费用加计扣除（接收I6研发费用/I2开发支出）⑤高新技术企业认定 ⑥税收优惠 ⑦财产损失税前扣除 ⑧**递延所得税费用核对**（接收N1递延税资产/N3递延税负债本期变动）⑨**所得税费用=当期所得税+递延所得税费用**。审定表36公式、明细表8公式、税收优惠10公式、研发加计17公式、财产损失12公式、递延核对12公式。关键公式总数约95+，含82行当期计算表+107行纳税调整大表。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_N5A**: 所得税审计程序表N5A，审计程序清单（复用a-program-console）
- **Adjudication_N5_1**: 所得税费用审定表N5-1，28行14列36公式，损益类科目6801审定（当期+递延，取发生额）
- **Disclosure_Listed**: 附注披露信息（上市公司），29行12列
- **Disclosure_SOE**: 附注披露信息（国有企业），32行255列
- **Detail_N5_2**: 所得税费用明细表N5-2，38行10列8公式
- **Adjustment_N5_3**: 调整分录汇总N5-3，AJE/RJE管理
- **Current_Tax_Calc_N5_4**: 当期所得税费用计算表N5-4，82行7列，应纳税所得额×税率
- **Tax_Adjustment_N5_5**: 纳税调整明细表N5-5，107行8列，调增/调减明细（虚拟滚动）
- **Tax_Benefit_N5_6**: 税收优惠明细表N5-6，54行6列10公式
- **RD_SuperDeduction_N5_6_1**: 加计扣除研发费用情况明细表N5-6-1，43行7列17公式
- **HighTech_Check_N5_6_2**: 高新技术企业认定条件检查表N5-6-2，18行13列
- **Property_Loss_N5_7**: 财产损失明细表N5-7，15行7列12公式
- **Deferred_Tax_Reconcile_N5_8**: 递延所得税费用核对表N5-8，44行10列12公式（接收N1/N3）
- **Income_Tax_Engine**: 所得税计算引擎（当期所得税=应纳税所得额×税率，纯函数）
- **Tax_Adjustment_Engine**: 纳税调整引擎（调增/调减净额，纯函数）
- **Formula_Engine**: 前端公式引擎composable（**损益类！发生额**）
- **Cross_Sheet_Engine**: 跨sheet引擎 + N1/N3/I6/I2/A跨底稿联动
- **Trial_Balance_Writeback**: 审定数回写（科目6801，本期发生额）
- **Skip_Sheet**: 辅助sheet标记skip（N3A原底稿）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to N5所得税费用底稿按sheetName分发, so that 15个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE N5 组件 SHALL 注册新componentType: `n5-income-tax-expense`，主入口为 GtN5IncomeTaxExpense.vue
2. THE GtN5IncomeTaxExpense.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(N5-1/N5-4/N5-6-1等)，v-if分发到子组件
3. THE N5 组件 SHALL 使用 defineAsyncComponent 懒加载各子组件
4. THE N5 组件 SHALL 拆为：n5/core/（审定+明细+调整+附注）、n5/calc/（当期计算+纳税调整+递延核对）、n5/benefit/（税收优惠+研发加计+高新认定+财产损失）
5. THE N5 组件 SHALL composable分层：useN5FormData + useN5FormulaEngine(纯函数) + useN5IncomeTaxEngine(纯函数) + useN5TaxAdjustmentEngine(纯函数) + useN5CrossSheet + useN5DualMode + useN5ImportExport
6. THE N5 组件 SHALL 在htmlRendererRegistry中注册'n5-income-tax-expense'
7. THE N5 组件 SHALL 在wp_code_overrides.json中将N5/N5-1~N5-8/N5-6-1/N5-6-2/N5A映射为'n5-income-tax-expense'
8. THE N5 组件 SHALL 在VALID_COMPONENT_TYPES中注册'n5-income-tax-expense'
9. THE GtN5IncomeTaxExpense.vue SHALL 支持selfLoad（bundle内嵌htmlData为null时自加载）
10. THE N5 组件 SHALL 使用 checklist_responses 存储，item_id前缀"N5-{sheet}-{field}"
11. THE N3A原底稿 SHALL 标记skip（走OnlyOffice fallback，不做HTML组件化）

### Requirement 2: 所得税费用审定表N5-1（损益类！36公式，当期+递延，取发生额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看所得税费用, so that 我能验证当期+递延所得税费用的审定发生额。

#### Acceptance Criteria

1. THE Adjudication_N5_1 SHALL 分行显示：当期所得税费用/递延所得税费用/所得税费用合计
2. THE Adjudication_N5_1 SHALL 显示列：项目 | 本期发生额 | 未审数 | AJE | RJE | 审定数 | 上期数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**损益类取数规则**：取本期发生额（从tb_ledger，而非期末余额）
5. THE Income_Tax_Engine SHALL 计算：所得税费用=当期所得税费用+递延所得税费用
6. THE Adjudication_N5_1 SHALL 当期所得税取自N5-4计算表，递延所得税费用取自N5-8核对表
7. WHEN 审定数变化时 SHALL 回写trial_balance（科目6801，本期发生额）+发布'substantive:adjudicated'
8. THE Adjudication_N5_1 SHALL 在底部显示审计说明+结论+复核入口

### Requirement 3: 当期所得税费用计算表N5-4（82行，应纳税所得额×税率）

**User Story:** As a 审计助理, I want to 计算当期所得税, so that 应纳税所得额和当期所得税有据可循。

#### Acceptance Criteria

1. THE Current_Tax_Calc_N5_4 SHALL 显示计算链：会计利润总额 → 加：纳税调增 → 减：纳税调减 → 应纳税所得额 → ×适用税率 → 减：减免税额/抵免 → 当期应纳所得税
2. THE Income_Tax_Engine SHALL 计算：应纳税所得额=会计利润总额+纳税调增合计-纳税调减合计
3. THE Income_Tax_Engine SHALL 计算：当期所得税=应纳税所得额×适用税率-减免税额-抵免税额
4. THE Current_Tax_Calc_N5_4 SHALL 会计利润总额取自A类利润表（联动）
5. THE Current_Tax_Calc_N5_4 SHALL 纳税调增/调减合计取自N5-5纳税调整明细
6. THE Current_Tax_Calc_N5_4 SHALL 减免税额取自N5-6税收优惠、加计扣除取自N5-6-1
7. THE Current_Tax_Calc_N5_4 SHALL 结果回填N5-1审定表当期所得税费用行

### Requirement 4: 纳税调整明细表N5-5（107行大表，调增/调减，虚拟滚动）

**User Story:** As a 审计助理, I want to 管理纳税调整明细, so that 每项税会差异的调增调减可逐项核对。

#### Acceptance Criteria

1. THE Tax_Adjustment_N5_5 SHALL 显示107行调整项：分类（收入类/扣除类/资产类/特殊事项/其他）× 调增金额/调减金额/依据
2. THE Tax_Adjustment_N5_5 SHALL 使用**虚拟滚动**渲染107行大表（性能优化）
3. THE Tax_Adjustment_Engine SHALL 计算：纳税调整净额=Σ调增-Σ调减
4. THE Tax_Adjustment_N5_5 SHALL 分类小计（各类调增合计/调减合计）
5. THE Tax_Adjustment_N5_5 SHALL 调整净额回填N5-4当期计算表
6. THE Tax_Adjustment_N5_5 SHALL 支持动态行新增（ElMessageBox.prompt输入调整项）+导入导出（分sheet导出）
7. THE Tax_Adjustment_N5_5 SHALL 研发费用加计扣除行联动N5-6-1

### Requirement 5: 加计扣除研发费用情况明细表N5-6-1（43×7，17公式，接收I6/I2）

**User Story:** As a 审计助理, I want to 测算研发费用加计扣除, so that 研发费用加计扣除额准确。

#### Acceptance Criteria

1. THE RD_SuperDeduction_N5_6_1 SHALL 显示：研发项目 | 人员人工 | 直接投入 | 折旧费用 | 无形资产摊销 | 其他费用 | 研发费用合计 | 加计比例 | 加计扣除额
2. THE Income_Tax_Engine SHALL 计算：加计扣除额=研发费用合计×加计比例（一般100%，制造业等特定行业）
3. THE RD_SuperDeduction_N5_6_1 SHALL 研发费用取自I6研发费用/I2开发支出（联动，费用化+资本化）
4. THE RD_SuperDeduction_N5_6_1 SHALL 区分费用化研发费用（当期加计）与资本化（按无形资产摊销加计）
5. THE RD_SuperDeduction_N5_6_1 SHALL 加计扣除额回填N5-5纳税调整调减项

### Requirement 6: 税收优惠明细表N5-6（54×6，10公式）+ 高新技术企业认定N5-6-2（18×13）

**User Story:** As a 审计助理, I want to 汇总税收优惠并检查高新认定, so that 税收优惠适用合规。

#### Acceptance Criteria

1. THE Tax_Benefit_N5_6 SHALL 汇总各项税收优惠（减免税/优惠税率/抵免）及减免税额
2. THE Income_Tax_Engine SHALL 计算：优惠税率减免=应纳税所得额×(法定税率-优惠税率)
3. THE Tax_Benefit_N5_6 SHALL 减免税额合计回填N5-4当期计算表
4. THE HighTech_Check_N5_6_2 SHALL 逐条检查高新技术企业认定条件（知识产权/科技人员占比/研发费用占比/高新收入占比等）
5. WHEN 高新认定条件不满足时 SHALL 红色警告（影响15%优惠税率适用）
6. THE HighTech_Check_N5_6_2 SHALL 认定结论联动N5-6税收优惠（优惠税率适用性）

### Requirement 7: 财产损失明细表N5-7（15×7，12公式）

**User Story:** As a 审计助理, I want to 管理财产损失税前扣除, so that 财产损失扣除额准确。

#### Acceptance Criteria

1. THE Property_Loss_N5_7 SHALL 显示：损失项目 | 账面损失 | 已核准扣除额 | 待核准 | 税前扣除额 | 纳税调整额 | 依据
2. THE Income_Tax_Engine SHALL 计算：税前扣除额=已核准扣除额；纳税调整额=账面损失-税前扣除额
3. THE Property_Loss_N5_7 SHALL 对未取得核准的损失作纳税调增
4. THE Property_Loss_N5_7 SHALL 纳税调整额回填N5-5纳税调整明细

### Requirement 8: 递延所得税费用核对表N5-8（44×10，12公式，接收N1/N3）

**User Story:** As a 审计助理, I want to 核对递延所得税费用, so that 递延所得税费用与N1/N3变动一致。

#### Acceptance Criteria

1. THE Deferred_Tax_Reconcile_N5_8 SHALL 显示：项目 | 递延税资产期初/期末/本期变动 | 递延税负债期初/期末/本期变动 | 递延所得税费用
2. THE Income_Tax_Engine SHALL 计算：递延所得税费用=递延税负债本期增加-递延税资产本期增加
3. THE Deferred_Tax_Reconcile_N5_8 SHALL subscribe 'deferred-tax:asset-updated'（N1）+ 'deferred-tax:liability-updated'（N3）接收本期变动
4. THE Deferred_Tax_Reconcile_N5_8 SHALL 与N1递延税资产本期变动、N3递延税负债本期变动交叉验证
5. THE Deferred_Tax_Reconcile_N5_8 SHALL 递延所得税费用回填N5-1审定表递延所得税费用行

### Requirement 9: 明细表N5-2（10列8公式）+ 调整分录N5-3

**User Story:** As a 审计助理, I want to 管理所得税费用明细和调整分录, so that 明细核对和审计调整有据可循。

#### Acceptance Criteria

1. THE Detail_N5_2 SHALL 显示所得税费用构成明细（当期/递延分项）+合计与N5-1交叉验证
2. THE Detail_N5_2 SHALL 支持动态行+导入导出
3. THE Adjustment_N5_3 SHALL 借贷平衡校验 + EventBus发布'adjustment:created' + 双向同步N5-1

### Requirement 10: 附注披露

**User Story:** As a 审计助理, I want to 生成所得税费用附注, so that 披露符合准则要求。

#### Acceptance Criteria

1. THE Disclosure_Listed/SOE SHALL 按上市(29×12)/国企(32×255)模板渲染所得税费用附注（当期+递延+所得税费用与会计利润调节表）
2. THE Disclosure SHALL subscribe 'substantive:adjudicated' 自动刷新 + publish 'disclosure:note-text-updated'
3. THE 附注 SHALL 展示所得税费用与会计利润的调节过程（有效税率分析）

### Requirement 11: 跨底稿联动（N1/N3递延核对+I6/I2研发+A利润表）

**User Story:** As a 审计助理, I want to N5与N1/N3/I6/I2/A正确联动, so that 所得税全链路可追溯。

#### Acceptance Criteria

1. THE N5 SHALL subscribe N1/N3递延税变动（N5-8核对）、A类利润表会计利润（N5-4）、I6/I2研发费用（N5-6-1）
2. THE N5 SHALL 提供GtIndexChip跳转：N5-8 ↔ N1-1/N3-1；N5-4 ↔ A利润表；N5-6-1 ↔ I6/I2
3. THE N5 SHALL publish 'income-tax:updated' 供A类利润表勾稽
4. THE N5 SHALL 展示有效税率=所得税费用/会计利润总额供合理性分析

### Requirement 12: 损益类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现损益类科目的取数和计算逻辑, so that N5不会错误地取期末余额（应取本期发生额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现损益类取数：取本期发生额（从tb_ledger），而非期末余额
2. THE TB取数 SHALL 从tb_ledger取本期发生额（损益类专用取数逻辑，与N4/H10/I6同款）
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为本期发生额
4. THE Formula_Engine SHALL 区分：本期发生额（损益类用）vs 期末余额（资产/负债用），N5用本期发生额

### Requirement 13: 所得税计算引擎与纳税调整引擎（核心）

**User Story:** As a 开发者, I want to 独立纯函数所得税引擎, so that 当期所得税/递延/纳税调整可PBT验证。

#### Acceptance Criteria

1. THE Income_Tax_Engine SHALL 计算应纳税所得额=会计利润总额+纳税调增-纳税调减（纯函数）
2. THE Income_Tax_Engine SHALL 计算当期所得税=应纳税所得额×适用税率（纯函数）
3. THE Income_Tax_Engine SHALL 计算所得税费用=当期所得税费用+递延所得税费用（纯函数）
4. THE Income_Tax_Engine SHALL 计算递延所得税费用=递延税负债本期增加-递延税资产本期增加（纯函数）
5. THE Tax_Adjustment_Engine SHALL 计算纳税调整净额=Σ调增-Σ调减（纯函数）
6. THE Income_Tax_Engine SHALL 计算研发费用加计扣除额=研发费用×加计比例（纯函数）
