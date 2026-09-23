# C6 —— 前端源码结构真源类失败（8 节点）

> 分诊范围：`backend/tests/workpaper_sync/` 下 8 个「判据读前端/路由源码结构」的失败节点。
> 环境：`cwd=backend`，`..\.venv\Scripts\python.exe -m pytest <file> -q --tb=short -rf -p no:randomly`。
> **从不跑整套 `tests/workpaper_sync`**（约 34 分钟且截断）。

## 0. 复现（逐文件，verbatim 计数）

| 文件 | 首轮结果 | 本簇归属的失败 |
|---|---|---|
| `test_task31_frontend_contract.py` | `2 failed, 26 passed` | 2 |
| `test_task46_d_cycle_migration.py` | `13 failed, 59 passed` | 1（其余 12 属他簇：manifest/模板 digest/slice 计数） |
| `test_task50_h_cycle_migration.py` | `9 failed, 95 passed` | 3（其余 6 属他簇） |
| `test_task54_l_cycle_migration.py` | `1 failed, 143 passed` | 1 |
| `test_task76_wp_code_adjudication.py` | `1 failed, 5 passed` | 1 |

## 1. 节点 → 它读的真源 → 是否在工作树 diff 里

工作树里被改的 4 个前端文件（任务给出的领先假设）：

```
 M audit-platform/frontend/src/components.d.ts                                （diff 实为空，仅 LF→CRLF 行尾噪声）
 M audit-platform/frontend/src/components/workpaper/sync/workpaperSyncLegacyBaseline.generated.ts   | 354 +-----
 M audit-platform/frontend/src/components/workpaper/sync/workpaperSyncManifest.generated.ts         | 736 +-----
 M audit-platform/frontend/src/utils/http.ts                                   |  38 +-
```

| # | 节点 | 它实际读的文件 + 符号 | 在上面 4 个 diff 里？ |
|---|---|---|---|
| 1 | `task31::test_a_real_slashed_entry_id_still_routes_through_the_generated_template` | `workpaperSyncContract.generated.ts`（`WP_SYNC_USER_PREFIX_TEMPLATE` / `WP_SYNC_ROUTES`）+ `wp_sync_router.router.routes` | **否** |
| 2 | `task31::test_the_callback_route_is_never_projected_to_the_frontend` | `wp_sync_router.public_router.routes[0]` + `workpaperSyncContract.generated.ts` + `sync/*.ts` | **否** |
| 3 | `task46::TestSourceCodeStructure::test_hosts_exist_and_import_legacy_composable` | `GtD2AccountsReceivable.vue`（找 `useD2EntryDualMode`）+ D slice JSON | **否** |
| 4 | `task50::TestHtmlCounterpartIsSourceBacked::test_write_carrier_client_and_put_site_agree_with_the_source` | `composables/useH3FormData.ts#L150` + H slice `endpoint_write_source` | **否** |
| 5 | `task50::TestHtmlCounterpartIsSourceBacked::test_payload_column_mode_matches_the_write_site` | `composables/useH3FormData.ts#L154` + H slice `payload_write_site` | **否** |
| 6 | `task50::TestSourceCodeStructure::test_hosts_exist_and_are_reachable_from_the_renderer_registry` | `workpaper/htmlRendererRegistry.ts`（找 `const GtX = defineAsyncComponent(() => import('./GtX.vue'))`） | **否** |
| 7 | `task54::TestSheetGranularityAndRouter::test_router_declaration_matches_the_source` | `backend/app/routers/wp_onlyoffice_router.py#L630` + L slice `endpoint_site` | **否** |
| 8 | `task76::TestHostResolutionNoLongerTrustsTheHeuristic::test_loader_is_fail_closed_when_the_table_is_missing` | `scripts/fix/fix_task76_provision_projection_definitions.py` 的 `WP_CODE_ADJUDICATION` / `load_wp_code_adjudication` | **否** |

### 「一个上游」假设：**推翻（8/8 全否）**

没有任何一个节点读那 4 个被改的文件。`components.d.ts` 的 diff 甚至是空的（只有行尾）。
`workpaperSync{Manifest,LegacyBaseline}.generated.ts` 被截短 1071 行确有其事，但它们与这 8 条判据
**无读写关系**——本簇 8 条读的是 contract 生成物、宿主 `.vue`、renderer registry、H3 composable、
后端 router 与 T76 宿主脚本。

真实上游是 **6 个互不相干的已提交变更**：

