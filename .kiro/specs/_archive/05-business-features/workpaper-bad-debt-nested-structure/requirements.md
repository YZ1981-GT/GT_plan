# Requirements Document

## Introduction

底稿 D2-3（应收账款坏账准备明细表）需要嵌套子表结构支持，以实现致同 2025 修订版模板中父行-子行层级数据录入。该底稿包含两个计提类别父行（单项评估计提、信用风险组合计提）及其下属明细子行，具有自动汇总、试算表预填、调整分录联动等需求。模板结构为 14 列（期初系列/本期增加/本期减少/期末系列），子行支持动态增删，父行和合计行金额自动计算。

## Glossary

- **Bad_Debt_Sheet**: 坏账准备明细表（D2-3），属于 D2 应收账款审定表的子 sheet
- **Provision_Method**: 坏账计提方法枚举类型，定义计提分类标准
- **Parent_Row**: 父行，代表一种计提类别（如"按单项评估计提"），拥有完整 14 列数据
- **Child_Row**: 子行，代表具体客户或组合明细（如"其中：某某公司"），仅 E/K/N 列必填
- **Summary_Row**: 合计行，汇总所有 Parent_Row 金额
- **Auto_SUM_Engine**: 自动汇总引擎，负责父行汇总子行、合计行汇总父行
- **Prefill_Service**: 辅助预填服务，从试算表读取坏账准备科目余额自动带入
- **AJE_Generator**: 调整分录建议生成器，根据审定数与未审数差额生成建议分录
- **Nested_Table_Service**: 嵌套子表服务，管理父子行 CRUD 和层级关系
- **Trial_Balance**: 试算表，提供科目余额数据源
- **Univer_Editor**: 前端 Univer 表格编辑器，承载 D2-3 的交互编辑

## Requirements

### Requirement 1: 坏账计提方法枚举定义

**User Story:** As a 审计人员, I want to 从预定义的坏账计提方法列表中选择分类, so that 坏账准备明细表的父行分类标准统一且规范。

#### Acceptance Criteria

1. THE Provision_Method SHALL 定义以下枚举值：INDIVIDUAL（按单项评估计提）、CREDIT_RISK_AGING（信用风险组合-账龄分析法）、CREDIT_RISK_OTHER（信用风险组合-其他组合）、OTHER（其他）
2. THE Nested_Table_Service SHALL 将每个 Parent_Row 关联一个 Provision_Method 枚举值
3. WHEN 创建新 Parent_Row, THE Nested_Table_Service SHALL 要求指定 Provision_Method 且不允许同一 sheet 内出现重复的 Provision_Method
4. THE Provision_Method SHALL 支持通过 API 查询可用枚举列表及其中文显示名称


### Requirement 2: 嵌套子表数据结构

**User Story:** As a 审计人员, I want to 在坏账准备明细表中按"计提类别→具体明细"的层级录入数据, so that 我可以清晰展示每种计提方法下的具体客户或组合信息。

#### Acceptance Criteria

1. THE Nested_Table_Service SHALL 支持两层嵌套结构：Parent_Row（计提类别）包含零到多个 Child_Row（明细行）
2. THE Parent_Row SHALL 包含完整 14 列数据字段：项目名、期初未审数、期初账项调整、重分类调整(期初)、期初审定数、本期计提、其他增加、本期转回、核销、其他减少、期末未审数、期末账项调整、重分类调整(期末)、期末审定数
3. THE Child_Row SHALL 至少包含项目名、期初审定数(E)、期末未审数(K)、期末审定数(N) 三个必填金额列，其余列可为空
4. WHEN 用户新增 Child_Row, THE Nested_Table_Service SHALL 将其插入到指定 Parent_Row 的子行列表末尾并分配唯一排序号
5. WHEN 用户删除 Child_Row, THE Nested_Table_Service SHALL 从父行中移除该子行并重新计算父行汇总
6. THE Nested_Table_Service SHALL 为每行维护 row_id（UUID）、parent_row_id（父行为 null，子行指向父行）、sort_order（排序号）、provision_method（仅父行有值）

### Requirement 3: 自动汇总（Auto-SUM）

**User Story:** As a 审计人员, I want to 父行金额自动等于其子行合计、合计行自动等于所有父行合计, so that 我不需要手动计算汇总值且不会出错。

#### Acceptance Criteria

1. WHEN 任意 Child_Row 金额字段发生变更, THE Auto_SUM_Engine SHALL 重新计算该子行所属 Parent_Row 的对应列汇总值
2. WHEN 任意 Parent_Row 金额发生变更（含因子行变动触发的重算）, THE Auto_SUM_Engine SHALL 重新计算 Summary_Row 的对应列汇总值
3. THE Auto_SUM_Engine SHALL 对 14 列中的 13 个金额列（B~N，排除 A 项目名）分别独立计算汇总
4. THE Auto_SUM_Engine SHALL 验证期末审定数(N) = 期初审定数(E) + 本期计提(F) + 其他增加(G) - 本期转回(H) - 核销(I) - 其他减少(J) + 期末账项调整(L) + 重分类调整(M)，不满足时在该行标记校验警告
5. WHEN Parent_Row 无 Child_Row, THE Auto_SUM_Engine SHALL 允许用户直接编辑 Parent_Row 金额而不强制清零
6. FOR ALL 金额计算, THE Auto_SUM_Engine SHALL 使用 Decimal 精度且保留两位小数


