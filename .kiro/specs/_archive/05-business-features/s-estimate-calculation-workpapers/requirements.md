# Requirements Document

> S 类计算型专项底稿专属组件（S3 会计政策变更 / S15 每股收益与净资产收益率 / S20 营业收入扣除 / S21 数据资产）

## Introduction

本 spec 覆盖 S 类特定项目程序中 **4 个计算密集型专项底稿**，它们均含大量公式计算、审定表回写与附注披露，需参照 D4 标准开发为**专属组件**（sheetName v-if 分发 + composable 公式引擎分层 + TB 回写联动 + EventBus + GtIndexChip + 导入导出）：

- **S3 会计政策变更、前期差错更正、会计估计变更**：审定表 + S3-1/2 变更程序 + S3-4/6/8 首次执行新金融/收入/租赁准则调整 + S3-9/10 简化追溯调整法（137+ 公式）
- **S15 每股收益和净资产收益率**：审定表 + S15-2 基本每股收益（加权平均股数公式链）+ S15-3 稀释每股收益 + S15-4 净资产收益率（全面摊薄/加权平均 ROE 公式链）
- **S20 营业收入扣除情况核查**：扣除项目合计/占比公式，区分「与主营业务无关的业务收入」与「不具备商业实质的收入」，取审定数
- **S21 数据资产**：审定表 + S21-1 基本情况 + S21-2 开发支出资本化分析（12 月分摊 + 占比）+ S21-3 成本归集与分摊 + S21-4 摊销政策

这些底稿的核心价值在于计算的准确性、与试算表/报表的联动取数、以及非经常性损益/披露的追溯能力。

## Glossary

- **专属组件**：以 sheetName prop 用 v-if 分发内部各 sheet 的 Vue 组件，不含内部 el-tabs（对齐 D4 标准）
- **componentType**：本 spec 新增 4 个 —— `s3-policy-change` / `s15-eps-roe` / `s20-revenue-deduction` / `s21-data-asset`
- **useXFormulaEngine**：各底稿的纯函数公式引擎 composable（如 useS15FormulaEngine / useS21FormulaEngine / useS20FormulaEngine / useS3AdjustmentEngine）
- **审定表回写**：将审定金额写回 trial_balance（audited_amount，v2 正数口径）
- **加权平均股数**：基本每股收益分母，公式 b = b0+b1+b2-b3-b4（期初 + 转增 + 新增加权 - 回购加权 - 并股）
- **全面摊薄 ROE**：P÷E（净利润 ÷ 期末净资产）
- **加权平均 ROE**：P÷(E0 + NP÷2 + Ei×Mi÷M0 - Ej×Mj÷M0 ± Ek×Mk÷M0)
- **营业收入扣除**：财务类强制退市标准下，从营业收入中扣除「与主营业务无关的业务收入」与「不具备商业实质的收入」
- **开发支出资本化**：数据资产开发阶段支出满足 5 项条件后资本化确认为无形资产
- **非经常性损益**：会计政策变更/非货币性资产交换/债务重组损益等，需在披露中标注
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **auto_data_source / resolver**：审定表/计算表的自动取数标识与取数函数
- **导入导出三级**：导出模板 / 导出数据 / 导入数据（复用 useXImportExport composable + 后端三端点）

## Requirements

### Requirement 1: 四个专属组件注册

**User Story:** 作为审计助理，我希望点击 S3/S15/S20/S21 时打开各自的专属精美组件，而非通用 univer/onlyoffice 渲染。

#### Acceptance Criteria

1. THE 系统 SHALL 在 htmlRendererRegistry 注册 4 个 componentType：`s3-policy-change`、`s15-eps-roe`、`s20-revenue-deduction`、`s21-data-asset`，均 defineAsyncComponent 延迟加载
2. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 注册上述 4 个 componentType，后端 validate_overrides 校验通过
3. THE wp_code_overrides SHALL 将 S3→`s3-policy-change`、S15→`s15-eps-roe`、S20→`s20-revenue-deduction`、S21→`s21-data-asset`
4. THE 各专属组件 SHALL 具备 RENDERER_DISPATCH 后端注册，避免被 onlyoffice-sheet 兜底吞掉
5. THE 各专属组件 SHALL 接收 sheetName prop 并以 v-if 分发内部各 sheet（不含内部 el-tabs）

