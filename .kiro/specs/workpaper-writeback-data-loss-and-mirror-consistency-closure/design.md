# 设计：底稿双向回写保存安全与镜像一致性收口

## 1. 现状与基线

基线提交：`de31e7bf6fbb0a2403054c611a90028262e66ba7`，与远端当前分支一致。相关生产文件在主工作区无本地 diff；实施放在仓库根锁定的分离头工作树，避免覆盖并发会话。

现算事实：

- generated manifest：155 个 entry，122 个缺 adapter、142 个无 durable forcesave ack、124 个无 forcesave command。它们不纳入本轮 adapter 迁移。
- pendingWrites 旧棘轮 108 条。逐文件调用链复核：2 个 composable 无生产消费者；其余 106 个都没有形成“清 timer + 等真实 PUT”的完整屏障。26 个自管 D4 bridge 即使清了 timer，`dispatchEvent()` 也不会 await 异步 listener。
- 父写入链共 10 条：`d4`、`f2` 主/估值/特殊/盘点、`f3`、`f4`、`f5`、`g2`、`g4`。当前都没有把完整保存 Promise 交给 `trackPendingWrite`。
- `checklist_responses` 已支持可选 `if_match`，但通用持久化和多数循环 formData 丢掉 GET 返回的 version；无版本仍按 LWW 并只在回执标 `overwritten=true`。
- OO→HTML 当前先提交 canonical content，再调用 `store_mirror`。多 item 路径按块/按 item commit，后段失败会留下 canonical 新、HTML store 部分新部分旧。
- 前端相关基线 18 passed。后端 provider surface 81 passed、D2 store equivalence 24 passed；完整 app 路由测试在干净 HEAD 采集期因 `project_creation_grant_service` 未入库而失败，属于基线阻断，不把它算成本轮回归。
- 磁盘最高迁移 V234，共享库最高已应用 V232。本设计复用现有表与事务，不新增迁移。

## 2. 决策

### 2.1 镜像方案

比较两种方案：

| 方案 | 一致性 | 锁时长 | 恢复复杂度 | 改动面 |
|---|---|---:|---:|---:|
| A. canonical commit 后写 durable mirror job | 最终一致；UI 需新增 pending 状态 | 短 | 高：需冻结 provider/contract/payload、worker、状态迁移和重放 | 大 |
| B. 在 content commit hook 内 `commit=False` 镜像 | 单事务强一致 | 增加 store SQL/JSON merge 时间 | 低：失败沿既有 durable incoming retry | 小 |

选择 B。xlsx 提取、materialize、roundtrip 等 CPU 重段已经在事务外；事务内新增的是 checklist 读取、provider 纯 merge 和 SQL 写入。正确性收益高于增加的短事务成本。若后续压测证明镜像临界区超预算，再以本次原子行为为契约拆成“冻结最终 store payload + CAS job”，不能退回无状态的 post-commit best effort。

### 2.2 CAS 兼容策略

`BatchSaveRequest` 新增 `require_if_match=false`。已迁移客户端固定传 true：

- 行不存在：允许创建；
- 行存在且无 `if_match`：428 `version_required`；
- 行存在且版本不同：409 `version_conflict`；
- 兼容客户端不传该开关：维持原 LWW，并继续回 `overwritten=true`。

前端新增单一 helper，维护 `item_id → version`。加载完整 checklist 时记版本；保存时按 map 发送 `if_match` 和 `require_if_match=true`；成功回执推进 map。版本未知而服务端已有行时宁可 428 保脏，不自动 GET 后覆盖本地快照。

### 2.3 pending barrier

`trackPendingWrite` 内部保存 settled outcome，而不是把 rejection 抹成 `undefined`。`flushPendingWrites`：

1. 并发调用所有 flusher并收集异常；
2. 循环等待 flusher 新加入的 in-flight；
3. 等全部结算后抛 `PendingWritesFlushError(failures)`；
4. 下一次用户重试从新的失败窗口开始，不永久粘住已经成功重试的旧错误。
父 handler 以一个 Promise 覆盖完整批次或顺序循环。子 writer 的 flusher必须是 pending-only：timer 为空直接返回；有 timer才 clear、置空并调用立即保存。这样自身 bridge 后续再次调用相同函数也是 no-op，不会双写。

