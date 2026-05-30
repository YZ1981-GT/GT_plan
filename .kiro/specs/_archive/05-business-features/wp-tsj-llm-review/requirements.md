# 需求文档：TSJ 提示词驱动 LLM 复核（wp-tsj-llm-review）

## 引言

`backend/data/tsj_review_prompts/` 70 个科目复核提示词是资深合伙人沉淀的复核框架。已有 `review_workpaper_with_prompt` 完整实现（底稿→audit_cycle→匹配 TSJ→注入 system prompt→逐项检查→存 ai_content），但**未接任何 router**（孤儿能力）。本 spec 接线 + 增强。

## 需求

### 需求 1：MVP 接线（让已有能力跑起来）
1. THE system SHALL 新增 `POST /api/workpapers/{wp_id}/ai/tsj-review` 端点，调用已有 `review_workpaper_with_prompt`
2. WHEN `WP_AI_SERVICE_ENABLED=True`，THEN 端点 SHALL 返回 LLM 复核结果
3. WHEN `WP_AI_SERVICE_ENABLED=False`，THEN 端点 SHALL 返回 stub 提示
4. THE frontend SHALL 在 SideStandardsTab（已展示 TSJ 原文）加「🤖 用此提示词复核当前底稿」按钮

### 需求 2：按认定分段复核（规避 8000 截断）
1. WHEN 底稿内容超过 8000 字符，THEN SHALL 按 TSJ 认定章节（存在性/完整性/准确性/权利义务/分类）分段调用 LLM
2. WHEN 分段复核，THEN 每段 SHALL 有独立 token 预算

### 需求 3：结构化输出
1. WHEN LLM 复核完成，THEN SHALL 解析输出为结构化 JSON（问题类型 / 严重程度 / sheet / 单元格范围 / 描述 / 整改建议）
2. WHEN 结构化发现产生，THEN SHALL 逐条写入 AiContent（content_type=risk_alert）并关联 target_cell
3. WHEN 复核发现写入，THEN SHALL 进入 V3 Req6 确认流（默认 pending，审计师逐条确认/驳回）

### 需求 4：复核发现跳证据（依赖 wp-locate-foundation）
1. WHEN 用户点击某条复核发现的"关联位置"，THEN SHALL 调 useCellLocate 跳转到底稿对应 cell
2. WHEN 复核发现关联附件，THEN SHALL 显示证据链接

## 范围边界
- 不改 TSJ 提示词内容
- 不替换现有 analytical_review / suggest（它们服务不同场景）
- 依赖 vllm-httpx-bugfix（LLM 链路必须先修）
- 需求 4 依赖 wp-locate-foundation
