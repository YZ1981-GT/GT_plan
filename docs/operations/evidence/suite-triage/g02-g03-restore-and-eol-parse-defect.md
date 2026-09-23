# G0-2 / G0-3 交付物找回 + 两处真缺陷（2026-09-24）

本文件记录三件独立的事，按发现顺序。每条都写清「测得什么」与「没测到什么」。

## 一、milestone DB 探针「隔次失败」= 同一棵树两份 projection（真缺陷，已修）

### 现象

同一进程内重复调 `collect_database_probe_facts()`，status 交替：

```
1 ok
2 database_unavailable
3 ok
4 database_unavailable
5 ok
```

第 2/4 次报 `phase=connect code=AttributeError`（更早的观测）/`RuntimeError: Event loop is closed`（本次复现原文）。
后果：`build_program_registry()` 跑两次得两份不同 projection，2 个 milestone 在
IMPLEMENTED↔BLOCKED 间抖动 —— **门的结论取决于它是第几次被调用**。

### 根因

`collect_database_probe_facts` 用 `asyncio.run(_collect_database_catalog())`：每次调用
**自建并关闭**一个事件循环。而 `app.core.database.engine` 是模块级常驻连接池
（本机 `_is_postgres` 分支 `pool_size=max(DB_POOL_SIZE,20)`，非 NullPool），asyncpg 连接
绑定在**创建它的那个循环**上。第 2 次探测从池里取到第 1 次留下的连接 → 该连接的 loop 已
关闭 → 在 `await session.connection()`（`phase="connect"`）炸 →
`status=database_unavailable`。失败连接随即被 invalidate，故第 3 次又能新建成功 —— 这就是
「隔次」的成因。

### 修复

`_collect_database_catalog` 在**同一循环内** `await engine.dispose()`（`finally`），即
「谁开循环谁清池」。`dispose()` 自身失败才改写 `phase="dispose"`，不覆盖在途异常的
phase（否则 connect 失败会被误报成 `query_failed`，把 blocked 说成 fail）。

### 变异检验

| 变异 | 结果 |
|---|---|
| 把 `await engine.dispose()` 换成 `pass` | **RED**：恢复 `ok/unavailable/ok/unavailable/ok` |
| 还原 | GREEN：`ok×5`；文件字节比对一致 |

### 回归判据

`test_repeated_in_process_database_probe_is_deterministic`：同进程连续两次探测 facts
**逐字段相等**且与 registry 首次探测的 status/failure 一致。
无库环境下两次都是 `database_unavailable` ⇒ 判据仍成立（断的是「两次一致」不是「必须 ok」），
故它在 CI 无库时不会伪绿也不会误红。module 级 `source` fixture 已先跑过一次探测，
所以本判据的**第一次调用就落在当年的失败位**上。

## 二、G0-2 与 G0-3 是同一种假收口：工作在一次性 checkout 里做完，只搬回了一部分

两张执行卡都自署 `"status": "CLOSED"`，`modified_files` 都含对应 `tasks.md`，但**主工作树里
tasks.md 的 hunk 从未落地**。两卡的验收段各自写着「主工作树仅精确暂存 …」，而枚举出来的
暂存清单里**没有** tasks.md 的正文改动 —— 只有 generator、守卫、generated projection 与
evidence。generator 的通用 dependency-order guard 在树上（加边会抛
`same-wave non-earlier tasks`，正是它），测试与 projection 也在树上，唯独被它们判据的
**文档没改**。⇒ 四条红不是「谁偷懒」，是一次 checkout 交接漏搬。

### 交付物（按两卡原文逐条落地）

G0-2（owner 裁决表，`evidence/g0-2-denominator-discovery-state/README.md`）：

