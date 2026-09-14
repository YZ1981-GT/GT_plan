# Requirements Document

## Introduction

G0 投资循环函证有**两张差异核对表**，与其他枢纽只有一张 X0-4 差异调节表不同：

- `函证差异核对表G0-3（证券投资）`：源模板 17 列，差异按 **数量 / 市价 / 公允价值 三维**核对
- `函证差异核对表G0-4(非证券投资)`：源模板 15 列，差异按 **持股比例 / 投资金额 / 投资条款 × 账面·回函·差异 三维**核对

平台现状：
- 证券投资表有专属组件 `g0-confirmation/diffSecurities/`（344 行），但**缺 5 列**（询证函索引号、资金账号、开户名称、账面余额、相关支持性证据），且「是否需要调账」被做成自由文本（源模板是判断列），另自造了源模板没有的 `security_code` / `security_type`
- 非证券投资表被指向共享 `diffReconcile`（单维金额调节），**持股比例列与投资条款列无处落**——结构不匹配

**前置依赖**：这两张表的**可达性**（sheet_name 精确 override，因编码不在 sheet 名尾部导致 override 落空、`diffSecurities` 组件此前全平台零渲染）由 `confirmation-hub-workbench-tabs` 的 Requirement 10 修复。本 spec 只做**渲染可达之后的结构正确性**。

**范围边界**：不改共享 `diffReconcile` 的既有单维模型（其他六枢纽在用，零回归红线）；不改 G0-1 汇总表与 G0-6 替代程序（后者归 `confirmation-alternative-structure-alignment`）；不改台账数据模型；不新增源模板没有的列。

## Glossary

| 术语 | 含义 |
|------|------|
| Securities_Diff_Sheet | `函证差异核对表G0-3（证券投资）`，源模板 17 列，数量/市价/公允价值三维 |
| NonSecurities_Diff_Sheet | `函证差异核对表G0-4(非证券投资)`，源模板 15 列，持股比例/投资金额/投资条款 × 账面·回函·差异 |
| Three_Dim_Diff | 「同一被投资单位在多个计量维度上分别有 账面值 / 回函值 / 差异」的差异结构 |
| Shared_Diff_Reconcile | 共享 `diffReconcile` 组件与 `DiffReconcileRow`（单维金额调节，六枢纽共用） |
| Adjust_Decision | 源模板「是否需要调账」判断列（是 / 否 / 待定 之类枚举，非自由文本） |
| Source_Extra_Field | 现有实现中超出源模板的字段（如 `security_code` / `security_type`） |

## Requirements

### Requirement 1: Securities_Diff_Sheet 按源模板补齐 17 列

**User Story:** 作为审计助理，我要在证券投资差异核对表里填询证函索引号、资金账号、开户名称、账面余额和支持性证据，现在这几列没有。

#### Acceptance Criteria

1. WHEN 渲染 Securities_Diff_Sheet THEN 系统 SHALL 提供源模板全部 17 列，含现缺的 询证函索引号 / 资金账号 / 开户名称 / 账面余额 / 相关支持性证据
2. WHEN 补列 THEN 列顺序与分组表头 SHALL 与源模板一致（数量 / 市价 / 公允价值 三维分组）
3. WHEN 「是否需要调账」渲染 THEN 系统 SHALL 以判断列（点选枚举）呈现而非自由文本，且既有已录文本 SHALL 可回显或可映射为枚举，SHALL NOT 丢失
4. WHERE 现有 `security_code` / `security_type` 无源模板对应 THE 系统 SHALL 保留并登记为 Source_Extra_Field，且 SHALL NOT 静默删除既有数据
5. WHERE 询证函索引号可从 G0-1 取得 THE 系统 SHALL 提供从 G0-1 带入并去重

### Requirement 2: NonSecurities_Diff_Sheet 三维模型（不套用 Shared_Diff_Reconcile）

**User Story:** 作为审计助理，非证券投资的差异要按持股比例、投资金额、投资条款三个维度分别记录账面数与回函数，单维金额调节表装不下。

#### Acceptance Criteria

