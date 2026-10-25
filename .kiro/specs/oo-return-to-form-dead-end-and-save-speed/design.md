# 在线编辑回表单死路与回写提速 — Design

## §1 现状 grep 确认（动手前逐项核对，2026-10-24）

| 事实 | 位置 | 对设计的影响 |
|---|---|---|
| 「保存并回到表单模式」一律 `forceSave()`，不看 `dirty` | `WorkpaperSyncEditorHost.vue` `onForceSaveClick` | R1.1 在按钮上分流；`forceSave()` 返回类型不变（各宿主 ref 类型声明 `{ operationId }`） |
| 未改动直接离开只在各宿主的「结构化视图」开关里有（D2 实测 0.22 s、恰一次 leave） | 各宿主 `switchRenderMode` / `useGRenderModeSwitch` / `useARenderModeSwitch` / `useHSyncMode` 等 | 宿主不用改；共享层修 |
| 返回码 4 落 `forcesave_frozen` 并把 `dirty` 清零 | 桥 `switchToHtml()` `callbackExpected === false` 分支 | 与后端契约相反（见下一行） |
| 契约 error 4：「request 落 `no_changes` 终态并直接放行离开」；`classify_editor_destroy` 判 `allowed_no_changes`（可回表单）但运行时零调用 | `onlyoffice_callback_state_contract.json` / `command_service.py` | R1.3 前端按契约放行，不改后端 |
| `forcesave_frozen` 出边只有 `forcesave_started` / 失权 / `sync_failed`；又在 `WP_BRIDGE_IN_FLIGHT_STATES` 里 ⇒ clean close 被拒、「同步中…」常亮、关页弹确认 | `workpaperSyncBridgeMachine.ts` / 桥 | R1.4 |
| 遮罩条件 `!editing`（≠ `oo_editing` 即整块拦截，冻结态也拦） | 宿主模板 | R1.4：冻结态不遮 |
| `error` 与三个终态唯一出边 `reset`，`reset()` 生产零调用；`error` 态 `leaveWithoutSaving()` 先发 leave 再因非法转换抛错（人留在 OO、lease 已释放） | 桥 / 状态机 | R1.5：出口 + 「先判边再发请求」 |
| 冲突裁决面板、恢复认领面板生产零挂载 | `WorkpaperSyncConflictDialog.vue` / `WorkpaperSyncRecoveryPanel.vue` | 范围外；R1.5 只给退出 |
| `onDocumentStateChange` 的 `false` = 改动已送达文档服务；桥只认 `true` | OnlyOffice 事件文档 / 桥 `notifyDirty` | R1.2 另记最近一次原始值 |
| 桥 1632 行，白名单 1559 × 1.05 ⇒ 只剩 4 行 | `backend/scripts/file_size_whitelist.txt` | 新逻辑进伴生模块，常量与 202 分支一并迁出，桥净增 ≤ 0 |
| `GtWpRenderer.vue` 1485 行（上限 1500） | 同上 | R4 只加挂点，横幅与注册表进新文件 |
| 回调 apply 先 `_attach_pilot_adapters`（冷建持全局锁 36~42 s）再 `bind_registration_to_target`（已只建本 entry、按键加锁） | `wp_sync_router._apply_durable_incoming` / `target_bound_registration.py` | R2：冷缓存时跳过全局锁，直接按 entry 绑；AST 判据只认被 await 的名字，加关键字参数即可 |
| `warm_source_fact_caches` 无单飞（`lru_cache` 不去重并发首算，首算约 7 s） | `entry_source_facts.py` | R2 加线程锁，预热与回调共用一次计算 |
| incoming 在三方提取里读一遍、物化计划 `_plan_materialize_step` 每个 binding 又读一遍（D2 4 个 binding）；baseline 只影响 `protected_findings`，`ExcelSyncAdapter.extract` 丢弃它、计划从不读它 | `oo_to_html.extract_three_way` / `excel_materialize.py` / `excel_extract._classify_protected_tamper` | R3.1 P8 的等价前提成立 |
| 已发布形态提取只有 store-projection 的 `BASELINE_EXTRACT_CACHE`（键 `contract_id:sha`，不含 binding / definitions）；OO→HTML 的 base 读每次重算（D2 约 1 s） | `store_projection_response.py` / `parse_cache.py` | R3.2 P9 键要更严，并放在 adapter 内让两条路径共用 |
| 宿主的 operation 追踪器随宿主卸载停掉；D2 等宿主在 HTML 模式卸载编辑器宿主 | 宿主 `startOperationTracking` / 各宿主 `v-if="renderMode === 'onlyoffice'"` | R4 后台阶段的追踪归桥（桥活在页面级宿主里），只在后台阶段起 |
| 页面级渲染器把 `readonly` 传给全部底稿宿主 | `GtWpRenderer.vue` `<component :readonly>` | R4 单点只读 |
| 表单写入经 `useChecklistPersistence.persist`（PUT `checklist-responses`） | `composables/workpaper/useChecklistPersistence.ts` | R4 持久化层拒写 |

## §2 R1 前端：死路与出口

### 状态机（`workpaperSyncBridgeMachine.ts`）

- 新事件 `forcesave_no_changes`：`forcesave_requesting → html_idle`（契约放行离开）。
- `forcesave_frozen` 加 `clean_close_completed → html_idle`（未改动静默离开）与 `reset → html_idle`（用户确认的退出）。
- `conflict` / `refresh_required` / `close_authorization_stale` / `recovery_pending` 加 `reset → html_idle`（`error` 与三个终态原本就有）。
- clean close 仍只在 `oo_editing` / `forcesave_frozen` 合法：其余状态离开都可能丢掉服务端未落地的改动，必须走带确认的退出。

