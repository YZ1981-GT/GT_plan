# Implementation Plan: 公式推送附注行匹配增强（formula-push-note-row-matching）

## Overview

解决公式推送引擎向附注子表推送审定数时 skipped_count 虚高问题。三个互补改进：①延迟 per-row skip 记录，合计行兜底成功后重分类为 `fallback_to_total`；②`find_row` 新增第三级包含匹配减少不必要的兜底；③PG 守卫按跳过原因分类别设棘轮。附带一次性探针脚本获取真实分布数据。

实现语言：Python（后端）。测试框架：pytest + hypothesis（max_examples=5）。

## Tasks

- [x] 0. 探针脚本（需求 4）
  - [x] 0.1 新建探针脚本 `backend/scripts/analyze/_nrm_probe_skip_breakdown.py`
    - 在真库上 `dry_run=True` 运行公式推送，遍历 `result.items` 中 `action=skipped` 且 reason 含"没有…行"的记录
    - 逐条输出 rule_id / wp_code / note_label / table_name / has_total / fallback_wrote
    - 按 wp_code 聚合统计虚假 skip（兜底已成功）与真正 skip（兜底未成功）
    - 输出到 `backend/scripts/analyze/_nrm_skip_breakdown_output.txt`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 0.2 在真库运行探针脚本，获取行匹配失败的详细分布
    - 需要连接重药控股安徽 2025 真实 PG 数据库
    - 记录 skipped 分布数据用于后续棘轮基线设定
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 0.3 从探针输出设定分类别棘轮基线值
    - 根据探针脚本产出的分布数据，填写 `_MAX_SKIPPED_BY_CATEGORY` 各类别的基线值
    - _Requirements: 3.1, 5.2_

- [x] 1. 延迟 skip 记录 + 重分类（需求 1）
  - [x] 1.1 在 `results.py` 新增 `FALLBACK_TO_TOTAL` 常量
    - 新增 `FALLBACK_TO_TOTAL = "fallback_to_total"` 与现有 `SKIPPED`/`CONFLICT` 并列
    - 确认 `skipped_count` 属性只计 `SKIPPED`/`CONFLICT`，`FALLBACK_TO_TOTAL` 不在其中（无需改 `skipped_count` 实现）
    - _Requirements: 1.1_

  - [x] 1.2 改 `engine.py::_push_note`：引入 `pending_row_skips` 延迟收集
    - 在 `_push_note` 函数内新增局部变量 `pending_row_skips: list[tuple[str, str]]`（存 addr_id 和 reason）
    - 数据行循环内 `find_row` 返回 None 时，不再立即调用 `ctx.skip()`，而是 `pending_row_skips.append((addr, reason))`
    - 确保 `"底稿未取到该行数值"` 的 skip **不参与延迟**（它代表科目不存在的真正跳过，保持立即 `ctx.skip()`）
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 1.3 改 `engine.py::_push_note`：合计行兜底成功后设 `fallback_wrote`
    - 在合计行兜底路径中，`source_row is not None` 且 `skip_total_recalc = True` 时同步设置 `fallback_wrote = True`
    - 语义：合计行路径被进入且产生了有意义的动作（即使 `_push_note_cell` 返回 False / unchanged）
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 1.4 改 `engine.py::_push_note`：循环结束后统一 flush pending_row_skips
    - 遍历 `pending_row_skips`，`action = FALLBACK_TO_TOTAL if fallback_wrote else SKIPPED`
    - 构造 `PushItem(rule_id, "note", "note", addr, action, reason=reason)` 追加到 `ctx.result.items`
    - 保留原始 `addr_id` 和 `reason` 字段（审计轨迹完整性，AC 1.3）
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.5 跑现有 formula_push 测试确认无回归
    - `python -m pytest backend/tests/ -k formula_push --tb=short`
    - 44 个现有测试 + 1 个 PG 守卫必须零回归
    - _Requirements: 5.1_

