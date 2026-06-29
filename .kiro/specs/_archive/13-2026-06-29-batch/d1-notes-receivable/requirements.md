# Requirements Document

## Introduction

D1 应收票据审定表是"销售与收款循环"（D 循环）实质性底稿，属于 CAS 1301 审计证据/CAS 1501 金融工具审计范畴。源模板包含 21 个 sheet（底稿目录 + 程序表 D1A + 审定表 D1-1 + 附注 ×2 + 检查表 ×16 + 分析提示），覆盖票据原值、坏账准备、业务模式分析、背书贴现、质押、监盘、贴息等全流程审计程序。

当前实现使用通用 `d-form-table`/`audit-sheet` 渲染，缺乏应收票据专属交互（审定表联动、到期分析、ECL 自动计算、业务模式 SPPI 判断、背书贴现终止确认）。本 spec 定义一个专属 `d1-notes-receivable` HTML 组件，将 21 sheet 聚合为统一 Tab 入口，提供：
- 审定表（D1-1）：未审数/调整数/审定数计算 + trial_balance 回写
- 程序表（D1A）：8 步审计程序执行状态 + 结论
- 原值明细表（D1-2/D1-3）：audit-sheet 子底稿 lazy 嵌入
- 坏账准备（D1-4/D1-14/D1-15/D1-16）：ECL 模型 + 迁徙率 + 转回核销
- 票据专属程序（D1-6~D1-13）：业务模式分析、背书贴现、质押、监盘、贴息、关联方

核心价值：
- 21 sheet 统一入口，消除多底稿切换
- 审定表公式自动计算（跨 sheet 引用 D1-2/D1-4 数据）
- trial_balance 双向联动：audited_amount 实时回写
- B50 风险评估→程序表步骤范围联动
- C 类控制测试结论→D1 实质性程序范围调整

## Glossary

- **D1_Component**: D1 应收票据专属 Vue 组件（componentType = `d1-notes-receivable`）
- **Adjudication_Table**: 审定表 D1-1，汇总未审数/调整数/审定数，回写 trial_balance
- **Procedure_Table**: 审计程序表 D1A，8 步实质性程序执行记录
- **Detail_Sheet_Category**: 原值明细表（按类别）D1-2，audit-sheet 子底稿
- **Detail_Sheet_Customer**: 原值明细表（按客户）D1-3，audit-sheet 子底稿
- **Bad_Debt_Sheet**: 坏账准备明细表 D1-4，组合/个别认定预期信用损失
- **Adjustment_Summary**: 调整分录汇总表 D1-5
- **Business_Model_Analysis**: 应收票据业务模式分析 D1-6（SPPI 测试 + 业务模式分类）
- **Ledger_Reconciliation**: 应收票据备查簿核对 D1-7
- **Endorsement_Discount**: 应收票据贴现、票据已背书未到期明细表 D1-8（终止确认/不终止确认）
- **Interest_Check**: 应收票据贴息检查表 D1-9
- **Inventory_Check**: 应收票据监盘 D1-10（盘点日→资产负债表日倒推）
- **Related_Party**: 关联方关系及交易检查表 D1-11
- **Pledge_Check**: 应收票据质押检查表 D1-12
- **General_Check**: 应收票据检查表 D1-13
- **ECL_Policy_Check**: 应收票据坏账准备会计政策检查 D1-14
- **ECL_Test_Sheet**: 应收票据坏账准备测试表 D1-15（迁徙率法 / ECL 模型）
- **WriteOff_Reversal**: 坏账准备转回、核销检查表 D1-16
- **Disclosure_Listed**: 附注披露信息（上市公司）
- **Disclosure_SOE**: 附注披露信息（国企）
- **trial_balance**: 试算平衡表，audited_amount 为审定数权威字段
- **ECL_Model**: 预期信用损失模型（Expected Credit Loss），IFRS 9 / CAS 22 三阶段减值
- **SPPI_Test**: 合同现金流量特征测试（Solely Payments of Principal and Interest）
- **Maturity_Analysis**: 到期分析，按到期日分组（未到期/逾期 30 天内/逾期 31-90 天/逾期 90 天以上）
- **Derecognition**: 终止确认判断，票据背书/贴现是否满足终止确认条件
- **Migration_Rate**: 迁徙率法，通过历史损失数据推算各账龄段的迁徙概率
- **checklist_responses**: 数据持久化表，通过 item_id 前缀 `D1-` 区分字段
- **htmlRendererRegistry**: 前端 componentType → Vue 组件的单一来源注册表
- **EventBus**: 进程内事件总线，D1 发布 `substantive:adjudicated` 事件
- **GtWpRenderer**: 子底稿懒加载渲染器，用于 Tab 内嵌 audit-sheet 子底稿
- **displayPrefs**: 金额/百分比/日期统一格式化出口

