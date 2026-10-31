# 设计：10 月 21 日 AI 采纳与笔记恢复

## 1. 事故边界

| 时间（北京时间） | 已核验事实 | 后果 |
|---|---|---|
| 2026-10-21 17:56:08 | `sess_e8ac610e` 执行 `git stash push -u -m temp-for-push-reconcile` | 已跟踪改动和未跟踪文件进入 `112bfabec`。 |
| 17:57:01 | 同会话执行 `git stash pop`，随后重做了其他工作 | stash ref 被 drop，但对象仍可由救援 tag 找到。 |
| 18:15:39 | `git checkout --force spec/disclosure-note-doc-upload-and-batch-fill` | 所有会话尚未提交的已跟踪改动被覆盖；未跟踪文件幸存。 |
| 19:52 后 | `021a47269` 仅提交幸存的新组件、工具和部分测试 | AI 新模块存在，但核心调用链断裂。 |

`git log --all -S` 默认不检查 stash 的合并提交，必须以 `git log -m`、reflog 和救援 tag 共同定位。这是早期搜索漏掉完整实现的直接原因。

本次共同祖先为 `dae1129f5`，恢复输入为 `112bfabec`，工作树基线为 `434e87972`。恢复原则是**每个路径做三方合并**，不是套用 stash 的整棵文件树。

## 2. 最小恢复闭环

```text
PlatformAiChatPanel
  ├─ canAdoptInPlace(host) ── true ──> adoptContent(messageId)
  ├─ false ──> ChatAdoptTargetDialog ──> adoptContent(messageId, target)
  └─ ChatNoteSaveDialog ──> saveAsNote({ name, target })

usePlatformAiChat
  └─ /api/ai-chat/adopt { host: target, source_host: source }
        └─ doc_ai_chat.py：目标 adopt + 来源 history
             └─ adopt_message：同主体、来源类型、目标类型、项目边界

useAiNoteCapture
  └─ /api/ai-chat/notes { message_ids, host_type, host_id, ..., target_* }
        └─ doc_ai_chat.py → save_note
             └─ resolve_note_source → resolve_note_target → claim receipt → document
```

`note_target.py`、两个 Vue 对话框、`chatTargetOptions.ts` 和错误信封解析器已由 `021a47269` 入库。本次不覆盖这些已存在文件，只把缺失的连接恢复。

## 3. 文件级合并方案

| 类别 | 文件 | 合并策略 |
|---|---|---|
| 可直接取 stash 版本 | `PlatformAiChatPanel.vue`、`PhaseBGateGuards.spec.ts`、`useAiHostContext.ts`、`useAiNoteCapture.ts` | 当前 HEAD 未有同文件的后续业务改动；恢复后由现有 `ChatAdoptNoteTarget.spec.ts` 验证。 |
| 可直接取 stash 版本 | `ai_chat/access.py`、`adopt.py`、`note_service.py`、`test_task7_adopt_fail_closed.py` | 作为一个原子服务层集合恢复；不得漏任一文件。 |
| 需要三方合并 | `usePlatformAiChat.ts` | 保留当前错误信封处理和成功事件。目标成功时以 `target?.host ?? host` 的 `projectId` 单次发送 `ai-content:adopted`。 |
| 需要三方合并 | `useDocAiChat.ts` | 保留当前成功事件，合入 stash 的 `readAiChatErrorResponse()`。 |
| 需要三方合并 | `doc_ai_chat.py` | 合入 `source_host`、笔记目标字段和授权分流，保留当前 SSE `get_db(scope="function")`。 |
| 仅保留 HEAD | `auditPlatformApi.ts` | 保留 `getDisclosureNoteTree(projectId, year, config?)`。此参数使目标选择将未生成附注的 404 降为空态。 |
| 仅保留 HEAD | `eventBus.ts`、`AiContentPendingBanner.vue` | 保留 v1.0.57 的必带 `projectId` 事件和目标标签修复，面板不可再自行发送无 payload 的重复事件。 |

