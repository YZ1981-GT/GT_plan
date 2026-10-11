# 设计：D2 在线编辑恢复与「任意企业首次打开」平台闭环

## §1 根因（2026-10-10 现场证据，按请求链路顺序）

| # | 缺陷 | 证据 | 影响面 |
|---|---|---|---|
| 1 | N1/N2/N3/N5 调用不存在的 `_L.attach_adapters`（`298ff78d8` 引入） | `register_from_manifest` 抛 `AttributeError`，非 `SyncDomainError` 不隔离 | 186 条 entry 注册全中断，所有 sync 端点 500 |
| 2 | D2 发布链走编排工厂内部**单数** `instrumentation_spec()` | 库里全部 D2 bundle 的 instrumentation 都是 `46f3c617`，只声明 `d22-managed`；模块自带的复数 payload 从未进发布链 | 观测器按冻结 instrumentation 找 sheet，找不到 d23/d21 ⇒ `ContractDriftError` ⇒ D2 永不注册 |
| 3 | 工厂 attach 不传兄弟 binding | `build_excel_adapter(...)` 无 `sibling_bindings` | 修好 #2 后 D2-3/D2-1 两个方向静默退化为只同步 D2-2 |
| 4 | 兄弟受管 sheet 的跨表引用不做传播逆替换 | dry-run：4 个 binding 中 D2-2、D2-3×2 等价；D2-1 有 9 格差异，**全是** `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)` → `$754`；样式索引 `s` 差异 0 格 | 发布 / materialize 必报 `adapter_unmanaged_region_drift` |
| 5 | 新 content version 的 generation 恒从 1 起 | `uq_wpoor_generation (wp, entry, generation)` 是 entry 全局；D2 09-26 升过定义（gen 2），gen 1 room 已 superseded | 任何业务提交后点在线编辑恒 `room_not_writable`（且被映射成 500）；D4/G7 已用白名单各自绕过 |
| 6 | 无运行时首版路径 | `publish_first_generation` 只有宿主脚本调用；宿主按全序为每个 entry **只选一张**目标底稿；现算 71 个 entry 有 entry_state、最多 2 张底稿 | 非 canary 企业点在线编辑恒 `materialize_substrate_not_published` |

#4 的修法在 `normalise_propagated_part` 的注释里早有伏笔：它明写了 D2 `sheet3.xml`（审定表D2-1）上 18 处 SUMIF 的传播声明 ——
声明一直在，只是兄弟受管 sheet 的单元格 digest 从不读它。

## §2 现状 grep 确认（动手前逐项核对坐标）

- 工厂：`phase5_entry_orchestration.build_orchestration` 的 `instrumentation_definition_payload()` 用单数 `build_instrumentation_payload`；`attach_adapters` 只传 `binding=observation.identity_binding`。工厂用户 8 个，只有 D2 / K1 自带复数 `instrumentation_specs()`，K1 自己实现了 `publish_definitions`。
- D2 契约：`pilot_d2_large_json.build_contract_payload` 内嵌 digest 用单数（10-03 注释写着「与 orchestrator 保持一致」—— 对齐了错误基准）。
- D1 先例：`phase5_d1_notes_receivable` 的 publish 与契约均走复数，attach 调 `attach_sibling_bindings`。
- 未管理区域：`excel_extract.unmanaged_region_digest` 对受管 sheet 调 `_managed_sheet_cell_digest` / `_sheet_structure_digest`，只认 `row_shift`；`propagation` 只作用于各桶 part。
- generation：`ContentMutationService._next_generation_probe` 对 G7/D4 返回 `max+1`、其余返回 1；`_commit_once` 非白名单走 `next_representation_generation`（新 content version 下恒为 1）。
- room 判定：`RoomService.open_or_reuse_room` 内联两条拒绝条件（state 不在 live 集 / refresh-required）。
- 拒绝码表：`MATERIALIZE_REJECTION_STATUS` 按具体类登记，未登记即 500；`RoomNotWritableError` 未登记。
- action 词汇表：`wp_sync_router._WRITE_ACTIONS`；`test_read_only_actions_match_the_read_endpoints_exactly` 双向锁死端点 action 与名单。
- 前端契约：`generate_workpaper_sync_frontend_contract.py` 由 router 路由 + 拒绝码表生成；该生成物已登记为预存过期（`check_known_failing_registry`）。

