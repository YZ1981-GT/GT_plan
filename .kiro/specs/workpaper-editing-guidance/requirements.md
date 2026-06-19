# 底稿编制指导助手 — 需求文档

## 概述

所有底稿在编制填充时，增加「编制说明」功能——右侧浮动面板展示编制指引、LLM 对话、知识库引用，帮助审计人员理解当前底稿的填写要求和操作步骤。面板可折叠/展开，不遮挡底稿主体编辑区。

## 设计原则

- 全量覆盖：所有底稿都有编制指导入口（复杂度不同，内容深度自适应）
- 静态优先：编制说明从模板提取为主，RAG 检索为辅，LLM 生成仅在对话时触发
- 不阻塞主流程：面板加载不影响底稿主体渲染，LLM 可选（`WP_AI_SERVICE_ENABLED` 控制）
- 复用已有管线：LLM 对话复用 `doc_ai_chat` 管线，RAG 复用 `knowledge_base` 模块
- **上下文从第一天就注入**：LLM 对话一上线就带底稿上下文（不分 P1/P2），用户第一次对话就能感受到"AI 理解当前底稿"
- **token 预算约束**：system prompt 总量不超 4000 tokens（guidance_text ≤ 1500, RAG hits ≤ 500/条, filled_data ≤ 2000），防止 context window 浪费降低回答质量

## 术语表

- **Guidance_Panel**：底稿编辑界面右侧浮动面板组件（`WpGuidancePanel.vue`）
- **Guidance_Service**：后端编制说明提取服务（扩展现有 `wp_guidance_service.py`）
- **Template_Extractor**：从 xlsx/docx 模板文件中提取「编制说明」sheet 或首行说明文本的解析器
- **Guidance_Cache**：按 `wp_code` + 模板 mtime 缓存编制说明提取结果
- **Context_Injector**：LLM 对话时自动注入底稿上下文（wp_code/wp_name/已填数据摘要/编制说明文本）的组件
- **Knowledge_RAG**：知识库 RAG 检索模块（BM25 + 向量检索，降级 ilike）
## 阶段划分

| 阶段 | 范围 | 依赖 |
|------|------|------|
| P0 | 编制说明静态提取 + 面板骨架 + 种子数据验证 | wp_guidance_service + wp_templates |
| P1 | LLM 对话 + 上下文注入（合并） | doc_ai_chat 管线 + ContextInjector |
| P2 | RAG 知识库增强 + 引用展示 | knowledge_base.semantic_search |
| P3 | 全量覆盖优化（自适应复杂度 + 缓存 + 性能 + 可编辑预留） | P0~P2 完成 |**） | P0~P2 完成 |

> **阶段调整说明**：原设计 P1 纯对话 / P2 上下文+RAG 分离，复盘后合并——P1 交付时 LLM 对话即带底稿上下文注入（否则对话=通用 GPT 无场景价值）。RAG 检索作为 P2 单独增强（可独立于上下文注入）。VICE_ENABLED |
| P2 | RAG 增强 + 上下文注入 | knowledge_base.semantic_search |
| P3 | 全量覆盖优化（自适应复杂度 + 缓存 + 性能） | P0~P2 完成 |

---

## 需求

### 需求 1: 浮动面板入口与骨架（P0）

**用户故事**：作为审计人员，我想在底稿编辑界面右侧随时唤起编制指导面板，以便查阅填写指引而不离开当前编辑上下文。

#### 验收标准

1. THE Guidance_Panel SHALL 在底稿编辑界面右侧提供一个始终可见的唤起按钮（折叠态图标）
2. WHEN 用户点击唤起按钮, THE Guidance_Panel SHALL 从右侧滑入展示，宽度为 360~420px
3. WHEN 面板展开时, THE Guidance_Panel SHALL 不遮挡底稿主体编辑区（主编辑区宽度自适应收缩）
4. THE Guidance_Panel SHALL 包含两个 Tab：「编制说明」（静态指引）和「AI 对话」（动态问答）
5. WHEN 用户点击折叠按钮, THE Guidance_Panel SHALL 收起并恢复底稿编辑区全宽
6. THE Guidance_Panel SHALL 记住用户的展开/折叠状态（localStorage 持久化，按用户维度）
7. WHILE WP_AI_SERVICE_ENABLED 为 False, THE Guidance_Panel SHALL 隐藏「AI 对话」Tab，仅展示「编制说明」
8. THE Guidance_Panel SHALL 在底稿加载完成后异步加载编制说明内容（不阻塞底稿主体渲染）

### 需求 2: 编制说明静态提取（P0）

