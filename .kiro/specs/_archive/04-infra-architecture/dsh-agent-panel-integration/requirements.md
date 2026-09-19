# Requirements Document

## Introduction

本 spec 将审计平台现有的多套 AI 对话入口收敛为一个平台原生的 AI 审计助手，并在同一受控运行内核上提供：文档与地址坐标 mention、附件 OCR、复核提示词、项目笔记转存，以及可选的 DSH 多步 Agent 引擎。

本 spec 不是从零新建，也不把现状误判为可直接复用的完整链路。当前仓库已经具备 `DshPanel.vue` 布局壳、`AIChatPanel.vue`、`DocAiChatPanel.vue`、`AiAssistantSidebar.vue`、`useAiChat.ts`、`useDocAiChat.ts`、`doc_ai_chat.py`、`ContextBuilder` 和对话持久化，但同时存在以下必须先收口的事实：

1. `doc_ai_chat` 只校验登录，资源授权晚于内容读取；`ContextBuilder` 的底稿查询未绑定 `project_id`，知识文档/文件夹正文也没有统一前置授权。
2. `note`、`report`、`knowledge_folder` 的宿主参数与 ContextBuilder 契约不一致，只有 workpaper 路径基本成立。
3. 完整对话正文被写入不含用户/项目/年度的 `localStorage` key，共享终端存在跨账号泄漏风险。
4. 当前会话模型没有唯一定位、run 状态、幂等、取消、恢复和工具调用审计，无法可靠承载多步 Agent。
5. 采纳接口信任客户端传入的正文，`ai_content_log` 写入失败仍可能返回成功，实际不是 fail-closed。
6. 前端已有多套聊天组件与 SSE 解析器；再创建 `AiChatPanel.vue` / `useAiChat.ts` 会重复建设，并在 Windows 上与 `AIChatPanel.vue` 发生大小写路径冲突。
7. DSH 本地 provider 的“存在”不等于有效路由已切到本地；自定义 Cordis 还必须包含 JSON-RPC bridge，并区分 MCP stdio 所需的运输子进程与禁止暴露给 Agent 的 shell/subprocess 工具。

因此，本 spec 的实施顺序固定为：

1. **安全与运行基线**：资源授权、宿主契约、typed run、会话幂等、审计与前端单一内核。
2. **上下文能力**：mention、OCR、笔记、复核模式、地址坐标语义索引。
3. **DSH 实验引擎**：MCP、scoped token、custom Cordis、隔离、限流与本地化运行时验证。

后续阶段不得绕过前置阶段直接交付。DSH 阶段通过服务端 feature flag 与能力握手启用；未通过运行时安全验收时，平台继续使用 `native` 引擎，但不得把 DSH 失败静默伪装成 native 成功。

## Glossary

| 术语 | 含义 |
|---|---|
| DSH | DeepSeek Harness，本 spec 中作为可选的本地多步 Agent 引擎 |
| native 引擎 | 平台通过既有 `AIService` / 本地 vLLM 完成的受控对话引擎 |
| HostContext | 由服务端根据宿主资源解析出的可信上下文，包含项目、年度、资源类型、资源 ID 和权限绑定 |
| ResourceAccessResolver | 在任何名称、摘要、正文或索引结果读取前执行的统一资源授权适配器 |
| Chat Run | 一次可取消、可追踪、可恢复且具备唯一 `run_id` 的 AI 执行 |
| ChatEvent | Chat Run 对外输出的 typed event，如 `delta`、`tool_started`、`error`、`done` |
| mention | 用户通过 `@` 选择的平台资源引用，提交结构化 `{type, id}`，正文由服务端授权后加载 |
| Context Manifest | 服务端返回的“本轮实际纳入了哪些上下文、哪些被裁剪”的可审计清单 |
| 项目笔记 | 由用户确认后，将服务端权威 AI 消息转存到当前项目知识库的条目 |
| scoped token | 限定用户、项目、run、只读 scope 和短时效的 MCP 调用凭据 |
| effective configuration | 运行时真正生效的模型路由、Cordis 和工具目录，而非仅存在于某个配置文件中的候选值 |
| terminal event | `done`、`error` 或 `cancelled`；一个 run 只能出现一个终态 |

## Requirements

### Requirement 1: 统一 AI 面板宿主与可访问布局

**User Story:** 作为审计人员，我希望在不同页面使用同一个 AI 助手内核，并能在桌面与窄屏环境中稳定操作，而不是面对多套行为不一致的聊天入口。

