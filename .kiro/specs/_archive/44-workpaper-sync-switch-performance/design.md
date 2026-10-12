# 底稿 HTML ↔ 在线编辑切换提速 — Design

## §1 现状 grep 确认（动手前逐项核对）

| 事实 | 位置 | 对设计的影响 |
|---|---|---|
| 复用判据只认 `projection_sha256 == payload_sha256` | `materialize_coordinator._find_business_identity_reuse` | 骨架行差异即永不命中 ⇒ P1 在其后加第二判据 |
| 未命中归因 `verdict_for_miss` 把骨架差异记成 `content_changed` | `materialize_reuse_verdict.py` | P1 命中时走 `hit`，归因函数不改（避免把表示腿的失败误判成缺陷） |
| overlay 以 store 行集合为准，丢基线骨架行（有意决策） | `projection_first_publication.overlay_store_on_baseline_projection` | 不改 overlay（改它会改所有 store 型 entry 的首版 / 物化输入） |
| extract 把任何有 UUID 的行读回；materialize 永不收敛骨架身份 | `excel_extract._scan_row_identities` / `excel_materialize` | 骨架行在 OO 侧恒在 ⇒ 比较口径必须骨架无关 |
| roundtrip 已对「骨架 ∧ 未声明」的多出字段豁免 | `content_mutation._assert_roundtrip_equivalent` | P1 用同一真源 `contracts.is_template_skeleton_identity` |
| store 读取单一真源 | `store_projection_response.read_store_payload` | P2 指纹与 P5 投影都从它取，同一份字节 |
| pending-mutations 用浏览器 POST 回来的 projection | `wp_sync_router._materialize_request` | P5 在服务端构造同形 projection（走 `_flatten_projection_values` → `build_projection` 往返保摘要同源） |
| create_pending_mutation / materialize 可同会话背靠背调用 | coordinator 各自 commit；token TTL 10 min | P5 端点直接复用两步，不写第二套编排 |
| 复用路径 `_settle_reuse` → `_open_room_and_descriptor` → `_apply_operation(stage=…)` | coordinator | P2 快路径同形新方法，零 revision |
| 基线提取缓存键 `contract_id:artifact_sha256`（未含契约版本 / binding） | `store_projection_response._overlay_with_published_substrate` / `parse_cache` | P4 补齐键 |
| 三方提取 3 次整册 extract、无缓存 | `oo_to_html.extract_three_way` | P4 去重 |
| callback 在同一请求内 durable commit 后内联 apply；前端等 `applied` 才回表单 | `wp_sync_router.post_room_onlyoffice_callback` / `WorkpaperSyncEditorHost.scheduleReturnToForm` | P3 前端提前回表单，后端不改 apply 调度 |
| leave 在 request 为 `correlated` 期间 409 | `rooms.leave_participant` / `_OPEN_REQUEST_STATES` | P3 加「延迟离开」意图，由终态结算同事务执行 |
| 单 uvicorn worker | `start-dev.bat` / `docker-compose.yml` | P6 评估项 |
| 两份已归档性能 spec 已做 O(N²)→O(N)、单趟物化、解析缓存、锁外计算；**否决**「只反读写过的格」 | `_archive/15-…/workpaper-sync-materialize-large-table-performance`、`_archive/39-oo-html-writeback-performance` | 本 spec 不动内核算法，只做流程层去重与跳过 |

## §2 P0 计时

- 新模块 `sync_timing.py`：`timing_scope(kind, **labels)` 上下文管理器（ContextVar），`mark(phase)` 记相邻耗时；退出时 `logger.info("[sync-timing] …")` 一行 JSON。无作用域时 `mark` 为 no-op（零侵入）。
- `ApplyJournal.record()` 顺带调用 `mark(stage.value)`（journal 结构不变：`entries` 仍是二元组，现有按二元组解包的代码与判据不受影响）。
- router：`materialize` / 新端点 / `_apply_durable_incoming` 各开一个 scope；coordinator 在 preflight / 复用判定 / 提交 / 开房间处 `mark`。
- 前端：桥在 `attemptSwitchToOnlyOffice` 与挂载 / 就绪 / 确认处打 `performance.now()`，汇总成只读 `switchTimings`。
- 工具 `scripts/analyze/report_sync_switch_timings.py --wp <id>`：读 operation / application 表列最近 N 次切换的 created→finished 与 durable 延迟（事件时间是事务开始时间，工具注明口径）。

