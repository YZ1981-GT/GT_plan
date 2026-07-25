# Implementation Plan: review-prompt-sheet-level-split

## Overview

将现有科目级审计复核提示词拆分为底稿级（sheet-level），试点 D2 应收账款（8 张底稿）。实现底稿级提示词文件创建 → ReviewPromptService 匹配加载 → LlmResponseParser 解析 → HTTP 路由（单/批量/导出/覆盖率）→ BatchReviewService 编排 → 前端 ReviewPanel 展示 → PBT 测试 → E2E 验证。

后端 Python/FastAPI（cwd=backend/），前端 Vue 3 + Element Plus（cwd=audit-platform/frontend/）。

## Tasks

- [x] 1. D2 底稿级提示词文件创建
  - [x] 1.1 创建目录结构 `backend/data/tsj_review_prompts/D/` 并编写 D2-1.md（审定表：期初期末勾稽、试算平衡表核对、审计调整完整性、分类列报准确性）
    - 从源文件 `backend/data/tsj_review_prompts/应收账款审计复核提示词.md` §2.1(审计认定)+§4(数据勾稽)抽取对应章节作为骨架
    - 包含结构化 sections: tips, checklist, risk_areas（高/中/低）
    - _Requirements: 1.1, 1.2, 9.1_
  - [x] 1.2 编写 D2-2.md（明细表：客户信息完整性、余额准确性、账龄分析正确性、前五大客户集中度分析）
    - 从源文件 §2.2(余额核实)+§2.7(账龄)+§5(分析程序-客户集中度)抽取
    - _Requirements: 1.2, 9.2_
  - [x] 1.3 编写 D2-3.md（坏账准备：ECL模型参数合理性、迁徙率计算准确性、单项减值判断充分性、计提比例与政策一致性）
    - 从源文件 §2.6(减值测试)+§3.3(坏账准备充分性)+§6(行业特定-ECL)抽取
    - _Requirements: 1.2, 9.3_
  - [x] 1.4 编写 D2-5.md（分析表：变动分析合理性、周转率计算准确性、异常波动解释充分性、前后期对比逻辑性）
    - 从源文件 §5(分析程序)+§2.3(分析性复核)抽取
    - _Requirements: 1.2, 9.5_
  - [x] 1.5 编写 D2-7.md（凭证检查：样本选取方法合理性、凭证核对完整性、检查比例达标性、异常交易标注充分性）
    - 从源文件 §3(凭证测试)+§2.5(样本量)+§2.4(截止测试)抽取
    - _Requirements: 1.2, 9.4_
  - [x] 1.6 编写 D2-8.md（政策检查）、D2-note-listed.md（附注上市）、D2-note-soe.md（附注国企）
    - D2-8 从源文件 §2.8(会计政策)抽取；附注从 §7(披露与列报)抽取
    - _Requirements: 1.2_

- [x] 2. ReviewPromptService 实现
  - [x] 2.1 创建 `backend/app/services/review_prompt_service.py`，实现 `resolve_sheet_suffix` 方法
    - 正则从 sheet_name 提取底稿编号后缀（"审定表D2-1" → "D2-1"，"D2-note-listed" → "D2-note-listed"）
    - 支持中文+编号混合的 sheet_name 格式
    - _Requirements: 2.1_
  - [x] 2.2 实现 `load_prompt` 方法（三级降级加载）
    - Level 1: `{base_dir}/{cycle_letter}/{wp_code}-{suffix}.md`
    - Level 2: 现有 `_audit_cycle_aliases` 关键词匹配加载科目级文件
    - Level 3: 通用复核基础模板
    - 返回 PromptResult dataclass（content, source_level, file_path, tips, checklist, risk_areas）
    - _Requirements: 1.3, 1.4, 2.2, 2.3, 2.4, 10.4_
  - [x] 2.3 实现 `get_coverage` 方法（提示词覆盖率统计）
    - 扫描文件系统按 cycle_letter 目录聚合
    - 返回 CoverageReport（total_subjects, subjects_with_sheet_prompts, sheet_breakdown, missing_gaps）
    - _Requirements: 10.1, 10.2, 10.3_
  - [x]* 2.4 Property tests for ReviewPromptService (P1, P2, P3, P4)
    - **Property 1: Sheet suffix extraction round-trip**
    - **Property 2: Prompt resolution specificity ordering**
    - **Property 3: Fallback completeness**
    - **Property 4: File path construction determinism**
    - **Validates: Requirements 2.1, 2.2, 2.4, 1.4, 10.4**

