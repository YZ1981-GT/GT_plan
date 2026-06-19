# Implementation Plan: 底稿编制指导助手

## Overview

按 P0→P1→P2→P3 四阶段递进实现：P0 面板骨架+静态提取（零 LLM 依赖），P1 LLM 对话集成，P2 RAG+上下文注入，P3 全量覆盖优化（复杂度自适应+缓存+性能）。后端扩展现有 `wp_guidance_service.py`，前端新建 `WpGuidancePanel.vue` 在 layout 层集成。

## Tasks

### Phase 0: 面板骨架 + 静态提取

- [x] 0. 种子数据验证：扫描模板覆盖率
  - 创建 `scripts/analyze/scan_guidance_sheets.py`：遍历 331 个 wp_templates 文件，统计有/无「编制说明」sheet 的数量和覆盖率
  - 输出报告：高复杂度底稿(A17/B60/审定表/程序表)中有多少有编制说明 sheet
  - 如覆盖率 < 50%：为 top 20 高复杂度底稿创建 `backend/data/wp_guidance/{wp_code}.json` 静态指引文件
  - _Requirements: 2.1~2.4_

- [x] 1. 实现 GuidanceExtractor 模板提取核心
  - [x] 1.1 创建 `backend/app/services/guidance_extractor.py`，实现 `GuidanceExtractor` 类
    - 定义 `GuidanceResult` / `GuidanceSection` dataclass
    - 实现 `_extract_xlsx_sheet`：python_calamine 读取「编制说明」/「说明」/「Instructions」sheet，按序号行分 section
    - 实现 `_extract_xlsx_header`：首 sheet 前 5 行合并单元格提取
    - 实现 `_extract_docx_instructions`：python-docx 提取第一个表格之前的段落
    - 实现 `extract` 主入口：优先级 sheet → header → static_json → fallback
    - 5 秒超时保护（`asyncio.wait_for`）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 1.2 Write property test for GuidanceExtractor (Property 1: 模板提取保持结构化)
    - **Property 1: 模板提取保持结构化**
    - **Validates: Requirements 2.1, 2.5**
    - 文件: `backend/tests/test_guidance_extractor_pbt.py`
    - `@settings(max_examples=5)`

  - [x]* 1.3 Write property test for GuidanceExtractor (Property 2: Guidance 端点永不返回空)
    - **Property 2: Guidance 端点永不返回空**
    - **Validates: Requirements 2.4, 2.8**
    - 文件: `backend/tests/test_guidance_service_pbt.py`
    - `@settings(max_examples=5)`

- [x] 2. 实现 GuidanceCache 缓存层
  - [x] 2.1 创建 `backend/app/services/guidance_cache.py`，实现 `GuidanceCache` 类
    - `OrderedDict` LRU（maxsize=128）
    - `get(wp_code, template_path)` → mtime 校验命中/失效
    - `put(wp_code, template_path, result)` → LRU 淘汰
    - _Requirements: 2.6, 8.1, 8.2, 8.3_

  - [x]* 2.2 Write property test for GuidanceCache (Property 3: 缓存一致性)
    - **Property 3: 缓存一致性（mtime 失效）**
    - **Validates: Requirements 2.6, 8.1, 8.2, 8.3**
    - 文件: `backend/tests/test_guidance_cache_pbt.py`
    - `@settings(max_examples=5)`

- [x] 3. 扩展 GuidanceService + REST 端点
  - [x] 3.1 扩展 `backend/app/services/wp_guidance_service.py`
    - 注入 `GuidanceExtractor` + `GuidanceCache`
    - 实现 `get_guidance(wp_id)` 编排：DB 查 wp → 定位模板路径 → cache.get → extractor.extract → cache.put → 降级链
    - 实现 `classify_complexity(wp_code)` 从 `_complexity.json` 配置
    - 实现推荐问题映射（program/determination/default）
    - _Requirements: 2.7, 2.8, 7.1_

  - [x] 3.2 创建 `backend/app/routers/wp_guidance_chat.py` 路由
    - `GET /api/workpapers/{wp_id}/guidance` 端点（JWT 认证）
    - 响应格式：`{wp_code, wp_name, source, complexity, guidance: {sections, raw_text}, recommended_questions}`
    - 404 处理（无效 wp_id）
    - 注册到 `router_registry`
    - _Requirements: 2.7, 2.8, 9.5_

  - [x]* 3.3 Write property test (Property 6: 推荐问题匹配 wp_code 模式)
    - **Property 6: 推荐问题匹配 wp_code 模式**
    - **Validates: Requirements 4.8**
    - 文件: `backend/tests/test_recommended_questions_pbt.py`
    - `@settings(max_examples=5)`

  - [x]* 3.4 Write property test (Property 11: 复杂度分类确定性)
    - **Property 11: 复杂度分类确定性**
    - **Validates: Requirements 7.1**
    - 文件: `backend/tests/test_complexity_classification_pbt.py`
    - `@settings(max_examples=5)`