## §3 设计决策

**D1（R1）** 4 个 N 文件改为 `_L.attach_l_entry_adapter(registry, IDENTITY, session=…, contract_payload_builder=…)`；
四者 SPECS 均为单 spec，与 N4 等价。守卫 `test_module_alias_attribute_resolvability.py` 用 AST 收集
`from app.services.workpaper_sync import X as Y` / `import … as Y`（含函数体内）后的 `Y.attr`，逐条 `hasattr` 解析。

**D2（R2/R3）** `Phase5EntryConfig` 新增两个可选钩子，默认 `None` = 旧行为逐字节不变：
- `instrumentation_definition_payload_fn`：给了就作为发布链的 instrumentation payload；
- `instrumentation_specs_fn`：给了就在 attach 时调 `attach_sibling_bindings(provider=<仅暴露复数 specs 的命名空间>, …)`。
D2 传入模块自带的复数实现；契约内嵌 digest 改为 `canonical_digest(instrumentation_definition_payload())`。
守卫：记录型 publisher（只记录不入库）跑每个已交付 provider 的 `publish_pilot_definitions`，取实际发布的 instrumentation payload，
断言契约 sheet_key 全部出现在其 `managed_sheets ∪ transposed_sheets ∪ static_sheets` 中。

**D3（R4）** `unmanaged_region_digest` 中：当 `propagation` 非空、`row_shift is None`，且声明里有 `part == region.sheet_part` 的条目时，
读出该 part 文本 → `normalise_propagated_part`（单一真源，与 `other_sheet_parts` 同一函数）→ 用一个只覆盖这一个 part 的只读 zip 视图
喂给 `_managed_sheet_cell_digest` 与 `_sheet_structure_digest`。只给 after 侧（before 侧调用不传 `propagation`，结构上已保证）。

**D4（R5）** rooms.py 抽出 `room_generation_reuse_refusal(room) -> str | None`（`open_or_reuse_room` 改为调用它，消息逐字不变）
与 `room_generation_is_retired(room)`（state ∈ {superseded, closed}，`ROOM_EDGES` 无出边）。
`_next_generation_probe`：G7/D4 仍无条件 `max+1`；其余 entry 的候选代际 = entry pointer 代际（无 pointer 为 1），
候选代际的 room 不存在或 `room_generation_reuse_refusal` 为空 ⇒ 沿用候选，否则 `max(rep, room)+1`。
`_commit_once` 统一走 `_next_generation_probe`，保证发布文件名与 representation 行的 generation 同源。

> **实施期勘误（候选代际）**：初稿写的是「查 generation=1 的 room」。实施时发现两处反例：
> ① definition upgrade / 换代旋转会把 pointer 推到 gen ≥ 2，此后候选取 1 会把升级后的提交拉回旧代际
>    （PG 守卫 `test_task25_materialize_coordinator_pg` 阶段 12 原本正是靠这个隐式假设复用 gen-1 room）；
> ② gen 1 一旦终结，「查 gen 1」规则让之后**每次**提交都换代，协同用户被拆进不同 room（AC 2.8）。
> 候选取 pointer 代际后：常态（pointer=1、room 可复用或不存在）与旧行为逐字节相同；只在撞死房间时换代。

**D4b（R5.4/R5.5）** 事务 C 内 `open_or_reuse_room` 抛 `RoomNotWritableError` 时，查该代际 room：终态 ⇒ 调既有
`_rotate_generation_for_stale_room` 为同一 content version 换代后重开一次；非终态 ⇒ 原样抛出（R6 → 409）。
必要性：OO→HTML 合并结果 ≠ incoming 时，`oo_to_html` 先按当前代际 commit、**再** supersede 本代 room（AC 4.11）——
commit 时 room 仍活着，D4 无从预见；此后内容未改的「重新 flush」走业务身份复用、不产生新 commit ⇒ 不换代即永久死循环。
非终态不换代：refresh-required / closing / recovery-required 的 room 可能仍有未终结 request 或待恢复的 durable incoming。

