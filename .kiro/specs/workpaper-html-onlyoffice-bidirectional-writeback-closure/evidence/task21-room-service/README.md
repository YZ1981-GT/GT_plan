# Task 21 证据：shared room / participant lease / frozen bundle 双基线 / generation write fence

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 21
Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10
Properties: **P6 / P15 / P43 / P44 / P62 / P63**

## 一、交付物

| 路径 | 作用 | git |
|---|---|---|
| `backend/app/services/onlyoffice_room_identity.py` | **生产接线 seam**（本轮新增）：两个 `onlyoffice-config` 端点的 doc_key 唯一来源、entry_id 派生、route credential 读取、`RoomService` 构造点 | `??` |
| `backend/app/routers/wp_onlyoffice_router.py`（增量） | 删除 `_generate_doc_key`（`md5(wp_code + st_mtime_ns)`），改调 seam | `M` |
| `backend/app/routers/wp_editor_router.py`（增量） | Word 端点 `document_key` 改调 seam（不再用 `file_version` / `prefilled`） | `M` |
| `backend/app/services/workpaper_sync/rooms.py` | room 策略层：doc_key 派生、九条资格判据、冻结身份、双基线、撤销旋转、**新增** representation 准入三门 / route credential / contributor 三分 / canonical fence + same-app fold | `??` |
| `backend/app/services/workpaper_sync/models.py`（增量） | **新增** `ContributorSource` / `ContributorConfidence` 两个封闭域（与 V151 CHECK 双向锁死） | `??` |
| `backend/app/services/workpaper_sync/repository.py`（增量） | `_advance_room_durable_fence` → 公开 `advance_room_durable_fence`，供服务层**委派**而不是各写一份 room 侧算术 | `??` |
| `backend/tests/workpaper_sync/test_task21_room_service.py` | 离线守卫 **98** 例 | `??` |
| `backend/tests/workpaper_sync/test_task21_room_service_pg.py` | 真实 PostgreSQL 行为守卫 **56** 例 | `??` |
| `backend/tests/test_onlyoffice_single_file_dockey.py`（改） | 旧 mtime characterization 迁到 room 身份语义（断言方向反转） | `M` |
| `backend/tests/test_wp_onlyoffice_router.py`（改） | 同上 + config 端点 mock 容纳新增的 room 查询 | `M` |
| `backend/scripts/diagnose/mutate_task21_room_service_guards.py` | **67** 条变异 | `??` |
| `mutation_report.json` | 变异结果：**67/67 RED**，零 GREEN / 零 ANCHOR-MISS / 零 WRONG-TEST | — |

基线：**154 passed**（98 + 56）。

> 🔴 `??` = 未跟踪。`backend/app/services/workpaper_sync/`、`backend/tests/workpaper_sync/` 整目录
> 与本 spec 的 `.kiro/specs/...` 目录在 git 里全是未跟踪状态，丢工作树即全部蒸发。

## 二、doc_key 身份：before / after，以及 mtime 是怎么被证明消失的

| | before | after |
|---|---|---|
| `/api/workpapers/*/sheets/*/onlyoffice-config` | `_generate_doc_key(file_path, wp_code)` = `md5(wp_code + st_mtime_ns)`，**mtime 耦合**（Task 73 行为探针实测：touch 文件 ⇒ key 变） | `resolve_room_doc_key(db, wp_id, entry_id)` ⇒ `wpsync-<24hex>-g<generation>` |
| `/api/projects/*/working-papers/*/onlyoffice-config` | `f"wp-{wp_id}-{wp.file_version}-{'pf'|'raw'}"`（无 mtime，但用 `file_version` 与展示态） | 同上（`word_template_entry_id`） |
| `_generate_doc_key` | 存在 | **已删除，不留 fallback**（design §`wp_onlyoffice_router`） |

「mtime 已消失」用**三条形态不同**的判据证明，缺一条都不够：

