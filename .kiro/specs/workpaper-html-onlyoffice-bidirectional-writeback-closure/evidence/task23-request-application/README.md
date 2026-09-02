# Task 23 证据：frozen request / content application 去重 / sequence 收敛

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 23
Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3
Properties: **P18 / P36 / P56 / P62 / P64**

## 〇、开工前的磁盘核查（交接要求逐条核过）

交接说「可能有被中断的残留，若有就审计+补完不要删」。**本次实况是确实没有**，
并且这个结论是三条独立判据得出的、不是「看了一眼没找到」：

1. 全仓 `*task23*` 递归搜索只命中另外两个 spec 的同号任务
   （`dsh_agent_panel/test_task23_address_*`、`procedure_trim/test_task23_zero_regr*`），
   与本 spec 无关；
2. `evidence/` 下没有 `task23-*` 目录（有 task4~task22 与 task73）；
3. **mtime 时序**：`backend/app/services/workpaper_sync/` 里最新的文件是
   `callback_delivery.py`（20:45:25），而 `tasks.md` 把 Task 23 翻成 `[-]` 是 20:58:55，
   Task 22 的 `mutation_report.json` 是 20:46:37。也就是说 20:41–20:45 那批
   `callback_*.py` 改动是 **Task 22 自己的收尾**，不是 Task 23 的残留。

另外核过一条交接没提但会误伤的事：`backend/data/amount_input_migration_status.json`
在 `git status` 里是 ` M`（已修改）。**不是本轮改的** —— 它的 mtime 是
**2026-08-23 22:21**，比本会话开工（2026-08-26 21:00）早三天，属并发会话的在途改动。
本轮全程未写该文件。

## 一、交付物

| 路径 | 作用 | git |
|---|---|---|
| `backend/app/services/workpaper_sync/request_application.py` | **新建**。frozen request 落库、application 去重、sequence 收敛、读路径固定四步、resolve 裁决的唯一组合点 | `??` |
| `backend/tests/workpaper_sync/test_task23_request_application_pg.py` | **真实 PostgreSQL** 行为守卫 **70** 例（含 Property 18 真并发） | `??` |
| `backend/tests/workpaper_sync/test_task23_request_application.py` | 离线守卫 **47** 例（裁决顺序矩阵 / 合成输入分支 / 结构判据） | `??` |
| `backend/scripts/diagnose/mutate_task23_request_application_guards.py` | **50** 条变异 | `??` |
| `mutation_report.json` | **50/50 RED**，零 GREEN / 零 ANCHOR-MISS / 零 WRONG-TEST | — |

基线：**117 passed**（70 真库 + 47 离线）。辐射面回归：**1231 passed / 0 failed**（3 分 33 秒）。

> 🔴 全部产物在 git 里是 `??` 未跟踪。**丢工作树即全部蒸发**，且挂进 CI 的 job 在干净
> checkout 下会因文件不存在而挂。同 Task 21/22 的处境，收口清单见 §九。

### 为什么需要新建一个模块（它不是又一层转发）

Task 21 给了 room 侧策略（`assert_can_initiate_request` / `build_request_freeze` /
canonical fence 推进），Task 10/22 给了仓储侧原子写（`create_forcesave_request_with_shell`
的复合幂等键、`correlate_durable_incoming` 的 primary/duplicate 收敛）。两侧都完整，
但开工时**没有任何生产代码把它们串起来** —— 全部调用点都是测试各自手工拼装
（实测：`create_forcesave_request_with_shell` 的 5 个调用点全在 `backend/tests/` 下）。

手工拼装的问题不是「重复」而是**顺序无法被证明**。AC 4.1 的措辞是「**先**在一个数据库
事务中持久化冻结…的 forcesave request，并创建 operation shell，**再**由后端调用
OnlyOffice Command Service」——「先/再」在散调用点里没有任何东西能保证。

## 二、Property 18：真并发结果（交接的核心欠账）

Task 22 显式把并发留给了本任务（其证据 §八.3）。串行循环 discharge 不了 P18：
串行下 `INSERT ... ON CONFLICT DO NOTHING` 的冲突分支与 `SELECT ... FOR UPDATE` 的
**等锁**分支根本不会被真正触发（第二次调用时第一次早已提交，`FOR UPDATE` 不阻塞，
也就无法证明「阻塞后再读能看到 winner」）。