- [x] 4. 前端面板骨架 WpGuidancePanel
  - [x] 4.1 创建 Pinia store `frontend/src/stores/guidancePanelStore.ts`
    - `useGuidancePanelStore`：isOpen / activeTab / wpContext / guidanceData / guidanceLoading / aiEnabled
    - localStorage 持久化展开/折叠状态
    - sessionStorage 缓存 guidanceData（按 wp_code 键）
    - _Requirements: 1.6, 8.4_

  - [x] 4.2 创建 `frontend/src/components/workpaper/WpGuidancePanel.vue`
    - 固定右侧面板（360~420px），展开/折叠动画
    - PanelHeader（折叠按钮 + 标题）
    - TabContainer：「编制说明」/「AI 对话」Tab
    - PanelTrigger（折叠态图标按钮）
    - `WP_AI_SERVICE_ENABLED=false` 时隐藏 AI Tab
    - 主编辑区宽度自适应收缩（非遮挡）
    - skeleton 占位（加载超 3s）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 8.5_

  - [x] 4.3 实现编制说明 Tab 渲染
    - SourceBadge（来源标签：模板提取/知识库/通用提示）
    - GuidanceContent：结构化渲染 sections（分步骤/章节/层级）
    - TableOfContents：内容超一屏时显示目录锚点导航
    - wp_code 链接化（复用 GtIndexChip 跳转逻辑）
    - fallback 态淡化样式 + 提示「暂无专属编制说明」
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.4 在 WorkpaperEditorLayout 层集成面板
    - **⚠️ 先调研再实现**：用 codegraph 确认底稿编辑器的实际路由结构和 layout 组件位置
    - 确认注入位置（candidates: WorkpaperEditorView / GtWpRenderer / 路由 layout）
    - 面板与 renderer 同级并列（flex 布局），非嵌套
    - 传递 wpContext（wpId/wpCode/wpName/componentType/projectId/year）
    - 面板加载不阻塞底稿主体渲染（异步）
    - 实现底稿切换竞态防护（requestId + AbortController，需求 10）
    - _Requirements: 1.3, 1.8, 10.1, 10.2, 10.3, 10.4_

  - [x]* 4.5 Write vitest for WpGuidancePanel (Property 15: AI Tab 随功能开关隐藏)
    - **Property 15: AI Tab 随功能开关隐藏**
    - **Validates: Requirements 1.7**
    - 文件: `frontend/src/components/workpaper/__tests__/WpGuidancePanel.spec.ts`

- [x] 5. Phase 0 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 验证：面板骨架可展开/折叠，编制说明从模板正确提取并渲染，无 LLM 依赖

### Phase 1: LLM 对话 + 上下文注入（合并原 P1+P2 核心）

- [x] 6. 实现 ContextInjector + AI 对话后端端点
  - [x] 6.1 创建 `backend/app/services/context_injector.py`
    - `build_system_prompt(wp_context: WpChatContext)` → 单条 system prompt
    - SYSTEM_TEMPLATE 填充：wp_code/wp_name/component_type/client_name/audit_period/business_category/guidance_text/filled_data_summary
    - `_build_filled_data_summary`：审定表→科目名+金额前10行；程序表→已完成/总步骤数；其他→非空字段数/总字段数
    - `_truncate_to_tokens(text, max_tokens=2000)`：按完整行截断
    - `merge_system_messages`：多条 system → 单条（vLLM 约束）
    - **token 预算总控**：system prompt 总量 ≤ 4000 tokens（guidance_text ≤ 1500, filled_data ≤ 2000）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 6.2 在 `wp_guidance_chat.py` 添加 `POST /api/workpapers/{wp_id}/ai-chat` 端点
    - 请求体验证：query / project_id / year / wp_code / wp_name（缺必填字段 422）
    - 调用 ContextInjector 构建 system prompt → 注入底稿上下文
    - 复用 `doc_ai_chat` 管线的 `_stream_chat` 模式
    - SSE 响应格式：citations → content(多条) → done
    - DB 持久化：复用 `doc_chat_persistence`，`doc_type="workpaper"`，定位键 `workpaper:{wp_id}:{user_id}`
    - 无效 wp_id 返回 404，LLM 熔断器 open 返回 503
    - _Requirements: 4.2, 4.3, 4.6, 5.1, 9.1, 9.2, 9.3, 9.5_

  - [x]* 6.3 Write property tests for ContextInjector (Properties 7, 8, 9, 10)
    - 文件: `backend/tests/test_context_injector_pbt.py`
    - `@settings(max_examples=5)`

  - [x]* 6.4 Write property test (Property 13: 请求体缺必填字段返回 422)
    - 文件: `backend/tests/test_wp_ai_chat_pbt.py`
    - `@settings(max_examples=5)`

- [x] 7. 实现对话历史持久化
  - [x] 7.1 集成 `doc_chat_persistence` 模块
    - `append_message` / `get_history` / `clear_history`
    - 会话维度：`workpaper:{wp_id}:{user_id}`
    - 历史上限 20 轮
    - _Requirements: 4.6, 4.7, 9.6_

  - [x]* 7.2 Write property test (Property 5: 对话历史持久化往返)
    - **Property 5: 对话历史持久化往返**
    - **Validates: Requirements 4.6, 4.7, 9.6**
    - 文件: `backend/tests/test_wp_chat_persistence_pbt.py`
    - `@settings(max_examples=5)`