**D5（R6）** `MATERIALIZE_REJECTION_STATUS[RoomNotWritableError] = 409`，重生成前端契约。

**D6（R7）** 新伴生模块 `first_publication_on_demand.py` + 薄端点：
1. 已有 current representation（判据同 `resolve_plan` ③）⇒ `already_published`；
2. `resolve_plan` → 读 store（与 store-projection 共用 `read_store_payload`）→ `asyncio.to_thread(stage_instrumented_substrate)` → `publish_first_generation`；
3. router 统一 commit；revision 冲突 / `first_publication_already_done` 时 rollback 后复查指针，存在即 `already_published`。
前端：`workpaperSyncApi.ensureFirstPublication()`；桥在 materialize 抛 `materialize_substrate_not_published` 时
先把状态退回 `html_idle`（`identity_rejected` 边），调一次首版端点，成功后整条链路重跑一次；重跑仍失败按普通失败处理（不会无限重试）。

## §4 被否决的方案

| 方案 | 否决理由 |
|---|---|
| 单元格 digest 去掉样式索引 `s` | dry-run 证明 `s` 差异 0 格，问题不在样式；去掉会让样式篡改不可检测 |
| 环境变量跳过未管理区域校验 | 绕过判据；本轮已全部撤销 |
| 直接 UPDATE representation 行 | 表有 immutable 触发器；违背「升级只能新增 generation」 |
| 逐企业跑宿主脚本发首版 | 不是平台修复；新项目永远需要人工 |
| materialize 内部透明首版 | 客户端 pending token 冻结了旧 revision 与无 overlay 的 projection，首版后两者都失效，需服务端重铸 token，幂等语义被破坏 |
| store-projection 里顺手发首版 | 该端点契约为只读（不写库、不推 revision） |

## §5 风险

1. **首次打开耗时**：首版发布 = 模板 instrumentation + materialize + 反读校验，大表可能 30~60 秒，仅每张底稿每个 entry 首次一次；前端 http 超时 180 秒。
2. **参考 representation 选择**：attach 取「全序第一张可见底稿」的 representation 冻结定义。R7 之后有首版的底稿会变多，若将来定义升级而某张较新底稿未重发布，可能被选为参考导致 entry 注册失败。本 spec 只登记，另立 spec 处理（候选：优先选绑定最新 approved bundle 的 representation）。
3. **前端契约重生成**会同时带入此前漏生成的 `adopt_substrate` 路由（预存过期项），需同步删除 `check_known_failing_registry` 对应登记。

## §6 数据处置（R8）

1. 代码修完、守卫全绿后：`generate_pilot_d2_large_json_contract.py --apply` → `fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d2-accounts-receivable` → `d2_rematerialize_sibling_sheets.py --apply --force`（不设任何跳过开关）。
2. 新 representation 预期落在 gen 3（R5 生效），开新 room；历史行一律不删。
3. `0c8426e6.approved_at` 恢复为其 `created_at`（原值已被覆盖，同批 bundle 的 approved_at 与 created_at 相差 <1 秒）。
4. 已知不可恢复：autocommit 清理时删掉的 1 行 `working_paper_oo_client_confirmation`（gen 2 房间的确认记录，该房间将被 gen 3 取代）。

## §7 验收期根因与设计（R10~R21，2026-10-11 真栈逐条暴露）

> 🔴 **勘误**：R8 数据处置完成时曾判断「参考 representation 重发布后即对全部企业生效」——这是错的。
> 重发布只修好和平药房那一张参考底稿；第二家企业（重药安徽）随即撞上 R14：entry 级注册冻结的是和平药房的
> 741 行身份清册。此后每一条都只在**真栈往返**里暴露，修之前单元与 PG 守卫全绿。
> 「修一次对所有企业生效」的真实前提是：代码修复（R1~R7、R10~R21）+ 首次打开自动首版（R7）；
> 已经卡在旧缺陷上的历史数据（§7.4）仍要一次性处置。