#### Acceptance Criteria

1.1 WHEN 用户从顶栏或右侧触发条打开 AI 助手 THEN 面板 SHALL 在 `ThreeColumnLayout` 中使用平台原生组件渲染，SHALL NOT 使用 DSH Web UI iframe。

1.2 WHEN 桌面视口宽度大于 1400px THEN 面板 SHALL 作为 `gt-body` 的独立列展开；WHEN 视口宽度介于 769px 与 1400px THEN 面板 SHALL 作为 fixed 浮层展示；WHEN 视口宽度不大于 768px THEN 面板 SHALL 使用全屏模式并适配 safe-area。

1.3 WHEN 用户拖拽面板左缘 THEN 宽度 SHALL 限制在 320 至 800px；面板宽度可写入 `localStorage['gt-dsh-panel-width']`，但消息正文、附件正文、OCR 文本和引用内容 SHALL NOT 写入 localStorage。

1.4 WHEN 面板折叠且收到新的 assistant terminal message THEN 顶栏 badge SHALL 增加；WHEN 面板展开或用户进入相应消息 THEN badge SHALL 清零，且计数 SHALL 由平台组件事件产生而非 iframe `postMessage`。

1.5 面板顶部 SHALL 提供“新窗口打开”“刷新当前会话”“收起/关闭”操作；新窗口 SHALL 打开平台自己的聊天路由，而非 DSH Web UI。

1.6 所有触发器、图标操作、拖拽手柄和 mention 选择器 SHALL 支持键盘操作、中文 `aria-label`、可见焦点和合理 tab 顺序；流式回复 SHALL 通过 `aria-live` 提供非阻塞播报。

1.7 WHEN 面板打开或关闭 THEN 焦点 SHALL 在面板与原触发元素之间正确转移；全屏模式 SHALL 支持 Escape、焦点锁定与滚动隔离。

1.8 平台 SHALL 只保留一个聊天消息模型、一个 SSE transport 和一个核心聊天组件；`DshPanel`、底稿侧栏、文档抽屉和独立窗口 SHALL 作为 host adapter 复用该内核。

1.9 WHEN 所有宿主完成迁移 THEN 与统一内核重复且无消费方的旧组件、composable 和手写 SSE 解析器 SHALL 被删除，不保留 DEPRECATED 或 fallback 死代码。

1.10 面板 SHALL NOT 渲染 workspace 选择器；工作范围 SHALL 由当前 HostContext 和服务端权限决定。

### Requirement 2: 资源授权前置与五角色可见性

**User Story:** 作为项目成员或独立复核人员，我只能让 AI 读取自己本来就有权访问的资源，资源名称本身也不能在授权前泄露。

#### 角色与权限原则

角色只是权限上界，不单独授予数据访问权。最终允许集合 SHALL 为以下条件的交集：当前用户有效角色、项目成员关系、资源级权限、`scope_cycles`、知识库 access level，以及具体动作权限。

| 角色 | 默认读取上界 | 写类动作上界 |
|---|---|---|
| 审计助理 | 当前项目且在分配循环/资源范围内 | 仅在已有权限允许时上传会话附件、发起采纳、创建项目笔记 |
| 现场经理 | 当前项目管理范围 | 仅在已有项目写权限允许时创建项目笔记或发起确认流 |
| 业务合伙人 | 当前项目合伙人可见范围 | 不因角色自动绕过知识库或资源级权限 |
| 质量控制复核合伙人 | 既有 QC 可见范围 | 默认只读；写类动作仍需显式 capability |
| EQCR 技术复核人 | 既有 EQCR 可见范围 | 默认只读；写类动作仍需显式 capability |

#### Acceptance Criteria

2.1 EVERY AI endpoint SHALL 在读取资源名称、摘要、正文、索引片段或历史消息前调用公共 `ResourceAccessResolver`；私有 ContextBuilder 方法 SHALL NOT 充当跨路由授权 API。

2.2 ResourceAccessResolver SHALL 复用平台既有项目、底稿、知识库和角色可见性服务；SHALL NOT 在 AI 模块复制第二套角色或资源权限算法。

2.3 WHEN 客户端提交 `project_id`、`year`、`doc_type` 或 `doc_id` THEN 服务端 SHALL 从目标资源反查可信 HostContext，并只把客户端值作为一致性断言；不一致请求 SHALL 被拒绝。

