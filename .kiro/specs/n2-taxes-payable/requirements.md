# Requirements Document: N2 应交税费底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/N税费循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **N4税金及附加计提联动** + **各税种测算子表汇总联动审定表** + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 多税种统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级 + useN2ImportExport composable（多税种分sheet导出）
- **AI辅助**：多section按区域AI + 弹确认预览再填入
- **双模式**：el-segmented + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

N2应交税费底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `n2-taxes-payable`，覆盖来自 `N2 应交税费.xlsx` 的18个sheet（其中O1A原底稿、出口退税额复核示例为辅助sheet标记skip）。科目覆盖2221应交税费（**贷方/负债类科目**）。

**N2核心特殊**：①**负债类科目**！期末=期初+贷方-借方 ②**多税种测算**（增值税/房产税/土地增值税/其他税费）是N循环最复杂底稿 ③增值税=销项税额-进项税额 ④各税种=计税依据×税率 ⑤出口退税核对 ⑥各税种明细子目（2221下二级科目）⑦应交税费计提联动N4税金及附加。审定表85公式、明细表22公式、其他税费测算11公式。关键公式总数约180+。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_N2A**: 应交税费审计程序表N2A（复用a-program-console）
- **Adjudication_N2_1**: 审定表N2-1，31行14列85公式，负债类/贷方科目2221审定（多税种分行）
- **Disclosure_Listed**: 附注披露信息（上市公司），27行11列
- **Disclosure_SOE**: 附注披露信息（国有企业），24行11列
- **Detail_N2_2**: 明细表N2-2，42行23列22公式，各税种明细子目
- **Adjustment_N2_3**: 调整分录汇总N2-3，AJE/RJE管理
- **Policy_Check_N2_4**: 税收政策检查N2-4，税收政策合规检查
- **Recognition_N2_5**: 应交税金认定表N2-5，54行15列，各税种应交额认定
- **VAT_Calc_N2_6**: 增值税测算表N2-6，48行8列，销项-进项测算
- **Export_Refund_N2_7**: 出口退税核对表N2-7，出口退税额核对
- **Other_Tax_Calc_N2_8**: 应交其他税费测算表N2-8，26行9列11公式
- **Property_Tax_N2_9**: 房产税测算表N2-9，30行7列，从价/从租
- **LVT_N2_10**: 土地增值税测算表N2-10，51行7列，增值额×累进税率
- **Tax_Check_N2_11**: 应交税费检查表N2-11，逐项核查
- **Multi_Tax_Engine**: 多税种测算引擎（各税种计税依据×税率，纯函数）
- **VAT_Engine**: 增值税测算引擎（销项-进项，纯函数）
- **Formula_Engine**: 前端公式引擎composable（**负债类！期末余额**）
- **Trial_Balance_Writeback**: 审定数回写（科目2221，期末余额）
- **Skip_Sheet**: 辅助sheet标记skip（O1A原底稿/出口退税额复核示例）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to N2应交税费底稿按sheetName分发, so that 18个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE N2 组件 SHALL 注册新componentType: `n2-taxes-payable`，主入口为 GtN2TaxesPayable.vue
2. THE GtN2TaxesPayable.vue SHALL 接收 `sheetName` prop，正则提取末尾编码，v-if分发
3. THE N2 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE N2 组件 SHALL 拆为：n2/core/（审定+明细+调整+附注）、n2/inspection/（政策检查+认定+税费检查）、n2/calc/（增值税/房产税/土增税/其他税费测算+出口退税）
5. THE N2 组件 SHALL composable分层：useN2FormData + useN2FormulaEngine(纯函数) + useN2MultiTaxEngine(纯函数) + useN2VatEngine(纯函数) + useN2CrossSheet + useN2DualMode + useN2ImportExport
6. THE N2 组件 SHALL 在htmlRendererRegistry中注册'n2-taxes-payable'
7. THE N2 组件 SHALL 在wp_code_overrides.json中将N2/N2-1~N2-11/N2A映射为'n2-taxes-payable'
8. THE N2 组件 SHALL 在VALID_COMPONENT_TYPES中注册'n2-taxes-payable'
9. THE GtN2TaxesPayable.vue SHALL 支持selfLoad
10. THE N2 组件 SHALL 使用 checklist_responses 存储，item_id前缀"N2-{sheet}-{field}"
11. THE O1A原底稿/出口退税额复核示例 SHALL 标记skip（走OnlyOffice fallback，不做HTML组件化）

### Requirement 2: 审定表N2-1（负债类！85公式，多税种分行）

