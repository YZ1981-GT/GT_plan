# Requirements Document

## Introduction

G0投资循环函证，覆盖科目：交易性金融资产/债权投资/长期股权投资/其他权益工具投资等投资科目。源模板1个xlsx文件(878KB)/9个有效sheet。

**核心架构决策（对齐D0实际实现 + F0 pattern）**：
- 函证模块是**跨循环共享**的9个componentType，D0/E0/F0/G0/H0/K0/L0全部复用
- G0-1~G0-3/G0-4(非证券)/G0-7/G0-8直接映射到D0已有的共享组件（confirmation-summary / confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile / confirmation-reliability / confirmation-fraud-risk）
- **G0与F0的差异**：G0有证券投资/非证券投资两种差异核对模式 + 投资循环特有替代程序G0-6(29列宽表)
- **仅G0-3(证券)/G0-6需要新建**：
  - G0-3(证券) 函证差异核对表-证券投资：证券特有的公允价值/持仓数量差异核对
  - G0-6 替代程序检查表：投资循环替代程序(51R×29C)，29列宽表需拆分
- G0A程序表复用`a-program-console`

**源模板sheet清单（openpyxl实读确认）**：

| # | Sheet名 | 行×列 | wp_code | componentType | 新建/复用 |
|---|---------|-------|---------|---------------|-----------|
| 1 | G0A 函证程序表 | 21R×10C | G0A | a-program-console | 复用 |
| 2 | G0-1 函证结果汇总表 | 58R×33C | G0-1 | confirmation-summary | 复用D0 |
| 3 | G0-2 核实被函证单位信息 | 35R×43C | G0-2 | confirmation-entity-verify | 复用D0 |
| 4 | G0-3 跟函函证过程控制 | 37R×18C | G0-3 | confirmation-followup | 复用D0 |
| 5 | G0-3(证券) 函证差异核对表-证券投资 | 24R×17C | G0-3S | confirmation-diff-securities | **新建** |
| 6 | G0-4(非证券) 函证差异核对表-非证券投资 | 24R×15C | G0-4 | confirmation-diff-reconcile | 复用D0 |
| 7 | G0-6 替代程序检查表 | 51R×29C | G0-6 | confirmation-alternative-g06 | **新建** |
| 8 | G0-7 邮件传真回函可靠性验证 | 40R×20C | G0-7 | confirmation-reliability | 复用D0 |
| 9 | G0-8 函证程序舞弊风险评价表 | 31R×10C | G0-8 | confirmation-fraud-risk | 复用D0 |

## Glossary

- **confirmation-hub**: 函证模块统一入口（ConfirmationHub.vue + ConfirmationTabs.vue），由confirmation-hub componentType触发，按wp_code路由分发到各共享子组件
- **共享函证组件**: D0开发的9个跨循环复用componentType
- **证券投资差异核对**: G0-3(证券)特有，按持仓数量/公允价值/成本多维度对比（有别于D0通用差异核对）
- **非证券投资差异核对**: G0-4(非证券)对齐D0-4通用差异核对模式（余额+明细核对）
- **投资循环替代程序**: G0-6特有，4区块（持仓证明检查/股利收入证据/投资收益证据/公允价值佐证），29列宽表
- **公允价值差异**: 证券投资按市场报价vs账面值对比（Level1直接引用市场价）

## Requirements

### Requirement 1: G0 overrides映射对齐D0（配置层）

**User Story:** As a 开发者, I want to G0各sheet映射到D0共享组件+2个新建组件, so that G0投资循环函证获得完整专属渲染。

#### Acceptance Criteria

1.1 THE wp_code_overrides.json SHALL 包含完整映射：G0→confirmation-hub, G0A→a-program-console, G0-1→confirmation-summary, G0-2→confirmation-entity-verify, G0-3→confirmation-followup, G0-3S→confirmation-diff-securities, G0-4→confirmation-diff-reconcile, G0-6→confirmation-alternative-g06, G0-7→confirmation-reliability, G0-8→confirmation-fraud-risk（10个wp_code条目）
1.2 THE G0.yaml render schema SHALL 准确反映9个有效sheet的component_type和class_code
1.3 THE account_package_registry.json SHALL 包含G0包（9 sheets按模板顺序）

### Requirement 2: G0-3(证券) 函证差异核对表-证券投资（新建）

**User Story:** As a 审计助理, I want to 对证券投资函证差异按持仓/公允价值/成本多维度核对, so that 我能识别证券投资函证回函与账面的具体差异。

#### Acceptance Criteria