特例单独处理：

- `useF2Adjudication` 使用 `metaDebounceTimer/flushMetaSave`；
- `useF2Impairment` 的 `adjudicatedTimer` 只发业务事件，不登记为写盘 timer；
- `useF2Adjustment` 先消除注入保存成功后仍派 window event 的双写；
- `F4TabAdjustment`、`F5TabAdjustment` 卸载不能调用会重新建 timer 的 `persist()`；
- `useD4WalkthroughTest`、`D4TabMarginMonthly`、`D4TabCustomerStructure` 的自身 bridge先改为清 timer；
- `useIpoChecklistTab` 按每个 Vue effect scope 注册，不能建模块单例。

## 3. 事务与调用顺序

### 3.1 HTML → OO

```text
用户编辑
  → pending-only flusher 清私有 timer
  → 父 handler track 完整 PUT
  → PUT 使用严格 CAS
  → flushPendingWrites 确认全部成功
  → 宿主 flushHtml / readStoreProjection
  → pending mutation / materialize
```

失败边界：任一 PUT reject，bridge 的 `fail('flush')` 进入 sticky error，后续 projection/materialize 调用次数必须为 0。

### 3.2 OO → HTML

```text
incoming durable
  → base/current/incoming 三方合并
  → 锁外 rematerialize 与等值校验
  → ContentMutationService._commit_once
      → per-wp advisory + working_paper row lock
      → revision / version / representation / pointer
      → CommitFenceHook.after_pointers
          → store_view 补显式 null与可信公式重算值
          → mirror_projection_into_store(commit=False)
          → application / operation / room canonical fence
      → pending mutation / outbox
      → 唯一 commit
  → settle client baseline
```

`_apply_committed` 不再做第二次 mirror。镜像抛错时 `_commit_once` rollback；外层既有 `_record_post_durable_failure` 把同一 application/operation 记为 error，incoming 保留，用户 retry 重新走同一协调器。

## 4. 生产文件规划与 ROI

核心改动：

- 后端：`checklist_responses.py`、`oo_to_html.py`、`store_mirror.py`。
- 前端核心：`checklistCas.ts`、`pendingWrites.ts`、`useWorkpaperSyncBridge.ts`、现有对应单测。
- 保存入口：通用 `useChecklistPersistence`、10 个父宿主、相关循环 formData。
- writer 接线：106 个活路径做机械的 pending-only 登记；2 个死 composable不改生产代码，只从债务表删除并由零消费者守卫钉住。

收益：覆盖当前所有已识别的 2 秒私有防抖写入面；任何保存失败都从“静默打开旧 OO”变成显式阻断；任何 store mirror 失败都从“部分提交”变成整个业务提交回滚。

风险：文件数多但每个 writer 只加一个 import和一个局部注册点。用生成清单、逐文件语义检查、TS 编译、变异和代表性浏览器链控制风险；不顺手改业务公式、表头或 adapter。

## 5. 测试设计

| 层 | 关键断言 |
|---|---|
| TS 单元 | CAS 带版本、成功推进版本、409/428 保脏；pending 多失败聚合且等到全部完成 |
| bridge | pending 失败后 store projection/pending/materialize/mount 均 0 |
| 静态守卫 | 106 个 writer 都有 pending-only 注册；10 个父 handler完整 Promise 被 track；2 个死项仍零消费者 |
| Python 单元 | strict CAS 的 428/409/新建/legacy LWW 四态 |
| mirror 单元 | dedicated 缺门面抛域错误；`commit=False` 下任何分支零 commit |
| 协调器 | mirror 在 hook 内、早于唯一 commit；post-commit 路径无 mirror调用 |
| PG | mirror 第 N 项失败时 revision/version/pointer/application/operation/outbox/store 全保持原值；retry 只推进一次 |
| 浏览器 | 【测试】项目快速切换、失败阻断、OO 往返刷新一致 |