### §7.1 根因（按暴露顺序）

| # | 真栈现象 | 根因 | 修法 |
|---|---|---|---|
| R10 | 和平药房 OO 改一格保存 ⇒ `state=conflict`，108 条 protected 冲突，全是公式字段 | base/current 是 HTML 侧 JS 累加后存进 store 的 float，incoming 是 OO 重算的 float，累加顺序不同（`3511.0600000000004` vs `3511.06`、相消残差 `-2.27e-13`）；篡改检测精确比较 | `merge.recomputed_values_equal`：金额按分（ROUND_HALF_UP）比，其余数值按 15 位有效数字；只用于「受保护字段篡改检测」与「客户端是否需重载」两处 |
| R11 | 重试后 content version 前进到 rev 40，镜像抛 `AttributeError: … has no attribute 'STORE_ITEM_IDS'`，错误处理再撞 `applied → error` 非法边（409） | `store_item_registry` 把 D2 登记成多 store item 型、provider 指向 bridge 模块；镜像硬取 `all_store_item_ids()` / `STORE_ITEM_IDS`，bridge 两个都没有。注册表、bridge、镜像各自「看起来对」，只有真跑一次 OO 保存才炸，且炸在 durable 之后 | bridge 补齐转发；全注册表逐 plan 守卫 + 「镜像解引用点 == 模型」完整性守卫 |
| R12 | 镜像抛 `StorePayloadError: 组合区行 'GTROW-D23CMB-0018' 无法判定归属` | D2-3 store 为空（多数企业如此）时模板受管区原样留着骨架行（首行「其中：」），extract 读回、merge 想建 store 行却无 category 信号；同源的 D2-2 侧：和平药房 store 里已躺着 12 条 `GTROW-D22-*` 示例行 | `template_skeleton_baseline.pure_template_skeleton_rows`：模板原样的骨架行跳过；填过内容的照常镜像；base 已有的照常更新；组合区 fail-closed 不放宽 |
| R13 | 保存 → 回表单 → 再点在线编辑：`confirm-descriptor` 恒 422「同一编辑会话不得用不同基线二次确认」 | HTML→OO 物化提交按 R5 沿用当前代际，同一用户 lease 被复用而 client-confirmation 钉在上一会话基线。更深一层：OO 按 `doc_key` 缓存文档，沿用旧 doc_key 时编辑器拿到旧文档、descriptor 记新基线 ⇒ 下次保存把 HTML 改动当成「OO 改回去了」静默覆盖 | `_next_generation_probe`：不随会话的提交遇「候选代际的 room 已被确认过」⇒ 换代 |
| R13b | applied 并回表单后 participant 仍 `active` 到 4 小时后的 `expires_at` | `reloadAfterApplied()` 只清本地 descriptor，不调 leave | 回表单恰发一次 leave（与 clean close 同端点），dirty 照实上报 |
| R13c | 「保存并回到表单模式」落地后停在编辑器，「同步中…」不消失 | `applied` 在桥的 in-flight 集合里，等的就是重载，而没有任何一方触发 | 共享宿主 `WorkpaperSyncEditorHost.vue`：本宿主发起的保存落地且无新改动 ⇒ 1.2 s 后 `reloadAfterApplied()` |
| R14 | 重药安徽 store-projection 422「OO 往返后丢失 729 个 row identity，首个 'dr-mtl5bqmm-0o950ft'」 | registry 按 entry 注册，provider attach 经共享解析器按 `wp.created_at, wp.id` 取**第一家**可见底稿的 representation，冻结身份跟着和平药房走 | `target_bound_registration`：解析器 pin（按 task 隔离）+ registry 三原语 `fork_unregistered` / `entry_provider` / `rebind_entry`；按 representation 缓存；绕过解析器 / 并发发布 / 目标不可见三种绑不上一律 fail closed；三个生产调用点按本请求底稿绑定 |
| R15 | 每次保存后的第一次 store-projection 38.75 s | entry 级注册缓存的指纹含 representation id，每次保存（新代际）⇒ 全平台冷建 | 指纹 = entry pointer 集合 + 指针所指 representation 的 **bundle** |
| R16 | callback apply 38.8 s | apply 路径不读注册缓存，每次冷建 | 先查缓存、命中跳过冷建；绑定调用包在 `_apply_durable_incoming` 既有的 try 内 |
| R19（D1） | 保存落地、回表单后 leave 恒 409 `participant_leave_refused_in_flight` | `REQUEST_EDGES[correlated]` 登记了 terminal / superseded / authorization_stale 出边，但全仓零生产写入方；守卫里 4 处裸 `UPDATE … SET state='terminal'` 恰好盖住缺口。真库每一次 OO→HTML 保存都滞留（68 条，最早 2026-09-11，涉及所有用过在线编辑的企业） | 伴生模块 `request_settlement.settle_requests_of_terminal_application`；协调器 `_advance_application` 落终态与 `supersede_application` 调用（`repository.py` 在行数门 whitelist 上，故不住仓储类） |
| R17 | OO 里清空一格保存 ⇒ 结构化视图仍显示旧值；下次进在线编辑时 HTML lane 冲刷把清空回滚 | extract 对空格省略键（「键缺失即 MISSING」），merged 也缺键；store 镜像只遍历 merged 里**存在**的键。真库：rev7（html）与 rev5（html）projection sha256 逐字节相同，store `updated_at` 停在 rev4 | `cleared_field_view.store_view_with_cleared_fields`：只给镜像补显式 null，发布的 projection 不变 |
| R18 | 同一页面第二次 OO 保存卡在「refresh_required 不允许经 operation 观测进入 application_bound」/「在线编辑不可用」 | 桥的 `canonicalApplicationId` 围栏跨会话残留：第二轮的新 application 被当成「同一会话里换了 canonical application」 | `beginSession()`：`apply('flush_started')` 之后重置 requestedOperationId / operation / canonicalApplicationId / applicationEffectiveSequence |
| R20 | 和平药房 D2-2 表格编辑模式改「公司代码」→ 立刻点在线编辑 ⇒ OO 里仍是旧值；之后在 OO 保存，HTML 那次编辑被覆盖（数据丢失、无提示） | 子 Tab 的 `useD2Detail` 有**私有** 2s 防抖，宿主 `flushHtml` 里的 `formData.flushPendingSave()` 只管宿主自己那层；网络序实测 GET store-projection 早于那次 PUT ⇒ rev45（html）投影仍是旧值；防抖随后照常落库，OO 保存回来以旧值为 base 镜像回 store | 平台注册表 `sync/pendingWrites.ts`（H 循环的 `hPendingWrites` 改为别名）；桥在**每次** `flushHtml` 之前 `await flushPendingWrites()`；D2 宿主 `d2SaveItems` 经 `trackPendingWrite` 追踪在途；14 个 `useD2*` 登记 flusher（语义与各自卸载时那段相同） |
| R21 | 控制台「[未捕获Promise] CanceledError: canceled」（`WorkpaperSyncOperationTracker.refresh`） | `handleContentUpdate` 两处 `void this.refresh()` 没有 catch；事件触发的补读常被 http 去重层取消（同一 operation 的轮询读正在飞） | 与轮询定时器同口径 `.catch(() => {})` |