### 状态集合（迁到伴生 `bridgeStateSets.ts`，桥原样 re-export）

- `WP_BRIDGE_IN_FLIGHT_STATES` 去掉 `forcesave_frozen`（冻结态 request 已终结或从未出站，没有任何东西在飞）。
- 新 `WP_BRIDGE_EXIT_STATES` = 冻结、出错、冲突、需重载、失权、恢复待认领、三个终态；宿主据它显示「退出在线编辑」。
- 新 `WP_BRIDGE_UNMASKED_STATES` = `oo_editing`、`forcesave_frozen`。

### 强制保存流程（伴生 `bridgeForcesaveFlow.ts`；`forcesaveTerminalMessage` 与 202 分支的错误构造一并迁入）

- `createDeliveryTracker()`：`note(raw)` 记每次原始事件；`waitDelivered(ms)` 最近一次为 `true` 时等下一次 `false`，超时返回 `false`；最近一次为 `false` 或从未收到事件立即返回 `true`。
- `switchToHtml()`：`apply('forcesave_started')` 之后先 `waitDelivered(deliveryWaitMs ?? 3000)`，再出站。202 分流：

| 回执 | 处置 |
|---|---|
| `dispatch_error` | 冻结（不变） |
| `no_changes` + 已送达 | 尽力 leave（`dirty=false`）→ `forcesave_no_changes` → 清 descriptor / confirmation / dirty → `lastForcesaveOutcome = 'no_changes_left'` |
| `no_changes` + 未送达 | 冻结；`dirty` 保留；提示「改动还在发送，请稍候再保存」 |
| 其它无回调终态 | 冻结（不变），`dirty` 保留 |
| 受理 | 不变 |

- `leaveWithoutSaving()`：先判 `clean_close_completed` 在当前状态是否合法（新纯函数 `canTransition`），不合法即 refuse，**不发** leave（修 `error` 态先 leave 后抛的半态）。
- `exitOnlineEdit()`：仅 `mode=oo` 且状态在 `WP_BRIDGE_EXIT_STATES`；尽力 leave（送真实 `dirty`，服务端拒绝即按 lease 过期）→ 尽力 `reloadHtml(0)`（服务端可能已合并过）→ `reset()`。

### 宿主（`WorkpaperSyncEditorHost.vue`）

- 按钮：`!dirty && canLeave` ⇒ `leaveWithoutSaving()`；否则 `forceSave()`。
- `forceSave()`：桥回到 `html` 模式（无改动放行）⇒ `ElMessage.info('在线编辑里没有需要保存的改动，已回到表单')`，返回本次 operation id。
- 遮罩：`WP_BRIDGE_UNMASKED_STATES` 之外才拦截（`descriptor_mounted` 的穿透条不变）。
- 「退出在线编辑」按钮在状态条一行（遮罩之外）：`mode=oo` 且状态在退出集合时显示；`dirty` 为真或状态为冲突时先 `ElMessageBox.confirm`，文案按状态说明后果。

### 正在输入的单元格（R1.6）

实测 OnlyOffice 9.4 `requestClose()`：①无未保存内容时 `onRequestClose` 是否立即触发 ②单元格编辑中是否弹编辑器自己的提示。两条都成立才接：宿主向桥登记一个离开前钩子，`leaveWithoutSaving()` 发 leave 前等它；用户选继续编辑则 refuse。否则在 §9 记录实测结论、不接。

## §3 R2 后端：按 entry 准备注册

- `_attach_pilot_adapters(svc, *, entry_scope=None)`：命中缓存照旧重放；未命中且给了 `entry_scope` ⇒ `_prepare_entry_only(svc, entry_id, wp_id)`：目标底稿没有 current representation ⇒ 返回 False 走原锁内冷建；否则工作线程里 `warm_source_fact_caches()`（加线程锁单飞）与 `warm_template_structure_hashes((本 entry provider 模块,))`，返回 `()`；**不写** `_REGISTRATION_CACHE`。
- 调用方随后照旧 `bind_registration_to_target`：它在零注册的 fork 上只跑本 entry 的 provider（per-key 锁），绑定后 `rebind_entry` 进本请求 registry。
- `_apply_durable_incoming` 传 `entry_scope=(entry_id, wp_id)`；`_registration` 各调用端点逐个核对只用返回的注册（不按 wp_code `resolve`、不 `build_report`）后同样传入，否则保持原样并在 §9 列明。
- 取舍：冷缓存路径上本 entry 不与其它 entry 做 RG-3 matcher 重叠校验（apply 按 entry_id 解析，不按 matcher）；全量注册（预热 / 下一次缓存命中）照旧全校验。

## §4 R3 后端：去掉重复提取

### P8（新模块 `incoming_view_reuse.py`）

- `ExcelSyncAdapter.extract` 读 incoming 形态（且无退役身份）时，把逐 binding 的 `(binding, outcome 去掉 protected_findings)` 连同文件身份 `_file_cache_key(artifact)` 与形态存进实例 `_baseline["incoming_views"]`。
- `_materialize_within_scope` 取出（pop）：`substrate_for_write is substrate`（没有重注 / G7 中性化副本）、文件身份与形态一致才用；按 `table_key` 传给 `materialize_projection_single_pass` / `materialize_projection`；`_plan_materialize_step(..., substrate_view=None)` 只在 `view_binding == binding` 时采用，否则照常提取。链式回落的后续趟读临时文件，自然不命中。

