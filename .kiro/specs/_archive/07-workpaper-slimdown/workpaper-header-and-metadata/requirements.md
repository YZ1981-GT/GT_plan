# Requirements: 底稿表头自动填充与业务分类裁剪

## Introduction

所有底稿模板前 4~5 行为统一表头（致同事务所/底稿名/客户名+编制人+日期+索引号/会计期间+复核人+日期+页次）。当前生成底稿时表头保持模板占位符（如"202X年"），需系统自动填充。同时，项目需区分业务分类(A/B/C)以驱动底稿裁剪和质控流程差异。

## Requirements

### Requirement 1: 底稿表头自动填充

**User Story:** 作为审计人员，我希望打开任何底稿时表头信息已自动填好（客户名、编制人、日期等），不需要每次手动填写重复信息。

#### Acceptance Criteria
1. WHEN 底稿生成时，THE 系统 SHALL 自动将表头占位符替换为项目实际数据（client_name→客户名称、audit_period→会计期间、wp_code→索引号）
2. WHEN 底稿分配给编制人后，THE 表头"编制人"字段 SHALL 自动填充为被分配人员姓名
3. WHEN 复核人完成复核时，THE 表头"复核人"+"复核日期"SHALL 自动更新
4. THE 表头区域（前5行）SHALL 设为只读，用户不可直接编辑（防止误改）
5. WHEN 项目信息变更（如客户名修改）时，THE 所有底稿表头 SHALL 同步更新
6. WHILE 项目为合并项目时，THE 子公司底稿表头"被审计单位名称"SHALL 填充对应子公司法人名称（非合并主体名）

### Requirement 2: 项目业务分类

**User Story:** 作为项目经理，我在创建项目时需要选择业务分类(A/B/C)，系统根据分类自动决定需要哪些底稿和质控流程。

#### Acceptance Criteria
1. WHEN 创建项目时，THE 系统 SHALL 提供业务分类选择（A类/B类/C类）
2. THE A类 SHALL 包含 A1~A8 共 8 个子分类（上市公司/IPO/重大资产重组等）
3. THE B类 SHALL 包含 B1~B6 共 6 个子分类（新三板/债券/特定行业等）
4. THE C类 SHALL 为一般审计业务（默认）
5. WHEN 用户选择分类时，THE 系统 SHALL 在旁边显示"查看分类标准"按钮，点击弹出只读参考表说明每类的定义和适用条件
6. THE 业务分类 SHALL 允许后续修改（但需项目合伙人确认）

### Requirement 3: 底稿裁剪确认

**User Story:** 作为项目经理，我希望在生成底稿前能确认哪些底稿适用于本项目，避免生成大量不适用的底稿浪费时间。

#### Acceptance Criteria
1. WHEN 用户点击"生成底稿"时，THE 系统 SHALL 先弹出裁剪确认界面
2. THE 裁剪界面 SHALL 按循环分组展示所有可生成底稿，每项可勾选"适用/不适用"
3. THE 系统 SHALL 根据业务分类(A/B/C)自动预选：C类自动取消 A 类专属底稿
4. THE 用户 SHALL 可以覆盖自动预选（如 C 类项目手动勾选某些 A 类底稿）
5. WHEN 用户确认后，THE 系统 SHALL 仅生成已勾选的底稿
6. THE 裁剪结果 SHALL 可后续修改（增删底稿）

### Requirement 4: A类专属底稿自动裁剪

**User Story:** 作为系统，我需要知道哪些底稿仅 A 类业务需要，C 类项目不应生成这些。

#### Acceptance Criteria
1. THE 以下底稿 SHALL 标记为 A 类专属：A1-12, A1-16, A17全系列, A18, A24, A25, A26, A27, A28
2. WHEN 项目为 C 类时，THE 裁剪预选 SHALL 自动取消上述底稿
3. WHEN 项目为 B 类时，THE 裁剪预选 SHALL 保留 A24/A25（质控复核仍需）但取消 A26（专委会）
4. THE A 类专属标记 SHALL 存储在底稿模板元数据中（可配置，非硬编码）