本轮做了**两场**真并发，各用 `asyncio.Barrier` 让 N 个事务真正同时打开。

### 场景 A：全并发 create-or-hit（`RACE_N = 8`）

| 度量 | 实测 |
|---|---|
| 独立连接数（`pg_backend_pid()` 去重） | **8**（= RACE_N，逐个记录，不是推断） |
| 全部 racer commit 成功 | ✅ `racer_errors == []` |
| 真重叠证明 | `max(t_ready) <= min(t_call)` 且 `ready_count == 8` |
| application 行数 | **1**（key = `576dc7f0…12d8a`，与按 frozen 字段重算的期望值逐字节相等） |
| `created_application` 报 true 的 racer 数 | **1** |
| primary | **1**（`application_id` 非空、`duplicate_of` 为空） |
| duplicate | **7**，且**全部直指**同一 primary（`duplicates_all_direct = true`） |
| duplicate 自身 `application_id` | 全部为空 |
| stranded（本批 shell 里 app 与 dup 双空） | **0** |
| `state = 'waiting_application'` | **0** |
| 链（duplicate 目标自身是 duplicate） | **0** |
| 环（递归闭包 depth≤16 内回到自身） | **0** |
| `application_bound` event | **1** |
| `duplicate` event | **7** |
| `origin_request_sequence` | 9（∈ 本批 sequences `[2..9]`） |
| `effective_request_sequence` | **9 = max** |
| `superseded_by_application_id` | `NULL`（无 self-supersede） |
| room `latest_durable_application_id / latest_durable_sequence` | 指向该 application / **9** |

### 场景 B：并发 fold，origin **不是** max（7 条连接）

🔴 **场景 A 单独跑是不够的，本轮实测就踩了**：winner 由谁先拿到 room lock 决定，
那一轮恰好是 sequence 最高的（9）赢 ⇒ `effective == origin == max` 恒成立、
**fold event 数 = 0** ⇒ 「同 key 后续 request 原子 `GREATEST` 并与 room fence 同事务推进」
这条核心声明**一次都没被执行**，而断言照样全绿。判据靠调度运气通过 = 假绿。

因此加了场景 B：先**串行** correlate 最低 sequence 的 shell（把 origin 钉死成最低），
再让余下 7 个更高 sequence 的 shell 真并发涌入。

| 度量 | 实测 |
|---|---|
| 独立连接数 | **7** |
| racer 里 `created_application` | **0**（application 由 seed 建好） |
| seed sequence / max sequence | **10 / 17** |
| `origin_request_sequence` | **10**（= seed，**严格小于 max**） |
| `effective_request_sequence` | **17**（= max） |
| `sequence_folded` event 数 | **2**（≤ N−1；取决于到达序，故断言的是上界与形状） |
| fold event 的 `folded_request_id` | 互不相同 |
| fold event 的 `room_latest_durable_sequence` | 全部非空（AC 10.11「同事务」的可测投影） |
| fold event 的 `origin_request_sequence` | 恒为 `[10]`（append-only timeline 不改写 origin） |
| fold event 按 `sequence_no` 的 effective | 单调上升 |
| `superseded_by_application_id` | `NULL` |
| room fence | 指向该 application / **17** |
| primary / duplicate | **1 / 7** |

场景 A 里还加了一条**条件蕴含**补上运气缺口：`winner == max` 或 `fold_event_count >= 1`
—— 「该 fold 时没漏 fold」。

> 探针自身的一处缺陷也记下来：首轮用 `max(t_barrier) <= min(t_call)` 证明重叠，
> 实测**偶发红**。barrier 释放后各任务恢复顺序任意，A 记 `t_barrier` 完全可能晚于
> B 记 `t_call` —— 那条不等式并不成立。改成 `t_ready`（记在 `barrier.wait()` **之前**）
> 后它成了 barrier 语义的直接推论，连跑 4 次全绿。这类「探针缺陷」若不揪出来，
> CI 里会表现为随机红，然后被人加 retry 掩掉。

## 三、frozen 字段等值与 409 不返回旧标识（AC 4.1）

### 逐字段参与 fingerprint