- [x] 8. 前端 AI 对话 Tab 实现
  - [x] 8.1 实现 AI 对话 UI 组件
    - MessageList：历史消息 + streaming 渲染
    - ChatInput：输入框 + 发送按钮
    - RecommendedQuestions：快捷按钮（从 guidance 响应取）
    - SSE 消费（EventSource / fetch ReadableStream）
    - 打字动画指示器（streaming 态）
    - 「清除对话」按钮
    - LLM 不可用时禁用输入框 + 提示「AI 服务暂不可用」
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.7, 4.8_

- [x] 9. Phase 1 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 验证：AI Tab 可发消息，SSE 流式接收回答，对话历史持久化，熔断器降级正确

### Phase 2: RAG 知识库增强

- [x] 10. 集成 RAG 知识库检索
  - [x] 10.1 在 ai-chat 端点集成 `KnowledgeIndexService.semantic_search`
    - 检索参数：wp_code + 用户问题，scope="knowledge_doc"，top_k=5
    - 降级链：向量检索 → BM25 → ilike（复用现有链路）
    - 检索结果作为 citations SSE 事件返回
    - 注入到 LLM 上下文（每条 RAG hit ≤ 500 tokens 截断）
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [x]* 10.2 Write property test (Property 16: 知识库检索结果上限)
    - 文件: `backend/tests/test_wp_ai_chat_pbt.py`
    - `@settings(max_examples=5)`

- [x] 11. 前端引用来源展示
  - [x] 11.1 实现 CitationList 组件
    - 在 AI 回答下方显示引用来源列表（准则名/文件名 + 可展开段落预览）
    - 点击引用来源跳转知识库文档详情页
    - _Requirements: 6.4, 6.5_

- [x] 12. Phase 2 Checkpoint
  - 验证：RAG 检索正确注入引用，引用来源前端展示正确

### Phase 3: 全量覆盖优化

- [x] 13. 复杂度自适应渲染
  - [x] 13.1 实现前端复杂度自适应逻辑
    - 高复杂度：完整编制说明 + 推荐问题 + RAG 引用
    - 中复杂度：编制说明摘要 + 推荐问题
    - 低复杂度：简短提示（1~2 行）+ 仅 AI 对话入口
    - 读取 `complexity` 字段控制渲染深度
    - _Requirements: 7.2, 7.3, 7.4_

  - [x]* 13.2 Write property test (Property 12: 内容深度随复杂度缩放)
    - **Property 12: 内容深度随复杂度缩放**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - 文件: `backend/tests/test_guidance_service_pbt.py`
    - `@settings(max_examples=5)`

- [x] 14. SSE 流式协议完整性保障
  - [x] 14.1 确保 SSE 协议合规 + 部分响应持久化
    - 所有成功对话以 `done` 事件结尾
    - `content` 事件拼接 = DB 中 assistant 消息文本
    - streaming 中断：已收集部分作为 partial response 存 DB
    - _Requirements: 4.3, 9.3_

  - [x]* 14.2 Write property test (Property 4: SSE 流式协议合规)
    - **Property 4: SSE 流式协议合规**
    - **Validates: Requirements 4.3, 9.3**
    - 文件: `backend/tests/test_wp_ai_chat_pbt.py`
    - `@settings(max_examples=5)`

- [x] 15. 性能优化与错误边界
  - [x] 15.1 前端性能与容错
    - 面板组件懒加载（dynamic import）
    - Vue errorBoundary 隔离（面板异常不影响底稿主体）
    - sessionStorage 缓存 guidance（按 wp_code）
    - 超 3s skeleton → 后台继续加载
    - _Requirements: 8.4, 8.5, 8.6_

  - [x] 15.2 后端超时与降级
    - 模板解析 5 秒超时（`asyncio.wait_for`）
    - python_calamine 异常 → 降级到 header → json → fallback
    - LLM 熔断器 open → SSE `{"type":"error","data":"AI 服务暂不可用"}`
    - _Requirements: 8.6_

- [x] 16. 编制说明可编辑预留（P3/P4 过渡）
  - 在「编制说明」Tab 底部渲染「补充说明」区域骨架（el-input textarea，默认折叠）
  - 读取 field_overrides scope="wp_guidance_custom:{wp_code}:{project_id}" 如有则展示
  - 保存逻辑标注 TODO（P4 实现），当前只读展示已有 customized_guidance
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 17. Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 验证：全量底稿均有编制指导入口，复杂度自适应正确，缓存命中率合理，错误边界隔离有效

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端测试运行: `.venv\Scripts\python.exe -m pytest`，加 `rtk` 前缀
- 前端测试运行: `npx vitest run`，加 `rtk` 前缀
- hypothesis PBT 统一 `@settings(max_examples=5)`（用户偏好）
- 所有用户可见文本中文
- 面板在 layout 层集成，兼容所有 componentType