2.4 mention 搜索、HostContext、history、clear、adopt、attachment、note save、review prompt、MCP callback 和 citation jump SHALL 使用同一授权决策；不得出现“搜索不可见但直接 ID 可读”或相反的旁路。

2.5 WHEN 用户无权访问资源 THEN API SHALL 在读取敏感字段前拒绝，并采用不泄露资源是否存在的响应语义；响应 SHALL NOT 包含资源 label、项目名或正文摘要。

2.6 WHEN `scope_cycles` 限制用户只能访问部分循环 THEN mention、RAG、MCP 和跨底稿 Agent SHALL 同步裁剪到相同循环范围。

2.7 每个涉及 AI 读取或写类动作的端点 SHALL 有五角色矩阵测试，至少覆盖允许、拒绝、跨项目、跨循环和 private/project_group 知识库五类边界。

2.8 ContextBuilder 或授权服务异常 SHALL fail-closed；SHALL NOT 降级为空上下文后继续调用模型。

### Requirement 3: 服务端可信 HostContext 契约

**User Story:** 作为用户，我希望 AI 确实理解当前所在的底稿、附注、报表或知识库位置，不会因为前端传错 ID 而读取空内容或错误资源。

#### Acceptance Criteria

3.1 HostContext SHALL 使用受后端枚举约束的宿主类型，至少覆盖 `workpaper`、`note`、`report`、`knowledge_doc`、`knowledge_folder` 和无项目资源的受限全局知识模式。

3.2 `workpaper` SHALL 以 working paper instance ID 解析；`note` SHALL 以项目、年度和稳定附注 section/instance 标识解析；`report` SHALL 以项目、年度和 report type/instance 标识解析；`knowledge_folder` SHALL 以 folder ID 解析。

3.3 服务端 SHALL 为每个宿主返回 canonical `{project_id, year, resource_type, resource_id, display_label, permission_binding}`；不存在的字段 SHALL 使用明确的 nullable 语义，不得用空字符串伪装有效 ID。

3.4 WHEN 当前页面无法解析项目上下文 THEN 项目工具 SHALL 被禁用并显示原因；SHALL NOT 发送空 `project_id` 或猜测最近项目。

3.5 `ReportView`、`DisclosureEditor`、`KnowledgeBase`、`WorkpaperEditor`、全局 `DshPanel` 和独立聊天窗口 SHALL 通过各自 adapter 构造同一 HostContext 请求，不得把 project ID 当作 document ID。

3.6 ContextBuilder SHALL 接受已授权的 HostContext，而不是再次依据未经验证的 `doc_type/doc_id/project_id` 自行猜测资源类型。

3.7 每一种 HostContext SHALL 有真实路由契约测试，证明正文加载器读取的是对应业务模型而非统一回退到 `WorkingPaper`。

### Requirement 4: Typed Chat Run、幂等、取消与恢复

**User Story:** 作为审计师，我希望重复点击、断网、取消或切换页面不会产生重复回答或留下一直运行的 Agent；作为运维人员，我要知道每次执行处于什么状态。

#### Acceptance Criteria

4.1 对话 SHALL 使用两阶段 API：创建幂等 Chat Run，再通过 SSE 订阅该 run 的事件；客户端断线重连 SHALL 订阅原 run，不得重新调用模型。

4.2 `ChatRunRequest` SHALL 包含服务端会话标识、query、mentions、attachment IDs、review mode 和 client-generated idempotency key；SHALL NOT 接收客户端可覆盖的 engine 或权限 scope。

4.3 ChatEvent 单一真源 SHALL 至少包含 `run_started`、`context_ready`、`citation`、`delta`、`tool_started`、`tool_finished`、`quota`、`error`、`cancelled` 和 `done`。

4.4 EVERY ChatEvent SHALL 包含单调事件 ID、`run_id`、`session_id`、`request_id`、event type 和 server timestamp；与消息相关的事件 SHALL 另外包含 server-issued `message_id`。

4.5 一个 run SHALL 只能从 queued/running 进入一个 terminal state；WHEN `error` 或 `cancelled` 已发出 THEN 后续 SHALL NOT 再发 success `done`。

4.6 WHEN 同一用户在同一会话重复提交相同 idempotency key THEN 服务端 SHALL 返回同一 run，不重复保存用户消息、不重复调用模型、不重复执行工具。

