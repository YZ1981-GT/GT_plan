# 设计：程序链加固与 Java 迁移契约

> 需求见 requirements.md。本文只写做法、改动点与取舍；行号会漂，锚点用函数名 / 端点字面量。

## §0 交付顺序与提交纪律

- 批次：批 1（R1~R3）→ 批 2（R4~R10）→ 批 3（R11~R14）→ 批 4（R15~R21）→ 批 5（R22~R24）。每批测试 + 变异 + 浏览器实测后单独提交推送。
- 并发会话 gt_push 正在交付上游 531 项；本 spec 在其推送之后提交，提交走私有索引 / 临时 worktree，只含本 spec 改动的文件（改动块归属逐文件登记在 tasks.md）。
- `WorkpaperEditor.vue` 有行数棘轮（`line-budget.spec.ts`），本 spec 在该文件净增 ≤0：前置环节编码判定移到工具函数抵消新增行。

## §1 R1 底稿详情单一来源

- `services/workpaperApi.ts`：新增 `getWorkpaperSettled(pid, wid)`：经 apiProxy、不带 config（进入 `_inflightGet`，同 URL 并发共享一个 promise），
  被取消（`isRequestCancelled`）时重取一次，其余错误原样抛出；返回值过 `normalizeWorkpaper`。
  `getWorkpaper` 保持每次独立请求（保存后刷新要拿最新版本号：共享会拿到保存前已在途的旧响应）。
- `useEditorMode.fetchComponentType` 改调 `getWorkpaperSettled`；取消重取后仍失败才回退 `'univer'`。
- `useEditorUniver`：`wpDetail` 选项改为只读类型；新增 `onDetailLoaded(detail)` 回调；本地变量承接详情（Shell 已有同 id 详情时直接用），不再写选项；
  `!detail?.id` 才判「数据为空」；catch 先判取消（重取一次），404 走 R10 文案。
- `useEditorSave`：四处写 `wpDetail.value` 改为 `setWpDetail?.(d)` 回调。
- `UniverEditorCore.vue`：去掉两处 `as any`；新增 `emit('update:wpDetail')` 供两个回调；`eventBus.off` 传各自的 handler；
  转发 `workpaper:saved` 加防重入（Shell 的 onChildSaved 收到 saved 会同步再广播一次，mitt 同步派发 ⇒ 原先无限递归直到栈溢出）。
- Shell：`<UniverEditorCore v-if="modeResolved" @update:wp-detail="...">`；`modeResolved` 在挂载流程的归类加载之后置真（成功失败都置），HTML 册不再先挂 Univer 再卸载。
- 测试：`WorkpaperEditor.detailRace.spec.ts` 用真实 `utils/http` + 假 adapter（详情 URL 由闸门放行、监听 abort 抛 CanceledError），不 mock useEditorMode / UniverEditorCore；
  断言详情 URL 只发 1 次、无 canceled、无错误页、Shell 拿到 wp_code。单元层补只读 computed 形态与取消用例。

## §2 R2 编辑锁鉴权

- `routers/editing_locks.py` 新增 `_authorize_lock(db, user, resource_type, resource_id, *, mode)`（mode = acquire / renew / force）：
  - `workpaper`：resource_id 转 UUID（失败 404）→ `enforce_wp_gate(entrypoint="workpaper.editing_lock", method=POST|PATCH, action=acquire_edit_lock|renew_edit_lock)` →
    `assert_project_permission(ctx.project_id, "edit")`（归档 423）。force 另过 `workpaper.editing_lock_force`（只登记给全权身份），被拒 ⇒ 403。
  - `disclosure_note` / `audit_report`：resource_id 形如 `{项目 uuid}_note|_report`，按该项目成员判（附注沿用附注编辑门禁的同一判定函数，报告与报告保存同级）。
  - 其他类型 404。
- `action_matrix.py`：`_CONTENT_MUTATION_FAMILIES` 加 `("workpaper.editing_lock","POST","acquire_edit_lock")`、`("workpaper.editing_lock","PATCH","renew_edit_lock")`；
  全权族加 `("workpaper.editing_lock_force","POST","force_edit_lock")`（assignee / reviewer 不登记）。
