# 设计：AI 面板「采纳」「转存笔记」选择目标位置与文件

## 1. 根因

| # | 现象 | 根因（已现读 + 浏览器复现） |
|---|---|---|
| D1 | 全局模式「采纳」404 | `adopt_message` 对 `host.project_id is None` / 无 adopt 动作直接 `ExternalNotFound`；前端无目标入口；`load_authoritative_message` 要求消息会话 == 授权宿主，换目标同样被拒 |
| D2 | 全局模式「转存笔记」前端拦截 | `useAiNoteCapture.saveAsNote` 判 `!host.projectId` 即返回；后端 `save_note` 只认宿主项目、保存位置写死 |
| D3 | 转存笔记在任何宿主恒 422 | 前端发嵌套 `host` + 无 `session_id`，后端要扁平字段 + 必填 `session_id`（`extra="forbid"`）；实测 422 缺 host_type / host_id / session_id |
| D4 | 跨项目转存 | `save_note` 只按 session_id + 属主读消息，不比会话项目与目标项目 |

## 2. 后端

### 2.1 采纳：显式来源宿主（`adopt.py` / `doc_ai_chat.py`）

- `AdoptRequest.source_host: AdoptHostRef | None`。不带或与 `host` 相同 ⇒ 现行同宿主路径，一行不变。
- 路由：带且不同 ⇒ `source = _authorize_doc_host(source_host, action=history, entrypoint="ai_chat.adopt.source")`；目标仍按 `adopt` 授权；`adopt_message(..., source_host=source)`。
- `adopt_message` 新参数 `source_host`：不同宿主时先过 `_assert_cross_target(source, target)`：
  - `source.resource_type ∈ CROSS_TARGET_SOURCE_TYPES = {global_knowledge, report, knowledge_doc, knowledge_folder}`（自身不能当采纳目标的宿主；底稿 / 附注会话保持严格绑定，`test_message_bound_to_another_host_or_project_is_rejected` 继续成立）
  - `target.resource_type ∈ ADOPT_TARGET_TYPES = {workpaper, note}`
  - `source.project_id is None or source.project_id == target.project_id`
  - `source.principal_id == target.principal_id`
  - 违规 ⇒ `audit_denial(host_context_mismatch, entrypoint="ai_chat.adopt.cross_target")` + `ExternalNotFound`，先于任何读写。
- `load_authoritative_message(host=source or target)`：消息归属链对**来源会话**校验，正文 / 哈希规则不变。
- 审计 `ADOPT_AUDIT_DETAIL_KEYS` 增 `source_host_type` / `source_host_id`（守卫按常量比对，同步更新）。

安全论证：全局会话在 `mention_service` 里项目类资源一律 `project_required`、ContextBuilder 不检索项目数据 ⇒ 正文不含任何项目数据，采纳到用户有写权的目标不构成跨项目泄漏；报表 / 带项目的知识库会话限定同项目。

### 2.2 笔记：保存位置（新模块 `ai_chat/note_target.py`）

```
resolve_note_source(db, actor_id, message_ids, session_id) -> NoteSource(session_id, project_id)
resolve_note_target(db, user, host, source, target_project_id, target_folder_id) -> NoteTarget
NoteTarget(kind=project|folder, project_id, folder_id, access_level, project_ids) + ensure_folder(db)
folder_location_label(db, folder_id) -> "A / B / C"
```

规则顺序（全部在 claim 收据之前）：二选一 → 会话项目范围（有项目则只能本项目、不能文件夹）→ 授权 → 存在性。
- 项目目标：`ResourceAccessResolver.authorize_project(user, pid, note_create)`（新增公共方法 = 角色上界 + `_authorize_project_resource`，异常 fail-closed）+ `Project` 存在；文件夹 = `ensure_project_folder(pid, "ai_notes")`。
- 文件夹目标：`resolve_subject` + `load_folder_permission` + `KnowledgeWritePolicy.can_create`（与 `knowledge_folders._authorize_folder_create` 同口径）；文档 `access_level=None`（继承文件夹）。
- 默认：宿主项目；`host.allows(note_create)`；宿主无项目 ⇒ `no_target`。

