# Task 31 · 前端 DTO/API、generated contract、recovery client 与 `EditorLaunchDescriptor`

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 3 Task 31
Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11 · Properties: 10 / 11 / 47

## 产物

| 文件 | 角色 |
|---|---|
| `backend/scripts/gen/generate_workpaper_sync_frontend_contract.py` | 生成器（`--check` / `--apply`） |
| `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncContract.generated.ts` | 生成物：路由表 / `Idempotency-Key` 必填集 / 封闭域 / confirm 回传清单 / 拒绝映射 |
| `.../workpaperSyncDto.ts` | DTO 与解析器（域校验 + 不变量 + 失败分型） |
| `.../workpaperSyncApi.ts` | 唯一 HTTP 调用面（16 个 client method） |
| `.../workpaperSyncOperationTracker.ts` | SSE 优先、轮询恢复、按 operation/revision 去重 |
| `.../__tests__/workpaperSyncDto.spec.ts` · `workpaperSyncApi.spec.ts` · `workpaperSyncOperationTracker.spec.ts` | 前端行为侧判据 |
| `backend/tests/workpaper_sync/test_task31_frontend_contract.py` | 后端锚点：生成物 ↔ 真实 router / 枚举 / `confirm_payload()` |
| `backend/scripts/check/mutate_task31_frontend_contract_guards.py` | 21 条变异检验 |

## 四类事实为什么必须**生成**

真源全在后端：路由模板（`wp_sync_router.router.routes`，16 条）、`Idempotency-Key`
必填集（FastAPI 解出的 dependant，7 个）、状态封闭域（`workpaper_sync.models` 的 Enum 与
`TERMINAL_STATES`）、confirm 回传的十项（`EditorLaunchDescriptor.confirm_payload()` 的
**真实调用**结果）。手抄任一份都会静默漂移，而四层静态检查全绿：

- 少一条路由 ⇒ 该端点前端永远打不到；
- `Idempotency-Key` 少一个端点 ⇒ 复合幂等键最后一项恒空，同 participant 两次 forcesave
  折叠成一次（Task 28 已证明这一侧改动零功能测试失败）；
- 少一个 operation state ⇒ 被前端当未知值 fail visible，或（若兜底）静默归类；
- confirm 少回传一项 ⇒ 服务端逐项比对永远 409，编辑器停在「已挂载但不能保存」。

## 刻意**不**投影 / 不实现

| 项 | 理由 |
|---|---|
| callback 路由 | DocServer 的服务凭证面，响应体是顶层 `{"error": N}`（被 `ResponseWrapperMiddleware` 排除包装）；前端解包套上去必然错一层。判据剥注释后扫 `.ts` 代码 |
| `document.url` / 签名下载地址 | descriptor 刻意不含（Task 25/28 的 signature-TTL 论证）；URL 由服务端在响应时放进 `onlyoffice_config` |
| `getConfig()` / 第二份 config | Requirement 11.4：descriptor 是唯一 config 来源 |
| `ParticipantState` / `ParticipantMode` / `RequestKind` 枚举 | 16 个端点无一返回 participant state/mode；`kind` 是服务端专有（`close_capture` 只能由 room arbiter 在锁内 CAS）。投影没有消费方的常量 = 本 spec 第一类假绿 |
| `recovery_case` / `room` 的 terminal 集 | 前端无消费方。recovery 的三实体规则是**人工裁决**（`download_only` 是 terminal 而 `quarantined` 不是，但两者都必须三实体全空），不能由 terminal 集派生 |
| `forcesave` 的 `kind` 入参 | 留一个入参等于把 AC 4.10 的禁令变成「调用点自觉」 |

`WP_SYNC_OPERATION_SHAPES` 改为**只发字面量联合类型**：shape 由
`classifyOperationShape()` 从两个 link 派生，服务端从不下发它 ⇒ 运行时没有「校验收到的
shape」这回事，发数组常量就是死代码。`test_no_domain_is_projected_without_a_frontend_consumer`
是这条的正面判据（它在自审时真的抓出了这个 orphan）。