## 6. 非目标与交接

- 不扩大 155 entry 中的 adapter/capability 覆盖；继续由 `oo-writeback-template-parity-closure` 和逐循环 spec处理。
- 不把 Univer 纳入 content/application 协议。
- 不在本轮把 callback apply 改成异步 worker，也不做 room/recovery 历史账面清理。
- 后续顺序：callback durable 后异步化与生命周期 reaper → adapter/template 覆盖 → Univer 统一 → 6000 人容量验收。

## 9. 三件如实标注项的逐一收口（2026-11-01 续做）

上一轮交付时如实标注了三件未完成/未修的事，用户要求逐一修复。本节记录实际做到了哪一步、
为什么，以及仍需拍板的部分。

### 9.1 第一件：后端侧没有浏览器证据

原因不是"没做"，而是候选后端起不来。逐层排查后发现**三个 HEAD 级 P0，都不是本 spec 引入的**，
且它们让整个平台处于起不来的状态：

| 现象 | 根因 | 归属 | 处置 |
|---|---|---|---|
| `app.main` 导入即 `NameError` ⇒ 后端整体起不来、CI `pytest -x` 必死 | `adjustment_import.py:82` 用了 `require_project_permission` 却没 import（其余 5 个调整分录路由都 import 了） | `3cd7352a6 WIP: adjustment module A-E batch`（`git blame -L 80,84` 定到行） | 补 import。守卫 `test_router_modules_mounted.py` **本来就能抓到**，当时正红在这一行 —— 是带着红守卫推的 |
| 前端 `DefaultLayout.vue` 500 ⇒ 整个前端起不来 | `ThreeColumnLayout.vue` 把 `useMountOnFirstOpen` import 了两次，`Identifier has already been declared` | `a6c1fa93a feat(platform-perf)` | 删重复 import |
| `MigrationRunner` 同号即抛 ⇒ **全平台迁移一条都跑不了**（health `check_error: RuntimeError`、`applied_count: 0`） | 三组迁移撞号：V233 / V235 / V236 | 并发会话 | 见 §9.2 |

修完后：`app.main` 导入通过（2619 条路由）、`test_router_modules_mounted.py` 3 passed、
候选后端在 9981 起来、候选前端在 3032 服务、`scan_migrations` 248 个迁移最高 251 无重复。

**仍差一步，需要放行**：候选后端连的共享库停在 **V234**，而 HEAD 代码需要 V235~V251。
现算确认只有一处落在 OO 往返路径上 —— `projects.amount_unit`（V250）缺列使
`GET /api/projects/{id}` 恒 500，前端的年度闸门因此不渲染页面；
`checklist-responses` 与 `render-config` 都是 200，`consol_operation` 缺表只影响后台 worker 噪音。
对 30 GB 的共享开发库应用 17 个迁移属"共享记账类写操作"，按既有纪律须先问。
启动时已用 `GT_BOOTSTRAP_DONE=1` 跳过迁移，确保本轮排查**没有改动共享库 schema**。

### 9.2 迁移撞号的处置依据

现扫事实：共享库最高已应用 V234（V233 = `V233__project_creation_grants.sql`）；磁盘最高 V249；
`display_preferences_and_project_amount_unit.sql` 同时存在 V233 与 V235，**两份只差注释里的版本号**
（纯改号残留），而它自己的 model docstring 已漂到"V240"。

按"撞号时改未应用的那一侧"：

1. 删 `V233__display_preferences_and_project_amount_unit.sql` + 配对的 R233
   —— V233 已被已应用的 `project_creation_grants` 占用；
2. V235 保留 `adjustment_review_tasks_and_group_revision`（3 处代码引用），
   `display_preferences_and_project_amount_unit` → **V250**；
3. V236 保留 `ai_chat_run_context_request_snapshot`（V/R 同 stem 自洽、测试按文件名钉死），
   `formula_provenance_report_runs` → **V251**；
