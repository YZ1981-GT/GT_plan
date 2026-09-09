# Requirements Document

## 总控 G1-1 执行约束

本工作包仅统一 projection Excel 发布结构摘要：HTML materialize、OO rematerialize、rollback 必须从各自冻结 bundle 的 approved instrumentation child 读取并校验 payload，传入完整 anchors；缺 contract/anchors 必须拒绝，不回退 adapter 摘要。finalize 必须从最终 staged candidate bytes 调用共享计算器，禁止复制摘要公式。Word 保留独立结构摘要，custom/opaque 保留权威 bytes 摘要。测试必须覆盖最终 artifact 同值、拒绝路径及三个宿主实际传参，并以变异反证校验。禁止写业务库、rehash --apply、暂存或提交；本包不代表生产双向验收或 G1-2 迁移完成。


## Introduction

本 spec 收口底稿模块 HTML（结构化视图）与 OnlyOffice（以下简称 OO）Excel/Word 的真实双向回写。目标不是让 184 个生产宿主继续各自维护一套“切模式”逻辑，而是建立平台同步内核、显式 adapter 契约和可审计的版本/冲突协议，再按入口清册逐一迁移。

只读调查与 Wave 0 生成器的当前基线（仅作本次修订背景，运行时仍以机器清册为准）：

- 当前生成事实为 185 个物理宿主、276 个挂载点、1 个 dispatcher、186 个 manifest entry；其中 142 个独立入口、43 个父级重复入口、1 个不可达旧桩、136 个尚未完成业务裁决。
- 入口、独立数据通道、重复关系和裁决状态均由 source-backed manifest 生成；本文不得把上述数字复制为生产判断。
- 当前逐 entry 红基线识别出 142 个 template-only、13 个 reload-only、142 个无后端 forcesave、142 个无 durable ack、142 个缺 adapter，以及 132 个 single capability 仍显示切换 UI。
- 当前真正闭环仍只有两类：`custom`（xlsx 本体单一权威）与 F2-22/F2-23（已有专用 to/from OO 端点，但仍缺 durable forcesave ack、三方冲突、canonical 重物化与 Word 自由正文隔离）。
- 多数入口当前只是 HTML 保存数据库、OO 打开模板副本、切回后重读原数据库；这类行为必须保持红基线，不得继续以双模式成功态呈现。

本 spec 的完成定义是：所有入口均出现在可执行 manifest 中；每个独立入口要么完成真双向 adapter，要么被明确裁决为 `single_html` / `single_onlyoffice`，界面不得继续展示假双向；所有真双向入口均通过 HTML→OO、OO→HTML、并行合并、同字段冲突、幂等重试、回滚和真实 OO 9.4 浏览器验收。

### Glossary

- **真双向回写**：HTML 的已提交修改可 materialize 到 canonical OO 文件；OO 的 durable 保存可解析、三方合并并提交到 HTML 权威结构；两方向均有版本、冲突和失败可见性。
- **模式切换**：用户从结构化视图切到 OO，或从 OO 切回结构化视图。模式切换本身不是同步完成凭证。
- **canonical OO artifact**：某个 content version 指向的不可变 OOXML 产物；config、download、callback、extract、rollback 均通过同一 resolver 解析，current 只是一条数据库指针。
- **content revision**：只因底稿业务内容变化而递增的单调版本。所有 HTML、上传、WOPI、OO、回滚 writer 必须经统一 content mutation 入口；纯模板、instrumentation、contract 或 OOXML representation 升级不得递增它，也不得使用 `updated_at`、mtime、`parsed_data._version` 或复核状态代替。
- **immutable content version**：不可原地覆盖的业务内容版本，记录父版本、权威 projection/自有文件哈希、来源和创建者；它与 OOXML representation 是一对多，不把隐藏结构升级伪装成业务内容变化。
- **representation generation**：某 content version 在特定 entry、authoritative model 与 immutable definition bundle 下生成的不可变 Excel/Word artifact；可因隐形载体升级产生新 generation，但不得修改旧 artifact 或推进 content revision。
- **immutable definition artifact**：template、instrumentation manifest、adapter contract 或 authoritative model 的内容寻址快照；operation、representation、retry 与 evidence 均以 FK + SHA-256 固定到不可变快照，不只保存可漂移的版本字符串。
- **authoritative model immutable definition**：声明 entry 的权威内容模型及允许的 projection/OOXML 写入语义的不可变 definition artifact；至少区分 `projection_contract / custom_authoritative_ooxml / opaque_single_onlyoffice`，不得用 contract 是否为空隐式推断。
- **immutable definition bundle**：按 `schema_version + authority_model_definition_digest + template/instrumentation/contract` 三类 typed canonical slots 生成的内容寻址定义包。每个 slot 必须出现；可选 child 只能使用版本化 typed null marker（例如 `instrumentation:none:v1`、`contract:none:v1`），字段缺失、空串、全零 hash 或 SQL NULL 均不得进入 canonical bytes。bundle digest 永远非空，历史 operation 不随 alias 漂移。
- **representation upgrade candidate**：upgrader 在 per-entry contract 与 approved bundle 就绪前生成的 non-current staged 候选；resolver、room、current pointer 与 evidence 均不得使用，只有发布 DAG 完成并通过校验后才能 finalize 为 immutable representation。
- **OO room**：同一 `wp_id + entry_id + generation` 的共享编辑房间，绑定 `doc_key`、opened base、服务端 last-applied 与客户端 confirmed base，不绑定单一用户。
- **OO participant lease**：某用户进入 room 的授权快照，绑定 `user_id / permission_epoch / mode / expires_at / revoked_at`。用户发起 forcesave 时按自身 lease 鉴权；聚合 OO callback 则按 room/generation route 鉴权，不能假定整个文件只由某个 participant 贡献。
- **opened base / last-applied / client-confirmed base**：分别表示 room 打开时业务版本、服务器最近成功应用的 canonical 版本、当前活跃 OO 编辑器已实际加载并确认的 merge 基线。只有结果投影与客户端 incoming 等值或编辑器重载确认后，client-confirmed base 才可推进。
- **forcesave request**：调用 Command Service 或进入 clean-close 前持久化的不可变请求快照，冻结 `request_id / generation / request_sequence / client_confirmed_base / immutable definition bundle / write-fence / initiator`；callback 不得读取到达时可变的 room 指针来构造 application identity。
- **durable ack**：Command Service 接受 forcesave 后，status=6/2 callback 的 incoming artifact 已耐久化，并已绑定可恢复 operation 或在无法安全归组时绑定 recovery case；它不等于结构化内容已应用。
- **callback delivery**：一次 OO 文档级 callback 传输记录；可因 status=6、status=2 或网络重试出现多次，并可记录多个贡献者，但 route participant 不是内容唯一作者或应用授权主体。
- **content application**：`working_paper_content_application` 表示某个 durable incoming 对业务状态的一次独立、不可变逻辑应用，唯一持有 `application_key`、frozen base/representation/bundle/authority model/incoming identity 与逻辑结果；它只在 incoming 已耐久且 correlation 成立后创建或命中，同一 frozen identity 最多产生一个 applied revision。
- **sync operation**：面向用户轮询与 append-only timeline 的执行容器。正常 forcesave 在 Command Service 前可创建 `application_id=NULL` 的 operation shell；durable correlation 事务结束时，shell 必须二选一收敛为绑定 application 的唯一 primary，或保持 `application_id=NULL` 并以 terminal `duplicate` 直指 canonical primary。recovery case 在 claim 成功前不得存在 operation，claim 事务结束时同样必须收敛为 primary 或 direct terminal duplicate。operation 不持有 application key，状态至少含 `received / downloading / durable / validating / extracting / merging / conflict / refresh_required / rematerializing / applying / applied / duplicate / error / superseded`。
- **staged artifact publish**：先在项目存储中写入并校验不可变 staged artifact，再用短数据库事务写 content version/representation/current pointer/outbox；事务失败只留下不可见 orphan，由 GC 清理，不宣称文件系统与 PostgreSQL ACID 同事务。
- **adapter contract**：某 wp/sheet 的显式业务字段映射；包含稳定字段键、JSON Pointer、OO 身份锚点、行/列身份、公式/只读策略及 template/instrumentation immutable artifact identity。
- **template instrumentation**：对平台自有 Excel/DOCX 权威模板做受控、版本化的隐形契约增强，例如 `_GT_SYNC` metadata、defined name、稳定 row UUID 或 tagged SDT；不得改变未经批准的可见业务语义，升级结果必须形成新的 representation generation。
- **canonical rematerialization**：merge/resolve 得到 merged projection 后，以 incoming artifact 为基底重写受管区域，再反读等值并发布新的 canonical artifact，确保 HTML 与 OO 不分叉。
- **base/current/incoming**：会话打开时基线、当前服务器权威值、OO 回传值；标准底稿一律三方合并，禁止 last-write-wins。
- **stable row key**：动态行稳定身份；用户新增行使用 UUID，模板行使用契约键，不得使用数组下标或可改 label。
- **SDT**：DOCX structured document tag/content control。Word 结构化岛必须带稳定 `w:tag`；重复行还需 `row_uuid`。
- **结构化岛**：Word 中参与 HTML 投影的 SDT 区域；SDT 外自由正文只属于 Word，不反向覆盖 HTML 字段。
- **入口 manifest**：覆盖全部宿主/挂载点/独立数据入口的机器清册，记录文档类型、持久化通道、adapter、迁移态和验收证据。