## §3 P1 骨架无关业务身份

新纯函数模块 `business_identity.py`：

```
skeleton_insensitive_identity(payload, *, declared) -> dict
business_identity_equal(base_payload, incoming_payload) -> bool   # declared = incoming 的 row_keys
```

规范形（对 `_projection_payload` 产物）：

1. `schema_version / contract_id / semantic_version / document_type` 原样。
2. 每张表 T：`order = [r for r in rows if not skeleton(r)]`（严格保序）；`skeletons = sorted(r for r in rows if skeleton(r) and r in declared[T])`。
3. values：丢弃「row_key 是骨架身份 ∧ 不在 declared[key 的表段]」的键；其余原样（value / value_type / mode / row_key）。

**正确性论证**（命中 ⇒ 复用与全量物化等价）：全量物化只写投影里声明的行与字段，永不收敛骨架身份；
声明了的骨架行按身份落位（实测：HTML 全量物化后 OO 侧骨架行仍在原物理位置）；非骨架行序与所有值严格相等；
表示腿（当前 representation 挂在基线 content version 上）照旧校验 ⇒ 全量物化的产物在受管格上与当前 representation 相同，复用即等价。
未声明骨架行里若有用户在 OO 填的内容，全量物化同样不会动它（不收敛）⇒ 复用不比全量物化更差（既有行为，不新增分歧）。

接入：`materialize()` 在 `_find_business_identity_reuse` 返回 None 后调用 `_find_skeleton_equivalent_reuse`（读基线落盘 payload，与 `_classify_reuse_miss` 同一读法），命中 ⇒ `_settle_reuse(..., verdict=ReuseVerdict(hit, differences=("template_skeleton_equivalent: …",)))`。

## §4 P2 + P5 服务端直取 + 指纹直通

### 4.1 端点

`POST {USER_SYNC_PREFIX}/materialize-from-store`（action `materialize_from_store`，写名单；必填 Idempotency-Key；body `{sheet_key, client_edit_epoch}`）。
业务住新模块 `store_materialize.py`，router 只 guard / 映射状态码 / `_attach_launch_urls`（与 `/materialize` 共用尾段 helper）。

### 4.2 流程

```
guard → registration（R14 目标绑定）→ target_sheet
→ read_store_payload → fingerprint F = sha256(canonical{multi, payload, contract_sha, adapter_id, schema})
→ 指纹表命中 (wp, entry) 且 F 相同 且 记录的 content_version == preflight.base_content_version
     ⇒ coordinator.reuse_for_unchanged_store(...)：open_operation → open_room_and_descriptor → apply(stage="store_fingerprint_reused")
→ 否则：provider 构造 store projection → overlay（基线缓存）→ flatten → build_projection（与客户端路径逐字节同源）
     → authorize_create → create_pending_mutation → authorize(token) → materialize（含 P1）
     → **仅当复用命中**（判词 hit ∧ business_identity_reused）才记录 F ↔ (content_version, artifact_sha)；提交 / 重放 ⇒ 清掉记录
```

