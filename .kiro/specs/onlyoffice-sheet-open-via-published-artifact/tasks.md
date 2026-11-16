# 任务：Sheet 级 OnlyOffice 改走 Published Representation

> **状态：23/34（2026-11-16，Phase 1.1~1.5 + 2.1~2.6 + 3.1 + 3.2 + 3.6 + 3.7 + 5.1 + 5.3 + 5.4 + 5.6 已完成）
>
> **本轮解开了 migrated=0 的死锁**（2026-11-16，用户指令「按建议来」）：
> - **新增 reviewed overlay 机制**：`backend/data/workpaper_sync_sheet_open_reviewed_bindings.json`
>   —— 生成器此前**硬编码**全部 status 为 pending/out_of_scope，spec design §3.2 第 1 步
>   要求的 "reviewed overlay" 从未实现。现已实现：只有该文件里列出的 entry 才允许晋级到
>   `migrated`/`ready`/`draining`/`retired`；无记录的一律保持 pending（spec 1.4 语义不变）。
> - **首个 migrated binding**：`xlsx/b60/gt-b60-bundle`（唯一 exact 候选）。现算 `migrated: 1`。
> - **顺带修一个真缺陷**：`SheetOpenBindingResolver` 按单值 `source_wp_code` 等值匹配，
>   而运行时 `resolve_sheet_wp_code` 会把底稿码换成父码（`B60-1` → `B60`，父码有模板时）
>   ⇒ **已 migrated 的 binding 命中不到**（真实库实测：端点恒 `sheet_binding_not_found`）。
>   修法 = 调用方传**候选码集合**（判定仍只有 `resolve_sheet_wp_code` 一份，不造第二套）。
>
> **余 11 项的真实阻断（现算）**：
> - **真环境 3 项**：3.3 / 3.4 / 3.5 —— 三项 canary 都要真实 OO 容器 + 浏览器取证。
>   B60 的 binding 解析链**已通**（端点返回 binding_id / entry_id / target_sheet=B60），
>   但下游 `current_representation_missing`：`working_paper_sync_entry_state` 里没有 B60 的行
>   （representation 表有 7 行历史数据，但无 entry_state 指向）⇒ 打开仍不可用。
>   要打开需**真实用户操作**「在结构化视图里保存一次以发布首版」，不是审核能代替的。
> - **治理前置 5 项**：4.1 / 4.2 / 4.3 / 4.4 / 5.2 —— 都有 1 条 migrated 了，但仍需真实
>   drain 周期观测（4.4 的「连续为 0」）与真实 published artifact 端到端（5.2）。
> - **治理收尾 2 项**：4.5（`GtOnlyOfficeSheet` 仍是 189 条未迁移 binding 的唯一载体）/
>   5.7（完成门未满足）。
> - **人的裁决 1 项**：0.4 五角色签字。
> - **真环境 1 项**：5.5 Playwright 五场景。
> - 环境侧**不是**阻断：`audit-onlyoffice` / `audit-postgres` / `audit-redis` 均 healthy。

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
- [ ]* 0.4 完成五角色范围复核：合伙人确认打开对象与业务含义，项目经理确认 rollout，质控确认不伪造双向，审计助理确认界面文案，EQCR 确认历史 operation / artifact 审计边界。
  - **阻断类别：人的裁决**（不是代码、不是环境）。owner = 用户/团队五角色。
  - 代码侧证据已就绪可审：①打开对象与业务含义 → `backend/data/workpaper_sync_sheet_open_bindings.json`（197 条逐条写明 `mapping_kind` / `status` / `reason`，可逐条裁决）；②rollout → 4.1 的状态机已定 `pending → ready → migrated → draining → retired`（见 design）；③不伪造双向 → 3.6 已加「独立在线编辑（不同步）」提示条 + `sync_mode` 默认 `independent`；④界面文案 → 3.6 的 40 条现算核对 + 12 例守卫；⑤历史 operation / artifact 审计边界 → 5.3 的 ledger（22 文件 / 27 处调用逐条 owner+reason）。
  - 下一步：把上述四项证据交五角色逐条签字；签字后本项可勾。**不得由我代签。**
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

