# 需求文档：doc-level-ai-chat（文档/文件夹级 LLM 知识库对话）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§二十二/§二十三）
> 工作流：Design-First（从 design.md 派生反推）
> 设计：#[[file:.kiro/specs/doc-level-ai-chat/design.md]]
> **前置依赖**：retrieval-kernel-unification spec（检索内核 + 知识文件入网）

## 引言

平台最实用核心功能：把知识库从"存文件"变"随时可问的专家"。任意文档/文件夹都能发起 AI 对话，自动注入当前文档 + 关联知识库（同行业/同模板/同科目）作 RAG 上下文。审计师在任何程序中"问 AI"加速填写、核对、对比。

不重复造轮子：复用 semantic_search（检索）+ ai_service（LLM）+ wrap_ai_output_with_log（留痕确认流）；新建 ContextBuilder + 前端可嵌入对话面板。

## 需求

### 需求 1：任意文档/文件夹级对话入口

**用户故事**：作为审计师，我在底稿/附注/报表/知识库文件夹任意页面都能点「AI 对话」发起带上下文的提问。

#### 验收标准

1. WHEN 用户在底稿/附注/报表/知识库文件夹页面 THEN 有「AI 对话」入口（右键或工具栏）
2. WHEN 用户发起对话 THEN 自动注入当前文档内容（parsed_data / content_text）作上下文
3. WHEN 对话面板打开 THEN 可嵌入任意页面（Drawer/Panel 形式）
4. WHEN 文件夹级对话 THEN 注入该文件夹下文档集合作上下文

### 需求 2：自动注入关联知识（RAG）

**用户故事**：作为审计师，我提问时系统自动检索关联知识库（同行业/同模板/同科目），不需要手动复制粘贴参考资料。

#### 验收标准

1. WHEN ContextBuilder 构建上下文 THEN 调 `semantic_search` 检索关联知识（按科目/行业/循环）
2. WHEN 用户想加额外参考 THEN 可 @mention 选指定文件夹/标签（extra_scopes）
3. WHEN 知识文档很大 THEN token 预算内 chunk + 相关性排序 + 截断（top_k 最相关段落，非全文塞入）
4. IF ContextBuilder 输出 THEN token_estimate ≤ 配置上限

### 需求 3：引用来源可追溯

**用户故事**：作为审计师，AI 回答时我能看到引用了哪个知识文件/哪个底稿，可以验证。

#### 验收标准

1. WHEN AI 回答 THEN 标注引用来源（知识文件 id + 段落 / 底稿 wp_code）
2. WHEN 用户点引用来源 THEN 可跳转到该知识文件/底稿
3. IF 每条 knowledge_hit THEN 必带可定位的 source（文件 id + 段落）

### 需求 4：AI 内容确认流回写

**用户故事**：作为审计师，AI 生成的内容我确认后才写入底稿/附注，不会被 AI 直接改数据。

#### 验收标准

1. WHEN 用户点「采纳」AI 内容 THEN 经 `AIContentMustBeConfirmedRule` 走确认流（pending 状态）
2. WHEN AI 内容回写 THEN 调 `wrap_ai_output_with_log` 留痕（ai_content_log）
3. IF AI 生成内容未确认 THEN 不直接写入底稿/附注

### 需求 5：权限继承与离线

**用户故事**：作为系统，我要求对话只检索用户有权访问的知识文件，且对话历史断网可查。

#### 验收标准

1. WHEN ContextBuilder 检索 THEN 只含 user 有权访问的知识文件（权限继承）
2. WHEN 对话历史 THEN 本地缓存（断网可查历史，不可发新问）
3. WHEN LLM 调用 THEN streaming 响应（复用 ai_service）

### 非功能需求

- **NFR-1 复用优先**：复用 semantic_search/ai_service/wrap_ai_output_with_log，禁止重造 RAG/LLM/留痕
- **NFR-2 依赖前置**：依赖 retrieval-kernel-unification 的 semantic_search（含知识文件入网）
- **NFR-3 token 预算**：上下文 token 不超模型 context window
- **NFR-4 合规**：AI 内容必经确认流（CAS 1131 + AI 溯源）

## 正确性属性（PBT 守护）

- **D1 token 预算不超限**：ContextBuilder 输出 token_estimate ≤ 配置上限
- **D2 权限隔离**：对话上下文只含 user 有权访问的知识文件
- **D3 引用可追溯**：每条 knowledge_hit 必带可定位 source
- **D4 确认流门禁**：AI 生成内容回写前必经 AIContentMustBeConfirmedRule（pending）
