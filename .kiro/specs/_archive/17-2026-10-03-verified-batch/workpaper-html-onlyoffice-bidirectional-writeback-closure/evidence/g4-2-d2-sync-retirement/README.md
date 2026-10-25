# G4-2 · `/d2-sync/*` legacy 旁路退役与物理删除

> 状态：**DONE**（2026-09-11）· 以本目录 `post-delete-eligibility.json` 与 `mutation_report.json` 为准
> 输入门：`HOST-CONSUMES-UNIFIED-PATH` = `ONLYOFFICE_VERIFIED`（10/10 谓词 · `entry_state_counts.ONLYOFFICE_VERIFIED=4` · 其余桶全 0 · `blockers=[]`）⇒ 总控 DEC-08 的解除条件成立
> 输出：DEC-08 关闭 · 总控 §2.4.4 的 gap 4/5/6/7/8/9/15 随删除消失 · gap 14 已由 G4-0a 关闭

## 1. 删了什么（6 个文件 + 2 处绑定）

| 对象 | 理由 |
|---|---|
| `backend/app/routers/d2_sync_router.py` | 4 个专用端点 `status` / `push-to-excel` / `forcesave` / `pull-from-excel` 绕过 coordinator |
| `backend/app/router_registry/workpaper.py`（2 处） | 摘掉 import 别名与「渲染」组里的 `d2_sync`；原位留三行说明为何不得回来 |
| `audit-platform/frontend/src/components/workpaper/sync/useD2SyncBridge.ts` | legacy 专用桥；宿主已于 2026-09-10 迁 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` |
| `backend/tests/test_d2_sync_durable_gate.py` | Half B 全部针对已删 router；Half A 已迁走（见 §2） |
| `audit-platform/frontend/src/components/workpaper/__tests__/d2SyncDurableGate.spec.ts` | 直接 import 已删的 legacy 桥 |
| `backend/scripts/diagnose/mutate_d2_sync_durable_gate_{backend,frontend}_guards.py` | 变异锚点落在已删文件上 |

**刻意不删** `backend/app/services/workpaper_sync/d2_bidirectional_bridge.py`：统一
`oo_to_html._mirror_store_backed_if_needed()` 在用它的 `STORE_ITEM_ID` 与
`merge_projection_into_store_rows()`（总控 §2.4.6 可复用资产）。门里 `E3b` 是**反方向**
判据 —— 它打红表示删过头，不是没删干净。

## 2. 迁走而不是删掉的判据

`test_d2_sync_durable_gate.py` 是**混合文件**：Half B 属 legacy router，Half A 的三条
store 值等价判据却守着统一路径在用的 `d2_store_value_equivalence`。整文件删除会让该
模块失去**全部**覆盖（全仓只有那一处引用它）。

→ 新宿主 `backend/tests/workpaper_sync/test_d2_store_value_equivalence.py`（**24 passed**），
除承接三条外新增：桥的转发别名用 `is` 判同一对象（防第二份实现）、契约映射唯一性、
merge 的 `applied`/`visited` 分离计数、protected 跳过、非受管键保留、OO 侧新增行，
以及两条统一路径接线反向锁。

## 3. 替换面（删除前逐项现算确认在位）

| legacy 覆盖的事 | 继任者 |
|---|---|
| `_issue_forcesave` 三态（accepted / nothing_to_save / rejected） | `command_service` 返回码真值表：error 0..6 / 6 个 outcome，严格更宽 |
| `_assert_not_stale` 读到未落盘旧文件 | durable callback + sealed incoming + representation generation CAS（结构上不再读活动磁盘文件） |
| 缺陷 A：切 OO 前不 flush | `d2SyncHostWiring.spec.ts` 在**统一宿主**上的顺序断言 |
| 缺陷 B：未拿耐久确认就 pull + 假「同步成功」文案 | `workpaperSyncBridgeMachine.spec.ts` 四态文案互不相同门 |
| forcesave 默认端点泄漏（gap 14） | `GtOnlyOfficeSheet.vue` G4-0a fail-closed |
| Half A：store 值等价 | 见 §2 |

## 4. 现算门

`backend/scripts/check/check_d2_sync_retirement_eligibility.py` —— 12 条判据，
**一门两相**（磁盘上 legacy 文件是否存在 ⇒ 自动判 `pre_delete` / `post_delete`，
半删状态 `partial` 直接打红）。

判据形态的纪律：**按「是否作为代码使用」判，不按字符串存在判**。Python 侧走 AST 只看
`ast.Constant` 字符串并剔除 docstring（注释天然不进 AST）；TS/Vue 侧先用带字符串/模板串
状态机做真正的注释剥离，再看剩下的代码。

| 相位 | 读数 |
|---|---|
| pre-delete | `pass 12 / fail 0`，`eligible_to_delete=True`（`pre-delete-eligibility.json`） |
| post-delete | `pass 12 / fail 0`，`post_delete_clean=True`；扫 **2200** 个 `backend/app` 模块 + **5209** 个 `src` 生产文件，零命中（`post-delete-eligibility.json`） |

`--self-check` **16/16 可翻动**，其中 4 条是「反向的反向」（本该放行的形态若被打红，
门就会逼人去删注释或删负向断言）：后端注释提及不算调用方、前端注释提及不算调用方、
`https://` 里的 `//` 不被当注释起点吞掉、缺陷 A 判据的变量改名不得打红。

