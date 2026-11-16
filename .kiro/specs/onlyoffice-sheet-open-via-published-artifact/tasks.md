# 任务：Sheet 级 OnlyOffice 改走 Published Representation

> **状态：19/34（2026-11-16，Phase 1.1~1.5 + 2.1~2.6 + 3.1 + 3.6 + 3.7 + 5.3 + 5.4 已完成；真源层 / 服务端解析层 / 前端三态与文案 / legacy ledger / 契约守卫 / 变异套件已收口）**
>
> 本 spec 必须在现状事实冻结后再改生产代码。所有 `[ ]` 都是必做任务；外部依赖不能标绿，必须写明 owner、证据和下一步。

## Phase 0：事实冻结与范围裁决

- [x] 0.1 固化旧式调用面：现算 backend 三个旧端点、前端 78 个调用 / 29 个文件，按 host、composable、Word、custom、single_onlyoffice 分组。
  - 产物：`evidence/legacy-sheet-onlyoffice-callers.json`（raw string mentions 81/30，去掉本 spec 新增唯一 helper 与共享声明后的 direct call baseline 78/29）。
  - _R: 4, 5, 6_
- [x] 0.2 固化 manifest / entry / representation 事实：现算 manifest entry、capability、`xlsx-sheet/*` 命名空间、current representation、mount host 与 room host。
  - 产物：`evidence/entry-and-representation-baseline.json`；共享 PG 行数只作 snapshot，不是永久门槛。
  - _R: 1, 2, 8_
- [x] 0.3 逐入口列出 sheet→entry 候选映射，分为 `exact` / `provider` / `whole_workbook` / `ambiguous` / `out_of_scope`。
  - 不得把当前 `sheet_entry_id()` 生成的 `xlsx-sheet/*` 直接当作已存在 entry。
  - 产物：`evidence/sheet-binding-adjudication.json`；首批候选为 K11 provider mapping 与 D4 aggregate source-sheet mapping，custom/Word 明确 out_of_scope。
  - _R: 1, 5_
- [ ] 0.4 完成五角色范围复核：合伙人确认打开对象与业务含义，项目经理确认 rollout，质控确认不伪造双向，审计助理确认界面文案，EQCR 确认历史 operation / artifact 审计边界。
  - _R: 5, 6, 10_

## Phase 1：SheetOpenBinding 真源与生成器

- [x] 1.1 定义 `sheet-open-binding:v1` JSON schema 与封闭枚举：scope、mapping_kind、status、reason、source_refs、digest。
  - 守卫拒绝缺 entry、缺 source digest、重复 binding、未知 status 与裸正则；`test_sheet_open_bindings.py` 现算覆盖。
  - _R: 1, 8_
- [x] 1.2 实现 `generate_workpaper_sync_sheet_open_bindings.py`：从 manifest、reviewed overlay、provider `wp_match` / sheet declarations 生成 binding。
  - 提供 `--apply` / `--check`；内容不变重跑零 diff；当前生成 197 条 binding，全部保持 `pending` 或 `out_of_scope`，不伪造迁移完成。
  - _R: 1, 8_
- [x] 1.3 为 exact / provider / whole workbook 分别建立正向与反向 fixture；provider resolver 必须有稳定 resolver identity。
  - 三种 kind 各 2 例（正向 + 反向）：exact（唯一字面量 → target 确定但仍 pending；多字面量 / 多 wp_code 必须拒）· provider（运行时表达式 → 必带 `provider:<digest>`；**声明顺序无关**且声明集合变则 identity 变）· whole_workbook（`mounts` 里的整册标记 → scope 对、target 空；非 xlsx 落 out_of_scope 而非 pending）。
  - `resolver_identity = provider:<16 位 digest>`，由 `sorted(wp_code_patterns) + sorted(sheet_expressions)` 算 —— 与 manifest 顺序无关，重排不会让已审核 binding 集体失效。
  - 🔴 两处现读教训：`has_whole_workbook_marker` 扫的是 `mounts`（不是 `wp_match`）；顺序无关用例必须用**单个** wp_code（两个会被判成 ambiguous，provider 分支从未触达 ⇒ 排序变异存活）。
  - _R: 1, 9_
