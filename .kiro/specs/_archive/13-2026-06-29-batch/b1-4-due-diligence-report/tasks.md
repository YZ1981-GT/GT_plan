# Implementation Plan: B1-4 尽职调查报告专属组件

## Overview

将 B1-4 从 word-template 升级为专属精美展示组件，采用 A17-1 验证过的多章卡片+左侧导航+debounce保存模式。实现 11~13 章卡片式结构化视图、标准版/简化版双变体切换、LLM 知识库辅助生成。

前端：TypeScript + Vue 3 Composition API + Element Plus
后端：Python + FastAPI

## Tasks

- [x] 1. 注册 componentType 并创建后端渲染策略
  - [x] 1.1 注册 `b1-4-due-diligence-report` 到 VALID_COMPONENT_TYPES（wp_classification_service.py）
    - 在 VALID_COMPONENT_TYPES 集合中新增条目
    - 在 wp_code_overrides.json 中将 B1-4 映射到 `b1-4-due-diligence-report`
    - _Requirements: 1.1_

  - [x] 1.2 实现后端渲染策略 `_b14_due_diligence.py`
    - 创建 `backend/app/workpapers/renderers/_b14_due_diligence.py`
    - 实现 `render(ctx: RenderContext)` 函数：从 checklist_responses 加载 `b14-*` 记录
    - 组装 chapters / variant / signature / project_context 输出结构
    - 从 projects 表加载 client_name / industry / audit_period / firm_name
    - 在 RENDERER_DISPATCH 中注册该渲染策略
    - _Requirements: 7.1, 7.2, 7.3_

  - [x]* 1.3 Write property tests for render function (hypothesis)
    - **Property 7: Render function produces well-structured output**
    - 生成随机 checklist_responses 行（b14-* item_id），验证 render 输出包含 chapters/variant/signature/project_context 且结构完整
    - **Validates: Requirements 7.2**

  - [x]* 1.4 Write property test for B14RenderData round-trip (hypothesis)
    - **Property 6: B14RenderData serialization round-trip**
    - 生成随机 B14RenderData 对象，验证 JSON 序列化→反序列化等价
    - **Validates: Requirements 7.4**

- [x] 2. Checkpoint - 后端渲染策略验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 实现前端 composables
  - [x] 3.1 实现 `useB14DueDiligence.ts` composable
    - 创建 `frontend/src/views/workpapers/composables/useB14DueDiligence.ts`
    - 实现 hydrate 逻辑：从 htmlData 初始化 chapters reactive state
    - 实现 selfLoad 逻辑：htmlData 为 null 时调用 render-config?force_component_type=b1-4-due-diligence-report
    - 实现 updateTextarea / updateTableRows / addTableRow / removeTableRow
    - 实现 setVariant（持久化到 b14-meta-variant）
    - 实现 updateSignature（item_id=b14-signature-{field}）
    - 实现 2s debounce 自动保存 + flushPendingSaves
    - 实现 saveStatus 状态管理（saved/saving/unsaved）
    - _Requirements: 1.6, 5.1, 5.2, 5.3, 5.4, 5.5, 4.4, 9.3_

  - [x] 3.2 实现 `useB14Navigation.ts` composable
    - 创建 `frontend/src/views/workpapers/composables/useB14Navigation.ts`
    - 实现 IntersectionObserver scrollspy 高亮当前章节
    - 实现 scrollToChapter 平滑滚动
    - 实现 completionStatus 计算（per chapter 填写状态）
    - 实现 overallProgress 百分比（已填可见章节 / 总可见章节 × 100）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.3 Write property tests for variant visibility (fast-check)
    - **Property 1: Variant controls chapter visibility**
    - 对任意 variant 值验证 visible chapters 集合：simplified 隐藏 ch11/ch12，standard 全显示
    - **Validates: Requirements 2.2, 4.2**

  - [x]* 3.4 Write property test for variant switch data preservation (fast-check)
    - **Property 2: Variant switch preserves chapter data**
    - 生成随机 chapter data + 随机 variant 切换序列，验证数据内容不变仅 visible 变化
    - **Validates: Requirements 4.3**

  - [x]* 3.5 Write property test for completion computation (fast-check)
    - **Property 3: Completion status computation**
    - 生成随机 chapter data 状态，验证 completionStatus 和 overallProgress 计算正确
    - **Validates: Requirements 3.4, 3.5**

  - [x]* 3.6 Write property test for item_id format (fast-check)
    - **Property 4: item_id format correctness**
    - 生成随机 chapter number + field name + signature field，验证 item_id 匹配 `b14-ch{N}-{field_id}` / `b14-signature-{field}` / `b14-meta-variant` 模式
    - **Validates: Requirements 5.2, 9.3**

  - [x]* 3.7 Write property test for table JSON round-trip (fast-check)
    - **Property 5: Table data JSON round-trip**
    - 生成随机 table rows（对象数组含 string/number/null），验证 JSON.stringify→JSON.parse 等价
    - **Validates: Requirements 5.5**