路由：`session_id` 可选；新增 `target_project_id` / `target_folder_id`；有显式目标时来源宿主按 `history` 授权（目标授权在服务里），否则保持 `note_create`；响应加 `location`。

### 2.3 错误码（笔记，均 422，中文 message）

| code | 含义 |
|---|---|
| `mixed_sessions` | 所选回复来自不同对话，请分开保存 |
| `ambiguous_target` | 保存位置只能选择一个 |
| `no_target` | 请选择笔记保存位置 |
| `target_out_of_scope` | 该对话属于项目，只能保存到本项目的笔记 |
| `target_denied` | 所选保存位置不存在或无权访问（不区分不存在与无权） |
| `messages_not_found` / `no_messages` / `empty_name` / `action_denied` / `concurrent_save` | 沿用 |

## 3. 前端

- `useAiHostContext.canAdoptInPlace(host)`：`workpaper|note` 且有项目。
- `usePlatformAiChat.adoptContent(messageId, target?)`：`target={host, targetCell?, label?}` 时 `host=目标`、`source_host=当前宿主`、`target_cell`。
- `useAiNoteCapture.saveAsNote({name, target})`：不再内置 `ElMessageBox.prompt`（名称与位置由对话框确认）；请求体扁平对齐后端；`target` = `host_project | project | folder`；幂等键指纹 = 消息 ID + 名称 + 位置；`retrySaveAsNote` 复用上次名称与位置。
- `ChatAdoptTargetDialog.vue`：项目（`listProjects`）→ 底稿（`listWorkpapers`）/ 附注章节（`getDisclosureNoteTree`，年度取 `audit_year`，缺则取期末日年份）→ 可选位置；来源有项目时锁定。
- `ChatNoteSaveDialog.vue`：名称 + 位置；有项目宿主只读展示；无项目宿主「项目笔记 | 知识库文件夹」，文件夹用 `el-tree-select`（`can_create=false` 禁选），知识库文件夹宿主默认当前文件夹。
- 面板：可就地采纳走原路径，否则开采纳对话框；转存笔记开笔记对话框；成功通知带「在知识库中查看」链接（用户点击打开新标签，不再 `window.open` 自动弹）。两个对话框均 `append-to-body`、打开时才加载数据。

## 4. 文件与行数预算

| 文件 | 现行数 | 预算 |
|---|---|---|
| `routers/doc_ai_chat.py`（白名单 1324，上限 ×1.05≈1390） | 1325 | ≤ +40 |
| `services/ai_chat/adopt.py` | 650 | ≤ 760 |
| `services/ai_chat/access.py` | 731 | ≤ 780 |
| `services/ai_chat/note_service.py` | 404 | ≤ 480 |
| `services/ai_chat/note_target.py`（新） | — | ≤ 260 |
| `PlatformAiChatPanel.vue` | 1075 | ≤ 1200 |

## 5. 测试

- PG（`dsh_agent_panel` 回滚夹具，真实 HostContextResolver / 授权 / 写入）：采纳跨宿主 允许 2 + 拒绝 5（隐式不带来源、底稿来源、跨项目、目标类型、不同主体）；笔记 允许 3 + 拒绝 8，含零副作用（文档 / 收据 / 确认流行数）。
- 路由契约：`AdoptRequest` / `NoteSaveRequestBody` 字段集合。
- 前端：两个 composable 请求体（字段从 `doc_ai_chat.py` 解析对账）、面板分流（可就地采纳不弹框、全局弹框）、对话框提交载荷。
- 变异：去掉跨宿主任一条规则、去掉会话项目范围校验、去掉文件夹授权 ⇒ 对应用例打红。

## 6. 实施记录与复盘（2026-10-21，未提交）

### 6.1 验证证据（可复现）