`compute_frozen_request_fingerprint` 的 **11** 个入参逐个单独扰动，各得一个与 baseline
不同、且 11 个互不相同的 digest：
`client_confirmation_id / client_base_version_id / client_base_representation_id /
client_base_projection_sha256 / definition_bundle_sha256 /
authority_model_definition_sha256 / adapter_build_digest / contributor_snapshot_digest /
client_edit_epoch / write_fence_epoch / initiator_permission_epoch`。

逐字段一条测试而不是合成一条：合成写法只能证明**某个**字段参与，漏掉任一字段
（例如忘记拼 `write_fence_epoch`）不会被发现，而那恰好让「撤权后重放拿回旧 request」成立。
「11 个互不相同」另外排除「两个字段被拼在同一位置」这类实现错误。

### cache hit 与 409

| 场景 | 实测 |
|---|---|
| 全部冻结字段等值重放 | `cache_hit = True`，**同一** request id 与 operation id |
| 另一 participant 复用同 key | **409** `IdempotencyConflictError` |
| 另一 kind（`close_capture`）复用同 key | **409** |
| 同 slot 但 payload 不同（`client_edit_epoch`） | **409** |
| 同 slot 但 contributor 集合不同 | **409** |

四个 409 场景**逐一**断言：异常文本**不含**旧 request id、**不含**旧 operation id，
且 `operation` 行数增量 **0**（没有半途落库）。

逐场景参数化而不是合成一条的理由是可证伪的：把 fingerprint 比对删掉后
（变异 M33），`cross_participant` 依然被 same-slot 判据拒绝 —— 合成写法仍然绿。

> 跨 kind 那条**刻意绕过 room 资格门直接打仓储**：`assert_can_initiate_request` 会先
> 拒 `close_capture`（room policy 判据在前），走服务层时被测的幂等谓词一次都跑不到（假红）。
> 一个场景只违反一个谓词：保持 freeze 完全等值，只换 kind。

### 「不返回旧标识」是负向承诺，配了反例注入

变异 **M35** 把旧 request id 塞回 409 的异常文本（回插缺陷）。没有它，
`leaks_prior_request is False` 这个断言永远无法被证明有效 —— 实现本来就没泄露。

## 四、`application_key` 只在 application（P64）

* **schema 级**：`information_schema.columns` 里整个 scratch schema 只有
  `working_paper_content_application` 一张表有 `application_key` 列（不是 grep）；
* ORM：`WorkpaperSyncOperation` / `WorkpaperSyncOperationEvent` 的 `__table__.columns`
  都没有该列，`WorkpaperContentApplication` 有；
* 唯一性：`working_paper_content_application_application_key_key`；
* **签名判据**（Task 22 立的形态，本任务同样依赖，故再钉一次）：
  `compute_application_key` 的参数集恰为 9 项 frozen 字段，且与
  `{callback_status, status, request_id, request_sequence, origin_request_sequence,
  effective_request_sequence, room_last_applied_version_id, delivery_*}` 交集为空。
  **保持签名形态、未弱化成值比较** —— 后者只证明当前实现没用它们，前者让「想把 status
  塞进 key」必须先改签名（会被打红）。
* 服务层一半：`request_application.py` 剥掉注释与字符串后**不含** `application_key`
  字面量（配反向自检，见 §六）。

## 五、sequence fold / supersede：13 条规则逐条归因到执法点

判据形态固定：被拒 **且** 拒它的正是声明的那个执法点 **且** `source != 'probe_defect'`。
每一行都构造成**只违反自己那一条**。

执法点分两类，判据形态不同 —— 这个区分是必需的，不是分类癖：

* `constraint`（行级 CHECK / UNIQUE）—— asyncpg 给 `constraint_name`，直接归因；
* `trigger`（plpgsql `RAISE EXCEPTION ... USING ERRCODE='check_violation'`）——
  **不带** constraint 名、报文也常不含函数名 ⇒ 只按名字归因必然判「没归因到」。
  这类的依据是该 RAISE 在 V151 里的**唯一报文片段**，并**额外要求 `mentions` 为空**
  （证明没有行级 CHECK 抢先遮蔽它）。