4.7 WHEN 用户取消 run THEN 取消 SHALL 传播到 native generator、DSH root、子 Agent、MCP 调用和排队任务；取消完成后 SHALL 不再发生工具调用或 assistant 消息追加。

4.8 SSE transport SHALL 正确处理任意网络字节分片、CRLF/LF、心跳和多行 data；不得按单个 `reader.read()` chunk 直接拆行解析。

4.9 SSE SHALL 接入平台 drain/registry 生命周期；服务停机时 active run SHALL 收到可识别的中止状态或在重启后被标为 interrupted。

4.10 对话 history SHALL 返回最近 N 条后再按时间正序展示，包含真实 message ID、citations、engine、model、token usage、latency 和 run status。

4.11 会话定位 SHALL 至少绑定 user、project、year、host type 和 host ID，并有数据库唯一约束；并发首轮创建 SHALL 使用 upsert 或等价原子语义。

4.12 active run 的短时事件回放 SHALL 使用平台已有 Redis 能力或等价有界缓冲并设置 TTL；数据库 SHALL 持久化 run/message/tool 摘要，SHALL NOT 为每个 token delta 写一行数据库。

### Requirement 5: Mention 与 Context Manifest

**User Story:** 作为审计师，我希望通过 `@` 精确引用平台资源，并能看到本轮 AI 实际读取了什么，而不是相信一个不可验证的上下文黑箱。

#### Acceptance Criteria

5.1 WHEN 用户输入 `@` THEN 面板 SHALL 打开支持搜索、键盘导航、多选和移除的 mention 选择器。

5.2 Mention type SHALL 由后端 schema 单一真源定义并生成或校验前端类型，至少包含 `workpaper`、`note`、`report`、`knowledge_doc`、`knowledge_folder`、`address` 和 `attachment`。

5.3 mention 搜索 SHALL 在服务端授权后返回统一 `{type, id, label, sublabel, jump_route}`；无权资源和未实例化资源 SHALL 不出现在结果中。

5.4 WHEN mention endpoint 失败、超时或引擎能力不可用 THEN 前端 SHALL 显示“加载失败/能力不可用”；WHEN 查询成功但无结果 THEN 前端 SHALL 显示“无匹配结果”，两者不得混淆。

5.5 客户端 SHALL 只提交 mention type 与稳定 ID；服务端 SHALL 在当前 HostContext 下重新授权、加载和定界正文，SHALL NOT 信任客户端提交的 label 或正文。

5.6 mention、宿主正文、OCR、review prompt 和自动 RAG SHALL 共用 token budget；用户显式 mention 的优先级、各分区预算和裁剪顺序 SHALL 在服务端单一策略中定义。

5.7 每个 run SHALL 通过 `context_ready` 返回 Context Manifest，至少包含纳入项、拒绝项、裁剪项、引用版本、stale 标志和原因码；前端 SHALL 可展开查看。

5.8 `extra_scopes` 旧语义 SHALL 被 mention 统一承载；完成所有宿主迁移后 SHALL 删除旧字段与旧请求路径，不保留长期双轨。

5.9 mention 或 Context Manifest 中的 jump route SHALL 在点击时再次经过目标页面权限校验，不能把前端 route 当成授权凭据。

### Requirement 6: 地址坐标语义索引

**User Story:** 作为审计师，我希望用审计语义定位报表、附注、底稿或试算表地址，并区分“确实无匹配”和“语义服务不可用”。

#### Acceptance Criteria

6.1 地址坐标 SHALL 作为 `address` mention 类型提供，并返回稳定 addr ID、label、domain、URI/formula reference、jump route 与授权后的当前值摘要。

6.2 地址索引 SHALL 接入既有 `IndexSource`、增量更新、stale 管理和 ACNR canonical invalidation event；SHALL NOT 新建第二套向量库或孤立索引调度器。

6.3 索引文本 SHALL 只来自 `AddressEntry.label`、ACNR `semantic_label` 及其既有结构字段；索引模块 SHALL NOT 复制科目、章节、表名或坐标标签字面量。

6.4 新增 knowledge source enum SHALL 使用实施时通过 migration status 分配的下一个可用迁移号，并使用数据库实际 enum 名称、`IF NOT EXISTS` 和独立事务约束；spec SHALL NOT 预占固定 V 号。

6.5 地址搜索 SHALL 使用严格 source type/scope 过滤；embedding 不可用时 SHALL 返回 `semantic_unavailable`，不得用 BM25/ILIKE 结果冒充语义命中。

