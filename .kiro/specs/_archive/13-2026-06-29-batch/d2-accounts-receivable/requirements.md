# Requirements Document

## Introduction

D2 应收账款审定表是"销售与收款循环"（D 循环）实质性底稿，属于 CAS 1301 审计证据/CAS 1502 应收账款审计范畴。源模板包含 20 个 sheet（底稿目录 + 程序表 D2A + 审定表 D2-1 + 附注 ×4 + 明细表 D2-2 + 坏账准备 D2-3 + 调整分录 D2-4 + GT_Custom + 分析程序 D2-5 + 检查表 ×8），覆盖应收账款按客户/账龄双维度明细、坏账准备（单项计提/账龄组合/客户类型组合三种方式）、函证关联、ECL 预期信用损失测算、截止测试、质押出售（保理）等全流程审计程序。

当前实现使用通用 `d-form-table`/`audit-sheet` 渲染，缺乏应收账款专属交互（审定表三分类 SUMIF 联动、函证结果引用、ECL 双 sheet 测算、分析程序、截止测试）。本 spec 定义一个专属 `d2-accounts-receivable` HTML 组件，将 20 sheet 聚合为统一 Tab 入口，提供：
- 审定表（D2-1）：按"单项计提/账龄组合/客户类型组合"三种坏账计提方式分行 + SUMIF 跨 sheet 引用 + trial_balance 回写
- 程序表（D2A）：7 步审计程序执行状态 + 结论
- 明细表（D2-2）：按客户/账龄双维度展开，audit-sheet 子底稿 lazy 嵌入
- 坏账准备（D2-3/D2-8/D2-9/D2-10/D2-11）：ECL 模型（迁徙率 + 个别认定）+ 计量测试 + 转回核销
- 分析程序（D2-5）：audit-sheet 子底稿 lazy 嵌入
- 关联方（D2-6）：audit-sheet 子底稿 lazy 嵌入
- 检查表（D2-7/D2-8/D2-12/D2-13）：应收账款检查 + 会计政策 + 质押出售 + 业务模式
- 函证关联（D0）：函证确认结果 → 审定表差异

核心价值：
- 20 sheet 统一入口，消除多底稿切换
- 审定表 SUMIF 公式自动计算（跨 sheet 引用 D2-2 按分类聚合数据）
- trial_balance 双向联动：audited_amount 实时回写
- D0 函证结果 → D2 审定表差异联动
- B50 风险评估→程序表步骤范围联动
- C 类控制测试结论（C3 销售与收款循环）→D2 实质性程序范围调整

## Glossary