## Requirements

### Requirement 1: 组件注册与路由

**User Story:** As a 开发者, I want 新组件正确注册到 htmlRendererRegistry 并通过 wp_code_overrides 路由, so that 打开 D1 底稿时自动渲染专属组件。

#### Acceptance Criteria

1. THE D1_Component SHALL 在 htmlRendererRegistry 中注册 componentType 为 `d1-notes-receivable`，contextProps 为 `standard`
2. THE D1_Component SHALL 在 wp_code_overrides.json 中将 `D1` 映射为 `d1-notes-receivable`（替换现有 `d-form-table`）
3. THE D1_Component SHALL 在 wp_code_overrides.json 中将 `D1-1` 映射为 `skip`（由 D1 统一渲染审定表）
4. THE D1_Component SHALL 在 wp_code_overrides.json 中保留 `D1-2` 和 `D1-3` 为 `audit-sheet`（作为子底稿 lazy 嵌入 Tab）
5. THE D1_Component SHALL 在 wp_code_overrides.json 中将 `D1-4` 映射为 `skip`（由 D1 统一渲染坏账准备）
6. THE D1_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly
7. THE D1_Component SHALL emit `save` 事件（保存成功后）和 `completed` 事件（复核完成时）
8. WHEN 后端 render-config 返回 componentType 为 `d1-notes-receivable` 时, THE 前端路由 SHALL 正确加载 D1_Component

### Requirement 2: 21 Sheet Tab 统一入口

**User Story:** As a 审计助理, I want 在一个界面通过 Tab 页签访问所有 21 个 sheet, so that 无需在多个底稿间切换即可完成应收票据全流程审计。

#### Acceptance Criteria

1. THE D1_Component SHALL 渲染顶部 Tab 页签栏，包含以下分组 Tab：底稿目录、程序表(D1A)、审定表(D1-1)、附注披露、原值明细(D1-2/D1-3)、坏账准备(D1-4)、调整分录(D1-5)、业务模式(D1-6)、备查簿核对(D1-7)、背书贴现(D1-8)、贴息(D1-9)、监盘(D1-10)、关联方(D1-11)、质押(D1-12)、检查表(D1-13)、ECL政策(D1-14)、ECL测试(D1-15)、转回核销(D1-16)
2. THE D1_Component SHALL 将附注披露 Tab 内部提供子切换：上市公司/国企（根据项目类型默认选中）
3. THE D1_Component SHALL 对子底稿 D1-2 和 D1-3 的 Tab 使用 GtWpRenderer 懒加载渲染（audit-sheet 模式）
4. THE D1_Component SHALL 对 D1-5 至 D1-16 的 Tab 内容使用 d-form-table 模式内嵌渲染
5. THE D1_Component SHALL 记住用户最后访问的 Tab（localStorage 持久化），下次进入时恢复
6. THE D1_Component SHALL 在 Tab 标签上显示完成状态标记（已完成=绿色勾、进行中=蓝色点、未开始=灰色）
7. WHEN Tab 切换时, THE D1_Component SHALL 懒加载目标 Tab 内容（首次访问时加载，之后缓存）

### Requirement 3: 审定表（D1-1）联动计算