---

## Requirements

### Requirement 1: 全量入口清册与诚实能力标识

**User Story:** 作为审计师，我要界面准确告诉我当前底稿是否真的支持双向回写，不能把“仅能打开 OO”伪装成双向同步。

#### Acceptance Criteria

1.1. 系统 SHALL 从生产源码与 adapter registry 生成入口 manifest，覆盖全部 `GtOnlyOfficeSheet`、`OnlyOfficeWordDialog`、`WorkpaperWordEditor` 挂载点及其父组件转发关系。
1.2. manifest 每条 SHALL 包含稳定 `entry_id`、宿主路径、wp/sheet 匹配规则、文档类型、HTML 持久化通道、OO canonical resolver、adapter id、能力态、验收态，以及 source-backed 的 `editable / room_model / scenario_profile`。后三者 SHALL 由生成器按宿主、descriptor 与 registry 事实确定并进入 manifest digest，不得由自由文本、可漂移布尔或人工豁免决定 required scenarios。
1.3. 能力态 SHALL 限定为 `bidirectional / single_html / single_onlyoffice / unreachable`，不得使用含糊的 `dual` 布尔值。
1.4. WHEN 入口未注册 adapter 或 adapter 未通过契约校验 THEN 前端 SHALL 禁止显示“可双向回写”，并显示可操作原因。
1.5. WHEN 入口被裁决为纯 OO 或纯 HTML THEN 系统 SHALL 只显示真实可用模式，不显示不可兑现的切换按钮。
1.6. 43 个父组件重复入口 SHALL 指向其独立数据入口，不得被重复计算为已迁移 adapter。
1.7. 不可达旧桩 SHALL 删除；不得以豁免或 `DEPRECATED` 注释长期保留。
1.8. manifest 的未裁决、未迁移、未验收条目数 SHALL 只许下降；新增入口未登记时 CI SHALL 打红。

### Requirement 2: 统一内容版本域、共享 OO room 与单一 canonical 指针

**User Story:** 作为维护者，我要所有内容 writer 使用同一 revision 协议，多人协同共享房间但各自保有授权租约，旧会话不能覆盖新内容。

#### Acceptance Criteria

2.1. 标准底稿 SHALL 使用独立单调 `content_revision`；它只因业务 projection 或 custom 权威文件内容变化递增。纯 template/instrumentation/contract/authority-model/bundle/representation generation 变化以及 `parsed_data._version`、`working_paper.file_version`、`updated_at`、文件 mtime 均不得推进或充当跨通道同步版本。
2.2. HTML save、导入上传、WOPI、OnlyOffice、冲突裁决与 rollback SHALL 通过统一 `ContentMutationService.commit(...)` 或等价唯一入口提交业务内容；任何绕过入口的 writer SHALL 被清册与 CI 阻断。
2.3. 每个已应用业务内容变更 SHALL 产生 immutable content version，至少记录 `wp_id / revision / parent_version / projection_or_authoritative_artifact_sha256 / source / actor / operation_id / created_at`；其 OOXML SHALL 由独立 immutable representation row 绑定 `entry_id / representation_generation / artifact_sha256 / adapter build / definition_bundle_id / definition_bundle_sha256`，不得只保存可漂移版本字符串或就地改旧 version。每个 bundle SHALL 引用 approved authoritative model definition，并以非空 typed slots 固定 template/instrumentation/contract child identity；`projection_contract` 标准入口的 template、instrumentation 与 per-entry contract child 必须全部为 approved 非空 artifact，`custom_authoritative_ooxml / opaque_single_onlyoffice` 则必须使用明确 authority model 与适用 child 的版本化 typed null marker，不得以 SQL NULL、空串或全零 hash 代替。
2.4. 文件系统与 PostgreSQL SHALL 使用 staged artifact 协议：artifact 先耐久校验，随后在一个短数据库事务内写 content version、representation、`content_revision`、current pointer 与 outbox；事务失败的 artifact 不可见并由 orphan GC 清理。
2.5. OO room SHALL 绑定 `wp_id / entry_id / doc_key / generation / opened_base_version_id / last_applied_version_id / client_confirmed_base_version_id / client_confirmed_representation_id / client_confirmed_definition_bundle_id+sha256 / latest_request_sequence / latest_durable_sequence / write_fence_epoch / close_barrier_epoch / close_leader_intent_id / state / expires_at`，不得用一个 `last_ack` 同时表示服务器已应用值与编辑器实际持有值，也不得保存单一 `user_id/mode/permission_epoch` 代表全房间。
2.6. 每位协同用户 SHALL 通过独立 participant lease 进入 room，lease 记录 `user_id / permission_epoch / mode / state / expires_at / revoked_at`；同 room 用户的 forcesave 发起权限逐人校验。创建 close intent 时，服务端 SHALL 在 room row lock 内把该 participant 从 `active` 原子转为 `closing`，且 `closing` 不再计入 active confirmed editor 仲裁集合。OO callback 作为聚合文档事件 SHALL 使用 room/generation/doc_key route credential，并单独记录 initiator、route participant 与 contributor set，三者不得混同。
2.7. `doc_key` SHALL 由稳定 room 身份与 generation 派生；不得继续由 `wp_code + mtime_ns` 生成。
2.8. 同一 generation 的协同用户 SHALL 可进入同一 active room；发布新 generation SHALL 显式 supersede 旧 room。WHEN 任一写 participant 撤销/过期且 OO 不能证明已从聚合文档安全踢出 THEN 系统 SHALL 旋转 generation 并要求其余有效用户重开，不得继续接收可能含被撤销贡献的旧 generation artifact。
2.9. 每次 content application 成功后 SHALL 原子推进 room 的 `last_applied_version_id`；仅当 result managed projection 与客户端 incoming 等值且 definition identity 未变，或编辑器显式重载并确认新 descriptor 时，才可推进 `client_confirmed_base_version_id`。WHEN merged result 与 incoming 不等值 THEN room SHALL 进入 `refresh_required` 并拒绝下一次 forcesave/application，直至 supersede/reopen 确认新基线。
2.10. config、WOPI/download、callback、materialize、extract、rematerialize、retry、rollback 与 evidence SHALL 通过同一 canonical resolver 返回相同 content version/representation/artifact、非空 immutable definition bundle 与 authoritative model identity；历史读取不得按当前 registry alias 重组 bundle。
2.11. custom 底稿 SHALL 保持 xlsx 本体单一权威，不得被标准结构化底稿的 JSON projection writer 改写；但其版本、representation、room、callback 和 evidence 仍须进入统一协议。
2.12. `WorkpaperSaveOrchestrator.after_save()` 等副作用 SHALL 由提交后可重放 handler 执行；handler 重试不得再次递增 content revision。

### Requirement 3: HTML → OO 的阻断式 materialize 协议

**User Story:** 作为审计师，我从 HTML 切到 OO 时，要看到刚提交且已形成 canonical artifact 的结构化内容，而不是旧模板或旧文件。

#### Acceptance Criteria

3.1. 对 bidirectional 标准底稿，HTML→OO SHALL 依次执行：flush pending 编辑并创建服务端 `pending_mutation` → 在一次 `ContentMutationService.commit(...)` 中消费它，完成 expected revision 校验、业务 projection 与兼容 canonical representation 的 staging/反读/发布 → 创建或复用 room/participant → 返回 launch descriptor。pending mutation SHALL 绑定 `project/wp/entry/sheet/user/expected_revision/payload_digest`，具有短 TTL、单次逻辑消费和 Idempotency-Key；commit/operation SHALL 冻结 approved immutable definition bundle，失败重试继续使用同一 bundle identity。失败重试返回同 operation，成功后重放返回既有结果，不得先提交 projection-only revision再补 artifact。
3.2. WHEN HTML flush 或该唯一 content commit 未得到服务端成功响应 THEN 模式切换 SHALL 停留在 HTML，且 room 创建和编辑器挂载调用次数均为 0；已产生的不可见 staged artifact 只可进入 orphan 流程。
3.3. WHEN adapter 不存在、immutable definition bundle 不存在/未 approved、authoritative model 不匹配、任一 typed slot 缺失或使用非法空值、template/instrumentation/per-entry contract identity 不兼容，或 representation 生成失败 THEN 模式切换 SHALL 被阻断并显示首个可操作原因。`projection_contract` entry 缺任一 approved child 时不得降级为 contract-less 模式。
3.4. representation 生成 SHALL 写入项目内 staged immutable artifact，完成 OOXML、sheet/DOCX 结构、安全、bundle compatibility 和 adapter 反读校验后，才允许数据库 pointer 指向它；upgrader 在 approved per-entry contract/bundle 之前只能写 non-current representation upgrade candidate，resolver、room 与 current pointer 不得读取 candidate；不得直接覆盖 current artifact 或修改既有 content version/representation row。
3.5. materialize SHALL 只写 adapter 声明的受管字段，保留模板公式、样式、合并单元格、图片、图表、宏策略允许的部件及未管理区域。
3.6. WHEN business projection、immutable definition bundle 与 canonical substrate identity 均相同 THEN materialize SHALL 幂等复用现有 content version/representation/room，不产生重复 content revision 或 representation。WHEN 仅 template/instrumentation/contract/bundle 隐形结构升级且业务 projection 不变 THEN SHALL 按 `template → instrumentation → contract → bundle → representation` 完成批准与 finalize，创建新 representation generation，但 content revision 保持不变；candidate、unapproved bundle 或 projection-based 缺 contract bundle 均不得 published/current。
3.7. 前端 SHALL 仅在服务端返回唯一 `EditorLaunchDescriptor`，且其中具备 `room_id / participant_id / doc_key / server_applied_revision / client_confirmed_base_revision / representation_id / representation_generation / artifact_sha256 / authority_model / definition_bundle_id / definition_bundle_sha256 / write_fence_epoch / config` 后挂载 OO 编辑器。DocEditor `onDocumentReady` 后 SHALL 调用幂等 descriptor-confirm API，逐项回传并校验上述 identity；确认前 room 不得 active、participant 不得发起 forcesave，陈旧 generation/representation/bundle/fence SHALL 被拒绝。
3.8. HTML→OO 任一失败 SHALL 产生终态明确的 operation 与 transition events，不得用 warning 后继续打开旧文件。
3.9. single_html entry SHALL 不创建空白 OO artifact；single_onlyoffice/custom entry SHALL 按各自权威模型返回 descriptor，不伪造结构化 projection。