- **D2_Component**: D2 应收账款专属 Vue 组件（componentType = `d2-accounts-receivable`）
- **Adjudication_Table**: 审定表 D2-1，按单项计提/账龄组合/客户类型组合三种坏账方式分行，汇总未审数/调整数/审定数，回写 trial_balance
- **Procedure_Table**: 审计程序表 D2A，7 步实质性程序执行记录
- **Detail_Sheet**: 明细表 D2-2，按客户/账龄双维度展开应收账款明细，audit-sheet 子底稿
- **Bad_Debt_Sheet**: 坏账准备明细表 D2-3，按账龄段汇总坏账准备变动
- **Adjustment_Summary**: 调整分录汇总表 D2-4
- **Analysis_Sheet**: 应收账款分析表 D2-5（分析程序），audit-sheet 子底稿
- **Related_Party**: 关联方及交易检查表 D2-6，audit-sheet 子底稿
- **AR_Check**: 应收账款检查表 D2-7
- **ECL_Policy_Check**: 坏账准备计提会计政策检查 D2-8
- **ECL_Calculation**: 应收坏账准备测算 D2-9（迁徙率法 / ECL 模型）
- **ECL_Measurement_Test**: 预期信用损失的计量测试 D2-10
- **WriteOff_Reversal**: 坏账准备转回（收回）、核销检查表 D2-11
- **Pledge_Factoring**: 应收账款质押出售情况检查表 D2-12（含保理合同分析）
- **Business_Model_Analysis**: 应收账款业务模式分析 D2-13
- **Disclosure_Listed**: 附注披露信息（上市公司）D2-1
- **Disclosure_SOE**: 附注披露信息（国企）D2-1
- **Disclosure_Listed_General**: 附注披露信息（上市公司）通用
- **Disclosure_SOE_General**: 附注披露信息（国企）通用
- **GT_Custom**: 自定义扩展 sheet
- **trial_balance**: 试算平衡表，audited_amount 为审定数权威字段（科目 1122 应收账款）
- **ECL_Model**: 预期信用损失模型（Expected Credit Loss），IFRS 9 / CAS 22 三阶段减值
- **SUMIF_Aggregation**: 审定表 SUMIF 跨 sheet 公式，按"单项计提/账龄组合/客户类型组合"分类从 D2-2 聚合
- **Migration_Rate**: 迁徙率法，通过历史损失数据推算各账龄段的迁徙概率
- **Confirmation_Linkage**: D0 函证模块与 D2 的联动（函证确认结果影响应收账款差异）
- **Cutoff_Test**: 截止测试，检查期末前后收入确认和应收账款入账的截止正确性
- **Factoring_Analysis**: 保理合同分析，应收账款出售/保理的终止确认判断
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `D2-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **EventBus**: 进程内事件总线，D2 发布 `substantive:adjudicated` 事件
- **GtWpRenderer**: 子底稿懒加载渲染器，用于 Tab 内嵌 audit-sheet 子底稿
- **displayPrefs**: 金额/百分比/日期统一格式化出口

## Requirements

### Requirement 1: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 D2 底稿时自动渲染专属组件。

#### Acceptance Criteria

1. THE D2_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `d2-accounts-receivable`，contextProps 为 `standard`
2. THE D2_Component SHALL 在 wp_code_overrides.json 中将 `D2` 映射为 `d2-accounts-receivable`（替换现有 `d-form-table`）
3. THE D2_Component SHALL 在 wp_code_overrides.json 中将 `D2-1` 映射为 `skip`（由 D2 统一渲染审定表）
4. THE D2_Component SHALL 在 wp_code_overrides.json 中将 `D2-3` 映射为 `skip`（由 D2 统一渲染坏账准备）
5. THE D2_Component SHALL 在 wp_code_overrides.json 中将 `D2-4` 映射为 `skip`（由 D2 统一渲染调整分录）
6. THE D2_Component SHALL 在 wp_code_overrides.json 中保留 `D2-2` 为 `audit-sheet`（明细表子底稿 lazy 嵌入 Tab）
7. THE D2_Component SHALL 在 wp_code_overrides.json 中保留 `D2-5` 为 `audit-sheet`（分析程序子底稿 lazy 嵌入 Tab）
8. THE D2_Component SHALL 在 wp_code_overrides.json 中保留 `D2-6` 为 `audit-sheet`（关联方子底稿 lazy 嵌入 Tab）
9. THE D2_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
10. THE D2_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
11. WHEN 后端 render-config 返回 componentType 为 `d2-accounts-receivable` 时, THE 前端路由 SHALL 正确加载 D2_Component

### Requirement 2: 20 Sheet Tab 统一入口

**User Story:** As a 审计助理, I want 在一个界面通过 Tab 页签访问所有 20 个 sheet, so that 无需在多个底稿间切换即可完成应收账款全流程审计。

#### Acceptance Criteria

1. THE D2_Component SHALL 渲染顶部 Tab 页签栏，包含以下分组 Tab：底稿目录、程序表(D2A)、审定表(D2-1)、附注披露、明细表(D2-2)、坏账准备(D2-3)、调整分录(D2-4)、GT_Custom、分析程序(D2-5)、关联方(D2-6)、检查表(D2-7)、会计政策(D2-8)、ECL测算(D2-9)、计量测试(D2-10)、转回核销(D2-11)、质押出售(D2-12)、业务模式(D2-13)
2. THE D2_Component SHALL 将附注披露 Tab 内部提供子切换：上市公司D2-1/国企D2-1/上市公司通用/国企通用（根据项目类型默认选中）
3. THE D2_Component SHALL 对子底稿 D2-2、D2-5、D2-6 的 Tab 使用 GtWpRenderer 懒加载渲染（audit-sheet 模式）
4. THE D2_Component SHALL 对 D2-7 至 D2-13 的 Tab 内容使用 d-form-table 模式内嵌渲染
5. THE D2_Component SHALL 记住用户最后访问的 Tab（localStorage 持久化），下次进入时恢复
6. THE D2_Component SHALL 在 Tab 标签上显示完成状态标记（已完成=绿色勾、进行中=蓝色点、未开始=灰色）
7. WHEN Tab 切换时, THE D2_Component SHALL 懒加载目标 Tab 内容（首次访问时加载，之后缓存）

### Requirement 3: 审定表（D2-1）SUMIF 联动计算

**User Story:** As a 审计助理, I want 审定表自动从明细表按坏账计提分类 SUMIF 取数并计算审定数, so that 减少手工抄数错误并确保审定表与明细表一致。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染审定表结构：行=科目项（应收账款-单项计提/账龄组合/客户类型组合/坏账准备/账面价值/合计），列=期初未审数(E)/期末未审数(I)/审计调整(J)/审定数(K)/变动率(K)
2. THE Adjudication_Table SHALL 从 Detail_Sheet（D2-2）通过 SUMIF 自动引用"单项计提"分类数据：F8←SUMIF(D2-2!AI列,"单项计提",D2-2!S列) 期初、G8←SUMIF(D2-2!AI列,"单项计提",D2-2!Z列) 本期变动、H8←SUMIF(D2-2!AI列,"单项计提",D2-2!AA列) 期末
3. THE Adjudication_Table SHALL 从 Detail_Sheet（D2-2）通过 SUMIF 自动引用"账龄组合"分类数据：F10←SUMIF(D2-2!AI列,"账龄组合",D2-2!S列)、G10←变动、H10←期末
4. THE Adjudication_Table SHALL 从 Detail_Sheet（D2-2）通过 SUMIF 自动引用"客户类型组合"分类数据：F11←SUMIF(D2-2!AI列,"客户类型组合",D2-2!S列)、G11←变动、H11←期末
5. THE Adjudication_Table SHALL 自动计算审定数：审定数 = 未审数 + AJE调整 + RJE重分类
6. THE Adjudication_Table SHALL 自动计算变动率：K列 = IF(E=0 AND I=0, "", IF(E=0 AND I>0, 1, J/E))（J=审定数与期初的差额）
7. WHEN 审定数计算完成后, THE D2_Component SHALL 通过 API 回写 trial_balance 对应科目（1122 应收账款）的 audited_amount
8. THE Adjudication_Table SHALL 使用 displayPrefs.fmtAmount 格式化所有金额单元格
9. WHEN D2-2 明细数据变更时, THE Adjudication_Table SHALL 实时重新计算 SUMIF 引用值

### Requirement 4: 审计程序表（D2A）执行管理

**User Story:** As a 审计助理, I want 在程序表中逐步记录 7 个审计步骤的执行情况, so that 追踪审计程序完成进度并形成结论。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 渲染 7 步审计程序列表：获取并核对明细/核对总账/函证/替代程序/坏账准备/截止测试/结论
2. THE Procedure_Table SHALL 每步包含字段：步骤名称、描述、执行状态（未开始/执行中/已完成/不适用）、执行人、执行日期、工作底稿索引、审计发现、结论
3. THE Procedure_Table SHALL 支持"不适用"标记（适用性自动判断：当科目余额为 0 时提示可标记不适用）
4. WHEN 某步骤标记"已完成"时, THE Procedure_Table SHALL 要求填写结论（不可为空）
5. THE Procedure_Table SHALL 在顶部显示完成进度：N/7 步骤已完成
6. WHEN 全部必要步骤完成时, THE Procedure_Table SHALL 允许录入整体审计结论
7. THE Procedure_Table SHALL 在每步骤右侧提供 ref_chip 跳转到对应 Tab（如"函证"→D0 函证底稿、"坏账准备"→D2-9 Tab）
8. WHEN B50 风险评估发布销售与收款循环重大风险时, THE Procedure_Table SHALL 在相关步骤旁显示风险标识

### Requirement 5: 坏账准备与 ECL 计算

**User Story:** As a 审计助理, I want 系统辅助计算预期信用损失并与被审计单位计提金额比对, so that 快速识别坏账准备计提是否充分。

#### Acceptance Criteria

1. THE Bad_Debt_Sheet SHALL 渲染坏账准备明细表结构：行=账龄段（1年以内/1-2年/2-3年/3-4年/4-5年/5年以上），列=期初余额/本期计提/本期转回/本期核销/期末余额/预期损失率/应计提金额/差异
2. THE D2_Component SHALL 支持三种坏账计提方式：单项计提 / 账龄组合 / 客户类型组合（对应审定表三行分类）
3. WHEN 选择迁徙率法时, THE ECL_Calculation SHALL 提供迁徙率矩阵输入（各账龄段历史迁徙概率），自动计算预期损失率
4. THE D2_Component SHALL 自动计算各账龄段应计提金额：应计提 = 余额 × 预期损失率
5. THE D2_Component SHALL 自动计算差异：差异 = 被审计单位实际计提 - 审计师测算应计提
6. WHEN 差异绝对值超过 B15 重要性水平时, THE D2_Component SHALL 高亮显示差异行并提示"差异超过重要性水平，建议提出调整"
7. THE Bad_Debt_Sheet SHALL 汇总行数据自动回传 Adjudication_Table（D2-1 坏账准备行）
8. THE ECL_Policy_Check SHALL 提供会计政策一致性检查清单（是否变更/变更原因/影响金额）
9. THE ECL_Measurement_Test SHALL 提供预期信用损失计量测试面板：验证 ECL 计算模型输入参数和假设的合理性

### Requirement 6: 函证关联与替代程序

**User Story:** As a 审计助理, I want 应收账款审定表与 D0 函证模块联动, so that 函证确认结果自动反映到审定表差异分析。

#### Acceptance Criteria

1. THE D2_Component SHALL 监听 D0 函证模块的函证完成事件，接收函证确认结果（确认/不一致/未回函）
2. THE D2_Component SHALL 在审定表区域显示函证汇总信息：发函数/回函数/回函率/确认金额/差异金额
3. WHEN 函证结果存在差异时, THE D2_Component SHALL 在审定表对应客户行标注"函证差异"并显示差异金额
4. THE D2_Component SHALL 在程序表"函证"步骤旁提供 ref_chip 跳转到 D0 函证底稿
5. THE D2_Component SHALL 在程序表"替代程序"步骤中提供替代程序记录区：对未回函客户记录替代审计程序执行情况
6. WHEN 替代程序完成后, THE D2_Component SHALL 更新对应客户的审计确认状态

### Requirement 7: 分析程序与截止测试

**User Story:** As a 审计助理, I want 对应收账款执行分析程序和截止测试, so that 从宏观趋势和期末截止两个维度验证应收账款合理性。

#### Acceptance Criteria

1. THE Analysis_Sheet SHALL 通过 GtWpRenderer 懒加载渲染（audit-sheet 模式），提供应收账款分析程序专属面板
2. THE D2_Component SHALL 在分析程序 Tab 中显示关键比率：应收账款周转率/周转天数/账龄分布变化/坏账率趋势
3. WHEN 应收账款周转天数同比变化超过 30% 时, THE D2_Component SHALL 高亮提示"周转效率显著变化，需关注原因"
4. THE D2_Component SHALL 在程序表"截止测试"步骤中提供截止测试记录区：检查期末前后收入确认和应收账款入账的截止正确性
5. THE D2_Component SHALL 支持截止测试样本记录：发票号/收入确认日期/应收入账日期/金额/是否跨期/结论
6. WHEN 存在跨期确认的样本时, THE D2_Component SHALL 在截止测试区域显示红色提示"存在截止错误，需评估影响"

### Requirement 8: 应收账款质押与出售（保理）

**User Story:** As a 审计助理, I want 记录应收账款质押和保理出售情况并判断终止确认条件, so that 验证表外事项和使用受限情况的会计处理是否正确。

#### Acceptance Criteria

1. THE Pledge_Factoring SHALL 渲染质押出售明细表：行=各笔已质押/已保理应收账款，列=客户名称/金额/质押对象或保理商/合同编号/起止日期/是否终止确认/备注
2. THE Pledge_Factoring SHALL 区分两类：质押（限制性资产）与 保理出售（终止确认判断）
3. THE Pledge_Factoring SHALL 提供终止确认判断辅助：是否转移了金融资产所有权上几乎所有风险和报酬（Y/N）+ 是否保留了控制（Y/N）
4. WHEN 标记"不终止确认"时, THE Pledge_Factoring SHALL 在对应行显示"应继续在资产负债表确认，同时确认相关负债"提示
5. THE Pledge_Factoring SHALL 自动汇总：已质押金额合计、已保理金额合计、终止确认金额、不终止确认金额
6. THE Pledge_Factoring SHALL 计算质押比例：已质押金额 / 应收账款总额
7. WHEN 质押比例超过 50% 时, THE Pledge_Factoring SHALL 显示黄色警告"大额质押，需关注流动性和披露"
8. THE D2_Component SHALL 在审定表区域标注已质押/已保理金额（供附注披露引用）

### Requirement 9: 关联方检查与通用检查表

**User Story:** As a 审计助理, I want 检查应收账款涉及的关联方交易和通用审计事项, so that 识别关联方舞弊风险和其他异常。

#### Acceptance Criteria

1. THE Related_Party SHALL 通过 GtWpRenderer 懒加载渲染（audit-sheet 模式），提供关联方及交易检查专属面板
2. THE D2_Component SHALL 提供关联方识别辅助：从项目已录入关联方清单（B 循环数据）自动匹配应收账款客户名称
3. WHEN 存在关联方应收账款且金额超过重要性水平时, THE D2_Component SHALL 显示红色警告"重大关联方应收账款，需充分披露"
4. THE AR_Check SHALL 渲染应收账款通用检查表：包含账龄分析合理性、大额异常交易、长期挂账、期后回款等检查项
5. THE AR_Check SHALL 每项检查提供结论选择：符合/不符合/不适用 + 备注
6. THE D2_Component SHALL 在关联方检查和通用检查完成后，将发现汇总到程序表对应步骤的"审计发现"字段

### Requirement 10: 跨底稿联动（trial_balance + D0 + B50 + C3 + A13）

**User Story:** As a 现场经理, I want D2 审定结果自动联动试算表和其他底稿, so that 审计链路数据一致无需手工同步。

#### Acceptance Criteria

1. WHEN Adjudication_Table 审定数变更时, THE D2_Component SHALL 通过 EventBus 发布 `substantive:adjudicated` 事件（含 wpCode="D2"、科目编码 1122、audited_amount）
2. THE D2_Component SHALL 通过 API 将审定数回写 trial_balance 对应应收账款科目（1122）的 audited_amount 字段
3. THE D2_Component SHALL 监听 B50 风险评估的 `risk:assessed` 事件，接收销售与收款循环风险等级，在程序表步骤旁显示风险标识
4. THE D2_Component SHALL 监听 C 类控制测试的 `control:test-concluded` 事件（C3 对应销售与收款循环），WHEN 控制有效时在程序表显示"控制有效，可适当减少样本量"
5. WHEN 审计调整分录（AJE/RJE）录入审定表时, THE D2_Component SHALL 通过 EventBus 发布 `adjustment:created` 事件供 A13 错报汇总表接收
6. THE D2_Component SHALL 在联动面板提供 ref_chip 跳转：→ trial_balance、→ D0 函证、→ B50 风险评估、→ C3 控制测试、→ A13 错报汇总
7. THE D2_Component SHALL 在组件初始化时从 trial_balance 获取应收账款科目（1122）的 unadjusted_amount 作为审定表未审数初始值
8. THE D2_Component SHALL 监听 D0 函证完成事件，接收函证确认结果并更新审定表函证差异区域

### Requirement 11: 数据持久化

**User Story:** As a 审计助理, I want 所有审计数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE D2_Component SHALL 将程序表/审定表/检查表数据存储到 checklist_responses 表，使用 item_id 前缀 `D2-` 区分字段
2. WHEN 用户编辑文本字段后停止输入 2 秒时, THE D2_Component SHALL 自动保存变更（debounce 2000ms）
3. WHEN 用户变更结论/状态/选择类字段时, THE D2_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE D2_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE D2_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE D2_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原全部 Tab 状态
7. THE D2_Component SHALL 使用结构化 item_id 命名规则：`D2-{sheet}-{field}`（如 `D2-proc-1-status`、`D2-adj-individual-prior`、`D2-ecl-aging1-rate`、`D2-cutoff-1-conclusion`、`D2-factoring-1-derecog`）

### Requirement 12: 复核签字与只读

**User Story:** As a 现场经理, I want 审计程序全部完成后签字复核并锁定, so that 确保底稿结论经审核后不被随意修改。

#### Acceptance Criteria

1. THE D2_Component SHALL 在程序表区域下方提供"现场经理复核"签字区域
2. WHEN 程序表存在未完成的必要步骤时, THE D2_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE D2_Component SHALL 将全组件（所有 Tab）转为只读模式并 emit `completed`
4. WHILE 处于已复核只读模式时, THE D2_Component SHALL 在顶部显示"已复核"绿色横幅和复核人/日期
5. WHEN 外部传入 readonly prop 为 true 时, THE D2_Component SHALL 强制进入只读模式
6. THE D2_Component SHALL 支持 Amendment 模式：填写修改原因后解锁编辑，完成后需重新复核

### Requirement 13: 后端白名单扩展

**User Story:** As a 开发者, I want 后端支持 D2- 前缀的结论值保存, so that 前端发送的应收账款审计数据能正常持久化。

#### Acceptance Criteria

1. THE 后端 checklist_responses 保存逻辑 SHALL 在结论白名单中支持 `D2-` 前缀的 item_id
2. THE 后端 SHALL 接受 D2- 前缀 item_id 的以下结论值：未开始、执行中、已完成、不适用、符合、不符合、单项计提、账龄组合、客户类型组合、终止确认、不终止确认、已披露且准确、已披露但需修改、未披露需补充、组合评估、个别认定、Y、N、是、否、跨期、未跨期
3. THE 后端 SHALL 对 D2- 前缀 item_id 的保存请求执行与现有 D0-/D1-/C{n}- 前缀相同的权限校验
4. IF 前端发送无效的 D2- 前缀结论值, THEN THE 后端 SHALL 返回 422 校验错误并拒绝保存

### Requirement 14: 附注披露检查

**User Story:** As a 审计助理, I want 对照披露要求逐项检查应收账款附注, so that 确保财务报表附注披露完整准确。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染上市公司附注披露检查清单：应收账款分类及账面价值/坏账准备变动（三种方式分别）/已质押应收账款/已保理应收账款/前五名欠款方/关联方应收账款/账龄分析/期后回款情况/会计政策说明
2. THE Disclosure_SOE SHALL 渲染国企附注披露检查清单：按国资委报表附注格式要求列示检查项
3. THE D2_Component SHALL 根据项目属性（上市公司/国企/一般企业）自动选择默认披露模板
4. THE 披露检查清单 SHALL 每项提供结论选择：已披露且准确/已披露但需修改/未披露需补充/不适用 + 备注
5. WHEN 存在"未披露需补充"项时, THE D2_Component SHALL 在程序表对应步骤旁显示红色提醒
6. THE 披露检查结论 SHALL 汇总到程序表"结论"步骤的审计发现字段

### Requirement 15: 调整分录汇总

**User Story:** As a 审计助理, I want 在调整分录 Tab 中汇总管理本底稿产生的所有审计调整, so that 与审定表联动并为 A13 提供数据源。

#### Acceptance Criteria

1. THE Adjustment_Summary SHALL 渲染调整分录汇总表：序号/分录类型(AJE/RJE)/借方科目/贷方科目/金额/摘要/是否已过入审定表
2. THE Adjustment_Summary SHALL 支持新增/编辑/删除调整分录
3. WHEN 新增调整分录时, THE Adjustment_Summary SHALL 自动更新 Adjudication_Table 对应行的调整数列
4. THE Adjustment_Summary SHALL 自动计算 AJE 合计和 RJE 合计
5. WHEN 调整分录删除时, THE Adjustment_Summary SHALL 同步清除 Adjudication_Table 中对应调整数
6. THE Adjustment_Summary SHALL 对每笔分录提供"推送至 A13"操作按钮，通过 EventBus 发布至错报汇总表

---

## Correctness Properties

### Property 1: 审定表公式计算不变式

*For any* 审定表行的未审数(E)、AJE调整(借/贷)、RJE调整(借/贷)值组合，审定数 SHALL 始终等于 E + AJE借 - AJE贷 + RJE借 - RJE贷（借方增贷方减）。变动率(K) SHALL 满足：期初=0且审定数=0→空、期初=0且审定数>0→1、其他→(审定数-期初)/期初。

**Validates: Requirements 3.5, 3.6**

### Property 2: SUMIF 跨 sheet 引用一致性

*For any* D2-2 明细表中 AI 列分类标识（"单项计提"/"账龄组合"/"客户类型组合"）和对应 S/Z/AA 列金额值变更，审定表 D2-1 对应行（F8/G8/H8、F10/G10/H10、F11/G11/H11）SHALL 实时同步更新。SUMIF 聚合结果始终等于源数据按分类过滤后的求和值。

**Validates: Requirements 3.2, 3.3, 3.4, 3.9**

### Property 3: ECL 计算正确性

*For any* 账龄段余额和预期损失率组合，应计提金额 SHALL 等于余额 × 损失率。差异 SHALL 等于实际计提 - 应计提。迁徙率法：最终损失率 = 各阶段迁徙率连乘。所有金额 ≥ 0，损失率 ∈ [0, 1]。

**Validates: Requirements 5.3, 5.4, 5.5**

### Property 4: 质押比例计算正确性

*For any* 已质押金额(P ≥ 0) 和应收账款总额(T > 0)，质押比例 SHALL 等于 P / T。WHEN T = 0 时质押比例 SHALL 为 0（避免除零）。WHEN P / T > 0.5 时 SHALL 触发警告标记为 true。

**Validates: Requirements 8.6, 8.7**

### Property 5: 截止测试样本跨期判定一致性

*For any* 截止测试样本的收入确认日期(revDate)和资产负债表日(bsDate)，WHEN revDate 在 bsDate 之后且对应应收已在 bsDate 前入账时 SHALL 标记"跨期"为 true。跨期判定结果与日期比较逻辑始终一致。

**Validates: Requirements 7.5, 7.6**

### Property 6: trial_balance 回写一致性

*For any* 审定表审定数变更，回写到 trial_balance 的 audited_amount SHALL 等于审定表最终计算的审定数。回写科目编码 SHALL 为 1122（应收账款）。PUT 后 GET 回读值必须一致。

**Validates: Requirements 10.1, 10.2, 10.7**

### Property 7: 数据持久化往返一致性

*For any* 有效的 D2- 前缀 checklist_responses 数据集（程序表状态 + 审定表数值 + ECL 参数 + 检查表结论 + 截止测试样本 + 保理条目），通过 PUT 批量保存后再通过 GET 加载，所有字段的 conclusion 和 remark 值 SHALL 与保存前一致。

**Validates: Requirements 11.5, 11.6**

### Property 8: item_id 命名唯一性与确定性

*For any* (sheet标识 × 序号 × 字段类型) 组合，生成的 item_id SHALL 唯一且确定。不同业务含义的数据不可产生相同 item_id；相同业务含义的数据始终生成相同 item_id。所有生成的 item_id 必须以 `D2-` 前缀开头。

**Validates: Requirements 11.7**

### Property 9: 程序表完成度与复核前置条件

*For any* 7 步程序表的步骤状态组合（每步 ∈ {未开始, 执行中, 已完成, 不适用}），复核签字按钮可用（canReview=true）当且仅当：所有 isRequired=true 的步骤 status 为 "已完成" 或 "不适用"。进度计数 = 状态为"已完成"或"不适用"的步骤数。

**Validates: Requirements 4.5, 4.6, 12.2**

### Property 10: EventBus 事件发射正确性

*For any* 审定数变更操作，WHEN 新旧审定数值不同时 SHALL 发布 `substantive:adjudicated` 事件（载荷含正确的 wpCode="D2"/accountCode="1122"/auditedAmount）。WHEN 值未变时 SHALL 不发布。WHEN 新增调整分录时 SHALL 发布 `adjustment:created` 事件（载荷含正确的分录信息）。

**Validates: Requirements 10.1, 10.5**

### Property 11: 调整分录与审定表双向同步

*For any* 调整分录集合的增/删/改操作，审定表对应行的 AJE 调整列 SHALL 始终等于所有 type='AJE' 分录金额之和，RJE 调整列 SHALL 始终等于所有 type='RJE' 分录金额之和。AJE合计 = Σ(AJE entries)，RJE合计 = Σ(RJE entries)。

**Validates: Requirements 15.3, 15.5**

### Property 12: 后端白名单校验正确性

*For any* item_id 以 `D2-` 开头的保存请求，conclusion 值在白名单（未开始/执行中/已完成/不适用/符合/不符合/单项计提/账龄组合/客户类型组合/终止确认/不终止确认/已披露且准确/已披露但需修改/未披露需补充/组合评估/个别认定/Y/N/是/否/跨期/未跨期）内时 SHALL 返回 200；conclusion 值不在白名单内时 SHALL 返回 422。remark 字段接受任意文本不做限制。

**Validates: Requirements 13.1, 13.2, 13.4**

### Property 13: Tab 完成状态一致性

*For any* Tab 关联的 checklist_responses 数据子集，Tab 标签完成状态标记 SHALL 满足：无任何 conclusion/remark 数据→"not-started"（灰色）、存在部分数据但未全部完成→"in-progress"（蓝色点）、所有必填项均有值→"completed"（绿色勾）。状态判定必须实时反映底层数据变化。

**Validates: Requirements 2.6**
