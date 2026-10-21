# 任务：AI 面板「采纳」「转存笔记」选择目标位置与文件

> 2026-10-21 实施完成，**未提交**（提交须带的文件见 design §6.5）。证据命令与范围见 design §6.1。
> 2026-10-21 第二轮复盘又修 6 缺陷 + 2 勘误（R1~R6 完成，R7 浏览器实测待环境），见文末「第二轮复盘修复」节与 design §6.6；追加文件见 §6.6.4。

- [x] 1. 后端采纳显式来源宿主（`AdoptRequest.source_host` + `adopt_message(source_host)` + 跨宿主四条规则 + 审计来源字段）
  - _需求：R2_
  - 证据：`adopt.py` 新增 `ADOPT_TARGET_TYPES` / `CROSS_TARGET_SOURCE_TYPES` / `_assert_cross_target`（违规 ⇒ `audit_denial(entrypoint="ai_chat.adopt.cross_target")` + 不可枚举 404，先于任何读写）；`ADOPT_AUDIT_DETAIL_KEYS` 增 `source_host_type` / `source_host_id`；路由带不同来源时按 history 授权（`ai_chat.adopt.source`）。PG 用例允许 2 + 拒绝 5 全绿

- [x] 2. 后端笔记保存位置（`note_target.py` + `save_note` 目标参数 + `authorize_project` + 路由 `session_id` 可选 / 目标字段 / `location`）
  - _需求：R4_
  - 证据：新模块 `note_target.py`（`resolve_note_source` / `resolve_note_target` / `NoteTarget.ensure_folder` / `folder_location_label`）；`access.authorize_project`；`save_note` 校验全部在 claim 收据之前；删死代码 `_ensure_notes_folder`。PG 用例允许 3 + 拒绝 10（含缺陷 D4 回归、知识库宿主项目断言补判权）全绿，每条拒绝断言错误码 + 零副作用

- [x] 3. 后端测试：PG 回滚夹具覆盖采纳跨宿主与笔记位置的允许 / 拒绝 / 零副作用；路由模型字段集合；既有守卫回归；变异证明
  - _需求：R5.1_
  - 证据：`test_adopt_note_explicit_target.py` 20 passed（真实 PG）；`test_ai_chat_explicit_target_endpoints.py` 7 passed（TestClient，含旧嵌套 host 形状必 422）；`test_task7_adopt_fail_closed.py` 字段集合加 `source_host`；回归 860 passed；磁盘变异 18/18 KILLED（逐字节恢复）

- [x] 4. 前端 composable：`adoptContent(messageId, target)`、`saveAsNote({name, target})` 扁平请求体 + 幂等指纹、`canAdoptInPlace`
  - _需求：R1、R3、R4.1、R4.5_
  - 证据：`aiChatWireError.ts`（按平台真实错误信封取业务码与中文原因）；`useAiHostContext.canAdoptInPlace`；不可就地采纳且无目标 ⇒ `adopt_target_required` 不发请求；笔记请求体扁平、不发 `session_id`，指纹 = 消息 ID + 名称 + 位置

- [x] 5. 前端对话框与面板接线：`ChatAdoptTargetDialog.vue`、`ChatNoteSaveDialog.vue`、成功通知「在知识库中查看」
  - _需求：R1、R3_
  - 证据：两个对话框 + `chatTargetOptions.ts`（加载器复用既有 service）；`getDisclosureNoteTree` 加可选 `config`（附注未生成的 404 当空态静默）；「在知识库中查看」只放行站内相对路径

- [x] 6. 前端测试：请求体跨语言契约（解析 `doc_ai_chat.py`）、面板分流、对话框载荷；修 Property 21；eslint + 单区域 tsc
  - _需求：R5.2_
  - 证据：`ChatAdoptNoteTarget.spec.ts` 21 例；Property 21 改测新 API；回归 23 文件 409 passed；磁盘变异 12/12 KILLED；`tsconfig._ai-adopt-note.json` 只剩 HEAD 预存的 `findLastIndex`（HEAD L415）；tsc 变异 4/4 KILLED；eslint 0