| Task | 标题承诺 | 已交付事实 | 记号 |
|---|---|---|---|
| 1 | 全量入口 manifest 与归一化清册 | discovery/characterization | `[x] → [~]` |
| 2 | 假双向红基线与能力态守卫 | characterization 红基线 | `[x] → [~]` |
| 20 | 关闭 writer/version domain gate | 门可信，债未归零 | `[x] → [~]` |
| 60 | F2 迁统一 Word adapter 并 finalize | 只交付勘查/欠账登记 | `[x] → [~]` |
| 62 | 迁移 18 个 generic DOCX entry | 只交付裁决与守卫，0 迁移 | `[x] → [~]` |
| 64 | 迁移 A16/A17 Word 链与宿主 | 只交付裁决 | `[x] → [~]` |

加 5 份 spec 的 overview 分母。G0-3：core Task 72 独立成 **Wave 8**、`72` 依赖加 `74`、
overview 改「9 个 Wave」。

### 为什么这不是「改标记凑绿」

判据方向相反：`[x]→[~]` 是**下调**交付声明，不是上调。三重独立确认：

1. **任务正文自证**。Task 1 正文原文就写着「本任务 `[x]` 只代表 discovery/characterization
   已完成，不代表 profile、adapter、DOM、真实 OO 或回写闭环已验收」—— 一个标着"完成"的
   任务自带"未完成"免责声明，`[~]` 才是它的真态。
2. **owner 授权在案**。裁决表出自 program-governance 自己的执行卡，不是我替它判的。
3. **分母独立现算**，没抄测试字面量：用 live parser 跑 8 份 tasks.md 得
   `core 77/77·0opt`、`published 43/28·15opt`、`structural 27/22·5opt`、`workbook 30·7wave`、
   `template 27·7wave` —— 与测试断言逐项吻合，故测试的字面量本身是对的。

### 结果

`test_workpaper_sync_program_milestones.py`：**4 failed → 1 failed / 22 passed**。
`diagnostics 6 → 5`（且只删掉 `archive_bypasses_writer_debt`，与 G0-3 卡预言一致）。
core waves `8 → 9`。`test_task20_writer_gate.py` 33 passed（task 20 记号改动无附带损伤）。

### 仍然红的一条，以及为什么不动它

`test_g0_3_does_not_promote_tasks_milestones_or_g0_4`：`BLOCKED 由 3 升到 6`。

- 6 个 BLOCKED（`PUBLISHED-ENTRY-READY` / `ROW-MUTATION-READY` / `SYNC-ENTRY-NAMESPACE` /
  `SYNC-MULTI-RESOLVER` / `TEMPLATE-OVERRIDE-CHANGED` / `X-RUNTIME-EVIDENCE`）**没有一条
  predicate 失败**，全部卡在 definitions 层：4 条 `natural_language_producer_placeholder`
  + 1 条 `producer_tasks_missing`，各有点名 owner。
- 这条上限**在 G0-3 收口当天就已被突破**：G0-3 卡自记基线 `BLOCKED=4`，而断言是 `<=3`。
  即它不是本轮改动造成的回归。此后 2 条由 STALE 转 BLOCKED（`STALE 9→7`）。
- 抬上限 = 放宽判据。守卫原文要求「要提升必须先有 producer task + 重算 evidence，并在此
  显式抬高上限」；我没有 producer 也没有授权，故**留红**。
  解阻条件：为那 5 条 diagnostic 点名的 milestone 补机器可判的 producer task。

⚠️ 未测：那 6 个 milestone 的 producer 是否真能在各自 spec 内交付（属别的 owner 范围）。

## 三、AC coverage matrix 解析器的 CRLF 缺陷（真缺陷，已修）

### 现象

`test_workpaper_ac_coverage_matrix.py` 6 红，报
`CoverageMatrixError: Property 1 has no Validates line before L1453`。
但 design.md L1447 是 `### Property 1: …`，**L1451 就是** `**Validates: Requirements 1.1**`。

### 根因

`_read_lines` = `path.read_bytes().decode("utf-8").split("\n")`。仓库
`core.autocrlf=true` 且 `.gitattributes` 未对 `*.md` 强制 `eol=lf` ⇒ 工作树里三份 spec 文档
全 CRLF（design.md 1993 CRLF / 0 lone LF），每行尾留 `\r`。于是：