### P9（新模块 `published_extract_cache.py`）

- 只在 `ExcelSyncAdapter.extract` 内：读的是已发布形态（`published_representation`）或物化反读（`staged_result`）、且无退役身份时查 / 填；incoming 形态永不经它。
- 键 = sha256(规范 JSON{文件字节 sha、`contract.canonical_sha256`、`definitions.as_dict()` 摘要、`_all_bindings()` 逐字段（含 tombstone / 动态列）、`limits` 指纹、转置 spec 由契约决定已含})。门判据（`assert_engine_entry_definitions` / 保留门 / 预算）只依赖键内输入 ⇒ 命中即判据结果相同。
- 值 = 合并后的 Projection + 主 binding 的 `(projection, formula_inventory)`；命中时若本次是 base 读则种 `_baseline["pair"]`。`BoundedLruCache(maxsize=16)`，并入 `clear_all_parse_caches()`。
- store-projection 首读 base 时经 adapter 填入 ⇒ 打开在线编辑后第一次保存的 base 读命中；第二次保存的 base = 上次物化产物，由反读填入。

## §5 R4 前端：先回表单、后台合并

- 状态机：新状态 `merging_in_background`（mode `html`）与 `background_merge_failed`（mode `html`）；事件 `background_merge_started`（`incoming_durable` / `application_bound` / `merging` / `rematerializing` / `background_merge_failed` → `merging_in_background`）、`background_merge_failed`（→ `background_merge_failed`）；`merging_in_background` 收 `reload_completed → html_idle`；`background_merge_failed` 收 `reset → html_idle`。两者都不收 `flush_started` ⇒ 合并期间切不进在线编辑。
- 伴生 `bridgeBackgroundMerge.ts`：`continueInBackground()` 转状态、登记注册表、起桥持有的 `WorkpaperSyncOperationTracker`（同 180 s 窗口、同 api 通道）；终态 applied / refresh_required / duplicate ⇒ `reloadHtml(revision)` → 尽力 leave → `reload_completed`；conflict / error / authorization_stale ⇒ `background_merge_failed` + 中文原因；重试走 `retryOperation`；桥卸载停追踪、清登记（服务端照常完成）。
- 宿主：`returnToFormPending` 且未再编辑、状态进入上述四态之一 ⇒ 停宿主追踪、调 `continueInBackground()`。落地太快直接 applied 的照旧走原路径。
- 单点：新 `backgroundMergeRegistry.ts`（按 wpId 的响应式登记）；`GtWpRenderer.vue` 有效只读 = `readonly || 合并中` 并挂 `WorkpaperBackgroundMergeBanner.vue`；`useChecklistPersistence.persist` 合并中拒写（错误文案中文）。两新状态不在 in-flight 集合 ⇒ 关页不阻断。

## §6 R5 开发环境

`start-dev.bat`：`GT_BACKEND_NO_RELOAD=1` 时去掉 `--reload*` 参数，默认不变。

## §7 守卫

- 前端：状态机新边（含「其余状态仍拒 clean close」）、`canTransition`；桥行为（未改动按钮恰一次 leave 零 forcesave、送达等待、no_changes 已送达放行 / 未送达冻结、冻结不 in-flight、各退出状态 `exitOnlineEdit` 请求次数、error 态 clean close 零请求）；宿主（按钮分流、冻结不遮罩、退出按钮显隐与确认、无改动提示）；后台合并（转状态、追踪归桥、只读与横幅、拒写、终态分流、卸载停止）。把旧死路钉成预期的用例（`forcesaveFrozenRetryable` / `sessionEditsStickyDirty` / 宿主 no_changes 用例）按新语义改写并在注释写明改判据的理由。
- 后端：冷缓存 + `entry_scope` 不进全局锁（锁被占时不阻塞）、不写全局缓存、无 representation 回落；源码事实单飞；P8 复用结果与重新提取逐字段相同、提取次数 8 → 4、换文件 / 换形态 / 换 binding 不复用；P9 命中与重算逐字段相同、键缺任一输入即打红、incoming 不进缓存、合并 / 叠加不改写缓存值。
- 磁盘变异逐条：删按钮分流、删送达等待、no_changes 退回冻结、frozen 放回 in-flight、删 `canTransition` 门、删 `entry_scope` 早返回、写部分快照、P8 不比文件身份 / 不比 binding / 不去 findings、P9 键漏 binding / 漏 definitions、后台合并不设只读。

## §8 拒绝方案

- 保留冻结态并让用户「点一下空白处再保存」：与契约相反，且遮罩下根本点不到。
- 按钮在未改动时禁用：把最显眼的回表单入口变成灰的。
- 返回码 4 自动重试 N 次：有送达等待后多余，且未改动时每次都白等。
- 后端改判返回码 4 为可重试：契约明文不可重试、直接放行。
- 去掉 `_baseline_pair()`（受保护格发现无人消费）：属 Property 24 可见性的行为变更，另议。
- 让桥在所有阶段自己轮询：会打红「桥只在被调用时发请求」那批判据；只在后台阶段由桥持有。
- 进程池 / 多 worker 提速：序列化 2 万键投影，单用户延迟不降。

## §9 实施记录

### 9.1 T1 R1 前端死路与出口（2026-10-25）