`tsconfig.json` 的 ES2023 lib 仅在区域类型检查证明 `findLastIndex` 需要时恢复。它不改变输出 target；若当前库定义已经从其他路径满足，则不做无关配置改动。

## 4. 授权与数据不变量

### 4.1 跨宿主采纳

- 目标 `host` 必须是 `workpaper` 或 `note`，按 `AiChatAction.adopt` 授权。
- `source_host` 缺省时，消息仍必须属于目标宿主会话，维持旧有严格行为。
- 有 `source_host` 时，来源只能是全局知识、报表、知识库文档或知识库文件夹，按 `AiChatAction.history` 授权。
- 来源和目标必须属于同一用户；来源有项目时，目标项目必须相同。任何不满足均写 denial audit 并返回不可枚举错误，发生在消息/收据/确认记录写入之前。
- `ADOPT_AUDIT_DETAIL_KEYS` 增加 `source_host_type`、`source_host_id`，审计中不复制正文。

### 4.2 笔记转存

- 服务端从 `message_ids` 查询同一用户、已完成的 assistant 消息，并确认它们仅属于一个会话。客户端 `session_id` 仅作可选断言。
- `target_project_id` 与 `target_folder_id` 互斥。项目会话只能写回所属项目；无项目会话才可选项目或有写权限的文件夹。
- 项目目标使用 `ResourceAccessResolver.authorize_project(..., note_create)` 再确认项目存在；文件夹目标使用 `KnowledgeAccessPolicy` 和 `KnowledgeWritePolicy`。
- 所有来源、范围、权限和存在性校验均在 `claim_action_receipt` 之前。失败不能创建 receipt、知识库文件夹或文档。
- 成功结果包含实际 `location`、`folder_id`、`document_id`、`name` 和站内 `jump_route`；前端只允许以 `/` 开头且非 `//` 的站内地址。

## 5. 验证计划

| 层次 | 现有验证 | 关键通过条件 |
|---|---|---|
| 前端契约 | `ChatAdoptNoteTarget.spec.ts` | 启动对话框而非直接请求；`host=目标` / `source_host=来源`；扁平笔记请求；错误信封和空态正确。 |
| 前端回归 | `PhaseBGateGuards.spec.ts`、AI 组件与 composable 选集 | 恢复的挂载不破坏宿主 gate；事件只按目标项目刷新。 |
| 后端 HTTP | `test_ai_chat_explicit_target_endpoints.py` | Pydantic 字段集合、授权分流、旧嵌套 host 422、错误信封。 |
| 后端 PG | `test_adopt_note_explicit_target.py` | 允许路径真正写入；拒绝路径无 receipt/文档/确认记录副作用。 |
| 后端回归 | `dsh_agent_panel`、`test_task7_adopt_fail_closed.py` | 权威消息读取、审计、失败回滚和模型字段守卫不回归。 |
| 类型 / 静态 | `scripts/typecheck-region.mjs`、诊断、守卫 | 没有新增类型错误；SSE function scope 和 event payload 契约保留。 |
| 变异 | 仅隔离 worktree 短暂注入再逐字节还原 | 无目标请求、跨宿主来源、对话框挂载和跨项目保存各有对应测试打红。 |
| 浏览器 | 【测试】项目、独立端口前端 | 见第 6 节，任何写入均可逐项清理。 |

PG 测试必须显式设置 `DATABASE_URL` 与 `GT_REQUIRE_PG=1`。若环境不可用，测试必须失败而不能把 `pg_only` skip 报为通过。

## 6. 浏览器验收与清理

只在【测试】项目操作。测试序列：

1. 在全局知识宿主点击“采纳”，确认未发送请求而弹出目标对话框；选择测试项目的底稿或附注章节并提交。
2. 检查目标项目的待确认横幅显示新记录，`ai_content_log` 为 pending，来源审计为 `global_knowledge`。
3. 在全局知识宿主选择多条回复，分别转存到项目笔记与可写知识库文件夹；检查地址、站内跳转和文档归属。
4. 在有项目的底稿或附注宿主测试就地采纳不弹框，再测试转存笔记位置被固定为本项目。
5. 用产品接口 reject 待确认内容、软删测试文档与仅本次创建的 AI 系统文件夹；若专为本次创建项目，再经项目回收站软删。保留不可逆审计和幂等收据。