R10 回应了用户「取数时只保留两位小数」的建议：两位小数用在「OO 重算出来的是不是同一个数」这个判定上；
存储值与可编辑字段**不**取整 —— OO 不重算可编辑格，那里任何差异都是用户真改的，取整会把多录的小数位悄悄吞掉。

### §7.2 设计决策（验收期）

**D7（R10）** 只在「OO 那一侧的值不会被采纳」的两处放宽：受保护字段的篡改检测（公式结果永远由服务端定，keep current）与「客户端是否需要重载」。可编辑字段仍走精确的 `values_equal`。

**D8（R11/R12）** 镜像失败一律发生在 durable 提交之后（OO 侧已落库、HTML 看不到），所以守卫按**全注册表**静态覆盖，而不是等真栈逐个踩：R11 逐 plan 校验镜像会无保护解引用的全部属性，R12 的骨架行判定读模板基线（`SkeletonBaseline`，只在有候选行时才读）。

**D9（R13）** 换代条件只看「候选代际 room 是否已被确认过」，且只对不随会话的提交生效；OO→HTML 提交必须留在会话代际（否则会话与内容分家）。

**D10（R13b/R13c）** 两处都改在共享层（桥 / `WorkpaperSyncEditorHost.vue`），D/F/G/H/K/L/M/N 各宿主不逐个改。lease 释放不是内容操作：失败不阻断回表单、不记 lastError。