- 伴生模块：`bridgeStateSets.ts`（四个状态集合）、`bridgeForcesaveFlow.ts`（送达跟踪、202 分流、终态文案）、`bridgeLeave.ts`（退出在线编辑、离开前确认登记位，T2 加）；桥 re-export，既有 import 路径不变。桥 1632 → 1593 行（上限 1636）。
- 回表单四条路（clean close / 返回码 4 放行 / applied 后重载 / 退出）共用 `bestEffortLeave()`：送真实 dirty、失败不阻断。
- 送达等待之后再判一次状态：等待期间编辑器出错 / 失权 ⇒ 不再出站（`bridge_forcesave_superseded`），否则出站后撞非法转换。
- 判据改写（理由写在各用例注释里）：`WorkpaperSyncEditorHost.spec` 按钮用例拆成「没编辑 ⇒ clean close」「编辑过 ⇒ 强制保存」、no_changes 用例改为「已送达 ⇒ 放行回表单并提示」并补 doc_not_online；`forcesaveFrozenRetryable` 的 mode 判据改查 `WP_BRIDGE_STATE_MODE`；`sessionEditsStickyDirty` 的 no_changes 拆三种（已送达放行 / 未送达冻结 / 不在线冻结）；`useWorkpaperSyncBridge.spec` in-flight 集合；`cleanCloseWithoutSaving` 标题注明冻结态也接受 clean close。
- 新判据 `ooReturnToFormDeadEnd.spec.ts` 26 例。sync 目录 vitest：改前 17 例失败、改后同一组 17 例（逐条比对，无新增）。
- 磁盘变异（隔离副本 `C:\Users\Administrator\oofix_verify`，避开共享开发服务器的热更新）20 条全部打红：按钮不分流、去送达等待、返回码 4 已送达仍冻结、冻结态放回 in-flight、clean close 不判边、删冻结态 reset / clean close 边、删 `forcesave_no_changes` 边、遮罩回到 `!editing`、退出按钮不显示、退出不重载、`notifyDirty` 不记送达、放行不提示、`canExit` 不看 mode、退出写死 dirty=false、有改动退出不确认、放行不发 leave、宿主不认放行结局、退出集合 / 不遮罩集合去掉冻结态、送达事件不结算、reset 不结算。
- 单区域 vue-tsc：改动文件 0 新错误（`workpaperSyncBridgeMachine.ts(895)` 与 D2 组合式函数、测试夹具 storage 类型等为 HEAD 既有）；注入 `number = string` 报 TS2322。
- 浏览器（【测试】在线编辑回表单验收 D2-2，平台接口新建项目并生成 D2）：没改动点「保存并回到表单模式」101 ms 回表单、网络恰一次 leave（54 ms）；单元格改动经编辑器「确定」撤销后保存 ⇒ 返回码 4 已送达 ⇒ 0.43 s 回表单并提示「在线编辑里没有需要保存的改动，已回到表单」。

### 9.2 T2 R1.6 `requestClose()` 实测与接入（2026-10-25）

实测（OnlyOffice 9.4.0，上述【测试】项目）：

| 情形 | 现象 |
|---|---|
| 单元格输入中（未按回车） | `onDocumentStateChange` 一次都不触发 ⇒ 桥 dirty=false（就是要补的静默丢失） |
| 没有未保存内容时 `requestClose()` | 约 1 ms 回 `onRequestClose`（三次观测） |
| 有输入中的单元格时 `requestClose()` | 编辑器弹「警告：此电子表格中所有未保存的更改都将丢失」（确定 / 取消），弹窗期间无事件 |
| 选「取消」 | 无事件，单元格仍在输入 |
| 选「确定」 | 先撤销全部改动（`onDocumentStateChange` true → false），再 `onRequestClose` |
| 声明 `onRequestClose` | 编辑器顶栏没有多出关闭按钮 |

两条前提都成立 ⇒ 接入（`editorLeaveConfirm.ts` + 桥登记位 `setLeaveConfirmer`）：

- clean close 发 leave 前问确认器。没登记 / 编辑器不支持 ⇒ 同步放行（原路径不多一跳异步）；800 ms 内有答复 ⇒ 放行；无答复 ⇒ 本次留下（KEPT 码，各宿主与 A / H 视图开关不当失败显示）+ 一句指引，记「提示中」。
- 提示中用户选「确定」（晚到答复）⇒ 宿主重走「保存并回到表单模式」：撤销让 dirty 置真 ⇒ 强制保存 ⇒ 返回码 4 放行。
- 提示中又点离开 ⇒ 再探测；仍无答复 ⇒ 平台自己的确认「放弃输入并回到表单 / 继续编辑」（编辑器无响应时也一定有出口）；平台确认期间编辑器先答复 ⇒ 关掉平台确认、按晚到答复处理。
- 强制保存那条路不问确认器：编辑器的「确定」会撤销全部改动，已送达的改动会被撤销后再保存。
- 浏览器：没改动 ⇒ 1 次 requestClose、101 ms 回表单；输入中点保存 ⇒ 编辑器提示 + 平台指引、零请求；随后选「确定」⇒ 0.86 s 自动回表单（强制保存返回码 4）；选「取消」后再点保存 ⇒ 编辑器提示与平台确认同时出现，选「放弃输入并回到表单」⇒ 恰一次 leave、123 ms 回表单。
- 判据 `editorLeaveConfirm.spec.ts` 26 例（确认器 14 / 登记位 5 / 宿主 7）；A / H 视图开关各 1 例（KEPT 不报、其它拒绝照报）。

### 9.3 T3 R2 后端按 entry 准备注册（2026-10-25）