- [x] 1.6 实现 reviewed overlay：`workpaper_sync_sheet_open_reviewed_bindings.json` + 生成器读取，解 `migrated` 恒为 0 的死锁。
  - **现算缺口（本轮实测）**：生成器 `binding_for()` **硬编码** status 为 `pending` / `out_of_scope`，
    **没有任何「已审核」输入** ⇒ `migrated` 恒为 0 ⇒ 3.3 / 3.4 / 3.5 / 4.1~4.4 / 5.2 全部无对象可验。
    而 spec design §3.2 第 1 步明文要求生成器「读取 manifest、**reviewed overlay**、provider」——
    该输入从未实现。
  - **为什么不复用 `workpaper_sync_entry_overlay.json`**：那是**组件级默认值**文件，180 条 entry
    共用（改一项会同时翻转全部 `GtOnlyOfficeSheet` entry 的 capability）。「审核某一条 binding
    可以迁移」与「改组件默认值」是两件事。
  - 新增文件 schema `sheet-open-reviewed-binding:v1`，`decision` 封闭集
    `{ready, migrated, draining, retired}`（**不含** pending —— 撤回审核应删记录，不是留
    `decision=pending`，否则无法区分「没审过」与「审过但决定不迁」）。
  - 生成器改动：`load_reviewed()` + `binding_for(reviewed=...)` + `input_material["reviewed_digest"]`
    （改审阅记录必须让 `input_digest` 变，否则「改了审阅却没重跑」`--check` 发现不了）。
  - **三条现算防御**（都配守卫）：①`decision` 不在封闭集 ⇒ 报错；②`entry_id` 不在 manifest ⇒
    报错（拼错会让审核静默失效）；③`entry_id` 重复 ⇒ 报错；④`out_of_scope` 不许晋级
    （Requirement 2.7：Word / custom 不进 room 协议）。
  - **首个 migrated binding**：`xlsx/b60/gt-b60-bundle`（唯一 exact）。现算
    `summary.status_counts = {migrated: 1, out_of_scope: 7, pending: 189}`。
  - 守卫升级：`test_projection_does_not_claim_migration_without_reviewed_binding` 原是首版
    临时形态（`claimed == []`），现升级为**双向**判据 —— ①claim 高级状态的每一条必须在
    reviewed 文件里且决策一致；②没有记录的必须仍是 pending/out_of_scope。只做单向会让
    「reviewed 有记录但生成器没生效」静默通过。
  - 新增 6 条 reviewed 守卫（正向 / 反向 / 封闭集 / 拼错 / 重复 / out_of_scope），
    `test_sheet_open_bindings.py` **28 passed**。
  - 变异 **6/6 全打红**（逐字节恢复一致）。🔴 M2 是**组合变异**：`decision` 封闭集在
    loader 与 `binding_for` 各有一道校验，只变异一道会被另一道兜住 ⇒ 变异存活（假存活）。
    M1 去覆盖 / M2 同时去两道 / M3 去 manifest 校验 / M4 去重复校验 / M5 放开 out_of_scope /
    M6 无 reviewed 也伪造 migrated。
  - _R: 1, 8_