## 7. 浏览器验收实测记录（2026-10-31）

环境：候选 worktree 前端 `127.0.0.1:3031` + 后端 `127.0.0.1:9980`（主工作区只镜像本 spec 的 4 个后端文件，与候选树逐字节一致，前端不镜像以免 HMR 改写他人页面）。
浏览器用独立隔离上下文，账号 admin。项目 `【测试】公式同步甲有限公司_2025`（`4c77f3e8-3938-4628-8836-1435dda4ddea`），底稿 `D2 应收账款审定表`（`a544a961-e30f-4a56-a012-fd127fea42dc`）。

| 路径 | 结果 | 取证 |
| --- | --- | --- |
| 全局知识宿主点「采纳」 | 通过 | 点击后请求记录里 adopt 调用数为 0，弹出标题「采纳到…」的对话框；选项目后才拉 `working-papers-all` |
| 选目标并提交 | 通过 | `POST /api/ai-chat/adopt` 请求体 `host.type=workpaper`、`source_host.type=global_knowledge`、`target_cell=恢复实测-D2-位置A`；提示语点名「项目 / 底稿」并说明需到待确认处确认 |
| 目标项目待确认 | 通过 | 横幅「该项目尚有 1 段 AI 生成内容待确认」；`ai_content_log.confirm_action=pending`、`target_cell=workpaper:<wpId>:<位置>`；`audit_log_entries` 的 `ai_content_adopt` 载荷 `source_host_type=global_knowledge`；`ai_chat_action_receipts` 幂等收据 `status=succeeded` 且 `result_resource_id` 指向该日志 |
| 转存笔记（项目） | 通过 | 请求体带 `target_project_id`、不带 `session_id`；落「【测试】…（项目资料）/ AI 对话笔记」，两级文件夹按需自动创建且 `project_ids` 只含该项目 |
| 转存笔记（知识库文件夹） | 通过 | 请求体带 `target_folder_id`（与 `target_project_id` 互斥）；位置「1」；深链 `/knowledge?folder_id=&doc_id=` 为站内相对路径、不带 `noopener`，新标签页经会话接力保持登录并自动选中文件夹 + 打开预览 |
| 底稿宿主就地采纳 | 通过 | 不弹任何对话框，直接提交；审计载荷 `source_host_type=workpaper` 且 `target_cell` 无位置后缀 |
| 底稿宿主转存笔记位置锁定 | 通过 | 只渲染固定文案「本项目的「AI 对话笔记」文件夹（首次保存时自动创建）」，无模式切换 / 项目选择器 / 文件夹选择器；请求体既无 `target_project_id` 也无 `target_folder_id` |
| `ai-content:adopted` 单点派发 | 通过 | 横幅保持展开（未重挂、未刷新页面）时再采纳一次，计数 2 段 → 3 段 |

附带确认的两条事实：

- 待确认明细的 `target_label` 现在真的有值（弹窗与 `GET /api/projects/{pid}/ai-content/pending` 都是「D2 应收账款审定表」）。原 spec 复盘里「底稿 target_label 恒空」的记录已过期，不要再按它判断。
- `tsconfig.json` 把 `lib` 从 `ES2022` 升到 `ES2023` 不是无关改动：`usePlatformAiChat.ts` 用了 `Array.prototype.findLastIndex`，不升 lib 区域 typecheck 必报缺声明。

复现到的既有限制（不是本次回归）：admin 不绕过知识库可见性。该测试项目唯一的 `project_assignments` 行指向 `staff_members.user_id` 为空的人员，因此没有任何用户是其成员；写进去的项目笔记 admin 自己看不到也删不掉，深链按设计给出「文档不存在或无权访问」+「文件夹不存在或无权访问」两条中文提示，不区分「存在但无权」与「不存在」。