- `entry_scoped_registration.prepare_entry_only`：目标底稿没有 current representation ⇒ False（调用方回落锁内整套建）；有 ⇒ 绑定缓存未命中时在工作线程预热源码事实与本 entry provider 模块的模板结构 hash，返回 True；不写 `_REGISTRATION_CACHE`。源码事实的单飞放在 `registration_template_warmup.warm_source_facts_once`（线程锁），冷建也改走它 ⇒ 预热与回调同时到达只算一次。`entry_source_facts.py` 本身已超行数门（HEAD 1257 > 1150），不动它。
- 接线：`_attach_pilot_adapters(svc, entry_scope=…)` 命中缓存照旧重放；未命中且准备成功 ⇒ 返回 `()`、不进全局锁。`_apply_durable_incoming` 传 `(application.entry_id, application.wp_id)`，`_registration` 传 `(scope.entry_id, scope.wp_id)`。
- R2.3 逐个核对：调 `_registration` 的 8 个端点（store-projection / adopt-substrate / materialize / materialize-from-store 及其 `_materialize_request` / 冲突 conflicts / resolve / retry / 版本 rollback）只用它返回的注册；路由里 `svc.registry` 除这两个函数外没有读者，`oo_to_html` / `conflicts` / `content` 等 service 构造时不拿 registry ⇒ 全部接入，没有保持原样的端点。
- 判据：`test_entry_scoped_registration.py` + `test_target_bound_registration_wiring.py` 新增 / 改写，62 例全过。磁盘变异（隔离 worktree）B1~B14 全部打红：忽略准备结果、无 representation 也跳过、写部分快照、两个调用方不传 / 传错 scope、准备恒 True、预热全部 provider、源码事实在事件循环上首算、绑定缓存命中也预热、去单飞锁、冷建绕过单飞、provider 不看 blocked_reason、准备放进全局锁。
- 相关测试文件前后对比（按用例名逐条）：13 个文件 900 → 901 passed / 26 failed 不变（+1 为新接线判据）；另 26 个文件 1033 passed / 14 failed / 6 errors 前后完全相同（task32 归档路径缺失 6 errors 等均为 HEAD 既有）。
- 实测（R2.5，和平药房 2025 D2，每个场景一个全新进程、缓存全冷、只读会话 commit 被替换成抛错）：

| 场景 | 改前（等全局锁） | 改后（按 entry 准备） |
|---|---|---|
| 无人在建，回调自己冷注册 | 48.9 s（整套 47.3 + 绑定 1.6） | 7.6 s（准备 6.0 + 绑定 1.7） |
| 预热整套冷建进行中（开始 1 s 后到达） | 46.3 s（预热 45.5 s） | 9.7 s（预热 51.4 s，照常完成） |

  四个场景绑定出的注册（adapter / 冻结定义 / binding / sibling 逐字段摘要）完全相同；改后请求 registry 只有本 entry 1 条（改前 31 条）。准备的 6 s 拆开：源码事实首算 6.3 s（扫前端源码，进程内只算一次、与预热共用）、模板结构 hash 0.36 s、注册指纹 0.24 s、representation 查询 2 ms。

### 9.4 T4 R3 P8 物化计划复用 incoming 提取（2026-10-25）

- `incoming_view_reuse.py`：`adapter.extract` 读 incoming（无退役身份）时逐 binding 登记 `(binding, 是否保留 identity 清册, 去掉 protected_findings 的 outcome)`，连同内容 sha256、形态、冻结定义（同一对象）、limits。`_materialize_within_scope` 开头取出即删；单 binding / 单趟 / 链式三条物化路径都交给 `_plan_materialize_step`，判据全部满足才用，任一不同照常提取（链式后续趟读中间产物，内容不同自然不命中）。
- 偏离 design §4 之一：文件身份按**内容 sha256** 比，不用 `_file_cache_key` 的路径 / mtime —— 同一路径在 mtime 精度内被改写会误命中，同一份字节换了路径会漏命中。每份 incoming（约 220 KB）多算一次 sha256，不到 1 ms；单趟物化全部 binding 共用一份字节，只算一次。
- 偏离 design §4 之二（T6 回放抓到）：真实 OnlyOffice 保存的 incoming 都把 `_GT_SYNC` 隐藏 sheet 掏空了，物化写的是从冻结 base 重注 runtime binding 的副本（`.gtsync-repaired`）。design 写的「写入用的不是原 substrate 就整份不取」使首版 P8 在真实保存里一次都不生效（D2 回放：计划仍提取 4 次）。扩展：写入副本正是重注出来的那一份、且逐 zip 部件（名字 / CRC / 大小）核对与 incoming 只差那个隐藏 part ⇒ 也认副本的字节摘要；G7 中性化等其它副本照旧不取。前提有判据钉住：掏空与重注后逐 binding 提取只差 `stats` 里的两项文件大小；写入计划读 substrate view 的字段集合按源码 AST 钉住为 region / scan / formula_inventory / projection / identity_inventory（不含 `stats`）；真实数据（和平药房 D2 回放）同样零差异。
- 判据 `test_incoming_view_reuse.py` 22 例：去掉 findings 后与不带 baseline 的重新提取逐字段相同（并钉住 findings 是 baseline 唯一影响的项、第一遍确有依赖 baseline 的 findings）；一次保存每个 binding 只提取 incoming 一次；内容 / binding / 形态 / 定义 / limits / 保留标志 / 未登记的表任一不同 ⇒ 重新提取；同字节换路径照用；非 incoming 与带退役身份的提取不登记；物化产物不变；掏空 `_GT_SYNC` 的 incoming 经重注副本照样复用、产物与不复用时逐 zip entry 相同；另有部件不同的副本、重注之后又换了一份的写入副本不认。
- 磁盘变异（隔离 worktree）P8-1~P8-20 全打红：不比内容 / binding / 形态 / 定义 / limits / 保留标志、不去 findings、其它副本也复用、退役身份也登记、已发布形态也登记、取出不删、adapter 不登记、物化不取、计划不用；重注副本不核对只差隐藏 part、只比部件名不比内容、写入副本不是重注那一份也认、不认副本摘要、副本摘要记成原件摘要、adapter 不交重注副本。
- 回归：见 §9.6 末。