## 5. 变异检验（10/10 RED · 零漂移 · 零 `.mutbak` 残留）

`backend/scripts/diagnose/mutate_d2_sync_retirement_guards.py`，四态判读。

| # | 变异 | 判读 |
|---|---|---|
| M01 | 后端 legacy router 复活 | RED |
| M02 | 前端 legacy 桥文件复活 | RED |
| M03 | 后端生产模块重新把 `d2-sync` 当端点字面量 | RED |
| M04 | registry 重新绑定 `d2_sync` | RED |
| M05 | 把仍被统一路径消费的桥一起删掉 | RED（删过头方向） |
| M06 | 拆掉缺陷 A 的顺序断言 | RED |
| M07 | 去掉 G4-0a fail-closed 的必填端点判断 | RED |
| M08 | 打断一处防复活负向断言 | RED |
| M09 | 只掏空 D2 分支的 store 合并绑定 | RED |
| M10 | 掏空**全部** store 合并绑定 | RED |

## 6. 本轮抓出并修掉的四个判据缺陷（都由真实执行证伪）

1. **`oo_to_html` 的接线判据 ANCHOR-MISS**：它是 `merge_rows_fn = bridge.merge_projection_into_store_rows`
   先绑定、再调 `merge_rows_fn(...)`，只看 `ast.Call` 的函数名会把「接线正常」误判成
   「没接线」。判据拆两半：存在 `*.merge_projection_into_store_rows` → 本地名的 `Assign`，
   且该本地名真被当函数调用。
2. **M06 首跑 GREEN —— 子串把断言顶替了**：E3c 原先只要求块里含 `toBeGreaterThan`，
   而同块还有 `expect(flushAt).toBeGreaterThanOrEqual(0)`，它**包含**那个子串。于是把
   `expect(readAt).toBeGreaterThan(flushAt)` 削弱成 `expect(readAt).not.toBe(-1)` 后判据
   照样绿。改为结构判据：现读两个下标变量各自绑定的符号，再要求二者之间的顺序断言。
3. **M09 首跑 WRONG-TEST —— 预期项写错，不是守卫缺陷**：只掏空 D2 分支时 h1/b60 仍绑着
   同名函数，故「接线是否存在」那条通用判据**应该**保持绿；打红的是 D2 专属那条。已改正
   预期项并补 M10 专打通用判据。
4. **动态加载含 `@dataclass` 的模块必须先进 `sys.modules`**：`spec_from_file_location` +
   `module_from_spec` 后若不注册就 `exec_module`，dataclasses 解析注解时
   `sys.modules[cls.__module__]` 为 `None` → 9 个 ERROR。

## 7. 顺带修好的 Task 28 判据形态错

`test_task28_sync_router.py::test_the_callback_route_is_a_service_scope_route` 原判据是
`len(public_router.routes) == 1`，把两件不同的事压成一条：①「callback 是 service-scope
路由」与②「public_router 只准一条路由」。G4-0d 为 OO `document.url` 合法新增
`GET /api/workpaper-sync/rooms/{room_id}/contents`（签名短 TTL token + room/representation/
digest 三重绑定 + 返回 `FileResponse`）之后①仍成立而判据打红。