| 上游 | 内容 | 命中节点 |
|---|---|---|
| U1 | `public_router` 现有 **2** 条路由，`get_room_contents`（L1045）声明在 `post_room_onlyoffice_callback` 之前 ⇒ `routes[0]` 不再是 callback | 2 |
| U2 | user router 新增 `/rooms/{room_id}/participants/{participant_id}/leave`，判据的占位替换表只有 room/operation/case/version 四个 | 1 |
| U3 | `useD2EntryDualMode.ts` 已在 `42d2f6e6f` 随本 spec 交付一并删除（D2 是 pilot，整体迁到 `useWorkpaperSyncBridge`） | 3 |
| U4 | `useH3FormData.ts` 在 `afdcbf0cc`（Task 17 死代码清理）后整体上移 10 行：`api.put(` 实为 L140、payload 实为 L141–146 | 4, 5 |
| U5 | `htmlRendererRegistry.ts` 在 `62cb462ea` 拆分为 `registry/entries/{core,forms,programs,confirmations,reports,specialized}.ts`；聚合器里 `defineAsyncComponent` 只剩 1 处，import 路径也由 `'./GtX.vue'` 变成 `'../../GtX.vue'` | 6 |
| U6 | BP-24：T76 不再自留第二份 loader，`WP_CODE_ADJUDICATION` 降级为**转引别名**，真正读盘在 `projection_target_resolution` | 8 |
| U7 | `wp_onlyoffice_router.py` 行漂移：`onlyoffice-config` 装饰器实为 **L648**（slice 写 L630） | 7 |

## 2. 两个优先标记的裁定

### 标记 A —— OnlyOffice **callback** 路由被投影进前端契约？→ **未确认（不是暴露面）**

实测（`_c6_probe.py`，已删）：

```
public_router routes:
   ['GET']  /api/workpaper-sync/rooms/{room_id}/contents          -> get_room_contents
   ['POST'] /api/workpaper-sync/rooms/{room_id}/onlyoffice-callback -> post_room_onlyoffice_callback
contract target: workpaperSyncContract.generated.ts exists=True
'onlyoffice-callback' in generated contract: False
'/contents'          in generated contract: False
```

* callback 路径 **没有**进生成物，也没有进前端任何 `.ts` **代码**面。前端 sync 目录里 `onlyoffice-callback`
  只出现 1 次，在 `workpaperSyncApi.ts#L30` 的**模块注释**里，逐字写着「`onlyoffice-callback` 是 DocServer
  的服务凭证路由」——这正是判据自带 `_strip_ts_comments` 要处理的情形。
* 真正红的原因是判据的**位置假设** `public_router.routes[0]`：`get_room_contents` 声明在前，于是
  反向自检 `assert "onlyoffice-callback" in callback_path` 先崩，安全断言 `assert "onlyoffice-callback"
  not in generated_text` **根本没执行到**。也就是说不变量本身成立，只是没被验证。
* 顺带核实第二条 public 路由是否是新暴露：`get_room_contents` 需要 `token: str = Query(...)`，
  由 `room_launch.resolve_room_contents(..., secret=ONLYOFFICE_JWT_SECRET)` 验短 TTL 签名，
  非法 token 回 401，且四处「存在性 404」已在 service 层收敛成单一 `_not_found()`。它是 OO
  `document.url` 的消费面，与 `public_router` 的既有定位一致（G4-3 注释在案），**不是**新增暴露。

**裁定：安全不变量完好；判据是脆的。修完后该判据比原来更强 —— 现在断言 public_router 的
每一条路由都不得出现在生成物里（callback 与 contents 同时被盯）。**

### 标记 B —— fail-closed loader 不再 fail closed？→ **生产行为未回归；但守卫当前空转**

* 生产侧 `app/services/workpaper_sync/projection_target_resolution.load_wp_code_adjudication()`
  仍然 fail closed：`if not WP_CODE_ADJUDICATION.is_file(): raise ProjectionTargetResolutionError(...)`，
  T76 宿主再把它转成 `SystemExit`。**没有回落到启发式。**
* 红的原因：判据 patch 的是 `T76M.WP_CODE_ADJUDICATION`，而 BP-24 之后这只是个
  `WP_CODE_ADJUDICATION = _TARGET_RESOLUTION.WP_CODE_ADJUDICATION` 的**转引别名**，读盘路径不再看它。
  于是 patch 落空 → 真表在盘上 → 不抛。
* 危害的准确表述：**不是**「宿主解析静默回落启发式」，而是「这条守卫已经无法再发现回落」——
  等价变异下恒绿。属于必须修的空转判据。

**裁定：fail-open 未发生；守卫空转已确认。修法＝把 patch 点对准真实读盘路径，并额外钉住
「别名必须仍指向生产常量」，这样 BP-24 若被回退成第二份实现，判据照样咬。**

## 3. 逐节点判定与修法