1. WHEN 渲染 NonSecurities_Diff_Sheet THEN 系统 SHALL 提供 Three_Dim_Diff 结构：持股比例 / 投资金额 / 投资条款 各有 账面 / 回函 / 差异
2. WHERE 维度为持股比例 THE 系统 SHALL 以百分比口径录入与展示（含比例 scale 明确定义），且差异 SHALL 按百分点计算
3. WHERE 维度为投资条款 THE 系统 SHALL 以文本载体记录账面条款与回函条款，且差异 SHALL 以「是否一致 + 差异说明」表达而非数值相减
4. WHEN 该表落地 THEN 系统 SHALL NOT 修改 Shared_Diff_Reconcile 的行模型或渲染（六枢纽零回归）
5. WHEN 该表落地 THEN 系统 SHALL 提供源模板全部 15 列，且 SHALL NOT 新增源模板没有的列
6. WHERE 既有项目已把非证券差异录在 Shared_Diff_Reconcile 中 THE 系统 SHALL 保证既有数据可回显或明确给出迁移路径，且 SHALL NOT 静默丢弃

### Requirement 3: 差异与上下游一致

**User Story:** 作为现场经理，G0-1 汇总表里标了「不符」的行，应该能在差异核对表里找到对应的核对记录。

#### Acceptance Criteria

1. WHEN G0-1 存在 match_status 为「不符」的行 THEN 系统 SHALL 使其可被差异核对表带入或以待核对提示呈现
2. WHEN 差异核对表有行 THEN 系统 SHALL 支持标注其对应的 G0-1 函证索引号，形成可追溯链
3. WHERE 差异核对表结论为「需要调账」THE 系统 SHALL 使该结论可被下游（调整分录 / 未更正错报）消费或至少给出明确提示与索引
4. WHERE 无法自动关联 THE 系统 SHALL 提供手工填索引且 SHALL NOT 静默断链

### Requirement 4: 两表分工明确不重复录

**User Story:** 作为审计助理，我不想同一笔差异在证券表和非证券表里都要填一遍。

#### Acceptance Criteria

1. WHEN 定义两表适用范围 THEN 系统 SHALL 在底稿内明示（证券投资 / 非证券投资），且 SHALL NOT 让同一被投资单位同时要求在两表录入
2. WHERE 某被投资单位性质不明 THE 系统 SHALL 允许审计师选择归属而 SHALL NOT 自动双写
3. WHEN 两表都有数据 THEN 差异合计口径 SHALL 明确（分别合计，不隐式相加）

### Requirement 5: 零回归

**User Story:** 作为平台维护者，共享差异调节表被六个枢纽用着，G0 的改造不能碰它。

#### Acceptance Criteria

1. WHEN 本 spec 改动落地 THEN Shared_Diff_Reconcile 在 D0/E0/F0/H0/K0/L0 的行为 SHALL 逐字不变
2. WHEN 本 spec 改动落地 THEN 既有函证域前端测试 SHALL 全部通过
3. WHEN 本 spec 改动落地 THEN G0 其余 sheet（G0-1 / G0-2 / 跟函 / 替代程序 / 可靠性 / 舞弊）行为 SHALL 不变
4. WHERE 两表改造分批实施 THE 每批 SHALL 独立可发布且可单独回退

### Requirement 6: 不臆造与可追溯

**User Story:** 作为业务合伙人，差异核对表的每一列都要能对上致同源模板。

#### Acceptance Criteria

1. WHERE 某列在 G0 源模板中不存在 THE 系统 SHALL NOT 新增
2. WHEN 新增任一字段 THEN 系统 SHALL 标注其源模板出处（sheet + 列名）
3. WHERE 保留 Source_Extra_Field THE 系统 SHALL 集中登记（可被守卫读取）并说明依据

### Requirement 7: 属性化可测

**User Story:** 作为平台维护者，三维差异的计算规则要有测试锁定。

#### Acceptance Criteria

1. WHEN 定义 Three_Dim_Diff THEN 系统 SHALL 具备属性测试：数值维度差异 = 账面 − 回函（符号与口径固定）；比例维度差异按百分点；条款维度不做数值相减
2. WHEN 定义两表列集合 THEN 系统 SHALL 具备契约测试：列集合与源模板清单（数据文件登记）一致，漂移即失败
3. WHEN 定义既有数据回显 THEN 系统 SHALL 具备 round-trip 属性测试
4. WHEN 定义 Requirement 5 THEN 系统 SHALL 具备守卫：`diffReconcile` 的行模型与渲染未被本 spec 改动
