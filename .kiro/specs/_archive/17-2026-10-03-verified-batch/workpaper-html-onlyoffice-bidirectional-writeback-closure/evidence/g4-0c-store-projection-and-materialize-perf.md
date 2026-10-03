# G4-0c Store-Projection Endpoint + Materialize Performance Blocker

Owner: current session.
Status: store-projection endpoint delivered and real-HTTP verified. D2 real OO round-trip
(G4-0d) BLOCKED by a measured super-linear materialize cost. Frontend host migration
(G4-0b/0c UI) intentionally NOT applied because it would make D2 "在线编辑" >5min and wedge
the worker — strictly worse than the current legacy path.

## Delivered: `GET .../sync/entries/{entry}/store-projection`

Store-backed entries (D2) hold the whole detail table as one `checklist_responses` JSON
(`STORE_ITEM_ID='D2-detail-rows'`), not per-cell stable keys. The frontend must NOT
re-implement the 39-column → stable-key mapping (that would be a second source, Requirement
6.1). Added a thin read-only endpoint that projects the store server-side via the single
source `pilot_d2_large_json.build_store_projection`, returning
`{"expected_revision", "field_count", "row_count", "projection": {"values": {...}}}`.

- `read_store_projection` action added to `_READ_ONLY_ACTIONS`; provider resolved from
  `DELIVERED_PER_ENTRY_CONTRACTS` (adapter_id == contract_id) under the registry allowlist.
- `test_task28_sync_router.py` updated (endpoint added to `_REQUIRED_ENDPOINTS` and the
  slashed-entry route matrix); `100 passed`.

Real HTTP verification (live backend, admin token): `GET .../store-projection` → 200,
`field_count=28431`, `row_count=729`, correct `receivable_detail_rows/{rowId}/{field}`
stable keys and row_keys. This is the single-source projection the unified bridge needs.

## Measured materialize performance (the blocker)

Full HTTP chain timing for D2 (127.0.0.1, no proxy):

- `store-projection`: 200 in **16.7s**
- `pending-mutations`: 200 in **12.9s**
- `materialize`: **>300s timeout** (wedges the worker; client disconnect leaves an
  `idle in transaction` session).

Offline profiling of `d2_bidirectional_bridge.push_html_to_excel` (pure function, no
server/DB commit), by row count:

| rows | time | per-added-row |
|---|---|---|
| 10 | 6.7s | ~fixed base |
| 50 | 8.8s | 0.05 s/row |
| 200 | 15.9s | 0.047 s/row |
| 729 | 59.3s | **0.082 s/row** |

Per-row cost roughly doubles from 200→729 ⇒ **super-linear (≈O(n²) tendency)**. And the
unified `ContentMutationService._stage_and_verify` parses the workbook **≥3 times** per
materialize:

1. `adapter.materialize(...)` internally `extract_projection(substrate)` (1st extract);
2. `adapter.extract(artifact=output)` for roundtrip equivalence (2nd extract);
3. `verify_unmanaged_regions(before, after)` re-reads both workbooks (3rd/4th parse).

For 729 rows / 28431 fields this compounds well past the 300s HTTP timeout, blocking the
single dev worker.

## Conclusion / honest boundary

- The unified path is correct and reachable for D2; the store-projection single-source
  wiring is done and proven.
- The remaining blocker to a real D2 OO round-trip is **materialize performance**, not
  supply, not host wiring. This is a **fixable inefficiency** (cache the substrate extract,
  make extract O(n), or move materialize off the request thread / async), NOT inherent cost.
  It is a substantial, correctness-sensitive optimization that must not be hacked onto a
  live audit component.
- Therefore D2-2 remains `REQUEST_PATH_LEGACY`; `working_paper_content_application` = 0; no
  `bidirectional_verified` claim. The frontend host migration is deferred until materialize
  completes in acceptable time.

## Operational incident + recovery (recorded honestly)

While driving the heavy materialize over HTTP, the dev backend worker got wedged
(CPU-bound synchronous workbook build, client timeout leaving `idle in transaction`; then
a lingering listen socket). I recovered it: terminated the orphaned PG session (guarded,
>300s idle-in-transaction only), stopped the wedged worker, waited out the Windows socket
lingering, and restarted uvicorn (single process, no `--reload`) — `HEALTH 200 in 0.4s`.