- 续期被拒：先 `release_lock(本人)` 再 404。强制接管收 `X-Client-Instance` 并写入新锁。`GET /active` 非 admin 403（前端无调用方）。
- 前端 `useEditingLock`：新增 `enabled` 选项（可编辑时才取锁，变为 false 时释放）；请求带 `_silent`；取锁 404/403 置 `denied`（不显示他人正在编辑）；
  续期失败停心跳、`isMine=false`；`forceAcquire` 失败中文提示。`WorkpaperEditor` 传 `enabled: canEdit`。
- 测试：表驱动（未委派审计员 / 被委派审计员 / 质控 / 经理 / admin）× 四动作，断言状态码与锁行；逐处摘判定做变异。既有锁测试用假资源 id 的改真底稿夹具。

## §3 R3 模板复制

- `_persist_copy_result`：`db.add(wp_index)` 后先 `flush` 再建 working_paper；返回 `WorkpaperFileJob`。全部落库后 `asyncio.to_thread(materialize_workpaper_files, ...)` 回写 `file_path`，
  提交失败对已落文件 `discard_generated_file`。
- 来源鉴权：单份先过底稿门（`workpaper.detail` / `read_detail`），被拒与不存在都 404「源底稿不存在」；整循环先 `assert_project_permission(来源, "readonly")`（403 转 404），
  再逐份按可见性过滤（不可见的标 skipped「无权查看该底稿，未复制」）。来源校验后对目标项目重设 RLS 上下文。
- `WpTemplateCopyDialog.vue`：去掉「覆盖」勾选；提示按 copied / skipped / failed 计数。
- 测试：`tests/services/test_template_copy_pg.py`（`pg_session` 回滚、两个【测试】项目）：单份 / 整循环成功且能 JOIN 查到、文件存在；非来源成员 404；
  SQLite 用例开外键检查（删中间 flush 即红）。

## §4 R4~R10 程序表链路

- R4 后端：`procedure_row_trim_service.trim_row / restore_row` 末尾同事务调 `_align_status_override`：按渲染同一口径（年度、`program_override_scope`、item_key=程序号）
  写 `status`（裁剪 not_applicable、恢复 pending）。`restore_row` 恢复前记下各任务执行人，回执加 `previous_assignees`（姓名）。
  前端：`applyRows` 返回 `{done, receipts}`；成功后 `loadRowAccess()`，有任务视图时 `refreshOverlayFromServer()`；恢复后页面状态置 pending 并提示重新委派；
  状态下拉改为待执行 / 执行中 / 已完成（+ 委派人可裁剪），不适用行显示「恢复执行」按钮。
- R5：`ProcedureTrimming.enterProgramConsole` 带 `?sheet=@program`；`resolveRenderSheet` 识别 `@program` ⇒ 第一张 a-program-console 页。
- R6：`ProgramRowTrimRequest / ProgramRowRestoreRequest.sheet_name` 与 `program-row-access` 的 `sheet_name` 放宽为可空（service 已按底稿编码定位）；
  前端 `applyRows / loadAccess` 只要求 wpId；控制台传 `sheetName || sheetCode || ''`；后端 422 `row_trim_unsupported` 时页面标记并提示「仅页面标记，未写入任务」。
- R7：`useProgramRowControl` 加 `accessState`（loading / ready / error）；非 ready 时 `fullPower=false`、`canTrim=false`、`canEditRow=false`；控制台 error 时显示原因与「重试」。
- R8：`POST /api/workpapers/field-overrides/batch`（≤200 项，一次 edit 鉴权，每项保存点内 `assert_program_override_allowed` + set，一次提交，回 `{saved, failed[]}`）；
  `writeProgramStepOverrides` 改走批量，失败逐条 `ElMessage.warning`。
- R9：`usePrerequisiteStatus(projectId, wpCode)` 接受 getter，`watch` 立即执行，编码为空不请求，旧回执按序号丢弃；工具函数 `prerequisiteWpCode(wpCode)`（D/E/F/G/H/I/L/M/N 循环返回编码，否则空）。
- R10：详情 404 文案统一为「无法打开这张底稿：它可能不存在、已删除或移入回收站，或没有委派给你。请回到底稿列表，或联系项目经理确认委派。」；
  能力快照 404 不再设「稍后重试」错误；结构化错误的 reasonCode 不在界面正文显示。

