# Task 28 证据：显式 scope sync router、兼容委派与 authorization-before-resource/cache 端点门

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28
Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
Properties: **P10 / P11 / P45**

## 产物

| 路径 | 作用 |
|---|---|
| `backend/app/routers/wp_sync_router.py` | 用户端 14 个端点 + 服务凭证 callback；只搬参数、过 guard、映射状态码 |
| `backend/app/services/workpaper_sync/endpoint_guard.py` | 固定五阶段 guard（唯一产出 `GuardedScope` 的途径）+ signed scope claim |
| `backend/app/services/workpaper_sync/endpoint_payloads.py` | HTTP body → 域值对象的唯一翻译层（resolve fence / 裁决 / projection） |
| `backend/app/services/workpaper_sync/__init__.py` | 本包对外形态的 import 面（Task 28 起不再只有 docstring） |
| `backend/app/router_registry/workpaper.py` | 两个 router 显式注册在自动加 gate 的循环之外 |
| `backend/app/routers/wp_onlyoffice_router.py` | legacy callback 的**纯增量**委派分支（四项 URL 绑定齐备时只走新服务） |
| `backend/tests/workpaper_sync/test_task28_sync_router.py` | 99 条离线判据（形态 + 替身驱动的 guard 行为） |
| `backend/tests/workpaper_sync/test_task28_sync_router_pg.py` | 47 条真库判据（TestClient + 真实中间件 + 逐 scenario 快照） |
| `backend/scripts/diagnose/mutate_task28_sync_router_guards.py` | 56 条变异（`_mutation_kit.span`，不落 `.mutbak`） |
| `backend/scripts/diagnose/radiation_task28_sync_router.py` | 按真实 import/引用反查辐射面 |
| `mutation_report.json` | 56 条四态判定 + 每条 `added/hit/restored_sha256` |
| `radiation.json` | 43 个受影响测试文件及其命中原因 |

## 基线

```
py -3 -m pytest backend/tests/workpaper_sync/test_task28_sync_router.py \
                backend/tests/workpaper_sync/test_task28_sync_router_pg.py -q
→ 147 passed（100 离线 + 47 真库）
```

## 变异矩阵：57 条全 RED

```
py -3 backend/scripts/diagnose/mutate_task28_sync_router_guards.py --check-anchors   # 只读，秒级
py -3 backend/scripts/diagnose/mutate_task28_sync_router_guards.py --run all \
    --report-path .kiro/specs/.../evidence/task28-sync-router/mutation_report.json
→ RED 57 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0；覆盖面 2/2 个登记守卫文件
```

七类落点：①阶段顺序 ②登记 vs 就地抛（含「常量工作量」）③六条 404 / 两条 403 / 一条 503
的逐条分型 ④形态判据自身（只读 scope index、404 家族名单、HTTP 映射封闭、依赖必填）
⑤signed claim（签发/消费/验签/跨 scope/用途）⑥router 形态与统一 envelope ⑦真实调用链。

**判定不看退出码**，只看失败名集合差集；另有一条独立核验逐条比对
`verdict=RED ∧ hit≠∅ ∧ added≠∅ ∧ restored_sha256 == 当前磁盘 sha256`（7 个生产文件）。

### 变异检验抓到的三个守卫缺陷（均已修）

| 变异 | 首轮判定 | 根因 | 修法 |
|---|---|---|---|
| **A07** `if not is_opaque_resource_id(...)` → `if False:` | GREEN | `_parse_route_scope` 的两条 route-key 分支**共用** `OpaqueResourceIdRequiredError`，而唯一覆盖第一支的判据用的是 `resource_kind=content_version` —— 第二支（`not is_uuid_text("11")` 恒真）抛出同一类型顶上来。于是「numeric revision 不得作 scope key」对 room/operation/recovery case 等**全部非 version kind** 从未被任何判据锁住 | 拆出 `VersionIdNotUuidError`（独立 error_code，同属 404 家族）；判据分母跨 5 种 kind；补一条「两支不得共用 error_code」的反向判据；新增 **A25** 作为该缺陷的回归变异 |
| **B09 / B10** `if outcome.response_error != 0:` / `if result.result is not ...applied:` → `if False:` | GREEN ×2 | 两条判据是 **presence** 形态（`"response_error" in attrs` / `"result.result" in ast.unparse(fn)`）—— 属性节点留在死分支里就能满足。而这正是「durable 前失败被当 ack=0，OO 丢件」与「apply 失败静默当成功」的形态 | 判据改看 `If.test`（值真的在**门控**分支），另加「函数内不得有 `False` 字面量门控的 `if`」与「该分支必须据此 `return` 非零 ack」 |
| **B26** 从 `RESOLVE_FENCE_REQUIRED_FIELDS` 删一项 | GREEN | 参数化的分母**就是被测常量本身** —— 删一项，对应用例也一起消失（自证重言式） | 分母换成域内 `ResolveFenceRequest` 的 dataclass 字段；另补一条「必填清单 ↔ 域字段双向等值（只减唯一合法可空项）」 |