### 9.5 T5 R3 P9 已发布形态提取跨请求缓存（2026-10-25）

- `published_extract_cache.py` + `parse_cache.PUBLISHED_EXTRACT_CACHE`（LRU 16，`clear_all_parse_caches` 一并清）。只在 `adapter.extract` 读已发布形态 / 物化反读且无退役身份时查 / 填；incoming 永不经它（走 P8）。值 = 合并后的 Projection（含转置 sheet）+ 主 binding 的 (projection, 公式清册)。
- 键 = 文件字节 sha256 + 契约 canonical digest + 冻结定义 / 全部 binding（保序）/ limits 逐字段递归规范化 + schema 版本。不用 `as_dict()`（漏 identity 清册字段）；规范化不认识的类型 ⇒ 这次不缓存，并按类型告警一次。实施中抓到：limits 的 OOXML 策略里有 bytes（ZIP magic），首版因此对所有提取静默不缓存 —— 改为 bytes 按十六进制规范化，变异 P9-10 钉住。
- 读冻结 base 时，命中与未命中都填 `_baseline["pair"]`；判据只写在 `_seeds_baseline_pair` 一处（adapter 里原来那段 seed 删掉）。
- 判据 `test_published_extract_cache.py` 10 例（真 D4，39 binding）：命中与重新提取逐字段相同且命中零提取；键随每个输入变（定义 7 项、binding 4 项、limits 2 项、字节、契约）；同字节换路径命中；incoming / 退役身份不查不填；冻结 base 命中与未命中填同一 pair、读别的已发布文件不填；物化反读填入后下一次 base 读命中；merge / overlay 不改写缓存值；清空与上限。
- 变异 P9-1~P9-16：首轮 14 条打红，P9-11（已填过 pair 也覆盖）与 P9-12（读的不是冻结 base 也填 pair）存活。P9-12 补「带 base 的 adapter 读另一份已发布文件不填 pair」后打红；P9-11 是等价变异 —— 能走到那里的只有再读一次同一份冻结 base，覆盖进去的是同一份内容（主 binding 结果与 `derive_baseline_from_representation` 的入参逐项相同），这道条件只省一次重复赋值。
- 内存（tracemalloc，D2 回放后缓存 4 条）约 25.5 MB，单条约 6.4 MB；上限 16 条 ⇒ D2 规模每进程约 100 MB 封顶（39 binding 的 D4 单条更大，未单独量）。

### 9.6 T6 重放探针（2026-10-25）

同一条真实 application（和平药房 2025 D2，`ed12728b`，4 个 binding，incoming 222 KB 且被 OnlyOffice 掏空了 `_GT_SYNC`）在隔离 worktree 里前后各跑两遍：before = P8 / P9 文件换回 HEAD，其余同 after。外层只读（commit 换成抛错、application 行锁读后即 rollback），base / incoming 复制到临时目录，物化产物写临时 `.staging/`；storage 用 worktree 里的副本（主树 storage 未入库），主树真实 storage 前后指纹核对不变。每遍三轮：cold（进程缓存全冷）→ 同一 base 再来一次 → 下一次保存（base = 上一轮物化产物）。

| apply CPU 段合计 | cold | 同一 base 再来一次 | 下一次保存 |
|---|---|---|---|
| 改前（两遍） | 9.44 / 9.61 s | 8.93 / 8.80 s | 9.51 / 9.01 s |
| 改后（两遍） | 8.00 / 8.00 s | 6.47 / 6.56 s | 6.57 / 7.09 s |

- 提取次数：改前每轮 base 4 + incoming 4 + 物化计划（重注副本）4 + 反读 4；改后 cold 少了计划那 4 次（P8），后两轮再少 base 那 4 次（P9 命中，0.004 s）。首版 P8（不认重注副本）的同一回放 cold 仍是 9.7 / 8.9 s，见 §9.4 偏离之二。
- 每轮四个摘要（merged / readback / base / incoming）、structure hash、identity 清册摘要、受管字段数、物化产物逐 zip entry 全部与改前第一遍相同；cold 的 merged 摘要与库里记录的 merged / result projection（`bd632382…`）相同。
- 回归（隔离 worktree；改前 = 三个改动文件换回 HEAD、四个新增文件移走，改后 = 主树版本，按用例名逐条比）：109 个相关测试文件改前 3229 passed / 188 failed / 141 errors，改后失败与错误除两个新判据文件外逐条相同（新文件当时因 worktree 缺 D4 证据目录在 setup 报错）；补上证据目录后单独重跑 23 个 D4 harness 文件 + 两个新文件：改前 668 passed / 102 failed，改后 696 / 102，失败逐条相同。102 条为 HEAD 既有（如 12 个 phase5 模块缺 `resolve_published_frozen_definitions`、binding 数 40 ≠ 39）。P8 扩展（认重注副本）之后带证据目录重跑这 109 个文件（2 个不在 worktree 所在提交里、跳过）：改前 3397 passed / 150 failed / 11 errors，改后 3429 / 150 / 11（+32 = 两个新判据文件），失败与错误逐条相同。