### Requirement 4: OO → HTML 的 forcesave、callback 生命周期与 durable ack

**User Story:** 作为审计师，我从 OO 切回 HTML 时，要等 OO 文件已耐久、内容已应用或冲突已建立后再离开，不能只重载原数据库。

#### Acceptance Criteria

4.1. OO→HTML SHALL 先在一个数据库事务中持久化冻结 `client_confirmed_base / request_sequence / immutable definition bundle id+digest / authority model / write_fence / initiator` 的 forcesave request，并创建供用户轮询的 operation shell（`application_id=NULL`），再由后端调用 OnlyOffice Command Service `forcesave`。forcesave `Idempotency-Key` 的唯一范围 SHALL 固定为 `(room_id,generation,initiated_by_participant_id,kind,idempotency_key)`，request 另存 canonical frozen request fingerprint；只有 initiator、kind、confirmation、base/representation、bundle、fence 与 contributor digest 全部相同的重放才可返回原 request/operation，任一不等 SHALL 返回 409 且不得返回旧标识。accepted 响应可返回该 operation id，但不得预建 application 或 application key。只有 incoming durable 且 request-first correlation 成立后，系统才可创建或命中 content application：最先赢得 application key 的 shell 成为唯一 primary并原子绑定；application 不可变保存 `origin_request_sequence`，并在同 key 的较高 sequence request 命中时原子执行 `effective_request_sequence=max(existing,request_sequence)`，同时把 room latest-durable fence 指向该 canonical application/effective sequence。不同 request 的后续 shell SHALL 保持 `application_id=NULL`、原子写 terminal `duplicate` event 与直指 primary 的 `duplicate_of_operation_id`，不得形成链/环或 stranded `waiting_application`；同 canonical application 的 sequence fold 不得 supersede 自己，只有较新且 canonical application 不同的 durable full snapshot 才可 supersede 旧 application。operation GET/冲突/timeline/retry/resolve SHALL 在重新校验 duplicate 自身显式 scope与当前权限后跟随 canonical primary 的 application/result，且不得新建 application/operation。recovery case 仍遵循 Requirement 5.8，claim 前不得存在 request/application/operation。不得把 `customization.forcesave=true` 或 Command Service HTTP 200 当成保存完成。
4.2. 前端 SHALL await 服务端 operation；仅当时序满足 `forcesave request frozen < command accepted < incoming durable < applied/conflict/refresh_required terminal < reload` 后方可离开 OO。
4.3. status=6 强制保存、status=2 最终保存及其网络重试 SHALL 各自留下 callback delivery 证据。callback 含 `userdata/request_id` 时 SHALL 先精确绑定并校验该 frozen request，再以其中非空 definition bundle identity 计算 application key；无 `userdata` 时只能按 Requirement 4.10 的确定性规则归组。不得在读取 request 前仅凭 incoming hash 命中旧 application，从而绕过不同 frozen base、bundle、authority model、permission epoch 或 write fence；同一 frozen application 才能应用一次。
4.4. WHEN forcesave 请求失败、callback 未到达、operation 超时、无法唯一关联 status=2 或仍在 in-flight grace THEN 前端 SHALL 保持 OO 模式并允许重试，不得切回后只执行 `reloadAll`。
4.5. WHEN merge 结果为 `applied` THEN 前端 SHALL 按返回的新 `content_revision` 刷新 HTML，并校验实际加载 revision 不低于该值。
4.6. WHEN merge 结果为 `conflict` THEN 前端 SHALL 打开冲突预览，不得自动选 incoming 或 current。
4.7. WHEN room/participant 已 `superseded / revoked / expired`、generation write fence 已变化或 room 为 `refresh_required` THEN forcesave SHALL 在调用 Command Service 前被拒绝。participant 撤销 SHALL 先通过 OO 可验证 drop 将其移出，无法证明时必须 supersede generation 并要求其余用户重开。
4.8. 关闭、刷新或路由离开且 OO 有 dirty、forcesave accepted 或 waiting callback 状态时 SHALL 提示用户；不得在卸载时只销毁编辑器。
4.9. 系统 SHALL 为 status 1/2/3/4/6/7 等实际启用的 callback 状态、Command Service 返回、clean-close intent、`userdata` 缺失/重复、错误、timeout、TTL 与 in-flight grace 定义版本化真值表；未知状态或无法唯一归组 SHALL fail visible。
4.10. clean close SHALL 由已完成 descriptor confirmation 的 authenticated active edit participant 在销毁编辑器前创建 participant close intent。服务端 SHALL 在同一 room row lock 内把 participant 原子转为 `closing` 并排除出 active confirmed editor 集合，推进 room close barrier；当 active 数首次归零时，按最高 `(intent_sequence,id)` 和冻结的 eligibility snapshot 确定唯一 `close_leader_intent_id`，并阻止该 generation 新 editor 加入。非 leader closing participant 只执行普通 forcesave；`reconcile_close_intents()` SHALL 在 intent 创建、每个前置普通 forcesave terminal/superseded-safe、participant leave/error/revoke/expire 后重新持有 room lock。若 leader 在 promotion 前失去资格，reconciler 必须将其 intent append-only 记为 `authorization_stale`，推进 eligibility epoch，并在仍合法 intents 中按同一最高 `(intent_sequence,id)` 规则选择唯一 successor；相同 eligibility snapshot 的重放不得换 leader。若存在 successor，仅当 active=0 且 barrier 内全部前置普通 forcesave 已安全终结时，才以 CAS 将该 leader exactly-once 提升为 generation 内唯一 open frozen close-capture request，冻结非空 initiator、permission epoch 与 definition bundle。若不存在合法 successor，系统 SHALL supersede generation，把 intents/room 终结为显式 `authorization_stale/recovery_required`，保留既有 durable incoming/application 并要求重新授权的用户从新 generation 恢复；不得永久 `retryable_blocked`、静默关闭或以 system/route identity 冒充用户。leader 已 promotion 后授权失效不得再创建第二 capture，只能由最终授权 fence 将该 request/application 置 `authorization_stale` 并进入同一 supersede/recovery 路径。partial unique constraint 只证明 at-most-one；单用户、两个 participant 两种关闭顺序以及“A 的普通 forcesave terminal 前/后 B close”的合法资格行为测试 SHALL 证明最终 exactly-one，另以 leader revoke/expire 交错证明“合法 successor 时仍 exactly-one、无 successor 时零 capture但显式 recovery terminal”，两类都不得丢失 durable 内容或无限阻塞。status=2 无 `userdata` 时优先绑定该唯一 request；不存在 eligible request 时，才可去重到 frozen identity 唯一且无更高不同 canonical application 的同 incoming application。无 request、候选冲突或浏览器 crash SHALL 创建 durable recovery case 且 claim 前不得创建 operation；不得猜 base 或直接应用。
4.11. 每次成功 application SHALL 推进 `last_applied_version_id`；连续 forcesave 只能使用 forcesave request 冻结的 `client_confirmed_base_version_id`。WHEN merged projection 不等于 incoming projection THEN SHALL 返回 `refresh_required`、supersede/reopen 后再接受下一次 request，不得把服务器结果直接冒充客户端已确认基线。
4.12. durable ack SHALL 只证明 incoming artifact 可恢复；UI 必须分别显示“命令已接受”“文件已耐久”“结构化回写完成/冲突”“需重载编辑器确认新基线”。

### Requirement 5: callback 安全、双层幂等与失败语义

**User Story:** 作为平台管理员，我要网络重试、状态 6/2 乱序、恶意下载和解析失败都不会重复应用或覆盖好文件，且每一步可恢复、可审计。

#### Acceptance Criteria

