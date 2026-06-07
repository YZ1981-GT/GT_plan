# 需求文档：账表导入表头识别与适配器契约

## 背景

本 spec 从 `ledger-import-smart-header-recognition` 总览需求中拆出表头识别、Adapter、人工列映射与历史映射复用。现有代码已经具备 `detector.py`、`identifier.py`、`AdapterRegistry`、`ColumnMappingService`、`DetectionPreview.vue` 和 `ColumnMappingEditor.vue`，本 spec 只做契约收口和增强，不重建导入框架。

## 需求

### 需求 1：Detector 表头识别增强

1. THE Detector SHALL 读取预览范围内的真实表头、原始表头、合并表头、组合表头和金额单位，并写入 `detection_evidence`。
2. WHEN 表头位于第 11 至 20 行，THE Detector SHALL 仍能定位真实表头，不得只扫描前 10 行后误判。
3. WHEN 表头为 2 至 3 层合并结构，THE Detector SHALL 输出稳定的单层列标识，并保留父子层级证据。
4. WHEN 表头为"期初/期末 × 借方/贷方"二维结构，THE Detector SHALL 输出可映射到 `opening_debit`、`opening_credit`、`closing_debit`、`closing_credit` 的列标识。
5. WHEN sheet 无法识别为四表之一，THE Detector SHALL 生成结构化 `skip_reason`，供前端解释为什么跳过。

### 需求 2：Adapter 选优与别名契约

1. THE System SHALL 明确 Adapter 口径：默认自动调用 `AdapterRegistry.detect_best(fd)` 选取最佳 Adapter；用户显式 `adapter_hint` 存在时优先使用该 Adapter。
2. WHEN 选中 Adapter，THE System SHALL 将 `adapter_id`、`adapter_score` 和匹配证据写入 `FileDetection` 或 sheet 级 `detection_evidence`。
3. THE Identifier SHALL 使用选中 Adapter 的 `get_column_aliases(table_type)` 作为 vendor 别名来源，并用 `GenericAdapter` 别名兜底。
4. THE System SHALL 保留现有 JSON recognition rules，但不得与 Adapter 别名产生两个互相覆盖的真源；冲突时应记录 evidence。
5. WHEN Adapter 匹配分数低于阈值，THE System SHALL 退回 `generic`，并标记需要人工确认的原因。
6. THE System SHALL 采用两阶段识别：先用 generic/global aliases 生成 provisional mappings，再执行 Adapter 选优，最后用选中 Adapter aliases 复识别，避免 Adapter 匹配依赖 `column_mappings`、`column_mappings` 又依赖 Adapter aliases 的循环。
7. WHEN Adapter 分数低但 sheet `table_type` 置信度高，THE System SHALL 保留表类型判断，但列映射进入人工确认，不得静默使用低分 Adapter aliases。

### 需求 3：JSON 驱动适配器加载

1. THE System SHALL 提供明确的 JSON adapter 加载入口，加载 `backend/data/ledger_adapters/*.json` 中非 `_` 前缀文件。
2. WHEN JSON adapter 文件格式非法、缺少 `id` 或 regex 无效，THE System SHALL 记录 warning 并跳过单个文件，不影响导入服务启动。
3. WHEN JSON adapter 与内置 Adapter 使用相同 `id`，THE System SHALL 按 `AdapterRegistry.register()` 的覆盖规则稳定替换，并记录来源。
4. THE System SHALL 提供测试覆盖 JSON adapter 的加载、覆盖、别名应用和非法文件跳过。

### 需求 4：人工列映射 DTO 统一

1. THE System SHALL 定义单一 `ConfirmedMappingDTO`，字段包含 `detection_id` 或稳定 `sheet_key`、`file_name`、`sheet_name`、`table_type`、`mapping_entries`、`aux_dimension_columns`、`file_fingerprint`、`software_fingerprint`。
2. THE frontend SHALL 提交 `ConfirmedMappingDTO`，不得继续混用 `file/sheet/column_mapping` 与 `file_name/sheet_name/mappings`。
3. THE backend SHALL 接收 `mapping_entries` 的规范格式，每条 entry 包含 `column_index`、`original_header`、`canonical_header`、`standard_field`；不得以普通 dict 的 header 字符串作为唯一 key。
4. WHEN `confirmed_mappings` 缺失、sheet key 不匹配或关键列缺失，THE backend SHALL 返回 blocking error，不得静默使用自动映射继续入库。
5. THE pipeline SHALL 只消费规范化后的 mapping entries，并按 `column_index` 从原始行取值；`canonical_header` 仅用于展示、raw_extra 追溯和诊断。
6. WHEN 原始文件存在重复表头（如多个"借方"、"贷方"、"金额"），THE System SHALL 生成稳定唯一的 `canonical_header`（如 `借方#3` 或 `期末余额.借方#7`），不得因 dict 覆盖丢列。

### 需求 5：低置信度与 unknown sheet 人工兜底

1. WHEN `confidence_level` 为 `low` 或 `manual_required`，THE System SHALL 要求人工确认后才能 submit。
2. WHEN sheet 被识别为 `unknown` 但用户手动选择 `balance` / `ledger` / `aux_balance` / `aux_ledger`，THE System SHALL 允许进入列映射，但必须要求关键列完整。
3. THE backend SHALL 独立校验人工确认状态，防止绕过前端直接调用 submit。
4. THE ColumnMappingEditor SHALL 展示关键列、推荐列、非关键列、样本值、历史映射来源和置信度。

### 需求 6：历史映射保存与复用

1. WHEN 用户确认或修正列映射，THE Column_Mapper SHALL 以 `file_fingerprint` 与 `software_fingerprint` 持久化 mapping，并形成 `override_parent_id` 历史链。
2. WHEN 后续上传命中 30 天内相同 `file_fingerprint`，THE System SHALL 自动预填历史映射，并标记 `auto_applied_from_history` 与 `history_mapping_id`。
3. WHEN 用户修改历史预填映射，THE System SHALL 保存新版本并指向被覆盖的父记录。
4. THE System SHALL 避免跨项目历史映射静默覆盖当前项目，跨项目复用必须有显式用户动作或明确策略。

## 范围边界

- 不改变 `converter.py` 的金额符号逻辑；该部分由 `ledger-import-sign-convention-migration` 承接。
- 不实现借贷不平衡诊断弹窗；该部分由 `ledger-balance-diagnostics-report-line-coverage` 承接。
- 不重写 parser / writer / dataset 激活流程。

## Properties / 验收不变量

1. **Property 1：人工确认不可绕过**  
   任一低置信度或关键列缺失 sheet，未确认时不得进入 pipeline 写库。
2. **Property 2：mapping 单一格式**  
   pipeline 收到的列映射必须总是 `mapping_entries[]`，并以 `column_index` 作为取值主键。
3. **Property 3：Adapter 证据可追溯**  
   每个识别结果都能解释使用了哪个 Adapter、分数是多少、命中了哪些证据。
4. **Property 4：Generic 可兜底**  
   任一未知软件格式都能落到 `generic`，但低置信度时必须人工确认。
5. **Property 5：重复表头不丢列**  
   即使多个原始列显示名相同，mapping 与 raw_extra 也必须按 `column_index` 保留每一列。

## 依赖关系

- 被 `ledger-import-sign-convention-migration` 消费列映射结果和表头二维结构识别结果。
- 被 `ledger-balance-diagnostics-report-line-coverage` 消费导入 diagnostics、skip_reason 和 validation findings。