- [x] 1.7 修 `SheetOpenBindingResolver` 的单值 wp_code 匹配缺陷（已 migrated 的 binding 命中不到）。
  - **真缺陷（2026-11-16 真库实测）**：`resolve_entry_identity` 先算
    `sheet_code = resolve_sheet_wp_code(wp_code, sheet_name, wb)` —— 对 B60 得 `B60`
    （底稿码 `B60-1`，但父码 `B60` 有自己的模板 ⇒ 换码），而 binding 的 `source_wp_code`
    是 manifest 的 `wp_code_patterns[0]` = `B60-1` ⇒ **单值等值匹配恒不命中**。
    表现：`GET /sync/entry-identity?sheet_name=B60` 返回
    `status=pending, reason=sheet_binding_not_found`，**而 binding 已是 migrated**
    —— 这正是本 spec 要消灭的「假迁移」。
  - 影响面现算：全表 197 条中只有 1 条（B60）走到这条路径（其余 `out_of_scope` 或缺
    code/target 被跳过），但它就是唯一的 canary ⇒ 必须修。
  - **修法选择**：不在 resolver 里再跑一次 `resolve_sheet_wp_code`（那会造**第二套**
    「哪个码是对的」判定，与 `_wp_sheet_code_resolution.py` 的「必须只有一份」直接冲突 ——
    历史事故就是两侧协商出不同 wp_code）。改为调用方传**候选码集合** `source_wp_codes=`，
    判定仍只有一份。
  - 守卫 4 条：①按真实端点方式传候选集 ⇒ 命中；②只传底稿原码 ⇒ 也命中（向后兼容）；
    ③候选集里没有的码 ⇒ **不许**命中（不能见谁都放行）；④**AST 检查端点真的传了**
    `source_wp_codes=`（文本匹配会被注释骗过，memory ㉖）。
  - 另加 1 条**fail-closed 反向判据**：只给单个码、不给候选集 ⇒ 必须不命中。它钉的是
    「resolver 不许自己猜还有哪些码可能对」—— 将来若有人为让用例过而加猜测，这条打红。
  - 修复后真库实测：端点返回 200 且
    `binding_id` / `entry_id=xlsx/b60/gt-b60-bundle` / `target_sheet=B60` /
    `mapping_kind=exact` / `source_wp_code=B60-1` **全部命中**（此前全为 null）。
    下游 `error_code=current_representation_missing` 是真实业务状态（见 3.3）。
  - _R: 1, 3_
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
- [x] 3.2 为 `WorkpaperSyncEditorHost` 增加 target sheet / whole workbook descriptor 接线；不得在业务 composable 自己调 materialize 或拼 callback URL。
  - 现算缺口：`WorkpaperSyncEditorHost.vue` 里 `target_sheet` / `whole_workbook` / `document_scope` 出现次数**全是 0**；`buildDocEditorConfig` 只把 `descriptor.onlyofficeConfig` 原样克隆 ⇒ room 协议打开**永远停在首 sheet**，单 sheet 视图语义无处表达。
  - 三处改动：①`workpaperSyncDto.ts` 增 `targetSheet: string | null` / `documentScope: 'single_sheet' | 'whole_workbook'` + mapper（未知 scope fail-closed `descriptor_document_scope_unknown`，带人话 message）；②`buildDocEditorConfig` 按 `documentScope === 'single_sheet' && targetSheet` 注入 `editorConfig.actionLink = { action: { type: 'bookmark', data: targetSheet } }`；③新登记失败码 `editor_host_config_editor_missing`（缺 editorConfig 段时拒绝，不静默补半截 config）。
  - **为什么注入只能在消费侧**：服务端 `_onlyoffice_config` **刻意不含** actionLink（避免与 descriptor 生命周期绑死），而 Property 11 禁止前端再请求 config ⇒ 「把 target sheet 变成 actionLink」只能发生在消费 descriptor 的那一层。它不产生第二份 config，只在既有结构上补一个键。
  - 两种视图**互斥**：`whole_workbook` 即便 `targetSheet` 有值也**不注入**（整册要显示全部 sheet tab，带定位会把其它 sheet 悄悄藏起来 —— Requirement 3.4 禁止的形态）；服务端若已给 actionLink **不覆盖**（两份定位不一致时以服务端为准）。
  - 守卫：新建 `__tests__/workpaperSyncEditorHostRuntime.spec.ts`（该模块此前无专属 spec）9 例 —— single+target 注入 / target=null 不注入 / whole_workbook 不注入 / 不覆盖服务端值 / 缺 editorConfig 拒绝且码已登记 / 其它 config 段逐项保留 / 返回纯对象（OO 可写 `document.token`）/ 码表登记；`workpaperSyncDto.spec.ts` 补 5 例视图身份解析。前端 `src/components/workpaper/sync` **59 files 全绿**。
  - 变异 **4/4 全打红**（逐字节恢复核对一致）：M1 去掉注入（2 红）· M2 whole_workbook 也注入（1 红）· M3 覆盖服务端值（1 红）· M4 未知 scope 静默当 single_sheet（1 红）。
  - 🔴 **顺带修三处 2.1/2.4 遗留**（都是「后端改了、前端没跟」的同一类）：①`workpaperSyncDto.spec.ts` / `task69IndependentRegression.spec.ts` / `workpaperSyncApi.spec.ts` 的 descriptor fixture 缺 `target_sheet` / `document_scope`（2.4 把它们加进后端 `DESCRIPTOR_REQUIRED_FIELDS`，前端只跑了后端选集）⇒ 17 条红；②`resolve_entry_identity` 是 `prefixKind: 'sibling'`（`WP_SYNC_SIBLING_PREFIX_TEMPLATE`，**不含** entry_id）而 `buildSyncEndpointUrl` 只用 entry 前缀 ⇒ 该端点**从未有前端 client method**（「每条路由恰一个 client method」21 vs 22 红）—— 这正是 2.1 要解决的问题（「前端仍得先知道 entry_id」），端点建好却调不了等于没解决 ⇒ 补 `buildSyncSiblingPrefix` + `resolveEntryIdentity` + 登记；③通用 URL 判据原断言「每条路由都以 entry 前缀开头且含 entry_id」对 sibling 不成立 —— **判据本来就写错了**（sibling 存在的意义就是不含 entry_id）⇒ 按 `prefixKind` 分派，两种路由各有各的严格判据。
  - _R: 3, 4_