| 规则 | 执法点 | kind | 实测归因 |
|---|---|---|---|
| `origin_sequence_immutable` | `wpsync_check_application_identity` | trigger | `trigger_raise`，片段「必须等于 origin request 的 request_sequence」 |
| `application_key_immutable` | `wpsync_check_application_mutation` | trigger | `trigger_raise`，片段「identity 列」 |
| `effective_sequence_monotonic` | `wpsync_check_application_mutation` | trigger | `trigger_raise`，片段「只可单调提升」 |
| `effective_below_origin` | `ck_wpca_effective_ge_origin` | constraint | ✅ 同名 |
| `self_supersede` | `ck_wpca_no_self_supersede` | constraint | ✅ 同名 |
| `second_primary_for_application` | `uq_wpso_application` | constraint | ✅ 同名 |
| `duplicate_pointer_removed` | `wpsync_check_operation_binding_immutable` | trigger | `trigger_raise`，片段「duplicate 指针不可变」 |
| `primary_rebound` | `wpsync_check_operation_binding_immutable` | trigger | `trigger_raise`，片段「禁止改绑/解绑」 |
| `duplicate_chain` | `wpsync_check_operation_duplicate_link` | trigger | `trigger_raise`，片段「不是 direct primary」 |
| `stranded_duplicate_state` | `ck_wpso_duplicate_shape` | constraint | ✅ 同名 |
| `fold_event_twice_same_request` | `uq_wpcae_fold_once` | constraint | ✅ 同名 |
| `fold_event_without_room_fence` | `ck_wpcae_fold_requires_room_fence` | constraint | ✅ 同名 |
| `duplicate_application_key` | `…_application_key_key` | constraint | ✅ 同名 |
| `second_application_bound_event` | `uq_wpsoe_application_bound_once` | constraint | ✅ 同名 |

另有服务层第二道：`supersede_application(old=X, new=X)` ⇒ `SupersedeError`，文本含
「self-supersede」。

### 首轮 4 条归因是错的，逐条根因

这四条不是「测试写歪了」，而是**遮蔽关系**，写错归因会让下一个人以为自己声明的约束还活着：

| 规则 | 首轮 | 根因 | 处置 |
|---|---|---|---|
| `origin_sequence_immutable` | 归到 mutation trigger，片段不匹配 | 同 timing 的 trigger 按名字排序触发：`trg_wpca_identity` < `trg_wpca_mutation`，前者把 origin 与 origin request 行**跨行**比对 ⇒ 它先抛 | 归因改到 identity trigger（它给的保证更强）；mutation trigger 的 identity-列 分支另找一个 identity trigger 不交叉校验的列（`application_key`）单独证明 ⇒ 拆成两条规则 |
| `effective_below_origin` | 归到 CHECK，实得 trigger | UPDATE 路径上任何把 effective 降到 origin 以下的写法**同时**是一次「effective 下降」⇒ BEFORE UPDATE 的 mutation trigger 先抛，CHECK 被完全遮蔽 | 探针改走 **INSERT**（BEFORE INSERT 的 identity trigger 不看 effective）⇒ 这一行只违反该 CHECK |
| `second_primary_for_application` | 归到 UNIQUE，实得 trigger | 把既有 duplicate 改绑成 primary 的 UPDATE 会先撞 `binding_immutable`（duplicate 指针不可变） | 改成 **INSERT** 一行 shape 合法的 primary（dup=NULL、state=application_bound、bound_at 非空、scope 全同） |
| `duplicate_chain` | 归到 `ck_wpso_duplicate_shape` | 把 primary 改成指向 duplicate 时，primary 的 `application_id` 非空 ⇒ duplicate 分支不成立 ⇒ 行级 CHECK 抢先挡住，被测 DEFERRED trigger 一次都没跑到（WRONG-TEST） | 改成 **INSERT** 一行「行级 CHECK 全合法、只是目标是 duplicate」的行 |

### 两条被结构性遮蔽的约束：承认而不是编归因

`ck_wpso_not_both_owners`（app 与 duplicate 指针互斥）在默认 schema 里**永远无法单独触发**。
真值表论证：它被违反需要 `app IS NOT NULL AND dup IS NOT NULL`，而此时
`ck_wpso_duplicate_shape` 的两个 disjunct
（`dup IS NULL AND state<>'duplicate'` / `dup IS NOT NULL AND state='duplicate' AND app IS NULL`）
同时失败 ⇒ 二者必然一起被违反。