- [x] 1.4 把 ambiguous / no target / no entry / stale digest 作为显式 pending reason，不得生成父级兜底映射。
  - `PENDING_REASONS` 封闭域 8 条：`document_type_out_of_scope` / `whole_workbook_target_requires_reviewed_binding` / `exact_candidate_requires_published_artifact_review` / `runtime_sheet_name_requires_provider_binding` / `ambiguous_sheet_target` / `sheet_target_not_declared` / `source_digest_stale` / `manifest_entry_missing`。
  - `ambiguous` 与「没声明 target」分两条 reason（处置不同：前者要裁决选哪个，后者要补声明）。
  - 🔴 修一处真缺陷：多 wp_code 的 ambiguous 判定原在 provider **之后** ⇒ 永远进不来（`wp_patterns` 非空即命中 provider），已前移。
  - 父级兜底守卫：每条 binding 的 `entry_id` / `effective_entry_id` 都必须逐字在 manifest 里。
  - _R: 1, 5_
- [x] 1.5 生成 `backend/data/workpaper_sync_sheet_open_bindings.json` 与 source manifest，加入 clean checkout 入库守卫。
  - 生成物 + 生成器都必须被 `git ls-files` 跟踪（`Path.is_file()` 在本地恒真、在 CI 可能缺文件）。
  - 源 digest 齐备（Requirement 8.1）：`input_digest`（聚合）+ `source.{manifest,overlay,adjudication,wp_code_adjudication}_digest` + 三份源路径。补了原缺的 `wp_code_adjudication_digest`（只对**被读的那张裁决表**算，改文件里别的段落不该让 binding 变 stale）。
  - 幂等守卫：同输入重跑 `render()` 必须字节相同。
  - _R: 1, 8, 10_

## Phase 2：服务端解析与 Published Artifact 读取

- [x] 2.1 重构 `/sync/entry-identity`：由 `SheetOpenBindingResolver` 返回真实 manifest `entry_id`，删除对不存在的 `xlsx-sheet/*` entry 的直接假设。
  - 兼容旧响应字段，但新字段必须含 mapping status、target sheet、representation identity；route 级测试覆盖 pending provider mapping 不伪造 entry。
  - _R: 1, 3_
- [x] 2.2 把 sheet readiness 接到 binding 后的 effective entry；缺 mapping 时返回 200 pending 或 typed 409，不能把 EntryReadinessNotFound 当成 room ready。
  - `SheetOpenBindingResolver` 在 entry 缺失、provider 未审核、exact 多义时均返回 pending；端点测试证明不会生成 `xlsx-sheet/*` 虚假身份。
  - _R: 1, 3, 7_
- [x] 2.3 新增 published artifact reader：通过 current representation id、bundle、contract 与 canonical artifact layout 读取文件，禁止模板 copy / hidden-sheet mutation。
  - 实现 `services/workpaper_sync/sheet_published_artifact.py`：`current pointer → representation/artifact row → canonical visibility/path → sha256/size → OOXML target sheet` 五步固定顺序，任一步失败即抛 typed error，**不回退模板**。
  - 接线 `/sync/entry-identity`：只有 `ready` / `migrated` binding 才读 artifact（`pending` 走不通，防未审核入口被当可开）。
  - 守卫 4 例（reader）+ 4 例（endpoint，含 pending 不读 / ready 读 / target_sheet 传参）；变异 M1 门控恒假、M2 门控恒真、M3 去 target_sheet 传参**全部精确打红**。
  - 🔴 M2 首轮存活：pending 用例原先只断言「不抛」，而端点 `except Exception` 把断言吞成 pending ⇒ 改为**记录调用并断言为空**。这是「断言必须落在观测到的副作用上」的又一实例。
  - _R: 2, 7_
