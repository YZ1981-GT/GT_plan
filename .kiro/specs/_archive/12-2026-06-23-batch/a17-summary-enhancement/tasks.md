# Implementation Plan: A17-1 重大事项概要深度打磨

## Overview

将 A17-1 重大事项概要从纯文本编辑器升级为富文本 HTML 编辑器，并新增跨章节一致性校验、LLM 生成增强（跨章上下文 + 润色模式）、A17-2 KAM 集成至 ch12、以及 A17 子文档快速导航。前端基于 contenteditable + DOMPurify 轻量方案，后端基于 FastAPI + hypothesis 属性测试。

## Tasks

- [x] 1. 前端基础设施：HTML 消毒 + wp_code 解析 composables
  - [x] 1.1 实现 `useSanitize` composable（DOMPurify 封装）
    - 创建 `frontend/src/composables/useSanitize.ts`
    - 封装 DOMPurify.sanitize，允许 h3/h4/ul/ol/li/table/tr/td/th/strong/em/br/p 标签
    - 剥离 script/iframe/object/embed 标签及所有 on* 事件属性
    - 导出 `sanitizeHtml(raw: string): string` 函数
    - _Requirements: 1.3, 1.4_

  - [x] 1.2 实现 `useWpCodeParser` composable（正则解析 wp_code）
    - 创建 `frontend/src/composables/useWpCodeParser.ts`
    - 正则 `[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?` 提取文本中所有 wp_code
    - 实现 `parseSourceLabel(label: string): string[]` 按 `+` 分割 source_label
    - _Requirements: 2.1, 2.4_

  - [x] 1.3 实现 `useA17Navigation` composable（wp_code 跳转逻辑）
    - 创建 `frontend/src/composables/useA17Navigation.ts`
    - 封装 wp_code → wpId 查找（复用 getWpIndex API）+ router.push 跳转
    - 处理 wp_code 不存在情况（返回 disabled 状态）
    - _Requirements: 2.2, 2.3_

  - [x]* 1.4 为 useSanitize 编写属性测试（fast-check）
    - **Property 1: HTML 消毒保留安全标签并剥离危险标签**
    - **Validates: Requirements 1.3, 1.4**

  - [x]* 1.5 为 useWpCodeParser 编写属性测试（fast-check）
    - **Property 4: wp_code 正则解析完备性**
    - **Validates: Requirements 2.1**

  - [x]* 1.6 为 parseSourceLabel 编写属性测试（fast-check）
    - **Property 6: source_label 分割正确性**
    - **Validates: Requirements 2.4**

- [x] 2. 前端组件：富文本编辑器 + RefChip
  - [x] 2.1 实现 `A17RichTextEditor.vue` 富文本编辑器组件
    - 创建 `frontend/src/views/workpaper/a17/A17RichTextEditor.vue`
    - 基于 contenteditable div + 轻量 toolbar（h3/h4、列表、加粗、斜体、表格插入）
    - paste handler 中调用 useSanitize 即时清洗粘贴内容
    - 遵循 isInternalChange guard 防止 focus/blur 竞争（踩坑铁律）
    - 纯文本兼容：检测内容无 HTML 标签时自动将 `\n` 转为 `<br>`
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [x] 2.2 实现 `RefChipInline.vue` 行内引用芯片组件
    - 创建 `frontend/src/views/workpaper/a17/RefChipInline.vue`
    - Props: wp_code, disabled, tooltip
    - 可点击时 router.push 跳转；禁用态灰色 + tooltip "该底稿在当前项目中不存在"
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.3 在 A17RichTextEditor 中集成 wp_code 自动检测与 RefChip 渲染
    - 渲染模式：解析 chapter content 中的 wp_code 模式，替换为 RefChipInline 组件
    - 编辑模式：支持 `@` 快捷输入 + wp_code 自动补全插入 RefChip
    - source_label 区域：按 `+` 分割后各段独立渲染为 RefChip
    - _Requirements: 2.1, 2.4, 2.5_

  - [x]* 2.4 为 RefChip 可用性逻辑编写属性测试（fast-check）
    - **Property 5: Ref_Chip 可用性由 wp_index 决定**
    - **Validates: Requirements 2.3, 6.3, 6.4**

  - [x]* 2.5 为纯文本兼容渲染编写属性测试（fast-check）
    - **Property 2: 纯文本兼容渲染保留换行**
    - **Validates: Requirements 1.5**

