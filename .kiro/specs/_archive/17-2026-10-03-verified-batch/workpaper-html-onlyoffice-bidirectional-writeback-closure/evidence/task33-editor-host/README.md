# Task 33 — Excel/Word 编辑器升级为 descriptor consumer 与可 await / recovery-aware 宿主

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 3
Requirements: 3.7, 4.8, 5.8, 11.4, 11.5, 11.6, 11.10, 11.12
Properties: **11**（DOM 半）· **47** · **48**（DOM 半）

---

## 1. 交付物

| 文件 | 角色 |
|---|---|
| `audit-platform/frontend/src/components/workpaper/sync/WorkpaperSyncEditorHost.vue` | **挂载宿主**（Excel + Word 共用）：只接 descriptor，创建 DocEditor，把真实 `onDocumentReady` 上报桥，确认成功后才允许保存 |
| `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncEditorHostRuntime.ts` | 纯函数层：DocsAPI 载入、DocEditor config 组装（等值判据的分母常量在此）、回调取码归一、宿主文案表 |
| `audit-platform/frontend/src/components/workpaper/sync/__tests__/WorkpaperSyncEditorHost.spec.ts` | **38 条**挂载判据（DOM + 真实 emit + 真实调用序列） |
| `backend/scripts/check/mutate_task33_editor_host_guards.py` | 35 条变异声明 + 四态判定 |
| `backend/scripts/diagnose/radiation_task33_editor_host.py` | 按 import/符号引用反查辐射面（不跑全量） |
| `audit-platform/frontend/src/components/workpaper/sync/useWorkpaperSyncBridge.ts` | **改动**：新增 `notifyHostFailure()` —— 宿主侧失败的唯一上报口（见 §4 缺陷 1） |

**不动 legacy**：`GtOnlyOfficeSheet.vue`（228 处引用）与 `WorkpaperWordEditor.vue` 保持原状。
它们的删除归 `legacy_delete` gate（Task 71 → Task 72）；本任务只交付新宿主，
把 legacy 一起改会让 Wave 3 承担 Wave 7 的删除门。

## 2. 锁死的顺序（Property 11 的 DOM 半）

判据用一条**真实调用序列**锁死，而不是「confirm 被调过」：

```
materialize → DocEditor 构造 → confirm_descriptor → request_forcesave
```

逐步 DOM 事实各不相同：

| 步 | 桥状态 | DOM |
|---|---|---|
| 无 descriptor | `html_idle` | 无 editor 容器、无保存钮 |
| descriptor 到手 | `oo_loading → descriptor_mounted` | 容器在（`getElementById(placeholderId)` 命中同一节点）、遮罩在、保存钮 **disabled** |
| 真实 `onDocumentReady` | `confirming_descriptor` | 遮罩仍在、保存钮仍 disabled、`forceSave()` 抛 `editor_host_forcesave_before_confirmation` |
| confirm 成功 | `oo_editing` | 遮罩消失、保存钮 **enabled** |
| confirm 失败(409) | `html_idle` + sticky error | 容器**移除**、`destroyEditor` 调用 1 次、保存钮消失、状态条 `kind=error` |

confirm 回传键集不手抄第二份：与生成的 `WP_SYNC_DESCRIPTOR_CONFIRM_KEYS` 逐项等值。

## 3. 变异矩阵（35 条，全 RED）

判定四态：`RED` 有效 / `GREEN` 守卫缺陷 / `WRONG-TEST` 锚点错位 / `ANCHOR-MISS` 脚本缺陷。
锚点一律唯一整行或 `scope`+`offset`，**无绝对 `line=`**。落盘 `mutation_report.json`。