处置不是编个归因，而是**在事务里临时 DROP 遮蔽者**（PG 的 DDL 是事务性的，ROLLBACK 后
schema 原样），再看剩下那条是否真的接管：实测**被 `ck_wpso_not_both_owners` 拒**，
且 ROLLBACK 后 `ck_wpso_duplicate_shape` 仍在（`pg_constraint` 计数 = 1，证明探针没污染 schema）。
这既承认了遮蔽关系，又证明纵深防御不是死代码。变异 **M40** 削掉它必须翻成 accepted ⇒ 实测 RED。

同一手法也用在服务层：`canonicalize_authorized` 里「application 必须被**恰好 1** 个
operation 绑定」这条分支被 `uq_wpso_application` 遮蔽成**不可达**。事务内 DROP 唯一约束、
造出双绑、再读 ⇒ 服务层真的拒（`CanonicalBindingError`），ROLLBACK 后约束计数 = 1。
没有这个探针，变异 M26 必判 GREEN——「不可达分支已被守卫锁住」只是自述。

## 六、读路径固定四步与 authorization-first（AC 5.5 末段 / 8.5 / 10.5）

阶段序做成**返回值的一部分**（`CanonicalRead.stages`），顺序本身才成为可断言的事实：

* primary 读：`requested_scope_resolved → requested_action_authorized →
  requested_operation_loaded → canonicalized → canonical_application_bound`；
* duplicate 读：中间多一步 `direct_primary_verified`，且断言其**下标小于** `canonicalized`；
* duplicate 读实测：`requested_operation.application_id` 为 **NULL**（这是**正确**形态），
  `canonical_application_id` 非空、canonical 是 primary、`effective_request_sequence` 可读
  ⇒ **从不要求 requested duplicate 自身绑定 application**；
* duplicate 读前后 operation / application 行数增量都是 **0** ⇒ 不新建。

### 「authorization-first」用三种互补形态锁住

单一形态都不够，三者缺一都能被绕：

1. **类型强制**：`canonicalize_authorized` 只接受 `AuthorizedOperationRef`，而后者只能由
   `authorize_operation_scope` 产出；裸对象与「只完成 scope 解析、缺 authorized 阶段」的
   ref 都被拒（`ScopeAuthorizationDeniedError`）。
2. **行为判据**：给一个**只在 scope index 登记、没有 operation 行**的 ghost id ——
   `authorize` 拒 ⇒ **403**；`authorize` 放行 ⇒ 才轮到 **404**。若实现先加载业务行，
   第一种情形只会得到 404。两态一起断言（只测第一条时「两种都返 403」也能过，而那意味着
   404 语义丢失）。
3. **源码形态**：`assert_authorization_first_source_shape()` AST 反查授权阶段，
   实测对 `self._repo/_rooms/_session` 的调用集合恰为 `('resolve_scope',)`，
   且不出现任何业务表 ORM 符号。运行期观察只能证明「这次没多读」；
   把 `lock_room` 加回去后行为结果一样，只有源码判据会红（变异 **M28** 正是回插这个形态）。

403（`scope_authorization_denied`）与 404（`operation_scope_not_found`）**互不为子类** ——
否则 `pytest.raises` 会被继承关系放过（Task 22 的 M04/M10 教训）。
跨 project scope、跨 entry scope、未知 id **共用同一 404 语义**，避免用错误类型泄露「该 id 存在」。

### AC 4.1 的「先落库、再调 Command Service」

本模块能给到的最强判据是三条结构判据的组合：

1. **import 图**：本模块不引入任何 HTTP 客户端 / Command Service 符号
   （`httpx / aiohttp / requests / urllib / CommandService / command_service /
   forcesave_command / sign_command_jwt`）⇒ 它自己发不出请求，「先落库」无法被一次内联调用绕过；
2. **不 commit**：AST 扫全模块无 `commit()` / `rollback()` 调用 ⇒ 事务边界属 coordinator，
   「request + shell 同一事务」才成立；
3. **四步调用顺序**：`assert_can_initiate_request → build_request_freeze →
   create_forcesave_request_with_shell → assert_dispatchable`，按源码行序断言。
   这条覆盖两种在 happy path 上**零行为差异**的失效：把授权挪到落库之后（变异 M19），
   以及把落库后的自证调用整条删掉（变异 M18）。