1. **真执行（seam 侧）** —— `test_seam_doc_key_is_behaviourally_immune_to_mtime`：建真实文件、
   走 `sheet_entry_id` → `derive_doc_key` 的**生产同一条链路**、`os.utime` 真把 mtime 改掉、
   先断言 `mtime_after != mtime_before`（否则这条根本没验证任何东西），再断言 key 逐字节相等。
2. **真执行（派生层）** —— `probe_room_facts()` 同样真改 mtime，另加 AST 传递闭包
   （`_doc_key_source_is_mtime_free`，禁 `st_mtime*/getmtime/stat(`）。**不用 grep**：本模块
   docstring 里就写着 `st_mtime_ns`，grep 会恒假。
3. **生产表达式实扫** —— `test_production_routers_no_longer_derive_doc_key_from_mtime` 复用
   `entry_source_facts._doc_key_expression()`（生产提取器，不在测试里抄正则）逐路由取
   **doc_key 赋值表达式**，要求 `includes_mtime is False`。判据落在表达式而不是整文件搜
   `st_mtime`：路由里仍有正当的 mtime 使用（sheet 可见性幂等短路），整文件搜会把它判红，
   接着人就会去放宽判据。

反向可 falsify：M43 把 sheet 端点的 doc_key 换回 `f"{wp_code}:{st_mtime_ns}"` ⇒ 第 3 条与
RG-17 在**真实 manifest** 上同时打红。M01 往派生链路注入一次 mtime 读取 ⇒ 第 1、2 条打红。

### 存量行为的一处刻意改变

旧实现里「切换 sheet 会重新下载」是靠 mtime 变化**偶然**实现的（旧 key 里没有 sheet 成分，
docstring 明写「同 wp_code 所有 sheet 共享同一 key」）。新实现把 sheet 名与「完整 Excel」
视图算进 `entry_id`，所以切换视图**仍然**换 key、仍会重新下载；变的只是「同一视图反复打开
不再无谓轮转」。这也顺手修掉一个旧行为缺陷：整册视图与单 sheet 视图曾共享 key，OO 会把缓存的
单 sheet 副本（其余 sheet 已被 openpyxl 隐藏）当成「完整 Excel」返回。

`_hide_non_target_sheets()` 就地改写共享 artifact 本身违反 Requirement 9.12，**本任务不动它**
（属 Task 25/26 的 staged artifact 范围）；下载、callback、`file_version`、席位限流也一律未动。

## 三、Task 73 留下的 RG-17 红：已清零（实测）

| | 接线前 | 接线后 |
|---|---|---|
| `room_service_wiring()` | `()`（零调用点） | 11 处，全在 `onlyoffice_room_identity.py` |
| 独立可达 entry | 142 | 142 |
| RG-17 红（mtime / lease） | **141 + 1 = 142** | **0** |
| `build_report().profile_drift` | 142 | 132 |

剩下的 132 条**与 room 事实无关**，逐条分桶实测：RG-16（descriptor mode ↔ capability）**127**、
RG-15（capability ↔ room_model）**5**。为证明它们不是本次接线引入的，用「把
`room_service_wiring()` 换空」的模拟对照跑了一次：桶分布为 `127 RG-16 + 10 RG-17/lease + 5 RG-15`
—— RG-16/RG-15 两桶前后完全一致。Task 73 的 tasks 正文写「须缩到只剩 RG-15 层」，实测是
**RG-15 + RG-16 两层**；RG-16 属 descriptor 观察（Task 31/33）与 capability 复核，不在 Task 21 范围。

判据落地为两条配对守卫：`test_rg17_is_clear_on_the_real_manifest`（逐 entry 跑
`assert_profile_consistent_with_room`，且断言 `checked >= 100` 防 vacuous truth，
**只**统计 RG-17 —— 把 RG-15/16 一起断言成 0 会让它永远红，接着人就会删掉整条判据）
与 `test_rg17_still_reds_when_wiring_disappears`（换空接线判据后必须打红）。

## 四、manifest 需要重生成 —— 未执行，digest delta 如下

