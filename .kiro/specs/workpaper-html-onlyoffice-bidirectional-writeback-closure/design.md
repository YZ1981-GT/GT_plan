# Design Document

## 总控 G1-1 实施边界

冻结身份只有 bundle typed slots，不假定 FrozenEntryDefinitions 含 instrumentation。复用 PublishedIdentityObserver 的 child digest、approved state、payload canonical digest 与 artifact 路径解析，提供按冻结 bundle 读取 anchors 的公共入口。三个业务宿主在构造 ContentCommitPlan 时传入 anchors；plan 仍是无 I/O 纯数据。Excel commit 与 candidate finalize 共同委托 compute_structure_hash_from_artifact 消费最终文件；Word 与权威 OOXML 不进入 Excel hash 路径。证据及回滚范围见 evidence/g1-1-publish-structure-hash/README.md；不得改动其他 owner 的 registry、Task75 测试、D2 router 或前端。


## Overview

本设计采用“统一内容提交内核 + shared OO room/per-user lease + 显式 adapter contract + 可增强模板 + 入口 manifest + 分波迁移”。它解决的不是单个切换按钮，而是六个必须同时成立的闭环：

1. **内容闭环**：所有 writer → `ContentMutationService` → 单次业务 commit 同时发布 projection 与兼容 representation → forcesave callback → extract → 三方 merge → canonical rematerialize → 新 content revision；不得把 HTML projection 与随后 materialize 写成两次业务提交。
2. **版本闭环**：business `content_revision` 与 `representation_generation` 分离；content application 固定非空 immutable definition bundle（含 authoritative model 与 typed template/instrumentation/contract slots），normal operation shell 在绑定前只读 frozen request 的同一 identity；room 同时记录 server last-applied 与 client-confirmed base，连续 forcesave 不把服务器合并结果冒充编辑器已加载基线。
3. **协同闭环**：room 共享聚合文档，participant lease 隔离用户、权限、模式、TTL 与撤销；callback 按 room/generation route 鉴权，initiator、route participant 与 contributor set 分开建模。
4. **幂等闭环**：forcesave/close request 在命令前冻结 client base、sequence、definition bundle、authority model 与 write fence；callback delivery 可多次，content application 对同一 incoming + frozen bundle 最多一次，status 6/2 乱序不读取可变 room 指针制造第二版本。
5. **介质闭环**：文件先 stage/校验，数据库短事务发布 content version/representation/pointer/outbox，失败 artifact 作为不可见 orphan 清理；不宣称文件系统与 PostgreSQL 同事务。
6. **覆盖闭环**：当前 185 个物理宿主、276 个挂载点、186 个 manifest entry 全部有裁决；每个 bidirectional entry 均有持久化 test run、逐 scenario evidence 与服务端可重算 trace bundle，不以单个 applied operation 代表全场景。

### 调查事实与方向性结论

| 维度 | 当前事实 | 设计结论 |
|---|---|---|
| 前端入口 | 185 个物理宿主、276 mounts、186 entries；142 independent、43 parent duplicate、1 unreachable | manifest 是动态真源；bridge 只接独立 entry，父级不重复计算 |
| legacy 能力 | 142 template-only、13 reload-only、142 无 forcesave/ack/adapter；132 个 single 仍显示切换 | 红基线保持 fail-closed；最终 reconcile 与 discovery 完成态分离 |
| HTML writer | `wp_html_save` 使用 `parsed_data._version`，orchestrator 另增 `file_version` 且异常 warning | 先建立 writer/resolver/version 清册；全部迁入 `ContentMutationService`，副作用改可重放且不增 revision |
| config/doc key | `_generate_doc_key = md5(wp_code + mtime_ns)` | room id + generation；mtime 不再参与业务版本 |
| 协同状态 | 现有/旧设计以一个 session 保存一个 user/epoch/mode | 拆 `oo_room` 与 `oo_participant_lease`；callback 是 room/generation 级聚合事件，撤销无法安全 drop 时旋转 generation |
| callback | `claim_version=None`、直接写 target、多次 commit；status 2/6 未分 delivery/application | 先持久化 frozen forcesave/close request，再 durable incoming；delivery 与 application 双层幂等，status 2 无 userdata 只按确定规则归组 |
| 文件/DB | 旧措辞暗示 pointer 与文件同事务 | staged immutable artifact → DB content/representation pointer transaction → orphan GC |
| 内容与表示 | HTML save、materialize、template upgrade 易被写成多个 version/commit | business content version 与 representation generation 1:N；纯 hidden instrumentation 升级不增 content revision |
| 定义身份 | operation/version 只存 contract/template 版本字符串 | template/instrumentation/contract/authority_model 发布 immutable definition artifact；按版本化 typed slots 生成永远非空的 definition bundle，所有 representation/application、pre-bind request/shell、retry/resolver/evidence 用 bundle FK+hash 固定 |
| 升级发布 | upgrader 容易在 per-entry contract 前直接发布 representation | 前置阶段只生成 non-current candidate；DAG 固定 `template → instrumentation → contract → bundle → representation`，approved bundle 后才 finalize/current |
| 前端 OO 组件 | `GtOnlyOfficeSheet` 自行请求 config，仅 emit `fallback`，卸载只 destroy | 唯一 `EditorLaunchDescriptor`；暴露可 await forcesave/dirty/ack/error |
| Excel schema | 478 YAML/3034 sheet；大量 dynamic sheet 为 `col_a` 占位 | 每 sheet 显式 contract；平台模板允许受控 instrumentation，但必须先过 OO 9.4 identity probe |
| Word 模板 | 20 份 DOCX 仅 5 个 SDT，均无稳定 tag/dataBinding | 正式协议只认 tagged SDT；先做真实保留 probe，再建通用 engine |
| custom | xlsx 本体唯一权威 | 保持同源模型，只接 room/ack/evidence，不强制 instrumentation/JSON 投影 |
| F2-22/23 | 专用 to/from OO，不等 callback且可能覆盖自由正文 | 作为 Word pilot，统一内核后删除第二套流程 |
| event | commit 前 debounce；typed replay 丢 `extra` | 复用 durable outbox；operation transition 另建 append-only event，handler 不递增 revision |

### 明确拒绝的方案

1. **给 184 个组件逐文件加“切回 reload”**：OO 内容从未进入数据库，是假同步。
2. **标准底稿 OO 全只读**：回避了用户要求的双向回写；只有业务上确实无 HTML 对端的入口才可裁决为单模式。
3. **把 generated `col_a` 自动映射到 JSON**：97% 以上 dynamic sheet 无业务语义，能运行但会写错格。
4. **按中文表头、label 或数组下标映射**：改名、重复 label、插删行后必串数据。
5. **直接覆盖 target 文件**：旧会话可覆盖新会话，且不可回滚。
6. **mtime doc key / updated_at 冲突检测**：文件操作或复核状态都会造成错误房间/假冲突。
7. **Word paragraph index、placeholder regex、整段回填**：同段多 token、跨 run、插删段落已证明不可靠。
8. **callback 解析失败返回非零要求 OO 重发**：文件已耐久保存时会制造重复 callback/版本；正确做法是 ack OO、operation 留 error 可重试。
9. **标准结构化底稿投影成自由网格并整体覆盖**：会破坏公式、auto-source、稳定行身份和审计追溯。
10. **新建第二套通用事件总线**：现有 durable outbox 可复用；operation transition event 与业务 outbox 分工，不重复造发布系统。
11. **单 session 行承载共享 room 与用户授权**：多人协同时会互相覆盖 user/mode/epoch，必须拆 participant lease。
12. **application key 放在 operation、预建 application 或包含 callback status**：accepted 时尚无 incoming，既无法形成完整 key，也会把同一内容的 status 6/2 当两次应用；normal path 只能先建 nullable-application operation shell，key 只由 durable 后的 content application 持有，status 只进入 delivery identity。
13. **把 incoming 或 merged JSON 直接设 current**：HTML 与 canonical OOXML 会立即分叉；必须 rematerialize + extract 等值后发布。
14. **先写 Excel/Word 通用 engine 再试 identity 保留**：若 OO 9.4 剥离 defined name/hidden UUID/SDT 会造成大规模返工；黑盒 probe 必须前置。
15. **在共享 canonical 上原地隐藏 sheet**：并发打开不同 sheet 会互相覆盖并可能丢 OOXML 部件；只能生成 room/staged 专用 artifact。
16. **代表 entry 代替逐 entry evidence**：pilot 只证明架构可行，不能证明其他 contract/template/宿主已接通。
17. **merge 成功就把 server result 写成 client base**：live OO 仍持有 incoming，下一次全量 forcesave 会把服务器合并字段回退；managed projection 不等值时必须 refresh/reopen。
18. **callback 绑定单个 participant 做整份 artifact 授权**：shared room 文件可含多人贡献，route participant、forcesave initiator 与 contributors 不是一回事；callback 只能 room/generation 鉴权，撤销歧义必须旋转 generation。
19. **callback 到达时读取可变 room 应用指针计算 application key**：status 6 首次应用会改变该值，随后 status 2 会得到第二 key；基线、sequence、definitions 必须在 request accepted 前冻结。
20. **HTML 先 commit projection，再 materialize 另 commit 一次**：同一业务变化会产生两个 revision 或改写 immutable version；bidirectional save 必须单次业务 commit，纯 representation 升级使用独立 generation。
21. **operation 只记 `contract_version/template_version` 字符串，或用 nullable contract 直接拼 application key**：registry alias 会漂移，custom/opaque 无法形成全定义 identity，历史 retry 无法复现；必须引用内容寻址 authoritative model 与非空 immutable definition bundle，所有可选 child 使用 typed null marker。
22. **upgrader 在 per-entry contract/bundle 前发布标准 representation**：会产生无法证明语义且可能被 room/resolver 打开的 current artifact；前置产物只能是 non-current candidate，批准完整 bundle 后再 finalize。
23. **一条 applied operation 证明 entry 已验收**：双向、identity、dedupe、no-userdata recovery、refresh/reopen、rollback、冲突/动态/多人场景必须逐 scenario 持久化并由服务端重算。

## Architecture

### 分层

```text
┌────────────────────────────────────────────────────────────────────┐
│ Vue hosts                                                         │
│ useWorkpaperSyncBridge + status/conflict + EditorLaunchDescriptor  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ flush / materialize / forcesave / status
┌──────────────────────────────▼─────────────────────────────────────┐
│ wp_sync_router + compatibility delegates                          │
└────────────┬──────────────────────┬────────────────────────────────┘
             │                      │
┌────────────▼────────────┐  ┌──────▼───────────────────────────────┐
│ Room/Participant       │  │ Request/Callback Coordinator        │
│ generation + leases    │  │ frozen request → delivery → durable │
│ client/server bases    │  │ → sequenced application             │
└────────────┬────────────┘  └──────┬───────────────────────────────┘
             │                      │
┌────────────▼──────────────────────▼───────────────────────────────┐
│ ContentMutationService / WorkpaperSyncCoordinator                 │
│ lock → freeze approved definition bundle → business mutation      │
│ → stage representation/candidate → roundtrip → one DB commit      │
│ → server last-applied; client base 仅等值/重载确认后推进           │
└────────────┬────────────────────────────┬──────────────────────────┘
             │                            │
┌────────────▼────────────┐    ┌──────────▼─────────────────────────┐
│ Excel contract engine  │    │ Word tagged-SDT engine             │
│ identity instrumentation│    │ structured islands                 │
└────────────┬────────────┘    └──────────┬─────────────────────────┘
             │                            │
┌────────────▼────────────────────────────▼─────────────────────────┐
│ CanonicalArtifactRepository                                      │
│ staged / upgrade candidates / immutable versions / incoming / GC │
└───────────────────────────────────────────────────────────────────┘
```

`ContentMutationService` 是所有业务内容 writer 的唯一提交边界；adapter 只负责读取/写入业务 projection 与 OOXML，不自行 commit、递增 revision 或发布事件。`DefinitionBundleService` 按 `template → instrumentation → contract → bundle` 发布并验证非空 immutable identity；`RepresentationService` 只能用 approved bundle 为既有 content version finalize 新的 immutable representation generation。upgrader 前置结果先写 non-current candidate；两者都不能改旧 row或推进 business revision。

### 状态机

#### OO room 与 participant lease

```text
room: opening → active → close_barrier → closing → closed
             │      ├──────────────→ refresh_required → superseded
             │      ├──────────────→ superseded
             │      ├──────────────→ expired
             │      └──────────────→ error

participant: active → closing → left
                  ├→ revoked
                  └→ expired

forcesave_request: frozen → command_pending → accepted → correlated → terminal
                                └→ rejected/timeout/unmatched/superseded

operation_shell: created(application_id=NULL) → accepted → application_bound(primary) → terminal
                                              ├→ duplicate(duplicate_of primary, application_id=NULL) → terminal
                                              └→ rejected/timeout

close_intent: created → ordinary_forcesaving → waiting_barrier → leader_ready
                    └────────────────────────→ promoted_to_close_capture → terminal
                    └→ authorization_stale → successor_selected | recovery_required
                    └→ retryable_blocked/superseded/error

recovery_case: unclaimed → claiming → application_created
                         └→ download_only/quarantined/expired
```

- room 共享 `doc_key/generation/opened_base/last_applied/client_confirmed_base`，不保存单一用户权限；close barrier 另保存单调 `close_barrier_epoch` 与 nullable `close_leader_intent_id`。
- participant 逐用户保存 mode、permission epoch、state 与 TTL；用户发起 request 时重新校验。callback route 是 room/generation 服务凭证，不承担单一作者语义。
- 每个正常 forcesave 在 Command Service 前，以一个事务冻结 request sequence、client base、representation、非空 definition bundle/authority model、write fence 与 initiator epoch，并创建 `application_id=NULL` 的 user-facing operation shell。Command accepted 只推进 shell/timeline，不创建 application 或 application key。
- incoming durable 且 request-first correlation 成立后，才创建或命中 `working_paper_content_application`。application key 的首个 winner shell 在一个事务中成为唯一 primary并绑定 application，delivery 同时记录该 canonical application；application 固定 `origin_request_sequence`，并把同 key 后续 request 原子 fold 到单调 `effective_request_sequence=max(...)`，room 同事务更新 `latest_durable_application_id/latest_durable_sequence`。不同 request 的后续 shell命中同一 application时保持 `application_id=NULL`，写 terminal `duplicate`/`sequence_folded` events并直指 primary，不得形成链/环或 stranded shell；同 canonical application 的 sequence fold永不 supersede自己，只有更高 effective sequence 且 canonical application不同才 supersede旧未应用 application。application 是 frozen identity/application key 与 logical result 的唯一 owner，primary operation 是唯一绑定执行容器，duplicate 只是可轮询 canonical 跳转。
- application 成功原子推进 `last_applied_version_id`。仅当 result managed projection 与 incoming 等值，或新 generation editor 明确 ack descriptor，才推进 `client_confirmed_base_version_id`。
- merged≠incoming 时 room 进入 `refresh_required`，拒绝下一 request，并 supersede/reopen；这条门防止 live OO 用旧 incoming 回退服务器合并值。
- 任一写 participant 撤销时先发可验证 OO drop；无法证明聚合文档已排除其贡献则提升 write fence、取消 outstanding request 并 supersede generation，其余用户重开。
- clean close 创建 intent 时必须在同一 room row lock 内把 participant `active → closing`；`closing` 从 active confirmed editor 仲裁集合排除。当 active 首次归零时按最高 `(intent_sequence,id)` 与当前 frozen eligibility snapshot写唯一 `close_leader_intent_id`，推进 barrier并阻止该 generation新 editor加入；此前 closing participant已启动的 ordinary forcesave是 barrier predecessor。
- `reconcile_close_intents()` 在 intent 创建、每个 predecessor ordinary forcesave terminal/superseded-safe、participant leave/error/revoke/expire 后幂等重入并再次锁 room。leader promotion 前失去资格时，旧 intent先写 append-only `authorization_stale` event并推进 `close_leader_eligibility_epoch`；随后只在仍合法 intents中按最高 `(intent_sequence,id)`选 successor。同一 eligibility snapshot的 replay不得换 leader。存在 successor且 active=0、全部 predecessor安全终结时，才以 CAS exactly-once提升为唯一 open close-capture；partial unique只负责 at-most-one。无 successor时必须 supersede generation并终结为`recovery_required/authorization_stale`，保留既有 durable incoming/application并要求重新授权用户从新 generation恢复，禁止无限`retryable_blocked`、静默零 capture或system/route代授权。promotion 后授权失效不得再选 successor或新建第二 capture，只能由最终授权 fence把唯一 request/application置authorization_stale并进入同一 recovery路径。合法资格的single/two-user关闭场景证明exactly-one；leader revoke/expire交错另证明有 successor仍exactly-one、无 successor则零 capture但显式可达终态且无数据丢失。
- 浏览器 crash/OO 自发 close 没有合法 request，或 callback 候选仍歧义时，incoming 绑定 recovery case 而非伪造 application/operation。claim 前 request/application/operation 全无；claim 先 authorization-first 校验 prior confirmed descriptor、bundle、generation/fence/contributors，再在一个事务中创建 `recovery_claim request + operation shell` 并创建或命中 application；commit 前 shell 必须成为绑定 application 的 primary，或保持 `application_id=NULL` 并成为直指 canonical primary 的 terminal duplicate，case/delivery 均记录同一 canonical application。download-only 只终结 case，三者恒无；nullable-operation case 不进入普通 retry。
- 新 representation generation 不自动改变 active editor；必须通过 descriptor/ack 建立 client-confirmed identity。

#### callback delivery 与 content application

```text
delivery: received → downloading → durable → acknowledged
                       └──────────→ rejected/error/unmatched

application: queued → validating → extracting → merging
                                             ├→ conflict
                                             ├→ superseded（较新 incoming sequence）
                                             └→ rematerializing → applying → applied
                                                                  └→ refresh_required
任一 durable 后阶段失败 → error（保留 incoming，可 retry）
同 frozen application key 已存在 → 当前 shell terminal duplicate（直指唯一 primary并返回其终态）
```

- delivery identity 可包含 callback status；application identity 明确不含 status，也不含 callback 到达时的 `room.last_applied`，而是固定非空 definition bundle 与 authority model。application key 只存于 `working_paper_content_application`。
- callback 含 `userdata/request_id` 时先精确绑定并校验 frozen forcesave/close-capture request，再由该快照与 durable incoming 计算 application key；不得先按 incoming 命中旧 application。仅 status 2 无 userdata 可走受限归组：唯一 open close-capture 优先；不存在 eligible request 时，只有 frozen identity（含 bundle）唯一且没有 sequence 更高 request 才可把 delivery 去重到已有 application。其余情况 durable 后创建 recovery case，correlation 标 `ambiguous/unmatched`，不得创建 operation、猜 base 或直接应用。
- delivery ownership 以 `durable_at` 判定而非泛化 terminal：`durable_at IS NULL` 的 received/downloading/rejected/error 可零 application/recovery owner（可保留已绑定 request/shell）但禁止双 owner；`durable_at IS NOT NULL` 的 durable/acknowledged/unmatched/post-durable error 必须二选一，且 post-durable error 保留既有 owner。application 路径可同时关联 frozen request与 operation shell；operation 若为 primary则自身 `application_id` 等于 delivery，若为 duplicate则自身 application为空且 direct primary 的 application等于 delivery。recovery 路径 request/application/operation 全空。
- callback 在 incoming durable 并原子创建/命中 application后，把 winner normal shell绑定为 primary；不同 request的 losing shell在同一事务写 direct `duplicate_of_operation_id` 与 terminal duplicate event，delivery仍绑定 application且 canonical primary一致。或者，callback持久化带 incoming/候选/原因的 recovery case后，即可按协议向 OO ack；`applied/conflict/refresh_required` 是前端离开或重开的门。recovery claim 创建/命中 application时遵循同一 primary/duplicate约束，download-only 三者恒无。
- 每个 generation 的 request sequence 单调；room 同时保存 `latest_durable_application_id/latest_durable_sequence`。较高 sequence命中同 application key时只原子提升该 application的`effective_request_sequence`并让room fence仍指向同canonical application；resolve先比较canonical application identity，再比较effective sequence，因此不得自我stale。只有较新 durable full snapshot属于不同canonical application时，旧未 applied application/conflict/operation才标记superseded。
- 每次 operation 转换先写 append-only event，再更新 current state projection；application 的 logical state/result 与 immutable identity 分离更新。无 operation 的 recovery case 使用自身 append-only recovery timeline。

### 两方向时序

#### HTML → OO

```text
Host        Bridge          ContentMutation/Representation       Room service        OO
 │ flush      │                       │                               │               │
 │───────────>│ draft+expected rev    │                               │               │
 │            │──────────────────────>│ lock once                     │               │
 │            │                       │ mutate business projection     │               │
 │            │                       │ resolve approved definition bundle
 │            │                       │ stage compatible representation│               │
 │            │                       │ roundtrip/security              │               │
 │            │                       │ one DB content/rep/pointer/outbox commit          │
 │ revision+rep│<─────────────────────│                               │               │
 │            │ request descriptor    │                               │               │
 │            │──────────────────────────────────────────────────────>│ room+lease    │
 │            │ EditorLaunchDescriptor│                               │               │
 │            │<──────────────────────────────────────────────────────│               │
 │ mount      │──────────────────────────────────────────────────────────────────────>│
```

