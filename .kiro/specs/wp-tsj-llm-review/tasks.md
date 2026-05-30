# 实施计划：TSJ 提示词驱动 LLM 复核

## 任务

- [ ] 1. MVP 接线
  - [ ] 1.1 wp_ai.py 新增 `POST /api/workpapers/{wp_id}/ai/tsj-review`（调 review_workpaper_with_prompt，WP_AI_SERVICE_ENABLED 门控）
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ] 1.2 SideStandardsTab.vue 加「🤖 用此提示词复核当前底稿」按钮 + 调端点
    - _Requirements: 1.4_
  - [ ] 1.3 验证：WP_AI_SERVICE_ENABLED=True 时返回 LLM 结果（需 vLLM 可用）
    - _Requirements: 1.2_

- [ ] 2. 按认定分段复核
  - [ ] 2.1 实现 TSJ 提示词按认定章节拆分（解析 `## 存在性` 等 markdown 标题）
    - _Requirements: 2.1_
  - [ ] 2.2 每段独立 LLM 调用 + 独立 token 预算
    - _Requirements: 2.2_
  - [ ] 2.3 超 8000 字符底稿自动走分段（≤8000 仍单次调用）
    - _Requirements: 2.1_

- [ ] 3. 结构化输出
  - [ ] 3.1 LLM prompt 要求输出 JSON（findings 数组）
    - _Requirements: 3.1_
  - [ ] 3.2 后端解析 JSON → 逐条写入 AiContent（content_type=risk_alert, target_cell, confirm_action=pending）
    - _Requirements: 3.2, 3.3_
  - [ ] 3.3 解析失败时 fallback 为纯文本存储（不丢数据）
    - _Requirements: 3.1_

- [ ] 4. 确认流接入
  - [ ] 4.1 复核发现进 V3 Req6 确认流（AiContentMustBeConfirmedRule 自动生效）
    - _Requirements: 3.3_
  - [ ] 4.2 前端显示 pending 发现列表 + 确认/驳回按钮
    - _Requirements: 3.3_

- [ ] 5. 跳证据（依赖 wp-locate-foundation）
  - [ ] 5.1 复核发现的 target_cell → LocateTarget → 点击调 useCellLocate 跳转
    - _Requirements: 4.1_
  - [ ] 5.2 关联附件显示
    - _Requirements: 4.2_

- [ ] 6. 测试
  - [ ]* 6.1 MVP 端点单测（mock LLM，断言返回结构）
  - [ ]* 6.2 分段逻辑单测（TSJ 提示词拆分正确性）
  - [ ]* 6.3 结构化解析单测（valid JSON / invalid JSON fallback）

## 说明
- 依赖 vllm-httpx-bugfix（硬前置，LLM 链路必须先通）
- Task 5 依赖 wp-locate-foundation
- MVP（Task 1）可独立交付，增强（Task 2-5）按需推进
