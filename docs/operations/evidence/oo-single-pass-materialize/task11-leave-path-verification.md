# 任务 11 验证证据：participant 主动离开（leave 路径）

**spec**：`oo-single-pass-materialize-and-room-leave` · 任务 11
**验收**：Requirements 4.1 / 4.2 / 4.3 / 4.4 / 4.5 · Properties **P7 / P8 / P9**
**日期**：2026-09-22　**环境**：win32 · Python 3.12.8 · pytest 8.4.2 · 真 PostgreSQL（`audit_platform`）
**结论**：任务 11 **实现与判据均已到位**；本轮补一条判据缺口（见 §4）后 51 条后端 + 10 条前端判据全绿，
且逐条经生产侧变异反证（见 §5）。

---

## 1. 后端判据：verbatim pytest 输出

命令（`cwd=d:\GT_plan\backend`）：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_participant_leave_endpoint.py tests/workpaper_sync/test_participant_leave_pg.py -q --tb=short -rf -p no:randomly
```

### 1.1 首轮（改动前的原样验证，50 条）

```
..................................................                       [100%]
============================== warnings summary ===============================
..\..\GT_workplan\.venv\Lib\site-packages\schemathesis\generation\coverage.py:305
  D:\GT_workplan\.venv\Lib\site-packages\schemathesis\generation\coverage.py:305: DeprecationWarning: jsonschema.exceptions.RefResolutionError is deprecated as of version 4.18.0. If you wish to catch potential reference resolution errors, directly catch referencing.exceptions.Unresolvable.
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
50 passed, 1 warning in 10.55s
```

分布：`test_participant_leave_endpoint.py` **27 条**（形态 / AST 判据，不连库）+
`test_participant_leave_pg.py` **23 条**（真库行为，scratch schema `tmp_leave_<hex>`）。
`test_ran_on_real_postgresql_in_scratch_schema` 与 `test_no_phase_crashed_during_collection`
均 PASSED ⇒ 确实跑在真 PostgreSQL 上、且 9 个采集场景无一崩溃（没有「读到缺失数据仍然绿」）。

### 1.2 末轮（补完 §4 的判据缺口后，51 条）

```
...................................................                          [100%]
================================ warnings summary =================================
..\..\GT_workplan\.venv\Lib\site-packages\schemathesis\generation\coverage.py:305
  D:\GT_workplan\.venv\Lib\site-packages\schemathesis\generation\coverage.py:305: DeprecationWarning: jsonschema.exceptions.RefResolutionError is deprecated as of version 4.18.0. If you wish to catch potential reference resolution errors, directly catch referencing.exceptions.Unresolvable.
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
51 passed, 1 warning in 10.12s
```

---

## 2. 验收子条款 → 判据 node id 映射表

文件简写：`E` = `backend/tests/workpaper_sync/test_participant_leave_endpoint.py`；
`P` = `backend/tests/workpaper_sync/test_participant_leave_pg.py`；
`F` = `audit-platform/frontend/src/components/workpaper/sync/__tests__/cleanCloseWithoutSaving.spec.ts`。

| # | 子条款 | 覆盖判据（node id） | 判定 |
|---|---|---|---|
| ① | 状态迁移 `active` → `left` | `P::test_the_participant_really_lands_on_left_with_a_timestamp`（真库落 `state=left` + `left_at` 非空 + `revoked_at`/`oo_drop_confirmed_at` 仍空）；前提 `E::TestTheStateMachinePremise::test_active_and_closing_may_both_reach_left` | **PASS** |
| ①b | 状态迁移 `closing` → `left` | `P::test_closing_may_also_leave`（转换表第二条边真的通；且从 `closing` 走也不动 room） | **PASS** |
| ② | **不**建 request 行 | `P::test_ac_4_1_no_request_no_close_intent_of_any_kind`（forcesave / close_capture / close_intent 三张表全数 0，happy + idempotent 两个 room）；结构侧 `E::TestLeaveDoesNoneOfTheCloseBarrierWork::test_no_request_no_barrier_no_generation_rotation[service]` 与 `[repository]`（AST 禁用调用名单，对「加了但这次没走到」同样红）；**观测者反证** `P::test_the_side_effect_counter_can_actually_see_a_request_row`（本轮新增，见 §4） | **PASS**（原为 GAP，已闭合） |
| ③ | **不**推 barrier | `P::test_property_7_not_one_room_column_changed`（room 行 17 列逐列比对，含 `state` / `close_barrier_epoch` / `close_leader_intent_id` / `close_leader_eligibility_epoch`）；`P::test_ac_4_3_the_room_stays_active_when_another_editor_remains`；`P::test_the_replay_does_not_touch_the_room_either`；结构侧 `E::…::test_not_one_room_column_is_assigned[service]` / `[repository]` | **PASS** |
| ④ | **不**旋转 generation | `P::test_property_7_not_one_room_column_changed`（比较面含 `generation` / `write_fence_epoch`，且断言分母不塌：`{state, generation, write_fence_epoch, close_barrier_epoch} ⊆ ROOM_COLUMNS` 且 `len ≥ 17`）；结构侧 `E::…::test_not_one_room_column_is_assigned[*]`（`_FORBIDDEN_ROOM_COLUMNS` 含 `generation`） | **PASS** |
| ⑤ | 幂等且分支**显式**（第二次走可区分的代码路径，不是蒙对） | `E::TestTheIdempotencyBranchIsExplicit::test_the_current_state_is_compared_before_assert_transition`（存在「比 `ParticipantState.left` 且 `return`」的 `if`，**且**它在源码上早于 `assert_transition`）；`P::test_property_9_repeating_leave_writes_nothing_at_all`（第 2、3 次 leave 发出的 participant `UPDATE` 语句数 = **0**，观测在 `before_cursor_execute` 上）；`P::test_property_9_the_replay_returns_the_very_same_result`（`already_left` False→True→True、`left_at` 逐字相同、participant 行逐字段相同）；`E::…::test_the_replayed_flag_reaches_the_response`（`replayed` 来自 `outcome.already_left`，重放在响应上可见 ⇒ 可区分路径）；边界 `P::test_an_illegal_start_state_is_refused_not_swallowed`（`revoked`/`expired → left` 必抛 `StateTransitionError`，不被幂等分支吞掉）；观测者反证 `P::test_the_statement_witness_can_actually_see_an_update`（第一次 leave 必须被看到恰 1 条 UPDATE，否则「零条」恒真） | **PASS** |
| ⑥ | dirty **被拒** | `P::test_property_8_dirty_is_refused_and_writes_nothing`（`ParticipantDirtyLeaveError` + `error_code=participant_leave_refused_dirty` + 被拒前 0 条 UPDATE + 行仍 `active`/`left_at` 空）；`P::test_the_dirty_gate_is_the_only_reason_that_call_was_refused`（同一 participant 在 `dirty=False` 下立刻能走 ⇒ 不是「永远拒绝」）；`E::TestAuthorizationFirst::test_the_two_refusals_are_409_with_distinct_error_codes`；前端同源 `F::有未保存改动 ⇒ 一律 refuse，且不发任何请求` | **PASS** |
| ⑦ | authorization-first，且「无权限」与「不存在」同一 404 oracle | 顺序：`E::TestAuthorizationFirst::test_guard_is_the_first_await_in_the_handler`（`_guard` 是 handler 第一个 await）、`test_both_the_room_and_the_participant_are_declared_refs`（两个 ref 都过 scope index 交叉比对）、`test_the_actor_is_passed_from_the_guarded_scope_not_from_the_body`（`actor_user_id` 只能来自 `scope.user_id`）；同一 oracle：`E::…::test_the_not_owned_participant_gets_the_very_same_404_envelope`（`_sync_http(ParticipantScopeNotVisibleError)` → 404 且 `detail == EXTERNAL_NOT_FOUND_DETAIL == _not_found().detail`，且 detail 里不含 `participant` 字样）、`E::…::test_all_three_codes_are_registered_in_the_single_mapping_table`（未登记会落 422 兜底 ⇒ 变成存在性预言机）；行为侧 `P::test_only_the_owner_may_leave_and_all_three_misses_share_one_error`（`not_my_lease`「存在但不是你的」/ `cross_room` / `absent` 三种全部收口到同一异常类型 + 同一 `error_code`，连 message 前缀都不得分型）；反空转 `P::test_a_failed_probe_leaves_the_victim_untouched` + `P::test_the_owner_can_still_leave_after_those_probes` | **PASS** |

### 2.1 映射表之外的附带判据（不属于任务 11 条文，但同批全绿）

* 路由形态：`E::TestRouteShape::*` —— POST、挂在显式三段 scope 前缀下、真实带斜杠的
  四段 `entry_id` 唯一命中且不被贪婪吞后缀、`leave_room` 在 `_WRITE_ACTIONS` 而不在只读白名单、
  生成契约里 `idempotencyKey == "absent"`。
* 事务边界：`E::TestTransactionBoundary::*`（service/repository 都不 commit；handler 恰 1 次
  commit + 1 次 rollback）＋ `P::test_the_service_only_flushes_so_a_rollback_undoes_the_leave`
  （回滚后回到 `active` —— 比 AST 多一层）。
* AC 4.4 的第二半（in-flight）：`P::test_property_8_an_outstanding_request_blocks_leave` /
  `test_the_in_flight_gate_is_scoped_to_that_participant`（别人的未终结 request 不得挡住我）/
  `test_once_the_request_is_terminal_leave_goes_through`；名单单源
  `E::TestTheOpenRequestStatesAreSingleSourced::*`。

---

## 3. 接线确认：端点注册 + 前端调用

### 3.1 端点与注册（「router 不在 registry ⇒ 前端 404」这条铁律显式核对）

| 事实 | 文件:行 | 内容 |
|---|---|---|
| 端点 handler | `backend/app/routers/wp_sync_router.py:1496` | `async def leave_room(` |
| 路由装饰器 | `backend/app/routers/wp_sync_router.py:1494-1495` | `@router.post(USER_SYNC_PREFIX + "/rooms/{room_id}/participants/{participant_id}/leave")` |
| action 登记 | `backend/app/routers/wp_sync_router.py:333` | `"leave_room"` 在 `_WRITE_ACTIONS` |
| registry import | `backend/app/router_registry/workpaper.py:340` | `from app.routers.wp_sync_router import router as wp_sync` |
| registry 挂载 | `backend/app/router_registry/workpaper.py:406` | `app.include_router(wp_sync, tags=["渲染"])` |

⚠️ 任务描述里写的 `backend/app/services/.../wp_sync_router.py` 有误 —— router 实际在
`backend/app/routers/wp_sync_router.py`（`app/services/workpaper_sync/` 下是 `rooms.py` /
`repository.py` 这两层实现）。

注册**不经**自动加 gate 循环（`wp_sync` 与 `wp_sync_public` 同 `wp_onlyoffice_public` 一样显式
单独 `include_router`）：理由写在 registry 的注释里 —— `dedicated_wp_gate` 是 router-level
依赖，会把 AC 10.6 规定的「scope index → visibility」顺序倒过来；本 router 内部用
`WpGateVisibilityProbe` 调同一个 `enforce_wp_gate`，可见性判据一份不少。

`E::TestRouteShape::test_a_real_slashed_entry_id_routes_to_it` 是这条注册的**行为**侧反证：
它用真实四段 `entry_id` 走 `route.matches(scope)`，断言唯一命中且 `entry_id` 原值解出 ——
路径模板写对但转换器错（默认 `[^/]+`）时端点在生产上恒 404，形态判据抓不到，这条能。

### 3.2 前端接线

| 事实 | 文件:行 | 内容 |
|---|---|---|
| `leaveWithoutSaving()` 定义 | `audit-platform/frontend/src/components/workpaper/sync/useWorkpaperSyncBridge.ts:1373` | `async function leaveWithoutSaving(): Promise<void> {` |
| 真的调 leave 端点 | 同上 `:1390` | `await api.leaveRoom(scope(), { roomId, participantId, dirty: dirty.value })` |
| API client | `…/sync/workpaperSyncApi.ts:534` | `export async function leaveRoom(...)` → `endpoint: 'leave_room'`，`params: { room_id, participant_id }` |
| 生成契约 | `…/sync/workpaperSyncContract.generated.ts:84` | `"endpoint": "leave_room"` / `"method": "POST"` / `"idempotencyKey": "absent"` |
| 可观测计数 | `…/useWorkpaperSyncBridge.ts:403-410` | `leaveCallCount`（leave 的失败被刻意吞掉，所以「有没有真发过」必须另有观测面） |

两处细节值得记：① `dirty` 显式送 `dirty.value` 而不是写死 `false` —— 写死会让服务端那道
同源 dirty 门永远收不到能触发它的输入，变成死代码；② leave 失败**不**阻断返回表单、也不记
`lastError` —— 它只是一次 lease 释放，失败的后果是退回「等 `expires_at` 自然过期」那个旧形态。

### 3.3 「零请求」判据已按 AC 4.5 更新，并实跑

判据文件：`…/sync/__tests__/cleanCloseWithoutSaving.spec.ts`。文件头第 15-17 行明文写着
「**恰一次 `leaveRoom`、零次 forcesave、零次 close-intent**」，测试名同款；正文三段各自钉一个数：

* `expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)` + `leaveCallCount === 1` + 入参逐项
  `{ roomId, participantId, dirty: false }`；
* `expect(h.api.requestForcesave).not.toHaveBeenCalled()` + `forcesaveCallCount === 0`；
* `expect(h.api.createCloseIntent).not.toHaveBeenCalled()`；
* 再加一圈**逐 api 成员比调用次数**（`leaveRoom` 是唯一允许 +1 的成员）⇒「换个端点凑数」挡得住。

仓库里剩下的「零请求」字样只在**叙事性注释**里（`useWorkpaperSyncBridge.ts:1371`、
`workpaperSyncBridgeMachine.ts:179/184` 讲这次切换的来历），没有任何判据仍按旧口径断言 ——
grep `零请求|零次请求|一个请求都不发` 全仓核对过。

命令（`cwd=d:\GT_plan\audit-platform\frontend`）与结果：

```powershell
npx vitest run src/components/workpaper/sync/__tests__/cleanCloseWithoutSaving.spec.ts --reporter=dot
```

```
 RUN  v3.2.4 D:/GT_plan/audit-platform/frontend
 Test Files  1 passed (1)
      Tests  10 passed (10)
   Duration  2.12s
```

---

## 4. 本轮找到并闭合的判据缺口

### 4.1 🔴 GAP-1（实质）：「不建 request 行」的真库判据是**空转**的

**现象**：`P::test_ac_4_1_no_request_no_close_intent_of_any_kind` 是子条款②唯一的行为判据，
它断言三个计数 `== 0`。但这三个计数由采集函数 `_side_effect_counts()` 产出，而全采集里
**没有任何一处证明这个函数看得见行** —— happy / idempotent 两个 room 本来就该是 0。

**实证**（把 `room_id` 过滤换成随机 UUID，即一个永远看不见任何行的观测者）：

```
tests/workpaper_sync/test_participant_leave_pg.py
-   .where(WorkpaperForcesaveRequest.room_id == room_id)
+   .where(WorkpaperForcesaveRequest.room_id == uuid.uuid4())
```

```
.......................                                                  [100%]
23 passed, 1 warning in 9.87s
```

**23 条 PG 判据全绿** ⇒ 该条确属空转。同一文件对 `_StatementWitness` 是有正对照的
（`test_the_statement_witness_can_actually_see_an_update`），side-effect 计数器却漏了这一层。

**闭合**：场景 E（in-flight）是全采集里唯一真的插入了 `WorkpaperForcesaveRequest`
（`kind=forcesave`）的 room —— 把它的 `side_effects` 收进快照，新增正对照判据：

* 新增 `P::test_the_side_effect_counter_can_actually_see_a_request_row`
  —— `forcesave_requests == 1`（基础计数 + `room_id` 过滤真的命中）、
  `close_capture_requests == 0`（`kind` 过滤会**分型**，不把 forcesave 行冒充成 close_capture）、
  `close_intents == 0`。
* `test_ac_4_1_…` 的 docstring 加一句指回这条正对照，说明它的非空转前提在哪。

**残余局限（诚实记录）**：`close_intents` 那一格仍没有独立正对照 —— 本采集里
`working_paper_oo_close_intent` 表始终为空，要造一行需要 `client_confirmation` FK 前提，
而 `create_close_intent()` 本身会改 room / 推 participant 到 `closing`，为一个计数器造它不划算。
它的可信度来自两处：① 同一函数、同一 session、同一过滤写法已由 `forcesave_requests == 1`
反证；② 「不建 close intent」这半条另有**已变异反证**的判据把着 —— room 行逐列比对
（M4b 抓到 `close_barrier_epoch: (0 → 1)`）与 AST 禁用调用名单（M2a 抓到 `create_close_intent`）。

### 4.2 GAP-2（诊断质量，非覆盖）：dirty / in-flight 拒绝的「没抛」形态撞 KeyError

**现象**：变异 M6（放宽服务端 dirty 门）之后，`P::test_property_8_dirty_is_refused_and_writes_nothing`
确实红，但红在 `KeyError: 'type'` 上 —— 因为场景 D 的 `refused` 初值是空 dict，异常没抛时
那个键根本不存在。同样红，但读的人看不出红在哪条语义上；而同文件的场景 F/G 探针写法是
「成功时显式记 `{"type": None}`」。

**闭合**：场景 D / E 的初值改为 `{"type": None, "error_code": None, "message": ""}`，
让门被放宽时落成一条**有名字**的判据失败而不是 KeyError。覆盖面不变，与文件既有约定对齐。

### 4.3 未发现缺口的子条款

①①b③④⑤⑦ 六条经 §5 的变异反证逐条确认为承重判据，未做改动。
特别地，⑤「显式分支」这条**不是**靠注释声明的：`E` 里那条判据同时要求存在比较 `left` 的
`if` 且其 body 有 `return`，并要求它在源码上**早于** `assert_transition` —— M5 实测抓到。

### 4.4 改动清单

只改了一个文件（生产代码零改动）：

* `backend/tests/workpaper_sync/test_participant_leave_pg.py`
  * 场景 E 快照加 `side_effects`；
  * 新增 `test_the_side_effect_counter_can_actually_see_a_request_row`；
  * `test_ac_4_1_…` docstring 补非空转前提说明；
  * 场景 D / E 的 refused / blocked 初值改为显式「没抛」形态。

---

## 5. 变异反证（每条：改生产 → 实测红 → 还原）

生产文件全部**逐字还原**，还原后 `git status` 只剩 §4.4 那一个测试文件为 modified
（`rooms.py` / `repository.py` / `wp_sync_router.py` / `useWorkpaperSyncBridge.ts` 均不在 diff 里）。

### 5.1 后端（`-q --tb=line -rf -p no:randomly`，基线 50 passed / 补完后 51 passed）

| 变异 | 改动 | 实测 | 打红的判据（节选原文） |
|---|---|---|---|
| **M1** 不落 `left` | `repository.mark_participant_left`：删 `participant.state = ParticipantState.left.value` | **11 failed / 39 passed** | `E::…test_the_only_participant_columns_written_are_the_leave_facts`：`AssertionError: ['left_at', 'updated_at']`；`P::test_the_participant_really_lands_on_left_with_a_timestamp`：`assert 'active' == 'left'`；`P::test_closing_may_also_leave`：`assert 'closing' == 'left'` ⇒ 子条款①①b 承重 |
| **M2a** leave 顺手提升 close barrier 仲裁（**不可达**分支） | `rooms.leave_participant` 里加 `if dirty and not dirty: await self._repo.create_close_intent(...)` | **1 failed / 49 passed** | `E::…test_no_request_no_barrier_no_generation_rotation[service]`：`RoomService.leave_participant 调了 ['create_close_intent'] —— 那是 close barrier 仲裁在做的事` ⇒ AST 判据对「加了但这次没走到」同样红（子条款②的结构侧承重） |
| **M3** 顺手改 room.state（design P7 原文反证） | `mark_participant_left`：`room = await self.lock_room(...)` + `room.state = RoomState.close_barrier.value` | **5 failed / 45 passed** | `E::…test_not_one_room_column_is_assigned[repository]`：`给 room 写了 ['state']`；`P::test_property_7_not_one_room_column_changed`：`leave 改了 room 的这些列: {'state': ('active', 'close_barrier')}`；`P::test_the_replay_does_not_touch_the_room_either`；`P::test_closing_may_also_leave`：`从 closing 离开也不得动 room` ⇒ 子条款③承重，且证明 `_room_row` 快照**能检出变化**（非空转） |
| **M4** 旋转 generation + 推 barrier | `mark_participant_left`：`room.generation += 1` / `room.close_barrier_epoch += 1` | **22 failed / 28 passed** | `E::…test_not_one_room_column_is_assigned[repository]`：`给 room 写了 ['close_barrier_epoch', 'generation']`；PG 侧多数场景崩在 doc_key/FK 前提上，由 `P::test_no_phase_crashed_during_collection` 显性打红（fail-closed 生效） ⇒ 子条款④承重 |
| **M4b** 只推 barrier（干净变异） | `mark_participant_left`：仅 `room.close_barrier_epoch += 1` | **4 failed / 46 passed** | `P::test_property_7_not_one_room_column_changed`：`leave 改了 room 的这些列: {'close_barrier_epoch': (0, 1)}`；`E::…[repository]`：`给 room 写了 ['close_barrier_epoch']` ⇒ 子条款③在真库列级可检出 |
| **M5** 幂等改成隐式（捕获 `assert_transition`） | `mark_participant_left`：删显式 `if … is left: return`，改 `try: assert_transition(...) except: return participant, True` | **2 failed / 48 passed** | `E::TestTheIdempotencyBranchIsExplicit::test_the_current_state_is_compared_before_assert_transition`：`找不到「当前状态已是 left ⇒ 直接返回」的显式分支`；`P::test_an_illegal_start_state_is_refused_not_swallowed`：`revoked → left 居然成功了` ⇒ 子条款⑤承重（**这正是「显式 vs 蒙对」的分界**：隐式版本对幂等本身仍然「能过」，但它把 `revoked → left` 一起放过了） |
| **M6** 放宽服务端 dirty 门 | `rooms.leave_participant`：`if client_reports_dirty and False:` | **1 failed / 49 passed** | `P::test_property_8_dirty_is_refused_and_writes_nothing`（基线为 `KeyError: 'type'` ⇒ 已按 §4.2 改成有名字的失败） ⇒ 子条款⑥承重 |
| **M7a** 授权之前先读业务行 | `wp_sync_router.leave_room`：`_guard` 之前插一句 `await svc.rooms.count_active_editors(room_id)` | **1 failed / 49 passed** | `E::TestAuthorizationFirst::test_guard_is_the_first_await_in_the_handler`：`第一个 await 是 'svc.rooms.count_active_editors' —— 先读业务行再授权会让 404/403 的时序泄露对象存在性` ⇒ 子条款⑦（authorization-first）承重 |
| **M7b** 泄露存在性（「存在但不是你的」分型） | `rooms.leave_participant`：把归属判据拆开，`participant.user_id != actor_user_id` 改抛 `ParticipantLeaveInFlightError` | **1 failed / 49 passed** | `P::test_only_the_owner_may_leave_and_all_three_misses_share_one_error`：`('not_my_lease', {'error_code': 'participant_leave_refused_in_flight', 'message': 'participant 36478eae-… 不属于你', 'type': 'ParticipantLeaveInFlightError'})` ⇒ 子条款⑦（同一 404 oracle）承重 |
| **M-obs** 观测者致盲（§4.1 新判据的反证） | `test_participant_leave_pg.py`：`_side_effect_counts` 的 `room_id` 过滤换随机 UUID | **1 failed / 23 passed** | 仅 `P::test_the_side_effect_counter_can_actually_see_a_request_row` 红：`场景 E 明明插了一条 forcesave request，观测者却没看到 —— 那么 AC 4.1 的三个「== 0」全是空转: {'forcesave_requests': 0, …}`。对照：**同一致盲在补这条之前 23 条全绿** ⇒ 新判据精确封住了那个空转 |

### 5.2 前端

| 变异 | 改动 | 实测 | 打红的判据 |
|---|---|---|---|
| **M8** 不发 leave（改发 close-intent 凑数） | `useWorkpaperSyncBridge.ts:1390`：`api.leaveRoom` → `api.createCloseIntent` | **2 failed / 8 passed** | `未改动 ⇒ 回 html_idle，且**恰一次 leave / 零次 forcesave / 零次 close-intent**`：`clean close 必须真的释放这条 lease: expected "spy" to be called 1 times, but got 0 times`；`🔴 恰一次：重复点「结构化视图」不会发第二次 leave` 同因红 ⇒「恰一次 leave」承重（旧的「零请求」口径下这个变异**不会**红） |
| **M8b** 放宽前端 dirty 门 | `useWorkpaperSyncBridge.ts:1376`：`if (!canLeave.value && false)` | **1 failed / 9 passed** | `🔴 有未保存改动 ⇒ 一律 refuse，且**不发**任何请求`：`promise resolved "undefined" instead of rejecting` ⇒ 子条款⑥的前端同源那一半承重（AC 4.4「两侧都不得放宽」成立） |

### 5.3 还原核验

```powershell
git status --short -- backend/app/services/workpaper_sync/rooms.py backend/app/services/workpaper_sync/repository.py backend/app/routers/wp_sync_router.py audit-platform/frontend/src/components/workpaper/sync/useWorkpaperSyncBridge.ts backend/tests/workpaper_sync/test_participant_leave_pg.py
```

```
 M backend/tests/workpaper_sync/test_participant_leave_pg.py
```

四个生产文件均无残留改动（唯一 modified 的是 §4.4 的判据文件）。

---

## 6. 结论

**任务 11 的四个交付面（repository / service / 端点 / 前端接线）在盘上都是完整的，且本轮拿到了
可复核的证据**：

* 后端 **51 passed**（27 形态/AST + 24 真库），前端 **10 passed**；
* 7 条验收子条款 → 判据 node id 全部 **PASS**，无 GAP 残留；
* 每条子条款各自经至少一个生产侧变异反证（M1 / M2a / M3 / M4·M4b / M5 / M6·M8b / M7a·M7b），
  确认不是「恰好绿」；
* 本轮补掉一条真实空转（GAP-1：side-effect 计数器无正对照，致盲后 23 条全绿）与一条诊断
  质量问题（GAP-2），生产代码零改动。

**未验证 / 不在本任务判据内**（如实标注）：真栈端到端点击（真实 OO 编辑器里点「结构化视图」
走完 `leave` 的浏览器实测）需 `start-dev.bat` 环境 + DocServer，属 Playwright 待环境项；
`close_intents` 计数器的独立正对照见 §4.1 残余局限。