flush 只形成待提交 mutation；bidirectional 业务保存与绑定 approved definition bundle 的兼容 representation 在一次 `ContentMutationService.commit` 中发布。若无业务变化则复用 content version；若只有 hidden instrumentation/contract/bundle 升级，`RepresentationService` 先登记 candidate，待 per-entry contract/authority model/bundle approved 后为同一 content version finalize 新 generation，business revision 不变。任一步失败都停留 HTML，candidate 不可见，不允许先产生 projection-only revision，再把 materialize 称作第二次 content commit。

#### OO → HTML

```text
Host/Bridge      API/Request+Operation       OO Command       Callback/Delivery      Application/Commit
 │ forcesave      │                               │                    │                    │
 │───────────────>│ tx: freeze req + create shell(application_id=NULL)│                    │
 │                │──────────────────────────────>│ accepted           │                    │
 │ accepted(req+operation) <──────────────────────│                    │                    │
 │ wait terminal  │<──────────────────────────────────────── status 6/2                    │
 │                │                               │ stream download → durable               │
 │                │                               │                    │ correlate frozen req
 │                │                               │                    │ create/hit application
 │                │<───────────────────────────────────────────────────│ correlation transaction
 │                │                               │                    │ winner: bind application + application_bound
 │                │                               │                    │ loser: application=NULL + duplicate_of(primary) + terminal
 │                │                               │                    │───────────────────>│
 │                │                               │                    │ frozen app identity + canonical primary
 │                │                               │                    │ extract+3-way merge│
 │                │                               │                    │ final auth/fence check
 │                │                               │                    │ rematerialize/roundtrip
 │                │                               │                    │ DB content+rep+outbox
 │ applied/conflict/refresh_required<──────────────────────────────────────────────────────│
 │ reload exact rev / conflict UI / supersede+reopen                                       │
```

Command Service HTTP 200 仅代表 accepted，正常路径此时只有 frozen request 与 nullable-application operation shell；incoming durable 仅代表可恢复。`working_paper_content_application` 在 durable correlation 后唯一持有 application key，status 6/2 可产生多 delivery 但不因首次 apply 改变 room 指针而分裂。application 总是推进 server last-applied；只有 result managed projection 与 incoming 等值时同一 live editor 才能自动推进 client-confirmed base，否则返回 `refresh_required` 并旋转 generation。

## Data Model

迁移编号在实施前重新实扫；设计时磁盘最高为 V150，若无并发新增则使用 V151。迁移须幂等并配回滚脚本。

### `working_paper` 增量列

| 列 | 类型 | 说明 |
|---|---|---|
| `content_revision` | bigint NOT NULL DEFAULT 0 | 只因业务 projection/custom 权威内容应用递增 |
| `current_content_version_id` | uuid NULL | 当前 immutable business content version |

`file_version` 保留给既有文件生命周期，不再被新同步协议当内容乐观锁。`updated_at` 继续服务通用审计时间，不参与 merge。entry 级 OO representation pointer 不塞进 `working_paper`，由下述 `working_paper_sync_entry_state` 管理。

### `working_paper_pending_mutation`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK；opaque token 只暴露签名后的 id |
| `project_id / wp_id / entry_id / sheet_key / user_id` | uuid/varchar | 完整作用域绑定 |
| `expected_revision` | bigint | 单次 business commit 乐观锁 |
| `payload_artifact_id / payload_sha256` | uuid/char(64) | 待提交 mutation，不经浏览器 token 携明文 |
| `idempotency_key` | varchar | UNIQUE `(wp_id,entry_id,user_id,idempotency_key)` |
| `state` | varchar | `pending / committing / committed / expired / invalidated` |
| `result_operation_id / result_content_version_id` | uuid | committed 后重放返回同结果 |
| `expires_at / created_at / committed_at` | timestamptz | 短 TTL 与服务端审计 |

`flushHtml()` 只创建 pending mutation，不推进 revision。commit 以 row lock 把 `pending→committing→committed` 与业务事务绑定：事务前失败可回到 pending 重试，事务成功后同 token/idempotency key 返回既有 operation/version；作用域、payload digest、expected revision、TTL 任一不符即拒绝。

### `working_paper_content_version`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `wp_id` | uuid | FK working_paper，索引 |
| `revision` | bigint | UNIQUE `(wp_id, revision)`；只映射业务内容 |
| `parent_version_id` | uuid | nullable self FK |
| `source` | varchar | `html / onlyoffice / conflict_resolution / rollback / custom` |
| `projection_artifact_id` | uuid | 标准底稿 gzip JSON 权威 projection；custom 可空 |
| `projection_sha256` | char(64) | base/current 三方 projection 身份 |
| `authoritative_artifact_id` | uuid | custom/single_onlyoffice 的权威 OOXML；标准结构化可空 |
| `authoritative_artifact_sha256` | char(64) | 与 artifact 双向校验 |
| `operation_id` | uuid | 来源操作，可空 |
| `actor_id` | uuid | 操作者 |
| `created_at` | timestamptz | immutable |

content version 不直接内嵌可漂移的 `contract_version/template_version`，也不拥有可被 upgrader 改写的标准 OOXML。标准底稿 projection 与下述 representation 1:N；custom 的 xlsx 本体可作为 authoritative artifact，但历史 row 仍不可变。

### `working_paper_sync_definition_artifact`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `kind` | varchar | `template / instrumentation / contract / authority_model` |
| `logical_id` / `semantic_version` | varchar | 人类可读 identity；非内容主键 |
| `blob_artifact_id` | uuid | FK 内容寻址不可变定义/模板 blob |
| `sha256` | char(64) | UNIQUE `(kind, sha256)` |
| `structure_hash` | char(64) | template/instrumentation 可空；authority_model/contract 由 canonical payload hash 表达 |
| `source_commit` | varchar | 创建该快照的源码提交 |
| `supersedes_id` | uuid | nullable self FK |
| `state` | varchar | `candidate / approved / retired`；历史引用不随 alias 漂移 |
| `created_at` / `approved_at` | timestamptz | 服务端时间 |

`authority_model` artifact 的 canonical payload 至少含 `schema_version / authority_model`，其中 authority model 为封闭枚举 `projection_contract / custom_authoritative_ooxml / opaque_single_onlyoffice`，并声明 content authority、merge 与可选 child 规则。registry 只把逻辑 alias 解析到 approved definition artifact；bundle、representation、forcesave request、operation、retry、resolver 和 evidence 必须保存具体 FK + digest。

### `working_paper_sync_definition_bundle`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `schema_version` | varchar | bundle canonical schema，例如 `definition-bundle:v1` |
| `authority_model_definition_id` / `authority_model_definition_sha256` | uuid/char(64) | NOT NULL FK + digest；必须 approved |
| `template_slot_type / template_slot_ref / template_slot_digest` | varchar/text/char(64) | 全部 NOT NULL；ref 为 `definition:<uuid>` 或版本化 `marker:<id>` |
| `instrumentation_slot_type / instrumentation_slot_ref / instrumentation_slot_digest` | varchar/text/char(64) | 全部 NOT NULL；`definition` 或 `instrumentation:none:v1` marker |
| `contract_slot_type / contract_slot_ref / contract_slot_digest` | varchar/text/char(64) | 全部 NOT NULL；`definition` 或 `contract:none:v1` marker |
| `canonical_payload_artifact_id` | uuid | NOT NULL FK，保存不可变 canonical bundle bytes |
| `canonical_payload_sha256` | char(64) | NOT NULL UNIQUE；亦为 `definition_bundle_sha256` |
| `state` | varchar | `candidate / approved / retired`；只有 approved 可用于 finalize/room |
| `created_at` / `approved_at` | timestamptz | 服务端时间 |

canonical payload 固定为：

```json
{
  "schema_version": "definition-bundle:v1",
  "authority_model": {"type":"definition","sha256":"<non-empty-authority-model-digest>"},
  "template": {"type":"definition","sha256":"<non-empty-template-digest>"},
  "instrumentation": {"type":"instrumentation:none:v1","sha256":"sha256(typed-marker)"},
  "contract": {"type":"contract:none:v1","sha256":"sha256(typed-marker)"}
}
```

四个 slot 均必须存在；三个 child slot 的 `type/ref/digest` 列也全部 NOT NULL。canonicalizer 对 UTF-8、键顺序、换行和 typed marker bytes 做版本化规范化；`definition:<uuid>` ref 由 DB trigger 解析并校验 artifact kind/state/digest，`marker:<id>` ref 由版本化 marker registry解析。optional child 只能使用 registry 定义的 typed null marker 及其真实 digest；字段缺失、空串、全零 hash、JSON `null` 或 SQL NULL 在 canonicalization/finalize 前即拒绝，绝不被编码为 canonical bytes。`projection_contract` bundle 必须把 template/instrumentation/contract 三个 slot 都解析为 approved `definition` child；`custom_authoritative_ooxml / opaque_single_onlyoffice` 按 authority model 规则使用明确 marker。数据库 NOT NULL/CHECK/trigger + service validator 双层锁死 child kind/state/digest，bundle approved 后不可修改或重组。

发布 DAG 固定为 `template → instrumentation → contract → bundle → representation`；authoritative model artifact 必须在 bundle 前 approved，但不允许 instrumentation 反向引用 contract 或 bundle。历史 retry 直接读取 bundle row，不按 alias 重新求值。

### `working_paper_representation_upgrade_candidate`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `wp_id / content_version_id / entry_id` | uuid/uuid/varchar | 目标业务版本与独立 entry |
| `source_representation_id` | uuid | FK immutable current/历史 representation |
| `staged_artifact_id / staged_artifact_sha256` | uuid/char(64) | 已校验但 non-current 的候选 artifact |
| `template_definition_id / instrumentation_definition_id` | uuid | 前置 upgrader 已固定 child；contract 不得伪造 |
| `target_contract_definition_id / target_definition_bundle_id` | uuid | 可空仅表示尚未批准，非 canonical null marker；finalize 前必须补齐 approved bundle |
| `state` | varchar | `staged / awaiting_contract / ready / finalized / rejected / orphaned` |
| `visible_equivalence_report_sha256 / rollback_source_sha256` | char(64) | 反读/回滚证据 |
| `created_at / finalized_at` | timestamptz | 审计 |

candidate 不是 representation：canonical resolver、config/download、room、current pointer、application substrate 与 evidence 均必须拒绝 candidate id/path。只有 per-entry contract、authority model 与 bundle 全部 approved，且 bundle/template/instrumentation 与候选 artifact compatibility 通过后，finalize 才在短事务中创建 immutable representation 并可切 entry pointer；失败只把 candidate 标 error/orphan，原 pointer/revision 不变。

### `working_paper_content_representation`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `wp_id` / `content_version_id` | uuid | FK；业务版本不变时允许多个 representation |
| `entry_id` | varchar | manifest 稳定 entry |
| `generation` | bigint | UNIQUE `(wp_id, entry_id, content_version_id, generation)` |
| `parent_representation_id` | uuid | nullable self FK |
| `document_type` | varchar | `xlsx / docx` |
| `artifact_id` / `artifact_sha256` | uuid/char(64) | 已发布 canonical OOXML |
| `definition_bundle_id` / `definition_bundle_sha256` | uuid/char(64) | NOT NULL approved bundle FK + digest |
| `authority_model_definition_id` / `authority_model_definition_sha256` | uuid/char(64) | NOT NULL，与 bundle child 双向锁死 |
| `adapter_id` / `adapter_build_digest` | varchar/char(64) | 代码实现身份 |
| `structure_hash` / `identity_inventory_sha256` | char(64) | roundtrip/载体身份 |
| `reason` | varchar | `content_commit / definition_upgrade / rollback / rematerialize` |
| `created_at` | timestamptz | immutable |

representation 只能由 approved bundle finalize。数据库触发器/约束与 service validator 必须同时拒绝 candidate bundle、digest 不一致以及 `projection_contract` bundle 的 missing/unapproved/typed-null contract child；custom/opaque 则按 authoritative model 明确接受相应 marker。representation 与 bundle 均不可原地更新。

### `working_paper_sync_entry_state`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `wp_id` / `entry_id` | uuid/varchar | 复合 PK |
| `current_representation_id` | uuid | FK published representation；candidate 不可引用 |
| `representation_generation` | bigint | 与 pointer 同事务推进，不改变 content revision |
| `updated_at` | timestamptz | 审计 |

同一业务 revision 的纯 instrumentation/template/contract/bundle 升级只在 DAG 完成后新增 representation 并切换 entry pointer；绝不更新旧 content version/representation。

### `working_paper_artifact`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `project_id` / `wp_id` | uuid | 路径与权限边界 |
| `kind` | varchar | `canonical / upgrade_candidate / incoming / projection / definition / template / evidence / trace_bundle` |
| `state` | varchar | `staged / durable / candidate / published / orphan / quarantined / deleted`；kind/state CHECK 强制 incoming 永不 published/current/resolvable |
| `relative_path` | text | 项目根内不可变路径 |
| `sha256` / `size_bytes` | char(64)/bigint | 内容身份/预算 |
| `document_type` | varchar | xlsx/docx/json.gz |
| `retention_class` | varchar | 清理与 legal hold |
| `source_delivery_id` / `created_by_operation_id` | uuid | 来源 FK，均可空但 incoming 至少有 delivery；recovery incoming 不要求 operation |
| `durable_at` / `quarantined_at` / `published_at` / `orphaned_at` / `deleted_at` | timestamptz | 生命周期；incoming durable与quarantined互斥，quarantined保持`durable_at=NULL` |

artifact 先在文件系统写入/校验，再登记或引用。incoming 只允许安全校验成功的 `staged → durable`，或失败的 `staged → quarantined → orphan/deleted`；两支不可互转。`.incoming` rename 叫 durable sealing，不叫 canonical publish，resolver永不返回incoming。只有`state=durable`的incoming可创建application或供extract/merge/retry/rematerialize读取；quarantined只允许authorization-first download-only、expire、retention/legal-hold，永不release、转durable、创建application或进入engine。只有新生成的canonical result representation可在verifier/eligibility通过后`staged → published`。DB rollback后没有current/version引用的artifact由reconciliation标记orphan，GC只删除超过grace且二次确认无引用的对象。

### `working_paper_sync_scope_index`

这是 authorization-only、非敏感且不可作为业务读取替代品的归属索引：

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `resource_kind / resource_id` | varchar/text | 复合 PK；canonical text id只支持不可变 opaque identity（UUID/doc_key等），覆盖 room/participant/confirmation/request/close-intent/delivery/application/operation/recovery/conflict/version 等用户可寻址 child；version 必须使用 `working_paper_content_version.id` UUID，numeric revision 禁止作resource_id |
| `project_id / wp_id / entry_id` | uuid/uuid/varchar | NOT NULL，用户路由显式 scope 的比对真源 |
| `room_id / generation` | uuid/integer | 适用时非空；只表达归属，不表达业务状态 |
| `created_at / retired_at` | timestamptz | 与 child 同事务创建；retired 仍保留防 id 重用 |

index 禁止保存 payload、业务状态、hash、错误、候选摘要或 authorization result。每个 child 与 scope row 必须同事务创建或退役，trigger/repository 校验 immutable scope 与 FK scope 一致；child 退役只设置 `retired_at`，tombstone 永不物理删除/清空，`(resource_kind,resource_id)` 永不跨 scope或同 scope复用，DELETE/复用尝试必须失败。用户 guard 只能先读该 index 与项目授权关系；scope/visibility 通过前不得读 child、artifact、cache 或幂等结果，retired id与不存在 id走同一 404 oracle但 tombstone仍参与防复用。

### `working_paper_oo_room`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `wp_id` | uuid | FK/索引 |
| `entry_id` | varchar | manifest 稳定入口 |
| `doc_key` | varchar | UNIQUE，传给 OO |
| `generation` | integer | UNIQUE `(wp_id, entry_id, generation)` |
| `opened_base_version_id` | uuid | room 初始 content version FK |
| `last_applied_version_id` | uuid | 服务器最近 applied business version |
| `client_confirmed_base_version_id` | uuid | live editor 已加载确认的 merge base |
| `client_confirmed_representation_id` | uuid | editor 当前 published artifact identity |
| `client_confirmed_definition_bundle_id / sha256` | uuid/char(64) | editor 实际确认的非空 bundle；与 representation 双向锁死 |
| `client_confirmed_projection_sha256` | char(64) | 防止只按 revision 猜客户端内容 |
| `latest_request_sequence` / `latest_durable_sequence` | bigint | generation 内单调 fence；同 application fold也推进 |
| `latest_durable_application_id` | uuid | nullable FK；与 latest durable sequence原子更新，resolve先比canonical application再比effective sequence |
| `write_fence_epoch` | bigint | participant/权限/代际变化即推进 |
| `close_barrier_epoch` | bigint | close intent 创建时单调推进；同 generation barrier identity |
| `close_leader_intent_id` | uuid | nullable FK；按最高`(intent_sequence,id)`写入；只可在promotion前且eligibility epoch变化时审计替换为合法successor |
| `close_leader_eligibility_epoch / digest` | bigint/char(64) | 冻结leader候选资格；同snapshot重放不得换leader |
| `state` | varchar | 含 `active/close_barrier/closing/refresh_required/superseded/...`；close barrier 后拒绝新 participant |
| `refresh_required_at` / `refresh_reason` | timestamptz/varchar | merged≠incoming 等原因 |
| `expires_at` | timestamptz | room TTL |
| `superseded_at` / `closed_at` | timestamptz | 生命周期 |
| `created_at` / `updated_at` | timestamptz | 审计 |

room 不保存单一 `user_id/permission_epoch/mode`。application commit 只无条件推进 `last_applied_version_id`；`client_confirmed_*`（含 representation/bundle）仅在 managed projection 等值或 editor ack 新 descriptor 时推进。二者不等或 bundle 变化未确认时 room=`refresh_required`，后续 request 在 Command Service 前被拒绝。

### `working_paper_oo_participant`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `room_id` / `user_id` | uuid | FK；UNIQUE active lease `(room_id,user_id)` |
| `mode` | varchar | `edit/view` |
| `state` | varchar | `active / closing / left / revoked / expired`；close intent 与 `active→closing` 必须同一 room-lock 事务 |
| `permission_epoch` | bigint | 打开时授权快照，每次用户命令和最终 commit 重验 |
| `joined_write_fence_epoch` | bigint | 加入时 room fence |
| `lease_token_hash` | char(64) | 仅存短期 token hash |
| `expires_at` | timestamptz | participant TTL |
| `revoked_at` / `left_at` / `oo_drop_confirmed_at` | timestamptz | 逐用户撤销/离开/drop 证据 |
| `created_at` / `updated_at` | timestamptz | 审计 |

### `working_paper_oo_client_confirmation`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `room_id / participant_id / generation` | uuid/uuid/integer | UNIQUE active confirmation |
| `doc_key / representation_id / artifact_sha256` | varchar/uuid/char(64) | descriptor identity |
| `content_version_id / projection_sha256` | uuid/char(64) | confirmed client base |
| `definition_bundle_id / definition_bundle_sha256` | uuid/char(64) | NOT NULL，固定 descriptor 的 approved bundle |
| `authority_model_definition_sha256 / bundle_slots_digest` | char(64) | 固定 authority model 与 typed child inventory |
| `write_fence_epoch` | bigint | stale descriptor 防线 |
| `idempotency_key` | varchar | 重复 `onDocumentReady` 返回同 confirmation |
| `confirmed_at / invalidated_at` | timestamptz | append-only event 同步记录 |

DocEditor `onDocumentReady` 后调用 confirmation API。服务端仅在 room/generation/doc_key、participant lease、representation/artifact、approved definition bundle/authority model 与 write fence 全匹配时写 confirmation；stale generation、bundle 或已推进 pointer 返回 409。room 首个有效 edit confirmation 才从 opening/refresh-required successor 进入 active；任何 participant 发起 forcesave 前必须有同 generation、同 bundle confirmation。

### `working_paper_forcesave_request`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK，服务端 request id/userdata |
| `room_id` / `generation` | uuid/integer | FK 与代际绑定 |
| `request_sequence` | bigint | UNIQUE `(room_id,generation,request_sequence)` |
| `kind` | varchar | `forcesave / close_capture / recovery_claim`；recovery_claim 不调用 Command Service |
| `initiated_by_participant_id` | uuid NOT NULL | 用户命令发起者；forcesave 须为 active confirmed edit participant，close-capture 须引用 intent 创建时已确认且现为 deterministic closing leader 的 participant |
| `initiator_permission_epoch` | bigint NOT NULL | accepted 前冻结；forcesave/close-capture 均不可缺失 |
| `client_edit_epoch` / `write_fence_epoch` | bigint | callback/application authorization fence |
| `client_base_version_id` / `client_base_representation_id` | uuid | 从 client-confirmed 指针冻结 |
| `client_base_projection_sha256` | char(64) | merge base 内容身份 |
| `definition_bundle_id / definition_bundle_sha256` | uuid/char(64) | NOT NULL approved bundle FK；历史 retry 原样使用 |
| `authority_model_definition_id / authority_model_definition_sha256` | uuid/char(64) | NOT NULL，必须与 bundle child 一致 |
| `adapter_build_digest` | char(64) | 代码 identity |
| `contributor_snapshot_digest` | char(64) | accepted/close intent 时 active writer set |
| `idempotency_key` | varchar | UNIQUE `(room_id,generation,initiated_by_participant_id,kind,idempotency_key)` |
| `frozen_request_fingerprint` | char(64) | canonical hash of confirmation/base/representation/bundle/fence/contributors；cache hit必须逐项等值 |
| `state` | varchar | `frozen/pending/accepted/correlated/terminal/rejected/unmatched/superseded` |
| `accepted_at` / `finished_at` | timestamptz | 服务端时钟 |

