# Requirements Document: N1 递延所得税资产底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/N税费循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **N3递延所得税负债联动** + **N5递延所得税费用核对联动** + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级 + useN1ImportExport composable
- **AI辅助**：多section按区域AI + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

N1递延所得税资产底稿的专属HTML精美组件构建。将现有 `d-form-table`/`audit-sheet` 通用渲染升级为独立专属组件 `n1-deferred-tax-assets`，覆盖来自 `N1 递延所得税资产.xlsx` 的9个有效sheet。科目覆盖1811递延所得税资产（**借方/资产类科目**）。

**N1核心特殊**：①**资产类科目**！期末=期初+借方-贷方 ②核心引擎：递延所得税资产=可抵扣暂时性差异×适用税率 ③可弥补亏损确认（判断未来应纳税所得额充足性）④与N3递延所得税负债对应（同一暂时性差异来源，不能抵销的分列）⑤递延所得税费用核对联动N5。审定表78公式、测算表21公式、明细表14公式。关键公式总数约120+。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_N1A**: 递延所得税资产审计程序表N1A，审计程序清单（复用a-program-console）
- **Adjudication_N1_1**: 审定表N1-1，35行15列78公式，资产类/借方科目1811审定
- **Disclosure_Listed**: 附注披露信息（上市公司），54行11列
- **Disclosure_SOE**: 附注披露信息（国有企业），74行256列
- **Detail_N1_2**: 明细表N1-2，52行14列14公式，按暂时性差异项目明细
- **Adjustment_N1_3**: 调整分录汇总N1-3，AJE/RJE管理
- **Calc_Table_N1_4**: 递延所得税资产(负债)测算表N1-4，63行15列21公式，暂时性差异×税率测算
- **Loss_Check_N1_5**: 可用以后年度税前利润弥补的亏损检查表N1-5，30行13列，弥补亏损充足性判断
- **Deferred_Tax_Engine**: 递延所得税测算引擎（差异×税率，纯函数）
- **Loss_Compensation_Engine**: 可弥补亏损确认引擎（充足性判断，纯函数）
- **Formula_Engine**: 前端公式引擎composable（**资产类！期末余额**）
- **Cross_Sheet_Engine**: 跨sheet引擎 + N3/N5跨底稿联动
- **Dynamic_Row**: 动态行
- **Dual_Mode**: 双模式切换
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话
- **Trial_Balance_Writeback**: 审定数回写（科目1811，期末余额）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to N1递延所得税资产底稿按sheetName分发, so that 9个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE N1 组件 SHALL 注册新componentType: `n1-deferred-tax-assets`，主入口为 GtN1DeferredTaxAssets.vue
2. THE GtN1DeferredTaxAssets.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(N1-1/N1-2等)，v-if分发到子组件
3. THE N1 组件 SHALL 使用 defineAsyncComponent 懒加载各子组件
4. THE N1 组件 SHALL 拆为：n1/core/（审定+明细+调整+附注）、n1/calc/（测算表+亏损检查）
5. THE N1 组件 SHALL composable分层：useN1FormData + useN1FormulaEngine(纯函数) + useN1DeferredTaxEngine(纯函数) + useN1LossCompensationEngine(纯函数) + useN1CrossSheet + useN1DualMode + useN1ImportExport
6. THE N1 组件 SHALL 在htmlRendererRegistry中注册'n1-deferred-tax-assets'
7. THE N1 组件 SHALL 在wp_code_overrides.json中将N1/N1-1~N1-5/N1A映射为'n1-deferred-tax-assets'
8. THE N1 组件 SHALL 在VALID_COMPONENT_TYPES中注册'n1-deferred-tax-assets'
9. THE GtN1DeferredTaxAssets.vue SHALL 支持selfLoad（bundle内嵌htmlData为null时自加载）
10. THE N1 组件 SHALL 使用 checklist_responses 存储，item_id前缀"N1-{sheet}-{field}"
11. THE 未迁移的sheet SHALL 走OnlyOffice fallback（GtOnlyOfficeSheet全高）

### Requirement 2: 审定表N1-1（资产类！78公式，期末余额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看递延所得税资产, so that 我能验证各暂时性差异项目对应的递延所得税资产审定数。

#### Acceptance Criteria

1. THE Adjudication_N1_1 SHALL 渲染为：按暂时性差异项目分行（资产减值准备/可弥补亏损/预提费用/递延收益/公允价值变动/其他）+ 期初/本期变动/期末
2. THE Adjudication_N1_1 SHALL 显示列：项目 | 期初余额 | 本期借方 | 本期贷方 | 未审数 | AJE | RJE | 审定数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**资产类取数规则**：期末=期初+本期借方-本期贷方（1811为借方科目）
5. THE Adjudication_N1_1 SHALL 与N1-2明细合计交叉验证
6. THE Adjudication_N1_1 SHALL 与N1-4测算表结果交叉验证（审定确认额=测算额）
7. WHEN 审定数变化时 SHALL 回写trial_balance（科目1811，期末余额）+发布'substantive:adjudicated'
8. THE Adjudication_N1_1 SHALL 在底部显示审计说明+结论+复核入口
9. THE Adjudication_N1_1 SHALL 显示与N3递延所得税负债的对应关系提示（同源差异分列展示）

### Requirement 3: 明细表N1-2（14列14公式）