| # | 判定 | 修法 |
|---|---|---|
| 1 | (c) 判据陈旧 —— 路由合法新增了 `{participant_id}` | 占位替换表补 `{participant_id}`；保留 `assert "{" not in suffix` 作 fail-closed 闸（再来新参数照样红） |
| 2 | (c) 判据陈旧 —— `routes[0]` 位置假设 | 按路径谓词选 callback 路由；并把安全断言加强为「public_router 每条路由的路径片段都不得出现在生成物里」 |
| 3 | (c) 结构合法变更 —— D2 legacy composable 已随本 spec 删除 | `pattern_by_host` 里 D2 改为其真实统一路径锚点，并显式断言 `useD2EntryDualMode.ts` 确已不在盘上（否则该 entry 又回到 legacy 而判据不知） |
| 4 | (c) slice 声明的行号陈旧（U4 行漂移） | H slice `endpoint_write_source` L150 → L140 |
| 5 | (c) 同上 | H slice `payload_write_site` L154 → L141 |
| 6 | (c) 判据陈旧 —— registry 已拆包 | 判据改为在聚合器 + `registry/entries/*.ts` 里找 import 边，允许 `./` 与 `../../` 两种相对路径；仍要求 component 绑定存在 |
| 7 | (c) slice 声明的行号陈旧（U7） | L slice `endpoint_site` L630 → L648 |
| 8 | (c) 判据 patch 错了符号（U6） | patch 真实读盘路径 `_TARGET_RESOLUTION.WP_CODE_ADJUDICATION`，并加「别名同一性」断言 |

**没有一个节点需要改前端源码**，也没有一个 `*.generated.ts` 需要重跑生成器
（`test_generated_file_is_fresh` 在首轮就是绿的 —— contract 生成物与生成器一致）。
slice JSON 是**手写冻结证据**（有 `frozen_at`、无 `generated_by`/`generator` 字段），
行号声明陈旧就地修正即正解，判据本身就是为了抓这种漂移而存在。

## 4. 变异验证（破坏真实结构 → 必红 → 逐字节复原）

夹具 `backend/scripts/_c6_mutate.py`（一次性，已删）：每次变异前后比 sha256，
复原不是「重写一遍」而是**写回读入时的原始字节**（含 CRLF）。

| id | 变异的真实结构 | 目标判据 | 结果 |
|---|---|---|---|
| M1 | 往 `workpaperSyncContract.generated.ts` 注入一条 callback 路径常量 | task31 callback | **RED** ✅ |
| M2 | 给 router 的 `operations/{operation_id}/timeline` 再加一段 `{slice_id}` | task31 slashed-entry | **RED** ✅ |
| M3 | 把生产 loader 的 `if not WP_CODE_ADJUDICATION.is_file():` 改成 `if False:`（fail-open） | task76 fail-closed | **RED** ✅ |
| M4 | `specialized.ts` 里把 H2 的 import 换成 H1（H2 宿主失去模块边） | task50 registry 可达性 | **RED** ✅ |
| M5 | D2 宿主的 `useWorkpaperSyncBridge` import spec 改成不存在的 `...BridgeXX` | task46 宿主结构 | **RED** ✅ |
| M6 | 把 `useD1EntryDualMode.ts` 从盘上改名移走 | task46 宿主结构 | **RED** ✅ |
| M7 | H slice 的 `useH5FormData.ts#L127` 回改成 L128 | task50 write-site | **RED** ✅ |
| M8 | L slice 的 `wp_onlyoffice_router.py#L648` 回改成 L630 | task54 router 声明 | **RED** ✅ |
| M9 | 把 `useD2EntryDualMode.ts` 复活到盘上（pilot 被回退） | task46 宿主结构 | **RED** ✅ |
| M10 | H2 的 `defineAsyncComponent` 边留着但挪出 `component:` 位 | task50 registry 可达性 | **RED** ✅ |

### 🔴 变异过程中抓到**我自己**写的一个空转判据

M5 第一版是 **GREEN**：我最初把 D2 的统一路径锚点写成裸子串
`assert "useWorkpaperSyncBridge" in content`。变异把 import 改成 `'./sync/useWorkpaperSyncBridgeXX'`
后子串依然命中（前缀关系），且宿主注释里另有同名词 —— 典型的等价变异。
改成「抽出 `from '...'` 的 import spec 集合 + 精确匹配 + 解析到盘上真实模块」后 M5 转 RED。
判据里留了这段实测记录，防止后人又退回子串写法。

复原核查：`git status --porcelain` 对 6 个被变异文件全空，无 `__c6_mutation__` 残留。

## 5. 前后计数

| 文件 | 修前 | 修后 | 本簇 8 节点 |
|---|---|---|---|
| `test_task31_frontend_contract.py` | 2 failed, 26 passed | **28 passed** | 2/2 ✅ |
| `test_task46_d_cycle_migration.py` | 13 failed, 59 passed | 9 failed, 63 passed | 1/1 ✅ |
| `test_task50_h_cycle_migration.py` | 9 failed, 95 passed | 6 failed, 98 passed | 3/3 ✅ |
| `test_task54_l_cycle_migration.py` | 1 failed, 143 passed | **144 passed** | 1/1 ✅ |
| `test_task76_wp_code_adjudication.py` | 1 failed, 5 passed | **6 passed** | 1/1 ✅ |