Command Service调用前，在一个事务中插入request、从已确认representation冻结非空approved definition bundle/authority model并计算`frozen_request_fingerprint`，同时创建`application_id=NULL`的operation shell；Command rejected/timeout也由该shell留痕。任何Idempotency-Key lookup都在authorization-first之后，并以`(room,generation,initiator,kind,key)`定位；只有initiator/kind及frozen fingerprint逐项一致才返回旧request/operation，不同payload或另一participant复用同key一律409且不得返回旧标识。clean close 先建 intent并把 participant 转 `closing`；仅 `reconcile_close_intents()` 可在 barrier predecessors 安全终结后把 deterministic leader 提升为唯一 open `close_capture`。浏览器崩溃或 OO 自发 close 没有该 request 时 incoming 绑定 recovery case，不能借 route identity 应用或预建 operation。callback 只读取已冻结字段；status=2 无 userdata 优先匹配唯一 open close-capture；不存在 eligible request 时，仅当同 incoming application 的 frozen identity（含 bundle）唯一且不存在 sequence 更高 request 才允许 delivery 去重。recovery claim 只有在 authorization-first 校验通过后，才在同一事务创建 `kind=recovery_claim` request 与 operation shell，并创建或命中 application；commit 前 shell 必须收敛为绑定 application 的 primary，或保持 `application_id=NULL` 并成为直指 canonical primary 的 terminal duplicate，case/delivery 指向同一 canonical application，且不调用 Command Service。

### `working_paper_oo_close_intent`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `room_id / generation / participant_id` | uuid/integer/uuid | FK；UNIQUE active `(room_id,generation,participant_id)` |
| `client_confirmation_id` | uuid | FK prior confirmed descriptor |
| `intent_sequence / barrier_epoch` | bigint | room 内单调；创建 intent 时同时推进 room barrier |
| `ordinary_forcesave_request_id` | uuid | nullable FK；非 leader/先关闭 participant 的 barrier predecessor |
| `state` | varchar | `created / ordinary_forcesaving / waiting_barrier / leader_ready / promoted / retryable_blocked / authorization_stale / successor_selected / recovery_required / superseded / error` |
| `promoted_request_id` | uuid | nullable FK；仅 room `close_leader_intent_id` 可由 reconciler CAS 写入 |
| `created_at / reconciled_at / finished_at` | timestamptz | 服务端时钟 |

intent 创建事务先锁 room并把 participant `active→closing`，因此后续 intent 看不到已 closing participant 作为 active。active首次归零时按最高`(intent_sequence,id)`与eligibility snapshot写deterministic leader，close barrier后禁止新participant加入。非leader intent驱动ordinary forcesave；leader等待所有barrier predecessor达terminal/superseded-safe。`reconcile_close_intents()`在intent创建、ordinary request terminal、leave/error/revoke/expire后再次持room lock并幂等检查。leader若在promotion前失去当前编辑授权/lease，则旧intent先写`authorization_stale` event，room eligibility epoch递增，并从仍合法intents按同一comparator选successor；同一eligibility digest重放不可换leader。存在successor且predecessors安全时CAS创建冻结successor confirmation/bundle的`close_capture` request并写`promoted_request_id`。无合法successor时不建request，原子supersede generation、将未终结intents置`recovery_required`并保留已有durable artifact/application供重新授权的新generation恢复；不得留永久blocked或system initiator。已promoted后授权失效由最终fence终结唯一request/application为authorization_stale并走recovery，不得再选successor。`working_paper_forcesave_request`对`(room_id,generation) WHERE kind='close_capture' AND state IN (...)`建partial unique只保证at-most-one；合法资格的single/two-user交错证明exactly-one，revoke/expire交错证明successor/no-successor两种可达终态。失败事务不得留下半个promoted intent/request。

### `working_paper_callback_recovery_case`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `room_id / generation` | uuid/integer | room/generation FK |
| `source_delivery_key / incoming_artifact_id` | char(64)/uuid | UNIQUE delivery identity + durable incoming FK |
| `reason` | varchar | `missing_request / ambiguous_close / crash_close / stale_candidate` |
| `candidate_confirmation_digest` | char(64) | 同 generation prior confirmations 的确定性候选摘要 |
| `candidate_contributor_digest` | char(64) | 可审计 contributor 候选 |
| `state` | varchar | `unclaimed / claiming / application_created / download_only / quarantined / expired`；不得停在 claimed-without-operation |
| `claimed_by_participant_id / prior_confirmation_id` | uuid | claim 后绑定当前有权 participant 与合法 confirmed descriptor |
| `recovery_request_id / application_id / operation_id` | uuid | claim 成功事务一次性写入；claim 前与 download-only 永远为空 |
| `claimed_definition_bundle_id / claimed_definition_bundle_sha256` | uuid/char(64) | claim 成功后冻结的非空 bundle |
| `idempotency_key` | varchar | claim UNIQUE，缓存命中仍须 authorization-first |
| `expires_at / created_at / claimed_at` | timestamptz | retention/审计 |

unmatched/ambiguous delivery 的 `operation_id/application_id/recovery_request_id` 在 claim 前全部保持空，但 `callback_recovery_case_id` 必须非空。claim API 只接受当前有权用户，先用显式 project/wp/entry/room 与 `working_paper_sync_scope_index` 完成 authorization-before-business-read，再引用同 room/generation 的 prior `working_paper_oo_client_confirmation`；随后在 room/case row lock 下校验 confirmation 的 base/representation/approved bundle、generation/write fence 与 contributors。全部通过后，在一个事务中创建唯一`recovery_claim` request与operation shell并创建/命中`working_paper_content_application`；新application时shell绑定为primary，命中已绑定application时shell原子成为direct terminal duplicate，operation/delivery/case均记录同一canonical application关系并推进case=`application_created`。不得出现claimed-without-application、stranded nullable shell或duplicate链/环。Idempotency-Key 命中前仍须重复当前 scope/auth/fence 校验。错误 prior confirmation、bundle、fence、未知/撤权 contributor 或 superseded generation 均不得创建三者，只能保持可诊断、转 download-only 或 quarantined。download-only 只记录 actor/authorization/artifact access 与 case terminal event，永不创建 request/application/operation；因此无 operation 的 case 不能调用普通 `retryOperation()`。

`working_paper_callback_recovery_case_event` 以 `(case_id, sequence_no)` 唯一记录 `from_state / to_state / actor / authorization_result / prior_confirmation_id / definition_bundle_sha256 / error_code / occurred_at`。case 创建、claim 尝试/拒绝/成功、download-only、quarantine/expire 都先写 append-only event 再更新 state；它与 operation timeline 分离，确保 claim 前零 operation 仍可形成 evidence。

### `working_paper_content_application`

这是 durable incoming 对业务状态的一次逻辑应用，也是 frozen idempotency identity 的唯一 owner：

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `project_id / wp_id / entry_id / room_id / generation` | uuid/uuid/varchar/uuid/integer | NOT NULL scope；与 scope index/request/delivery/operation 双向校验 |
| `origin_request_id` | uuid | NOT NULL FK forcesave/recovery-claim request；同 application 唯一 origin |
| `application_key` | char(64) | UNIQUE；来自 frozen request + durable incoming，不含 callback status/request id |
| `client_edit_epoch / origin_request_sequence` | bigint | origin sequence不可变；与origin request一致 |
| `effective_request_sequence` | bigint | 只能`GREATEST`单调提升；折叠同application的后续request |
| `base_version_id / base_representation_id` | uuid | request 冻结的 client-confirmed base |
| `current_revision / result_revision` | bigint | 三方/current 与逻辑结果业务版本 |
| `incoming_artifact_id` | uuid | NOT NULL，`kind=incoming,state=durable`；quarantined FK被CHECK/trigger拒绝，永不published |
| `incoming_sha256 / incoming_projection_sha256` | char(64) | incoming 文件/受管 projection 身份 |
| `merged_projection_sha256` | char(64) | merge 身份 |
| `result_representation_id / result_artifact_sha256` | uuid/char(64) | verifier/eligibility 后发布的独立 canonical result，不等于 incoming |
| `definition_bundle_id / definition_bundle_sha256` | uuid/char(64) | NOT NULL frozen bundle |
| `authority_model_definition_id / authority_model_definition_sha256` | uuid/char(64) | NOT NULL，与 bundle child 双向锁死 |
| `adapter_id / adapter_build_digest` | varchar/char(64) | 解析实现身份 |
| `contributor_snapshot_digest` | char(64) | 多人贡献授权快照 |
| `conflict_count / conflict_set_digest` | integer/char(64) | 默认 0/可空 |
| `state` | varchar | `queued/validating/extracting/merging/conflict/rematerializing/applying/applied/refresh_required/error/superseded` |
| `superseded_by_application_id` | uuid | 较新 full snapshot supersede |
| `logical_result_code` | varchar | terminal 结果；与 operation timeline projection 一致 |
| `created_at / durable_at / finished_at` | timestamptz | 服务端时钟 |

identity 列从 `application_key` 到 adapter/bundle/incoming 均不可变；只有 state/result/supersede/timestamps 按允许边更新。application key 只使用 forcesave/recovery-claim request 已冻结的值与 durable incoming：

```text
sha256(wp_id | room_id | generation | frozen_client_base_version_id |
       frozen_client_base_representation_id | incoming_sha256 |
       definition_bundle_sha256 | authority_model_definition_sha256 |
       adapter_build_digest)
```

`definition_bundle_sha256` 与 authority model digest 必须为真实非空 digest；可选 instrumentation/contract 的缺省已作为 bundle canonical bytes 内的 typed null marker 固定，不以 SQL NULL、空串或全零 hash参与 key。key 不含 callback status、request id、request sequence或callback到达时的room pointer。归组顺序固定为request-first：payload有`userdata/request_id`时先校验并绑定frozen request，incoming durable后计算完整key才查询application；相同key的status 6/2、乱序和网络重试返回同一application。首个winner写immutable `origin_request_sequence`；不同request已各自创建shell时，唯一winner绑定application，其余shell在锁定primary后原子执行`effective_request_sequence=GREATEST(existing,request_sequence)`、更新room `latest_durable_application_id/latest_durable_sequence`并终结为direct duplicate。sequence fold写append-only event，不能修改origin、不能把同canonical application的primary/conflict标superseded。仅status 2无userdata可先找唯一eligible close-capture；不存在eligible request时，才允许按incoming找到frozen identity完全唯一且没有更高**不同canonical application**的既有application。相同incoming但frozen base、representation、bundle或authority model不同必须得到不同key，候选不唯一即`ambiguous/unmatched`并创建零operation recovery case。

### `working_paper_sync_operation`

operation 是用户轮询/执行/timeline 容器，不再承担 application identity：

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK，亦作 correlation id |
| `project_id / wp_id / entry_id / room_id` | uuid/uuid/varchar/uuid | scope FK/索引 |
| `forcesave_request_id` | uuid | nullable FK；正常/recovery OO→HTML 非空且每 request 最多一个 shell，HTML/rollback 可空 |
| `application_id` | uuid | nullable UNIQUE FK；normal accepted shell 初始为空；winner primary 在 durable correlation 后绑定，duplicate 永远为空；recovery claim commit 后必须成为 primary或 terminal duplicate |
| `duplicate_of_operation_id` | uuid | nullable self FK；仅 terminal duplicate 非空，必须直指同 scope/bundle且已绑定 application的 primary，禁止 self/链/环 |
| `initiated_by_participant_id` | uuid | 可空；不是聚合 artifact 唯一作者 |
| `direction` | varchar | `html_to_oo / oo_to_html / conflict_resolution / rollback` |
| `state` | varchar | `created/command_pending/accepted/waiting_application/application_bound/duplicate/...terminal` 的执行投影；duplicate 必为 terminal |
| `definition_bundle_id / definition_bundle_sha256` | uuid/char(64) | NOT NULL；pre-bind 与 request 一致，post-bind 还须与 application 一致 |
| `authority_model_definition_id / authority_model_definition_sha256` | uuid/char(64) | NOT NULL，同上 |
| `error_code / error_stage / error_detail` | text | fail-visible，detail 经脱敏 |
| `accepted_at / application_bound_at / finished_at` | timestamptz | 阶段时延 |
| `created_by` | uuid | 发起者/系统 |

正常 forcesave 冻结 request 时同事务创建 shell，accepted API 因而可立即返回 `operation_id`；此时 `application_id=NULL AND duplicate_of_operation_id=NULL` 是合法 pre-correlation 状态。durable correlation 以 application key锁定 application及其 primary：winner 在一个事务中写 `operation.application_id`、`delivery.application_id` 与 `application_bound` event；loser 保持 application为空并写 `duplicate_of_operation_id=<primary>`、`state=duplicate` 与 terminal event，delivery绑定同一 application。CHECK/deferred trigger 强制 primary为 `application_id IS NOT NULL AND duplicate_of IS NULL`，duplicate为 `application_id IS NULL AND duplicate_of IS NOT NULL`，目标必须同 scope/frozen bundle且已绑定该 application；禁止 self、duplicate→duplicate、链、环与 stranded durable `waiting_application`。普通 GET/timeline/conflict/retry/resolve先授权当前 operation，再把 duplicate直接规范化到 primary并复用其 timeline/result，不创建第二 operation/application。recovery claim 前没有 shell；claim 成功事务创建 request+shell并创建/命中 application，commit前将 shell落为 primary或terminal duplicate，download-only 三者恒无。数据库 CHECK/trigger 禁止 operation 保存 `application_key` 或复制 incoming identity作为幂等真源。

### `working_paper_callback_delivery`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | uuid | PK |
| `project_id / wp_id / entry_id / room_id / generation` | uuid/uuid/varchar/uuid/integer | scope；与 scope index 双向锁死 |
| `operation_id / application_id` | uuid | nullable FK/索引；正常 pre-correlation 可只有 shell；durable correlated 后 application非空，operation可为绑定它的primary或直指该primary的terminal duplicate |
| `forcesave_request_id` | uuid | 成功 request-first correlation 后 FK，可与 application 同时存在 |
| `callback_recovery_case_id` | uuid | unmatched/ambiguous durable 时非空，此时 request/application/operation 全空 |
| `route_credential_id` | uuid | room/generation callback route；不是用户作者 |
| `callback_status` | integer | OO 原始状态 |
| `delivery_key` | char(64) | UNIQUE；含 status 与 OO/userdata discriminator |
| `state` | varchar | `received/downloading/durable/acknowledged/rejected/error/unmatched` |
| `payload_sha256` / `oo_users_digest` | char(64) | 不保存敏感原文；记录聚合 contributor signal |
| `correlation_result` | varchar | `request / existing_application / close_capture / unmatched / ambiguous` |
| `incoming_artifact_id` | uuid | durable 后绑定，可空；必须是 non-published incoming |
| `response_error` | integer | 返回 OO 的 error |
| `received_at` / `durable_at` / `responded_at` | timestamptz | timeline |

CHECK + deferred trigger 以 `durable_at` 而非泛化 terminal 约束阶段性归属：`durable_at IS NULL` 的 `received/downloading/rejected/error` 可零 application/recovery owner（可保留已精确绑定的 request/operation），但任何状态都禁止双 owner；`durable_at IS NOT NULL` 的 correlated row 必须 `application_id IS NOT NULL AND callback_recovery_case_id IS NULL`，request 可同时非空，若 operation为primary则 `operation.application_id=delivery.application_id`，若为duplicate则其 direct primary 的 application等于delivery；unmatched/ambiguous row必须 recovery case非空且 request/application/operation全空，post-durable error保留原owner。application ownership 与 recovery ownership 是 XOR，request 与 application 不是 XOR。所有 FK/duplicate canonical link还须通过 scope index 验证 project/wp/entry/room/generation 相同。

### `working_paper_sync_operation_contributor`

| 列 | 类型 | 说明 |
|---|---|---|
| `operation_id` / `participant_id` | uuid | 复合 PK/FK |
| `user_id` / `permission_epoch` | uuid/bigint | application 最终授权重验 |
| `source` | varchar | `request_initiator / oo_users / active_writer_snapshot` |
| `confidence` | varchar | `exact / aggregate / unknown` |

若 contributor 只能 aggregate/unknown 且 generation 内有被撤销 writer，安全策略是不应用并旋转 generation，而不是把 route participant 当作者。

### `working_paper_sync_operation_event`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | bigint | PK，单调序列 |
| `operation_id` | uuid | FK/索引 |
| `sequence_no` | integer | UNIQUE `(operation_id, sequence_no)` |
| `from_state` / `to_state` | varchar | 允许边 |
| `stage` / `error_code` | varchar | 诊断 |
| `actor_type` / `actor_id` | varchar/uuid | user/system/callback |
| `detail_digest` | char(64) | 敏感详情摘要 |
| `occurred_at` | timestamptz | 服务端时间 |

### `working_paper_sync_conflict`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid | PK |
| `operation_id` | uuid | FK/索引 |
| `client_edit_epoch` / `canonical_application_id` / `effective_request_sequence` | bigint/uuid/bigint | resolve room latest-durable canonical application fence |
| `stable_field_key` | varchar | adapter 全局稳定键 |
| `sheet_key` / `table_key` / `row_key` | varchar | UI 分组 |
| `json_pointer` / `oo_location` | text | 双侧溯源 |
| `conflict_kind` | varchar | `value / protected / delete_update / schema / duplicate_word_instance` |
| `base_value` / `current_value` / `incoming_value` | jsonb | 三方值 |
| `resolution` / `resolved_value` | jsonb | 选择与合并值 |
| `resolved_by` / `resolved_at` | uuid/timestamptz | 审计 |

`UNIQUE(operation_id, stable_field_key, row_key, oo_location)` 防重复 callback 生成重复冲突。较新 durable incoming sequence 到达时，旧 operation/conflict 标记 superseded；旧 resolve 不能跨 sequence 生效。

### `working_paper_sync_test_run` / `working_paper_entry_evidence_scenario`

`sync_test_run` 是一次可复现验收执行，不是 manifest 中的自由文本：

| `working_paper_sync_test_run` 列 | 说明 |
|---|---|
| `id / entry_id / source_commit / runner_version` | 运行与代码身份 |
| `manifest_source_digest / editability / room_model / scenario_profile_digest` | source-backed scenario capability identity；禁止自由文本覆写 |
| `onlyoffice_build / browser_build / environment_digest` | 黑盒环境 |
| `required_scenario_set_digest` | 从 manifest profile + entry capability + approved immutable definition bundle + authoritative model 服务端推导 |
| `authority_model_definition_sha256 / definition_bundle_sha256` | 本次 run 固定的非空 identity；与每条 scenario 双向校验 |
| `started_at / finished_at / aggregate_result` | 服务端时间与结果 |
| `run_manifest_artifact_id / sha256` | immutable run manifest |

每个 `working_paper_entry_evidence_scenario` 保存 `run_id / scenario_id / ordinal / result / operation_ids / application_ids / recovery_case_ids / content_version_ids / representation_ids / authority_model_definition_sha256 / definition_bundle_sha256 / trace_bundle_artifact_id + sha256 / server_timeline_digest / database_snapshot_digest / error_code`，并以 `UNIQUE(run_id,scenario_id,ordinal)` 防替换。trace bundle 包含经 RedactionPolicy 过滤的浏览器 network/console、服务端 operation/application/recovery timeline 范围、artifact inventory 与 oracle 输出。允许 recovery reject/download-only 场景的 `operation_ids=[]/application_ids=[]`，但必须有 recovery case 与零三实体 oracle；normal accepted 场景须先证明 operation shell 的 application id 为空，correlation 后再证明 operation/application 一对一；其他需要 application 的场景两者均不得为空。

服务端 evidence recomputer 不信任写入的 aggregate result：它从 source-backed `editable/room_model/scenario_profile + capability + immutable definition bundle + authoritative model` 推导 required scenario set，并验证 manifest/profile digest、bundle typed child inventory 与 representation/application/operation 固定 identity 相同。所有 projection-based bidirectional entry 无条件要求 HTML→OO、OO→HTML、identity、different-field merge、same-field conflict/resolve、frozen dedupe、no-userdata browser-crash recovery claim、错误 prior confirmation/fence/contributor 拒绝、download-only 零 operation/application、refresh/reopen、rollback；dynamic/Word-only 再追加相应场景。凡 `editable=true AND (capability=bidirectional OR room_model=shared)` 均无条件追加 single participant、两个用户两种关闭顺序、A ordinary forcesave terminal 前/后 B close、barrier reconcile 与最终 exactly-one close-capture；不得以“未标 multi-user”跳过。`custom_authoritative_ooxml/opaque_single_onlyoffice` 只能由 bundle 中的枚举 authority model 把两条字段级场景替换为 authoritative artifact revision conflict/no-silent-overwrite，不能替换 close/recovery/authorization 场景，也不接受自由文本豁免。recomputer 逐行重读 recovery case、application、operation/version/representation/bundle/definition/artifact/timeline 外键并重算 hash、时序与 stale 状态，最后生成 manifest evidence summary。缺场景、profile/bundle 不一致、同一 application/operation 被跨 scenario/entry 非法复用、download-only 出现三实体、close 最终为 0 或 >1、trace bundle 不可读或环境 digest 变化均返回 unverified。