## 8. 实测数据清理记录

| 对象 | 处置 | 核对 |
| --- | --- | --- |
| 3 条 `ai_content_log` | 1 条经横幅「❌ 拒绝」按钮，2 条经同一端点 `POST /api/ai-content/{id}/reject` | 该项目 pending 归零，三条全 `rejected`；对已拒绝的再拒一次正确返回 422「AI 内容已处理过」 |
| 文件夹「1」下的笔记 | `DELETE /api/knowledge-library/documents/{id}` | 200「文档已删除」 |
| 项目范围的 2 篇笔记 + 本次自动创建的 2 个文件夹 | 平台删除对 admin 恒 404（上述可见性限制），改用点名软删脚本 | 脚本带名称前缀与创建日期断言、落备份 JSON、打印回退 SQL；只按 4 个 id 置 `is_deleted` |
| 底稿宿主会话 | `DELETE /api/ai-chat/doc/workpaper/{id}/history` | 该会话消息清零；预先存在的全局知识会话 443 条未动 |
| 审计链与幂等收据 | 保留 | 哈希链不可逆，按设计不删 |

终局核对：知识库存活文档 0 条、存活文件夹 1 个，与实测前基线一致。

## 9. 用户批准的范围扩展（2026-10-31）

用户随后明确要求把本轮发现的他人欠账一并修复后再归档。扩展范围和处置如下：

| 欠账 | 实证根因 | 本轮处置 |
| --- | --- | --- |
| TSJ 结构化复核不进确认门禁 | 两处调用漏 `user_id`，`wrap_ai_output_with_log` 的五参写入门恒不满足；`AIContentMustBeConfirmedRule` 只读 `ai_content_log`。兼容端点还只回 parser 临时 UUID、从未调用持久层。 | `user_id` 改为两个服务入口的必填关键字参数；集中 `_log_ai_content` 以内外 SAVEPOINT 写入、核验真实 `ai_content_log_id`，失败整体回滚；`/ai/tsj-review` 接入该服务、返回日志 ID并加底稿 edit 门。 |
| 自动声明陈旧 | `components.d.ts` 是 `unplugin-vue-components` 的生成物，前端源码已用到 7 个组件但声明仍旧；`auto-imports.d.ts` 是悬空引用门禁的输入，陈旧会误报/漏报。 | 仅用当前 Vite 生成器重建；CI build 后检查两个 d.ts 没有未提交 diff。 |
| S32–S35 已提交代码引用未提交模块 | 4 个 bundle UI + 4 个状态 composable 引用了从未进入 Git 历史的 `BundleAssigneeDisplay.vue` / `bundleAssignee.ts`；干净 Vite build `Could not resolve`。 | 两个模块原子入库；同步修正同一次重构留下的 S34 测试/生产 API 分叉、PBT 模板口径和 TS7006。 |

没有扩大范围到清册中其余 73 个非 AI 完整丢失文件。救援标签、备份 refs 与历史目录删除仍需要用户另行确认。

## 10. 扩展范围的实现与验证

### 10.1 TSJ 日志与门禁

`_log_ai_content()` 是唯一调用点。它用真实的触发用户、目标底稿和 finding 位置调用包装器，在内层 SAVEPOINT 中检查非空 `ai_content_log_id` 对应同项目同用户的真实 pending 行。外层 SAVEPOINT 包住本次**全部** `AIContent` 与日志：包装器吞掉写异常、返回伪 ID或审计 DML 失败时，服务抛 `TsjConfirmationLogWriteError`，撤回本次记录；服务不 `commit` 也不 `rollback` 调用方事务，保存点的正常退出完成必要 flush。`POST /api/workpapers/{wp_id}/ai/tsj-review` 先过 `require_wp_edit_permission()`，把服务端 `LlmResponseParser` 的 `risk_level/category/location/suggestion` 显式投影为 TSJ 持久化 schema，调用 `process_review_response()` 并完成 finding 数量、每条日志 ID 和 DTO 校验后才做本请求唯一的 `commit`。任一后置校验或 commit 失败都 rollback 并返回 500/503，不能留下签字门禁看不见的 pending 内容。原有 mock 测试不再用 `AsyncMock` 伪装整个 `AsyncSession`，避免同步 `add()` / async context manager 被误建成未 await coroutine；真实 SQLite + PostgreSQL 用例验证成功、真实 DML 违例和服务返回后的 rollback 边界。