- [ ]* 3.3 迁移一个普通 single-sheet canary，从 `GtOnlyOfficeSheet` 切到 room host；记录 old URL、descriptor、target sheet 与 HTML 回读证据。
  - **阻断类别：真环境（浏览器取证）+ 真实用户操作**。canary 已选定并**已 migrated**：
    `xlsx/b60/gt-b60-bundle`（唯一 `exact`；`wp_code=B60-1`、`target_sheet=B60`；
    底稿 = 重药控股安徽有限公司_2025 / B60-1「审计项目工时预算与控制表」/ wp_id `afb9201a`）。
  - **服务端解析链已通（2026-11-16 真库实测）**：
    `GET /api/projects/{pid}/workpapers/{wp_id}/sync/entry-identity?sheet_name=B60` 返回 200
    且 `binding_id` / `entry_id=xlsx/b60/gt-b60-bundle` / `target_sheet=B60` /
    `mapping_kind=exact` / `source_wp_code=B60-1` **全部命中**。
  - **下一步阻断点（不是本次缺陷，是真业务状态）**：同响应的
    `error_code=current_representation_missing`，reason 文案「该底稿还没有已发布的在线编辑版本
    —— 请先在结构化视图里保存一次以发布首版」。根因现算：
    `working_paper_sync_entry_state` 里 **B60 有 0 行**（该表 85 行全有 rep），
    而 `working_paper_content_representation` 有 7 行历史数据（artifact `published` /
    bundle `approved` / sha 一致 / 文件在盘 23450 bytes）—— 但**没有任何 entry_state 指向它们**。
  - 为什么不能由我代做：「发布首版」是用户在结构化视图里保存一次产生的 entry_state，
    我伪造一条 entry_state 就是伪造「canary 已跑通」。
  - 四项取证（old URL / descriptor / target sheet / HTML 回读）**待 entry_state 就绪后**做。
  - 环境已就绪：`audit-onlyoffice` healthy / `audit-postgres` healthy。
  - _R: 3, 9, 10_