- [x] 2.4 descriptor 增加 target sheet / document scope 的冻结字段；单 sheet 使用 actionLink，whole workbook 保持完整 artifact 视图。
  - 实现 `services/workpaper_sync/descriptor_view_identity.py`（封闭域 + 归一化 + 组合约束）；`EditorLaunchDescriptor` 增 `target_sheet` / `document_scope` 两字段并纳入 `DESCRIPTOR_REQUIRED_FIELDS`；route 与 store service 均把 `resolve_launch_target_sheet` 的结果冻结进 `MaterializeRequest`。
  - 21 例守卫（`test_sheet_descriptor_view_identity.py`）：构造期封闭域 7 例、归一化 4 例、route/service 装配 AST 7 例、阴性对照 3 例。
  - 变异 11/11 全精确打红（含 `M1` 去 target、`M2` scope 字面量、`M3` 整册带 target、`M4` 枚举加宽、`M5a/M5b` 两处 route scope、`M6` store 丢 scope、`M7` 不转发 target、`M8` 归一化忽略 scope、`M9` 用原始 request 值、`M10` 去封闭域校验），零假红。
  - 🔴 首轮 5/6 存活：初版判据只查**字段存在性**（`target_sheet=None` 也能构造成功）⇒ 补「构造点实参表达式」与「被调方收到什么」两层 AST 判据才承重。这是「字段存在 ≠ 值正确」「测了被调函数一层，测不到调用方传没传参」的第三、第四层。
  - 🔴 顺带修 task 2.1 遗留的真回归：前端契约生成器只认 `USER_SYNC_PREFIX`，把兄弟前缀上的 `entry-identity` 判成「缺 scope 段」而整体 `raise` ⇒ 改为认**全部显式 scope 前缀**并投影 `prefixKind` / `WP_SYNC_SIBLING_PREFIX_TEMPLATE`；`task28` 的 6 条守卫同步（等价鉴权判据 `authorize_wp_read` 而非放宽白名单）。
  - 行数门：抽出 `descriptor_view_identity.py` 后 `materialize_coordinator` 3508 / `wp_sync_router` 3638 / `test_task28` 1957 全部回到门内（未抬白名单）。
  - _R: 3, 8_
- [x] 2.5 为 target sheet 缺失、candidate、bundle drift、artifact missing、artifact digest drift 建 typed error 与中文原因。
  - `PUBLISHED_SHEET_ARTIFACT_REASONS` 11 条封闭原因表（每条都给出可操作下一步）+ `DEFAULT_UNKNOWN_REASON` 兜底；`PublishedSheetArtifactError.as_dict()` 同时给 `error_code` / `reason` / `detail`。
  - 新增三类判据：`artifact_candidate_rejected`（candidate 是正常流程中间态，与「state 不是 published」分两类）· `artifact_missing`（路径可解析但文件不在，与 `path_unresolvable` 分两类）· `definition_bundle_drift`（representation 冻结 digest ≠ bundle 行 `canonical_payload_sha256` 现算值，**在读文件之前**拒）。
  - 端点回 `{reason, error_code}` 两样：只回 code 前端无话可说，只回中文无法分支。
  - 12 例守卫；变异 9/9 全精确打红零假红。
  - 🔴 首版把 bundle digest 字段猜成 `bundle_sha256` / `sha256`（真名 `canonical_payload_sha256`）⇒ `getattr(..., "")` 恒空 ⇒ 所有读路径都报 drift。这是「未确认接口先读一次」的又一次实例。
  - _R: 2, 3, 7_