**User Story:** As a 审计助理, I want 审定表自动从明细表取数并计算审定数, so that 减少手工抄数错误并确保审定表与明细表一致。

#### Acceptance Criteria

1. THE Adjudication_Table SHALL 渲染审定表结构：行=科目项（应收票据-银行承兑汇票/商业承兑汇票/坏账准备/账面价值），列=期初未审数(B)/期末未审数(C)/本期变动(D)/审计调整(E~H)/审定数(I)/变动率(K)
2. THE Adjudication_Table SHALL 从 Detail_Sheet_Category（D1-2）自动引用原值数据：B8←D1-2!B14、C8←D1-2!C14、D8←D1-2!D14（银行承兑汇票行）
3. THE Adjudication_Table SHALL 从 Detail_Sheet_Category（D1-2）自动引用原值数据：B9←D1-2!B13、C9←D1-2!C13、D9←D1-2!D13（商业承兑汇票行）
4. THE Adjudication_Table SHALL 从 Bad_Debt_Sheet（D1-4）自动引用坏账数据：B12←D1-4!B23、C12←D1-4!C23
5. THE Adjudication_Table SHALL 自动计算审定数：审定数 = 未审数 + AJE调整 + RJE重分类
6. THE Adjudication_Table SHALL 自动计算变动率：K列 = IF(期初=0 AND 审定数=0, "", IF(期初=0 AND 审定数>0, 1, (审定数-期初)/期初))
7. WHEN 审定数计算完成后, THE D1_Component SHALL 通过 API 回写 trial_balance 对应科目的 audited_amount
8. THE Adjudication_Table SHALL 使用 displayPrefs.fmtAmount 格式化所有金额单元格
9. WHEN D1-2 或 D1-4 的明细数据变更时, THE Adjudication_Table SHALL 实时重新计算引用值

### Requirement 4: 审计程序表（D1A）执行管理

**User Story:** As a 审计助理, I want 在程序表中逐步记录 8 个审计步骤的执行情况, so that 追踪审计程序完成进度并形成结论。

#### Acceptance Criteria

1. THE Procedure_Table SHALL 渲染 8 步审计程序列表：获取明细/核对总账/票据验真/到期分析/背书贴现/减值评估/披露检查/结论
2. THE Procedure_Table SHALL 每步包含字段：步骤名称、描述、执行状态（未开始/执行中/已完成/不适用）、执行人、执行日期、工作底稿索引、审计发现、结论
3. THE Procedure_Table SHALL 支持"不适用"标记（适用性自动判断：当科目余额为 0 时提示可标记不适用）
4. WHEN 某步骤标记"已完成"时, THE Procedure_Table SHALL 要求填写结论（不可为空）
5. THE Procedure_Table SHALL 在顶部显示完成进度：N/8 步骤已完成
6. WHEN 全部必要步骤完成时, THE Procedure_Table SHALL 允许录入整体审计结论
7. THE Procedure_Table SHALL 在每步骤右侧提供 ref_chip 跳转到对应 Tab（如"到期分析"→D1-6 Tab）
8. WHEN B50 风险评估发布销售与收款循环重大风险时, THE Procedure_Table SHALL 在相关步骤旁显示风险标识

### Requirement 5: 坏账准备与 ECL 计算

**User Story:** As a 审计助理, I want 系统辅助计算预期信用损失并与被审计单位计提金额比对, so that 快速识别坏账准备计提是否充分。

#### Acceptance Criteria