`AcceptedRequest` 凭据带三条自证，其中「零 application」是**真查了一次库**
（`count(application where origin_request_id = req.id)`），不是「我没建所以肯定是 0」——
二者在并发下不等价。

> 剥注释的辅助函数配了**反向自检**（`test_strip_helper_actually_removes_comments_and_strings`）：
> 若它退化成 `return ""`，「服务层不含 application_key 字面量」这条断言恒真而无判据会红。
> 同理 `_call_order` 配了 `test_call_order_helper_detects_a_swap`。

## 七、其余 Property 的本任务份额

* **P56（重复 callback 零多版本）**：同 frozen identity 下三次 correlation
  （status 6 / status 2 / 重试）⇒ application 行数增量 **1**，
  shapes `['primary','duplicate','duplicate']`，该 incoming 的 primary 数 **1**。
  > 这个场景首轮**测错了对象**：复用了 race 阶段那份已提交的 incoming，于是三次全部命中
  > race 建好的 application ⇒ 增量 0、shapes 全 duplicate。那实际测的是「跨阶段去重」，
  > 与 P56 想证明的事不是同一件 —— 判据被上一阶段的残留状态遮蔽。改用本阶段自己的 incoming。
* **P62 / AC 2.9 / 4.11**：room 进 `refresh_required` 后，下一次
  `freeze_and_persist_request` 被 `RoomNotWritableError` 拒，文本含「refresh」，
  且 operation 行数增量 **0**。「在 Command Service **之前**被拒」的可测形态就是这个 0：
  既没落 request 也没落 shell，因此不可能已经发过 Command Service 调用（后者以凭据为前提）。
* **recovery（AC 4.10 / 5.8 / 14.3）**：claim **前** request/application/operation
  三者全空、case `unclaimed`；claim 后 shell 是 **primary**、`kind='recovery_claim'`、
  `case.application_id == application.id`、`application.incoming == case.incoming`。
  `retry_eligibility` 两态各自断言：claim 前 `False`、claim 后 `True`
  （只断言前者时「恒返回 False」也通过，而那会让 primary retry 也进不去）。

## 八、变异检验：50/50 RED

`mutate_task23_request_application_guards.py --run all` ⇒
**50 RED / 0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST**，`restored=True` 全条，
事后 `--check-anchors` 50/50 OK、目标文件 md5 未变、无 `.mutbak` 残留。

五类落点：
① 裁决顺序（M01~M09，含把 identity 比较短路的「顺序调换」）；
② 纯判定函数的合成输入分支（M10~M17）；
③ **接线顺序 AST 判据**（M18/M19）—— happy path 上零行为差异，只有源码判据能看见；
④ 读路径与 authorization-first（M20~M29、M50，含回插禁止形态的 M28）；
⑤ 仓储收敛/幂等（M30~M35，含负向承诺反例注入 M35）+ **V151 逐条削**（M36~M49）。

### 首轮 10 WRONG-TEST + 1 GREEN 的逐条归因与处置

| 条目 | 首轮 | 归因 | 处置 |
|---|---|---|---|
| M04/M05/M06、M10、M12~M17（10 条） | WRONG-TEST | **脚本+守卫缺陷**：`parametrize` 没给 `ids=`，pytest 按**全部**参数拼 id（dict 参数变成 `over0`），实得 `[generation-over0-room_generation]` ⇒ `want=[generation]` 定位不到 | 四处 `parametrize` 显式给 `ids=`。参数化 nodeid 一旦被变异脚本引用，它就是接口的一部分 |
| M25 | GREEN | **守卫缺陷（两条拒绝共用一个类型）**：`app_id is None` 时若不拒，紧接着的 `count(... application_id == app_id)` 被 SQLAlchemy 渲染成 `IS NULL` ⇒ 统计到全部 pre-correlation shell ⇒ `bound != 1` 抛**同一个** `CanonicalBindingError` ⇒ 第一条永久不可达 | 拆出 `CanonicalPrimaryUnboundError`，并断言二者**互不为子类**（Task 22 M04/M10 的同一形态，本 spec 第三次遇到） |
| 基线 | 1 failed（ABORT） | **探针缺陷**：`max(t_barrier) <= min(t_call)` 偶发不成立（见 §二末段） | 改用 `t_ready` + `ready_count` |

