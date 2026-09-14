# 复盘：HTML ↔ OnlyOffice 双向回写总控 G0–G4 推进

> 日期：2026-09-09 · 范围：本轮按总控 `docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md` 执行方向连续推进的 G0→G4 工作。
> 定位：跨工作包复盘 + 已修问题登记。各包细节见同目录 evidence README。

---

## 1. 做了什么（按 Phase）

| Phase | 结论 | 关键实证 |
|---|---|---|
| G0（治理里程碑） | 复验通过，未改 | generator `--check` 通过；22 项守卫绿；程序仍 STALE（诚实） |
| G1-1（structure_hash 统一） | 实现 + 守卫 | 三条业务提交路径 fail-closed；Excel finalize 去掉第二份公式；8 项行为/变异测试 |
| G1-2（rehash representation-only） | 实现 + **真库 finalize** | 分流纯口径 stale/坐标漂移；H1 真库 finalize 出 gen2、revision 不变、同 content version、旧 gen 保留 |
| G1-3（请求路径复验） | 实现 + **真库 verified** | H1 gen2 经 observer+registry 复验为 `verified`；未迁移实例 `migration_not_run` |
| G2-1（BP-21 排版行） | 补齐缺失守卫 | 27 项测试（含全库 census 879/182/39 + 变异反证）；验收脚本 exit 0 |
| G2-2/G2-3（结构引擎） | 验证已实现 + 修遗留 | owner 分离 + AST 守卫；修 BP-21 遗留的 D2 删除测试（13..25→13..24）；292 passed |
| G3-1（请求期 registry） | 真库验证 | register_from_manifest 真注册 3 entry + 183 显式原因；H1 gen2 组 extract adapter 无 drift |
| G4-0a（forceSave 参数化） | 安全实现 | `forcesaveEndpoint` prop 默认回退 legacy，行为不变；d2 gate 10/10 |
| G4 后端全链 | **真实 HTTP 验证** | 统一 materialize 对 D2 路径可达+认证+协议全正确执行 |
| G4 浏览器 | **真实浏览器基线** | 登录 admin + 开 D2 + 观察 legacy `/d2-sync/status=200` |

真库两次写入：仅 H1 finalize（可逆、revision 不变、新增 gen 不删旧行）。其余全只读。

---

## 2. 本轮纠正的错误判断（重要）

1. **「D2 无 published representation/approved bundle，统一 materialize 必 422」是错的。**
   来源是 sub-agent 读过时 docstring 的推断（它无 DB access）。真库只读实测：D2/G7/H1
   三个 entry 都有 current published representation + approved bundle，
   `register_from_manifest` 全注册成功，`assert_bidirectional_ready` 全 PASS。
   ⇒ 教训：**docstring 说「两表 0 行」不能当运行态事实**，涉及供给态一律连库核。

2. **「representation-only finalize 无 ready candidate 可跑」在 H1 上也是错的。**
   最初基于代码判断「存量遗留行尚无 ready candidate」，真库查证 H1 恰有一个
   `state=ready`、contract+bundle 齐全的 candidate。⇒ 教训：候选/供给态先查库再下结论。

3. **G4 真实阻塞不是后端供给，而是前端宿主。** D2 前端仍走 legacy `/d2-sync/*` +
   `GtOnlyOfficeSheet`（config 带 `customization.forcesave:true`，与统一 host 不兼容）。

---

## 3. 复盘中发现并已修复的问题

1. **BP-21 遗留的过期删除测试**（G2-3）：`test_workbook_row_change_delete.py::test_d2_region_is_13_to_25_not_11_to_25` 在 HEAD 即失败——BP-21 已把 D2 受管区收缩到 13..24 且契约 `formula_mask` 同步为 13:24，但该删除测试仍断言 13..25。**已按真实模板只读探针修正** region 常量/端点/collapse count，292 passed。

2. **finalize 脚本的死代码 import**（复盘本轮发现）：`finalize_ready_candidate_representation_only.py` 里 `WorkpaperSyncRepository`、`reg_module` 两个 import 只被 `_ = ...` 占位保活，实际未用（仓储由 coordinator factory 内部装配）。按仓库纪律「死代码立即删除」**已删除两处 import 与占位行**；`--check` 复跑对已 finalize 的 H1 正确 fail-closed（无 ready candidate），证明清理未破坏真实路径。

3. **G1-1 一个变异测试原本未打红**（G1-1 收尾发现）：finalize 内联公式变异与 fixture 期望值恰等价，未能打红。**已改为真正模拟旧 whole-structure 公式**，变异确实打红后才通过。

---

## 4. 诚实边界（未完成、不冒充）

- **G4-0b/0c/0d 未做**：D2 前端宿主迁到统一 `WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`（需 `flushHtml` 把 D2 store 投影成 28491 字段的 `{values}`、切 descriptor 驱动的编辑器、forcesave/callback 走 room_id）是对**生产组件的大改写**，其唯一有效验收是完整真实 OO 往返（编辑→forcesave→callback→durable→application `applied`→HTML 刷新）。本轮未做，以免落未验证改动到生产。
- **D2-2 仍 `REQUEST_PATH_LEGACY`**，`working_paper_content_application` = 0，`HOST-CONSUMES-UNIFIED-PATH` 8 谓词未满足。**未宣称 `bidirectional_verified`**。
- 统一 materialize 对 D2 的真实 HTTP 验证止于「协议全正确、空 projection 因 roundtrip 不等值被正确拒」——驱动成功 descriptor 需真实 D2 store projection（前端 bridge 职责）。