1. THE Bad_Debt_Sheet SHALL 渲染坏账准备明细表结构：行=账龄段（未逾期/逾期1-30天/逾期31-90天/逾期91-180天/逾期181-365天/逾期1年以上），列=期初余额/本期计提/本期转回/本期核销/期末余额/预期损失率/应计提金额/差异
2. THE D1_Component SHALL 支持两种 ECL 计算方法切换：组合评估（迁徙率法）/ 个别认定
3. WHEN 选择迁徙率法时, THE ECL_Test_Sheet SHALL 提供迁徙率矩阵输入（各账龄段历史迁徙概率），自动计算预期损失率
4. THE D1_Component SHALL 自动计算各账龄段应计提金额：应计提 = 余额 × 预期损失率
5. THE D1_Component SHALL 自动计算差异：差异 = 被审计单位实际计提 - 审计师测算应计提
6. WHEN 差异绝对值超过 B15 重要性水平时, THE D1_Component SHALL 高亮显示差异行并提示"差异超过重要性水平，建议提出调整"
7. THE Bad_Debt_Sheet SHALL 汇总行数据自动回传 Adjudication_Table（D1-1 坏账准备行）
8. THE ECL_Policy_Check SHALL 提供会计政策一致性检查清单（是否变更/变更原因/影响金额）

### Requirement 6: 票据到期分析与业务模式

**User Story:** As a 审计助理, I want 系统自动按到期日分组分析票据并进行业务模式判断, so that 评估票据分类和减值是否恰当。

#### Acceptance Criteria

1. THE Business_Model_Analysis SHALL 渲染 Maturity_Analysis 区域：将票据按到期日分为未到期/逾期30天内/逾期31-90天/逾期90天以上四组，显示各组金额和占比
2. THE Business_Model_Analysis SHALL 提供 SPPI_Test 检查清单：合同现金流量是否仅为本金和利息（Y/N + 说明）
3. THE Business_Model_Analysis SHALL 提供业务模式分类选择：以收取合同现金流量为目标 / 既以收取合同现金流量又以出售为目标 / 以出售为目标
4. WHEN 业务模式为"以收取合同现金流量为目标"且 SPPI 通过时, THE Business_Model_Analysis SHALL 建议分类为"以摊余成本计量"
5. WHEN 存在逾期90天以上票据时, THE Business_Model_Analysis SHALL 在 Maturity_Analysis 区域显示红色警告"存在重大逾期票据，需关注减值"
6. THE Business_Model_Analysis SHALL 提供分析提示参考面板（渲染 D1 模板最后一个 sheet "应收票据业务模式分析提示"的指导内容）
7. WHEN Maturity_Analysis 数据变更时, THE D1_Component SHALL 联动更新坏账准备各账龄段余额

### Requirement 7: 背书贴现与终止确认

**User Story:** As a 审计助理, I want 记录票据背书贴现情况并判断终止确认条件, so that 验证表外事项会计处理是否正确。

#### Acceptance Criteria

1. THE Endorsement_Discount SHALL 渲染背书贴现明细表：行=各笔已背书/已贴现票据，列=票据编号/出票人/金额/到期日/背书日期/受让人/是否终止确认/备注
2. THE Endorsement_Discount SHALL 提供终止确认判断辅助：是否转移了金融资产所有权上几乎所有风险和报酬（Y/N）
3. WHEN 标记"不终止确认"时, THE Endorsement_Discount SHALL 在对应行显示"应作为表外事项披露"提示
4. THE Endorsement_Discount SHALL 自动汇总：已背书未到期金额合计、已贴现未到期金额合计、终止确认金额、不终止确认金额
5. THE Interest_Check SHALL 渲染贴息检查表：贴现金额/贴现率/贴现天数/贴息金额/审计师复核金额/差异
6. THE Interest_Check SHALL 自动计算贴息：贴息 = 贴现金额 × 贴现率 × 贴现天数 / 360
7. WHEN 贴息差异超过允许范围时, THE Interest_Check SHALL 高亮差异并提示核实

### Requirement 8: 票据监盘与质押

**User Story:** As a 审计助理, I want 记录票据监盘结果并检查质押情况, so that 验证票据实物存在和使用受限情况。

#### Acceptance Criteria