## 变异矩阵（21 / 21 RED）

`mutation_batch1.json`（M01–M07，fe）· `mutation_batch2.json`（M08–M13，fe）·
`mutation_batch3.json`（M14–M21，be）

| id | 侧 | 变异 | 预测判据 | 观测 |
|---|---|---|---|---|
| M01 | fe | `encodeEntryId` 改整串 `encodeURIComponent` | 分隔符 `/` 原样进入 URL | RED |
| M02 | fe | 不发 `Idempotency-Key` header | 七个端点各自「带非空 Idempotency-Key」 | RED |
| M03 | fe | 删 rollback 的 opaque UUID 门 | numeric revision ⇒ 发出前拒绝拼 route | RED |
| M04 | fe | claim body 塞 `client_confirmed_base_version_id` | claim body 白名单构造 | RED |
| M05 | fe | 在 API 层之外再解一次 envelope | 载荷仍是 envelope 时 fail visible | RED |
| M06 | fe | 删 primary/duplicate 互斥门 | 同时带两个 link ⇒ 拒绝 | RED |
| M07 | fe | 封闭域扩成「含本次收到的任何值」 | 未知 operation state fail visible | RED |
| M08 | fe | 三实体只检查 `operationId` | unclaimed 却带 `application_id` ⇒ 拒绝 | RED |
| M09 | fe | typed slot 只要求 `template` | 缺 instrumentation/contract ⇒ 拒绝 | RED |
| M10 | fe | download-only 禁项摘掉 `result_revision` | 带 `result_revision` ⇒ 拒绝伪造 applied | RED |
| M11 | fe | `start()` 无条件起轮询 | SSE 健康时只读一次 | RED |
| M12 | fe | 去重键丢掉 result revision | 同 state 但 revision 推进也必须通知 | RED |
| M13 | fe | content.updated 去重键塞进 operation | 按 `wp_id + revision` 去重（AC 11.9） | RED |
| M14 | be | 路由表只投影前 10 条 | `test_route_table_covers_every_real_user_route` | RED |
| M15 | be | `Idempotency-Key` 必填写死 `False` | `test_idempotency_key_projection_equals_the_dependant_truth` | RED |
| M16 | be | 封闭域只投影前三个值 | `test_closed_domain_equals_the_backend_enum` | RED |
| M17 | be | terminal 集误抄成状态域 | `test_terminal_set_equals_the_state_machine` | RED |
| M18 | be | confirm 清单改成 `as_dict()` | `test_confirm_keys_come_from_a_real_confirm_payload_call` | RED |
| M19 | be | 全部拒绝码压成 422 | `test_rejection_status_equals_the_single_mapping_point` | RED |
| M20 | be | 前缀模板保留 `:path` | `test_prefix_template_drops_the_path_converter...` | RED |
| M21 | be | 客户端代码里出现 callback 路径 | `test_the_callback_route_is_never_projected_to_the_frontend` | RED |

全部 21 条 `restored=True`、`hit>=1`、零 `.mutbak` 残留；锚点自检 21/21 OK（全部走
`scope`+`offset` 相对定位 —— 中途因清理死导出改动了这三个文件，绝对行号全会失效而
相对锚点一条没漂）。

## 测试与检查

| 项 | 结果 |
|---|---|
| vitest `src/components/workpaper/sync/` | 6 files · **220 passed** |
| `test_task31_frontend_contract.py` | **28 passed** |
| 辐射面（AST import 反查）：`test_task28/25/29 + task31` | **364 passed** |
| `backend/tests/workpaper_sync/`（全目录） | **2663 passed**，376s |
| `npx eslint --ext .ts src/components/workpaper/sync/` | 0 问题 |
| `npx tsc --noEmit` | 本任务四个新文件 **0 错**；`workpaperSyncLegacyBaseline.spec.ts(20,44) TS2367` 为**既存**（属早前任务的生成物投影，非本任务引入） |
| 生成器 `--check` | `[OK] contract digest ca3b003a…` |