6.6 WHEN 坐标发生变化或失效 THEN 对应索引 SHALL 被增量更新或标为 stale；Context Manifest SHALL 暴露 stale 状态。

6.7 地址当前值 SHALL 经过项目权限、地址域权限和脱敏；未授权用户不得通过语义搜索获知地址 label 或当前值。

### Requirement 7: 会话附件与本地 OCR

**User Story:** 作为审计师，我希望上传或粘贴截图、扫描件并让 AI 使用 OCR 结果，同时确保恶意文件、跨会话引用和临时文件不会污染平台。

#### Acceptance Criteria

7.1 输入区 SHALL 支持附件按钮、拖拽和剪贴板图片粘贴，并显示上传、OCR、失败、取消和完成状态。

7.2 后端 SHALL 同时校验扩展名、MIME magic、文件数量、单文件大小、PDF 页数/像素/解压上限，并使用随机服务端文件名；非法文件 SHALL 在 OCR 前被拒绝。

7.3 附件 SHALL 有服务端 metadata，至少绑定 attachment ID、owner、project、session、run、hash、状态、路径、大小、MIME、创建时间和过期时间；聊天请求只提交 attachment ID。

7.4 WHEN 客户端引用 attachment ID THEN 服务端 SHALL 校验 owner、HostContext 与 session；跨用户、跨项目或跨会话引用 SHALL 被拒绝。

7.5 OCR SHALL 复用 `UnifiedOCRService` 并完全在本地执行；HTTP 模式不可用、in-process 引擎链失败和超时 SHALL 返回可区分错误，SHALL NOT 以 200 空文本伪装成功。

7.6 WHEN OCR 成功但没有文本 THEN 状态 SHALL 为 `empty` 并显示“未识别到文字内容”，用户可补充说明；空文本不得被当作失败或静默丢弃附件。

7.7 OCR 文本 SHALL 被视为不可信数据，进入模型前须定界、脱敏并记录 Context Manifest；前端展开显示时须使用统一 sanitize 路径。

7.8 附件 SHALL 存放在独立 `storage/ai_chat/` 空间，不写入业务证据附件表；clear、过期清理和 legal hold SHALL 使用明确策略并产生审计记录。

7.9 cleanup SHALL 可重试且幂等；磁盘删除失败不得删除 metadata 后失去追踪。

### Requirement 8: 项目笔记与 AI 内容采纳 fail-closed

**User Story:** 作为审计师，我希望保存有价值的 AI 结论或发起采纳，同时平台必须保证保存的是服务端真实生成且可追溯的内容。

#### Acceptance Criteria

8.1 AI assistant 消息 SHALL 使用服务端签发的 message ID；复制、转存项目笔记和采纳 SHALL 引用 message ID，不把客户端正文作为权威来源。

8.2 WHEN 用户转存一条或多条消息 THEN 前端 SHALL 要求确认笔记名称，并提交 idempotency key；重复请求 SHALL 返回同一知识文档，不创建重复文件夹或重复文档。

8.3 项目笔记目标文件夹 SHALL 由单一命名与定位规则解析，并使用数据库唯一约束/upsert 保证并发幂等，而非仅“先查后建”。

8.4 项目笔记 SHALL 保存 source run/message IDs、HostContext、原问题、citations、content hash、创建者、项目、年度和 `ai-note` tag，并触发既有知识索引链路。

8.5 WHEN 笔记保存失败 THEN 前端 SHALL 保留选择状态并显示可重试原因；WHEN 成功 THEN SHALL 返回经授权的跳转链接。

8.6 adopt endpoint SHALL 根据 message ID 从数据库读取 assistant 正文，并校验消息属于当前用户、会话、项目和 HostContext；篡改 message ID、project ID 或客户端 content SHALL 被拒绝。

8.7 `wrap_ai_output_with_log` 或 `ai_content_log` 写入失败 SHALL 回滚并返回失败；只有获得非空、有效的 log ID 后才能返回“已进入确认流”。

8.8 项目笔记属于知识资产写入，采纳属于业务确认流；两者 SHALL 分别执行既有 write capability 检查，不得因为能读资源就自动获得写权限。

8.9 笔记保存与采纳 SHALL 写入平台哈希链审计日志；审计内容保存 message/content hash 和引用 ID，不重复存储完整敏感正文。

### Requirement 9: 底稿复核模式