- [x] 3. LlmResponseParser 实现
  - [x] 3.1 创建 `backend/app/services/llm_response_parser.py`，实现 `parse` 静态方法
    - 识别 checklist 标记（`- [ ]` / `- [x]`），未勾选项 → ReviewFinding
    - 从 section 标题推断 risk_level（"高风险"→high、"中风险"→medium、"低风险"→low）
    - 解析失败降级：存储原文为单条 unknown finding
    - _Requirements: 8.1, 8.2, 8.4_
  - [x] 3.2 实现 `determine_pass_status` 静态方法
    - Rules: zero high-risk AND < 3 medium-risk → "pass"，否则 "fail"
    - _Requirements: 8.3_
  - [x]* 3.3 Property tests for LlmResponseParser (P5, P12)
    - **Property 5: Pass/fail determination correctness**
    - **Property 12: Parse degradation safety**
    - **Validates: Requirements 8.3, 8.4**

- [x] 4. Checkpoint - 核心服务层验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. HTTP 路由端点实现
  - [x] 5.1 创建 `backend/app/routers/review_prompt.py`，实现 POST `/api/workpapers/{wp_id}/review` 端点
    - 接收 optional body `{sheet_name: string}`
    - 有 sheet_name 时用 ReviewPromptService 匹配 sheet-level prompt
    - 无 sheet_name 时降级到科目级（向后兼容）
    - 不复用旧 review_workpaper_with_prompt（走 audit_cycle 匹配，与 sheet-level 冲突）
    - 新写 `review_sheet` 函数：ReviewPromptService.load_prompt → 获取底稿内容(render-config JSON→文本) → chat_completion → LlmResponseParser.parse → 返回结构化结果
    - 底稿内容获取：GET /api/workpapers/{wp_id}/render-config → 提取 html_data/sheets 中对应 sheet 的文本内容（非读文件路径）
    - 返回 ReviewResponse（findings, overall_pass, risk_summary, sheet_info）
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 5.2 实现 POST `/api/projects/{pid}/batch-review` 端点
    - 接收 `{wp_code_prefix: str, year: int}`
    - 委托 BatchReviewService 执行
    - _Requirements: 4.1_
  - [x] 5.3 实现 GET `/api/projects/{pid}/review-export` 端点
    - 生成 Excel workbook（openpyxl），每张底稿一个 worksheet + 首页汇总
    - 列：序号/检查项/风险等级/是否通过/问题描述/涉及底稿定位/整改建议/负责人/状态
    - RFC5987 中文文件名编码
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 5.4 实现 GET `/api/review-prompts/coverage` 端点
    - 委托 ReviewPromptService.get_coverage
    - _Requirements: 10.3_
  - [x] 5.5 注册路由到 `router_registry/system.py`
    - _Requirements: 3.1_
  - [x]* 5.6 Property tests for export (P10, P11)
    - **Property 10: Export worksheet count**
    - **Property 11: RFC5987 filename encoding validity**
    - **Validates: Requirements 7.1, 7.4**

- [x] 6. BatchReviewService 实现
  - [x] 6.1 创建 `backend/app/services/batch_review_service.py`，实现 `execute_batch` 方法
    - 查 wp_index + working_paper 获取前缀下所有底稿
    - 逐份调用 LLM 复核（顺序，避免 LLM 并发压力）
    - 单底稿失败标记 review_error 继续下一张（容错续行）
    - 汇总 BatchReviewReport（per-sheet results, statistics, execution metadata）
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 6.2 实现持久化逻辑（写入 ai_content 表）
    - content_type="review_finding"
    - data_sources 包含 sheet_name, risk_level, pass_status, category, session_id, wp_code
    - 复核会话索引写入 checklist_responses（item_id=`{wp_code}-review-session-{timestamp}`）
    - Append-only，不覆盖旧记录
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x]* 6.3 Property tests for BatchReviewService (P6, P7, P8, P9)
    - **Property 6: Batch resilience (error isolation)**
    - **Property 7: Append-only persistence**
    - **Property 8: Finding traceability**
    - **Property 9: Batch statistics consistency**
    - **Validates: Requirements 4.4, 5.3, 5.4, 4.3**

