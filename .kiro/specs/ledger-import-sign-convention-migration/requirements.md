# 需求文档：账表导入符号约定与历史迁移

## 背景

当前 `converter.py` 已支持借贷分列计算与显式方向调符号，但 `tb_balance` / `tb_aux_balance` 缺少方向来源、符号约定版本与异常复核字段，`TrialBalance.vue` 仍在展示层推断方向。本 spec 负责把"净额借方为正、贷方为负"落到导入、存储、迁移和展示全链路。

## 需求

### 需求 1：Sign_Convention 单一权威

1. THE System SHALL 采用单一 Sign_Convention："净额借方为正、贷方为负"。
2. THE System SHALL 在存储层保留带符号余额，展示层只负责按方向取绝对值展示，不回写存储。
3. THE System SHALL 为导入数据记录 `sign_convention_version`，用于区分历史数据与新约定数据。
4. THE System SHALL 在导入报告和数据质量检查中展示采用的符号约定。

### 需求 2：方向来源结构化落库

1. THE System SHALL 为 `tb_balance` / `tb_aux_balance` 增加期初、期末方向和来源字段。
2. THE System SHALL 至少支持方向来源：`explicit_direction`、`split_columns`、`account_category_inferred`、`user_override`、`legacy_inferred`。
3. WHEN 余额表使用借贷分列，THE Converter SHALL 按借方列减贷方列计算净额，并记录方向来源为 `split_columns`。
4. WHEN 余额表使用净额 + 方向列，THE Converter SHALL 按方向调整符号，并记录方向来源为 `explicit_direction`。
5. WHEN 仅有单一净额列且无方向列，THE Converter SHALL 依据 Account_Category 和 Contra_Asset 规则推断方向，并记录方向来源为 `account_category_inferred`。
6. WHEN 同一行借方列与贷方列同时非零，THE Converter SHALL 按净额符号确定方向，并记录 warning 供人工复核。
7. THE System SHALL 保持 `opening_debit`、`opening_credit`、`closing_debit`、`closing_credit` 等源分列字段为源文件绝对值；只有 `opening_balance` / `closing_balance` 等净额字段按 Sign_Convention 带符号。
8. WHEN Account_Category metadata 缺失但可按科目编码前缀低置信推断，THE System SHALL 标记 `account_category_inferred_low_confidence`，不得伪装成高置信来源。

### 需求 3：Converter 结果结构

1. THE Converter SHALL 返回结构化 `ConversionResult`，包含标准化 rows、aux rows、warnings、sign anomalies 和统计摘要。
2. THE pipeline SHALL 将 `ConversionResult.warnings` 纳入导入 validation findings 或 result summary。
3. THE writer SHALL 持久化方向字段、方向来源、符号约定版本和异常标记。
4. THE System SHALL 保持 converter 纯函数特性，不在 converter 内直接访问 DB。

### 需求 4：符号异常识别与人工复核

1. WHEN 科目余额方向与 Account_Category 正常方向冲突，THE System SHALL 记录 `sign_anomaly_flags`，不得静默改写为正常方向。
2. WHEN 负债、权益、收入类科目出现借方净额，THE System SHALL 将其列入符号异常清单。
3. WHEN 资产备抵科目出现借方净额，THE System SHALL 将其列入符号异常清单。
4. THE System SHALL 提供人工复核入口，允许用户确认异常为真实业务余额或修正方向。
5. WHEN 用户覆盖方向，THE System SHALL 持久化覆盖人、覆盖时间、覆盖原因和原始方向来源。

### 需求 5：历史数据 dry-run 与迁移

1. THE System SHALL 提供历史数据符号校正 dry-run，先输出受影响项目、科目、原金额、建议金额、原因和风险等级。
2. THE System SHALL 在 dry-run 未通过人工确认前，不得批量改写存量 `tb_balance`。
3. THE System SHALL 提供幂等迁移脚本，所有 `CREATE` / `ALTER` 使用 `IF NOT EXISTS`。
4. WHEN 存量数据已符合新约定，THE 迁移 SHALL 重复执行不改变金额。
5. WHEN 存量数据存在方向冲突，THE 迁移 SHALL 记录待复核项，不静默改写。
6. THE dry-run SHALL 输出迁移安全等级：`safe_auto_fix`、`manual_review_required`、`no_change`。
7. WHEN 存量数据有显式方向列或借贷分列证据且当前存储符号与证据矛盾，THE 迁移 MAY 标记为 `safe_auto_fix`。
8. WHEN 仅能依据 Account_Category 推断方向，THE 迁移 SHALL 标记为 `manual_review_required`，不得自动改写金额。
9. WHEN 余额反向可能是真实业务余额（如负债借方余额、税费留抵、收入冲回），THE 迁移 SHALL 标记为 `no_change` 或 `manual_review_required`，不得按正常方向强制改写。

### 需求 6：试算表展示去补救化

1. WHEN Trial_Balance_View 渲染方向，THE frontend SHALL 优先使用后端返回的权威方向和方向来源。
2. WHEN 方向来源为 `legacy_inferred` 或 `account_category_inferred`，THE frontend SHALL 显示可追溯标记。
3. WHEN 用户手动覆盖方向，THE frontend SHALL 调用后端接口持久化覆盖，不得只写入本地 `directionOverrides`。
4. WHEN 历史数据尚未迁移，THE frontend MAY 回退类别推断，但必须标记为"推断方向"。
5. THE frontend SHALL 不再把金额正负作为普通科目的第一方向来源。
6. THE System SHALL 优先以独立方向覆盖表或 overlay 记录用户覆盖，不直接改写原始导入行，保留导入事实与用户判断的审计追溯边界。

### 需求 7：回归与兼容

1. THE System SHALL 保证新导入余额表、辅助余额表、序时账、辅助序时账仍能完成四表入库。
2. THE System SHALL 保证已有未迁移项目可继续打开试算表，但必须显示方向来源风险。
3. THE System SHALL 提供测试覆盖借贷分列、净额方向列、单一净额列、反常方向和资产备抵科目。

## 范围边界

- 不负责 Adapter / 表头识别契约，该部分由 `ledger-import-header-adapter-contract` 承接。
- 不负责借贷不平衡诊断弹窗聚合，该部分由 `ledger-balance-diagnostics-report-line-coverage` 承接。
- 不改变报表行次 mapping seed 的业务口径。

## Properties / 验收不变量

1. **Property 1：存储带符号**  
   贷方净额在存储层必须为负数，不得为了展示改成正数。
2. **Property 2：来源可追溯**  
   每个余额方向必须能解释来自显式方向、借贷分列、类别推断、用户覆盖或历史推断。
3. **Property 3：异常不静默**  
   与正常方向冲突的科目不得被静默改写，必须进入 warning / 复核清单。
4. **Property 4：迁移可 dry-run**  
   任何存量金额改写前必须能预览影响清单。
5. **Property 5：原始事实不可被覆盖抹除**  
   用户方向覆盖和历史迁移建议必须保留原始导入金额、原始方向证据和覆盖原因。

## 依赖关系

- 依赖 `ledger-import-header-adapter-contract` 输出稳定的列映射和二维借贷表头识别。
- 向 `ledger-balance-diagnostics-report-line-coverage` 提供 `sign_anomaly_flags` 和方向来源。