**用户故事**：作为审计人员，我想看到当前底稿的填写指引（从模板提取的编制说明），以便了解每个字段的填写规范和操作步骤。

#### 验收标准

1. WHEN 面板加载时, THE Guidance_Service SHALL 从 `backend/wp_templates/{cycle}/{file}.xlsx` 的「编制说明」sheet 提取指引文本
2. IF 模板文件无「编制说明」sheet, THEN THE Guidance_Service SHALL 从模板首行/首列说明文字提取指引
3. IF 模板文件无可提取的说明文本, THEN THE Guidance_Service SHALL 从 `backend/data/wp_guidance/{wp_code}.json` 静态配置文件读取
8. THE Guidance_Service SHALL 在响应中标注数据来源（template_sheet / template_header / static_json / fallback）
9. THE Guidance_Service SHALL 在 guidance 响应中附带 `ai_enabled` 布尔字段（从后端 `WP_AI_SERVICE_ENABLED` 配置读取），前端据此控制 AI Tab 可见性
5. THE Template_Extractor SHALL 解析「编制说明」sheet 中的分步骤说明（序号+内容），保持原始结构化格式
6. THE Guidance_Cache SHALL 按 `wp_code` 缓存提取结果，当模板文件 mtime 变化时自动失效
7. THE Guidance_Service SHALL 通过 `GET /api/workpapers/{wp_id}/guidance` 端点返回编制说明数据
8. THE Guidance_Service SHALL 在响应中标注数据来源（template_sheet / template_header / static_json / fallback）

### 需求 3: 编制说明前端渲染（P0）

**用户故事**：作为审计人员，我想在面板中以结构化方式阅读编制说明，以便快速定位到需要的填写指引段落。

#### 验收标准

1. THE Guidance_Panel SHALL 按原始结构渲染编制说明（分步骤、分章节、保留层级关系）
2. WHEN 编制说明超过一屏高度时, THE Guidance_Panel SHALL 提供目录锚点导航（可点击跳转到对应章节）
3. THE Guidance_Panel SHALL 对编制说明中的底稿编号引用（如 B60、D2-1）渲染为可点击的链接（复用 GtIndexChip 跳转逻辑）
4. WHEN 编制说明来源为 fallback 时, THE Guidance_Panel SHALL 显示淡化样式并提示「暂无专属编制说明」
5. THE Guidance_Panel SHALL 在编制说明 Tab 顶部显示数据来源标签（模板提取/知识库/通用提示）

### 需求 4: LLM 对话集成（P1）

**用户故事**：作为审计人员，我想在面板内针对当前底稿提问（如"这一步怎么填""这个数据从哪来"），以便获得即时的上下文相关回答。

#### 验收标准

1. THE Guidance_Panel SHALL 在「AI 对话」Tab 中提供聊天输入框和消息列表
2. WHEN 用户发送消息, THE Guidance_Panel SHALL 调用 `POST /api/workpapers/{wp_id}/ai-chat` 发起流式对话
3. THE LLM_Client SHALL 以 SSE 流式响应返回 AI 回答（复用 doc_ai_chat 管线的 `_stream_chat` 模式）
8. THE Guidance_Panel SHALL 在对话输入框下方提供 2~3 个推荐问题快捷按钮（基于 wp_code 预设）
9. THE Guidance_Service SHALL 支持推荐问题两级覆盖：`wp_guidance/{wp_code}.json` 中的 `recommended_questions` 字段优先于模式匹配通用问题（高优先级底稿如 A17/B60/B50/B51 手写专属推荐问题）
### 需求 5: LLM 上下文注入（P1，与对话同阶段交付）或 WP_AI_SERVICE_ENABLED=False）, THE Guidance_Panel SHALL 显示「AI 服务暂不可用」提示并禁用输入框
### 需求 5: LLM 上下文注入（P1，与对话同阶段交付）

**用户故事**：作为审计人员，我希望 AI 对话能理解当前底稿的完整上下文（编号/名称/已填数据/项目信息），以便给出精准的、与当前工作直接相关的回答。

#### 验收标准

1. THE Context_Injector SHALL 在每次对话时注入以下上下文到 system prompt：
   - 当前底稿的 wp_code + wp_name + componentType
   - 当前底稿的编制说明文本（需求 2 提取结果）
   - 当前项目基本信息（client_name, audit_period, business_category）
   - 当前底稿已填写数据的摘要