2.1 THE G0-3(证券) SHALL 注册componentType: `confirmation-diff-securities`
2.2 THE G0-3(证券) SHALL 多公司Master-Detail（一证券一核对表，参照D0-4差异核对模式）
2.3 THE G0-3(证券) SHALL 顶部差异汇总区：证券名称|证券代码|回函确认持仓数量|账面持仓数量|数量差异|回函确认公允价值|账面公允价值|公允价值差异|差异原因分类
2.4 THE G0-3(证券) SHALL 明细核对区(17列)：序号|证券名称|证券代码|证券类型(股票/基金/债券)|回函持仓数量|账面持仓数量|数量差异(公式)|回函单位公允价值|账面单位公允价值|公允价值差异(公式)|回函总市值|账面总市值|市值差异(公式)|差异原因|调节事项|核实结论|备注
2.5 THE Formula_Engine SHALL 计算数量差异 = 回函持仓 - 账面持仓
2.6 THE Formula_Engine SHALL 计算公允价值差异 = 回函单位公允价值 - 账面单位公允价值
2.7 THE Formula_Engine SHALL 计算市值差异 = 回函总市值 - 账面总市值
2.8 WHEN |数量差异|>0 OR |公允价值差异|>0, THE 系统 SHALL 以橙色高亮该行
2.9 THE G0-3(证券) SHALL 差异原因下拉：估值时点差异/交易日与结算日差异/计量方法差异/其他
2.10 THE G0-3(证券) SHALL 底部汇总（核对笔数/有差异笔数/无差异笔数/最大单笔差异）+ 审计结论textarea(AI辅助)
2.11 THE G0-3(证券) SHALL 支持动态行增删 + 导入导出
2.12 THE G0-3(证券) SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry

### Requirement 3: G0-6 替代程序检查表（新建，29列宽表）

**User Story:** As a 审计助理, I want to 对未回函的投资项目执行替代程序, so that 我能获取充分适当的投资存在性和计价证据。

#### Acceptance Criteria

3.1 THE G0-6 SHALL 注册componentType: `confirmation-alternative-g06`
3.2 THE G0-6 SHALL 多公司Master-Detail（一投资项目一检查表，参照D0-5模式）
3.3 THE G0-6 SHALL 顶部余额汇总区：投资类型(交易性金融资产/债权投资/长期股权投资/其他权益工具) | 年初余额 | 本期增加 | 本期减少 | 期末余额 | 投资收益 | 公允价值变动
3.4 THE G0-6 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程6字段textarea）
3.5 THE G0-6 4区块 SHALL 为（29列宽表→4区块各自拆分，每区块独立el-table动态行）：
   - ①持仓证明检查（15列）：日期/凭证编号/业务内容/对方科目/金额 | 证券公司对账单日期/持仓品种/数量/市值 | 托管机构确认函/确认日期 | 中登公司查询日/持仓一致性/索引号
   - ②投资收益/股利收入证据（14列）：日期/凭证编号/业务内容/对方科目/金额 | 分红公告日期/每股股利/应收股利金额 | 银行回单日期/到账金额 | 红利税扣缴/实收金额/差异/索引号
   - ③投资处置收益证据（15列）：日期/凭证编号/业务内容/对方科目/金额 | 交易确认单日期/卖出数量/成交价/成交金额 | 原始成本/处置损益(公式) | 手续费/净收入/银行到账/索引号
   - ④公允价值佐证（14列）：日期/凭证编号/业务内容/对方科目/金额 | 报价来源(交易所/Wind/Bloomberg)/报价日期/报价值 | 估值模型(如有)/估值假设/Level层级(1/2/3) | 账面vs报价差异/合理性判断/索引号
3.6 THE G0-6 每区块 SHALL 宽表拆为左右两个视觉分组（记账凭证5列 | 检查证据N列），减少横向滚动
3.7 THE G0-6 SHALL 每区块底部显示合计行（SUM金额列）+ 索引号列
3.8 THE G0-6 SHALL 支持从confirmation-hub的G0-1带入未回函项目（反向联动）
3.9 THE G0-6 SHALL 支持增删行+动态宽表编辑+行级OCR上传（复用`/d4/contract-ocr`端点）
3.10 THE G0-6 SHALL 底部审计说明textarea + 审计结论textarea（均支持AI辅助生成）
3.11 THE G0-6 SHALL 注册到VALID_COMPONENT_TYPES + htmlRendererRegistry
3.12 THE G0-6 SHALL 支持导入导出（el-dropdown"导入导出▾"：导出模板/导出数据/导入数据）
3.13 THE G0-6 处置损益公式 SHALL = 成交金额 - 原始成本 - 手续费

### Requirement 4: 注册契约完整性

**User Story:** As a 开发者, I want to 新增的2个componentType完整注册, so that 前后端都能正确渲染。

#### Acceptance Criteria