- [x] 3. 改造 GtA17Summary.vue 主容器集成富文本编辑器
  - 替换原 textarea/纯文本编辑为 A17RichTextEditor 组件
  - 保存时调用 useSanitize 清洗后写入 checklist_responses.remark
  - 加载时自动检测纯文本/HTML 并兼容渲染
  - 集成 source_label 区域 RefChip 渲染
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.4_

- [x] 4. Checkpoint - 富文本编辑器基础功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 后端：跨章节一致性校验
  - [x] 5.1 创建一致性规则 JSON 配置文件
    - 创建 `backend/data/a17_consistency_rules.json`
    - 包含 4 条规则：gc_vs_opinion、kam_required_listed、fraud_vs_opinion、risk_vs_opinion
    - _Requirements: 3.2_

  - [x] 5.2 实现 `a17_consistency_checker.py` 校验引擎
    - 创建 `backend/app/services/a17_consistency_checker.py`
    - 加载规则 JSON，遍历章节内容执行正则匹配
    - 支持 project.business_category 条件判断
    - 返回 `List[ConsistencyResult]`（rule_id, severity, affected_chapters, description）
    - business_category 为 null 时跳过依赖此字段的规则
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

  - [x] 5.3 新增 `POST /api/a17/consistency-check` 端点
    - 在 `backend/app/routers/a17_summary.py` 中新增路由
    - 接收 project_id + wp_id，查询 16 章内容，调用 checker，返回结果
    - _Requirements: 3.1_

  - [x]* 5.4 为一致性规则引擎编写属性测试（hypothesis）
    - **Property 7: 一致性校验规则引擎正确触发**
    - **Validates: Requirements 3.2, 3.3, 3.6**

  - [x]* 5.5 为一致性校验输出编写 schema 属性测试（hypothesis）
    - **Property 8: 一致性校验输出 schema 不变式**
    - **Validates: Requirements 3.3**

- [x] 6. 前端：一致性校验面板组件
  - [x] 6.1 实现 `ConsistencyPanel.vue` 校验结果展示面板
    - 创建 `frontend/src/views/workpaper/a17/ConsistencyPanel.vue`
    - 可折叠面板，按 severity 分组（error → warning → info）
    - 章节引用渲染为可点击链接，导航到对应章节
    - 无问题时显示成功指示器
    - _Requirements: 3.4, 3.5, 3.6_

  - [x] 6.2 在 GtA17Summary.vue 工具栏集成一致性校验触发按钮
    - 工具栏新增"一致性校验"按钮
    - 点击后调用 POST /api/a17/consistency-check
    - 结果传递给 ConsistencyPanel 展示
    - _Requirements: 3.1_

- [x] 7. 后端：LLM 生成增强（跨章上下文 + 润色模式）
  - [x] 7.1 改造 `a17_llm_service.py` 增加跨章上下文收集
    - 添加 CHAPTER_AFFINITY 静态配置
    - 实现 `build_cross_chapter_context(target_chapter, all_chapters, budget)` 方法
    - 优先包含 affinity 矩阵中的关联章节，超 budget 时截断
    - _Requirements: 4.1, 4.5_

  - [x] 7.2 改造 `a17_llm_service.py` 支持 polish 模式
    - AI 生成端点 Body 新增 `mode: "generate" | "polish"` 字段
    - mode="polish" 时 prompt 包含当前章节内容 + 润色指令
    - mode="generate" 时 prompt 不含当前章节内容（现有行为）
    - prompt 始终包含 project industry 和 audit_period_end
    - _Requirements: 4.2, 4.3, 4.6_

  - [x]* 7.3 为跨章上下文构建编写属性测试（hypothesis）
    - **Property 9: LLM 跨章上下文构建完备性**
    - **Validates: Requirements 4.1, 4.5**

  - [x]* 7.4 为 prompt 构建编写属性测试（hypothesis）
    - **Property 10: LLM 生成模式 prompt 构建**
    - **Validates: Requirements 4.2, 4.3, 4.6**