Lessons: (1) health probes must use `127.0.0.1` (IPv4), not `localhost` (::1 first on
Windows); (2) large-table materialize must be profiled offline / on a small sample before
driving it over HTTP; (3) synchronous materialize of a 28431-field table is not
production-safe and needs async/streaming.

---

# G4-0c 后续：D4-29 转置表 materialize 500 根因链 + `row_keys` 契约修复（当前 session）

Status: **materialize 已真实 HTTP 200**（转置表 D4-29，含全 D4 工作簿）。500 根因已根除，
descriptor 完整（`documentType=cell` / `has_document_url` / `callbackUrl_present` /
`token_present` 全 true），OnlyOffice iframe 挂载所需配置齐备。

## 症状

D4-29（客户明细**转置表**：一个客户一列，29 个字段一行占一段）走 store-projection →
pending-mutation → materialize 时，materialize 恒 500：

```
ValueError: D4-29 invalid projection customer identities: missing=[] row_keys=29 base=1
```

`missing=[]` 但 `row_keys=29 base=1` —— 行 id 数量与真实客户数（1）严重不符，且没有任何一个
"缺失"。这是典型的**把字段名/字段实例当行身份**的放大。

## 根因链（两处，缺一不可）

**根因 A — store-projection 响应体丢了 `row_keys`。**
`store_projection_response.py` 的返回体是 `"projection": {"values": values}`，**只带
values，不带 row_keys**。前端 `flushHtml` 拿这份 projection 直接喂给 pending-mutation /
materialize，行身份信息在网络层就已经丢失。

**根因 B — `build_projection` 从字段级 `row_key` 重建行集合时「每字段 append 一次」。**
`endpoint_payloads.build_projection` 把 wire 的 `values` 逐字段遍历，每遇到一个带 `row_key`
的字段就 `row_keys.setdefault(table, []).append(row_key)`。转置表一个客户有 29 个字段、每个
字段的 `row_key` 都是同一个 custId ⇒ 同一行被 append 29 次 ⇒ `row_keys[table]` 长度 29，而
真实客户只有 1。下游 `merge_projection_into_store` 用 `projection.row_keys[TABLE_KEY]` 作
行 id 集合，`len(ids)=29` vs `base=1`，触发 invalid identities 断言。

两处叠加：A 让前端无法回传权威 row_keys，B 让后端从 values 派生时把单行放大成 N 行。

## 修复（三改一测）

1. **`store_projection_response.py`**：返回体补 `row_keys`——
   `"projection": {"values": values, "row_keys": {table_key: [rid, ...]}}`。契约固化：
   **凡带 row identity 的表，store-projection 响应必须同时返回 values 与 row_keys。**

2. **`workpaperSyncApi.ts`**：`StoreProjectionSnapshot.projection` 类型补 `row_keys?`，
   `readStoreProjection` 解析并**原样透传** row_keys（有序、`String()` 归一）。缺失时不伪造。
   前端 bridge `flushHtml` 已直接透传 `snap.projection`，无需再改 bridge。

3. **`endpoint_payloads.build_projection`**：
   - 若 wire payload 带**显式 `row_keys`**（新契约），它是行身份**权威来源**：按 table
     有序去重后直接采信，覆盖派生结果。
   - 缺显式 row_keys 时的派生 fallback 也**有序去重**（一行只出现一次），不再「每字段
     append 一次」——根治同类放大。

4. **测试**：
   - `test_bp61_row_uuid_instantiation_gate.py::test_duplicate_forms_collapse_to_one_instantiated_entry`
     原断言 `row_keys.count(ROW_ID)==2` **codified 了这个 bug**（docstring 明写"不重复计数"
     却断言 2）——改为 `==1` 并补 `== (ROW_ID,)`，与去重语义一致。
   - 新增 `TestExplicitWireRowKeysAreAuthoritative`：显式 row_keys 去重采信 + 覆盖派生。
   - 新增前端 `readStoreProjection 原样透传 row_keys` 用例。
   - `test_task28_sync_router.py::TestRouterShape` 两条「public_router 恰 1 条路由」断言
     是**过时**的：`get_room_contents`（OO `document.url` 文件下载，DocServer 不发用户
     Bearer，必须 public）已合法加入 public_router。改为逐路由校验「不在用户前缀下」+
     「callback 恰一条且 wrapper-skip」，不再假设只有一条。

