# Requirements Document

## Introduction

报表模块（Report Module）增强需求，目标是将当前 ~85% 完成度的报表模块推进到生产就绪状态。涵盖种子数据公式补全、路由注册修复、多标准覆盖验证、现金流量表自动调整规则扩展、以及报表 API 测试基础设施修复。

## Glossary

- **Report_Engine**: 报表生成引擎（`backend/app/services/report_engine.py`），负责根据 report_config 逐行执行公式生成四张报表
- **Report_Formula_Service**: 报表公式填充服务（`backend/app/services/report_formula_service.py`），负责幂等填充 report_config 表的 formula 字段
- **Report_Config_Seed**: 种子数据文件（`backend/data/report_config_seed.json`），包含 4 标准 × 4 报表类型的行次定义
- **CFS_Engine**: 现金流量表工作底稿引擎（`backend/app/services/cfs_worksheet_engine.py`），负责工作底稿法编制现金流量表
- **Router_Registry**: 路由注册中心（`backend/app/router_registry/*.py`），负责将所有 FastAPI router 注册到应用
- **Formula_DSL**: 报表公式领域特定语言，支持 TB('account_code','column')、SUM_TB('range','column')、ROW('row_code')、SUM_ROW('start','end') 等语法
- **Applicable_Standard**: 报表适用标准，取值为 soe_consolidated / soe_standalone / listed_consolidated / listed_standalone / enterprise
- **Auto_Adjustment_Rules**: CFS 自动调整规则（`AUTO_ADJUSTMENT_RULES` 列表），定义从试算表科目自动生成现金流量表调整分录的规则

## Requirements

### Requirement 1: 种子数据公式补全

**User Story:** As a 审计项目经理, I want report_config_seed.json 中所有适用行次都有正确的 Formula_DSL 公式, so that 报表生成时每行都能从试算表自动取数而非返回 0。

#### Acceptance Criteria

1. WHEN Report_Formula_Service 执行 fill_all_formulas 对 soe_consolidated 标准, THE Report_Formula_Service SHALL 使公式覆盖率达到 95% 以上（排除标题行和分类行）
2. WHEN Report_Formula_Service 执行 fill_all_formulas 对 soe_standalone 标准, THE Report_Formula_Service SHALL 使公式覆盖率达到 95% 以上（排除标题行和分类行）
3. WHEN Report_Formula_Service 执行 fill_all_formulas 对 listed_consolidated 标准, THE Report_Formula_Service SHALL 使公式覆盖率达到 95% 以上（排除标题行和分类行）
4. WHEN Report_Formula_Service 执行 fill_all_formulas 对 listed_standalone 标准, THE Report_Formula_Service SHALL 使公式覆盖率达到 95% 以上（排除标题行和分类行）
5. THE Report_Formula_Service SHALL 为资产负债表行次生成 TB('account_code','期末余额') 或 SUM_TB('range','期末余额') 格式的公式
6. THE Report_Formula_Service SHALL 为利润表行次生成 TB('account_code','本期发生额') 或 SUM_TB('range','本期发生额') 格式的公式
7. THE Report_Formula_Service SHALL 为合计行生成 ROW() 或 SUM_ROW() 引用子行的公式
8. WHEN Report_Config_Seed 中某行的 row_name 以冒号结尾（如"流动资产："）, THE Report_Formula_Service SHALL 将该行视为标题行并跳过公式填充
9. THE Report_Formula_Service SHALL 保持幂等性：已有 formula 的行不被覆盖

### Requirement 2: 审计日志路由注册修复

**User Story:** As a 审计合伙人, I want GET /api/audit-logs/verify-chain 端点可正常访问, so that 我可以校验审计日志哈希链的完整性。

#### Acceptance Criteria

1. WHEN 应用启动完成, THE Router_Registry SHALL 将 audit_logs router 注册到 FastAPI 应用
2. WHEN 已认证用户发送 GET /api/audit-logs/verify-chain 请求, THE Router_Registry SHALL 返回 200 状态码（而非 404）
3. THE Router_Registry SHALL 将 audit_logs router 注册在 system.py 中并标记 tags=["audit-logs"]
4. WHEN audit_logs router 注册后, THE Router_Registry SHALL 保持现有所有路由的正常工作不受影响

### Requirement 3: 多标准公式覆盖验证

**User Story:** As a 开发者, I want 一个验证脚本来检查 4 个标准的公式覆盖完整性, so that 我可以快速发现哪些行次缺少公式并定位问题。

#### Acceptance Criteria

1. THE Validation_Script SHALL 扫描 report_config 表中 4 个标准的所有行次并统计公式覆盖率
2. THE Validation_Script SHALL 输出每个标准每种报表类型的覆盖率百分比
3. THE Validation_Script SHALL 列出所有 formula 为 null 且非标题行的行次（row_code + row_name）
4. WHEN 某标准的覆盖率低于 95%, THE Validation_Script SHALL 以非零退出码退出并输出警告
5. THE Validation_Script SHALL 支持通过命令行参数指定单个标准或全部标准
6. FOR ALL 有效的 report_config 行次, 解析公式文本再格式化输出 SHALL 产生语法等价的公式字符串（round-trip property）