task46 少了 4 条而我只修 1 条：另外 3 条
（`test_every_pending_entry_host_mounts_the_notice` /
`test_notice_mount_sits_inside_the_mode_toolbar` /
`test_hosts_do_not_claim_bidirectional_writeback`）在我不动它们的情况下自行转绿 ——
并行 agent 正在改 `backend/data/workpaper_sync_entry_manifest.json` 与 D2 宿主
（实测其 working-tree diff 删掉了 `import GtEntrySyncCapabilityNotice`）。
余下 9 + 6 条全属他簇（manifest/模板 digest/slice 计数/孤儿 composable/位置化行身份）。

## 6. 改动清单

判据侧（4 个测试文件，均为「陈旧检测器」修正，无一弱化）：
* `backend/tests/workpaper_sync/test_task31_frontend_contract.py` —— 占位替换表补 `{participant_id}`；callback 改按路径谓词选并扩成「public_router 每条路由都不得投影」
* `backend/tests/workpaper_sync/test_task46_d_cycle_migration.py` —— D2 按已迁 pilot 判（import spec 精确匹配 + 解析到真实模块 + legacy 必须确已不在盘上），D1/D3~D7 仍按 legacy 未删判
* `backend/tests/workpaper_sync/test_task50_h_cycle_migration.py` —— registry 可达性跟随拆包（聚合器 + `registry/entries/*.ts`，两种相对前缀），仍要求边坐在 `component:` 位上
* `backend/tests/workpaper_sync/test_task76_wp_code_adjudication.py` —— patch 点对准真实读盘路径，另加「别名必须仍转引生产常量」

数据侧（手写冻结证据里的陈旧行号，4 处）：
* `backend/data/workpaper_sync_h_cycle_manifest_slice.json` —— H3 `endpoint_write_source` L150→L140、`payload_write_site` L154→L144；H5 `endpoint_write_source` L128→L127
* `backend/data/workpaper_sync_l_cycle_manifest_slice.json` —— `endpoint_site` L630→L648、`sheet_resolution_site` L301→L306（BP-8 的同两条 `source_refs` 同步更新，保持内部一致）

**前端源码 0 改动**，**`*.generated.ts` 0 手改**（contract 生成物的 `test_generated_file_is_fresh`
首轮即绿 —— 生成物与生成器一致，无需重跑）。

## 7. 前端校验

* `npx vue-tsc --noEmit -p tsconfig.json`：**OOM**，`--max-old-space-size=8192` 仍 OOM
  （`FATAL ERROR: Ineffective mark-compacts near heap limit`）。属本仓规模下的既存限制，
  与本次无关 —— 实测本次对 `audit-platform/frontend/` 的改动为 **0 字节**
  （`git diff --stat` 里那几个前端文件是并行 agent 的在改项，我一个都没编辑；
  被变异的 6 个文件已核对 sha 逐字节复原）。
* `npx vitest run <registry / D2 / sync 相关 5 个 spec> --reporter=dot`：
  `4 passed | 1 failed`，`135 passed | 6 failed`。
  唯一失败文件 `d2SyncHostWiring.spec.ts` 的 6 条**与本次无关且既存**：它要的
  `useD2SyncBridge(` / `const ooSheetRef` / `ref="ooSheetRef"` / `flushBeforeOo` /
  `requestForceSave` 五个锚点在 `git show HEAD:` 的 D2 宿主里**全部 ABSENT**。
  这是节点 3 的**前端孪生体** —— 同一次 D2 统一路径迁移在前端侧也留了一个陈旧判据。
  与 registry 拆包直接相关的 `htmlRendererRegistry` / `registryDomainSplit` /
  `registrySplitEquivalence.pbt` / `workpaperSyncApi` 四个 spec 全绿。

## 8. 交给后续的两条观察（本次不动，避免越界）

1. **`d2SyncHostWiring.spec.ts` 是节点 3 的前端孪生陈旧判据**（6 条既存红，锚点在 HEAD 即不存在）。
   与本簇同一根因，但属前端 spec，且 D2 宿主此刻正被并行 agent 编辑 —— 建议由该 spec 的归属方一并收口。
2. **H slice 的 `payload_write_site` 存在 ±4 行窗口容差**（`_write_site_window(span=4)`）。
   H4 的声明 L192 与同族约定完全一致，但这个容差意味着「差 1~4 行」的漂移不会被发现。
   若要把这类漂移也钉死，应把判据从「窗口含 token」改成「声明行本身即 payload 行」——
   属判据强度升级，需要先把 9 条 H entry 的声明统一到同一锚点语义，另立工项更稳。

