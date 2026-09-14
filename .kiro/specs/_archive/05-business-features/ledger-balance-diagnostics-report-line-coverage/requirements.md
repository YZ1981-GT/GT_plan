# 需求文档：借贷不平衡诊断与报表行次覆盖治理

## 背景

当前导入作业诊断由 `validator.py` findings 与 `DiagnosticPanel.vue` 承载，试算表数据质量检查由 `DataQualityService` 与 `DataQualityDialog.vue` 承载，报表行次映射由 `report_line_mapping_service.py` 与 `ReportLineMappingDialog.vue` 承载。三者都与"借贷不平衡"有关，但口径和跳转入口分散。本 spec 负责统一诊断 DTO，并治理 `account_to_report_line_seed.json` 四套维度覆盖率。

## 需求

### 需求 1：统一借贷不平衡诊断 DTO

1. THE System SHALL 定义 `BalanceDiagnosticsResult`，统一承载差额、口径、原因清单、明细样本和跳转目标。
2. WHEN 导入 L2/L3 校验或试算表数据质量检查发现不平衡，THE System SHALL 复用同一诊断 DTO。
3. THE DTO SHALL 至少包含 `caliber`、`difference`、`debit_total`、`credit_total`、`likely_causes`、`unmatched_accounts`、`sign_anomalies`、`top_contributors`、`jump_targets`。
4. THE System SHALL 标明当前采用的 Trial_Balance_Caliber，不得混用"全科目借贷合计"和"资产=负债+权益"。
5. THE System SHALL 为每个 `caliber` 定义明确的数据来源和计算公式，不得由调用方自行解释。

### 需求 2：诊断原因分类

1. THE System SHALL 至少识别四类原因：报表行次未匹配、方向/符号异常、损益未结转或口径差异、源数据本身不平。
2. WHEN 存在未匹配科目，THE System SHALL 输出 `Unmatched_Account` 清单，包含科目编码、科目名称、金额、当前映射状态。
3. WHEN 存在方向/符号异常，THE System SHALL 输出来自 `sign_anomaly_flags` 的异常清单。
4. WHEN 序时账凭证借贷不平，THE System SHALL 输出差异最大的前 10 条凭证或科目。
5. WHEN 原因不足以自动判断，THE System SHALL 标记 `manual_review_required`，不得给出确定性结论。
6. WHEN `sign_anomaly_flags` 字段尚未上线或为空，THE System SHALL graceful degrade，继续输出其他原因并标记符号异常数据不可用，不得阻断诊断。
7. THE System SHALL 为每种 `caliber` 定义 `top_contributors` 来源：凭证、科目或报表行次。

### 需求 3：前端诊断弹窗与跳转

1. THE frontend SHALL 提供 `BalanceDiagnosticsDialog`，可被导入进度、导入诊断、试算表数据质量检查复用。
2. THE dialog SHALL 展示差额、平衡口径、原因清单、风险级别和可操作修复入口。
3. WHEN 原因为报表行次未匹配，THE dialog SHALL 跳转到 `ReportLineMappingDialog` 并定位到对应科目。
4. WHEN 原因为方向/符号异常，THE dialog SHALL 跳转到方向复核入口或异常列表。
5. THE dialog SHALL NOT 把报表行次映射问题跳转到导入列映射界面，二者不得混用。

### 需求 4：DataQualityService 口径统一

1. THE DataQualityService SHALL 使用统一 Trial_Balance_Caliber 计算借贷平衡。
2. THE DataQualityService SHALL 区分导入层四表借贷平衡、试算表余额平衡和报表资产负债表平衡。
3. WHEN 检查资产负债表平衡，THE System SHALL 明确该检查只适用于报表生成后的 BS 勾稽，不替代通用试算平衡。
4. THE DataQualityService SHALL 返回 `BalanceDiagnosticsResult` 或可转换为该 DTO 的 details。

### 需求 5：Account_To_Report_Line_Seed 覆盖治理

1. THE System SHALL 对 `account_to_report_line_seed.json` 的四套 Seed_Dimension 输出覆盖率报告。
2. THE coverage script SHALL 以平台标准科目全集为权威输入，校验每套维度均覆盖国企版与上市版报表模板需要取数的标准科目。
3. THE coverage script SHALL 输出未覆盖科目、重复映射、非法 `report_line_code`、非法 `report_type` 和国企/上市差异清单。
4. WHEN 一键预设科目映射执行，THE System SHALL 对项目有余额但 seed 查不到行次的科目输出 `Unmatched_Account`，不得静默跳过。
5. WHERE 国企版与上市版行次不同，THE seed SHALL 在对应维度分别体现，不得混用。
6. THE System SHALL 明确标准科目全集来源，优先使用平台标准 AccountChart seed / CAS 科目库；不得只从报表模板行次反推科目全集。
7. BEFORE coverage script 升级为 CI 阻断，THE System SHALL 先生成 baseline，区分历史缺口与本次新增缺口。

### 需求 6：报表行次映射修复闭环

1. THE Report_Line_Mapping UI SHALL 能接收诊断跳转参数并高亮未匹配科目。
2. WHEN 用户修复未匹配科目，THE System SHALL 支持重新运行诊断并更新原因清单。
3. WHEN seed 升级新增映射，THE System SHALL 支持刷新未确认的 ai_suggested 映射，但不得覆盖 manual / reference_copied 映射。
4. THE System SHALL 在诊断中区分 seed 缺失、项目映射未确认、项目手工映射错误三类情况。
5. THE DiagnosticJumpTarget SHALL 明确前端传参方式（route query、dialog prop 或事件 payload），避免跳转后无法定位目标科目。

## 范围边界

- 不负责表头识别和列映射契约，由 `ledger-import-header-adapter-contract` 承接。
- 不负责符号字段和历史迁移，由 `ledger-import-sign-convention-migration` 承接。
- 不重写整个报表生成引擎，只治理科目到报表行次映射和诊断入口。

## Properties / 验收不变量

1. **Property 1：口径唯一可解释**  
   每个不平衡诊断必须显示使用的平衡口径。
2. **Property 2：跳转不混淆**  
   报表行次映射问题只跳转 Report_Line_Mapping，不跳转导入列映射。
3. **Property 3：未匹配不静默**  
   有余额但没有行次映射的科目必须出现在 Unmatched_Account 清单。
4. **Property 4：seed 四维度独立**  
   soe/listed、standalone/consolidated 四套 seed 必须各自完整，不互相依赖。

## 依赖关系

- 消费 `ledger-import-sign-convention-migration` 提供的方向来源和 `sign_anomaly_flags`。
- 消费 `ledger-import-header-adapter-contract` 的导入 validation findings 与 diagnostics。