### outbox

不新建第二套事件表。抽取通用 `DurableEventOutboxService` facade，底层复用现有 `ImportEventOutbox`/DLQ 能力；保留旧 service 作为兼容门面。新增事件类型 `workpaper.content.updated`，payload：

```json
{
  "wp_id": "uuid",
  "project_id": "uuid",
  "revision": 12,
  "operation_id": "uuid",
  "source": "onlyoffice",
  "adapter_id": "g7.disclosure.listed",
  "file_sha256": "..."
}
```

outbox enqueue 与 content commit 同事务；publish/replay 在事务提交后执行。typed Redis replay 必须原样保留 payload，而非丢弃 `extra`。

## Filesystem Layout 与发布协议

```text
storage/{project_id}/workpapers/
  .staging/{wp_id}/{artifact_stage_id}/
    artifact.tmp
    projection.json.gz.tmp
  .upgrade-candidates/{wp_id}/{candidate_id}/
    artifact-{sha12}.candidate.ooxml
    equivalence-{sha12}.json
  .versions/{wp_id}/
    content/000000001-{projectionSha12}.projection.json.gz
    representations/{entry_id}/000000003-{artifactSha12}.xlsx
  .incoming/{wp_id}/{delivery_id}/
    callback-{sha12}.xlsx
  .evidence/{entry_id}/{test_run_id}/
    scenarios/{scenario_id}-{traceSha12}.trace.json.gz
    evidence.json
  {wp_code}.xlsx              # 可选兼容 copy，不是版本真源

definition_store/
  templates/{sha256}.ooxml
  instrumentation/{sha256}.json
  contracts/{sha256}.json
  authority-models/{sha256}.json
  bundles/{sha256}.json
```

发布步骤是可恢复协议，不是跨介质 ACID：

1. 在项目同卷 `.staging/{artifact_stage_id}` 流式写入，计算 hash、fsync 并执行安全/roundtrip 校验；staging identity 不依赖 operation，因此 unmatched recovery 也可先耐久。upgrader 在 per-entry approved contract/bundle 前只能移动到 `.upgrade-candidates` 并登记 non-current candidate。
2. incoming 通过以 delivery id + content hash 命名的 `os.replace` 封入不可变 `.incoming`。安全校验全通过才写`state=durable,durable_at!=NULL`；失败分支写`state=quarantined,quarantined_at!=NULL,durable_at=NULL`，两者不可互转。该动作仅叫 durable sealing/quarantine，不叫 publish、不可进 resolver；quarantined只可download-only/expire/retention，永不创建application或进入engine。canonical result/candidate使用独立content-addressed名称；candidate只有在`template → instrumentation → contract → approved bundle`全部完成后才可finalize到`.versions`。
3. 对 OO→HTML，只以 application固定的`state=durable` incoming为只读substrate生成新的staged result；frozen-bundle extract等值、未管理区、安全、最终authorization/eligibility全通过后，开启短DB事务写content version/revision、published result representation（强制非空approved bundle）、entry pointer/outbox/application result与server last-applied，并按等值判据推进client-confirmed或标refresh-required。quarantined incoming在本步骤前即被拒绝，不能extract/merge/rematerialize。纯definition upgrade在candidate finalize后只写新representation/entry pointer/outbox。事务内禁止远程下载或OOXML大解析。
4. commit 后只有 published canonical/result representation 对 resolver 可见；incoming 与 candidate 永不属于 resolver namespace，也不得被原地晋升。rollback 后 reconciliation 将无引用文件标 orphan。
5. candidate/orphan/trace/incoming GC 按版本化 RetentionPolicy 等待 configurable grace，二次扫描 DB/进行中 application/operation/recovery/legal hold 后删除并写审计事件；dry-run 和删除清单均持久化。

所有目录必须 resolve 后仍在项目根内。Windows 文件占用返回 `FILE_IN_USE`；content/representation pointers 与 room 的 server last-applied/client-confirmed baselines 不变。Word 使用同布局，仅扩展名不同。

## Components and Interfaces

### Backend package

新建 `backend/app/services/workpaper_sync/`：

| 模块 | 责任 |
|---|---|
| `models.py` | domain enum、状态转换、DTO；不放 ORM |
| `repository.py` | wp lock、scope-index、room/participant/version/delivery/application/operation/event/conflict CRUD；child 与 scope row 同事务；只 flush 不 commit |
| `scope_authorization.py` | 显式 project/wp/entry scope 解析、authorization-only index lookup、统一 404/403 与 action/workflow guard；禁止预读业务资源/cache |
| `artifacts.py` | staging、incoming durable sealing、path/hash、安全校验、canonical immutable publish、orphan reconciliation/GC |
| `content_mutation.py` | 所有 writer 的唯一 business revision/version/pointer/outbox 提交边界；单次发布 projection+representation |
| `representations.py` / `definitions.py` | content version 1:N representation、immutable template/instrumentation/contract/authority-model artifacts、typed definition bundle、candidate finalize 守卫 |
| `writer_inventory.py` | HTML/upload/WOPI/OO/custom writer 与 resolver 迁移清册 |
| `room_service.py` | create/reuse/supersede room、participant lease、doc_key、server/client bases、generation write fence、close barrier/leader 与 `reconcile_close_intents()` |
| `forcesave_requests.py` | Command 前原子冻结 request + nullable-application operation shell；close leader/recovery claim 使用各自原子协议 |
| `onlyoffice_command.py` | Command Service forcesave/JWT/timeout/错误归类 |
| `callback_delivery.py` | room route claim/SSRF/stream download/delivery 去重/durable ack/request-first correlation；durable 后 application 或 recovery 二选一 |
| `recovery.py` | recovery case、authorization-first claim 原子创建 request + operation shell并创建/命中 application、commit 前收敛 primary/direct terminal duplicate、download-only 零三实体 |
| `application_service.py` | application-owned frozen key/identity、shell binding、incoming sequence/supersede、extract/merge/rematerialize/final auth/同 operation retry |
| `merge.py` | 文档无关 stable field 三方 merge |
| `coordinator.py` | HTML→OO、OO→HTML、resolve、rollback 编排 |
| `outbox.py` | durable outbox facade；handler 不递增 revision |
| `manifest.py` / `evidence.py` | 入口清册、test-run/scenario/trace bundle、服务端重算与新鲜度 |
| `retention.py` | 版本化 retention class、legal hold、dry-run、引用复核与删除审计 |
| `redaction.py` / `alerts.py` | 字段 allowlist 脱敏策略与版本化阈值/窗口/runbook 规则 |
| `contracts.py` / `definition_bundles.py` | immutable contract/authority-model schema/hash、typed null marker canonicalization、bundle compatibility 与 approved-child 守卫 |
| `template_instrumentation.py` | Excel identity/Word SDT probe、instrument、versioned upgrader 与 non-current candidate 生成 |
| `adapters/base.py` / `registry.py` | adapter protocol、fail-closed registry |
| `excel/` | identity-aware materialize/extract、结构保护 |
| `word/` | tagged SDT materialize/extract/保留校验 |

现有 `wp_onlyoffice_router.py` 保留 URL 兼容，但逻辑下沉：

- config 委派 `room_service`、participant authorization 与统一 resolver，后者只接受 published representation + approved non-null bundle并返回 `EditorLaunchDescriptor`；descriptor ack 建立 client-confirmed representation/bundle。
- forcesave/close intent 先委派 `forcesave_requests` 冻结 request，再调用 Command Service。
- callback 委派 `callback_delivery`；router 只校验 room/generation route credential，不把 URL 上 participant 当聚合内容作者，不下载文件、不写 target、不 commit。
- `_generate_doc_key` 删除且不留 fallback。
- `_extract_placeholder_value_from_docx` 仅可进入一次性诊断工具，生产路径零调用。

`wp_html_save.py`、上传、WOPI、custom 与其他 writer 按 inventory 逐个迁入 `ContentMutationService`；在全部 writer 迁入前不得宣称 base revision 可靠。新建 `wp_sync_router.py`，避免继续放大现有 router。

### Adapter protocol

```python
class WorkpaperSyncAdapter(Protocol):
    adapter_id: str
    document_type: Literal["xlsx", "docx"]
    contract_version: str

    async def read_current_projection(self, ctx: SyncContext) -> Projection: ...
    async def stage_projection_mutation(
        self,
        ctx: SyncContext,
        merged: Projection,
        *,
        expected_revision: int,
    ) -> ProjectionMutation: ...
    def materialize(
        self,
        *,
        substrate: Path,
        projection: Projection,
        output: Path,
        contract: SyncContract,
    ) -> MaterializeResult: ...
    def extract(self, *, artifact: Path, contract: SyncContract) -> Projection: ...
    def verify_unmanaged_regions(
        self, *, before: Path, after: Path, contract: SyncContract
    ) -> UnmanagedRegionReport: ...
```

- adapter 不 commit、不递增 revision、不更新 pointer、不发布 outbox；`ContentMutationService` 统一控制一次 business commit。
- adapter 接收的是由 content application/representation 固定的 immutable `DefinitionBundleSnapshot`，其中包含 approved authority model 与三类 typed child slots；normal operation shell 在 application 绑定前只可从 frozen request读取同一 snapshot，不得在执行中重新按 registry alias 取“最新版”或用 nullable contract 重组 identity。
- OO→HTML成功路径必须以application固定的`kind=incoming,state=durable` artifact为只读`substrate`，把merged projection写入新的staged result、再extract等值和未管理区域比对；incoming本身永不publish。quarantined incoming在adapter入口即fail closed，禁止application、extract、merge、retry或rematerialize消费。
- HTML→OO 的业务 mutation 与 representation 在一个 commit 中 stage/publish；无业务变化的纯 definition upgrade 先生成 non-current candidate，只有 approved per-entry contract/bundle 后才由 `RepresentationService.finalize_candidate()` 生成同 content version 的新 generation。
- custom adapter 可保持 xlsx 单一权威，但仍返回 content version/representation/hash/evidence，并使用 `custom_authoritative_ooxml` 或 `opaque_single_onlyoffice` bundle；无 contract 的 user upload 不被强制 instrumentation，但 contract slot 必须是版本化 typed null marker。
- registry 启动时拒绝 matcher 重叠、空匹配、文档类型、authority model/bundle/template/instrumentation/contract definition artifact 不一致；projection-based entry 的 contract child 不得为空/未批准，alias 变更不影响历史 operation/retry。

### Contract schema

存储在 `backend/data/workpaper_sync_contracts/{adapter_id}.json` 的是可跨环境复现的 canonical semantic payload，由 `SyncContract` 强校验。payload 禁止包含自身 artifact UUID/hash，也不包含环境相关 FK；发布器按 UTF-8、递归键排序、稳定数值/换行规则序列化后计算 SHA-256，再创建 `working_paper_sync_definition_artifact` envelope。每份 contract payload 顶层：

```json
{
  "contract_id": "g7.disclosure.listed",
  "semantic_version": "1.0.0",
  "document_type": "xlsx",
  "template_definition_sha256": "...",
  "instrumentation_definition_sha256": "...",
  "template": {
    "relative_path": "G/G7....xlsx",
    "sha256": "...",
    "structure_hash": "..."
  },
  "sheets": [
    {
      "sheet_key": "G7-...",
      "excel_name": "...",
      "tables": []
    }
  ]
}
```

发布 envelope/DB row（不参与 payload hash）：

```json
{
  "definition_artifact_id": "uuid",
  "kind": "contract",
  "definition_sha256": "sha256(canonical_payload)",
  "template_definition_id": "resolved-by-template-digest",
  "instrumentation_definition_id": "resolved-by-instrumentation-digest"
}
```

同一 semantic payload 在不同环境必须得到相同 SHA；UUID 只在发布后生成。definition 发布严格单向：先发布 template，instrumentation payload 只引用 template digest，随后 contract payload 引用已发布的 template + instrumentation digests；authoritative model definition 独立批准；最后 bundle 将 authority model 与三个 typed child slots 组合。instrumentation 禁止反向包含 contract 或 bundle digest，contract 也不引用 bundle；representation 只引用已经计算完成且 approved 的 bundle。

Authoritative model payload 示例：

```json
{
  "schema_version": "authority-model:v1",
  "authority_model": "projection_contract",
  "content_authority": "structured_projection",
  "merge_model": "stable_field_three_way",
  "required_slots": ["template", "instrumentation", "contract"]
}
```

Bundle canonical payload 示例：

```json
{
  "schema_version": "definition-bundle:v1",
  "authority_model": {"type":"definition","sha256":"<authority-model-sha256>"},
  "template": {"type":"definition","sha256":"<template-sha256>"},
  "instrumentation": {"type":"definition","sha256":"<instrumentation-sha256>"},
  "contract": {"type":"definition","sha256":"<contract-sha256>"}
}
```

`custom_authoritative_ooxml/opaque_single_onlyoffice` 的可选 slot 必须显式写成例如 `{"type":"contract:none:v1","sha256":"sha256(contract:none:v1 canonical bytes)"}`，而不是省略、`null`、空串或全零 hash。bundle publisher 先验证 child kind/state/digest 与 authority model slot policy，再对完整 canonical payload 计算 digest；projection-based bundle 若 contract/instrumentation 不是 approved `definition` 立即拒绝。canonicalizer 以 golden bytes、键顺序/换行扰动、跨 Python/TypeScript 实现、“把自身 hash 塞回 payload 必红”“slot omission/SQL NULL/空串/全零 hash 必红”“新增反向 contract/bundle digest 必红”及“typed null marker 版本变化 digest 必变”测试锁死。

Excel table contract：

```json
{
  "table_key": "equity_changes",
  "anchor": "A7",
  "header_rows": 2,
  "footer_anchor": {"marker": "合计", "search_column": "A"},
  "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
  "dynamic_columns": {"identity": "{slot}_{seq}", "source_ref": "源xlsx!B6:Z6"},
  "fields": [
    {
      "stable_field_key": "equity_changes/{row_uuid}/closing_amount",
      "json_pointer": "/rows/{row_uuid}/closingAmount",
      "column_key": "closing_amount",
      "cell": {"column": "H", "row_from": "row_identity"},
      "mode": "editable",
      "value_type": "amount",
      "source_ref": "源xlsx!H8"
    }
  ],
  "formula_mask": ["I8:I200"],
  "delete_policy": "tombstone"
}
```

Word contract：

```json
{
  "contract_id": "f2.stocktake.plan",
  "semantic_version": "1.0.0-sdt1",
  "document_type": "docx",
  "template_definition_sha256": "...",
  "instrumentation_definition_sha256": "...",
  "template": {"relative_path": "...docx", "sha256": "...", "structure_hash": "..."},
  "fields": [
    {
      "stable_field_key": "plan/location",
      "json_pointer": "/plan/location",
      "sdt_tag": "gt:field:f2.stocktake.plan:plan/location",
      "mode": "editable",
      "instances": "one"
    }
  ],
  "repeaters": [
    {
      "stable_field_key": "plan/members",
      "json_pointer": "/plan/members",
      "row_tag": "gt:row:f2.stocktake.plan:members:{row_uuid}"
    }
  ]
}
```

`source_ref` 指向权威源 xlsx/docx 的具体位置，禁止无来源自造字段。contract 生成工具只能生成候选骨架；未人工审核、未填 stable key/source_ref 的候选不得注册生产 adapter。

### Normalized structure hash

物理 SHA 会因 OO 保存元数据变化而变化，因此同时计算结构 hash：

- Excel：sheet 顺序/名称、merged ranges、受管区域公式位置、表头规范化文本、命名区域；不含普通业务值、calcChain、creator/modified time。
- Word：SDT tag 层级/计数、表格拓扑、关键 section、关系类型；不含普通正文值、rsid、modified time。

模板准入同时校验权威 template SHA；运行中 OO 文件校验 compatible structure hash。两者用途不可混用。

## Merge Algorithm

### 规范化字段

Projection 是按 stable key 索引的值集合，不是位置数组：

```python
@dataclass(frozen=True)
class FieldValue:
    stable_key: str
    row_key: str | None
    value: JsonValue
    value_type: str
    mode: Literal["editable", "formula", "auto_source", "word_only"]
    oo_location: str
    json_pointer: str

@dataclass(frozen=True)
class Projection:
    fields: Mapping[FieldIdentity, FieldValue]
    structure_hash: str
```

值比较先按类型规范化：金额 Decimal、日期 ISO、字符串仅规范化 OO 非语义控制字符，不 trim 用户有意义空格；空值与 0 严格区分。

### 三方规则

```python
for identity in union(base, current, incoming):
    b, c, i = value(base), value(current), value(incoming)

    if protected(identity) and i != b:
        conflict(PROTECTED_FIELD)
    elif i == b:
        merged = c                     # OO 未改，保留服务器新值
    elif c == b:
        merged = i                     # 仅 OO 改
    elif c == i:
        merged = c                     # 两侧同改为相同值
    else:
        conflict(VALUE)
```

新增/删除作为显式 MISSING sentinel 参与同一规则：

- base 无、current 无、incoming 有：OO 新增。
- base 有、current 删除、incoming 未改：保留删除。
- 一侧删除、一侧更新：`delete_update` 冲突。
- row reorder 只改变展示顺序字段，不改变 row identity。

不同字段天然自动合并；同字段才冲突。不得把整张 JSON 字符串作为一个字段比较，否则 D2 任意两行并改都会形成整表冲突。

### 冲突解决与 canonical rematerialization

`resolve` 请求携带 `operation_id + expected_current_revision + room_generation + client_edit_epoch + canonical_application_id + application_effective_request_sequence + room_latest_durable_application_id+sequence + conflict_set_digest + resolutions[]`。coordinator 的不可交换顺序是：先以请求中的 operation id 与显式 route scope执行 authorization-first guard；若 requested operation为`application_id=NULL`的terminal duplicate，则验证其direct-primary同scope/bundle关系并canonicalize；随后才要求canonical primary唯一绑定content application，锁wp/room并从该application读取frozen identity，再读取room latest durable application/sequence：

- 若room `latest_durable_application_id`与当前canonical application相同，则把请求中的sequence规范化为application当前`effective_request_sequence`并继续；same-key较高request的fold不得supersede自己。只有room latest durable指向同generation另一个canonical application且其effective sequence更高时，旧application/operation/conflict才标`superseded`并返回409指向最新operation；不得把旧选择跨不同snapshot套用，也不得形成duplicate→primary→stale循环。
- sequence/fence 未变但 current revision 已变：以 application 固定的 `base_version_id`、immutable definition bundle/authority model 与 incoming 对最新 current 再跑三方 merge；无冲突部分继承，冲突列表重建，返回 409 `CONFLICT_REBASED`。
- 所有 fence 均匹配：按用户选择得到 merged projection。
- 无冲突 merge 和全部 resolved 都进入同一 rematerialize 流程：只以 application 的 `kind=incoming,state=durable` artifact 为只读 substrate，仅把受管区域重写到新 staged result → extract 比对 merged projection → 比对未管理区域 → security/eligibility → publish result representation；quarantined 在入口拒绝，incoming row不变且永不published。
- 进入 DB commit 前再次校验 project/visibility/workflow lock、generation、write fence、initiator permission epoch 与 contributor snapshot；失效则 incoming 保留、application/operation=`authorization_stale`，不提交。
- `ContentMutationService` 在单一 DB 事务内提交 projection mutation、content version、result representation、current pointers、room last-applied、application result、operation、outbox。若 result managed projection 与 incoming 等值，则 client-confirmed base 同步推进；否则 room=`refresh_required` 且 generation 必须 supersede/reopen。
- 任何 roundtrip/unmanaged-region 失败都不得只提交 HTML projection，也不得把原 incoming 直接设 current。

### 回滚

回滚不改历史：用户路由只接受目标historical content version的immutable opaque UUID `version_id`；scope index以该UUID作`resource_id`完成project/wp/entry授权后，才读取其projection与对应entry published representation/immutable definition bundle，作为substrate重新materialize/反读，stage新representation，再以source=`rollback`创建新business revision。numeric `revision`只用于展示、响应与expected-current乐观锁，不参与全局scope lookup或路由定位，因此不同wp的revision 1不会碰撞。若只回退representation definition而业务projection不变，则仍须经candidate + approved bundle finalize走representation rollback、不增content revision。文件系统失败发生在DB commit前；DB失败只留下orphan/candidate，current/last-applied/client-confirmed不变。

## Template Instrumentation 与版本化升级

### Identity probe 决策门

在通用 Excel/Word engine 前先对真实 OnlyOffice 9.4 执行黑盒矩阵：