| ID | 目标 | 注入 | 预测打红 | 实测 |
|---|---|---|---|---|
| M01 | HOST prop 名 | `descriptor` → `launchDescriptor`（父传的成了**不存在的 prop**） | 四步顺序 + prop 正面判决 | RED |
| M02 | HOST props | 加一个没人传的 `sheetKey?`（死 prop） | prop 正面判决 | RED |
| M03 | HOST emits | 加 design 里那个永不触发的 `fallback: []` | emit 正面判决 | RED |
| M04 | HOST | 删 `emit('dirty')` 唯一触发 | dirty + emit 正面判决 | RED |
| M05 | HOST 模板 | 保存钮 `:disabled` 从 `canForcesave` 改 `editorLive`（**ready 即可保存**） | 四步 + ready 不等于可保存 | RED |
| M06 | HOST | `forceSave()` 确认门 → `if (false)` | ready 不等于可保存 | RED |
| M07 | HOST 模板 | 确认前遮罩 `v-if="false"` | 四步 + ready 不等于可保存 | RED |
| M08 | HOST | `editorLive` 不看 mode（**确认失败仍 editing**） | confirm 409 + 只读 participant | RED |
| M09 | HOST | mode 离开 oo 时不 `destroyEditor()` | confirm 409 | RED |
| M10 | HOST | 确认失败被吞（`void error`） | confirm 409 | RED |
| M11 | HOST | 状态条自己编「同步成功」 | confirm 409 + 卸载后不洗回 + 四步 | RED |
| M12 | HOST | `recoveryCase` 载荷带上 **claim 前的 operation id** | claim 前三实体全空 | RED |
| M13 | HOST | 普通 retry 门全开（`return true`） | crash→recovery 不渲染重试（三条） | RED |
| M14 | HOST | 列不出恢复项时静默返回 | 列不出可认领项 ⇒ 显式失败 | RED |
| M15 | HOST | recovery list 带 `docKey` 冒充 `roomId` | crash→recovery | RED |
| M16 | HOST | 确认前的异常也去查恢复项 | 确认前异常不进恢复流程 | RED |
| M17 | RUNTIME | config 里塞一个 `token`（第二份 config） | config 逐字来自 descriptor | RED |
| M18 | RUNTIME | 削 `WP_SYNC_HOST_ADDED_CONFIG_KEYS` 分母 | config 逐字来自 descriptor（证明判据非自证） | RED |
| M19 | RUNTIME | 编辑器侧 forcesave 门失效 | 打开 forcesave 时拒绝挂载 | RED |
| M20 | RUNTIME | 缺 document 段照挂 | fail closed | RED |
| M21 | HOST | 去掉 `await nextTick()` | **重开**（见下方 WRONG-TEST 归因） | RED |
| M22 | HOST | 传给 DocEditor 的容器 id 漂开一格 | 四步（`getElementById`） | RED |
| M23 | HOST | 构造抛错却上报「已挂载」 | 构造抛错不得上报挂载 | RED |
| M24 | HOST | 删 `mountedKey === key` 幂等门 | 重复下发不重挂 | RED |
| M25 | HOST | 忽略 `documentServerUrl` prop，只认环境变量 | 按 documentServerUrl 载入 api.js | RED |
| M26 | BRIDGE | `notifyHostFailure` 不记 sticky error | 无服务地址 + 终态 sticky + 构造抛错 | RED |
| M27 | BRIDGE | `notifyHostFailure` 不推状态 | 无服务地址 + 构造抛错 + forcesave config | RED |
| M28 | HOST | 用 descriptor 的 artifact 摘要冒充 incoming 摘要 | incomingDurable 不伪造摘要 | RED |
| M29 | HOST | 三个终态压成 `applied` | conflict 与 applied 可分辨 | RED |
| M30 | HOST | 删 `emit('saveRequested')` | forceSave + 按钮 + emit 正面判决 | RED |
| M31 | HOST | `getSyncState()` 自己编 `canForcesave: true` | getSyncState 逐项来自桥 | RED |
| M32 | RUNTIME | dirty 放宽成真值判断 | dirty 只认 `data===true` | RED |
| M33 | RUNTIME | 取不到码时回空串 | 取码归一 | RED |
| M34 | RUNTIME | 未登记失败码不再被拦 | 码未登记 | RED |
| M35 | HOST | 挂载身份少算 representation 代际 | 编辑中换身份 ⇒ 显式失败 | RED |

### M21 的 WRONG-TEST 归因（保留在案）

首轮 M21 的 `want` 指向「四步顺序」，实测 **WRONG-TEST**：打红的是重开判据。
原因是**首次**挂载碰不到这条 —— `await nextTick()` 之后紧跟的 `await docsApiLoader()`
本身也让出一个微任务，Vue 的渲染 flush 在那时已经跑完，容器已在 DOM 上。
真正需要 `nextTick` 的是**重挂**（容器 id 变了、旧 id 还挂在 DOM 上）。
处理方式是把 `want` 改指到真正观测它的判据，并把这段归因写进 `why` ——
比给首挂判据硬编一条时序断言诚实。

## 4. 发现并修掉的生产缺陷（3 个）

### 4.1 桥没有宿主侧失败的上报口 ⇒ 永久 loading（fail-open）

`oo_loading` / `descriptor_mounted` 都在 `WP_BRIDGE_IN_FLIGHT_STATES` 里。
宿主载不到 DocsAPI、config 被拒、DocEditor 构造抛错时，桥的公开面里**没有任何**
方法能把这件事变成状态：状态条继续显示「正在打开 OnlyOffice 编辑器」、离开被阻断、
而失败只存在于宿主局部变量里。

修法：`useWorkpaperSyncBridge` 新增 `notifyHostFailure(stage, error)` —— 记 sticky
`lastError` + 尝试 `apply('sync_failed')`（终态下容忍非法转换，与既有 `fail()` 逐字一致），
**不抛**（调用点在 DocsAPI 回调里）。M26/M27 两条变异分别锁死它的两个作用。

### 4.2 `notifyEditorMounted()` 的抛出没人接 ⇒ unhandled rejection

宿主在桥不预期的时点挂载编辑器时，`apply('editor_mounted')` 会抛，而 `mountEditor()`
是 async 且无人 await ⇒ unhandled rejection，界面上什么都看不到、编辑器实例还留着。
修法：包 try/catch 并走 `failHost(..., reportToBridge=true)`。
（实测形态：`oo_editing` 下换 descriptor 身份，见 M35 的判据。）