三条都**不是生产缺陷**。变异检验在这里的作用正是把「守卫看起来全绿」与「守卫真的有效」
分开：117 例全绿的同时，有 11 条判据是无效的。

## 九、辐射面回归：按引用关系反查，不跑全量

全量 `backend/tests` 有 1522 个测试文件，前台跑数分钟无输出会被当卡死。改用引用关系反查：
扫全部 `test_*.py` 对本轮改动物（新模块、`correlate_durable_incoming`、
`create_forcesave_request_with_shell`、`advance_room_durable_fence`、
`fold_effective_sequence`、`compute_application_key`、`resolve_canonical_operation`、
`assert_direct_primary`、V151 与其约束名前缀等）的实际引用（命中 18 个文件），
并入交接指定的 Task 12/15/16/18/19/20/21/22 文件 ⇒ **24 个文件**。

结果 **1231 passed / 0 failed（3 分 33 秒）**。

交接提到的 5 条既存 `public_router` 404（`test_onlyoffice_word_template_callback.py`）
**不在本轮辐射面内**（Task 22 证据已记：那是反查脚本把测试函数名
`test_callback_download_failure_returns_error_1` 里的 `callback_download` 当成模块引用的
**假阳性**，该文件与同步域零耦合）。仍单独跑过确认状态未变，**双证**：

1. **行为**：单跑该文件 = `5 failed`，形态一律 `assert 404 == 200`；
2. **取证**：`git status --porcelain` 对该测试文件与 `wp_onlyoffice_router.py` 都是**空**
   （worktree 未改动），且 `git show HEAD:` 取出的测试文件只有 4 处
   `include_router(router)`、**零**处 `public_router` ⇒ HEAD 上同样 404。

## 十、没能验证的部分 / 收口欠账

1. **无生产消费方（结构性，非遗漏）**。`request_application.py` 目前只有守卫在 import，
   没有任何 router 调用它。这不是「additive 注入即死代码」的假绿，而是 spec 的分工：
   Task 23 交付的是**领域层**，HTTP 面属 **Task 28**（`- [ ] 28. 建完整显式 scope sync
   router…`），Command Service 调用属 **Task 24**。本任务能给的是**委派缝的结构判据**
   （§六 的三条：无 HTTP 依赖、不 commit、四步顺序）。
   🔴 **在 Task 24/28 接线之前，不得声称 OO→HTML 回写在生产上可用。**
2. **close-capture 仲裁未实现**（属 Task 24，交接已明确划界）。本任务只在
   `assert_can_initiate_request` 层面确认 `kind=close_capture` 不得由客户端发起。
3. **未起真实 OO 9.4 做两用户实测**。本轮全部 correlation 的 incoming 都是构造字节
   （走真 sealing 路径、真约束，但不是真 OO 投递）。「真实 OO 的 forcesave 回调能被这条
   链路正确归组」的终局证据只有 Task 44/70 的真实 OO gate 能给。
4. **`_assert_convergence` 与 `assert_recovery_claim_shape` 的分支在真库 happy path 上
   触发不到**，其判据全部是**合成输入**（离线守卫 §二之二）。这是有意的形态选择
   （「绝不写断言真实数据仍有缺陷的守卫」），但要说清：真库那份只证明 happy path
   走通，分支有效性由合成输入 + 变异 M12~M17 证明。
5. **`fold_event_count` 是到达序相关量**，因此断言的是上界与形状（≤ N−1、
   `folded_request_id` 互不相同、room fence 全非空），不是一个确定数字。
   确定性那一半由场景 B 的 `>= 1` 承担。
6. **产物全部 `??` 未跟踪**，须尽快入库：
   `backend/app/services/workpaper_sync/request_application.py`、
   `backend/tests/workpaper_sync/test_task23_request_application.py`、
   `backend/tests/workpaper_sync/test_task23_request_application_pg.py`、
   `backend/scripts/diagnose/mutate_task23_request_application_guards.py`、
   本证据目录。**未入库前不要把对应 job 挂进 CI**（干净 checkout 下必挂）。