1. THE Inventory_Check SHALL 渲染监盘表：盘点日期/盘点地点/票据清单（编号/金额/到期日/实物状态）/盘点结论
2. THE Inventory_Check SHALL 支持"盘点日→资产负债表日"倒推逻辑：记录盘点日余额 + 期间增减 = 资产负债表日余额
3. WHEN 倒推结果与账面余额不一致时, THE Inventory_Check SHALL 显示差异金额并标红
4. THE Pledge_Check SHALL 渲染质押清单：票据编号/金额/质押对象/质押用途/解质押日期/是否限制性资产
5. THE Pledge_Check SHALL 自动汇总已质押金额占应收票据总额的比例
6. WHEN 质押比例超过 50% 时, THE Pledge_Check SHALL 显示黄色警告"大额质押，需关注流动性和披露"
7. THE D1_Component SHALL 在审定表区域标注已质押金额（供附注披露引用）

### Requirement 9: 关联方检查与通用检查表

**User Story:** As a 审计助理, I want 检查应收票据涉及的关联方交易和通用审计事项, so that 识别关联方舞弊风险和其他异常。

#### Acceptance Criteria

1. THE Related_Party SHALL 渲染关联方交易检查表：关联方名称/关系类型/交易金额/票据编号/是否正常商业条款/备注
2. THE Related_Party SHALL 提供关联方识别辅助：从项目已录入关联方清单（B 循环数据）自动匹配票据出票人/承兑人
3. WHEN 存在关联方票据且金额超过重要性水平时, THE Related_Party SHALL 显示红色警告"重大关联方票据交易，需充分披露"
4. THE General_Check SHALL 渲染通用检查表：包含票据真实性验证、票面要素完整性、背书连续性、承兑人信用评级等检查项
5. THE General_Check SHALL 每项检查提供结论选择：符合/不符合/不适用 + 备注
6. THE D1_Component SHALL 在关联方检查和通用检查完成后，将发现汇总到程序表对应步骤的"审计发现"字段

### Requirement 10: 跨底稿联动（trial_balance + B50 + C + A13）

**User Story:** As a 现场经理, I want D1 审定结果自动联动试算表和其他底稿, so that 审计链路数据一致无需手工同步。

#### Acceptance Criteria

1. WHEN Adjudication_Table 审定数变更时, THE D1_Component SHALL 通过 EventBus 发布 `substantive:adjudicated` 事件（含 wpCode="D1"、科目编码、audited_amount）
2. THE D1_Component SHALL 通过 API 将审定数回写 trial_balance 对应应收票据科目的 audited_amount 字段
3. THE D1_Component SHALL 监听 B50 风险评估的 `risk:assessed` 事件，接收销售与收款循环风险等级，在程序表步骤旁显示风险标识
4. THE D1_Component SHALL 监听 C 类控制测试的 `control:test-concluded` 事件（C2 对应销售与收款循环），WHEN 控制有效时在程序表显示"控制有效，可适当减少样本量"
5. WHEN 审计调整分录（AJE/RJE）录入审定表时, THE D1_Component SHALL 通过 EventBus 发布 `adjustment:created` 事件供 A13 错报汇总表接收
6. THE D1_Component SHALL 在联动面板提供 ref_chip 跳转：→ trial_balance、→ B50 风险评估、→ C2 控制测试、→ A13 错报汇总
7. THE D1_Component SHALL 在组件初始化时从 trial_balance 获取应收票据科目的 unadjusted_amount 作为审定表未审数初始值

### Requirement 11: 数据持久化

**User Story:** As a 审计助理, I want 所有审计数据自动保存, so that 不会因意外关闭而丢失工作。

#### Acceptance Criteria

1. THE D1_Component SHALL 将程序表/审定表/检查表数据存储到 checklist_responses 表，使用 item_id 前缀 `D1-` 区分字段
2. WHEN 用户编辑文本字段后停止输入 2 秒时, THE D1_Component SHALL 自动保存变更（debounce 2000ms）
3. WHEN 用户变更结论/状态/选择类字段时, THE D1_Component SHALL 立即保存（不等待 debounce）
4. WHEN 保存失败时, THE D1_Component SHALL 显示错误提示并保留本地编辑内容（不回滚）
5. THE D1_Component SHALL 通过 `PUT /api/workpapers/{wp_id}/checklist-responses` 接口批量保存
6. THE D1_Component SHALL 通过 `GET /api/workpapers/{wp_id}/checklist-responses` 加载已保存数据并还原全部 Tab 状态
7. THE D1_Component SHALL 使用结构化 item_id 命名规则：`D1-{sheet}-{field}`（如 `D1-proc-1-status`、`D1-adj-row8-aje`、`D1-ecl-aging1-rate`、`D1-endorse-1-derecog`、`D1-pledge-1-amount`）