- [x] 2.6 为 migrated binding 停止签发旧 config / WOPI / callback；pending / out_of_scope 保留独立在线编辑并在响应标明不同步。
  - `_wp_onlyoffice_legacy_url_gate.py` 改两层判据：**binding 状态机优先**（`migrated`/`retired`/`draining` 拒 409；`pending`/`out_of_scope`/`ready` 放 + `sync_mode=independent`），binding 层无结论时才走 readiness 层（与 2.8 第 ① 步同口径）。
  - 旧式 config 响应新增 `sync_mode`（值取自 verdict，非字面量）+ `binding_status`：前端据此显示「独立在线编辑（不同步）」而不是假「已同步」。
  - `draining` 独立文案（`DRAINING_MESSAGE`）：已打开的会话还能存，与 `migrated` 的「必须换入口」分开。
  - 生成物坏掉（`unresolved`）取中间档：放行 + 标 `binding_status=resolution_failed` + `logger.error`（不拒：会让全平台在线编辑一起挂；不静默：那是本 spec 交付物坏了）。
  - 17 例新守卫（`test_sheet_legacy_gate_binding_states.py`）+ 既有 9 例按新分层改口径；变异 9/9 全精确打红零假红。
  - 🔴 M8/M9 首轮存活：打桩了 `_binding_verdict` 整个函数 ⇒ 测不到它内部容错方向；`sync_mode` 无任何判据查 router 响应字段。补「调真实 `_binding_verdict` + 只打桩 resolver」与「AST 查响应字典键 + 值来源」后打红。
  - _R: 4, 6_

## Phase 3：前端宿主切换

- [x] 3.1 把 `onlyOfficeEntryConfig.ts` 改为读取真实 binding，不再把 `xlsx-sheet/*` 作为 entry 身份；保留 readiness / legacy fallback 的明确三态。
  - `OnlyOfficeEntryConfigProbe` 增 `bindingStatus`（封闭域 6 值）与 `syncMode`（`bound` / `independent`）。三态判定：`migrated`/`ready` → room（供给不就绪时**不回退旧式**，给原因）；`pending`/`out_of_scope` → 旧式但标 `independent`（**不是**不可用）；无 binding → 旧式（与改动前一致）。
  - 灰度期兼容：缺 `status` 时按 `room_ready` 判（否则前后端版本共存期所有已就绪入口会退回旧式）。
  - `probeLegacy` 返回 `LegacyProbe`（含 `syncMode` / `bindingStatus`）—— 服务端把这两个字段放在**响应顶层**（与 `config` 平级），首版按 config 内层读恒 undefined。
  - 15 例守卫（原 9 + 新 6）；变异 6/6 全精确打红零假红。
  - 🔴 两轮假绿：① pending 用例用 `room_ready: false` 写 ⇒ pending 被误判成 bound 时也走 legacy，无法区分（M1 存活）⇒ 改 `room_ready: true`（binding 是权威判定）；② 变异脚本用 `"FAIL " in line` 检测，而 vitest 输出带 ANSI 色 ⇒ 检测器恒空，M2 被误判成存活 ⇒ 去 ANSI + 解析 `Tests N failed` 摘要行。
  - _R: 1, 4, 6_
- [ ] 3.2 为 `WorkpaperSyncEditorHost` 增加 target sheet / whole workbook descriptor 接线；不得在业务 composable 自己调 materialize 或拼 callback URL。
  - _R: 3, 4_
- [ ] 3.3 迁移一个普通 single-sheet canary，从 `GtOnlyOfficeSheet` 切到 room host；记录 old URL、descriptor、target sheet 与 HTML 回读证据。
  - _R: 3, 9, 10_
- [ ] 3.4 迁移一个 whole-workbook canary；验证所有 sheet 可见、target sheet 正确、切回 HTML 不丢写。
  - _R: 3, 9_
- [ ] 3.5 迁移一个聚合 source sheet；验证映射到子 entry，不回退父级模板。
  - _R: 1, 3, 9_