### Requirement 2: S15 每股收益计算

**User Story:** 作为审计助理，我希望 S15-2 基本每股收益按加权平均股数自动计算，减少手工推导。

#### Acceptance Criteria

1. THE useS15FormulaEngine SHALL 以纯函数计算发行在外普通股加权平均数 b = b0 + b1 + b2 - b3 - b4
2. THE useS15FormulaEngine SHALL 计算新增股份加权 c = c1×c2÷m0、债转股加权 d = d1×d2÷m0、回购加权 b3 = e1×e2÷m0
3. THE useS15FormulaEngine SHALL 计算基本每股收益 = 归母净利润 ÷ 加权平均股数，及扣非后基本每股收益 = 扣非归母净利润 ÷ 加权平均股数
4. WHERE 报告期发生配股，THE useS15FormulaEngine SHALL 按含送股因素调整加权平均股数并重算配股后每股收益
5. WHEN 输入项变更时，THE S15 组件 SHALL 实时重算所有派生单元格，公式单元格不可手工覆盖

### Requirement 3: S15 净资产收益率计算

**User Story:** 作为审计助理，我希望 S15-4 净资产收益率的全面摊薄与加权平均口径自动计算。

#### Acceptance Criteria

1. THE useS15FormulaEngine SHALL 计算全面摊薄 ROE = P ÷ E（净利润 ÷ 期末净资产）
2. THE useS15FormulaEngine SHALL 计算加权平均 ROE = P ÷ (E0 + NP÷2 + Ei×Mi÷M0 - Ej×Mj÷M0 ± Ek×Mk÷M0)
3. THE useS15FormulaEngine SHALL 同时输出基本与稀释每股收益，稀释口径含稀释性潜在普通股利息与转换费用调整
4. THE S15 组件 SHALL 同屏对比展示本年/上年两期的 ROE 与 EPS
5. IF 期末净资产为零或缺失，THEN THE useS15FormulaEngine SHALL 返回不可计算标识而非除零错误

### Requirement 4: S20 营业收入扣除计算

**User Story:** 作为审计助理，我希望 S20 自动汇总营业收入扣除项目并计算扣除后金额与占比，判断是否触及强制退市财务类标准。

#### Acceptance Criteria

1. THE useS20FormulaEngine SHALL 计算营业收入 = 主营业务收入 + 其他业务收入（主营 = SUM 明细，其他 = SUM 明细）
2. THE useS20FormulaEngine SHALL 计算营业收入扣除项目合计 = 与主营业务无关的业务收入 + 不具备商业实质的收入
3. THE useS20FormulaEngine SHALL 计算扣除项目占营业收入比重 = 扣除合计 ÷ 营业收入，及扣除后金额 = 营业收入 - 扣除合计
4. THE S20 组件 SHALL 取本年度审定数与上年度追溯调整后审定数两列并行呈现
5. THE S20 组件 SHALL 在顶部以方法论上下文区块展示适用情形提示（利润总额/净利润/扣非净利润孰低为负值时适用）

### Requirement 5: S21 数据资产开发支出资本化计算

**User Story:** 作为审计助理，我希望 S21-2 开发支出资本化分析按月归集并计算各项/各月占比。

#### Acceptance Criteria

1. THE useS21FormulaEngine SHALL 按项目分月（1-12 月）汇总各成本类目（采购/人工/脱敏清洗标注/权属鉴证/质量评估/登记结算/安全管理），本期合计 = SUM(各月)
2. THE useS21FormulaEngine SHALL 计算各成本类目占比 = 类目合计 ÷ 资本化总额，及各月比例 = 月合计 ÷ 资本化总额
3. THE useS21FormulaEngine SHALL 计算研究阶段支出/开发阶段支出的合计（SUM）
4. THE S21-2 组件 SHALL 呈现资本化 5 项条件（技术可行性/使用出售意图/市场需求/技术财力支持/单独核算可靠计量）的逐项判断
5. THE S21-3 组件 SHALL 呈现成本归集与分摊检查（分摊方法 + 适当性评价）
6. WHEN 分月明细变更时，THE 汇总与占比单元格 SHALL 实时重算且不可手工覆盖