| 文档 | 候选 identity | 操作矩阵 | 通过条件 |
|---|---|---|---|
| Excel | hidden `_GT_SYNC` sheet | 改值、插删/排序/复制行、forcesave、下载、重开 | sheet/ID/保护和业务部件均保留 |
| Excel | workbook/sheet defined names | 同上并重命名展示 label/sheet | 名称与目标关系稳定，无自动重命名漂移 |
| Excel | Excel Table + hidden UUID 列 | 插删/排序/复制/粘贴 | 原行 ID 稳定；空/重复 ID 可判定 |
| Word | tagged SDT/row SDT | 编辑、插删段落/行、forcesave、重开 | tag、层级、row UUID 集合符合预期 |

probe 产物绑定 OO build、模板 hash 和操作脚本。候选未通过时不得被 contract/engine 依赖；允许不同模板采用不同已验证载体。

### Excel instrumentation contract

`backend/wp_templates/` 是唯一权威源。instrumentation manifest 对每个模板声明：

```json
{
  "template_id": "G7/...",
  "template_definition_sha256": "...",
  "from_sha256": "...",
  "instrumentation_version": "1.0.0",
  "identity_schema_version": "1.0.0",
  "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
  "managed_tables": [{"sheet_id":"...","table_id":"...","row_id":"row_uuid"}],
  "visible_equivalence_policy": "strict",
  "ignored_by_business_sheet_enumerators": ["_GT_SYNC"]
}
```

instrumentation manifest canonical payload 只绑定已发布 template digest 与 identity carrier/inventory，不保存自身 artifact UUID/hash，也不引用尚未计算的 contract 或 bundle digest。contract 在 instrumentation 发布后单向引用其 digest；authoritative model 独立批准；bundle 在三类 child 和 authority model 均可解析后生成。具体 representation finalize 时，再把已计算的 authority-model/template/instrumentation/contract/bundle digests 写入 `_GT_SYNC` runtime binding block；该 block 属于 representation artifact identity，不反向改变任一 definition。动态行 UUID 为预生成字面量，不用易重算公式。新行空 UUID可在 contract 允许时分配；复制产生重复 UUID默认为结构冲突，除非特定表声明可安全拆分。运行时不得写回模板库。

### Versioned upgrader

存量 artifact 升级流程：解析并固定 from definition bundle → 复制到 staging → 注入 identity → 可见结构/公式/样式/merge/drawing 等价校验 → extract roundtrip → 登记 non-current `working_paper_representation_upgrade_candidate`。此时即使 template/instrumentation 已批准，也不得生成 published/current standard representation。只有 per-entry contract、authoritative model 与 target bundle 按 `template → instrumentation → contract → bundle` 全部 approved，且 candidate 与 bundle compatibility/反读等值通过后，才原子 finalize 为同一 content version 的新 immutable representation generation并可切 pointer。失败不改变 entry pointer/revision；成功保留 candidate、from/to bundle/child IDs/hash、representation/artifact hash、业务 projection 等值报告和 rollback target。只要业务 projection 未变，`content_revision` 必须保持不变。custom/user-upload 文件默认不升级。

## Excel Engine

### Materialize / rematerialize

1. HTML→OO 读取当前 published entry representation；首次使用已通过 probe、且已形成 approved per-entry contract/bundle 的 instrumented template。OO→HTML 必须读取 content application 固定的 `kind=incoming,state=durable` artifact 作只读 substrate，并把输出写到独立 staged result；upgrade candidate 与 incoming 绝不能直接作 published result。
2. 按 application/representation 保存的 immutable definition bundle 校验 authority model、typed child kind/state/digest 与 compatible structure identity；pre-bind operation shell 只读 frozen request 的同一 identity，projection-based bundle 必须含 approved contract，不得解析 registry 当前 alias。
3. 仅通过稳定 sheet/table/row/column identity 定位受管字段。
4. 把目标 projection 写入 editable 字段；不变字段也按 merged projection 规范化，避免 incoming 与 HTML 分叉。
5. 动态行复制已声明样式/公式源，保留原 row UUID；空/重复/丢失 UUID 按 contract 决策，不按位置猜。
6. 动态公司列按 `{slot}_{seq}` 展开；label 仅展示。
7. footer/公式范围按 contract 更新；formula/auto-source 写服务端值并保护。
8. 保存 staged artifact，重新打开并 extract；受管 projection 必须类型化等值。
9. 比对未管理区域与 substrate：drawing/chart/pivot/VBA/未知关系按 policy 不得非预期变化。
10. 通过后交由 artifact repository、`RepresentationService` 与 `ContentMutationService` 按“业务变化单次 commit / 纯表示变化不增 revision”规则发布；所有 published representation 必须绑定 approved bundle。definition upgrader 路径先写 candidate，再经 approved bundle finalize；engine 自身不更新 pointer。

优先使用 zip-level OOXML 定点修改。只有 template capability manifest 明确 `openpyxl_safe` 且探针覆盖所有关键部件时才允许 openpyxl roundtrip；含 drawing/chart/pivot/macro 的文件默认禁止全量重写。

### Extract

- 先验证 workbook/sheet/merge/formula、frozen definition bundle/authority model、typed instrumentation/contract child digest 与 identity inventory；candidate、alias 漂移或 projection bundle 缺 contract 立即失败。
- 优先从已验证的 hidden metadata/defined names/Table UUID 读取 identity；缺失、重复或未知 identity 形成 schema conflict，不按中文表头/位置猜。
- 业务 importer、sheet 枚举和导入导出必须显式排除 `_GT_SYNC` 等 metadata sheet。
- 只读取受管 editable 字段；formula/auto-source incoming 值仅用于篡改检测。
- 同 stable key 多位置异值形成 schema conflict；类型转换失败保留原值供裁决。
- 大表按 table 分块，projection sidecar 流式 gzip；整个 callback 不同时持有多份完整 workbook/projection。
- 输出同时包含 identity inventory 与 unmanaged-region digest，供 rematerialize 反读校验。

## Word SDT Engine

### SDT migration

现有 DOCX token 只作为一次性定位线索。迁移工具：

1. 从 adapter contract 读取 stable field 与候选 token/位置。
2. 在原 OOXML 上包裹/创建 `w:sdt`，写 `w:tag w:val="gt:field:..."`；不得用 python-docx 重建整文档。
3. 同段多 token 分别建立独立 SDT；跨 run token 合并其 run 后放入 SDT，保留样式。
4. 重复表格行包 row-level SDT，并写 `row_uuid`。
5. 保存后重新打开 zip 验证 tag 集合/计数/层级与 contract 一致。
6. 产出迁移后 template SHA/structure hash；原模板保持可回滚副本或由 git 恢复。

### Word materialize

- HTML→OO 以 current published canonical Word 为底，不以原模板重建；首次也必须由 approved Word per-entry contract/bundle finalize，candidate 不可打开。OO→HTML merge/resolve 则以 content application 固定的 `kind=incoming,state=durable` artifact 为只读 substrate，只改结构化岛并输出新的 staged result；incoming 本身不 publish。
- 仅按 content application/representation 冻结的 bundle 解析 tagged SDT；pre-bind operation shell 只能通过 frozen request读取同一 bundle，不得重新读取 alias 或把 missing contract 降级为 paragraph 规则。
- 仅替换匹配 tag 的 `w:sdtContent`。
- SDT 外段落、批注、修订、图片和表格保留。
- 重复行按 row UUID 增删，样式源由 contract 指定。
- 若 tag 缺失、重复计数异常或结构漂移则阻断。

### Word extract

- 遍历所有 `w:sdt`，以 `w:tag` 解析 stable key/row UUID。
- 内容读取合并全部 `w:t`，保留 contract 指定的换行/富文本语义。
- 同 stable key 多实例一致则返回一个字段；不一致形成 `duplicate_word_instance` 冲突并记录全部 XPath。
- SDT 外内容不进入 Projection，永远不回填 HTML。
- 不提供 paragraph-index/regex fallback。

### OO 9.4 pilot 门

F2-22/F2-23 必须先通过：

1. 注入 tag 后 unzip 校验。
2. OO 9.4 打开并编辑 SDT 内容。
3. Command Service forcesave。
4. status=6 callback 耐久保存。
5. 回传 DOCX unzip 校验 tag 集合与 row UUID 未丢。
6. extract/merge 后 HTML 值正确。
7. 再次 materialize，Word-only 自由正文逐字保留。

任一步失败则 Word 批量迁移阻塞，不能降级段落索引。

## API Design

统一响应沿用平台 `{code,message,data}` envelope。

所有用户发起端点使用统一前缀 `USER_SYNC_PREFIX=/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}`；project/wp/entry 都是显式 route scope，不得从 room/operation/recovery 业务 row 反查后才授权。`AuthorizationFirstIdempotencyGuard`（GET/list/query/download-only 也使用 read 模式）的不可交换顺序为：认证 → 解析显式 route scope 与端点 opaque ids/可选短期 signed scope claim → **只查询** `working_paper_sync_scope_index` → route/signed/index scope 交叉比对与当前 project visibility → action/workflow/lease/generation/write-fence/bundle 重验 → business resource read 或 Idempotency-Key/cache lookup → 新副作用。scope row 与每个 child 同事务创建或以 `retired_at` 退役且只含非敏感归属；tombstone 永不物理删除，resource id 永不复用；guard 不得用业务 table、artifact、候选摘要、错误或 cache 补 scope。

不存在、跨 scope、伪造 entry 或无 project visibility 必须在同一 guard 阶段返回同 envelope、统一时序预算的 404；已确认 project visibility 但缺 action/edit 权限、工作流/lease/fence 门禁时返回 403；未认证才返回 401。调用顺序与时序分桶均有 oracle，禁止先读业务对象再“统一文案”。该 guard 覆盖 pending-mutations、materialize、confirm-descriptor、forcesave、close-intents、recovery-cases list/claim/download-only、operations/conflicts/timeline query、resolve 与带显式 entry 的 rollback；成功后撤权/过期/supersede 的同 key 重放也必须在 cache 前拒绝。callback route 继续使用独立签名的 room/generation/doc_key service scope，不暴露用户 404/403 语义，但 application 仍经过 frozen request/recovery claim 与最终 authorization fence。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/pending-mutations`

`flushHtml()` 调用此端点保存尚未提交的 mutation payload，返回：

```json
{
  "pending_mutation_token": "opaque-signed-token",
  "expected_revision": 11,
  "payload_sha256": "...",
  "expires_at": "..."
}
```

Request 必须带 `sheet_key/expected_revision/Idempotency-Key`；route 已显式给出 project/wp/entry，payload 若保留 `entry_id` 必须逐字相等。每次调用先经过 scope-index `AuthorizationFirstIdempotencyGuard`；通过后相同 key+payload 才返回同 token，不同 payload 返回 409。token 过期、跨 entry/user 使用、payload digest 不符或重放时当前权限/lease/fence 已失效均 fail-visible，创建 token不推进 revision。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/materialize`

Request：

```json
{
  "entry_id": "g7.disclosure.listed",
  "sheet_key": "...",
  "expected_revision": 11,
  "pending_mutation_token": "opaque flush result"
}
```

Response（唯一 `EditorLaunchDescriptor`）：

```json
{
  "operation_id": "uuid",
  "room_id": "uuid",
  "participant_id": "uuid",
  "doc_key": "...",
  "generation": 3,
  "server_applied_revision": 12,
  "client_confirmed_base_revision": 12,
  "representation_id": "uuid",
  "representation_generation": 4,
  "write_fence_epoch": 9,
  "artifact_sha256": "...",
  "authority_model": "projection_contract",
  "authority_model_definition_sha256": "...",
  "definition_bundle_id": "uuid",
  "definition_bundle_sha256": "...",
  "definition_bundle_slots": {
    "template": {"type":"definition","sha256":"..."},
    "instrumentation": {"type":"definition","sha256":"..."},
    "contract": {"type":"definition","sha256":"..."}
  },
  "document_type": "xlsx",
  "mode": "edit",
  "onlyoffice_config": {}
}
```

409：revision/token 已提交但 identity 不同或已过期；422：adapter/authority-model/bundle/contract/template/instrumentation 不适配、bundle slot 非法或 representation 仍是 candidate；423：工作流/编辑锁；503：OO 不健康。只有先通过当前 authorization/lease/generation/fence 重验，相同 pending token + Idempotency-Key 的成功重放才返回同 operation/content version/representation；撤权后不得返回 cached descriptor。resolver 必须拒绝 unapproved bundle、projection-contract 缺 contract child 与 candidate。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/rooms/{room_id}/confirm-descriptor`

DocEditor 真实触发 `onDocumentReady` 后调用：

```json
{
  "participant_id": "uuid",
  "generation": 3,
  "doc_key": "...",
  "representation_id": "uuid",
  "artifact_sha256": "...",
  "content_revision": 12,
  "write_fence_epoch": 9,
  "authority_model_definition_sha256": "...",
  "definition_bundle_id": "uuid",
  "definition_bundle_sha256": "...",
  "definition_bundle_slots_digest": "..."
}
```

请求带 `Idempotency-Key`。先经过 authorization-first guard，再锁 room 并重验 participant lease、generation/doc_key、entry current published representation、artifact、approved definition bundle/authority model/typed slots 与 write fence；candidate 或 stale bundle 直接 409。首次成功写 `working_paper_oo_client_confirmation` 和 append-only `descriptor_confirmed` event，原子推进 room client-confirmed identity并转 active。只有当前授权仍有效时，完全相同重放才返回既有 confirmation；旧 generation/fence/representation/bundle 或撤权重放返回 409且不得 forcesave。该 endpoint 不递增 content revision。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/rooms/{room_id}/forcesave`

先在一个 DB 事务中冻结 `working_paper_forcesave_request`、写 scope-index rows并创建 `application_id=NULL` 的 operation shell，再调用 Command Service；返回 202：

```json
{"forcesave_request_id":"uuid","operation_id":"uuid","request_sequence":7,"state":"accepted","poll_after_ms":500}
```

重复请求带 `Idempotency-Key`，唯一范围为`(room_id,generation,initiated_by_participant_id,kind,key)`；但只有scope-index authorization-first guard与当前participant/room/fence/bundle重验通过，且existing request的initiator、kind及confirmation/base/representation/bundle/fence/contributor组成的`frozen_request_fingerprint`逐项相同，才可返回同request/operation。另一participant、不同kind或不同frozen payload复用同key一律409且不得返回已有标识；撤权或bundle supersede后重放同样不得拿到cached result。accepted 响应中的 operation 只是 nullable-application shell，直到 durable request-first correlation 才绑定 application。若 room=`refresh_required/close_barrier/closing`、write fence 变化、participant 无写权限/未 confirmation、confirmed bundle 与 current representation 不同或 initiator 为空，则在 Command Service 前拒绝。普通 forcesave 使用本 endpoint；clean close 必须改走下述 `close-intents` 仲裁，禁止客户端直接创建 `kind=close_capture`。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/rooms/{room_id}/close-intents`

由当前confirmed active edit participant创建close intent。服务端先经scope-index authorization-first guard，再锁room并在同一事务写intent、把participant `active→closing`、推进barrier；closing不再计入active。active首次归零时按最高`(intent_sequence,id)`与eligibility snapshot写leader并阻止新join；此前closing intents的ordinary forcesave成为barrier predecessors。`reconcile_close_intents()`在intent创建、每个ordinary forcesave terminal/superseded-safe、participant leave/error/revoke/expire后重锁room。promotion前leader失去资格时先审计`authorization_stale`并推进eligibility epoch，再按同一comparator选合法successor；同snapshot重放不得换leader。存在successor且predecessors安全时CAS提升为唯一`close_capture` request。无successor时supersede generation并进入`recovery_required/authorization_stale`显式终态；已promoted后失效由最终fence终结唯一capture，不得再造第二个。partial unique只防双capture；合法资格标准场景必须exactly-one，leader撤权/过期场景必须证明successor或无successor两条路径均可达、无数据丢失且不永久阻塞。只有各自ordinary request、leader close-capture或显式recovery terminal达相应终态才允许editor destroy。

### callback recovery APIs

- `GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/recovery-cases?room_id={room_id}&generation={generation}`：read-mode guard 先只查 scope index并验证显式 project/wp/entry/room/generation 与当前 visibility/workflow/lease/fence；通过后才查询 cases并返回 reason、候选 prior confirmation 摘要和 `claim/download-only` 能力，不返回业务内容或未授权资源存在性。
- `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/recovery-cases/{case_id}/claim`：带 `room_id / participant_id / prior_confirmation_id / expected_generation / expected_write_fence / expected_definition_bundle_sha256 / Idempotency-Key`。scope-index authorization-first guard后才锁case/room并读取业务内容；服务端自行校验候选base/representation/approved bundle/authority model/contributors。全部通过后在一个事务中创建唯一recovery-claim request与operation shell、创建/命中application及scope rows；commit前shell成为primary或direct terminal duplicate，delivery/case绑定同一canonical application。客户端不得提交任意base/bundle；同key重放前仍须完整重验当前授权与fence。
- `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/recovery-cases/{case_id}/download-only`：同样先只读 scope index完成 current authorization，再显式终结为 download-only并签发最小权限短期下载；保留审计，不写业务内容，且 request/application/operation 必须保持为空。

claim 前 unmatched/ambiguous case 不存在 operation，不能调用普通 operation retry。过期/superseded generation、错误 prior confirmation/bundle、contributor 含撤权/未知 writer、fence 变化或 claim 幂等重放时授权已失效，均不得创建 request/application/operation；case 转 quarantined/download-only 或保持可诊断状态。浏览器 crash、错误候选拒绝、download-only 零三实体，以及每个 `editable=true AND (capability=bidirectional OR room_model=shared)` entry 的 single participant、两种关闭顺序、两类 terminal 交错与 exactly-one close-capture，均必须进入真实 OO scenario evidence。

### `GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/operations/{operation_id}`

返回 operation shell 状态、nullable `application_id`、nullable `duplicate_of_operation_id`、`canonical_operation_id`、阶段时间，以及 primary绑定后从 application解析的 result revision、bundle/authority model identity、冲突数、错误码与可执行动作。read-mode guard必须先按调用者提供的 duplicate/primary operation id与显式 route scope只查 scope index；通过 visibility/action后才读取 operation。若为duplicate，再校验其 direct primary同 scope/bundle/application约束并读取primary/application或轮询缓存；禁止授权前canonical跳转、链/环或因duplicate泄露旧终态。前端优先SSE/事件，轮询作为断线恢复。

### `GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/operations/{operation_id}/conflicts` 与 `GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/operations/{operation_id}/timeline`

均先对请求中的 operation id执行 read-mode authorization-first guard；若为duplicate，只有在校验 direct primary同 scope/bundle/application后才分页返回 canonical primary 的冲突分组/可显示字段元数据或脱敏 append-only timeline，并在响应保留 requested/canonical ids。不得在授权前解析 duplicate pointer或泄露 operation/case/primary 是否存在、hash、候选或敏感整稿。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/operations/{operation_id}/resolve`

```json
{
  "expected_current_revision": 12,
  "room_generation": 3,
  "client_edit_epoch": 5,
  "canonical_application_id": "uuid",
  "application_effective_request_sequence": 8,
  "room_latest_durable_application_id": "uuid",
  "room_latest_durable_sequence": 8,
  "conflict_set_digest": "sha256",
  "resolutions": [
    {"conflict_id":"uuid","choice":"incoming"},
    {"conflict_id":"uuid","choice":"merged","value":"..."}
  ]
}
```

全解决返回applied revision；最新revision/bundle/generation/fence变化或room latest durable指向另一个较新canonical application时返回409 + rebased operation/conflicts；same-application effective sequence fold只规范化sequence，不判stale。authorization-first guard在读取请求中的operation/conflict与Idempotency-Key结果前执行；若requested id为`application_id=NULL`的duplicate，必须先完成requested授权、再验证direct-primary invariant并canonicalize，最后仅要求canonical primary唯一绑定application。响应同时返回requested/canonical ids，绝不创建第二operation/application。

### `POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/versions/{version_id}/rollback`

需编辑权限和二次确认；`version_id`为immutable opaque content-version UUID，project/wp/entry均来自显式route，guard在读取历史representation/bundle或幂等结果前只以`(resource_kind=version,resource_id=version_id)`查scope index并完成authorization。numeric revision仅在响应中展示/作为expected-current乐观锁，禁止用于scope lookup。返回新revision，不把current revision倒退，不允许candidate/incoming作rollback source；两个wp都存在revision 1时仍由不同UUID无碰撞定位。

### callback compatibility 与真值表

现有 callback URL 保持兼容，签名绑定 `room_id / generation / doc_key / claim_version / route_credential_id / callback_token`。payload `key` 必须等于 room doc_key；`userdata` 若存在则携带 forcesave request id。route credential 是 room/generation 服务凭证，不能把 URL 中某个 participant 当聚合 artifact 唯一作者。router 只交给 delivery service。