- [x] 8. 前端：AI 生成对话框模式选择
  - 改造 A17 AI 生成对话框，新增 generate/polish 模式选择器
  - 默认值逻辑：章节内容为空 → "generate"，已有内容 → "polish"
  - 调用时传递 mode 参数到后端
  - _Requirements: 4.4_

  - [x]* 8.1 为 AI 模式默认值逻辑编写属性测试（fast-check）
    - **Property 11: AI 模式默认值由内容状态决定**
    - **Validates: Requirements 4.4**

- [x] 9. Checkpoint - 一致性校验 + LLM 增强验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 前端+后端：A17-2 KAM 集成至 ch12
  - [x] 10.1 实现 `KamEmbedPanel.vue` KAM 嵌入面板
    - 创建 `frontend/src/views/workpaper/a17/KamEmbedPanel.vue`
    - 展示 A17-2-1 KAM 条目列表（title、description、wp_refs 渲染为 RefChip）
    - 点击条目跳转至 A17-2-1 对应条目
    - A17-2-1 不存在时显示占位提示
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x] 10.2 在 GtA17Summary.vue 中 ch12 激活时展示 KamEmbedPanel
    - ch12 为活动章节时渲染 KamEmbedPanel
    - 支持手动刷新 KAM 数据
    - _Requirements: 5.1, 5.4_

- [x] 11. 前端+后端：A17 子文档快速导航
  - [x] 11.1 新增 `GET /api/a17/sub-documents` 后端端点
    - 查询项目 wp_index 中 A17-2 ~ A17-7 的存在状态
    - 返回 `SubDocItem[]`（wp_code, label, exists, wp_id）
    - _Requirements: 6.5_

  - [x] 11.2 实现 `SubDocNavigator.vue` 子文档导航栏组件
    - 创建 `frontend/src/views/workpaper/a17/SubDocNavigator.vue`
    - 横向导航栏列出 A17-2 ~ A17-7（KAM/业务咨询/分歧记录/完成核对表/总结会/独立性声明）
    - 已创建：可点击跳转；未创建：禁用 + tooltip
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 11.3 在 GtA17Summary.vue 集成 SubDocNavigator
    - 在章节导航上方或侧边渲染 SubDocNavigator
    - 页面加载时调用 sub-documents API 获取状态
    - _Requirements: 6.1_

  - [x]* 11.4 为子文档导航可用性映射编写属性测试（fast-check）
    - **Property 12: 子文档导航可用性映射**
    - **Validates: Requirements 6.3, 6.4, 6.5**

- [x] 12. 后端：Word 导出 HTML→docx 转换增强
  - [x] 12.1 改造 `a17_word_exporter.py` 支持 HTML 章节内容导出
    - h3/h4 → Heading 样式段落
    - ul/ol → 列表段落
    - strong → bold run，em → italic run
    - table → Table 对象
    - 不支持的标签静默跳过
    - _Requirements: 1.6_

  - [x] 12.2 Word 导出时自动触发一致性校验
    - export-word 流程中调用 consistency_checker
    - 有 error 级别结果时提示用户（不阻断导出）
    - _Requirements: 3.1_

  - [x]* 12.3 为 HTML→Word 导出编写属性测试（hypothesis）
    - **Property 3: HTML→Word 导出保留结构元素**
    - **Validates: Requirements 1.6**

- [x] 13. Final checkpoint - 全功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 前端使用 fast-check 进行属性测试，后端使用 hypothesis（项目已有 .hypothesis/ 目录）
- contenteditable 组件必须遵循 isInternalChange guard 防止 focus/blur 竞争（踩坑铁律）
- 存量纯文本数据无需迁移，自动兼容渲染（\n → <br>）
- 一致性校验 API 失败不阻断编辑流程