5.1. callback SHALL 校验版本化 JWT claim schema、issuer/audience/action、room、doc_key、generation、callback route token 与 URL 绑定；它是 room/generation 级服务事件，不得把可选 `participant_id` 当作聚合 artifact 的唯一作者或唯一授权依据。缺失或未知 claim version SHALL 在下载前拒绝。
5.2. `verify_callback_preconditions` SHALL 接收真实 claim version；不得以 `claim_version=None`、默认用户、route participant 或 opened-time 权限绕过校验。
5.3. callback 下载 SHALL 使用 allowlist/签名代理、DNS 解析后地址复核、重定向限制、连接/读取超时与流式大小上限，防 SSRF、DNS rebinding 和内存整包读取。
5.4. 每次 callback delivery SHALL 由包含 `room_id / generation / callback_status / delivery discriminator` 的 delivery key 唯一记录，归属约束只以 immutable `durable_at`/durable fact 判定，不得把泛化 `terminal` 当 durable。`durable_at IS NULL` 的 `received/downloading/rejected/error` MAY 尚未归组并保持 application/recovery owner 均空（可保留已精确绑定的 request/operation shell），但任何阶段都不得双 owner；`durable_at IS NOT NULL` 的 `durable/acknowledged/unmatched/post-durable error` 必须恰属两类之一：correlated delivery 满足 `application_id IS NOT NULL AND callback_recovery_case_id IS NULL`，unmatched/ambiguous delivery 满足 `callback_recovery_case_id IS NOT NULL` 且 request/application/operation 全为空，post-durable error 保留其既有 owner。application ownership 与 recovery ownership SHALL 互斥，但不得错误地把 request 与 application 做 XOR；delivery 引用 primary operation 时 `operation.application_id=delivery.application_id`，引用 terminal duplicate operation 时该 operation 自身 `application_id` 为空、`duplicate_of_operation_id` 必须直指同 scope且 `application_id=delivery.application_id` 的 primary。不同 status 可有不同 delivery row；存在 `userdata/request_id` 时必须 request-first，status=2 无 userdata 只能按 Requirement 4.10 的唯一 close-capture/frozen-identity 规则归组。无法关联时必须建立可审计、可授权认领或 download-only 终结的 recovery case，禁止 durable incoming 成为无所有者死路。
5.5. `working_paper_content_application` SHALL 是 application key 的唯一 owner，并不可变保存 `wp_id / room_id / generation / frozen_client_base_version_id / frozen_client_base_representation_id / incoming artifact+sha256 / immutable_definition_bundle_sha256 / authority_model_definition_sha256 / adapter_build_digest / origin_request_sequence / logical result`，另维护只能单调增的 `effective_request_sequence`；key 不包含 callback status、request id、callback 到达时的 room last-applied、可选 child 的 SQL NULL 或可变版本字符串。operation SHALL 不保存 application key；正常 forcesave shell 在 accepted/durable correlation 前保持 `application_id=NULL`。correlation 创建新 application时，该 shell 成为唯一 primary并绑定 application；若不同 request/Idempotency-Key 的 shell 并发命中既有同 key application，则 application row/primary 被锁定，原子执行 `effective_request_sequence=max(existing,request_sequence)` 并同步 room 的 `latest_durable_application_id/latest_durable_sequence`，后续 shell SHALL 以 `application_id=NULL, state=duplicate, duplicate_of_operation_id=<primary>` 直接终结并写 append-only sequence-fold/duplicate events。`origin_request_sequence` 永不改写；同 canonical application 的更高 sequence 只 fold，不得把自身 primary/conflict 标 stale或经 duplicate→primary 循环重定向。只有 room latest durable 指向另一个 canonical application且其 effective sequence 更高时，旧未应用 application 才可 supersede。`duplicate_of_operation_id` 必须同 project/wp/entry/room/generation、同 frozen bundle/authority model，目标必须是已绑定该 application 的 primary；禁止 self-reference、链、环、指向另一 duplicate或把 duplicate 再绑定 application。definition bundle digest 与 authority model digest SHALL 永远非空；可选 child 由 bundle 内版本化 typed null marker 固定。只有命中同一 frozen identity 的 status=6、status=2 和网络重试才可复用一个 application；相同 incoming 在不同 frozen base/representation/bundle/authority model 下必须产生不同 key，不得被 incoming-first 去重。即使 key 相同，operation 查询或 retry/resolve 跟随 primary前也必须先完成当前 requested duplicate 的显式 scope、permission/write-fence 校验和 direct-primary invariant，再 canonicalize；只要求 canonical primary 唯一绑定 application，不得要求合法 duplicate 自身绑定 application。复用旧终态不得绕过授权或创建第二 application/operation。
5.6. 下载文件 SHALL 先进入隔离 staged path，流式校验压缩大小、MIME/ZIP magic、OOXML 类型、entry/展开量、外部关系、宏策略和恶意路径。全部校验通过后才可登记 `kind=incoming,state=durable`；校验或安全策略失败只能登记 `kind=incoming,state=quarantined` 并保持 `durable_at=NULL`。只有 durable incoming 可创建/命中 content application、参与 extract/merge/retry/rematerialize 或作为只读 substrate；quarantined incoming 只允许 authorization-first download-only、expire、retention/legal-hold 处理，永不得“解除隔离”、转 durable、创建 application、进入 engine 或作为 result 来源。所有 incoming SHALL 永不进入 `published/current/resolvable` 状态，也不得被直接晋升为 representation；只有以 durable incoming 为只读 substrate 新生成的 result representation 经过 frozen-bundle rematerialize、反读等值、安全、最终授权与 eligibility 校验后，才可独立执行 `staged → published`。
5.7. WHEN 鉴权、下载、OOXML 校验或 durable 写入失败 THEN callback SHALL 返回 OO 非零 error，`durable_at` 保持空，delivery 可进入 pre-durable `rejected/error` 且 application/recovery owner 均空；已精确关联的 request/operation shell只记录失败终态，不得伪造 recovery/application，canonical pointer 与 content revision 不变。
5.8. WHEN incoming 已耐久但 correlation 无法唯一完成 THEN callback SHALL 返回 `error=0`，delivery 绑定 immutable recovery case 与 incoming，不得伪造 operation。系统 SHALL 提供 authorization-first 的 claim/re-correlation：claim 必须引用同 room/generation 的 prior confirmed descriptor，冻结其 legal base、非空 immutable definition bundle 与 authority model，重验当前 project/workflow、claiming participant、generation/write fence 与 contributor snapshot，并以 Idempotency-Key 在一个数据库事务内最多创建一个 `recovery_claim` request、一个 operation shell，并创建或命中一个 content application；新 application 时 shell 作为唯一 primary绑定 application，case/delivery 记录同一 canonical application；若命中已绑定的同 key application则 shell 必须按 Requirement 5.5 在事务结束前成为直指 canonical primary 的 terminal duplicate，case/delivery 显式绑定同一 application且 canonical primary一致；三者在 claim 成功前均不存在，禁止把正常 forcesave accepted 时允许的 nullable-application operation shell 套用于 recovery。授权、prior confirmation、bundle/fence 或 contributor 任一不合法时不得产生 operation；download-only SHALL 只终结 recovery case并授权下载，永不创建 request/application/operation。不满足安全条件时只能转 `download_only/quarantined/expired`。WHEN extract/merge/rematerialize 或最终 authorization fence 失败 THEN 已形成的 operation 落可重试 `error / authorization_stale` 并保留 incoming；两类恢复均不得要求 OO 重发文件，且 nullable operation 的 recovery case 不得进入普通 operation retry。
5.9. 文件 durable 与数据库 application 不宣称同一 ACID 事务；数据库事务 SHALL 只发布已校验 staged artifact，失败留下不可见 orphan，不能形成 pointer 指向缺失 artifact 的半成功态。
5.10. 所有 operation 状态转换 SHALL 写 append-only transition event，包含 from/to、stage、actor、timestamp、correlation id、`client_edit_epoch / origin_request_sequence / effective_request_sequence / superseded_by` 与错误码；primary 的 `application_bound`、same-application 的 `sequence_folded` 与 duplicate 的 `duplicate_of_operation_id/state=duplicate` 都必须和 application/delivery correlation 同事务落唯一 event。duplicate GET/timeline/retry/resolve SHALL 先对 requested operation 做当前授权与 direct-primary 校验，再 canonicalize，并只要求 canonical primary 唯一绑定 application。同 generation 较新的 durable request SHALL 推进 room durable fence；若命中同 canonical application，只单调 fold effective sequence且不得 supersede 自己，只有较新且 canonical application 不同的 durable incoming 才 SHALL supersede 旧的未应用冲突/operation。current state 只是 timeline 投影。
5.11. incoming、temp、representation candidate、conflict、recovery case、orphan、trace bundle 和 evidence artifact SHALL 有按敏感级别配置的 retention、访问控制、清理审计与 legal hold 例外；策略必须有版本、dry-run、引用复核与删除结果证据。
5.12. 解析异常 SHALL 记录 error code、stage、immutable adapter/definition bundle/authority model identity、bundle typed child inventory、base/current/incoming revision、sequence 与 correlation id；不得被宽泛 `except Exception` 降为成功或“本项目无数据”。

### Requirement 6: Excel 显式契约、模板增强与字段级三方合并

**User Story:** 作为审计师，我要 OO Excel 的每个可编辑业务格准确回写到对应字段；动态行列、公式和重复表头不能串数据。

#### Acceptance Criteria