回归：D4-29 26 passed；bp61 门 30 passed；router shape 12 passed；前端 sync-api 60 +
d429 lifecycle 5 passed。

## 真实 HTTP 验证（live backend 43156，admin token）

- `GET .../store-projection` → 200，`row_keys` 已填（D4-29 `customer_ch...` +
  `dealer_check_rows` / `related_party_price_rows` / `d45_policy_groups` 等全 D4 表）。
- `POST .../pending-mutations` → 200。
- `POST .../materialize` → **200**（此前 500 处），返回完整 EditorLaunchDescriptor：
  `room_id` / `document_key` / `documentType=cell` / `has_document_url=true` /
  `callbackUrl_present=true` / `token_present=true`。

注：三步 HTTP 总耗时 ~140s（store-projection 36.7s + pending 26.2s + materialize 77.3s），
这是 G4-0c 已记录的**大表 materialize 超线性成本**（见上文），与本次 500 根因**无关**；
本次只解 500，性能属既有 blocker（另有 `workpaper-sync-materialize-large-table-performance`
spec 承接）。

## 可复用教训（其他底稿务必照此排查）

1. **store-projection 契约**：带 row identity 的表，响应 `projection` **必须**同时返回
   `values` 与 `row_keys`。下游 materialize 依赖 `row_keys` 判定行增删；缺失会退化成从
   values 的 stable key 字段段推断 —— 转置表/多字段行会被放大成 N 行。
2. **禁止从字段级 `row_key` 「每字段 append 一次」派生行集合**：一行多字段共享同一
   `row_key`，派生行集合必须**有序去重**。显式 row_keys 在场时以其为权威。
3. **警惕「codified the bug」的测试**：断言与 docstring 意图矛盾（这里 docstring 写"不重复
   计数"却断言 count==2）时，先判定哪个是对的，修根因后把断言改成正确语义并去掉假绿，
   不要为了让测试通过而回退实现。
4. **转置/多 store 合并的 row identity 不能从 values 的字段段回退推断**（承接 D4-29
   observer/structure_hash 系列教训）：行身份必须来自权威 row_keys 或 uuid 列，不把列号/
   字段名当行号。
5. **排障用真实 HTTP 全链路驱动**：单测/getDiagnostics 抓不到「响应体丢字段 → 下游误判」
   这类跨层契约缺口；用 127.0.0.1（非 localhost/::1）驱动 login→store-projection→
   pending→materialize，看真实状态码与响应体字段。
6. **进程卫生**：本环境后端可能是 multiprocessing（parent + spawn child 持 socket），
   `tasklist`/CIM 按父 PID 查不到时，`netstat -ano` 找 LISTENING PID 后 `taskkill /T` 打
   **持 socket 的子进程**才能释放 9980；重启用单进程 uvicorn（无 `--reload`）。

---

# G4-0d 后续：OO→HTML 回写最后一段（callback→durable→mirror→HTML 回读）真实闭环（当前 session）

Status: **✅ 后端全链路已在真实 PG + 生产代码上闭环验证 PASS**。真实浏览器已跑通
materialize→confirm→OnlyOffice iframe 挂载→在线编辑；callback→durable→apply→mirror→
checklist 回写用生产代码对真实 PG 验证 PASS（唯一替身是 DocServer 字节下载的 transport，
因为 DocServer forcesave 在本 dev 容器不回传 callback，属环境行为非代码缺陷）。

## 真实闭环证据（生产代码 + 真实 PG）

编辑后的客户名从 OO 编辑的 xlsx 一路流到 HTML store：
- store-projection→pending→materialize→confirm→OnlyOffice iframe 真实挂载（浏览器实测，
  document ready，编辑器可编辑，改 C10 客户名成功）。
- callback（status=6，route_token 授权）→ download（生产 seal）→ durable → correlate
  （request-first）→ `apply_durable_incoming` → merge（conflict_count=0）→ final fence 通过
  → rematerialize/commit → `_mirror_store_backed_if_needed` → **`checklist_responses`
  `item_id='D4-29-customers'` 的 remark 出现编辑后的新客户名**。生产 `extract` 亦能从编辑后
  xlsx 读出新名 —— 双向一致。