接线让 `room_service_wiring()` 非空 ⇒ 派生的 `scenario_profile.room_service_state` 从
`pending_room_service` 翻成 `room_service_wired` ⇒ 磁盘 manifest 立刻 stale。生成器
`--check` 如实 fail closed：

```
[FAIL] entry xlsx/cash-flow-verification (GtOnlyOfficeSheet): source facts derive
scenario_profile_ids='xlsx.editable.shared.single.room_service_wired.v1', which is not in
the reviewed set ['xlsx.editable.shared.single.pending_room_service.v1']
```

按交接约定**没有**改 `entry_source_facts.py` / `generate_workpaper_sync_manifest.py` /
`workpaper_sync_entry_manifest.json` / `workpaper_sync_entry_overlay.json`。digest delta 由
**仅在内存中**改写 overlay reviewed set 后调用 `build_manifest()` 算出：

| 字段 | on disk | 接线后 |
|---|---|---|
| `manifest_digest` | `67109bb81d4652e1cd32c28d2e5cf7eb4173b82504e4302a52fb4a3680c66a12` | `8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28` |
| `profile_source_digest` | `a75b8aa37c0e81c6e7b8180da76a4208123a8dfe98c6235a68c4247e3df6d18d` | `13961b0c8494be5d979d9c5a110c66a70a5da87c9005fa60d0311b9628ece766` |
| `overlay_digest` | `b5c6781cccf95794c18812c87b4b8ae0f1debc6104e0fa6a3ce409920a23d999` | `60ff3be93ddea90b65f5d029ad3a938d9fd86d3a0a9f517387b46feef4811fc8`（仅因内存改了 reviewed set） |
| `stats.room_service_state` | `pending_room_service` | `room_service_wired` |
| 变化的 entry | — | **186 / 186**（每条的 `scenario_profile.profile_id` + `room_service_state`，以及 `profile_source.source_refs` 里 doc_key provider 的行号） |

**待办（不属 Task 21 的验收范围）**：由 overlay 复核方把 6 条 reviewed
`scenario_profile_ids` 从 `.pending_room_service.` 改成 `.room_service_wired.`，再跑
`--apply`。在那之前 `test_task73_entry_profile_manifest.py` 有 8 条红，其中
`test_room_service_is_still_unwired_and_reported_as_such` 的**前提已被本任务推翻**
（它断言接线为空），需与 manifest 一同更新。这就是 design 的 stale policy 在工作，不是回归。

## 五、lease / fence 语义与各自的真实 DB 约束

| 语义 | 服务层落点 | 由哪条真实 DB 约束兜底 |
|---|---|---|
| 逐用户 lease（mode/epoch/TTL/revoke） | `join_participant` + `_assert_participant_lease_live` | `uq_wpoop_active_lease (room_id, user_id) WHERE 未终结`（partial unique）、`ck_wpoop_epochs (joined_write_fence_epoch >= 1)` |
| lease token 只存 hash | `join_participant`（明文只出现一次） | `working_paper_oo_participant.lease_token_hash CHAR(64)` |
| 一个 generation 一个 room | `open_or_reuse_room`「开或复用」 | `uq_wpoor_doc_key UNIQUE (doc_key)` + `uq_wpoor_generation UNIQUE (wp_id, entry_id, generation)` |
| room 身份不可变 | — | `wpsync_check_room_immutable`（`generation`/`doc_key`/`wp_id`/`entry_id`/`opened_base_version_id`） |
| write fence 提升 + 取消 outstanding 同事务 | `revoke_participant`（`lock_room` 内） | `ROOM_EDGES` 状态机 + `working_paper_forcesave_request` 冻结字段 immutable trigger |
| 双基线不混同 | `advance_server_last_applied` / `settle_client_baseline` 两个方法 | room 上 `last_applied_version_id` 与 `client_confirmed_*` 是**两组独立列** |
| canonical fence 与 server 指针同事务 | `advance_server_last_applied`（`application_id` 必填）→ 委派 `repo.advance_room_durable_fence` | `working_paper_oo_room.latest_durable_application_id` FK + `latest_durable_sequence` |
| same-app 只 fold 不 self-supersede | `fold_same_application_request` + `models.fold_effective_sequence` / `assert_supersede` | `wpsync_check_application_immutable`（`origin_request_sequence` 不可变）、`application_key UNIQUE` |
| route credential 绑 room/generation/doc_key | `mint_route_credential`（uuid5，确定性可重算） | `working_paper_callback_delivery.route_credential_id NOT NULL` |
| initiator / route / contributor 三处分离 | `record_contributor_snapshot` | 三张表：`working_paper_forcesave_request.initiated_by_participant_id` / `working_paper_callback_delivery.route_credential_id` / `working_paper_sync_operation_contributor`（`ck_wpsoc_source` + `ck_wpsoc_confidence`） |
| published representation 才能进 room | `assert_representation_admissible` ①② | `working_paper_sync_entry_state.current_representation_id`、`working_paper_representation_upgrade_candidate` |
| bundle alias 不漂移 | `assert_representation_admissible` ③ | `trg_wpcr_identity`（INSERT 时双向锁死）+ `trg_wpcr_immutable`（整行 immutable） |