- [x] 7. Checkpoint - 后端全链路验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 前端 ReviewPanel 组件
  - [x] 8.1 创建 `audit-platform/frontend/src/components/workpaper/review/ReviewPanel.vue`
    - Props: projectId, wpCodePrefix, year
    - 挂载入口：底稿列表页 WorkpaperWorkbenchView 的科目级操作区（非单张底稿侧栏）
    - 也可从科目主入口组件（如 GtD2Receivables.vue）的 tab-toolbar 右侧触发打开 el-dialog
    - 显示每张底稿卡片：sheet name, pass/fail badge, finding count, 风险等级分布（high/medium/low）
    - 卡片点击展开完整 Finding 列表（description, risk_level tag 色标, category, sheet_location）
    - "开始批量复核" 按钮（visible to 现场经理/业务合伙人/QC合伙人）
    - 复核进行中显示进度（当前 sheet + completion %）
    - "导出 Excel" 按钮触发 review-export 下载
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 8.2 创建 `useReviewPanel` composable
    - API 调用封装（batch-review POST / review-export GET / 单底稿 review POST）
    - 状态管理（sheets, isReviewing, progress, expandedSheet）
    - 使用 http（axios）而非原生 fetch
    - _Requirements: 6.1, 6.4_

- [x] 9. Checkpoint - 前后端联调验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. PBT + 集成测试
  - [x]* 10.1 创建 `backend/tests/test_review_prompt_service_pbt.py`
    - @settings(max_examples=5) 全局
    - P1: resolve_sheet_suffix round-trip（中文+编号组合）
    - P2: load_prompt specificity（有 sheet 文件时必返 sheet）
    - P3: fallback completeness（任何 wp_code 必返非空）
    - P4: file path determinism（合法 wp_code → 确定路径）
    - _Requirements: 2.1, 2.2, 2.4, 1.4_
  - [x]* 10.2 创建 `backend/tests/test_llm_response_parser_pbt.py`
    - P5: pass/fail determination（findings 组合 → 正确 pass/fail）
    - P12: parse degradation safety（任何字符串不崩溃）
    - _Requirements: 8.3, 8.4_
  - [x]* 10.3 创建 `backend/tests/test_batch_review_pbt.py`
    - P6: batch error isolation（N sheets K errors → N results）
    - P9: batch statistics consistency（total = passed + failed + error）
    - _Requirements: 4.3, 4.4_
  - [x]* 10.4 创建 `backend/tests/test_review_export_pbt.py`
    - P10: worksheet count = reviewed sheets + 1
    - P11: RFC5987 filename encoding round-trip
    - _Requirements: 7.1, 7.4_
  - [x]* 10.5 创建 `backend/tests/test_review_prompt_integration.py` 集成测试
    - POST /api/workpapers/{wp_id}/review 端点响应结构
    - POST /api/projects/{pid}/batch-review 批量调用
    - GET /api/review-prompts/coverage 覆盖率
    - ai_content 表写入验证
    - _Requirements: 3.4, 4.3, 10.3, 5.1_

- [x] 11. Playwright E2E 验证
  - [x]* 11.1 创建 `audit-platform/frontend/e2e/review-panel.spec.ts`
    - 导航到含 D2 底稿的项目
    - ReviewPanel 挂载渲染（卡片列表）
    - 点击"开始批量复核"按钮触发 API
    - 验证进度条显示
    - 展开卡片查看 Finding 列表
    - 导出 Excel 按钮触发下载
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1_

- [x] 12. Final checkpoint - 全链路验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (hypothesis, @settings(max_examples=5))
- Unit tests validate specific examples and edge cases
- 现有依赖：workpaper_fill_service.py（review_workpaper_with_prompt）、tsj_prompt_service.py（解析逻辑）、ai_service.py（chat_completion）、openpyxl（导出）
- 路由注册到 router_registry/system.py
- 测试命令：`python -m pytest backend/tests/test_review_*.py -v`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "5.1", "5.4", "5.5"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 5, "tasks": ["5.6", "6.2", "6.3"] },
    { "id": 6, "tasks": ["8.1", "8.2"] },
    { "id": 7, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "11.1"] }
  ]
}
```