2. THE Context_Injector SHALL 对已填写数据摘要进行截断控制（不超过 2000 tokens）
3. WHEN 底稿为审定表类（D~N 循环 *-1 底稿）, THE Context_Injector SHALL 注入已填金额字段摘要（科目名+审定金额前 10 行）
4. WHEN 底稿为程序表类（*-A 底稿）, THE Context_Injector SHALL 注入已完成步骤数/总步骤数
5. THE Context_Injector SHALL 合并多条 system 消息为一条（避免 vLLM 拒绝多 system 消息）
6. THE Context_Injector SHALL 控制 system prompt 总 token 数 ≤ 4000（guidance_text ≤ 1500 tokens, RAG hits ≤ 500 tokens/条, filled_data ≤ 2000 tokens）
2. THE Context_Injector SHALL 对已填写数据摘要进行截断控制（不超过 2000 tokens）
3. WHEN 底稿为审定表类（D~N 循环 *-1 底稿）, THE Context_Injector SHALL 注入已填金额字段摘要（科目名+审定金额前 10 行）
4. WHEN 底稿为程序表类（*-A 底稿）, THE Context_Injector SHALL 注入已完成步骤数/总步骤数
5. THE Context_Injector SHALL 合并多条 system 消息为一条（避免 vLLM 拒绝多 system 消息）

### 需求 6: RAG 知识库检索增强（P2）

**用户故事**：作为审计人员，我希望 AI 对话能引用相关审计准则/模板/案例作为上下文，以便回答有据可依、可追溯。

#### 验收标准

1. WHEN 用户发起对话时, THE Knowledge_RAG SHALL 以 wp_code + 用户问题关键词调用 `semantic_search` 检索相关准则段落
2. THE Knowledge_RAG SHALL 返回 top 5 相关命中段落作为 LLM 上下文注入（复用现有 ChatContext.knowledge_hits 结构）
3. IF 向量检索不可用（embedding 404）, THEN THE Knowledge_RAG SHALL 降级为 BM25 或 ilike 检索（复用现有降级链路）
4. THE Guidance_Panel SHALL 在 AI 回答下方显示引用来源列表（准则名/文件名 + 可展开段落预览）
5. WHEN 用户点击引用来源, THE Guidance_Panel SHALL 跳转到知识库对应文档详情页
6. THE Knowledge_RAG SHALL 按 `scope="knowledge_doc"` 检索（限定知识库范围，不检索项目数据）

### 需求 7: 底稿复杂度自适应（P3）

**用户故事**：作为审计人员，我希望编制指导的详细程度与底稿复杂度匹配——复杂底稿给详尽指引，简单底稿仅给简短提示，避免信息过载。

#### 验收标准

1. THE Guidance_Service SHALL 根据 wp_code 前缀和 componentType 判定底稿复杂度等级（高/中/低）
2. WHEN 底稿为高复杂度（A17 总结/B60 总体策略/审定表/程序表）, THE Guidance_Panel SHALL 展示完整编制说明 + 推荐问题 + RAG 引用
3. WHEN 底稿为中复杂度（核对表 A1-15/A1-16/分析性复核 A1-13/A1-14）, THE Guidance_Panel SHALL 展示编制说明摘要 + 推荐问题
4. WHEN 底稿为低复杂度（调整分录/明细表/audit-sheet 类）, THE Guidance_Panel SHALL 展示简短提示（1~2 行）+ 仅 AI 对话入口
5. THE Guidance_Service SHALL 允许通过 `backend/data/wp_guidance/_complexity.json` 配置文件自定义复杂度等级映射

### 需求 8: 缓存与性能（P3）

**用户故事**：作为审计人员，我希望编制说明面板快速加载，不影响底稿打开速度。

#### 验收标准

1. THE Guidance_Cache SHALL 在后端内存中按 `wp_code` 缓存提取结果（LRU，最大 128 条）
2. WHEN 模板文件 mtime 未变化时, THE Guidance_Cache SHALL 直接返回缓存结果（0ms 延迟）
3. WHEN 模板文件 mtime 变化时, THE Guidance_Cache SHALL 自动失效并重新提取
4. THE Guidance_Panel SHALL 在前端缓存已加载的编制说明（sessionStorage，按 wp_code 键）
5. IF 后端 guidance 端点响应超过 3 秒, THEN THE Guidance_Panel SHALL 显示 skeleton 占位并在后台继续加载
6. THE Guidance_Service SHALL 对模板解析过程设置 5 秒超时（防止巨型 xlsx 阻塞）

### 需求 9: 对话端点与协议（P1）

**用户故事**：作为前端开发者，我需要明确的 API 协议来集成 AI 对话功能。

#### 验收标准