- [ ]* 3.4 迁移一个 whole-workbook canary；验证所有 sheet 可见、target sheet 正确、切回 HTML 不丢写。
  - **阻断类别：治理前置（binding 审核）**。现算：`whole_workbook` 10 条**全为 pending**，reason 全是 `whole_workbook_target_requires_reviewed_binding`（设计如此：整册映射必须人工确认 target 语义，不能由生成器自认）。
  - 候选：`xlsx/cash-flow-verification` · `xlsx/gt-a112-dual-checklist` · `xlsx/gt-a115-disclosure-checklist` · `xlsx/gt-a38-goodwill-impairment` · `xlsx/gt-b22-a-control-matrix`（另 5 条）。
  - 代码侧已就绪：3.2 的 `whole_workbook` 分支**明确不注入 actionLink**（整册要显示全部 sheet tab），且有守卫钉住「即便 targetSheet 有值也不注入」。
  - 下一步：用户裁决其中一条 → 迁移 → 验证「所有 sheet 可见 + 切回 HTML 不丢写」。
  - _R: 3, 9_
- [ ]* 3.5 迁移一个聚合 source sheet；验证映射到子 entry，不回退父级模板。
  - **阻断类别：治理前置（binding 审核）**。现算：`provider` 173 条全 pending，reason 全为 `runtime_sheet_name_requires_provider_binding`（sheet 名由运行时表达式决定 ⇒ 必须人工确认 resolver 身份可信）。
  - 候选：`xlsx/d4/analysis/d4-tab-*`（D4 聚合的 4 张 source sheet）· `xlsx/b60/gt-b60-docx-pane`。
  - 「不回退父级模板」的守卫**已就绪**：`test_sheet_open_bindings.py` 的父级兜底断言（每条 binding 的 `entry_id` / `effective_entry_id` 都必须逐字在 manifest 里）—— 一旦回退到父级模板，那条断言就打红。
  - 下一步：用户裁决一条 provider binding → 迁移 → 验证映射到子 entry。
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

- [ ]* 4.1 将全局 legacy 开关收敛为 binding 级状态机：pending → ready → migrated → draining → retired。
  - **阻断类别：治理前置（真实 drain 周期）**。已有 1 条 `migrated`（B60），状态机**代码已就绪**：`backend/app/routers/_wp_onlyoffice_legacy_url_gate.py` 按 binding 级判定，`test_sheet_legacy_gate_binding_states.py` 17 例覆盖五态 + 非法跃迁。
  - 为什么不能标完成：后三态（`migrated → draining → retired`）需要真实有 binding 走过才能证明。现算 `migrated` = **1 条**（B60，仅单 sheet）⇒ 后三态在生产上仍从未被真实触达（空分母恒真）。
  - 下一步：随 3.3（首条 binding 进 `migrated` 后，draining / retired 才有对象可验）。
  - _R: 6, 8_
- [ ]* 4.2 新增旧 doc key / callback drain ledger：记录签发时间、TTL、binding、entry、generation、终结状态。
  - **阻断类别：治理前置**。ledger **读取侧已就绪**（gate 按 binding 状态判定；`workpaper_sync_legacy_onlyoffice_callers.json` 记录 22 文件 / 27 处调用逐条 owner+reason）。
  - 缺**写入侧有数据**：B60 虽已 migrated 但从未签发过旧 doc key（entry_state 缺失，打开都没发生）⇒ 「旧 doc key 已签发待 drain」记录仍恒空。
  - 下一步：随 3.3。
  - _R: 6, 7, 8_
- [ ]* 4.3 migrated binding 的新请求不得签旧 URL；draining 只接受已签发且 scope / token / generation 全匹配的 callback。
  - **阻断类别：治理前置**。「不得签旧 URL」判据已就绪（`test_sheet_legacy_gate_binding_states.py` 的 `migrated` 分支 + 3.7 ledger 双向相等）；`draining` 的 scope / token / generation 三匹配也已在 gate 实现。
  - 缺的仍是**真实 drain 过程**（B60 打开都要先补 entry_state，见 3.3）。
  - 下一步：随 3.3。
  - _R: 6, 7_