4.1 THE `confirmation-diff-securities` SHALL 在VALID_COMPONENT_TYPES中注册
4.2 THE `confirmation-alternative-g06` SHALL 在VALID_COMPONENT_TYPES中注册
4.3 THE htmlRendererRegistry SHALL 包含g0-diff-securities/g0-alternative→对应Vue组件的映射
4.4 THE htmlRendererRegistry.spec.ts SHALL 更新expected componentType列表包含新增2个
4.5 THE 后端RENDERER_DISPATCH SHALL 有g0-diff-securities/g0-alternative的render策略

### Requirement 5: 独立composable与导入导出

**User Story:** As a 开发者, I want to G0-3(证券)/G0-6各有独立composable管理数据和导入导出, so that 代码组织清晰、复用导入导出模式。

#### Acceptance Criteria

5.1 THE G0-3(证券) SHALL 有独立composable `useDiffSecuritiesData.ts`（Master-Detail CRUD+持久化+差异计算+合计）
5.2 THE G0-6 SHALL 有独立composable `useAlternativeG06Data.ts`（4区块CRUD+持久化+loadAll+persistAll+合计计算）
5.3 THE G0-3(证券)/G0-6 SHALL 复用 `useXImportExport` 模式（composable封装三端点调用）
5.4 THE 后端导入导出端点 SHALL 路径为 `/api/workpapers/{wp_id}/g0/export-template?sheet=G0-3S` 等
5.5 THE G0-6导出模板 SHALL 包含4区块对应4个sheet（每个区块一个sheet，含列头+填写说明）
5.6 THE 导入 SHALL 按sheet名匹配区块，校验列头后解析行数据

### Requirement 6: 版本链集成

**User Story:** As a 审计助理, I want to G0函证底稿自动记录版本快照并可查看历史, so that 满足质量控制要求。

#### Acceptance Criteria

6.1 THE GtConfirmationDiffSecurities/GtConfirmationAlternativeG06 主入口 SHALL 集成 useVersionTrail composable（auto-snapshot on save）
6.2 WHEN 用户保存底稿时, THE useVersionTrail SHALL 自动创建版本快照
6.3 THE 工具栏 SHALL 提供"版本历史"按钮，点击打开 GtWpVersionTrail 抽屉面板
6.4 THE useVersionTrail SHALL 支持手动创建命名快照

### Requirement 7: 公式引擎（G0专属）

**User Story:** As a 开发者, I want to 实现G0证券差异核对与替代程序公式引擎, so that 差异计算和处置损益可PBT验证。

#### Acceptance Criteria

7.1 THE Formula_Engine SHALL 实现 `calcQuantityDiff`（数量差异 = 回函持仓 - 账面持仓）
7.2 THE Formula_Engine SHALL 实现 `calcFairValueDiff`（公允价值差异 = 回函公允值 - 账面公允值）
7.3 THE Formula_Engine SHALL 实现 `calcMarketValueDiff`（市值差异 = 回函总市值 - 账面总市值）
7.4 THE Formula_Engine SHALL 实现 `calcDisposalGain`（处置损益 = 成交金额 - 原始成本 - 手续费）
7.5 THE Formula_Engine SHALL 实现 `calcDividendDiff`（股利差异 = 应收股利 - 实收金额 - 红利税）
7.6 THE Formula_Engine SHALL 实现 `hasDifference`（有差异 = |数量差异|>0 OR |公允价值差异|>0.01）

## Correctness Properties

> 以下性质将通过Property-Based Testing验证G0公式引擎的正确性。

**P1: 数量差异公式** — ∀ confirmed, booked ∈ ℤ: calcQuantityDiff(confirmed, booked) === confirmed - booked

**P2: 公允价值差异公式** — ∀ confirmedFV, bookedFV ∈ ℝ: calcFairValueDiff(confirmedFV, bookedFV) === confirmedFV - bookedFV

**P3: 市值差异公式** — ∀ confirmedMV, bookedMV ∈ ℝ≥0: calcMarketValueDiff(confirmedMV, bookedMV) === confirmedMV - bookedMV

**P4: 处置损益公式** — ∀ proceeds, cost, fee ∈ ℝ≥0: calcDisposalGain(proceeds, cost, fee) === proceeds - cost - fee

**P5: 股利差异恒等** — ∀ declared, received, tax ∈ ℝ≥0: calcDividendDiff(declared, received, tax) === declared - received - tax

**P6: 差异判定定义一致性** — ∀ qtyDiff ∈ ℝ, fvDiff ∈ ℝ: hasDifference(qtyDiff, fvDiff) === (|qtyDiff|>0 ∨ |fvDiff|>0.01)

**P7: 零差异恒等** — ∀ v ∈ ℝ: calcQuantityDiff(v, v) === 0 ∧ calcFairValueDiff(v, v) === 0 ∧ calcMarketValueDiff(v, v) === 0

**P8: 处置损益与手续费反比** — ∀ proceeds, cost固定, fee1 > fee2 ≥ 0: calcDisposalGain(proceeds, cost, fee1) < calcDisposalGain(proceeds, cost, fee2)