- 以**字面量**收尾的锚点失配：`_VALIDATES_RE` 的 `\*\*$`、oracle 表头行的整行 `.index()`；
- 以 `.*$` 收尾的锚点却把 `\r` 吞进 title 照常匹配：`_PROP_HEAD_RE`。

这个不对称把「Property 1 有 Validates 行」报成「没有」——**解析缺陷伪装成文档缺陷**。
同一份 design.md 在 CI(LF) 绿、本地(CRLF) 红。

### 修复

读取侧归一化（先 `\r\n`/`\r` → `\n` 再按 `\n` 切；不用 `splitlines()`，它还会在
`\x0b`/`\x0c`/`\u2028` 断行使行号与文档不符）。测试侧的 `_doc()` 改为**委托** `_read_lines`，
读取器单源。摘要仍摘原始字节，EOL 捕获口径统一属另案（D-EOL-1），未夹带。

### 顺带查明：digest 不匹配是真漂移，不是 EOL

| | raw sha256 | LF-归一化 sha256 |
|---|---|---|
| design.md | `dfb2ca8607594ab0…` | `f6a4ade522314fb9…` |
| matrix 内 pin | `6d7ab5ca05acc71d…` | — |

pin 值既不等于 raw 也不等于 LF ⇒ design.md **内容确实变过**，需 `--apply` 重算（这也是
测试自己的错误提示给的动作）。修完解析器后 `--apply` 得
`ac=170 / property=72 / task=77 / family=14`，`--check` OK。

### 结果

`test_workpaper_ac_coverage_matrix.py`：**6 failed → 50 passed**。

### 同类反模式全仓 grep

`read_bytes().decode(` 共 20+ 处，逐一核：多数已显式归一化（`test_task30_closure_gate`、
`test_downstream_base_reliability_gate`、`check_task44_…`、`mutate_ie_lifecycle_guards`）
或读 JSON（`\r` 无害）或**故意**保留 CRLF（`_mutation_kit/anchor.py` 为还原核验）。
唯一余下同形：`tests/workpaper_sync/test_task20_writer_gate.py:146` 按 `split("\n")` 切
task body —— 实测 **33 passed**，其 `_TASK_HEAD_RE` 以 `.*$` 收尾故容错，`\r` 只是留在
body 字符串里。登记为**潜在**（与既有 14 条 latent 同级），不在本轮改动。

## 四、pilot 宿主的「统一路径」判据把过渡态当成了永久不变量（已重述 + 变异检验）

### 用户的下一步被它挡住

用户计划「比照 D4 的底稿来修复 D2 的所有底稿」。开工前必须先定：**哪个 bridge 是正统**。
`test_task45_pilot_legacy_deletion.py::test_host_imports_bridge_adapter[GtD2AccountsReceivable.vue]`
要求 D2 宿主 import `usePilotBridgeAdapter`，而 D2 宿主 import 的是 `useWorkpaperSyncBridge`。

### 裁定：终态是 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`

依据是 `usePilotBridgeAdapter.ts` **自己的 docstring**（不是我的判断）：

> 「这不是长期方案 —— Wave 5 的每个 entry 迁移时宿主会直接用 `WorkpaperSyncEditorHost`
>   并彻底删除 adapter-shaped wiring。本层只是 Task 45 的过渡胶水。」
> 「删除条件：当四个 pilot 宿主全部改为直接渲染 `WorkpaperSyncEditorHost` 时，本文件删除。」

五个 pilot 宿主现状（剥注释后现算）：

| 宿主 | adapter | editorHost | bridge | 形态 |
|---|---|---|---|---|
| `GtG7LongTermEquityMain.vue` | Y | n | n | 过渡态 |
| `GtH1FixedAssets.vue` | Y | n | n | 过渡态 |
| `GtD2AccountsReceivable.vue` | n | **Y** | **Y** | **终态** |
| `GtB60Bundle.vue` | Y | n | n | 过渡态 |
| `GtB60DocxPane.vue` | Y | n | n | 过渡态 |