后端（cwd=`backend`）：
- `test_adopt_note_explicit_target.py` 20 passed（真实 PG 回滚夹具）：采纳允许 2 / 拒绝 5；笔记允许 3 / 拒绝 10（§5 预估拒绝 8 条）。
- `test_ai_chat_explicit_target_endpoints.py` 7 passed（TestClient；含旧嵌套 host 形状必 422）。
- 回归 `tests/dsh_agent_panel` + `test_doc_ai_chat_{integration,pbt,router}` + `test_doc_ai_context_builder` + `test_ai_chat_*`（6 个）+ `test_ai_note_capture_pg` + `test_knowledge_folder_create_upload`：860 passed。3 条警告都与本 spec 无关（schemathesis / jieba 弃用提示，`persistence.py:353` 的 SAWarning）。
- 磁盘变异 18/18 KILLED，每条都确认红在预期用例上，文件逐字节恢复。A1~A4 对应跨宿主四条规则，A5 归属链，A6/A7 路由来源授权，N1~N9 笔记位置规则，R1/R2 路由授权与位置透传。脚本放在仓库外的 `~/.gt_probes/adopt_note/mutate.py`。

前端（cwd=`audit-platform/frontend`）：
- `vitest run src/components/ai src/composables/__tests__/useAiHostContext.spec.ts src/composables/__tests__/useDocAiChat src/composables/__tests__/useAiCapabilities.spec.ts src/views/__tests__/KnowledgeBase.deepLinkAndGating.spec.ts src/components/layout/__tests__/FourColumnCatalog.chapterLabels.spec.ts`：23 文件 409 passed。
- 磁盘变异 12/12 KILLED（F1~F12，含附注年度写死、404 当失败、查看入口放行外链）；tsc 变异 4/4 KILLED。
- `vue-tsc -p tsconfig._ai-adopt-note.json` 只剩 `usePlatformAiChat.ts` 的 `findLastIndex`。它在 HEAD 的 L415 就有。`findLastIndex` 属 ES2023，而主 tsconfig 的 `lib` 同为 ES2022，所以不是单区域配置引入的。eslint 0。
- 门禁：`check_file_size.py` 对 19 个改动文件 exit 0（见 §6.4 第 6 条）；U+FFFD 0 处；gitleaks 无泄漏；白名单格式守卫 13 passed。

### 6.2 浏览器实测（chrome-devtools 隔离上下文，`/projects` 全局模式）

- 采纳到【E2E】公式管理运行时门禁_2025 / D2-1，位置 E5：`ai_content_log` 状态 pending，`target_cell=workpaper:e862981a…:E5`，审计来源 `global_knowledge`、目标 `workpaper`，待确认接口能列出这条。
- 转存到项目笔记：位置显示「…（项目资料） / AI 对话笔记」。转存到知识库文件夹「1」：成功。「在知识库中查看」打开的新标签保持登录。
- 附注：E2E 项目附注未生成，显示「该项目 2025 年度尚未生成附注」，没有全局弹窗；和平药房_2025 能只读列出 166 章，但未提交采纳。
- 清理：采纳日志 `b7e4387a` 走 API reject；文档 `29c45669` / `18c245ff` 软删；系统文件夹 `528223ac` / `567cfa51` 经 `KnowledgeFolderService.delete_folder` 软删（admin 不是成员，路由删不了，见 §6.3）。收据与审计条目按 append-only 保留。

第二轮（补测首轮未覆盖的三条，tasks 7.1）：用一次性脚本建专用项目「【测试】AI采纳笔记验收有限公司_2025」。建项走 `project_wizard_service.create_project`，附注走 `DisclosureEngine.generate_notes`（166 章，不调大模型），admin 加为项目成员，再建一张 D2-1 底稿。E2E 夹具不再碰。