1. THE Guidance_Service SHALL 通过 `POST /api/workpapers/{wp_id}/ai-chat` 端点接收对话请求（复用 doc_ai_chat 管线）
---

## 正确性属性话端点 SHALL 将当前底稿上下文（需求 5）自动注入到 ContextBuilder.build 的参数中
5. IF 对话请求中 wp_id 无效或底稿不存在, THEN THE Guidance_Service SHALL 返回 HTTP 404
6. THE 对话端点 SHALL 共享 doc_ai_chat 的 DB 持久化机制（doc_chat_persistence，按 workpaper:{wp_id} 维度存储）

---

## 正确性属性

### P1: 编制说明提取幂等性

对同一 wp_code 多次调用 `GET /api/workpapers/{wp_id}/guidance`，在模板未变更时，返回内容完全一致（幂等）。

### P2: 上下文截断不破坏语义完整性

Context_Injector 截断后的已填数据摘要，其 token 数不超过 2000，且截断点位于完整行末尾（不在单元格值中间截断）。

### P3: 降级链路完整性

当模板文件不可读、RAG 向量服务不可用、LLM 熔断器触发时，Guidance_Panel 始终有可展示内容（至少 fallback 通用提示），不出现空白面板或未捕获异常。

### P4: 缓存一致性

当模板文件被更新（mtime 变化）后，下一次 guidance 请求必须返回新提取内容，不返回过期缓存。

### P5: 对话历史持久化往返（Round-Trip）

用户发送消息 → 收到 AI 回复 → 关闭面板 → 重新打开面板 → 对话历史完整展示（不丢消息）。验证 `append_message → get_history` 的往返一致性。

---

## 非功能需求

### 性能

- 编制说明端点响应时间 ≤ 500ms（缓存命中时 ≤ 50ms）
- 面板组件懒加载，不影响底稿主体 LCP（Largest Contentful Paint）
- LLM 首 token 时间 ≤ 3s（本地 vLLM，非网络延迟瓶颈）

### 可用性

- `WP_AI_SERVICE_ENABLED=False` 时面板仅展示静态编制说明，无任何 LLM 调用
- LLM/RAG 不可用时优雅降级，不阻塞底稿正常编辑
- 面板组件异常不影响底稿主体功能（错误边界隔离）

### 安全

- 对话端点复用现有 JWT 认证（`get_current_user`）
- 对话历史按 user_id 隔离（不同用户看不到彼此的对话）
- LLM 输入不注入用户敏感信息（如密码、个人手机号）

### 兼容性

- 面板组件兼容所有 componentType（d-form-table / univer / a-program-console / checklist-table / word-template）
- 面板在 1920×1080 分辨率下不遮挡底稿关键编辑区
- 所有用户可见文本中文

---

## 适用底稿举例

| 复杂度 | 底稿示例 | 编制说明预期内容 |
|--------|----------|-----------------|
| 高 | A17 总结/B60 总体策略/审定表(D~N-1)/程序表(D~N-A) | 完整分步指引 + 数据来源说明 + 准则引用 |
| 中 | 核对表(A1-15/A1-16)/分析性复核(A1-13/A1-14) | 填写要点摘要 + 适用性判断说明 |
### 兼容性

- 面板组件兼容所有 componentType（d-form-table / univer / a-program-console / checklist-table / word-template）
- 面板在 1920×1080 分辨率下不遮挡底稿关键编辑区
- **小屏适配**：屏幕宽度 < 1600px 时面板自动切换为 overlay 模式（半透明遮罩，非推挤主编辑区），或面板宽度降为 300px；笔记本 1366×768 场景不得导致底稿编辑区 < 900px
- 所有用户可见文本中文

| 组件 | 现状 | 差距 |
|------|------|------|
| `wp_guidance_service.py` | 已有按 wp_code 加载静态 JSON 逻辑 | 需增加模板 sheet 动态提取 + mtime 缓存 |
| `doc_ai_chat` 管线 | 已有文档级对话（ContextBuilder + SSE streaming + DB 持久化） | 需扩展 ContextBuilder 支持底稿上下文注入 |
| `knowledge_base` 模块 | 已有 semantic_search（向量 + BM25 + ilike 降级） | 需增加 wp_code 维度的 scope 过滤 |
| `wp_llm_prompts` | 已有底稿 LLM 提示词体系 | 需增加编制指导专用 system prompt |
| 前端面板 | 无 | 需新建 `WpGuidancePanel.vue` |
| 模板提取 | `analyze_wp_templates.py` 已识别「编制说明」sheet 分类 | 需将分析逻辑固化为运行时提取服务 |