### Requirement 4: CFS 自动调整规则扩展

**User Story:** As a 审计项目经理, I want 现金流量表自动调整规则覆盖更多行业常见科目, so that 间接法补充资料的自动生成更加完整准确。

#### Acceptance Criteria

1. THE CFS_Engine SHALL 在 AUTO_ADJUSTMENT_RULES 中包含以下行业常见调整项：资产减值损失、处置固定资产损失、处置无形资产损失、固定资产报废损失、存货跌价准备、坏账准备
2. THE CFS_Engine SHALL 在 AUTO_ADJUSTMENT_RULES 中包含以下资产负债表变动项：存货的减少、经营性应收项目的减少、经营性应付项目的增加
3. THE CFS_Engine SHALL 在 AUTO_ADJUSTMENT_RULES 中包含递延所得税相关调整项：递延所得税资产减少、递延所得税负债增加
4. WHEN auto_generate_adjustments 执行时, THE CFS_Engine SHALL 从试算表中匹配科目编码并计算期初期末差额作为调整金额
5. THE CFS_Engine SHALL 为每条自动调整规则指定正确的 cash_flow_category 和 cf_row_code
6. WHEN 试算表中不存在某规则对应的科目, THE CFS_Engine SHALL 跳过该规则而非报错

### Requirement 5: 报表 API 测试基础设施修复

**User Story:** As a 开发者, I want 报表 API 测试能正确匹配生产路由路径, so that 测试结果能真实反映 API 的可用性。

#### Acceptance Criteria

1. THE Test_Infrastructure SHALL 确保测试中调用 GET /api/reports/{project_id}/{year}/{report_type} 路径与生产路由定义一致
2. WHEN 测试调用报表生成 API (POST /api/reports/generate), THE Test_Infrastructure SHALL 正确注入 get_current_user 和 get_db 依赖
3. THE Test_Infrastructure SHALL 使用 override_auth 模式统一注入认证依赖，避免 401 错误
4. WHEN 测试执行报表查询, THE Test_Infrastructure SHALL 预先通过 seed 数据或 generate 接口确保 report_config 表有数据
5. IF 测试因 prerequisite_checker 前置校验失败, THEN THE Test_Infrastructure SHALL 通过 mock 或 fixture 绕过前置检查

### Requirement 6: 报表公式 DSL 解析器健壮性

**User Story:** As a 开发者, I want 公式解析器能正确处理所有合法 DSL 语法和边界情况, so that 报表生成不会因公式解析错误而产生错误数据。

#### Acceptance Criteria

1. THE Report_Engine SHALL 正确解析嵌套算术表达式：TB('1601','期末余额')-TB('1602','期末余额')
2. THE Report_Engine SHALL 正确解析多项求和：TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')
3. THE Report_Engine SHALL 正确解析 SUM_TB 范围语法：SUM_TB('1400~1499','期末余额')
4. THE Report_Engine SHALL 正确解析 ROW 引用：ROW('BS-002')+ROW('BS-003')
5. THE Report_Engine SHALL 正确解析 SUM_ROW 范围引用：SUM_ROW('BS-002','BS-010')
6. WHEN 公式引用的科目在试算表中不存在, THE Report_Engine SHALL 返回 Decimal("0") 而非抛出异常
7. WHEN 公式为 null 或空字符串, THE Report_Engine SHALL 返回 Decimal("0")
8. WHEN 公式包含除零运算, THE Report_Engine SHALL 返回 Decimal("0") 而非抛出 ZeroDivisionError
9. FOR ALL 合法的 Formula_DSL 表达式, 解析后再序列化 SHALL 产生语义等价的表达式（round-trip property）

### Requirement 7: 报表生成跨标准一致性

**User Story:** As a 审计项目经理, I want 同一项目在不同标准下生成的报表行次结构保持一致, so that 切换标准时不会丢失关键财务数据行。

#### Acceptance Criteria

1. THE Report_Engine SHALL 确保 soe_consolidated 和 listed_consolidated 的资产负债表包含相同的核心行次（货币资金、应收账款、存货、固定资产等）
2. THE Report_Engine SHALL 确保 soe_standalone 和 listed_standalone 的利润表包含相同的核心行次（营业收入、营业成本、净利润等）
3. WHEN 从 soe_consolidated 切换到 listed_consolidated, THE Report_Engine SHALL 保留所有共有行次的计算结果
4. THE Report_Config_Seed SHALL 确保 4 个标准的 balance_sheet 行次数量差异不超过 20%
5. THE Report_Config_Seed SHALL 确保 4 个标准的 income_statement 行次数量差异不超过 20%
