# 实施计划：doc-level-ai-chat（文档/文件夹级 LLM 知识库对话）

> 设计：#[[file:.kiro/specs/doc-level-ai-chat/design.md]]
> 需求：#[[file:.kiro/specs/doc-level-ai-chat/requirements.md]]
> 工作流：Design-First | ~5-7 人天 | **前置依赖 retrieval-kernel-unification spec**
> 铁律：复用 semantic_search/ai_service/wrap_ai_output_with_log；AI 内容必经确认流

## 阶段 1 — 后端 ContextBuilder + 对话端点（~2 天）

- [ ] 1. ContextBuilder 上下文构建器
  - build()：① 当前文档内容（parsed_data/content_text）② semantic_search 关联知识 ③ 项目摘要 ④ extra_scopes
  - ChatContext dataclass（doc_excerpt/knowledge_hits/project_summary/citations/token_estimate）
  - _需求: 1.2, 2.1_ _属性: D3_

- [ ] 2. token 预算管理
  - chunk + 相关性排序 + 截断（top_k 最相关段落，非全文）
  - token_estimate ≤ 配置上限
  - _需求: 2.3, 2.4_ _属性: D1_

- [ ] 3. 权限过滤
  - ContextBuilder 检索只含 user 有权访问的知识文件（继承 KnowledgeDocument 权限）
  - _需求: 5.1_ _属性: D2_

- [ ] 4. 对话端点（streaming + 留痕）
  - POST /api/ai-chat/doc/{doc_type}/{doc_id}（streaming，复用 ai_service）
  - GET .../history
  - POST /api/ai-chat/adopt（采纳回写，走确认流）
  - router_registry 注册（防 404）
  - _需求: 1.1, 4.1, 4.2, 5.3_ _属性: D4_

- [ ] 5. 阶段 1 PBT
  - D1 token 预算 + D2 权限隔离 + D3 引用可追溯 + D4 确认流门禁
  - hypothesis max_examples 10~15
  - _需求: 2.4, 5.1_ _属性: D1, D2, D3, D4_

## 阶段 2 — 前端对话面板 + 挂载（~2 天）

- [ ] 6. DocAiChatPanel.vue（可嵌入面板）
  - Drawer/Panel 形式，对话历史 + streaming 接收
  - 引用来源标注（点击跳转知识文件/底稿）
  - @mention 选额外知识范围（extra_scopes）
  - _需求: 1.3, 2.2, 3.1, 3.2_

- [ ] 7. useDocAiChat.ts composable
  - 发起对话 / streaming 接收 / 历史管理 / 离线缓存
  - _需求: 5.2, 5.3_

- [ ] 8. 4 个挂载点接入
  - 底稿编辑器 / 附注编辑器 / 报表视图 / 知识库文件夹 加「AI 对话」入口
  - 文件夹级对话注入文件夹下文档集合
  - _需求: 1.1, 1.4_

- [ ] 9. 采纳回写 + 确认流
  - 采纳按钮 emit adopt → 父组件回写 + AIContentMustBeConfirmedRule（pending）
  - _需求: 4.1, 4.3_ _属性: D4_

## 阶段 3 — 引用追溯 + 集成（~1-2 天）

- [ ] 10. 引用来源跳转打通
  - knowledge_hit source → 跳转知识文件/底稿（复用 useCellLocate）
  - _需求: 3.2, 3.3_ _属性: D3_

- [ ] 11. 集成测试 + 收尾
  - ContextBuilder → 对话端点 → 面板 → 采纳回写 全链路
  - 更新 INDEX.md + memory 完成记录
  - 单 commit（git status 确认无其他 staged）
  - _需求: 4.1_ _属性: D4_

## 阶段 4 — 真实环境 UAT（~1 天，待环境）

- [ ]* 12. Playwright UAT（待 start-dev.bat）
  - 底稿页发起 AI 对话 → 注入上下文 + 关联知识 → 引用可点跳转 → 采纳走确认流
  - 文件夹级对话 → 注入文档集合
  - 显式标"待环境"不伪绿
  - _需求: 1.1, 2.1, 3.2, 4.1_
