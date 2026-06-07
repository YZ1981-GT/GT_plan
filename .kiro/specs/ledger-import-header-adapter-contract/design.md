# 设计文档：账表导入表头识别与适配器契约

## 概述

本设计在现有 `backend/app/services/ledger_import/` 管线中收口识别阶段契约。核心目标是让 detect 阶段产出可追溯、可人工修正、可复用的列映射结果，并确保 submit / pipeline 消费的 mapping 格式唯一。

## 核心设计

### 1. 识别阶段数据流

```text
UploadStep
  -> POST /ledger-import/detect
  -> detect_file_from_path
  -> identify(sheet, generic/global aliases)  # provisional
  -> AdapterRegistry.detect_best(fd)
  -> identify(sheet, selected_adapter_aliases + generic aliases)  # final
  -> apply_history_reuse
  -> LedgerDetectionResult
  -> DetectionPreview / ColumnMappingEditor
```

`adapter_hint` 存在时跳过自动选优，直接使用指定 Adapter；否则按 `AdapterRegistry.detect_best(fd)` 选取最高分 Adapter。`generic` 始终兜底。

两阶段识别是强制约束：`JsonDrivenAdapter.match()` 可能依赖 provisional `column_mappings` 中的表头特征，因此不能让第一次 `identify()` 又依赖尚未选出的 Adapter aliases。

### 2. Adapter 证据结构

`detection_evidence.adapter_match` 建议结构：

```json
{
  "adapter_id": "yonyou",
  "adapter_score": 0.85,
  "source": "auto_detect",
  "matched_filename": true,
  "matched_signature_columns": ["科目编码", "科目名称"],
  "fallback_to_generic": false
}
```

如果用户选择 `adapter_hint`，`source` 为 `user_hint`。如果分数低于阈值并退回 `generic`，必须写明 `fallback_to_generic=true`。

### 3. Adapter 别名合并

`identifier.py` 当前有 `_RAW_HEADER_ALIASES` 与 JSON recognition rules。改造后字段匹配的 alias 来源顺序为：

1. 选中 Adapter 的 `get_column_aliases(table_type)`
2. `GenericAdapter.get_column_aliases(table_type)`
3. JSON recognition rules 中的全局别名

同一 header 命中多个 standard_field 时不静默覆盖，记录 `alias_conflicts`，优先级高者生效。

### 4. `ConfirmedMappingDTO`

前后端共享 DTO：

```typescript
interface ConfirmedMappingDTO {
  detection_id?: string
  sheet_key: string
  file_name: string
  sheet_name: string
  table_type: 'balance' | 'ledger' | 'aux_balance' | 'aux_ledger' | 'account_chart'
  mapping_entries: ConfirmedMappingEntry[]
  aux_dimension_columns: number[]
  file_fingerprint?: string
  software_fingerprint?: string
  confirmed_by_user: boolean
}

interface ConfirmedMappingEntry {
  column_index: number
  original_header: string
  canonical_header: string
  standard_field: string
}
```

`sheet_key` 建议由 `file_name + sheet_name + header_fingerprint` 派生，submit 阶段必须与 detect artifact 对齐。后端 submit 入口只允许 pipeline 消费规范化 DTO。如果收到历史格式 `{column_index: standard_field}`，必须利用 detect artifact 中的 `header_cells` 转换为 `mapping_entries`；无法转换时返回 400。

### 4.1 重复表头处理

parser 阶段必须生成稳定唯一的 canonical header：

```text
原始表头: ["期末余额.借方", "期末余额.贷方", "借方", "借方"]
canonical: ["期末余额.借方#0", "期末余额.贷方#1", "借方#2", "借方#3"]
```

`prepare_rows_with_raw_extra()` 应按 `column_index` 映射标准字段，而不是依赖 dict 中的 header 字符串。raw_extra 可使用 `canonical_header` 作为 key，并保留 `original_header` 以便用户追溯。

### 5. 后端 submit gate

submit 入口在创建 `ImportJob` 前执行：

- sheet key 是否能匹配 detect artifact
- 低置信度 sheet 是否 `confirmed_by_user=true`
- `unknown` sheet 被人工改类型后关键列是否完整
- `mappings` 是否包含该表类型的必需关键列或合法替代组
- 是否存在同一原始列映射到多个 standard_field
- 是否存在同一关键 standard_field 被多个原始列映射且无合并策略
- `sheet_key` / `detection_id` 是否与 detect artifact 中的 sheet 一致
- 低分 Adapter aliases 是否被用于自动通过关键列 gate

### 6. 历史映射保存点

历史映射保存应发生在 submit 成功创建 job 前，或作为 submit 同事务的一部分：

1. 规范化 DTO
2. 计算/读取 `file_fingerprint`
3. 对历史预填后被用户修改的 mapping 写新记录
4. 记录 `override_parent_id`
5. job 的 `custom_mapping` 保存规范化 DTO

### 7. 前端交互

`DetectionPreview.vue` 不应禁止 unknown sheet 的类型选择。用户可以把 unknown 改为四表之一，但进入 `ColumnMappingEditor.vue` 后必须补齐关键列。

`ColumnMappingEditor.vue` 展示：

- key / recommended / extra 分区
- 每列样本值
- 自动识别来源
- 历史映射 badge
- 缺失关键列的阻断说明

## 风险与兼容

- 老 job 中可能仍存在 `file/sheet/column_mapping` 格式。pipeline 可在迁移期兼容读取，但新 submit 必须写规范格式。
- JSON adapter 热加载需要明确启动时机，避免测试环境和生产环境 registry 内容不一致。
- Adapter 自动选优可能改变历史识别结果，需要以 snapshot 测试锁定 9 家样本。
- 从 header dict 迁移到 column-index mapping 会触碰 `prepare_rows_with_raw_extra()`，需要保留兼容 wrapper，避免一次性破坏已导入任务重试。

## 测试策略

- 单元测试：Adapter 选优、JSON adapter 加载、alias 冲突、mapping DTO normalization。
- 后端 API 测试：低置信度未确认 submit 被拒绝、unknown 人工改类型后可提交。
- 前端 Vitest：ColumnMappingEditor 输出 `ConfirmedMappingDTO`，不再输出旧字段。
- 快照测试：9 家样本 header 和 table_type 识别稳定。