- [ ]* 4.4 旧 direct-write 分支按 binding 逐个删除；删除前守卫要求旧签发数、callback in-flight、drain timeout 连续为 0。
  - **阻断类别：治理前置 + 时间**。「连续为 0」需要**真实运行一段时间的观测数据**；当前 1 条 migrated 但从未打开过 ⇒ 三个计数天然为 0 但**没有观测意义**（空分母恒真）。
  - 下一步：3.3 完成 → 观察一个完整 drain 周期 → 才能按 binding 逐个删。
  - _R: 2, 6, 10_
- [ ]* 4.5 删除无调用方的 `GtOnlyOfficeSheet` 兼容代码前，完成 grep 0 调用、测试全绿、独立提交与回滚标签；single/custom/Word 豁免必须有真实条件断言。
  - **阻断类别：治理前置**。现算 `GtOnlyOfficeSheet` **仍有调用方**（196 条未迁移 entry 都靠它）：它是 `pending` / `out_of_scope` / custom / Word / single_onlyoffice 的**唯一载体**（197 条 binding 里仅 1 条 migrated）⇒ 现在删会让全部未迁移入口失去在线编辑能力。
  - 这正是 3.6 加「独立在线编辑（不同步）」提示条的原因：它现在是**有正当职责**的组件，不是遗留垃圾。
  - 下一步：等 4.4 逐 binding 删完后，调用方才会自然降到 0。
  - _R: 4, 5, 6_

## Phase 5：测试与真实验收

- [x] 5.1 后端 unit / contract：mapping 唯一性、scope、target sheet、current representation、candidate 拒绝、path boundary、typed error。
  - 先做覆盖度审计：7 类判据**全部已有覆盖**，但分散在 6 个文件里 ⇒ 某类被删时没有任何东西会发现。
  - `test_sheet_open_unit_contract.py` 提供两样：①**判据清单守卫** `JUDGEMENT_COVERAGE`（7 类 → 具体文件::函数名，逐条查函数定义存在；清单腐化/改名即红）②**补真实缺口** —— `path boundary` 此前只有关键词命中而无真测试，补 6 条（跨项目 / 跨底稿 / 路径逃逸 / 不回退模板 / project_id 必须传请求值 / kind+state 必须在调 resolver 前校验）。
  - 18 例守卫；变异 6/6 全精确打红零假红。
  - 🔴 三处承重点不承重（都是「夹具与判据不匹配」）：
    1. `_RejectingArtifacts` **无条件拒绝** ⇒ 「project_id 传错」观察不到（两种实现都拒）⇒ 补 `_RecordingArtifacts` 按参数校验。
    2. `candidate` 分支在 `kind`/`state` 校验**之前**独立拦截 ⇒ 把校验改成 `if False:` 后 candidate 用例仍绿（M3 存活）⇒ 补「非 candidate 的非 published 态」（`superseded`/`incoming`/`draft`）与「非 canonical kind」两组。
    3. `_fake_rows` 的 artifact **没有 `project_id`** 字段 ⇒ `getattr(..., project_id)` 回落到请求值 ⇒ 语义等价 ⇒ M2 存活 ⇒ 给 artifact 加一个**不同的** `project_id`。
  - _R: 1, 2, 7_