**User Story:** 作为编制或复核人员，我希望 AI 使用平台现有底稿复核提示词和方法论，并明确告知使用的是专属模板还是通用模板。

#### Acceptance Criteria

9.1 只有 HostContext 为 workpaper 且用户对该底稿有读取权限时 SHALL 提供复核模式；其他宿主 SHALL 禁用并显示原因。

9.2 WHEN 复核模式启用 THEN 后端 SHALL 通过 `ReviewPromptService.load_prompt(wp_code, sheet_name)` 获取内容，前端 SHALL NOT 保存或复制提示词正文。

9.3 review prompt、系统策略、数据定界和上下文 SHALL 在进入 vLLM 前合并为符合单 system 约束的消息；不得因为新增模式产生多个 system message。

9.4 前端 SHALL 展示 `source_level`、`tips`、`checklist`、`risk_areas` 和 version；命中 base 模板时 SHALL 明确提示“当前使用通用复核模板”。

9.5 当前复核模式 SHALL 随服务端会话保存，不得只存于不含用户/项目作用域的 localStorage。

9.6 review prompt 加载失败 SHALL 终止复核模式本轮请求并产生明确错误，不得静默退回普通问答后按成功显示。

### Requirement 10: 引擎抽象、能力握手与降级

**User Story:** 作为用户，我希望平台明确告诉我当前引擎能做什么；作为管理员，我希望 DSH 不可用时不会被悄悄替换成另一条行为不同的链路。

#### Acceptance Criteria

10.1 引擎选择 SHALL 只由服务端配置和服务端 feature flag 决定，默认 `native`；客户端 SHALL NOT 通过请求体覆盖 engine。

10.2 ChatEngine SHALL 消费统一 `ChatRunRequest` 并产生统一 `ChatEvent`，而不是仅返回字符串流；native 与 DSH SHALL 遵守相同 terminal、cancel、usage 和 audit 语义。

10.3 每个 engine SHALL 发布 capability manifest，至少包括 `streaming`、`tools`、`subagents`、`max_context`、`structured_output`、`local_only`、`review_mode` 和 attachment support。

10.4 WHEN 当前 engine 不支持某能力 THEN 前端 SHALL 禁用对应入口并显示中文原因；不得提交后由后端静默忽略。

10.5 WHEN DSH 启动、JSON-RPC、MCP 或有效本地模型检查失败 THEN run SHALL 以 `engine_unavailable` 结束；SHALL NOT 静默回落 native 后返回成功内容。

10.6 DSH SHALL 作为 experimental feature flag 分阶段启用；未通过 custom Cordis smoke、双用户隔离、取消传播和无出网验证前，SHALL NOT 对全部项目开放。

10.7 native 引擎 SHALL 继续复用既有 AIService、熔断器、并发限制和本地 vLLM，不新写第二套模型 HTTP client。

### Requirement 11: DSH、MCP 与身份隔离

**User Story:** 作为质量控制复核人员，我要求多步 Agent 只能通过平台授权的只读工具取数，不能访问数据库凭据、执行 shell、写文件或把一个用户的权限带进另一个用户的 run。

#### Acceptance Criteria

11.1 DSH SHALL 使用精确 pin 的兼容 SDK/runtime 版本和平台维护的 custom Cordis；custom Cordis SHALL 包含 SDK 所需 JSON-RPC server、Agent spine、本地 LLM provider 和 MCP client。

11.2 “禁止 subprocess” SHALL 指禁止向 Agent 暴露 shell/subprocess 工具；MCP stdio transport 与 JSON-RPC bridge 所需的内部运输进程 MAY 存在，但不得接受 Agent 自定义命令。

11.3 Agent 可见工具 SHALL 由 `MCP_READONLY_TOOLS` 单一真源注册，全部显式 `readonly=true`；运行时实际 tool catalog SHALL 与声明完全一致且不包含 filesystem write、shell、web fetch 或任意命令执行工具。

11.4 `audit-data` MCP server SHALL 使用 stdio 且不监听网络端口；SHALL NOT 直连数据库、读取 DB/Redis/平台密钥或 import 平台 ORM，全部数据经平台受权 REST API 获取。

11.5 MCP callback SHALL 使用短时 scoped token，至少绑定 user、project、run、只读 scope 和 expiry；长期登录 token SHALL NOT 传入 DSH/MCP 子进程。