更要紧的是 `len == 1` 保护得太弱 —— 它管不住「新增的那条 public 路由有没有凭据校验」。
已改为**封闭清册** `_PUBLIC_ROUTE_INVENTORY`（逐条登记 why / 凭据机制 / 是否需
`_SKIP_CONTAINS` 跳过）+ 4 条判据：清册封闭、无 public 路由落在用户前缀、callback 恰一条、
**每条 public 路由按登记机制真校验凭据**（`required_query_token` 查必填 `FieldInfo.is_required()`；
`delegated` 查函数体真委派）。严格强于原判据。

坑：`Query(...)` 的 `.default` 是 `PydanticUndefined` 而非 `Ellipsis`，判必填只能问
`FieldInfo.is_required()`。

## 8. 🔴 本次删除把 `HOST-CONSUMES-UNIFIED-PATH` 退成了 `STALE`（设计行为，如实登记）

重跑 `generate_workpaper_sync_program_milestones.py --apply` 后：

```text
milestone_state_counts: ONLYOFFICE_VERIFIED 1 → 0 · STALE 9 → 10
HOST-CONSUMES-UNIFIED-PATH: ONLYOFFICE_VERIFIED → STALE（predicates 10/10 → 1/10，blockers 0 → 9）
```

这**不是**回退，而是总控 §2.3（「真实 OO 已跑但 source/evidence stale ⇒ 退回 `STALE`」）
与核心 Task 45（「删除提交导致 source commit 变化时，Task 44 evidence 立即 stale」）
预先规定的行为 —— 浏览器观测是在删除前的源码上取的，删除后它不能继续代表现在的代码。

**三条机器 stale 原因（现算，逐条可执行）**：

| # | `stale_reason` | 归因 |
|---|---|---|
| 1 | `network:required_literal_missing:.../GtOnlyOfficeSheet.vue` | 该 evidence 的 `source_bindings` 要求文件里出现字面量 `"不得默认打 /d2-sync/forcesave"`，而 G4-2 把 fail-closed 文案改掉了 |
| 2 | `network:source_digest_mismatch:.../GtOnlyOfficeSheet.vue` | 同一文件 `sha256` 由 `9c71785e…` 变化 |
| 3 | `source_check_missing_file:capability` | 谓词 8（能力现算）的 source check 绑在已删的 `d2_sync_router.py` 上 |

**解除条件（唯一）**：按 §9.6 在 **post-delete 源码**上重跑四个 pilot 的 Playwright 并重新
采集 `evidence/g0-4-host-consumes-unified-path/{d2-2,h1,g7,b60}/` 三个通道，同时把两处
**已过时的锚点**一并换掉 —— 锚点 1 现在要求代码永久保留对一个已删端点的提及，锚点 3
指向一个已不存在的文件；替代锚点应是行为型的（`forcesaveEndpoint` 必填 + fail-closed），
该禁令现已由 `test_d2_sync_retirement.py` 与本门 `E2b` 结构性承担。

**本轮为何不做**：`sha256` 不匹配只能由真实重跑消除，而重跑需要前端 3030 —— 实测
**3030 未监听**（9980 与 OnlyOffice 8080 在跑）。按 §2.3「环境不可用 ⇒ `UNVERIFIABLE`，
不得写成实现失败」，本项记为环境不可得，owner 是核心 Task 45 的「post-delete 全场景重验」
与 G9-1。**在重跑完成前，任何地方都不得再把该 milestone 记作 `ONLYOFFICE_VERIFIED`。**

**刻意不做的两件事**：不改 evidence 的 `sha256`/`required_literals` 让它「看起来还新鲜」
（那是「把错值当基线锁死」的反向形态）；不回退文案去迁就锚点（那等于让生产代码为了
凑证据而永久保留对已删端点的引用）。

## 9. 诚实边界

- **不宣称** `/d2-sync/*` 的删除推进了任何 entry 的双向验收状态。它只关闭 DEC-08 与
  gap 4/5/6/7/8/9/15；`HOST-CONSUMES-UNIFIED-PATH` 的**分母**（4 个 entry）一字未动，
  但**状态**已按上节退为 `STALE`。
- **未跑**真实 OnlyOffice / Playwright。本工作包的删除面在请求路径上已由 §9.6 的四个
  pilot（D2-2 / H1 / G7 / B60）证明零调用（`d2_sync_hits=0`），本轮不重复取证。
- **未动** manifest / overlay / writer inventory：三者的 stale 各有 owner（见 §9）。

## 10. 登记为后续工作包的遗留

### G4-3（新）：把 OO launch config 组装与 JWT 收敛回 service 层

`test_task28_sync_router.py` 3 条红，**HEAD 上是绿的**，由 G4-0d 的未提交工作引入：