| 路径 | 页面表现 | 落库 / 审计 |
|---|---|---|
| 底稿宿主就地采纳 | 不弹框；提示「已提交采纳：请在本页「AI 生成内容待确认」中确认后生效」 | `target_cell=workpaper:<底稿>`，pending；审计 `host_type = source_host_type = workpaper`，ID 相同 |
| 有项目宿主转存笔记 | 对话框固定显示「本项目的「AI 对话笔记」文件夹（首次保存时自动创建）」；成功页显示名称与「…（项目资料） / AI 对话笔记」；「在知识库中查看」打开即见该笔记 | 文档落在 `system_key=project:<项目>:ai_notes` 文件夹，`access_level=project_group` |
| 全局模式采纳到附注章节 | 项目 →「附注章节」→ 列出 166 章 → 选「八、1 货币资金」，位置填「正文第一段」；提示写明「项目 / 八、1 货币资金」 | `target_cell=note:<章节>:正文第一段`；审计来源 `global_knowledge` → 目标 `note` |
| 附注宿主就地采纳 | 附注编辑页「AI 助手 → AI 对话」，点「采纳」不弹框 | `target_cell=note:<章节>`；审计 `note → note`，ID 相同 |

三条待确认都能在 `GET /api/projects/{id}/ai-content/pending` 里列出。附注宿主那次的成功提示没截到：该请求在共享后端排队约 56 秒才被处理（服务端耗时 1.4 秒，同时段页面其他轮询也在中止），接口返回与落库已核对。清理全部走产品接口：3 条 reject、文档与 2 个系统文件夹删除（admin 是成员，路由可删）、2 个测试项目软删。底稿占位 xlsx 已删，收据与审计条目保留。

### 6.3 偏差与已知限制

- `note_target.py` 288 行，超出 §4 预算 260 行（仍低于 800 行门禁）。其余文件都在预算内：路由 +24、`adopt.py` 750、`access.py` 769、`note_service.py` 386（删死代码后变小）、面板 1143。
- admin 不是项目成员时：`authorize_project` 让 admin 免成员校验，能把笔记写进该项目；但知识库可见性规则是 admin 不绕过，所以 admin 写完看不到，也不能通过路由删除（404）。暂按已知限制处理，提示文案写「仅该项目成员可在知识库中查看」。要不要改成拒绝写入，需要产品拍板。
- 首轮未浏览器实测的三条（底稿 / 附注宿主就地采纳、有项目宿主转存笔记、提交采纳到附注章节）已在第二轮用专用【测试】项目补测通过，见 §6.2。
- 「在知识库中查看」去掉了 `noopener`，因为新标签要继承 sessionStorage 里的令牌。只放行站内路径（以 `/` 开头且不是 `//`），同源页面互相本来就能访问，所以不新增反向标签劫持风险。

### 6.4 复盘教训

1. 面板的采纳（`/api/ai-chat/adopt`）与转存笔记（`/api/ai-chat/notes`）请求用 fetch 直连，不经过 http 拦截器，错误必须按平台真实信封解析：业务 HTTPException 是 `{code:<HTTP 状态数字>, message:{code, message}}`，ExternalNotFound 是 `{code:404, message:"资源不存在或不可访问"}`，校验失败是 `{code:422, message:"请求参数校验失败", detail:[…]}`。业务码在 `message.code`，不在外层 `code`。实现见 `aiChatWireError.ts`。
2. 转存笔记的请求体在任何宿主下都恒 422，原因是唯一的前端守卫（Property 21）只数调用次数、比幂等键，不看请求体形状。现在改为跨语言契约：前端测试直接解析 `doc_ai_chat.py` 的 pydantic 模型取必填字段集合来比对，后端 TestClient 再钉住「旧形状必 422」。
3. `window.open(…, 'noopener')` 打开的新标签不会复制 sessionStorage，令牌丢失，直接跳到登录页。
4. 附注未生成时后端返回 404「附注数据不存在，请先生成附注」，这是空态，不是加载失败：调用方传 `_silent` 后自行提示。
5. 在共享开发环境上做磁盘变异会污染其他会话。前端：Vite（3030）HMR 会把变异版推给所有已打开的浏览器，实测 F10（附注年度写死）被推到了实测页，硬刷新后才恢复。后端：start-dev 带 `--reload --reload-dir app`，变异窗口内共享的 9980 跑的就是去掉规则的代码。今后变异一律在独立 worktree 里跑，或者先把浏览器停在 about:blank。
6. 行数门：`test_task7_adopt_fail_closed.py` 在 HEAD 就有 1431 行且未登记白名单，改一行 pre-commit 就会拒。先前记的「`check_file_size` exit 0」用的文件清单只含源码，漏了这个被改动的旧测试。现已登记白名单：基线 1433，写明拆分方向。教训：核对门禁的文件清单必须等于将要提交的全部文件。
7. chrome-devtools 的「当前页」在所有会话间共享：别的会话不带 pageId 的导航会落到你刚建的页上。实测第二轮点「发送问题」那一刻，页面被带到另一个项目的合并页，问题发到了全局会话。关键点击前，先在同一个脚本里校验 `location.pathname`。
8. 写入型验收缺少合适项目时，用平台同一路径临时建【测试】项目，比在 E2E 夹具或真实项目上冒险更稳；用完走项目删除接口软删。