4. 同步改：迁移文件首行注释、`core.py` / `models/__init__.py` / `user_display_preferences.py`
   的版本注释、按文件名钉死的 `test_formula_provenance_report_schema.py`。

### 9.3 第二件：D4 四个 dedicated item 首次真正接受镜像写入

注册表常量改名让 D4-8 / D4-33 / D4-34 / D4-36 从本轮起第一次真正写入，风险是"开始写就写坏"。
现已逐个用**各自真实载荷形态与身份键**的最小非空基线实测：空投影下 `applied=0` 且基线逐字段
原样带回。守卫 `tests/workpaper_sync/test_dedicated_store_merge_is_non_destructive.py`（17 例）。

🔴 判据写到第四版才站得住，前三版全是**夹具造成的误报**，教训固化在该文件 docstring 里：

1. 统一夹具 `{unmanaged, tables:{rows}}` ⇒ 误报 D4-35（它的契约只返回
   `{rows, sampling, periodAmount}`，正确地忽略了不属于自己的键）；
2. 行统一用 `{"id": ...}` ⇒ 误报 D1-memo-rows（它声明 `ROW_IDENTITY_KEY = "rowId"`）；
3. 行不带身份键 ⇒ 误报 D4-34 / D4-36（它们 `if r.get("id")` 过滤无身份行后按 order 重建）。

这正是"口径类判据必须拿真实接口现读"的又一次复现：三次都是我的夹具错，不是代码错。
所以守卫里加了 `test_handmade_bases_match_the_canonical_shape`（手写基线的键必须等于 merge
自己产出的键），夹具一漂就打红，而不是变成"测了个不相干的结构"。

### 9.4 第三件：上一轮语义审查记为"范围外"的 7 项残留

清单即下表（上一轮只修了 P1-1~P1-3，见任务 8；其余 7 项当时如实标注为范围外）。

| 项 | 处置 |
|---|---|
| 残留 1：`_INCLUDE_D4xx_*` flag 失去闸门 + 注释 stale | 不新增机制，改为注册表不变量：**每个 dedicated item 的 item_id 必须出现在本 adapter 声明的 store item 集合里**（现算 7/7 成立）。flag 翻 False 后 `STORE_ITEM_IDS` 会排除该 item 而 dedicated 照跑 ⇒ 不变量当场打红，不再静默分叉。stale 注释改成勘误说明 |
| 残留 2：K1 `dedicated_items` 永不执行 | 🔴 排查中发现比原判更重的缺陷：K1 载荷是 dict，却被接到单 store 的 **rows** 分支，而该分支解码 base 时是 `if isinstance(parsed, list)` ⇒ dict 基线留在 `[]`，**每次镜像清空既有行与未受管标量**（真库 K1-9 当前 0 行，属潜伏缺陷，首次使用即损坏）。改 `merge_state_fn="merge_k1_from_projection"` 走 dict 感知的 state 分支（该函数返回的正是 state 分支要的 3 元组，provider 本来就是按 state 形态写的），并删掉永不执行的 `dedicated_items`。触类旁通按**运行期解析**全仓扫 69 个走 rows 分支的 plan，K1 是唯一一例、零无法解析（第一版 AST 探针把 20 个共用函数的 provider 误判成"找不到"） |
| 残留 3：逐 item 两条锁语句 | `FOR UPDATE` 合并为一条 `item_id = ANY(:ids)`（46 个 item 时 92 → 47 次往返）。**advisory lock 保持逐条有序**：死锁安全完全依赖"两条路径都按 item_id 升序逐个取锁"，单条语句里对集合的函数求值顺序 PG 不保证，合并会把往返换成偶发死锁。守卫断言往返形态与取锁顺序 |
| 残留 4：屏障文案只有计数 | `PendingWritesFlushError` 把 `failures` 里的原始原因摊进文案（去重、最多 3 类、超出折叠计数），并暴露 `reasons` 供界面逐条列出；axios 信封 / Error / 字符串三种形态都能取到 |
| 残留 5：14 个 G formData 仍是 LWW | **未做**。R1.3 明文允许，且已有"只许缩短 + 与 strict 清单互斥"的单向棘轮。迁移需要 14 个带草稿/重试/TB 逻辑的 formData 各自维护 `item_id → version`，是独立一轮的改动面 |
| 残留 6：裸 PUT 未传 `_dedupe: false` | 14 个文件 15 处 PUT 全部补上（与已迁移的 11 个 strict CAS 调用面一致）。此后 `ERR_CANCELED` 回到"只可能来自调用方自己的 signal"，`_doSave` 对 canceled 不重抛才真正安全 |
| 残留 7：F2 事件无监听方卡满 8 秒 | detail 上加同步 `accept()` 回执。`window.dispatchEvent` 对 CustomEvent 是同步的 ⇒ 派发返回后仍未被 accept 就一定没有监听方，立即失败并给出可操作文案；只有已 accept 的才进 8 秒超时（那才是真的"在处理但卡住"）。宿主 `handleSave` 在第一个 await 之前 accept |