### 撤销裁决不是本模块的选择

`revocation_policy()` 从 Task 4 契约读 `multi_user_semantics.revocation.decision`
= `write_fence_plus_generation_rotation`。`evidence/task4-oo94-multiuser-callback/findings.md` §4
实证：`c=drop` 之后 `c=info` 里该用户消失、其后续输入写不进，但**它 drop 前写的 `Z92` 仍出现在
此后每一次 forcesave 与最终 status 2 的 artifact 里**，`history.changes` 也仍列出它。所以
「有 drop 证据就可以留在原 generation」这个分支在 OO 9.4 上**永不成立** ——
`oo_drop_confirmed` 只决定要不要多记一个取证时间戳，不放宽 fence。只读（view）撤销不污染内容，
故不旋转 generation（M23 检验这一条不被过度反应吃掉）。

## 六、本轮修掉的三个真实缺陷

1. **`build_request_freeze` 从 immutable 的 confirmation 行取 base**（原实现）。
   `settle_client_baseline` 在 merged==incoming 时把 client 快照推进到**已应用**版本，
   而 confirmation 行永远停在打开时那一版 ⇒ 第二次 forcesave 的三方 merge 仍以「打开时那一版」
   为 base，第一次已合并进去的改动会被当成本次新改动**再合一遍**；若第一次做过冲突裁决，
   裁决结果会被这次重放覆盖。AC 4.11 的原文正是「后续 request 从**该确认快照**冻结 bundle/base」。
   现改为读 room 的 client-confirmed 快照，M66/M67 双向可 falsify。
2. **`advance_server_last_applied` 不带 application、不推 canonical fence**（原实现只写
   `last_applied_version_id`）。AC 10.11 要求 same-application fold 与 room latest-durable
   application/sequence 在**同一 room lock 事务**内原子决定；拆开会出现「server 已推进、
   canonical fence 还指着上一个 application」的中间态，而 Task 27 的 resolve 先比 canonical
   application identity 再比 effective sequence，读到那个中间态会把一次合法 resolve 判成 stale。
   `application_id` 因此是**必填**参数 —— 可选就意味着调用方可以只推一半。
3. **candidate / 未发布代际可以进 active room**（原实现只校验 `entry_id` 与 `generation >= 1`）。
   AC 2.5 写的是 published representation，不是「任何一行 representation」。

## 七、变异检验：67/67 RED，两条 GREEN/MISS 的逐条归因

第一轮 67 条：**65 RED / 2 GREEN**。两条都归因到**非守卫**原因，处置如下。

### M44：无效变异（脚本缺陷）