## §5 R11~R14 生成与人员

- `services/wp_generation_receipt.py`：`GenerationReceipt`（created_codes / existing_codes / skipped_trimmed_codes / in_recycle_codes / blank_codes / failures / header_failures / header_unfilled）
  + `to_payload()` + `describe()`（中文提示）。各入口改用它拼回执（已有字段名保持不变，只补缺项）。
- 链路编排 `_step_generate_workpapers`：编码集（科目匹配 ∪ 自定义程序）经 `plan_generation`；逐码保存点；落文件走 `materialize_workpaper_file`（找不到模板建空白册计入 blank）；
  落文件 / 建行失败进 failures 且不计 created；表头结果进 header_failures。子底稿段同样逐码保存点。
- IPO / B60：模板复制改走 `materialize_workpaper_file`（场景按原值），在保存点内；失败回滚该码并进 failures / errors；D4 包装透传 `skipped_trimmed_codes / in_recycle_codes`。
- 自定义单张：读取 `fill_workpaper_header` 的 status，非 ok 进 header_failures 与提示。模板集：回执 `header_unfilled = 新建数`，提示写明。
- R12：`DELETE /api/staff/{id}` 改 admin；有效项目分配存在且未带 `revoke_assignments=true` ⇒ 409（列项目名）；带参数时同事务软删分配与对应项目成员行，并对这些项目 `bump_policy_epoch`。
  前端人员管理页收到 409 弹二次确认后带参数重试。`require_staff_active_user` 的 422 文案写明原因与处理办法。
- R13：`prepare_row_tasks` 只捕获 `SQLAlchemyError / HTTPException / ValueError / LookupError`，失败时计数清零、`ready=False`；预览回执加 `preparation_ready`，前端据此提示；
  物化服务 `_load_wp_indexes` 公开为 `load_wp_indexes`（保留私有别名）。
- R14：`backend/scripts/fix/report_workpaper_file_backlog.py`：默认 dry-run 分类计数并输出 JSON；`--apply --confirm` 才写（落文件 + 条件更新 file_path），本 spec 只跑 dry-run。

## §6 R15~R21 请求收敛与工程化

- R15：`useAcnr.resolveIndexBatched`：模块级按项目排队，微任务末尾合并、去重、每批 ≤50 调 `/resolve-batch`；同键在途共享；命中进现有 LRU。`GtIndexChip` 改用它，`disabled` 时不解析。
- R16：`auditPlatformApi.getProject` 与 Shell `loadProjectMeta` 改为经 apiProxy、不带 config（共享在途）；错误分支保持原兜底。
- R17：`ThreeColumnLayout.pollImportQueue` 与 `DetailProjectPanel.pollImportStatus` 改 setTimeout 链：处理中 5 秒，否则 30 秒；隐藏暂停保持。
- R18：迁移 `V{实施时取号}`：`workpaper_lifecycle_events`（id、project_id、wp_index_id、wp_code、event_type recycled|restored、kind、reason、actor_user_id、request_id、working_paper_ids jsonb、created_at），
  只追加；`move_to_recycle_bin / restore_from_recycle_bin` 同事务写；回收站「删除人」读最近一条 recycled 事件，旧数据回退去向 JSON。
- R19：`wp_program_row_access` 路由级 `dependencies=[Depends(dedicated_wp_gate)]`；注册表注入前判断路由已带该依赖则跳过（避免两次判定、两条拒绝记录）。
- R20：`tests/conftest.py`：`GT_REQUIRE_PG=1` 且收集到 pg_only 用例而地址不是 PG ⇒ `pytest.UsageError`；识别 `postgresql` 与 `postgres://`。
- R21：`tests/procedure_chain_e2e/test_cross_role_chain_pg.py`（PG 回滚事务、真实路由、三种角色）；`e2e/procedure-chain-cross-role.spec.ts`（`GT_E2E_*` 环境变量，未配置跳过）。

## §7 R22~R24 Java 契约