6.1. 每个标准 Excel 双向入口 SHALL 注册显式 adapter contract；generated YAML 的 `col_a / col_b / ...` 不得直接作为生产写格契约。
6.2. contract canonical payload SHALL 只包含 `contract_id / semantic_version / template_definition_sha256 / instrumentation_definition_sha256 / normalized_structure_hash / sheet_key / table_key / stable_field_key / JSON Pointer / cell mapping` 等语义字段，不得内嵌自身 artifact UUID/hash。发布器 SHALL 先解析已发布的 template 与 instrumentation definitions，再对 UTF-8、递归键排序、数值/换行规范化后的 contract canonical JSON 计算 SHA-256，最后在 DB/envelope 写 `definition_artifact_id + definition_sha256` 与被引用 FK。definition 发布与 representation finalize 的依赖方向 SHALL 固定为 `template → instrumentation → contract → definition bundle → representation`；authoritative model definition 独立先行批准并作为 bundle 必填 child。bundle canonical payload SHALL 含 schema version、authority model digest 及 template/instrumentation/contract 三类 typed canonical slots；每个 slot 必须出现，可选 child 只能使用版本化 typed null marker，严禁字段缺失、空串、全零 hash 或 SQL NULL 进入 canonical bytes。instrumentation payload 不得反向引用 contract 或 bundle digest，registry alias 只能指向不可变快照，历史 operation 不得按 alias 重新解析。
6.3. contract SHALL 表达两级表头、merge、公式 mask、样式来源、动态行/列、footer anchor、删除策略与 row identity。
6.4. 按公司/单位横向动态列 SHALL 使用稳定 key `{slot}_{seq}`；不得使用可改 label 作 identity，不得写死列数。
6.5. 动态行 SHALL 使用模板行 key 或 `row_uuid`；不得使用数组下标作为持久化身份。
6.6. 公式、auto-source 和受保护单元格 SHALL 默认只读；OO 对其修改 SHALL 产生受保护字段冲突，不得覆盖公式结果。
6.7. extract SHALL 产出按 stable field key 对齐的 incoming 投影，并以 base/current/incoming 三方规则合并：仅 incoming 变更则采 incoming，仅 current 变更则保 current，两侧同值则合并，同字段异值则冲突。
6.8. 不同字段的并行修改 SHALL 自动合并；同字段不同值 SHALL 进入冲突预览。
6.9. 行新增、删除、重排与 footer 下移 SHALL 按 row identity 合并；不得把位置变化误判为整表覆盖。
6.10. contract/template 结构漂移 SHALL fail closed，指出首个漂移 sheet/field/cell；不得继续按旧坐标写格。
6.11. materialize 后 SHALL 以同一 adapter extract 反读并比对受管字段；不一致不得发布版本。
6.12. D2 大 JSON 载荷等大表 SHALL 流式/分区处理，不得复制多份 866KB+ 结构造成无界内存增长。
6.13. 平台自有且位于 `backend/wp_templates/` 的 Excel 模板 MAY 进行受控 instrumentation；允许使用隐藏 `_GT_SYNC` sheet、defined names、Excel Table identity、隐藏稳定 row/column UUID，但不得自造可见披露内容或改变未经批准的业务公式/标签。
6.14. instrumentation canonical manifest SHALL 不内嵌自身 UUID/hash，也不得包含 `contract_definition_sha256`、`definition_bundle_sha256` 或其他反向 contract/bundle 引用；其语义 payload 只包含已发布的 `template_definition_sha256 / template_sha256 / instrumentation_version / identity_schema_version / sheet_id / table_id / field_id / row_uuid` 等载体定义，发布后由 DB/envelope 赋予 artifact ID/hash。contract 在 instrumentation 发布后单向引用其 digest；bundle 在 contract 与 authoritative model 均 approved 后单向引用 child digests。若要证明配对，只能由 bundle/representation compatibility envelope 在 child digests 均已计算后绑定。写入具体 representation 的 `_GT_SYNC` runtime binding 可包含已计算的 authority model、template、instrumentation、contract 与 bundle digests 及稳定业务 identity，但不得反向改变任一 child definition hash；identity 不得依赖环境 UUID、sheet 展示名、中文 label、数组下标、当前单元格坐标或运行时可变 alias。
6.15. OO 内新增动态行的空 UUID、复制行产生的重复 UUID、用户删除 identity 列及非法 structural edit SHALL 按 contract 明确分类为“分配新 ID、结构冲突或拒绝”；不得静默猜测或复用已删除 UUID。
6.16. identity 载体的具体选择 SHALL 先通过真实 OnlyOffice 9.4 黑盒探针，验证打开、编辑、插删、排序、复制、forcesave、下载、重开后仍保留；未过门不得建设依赖该载体的通用 engine。
6.17. instrumentation 后 SHALL 验证可见 sheet、业务值、公式、样式、merge、drawing/chart/pivot 等受保护部件与增强前等价；隐藏元数据 sheet 必须被业务导入、报表与 sheet 枚举显式排除。
6.18. 已生成存量底稿 SHALL 通过版本化 template upgrader 迁移：引用旧 content version/representation、复制 artifact 到 staging、校验旧 immutable definitions、注入 identity、反读等值后先写 non-current `representation upgrade candidate`。candidate 不得被 canonical resolver、room、download、current pointer 或 evidence 使用；只有该 entry 的 approved per-entry contract、approved authoritative model 与非空 approved definition bundle 均形成，且 `template → instrumentation → contract → bundle → representation` 校验通过后，才可 finalize 为新 immutable representation generation并允许切 pointer。WHEN 业务 projection 未变化 THEN content revision SHALL 保持不变；失败或缺 bundle/contract SHALL 保持原 pointer/revision，不得原地批量覆盖或制造伪业务 revision。
6.19. custom/user-uploaded xlsx 在无显式 contract 时 SHALL 不被强行 instrumentation；其 bundle 必须声明 `custom_authoritative_ooxml` 或 `opaque_single_onlyoffice` authoritative model，并在 instrumentation/contract slot 使用明确版本化 typed null marker，只能使用不改变原文件语义的 sidecar identity或保持 `single_onlyoffice/custom` 能力态。不得以缺字段、SQL NULL、空 digest 或 projection-contract bundle 冒充。
6.20. extract SHALL 以 instrumented stable identity 为首选、contract 中已验证的原生结构锚点为次选；两者均不存在时 fail closed，不得降级中文标题或位置猜测。

### Requirement 7: Word SDT 结构化岛与自由正文隔离

**User Story:** 作为审计师，我要在 Word 中自由完善正文，同时稳定字段仍可回写 HTML；自由文字不能被一次同步抹掉。

#### Acceptance Criteria

7.1. Word 标准双向入口 SHALL 使用带稳定 `w:tag` 的 SDT 映射结构化字段；段落绝对索引、中文正则、整段文本和已替换 placeholder 不得作为正式回写协议。
7.2. 重复行/区块 SHALL 使用 row-level SDT，并在 tag 中包含稳定 `row_uuid`；不得用表格行号识别。
7.3. SDT 外内容 SHALL 视为 Word-only，自由正文在 HTML materialize 时必须保留。
7.4. 同一 stable field key 多实例值一致时可合并；值不一致时 SHALL 产生冲突并列出全部 OO 位置。
7.5. 模板 token 跨 run、同段多 token、插删段落后 SHALL 仍能通过 SDT tag 读写。
7.6. F2-22/F2-23 SHALL 作为 Word pilot，先验证 OO 9.4 打开、编辑、forcesave、callback、重开后 `w:tag` 仍存在，再允许批量迁移其他 DOCX。
7.7. 18 个可正确解析 DOCX、9 个误解析为父级 XLSX 的 B 子码、缺失的 `S33-REV` 及 A16/A17 专用链 SHALL 逐一进入 resolver/adapter 清册并完成裁决。
7.8. WHEN OO 版本或模板操作导致 SDT tag 丢失 THEN operation SHALL fail closed 并保留 Word 文件版本，不得用段落索引降级回写。
7.9. HTML materialize SHALL 只更新结构化岛；不得用模板重生成覆盖审计师已编辑的 Word-only 内容。
7.10. Word adapter SHALL 固定非空 immutable definition bundle id/digest、authoritative model、bundle 内 template/instrumentation/per-entry contract typed child identities、SDT schema version和字段实例计数，以检测模板漂移和实例缺失；projection-based Word 的 contract child 必须 approved 非空，历史 retry 不得加载 registry 当前 alias或重组 bundle。

### Requirement 8: 冲突预览、人工裁决与可回滚

**User Story:** 作为现场经理，我要知道哪里冲突、为什么冲突，并能逐项选择后留下审计轨迹；任何错误应用都能回到上一版本。

#### Acceptance Criteria