- [x] 3.6 更新 pending / single_onlyoffice / custom / Word 的前端文案与入口门控；不得显示“双向回写”假状态。
  - 先现算再改：模板里 **40 条**含「已同步 / 双向回写」的文案，逐条核对后确认**没有一条**是「在线编辑已同步」的假状态（全部是业务语义：披露表→附注、审定数同步、H9 同步等）⇒ 不需要大改全仓文案。
  - 真实缺口一处：`GtOnlyOfficeSheet`（pending / out_of_scope / custom / single_onlyoffice 的载体）打开成功时**不告诉用户这是独立在线编辑**。已加常驻 `el-alert type="info"` 提示条：「独立在线编辑（不同步）」+「本底稿的在线编辑与左侧结构化表单各自保存，改动不会自动互相同步」。
  - 用 `type="info"` 而非 `warning`（这不是错误/降级）也非 `success`（那会暗示已同步）。`sync_mode` 默认 `independent`（缺字段按不同步显示 —— 反向会让灰度期全部显示假「已同步」）。
  - 12 例守卫（原 8 + 新 4）；变异 5/5 全精确打红零假红。
  - 🔴 三处假绿/假红：①文案判据首版扫全文 ⇒ 抓到我自己的说明性注释（「不得暗示已同步」）⇒ 改成只扫**模板文本 + 字符串字面量**；②`el-alert` 桩只渲染默认插槽而标题在 `<template #title>` ⇒ `wrapper.text()` 恒空（看起来像功能没实现）⇒ 桩补渲染命名插槽；③「默认显示」用例 mock 了成功的 config 响应 ⇒ `syncMode` 在赋值时被显式设成 `independent`，**默认值从未被验证**（M3 存活）⇒ 补「config 请求失败」用例让赋值语句不执行。
  - _R: 4, 5, 6_
- [x] 3.7 宿主闭包守卫：迁移 binding 的所有旧 `onlyoffice-config` 调用为 0；未迁移调用逐条存在 ledger、owner 与 reason。
  - 生成器 `generate_legacy_onlyoffice_caller_ledger.py`（`--apply` / `--check`，幂等）+ 生成物 `backend/data/workpaper_sync_legacy_onlyoffice_callers.json`：现算 **22 个调用方文件 / 27 处代码调用**（非注释、非测试），3 个合法入口（`onlyOfficeEntryConfig.ts` 唯一入口 + `onlyOfficeSheetConfig.ts` URL 拼装 + `utils/http.ts` URL 判断）。
  - 四条判据：①ledger 与**独立重算**双向相等（不漏登 / 不留死条目）②每条 owner（模块名 kebab-case）+ reason + next 三样齐全且 reason ≠ next ③登记行号必须真实指向含 `onlyoffice-config` 的代码行 ④`migrated`/`ready` binding 的入口不得仍在旧调用面里。
  - 13 例守卫（含阳性/阴性对照），1 skipped（空分母显式记录）；变异 10/10 全精确打红零假红。
  - 🔴 承重点两轮不承重：①首版按文件名猜 wp_code（`needle in stem`）—— 但 `exact` 那条是 `B60-1`，ledger 里没有 B60 的调用方 ⇒ 恒空（M10 存活）；②改内容判据后仍存活，因为**测试数据选错**（B60 确实没有 legacy 调用方）⇒ 最终把判据抽成 `_find_migrated_offenders()` 并补阳性对照（注入「K11 已 migrated」断言会红）+ 阴性对照（无关 wp_code 不得报红）。
  - _R: 4, 6, 10_

## Phase 4：Legacy Drain 与旧路径删除

- [ ] 4.1 将全局 legacy 开关收敛为 binding 级状态机：pending → ready → migrated → draining → retired。
  - _R: 6, 8_
- [ ] 4.2 新增旧 doc key / callback drain ledger：记录签发时间、TTL、binding、entry、generation、终结状态。
  - _R: 6, 7, 8_