### Requirement 4: 试算表辅助预填

**User Story:** As a 审计人员, I want to 从试算表坏账准备科目(1231)自动带入期初/期末未审数, so that 我不需要手动查找和抄录科目余额。

#### Acceptance Criteria

1. WHEN 用户打开 Bad_Debt_Sheet 且 Summary_Row 的期初未审数(B)为空, THE Prefill_Service SHALL 从 Trial_Balance 查询科目 1231（坏账准备）的 opening_balance 并填入 Summary_Row 的期初未审数(B)
2. WHEN 用户打开 Bad_Debt_Sheet 且 Summary_Row 的期末未审数(K)为空, THE Prefill_Service SHALL 从 Trial_Balance 查询科目 1231（坏账准备）的 unadjusted_amount 并填入 Summary_Row 的期末未审数(K)
3. THE Prefill_Service SHALL 仅在目标单元格为空时执行预填，已有用户输入值时不覆盖
4. WHEN Trial_Balance 中无科目 1231 数据, THE Prefill_Service SHALL 跳过预填且不报错
5. WHEN 预填成功, THE Prefill_Service SHALL 在单元格添加来源标注（如 tooltip 显示"来自试算表 1231 坏账准备"）

### Requirement 5: 调整分录联动

**User Story:** As a 审计人员, I want to 当坏账准备审定数与未审数存在差额时系统自动生成建议调整分录, so that 我可以快速决定是否调整并保持调整分录与底稿一致。

#### Acceptance Criteria

1. WHEN Summary_Row 的期末审定数(N)与期末未审数(K)存在差额, THE AJE_Generator SHALL 计算差额并生成建议调整分录
2. THE AJE_Generator SHALL 生成的调整分录包含：借方科目（资产减值损失/信用减值损失）、贷方科目（坏账准备 1231）、金额（审定数-未审数绝对值）、摘要说明
3. WHEN 审定数 > 未审数（需补提）, THE AJE_Generator SHALL 生成借记资产减值损失/贷记坏账准备的分录
4. WHEN 审定数 < 未审数（需冲回）, THE AJE_Generator SHALL 生成借记坏账准备/贷记资产减值损失的分录
5. THE AJE_Generator SHALL 将建议分录标记为 suggested 状态，审计人员确认后才写入正式调整分录表
6. WHEN 用户修改 Summary_Row 的审定数或未审数, THE AJE_Generator SHALL 重新计算差额并更新建议分录（覆盖旧建议）


### Requirement 6: 前端 Univer 编辑器交互

**User Story:** As a 审计人员, I want to 在 Univer 表格中直观地编辑嵌套子表（展开/折叠子行、右键新增/删除子行）, so that 操作体验接近 Excel 且无需离开底稿编辑页面。

#### Acceptance Criteria

1. THE Univer_Editor SHALL 按层级渲染 Bad_Debt_Sheet：Parent_Row 显示为加粗行，Child_Row 缩进显示"其中：{项目名}"
2. WHEN 用户点击 Parent_Row 的展开/折叠图标, THE Univer_Editor SHALL 切换该父行下所有 Child_Row 的可见性
3. WHEN 用户右键点击 Parent_Row, THE Univer_Editor SHALL 显示上下文菜单包含"新增子行"选项
4. WHEN 用户右键点击 Child_Row, THE Univer_Editor SHALL 显示上下文菜单包含"删除子行"和"在上方插入子行"和"在下方插入子行"选项
5. WHEN 用户执行新增/删除子行操作, THE Univer_Editor SHALL 调用后端 API 持久化变更并刷新汇总值显示
6. THE Univer_Editor SHALL 对 Summary_Row 和 Parent_Row 的汇总列（由 Auto_SUM 计算的列）设置只读保护，阻止直接编辑
7. WHILE Parent_Row 包含 Child_Row, THE Univer_Editor SHALL 对该 Parent_Row 的金额列设置只读保护（金额由子行汇总决定）

### Requirement 7: 致同 D2-3 模板对齐与导出

**User Story:** As a 项目经理, I want to 导出的坏账准备明细表与致同模板 14 列结构完全一致, so that 归档和质控时格式符合事务所标准。

#### Acceptance Criteria