原写法是「在 router 的 import 行后加一个别名赋值」。它**一个字节都没动直接调用点**，
AST 判据当然照旧命中 ⇒ GREEN 与守卫无关。落点改成**调用本身**（换成本地拼 key）后 RED。

顺带确认了 M43/M44 的分工不重叠：M43 换成含 mtime 的 key（只有 mtime 判据敏感），
M44 换成不含 mtime 的本地 key（只有接线判据敏感）。

### M64：生产代码缺陷 —— 一段 provably 不可达的检查

原 M64 是「删掉 `_load_application` 里的 `app.generation == room.generation` 检查」，判 GREEN。
逐条归因后结论是那道检查**永不可达**：V151 把三样都锁成 immutable —— room 的 `generation`
（`wpsync_check_room_immutable`）、application 的 `room_id` 与 `generation`
（`wpsync_check_application_immutable`），而 application 的 generation 是
`correlate_durable_incoming` 在 room row lock 内从 `req.generation`（= 该 room 当时的
generation）复制来的。三条合起来 ⇒ `app.room_id == room.id` 成立时 generation 必然相等。

留着它比删掉更糟：它让「删掉它」永远判 GREEN，下一个人会以为守卫有缺陷而去放宽判据。
处置 = **删掉死代码**，并把依据正面钉成
`test_application_room_and_generation_are_db_immutable`（三条 UPDATE 都必须被 DB 拒绝）——
DB 哪天解锁任一条，那条守卫打红，检查就必须补回来。M64 落点改为「不存在的 application 静默通过」。

第二轮：**67/67 RED**，`restored=True` 全条，目标文件 md5 复核未变、无 `.mutbak` 残留。

## 八、alias 漂移的执法点在数据库，服务层是纵深防御

采集时实测到一件重要的事：`working_paper_content_representation` 有
`trg_wpcr_immutable`（**整行 immutable**，任何 UPDATE 直接 RAISE）与 `trg_wpcr_identity`
（INSERT 时把 `definition_bundle_sha256` / authority 与 bundle 双向锁死）。所以
「改一行 representation 的 bundle digest」在库里**根本做不到** —— 首版把这个当成服务层判据的
场景，实测拿到的是 DB 的 CheckViolation 而不是服务层拒绝。

处置分两条，各有独立断言：

* `test_database_itself_refuses_representation_row_drift` —— 钉住**主要**执法点在 DB。
  不钉住它，下面那条会被当成唯一防线，将来有人删掉 trigger 时没有任何测试会红。
* `test_only_published_non_candidate_drift_free_representation_enters_room[alias_drift|authority_drift]`
  —— 服务层判据的**可达路径**：`open_or_reuse_room` 收到的是调用方给的 representation
  **对象**（coordinator 可能持有一份 detached/陈旧副本），不是一个 id。把对象 `expunge` 后改掉
  冻结 digest 再传进来，精确复现「拿着 bundle 身份已漂移的 representation 来开 room」。
  不 expunge 会触发 autoflush ⇒ 撞上面那条 immutable trigger，测出来的就变成 DB 异常而不是
  服务层判据（判据被遮蔽）。

## 九、去遮蔽：本轮新增的三个「只让一条判据生效」场景

| 场景 | 只让哪条生效 | 不这样写会被谁遮蔽 |
|---|---|---|
| `cross_room_error` 用**同 generation** 的另一个 room | `app.room_id != room.id` | 用 room2（generation 2）时 generation 判据同时命中；且若 fence 阶段 rollback，两个场景会双双落到「application 不存在」——首轮实测诊断文本就是它 |
| `reopen_superseded_generation`（supersede 后、**发布新代际之前**） | room-state 的 `uq_wpoor_generation` 诊断 | 等 g2 发布后再试，准入门的「不再是 published 代际」会先命中并整条遮蔽 |
| `reopen_after_new_generation`（配对场景） | 准入门 | 只留上一条时，改动两道门的先后会静默改变用户看到的诊断而无人发现 |

## 十、Word 端点缺陷（`frontend_endpoint_without_backend_route`）：判定为**不在** Task 21 范围