- `docs/contracts/procedure-chain/`：每个契约一个 `*.schema.json`（2020-12，`$id` 带版本号 `v1`），`README.md` 写状态机、错误码、事务边界、鉴权口径。
- `backend/tests/contracts/test_procedure_chain_contracts.py`：从真实接口（TestClient + 夹具）取响应按 schema 校验；schema 自身用 `Draft202012Validator.check_schema`；变异：删响应字段即红。
- `backend/scripts/gen/export_procedure_chain_openapi.py`：从 `app.openapi()` 取本链路径子集写 `openapi.procedure-chain.json`，`--check` 只比对（内容不变不改文件）。

## §8 取舍

- 不给 `WorkingPaper` 加 relationship 解决插入顺序（核心模型影响面大），用显式 flush。
- 模板集生成不在请求内填表头（737 码约多 4 分钟，超前端超时）；只如实回报，异步补填另议。
- 删除人员默认拒绝而非静默级联：撤权是不可逆的业务动作，须二次确认。
- 存量 file_path 回填属真库写入，需用户放行。

## §9 实施记录（批 1 + 批 2，2026-10-26）

### 9.1 与设计的偏差

- R2 测试：SQLite 锁语义用例（409 / 续期 / 释放 / 强抢，合成资源 id）经 `tests/_editing_lock_helpers.py` 的 autouse 夹具放行 `_authorize_lock`（仍按 `_resolve_project_id` 给 SSE 的 project_id），没有改成真底稿夹具；资源鉴权全部由 `test_editing_lock_authz_pg.py` 在真库回滚事务里覆盖。顺带修 4 例在 d0de87a6c 上就红的过期用例：错误信封是 `{code, message}`（不是 `detail`），以及路由里是懒导入 `event_bus`（只能 patch 单例的方法）。
- R4：对齐逻辑放在 `services/program_row_status_sync.py`，由 `ProcedureTrimService` 的三条行级路径调用（控制台按行 → `trim_row / restore_row` → 任务级；任务级端点；裁剪方案的行条目），而不只是 `trim_row / restore_row`。只改已有的状态覆盖值、不新建（页面状态由任务投影给出，进度统计分母不变）；取不到审计年度就跳过（前端也写不了覆盖值）；程序号按 `normalize_program_no` 比。
- R9：设计只写了前端 getter。实施时发现后端 `prerequisites_for` 只认 E1 / D / F / M，前端修好后 G / H / I / J / K / L / N 会显示「所有前置底稿已完成」（比原先恒按 E1 更糟：给出错误的放行信号），于是一并补齐全部循环（与前端回退清单逐项对拍）、按 `WpFileStatus` 逐值映射（复核通过原先算「进行中」）、粗裁为不适用 / 跳过的前置记 `not_applicable` 不阻断；横幅显示与请求同一判定（`prerequisiteWpCode`，原先漏了 J 循环）。
- R10：`getWorkpaperSettled` 用本模块自己的在途表（apiProxy 只给不带 config 的 GET 共享，这里要带 `_silent`）；403 与 404 同一句；其余错误不再显示 axios 英文；能力快照逻辑抽到 `views/workpaper-editor/useShellCapability.ts`（403 / 404 只给拒绝快照、不叠加错误条），`fetchWorkpaperCapabilitySnapshot` 静默；`WorkpaperCapabilityShell` 的原因码移到 `data-reason-code`。抽出后壳 1456 → 1362 行，`line-budget.spec.ts` 的棘轮同步下调。
- R19 随批 2 完成（路由自带 `dedicated_wp_gate`，注册表见到就不重复挂）。

### 9.2 预存失败（d0de87a6c 干净检出逐条复现，非本 spec）

`test_template_engine` 3 例；`test_wp_onlyoffice_router::TestOnlyOfficeConfigEndpoint` 4 例（404）；`procedure_trim/test_report_line_index::test_live_report_config_standard_variants_are_four`（读真库 report_config，多出一个 `project:` 变体）；`test_task9_core_route_gate::test_checklist_put_allow_admin`（MissingGreenlet）；`test_lazy_import_resolvability` 2 例（consol_lock_service / disclosure_note_models / resolve_alias_counterparts）；`test_authz_inventories_check_mode` 4 例（见 9.3）。