11.6 带身份的 token SHALL NOT 固化到跨用户共享 runtime 环境。实现 SHALL 使用 per-run MCP process 或经验证的 token broker；任何 runtime/pool 在跨 principal 复用前必须完成可证明的上下文清理。

11.7 子 Agent SHALL 继承父 run 的项目、权限、只读 scope、配额与过期时间，不能签发更高权限 token 或扩大循环范围。

11.8 MCP endpoint SHALL 复用 Requirement 2 的 ResourceAccessResolver，并对每个工具设置调用频率、单次返回字节数、行数和总 run budget；超限 SHALL 返回明确错误而非截断后按成功返回。

11.9 MCP 返回与 native 上下文 SHALL 使用相同的 `ExportMaskService` 角色映射；auditor、manager、partner、qc、eqcr 的映射 SHALL 显式定义，未知角色 fail-closed。

11.10 不可信底稿、知识库和 OCR 内容 SHALL 以“数据而非指令”定界；提示注入策略 SHALL 由 deterministic policy 测试验证，不能依赖真实模型每次选择完全相同工具。

11.11 DSH root、session 文件、JSONL、日志和子进程 SHALL 绑定 run/principal 并有 TTL；run 结束、取消或 worker 回收后 SHALL 不残留另一用户可读取的上下文。

11.12 DSH worker SHALL 有有界并发、排队、超时和 backpressure；平台 6000 用户目标不等于允许创建 6000 个无界子进程。

### Requirement 12: 全本地化、失败可见与审计可观测

**User Story:** 作为事务所和运维人员，我要确认审计数据没有出内网，并能从运行记录还原每个 run、上下文和工具调用的结果。

#### Acceptance Criteria

12.1 模型、embedding 和 OCR 的 effective endpoint SHALL 为内网或 loopback allowlist；仅在配置文件中出现 localhost 不足以通过验收，启动时 SHALL 输出并校验实际生效路由。

12.2 WHEN effective DSH model 指向 `deepseek-official`、公网 URL、bundled default 或未知 provider THEN DSH SHALL 拒绝启动并产生 `local_only_violation`。

12.3 本 spec 引入的代码 SHALL NOT 发起公网请求；运行时 egress 测试 SHALL 证明模型、MCP、OCR、embedding 和插件路径均未建立公网连接。

12.4 embedding 不可用 SHALL 返回 `semantic_unavailable`；OCR 不可用 SHALL 返回明确 OCR 错误；模型熔断/超时 SHALL 转成 typed error，三者不得伪装成“无结果”或普通 assistant 消息。

12.5 ContextBuilder、mention、OCR、note、review、engine 和 MCP 的错误 SHALL 使用稳定 error code 和中文用户消息；内部异常细节 SHALL 进入受控日志而非直接返回客户端。

12.6 EVERY run SHALL 在平台哈希链审计日志中记录 started 与唯一 terminal event；EVERY tool call SHALL 记录 started 与 finished/failed，包含 run、actor、project、tool、arg hash、结果字节数、耗时和错误码。

12.7 审计日志 SHALL NOT 保存 scoped token、数据库凭据、完整附件正文或未脱敏上下文；敏感参数只保存 hash/摘要和可追踪 ID。

12.8 平台 SHALL 暴露 active runs、queue wait、run latency、tokens、tool calls/run、cancel latency、MCP bytes、authorization denials、pool occupancy、attachment bytes 和 cleanup failures 等指标，并配置容量/错误率告警阈值。

12.9 `ContextBuilder.build` 异常、LLM fail-soft 占位串、tool error 或下游写入失败 SHALL 不产生 success terminal event或成功文案。

### Requirement 13: 输出安全、浏览器数据边界与调用配额

**User Story:** 作为审计师，我不希望 AI 或外部文档内容在浏览器执行脚本，也不希望共享终端留下前一用户的对话，或在限流时只看到通用错误。

#### Acceptance Criteria

13.1 AI 回复、mention 预览、OCR 文本、citation excerpt 和 Context Manifest 中的可控 HTML SHALL 共用 `marked` 加既有 `useSanitize` 的唯一渲染路径。

13.2 script、iframe、事件属性、危险 URL scheme 和注入式 SVG SHALL 被移除；安全测试 SHALL 落到渲染 DOM，不只扫描源码中是否出现 sanitize 符号。

13.3 完整对话、OCR、mention 正文、attachment metadata 和 prompt SHALL NOT 持久化到 localStorage；退出登录、切换用户和首次升级 SHALL 清除遗留 `doc_ai_chat_*` 敏感 key。