D2 于 `42d2f6e6f` 走完 Wave 5 迁移，是五个里唯一到终态的 —— 所以**只有它红**。

### 为什么原判据必须重述而不是"让 D2 退回 adapter"

原判据是「必须 import `usePilotBridgeAdapter`」。按 adapter 自述的路线，**每个宿主完成
迁移都会把这条打红**，而红的那一刻它恰恰更接近目标；等四个宿主都迁完、adapter 依约删除时，
同文件的 `test_pilot_bridge_adapter_exists` 也会一起红。照原样留着，唯一的"修法"是把生产
代码**倒退**回过渡态 —— 判据在逼着实现走反方向。

Task 45 真正守的是 AC 11.1「不存在与 sync bridge 并行的第二条路径」，由两条判据分担：
`test_host_does_not_import_deleted_composable` 断死 legacy 侧（D2 本来就过），本条断活
统一侧。故本条改名 `test_host_is_on_the_unified_sync_path`，接受两种合法形态：

* 过渡态：`usePilotBridgeAdapter`
* 终态：`WorkpaperSyncEditorHost` **且** `useWorkpaperSyncBridge`（要求两者同时在场，
  比原判据更严 —— 只写组件名不接 bridge 不算）

两形态皆无仍然红。先剥 HTML/块/行注释再判，散文喂不饱门。

### 变异检验（5 参数化用例）

| 变异 | 结果 |
|---|---|
| 基线 | 5 passed |
| MV1 D2 抹掉 `WorkpaperSyncEditorHost` 引用 | **1 failed** |
| MV2 D2 抹掉 `useWorkpaperSyncBridge` 调用 | **1 failed** |
| MV3 G7 抹掉过渡态 `usePilotBridgeAdapter` | **1 failed** |
| MV4 D2 两个终态标记只留在 `//` 注释里 | **1 failed** |
| 全部还原（逐文件字节比对） | 5 passed |

MV4 是关键：它证明剥注释真的在起作用，否则「在注释里写上组件名」就能通过。

### 对 D2 扫尾的结论

D2 底稿按 **D2 自己已走通的终态**（`WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`）
推进即可，`test_task45` 不再挡路。`usePilotBridgeAdapter` 不要再新接线 —— 它在等 G7/H1/B60
迁完后删除。

⚠️ 未测：D2 宿主 `:244` 仍留 `v-else-if="useOnlyOfficeFallback"` 的 legacy `GtOnlyOfficeSheet`
分支（既有登记项，不在本条范围）。

## 五、`/d2-sync/*` 退网的真实阻塞面：180 个宿主，0 个能寻址统一端点

用户问：「D2 退网授权会影响 D2-2 吗？」结论先给：**不影响 D2-2**，但影响面比先前登记的大得多，
且性质不是「注入一个 prop」。

### 实测

| 事实 | 数 |
|---|---|
| 渲染 `GtOnlyOfficeSheet` 的宿主（排除组件自身） | **180** |
| 其中注入 `forcesaveEndpoint` 的 | **0** |

`GtOnlyOfficeSheet.vue:301`：

```
props.forcesaveEndpoint || `/api/workpapers/${props.wpId}/d2-sync/forcesave`
```

组件第 49 行自己写明「默认仍指 legacy `/d2-sync/forcesave`」。⇒ 180 个宿主的 forcesave
**全部 fail-open 落进 legacy 路由**。而 `d2_sync_router.py` 把 `_OO_WP_CODE` / `_OO_SHEET_PARAM`
硬编码成 `"D2-2"`，room entry 固定 `xlsx-sheet/D2-2/D2-2` —— 所以这 180 个宿主的 forcesave
其实都在借 D2-2 的壳发车。

### 先前的解阻设想不成立

门 `check_d2_sync_retirement_eligibility.verdict_forcesave_fail_closed` 要
`forcesaveEndpoint` + `if (!endpoint)` + `accepted: false`。先前登记的解法是「让宿主注入
prop」。**做不到**：统一 forcesave 是

```
POST /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/rooms/{room_id}/forcesave
```