### 4.3 早于确认的保存点击会打断正在飞行的合法确认

首版 `forceSave()` 的确认前拒绝走 `reportToBridge=true`，于是「用户点早了」被记成一次
同步步骤失败：`confirming_descriptor --sync_failed--> error`，随后 confirm 成功返回时
`descriptor_confirmed` 在 `error` 上没有出边 ⇒ 一次**完全合法**的确认被用户的一次早点击
永久毁掉。修法：该拒绝只落宿主可见（`reportToBridge=false`）。判据现在同时断言
「宿主可见」与「桥状态仍是 `confirming_descriptor` 且 `lastError` 仍为 null」。

## 5. 登记的上游缺口（不假设被强制，判据按当前事实写）

1. **`GET .../operations/{id}` 的投影没有 incoming artifact digest**（只有 application 的
   bundle/authority digest）。design 的 `incomingDurable: [{operationId, artifactSha256}]`
   因此只能给 `null`；拿 descriptor 的 `artifactSha256`（materialize **出去**那份）顶替会让
   「回来的文件就是我发出去的那份」凭空成立。M28 锁死这一点。
2. **桥的三条声明边在公开 API 下不可达**（本任务在接线时钉出的事实，归属 Task 32 的 AC 4.4/AC 4.6，
   本任务不越界修）：
   - `forcesave_frozen --forcesave_started--> forcesave_requesting`
   - `error --forcesave_started--> forcesave_requesting`
   - `refresh_required --descriptor_received--> rematerializing`
   三者的唯一触发口分别是 `switchToHtml()`（门是 `canForcesave`，要求 `state === 'oo_editing'`）
   与 `switchToOnlyOffice()`（第一步是 `flush_started`，在 `refresh_required` 上非法）。
   后果：dispatch 失败后既不能重发命令也不能普通重试；refresh-required 之后无法经桥重开。
   本任务的重开判据因此只走**可达**路径（身份失败 → 回 HTML → 重新 materialize）。
3. `claim_recovery_case` 仍不校验 `expected_generation / expected_write_fence /
   expected_definition_bundle_sha256`（Task 32 已登记，本任务未依赖它）。

## 6. 验证

| 项 | 结果 |
|---|---|
| 本任务判据 | **38 passed / 38** |
| sync 目录全量 + legacy `GtOnlyOfficeSheet` | **392 passed / 392**（11 文件） |
| 变异 | **35/35 RED**，全部 `restored=True`，无 `.mutbak` 残留 |
| `--list` 声明校验 | 35 条全过（锚点唯一命中、want 可定位、分母文件存在） |
| `--check-anchors` | 35/35 OK、目标文件 md5 未变 |
| `npx tsc --noEmit` | 2123 → **2124**；唯一新增是 `TS2307: Cannot find module '../WorkpaperSyncEditorHost.vue'`，与基线里 841 条同类（plain `tsc` 不解析 `.vue`）。中途另有一条真 `TS2349`（`let x: (()=>void)|null` 被控制流收窄成 `never`）已修 —— vitest 走 esbuild，只有 `tsc` 能看见 |
| `npx eslint src/components/workpaper/sync` | 0 problem |
| 后端辐射面 | `test_task32_bridge_state_domain.py` 14 passed（它按成员判断桥的公开面，新增方法不破坏它） |
| 辐射面反查 | FE 2 文件 / BE 1 文件（脚本首版漏了多行 import，已修并写进注释） |

## 7. Property 结论

| Property | 状态 | 依据 |
|---|---|---|
| **11**（OO 打开前具备唯一 descriptor 且 ready 后服务端确认） | **DOM 半已闭**（Task 31/32 留的那半） | 四步顺序 + 容器 id 真查 + 零 HTTP（`fetch`/`XHR.open` spy 全程零调用）+ config 键集等值 + 确认前 disabled/遮罩 + 确认失败收回编辑器。服务端侧的 409 判据在 Task 21/25 |
| **47**（编辑器只消费 descriptor 并暴露 durable API） | **已闭** | 7 个 emit 各有真实触发路径并被正面判决锁成等值集合；`forceSave()`/`getSyncState()` 真调用；`recoveryCase` 在 claim 前类型与运行时双重禁 operation id |
| **48**（同步失败不被成功文案覆盖） | **DOM 半已闭** | 状态条唯一真源是桥的 `feedback`（error 优先）；确认失败后撤走 descriptor（清理成功）仍 `kind=error`；`destroyEditor` 的异常不动 `hostError`。跨会话/跨组件的粘性由 Task 34 的状态条继续承接 |

**仍开**：Property 11/47 的**真实 OnlyOffice 9.4.0 浏览器实测**（DocsAPI stub 不能替代
真容器里的 `onDocumentReady`/`onError` 时序）—— 那属于 Task 39 的 pilot harness，
本任务不宣称它已通过。