8.1. 冲突记录 SHALL 包含 stable field key、业务标签、JSON Pointer/OO 位置、base/current/incoming、字段来源、保护策略和建议动作。
8.2. 冲突预览 SHALL 按 sheet/table/row 分组，金额使用平台 `displayPrefs.fmtAmount()`，并提供可追溯 OO 单元格/SDT 地址。
8.3. 用户 SHALL 可逐项选择 current/incoming，或对文本字段输入合并值；批量选择 SHALL 明确作用范围并二次确认。
8.4. 仅具备底稿编辑权限的用户可提交裁决；复核锁定、归档或权限 epoch 变化时 SHALL 拒绝。
8.5. 冲突裁决 SHALL 同时携带 `expected_current_revision / room_generation / client_edit_epoch / canonical_application_id / application_effective_request_sequence / room_latest_durable_application_id / room_latest_durable_sequence / conflict_set_digest` 作乐观锁。服务端先授权 requested operation；若其为 `application_id=NULL` 的 terminal duplicate，先验证 direct-primary invariant再 canonicalize，并以 canonical primary/application 比较 room fence。裁决期间出现 permission/write fence 变化或新 content revision 时 SHALL 拒绝或 rebase；room latest durable 指向较新且不同 canonical application 时，旧 conflict SHALL 被 supersede 或对最新 operation 重建。仅同一 canonical application 因较高 request sequence 发生 effective-sequence fold时不得把自己判 stale、不得形成 duplicate→primary→stale 循环，而应规范化到最新 effective sequence 后继续同一 conflict set。
8.6. 每次应用和裁决 SHALL 记录 actor、时间、来源 operation、选择结果和前后 revision。
8.7. 回滚 SHALL 通过创建新的 content version 指向选定历史内容实现，不得删除或原地改写历史版本。用户路由必须以该 historical content version 的 immutable opaque UUID `version_id` 定位；per-wp numeric revision 只作显示/乐观锁，不得作为 scope lookup key。
8.8. 回滚 SHALL 先 stage 并反读目标 artifact/projection，再以短数据库事务创建新 version、推进 revision/pointer/outbox；文件或数据库任一步失败均不得把不完整版本暴露为 current。
8.9. incoming 已耐久但 merge 失败的 operation SHALL 可从保存点重试 extract/merge，不再次调用 OO forcesave。未形成 operation 的 unmatched/ambiguous delivery SHALL 只能经 Requirement 5.8 的 authenticated recovery claim 绑定 prior confirmation/bundle 后原子创建 recovery request/application/operation，或进入 download-only/quarantine；download-only 永不创建 operation，不得把 nullable operation id 传给普通 retry。
8.10. merge 或人工 resolve 得到 merged projection 后 SHALL 只以该 application 固定且 `kind=incoming,state=durable` 的 artifact（无 incoming 的非 OO 路径使用当前 canonical representation）为只读基底，仅把受管区域重写到新的 staged result，使用 frozen 非空 definition bundle/authority model 完成 extract 等值、未管理区域保留、安全与最终 eligibility 校验后，才发布新的 immutable representation。quarantined incoming SHALL 永不创建 application、不得被 extract/merge/retry/rematerialize 或任何 engine 消费，只能 authorization-first download-only、expire、retention/legal-hold；本协议不提供解除隔离或 quarantined→durable 边。incoming 本身 SHALL 永不成为 published representation、current pointer 或 resolver 输出；不得按 registry 当前 alias 偷换 contract/template/instrumentation、重组 bundle或使用 upgrade candidate。
8.11. WHEN rematerialized artifact 的受管 projection 与 merged projection 不等值，或 Word-only/Excel 未管理区域发生非预期变化 THEN application SHALL 失败，HTML projection、current pointer、last-applied 与 client-confirmed base 均不得推进。
8.12. applied content version SHALL 同时绑定 merged projection hash 与 result representation id/artifact hash/immutable definition bundle id+digest/authoritative model identity；任何 resolver 读取该 revision/entry 必须返回一致身份，projection-based result 的 bundle 必须含 approved contract child。WHEN result managed projection 与 incoming 不等值 THEN client-confirmed base 保持旧值并触发 refresh-required generation rotation。

### Requirement 9: 模板解析、canonical resolver 与版本化迁移统一

**User Story:** 作为维护者，我要 Word/Excel 配置、下载和 callback 始终操作同一份项目文件，不能因 resolver 分叉写到另一条路径。

#### Acceptance Criteria

9.1. 标准模板权威源 SHALL 为 `backend/wp_templates/`；每个审核通过的 template、instrumentation manifest、contract 与 authoritative model SHALL 发布为内容寻址 immutable definition artifact，记录 SHA-256、normalized structure hash（适用时）、来源 commit 与 supersedes 关系；每个可用 representation 还 SHALL 绑定按 canonical typed slots 生成的非空 immutable definition bundle。
9.2. 运行态 canonical 文件 SHALL 位于项目独立存储，不得写回模板库或跨项目共享路径。
9.3. 通用 Word config 与 callback SHALL 解析到同一 canonical path；不得一侧使用 `.../workpapers/onlyoffice/{wp_code}.docx`、另一侧写 `storage/{project_id}/workpapers/{wp_code}.docx`。
9.4. `find_template_file_any()` SHALL 对所有适用子码按最具体 wp_code 优先解析 DOCX，不得只对 A 类特殊处理。
9.5. 模板缺失或类型与 adapter 不符 SHALL 显式报错并进入 manifest，禁止回退到父级异类型文件。
9.6. canonical resolver SHALL 防目录穿越、软链接越界、扩展名伪装和项目间路径复用。
9.7. artifact/candidate 发布 SHALL 使用同卷 staged file、fsync 与不可变目标；Windows 文件占用、杀毒扫描或 rename 冲突 SHALL 可诊断。candidate finalize 或 published artifact 任一步失败时数据库 pointer/revision 不得提前推进，candidate 仍不可被 resolver 使用。
9.8. 模板、instrumentation、contract 或 authoritative model 更新 SHALL 先按 `template → instrumentation → contract → bundle` 生成并批准新的 immutable definitions/bundle，再触发 template SHA、normalized structure、identity inventory、contract 双向漂移与 bundle compatibility 检查；未审核结构、unapproved/missing-contract bundle 或 candidate 不得自动移动 alias、finalize/current、套用旧 adapter 或改变历史 operation 的固定 bundle。
9.9. 权威模板的可见业务结构 SHALL 与源 xlsx/docx 及已登记 `source_ref` 守卫锁死；instrumentation 只能通过声明式迁移清单增加，不得在运行时临时写回模板库。
9.10. template upgrader SHALL 记录 from/to template、instrumentation、contract、authoritative model 与 definition bundle IDs/digests、candidate id、前后 representation/artifact hash、业务 projection 等值报告、actor 与 rollback target；前置阶段只可生成 non-current candidate，待 approved per-entry contract/bundle 后方可 finalize。纯 representation 升级不得递增 content revision，任何失败、未批准或缺 child 时 current pointer/revision 保持不变。
9.11. config、download、callback、extract、rematerialize、retry、rollback、历史版本下载和 evidence 生成 SHALL 共用 resolver API，并按 content version + entry + representation generation 解析同一 artifact 与非空 definition bundle；现有 `wp_export/wp_file_resolver.py`、WOPI/storage/version 等 writer/resolver 必须进入迁移矩阵，不得形成第二权威，也不得解析 upgrade candidate。
9.12. 当前打开 sheet 的隐藏/显示 SHALL 只作用于 session 专用或 staged artifact；不得用 openpyxl 原地修改共享 current artifact 来隐藏其他 sheet。

### Requirement 10: 权限、并发、room participant 与会话撤销

**User Story:** 作为合伙人，我要 OO 回写遵守与 HTML 相同的项目可见性、编辑锁与复核权限，同 room 的不同用户也必须逐人授权和审计。

#### Acceptance Criteria

10.1. materialize、config、forcesave、callback application、冲突裁决和 rollback SHALL 复用现有 project access、visibility、delegation、编辑锁和工作流门禁。
10.2. forcesave command SHALL 按 initiating participant 重新校验 permission epoch/action/mode；callback route SHALL 按 room/generation/doc_key 服务凭证校验并记录 contributor snapshot，不得把 route participant 当整个聚合 artifact 的唯一授权主体。
10.3. 只读 participant 不得发起写 forcesave，也不得进入 write contributor snapshot；若 OO callback 显示其参与写入或 contributor 身份无法安全判定，当前 generation SHALL 被隔离/supersede，不得产生 content application/version。
10.4. 已撤销/过期 participant 或 superseded room SHALL 不能覆盖当前版本。撤销写 participant 时系统 SHALL 通过 OO drop 取证其已退出；无法证明时立即提升 `write_fence_epoch`、取消 outstanding requests并 supersede generation，其余有效用户须在新 generation 继续。若被撤销/过期 participant 持有尚未 promotion 的 close leader，`reconcile_close_intents()` SHALL 在 room lock 下按 Requirement 4.10 审计为 `authorization_stale` 并选择合法 successor；无 successor时必须进入 generation supersede + recovery-required 显式终态，不得永久阻塞或以 system identity 代提交。
10.5. 多用户不同字段并发 SHALL 自动合并；同字段并发 SHALL 产生按 frozen application key 去重的冲突，不得以 callback 到达顺序决定结果。
10.6. 所有用户发起的 sync API SHALL 统一遵循 authorization-before-idempotency/resource-read，并使用只含非敏感归属的 `working_paper_sync_scope_index(resource_kind, resource_id, project_id, wp_id, entry_id, room_id, generation, retired_at)` 打破“先读业务资源才能知道 scope”的循环。room/participant/confirmation/request/close-intent/delivery/application/operation/recovery/conflict 等可由用户提供 opaque id 定位的 child，以及 content version 的 immutable opaque UUID `version_id`，SHALL 与 scope row 在同一事务创建或退役；numeric `revision` 只用于显示与乐观锁，禁止作为全局 scope `resource_id` 或 rollback route key。child 退役只能原子设置 scope row `retired_at`，scope tombstone SHALL 永久保留且 `(resource_kind,resource_id)` 永不跨 scope/同 scope 重用，repository/trigger 必须拒绝物理删除、清空 tombstone或复用 id，index 不得存业务 payload、状态、hash、错误或候选摘要。每个用户路由/请求 SHALL 显式携带 `project_id/wp_id/entry_id`（recovery list 明确 entry/room scope，rollback 明确 entry并只接受该 scope 下 opaque `version_id`），统一 guard 的不可交换顺序为：认证 → 解析显式 scope/短期 signed scope claim → 仅查询 scope index → scope 与当前 project visibility 比对 → action/workflow/lease/generation/write-fence/bundle 重验 → 业务 resource 或 Idempotency-Key/cache lookup → 副作用。不存在、跨 scope 或无 project visibility SHALL 在业务读取前返回同形态、同阶段且满足统一时序预算的 404；已确认 project visibility 但缺 action/edit 权限或工作流门禁 SHALL 返回 403；401 只表示未认证。该顺序 SHALL 覆盖 pending-mutations、materialize、confirm-descriptor、forcesave、close-intents、recovery-cases list/claim/download-only、operations/conflicts/timeline query、resolve 与 rollback；GET/list/download-only 也不得提前暴露存在性。原请求成功后撤权、过期或 supersede 的重放 SHALL 被拒绝且不得泄露 descriptor/config/result，也不得产生新副作用。文档级 callback SHALL 继续使用独立签名的 room/generation service route，不走用户 404/403 契约；application 仍须通过 frozen request/recovery claim 与最终 authorization fence。
10.7. 临时文件、callback URL、Command Service 请求、evidence 和日志 SHALL 不泄露长期 token、授权 header 或项目敏感内容；短期凭证必须最小权限、短 TTL、可撤销。
10.8. 恶意/超大 OOXML、ZIP bomb、外部关系、宏与嵌入对象 SHALL 按版本化安全策略拒绝或隔离；不得直接交给解析器无限展开。
10.9. room 共享只表示协同文档共享，不得共享 participant 的 user_id、mode、permission epoch、lease、last seen 或审计 actor；initiator、callback route 与多 contributor 关系 SHALL 分表记录。
10.10. application 在进入最终 DB commit 前 SHALL 再次校验 project/visibility/workflow lock、room generation、write_fence_epoch、forcesave 或 close-capture request 的非空 initiating participant、其 permission epoch 与 contributor snapshot。clean close 不得以 system/route identity 代替用户授权；任一变化或 initiator 缺失 SHALL 阻止提交。leader 在 promotion 前授权 stale 按 Requirement 4.10 选择 successor或终结 generation；leader 已 promotion 后授权 stale SHALL 使唯一 request/application 进入 `authorization_stale` 并 supersede/recovery，不得接任再造第二 capture。已 durable incoming可保留，但只能由重新授权且未 supersede 的显式 retry继续；quarantined incoming不得进入 retry/application。
10.11. per-wp 串行化 SHALL 使用数据库 advisory/row lock 与唯一约束；不得依赖单进程内存锁，在多 worker 下必须保持相同结果。same-application effective sequence fold、room latest-durable application/sequence、close eligibility epoch/leader successor 与 no-successor supersede终态 SHALL 在同一 room/wp lock事务中原子决定。