### 9.7 T7 R4 先回表单、后台合并（2026-10-25）

- 状态机两态 `merging_in_background` / `background_merge_failed`（mode html；都不收 `flush_started` / `forcesave_started`，都不在 in-flight / 退出集合 ⇒ 关页不拦、编辑器退出按钮不显示）。展示三表补两态：合并中 progress（180 s 窗口封顶），失败 settled、动作提示指向表单顶部横幅。
- `bridgeBackgroundMerge.ts`：转后台 ⇒ 登记 → 桥持有追踪器（180 s、后端 `poll_after_ms`、桥的 api 通道）。落地（applied 且有结果 revision / refresh_required / superseded / duplicate）⇒ 按结果 revision 重载 → 释放 lease → `reload_completed` → 注销；冲突 / 失权 / 出错（带后端原因、可重试）/ 等超时 / 表单重载失败 ⇒ 失败态，lease 留到关提示（最后一道门要求发起人在线）。出口：重试回写（`retryOperation` 后重新追踪）/ 刷新状态 / 关闭提示（leave → reset → 注销）。追踪代次：停一次加一，被停掉的追踪器迟到的快照与到点都不起作用；桥卸载 ⇒ 停追踪、注销、不改状态。
- 宿主：`returnToFormPending && !dirty && 四个耐久态之一` ⇒ 停宿主追踪、`continueInBackground()`。第一份快照就落地的走原路径；保存受理后又改过、或不是宿主发起的保存，不交。
- 共享层顺带修：`WorkpaperSyncOperationTracker.readOnce` 读在飞时调用方已 `stop()` ⇒ 不再投递。原先 `deliver` 不看 stopped，交接那一刻宿主追踪器在飞的那一读回来，会把旧快照推进已转后台的状态机（非法转换 → 宿主报错）。
- 单点：`backgroundMergeRegistry.ts`（按 wpId 的响应式登记）；`GtWpRenderer.vue` 有效只读 = `readonly || 合并中`（模板 7 处 + scaffold），挂 `WorkpaperBackgroundMergeBanner.vue`（合并中只有说明；失败给原因与出口，不能重试时不给重试按钮）；`useChecklistPersistence.persist` 合并中拒写并丢弃（不留 pending ⇒ 合并结束后整体 flush 也不会把旧值补写回去盖掉合并结果）。
- 已知限制：前端生产代码另有约 279 处（245 个文件）直接 PUT / POST `checklist-responses`、不经 `useChecklistPersistence`，只靠渲染器传下去的只读挡住；D2 全部 tab 都接 `isReadonly`，其余宿主是否逐个遵守未逐个核对。业务组件的 `reloadHtml` 若让渲染器整体 reload（`loading` 使 Ready 模板整块卸载），桥随之卸载、后台追踪停止（服务端照常完成、lease 等过期，与改前 applied 路径相同）；D2 的 `reloadHtml` 是 `formData.loadAll()`，不触发。
- 改判据的既有用例（注释写明理由）：宿主 spec「incomingDurable / terminal 由真实状态推进触发」、T69-I32「八个事件逐个有真实触发路径」—— 宿主发起的保存现在耐久后就转后台，两条改为保存受理后再改一笔（人留在编辑器里），原判据不变；状态条「24 个状态」计数改按状态域现算（26）；桥 spec in-flight 补集加两态；UI 驱动器补两态的驱动路径。
- 判据：`backgroundMerge.spec.ts` 39 例 + `GtWpRenderer.background-merge.test.ts` 2 例。磁盘变异（隔离副本）48 条：首轮 46 条打红，F9（旧追踪器到点照收）与 H2（交接不停宿主追踪）存活 ⇒ 补「刷新状态后旧追踪器不起作用」「落地后两个追踪器都停（等过一个轮询周期读数不增）」两条判据，复跑打红。
- 回归：sync 目录 + 渲染器 / 持久化测试 1145 例，失败 17 例 = 改前同一组；受影响 155 个测试目标前后对比 198 = 198 失败、零新增；单区域 vue-tsc（含 `GtWpRenderer.vue`，24 GB 堆）改前 1457 / 改后 1456，新增 0（渲染器原有一处 `boolean | undefined` 随有效只读消失）。

### 9.8 T8 R5 `start-dev.bat` 热重载开关（2026-10-25）

- 新变量 `BACKEND_RELOAD_ARGS`：默认展开与旧命令逐字节相同；`GT_BACKEND_NO_RELOAD=1` 时为空（去掉全部 `--reload*`）并打印一行提示。文件保持 ASCII、CRLF；runbook `docs/runbooks/start-dev-launcher-notes.md` §七。
- 判据 `test_start_dev_backend_reload_switch.py` 2 例 + 既有 start-dev 守卫 37 例全过；变异（临时目录里放 bat 副本）S1~S4 全打红：关闭模式不清空参数、启动行仍写死 `--reload`、默认参数漏 `--reload-dir`、不打印关闭提示。

### 9.9 T9 浏览器实测（2026-10-25）

【测试】在线编辑回表单验收 D2-2（平台接口新建，1 个客户行）+ 和平药房 2025 D2-2（729 行，只读）。页面内记录器以点击事件为 0 点（MutationObserver + 50 ms 轮询判状态），请求耗时取 Resource Timing，服务端合并取 application 行 `created_at`（= 耐久）→ `finished_at`。

