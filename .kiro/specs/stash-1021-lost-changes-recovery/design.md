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

## 9. 非范围

- 清册中 A 循环 driver、D4、B23、生成物和清理脚本等 73 个非 AI 完整丢失文件，不在本次提交恢复。
- `tsj_structured_output_service` 未传 `user_id` 因而不写 AI 内容日志，是独立问题，不能在本次借题扩大范围。
- 备份 refs 和历史目录删除需要用户另行确认。
- `components.d.ts` 在当前 origin 上是陈旧的：跑一次 Vite 就会补出 `ElImage` / `ElScrollbar` 两条，而这两个组件用在 `AttachmentPreviewCore.vue` / `DisclosureEditor.vue` 等本次未改的文件里。属别人提交时没重生成生成物，本次不混进来（按「生成文件不取并集」处置，已丢弃该工作区改动）。