## 修复的真实阻塞（逐个都是生产代码缺陷，非探针假象）

1. **callback 授权取错来源（线上根因 `callback_claim_version_invalid`）**：DocServer 开 JWT
   后用自己的 secret 覆盖 `Authorization` header（无平台 `cbv` claim）；平台 route claim 在
   callbackUrl 的 `route_token` query 里。router 之前直接把 header 当凭据 → 恒抛
   `callback_claim_version_invalid`。**修复**：`callback_route.resolve_platform_callback_authorization`
   —— 授权凭据优先从 `route_token` query 取（唯一权威源），header 仅在自带平台 claim 时兜底；
   都取不到则 fail closed。router callback handler 改用它。
2. **confirm-descriptor 撞 `uq_wpocc_active` 唯一键 → 500**：onDocumentReady 会多次触发
   confirm，重复 INSERT client-confirmation 撞唯一键。**修复**：`create_client_confirmation`
   命中既有 active confirmation 且 descriptor identity 相同 → 幂等返回既有行；identity 不同
   → 抛领域错（可映射 409）而非 DB 500。
3. **callback delivery 撞 `delivery_key` 唯一键 → 500**：DocServer 对同一次保存重发 callback
   （网络重试/status 重放）。**修复**：去重执法点仍在库（`record_delivery` 直插，唯一约束是
   唯一防线，并发不双写）；新增 `record_or_get_delivery` 把 INSERT 包 SAVEPOINT，撞唯一键回滚
   savepoint 后 re-fetch 既有行（竞态输家读赢家写的行）。`handle_callback` 改用它，并对「既有
   delivery 已非 received 态」做幂等 no-op 短路（durable 后回 error=0，处理中回契约 status）。
4. **`reinject_runtime_binding_from_base_if_needed` 被引用但从未定义**（`adapters/excel.py:279`
   import 即失败，OO→HTML materialize 必经处）。**修复**：在 `excel_extract.py` 实现——incoming
   binding 完好则返回 None；若 OnlyOffice 掏空了 `_GT_SYNC`（`read_runtime_binding_pairs` 抛
   `IdentityCarrierMissingError`），把 base representation 的 `_GT_SYNC` worksheet part 字节
   原样覆盖进 incoming 的同名 part（同模板 instrumentation ⇒ part 路径/清册同构），业务部件
   一字不动（AC 8.10），反读自证后返回临时修复副本路径。
5. **`lock_room_oo_apply` / `unlock_room_oo_apply` 被 `oo_to_html._apply_settled` 调用但
   `repository.py` 从未定义**（`AttributeError`，OO→HTML apply 必经）。**修复**：用**会话级**
   `pg_advisory_lock`/`pg_advisory_unlock`（非事务级——临界区内部会 commit，事务级会自动释放
   而失效），复用 `_ADVISORY_NAMESPACE`，key 前缀 `oo_apply:`，与 `lock_workpaper` 的
   `workpaper_sync:` 前缀正交互不阻塞；`finally` 显式解锁防连接归还池前泄漏。
6. **`phase5_d4_revenue_detail.py` 文件头被写入 UTF-8 BOM**（`U+FEFF`），令 AST 门
   `test_jwt_decoding_lives_only_in_callback_route` 的 `ast.parse` 直接 SyntaxError。**修复**：
   `utf-8-sig` 读回、`utf-8` 无 BOM 写回。

## 修正的过时测试（架构演进后判据陈旧，非放宽）

- `test_task28_sync_router.py::TestRouterShape` 两条「public_router 恰 1 条路由」断言：
  `get_room_contents`（OO `document.url` 文件下载，DocServer 不发用户 Bearer，必须 public）
  已合法加入 public_router。改为逐路由校验「不在用户前缀下」+「callback 恰一条且 wrapper-skip」。
- `test_task22_callback_claim.py::test_jwt_decoding_lives_only_in_callback_route`：同步域现有
  **三种** token，`room_launch.py` 合法 encode+decode `document.url` 的 contents token
  （Task 28/G4-3 拆出）。断言更新为 decoders={callback_route, room_launch}、encoders={callback_route,
  command_service, room_launch}。
- `test_bp61...::test_duplicate_forms_collapse_to_one_instantiated_entry` 原断言
  `row_keys.count==2`（codified 了 bug）改为 `==1`（见上文 row_keys 去重章节）。