### Requirement 12: 复核签字与只读

**User Story:** As a 现场经理, I want 审计程序全部完成后签字复核并锁定, so that 确保底稿结论经审核后不被随意修改。

#### Acceptance Criteria

1. THE D1_Component SHALL 在程序表区域下方提供"现场经理复核"签字区域
2. WHEN 程序表存在未完成的必要步骤时, THE D1_Component SHALL 禁用复核签字按钮并显示待完成事项清单
3. WHEN 现场经理完成签字时, THE D1_Component SHALL 将全组件（所有 Tab）转为只读模式并 emit `completed`
4. WHILE 处于已复核只读模式时, THE D1_Component SHALL 在顶部显示"已复核"绿色横幅和复核人/日期
5. WHEN 外部传入 readonly prop 为 true 时, THE D1_Component SHALL 强制进入只读模式
6. THE D1_Component SHALL 支持 Amendment 模式：填写修改原因后解锁编辑，完成后需重新复核

### Requirement 13: 后端白名单扩展

**User Story:** As a 开发者, I want 后端支持 D1- 前缀的结论值保存, so that 前端发送的应收票据审计数据能正常持久化。

#### Acceptance Criteria

1. THE 后端 checklist_responses 保存逻辑 SHALL 在结论白名单中支持 `D1-` 前缀的 item_id
2. THE 后端 SHALL 接受 D1- 前缀 item_id 的以下结论值：未开始、执行中、已完成、不适用、符合、不符合、是、否、以摊余成本计量、以公允价值计量且变动计入其他综合收益、以公允价值计量且变动计入当期损益、终止确认、不终止确认、控制有效运行、组合评估、个别认定、Y、N
3. THE 后端 SHALL 对 D1- 前缀 item_id 的保存请求执行与现有 D0-/C{n}- 前缀相同的权限校验
4. IF 前端发送无效的 D1- 前缀结论值, THEN THE 后端 SHALL 返回 422 校验错误并拒绝保存

### Requirement 14: 附注披露检查

**User Story:** As a 审计助理, I want 对照披露要求逐项检查应收票据附注, so that 确保财务报表附注披露完整准确。

#### Acceptance Criteria

1. THE Disclosure_Listed SHALL 渲染上市公司附注披露检查清单：应收票据分类及账面价值/坏账准备变动/已质押票据/已背书未到期/已贴现未到期/前五名出票人/关联方票据/会计政策说明
2. THE Disclosure_SOE SHALL 渲染国企附注披露检查清单：按国资委报表附注格式要求列示检查项
3. THE D1_Component SHALL 根据项目属性（上市公司/国企/一般企业）自动选择默认披露模板
4. THE 披露检查清单 SHALL 每项提供结论选择：已披露且准确/已披露但需修改/未披露需补充/不适用 + 备注
5. WHEN 存在"未披露需补充"项时, THE D1_Component SHALL 在程序表"披露检查"步骤旁显示红色提醒
6. THE 披露检查结论 SHALL 汇总到程序表第 7 步"披露检查"的审计发现字段

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

*For any* 审定表行的未审数(B)、AJE调整(E/F)、RJE调整(G/H)值组合，审定数(I) SHALL 始终等于 B + E - F + G - H（借方增贷方减）。变动率(K) SHALL 满足：期初=0且审定数=0→空、期初=0且审定数>0→1、其他→(审定数-期初)/期初。

**Validates: Requirements 3.5, 3.6**

### Property 2: 跨 sheet 引用一致性

*For any* D1-2（原值明细表按类别）的 B14/C14/D14/B13/C13/D13 单元格值变更，审定表 D1-1 对应行（B8/C8/D8/B9/C9/D9）SHALL 实时同步更新。D1-4（坏账准备）的 B23/C23 变更时，审定表 B12/C12 SHALL 同步更新。引用值与源值始终相等。