### 另补一条此前完全无判据的不变量

Task 28 bullet 1 明文「pending token / confirmation / claim 的 Idempotency-Key、409 stale
identity 与零 revision 语义不得由前端约定代替」，但**没有任何判据**证明
`Idempotency-Key` 是服务端强制的：七个幂等端点都写着 `Header(..., alias=...)`，
改成 `Header(default="")` 时不会有一条测试失败。后果是复合幂等键
`(room, generation, participant, kind, key)` 的最后一项对所有请求恒为空串 ⇒
**同一 participant 的任意两次 forcesave 折叠成一次**（第二次拿到第一次的
request/operation，真实编辑内容再也不会被 correlate）。
补 `test_the_idempotency_key_is_a_required_server_side_header`（走 FastAPI 解出的
dependant 的 `field_info.is_required()`，端点集合双向等值 + 逐个 required），
对应变异 **B32**（`allow_multi`，一次改掉全部 7 处）。

### 顺带修掉的一处「判据不可达」

`_build_error_code_status` 的「同一 error_code 登记两个 status 即抛」分支在真实映射表上
恒不触发 ⇒ 从测试侧不可达 ⇒ 其变异必永久 GREEN（分支存在但没有任何判据锁着它）。
给它开了**只给判据用**的 `spec` 注入口（生产调用不传），判据这才能真的喂一份矛盾登记；
对应变异 **B16**。

### 刻意不登记的一条候选

把 `phases=tuple(phases) + (action_authorized,)` 换成 `phases=REQUIRED_PHASES`：
当前 `enforce` 是一条线性路径、四阶段必然已走过，两种写法**语义等价** ⇒ 无效变异，
判 GREEN 也不代表守卫缺陷。脚本里以注释形式登记了「为什么不登记」。

## `oo_to_html.py` 的欠账已翻转成真实调用链判据

Task 26 收口时 `oo_to_html` / `conflict_resolution` **没有生产调用方**，非死代码只由
`merge.RETIRED_DEFERRALS` 登记表 + Task 14 的「merge 域恰一个消费方」做**结构性**背书。
Task 28 落地后判据从 router 出发反查真实链：

```
POST /api/workpaper-sync/rooms/{room_id}/onlyoffice-callback
  → CallbackDeliveryService.handle_callback()        （durable + request-first correlate）
  → wp_sync_router._apply_durable_incoming()
  → OoToHtmlCoordinator.apply_durable_incoming()
```

`TestOoToHtmlHasARealProductionCallChain` 的七条分别锁住：import 面、
`apply_durable_incoming` 真被调、callback handler 真到达那个函数、两处「读结果而不是
读『没抛异常』」、`ConflictResolutionService` 的 resolve/retry/rollback 三个方法各有调用点、
以及登记表里 Task 28 那一条（**归因型**判据，不用 `len(...) == N`，否则别人合法追加就打红）。

对应变异 B07（删接线）、B08（接线搬去别处）、B09/B10（只靠没抛异常判成功）全部 RED ——
登记表判据查不出这四种形态中的任何一种。

## legacy 路由：改了什么、没改什么

**改了**：`post_sheet_onlyoffice_callback` 顶部新增两行委派分支 —— URL 带齐
`callback_route.URL_BOUND_PARAMS` 四项绑定（新式 callback）时只委派新服务，
下方 legacy 逻辑一行不跑。判据 B23（分支被门控）、B24（自写参数名清单）、
B25（`all` → `any`）各自 RED。

**没改**：legacy URL 没有那四项 query，因此其行为**逐字节不变**（纯增量）。
把 legacy 分支整体删掉、让端点无条件只委派，取决于 `get_sheet_onlyoffice_config` /
`get_sheet_wopi_contents` / `get_whole_excel_grid` 三条 resolver 行先迁到 room/staged
representation substrate —— 那是 **Task 30** 的 `multi_resolver` gate 明文承接的范围。