### 9.5 本轮验证

- 后端：`test_store_merge_registry_invariants.py` 9 例、
  `test_dedicated_store_merge_is_non_destructive.py` 17 例、`test_router_modules_mounted.py` 3 例全绿；
  真实 PG 并发与镜像原子性 12 passed。
- 前端：pending / CAS / F2 监盘 / G 支线定向 67 passed（含残留 4、残留 7 的新判据）。
- 变异：5 条 RED 且逐字节恢复 —— K1 回 rows 分支、K1 加回永不执行的 dedicated 声明、
  D4-34 不从 base 起步、手写夹具漂移、D4-33 flag 翻 False。

### 9.6 本轮归因：哪些红不是本轮引入

按「见红先在干净 HEAD 上复跑」的纪律逐条归因（干净 HEAD = `4390aaaa3`，同一台机、同一批命令）：

| 现象 | 干净 HEAD | 候选树 | 归属 |
|---|---|---|---|
| `tests/test_migration_drift_ledger.py` | **22 条全部 ERROR**（撞号 RuntimeError，守卫完全失明） | 20 passed / 2 failed | 预存。修完撞号后守卫才真正跑起来，于是暴露出 `V200` / `V201` 的 drift 台账条目**对应的迁移文件不在磁盘上**（两边 `migrations/V20[01]*` 都为空）。这与 memory 里登记的「`V201`/`R201` 重复迁移待迁移负责人裁决」是同一件事，交迁移负责人 |
| 改动过的 7 个 py 文件 ruff | **33 errors** | 32 errors | 预存（本轮少 1 条，没新增） |
| `test_report_provenance_migration_matches_model_surface` | 在上面那 22 条 ERROR 之外另算 | 失败 → 已修 | **本轮引入**，见 §9.7 |

### 9.7 自己脚本的 bug：同文件多编辑互相覆盖

`fix_migration_collisions.py` 第一版对每条文本编辑都**各自从磁盘读原文**，改完 append 到
待写清单，最后统一写盘 ⇒ 同一文件的第二条编辑覆盖了第一条，**前面的编辑静默丢失**。
实际丢了 3 条：`models/__init__.py:225`（V233 → V250）、
`user_display_preferences.py:3`（V240 → V250）、
`test_formula_provenance_report_schema.py:113`（V236 → V251，正是上表那条红）。

只有第三条被测试咬出来 —— 另两条是注释，不会让任何测试变红，差点就带着错版本号入库了。
已改为在**累积结果**上逐条改（`pending: dict[Path, str]`），并补跑一次复核：
这三个文件里不得再出现旧版本号（现算残留 0）。

教训：批量改写脚本只要允许「同一文件多个靶点」，就必须把中间结果带下去；
「每条独立读原文 + 最后统一写盘」在单靶点时正确、多靶点时静默丢数据，
而注释类编辑丢了不会有任何守卫报警。