- 指纹表 = `parse_cache` 风格的进程内 `BoundedLruCache`（键 `(wp_id, entry_id)`）。重启 / 发版清空 ⇒ 代码变更不会让旧指纹误命中。
- 快路径零 revision（`assert_revision_delta` 照跑），判词 `hit`（differences 注明 store 指纹直通），指标落既有 `REUSE_METRIC`。
- 🔴 **为什么提交后不记**（实施时修正，原稿写的是「成功后记录」）：提交产生的新版本来自本次投影，但「从新 substrate
  重新构造的投影是否仍等于它」取决于 materialize→extract 往返是否不动点 —— P1 修的正是它在 D2 上不成立。提交后就记，
  等于把一次没做过的校验当成做过。代价只是提交后的下一次多走一趟正常路径（真库实测：该趟复用命中、零 revision）。
- 状态码按**阶段**映射：store 阶段（manifest / 读 store / 构造投影）的域错误包成 `StorePhaseRejectedError`，原样保留
  `error_code` 与文案、一律 422（与 `GET store-projection` 同口径）；物化阶段原样抛出，走 `classify_materialize_rejection`
  （与 `/materialize` 逐字同一映射，未登记 ⇒ 500）。原稿「store 域错误一律 422」会把物化阶段未登记的失败从 500 降成 422。
- 非 store 型 entry ⇒ 422 `entry_not_store_backed`（`StoreProjectionNotBackedError` 的真实 error_code；原稿误写成
  `store_projection_not_backed`）/ `provider_module_not_allowed` ⇒ 前端据此回落客户端路径。

### 4.3 前端（宿主零改动）

- `workpaperSyncApi`：新增 `materializeFromStore(scope, {sheetKey, clientEditEpoch, idempotencyKey})`；新增
  `withServerStoreFlush(scope, fn)`：作用域内同 scope 的 `readStoreProjection()` 不发请求，返回带哨兵对象的快照。
- 桥：`flushPendingWrites()` → `withServerStoreFlush(scope, flushHtml)`：
  - 宿主没调 readStoreProjection ⇒ 原路径（用宿主自己的 projection）；
  - 调了且原样返回哨兵 ⇒ `materializeFromStore`；
  - 调了但改写了投影 ⇒ 不拦截重跑一次 `flushHtml()` 走原路径；
  - 服务端 422 `entry_not_store_backed` / `provider_module_not_allowed` ⇒ 同上回落原路径（并按 entry 记住，本会话不再试）；
    `materialize_substrate_not_published` ⇒ 首版后整链重走（与 R7 同一逻辑）。
- 拦截是**一次性**的、且只认同 scope（project / wp / entry 三段全等）：第一次匹配的读取消费掉它，其后同 scope 的读取照常发请求。
  哨兵投影带一个不存在的 stable key（非空）——万一被当成真投影 POST 出去，服务端按契约拒收（fail visible），且 client 的
  `createPendingMutation` / `materialize` 在发出前就拒绝哨兵。
- 状态机不加新状态：响应回来后依次 `pending_mutation_created` → `descriptor_received` → `descriptor_accepted`。

## §5 P4 去重复提取

- `parse_cache.projection_extract_key(adapter, contract, artifact_sha256)`：仅 `ExcelSyncAdapter` 精确类型；
  键 = `x2:{contract_id}:{contract.canonical_sha256}:{profile}:{sha}`，profile = 提取相关输入的摘要（entry / bundle / adapter_build /
  identity_inventory / business_sheets / dynamic_column_keys / binding / sibling_bindings / limits）；substrate 形态与 baseline 不进键（只影响门禁与 findings）。
- overlay 改用新键；`extract_three_way`：base 读缓存，current 与 base sha 相同则复用同一对象（journal 照记 current_extracted + 其 representation id），不同则读缓存；incoming 不缓存。
- 提交成功后（publish 完成）把 roundtrip 的 `extracted` 按发布 artifact sha 写入缓存；失败路径不写。
- 等值守卫：命中与冷提取逐字节相同；同 contract_id 不同 canonical 内容的键不同；oo_to_html 与 html_to_oo adapter 对同一字节同键同值；缓存对象经 overlay / merge 后不变。

## §6 P3 先回表单

