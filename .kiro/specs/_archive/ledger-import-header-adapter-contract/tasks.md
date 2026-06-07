# 实施计划：账表导入表头识别与适配器契约

## 任务总览

- [x] 1. 定义识别与映射契约
  - [x] 1.1 后端新增 `ConfirmedMappingDTO` / `NormalizedMappingDTO`
  - [x] 1.2 前端更新 `ConfirmedMapping` 类型，统一字段为 `file_name`、`sheet_name`、`mappings`
  - [x] 1.3 增加前后端 DTO fixture，确保字段名和枚举一致
  - [x] 1.4 将 `mappings` 升级为 `mapping_entries[]`，每条包含 `column_index`、`original_header`、`canonical_header`、`standard_field`
  - [x] 1.5 定义稳定 `sheet_key` / `detection_id`，submit 阶段用于校验 detect artifact
  - _Requirements: 4.1, 4.2, 4.3, 4.6_

- [x] 2. 接入 Adapter 自动选优
  - [x] 2.1 detect 先用 generic/global aliases 做 provisional `identify`
  - [x] 2.2 支持 `adapter_hint` 覆盖自动选优
  - [x] 2.3 在 provisional mappings 生成后调用 `AdapterRegistry.detect_best(fd)`
  - [x] 2.4 用选中 adapter aliases + generic aliases 进行 final `identify`
  - [x] 2.5 将 `adapter_id`、`adapter_score`、匹配证据写入 `detection_evidence.adapter_match`
  - [x] 2.6 adapter 分数低但 table_type 高置信时，保留表类型、列映射进入人工确认
  - [x] 2.7 测试：vendor adapter 分数高于 generic 时自动命中，低分 adapter 不自动通过关键列 gate
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7_

- [x] 3. JSON 驱动适配器加载
  - [x] 3.1 明确启动加载 `backend/data/ledger_adapters/*.json` 的入口
  - [x] 3.2 非法 JSON / 缺 `id` / regex 错误记录 warning 并跳过
  - [x] 3.3 同 `id` adapter 覆盖时记录来源
  - [x] 3.4 测试：`sample.json` 可加载并参与 alias 映射
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. 表头识别增强
  - [x] 4.1 `_detect_header_row` 支持表头位于第 11 至 20 行
  - [x] 4.2 增加 3 层合并表头识别或明确降级策略
  - [x] 4.3 增加二维借贷平铺列识别测试
  - [x] 4.4 保留 `header_cells_raw`、`merged_header`、`compound_headers`、`amount_unit`
  - [x] 4.5 测试：方括号、组合表头、横幅跳过、skip_reason 稳定
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 5. Submit gate 与 mapping normalization
  - [x] 5.1 submit 入口读取 detect artifact，校验 sheet key
  - [x] 5.2 兼容旧 `{column_index: standard_field}` 输入并转换为 `mapping_entries[]`
  - [x] 5.3 无法转换旧格式时返回 400，不创建 ImportJob
  - [x] 5.4 低置信度未确认、关键列缺失、unknown 未改类型时阻断 submit
  - [x] 5.5 pipeline 只消费规范化 DTO，并按 `column_index` 取原始列值
  - [x] 5.6 `prepare_rows_with_raw_extra` 支持 canonical header，重复原始表头不得覆盖
  - [x] 5.7 测试：重复"借方/贷方/金额"表头都能保留并正确映射
  - _Requirements: 4.3, 4.4, 4.5, 4.6, 5.1, 5.3_

- [x] 6. 前端人工确认流程
  - [x] 6.1 `DetectionPreview.vue` 允许 unknown sheet 人工选择表类型
  - [x] 6.2 `ColumnMappingEditor.vue` 输出规范 `ConfirmedMappingDTO`
  - [x] 6.3 展示样本值、历史映射 badge、关键列缺失原因
  - [x] 6.4 测试：关键列未补齐时不能确认
  - [x] 6.5 测试：unknown 人工改为 balance 后进入列映射
  - _Requirements: 5.1, 5.2, 5.4_

- [x] 7. 历史映射保存与复用
  - [x] 7.1 submit 成功前保存 `file_fingerprint` / `software_fingerprint` mapping
  - [x] 7.2 用户修改历史预填时写 `override_parent_id`
  - [x] 7.3 detect 阶段命中历史映射时标记 `auto_applied_from_history`
  - [x] 7.4 禁止跨项目历史映射静默覆盖，跨项目复用必须显式触发
  - [x] 7.5 测试：30 天窗口、父子链、过期记录不复用
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

## P0-MVP

- [x] MVP-1. `ConfirmedMappingDTO` 前后端一致
- [x] MVP-2. submit gate 能阻断低置信度未确认与关键列缺失
- [x] MVP-3. pipeline 消费 `mapping_entries[]` 单一格式，重复表头不丢列
- [x] MVP-4. Adapter 自动选优或显式 hint 口径落地并有 evidence
- [x] MVP-5. unknown sheet 可人工改类型并补映射

## 验收与回归

- [x] CI-1 pytest：AdapterRegistry / JSON adapter / alias merge 通过
- [x] CI-2 pytest：submit mapping normalization 和低置信度 gate 通过
- [x] CI-3 pytest：9 家样本 header snapshot 不回退
- [x] CI-4 Vitest：ColumnMappingEditor 输出新 DTO
- [x] CI-5 手工 UAT：上传未知格式余额表，人工确认后可导入
- [x] CI-6 回归：历史 mapping 30 天内自动预填，修改后形成父子链
- [x] CI-7 pytest：重复表头 canonical header 与 raw_extra 保留通过