**User Story:** As a 审计助理, I want to 在精美审定表中查看应交税费, so that 我能验证各税种应交额的审定数。

#### Acceptance Criteria

1. THE Adjudication_N2_1 SHALL 按税种分行（增值税/未交增值税/消费税/城建税/教育费附加/地方教育附加/房产税/土地使用税/印花税/所得税/其他）+ 期初/本期计提/本期缴纳/期末
2. THE Adjudication_N2_1 SHALL 显示列：税种 | 期初余额 | 本期贷方(计提) | 本期借方(缴纳) | 未审数 | AJE | RJE | 审定数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**负债类取数规则**：期末=期初+本期贷方-本期借方（2221为贷方科目）
5. THE Adjudication_N2_1 SHALL 与N2-2明细合计交叉验证
6. THE Adjudication_N2_1 SHALL 与各税种测算表（N2-6/N2-8/N2-9/N2-10）结果交叉验证
7. WHEN 审定数变化时 SHALL 回写trial_balance（科目2221，期末余额）+发布'substantive:adjudicated'
8. THE Adjudication_N2_1 SHALL 在底部显示审计说明+结论+复核入口

### Requirement 3: 明细表N2-2（23列22公式，各税种子目）

**User Story:** As a 审计助理, I want to 管理应交税费明细, so that 各税种明细子目可逐项核对。

#### Acceptance Criteria

1. THE Detail_N2_2 SHALL 将23列拆为区段Tab：基础(税种/明细子目/计税依据/税率) | 计提缴纳(期初/本期计提/本期缴纳/期末) | 核对(申报表金额/差异/核查结论)
2. THE Detail_N2_2 SHALL 自动计算每行：期末=期初+本期计提-本期缴纳（负债类）；差异=账面-申报表
3. THE Detail_N2_2 SHALL 合计行与N2-1审定表交叉验证
4. THE Detail_N2_2 SHALL 支持动态行新增（ElMessageBox.prompt输入税种/子目）+导入导出
5. THE Detail_N2_2 SHALL 对账面与申报表存在差异的行标记红色背景
6. THE Detail_N2_2 SHALL 在底部统计：税种数/计提合计/缴纳合计/期末合计

### Requirement 4: 增值税测算表N2-6（48×8，销项-进项）

**User Story:** As a 审计助理, I want to 测算应交增值税, so that 增值税销项/进项/应交额有据可循。

#### Acceptance Criteria

1. THE VAT_Calc_N2_6 SHALL 显示：项目 | 销售额 | 销项税额 | 进项税额 | 进项转出 | 应交增值税 | 已交 | 未交
2. THE VAT_Engine SHALL 计算：销项税额=销售额×适用税率；应交增值税=销项税额-(进项税额-进项转出)
3. THE VAT_Calc_N2_6 SHALL 按月/季度分行汇总年度增值税
4. THE VAT_Calc_N2_6 SHALL 与增值税申报表核对（税负率分析）
5. THE VAT_Calc_N2_6 SHALL 结果回填N2-1审定表增值税行
6. THE VAT_Calc_N2_6 SHALL 计算增值税税负率=应交增值税/销售额

### Requirement 5: 应交其他税费测算表N2-8（26×9，11公式）

**User Story:** As a 审计助理, I want to 测算城建税及附加等其他税费, so that 附加税费计算正确。

#### Acceptance Criteria

1. THE Other_Tax_Calc_N2_8 SHALL 显示：税种(城建税/教育费附加/地方教育附加) | 计税依据(增值税+消费税) | 税率 | 应交额
2. THE Multi_Tax_Engine SHALL 计算：城建税=(增值税+消费税)×7%/5%/1%；教育费附加=×3%；地方教育附加=×2%
3. THE Other_Tax_Calc_N2_8 SHALL 计税依据取自N2-6增值税测算结果（联动）
4. THE Other_Tax_Calc_N2_8 SHALL 结果回填N2-1及联动N4税金及附加
5. THE Other_Tax_Calc_N2_8 SHALL 支持城建税税率按地区选择(市区7%/县城5%/其他1%)

### Requirement 6: 房产税测算表N2-9（30×7，从价/从租）

**User Story:** As a 审计助理, I want to 测算应交房产税, so that 房产税从价/从租计算正确。

#### Acceptance Criteria

1. THE Property_Tax_N2_9 SHALL 显示：房产 | 计税方式(从价/从租) | 计税依据 | 税率 | 应交房产税
2. THE Multi_Tax_Engine SHALL 计算：从价=房产原值×(1-扣除比例)×1.2%；从租=租金收入×12%
3. THE Property_Tax_N2_9 SHALL 结果回填N2-1及联动N4
4. THE Property_Tax_N2_9 SHALL 支持扣除比例按地区(10%~30%)配置