- [x] 2. 包含匹配（需求 2）
  - [x] 2.1 改 `note_writer.py::find_row`：新增第三级包含匹配
    - 在现有精确匹配和去"小计"后缀匹配之后，新增包含匹配（substring）
    - 遍历 `wanted` 标签，对每个非空 label 查找 `label in row_label(row) or row_label(row) in label`
    - 排除 `is_total=True` 的行（AC 2.4）
    - 唯一命中（`len(candidates)==1`）时返回该行索引（AC 2.3）；多命中或零命中返回 None（AC 2.2）
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 2.2 写 PBT `test_find_row_contains_unique_hit`
    - **Property 3: 包含匹配唯一命中返回正确索引**
    - **Validates: Requirements 2.1, 2.3**
    - 构造恰好有唯一非 total 行的 label 与搜索标签满足包含关系的附注行列表
    - 断言 `find_row` 返回该行索引

  - [x]* 2.3 写 PBT `test_find_row_contains_multi_hit_returns_none`
    - **Property 4: 包含匹配多命中返回 None**
    - **Validates: Requirements 2.2**
    - 构造多于一行非 total 行满足包含关系的附注行列表
    - 断言 `find_row` 返回 None

  - [x]* 2.4 写 PBT `test_find_row_contains_excludes_total`
    - **Property 5: 包含匹配排除合计行**
    - **Validates: Requirements 2.4**
    - 构造唯一满足包含关系的行是 `is_total=True` 的场景
    - 断言 `find_row` 返回 None（合计行不参与模糊匹配）

  - [x]* 2.5 写回归测试 `test_find_row_exact_match_not_affected`
    - 验证精确匹配成功时不受第三级包含匹配影响（回归保护）
    - _Requirements: 2（回归）_

  - [x] 2.6 变异验证：删除包含匹配逻辑 → 2.2 打红
    - 临时删除第三级包含匹配代码块，确认 `test_find_row_contains_unique_hit` 失败
    - 恢复代码，确认测试通过
    - _Requirements: 5.5_

- [x] 3. 延迟 skip 单元测试 + PBT（需求 1 + 5）
  - [x]* 3.1 写 PBT `test_deferred_skip_reclassified_on_fallback`
    - **Property 1: 合计行兜底成功后 skip 记录被重分类且字段保留**
    - **Validates: Requirements 1.1, 1.3**
    - 构造 mock 附注表（所有数据行 find_row 返回 None，有合计行）
    - 断言所有 per-row skip 记录的 action 为 `fallback_to_total`，且 addr_id / reason 保留

  - [x]* 3.2 写 PBT `test_deferred_skip_stays_skipped_without_total`
    - **Property 2: 合计行兜底失败时 skip 记录保持 skipped**
    - **Validates: Requirements 1.2**
    - 构造 mock 附注表（无合计行）
    - 断言所有 per-row skip 记录的 action 为 `skipped`

  - [x]* 3.3 写示例测试 `test_deferred_skip_multi_account`
    - 模拟多科目底稿（如 F2 存货 6 个科目码），验证 6 行 × 2 字段 = 12 条 pending 全部重分类
    - _Requirements: 1.4_

  - [x]* 3.4 写示例测试 `test_deferred_skip_single_account`
    - 模拟单科目底稿（如 N4 应交税费），验证 1 行 × 2 字段 = 2 条 pending 重分类
    - _Requirements: 1.5_

  - [x] 3.5 变异验证：删除 `fallback_wrote = True` → 3.1 打红
    - 临时删除 `fallback_wrote = True` 赋值，确认 `test_deferred_skip_reclassified_on_fallback` 失败
    - 恢复代码，确认测试通过
    - _Requirements: 5.5_