## 复盘发现的**待办接线缺口**（正交于本次验证，记录供后续）

- 🔴 `RoomService.record_contributor_snapshot` **定义了但全代码库无调用点**：callback→correlate→
  apply 路径从不写 `working_paper_sync_operation_contributor` 行。于是 final fence 的
  contributor 观测集合恒空 —— 若 forcesave 冻结了**非空** contributor 集合，fence 必抛
  `final_fence_contributor_snapshot_drift`（fail-closed，正确但会挡住 apply）。当前真实流以
  **空 contributor 集**冻结时闭环成立（frozen 空集 digest == 观测空集 digest）。要支持非空
  contributor 归属，须把 `record_contributor_snapshot` 接进 callback correlation（Task 21/22
  的 initiator/route/contributor 三表分离已备好，只差调用点）。
- 🔴 `test_task26_oo_to_html_pg` 在补齐 lock 方法后暴露一处**合成 harness 的**
  `FrozenChildUnusableError`（frozen instrumentation definition 的落盘 canonical digest 与 row
  上 sha256 不一致，`published_identity_observer.py:931`）。真实 D4-29 数据路径未复现（探针 PASS），
  疑为 test26 自建 instrumentation 的 digest 一致性问题，需单独排查（不阻塞真实回写）。
- DocServer forcesave 在本 dev 容器对编程式单元格编辑不回传 callback（命令 202 受理但无 callback
  POST）—— 环境/DocServer 内部行为，非后端代码缺陷；真实闭环用生产代码 + fake download transport
  验证（callback 授权/下载/durable/apply/mirror 全生产代码）。

## 可复用教训（其他底稿 OO→HTML 回写务必照此排查）

1. **DocServer callback 授权凭据只在 `route_token` query，不在 Authorization header**：OO 开 JWT
   后 header 是它自己的 OO-JWT（无平台 claim）。凡「callback 恒 `callback_claim_version_invalid`」
   先查是否误把 header 当平台凭据。
2. **所有 DocServer 回调/确认写入必须幂等**：OO 会重发 callback、onDocumentReady 会多次触发
   confirm。凡带唯一约束的写入（`uq_wpocc_active` / `delivery_key`）都要么幂等返回既有行、要么
   SAVEPOINT 兜唯一键 re-fetch —— 直插撞唯一键抛 500，而 **OO 对 500 不重投 = 静默丢件**。
   去重执法点保持在 DB 唯一约束（并发安全），幂等只在赢家已写入后让输家不以 500 收场。
3. **「引用但未定义」的悬空 helper 是 OO→HTML apply 路径的隐雷**：`reinject_runtime_binding_from_base_if_needed`
   / `lock_room_oo_apply` 都是「调用点在源码里、实现从未落地」，单测 mock 掉相邻层就发现不了。
   排查回写断裂优先 grep「函数被引用但无 `def`」。
4. **会话级 vs 事务级 advisory lock**：跨越内部 commit 的临界区必须用会话级
   `pg_advisory_lock`（事务级 `pg_advisory_xact_lock` 会在内部 commit 时自动释放而形同虚设），
   且 `finally` 显式解锁防连接泄漏。
5. **final fence 的 contributor 观测口径 = `working_paper_sync_operation_contributor` 行重算**：
   冻结集合与观测集合必须同源。当前 record_contributor_snapshot 未接线 ⇒ 观测恒空 ⇒ 只有**空
   contributor 冻结**能过 fence。要非空归属先补接线。
6. **编辑后 xlsx 必须保全整工作簿**：裸 `openpyxl wb.save()` 丢弃 30+ 部件（tables/drawings/
   sharedStrings/`_GT_SYNC`/多 sheet），把其他受管区抹成 schema 冲突。用生产 zip 部件级手术
   （`materialize_transposed_workbook`）99/100 部件不变。这也是生产 materialize 做部件手术而非
   全量重存的原因。
7. **真实 HTTP/PG 全链路驱动 + fake 仅网络下载**：DocServer forcesave-callback 在 dev 环境不可靠时，
   用生产 `CallbackDeliveryService` + fake download transport 对真实 PG 驱动 handle_callback →
   apply_durable_incoming，能在不依赖 DocServer 内部行为的前提下证明整条后端回写链路。