版本化真值表作为 `backend/data/onlyoffice_callback_state_contract.json` 单一真源，至少定义 status 1/2/3/4/6/7、是否含 URL/userdata、是否应下载、OO response error、room transition、delivery terminal、request correlation、recovery outcome 与 application 是否允许。任何带 userdata 的 callback 都先精确绑定 frozen request。status=2 无 userdata 时优先绑定 room arbiter 产生的唯一 open close-capture；不存在 eligible request 时，才可去重到 frozen identity（含 bundle/authority model）唯一、同 incoming 且不存在 sequence 更高的**不同 canonical application**；命中同 application key的较高request必须fold effective sequence并让room fence继续指向同application，不得将primary自我supersede。缺 request、违反 singleton 或候选不唯一时 durable 并创建零 operation recovery case；claim成功才原子创建request+shell并创建/命中application、在commit前收敛为primary或direct terminal duplicate，download-only永远不创建，不能默认按callback到达时room base处理。

### 多用户 callback 黑盒真值门

在实现 shared room 前，必须用真实 OO 9.4 两个独立用户同时编辑同一 doc_key，记录：forcesave 由用户 A 发起时 callback 的 `users/actions/userdata/status`、用户 B 修改是否聚合入 artifact、status 6/2 顺序、drop/revoke 后 payload 与最终文件、无 userdata close 行为。探针输出 OO build、前后 artifact、callback payload digest、网络/timeline 与参与者矩阵。若 OO 无法证明被撤销用户已从聚合文档排除，设计固定采用“提升 write fence + supersede generation + 其余用户重开”，不得实现选择性 participant callback 应用。

## Frontend Design

### `useWorkpaperSyncBridge.ts`

```ts
interface WorkpaperSyncBridgeOptions {
  entryId: Ref<string>
  wpId: Ref<string>
  projectId: Ref<string>
  sheetKey?: Ref<string>
  flushHtml: () => Promise<{
    expectedRevision: number
    pendingMutationToken: string
    payloadSha256: string
    expiresAt: string
  }>
  reloadHtml: (minimumRevision: number) => Promise<void>
}

type EditorLaunchDescriptor = {
  roomId: string
  participantId: string
  docKey: string
  generation: number
  serverAppliedRevision: number
  clientConfirmedBaseRevision: number
  representationId: string
  representationGeneration: number
  writeFenceEpoch: number
  artifactSha256: string
  authorityModel: 'projection_contract' | 'custom_authoritative_ooxml' | 'opaque_single_onlyoffice'
  authorityModelDefinitionSha256: string
  definitionBundleId: string
  definitionBundleSha256: string
  definitionBundleSlots: {
    template: { type: string; sha256: string }
    instrumentation: { type: string; sha256: string }
    contract: { type: string; sha256: string }
  }
  documentType: 'xlsx' | 'docx'
  mode: 'edit' | 'view'
  onlyofficeConfig: Record<string, unknown>
}

type RecoveryCaseSummary = {
  caseId: string
  reason: 'missing_request' | 'ambiguous_close' | 'crash_close' | 'stale_candidate'
  state: 'unclaimed' | 'claiming' | 'application_created' | 'download_only' | 'quarantined' | 'expired'
  priorConfirmationCandidates: Array<{
    confirmationId: string
    generation: number
    definitionBundleSha256: string
  }>
  allowedActions: Array<'claim' | 'download_only'>
  blockingReason?: string
  operationId?: string // 仅 claim 成功并原子创建 operation 后出现
}
```

公开：

- `mode`, `capability`, `state`, `descriptor`, `operation`, `recoveryCases`, `conflicts`, `lastError`
- `switchToOnlyOffice()`：flush 创建 pending mutation → 服务端单次 content/representation commit（approved bundle）→ consume descriptor → mount；DocEditor `onDocumentReady` 后回传 bundle identity 调用 confirm-descriptor，成功前不进入可编辑/可 forcesave 状态。
- `switchToHtml()`：freeze forcesave/close request（含 bundle）→ command accepted → await incoming durable → await applied/conflict/refresh_required；applied 等值时 reload，refresh-required 时销毁旧 generation 并用新 descriptor mount + confirm 后重开。
- `retryOperation()`：仅对已有 operation 从 durable incoming 与原 immutable definition bundle 恢复，不重复 forcesave；`operationId` 为空的 unmatched/ambiguous recovery case 与 download-only 不进入此 API。
- `listRecoveryCases()` / `claimRecoveryCase()` / `downloadRecoveryArtifact()`：三者都由服务端 authorization-first；UI 显示 prior confirmation 的 bundle digest 与阻断原因。claim 只提交 case/participant/confirmation/expected bundle/fence，不允许客户端指定 base；成功后才获得 operation 并等待 terminal。download-only 只下载并终结 case，UI 不伪造 operation 或“结构化回写成功”。
- `resolveConflicts()`：提交 revision + generation + incoming sequence + conflict digest fence；`rollbackToRevision()`。
- `canLeave` / beforeunload guard。

bridge 是唯一模式状态机；除主同步状态外显式包含 `recovery_pending / recovery_claiming / recovery_download_only`。recovery pending 不等于 operation error，claim 成功后才关联 operation，download-only 为独立终态。`GtOnlyOfficeSheet`/Word editor 不再次请求 config，业务 composable 不拼 endpoint、localStorage key 或成功文案。

### `GtOnlyOfficeSheet.vue` / Word editor

只接收 `descriptor: EditorLaunchDescriptor`，不得再自行调用 config endpoint。事件：

```ts
ready: [{ roomId: string; participantId: string }]
dirty: [{ dirty: boolean }]
saveRequested: [{ operationId: string }]
incomingDurable: [{ operationId: string; artifactSha256: string }]
terminal: [{ operationId: string; state: 'applied' | 'conflict' | 'refresh_required'; revision?: number }]
recoveryCase: [{ caseId: string; reason: string; operationId?: never }]
error: [{ stage: string; code: string; message: string }]
fallback: []
```

`defineExpose` 提供 `forceSave(): Promise<SyncOperationResult>` 与 `getSyncState()`。`ready` 只表示 DocsAPI `onDocumentReady` 已触发；bridge 必须随后 await confirm-descriptor，确认成功才标 `oo_editing` 并启用 forcesave。只读 participant 不暴露写 forcesave；dirty/awaiting ack 时 route/beforeunload 由 bridge 阻断。

### UI components

- `WorkpaperSyncStatusBar.vue`：紧凑显示版本、representation generation、authority model、bundle digest、状态、最后同步、重试。
- `WorkpaperSyncConflictDialog.vue`：按 sheet/table/row 分组；金额走 displayPrefs store 的 `fmtAmount`。
- `WorkpaperSyncRecoveryPanel.vue`：仅在 read authorization 通过后显示 recovery reason、prior confirmation/bundle 摘要、claim 与 download-only；claim 失败保持零 operation，download-only 不显示“回写完成”。
- `WorkpaperSyncDetailsDrawer.vue`：operation/recovery timeline、hash、adapter/bundle/contract、错误和已授权 incoming 下载。

文案全中文；“已冻结保存请求”“已发送强制保存”“OO 文件已耐久保存”“结构化回写完成”“服务器已合并，需重载编辑器确认新基线”必须分别展示。

### legacy migration

旧 key 读取一次后转换为 `workpaper-sync-mode:{entry_id}:{wp_id}:{sheet_key}`。若 manifest capability 不支持存量值，则回落真实可用模式并删除旧值。迁移后不再写旧 key。

## Entry Manifest

生成文件建议：

- 源事实：`backend/data/workpaper_sync_entry_manifest.json`
- 生成/校验器：`backend/scripts/gen/generate_workpaper_sync_manifest.py`
- 前端只读投影：`audit-platform/frontend/src/components/workpaper/sync/workpaperSyncManifest.generated.ts`

每条：

```json
{
  "entry_id": "d2.detail.rows",
  "mounts": [{"file":"...vue","component":"GtOnlyOfficeSheet","sheet_expr":"..."}],
  "independent_entry": true,
  "parent_entry_id": null,
  "wp_match": ["D2-*"],
  "document_type": "xlsx",
  "editable": true,
  "room_model": "shared",
  "scenario_profile": "editable_shared_bidirectional:v1",
  "html_store": "checklist_responses:D2-detail-rows",
  "canonical_resolver": "standard_project_file",
  "adapter_id": "d2.detail.rows",
  "capability": "bidirectional",
  "authority_model": "projection_contract",
  "authority_model_definition_sha256": "...",
  "definition_bundle_id": "uuid",
  "definition_bundle_sha256": "...",
  "definition_bundle_slots": {
    "template": {"type":"definition","sha256":"..."},
    "instrumentation": {"type":"definition","sha256":"..."},
    "contract": {"type":"definition","sha256":"..."}
  },
  "migration_state": "pilot",
  "evidence": {
    "sync_test_run_id": null,
    "required_scenario_set_digest": null,
    "scenario_evidence_ids": [],
    "authority_model_definition_sha256": null,
    "definition_bundle_sha256": null,
    "bundle_slots_digest": null,
    "onlyoffice_build": null,
    "run_manifest_sha256": null,
    "verified_at": null,
    "result": "unverified"
  }
}
```

生成器负责发现 mounts，并从真实宿主是否可编辑、descriptor/room 接线与 registry 生成 `editable / room_model / scenario_profile`；这些 source-backed 字段与来源摘要进入 manifest digest，reviewed overlay 只能裁决业务 capability/adapter，不能用自由文本或可漂移 `multi_user` 布尔降级 required scenarios。业务字段、capability 和 adapter 来自 reviewed overlay。三向守卫为源码 mounts ↔ manifest ↔ registry；最终增加第四、第五边：真实渲染宿主 DOM/调用链与 evidence application/operation/artifact。父组件入口不重复计数。

Evidence writer 只接受数据库中真实 `sync_test_run`、逐 scenario rows、recovery cases、content applications、terminal operations、content versions、published result representations、approved definition bundles/children、artifacts 与 trace bundles，按 source-backed manifest profile + `capability + immutable definition bundle + authoritative model` 重算 required scenario set 与 deterministic evidence projection；不能由人直接填写 `verified_at/result`，也不能引用 candidate/incoming 作为 published result。凡 `editable=true AND (capability=bidirectional OR room_model=shared)` 的 entry 无条件要求 single participant、两种关闭顺序、两类 terminal 交错和 exactly-one close-capture。stale policy 绑定 manifest/profile digest、OO/browser build、runner/source commit、authority model、bundle digest与 typed child digests，任一变化自动把 entry 退回 unverified。pilot 可复用 runner，不可复用 scenario/evidence entity。

## Writer / Resolver Migration Matrix

Wave 0/1 必须生成并人工裁决矩阵，至少覆盖：`wp_html_save.py`、专属 HTML save routers、上传/导入、WOPI、OnlyOffice callback、custom xlsx、F2 to/from OO、rollback、历史恢复、`wp_export/wp_file_resolver.py`、storage/version service。每行记录 read/write version domain、canonical resolver、authoritative model、definition bundle/candidate policy、是否调用 orchestrator、迁入 `ContentMutationService` 的任务与 characterization test。矩阵未归零时，base revision 与 bundle identity 仍不可信，禁止批量 adapter migration。

## Security and Failure Handling

| 阶段 | 失败 | 行为 |
|---|---|---|
| HTML flush | API/版本失败 | 停留 HTML；不 materialize |
| definition bundle/candidate | authority model/slot/digest 非法、child 未 approved、projection contract 缺 contract，或 artifact 仍为 candidate | 422 + 首个失败 slot；不 finalize、不打开 OO、不移动 pointer |
| OO health/config | 不可用 | 停留 HTML；可下载当前 published 版本但不假切换 |
| forcesave command | 非 200/超时/refresh-required/write fence/bundle 变化 | request error；保持 OO，可重试或重开 |
| callback auth | route token/room/generation/key/claim version 不符 | OO 非零 error；安全日志；不按 participant 猜作者 |
| callback correlation | userdata request 不匹配；或 status=2 无 userdata 时 close-capture/frozen bundle identity 非唯一、存在更高 request | incoming 可 durable，delivery ambiguous/unmatched；创建 recovery case，claim 前不创建 application/operation |
| recovery claim | prior confirmation/bundle/fence/contributor/当前授权任一错误 | case 保持可诊断或 quarantined/download-only；request/application/operation 均不创建 |
| recovery download-only | 当前 read/download 授权有效 | 只终结 case并授权 artifact 下载；永不创建 request/application/operation |
| callback download | SSRF/URL/大小/ZIP/路径异常 | OO 非零 error；删除 staging；pointer 不变 |
| incoming durable 后处理 | 已有关联 operation 的 extract/merge/rematerialize/final auth 异常 | OO error=0；operation error；incoming 保留可重试；无 operation recovery case 不进普通 retry |
| merge conflict | 同字段/保护字段 | operation conflict；不更新 projection/current pointer/server/client bases |
| merged≠incoming | live editor 未持有 server merged projection | commit server result 后 room refresh-required；禁止下一 forcesave并旋转 generation |
| rematerialize | roundtrip 或未管理区域变化 | application error；不提交 HTML projection |
| DB commit/finalize | projection/content version/approved bundle/representation/pointers/outbox 任一步失败 | 事务回滚；artifact/candidate 作为 orphan/non-current，不可见，原 pointer/revision 不变 |
| orphan GC | 引用或 legal hold 不确定 | 保留并告警；不得猜测删除 |
| outbox publish | Redis/handler 失败 | DB 已提交；outbox pending/failed 可重放，handler 不增 revision |
| Windows file occupied | `os.replace` 失败 | 可诊断 `FILE_IN_USE`；content/representation pointers 与 room 的 server last-applied/client-confirmed baselines 不变 |

callback URL 属不可信输入：只允许签名代理/allowlist，连接前后复核 DNS/IP，限制重定向，流式读取并在超限立即终止。OOXML 解压前检查压缩比、entry 数、展开总量、`../`、外部关系与宏。

`RetentionPolicyService` 从版本化配置读取每类 incoming/temp/candidate/conflict/recovery/evidence/trace/orphan 的 TTL、grace、legal hold 与访问角色，先 dry-run、再二次引用扫描、最后逐 artifact/case 写删除审计；无策略或引用不确定即保留并告警。`RedactionPolicy` 对日志、operation/recovery event detail、trace bundle 与 evidence 做字段 allowlist 投影，递归屏蔽 token/header/URL query/业务值和异常文本中的敏感片段。`AlertRuleRegistry` 固定每条规则的阈值、窗口、严重级别、dedupe key、recovery 与 runbook；规则覆盖 bundle/candidate/recovery/close singleton 并受 schema、变异和 synthetic event 测试。

## Capacity Budget

预算来自单一 `workpaper_sync_limits` 配置并被 contract/test 读取，禁止代码散落常量：compressed 50 MiB、expanded 512 MiB、ZIP entries 20000、compression ratio 100、table rows 100000、projection fields 200000。基准 operation（≤10 MiB、≤50000 fields）目标 incoming durable p95≤10s、applied p95≤30s。容量 profile 为 6000 登录会话、1200 active participants、120 同秒 forcesave burst、持续 20 applications/s×10 分钟；同 wp 串行、跨 wp 无全局锁。调整预算必须提交记录环境和测量结果的 capacity ADR，并同步 requirements/guards。

## Correctness Properties

### Property 1: 入口清册覆盖源码挂载点

源码发现的生产挂载点集合与 manifest mounts 集合相等；新增/删除任一挂载点未同步 manifest 必须打红。

**Validates: Requirements 1.1**

### Property 2: 能力态取值封闭

manifest capability 只允许四态，且每条均有可执行原因/evidence。

**Validates: Requirements 1.3**

### Property 3: 未注册 adapter 不得宣称双向

任一 `bidirectional` entry 必须解析到唯一 adapter、approved authoritative model 与非空 immutable definition bundle；`projection_contract` 还必须解析到 approved per-entry contract。删 adapter/bundle/contract 任一项后守卫打红。

**Validates: Requirements 1.4**

### Property 4: 业务内容版本与 representation generation 正交

状态/复核字段或纯 template/instrumentation/contract/bundle/OOXML 表示变化不改变 `content_revision`；一次业务内容应用恰好递增一次并同时发布绑定 approved bundle 的兼容 representation。纯表示升级先产生 non-current candidate，approved bundle finalize 后才新增 representation generation；旧 content version/representation/bundle 均不可变。

**Validates: Requirements 2.1**

### Property 5: staged artifact 与 DB pointer 不产生悬空可见态

在 artifact/candidate publish、bundle approval/finalize 及 DB transaction 任一点注入失败，current pointer 要么仍指旧 published version，要么完整指向已存在且绑定 approved bundle 的新 artifact；candidate 永不可见，无引用 artifact 最终进入 orphan GC。

**Validates: Requirements 2.4**

### Property 6: doc_key 与 mtime 解耦

同 room 修改文件 mtime 后 doc_key 不变；新 generation 即使 mtime 不变 doc_key 也变化。

**Validates: Requirements 2.7**

### Property 7: 全链统一 canonical resolver

config/download/callback/materialize/extract/rematerialize/retry/rollback/evidence 对同 content version + entry + representation generation 解析到相同 published artifact/path/hash、非空 immutable definition bundle 与 authority model；candidate 与当前 alias 均不得改变历史解析。

**Validates: Requirements 2.10**

### Property 8: HTML flush 失败阻断 OO

flush 抛错或未返回 revision 时 materialize API 调用次数为 0、编辑器挂载次数为 0。

**Validates: Requirements 3.2**

### Property 9: materialize 使用临时校验与原子发布

在 OOXML/roundtrip 校验任一点注入失败，current file hash/pointer/revision 均不变。

**Validates: Requirements 3.4**

### Property 10: 单次业务 commit 与 representation 幂等

相同 pending mutation token、Idempotency-Key、content base、approved immutable definition bundle/authority model 和 substrate 重复请求返回同 operation/content version/representation/room；token 跨 scope、过期或同 key 不同 payload 必须拒绝。仅 definitions/bundle 变化时先生成 candidate，approved bundle finalize 后可新增 representation generation但 revision 不变；unapproved/missing-contract bundle 不得 published/current，任何路径不得先提交 projection-only version再二次补 artifact。

**Validates: Requirements 3.6**

### Property 11: OO 打开前具备唯一 descriptor 且 ready 后服务端确认

前端只有取得 room/participant/doc_key/generation、server/client revisions、representation id/generation、artifact、write fence、authority model、非空 definition bundle id/digest/typed slots 与 config 后才创建 DocEditor；组件不得再次请求 config。`onDocumentReady` 后相同 identity 幂等确认才进入 editing/forcesave，篡改或陈旧 generation/representation/bundle/fence 必须 409，candidate descriptor 必须拒绝。

**Validates: Requirements 3.7**

### Property 12: forcesave request/命令不是完成凭证

DB transaction先按`(room,generation,initiated_by_participant_id,kind,Idempotency-Key)`冻结request、保存canonical `frozen_request_fingerprint`并创建`application_id=NULL`的operation shell，之后才允许调用Command Service；另一participant、不同kind或不同frozen payload复用同key必须409且不返回旧标识。HTTP 200后shell仍为accepted/waiting_application、application row数为0，bridge仍waiting_callback。incoming durable + request-first correlation后才可原子创建/命中application并绑定shell；未收到applied/conflict/refresh_required终态不得切HTML。recovery claim前则request/application/operation全为0。

**Validates: Requirements 4.1**

### Property 13: callback 超时保持 OO

等待超时时 mode 仍是 OO，错误可见且 retry 可用，reloadHtml 调用次数为 0。

**Validates: Requirements 4.4**

### Property 14: applied 后加载精确 revision

reloadHtml 参数和最终页面 revision 均不低于 operation 绑定的 `application.result_revision`；pre-bind shell 不得伪造 result revision。

**Validates: Requirements 4.5**

### Property 15: superseded/refresh-required room 或失效 lease 不能 forcesave

旧generation、refresh-required room或revoked/expired participant请求在Command Service前被拒绝。撤销writer无法取得OO drop证据时generation必须旋转，其他有效participant只可在新generation继续。尚未promotion的close leader被撤销/过期时，room-lock reconciler必须审计`authorization_stale`并按同eligibility snapshot选择稳定successor；无successor则显式supersede/recovery terminal，不能永久blocked或用system identity提交。

**Validates: Requirements 4.7**

### Property 16: callback claim version 真校验

篡改 callback claim version 必须在下载前失败；传 None 不得绕过。

**Validates: Requirements 5.2**

### Property 17: callback 文件先隔离校验

恶意ZIP、扩展名伪装、超限文件、SSRF/DNS rebinding和不可打开OOXML均不进入incoming durable目录。合法incoming只可成为`kind=incoming,state=durable`且resolver不可见；安全失败可登记`state=quarantined,durable_at=NULL`，但只能download-only/expire/retention，任何quarantined→durable、application FK、extract/merge/retry/rematerialize或representation绑定都必须失败。把任一incoming state改为published/current或以operation id作为recovery前置路径同样失败。

**Validates: Requirements 5.6**

### Property 18: delivery 可多次、frozen application 恰好一次