### 10.2 S bundle 与声明文件

四个 bundle 的生产动态入口在 `registry/entries/specialized.ts`，所以 Vite 在生产构建期而非用户点开页面后才会解析缺失模块。`BundleAssigneeDisplay` 有 assignment 时显示姓名和可访问性标签，无 assignment 时不渲染。`buildBundleAssigneeMap` 用 `wp_index` 返回的姓名 → 用户名 → ID 前八位回退。S34 的 `buildWpIdMap` 已拆成仅返回 wp_id 映射，测试改为独立验证新的负责人映射；C23 人工输入 / C24=F19 / C25=C24÷C23 的权威模板口径写入 PBT，次正规数反例和非对称夹具防止回归。模板内联回调收敛为 `hasTab(TabDef[], tabId)`，消除 vue-tsc 虚拟文件的 TS7006。

### 10.3 证据摘要

- TSJ：生产端点已接 `require_wp_edit_permission()` → 服务端 schema 投影 → `process_review_response()` → 真实 `ai_content_log.id` 回前端；服务只在外层 SAVEPOINT 内写入、既不 commit 也不 rollback 调用方事务，路由 DTO 校验后统一 commit。32 个单元 / router 测试、3 个真实 PG 测试（含 NOT NULL DML 违例、服务返回后 rollback、非日志异常保留调用方写入）在显式 PG 环境通过；10 个故障注入（漏 user_id、使参数可选 ×2、去外层 SAVEPOINT、不看真实行、丢位置、丢 wp_id、服务回滚调用方事务、路由通用分支不 rollback、路由在 DTO 校验前 commit）全部在预期断言打红。
- S bundle：4 个目录 + shared mapper + 组件接线共 325 例通过；8 个前端故障注入（C25 分母错引、导航 helper 反转、移走展示模块、删生成声明、S32/S33/S35 各自的接线丢失、共享映射器放行空负责人）全部打红，恢复后 d.ts gate 通过；共享 mapper 表驱动覆盖 S32/S33/S34/S35 四个前缀、子表和显示名三级回退。
- Vite：生产 build exit 0；连续两次 d.ts 输出 hash 完全一致。区域 vue-tsc 中 S34 的两条 TS7006 消失，只余 `GtAProgramConsole` 1 条、`apiProxy` 2 条既有错误。
- 浏览器：隔离 Vite 页实际加载并 mount 真实 `BundleAssigneeDisplay`，有 assignment 时显示「编制人测试编制人」和 `S34-16 编制人：测试编制人` aria-label；无 assignment 时只输出 `<!--v-if-->`；console error 为 0。数据库没有【测试】S34 项目且现有 S34 子稿的 `assigned_to` 都为空，未向共享库写入测试数据。

## 11. 非范围

- 清册中 A 循环 driver、D4、B23、生成物和清理脚本等 73 个非 AI 完整丢失文件，不在本次提交恢复。
- 主工作区另一份 `platform-performance-user-experience-closure` 未提交 WIP 不纳入：曾把它的 CI 新脚本误读成当前提交树的缺失 script，复核 `1154b99ca` 后确认旧 CI 只有重复 typecheck、没有调用那些 script。
- 前端「已提交源码 import 只能指向已提交文件」的专用扫描器没有纳入：第一版正则在测试里的假源码和跨行 import 上同时出现误报/漏报，不能以不可信门禁代替真实 Vite build。
- 备份 refs 和历史目录删除需要用户另行确认。