辐射面用 **AST import/symbol 反查**（不是裸词搜 —— 本 spec 的 docstring 逐字引用类名与
文件名，裸词搜会把 67 个无关文件拖进来）：全仓 2284 个后端测试文件里，只有
`test_task31_frontend_contract.py` 直接依赖本次新增物；生产代码 **0 处改动**。

## 覆盖判定：Property 10 / 11 / 47

| Property | 本任务覆盖的部分 | 留给后续任务的部分 |
|---|---|---|
| **P10**（单次 commit 与 representation 幂等） | 客户端侧凭据：`createPendingMutation()` 的四项回执（回执**不含** revision 结果，AC 3.1）、`materialize()` 携带同一 `pending_mutation_token` + `Idempotency-Key` 并把 `replayed` 逐项投影、缺 token 时发出前拒绝（AC 3.2）；`Idempotency-Key` 是必发 header 且由生成的必填集驱动 | **幂等的服务端语义**（同 token 重放返回同 operation/version/representation，不同 payload 409）由 Task 25/28 的 PG 判据覆盖，本任务不重复 |
| **P11**（OO 打开前具备唯一 descriptor + ready 后服务端确认） | 前半的**数据侧**：20 个必备字段逐项校验（缺任一即拒绝挂载）、全零 UUID / 非法 digest / `generation<1` / typed slot 缺失 / 空 config 全部 fail visible、descriptor 无 `documentUrl`、confirm 回传键集逐项等于服务端 `confirm_payload()`、`forcesaveUnlocked` 之前的门 | 前半的**渲染侧**（`descriptor → DocEditor mount → onDocumentReady → confirm API → oo_editing/forcesave enabled` 的 DOM 顺序）明确属 **Task 33**（其正文原文即「mounted test 锁死…」）。本任务的判据全部在 API/DTO 层，不声称覆盖挂载宿主 |
| **P47**（编辑器只消费 descriptor 并暴露 durable API） | 「不自行请求 config」的**API 层事实**：本模块无 `getConfig` 面、未登记 endpoint 名拒绝拼 URL、路由表里无 `/config` 与 `onlyoffice-callback`；`recoveryCase` 在 claim 前不带 operation id 的**数据侧**不变量（`parseRecoveryCase` 对 5 个 pre-claim 状态强制三实体全空） | `forceSave()` / `getSyncState()` 的 `defineExpose`、七个事件的真实触发路径、`recoveryCase` 事件形态 —— 全部需要一个**挂载宿主**，属 **Task 33**；bridge 状态机（含 `recovery_pending/claiming/download_only` 终态与非法转换）属 **Task 32** |

## 发现但未修的上游问题（登记，不在本任务范围内动手）

**`claim` 请求体的三个 expected 字段服务端未读取。** design §API 规定 claim 带
`room_id / participant_id / prior_confirmation_id / expected_generation /
expected_write_fence / expected_definition_bundle_sha256 / Idempotency-Key`；实测
`wp_sync_router.claim_recovery_case` 只读 `room_id` / `prior_confirmation_id` /
`participant_id` / `expected_current_revision` 四项（fence / generation / bundle digest
三项**从请求体读都没读**，服务端另从 scope index 与候选 confirmation 自行冻结）。

- 影响：客户端提交的 `expected_*` 目前是**声明而非校验** —— 「客户端以为自己做了乐观锁」
  与「服务端真的比对过」在响应上不可区分。这不是本任务能修的（属 Task 28 的 guard 面），
  也不宜由客户端悄悄不发（那会让契约与 design 不一致）。
- 本任务的处置：`buildClaimRequestBody()` 按 design 的白名单**照发**，并由
  `CLAIM_REQUEST_ALLOWED_KEYS` 交叉锁死（禁止再多塞 base/bundle/contributor）；此处登记
  事实，建议由 Task 28 的后续收口或 Task 32 一并处理。