同一frozen request/incoming/bundle的status 6/status 2/网络重试可产生多delivery；不同request/Idempotency-Key也可能计算出同一application key。并发N个shell时必须只产生一个application、一个`application_id`非空且`duplicate_of_operation_id`为空的primary、N-1个`application_id=NULL/state=duplicate`且直指primary的可轮询terminal operations、一个applied revision/conflict set/outbox与零stranded`waiting_application`。application保留immutable `origin_request_sequence`并将N个request原子fold为最大`effective_request_sequence`；room latest durable fence必须指向该canonical application/effective sequence。删除duplicate pointer、指向duplicate、形成链/环、绕过当前授权、让duplicate再绑定application，或让同canonical application因自己的较高sequence被supersede均失败。durable correlated delivery必须绑定该application，operation为primary时自身application相等，为duplicate时canonical primary application相等；application/recovery ownership XOR，request/application不做XOR。`application_key`只存在application，operation不得复制。相同incoming但frozen base/representation/bundle/authority model不同不得合并，首次apply后room指针变化不改原key。close侧创建intent即`active→closing`；合法资格的single participant、两个participant两种关闭顺序及A ordinary forcesave terminal前/后B close交错最终恰有一个eligible close-capture。leader在promotion前revoke/expire时，合法successor仍产生exactly-one；无successor则零capture但必须原子进入superseded+recovery-required/authorization-stale终态。标准合法场景0或>1失败，无successor场景出现capture或永久blocked也失败；partial unique单独通过不算liveness。浏览器crash且无request时只产生durable recovery case，claim前request/application/operation均为0。

**Validates: Requirements 5.5**

### Property 19: 耐久后处理失败向 OO ack

incoming 已 durable 且正常 operation shell 已收敛为 primary，或已成为直指 canonical primary 的 terminal duplicate 后，extract/merge/rematerialize 抛错时 callback 返回 error=0；application/primary operation 进入 error，duplicate 仅在当前授权通过后跟随 canonical error/result，application 固定 incoming 可读取重试，content/representation pointers 与 room 双基线不变。若 delivery 尚未安全归组，则 callback 同样 error=0但只创建 recovery case：authorization-first claim 以相同 Idempotency-Key 并发 N 次，最多创建一个 recovery_claim request 与一个 operation shell，并创建或命中一个 application及 scope rows；commit 时 shell 必须成为绑定 application 的 primary，或保持 `application_id=NULL` 并成为直指 canonical primary 的 terminal duplicate，delivery/case 指向同一 canonical application。不允许 claimed-with-null-application、stranded shell、duplicate 链/环中间态。错误 prior confirmation、bundle、generation/fence 或只读/撤权/未知 contributor 均保持零三实体，download-only 亦然。

**Validates: Requirements 5.8**

### Property 20: generated col 占位不可注册生产 adapter

contract 含无语义 `col_[a-z]+` 且无人工 stable key/source_ref 时 registry 校验失败。

**Validates: Requirements 6.1**

### Property 21: contract 字段完整

每个 editable field 均有 stable key、JSON Pointer、OO 位置、value type、source_ref 和模式。

**Validates: Requirements 6.2**

### Property 22: 动态列 key 与 label 解耦

重命名公司 label 不改变 `{slot}_{seq}` key；重复 label 不发生键冲突。

**Validates: Requirements 6.4**

### Property 23: 动态行身份不使用下标

删除/重排/再新增后旧 row_uuid 不复用，原行数据不串到新行。

**Validates: Requirements 6.5**

### Property 24: 保护字段修改形成冲突

OO 修改 formula/auto-source 单元格时 current 公式和值不变，并生成 protected conflict。

**Validates: Requirements 6.6**

### Property 25: 不同字段自动三方合并

current 改 A、incoming 改 B，结果同时含 A/B 且 conflict_count=0。

**Validates: Requirements 6.8**

### Property 26: 同字段异值必冲突

base=A、current=B、incoming=C 时不得应用任一侧，冲突三值完整。

**Validates: Requirements 6.8**

### Property 27: delete/update 冲突不整表覆盖

一侧删行、另一侧改同 row_uuid 时只生成该行冲突，其他行照常合并。

**Validates: Requirements 6.9**

### Property 28: immutable definition 漂移 fail closed

改变 template/merge/formula mask、instrumentation identity、contract、authority model 或 definition bundle 任一受管 identity 后，旧 representation/operation 仍固定原 bundle；新请求在写入前失败并指出位置，除非按 DAG 显式发布新 definitions + approved bundle + finalized representation generation。只改 registry alias 不得改变历史 retry；bundle slot omission、非法 null marker或 projection contract 缺 contract 必须 fail closed。

**Validates: Requirements 6.10**

### Property 29: materialize/extract roundtrip

任一有效 projection materialize 后 extract，全部受管 editable 字段类型化相等。

**Validates: Requirements 6.11**

### Property 30: Word 只认 tagged SDT

删除 tag 或仅保留 placeholder 文本后 extract 必须失败，不得回退 paragraph index/regex。

**Validates: Requirements 7.1**

### Property 31: Word-only 正文保留

两次 HTML materialize 前后，所有 SDT 外 OOXML 正文节点规范化内容相等。

**Validates: Requirements 7.3**

### Property 32: Word 多实例异值冲突

同 stable tag 多实例出现不同值时生成 duplicate conflict，并列出全部 XPath。

**Validates: Requirements 7.4**

### Property 33: Word pilot tag 往返保留

真实 OO 9.4 打开/编辑/forcesave/重开后 tag 集合、层级和 row_uuid 集合不减少。

**Validates: Requirements 7.6**

### Property 34: SDT 丢失不降级

tag retention 失败时 operation error、incoming 保留、HTML 未变化，生产路径不调用段落索引提取器。

**Validates: Requirements 7.8**

### Property 35: 冲突记录双侧可追溯

每条冲突均能定位 JSON Pointer 与 OO cell/XPath，三方值和 kind 非空。

**Validates: Requirements 8.1**

### Property 36: 裁决 revision + incoming sequence 双 fence

裁决期间current revision、room generation、client edit epoch、definition bundle、conflict digest或room latest durable canonical application变化时按协议拒绝/rebase。若latest durable指向另一个effective sequence更高的canonical application，旧conflict superseded；若仍指向同canonical application但其effective sequence因same-key duplicate提高，服务端只规范化sequence并继续同一conflict set，不得自我stale或duplicate→primary循环。没有不同较新application但current变化时，返回按原immutable definition bundle/authority model重建的rebased conflict。

**Validates: Requirements 8.5**

### Property 37: 回滚创建新版本

回滚到 revision N 后 current revision 大于回滚前 revision，历史行与文件仍存在不变。

**Validates: Requirements 8.7**

### Property 38: durable incoming 可无 forcesave 重试

已有application/operation的extract失败后，普通retry只读取`application.incoming_artifact_id`且必须重验其`kind=incoming,state=durable`，并使用frozen definition bundle在同一primary timeline追加attempt；Command Service调用次数为0且不创建第二application/operation。quarantined incoming一律拒绝retry/engine消费。terminal duplicate仅在requested authorization与direct-primary invariant通过后canonicalize，并只要求primary绑定application。unmatched/ambiguous recovery case在claim前`operation_id/application_id=NULL`，普通retry必须拒绝；scope-index authorization-first claim成功后才在一个事务中创建request+operation shell并创建或命中application，commit前shell成为primary或direct duplicate。错误prior confirmation/fence/bundle/contributor的claim与download-only都保持零三实体，且均不要求OO重发durable incoming。

**Validates: Requirements 8.9**

### Property 39: config/callback Word 路径一致

通用 Word config 的下载 hash、definition bundle digest 与 callback 发布基线来自同一 published canonical version；candidate 或另一 bundle 不得被任一侧解析。

**Validates: Requirements 9.3**

### Property 40: 子码模板最具体匹配

每个登记 B 子码解析为自己的 DOCX；父级 XLSX 存在也不得抢占。

**Validates: Requirements 9.4**

### Property 41: 模板缺失不异类型回退

缺 DOCX 时返回明确 missing/type mismatch，resolver 不返回父级 XLSX。

**Validates: Requirements 9.5**

### Property 42: 路径安全

目录穿越、项目外绝对路径、软链接越界和跨项目复用均被 canonical repository 拒绝。

**Validates: Requirements 9.6**

### Property 43: 最终 commit 重验权限与 generation write fence

打开后撤销授权、改变 visibility/workflow lock、提升 write fence、supersede generation 或替换 current approved bundle，application 即使已 durable/已 rematerialize 也必须在 DB commit 前失败，current revision 与 server/client bases 不变。

**Validates: Requirements 10.10**

### Property 44: 只读/被撤销 contributor 零内容版本

只读 participant 不能发起 request；若聚合 callback contributor snapshot 含只读/被撤销 writer或归属未知且 generation 不安全，application、version、representation pointer、server/client bases、outbox 均不变并旋转 generation。

**Validates: Requirements 10.3**

### Property 45: 横向越权与撤权后幂等重放被拒

对pending-mutations、materialize、confirm-descriptor、forcesave、close-intents、recovery-cases list/claim/download-only、operations/conflicts/timeline query、resolve、rollback的每个opaque resource id，先提供显式project/wp/entry（recovery list另含room/generation）并且只允许读取`working_paper_sync_scope_index`。rollback必须携带immutable opaque `version_id` UUID；两个wp都存在numeric revision 1时scope rows不碰撞，numeric revision作resource_id或route key必须失败。将resource id与另一scope组合、物理删除/清空/篡改scope row、让child与scope row非同事务、child退役未同事务设置`retired_at`、复用任一retired `(resource_kind,resource_id)`或让rollback缺entry/version_id，均须失败；retired tombstone永久保留且其用户访问与不存在对象走同一404 oracle。不存在、跨scope、无visibility的响应envelope/guard stage/时序分桶与404 oracle一致；已确认visibility但缺action/workflow权限才为403。forcesave同key只有在`(room,generation,participant,kind)`相同且frozen request fingerprint等值时可重放；另一participant、不同kind/payload须409且不得泄露旧标识。首次成功后撤销access/lease、改变workflow/generation/fence/bundle，再用同key重放同样先拒绝并保持零泄露/零副作用；callback service route不混入该用户响应oracle。

**Validates: Requirements 10.6**

### Property 46: bridge 状态转换封闭

随机事件序列只能进入声明状态；非法转换抛显式错误且不改变 mode。unmatched/crash 只能进入 `recovery_pending` 且 operation 为空，claim 成功后方可转入 operation 流程，download-only 只能进入独立终态而不得转 `applied`。

**Validates: Requirements 11.2**

### Property 47: 编辑器只消费 descriptor 并暴露 durable API

挂载组件不自行请求 config，只消费含 approved bundle 的 descriptor，可 await forceSave，且 ready/dirty/saveRequested/incomingDurable/terminal/recoveryCase/error 事件各有真实触发路径；recoveryCase 在 claim 前不得带 operation id。

**Validates: Requirements 11.5**

### Property 48: 同步失败不被成功文案覆盖

任一真同步步骤失败后不得调用 success 文案，后续清理/reload 成功也不能覆盖 error。

**Validates: Requirements 11.10**

### Property 49: pilot 四类 Excel 均覆盖

manifest 中简单、D2、H1、G7 pilot 各至少一个 bidirectional entry，且有 approved per-entry contract/bundle、产物测试与真实 browser evidence；probe/pilot 未实际通过时必须保持 UNVERIFIABLE，不得因文档声明计为通过。

**Validates: Requirements 12.2**

### Property 50: custom 保持 xlsx 权威且进入统一 representation 协议

custom adapter 的 HTML/OO 修改都落同一权威 xlsx content artifact，标准 projection persist 不被调用；但必须使用 approved `custom_authoritative_ooxml`（或明确 opaque）authoritative model 与非空 bundle，contract/instrumentation 缺省用 typed null marker。room/request/durable ack/representation/evidence、same-incoming different-bundle identity 与最终授权 fence 仍完整存在。

**Validates: Requirements 12.6**

### Property 51: manifest/evidence 收口五个零

structural pre-reconcile 可报告未裁决、假双向、bidirectional 未验收、unreachable 与 evidence stale，而不以 stale=0 阻塞结构报告；只有全 entry required scenario rerun 与服务端 recomputation 后，真正 pre-delete eligibility/最终归档才要求未裁决、假双向、bidirectional 未验收、unreachable、evidence stale 五类计数均为 0。

**Validates: Requirements 12.13**

### Property 52: outbox 仅 commit 后发布

事务 rollback 时无事件；commit 后恰有一个 payload 完整事件，重放不重复副作用。

**Validates: Requirements 13.1**

### Property 53: replay 保留完整 payload

Redis typed event 中 wp_id/revision/operation/source/adapter 与 outbox 逐项相等。

**Validates: Requirements 13.2**

### Property 54: after-save 失败可重试

after-save handler 注入失败后 outbox 为 failed/pending 并可重放成功，不静默丢失。

**Validates: Requirements 13.4**

### Property 55: 真浏览器双向闭环

真实 OO 环境中 HTML 改值可在 OO 看到，OO 改值经 callback 后 HTML 显示且 revision 递增。

**Validates: Requirements 14.2**

### Property 56: 重复 callback 零多版本

status=6/status=2/同 hash 重试组合后 version/event/conflict 数均符合幂等期望。

**Validates: Requirements 14.3**

### Property 57: 变异四态准确

每个关键判据有命中唯一锚点的变异，预期测试名匹配；GREEN/MISS/WRONG 任一非零均不算通过。

**Validates: Requirements 14.7**

### Property 58: 客户端与服务端联合时序

联合trace/timeline证明`flush committed < approved-bundle representation published < descriptor mounted`，以及正常路径`request+operation shell committed(application_id=NULL,frozen_request_fingerprint) < command accepted < incoming durable < application created/hit + effective-sequence fold + delivery/shell bound < applied/conflict terminal < reload`。same-key higher request必须显示room fence与canonical application/effective sequence原子收敛，不出现primary self-stale。no-userdata crash另证明`incoming durable < recovery case(request/application/operation all null) < scope-index authorization-first claim atomic create+bind three entities`或`download-only(three entities null)`。缺服务端timestamp、application/bundle identity、shell bind/sequence-fold event或顺序颠倒即失败。

**Validates: Requirements 14.8**

### Property 59: 同 wp 串行跨 wp 并行

并发操作对同 wp 无丢更新，对不同 wp 不共享全局互斥；数据库锁而非进程锁决定正确性。

**Validates: Requirements 14.10**

### Property 60: 大文件预算 fail visible

对压缩 50 MiB、展开 512 MiB、20000 ZIP entries、100 倍压缩比、100000 行或 200000 fields 的任一边界做 N-1/N/N+1 测试；超限明确拒绝，进程内存受界且无静默截断。

**Validates: Requirements 14.11**

### Property 61: 所有 writer 进入唯一 revision 域

writer inventory 中任一生产内容写路径绕过 `ContentMutationService`、仍自行使用 `_version/file_version` 或直接 commit 时守卫打红。

**Validates: Requirements 2.2**

### Property 62: server last-applied 与 client-confirmed base 不混同

同 room application A 的 merged projection 等于 incoming 时，server/client base 可同时推进，后续 request B 冻结 A result。若 A merged≠incoming，则只推进 server last-applied，room=`refresh_required` 且 B 在 Command Service 前被拒；新 generation ack A representation 后才可继续，下一 incoming 不会回退 A 中服务器合并字段。

**Validates: Requirements 4.11**

### Property 63: shared room 聚合 callback 与 participant 撤销安全

同room两用户可贡献同一artifact，forcesave initiator、route credential与contributor rows分离。close intent在room lock下把participant `active→closing`，closing不再参与active writer仲裁；close barrier后禁止新join，reconciler只在predecessors安全终结后提升deterministic leader。leader在promotion前被revoke/expire时，旧intent审计为authorization_stale并在新eligibility epoch内按最高`(intent_sequence,id)`选择合法successor；同snapshot重放不换leader。无successor时generation显式supersede/recovery-required且零capture，不能永久blocked或用route identity。撤销任一writer且OO drop可证明时其outstanding request失效；无法证明时write fence提升、旧generation不应用、其余用户在新generation继续。

**Validates: Requirements 10.9**

### Property 64: application identity 使用 frozen bundle 且不含 status

`application_key`只能存在于`working_paper_content_application`；operation schema/ORM出现同名字段即失败。对相同room/generation/frozen client base+representation/incoming/immutable definition bundle+authority model，仅改变callback status、delivery order、request sequence或首次apply后room last-applied，application key不变，delivery key按status/discriminator变化。正常accepted时只能有request + `application_id=NULL,duplicate_of_operation_id=NULL` shell；incoming durable且request-first correlation后才创建/命中application。首个request写immutable `origin_request_sequence`；并发不同request命中同key时唯一winner绑定application，其余shell成为direct terminal duplicate，同时application `effective_request_sequence=max(all request sequences)`且room latest durable application/sequence原子指向它，N个shell最终1 primary+N-1 duplicates、无stranded或self-supersede。若base、representation、bundle或authority model任一不同，key必须变化，因此same incoming+different identity永不折叠。bundle/authority digests必须非空，可选child只通过typed null marker参与。callback含request id时须在application lookup前绑定验证该request。GET/retry/resolve必须先按requested operation重验scope/permission/write-fence/bundle；若requested duplicate的application为空则验证direct-primary后canonicalize，只要求canonical primary唯一绑定application。forcesave Idempotency-Key还必须绑定generation/participant/kind和frozen request fingerprint；跨participant/kind/payload复用返回409且不泄露旧标识。

**Validates: Requirements 5.5**

### Property 65: business projection 与同 revision representation 等值

任一applied/resolve content version的projection hash等于从其entry result published representation按application固定immutable definition bundle extract后的hash，且未管理区域与`kind=incoming,state=durable` substrate按policy等价；representation的bundle/authority model与application/result identity一致。quarantined incoming不得被application FK或任何engine读取，只可download-only/expire/retention。incoming永远non-published、resolver-invisible，只有新staged result经rematerialize+verifier+final authorization/eligibility后可publish。content version、representation、application identity与bundle均不可原地改写；candidate不得参与，merged≠incoming时client-confirmed base不推进。

**Validates: Requirements 8.10**

### Property 66: Excel identity 经真实 OO 往返保留

选定 hidden metadata/defined name/Table UUID 载体在编辑、插删、排序、复制、forcesave、下载、重开后满足 identity inventory 预期；任一缺失阻断 engine gate。

**Validates: Requirements 6.16**

### Property 67: template upgrader 先 candidate、approved bundle 后 finalize

任一存量 artifact 升级前置阶段只可产生 non-current candidate；candidate、unapproved bundle、missing/typed-null contract 的 `projection_contract` bundle 均不得成为 published representation、current pointer、resolver/room substrate 或 evidence。升级失败时 content/entry pointers 与 revision 不变；只有 per-entry contract、authority model 与 bundle 全部 approved，且 candidate 可见业务结构/projection/identity 等价后，才为同一 content version finalize 新 representation generation并能回滚旧 representation。任何纯 hidden upgrade 递增 content revision、改写旧 row、绕过 `template → instrumentation → contract → bundle → representation` 或把 candidate 暴露为 current 都必须打红。

**Validates: Requirements 6.18**

### Property 68: operation/recovery timeline 完整单调

operation、application sequence fold、close-intent eligibility变化与recovery case每次state变化各自在对应timeline中恰有一个sequence递增的transition event。normal shell correlation必须二选一：primary `application_id: NULL→id`有唯一`application_bound` event，或duplicate保持application空并有唯一terminal `duplicate` event/direct pointer；同key较高request还必须与application `effective_request_sequence`和room latest durable application/sequence同事务写`sequence_folded`，origin sequence不得改写，三者不得分叉。N个同key shell恰为1 primary+N-1 direct duplicates、无链/环/stranded/self-supersede。leader authorization stale、successor selection或no-successor recovery terminal均须append-only且同eligibility snapshot重放不产生第二event/capture。recovery claim前timeline不得关联operation/application，claim成功首批event证明三实体与canonical binding。删除中间event/pointer、伪造event、让identity/fence与timeline分叉或直接改current state后一致性守卫打红。

**Validates: Requirements 13.5**

### Property 69: evidence 由逐 scenario 实体与服务端重算闭合

对每个entry，服务端从source-backed manifest `editable/room_model/scenario_profile` + capability + immutable definition bundle + authoritative model推导required scenario set，逐项重算test run、recovery case、content application、operation、content version、published result representation、bundle/child definition、artifact、trace bundle及application/operation/recovery/close timeline外键/hash。集合无条件包含既有双向/identity/merge/conflict/dedupe/refresh/rollback，以及normal accepted shell→primary/direct duplicate、same-application higher-sequence fold不self-stale、cross-participant同Idempotency-Key 409、quarantined禁止application/engine、跨wp相同revision由opaque version_id无碰撞、no-userdata recovery claim、错误prior confirmation/fence/contributor拒绝、download-only零三实体。凡`editable=true AND (capability=bidirectional OR room_model=shared)`无条件要求single participant、两个关闭顺序、A terminal前/后B close与barrier reconcile的合法资格exactly-one；另要求leader revoke/expire交错覆盖“合法successor exactly-one”和“无successor zero capture + superseded/recovery-required terminal”。篡改profile/任一字段、遗漏场景、bundle不一致、download-only出现三实体、标准场景capture为0/>1、无successor场景产生capture/永久blocked，或只提供一条applied operation，validator必须拒绝。

**Validates: Requirements 12.10**

### Property 70: scenario/evidence 不得跨 entry 或跨场景复用