Task 73 记录的实况：`WorkpaperWordEditor.vue#L995` 请求
`/api/workpapers/{wpId}/onlyoffice-config`，后端**没有这条路由**（只有
`/api/projects/*/working-papers/*/onlyoffice-config` 与 `/api/workpapers/*/sheets/*/onlyoffice-config`），
于是客户端 `Date.now()` 兜底成为实际路径，Word doc_key 每次打开都变。

判定为**出范围**，理由是可验证的而不是划界方便：

1. 它是**前端端点契约**缺陷（前端请求了一条不存在的路由），修法是统一 launch descriptor
   与前端 DTO —— 那是 Task 25（唯一 launch descriptor）/ Task 31（前端 DTO + generated
   manifest）/ Task 64（Word editor 宿主迁移）的范围。Task 21 的边界是 room 身份与资格判定。
2. 它**不阻塞** RG-17。实测：这 5 条 docx entry 的宿主端点无匹配 provider ⇒
   `matched=False` ⇒ `shared_doc_key=False`，profile 侧 `room_model=exclusive`，
   RG-17 的 exclusive 分支要求的正是 `not shared_doc_key` + `participant_lease` ⇒ 接线后通过。
   接线**没有掩盖**这个缺陷：它仍如实记在 manifest 的
   `scenario_profile.doc_key_defects = [frontend_endpoint_without_backend_route,
   client_local_doc_key_fallback]` 里。
3. 在 Task 21 里顺手加一条后端路由会**扩大**范围而不是收敛：那条路由要返回什么 substrate
   （legacy 文件 vs staged representation）恰恰是 Task 25/26 未决的事。

本任务对 Word 侧做的是范围内的那一半：**已存在**的 `/api/projects/*/working-papers/*/onlyoffice-config`
的 `document_key` 从 `wp-{wp_id}-{file_version}-{pf|raw}` 换成 room 身份派生
（Requirement 2.1 禁止 `file_version` 充当跨通道同步版本；`prefilled` 是展示态，进 doc_key
会让同一份文件在两个房间里被并行编辑）。M45 检验这一条。

## 十一、辐射面回归：按引用关系反查，不跑全量

全量 `backend/tests` 有 1522 个测试文件，前台跑数分钟无输出会被当卡死。改用**引用关系反查**：
扫全部 `test_*.py` 里对本次改动物（`rooms`/`RoomService`/`derive_doc_key`/
`onlyoffice_room_identity`/两个 router/`advance_server_last_applied`/`build_request_freeze`/
`ContributorSource`/`room_service_wiring`/`observe_room_facts`/`doc_key_providers`/
`correlate_durable_incoming`/`fold_effective_sequence` 等）的实际引用 ⇒ **30 个文件**，
再并上 Task 12/13/15/16/18/19/20 的既有守卫。

结果 **1025 passed / 65 failed**。65 条逐条归因，三类：

### (a) 本次改动引入、已修（原 2 类共 6 处）

* `test_onlyoffice_single_file_dockey.py` / `test_wp_onlyoffice_router.py` 两处
  `from app.routers.wp_onlyoffice_router import _generate_doc_key` ⇒ **collection ImportError**。
  这正是反向引用扫描的价值：不扫就会在 CI 上才发现。已把两处 characterization 迁到 room 身份
  语义（mtime 断言方向反转，见 §二）。
* config 端点四个用例的 `db.execute` mock 写死两项 `side_effect` ⇒ 新增的 room 查询让它们
  `StopIteration`。改成 `_db_execute(前两项…)` + 其后一律返回 `_empty_result()` ——
  **刻意不写死总调用次数**：写死之后任何一次「多查一条辅助数据」都会让整组用例崩掉，
  而崩掉的原因与被测行为无关，那是最容易被误读成回归的假红。

### (b) 本次改动引起的**生成物** stale、已重生成（4 条）