| 失败判据 | 根因位置 |
|---|---|
| `test_the_router_builds_no_second_onlyoffice_config` | `wp_sync_router.py` L795~840 组装 `document`/`editorConfig`/`documentType`/`type` 并 `jwt.encode` |
| `test_the_router_never_decodes_a_jwt` | 同文件 L850~891 `_sign_room_contents_token` / `_verify_room_contents_token`；L2294 OO outbox JWT `jwt.decode` |
| `test_404_has_exactly_one_construction_site` | 同批改动新增的 404 构造点 |

Task 28 明令「router 不自己 `jwt.decode` 后比字段」「descriptor 必须是唯一来源」。
修法是把上述三块抽到 service 层（`materialize_coordinator` 或新建 room launch descriptor
模块），约 150 行迁移 + 新测试 —— 文件面与不变量都与本工作包不同，故不混入。

### 他人 lane 的红（本轮实证不归本工作包，未触碰）

- `test_workpaper_writer_inventory.py` 4 failed + 1 error：`WriterInventoryError` 仍**只**点名
  `app.routers.wp_render_config::_get_render_config_impl`（他人对 `wp_render_config.py` 的
  555 行在途重构使它不再直调 `_resolve_template_path`，overlay 裁决成孤儿）。该错误在本
  工作包开工前就已存在，且删除后错误信息一字未变 ⇒ **本次删除零新增孤儿**（已核
  `workpaper_writer_domain_overlay.json` 里 `d2_sync_router` 裁决为 **0 条**）。
- 前端 `FrontendReferenceIntegrity.spec.ts` 路由投影 **114 vs golden 113**：多出的是
  `extension/custom-templates/ingest` / `CustomTemplateIngest`（`router/domains/extension.ts`
  为他人 ` M`，custom-template-ingestion lane 的 Task 4 加了路由未更 golden；golden fixture
  本身还是 `??` 未跟踪）。与本次删除无关（被删对象不是路由）。

## 11. 🔴 产物未入库 —— 新增 CI job 在干净 checkout 下必挂

收口实扫 `git status --porcelain -- <产物清单>`，**10 个产物为 `??` 未跟踪**：

| 归属 | 未跟踪产物 |
|---|---|
| 本工作包（G4-2） | `backend/scripts/check/check_d2_sync_retirement_eligibility.py` · `backend/scripts/diagnose/mutate_d2_sync_retirement_guards.py` · `backend/tests/workpaper_sync/test_d2_sync_retirement.py` · `backend/tests/workpaper_sync/test_d2_store_value_equivalence.py` · 本目录 4 个 evidence 文件 |
| 上一会话（G0-1，同样从未提交） | `backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py` · `backend/data/workpaper_sync_program_milestones.json` |

**后果两条**：

1. `.github/workflows/governance-checks.yml::workpaper-sync-d2-legacy-retirement` 的三步全部
   引用上表第一行的文件 ⇒ **干净 checkout 下该 job 必挂**（文件不存在）。同理，既有的
   `workpaper-sync-program-milestones` job 也因第二行两个文件未入库而在干净 checkout 下必挂。
2. 工作树一丢，本工作包的全部判据与 evidence 蒸发；而 `.gitignore` 已收 `tmp_*`/`_wip_*`
   但**不**收这些正式产物 —— 它们只是从未被 `git add` 过。

**已删除的 6 个文件**在 `git status` 里是 ` D`（已在索引外记录删除），提交时必须与新增产物
**同一个 commit**，否则会出现「router 已删而防复活守卫未入库」的半态 —— 那正是本门 `E0`
相位判据要打红的形态。

**未提交的原因**：本轮未获明确的提交指示。提交前按项目规则须先 `git fetch` 看远端真实
base，并走 PR 不直推 main。

## 12. 复验命令

```bash
python backend/scripts/check/check_d2_sync_retirement_eligibility.py
python backend/scripts/check/check_d2_sync_retirement_eligibility.py --self-check
python backend/scripts/diagnose/mutate_d2_sync_retirement_guards.py
python -m pytest backend/tests/workpaper_sync/test_d2_sync_retirement.py backend/tests/workpaper_sync/test_d2_store_value_equivalence.py -q
```

CI：`.github/workflows/governance-checks.yml::workpaper-sync-d2-legacy-retirement`（归因型新增 job，前三步；变异检验要改盘故不入 CI）。