1. WHEN 导出 Bad_Debt_Sheet 为 xlsx, THE Export_Engine SHALL 按致同模板结构输出 14 列：A(项目名) B(期初未审数) C(期初账项调整) D(重分类调整) E(期初审定数) F(本期计提) G(其他增加) H(本期转回) I(核销) J(其他减少) K(期末未审数) L(期末账项调整) M(重分类调整) N(期末审定数)
2. THE Export_Engine SHALL 按模板行顺序输出：表头行(R10-R11) → 单项评估计提父行(R12) → 子行 → 信用风险组合计提父行 → 子行 → 合计行
3. WHEN Child_Row 某金额列为空, THE Export_Engine SHALL 在对应单元格输出空值而非零
4. THE Export_Engine SHALL 在导出文件中保留表头区域（R1-R9）的事务所名称、被审计单位、审计期间等元信息
5. THE Export_Engine SHALL 对 Parent_Row 的"其中"子行使用缩进格式（A 列前加两个空格）以区分层级


### Requirement 8: 数据持久化与 API

**User Story:** As a 开发者, I want to 嵌套子表数据以结构化方式存储在数据库中, so that 前后端交互明确、查询高效、支持审计追溯。

#### Acceptance Criteria

1. THE Nested_Table_Service SHALL 将嵌套行数据存储在专用表（bad_debt_detail_rows）中，包含字段：id(UUID PK)、wp_index_id(FK)、parent_row_id(self-FK, nullable)、provision_method(enum, nullable)、sort_order(int)、row_label(varchar)、amount_b ~ amount_n(13 个 NUMERIC(18,2) 列)、created_at、updated_at
2. THE Nested_Table_Service SHALL 提供 RESTful API：GET（读取全部行含层级）、POST（新增子行）、PUT（更新单行金额）、DELETE（删除子行）
3. WHEN GET 请求返回数据, THE Nested_Table_Service SHALL 以树形结构返回（Parent_Row 嵌套 children 数组）
4. WHEN DELETE 父行, THE Nested_Table_Service SHALL 级联删除其所有子行
5. IF 并发编辑冲突（同一行同时被两人修改）, THEN THE Nested_Table_Service SHALL 使用乐观锁（version 字段）检测冲突并返回 409 错误

### Requirement 9: 公式引擎集成

**User Story:** As a 审计人员, I want to 其他底稿可以通过公式引用 D2-3 的汇总数据（如本期计提合计）, so that 跨底稿数据联动自动计算。

#### Acceptance Criteria

1. THE Auto_SUM_Engine SHALL 将 Summary_Row 的关键汇总值注册为可引用地址：本期计提合计、本期转回合计、核销合计、期末余额
2. WHEN 其他底稿公式引用 `=WP('D2','坏账准备明细表D2-3','本期计提合计')`, THE FormulaEngine SHALL 返回 Summary_Row 的 F 列值
3. WHEN Bad_Debt_Sheet 数据变更导致汇总值改变, THE Auto_SUM_Engine SHALL 触发依赖此地址的下游公式重算
4. THE FormulaEngine SHALL 支持按 Parent_Row 级别引用（如 `=WP('D2','坏账准备明细表D2-3','单项评估计提.期末审定数')`）返回特定父行的值

### Requirement 10: 数据校验与完整性

**User Story:** As a 审计人员, I want to 系统自动校验坏账准备明细表的数据一致性, so that 我能及时发现录入错误或逻辑矛盾。

#### Acceptance Criteria

1. THE Auto_SUM_Engine SHALL 校验 Summary_Row 的期末审定数(N)是否等于 Trial_Balance 中科目 1231 的 audited_amount，不等时标记差异提示
2. WHEN Parent_Row 的子行合计与父行显示值不一致（因手动覆盖或数据损坏）, THE Nested_Table_Service SHALL 在该行标记校验错误并提供"重新汇总"操作
3. THE Nested_Table_Service SHALL 校验所有金额字段不超过 NUMERIC(18,2) 精度范围
4. WHEN 数据保存时, THE Nested_Table_Service SHALL 验证层级关系完整性：Child_Row 的 parent_row_id 必须指向同一 wp_index_id 下的有效 Parent_Row
5. IF 用户删除最后一个 Parent_Row, THEN THE Nested_Table_Service SHALL 拒绝操作并提示至少保留一个计提类别

### Requirement 11: 嵌套结构序列化与反序列化

**User Story:** As a 开发者, I want to 嵌套子表结构可以完整序列化为 JSON 并从 JSON 恢复, so that 导入导出和版本快照可以保存完整层级数据。

#### Acceptance Criteria

1. THE Nested_Table_Service SHALL 提供 serialize 方法将完整嵌套结构（含父行、子行、排序、枚举值）输出为 JSON 格式
2. THE Nested_Table_Service SHALL 提供 deserialize 方法从 JSON 恢复完整嵌套结构到数据库
3. FOR ALL 有效的嵌套结构数据, 执行 serialize 再 deserialize 后得到的结构 SHALL 与原始数据在语义上等价（round-trip property）
4. WHEN deserialize 输入的 JSON 缺少必要字段或层级关系无效, THE Nested_Table_Service SHALL 返回详细的验证错误列表而非静默忽略