- [x] 7. 浏览器实测：全局模式采纳到底稿、转存到项目笔记 / 知识库文件夹，核对落库后清理（原范围中未实测的三条拆到 7.1）
  - _需求：R5.3_
  - 证据（chrome-devtools 隔离上下文，`/projects` 全局模式）：采纳到【E2E】公式管理运行时门禁_2025 / D2-1（E5）⇒ `ai_content_log` pending、`target_cell=workpaper:…:E5`、审计来源 `global_knowledge`、待确认列表可见；转存到项目笔记与知识库文件夹「1」均成功，位置显示正确，「在知识库中查看」新标签保持登录；E2E 项目附注空态提示正确。清理：采纳日志走 API reject；2 份笔记文档与 2 个系统文件夹软删；收据与审计条目按 append-only 保留
  - [x] 7.1 浏览器补测（2026-10-21 第二轮）：底稿 / 附注宿主就地采纳、有项目宿主转存笔记、实际提交采纳到附注章节
    - 证据（专用【测试】项目「【测试】AI采纳笔记验收有限公司_2025」，按平台建项 + 生成附注 166 章 + admin 为成员；不再碰 E2E 夹具）：底稿宿主点「采纳」不弹框，提示「已提交采纳：请在本页「AI 生成内容待确认」中确认后生效」，落库 `target_cell=workpaper:<底稿>`、审计来源 = 目标 = workpaper；同页转存笔记，对话框固定显示「本项目的「AI 对话笔记」文件夹」，保存后位置「…（项目资料） / AI 对话笔记」，「在知识库中查看」打开即见该笔记；全局模式采纳到「八、1 货币资金」（位置「正文第一段」），落库 `target_cell=note:<章节>:正文第一段`、审计来源 global_knowledge → 目标 note；附注编辑页「AI 对话」里点「采纳」不弹框，落库 `target_cell=note:<章节>`、审计来源 = 目标 = note。三条待确认均出现在 `/ai-content/pending`
    - 附注宿主那次的成功提示没截到：请求在共享后端排队约 56 秒（服务端处理 1.4 秒，同时段其他轮询也在中止），落库、审计和接口返回均已核对
    - 清理：3 条采纳走 API reject（待确认归零）；笔记文档与 2 个系统文件夹走知识库删除接口；2 个测试项目走项目删除接口软删；底稿占位文件已删；收据与审计条目按 append-only 保留

- [x] 8. 收尾：证据回填、INDEX.md 登记、memory 记录
  - 证据：本文件；design §6；INDEX.md 登记；memory 条目；`test_task7_adopt_fail_closed.py` 登记行数门白名单（触碰前已 1431 行且未登记，见 design §6.4）

---

## 第二轮复盘修复（2026-10-21，未提交）

> 承第一轮交付后对「确认 / 修订 / 拒绝 → 写回」链路再复盘，查到 6 缺陷 + 2 勘误。详见 design §6.6。证据命令同 §6.1 口径。

- [x] R1. 后端：confirm/revise/reject 接项目鉴权（review 级）+ 附注类经 `DisclosureEngine.update_note` 追加写回 + 合并锁 / edit 无权保持 pending + revise 写 revised_content + 底稿类不自动写
  - _缺陷 1/2/4/5_
  - 证据：`ai_content.py` 新增 `_confirm_or_revise` / `_writeback_note` / `_note_saved_event` / `_load_log_or_404` / `_note_target_id`；`test_ai_content_confirm_writeback.py` 7 passed；`test_project_endpoint_authorization_baseline.py` 29 passed（识别为项目级鉴权）；变异 `cw_mutate.py` 4/4 KILLED
- [x] R2. 后端：`target_label` enrich 修 key（`str(log.id)`）+ 允许多条指向同一目标 + `list_pending_ai_content` 包 savepoint 降级
  - _缺陷 6_
  - 证据：真库探针三条待确认都拿到标签（原全 None）；enrich 失败降级 None 不毒化事务
- [x] R3. 前端：横幅 `_handleConfirmResult` 按 `writeback.skipped` / `written` 分流（pending 警告不移出 / 写附注成功含章节 / 底稿提示复制）+ eventBus `ai-content:adopted` 刷新 + 复制按钮
  - _缺陷 4（UI 侧）_
  - 证据：`AiContentPendingBanner.vue`；`AiContentPendingBanner.spec.ts` 14 passed（+6 例）；eslint 0 warning（去 `confirm_action === 'pending'` 字面量改用 `writeback.skipped`）
- [x] R4. 前端：编辑器 `@resolved="onAiContentResolved"` 刷新当前章节；有未保存改动先 `ElMessageBox.confirm` 警告
  - _缺陷 3_
  - 证据：`DisclosureEditor.vue`；`get_diagnostics` 0 诊断；HEAD 对比加 0 条新 eslint warning
- [x] R5. 前端：发送问题失败显示中文原因（`err.reason`）
  - 证据：`usePlatformAiChat.ts` `sendMessageNewApi` catch 用 `(e?.reason as string) || 兜底`
- [x] R6. 勘误：修正 §6 两处不实陈述（A 第一轮无 confirm 写回 / 鉴权用例、B 429 描述删除）
  - 证据：design §6.6.2
- [ ]* R7. 浏览器实测四条路径（确认写附注 / 锁定保持 pending / 底稿复制 / 横幅实时刷新）—— 前端 3030 未响应，受共享环境阻塞，待前端起来后补。静态 + 单测 + 变异已覆盖逻辑分支