把 pilot scenario/trace/recovery case/application/operation 复制到另一 entry、另一 manifest scenario profile或另一 bundle，或用同一 application/operation 非法填充互不等价的 required scenarios 时，entry/profile/bundle/authority-model/application/operation/recovery/trace 外键或场景 oracle 校验失败，收口计数保持未验收。normal shell pre-correlation与primary-bound/direct-duplicate、claim与download-only不得共用伪application/operation；每个命中 editable/shared predicate 的 entry 必须拥有自己的四类 close scenario，不能复制另一 entry 的 close-capture。custom/opaque 的字段场景替换只能来自 bundle 中枚举 authority model，不能替换 close/recovery。

**Validates: Requirements 12.12**

### Property 71: evidence 随环境、runner 与 immutable definition bundle 变化失效

OnlyOffice/browser build、runner/source commit、manifest source digest、editable/room_model/scenario_profile、authority model definition、immutable definition bundle/typed child artifact、required scenario set 任一变化，旧 test run/evidence 自动 stale，capability 不再计入已验收；尤其不能把 profile 从 shared/multi 改成 single 来保鲜旧证据。structural pre-reconcile 可以如实报告 stale，且不得把 fresh=0 当作其前置条件；真正 pre-delete eligibility 只在全 entry required scenario rerun与服务端 recomputation 完成后评估。legacy/不可达桩删除改变 source commit 后，受影响 entry 必须产生新的 test run，完整重跑 required scenarios；只跑 smoke 不能恢复 verified。

**Validates: Requirements 14.16**

### Property 72: 量化容量模型可重复

6000 sessions、1200 participants、120 同秒 burst 与 20 applications/s 持续负载下无丢更新/全局锁；结果记录环境并满足预算或产生显式 capacity ADR。

**Validates: Requirements 14.10**

## Acceptance Oracle Matrix

每个 AC 必须由下列命名 oracle family 产生带 `ac_id` 的机器结果；范围表示同一 oracle family 的多个独立断言，不是用一条代表测试替代整段 AC。Task 8 生成逐 AC 展开矩阵，Task 72 校验没有悬挂、单任务自证或缺 evidence type。

| AC 范围 | Design oracle family | 核心判据 | Evidence type |
|---|---|---|---|
| 1.1–1.8 | `ManifestCoverageOracle` | 源码 mounts/editability/room wiring、独立 entry、capability、scenario profile、UI 与 closure count 双向一致 | manifest/profile digest + DOM/registry report |
| 2.1–2.12 | `ContentRevisionOracle` | business revision 与 representation 正交、所有 writer 单一 commit、room 双基线/close barrier、非空 definition bundle/authority model、resolver 与 replay-safe handler | DB transaction trace + writer/bundle/representation matrix |
| 3.1–3.9 | `HtmlToOoProtocolOracle` | flush mutation/单次 business+representation commit/approved bundle/descriptor 顺序，candidate/失败零挂载/零 pointer 变化 | operation timeline + artifact/bundle hashes |
| 4.1–4.12 | `ForcesaveLifecycleOracle` | participant/kind/generation 复合幂等 + frozen fingerprint、nullable-application shell、accepted/durable、application origin/effective sequence fold + room canonical fence、primary-bound/direct-duplicate terminal、close barrier/leader authorization-stale successor 或 recovery-required 终态、双基线 refresh/reopen、crash recovery | request/operation/application + callback/recovery timelines |
| 5.1–5.12 | `CallbackSafetyOracle` | room route claims、SSRF、stream limits、application-owned key、delivery归属、仅 durable incoming 可建 application/进入 engine、quarantined 仅 download-only/expire/retention 且不可 release、recovery claim/download-only、sequence/retention/失败语义 | security/delivery/application/recovery + DB/artifact snapshots |
| 6.1–6.20 | `ExcelContractIdentityOracle` | contract、authority model、typed bundle、stable identity、instrumentation、candidate/finalize、动态结构、保护字段与 roundtrip | workbook identity inventory + bundle/projections |
| 7.1–7.10 | `WordSdtOracle` | tagged SDT、row UUID、自由正文、approved bundle/resolver 清册与 tag retention | DOCX tag inventory + bundle/projection diff |
| 8.1–8.12 | `MergeRematerializeOracle` | 字段级 merge、canonical application + effective sequence + bundle fence、requested authorization → direct-primary invariant → canonical-primary application resolve、opaque version UUID rollback、representation 等值与 refresh-required | conflict records + before/after artifacts |
| 9.1–9.12 | `TemplateResolverOracle` | 权威模板、definition DAG/bundle、路径安全、candidate upgrader、共享文件隔离与单 resolver | resolver matrix + definition/bundle/upgrade report |
| 10.1–10.11 | `AuthorizationConcurrencyOracle` | 显式 project/wp/entry + scope-index-only pre-read、统一404/403时序、forcesave participant/kind/fingerprint 幂等冲突、opaque version UUID、room callback/participant分离、recovery claim、contributors、最终commit权限、撤销generation rotation与DB锁 | scope-index/auth call trace + recovery/lock/contributor traces |
| 11.1–11.12 | `FrontendBridgeOracle` | descriptor 单一来源、双基线/refresh 状态机、DOM 消费、文案与事件刷新 | mounted DOM test + browser network trace |
| 12.1–12.14 | `EntryEvidenceOracle` | 每entry裁决、source-backed scenario profile + bundle/authority-model推导逐scenario test run/trace、normal shell bind、每个editable/shared close exactly-one、crash recovery、服务端重算/新鲜度/五个零 | immutable evidence projection + manifest/profile counts |
| 13.1–13.10 | `TimelineOutboxOracle` | commit 后事件、append-only operation/application-bound/recovery transitions、完整 replay、retention/redaction/alerts | outbox/event timeline + observability report |
| 14.1–14.16 | `VerificationCapacityOracle` | 真实 OO、bundle/candidate/recovery 变异四态、逐 scenario 证据、量化预算/时延/容量与复原 | test-run/trace bundles + capacity/fault report |

## Testing Strategy

### 后端

1. domain/merge/property tests：纯三方规则、MISSING、保护字段、行增删重排，以及 authority model 封闭枚举。
2. repository integration：PostgreSQL 唯一约束、`FOR UPDATE`、事务回滚、typed bundle slots、candidate/finalize、scope-index child创建/退役同事务+tombstone不可删不可复用、forcesave `(room,generation,participant,kind,key)`唯一与 immutable frozen fingerprint、frozen request+pre-correlation shell、application-owned key、N个different-request同key收敛为1 primary+N-1 direct terminal duplicates且零stranded shell、同application较高request原子提升`effective_request_sequence`并与room canonical fence一致且不self-supersede、delivery `durable_at`归属CHECK与pre/post-durable error、application incoming仅durable、close barrier/最高`intent_sequence` leader/reconciler exactly-one（含两顺序、terminal前后交错、created_at扰动、promotion前leader撤权/过期后successor与无successor recovery-required终态）、opaque version UUID跨wp无碰撞。
3. file tests：真实 xlsx/docx zip、incoming durable sealing与resolver不可见、quarantined分支`durable_at=NULL`且不可release/转durable/建application/进入engine、candidate/canonical immutable原子发布、路径安全、ZIP bomb预算、Windows占用、retention/legal hold模拟。
4. adapter/definition tests：template→instrumentation→contract→bundle DAG、authority model、typed null marker canonical bytes、approved-child 守卫、模板 SHA/structure、materialize/extract roundtrip、字段类型。
5. callback/recovery tests：room route JWT、forcesave initiator/contributor、claim version、status 2/6乱序、正常request+shell→primary/duplicate收敛、same-application effective sequence fold、两个participant复用同key与不同kind/payload均409且不返回旧ID、duplicate requested授权→direct-primary校验→canonical-primary application query/retry/resolve、browser-crash no-userdata recovery case、single/two-user close barrier exactly-one、leader promotion前revoke/expire successor与无successor generation supersede/recovery-required、scope-index authorization-first claim幂等、错误prior confirmation/bundle/fence/contributor拒绝、download-only零三实体、nullable operation普通retry拒绝、SSRF、pre-durable下载/校验/落盘失败零owner、post-durable error保留owner及最终permission fence失败。
6. authorization tests：完整端点集合（含GET/list/query/download-only/`versions/{version_id}/rollback`）显式携带project/wp/entry，先只读scope index；删除/清空tombstone、retired id复用、横向id、numeric revision作route/scope key、两个wp同revision碰撞、业务/cache-before-auth、duplicate授权前canonical跳转、404/403阶段与时序分桶、成功后撤权重放零泄露均有调用顺序oracle。
7. event/ops tests：commit/rollback、normal shell primary application-bound或terminal duplicate、direct canonical约束、operation/recovery timeline、replay、DLQ、payload完整、RedactionPolicy、alert synthetic events。
8. evidence tests：从 source-backed manifest profile + capability + immutable bundle + authority model 推导 required scenario set，重算 test run/scenario/application/recovery/trace bundle外键/hash，拒绝跨 entry/场景复用、download-only伪三实体、same-app self-stale、跨participant幂等串用、quarantined engine消费、leader auth-stale永久阻塞、numeric revision寻址、close为0/>1、profile降级与stale。

### 前端

1. bridge 状态机 PBT：事件序列、bundle/candidate descriptor 与非法转换。
2. `GtOnlyOfficeSheet` mounted test：DocsAPI stub + API 实际顺序，不能只扫字符串；candidate/unapproved bundle 零挂载。
3. host integration：代表性 Excel/Word 宿主真挂 bridge，避免“组件写了但零宿主”。
4. conflict UI：字段分组、金额 store、裁决 payload、revision/bundle rebase。
5. recovery UI：显式 project/wp/entry/room scope 的 list/claim/download-only authorization-first network 顺序、错误候选零三实体、claim 后才可 retry、download-only 不显示回写成功。
6. manifest 守卫：源码 mounts/editability/room wiring ↔ manifest scenario profile ↔ registry/bundle ↔ generated frontend。

### 真实 OnlyOffice 9.4

Wave 0 先跑 Excel identity、Word SDT 与两用户 callback 聚合/撤销黑盒 probes，并保存 OO build/前后 artifact/identity inventory/callback payload digest；任一载体或撤销语义未取证，不得建设依赖它的 engine/authorization shortcut。pilot 与 bulk 使用 `start-dev.bat` 环境，Playwright 证据必须联合服务端 application/operation/recovery timeline/DB timestamps。每个 bidirectional entry 由服务端从 source-backed manifest profile + approved bundle + authority model 生成 required scenario set，持久化独立 run/scenario/trace bundle；真实场景至少含 normal operation-shell 的 primary/direct-duplicate 收敛、same-application higher-sequence fold不self-stale、两个participant同Idempotency-Key冲突且不泄露旧ID、browser-crash no-userdata recovery claim/download-only、quarantined不可进入application/engine，以及opaque version UUID rollback跨wp同revision无碰撞。凡 `editable=true AND (capability=bidirectional OR room_model=shared)` 无条件含 single participant、两种关闭顺序、A ordinary terminal前/后B close、leader promotion前revoke/expire后的successor与无successor recovery-required终态、exactly-one arbitration。无合法对象/环境或 probe 尚未执行一律标 UNVERIFIABLE；本设计不声称任何 probe 已验证。

### 性能与恢复

容量测试使用 Requirements 14.10–14.12 的固定 profile 和单一预算配置，记录硬件、worker、PG/pgbouncer、OO build、文件/字段规模。故障注入覆盖candidate/finalize或DB rollback后orphan、incoming durable sealing与误发布、quarantined误release/误进engine、进程退出、Redis/DLQ、OO timeout、Windows file lock、status 6/2乱序与callback重放、N个normal shell同key的primary/duplicate收敛中断、same-application effective sequence fold与room canonical fence提交中断、两个participant/kind/payload复用key、pre-durable failure零owner/post-durable error保留owner、scope retire/tombstone与跨wp同numeric revision、browser crash无userdata、claim事务中断、download-only、两个用户两种close顺序及ordinary terminal前后交错、`created_at`扰动下最高sequence leader、leader promotion前authorization-stale successor/no-successor分支与reconciler重入，以及same incoming+different bundle/authority model。

### 变异

变异覆盖至少：

- 恢复 mtime doc_key。
- callback 传 `claim_version=None`。
- callback 直接覆盖 target。
- callback 在绑定显式 request 前按 incoming 命中旧 application。
- 相同 incoming、不同 frozen base/representation/bundle/authority model 被错误折叠为一个 application。
- application key 在 callback 到达时读取 `room.last_applied`，使用 nullable contract/空串/全零 hash，存回 operation，或在 incoming durable 前预建 application。
- forcesave request退化为仅`room_id + idempotency_key`二元唯一、遗漏generation/participant/kind，cache hit不比`frozen_request_fingerprint`，另一participant或不同kind/payload复用key仍返回旧request/operation标识。
- 同application key的较高request未原子提升`effective_request_sequence`、room只推进raw sequence不保存canonical application、origin sequence被改写，或same-app fold使primary/conflict自我supersede。
- normal forcesave未先原子创建pre-correlation shell；N个different-request同key后出现多个primary、零primary、stranded waiting shell、missing/链式/循环`duplicate_of_operation_id`、duplicate再绑定application、resolve先要求requested duplicate绑定application或在requested授权前跟随primary；delivery owner gate错误使用terminal、pre-durable rejected/error被强制owner、durable零owner、post-durable error丢owner或request/application被错误XOR。
- clean-close允许null initiator/route identity代替participant授权，intent未原子`active→closing`，closing仍计active，leader改按`created_at`或非最高`(intent_sequence,id)`；promotion前leader revoke/expire后未写`authorization_stale`、同eligibility snapshot换leader、未按同一comparator选合法successor、无successor时未supersede generation并落`recovery_required`，reconciler未在ordinary terminal/revoke/expire后重入，或两名participant最终产生0/>1个close-capture。
- instrumentation canonical payload 反向包含 contract/bundle digest。
- bundle canonical payload 缺 authority/template/instrumentation/contract 任一 typed slot，或以字段缺失、JSON/SQL NULL、空串、全零 hash 代替 versioned typed null marker。
- `projection_contract` 使用 unapproved/missing contract bundle，upgrader candidate 或 incoming artifact 被 resolver/room/current pointer 当成 published representation；incoming state被写成published、`.incoming` sealing被称为publish，或rematerialize直接复用incoming row作result；quarantined被release/转durable、绑定application、进入extract/merge/retry/rematerialize，或其`durable_at`非空。
- merged≠incoming 后仍推进 client-confirmed base并允许下一 forcesave。
- callback 把 route participant 当聚合 artifact 唯一作者。
- 任一用户端点（含recovery list/download-only、operation/conflict/timeline GET与`versions/{version_id}/rollback`）缺显式project/wp/entry，未先查询`working_paper_sync_scope_index`，rollback用numeric revision作route/resource id或让两个wp相同revision碰撞，删除/清空/篡改scope tombstone、child退役未原子写`retired_at`、复用retired resource id仍成功，duplicate在requested operation授权前解析canonical primary，或在scope/visibility通过前读取业务资源、artifact、候选或Idempotency-Key cache。
- 不存在/跨scope/无visibility未走同阶段404，已知可见但缺action未走403，或响应时序分桶泄露对象存在性。
- 原请求成功后撤权，重放仍泄露旧 descriptor/config/operation/recovery case/artifact 存在性。
- recovery case在claim前预建operation/application，claim未原子创建request+operation shell及scope rows并创建/命中application，或事务提交时shell既非绑定primary也非direct terminal duplicate。
- browser crash no-userdata未建立recovery case；两关闭顺序/terminal交错产生多个或零eligible close-capture。
- claim接受错误prior confirmation/bundle/fence/撤权或未知contributor；download-only创建任一三实体；nullable operation被普通retry接受。
- HTML projection 与 materialize 分两次 content revision。
- 纯 instrumentation upgrade 递增 content revision、改写旧 representation，或未经 approved per-entry contract/bundle 直接 finalize candidate。
- conflict resolve 只比较raw request sequence、忽略canonical application identity/effective sequence、把same-app较高sequence判stale，或未按requested authorization → direct-primary invariant → canonical-primary application的固定顺序处理duplicate。
- operation retry 重新读取 registry 当前 alias/contract/bundle，而不是冻结 bundle。
- evidence用一条applied operation伪造全部scenarios，遗漏normal shell bind、same-app sequence fold、跨participant幂等冲突、quarantined消费拒绝、opaque version rollback碰撞、crash recovery/download-only、leader authorization-stale successor/no-successor、每个editable-shared entry的关闭场景，不记录application/bundle/profile digest，或把`editable/room_model/scenario_profile`改成single以错误复用旧evidence。
- structural pre-reconcile 错误要求 evidence fresh=0，或真正 pre-delete eligibility 在全 entry rerun 前判定通过。
- pre-delete eligibility 错误要求待删 unreachable 已为 0。
- legacy 删除改变 source commit 后仅跑 smoke 就把 stale evidence 标回 verified。
- forcesave HTTP 200 即切回 HTML。
- merge 改 last-write-wins。
- protected field 当普通 editable。
- Excel row key 改数组下标。
- Word tag 缺失时启用 paragraph fallback。
- outbox 改 commit 前 publish。
- host 仅 import bridge 不渲染/不调用。

判定使用失败测试名差集，不看退出码；CRLF 归一；锚点命中必须恰为 1；还原后 sha256 自证。

## Rollout and Compatibility

1. Wave 0 只做 inventory、characterization、Excel/Word identity、真实两用户 callback/撤销、Windows staged publish probes 与守卫；未过门不创建通用 engine 或 participant attribution shortcut。
2. migration/service 可先上线但 feature flag 关闭；回填 revision 0 不改业务值，并为 authority model、definitions、typed bundles、published representations 与既有 artifact 建 immutable baseline；同步建立forcesave复合幂等/fingerprint、application origin/effective sequence + room canonical fence、durable-only application FK、close eligibility successor/recovery-required及opaque version UUID约束。无法形成合法 bundle 的 entry 保持 single/unverified，不填空 digest；quarantined历史对象只保留download-only/retention，不迁成durable或application。
3. 先将全部生产 writer/resolver 迁入唯一 content revision 域，并锁死 business content 与 representation generation 分离，再启用 adapter；writer matrix 未归零时禁止 bulk。
4. pilot entry 单独启用；per-entry contract 与 approved bundle 形成前 upgrader 只产 candidate。旧逻辑仅在该 entry scenario evidence 通过后可局部删除，禁止长期双路；删除改变 source commit 后，该 pilot evidence 立即 stale，必须生成新 test run、完整重跑 required scenario set并经服务端 recomputation 后才恢复 verified。
5. old callback/config URL 委派新 service；旧 active session 只完成兼容关闭，不产生新协议 revision，随后 supersede。
6. template instrumentation 通过版本化 upgrader为既有 content version 生成 non-current candidate；只有 `template → instrumentation → contract → bundle` approved 后才 finalize 新 representation generation。不原地覆盖存量、不推进 business revision，也不运行时写模板库。
7. 每个 entry 的服务端 required scenario set 由 source-backed manifest `editable/room_model/scenario_profile` + capability + approved bundle + authority model 推导；所有 editable bidirectional/shared-room entry 无条件含 same-app sequence fold、跨participant幂等冲突、quarantined消费拒绝、opaque version UUID rollback、close liveness及leader authorization-stale successor/no-successor场景，全部通过后才标 bidirectional，代表 entry 仅作 pilot。
8. 最终采用 structural pre-reconcile → 全 entry required scenario rerun/evidence recomputation → pre-delete eligibility → 删除 → post-delete closure。structural pre-reconcile 允许报告 stale，不要求 fresh=0；真正 eligibility 才要求所有保留入口已裁决/已验收/evidence fresh，且每个 unreachable 唯一命中 source-backed deletion plan，不要求待删除 unreachable 预先为 0。删除 legacy/段落 fallback/不可达桩后重新生成 manifest/registry，按 source-commit stale 影响面再次完整重跑 required scenario/evidence recomputation。最终五类计数全为 0 后才可归档，不留 DEPRECATED 注释。

## Open Gates

实施前有四项真实环境门：

1. **Excel identity carrier**：hidden `_GT_SYNC`、defined names、Table/hidden UUID 在 OO 9.4 的插删、排序、复制、forcesave、重开后是否保留；未过门不建通用 Excel engine。
2. **Word tagged SDT**：tag/层级/row UUID 是否往返保留；未过门阻塞 F2 及全部 Word engine，不得降级 paragraph-index。
3. **真实两用户 callback/撤销语义**：forcesave initiator、callback route、OO `users/actions/userdata` 与聚合 artifact 贡献关系，以及 drop/revoke 后能否证明被撤销用户已移出；不明确时必须采用 generation rotation，禁止 participant-bound callback authorization。
4. **Windows staged publish/candidate finalize**：文件占用、DB rollback 与进程中断下能否保证 candidate 不可见、approved bundle finalize 后 pointer 不悬空、orphan 可回收。

这些 gate 当前均为待实测，不表示任何真实 OO probe 已通过。它们不阻塞 writer inventory、business revision/representation 语义、authority-model/bundle/candidate 数据模型、room/request/delivery/recovery/application 数据模型与测试骨架，但阻塞依赖具体 OOXML identity、candidate finalize 或多人 attribution 的 adapter/engine/authorization 分支。任何 probe 失败必须回到设计选择另一种原生载体或更保守 generation 规则并重新取证，不能以 fallback 绕过。