### Requirement 11: 统一前端 launch descriptor、bridge 与可见状态机

**User Story:** 作为审计师，我要在所有底稿看到一致的编辑器启动、同步状态、错误和冲突处理，不必猜某个循环的切换按钮实际做了什么。

#### Acceptance Criteria

11.1. legacy dual-mode 实现 SHALL 收敛到统一 bridge；业务组件只提供 `entry_id`、flush/reload 钩子和 adapter 上下文，不得自行拼 config/forcesave URL。
11.2. bridge 状态 SHALL 至少包含 `html_idle / flushing / committing / materializing / oo_loading / confirming_descriptor / oo_editing / forcesave_requesting / forcesave_accepted / incoming_durable / merging / rematerializing / conflict / refresh_required / recovery_pending / recovery_claiming / recovery_download_only / applied / error`。
11.3. 用户可见文案 SHALL 全中文，并分别表达“命令已接受”“文件已耐久”“结构化回写完成”“发生冲突”；不得统一显示“同步成功”。
11.4. 后端 SHALL 返回唯一 `EditorLaunchDescriptor`；`GtOnlyOfficeSheet` 与 Word editor 只能消费该 descriptor，不得组件内再次请求并解释另一份 config。
11.5. `GtOnlyOfficeSheet` SHALL 暴露可 await 的 `forceSave()`/状态 API，发出 ready、dirty、save-requested、incoming-durable、applied/conflict、recovery-case、error 事件；不得只 emit `fallback`，且 recovery-case 事件在 claim 前不得伪造 operation id。
11.6. 模式开关在同步中 SHALL 禁用；失败后保持原模式并提供重试、查看详情或下载已保存 OO artifact。存在 callback recovery case 时，UI SHALL 仅向当前有权用户显示“认领恢复/仅下载”动作、候选 prior confirmation 与阻断原因；不得把 unmatched delivery 当普通 operation 自动重试。
11.7. 冲突态 SHALL 进入统一冲突面板，关闭面板不得自动应用任何一侧。
11.8. 旧 localStorage 枚举和按 wpId 的键 SHALL 幂等迁移到按 `entry_id/wp_id/sheet` 的统一键；过期值不得打开不支持模式。
11.9. 前端 SHALL 消费 commit 后 `workpaper.content.updated`，按 `wp_id + revision` 去重；不得依赖进程内 commit 前 debounce 事件。
11.10. fail-open 文案 SHALL 被禁止：任一真实同步失败后，后续 destroy/reload 成功不得覆盖 error。
11.11. UI SHALL 提供当前 content revision、representation generation、room/participant、opened/server last-applied/client-confirmed base、refresh-required、最后同步、未解决冲突与 evidence correlation id 的追溯信息。
11.12. descriptor/bridge 接线 SHALL 在真实渲染宿主做 DOM 与 API 顺序测试；仅 import、传不存在 prop 或调用不存在 expose API 均不得算接入。

### Requirement 12: adapter 分波迁移、模板改造与逐 entry 证据收口

**User Story:** 作为产品负责人，我要每个独立入口逐一有裁决、真实 operation 和可复核证据，而不是只做几个样板后宣布平台已支持。

#### Acceptance Criteria

12.1. adapter 迁移 SHALL 由 manifest slice 驱动；每个独立 entry 必须记录 capability 裁决、authoritative model immutable definition、非空 immutable definition bundle id/digest 及其 template/instrumentation/contract typed slots、representation generation、自动测试、真实 OO operation 和验收态。projection-based entry 缺 approved per-entry contract/bundle 时不得进入 bidirectional 验收。
12.2. Excel pilot SHALL 覆盖简单 checklist、D2 大 JSON 子表、H1 分组/动态结构、G7 两级动态表，并验证选定 identity instrumentation 在 OO 9.4 往返保留。
12.3. Word pilot SHALL 为 F2-22/F2-23；pilot 未通过 tagged SDT 往返保留前不得批量迁移其他 DOCX。
12.4. Excel 后续 SHALL 按 D→N、A/B/C、S 的冻结 manifest slice 逐 entry 推进；父组件重复入口只复用独立 adapter，不复制契约。
12.5. Word 后续 SHALL 覆盖 18 个 generic DOCX、9 个 B 子码错型、`S33-REV`、A16/A17 专用链；每个 entry 均需自身真实证据。
12.6. custom SHALL 继续使用 xlsx 单一权威 adapter，并接入统一 room/durable ack/状态/evidence；不得转为 JSON 三方 projection。
12.7. F2-22/F2-23 现有专用 to/from 端点 SHALL 迁到统一协议并删除第二套半闭环；删除前必须有等价证据和 rollback 点。
12.8. 无 HTML 对端的纯 OO entry SHALL 标为 `single_onlyoffice`；不得为满足数字伪造字段映射或修改模板制造对端。
12.9. 无 OO 业务价值或不可达入口 SHALL 删除或标 `single_html`；不得保留空白模板切换入口。
12.10. 每个 bidirectional entry SHALL 有一个服务端生成的 evidence summary，绑定 `entry_id / manifest source digest / editability / room_model / scenario_profile_digest / sync_test_run_id / required_scenario_set_digest / scenario_evidence_ids / authority_model_definition_sha256 / definition_bundle_id / definition_bundle_sha256 / bundle typed child identities / OO build / verified_at / aggregate result`；单个 operation、截图或一条 applied revision 不得代表全部场景。
12.11. 每个 scenario evidence SHALL 绑定自身 `scenario_id / operation_ids（可按场景为空） / application_ids / recovery_case_ids / content_version_ids / representation_ids / authority_model_definition_sha256 / definition_bundle_sha256 / artifact/projection/trace_bundle SHA-256 / server timeline range / browser build / result`。`sync_test_run`、scenario 与 trace bundle必须是持久化不可变实体；evidence SHALL 由服务端按 source-backed `editable/room_model/scenario_profile` + capability + frozen immutable definition bundle + authority model 从 DB、artifact 和 timeline 重算，禁止自由文本、自填时间或跨 entry 复制。download-only 场景 SHALL 断言 operation_ids/application_ids 为空。
12.12. 每个 projection-based bidirectional entry 的最小 scenario set SHALL 无条件独立覆盖 HTML→OO、OO→HTML、identity retention、不同字段并行 merge、同字段异值 conflict/resolve、frozen-base/status 6/2 dedupe、no-userdata browser-crash recovery claim、错误 prior confirmation/fence/contributor 拒绝、download-only 零 operation/application、merged≠incoming refresh/reopen 和 rollback；动态结构与 Word-only 再按机器 profile 追加对应场景。凡 manifest 满足 `editable=true AND (capability=bidirectional OR room_model=shared)` 的 entry SHALL 无条件追加两个真实用户的两种关闭顺序、A 普通 forcesave terminal 前/后 B close 两类交错、single participant，以及 close barrier/reconciler 最终 exactly-one close-capture；不得用“未标多人”、自由文本或可漂移布尔跳过。required scenario set SHALL 从 source-backed manifest profile + immutable definition bundle + authoritative model 枚举推导，并把 profile/digest 固定进 test run。`custom_authoritative_ooxml/opaque_single_onlyoffice` 不得省略 close/recovery/authorization 判据，只能由 bundle 中枚举型 authority model 把字段级两场景替换为“并发 authoritative artifact revision conflict + 无静默覆盖”；替换规则由服务端 registry 守卫，禁止自由文本豁免。任一缺失、失败、UNVERIFIABLE、bundle/profile 不匹配或 stale SHALL 保持未验收。
12.13. 全局 legacy 删除 SHALL 使用两阶段门：删除前可先执行 structural pre-reconcile，报告未裁决、假双向、bidirectional 未验收、unreachable 与 evidence stale，但该报告不得把 stale=0 当成结构检查前置条件或 deletion eligibility。所有保留入口完成全 entry required scenario rerun、服务端 evidence recomputation 后，真正 pre-delete eligibility 才 SHALL 要求未裁决、假双向、bidirectional 未验收与 evidence stale 为 0，且每个仍存在的 `unreachable` 唯一命中 source-backed deletion plan；不得把“待本次删除的 unreachable 已为 0”作为启动前提。删除后 SHALL 重新生成 manifest/registry，并因 source commit 变化将受影响 evidence 标 stale，完整重跑其 required scenario set 与服务端 recomputation。只有最终未裁决、假双向、bidirectional 未验收、unreachable、evidence stale 五类计数全为 0，才允许归档 spec。
12.14. Task 1/2 的 discovery/characterization 完成态 SHALL 与最终 reconcile 分开记录；早期 `[x]` 不得被解释为 registry、DOM 或真实 OO 已闭环。