- [x] 4. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 分类别 PG 守卫（需求 3）
  - [x] 5.1 在 `test_formula_push_note_skip_pg.py` 新增 `_categorize()` 函数和 `_SKIP_CATEGORIES` 字典
    - 正则匹配 reason 字段：A=行匹配失败 / C=银行明细未取数 / D=章节号不匹配 / G=模板缺定义 / I=科目不存在
    - 首次匹配即分类，未匹配归入 `"other"`
    - _Requirements: 3.1, 3.4_

  - [x] 5.2 新增 `_MAX_SKIPPED_BY_CATEGORY` 棘轮基线
    - 初始值先用探针脚本输出设定（Task 0.3），若探针未运行则设保守上限值
    - _Requirements: 3.1_

  - [x] 5.3 新增分类别断言 + 总量安全网
    - 每个类别独立棘轮断言，失败消息明确报出类别名称和超出量（AC 3.2）
    - 保留原有 `_MAX_SKIPPED` 总量安全网
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 5.4 写 PBT `test_categorize_known_patterns`
    - **Property 6: 跳过原因分类完备性**
    - **Validates: Requirements 3.1, 3.4**
    - 对已知类别的 reason 样例验证分类正确；对未知 reason 验证归入 "other"

  - [x]* 5.5 写示例测试 `test_pg_guard_category_assertion_message`
    - 构造某类别超过棘轮的场景，断言失败消息包含类别名和超出量
    - _Requirements: 3.2_

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 真库验证 + 棘轮更新（需求 5.2–5.3）
  - [x] 7.1 跑全套 formula_push 测试确认零回归
    - 需要真实 PG 数据库连接
    - _Requirements: 5.1_

  - [x] 7.2 在真库运行 PG 守卫，验证 skipped 下降
    - 预期 skipped 从 208 下降至 ~170 以下（需求 1 消除虚假 skip + 需求 2 减少不必要兜底）
    - _Requirements: 5.2_

  - [x] 7.3 更新 `_MAX_SKIPPED` 和 `_MIN_COVERAGE` 棘轮基线至实测值
    - `_MAX_SKIPPED` 只许减不许增（AC 5.2）；`_MIN_COVERAGE` 只许增不许减（AC 5.3）
    - 同步更新 `_MAX_SKIPPED_BY_CATEGORY` 各类别基线至实测值
    - _Requirements: 5.2, 5.3_

  - [x] 7.4 验证幂等不变量（两次 dry_run 结果一致）
    - 两次运行的 unchanged 项 addr_id 集合必须相同
    - _Requirements: 5.4_

- [x] 8. 清理
  - [x] 8.1 删除探针脚本 `backend/scripts/analyze/_nrm_probe_skip_breakdown.py` 及其输出文件
    - 一次性探针用完即删（`_` 前缀文件）
    - _Requirements: 5.6_

  - [x] 8.2 更新 memory.md dev-history 记录本 spec 完成状态
    - 记录实测 skipped / coverage 最终值、棘轮基线变更

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design document
- Unit tests validate specific examples and edge cases
- Task 0.2/0.3 和 Task 7 全部需要真实 PG 数据库，标为 `[-]`
- Task 8 是手动清理工作，标为 `[-]`
- 改动文件范围：`results.py`（1 常量）/ `engine.py`（~30 行 `_push_note`）/ `note_writer.py`（~15 行 `find_row`）/ 两个测试文件

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1"] },
    { "id": 1, "tasks": ["0.2", "1.1"] },
    { "id": 2, "tasks": ["0.3", "1.2", "1.3"] },
    { "id": 3, "tasks": ["1.4", "2.1"] },
    { "id": 4, "tasks": ["1.5", "2.2", "2.3", "2.4", "2.5"] },
    { "id": 5, "tasks": ["2.6", "3.1", "3.2", "3.3", "3.4"] },
    { "id": 6, "tasks": ["3.5", "5.1", "5.2"] },
    { "id": 7, "tasks": ["5.3", "5.4", "5.5"] },
    { "id": 8, "tasks": ["7.1"] },
    { "id": 9, "tasks": ["7.2"] },
    { "id": 10, "tasks": ["7.3", "7.4"] },
    { "id": 11, "tasks": ["8.1", "8.2"] }
  ]
}
```