### 6.5 提交须带的文件（未提交）

- 后端修改：`routers/doc_ai_chat.py`、`services/ai_chat/{access,adopt,note_service}.py`、`tests/dsh_agent_panel/test_task7_adopt_fail_closed.py`、`scripts/file_size_whitelist.txt`（只追加 test_task7 一段）。
- 后端新增：`services/ai_chat/note_target.py`、`tests/dsh_agent_panel/test_adopt_note_explicit_target.py`、`tests/test_ai_chat_explicit_target_endpoints.py`。
- 前端修改：`components/ai/PlatformAiChatPanel.vue`、`components/ai/__tests__/PhaseBGateGuards.spec.ts`、`composables/{useAiHostContext,useAiNoteCapture,usePlatformAiChat}.ts`、`services/auditPlatformApi.ts`（只改 `getDisclosureNoteTree`）、`components.d.ts`（只带 `ChatAdoptTargetDialog` / `ChatNoteSaveDialog` 两行，其余 El* / Formula* / ModelRoutePanel 属于并发会话）。
- 前端新增：`components/ai/{ChatAdoptTargetDialog.vue,ChatNoteSaveDialog.vue,chatTargetOptions.ts}`、`composables/aiChatWireError.ts`、`components/ai/__tests__/ChatAdoptNoteTarget.spec.ts`、`tsconfig._ai-adopt-note.json`。
- 文档：本 spec 三件套、`.kiro/specs/INDEX.md` 本条与统计行、`.kiro/steering/memory.md` 本条。这两个共享文件的工作树里还有并发会话未提交的改动：INDEX.md 有 a-cycle-online-edit-driver-closure / frontend-test-network-isolation-and-load-dedup / formula-manager-runtime-integrity-closure 三行，memory.md 有其他小节的改动。提交时按块只挑本 spec 的部分。另外，工作树 INDEX.md 里 dsh-kb-ocr-local-first-routing / preexisting-test-failures-closure 两行原是归档前的旧版本（链接指向已不存在的目录），原样提交会回退 HEAD `8bfe70c1d` 的归档记录，已按 HEAD 同步回 `_archive/53`、`_archive/54` 的版本。
- 不要带：`useAiCapabilities.spec.ts`（`isRequestCancelled` mock，10-19 的并发会话改动），以及 `useEditorMode` / `useEditingLock` / `useFormulaImportExport` / `formula/useFormulaSettings` 等其他改动。

### 6.6 第二轮复盘：确认流写回 + 目标标签 + 编辑器刷新（2026-10-21，未提交）

承 §6 第一轮交付后，应用户「再复盘，是否还有改进建议」要求对**确认 / 修订 / 拒绝 → 写回**链路做了第二轮审查，查到 6 个缺陷 + 2 处勘误，全部已修并有测试 + 变异 + 单区域 tsc 证据（浏览器实测受环境阻塞，见下）。

#### 6.6.1 修复的 6 个缺陷