### Requirement 7: 土地增值税测算表N2-10（51×7，累进税率）

**User Story:** As a 审计助理, I want to 测算应交土地增值税, so that 增值额四级累进税率计算正确。

#### Acceptance Criteria

1. THE LVT_N2_10 SHALL 显示：项目 | 转让收入 | 扣除项目金额 | 增值额 | 增值率 | 适用税率 | 速算扣除 | 应交土增税
2. THE Multi_Tax_Engine SHALL 计算：增值额=转让收入-扣除项目；增值率=增值额/扣除项目；四级累进(30%/40%/50%/60%)
3. THE LVT_N2_10 SHALL 按增值率区间自动匹配税率和速算扣除系数
4. THE LVT_N2_10 SHALL 应交土增税=增值额×税率-扣除项目×速算扣除系数
5. THE LVT_N2_10 SHALL 结果回填N2-1

### Requirement 8: 出口退税核对表N2-7

**User Story:** As a 审计助理, I want to 核对出口退税, so that 出口退税额确认正确。

#### Acceptance Criteria

1. THE Export_Refund_N2_7 SHALL 显示：出口销售额 | 退税率 | 免抵退税额 | 应退税额 | 免抵税额 | 已退税额 | 差异
2. THE Export_Refund_N2_7 SHALL 计算免抵退税额并与主管税务机关批复核对
3. THE Export_Refund_N2_7 SHALL 对差异标记提示
4. THE Export_Refund_N2_7 SHALL 结果联动N2-6增值税测算

### Requirement 9: 应交税金认定表N2-5（54×15）+ 税收政策检查N2-4

**User Story:** As a 审计助理, I want to 认定各税种应交额并检查税收政策, so that 税费认定完整合规。

#### Acceptance Criteria

1. THE Recognition_N2_5 SHALL 汇总各税种应交额认定（按税种×期间矩阵）
2. THE Recognition_N2_5 SHALL 与各测算表结果交叉验证
3. THE Policy_Check_N2_4 SHALL 检查税收优惠/税率适用/纳税义务发生时点合规性
4. THE Policy_Check_N2_4 SHALL 对每项提供"合规/不合规/不适用"判断
5. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 10: 应交税费检查表N2-11 + 调整分录N2-3

**User Story:** As a 审计助理, I want to 完成应交税费检查并录入调整分录, so that 审计验证和调整有据可循。

#### Acceptance Criteria

1. THE Tax_Check_N2_11 SHALL 逐税种核查（计提准确性/缴纳及时性/申报一致性）
2. THE Tax_Check_N2_11 SHALL 支持行级抽凭
3. THE Adjustment_N2_3 SHALL 借贷平衡校验 + EventBus发布'adjustment:created' + 双向同步N2-1

### Requirement 11: 跨底稿联动（N4税金及附加）

**User Story:** As a 审计助理, I want to N2应交税费计提与N4税金及附加正确联动, so that 计提与费用确认一致。

#### Acceptance Criteria

1. THE N2 SHALL publish 'tax-accrual:updated'（各税种计提额）供N4税金及附加接收
2. THE N2 SHALL 提供GtIndexChip跳转：N2-1税种行 ↔ N4-1税金及附加对应项
3. THE N2 SHALL 与N4对城建税/教育费附加/房产税/土地使用税/印花税等计提额交叉验证
4. THE N2 SHALL 展示计提与缴纳的时间性差异供N4核对

### Requirement 12: 负债类科目特殊处理

**User Story:** As a 开发者, I want to 正确实现负债类科目的取数和计算逻辑, so that N2不会错误地取借方期末（应为贷方期末）。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 实现负债类期末公式：期末余额=期初余额+本期贷方-本期借方（2221贷方科目）
2. THE TB取数 SHALL 从tb_balance取期末余额（direction=贷）
3. THE 审定数回写 SHALL 回写trial_balance.audited_amount为期末余额
4. THE Formula_Engine SHALL 区分：负债类期末（贷方增） vs 资产类期末（借方增）

### Requirement 13: 附注披露

**User Story:** As a 审计助理, I want to 生成应交税费附注, so that 披露符合准则要求。

#### Acceptance Criteria

1. THE Disclosure_Listed/SOE SHALL 按上市/国企模板渲染应交税费附注结构（各税种明细）
2. THE Disclosure SHALL subscribe 'substantive:adjudicated' 自动刷新 + publish 'disclosure:note-text-updated'
3. THE 附注 SHALL 展示各税种期初/期末余额明细