**Validates: Requirements 3.2, 3.3, 3.4, 3.9**

### Property 3: ECL 计算正确性

*For any* 账龄段余额和预期损失率组合，应计提金额 SHALL 等于余额 × 损失率。差异 SHALL 等于实际计提 - 应计提。迁徙率法：最终损失率 = 各阶段迁徙率连乘。所有金额 ≥ 0，损失率 ∈ [0, 1]。

**Validates: Requirements 5.3, 5.4, 5.5**

### Property 4: 贴息计算正确性

*For any* 贴现金额(P)、贴现率(R)、贴现天数(D)组合，贴息 SHALL 等于 P × R × D / 360。差异 SHALL 等于被审计单位贴息 - 审计师复核贴息。P ≥ 0，R ∈ [0, 1]，D ≥ 0。

**Validates: Requirements 7.6**

### Property 5: 监盘倒推一致性

*For any* 盘点日余额(A)、期间增加(B)、期间减少(C)，资产负债表日余额 SHALL 等于 A + B - C。差异 = 账面余额 - 倒推余额。倒推逻辑满足：A ≥ 0, B ≥ 0, C ≥ 0。

**Validates: Requirements 8.2, 8.3**

### Property 6: trial_balance 回写一致性

*For any* 审定表审定数变更，回写到 trial_balance 的 audited_amount SHALL 等于审定表最终计算的审定数。回写科目编码 SHALL 与项目 trial_balance 中应收票据科目的 standard_account_code 匹配。

**Validates: Requirements 10.1, 10.2, 10.7**

### Property 7: 数据持久化往返一致性

*For any* 有效的 D1 审计数据（程序表状态 + 审定表数值 + 检查表结论 + 样本明细），通过 PUT 保存后再通过 GET 加载，所有字段值 SHALL 与保存前一致（round-trip property）。

**Validates: Requirements 11.1, 11.5, 11.6**

### Property 8: item_id 命名唯一性

*For any* 组合（sheet标识 × 行号/字段类型），生成的 item_id SHALL 唯一。不同业务含义的数据不可产生相同 item_id。同一 item_id 重复保存应覆盖而非新增。

**Validates: Requirements 11.7**

### Property 9: 程序表完成度与复核前置条件

*For any* 程序表步骤状态组合，复核签字按钮可用当且仅当：所有 is_required=true 的步骤状态为"已完成"或"不适用"。条件不满足时按钮必须禁用。

**Validates: Requirements 12.2**

### Property 10: EventBus 事件发射正确性

*For any* 审定数变更操作，WHEN 审定数实际变更（新旧值不同）时 SHALL 发布 `substantive:adjudicated` 事件。WHEN 审定数未变更时 SHALL 不发布事件。事件载荷中 audited_amount SHALL 等于审定表最终计算值。

**Validates: Requirements 10.1, 10.5**

### Property 11: 调整分录与审定表双向同步

*For any* 调整分录的增/删/改操作，Adjudication_Table 对应行的 AJE/RJE 调整列 SHALL 始终等于 Adjustment_Summary 中同类型分录金额之和。新增分录增加审定表调整数，删除分录减少审定表调整数。

**Validates: Requirements 15.3, 15.5**

### Property 12: 后端白名单校验正确性

*For any* item_id 以 `D1-` 开头的保存请求，conclusion 值在白名单内时 SHALL 返回 200；conclusion 值不在白名单内时 SHALL 返回 422。remark 字段接受任意文本。

**Validates: Requirements 13.1, 13.2, 13.4**

### Property 13: Tab 完成状态一致性

*For any* Tab 内容的数据变更，Tab 标签上的完成状态标记 SHALL 实时反映实际状态：所有必填项已填且有结论→已完成(绿色勾)、存在已填项但未全部完成→进行中(蓝色点)、无任何数据→未开始(灰色)。

**Validates: Requirements 2.6**