它要 `project_id` + `entry_id` + `room_id` 三样。而 `GtOnlyOfficeSheet` 只有 `wpId` /
`sheetName` / 可选 `projectId` —— **既没有 entry_id 也没有 room_id**，它在结构上无法寻址
统一端点。改组件里那个默认 URL 也不行（同样缺 entry/room 身份）。descriptor → room → entry
的解析归 `WorkpaperSyncEditorHost` 所有。

⇒ 真正的解阻动作是把这 180 个宿主迁到 `WorkpaperSyncEditorHost`（Wave 5/6 的逐 entry 迁移），
不是改一个默认值，也不是逐宿主传 prop。

### 对 D2-2 的影响：无

D2-2 走统一路径（`GtD2AccountsReceivable.vue` 渲染 `WorkpaperSyncEditorHost` +
`useWorkpaperSyncBridge`，见上一节实测表）。legacy 路由被硬编码到 D2-2 这件事反而说明：
**留着它对 D2-2 是风险**（180 个宿主借 D2-2 的壳写盘），删掉它是保护而不是破坏。

### 排序（不变）

E3e 改 fail-closed **必须晚于** 180 宿主迁移；当前把它翻成 fail-closed 会直接打断 180 个
宿主的 forcesave。故那 9 条红保持红 —— 它们是删除资格的前置条件，不是待修的判据缺陷。
本节把解阻条件从「注入 prop」修正为「180 宿主迁 `WorkpaperSyncEditorHost`」，属**范围级
决策**，需用户拍板后才动。

⚠️ 未测：180 个宿主里有多少已有对应 manifest entry / adapter（决定迁移是逐个改模板还是
可批量）。

## 六、本轮测量与「等一次提交」的 36 条

### 两次测量口径不同，先对齐

| | 范围 | 结果 |
|---|---|---|
| `final-rerun-2026-09-24.txt` | 全量套件（未覆盖 `workpaper_sync_oo/chaos/predelete`） | 58 failed / 8659 passed / **0 errors** |
| `ws-rerun-after-fixes.txt` | `workpaper_sync` + `_frontend` + `_oo` + `_chaos` + `_predelete` | **67 failed / 8951 passed** / 2 skipped / 16 xfailed |

基线是 `283 failed / 8294 passed / 16 errors`。

逐条 diff（before ∖ after）**本轮清掉 6 条**：`test_task12::test_matrix_is_fresh`、
`test_task45::test_host_imports_bridge_adapter[D2]`、`test_task58::test_ledger_is_in_sync_with_sources`、
`test_task63::test_bp16_manifest_criterion_is_recomputed_from_the_manifest`、
`test_task63::test_source_digests_cover_every_file_the_measured_criteria_read`、
`test_task64::test_generator_check_is_idempotent`。范围外另清 7 条
（AC coverage matrix 6→0、program milestones 4→1）。

### after ∖ before 的 15 条不是本轮引入的回归

它们全在 `_oo` / `_chaos` / `_predelete` 三个目录 —— 前一次测量**没覆盖**。
且它们卡在各门的 `source_commit` / `plan_commit` 锁上，而那些锁 pin 的 commit
**早于本会话**：

| 报告 | pinned commit | == HEAD(`fb7a0ace2`)? |
|---|---|---|
| `…task71_mutation_capacity_recovery.json` | `c882f831c9eb` | 否 |
| `…task72_pre_delete_eligibility.json` | `d330d7cea6bb` | 否 |
| `…task66_legacy_deletion_plan.json` | `d330d7cea6bb` | 否 |

⇒ stale 轴在我动手前就已触发。本轮的 core `tasks.md` 改动只是给 task71 的漂移键**多加了
一个** `dag_dependency`（Wave 8 那条边），不是把绿打成红。

### 这 36 条共用同一个解阻动作：先提交

`test_task66`(14) + `test_task67`(6) + `test_task68`(1) + `test_task70`(8) + `test_task71`(2)
+ `test_task72`(5) = **36 / 67**。