13.4 服务端 SHALL 是对话历史权威来源；离线时前端 MAY 显示当前页面内存中已经加载的消息，但 SHALL NOT 承诺跨重启离线保存敏感正文。

13.5 AI chat endpoint SHALL 被真实纳入独立限流匹配规则；prefix 常量存在但 matcher 未消费 SHALL 视为未接线。

13.6 WHEN 限流触发 THEN typed quota/error event SHALL 包含 `retry_after`、remaining 和 reset；前端 SHALL 显示中文倒计时并保留未发送草稿。

13.7 rate limit、DSH queue limit、MCP budget 和附件限制 SHALL 使用服务端配置单一真源；前端展示值来自服务端 capability/quota，不复制常量。

### Requirement 14: 分阶段交付、运行时验收与清洁收口

**User Story:** 作为负责人，我希望先得到安全且可用的 native 面板，再逐步启用上下文能力和 DSH，而不是所有风险一次上线后靠静态守卫宣称完成。

#### Acceptance Criteria

14.1 Phase A SHALL 完成 ResourceAccessResolver、HostContext、typed run、会话/幂等/取消、采纳 fail-closed、统一前端内核、sanitize 和敏感缓存清理；Phase A 未完成时 SHALL NOT 开始生产接入 DSH。

14.2 Phase B SHALL 完成 mention、OCR、笔记、复核模式和地址索引；每项 SHALL 有独立失败状态和 Context Manifest 证据。

14.3 Phase C SHALL 完成 scoped MCP、custom Cordis、DSH engine、双用户隔离、取消传播、本地路由与无出网验证，并通过 feature flag 逐项目启用。

14.4 每个阶段 SHALL 先有行为/契约守卫，再进行变异检验；变异结果 SHALL 区分 RED、GREEN、ANCHOR-MISS 和 WRONG-TEST，不能只检查退出码。

14.5 最终验收 SHALL 在 clean checkout 可运行，所有新增正式产物 SHALL 已纳入版本控制；CI SHALL 不依赖工作树中的未跟踪文件。

14.6 Playwright SHALL 至少覆盖 390px、768px、1400px 三档视口以及五角色的关键可见性；浏览器实测 SHALL 验证 DOM、网络事件、取消、错误、上下文清单和 XSS 行为。

14.7 DSH runtime 验收 SHALL 使用真实 SDK import、custom Cordis load、JSON-RPC handshake、有效模型路由、实际 tool catalog、进程/端口和 egress 观察，不能只 grep 配置文本。

14.8 spec 完成前 SHALL 清理本 spec 产生的 `tmp_*` / `_wip_*`，并运行 requirements/design/tasks 机器诊断、悬挂 AC 检查、任务依赖检查和产物跟踪检查。

## Non-Functional Requirements

### NFR-1: 复用与删除

优先复用平台现有权限、Redis、SSE registry、AIService、KnowledgeIndexService、IndexSource、UnifiedOCRService、ReviewPromptService、ExportMaskService、审计哈希链、`marked` 和 `useSanitize`。迁移完成后立即删除重复实现，不保留长期双轨或 DEPRECATED fallback。

### NFR-2: 单一真源

Host type、Mention type、ChatEvent、engine capability、MCP tool catalog、附件限制、错误码、项目笔记定位规则和配额 SHALL 分别只有一个服务端真源；前端通过 OpenAPI/generated schema 或运行时契约消费。

### NFR-3: 数据最小化

客户端只提交稳定 ID 和用户输入；资源正文、AI 权威消息、权限 scope、附件路径和模型路由均由服务端解析。日志、审计和指标只保存完成追踪所需的最小信息。

### NFR-4: 并发与容量

run、session、note save、adopt 和 attachment upload SHALL 支持幂等与并发；所有队列、缓存、Redis replay、附件和子进程 SHALL 有容量上限、TTL 与 backpressure。

### NFR-5: 全中文与可理解性

所有用户可见状态、权限拒绝、能力降级、错误、配额和重试提示 SHALL 使用中文并给出可执行下一步；内部英文 error code MAY 同时保留用于诊断。

### NFR-6: 守卫质量

守卫 SHALL 验证真实执行、状态转换或 DOM 结果；字符串存在、同一符号出现次数、固定字符窗口和未消费声明不能作为能力已接通的充分证据。