- [ ] 4.3 migrated binding 的新请求不得签旧 URL；draining 只接受已签发且 scope / token / generation 全匹配的 callback。
  - _R: 6, 7_
- [ ] 4.4 旧 direct-write 分支按 binding 逐个删除；删除前守卫要求旧签发数、callback in-flight、drain timeout 连续为 0。
  - _R: 2, 6, 10_
- [ ] 4.5 删除无调用方的 `GtOnlyOfficeSheet` 兼容代码前，完成 grep 0 调用、测试全绿、独立提交与回滚标签；single/custom/Word 豁免必须有真实条件断言。
  - _R: 4, 5, 6_

## Phase 5：测试与真实验收

- [ ] 5.1 后端 unit / contract：mapping 唯一性、scope、target sheet、current representation、candidate 拒绝、path boundary、typed error。
  - _R: 1, 2, 7_
- [ ] 5.2 后端 PG：真实 `WorkpaperContentRepresentation`、bundle、artifact 读取与项目隔离；只读验证先独立事务，写入验收只用【测试】项目并可恢复。
  - _R: 2, 7, 9_
- [x] 5.3 前端 unit / AST：唯一 URL、唯一 binding resolver、migrated 旧调用为 0、pending 文案与模式集合封闭。
  - `onlyOfficeEntryConfigContract.spec.ts` 10 例，四条判据：①**唯一 URL**（`/sync/entry-identity` 字面量在前端必须为 **0** —— 3.1 起从生成契约 `WP_SYNC_SIBLING_PREFIX_TEMPLATE` 取；`onlyoffice-config` 只允许出现在 3 个合法入口或 **3.7 ledger 已登记**的文件里，白名单直接读 ledger 不重抄）②**唯一 binding resolver**（`binding_status` / `bindingStatus` / `BINDING_STATUSES` 只允许在唯一入口出现）③**pending 文案**（`syncMode` 两值封闭；扫**含注释**的全文找「已同步」/「双向回写」肯定式表述）④**模式集合封闭**（与后端 bindings 里出现的状态逐值相等 + 恰好 6 个成员）。
  - 变异 7/7 全精确打红零假红。
  - 🔴 三处判据形态修正：①首版只允许 3 个合法入口 ⇒ 22 个已登记调用方全被判违规（口径错：3.7 语义是「未迁移可以存在但必须登记」，5.3 判的是「**未登记**不许有」）⇒ 直接读 ledger；②`/sync/entry-identity` 断言「至少一处」而 3.1 已让它归零（那是更好的状态）⇒ 改「必须为 0」；③「已同步」判据只扫代码行而变异写在 JSDoc 里 ⇒ 改扫全文（Requirement 4.3 明确禁止靠注释隐藏）。
  - _R: 1, 4, 6, 10_
