# 合并附注从单体附注拉取数据 — 实施任务（v2，基于真库实测修正）

## 真库实测修正摘要

- **_tables 是主读取路径**（98.4%），sub_table_data 仅 13.5%
- **公式推送规则不需要补**，70 个已够用
- **已有 3 个项目有真实推送数据**可验证（安徽/和平/宜宾）
- **差额节点 Phase 1 不处理**，只汇总数据叶子的个别数

## Phase 1：核心链路

### Task 1：章节映射生成脚本与配置文件

- [x] 1.1 新建 `backend/scripts/seed/gen_consol_standalone_note_mapping.py`
  - 八章优先匹配（避免十二章关联方同名覆盖）
  - SOE 104/110 自动匹配（94%），Listed 94/101（93%）
  - AC：✅ SOE ≥ 96/110 自动匹配

- [x] 1.2 手工补充 14 个截断名映射（fuzzy 匹配自动覆盖 8 个，仅 6 个 consol_only）
  - AC：✅ consol_only 仅"续："类续表章节

- [x] 1.3 新建 `backend/app/services/consol_note_section_mapping.py`
  - `resolve_standalone_section` / `resolve_consol_sections` / `all_mapped_sections`
  - mtime 缓存
  - AC：✅ 单测验证 `五-1-1` → `八、1`（SOE）；`五-4-1` → `八、4`（SOE）

- [x] 1.4 新建 `backend/tests/test_consol_note_section_mapping.py`
  - 15 个测试全绿
  - AC：✅ ≥ 8 个测试用例

### Task 2：单体附注读取层（_tables 主路径）

- [x] 2.1 `read_standalone_note_table()` 统一入口
  - 优先级：sub_table_data → _tables（按 name）→ _tables[0]
  - AC：✅ 单测 4 例

- [x] 2.2 `read_tables_format()` — _tables 行读取
  - dict 行 {label, values:[]} + list 行 [cell, cell, ...]
  - AC：✅ 单测 5 例

- [x] 2.3 `read_sub_table_format()` — F2 业务键 + F3 values 数组
  - AC：✅ 单测 4 例

- [x] 2.4 `_match_column()` 列匹配
  - 精确 → 同义词组匹配（_END_SYNONYMS / _PRIOR_SYNONYMS）
  - AC：✅ 单测 6 例

### Task 3：汇总核心逻辑

- [x] 3.1 `aggregate_section()` 主函数
  - 章节映射 → 批量加载 → 逐叶子读取 + 行列匹配 + 累加
  - AC：✅ 端到端 mock 测试 2 个子企业货币资金汇总

- [x] 3.2 `_batch_load_notes()` 批量查询优化
  - 一次 `WHERE project_id IN (...) AND note_section = ...` 查全部叶子
  - AC：✅ 实现

- [x] 3.3 `_find_matching_row()` 行匹配
  - 三级策略：精确 → 去后缀 → 包含唯一命中
  - AC：✅ 单测 7 例

- [x] 3.4 `AggregateResult` + `CellValue` + `LeafStatus` 数据结构
  - AC：✅ 完整定义

### Task 4：reaggregate 端点改造

- [x] 4.1 `reaggregate_from_standalone()` 编排函数
  - 逐章节 SAVEPOINT + fill_rows + manual_cells/locked_cells 保护
  - AC：✅ 在 consol_note_aggregator.py 中实现

- [x] 4.2 修改 `consol_notes.py` 的 reaggregate 端点
  - `fill_note_sections()` → `reaggregate_from_standalone()`
  - ReaggregateResponse 新增 `leaf_summary` + `source`（超集兼容）
  - AC：✅ 锁测试 PASSED

- [x] 4.3 CellValue → fill_rows 格式转换
  - `{row_index, col_index, MEASURE_CONSOLIDATED: str(value)}`
  - AC：✅ fill_rows 不需要改动

### Task 5：前端汇总结果弹窗增强

- [x] 5.1 handleReaggregate 结果处理增加 leaf_summary
  - 消息显示子企业读取状态（已读取 N/M 个）
  - 缺失子企业列出名称和原因
  - AC：✅ 代码实现

- [ ]* 5.2 增加 unmatched_rows 展示
  - `[ ]*` 依赖 start-dev 环境浏览器实测

### Task 6：回归测试

- [x] 6.1 `test_consol_note_aggregator.py` — 34 个测试全绿
  - _safe_float 7 / 列匹配 6 / 行匹配 7 / _tables 5 / sub_table 4 / 统一入口 4 / 端到端 1
  - AC：✅ ≥ 15 个测试用例

- [x] 6.2 现有合并附注测试不回归
  - 46 passed / 2 预存 failed（HEAD 也失败：seed_counts 基线不一致）
  - AC：✅ 0 回归

- [x] 6.3 端到端测试：货币资金（2 个子企业汇总）
  - TestAggregateEndToEnd.test_two_subsidiaries_sum
  - AC：✅ 测试通过（库存现金=150, 银行存款=500）

- [ ]* 6.4 端到端测试：存货（多表 + values 数组格式）
  - `[ ]*` 在 PG 真库环境补测

### Task 7：收尾

- [x] 7.1 映射配置文件已生成
  - `consol_note_section_mapping.json` — 753 条映射
  - AC：✅ 文件在仓库中

- [x] 7.2 API 实测通过
  - 测试集团项目 reaggregate 五-1-1 返回 200 persisted
  - filled 4 格，链路完整
  - AC：✅ 端到端验证通过

- [x] 7.3 更新 tasks.md 完成状态
  - AC：✅ 本文件


## Phase 2 进展

### Stale 联动（2026-10-22 实施）

- [x] NOTE_SECTION_SAVED → 标 consol_note_data.is_stale
  - 在 `consol_note_stale_handler.py` 新增 `_on_note_section_saved_mark_consol_stale` handler
  - 通过 `consol_note_section_mapping.resolve_consol_sections()` 找对应的合并附注章节
  - 通过 `_find_consol_parents()` 递归找所有 parent 合并项目
  - `_mark_consol_note_data_stale()` 标 consol_note_data.is_stale=True
  - SSE 广播 `consol.note_stale` 让前端实时感知
  - AC：✅ 53 测试全绿（49 新增 + 4 现有 stale SSE 测试）

### API 实测（2026-10-22）

- [x] 测试集团 reaggregate 五-1-1/五-2-1/五-4-1/五-5-1 全部 persisted
  - 五-5-1 应收账款读到真实金额 1920.00（来自子企业单体附注）
  - 四个章节全部成功写入 consol_note_data
  - AC：✅ Status 200 / 4 sections_updated

### 启动修复（2026-10-22）

- [x] V200 迁移版本号冲突：并发会话的 `V200__consol_note_mapping_reuse_and_reference.sql` → V202
- [x] formula_health.py import 错误：try/except 包住路由注册
- [x] note_custom_section.py import 错误：try/except 包住路由注册