1. **安全漏洞（P0）：`/api/ai-content/{id}/confirm|revise|reject` 无项目鉴权。** 任意登录用户可确认 / 写回他人项目的 AI 内容到附注。修复：三个端点统一经 `_confirm_or_revise` / `reject` 先 `assert_project_permission(db, user, log.project_id, "review")`（确认 / 修订 / 拒绝都是复核动作，取 review 级，与 `assignment_service.ROLE_MAP` 一致，admin 免成员校验）。已被 `test_project_endpoint_authorization_baseline.py`（29 passed）识别为项目级鉴权端点。
2. **绕过协调器：确认后裸赋值 `text_content`。** 上一版直接把 AI 文本赋给 `note.text_content`，不盖「最近一次编辑」、不发事件、不走协调器语义。修复：`_writeback_note` 改调 `DisclosureEngine.update_note(note_id, text_content=appended, user_id=user.id)`，正文以 `\n\n---\n\n` 追加而非覆盖；写回成功后发 `NOTE_SECTION_SAVED`（带 project_id / note_year / note_section）供附注刷新与下游失效。
3. **编辑器旧内容覆盖：确认写回后编辑器未刷新。** 用户在附注编辑页确认 AI 内容后，编辑器仍持旧正文，随后保存会用旧草稿盖掉刚写入的 AI 文本。修复：`DisclosureEditor.vue` 的 `AiContentPendingBanner` 加 `@resolved="onAiContentResolved"`；该函数在当前章节有未保存改动时先 `ElMessageBox.confirm` 警告（放弃本地改动并刷新 / 保留本地改动），否则直接 `fetchDetailFresh(section)` 拉最新正文。
4. **锁定仍标「已确认」内容丢失。** 合并锁定 / 无 edit 权限时，上一版把日志标为 confirmed 但附注没写进去，内容静默丢失。修复：`_writeback_note` 遇 edit 无权（403）或合并锁（`check_consol_lock` → 423）时 `db.rollback()` 回滚状态流转、保持 pending，并回传 `writeback:{written:false, skipped:true, reason}`（中文原因）；前端横幅 `_handleConfirmResult` 见 `skipped` 即 `ElMessage.warning(reason)`、不移出列表、不发 `resolved`。
5. **revise 不写回。** 上一版修订端点只改 `revised_content`、不触发写回。修复：`revise` 与 `confirm` 共用 `_confirm_or_revise`，附注类写入时取 `revised_content`（优先于 `generated_content`）。
6. **`target_label` 全 None。** `_enrich_target_labels` 用 UUID 对象做 dict key 写、用 `str(log.id)` 查 ⇒ 全 miss；且 `wp_of_log` / `note_of_log` 不允许多条日志指向同一目标。修复：统一用 `str(log.id)` 做 key，允许多条指向同一目标；`list_pending_ai_content` 把 enrich 包进 `async with db.begin_nested()` try/except，失败降级 None 而非毒化事务 500。真库探针证实修复后三条待确认都拿到标签（原全 None）。

**底稿类不自动写入（设计裁定，非缺陷）：** AI 文本无行列坐标、`target_cell` 的位置是自由文本，无法安全写回底稿 `parsed_data`（需选 sheet/cell + 构造 html_data + 过 CAS，非 confirm 端点职责）。改为：确认成功但 `writeback:{written:false, reason:"底稿内容不自动写入，请在底稿页面复制到目标位置"}`，前端提示复制。

#### 6.6.2 勘误（修正 §6 两处不实陈述）

- **勘误 A：** §6.1 称后端回归「860 passed」覆盖确认写回链路——实际第一轮并未对 confirm/revise/reject 的写回与鉴权建任何用例（P0 安全漏洞因此潜伏）。本轮新建 `test_ai_content_confirm_writeback.py`（7 passed，SQLite 内存库）专门守护：review 鉴权、edit 无权保持 pending、合并锁保持 pending、附注追加写、revise 写 revised_content、底稿不写、target_label enrich。
- **勘误 B：** 上一版把 429（限流）当作「本就进入写回分支」描述，但限流在 `_confirm_or_revise` 之前由中间件拦截，确认端点内部不处理 429；该描述删除，避免误导。

#### 6.6.3 本轮验证证据