不能先 `--write` 再提交，理由是两条**门自己写明**的机制：

1. `check_task71_…_gate.py:163` 原文：
   > `source_commit` 刻意不在 `VOLATILE_KEYS` 名单里 —— 它是「源码变了但证据没刷新」这条
   > stale 轴的**唯一锁**。

   报告写 `source_commit = git_head()`。工作树有 ~151 处未提交改动，此刻重生成会写下
   `source_commit = fb7a0ace2`，**声称证据对应一个内容并不相符的 commit** —— 正是这把锁
   要防的形态。
2. `generate_task66_legacy_deletion_plan.py` 的 rollback 指令是
   `git checkout {plan_commit} -- {path}`。在脏树上重算，plan 会承诺「这些文件可从
   plan_commit 恢复」，而实际恢复出来的是**旧字节**。假可逆承诺比红更危险。

同一处还写着 `Tasks 61/66/67/68/69/70 产物禁改`。

⇒ 正确顺序：**提交 → `--write` → 复核 diff**。提交属用户授权范围，故停在此处等拍板。

### 其余 31 条分类

| 类 | 条数 | 状态 |
|---|---|---|
| `d2_sync_retirement` | 8 | 诚实红，解阻 = 180 宿主迁移（见 §五） |
| `projection_lane_regression_gate` + `task61` 三臂 | 5 | 已登记分歧：manifest 侧 human-reviewed override 判 bidirectional，门侧机器判首发布前置未交付。**刻意不消除** |
| `program_milestones` `BLOCKED<=3` | 1 | 诚实红（见 §二） |
| `workbook_row_change_zero_regression` 冻结基线 | 1 | 拒绝重新冻结（D7 两个 `insert_ctx` 都漂了） |
| `task69` 前端 | 1 | 拒绝 `--write`（重算得 `verdict: failed`，写入会把 failed 焊进基线并危及同文件另 78 绿） |
| `template_override` `_index.json` size 漂移 | 1 | 待 owner 拍板（451/23 vs 447/27） |
| `downstream_base_reliability_gate` | 1 | 750 条 blocking facts 下磁盘上仍有 4 处 entry 级验收断言 |
| 未细分（task50 3 / task46 2 / task42 3 / task43 1 / task52 1） | 10 | 部分已定位（task46 见下） |

### task46 的 2 条：权威模板目录有未跟踪污染

判据逐一枚举 `backend/wp_templates/D/` 全部文件（只排除 `~$` 锁文件）并要求与冻结 slice
集合相等。实测 `D/` 24 文件 / slice 登记 18，差 6：

| 磁盘多出 | git 跟踪 | 备注 |
|---|---|---|
| `D3 预收账款.xlsx.preclean.bak` | **否** | 内容唯一，删了不可恢复 |
| `D4 收入底稿.xlsx.preclean.bak` | **否** | 与 tracked 的 `D4收入底稿.xlsx` **字节相同** ⇒ 纯重复 |
| `D5 应收款项融资.xlsx.preclean.bak` | **否** | 内容唯一 |
| `D6 合同资产.xlsx.preclean.bak` | **否** | 内容唯一 |
| `D7 合同负债.xlsx.preclean.bak` | **否** | 内容唯一 |
| `D4 收入底稿.xlsx`（**带空格**，199176 B） | 是（`d3b3d80d9`） | slice 未登记 |

补充事实：slice 里 `D4收入底稿.xlsx`（**无空格**，352950 B）已登记且 `belongs_to_entry=None`
（显式排除）；D4 entry 的 `template_ref` 实为
`D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`，**不是**任何 `收入底稿` 变体。
`backend/scripts/gen` 下**无 slice 生成器** ⇒ slice 是手工冻结镜像，登记新文件须手改。

不自行处置的理由：①删 4 个内容唯一且未跟踪的文件 = 不可逆数据删除；②「带空格的 D4 收入底稿
是权威模板还是应排除」是审计域判断。**不**把判据的排除过滤器放宽到跳过 `.bak` —— 那会让真
污染以后静默进入运行时权威目录。