## 辐射面与既存红的归因

```
py -3 backend/scripts/diagnose/radiation_task28_sync_router.py    → 43 个测试文件（全量 2279）
py -3 -m pytest <这 43 个文件> -q                                  → 2448 passed, 54 failed
```

不跑全量（`backend/tests` 下 2279 个测试文件，前台跑会被当成卡死），按**真实
import/符号引用**反查辐射面。

54 条既存红**逐条归因，与 Task 28 无关**（改动前后同为 54 条；passed 由 2443 → 2448 是
本任务新增的 4 条 callback-route 判据 + 1 条 Idempotency-Key 判据）：

| 条数 | 文件 | 失败形态 | 归属 |
|---|---|---|---|
| 26 | `test_wp_onlyoffice_router.py` | `assert 404 == 200` —— harness 只 `include_router(router)`，callback/WOPI/health 都挂在 `public_router` 上 | 既存 harness 挂载问题 |
| 5 | `test_onlyoffice_word_template_callback.py` | 同上 | 同上 |
| 11 | `test_onlyoffice_session_lifecycle.py` | `StopAsyncIteration` @ `wp_onlyoffice_router.py:704 → resolve_room_doc_key` —— **Task 21** 把 doc_key 从 `md5(wp_code+mtime_ns)` 改成 room 身份派生，多了一次 DB 往返，而 mock session 没喂 | Task 21 |
| 10 | `test_onlyoffice_wopi_auth.py` | 同上 | Task 21 |
| 2 | `test_task21_...contract_numbers_have_single_source_in_oo_contract`、`test_task22_...jwt_decoding_lives_only_in_callback_route` | 都追到 Task 24 的 `command_service.py` | Task 30 的门 |

Task 28 对 legacy router 的三处新增（两个模块级函数 + 2 行分支）**不在上述任何失败路径上**：
404 那一族在路由匹配阶段就没进 handler；`StopAsyncIteration` 那一族栈顶在
`get_sheet_onlyoffice_config`。

### 关于 `public_router` 挂载：正确修法已可见，但不单方面改

本任务的真库 harness 同时 `include_router(SR.router)` 与 `include_router(SR.public_router)`，
并装上 `ResponseWrapperMiddleware` —— 于是 31 条 legacy 红（26 + 5）的修法就是同一句
`app.include_router(public_router)`。**没有动它**：那是 legacy 测试文件的 harness，
且 `test_wp_onlyoffice_router.py` 有并发会话在途改动。

## 🔴 产物入库状态：9 个正式产物仍是 `??` 未跟踪

```
git status --porcelain -- <产物清单>
 M backend/app/router_registry/workpaper.py
 M backend/app/routers/wp_onlyoffice_router.py
?? backend/app/routers/wp_sync_router.py
?? backend/app/services/workpaper_sync/{__init__,endpoint_guard,endpoint_payloads}.py
?? backend/tests/workpaper_sync/test_task28_sync_router{,_pg}.py
?? backend/scripts/diagnose/{mutate,radiation}_task28_sync_router*.py
?? .kiro/specs/.../evidence/task28-sync-router/
```

这是**整个 spec** 的既存状态（`backend/app/services/workpaper_sync/` 整个包自 Task 9 起
就未跟踪），不是 Task 28 引入的。两条后果照旧成立：①挂进 CI 的 job 在干净 checkout 下
必挂（文件不存在）②工作树一丢全部蒸发。**未自行 commit**（未获授权），在此登记待 add。

## 残留（不属于 Task 28 的范围，不在此宣称覆盖）

* 新 callback 端点的**端到端** durable/correlate/apply 链路（status 6/2 多 delivery、SSRF、
  最终 authorization fence、canonical rematerialize）由 **Task 30** 的独立集成门承接。
  本任务只证明：端点已挂载、信封被跳过、pre-durable 拒绝回非零 ack、被拒时零 delivery 行、
  且不误用用户 404/403 契约（`TestServiceScopeCallbackRoute`，4 条）。
* adapter registry 当前**刻意**零注册（Tasks 40~57 / 62~64 逐 entry 接线），因此
  materialize / conflicts / resolve / retry / rollback 的 happy path 在真库侧只能验到
  「无 approved adapter ⇒ 422 fail visible」（B17 锁住它不得退化成兜底 None）。