- [x] 5.4 变异：删 mapping、伪造 parent fallback、candidate 冒充 current、恢复 template copy、去掉 target sheet、绕过 legacy token、让 old callback 无条件写入均必须 RED；阴性对照 GREEN。
  - `test_sheet_open_mutation_suite.py`：7 类变异 + 1 阴性对照 + 4 条元判据，**可重复运行的套件**（不是一次性脚本）。默认跳过，`GT_RUN_MUTATION_SUITE=1` 时运行（约 2 分钟）。
  - 每条断言 `expected_test` 出现在 FAILED 列表里 —— 只断言 `rc != 0` 会漏「收集期语法错」与「红在别的用例上」两类假红。
  - 实测 **11 passed**：7 类变异全 RED（各自红在点名用例上）+ 阴性对照 GREEN。
  - 🔴 六轮修复（每轮都是真问题）：
    1. 阴性对照选生成器当靶点 ⇒ 改源码必然触发 `--check`（比的是产物字节），不是「语义不变」⇒ 改到 `descriptor_view_identity.py`。
    2. `expected_test` 正则只写 `def` 而用例是 `async def` ⇒ 恒找不到。
    3. **02 变异存活** = 真缺口：判据只查 `entry_id` 集合，而伪造父级兜底正是通过 `effective_entry_id` 实现 ⇒ 补 `test_effective_entry_id_is_never_a_forged_parent_fallback`（三层：在 manifest 里 / 不是同一固定值 / 与 entry_id 不同时必须 `independent_entry=False`）。
    4. 沙箱化后 `--check` 抢红 ⇒ 让 freshness 判据也认 `GT_SHEET_BINDINGS_OUT`，并加 autouse fixture 在运行期重赋 `GEN.OUTPUT`（module-level 常量 import 时求值一次，光设环境变量不够）。
    5. `_SANDBOX` 进程级缓存 ⇒ 7 条变异共用目录、阴性对照读到上一条变异残留 ⇒ 改**每条用例独立沙箱**且跑前先 apply。
    6. `test_generated_projection_is_tracked_by_git` 用 `relative_to(REPO)` 对沙箱路径抛 ValueError ⇒ 沙箱模式显式 `pytest.skip` 并说明原因（真实 CI 无 `GT_SHEET_BINDINGS_OUT`，照常执行）。
  - 生成器新增 `GT_SHEET_BINDINGS_OUT` 覆盖（默认写真实路径，语义不变）。
  - _R: 1, 2, 3, 6, 10_
- [ ] 5.5 Playwright：普通 sheet / whole workbook / 聚合 source sheet / pending fallback / drain 五条 required scenarios；记录网络、console、页面错误、数据快照与 artifact identity。
  - _R: 3, 4, 6, 9, 10_
- [ ] 5.6 clean checkout：生成物 `--check`、后端测试、前端定向测试、构建、路由注册、行数门与 git tracked 交付物检查。
  - _R: 8, 10_
- [ ] 5.7 更新 umbrella 2.8 的余项状态、INDEX、memory 与归档证据；只有完成门满足后归档本 spec。
  - _R: 10

## 依赖图

```text
0.1~0.4
   │
   ▼
1.1~1.5  ─────► 2.1~2.6
                    │
                    ▼
                 3.1~3.7
                    │
                    ▼
                 4.1~4.5
                    │
                    ▼
                 5.1~5.7
```

## 当前明确不做的事

- 不在本 spec 中修 `wp_generation_staging._source_paths` 的 `multi_resolver`：它依赖 staging 是否应受 Property 42 canonical path boundary 约束，需单独裁决；当前错误替换已回退，原有 4 行 writer debt 保持真实。
- 不把当前 78 个旧式调用按文件机械替换；只有 binding 成为 `migrated` 后才允许迁移，pending 继续标独立在线编辑。
- 不修改当前工作树中其它会话的 frozen contract、OO template parity、published identity observer 等脏文件；本 spec 的任务按 clean candidate tree 执行。


## Umbrella 交接边界（2026-11-16）

本 spec 是 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 2.8 中「sheet 级旧入口与 published artifact 打开语义」的后续承接者。它不把原 umbrella 的未完成项自动标绿：

- 本 spec 承接：SheetOpenBinding、真实 manifest entry、published artifact、target sheet / whole workbook、前端宿主切换、legacy drain 与相应 sheet 级浏览器场景。
- 本 spec 不单独宣称完成 umbrella 6.3 的全部 entry required scenarios；全量 bidirectional entry 的 operation / evidence 账本仍需后续 owner 按原 umbrella 口径闭合。
- 本 spec 不单独宣称完成 umbrella 7.5；五角色最终复核、clean-checkout 总验与最终归档必须在本 spec 及相关 residual owner 的证据齐备后执行。
- 原 umbrella 的 `_source_paths` resolver debt 仍保持真实，需先裁决 staging 是否应纳入 Property 42 canonical path boundary，不因本 spec 的 sheet 映射而自动关闭。
