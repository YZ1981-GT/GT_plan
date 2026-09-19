# Requirements Document: N3 递延所得税负债底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

本spec的需求来源于两个权威数据源的交叉验证：

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构（sheet名/列头/行数/公式/合并单元格/数据类型）。这是列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/N税费循环底稿模板库.md`）：获取业务语义（审计目标/程序清单/联动关系/认定对应/交叉引用）。这是业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **N1递延所得税资产对应联动** + **N5递延所得税费用核对联动** + TB回写
- **美观性**：分组配色(浅绿/浅蓝/浅紫) + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip显示数据来源 + 公式列虚线下划线
- **易操作**：引导步骤(蓝色渐变) + 方法论上下文(琥珀色左边线) + 编制提示折叠
- **导入导出**：el-dropdown三级 + useN3ImportExport composable
- **AI辅助**：多section按区域AI + 弹确认预览再填入
- **双模式**：el-segmented(结构化视图/矩阵视图/在线编辑) + OO健康检查降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0(双源输入)~Phase7(测试)排序

## Introduction

N3递延所得税负债底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `n3-deferred-tax-liabilities`，覆盖来自 `N3 递延所得税负债.xlsx` 的6个sheet。科目覆盖2901递延所得税负债（**贷方/负债类科目**）。

**N3核心特殊**：①**负债类科目**！期末=期初+贷方-借方 ②核心引擎：递延所得税负债=应纳税暂时性差异×适用税率 ③与N1递延所得税资产对应（同源暂时性差异，账面>计税基础的资产项/账面<计税基础的负债项产生应纳税暂时性差异→递延税负债）④不能抵销的部分与N1分列 ⑤递延所得税费用核对联动N5。审定表78公式、明细表14公式。关键公式总数约92+。N3是N循环最简底稿。

## Glossary

- **Tab_Index**: 底稿目录，sheet导航+进度统计
- **Procedure_Table_N3A**: 递延所得税负债审计程序表N3A，审计程序清单（复用a-program-console）
- **Adjudication_N3_1**: 审定表N3-1，24行14列78公式，负债类/贷方科目2901审定
- **Detail_N3_2**: 明细表N3-2，31行14列14公式，按应纳税暂时性差异项目明细
- **Adjustment_N3_3**: 调整分录汇总N3-3，AJE/RJE管理
- **Disclosure**: 附注披露信息，递延所得税负债附注结构
- **Deferred_Tax_Engine**: 递延所得税测算引擎（应纳税暂时性差异×税率，纯函数）
- **Formula_Engine**: 前端公式引擎composable（**负债类！期末余额**）
- **Cross_Sheet_Engine**: 跨sheet引擎 + N1/N5跨底稿联动
- **Trial_Balance_Writeback**: 审定数回写（科目2901，期末余额）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Review_Dialog**: 通用复核对话

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to N3递延所得税负债底稿按sheetName分发, so that 6个sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE N3 组件 SHALL 注册新componentType: `n3-deferred-tax-liabilities`，主入口为 GtN3DeferredTaxLiabilities.vue
2. THE GtN3DeferredTaxLiabilities.vue SHALL 接收 `sheetName` prop，用正则提取末尾编码(N3-1/N3-2等)，v-if分发到子组件
3. THE N3 组件 SHALL 使用 defineAsyncComponent 懒加载各子组件
4. THE N3 组件 SHALL 拆为：n3/core/（审定+明细+调整+附注）
5. THE N3 组件 SHALL composable分层：useN3FormData + useN3FormulaEngine(纯函数) + useN3DeferredTaxEngine(纯函数) + useN3CrossSheet + useN3DualMode + useN3ImportExport
6. THE N3 组件 SHALL 在htmlRendererRegistry中注册'n3-deferred-tax-liabilities'
7. THE N3 组件 SHALL 在wp_code_overrides.json中将N3/N3-1~N3-3/N3A映射为'n3-deferred-tax-liabilities'
8. THE N3 组件 SHALL 在VALID_COMPONENT_TYPES中注册'n3-deferred-tax-liabilities'
9. THE GtN3DeferredTaxLiabilities.vue SHALL 支持selfLoad（bundle内嵌htmlData为null时自加载）
10. THE N3 组件 SHALL 使用 checklist_responses 存储，item_id前缀"N3-{sheet}-{field}"
11. THE 未迁移的sheet SHALL 走OnlyOffice fallback（GtOnlyOfficeSheet全高）

### Requirement 2: 审定表N3-1（负债类！78公式，期末余额）

**User Story:** As a 审计助理, I want to 在精美审定表中查看递延所得税负债, so that 我能验证各应纳税暂时性差异项目对应的递延所得税负债审定数。

#### Acceptance Criteria

1. THE Adjudication_N3_1 SHALL 按应纳税暂时性差异项目分行（固定资产折旧差异/公允价值变动/一次性税前扣除/长期股权投资/其他）+ 期初/本期变动/期末
2. THE Adjudication_N3_1 SHALL 显示列：项目 | 期初余额 | 本期贷方 | 本期借方 | 未审数 | AJE | RJE | 审定数
3. THE Formula_Engine SHALL 计算：审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 使用**负债类取数规则**：期末=期初+本期贷方-本期借方（2901为贷方科目）
5. THE Adjudication_N3_1 SHALL 与N3-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance（科目2901，期末余额）+发布'substantive:adjudicated'
7. THE Adjudication_N3_1 SHALL 在底部显示审计说明+结论+复核入口
8. THE Adjudication_N3_1 SHALL 显示与N1递延所得税资产的对应关系提示（同源差异分列展示）

### Requirement 3: 明细表N3-2（14列14公式）

**User Story:** As a 审计助理, I want to 管理递延所得税负债明细, so that 每个应纳税暂时性差异项目的确认可逐项核对。

#### Acceptance Criteria

1. THE Detail_N3_2 SHALL 显示列：序号/应纳税暂时性差异项目/账面价值/计税基础/应纳税暂时性差异/适用税率/期初递延税负债/本期确认/本期转回/期末递延税负债/备注
2. THE Deferred_Tax_Engine SHALL 自动计算每行：应纳税暂时性差异=账面价值-计税基础（资产项账面>计税基础）；递延税负债=应纳税暂时性差异×适用税率
3. THE Detail_N3_2 SHALL 合计行与N3-1审定表交叉验证
4. THE Detail_N3_2 SHALL 支持动态行新增（ElMessageBox.prompt输入项目名称）+导入导出
5. THE Detail_N3_2 SHALL 对期末递延税负债为0的转回项标记灰色
6. THE Detail_N3_2 SHALL 在底部统计：差异项目数/应纳税差异合计/递延税负债合计/加权平均税率

### Requirement 4: 递延所得税负债测算（应纳税暂时性差异×税率）

**User Story:** As a 审计助理, I want to 测算应纳税暂时性差异对应的递延所得税负债, so that 递延税负债的确认金额有据可循。

#### Acceptance Criteria

1. THE Deferred_Tax_Engine SHALL 计算：账面价值>计税基础(资产)→应纳税暂时性差异→递延所得税负债
2. THE Deferred_Tax_Engine SHALL 递延所得税负债=应纳税暂时性差异×适用税率
3. THE Deferred_Tax_Engine SHALL 计算加权平均税率
4. THE N3 SHALL 对不确认递延税负债的特殊项（商誉初始确认/长期股权投资拟长期持有）提供说明标注

### Requirement 5: 调整分录N3-3 + 附注

**User Story:** As a 审计助理, I want to 录入调整分录并生成附注, so that 审计调整和披露有据可循。

#### Acceptance Criteria

1. THE Adjustment_N3_3 SHALL 借贷平衡校验 + EventBus发布'adjustment:created' + 双向同步N3-1
2. THE Disclosure SHALL 按上市/国企模板渲染递延所得税负债附注结构
3. THE Disclosure SHALL subscribe 'substantive:adjudicated' 自动刷新 + publish 'disclosure:note-text-updated'
4. THE 附注 SHALL 展示应纳税暂时性差异明细及递延税负债期初期末余额

### Requirement 6: 跨底稿联动（N1对应+N5递延税费用核对）+ 负债类科目特殊处理

**User Story:** As a 审计助理, I want to N3与N1/N5正确联动且正确实现负债类取数, so that 递延所得税全链路可追溯。

#### Acceptance Criteria

1. THE N3 SHALL 与N1递延所得税资产通过同源暂时性差异对应（N1-4测算表同时产出资产/负债两部分，N3接收负债部分）
2. THE N3 SHALL publish 'deferred-tax:liability-updated' 供N5递延所得税费用核对表N5-8接收
3. THE N3 SHALL 提供GtIndexChip跳转：N3-2 ↔ N1-4测算表
4. THE N3 SHALL 展示递延税负债本期变动额（期末-期初）供N5核对递延所得税费用
5. THE N3 SHALL 与N1不能相互抵销的部分分别列示（同一纳税主体可抵销，不同主体分列）
6. THE Formula_Engine SHALL 实现负债类期末公式：期末余额=期初余额+本期贷方-本期借方（2901贷方科目），TB从tb_balance取期末余额（direction=贷），审定数回写trial_balance.audited_amount为期末余额