**D11（R14~R16）** entry 级注册保留为冷建单元；请求期在其上按「目标底稿 + representation」绑定并缓存。指纹只跟 pointer 集合与 bundle 走 —— 「保存」只产生同 bundle 的新代际，不该触发全平台冷建；首版发布（新供给）与 bundle 重发布（RG-11 stale）才触发。

**D12（R19）** 结算挂在 application **终态写入点**上，而不是挂在各调用方：映射单源，所有终态路径（协调器单一写入点、supersede）共享一个结算函数；锁序与撤销路径一致（先 room 后 request）。error / conflict 不在映射里：它们仍有出边（重试 / 裁决）。

**D13（R17）** 「清空」只在 store 镜像视图里显式化。merge 真值表本就区分「清空（i=None）」与「载体删除（i=MISSING）」，xlsx 行内空格不可能是载体删除（行身份在、列在），所以「存活行里被 merge 判掉的可编辑字段」就是被清空的字段；`row_deleted` 必然落在「行不存活」里，不另设 verdict 过滤（那会是证伪不了的死分支）。

**D14（R18）** 围栏的语义是「同一会话内 canonical application 不得被换掉」，所以重置点是会话边界（进入在线编辑的 flush 开始），围栏本身不拆。为过 bridge 行数门，「失败归一」整段原样迁到 `sync/workpaperSyncBridgeFailure.ts` 并由桥 re-export（调用方零改动）。

**D15（R20）** 等待点放在**桥**而不是各宿主的 `flushHtml`：宿主够不着子 Tab 自己 new 的 composable 实例，而桥是所有宿主的唯一入口 ⇒ 写入方登记一次，全部宿主同时生效。两类写入各一种登记：防抖型 `registerPendingFlusher`（「有挂起就清掉并立即发起写入」）、在途型 `trackPendingWrite`（包在宿主注入给子 Tab 的保存函数上，一处覆盖下面全部子 composable）。scope 外调用不登记（生产里恒在组件 setup 内；scope 外只有脱离组件的单测，那里没有注销时机）。其余循环 108 个同形写入方规模超出本 spec，冻结为两向棘轮（`pendingWritesCoverageRatchet.spec.ts`）。

**D16（行数门）** 本 spec 改动使 8 个文件越过 `check_file_size`（pre-commit 按暂存文件阻断）。能原样拆出一个独立单元的就拆：`test_target_bound_registration.py` §4~§7 → `test_target_bound_registration_wiring.py`；task25 PG 阶段 13 的采集体 → `task25_room_generation_world.py`、R5/R6/R13 判据 → `test_task25_room_generation_reuse_pg.py`（按 task26 的 D1 先例按路径加载宿主 `snap`，57 例不变）。拆了会让判据失锚的按仓库既有做法在 whitelist 登记理由与拆分轴、基线 = 实测：registry（三原语直接维护双索引的原子换绑）、materialize_coordinator（事务 C 内的 except 分支）、merge（R10 判定用 merge 自己的规范化口径 + 消费方登记表单表维护）、test_task15（diagnose 工具按节点 id 锚定第 9 节）、EditorHost.spec（§11 零消费方判决按本文件计数）、phase5_d2_03（R12 接线，新入册）。

### §7.3 被否决的方案（验收期）