### Requirement 6: S3 首次执行新准则调整与追溯

**User Story:** 作为审计助理，我希望 S3 的首次执行新准则调整与简化追溯调整法保留公式计算，减少手工调表出错。

#### Acceptance Criteria

1. THE useS3AdjustmentEngine SHALL 保留 S3-4/6/8（首次执行新金融/收入/租赁准则调整）与 S3-9/10（简化的追溯调整法）源模板的公式语义并实时重算
2. THE S3 组件 SHALL 以 sheetName v-if 分发 S3 审定表 / S3-1 会计政策变更和前期差错更正 / S3-2 会计估计变更 / S3-4/6/8 / S3-9/10 各 sheet
3. THE S3 组件 SHALL 区分「会计政策变更」「前期差错更正」「会计估计变更」三类事项并分别记录追溯调整
4. WHERE 事项属于非经常性损益范畴，THE S3 组件 SHALL 在披露内容中标注非经常性损益

### Requirement 7: 审定表回写试算表

**User Story:** 作为审计助理，我希望含审定表的底稿（S3/S4 系列思路一致）能将审定金额回写试算表，保持全链取数一致。

#### Acceptance Criteria

1. WHERE 底稿含审定表 sheet，THE 组件 SHALL 支持将审定金额回写 trial_balance 的 audited_amount（v2 正数口径）
2. THE 审定表 SHALL 通过 auto_data_source/resolver 自动取数未审数与调整分录，用户可 field_overrides 覆盖
3. WHEN 审定表数据保存时，THE 系统 SHALL 通过 EventBus 发布 WORKPAPER_SAVED 事件触发一致性检查
4. THE 回写 SHALL 仅 flush 不 commit（service 层），由上层统一提交

### Requirement 8: 附注披露联动

**User Story:** 作为审计助理，我希望计算型底稿的结果能联动到附注披露，避免重复录入。

#### Acceptance Criteria

1. WHERE 底稿含附注披露内容（如 S15 每股收益披露、S3 会计政策变更披露、S20 扣除说明），THE 组件 SHALL 提供披露文本区并支持 AI 辅助生成
2. WHEN 披露文本更新时，THE 组件 SHALL 通过 EventBus 发布 `disclosure:note-text-updated` 供附注模块订阅
3. THE 组件 SHALL 订阅 `substantive:adjudicated` 事件在审定金额变化时刷新披露引用数据

### Requirement 9: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望计算取数来源（如审定报表、非经常性损益明细表、B10、B22）以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 计算表的取数说明/索引列包含其他底稿编码，THE 组件 SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击 chip 时，THE 组件 SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 10: 导入导出

**User Story:** 作为审计助理，我希望计算型底稿的动态明细表（如 S21-2 分月归集、S20 扣除明细）支持导入导出，减少手工录入。

#### Acceptance Criteria

1. WHERE 底稿含动态明细行表格，THE 组件 SHALL 提供 el-dropdown「导入导出▾」（导出模板/导出数据/导入数据）
2. THE 导入导出 SHALL 复用 useXImportExport composable + 后端三端点，且使用 http(axios) 而非原生 fetch（避免 401）
3. WHERE 底稿为多区块，THE 导出 SHALL 分 sheet 导出
4. THE 导出的中文文件名 SHALL 按 RFC5987 编码（StreamingResponse）

### Requirement 11: UI 规范与只读

**User Story:** 作为审计助理，我希望计算型底稿 UI 统一、公式可溯源；作为复核合伙人，我希望只读模式下不可编辑。

#### Acceptance Criteria

1. THE 表格 SHALL 使用 13px 字体，公式列以虚线下划线 + cursor:help + tooltip 展示公式来源
2. THE 审计说明/结论区 SHALL 以 el-card 包裹，编制提示以 details 折叠置于底部
3. WHERE 底稿为多步骤，THE 组件 SHALL 在顶部增加蓝色渐变引导区（2 列 grid 序号步骤）
4. WHEN readonly 为 true 时，THE 组件 SHALL 禁止所有输入单元格编辑与明细行增删，仅允许浏览与跳转
5. THE 金额显示 SHALL 默认以「元」为单位并经统一格式化出口（fmt）