`backend/data/workpaper_writer_inventory.json` 的 `source_digest` 随生产源码变化。逐行归因
（不看总数 —— 该文件是并发多会话共用生成物）：

* 首轮 **10 行变化，全部落在我改的两个文件里，零 foreign 行**，无行增删，**22 项 stats 全部未变**
  （含 `multi_resolver=4`、`bypass_unified_commit=261`）；
* 唯一的语义变化是 `wp_editor_router.get_wp_onlyoffice_config` 的
  `facts.version_fields_read: ['file_version'] -> []` —— 恰好就是我这次改动的效果，方向是变好；
* 其余全是行号位移（其中 `wp_editor_router.py` 的位移含并发会话已在工作树里的 Task 18/19 改动）。

据此 `--apply` 重生成清册，并连带重生成派生的
`workpaper_resolver_migration_matrix.json`（delta **只有三个 digest**，`by_status` 仍是
`deferred 66 / migrated 13`，Task 12 登记的四条 `wp_onlyoffice_router` deferred 行**一个字节未变** ——
Task 20 的门仍红，本任务没有去碰它）。

> 后续把 router 的调用改成单行（为让变异有稳定单行锚点）后，清册第二次 stale，
> 同样逐行归因（8 行、全 MINE、零 foreign、stats 未变）后重生成。

### (c) 既存失败，与本任务无关（55 条）

* **`public_router` 家族（50 条）**：`test_wp_onlyoffice_router.py`（26）、
  `test_onlyoffice_word_template_callback.py`（5）等，全部 `404`。根因是 health / `wopi/contents` /
  `onlyoffice-callback` 三类端点注册在 `public_router` 上，而这些测试的测试 app 只
  `include_router(router)`。**决定性取证**：`git show HEAD:` 取出两个测试文件，
  `include_router(router)` 31 次 / `public_router` **0 次**，而 HEAD 的 router 已经有
  `@public_router.get("/onlyoffice/health")` ⇒ HEAD 上同样 404。
* **`test_property_archived_invariant`（1 条）**：`POST /api/projects/{pid}/adjustments` 归档项目
  返 403 而非 423，与 doc_key/room 无关。
* **Task 73（8 条）**：manifest stale + 「room service 仍未接线」这条前提被推翻，见 §四。

## 十二、没能验证的部分

1. **真实浏览器 / 真实 OO 9.4 的协同验收**：本任务只做后端 room 身份与策略，没有起 OO 容器做
   两用户实测。「stable doc_key 让两个用户真的进同一间房」这条**只有** Task 44/70 的真实
   OO gate 能给终局证据；本轮给到的是「同 wp+entry+generation 派生出同一 key」+ V151 的
   `uq_wpoor_doc_key` / `uq_wpoor_generation` 两条唯一约束。
2. **legacy substrate 上「稳定 key + OO 缓存」的长尾**：该共享缓存文件的内容写入方只有
   OO callback 自己（`_resolve_wp_file` 只在首次从模板复制），所以「OO 写完自己缓存里就是新内容」
   在推理上成立，但**没有做浏览器实测**。真正的收口是 Task 25/26 的 staged artifact +
   representation publish（同时也解掉 Requirement 9.12 那处就地改写）。
3. **`record_contributor_snapshot` 的一条纵深防御未被变异覆盖**：
   「route credential 被当成 contributor participant id 传进来」那条 `raise` 在当前 harness 里
   不可达（credential 是 uuid5，不可能等于任何 participant id），故没有对应变异。它是结构性
   防御（`RouteCredential` 类型里根本没有 participant 字段，`mint_route_credential` 签名里也没有
   user/participant 入参，由 `test_mint_signature_has_no_user_or_participant_parameter` 正面钉住）。
4. **Task 20 的 writer/version gate 仍红**（`multi_resolver = 4`，四行全在
   `wp_onlyoffice_router`）。按交接要求没有去关它：那四行的 substrate 要变成 room/staged
   representation，依赖 Task 25/26。本任务只让这个判据**变得可达**。
