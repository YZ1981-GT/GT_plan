# 平台发布阻断项收口 — 设计

## 1. 基线与原则

候选树基于远端 `a142627c9`，在仓库根锁定的 detached worktree 中实施。主工作区的未提交文件不参与候选。修复采用“一个业务动作一个生产入口、服务只 flush、router 统一 commit、失败不清状态”的原则。

## 2. 前端启动与保存

- `ThreeColumnLayout` 将 `DshPanel` 改为 `defineAsyncComponent`，并仅在 `showDshPanel` 为真时挂载；错误组件局部显示“AI 助手加载失败”。
- `useAiNoteCapture` 恢复对话框所需的常量和 DTO 导出，并保留服务端消息 ID、幂等键与中文错误映射。
- `useWorkpaperAutoSave` 将保存回调改为 `Promise<boolean | void>`：仅 `!== false` 视为成功；每次编辑推进 epoch，回执只清除自己起点代际。
- `useEditorSave` 删除 `status < 600`，冲突取消不再解释为强制覆盖；成功回执校验 `success !== false`。

## 3. 复核编排

新增 `workpaper_review_submission_service`：

1. 按 `(project_id, wp_id)` 锁定底稿；
2. 要求 `edit_complete`；退回重提时将 rejected 状态在同一动作内归一到 `not_submitted`；
3. GateEngine、SoD、QC、批注、AI、复核意见任一检查异常均 fail-closed；
4. 通过后写 `pending_level1/under_review`，并同步程序实例；
5. 服务只 flush，不 commit。

单笔 router 与批量 router共用该服务。批量每稿一个 SAVEPOINT，逐项返回 submitted/skipped；跨项目 ID 统一按不存在处理。旧 `batch-status` 仅保留非提交类合法生命周期动作，`submit_review` 返回 410；旧 `workpapers/batch-submit` 返回 410。

复核状态服务在退回时直接归一为 `not_submitted + revision_required`，保留本次退回事实到专用字段/ReviewRecord；这样编制完成后可直接重提。末级通过后的写保护集中到现有 wp gate 的写动作判据，不依赖前端 readonly。

## 4. 安全边界

- Metabase 所有动态 URL 端点要求登录；项目参数转 UUID 后调用 `assert_project_permission(readonly)`，无项目仅 admin；签名密钥成为正式 Settings 字段，生产禁止默认值。
- 删除 main 中三个临时 debug route。
- ledger SSE generator 接收 project_id，查询 `id + project_id`。
- Review request DTO 不再要求 actor UUID；router 一律传 `current_user.id`，service 查询 `review_id + working_paper_id + !deleted`。
- review-config GET 用 readonly，PUT 用 edit + 全局角色；非法 level role 值拒绝。
- user-formulas/v2 三端点统一 410，直到持久化项目隔离版本另行交付。

## 5. 出具链

- 交付中心复用已有 trio API：readiness 通过后创建 trio job，继续使用 trio detail 轮询，不再调用旧 full endpoint。
- 旧 full endpoint 返回 410 和迁移指引，避免第三条影子入口。
- `ReportEngine.generate_all_reports` 的 TB 重算异常直接传播。
- 新增 `consol_note_export_adapter`：按项目口径解析模板，找到企业树根节点，读取 `(project, year, section, root_node_key)` 的 `ConsolNoteData`，构造导出器需要的章节对象。单体导出路径不变；合并项目若根节点或章节数据缺失则 fail-closed。
- readiness 按项目 scope 分流：单体读 `DisclosureNote/FormulaPushRun`，合并读 `ConsolNoteData/ConsolPushRun`。
- snapshot 对每个源加入稳定内容摘要及最后成功 run/version 标识。

## 6. 迁移与就绪

启动上下文保存迁移执行结果。`migration_mark_complete` 改为异步核对：磁盘版本集合减数据库版本集合必须为空，failure 表必须为空；否则抛出 critical 启动错误。reload worker 也执行这项只读核对。

`readyz` 读取迁移状态详情与 critical drift；存在阻断时返回 503。`health` 增加 `pending_versions`。V229 本身不改号，本批在一次性 PG 验证；共享库只在用户放行后执行。

## 7. 发布门

- CI push 分支增加 `spec/**`。
- package scripts补 `bundle:check`、`build:verify`、`preview:verified`。
- Vite `build.outDir` 消费 `GT_FRONTEND_OUT_DIR`。
- stable launcher 使用 `build:verify` 后再切换，并用 `preview:verified`。
- runtime import smoke、前端 build、迁移完整性均为阻断项；浏览器 smoke 无环境时继续诚实标 skip，但 release checklist 不允许以该 CI skip 代替预发验收。

## 8. 验证

验证分四层：纯函数/服务单测、FastAPI 端点测试、一次性 PG 迁移与状态机、独立端口浏览器 smoke。候选与基线按测试节点比对；已有红项不得归因给本批。所有写真库动作留到单独批准点。