---

## 5. 全轮验证汇总（复盘时重跑）

- G1（G1-1+G1-2+G1-3）+ G2-1 + G2-3 删除测试：**88 passed**。
- structure hash semantics + Excel entry gate：**117 passed**。
- 结构引擎全套：**292 passed**（G2-2/G2-3 复盘时）。
- 前端 d2SyncDurableGate + WorkpaperSyncEditorHost：**51 passed**。
- 三个后端脚本 `py_compile` 通过；scoped `git diff --check` 干净。
- 真库仍在线，H1 gen2/revision 不变状态未被后续动作改变。

---

## 6. 下一步（交接）

1. **G4-0b/0c/0d 需在真栈上交互完成**：把 `GtD2AccountsReceivable` 迁到统一 host，
   跑一次真实 OO 往返，取 `working_paper_content_application.state='applied'` 行 +
   浏览器 network 断言（`USER_SYNC_PREFIX` 出现、`/d2-sync/*` 消失）+ `content_revision`
   前后差 1。前置（G4-0a 参数化、后端全链、供给态）已就绪。
2. **G4-0a 的 `forcesaveEndpoint` prop** 已备好注入点，迁移时把它指向
   `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave`。
3. 所有本轮 evidence 与新增测试/脚本目前是**未跟踪**状态，各推进方入库前按产物清单
   `git status --porcelain -- <清单>` 核查，避免干净 checkout 缺文件。

---

## 复盘补充（2026-09-10）：G4 canary 深入推进

### 做了什么

- **交付 store-projection 只读端点** `GET .../sync/entries/{entry}/store-projection`：store-backed entry（D2 整表 JSON）的 projection 由服务端单一真源 `build_store_projection` 现算，前端不重造 39 列→stable-key 映射。真实 HTTP 验证：D2 得 `field_count=28431`、`row_count=729`。`test_task28` 100 passed（含 read-only-action 双向匹配 + slashed-entry 路由矩阵同步）。
- **真库只读纠正**：D2/G7/H1 三 entry 均已有 current published representation + approved bundle，`register_from_manifest` 全注册、`assert_bidirectional_ready` 全 PASS。推翻上一轮 sub-agent 基于过时 docstring 的「D2 无供给必 422」判断。
- **端点 fail-closed 验证**：非 store-backed / 不存在 entry 均 422 且原因清晰（`sync_pilot_store_payload_invalid` / `adapter_stale`），无崩溃、无静默空投影。

### 🔴 关键发现（DEC-10）：D2 大表 materialize 同步不可行

真实 HTTP：store-projection 16.7s、pending-mutations 12.9s 均 OK，但 **materialize >300s 超时且 CPU-bound 阻塞 worker**。离线剖析 `push_html_to_excel` 呈超线性（≈O(n²)）：10行6.7s / 50行8.8s / 200行15.9s / 729行59.3s。根因：`_stage_and_verify` 每次 materialize 解析工作簿 ≥3 次 + 每行成本随规模翻倍。这是**可修的低效**，非固有成本。⇒ D2 真实 OO 往返（G4-0d）与前端宿主迁移（G4-0b/0c UI）在此优化前**不可做**（否则「在线编辑」>5min 并 wedge worker，比 legacy 更差）。

### 🔴 运维事件与恢复（如实记录）

驱动重 materialize 时把 dev backend worker 搞 wedged（同步大工作簿构建阻塞事件循环 + 客户端超时留 `idle in transaction` + Windows lingering listen socket）。已完整恢复：guard 化终止 >300s 的孤儿 PG 会话、停 wedged worker、等 socket 释放、以单进程（无 `--reload`）重启 uvicorn ⇒ `HEALTH 200 in 0.4s`。

### 本次修复/改进的具体项

1. **store-projection 端点**：新增并接线（action 词汇表 + provider 白名单解析 + fail-closed），补齐 `test_task28` 分母（`_REQUEST_ENDPOINTS` + 路由矩阵 + guard-first 计数）。
2. **DEC-10 登记进总控**：把 materialize 性能阻塞写成一等事实 + 解除条件，避免后续再撞同一坑。
3. **教训固化**：①health 探针必须 `127.0.0.1`（IPv4）非 `localhost`（Windows ::1 优先）②大表 materialize 必须先离线/小样本剖析再走 HTTP ③同步 materialize 28431 字段非生产安全，需异步/流式。

### 诚实状态

D2-2 仍 `REQUEST_PATH_LEGACY`，`working_paper_content_application`=0，未宣称 `bidirectional_verified`。真实阻塞已从「未知统一路径是否可行」精确到「materialize 大表性能」这一个可定位、可修的点。下一步应立**materialize 性能 spec**（缓存 substrate extract / extract O(n) / 异步化），完成后 D2 canary 的真实 OO 往返即可推进。

### 本次回归

- `test_task28_sync_router` 100 passed；`test_workbook_row_change_delete` + `test_g1_2/g1_3` 合计 153 passed；前端 `d2SyncDurableGate` 10 passed。
- 触及生产文件 `wp_sync_router.py` py_compile 通过；无 tmp_ 残留；backend `HEALTH 200`。