### Requirement 13: 事务后事件、append-only timeline 与运维可见性

**User Story:** 作为平台管理员，我要同步链可重放、可查询、可解释，并保证副作用不会反向制造新内容版本。

#### Acceptance Criteria

13.1. 内容提交 SHALL 在发布 current pointer 的同一数据库事务写入 outbox；`workpaper.content.updated` 只在 commit 后发布。
13.2. typed Redis replay SHALL 原样保留 `wp_id / revision / operation_id / source / adapter_id / artifact_sha256` 及扩展字段，不得丢失 `extra`。
13.3. event consumer SHALL 以 event id/handler version 幂等；重复投递不得重复刷新、重复 after-save、重复生成 artifact 或递增 revision。
13.4. `WorkpaperSaveOrchestrator.after_save` SHALL 拆为不递增 revision 的可重放副作用 handler；失败进入 pending/failed/DLQ，不得 best-effort warning 后永久丢失。
13.5. operation 与 recovery case 的每个状态变化 SHALL 先写各自 append-only transition event，再更新 current state projection；禁止只保留最后状态，且 recovery case 在 claim 前不得借 operation timeline 伪造 operation。
13.6. 系统 SHALL 提供按 wp/room/participant/operation/recovery case/application/correlation id 查询完整 timeline、阶段耗时、幂等命中、冲突与错误码的接口或管理视图；所有查询先执行 Requirement 10.6 的 authorization-before-resource-read。
13.7. 指标 SHALL 至少覆盖 forcesave 接受、incoming durable、validate/extract/merge/rematerialize/apply、delivery/application 去重、recovery case/claim/download-only、close-intent singleton、bundle/candidate finalize、冲突率、contract 漂移、orphan GC 与 outbox 重试。
13.8. 日志、timeline、trace bundle 与 evidence SHALL 通过版本化字段级 `RedactionPolicy` 记录稳定 identity/hash，不记录整份底稿、token、授权 header 或敏感字段值；策略必须对嵌套 payload、异常文本和下载 URL 做 allowlist 投影，并有反向泄露测试。
13.9. 系统 SHALL 以版本化可测试 alert rules 区分 OO 服务不可用、callback 不达、无法归组的 status=2、recovery case/claim/download-only 积压、close-intent singleton 违规、callback 已 durable 后处理失败、permission/write fence 失效、definition bundle/contract/template 漂移、candidate finalize 失败或误暴露、refresh-required 积压、canonical rematerialize 失败、outbox 堆积、orphan/retention backlog 和 Windows 文件占用；每条规则须定义阈值、窗口、严重级别、去重键、恢复条件和 runbook。
13.10. operation timeline 的关键时间 SHALL 来自后端数据库/服务端时钟；浏览器 trace 只能作为客户端证据，不得伪造服务端 callback 顺序。

### Requirement 14: 测试、变异、真实 OO 验收、证据与性能边界

**User Story:** 作为维护者，我要证明双向回写真正贯通浏览器、OO、callback、数据库和 canonical artifact，并在目标并发下有明确容量边界。

#### Acceptance Criteria

14.1. 每个 bidirectional entry SHALL 有服务端编排的逐 scenario 产物级测试，至少断言真实字段、projection hash、representation/artifact hash、content revision、authoritative model definition、非空 immutable definition bundle 与 operation/recovery timeline；不得用一条 applied operation 覆盖全部场景，且 download-only 场景必须证明零 operation。
14.2. 验收 SHALL 覆盖 HTML 改值→OO 可见、OO 改值→durable callback→HTML 可见、不同字段自动 merge、同字段冲突预览/裁决、连续 forcesave frozen client base、merged≠incoming 后 refresh/reopen 与 rollback。
14.3. status=6/status=2 乱序、缺 userdata close、重复 delivery、相同 frozen application key 并发重试 SHALL 不产生多 revision、多 event、多 conflict 或错误推进 client-confirmed base；application key 计算不得读取 callback 到达时可变 room 指针，并须使用 frozen non-null bundle/authority model。browser-crash recovery case 在 claim 前必须零 operation。
14.4. Word pilot SHALL 在真实 OnlyOffice 9.4 验证 SDT 经打开、编辑、forcesave、callback、重开后 tag/row_uuid 集合与层级仍保留。
14.5. Excel pilot SHALL 在真实 OnlyOffice 9.4 验证 instrumentation identity、动态行增删重排复制、动态公司列、两级表头、公式保护、footer 下移和结构漂移拒绝。
14.6. merge/resolve/rollback 验收 SHALL 比对结构化数据、rematerialized published representation、projection/artifact sha256、content revision、definition bundle/authority model、last-applied/client-confirmed base、refresh-required/generation rotation、event 与审计 timeline；candidate 不得作为结果。
14.7. 守卫 SHALL 以行为、结构、真实执行或 DOM 为判据并做变异；必须区分 RED/GREEN/ANCHOR-MISS/WRONG-TEST，后三者任一非零不得通过。
14.8. 浏览器验收 SHALL 联合前端 network/console、后端 operation/recovery timeline 与数据库时间，证明 `flush mutation accepted < single content/approved-bundle representation commit < descriptor mounted` 以及 `forcesave request frozen < command accepted < incoming durable < applied/conflict/refresh-required terminal < reload/reopen`。对 no-userdata crash SHALL 证明 `incoming durable < recovery case(no operation) < authorization-first claim 或 download-only`；claim 成功后才出现 operation。
14.9. 测试数据 SHALL 完整复原；无法获得合法对象或真实 OO 环境时 SHALL 标记 UNVERIFIABLE，相关 entry 保持未验收，不得用 fixture 冒充。
14.10. 并发容量门 SHALL 至少覆盖 6000 个并发登录会话、1200 个 active OO participant、120 个同秒 forcesave burst 与持续 20 callback applications/s（10 分钟）；同 wp 串行、跨 wp 并行，且不得依赖单进程锁。
14.11. 默认安全预算 SHALL 由单一配置与测试锁死：压缩 OOXML ≤50 MiB、展开总量 ≤512 MiB、ZIP entries ≤20000、压缩比 ≤100、单 table ≤100000 行、单 projection ≤200000 fields；超限必须 fail visible，不得 OOM 或截断。
14.12. 对 ≤10 MiB、≤50000 fields 的标准 operation，在基准环境中 SHALL 达到 incoming durable p95 ≤10s、无冲突 applied terminal p95 ≤30s；若真实基线无法达标，须先用记录硬件/OO build/载荷的 capacity ADR 调整，不得静默放宽。
14.13. CI SHALL 覆盖 migration、后端、前端、contract/manifest、template instrumentation、mutation、evidence freshness、retention/redaction/alert rules 与无假双向门；引用产物必须被 git 跟踪。
14.14. 每个 entry 的 evidence SHALL 由服务端从 `sync_test_run + scenario rows + operation/recovery case/content version/representation + trace bundle` 重算 capability + immutable definition bundle + authoritative model 所要求的 scenario set、外键、hash、bundle typed slots、OO build 与 timeline 一致性；代表 entry、截图、自由文本或一条 operation 不能替代逐 scenario 证据。
14.15. final gate SHALL 扫描每个 AC 的 Design oracle、实现 task、独立验证 task 与 evidence type；任何悬挂 AC、无验证 Property、无依赖边或单任务自证均不得归档。
14.16. 真实 OO probe、pilot 和 bulk evidence SHALL 记录 OnlyOffice 精确 build、浏览器版本、authority model definition digest、immutable definition bundle id/digest 及其 template/instrumentation/contract typed child identities、runner/source commit 与运行时间；环境、source commit、runner、bundle 或任一非-null definition child 变化后 SHALL 按 stale policy 失效。structural pre-reconcile MAY 报告 stale 而不把 fresh=0 当作结构检查前提；真正 pre-delete eligibility 只能在全 entry required scenario rerun 与服务端 recomputation 后判定。删除 legacy/不可达桩造成 source commit 变化后，相关 entry 必须生成新的 test run，完整重跑 required scenario set并通过服务端 recomputation；post-delete smoke 不得替代。