推送前在 13120d6d6（远端前移后的父提交）上补跑守卫与前端，新增的预存红同样逐条在父提交复现：`test_raw_sql_schema_contract::test_raw_sql_tables_are_known`（`note_project_realign_apply.py` 的 `json_populate_recordset`）；`test_raw_sql_bind_cast_contract`（`consol_note_template_push_service.py` 的 `:f::jsonb`）；`test_wp_large_file_size_guard::test_pass2_files_not_regressed`（`wp_render_config.py` 1183 行）；`test_raw_sql_unqualified_column_contract::test_no_new_unqualified_column_violations`（`ai_content.py` 读 `working_paper.wp_name`；与其他 PG 文件同跑时另有 3 例 setup「Event loop is closed」，单独跑只剩这 1 例）；前端 `d4OtherGroupWriteback` 2 例、`views/workpaper-list/__tests__/line-budget` 的 Workbench ≤1210（`WorkpaperWorkbenchView.vue` 1765 行）。

### 9.3 范围外发现（未改，汇报用户）

- edit 级影响清单：已提交产物比 d0de87a6c 的代码落后 35 处门禁调用点；生成器按（文件, 函数, 形态）做条目键，同一函数两次同形门禁会撞键 ⇒ `--check` 恒红。本 spec 新增 5 处调用点（覆盖值批量 1、取锁 2、模板复制 2），取锁与模板复制各撞一次键（撞键 4 处 → 6 处）。需在生成器键里加序号 / 级别后整体重生成，属 partner-manager-edit-permission 的工具，本 spec 不重生成（重生成也绿不了）。
- 模板复制弹窗要用户手输源底稿 / 源项目的 UUID，没有选择器。
- 委派对话框：项目没有团队成员时执行人下拉只显示「无数据」，没有「先在项目团队里添加成员」之类的提示。
- 打不开底稿时编辑器顶部工具栏（保存 / 一键填充 / 刷新取数…）仍显示；工具栏在壳里，壳卡在行数棘轮上，本 spec 未改。
- 附注写端点清册：已提交产物落后 3 处（非本 spec）；双次生成比对在 autocrlf=true 的检出上因行尾必红。
- `PUT /api/audit-report/{id}/paragraphs/{section}` 只要求登录（跨项目可写）；`DELETE /api/staff/{id}` 只要求登录（R12 处理）。
- 前置横幅后端仍是「没有底稿 = 未开始」：未生成也未裁剪的前置会一直显示未完成（与原 D / F 口径一致）。

### 9.4 浏览器实测补修（批 1 + 批 2）

- R10：不存在 / 无权的底稿除详情外，壳还会取步骤映射、侧栏渲染配置（decision_trace）和 Univer 页签目录，三处都没带 `_silent`，404 时各弹一次「资源不存在或不可访问」，页面左侧还显示「Sheet 0 / 无匹配的 sheet」。改：`useStepMapping` 静默；`useWpRenderer` 加 `silent` 选项（壳的侧栏用），silent 那一发同时 `_dedupe: false` —— 带配置的 GET 不走 apiProxy 在途共享，会和 GtWpRenderer 同 URL 那一发互相取消（用例里用真实 http 复现过）；Univer 目录请求同样 `_silent, _dedupe: false`；`UniverEditorCore` 打不开时不显示左侧页签导航。变异 FA1~FA6 全红。
- R5：循环册（E1 / H1 / D2-1 …）的程序表页 componentType 是循环组件（`e1-monetary-fund` / `h1-fixed-assets` …），只有独立程序表册才是 `a-program-console`；`@program` 原先只认后者 ⇒ 程序裁剪页「程序裁剪 ›」进 E1 落到「底稿目录」。改为同时认 `sheet_type = procedure`（后端下发，缺省按表名启发式，与 `resolveSheetType` 同口径）。变异 FR5d（只认 a-program-console）/ FR5e（只认下发的 sheet_type、不走启发式）全红。
- R3：目标已有同编码时，复制器的跳过说明「目标项目已存在 wp_code=E1，overwrite=False 跳过」先于路由的中文说明返回，界面上漏出参数名。改为复制器与路由共用一句中文常量 `EXISTING_CODE_SKIP_MESSAGE`。变异 C7 红。
- 测试数据：【测试】公式同步甲 E1 第 23 行裁剪 / 恢复留下 1 条程序行任务（现为 execute / unassigned）、2 条任务历史、1 条程序行定义（E1A 第 23 行，其他项目委派预览也会建同一条），收尾时备份后清理（tasks 6.1）。