- 后端（cwd=`backend`，`..\.venv\Scripts\python.exe -m pytest <file> -q -p no:cacheprovider`）：`test_ai_content_confirm_writeback.py` 7 passed、`test_ai_content_router.py` 8 passed、`test_project_endpoint_authorization_baseline.py` 29 passed、`test_disclosure_note_edit_stamp.py` + `test_note_edit_stamp_writers.py` 60 passed。
- 后端变异：`~/.gt_probes/adopt_note/cw_mutate.py` 4/4 KILLED（CRLF-aware，逐字节恢复）：摘掉 review 鉴权 / 摘掉 edit 校验 / 摘掉合并锁 / target_label 改回 UUID key，各自红在对应用例。
- 前端（cwd=`audit-platform/frontend`）：`AiContentPendingBanner.spec.ts` 14 passed（新增 6 例：pending+skipped 警告不移出、written 成功含章节、底稿 written=false 提示复制、eventBus `ai-content:adopted` 同项目重拉 / 异项目不拉、复制按钮调 clipboard）；5 文件 63 passed 无回归。
- eslint 0 error；`AiContentPendingBanner.vue` 0 warning（去掉 `confirm_action === 'pending'` 字面量，改用后端权威 `writeback.skipped`，消除 `no-status-string-literal`）；`DisclosureEditor.vue` 12 warning 全部 HEAD 预存（`git stash` 对比确认我的 `onAiContentResolved` 加了 0 条新 warning）。
- `check_file_size.py backend/app/routers/ai_content.py` exit 0（437 行）。
- 单区域 `tsconfig._ai-adopt-note.json` 加入 `AiContentPendingBanner.vue` + 其测试 + `eventBus.ts`，`vue-tsc` 0 error；变异 `tsc_mutation_banner.py` 注入 `const _bad:number='x'` ⇒ KILLED（TS2322），逐字节恢复。`DisclosureEditor.vue` 不纳入单区域（其 import 图带出 19 个预存无关错误，已 `git stash` 对比确认全部 HEAD 已存在、与本轮改动无关），其类型安全由编辑器内 `get_diagnostics` 覆盖（0 诊断）。

#### 6.6.4 本轮改动文件（并入 §6.5 提交清单）

- 后端修改：`routers/ai_content.py`（新增 `_load_log_or_404` / `_note_target_id` / `_writeback_note` / `_note_saved_event` / `_confirm_or_revise`；confirm/revise/reject 接鉴权与写回；`_enrich_target_labels` 修 key；`list_pending_ai_content` 包 savepoint；导入 `assert_project_permission` / `check_consol_lock`）。
- 后端新增：`tests/test_ai_content_confirm_writeback.py`。
- 前端修改：`components/ai/AiContentPendingBanner.vue`（`_handleConfirmResult` 分流 + 复制 + eventBus 刷新）、`components/ai/__tests__/AiContentPendingBanner.spec.ts`（+6 例、加 post/ElMessage/eventBus mock）、`views/DisclosureEditor.vue`（`@resolved` + `onAiContentResolved`）、`composables/usePlatformAiChat.ts`（发送失败带 `err.reason` 中文原因）、`tsconfig._ai-adopt-note.json`（include 扩 banner / test / eventBus）。
- 流程更正（非产物）：回退了第一轮越权改动的 12 个他 spec 的 tsconfig（`git checkout` 还原 11 个 tracked + 手动把 untracked `tsconfig._formula-settings.json` 从 ES2023 改回 ES2022；后者属并发会话未提交文件）。

#### 6.6.5 本轮未完成 / 待拍板

- **浏览器实测受环境阻塞：** 后端 9980 健康（200），但前端 3030 开发服务器未响应（共享环境，当前会话不自行启动 `start-dev.bat`）。确认写附注（edit 成员）、锁定 / 非成员保持 pending、底稿复制按钮、横幅 `@resolved` 实时刷新四条路径的浏览器实测挂起，待前端起来后补。静态 + 单测 + 变异已覆盖这些分支的逻辑。
- **待产品拍板（承 §6.3）：** admin 非项目成员时可写入但看不到 / 删不掉（已知限制）；底稿是否改为真正写回 `parsed_data`（当前复制方案）。