- [x] 4. Checkpoint - Composables 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 实现 Vue 组件
  - [x] 5.1 实现 `GtB14DueDiligenceReport.vue` (~400 行)
    - 创建 `frontend/src/views/workpapers/components/GtB14DueDiligenceReport.vue`
    - Toolbar：el-segmented 模式切换（结构化视图/在线编辑）+ el-segmented 变体切换（标准版/简化版）+ 保存状态
    - Layout：左侧导航 180px sticky + 右侧内容区 el-collapse 11~13 章卡片
    - 章节卡片：textarea 型（el-input type=textarea）/ table 型（el-table 行内编辑 + 增删行）/ mixed 型（el-divider 子节）
    - 默认展开 ch1 + ch2
    - 签字区卡片：partner/manager 签名 + 日期
    - GtIndexChip：ch6→B15 / ch9→B22A / ch13→B50
    - GtOnlyOfficeSheet 在线编辑模式（OO 健康检查失败则隐藏）
    - selfLoad 逻辑（htmlData=null 时 onMounted 自加载）
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.2, 4.3, 4.5, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 10.1, 10.2, 10.3, 10.4_

  - [x] 5.2 注册到 htmlRendererRegistry
    - 在 `htmlRendererRegistry.ts` 中注册 `b1-4-due-diligence-report` → GtB14DueDiligenceReport 组件映射
    - _Requirements: 1.1_

  - [x]* 5.3 Write unit tests for composables (vitest)
    - hydrate 从 htmlData 正确初始化 chapters
    - updateTextarea 触发 pendingItems + scheduleSave
    - addTableRow / removeTableRow 修改 rows
    - setVariant 持久化 b14-meta-variant
    - selfLoad 在 htmlData=null 时调用 render-config
    - OO 健康检查失败 → modeOptions 仅保留结构化视图
    - flushPendingSaves 在模式切换前被调用
    - 签字区 updateSignature 生成正确 item_id
    - 默认展开 ch1+ch2
    - _Requirements: 1.4, 1.5, 1.6, 5.1, 5.4, 7.2, 9.3, 2.3_

- [x] 6. Checkpoint - 前端组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. LLM 内容生成集成
  - [x] 7.1 实现后端 AI 生成端点
    - 新增 `POST /api/projects/{project_id}/b14/chapters/{chapter_id}/ai-generate`
    - 接收 body: { mode: "generate"|"polish", user_hint, current_content }
    - 通过 ReferenceDocService.load_from_knowledge_base 检索知识库文档（最多 3 篇）
    - 构造尽调报告专属 system prompt（含 CPA 行业格式规范）
    - 注入 project_context + 跨章节摘要 + 知识库参考
    - 调用 vLLM 生成并返回 { draft, model, confidence, error }
    - LLM 服务不可用时返回 503 + error 消息
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 7.2 前端 AI 按钮集成
    - 在每个 textarea 型章节右上角显示"🤖 AI 生成"按钮
    - 点击后调用 ai-generate 端点
    - 生成完成后 el-dialog 展示建议稿，用户确认后填入
    - 支持 generate（从头生成）和 polish（润色）两种模式
    - LLM 不可用时按钮 disabled + tooltip 提示
    - _Requirements: 6.1, 6.5, 6.6, 6.7_

  - [x]* 7.3 Write property test for LLM prompt context (hypothesis)
    - **Property 8: LLM prompt includes required context sections**
    - 生成随机 chapter_id / project_context / knowledge_docs(0-3) / cross-chapter summaries，验证 prompt 包含章节标题、知识库文档、项目信息、current_content(polish mode)
    - **Validates: Requirements 6.4**

  - [x]* 7.4 Write backend integration tests for AI endpoint
    - 测试正常调用返回正确 schema
    - 测试知识库无匹配文档时继续生成（不报错）
    - 测试 LLM 超时/500 返回 503 + error
    - _Requirements: 6.2, 6.3, 6.7_

- [x] 8. Checkpoint - LLM 集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 契约测试与注册完整性验证
  - [x] 9.1 更新 htmlRendererRegistry.spec.ts 契约测试
    - 在 expected componentType 列表中新增 `b1-4-due-diligence-report`
    - 确保契约测试通过
    - _Requirements: 1.1_

  - [x] 9.2 更新 VALID_COMPONENT_TYPES 契约测试
    - 确保后端 validate_overrides 启动时不 raise ValueError
    - _Requirements: 1.1_

- [x] 10. Playwright E2E 验证
  - [x]* 10.1 E2E: 打开 B1-4 显示结构化视图
    - 验证打开 B1-4 底稿后看到结构化视图 + 11 章卡片
    - _Requirements: 1.2, 2.1_

  - [x]* 10.2 E2E: 变体切换显示/隐藏章节
    - 切换到简化版验证 ch11/ch12 隐藏，切回标准版验证恢复
    - _Requirements: 4.2_

  - [x]* 10.3 E2E: 编辑 textarea 自动保存
    - 编辑章节 textarea → 等待 2s → 验证保存状态变为 ✓
    - _Requirements: 5.1, 5.3_

  - [x]* 10.4 E2E: 表格行增删
    - 验证添加行、删除行功能正常
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 11. Final checkpoint - 全量验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 架构参照已验证的 A17-1 模式（多章卡片+左侧导航+debounce保存）
- LLM 集成（Task 7）可先以 disabled 占位实现，待 vLLM 服务就绪后激活
- selfLoad 逻辑确保 bundle 内嵌场景不会空白（踩坑铁律）
- Property tests 使用 fast-check（前端）和 hypothesis（后端）
- 注册顺序：VALID_COMPONENT_TYPES → overrides → RENDERER_DISPATCH → htmlRendererRegistry