**User Story:** As a 审计助理, I want to 管理递延所得税资产明细, so that 每个暂时性差异项目的确认可逐项核对。

#### Acceptance Criteria

1. THE Detail_N1_2 SHALL 显示列：序号/暂时性差异项目/账面价值/计税基础/可抵扣暂时性差异/适用税率/期初递延税资产/本期确认/本期转回/期末递延税资产/备注
2. THE Deferred_Tax_Engine SHALL 自动计算每行：可抵扣暂时性差异=账面价值-计税基础（资产项）；递延税资产=可抵扣暂时性差异×适用税率
3. THE Detail_N1_2 SHALL 合计行与N1-1审定表交叉验证
4. THE Detail_N1_2 SHALL 支持动态行新增（ElMessageBox.prompt输入项目名称）+导入导出
5. THE Detail_N1_2 SHALL 对期末递延税资产为0的转回项标记灰色
6. THE Detail_N1_2 SHALL 在底部统计：差异项目数/可抵扣差异合计/递延税资产合计/加权平均税率

### Requirement 4: 递延所得税资产(负债)测算表N1-4（63×15，21公式，核心引擎）

**User Story:** As a 审计助理, I want to 测算暂时性差异对应的递延所得税, so that 递延税资产/负债的确认金额有据可循。

#### Acceptance Criteria

1. THE Calc_Table_N1_4 SHALL 显示：项目 | 账面价值 | 计税基础 | 应纳税暂时性差异 | 可抵扣暂时性差异 | 适用税率 | 递延所得税负债 | 递延所得税资产
2. THE Deferred_Tax_Engine SHALL 计算：账面>计税基础(资产)→应纳税暂时性差异→递延税负债；账面<计税基础(资产)→可抵扣暂时性差异→递延税资产
3. THE Deferred_Tax_Engine SHALL 递延所得税=暂时性差异×适用税率
4. THE Calc_Table_N1_4 SHALL 将递延税资产部分回填N1-1/N1-2，递延税负债部分联动N3
5. THE Calc_Table_N1_4 SHALL 显示是否满足确认条件（未来应纳税所得额充足性）
6. THE Calc_Table_N1_4 SHALL 合计行与N1-1审定+N3审定交叉验证

### Requirement 5: 可用以后年度税前利润弥补的亏损检查表N1-5（30×13）

**User Story:** As a 审计助理, I want to 检查可弥补亏损的确认充足性, so that 递延所得税资产的确认符合谨慎性原则。

#### Acceptance Criteria

1. THE Loss_Check_N1_5 SHALL 显示列：亏损年度/亏损金额/弥补截止年度/已弥补金额/未弥补金额/预计未来应纳税所得额/可确认递延税资产/确认依据
2. THE Loss_Compensation_Engine SHALL 计算：未弥补金额=亏损金额-已弥补金额；可确认递延税资产=min(未弥补金额, 预计未来应纳税所得额)×适用税率
3. THE Loss_Check_N1_5 SHALL 判断弥补期限（一般5年，高新/科技型中小企业10年）是否届满，届满标红
4. THE Loss_Check_N1_5 SHALL 对预计未来应纳税所得额不足的部分不确认递延税资产（黄色警告）
5. THE Loss_Check_N1_5 SHALL 合计可确认额回填N1-4/N1-1的可弥补亏损项
6. THE Loss_Check_N1_5 SHALL 在底部说明确认判断依据+复核入口

### Requirement 6: 调整分录N1-3 + 附注

**User Story:** As a 审计助理, I want to 录入调整分录并生成附注, so that 审计调整和披露有据可循。

#### Acceptance Criteria

1. THE Adjustment_N1_3 SHALL 借贷平衡校验 + EventBus发布'adjustment:created' + 双向同步N1-1
2. THE Disclosure_Listed/SOE SHALL 按上市/国企模板渲染递延所得税资产附注结构
3. THE Disclosure SHALL subscribe 'substantive:adjudicated' 自动刷新 + publish 'disclosure:note-text-updated'
4. THE 附注 SHALL 展示未确认递延所得税资产的可抵扣暂时性差异及可弥补亏损金额

### Requirement 7: 跨底稿联动（N3递延税负债+N5递延税费用核对）

**User Story:** As a 审计助理, I want to N1与N3/N5正确联动, so that 递延所得税全链路可追溯。

#### Acceptance Criteria

1. THE N1 SHALL 与N3递延所得税负债通过同源暂时性差异对应（N1-4测算表同时产出资产/负债两部分）
2. THE N1 SHALL publish 'deferred-tax:asset-updated' 供N5递延所得税费用核对表N5-8接收
3. THE N1 SHALL 提供GtIndexChip跳转：N1-4 ↔ N3-2明细
4. THE N1 SHALL 展示递延税资产本期变动额（期末-期初）供N5核对递延所得税费用
5. THE N1 SHALL 与N3不能相互抵销的部分分别列示（同一纳税主体可抵销，不同主体分列）

### Requirement 8: 资产类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现资产类科目的取数和计算逻辑, so that N1不会错误地取发生额（应取期末余额）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现资产类期末公式：期末余额=期初余额+本期借方-本期贷方（1811借方科目）
2. THE TB取数 SHALL 从tb_balance取期末余额（direction=借），使用资产类专用取数逻辑
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为期末余额
4. THE Formula_Engine SHALL 区分：期末余额（资产/负债用）vs 发生额（损益用），N1用期末余额