- 后端：participant 加 `leave_requested_at`（V185/R185）；leave 端点支持 `defer_until_settled`：仅当未终结 request 全为 `correlated`（incoming 已 durable）时登记意图并返回 `leave_deferred`，其余照旧 409；
  `request_settlement.settle_requests_of_terminal_application` 结算后执行已登记的离开（同事务、锁序 room → request → participant）。
- 前端：桥新状态 `html_pending_apply`（mode=html）；`returnToFormWhileApplying()` 发延迟离开、清 descriptor、由桥持有的追踪器跟到终态：
  applied/refresh_required ⇒ 按 result revision 重载并回 `html_idle`；conflict / error ⇒ 横幅入口。宿主只读 = `readonly || state === 'html_pending_apply'`。
- 详细状态边与宿主接线清单在实施时现扫补入本节（宿主约 17 处 + 共享 `useGRenderModeSwitch`）。

## §7 拒绝方案

- 改 overlay 让 store 侧补骨架行：反转既有有意决策，影响所有 store 型 entry 的首版 / 物化输入与 roundtrip 判据。
- 改 extract 丢弃纯模板行：extract 是校验仪器，历史 OO 版本含骨架行 ⇒ 下次合并会看到删除。
- 改 `projection_sha256` 口径：历史摘要与 pending / settlement 三处同源，改一处即全链路失配。
- 指纹落库：需迁移且发版后旧指纹可能在新代码下误命中；进程内 LRU 天然随发版失效。
- 常驻隐藏编辑器：每页占一个 OO 连接（授权 / 内存），6000 人目标下不划算。
- 纯手动「点刷新才回写」：慢的部分只是挪位置，且带来两侧分叉、下游读旧数（见 requirements 背景）。

## §8 P6 进程池 ROI 评估（实施结论：不做）

第一批（P0~P5）已把 HTML→OO 切换的服务端耗时从 13.9~15.2s 降到 ~0.2s（指纹直通）/ ~1.5s（首次无指纹，含 store 读取 + 投影构造 + 协调器复用命中）。到 OO 编辑器确认可编辑的端到端耗时约 3.3~4.4s，其中 ~3s 是 OnlyOffice DocsAPI 自身的加载时间（服务端无法干预）。

在此基础上，进程池预热的收益分析：

| 路径 | 服务端耗时 | 进程池能省的 | 占端到端比 |
|---|---|---|---|
| 指纹直通（无改动再切） | ~200ms | ~0ms（不过 extract） | 0% |
| 首次无指纹 | ~1500ms | ~0ms（build_projection 已走线程池） | 0% |
| 全量物化（store 变了） | ~1600ms | ~0ms（同上） | 0% |
| OO→HTML merge（保存方向，非切换） | ~22s | ~13s（三次 extract 各 ~4s，去重省一次） | N/A（不在切换路径） |

结论：进程池对切换路径零收益（第一批已消除了所有 extract）。OO→HTML 方向的 extract 去重（P4）可独立做，但与切换体验无关。

## §9 `.json.gz` 明文发现

`store-projection` 的投影产物文件名为 `.json.gz`，但实际存储为**纯 JSON**（4.29 MB，gzipped 约 183 KB）。这不影响正确性（读写两侧都不做解压），但命名有误导性。记录在此，不在本 spec 修正。

## §10 P4 / P3 延后评估

**P4 去重复提取**：收益在 OO→HTML（保存）方向的 merge 路径上，不在 HTML→OO 切换路径上。当 base 与 current 指向同一 representation 时省一次 ~4s extract（22s→18s），值得做但与本 spec 核心诉求「切换提速」独立。建议另立 spec。

**P3 先回表单**：改善的是「保存后回表单」的体感（从等 applied 才回到 incoming durable 即回），需要后端迁移（V185 `leave_requested_at`）+ leave 端点参数 + request_settlement 联动 + 前端新状态 `html_pending_apply` + 17+ 宿主只读绑定 + 横幅组件。工作量大且完全独立于切换提速。建议另立 spec。