- [ ]* 5.2 后端 PG：真实 `WorkpaperContentRepresentation`、bundle、artifact 读取与项目隔离；只读验证先独立事务，写入验收只用【测试】项目并可恢复。
  - **阻断类别：治理前置**。`audit-postgres` healthy（环境可用）。B60 有 7 行 representation（artifact published / 文件在盘），但**无 entry_state 指向** ⇒ 端到端读取仍会在 `current_representation_missing` 停下。
  - 代码侧已就绪：`read_current_published_sheet_artifact`（11 条 `PUBLISHED_SHEET_ARTIFACT_REASONS`）+ 12 例守卫；项目隔离在 gate 层。
  - unit / contract 层已用合成夹具覆盖同一批判据（`test_sheet_published_artifact.py` 12 例）；PG 层要验的是**真实 schema / 真实 bundle 形状**，两者不能互相替代。
  - 下一步：随 3.3。
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
- [ ]* 5.5 Playwright：普通 sheet / whole workbook / 聚合 source sheet / pending fallback / drain 五条 required scenarios；记录网络、console、页面错误、数据快照与 artifact identity。
  - **阻断类别：治理前置（4/5 场景）+ 真环境**。逐场景现算：
    - 「普通 sheet」/「whole workbook」/「聚合 source sheet」→ 各需一条 **migrated binding**（当前 0 条）；
    - 「drain」→ 需 4.2 的 drain ledger 有真实记录（当前恒空）；
    - 「pending fallback」→ **本场景代码已就绪且可单测**（3.6 的「独立在线编辑（不同步）」提示条 + 12 例守卫），但 Playwright 层仍要真浏览器 + 真 OO 容器跑一次取证。
  - 环境已就绪：`audit-onlyoffice` healthy / `audit-postgres` healthy / `audit-redis` healthy。
  - 为什么不能用现有单测替代：Playwright 层要验的是**真实 OO iframe 内的 sheet tab 可见性与 actionLink 定位效果** —— 这是 3.2 注入的 `editorConfig.actionLink` 唯一能被证明有效的层级（单测只能证明「config 里那个键被写进去了」）。
  - 下一步：3.3 完成 → 五场景可逐条跑。
  - _R: 3, 4, 6, 9, 10_
- [x] 5.6 clean checkout：生成物 `--check`、后端测试、前端定向测试、构建、路由注册、行数门与 git tracked 交付物检查。
  - `backend/scripts/check/check_sheet_open_clean_checkout.py`：**可重复执行的单一入口**（`--skip-tests` 只跑静态项）。7 项检查：①三个生成器 `--check` ②23 个交付物 `git ls-files` 跟踪 ③`entry-identity` 挂在**真实 `app.routes`**（不只查模块级 router —— 本仓踩过「router 存在但没注册」）④**变异残留**（11 类精确靶点 × 8 个生产文件）⑤后端守卫选集 ⑥前端定向测试 ⑦行数门。
  - 实测 **7/7 全过**：后端 116 passed / 1 skipped，前端 37 passed。
  - 🔴 **本轮最重要的发现**：5.3 的变异 M4 残留（`if (value !== undefined && value !== null) return 'pending'`）**从未被恢复** —— 它让 3 条前端用例一直红，而我在 3.1/3.6 期间看到「15 passed」是**误读输出**（`Select-Object -Last N` 截到了别的行）。根因：变异脚本的 `finally` 会被 Ctrl+C 绕过（本轮终端多次显示 `^C`）。
    - 修复：删掉残留 + 把「变异残留检查」**固化进 5.6 总验**（独立于变异脚本，始终执行，不受 `--skip-tests` 影响）。
    - 判据设计：只列「注入后**不可能**是任何人手写」的形态（如 `(lambda **k: None)(`），且**只扫生产代码**（测试文件里提到变异形态是正当的 —— 首版全扫 `DELIVERABLES` 产生 4 处误报）。
  - 🔴 另两处修复：①路由探测的 JSON 解析被 `app.main` 导入时的 JWT 弱密钥**警告**干扰（取最后一行拿到的是警告）⇒ 改为找第一个以 `[` 开头的行；②probe 脚本放仓库根而 `app` 包在 `backend/` 下 ⇒ 显式设 `PYTHONPATH`（不靠 `cwd`）。
  - _R: 8, 10_
- [ ] 5.7 更新 umbrella 2.8 的余项状态、INDEX、memory 与归档证据；只有完成门满足后归档本 spec。
  - **阻断类别：治理收尾（依赖完成门）**。本 spec 的完成门 = 34/34 全勾；当前 22/34（3.2 本轮完成），余 12 项全部依赖上面的治理前置 / 人的裁决 / 真环境。
  - 不归档的理由：归档会让「还有 12 项没做」这件事失去可见性。按 memory 铁律「归档新判据 = HEAD 干净检出跑守卫」，且 `INDEX.md` 的 Active 表要现扫。
  - 下一步：0.4 签字 + 3.3 首条 binding 迁移后，逐项收口再归档。
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