| 条目 | 方案 | 否决理由 |
|---|---|---|
| R10 | 取数 / extract 时把金额一律截两位 | 会改写可编辑字段的录入，并让全平台 projection digest 一起变 |
| R10 | 只吸收 15 位有效数字以外的尾差 | 实测 108 → 54 条，剩余尾差落在第 12~14 位（多项累加）；按分取整后为 0 |
| R12 | 镜像里无条件跳过 `GTROW-*` 行 | 用户往模板空行里填的内容会被静默丢弃（变异 TSB_M1 即此形态） |
| R13 | 维持「任何可复用 room 都沿用」 | confirm 恒 422，且 OO 拿到缓存的旧文档 |
| R14 | 每个请求按目标底稿冷建整套注册 | 实测冷建 30~38 s / 次 |
| R17 | extract 对空格输出显式 None | 全平台 projection digest / roundtrip 判据的辐射面 |
| R17 | 逐 provider 改 store 合并函数 | 几十个 provider；各合并函数本就按「显式 null = 清空」处理 |
| R17 | 只看 `merge.deleted_keys` | 漏掉冲突裁决路径；改用 `merge.verdicts` 的键 |
| R18 | 在 `reloadAfterApplied` 里清 requestedOperationId | 破坏 `WorkpaperSyncStatusBar.spec` 的构造前提 |
| R18 | 去掉 canonicalApplicationId 围栏 | 同会话 rebase 守卫必须保留（有测试锁死） |
| R19 | 只在出问题的调用点结算 | 新增的终态路径会再漏一次 |
| R19 | error / conflict 一并结算 | 二者仍可重试 / 裁决，结算即丢掉恢复出口 |
| R19 | 只结算 `origin_request_id` | 折叠进 duplicate 的 request 仍会滞留 |
| R19 | 先锁 request 再锁 room | 与撤销路径反序，有死锁风险 |
| R19 | 历史滞留用裸 SQL 迁移修 | 第二套规则；改为正式工具委派生产结算函数 |
| R19 / R18 | 抬高 `repository.py` / bridge 的行数基线 | 门禁语义是「打磨让文件变小」；改为伴生模块 / 原样拆分（这两处都有可原样拆出的独立单元，与 D16 里登记理由的六处不同） |
| R20 | 在 D2 宿主的 `flushHtml` 里逐个调子 Tab 的 flush | 宿主拿不到子 Tab 自己 new 的实例；且只修 D2 一个宿主，其余宿主照旧 |
| R20 | 切换前固定等 2.2 s「防抖窗口」 | 依赖各处防抖时长的猜测，每次切换都白等；登记式等待在无待写盘时零开销 |
| R20 | 把 108 个同形写入方一次全部接入 | 每个写入方的写出口各不相同（注入 / window 事件 / 直接 PUT），需逐个核对语义；规模超出本 spec ⇒ 冻结棘轮 |

### §7.4 数据处置（验收期，一次性；全部走平台既有函数，不手改表）

1. **R12**：和平药房 rev 40（application `3d1e557a`）落地后镜像失败 ⇒ R12 修好后，用同一平台函数 `store_mirror.mirror_projection_into_store` 喂 rev 40 已提交的 merged projection（落库前核对 artifact sha256）：`D2-detail-rows` 741 → 741 行，唯一差异 `dr-mtl5bqmm-ffdu55p.companyCode` `''` → `'RT-OO-1011'`（即那次 OO 编辑）。
2. **R13**：同一次镜像失败使 settle 没跑，和平药房 gen 3 room `6449c276` 停在 active、confirmation 钉在 rev 39 的基线上 ⇒ 用平台既有 `RoomService.supersede_room`（reason `post_durable_settle_skipped_r12`）作废，下一次物化按 R5 换代。
3. **R19**：正式工具 `backend/scripts/fix/settle_stranded_forcesave_requests.py --apply`（委派生产结算函数）：真库 68 条滞留（applied 66 + authorization_stale 2，最早 2026-09-11）→ 0。仍未终结的 29 条按设计不动：application=error 12 / conflict 9（可重试 / 裁决），frozen 无回调 8。
4. **测试 lease**：本轮验收产生的 7 条 participant 经正式 leave 端点释放（7 × 200）；更早的 44 条历史 lease（D4 39 条 09-21~09-30，其中 8 条挂着上面第 3 项的未终结 request、按设计拒绝离开；D1 / D2 和平药房 09-26 / M1 / M5 / M9 各 1）全部已过期，不动。