有改动回表单（改客户名称 B13；开始时机器约 15% CPU）：

| 轮次 | 回表单（编辑器关、表单只读 + 横幅） | 新值出现 | 表单恢复可编辑 | 服务端合并 |
|---|---|---|---|---|
| 1（worker 已运行约 50 分钟） | 1.44 s | 3.37 s | 3.49 s | 1.89 s |
| 2（worker 被并发会话的改动热重载后约 3 分钟） | 2.23 s | 4.85 s | 5.02 s | 2.71 s |
| 3（同 2，第二次） | 2.35 s | 4.84 s | 4.98 s | 2.67 s |

- 三轮都 applied、0 冲突，结果 revision 4 / 5 / 6；leave 后参与者 left。拆开（第 2 / 3 轮）：forcesave 请求 0.3 s → 轮询到文件耐久约 1.9 s（OnlyOffice 生成文件 + 回调落盘）→ 转后台；合并期间 D2-2 表格渲染为文字（输入框 39 → 4，剩下的是页面其它输入），新值先以只读文字出现；随后表单重载（两个 GET 共约 40 ms）、leave 70~100 ms、横幅消失、输入框回到 39 个。
- 更早一轮（同一项目、机器满载）：回表单 2.07 s、新值 4.59 s、服务端 2.5 s。
- 冲突路径（改金额，期末三个公式格 1000 → 2500）：表单立即可编辑，横幅「冲突」带「刷新状态 / 关闭提示」，关闭提示 121 ms；再次进入在线编辑正常（新 room）。冲突本身见 §9.10 第 1 条。
- 进入在线编辑（HTML → OO）：materialize-from-store 0.64 s（热重载后第一次约 1.9 s）→ 编辑器 iframe 出现 0.68 / 1.89 s →「OnlyOffice 编辑中」3.46 / 5.04 s（之间约 2.8 s 是 OnlyOffice 自己加载文档）；编辑器里 B13 是表单的最新值。
- 出错出口：编辑器里改过一格后把页面断网（chrome-devtools 网络模拟，OnlyOffice iframe 也随之「失去网络连接」），点「保存并回到表单模式」⇒ 77 ms 进出错态，显示「退出在线编辑」；点它 ⇒ 确认框「在线编辑里还有改动没有保存到表单，退出后这些改动不会回写。确定退出？」（继续编辑 / 退出）；选「退出」⇒ 124 ms 回表单（leave、表单重载都因断网失败，按设计不阻断），值仍是改动前的「验收客户己」。恢复网络后：OnlyOffice 约 1 分钟后发来 status 2 回调，后端判 unmatched、不合并，与确认框的说法一致；那一代 lease 因 leave 没送达仍 active 到过期，但不挡路 —— 再进在线编辑开新一代 room（3.69 s 可编辑），编辑器里是表单的值；不改动点「保存并回到表单模式」103 ms 回表单、恰一次 leave。
- 和平药房 2025 D2-2（只读，不改任何格；后台同时在跑 §9.6 的回归，CPU 约 40%）：进入在线编辑 materialize-from-store 1.12 s、iframe 1.16 s、「OnlyOffice 编辑中」5.66 s；不改动点「保存并回到表单模式」167 ms 回表单，恰一次 leave（73 ms）；库里核对 0 个新 application、0 个 forcesave 请求、参与者 left。
- 没在真实环境复现：冻结态（返回码 4 但改动没送达）—— 要只断 OnlyOffice 的同步通道、不断平台接口，网络模拟做不到；由 §9.1 判据与变异覆盖。和平药房只做了不改动的路径，出错出口改在【测试】项目上做。

### 9.10 实测中发现、本 spec 未修（需拍板或另立）

1. **D2-2 在编辑器里改金额必冲突**（改文字不受影响）。冲突 application `7cdfbe36` 的 3 条冲突全是公式字段：期末余额 Q / 期末未审 S / 期末审定 AB（`server_formula`、`read_only_formula`），base 1000 / current 1000 / incoming 2500。根因：OnlyOffice 在用户改了可编辑的金额后重算公式格，`merge.py` 对受保护字段只要 incoming 与 base 按分取整后不等就判「在 OO 侧被改动」（Property 24）⇒ 整条 application 进冲突，那格可编辑的改动也落不了地。发生额、期初、调整列的改动都会带动这几个公式格，等于 OO 侧改不了 D2-2 的金额。建议另立 spec：公式格本身没被改写（公式清册与冻结 base 一致、无 tamper finding）且合并后可编辑字段全部取了 incoming 时，把公式格的 incoming 视为重算结果放行；否则维持冲突。改的是合并语义的核心判据，需要拍板。
2. 冲突后 / leave 没送达时 lease 留到过期（约 4 小时）：服务端对非终态冲突拒绝 leave（`participant_leave_refused_in_flight`），断网退出时 leave 根本没到。不挡再次进入（开新一代 room），改前就是这样。
3. `utils/http.ts` 断网分支动态 `import('./feedback')`，断网时这次 import 自己也失败 ⇒ 原来的网络错误被替换成 `Failed to fetch dynamically imported module …/src/utils/feedback.ts`，在线编辑状态条原样显示这串英文（应为中文断网提示）。全局请求共用，改前就有，本 spec 未动。
4. 已在 §9.7：约 279 处直接 PUT / POST `checklist-responses` 不经持久化层，只靠渲染器的只读挡住。