### §7.5 未修发现（登记，不在本 spec 修）

1. **保存 → 落地仍要 16~20 s**（durable → finished ≈ 16.5 s；R16 前 38.8 s）。
2. **镜像失败都发生在 durable 之后**（R11 / R12 / D2-3 组合区 fail-closed 都是这一形态）：OO 侧已落库而 HTML 不可见，settle 一步跟着不跑（§7.4 第 1、2 项即此）。应改为提交前预检或失败补偿。
3. OO 里 D2-2 表头下方 12 行空骨架行（模板占位；R12 只处理镜像侧）。
4. D2-2 结构化视图约 1023 个受控 `el-input`，大表输入卡顿。
5. 和平药房 D2-2 store 里 12 条 `GTROW-D22-*` 示例行（早先镜像写入；R12 防止再写，存量待业务确认后清理）。
6. 每次往返都产生新 revision：同一内容 HTML 侧与 OO 侧 projection 不等（D2-3 86 个骨架键 None / MISSING 口径不同；真库 rev11 / rev15（html）`0bf2a2bc…` vs rev10 / rev14（OO）`d6498432…`）。
7. 每次会话开新代际 room，旧 room 一直 `active`（重药安徽 D2 一张底稿 8 间、0 participant）；participant lease 过期后也没有清扫器（真库 44 条过期仍 `active`）。
8. adopt-substrate 路径对清空键有与 R17 同样的省略（受 AOS plan / verification 不变量约束，未改）。
9. OO 里清空**静态**受管格大概率触发 `missing_identity_carrier` 冲突（未实测）。
10. 普通 request 终结后不重跑 close-intent reconcile（close barrier 的 predecessor 计数要等下一次触发）。
11. `command_service.classify_editor_destroy` 无生产调用方。
12. `registry._describe_entry_supply` 的 entry_state 查询无 ORDER BY 就取 `.first()`；R7 之后一个 entry 有多张底稿的 pointer，结果不确定。
13. request / operation 的 `accepted` 态与 `accepted_at` 列零写入方（状态机直接 frozen → correlated），operation 读端点恒返回 null。
14. 既有红 / 环境项（非本 spec 代码引入）：`workpaperSyncBridgeMachine.ts(862,42)` TS2345 与 `d2SyncHostWiring.spec` 正则过期（HEAD 同红）；工作树里 J2 模板目录未跟踪的 `.bak` 致 task52 红（干净检出无此文件）；lane gate 真库读数 4 条（HEAD 上因 R1 走 skip，R1 修好后真跑才暴露，见 tasks 6.4）。
15. uvicorn `--reload` 重启 worker 期间的瞬时 401（仅开发环境）。
16. **R20 同形缺陷在其余循环仍在**：108 个「私有防抖 + 宿主注入写盘」的写入方未登记（D 13、D4 子 Tab 17、F 67、G 9、其他 2，清单冻结在 `pendingWritesCoverageRatchet.spec.ts`）⇒ 这些底稿改格后 2 秒内切在线编辑，同样可能丢编辑。接入方式见 D15（每个写入方一处登记，宿主注入的保存函数一处 `trackPendingWrite`）。
17. 行数门 whitelist 在 HEAD 上就有 8 行损坏（文件头 BOM、6 行 `$1xxxx`、2 行只有路径没有基线 —— 像是某次正则替换把 `$1` 写成了字面量）⇒ 这些条目被 `load_whitelist` 静默丢弃，`test_every_whitelist_entry_has_path_and_integer_baseline` 预存红。
18. `test_committed_code_imports_only_committed_modules` 在提交前必红：本 spec 新增的模块（`cleared_field_view` / `first_publication_on_demand` / `request_settlement` / `target_bound_registration` / `template_skeleton_baseline`，测试世界 `task26_d1_settlement_world` / `task25_room_generation_world`）已被已跟踪代码 import ⇒ **必须与本 spec 的改动同一次提交入库**，否则干净检出在 import 期就挂。前端 `sync/pendingWrites.ts` / `sync/workpaperSyncBridgeFailure.ts` 同理（被已跟踪的桥与 H 循环文件 import）。
